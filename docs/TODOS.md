# TODOS — NYSE ATS Framework

> Eng review 2026-04-15. Items ordered by phase dependency.

> **Related docs added 2026-04-17:**
> [MODEL_VALIDATION.md](MODEL_VALIDATION.md) (SR 11-7-style validation report) |
> [CAPACITY_AND_LIQUIDITY.md](CAPACITY_AND_LIQUIDITY.md) (AUM capacity + unwind)
> — both expose TODO-10 / TODO-11 as blocking items before any promotion.

## Phase 0

### TODO-4: Structured Logging Standard for nyse_ats
**What:** Configure structlog or stdlib logging with JSON output in nyse_ats.
**Why:** nyse_core uses diagnostic returns (no logging import), but nyse_ats has 10+ modules making API calls, DB writes, and order submissions. Without a logging standard, each module invents its own format, making production debugging painful.
**How to apply:** Create a logging config module. Log levels: DEBUG (API responses), INFO (rebalance events), WARNING (data gaps), ERROR (failures). All log entries include `rebalance_date` + `run_id` for traceability across a single pipeline run.
**Depends on:** Nothing. Phase 0 deliverable.

### TODO-5: Dependency Pinning Strategy
**What:** Choose uv or poetry with a lockfile. Pin major versions in pyproject.toml, exact versions in lockfile.
**Why:** 40-week project with ~15 dependencies. NautilusTrader has breaking API changes between minor versions. Without pinning, a `pip install` 6 months from now could break the entire system.
**How to apply:** Decide tool (uv recommended — fastest, lockfile built-in). Add `uv.lock` or `poetry.lock` to repo. CI tests against pinned versions.
**Depends on:** Nothing. Phase 0 deliverable.

## Phase 1

### TODO-3: VectorBT Version Strategy
**What:** Evaluate VectorBT open-source (v0.x) vs VectorBT PRO (commercial).
**Why:** VectorBT open-source and PRO have diverged. Open-source may not receive updates. PRO has licensing cost. The plan lists vectorbt as a dependency but doesn't specify which.
**How to apply:** During Phase 1, test both versions against the synthetic backtest. If PRO features are needed (portfolio optimization, advanced metrics), factor in licensing. Pin the chosen version in lockfile.
**Depends on:** TODO-5 (dependency pinning).

## Phase 2

### TODO-1: Falsification Trigger Frozen-Date Enforcement in Code
**What:** `falsification.py` should hash the triggers config at freeze time and refuse to evaluate if the hash changes.
**Why:** The frozen_date is currently a YAML comment — nothing prevents editing thresholds after the freeze date. Under drawdown pressure, the temptation to "adjust" thresholds is real. This is the same class of bug as the 0050 ETF split silently corrupting regime detection for months on TWSE.
**How to apply:** On first run after frozen_date, compute SHA-256 of falsification_triggers.yaml and store it in live.duckdb. On every subsequent run, recompute and compare. If mismatch → VETO + Telegram alert with diff. ~30 LOC in falsification.py.
**Depends on:** storage/live_store.py (Phase 2).

### TODO-6: CI/CD Pipeline (GitHub Actions)
**What:** GitHub Actions workflow: pytest + mypy + ruff + secret scan. Pre-commit hooks for local development.
**Why:** 40-week project with 998 tests. Without CI, regressions can silently accumulate on feature branches. The plan lists CI/CD as a Phase 1 deliverable, but no workflow file exists yet.
**How to apply:** Create `.github/workflows/ci.yml`: run pytest (all 3 tiers: unit, integration, property), mypy strict mode, ruff linting, trufflehog/gitleaks for secret scanning. Add `.pre-commit-config.yaml` with ruff + mypy hooks. Badge in README.
**Depends on:** TODO-5 (dependency pinning — CI needs reproducible installs).

### TODO-7: Automated Data Freshness Monitor
**What:** Scheduled check verifying each data source (FinMind OHLCV, EDGAR filings, FINRA short interest) delivered within its expected cadence. Fires Telegram alert on staleness.
**Why:** F8 falsification trigger only fires during rebalance (~weekly). This catches staleness proactively — e.g., "FinMind hasn't delivered since Tuesday" on Wednesday, not "skip rebalance because features are stale" on Friday. ~100 LOC.
**How to apply:** Per-source freshness query against DuckDB (most recent date per source vs expected cadence: OHLCV=daily, EDGAR=24h post-filing, FINRA=bi-monthly with 11-day lag). Threshold config in `data_sources.yaml`. Integrates with existing `alert_bot.py`. Can run as a cron job or pre-rebalance check.
**Depends on:** Data adapters (Phase 2), live_store.py (Phase 2), alert_bot.py (Phase 2).

### TODO-8: Extract Shared Normalize Chain (DRY Refactor)
**What:** `research_pipeline.py:87-131` and `pipeline.py._normalize_features()` both implement winsorize → rank_percentile → impute → drop-all-NaN. After the architecture fixes they'll be behaviorally identical but still duplicated (~45 LOC + ~25 LOC). Extract a shared `normalize_feature_matrix()` function in `normalize.py` or a new `feature_pipeline.py`.
**Why:** DRY violation. If the normalize logic changes (e.g., adding a new step, changing winsorize percentiles), it must be updated in two places. The risk is train/serve skew — the exact bug class that prompted the CEO review fix.
**How to apply:** Extract function with signature `normalize_feature_matrix(raw_features: DataFrame, rebalance_date: date) -> (DataFrame, Diagnostics)`. Both pipelines call it. Trigger: next time either pipeline's normalize logic needs to change.
**Depends on:** Architecture fix #1 (winsorize in pipeline.py) must be complete first.

## Investigation Findings (2026-04-17)

> From `/investigate` + `/codex` cross-model analysis of strategy vs SPY underperformance in 2024-2025.

### TODO-9: Use RSP (Equal-Weight ETF) as Primary Benchmark
**What:** Replace SPY as the performance benchmark with RSP (Invesco S&P 500 Equal Weight ETF). Keep SPY for regime overlay only.
**Why:** The strategy is structurally equal-weight. Benchmarking against cap-weight SPY bakes in a permanent headwind during concentration regimes (2024: RSP +12% vs SPY +25%, a 13pp gap from weighting alone). RSP is the apples-to-apples comparison. SPY outperformance in 2024-2025 is dominated by Magnificent 7 concentration — an architectural mismatch, not a signal failure.
**How to apply:** Add RSP price series to data adapters. Report both RSP-relative and SPY-relative Sharpe in backtest output and dashboard. Use RSP for factor IC calculation. Keep SPY for regime overlay (SMA200).
**Depends on:** FinMind adapter (Phase 2 — already built).

### TODO-10: Monitor Factor Weight Signs on Real Data
**What:** After first real-data backtest, verify that momentum_2_12, 52w_high, and ewmac carry positive Ridge weights.
**Why:** Synthetic backtest showed all price/volume factors with negative weights (anti-momentum bet). This may be a synthetic data artifact OR a real signal inversion bug. On real NYSE data, momentum has a well-documented positive premium. If weights remain negative on real data, investigate sign convention in registry.py or label timing.
**How to apply:** Add assertion/warning in backtest output: if momentum factor weight is negative after training on >2 years of real data, flag for manual review. Check that INVERTED_FACTORS list in registry is correct.
**Depends on:** Real data backtest (Phase 3).

### TODO-11: Validate Strategy on Real S&P 500 Data
**What:** Execute full walk-forward backtest using real data from FinMind/EDGAR/FINRA adapters (all built). The synthetic backtest in `generate_figures.py` is a pipeline smoke test, not a signal validation.
**Why:** All signal quality conclusions (IC, factor weights, Sharpe) are currently from synthetic data. The synthetic generator creates both returns AND factors from the same latent traits — it's a self-fulfilling world. No investment decision should be made based on synthetic metrics.
**How to apply:** Run `scripts/download_data.py` → populate `research.duckdb` → run `scripts/run_backtest.py` with 2016-2023 research period. Compare results to synthetic baseline. This is the single highest-priority validation task.
**Depends on:** Data download scripts, FinMind API key.

### TODO-12: Monitor Market Breadth for Strategy Timing
**What:** Track RSP/SPY ratio as a breadth indicator. When breadth improves (ratio rising), the equal-weight strategy should recover relative to SPY.
**Why:** Web data (Capital Group, mid-2025) shows breadth already improving: non-Mag7 stocks represented 59% of SPY returns by Q3 2025, up from 21% in 2024. Equal-weight approaches historically outperform over 20-year horizons. The 2024-2025 underperformance may be regime-specific.
**How to apply:** Add RSP/SPY ratio to dashboard. Alert when ratio crosses 6-month moving average (breadth regime change). Consider as input to deployment timing (don't launch live during extreme concentration).
**Depends on:** Dashboard (Phase 4), RSP data (TODO-9).

### TODO-2: Corporate Action Guard Between Signal and Execution
**What:** Before submitting TradePlan orders on Monday, check for corporate actions (splits, dividends) on held stocks that occurred between Friday close (signal generation) and Monday open (execution).
**Why:** A 4:1 split between signal and execution means the TradePlan has target_shares based on pre-split prices. Without a guard, you'd buy 4x the intended position. This is the EXACT bug class that corrupted TWSE regime detection for months (0050 ETF 4:1 split, Lesson_Learn Section 2.1).
**How to apply:** `nautilus_bridge.py` queries FinMind/data source for corporate actions on held symbols since TradePlan.decision_timestamp. If any found → cancel affected orders, re-run portfolio.build() with adjusted prices, regenerate TradePlan. ~50 LOC.
**Depends on:** nautilus_bridge.py (Phase 2), finmind_adapter.py (Phase 2).

## Documentation & Governance (2026-04-17)

> From documentation gap analysis vs enterprise-tier standards (AQR / Two Sigma / MSCI / Bloomberg / SR 11-7).
> Current 12-doc set has strong coverage; the items below close the remaining gaps auditors, LPs, and regulators expect.

### TODO-13: Independent Validation Section in MODEL_VALIDATION.md
**What:** Add an explicit "Independence" subsection naming the developer(s), validator(s), dates, and any scope limitations. If validator = developer, state that honestly and list a target date for third-party review.
**Why:** SR 11-7 §V requires model validation independent of development. Self-authored validation is acceptable as an interim state only if explicitly documented. Silent self-validation is an audit finding.
**How to apply:** Add §1.5 "Independence statement" to `MODEL_VALIDATION.md`. Fields: developer, validator, validation date, validator independence (yes/no/partial), planned external review date. Update at each material model change.
**Depends on:** Nothing. ~15 min edit.

### TODO-14: Formal Risk Register
**What:** Create `docs/RISK_REGISTER.md` — single table of known risks with columns: ID, description, category (model/data/execution/operational), severity (1-5), likelihood (1-5), mitigation, owner, review date.
**Why:** Risks are currently scattered across MODEL_VALIDATION §3.4, FRAMEWORK §1.2, CAPACITY §6, AUDIT_TRAIL. Scattered risks get forgotten. Enterprise review expects one table where severity × likelihood is comparable across risks. SR 11-7 §VI.
**How to apply:** Seed with ~20 risks pulled from existing "known limits" sections. Assign owner + review cadence (quarterly). Link from MODEL_VALIDATION and FRAMEWORK as canonical source.
**Depends on:** Nothing. ~2 hr initial compile.

### TODO-15: Performance Attribution Report Template
**What:** Template + sample output for monthly performance attribution (per-factor contribution, per-sector contribution, per-name top/bottom 10, IC realized vs expected, cost breakdown). Lives at `docs/templates/ATTRIBUTION_REPORT.md` with JSON schema sidecar.
**Why:** Attribution is the #1 LP-facing deliverable. `attribution.py` will emit per-factor P&L but there's no agreed report shape. Without a template, each month's output is ad-hoc → non-comparable over time. MSCI/Bloomberg tear-sheet pattern.
**How to apply:** Draft the Markdown template (frozen layout), then JSON schema for programmatic fill. Include a worked example using synthetic backtest numbers. Populate with real numbers once TODO-11 completes.
**Depends on:** `attribution.py` (already in plan), real-data backtest (TODO-11).

### TODO-16: Reproducibility Pack Specification
**What:** `docs/REPRODUCIBILITY.md` — one-page spec for the "research pack" produced by every material run: git SHA, config hashes (strategy/gates/data_sources YAMLs), data snapshot hash (DuckDB schema + row counts), one-line reproduction command, Python version, dependency lockfile hash.
**Why:** Reproducibility is the single most common audit ask. Without a standard pack, each reviewer asks for different artifacts. Also required implicitly by SR 11-7 "documentation sufficient for unfamiliar party to understand and re-run."
**How to apply:** Add `scripts/make_research_pack.py` that emits a `results/packs/<run_id>/manifest.json` alongside config/snapshot files. Document the pack format in REPRODUCIBILITY.md. Wire into `run_backtest.py`.
**Depends on:** Nothing. ~1 hr spec + ~2 hr script.

### TODO-17: Data Dictionary Consolidation
**What:** `docs/DATA_DICTIONARY.md` — per-field table: source, vendor, publication lag, PiT rule, canonical column name, dtype, nullable policy, downstream consumers, owner.
**Why:** Data fields are described in FRAMEWORK §3, MODEL_VALIDATION §4.1, schema.py, and config_schema.py — four places, easy to drift. A single dictionary is the industry norm and the only workable artifact for a data-quality exam.
**How to apply:** Generate initial version from `schema.py` constants + FinMind/EDGAR/FINRA adapter docstrings. Add publication-lag column from `pit.py`. Review cadence: on any adapter schema change.
**Depends on:** Nothing. ~3 hr.

### TODO-18: Vendor Due-Diligence Files
**What:** `docs/vendors/FINMIND.md`, `docs/vendors/EDGAR.md`, `docs/vendors/FINRA.md` — each with: vendor contact, SLA terms, license/ToS summary, historical outage log, failover plan, data-quality issues observed, escalation path.
**Why:** Recurring finding in algo-trading regulatory exams. FINRA 2026 priorities specifically call out third-party data governance. Also prerequisite for any LP DDQ.
**How to apply:** Template each file (same structure). Populate FinMind first (primary source). Outage log is append-only — each incident adds a dated row. Link from SEC_FINRA_COMPLIANCE.
**Depends on:** Nothing. ~1 hr per vendor.

### TODO-19: Governance / Decision Log
**What:** `docs/GOVERNANCE_LOG.md` — append-only log of authorization decisions: who approved what, when, against what criteria, with what dissent. Applies to: paper→shadow graduation, shadow→live graduation, falsification-trigger freeze, threshold changes, factor additions, model swaps, kill-switch activations.
**Why:** AUDIT_TRAIL logs experiments (what ran); this logs approvals (what was sanctioned). Different artifact. Investment Committee / Model Risk Committee analog. SR 11-7 §VII governance requirement.
**How to apply:** Template row format: date, decision, approver(s), criteria cited, evidence link, dissent. Start with all graduation gates from `deployment_ladder.yaml`.
**Depends on:** Nothing. ~1 hr initial, then per-decision updates.

### TODO-20: Pre-Trade and Post-Trade Compliance Attestations
**What:** Template attestation forms: pre-trade (daily, before first order submission — confirms kill switch off, no earnings conflict, within risk limits) and post-trade (daily EOD — reconciles fills, flags rejects, confirms no limit breach).
**Why:** SEC Rule 15c3-5 (Market Access) and FINRA Rule 3110 require documented supervisory review. SEC_FINRA_COMPLIANCE.md maps the rules but lacks the actual attestation artifact auditors collect.
**How to apply:** Two Markdown templates under `docs/templates/`. Pre-trade checklist: 8-10 items. Post-trade: fills-vs-plan table, rejection reasons, limit breaches (none expected), sign-off line. Auto-populate from `live.duckdb` where possible.
**Depends on:** `live_store.py` (Phase 2), `falsification.py` (Phase 4).

### TODO-21: Populate CAPACITY_AND_LIQUIDITY Placeholders
**What:** Fill §3.1 "Realized participation distribution," §3.2 "Per-stock capacity worst-basket," and §5.4 "Unwind horizon placeholder table" with numbers from real-data backtest.
**Why:** These are the three highest-leverage LP-facing numbers in the whole doc set and they are currently explicitly "To Populate." Blocks any investor conversation and any serious capacity-vs-fee discussion.
**How to apply:** After TODO-11 completes (real-data backtest), compute participation distribution from backtest order sizes / ADV. Worst-basket = bottom-decile ADV scenario. Unwind horizon = target-exit at 5% participation.
**Depends on:** TODO-11 (real-data backtest).

### TODO-22: Plain-English Executive Summary for CRO/CCO
**What:** Rewrite `NYSE_ALPHA_ONE_PAGER.md` (or add `docs/EXECUTIVE_SUMMARY_NONQUANT.md`) in CRO/CCO vocabulary: no IC/IC_IR/Romano-Wolf jargon; describe strategy, risk controls, kill switches, regulatory posture in plain English. Target audience: someone who must defend the program in a regulatory exam but is not a quant.
**Why:** Regulatory defense and internal governance often route through non-quant stakeholders. A doc written for a Chief Compliance Officer does not match a doc written for a quant colleague. Every serious firm has both.
**How to apply:** 2-page cap. Structure: What we do (1 paragraph), Who benefits (1 paragraph), How we control risk (5 bullets), What would cause us to halt (5 bullets), How we prove it works (3 bullets), Who owns what (table).
**Depends on:** Nothing. ~2 hr.

## Post-ivol_20d FAIL (2026-04-18)

> Added after the first real-data factor screen (ivol_20d) falsified the TWSE prior.
> See `docs/INDEPENDENT_VALIDATION_DRAFT.md` §4 and `docs/OUTCOME_VS_FORECAST.md`.

### TODO-23: Regime-Conditional IVOL Variant — EVIDENCE GATHERED 2026-04-18, DECISION DEFERRED
**What:** Evaluate a regime-conditional ivol_20d variant. Original framing (2026-04-17): trade IVOL only in bull regimes, hoping to recover a pre-2020 premium.
**Evidence from 2026-04-18 investigation** (`results/investigations/ivol_regime_2026-04-18.json`, research log event `ivol_20d_regime_stratified_ic`, chain entry hash `cfbf5e61...`):
- Pre-2020 IC = -0.0071; post-2020 IC = -0.0087. **The pre/post-2020 structural break hypothesis is not supported.**
- Bull-regime IC (SMA-200 on cap-weighted market) = -0.0010 (n=296, 51.0% positive). **Near zero — no tradeable bull-only variant.**
- Bear-regime IC = -0.0342 (n=104, 47.1% positive). **Strong anti-signal, tradeable only with INVERTED sign** (long high-IVOL in drawdowns). That is a short-volatility / crisis-exposure factor, not an IVOL-anomaly factor — different risk profile, different friction hypothesis.
- Year-level dispersion: 2019-2021 positive, 2016-2018 + 2022-2023 strongly negative. 4pp swing year-over-year.
**Why this changes the decision:** The original TODO-23 hypothesis ("bull-regime IVOL recovers the premium") does not survive the evidence. What the data actually supports is an inverted-sign bear-regime variant — a *different factor* with a *different name and theory*. Conflating the two and calling it "ivol_20d × SMA200" would be retroactive narrative fitting (AP-6 violation even though no code has been touched).
**What to do instead:**
1. **Do nothing on regime-conditional ivol until fundamentals screen first.** Run piotroski, earnings_surprise, accruals, profitability through G0-G5. If the ensemble clears Sharpe ≥ 0.5 without any ivol variant, regime-ivol is moot.
2. **If fundamentals also underperform expectations, revisit.** At that point, construct *one* pre-registered variant with an explicit friction hypothesis distinct from plain IVOL. Candidate: "short-volatility in drawdowns" (bear-only, inverted sign). Pre-register forecast in `results/research_log.jsonl` and `docs/OUTCOME_VS_FORECAST.md` BEFORE the screen, as a separate factor ID.
3. **Do NOT build bull-only IVOL.** The data shows bull-regime IC ≈ 0, so the variant would have no premium. Building it anyway would be curve-fitting to a single non-tradeable statistic.
**Risk of overfitting:** Still high. With 8 years of data and 3 regime definitions already examined, any further conditioning is implicitly mined. One variant, pre-registered, one screen, one verdict — OR shelve the factor family.
**Depends on:** TODO-3 (EDGAR + FINRA adapters) to enable fundamental factor screening before revisiting this decision.

### TODO-24: Run high_52w and momentum_2_12 Screens Next
**What:** Run `scripts/screen_factor.py --factor high_52w` and `scripts/screen_factor.py --factor momentum_2_12` on the populated `research.duckdb` before making any ensemble composition decisions.
**Why:** These two are price-only, immediately runnable, and represent the Tier 1 and Tier 2 priors. Three real-data data points (ivol, high_52w, momentum) are the minimum to distinguish "the framework is fine, ivol just doesn't transfer" from "our backtest methodology has a systemic problem." Don't generalize from n=1.
**How to apply:** Run both screens. Log forecasts to research log BEFORE running (use `scripts/append_research_log.py`). Update `docs/OUTCOME_VS_FORECAST.md` after each run. If both also fail, escalate and investigate methodology (label timing, purge gap, universe survivorship bias) before screening more factors.
**Depends on:** Nothing. Estimated 1 hr per factor.

### TODO-25: Outcome Tracker Integration with Live Database
**What:** Extend `scripts/generate_outcome_tracker.py` to read per-position forecast/outcome pairs from `live.duckdb` once paper trading begins. Schema: each weekly rebalance emits `forecast_return_5d` (Ridge-combined score × OOS stdev) per position; reconciliation writes `realized_return_5d` five days later.
**Why:** Pre-live tracker only covers factor-level predictions. The real calibration test happens at position level over hundreds of weekly predictions. Calibration at that scale is what distinguishes a researcher from an operator.
**How to apply:** Wait until `live.duckdb` schema is finalized by nautilus_bridge reconciliation (Phase 2-3). Add `--mode live` path to the generator. Emit per-position rows with calibration HIT/MISS based on sign agreement.
**Depends on:** `nautilus_bridge.py` reconciliation (Phase 2), paper trading start (Phase 5).

### TODO-26: Pre-commit Hook for Research Log Verification
**What:** Add `scripts/verify_research_log.py` to `.pre-commit-config.yaml` so any commit that silently clobbers the research log chain fails locally.
**Why:** The hash chain is only enforceable if verification runs automatically. Without a hook, the only check happens when a human remembers to run verify — which will not happen reliably under time pressure.
**How to apply:** Add a local-repo hook entry calling `python3 scripts/verify_research_log.py`. Non-zero exit aborts the commit. Also add to CI pipeline (TODO-6) as a required check.
**Depends on:** TODO-6 (CI/CD) for CI integration; pre-commit framework installed.

### TODO-27: External Timestamping of Research Chain Tip
**What:** Every ~50 research-log entries (or weekly, whichever comes first), publish the current chain tip hash externally — git tag (`research-chain-YYYYMMDD`), OpenTimestamps calendar entry, or email to a trusted third party.
**Why:** The hash chain defends against silent edits to history, but an attacker with write access can still re-chain the entire file from scratch. External timestamping closes that gap cheaply. Required before the chain can be cited in LP / regulatory contexts.
**How to apply:** Wrap in a script: `scripts/timestamp_research_chain.sh`. Initially: git tag. Later: add OpenTimestamps (`ots stamp`) for cryptographic third-party witness. Run manually for first 3 months, then CI.
**Depends on:** `scripts/verify_research_log.py` (shipped 2026-04-18), git.

### TODO-28: Broader-Research MCP Tooling (Perplexity / Web Search)
**What:** Wire a research-class MCP (Perplexity, Brave Search, or equivalent) into the Claude Code environment so the documentation / validation workflow can cite current external literature without the operator having to context-switch to a browser.
**Why:** The `/sparc:documenter` review on 2026-04-18 asked for Perplexity-driven analysis of institutional LP documentation standards (AIMA 2025 DDQ, ILPA DDQ v1.2, SR 11-7 interpretations, FMSB 2025). Without a live search tool, the doc drafter relies on training-cutoff knowledge and cannot verify that cited standards are current. This gap is not load-bearing for pre-live research but is load-bearing for any LP-facing document (DDQ responses, quarterly letters, validation reports).
**How to apply:** (1) Add a search-class MCP server to `~/.claude/settings.json`. Perplexity API requires a key; free tier is usable for document research. (2) Document allowed queries in a new `docs/EXTERNAL_RESEARCH_POLICY.md` — specifically, what can be searched (public standards, academic papers) vs what cannot (queries that might leak the strategy). (3) Re-run `/sparc:documenter` with the MCP active and capture the reviewer's second-pass findings in an amendment to `docs/REVIEW_CHECKLIST.md`.
**Depends on:** Nothing technical. Operator decision on which search MCP to adopt + API-key procurement.

### TODO-29: Quarterly Calibration-Curve Figure
**What:** At n ≥ 10 resolved forecasts in `OUTCOME_VS_FORECAST.md`, auto-generate a rolling Brier-score curve and save as `docs/figures/calibration_curve.png`.
**Why:** `CALIBRATION_TRACKER.md` (shipped 2026-04-18) commits to this artifact but cannot produce it at n = 7. Once the Tier-3 screens and regime variants land, sample size clears the threshold. Figure is a direct LP-facing artifact.
**How to apply:** Extend `scripts/generate_outcome_tracker.py` with a `--figure` flag. Use matplotlib. 4-forecast rolling window; annotate no-skill baseline at 0.56 and perfect-forecaster baseline at 0.0. Commit the PNG under `docs/figures/`.
**Depends on:** At least 4 additional resolved forecasts (Tier-3 factors or regime variants), `scripts/generate_outcome_tracker.py` baseline implementation.
