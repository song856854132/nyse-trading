"""Unit tests for ``nyse_core.benchmark_metrics.compute_benchmark_relative_metrics``.

The helper is diagnostic (not gated), so correctness here is about arithmetic honesty
more than thresholds:

- Perfectly correlated benchmark → beta ≈ 1, alpha_ann ≈ 0, sharpe_excess ≈ 0
- Anti-correlated benchmark → beta ≈ -1, large positive excess Sharpe when portfolio
  direction dominates
- Zero-variance benchmark → beta NaN (documented), metrics gracefully degrade
- Non-overlapping indices → empty overlap path returns NaN payload with n_obs=0
- Empty portfolio → every benchmark returns NaN payload with n_obs=0
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nyse_core.benchmark_metrics import compute_benchmark_relative_metrics
from nyse_core.schema import TRADING_DAYS_PER_YEAR


def _weekly_dates(n: int, start: str = "2020-01-03") -> pd.DatetimeIndex:
    return pd.date_range(start=start, periods=n, freq="W-FRI")


class TestCorrelatedBenchmark:
    def test_identical_series_has_zero_excess_and_unit_beta(self) -> None:
        idx = _weekly_dates(200)
        rng = np.random.default_rng(42)
        port = pd.Series(rng.normal(0.002, 0.01, size=200), index=idx)
        bench = port.copy()

        out, diag = compute_benchmark_relative_metrics(
            portfolio_returns=port,
            benchmark_returns={"IDENT": bench},
        )

        m = out["IDENT"]
        assert m["n_obs"] == 200
        # portfolio == benchmark => excess ≡ 0 => sharpe_excess==0, tracking==0, IR=NaN
        assert m["sharpe_excess"] == pytest.approx(0.0, abs=1e-12)
        assert m["tracking_error_ann"] == pytest.approx(0.0, abs=1e-12)
        assert np.isnan(m["information_ratio"])
        # beta of series with itself is 1 exactly
        assert m["beta"] == pytest.approx(1.0, rel=1e-10)
        # alpha = (mean_p - beta*mean_b)*af = 0*af = 0
        assert m["alpha_ann"] == pytest.approx(0.0, abs=1e-12)

    def test_scaled_benchmark_recovers_scale_factor_as_beta(self) -> None:
        idx = _weekly_dates(500)
        rng = np.random.default_rng(1)
        base = rng.normal(0.0, 0.01, size=500)
        port = pd.Series(2.0 * base + 0.001, index=idx)  # port = 2*bench + 0.001
        bench = pd.Series(base, index=idx)

        out, _ = compute_benchmark_relative_metrics(
            portfolio_returns=port,
            benchmark_returns={"SCALE": bench},
        )
        m = out["SCALE"]
        # beta must recover the scale factor, alpha_ann approximately 0.001 * 252
        assert m["beta"] == pytest.approx(2.0, rel=5e-3)
        assert m["alpha_ann"] == pytest.approx(0.001 * TRADING_DAYS_PER_YEAR, rel=0.1)


class TestAntiCorrelatedBenchmark:
    def test_negative_beta_when_benchmark_mirrors_portfolio(self) -> None:
        idx = _weekly_dates(500)
        rng = np.random.default_rng(7)
        port = pd.Series(rng.normal(0.003, 0.02, size=500), index=idx)
        # Pure anti-correlation: bench is exactly -portfolio so beta = -1 exactly
        bench = -port

        out, _ = compute_benchmark_relative_metrics(
            portfolio_returns=port,
            benchmark_returns={"NEG": bench},
        )
        m = out["NEG"]
        assert m["beta"] == pytest.approx(-1.0, abs=1e-10)


class TestDegenerateInputs:
    def test_empty_portfolio_returns_nan_payload(self) -> None:
        port = pd.Series(dtype=float)
        idx = _weekly_dates(10)
        bench = pd.Series(np.ones(10) * 0.001, index=idx)

        out, diag = compute_benchmark_relative_metrics(
            portfolio_returns=port,
            benchmark_returns={"SPY": bench},
        )
        assert set(out.keys()) == {"SPY"}
        m = out["SPY"]
        assert m["n_obs"] == 0
        for k in ("sharpe_excess", "beta", "alpha_ann", "information_ratio"):
            assert np.isnan(m[k])
        assert any("portfolio_returns is empty" in msg.message for msg in diag.messages)

    def test_empty_benchmark_returns_nan_payload_for_that_ticker(self) -> None:
        idx = _weekly_dates(50)
        port = pd.Series(np.linspace(-0.01, 0.02, 50), index=idx)
        good = port * 0.5
        empty = pd.Series(dtype=float)

        out, diag = compute_benchmark_relative_metrics(
            portfolio_returns=port,
            benchmark_returns={"GOOD": good, "EMPTY": empty},
        )
        assert out["GOOD"]["n_obs"] == 50
        assert out["EMPTY"]["n_obs"] == 0
        assert np.isnan(out["EMPTY"]["beta"])
        assert any("'EMPTY' empty" in msg.message for msg in diag.messages)

    def test_no_index_overlap_returns_nan_payload(self) -> None:
        port = pd.Series([0.01, 0.02, -0.005], index=_weekly_dates(3, start="2020-01-03"))
        bench = pd.Series([0.005, 0.004, 0.007], index=_weekly_dates(3, start="2021-06-04"))
        out, diag = compute_benchmark_relative_metrics(
            portfolio_returns=port,
            benchmark_returns={"NOOVL": bench},
        )
        assert out["NOOVL"]["n_obs"] == 0
        assert any("no overlap" in msg.message for msg in diag.messages)

    def test_zero_variance_benchmark_yields_nan_beta_but_defined_sharpe(self) -> None:
        idx = _weekly_dates(100)
        rng = np.random.default_rng(11)
        port = pd.Series(rng.normal(0.002, 0.01, size=100), index=idx)
        bench = pd.Series(np.full(100, 0.001), index=idx)  # zero variance

        out, diag = compute_benchmark_relative_metrics(
            portfolio_returns=port,
            benchmark_returns={"FLAT": bench},
        )
        m = out["FLAT"]
        # beta and alpha are undefined (var=0)
        assert np.isnan(m["beta"])
        assert np.isnan(m["alpha_ann"])
        # sharpe_excess is still computable — excess = port - constant
        assert np.isfinite(m["sharpe_excess"])
        assert any("variance near zero" in msg.message for msg in diag.messages)


class TestMultipleBenchmarks:
    def test_spy_and_rsp_both_reported_with_distinct_metrics(self) -> None:
        idx = _weekly_dates(300)
        rng = np.random.default_rng(3)
        port = pd.Series(rng.normal(0.003, 0.015, size=300), index=idx)
        spy = pd.Series(rng.normal(0.001, 0.010, size=300), index=idx)
        rsp = pd.Series(rng.normal(0.002, 0.012, size=300), index=idx)

        out, _ = compute_benchmark_relative_metrics(
            portfolio_returns=port,
            benchmark_returns={"SPY": spy, "RSP": rsp},
        )
        assert set(out.keys()) == {"SPY", "RSP"}
        for ticker in ("SPY", "RSP"):
            m = out[ticker]
            assert m["n_obs"] == 300
            for k in (
                "sharpe_excess",
                "mean_excess_ann",
                "tracking_error_ann",
                "information_ratio",
                "beta",
                "alpha_ann",
            ):
                assert np.isfinite(m[k])
        # Independently-drawn benchmarks → different beta/alpha
        assert out["SPY"]["beta"] != out["RSP"]["beta"]
        assert out["SPY"]["alpha_ann"] != out["RSP"]["alpha_ann"]
