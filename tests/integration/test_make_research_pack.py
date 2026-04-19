"""Integration tests for scripts/make_research_pack.py.

Exercises the real script against a real DuckDB file and a real research-log
sample to verify the manifest contract. No mocks — iron rule 3 forbids
mocking the database in integration tests, and the research-pack manifest
fingerprint is the artifact auditors will re-verify.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import duckdb
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"


def _load_pack_module():
    spec = importlib.util.spec_from_file_location("make_research_pack", SCRIPTS_DIR / "make_research_pack.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def pack_module():
    return _load_pack_module()


@pytest.fixture
def mini_duckdb(tmp_path: Path) -> Path:
    """Two-table DuckDB with known row counts for deterministic fingerprint."""
    db = tmp_path / "mini.duckdb"
    conn = duckdb.connect(str(db))
    try:
        conn.execute("CREATE TABLE ohlcv (date DATE, symbol VARCHAR, close DOUBLE)")
        conn.execute(
            "INSERT INTO ohlcv VALUES "
            "('2023-01-03', 'AAPL', 125.1), "
            "('2023-01-03', 'MSFT', 224.5), "
            "('2023-01-04', 'AAPL', 126.0)"
        )
        conn.execute("CREATE TABLE fundamentals (cik VARCHAR, period_end DATE, revenue BIGINT)")
        conn.execute("INSERT INTO fundamentals VALUES ('0000320193', '2023-12-31', 394000000000)")
    finally:
        conn.close()
    return db


@pytest.fixture
def mini_log(tmp_path: Path) -> Path:
    """Small hash-chained research log (2 entries) with a known tip."""
    log = tmp_path / "research_log.jsonl"
    GENESIS = "0" * 64
    entry_a = {"event": "bootstrap", "iter": 0}
    entry_b = {"event": "factor_screen", "iter": 1, "factor": "ivol_20d"}

    def canon(obj):
        return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def sha(prev: str, entry: dict) -> str:
        h = hashlib.sha256()
        h.update(prev.encode("utf-8"))
        h.update(canon(entry))
        return h.hexdigest()

    h1 = sha(GENESIS, entry_a)
    h2 = sha(h1, entry_b)
    with log.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"prev_hash": GENESIS, "entry": entry_a, "hash": h1}) + "\n")
        fh.write(json.dumps({"prev_hash": h1, "entry": entry_b, "hash": h2}) + "\n")
    return log


class TestMakeResearchPack:
    def test_manifest_contains_required_top_level_keys(
        self, pack_module, tmp_path: Path, mini_duckdb: Path, mini_log: Path
    ):
        packs_dir = tmp_path / "packs"
        pack_dir = pack_module.build_pack(
            run_id="test_run_a",
            label="int-test-a",
            db_path=mini_duckdb,
            log_path=mini_log,
            packs_dir=packs_dir,
        )
        manifest = json.loads((pack_dir / "manifest.json").read_text())

        required = {
            "run_id",
            "run_label",
            "generated_at",
            "git",
            "python",
            "platform",
            "dependencies",
            "configs",
            "data_snapshot",
            "research_log_tip",
            "reproduction",
            "manifest_sha256",
        }
        assert required.issubset(manifest.keys()), f"missing: {required - set(manifest.keys())}"

    def test_manifest_sha256_hex_64(self, pack_module, tmp_path, mini_duckdb, mini_log):
        pack_dir = pack_module.build_pack(
            run_id="test_run_b",
            label=None,
            db_path=mini_duckdb,
            log_path=mini_log,
            packs_dir=tmp_path / "packs",
        )
        manifest = json.loads((pack_dir / "manifest.json").read_text())
        assert len(manifest["manifest_sha256"]) == 64
        int(manifest["manifest_sha256"], 16)  # must be valid hex

    def test_data_snapshot_row_counts_and_hash_deterministic(
        self, pack_module, tmp_path, mini_duckdb, mini_log
    ):
        """Same inputs must produce the same schema_hash + counts across runs."""
        pack_a = pack_module.build_pack(
            run_id="det_a",
            label=None,
            db_path=mini_duckdb,
            log_path=mini_log,
            packs_dir=tmp_path / "a",
        )
        pack_b = pack_module.build_pack(
            run_id="det_b",
            label=None,
            db_path=mini_duckdb,
            log_path=mini_log,
            packs_dir=tmp_path / "b",
        )
        m_a = json.loads((pack_a / "manifest.json").read_text())
        m_b = json.loads((pack_b / "manifest.json").read_text())

        assert m_a["data_snapshot"]["schema_hash"] == m_b["data_snapshot"]["schema_hash"]
        assert m_a["data_snapshot"]["table_row_counts"] == {"ohlcv": 3, "fundamentals": 1}
        assert m_a["data_snapshot"]["table_row_counts"] == m_b["data_snapshot"]["table_row_counts"]

    def test_research_log_tip_matches_last_chained_hash(self, pack_module, tmp_path, mini_duckdb, mini_log):
        pack_dir = pack_module.build_pack(
            run_id="tip_check",
            label=None,
            db_path=mini_duckdb,
            log_path=mini_log,
            packs_dir=tmp_path / "packs",
        )
        manifest = json.loads((pack_dir / "manifest.json").read_text())
        tip = manifest["research_log_tip"]
        assert tip is not None
        assert tip["height"] == 2
        # Recompute expected last hash independently.
        last_line = mini_log.read_text().strip().splitlines()[-1]
        expected_hash = json.loads(last_line)["hash"]
        assert tip["hash"] == expected_hash

    def test_snapshot_copies_all_configs(self, pack_module, tmp_path, mini_duckdb, mini_log):
        pack_dir = pack_module.build_pack(
            run_id="copy_check",
            label=None,
            db_path=mini_duckdb,
            log_path=mini_log,
            packs_dir=tmp_path / "packs",
        )
        configs_snap = pack_dir / "configs"
        assert configs_snap.exists()
        repo_configs = Path(pack_module.CONFIG_DIR)
        if repo_configs.exists():
            expected = {p.name for p in repo_configs.iterdir() if p.is_file()}
            copied = {p.name for p in configs_snap.iterdir() if p.is_file()}
            assert copied == expected

    def test_manifest_sha256_reflects_payload_changes(self, pack_module, tmp_path, mini_duckdb, mini_log):
        """Manifest self-hash changes when inputs change."""
        pack_a = pack_module.build_pack(
            run_id="payload_a",
            label="run-a",
            db_path=mini_duckdb,
            log_path=mini_log,
            packs_dir=tmp_path / "packs",
        )
        pack_b = pack_module.build_pack(
            run_id="payload_b",
            label="run-b",  # label differs
            db_path=mini_duckdb,
            log_path=mini_log,
            packs_dir=tmp_path / "packs",
        )
        m_a = json.loads((pack_a / "manifest.json").read_text())
        m_b = json.loads((pack_b / "manifest.json").read_text())
        assert m_a["manifest_sha256"] != m_b["manifest_sha256"]

    def test_missing_db_returns_none_snapshot(self, pack_module, tmp_path, mini_log):
        """No DuckDB present → data_snapshot is None (not a hard failure)."""
        pack_dir = pack_module.build_pack(
            run_id="no_db",
            label=None,
            db_path=tmp_path / "does_not_exist.duckdb",
            log_path=mini_log,
            packs_dir=tmp_path / "packs",
        )
        manifest = json.loads((pack_dir / "manifest.json").read_text())
        assert manifest["data_snapshot"] is None

    def test_missing_log_returns_none_tip(self, pack_module, tmp_path, mini_duckdb):
        pack_dir = pack_module.build_pack(
            run_id="no_log",
            label=None,
            db_path=mini_duckdb,
            log_path=tmp_path / "does_not_exist.jsonl",
            packs_dir=tmp_path / "packs",
        )
        manifest = json.loads((pack_dir / "manifest.json").read_text())
        assert manifest["research_log_tip"] is None

    def test_rerun_command_references_run_id(self, pack_module, tmp_path, mini_duckdb, mini_log):
        pack_dir = pack_module.build_pack(
            run_id="rerun_check_xyz",
            label=None,
            db_path=mini_duckdb,
            log_path=mini_log,
            packs_dir=tmp_path / "packs",
        )
        manifest = json.loads((pack_dir / "manifest.json").read_text())
        assert "rerun_check_xyz" in manifest["reproduction"]["rerun_command"]

    def test_existing_run_id_errors(self, pack_module, tmp_path, mini_duckdb, mini_log):
        pack_module.build_pack(
            run_id="collide",
            label=None,
            db_path=mini_duckdb,
            log_path=mini_log,
            packs_dir=tmp_path / "packs",
        )
        with pytest.raises(FileExistsError):
            pack_module.build_pack(
                run_id="collide",
                label=None,
                db_path=mini_duckdb,
                log_path=mini_log,
                packs_dir=tmp_path / "packs",
            )

    def test_cli_main_auto_generates_run_id(self, pack_module, tmp_path, mini_duckdb, mini_log, monkeypatch):
        """`make_research_pack.main([])` with no --run-id should succeed."""
        packs_dir = tmp_path / "auto_packs"
        rc = pack_module.main(
            [
                "--db-path",
                str(mini_duckdb),
                "--log-path",
                str(mini_log),
                "--packs-dir",
                str(packs_dir),
            ]
        )
        assert rc == 0
        subdirs = [p for p in packs_dir.iterdir() if p.is_dir()]
        assert len(subdirs) == 1
        manifest = json.loads((subdirs[0] / "manifest.json").read_text())
        assert manifest["run_id"] == subdirs[0].name
