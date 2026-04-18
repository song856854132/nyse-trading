"""Tests for nyse_core.schema -- canonical constants, enums, and column names.

Validates that:
- Constants have expected values matching plan specifications
- Enums contain all expected members with correct string values
- OHLCV_COLUMNS list is complete and ordered
- Risk limits, CV defaults, and cost model constants are correct
"""

from __future__ import annotations

from nyse_core.schema import (
    BASE_SPREAD_BPS,
    BEAR_EXPOSURE,
    BETA_CAP_HIGH,
    BETA_CAP_LOW,
    BULL_EXPOSURE,
    COL_ADJ_CLOSE,
    COL_ADV_20D,
    COL_CLOSE,
    COL_DATE,
    COL_FACTOR,
    COL_FORWARD_RET_5D,
    COL_FORWARD_RET_20D,
    COL_HIGH,
    COL_LOW,
    COL_MARKET_CAP,
    COL_OPEN,
    COL_RANK_PCT,
    COL_REASON,
    COL_SCORE,
    COL_SECTOR,
    COL_SIDE,
    COL_SYMBOL,
    COL_TARGET_SHARES,
    COL_VOLUME,
    COL_WEIGHT,
    DAILY_LOSS_LIMIT,
    DEFAULT_COMMISSION_PER_SHARE,
    DEFAULT_EMBARGO_DAYS,
    DEFAULT_MIN_ADV_20D,
    DEFAULT_MIN_PRICE,
    DEFAULT_PURGE_DAYS,
    DEFAULT_SELL_BUFFER,
    DEFAULT_TEST_MONTHS,
    DEFAULT_TOP_N,
    EARNINGS_EVENT_CAP,
    EARNINGS_EVENT_DAYS,
    EARNINGS_WEEK_MULTIPLIER,
    MAX_PARAMS_WARNING,
    MAX_POSITION_PCT,
    MAX_SECTOR_PCT,
    MIN_TRAIN_YEARS,
    MONDAY_MULTIPLIER,
    OHLCV_COLUMNS,
    POSITION_INERTIA_THRESHOLD,
    SMA_WINDOW,
    STRICT_CALENDAR,
    TRADING_DAYS_PER_YEAR,
    CombinationModelType,
    NormalizationMethod,
    RebalanceFrequency,
    RegimeState,
    Severity,
    Side,
    UsageDomain,
)

# ── Trading Calendar Constants ──────────────────────────────────────────────


class TestTradingCalendar:
    def test_trading_days_per_year(self) -> None:
        assert TRADING_DAYS_PER_YEAR == 252

    def test_strict_calendar_enabled(self) -> None:
        """AP-5: never forward-fill prices by default."""
        assert STRICT_CALENDAR is True


# ── OHLCV Column Constants ──────────────────────────────────────────────────


class TestOHLCVColumns:
    def test_column_count(self) -> None:
        assert len(OHLCV_COLUMNS) == 7

    def test_column_names(self) -> None:
        expected = {"date", "symbol", "open", "high", "low", "close", "volume"}
        assert set(OHLCV_COLUMNS) == expected

    def test_column_order(self) -> None:
        """date and symbol must be first two columns."""
        assert OHLCV_COLUMNS[0] == COL_DATE
        assert OHLCV_COLUMNS[1] == COL_SYMBOL

    def test_adj_close_not_in_ohlcv(self) -> None:
        """adj_close exists as a constant but is not in the base OHLCV list."""
        assert COL_ADJ_CLOSE not in OHLCV_COLUMNS
        assert COL_ADJ_CLOSE == "adj_close"


# ── Risk Limit Constants ────────────────────────────────────────────────────


class TestRiskLimits:
    def test_max_position_pct(self) -> None:
        assert MAX_POSITION_PCT == 0.10

    def test_max_sector_pct(self) -> None:
        assert MAX_SECTOR_PCT == 0.30

    def test_position_inertia_threshold(self) -> None:
        """Carver's 10% relative deviation → 0.5pp for 5% EW target."""
        assert POSITION_INERTIA_THRESHOLD == 0.005

    def test_default_sell_buffer(self) -> None:
        """Lesson_Learn Phase 63 value."""
        assert DEFAULT_SELL_BUFFER == 1.5

    def test_beta_caps_ordered(self) -> None:
        assert BETA_CAP_LOW < BETA_CAP_HIGH
        assert BETA_CAP_LOW == 0.5
        assert BETA_CAP_HIGH == 1.5

    def test_daily_loss_limit_negative(self) -> None:
        assert DAILY_LOSS_LIMIT < 0
        assert DAILY_LOSS_LIMIT == -0.03

    def test_regime_exposure_values(self) -> None:
        assert BULL_EXPOSURE == 1.0
        assert BEAR_EXPOSURE == 0.4
        assert BEAR_EXPOSURE < BULL_EXPOSURE

    def test_sma_window(self) -> None:
        assert SMA_WINDOW == 200

    def test_earnings_event_constraints(self) -> None:
        assert EARNINGS_EVENT_CAP == 0.05
        assert EARNINGS_EVENT_DAYS == 2


# ── Universe Defaults ───────────────────────────────────────────────────────


class TestUniverseDefaults:
    def test_min_price(self) -> None:
        assert DEFAULT_MIN_PRICE == 5.0

    def test_min_adv(self) -> None:
        assert DEFAULT_MIN_ADV_20D == 500_000

    def test_top_n(self) -> None:
        assert DEFAULT_TOP_N == 20


# ── CV Parameter Constants ──────────────────────────────────────────────────


class TestCVDefaults:
    def test_min_train_years(self) -> None:
        assert MIN_TRAIN_YEARS == 2

    def test_purge_days(self) -> None:
        assert DEFAULT_PURGE_DAYS == 5

    def test_embargo_days(self) -> None:
        assert DEFAULT_EMBARGO_DAYS == 5

    def test_test_months(self) -> None:
        assert DEFAULT_TEST_MONTHS == 6

    def test_max_params_warning(self) -> None:
        """AP-7: warn if optimizing > 5 params with limited data."""
        assert MAX_PARAMS_WARNING == 5


# ── Cost Model Constants ────────────────────────────────────────────────────


class TestCostModelDefaults:
    def test_commission(self) -> None:
        assert DEFAULT_COMMISSION_PER_SHARE == 0.005

    def test_base_spread(self) -> None:
        assert BASE_SPREAD_BPS == 10.0

    def test_monday_multiplier(self) -> None:
        assert MONDAY_MULTIPLIER == 1.3

    def test_earnings_week_multiplier(self) -> None:
        assert EARNINGS_WEEK_MULTIPLIER == 1.5


# ── Enums ───────────────────────────────────────────────────────────────────


class TestSideEnum:
    def test_members(self) -> None:
        assert set(Side) == {Side.BUY, Side.SELL, Side.HOLD}

    def test_values(self) -> None:
        assert Side.BUY.value == "BUY"
        assert Side.SELL.value == "SELL"
        assert Side.HOLD.value == "HOLD"


class TestSeverityEnum:
    def test_members(self) -> None:
        assert set(Severity) == {Severity.VETO, Severity.WARNING}

    def test_values(self) -> None:
        assert Severity.VETO.value == "VETO"
        assert Severity.WARNING.value == "WARNING"


class TestUsageDomainEnum:
    def test_members(self) -> None:
        assert set(UsageDomain) == {UsageDomain.SIGNAL, UsageDomain.RISK}

    def test_values(self) -> None:
        assert UsageDomain.SIGNAL.value == "SIGNAL"
        assert UsageDomain.RISK.value == "RISK"


class TestRegimeStateEnum:
    def test_members(self) -> None:
        assert set(RegimeState) == {RegimeState.BULL, RegimeState.BEAR}


class TestRebalanceFrequencyEnum:
    def test_members(self) -> None:
        assert set(RebalanceFrequency) == {
            RebalanceFrequency.WEEKLY,
            RebalanceFrequency.MONTHLY,
        }


class TestCombinationModelTypeEnum:
    def test_members(self) -> None:
        assert set(CombinationModelType) == {
            CombinationModelType.RIDGE,
            CombinationModelType.GBM,
            CombinationModelType.NEURAL,
        }


class TestNormalizationMethodEnum:
    def test_members(self) -> None:
        assert set(NormalizationMethod) == {
            NormalizationMethod.RANK_PERCENTILE,
            NormalizationMethod.WINSORIZE,
            NormalizationMethod.Z_SCORE,
        }


class TestEnumUniqueness:
    """@unique decorator should guarantee no duplicate values."""

    def test_all_enums_have_unique_values(self) -> None:
        for enum_cls in [
            Side,
            Severity,
            UsageDomain,
            RegimeState,
            RebalanceFrequency,
            CombinationModelType,
            NormalizationMethod,
        ]:
            values = [m.value for m in enum_cls]
            assert len(values) == len(set(values)), f"Duplicate in {enum_cls}"


# ── Column Name Consistency ─────────────────────────────────────────────────


class TestColumnNameConsistency:
    def test_all_column_names_are_strings(self) -> None:
        cols = [
            COL_DATE,
            COL_SYMBOL,
            COL_OPEN,
            COL_HIGH,
            COL_LOW,
            COL_CLOSE,
            COL_VOLUME,
            COL_ADJ_CLOSE,
            COL_FACTOR,
            COL_SCORE,
            COL_RANK_PCT,
            COL_FORWARD_RET_5D,
            COL_FORWARD_RET_20D,
            COL_SECTOR,
            COL_MARKET_CAP,
            COL_ADV_20D,
            COL_WEIGHT,
            COL_TARGET_SHARES,
            COL_SIDE,
            COL_REASON,
        ]
        for col in cols:
            assert isinstance(col, str)
            assert len(col) > 0

    def test_no_leading_trailing_whitespace(self) -> None:
        cols = [
            COL_DATE,
            COL_SYMBOL,
            COL_OPEN,
            COL_HIGH,
            COL_LOW,
            COL_CLOSE,
            COL_VOLUME,
            COL_ADJ_CLOSE,
        ]
        for col in cols:
            assert col == col.strip()
