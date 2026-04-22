"""Fetch current S&P 500 GICS sector assignments and persist as a static CSV.

Provenance note (AP-6 safe)
--------------------------
This script is **NOT** part of the factor-screening runtime. It is a one-shot
data-sourcing utility whose output — ``config/gics_sectors_sp500.csv`` — is
committed to the repository. That committed CSV is the sole input to the
pure-logic ``src/nyse_core/sector_map_loader.py::load_gics_sectors`` loader.

Why scrape Wikipedia once and commit the CSV, rather than fetch at runtime?

* **Reproducibility.** The Wikipedia page updates as S&P changes its index.
  A runtime scrape would silently change the sector_map between re-screens,
  producing a different sector-neutral benchmark or Brinson attribution —
  which would be an AP-6 violation (post-hoc methodology change). The static
  CSV freezes the map at a specific date (``fetched_at``) and requires an
  explicit re-run of this script + commit to change it.

* **PiT caveat.** The table reflects *current* S&P 500 membership and GICS
  assignments. Between 2016-2023 several reclassifications occurred — most
  notably the September 2018 Communication Services creation that split off
  parts of Tech and Consumer Discretionary. Using the current map for
  pre-2018 diagnostics is a known approximation. It is acceptable for
  a *diagnostic* benchmark (iter-2) and a *diagnostic* Brinson decomposition
  (iter-3); it would NOT be acceptable for a gated admission metric.

* **Network-free runtime.** Every downstream module reads the CSV, never
  the web. The runtime has no dependency on Wikipedia being up.

Usage
-----
    python3 scripts/fetch_gics_sectors.py

Writes ``config/gics_sectors_sp500.csv`` with a leading comment header
carrying provenance and a ``fetched_at`` ISO 8601 timestamp.
"""

from __future__ import annotations

import sys
import urllib.request
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

import pandas as pd

_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
_OUT = Path(__file__).resolve().parent.parent / "config" / "gics_sectors_sp500.csv"


def main() -> int:
    req = urllib.request.Request(_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8")

    tables = pd.read_html(StringIO(html))
    if not tables or tables[0].shape[1] < 4:
        print("ERROR: Wikipedia table 0 not shaped as expected.", file=sys.stderr)
        return 1

    sp = tables[0][["Symbol", "Security", "GICS Sector", "GICS Sub-Industry"]].copy()
    sp.columns = ["symbol", "security", "gics_sector", "gics_sub_industry"]
    sp["symbol"] = sp["symbol"].astype(str).str.strip()
    sp = sp.sort_values("symbol").reset_index(drop=True)

    fetched_at = datetime.now(UTC).isoformat(timespec="seconds")
    header = (
        f"# gics_sectors_sp500.csv\n"
        f"# source      : {_URL}\n"
        f"# fetched_at  : {fetched_at}\n"
        f"# n_rows      : {len(sp)}\n"
        f"# n_sectors   : {sp['gics_sector'].nunique()}\n"
        f"# NOTE: current S&P 500 membership + GICS. For 2016-2023 diagnostics\n"
        f"#       (iter-2 sector-neutral benchmark, iter-3 Brinson attribution),\n"
        f"#       this is a PiT approximation — notably Communication Services\n"
        f"#       did not exist before Sep 2018. Acceptable for diagnostics only.\n"
    )

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    with _OUT.open("w", encoding="utf-8") as f:
        f.write(header)
        sp.to_csv(f, index=False)
    print(f"wrote {_OUT} ({len(sp)} symbols, {sp['gics_sector'].nunique()} sectors, fetched_at={fetched_at})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
