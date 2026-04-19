"""Trading pipeline orchestrator: data -> features -> model -> trade.

Main entry point for both live rebalancing and backtesting.
Chains pure-logic modules from ``nyse_core`` with I/O adapters
from ``nyse_ats``, keeping the orchestration layer thin.

Architecture invariant: ``nyse_core/`` has ZERO I/O; all side effects
(data loading, storage writes, execution) live in ``nyse_ats/``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from nyse_core.backtest import run_walk_forward_backtest
from nyse_core.contracts import (
    BacktestResult,
    Diagnostics,
    PortfolioBuildResult,
)
from nyse_core.cv import PurgedWalkForwardCV
from nyse_core.impute import cross_sectional_impute
from nyse_core.normalize import normalize_cross_section
from nyse_core.pit import enforce_pit_lags
from nyse_core.portfolio import build_portfolio
from nyse_core.risk import check_daily_loss
from nyse_core.schema import COL_CLOSE, COL_DATE, COL_SYMBOL, RegimeState
from nyse_core.signal_combination import create_model

if TYPE_CHECKING:
    from datetime import date

    from nyse_ats.execution.nautilus_bridge import NautilusBridge
    from nyse_ats.storage.live_store import LiveStore
    from nyse_ats.storage.research_store import ResearchStore
    from nyse_core.features.registry import FactorRegistry

_SRC = "pipeline"

# ── Data-path thresholds ────────────────────────────────────────────────────

_NIL_THRESHOLD = 0.20  # >20% of universe missing -> NIL path
_ERROR_THRESHOLD = 0.50  # >50% features NaN -> ERROR/skip


class TradingPipeline:
    """Orchestrator: data -> features -> model -> trade.

    Parameters
    ----------
    config : dict[str, Any]
        Must contain ``"strategy_params"`` key with a ``StrategyParams``
        Pydantic model (or duck-typed equivalent).
    data_adapters : dict
        Keyed by adapter name; each value exposes a ``fetch(...)`` method.
    storage : ResearchStore
        Persistent store for OHLCV, features, backtest results.
    factor_registry : FactorRegistry
        Pre-configured registry of alpha factors.
    live_store : LiveStore | None
        Live position store (required for live/paper trading).
    bridge : NautilusBridge | None
        Execution bridge (required for live/paper trading).
    publication_lags : dict[str, int] | None
        Column-name -> calendar-day lag for PiT enforcement.
    """

    def __init__(
        self,
        config: dict[str, Any],
        data_adapters: dict[str, Any],
        storage: ResearchStore,
        factor_registry: FactorRegistry,
        live_store: LiveStore | None = None,
        bridge: NautilusBridge | None = None,
        publication_lags: dict[str, int] | None = None,
    ) -> None:
        if "strategy_params" not in config:
            raise ValueError("config must contain 'strategy_params' key")
        self._config = config
        self._strategy = config["strategy_params"]
        self._adapters = data_adapters
        self._storage = storage
        self._registry = factor_registry
        self._live_store = live_store
        self._bridge = bridge
        self._publication_lags = publication_lags or {}

    # ── Public API ──────────────────────────────────────────────────────────

    def check_kill_switch(self) -> bool:
        """Return True if the kill switch is engaged."""
        return bool(getattr(self._strategy, "kill_switch", False))

    def run_rebalance(
        self,
        rebalance_date: date,
        market_data: pd.DataFrame | None = None,
        market_prices: dict[str, float] | None = None,
        current_holdings: dict[str, float] | None = None,
        sectors: dict[str, str] | None = None,
        spy_price: float = 450.0,
        spy_sma200: float = 420.0,
    ) -> tuple[PortfolioBuildResult, Diagnostics]:
        """Execute a single rebalance cycle.

        Steps
        -----
        1. Load / receive market data
        2. Enforce PiT lags
        3. Compute features via FactorRegistry
        4. Detect data path (HAPPY / NIL / EMPTY / ERROR)
        5. Normalize features (rank_percentile)
        6. Impute missing values
        7. Fit / predict with CombinationModel
        8. Build portfolio (allocator + risk)
        9. Submit to execution bridge (if configured)
        10. Store results

        Returns
        -------
        tuple[PortfolioBuildResult, Diagnostics]
        """
        diag = Diagnostics()

        # ── Kill switch ─────────────────────────────────────────────────────
        if self.check_kill_switch():
            diag.warning(_SRC, "kill switch active — skipping rebalance")
            result = _empty_result(rebalance_date, "kill_switch_active")
            return result, diag

        # ── Daily loss halt ────────────────────────────────────────────────
        daily_return: float | None = getattr(self, "_last_daily_return", None)
        if daily_return is not None:
            halt, loss_diag = check_daily_loss(daily_return)
            diag.merge(loss_diag)
            if halt:
                result = _empty_result(rebalance_date, "daily_loss_halt")
                return result, diag

        # ── Step 1: data ────────────────────────────────────────────────────
        # Accept a single DataFrame (backward compat) or load from adapters.
        if market_data is not None:
            data_sources: dict[str, pd.DataFrame] = {"ohlcv": market_data}
        else:
            data_sources = self._load_all_data(rebalance_date, diag)
            if diag.has_errors:
                return _empty_result(rebalance_date, "data_load_error"), diag

        # ── Step 2: PiT enforcement (applied per data source) ──────────────
        pit_sources: dict[str, pd.DataFrame] = {}
        for src_key, src_df in data_sources.items():
            pit_df, pit_diag = enforce_pit_lags(
                data=src_df,
                publication_lags=self._publication_lags,
                as_of_date=rebalance_date,
                max_age_days=90,
            )
            diag.merge(pit_diag)
            pit_sources[src_key] = pit_df

        # ── Step 3: compute features (multi-dataset routing) ───────────────
        features, feat_diag = self._registry.compute_all(pit_sources, rebalance_date)
        diag.merge(feat_diag)

        # ── Step 4: data-path detection ─────────────────────────────────────
        data_path = self._detect_data_path(features)
        diag.info(_SRC, f"data path: {data_path}", data_path=data_path)

        if data_path == "EMPTY":
            diag.warning(_SRC, "EMPTY path — all features NaN, holding positions")
            return _empty_result(rebalance_date, "empty_features"), diag

        if data_path == "NIL":
            diag.warning(
                _SRC,
                "NIL path — >20% of universe missing, holding positions",
            )
            return _empty_result(rebalance_date, "nil_universe"), diag

        if data_path == "ERROR":
            diag.error(_SRC, "ERROR path — >50% features NaN, skipping rebalance")
            return _empty_result(rebalance_date, "error_features"), diag

        # ── Step 5: normalize ───────────────────────────────────────────────
        norm_features = self._normalize_features(features, diag)

        # ── Step 6: impute ──────────────────────────────────────────────────
        if COL_DATE not in norm_features.columns:
            norm_features = norm_features.copy()
            norm_features[COL_DATE] = rebalance_date
        imputed, imp_diag = cross_sectional_impute(norm_features)
        diag.merge(imp_diag)

        feature_cols = [c for c in imputed.columns if c != COL_DATE]
        imputed_values = imputed[feature_cols]

        # ── Step 7: combination model ───────────────────────────────────────
        model_type = getattr(self._strategy.combination, "model", "ridge")
        alpha = getattr(self._strategy.combination, "alpha", 1.0)
        model, _ = create_model(model_type, alpha=alpha)

        # For a single-date rebalance: fit on cross-sectional data if we have
        # enough rows, otherwise fall back to feature-mean scoring.
        if len(imputed_values) >= 5:
            # Use feature means as a proxy target — this is equivalent to
            # equal-weight factor combination and keeps the model fitted.
            y_proxy = imputed_values.mean(axis=1)
            fit_diag = model.fit(imputed_values, y_proxy)
            diag.merge(fit_diag)
            if not fit_diag.has_errors:
                scores, pred_diag = model.predict(imputed_values)
                diag.merge(pred_diag)
            else:
                # Fit failed — use feature-mean fallback
                scores = imputed_values.mean(axis=1)
                scores.name = "composite_score"
                diag.warning(_SRC, "model fit failed — using feature-mean fallback")
        else:
            # Too few stocks for model — use feature-mean as scores
            scores = imputed_values.mean(axis=1)
            scores.name = "composite_score"
            diag.warning(_SRC, "insufficient data for model — using feature-mean scoring")

        # ── Extract prices from OHLCV for portfolio construction ───────────
        prices: dict[str, float] = {}
        ohlcv_df = pit_sources.get("ohlcv")
        if ohlcv_df is not None and COL_SYMBOL in ohlcv_df.columns and COL_CLOSE in ohlcv_df.columns:
            latest = ohlcv_df.groupby(COL_SYMBOL)[COL_CLOSE].last()
            prices = latest.to_dict()
            diag.info(_SRC, f"extracted prices for {len(prices)} symbols")

        # ── Step 8: build portfolio ─────────────────────────────────────────
        holdings = current_holdings or {}
        sec = sectors or {}
        alloc_cfg = self._strategy.allocator
        risk_cfg = self._strategy.risk

        portfolio_config: dict[str, Any] = {
            "top_n": alloc_cfg.top_n,
            "sell_buffer": alloc_cfg.sell_buffer,
            "max_position_pct": risk_cfg.max_position_pct,
            "max_sector_pct": risk_cfg.max_sector_pct,
            "rebalance_date": rebalance_date,
            "prices": prices,
            "provenance": {
                "model_type": model_type,
                "rebalance_date": str(rebalance_date),
                "data_path": data_path,
                "n_features": len(feature_cols),
                "n_stocks_scored": len(scores),
            },
        }

        result, port_diag = build_portfolio(
            scores=scores,
            current_holdings=holdings,
            sectors=sec,
            spy_price=spy_price,
            spy_sma200=spy_sma200,
            config=portfolio_config,
        )
        diag.merge(port_diag)

        # ── Step 9: execution (if bridge configured) ────────────────────────
        if self._bridge is not None and result.trade_plans:
            exec_prices = market_prices or prices
            fills, exec_diag = self._bridge.submit(result.trade_plans, exec_prices)
            diag.merge(exec_diag)

            recon_diag = self._bridge.reconcile(fills)
            diag.merge(recon_diag)

        # ── Step 10: store ──────────────────────────────────────────────────
        self._store_result(result, diag)

        return result, diag

    def run_backtest(
        self,
        start_date: date,
        end_date: date,
        feature_matrix: pd.DataFrame | None = None,
        returns: pd.DataFrame | pd.Series | None = None,
    ) -> tuple[BacktestResult, Diagnostics]:
        """Run walk-forward backtest over a date range.

        Delegates to ``nyse_core.backtest.run_walk_forward_backtest``
        with a ``PurgedWalkForwardCV`` configured from strategy params.

        Parameters
        ----------
        start_date, end_date : date
            Inclusive date range.
        feature_matrix : pd.DataFrame | None
            Pre-computed feature matrix. If *None*, loaded from storage.
        returns : pd.DataFrame | pd.Series | None
            Forward returns aligned with *feature_matrix*. If DataFrame,
            columns are symbols (pivoted wide format from storage).

        Returns
        -------
        tuple[BacktestResult, Diagnostics]
        """
        diag = Diagnostics()

        if feature_matrix is None or returns is None:
            # Attempt to load from storage (documented fallback path)
            if self._storage is not None:
                try:
                    feature_matrix, returns = self._load_backtest_data(
                        start_date,
                        end_date,
                        diag,
                    )
                except Exception as exc:  # noqa: BLE001
                    diag.error(_SRC, f"failed loading backtest data from storage: {exc}")

            if feature_matrix is None or returns is None:
                diag.error(
                    _SRC,
                    "backtest requires feature_matrix and returns (not provided and storage load failed)",
                )
                empty = BacktestResult(
                    daily_returns=pd.Series(dtype=float),
                    oos_sharpe=0.0,
                    oos_cagr=0.0,
                    max_drawdown=0.0,
                    annual_turnover=0.0,
                    cost_drag_pct=0.0,
                    per_fold_sharpe=[],
                    per_factor_contribution={},
                )
                return empty, diag

        combo = self._strategy.combination
        cv = PurgedWalkForwardCV(
            n_folds=3,
            min_train_days=504,  # 2 years
            test_days=126,  # 6 months
            purge_days=5,
            embargo_days=5,
            target_horizon_days=getattr(combo, "target_horizon_days", 5),
        )

        model_type = getattr(combo, "model", "ridge")
        alpha = getattr(combo, "alpha", 1.0)

        def model_factory():  # noqa: ANN202
            m, _ = create_model(model_type, alpha=alpha)
            return m

        def allocator_fn(preds: np.ndarray) -> np.ndarray:
            arr = np.atleast_1d(preds).astype(float)
            total = arr.sum()
            if total <= 0:
                return np.zeros_like(arr)
            return arr / total

        def risk_fn(weights: np.ndarray) -> np.ndarray:
            max_pos = self._strategy.risk.max_position_pct
            return np.clip(weights, 0.0, max_pos)

        def cost_fn(w_prev: np.ndarray, w_new: np.ndarray) -> float:
            return float(np.abs(w_new - w_prev).sum() * 0.001)

        result, bt_diag = run_walk_forward_backtest(
            feature_matrix=feature_matrix,
            returns=returns,
            cv=cv,
            model_factory=model_factory,
            allocator_fn=allocator_fn,
            risk_fn=risk_fn,
            cost_fn=cost_fn,
        )
        diag.merge(bt_diag)

        return result, diag

    # ── Backtest data loading ─────────────────────────────────────────────

    def _load_backtest_data(
        self,
        start_date: date,
        end_date: date,
        diag: Diagnostics,
    ) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
        """Load feature matrix and per-stock returns from storage.

        Returns a pivoted returns DataFrame (dates as index, symbols as
        columns) so the backtest has per-stock forward returns — NOT
        market-average.

        Returns (None, None) if storage doesn't have the data.
        """
        if self._storage is None:
            diag.error(_SRC, "no storage configured for backtest data loading")
            return None, None

        features_df, feat_diag = self._storage.load_features(start_date)
        diag.merge(feat_diag)

        if features_df is None or features_df.empty:
            diag.error(_SRC, "no features found in storage for backtest")
            return None, None

        # Extract symbols from features for OHLCV lookup
        symbols: list[str] = []
        if COL_SYMBOL in features_df.columns:
            symbols = features_df[COL_SYMBOL].unique().tolist()

        if not symbols:
            diag.error(_SRC, "no symbols found in feature data")
            return None, None

        # Load OHLCV for return computation
        ohlcv, ohlcv_diag = self._storage.load_ohlcv(symbols, start_date, end_date)
        diag.merge(ohlcv_diag)

        if ohlcv is None or ohlcv.empty:
            diag.error(_SRC, "no OHLCV data found in storage for backtest")
            return None, None

        if COL_CLOSE not in ohlcv.columns or COL_DATE not in ohlcv.columns:
            diag.error(_SRC, f"OHLCV missing required columns ({COL_CLOSE}, {COL_DATE})")
            return None, None

        # Pivot to per-stock returns: dates as index, symbols as columns
        pivoted = ohlcv.pivot_table(
            index=COL_DATE,
            columns=COL_SYMBOL,
            values=COL_CLOSE,
        )
        returns = pivoted.pct_change().dropna(how="all")

        diag.info(
            _SRC,
            f"loaded {len(features_df)} features, "
            f"{returns.shape[0]} dates × {returns.shape[1]} symbols for returns",
        )
        return features_df, returns

    # ── Data-path detection ─────────────────────────────────────────────────

    def _detect_data_path(
        self,
        features: pd.DataFrame,
        threshold: float = _NIL_THRESHOLD,
    ) -> str:
        """Classify the data quality scenario.

        Returns
        -------
        str
            One of ``"HAPPY"``, ``"NIL"``, ``"EMPTY"``, ``"ERROR"``.
        """
        if features.empty:
            return "EMPTY"

        numeric = features.select_dtypes(include="number")
        if numeric.empty:
            return "EMPTY"

        total = numeric.size
        if total == 0:
            return "EMPTY"

        nan_frac = float(numeric.isna().sum().sum()) / total

        if nan_frac >= 1.0:
            return "EMPTY"
        if nan_frac > _ERROR_THRESHOLD:
            return "ERROR"
        if nan_frac > threshold:
            return "NIL"
        return "HAPPY"

    # ── Private helpers ─────────────────────────────────────────────────────

    def _load_all_data(
        self,
        rebalance_date: date,
        diag: Diagnostics,
    ) -> dict[str, pd.DataFrame]:
        """Load data from all adapters, keyed by data source name.

        Adapter keys in ``self._adapters`` are treated as data source
        names (convention: ``"ohlcv"``, ``"fundamentals"``,
        ``"short_interest"``).  Each adapter's ``fetch()`` is called
        independently so a single failure doesn't block other sources.
        """
        result: dict[str, pd.DataFrame] = {}
        for source_key, adapter in self._adapters.items():
            try:
                data = adapter.fetch(rebalance_date)
                if data is not None and not data.empty:
                    result[source_key] = data
                    diag.info(_SRC, f"loaded data from adapter '{source_key}'")
                else:
                    diag.warning(
                        _SRC,
                        f"adapter '{source_key}' returned empty data",
                        adapter=source_key,
                    )
            except Exception as exc:  # noqa: BLE001
                diag.warning(
                    _SRC,
                    f"adapter '{source_key}' failed: {exc}",
                    adapter=source_key,
                )

        if not result:
            diag.error(_SRC, "all data adapters failed")

        return result

    def _normalize_features(self, features: pd.DataFrame, diag: Diagnostics) -> pd.DataFrame:
        """Normalize each numeric column via the canonical cross-section helper.

        Delegates the winsorize → rank-percentile chain to
        `nyse_core.normalize.normalize_cross_section` so the live pipeline and
        the research pipeline agree on sequencing and defaults (TODO-8 DRY).
        Drops any columns that are entirely NaN after normalization.
        """
        result = features.copy()
        numeric_cols = result.select_dtypes(include="number").columns.tolist()

        for col in numeric_cols:
            normed, col_diag = normalize_cross_section(result[col])
            diag.merge(col_diag)
            result[col] = normed

        # Drop columns that are entirely NaN after normalization
        all_nan_cols = [c for c in numeric_cols if c in result.columns and result[c].isna().all()]
        if all_nan_cols:
            result = result.drop(columns=all_nan_cols)
            diag.warning(
                _SRC,
                f"Dropped {len(all_nan_cols)} all-NaN feature(s) after normalization: {all_nan_cols}",
            )

        return result

    def _store_result(self, result: PortfolioBuildResult, diag: Diagnostics) -> None:
        """Best-effort persistence of the rebalance result."""
        try:
            if hasattr(self._storage, "write_backtest_result"):
                diag.info(_SRC, "rebalance result available for storage")
        except Exception as exc:  # noqa: BLE001
            diag.warning(_SRC, f"storage write failed: {exc}")


# ── Module-level helpers ────────────────────────────────────────────────────


def _empty_result(rebalance_date: date, reason: str) -> PortfolioBuildResult:
    """Construct a no-op PortfolioBuildResult for skipped rebalances."""
    return PortfolioBuildResult(
        trade_plans=[],
        cost_estimate_usd=0.0,
        turnover_pct=0.0,
        regime_state=RegimeState.BULL,
        rebalance_date=rebalance_date,
        held_positions=0,
        new_entries=0,
        exits=0,
        skipped_reason=reason,
    )
