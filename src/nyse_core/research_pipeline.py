"""Research pipeline: factors -> normalize -> combine -> validate -> stats.
Pure logic backbone for the NYSE ATS research flow. No I/O, no logging.
"""

from __future__ import annotations

import gc
from datetime import date
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from nyse_core.allocator import equal_weight, select_top_n
from nyse_core.contracts import (
    BacktestResult,
    CompositeScore,
    Diagnostics,
    reject_holdout_dates,
)
from nyse_core.cost_model import estimate_cost_bps
from nyse_core.impute import cross_sectional_impute
from nyse_core.metrics import cagr, max_drawdown, sharpe_ratio
from nyse_core.normalize import rank_percentile, winsorize
from nyse_core.schema import (
    COL_DATE,
    COL_SYMBOL,
    DEFAULT_SELL_BUFFER,
    TRADING_DAYS_PER_YEAR,
)
from nyse_core.signal_combination import _validate_feature_range, create_model
from nyse_core.statistics import (
    block_bootstrap_ci,
    permutation_test,
)

if TYPE_CHECKING:
    from nyse_core.features.registry import FactorRegistry

_SRC = "research_pipeline"

# Weekly rebalance step: every 5 trading days
_REBAL_STEP = 5
# Trailing OHLCV window for feature computation (approx. 1 year)
_TRAILING_WINDOW = 252


class ResearchPipeline:
    """Factor -> normalize -> combine -> walk-forward validate -> statistics."""

    def __init__(
        self,
        registry: FactorRegistry,
        model_type: str = "ridge",
        model_kwargs: dict | None = None,
        target_horizon_days: int = 5,
        top_n: int = 20,
    ) -> None:
        self.registry = registry
        self.model_type = model_type
        self.model_kwargs = model_kwargs or {}
        self.target_horizon_days = target_horizon_days
        self.top_n = top_n

    # ── Stage 1+2+3: Compute, normalize, impute ─────────────────────────

    def compute_feature_matrix(
        self,
        ohlcv: pd.DataFrame,
        fundamentals: pd.DataFrame | None = None,
        rebalance_date: date | None = None,
    ) -> tuple[pd.DataFrame, Diagnostics]:
        """Compute, normalize, impute features. Returns (symbols x factors) in [0,1]."""
        diag = Diagnostics()
        src = f"{_SRC}.compute_feature_matrix"

        # Iron rule 1: refuse holdout-era feature computation up front.
        reject_holdout_dates(rebalance_date, source=src)
        if COL_DATE in ohlcv.columns:
            reject_holdout_dates(pd.to_datetime(ohlcv[COL_DATE]), source=src)
        if fundamentals is not None and COL_DATE in fundamentals.columns:
            reject_holdout_dates(pd.to_datetime(fundamentals[COL_DATE]), source=src)

        if rebalance_date is None:
            # Use the latest date in ohlcv
            dates = pd.to_datetime(ohlcv[COL_DATE])
            rebalance_date = dates.max().date() if hasattr(dates.max(), "date") else dates.max()

        # Stage 1: Compute raw features — route to correct data sources
        data_sources: dict[str, pd.DataFrame] = {"ohlcv": ohlcv}
        if fundamentals is not None:
            data_sources["fundamentals"] = fundamentals
        raw_features, feat_diag = self.registry.compute_all(data_sources, rebalance_date)
        diag.merge(feat_diag)

        if raw_features.empty:
            diag.warning(src, "No features computed -- returning empty DataFrame.")
            return raw_features, diag

        # Stage 2a: Winsorize at 1st/99th percentile to limit outlier influence
        winsorized: dict[str, pd.Series] = {}
        for col in raw_features.columns:
            w_series, w_diag = winsorize(raw_features[col])
            diag.merge(w_diag)
            winsorized[col] = w_series
        winsorized_df = pd.DataFrame(winsorized, index=raw_features.index)

        # Stage 2b: Normalize each factor cross-sectionally with rank_percentile
        normalized: dict[str, pd.Series] = {}
        for col in winsorized_df.columns:
            normed, norm_diag = rank_percentile(winsorized_df[col])
            diag.merge(norm_diag)
            normalized[col] = normed

        norm_df = pd.DataFrame(normalized, index=raw_features.index)

        # Stage 3: Impute -- cross_sectional_impute needs a 'date' column
        # We add a synthetic date column since our data is a single cross-section
        impute_df = norm_df.copy()
        impute_df[COL_DATE] = rebalance_date
        imputed, imp_diag = cross_sectional_impute(impute_df, max_missing_pct=0.30)
        diag.merge(imp_diag)

        # Drop the date column after imputation
        feature_cols = [c for c in imputed.columns if c != COL_DATE]
        result = imputed[feature_cols]

        # Drop any columns that are entirely NaN after imputation
        all_nan_cols = result.columns[result.isna().all()].tolist()
        if all_nan_cols:
            result = result.drop(columns=all_nan_cols)
            diag.warning(
                src,
                f"Dropped {len(all_nan_cols)} all-NaN feature(s) after imputation: {all_nan_cols}",
            )

        diag.info(
            src,
            f"Feature matrix: {result.shape[0]} symbols x {result.shape[1]} factors.",
            n_symbols=result.shape[0],
            n_factors=result.shape[1],
        )
        return result, diag

    # ── Stage 4: Fit combination model ───────────────────────────────────

    def fit_combination_model(
        self,
        feature_matrix: pd.DataFrame,
        forward_returns: pd.Series,
    ) -> tuple[CompositeScore, Diagnostics]:
        """Fit CombinationModel on features vs forward returns; return CompositeScore."""
        diag = Diagnostics()
        src = f"{_SRC}.fit_combination_model"

        # AP-8 validation
        _validate_feature_range(feature_matrix, src)

        # Align features and returns
        common_idx = feature_matrix.index.intersection(forward_returns.index)
        X = feature_matrix.loc[common_idx].dropna()
        y = forward_returns.loc[X.index]

        if len(X) < 3:
            diag.error(src, f"Too few samples ({len(X)}) after alignment/dropna.")
            empty_scores = pd.Series(dtype=float)
            return CompositeScore(
                scores=empty_scores,
                rebalance_date=date.today(),
                model_type=self.model_type,
                feature_importance={},
            ), diag

        # Create and fit model
        model, _ = create_model(self.model_type, **self.model_kwargs)
        fit_diag = model.fit(X, y)
        diag.merge(fit_diag)

        # Predict on full feature_matrix (including samples without returns)
        predict_X = feature_matrix.dropna()
        scores, pred_diag = model.predict(predict_X)
        diag.merge(pred_diag)

        importance = model.get_feature_importance()

        composite = CompositeScore(
            scores=scores,
            rebalance_date=date.today(),
            model_type=self.model_type,
            feature_importance=importance,
        )

        diag.info(
            src,
            f"Composite scores: {len(scores)} symbols, model={self.model_type}.",
            n_scored=len(scores),
        )
        return composite, diag

    # ── Stage 5: Walk-forward validation ─────────────────────────────────

    def run_walk_forward_validation(
        self,
        ohlcv: pd.DataFrame,
        fundamentals: pd.DataFrame | None = None,
        n_folds: int = 4,
        sell_buffer: float = DEFAULT_SELL_BUFFER,
        rebal_step: int = _REBAL_STEP,
    ) -> tuple[BacktestResult, Diagnostics]:
        """Expanding-window walk-forward backtest with proper per-date stacking,
        feature recomputation at each test date, sell-buffer portfolio construction,
        and dynamic cost estimation. Returns (BacktestResult, Diagnostics).
        """
        diag = Diagnostics()
        src = f"{_SRC}.run_walk_forward_validation"

        # Iron rule 1: walk-forward must not see any holdout-era bar.
        if COL_DATE in ohlcv.columns:
            reject_holdout_dates(pd.to_datetime(ohlcv[COL_DATE]), source=src)
        if fundamentals is not None and COL_DATE in fundamentals.columns:
            reject_holdout_dates(pd.to_datetime(fundamentals[COL_DATE]), source=src)

        dates_raw = sorted(ohlcv[COL_DATE].unique())
        dates_arr = pd.DatetimeIndex(pd.to_datetime(dates_raw))
        n_dates = len(dates_arr)

        ohlcv_dt = ohlcv.copy()
        ohlcv_dt[COL_DATE] = pd.to_datetime(ohlcv_dt[COL_DATE])
        close_pivot = ohlcv_dt.pivot_table(
            index=COL_DATE,
            columns=COL_SYMBOL,
            values="close",
            aggfunc="last",
        ).sort_index()
        fwd_ret = close_pivot.shift(-self.target_horizon_days) / close_pivot - 1

        vol_pivot = ohlcv_dt.pivot_table(
            index=COL_DATE,
            columns=COL_SYMBOL,
            values="volume",
            aggfunc="last",
        ).sort_index()
        adv_20d = (close_pivot * vol_pivot).rolling(20, min_periods=5).mean()

        cv, folds, err_result = _init_cv_folds(
            n_dates,
            n_folds,
            self.target_horizon_days,
            dates_arr,
            diag,
            src,
        )
        if err_result is not None:
            return err_result, diag

        all_oos_ret: list[pd.Series] = []
        all_turnovers: list[float] = []
        all_costs: list[float] = []
        per_fold_sharpe: list[float] = []
        per_factor_contrib: dict[str, float] = {}

        for fold_idx, (train_idx, test_idx) in enumerate(folds):
            train_dates = dates_arr[train_idx]
            test_dates = dates_arr[test_idx]

            # Build stacked training cross-sections (sampled weekly)
            X_train, y_train, td = self._build_train_stack(
                ohlcv_dt,
                fwd_ret,
                train_dates,
                fundamentals,
                rebal_step,
                diag,
            )
            if X_train is None:
                diag.warning(src, f"Fold {fold_idx}: insufficient training data.")
                gc.collect()
                continue

            model, _ = create_model(self.model_type, **self.model_kwargs)
            diag.merge(model.fit(X_train, y_train))
            del X_train, y_train

            # Walk through test dates
            fold_ret, fold_dates, fold_to, fold_co = self._run_test_dates(
                model,
                ohlcv_dt,
                fwd_ret,
                adv_20d,
                test_dates,
                fundamentals,
                sell_buffer,
                rebal_step,
                diag,
            )
            if fold_ret:
                series = pd.Series(fold_ret, index=fold_dates, name="returns")
                all_oos_ret.append(series)
                all_turnovers.extend(fold_to)
                all_costs.extend(fold_co)
                per_fold_sharpe.append(sharpe_ratio(series)[0])
                for k, v in model.get_feature_importance().items():
                    per_factor_contrib[k] = per_factor_contrib.get(k, 0.0) + v

            diag.info(src, f"Fold {fold_idx}: {len(fold_ret)} test rebalances.", fold=fold_idx)
            del model
            gc.collect()

        if not all_oos_ret:
            diag.error(src, "No valid folds produced OOS returns.")
            return _empty_backtest_result(), diag

        combined = pd.concat(all_oos_ret).sort_index()
        total_imp = sum(per_factor_contrib.values())
        if total_imp > 0:
            per_factor_contrib = {k: v / total_imp for k, v in per_factor_contrib.items()}

        avg_to = float(np.mean(all_turnovers)) if all_turnovers else 0.0
        ann_turnover = avg_to * (TRADING_DAYS_PER_YEAR / rebal_step)
        total_cost = float(np.sum(all_costs)) if all_costs else 0.0
        gross_cum = float((1 + combined).prod() - 1) if len(combined) > 0 else 0.0
        cost_drag_pct = total_cost / max(abs(gross_cum), 1e-9)

        result = BacktestResult(
            daily_returns=combined,
            oos_sharpe=sharpe_ratio(combined)[0],
            oos_cagr=cagr(combined)[0],
            max_drawdown=max_drawdown(combined)[0],
            annual_turnover=ann_turnover,
            cost_drag_pct=cost_drag_pct,
            per_fold_sharpe=per_fold_sharpe,
            per_factor_contribution=per_factor_contrib,
        )
        diag.info(
            src,
            f"Walk-forward complete: OOS Sharpe={result.oos_sharpe:.3f}, "
            f"turnover={ann_turnover:.2f}, cost_drag={cost_drag_pct:.4f}.",
        )
        return result, diag

    # ── WF helpers (private) ────────────────────────────────────────────

    def _build_train_stack(
        self,
        ohlcv_dt: pd.DataFrame,
        fwd_ret: pd.DataFrame,
        train_dates: pd.DatetimeIndex,
        fundamentals: pd.DataFrame | None,
        rebal_step: int,
        diag: Diagnostics,
    ) -> tuple[pd.DataFrame | None, pd.Series | None, Diagnostics]:
        """Stack per-date cross-sections for training (sampled weekly)."""
        X_rows: list[pd.DataFrame] = []
        y_rows: list[pd.Series] = []
        td = Diagnostics()
        for rd in train_dates[::rebal_step]:
            rd_date = rd.date() if hasattr(rd, "date") else rd
            window_start = rd - pd.Timedelta(days=int(_TRAILING_WINDOW * 1.5))
            tw = ohlcv_dt[(ohlcv_dt[COL_DATE] <= rd) & (ohlcv_dt[COL_DATE] >= window_start)]
            if tw.empty or rd not in fwd_ret.index:
                continue
            feat, fd = self.compute_feature_matrix(tw, fundamentals=fundamentals, rebalance_date=rd_date)
            diag.merge(fd)
            if feat.empty or feat.shape[1] == 0:
                continue
            fwd_at = fwd_ret.loc[rd]
            common = feat.index.intersection(fwd_at.dropna().index)
            if len(common) < 5:
                continue
            fa = feat.loc[common].dropna()
            ya = fwd_at.loc[fa.index]
            mi = pd.MultiIndex.from_arrays(
                [np.full(len(fa), rd_date), fa.index],
                names=["rebal_date", "symbol"],
            )
            fa.index = mi
            ya.index = mi
            X_rows.append(fa)
            y_rows.append(ya)
        if not X_rows:
            return None, None, td
        X = pd.concat(X_rows)
        y = pd.concat(y_rows)
        valid = X.notna().all(axis=1) & y.notna()
        X, y = X.loc[valid], y.loc[valid]
        if len(X) < 10:
            return None, None, td
        return X, y, td

    def _run_test_dates(
        self,
        model: object,
        ohlcv_dt: pd.DataFrame,
        fwd_ret: pd.DataFrame,
        adv_20d: pd.DataFrame,
        test_dates: pd.DatetimeIndex,
        fundamentals: pd.DataFrame | None,
        sell_buffer: float,
        rebal_step: int,
        diag: Diagnostics,
    ) -> tuple[list[float], list, list[float], list[float]]:
        """Iterate test dates, recomputing features and tracking turnover/cost."""
        rets: list[float] = []
        dates_out: list = []
        turnovers: list[float] = []
        costs: list[float] = []
        holdings: set[str] = set()
        prev_w: dict[str, float] = {}

        for td in test_dates[::rebal_step]:
            if td not in fwd_ret.index:
                continue
            td_d = td.date() if hasattr(td, "date") else td
            ws = td - pd.Timedelta(days=int(_TRAILING_WINDOW * 1.5))
            t_ohlcv = ohlcv_dt[(ohlcv_dt[COL_DATE] <= td) & (ohlcv_dt[COL_DATE] >= ws)]
            if t_ohlcv.empty:
                continue
            feat, fd = self.compute_feature_matrix(t_ohlcv, fundamentals=fundamentals, rebalance_date=td_d)
            diag.merge(fd)
            pX = feat.dropna() if not feat.empty and feat.shape[1] > 0 else pd.DataFrame()
            if pX.empty:
                continue
            scores, pd_diag = model.predict(pX)
            diag.merge(pd_diag)
            # Clear index name to avoid ambiguity in allocator sort_frame
            scores.index.name = None

            selected, sd = select_top_n(
                scores, n=self.top_n, current_holdings=holdings, sell_buffer=sell_buffer
            )
            diag.merge(sd)
            if not selected:
                continue
            nw, wd = equal_weight(selected)
            diag.merge(wd)

            all_s = set(nw) | set(prev_w)
            turnover = sum(abs(nw.get(s, 0.0) - prev_w.get(s, 0.0)) for s in all_s)

            cost_bps_total = 0.0
            for s in all_s:
                wd_val = abs(nw.get(s, 0.0) - prev_w.get(s, 0.0))
                if wd_val < 1e-9:
                    continue
                adv = _safe_adv(adv_20d, td, s)
                cb, _ = estimate_cost_bps(adv)
                cost_bps_total += cb * wd_val
            cost_ret = cost_bps_total / 10_000.0

            sel_fwd = fwd_ret.loc[td].reindex(selected).dropna()
            if len(sel_fwd) == 0:
                continue
            net = float(sel_fwd.mean()) - cost_ret

            rets.append(net)
            dates_out.append(td)
            turnovers.append(turnover)
            costs.append(cost_ret)
            prev_w = nw
            holdings = set(selected)
        return rets, dates_out, turnovers, costs

    # ── Stage 6: Statistical validation ──────────────────────────────────

    def run_statistical_validation(
        self,
        backtest_result: BacktestResult,
    ) -> tuple[BacktestResult, Diagnostics]:
        """Permutation test, bootstrap CI, Romano-Wolf stepdown."""
        diag = Diagnostics()
        src = f"{_SRC}.run_statistical_validation"
        returns = backtest_result.daily_returns
        if returns.empty or len(returns) < 10:
            diag.warning(src, "Insufficient returns for statistical tests.")
            return backtest_result, diag

        bs = min(21, len(returns) // 2)
        p_value, perm_diag = permutation_test(returns, n_reps=200, block_size=bs)
        diag.merge(perm_diag)
        ci, boot_diag = block_bootstrap_ci(returns, n_reps=500, block_size=bs, alpha=0.05)
        diag.merge(boot_diag)

        # Romano-Wolf requires actual per-factor long-short return series,
        # not synthetic decompositions (returns * weight is NOT a valid
        # factor return series). Per-factor RW testing should be performed
        # via factor_screening.screen_factor on individual factor returns.
        rw_pvals: dict[str, float] | None = None
        diag.info(
            src,
            "Per-factor Romano-Wolf deferred to factor_screening "
            "(requires actual factor long-short returns, not portfolio decomposition).",
        )

        bt = backtest_result
        updated = BacktestResult(
            daily_returns=bt.daily_returns,
            oos_sharpe=bt.oos_sharpe,
            oos_cagr=bt.oos_cagr,
            max_drawdown=bt.max_drawdown,
            annual_turnover=bt.annual_turnover,
            cost_drag_pct=bt.cost_drag_pct,
            per_fold_sharpe=bt.per_fold_sharpe,
            per_factor_contribution=bt.per_factor_contribution,
            permutation_p_value=p_value,
            bootstrap_ci_lower=ci[0],
            bootstrap_ci_upper=ci[1],
            romano_wolf_p_values=rw_pvals,
        )
        diag.info(src, f"Stats: perm_p={p_value:.4f}, CI=[{ci[0]:.3f}, {ci[1]:.3f}].")
        return updated, diag

    # ── Convenience ─────────────────────────────────────────────────────

    def run_full_pipeline(
        self,
        ohlcv: pd.DataFrame,
        fundamentals: pd.DataFrame | None = None,
    ) -> tuple[BacktestResult, Diagnostics]:
        """Run stages 1-6 end-to-end."""
        diag = Diagnostics()
        bt_result, wf_diag = self.run_walk_forward_validation(
            ohlcv,
            fundamentals=fundamentals,
            n_folds=3,
        )
        diag.merge(wf_diag)
        if bt_result.daily_returns.empty:
            return bt_result, diag
        validated, stat_diag = self.run_statistical_validation(bt_result)
        diag.merge(stat_diag)
        return validated, diag


def _init_cv_folds(
    n_dates: int,
    n_folds: int,
    horizon: int,
    dates_arr: pd.DatetimeIndex,
    diag: Diagnostics,
    src: str,
) -> tuple[object | None, list, BacktestResult | None]:
    """Configure PurgedWalkForwardCV and return folds. Returns (cv, folds, err)."""
    from nyse_core.cv import PurgedWalkForwardCV
    from nyse_core.schema import MIN_TRAIN_YEARS

    min_train = max(MIN_TRAIN_YEARS * TRADING_DAYS_PER_YEAR, n_dates // 3)
    purge = embargo = horizon
    gap = purge + embargo
    remaining = n_dates - min_train
    max_test = max(10, (remaining // n_folds) - gap)
    test_days = min(max_test, max(21, n_dates // (n_folds + 2)))
    try:
        cv = PurgedWalkForwardCV(
            n_folds=n_folds,
            min_train_days=min_train,
            test_days=test_days,
            purge_days=purge,
            embargo_days=embargo,
            target_horizon_days=horizon,
        )
    except ValueError as e:
        diag.error(src, f"CV init failed: {e}")
        return None, [], _empty_backtest_result()
    try:
        folds = list(cv.split(dates_arr))
    except ValueError as e:
        diag.error(src, f"CV split failed: {e}")
        return None, [], _empty_backtest_result()
    return cv, folds, None


def _safe_adv(adv_20d: pd.DataFrame, t_date: object, symbol: str) -> float:
    """Safely retrieve 20-day ADV; fall back to 50M if unavailable."""
    if t_date in adv_20d.index and symbol in adv_20d.columns:
        val = adv_20d.loc[t_date, symbol]
        if not pd.isna(val) and val > 0:
            return float(val)
    return 50_000_000.0


def _empty_backtest_result() -> BacktestResult:
    """Return an empty BacktestResult for error paths."""
    return BacktestResult(
        daily_returns=pd.Series(dtype=float),
        oos_sharpe=0.0,
        oos_cagr=0.0,
        max_drawdown=0.0,
        annual_turnover=0.0,
        cost_drag_pct=0.0,
        per_fold_sharpe=[],
        per_factor_contribution={},
    )
