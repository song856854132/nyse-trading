"""Unit tests for FactorRegistry — registration, domain enforcement, compute_all."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from nyse_core.contracts import Diagnostics
from nyse_core.features.registry import DoubleDipError, FactorRegistry
from nyse_core.schema import UsageDomain

# ── Helpers ──────────────────────────────────────────────────────────────────


def _dummy_factor_pos(data: pd.DataFrame) -> tuple[pd.Series, Diagnostics]:
    """Dummy +1 factor: returns column 'a' as-is."""
    diag = Diagnostics()
    diag.info("dummy_pos", "computed")
    return data["a"], diag


def _dummy_factor_neg(data: pd.DataFrame) -> tuple[pd.Series, Diagnostics]:
    """Dummy -1 factor: returns column 'b' as-is (registry inverts)."""
    diag = Diagnostics()
    diag.info("dummy_neg", "computed")
    return data["b"], diag


def _make_data() -> pd.DataFrame:
    return pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [10.0, 20.0, 30.0]})


# ── Registration ─────────────────────────────────────────────────────────────


class TestRegistration:
    def test_register_single_factor(self) -> None:
        reg = FactorRegistry()
        reg.register("alpha", _dummy_factor_pos, UsageDomain.SIGNAL, +1, "test alpha")
        assert reg.get_signal_factors() == ["alpha"]
        assert reg.get_risk_factors() == []

    def test_register_risk_factor(self) -> None:
        reg = FactorRegistry()
        reg.register("beta_exp", _dummy_factor_neg, UsageDomain.RISK, -1, "beta exposure")
        assert reg.get_risk_factors() == ["beta_exp"]
        assert reg.get_signal_factors() == []

    def test_register_multiple_factors(self) -> None:
        reg = FactorRegistry()
        reg.register("f1", _dummy_factor_pos, UsageDomain.SIGNAL, +1)
        reg.register("f2", _dummy_factor_neg, UsageDomain.RISK, -1)
        reg.register("f3", _dummy_factor_pos, UsageDomain.SIGNAL, +1)
        assert sorted(reg.get_signal_factors()) == ["f1", "f3"]
        assert reg.get_risk_factors() == ["f2"]


# ── Error Cases ──────────────────────────────────────────────────────────────


class TestRegistrationErrors:
    def test_duplicate_name_raises_value_error(self) -> None:
        reg = FactorRegistry()
        reg.register("alpha", _dummy_factor_pos, UsageDomain.SIGNAL, +1)
        with pytest.raises(ValueError, match="already registered"):
            reg.register("alpha", _dummy_factor_pos, UsageDomain.SIGNAL, +1)

    def test_double_dip_raises_error(self) -> None:
        """AP-3: same factor in SIGNAL then RISK must raise DoubleDipError."""
        reg = FactorRegistry()
        reg.register("ivol", _dummy_factor_neg, UsageDomain.SIGNAL, -1)

        # Remove from internal dict to simulate re-registration attempt
        # while domain_map still tracks it
        del reg._factors["ivol"]

        with pytest.raises(DoubleDipError, match="AP-3"):
            reg.register("ivol", _dummy_factor_neg, UsageDomain.RISK, -1)

    def test_double_dip_error_is_exception(self) -> None:
        assert issubclass(DoubleDipError, Exception)


# ── compute_all ──────────────────────────────────────────────────────────────


class TestComputeAll:
    def test_basic_compute_all(self) -> None:
        reg = FactorRegistry()
        reg.register("f_pos", _dummy_factor_pos, UsageDomain.SIGNAL, +1)
        data = _make_data()
        result, diag = reg.compute_all(data, date(2025, 1, 15))

        assert "f_pos" in result.columns
        pd.testing.assert_series_equal(result["f_pos"], data["a"], check_names=False)
        assert not diag.has_errors

    def test_sign_inversion_for_negative_convention(self) -> None:
        reg = FactorRegistry()
        reg.register("f_neg", _dummy_factor_neg, UsageDomain.SIGNAL, -1)
        data = _make_data()
        result, diag = reg.compute_all(data, date(2025, 1, 15))

        # The registry should negate column 'b'
        expected = -data["b"]
        pd.testing.assert_series_equal(result["f_neg"], expected, check_names=False)

    def test_compute_all_returns_diagnostics(self) -> None:
        reg = FactorRegistry()
        reg.register("f1", _dummy_factor_pos, UsageDomain.SIGNAL, +1)
        _, diag = reg.compute_all(_make_data(), date(2025, 1, 15))

        # Should have at least the factor diag + the assembly diag
        assert len(diag.messages) >= 2

    def test_compute_all_empty_registry(self) -> None:
        reg = FactorRegistry()
        result, diag = reg.compute_all(_make_data(), date(2025, 1, 15))

        assert result.empty or len(result.columns) == 0
        assert not diag.has_errors

    def test_compute_all_multiple_factors(self) -> None:
        reg = FactorRegistry()
        reg.register("f_pos", _dummy_factor_pos, UsageDomain.SIGNAL, +1)
        reg.register("f_neg", _dummy_factor_neg, UsageDomain.RISK, -1)
        data = _make_data()
        result, diag = reg.compute_all(data, date(2025, 1, 15))

        assert set(result.columns) == {"f_pos", "f_neg"}
        # f_pos should be unchanged, f_neg should be negated
        np.testing.assert_array_equal(result["f_pos"].values, data["a"].values)
        np.testing.assert_array_equal(result["f_neg"].values, -data["b"].values)


# ── Factor fault tolerance (Fix 4: registry catches exceptions) ────────────


def _crashing_factor(data: pd.DataFrame) -> tuple[pd.Series, Diagnostics]:
    """Factor that always raises."""
    raise ZeroDivisionError("deliberate crash")


class TestComputeAllFaultTolerance:
    def test_exception_in_compute_fn_is_caught(self) -> None:
        """A crashing compute_fn must not kill compute_all."""
        reg = FactorRegistry()
        reg.register("bad", _crashing_factor, UsageDomain.SIGNAL, +1)
        result, diag = reg.compute_all(_make_data(), date(2025, 1, 15))

        # The crashing factor should be absent from results
        assert "bad" not in result.columns
        # An ERROR diagnostic must be logged
        assert diag.has_errors
        err_msgs = [m for m in diag.messages if m.level.value == "ERROR"]
        assert any("ZeroDivisionError" in m.message for m in err_msgs)

    def test_continues_after_exception(self) -> None:
        """Other factors should still compute when one crashes."""
        reg = FactorRegistry()
        reg.register("good", _dummy_factor_pos, UsageDomain.SIGNAL, +1)
        reg.register("bad", _crashing_factor, UsageDomain.SIGNAL, +1)
        data = _make_data()
        result, diag = reg.compute_all(data, date(2025, 1, 15))

        assert "good" in result.columns
        assert "bad" not in result.columns
        pd.testing.assert_series_equal(result["good"], data["a"], check_names=False)


# ── Multi-dataset routing ──────────────────────────────────────────────────


def _fundamentals_factor(data: pd.DataFrame) -> tuple[pd.Series, Diagnostics]:
    """Factor requiring 'fundamentals' data source."""
    diag = Diagnostics()
    diag.info("fund_factor", "computed from fundamentals")
    return data["roe"], diag


class TestMultiDatasetRouting:
    def test_factor_gets_correct_data_source(self) -> None:
        """Factors with data_source='fundamentals' receive fundamentals DataFrame."""
        reg = FactorRegistry()
        reg.register(
            "ohlcv_f",
            _dummy_factor_pos,
            UsageDomain.SIGNAL,
            +1,
            data_source="ohlcv",
        )
        reg.register(
            "fund_f",
            _fundamentals_factor,
            UsageDomain.SIGNAL,
            +1,
            data_source="fundamentals",
        )

        ohlcv = _make_data()
        fundamentals = pd.DataFrame({"roe": [0.1, 0.2, 0.3]})
        data_sources = {"ohlcv": ohlcv, "fundamentals": fundamentals}

        result, diag = reg.compute_all(data_sources, date(2025, 1, 15))
        assert "ohlcv_f" in result.columns
        assert "fund_f" in result.columns
        assert not diag.has_errors

    def test_missing_data_source_logs_warning(self) -> None:
        """Factor with missing data_source is skipped with a WARNING."""
        reg = FactorRegistry()
        reg.register(
            "needs_missing",
            _dummy_factor_pos,
            UsageDomain.SIGNAL,
            +1,
            data_source="short_interest",
        )
        result, diag = reg.compute_all({"ohlcv": _make_data()}, date(2025, 1, 15))

        assert "needs_missing" not in result.columns
        assert diag.has_warnings
