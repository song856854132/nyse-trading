#!/usr/bin/env python3
"""Verify integrity of results/research_log.jsonl.

Walks the file line-by-line. For each line, recomputes hash = sha256(prev_hash + canonical(entry))
and checks that:
  (a) each line's `prev_hash` equals the previous line's `hash` (chain continuity).
  (b) each line's `hash` equals the recomputed value (no silent edits to the entry).

Backward-compatibility: legacy entries (written before the chain was introduced) may not
have `prev_hash` / `hash` fields. Those are accepted only at the start of the file,
treated as a "pre-chain prologue", and their presence is reported. Once the first
chained entry appears, all subsequent entries must be chained.

Exit code:
  0 — chain is intact
  1 — chain is broken or file is malformed
  2 — file not found
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

GENESIS_PREV_HASH = "0" * 64


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _compute_hash(prev_hash: str, entry: dict) -> str:
    h = hashlib.sha256()
    h.update(prev_hash.encode("utf-8"))
    h.update(_canonical(entry))
    return h.hexdigest()


def verify(log_path: Path, verbose: bool = False) -> tuple[bool, list[str]]:
    """Return (ok, messages)."""
    if not log_path.exists():
        return False, [f"Log file not found: {log_path}"]

    messages: list[str] = []
    prev_hash = GENESIS_PREV_HASH
    seen_chained = False
    legacy_count = 0
    chained_count = 0
    broken_count = 0

    with log_path.open() as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                messages.append(f"[line {lineno}] Invalid JSON: {e}")
                broken_count += 1
                continue

            if "entry" not in obj or "hash" not in obj or "prev_hash" not in obj:
                # Legacy unchained entry
                if seen_chained:
                    messages.append(
                        f"[line {lineno}] Legacy (unchained) entry appeared after a chained "
                        f"entry — chain integrity broken."
                    )
                    broken_count += 1
                else:
                    legacy_count += 1
                    if verbose:
                        messages.append(f"[line {lineno}] Legacy unchained entry (accepted in prologue)")
                continue

            # Chained entry
            seen_chained = True
            chained_count += 1

            if obj["prev_hash"] != prev_hash:
                messages.append(
                    f"[line {lineno}] prev_hash mismatch: expected {prev_hash[:16]}... "
                    f"got {obj['prev_hash'][:16]}..."
                )
                broken_count += 1
                prev_hash = obj["hash"]  # continue so we catch further breaks
                continue

            recomputed = _compute_hash(obj["prev_hash"], obj["entry"])
            if recomputed != obj["hash"]:
                messages.append(
                    f"[line {lineno}] hash mismatch: stored {obj['hash'][:16]}... "
                    f"recomputed {recomputed[:16]}..."
                )
                broken_count += 1
                prev_hash = obj["hash"]
                continue

            prev_hash = obj["hash"]
            if verbose:
                ts = obj["entry"].get("timestamp", "?")
                evt = obj["entry"].get("event", "?")
                messages.append(f"[line {lineno}] OK  {obj['hash'][:12]}  {ts}  event={evt}")

    ok = broken_count == 0
    summary = (
        f"Summary: {legacy_count} legacy (pre-chain) entries, "
        f"{chained_count} chained entries, {broken_count} broken."
    )
    messages.append(summary)
    if ok and chained_count > 0:
        messages.append(f"Chain tip (latest hash): {prev_hash}")
    return ok, messages


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify research log hash chain integrity.")
    ap.add_argument(
        "--log-path", type=Path, default=Path("results/research_log.jsonl"),
    )
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    if not args.log_path.exists():
        print(f"File not found: {args.log_path}", file=sys.stderr)
        return 2

    ok, messages = verify(args.log_path, verbose=args.verbose)
    for m in messages:
        print(m)

    if ok:
        print("VERIFIED: chain is intact.")
        return 0
    else:
        print("FAILED: chain is broken. See messages above.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
