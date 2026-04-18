"""Unit tests for DataQualityChecker (5 OHLCV checks)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from nyse_ats.monitoring.data_quality import DataQualityChecker

# ── Helpers ─────────────────────────────────────────────────────────────────


def _clean_ohlcv(n_days: int = 30, n_symbols: int = 120) -> pd.DataFrame:
    """Generate a clean OHLCV DataFrame that passes all checks."""
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2025-01-01", periods=n_days)
    symbols = [f"SYM{i:04d}" for i in range(n_symbols)]
    rows = []
    for sym in symbols:
        base = rng.uniform(20, 200)
        for d in dates:
            open_ = base * (1 + rng.normal(0, 0.01))
            close = base * (1 + rng.normal(0, 0.01))
            high = max(open_, close) * (1 + abs(rng.normal(0, 0.005)))
            low = min(open_, close) * (1 - abs(rng.normal(0, 0.005)))
            vol = int(rng.integers(100_000, 5_000_000))
            rows.append(
                {
                    "date": d,
                    "symbol": sym,
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": vol,
                }
            )
            base = close  # random walk
    return pd.DataFrame(rows)


# ── Tests ───────────────────────────────────────────────────────────────────


class TestDataQualityChecker:
    def setup_method(self) -> None:
        self.checker = DataQualityChecker()

    # -- All checks pass on clean data ----------------------------------------

    def test_all_pass_clean_data(self) -> None:
        df = _clean_ohlcv()
        results, diag = self.checker.check_all(df)
        assert len(results) == 5
        assert all(r.passed for r in results), [r.check_name for r in results if not r.passed]
        assert not diag.has_errors

    # -- Check 1: Missing dates -----------------------------------------------

    def test_missing_dates_gap_detected(self) -> None:
        dates = pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-10"])
        df = pd.DataFrame(
            {
                "date": dates,
                "symbol": ["A", "A", "A"],
                "close": [100, 101, 102],
            }
        )
        result = self.checker.check_missing_dates(df, max_gap_days=3)
        assert result.passed is False
        assert result.violations >= 1

    def test_missing_dates_no_gap(self) -> None:
        dates = pd.bdate_range("2025-01-01", periods=10)
        df = pd.DataFrame({"date": dates, "symbol": "A", "close": range(10)})
        result = self.checker.check_missing_dates(df)
        assert result.passed is True

    # -- Check 2: OHLCV constraints -------------------------------------------

    def test_ohlcv_high_less_than_close(self) -> None:
        df = pd.DataFrame(
            {
                "open": [100.0],
                "high": [99.0],
                "low": [98.0],
                "close": [100.5],
                "volume": [1000],
            }
        )
        result = self.checker.check_ohlcv_constraints(df)
        assert result.passed is False
        assert result.violations == 1

    def test_ohlcv_negative_volume(self) -> None:
        df = pd.DataFrame(
            {
                "open": [100.0],
                "high": [101.0],
                "low": [99.0],
                "close": [100.5],
                "volume": [-10],
            }
        )
        result = self.checker.check_ohlcv_constraints(df)
        assert result.passed is False

    # -- Check 3: Stale prices ------------------------------------------------

    def test_stale_price_detected(self) -> None:
        dates = pd.bdate_range("2025-01-01", periods=10)
        df = pd.DataFrame(
            {
                "date": dates,
                "symbol": "STALE",
                "close": [50.0] * 10,  # all identical
            }
        )
        result = self.checker.check_stale_prices(df, max_stale_days=5)
        assert result.passed is False
        assert result.violations == 1
        assert result.violation_samples[0]["symbol"] == "STALE"

    def test_no_stale_prices(self) -> None:
        dates = pd.bdate_range("2025-01-01", periods=10)
        df = pd.DataFrame(
            {
                "date": dates,
                "symbol": "OK",
                "close": [50.0 + i * 0.1 for i in range(10)],
            }
        )
        result = self.checker.check_stale_prices(df)
        assert result.passed is True

    # -- Check 4: Price outliers -----------------------------------------------

    def test_price_outlier_detected(self) -> None:
        dates = pd.bdate_range("2025-01-01", periods=3)
        df = pd.DataFrame(
            {
                "date": dates,
                "symbol": "JUMP",
                "close": [100.0, 200.0, 205.0],  # 100% jump day 1→2
            }
        )
        result = self.checker.check_price_outliers(df, max_daily_move=0.50)
        assert result.passed is False
        assert result.violations >= 1

    def test_no_outliers_small_moves(self) -> None:
        dates = pd.bdate_range("2025-01-01", periods=5)
        df = pd.DataFrame(
            {
                "date": dates,
                "symbol": "CALM",
                "close": [100, 101, 99, 100, 98],
            }
        )
        result = self.checker.check_price_outliers(df)
        assert result.passed is True

    # -- Check 5: Universe coverage -------------------------------------------

    def test_universe_coverage_too_few(self) -> None:
        df = pd.DataFrame(
            {
                "date": ["2025-01-02"] * 50,
                "symbol": [f"S{i}" for i in range(50)],
                "close": [100.0] * 50,
            }
        )
        result = self.checker.check_universe_coverage(df, min_symbols=100)
        assert result.passed is False
        assert result.violations == 1

    def test_universe_coverage_enough(self) -> None:
        df = pd.DataFrame(
            {
                "date": ["2025-01-02"] * 150,
                "symbol": [f"S{i}" for i in range(150)],
                "close": [100.0] * 150,
            }
        )
        result = self.checker.check_universe_coverage(df, min_symbols=100)
        assert result.passed is True

    # -- check_all returns all 5 results --------------------------------------

    def test_check_all_returns_five(self) -> None:
        df = _clean_ohlcv(n_days=10, n_symbols=120)
        results, _ = self.checker.check_all(df)
        assert len(results) == 5
        names = {r.check_name for r in results}
        assert names == {
            "missing_dates",
            "ohlcv_constraints",
            "stale_prices",
            "price_outliers",
            "universe_coverage",
        }

    # -- Violation samples populated ------------------------------------------

    def test_violation_samples_populated(self) -> None:
        df = pd.DataFrame(
            {
                "open": [100.0, 100.0],
                "high": [99.0, 99.0],  # both violate high < close
                "low": [98.0, 98.0],
                "close": [100.5, 100.5],
                "volume": [1000, 1000],
            }
        )
        result = self.checker.check_ohlcv_constraints(df)
        assert result.violations == 2
        assert len(result.violation_samples) == 2
