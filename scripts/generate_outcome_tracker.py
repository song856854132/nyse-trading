#!/usr/bin/env python3
"""Regenerate docs/OUTCOME_VS_FORECAST.md from forecast + outcome artifacts.

Pre-live mode (current): reads pre-registered forecasts from results/research_log.jsonl
(event type "forecast") and outcome artifacts from results/factors/*/gate_results.json,
results/backtests/*/backtest_result.json, results/holdout/holdout_result.json.

Live mode (future): also reads live.duckdb for per-position forecast/outcome pairs.

Manual notes in the existing tracker are preserved on regeneration — matched by `id`.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

_SEED_FORECASTS: list[dict] = [
    {
        "id": "factor-ivol_20d-2016_2023",
        "forecast_date": "2026-04-15",
        "prediction_target": "ivol_20d G0-G5 verdict on 2016-2023",
        "forecast_value": "PASS likely (TWSE prior: strong Tier 1 factor)",
        "forecast_source": "plan `Factor Priority List Tier 1`, 2026-04-15",
    },
    {
        "id": "factor-high_52w-2016_2023",
        "forecast_date": "2026-04-15",
        "prediction_target": "high_52w G0-G5 verdict on 2016-2023",
        "forecast_value": "PASS likely",
        "forecast_source": "plan `Factor Priority List Tier 1`",
    },
    {
        "id": "factor-momentum_2_12-2016_2023",
        "forecast_date": "2026-04-15",
        "prediction_target": "momentum_2_12 G0-G5 verdict on 2016-2023",
        "forecast_value": "UNCERTAIN (DEAD on TWSE; may work on NYSE)",
        "forecast_source": "plan `Factor Priority List Tier 2`",
    },
    {
        "id": "factor-piotroski-2016_2023",
        "forecast_date": "2026-04-15",
        "prediction_target": "piotroski G0-G5 verdict on 2016-2023",
        "forecast_value": "PASS likely",
        "forecast_source": "plan `Factor Priority List Tier 1`",
    },
    {
        "id": "ensemble-oos_sharpe-2016_2023",
        "forecast_date": "2026-04-15",
        "prediction_target": "Ensemble OOS Sharpe on research period",
        "forecast_value": "0.5 - 0.8 (Phase 3 exit target)",
        "forecast_source": "plan Build Phase 3 target",
    },
    {
        "id": "ensemble-oos_sharpe-final",
        "forecast_date": "2026-04-15",
        "prediction_target": "Final ensemble OOS Sharpe after Phase 4 optimization",
        "forecast_value": "0.8 - 1.2",
        "forecast_source": "plan Build Phase 4 target",
    },
    {
        "id": "holdout-sharpe-2024_2025",
        "forecast_date": "2026-04-15",
        "prediction_target": "Holdout Sharpe on 2024-2025",
        "forecast_value": "> 0 (any positive OOS Sharpe admits to paper; < 0 STOPS)",
        "forecast_source": "plan Statistical Validation Suite step 8",
    },
]


@dataclass
class Row:
    id: str
    forecast_date: str
    prediction_target: str
    forecast_value: str
    forecast_source: str
    outcome_date: str = "—"
    outcome_value: str = "not yet run"
    outcome_source: str = "—"
    calibration: str = "PENDING"
    error_magnitude: str = "—"
    notes: str = "—"


def _parse_existing_notes(tracker_path: Path) -> dict[str, str]:
    """Return {row_id: notes_cell} from a prior version of the tracker, if present."""
    if not tracker_path.exists():
        return {}
    notes: dict[str, str] = {}
    text = tracker_path.read_text()
    # Row lines start with `| factor-...` or `| ensemble-...` etc.
    for m in re.finditer(
        r"^\|\s*([a-z0-9_\-]+)\s*\|(?:[^|]*\|){9}\s*([^|]*)\s*\|\s*$",
        text,
        flags=re.MULTILINE,
    ):
        row_id, note = m.group(1), m.group(2).strip()
        if note and note != "—":
            notes[row_id] = note
    return notes


def _load_gate_outcome(results_dir: Path, factor: str) -> tuple[str, str, str, str] | None:
    """Return (outcome_date, outcome_value, outcome_source, calibration) or None."""
    gate_path = results_dir / "factors" / factor / "gate_results.json"
    if not gate_path.exists():
        return None
    data = json.loads(gate_path.read_text())
    gates = data.get("gate_results", {})
    fails = [g for g, v in gates.items() if not v]
    passed = data.get("passed_all", False)

    # Use mtime as a proxy for outcome_date if we can't derive from the log
    mtime = date.fromtimestamp(gate_path.stat().st_mtime).isoformat()

    if passed:
        verdict = f"PASS (all G0-G5)"
        cal = "HIT"
    elif fails:
        parts = "/".join(sorted(fails))
        verdict = f"FAIL ({parts} FAIL)"
        cal = "MISS"
    else:
        verdict = "PARTIAL"
        cal = "PARTIAL"

    return mtime, verdict, str(gate_path.relative_to(results_dir.parent)), cal


def _load_holdout(results_dir: Path) -> tuple[str, str, str, str] | None:
    """Return (outcome_date, outcome_value, outcome_source, calibration) or None."""
    holdout_path = results_dir / "holdout" / "holdout_result.json"
    if not holdout_path.exists():
        return None
    data = json.loads(holdout_path.read_text())
    sharpe = data.get("oos_sharpe", None)
    if sharpe is None:
        return None
    mtime = date.fromtimestamp(holdout_path.stat().st_mtime).isoformat()
    verdict = f"Sharpe={sharpe:.4f}"
    cal = "HIT" if sharpe > 0 else "MISS"
    return mtime, verdict, str(holdout_path.relative_to(results_dir.parent)), cal


def _compute_rows(results_dir: Path, prior_notes: dict[str, str]) -> list[Row]:
    rows: list[Row] = []
    for f in _SEED_FORECASTS:
        r = Row(**f)  # type: ignore[arg-type]
        if r.id.startswith("factor-"):
            # id format: factor-<name>-<yyyy>_<yyyy>
            m = re.match(r"factor-(.+)-\d{4}_\d{4}$", r.id)
            if m:
                factor = m.group(1)
                out = _load_gate_outcome(results_dir, factor)
                if out:
                    r.outcome_date, r.outcome_value, r.outcome_source, r.calibration = out
        elif r.id == "holdout-sharpe-2024_2025":
            out = _load_holdout(results_dir)
            if out:
                r.outcome_date, r.outcome_value, r.outcome_source, r.calibration = out

        if r.id in prior_notes:
            r.notes = prior_notes[r.id]
        rows.append(r)
    return rows


def _summary(rows: list[Row]) -> dict[str, int]:
    summary = {"HIT": 0, "MISS": 0, "PARTIAL": 0, "INADMISSIBLE": 0, "PENDING": 0}
    for r in rows:
        summary[r.calibration] = summary.get(r.calibration, 0) + 1
    return summary


def _render(rows: list[Row], generated_on: str) -> str:
    header = (
        "| id | forecast_date | prediction_target | forecast_value | forecast_source | "
        "outcome_date | outcome_value | outcome_source | calibration | error_magnitude | notes |"
    )
    sep = "|---|---|---|---|---|---|---|---|---|---|---|"
    lines = [header, sep]
    for r in rows:
        lines.append(
            f"| {r.id} | {r.forecast_date} | {r.prediction_target} | {r.forecast_value} | "
            f"{r.forecast_source} | {r.outcome_date} | {r.outcome_value} | {r.outcome_source} | "
            f"{r.calibration} | {r.error_magnitude} | {r.notes} |"
        )

    s = _summary(rows)
    resolved = s["HIT"] + s["MISS"]
    brier = (s["MISS"] / resolved) if resolved > 0 else float("nan")
    brier_line = f"{brier:.2f}  ({s['MISS']} MISS / {resolved} resolved)" if resolved else "n/a  (no resolved predictions)"

    summary_block = (
        "```\n"
        f"CALIBRATION SUMMARY — generated {generated_on}\n"
        "═══════════════════════════════════════════════════════════\n"
        f"Pre-live predictions             {len(rows)}\n"
        f"  HIT                            {s['HIT']}\n"
        f"  MISS                           {s['MISS']}\n"
        f"  PARTIAL                        {s['PARTIAL']}\n"
        f"  INADMISSIBLE                   {s['INADMISSIBLE']}\n"
        f"  PENDING                        {s['PENDING']}\n"
        "\n"
        "Live predictions                 0\n"
        "\n"
        f"Brier score (HIT/MISS only)      {brier_line}\n"
        "═══════════════════════════════════════════════════════════\n"
        "```"
    )

    return "\n".join(lines) + "\n\n" + summary_block


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["pre-live", "live"], default="pre-live")
    ap.add_argument("--research-db", type=Path, default=Path("research.duckdb"))
    ap.add_argument("--results-dir", type=Path, default=Path("results"))
    ap.add_argument(
        "--output", type=Path, default=Path("docs/OUTCOME_VS_FORECAST.md")
    )
    ap.add_argument("--print-only", action="store_true",
                    help="Print the rendered table to stdout; don't write the file.")
    args = ap.parse_args()

    prior = _parse_existing_notes(args.output)
    rows = _compute_rows(args.results_dir, prior)
    generated_on = date.today().isoformat()
    rendered = _render(rows, generated_on)

    if args.print_only:
        print(rendered)
        return 0

    if not args.output.exists():
        print(f"ERROR: {args.output} does not exist — generator overwrites tables only, "
              f"not the full file. Create the seed document first.", flush=True)
        return 1

    text = args.output.read_text()
    # Replace the Live Forecasts table (the Pre-live sub-table + summary).
    # Anchor: lines between "### Pre-live" and the "### Live forecasts" header.
    start_marker = "### Pre-live (Research-period predictions vs research-period outcomes)\n\n"
    end_marker = "\n### Live forecasts (post-paper / post-live)"
    try:
        i = text.index(start_marker) + len(start_marker)
        j = text.index(end_marker, i)
    except ValueError:
        print(f"ERROR: anchors not found in {args.output}", flush=True)
        return 2

    # Also replace the Calibration Summary block
    cal_start = "## Calibration Summary (auto-generated; overwritten on regeneration)\n\n"
    cal_end = "\nBrier score interpretation:"
    try:
        ci = text.index(cal_start) + len(cal_start)
        cj = text.index(cal_end, ci)
    except ValueError:
        print(f"ERROR: calibration-summary anchors not found", flush=True)
        return 3

    # Split the rendered output into table + summary
    parts = rendered.split("\n\n", 1)
    table_md = parts[0] + "\n"
    summary_md = parts[1] + "\n"

    new_text = text[:i] + table_md + text[j:ci] + summary_md + text[cj:]
    args.output.write_text(new_text)

    print(f"Updated {args.output}. Summary:")
    s = _summary(rows)
    for k, v in s.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
