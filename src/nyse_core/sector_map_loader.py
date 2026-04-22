"""Pure loader for the static GICS-sector reference CSV.

Why a dedicated loader?
-----------------------
Both ``benchmark_construction.compute_sector_neutral_returns`` (iter-2) and
``attribution.compute_factor_sector_attribution`` (pre-existing) consume a
``pd.Series`` mapping symbol → sector string. The sector data itself is
sourced once by ``scripts/fetch_gics_sectors.py`` and committed as
``config/gics_sectors_sp500.csv``.

This module provides a thin, pure loader that reads the committed CSV. It
handles comment-prefixed header lines (provenance metadata) and returns
a ``(Series, Diagnostics)`` tuple so every downstream caller follows the
project-wide ``(result, Diagnostics)`` contract.

The loader does **not** fetch, scrape, or network. Runtime code reading a
moving sector_map would be an AP-6 violation waiting to happen — freezing
the map at commit time is a deliberate design choice.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from nyse_core.contracts import Diagnostics

if TYPE_CHECKING:
    from pathlib import Path

_SRC = "sector_map_loader"


def load_gics_sectors(csv_path: Path) -> tuple[pd.Series, Diagnostics]:
    """Load the symbol→GICS-sector map from the committed static CSV.

    Parameters
    ----------
    csv_path
        Path to the CSV file produced by ``scripts/fetch_gics_sectors.py``.
        Lines beginning with ``#`` are treated as comments and skipped. The
        data table must have at least ``symbol`` and ``gics_sector`` columns.

    Returns
    -------
    tuple[pd.Series, Diagnostics]
        Series indexed by symbol (string) with values the GICS sector
        (string). Name of the Series is ``"gics_sector"``. Diagnostics
        carries the row count, sector count, and any warnings about missing
        or duplicate symbols.
    """
    diag = Diagnostics()

    if not csv_path.exists():
        diag.warning(
            _SRC,
            f"sector CSV not found at {csv_path} — returning empty sector map",
            path=str(csv_path),
        )
        return pd.Series(dtype=str, name="gics_sector"), diag

    df = pd.read_csv(csv_path, comment="#")

    required_cols = {"symbol", "gics_sector"}
    missing = required_cols - set(df.columns)
    if missing:
        diag.warning(
            _SRC,
            f"sector CSV missing required columns: {sorted(missing)} — returning empty map",
            missing_cols=sorted(missing),
        )
        return pd.Series(dtype=str, name="gics_sector"), diag

    df["symbol"] = df["symbol"].astype(str).str.strip()

    n_dup = int(df["symbol"].duplicated().sum())
    if n_dup:
        diag.warning(
            _SRC,
            f"sector CSV has {n_dup} duplicated symbols — keeping first occurrence",
            n_duplicates=n_dup,
        )
        df = df.drop_duplicates(subset="symbol", keep="first")

    n_nan_sector = int(df["gics_sector"].isna().sum())
    if n_nan_sector:
        diag.info(
            _SRC,
            f"{n_nan_sector} rows have NaN sector — kept as-is (caller filters)",
            n_nan_sector=n_nan_sector,
        )

    s = df.set_index("symbol")["gics_sector"]
    s.name = "gics_sector"

    diag.info(
        _SRC,
        "gics_sectors loaded",
        n_symbols=int(len(s)),
        n_sectors=int(s.nunique(dropna=True)),
        path=str(csv_path),
    )
    return s, diag
