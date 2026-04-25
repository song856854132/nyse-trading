#!/usr/bin/env python3
"""Wave 7 / iter-26 -- One-shot 2024-2025 holdout consumption (GL-0020).

Pre-landed under Iron Rule 10 (P0-C deliverable from GL-0017 iter-21
pre-registration). MUST land in a separate commit BEFORE iter-26 attempts
holdout consumption; same-iteration introduction of new holdout-running code
AND consumption of the one-shot 2024-2025 holdout is forbidden.

Mirrors iter-19 #144 ensemble construction grammar EXACTLY:

- Active v2 factor universe (GL-0014, frozen)::

    [ivol_20d_flipped, piotroski_f_score, momentum_2_12, accruals, profitability]

- K=3-of-N=5 coverage gate via ``compute_ensemble_weights(min_factor_coverage=3)``
- Equal-Sharpe simple-mean aggregation (uniform 1.0 per-factor weights, matches
  GL-0015 ceiling derivation; deviating to Sharpe-weighted would break
  construction-grammar identity with iter-19 #144 baseline +0.5549)
- Simple-mean rho over the 10 off-diagonal pairs of the 5x5 top-decile return
  correlation matrix (V2-PREREG-2026-04-24 sec 3.1)
- Deterministic tie-break seed: ``numpy.random.default_rng(seed=date.toordinal())``
- 5-day forward-return target (post-execution Monday-open to Friday-close)
- Sharpe annualization factor 52; permutation block_size 21, n_reps 500

Hardcoded window: 2024-01-01 -> 2025-12-31. No CLI override of dates.

Iron Rule 10 P1-4 test scope (covered by tests/unit/test_run_holdout_once.py):
  (a) hardcoded 2024-01-01..2025-12-31 window enforcement
  (b) refusal when .holdout_used or .holdout_in_progress exists
  (c) refusal on frozen-hash mismatch
  (d) successful write of holdout_result.json + .sha256 on fixture
  (e) check_holdout_guard.py 4-path allowlist passes

Atomic lockfile protocol (Codex iter-21 review requirement):
  1. preflight_check raises PreflightError on any precondition violation
  2. acquire_in_progress_lockfile creates .holdout_in_progress via O_EXCL
  3. Compute holdout ensemble (frozen iter-19 grammar)
  4. write_evidence atomically writes holdout_result.json + sha256 sidecar
  5. promote_lockfile_to_used renames .holdout_in_progress -> .holdout_used
     (POSIX atomic rename via os.replace)
  6. Crash semantics: partial = consumed (Iron Rule 1 invariant)
     -- if step 2 succeeds and step 5 fails, .holdout_in_progress remains and
     the holdout IS considered consumed; no re-runs permitted.

Three-tier outcome (REPORTING ONLY, not gating):
  - FAIL: Sharpe <= 0
  - PASS-WEAK: 0 < Sharpe < 0.30
  - PASS-DECISIVE: Sharpe >= 0.30

The DECISIVE binary verdict (Sharpe > 0) is the AP-6 holdout invariant per
docs/GOVERNANCE_LOG.md:101 "Sharpe > 0. No iteration after this test."
The three-tier label is a reporting construct that informs the iter-27
paper-stage decision but does NOT change the binary holdout PASS/FAIL.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

# Module constants -- referenced by name from main() so test monkeypatching
# of these names takes effect at call time. Do NOT thread them through main()
# default arguments (those are evaluated once at function-definition time and
# would not pick up monkeypatched values).
_HOLDOUT_START: date = date(2024, 1, 1)
_HOLDOUT_END: date = date(2025, 12, 31)

_REPO_ROOT: Path = Path(__file__).resolve().parent.parent
_GATES_V2_PATH: Path = _REPO_ROOT / "config" / "gates_v2.yaml"
_GATES_V2_SHA256_FROZEN: str = (
    "bd0fc5de89307dab36fe82c12e0d921a7fa145376e2ef01aad8d000dd92979d2"
)
_BASELINE_ENSEMBLE_PATH: Path = (
    _REPO_ROOT / "results" / "ensemble" / "iter19_v2_phase3" / "ensemble_result.json"
)

_HOLDOUT_DIR: Path = _REPO_ROOT / "results" / "holdout"
_LOCKFILE_USED: Path = _HOLDOUT_DIR / ".holdout_used"
_LOCKFILE_IN_PROGRESS: Path = _HOLDOUT_DIR / ".holdout_in_progress"
_OUTPUT_PATH: Path = _HOLDOUT_DIR / "holdout_result.json"
_OUTPUT_SHA_PATH: Path = _HOLDOUT_DIR / "holdout_result.json.sha256"

_DECISIVE_FLOOR: float = 0.30  # PASS-DECISIVE iff oos_sharpe >= this floor

_SRC: str = "scripts.run_holdout_once"


class PreflightError(RuntimeError):
    """Raised when a holdout-runner precondition fails. AP-6-terminal."""


def _sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def preflight_check(
    *,
    start_date: date,
    end_date: date,
    gates_v2_path: Path,
    gates_v2_expected_sha256: str,
    baseline_path: Path,
    lockfile_used: Path,
    lockfile_in_progress: Path,
) -> None:
    """Raise PreflightError on any Iron Rule 10 P1-4 (a)/(b)/(c) violation.

    Iron Rule 10 P1-4 mapped to this function:
      (a) hardcoded window enforcement -- start/end MUST equal module constants
      (b) lockfiles MUST NOT exist (used = re-run forbidden; in_progress =
          prior crash, partial = consumed under Iron Rule 1)
      (c) frozen-hash anchors -- gates_v2.yaml sha256 MUST match the GL-0014
          frozen value AND the iter-19 baseline ensemble result MUST exist
          (so we can hash-cite it in the holdout payload).
    """
    if start_date != _HOLDOUT_START or end_date != _HOLDOUT_END:
        raise PreflightError(
            f"holdout window mismatch: got {start_date}..{end_date}, "
            f"required {_HOLDOUT_START}..{_HOLDOUT_END} (hardcoded; "
            "no CLI override permitted under Iron Rule 1)"
        )
    if lockfile_used.exists():
        raise PreflightError(
            f"holdout already consumed (lockfile exists: {lockfile_used}); "
            "no re-runs permitted under Iron Rule 1"
        )
    if lockfile_in_progress.exists():
        raise PreflightError(
            f"prior holdout run did not complete cleanly "
            f"(lockfile exists: {lockfile_in_progress}); "
            "investigate crash; partial = consumed"
        )
    if not gates_v2_path.exists():
        raise PreflightError(
            f"frozen artefact missing: {gates_v2_path}"
        )
    actual_sha = _sha256_of_file(gates_v2_path)
    if actual_sha != gates_v2_expected_sha256:
        raise PreflightError(
            f"frozen-hash mismatch on {gates_v2_path}: "
            f"got {actual_sha}, expected {gates_v2_expected_sha256}"
        )
    if not baseline_path.exists():
        raise PreflightError(
            f"baseline iter-19 ensemble result missing: {baseline_path}"
        )


def acquire_in_progress_lockfile(path: Path) -> None:
    """Create .holdout_in_progress atomically via O_EXCL. Fsync to disk.

    O_CREAT | O_EXCL guarantees the create operation fails (FileExistsError /
    OSError EEXIST) if any file already exists at ``path``, preventing a TOCTOU
    race between preflight_check and lockfile acquisition.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    fd = os.open(str(path), flags, 0o644)
    try:
        marker = (
            f"{_dt.datetime.now(_dt.UTC).isoformat()}\n"
            f"pid={os.getpid()}\n"
            f"runner={_SRC}\n"
        )
        os.write(fd, marker.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def promote_lockfile_to_used(*, in_progress: Path, used: Path) -> None:
    """Atomic POSIX rename .holdout_in_progress -> .holdout_used.

    os.replace() is the POSIX atomic-rename primitive: either the target
    exists with the new name OR the rename fails entirely. There is no
    intermediate state where both names exist.
    """
    if not in_progress.exists():
        raise PreflightError(
            f"cannot promote lockfile: {in_progress} does not exist"
        )
    os.replace(str(in_progress), str(used))


def three_tier_outcome(oos_sharpe: float | None) -> str:
    """Map OOS Sharpe to FAIL / PASS-WEAK / PASS-DECISIVE / ABORT label.

    The three-tier outcome is a REPORTING construct, not a gating construct.
    The decisive binary verdict (PASS/FAIL on Sharpe > 0) is what the
    holdout invariant requires. ABORT is reserved for the case where the
    runner produced no Sharpe value (e.g., empty ensemble, computation
    aborted).
    """
    if oos_sharpe is None:
        return "ABORT"
    if oos_sharpe <= 0.0:
        return "FAIL"
    if oos_sharpe < _DECISIVE_FLOOR:
        return "PASS-WEAK"
    return "PASS-DECISIVE"


def write_evidence(
    payload: dict,
    *,
    output_path: Path,
    sha_output_path: Path,
) -> None:
    """Atomic write of holdout_result.json + sha256 sidecar (tmp + rename).

    Each file is written to a ``.tmp`` sibling, fsynced, then renamed via
    os.replace(). A crash mid-write leaves the original file (if any) intact;
    a crash mid-rename either leaves the temp file (cleaned up in finally) or
    completes the rename atomically.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, indent=2, sort_keys=True, default=str).encode("utf-8")
    tmp_main = output_path.with_suffix(output_path.suffix + ".tmp")
    tmp_sha = sha_output_path.with_suffix(sha_output_path.suffix + ".tmp")
    try:
        with tmp_main.open("wb") as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(tmp_main), str(output_path))
        digest = hashlib.sha256(body).hexdigest()
        sha_line = f"{digest}  {output_path.name}\n"
        with tmp_sha.open("wb") as f:
            f.write(sha_line.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(tmp_sha), str(sha_output_path))
    finally:
        if tmp_main.exists():
            tmp_main.unlink(missing_ok=True)
        if tmp_sha.exists():
            tmp_sha.unlink(missing_ok=True)


def _compute_holdout_ensemble(
    db_path: Path,
    *,
    start: date,
    end: date,
    perm_reps: int,
) -> dict:
    """Run the iter-19 #144 ensemble construction grammar over the holdout window.

    Imports happen at function scope so test cases that monkeypatch a
    ``compute_fn`` replacement don't pay the import cost or hit a missing
    DuckDB at module-load time. The function reuses iter-19 module-level
    helpers verbatim -- no parallel implementation, no parameter drift.
    """
    import pandas as pd

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from screen_factor import (  # noqa: E402
        _build_forward_returns,
        _load_fundamentals,
        _load_ohlcv,
        _weekly_fridays,
    )
    from simulate_v2_ensemble_phase3 import (  # noqa: E402
        _GATES_V2_SHA256,
        _V2_ACTIVE_FACTORS,
        _build_panel_with_rng_tiebreak,
        _simple_mean_rho,
        _summarize_ensemble,
    )

    from nyse_core.factor_screening import compute_ensemble_weights

    if _GATES_V2_SHA256 != _GATES_V2_SHA256_FROZEN:
        raise PreflightError(
            "internal sha256 constant drift: "
            f"simulate_v2_ensemble_phase3._GATES_V2_SHA256 = {_GATES_V2_SHA256}, "
            f"runner expected {_GATES_V2_SHA256_FROZEN}"
        )

    print(f"[1/5] Loading OHLCV {start} -> {end}", flush=True)
    ohlcv = _load_ohlcv(db_path, start, end)
    print(f"       rows={len(ohlcv):,}", flush=True)

    lookback_start = start - pd.Timedelta(days=400).to_pytimedelta()
    print(f"[2/5] Loading fundamentals {lookback_start} -> {end}", flush=True)
    fundamentals = _load_fundamentals(db_path, lookback_start, end)
    print(f"       rows={len(fundamentals):,}", flush=True)

    rebalance = _weekly_fridays(start, end)
    fwd_returns = _build_forward_returns(ohlcv, rebalance)
    print(
        f"[3/5] Forward-return rows: {len(fwd_returns):,} "
        f"(rebalance dates: {len(rebalance)})",
        flush=True,
    )

    print("[4/5] Building 5 factor panels with V2-PREREG RNG tie-break", flush=True)
    panels: dict = {}
    for fname, (compute_fn, sign, source, _) in _V2_ACTIVE_FACTORS.items():
        if source == "ohlcv":
            panel = _build_panel_with_rng_tiebreak(ohlcv, rebalance, compute_fn, sign, source)
        elif source == "fundamentals":
            panel = _build_panel_with_rng_tiebreak(fundamentals, rebalance, compute_fn, sign, source)
        else:
            raise ValueError(f"unknown data source for {fname!r}: {source}")
        if panel.empty:
            raise RuntimeError(f"factor panel empty for {fname!r}")
        panels[fname] = panel
        print(f"  {fname}: {len(panel)} rows", flush=True)

    # iter-19 #144 construction-grammar identity: uniform 1.0 per-factor weights.
    equal_sharpes = dict.fromkeys(panels.keys(), 1.0)
    ensemble_scores, _ens_diag = compute_ensemble_weights(
        panels, equal_sharpes, min_factor_coverage=3
    )

    print("[5/5] Computing summary metrics + simple-mean rho", flush=True)
    summary = _summarize_ensemble(ensemble_scores, fwd_returns, perm_reps=perm_reps)
    rho_mean, pair_corrs, n_pairs = _simple_mean_rho(panels, fwd_returns)

    n_dates = (
        int(ensemble_scores["date"].nunique())
        if not ensemble_scores.empty
        else 0
    )

    return {
        "factor_diagnostics": {
            name: {"n_panel_rows": int(len(panel))}
            for name, panel in panels.items()
        },
        "n_rebalance_dates": int(len(rebalance)),
        "n_panel_rows": {name: int(len(panel)) for name, panel in panels.items()},
        "n_forward_return_rows": int(len(fwd_returns)),
        "n_ensemble_rows": int(len(ensemble_scores)),
        "n_ensemble_dates": n_dates,
        "rho": {
            "mean_off_diagonal": rho_mean,
            "n_pairs_used": int(n_pairs),
            "expected_n_pairs": 10,
            "pairwise_correlations": pair_corrs,
        },
        "summary": summary,
        "factor_sharpes_used": equal_sharpes,
    }


def build_payload(
    *,
    compute_result: dict,
    start: date,
    end: date,
    runner_path: Path,
    runner_sha256: str,
    perm_reps: int,
) -> dict:
    """Assemble the canonical iter-26 holdout evidence payload."""
    summary = compute_result["summary"]
    oos_sharpe = summary.get("oos_sharpe")
    oos_sharpe_float = float(oos_sharpe) if oos_sharpe is not None else None
    outcome = three_tier_outcome(oos_sharpe_float)
    if oos_sharpe_float is None:
        decisive_verdict = "ABORT"
    elif oos_sharpe_float > 0.0:
        decisive_verdict = "PASS"
    else:
        decisive_verdict = "FAIL"
    return {
        "iteration": 26,
        "iteration_tag": "iter-26",
        "task_id": 156,
        "wave": "Wave 7 -- One-shot 2024-2025 holdout consumption (GL-0020)",
        "authorizing_governance_rows": [
            "GL-0014",
            "GL-0015",
            "GL-0016",
            "GL-0017",
            "GL-0018",
        ],
        "active_v2_factor_universe": [
            "accruals",
            "ivol_20d_flipped",
            "momentum_2_12",
            "piotroski_f_score",
            "profitability",
        ],
        "construction_grammar_identity_with_iter19": {
            "min_factor_coverage": 3,
            "n_active_factors": 5,
            "ensemble_aggregator": "equal_sharpe_simple_mean",
            "factor_sharpes_used": compute_result.get("factor_sharpes_used"),
            "rng_tiebreak_seed": "numpy.random.default_rng(seed=date.toordinal())",
            "annual_factor": 52,
            "perm_block_size": 21,
            "spec_source": "V2-PREREG-2026-04-24 + iter-19 #144 baseline",
        },
        "window": {"start": str(start), "end": str(end)},
        "perm_reps": int(perm_reps),
        "frozen_artefact_sha256s": {
            "config_gates_v2_yaml": _GATES_V2_SHA256_FROZEN,
            "scripts_run_holdout_once_py": runner_sha256,
        },
        "runner_path": str(runner_path),
        "factor_diagnostics": compute_result.get("factor_diagnostics", {}),
        "n_rebalance_dates": compute_result.get("n_rebalance_dates"),
        "n_panel_rows": compute_result.get("n_panel_rows"),
        "n_forward_return_rows": compute_result.get("n_forward_return_rows"),
        "n_ensemble_rows": compute_result.get("n_ensemble_rows"),
        "n_ensemble_dates": compute_result.get("n_ensemble_dates"),
        "rho": compute_result.get("rho", {}),
        "summary": summary,
        "oos_sharpe": oos_sharpe_float,
        "verdict": decisive_verdict,
        "verdict_decisive_floor": "Sharpe > 0 (GL-0020 binary)",
        "outcome_three_tier": outcome,
        "no_iteration_clause": (
            "Iron Rule 1 + GL-0020: holdout window 2024-01-01..2025-12-31 is "
            "one-shot; no parameter retuning, no factor re-screening, no gate "
            "threshold adjustment after this commit, regardless of outcome."
        ),
        "ap6_compliance": (
            "Pre-registered V1/V2/V3/V4 bars (GL-0017) cleared at iter-25 "
            "Branch A (GL-0018). Holdout-runner pre-landed (Iron Rule 10). "
            "Construction grammar bit-identical to iter-19 #144."
        ),
    }


def main(
    argv: list[str] | None = None,
    *,
    compute_fn: Callable[..., dict] | None = None,
) -> int:
    """Wave 7 / iter-26 holdout entry point.

    Module-constant references in this function body (rather than default
    arguments) ensure that test monkeypatching of e.g. ``runner._LOCKFILE_USED``
    takes effect at call time -- default arguments are evaluated once at
    function-definition time.
    """
    parser = argparse.ArgumentParser(
        description="Wave 7 / iter-26 one-shot 2024-2025 holdout runner",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path("research.duckdb"),
        help="path to research.duckdb (frozen iter-19 schema)",
    )
    parser.add_argument(
        "--perm-reps",
        type=int,
        default=500,
        help="bootstrap reps for permutation test (default 500, mirrors iter-19)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="run preflight only; do NOT acquire lockfile or compute",
    )
    args = parser.parse_args(argv)

    try:
        preflight_check(
            start_date=_HOLDOUT_START,
            end_date=_HOLDOUT_END,
            gates_v2_path=_GATES_V2_PATH,
            gates_v2_expected_sha256=_GATES_V2_SHA256_FROZEN,
            baseline_path=_BASELINE_ENSEMBLE_PATH,
            lockfile_used=_LOCKFILE_USED,
            lockfile_in_progress=_LOCKFILE_IN_PROGRESS,
        )
    except PreflightError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        print("DRY-RUN: preflight passed; no lockfile created, no compute run.", flush=True)
        return 0

    acquire_in_progress_lockfile(_LOCKFILE_IN_PROGRESS)

    if compute_fn is None:
        compute_fn = _compute_holdout_ensemble
    compute_result = compute_fn(
        args.db_path,
        start=_HOLDOUT_START,
        end=_HOLDOUT_END,
        perm_reps=args.perm_reps,
    )

    runner_sha256 = _sha256_of_file(Path(__file__).resolve())
    payload = build_payload(
        compute_result=compute_result,
        start=_HOLDOUT_START,
        end=_HOLDOUT_END,
        runner_path=Path(__file__).resolve(),
        runner_sha256=runner_sha256,
        perm_reps=args.perm_reps,
    )
    write_evidence(
        payload,
        output_path=_OUTPUT_PATH,
        sha_output_path=_OUTPUT_SHA_PATH,
    )

    promote_lockfile_to_used(
        in_progress=_LOCKFILE_IN_PROGRESS, used=_LOCKFILE_USED
    )

    oos = payload["oos_sharpe"]
    print("")
    print("WAVE 7 / iter-26 HOLDOUT (2024-2025) -- ONE-SHOT")
    print("=" * 66)
    if oos is not None:
        print(f"  OOS Sharpe       : {oos:+.4f}")
    else:
        print("  OOS Sharpe       : <None>")
    print(f"  Verdict (binary) : {payload['verdict']} (decisive floor Sharpe > 0)")
    print(f"  Three-tier label : {payload['outcome_three_tier']}")
    print(f"  Evidence         : {_OUTPUT_PATH}")
    print(f"  SHA256 sidecar   : {_OUTPUT_SHA_PATH}")
    print(f"  Lockfile state   : {_LOCKFILE_USED} (consumed)")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
