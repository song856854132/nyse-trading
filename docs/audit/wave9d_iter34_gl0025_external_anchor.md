# Wave 9-D iter-34 GL-0025 External Anchor — Pre-Commit Metadata Capture

**Iteration:** iter-34 (#188)
**Governance row:** GL-0025 (Wave 9-D pre-authorization for 2024-2025 holdout consumption)
**Commit type:** Atomic governance-only
**Date (UTC):** 2026-04-28
**Iron Rule satisfied by this row:** Iron Rule 12 (holdout re-authorization required)

This audit file captures the pre-commit-knowable external-anchor reinforcement
metadata for GL-0025. It is the **internal copy** for in-repo provenance. The
**channel-2 reinforcement** is published off-repo by the operator post-commit
(see "Channel 2 — Operator off-repo publication" below); this file deliberately
does NOT capture the channel-2 URL/message-id, per Codex rev4 P1-1 sequencing-
contradiction fix (option-2 sequencing): publishing the channel-2 pointer in
the iter-34 commit body would re-create the impossible "row references its
own future authority" pattern that GL-0017 iter-21 was designed to avoid.

## Channel 1 — Signed annotated git tag

- **Tag name:** `gl-0025-wave-9d-pre-auth`
- **Tag pointer:** iter-34 commit (HEAD at tag time)
- **Signing posture:** **Annotated, UNSIGNED.** Mirrors the GL-0017 iter-21
  precedent (`v-iter21-gl-0017` is annotated-but-unsigned —
  `git verify-tag v-iter21-gl-0017` returns "no signature found"). The
  Lesson_Learn pattern at FRAMEWORK_AND_PIPELINE.md:1289 specifies "a signed
  git tag pushed to origin" as the ideal; iter-21 introduced annotated-without-
  signature as the operator-attested variant when the local environment lacks
  GPG/SSH signing material. iter-34 follows the same precedent for
  cross-row consistency.
- **Push target:** `origin master` (commit) + `origin gl-0025-wave-9d-pre-auth`
  (tag).
- **Verification at iter-35 pre-flight:** OPERATOR runs
  `git tag -l gl-0025-wave-9d-pre-auth` (local existence) +
  `git ls-remote --tags origin gl-0025-wave-9d-pre-auth` (remote existence) +
  `git rev-list --max-parents=0 gl-0025-wave-9d-pre-auth..HEAD` to confirm
  tag-to-HEAD chain unbroken. Refusal on any mismatch.

## Channel 2 — Operator off-repo publication (post-commit)

**RULE (this row):** After iter-34 commit + tag push, the operator publishes
ONE timestamped artifact through a channel that is independent of the repo
filesystem (so a malicious or accidental retroactive edit to repo bytes
cannot also retroactively edit the channel-2 record). Acceptable channels
mirror GL-0017 iter-21 precedent:

- A public GitHub gist URL whose creation timestamp is server-attested by
  GitHub (operator runs `gh gist create`), OR
- An email-to-self with a server-attested `Date:` header preserved by the
  receiving MTA, OR
- An equivalent timestamped channel meeting both: (a) **server-attested
  timestamp** (not operator-attested) and (b) **filesystem independence**
  from the working tree.

**Anti-pattern (explicitly forbidden):** the channel-2 record MUST NOT be
the iter-34 Codex consult session itself
(`019dcf3e-f28d-7c20-ac9b-46493b054c40`). That session is part of the
mandatory consult attestation captured in this very audit file + the GL-0025
row body — re-using it as channel-2 would collapse two independent channels
into one. Per Codex rev5 P1-1 anti-collapse closure.

**Sequencing (option-2 fix per Codex rev4 P1-1):** the URL/message-id of the
channel-2 artifact is NOT captured in this audit file (which is committed
in iter-34) NOR in the GL-0025 row body NOR in the iter-34 commit message
trailer. It is **published post-commit** and verified by the operator at
iter-35 pre-flight via:

1. Operator-local timestamp record (operator's own notes), AND
2. Server-attested timestamp lookup against the chosen channel (e.g.
   `gh gist view <id> --json createdAt`).

This avoids the "row references its own future authority" sequencing
contradiction. Pre-commit, the channel-2 URL/message-id does not exist
yet; capturing it in the iter-34 commit would require a placeholder that
either (a) gets backfilled post-commit (rewrites history) or (b) stays
unfilled (defeats the purpose). Option-2 instead defers channel-2
publication entirely and verifies at iter-35 pre-flight.

## Codex consult provenance

- **Session:** `019dcf3e-f28d-7c20-ac9b-46493b054c40` (server-side OpenAI
  conversation thread; multi-revision adversarial closure)
- **Revisions and GATE outcomes:**
  - rev1: `FAIL_NEW_P0` (3 P0 introduced by initial draft; closed via
    user option-A selections — block-size split, bit-identical Sharpe import
    via `nyse_core.metrics`, plumbing replicates iter-28 imports, test 1
    runtime value-equality, 5th terminal state)
  - rev2: `FAIL_NEW_P0` (1 P0 + 4 P1 + 1 P2 introduced by rev1 fixes;
    closed via user option-A selections)
  - rev3: `FAIL_STALE_LANGUAGE` (stale sqrt(52) language at GL-0025 §17.6
    + iter-35 Step 3; closed via §17.6 + iter-35 Step 3 rewrites)
  - rev4: `FAIL_SEQUENCING_CONTRADICTION` (`Channel-2-Anchor:` trailer in
    iter-34 commit body created impossible "post-commit publication
    pre-commit-captured" sequencing; closed via option-2 sequencing — no
    repo-captured channel-2 pointer, post-commit publication, iter-35
    verification)
  - rev5: `FAIL_STALE_TRAILER_REFERENCE` (rev4 fix incomplete — DRAFT 1
    `Criteria cited` column still cited the stale `Channel-2-Anchor:`
    trailer; closed via stale-reference removal across all cross-references
    and §17.8)
  - **rev6:** `PASS_READY_FOR_ITER34` — 0 P0 (confidence 9/10) + 0 P1
    (confidence 8/10) + 0 P2. Anchor and sequencing contradictions are
    stated consistently across the row body, cross-references, and §17.8:
    no repo-captured channel-2 pointer, post-commit operator publication,
    iter-35 verification, no reuse of Codex session as anchor channel.
- **Total tokens (rev6 reported):** 4,399,497

## Frozen artefact sha256s (this row)

Anchored from iter-33 P0-E pre-land + Wave 8 invariants:

| Artefact | sha256 | Origin |
|---|---|---|
| `config/gates_v2.yaml` | `bd0fc5de89307dab36fe82c12e0d921a7fa145376e2ef01aad8d000dd92979d2` | Wave 6 GL-0017 frozen |
| `config/gates.yaml` | `521b7571c330a5a1e87642eb9e5c0869ae8dc23cba3a1a175baf21a42f559af4` | Wave 6 GL-0017 frozen |
| `scripts/run_holdout_once_long_short.py` | `48ebff546d1d2c8ceca777714bfc8a4068899cacbfd233dd57178d3fd65c5b65` | iter-33 P0-E pre-land (commit `810b69a`) |
| `scripts/run_holdout_once.py` | `d4c52baab6c8b6c958e79488dbc6bfc2a0f8632c436097e886dd703e637b6067` | Wave 6 P0-C pre-land (read-only, retained) |
| `scripts/run_workstream_d_single_factor.py` | `e15983ed057f1768fabca78a88c5a323f3bc66825eb02b6934080a83119a8a33` | Wave 8 P0-D pre-land (read-only) |
| `scripts/check_holdout_guard.py` | `e2c9933f4aeff21df0a4216f8ddd771be642ecade08b678f7aecbb32d14cb8a1` | iter-33 provenance update (was `cce7bd00...647bd0ac`) |
| `tests/unit/test_run_holdout_once_long_short.py` | `233123d6c93d605af4b3f82933e8fef623cd8895bd5a8c207766634fb1ec51e3` | iter-33 P0-E pre-land |
| `results/validation/wave8_d_single_factor/result.json` | `1d1a8be0cb3c4cb1cb3e4de73f0e2b7654c5c080a33f51f5912c2dfd762d0bf2` | W8-D iter-28 evidence |

## Iron Rule 12 verbatim 3-line zero-transitive-authority attestation

The following three lines appear bit-identically in:

1. The GL-0025 row body (this commit's `docs/GOVERNANCE_LOG.md` modification)
2. The §17.8 narrative (this commit's `docs/FRAMEWORK_AND_PIPELINE.md`
   modification)
3. The iter-33 P0-E commit message (commit `810b69a`, retroactively the
   pre-authorization handshake)
4. This audit file (immediately below)
5. The iter-34 commit message body

```
1. ALL authority to consume the 2024-2025 holdout originates in this GL-0025 row.
2. GL-0024 routing GRANTS ZERO authority to consume; W8-D PASS verdict establishes ELIGIBILITY only.
3. iter-33 P0-E pre-landed runner is DORMANT until GL-0025 commits; runner sha256 pin without committed governance row = NO authority.
```

## Hash chain anchor

- **iter-33 chain tip (this row's `prev_hash`):**
  `aace91f2b4894f30762a01f08d8416954aaf14c2ee6bfe0daddfca9b01e53706`
- **iter-33 commit hash:** `810b69a0ec0282762b86699427d6d403225daaa9`
- **iter-32 chain tip (iter-33's `prev_hash`):**
  `c7776c0a4677295c5b0dcf1a0efbc8064c82107c5c4c02e15c5947ac88861ba3`
