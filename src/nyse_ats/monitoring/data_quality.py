"""Five automated data quality checks for OHLCV data (CI-compatible).

Each check returns a :class:`DataQualityResult` with pass/fail, violation
count, and up to 5 sample violations for debugging.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from nyse_core.contracts import Diagnostics
from nyse_core.schema import (
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_SYMBOL,
    COL_VOLUME,
)

_SRC = "monitoring.data_quality"


@dataclass
class DataQualityResult:
    """Outcome of a single data quality check."""

    check_name: str
    passed: bool
    details: str
    violations: int = 0
    violation_samples: list[dict] = field(default_factory=list)


class DataQualityChecker:
    """Five automated data quality checks for OHLCV data."""

    def check_all(
        self,
        data: pd.DataFrame,
    ) -> tuple[list[DataQualityResult], Diagnostics]:
        """Run all 5 checks and return results + diagnostics."""
        diag = Diagnostics()
        results = [
            self.check_missing_dates(data),
            self.check_ohlcv_constraints(data),
            self.check_stale_prices(data),
            self.check_price_outliers(data),
            self.check_universe_coverage(data),
        ]
        passed = sum(1 for r in results if r.passed)
        diag.info(_SRC, f"Data quality: {passed}/{len(results)} checks passed.")
        for r in results:
            if not r.passed:
                diag.warning(_SRC, f"FAIL: {r.check_name} - {r.details}")
        return results, diag

    # ── Check 1: Missing trading days ───────────────────────────────────────

    def check_missing_dates(
        self,
        data: pd.DataFrame,
        max_gap_days: int = 3,
    ) -> DataQualityResult:
        """No gaps > *max_gap_days* business days in the date column."""
        name = "missing_dates"
        if COL_DATE not in data.columns:
            return DataQualityResult(name, False, f"Column '{COL_DATE}' missing.", 1)

        dates = pd.to_datetime(data[COL_DATE]).drop_duplicates().sort_values().reset_index(drop=True)
        if len(dates) < 2:
            return DataQualityResult(name, True, "Fewer than 2 dates; nothing to check.")

        diffs = dates.diff().dropna()
        gaps = diffs[diffs > pd.Timedelta(days=max_gap_days)]
        violations = len(gaps)
        samples = [
            {
                "gap_start": str(dates.loc[i - 1].date()),
                "gap_end": str(dates.loc[i].date()),
                "business_days": int(diffs.loc[i].days),
            }
            for i in gaps.index[:5]
        ]
        passed = violations == 0
        detail = f"{violations} gap(s) > {max_gap_days} days." if not passed else "No gaps detected."
        return DataQualityResult(name, passed, detail, violations, samples)

    # ── Check 2: OHLCV constraints ──────────────────────────────────────────

    def check_ohlcv_constraints(self, data: pd.DataFrame) -> DataQualityResult:
        """high >= max(open, close), low <= min(open, close), volume >= 0."""
        name = "ohlcv_constraints"
        required = {COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE, COL_VOLUME}
        missing = required - set(data.columns)
        if missing:
            return DataQualityResult(name, False, f"Missing columns: {missing}", 1)

        high_ok = data[COL_HIGH] >= data[[COL_OPEN, COL_CLOSE]].max(axis=1)
        low_ok = data[COL_LOW] <= data[[COL_OPEN, COL_CLOSE]].min(axis=1)
        vol_ok = data[COL_VOLUME] >= 0

        mask = ~(high_ok & low_ok & vol_ok)
        violations = int(mask.sum())
        bad = data.loc[mask].head(5)
        samples = bad.to_dict(orient="records") if len(bad) > 0 else []
        passed = violations == 0
        detail = f"{violations} row(s) violate OHLCV constraints." if not passed else "All rows valid."
        return DataQualityResult(name, passed, detail, violations, samples)

    # ── Check 3: Stale prices ───────────────────────────────────────────────

    def check_stale_prices(
        self,
        data: pd.DataFrame,
        max_stale_days: int = 5,
    ) -> DataQualityResult:
        """No symbol has identical close for > *max_stale_days* consecutive days."""
        name = "stale_prices"
        if COL_SYMBOL not in data.columns or COL_CLOSE not in data.columns:
            return DataQualityResult(name, False, f"Requires '{COL_SYMBOL}' and '{COL_CLOSE}'.", 1)

        df = data.sort_values([COL_SYMBOL, COL_DATE]) if COL_DATE in data.columns else data.copy()

        violations = 0
        samples: list[dict] = []

        for symbol, group in df.groupby(COL_SYMBOL):
            closes = group[COL_CLOSE].values
            if len(closes) < max_stale_days + 1:
                continue
            streak = 1
            max_streak = 1
            for i in range(1, len(closes)):
                if closes[i] == closes[i - 1]:
                    streak += 1
                    max_streak = max(max_streak, streak)
                else:
                    streak = 1
            if max_streak > max_stale_days:
                violations += 1
                if len(samples) < 5:
                    samples.append({"symbol": str(symbol), "max_streak": max_streak})

        passed = violations == 0
        detail = (
            f"{violations} symbol(s) have stale prices (>{max_stale_days} identical closes)."
            if not passed
            else "No stale prices detected."
        )
        return DataQualityResult(name, passed, detail, violations, samples)

    # ── Check 4: Price outliers ─────────────────────────────────────────────

    def check_price_outliers(
        self,
        data: pd.DataFrame,
        max_daily_move: float = 0.50,
    ) -> DataQualityResult:
        """No single-day return exceeds *max_daily_move* (50% default)."""
        name = "price_outliers"
        if COL_SYMBOL not in data.columns or COL_CLOSE not in data.columns:
            return DataQualityResult(name, False, f"Requires '{COL_SYMBOL}' and '{COL_CLOSE}'.", 1)

        df = data.sort_values([COL_SYMBOL, COL_DATE]) if COL_DATE in data.columns else data.copy()

        violations = 0
        samples: list[dict] = []

        for symbol, group in df.groupby(COL_SYMBOL):
            closes = group[COL_CLOSE].values
            if len(closes) < 2:
                continue
            rets = np.diff(closes) / closes[:-1]
            outlier_idx = np.where(np.abs(rets) > max_daily_move)[0]
            for idx in outlier_idx:
                violations += 1
                if len(samples) < 5:
                    sample: dict = {"symbol": str(symbol), "return": float(rets[idx])}
                    if COL_DATE in group.columns:
                        dates_arr = group[COL_DATE].values
                        sample["date"] = str(dates_arr[idx + 1])
                    samples.append(sample)

        passed = violations == 0
        detail = (
            f"{violations} day(s) with |return| > {max_daily_move:.0%}."
            if not passed
            else "No outlier returns detected."
        )
        return DataQualityResult(name, passed, detail, violations, samples)

    # ── Check 5: Universe coverage ──────────────────────────────────────────

    def check_universe_coverage(
        self,
        data: pd.DataFrame,
        min_symbols: int = 100,
    ) -> DataQualityResult:
        """At least *min_symbols* symbols present per date."""
        name = "universe_coverage"
        if COL_DATE not in data.columns or COL_SYMBOL not in data.columns:
            return DataQualityResult(
                name,
                False,
                f"Requires '{COL_DATE}' and '{COL_SYMBOL}'.",
                1,
            )

        counts = data.groupby(COL_DATE)[COL_SYMBOL].nunique()
        under = counts[counts < min_symbols]
        violations = len(under)
        samples = [{"date": str(dt), "symbol_count": int(cnt)} for dt, cnt in under.head(5).items()]
        passed = violations == 0
        detail = (
            f"{violations} date(s) with fewer than {min_symbols} symbols."
            if not passed
            else f"All dates have >= {min_symbols} symbols."
        )
        return DataQualityResult(name, passed, detail, violations, samples)
