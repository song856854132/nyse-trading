"""Unit tests for the factor screening pipeline (G0-G5)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from nyse_core.contracts import GateVerdict
from nyse_core.factor_screening import (
    compute_long_short_returns,
    compute_long_short_weights,
    compute_volatility_scaled_weights,
    screen_factor,
)


def _make_vol_panel(
    factor_scores: pd.DataFrame,
    base_vol: float = 0.02,
    vol_heterogeneity: float = 0.0,
    seed: int = 99,
) -> pd.DataFrame:
    """Build a per-(date, symbol) vol panel matching factor_scores' index.

    If ``vol_heterogeneity`` is 0, every symbol has vol=base_vol (homogeneous).
    Otherwise each symbol gets a symbol-level multiplier drawn uniformly from
    [1 - vol_heterogeneity, 1 + vol_heterogeneity] so vols differ.
    """
    rng = np.random.default_rng(seed)
    unique_syms = sorted(factor_scores["symbol"].unique())
    if vol_heterogeneity > 0:
        mults = {s: float(rng.uniform(1.0 - vol_heterogeneity, 1.0 + vol_heterogeneity)) for s in unique_syms}
    else:
        mults = dict.fromkeys(unique_syms, 1.0)
    records = [
        {"date": row.date, "symbol": row.symbol, "vol": base_vol * mults[row.symbol]}
        for row in factor_scores.itertuples(index=False)
    ]
    return pd.DataFrame(records)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_factor_data(
    n_dates: int = 60,
    n_stocks: int = 100,
    signal_strength: float = 0.0,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate synthetic factor scores and forward returns.

    Parameters
    ----------
    n_dates : int
        Number of rebalance dates.
    n_stocks : int
        Stocks per date.
    signal_strength : float
        0.0 = pure noise, >0 = score explains some return variance.
    seed : int
        RNG seed for determinism.

    Returns
    -------
    (factor_scores, forward_returns) DataFrames.
    """
    rng = np.random.default_rng(seed)
    dates = pd.biz_day_range("2020-01-01", periods=n_dates, freq="5B")
    symbols = [f"SYM{i:03d}" for i in range(n_stocks)]

    records_scores = []
    records_rets = []

    for dt in dates:
        scores = rng.standard_normal(n_stocks)
        noise = rng.standard_normal(n_stocks) * 0.02
        returns = signal_strength * scores * 0.02 + noise

        for i, sym in enumerate(symbols):
            records_scores.append({"date": dt, "symbol": sym, "score": scores[i]})
            records_rets.append({"date": dt, "symbol": sym, "fwd_ret_5d": returns[i]})

    return pd.DataFrame(records_scores), pd.DataFrame(records_rets)


def _make_strong_signal(
    n_dates: int = 80,
    n_stocks: int = 100,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate a factor with strong monotonic signal."""
    rng = np.random.default_rng(seed)
    dates = pd.biz_day_range("2020-01-01", periods=n_dates, freq="5B")
    symbols = [f"SYM{i:03d}" for i in range(n_stocks)]

    records_scores = []
    records_rets = []

    for dt in dates:
        scores = rng.standard_normal(n_stocks)
        # Strong signal: returns strongly correlated with scores
        noise = rng.standard_normal(n_stocks) * 0.005
        returns = 0.5 * scores * 0.03 + 0.003 + noise

        for i, sym in enumerate(symbols):
            records_scores.append({"date": dt, "symbol": sym, "score": scores[i]})
            records_rets.append({"date": dt, "symbol": sym, "fwd_ret_5d": returns[i]})

    return pd.DataFrame(records_scores), pd.DataFrame(records_rets)


# Helper to generate business day ranges (pd doesn't expose biz_day_range)
def _biz_days(start: str, n: int) -> list:
    """Generate n business-day-spaced timestamps."""
    return pd.bdate_range(start, periods=n, freq="B").tolist()


# Patch the helper above into _make_factor_data and _make_strong_signal
def _make_factor_data_v2(
    n_dates: int = 60,
    n_stocks: int = 100,
    signal_strength: float = 0.0,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=n_dates, freq="5B")
    symbols = [f"SYM{i:03d}" for i in range(n_stocks)]

    records_scores = []
    records_rets = []

    for dt in dates:
        scores = rng.standard_normal(n_stocks)
        noise = rng.standard_normal(n_stocks) * 0.02
        returns = signal_strength * scores * 0.02 + noise

        for i, sym in enumerate(symbols):
            records_scores.append({"date": dt, "symbol": sym, "score": scores[i]})
            records_rets.append({"date": dt, "symbol": sym, "fwd_ret_5d": returns[i]})

    return pd.DataFrame(records_scores), pd.DataFrame(records_rets)


def _make_strong_signal_v2(
    n_dates: int = 80,
    n_stocks: int = 100,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=n_dates, freq="5B")
    symbols = [f"SYM{i:03d}" for i in range(n_stocks)]

    records_scores = []
    records_rets = []

    for dt in dates:
        scores = rng.standard_normal(n_stocks)
        noise = rng.standard_normal(n_stocks) * 0.005
        returns = 0.5 * scores * 0.03 + 0.003 + noise

        for i, sym in enumerate(symbols):
            records_scores.append({"date": dt, "symbol": sym, "score": scores[i]})
            records_rets.append({"date": dt, "symbol": sym, "fwd_ret_5d": returns[i]})

    return pd.DataFrame(records_scores), pd.DataFrame(records_rets)


# ── Tests ────────────────────────────────────────────────────────────────────


class TestScreenFactorAllGatesPass:
    """Strong synthetic signal should pass all G0-G5 gates."""

    def test_screen_factor_all_gates_pass(self):
        factor_scores, forward_returns = _make_strong_signal_v2(n_dates=80, n_stocks=100, seed=42)
        verdict, metrics, diag = screen_factor(
            factor_name="strong_momentum",
            factor_scores=factor_scores,
            forward_returns=forward_returns,
            existing_factors=None,
        )
        assert isinstance(verdict, GateVerdict)
        assert verdict.passed_all is True, (
            f"Expected all gates to pass. Results: {verdict.gate_results}, Metrics: {metrics}"
        )
        assert not diag.has_errors


class TestScreenFactorWeakSignalFails:
    """Random noise should fail at least one gate (likely G1 permutation)."""

    def test_screen_factor_weak_signal_fails(self):
        factor_scores, forward_returns = _make_factor_data_v2(
            n_dates=60, n_stocks=100, signal_strength=0.0, seed=42
        )
        verdict, metrics, diag = screen_factor(
            factor_name="noise_factor",
            factor_scores=factor_scores,
            forward_returns=forward_returns,
            existing_factors=None,
        )
        assert isinstance(verdict, GateVerdict)
        # A pure noise factor should fail at least one gate
        assert verdict.passed_all is False, (
            f"Pure noise should fail. Results: {verdict.gate_results}, Metrics: {metrics}"
        )


class TestLongShortReturns:
    """Tests for the compute_long_short_returns helper."""

    def test_long_short_returns_shape(self):
        factor_scores, forward_returns = _make_factor_data_v2(
            n_dates=20, n_stocks=50, signal_strength=0.1, seed=42
        )
        ls_ret, diag = compute_long_short_returns(factor_scores, forward_returns)
        assert isinstance(ls_ret, pd.Series)
        # Should have at most n_dates entries
        assert len(ls_ret) <= 20
        assert len(ls_ret) > 0
        assert not diag.has_errors

    def test_long_short_top_quintile_positive(self):
        """With a planted monotonic signal, long-short returns should be positive on average."""
        factor_scores, forward_returns = _make_strong_signal_v2(n_dates=60, n_stocks=100, seed=42)
        ls_ret, diag = compute_long_short_returns(factor_scores, forward_returns)
        assert ls_ret.mean() > 0, (
            f"Expected positive mean LS return with strong signal, got {ls_ret.mean():.6f}"
        )


class TestLongShortWeights:
    """Tests for the compute_long_short_weights helper (iter-3 Brinson input).

    The weights mirror the quintile construction of compute_long_short_returns
    but expose per-(date, symbol) rows so downstream Brinson attribution and
    characteristic-matched benchmarks can consume them directly.
    """

    def test_shape_and_columns(self) -> None:
        factor_scores, _ = _make_factor_data_v2(n_dates=10, n_stocks=50, seed=0)
        weights, diag = compute_long_short_weights(factor_scores)
        assert isinstance(weights, pd.DataFrame)
        assert list(weights.columns) == ["date", "symbol", "weight"]
        assert not diag.has_errors

    def test_dollar_neutral_per_date(self) -> None:
        """Sum of longs must be +1 and sum of shorts must be -1 per date."""
        factor_scores, _ = _make_factor_data_v2(n_dates=20, n_stocks=100, seed=1)
        weights, _ = compute_long_short_weights(factor_scores)
        per_date = weights.groupby("date")["weight"].agg(
            long_sum=lambda s: s[s > 0].sum(),
            short_sum=lambda s: s[s < 0].sum(),
        )
        # Per-date gross longs sum to +1, gross shorts sum to -1.
        assert np.allclose(per_date["long_sum"], 1.0, atol=1e-12)
        assert np.allclose(per_date["short_sum"], -1.0, atol=1e-12)

    def test_equal_weights_within_leg(self) -> None:
        """Within the long leg all weights are equal, ditto short leg."""
        factor_scores, _ = _make_factor_data_v2(n_dates=5, n_stocks=50, seed=2)
        weights, _ = compute_long_short_weights(factor_scores)
        for _dt, grp in weights.groupby("date"):
            longs = grp.loc[grp["weight"] > 0, "weight"].unique()
            shorts = grp.loc[grp["weight"] < 0, "weight"].unique()
            assert len(longs) == 1, f"longs not uniform: {longs}"
            assert len(shorts) == 1, f"shorts not uniform: {shorts}"

    def test_long_symbols_have_higher_scores(self) -> None:
        """The long leg (positive weights) must correspond to top-quintile scores."""
        factor_scores, _ = _make_factor_data_v2(n_dates=5, n_stocks=100, seed=3)
        weights, _ = compute_long_short_weights(factor_scores)
        merged = pd.merge(weights, factor_scores, on=["date", "symbol"])
        for _dt, grp in merged.groupby("date"):
            long_scores = grp.loc[grp["weight"] > 0, "score"]
            short_scores = grp.loc[grp["weight"] < 0, "score"]
            assert long_scores.min() > short_scores.max()

    def test_nan_scores_excluded(self) -> None:
        """NaN scores must not appear in the output weights."""
        factor_scores, _ = _make_factor_data_v2(n_dates=3, n_stocks=50, seed=4)
        # Poison a handful of scores
        factor_scores.loc[::10, "score"] = np.nan
        weights, _ = compute_long_short_weights(factor_scores)
        poisoned = factor_scores.loc[factor_scores["score"].isna(), ["date", "symbol"]]
        merged = pd.merge(weights, poisoned, on=["date", "symbol"], how="inner")
        assert merged.empty, "NaN-scored rows must not receive weights"

    def test_empty_input_returns_empty_frame(self) -> None:
        weights, diag = compute_long_short_weights(pd.DataFrame(columns=["date", "symbol", "score"]))
        assert weights.empty
        assert list(weights.columns) == ["date", "symbol", "weight"]
        assert any("Empty factor_scores" in m.message for m in diag.messages)

    def test_insufficient_stocks_per_date_skipped(self) -> None:
        """A date with fewer than n_quantiles stocks must be dropped, not raise."""
        factor_scores = pd.DataFrame(
            {
                "date": [pd.Timestamp("2020-01-03")] * 3 + [pd.Timestamp("2020-01-10")] * 50,
                "symbol": [f"S{i}" for i in range(3)] + [f"T{i}" for i in range(50)],
                "score": list(range(3)) + list(range(50)),
            }
        )
        weights, diag = compute_long_short_weights(factor_scores, n_quantiles=5)
        # Only the 50-stock date should appear in the output.
        assert set(weights["date"].unique()) == {pd.Timestamp("2020-01-10")}
        assert any(
            "insufficient quantile spread" in m.message or "Skipped" in m.message for m in diag.messages
        )


class TestVolatilityScaledWeights:
    """Tests for compute_volatility_scaled_weights (iter-5 Wave-2 diagnostic).

    The helper mirrors compute_long_short_weights quintile construction (same
    pd.qcut with duplicates="drop") but replaces equal-within-leg weighting
    with inverse-vol weighting:  w_i = sign * (1/vol_i) / sum(1/vol).
    Iron rules: diagnostic only, no gate change, no sign-convention change.
    """

    def test_shape_and_columns(self) -> None:
        factor_scores, _ = _make_factor_data_v2(n_dates=10, n_stocks=50, seed=0)
        vol_panel = _make_vol_panel(factor_scores, vol_heterogeneity=0.5, seed=10)
        weights, diag = compute_volatility_scaled_weights(factor_scores, vol_panel)
        assert isinstance(weights, pd.DataFrame)
        assert list(weights.columns) == ["date", "symbol", "weight"]
        assert not diag.has_errors

    def test_dollar_neutral_per_leg_per_date(self) -> None:
        """Long leg sums to +1, short leg sums to -1, per date."""
        factor_scores, _ = _make_factor_data_v2(n_dates=20, n_stocks=100, seed=1)
        vol_panel = _make_vol_panel(factor_scores, vol_heterogeneity=0.7, seed=11)
        weights, _ = compute_volatility_scaled_weights(factor_scores, vol_panel)
        per_date = weights.groupby("date")["weight"].agg(
            long_sum=lambda s: s[s > 0].sum(),
            short_sum=lambda s: s[s < 0].sum(),
        )
        assert np.allclose(per_date["long_sum"], 1.0, atol=1e-12)
        assert np.allclose(per_date["short_sum"], -1.0, atol=1e-12)

    def test_weights_inverse_proportional_to_vol(self) -> None:
        """Within each leg, weight ratio must equal inverse-vol ratio."""
        factor_scores, _ = _make_factor_data_v2(n_dates=5, n_stocks=50, seed=2)
        vol_panel = _make_vol_panel(factor_scores, vol_heterogeneity=0.6, seed=12)
        weights, _ = compute_volatility_scaled_weights(factor_scores, vol_panel)
        merged = weights.merge(vol_panel, on=["date", "symbol"])
        for _dt, grp in merged.groupby("date"):
            for sign_filter in (grp["weight"] > 0, grp["weight"] < 0):
                leg = grp.loc[sign_filter]
                if len(leg) < 2:
                    continue
                expected = (1.0 / leg["vol"]) / (1.0 / leg["vol"]).sum()
                got = leg["weight"].abs().to_numpy()
                np.testing.assert_allclose(got, expected.to_numpy(), atol=1e-12)

    def test_reduces_to_equal_weight_when_vols_equal(self) -> None:
        """When all vols are identical, vol-scaling degenerates to equal weight."""
        factor_scores, _ = _make_factor_data_v2(n_dates=5, n_stocks=50, seed=3)
        vol_panel = _make_vol_panel(factor_scores, vol_heterogeneity=0.0, seed=13)
        vol_weights, _ = compute_volatility_scaled_weights(factor_scores, vol_panel)
        eq_weights, _ = compute_long_short_weights(factor_scores)
        merged = vol_weights.merge(eq_weights, on=["date", "symbol"], suffixes=("_vol", "_eq"))
        np.testing.assert_allclose(
            merged["weight_vol"].to_numpy(), merged["weight_eq"].to_numpy(), atol=1e-12
        )

    def test_long_symbols_have_higher_scores(self) -> None:
        """Top-quintile still gets positive weights even with vol scaling."""
        factor_scores, _ = _make_factor_data_v2(n_dates=5, n_stocks=100, seed=4)
        vol_panel = _make_vol_panel(factor_scores, vol_heterogeneity=0.5, seed=14)
        weights, _ = compute_volatility_scaled_weights(factor_scores, vol_panel)
        merged = weights.merge(factor_scores, on=["date", "symbol"])
        for _dt, grp in merged.groupby("date"):
            long_scores = grp.loc[grp["weight"] > 0, "score"]
            short_scores = grp.loc[grp["weight"] < 0, "score"]
            assert long_scores.min() > short_scores.max()

    def test_nan_vol_excluded(self) -> None:
        """Symbols with NaN vol must be dropped; remaining weights still sum to 1."""
        factor_scores, _ = _make_factor_data_v2(n_dates=3, n_stocks=50, seed=5)
        vol_panel = _make_vol_panel(factor_scores, vol_heterogeneity=0.4, seed=15)
        vol_panel.loc[::7, "vol"] = np.nan
        weights, diag = compute_volatility_scaled_weights(factor_scores, vol_panel)
        poisoned = vol_panel.loc[vol_panel["vol"].isna(), ["date", "symbol"]]
        bad = pd.merge(weights, poisoned, on=["date", "symbol"], how="inner")
        assert bad.empty, "NaN-vol rows must not receive weights"
        assert any("NaN vol" in m.message for m in diag.messages)

    def test_zero_vol_excluded(self) -> None:
        """Symbols with vol <= 0 must be dropped."""
        factor_scores, _ = _make_factor_data_v2(n_dates=3, n_stocks=50, seed=6)
        vol_panel = _make_vol_panel(factor_scores, vol_heterogeneity=0.2, seed=16)
        vol_panel.loc[::11, "vol"] = 0.0
        weights, diag = compute_volatility_scaled_weights(factor_scores, vol_panel)
        bad_keys = vol_panel.loc[vol_panel["vol"] <= 0, ["date", "symbol"]]
        bad = pd.merge(weights, bad_keys, on=["date", "symbol"], how="inner")
        assert bad.empty
        assert any("zero vol" in m.message for m in diag.messages)

    def test_leg_with_no_valid_vol_is_skipped(self) -> None:
        """If the entire long leg has NaN vol on a date, only the short leg emits."""
        factor_scores, _ = _make_factor_data_v2(n_dates=2, n_stocks=50, seed=7)
        vol_panel = _make_vol_panel(factor_scores, vol_heterogeneity=0.0, seed=17)
        target_date = factor_scores["date"].iloc[0]
        day_scores = factor_scores[factor_scores["date"] == target_date].copy()
        day_scores["q"] = pd.qcut(day_scores["score"], q=5, labels=False, duplicates="drop")
        top_syms = day_scores.loc[day_scores["q"] == day_scores["q"].max(), "symbol"]
        mask = (vol_panel["date"] == target_date) & (vol_panel["symbol"].isin(top_syms))
        vol_panel.loc[mask, "vol"] = np.nan
        weights, diag = compute_volatility_scaled_weights(factor_scores, vol_panel)
        emitted_long = weights[(weights["date"] == target_date) & (weights["weight"] > 0)]
        assert emitted_long.empty, "Long leg should not emit when all vols are NaN"
        emitted_short = weights[(weights["date"] == target_date) & (weights["weight"] < 0)]
        assert not emitted_short.empty, "Short leg should still emit on that date"
        assert any("no valid vols" in m.message for m in diag.messages)

    def test_empty_factor_scores_returns_empty(self) -> None:
        weights, diag = compute_volatility_scaled_weights(
            pd.DataFrame(columns=["date", "symbol", "score"]),
            pd.DataFrame({"date": [], "symbol": [], "vol": []}),
        )
        assert weights.empty
        assert list(weights.columns) == ["date", "symbol", "weight"]
        assert any("Empty factor_scores" in m.message for m in diag.messages)

    def test_empty_vol_panel_returns_empty(self) -> None:
        factor_scores, _ = _make_factor_data_v2(n_dates=3, n_stocks=50, seed=8)
        weights, diag = compute_volatility_scaled_weights(
            factor_scores, pd.DataFrame(columns=["date", "symbol", "vol"])
        )
        assert weights.empty
        assert any("Empty vol_panel" in m.message for m in diag.messages)

    def test_missing_vol_panel_columns_returns_empty(self) -> None:
        factor_scores, _ = _make_factor_data_v2(n_dates=3, n_stocks=50, seed=9)
        bad_panel = pd.DataFrame({"date": factor_scores["date"], "symbol": factor_scores["symbol"]})
        weights, diag = compute_volatility_scaled_weights(factor_scores, bad_panel)
        assert weights.empty
        assert any("missing columns" in m.message for m in diag.messages)

    def test_insufficient_stocks_per_date_skipped(self) -> None:
        """A date with fewer than n_quantiles rows must be dropped silently."""
        factor_scores = pd.DataFrame(
            {
                "date": [pd.Timestamp("2020-01-03")] * 3 + [pd.Timestamp("2020-01-10")] * 50,
                "symbol": [f"S{i}" for i in range(3)] + [f"T{i}" for i in range(50)],
                "score": list(range(3)) + list(range(50)),
            }
        )
        vol_panel = _make_vol_panel(factor_scores, vol_heterogeneity=0.3, seed=18)
        weights, _diag = compute_volatility_scaled_weights(factor_scores, vol_panel)
        assert set(weights["date"].unique()) == {pd.Timestamp("2020-01-10")}

    def test_no_unmapped_symbols_in_output(self) -> None:
        """Symbols absent from vol_panel on a date must be excluded from output."""
        factor_scores, _ = _make_factor_data_v2(n_dates=3, n_stocks=50, seed=20)
        vol_panel = _make_vol_panel(factor_scores, vol_heterogeneity=0.3, seed=21)
        drop_sym = factor_scores["symbol"].iloc[0]
        vol_panel = vol_panel[vol_panel["symbol"] != drop_sym].copy()
        weights, _diag = compute_volatility_scaled_weights(factor_scores, vol_panel)
        assert drop_sym not in weights["symbol"].unique()


class TestMissingMetricFailsGate:
    """If a required metric cannot be computed, the gate should fail."""

    def test_missing_metric_fails_gate(self):
        # Provide empty data so metrics degenerate
        factor_scores = pd.DataFrame(columns=["date", "symbol", "score"])
        forward_returns = pd.DataFrame(columns=["date", "symbol", "fwd_ret_5d"])

        verdict, metrics, diag = screen_factor(
            factor_name="empty_factor",
            factor_scores=factor_scores,
            forward_returns=forward_returns,
        )
        # With no data, OOS Sharpe = 0 (< 0.3 threshold) -> G0 fail
        assert verdict.passed_all is False


class TestG5MarginalAutoPassNoExisting:
    """G5 should auto-pass when no existing factors are provided."""

    def test_g5_marginal_auto_pass_no_existing(self):
        factor_scores, forward_returns = _make_strong_signal_v2(n_dates=80, n_stocks=100, seed=42)
        verdict, metrics, diag = screen_factor(
            factor_name="test_factor",
            factor_scores=factor_scores,
            forward_returns=forward_returns,
            existing_factors=None,  # No existing factors -> G5 auto-pass
        )
        # G5 should pass (auto-pass with sentinel = 1.0 > 0)
        assert verdict.gate_results.get("G5") is True, (
            f"G5 should auto-pass with no existing factors. "
            f"Results: {verdict.gate_results}, Metrics: {metrics}"
        )
