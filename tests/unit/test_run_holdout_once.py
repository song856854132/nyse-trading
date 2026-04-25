"""Unit tests for the Wave 7 / iter-26 holdout runner (Iron Rule 10 pre-land).

Scope (mirrors the GL-0017 Iron Rule 10 P1-4 minimum test scope):

    (a) hardcoded 2024-01-01..2025-12-31 window enforcement
    (b) refusal when .holdout_used or .holdout_in_progress exists
    (c) refusal on frozen-hash mismatch (gates_v2.yaml + baseline ensemble)
    (d) successful write of holdout_result.json + .sha256 on a fixture
        (compute_fn is mocked -- DuckDB is NOT hit; iter-19 helpers are NOT imported)
    (e) check_holdout_guard.py 4-path allowlist passes

The tests are hermetic. They never touch the real ``results/holdout/`` directory
on disk -- ``runner._LOCKFILE_USED`` and friends are monkey-patched onto a
tmp-path-rooted layout so a failed assertion cannot accidentally consume the
holdout. They never import iter-19 helpers; ``compute_fn`` is mocked out at
the ``main(..., compute_fn=...)`` injection point.

The test file is the operational evidence that the pre-landed holdout runner
is fit for iter-26 use; if any of these tests regress, the runner MUST be
re-pre-landed in a separate commit before iter-26.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"
sys.path.insert(0, str(_SCRIPTS))

_RUNNER_SPEC = importlib.util.spec_from_file_location(
    "run_holdout_once",
    _SCRIPTS / "run_holdout_once.py",
)
assert _RUNNER_SPEC is not None and _RUNNER_SPEC.loader is not None
runner = importlib.util.module_from_spec(_RUNNER_SPEC)
sys.modules["run_holdout_once"] = runner
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


def _seed_frozen_gates_yaml(root: Path) -> Path:
    """Copy the real ``config/gates_v2.yaml`` into ``root`` so its sha256 is
    bit-identical to the GL-0014 frozen hash. Tests that intentionally mutate
    this file should do so AFTER calling this helper.
    """
    src = _REPO_ROOT / "config" / "gates_v2.yaml"
    dst_dir = root / "config"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / "gates_v2.yaml"
    shutil.copyfile(src, dst)
    return dst


def _seed_baseline_ensemble(root: Path) -> Path:
    """Create a stub iter-19 baseline ensemble file. Existence is what the
    preflight checks; contents are never read by the runner.
    """
    dst = root / "results" / "ensemble" / "iter19_v2_phase3" / "ensemble_result.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("{}")
    return dst


def _seed_holdout_layout(root: Path) -> dict[str, Path]:
    """Lay out a ``results/holdout/`` directory under ``root`` and return the
    paths the runner will use. Lockfiles are NOT created -- callers create
    them when they want to test refusal paths.
    """
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
    """Install a tmp-path-rooted layout onto the runner module's path constants.

    This is the central mechanism by which the tests stay hermetic. Without
    this, a buggy test could end up creating ``results/holdout/.holdout_used``
    in the real repo and consuming the holdout for everyone.
    """
    gates_path = _seed_frozen_gates_yaml(root)
    baseline_path = _seed_baseline_ensemble(root)
    layout = _seed_holdout_layout(root)
    monkeypatch.setattr(runner, "_GATES_V2_PATH", gates_path)
    monkeypatch.setattr(runner, "_BASELINE_ENSEMBLE_PATH", baseline_path)
    monkeypatch.setattr(runner, "_HOLDOUT_DIR", layout["dir"])
    monkeypatch.setattr(runner, "_LOCKFILE_USED", layout["used"])
    monkeypatch.setattr(runner, "_LOCKFILE_IN_PROGRESS", layout["in_progress"])
    monkeypatch.setattr(runner, "_OUTPUT_PATH", layout["output"])
    monkeypatch.setattr(runner, "_OUTPUT_SHA_PATH", layout["sha"])
    return {
        "gates": gates_path,
        "baseline": baseline_path,
        **layout,
    }


def _fake_compute_result() -> dict:
    """Return a compute_fn-shaped dict that build_payload can consume.

    Mirrors the structure of ``_compute_holdout_ensemble`` output with a
    fixture-grade Sharpe of 0.5549 (matches iter-19 baseline) so the
    PASS-DECISIVE branch of three_tier_outcome fires.
    """
    return {
        "factor_diagnostics": {
            "ivol_20d_flipped": {"n_panel_rows": 100},
            "piotroski_f_score": {"n_panel_rows": 100},
            "momentum_2_12": {"n_panel_rows": 100},
            "accruals": {"n_panel_rows": 100},
            "profitability": {"n_panel_rows": 100},
        },
        "n_rebalance_dates": 104,
        "n_panel_rows": {
            "ivol_20d_flipped": 100,
            "piotroski_f_score": 100,
            "momentum_2_12": 100,
            "accruals": 100,
            "profitability": 100,
        },
        "n_forward_return_rows": 5000,
        "n_ensemble_rows": 5000,
        "n_ensemble_dates": 104,
        "rho": {
            "mean_off_diagonal": 0.834,
            "n_pairs_used": 10,
            "expected_n_pairs": 10,
            "pairwise_correlations": {},
        },
        "summary": {
            "oos_sharpe": 0.5549,
            "ic_mean": 0.0123,
            "ic_ir": 0.42,
            "perm_p_value": 0.018,
            "max_drawdown": -0.142,
        },
        "factor_sharpes_used": {
            "ivol_20d_flipped": 1.0,
            "piotroski_f_score": 1.0,
            "momentum_2_12": 1.0,
            "accruals": 1.0,
            "profitability": 1.0,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# (a) Hardcoded 2024-01-01..2025-12-31 window enforcement
# ═══════════════════════════════════════════════════════════════════════════════


class TestWindowEnforcement:
    def test_holdout_window_constants_are_2024_2025(self) -> None:
        from datetime import date

        assert date(2024, 1, 1) == runner._HOLDOUT_START
        assert date(2025, 12, 31) == runner._HOLDOUT_END

    def test_main_argparse_does_not_accept_start_date_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Iron Rule 1: holdout window is hardcoded; CLI may NOT override."""
        _patch_runner_paths(monkeypatch, root=tmp_path)
        with pytest.raises(SystemExit) as exc:
            runner.main(["--start-date", "2023-01-01"])
        # argparse exits 2 on unrecognized arg
        assert exc.value.code == 2

    def test_main_argparse_does_not_accept_end_date_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_runner_paths(monkeypatch, root=tmp_path)
        with pytest.raises(SystemExit) as exc:
            runner.main(["--end-date", "2030-12-31"])
        assert exc.value.code == 2

    def test_preflight_window_mismatch_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from datetime import date

        paths = _patch_runner_paths(monkeypatch, root=tmp_path)
        with pytest.raises(runner.PreflightError, match="window mismatch"):
            runner.preflight_check(
                start_date=date(2023, 1, 1),
                end_date=runner._HOLDOUT_END,
                gates_v2_path=paths["gates"],
                gates_v2_expected_sha256=runner._GATES_V2_SHA256_FROZEN,
                baseline_path=paths["baseline"],
                lockfile_used=paths["used"],
                lockfile_in_progress=paths["in_progress"],
            )
        with pytest.raises(runner.PreflightError, match="window mismatch"):
            runner.preflight_check(
                start_date=runner._HOLDOUT_START,
                end_date=date(2026, 6, 30),
                gates_v2_path=paths["gates"],
                gates_v2_expected_sha256=runner._GATES_V2_SHA256_FROZEN,
                baseline_path=paths["baseline"],
                lockfile_used=paths["used"],
                lockfile_in_progress=paths["in_progress"],
            )


# ═══════════════════════════════════════════════════════════════════════════════
# (b) Refusal when .holdout_used or .holdout_in_progress exists
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
                gates_v2_path=paths["gates"],
                gates_v2_expected_sha256=runner._GATES_V2_SHA256_FROZEN,
                baseline_path=paths["baseline"],
                lockfile_used=paths["used"],
                lockfile_in_progress=paths["in_progress"],
            )

    def test_preflight_refuses_when_holdout_in_progress_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A leftover .holdout_in_progress file means a prior run crashed.
        Iron Rule 1 + Codex iter-21 review: partial = consumed; no rerun."""
        paths = _patch_runner_paths(monkeypatch, root=tmp_path)
        paths["in_progress"].write_text("crashed at 2026-04-30T12:00:00Z\n")
        with pytest.raises(runner.PreflightError, match="did not complete cleanly"):
            runner.preflight_check(
                start_date=runner._HOLDOUT_START,
                end_date=runner._HOLDOUT_END,
                gates_v2_path=paths["gates"],
                gates_v2_expected_sha256=runner._GATES_V2_SHA256_FROZEN,
                baseline_path=paths["baseline"],
                lockfile_used=paths["used"],
                lockfile_in_progress=paths["in_progress"],
            )


# ═══════════════════════════════════════════════════════════════════════════════
# (c) Refusal on frozen-hash mismatch
# ═══════════════════════════════════════════════════════════════════════════════


class TestFrozenHashMismatch:
    def test_preflight_refuses_on_gates_v2_sha_mismatch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        paths = _patch_runner_paths(monkeypatch, root=tmp_path)
        # Mutate gates_v2.yaml so its sha256 no longer matches the frozen value.
        paths["gates"].write_text(paths["gates"].read_text() + "\n# tampered\n")
        with pytest.raises(runner.PreflightError, match="frozen-hash mismatch"):
            runner.preflight_check(
                start_date=runner._HOLDOUT_START,
                end_date=runner._HOLDOUT_END,
                gates_v2_path=paths["gates"],
                gates_v2_expected_sha256=runner._GATES_V2_SHA256_FROZEN,
                baseline_path=paths["baseline"],
                lockfile_used=paths["used"],
                lockfile_in_progress=paths["in_progress"],
            )

    def test_preflight_refuses_when_gates_v2_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        paths = _patch_runner_paths(monkeypatch, root=tmp_path)
        paths["gates"].unlink()
        with pytest.raises(runner.PreflightError, match="frozen artefact missing"):
            runner.preflight_check(
                start_date=runner._HOLDOUT_START,
                end_date=runner._HOLDOUT_END,
                gates_v2_path=paths["gates"],
                gates_v2_expected_sha256=runner._GATES_V2_SHA256_FROZEN,
                baseline_path=paths["baseline"],
                lockfile_used=paths["used"],
                lockfile_in_progress=paths["in_progress"],
            )

    def test_preflight_refuses_when_baseline_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        paths = _patch_runner_paths(monkeypatch, root=tmp_path)
        paths["baseline"].unlink()
        with pytest.raises(runner.PreflightError, match="baseline iter-19 ensemble result missing"):
            runner.preflight_check(
                start_date=runner._HOLDOUT_START,
                end_date=runner._HOLDOUT_END,
                gates_v2_path=paths["gates"],
                gates_v2_expected_sha256=runner._GATES_V2_SHA256_FROZEN,
                baseline_path=paths["baseline"],
                lockfile_used=paths["used"],
                lockfile_in_progress=paths["in_progress"],
            )


# ═══════════════════════════════════════════════════════════════════════════════
# (d) Successful write of holdout_result.json + .sha256 on fixture
# ═══════════════════════════════════════════════════════════════════════════════


class TestThreeTierOutcome:
    def test_three_tier_outcome_labels(self) -> None:
        assert runner.three_tier_outcome(None) == "ABORT"
        assert runner.three_tier_outcome(-0.10) == "FAIL"
        assert runner.three_tier_outcome(0.0) == "FAIL"
        assert runner.three_tier_outcome(0.0001) == "PASS-WEAK"
        assert runner.three_tier_outcome(0.2999) == "PASS-WEAK"
        assert runner.three_tier_outcome(0.30) == "PASS-DECISIVE"
        assert runner.three_tier_outcome(0.5549) == "PASS-DECISIVE"


class TestAtomicLockfile:
    def test_acquire_in_progress_lockfile_is_atomic_excl(self, tmp_path: Path) -> None:
        target = tmp_path / "results" / "holdout" / ".holdout_in_progress"
        runner.acquire_in_progress_lockfile(target)
        assert target.exists()
        # Second attempt MUST fail -- O_CREAT|O_EXCL guarantees this.
        with pytest.raises(FileExistsError):
            runner.acquire_in_progress_lockfile(target)

    def test_promote_lockfile_renames_in_progress_to_used(self, tmp_path: Path) -> None:
        in_progress = tmp_path / ".holdout_in_progress"
        used = tmp_path / ".holdout_used"
        in_progress.write_text("created at 2026-04-30\n")
        runner.promote_lockfile_to_used(in_progress=in_progress, used=used)
        assert not in_progress.exists()
        assert used.exists()
        assert "created at 2026-04-30" in used.read_text()

    def test_promote_lockfile_raises_when_in_progress_missing(self, tmp_path: Path) -> None:
        with pytest.raises(runner.PreflightError, match="cannot promote lockfile"):
            runner.promote_lockfile_to_used(
                in_progress=tmp_path / ".does_not_exist",
                used=tmp_path / ".holdout_used",
            )


class TestEvidenceWrite:
    def test_write_evidence_creates_json_and_sha256(self, tmp_path: Path) -> None:
        output = tmp_path / "holdout_result.json"
        sha = tmp_path / "holdout_result.json.sha256"
        payload = {"verdict": "PASS", "oos_sharpe": 0.5549}
        runner.write_evidence(payload, output_path=output, sha_output_path=sha)
        assert output.exists()
        assert sha.exists()
        loaded = json.loads(output.read_text())
        assert loaded["verdict"] == "PASS"
        assert loaded["oos_sharpe"] == pytest.approx(0.5549)
        # sha file must contain the actual sha256 of the JSON bytes
        sha_text = sha.read_text().strip()
        digest, fname = sha_text.split()
        assert fname == "holdout_result.json"
        assert len(digest) == 64
        # Recompute and verify
        import hashlib

        recomputed = hashlib.sha256(output.read_bytes()).hexdigest()
        assert recomputed == digest


class TestBuildPayload:
    @pytest.mark.parametrize(
        "sharpe,expected_verdict,expected_outcome",
        [
            (0.5549, "PASS", "PASS-DECISIVE"),
            (0.15, "PASS", "PASS-WEAK"),
            (-0.10, "FAIL", "FAIL"),
            (0.0, "FAIL", "FAIL"),
            (None, "ABORT", "ABORT"),
        ],
    )
    def test_build_payload_three_tier_outcomes_consistent(
        self,
        sharpe: float | None,
        expected_verdict: str,
        expected_outcome: str,
    ) -> None:
        from datetime import date

        compute = _fake_compute_result()
        compute["summary"]["oos_sharpe"] = sharpe
        payload = runner.build_payload(
            compute_result=compute,
            start=date(2024, 1, 1),
            end=date(2025, 12, 31),
            runner_path=Path("/x/scripts/run_holdout_once.py"),
            runner_sha256="0" * 64,
            perm_reps=500,
        )
        assert payload["verdict"] == expected_verdict
        assert payload["outcome_three_tier"] == expected_outcome
        assert payload["window"] == {"start": "2024-01-01", "end": "2025-12-31"}
        assert payload["iteration"] == 26
        assert payload["wave"].startswith("Wave 7")
        # Construction-grammar identity invariants
        cgi = payload["construction_grammar_identity_with_iter19"]
        assert cgi["min_factor_coverage"] == 3
        assert cgi["n_active_factors"] == 5
        assert cgi["ensemble_aggregator"] == "equal_sharpe_simple_mean"
        assert cgi["annual_factor"] == 52
        assert cgi["perm_block_size"] == 21
        # Active factor universe must match GL-0014 frozen list
        assert sorted(payload["active_v2_factor_universe"]) == sorted(
            [
                "ivol_20d_flipped",
                "piotroski_f_score",
                "momentum_2_12",
                "accruals",
                "profitability",
            ]
        )


class TestMainEndToEnd:
    def test_main_happy_path_with_mocked_compute(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """End-to-end: preflight -> lockfile -> compute -> evidence -> rename.

        compute_fn is mocked so DuckDB and iter-19 helpers are never touched.
        """
        paths = _patch_runner_paths(monkeypatch, root=tmp_path)

        captured: dict[str, object] = {}

        def fake_compute(db_path, *, start, end, perm_reps):
            captured["db_path"] = db_path
            captured["start"] = start
            captured["end"] = end
            captured["perm_reps"] = perm_reps
            return _fake_compute_result()

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

        # compute_fn received the hardcoded window, NOT a CLI override
        from datetime import date

        assert captured["start"] == date(2024, 1, 1)
        assert captured["end"] == date(2025, 12, 31)
        assert captured["perm_reps"] == 500

    def test_main_dry_run_returns_zero_no_lockfile_left(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        paths = _patch_runner_paths(monkeypatch, root=tmp_path)
        rc = runner.main(["--dry-run"])
        assert rc == 0
        assert not paths["in_progress"].exists()
        assert not paths["used"].exists()
        assert not paths["output"].exists()

    def test_main_returns_2_when_holdout_used_exists(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        paths = _patch_runner_paths(monkeypatch, root=tmp_path)
        paths["used"].write_text("consumed earlier\n")
        rc = runner.main([])
        assert rc == 2
        captured = capsys.readouterr()
        assert "REFUSED" in captured.err
        assert "already consumed" in captured.err

    def test_main_returns_2_when_in_progress_exists(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        paths = _patch_runner_paths(monkeypatch, root=tmp_path)
        paths["in_progress"].write_text("crashed earlier\n")
        rc = runner.main([])
        assert rc == 2
        captured = capsys.readouterr()
        assert "REFUSED" in captured.err
        assert "did not complete cleanly" in captured.err


# ═══════════════════════════════════════════════════════════════════════════════
# (e) check_holdout_guard.py 4-path allowlist passes
# ═══════════════════════════════════════════════════════════════════════════════


class TestHoldoutGuardAllowlist:
    """Verify that ``scripts/check_holdout_guard.py`` accepts EXACTLY the four
    iter-26 holdout commit payload paths and rejects everything else under
    ``results/holdout/``. Any drift here will block iter-26 commits and force
    a guard edit + GL-0017 sha256 cite refresh.
    """

    def test_holdout_guard_accepts_four_allowlisted_paths(self) -> None:
        for p in [
            "results/holdout/.holdout_in_progress",
            "results/holdout/.holdout_used",
            "results/holdout/holdout_result.json",
            "results/holdout/holdout_result.json.sha256",
        ]:
            assert guard.violates(p) is None, f"path {p} should be allowlisted"

    def test_holdout_guard_rejects_fifth_holdout_path(self) -> None:
        # A fifth path under results/holdout/ MUST be rejected -- this prevents
        # silent expansion of the allowlist via a glob.
        result = guard.violates("results/holdout/extra_artefact.json")
        assert result is not None
        assert "GL-0017 iter-26 allowlist" in result

    def test_holdout_guard_rejects_2024_directory_component(self) -> None:
        # Iron Rule 1: paths with 2024 / 2025 directory components are rejected
        # outside tests/ and docs/.
        result = guard.violates("data/raw/2024/Q1/prices.csv")
        assert result is not None
        assert "holdout-year component" in result

    def test_holdout_guard_rejects_2025_directory_component(self) -> None:
        # Path component MUST be exactly "2025" (not a substring like
        # "screen_2025") -- the guard splits on path separators.
        result = guard.violates("results/screen/2025/factor_a/result.json")
        assert result is not None
        assert "holdout-year component" in result

    def test_holdout_guard_allows_2024_under_tests(self) -> None:
        # tests/ is exempt -- we legitimately need tests that reference holdout
        # years (e.g., to test the leakage detection itself).
        assert guard.violates("tests/unit/test_2024_leakage.py") is None
        assert guard.violates("tests/fixtures/2025_synthetic.csv") is None

    def test_holdout_guard_allows_2024_under_docs(self) -> None:
        assert guard.violates("docs/audit/2024_holdout_postmortem.md") is None
        assert guard.violates("docs/holdout/2025_window_design.md") is None

    def test_holdout_guard_returns_none_for_safe_path(self) -> None:
        assert guard.violates("src/nyse_core/factor_screening.py") is None
        assert guard.violates("scripts/run_holdout_once.py") is None


# ═══════════════════════════════════════════════════════════════════════════════
# Sanity: real on-disk gates_v2.yaml has the expected frozen sha256
# ═══════════════════════════════════════════════════════════════════════════════


class TestFrozenHashAnchor:
    """Defensive check: the runner's hardcoded sha256 constant must match the
    ACTUAL on-disk gates_v2.yaml. If this drifts, every holdout run will
    refuse via PreflightError -- this test fires the alarm at unit-test time
    instead of at iter-26 commit time.
    """

    def test_runner_frozen_sha256_matches_real_gates_v2(self) -> None:
        actual = runner._sha256_of_file(_REPO_ROOT / "config" / "gates_v2.yaml")
        assert actual == runner._GATES_V2_SHA256_FROZEN, (
            f"real gates_v2.yaml sha256 has drifted from runner constant: "
            f"got {actual}, expected {runner._GATES_V2_SHA256_FROZEN}. "
            "Either the file was tampered (Iron Rule 8 violation) or the "
            "runner's frozen-hash constant needs a synchronized update + "
            "GL-0017 sha256 cite refresh."
        )
