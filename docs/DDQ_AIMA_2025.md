# Due Diligence Questionnaire (AIMA 2025 Template)

**Fund / Strategy:** NYSE Algorithmic Trading System (ATS) — Cross-sectional equity factor
**Manager:** [Operator Name] (solo researcher, pre-operational)
**As-of date:** 2026-04-18
**Status:** DRAFT — answers sourced from codebase + existing docs as of this date; "TBD"
marks items that operator must complete before first LP conversation.

---

## Preamble — How to read this document

This DDQ follows the AIMA 2025 Illustrative Questionnaire layout. For each question:

- **Answered** — Response drawn directly from code, configs, or existing governance docs.
  A cross-reference to the authoritative source is provided so a reviewer can verify.
- **TBD** — Operator has not yet produced the artifact (e.g., no signed compliance manual,
  no incorporated entity). These are blockers for live LP fundraising, not for paper trading.
- **N/A** — Question does not apply at current scale (pre-operational, solo, no outside capital).

Answers reflect the **as-built state on 2026-04-18**. Material changes require updating this
DDQ and re-circulating to LPs under any subscription agreement side letter provision.

---

## Section 1 — Firm Information

| # | Question | Answer |
|---|----------|--------|
| 1.1 | Full legal name of the management entity | TBD — operator has not yet incorporated. Intended: Delaware LLC. |
| 1.2 | Date and jurisdiction of formation | TBD |
| 1.3 | Registered office address | TBD |
| 1.4 | Principal place of business | Home office (TBD address); no separate commercial lease at this stage. |
| 1.5 | Does the manager have offices in multiple jurisdictions? | No. |
| 1.6 | Ownership structure of the management company | TBD — 100% founder-held at formation is the intent. |
| 1.7 | Key principals (names, roles, tenure, prior firms) | [Operator] — sole researcher/operator. Prior: TWSE cross-sectional project (63 phases, 2025, Sharpe 1.186 gross on paper). |
| 1.8 | Total number of employees | 1 (sole proprietor at this stage). |
| 1.9 | Total number of investment professionals | 1. |
| 1.10 | Is the manager registered with any regulator? | No. Registration threshold analysis is in `docs/SEC_FINRA_COMPLIANCE.md`. Operator is below SEC RIA threshold ($100M AUM); state registration may be required above state thresholds. |
| 1.11 | Regulatory registration number(s) | N/A — see 1.10. |
| 1.12 | Prior disciplinary history of the firm or principals | None. Operator will complete FINRA BrokerCheck / IAPD searches before LP conversations. |
| 1.13 | Material litigation outstanding | None. |
| 1.14 | Affiliates and related parties | None. |

**Source references:** `docs/SEC_FINRA_COMPLIANCE.md` for registration analysis.

---

## Section 2 — Investment Strategy

| # | Question | Answer |
|---|----------|--------|
| 2.1 | Strategy name | NYSE Cross-Sectional Equity Factor |
| 2.2 | Strategy classification | Quantitative equity long-only (initial); long/short is a roadmap item (see `docs/TODOS.md`). |
| 2.3 | Asset classes traded | US listed equities (S&P 500 universe at inception). |
| 2.4 | Geographic focus | United States (NYSE + Nasdaq listings in S&P 500). |
| 2.5 | Target gross exposure | 100% (equal-weighted top-N in bull regime, 40% in bear per `config/strategy_params.yaml:regime.bear_exposure`). |
| 2.6 | Target net exposure | Long-only: net = gross. Net falls to 40% under SMA-200 bear regime. |
| 2.7 | Expected annual return target (gross) | 18-28% CAGR — see `docs/NYSE_ALPHA_TECHNICAL_BRIEF.md`. Targets are plan-stage; no live track record exists. |
| 2.8 | Expected annual volatility target | ~15% annualized portfolio volatility (half-Kelly of 0.30 Sharpe). `config/strategy_params.yaml:volatility_target.annual_pct`. |
| 2.9 | Target Sharpe ratio (net of costs) | 0.8 to 1.2 after costs. Plan-stage; see §4 Outcomes in `docs/INDEPENDENT_VALIDATION_DRAFT.md`. |
| 2.10 | Target max drawdown | -15% to -25% with regime overlay engaged. |
| 2.11 | Target Sortino ratio | Not set as primary; Sharpe is primary per `metrics.py`. |
| 2.12 | Benchmark | SPY (S&P 500 cap-weighted) — chosen deliberately despite structural disadvantage for equal-weighted strategies. Analysis of equal-weight vs cap-weight performance gap 2024-2025 is in TODO-9 and the "SPY underperformance investigation" section of `docs/NYSE_ALPHA_RESEARCH_RECORD.md`. |
| 2.13 | Why does this strategy exist? (friction hypothesis) | Multiple cross-sectional anomalies persist because of retail lottery demand (IVOL), short-sale constraints, disposition effect (52-week high), post-earnings announcement drift, and accounting-quality mispricing. Each factor has a stated friction hypothesis documented in `src/nyse_core/features/*.py` and in the plan's Factor Priority List. |
| 2.14 | What is the strategy's edge? | Not a single-factor edge — the ensemble's Ridge-combined risk-adjusted return after gates and costs. Individual factor edges are small (expected IC 0.02-0.04); combination via Ridge + regime overlay is where the plan claims Sharpe > 0.8 comes from. |
| 2.15 | How does the strategy degrade or die? | Monitored via eight F1-F8 falsification triggers defined in `config/falsification_triggers.yaml` and frozen 2026-04-15. F1 (60-day rolling IC < 0.01 for 2 months) and F2 (core factor sign flips ≥3 in 2 months) are the primary death signals. |
| 2.16 | Capacity estimate | ~$500M-$1B gross at weekly rebalance with 5% ADV participation limit. Justification: S&P 500 universe mean ADV ~$200M; 5% of $200M × 20 positions × weekly turnover fits well below impact threshold. See `docs/FRAMEWORK_AND_PIPELINE.md`. |
| 2.17 | Will capacity be soft-closed at any AUM level? | Yes — intended soft close at $500M until shadow-to-live impact measurement confirms linear slippage. |
| 2.18 | Leverage policy | No leverage in the long-only strategy. Long/short variant (roadmap) would run at 150%/50% gross with beta-neutral targeting. |

**Source references:** `config/strategy_params.yaml`, `config/falsification_triggers.yaml`, `docs/NYSE_ALPHA_TECHNICAL_BRIEF.md`, `docs/FRAMEWORK_AND_PIPELINE.md`.

---

## Section 3 — Investment Process

| # | Question | Answer |
|---|----------|--------|
| 3.1 | Describe the research process | Theory-first factor proposal → G0-G5 gate evaluation on 2016-2023 research period → ensemble backtest with PurgedWalkForwardCV → permutation test + Romano-Wolf correction → one-shot holdout on 2024-2025. Process is documented in `.claude/skills/alpha-research` workflow and in `docs/NYSE_ALPHA_RESEARCH_RECORD.md`. |
| 3.2 | How are factors selected? | Each factor must (a) have a stated friction hypothesis (Lesson_Learn Rule #7), (b) pass G0 (OOS Sharpe ≥ 0.30), G1 (permutation p < 0.05), G2 (IC mean ≥ 0.02), G3 (IC IR ≥ 0.50), G4 (MaxDD ≥ -0.30), G5 (marginal contribution to ensemble > 0). No greedy selection by standalone IC_IR (AP-2). |
| 3.3 | How are factors combined? | Default: Ridge regression with α=1.0 on rank-percentile normalized features [0,1]. GBM and Neural alternatives are gated — they must beat Ridge by ≥0.1 OOS Sharpe AND have overfit ratio < 3.0 to be adopted. See `src/nyse_core/signal_combination.py` and `src/nyse_core/models/`. |
| 3.4 | How is the universe defined? | S&P 500 constituents. PiT reconstitution is a Phase 0 deliverable in `src/nyse_core/universe.py`. Current production download uses `config/sp500_current.csv` (current-list-only) — this introduces survivorship bias and is logged in `docs/NYSE_ALPHA_RESEARCH_RECORD.md` as a known limitation. |
| 3.5 | How is position sizing determined? | Equal-weight top-N after factor combination. N=20 is in `config/strategy_params.yaml:allocator.top_n`. Rationale for equal weight: per TWSE Lesson_Learn, signal-weighting failed when alpha surface was flat. |
| 3.6 | Sell buffer / position inertia | Sell buffer = 1.5 (sell only if rank drops below top-30 after being in top-20). Saved ~1,644 bps / +0.040 Sharpe on TWSE per Phase 63 postmortem. |
| 3.7 | Rebalance frequency | Weekly (Friday signal, Monday open execution). NYSE 15-20 bps costs enable weekly; TWSE was monthly due to higher costs. |
| 3.8 | How are transaction costs modeled? | Dynamic spread ∝ 1/√(ADV), base 10 bps, Monday multiplier 1.3, earnings-week multiplier 1.5. `src/nyse_core/cost_model.py`. Commission flat $0.005/share. |
| 3.9 | How is label construction done? | 5-day forward returns from Monday open (T+1) to Friday close (T+5) — i.e., returns that a strategy executing on Monday open AFTER Friday close signal would actually capture. 20-day secondary target for robustness. `scripts/screen_factor.py:_build_forward_returns`. |
| 3.10 | How is look-ahead bias prevented? | PurgedWalkForwardCV with 5-day purge gap (auto-adjusts to 20d for longer horizon); embargo of 5 days after each test fold. PiT publication lags enforced: OHLCV T+0, EDGAR T+45, FINRA T+11. See `src/nyse_core/pit.py` and `src/nyse_core/cv.py`. |
| 3.11 | Hyperparameter tuning procedure | No tuning on the holdout period. Parameter sensitivity is checked via ±20% perturbation on research period; Sharpe must stay within ±20% across perturbations. AP-7 limit: max 5 parameters optimized simultaneously with <60 monthly observations. |
| 3.12 | Model retraining cadence | Weekly retrain on expanding window (minimum 2 years). Drift detection on rolling 60-day IC triggers ad-hoc retrain with human approval gate. `src/nyse_core/drift.py` (roadmap). |
| 3.13 | Forward / Decision-to-execution lag | Signal generated Friday EOD; orders submitted Monday open via TWAP over 30 minutes. `config/strategy_params.yaml:execution`. |

**Source references:** `.claude/skills/alpha-research`, `src/nyse_core/*`, `config/strategy_params.yaml`, `config/gates.yaml`, `docs/NYSE_ALPHA_RESEARCH_RECORD.md`.

---

## Section 4 — Risk Management

| # | Question | Answer |
|---|----------|--------|
| 4.1 | Is there an independent risk function? | No — solo operator. This is disclosed as a material limitation in `docs/MODEL_VALIDATION.md` §1 and `docs/INDEPENDENT_VALIDATION_DRAFT.md` §1. Third-party validation is a precondition for live capital. |
| 4.2 | Primary risk framework | SR 11-7-inspired: conceptual soundness → implementation verification → outcomes analysis → ongoing monitoring. |
| 4.3 | Portfolio-level risk limits | Max single position 10%, max sector 30%, ex-ante beta to SPY in [0.5, 1.5], daily loss limit -3% (halt new orders), earnings-event position cap 5% if reporting within 2 days, manual kill switch via config flag. `src/nyse_core/risk.py` (Phase 1). |
| 4.4 | Pre-trade risk checks | Eight risk layers applied in order: regime overlay → position caps → sector caps → beta cap → daily loss limit → earnings cap → kill switch → position inertia. See `docs/FRAMEWORK_AND_PIPELINE.md` "Risk Management" section. |
| 4.5 | Stress testing | Block bootstrap CI (63-day blocks, 10,000 reps) on OOS returns. Regime tests: 2020 COVID drawdown, 2022 rate-shock, 2018 Q4. See `docs/NYSE_ALPHA_TECHNICAL_BRIEF.md`. |
| 4.6 | Concentration limits | No single stock > 10% of portfolio NAV. No GICS sector > 30%. Enforced in `src/nyse_core/risk.py`. Property test in `tests/property/test_position_caps_invariant.py`. |
| 4.7 | Liquidity management | Universe filter: min price $5, min 20-day ADV $500K. Per-order max 5% of ADV. |
| 4.8 | Drawdown management | Regime overlay (SMA-200 on SPY): 100% exposure in bull, 40% in bear. F3 trigger at -25% MaxDD halts to paper mode. |
| 4.9 | Counterparty exposure | Single prime brokerage relationship at inception (TBD — Interactive Brokers is intended). No OTC derivative exposure. |
| 4.10 | VaR methodology | Not primary — Sharpe, MaxDD, block-bootstrap CI are primary. 95% historical VaR can be computed from `metrics.py` outputs on request. |
| 4.11 | How is model risk governed? | Per `docs/MODEL_VALIDATION.md`. Model inventory maintained; each model has owner, validator, tier, retrain cadence, last review date. G0-G5 gate re-run before any production model update. |
| 4.12 | Scenario analysis | Plan includes forward-looking scenarios: IVOL regime flip (already observed 2016-2023), momentum crash, short-squeeze (Q1 2021 meme stocks), earnings anomaly decay. No live scenario dashboard yet. |

**Source references:** `docs/MODEL_VALIDATION.md`, `docs/INDEPENDENT_VALIDATION_DRAFT.md`, `src/nyse_core/risk.py`, `config/falsification_triggers.yaml`.

---

## Section 5 — Trading & Execution

| # | Question | Answer |
|---|----------|--------|
| 5.1 | Execution venue(s) | NYSE / Nasdaq via the prime broker's smart order router. |
| 5.2 | Execution algorithm | TWAP over 30 minutes post-open on rebalance day. `config/strategy_params.yaml:execution.algorithm`. |
| 5.3 | Order types used | Limit orders with participation cap; no market orders. |
| 5.4 | Max participation rate | 5% of ADV per order. |
| 5.5 | Slippage assumption in backtest | 4-10 bps per side, dynamic (1/√ADV). Monday/earnings multipliers. Validated against paper trade before live. |
| 5.6 | Fill rate target | > 95% for production graduation (one of seven Shadow-to-Live graduation criteria). |
| 5.7 | Execution engine | NautilusTrader (open-source event-driven platform). `src/nyse_ats/execution/nautilus_bridge.py` — planned for Phase 2. |
| 5.8 | Position source of truth | NautilusTrader post-fill state → `live.duckdb` via nautilus_bridge.reconcile. Pipeline reads actual positions before computing next TradePlan. |
| 5.9 | Handling of partial fills | Reconciliation writes actual fill to live.duckdb; next rebalance computes delta from actual, not target. |
| 5.10 | Handling of corporate actions | Event-sourced append-only corporate action log. Pre-submit check cancels affected orders if CA detected between signal and execution; regenerates TradePlan with adjusted prices. `src/nyse_ats/storage/corporate_action_log.py`. |
| 5.11 | Trade reporting frequency to LPs | TBD — monthly NAV + trade attribution intended. |
| 5.12 | Best execution policy | TBD — must be written before live trading. Reference: FINRA Rule 5310. |

**Source references:** `config/strategy_params.yaml`, `src/nyse_ats/execution/` (planned), `docs/FRAMEWORK_AND_PIPELINE.md`.

---

## Section 6 — Compliance & Regulation

| # | Question | Answer |
|---|----------|--------|
| 6.1 | Compliance officer | Operator (combined role) — a material weakness. Pre-live: engage fractional compliance consultant or designate external CCO. |
| 6.2 | Compliance manual | TBD. Draft blocked on entity formation and registration decision. |
| 6.3 | Code of ethics | TBD — model on CFA Institute Code of Ethics and Standards. |
| 6.4 | Personal trading policy | TBD — intended pre-clearance of all personal equity trades; 30-day holding period; no trading in strategy universe. |
| 6.5 | Insider information policy | TBD. Standard "no trading on material non-public information" policy; barrier from any day-job access to MNPI. |
| 6.6 | Material non-public information safeguards | All data sources are public-market (FinMind OHLCV, EDGAR filings, FINRA short interest). No alternative-data sources with potential MNPI content are currently subscribed. |
| 6.7 | AML / KYC program | N/A — no outside capital yet. Pre-launch: adopt standard AML program or delegate to fund administrator. |
| 6.8 | Anti-bribery / sanctions screening | TBD — standard OFAC screening via fund administrator if established. |
| 6.9 | Marketing materials review | TBD — SEC Marketing Rule compliance review before any track-record distribution. |
| 6.10 | Trade allocation policy | N/A — single-account strategy at inception. |
| 6.11 | Soft dollar policy | None — no soft-dollar arrangements. |
| 6.12 | Trade error policy | TBD. Intended: all errors logged to `live.duckdb`; client is made whole; errors > $1K reported to LP. |
| 6.13 | Regulatory examinations (historical) | None — pre-operational. |
| 6.14 | Whistleblower program | TBD. |
| 6.15 | Political contributions / pay-to-play (Rule 206(4)-5) | N/A if not registered as RIA; policy TBD. |

**Source references:** `docs/SEC_FINRA_COMPLIANCE.md` for current analysis of obligations.

---

## Section 7 — Operations

| # | Question | Answer |
|---|----------|--------|
| 7.1 | Fund administrator | TBD. Candidates for sub-$100M launch: NAV Consulting, SS&C, Apex. |
| 7.2 | Auditor | TBD. Big 4 or specialist audit (Anchin, PKF O'Connor Davies) pending entity formation. |
| 7.3 | Prime broker | TBD — Interactive Brokers is the intended first PB given per-share pricing and API quality. |
| 7.4 | Custodian | Same as PB initially; multi-custodial structure post-scale. |
| 7.5 | Legal counsel | TBD — fund formation counsel (Seward & Kissel, Schulte Roth, Akin, Lowenstein) pending entity decision. |
| 7.6 | Tax advisor | TBD. |
| 7.7 | NAV calculation frequency | Monthly at inception; daily post-scale. Administrator-calculated. |
| 7.8 | NAV verification | Independent administrator; shadow NAV by operator for reconciliation. |
| 7.9 | Cash management | Cash swept to custodian overnight; no separate treasury program at inception. |
| 7.10 | Reconciliation process | Daily: broker statement vs live.duckdb position table. Breaks > $1 investigated within 24 hours. |
| 7.11 | Valuation of hard-to-value assets | N/A — exchange-traded equities only, closing-price valuation. |
| 7.12 | Segregation of duties | Not currently achievable (solo operator). Mitigations: automated reconciliation, broker-statement comparison, hash-chained research log. |

**Source references:** `docs/AUDIT_TRAIL.md`, `docs/RESEARCH_RECORD_INTEGRITY.md` (pending).

---

## Section 8 — Technology & Cybersecurity

| # | Question | Answer |
|---|----------|--------|
| 8.1 | Describe the technology stack | Python 3.11+, pandas/numpy/scipy/sklearn, DuckDB for storage, NautilusTrader for execution, Streamlit for dashboard. Runs on Linux. Editable install via `pyproject.toml`. |
| 8.2 | Where is code hosted? | Git repository (local + intended remote on GitHub private). Research period: 2016-01-01 to 2023-12-31. |
| 8.3 | Version control | Git; feature-branch workflow; changelog + VERSION file; structured release via `/ship` skill. |
| 8.4 | CI / CD | GitHub Actions pipeline: pytest + mypy + ruff + secret scan. Phase 1 deliverable. |
| 8.5 | Code review | Solo operator; compensating controls: static analysis, plan-eng-review skill before major changes, cross-AI review (Codex) before live capital. |
| 8.6 | Test coverage | Target: 90%+ path coverage on `nyse_core` pure-logic modules. Current: TBD — see `docs/TODOS.md` for coverage gaps. |
| 8.7 | Data centers / cloud providers | Local workstation at inception. Migration to cloud (AWS / GCP) post-Phase 5. |
| 8.8 | Backup policy | Daily snapshots of `research.duckdb` and `live.duckdb` to external storage. TBD: offsite replication. |
| 8.9 | Disaster recovery RTO / RPO | Per `docs/DISASTER_RECOVERY.md`: RPO 24 hours, RTO 4 hours for pre-live; targets tighten post-go-live. |
| 8.10 | Penetration testing | TBD — annual third-party pentest before live capital. |
| 8.11 | Cybersecurity framework | NIST CSF-aligned at small scale. Basic controls: disk encryption, SSH key auth, 2FA on broker and critical accounts, secrets in environment variables (no secrets in YAML — enforced via CI pre-commit hook). |
| 8.12 | How are API keys managed? | Environment variables only. `FINMIND_API_TOKEN` can be read from `~/.config/finmind/token`. Never stored in YAML or git. Adapter error messages scrub token from query strings (see feedback memory `feedback_secret_leakage.md`). |
| 8.13 | Multi-factor authentication | Required on broker, GitHub, email, cloud provider accounts. |
| 8.14 | Endpoint security | Linux workstation with automatic updates, disk encryption, firewall enabled. |
| 8.15 | Incident response plan | TBD — formal playbook required pre-live. |
| 8.16 | Vendor security review | TBD for each new data / infra vendor pre-engagement. |
| 8.17 | Employee security training | N/A at scale of 1; self-review on OWASP top-10, phishing basics, social engineering. |

**Source references:** `docs/FRAMEWORK_AND_PIPELINE.md`, `docs/DISASTER_RECOVERY.md`, feedback memory `feedback_secret_leakage.md`.

---

## Section 9 — Business Continuity / Disaster Recovery

| # | Question | Answer |
|---|----------|--------|
| 9.1 | Is there a written BCP? | `docs/DISASTER_RECOVERY.md` covers the technical DR posture. BCP-as-operations document is TBD. |
| 9.2 | When was the BCP last tested? | TBD — quarterly failover test is planned pre-live. |
| 9.3 | Key-person risk | Extreme — one operator. Documented in `docs/MODEL_VALIDATION.md` §1 as a material limitation. Mitigations: hash-chained research log, full-text config snapshots, runbook-style documentation. |
| 9.4 | Succession plan | TBD. Required before outside capital. |
| 9.5 | Pandemic / remote-work readiness | Native remote — no office dependency. |
| 9.6 | Critical-vendor failure plan | `docs/DISASTER_RECOVERY.md` covers FinMind outage (fallback to yfinance snapshot + halt), EDGAR outage (fundamental features go NaN, fall back to price-only subset), broker outage (kill switch, manual liquidation plan). |
| 9.7 | Data-loss recovery | Daily research.duckdb snapshots to external encrypted drive; live.duckdb WAL-mode with frequent checkpoints. |
| 9.8 | Communication plan with LPs during incident | TBD. |

**Source references:** `docs/DISASTER_RECOVERY.md`.

---

## Section 10 — Performance & Reporting

| # | Question | Answer |
|---|----------|--------|
| 10.1 | Performance calculation methodology | Time-weighted return per GIPS-aligned definition; administrator-independent at first NAV. |
| 10.2 | Benchmark for reporting | SPY (S&P 500 total return). Secondary: RSP (equal-weight S&P 500) — more apt comparator given strategy is equal-weighted. TODO-9 tracks formal RSP adoption. |
| 10.3 | Performance track record length | Zero live. Research-period (2016-2023) plan-stage metrics are in `docs/NYSE_ALPHA_TECHNICAL_BRIEF.md`. All metrics are hypothetical until paper/live trading begins. |
| 10.4 | Hypothetical vs actual labeling | All backtest / research metrics are labeled HYPOTHETICAL per SEC Marketing Rule. No results from this strategy have been computed on real capital. |
| 10.5 | Attribution methodology | Per-factor + per-sector contribution via `src/nyse_core/attribution.py` (Phase 4 deliverable). |
| 10.6 | Reporting cadence | Monthly LP report: NAV, gross/net return, factor attribution, risk dashboard, F1-F8 trigger status. Weekly to internal team. |
| 10.7 | Independent verification of returns | Administrator-reported NAV at inception; annual audit. |
| 10.8 | GIPS compliance | Not claimed. GIPS verification can be pursued if composite becomes material. |
| 10.9 | Side letter provisions | TBD — MFN clause intended across all LPs. |

**Source references:** `docs/NYSE_ALPHA_TECHNICAL_BRIEF.md`, `docs/OUTCOME_VS_FORECAST.md` (pending), `src/nyse_core/metrics.py`.

---

## Section 11 — Fees & Terms

| # | Question | Answer |
|---|----------|--------|
| 11.1 | Management fee | TBD — conventional 1-2% on gross assets. |
| 11.2 | Performance fee | TBD — conventional 15-20% above high-water mark with crystallization annual. |
| 11.3 | High-water mark | TBD — yes, standard. |
| 11.4 | Hurdle rate | TBD — decide between soft/hard hurdle vs none. |
| 11.5 | Redemption frequency | TBD — monthly with 30-day notice is conventional for this strategy's liquidity. |
| 11.6 | Lock-up period | TBD — 12 months initial is conventional. |
| 11.7 | Gates | TBD — investor gate 25%, fund gate 15% conventional. |
| 11.8 | Side-pocket policy | N/A — liquid strategy. |
| 11.9 | Subscription frequency | TBD — monthly. |
| 11.10 | Minimum investment | TBD — $250K / $1M accredited / qualified-purchaser stratification. |
| 11.11 | Expenses charged to the fund | TBD — operating expenses (admin, audit, market data, compliance) typically capped at 10-25 bps/year. |

---

## Section 12 — Service Providers / Counterparties

| # | Question | Answer |
|---|----------|--------|
| 12.1 | Primary prime broker(s) | TBD — Interactive Brokers is the intended first PB. |
| 12.2 | Back-up prime broker | None at inception; added post-scale. |
| 12.3 | Administrator | TBD (see 7.1). |
| 12.4 | Auditor | TBD (see 7.2). |
| 12.5 | Legal counsel | TBD (see 7.5). |
| 12.6 | Market data vendors | FinMind (primary OHLCV, bulk + incremental), EDGAR via edgartools (fundamentals), FINRA (short interest). See `docs/NYSE_ALPHA_RESEARCH_RECORD.md` and `config/data_sources.yaml`. |
| 12.7 | Due diligence on key vendors | Operator reviewed FinMind SLA, rate limits, and token-security posture. FinMind token redaction implemented in adapter per `feedback_secret_leakage.md`. |
| 12.8 | Vendor concentration | High (FinMind is single OHLCV source). Mitigation: adapter protocol allows swap to yfinance or Polygon with minimal code change. |

---

## Section 13 — ESG / Sustainability

| # | Question | Answer |
|---|----------|--------|
| 13.1 | ESG integration in investment process | None at present — factors are quantitative / fundamental / price-based. No ESG screens. |
| 13.2 | Does the strategy consider climate risk? | Not explicitly. Climate-tilted equity factor ("green - brown") is a roadmap research idea, not in the current plan. |
| 13.3 | Voting policy | TBD — strategy is short holding period (weekly) so proxy voting is rare. Default: abstain unless material and holding > 1 week. |
| 13.4 | UN PRI signatory | No. |
| 13.5 | SFDR classification | N/A — US-domiciled at inception. |
| 13.6 | Diversity / inclusion at manager | N/A at scale of 1. Policy TBD for hiring. |

---

## Section 14 — Conflicts of Interest

| # | Question | Answer |
|---|----------|--------|
| 14.1 | Describe all material conflicts | Principal trading: operator has personal brokerage. Mitigation: personal trades pre-cleared; no trading in strategy universe during lock-up. |
| 14.2 | Related-party transactions | None. |
| 14.3 | Proprietary capital of the GP invested alongside LP | TBD — target GP skin-in-the-game of ≥1% of fund NAV. |
| 14.4 | Outside business interests | TBD — operator to disclose prior to any LP engagement. |
| 14.5 | Gifts / entertainment policy | TBD. |

---

## Section 15 — Track Record & Live Evidence

| # | Question | Answer |
|---|----------|--------|
| 15.1 | Has this strategy been traded live? | No. Pre-paper-trading stage. |
| 15.2 | Prior-strategy live track record of operator | TWSE cross-sectional project (2025, 63 phases): paper Sharpe 1.186 gross. No LP capital was managed. |
| 15.3 | Live / paper start date for this strategy | TBD — paper target Q3 2026 if factor screening succeeds. |
| 15.4 | Current outcomes vs forecast | `docs/OUTCOME_VS_FORECAST.md` tracks. As of 2026-04-18: first real-data factor screen (ivol_20d) FAILED G0-G4 on 2016-2023, contradicting the "likely PASS" prior from TWSE. See also `docs/INDEPENDENT_VALIDATION_DRAFT.md` §4. |
| 15.5 | Any material changes to strategy since research inception | Research in flight; no strategy has been committed to live. Plan drift is logged in `docs/NYSE_ALPHA_RESEARCH_RECORD.md`. |
| 15.6 | Independent validation performed | No third-party validation. Internal draft is `docs/INDEPENDENT_VALIDATION_DRAFT.md` — labeled DRAFT / not approved, not a substitute. |

---

## Appendix A — Cross-Reference Index

| DDQ Section | Authoritative source document(s) |
|-------------|----------------------------------|
| 1 Firm | `docs/SEC_FINRA_COMPLIANCE.md` |
| 2 Strategy | `docs/NYSE_ALPHA_ONE_PAGER.md`, `docs/NYSE_ALPHA_TECHNICAL_BRIEF.md`, `config/strategy_params.yaml` |
| 3 Process | `docs/NYSE_ALPHA_RESEARCH_RECORD.md`, `.claude/skills/alpha-research`, `src/nyse_core/` |
| 4 Risk | `docs/MODEL_VALIDATION.md`, `config/falsification_triggers.yaml`, `src/nyse_core/risk.py` |
| 5 Trading | `docs/FRAMEWORK_AND_PIPELINE.md`, `src/nyse_ats/execution/` |
| 6 Compliance | `docs/SEC_FINRA_COMPLIANCE.md` |
| 7 Ops | `docs/AUDIT_TRAIL.md`, `docs/RESEARCH_RECORD_INTEGRITY.md` |
| 8 Tech | `docs/FRAMEWORK_AND_PIPELINE.md`, `docs/DISASTER_RECOVERY.md` |
| 9 BCP/DR | `docs/DISASTER_RECOVERY.md` |
| 10 Performance | `docs/NYSE_ALPHA_TECHNICAL_BRIEF.md`, `docs/OUTCOME_VS_FORECAST.md` |
| 15 Track Record | `docs/INDEPENDENT_VALIDATION_DRAFT.md`, `docs/OUTCOME_VS_FORECAST.md`, `results/research_log.jsonl` |

---

## Appendix B — AIMA 2025 Questions Not Yet Addressed

AIMA 2025 has approximately 150 questions across these sections. This draft covers ~120. The
following are deferred — they become relevant after the operator completes entity formation,
vendor selection, and the first paper-trade cycle:

- Detailed trade-error reconciliation workflow
- Complex cross-border tax structuring (single-jurisdiction at inception)
- Derivatives clearing (N/A until long/short variant ships)
- Collateral management (N/A until leveraged strategy ships)
- Bespoke side-letter content (TBD per first-LP negotiation)
- Business-interruption insurance specifics
- E&O / D&O insurance specifics

---

## Change Log

| Version | Date | Change |
|---------|------|--------|
| 0.1 | 2026-04-18 | Initial draft following AIMA 2025 template. Answered where codebase/docs support; TBD elsewhere. |

---

**Document owner:** Operator
**Review cadence:** Annual, or upon material change to strategy, service providers, or regulatory status.
**Related documents:** `docs/INDEPENDENT_VALIDATION_DRAFT.md`, `docs/MODEL_VALIDATION.md`, `docs/NYSE_ALPHA_TECHNICAL_BRIEF.md`, `docs/NYSE_ALPHA_RESEARCH_RECORD.md`, `docs/FRAMEWORK_AND_PIPELINE.md`, `docs/OUTCOME_VS_FORECAST.md`, `docs/RESEARCH_RECORD_INTEGRITY.md`.
