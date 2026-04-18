"""S&P 500 Historical Constituency adapter.

Scrapes Wikipedia for the S&P 500 historical changes table, or falls
back to a CSV file. Returns a DataFrame compatible with
``nyse_core.universe.get_universe_at_date()``.
"""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
import requests

from nyse_core.contracts import Diagnostics
from nyse_core.schema import COL_DATE, COL_SYMBOL

if TYPE_CHECKING:
    from nyse_core.config_schema import ConstituencyConfig

_SRC = "constituency_adapter"

# ── Constituency columns ─────────────────────────────────────────────────────

COL_ACTION = "action"
ACTION_ADD = "ADD"
ACTION_REMOVE = "REMOVE"

_OUTPUT_COLS = [COL_DATE, COL_SYMBOL, COL_ACTION]

_WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


class ConstituencyAdapterError(Exception):
    """Raised when constituency data cannot be loaded from any source."""


class ConstituencyAdapter:
    """Adapter for S&P 500 historical constituency changes.

    Parameters
    ----------
    config : ConstituencyConfig
        Validated constituency configuration from data_sources.yaml.
    session : requests.Session | None
        Optional session for dependency injection / testing.
    """

    def __init__(
        self,
        config: ConstituencyConfig,
        session: requests.Session | None = None,
    ) -> None:
        self._config = config
        self._session = session or requests.Session()

    def _scrape_wikipedia(self, diag: Diagnostics) -> pd.DataFrame:
        """Scrape S&P 500 changes table from Wikipedia.

        The Wikipedia page has a table with columns for Date, Added, Removed.
        """
        diag.info(_SRC, "Attempting Wikipedia scrape for S&P 500 changes")

        resp = self._session.get(_WIKIPEDIA_URL, timeout=30)
        resp.raise_for_status()

        tables = pd.read_html(io.StringIO(resp.text))

        # Find the changes table by looking for one with Added/Removed columns
        changes_table = None
        for tbl in tables:
            cols_lower = [str(c).lower() for c in tbl.columns.tolist()]
            # Flatten MultiIndex columns if present
            if hasattr(tbl.columns, "levels"):
                flat_cols = [
                    " ".join(str(x) for x in col).lower() if isinstance(col, tuple) else str(col).lower()
                    for col in tbl.columns
                ]
                cols_lower = flat_cols
            if any("added" in c for c in cols_lower) and any("removed" in c for c in cols_lower):
                changes_table = tbl
                break

        if changes_table is None:
            diag.warning(_SRC, "Could not find changes table on Wikipedia")
            return pd.DataFrame(columns=_OUTPUT_COLS)

        return self._parse_wikipedia_table(changes_table, diag)

    def _parse_wikipedia_table(self, table: pd.DataFrame, diag: Diagnostics) -> pd.DataFrame:
        """Parse the Wikipedia changes table into canonical format."""
        rows: list[dict[str, Any]] = []

        # Flatten MultiIndex columns if present
        if hasattr(table.columns, "levels"):
            table.columns = [
                " ".join(str(x) for x in col).strip() if isinstance(col, tuple) else str(col)
                for col in table.columns
            ]

        col_names = table.columns.tolist()
        date_col = None
        added_col = None
        removed_col = None

        for c in col_names:
            c_lower = str(c).lower()
            if "date" in c_lower and date_col is None:
                date_col = c
            elif "added" in c_lower and "ticker" in c_lower or "added" in c_lower and added_col is None:
                added_col = c
            elif "removed" in c_lower and "ticker" in c_lower or "removed" in c_lower and removed_col is None:
                removed_col = c

        if date_col is None or (added_col is None and removed_col is None):
            diag.warning(
                _SRC,
                f"Wikipedia table columns not recognized: {col_names}",
            )
            return pd.DataFrame(columns=_OUTPUT_COLS)

        for _, row in table.iterrows():
            try:
                date_val = pd.to_datetime(row[date_col], errors="coerce")
                if pd.isna(date_val):
                    continue
                change_date = date_val.date()

                if added_col is not None:
                    ticker = str(row[added_col]).strip()
                    if ticker and ticker != "nan" and ticker != "":
                        rows.append(
                            {
                                COL_DATE: change_date,
                                COL_SYMBOL: ticker,
                                COL_ACTION: ACTION_ADD,
                            }
                        )

                if removed_col is not None:
                    ticker = str(row[removed_col]).strip()
                    if ticker and ticker != "nan" and ticker != "":
                        rows.append(
                            {
                                COL_DATE: change_date,
                                COL_SYMBOL: ticker,
                                COL_ACTION: ACTION_REMOVE,
                            }
                        )
            except Exception:
                continue

        diag.info(
            _SRC,
            f"Parsed {len(rows)} constituency changes from Wikipedia",
            row_count=len(rows),
        )

        if not rows:
            return pd.DataFrame(columns=_OUTPUT_COLS)
        return pd.DataFrame(rows)[_OUTPUT_COLS]

    def _load_csv_backup(self, diag: Diagnostics) -> pd.DataFrame:
        """Load constituency changes from CSV backup file."""
        csv_path = Path(self._config.csv_path)
        if not csv_path.exists():
            diag.error(
                _SRC,
                f"CSV backup file not found: {csv_path}",
            )
            return pd.DataFrame(columns=_OUTPUT_COLS)

        diag.info(_SRC, f"Loading constituency changes from CSV: {csv_path}")
        df = pd.read_csv(csv_path)

        required = {COL_DATE, COL_SYMBOL, COL_ACTION}
        if not required.issubset(set(df.columns)):
            diag.error(
                _SRC,
                f"CSV missing required columns. Has: {list(df.columns)}, needs: {required}",
            )
            return pd.DataFrame(columns=_OUTPUT_COLS)

        df[COL_DATE] = pd.to_datetime(df[COL_DATE]).dt.date
        df[COL_ACTION] = df[COL_ACTION].str.upper()

        diag.info(
            _SRC,
            f"Loaded {len(df)} constituency changes from CSV",
            row_count=len(df),
        )
        return df[_OUTPUT_COLS]

    def fetch(self, symbols: list[str], start_date: date, end_date: date) -> tuple[pd.DataFrame, Diagnostics]:
        """Fetch S&P 500 constituency changes.

        The *symbols* parameter is ignored; all known changes are returned.
        If Wikipedia scraping fails, falls back to CSV at config.csv_path.

        Returns DataFrame: date, symbol, action ("ADD" or "REMOVE").
        """
        diag = Diagnostics()

        if self._config.source == "wikipedia":
            try:
                df = self._scrape_wikipedia(diag)
                if not df.empty:
                    return df, diag
                diag.warning(
                    _SRC,
                    "Wikipedia scrape returned empty, falling back to CSV",
                )
            except Exception as exc:
                diag.warning(
                    _SRC,
                    f"Wikipedia scrape failed: {exc}, falling back to CSV",
                )

        # Fall back to CSV
        df = self._load_csv_backup(diag)
        return df, diag

    def fetch_incremental(self, symbols: list[str], since: date) -> tuple[pd.DataFrame, Diagnostics]:
        """Incremental fetch -- returns all changes, caller filters by date."""
        return self.fetch(symbols, since, date.today())

    def health_check(self) -> tuple[bool, Diagnostics]:
        """Check if the constituency data source is reachable."""
        diag = Diagnostics()

        if self._config.source == "wikipedia":
            try:
                resp = self._session.get(_WIKIPEDIA_URL, timeout=10)
                healthy = resp.status_code < 500
                if healthy:
                    diag.info(_SRC, "Wikipedia health check passed")
                else:
                    diag.error(
                        _SRC,
                        f"Wikipedia returned status {resp.status_code}",
                    )
                return healthy, diag
            except Exception as exc:
                diag.error(_SRC, f"Wikipedia health check failed: {exc}")

        # Check CSV fallback
        csv_path = Path(self._config.csv_path)
        if csv_path.exists():
            diag.info(_SRC, f"CSV backup exists at {csv_path}")
            return True, diag

        diag.error(_SRC, "No constituency data source available")
        return False, diag
