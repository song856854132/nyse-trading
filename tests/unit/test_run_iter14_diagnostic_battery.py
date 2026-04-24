"""Unit tests for the iter-14 Wave-D diagnostic battery orchestrator.

Scope: ``scripts/run_iter14_diagnostic_battery.py`` pure stream functions —
near-miss bucketing, coverage matrix, pairwise Jaccard, score / return
correlation matrices, top-decile return series, sector residualization, and
sign-flip panel.

The tests are hermetic: they do NOT touch ``research.duckdb``, do NOT invoke
``main()``, and do NOT call ``screen_factor`` (which owns its own 500-rep
permutation suite). Every stream is exercised on small synthetic inputs so
invariants can be asserted deterministically.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

_SPEC = importlib.util.spec_from_file_location(
    "run_iter14_diagnostic_battery",
    _SCRIPTS / "run_iter14_diagnostic_battery.py",
)
assert _SPEC is not None and _SPEC.loader is not None
diag = importlib.util.module_from_spec(_SPEC)
# Register in sys.modules so dataclass decorator can resolve __module__ forward refs.
sys.modules["run_iter14_diagnostic_battery"] = diag
_SPEC.loader.exec_module(diag)


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _panel(rows: list[tuple[str, str, float]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["date", "symbol", "score"]).assign(
        date=lambda df: pd.to_datetime(df["date"])
    )


def _gate_payload(metrics: dict[str, float]) -> dict:
    """Build a gate_results.json-shaped payload. Accepts either semantic keys
    (``oos_sharpe``) or raw ``G{N}_value`` keys; semantic keys are translated."""
    semantic_to_raw = {
        "oos_sharpe": "G0_value",
        "permutation_p": "G1_value",
        "ic_mean": "G2_value",
        "ic_ir": "G3_value",
        "max_drawdown": "G4_value",
        "marginal_contribution": "G5_value",
    }
    normalized: dict[str, float] = {}
    for k, v in metrics.items():
        normalized[semantic_to_raw.get(k, k)] = v
    return {"gate_metrics": normalized, "passed_all": False}


# ─── Stream 1: near-miss bucketing ───────────────────────────────────────────


class TestNearMissTag:
    def test_pass_returns_pass_token(self) -> None:
        assert diag._near_miss_tag("G2_ic_mean", +0.01, passes=True) == "pass"

    def test_ic_near_miss_within_50bps(self) -> None:
        assert diag._near_miss_tag("G2_ic_mean", -0.003, passes=False) == "near_miss_within_50bps_ic"

    def test_ic_miss_beyond_50bps_returns_fail(self) -> None:
        assert diag._near_miss_tag("G2_ic_mean", -0.02, passes=False) == "fail"

    def test_icir_near_miss_within_025(self) -> None:
        assert diag._near_miss_tag("G3_ic_ir", -0.10, passes=False) == "near_miss_within_025_icir"

    def test_sharpe_near_miss_within_015(self) -> None:
        assert diag._near_miss_tag("G0_oos_sharpe", -0.10, passes=False) == "near_miss_within_015_sharpe"

    def test_mdd_near_miss_within_10pct(self) -> None:
        assert diag._near_miss_tag("G4_max_drawdown", -0.05, passes=False) == "near_miss_within_10pct_mdd"

    def test_unrecognized_gate_returns_fail(self) -> None:
        assert diag._near_miss_tag("G1_permutation_p", 0.5, passes=False) == "fail"


class TestComputePerFactorNearMiss:
    def test_emits_one_row_per_gate_present(self) -> None:
        payload = _gate_payload(
            {
                "oos_sharpe": 0.35,
                "permutation_p": 0.01,
                "ic_mean": 0.025,
                "ic_ir": 0.60,
                "max_drawdown": -0.20,
                "marginal_contribution": 0.002,
            }
        )
        rows = diag.compute_per_factor_near_miss({"foo": payload})
        assert len(rows) == 6
        assert {r.gate for r in rows} == set(diag._IN_FORCE_THRESHOLDS)
        assert all(r.passes for r in rows)
        assert all(r.near_miss_tag == "pass" for r in rows)

    def test_direction_semantics_gte(self) -> None:
        rows = diag.compute_per_factor_near_miss({"foo": _gate_payload({"oos_sharpe": 0.25})})
        row = [r for r in rows if r.gate == "G0_oos_sharpe"][0]
        assert row.passes is False
        assert row.gap == pytest.approx(-0.05)
        assert row.near_miss_tag == "near_miss_within_015_sharpe"

    def test_direction_semantics_lt(self) -> None:
        rows = diag.compute_per_factor_near_miss({"foo": _gate_payload({"permutation_p": 0.20})})
        row = [r for r in rows if r.gate == "G1_permutation_p"][0]
        assert row.passes is False
        # direction "<": gap = threshold - value = 0.05 - 0.20 = -0.15
        assert row.gap == pytest.approx(-0.15)

    def test_missing_metric_skipped_without_error(self) -> None:
        payload = _gate_payload({"oos_sharpe": 0.40})
        rows = diag.compute_per_factor_near_miss({"foo": payload})
        assert [r.gate for r in rows] == ["G0_oos_sharpe"]

    def test_multiple_factors_sorted_by_name(self) -> None:
        rows = diag.compute_per_factor_near_miss(
            {
                "zzz": _gate_payload({"ic_mean": 0.01}),
                "aaa": _gate_payload({"ic_mean": 0.01}),
            }
        )
        assert [r.factor for r in rows] == ["aaa", "zzz"]


# ─── Stream 2: coverage ──────────────────────────────────────────────────────


class TestCoverageMatrix:
    def test_coverage_counts_and_percent(self) -> None:
        panels = {
            "f1": _panel(
                [
                    ("2020-01-03", "A", 0.1),
                    ("2020-01-03", "B", 0.9),
                    ("2020-01-10", "A", 0.5),
                ]
            )
        }
        rebalance = [pd.Timestamp("2020-01-03"), pd.Timestamp("2020-01-10")]
        universe = {pd.Timestamp("2020-01-03"): 4, pd.Timestamp("2020-01-10"): 4}
        out = diag.compute_coverage_matrix(panels, rebalance, universe)
        assert list(out.columns) == ["date", "factor", "n_covered", "universe_size", "coverage_pct"]
        r1 = out.loc[out["date"] == "2020-01-03"].iloc[0]
        assert int(r1["n_covered"]) == 2
        assert r1["coverage_pct"] == pytest.approx(0.5)
        r2 = out.loc[out["date"] == "2020-01-10"].iloc[0]
        assert r2["coverage_pct"] == pytest.approx(0.25)

    def test_empty_panel_yields_empty_output(self) -> None:
        out = diag.compute_coverage_matrix({"f1": pd.DataFrame(columns=["date", "symbol", "score"])}, [], {})
        assert out.empty
        assert list(out.columns) == ["date", "factor", "n_covered", "universe_size", "coverage_pct"]

    def test_universe_size_zero_yields_zero_pct(self) -> None:
        panels = {"f1": _panel([("2020-01-03", "A", 0.1)])}
        out = diag.compute_coverage_matrix(
            panels, [pd.Timestamp("2020-01-03")], {pd.Timestamp("2020-01-03"): 0}
        )
        assert out.iloc[0]["coverage_pct"] == 0.0


class TestPairwiseJaccard:
    def test_identity_on_diagonal(self) -> None:
        panels = {
            "f1": _panel([("2020-01-03", "A", 0.1), ("2020-01-03", "B", 0.2)]),
            "f2": _panel([("2020-01-03", "A", 0.3), ("2020-01-03", "C", 0.4)]),
        }
        j = diag.compute_pairwise_jaccard(panels)
        assert j.at["f1", "f1"] == 1.0
        assert j.at["f2", "f2"] == 1.0

    def test_off_diagonal_symmetric(self) -> None:
        panels = {
            "f1": _panel([("2020-01-03", "A", 0.1), ("2020-01-03", "B", 0.2), ("2020-01-03", "C", 0.3)]),
            "f2": _panel([("2020-01-03", "A", 0.3), ("2020-01-03", "B", 0.4)]),
        }
        j = diag.compute_pairwise_jaccard(panels)
        # {A,B,C} ∩ {A,B} = {A,B} size 2; union size 3 → jaccard = 2/3
        assert j.at["f1", "f2"] == pytest.approx(2 / 3)
        assert j.at["f2", "f1"] == pytest.approx(2 / 3)

    def test_disjoint_factors_give_zero(self) -> None:
        panels = {
            "f1": _panel([("2020-01-03", "A", 0.1)]),
            "f2": _panel([("2020-01-03", "B", 0.2)]),
        }
        j = diag.compute_pairwise_jaccard(panels)
        assert j.at["f1", "f2"] == 0.0


# ─── Stream 3: correlations ──────────────────────────────────────────────────


class TestPairwiseScoreCorrelation:
    def test_perfect_correlation_when_scores_align(self) -> None:
        # f1 and f2 have identical per-date rankings; Spearman = +1
        symbols = [f"S{i:02d}" for i in range(12)]
        scores = np.linspace(0.0, 1.0, 12)
        rows_f1 = [("2020-01-03", s, v) for s, v in zip(symbols, scores, strict=True)]
        rows_f2 = [("2020-01-03", s, v + 0.0) for s, v in zip(symbols, scores, strict=True)]
        out = diag.compute_pairwise_score_correlation({"f1": _panel(rows_f1), "f2": _panel(rows_f2)})
        assert out.at["f1", "f2"] == pytest.approx(1.0)

    def test_perfect_negative_correlation(self) -> None:
        symbols = [f"S{i:02d}" for i in range(12)]
        scores = np.linspace(0.0, 1.0, 12)
        rows_f1 = [("2020-01-03", s, v) for s, v in zip(symbols, scores, strict=True)]
        rows_f2 = [("2020-01-03", s, 1.0 - v) for s, v in zip(symbols, scores, strict=True)]
        out = diag.compute_pairwise_score_correlation({"f1": _panel(rows_f1), "f2": _panel(rows_f2)})
        assert out.at["f1", "f2"] == pytest.approx(-1.0)

    def test_insufficient_overlap_skips_date(self) -> None:
        # only 3 shared symbols — below min_periods=10 threshold
        rows_f1 = [("2020-01-03", f"S{i}", float(i)) for i in range(3)]
        rows_f2 = [("2020-01-03", f"S{i}", float(i)) for i in range(3)]
        out = diag.compute_pairwise_score_correlation({"f1": _panel(rows_f1), "f2": _panel(rows_f2)})
        assert pd.isna(out.at["f1", "f2"])


class TestTopDecileReturnSeries:
    def test_equal_weight_mean_of_top_quantile(self) -> None:
        symbols = [f"S{i:02d}" for i in range(10)]
        panel = _panel([("2020-01-03", s, float(i) / 10) for i, s in enumerate(symbols)])
        # Top 10% → top 1 symbol by score (S09); its fwd_ret_5d = 0.05
        fwd = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-03"] * 10),
                "symbol": symbols,
                "fwd_ret_5d": np.linspace(-0.05, 0.05, 10),
            }
        )
        series = diag.compute_top_decile_return_series(panel, fwd, quantile=0.9)
        assert series.iloc[0] == pytest.approx(np.linspace(-0.05, 0.05, 10)[-1])

    def test_empty_inputs(self) -> None:
        s = diag.compute_top_decile_return_series(
            pd.DataFrame(columns=["date", "symbol", "score"]),
            pd.DataFrame(columns=["date", "symbol", "fwd_ret_5d"]),
        )
        assert s.empty

    def test_insufficient_symbols_drops_date(self) -> None:
        symbols = [f"S{i}" for i in range(5)]
        panel = _panel([("2020-01-03", s, float(i)) for i, s in enumerate(symbols)])
        fwd = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-03"] * 5),
                "symbol": symbols,
                "fwd_ret_5d": [0.0] * 5,
            }
        )
        s = diag.compute_top_decile_return_series(panel, fwd)
        assert s.empty


class TestPairwiseReturnCorrelation:
    def test_symmetric_and_diagonal_one(self) -> None:
        rng = np.random.default_rng(42)
        symbols = [f"S{i:02d}" for i in range(20)]
        frames_panel = []
        frames_fwd = []
        for d in pd.date_range("2020-01-03", periods=15, freq="W-FRI"):
            frames_panel.append(_panel([(d.strftime("%Y-%m-%d"), s, float(rng.uniform())) for s in symbols]))
            frames_fwd.append(
                pd.DataFrame(
                    {
                        "date": [d] * len(symbols),
                        "symbol": symbols,
                        "fwd_ret_5d": rng.normal(0.0, 0.01, len(symbols)),
                    }
                )
            )
        panel_a = pd.concat(frames_panel, ignore_index=True)
        panel_b = panel_a.copy()
        fwd = pd.concat(frames_fwd, ignore_index=True)
        out = diag.compute_pairwise_return_correlation({"a": panel_a, "b": panel_b}, fwd)
        assert out.at["a", "a"] == pytest.approx(1.0)
        assert out.at["a", "b"] == pytest.approx(out.at["b", "a"])


# ─── Stream 4: sector residualization ────────────────────────────────────────


class TestSectorResidualizePanel:
    def test_within_sector_mean_is_zero(self) -> None:
        # Two sectors, mean score per sector = 0.5 → within-sector residuals sum to 0.
        panel = _panel(
            [
                ("2020-01-03", "A", 0.1),
                ("2020-01-03", "B", 0.9),
                ("2020-01-03", "C", 0.2),
                ("2020-01-03", "D", 0.8),
                ("2020-01-03", "E", 0.3),
            ]
        )
        sector_map = pd.Series({"A": "Tech", "B": "Tech", "C": "Energy", "D": "Energy", "E": "Energy"})
        out, d = diag.sector_residualize_panel(panel, sector_map)
        # per sector, residuals must sum to ~0
        by_sym = dict(zip(out["symbol"], out["score"], strict=True))
        tech = by_sym["A"] + by_sym["B"]
        energy = by_sym["C"] + by_sym["D"] + by_sym["E"]
        assert tech == pytest.approx(0.0, abs=1e-9)
        assert energy == pytest.approx(0.0, abs=1e-9)
        assert d["dates_processed"] == 1
        assert d["symbols_dropped_no_sector"] == 0

    def test_drops_symbols_with_no_sector(self) -> None:
        panel = _panel(
            [
                ("2020-01-03", "A", 0.1),
                ("2020-01-03", "B", 0.5),
                ("2020-01-03", "C", 0.9),
                ("2020-01-03", "D", 0.4),
                ("2020-01-03", "E", 0.3),
                ("2020-01-03", "UNKNOWN", 0.7),
            ]
        )
        sector_map = pd.Series({"A": "Tech", "B": "Tech", "C": "Tech", "D": "Energy", "E": "Energy"})
        out, d = diag.sector_residualize_panel(panel, sector_map)
        assert "UNKNOWN" not in set(out["symbol"])
        assert d["symbols_dropped_no_sector"] == 1

    def test_too_few_observations_skipped(self) -> None:
        # Only 2 symbols — below the len(group) < 5 guard.
        panel = _panel([("2020-01-03", "A", 0.1), ("2020-01-03", "B", 0.9)])
        sector_map = pd.Series({"A": "Tech", "B": "Energy"})
        out, d = diag.sector_residualize_panel(panel, sector_map)
        assert out.empty
        assert d["dates_processed"] == 0

    def test_empty_input_returns_empty(self) -> None:
        out, d = diag.sector_residualize_panel(
            pd.DataFrame(columns=["date", "symbol", "score"]),
            pd.Series(dtype=str),
        )
        assert out.empty
        assert d["dates_processed"] == 0
        assert d["rows_in"] == 0


# ─── Stream 5: sign flip ─────────────────────────────────────────────────────


class TestSignFlipPanel:
    def test_p_becomes_one_minus_p(self) -> None:
        panel = _panel(
            [
                ("2020-01-03", "A", 0.0),
                ("2020-01-03", "B", 0.25),
                ("2020-01-03", "C", 0.75),
                ("2020-01-03", "D", 1.0),
            ]
        )
        out = diag.sign_flip_panel(panel)
        flipped = dict(zip(out["symbol"], out["score"], strict=True))
        assert flipped["A"] == pytest.approx(1.0)
        assert flipped["B"] == pytest.approx(0.75)
        assert flipped["C"] == pytest.approx(0.25)
        assert flipped["D"] == pytest.approx(0.0)

    def test_rank_order_reversed(self) -> None:
        panel = _panel(
            [
                ("2020-01-03", "A", 0.1),
                ("2020-01-03", "B", 0.9),
                ("2020-01-03", "C", 0.5),
            ]
        )
        out = diag.sign_flip_panel(panel)
        # Highest original should become lowest flipped.
        orig_ord = panel.sort_values("score")["symbol"].tolist()
        flip_ord = out.sort_values("score")["symbol"].tolist()
        assert orig_ord == list(reversed(flip_ord))

    def test_empty_input_returns_empty(self) -> None:
        out = diag.sign_flip_panel(pd.DataFrame(columns=["date", "symbol", "score"]))
        assert out.empty

    def test_does_not_mutate_input(self) -> None:
        panel = _panel([("2020-01-03", "A", 0.3)])
        _ = diag.sign_flip_panel(panel)
        assert panel.iloc[0]["score"] == pytest.approx(0.3)
