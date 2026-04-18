"""Unit tests for nyse_ats.storage.atomic_writer."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING
from unittest.mock import patch

import pandas as pd
import pytest

from nyse_ats.storage.atomic_writer import AtomicWriter, atomic_write, atomic_write_df

if TYPE_CHECKING:
    from pathlib import Path

# ── Function-based API ──────────────────────────────────────────────────────


class TestAtomicWriteText:
    """Tests for atomic_write with text content."""

    def test_text_round_trip(self, tmp_path: Path) -> None:
        """Write text and read it back -- content must match exactly."""
        target = tmp_path / "output.txt"
        content = "Hello, NYSE ATS!\nLine two."
        atomic_write(target, content, mode="w")

        assert target.exists()
        assert target.read_text() == content

    def test_bytes_round_trip(self, tmp_path: Path) -> None:
        """Write bytes and read them back -- content must match exactly."""
        target = tmp_path / "output.bin"
        content = b"\x00\x01\x02\xff\xfe"
        atomic_write(target, content, mode="wb")

        assert target.exists()
        assert target.read_bytes() == content

    def test_atomic_target_unchanged_on_write_failure(self, tmp_path: Path) -> None:
        """If the write fails (e.g., OSError), the original target must be untouched."""
        target = tmp_path / "important.txt"
        original_content = "original data"
        target.write_text(original_content)

        with patch("nyse_ats.storage.atomic_writer.os.write", side_effect=OSError("disk full")):
            with pytest.raises(OSError, match="disk full"):
                atomic_write(target, "new data that should not appear")

        assert target.read_text() == original_content

    def test_tempfile_cleaned_up_on_success(self, tmp_path: Path) -> None:
        """After a successful write, no .tmp files should remain."""
        target = tmp_path / "clean.txt"
        atomic_write(target, "data")

        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == [], f"Leftover tempfiles: {tmp_files}"

    def test_tempfile_cleaned_up_on_failure(self, tmp_path: Path) -> None:
        """After a failed write, no .tmp files should remain."""
        target = tmp_path / "fail.txt"

        with patch("nyse_ats.storage.atomic_writer.os.write", side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                atomic_write(target, "data")

        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == [], f"Leftover tempfiles: {tmp_files}"

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Parent directories are created if they don't exist."""
        target = tmp_path / "sub" / "dir" / "output.txt"
        atomic_write(target, "nested")
        assert target.read_text() == "nested"

    def test_concurrent_writes_no_corruption(self, tmp_path: Path) -> None:
        """Multiple threads writing to different files should not corrupt each other."""
        results: list[Exception | None] = [None] * 10

        def writer(idx: int) -> None:
            try:
                path = tmp_path / f"concurrent_{idx}.txt"
                content = f"data-{idx}" * 100
                atomic_write(path, content)
                read_back = path.read_text()
                assert read_back == content
            except Exception as e:
                results[idx] = e

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        errors = [r for r in results if r is not None]
        assert errors == [], f"Concurrent write errors: {errors}"

    def test_disk_full_handling(self, tmp_path: Path) -> None:
        """OSError (disk full) is raised and tempfile is cleaned up."""
        target = tmp_path / "diskfull.txt"

        with patch("nyse_ats.storage.atomic_writer.os.write", side_effect=OSError("No space left")):
            with pytest.raises(OSError, match="No space left"):
                atomic_write(target, "data")

        assert not target.exists()


class TestAtomicWriteDataFrame:
    """Tests for atomic_write_df with DataFrames."""

    def test_parquet_round_trip(self, tmp_path: Path) -> None:
        """Write a DataFrame as parquet and read it back."""
        target = tmp_path / "data.parquet"
        df = pd.DataFrame({"symbol": ["AAPL", "MSFT"], "price": [150.0, 300.0]})
        atomic_write_df(target, df, format="parquet")

        result = pd.read_parquet(target)
        pd.testing.assert_frame_equal(result, df)

    def test_csv_round_trip(self, tmp_path: Path) -> None:
        """Write a DataFrame as CSV and read it back."""
        target = tmp_path / "data.csv"
        df = pd.DataFrame({"symbol": ["AAPL", "MSFT"], "price": [150.0, 300.0]})
        atomic_write_df(target, df, format="csv")

        result = pd.read_csv(target, index_col=0)
        pd.testing.assert_frame_equal(result, df)

    def test_invalid_format_raises(self, tmp_path: Path) -> None:
        """Unsupported format raises ValueError."""
        target = tmp_path / "data.json"
        df = pd.DataFrame({"a": [1]})
        with pytest.raises(ValueError, match="Unsupported format"):
            atomic_write_df(target, df, format="json")

    def test_df_disk_full_handling(self, tmp_path: Path) -> None:
        """OSError during DataFrame write is raised and tempfile is cleaned up."""
        target = tmp_path / "diskfull.parquet"
        df = pd.DataFrame({"a": [1, 2, 3]})

        with patch.object(pd.DataFrame, "to_parquet", side_effect=OSError("No space")):
            with pytest.raises(OSError, match="No space"):
                atomic_write_df(target, df, format="parquet")

        assert not target.exists()
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == [], f"Leftover tempfiles: {tmp_files}"


# ── Class-based AtomicWriter ────────────────────────────────────────────────


class TestAtomicWriterContextManager:
    """Tests for the AtomicWriter class-based context manager."""

    def test_context_manager_write(self, tmp_path: Path) -> None:
        """AtomicWriter writes content atomically via context manager."""
        target = tmp_path / "cm_output.txt"
        with AtomicWriter(target) as fh:
            fh.write("line1\n")
            fh.write("line2\n")

        assert target.read_text() == "line1\nline2\n"

    def test_context_manager_cleanup_on_exception(self, tmp_path: Path) -> None:
        """If an exception occurs inside the with-block, temp is cleaned up."""
        target = tmp_path / "cm_fail.txt"
        target.write_text("original")

        with pytest.raises(RuntimeError, match="deliberate"), AtomicWriter(target) as fh:
            fh.write("should not persist")
            raise RuntimeError("deliberate")

        assert target.read_text() == "original"
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == []

    def test_context_manager_creates_parents(self, tmp_path: Path) -> None:
        """AtomicWriter creates parent directories if needed."""
        target = tmp_path / "deep" / "nested" / "file.txt"
        with AtomicWriter(target) as fh:
            fh.write("deep write")
        assert target.read_text() == "deep write"

    def test_context_manager_writelines(self, tmp_path: Path) -> None:
        """The handle returned by AtomicWriter supports .writelines()."""
        target = tmp_path / "lines.txt"
        with AtomicWriter(target) as fh:
            fh.writelines(["a\n", "b\n", "c\n"])
        assert target.read_text() == "a\nb\nc\n"

    def test_overwrite_existing_file_atomically(self, tmp_path: Path) -> None:
        """Writing to an existing file replaces it atomically."""
        target = tmp_path / "overwrite.txt"
        target.write_text("v1")

        with AtomicWriter(target) as fh:
            fh.write("v2")

        assert target.read_text() == "v2"

    def test_disk_full_during_fsync_cleans_temp(self, tmp_path: Path) -> None:
        """If os.fsync raises OSError (disk full), temp is cleaned up."""
        target = tmp_path / "full.txt"

        with pytest.raises(OSError, match="disk full"):
            with patch("os.fsync", side_effect=OSError("disk full")):
                with AtomicWriter(target) as fh:
                    fh.write("data")

        assert not target.exists()
        temps = list(tmp_path.glob("*.tmp"))
        assert temps == []
