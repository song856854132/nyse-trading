"""Tests for nyse_ats.data.vendor_registry — config-driven adapter resolution.

Validates:
- from_config() creates correct adapter types for each data source
- register/get mechanics work
- Rate limiters have correct limits from config
- Duplicate registration raises VendorRegistryError
- Unknown adapter lookup raises VendorRegistryError
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from nyse_ats.data.constituency_adapter import ConstituencyAdapter
from nyse_ats.data.edgar_adapter import EdgarAdapter
from nyse_ats.data.finmind_adapter import FinMindAdapter
from nyse_ats.data.finra_adapter import FinraAdapter
from nyse_ats.data.vendor_registry import VendorRegistry, VendorRegistryError
from nyse_core.config_schema import (
    ConstituencyConfig,
    DataSourcesConfig,
    EdgarConfig,
    FinMindConfig,
    FinraConfig,
)


def _make_config() -> DataSourcesConfig:
    return DataSourcesConfig(
        finmind=FinMindConfig(
            base_url="https://api.finmindtrade.com/api/v4",
            token_env_var="FINMIND_API_TOKEN",
            rate_limit_per_minute=30,
            datasets={"ohlcv": "USStockPrice", "info": "USStockInfo"},
            bulk_start_date="2016-01-01",
        ),
        edgar=EdgarConfig(
            base_url="https://efts.sec.gov",
            rate_limit_per_second=10,
            user_agent_env_var="EDGAR_USER_AGENT",
            filing_types=["10-Q", "10-K"],
        ),
        finra=FinraConfig(
            short_interest_url="https://api.finra.org/data/group/otcMarket/name/shortInterest",
            publication_lag_days=11,
            update_frequency="bi-monthly",
        ),
        constituency=ConstituencyConfig(
            source="wikipedia",
            backup_source="manual_csv",
            csv_path="config/sp500_changes.csv",
        ),
    )


def _make_registry() -> VendorRegistry:
    """Create a VendorRegistry via from_config() with mocked env vars."""
    with patch.dict(os.environ, {"EDGAR_USER_AGENT": "TestBot test@example.com"}):
        return VendorRegistry.from_config(_make_config())


# ── Adapter Type Tests ──────────────────────────────────────────────────────


class TestAdapterTypes:
    """from_config() registers the correct adapter for each vendor."""

    def test_finmind_adapter_registered(self) -> None:
        registry = _make_registry()
        adapter = registry.get("finmind")
        assert isinstance(adapter, FinMindAdapter)

    def test_edgar_adapter_registered(self) -> None:
        registry = _make_registry()
        adapter = registry.get("edgar")
        assert isinstance(adapter, EdgarAdapter)

    def test_finra_adapter_registered(self) -> None:
        registry = _make_registry()
        adapter = registry.get("finra")
        assert isinstance(adapter, FinraAdapter)

    def test_constituency_adapter_registered(self) -> None:
        registry = _make_registry()
        adapter = registry.get("constituency")
        assert isinstance(adapter, ConstituencyAdapter)

    def test_four_adapters_registered(self) -> None:
        registry = _make_registry()
        assert len(registry) == 4
        assert set(registry.names) == {"constituency", "edgar", "finmind", "finra"}


# ── Rate Limiter Limits ─────────────────────────────────────────────────────


class TestRateLimiterConfig:
    """Rate limiters are configured from YAML values."""

    def test_finmind_limiter_30_per_minute(self) -> None:
        """FinMind rate limiter: 30 requests per 60 seconds."""
        registry = _make_registry()
        adapter = registry.get("finmind")
        assert isinstance(adapter, FinMindAdapter)
        # The adapter stores its rate limiter; verify indirectly via the adapter
        # The factory uses config.finmind.rate_limit_per_minute=30, window=60s
        assert adapter._rate_limiter.max_requests == 30
        assert adapter._rate_limiter.window_seconds == 60.0

    def test_edgar_limiter_10_per_second(self) -> None:
        """EDGAR rate limiter: 10 requests per 1 second."""
        registry = _make_registry()
        adapter = registry.get("edgar")
        assert isinstance(adapter, EdgarAdapter)
        assert adapter._rate_limiter.max_requests == 10
        assert adapter._rate_limiter.window_seconds == 1.0


# ── Register / Get Mechanics ────────────────────────────────────────────────


class TestRegistryMechanics:
    """register() and get() behavior."""

    def test_contains_check(self) -> None:
        registry = _make_registry()
        assert "finmind" in registry
        assert "nonexistent" not in registry

    def test_get_unknown_raises(self) -> None:
        registry = _make_registry()
        with pytest.raises(VendorRegistryError, match="No adapter registered"):
            registry.get("nonexistent_vendor")

    def test_duplicate_register_raises(self) -> None:
        registry = _make_registry()
        adapter = registry.get("finmind")
        with pytest.raises(VendorRegistryError, match="already registered"):
            registry.register("finmind", adapter)

    def test_names_sorted(self) -> None:
        registry = _make_registry()
        names = registry.names
        assert names == sorted(names)
