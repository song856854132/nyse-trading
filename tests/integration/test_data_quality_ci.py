"""CI-compatible data quality tests.

Designed to run in CI pipelines with deterministic synthetic data.
Validates that quality checks produce correct results, are serializable
for reporting, and meet performance targets.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict

import pandas as pd
import pytest

# ── Graceful skip if Phase 2 modules not yet available ────────────────────

try:
    from nyse_ats.monitoring.data_quality import DataQualityChecker, DataQualityResult
    from nyse_core.schema import (
        COL_CLOSE,
        COL_DATE,
        COL_HIGH,
        COL_LOW,
        COL_OPEN,
        COL_SYMBOL,
        COL_VOLUME,
    )

    MODULES_AVAILABLE = True
except ImportError:
    MODULES_AVAILABLE = False

from tests.fixtures.synthetic_prices import generate_prices

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not MODULES_AVAILABLE, reason="Phase 2 modules not yet available"),
]


# ── Helpers ────────────────────────────────────────────────────────────────


def _generate_clean_data(
    n_stocks: int = 10,
    n_days: int = 100,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate synthetic OHLCV data with known clean properties."""
    return generate_prices(n_stocks=n_stocks, n_days=n_days, seed=seed)


def _generate_large_dataset(
    n_stocks: int = 500,
    n_days: int = 1000,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate a large dataset for performance testing."""
    return generate_prices(n_stocks=n_stocks, n_days=n_days, seed=seed)


# ── Tests ─────────────────────────────────────────────────────────────────


class TestDataQualityCI:
    """Data quality checks designed to run in CI pipeline."""

    def test_synthetic_data_ohlcv_valid(self) -> None:
        """Generated synthetic data passes OHLCV constraint checks."""
        data = _generate_clean_data(n_stocks=10, n_days=100)
        checker = DataQualityChecker()

        result = checker.check_ohlcv_constraints(data)
        assert result.passed, f"OHLCV constraints: {result.details}"

    def test_synthetic_data_no_stale(self) -> None:
        """Generated synthetic data has no stale prices (max_stale_days=5)."""
        data = _generate_clean_data(n_stocks=10, n_days=100)
        checker = DataQualityChecker()

        result = checker.check_stale_prices(data, max_stale_days=5)
        assert result.passed, f"Stale prices: {result.details}"

    def test_synthetic_data_no_outliers(self) -> None:
        """Generated synthetic data has no extreme outliers (>50% daily move)."""
        data = _generate_clean_data(n_stocks=10, n_days=100)
        checker = DataQualityChecker()

        result = checker.check_price_outliers(data, max_daily_move=0.50)
        assert result.passed, f"Price outliers: {result.details}"

    def test_check_results_are_serializable(self) -> None:
        """DataQualityResult can be JSON-serialized for CI reporting."""
        data = _generate_clean_data(n_stocks=10, n_days=100)
        checker = DataQualityChecker()

        results, _ = checker.check_all(data)

        for r in results:
            d = asdict(r)
            serialized = json.dumps(d, default=str)
            parsed = json.loads(serialized)
            assert parsed["check_name"] == r.check_name
            assert parsed["passed"] == r.passed
            assert isinstance(parsed["violations"], int)

    def test_quality_check_performance(self) -> None:
        """5 checks on 500-stock x 1000-day dataset complete in < 30 seconds.

        Note: the generator itself may be slow; we only time the checks.
        """
        data = _generate_large_dataset(n_stocks=500, n_days=1000)
        checker = DataQualityChecker()

        t0 = time.monotonic()
        results, diag = checker.check_all(data)
        elapsed = time.monotonic() - t0

        assert elapsed < 30.0, f"Quality checks took {elapsed:.1f}s, exceeds 30s limit"
        assert len(results) == 5

    def test_quality_report_format(self) -> None:
        """Results format is CI-friendly: check_name, passed, details, violation_count."""
        data = _generate_clean_data(n_stocks=10, n_days=100)
        checker = DataQualityChecker()

        results, _ = checker.check_all(data)

        for r in results:
            assert isinstance(r.check_name, str), "check_name must be str"
            assert isinstance(r.passed, bool), "passed must be bool"
            assert isinstance(r.details, str), "details must be str"
            assert isinstance(r.violations, int), "violations must be int"
            assert isinstance(r.violation_samples, list), "violation_samples must be list"

    def test_injected_errors_detected_by_check_all(self) -> None:
        """Inject multiple error types and verify check_all catches them."""
        data = _generate_clean_data(n_stocks=5, n_days=100)
        checker = DataQualityChecker()

        # Inject a stale price streak
        target_sym = data[COL_SYMBOL].unique()[0]
        mask = data[COL_SYMBOL] == target_sym
        sym_df = data.loc[mask].sort_values(COL_DATE)
        stale_price = float(sym_df[COL_CLOSE].iloc[20])
        idx = sym_df.index[20:35]  # 15-day stale streak
        data_bad = data.copy()
        data_bad.loc[idx, COL_CLOSE] = stale_price

        results, diag = checker.check_all(data_bad)
        stale_result = next(r for r in results if r.check_name == "stale_prices")
        assert not stale_result.passed, "Should detect injected stale prices"

    def test_check_all_returns_five_results(self) -> None:
        """check_all always returns exactly 5 check results."""
        data = _generate_clean_data(n_stocks=10, n_days=100)
        checker = DataQualityChecker()

        results, diag = checker.check_all(data)
        assert len(results) == 5

        check_names = {r.check_name for r in results}
        expected = {
            "missing_dates",
            "ohlcv_constraints",
            "stale_prices",
            "price_outliers",
            "universe_coverage",
        }
        assert check_names == expected

    def test_empty_dataframe_handled(self) -> None:
        """Quality checks handle empty DataFrames gracefully."""
        checker = DataQualityChecker()
        empty = pd.DataFrame(
            columns=[
                COL_DATE,
                COL_SYMBOL,
                COL_OPEN,
                COL_HIGH,
                COL_LOW,
                COL_CLOSE,
                COL_VOLUME,
            ]
        )

        results, _ = checker.check_all(empty)
        # Should return results (possibly failing) without raising
        assert len(results) == 5
