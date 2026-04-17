#!/usr/bin/env python3
"""Append a hash-chained event to results/research_log.jsonl.

Each line in the log is a JSON object with:
  - prev_hash : sha256 of the previous line's canonical bytes (genesis line has "0"*64)
  - entry     : the event payload (arbitrary JSON-serializable dict)
  - hash      : sha256 of canonical(prev_hash + canonical(entry))

Canonical form = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")

Why hash-chain a research log?
  - Tamper-evident: silently editing any entry breaks the chain on all following entries.
  - Cheap: ~100 bytes per entry; pure Python stdlib; no server, no database.
  - Cryptographically irreversible: if you later want to publish a Merkle root of the chain,
    you have one-shot evidence that your research history wasn't rewritten after outcomes
    were observed.

Threat model — what this defends against:
  [DEFENDED] Silent retroactive edits to past predictions (AP-6 enforcement).
  [DEFENDED] "Losing" unfavorable experiment results.
  [DEFENDED] Reordering events to make outcomes look better than predictions.

  [NOT DEFENDED] An attacker with write access can re-chain the whole file from scratch.
                 Mitigation: publish the latest hash externally (git commit, email, tweet).
  [NOT DEFENDED] Malicious code that appends fake events before a real one.
                 Mitigation: the log doesn't replace domain verification; it just makes
                 retroactive edits detectable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

GENESIS_PREV_HASH = "0" * 64


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _compute_hash(prev_hash: str, entry: dict) -> str:
    h = hashlib.sha256()
    h.update(prev_hash.encode("utf-8"))
    h.update(_canonical(entry))
    return h.hexdigest()


def _last_hash(log_path: Path) -> str:
    if not log_path.exists() or log_path.stat().st_size == 0:
        return GENESIS_PREV_HASH
    last_line = None
    with log_path.open("rb") as f:
        for line in f:
            line = line.strip()
            if line:
                last_line = line
    if last_line is None:
        return GENESIS_PREV_HASH
    try:
        obj = json.loads(last_line)
    except json.JSONDecodeError:
        print(f"ERROR: last line of {log_path} is not valid JSON. "
              "Run scripts/verify_research_log.py to diagnose.", file=sys.stderr)
        sys.exit(2)

    # Legacy entries (pre-chain) may not have a hash field — treat as genesis.
    return obj.get("hash", GENESIS_PREV_HASH)


def append_event(log_path: Path, event: dict) -> dict:
    """Append an event to the log with hash chaining. Returns the full record written."""
    prev_hash = _last_hash(log_path)
    # Ensure timestamp is present
    event.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    this_hash = _compute_hash(prev_hash, event)
    record = {"prev_hash": prev_hash, "entry": event, "hash": this_hash}
    with log_path.open("a") as f:
        f.write(json.dumps(record) + "\n")
    return record


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Append a hash-chained event to results/research_log.jsonl"
    )
    ap.add_argument(
        "--log-path", type=Path, default=Path("results/research_log.jsonl"),
        help="Path to the research log (default: results/research_log.jsonl)",
    )
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--event-json", help="Event payload as a JSON string")
    g.add_argument("--event-file", type=Path, help="Path to a file containing the event JSON")
    ap.add_argument("--quiet", action="store_true", help="Suppress stdout output")
    args = ap.parse_args()

    if args.event_json:
        event = json.loads(args.event_json)
    else:
        event = json.loads(args.event_file.read_text())

    if not isinstance(event, dict):
        print("ERROR: event must be a JSON object", file=sys.stderr)
        return 1

    args.log_path.parent.mkdir(parents=True, exist_ok=True)
    record = append_event(args.log_path, event)

    if not args.quiet:
        print(f"Appended hash {record['hash'][:16]}...{record['hash'][-8:]}")
        print(f"  Prev hash:  {record['prev_hash'][:16]}...{record['prev_hash'][-8:]}")
        print(f"  Entry keys: {sorted(record['entry'].keys())}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
