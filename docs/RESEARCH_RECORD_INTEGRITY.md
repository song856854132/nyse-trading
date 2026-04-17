# Research Record Integrity — Hash-Chained Append-Only Log

**Purpose:** Make silent retroactive edits to the research log impossible to miss.
Enforces AP-6 ("never expand experiment menu after results") at the filesystem level.

---

## The problem this solves

A research log that can be freely edited is not evidence. If a prediction dated 2026-04-15
said "ivol_20d will PASS G0-G5," but someone can later rewrite that line to say "ivol_20d
was expected to FAIL in low-vol winter," no independent validator can tell the difference
between calibration and motivated reasoning.

The classical remedy is a **hash chain**: each entry commits to the cryptographic hash of
the previous entry, so a change anywhere in the history invalidates every entry after it.

---

## Scheme

The log file is `results/research_log.jsonl`. Each line is a JSON object:

```json
{
  "prev_hash": "<64 hex chars>",
  "entry":     { "timestamp": "...", "event": "...", ... },
  "hash":      "<64 hex chars>"
}
```

The hash is computed as:

```
canonical(x) := json.dumps(x, sort_keys=True, separators=(",", ":")).encode("utf-8")
hash         := sha256(prev_hash_bytes + canonical(entry)).hexdigest()
```

The **genesis** entry uses `prev_hash = "0" * 64`.

### Why canonicalize?

Without canonical JSON, whitespace or key-order changes would silently change the hash
and break the chain for reasons that have nothing to do with tampering. `sort_keys=True`
+ tight separators produces a byte-stable representation.

### Why SHA-256?

Good enough for integrity against a motivated researcher or a sloppy tool. This is not
a blockchain — there is no adversarial economic threat model. SHA-256 pre-image and
collision resistance are more than sufficient for a single-operator research log.

---

## Tooling

### Append an event (hash-chained)

```bash
python3 scripts/append_research_log.py \
  --event-json '{"event":"factor_screen","factor":"high_52w","status":"started"}'
```

This:
1. Reads the last line of the log.
2. Extracts its `hash` (or uses the genesis hash if the log is empty).
3. Injects a `timestamp` if missing.
4. Computes the new hash and appends the record.

### Verify the chain

```bash
python3 scripts/verify_research_log.py -v
```

Exit codes: `0 = ok`, `1 = chain broken`, `2 = file missing`. This is CI-friendly — add
it to the pre-commit hook to prevent commits that silently clobber history.

### Legacy compatibility

The log existed **before** this scheme (3 pre-chain entries as of 2026-04-17). The
verifier accepts a **prologue** of unchained entries at the start of the file. Once the
first chained entry appears, all subsequent entries must be chained. Mixing chained
and unchained entries after the prologue is flagged as broken.

---

## Operating recipe

### Daily research flow
1. Before a new experiment, append a **forecast** event with the prediction:
   ```json
   {"event":"forecast","id":"factor-high_52w-2016_2023","prediction":"PASS likely",
    "rationale":"TWSE Tier-1 factor; 52w-high disposition effect documented in US"}
   ```
2. Run the experiment.
3. Append an **outcome** event with the resolved verdict:
   ```json
   {"event":"factor_screen","factor":"high_52w","passed_all":true,
    "gate_results":{"G0":true,"G1":true,...}}
   ```

The forecast-then-outcome order is what makes the prediction pre-registered.

### Pre-commit hook (recommended)
Add to `.git/hooks/pre-commit`:
```bash
python3 scripts/verify_research_log.py || {
  echo "Research log chain is broken — aborting commit."
  exit 1
}
```

### External timestamping (optional, for sharing with LPs)
Every ~50 entries, publish the latest chain tip somewhere external and unmodifiable:
- git tag: `git tag -a research-chain-$(date +%Y%m%d) -m "chain tip: <hash>"`
- Send the hash to a trusted third party (email, a tweet, a hash of it committed to an
  opentimestamps calendar)

This gives you evidence that the chain existed at time T with that specific history,
which closes the "rewrote everything from scratch" attack.

---

## Threat model (what this defends against, and what it doesn't)

| Threat | Defended? | Notes |
|--------|-----------|-------|
| Silent retroactive edits to past predictions | YES | Any change breaks the chain for every subsequent entry. |
| "Losing" unfavorable experiment results | YES | A missing entry breaks the chain; a present-but-unflattering entry is evidence. |
| Reordering entries | YES | Each entry commits to its predecessor. |
| Retroactively re-chaining the entire file | NO | An attacker with write access can rewrite the whole history. **Mitigation:** external timestamping (see above). |
| Adding a fake forecast after the outcome is known | PARTIAL | The chain won't catch this — but `docs/OUTCOME_VS_FORECAST.md` marks any row where `forecast_date >= outcome_date` as **INADMISSIBLE**, and git commit timestamps are a second witness. |
| Tampering with the outcome JSON (e.g., gate_results.json) | NO | The log records outcomes by reference (file path), not value. **Mitigation:** when an outcome event is logged, include a SHA-256 of the outcome file in the entry. |
| Byzantine code that appends fake events | NO | The log doesn't replace domain verification. Use with automated tests, CI, and second-pair-of-eyes reviews. |

---

## Forensic workflow: what to do if verification fails

```
$ python3 scripts/verify_research_log.py
[line 14] prev_hash mismatch: expected a1b2... got c3d4...
Summary: 3 legacy entries, 10 chained entries, 1 broken.
FAILED: chain is broken.
```

1. **Diagnose:** run with `-v` to locate the exact broken line.
2. **Do not silently rebuild.** Keep the broken file — it is evidence.
3. **Branch off:** copy `results/research_log.jsonl` to `results/research_log.jsonl.broken_YYYYMMDD`.
4. **Decide root cause:**
   - Editor reflow / accidental whitespace change → restore from git history.
   - Append script bug → freeze the file, fix the script, re-verify.
   - Actual tamper → escalate; do not clean up.
5. **Record the incident** as a new event in the log (which resumes the chain from the
   last-good entry's hash as prev_hash, with a `root_cause` field explaining the break).

---

## Schema of canonical event types

| event | Required fields | When emitted |
|-------|-----------------|--------------|
| `init` | — | First-time log creation |
| `forecast` | `id`, `prediction`, `rationale`, `source_doc` | Before an experiment runs |
| `factor_screen` | `factor`, `passed_all`, `gate_results`, `metrics`, `outcome_file_sha256` | Immediately after `screen_factor()` returns |
| `data_download` | `start_date`, `end_date`, `sources`, `n_rows`, `status` | Data pipeline runs |
| `backtest` | `run_id`, `config_snapshot_sha256`, `oos_sharpe`, `cagr`, `max_drawdown` | Backtest completes |
| `holdout` | `run_id`, `oos_sharpe`, `verdict` | One-shot holdout (immediately followed by `.holdout_used` lockfile) |
| `VETO` / `WARNING` | `trigger_id`, `metric`, `value`, `threshold` | F1-F8 triggers fire |
| `BLOCKED` | `root_cause`, `context` | Research halted for debugging |

Adding new event types is fine — the verifier only cares about the hash chain, not the
entry schema. Domain consumers of the log should tolerate unknown event types.

---

## Change log

| Version | Date | Change |
|---------|------|--------|
| 0.1 | 2026-04-18 | Initial scheme. Append + verify scripts shipped. Legacy 3-entry prologue accepted. |

---

**Document owner:** Operator
**Related:** `scripts/append_research_log.py`, `scripts/verify_research_log.py`, `docs/AUDIT_TRAIL.md`, `docs/OUTCOME_VS_FORECAST.md`, `docs/INDEPENDENT_VALIDATION_DRAFT.md`.
