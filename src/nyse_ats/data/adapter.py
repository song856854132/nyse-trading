"""DataAdapter Protocol -- abstract interface for all data source adapters.

Every adapter in nyse_ats.data implements this protocol. The fetch() and
fetch_incremental() methods return DataFrames with canonical column names from
nyse_core.schema (COL_DATE, COL_SYMBOL, etc.) alongside Diagnostics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from datetime import date

    import pandas as pd

    from nyse_core.contracts import Diagnostics


@runtime_checkable
class DataAdapter(Protocol):
    """Protocol that all data adapters must satisfy.

    All methods return ``(result, Diagnostics)`` tuples for full traceability.
    DataFrames use canonical column names from ``nyse_core.schema``.
    """

    def fetch(self, symbols: list[str], start_date: date, end_date: date) -> tuple[pd.DataFrame, Diagnostics]:
        """Fetch data for specific symbols over a date range.

        Returns a DataFrame with canonical column names from nyse_core.schema.
        """
        ...

    def fetch_incremental(self, symbols: list[str], since: date) -> tuple[pd.DataFrame, Diagnostics]:
        """Incremental fetch for daily updates since *since*.

        Returns a DataFrame with canonical column names from nyse_core.schema.
        """
        ...

    def health_check(self) -> tuple[bool, Diagnostics]:
        """Return ``(True, diag)`` if the upstream API is reachable and responding."""
        ...
