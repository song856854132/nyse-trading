# Data Dictionary

> Status: canonical (2026-04-19). Single source of truth for every field entering,
> flowing through, or leaving the NYSE ATS pipeline. Any disagreement between this
> document and `src/nyse_core/schema.py`, `src/nyse_core/contracts.py`, or the
> adapter modules is a bug — the code wins and this file must be corrected.
>
> Scope: vendor-sourced fields (FinMind OHLCV, EDGAR fundamentals, FINRA short
> interest, S&P 500 constituency) plus internal canonical columns, feature outputs,
> and inter-module contracts. Out of scope: transient DataFrame column aliases
> produced inside compute functions — those are implementation detail.

## Conventions

- **Dtypes.** `date` columns are `datetime64[ns]` after adapter normalization;
  `symbol` is string (upper-cased NYSE ticker); `date` + `symbol` together are
  the primary key of almost every long-format table. Numeric columns are float64
  unless explicitly noted (`COL_VOLUME` is float64 despite being conceptually int;
  integer-required fields — target shares, current shares — live in frozen
  dataclass contracts and are typed `int`). Nullability per column is documented
  below.
- **Dates.** Strict calendar — `STRICT_CALENDAR = True` at
  `src/nyse_core/schema.py:13`. Never forward-fill prices (AP-5). A missing
  observation stays missing; the PiT layer decides whether to NaN or error.
- **Point-in-time.** `src/nyse_core/pit.py:23` enforces per-column publication
  lag and max age as of a rebalance date. The universal guard is iron rule 1:
  any `as_of_date` strictly greater than `HOLDOUT_BOUNDARY` (2023-12-31) raises
  `HoldoutLeakageError` via `reject_holdout_dates`
  (`src/nyse_core/contracts.py:37-100`).
- **Sign convention.** ALL factor scores oriented so HIGH score = BUY (Codex #9
  ruling). IVOL, short-interest, accruals, and other naturally-short factors
  are inverted inside their compute functions before rank-percentile.
- **Normalization.** Every factor score is rank-percentile normalized into
  `[0, 1]` before entering the combination model
  (`src/nyse_core/normalize.py` + AP-8 assertion in `signal_combination.py`).
- **Canonical column names.** Import from `src/nyse_core/schema.py` — never
  hard-code string literals. If you see a magic string in module code, fix it.

## Publication-lag registry

| Source       | Field                          | Lag (calendar days) | Source of truth                                                     |
|--------------|--------------------------------|---------------------|---------------------------------------------------------------------|
| FinMind      | `open/high/low/close/volume`   | 0 (T+0, EOD fix)    | FinMind dataset `USStockPrice`; daily snapshot                      |
| EDGAR        | `revenue/net_income/...`       | 0 on `filed` date   | `filed` field in companyfacts JSON; adapter uses filing date as PiT |
| FINRA        | `short_interest/days_to_cover` | 11                  | `config/data_sources.yaml:20` `finra.publication_lag_days: 11`      |
| Constituency | `action`                       | 0 (event-dated)     | Wikipedia historical changes table; event-dated `effective_date`    |

The runtime wiring lives at `src/nyse_core/pit.py:78` — each feature column is
looked up in the `publication_lags` dict and that many calendar days are added
to the filing date before comparing against `as_of_date`. Columns not present
in the dict are assumed to have zero lag.

---

## 1. FinMind OHLCV

**Source-of-truth module:** `src/nyse_ats/data/finmind_adapter.py`
**Vendor dataset:** `USStockPrice` (see `config/data_sources.yaml:8`)
**Endpoint:** `https://api.finmindtrade.com/api/v4/data`
**Auth:** `FINMIND_API_TOKEN` env var, header auth only (never query string —
see `memory/feedback_secret_leakage.md`).
**Rate limit:** 30 requests/minute (`config/data_sources.yaml:6`).
**PiT rule:** T+0, no publication lag (EOD snapshot published after close).
**Refresh cadence:** daily incremental; full backfill on bulk load.

### Fields (per-row, one row per `(date, symbol)`)

| Canonical column | Vendor raw              | Type       | Unit   | Nullable | Notes                                                       |
|------------------|-------------------------|------------|--------|----------|-------------------------------------------------------------|
| `date`           | `Trading_Date` / `date` | date       | —      | No       | Trading session date. Normalized to `datetime64[ns]`.       |
| `symbol`         | `stock_id`              | str        | —      | No       | NYSE ticker, uppercased. PK component.                      |
| `open`           | `Open` / `open`         | float64    | USD    | No       | Session open.                                               |
| `high`           | `High` / `max`          | float64    | USD    | No       | Session high.                                               |
| `low`            | `Low` / `min`           | float64    | USD    | No       | Session low.                                                |
| `close`          | `Close` / `close`       | float64    | USD    | No       | Session close. Never forward-filled (AP-5).                 |
| `volume`         | `Trading_Volume` / `Volume` | float64 | shares | No       | Total session volume.                                       |

Canonical column mapping lives at
`src/nyse_ats/data/finmind_adapter.py:42-60`; output shape enforced by
`_CANONICAL_OHLCV` at `:62-70`.

### Known gotchas

- **No adjusted close from FinMind.** Split/dividend adjustment happens inside
  `src/nyse_core/corporate_actions.py` via an event-sourced append-only log.
  `COL_ADJ_CLOSE` (`src/nyse_core/schema.py:23`) is reserved for that output,
  not the vendor field.
- **Two column-name conventions.** FinMind returns either lowercase
  (`open/max/min/close`) or capitalized (`Open/High/Low/Close`) depending on
  dataset vintage. The adapter accepts both and maps to canonical names.
- **Error-path redaction.** Any adapter error message that would include the
  query URL must redact the token. This is enforced by regex scrub in the
  adapter's exception handlers. Iron rule 4.

---

## 2. EDGAR Fundamentals (XBRL companyfacts)

**Source-of-truth module:** `src/nyse_ats/data/edgar_adapter.py`
**Endpoint:** `https://data.sec.gov/api/xbrl/companyfacts/CIK{10-digit}.json`
**Auth:** user-agent header only (SEC requires contact info). Env var
`EDGAR_USER_AGENT` (`config/data_sources.yaml:15`); default
`"nyse-ats-bot contact@example.com"` when unset.
**Rate limit:** 10 requests/second (SEC fair-use).
**PiT rule:** `date` column is the `filed` date — i.e. the SEC-stamped filing
date. Zero publication lag: the moment SEC accepts the filing, it's public.
Quarterly vs annual disambiguation by `(period_end − period_start)` window
(`src/nyse_ats/data/edgar_adapter.py:123-124`: quarterly 80–100 days; annual
350–380 days).
**Refresh cadence:** one companyfacts call per symbol on rebalance; cached.

### Output fields

Long-format (one row per metric observation):

| Canonical column | Type     | Unit                 | Nullable | Notes                                                    |
|------------------|----------|----------------------|----------|----------------------------------------------------------|
| `date`           | date     | —                    | No       | SEC `filed` date. Usable as-of this date.                |
| `symbol`         | str      | —                    | No       | Resolved from ticker → CIK map.                          |
| `metric_name`    | str      | —                    | No       | One of 10 canonical names (see XBRL tag map below).      |
| `value`          | float64  | USD / shares / USD-per-share | No | Unit depends on metric; see below.                       |
| `filing_type`    | str      | —                    | No       | `10-Q` or `10-K` (`config/data_sources.yaml:16`).        |
| `period_end`     | date     | —                    | No       | Last day of the reporting period.                        |

Output columns enforced at `src/nyse_ats/data/edgar_adapter.py:60-66`.

### Canonical metric → XBRL tag map

Insertion order matters — first tag listed wins when multiple XBRL tags map
to the same canonical metric. Source of truth:
`src/nyse_ats/data/edgar_adapter.py:79-105`.

| Canonical metric      | Type | Unit           | XBRL tags (first wins)                                                                                                 |
|-----------------------|------|----------------|------------------------------------------------------------------------------------------------------------------------|
| `revenue`             | Flow | USD            | `Revenues`, `RevenueFromContractWithCustomerExcludingAssessedTax`, `SalesRevenueNet`                                   |
| `net_income`          | Flow | USD            | `NetIncomeLoss`                                                                                                        |
| `gross_profit`        | Flow | USD            | `GrossProfit`                                                                                                          |
| `cost_of_revenue`     | Flow | USD            | `CostOfRevenue`, `CostOfGoodsAndServicesSold`, `CostOfGoodsSold`                                                       |
| `total_assets`        | PiT  | USD            | `Assets`                                                                                                               |
| `current_assets`      | PiT  | USD            | `AssetsCurrent`                                                                                                        |
| `total_liabilities`   | PiT  | USD            | `Liabilities`                                                                                                          |
| `current_liabilities` | PiT  | USD            | `LiabilitiesCurrent`                                                                                                   |
| `long_term_debt`      | PiT  | USD            | `LongTermDebtNoncurrent`, `LongTermDebt`                                                                               |
| `operating_cash_flow` | Flow | USD            | `NetCashProvidedByUsedInOperatingActivities`                                                                           |
| `shares_outstanding`  | PiT  | shares         | `CommonStockSharesOutstanding`, `EntityCommonStockSharesOutstanding`, `WeightedAverageNumberOfSharesOutstandingBasic`  |
| `eps`                 | Flow | USD per share  | `EarningsPerShareBasic`, `EarningsPerShareDiluted`                                                                     |

**Flow vs PiT.** Flow metrics (`revenue`, `net_income`, `gross_profit`,
`cost_of_revenue`, `operating_cash_flow`, `eps`) require window filtering on
`(period_end − period_start)` so we don't mix quarterly + YTD rollups. PiT
metrics (balance sheet + `shares_outstanding`) pass through unfiltered. The
`_FLOW_METRICS` set at `src/nyse_ats/data/edgar_adapter.py:109-116` is the
authoritative list.

### Known gotchas

- **CIK, not ticker.** Every companyfacts call keys by 10-digit CIK. Ticker →
  CIK mapping is lazy-loaded from `www.sec.gov/files/company_tickers.json` and
  cached per adapter instance.
- **Restated filings.** When a company restates, SEC accepts a new filing with
  an earlier `period_end` but a later `filed` date. Our PiT rule (use `filed`
  as `date`) handles this correctly — the restatement is only visible after
  the restatement filing date.
- **Deduplication.** Same `(metric, period_end, filed, form)` can appear
  multiple times if a filing references the same fact via multiple tags.
  First entry in the tag map wins (`_XBRL_TAG_MAP` preserves insertion order).

---

## 3. FINRA Short Interest

**Source-of-truth module:** `src/nyse_ats/data/finra_adapter.py`
**Endpoint:**
`https://api.finra.org/data/group/otcMarket/name/shortInterest`
(`config/data_sources.yaml:19`)
**Auth:** public endpoint, no key required.
**Rate limit:** none documented; sliding window applied for courtesy.
**PiT rule:** 11 calendar days between `settlement_date` and publication
(`config/data_sources.yaml:20` `finra.publication_lag_days: 11`). Adapter
records both — `date` holds the settlement date and `publication_date` holds
settlement + lag, and `src/nyse_core/pit.py` NaNs any row whose
`publication_date > as_of_date`.
**Refresh cadence:** bi-monthly (settlements mid-month and month-end per FINRA
schedule).

### Fields

Output columns at `src/nyse_ats/data/finra_adapter.py:35-48`.

| Canonical column    | Vendor raw                         | Type    | Unit   | Nullable | Notes                                                       |
|---------------------|------------------------------------|---------|--------|----------|-------------------------------------------------------------|
| `date`              | `settlementDate`                   | date    | —      | No       | Settlement date — the observation date.                     |
| `symbol`            | `securityCode` / ticker            | str     | —      | No       | NYSE ticker.                                                |
| `short_interest`    | `currentShortPositionQuantity`     | float64 | shares | Yes      | Aggregate short position at settlement.                     |
| `days_to_cover`     | `daysToCoverQuantity`              | float64 | days   | Yes      | Short interest / ADV.                                       |
| `short_ratio`       | `shortInterestRatioQuantity`       | float64 | pct    | Yes      | Short interest as % of float.                               |
| `publication_date`  | `settlementDate + 11d`             | date    | —      | No       | Derived; controls PiT availability.                         |

Float fields are nullable because FINRA occasionally posts records with
missing quantity fields; the adapter's `_safe_float` helper at
`src/nyse_ats/data/finra_adapter.py:163-165` silently NaNs them.

### Known gotchas

- **Settlement vs publication.** Never join `short_interest` to a factor run
  keyed on `date = settlement_date` without also checking `publication_date`
  against `as_of_date`. The PiT layer handles this; direct SQL on the raw
  table must replicate the check.
- **Sign convention.** All three short-interest columns are BEARISH — high
  value = short-pressure signal. Factor compute functions invert the sign
  before rank-percentile so HIGH score = BUY.

---

## 4. S&P 500 Constituency

**Source-of-truth module:** `src/nyse_ats/data/constituency_adapter.py`
**Primary source:** Wikipedia "List of S&P 500 companies" page
(`https://en.wikipedia.org/wiki/List_of_S%26P_500_companies`).
**Backup source:** `config/sp500_changes.csv`
(`config/data_sources.yaml:25-26`).
**Auth:** none.
**Rate limit:** none (Wikipedia scraping; light cadence).
**PiT rule:** event-dated; zero lag. `action` takes effect on `date`.
**Refresh cadence:** ad-hoc when constituency changes are suspected.

### Fields

| Canonical column | Type | Unit | Nullable | Notes                                                 |
|------------------|------|------|----------|-------------------------------------------------------|
| `date`           | date | —    | No       | Effective date of the change.                         |
| `symbol`         | str  | —    | No       | Ticker being added or removed.                        |
| `action`         | str  | —    | No       | `ADD` or `REMOVE` — see `ACTION_ADD` / `ACTION_REMOVE` at `src/nyse_ats/data/constituency_adapter.py:27-28`. |

Output columns at `src/nyse_ats/data/constituency_adapter.py:30`.

### Known gotchas

- **Survivorship bias guard.** Use `src/nyse_core/universe.py` to materialize
  the as-of-date membership set, never a static snapshot. Historical changes
  must be applied in chronological order.
- **Ticker changes.** When a company changes ticker (e.g. FB → META), the
  change is encoded as a paired `REMOVE` / `ADD` event, not a rename. Consumers
  must stitch the history using the CUSIP or entity-level mapping — deferred
  to TODO-18 (vendor files) and currently left as a known limitation.

---

## 5. Internal canonical columns (`src/nyse_core/schema.py`)

These are the public column-name constants that every module imports. Never
hard-code these strings anywhere else.

### OHLCV (`:15-33`)

| Constant          | Value          | Used by                                     |
|-------------------|----------------|---------------------------------------------|
| `COL_DATE`        | `"date"`       | Every long-format table                     |
| `COL_SYMBOL`      | `"symbol"`     | Every long-format table                     |
| `COL_OPEN`        | `"open"`       | OHLCV tables, execution cost calcs          |
| `COL_HIGH`        | `"high"`       | OHLCV tables, 52-week-high factor           |
| `COL_LOW`         | `"low"`        | OHLCV tables                                |
| `COL_CLOSE`       | `"close"`      | OHLCV tables, most price-based factors      |
| `COL_VOLUME`      | `"volume"`     | OHLCV tables, liquidity filters             |
| `COL_ADJ_CLOSE`   | `"adj_close"`  | Reserved for corporate-actions-adjusted output |

### Feature outputs (`:35-43`)

| Constant               | Value                | Notes                                                     |
|------------------------|----------------------|-----------------------------------------------------------|
| `COL_FACTOR`           | `"factor_name"`      | Long-format factor tables.                                |
| `COL_SCORE`            | `"composite_score"`  | Output of `signal_combination`.                           |
| `COL_RANK_PCT`         | `"rank_pct"`         | Output of `normalize.rank_percentile`; ∈ [0, 1].          |
| `COL_FORWARD_RET_5D`   | `"fwd_ret_5d"`       | Primary label: Mon-open T+1 to Fri-close T+5.             |
| `COL_FORWARD_RET_20D`  | `"fwd_ret_20d"`      | Secondary (robustness) label.                             |
| `COL_SECTOR`           | `"gics_sector"`      | Used for Brinson-style sector attribution.                |
| `COL_MARKET_CAP`       | `"market_cap"`       | From EDGAR (`shares_outstanding × close`).                |
| `COL_ADV_20D`          | `"adv_20d"`          | 20-day average dollar volume.                             |

### Portfolio fields (`:45-49`)

| Constant           | Value              | Notes                                                   |
|--------------------|--------------------|---------------------------------------------------------|
| `COL_WEIGHT`       | `"weight"`         | Equal-weight post-allocator; ∈ [0, MAX_POSITION_PCT].   |
| `COL_TARGET_SHARES`| `"target_shares"`  | Integer share count for the next rebalance cycle.       |
| `COL_SIDE`         | `"side"`           | `Side` enum value (BUY / SELL / HOLD).                  |
| `COL_REASON`       | `"reason"`         | Free-text rationale stored with every TradePlan.        |

### Enums (`:52-108`)

| Enum                     | Values                                                 | Purpose                                      |
|--------------------------|--------------------------------------------------------|----------------------------------------------|
| `Side`                   | `BUY` / `SELL` / `HOLD`                                | Order direction for TradePlan.               |
| `Severity`               | `VETO` / `WARNING`                                     | Falsification trigger response category.     |
| `UsageDomain`            | `SIGNAL` / `RISK`                                      | AP-3 anti-double-dip marker in registry.     |
| `RegimeState`            | `BULL` / `BEAR`                                        | SMA200 binary overlay state.                 |
| `RebalanceFrequency`     | `WEEKLY` / `MONTHLY`                                   | Cadence in `strategy_params.yaml`.           |
| `CombinationModelType`   | `RIDGE` / `GBM` / `NEURAL`                             | Signal combination model toggle.             |
| `NormalizationMethod`    | `RANK_PERCENTILE` / `WINSORIZE` / `Z_SCORE`            | Default is `RANK_PERCENTILE`.                |

### Frozen research-period constants

| Constant                       | Value                | Source of truth                                     |
|--------------------------------|----------------------|-----------------------------------------------------|
| `STRICT_CALENDAR`              | `True`               | `src/nyse_core/schema.py:13`                        |
| `TRADING_DAYS_PER_YEAR`        | `252`                | `src/nyse_core/schema.py:12`                        |
| `HOLDOUT_BOUNDARY`             | `date(2023, 12, 31)` | `src/nyse_core/contracts.py:37`                     |
| `DEFAULT_MIN_PRICE`            | `5.0` USD            | `src/nyse_core/schema.py:112`                       |
| `DEFAULT_MIN_ADV_20D`          | `500_000` USD        | `src/nyse_core/schema.py:113`                       |
| `DEFAULT_TOP_N`                | `20`                 | `src/nyse_core/schema.py:114`                       |
| `MAX_POSITION_PCT`             | `0.10`               | `src/nyse_core/schema.py:117`                       |
| `MAX_SECTOR_PCT`               | `0.30`               | `src/nyse_core/schema.py:118`                       |
| `BULL_EXPOSURE` / `BEAR_EXPOSURE` | `1.0` / `0.4`     | `src/nyse_core/schema.py:128-129`                   |
| `SMA_WINDOW`                   | `200`                | `src/nyse_core/schema.py:130`                       |
| `DEFAULT_PURGE_DAYS`           | `5`                  | `src/nyse_core/schema.py:134`                       |
| `DEFAULT_EMBARGO_DAYS`         | `5`                  | `src/nyse_core/schema.py:135`                       |
| `MAX_PARAMS_WARNING`           | `5` (AP-7)           | `src/nyse_core/schema.py:137`                       |
| `BASE_SPREAD_BPS`              | `10.0`               | `src/nyse_core/schema.py:141`                       |
| `MONDAY_MULTIPLIER`            | `1.3`                | `src/nyse_core/schema.py:142`                       |
| `EARNINGS_WEEK_MULTIPLIER`     | `1.5`                | `src/nyse_core/schema.py:143`                       |

These are AP-6 frozen and must never be edited in response to a result.

---

## 6. Inter-module contracts (`src/nyse_core/contracts.py`)

Frozen dataclasses that cross module boundaries. Any caller that unpacks them
must depend on this shape, not on the underlying DataFrame dtypes.

| Contract                     | Key fields                                                                                         | Who produces                                  | Who consumes                                                    | Source                                    |
|------------------------------|----------------------------------------------------------------------------------------------------|-----------------------------------------------|-----------------------------------------------------------------|-------------------------------------------|
| `UniverseSnapshot`           | `data`, `rebalance_date`, `universe_size`                                                          | `nyse_ats/pipeline.py`                        | feature compute functions                                       | `contracts.py:154-165`                    |
| `FeatureMatrix`              | `data` (MultiIndex `(date, symbol)` × factor), `factor_names`, `rebalance_date` — values ∈ [0, 1]   | `normalize.py`                                | `signal_combination`, gates, attribution                        | `contracts.py:168-179`                    |
| `GateVerdict`                | `factor_name`, `gate_results` (dict[str, bool]), `gate_metrics` (dict[str, float]), `passed_all`    | `gates.py` / `factor_screening.py`            | registry admission, research log, TODO closure evidence         | `contracts.py:182-189`                    |
| `CompositeScore`             | `scores` (Series[symbol → score]), `rebalance_date`, `model_type`, `feature_importance`             | `signal_combination.py`                       | `allocator.py`, attribution                                     | `contracts.py:192-199`                    |
| `TradePlan`                  | `symbol`, `side`, `target_shares`, `current_shares`, `order_type`, `reason`, `decision_timestamp`, `execution_timestamp`, `estimated_cost_bps`, `provenance` | `portfolio.py`                                | `nautilus_bridge.py`                                            | `contracts.py:202-218`                    |
| `PortfolioBuildResult`       | `trade_plans`, `cost_estimate_usd`, `turnover_pct`, `regime_state`, `rebalance_date`, `held_positions`, `new_entries`, `exits`, `skipped_reason`           | `portfolio.py`                                | execution bridge, dashboard, research log                       | `contracts.py:221-233`                    |
| `BacktestResult`             | `daily_returns`, `oos_sharpe`, `oos_cagr`, `max_drawdown`, `annual_turnover`, `cost_drag_pct`, `per_fold_sharpe`, `per_factor_contribution`, `permutation_p_value`, `bootstrap_ci_lower/upper`, `romano_wolf_p_values` | `backtest.py`                                 | gates, research log, attribution report                         | `contracts.py:236-251`                    |
| `FalsificationCheckResult`   | `trigger_id`, `trigger_name`, `current_value`, `threshold`, `severity`, `passed`, `description`     | `falsification.py`                            | alert bot, dashboard, halt logic                                | `contracts.py:254-264`                    |
| `ThresholdCheck`             | `name`, `metric_name`, `current_value`, `threshold`, `direction`, `passed`                         | shared evaluator inside `gates.py`            | gates, falsification                                            | `contracts.py:267-276`                    |
| `AttributionReport`          | `factor_contributions`, `sector_contributions`, `total_return`, `period_start`, `period_end`       | `attribution.py`                              | monthly attribution report template (TODO-15)                   | `contracts.py:279-287`                    |
| `DriftCheckResult`           | (see module — factor, rolling IC, drift/retrain flags)                                              | `drift.py`                                    | retraining logic, dashboard                                     | `contracts.py:290-293`                    |
| `Diagnostics`                | `messages: list[DiagMessage]` with severity levels                                                  | every pure `nyse_core` function               | pipeline logging, research log                                  | `contracts.py:102-152`                    |

All pure `nyse_core` functions return `(result, Diagnostics)` tuples — no
logging, no side effects, no I/O.

---

## 7. Change protocol

Data-dictionary drift is a compliance-relevant event. The process:

1. **On any adapter schema change** (new vendor field, renamed column, changed
   publication lag, new XBRL tag): update this document in the same commit
   that changes the adapter.
2. **On any `src/nyse_core/schema.py` constant change**: update the relevant
   row here in the same commit.
3. **On a new internal contract** (new frozen dataclass in `contracts.py`): add
   a row to Section 6 and cite the line range.
4. **Review cadence:** read-through on every AUDIT_TRAIL entry that touches
   vendor or schema code (quarterly at minimum).
5. **CI guard (future — TODO-infra):** a pre-commit hook to diff this file
   against `schema.py` constants and `contracts.py` dataclass definitions,
   failing the commit if a constant or field is added without a dictionary
   update. Open follow-up TODO if time permits.

## 8. Known open items (deferred)

- **Ticker-change handling** in constituency — flagged at Section 4; tracked
  as a TODO-18 vendor-file question (S&P 500 ticker rename history source).
- **Adjusted close source** — currently computed in-process from the
  corporate-actions log; no vendor-provided `adj_close`. If FinMind exposes a
  factor-adjusted series in future, prefer it and update Section 1.
- **Market cap realization lag** — `COL_MARKET_CAP` is computed from EDGAR
  `shares_outstanding` (PiT, available at `filed` date) × FinMind `close`
  (T+0). Effective lag is the EDGAR filing lag of `shares_outstanding`.
