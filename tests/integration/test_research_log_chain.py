"""Integration test for the research log SHA-256 hash chain.

Iron rule 6: every research artifact must be appended to results/research_log.jsonl
with SHA-256 hash chaining. If the chain breaks, halt and repair. This test walks
the real log file end to end and asserts the chain is intact.

Iron rule 3 (no mocks on the database path) is respected: this test reads the
real results/research_log.jsonl on disk and does NOT import any scripts.*
module (scripts/ is not on sys.path and is not a package). We reimplement the
canonical hash computation here from pure stdlib so the test guards against
both log tampering and accidental drift in the writer/verifier scripts.

Envelope shape (produced by scripts/append_research_log.py):
    {"prev_hash": "<64-hex>", "entry": {...payload...}, "hash": "<64-hex>"}
where hash = sha256(prev_hash_bytes + canonical(entry_bytes)).

Canonical form: json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8").

Legacy pre-chain prologue: a handful of early entries (written before the chain
was introduced) do not carry the envelope. They are accepted ONLY at the head of
the file, before any chained entry appears. Any legacy entry appearing after a
chained entry is treated as a break.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

LOG_PATH = Path(__file__).resolve().parents[2] / "results" / "research_log.jsonl"
GENESIS_PREV_HASH = "0" * 64


def _canonical(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _compute_hash(prev_hash: str, entry: dict) -> str:
    h = hashlib.sha256()
    h.update(prev_hash.encode("utf-8"))
    h.update(_canonical(entry))
    return h.hexdigest()


def _walk_chain(log_path: Path) -> tuple[int, int, int, str, list[str]]:
    """Walk a research-log file and return (legacy, chained, broken, tip, errors).

    The first break (if any) is reported in errors[0] including the 1-based line
    number. Subsequent breaks are also appended so a full repair can be planned.
    """
    prev_hash = GENESIS_PREV_HASH
    seen_chained = False
    legacy = 0
    chained = 0
    broken = 0
    errors: list[str] = []

    with log_path.open() as f:
        for lineno, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                broken += 1
                errors.append(f"line {lineno}: invalid JSON ({exc})")
                continue

            has_envelope = isinstance(obj, dict) and "prev_hash" in obj and "entry" in obj and "hash" in obj

            if not has_envelope:
                if seen_chained:
                    broken += 1
                    errors.append(
                        f"line {lineno}: legacy (unchained) entry appeared after "
                        f"chained entry — chain integrity broken"
                    )
                else:
                    legacy += 1
                continue

            seen_chained = True
            chained += 1

            if obj["prev_hash"] != prev_hash:
                broken += 1
                errors.append(
                    f"line {lineno}: prev_hash mismatch — expected "
                    f"{prev_hash[:16]}... got {obj['prev_hash'][:16]}..."
                )
                prev_hash = obj["hash"]
                continue

            recomputed = _compute_hash(obj["prev_hash"], obj["entry"])
            if recomputed != obj["hash"]:
                broken += 1
                errors.append(
                    f"line {lineno}: hash mismatch — stored {obj['hash'][:16]}... "
                    f"recomputed {recomputed[:16]}..."
                )
                prev_hash = obj["hash"]
                continue

            prev_hash = obj["hash"]

    return legacy, chained, broken, prev_hash, errors


class TestRealResearchLogChain:
    """The canonical guard: walks the real results/research_log.jsonl on disk."""

    def test_log_file_exists(self) -> None:
        assert LOG_PATH.exists(), f"research log missing at {LOG_PATH}; iron rule 6 requires it"

    def test_real_log_chain_is_unbroken(self) -> None:
        """Fail with the FIRST broken line number if the chain is compromised."""
        legacy, chained, broken, tip, errors = _walk_chain(LOG_PATH)

        if broken:
            pytest.fail(
                "research log chain is broken:\n"
                + "\n".join(errors)
                + f"\n(summary: legacy={legacy} chained={chained} broken={broken})"
            )

        # Positive assertions so a silently empty or legacy-only log can't pass.
        assert chained >= 1, (
            f"research log has no chained entries yet "
            f"(legacy={legacy}); the chain must have been seeded by now"
        )
        assert len(tip) == 64 and all(c in "0123456789abcdef" for c in tip), (
            f"chain tip is not a 64-hex digest: {tip!r}"
        )


class TestTamperDetection:
    """Guard against writer/verifier rot by feeding known-bad synthetic logs."""

    @staticmethod
    def _write_chain(path: Path, entries: list[dict]) -> str:
        """Write a well-formed chained log and return the final tip hash."""
        prev = GENESIS_PREV_HASH
        with path.open("w") as f:
            for entry in entries:
                h = _compute_hash(prev, entry)
                f.write(
                    json.dumps(
                        {"prev_hash": prev, "entry": entry, "hash": h},
                        sort_keys=True,
                    )
                    + "\n"
                )
                prev = h
        return prev

    def test_clean_synthetic_log_verifies(self, tmp_path: Path) -> None:
        p = tmp_path / "clean.jsonl"
        entries = [{"event": "a", "i": 1}, {"event": "b", "i": 2}, {"event": "c", "i": 3}]
        tip = self._write_chain(p, entries)
        legacy, chained, broken, walked_tip, errors = _walk_chain(p)
        assert broken == 0, errors
        assert chained == 3
        assert legacy == 0
        assert walked_tip == tip

    def test_tampered_entry_body_is_detected(self, tmp_path: Path) -> None:
        """Editing an entry after the fact must break hash recomputation."""
        p = tmp_path / "tampered.jsonl"
        self._write_chain(p, [{"event": "a", "i": 1}, {"event": "b", "i": 2}])

        lines = p.read_text().splitlines()
        obj = json.loads(lines[0])
        obj["entry"]["i"] = 999  # silent edit; hash no longer matches body
        lines[0] = json.dumps(obj, sort_keys=True)
        p.write_text("\n".join(lines) + "\n")

        legacy, chained, broken, _tip, errors = _walk_chain(p)
        assert broken >= 1
        assert errors and "line 1" in errors[0]
        assert "hash mismatch" in errors[0]

    def test_dropped_link_is_detected(self, tmp_path: Path) -> None:
        """Deleting the middle entry must surface a prev_hash mismatch on the next."""
        p = tmp_path / "dropped.jsonl"
        self._write_chain(
            p,
            [{"event": "a", "i": 1}, {"event": "b", "i": 2}, {"event": "c", "i": 3}],
        )

        lines = p.read_text().splitlines()
        del lines[1]  # drop middle; line 3's prev_hash now points to a vanished hash
        p.write_text("\n".join(lines) + "\n")

        legacy, chained, broken, _tip, errors = _walk_chain(p)
        assert broken >= 1
        # After deletion, the new line 2 is the former line 3 and should fail prev_hash.
        assert any("line 2" in e and "prev_hash mismatch" in e for e in errors), errors

    def test_legacy_after_chained_is_detected(self, tmp_path: Path) -> None:
        """A legacy (unchained) entry after a chained entry is a chain break."""
        p = tmp_path / "legacy_after.jsonl"
        self._write_chain(p, [{"event": "a", "i": 1}])
        with p.open("a") as f:
            f.write(json.dumps({"event": "legacy", "i": 2}) + "\n")

        legacy, chained, broken, _tip, errors = _walk_chain(p)
        assert broken >= 1
        assert any("line 2" in e and "legacy" in e.lower() for e in errors), errors

    def test_legacy_prologue_is_accepted(self, tmp_path: Path) -> None:
        """Legacy entries AT THE HEAD (before any chained entry) are valid."""
        p = tmp_path / "prologue.jsonl"
        with p.open("w") as f:
            f.write(json.dumps({"event": "legacy-1"}) + "\n")
            f.write(json.dumps({"event": "legacy-2"}) + "\n")
        # Now append two chained entries starting from genesis
        prev = GENESIS_PREV_HASH
        with p.open("a") as f:
            for entry in [{"event": "a"}, {"event": "b"}]:
                h = _compute_hash(prev, entry)
                f.write(
                    json.dumps(
                        {"prev_hash": prev, "entry": entry, "hash": h},
                        sort_keys=True,
                    )
                    + "\n"
                )
                prev = h

        legacy, chained, broken, tip, errors = _walk_chain(p)
        assert broken == 0, errors
        assert legacy == 2
        assert chained == 2
        assert tip == prev

    def test_genesis_prev_hash_is_required(self, tmp_path: Path) -> None:
        """The first chained entry's prev_hash must equal GENESIS_PREV_HASH."""
        p = tmp_path / "bad_genesis.jsonl"
        entry = {"event": "a"}
        bad_prev = "ff" * 32  # not genesis
        h = _compute_hash(bad_prev, entry)
        p.write_text(json.dumps({"prev_hash": bad_prev, "entry": entry, "hash": h}, sort_keys=True) + "\n")

        legacy, chained, broken, _tip, errors = _walk_chain(p)
        assert broken >= 1
        assert any("line 1" in e and "prev_hash" in e for e in errors), errors
