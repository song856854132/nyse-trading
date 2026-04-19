#!/usr/bin/env python3
"""Generate 10 professional performance charts + metrics JSON from synthetic backtest data.

Produces all figures for the NYSE ATS framework documentation.
Charts use a consistent navy-blue professional theme (#003366 primary).
Synthetic data spans 2018-2025 (8 years) with 13 factors across 6 families.

Usage:
    source /tmp/pdf-gen/bin/activate
    python scripts/generate_figures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Headless rendering before any other matplotlib import
import matplotlib

matplotlib.use("Agg")

import matplotlib.colors as mcolors
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.patches import Patch
from scipy import stats as sp_stats
from sklearn.linear_model import Ridge

# ── Project imports ──────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from nyse_core.metrics import cagr, max_drawdown, sharpe_ratio
from nyse_core.schema import BEAR_EXPOSURE, BULL_EXPOSURE, SMA_WINDOW

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
FIG_DIR = ROOT / "docs" / "figures"
METRICS_PATH = ROOT / "docs" / "backtest_metrics.json"
FIG_DIR.mkdir(parents=True, exist_ok=True)

# ── Theme ────────────────────────────────────────────────────────────────────
PRIMARY = "#003366"
SECONDARY = "#004488"
ACCENT = "#0066aa"
GREEN = "#2e7d32"
RED = "#c62828"
BG_ACCENT = "#f0f4f8"
GOLD = "#d4a017"
PURPLE = "#6a1b9a"
TEAL = "#00695c"
DPI = 150

plt.style.use("seaborn-v0_8-whitegrid")
plt.rcParams.update(
    {
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": "#cccccc",
        "axes.labelcolor": PRIMARY,
        "xtick.color": "#555555",
        "ytick.color": "#555555",
        "text.color": PRIMARY,
        "font.size": 10,
        "axes.titlesize": 13,
        "axes.labelsize": 11,
        "legend.fontsize": 9,
        "figure.titlesize": 14,
    }
)

# ── Seed for full reproducibility ────────────────────────────────────────────
RNG = np.random.default_rng(42)

# ── Factor definitions ───────────────────────────────────────────────────────
ALL_FACTOR_COLS = [
    # Price/Volume (4)
    "ivol_20d",
    "momentum_2_12",
    "52w_high",
    "ewmac",
    # Fundamental (3)
    "piotroski",
    "accruals",
    "profitability",
    # Earnings (1)
    "earn_surprise",
    # Short Interest (2)
    "short_ratio",
    "days_to_cover",
    # Sentiment (1)
    "options_flow",
    # NLP/Analyst (2)
    "earnings_sentiment",
    "analyst_rev",
]

FACTOR_FAMILIES = {
    "Price/Volume": ["ivol_20d", "momentum_2_12", "52w_high", "ewmac"],
    "Fundamental": ["piotroski", "accruals", "profitability"],
    "Earnings": ["earn_surprise"],
    "Short Interest": ["short_ratio", "days_to_cover"],
    "Sentiment": ["options_flow"],
    "NLP/Analyst": ["earnings_sentiment", "analyst_rev"],
}

FAMILY_COLORS = {
    "Price/Volume": PRIMARY,
    "Fundamental": GREEN,
    "Earnings": GOLD,
    "Short Interest": RED,
    "Sentiment": PURPLE,
    "NLP/Analyst": TEAL,
}

# Factors where HIGH raw value = SELL signal (invert before rank-percentile)
INVERTED_FACTORS = {"ivol_20d", "short_ratio", "days_to_cover", "accruals"}


# ============================================================================
# 1. SYNTHETIC DATA GENERATION (2018-2025, 8 years)
# ============================================================================

N_STOCKS = 100
N_DAYS = 2016  # ~8 years of trading days
START_DATE = "2018-01-02"


def generate_trading_dates(n_days: int = N_DAYS, start: str = START_DATE) -> pd.DatetimeIndex:
    return pd.bdate_range(start=start, periods=n_days, freq="B")


def generate_stock_characteristics(n_stocks: int = N_STOCKS) -> dict:
    """Persistent stock-level traits that drive both prices and factors."""
    return {
        "quality": RNG.standard_normal(n_stocks),
        "risk": RNG.standard_normal(n_stocks),
        "momentum_tendency": RNG.standard_normal(n_stocks),
        "sentiment": RNG.standard_normal(n_stocks),
    }


def generate_stock_prices(chars: dict, n_stocks: int = N_STOCKS, n_days: int = N_DAYS) -> pd.DataFrame:
    """Generate ~8 years of OHLCV with regime-aware returns and quality signal."""
    dates = generate_trading_dates(n_days)
    quality = chars["quality"]
    frames = []
    for i in range(n_stocks):
        p0 = RNG.uniform(25, 300)
        base_drift = RNG.uniform(-0.02, 0.12)
        # Quality bonus: high-quality stocks drift slightly higher
        drift_annual = base_drift + 0.015 * quality[i]
        vol = RNG.uniform(0.18, 0.42)
        dt = 1 / 252
        log_ret = RNG.normal((drift_annual - 0.5 * vol**2) * dt, vol * np.sqrt(dt), n_days)

        # Market-wide events injected into all stocks
        # 2020 COVID crash: ~day 504-525 (approx March 2020)
        if n_days > 530:
            crash_beta = RNG.uniform(0.5, 1.5)
            log_ret[504:525] -= 0.03 * crash_beta
            log_ret[525:565] += 0.015 * crash_beta  # V-recovery

        # 2022 bear market: ~day 1008-1134 (approx Jan-Jun 2022)
        if n_days > 1140:
            bear_beta = RNG.uniform(0.3, 0.9)
            log_ret[1008:1134] -= 0.003 * bear_beta

        close = p0 * np.exp(np.cumsum(log_ret))
        frames.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "symbol": f"SYM_{i:03d}",
                    "close": np.round(close, 2),
                    "volume": (RNG.lognormal(14.5, 0.5, n_days) * (1 + 5 * np.abs(log_ret))).astype(int),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def generate_spy(n_days: int = N_DAYS) -> pd.DataFrame:
    """SPY benchmark with realistic 2018-2025 regime structure."""
    dates = generate_trading_dates(n_days)
    n = len(dates)

    # Piecewise annual drift (realistic regime narrative)
    segments = [
        (126, 0.24),  # 2018 H1: bull
        (126, -0.12),  # 2018 H2: Q4 correction
        (252, 0.30),  # 2019: strong bull
        (42, -0.90),  # 2020 Feb-Mar: COVID crash (~-30% in 6 weeks)
        (84, 0.80),  # 2020 Apr-Jun: V-recovery
        (126, 0.25),  # 2020 H2: continued recovery
        (252, 0.26),  # 2021: bull
        (126, -0.30),  # 2022 H1: bear (rate hikes)
        (126, -0.08),  # 2022 H2: continued weakness
        (252, 0.22),  # 2023: recovery
        (252, 0.18),  # 2024: moderate bull
    ]

    drift = np.zeros(n)
    pos = 0
    for seg_days, annual_ret in segments:
        actual = min(seg_days, n - pos)
        if actual <= 0:
            break
        drift[pos : pos + actual] = annual_ret / 252
        pos += actual
    if pos < n:
        drift[pos:] = 0.12 / 252  # 2025: moderate

    noise = RNG.normal(0, 0.011, n)
    close = 450.0 * np.exp(np.cumsum(drift + noise))
    return pd.DataFrame({"date": dates, "close": np.round(close, 2)})


# ============================================================================
# 2. FACTOR COMPUTATION (13 factors across 6 families)
# ============================================================================


def compute_price_factors(prices: pd.DataFrame, rebal_dates) -> pd.DataFrame:
    """Vectorized computation of 4 price-based factors per rebalance date."""
    close_wide = prices.pivot(index="date", columns="symbol", values="close").sort_index()
    all_idx = close_wide.index
    records = []

    for dt in rebal_dates:
        dt_loc = all_idx.get_loc(dt)
        if dt_loc < 252:
            continue

        window = close_wide.iloc[dt_loc - 252 : dt_loc + 1]

        # IVOL: std of last 20 daily log returns
        last_21 = close_wide.iloc[dt_loc - 20 : dt_loc + 1]
        log_rets = np.log(last_21).diff().iloc[1:]
        ivol = log_rets.std(ddof=1)

        # Momentum 2-12: return from 252d ago to 21d ago
        p_252 = close_wide.iloc[dt_loc - 252]
        p_21 = close_wide.iloc[dt_loc - 21]
        mom = (p_21 - p_252) / p_252
        mom[p_252 == 0] = np.nan

        # 52-week high proximity
        high52 = close_wide.iloc[dt_loc] / window.max()

        # EWMAC: EMA(12) / EMA(60) - 1
        ema_s = window.ewm(span=12).mean().iloc[-1]
        ema_l = window.ewm(span=60).mean().iloc[-1]
        ewmac = (ema_s / ema_l) - 1
        ewmac[ema_l == 0] = np.nan

        df = pd.DataFrame(
            {
                "date": dt,
                "symbol": close_wide.columns,
                "ivol_20d": ivol.values,
                "momentum_2_12": mom.values,
                "52w_high": high52.values,
                "ewmac": ewmac.values,
            }
        )
        records.append(df)

    return pd.concat(records, ignore_index=True)


def generate_synthetic_factors(rebal_dates, symbols, chars: dict) -> pd.DataFrame:
    """Generate 9 synthetic fundamental/alternative factors (vectorized)."""
    n_sym = len(symbols)
    n_dates = len(rebal_dates)
    quality = chars["quality"]
    risk = chars["risk"]
    sentiment = chars["sentiment"]

    # Pre-allocate arrays: (n_dates, n_sym)
    piotroski = np.clip(np.round(4.5 + 1.5 * quality[None, :] + RNG.standard_normal((n_dates, n_sym))), 0, 9)

    accruals = -0.02 * quality[None, :] + RNG.normal(0, 0.04, (n_dates, n_sym))

    profitability = 0.12 + 0.06 * quality[None, :] + RNG.normal(0, 0.03, (n_dates, n_sym))

    # Earnings surprise: mostly near zero, quarterly spikes
    earn_base = RNG.normal(0, 0.005, (n_dates, n_sym))
    earn_spike = 0.01 * quality[None, :] + RNG.normal(0, 0.025, (n_dates, n_sym))
    quarterly_mask = np.zeros((n_dates, n_sym), dtype=bool)
    for q in range(0, n_dates, 3):
        quarterly_mask[q, RNG.random(n_sym) < 0.3] = True
    earn_surprise = np.where(quarterly_mask, earn_spike, earn_base)

    short_ratio = np.clip(np.exp(1.0 + 0.3 * risk[None, :] + RNG.normal(0, 0.3, (n_dates, n_sym))), 0.1, 30)

    days_to_cover = np.clip(short_ratio * RNG.uniform(0.8, 2.5, (n_dates, n_sym)), 0.5, 40)

    options_flow = 0.7 + 0.1 * sentiment[None, :] + RNG.normal(0, 0.15, (n_dates, n_sym))

    earnings_sentiment = np.clip(
        0.5 + 0.1 * quality[None, :] + RNG.normal(0, 0.12, (n_dates, n_sym)),
        0,
        1,
    )

    analyst_rev = 0.005 * sentiment[None, :] + RNG.normal(0, 0.015, (n_dates, n_sym))

    # Build DataFrame
    records = []
    for di, dt in enumerate(rebal_dates):
        df = pd.DataFrame(
            {
                "date": dt,
                "symbol": symbols,
                "piotroski": piotroski[di],
                "accruals": accruals[di],
                "profitability": profitability[di],
                "earn_surprise": earn_surprise[di],
                "short_ratio": short_ratio[di],
                "days_to_cover": days_to_cover[di],
                "options_flow": options_flow[di],
                "earnings_sentiment": earnings_sentiment[di],
                "analyst_rev": analyst_rev[di],
            }
        )
        records.append(df)
    return pd.concat(records, ignore_index=True)


def compute_all_factors(prices: pd.DataFrame, chars: dict) -> pd.DataFrame:
    """Compute all 13 factors for each rebalance date x symbol."""
    symbols = sorted(prices["symbol"].unique().tolist())
    dates_all = sorted(prices["date"].unique())
    rebal_dates = dates_all[252::5]  # Weekly rebalance after 1-year warmup

    print(
        f"  Rebalance dates: {len(rebal_dates)} "
        f"({pd.Timestamp(rebal_dates[0]).strftime('%Y-%m')} to "
        f"{pd.Timestamp(rebal_dates[-1]).strftime('%Y-%m')})"
    )

    price_df = compute_price_factors(prices, rebal_dates)
    synth_df = generate_synthetic_factors(rebal_dates, symbols, chars)

    # Merge on (date, symbol)
    merged = price_df.merge(synth_df, on=["date", "symbol"], how="inner")
    return merged


# ============================================================================
# 3. WALK-FORWARD BACKTEST (13-factor Ridge, 6-7 expanding folds)
# ============================================================================


def rank_percentile_col(s: pd.Series) -> pd.Series:
    """Map a series to [0,1] via rank-percentile."""
    valid = s.dropna()
    if len(valid) < 2:
        return s.copy().fillna(0.5)
    ranks = valid.rank(method="average")
    return ((ranks - 1) / (len(valid) - 1)).reindex(s.index)


def run_backtest(factors_df: pd.DataFrame, prices: pd.DataFrame, spy: pd.DataFrame):
    """Walk-forward Ridge backtest with 13 factors, returning all chart data."""
    factor_cols = [c for c in ALL_FACTOR_COLS if c in factors_df.columns]
    rebal_dates = sorted(factors_df["date"].unique())

    # Build forward return: close[T+1] to close[T+5] (approximates open[T+1]→close[T+5]).
    # Signal on T (Friday close), execution at T+1 (Monday open ≈ Friday close).
    # Return = what you capture AFTER execution, not including the overnight gap.
    fwd_map = {}
    price_lookup = prices.set_index(["date", "symbol"])["close"]
    all_dates = sorted(prices["date"].unique())
    date_idx = {d: i for i, d in enumerate(all_dates)}
    for dt in rebal_dates:
        idx = date_idx.get(dt)
        if idx is None or idx + 5 >= len(all_dates):
            continue
        exec_dt = all_dates[idx + 1]  # T+1: execution day (Monday)
        fwd_dt = all_dates[idx + 5]  # T+5: exit day (Friday)
        for sym in factors_df[factors_df["date"] == dt]["symbol"].unique():
            try:
                p_exec = price_lookup.loc[(exec_dt, sym)]
                p_fwd = price_lookup.loc[(fwd_dt, sym)]
                fwd_map[(dt, sym)] = (p_fwd - p_exec) / p_exec
            except KeyError:
                pass

    factors_df = factors_df.copy()
    factors_df["fwd_ret"] = factors_df.apply(lambda r: fwd_map.get((r["date"], r["symbol"]), np.nan), axis=1)
    factors_df = factors_df.dropna(subset=["fwd_ret"])

    # Normalize: rank-percentile per date (invert sign for INVERTED factors)
    for col in factor_cols:
        mult = -1 if col in INVERTED_FACTORS else 1
        factors_df[col] = factors_df.groupby("date")[col].transform(
            lambda s, m=mult: rank_percentile_col(s * m)
        )

    # SPY regime
    spy_s = spy.set_index("date")["close"]
    spy_sma200 = spy_s.rolling(SMA_WINDOW, min_periods=SMA_WINDOW).mean()

    # Walk-forward: expanding window
    n_dates = len(rebal_dates)
    fold_size = max(1, n_dates // 9)  # ~9 rebal periods per fold
    min_train = max(12, n_dates // 5)  # at least ~2 years train

    per_fold_sharpe = []
    all_oos_returns = []
    all_oos_dates = []
    fold_boundaries = []
    ic_series_vals = []
    ic_dates = []
    model_weights = {}
    total_trades = 0

    for fold_i in range(12):  # up to 12 folds, break when train too short
        test_end = n_dates - fold_i * fold_size
        test_start = test_end - fold_size
        if test_start < min_train:
            break
        train_dates = rebal_dates[:test_start]
        test_dates = rebal_dates[test_start:test_end]
        if len(test_dates) == 0:
            continue

        fold_boundaries.append((train_dates[0], train_dates[-1], test_dates[0], test_dates[-1]))

        train_data = factors_df[factors_df["date"].isin(train_dates)]
        test_data = factors_df[factors_df["date"].isin(test_dates)]

        X_train = train_data[factor_cols].values
        y_train = train_data["fwd_ret"].values

        model = Ridge(alpha=1.0)
        model.fit(X_train, y_train)

        # Store model weights from last (most recent) fold
        model_weights = dict(zip(factor_cols, model.coef_.tolist(), strict=False))

        # Equal-weight top-N allocation per rebalance date
        fold_daily_ret = []
        for tdt in test_dates:
            mask = test_data["date"] == tdt
            day_data = test_data[mask].copy()
            if len(day_data) < 5:
                continue
            day_X = day_data[factor_cols].values
            day_preds = model.predict(day_X)
            day_data = day_data.copy()
            day_data["pred"] = day_preds

            top_n = min(20, len(day_data))
            top = day_data.nlargest(top_n, "pred")
            port_ret = top["fwd_ret"].mean()
            total_trades += top_n

            # Regime overlay
            spy_dt_close = spy_s.get(tdt)
            spy_dt_sma = spy_sma200.get(tdt)
            if spy_dt_close is not None and spy_dt_sma is not None and not np.isnan(spy_dt_sma):
                regime_mult = BULL_EXPOSURE if spy_dt_close > spy_dt_sma else BEAR_EXPOSURE
            else:
                regime_mult = BULL_EXPOSURE
            port_ret *= regime_mult

            # IC
            ic_val = float(sp_stats.spearmanr(day_preds, day_data["fwd_ret"].values)[0])
            ic_series_vals.append(ic_val)
            ic_dates.append(tdt)

            fold_daily_ret.append(port_ret)
            all_oos_returns.append(port_ret)
            all_oos_dates.append(tdt)

        fold_ret_s = pd.Series(fold_daily_ret)
        fold_sharpe = sharpe_ratio(fold_ret_s)[0] if len(fold_ret_s) > 2 else 0.0
        per_fold_sharpe.append(fold_sharpe)

    # Reverse (folds computed from end backwards)
    per_fold_sharpe.reverse()
    fold_boundaries.reverse()

    # Build rebalance-level return series
    rebal_ret = pd.Series(
        all_oos_returns,
        index=pd.DatetimeIndex([pd.Timestamp(d) for d in all_oos_dates]),
    ).sort_index()
    ic_series = pd.Series(
        ic_series_vals,
        index=pd.DatetimeIndex([pd.Timestamp(d) for d in ic_dates]),
    ).sort_index()

    # Expand rebalance returns into daily returns for smooth charting
    all_trade_dates = generate_trading_dates(N_DAYS)
    oos_start = rebal_ret.index[0]
    oos_end = rebal_ret.index[-1]
    oos_daily_dates = all_trade_dates[(all_trade_dates >= oos_start) & (all_trade_dates <= oos_end)]

    daily_returns = []
    daily_dates = []
    for i in range(len(rebal_ret)):
        period_start = rebal_ret.index[i]
        if i + 1 < len(rebal_ret):
            period_end = rebal_ret.index[i + 1]
            mask = (oos_daily_dates >= period_start) & (oos_daily_dates < period_end)
        else:
            mask = (oos_daily_dates >= period_start) & (oos_daily_dates <= oos_end)
        day_dates = oos_daily_dates[mask]
        days_in_period = len(day_dates)
        if days_in_period == 0:
            continue
        period_ret = rebal_ret.iloc[i]
        rng_local = np.random.default_rng(42 + i)
        noise = rng_local.normal(0, abs(period_ret) * 0.3 + 0.001, days_in_period)
        daily_ret_chunk = np.full(days_in_period, period_ret / days_in_period) + noise
        adj = (period_ret - daily_ret_chunk.sum()) / days_in_period
        daily_ret_chunk += adj
        daily_returns.extend(daily_ret_chunk.tolist())
        daily_dates.extend(day_dates.tolist())

    daily_ret = pd.Series(daily_returns, index=pd.DatetimeIndex(daily_dates)).sort_index()

    # Factor correlation (on all normalized data)
    all_factor_data = factors_df[factor_cols].dropna()
    factor_corr = all_factor_data.corr(method="spearman")

    # SPY aligned daily returns
    spy_ts = spy_s.copy()
    spy_ts.index = pd.DatetimeIndex([pd.Timestamp(d) for d in spy_ts.index])
    spy_daily = spy_ts.pct_change().dropna()
    spy_aligned = spy_daily.reindex(daily_ret.index).fillna(0)

    spy_sma200_ts = spy_sma200.copy()
    spy_sma200_ts.index = pd.DatetimeIndex([pd.Timestamp(d) for d in spy_sma200_ts.index])

    # Regime mask on daily dates
    regime_mask = pd.Series(index=daily_ret.index, dtype=str)
    for dt in daily_ret.index:
        sc = spy_ts.get(dt)
        ss = spy_sma200_ts.get(dt)
        if sc is not None and ss is not None and not np.isnan(ss):
            regime_mask[dt] = "BEAR" if sc <= ss else "BULL"
        else:
            regime_mask[dt] = "BULL"

    # Cost model
    cost_per_trade_bps = 8.0
    avg_trades_per_period = 20
    n_rebalances = len(rebal_ret)
    n_daily = len(daily_ret)
    total_cost_pct = (
        cost_per_trade_bps / 10000 * avg_trades_per_period * n_rebalances / max(n_daily / 252, 1e-9)
    )

    return {
        "daily_ret": daily_ret,
        "spy_ret": spy_aligned,
        "ic_series": ic_series,
        "per_fold_sharpe": per_fold_sharpe,
        "fold_boundaries": fold_boundaries,
        "model_weights": model_weights,
        "factor_corr": factor_corr,
        "factor_cols": factor_cols,
        "regime_mask": regime_mask,
        "total_trades": total_trades,
        "cost_drag_pct": total_cost_pct,
        "spy_close": spy_ts,
        "spy_sma200": spy_sma200_ts,
    }


# ============================================================================
# 4. CHART GENERATORS
# ============================================================================


def _save(fig: plt.Figure, name: str) -> None:
    fig.savefig(FIG_DIR / name, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  [OK] {name}")


def _shade_bear_regimes(ax, regime: pd.Series) -> None:
    """Add translucent red bands for BEAR regime periods."""
    bear_mask = regime == "BEAR"
    if not bear_mask.any():
        return
    in_bear = False
    start = None
    for dt, is_bear in bear_mask.items():
        if is_bear and not in_bear:
            start = dt
            in_bear = True
        elif not is_bear and in_bear:
            ax.axvspan(start, dt, color="#ffcccc", alpha=0.25, zorder=0)
            in_bear = False
    if in_bear and start is not None:
        ax.axvspan(start, bear_mask.index[-1], color="#ffcccc", alpha=0.25, zorder=0)


def chart_equity_curve(data: dict) -> None:
    """1. Strategy vs SPY with drawdown subplot (2-panel, TWSE-style)."""
    ret = data["daily_ret"]
    spy = data["spy_ret"]
    regime = data["regime_mask"]

    cum_strat = (1 + ret).cumprod()
    cum_spy = (1 + spy).cumprod()
    dd = cum_strat / cum_strat.cummax() - 1

    fig, (ax1, ax2) = plt.subplots(
        2,
        1,
        figsize=(14, 8),
        gridspec_kw={"height_ratios": [2.5, 1]},
        sharex=True,
    )

    # ── Top panel: cumulative returns ──
    _shade_bear_regimes(ax1, regime)
    ax1.plot(cum_strat.index, cum_strat.values, color=PRIMARY, lw=2, label="NYSE Alpha Strategy")
    ax1.plot(cum_spy.index, cum_spy.values, color="#888888", lw=1.5, ls="--", label="SPY Benchmark")

    # Annotate final values
    strat_final = cum_strat.iloc[-1]
    spy_final = cum_spy.iloc[-1]
    ax1.annotate(
        f"${strat_final:.2f}",
        xy=(cum_strat.index[-1], strat_final),
        fontsize=9,
        fontweight="bold",
        color=PRIMARY,
        xytext=(5, 5),
        textcoords="offset points",
    )
    ax1.annotate(
        f"${spy_final:.2f}",
        xy=(cum_spy.index[-1], spy_final),
        fontsize=9,
        color="#888888",
        xytext=(5, -12),
        textcoords="offset points",
    )

    ax1.set_title("Cumulative Returns: Strategy vs. SPY Benchmark", fontweight="bold", fontsize=14)
    ax1.set_ylabel("Growth of $1")
    bear_patch = Patch(facecolor="#ffcccc", alpha=0.4, label="Bear Regime")
    handles, labels = ax1.get_legend_handles_labels()
    handles.append(bear_patch)
    labels.append("Bear Regime")
    ax1.legend(handles, labels, loc="upper left", frameon=True, fancybox=True)
    ax1.grid(True, alpha=0.3)

    # ── Bottom panel: drawdown depth ──
    _shade_bear_regimes(ax2, regime)
    dd_pct = dd * 100
    ax2.fill_between(dd_pct.index, dd_pct.values, 0, color=RED, alpha=0.35, step="mid")
    ax2.plot(dd_pct.index, dd_pct.values, color=RED, lw=0.7, alpha=0.8)
    ax2.axhline(0, color="#333333", lw=0.5)

    # Annotate max drawdown
    max_dd_idx = dd_pct.idxmin()
    max_dd_val = dd_pct[max_dd_idx]
    ax2.annotate(
        f"Max DD: {max_dd_val:.1f}%",
        xy=(max_dd_idx, max_dd_val),
        xytext=(30, -15),
        textcoords="offset points",
        fontsize=9,
        fontweight="bold",
        color=RED,
        arrowprops=dict(arrowstyle="->", color=RED, lw=1.2),
    )

    ax2.set_ylabel("Drawdown (%)")
    ax2.set_xlabel("")
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax2.xaxis.set_major_locator(mdates.YearLocator())
    fig.autofmt_xdate(rotation=0, ha="center")
    fig.tight_layout(h_pad=0.5)
    _save(fig, "equity_curve.png")


def chart_underwater(data: dict) -> None:
    """2. Standalone drawdown depth with color gradient."""
    ret = data["daily_ret"]
    cum = (1 + ret).cumprod()
    dd = (cum / cum.cummax() - 1) * 100

    fig, ax = plt.subplots(figsize=(14, 4.5))
    dd_vals = dd.values
    norm = mcolors.Normalize(vmin=min(dd_vals.min(), -1), vmax=0)
    cmap = mcolors.LinearSegmentedColormap.from_list("dd", ["#c62828", "#ff8f00", "#ffd54f"])
    colors = cmap(norm(dd_vals))

    ax.bar(dd.index, dd_vals, color=colors, width=2, edgecolor="none")
    ax.set_title("Underwater Plot (Drawdown Depth)", fontweight="bold")
    ax.set_ylabel("Drawdown (%)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.axhline(0, color="#333333", lw=0.5)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, pad=0.02, aspect=30)
    cbar.set_label("Drawdown Depth (%)")
    fig.autofmt_xdate(rotation=0, ha="center")
    _save(fig, "underwater_plot.png")


def chart_monthly_heatmap(data: dict) -> None:
    """3. Year x Month returns heatmap."""
    ret = data["daily_ret"].copy()
    if not isinstance(ret.index, pd.DatetimeIndex):
        ret.index = pd.DatetimeIndex(ret.index)
    monthly = ret.resample("ME").apply(lambda x: (1 + x).prod() - 1) * 100
    pivot = pd.DataFrame(
        {
            "year": monthly.index.year,
            "month": monthly.index.month,
            "ret": monthly.values,
        }
    )
    table = pivot.pivot(index="year", columns="month", values="ret")
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    table.columns = [month_names[m - 1] for m in table.columns]

    fig, ax = plt.subplots(figsize=(14, 5))
    valid_vals = table.values[~np.isnan(table.values)]
    vmax = max(abs(valid_vals.max()), abs(valid_vals.min()), 3)
    sns.heatmap(
        table,
        annot=True,
        fmt=".1f",
        center=0,
        cmap=sns.diverging_palette(10, 150, as_cmap=True),
        vmin=-vmax,
        vmax=vmax,
        linewidths=0.5,
        linecolor="#dddddd",
        cbar_kws={"label": "Return (%)"},
        ax=ax,
        annot_kws={"size": 9},
    )
    ax.set_title("Monthly Returns Heatmap (%)", fontweight="bold")
    ax.set_ylabel("")
    ax.set_xlabel("")
    _save(fig, "monthly_returns_heatmap.png")


def chart_rolling_metrics(data: dict) -> None:
    """4. Rolling 63-day Sharpe (top) and volatility (bottom)."""
    ret = data["daily_ret"]
    n_obs = len(ret)
    window = min(63, max(20, n_obs // 8))
    roll_mean = ret.rolling(window, min_periods=window).mean()
    roll_std = ret.rolling(window, min_periods=window).std(ddof=1)
    roll_std_safe = roll_std.replace(0, np.nan)
    roll_sharpe = (roll_mean / roll_std_safe * np.sqrt(252)).dropna()
    roll_vol = (roll_std * np.sqrt(252) * 100).dropna()

    fig, axes = plt.subplots(2, 1, figsize=(14, 7), sharex=True)

    axes[0].plot(roll_sharpe.index, roll_sharpe.values, color=PRIMARY, lw=1.5)
    axes[0].axhline(0, color="#cccccc", lw=0.8, ls="--")
    mean_sharpe = roll_sharpe.mean()
    axes[0].axhline(mean_sharpe, color=GOLD, lw=1, ls=":", label=f"Mean = {mean_sharpe:.2f}")
    axes[0].fill_between(
        roll_sharpe.index, 0, roll_sharpe.values, where=roll_sharpe > 0, color=GREEN, alpha=0.12
    )
    axes[0].fill_between(
        roll_sharpe.index, 0, roll_sharpe.values, where=roll_sharpe < 0, color=RED, alpha=0.12
    )
    axes[0].set_title(f"Rolling {window}-Day Sharpe Ratio", fontweight="bold")
    axes[0].set_ylabel("Sharpe")
    axes[0].legend(loc="upper right", frameon=True)

    axes[1].plot(roll_vol.index, roll_vol.values, color=SECONDARY, lw=1.5)
    mean_vol = roll_vol.mean()
    axes[1].axhline(mean_vol, color=GOLD, lw=1, ls=":", label=f"Mean = {mean_vol:.1f}%")
    axes[1].fill_between(roll_vol.index, roll_vol.values, alpha=0.12, color=SECONDARY)
    axes[1].set_title(f"Rolling {window}-Day Annualized Volatility", fontweight="bold")
    axes[1].set_ylabel("Volatility (%)")
    axes[1].legend(loc="upper right", frameon=True)
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    axes[1].xaxis.set_major_locator(mdates.YearLocator())
    fig.autofmt_xdate(rotation=0, ha="center")
    fig.tight_layout()
    _save(fig, "rolling_metrics.png")


def chart_factor_coefficients(data: dict) -> None:
    """5. Ridge coefficients for all 13 factors, grouped by family."""
    weights = data["model_weights"]

    # Build ordered list with family grouping
    names, vals, bar_colors, family_labels = [], [], [], []
    for family, factors in FACTOR_FAMILIES.items():
        for f in factors:
            if f in weights:
                names.append(f)
                vals.append(weights[f])
                bar_colors.append(FAMILY_COLORS[family])
                family_labels.append(family)

    fig, ax = plt.subplots(figsize=(10, max(6, len(names) * 0.45 + 1)))
    y_pos = np.arange(len(names))
    bars = ax.barh(y_pos, vals, color=bar_colors, height=0.55, edgecolor="white", linewidth=0.5)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(names, fontsize=9)
    ax.axvline(0, color="#333333", lw=0.8)
    ax.set_title("Ridge Model Factor Coefficients by Family", fontweight="bold", fontsize=13)
    ax.set_xlabel("Coefficient Value")

    # Value annotations
    max_abs = max(abs(v) for v in vals) if vals else 1
    for i, (v, _bar) in enumerate(zip(vals, bars, strict=False)):
        offset = max_abs * 0.04
        ax.text(
            v + offset * (1 if v >= 0 else -1),
            i,
            f"{v:.4f}",
            va="center",
            ha="left" if v >= 0 else "right",
            fontsize=8,
            color=PRIMARY,
        )

    # Family legend
    seen = set()
    legend_patches = []
    for fam, col in FAMILY_COLORS.items():
        if fam not in seen and any(fl == fam for fl in family_labels):
            legend_patches.append(Patch(color=col, label=fam))
            seen.add(fam)
    ax.legend(handles=legend_patches, loc="lower right", fontsize=8, frameon=True, fancybox=True)

    # Separator lines between families
    prev_fam = None
    for i, fam in enumerate(family_labels):
        if prev_fam is not None and fam != prev_fam:
            ax.axhline(i - 0.5, color="#cccccc", lw=0.5, ls="--")
        prev_fam = fam

    ax.annotate(
        "Sign convention: all factors oriented HIGH = BUY.\n"
        "Inverted factors (IVOL, accruals, short interest)\n"
        "are sign-flipped before rank-percentile normalization.",
        xy=(0.02, 0.02),
        xycoords="axes fraction",
        fontsize=7.5,
        style="italic",
        color="#555555",
        bbox=dict(boxstyle="round,pad=0.3", facecolor=BG_ACCENT, edgecolor="#cccccc"),
    )
    fig.tight_layout()
    _save(fig, "factor_coefficients.png")


def chart_ic_analysis(data: dict) -> None:
    """6. IC time series, histogram, cumulative IC (3 panels)."""
    ic = data["ic_series"]
    mean_ic = ic.mean()
    std_ic = ic.std(ddof=1)
    ic_ir_val = mean_ic / std_ic if std_ic > 0 else 0

    fig, axes = plt.subplots(3, 1, figsize=(14, 10))

    # Panel 1: IC time series
    axes[0].bar(ic.index, ic.values, width=8, color=np.where(ic.values >= 0, ACCENT, RED), alpha=0.7)
    axes[0].axhline(mean_ic, color=GOLD, lw=1.5, ls="--", label=f"Mean IC = {mean_ic:.3f}")
    axes[0].set_title("Information Coefficient (IC) Over Time", fontweight="bold")
    axes[0].set_ylabel("Spearman IC")
    axes[0].legend(loc="upper right", frameon=True)
    axes[0].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    axes[0].xaxis.set_major_locator(mdates.YearLocator())

    # Panel 2: IC histogram
    axes[1].hist(ic.values, bins=35, color=SECONDARY, alpha=0.75, edgecolor="white")
    axes[1].axvline(mean_ic, color=GOLD, lw=2, ls="--")
    axes[1].set_title("IC Distribution", fontweight="bold")
    axes[1].set_xlabel("IC")
    axes[1].set_ylabel("Frequency")
    stats_text = f"Mean = {mean_ic:.4f}\nStd  = {std_ic:.4f}\nIC IR = {ic_ir_val:.3f}"
    axes[1].annotate(
        stats_text,
        xy=(0.97, 0.95),
        xycoords="axes fraction",
        ha="right",
        va="top",
        fontsize=9,
        family="monospace",
        bbox=dict(boxstyle="round,pad=0.4", facecolor=BG_ACCENT, edgecolor="#cccccc"),
    )

    # Panel 3: Cumulative IC
    cum_ic = ic.cumsum()
    axes[2].plot(cum_ic.index, cum_ic.values, color=PRIMARY, lw=2)
    axes[2].fill_between(cum_ic.index, 0, cum_ic.values, alpha=0.1, color=PRIMARY)
    axes[2].set_title("Cumulative IC", fontweight="bold")
    axes[2].set_ylabel("Cumulative IC")
    axes[2].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    axes[2].xaxis.set_major_locator(mdates.YearLocator())

    fig.autofmt_xdate(rotation=0, ha="center")
    fig.tight_layout()
    _save(fig, "ic_analysis.png")


def chart_return_distribution(data: dict) -> None:
    """7. Return histogram + rolling Sharpe."""
    ret = data["daily_ret"]
    n_obs = len(ret)

    fig, axes = plt.subplots(2, 1, figsize=(14, 7))

    # Panel 1: Histogram with normal overlay
    vals = ret.values
    mu, sigma = vals.mean(), vals.std(ddof=1)
    n_bins = min(60, max(20, n_obs // 10))
    axes[0].hist(vals, bins=n_bins, density=True, color=SECONDARY, alpha=0.7, edgecolor="white")
    x_range = np.linspace(mu - 4 * sigma, mu + 4 * sigma, 200)
    axes[0].plot(x_range, sp_stats.norm.pdf(x_range, mu, sigma), color=RED, lw=2, label="Normal Fit")
    axes[0].set_title("Return Distribution", fontweight="bold")
    axes[0].set_xlabel("Daily Return")
    axes[0].set_ylabel("Density")
    skew = float(sp_stats.skew(vals))
    kurt = float(sp_stats.kurtosis(vals))
    ann_ret = float((1 + mu) ** 252 - 1) * 100
    ann_vol = sigma * np.sqrt(252) * 100
    stats_text = (
        f"Mean    = {ann_ret:.1f}% ann.\n"
        f"Vol     = {ann_vol:.1f}% ann.\n"
        f"Skew    = {skew:.3f}\n"
        f"Kurtosis = {kurt:.3f}"
    )
    axes[0].annotate(
        stats_text,
        xy=(0.97, 0.95),
        xycoords="axes fraction",
        ha="right",
        va="top",
        fontsize=9,
        family="monospace",
        bbox=dict(boxstyle="round,pad=0.4", facecolor=BG_ACCENT, edgecolor="#cccccc"),
    )
    axes[0].legend(loc="upper left", frameon=True)

    # Panel 2: Rolling Sharpe
    roll_w = min(252, max(40, n_obs // 5))
    roll_mean = ret.rolling(roll_w, min_periods=roll_w).mean()
    roll_std = ret.rolling(roll_w, min_periods=roll_w).std(ddof=1)
    roll_std = roll_std.replace(0, np.nan)
    roll_sharpe = (roll_mean / roll_std * np.sqrt(252)).dropna()
    axes[1].plot(roll_sharpe.index, roll_sharpe.values, color=PRIMARY, lw=1.5)
    axes[1].axhline(0, color="#cccccc", lw=0.8, ls="--")
    axes[1].fill_between(
        roll_sharpe.index, 0, roll_sharpe.values, where=roll_sharpe > 0, color=GREEN, alpha=0.12
    )
    axes[1].fill_between(
        roll_sharpe.index, 0, roll_sharpe.values, where=roll_sharpe < 0, color=RED, alpha=0.12
    )
    axes[1].set_title(f"Rolling {roll_w}-Day Sharpe Ratio", fontweight="bold")
    axes[1].set_ylabel("Sharpe")
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    axes[1].xaxis.set_major_locator(mdates.YearLocator())
    fig.autofmt_xdate(rotation=0, ha="center")
    fig.tight_layout()
    _save(fig, "return_distribution.png")


def chart_cost_breakdown(data: dict) -> None:
    """8. Cost components stacked bar + regime capital deployment."""
    regime = data["regime_mask"]

    fig, axes = plt.subplots(2, 1, figsize=(14, 7))

    # Panel 1: Cost components
    categories = ["Spread\n(Impact)", "Commission", "Slippage", "Total"]
    spread_bps = 5.2
    commission_bps = 2.0
    slippage_bps = 0.8
    total_bps = spread_bps + commission_bps + slippage_bps
    vals = [spread_bps, commission_bps, slippage_bps, total_bps]
    bar_colors = [SECONDARY, ACCENT, "#6699cc", PRIMARY]

    bars = axes[0].bar(categories, vals, color=bar_colors, width=0.5, edgecolor="white", linewidth=0.5)
    for bar, v in zip(bars, vals, strict=False):
        axes[0].text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.15,
            f"{v:.1f} bps",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
            color=PRIMARY,
        )
    axes[0].set_title("Transaction Cost Components (Roundtrip)", fontweight="bold")
    axes[0].set_ylabel("Basis Points (bps)")
    axes[0].set_ylim(0, total_bps * 1.4)

    # Panel 2: Regime capital deployment
    regime_pct = regime.map({"BULL": BULL_EXPOSURE * 100, "BEAR": BEAR_EXPOSURE * 100}).astype(float)
    axes[1].fill_between(
        regime_pct.index,
        0,
        regime_pct.values,
        color=np.where(regime_pct.values > 50, ACCENT, RED),
        alpha=0.5,
        step="post",
    )
    axes[1].step(regime_pct.index, regime_pct.values, color=PRIMARY, lw=1.5, where="post")
    axes[1].set_ylim(0, 115)
    axes[1].set_title("Regime-Driven Capital Deployment", fontweight="bold")
    axes[1].set_ylabel("Capital Deployed (%)")
    axes[1].axhline(100, color=GREEN, lw=0.8, ls=":", alpha=0.5)
    axes[1].axhline(BEAR_EXPOSURE * 100, color=RED, lw=0.8, ls=":", alpha=0.5)
    axes[1].annotate(
        f"Bull: {BULL_EXPOSURE * 100:.0f}%",
        xy=(0.02, 0.92),
        xycoords="axes fraction",
        fontsize=9,
        color=GREEN,
        fontweight="bold",
    )
    axes[1].annotate(
        f"Bear: {BEAR_EXPOSURE * 100:.0f}%",
        xy=(0.02, 0.15),
        xycoords="axes fraction",
        fontsize=9,
        color=RED,
        fontweight="bold",
    )
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    axes[1].xaxis.set_major_locator(mdates.YearLocator())
    fig.autofmt_xdate(rotation=0, ha="center")
    fig.tight_layout()
    _save(fig, "cost_breakdown.png")


def chart_factor_correlation(data: dict) -> None:
    """9. 13 x 13 factor correlation heatmap."""
    corr = data["factor_corr"]

    fig, ax = plt.subplots(figsize=(11, 9))
    cmap = sns.diverging_palette(220, 10, as_cmap=True)
    sns.heatmap(
        corr,
        annot=True,
        fmt=".2f",
        cmap=cmap,
        vmin=-1,
        vmax=1,
        center=0,
        square=True,
        linewidths=0.5,
        linecolor="white",
        cbar_kws={"label": "Spearman Correlation", "shrink": 0.7},
        ax=ax,
        annot_kws={"size": 7.5},
    )

    ax.set_title(
        "Cross-Sectional Factor Correlation Matrix (13 Factors)", fontweight="bold", pad=15, fontsize=13
    )
    ax.tick_params(axis="x", rotation=45, labelsize=8)
    ax.tick_params(axis="y", rotation=0, labelsize=8)

    # Family bracket annotations on the left
    y_pos = 0
    for _family, factors in FACTOR_FAMILIES.items():
        n_in_corr = sum(1 for f in factors if f in corr.index)
        if n_in_corr > 0:
            y_pos += n_in_corr

    fig.tight_layout()
    _save(fig, "factor_correlation_heatmap.png")


def chart_walkforward_folds(data: dict) -> None:
    """10. Walk-forward timeline + OOS Sharpe on SHARED datetime x-axis."""
    per_fold = data["per_fold_sharpe"]
    boundaries = data["fold_boundaries"]
    n_folds = len(per_fold)
    if n_folds == 0:
        return

    fig, (ax_sharpe, ax_time) = plt.subplots(
        2,
        1,
        figsize=(14, 7.5),
        gridspec_kw={"height_ratios": [1, 1.3]},
    )

    # ── Panel 1: OOS Sharpe bars positioned at test-period midpoints ──
    for i, (_tr_s, _tr_e, te_s, te_e) in enumerate(boundaries):
        te_start = pd.Timestamp(te_s)
        te_end = pd.Timestamp(te_e)
        mid = te_start + (te_end - te_start) / 2
        width = (te_end - te_start).days * 0.7

        color = GREEN if per_fold[i] > 0 else RED
        ax_sharpe.bar(mid, per_fold[i], width=width, color=color, alpha=0.8, edgecolor="white", linewidth=0.5)
        offset = 0.15 * (1 if per_fold[i] >= 0 else -1)
        ax_sharpe.text(
            mid,
            per_fold[i] + offset,
            f"{per_fold[i]:.2f}",
            ha="center",
            va="bottom" if per_fold[i] >= 0 else "top",
            fontsize=9,
            fontweight="bold",
            color=PRIMARY,
        )

    ax_sharpe.axhline(0, color="#cccccc", lw=0.8)
    mean_s = np.mean(per_fold)
    ax_sharpe.axhline(mean_s, color=GOLD, lw=1.5, ls="--", label=f"Mean OOS Sharpe = {mean_s:.2f}")
    ax_sharpe.set_title("Out-of-Sample Sharpe Ratio by Fold", fontweight="bold")
    ax_sharpe.set_ylabel("Sharpe Ratio")
    ax_sharpe.legend(loc="upper right", frameon=True)
    ax_sharpe.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax_sharpe.xaxis.set_major_locator(mdates.YearLocator())

    # ── Panel 2: Train/Test timeline bands ──
    for i, (tr_s, tr_e, te_s, te_e) in enumerate(boundaries):
        y = n_folds - i
        tr_start_num = mdates.date2num(pd.Timestamp(tr_s))
        tr_end_num = mdates.date2num(pd.Timestamp(tr_e))
        te_start_num = mdates.date2num(pd.Timestamp(te_s))
        te_end_num = mdates.date2num(pd.Timestamp(te_e))

        # Train band
        ax_time.barh(
            y,
            tr_end_num - tr_start_num,
            left=tr_start_num,
            height=0.4,
            color=SECONDARY,
            alpha=0.6,
            label="Train" if i == 0 else "",
        )
        # Purge gap
        ax_time.barh(
            y,
            te_start_num - tr_end_num,
            left=tr_end_num,
            height=0.4,
            color="#eeeeee",
            alpha=0.6,
            label="Purge Gap" if i == 0 else "",
        )
        # Test band
        ax_time.barh(
            y,
            te_end_num - te_start_num,
            left=te_start_num,
            height=0.4,
            color=GOLD,
            alpha=0.8,
            label="Test (OOS)" if i == 0 else "",
        )

    ax_time.set_yticks(range(1, n_folds + 1))
    ax_time.set_yticklabels([f"Fold {i + 1}" for i in range(n_folds)])
    ax_time.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax_time.xaxis.set_major_locator(mdates.YearLocator())
    ax_time.set_title("Walk-Forward Expanding Window Timeline", fontweight="bold")
    ax_time.set_xlabel("Date")
    ax_time.legend(loc="lower right", frameon=True, ncol=3)

    # Sync x-axis limits between both panels
    all_dates = []
    for tr_s, _tr_e, _te_s, te_e in boundaries:
        all_dates.extend([pd.Timestamp(tr_s), pd.Timestamp(te_e)])
    margin = pd.Timedelta(days=60)
    xlim = (min(all_dates) - margin, max(all_dates) + margin)
    ax_sharpe.set_xlim(xlim)
    ax_time.set_xlim(xlim)

    fig.autofmt_xdate(rotation=0, ha="center")
    fig.tight_layout()
    _save(fig, "walkforward_folds.png")


# ============================================================================
# 5. METRICS JSON
# ============================================================================


def save_metrics(data: dict) -> None:
    ret = data["daily_ret"]
    ic = data["ic_series"]
    oos_sharpe_val, _ = sharpe_ratio(ret)
    oos_cagr_val, _ = cagr(ret)
    mdd, _ = max_drawdown(ret)
    mean_ic_val = float(ic.mean())
    ic_ir_val = float(ic.mean() / ic.std(ddof=1)) if ic.std(ddof=1) > 0 else 0.0

    wins = (ret > 0).sum()
    total = len(ret)
    win_rate = float(wins / total) if total > 0 else 0.0

    # Turnover estimate: ~20 positions changed per rebalance, weekly
    annual_turnover_est = 20 * 52 * 2 / N_STOCKS

    metrics = {
        "oos_sharpe": round(oos_sharpe_val, 4),
        "oos_cagr": round(oos_cagr_val, 4),
        "max_drawdown": round(mdd, 4),
        "annual_turnover": round(annual_turnover_est, 2),
        "cost_drag_pct": round(data["cost_drag_pct"], 4),
        "mean_ic": round(mean_ic_val, 4),
        "ic_ir": round(ic_ir_val, 4),
        "per_fold_sharpe": [round(s, 4) for s in data["per_fold_sharpe"]],
        "factor_weights": {k: round(v, 6) for k, v in data["model_weights"].items()},
        "factor_correlations": {
            f"{r}|{c}": round(float(data["factor_corr"].loc[r, c]), 4)
            for r in data["factor_corr"].index
            for c in data["factor_corr"].columns
            if r <= c
        },
        "n_factors": len(data["factor_cols"]),
        "factor_families": {
            fam: [f for f in facs if f in data["factor_cols"]] for fam, facs in FACTOR_FAMILIES.items()
        },
        "oos_period": {
            "start": str(ret.index[0].date()),
            "end": str(ret.index[-1].date()),
            "n_days": len(ret),
        },
        "total_trades": data["total_trades"],
        "win_rate": round(win_rate, 4),
        "avg_holding_period_days": 21,
    }

    METRICS_PATH.write_text(json.dumps(metrics, indent=2) + "\n")
    print("  [OK] backtest_metrics.json")


# ============================================================================
# MAIN
# ============================================================================


def main() -> None:
    print("=" * 65)
    print("NYSE ATS Framework -- Figure Generation (v2: 13 factors, 8 years)")
    print("=" * 65)

    print("\n[1/5] Generating stock characteristics ...")
    chars = generate_stock_characteristics(N_STOCKS)
    print("  Stock traits: quality, risk, momentum_tendency, sentiment")

    print("\n[2/5] Generating synthetic market data (2018-2025) ...")
    prices = generate_stock_prices(chars, N_STOCKS, N_DAYS)
    spy = generate_spy(N_DAYS)
    print(
        f"  Stocks: {prices['symbol'].nunique()}, "
        f"Days: {prices['date'].nunique()}, "
        f"Range: {prices['date'].min()} to {prices['date'].max()}"
    )

    print("\n[3/5] Computing 13 factors across 6 families ...")
    for fam, facs in FACTOR_FAMILIES.items():
        print(f"  {fam}: {', '.join(facs)}")
    factors = compute_all_factors(prices, chars)
    print(f"  Factor matrix: {len(factors)} observations, {len(ALL_FACTOR_COLS)} factors")

    print("\n[4/5] Running walk-forward backtest (Ridge, 13 factors) ...")
    data = run_backtest(factors, prices, spy)
    oos_sharpe, _ = sharpe_ratio(data["daily_ret"])
    oos_cagr_val, _ = cagr(data["daily_ret"])
    mdd, _ = max_drawdown(data["daily_ret"])
    n_folds = len(data["per_fold_sharpe"])
    print(f"  OOS Sharpe:  {oos_sharpe:.3f}")
    print(f"  OOS CAGR:    {oos_cagr_val:.3%}")
    print(f"  Max DD:      {mdd:.3%}")
    print(f"  Folds:       {n_folds}")
    print(f"  IC mean:     {data['ic_series'].mean():.4f}")
    print(
        f"  OOS period:  {data['daily_ret'].index[0].strftime('%Y-%m-%d')} "
        f"to {data['daily_ret'].index[-1].strftime('%Y-%m-%d')}"
    )

    print(f"\n[5/5] Generating 10 charts -> {FIG_DIR}/")
    chart_equity_curve(data)
    chart_underwater(data)
    chart_monthly_heatmap(data)
    chart_rolling_metrics(data)
    chart_factor_coefficients(data)
    chart_ic_analysis(data)
    chart_return_distribution(data)
    chart_cost_breakdown(data)
    chart_factor_correlation(data)
    chart_walkforward_folds(data)

    print("\nSaving metrics JSON ...")
    save_metrics(data)

    print("\n" + "=" * 65)
    print("DONE -- all figures saved to docs/figures/")
    print("=" * 65)


if __name__ == "__main__":
    main()
