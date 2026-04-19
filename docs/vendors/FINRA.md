# Vendor Due-Diligence: FINRA (Short Interest)

> Status: canonical (2026-04-19). Primary short-interest source. Any change to
> endpoint, auth method, rate limit, or publication lag MUST update this file
> and `config/data_sources.yaml` in the same commit. Outage-log rows are
> append-only.
>
> Linked from: `docs/SEC_FINRA_COMPLIANCE.md` §5 (Gaps and Remediation) and
> `docs/DATA_DICTIONARY.md` §6 (FINRA short interest).

## 1. Purpose & pipeline usage

| Item | Value |
|---|---|
| Role | **Primary** source of security-level short interest (bi-monthly reporting) |
| Consumers | `src/nyse_ats/data/finra_adapter.py`, `scripts/download_data.py` |
| Downstream factors | `short_ratio`, `days_to_cover`, `si_pca` (all short-interest features) |
| Outage blast radius | Low-to-medium — short interest refreshes bi-monthly, so week-long outages tolerable; factor value stale for the next scheduled rebalance only |

## 2. Endpoint & contact

| Item | Value |
|---|---|
| Short-interest URL | `https://api.finra.org/data/group/otcMarket/name/shortInterest` (`config/data_sources.yaml:19`) |
| HTTP method | POST with JSON body (`dateRangeFilters`, `domainFilters`) — see `finra_adapter.py:82-113` |
| Docs | <https://www.finra.org/filing-reporting/regulatory-filing-systems/short-interest> |
| FINRA Data Portal | <https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data> |
| Support email | `datasupport@finra.org` |
| Escalation path | Email datasupport@finra.org → reference the query payload + settlement-date range + symbolCode list |

## 3. Auth & rate limits

| Item | Value | Source |
|---|---|---|
| Auth method | None (public, unauthenticated endpoint) |
| Rate limit | No official published limit; adapter self-throttles via `SlidingWindowRateLimiter` to stay well below any unstated quota |
| Payload shape | `{"fields": [...], "dateRangeFilters": [...], "domainFilters": [...]}` (`finra_adapter.py:92-113`) |
| 4xx / 5xx handling | Tenacity retry 3× with exponential backoff 2–30s (`finra_adapter.py:76-81`); HTTP errors bubble as `FinraAdapterError` after retry exhaustion |

There is no token to protect, but callers should still set a descriptive
`User-Agent` and a contact email in future iterations as a courtesy — FINRA
has on occasion rate-limited abusive clients.

## 4. License & ToS summary

| Item | Summary |
|---|---|
| License | Public (FINRA publishes short-interest data under its regulatory mandate) |
| Distribution | Unrestricted; redistribution permitted with attribution |
| ToS | <https://www.finra.org/about/terms-use> |
| Coverage | All FINRA member firms' short positions on OTC + listed equities; bi-monthly snapshot (mid-month + end-of-month settlement dates) |

## 5. Point-in-time (PiT) rule

This is the **most important section** for FINRA — the settlement vs
publication distinction is the source of past leakage incidents industry-wide.

| Item | Value |
|---|---|
| `settlement_date` | Calendar date on which short positions were held — the "as-of" date; stored in the canonical `date` column (`finra_adapter.py:152`) |
| `publication_date` | `settlement_date + publication_lag_days` — the calendar date on which FINRA publishes the snapshot; stored in a separate `publication_date` column (`finra_adapter.py:153, 166`) |
| Publication lag | **11 calendar days** (`config/data_sources.yaml:20`; ingested as `publication_lag_days=11` in `finra_adapter.py:144`) |
| Reporting cadence | Bi-monthly — mid-month (~15th) + end-of-month settlement dates |
| PiT enforcement | `src/nyse_core/pit.py:23` `enforce_pit_lags` uses `publication_date <= as_of_date` as the visibility test, NOT `settlement_date` |
| Holdout guard | Iron rule 1 — any `as_of_date > HOLDOUT_BOUNDARY (2023-12-31)` raises `HoldoutLeakageError` via `src/nyse_core/contracts.py:37-100` |

**Common leakage failure mode:** using `settlement_date` as the visibility
test instead of `publication_date` creates an 11-day look-ahead bias, which
silently improves backtested short-interest factor Sharpe by ~0.1–0.2. The
adapter computes `publication_date` at parse time so downstream code cannot
forget.

## 6. Failover plan

| Trigger | Response |
|---|---|
| Transient 5xx | Automatic retry (tenacity, 3 attempts) |
| Full FINRA outage <1 rebalance cycle | Wait; factor value stays on the most recent snapshot (still stale-compliant given 11-day lag) |
| Full FINRA outage ≥2 rebalance cycles | Flag F8 staleness WARNING for short-interest features; fall back to NASDAQ short-interest API (different symbol coverage but overlaps on common NYSE names) |
| Payload schema change | Canonical parse in `finra_adapter.py:130-178` uses `.get()` with defaults and coerces via `_safe_float`; schema drift surfaces as a per-record warning, not a hard failure |

There is no paid commercial failover for FINRA short interest. NASDAQ's
short-interest feed (`https://api.nasdaq.com/api/quote/{symbol}/short-interest`)
is a partial substitute for NYSE-listed names and may be added as a
`DataAdapter`-protocol backup if an outage exceeds one rebalance cycle.

## 7. Known data-quality issues

| ID | Observed | Workaround | Resolved |
|---|---|---|---|
| DQ-FINRA-01 | Symbol codes in FINRA payloads do not always match CRSP/FinMind canonical tickers (e.g., class-share suffix differences) | Fuzzy-match fallback in vendor registry; manual override CSV for known mismatches | Ongoing |
| DQ-FINRA-02 | Some settlement dates fall on exchange holidays when the underlying market was closed | Adapter emits a per-record warning; PiT layer still respects `publication_date` |  Ongoing (monitored) |
| DQ-FINRA-03 | `daysToCoverQuantity` is occasionally missing for thinly traded names | `_safe_float` converts to NaN; feature layer drops the observation | Resolved (adapter design) |

## 8. Historical outage log (append-only)

| Date (UTC) | Duration | Severity | Detection | Impact | Resolution |
|---|---|---|---|---|---|
| — | — | — | — | No incidents recorded prior to 2026-04-19. | — |

Append a new row on every detected incident; never edit older rows. Include
the research-log hash of the incident event in the resolution column.

## 9. Review cadence & ownership

| Item | Value |
|---|---|
| Owner | Data engineering (solo-operator today; rotate quarterly once team expands) |
| Review cadence | Quarterly + on every bi-monthly cycle miss |
| Last reviewed | 2026-04-19 (iter-14, TODO-18 close) |
| Next review due | 2026-07-19 |
