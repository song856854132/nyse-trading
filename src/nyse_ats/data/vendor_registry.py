"""Vendor registry -- adapter resolution and lifecycle management.

Stores adapter instances keyed by name and provides a factory method
to create all adapters from a ``DataSourcesConfig``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nyse_ats.data.constituency_adapter import ConstituencyAdapter
from nyse_ats.data.edgar_adapter import EdgarAdapter
from nyse_ats.data.finmind_adapter import FinMindAdapter
from nyse_ats.data.finra_adapter import FinraAdapter
from nyse_ats.data.rate_limiter import SlidingWindowRateLimiter

if TYPE_CHECKING:
    from nyse_ats.data.adapter import DataAdapter
    from nyse_core.config_schema import DataSourcesConfig


class VendorRegistryError(Exception):
    """Raised when adapter lookup or registration fails."""


class VendorRegistry:
    """Registry of data adapters keyed by vendor name.

    Provides registration, retrieval, and a factory to wire up all
    adapters from a single ``DataSourcesConfig`` instance.
    """

    def __init__(self) -> None:
        self._adapters: dict[str, DataAdapter] = {}

    def register(self, name: str, adapter: DataAdapter) -> None:
        """Register an adapter under the given name.

        Parameters
        ----------
        name : str
            Unique vendor name (e.g. "finmind", "edgar").
        adapter : DataAdapter
            An object satisfying the DataAdapter protocol.

        Raises
        ------
        VendorRegistryError
            If *name* is already registered.
        """
        if name in self._adapters:
            raise VendorRegistryError(f"Adapter already registered: '{name}'")
        self._adapters[name] = adapter

    def get(self, name: str) -> DataAdapter:
        """Retrieve a registered adapter by name.

        Raises
        ------
        VendorRegistryError
            If *name* is not registered.
        """
        if name not in self._adapters:
            raise VendorRegistryError(f"No adapter registered with name: '{name}'")
        return self._adapters[name]

    @property
    def names(self) -> list[str]:
        """Return sorted list of registered adapter names."""
        return sorted(self._adapters.keys())

    def __len__(self) -> int:
        return len(self._adapters)

    def __contains__(self, name: str) -> bool:
        return name in self._adapters

    @classmethod
    def from_config(cls, config: DataSourcesConfig) -> VendorRegistry:
        """Factory: create a VendorRegistry with all adapters wired from config.

        Creates rate limiters and adapter instances for:
        - finmind (OHLCV)
        - edgar (fundamentals)
        - finra (short interest)
        - constituency (S&P 500 membership)

        Parameters
        ----------
        config : DataSourcesConfig
            Validated data sources configuration.

        Returns
        -------
        VendorRegistry
            A registry with all four adapters registered.
        """
        registry = cls()

        # FinMind: rate_limit_per_minute -> per-minute window
        finmind_limiter = SlidingWindowRateLimiter(
            max_requests=config.finmind.rate_limit_per_minute,
            window_seconds=60.0,
        )
        registry.register(
            "finmind",
            FinMindAdapter(config.finmind, finmind_limiter),
        )

        # EDGAR: rate_limit_per_second -> per-second window
        edgar_limiter = SlidingWindowRateLimiter(
            max_requests=config.edgar.rate_limit_per_second,
            window_seconds=1.0,
        )
        registry.register(
            "edgar",
            EdgarAdapter(config.edgar, edgar_limiter),
        )

        # FINRA: no explicit rate limit in config, use a conservative default
        finra_limiter = SlidingWindowRateLimiter(
            max_requests=10,
            window_seconds=1.0,
        )
        registry.register(
            "finra",
            FinraAdapter(config.finra, finra_limiter),
        )

        # Constituency: no rate limiter needed
        registry.register(
            "constituency",
            ConstituencyAdapter(config.constituency),
        )

        return registry
