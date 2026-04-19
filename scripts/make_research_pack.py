#!/usr/bin/env python3
"""Emit a reproducibility research pack for a given run.

Produces `results/packs/<run_id>/manifest.json` plus a snapshot copy of every
frozen config file. The manifest is a machine-readable audit artifact: given
the manifest plus the paired commit, a third party can recreate the exact
environment that produced a research result.

Manifest contents (enforced shape — downstream tools read these keys):

    run_id             : user-supplied ID (or auto from timestamp)
    run_label          : optional human label (e.g. "iter11_attribution_demo")
    generated_at       : ISO 8601 UTC
    git                : {sha, short, branch, dirty, dirty_files_count}
    python             : {version, implementation, executable}
    platform           : {system, release, machine}
    dependencies       : {pyproject_sha256, uv_lock_sha256, uv_lock_present}
    configs            : {<filename>: <sha256>} for every YAML in config/
    data_snapshot      : {path, schema_hash, table_row_counts}  (or null if absent)
    research_log_tip   : {hash, height}                          (or null if absent)
    reproduction       : {env_setup_cmds, rerun_command}

Snapshot files copied alongside manifest.json:
    config/<each .yaml>      -> <pack_dir>/configs/<name>.yaml
    uv.lock                  -> <pack_dir>/uv.lock      (if present)
    pyproject.toml           -> <pack_dir>/pyproject.toml

Usage:
    python scripts/make_research_pack.py --run-id 2026-04-19_iter11 \\
        --label "attribution-template-demo"
    python scripts/make_research_pack.py                       # auto run_id
    python scripts/make_research_pack.py --db-path other.duckdb

The pack is intentionally *not* hash-chained into research_log.jsonl by this
script. Callers that want a permanent anchor should append a research-log
event whose payload includes `manifest_sha256` — that is the canonical
tamper-evident pointer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform as _platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "research.duckdb"
DEFAULT_PACKS_DIR = REPO_ROOT / "results" / "packs"
DEFAULT_LOG = REPO_ROOT / "results" / "research_log.jsonl"
CONFIG_DIR = REPO_ROOT / "config"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(args: list[str]) -> str:
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _git_info() -> dict[str, Any]:
    sha = _git(["rev-parse", "HEAD"])
    short = _git(["rev-parse", "--short", "HEAD"])
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"])
    porcelain = _git(["status", "--porcelain"])
    dirty_files = [ln for ln in porcelain.splitlines() if ln.strip()]
    return {
        "sha": sha,
        "short": short,
        "branch": branch,
        "dirty": bool(dirty_files),
        "dirty_files_count": len(dirty_files),
    }


def _python_info() -> dict[str, str]:
    return {
        "version": _platform.python_version(),
        "implementation": _platform.python_implementation(),
        "executable": sys.executable,
    }


def _platform_info() -> dict[str, str]:
    return {
        "system": _platform.system(),
        "release": _platform.release(),
        "machine": _platform.machine(),
    }


def _dependency_info() -> dict[str, Any]:
    pyproject = REPO_ROOT / "pyproject.toml"
    uv_lock = REPO_ROOT / "uv.lock"
    return {
        "pyproject_sha256": _sha256_file(pyproject) if pyproject.exists() else None,
        "uv_lock_sha256": _sha256_file(uv_lock) if uv_lock.exists() else None,
        "uv_lock_present": uv_lock.exists(),
    }


def _config_hashes() -> dict[str, str]:
    """sha256 of every file under config/ so a mismatch flags drift."""
    result: dict[str, str] = {}
    if not CONFIG_DIR.exists():
        return result
    for p in sorted(CONFIG_DIR.iterdir()):
        if p.is_file():
            result[p.name] = _sha256_file(p)
    return result


def _duckdb_snapshot(db_path: Path) -> dict[str, Any] | None:
    """Return a deterministic fingerprint of the DuckDB schema + row counts.

    Returns None if the DB file is missing. The fingerprint is *not* a hash of
    raw data pages (DuckDB pages embed file-level metadata that changes on
    every re-open); it's a hash of (table_name, schema, row_count) tuples.
    This catches schema changes and data growth/shrinkage, which is what a
    reproducibility audit needs.
    """
    if not db_path.exists():
        return None
    try:
        import duckdb  # local import: dependency is optional for script import
    except ImportError:
        return {"path": str(db_path), "schema_hash": None, "table_row_counts": None,
                "error": "duckdb python module not installed"}
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' ORDER BY table_name"
        ).fetchall()
        table_names = [r[0] for r in rows]
        counts: dict[str, int] = {}
        schema_records: list[dict[str, Any]] = []
        for tn in table_names:
            cols = conn.execute(
                "SELECT column_name, data_type "
                "FROM information_schema.columns "
                f"WHERE table_schema='main' AND table_name=? "
                "ORDER BY ordinal_position",
                [tn],
            ).fetchall()
            schema_records.append({"table": tn, "columns": [list(c) for c in cols]})
            count = conn.execute(f'SELECT COUNT(*) FROM "{tn}"').fetchone()
            counts[tn] = int(count[0]) if count else 0
        fingerprint = {
            "tables": schema_records,
            "counts": counts,
        }
        fp_bytes = json.dumps(fingerprint, sort_keys=True,
                              separators=(",", ":")).encode("utf-8")
        try:
            path_repr = str(db_path.relative_to(REPO_ROOT))
        except ValueError:
            path_repr = str(db_path)
        return {
            "path": path_repr,
            "schema_hash": _sha256_bytes(fp_bytes),
            "table_row_counts": counts,
        }
    finally:
        conn.close()


def _research_log_tip(log_path: Path) -> dict[str, Any] | None:
    if not log_path.exists():
        return None
    last_hash: str | None = None
    height = 0
    with log_path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and isinstance(obj.get("hash"), str):
                last_hash = obj["hash"]
                height += 1
    if last_hash is None:
        return None
    return {"hash": last_hash, "height": height}


def _reproduction_block(run_id: str) -> dict[str, Any]:
    return {
        "env_setup_cmds": [
            "pip install --user uv",
            "uv sync --extra dev --extra research",
            "pre-commit install",
        ],
        "verify_chain_cmd": "python3 scripts/verify_research_log.py",
        "rerun_command": (
            f"python3 scripts/run_backtest.py --research-pack results/packs/{run_id}"
        ),
    }


def _auto_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _copy_snapshot_files(pack_dir: Path) -> None:
    """Copy every file that affects reproducibility into the pack."""
    configs_out = pack_dir / "configs"
    configs_out.mkdir(parents=True, exist_ok=True)
    if CONFIG_DIR.exists():
        for p in sorted(CONFIG_DIR.iterdir()):
            if p.is_file():
                shutil.copy2(p, configs_out / p.name)
    for top_level in ("uv.lock", "pyproject.toml"):
        src = REPO_ROOT / top_level
        if src.exists():
            shutil.copy2(src, pack_dir / top_level)


def build_pack(
    run_id: str,
    label: str | None,
    db_path: Path,
    log_path: Path,
    packs_dir: Path,
) -> Path:
    pack_dir = packs_dir / run_id
    pack_dir.mkdir(parents=True, exist_ok=False)

    manifest: dict[str, Any] = {
        "run_id": run_id,
        "run_label": label,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git": _git_info(),
        "python": _python_info(),
        "platform": _platform_info(),
        "dependencies": _dependency_info(),
        "configs": _config_hashes(),
        "data_snapshot": _duckdb_snapshot(db_path),
        "research_log_tip": _research_log_tip(log_path),
        "reproduction": _reproduction_block(run_id),
    }

    _copy_snapshot_files(pack_dir)

    manifest_bytes = json.dumps(manifest, sort_keys=True,
                                separators=(",", ":")).encode("utf-8")
    manifest["manifest_sha256"] = _sha256_bytes(manifest_bytes)

    (pack_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return pack_dir


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Emit a reproducibility research pack.")
    ap.add_argument("--run-id", default=None,
                    help="run identifier (default: current UTC timestamp)")
    ap.add_argument("--label", default=None,
                    help="optional human-readable label")
    ap.add_argument("--db-path", default=str(DEFAULT_DB),
                    help=f"path to research DuckDB (default: {DEFAULT_DB})")
    ap.add_argument("--log-path", default=str(DEFAULT_LOG),
                    help="path to research_log.jsonl")
    ap.add_argument("--packs-dir", default=str(DEFAULT_PACKS_DIR),
                    help="parent directory for pack output")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ns = _parse_args(argv)
    run_id = ns.run_id or _auto_run_id()
    try:
        pack_dir = build_pack(
            run_id=run_id,
            label=ns.label,
            db_path=Path(ns.db_path),
            log_path=Path(ns.log_path),
            packs_dir=Path(ns.packs_dir),
        )
    except FileExistsError:
        print(f"ERROR: pack directory already exists: "
              f"{Path(ns.packs_dir) / run_id}", file=sys.stderr)
        return 2
    print(f"Wrote research pack: {pack_dir}")
    print(f"  manifest: {pack_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
