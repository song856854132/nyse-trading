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

Threat model -- what this defends against:
  [DEFENDED] Silent retroactive edits to past predictions (AP-6 enforcement).
  [DEFENDED] "Losing" unfavorable experiment results.
  [DEFENDED] Reordering events to make outcomes look better than predictions.
  [DEFENDED] Concurrent-writer races in a ralph-loop iteration (--expected-prev-hash).
  [DEFENDED] Silent double-append on iteration retry (iteration_tag idempotency).

  [NOT DEFENDED] An attacker with write access can re-chain the whole file from scratch.
                 Mitigation: publish the latest hash externally (git commit, email, tweet).
  [NOT DEFENDED] Malicious code that appends fake events before a real one.
                 Mitigation: the log doesn't replace domain verification; it just makes
                 retroactive edits detectable.

Pre-Wave-8 enhancements (2026-04-26):
  --expected-prev-hash <hash>   Optimistic-concurrency guard. If the current chain tip
                                does not equal the provided hash, the append is rejected
                                with PREV_HASH_CONFLICT. Caller should re-read the log
                                and decide whether to retry. Used by ralph-loop iters
                                to refuse stale appends after a concurrent writer races
                                ahead.
  iteration_tag idempotency     If event["iteration_tag"] is already in the log:
                                  - identical content (modulo timestamp) -> silent no-op
                                    (exit 0, status="already_appended"). Lets ralph-loop
                                    safely re-run the same iter without duplicate entries.
                                  - different content -> ITERATION_TAG_CONFLICT (exit 1).
                                    Forces the caller to manually resolve a divergent
                                    re-run rather than silently overwriting evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
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
    """Return prev_hash for the next append.

    Walks the entire file and returns the hash of the LAST line that carries a
    `hash` field (i.e. the last chained entry). If no chained entries exist,
    returns GENESIS (bootstraps a new chain over pre-chain legacy prologue).

    Returning the *last chained* hash (not just the last line) defends against
    a subtle bug: if any tool appends a raw/legacy-style entry after chained
    entries, naively trusting the last line would cause a new fork-from-genesis
    and silently break the chain. Instead we chain past any trailing legacy
    entries, preserving integrity.
    """
    if not log_path.exists() or log_path.stat().st_size == 0:
        return GENESIS_PREV_HASH

    last_chained_hash: str | None = None
    with log_path.open("rb") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                print(
                    f"ERROR: non-JSON line in {log_path}. Run scripts/verify_research_log.py to diagnose.",
                    file=sys.stderr,
                )
                sys.exit(2)
            h = obj.get("hash")
            if isinstance(h, str) and len(h) == 64:
                last_chained_hash = h

    return last_chained_hash if last_chained_hash is not None else GENESIS_PREV_HASH


def _find_iteration_tag_match(log_path: Path, iteration_tag: str) -> dict | None:
    """Return the FIRST envelope whose entry.iteration_tag matches, else None.

    Idempotency design choice: returning the first match (oldest occurrence) means a
    later content-divergent re-append is reported as a conflict against the original
    record. This is what we want -- the original is the canonical evidence, any
    divergent rewrite is a violation.
    """
    if not log_path.exists() or log_path.stat().st_size == 0:
        return None
    with log_path.open("rb") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            entry = obj.get("entry")
            if isinstance(entry, dict) and entry.get("iteration_tag") == iteration_tag:
                return obj
    return None


def _entry_content_equal(prior: dict, candidate: dict) -> bool:
    """Compare two events ignoring the auto-set `timestamp` field.

    Idempotency rule: a re-append with the SAME iteration_tag and SAME content (modulo
    its timestamp) is a no-op success. Any non-timestamp difference is a conflict.
    Timestamp is excluded because the runtime stamps it on the FIRST append; the
    second invocation will produce a fresh timestamp by design.
    """
    a_clean = {k: v for k, v in prior.items() if k != "timestamp"}
    b_clean = {k: v for k, v in candidate.items() if k != "timestamp"}
    return a_clean == b_clean


def append_event(
    log_path: Path,
    event: dict,
    expected_prev_hash: str | None = None,
) -> tuple[dict, str]:
    """Append an event to the log with hash chaining.

    Returns (record, status) where status is one of:
      - "appended"          : the event was newly written to the log
      - "already_appended"  : event.iteration_tag already matched an existing record
                              with identical content (modulo timestamp); no write occurred

    Raises:
      ValueError("PREV_HASH_CONFLICT", ...)
        expected_prev_hash was provided and does NOT match the current chain tip.
        The caller likely has a stale view (concurrent writer raced ahead). Refuse
        to append rather than silently fork.
      ValueError("ITERATION_TAG_CONFLICT", ...)
        An entry with the same iteration_tag exists but with different content.
        Refuse to append; require manual resolution -- a deliberate change to a
        previously-recorded iteration is an AP-6 red flag.
    """
    iteration_tag = event.get("iteration_tag")
    if isinstance(iteration_tag, str) and iteration_tag:
        prior = _find_iteration_tag_match(log_path, iteration_tag)
        if prior is not None:
            prior_entry = prior.get("entry", {})
            if _entry_content_equal(prior_entry, event):
                return prior, "already_appended"
            raise ValueError(
                f"ITERATION_TAG_CONFLICT: iteration_tag={iteration_tag!r} already in log "
                f"with different content. Resolve manually -- do not silently re-append."
            )

    prev_hash = _last_hash(log_path)
    if expected_prev_hash is not None and prev_hash != expected_prev_hash:
        raise ValueError(
            f"PREV_HASH_CONFLICT: expected prev_hash={expected_prev_hash[:16]}... "
            f"but log tip is {prev_hash[:16]}.... "
            f"Concurrent writer or stale view; refusing to append."
        )

    event.setdefault("timestamp", datetime.now(UTC).isoformat())
    this_hash = _compute_hash(prev_hash, event)
    record = {"prev_hash": prev_hash, "entry": event, "hash": this_hash}
    with log_path.open("a") as f:
        f.write(json.dumps(record) + "\n")
    return record, "appended"


def main() -> int:
    ap = argparse.ArgumentParser(description="Append a hash-chained event to results/research_log.jsonl")
    ap.add_argument(
        "--log-path",
        type=Path,
        default=Path("results/research_log.jsonl"),
        help="Path to the research log (default: results/research_log.jsonl)",
    )
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--event-json", help="Event payload as a JSON string")
    g.add_argument("--event-file", type=Path, help="Path to a file containing the event JSON")
    ap.add_argument(
        "--expected-prev-hash",
        help=(
            "If provided, refuse to append unless the current chain tip equals this hash. "
            "Used to detect concurrent writers in ralph-loop iterations."
        ),
    )
    ap.add_argument("--quiet", action="store_true", help="Suppress stdout output")
    args = ap.parse_args()

    event = json.loads(args.event_json) if args.event_json else json.loads(args.event_file.read_text())

    if not isinstance(event, dict):
        print("ERROR: event must be a JSON object", file=sys.stderr)
        return 1

    args.log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        record, status = append_event(
            args.log_path,
            event,
            expected_prev_hash=args.expected_prev_hash,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if not args.quiet:
        if status == "already_appended":
            tag = event.get("iteration_tag")
            print(f"Idempotent re-append: iteration_tag={tag!r} already in log; no-op.")
            print(f"  Existing hash: {record['hash'][:16]}...{record['hash'][-8:]}")
        else:
            print(f"Appended hash {record['hash'][:16]}...{record['hash'][-8:]}")
            print(f"  Prev hash:  {record['prev_hash'][:16]}...{record['prev_hash'][-8:]}")
            print(f"  Entry keys: {sorted(record['entry'].keys())}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
