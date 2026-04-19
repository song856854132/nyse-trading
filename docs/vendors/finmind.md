# Vendor Due-Diligence: FinMind

> Status: canonical (2026-04-19). Primary OHLCV vendor. Any change to endpoint,
> auth method, rate limit, or publication lag MUST update this file and
> `config/data_sources.yaml` in the same commit. Outage-log rows are
> append-only — never edit or reorder past entries.
>
> Linked from: `docs/SEC_FINRA_COMPLIANCE.md` §5 (Gaps and Remediation) and
> `docs/DATA_DICTIONARY.md` §4 (FinMind OHLCV).

## 1. Purpose & pipeline usage

| Item | Value |
|---|---|
| Role | **Primary** OHLCV source (bulk historical + daily incremental) |
| Dataset | `USStockPrice` (US equities) |
| Consumers | `src/nyse_ats/data/finmind_adapter.py`, `scripts/download_data.py` |
| Downstream factors | `ivol_20d`, `momentum_2_12`, `high_52w`, `ewmac` (all price/volume features) |
| Outage blast radius | Critical — every price/volume factor stops computing; feature staleness cascade (F8) fires within 10 trading days |

## 2. Endpoint & contact

| Item | Value |
|---|---|
| Base URL | `https://api.finmindtrade.com/api/v4` (`config/data_sources.yaml:4`) |
| Data endpoint | `{base_url}/data` (GET) |
| Docs | <https://finmindtrade.com/analysis/#/data/api> |
| Status page | None public (self-monitor via health-check endpoint) |
| Support email | `support@finmindtrade.com` (verify on each renewal) |
| Escalation path | Email → GitHub issue on finmind repo → consider failover |

## 3. Auth & rate limits

| Item | Value | Source |
|---|---|---|
| Auth method | Query-string bearer token (`token=<...>`) | `src/nyse_ats/data/finmind_adapter.py:127` |
| Token env var | `FINMIND_API_TOKEN` | `config/data_sources.yaml:5` |
| Rate limit | 30 requests / minute | `config/data_sources.yaml:6` |
| Throttle mechanism | `SlidingWindowRateLimiter` (`src/nyse_ats/data/rate_limiter.py`) acquires before every request |
| 429 handling | Retry up to 3× with exponential backoff 2–30s (`finmind_adapter.py:106-111`); downgraded to warning on persistent failure |
| Token redaction | Error paths scrub `token=<REDACTED>` via regex before logging (`finmind_adapter.py:266`) |

**Known weakness (iron rule 4 partial compliance):** FinMind's public API does not
accept the token as a header — it must go in the query string. The adapter
redacts the token in any error message it emits, but external layers (retry
libraries, intrusive proxies) could theoretically re-log the raw URL. Memory
entry `feedback_secret_leakage.md` tracks this. Mitigations: (1) never enable
requests' `DEBUG` logging in production, (2) the `FINMIND_API_TOKEN` lives in
env vars only (never in config files per AP-13), (3) gitleaks in pre-commit
catches any literal token that lands in a diff.

## 4. License & ToS summary

| Item | Summary |
|---|---|
| Plan tier | Paid / Sponsor (required for `USStockPrice` dataset — free tier is TWSE-only) |
| Distribution | Internal use only; no redistribution of raw data |
| Derived data | Derived metrics (returns, factors, scores) are OK to publish |
| Historical depth | 2016-01-01 onward for US equities (`config/data_sources.yaml:10`) |
| Restrictions | No scraping outside the documented API |

Read the current ToS at <https://finmindtrade.com/analysis/#/terms> at each
quarterly review and flag material changes in the outage-log section as a
"ToS-change" row.

## 5. Point-in-time (PiT) rule

| Item | Value |
|---|---|
| Publication lag | 0 trading days (EOD snapshot available same-day post-close) |
| Canonical column | `date` = trading date; no separate `publication_date` |
| PiT enforcement | `src/nyse_core/pit.py:23` `enforce_pit_lags` with `publication_lags={'close': 0}` |
| Max-age default | 10 calendar days (F8 staleness threshold, `config/falsification_triggers.yaml`) |

## 6. Failover plan

| Trigger | Response |
|---|---|
| Single-symbol 429 | Automatic retry (tenacity, 3 attempts) |
| Full-vendor outage <24h | Wait; F8 WARNING after 3 consecutive rebalance misses |
| Full-vendor outage ≥72h | Stand up Polygon or Tiingo adapter behind existing `DataAdapter` protocol (`src/nyse_ats/data/adapter.py`); dual-write into `research.duckdb` for a week to reconcile |
| ToS violation / account lock | Same as ≥72h outage; evaluate Polygon/Tiingo before switching primary |
| Data quality failure | Existing OHLCV validation in `finmind_adapter.py:197-239` flags `high<max(open,close)` and weekday gaps; any symbol failing >3 consecutive days is quarantined until manual review |

## 7. Known data-quality issues

| ID | Observed | Workaround | Resolved |
|---|---|---|---|
| DQ-FINMIND-01 | USStockPrice occasionally returns `null` `Trading_Volume` for ADRs | Numeric coerce to NaN + downstream impute | Ongoing |
| DQ-FINMIND-02 | Holiday rows occasionally appear with previous-close duplicates | Calendar filter drops non-trading days at load time | Ongoing (monitored) |
| DQ-FINMIND-03 | Split-adjustment is retroactive — vendor mutates historical rows on split events; no advisory | Store raw + adjusted columns separately; rerun ingest nightly for a 5-day rolling window | Ongoing |

## 8. Historical outage log (append-only)

| Date (UTC) | Duration | Severity | Detection | Impact | Resolution |
|---|---|---|---|---|---|
| — | — | — | — | No incidents recorded prior to 2026-04-19. | — |

Append a new row (never edit older rows) on every detected incident. Include
the research-log hash of the incident event in the resolution column for
tamper-evident cross-reference.

## 9. Review cadence & ownership

| Item | Value |
|---|---|
| Owner | Data engineering (solo-operator today; rotate quarterly once team expands) |
| Review cadence | Quarterly + on any adapter schema change + on ToS change |
| Last reviewed | 2026-04-19 (iter-14, TODO-18 close) |
| Next review due | 2026-07-19 |
