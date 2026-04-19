# Vendor Due-Diligence: SEC EDGAR (XBRL Companyfacts)

> Status: canonical (2026-04-19). Primary fundamentals source. Any change to
> endpoint, auth method, rate limit, or publication lag MUST update this file
> and `config/data_sources.yaml` in the same commit. Outage-log rows are
> append-only.
>
> Linked from: `docs/SEC_FINRA_COMPLIANCE.md` §5 (Gaps and Remediation) and
> `docs/DATA_DICTIONARY.md` §5 (EDGAR fundamentals).

## 1. Purpose & pipeline usage

| Item | Value |
|---|---|
| Role | **Primary** source of 10-Q / 10-K fundamental metrics (XBRL tags) |
| Endpoint family | `data.sec.gov/api/xbrl/companyfacts/CIK##########.json` |
| Consumers | `src/nyse_ats/data/edgar_adapter.py`, `scripts/download_data.py` |
| Downstream factors | `piotroski`, `accruals`, `profitability`, `earnings_surprise` (all fundamental features) |
| Outage blast radius | Medium — fundamentals refresh at most quarterly, so short outages tolerable; long outages delay F-score refresh |

## 2. Endpoint & contact

| Item | Value |
|---|---|
| Base URL | `https://data.sec.gov` (`config/data_sources.yaml:13`) |
| Companyfacts path | `/api/xbrl/companyfacts/CIK{cik:010d}.json` (`edgar_adapter.py:71`) |
| Ticker→CIK map | `https://www.sec.gov/files/company_tickers.json` (`edgar_adapter.py:72`) |
| Docs | <https://www.sec.gov/developer> and <https://www.sec.gov/privacy.htm#security> |
| Status page | <https://www.sec.gov/status> (planned + unplanned maintenance) |
| Support | <webmaster@sec.gov> |
| Escalation path | If blocked: confirm User-Agent compliance → switch source IP → email webmaster |

## 3. Auth & rate limits

| Item | Value | Source |
|---|---|---|
| Auth method | No token; SEC requires a **User-Agent header** identifying caller | `src/nyse_ats/data/edgar_adapter.py:158` |
| User-Agent env var | `EDGAR_USER_AGENT` (must contain contact email, e.g. `"OpenClaw Research contact@example.com"`) | `config/data_sources.yaml:15` |
| Rate limit | 10 requests / second (SEC fair-access policy) | `config/data_sources.yaml:14` |
| Throttle mechanism | `SlidingWindowRateLimiter` acquires before each request |
| 429 / 403 handling | Tenacity retry 3× with exponential backoff 2–30s; if User-Agent is missing SEC returns 403 with an explanatory body — do not retry, fix the UA |

SEC's published rule: if you exceed 10 req/s or omit a descriptive User-Agent,
your IP may be blocked for 10 minutes or longer. Keep the User-Agent stable
and descriptive; SEC logs and contacts misbehaving callers by the UA email.

## 4. License & ToS summary

| Item | Summary |
|---|---|
| License | Public domain (US government work) |
| Distribution | Unrestricted; redistribution allowed with attribution to SEC |
| ToS | <https://www.sec.gov/privacy.htm#security> — fair-access policy, no denial-of-service, must identify in User-Agent |
| Coverage | All SEC filers; 10-Q (quarterly, `filing_types:[10-Q, 10-K]` in `config/data_sources.yaml:16`) |

## 5. Point-in-time (PiT) rule

| Item | Value |
|---|---|
| Publication lag | 0 calendar days on `filed` date — once a filing is accepted, companyfacts publishes within hours |
| Canonical column | `date` = `period_end` (the reporting-period end date); `filed` is the fact's filing timestamp and is used in PiT logic |
| PiT rule in code | Only facts where `filed <= as_of_date` are visible; see `edgar_adapter.py` companyfacts unpacker |
| Max-age policy | Quarterly metrics stale after ~100 days; annual metrics stale after ~380 days — window enforcement in adapter |
| Holdout guard | Iron rule 1 — any `as_of_date > HOLDOUT_BOUNDARY (2023-12-31)` raises `HoldoutLeakageError` via `src/nyse_core/contracts.py:37-100` |

## 6. Failover plan

| Trigger | Response |
|---|---|
| Transient 5xx | Automatic retry (tenacity, 3 attempts) |
| 403 "missing UA" | Fail fast; adapter rechecks `EDGAR_USER_AGENT` env var and retries once with a diagnostic log |
| Full EDGAR outage <24h | Wait; quarterly cadence tolerates same-day outages |
| Full EDGAR outage ≥7 days | Switch to mirror (e.g., `https://data.sec.gov` has parallel paths via `www.sec.gov`); no paid backup vendor currently |
| XBRL taxonomy change | `edgar_adapter.py:79-105` `_XBRL_TAG_MAP` is ordered — new tags can be appended without reprocessing historical data; document each new tag mapping in `docs/DATA_DICTIONARY.md` |

There is no paid failover for EDGAR — it is the authoritative source. If
`data.sec.gov` is unavailable, treat fundamentals as stale and rely on the
cached `research.duckdb` snapshot for research decisions until service
returns.

## 7. Known data-quality issues

| ID | Observed | Workaround | Resolved |
|---|---|---|---|
| DQ-EDGAR-01 | Flow metrics appear multiple times per fiscal year (quarterly + YTD + annual rollups in same `units` list) | `edgar_adapter.py` filters by `(period_end - period_start)` to keep quarterly for 10-Q and annual for 10-K | Resolved (adapter design) |
| DQ-EDGAR-02 | Some issuers report revenue under `Revenues`, others under `RevenueFromContractWithCustomerExcludingAssessedTax` | Insertion-ordered `_XBRL_TAG_MAP` (`edgar_adapter.py:79-105`) — first tag wins; all known variants mapped | Resolved (adapter design) |
| DQ-EDGAR-03 | `CommonStockSharesOutstanding` is preferred, but many issuers file `WeightedAverageNumberOfSharesOutstandingBasic` | Fallback priority in tag map (`edgar_adapter.py:99-101`) | Resolved (adapter design) |
| DQ-EDGAR-04 | Amended filings (`10-Q/A`, `10-K/A`) silently overwrite the fact; `filed` timestamp on amendment is later than original | PiT logic uses `filed <= as_of_date`, so an amendment is invisible to backtests dated before the amendment | Resolved (adapter design) |

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
| Review cadence | Quarterly + on any XBRL taxonomy change announced by the SEC |
| Last reviewed | 2026-04-19 (iter-14, TODO-18 close) |
| Next review due | 2026-07-19 |
