"""Unit tests for the factor screening pipeline (G0-G5)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from nyse_core.contracts import GateVerdict
from nyse_core.factor_screening import (
    compute_cap_tilted_weights,
    compute_ensemble_weights,
    compute_long_short_returns,
    compute_long_short_weights,
    compute_risk_parity_weights,
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


def _make_size_panel(
    factor_scores: pd.DataFrame,
    base_size: float = 1_000_000_000.0,
    size_heterogeneity: float = 0.0,
    seed: int = 123,
) -> pd.DataFrame:
    """Build a per-(date, symbol) market-cap panel matching factor_scores.

    If ``size_heterogeneity`` is 0, every symbol has size=base_size
    (homogeneous). Otherwise each symbol gets a symbol-level multiplier
    drawn uniformly from [1 - size_heterogeneity, 1 + size_heterogeneity].
    """
    rng = np.random.default_rng(seed)
    unique_syms = sorted(factor_scores["symbol"].unique())
    if size_heterogeneity > 0:
        mults = {
            s: float(rng.uniform(1.0 - size_heterogeneity, 1.0 + size_heterogeneity)) for s in unique_syms
        }
    else:
        mults = dict.fromkeys(unique_syms, 1.0)
    records = [
        {"date": row.date, "symbol": row.symbol, "size": base_size * mults[row.symbol]}
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


class TestCapTiltedWeights:
    """Tests for compute_cap_tilted_weights (iter-6 Wave-2 diagnostic).

    Mirrors compute_long_short_weights quintile construction (same
    pd.qcut with duplicates="drop"). Within each leg, weights are
    proportional to size**tilt_exponent. Iron rules: diagnostic only,
    no gate change, no sign-convention change.

    Degeneracies:
        * tilt_exponent = 0   → equal-weight (same as compute_long_short_weights)
        * tilt_exponent = 1   → pure cap-weight within leg
        * tilt_exponent = 0.5 → sqrt-cap tilt (default)
    """

    def test_shape_and_columns(self) -> None:
        factor_scores, _ = _make_factor_data_v2(n_dates=10, n_stocks=50, seed=0)
        size_panel = _make_size_panel(factor_scores, size_heterogeneity=0.5, seed=30)
        weights, diag = compute_cap_tilted_weights(factor_scores, size_panel)
        assert isinstance(weights, pd.DataFrame)
        assert list(weights.columns) == ["date", "symbol", "weight"]
        assert not diag.has_errors

    def test_dollar_neutral_per_leg_per_date(self) -> None:
        """Long leg sums to +1, short leg sums to -1, per date, for any tilt."""
        factor_scores, _ = _make_factor_data_v2(n_dates=20, n_stocks=100, seed=1)
        size_panel = _make_size_panel(factor_scores, size_heterogeneity=0.7, seed=31)
        for tilt in (0.0, 0.5, 1.0, 2.0):
            weights, _ = compute_cap_tilted_weights(factor_scores, size_panel, tilt_exponent=tilt)
            per_date = weights.groupby("date")["weight"].agg(
                long_sum=lambda s: s[s > 0].sum(),
                short_sum=lambda s: s[s < 0].sum(),
            )
            assert np.allclose(per_date["long_sum"], 1.0, atol=1e-12), (
                f"long leg not dollar-neutral at tilt={tilt}"
            )
            assert np.allclose(per_date["short_sum"], -1.0, atol=1e-12), (
                f"short leg not dollar-neutral at tilt={tilt}"
            )

    def test_weights_proportional_to_size_power_tilt(self) -> None:
        """Within each leg, weight ratio equals (size**tilt) ratio."""
        factor_scores, _ = _make_factor_data_v2(n_dates=5, n_stocks=50, seed=2)
        size_panel = _make_size_panel(factor_scores, size_heterogeneity=0.6, seed=32)
        tilt = 0.5
        weights, _ = compute_cap_tilted_weights(factor_scores, size_panel, tilt_exponent=tilt)
        merged = weights.merge(size_panel, on=["date", "symbol"])
        for _dt, grp in merged.groupby("date"):
            for sign_filter in (grp["weight"] > 0, grp["weight"] < 0):
                leg = grp.loc[sign_filter]
                if len(leg) < 2:
                    continue
                raw = leg["size"] ** tilt
                expected = raw / raw.sum()
                got = leg["weight"].abs().to_numpy()
                np.testing.assert_allclose(got, expected.to_numpy(), atol=1e-12)

    def test_tilt_zero_reduces_to_equal_weight(self) -> None:
        """tilt=0 → every stock in a leg gets identical weight (equals equal-weight)."""
        factor_scores, _ = _make_factor_data_v2(n_dates=5, n_stocks=50, seed=3)
        size_panel = _make_size_panel(factor_scores, size_heterogeneity=0.8, seed=33)
        ct_weights, _ = compute_cap_tilted_weights(factor_scores, size_panel, tilt_exponent=0.0)
        eq_weights, _ = compute_long_short_weights(factor_scores)
        merged = ct_weights.merge(eq_weights, on=["date", "symbol"], suffixes=("_ct", "_eq"))
        np.testing.assert_allclose(merged["weight_ct"].to_numpy(), merged["weight_eq"].to_numpy(), atol=1e-12)

    def test_tilt_one_is_pure_cap_weight(self) -> None:
        """tilt=1 → weights proportional to raw size within leg."""
        factor_scores, _ = _make_factor_data_v2(n_dates=5, n_stocks=50, seed=4)
        size_panel = _make_size_panel(factor_scores, size_heterogeneity=0.6, seed=34)
        weights, _ = compute_cap_tilted_weights(factor_scores, size_panel, tilt_exponent=1.0)
        merged = weights.merge(size_panel, on=["date", "symbol"])
        for _dt, grp in merged.groupby("date"):
            for sign_filter in (grp["weight"] > 0, grp["weight"] < 0):
                leg = grp.loc[sign_filter]
                if len(leg) < 2:
                    continue
                expected = leg["size"] / leg["size"].sum()
                got = leg["weight"].abs().to_numpy()
                np.testing.assert_allclose(got, expected.to_numpy(), atol=1e-12)

    def test_reduces_to_equal_weight_when_sizes_equal(self) -> None:
        """When all sizes are identical, any tilt yields equal-weight."""
        factor_scores, _ = _make_factor_data_v2(n_dates=5, n_stocks=50, seed=5)
        size_panel = _make_size_panel(factor_scores, size_heterogeneity=0.0, seed=35)
        ct_weights, _ = compute_cap_tilted_weights(factor_scores, size_panel, tilt_exponent=0.5)
        eq_weights, _ = compute_long_short_weights(factor_scores)
        merged = ct_weights.merge(eq_weights, on=["date", "symbol"], suffixes=("_ct", "_eq"))
        np.testing.assert_allclose(merged["weight_ct"].to_numpy(), merged["weight_eq"].to_numpy(), atol=1e-12)

    def test_long_symbols_have_higher_scores(self) -> None:
        """Top-quintile still gets positive weights under cap-tilting."""
        factor_scores, _ = _make_factor_data_v2(n_dates=5, n_stocks=100, seed=6)
        size_panel = _make_size_panel(factor_scores, size_heterogeneity=0.5, seed=36)
        weights, _ = compute_cap_tilted_weights(factor_scores, size_panel)
        merged = weights.merge(factor_scores, on=["date", "symbol"])
        for _dt, grp in merged.groupby("date"):
            long_scores = grp.loc[grp["weight"] > 0, "score"]
            short_scores = grp.loc[grp["weight"] < 0, "score"]
            assert long_scores.min() > short_scores.max()

    def test_nan_size_excluded(self) -> None:
        """Symbols with NaN size must be dropped; remaining weights still sum to 1."""
        factor_scores, _ = _make_factor_data_v2(n_dates=3, n_stocks=50, seed=7)
        size_panel = _make_size_panel(factor_scores, size_heterogeneity=0.4, seed=37)
        size_panel.loc[::7, "size"] = np.nan
        weights, diag = compute_cap_tilted_weights(factor_scores, size_panel)
        poisoned = size_panel.loc[size_panel["size"].isna(), ["date", "symbol"]]
        bad = pd.merge(weights, poisoned, on=["date", "symbol"], how="inner")
        assert bad.empty, "NaN-size rows must not receive weights"
        assert any("NaN size" in m.message for m in diag.messages)

    def test_nonpositive_size_excluded(self) -> None:
        """Symbols with size <= 0 must be dropped."""
        factor_scores, _ = _make_factor_data_v2(n_dates=3, n_stocks=50, seed=8)
        size_panel = _make_size_panel(factor_scores, size_heterogeneity=0.2, seed=38)
        size_panel.loc[::11, "size"] = 0.0
        size_panel.loc[::13, "size"] = -1.0
        weights, diag = compute_cap_tilted_weights(factor_scores, size_panel)
        bad_keys = size_panel.loc[size_panel["size"] <= 0, ["date", "symbol"]]
        bad = pd.merge(weights, bad_keys, on=["date", "symbol"], how="inner")
        assert bad.empty
        assert any("non-positive size" in m.message for m in diag.messages)

    def test_leg_with_no_valid_size_is_skipped(self) -> None:
        """If the entire long leg has NaN size, only the short leg emits."""
        factor_scores, _ = _make_factor_data_v2(n_dates=2, n_stocks=50, seed=9)
        size_panel = _make_size_panel(factor_scores, size_heterogeneity=0.0, seed=39)
        target_date = factor_scores["date"].iloc[0]
        day_scores = factor_scores[factor_scores["date"] == target_date].copy()
        day_scores["q"] = pd.qcut(day_scores["score"], q=5, labels=False, duplicates="drop")
        top_syms = day_scores.loc[day_scores["q"] == day_scores["q"].max(), "symbol"]
        mask = (size_panel["date"] == target_date) & (size_panel["symbol"].isin(top_syms))
        size_panel.loc[mask, "size"] = np.nan
        weights, diag = compute_cap_tilted_weights(factor_scores, size_panel)
        emitted_long = weights[(weights["date"] == target_date) & (weights["weight"] > 0)]
        assert emitted_long.empty, "Long leg should not emit when all sizes are NaN"
        emitted_short = weights[(weights["date"] == target_date) & (weights["weight"] < 0)]
        assert not emitted_short.empty, "Short leg should still emit on that date"
        assert any("no valid sizes" in m.message for m in diag.messages)

    def test_empty_factor_scores_returns_empty(self) -> None:
        weights, diag = compute_cap_tilted_weights(
            pd.DataFrame(columns=["date", "symbol", "score"]),
            pd.DataFrame({"date": [], "symbol": [], "size": []}),
        )
        assert weights.empty
        assert list(weights.columns) == ["date", "symbol", "weight"]
        assert any("Empty factor_scores" in m.message for m in diag.messages)

    def test_empty_size_panel_returns_empty(self) -> None:
        factor_scores, _ = _make_factor_data_v2(n_dates=3, n_stocks=50, seed=10)
        weights, diag = compute_cap_tilted_weights(
            factor_scores, pd.DataFrame(columns=["date", "symbol", "size"])
        )
        assert weights.empty
        assert any("Empty size_panel" in m.message for m in diag.messages)

    def test_missing_size_panel_columns_returns_empty(self) -> None:
        factor_scores, _ = _make_factor_data_v2(n_dates=3, n_stocks=50, seed=11)
        bad_panel = pd.DataFrame({"date": factor_scores["date"], "symbol": factor_scores["symbol"]})
        weights, diag = compute_cap_tilted_weights(factor_scores, bad_panel)
        assert weights.empty
        assert any("missing columns" in m.message for m in diag.messages)

    def test_invalid_tilt_exponent_returns_empty(self) -> None:
        """tilt < 0 or NaN must fail fast with an empty result."""
        factor_scores, _ = _make_factor_data_v2(n_dates=3, n_stocks=50, seed=12)
        size_panel = _make_size_panel(factor_scores, size_heterogeneity=0.3, seed=40)
        for bad in (-0.5, -1.0, float("nan")):
            weights, diag = compute_cap_tilted_weights(factor_scores, size_panel, tilt_exponent=bad)
            assert weights.empty, f"tilt={bad} must produce empty weights"
            assert any("tilt_exponent" in m.message for m in diag.messages)

    def test_insufficient_stocks_per_date_skipped(self) -> None:
        """A date with fewer than n_quantiles rows must be dropped silently."""
        factor_scores = pd.DataFrame(
            {
                "date": [pd.Timestamp("2020-01-03")] * 3 + [pd.Timestamp("2020-01-10")] * 50,
                "symbol": [f"S{i}" for i in range(3)] + [f"T{i}" for i in range(50)],
                "score": list(range(3)) + list(range(50)),
            }
        )
        size_panel = _make_size_panel(factor_scores, size_heterogeneity=0.3, seed=41)
        weights, _diag = compute_cap_tilted_weights(factor_scores, size_panel)
        assert set(weights["date"].unique()) == {pd.Timestamp("2020-01-10")}

    def test_no_unmapped_symbols_in_output(self) -> None:
        """Symbols absent from size_panel on a date must be excluded from output."""
        factor_scores, _ = _make_factor_data_v2(n_dates=3, n_stocks=50, seed=13)
        size_panel = _make_size_panel(factor_scores, size_heterogeneity=0.3, seed=42)
        drop_sym = factor_scores["symbol"].iloc[0]
        size_panel = size_panel[size_panel["symbol"] != drop_sym].copy()
        weights, _diag = compute_cap_tilted_weights(factor_scores, size_panel)
        assert drop_sym not in weights["symbol"].unique()


def _panel_from_scores(factor_scores: pd.DataFrame, score_offset: float = 0.0) -> pd.DataFrame:
    """Build a score panel from factor_scores by shifting the score column."""
    out = factor_scores[["date", "symbol", "score"]].copy()
    out["score"] = out["score"].astype(float) + float(score_offset)
    return out


class TestEnsembleWeights:
    """Tests for ``compute_ensemble_weights`` (Sharpe-weighted ensemble aggregator)."""

    def test_shape_and_columns(self):
        factor_scores, _ = _make_factor_data_v2(n_dates=4, n_stocks=30, seed=7)
        panels = {
            "A": _panel_from_scores(factor_scores, 0.0),
            "B": _panel_from_scores(factor_scores, 0.5),
        }
        sharpes = {"A": 1.0, "B": 0.5}
        ensemble, _diag = compute_ensemble_weights(panels, sharpes)
        assert list(ensemble.columns) == ["date", "symbol", "score"]
        assert len(ensemble) == len(factor_scores)

    def test_equal_sharpes_reduce_to_simple_mean(self):
        factor_scores, _ = _make_factor_data_v2(n_dates=3, n_stocks=40, seed=11)
        panel_a = _panel_from_scores(factor_scores, 0.0)
        panel_b = _panel_from_scores(factor_scores, 1.0)
        ensemble, _diag = compute_ensemble_weights({"A": panel_a, "B": panel_b}, {"A": 1.0, "B": 1.0})
        merged = ensemble.merge(panel_a, on=["date", "symbol"], suffixes=("", "_a"))
        merged = merged.merge(panel_b, on=["date", "symbol"], suffixes=("", "_b"))
        expected = 0.5 * (merged["score_a"].astype(float) + merged["score_b"].astype(float))
        assert np.allclose(merged["score"].astype(float), expected)

    def test_single_factor_passthrough(self):
        factor_scores, _ = _make_factor_data_v2(n_dates=3, n_stocks=20, seed=3)
        panel = _panel_from_scores(factor_scores, 0.25)
        ensemble, _diag = compute_ensemble_weights({"only": panel}, {"only": 0.7})
        merged = panel.merge(ensemble, on=["date", "symbol"], suffixes=("_in", "_out"))
        assert np.allclose(merged["score_in"].astype(float), merged["score_out"].astype(float))

    def test_positive_sharpe_weighting_is_monotone(self):
        factor_scores, _ = _make_factor_data_v2(n_dates=3, n_stocks=20, seed=5)
        zeros = factor_scores.copy()
        zeros["score"] = 0.0
        ones = factor_scores.copy()
        ones["score"] = 1.0
        ensemble_heavy_a, _ = compute_ensemble_weights({"A": zeros, "B": ones}, {"A": 3.0, "B": 1.0})
        ensemble_heavy_b, _ = compute_ensemble_weights({"A": zeros, "B": ones}, {"A": 1.0, "B": 3.0})
        # Heavier weight on A (zeros) → lower ensemble; heavier on B (ones) → higher.
        assert ensemble_heavy_a["score"].mean() < ensemble_heavy_b["score"].mean()
        assert np.allclose(ensemble_heavy_a["score"], 0.25)
        assert np.allclose(ensemble_heavy_b["score"], 0.75)

    def test_zero_sharpe_excluded(self):
        factor_scores, _ = _make_factor_data_v2(n_dates=2, n_stocks=15, seed=8)
        panel_a = _panel_from_scores(factor_scores, 0.0)
        panel_b = factor_scores.copy()
        panel_b["score"] = 99.0
        ensemble, _diag = compute_ensemble_weights({"A": panel_a, "B": panel_b}, {"A": 1.5, "B": 0.0})
        # Only A survives → ensemble equals A.
        merged = ensemble.merge(panel_a, on=["date", "symbol"], suffixes=("_out", "_in"))
        assert np.allclose(merged["score_out"].astype(float), merged["score_in"].astype(float))
        assert 99.0 not in ensemble["score"].tolist()

    def test_negative_sharpe_excluded(self):
        factor_scores, _ = _make_factor_data_v2(n_dates=2, n_stocks=12, seed=2)
        panel_a = _panel_from_scores(factor_scores, 0.0)
        panel_b = factor_scores.copy()
        panel_b["score"] = 42.0
        ensemble, _diag = compute_ensemble_weights({"A": panel_a, "B": panel_b}, {"A": 0.8, "B": -0.5})
        assert 42.0 not in ensemble["score"].tolist()

    def test_nan_sharpe_excluded(self):
        factor_scores, _ = _make_factor_data_v2(n_dates=2, n_stocks=10, seed=6)
        panel_a = _panel_from_scores(factor_scores, 0.0)
        panel_b = factor_scores.copy()
        panel_b["score"] = 77.0
        ensemble, _diag = compute_ensemble_weights(
            {"A": panel_a, "B": panel_b}, {"A": 1.2, "B": float("nan")}
        )
        assert 77.0 not in ensemble["score"].tolist()

    def test_inf_sharpe_excluded(self):
        factor_scores, _ = _make_factor_data_v2(n_dates=2, n_stocks=10, seed=4)
        panel_a = _panel_from_scores(factor_scores, 0.0)
        panel_b = factor_scores.copy()
        panel_b["score"] = 55.0
        ensemble, _diag = compute_ensemble_weights(
            {"A": panel_a, "B": panel_b}, {"A": 1.0, "B": float("inf")}
        )
        assert 55.0 not in ensemble["score"].tolist()

    def test_all_nonpositive_sharpes_returns_empty(self):
        factor_scores, _ = _make_factor_data_v2(n_dates=2, n_stocks=10, seed=1)
        panels = {"A": factor_scores.copy(), "B": factor_scores.copy()}
        ensemble, _diag = compute_ensemble_weights(panels, {"A": 0.0, "B": -1.0})
        assert ensemble.empty
        assert list(ensemble.columns) == ["date", "symbol", "score"]

    def test_empty_factor_score_panels_returns_empty(self):
        ensemble, _diag = compute_ensemble_weights({}, {})
        assert ensemble.empty
        assert list(ensemble.columns) == ["date", "symbol", "score"]

    def test_missing_sharpe_key_returns_empty(self):
        factor_scores, _ = _make_factor_data_v2(n_dates=2, n_stocks=8, seed=9)
        ensemble, _diag = compute_ensemble_weights(
            {"A": factor_scores.copy(), "B": factor_scores.copy()}, {"A": 1.0}
        )
        assert ensemble.empty

    def test_empty_panel_factor_excluded(self):
        factor_scores, _ = _make_factor_data_v2(n_dates=2, n_stocks=8, seed=10)
        good = _panel_from_scores(factor_scores, 0.3)
        empty = pd.DataFrame(columns=["date", "symbol", "score"])
        ensemble, _diag = compute_ensemble_weights({"A": good, "B": empty}, {"A": 1.0, "B": 1.0})
        assert not ensemble.empty
        merged = ensemble.merge(good, on=["date", "symbol"], suffixes=("_out", "_in"))
        assert np.allclose(merged["score_out"].astype(float), merged["score_in"].astype(float))

    def test_panel_missing_columns_excluded(self):
        factor_scores, _ = _make_factor_data_v2(n_dates=2, n_stocks=8, seed=14)
        good = _panel_from_scores(factor_scores, 0.0)
        bad = factor_scores.rename(columns={"score": "not_score"})
        ensemble, _diag = compute_ensemble_weights({"A": good, "B": bad}, {"A": 1.0, "B": 1.0})
        assert not ensemble.empty
        # Ensemble comes entirely from A.
        merged = ensemble.merge(good, on=["date", "symbol"], suffixes=("_out", "_in"))
        assert np.allclose(merged["score_out"].astype(float), merged["score_in"].astype(float))

    def test_nan_scores_dropped(self):
        factor_scores, _ = _make_factor_data_v2(n_dates=2, n_stocks=10, seed=17)
        panel_a = _panel_from_scores(factor_scores, 0.0)
        panel_b = factor_scores.copy()
        panel_b["score"] = float("nan")
        ensemble, _diag = compute_ensemble_weights({"A": panel_a, "B": panel_b}, {"A": 2.0, "B": 1.0})
        # B contributes nothing; ensemble equals A.
        merged = ensemble.merge(panel_a, on=["date", "symbol"], suffixes=("_out", "_in"))
        assert np.allclose(merged["score_out"].astype(float), merged["score_in"].astype(float))

    def test_coverage_mismatch_reweights_per_row(self):
        """When a factor is missing for specific (date, symbol) pairs, the
        remaining factors are re-normalized per row so the stock is not
        penalized for the coverage gap."""
        factor_scores, _ = _make_factor_data_v2(n_dates=2, n_stocks=10, seed=22)
        panel_a = factor_scores.copy()
        panel_a["score"] = 0.2
        panel_b = factor_scores.copy()
        panel_b["score"] = 0.8
        # Remove the first (date, symbol) from panel_b so it only has A.
        drop_mask = (panel_b["date"] == panel_b["date"].iloc[0]) & (
            panel_b["symbol"] == panel_b["symbol"].iloc[0]
        )
        panel_b = panel_b[~drop_mask].copy()
        ensemble, _diag = compute_ensemble_weights({"A": panel_a, "B": panel_b}, {"A": 1.0, "B": 1.0})
        # Orphan row (only A) → ensemble score == 0.2.
        orphan = ensemble[
            (ensemble["date"] == panel_a["date"].iloc[0]) & (ensemble["symbol"] == panel_a["symbol"].iloc[0])
        ]
        assert len(orphan) == 1
        assert float(orphan["score"].iloc[0]) == 0.2
        # Rows with both factors → 0.5 of (0.2 + 0.8) == 0.5.
        both = ensemble.merge(panel_b, on=["date", "symbol"], suffixes=("_out", "_b"))
        assert np.allclose(both["score_out"].astype(float), 0.5)

    def test_sharpe_weights_normalize(self):
        """Shared multiplicative scaling of Sharpes must not change the ensemble."""
        factor_scores, _ = _make_factor_data_v2(n_dates=2, n_stocks=10, seed=31)
        panels = {
            "A": _panel_from_scores(factor_scores, 0.0),
            "B": _panel_from_scores(factor_scores, 1.0),
        }
        ensemble_low, _ = compute_ensemble_weights(panels, {"A": 0.4, "B": 0.6})
        ensemble_high, _ = compute_ensemble_weights(panels, {"A": 4.0, "B": 6.0})
        merged = ensemble_low.merge(ensemble_high, on=["date", "symbol"], suffixes=("_lo", "_hi"))
        assert np.allclose(merged["score_lo"].astype(float), merged["score_hi"].astype(float))

    def test_weighted_mean_within_bounds(self):
        factor_scores, _ = _make_factor_data_v2(n_dates=3, n_stocks=25, seed=19)
        rng = np.random.default_rng(100)
        rank_a = factor_scores.copy()
        rank_a["score"] = rng.uniform(0.0, 1.0, size=len(rank_a))
        rank_b = factor_scores.copy()
        rank_b["score"] = rng.uniform(0.0, 1.0, size=len(rank_b))
        ensemble, _diag = compute_ensemble_weights({"A": rank_a, "B": rank_b}, {"A": 0.8, "B": 1.3})
        assert ensemble["score"].min() >= 0.0
        assert ensemble["score"].max() <= 1.0


def _gaussian_returns(
    vols: dict[str, float],
    n_periods: int = 200,
    seed: int = 0,
    correlation: float | None = None,
) -> dict[str, pd.Series]:
    """Generate synthetic independent (or correlated) Gaussian return series for testing."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2021-01-01", periods=n_periods, freq="B")
    names = list(vols.keys())
    n = len(names)
    if correlation is None or n < 2:
        raw = rng.standard_normal(size=(n_periods, n))
    else:
        base = rng.standard_normal(size=(n_periods, n))
        shared = rng.standard_normal(size=(n_periods, 1))
        raw = np.sqrt(1.0 - correlation) * base + np.sqrt(correlation) * shared
    scaled = raw * np.array([vols[k] for k in names])
    return {name: pd.Series(scaled[:, idx], index=dates, name=name) for idx, name in enumerate(names)}


class TestRiskParityWeights:
    """Risk-parity allocator invariants (Maillard-Roncalli-Teiletche 2010)."""

    def test_shape_and_index(self):
        returns = _gaussian_returns({"A": 0.01, "B": 0.02, "C": 0.03}, seed=1)
        w, _diag = compute_risk_parity_weights(returns)
        assert isinstance(w, pd.Series)
        assert w.name == "weight"
        assert set(w.index) == {"A", "B", "C"}
        assert len(w) == 3

    def test_weights_sum_to_one(self):
        returns = _gaussian_returns({"A": 0.01, "B": 0.02, "C": 0.03, "D": 0.015}, seed=2)
        w, _diag = compute_risk_parity_weights(returns)
        assert abs(float(w.sum()) - 1.0) < 1e-6

    def test_weights_are_nonnegative(self):
        returns = _gaussian_returns({"A": 0.01, "B": 0.02, "C": 0.03}, seed=3)
        w, _diag = compute_risk_parity_weights(returns)
        assert (w >= 0.0).all()

    def test_equal_variance_diagonal_gives_equal_weight(self):
        cov = pd.DataFrame(
            np.diag([0.04, 0.04, 0.04]),
            index=["A", "B", "C"],
            columns=["A", "B", "C"],
        )
        returns = _gaussian_returns({"A": 0.2, "B": 0.2, "C": 0.2}, seed=4)
        w, _diag = compute_risk_parity_weights(returns, cov_matrix=cov)
        np.testing.assert_allclose(w.to_numpy(), np.full(3, 1.0 / 3), atol=1e-6)

    def test_diagonal_cov_gives_inverse_vol(self):
        vols = np.array([0.1, 0.2, 0.4])
        cov = pd.DataFrame(np.diag(vols**2), index=["A", "B", "C"], columns=["A", "B", "C"])
        returns = _gaussian_returns({"A": 0.1, "B": 0.2, "C": 0.4}, seed=5)
        w, _diag = compute_risk_parity_weights(returns, cov_matrix=cov)
        expected = (1.0 / vols) / (1.0 / vols).sum()
        np.testing.assert_allclose(w.to_numpy(), expected, atol=1e-6)

    def test_single_factor_passthrough(self):
        returns = _gaussian_returns({"A": 0.02}, seed=6)
        w, _diag = compute_risk_parity_weights(returns)
        assert len(w) == 1
        assert w.index.tolist() == ["A"]
        assert float(w.iloc[0]) == 1.0

    def test_empty_input_returns_empty(self):
        w, _diag = compute_risk_parity_weights({})
        assert w.empty

    def test_all_nan_series_excluded(self):
        dates = pd.date_range("2021-01-01", periods=50, freq="B")
        nan_series = pd.Series([np.nan] * 50, index=dates)
        returns = _gaussian_returns({"A": 0.02, "B": 0.03}, seed=7)
        returns["nan_factor"] = nan_series
        w, _diag = compute_risk_parity_weights(returns)
        assert "nan_factor" not in w.index
        assert set(w.index) == {"A", "B"}

    def test_non_series_values_excluded(self):
        returns = _gaussian_returns({"A": 0.02, "B": 0.03}, seed=8)
        returns["bad"] = [1.0, 2.0, 3.0]  # type: ignore[assignment]
        w, _diag = compute_risk_parity_weights(returns)
        assert "bad" not in w.index
        assert set(w.index) == {"A", "B"}

    def test_zero_variance_factor_excluded(self):
        dates = pd.date_range("2021-01-01", periods=100, freq="B")
        returns = _gaussian_returns({"A": 0.02, "B": 0.03}, seed=9)
        returns["const"] = pd.Series(np.full(100, 0.001), index=dates)
        w, _diag = compute_risk_parity_weights(returns)
        assert "const" not in w.index
        assert set(w.index) == {"A", "B"}

    def test_explicit_cov_respected(self):
        returns = _gaussian_returns({"A": 0.01, "B": 0.01, "C": 0.01}, seed=10)
        cov = pd.DataFrame(
            np.diag([0.0001, 0.0004, 0.0016]),
            index=["A", "B", "C"],
            columns=["A", "B", "C"],
        )
        w, _diag = compute_risk_parity_weights(returns, cov_matrix=cov)
        # A (lowest vol) should have the largest weight
        assert w["A"] > w["B"] > w["C"]

    def test_cov_missing_factor_excluded(self):
        returns = _gaussian_returns({"A": 0.01, "B": 0.02, "C": 0.03}, seed=11)
        cov = pd.DataFrame(
            np.diag([0.0001, 0.0004]),
            index=["A", "B"],
            columns=["A", "B"],
        )
        w, _diag = compute_risk_parity_weights(returns, cov_matrix=cov)
        assert "C" not in w.index
        assert set(w.index) == {"A", "B"}

    def test_cov_non_square_returns_empty(self):
        returns = _gaussian_returns({"A": 0.01, "B": 0.02}, seed=12)
        cov = pd.DataFrame(
            [[0.0001, 0.0], [0.0, 0.0004]],
            index=["A", "B"],
            columns=["X", "Y"],
        )
        w, _diag = compute_risk_parity_weights(returns, cov_matrix=cov)
        assert w.empty

    def test_risk_contributions_equal_at_convergence(self):
        cov = pd.DataFrame(
            np.diag([0.01, 0.04, 0.09]),
            index=["A", "B", "C"],
            columns=["A", "B", "C"],
        )
        returns = _gaussian_returns({"A": 0.1, "B": 0.2, "C": 0.3}, seed=13)
        w, _diag = compute_risk_parity_weights(returns, cov_matrix=cov, tol=1e-12, max_iter=500)
        cov_np = cov.loc[w.index, w.index].to_numpy()
        marginal = cov_np @ w.to_numpy()
        risk_contributions = w.to_numpy() * marginal
        # All risk contributions should be equal (to within numerical tolerance)
        assert np.allclose(risk_contributions, risk_contributions.mean(), rtol=1e-5, atol=1e-8)

    def test_correlated_factors_share_weight(self):
        # Two factors A, B correlated at 0.9 with equal vol; C independent with same vol.
        # Under exact (symmetric) cov, A and B must get equal weight by symmetry, and
        # C (independent) must carry more weight than either A or B individually.
        cov = pd.DataFrame(
            [[0.0001, 0.00009, 0.0], [0.00009, 0.0001, 0.0], [0.0, 0.0, 0.0001]],
            index=["A", "B", "C"],
            columns=["A", "B", "C"],
        )
        returns = _gaussian_returns({"A": 0.01, "B": 0.01, "C": 0.01}, seed=14)
        w, _diag = compute_risk_parity_weights(returns, cov_matrix=cov, tol=1e-10, max_iter=500)
        assert w["C"] > w["A"]
        assert w["C"] > w["B"]
        np.testing.assert_allclose(float(w["A"]), float(w["B"]), atol=1e-6)

    def test_two_factor_known_solution(self):
        cov = pd.DataFrame(
            [[0.04, 0.0], [0.0, 0.16]],
            index=["A", "B"],
            columns=["A", "B"],
        )
        returns = _gaussian_returns({"A": 0.2, "B": 0.4}, seed=15)
        w, _diag = compute_risk_parity_weights(returns, cov_matrix=cov)
        # Vols 0.2 and 0.4 → weights ∝ (1/0.2, 1/0.4) = (5, 2.5) → (2/3, 1/3)
        np.testing.assert_allclose(w.to_numpy(), np.array([2.0 / 3, 1.0 / 3]), atol=1e-6)

    def test_cov_index_preserved_in_output(self):
        returns = _gaussian_returns({"alpha": 0.01, "beta": 0.02, "gamma": 0.03}, seed=16)
        w, _diag = compute_risk_parity_weights(returns)
        assert list(w.index) == ["alpha", "beta", "gamma"]


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
