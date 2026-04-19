# Executive Summary — Non-Quant Audience

> **Audience.** Chief Risk Officer, Chief Compliance Officer, external counsel,
> internal audit, regulatory examiner, board member. Anyone who may need to
> understand or defend this program without a quantitative finance background.
>
> **Frozen.** 2026-04-19. Any edit requires a row in `docs/GOVERNANCE_LOG.md`
> and a commit reference. No silent updates.
>
> **Two-page companion.** The quant-audience version lives at
> `docs/NYSE_ALPHA_ONE_PAGER.md`. The two MUST stay consistent: a change in
> one requires a change in the other in the same commit.

---

## What we do (1 paragraph)

We are building a systematic U.S. stock-picking program that runs on the NYSE.
Each Friday after the market closes, a computer program ranks every stock in
the S&P 500 using a small set of pre-declared scoring rules and buys the
twenty highest-ranked stocks at equal weight on the following Monday. There is
no human discretion once the program runs — every trade can be traced back to
a rule, a data source, and a timestamp. **The program is not trading any money
today.** It is in a research stage in which we are still deciding whether the
rules work well enough to justify even a small dollar allocation.

## Who benefits (1 paragraph)

If the program eventually passes all of its pre-declared tests, the intended
beneficiaries are the firm's clients and the firm itself — through returns
that are designed to come from price differences between stocks rather than
from the direction of the market as a whole. Because the rules and the tests
are written down before any trading, the program is also a compliance and
audit aid: every past decision is reproducible, every future decision is
explainable, and every failure mode has a pre-written response. Regulators and
external auditors benefit from a program whose behavior is easier to examine
than a discretionary trader's.

## How we control risk (5 bullets)

- **Pre-declared stop rules.** Eight named conditions, frozen on 2026-04-15,
  describe exactly when the program must halt or reduce exposure. They cover
  signal decay, drawdown, concentration, turnover, cost, regime breaks, and
  stale data. We cannot tune or relax them after seeing results
  (`config/falsification_triggers.yaml`, `docs/RISK_REGISTER.md`).
- **Documented daily review.** Every trading day begins with a signed
  pre-trade attestation and ends with a signed post-trade attestation. Both
  forms check the same list of limits every day and are kept for six years.
  Skipping a form halts trading for that day
  (`docs/templates/PRE_TRADE_ATTESTATION.md`, `docs/templates/POST_TRADE_ATTESTATION.md`).
- **Position and concentration limits.** No single stock can exceed 10 percent
  of the portfolio; no industry sector can exceed 30 percent; portfolio market
  sensitivity is held in a bounded range; daily losses cap at 3 percent before
  the program stops itself (`config/strategy_params.yaml`, `docs/RISK_LIMITS.md`).
- **Untouched out-of-sample data.** Two years of market history (2024 and
  2025) are reserved and have not been looked at. They exist only to judge the
  program after research is complete, which prevents the common failure of
  "tuning until the test passes" (iron rule 1,
  `docs/REPRODUCIBILITY.md`).
- **Written-down authorization log.** Every decision — to freeze a threshold,
  to reject a factor, to graduate to a new deployment stage, to activate a
  kill switch — is appended to `docs/GOVERNANCE_LOG.md` with date, approver,
  evidence, and any dissent. History is never rewritten.

## What would cause us to halt (5 bullets)

- **A signal-death or factor-death condition fires.** If the scoring rules
  stop predicting returns for two months in a row, or if core factors flip
  sign three times in two months, the program halts and switches back to
  paper mode (triggers F1 and F2).
- **Drawdown breaches 25 percent.** The program stops all new orders and
  escalates to the Chief Risk Officer. Resumption requires a new authorization
  row in `docs/GOVERNANCE_LOG.md` (trigger F3).
- **Daily loss exceeds 3 percent.** The kill switch engages
  intraday; no additional orders are submitted that day. The incident is
  recorded in `docs/AUDIT_TRAIL.md` the same day.
- **A data-quality or corporate-action failure is detected.** Missing prices
  older than ten calendar days, or an unadjusted split or dividend on a held
  position, halts that day's rebalance and forces a data re-pull before
  trading resumes (trigger F8).
- **Any of the four iron rules is violated.** The program stops. Iron rules
  are (1) no use of reserved 2024-2025 data during research, (2) no changing
  a threshold after seeing a result, (3) no mocking the database in
  integration tests, (4) no committing secrets. Violations are supervisory
  incidents regardless of whether live money was in the market
  (`docs/RALPH_LOOP_TASK.md`).

## How we prove it works (3 bullets)

- **Pre-registered criteria.** Six scoring rules and six pass/fail gates are
  written down before any data is tested. We record the prediction in
  `docs/OUTCOME_VS_FORECAST.md` before the experiment runs and the result
  afterward, so the hit rate on our own predictions is itself a track record.
- **Reproducible from raw inputs.** Any person with the source code can
  reconstruct the entire research database from raw vendor pulls and verify
  every published number. A tamper-evident log of research events chains each
  entry to the previous one with a cryptographic hash; a single edit
  anywhere in the history is detectable
  (`docs/REPRODUCIBILITY.md`, `results/research_log.jsonl`).
- **Honest reporting of failures.** As of 2026-04-18, **all six scoring rules
  that have been tested on real data have failed** the pass/fail gates.
  The program is in research and no money is at risk. We report this as a
  test of our own process, not as a success story: when a program fails its
  own pre-declared tests, the correct action is to halt, document, and learn
  — which is what has happened here (`docs/GOVERNANCE_LOG.md` GL-0009,
  `docs/OUTCOME_VS_FORECAST.md`).

## Who owns what

| Role | Responsibility | Primary artifacts |
|---|---|---|
| Portfolio Manager | Strategy design, factor selection, research velocity | `docs/NYSE_ALPHA_ONE_PAGER.md`, `docs/NYSE_ALPHA_TECHNICAL_BRIEF.md`, `docs/NYSE_ALPHA_RESEARCH_RECORD.md` |
| Chief Risk Officer | Risk limits, kill-switch authority, stop-rule thresholds | `docs/RISK_REGISTER.md`, `docs/RISK_LIMITS.md`, `config/falsification_triggers.yaml`, `config/strategy_params.yaml` |
| Chief Compliance Officer | Regulatory posture, supervisory review, attestation retention | `docs/SEC_FINRA_COMPLIANCE.md`, `docs/templates/PRE_TRADE_ATTESTATION.md`, `docs/templates/POST_TRADE_ATTESTATION.md`, `docs/AUDIT_TRAIL.md` |
| Model Validator (independent) | SR 11-7 independence, model-risk review, gate-verdict audit | `docs/MODEL_VALIDATION.md` §1.5, `docs/INDEPENDENT_VALIDATION_DRAFT.md` |
| Chief Technology Officer | Reproducibility, CI gates, data infrastructure | `docs/REPRODUCIBILITY.md`, `docs/DATA_DICTIONARY.md`, `.github/workflows/ci.yml`, `.pre-commit-config.yaml` |
| Internal Audit | Authorization-register coverage, retention-protected commits | `docs/GOVERNANCE_LOG.md`, `docs/AUDIT_TRAIL.md`, `docs/MLOPS_LIFECYCLE.md` |
| External Counsel | ToS and license review for each data vendor | `docs/vendors/finmind.md`, `docs/vendors/edgar.md`, `docs/vendors/finra.md` |
| Investment Committee | Deployment-stage graduations (paper → shadow → minimum live → scale) | `config/deployment_ladder.yaml`, `docs/GOVERNANCE_LOG.md` §5 pending authorizations |

---

## Current state (as of 2026-04-19)

- **Stage:** research. No paper trading. No live capital. $0 deployed.
- **Factors admitted to ensemble:** 0 of 6 tested.
- **Factors rejected at gates:** 6 (ivol_20d, high_52w, momentum_2_12,
  piotroski, accruals, profitability). Each rejection is recorded in
  `docs/GOVERNANCE_LOG.md` rows GL-0002 through GL-0007.
- **Stop-rule thresholds:** frozen 2026-04-15
  (`config/falsification_triggers.yaml:5`, GOVERNANCE_LOG GL-0001).
- **Reserved data (2024-2025):** untouched.
- **Authorization register:** `docs/GOVERNANCE_LOG.md`, nine authorization
  rows, append-only.
- **Daily attestations:** templates frozen; not yet in daily use because no
  trading is occurring.

## Who to contact

- Questions about the rules or the research process — Portfolio Manager.
- Questions about risk limits, the stop rules, or the kill switch — CRO.
- Questions about regulatory posture, supervisory review, or the attestation
  templates — CCO.
- Questions about data sources, vendor licensing, or reproducibility — CTO.
- Regulatory or audit requests — CCO, then Internal Audit.
