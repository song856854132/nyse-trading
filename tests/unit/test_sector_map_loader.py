"""Unit tests for ``nyse_core.sector_map_loader.load_gics_sectors``.

The loader is trivial by design — its correctness reduces to:

* Reads comment-prefixed CSV (``#``-lines skipped)
* Returns Series indexed by symbol, named ``gics_sector``
* Missing file → warning + empty Series
* Missing required columns → warning + empty Series
* Duplicate symbols → warning + first-wins deduplication
* NaN sector values pass through (caller decides filtering)
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from nyse_core.sector_map_loader import load_gics_sectors


def _write_csv(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


class TestHappyPath:
    def test_reads_provenance_commented_csv(self, tmp_path: Path) -> None:
        csv = tmp_path / "sectors.csv"
        _write_csv(
            csv,
            "# source: wiki\n# fetched_at: 2026-04-22\nsymbol,gics_sector\nAAPL,Information Technology\nJPM,Financials\nXOM,Energy\n",
        )
        s, diag = load_gics_sectors(csv)

        assert isinstance(s, pd.Series)
        assert s.name == "gics_sector"
        assert list(s.index) == ["AAPL", "JPM", "XOM"]
        assert s["AAPL"] == "Information Technology"
        assert s["JPM"] == "Financials"
        assert s["XOM"] == "Energy"
        assert any("gics_sectors loaded" in m.message for m in diag.messages)

    def test_keeps_extra_columns_ignored(self, tmp_path: Path) -> None:
        csv = tmp_path / "sectors.csv"
        _write_csv(
            csv,
            "symbol,security,gics_sector,gics_sub_industry\nAAPL,Apple,Information Technology,Hardware\nJPM,JPMorgan,Financials,Banks\n",
        )
        s, _ = load_gics_sectors(csv)
        assert len(s) == 2
        assert s["JPM"] == "Financials"


class TestDegenerateInputs:
    def test_missing_file_returns_empty_series_with_warning(self, tmp_path: Path) -> None:
        missing = tmp_path / "does_not_exist.csv"
        s, diag = load_gics_sectors(missing)
        assert s.empty
        assert s.name == "gics_sector"
        assert any("sector CSV not found" in m.message for m in diag.messages)

    def test_missing_required_columns_returns_empty_with_warning(self, tmp_path: Path) -> None:
        csv = tmp_path / "bad.csv"
        # Missing gics_sector column.
        _write_csv(csv, "symbol,security\nAAPL,Apple\n")
        s, diag = load_gics_sectors(csv)
        assert s.empty
        assert any("missing required columns" in m.message for m in diag.messages)


class TestDuplicatesAndNaN:
    def test_duplicate_symbols_keep_first_with_warning(self, tmp_path: Path) -> None:
        csv = tmp_path / "sectors.csv"
        _write_csv(
            csv,
            "symbol,gics_sector\nAAPL,Information Technology\nAAPL,Consumer Discretionary\nJPM,Financials\n",
        )
        s, diag = load_gics_sectors(csv)
        assert len(s) == 2
        assert s["AAPL"] == "Information Technology"
        assert any("duplicated symbols" in m.message for m in diag.messages)

    def test_nan_sector_values_preserved(self, tmp_path: Path) -> None:
        csv = tmp_path / "sectors.csv"
        _write_csv(csv, "symbol,gics_sector\nAAPL,Information Technology\nUNKN,\n")
        s, diag = load_gics_sectors(csv)
        assert len(s) == 2
        assert s["AAPL"] == "Information Technology"
        assert pd.isna(s["UNKN"])
        assert any("NaN sector" in m.message for m in diag.messages)


class TestAgainstCommittedArtifact:
    def test_production_csv_loads_and_covers_iter0_universe(self) -> None:
        """Guard against accidental deletion or corruption of the committed CSV."""
        csv = Path(__file__).resolve().parents[2] / "config" / "gics_sectors_sp500.csv"
        s, diag = load_gics_sectors(csv)

        # The committed artifact should have at least the full SPY constituent set.
        assert len(s) >= 490, f"expected ~503, got {len(s)}"
        # All 11 GICS sectors should be present.
        assert s.nunique(dropna=True) == 11
        # Spot-check: AAPL is Information Technology, JPM is Financials, XOM is Energy.
        assert s.get("AAPL") == "Information Technology"
        assert s.get("JPM") == "Financials"
        assert s.get("XOM") == "Energy"
        assert any("gics_sectors loaded" in m.message for m in diag.messages)
