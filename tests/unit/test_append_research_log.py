"""Unit tests for scripts/append_research_log.py.

Covers the pre-Wave-8 enhancements:
  - `--expected-prev-hash <hash>` optimistic-concurrency guard
  - `iteration_tag` idempotency (silent skip on identical content; raise on divergence)

scripts/ is not a Python package on sys.path (per integration test convention), so we
load the module via importlib for direct function tests, and shell out via subprocess
for end-to-end CLI behavior.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "append_research_log.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("append_research_log", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def appender():
    return _load_module()


@pytest.fixture
def log_path(tmp_path):
    return tmp_path / "log.jsonl"


class TestChainIntegrity:
    def test_genesis_bootstrap_when_log_missing(self, appender, log_path):
        record, status = appender.append_event(log_path, {"event": "a"})
        assert status == "appended"
        assert record["prev_hash"] == appender.GENESIS_PREV_HASH

    def test_chain_continues_across_appends(self, appender, log_path):
        r1, _ = appender.append_event(log_path, {"event": "a"})
        r2, _ = appender.append_event(log_path, {"event": "b"})
        assert r2["prev_hash"] == r1["hash"]

    def test_hash_is_deterministic_over_canonical_form(self, appender, log_path):
        r1, _ = appender.append_event(log_path, {"event": "a", "x": 1, "y": 2})
        # recomputed independently
        recomputed = appender._compute_hash(r1["prev_hash"], r1["entry"])
        assert recomputed == r1["hash"]


class TestExpectedPrevHashGuard:
    def test_match_succeeds(self, appender, log_path):
        r1, _ = appender.append_event(log_path, {"event": "a"})
        r2, _ = appender.append_event(log_path, {"event": "b"}, expected_prev_hash=r1["hash"])
        assert r2["prev_hash"] == r1["hash"]

    def test_mismatch_rejects(self, appender, log_path):
        appender.append_event(log_path, {"event": "a"})
        with pytest.raises(ValueError, match="PREV_HASH_CONFLICT"):
            appender.append_event(log_path, {"event": "b"}, expected_prev_hash="ff" * 32)

    def test_genesis_expected_on_empty_log_succeeds(self, appender, log_path):
        record, _ = appender.append_event(
            log_path,
            {"event": "a"},
            expected_prev_hash=appender.GENESIS_PREV_HASH,
        )
        assert record["prev_hash"] == appender.GENESIS_PREV_HASH

    def test_none_means_unguarded(self, appender, log_path):
        # No expected_prev_hash -> behaves like the original implementation
        r1, _ = appender.append_event(log_path, {"event": "a"})
        r2, _ = appender.append_event(log_path, {"event": "b"}, expected_prev_hash=None)
        assert r2["prev_hash"] == r1["hash"]


class TestIterationTagIdempotency:
    def test_absent_tag_means_normal_append(self, appender, log_path):
        _, s1 = appender.append_event(log_path, {"event": "a"})
        _, s2 = appender.append_event(log_path, {"event": "b"})
        assert s1 == s2 == "appended"

    def test_duplicate_tag_identical_content_silent_skip(self, appender, log_path):
        event = {"event": "a", "iteration_tag": "iter-X", "k": 1}
        r1, s1 = appender.append_event(log_path, dict(event))
        r2, s2 = appender.append_event(log_path, dict(event))
        assert s1 == "appended"
        assert s2 == "already_appended"
        # Log file should still contain ONE chained line for iter-X
        lines = [ln for ln in log_path.read_text().splitlines() if ln.strip()]
        assert len(lines) == 1
        assert r2["hash"] == r1["hash"]

    def test_duplicate_tag_different_content_raises(self, appender, log_path):
        appender.append_event(log_path, {"event": "a", "iteration_tag": "iter-X", "k": 1})
        with pytest.raises(ValueError, match="ITERATION_TAG_CONFLICT"):
            appender.append_event(log_path, {"event": "a", "iteration_tag": "iter-X", "k": 2})

    def test_timestamp_difference_is_not_a_conflict(self, appender, log_path):
        appender.append_event(
            log_path,
            {"event": "a", "iteration_tag": "iter-X", "timestamp": "2025-01-01T00:00:00+00:00"},
        )
        _, s = appender.append_event(
            log_path,
            {"event": "a", "iteration_tag": "iter-X", "timestamp": "2026-01-01T00:00:00+00:00"},
        )
        assert s == "already_appended"
        lines = [ln for ln in log_path.read_text().splitlines() if ln.strip()]
        assert len(lines) == 1

    def test_idempotency_works_across_intervening_entries(self, appender, log_path):
        appender.append_event(log_path, {"event": "a", "iteration_tag": "iter-A", "k": 1})
        appender.append_event(log_path, {"event": "b", "iteration_tag": "iter-B", "k": 2})
        # Re-appending iter-A with identical content is still a no-op even though
        # iter-B was written after it.
        _, s = appender.append_event(log_path, {"event": "a", "iteration_tag": "iter-A", "k": 1})
        assert s == "already_appended"
        lines = [ln for ln in log_path.read_text().splitlines() if ln.strip()]
        assert len(lines) == 2

    def test_empty_string_tag_treated_as_absent(self, appender, log_path):
        _, s1 = appender.append_event(log_path, {"event": "a", "iteration_tag": ""})
        _, s2 = appender.append_event(log_path, {"event": "a", "iteration_tag": ""})
        # Empty tag bypasses idempotency -> two appends
        assert s1 == "appended"
        assert s2 == "appended"
        lines = [ln for ln in log_path.read_text().splitlines() if ln.strip()]
        assert len(lines) == 2


class TestCLI:
    def test_expected_prev_hash_mismatch_exits_1(self, tmp_path):
        log = tmp_path / "log.jsonl"
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--log-path",
                str(log),
                "--event-json",
                '{"event":"seed"}',
                "--quiet",
            ],
            check=True,
        )
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--log-path",
                str(log),
                "--event-json",
                '{"event":"a"}',
                "--expected-prev-hash",
                "ff" * 32,
                "--quiet",
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1
        assert "PREV_HASH_CONFLICT" in proc.stderr

    def test_expected_prev_hash_match_exits_0(self, tmp_path):
        log = tmp_path / "log.jsonl"
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--log-path",
                str(log),
                "--event-json",
                '{"event":"seed"}',
                "--quiet",
            ],
            check=True,
        )
        # read tip
        tip = json.loads(log.read_text().splitlines()[-1])["hash"]
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--log-path",
                str(log),
                "--event-json",
                '{"event":"a"}',
                "--expected-prev-hash",
                tip,
                "--quiet",
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr

    def test_iteration_tag_idempotent_silent_skip_exits_0(self, tmp_path):
        log = tmp_path / "log.jsonl"
        payload = '{"event":"a","iteration_tag":"iter-Y","k":1}'
        proc1 = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--log-path", str(log), "--event-json", payload, "--quiet"],
            capture_output=True,
            text=True,
        )
        assert proc1.returncode == 0, proc1.stderr
        proc2 = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--log-path", str(log), "--event-json", payload, "--quiet"],
            capture_output=True,
            text=True,
        )
        assert proc2.returncode == 0, proc2.stderr
        lines = [ln for ln in log.read_text().splitlines() if ln.strip()]
        assert len(lines) == 1

    def test_iteration_tag_conflict_exits_1(self, tmp_path):
        log = tmp_path / "log.jsonl"
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--log-path",
                str(log),
                "--event-json",
                '{"event":"a","iteration_tag":"iter-Z","k":1}',
                "--quiet",
            ],
            check=True,
        )
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--log-path",
                str(log),
                "--event-json",
                '{"event":"a","iteration_tag":"iter-Z","k":2}',
                "--quiet",
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1
        assert "ITERATION_TAG_CONFLICT" in proc.stderr

    def test_idempotent_skip_message_includes_existing_hash(self, tmp_path):
        log = tmp_path / "log.jsonl"
        payload = '{"event":"a","iteration_tag":"iter-Q","k":1}'
        subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--log-path", str(log), "--event-json", payload],
            check=True,
            capture_output=True,
        )
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--log-path", str(log), "--event-json", payload],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0
        assert "Idempotent re-append" in proc.stdout
        assert "iter-Q" in proc.stdout
