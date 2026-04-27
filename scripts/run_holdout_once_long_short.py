#!/usr/bin/env python3
"""Wave 9-D / iter-35 -- One-shot 2024-2025 holdout consumption (GL-0025).

Pre-landed under Iron Rule 10 + Iron Rule 12 (P0-E deliverable from GL-0025
pre-registration). MUST land in iter-33 SEPARATE commit BEFORE iter-34 GL-0025
governance row, which BEFORE iter-35 attempts holdout consumption. Same-iter
introduction of new holdout-running code AND consumption is forbidden.

Iron Rule 12 zero-transitive-authority attestation (verbatim 3 lines):
  1. ALL authority to consume the 2024-2025 holdout originates in GL-0025.
  2. GL-0024 routing GRANTS ZERO authority to consume; W8-D PASS verdict
     establishes ELIGIBILITY only.
  3. iter-33 P0-E pre-landed runner is DORMANT until GL-0025 commits;
     runner sha256 pin without committed governance row = NO authority.

Bit-identical iter-28 replay of `scripts/run_workstream_d_single_factor.py`
re-pointed at the 2024-2025 holdout window (Iron Rule 9 strict reading):
  - Strategy class: long-short quintile (n_quantiles=5)
  - Factor: ivol_20d_flipped (sign=+1 no negation, RNG tie-break)
  - V_D1: nyse_core.metrics.sharpe_ratio(annual_factor=52)  >= 0.30   (UNCHANGED)
  - V_D2: nyse_core.statistics.permutation_test(reps=500, block=21) < 0.05 (UNCHANGED)
  - V_D3: nyse_core.statistics.block_bootstrap_ci(reps=10000, block=63, alpha=0.05)
          ci_lower >= 0.20  (UNCHANGED)
  - V_D4: min(bull_sharpe, bear_sharpe) on SPY SMA200 split via UNCHANGED
          sharpe_ratio(annual_factor=52)                              >= 0.20

Hardcoded window: 2024-01-01 -> 2025-12-31. No CLI override of dates.
Hardcoded params (no config reads, no CLI flags). frozen_construction echo
in payload provides defense-in-depth against runner mutation.

Strict consume-on-touch lockfile protocol (Codex iter-21 + GL-0025 review):
  1. preflight_check raises PreflightError on any precondition violation
  2. acquire_in_progress_lockfile creates .holdout_in_progress via O_EXCL
  3. Compute V_D1..V_D4 via UNCHANGED nyse_core.metrics.sharpe_ratio +
     nyse_core.statistics.permutation_test/block_bootstrap_ci primitives
  4. write_evidence atomically writes holdout_result.json + sha256 sidecar
  5. promote_lockfile_to_used renames .holdout_in_progress -> .holdout_used
     via POSIX atomic os.replace (no intermediate state)
  6. ANY exception after step 2 = consumed forever (Iron Rule 1 invariant).
     iter-36 GL-0026 routes to A8 ABANDON via terminal-state pre-registration:
       CONSUMED_NO_VERDICT, CONSUMED_PARTIAL_EVIDENCE,
       CONSUMED_LOCKFILE_MISMATCH, CONSUMED_USED_EVIDENCE_INTEGRITY_FAIL.

Three-tier outcome (REPORTING ONLY, not gating):
  - FAIL          : Sharpe <= 0    -> A8 ABANDON
  - PASS-WEAK     : 0 < S < 0.30   -> A9 cost-drag DEFERRED to Wave 10
  - PASS-DECISIVE : Sharpe >= 0.30 -> Wave 10 paper-prep eligibility prereq

The DECISIVE binary verdict (Sharpe > 0 on V_D1) is the AP-6 holdout
invariant (GOVERNANCE_LOG.md GL-0025 + Lesson_Learn TWSE Rule §2.2).

Usage (DORMANT until GL-0025 commits):

    python3 scripts/run_holdout_once_long_short.py --db-path research.duckdb

Output: results/holdout/holdout_result.json (+ sha256 sidecar; lockfile rename).
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

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from screen_factor import (  # noqa: E402
    _build_forward_returns,
    _load_ohlcv,
    _weekly_fridays,
)

from nyse_core.factor_screening import compute_long_short_returns  # noqa: E402
from nyse_core.features.price_volume import compute_ivol_20d  # noqa: E402
from nyse_core.metrics import sharpe_ratio  # noqa: E402
from nyse_core.normalize import rank_percentile  # noqa: E402
from nyse_core.schema import COL_DATE  # noqa: E402
from nyse_core.statistics import block_bootstrap_ci, permutation_test  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Callable

# ---------------------------------------------------------------------------
# Hardcoded constants (Iron Rule 1 + Iron Rule 9 + Iron Rule 10 + Iron Rule 12)
# ---------------------------------------------------------------------------

_HOLDOUT_START: date = date(2024, 1, 1)
_HOLDOUT_END: date = date(2025, 12, 31)

_REPO_ROOT: Path = Path(__file__).resolve().parent.parent
_GATES_V2_PATH: Path = _REPO_ROOT / "config" / "gates_v2.yaml"
_GATES_PATH: Path = _REPO_ROOT / "config" / "gates.yaml"
_W8D_EVIDENCE_PATH: Path = _REPO_ROOT / "results" / "validation" / "wave8_d_single_factor" / "result.json"

_GATES_V2_SHA256_FROZEN: str = "bd0fc5de89307dab36fe82c12e0d921a7fa145376e2ef01aad8d000dd92979d2"
_GATES_SHA256_FROZEN: str = "521b7571c330a5a1e87642eb9e5c0869ae8dc23cba3a1a175baf21a42f559af4"
_W8D_EVIDENCE_SHA256_FROZEN: str = "1d1a8be0cb3c4cb1cb3e4de73f0e2b7654c5c080a33f51f5912c2dfd762d0bf2"

_HOLDOUT_DIR: Path = _REPO_ROOT / "results" / "holdout"
_LOCKFILE_USED: Path = _HOLDOUT_DIR / ".holdout_used"
_LOCKFILE_IN_PROGRESS: Path = _HOLDOUT_DIR / ".holdout_in_progress"
_OUTPUT_PATH: Path = _HOLDOUT_DIR / "holdout_result.json"
_OUTPUT_SHA_PATH: Path = _HOLDOUT_DIR / "holdout_result.json.sha256"

# GL-0021 V_D1..V_D4 frozen iter-27..iter-35 (bit-identical iter-28 replay)
_V_D1_THRESHOLD: float = 0.30
_V_D2_THRESHOLD: float = 0.05
_V_D3_THRESHOLD: float = 0.20
_V_D4_THRESHOLD: float = 0.20

_N_QUANTILES: int = 5
_ANNUAL_FACTOR_WEEKLY: int = 52  # V_D1/V_D4 only; iter-28 line 82 + 265
_PERM_REPS: int = 500
_PERM_BLOCK: int = 21  # V_D2 -- replicates iter-28 line 84 (NOT collapsed with V_D3)
_BOOT_REPS: int = 10000
_BOOT_BLOCK: int = 63  # V_D3 -- replicates iter-28 line 86 (NOT collapsed with V_D2)
_BOOT_ALPHA: float = 0.05
_SMA_WINDOW: int = 200

_DECISIVE_FLOOR: float = 0.30  # PASS-DECISIVE iff oos_sharpe >= this floor

# Runtime value-equality assertions (rev2 P1-3 reframing) -- catch future
# retunes of the holdout window via direct value check at module import time.
# Pairs with check_holdout_guard.py allowlist sha256 pin (defense-in-depth).
assert _HOLDOUT_START == date(2024, 1, 1), (  # noqa: SIM300
    f"_HOLDOUT_START retuned: {_HOLDOUT_START} != date(2024, 1, 1)"
)
assert _HOLDOUT_END == date(2025, 12, 31), (  # noqa: SIM300
    f"_HOLDOUT_END retuned: {_HOLDOUT_END} != date(2025, 12, 31)"
)

_SRC: str = "scripts.run_holdout_once_long_short"


# ---------------------------------------------------------------------------
# Lockfile + evidence primitives (mirror run_holdout_once.py Wave 7 pattern)
# ---------------------------------------------------------------------------


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
    gates_path: Path,
    gates_expected_sha256: str,
    w8d_evidence_path: Path,
    w8d_evidence_expected_sha256: str,
    lockfile_used: Path,
    lockfile_in_progress: Path,
) -> None:
    """Refuse on any Iron Rule 10 P1-4 (a)/(b)/(c) + W8-D evidence violation.

    Iron Rule 10 P1-4 mapped to this function:
      (a) hardcoded window enforcement -- start/end MUST equal module constants
      (b) lockfiles MUST NOT exist (used = re-run forbidden; in_progress =
          prior crash, partial = consumed under Iron Rule 1)
      (c) frozen-hash anchors -- gates_v2.yaml + gates.yaml + W8-D evidence
          all MUST match GL-0025 frozen values.
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
            "no re-runs permitted under Iron Rule 1 + GL-0025 strict "
            "consume-on-touch protocol"
        )
    if lockfile_in_progress.exists():
        raise PreflightError(
            f"prior holdout run did not complete cleanly "
            f"(lockfile exists: {lockfile_in_progress}); "
            "investigate crash; partial = consumed (Iron Rule 1). "
            "iter-36 GL-0026 routes A8 ABANDON via CONSUMED_NO_VERDICT "
            "or CONSUMED_PARTIAL_EVIDENCE terminal state."
        )
    for path, expected, label in (
        (gates_v2_path, gates_v2_expected_sha256, "gates_v2.yaml"),
        (gates_path, gates_expected_sha256, "gates.yaml"),
        (w8d_evidence_path, w8d_evidence_expected_sha256, "W8-D evidence"),
    ):
        if not path.exists():
            raise PreflightError(f"frozen artefact missing ({label}): {path}")
        actual = _sha256_of_file(path)
        if actual != expected:
            raise PreflightError(
                f"frozen-hash mismatch on {label} ({path}): got {actual}, expected {expected}"
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
        marker = f"{_dt.datetime.now(_dt.UTC).isoformat()}\npid={os.getpid()}\nrunner={_SRC}\n"
        os.write(fd, marker.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def promote_lockfile_to_used(*, in_progress: Path, used: Path) -> None:
    """Atomic POSIX rename .holdout_in_progress -> .holdout_used.

    os.replace() is the POSIX atomic-rename primitive: either the target
    exists with the new name OR the rename fails entirely. There is no
    intermediate state where both names exist. A failure here leaves
    .holdout_in_progress in place (CONSUMED_LOCKFILE_MISMATCH or
    CONSUMED_PARTIAL_EVIDENCE depending on evidence-write state).
    """
    if not in_progress.exists():
        raise PreflightError(f"cannot promote lockfile: {in_progress} does not exist")
    os.replace(str(in_progress), str(used))


def three_tier_outcome(oos_sharpe: float | None) -> str:
    """Map V_D1 OOS Sharpe to FAIL / PASS-WEAK / PASS-DECISIVE / ABORT label.

    The three-tier outcome is a REPORTING construct, not a gating construct.
    The decisive binary verdict (PASS/FAIL on Sharpe > 0) is the AP-6 holdout
    invariant. PASS-WEAK is informational only; A9 cost-drag computation +
    routing DEFERRED to Wave 10 paper-prep where cost-drag belongs.
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


def _verdict(observed: float | None, threshold: float, direction: str) -> str:
    """Return PASS/FAIL/INDETERMINATE for an observed scalar vs. threshold."""
    if observed is None or (isinstance(observed, float) and np.isnan(observed)):
        return "INDETERMINATE"
    if direction == ">=":
        return "PASS" if observed >= threshold else "FAIL"
    if direction == "<":
        return "PASS" if observed < threshold else "FAIL"
    raise ValueError(f"unknown direction: {direction!r}")


# ---------------------------------------------------------------------------
# Compute path: bit-identical iter-28 long-short quintile replay
# (replicates scripts/run_workstream_d_single_factor.py:101-307)
# ---------------------------------------------------------------------------


def _build_ivol_panel(
    ohlcv: pd.DataFrame,
    rebalance_dates: list[pd.Timestamp],
) -> pd.DataFrame:
    """Per-date rank-percentile panel for ivol_20d_flipped (sign=+1, no negation).

    Replicates run_workstream_d_single_factor.py:101-136 (iter-28). RNG tie-break
    seed = ts.toordinal() preserves bit-identity with the W8-D evidence template
    that drove the V2 ensemble +0.5549 Sharpe.
    """
    ohlcv = ohlcv.copy()
    ohlcv[COL_DATE] = pd.to_datetime(ohlcv[COL_DATE])

    rows: list[pd.DataFrame] = []
    for ts in rebalance_dates:
        window = ohlcv[ohlcv[COL_DATE] <= ts]
        if window.empty:
            continue
        series, _ = compute_ivol_20d(window)
        series = series.dropna()
        if series.empty:
            continue
        # sign=+1 -> no negation; high raw IVOL = high score (V2 ensemble convention)
        rng = np.random.default_rng(seed=ts.toordinal())
        ranked, _ = rank_percentile(series, rng=rng)
        rows.append(
            pd.DataFrame(
                {
                    "date": ts.date(),
                    "symbol": ranked.index,
                    "score": ranked.values,
                }
            )
        )
    if not rows:
        return pd.DataFrame(columns=["date", "symbol", "score"])
    return pd.concat(rows, ignore_index=True)


def _load_spy_sma200(
    db_path: Path,
    start: date,
    end: date,
) -> pd.Series:
    """SPY close series with SMA200 lookback. Replicates iter-28 lines 139-167."""
    lookback = start - pd.Timedelta(days=_SMA_WINDOW * 2).to_pytimedelta()
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        df = conn.execute(
            "SELECT date, close FROM ohlcv WHERE symbol = 'SPY' AND date >= ? AND date <= ? ORDER BY date",
            [lookback.isoformat(), end.isoformat()],
        ).fetchdf()
    finally:
        conn.close()
    if df.empty:
        raise PreflightError(f"no SPY rows in {db_path} over [{lookback}, {end}]; V_D4 cannot be computed.")
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")["close"].astype(float).sort_index()


def _classify_regime_per_date(
    ls_dates: pd.DatetimeIndex,
    spy_close: pd.Series,
) -> pd.Series:
    """Per-date BULL/BEAR via SPY vs SMA200. Replicates iter-28 lines 170-196."""
    sma200 = spy_close.rolling(_SMA_WINDOW, min_periods=_SMA_WINDOW).mean()
    regimes: dict = {}
    for dt in ls_dates:
        ts = pd.Timestamp(dt)
        idx = spy_close.index.searchsorted(ts, side="right") - 1
        if idx < 0:
            regimes[dt] = "UNKNOWN"
            continue
        as_of = spy_close.index[idx]
        sma_val = sma200.loc[as_of]
        close_val = spy_close.loc[as_of]
        if pd.isna(sma_val) or pd.isna(close_val):
            regimes[dt] = "UNKNOWN"
            continue
        regimes[dt] = "BULL" if close_val > sma_val else "BEAR"
    return pd.Series(regimes, name="regime")


def _compute_holdout_long_short(
    db_path: Path,
    *,
    start: date,
    end: date,
) -> dict:
    """Bit-identical iter-28 long-short quintile compute over the holdout window.

    Returns a dict consumed by build_payload(). Test cases can replace this via
    main()'s ``compute_fn`` keyword argument to avoid hitting research.duckdb.
    """
    print(f"[1/6] Loading OHLCV {start} -> {end}", flush=True)
    ohlcv = _load_ohlcv(db_path, start, end)
    print(f"       rows={len(ohlcv):,}", flush=True)

    rebalance = _weekly_fridays(start, end)
    print(f"[2/6] Rebalance dates: {len(rebalance)} weekly Fridays", flush=True)

    fwd_returns = _build_forward_returns(ohlcv, rebalance)
    print(f"[3/6] Forward-return rows: {len(fwd_returns):,}", flush=True)

    print("[4/6] Building ivol_20d_flipped panel (sign=+1, RNG tie-break)", flush=True)
    panel = _build_ivol_panel(ohlcv, rebalance)
    print(f"       panel rows: {len(panel):,}", flush=True)
    if panel.empty:
        raise PreflightError("ivol_20d_flipped panel is empty over holdout window")

    print("[5/6] Long-short quintile portfolio + V_D1..V_D3", flush=True)
    ls_returns, ls_diag = compute_long_short_returns(panel, fwd_returns, n_quantiles=_N_QUANTILES)
    n_periods = int(len(ls_returns))
    if n_periods < 2 or float(ls_returns.std(ddof=1)) == 0.0:
        raise PreflightError(f"insufficient long-short data (n={n_periods}, std=0?) over holdout")

    # V_D1: bit-identical iter-28 line 265
    oos_sharpe, _ = sharpe_ratio(ls_returns, annual_factor=_ANNUAL_FACTOR_WEEKLY)
    v_d1_observed = float(oos_sharpe) if oos_sharpe is not None else None

    # V_D2: bit-identical iter-28 line 270
    perm_p, _ = permutation_test(ls_returns, n_reps=_PERM_REPS, block_size=_PERM_BLOCK)
    v_d2_observed = float(perm_p) if perm_p is not None else None

    # V_D3: bit-identical iter-28 lines 275-277
    (boot_lower, boot_upper), _ = block_bootstrap_ci(
        ls_returns, n_reps=_BOOT_REPS, block_size=_BOOT_BLOCK, alpha=_BOOT_ALPHA
    )
    v_d3_observed = float(boot_lower) if boot_lower is not None else None
    v_d3_ci_upper = float(boot_upper) if boot_upper is not None else None

    # V_D4: bit-identical iter-28 lines 282-307
    print("[6/6] V_D4 SPY SMA200 regime stratification", flush=True)
    spy_close = _load_spy_sma200(db_path, start, end)
    ls_index = pd.DatetimeIndex([pd.Timestamp(d) for d in ls_returns.index])
    regimes = _classify_regime_per_date(ls_index, spy_close)
    regimes.index = list(ls_returns.index)

    bull_mask = regimes == "BULL"
    bear_mask = regimes == "BEAR"
    bull_returns = ls_returns[bull_mask.values]
    bear_returns = ls_returns[bear_mask.values]

    bull_sharpe = (
        float(sharpe_ratio(bull_returns, annual_factor=_ANNUAL_FACTOR_WEEKLY)[0])
        if len(bull_returns) >= 2 and bull_returns.std(ddof=1) > 0
        else None
    )
    bear_sharpe = (
        float(sharpe_ratio(bear_returns, annual_factor=_ANNUAL_FACTOR_WEEKLY)[0])
        if len(bear_returns) >= 2 and bear_returns.std(ddof=1) > 0
        else None
    )
    if bull_sharpe is None or bear_sharpe is None:
        v_d4_observed: float | None = None
    else:
        v_d4_observed = float(min(bull_sharpe, bear_sharpe))

    return {
        "n_rebalance_dates": len(rebalance),
        "n_forward_return_rows": int(len(fwd_returns)),
        "n_panel_rows": int(len(panel)),
        "n_ls_periods": n_periods,
        "v_d1_observed": v_d1_observed,
        "v_d2_observed": v_d2_observed,
        "v_d3_observed": v_d3_observed,
        "v_d3_ci_upper": v_d3_ci_upper,
        "v_d4_observed": v_d4_observed,
        "v_d4_bull_sharpe": bull_sharpe,
        "v_d4_bear_sharpe": bear_sharpe,
        "v_d4_bull_n_periods": int(bull_mask.sum()),
        "v_d4_bear_n_periods": int(bear_mask.sum()),
        "long_short_diagnostic_warnings": [
            f"[{m.source}] {m.message}" for m in ls_diag.messages if m.level.value == "WARNING"
        ],
    }


# ---------------------------------------------------------------------------
# Payload assembly + main entry point
# ---------------------------------------------------------------------------


def build_payload(
    *,
    compute_result: dict,
    start: date,
    end: date,
    runner_path: Path,
    runner_sha256: str,
) -> dict:
    """Assemble the canonical iter-35 holdout evidence payload.

    The ``frozen_construction`` echo dict provides defense-in-depth proof that
    the runner used hardcoded params (alongside the runner sha256 pin in
    GL-0025 + check_holdout_guard.py allowlist).
    """
    v_d1 = compute_result["v_d1_observed"]
    v_d2 = compute_result["v_d2_observed"]
    v_d3 = compute_result["v_d3_observed"]
    v_d4 = compute_result["v_d4_observed"]

    v_d1_verdict = _verdict(v_d1, _V_D1_THRESHOLD, ">=")
    v_d2_verdict = _verdict(v_d2, _V_D2_THRESHOLD, "<")
    v_d3_verdict = _verdict(v_d3, _V_D3_THRESHOLD, ">=")
    v_d4_verdict = _verdict(v_d4, _V_D4_THRESHOLD, ">=")

    all_pass = all(v == "PASS" for v in (v_d1_verdict, v_d2_verdict, v_d3_verdict, v_d4_verdict))
    any_indet = any(v == "INDETERMINATE" for v in (v_d1_verdict, v_d2_verdict, v_d3_verdict, v_d4_verdict))
    v_d_overall = "PASS" if all_pass else ("INDETERMINATE" if any_indet else "FAIL")

    # AP-6 binary verdict on V_D1 Sharpe > 0
    if v_d1 is None:
        decisive_verdict = "ABORT"
    elif v_d1 > 0.0:
        decisive_verdict = "PASS"
    else:
        decisive_verdict = "FAIL"
    outcome_three_tier = three_tier_outcome(v_d1)

    return {
        "iteration": 35,
        "iteration_tag": "iter-35",
        "wave": "Wave 9-D -- One-shot 2024-2025 holdout consumption (GL-0025)",
        "authorizing_governance_rows": [
            "GL-0017",  # Wave 6 freeze pattern
            "GL-0019",  # Wave 6 verdict (ensemble retired)
            "GL-0021",  # V_D1..V_D4 frozen iter-27..iter-35
            "GL-0024",  # Wave 8 D-ONLY routing + scope guardrail
            "GL-0025",  # Wave 9-D pre-authorization (Iron Rule 12)
        ],
        "factor_under_test": "ivol_20d_flipped",
        "strategy_class": "long_short_quintile",
        "frozen_construction": {
            "n_quantiles": _N_QUANTILES,
            "weighting": "equal",
            "sign_convention": +1,
            "rank_percentile_tiebreak": "rng_default_rng_seed_date_toordinal",
            "annual_factor_weekly_v_d1_v_d4": _ANNUAL_FACTOR_WEEKLY,
            "perm_reps_v_d2": _PERM_REPS,
            "perm_block_v_d2": _PERM_BLOCK,
            "boot_reps_v_d3": _BOOT_REPS,
            "boot_block_v_d3": _BOOT_BLOCK,
            "boot_alpha_v_d3": _BOOT_ALPHA,
            "sma_window_v_d4": _SMA_WINDOW,
            "ensemble": False,
            "k_of_n_coverage": False,
            "regime_overlay_applied_to_ls_series": False,
            "spec_source": "GL-0025 + bit-identical iter-28 replay",
        },
        "window": {"start": str(start), "end": str(end)},
        "frozen_artefact_sha256s": {
            "config_gates_v2_yaml": _GATES_V2_SHA256_FROZEN,
            "config_gates_yaml": _GATES_SHA256_FROZEN,
            "wave8_d_evidence_result_json": _W8D_EVIDENCE_SHA256_FROZEN,
            "scripts_run_holdout_once_long_short_py": runner_sha256,
        },
        "runner_path": str(runner_path),
        "n_rebalance_dates": compute_result["n_rebalance_dates"],
        "n_forward_return_rows": compute_result["n_forward_return_rows"],
        "n_panel_rows": compute_result["n_panel_rows"],
        "n_ls_periods": compute_result["n_ls_periods"],
        "v_d1": {
            "metric": "oos_sharpe",
            "observed": v_d1,
            "threshold": _V_D1_THRESHOLD,
            "direction": ">=",
            "verdict": v_d1_verdict,
            "annual_factor": _ANNUAL_FACTOR_WEEKLY,
            "compute_path": "nyse_core.metrics.sharpe_ratio (UNCHANGED)",
        },
        "v_d2": {
            "metric": "permutation_p",
            "observed": v_d2,
            "threshold": _V_D2_THRESHOLD,
            "direction": "<",
            "n_reps": _PERM_REPS,
            "block_size": _PERM_BLOCK,
            "verdict": v_d2_verdict,
            "compute_path": "nyse_core.statistics.permutation_test (UNCHANGED, sqrt(252))",
        },
        "v_d3": {
            "metric": "bootstrap_ci_lower",
            "observed": v_d3,
            "threshold": _V_D3_THRESHOLD,
            "direction": ">=",
            "n_reps": _BOOT_REPS,
            "block_size": _BOOT_BLOCK,
            "alpha": _BOOT_ALPHA,
            "ci_upper": compute_result["v_d3_ci_upper"],
            "verdict": v_d3_verdict,
            "compute_path": "nyse_core.statistics.block_bootstrap_ci (UNCHANGED, sqrt(252))",
        },
        "v_d4": {
            "metric": "min_regime_sharpe",
            "observed": v_d4,
            "threshold": _V_D4_THRESHOLD,
            "direction": ">=",
            "regime_split": "spy_sma200_binary",
            "sma_window": _SMA_WINDOW,
            "annual_factor": _ANNUAL_FACTOR_WEEKLY,
            "bull_n_periods": compute_result["v_d4_bull_n_periods"],
            "bear_n_periods": compute_result["v_d4_bear_n_periods"],
            "bull_sharpe": compute_result["v_d4_bull_sharpe"],
            "bear_sharpe": compute_result["v_d4_bear_sharpe"],
            "verdict": v_d4_verdict,
            "compute_path": "nyse_core.metrics.sharpe_ratio (UNCHANGED) on regime split",
        },
        "v_d_overall_verdict": v_d_overall,
        "oos_sharpe": v_d1,
        "verdict": decisive_verdict,
        "verdict_decisive_floor": "Sharpe > 0 (GL-0025 binary, AP-6)",
        "outcome_three_tier": outcome_three_tier,
        "long_short_diagnostic_warnings": compute_result.get("long_short_diagnostic_warnings", []),
        "iron_rule_9_attestation": (
            "src/nyse_core/statistics.py:37 _sharpe preserved bit-identical; "
            "src/nyse_core/metrics.py sharpe_ratio preserved bit-identical "
            "(imported UNCHANGED, no library forking, no local helper). "
            "V_D1/V_D4 call sharpe_ratio(returns, annual_factor=52) matching "
            "iter-28 line 67 import + line 265 call site exactly. V_D2/V_D3 "
            "inherit sqrt(252) via UNCHANGED permutation_test/block_bootstrap_ci."
        ),
        "iron_rule_12_attestation": (
            "ALL authority to consume the 2024-2025 holdout originates in "
            "GL-0025. GL-0024 routing GRANTS ZERO authority to consume; "
            "W8-D PASS verdict establishes ELIGIBILITY only. iter-33 P0-E "
            "pre-landed runner is DORMANT until GL-0025 commits; runner "
            "sha256 pin without committed governance row = NO authority."
        ),
        "no_iteration_clause": (
            "Iron Rule 1 + GL-0025 + strict consume-on-touch protocol: holdout "
            "window 2024-01-01..2025-12-31 is one-shot; no parameter retuning, "
            "no factor re-screening, no gate threshold adjustment after this "
            "commit, regardless of outcome. PASS-WEAK is informational only "
            "(A9 cost-drag DEFERRED to Wave 10)."
        ),
        "ap6_compliance": (
            "Pre-registered V_D1..V_D4 bars (GL-0021 frozen iter-27..iter-35) "
            "applied bit-identically to the 2024-2025 holdout window. "
            "Holdout-runner pre-landed iter-33 (Iron Rule 10 + Iron Rule 12). "
            "Compute path bit-identical to W8-D iter-28."
        ),
        "timestamp_source": f"{_SRC}.main",
    }


def main(
    argv: list[str] | None = None,
    *,
    compute_fn: Callable[..., dict] | None = None,
) -> int:
    """Wave 9-D / iter-35 holdout entry point.

    Module-constant references in this function body (rather than default
    arguments) ensure that test monkeypatching of e.g. ``runner._LOCKFILE_USED``
    takes effect at call time.
    """
    parser = argparse.ArgumentParser(
        description="Wave 9-D / iter-35 long-short quintile holdout runner",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path("research.duckdb"),
        help="path to research.duckdb (frozen iter-28 schema)",
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
            gates_path=_GATES_PATH,
            gates_expected_sha256=_GATES_SHA256_FROZEN,
            w8d_evidence_path=_W8D_EVIDENCE_PATH,
            w8d_evidence_expected_sha256=_W8D_EVIDENCE_SHA256_FROZEN,
            lockfile_used=_LOCKFILE_USED,
            lockfile_in_progress=_LOCKFILE_IN_PROGRESS,
        )
    except PreflightError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(
            "DRY-RUN: preflight passed; no lockfile created, no compute run.",
            flush=True,
        )
        return 0

    acquire_in_progress_lockfile(_LOCKFILE_IN_PROGRESS)

    if compute_fn is None:
        compute_fn = _compute_holdout_long_short
    compute_result = compute_fn(
        args.db_path,
        start=_HOLDOUT_START,
        end=_HOLDOUT_END,
    )

    runner_sha256 = _sha256_of_file(Path(__file__).resolve())
    payload = build_payload(
        compute_result=compute_result,
        start=_HOLDOUT_START,
        end=_HOLDOUT_END,
        runner_path=Path(__file__).resolve(),
        runner_sha256=runner_sha256,
    )
    write_evidence(
        payload,
        output_path=_OUTPUT_PATH,
        sha_output_path=_OUTPUT_SHA_PATH,
    )

    promote_lockfile_to_used(in_progress=_LOCKFILE_IN_PROGRESS, used=_LOCKFILE_USED)

    oos = payload["oos_sharpe"]
    v_d2 = payload["v_d2"]["observed"]
    v_d3 = payload["v_d3"]["observed"]
    v_d4 = payload["v_d4"]["observed"]
    print("")
    print("WAVE 9-D / iter-35 HOLDOUT (2024-2025) -- ONE-SHOT")
    print("=" * 66)
    if oos is not None:
        print(f"  V_D1 OOS Sharpe   : {oos:+.4f}  (>= {_V_D1_THRESHOLD})  -> {payload['v_d1']['verdict']}")
    else:
        print("  V_D1 OOS Sharpe   : <None>")
    print(f"  V_D2 perm p       : {v_d2!r:>10}  (<  {_V_D2_THRESHOLD})  -> {payload['v_d2']['verdict']}")
    print(f"  V_D3 ci_lower     : {v_d3!r:>10}  (>= {_V_D3_THRESHOLD})  -> {payload['v_d3']['verdict']}")
    print(f"  V_D4 min reg-Sh   : {v_d4!r:>10}  (>= {_V_D4_THRESHOLD})  -> {payload['v_d4']['verdict']}")
    print(f"  V_D OVERALL       : {payload['v_d_overall_verdict']}")
    print(f"  AP-6 binary (V_D1): {payload['verdict']} (decisive floor Sharpe > 0)")
    print(f"  Three-tier label  : {payload['outcome_three_tier']}")
    print(f"  Evidence          : {_OUTPUT_PATH}")
    print(f"  SHA256 sidecar    : {_OUTPUT_SHA_PATH}")
    print(f"  Lockfile state    : {_LOCKFILE_USED} (consumed)")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    np.seterr(invalid="ignore")
    raise SystemExit(main())
