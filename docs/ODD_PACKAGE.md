# Operational Due Diligence (ODD) Package

**Version 0.1 | 2026-04-18 | Pre-Paper-Trade**
**Audience:** LP operational due diligence teams, fund administrators, prime-brokerage credit
**Scope:** Operations only. Investment due diligence is in `docs/DDQ_AIMA_2025.md`.

---

## How to read this document

ODD asks a different question than investment diligence: "Can this organization actually
run the strategy it claims, without losing the money for operational reasons?" LP experience
shows that ~70% of hedge-fund failures are operational (trade error, mis-reconciliation,
counterparty failure, cyber, BCP) rather than investment-driven.

This document is a **pre-live draft**. Sections marked [TBD-LIVE] require vendor selection
or entity formation that has not occurred. They are labeled honestly rather than invented.

---

## 1. Legal Entity and Regulatory Status

| # | Item | Answer |
|---|------|--------|
| 1.1 | Legal entity | [TBD-LIVE] Expected structure: Delaware LLC (GP) + Delaware LP (fund). No entity formed prior to first LP commitment. |
| 1.2 | Domicile | United States (Delaware) at inception. No offshore vehicle. |
| 1.3 | Regulatory registration | [TBD-LIVE] Below SEC RIA threshold at inception (<$100M AUM). Operator registers with SEC or state once assets cross threshold. |
| 1.4 | CFTC / NFA | Not registered. No derivatives trading in current strategy. |
| 1.5 | Tax status | Pass-through entity (LP). No PFIC concerns for US LPs. |
| 1.6 | AML / KYC program | [TBD-LIVE] To be contracted through fund administrator (see §3). |
| 1.7 | Compliance officer | Solo operator acts as CCO until first compliance hire or service provider. Disclosed as material limitation. |

---

## 2. Ownership and Governance

| # | Item | Answer |
|---|------|--------|
| 2.1 | Ownership of GP | 100% operator-owned at inception. |
| 2.2 | Board / advisory board | None at inception. [TBD-LIVE] Operator commits to forming a 3-person independent advisory board within 6 months of first external capital, per `docs/INDEPENDENT_VALIDATION_DRAFT.md` §1. |
| 2.3 | Key-person risk | Single key person (operator). Material risk. Mitigation: all research + configs + data in version-controlled repo with hash chain; any successor can resume within 1 week given codebase access. `docs/DISASTER_RECOVERY.md` documents handover. |
| 2.4 | Signing authority | Solo. Documented in `docs/GOVERNANCE.md` (to be written before first LP capital). |
| 2.5 | Conflicts policy | See `docs/DDQ_AIMA_2025.md` §14. Personal brokerage trades pre-cleared; no trading in strategy universe during rebalance windows. |
| 2.6 | Change control | Any change to strategy parameters (`config/strategy_params.yaml`), gates (`config/gates.yaml`), or falsification triggers (`config/falsification_triggers.yaml`) requires: (a) git commit, (b) research-log entry via `scripts/append_research_log.py`, (c) post-change verification via `scripts/verify_research_log.py`. Post-live, LP notification within 30 days of material change. |

---

## 3. Service Providers

At the time of this document, no third-party service agreements are executed. The table
below is the pre-live selection plan. Actual agreements are a precondition for paper-to-live
promotion per `config/deployment_ladder.yaml`.

| Role | Provider | Status | Selection criteria |
|------|----------|--------|--------------------|
| Prime brokerage | Interactive Brokers (intended) | [TBD-LIVE] | API stability, sub-pennies commission, margin rates, TWAP algo support, API rate limits compatible with weekly rebalance |
| Fund administrator | [TBD-LIVE] — candidates: NAV Consulting, SS&C, Opus Fund Services | Not contracted | NAV calc, investor reporting, AML/KYC, fee calculation |
| Auditor | [TBD-LIVE] — candidates: EY, KPMG, or tier-2 (Spicer Jeffries) | Not contracted | Financial statement audit annually; SOC-1 review of FA |
| Legal | [TBD-LIVE] — fund-formation counsel | Not engaged | Delaware fund formation, Reg D filings, side letters |
| Tax | [TBD-LIVE] | Not engaged | K-1 prep, entity returns |
| Data vendors | FinMind (OHLCV), SEC EDGAR (fundamentals, free), FINRA (short interest, free) | Research contracts active; no live data feeds yet | See `docs/DDQ_AIMA_2025.md` §12 |
| Cloud / infrastructure | Self-hosted Linux workstation for research; Phase 5+ paper/live TBD (Hetzner or AWS dedicated) | Research only | No multi-tenant SaaS holding position data pre-live |
| Compliance consultant | [TBD-LIVE] | Not engaged | SEC registration support, ongoing 15(a) compliance |
| E&O / D&O insurance | [TBD-LIVE] | Not bound | Minimum $1M E&O, $1M D&O before first LP capital |

**Rationale for the gap:** the operator explicitly defers vendor selection until research
produces a live-ready strategy. Contracting service providers before the strategy survives
holdout validation would be premature capex and vendor lock-in. This is disclosed as a
material known limitation.

---

## 4. Operations Lifecycle

### 4.1 Trade lifecycle

```
T-3 (Tue)    — Data refresh: FinMind OHLCV + EDGAR fundamentals + FINRA short interest
T-1 (Thu)    — Data quality check (scripts/validate_data.py); failures trigger F8 WARNING
T+0 (Fri EOD)— Compute factors → rank-percentile → Ridge combine → top-20 select
              → sell-buffer hysteresis → regime overlay → risk caps → TradePlan emitted
T+1 (Mon)    — TradePlan consumed by NautilusTrader; TWAP execution over first 30 minutes
              of regular session (09:30-10:00 ET); max 5% of 20-day ADV per order
T+1 EOD      — Reconciliation: broker fills → live.duckdb; deltas flagged if > 0.5%
T+2+         — Settlement (T+2 for US equities); cash-flow reconciliation
```

### 4.2 Reconciliation

- **Position reconciliation:** `nautilus_bridge.reconcile` runs after every fill batch.
  Expected positions from TradePlan compared to broker-reported fills. Mismatches > 0.5%
  generate WARNING; > 5% trigger kill-switch until resolved.
- **Cash reconciliation:** Daily vs broker statement. Any discrepancy > $100 escalated
  same day.
- **NAV reconciliation:** [TBD-LIVE] Weekly vs fund administrator; monthly sign-off.

### 4.3 Trade error handling

- **Error classification:**
  - Severity 1: unintended position (wrong ticker, wrong direction, wrong size > 10x intended)
  - Severity 2: partial fill + missed follow-up (execution gap)
  - Severity 3: slippage exceeding model estimate by > 2x
- **Response protocol:**
  - Severity 1: halt all trading via kill-switch; unwind erroneous position at next open;
    LP notification within 24 hours; entry in research log + error register.
  - Severity 2: complete at next rebalance; document in research log; track cumulative
    execution gap vs F6 cost-drag trigger.
  - Severity 3: monitor; if recurring, revisit cost model in `src/nyse_core/cost_model.py`
    and re-run backtest with updated slippage assumption.
- **Error register:** [TBD-LIVE] Append-only entry in research log (same hash-chained file)
  with error-type tag. Reported in quarterly letter (`docs/QUARTERLY_LETTER_TEMPLATE.md`).

### 4.4 Segregation of duties (scale-of-one disclosure)

At current scale, portfolio manager, trader, risk officer, compliance officer, and
technology are the same person. This is a material operational limitation and is disclosed
in `docs/DDQ_AIMA_2025.md` §4.1 and `docs/INDEPENDENT_VALIDATION_DRAFT.md` §1.

**Compensating controls:**

1. **Process-based controls replace person-based controls.** Pre-registered gates (G0-G5),
   pre-registered falsification triggers (F1-F8 frozen 2026-04-15), hash-chained research
   log — any of these can detect a human override because the override breaks the chain.
2. **Kill-switch requires no human to execute.** `config/strategy_params.yaml: kill_switch: true`
   halts orders without requiring a second signer. Fails safe.
3. **Independent validation:** `docs/INDEPENDENT_VALIDATION_DRAFT.md` is explicitly labeled
   as draft and not a substitute for a third-party reviewer. Third-party validation is a
   precondition for external capital.
4. **External timestamping of chain tip** (TODO-27): monthly publish of the hash-chain tip
   creates an external witness that prevents retroactive chain rewrites.

---

## 5. Cybersecurity

### 5.1 Threat model

| Threat | Likelihood | Impact | Mitigation |
|--------|-----------|--------|------------|
| Credential theft (broker API key) | Medium | Critical | All secrets in env vars, never in repo; gitleaks pre-commit hook; rotation on any suspected exposure (see `feedback_secret_leakage.md`) |
| Laptop theft | Low | High | Full-disk encryption (LUKS); no broker keys on laptop during research; live keys only on dedicated hardened host |
| Supply-chain (compromised Python package) | Medium | High | `pip-audit` on every `pyproject.toml` update; pin exact versions in `uv.lock`; no dev dependencies in live environment |
| Data vendor compromise | Low | Medium | PiT enforcement + data-quality gates catch injected bad data; no direct write path from vendor to live.duckdb |
| Insider (single operator) | N/A | N/A | Scale-of-one; compensating control is the hash chain |
| Social engineering | Medium | High | [TBD-LIVE] 2FA on broker + cloud + email; hardware key for broker; no phone-based account recovery |
| DDoS on live infra | Low | Medium | Execution via NautilusTrader + IB API — not a public endpoint; no web-exposed attack surface until dashboard goes external |

### 5.2 Controls summary

- **Secret management:** Environment variables only. Checked into `.gitignore`. Pre-commit
  hook runs `gitleaks` (TODO-26 will add chain verification to same hook).
- **Access control:** Single-user laptop for research; [TBD-LIVE] dedicated hardened Linux
  host for live (no shared accounts, SSH-key-only, disable password auth).
- **Logging:** Application logs to local file + structured log (JSON). [TBD-LIVE] Ship to
  remote immutable log store post-live (candidates: AWS CloudWatch, self-hosted Loki).
- **Backups:** `research.duckdb`, `live.duckdb`, and the research log are backed up daily
  to encrypted off-site storage (see `docs/DISASTER_RECOVERY.md`).
- **Patching:** OS patches applied weekly on research host; [TBD-LIVE] live host patched
  within 7 days of CVE severity ≥ 7.

### 5.3 Incident response

- **Detection:** Unauthorized trade → kill-switch via config flag → broker halt within seconds.
- **Containment:** Revoke compromised API key at broker; rotate all secrets; force logout.
- **Recovery:** Restore from last known-good backup; replay research log from hash-chain tip.
- **Post-incident:** Written postmortem within 72 hours; LP notification if impact > $10K
  or any unauthorized trade; research-log `incident` event appended.

---

## 6. Business Continuity and Disaster Recovery

See `docs/DISASTER_RECOVERY.md` for detail. Summary here:

| Scenario | RTO | RPO | Procedure |
|----------|-----|-----|-----------|
| Single-host failure | 4 hours | 24 hours | Restore from daily backup to spare machine |
| Broker API outage | 0 (halt) | N/A | Kill-switch engaged; position frozen; wait for recovery |
| Data vendor outage | 1 week | N/A | Cached data ages out to NaN; F8 WARNING fires; strategy holds positions |
| Operator incapacitated | 1 week | 24 hours | Documented restart procedure in `docs/DISASTER_RECOVERY.md`; designated successor receives access per sealed instructions |
| Total site loss (fire/flood) | 1 week | 24 hours | Off-site backup restore to cloud environment |

**Testing cadence:** Quarterly DR drill starting Phase 5 (paper trading). Pre-live, only
backup-restore is tested; failover is theoretical.

---

## 7. Trade Booking and Accounting

| # | Item | Answer |
|---|------|--------|
| 7.1 | Front office → back office split | No split — same operator. Mitigated by hash-chained research log + pre-registered triggers. |
| 7.2 | Trade affirmation | Broker confirmation compared to TradePlan within 1 hour of fill. |
| 7.3 | NAV calculation | [TBD-LIVE] Fund administrator performs weekly NAV; operator shadow-calcs daily. |
| 7.4 | Fee calculation | [TBD-LIVE] Management fee: 1.5% annually accrued daily. Performance fee: 20% over high-water mark, annual crystallization. Both calculated by FA, shadow-calculated by operator. |
| 7.5 | Side pockets | Not used. Weekly liquid strategy. |
| 7.6 | Investor gating | Quarterly redemption with 30 days notice at inception. [TBD-LIVE] Side-letter terms per first-LP negotiation. |

---

## 8. Audit and Independent Review

| # | Item | Answer |
|---|------|--------|
| 8.1 | Financial statement audit | [TBD-LIVE] Annual, big-4 or tier-2 auditor. |
| 8.2 | SOC-1 on fund administrator | Operator reviews FA's SOC-1 annually. |
| 8.3 | Independent model validation | `docs/INDEPENDENT_VALIDATION_DRAFT.md` is a placeholder. Third-party validation contracted before first LP capital. |
| 8.4 | Internal audit | [TBD-LIVE] Semi-annual. Reviewed items: trade error register, reconciliation exceptions, access log, backup success rate, chain-verification runs. |
| 8.5 | Regulatory exam readiness | Per `docs/SEC_FINRA_COMPLIANCE.md`. Docs, configs, research log, and reproducibility package (`scripts/reproduce.sh`) are the primary exam deliverables. |

---

## 9. Known Operational Limitations (pre-live honest disclosure)

This section is what an experienced ODD team will ask about first. Listed explicitly
rather than hidden:

1. **Scale-of-one operation.** Single operator is PM + trader + risk + compliance + tech.
   Compensating controls are documented (§4.4) but do not fully substitute for segregation.
2. **No production trading history.** All performance claims are backtested or from a prior
   strategy on a different market (TWSE). See `docs/INDEPENDENT_VALIDATION_DRAFT.md` §4.
3. **Vendor contracts not executed.** §3 lists the plan; no agreements signed.
4. **Third-party validation not performed.** Precondition for first LP dollar.
5. **Insurance not bound.** Precondition for first LP dollar.
6. **Regulatory registration not filed.** Below AUM threshold; will file as required.
7. **Hash-chain is self-witnessed.** External timestamping (TODO-27) closes this gap via
   git tags or OpenTimestamps.
8. **DR testing is paper-only.** No live failover has occurred.
9. **Research factors failing validation.** 3/3 Tier-1 price-volume factors failed G0-G5 on
   2016-2023. Fundamental factors (piotroski, earnings_surprise, accruals, profitability)
   are the critical path. See `docs/OUTCOME_VS_FORECAST.md`.

---

## Change Log

| Version | Date | Change |
|---------|------|--------|
| 0.1 | 2026-04-18 | Initial draft. |

**Document owner:** Operator
**Review cadence:** Annual, or upon material change to service providers, operations, or cyber posture.
**Related documents:** `docs/DDQ_AIMA_2025.md` §§1, 4, 7, 8, 9, 12; `docs/DISASTER_RECOVERY.md`; `docs/SEC_FINRA_COMPLIANCE.md`; `docs/GOVERNANCE.md` (pending); `docs/COUNTERPARTY_DUE_DILIGENCE.md` (pending).
