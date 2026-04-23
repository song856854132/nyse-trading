"""Unit tests for the iter-12 ensemble G0 orchestrator glue.

Scope: ``scripts/simulate_ensemble_g0.py`` helper functions — registry-driven
panel construction, sign-inversion pass-through, equal-Sharpe aggregator
degeneracy, forward-return builder, per-date IC series, and the all-metric
summary bundle including the all-empty guards.

The tests are hermetic: they do NOT touch ``research.duckdb`` and do NOT
invoke ``main()``. Dummy factor compute functions are registered via
``FactorRegistry`` so behavior is verified against the same code path the
iter-12 run exercises (``registry.compute_all`` → rank-percentile →
``compute_ensemble_weights``).
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from nyse_core.contracts import Diagnostics
from nyse_core.features.registry import FactorRegistry
from nyse_core.schema import UsageDomain

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

_SPEC = importlib.util.spec_from_file_location("simulate_ensemble_g0", _SCRIPTS / "simulate_ensemble_g0.py")
assert _SPEC is not None and _SPEC.loader is not None
sim = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sim)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _factor_pos_close(data: pd.DataFrame) -> tuple[pd.Series, Diagnostics]:
    """+1 factor: per-symbol mean close price on visible OHLCV."""
    diag = Diagnostics()
    grouped = data.groupby("symbol")["close"].mean()
    return grouped, diag


def _factor_neg_volume(data: pd.DataFrame) -> tuple[pd.Series, Diagnostics]:
    """-1 factor (registry inverts): per-symbol mean volume. Low volume = buy."""
    diag = Diagnostics()
    grouped = data.groupby("symbol")["volume"].mean()
    return grouped, diag


def _factor_raises(data: pd.DataFrame) -> tuple[pd.Series, Diagnostics]:
    """Always-raising factor; registry catches and skips it."""
    raise KeyError("missing_metric")


def _make_ohlcv(
    symbols: list[str],
    dates: list[pd.Timestamp],
    seed: int = 0,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []
    for dt in dates:
        for sym in symbols:
            base = 10.0 + hash(sym) % 50
            price = float(base + rng.standard_normal() * 0.5)
            rows.append(
                {
                    "date": dt,
                    "symbol": sym,
                    "open": price,
                    "high": price * 1.01,
                    "low": price * 0.99,
                    "close": price,
                    "volume": float(1_000_000 + rng.integers(0, 500_000)),
                }
            )
    return pd.DataFrame(rows)


# ── build_factor_score_panels ────────────────────────────────────────────────


class TestBuildFactorScorePanels:
    def test_happy_path_two_factors_present(self) -> None:
        """Registry produces per-factor panels rank-percentile normalized in [0,1]."""
        reg = FactorRegistry()
        reg.register("mean_close_plus", _factor_pos_close, UsageDomain.SIGNAL, +1)
        reg.register("mean_volume_inv", _factor_neg_volume, UsageDomain.SIGNAL, -1)
        symbols = [f"SYM{i:03d}" for i in range(20)]
        dates = [pd.Timestamp("2020-01-10"), pd.Timestamp("2020-01-17")]
        ohlcv = _make_ohlcv(symbols, dates)

        panels, exclusions = sim.build_factor_score_panels(reg, ohlcv, pd.DataFrame(), dates)

        assert set(panels.keys()) == {"mean_close_plus", "mean_volume_inv"}
        assert exclusions == {}
        for name, panel in panels.items():
            assert set(panel.columns) == {"date", "symbol", "score"}
            assert len(panel) > 0, name
            assert panel["score"].min() >= 0.0
            assert panel["score"].max() <= 1.0

    def test_missing_data_source_excluded_with_reason(self) -> None:
        """Factor whose data_source is absent from data_sources is excluded."""
        reg = FactorRegistry()
        reg.register(
            "needs_fundamentals",
            _factor_pos_close,
            UsageDomain.SIGNAL,
            +1,
            data_source="fundamentals",
        )
        symbols = [f"SYM{i:03d}" for i in range(10)]
        dates = [pd.Timestamp("2020-01-10")]
        ohlcv = _make_ohlcv(symbols, dates)

        panels, exclusions = sim.build_factor_score_panels(reg, ohlcv, pd.DataFrame(), dates)

        assert panels == {}
        assert "needs_fundamentals" in exclusions
        assert "no_scores_produced" in exclusions["needs_fundamentals"]

    def test_factor_raising_exception_skipped(self) -> None:
        """Registry's per-factor try/except means a raising compute does not poison batch."""
        reg = FactorRegistry()
        reg.register("good", _factor_pos_close, UsageDomain.SIGNAL, +1)
        reg.register("broken", _factor_raises, UsageDomain.SIGNAL, +1)
        symbols = [f"SYM{i:03d}" for i in range(8)]
        dates = [pd.Timestamp("2020-02-07")]
        ohlcv = _make_ohlcv(symbols, dates)

        panels, exclusions = sim.build_factor_score_panels(reg, ohlcv, pd.DataFrame(), dates)

        assert "good" in panels
        assert "broken" in exclusions

    def test_sign_inversion_round_trip(self) -> None:
        """-1 sign_convention inverts raw values before rank-percentile.

        Because we register ``mean_volume_inv`` with sign=-1, symbols with
        LOWER volume should map to HIGHER normalized scores.
        """
        reg = FactorRegistry()
        reg.register("volume_inv", _factor_neg_volume, UsageDomain.SIGNAL, -1)

        dates = [pd.Timestamp("2020-03-06")]
        rows: list[dict[str, object]] = []
        for dt in dates:
            for sym, vol in [("LOW_VOL", 100.0), ("MID_VOL", 1_000.0), ("HIGH_VOL", 10_000.0)]:
                rows.append(
                    {
                        "date": dt,
                        "symbol": sym,
                        "open": 10.0,
                        "high": 10.1,
                        "low": 9.9,
                        "close": 10.0,
                        "volume": vol,
                    }
                )
        ohlcv = pd.DataFrame(rows)

        panels, _ = sim.build_factor_score_panels(reg, ohlcv, pd.DataFrame(), dates)
        panel = panels["volume_inv"].set_index("symbol")
        assert panel.loc["LOW_VOL", "score"] > panel.loc["HIGH_VOL", "score"]

    def test_empty_rebalance_dates_returns_empty(self) -> None:
        reg = FactorRegistry()
        reg.register("mean_close_plus", _factor_pos_close, UsageDomain.SIGNAL, +1)
        symbols = ["A", "B"]
        ohlcv = _make_ohlcv(symbols, [pd.Timestamp("2020-01-10")])

        panels, exclusions = sim.build_factor_score_panels(reg, ohlcv, pd.DataFrame(), [])

        assert panels == {}
        assert "mean_close_plus" in exclusions

    def test_visibility_filter_uses_only_past_data(self) -> None:
        """Factor sees only rows with date <= rebalance timestamp."""
        captured: dict[str, int] = {}

        def factor_counts(data: pd.DataFrame) -> tuple[pd.Series, Diagnostics]:
            diag = Diagnostics()
            captured["rows_seen"] = len(data)
            return data.groupby("symbol")["close"].mean(), diag

        reg = FactorRegistry()
        reg.register("counts", factor_counts, UsageDomain.SIGNAL, +1)
        symbols = [f"SYM{i:02d}" for i in range(5)]
        all_dates = pd.date_range("2020-01-01", "2020-03-01", freq="B")
        ohlcv = _make_ohlcv(symbols, list(all_dates))

        early = pd.Timestamp("2020-01-15")
        sim.build_factor_score_panels(reg, ohlcv, pd.DataFrame(), [early])
        rows_early = captured["rows_seen"]

        late = pd.Timestamp("2020-02-28")
        sim.build_factor_score_panels(reg, ohlcv, pd.DataFrame(), [late])
        rows_late = captured["rows_seen"]

        assert rows_early < rows_late


# ── _compute_forward_returns ─────────────────────────────────────────────────


class TestComputeForwardReturns:
    def test_basic_fwd_return_shape(self) -> None:
        symbols = ["A", "B", "C"]
        dates = pd.date_range("2020-01-02", periods=20, freq="B")
        ohlcv = _make_ohlcv(symbols, list(dates))
        rebalance = [dates[0], dates[5]]

        fwd = sim._compute_forward_returns(ohlcv, rebalance)

        assert set(fwd.columns) == {"date", "symbol", "fwd_ret_5d"}
        assert len(fwd) > 0
        for dt in fwd["date"].unique():
            assert dt in {d.date() for d in rebalance}

    def test_insufficient_future_skipped(self) -> None:
        """Rebalance date with < 5 future bars yields no forward-return row."""
        symbols = ["A", "B"]
        dates = pd.date_range("2020-01-02", periods=4, freq="B")
        ohlcv = _make_ohlcv(symbols, list(dates))

        fwd = sim._compute_forward_returns(ohlcv, [dates[0]])

        assert fwd.empty
        assert set(fwd.columns) == {"date", "symbol", "fwd_ret_5d"}

    def test_empty_ohlcv_returns_empty(self) -> None:
        empty = pd.DataFrame(columns=["date", "symbol", "open", "high", "low", "close", "volume"])
        fwd = sim._compute_forward_returns(empty, [pd.Timestamp("2020-01-15")])
        assert fwd.empty


# ── compute_ensemble_ic_series + summarize_ensemble ──────────────────────────


class TestEnsembleSummary:
    def test_ic_series_empty_when_no_overlap(self) -> None:
        scores = pd.DataFrame(
            [
                {"date": date(2020, 1, 10), "symbol": "A", "score": 0.5},
                {"date": date(2020, 1, 10), "symbol": "B", "score": 0.8},
            ]
        )
        fwd = pd.DataFrame(
            [
                {"date": date(2020, 2, 10), "symbol": "A", "fwd_ret_5d": 0.01},
            ]
        )

        ic = sim.compute_ensemble_ic_series(scores, fwd)

        assert len(ic) == 0

    def test_summary_empty_ls_returns_all_none(self) -> None:
        """No overlap → n_periods=0 and metrics None, not a raise."""
        scores = pd.DataFrame(columns=["date", "symbol", "score"])
        fwd = pd.DataFrame(columns=["date", "symbol", "fwd_ret_5d"])

        result = sim.summarize_ensemble(scores, fwd, perm_reps=50)

        assert result["n_periods"] == 0
        for key in ("oos_sharpe", "ic_mean", "ic_ir", "max_drawdown", "permutation_p"):
            assert result[key] is None
        assert result["permutation_reps"] == 50
        assert result["annualization_periods_per_year"] == 52

    def test_summary_populates_metrics_on_real_overlap(self) -> None:
        """Happy path: enough dates + symbols → Sharpe + IC metrics populate."""
        rng = np.random.default_rng(7)
        dates = [date(2020, m, 3) for m in range(1, 13)]
        symbols = [f"SYM{i:03d}" for i in range(40)]
        scores_rows: list[dict[str, object]] = []
        fwd_rows: list[dict[str, object]] = []
        for dt in dates:
            for sym in symbols:
                s = float(rng.uniform(0.0, 1.0))
                r = 0.02 * (s - 0.5) + rng.standard_normal() * 0.01
                scores_rows.append({"date": dt, "symbol": sym, "score": s})
                fwd_rows.append({"date": dt, "symbol": sym, "fwd_ret_5d": float(r)})
        scores = pd.DataFrame(scores_rows)
        fwd = pd.DataFrame(fwd_rows)

        result = sim.summarize_ensemble(scores, fwd, perm_reps=60)

        assert result["n_periods"] == len(dates)
        assert result["oos_sharpe"] is not None
        assert result["ic_mean"] is not None
        assert result["ic_ir"] is not None
        assert result["max_drawdown"] is not None
        assert result["max_drawdown"] <= 0.0
        assert result["permutation_reps"] == 60


# ── Equal-Sharpe aggregator degeneracy (the iter-12 contract) ────────────────


class TestEqualSharpeDegeneracy:
    """The iter-12 diagnostic relies on equal Sharpes collapsing to a mean.

    ``compute_ensemble_weights`` normalizes weights to sum to 1. With all
    Sharpes equal and positive, and full coverage across (date, symbol), the
    numerator / denominator ratio degenerates to the arithmetic mean of the
    per-factor scores at each (date, symbol) pair.
    """

    def test_equal_sharpes_equal_simple_mean(self) -> None:
        panel_a = pd.DataFrame(
            [
                {"date": date(2020, 1, 10), "symbol": "A", "score": 0.2},
                {"date": date(2020, 1, 10), "symbol": "B", "score": 0.8},
            ]
        )
        panel_b = pd.DataFrame(
            [
                {"date": date(2020, 1, 10), "symbol": "A", "score": 0.4},
                {"date": date(2020, 1, 10), "symbol": "B", "score": 0.6},
            ]
        )
        from nyse_core.factor_screening import compute_ensemble_weights

        ens, _ = compute_ensemble_weights(
            {"fa": panel_a, "fb": panel_b},
            {"fa": 1.0, "fb": 1.0},
        )
        ens_by_sym = ens.set_index("symbol")["score"]

        assert ens_by_sym.loc["A"] == pytest.approx((0.2 + 0.4) / 2)
        assert ens_by_sym.loc["B"] == pytest.approx((0.8 + 0.6) / 2)

    def test_single_factor_degenerates_to_identity(self) -> None:
        """One factor in + equal Sharpes ⇒ ensemble == input scores."""
        panel = pd.DataFrame(
            [
                {"date": date(2020, 6, 5), "symbol": "X", "score": 0.33},
                {"date": date(2020, 6, 5), "symbol": "Y", "score": 0.91},
            ]
        )
        from nyse_core.factor_screening import compute_ensemble_weights

        ens, _ = compute_ensemble_weights({"solo": panel}, {"solo": 1.0})
        ens_by_sym = ens.set_index("symbol")["score"]

        assert ens_by_sym.loc["X"] == pytest.approx(0.33)
        assert ens_by_sym.loc["Y"] == pytest.approx(0.91)

    def test_missing_symbol_per_factor_renormalizes(self) -> None:
        """Symbol in factor A but not B ⇒ ensemble uses {A} only at that row.

        ``compute_ensemble_weights`` re-normalizes per (date, symbol) via
        numerator/denominator, so a symbol seen by only one factor gets that
        factor's raw score (not a downweighted score).
        """
        panel_a = pd.DataFrame(
            [
                {"date": date(2020, 9, 4), "symbol": "ONLY_A", "score": 0.7},
                {"date": date(2020, 9, 4), "symbol": "BOTH", "score": 0.3},
            ]
        )
        panel_b = pd.DataFrame(
            [
                {"date": date(2020, 9, 4), "symbol": "BOTH", "score": 0.9},
            ]
        )
        from nyse_core.factor_screening import compute_ensemble_weights

        ens, _ = compute_ensemble_weights(
            {"fa": panel_a, "fb": panel_b},
            {"fa": 1.0, "fb": 1.0},
        )
        ens_by_sym = ens.set_index("symbol")["score"]
        assert ens_by_sym.loc["ONLY_A"] == pytest.approx(0.7)
        assert ens_by_sym.loc["BOTH"] == pytest.approx((0.3 + 0.9) / 2)

    def test_empty_panels_returns_empty(self) -> None:
        from nyse_core.factor_screening import compute_ensemble_weights

        ens, diag = compute_ensemble_weights({}, {})

        assert ens.empty
        assert list(ens.columns) == ["date", "symbol", "score"]
        assert any(m.level.value == "WARNING" for m in diag.messages)

    def test_all_nan_scores_excluded(self) -> None:
        """A factor with all-NaN scores is silently dropped from the aggregation."""
        panel_nan = pd.DataFrame(
            [
                {"date": date(2020, 9, 4), "symbol": "A", "score": np.nan},
                {"date": date(2020, 9, 4), "symbol": "B", "score": np.nan},
            ]
        )
        panel_ok = pd.DataFrame(
            [
                {"date": date(2020, 9, 4), "symbol": "A", "score": 0.4},
                {"date": date(2020, 9, 4), "symbol": "B", "score": 0.6},
            ]
        )
        from nyse_core.factor_screening import compute_ensemble_weights

        ens, _ = compute_ensemble_weights(
            {"bad": panel_nan, "good": panel_ok},
            {"bad": 1.0, "good": 1.0},
        )
        ens_by_sym = ens.set_index("symbol")["score"]
        assert ens_by_sym.loc["A"] == pytest.approx(0.4)
        assert ens_by_sym.loc["B"] == pytest.approx(0.6)


# ── _weekly_fridays ──────────────────────────────────────────────────────────


class TestWeeklyFridays:
    def test_weekly_fridays_falls_on_friday(self) -> None:
        fridays = sim._weekly_fridays(date(2020, 1, 1), date(2020, 2, 1))
        assert len(fridays) > 0
        for f in fridays:
            assert f.dayofweek == 4  # 0=Mon ... 4=Fri

    def test_weekly_fridays_covers_range(self) -> None:
        fridays = sim._weekly_fridays(date(2020, 1, 1), date(2020, 3, 31))
        assert fridays[0] >= pd.Timestamp("2020-01-01")
        assert fridays[-1] <= pd.Timestamp("2020-03-31")
