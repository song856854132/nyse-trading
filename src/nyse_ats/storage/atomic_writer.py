"""Crash-safe file writer using tempfile + rename pattern.

Guarantees atomicity: if a crash occurs during write, the target file is untouched.
Uses os.replace() for cross-platform atomic rename.

Class-based API:
    with AtomicWriter(Path("/data/output.csv")) as fh:
        fh.write("col1,col2\\n")
    # file is atomically visible at /data/output.csv only after __exit__

Function-based API:
    atomic_write(Path("/data/out.txt"), "content")
    atomic_write_df(Path("/data/df.parquet"), df, format="parquet")
"""

from __future__ import annotations

import contextlib
import logging
import os
import tempfile
from pathlib import Path
from typing import IO, TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

logger = logging.getLogger(__name__)


# ── Class-based context manager ─────────────────────────────────────────────


class AtomicWriter:
    """Write files atomically using tempfile + rename pattern.

    On success (__exit__ with no exception): ``os.replace(tmp, target)`` — atomic on POSIX.
    On exception: temp file is deleted, exception is re-raised.
    On disk-full (``OSError``): temp file is cleaned up, a clear error is raised.
    Parent directories are created automatically if they do not exist.
    """

    def __init__(self, target_path: Path) -> None:
        self._target = Path(target_path)
        self._tmp_path: str | None = None
        self._fd: int | None = None
        self._file: IO[str] | None = None

    def __enter__(self) -> IO[str]:
        """Create a temp file in the target's parent directory and return a writable handle."""
        parent = self._target.parent
        parent.mkdir(parents=True, exist_ok=True)

        self._fd, self._tmp_path = tempfile.mkstemp(
            dir=parent,
            prefix=f".{self._target.name}.",
            suffix=".tmp",
        )
        self._file = os.fdopen(self._fd, mode="w", encoding="utf-8")
        self._fd = None  # fdopen owns the fd now; do not double-close
        return self._file

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        try:
            if exc_type is None:
                assert self._file is not None
                self._file.flush()
                os.fsync(self._file.fileno())
                self._file.close()
                self._file = None
                assert self._tmp_path is not None
                os.replace(self._tmp_path, self._target)
                logger.debug("Atomic write complete: %s", self._target)
            else:
                self._cleanup()
        except OSError as ose:
            self._cleanup()
            raise OSError(f"Atomic write to {self._target} failed (disk full?): {ose}") from ose

    def _cleanup(self) -> None:
        """Best-effort close + delete of the temp file."""
        if self._file is not None:
            with contextlib.suppress(OSError):
                self._file.close()
            self._file = None

        if self._fd is not None:
            with contextlib.suppress(OSError):
                os.close(self._fd)
            self._fd = None

        if self._tmp_path is not None and os.path.exists(self._tmp_path):
            try:
                os.unlink(self._tmp_path)
                logger.debug("Cleaned up temp file: %s", self._tmp_path)
            except OSError:
                pass
            self._tmp_path = None


# ── Function-based helpers ──────────────────────────────────────────────────


def atomic_write(filepath: Path, content: bytes | str, mode: str = "w") -> None:
    """Write content to filepath atomically.

    Strategy: write to a tempfile in the same directory, then os.replace() to target.
    If a crash occurs during the write phase, the original target is untouched.

    Args:
        filepath: Target file path.
        content: Bytes or string content to write.
        mode: File open mode — "w" for text, "wb" for binary.

    Raises:
        OSError: If disk is full or other I/O error (tempfile is cleaned up).
    """
    filepath = Path(filepath)
    parent = filepath.parent
    parent.mkdir(parents=True, exist_ok=True)

    is_binary = "b" in mode
    fd = None
    tmp_path: str | None = None

    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=parent,
            prefix=f".{filepath.name}.",
            suffix=".tmp",
        )
        if is_binary:
            os.write(fd, content if isinstance(content, bytes) else content.encode("utf-8"))
        else:
            os.write(fd, content.encode("utf-8") if isinstance(content, str) else content)
        os.fsync(fd)
        os.close(fd)
        fd = None

        os.replace(tmp_path, filepath)
        logger.debug("Atomic write complete: %s", filepath)

    except OSError:
        logger.error("Atomic write failed for %s — cleaning up tempfile", filepath)
        if fd is not None:
            with contextlib.suppress(OSError):
                os.close(fd)
        if tmp_path is not None and os.path.exists(tmp_path):
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
        raise


def atomic_write_df(filepath: Path, df: pd.DataFrame, format: str = "parquet") -> None:
    """Write a DataFrame to filepath atomically.

    Args:
        filepath: Target file path.
        df: DataFrame to write.
        format: Output format — "parquet" or "csv".

    Raises:
        ValueError: If format is not "parquet" or "csv".
        OSError: If disk is full or other I/O error.
    """
    filepath = Path(filepath)
    parent = filepath.parent
    parent.mkdir(parents=True, exist_ok=True)

    if format not in ("parquet", "csv"):
        raise ValueError(f"Unsupported format: {format!r}. Use 'parquet' or 'csv'.")

    tmp_path: str | None = None

    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=parent,
            prefix=f".{filepath.name}.",
            suffix=".tmp",
        )
        os.close(fd)

        if format == "parquet":
            df.to_parquet(tmp_path, index=True)
        else:
            df.to_csv(tmp_path, index=True)

        os.replace(tmp_path, filepath)
        logger.debug("Atomic DataFrame write complete (%s): %s", format, filepath)

    except OSError:
        logger.error("Atomic DataFrame write failed for %s — cleaning up tempfile", filepath)
        if tmp_path is not None and os.path.exists(tmp_path):
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
        raise
