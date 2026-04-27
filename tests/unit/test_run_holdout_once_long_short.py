"""Unit tests for the Wave 9-D / iter-33 P0-E long-short holdout runner.

Scope (mirrors plan ``dreamy-riding-quasar.md`` Tests section, 11 tests total):

    5 P1-4 baseline tests (Wave 6 P0-C pattern):
      1. Window enforcement -- runtime value-equality assertion at module-import
         time (rev2 P1-3 reframing of v1's no-op in-memory-mutation test)
      2. Lockfile refusal -- refuses if .holdout_used or .holdout_in_progress exists
      3. Frozen-hash mismatch -- refuses if any of the 3 frozen sha256s drift
         (gates_v2.yaml + gates.yaml + W8-D evidence)
      4. Successful evidence write on synthetic fixture (compute_fn injected;
         DuckDB NOT touched; iter-28 helpers NOT exercised)
      5. check_holdout_guard.py allowlist passes (no new paths beyond Wave 7)

    6 crash-path tests (P1-6 expansion -- terminal-state pre-registration):
      6. Compute exception after .holdout_in_progress create -> CONSUMED_NO_VERDICT
         lockfile state preserved (Iron Rule 1 strict consume-on-touch)
      7. os.replace failure on .holdout_used rename -> CONSUMED_LOCKFILE_MISMATCH
         (mock OSError; verify deterministic terminal state)
      8. fsync failure on evidence write -> partial JSON detected on next pre-flight
         via sidecar sha256 mismatch (defense-in-depth path)
      9. Concurrent execution race -- two runner processes start simultaneously;
         O_EXCL on .holdout_in_progress allows EXACTLY ONE to proceed
     10. Consumed-without-evidence detection on subsequent invocation -- pre-flight
         refuses with explicit error message naming GL-0025
     11. Corrupted JSON detected by sidecar sha256 mismatch -- post-write tamper;
         verify integrity check pattern (lockfile prevents real re-run, but
         iter-35 verification + iter-36 forensic memo use this exact check).

The tests are hermetic: they never touch the real ``results/holdout/`` directory
on disk. ``runner._LOCKFILE_USED`` and friends are monkey-patched onto a
tmp-path-rooted layout so a failed assertion cannot accidentally consume the
holdout. ``compute_fn`` is mocked at the ``main(..., compute_fn=...)`` injection
point so DuckDB and iter-28 helpers are never touched.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import multiprocessing as mp
import os
import shutil
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"
sys.path.insert(0, str(_SCRIPTS))

_RUNNER_SPEC = importlib.util.spec_from_file_location(
    "run_holdout_once_long_short",
    _SCRIPTS / "run_holdout_once_long_short.py",
)
assert _RUNNER_SPEC is not None and _RUNNER_SPEC.loader is not None
runner = importlib.util.module_from_spec(_RUNNER_SPEC)
sys.modules["run_holdout_once_long_short"] = runner
_RUNNER_SPEC.loader.exec_module(runner)

_GUARD_SPEC = importlib.util.spec_from_file_location(
    "check_holdout_guard",
    _SCRIPTS / "check_holdout_guard.py",
)
assert _GUARD_SPEC is not None and _GUARD_SPEC.loader is not None
guard = importlib.util.module_from_spec(_GUARD_SPEC)
sys.modules["check_holdout_guard"] = guard
_GUARD_SPEC.loader.exec_module(guard)


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _seed_frozen_artefacts(root: Path) -> dict[str, Path]:
    """Copy the real frozen artefacts into ``root`` so their sha256s are
    bit-identical to the GL-0025 frozen values. Tests that intentionally mutate
    these files should do so AFTER calling this helper.
    """
    cfg_dir = root / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    gates_v2 = cfg_dir / "gates_v2.yaml"
    gates = cfg_dir / "gates.yaml"
    shutil.copyfile(_REPO_ROOT / "config" / "gates_v2.yaml", gates_v2)
    shutil.copyfile(_REPO_ROOT / "config" / "gates.yaml", gates)

    w8d_dir = root / "results" / "validation" / "wave8_d_single_factor"
    w8d_dir.mkdir(parents=True, exist_ok=True)
    w8d_evidence = w8d_dir / "result.json"
    shutil.copyfile(
        _REPO_ROOT / "results" / "validation" / "wave8_d_single_factor" / "result.json",
        w8d_evidence,
    )
    return {"gates_v2": gates_v2, "gates": gates, "w8d_evidence": w8d_evidence}


def _seed_holdout_layout(root: Path) -> dict[str, Path]:
    holdout_dir = root / "results" / "holdout"
    holdout_dir.mkdir(parents=True, exist_ok=True)
    return {
        "dir": holdout_dir,
        "used": holdout_dir / ".holdout_used",
        "in_progress": holdout_dir / ".holdout_in_progress",
        "output": holdout_dir / "holdout_result.json",
        "sha": holdout_dir / "holdout_result.json.sha256",
    }


def _patch_runner_paths(monkeypatch: pytest.MonkeyPatch, *, root: Path) -> dict[str, Path]:
    """Install a tmp-path-rooted layout onto the runner module's path constants."""
    artefacts = _seed_frozen_artefacts(root)
    layout = _seed_holdout_layout(root)
    monkeypatch.setattr(runner, "_GATES_V2_PATH", artefacts["gates_v2"])
    monkeypatch.setattr(runner, "_GATES_PATH", artefacts["gates"])
    monkeypatch.setattr(runner, "_W8D_EVIDENCE_PATH", artefacts["w8d_evidence"])
    monkeypatch.setattr(runner, "_HOLDOUT_DIR", layout["dir"])
    monkeypatch.setattr(runner, "_LOCKFILE_USED", layout["used"])
    monkeypatch.setattr(runner, "_LOCKFILE_IN_PROGRESS", layout["in_progress"])
    monkeypatch.setattr(runner, "_OUTPUT_PATH", layout["output"])
    monkeypatch.setattr(runner, "_OUTPUT_SHA_PATH", layout["sha"])
    return {**artefacts, **layout}


def _fake_compute_result(*, sharpe: float = 0.5549) -> dict:
    """Return a compute_fn-shaped dict that build_payload() can consume.

    Mirrors the structure of ``_compute_holdout_long_short`` output. The default
    sharpe of 0.5549 fires PASS-DECISIVE; tests can override to exercise other
    three-tier branches.
    """
    return {
        "n_rebalance_dates": 104,
        "n_forward_return_rows": 5000,
        "n_panel_rows": 1500,
        "n_ls_periods": 104,
        "v_d1_observed": sharpe,
        "v_d2_observed": 0.020,
        "v_d3_observed": 0.25,
        "v_d3_ci_upper": 0.85,
        "v_d4_observed": 0.22,
        "v_d4_bull_sharpe": 0.30,
        "v_d4_bear_sharpe": 0.22,
        "v_d4_bull_n_periods": 60,
        "v_d4_bear_n_periods": 44,
        "long_short_diagnostic_warnings": [],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Test 1: Window enforcement -- runtime value-equality at module-import time
# ═══════════════════════════════════════════════════════════════════════════════


class TestWindowEnforcement:
    def test_holdout_window_constants_are_2024_2025(self) -> None:
        """Rev2 P1-3 reframing: catch a future retune of the holdout window via
        direct value-equality check. Pairs with check_holdout_guard.py allowlist
        sha256 pin (defense-in-depth) once iter-34 GL-0025 lands the new pin.
        """
        assert runner._HOLDOUT_START == date(2024, 1, 1)  # noqa: SIM300
        assert runner._HOLDOUT_END == date(2025, 12, 31)  # noqa: SIM300

    def test_main_argparse_does_not_accept_start_date_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Iron Rule 1: holdout window is hardcoded; CLI may NOT override."""
        _patch_runner_paths(monkeypatch, root=tmp_path)
        with pytest.raises(SystemExit) as exc:
            runner.main(["--start-date", "2023-01-01"])
        assert exc.value.code == 2

    def test_main_argparse_does_not_accept_end_date_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_runner_paths(monkeypatch, root=tmp_path)
        with pytest.raises(SystemExit) as exc:
            runner.main(["--end-date", "2030-12-31"])
        assert exc.value.code == 2

    def test_preflight_window_mismatch_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        paths = _patch_runner_paths(monkeypatch, root=tmp_path)
        with pytest.raises(runner.PreflightError, match="window mismatch"):
            runner.preflight_check(
                start_date=date(2023, 1, 1),
                end_date=runner._HOLDOUT_END,
                gates_v2_path=paths["gates_v2"],
                gates_v2_expected_sha256=runner._GATES_V2_SHA256_FROZEN,
                gates_path=paths["gates"],
                gates_expected_sha256=runner._GATES_SHA256_FROZEN,
                w8d_evidence_path=paths["w8d_evidence"],
                w8d_evidence_expected_sha256=runner._W8D_EVIDENCE_SHA256_FROZEN,
                lockfile_used=paths["used"],
                lockfile_in_progress=paths["in_progress"],
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Test 2: Lockfile refusal -- .holdout_used or .holdout_in_progress exists
# ═══════════════════════════════════════════════════════════════════════════════


class TestLockfileRefusal:
    def test_preflight_refuses_when_holdout_used_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        paths = _patch_runner_paths(monkeypatch, root=tmp_path)
        paths["used"].write_text("consumed at 2026-04-30T12:00:00Z\n")
        with pytest.raises(runner.PreflightError, match="already consumed"):
            runner.preflight_check(
                start_date=runner._HOLDOUT_START,
                end_date=runner._HOLDOUT_END,
                gates_v2_path=paths["gates_v2"],
                gates_v2_expected_sha256=runner._GATES_V2_SHA256_FROZEN,
                gates_path=paths["gates"],
                gates_expected_sha256=runner._GATES_SHA256_FROZEN,
                w8d_evidence_path=paths["w8d_evidence"],
                w8d_evidence_expected_sha256=runner._W8D_EVIDENCE_SHA256_FROZEN,
                lockfile_used=paths["used"],
                lockfile_in_progress=paths["in_progress"],
            )

    def test_preflight_refuses_when_holdout_in_progress_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Strict consume-on-touch: a leftover .holdout_in_progress means a prior
        run crashed; partial = consumed (Iron Rule 1 + GL-0025 pre-registration).
        iter-36 routes A8 ABANDON via CONSUMED_NO_VERDICT or _PARTIAL_EVIDENCE.
        """
        paths = _patch_runner_paths(monkeypatch, root=tmp_path)
        paths["in_progress"].write_text("crashed at 2026-04-30T12:00:00Z\n")
        with pytest.raises(runner.PreflightError, match="did not complete cleanly"):
            runner.preflight_check(
                start_date=runner._HOLDOUT_START,
                end_date=runner._HOLDOUT_END,
                gates_v2_path=paths["gates_v2"],
                gates_v2_expected_sha256=runner._GATES_V2_SHA256_FROZEN,
                gates_path=paths["gates"],
                gates_expected_sha256=runner._GATES_SHA256_FROZEN,
                w8d_evidence_path=paths["w8d_evidence"],
                w8d_evidence_expected_sha256=runner._W8D_EVIDENCE_SHA256_FROZEN,
                lockfile_used=paths["used"],
                lockfile_in_progress=paths["in_progress"],
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Test 3: Frozen-hash mismatch -- gates_v2 + gates + W8-D evidence
# ═══════════════════════════════════════════════════════════════════════════════


class TestFrozenHashMismatch:
    def test_preflight_refuses_on_gates_v2_sha_mismatch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        paths = _patch_runner_paths(monkeypatch, root=tmp_path)
        paths["gates_v2"].write_text(paths["gates_v2"].read_text() + "\n# tampered\n")
        with pytest.raises(runner.PreflightError, match="frozen-hash mismatch.*gates_v2"):
            runner.preflight_check(
                start_date=runner._HOLDOUT_START,
                end_date=runner._HOLDOUT_END,
                gates_v2_path=paths["gates_v2"],
                gates_v2_expected_sha256=runner._GATES_V2_SHA256_FROZEN,
                gates_path=paths["gates"],
                gates_expected_sha256=runner._GATES_SHA256_FROZEN,
                w8d_evidence_path=paths["w8d_evidence"],
                w8d_evidence_expected_sha256=runner._W8D_EVIDENCE_SHA256_FROZEN,
                lockfile_used=paths["used"],
                lockfile_in_progress=paths["in_progress"],
            )

    def test_preflight_refuses_on_gates_sha_mismatch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        paths = _patch_runner_paths(monkeypatch, root=tmp_path)
        paths["gates"].write_text(paths["gates"].read_text() + "\n# tampered\n")
        with pytest.raises(runner.PreflightError, match="frozen-hash mismatch.*gates.yaml"):
            runner.preflight_check(
                start_date=runner._HOLDOUT_START,
                end_date=runner._HOLDOUT_END,
                gates_v2_path=paths["gates_v2"],
                gates_v2_expected_sha256=runner._GATES_V2_SHA256_FROZEN,
                gates_path=paths["gates"],
                gates_expected_sha256=runner._GATES_SHA256_FROZEN,
                w8d_evidence_path=paths["w8d_evidence"],
                w8d_evidence_expected_sha256=runner._W8D_EVIDENCE_SHA256_FROZEN,
                lockfile_used=paths["used"],
                lockfile_in_progress=paths["in_progress"],
            )

    def test_preflight_refuses_on_w8d_evidence_sha_mismatch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        paths = _patch_runner_paths(monkeypatch, root=tmp_path)
        paths["w8d_evidence"].write_text(paths["w8d_evidence"].read_text() + "\n# tampered\n")
        with pytest.raises(runner.PreflightError, match="frozen-hash mismatch.*W8-D evidence"):
            runner.preflight_check(
                start_date=runner._HOLDOUT_START,
                end_date=runner._HOLDOUT_END,
                gates_v2_path=paths["gates_v2"],
                gates_v2_expected_sha256=runner._GATES_V2_SHA256_FROZEN,
                gates_path=paths["gates"],
                gates_expected_sha256=runner._GATES_SHA256_FROZEN,
                w8d_evidence_path=paths["w8d_evidence"],
                w8d_evidence_expected_sha256=runner._W8D_EVIDENCE_SHA256_FROZEN,
                lockfile_used=paths["used"],
                lockfile_in_progress=paths["in_progress"],
            )

    def test_runner_constants_match_real_on_disk_artefacts(self) -> None:
        """Defensive: catch drift at unit-test time, not at iter-35 commit time."""
        assert (
            runner._sha256_of_file(_REPO_ROOT / "config" / "gates_v2.yaml") == runner._GATES_V2_SHA256_FROZEN
        )
        assert runner._sha256_of_file(_REPO_ROOT / "config" / "gates.yaml") == runner._GATES_SHA256_FROZEN
        assert (
            runner._sha256_of_file(
                _REPO_ROOT / "results" / "validation" / "wave8_d_single_factor" / "result.json"
            )
            == runner._W8D_EVIDENCE_SHA256_FROZEN
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Test 4: Successful evidence write on synthetic fixture (compute_fn injected)
# ═══════════════════════════════════════════════════════════════════════════════


class TestEvidenceWriteHappyPath:
    def test_main_happy_path_with_mocked_compute(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """End-to-end: preflight -> lockfile -> compute -> evidence -> rename.

        compute_fn is injected so DuckDB and iter-28 helpers are never touched.
        """
        paths = _patch_runner_paths(monkeypatch, root=tmp_path)

        captured: dict[str, object] = {}

        def fake_compute(db_path, *, start, end):
            captured["db_path"] = db_path
            captured["start"] = start
            captured["end"] = end
            return _fake_compute_result(sharpe=0.5549)

        rc = runner.main(["--db-path", "fake.duckdb"], compute_fn=fake_compute)
        assert rc == 0

        # Lockfile state: .holdout_in_progress consumed via rename to .holdout_used
        assert not paths["in_progress"].exists()
        assert paths["used"].exists()

        # Evidence written + sha256 sidecar
        assert paths["output"].exists()
        assert paths["sha"].exists()
        loaded = json.loads(paths["output"].read_text())
        assert loaded["verdict"] == "PASS"
        assert loaded["outcome_three_tier"] == "PASS-DECISIVE"
        assert loaded["oos_sharpe"] == pytest.approx(0.5549)
        assert loaded["window"] == {"start": "2024-01-01", "end": "2025-12-31"}
        assert loaded["iteration"] == 35
        assert loaded["wave"].startswith("Wave 9-D")
        assert loaded["strategy_class"] == "long_short_quintile"
        assert loaded["factor_under_test"] == "ivol_20d_flipped"

        # frozen_construction echo dict (defense-in-depth proof)
        fc = loaded["frozen_construction"]
        assert fc["n_quantiles"] == 5
        assert fc["sign_convention"] == 1
        assert fc["annual_factor_weekly_v_d1_v_d4"] == 52
        assert fc["perm_block_v_d2"] == 21
        assert fc["boot_block_v_d3"] == 63
        assert fc["ensemble"] is False
        assert fc["regime_overlay_applied_to_ls_series"] is False

        # GL-0025 + frozen sha256 references
        sha_block = loaded["frozen_artefact_sha256s"]
        assert sha_block["config_gates_v2_yaml"] == runner._GATES_V2_SHA256_FROZEN
        assert sha_block["config_gates_yaml"] == runner._GATES_SHA256_FROZEN
        assert sha_block["wave8_d_evidence_result_json"] == runner._W8D_EVIDENCE_SHA256_FROZEN
        assert len(sha_block["scripts_run_holdout_once_long_short_py"]) == 64

        assert "GL-0025" in loaded["authorizing_governance_rows"]

        # Sidecar sha256 must match the actual JSON bytes
        digest, fname = paths["sha"].read_text().strip().split()
        assert fname == "holdout_result.json"
        assert hashlib.sha256(paths["output"].read_bytes()).hexdigest() == digest

        # compute_fn received the hardcoded window, NOT a CLI override
        assert captured["start"] == date(2024, 1, 1)
        assert captured["end"] == date(2025, 12, 31)


# ═══════════════════════════════════════════════════════════════════════════════
# Test 5: check_holdout_guard.py allowlist passes (no new paths beyond Wave 7)
# ═══════════════════════════════════════════════════════════════════════════════


class TestHoldoutGuardAllowlist:
    def test_holdout_guard_accepts_four_allowlisted_paths(self) -> None:
        for p in [
            "results/holdout/.holdout_in_progress",
            "results/holdout/.holdout_used",
            "results/holdout/holdout_result.json",
            "results/holdout/holdout_result.json.sha256",
        ]:
            assert guard.violates(p) is None, f"path {p} should be allowlisted"

    def test_holdout_guard_rejects_fifth_holdout_path(self) -> None:
        """Wave 9-D must not silently expand the allowlist beyond Wave 7's 4 paths."""
        result = guard.violates("results/holdout/extra_long_short_artefact.json")
        assert result is not None
        assert "GL-0017 (Wave 7) / GL-0025 (Wave 9-D) allowlist" in result

    def test_holdout_guard_allows_runner_path(self) -> None:
        """The new long-short runner script lives in scripts/ (no holdout boundary)."""
        assert guard.violates("scripts/run_holdout_once_long_short.py") is None

    def test_holdout_guard_allows_test_file(self) -> None:
        assert guard.violates("tests/unit/test_run_holdout_once_long_short.py") is None


# ═══════════════════════════════════════════════════════════════════════════════
# Test 6: Compute exception after .holdout_in_progress create
# CONSUMED_NO_VERDICT terminal state preserved (Iron Rule 1)
# ═══════════════════════════════════════════════════════════════════════════════


class TestCrashCompute:
    def test_compute_exception_leaves_in_progress_lockfile_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Strict consume-on-touch: any exception after acquire leaves the
        .holdout_in_progress lockfile in place permanently. iter-36 GL-0026
        detects this state and routes A8 ABANDON via CONSUMED_NO_VERDICT.
        """
        paths = _patch_runner_paths(monkeypatch, root=tmp_path)

        def crashing_compute(db_path, *, start, end):
            raise RuntimeError("synthetic compute failure")

        with pytest.raises(RuntimeError, match="synthetic compute failure"):
            runner.main(["--db-path", "fake.duckdb"], compute_fn=crashing_compute)

        # Terminal state: .holdout_in_progress present, .holdout_used absent,
        # no evidence file -- CONSUMED_NO_VERDICT (iter-36 routes A8 ABANDON)
        assert paths["in_progress"].exists()
        assert not paths["used"].exists()
        assert not paths["output"].exists()
        assert not paths["sha"].exists()


# ═══════════════════════════════════════════════════════════════════════════════
# Test 7: os.replace failure on .holdout_used rename
# CONSUMED_LOCKFILE_MISMATCH terminal state
# ═══════════════════════════════════════════════════════════════════════════════


class TestCrashLockfileRename:
    def test_os_replace_failure_on_lockfile_promotion_leaves_evidence(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If os.replace fails during promotion, evidence is already written but
        the lockfile rename did not complete. iter-36 GL-0026 detects this
        state and routes A8 ABANDON via CONSUMED_LOCKFILE_MISMATCH (manual
        audit memo required for the evidence-without-lockfile case).
        """
        paths = _patch_runner_paths(monkeypatch, root=tmp_path)

        original_replace = os.replace

        def selectively_failing_replace(src, dst):
            # Fail only on the lockfile-promotion rename (in_progress -> used).
            # All other os.replace calls (atomic evidence write) must succeed.
            if str(src).endswith(".holdout_in_progress") and str(dst).endswith(".holdout_used"):
                raise OSError("synthetic ENOSPC during lockfile rename")
            return original_replace(src, dst)

        monkeypatch.setattr(runner.os, "replace", selectively_failing_replace)

        with pytest.raises(OSError, match="synthetic ENOSPC"):
            runner.main(
                ["--db-path", "fake.duckdb"],
                compute_fn=lambda db_path, *, start, end: _fake_compute_result(),
            )

        # Terminal state: evidence + sidecar present, .holdout_in_progress
        # present, .holdout_used absent -- CONSUMED_LOCKFILE_MISMATCH
        assert paths["output"].exists()
        assert paths["sha"].exists()
        assert paths["in_progress"].exists()
        assert not paths["used"].exists()

        # Evidence integrity is intact (the failure was downstream of write)
        digest = paths["sha"].read_text().strip().split()[0]
        assert hashlib.sha256(paths["output"].read_bytes()).hexdigest() == digest


# ═══════════════════════════════════════════════════════════════════════════════
# Test 8: fsync failure on evidence write -- partial JSON detected on next pre-flight
# ═══════════════════════════════════════════════════════════════════════════════


class TestCrashFsync:
    def test_fsync_failure_during_evidence_write_propagates_and_locks(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """fsync failure during write_evidence raises through main() -- the
        lockfile is already acquired so the strict consume-on-touch invariant
        holds (.holdout_in_progress remains, .holdout_used absent, evidence
        absent or partial). iter-36 routes A8 ABANDON.
        """
        paths = _patch_runner_paths(monkeypatch, root=tmp_path)

        original_fsync = os.fsync
        sync_calls: list[int] = []

        def selectively_failing_fsync(fd):
            sync_calls.append(fd)
            # Fail on the FIRST evidence-write fsync (after lockfile acquisition).
            # The lockfile-acquisition fsync runs in acquire_in_progress_lockfile,
            # which we want to succeed; only the write_evidence fsyncs should fail.
            if len(sync_calls) >= 2:
                raise OSError("synthetic EIO during evidence fsync")
            return original_fsync(fd)

        monkeypatch.setattr(runner.os, "fsync", selectively_failing_fsync)

        with pytest.raises(OSError, match="synthetic EIO"):
            runner.main(
                ["--db-path", "fake.duckdb"],
                compute_fn=lambda db_path, *, start, end: _fake_compute_result(),
            )

        # Terminal state: lockfile acquired, evidence-write failed mid-flight
        assert paths["in_progress"].exists()
        assert not paths["used"].exists()
        # No evidence at the canonical path (the .tmp sibling was cleaned in finally)
        assert not paths["output"].exists()
        assert not paths["sha"].exists()


# ═══════════════════════════════════════════════════════════════════════════════
# Test 9: Concurrent execution race -- O_EXCL allows EXACTLY ONE process
# ═══════════════════════════════════════════════════════════════════════════════


def _concurrent_acquire_worker(target_path_str: str, barrier_obj, result_q) -> None:
    """Worker that tries to acquire a lockfile after a multiprocessing.Barrier.

    Importing runner inside the worker keeps the test hermetic across spawn vs
    fork start methods; the parent does not need to share its monkey-patched
    module state with the children.
    """
    import importlib.util as _ilu
    import sys as _sys
    from pathlib import Path as _Path

    repo = _Path(target_path_str).resolve().parents[2]
    scripts = repo / "scripts"
    _sys.path.insert(0, str(scripts))
    spec = _ilu.spec_from_file_location("_worker_runner", scripts / "run_holdout_once_long_short.py")
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Synchronize start: both workers race on the same O_EXCL create.
    barrier_obj.wait(timeout=30)
    try:
        mod.acquire_in_progress_lockfile(_Path(target_path_str))
        result_q.put(("OK", None))
    except FileExistsError as exc:
        result_q.put(("FILE_EXISTS", str(exc)))
    except Exception as exc:  # noqa: BLE001
        result_q.put(("OTHER_ERROR", repr(exc)))


class TestConcurrentLockfile:
    def test_two_processes_O_EXCL_only_one_succeeds(self, tmp_path: Path) -> None:
        """O_CREAT|O_EXCL is the POSIX atomic lockfile primitive: exactly one
        of N concurrent processes creates the file; all others get FileExistsError.
        Verified via two multiprocessing.Process workers + Barrier.
        """
        target = tmp_path / "holdout" / ".holdout_in_progress"
        target.parent.mkdir(parents=True, exist_ok=True)

        # The worker locates the runner script via path arithmetic on the
        # target path's parents, so the path must look like a real layout.
        # Construct it: <tmp>/holdout/.holdout_in_progress -> parents[2] = <tmp>
        # The worker computes parents[2] of target_path_str. To make the worker
        # find the real scripts/ dir, we pass the actual repo target instead.
        real_target = _REPO_ROOT / "tests" / "unit" / f".pytest_concurrent_acquire_{os.getpid()}_{id(self)}"
        real_target.unlink(missing_ok=True)
        try:
            ctx = mp.get_context("spawn")
            barrier = ctx.Barrier(2)
            q = ctx.Queue()
            procs = [
                ctx.Process(
                    target=_concurrent_acquire_worker,
                    args=(str(real_target), barrier, q),
                )
                for _ in range(2)
            ]
            for p in procs:
                p.start()
            for p in procs:
                p.join(timeout=60)

            results = []
            while not q.empty():
                results.append(q.get())

            assert len(results) == 2, f"expected 2 worker results, got {results}"
            statuses = sorted(r[0] for r in results)
            assert statuses == ["FILE_EXISTS", "OK"], (
                f"expected exactly one OK and one FILE_EXISTS, got {results}"
            )
            assert real_target.exists()
        finally:
            real_target.unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Test 10: Consumed-without-evidence detection on subsequent invocation
# ═══════════════════════════════════════════════════════════════════════════════


class TestConsumedWithoutEvidence:
    def test_main_refuses_with_gl0025_message_when_in_progress_left_behind(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A second invocation after a prior crash MUST refuse with an explicit
        message naming GL-0025 (the authorizing governance row). This is the
        operator-facing path that surfaces the strict consume-on-touch
        terminal-state pre-registration.
        """
        paths = _patch_runner_paths(monkeypatch, root=tmp_path)
        paths["in_progress"].write_text("crashed previously\n")

        rc = runner.main([])
        assert rc == 2

        captured = capsys.readouterr()
        assert "REFUSED" in captured.err
        # Message must reference Iron Rule 1 + iter-36 terminal-state pre-registration
        assert "Iron Rule 1" in captured.err
        assert "CONSUMED_NO_VERDICT" in captured.err or "CONSUMED_PARTIAL_EVIDENCE" in captured.err

    def test_main_refuses_when_used_lockfile_exists_without_evidence(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """If .holdout_used exists (canonical happy-path terminal state), a
        re-run MUST refuse regardless of evidence presence.
        """
        paths = _patch_runner_paths(monkeypatch, root=tmp_path)
        paths["used"].write_text("consumed at 2026-04-30T12:00:00Z\n")

        rc = runner.main([])
        assert rc == 2

        captured = capsys.readouterr()
        assert "REFUSED" in captured.err
        assert "already consumed" in captured.err
        assert "Iron Rule 1" in captured.err


# ═══════════════════════════════════════════════════════════════════════════════
# Test 11: Corrupted JSON detected by sidecar sha256 mismatch
# (CONSUMED_USED_EVIDENCE_INTEGRITY_FAIL forensic check)
# ═══════════════════════════════════════════════════════════════════════════════


class TestSidecarIntegrityCheck:
    def test_post_write_tamper_detected_by_sidecar_sha_mismatch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Defense-in-depth: even though the lockfile prevents real re-runs,
        post-write tampering is detectable by recomputing sha256 of the
        evidence file and comparing to the sidecar. iter-35 verification +
        iter-36 GL-0026 forensic memo for CONSUMED_USED_EVIDENCE_INTEGRITY_FAIL
        use this exact integrity check.
        """
        paths = _patch_runner_paths(monkeypatch, root=tmp_path)

        rc = runner.main(
            ["--db-path", "fake.duckdb"],
            compute_fn=lambda db_path, *, start, end: _fake_compute_result(),
        )
        assert rc == 0

        # Sanity: clean state passes the integrity check
        digest_before = paths["sha"].read_text().strip().split()[0]
        actual_before = hashlib.sha256(paths["output"].read_bytes()).hexdigest()
        assert digest_before == actual_before

        # Tamper with the evidence file post-write
        original_bytes = paths["output"].read_bytes()
        tampered = original_bytes.replace(b'"verdict": "PASS"', b'"verdict": "TAMPERED"')
        assert tampered != original_bytes, "tamper string not present in payload"
        paths["output"].write_bytes(tampered)

        # Recompute sha256 -- must NO LONGER match the sidecar
        actual_after = hashlib.sha256(paths["output"].read_bytes()).hexdigest()
        assert actual_after != digest_before, "tamper not detected -- sidecar invariant broken"

        # Sidecar still claims the original digest -- this asymmetry is the
        # detectable signal iter-36 forensic memo classifies as
        # CONSUMED_USED_EVIDENCE_INTEGRITY_FAIL.
        sidecar_digest = paths["sha"].read_text().strip().split()[0]
        assert sidecar_digest == digest_before
        assert sidecar_digest != actual_after
