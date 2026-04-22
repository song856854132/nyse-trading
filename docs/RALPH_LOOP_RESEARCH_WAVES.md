# Ralph Loop Task: 20-Iteration Cross-Sectional Alpha Research Waves

You are running a 20-iteration (escalate to 40 if needed) research loop on the NYSE ATS framework. The prior `RALPH_LOOP_TASK.md` loop (P1/P2 infrastructure gaps) is **complete** — do not re-open it. This loop opens the next research wave now that iter-0 has verified the 2026-04-18 baseline is reproducible.

The canonical research narrative lives at `docs/NYSE_ALPHA_RESEARCH_RECORD.md` §Eighth Action. Read it at the start of every iteration. The hash-chained event log lives at `results/research_log.jsonl` and is **the** source of truth for which iterations have shipped.

**Standing authorization (from the operator):** auto-proceed as long as every decision is AP-6-safe and reversible (two-way door). Any threshold change, factor-sign flip, gate-definition edit, holdout touch, or admission-verdict revision is a **one-way door** — halt and ask. If 20 iterations is not enough, continue to 40.

## Iron Rules — Violating Any Is an Immediate Halt

1. **No post-2023 data.** Never read, query, or backtest any date after 2023-12-31. Holdout is 2024-2025, governed by `results/holdout/.holdout_used` lockfile. Pre-commit `holdout path guard` enforces this at the filesystem level.
2. **AP-6 absolute.** Never change a gate threshold, falsification trigger, abandonment criterion, factor sign convention, or admission verdict after seeing a result. All additions in this loop must be **diagnostic-only** until a dedicated pre-registered `correction` event is logged — and corrections are one-way-door decisions that require operator approval.
3. **No DB mocks in integration tests.** Prior incident, zero tolerance. Synthetic pandas/numpy fixtures only.
4. **No secret leakage.** FinMind adapter must use header auth and redact query strings in every error path. Pre-commit `gitleaks` enforces at commit time.
5. **No `--no-verify`.** If a hook fails, fix the root cause. The six pre-commit hooks (gitleaks, ruff check, ruff format, mypy, holdout path guard, research-log chain verification) are non-negotiable.
6. **Hash chain preserved.** Every research-relevant artifact is appended via `scripts/append_research_log.py` (never hand-edited). The chain tip is the prior iteration's hash — if you do not know it, halt and read the log.
7. **TODO-11 and TODO-23 untouched.** Factor screening results (TODO-11) and paper-trade deployment (TODO-23) remain frozen for the duration of this loop. The strategy is in research, not pre-deployment.
8. **iter-0 bit-exact reproduction is the anchor.** 5 of 6 factors (ivol_20d, high_52w, momentum_2_12, accruals, profitability) reproduce bit-exactly vs 2026-04-18. Piotroski has a known quintile-tie non-determinism (TODO-36, still well below G0 floor so admission verdict unchanged). Never change the 491-symbol factor universe — put any new data (benchmarks, sector maps, alt-source prices) in isolated tables or static CSVs.

## State of Prior Iterations (Completed)

| iter | Wave | Commit | Research-log hash tip | Scope |
|---|---|---|---|---|
| 0 | pre-wave | `c6d6be4` | `c6db45b0...22f01908` | 6-factor reproduction (5 bit-exact, 1 known-discrete drift) |
| 1 | A-benchmark | `f3e340e` | `568d10bd...84ed963e` | `benchmark_ohlcv` table + `benchmark_relative_metrics` |
| 2 | A-benchmark | `9a9378c` | `2a030ef3...b4a42142` | `compute_sector_neutral_returns` (pure helper, sourcing deferred) |
| 3 | A-benchmark | `0a30f31` | `2c0fe425...ea2620cd` | Static GICS CSV + `sector_map_loader` + Brinson wiring + sector-neutral benchmark wired into `screen_factor.py` |
| 4 | A-benchmark | `28681d2` | `98fd0417...81034de0` | `compute_characteristic_matched_benchmark` pure helper + `char_matched_size` wiring in `screen_factor.py` (size proxy = 20d mean close×volume; 18 tests; ls_weights hoisted; diagnostic only) |
| 5 | B-portfolio | pending | `c1fa28f0...e38b2bcb` | `compute_volatility_scaled_weights` pure helper (inverse-vol within leg; degenerates to equal-weight when all vols equal) + `_build_vol_panel` (20d trailing std of daily pct_change) + `alternative_portfolios.{vol_scaled,equal_weight_baseline}` persisted in `screening_metrics.json`; 13 tests; diagnostic only |

**Wave 1 (A-benchmark) COMPLETE.** All four benchmark references (SPY, RSP, sector_neutral, char_matched_size) now flow through `compute_benchmark_relative_metrics` in `screen_factor.py`. Gate admission (G0-G5) untouched.

**Wave 2 (B-portfolio) IN PROGRESS.** iter-5 shipped (vol-scaled long-short). Next: iter-6 market-cap-tilted, iter-7 Sharpe-weighted ensemble, iter-8 risk-parity across legs.

**Current research-log chain tip:** `c1fa28f0b97fb3295e2316ac3a15925a0dc4c81429651dd548a6c411e38b2bcb` (iter-5, 2026-04-22).

## Next Iteration Scope

### Wave 1 (iter-4): Characteristic-matched benchmark

**Goal.** Ship a pure `compute_characteristic_matched_benchmark(daily_returns, characteristic_panel, n_buckets=5) -> (Series, Diagnostics)` that, for each date, splits the universe into `n_buckets` quantiles of the characteristic (e.g., market cap, book-to-market, 12-month momentum), takes the equal-weight return within each bucket, and returns the bucket-mean matched to the **long-leg composition** of the factor portfolio. This is the iter-2 pre-announced slot.

**Why.** SPY and RSP are size-biased benchmarks; the sector-neutral benchmark removes GICS bias. A characteristic-matched benchmark removes style bias (size/value/momentum) so the factor-screen diagnostic measures the alpha contribution **net of known styles** — which is the right question for "does this factor add to an existing style-factor ensemble?"

**Shape.**
- New pure leaf in `src/nyse_core/benchmark_construction.py` (sibling to iter-2 sector_neutral).
- Input: `daily_returns: pd.DataFrame [date x symbol]`, `characteristic_panel: pd.DataFrame [date, symbol, value]`, `n_buckets: int = 5`.
- Matching rule: for each date, compute the long-leg's weighted-mean bucket index, round to nearest integer bucket, return that bucket's equal-weight mean.
- Returns `(pd.Series, Diagnostics)`. Empty / zero-overlap → NaN series + warning.
- 10+ new tests covering: hand-computed two-stage means, monotone characteristic, NaN handling, empty inputs, multi-bucket-tie boundaries, single-bucket degeneracy, unmapped-symbol exclusion, matched-vs-universe-mean reduces to universe-mean when long-leg is universe, per-date bucket imbalance, long-only vs long-short.

**Diagnostic-only wiring.** `scripts/screen_factor.py` persists `benchmark_relative_metrics["char_matched_size"]` (market-cap characteristic) under `screening_metrics.json`. No gate (G0-G5) compared against this.

**AP-6 check before committing:** no threshold, no admission change, no new factor sign. If iter-4 reveals a style-factor that explains 100% of a factor's alpha, that is a **finding to log, not a reason to drop the factor** — admission is governed by G0-G5 only.

### Wave 2 (iter 5-8): Portfolio construction alternatives

All diagnostic. Ship each as a pure helper + `screen_factor.py` persistence, with tests but no gate comparison. No rank/sign/factor-universe changes.

- **iter-5: volatility-scaled long-short weights.** `compute_volatility_scaled_weights(factor_scores, vol_panel)` returns per-date weights that normalize each stock's position size by trailing-20d realized volatility (Carver's vol targeting at the position level). Diagnostic for "would vol-scaling have helped the failing factors?"
- **iter-6: market-cap-tilted long-short weights.** Alternative to equal-weight within leg. Reduces the tiny-cap exposure that often dominates equal-weight long-short portfolios.
- **iter-7: Sharpe-weighted ensemble aggregation.** `compute_ensemble_weights(factor_score_panels, sharpes_vector)` — diagnostic-only multi-factor aggregation (no admission change).
- **iter-8: risk-parity across factor legs.** `compute_risk_parity_weights(score_panels, cov_matrix)` — allocate 1/n risk (not 1/n dollar) across factors.

### Wave 3 (iter 9-11): Gate calibration audit under pre-registration

**Operator approval required before starting — this is a potential one-way door.** The goal is to produce a pre-registered `correction` event that, if approved, would adjust any threshold that was mis-transcribed from the plan. Procedure:

- **iter-9: write the audit memo.** `docs/templates/factor_screen_memo.md` → instantiate per-gate at `docs/audit/gate_calibration_audit.md`. For each gate threshold in `config/gates.yaml`, state the plan's original value (from `/.claude/plans/dreamy-riding-quasar.md`), the config value, the difference (if any), and the commit that introduced the discrepancy.
- **iter-10: present findings.** If any threshold was transcribed incorrectly (e.g., "0.02" vs "0.5"), present the discrepancy to the operator. Do not change any threshold. This iteration writes a research-log event with the findings and halts pending operator authorization.
- **iter-11 (conditional, one-way door).** Only proceeds if the operator has authorized the specific `correction` event. Applies the threshold correction, re-runs all 6 factor screens against the corrected threshold, and records the new verdicts.

### Wave 4 (iter 12-15): Multi-factor admission reform

**Operator approval required before iter-13 — also a potential one-way door.** Current admission is per-factor. Ensembles may have non-additive gate properties (a factor that fails G0 alone may pass in an ensemble). The reform:

- **iter-12: simulate ensemble G0.** Given all 6 factor panels, compute the equal-weight ensemble long-short Sharpe. This is diagnostic — no admission decision.
- **iter-13: ensemble Romano-Wolf (one-way door).** Re-compute Romano-Wolf adjusted p-values over a family including ensemble candidates. Pre-register the family before computing. If operator approves the reform, the ensemble G3 metric becomes primary.
- **iter-14: G2 redundancy under ensemble.** Re-evaluate G2 (max_corr_with_existing) for each factor against the **ensemble** rather than pairwise.
- **iter-15: admission retrospective.** If any factor previously rejected by G0 passes under ensemble G0, log the finding but **do not auto-admit** — admission still requires a fresh pre-registered correction.

### Wave 5 (iter 16-20): Regime conditioning + final

- **iter-16: regime panel.** `compute_regime_panel(benchmark_series, method="sma_200")` — per-date BULL/BEAR label. Pure helper.
- **iter-17: regime-conditional IC.** `compute_ic_by_regime(factor_scores, fwd_returns, regime_panel)` — diagnostic only.
- **iter-18: regime-conditional factor rescreens.** Re-run all 6 factors split by regime. If any factor passes G0-G5 **within** a regime, log the finding — the admission decision is reserved for iter-20.
- **iter-19: regime overlay audit.** Verify `src/nyse_core/risk.py` regime overlay matches `strategy_params.yaml` (`bear_exposure: 0.4`, `bull_exposure: 1.0`). No threshold changes.
- **iter-20: final synthesis.** Single research-log event summarizing the 20-iter loop: what shipped, what the ensemble G0 would be, which factors (if any) pass under regime conditioning, what pre-registered corrections the operator should consider. **No admission decisions taken in iter-20.**

Escalate to iter 21-40 only for operator-authorized `correction` events arising from the waves above.

## Per-Iteration Workflow

1. **Read state.** Re-read the most recent entries of `results/research_log.jsonl` to confirm the chain tip and which iteration is next. Re-read `docs/NYSE_ALPHA_RESEARCH_RECORD.md` §Eighth Action.
2. **Check the iron rules.** If the planned iteration touches any threshold, admission verdict, factor sign, gate definition, or holdout artifact → **halt and ask the operator**. Otherwise proceed.
3. **Write a short plan.** One paragraph, in chat (not in a file). Name the pure helper, the test cases, the persistence hook in `screen_factor.py` (if any), and the AP-6 guarantee ("diagnostic only — no gate / threshold / admission change").
4. **Implement.** `src/nyse_core/` for pure helpers, `tests/unit/` for tests, `scripts/screen_factor.py` for persistence wiring. No working files in repo root.
5. **Test targeted.** Run the new tests first to confirm shape. Then run the targeted slice of the full suite (`pytest tests/unit/test_<new>.py tests/unit/test_factor_screening.py tests/unit/test_benchmark_construction.py -x`).
6. **Test full.** `pytest tests/ -x --timeout=300` (background with `run_in_background: true` while other work proceeds). Expect 1 pre-existing `test_optimizer::test_ap7_warning_fires` timeout on some runs — it reproduces on base iter-2 commit `9a9378c` and is unrelated to this loop.
7. **mypy and ruff.** `python3 -m mypy <new files>` and `python3 -m ruff check <new files> && python3 -m ruff format --check <new files>`. Fix until green.
8. **Append research log.** Build an event JSON with `event`, `iteration`, `wave`, `artifacts`, `summary`, `ap6_verdict`, `tests_added`, `tests_total_pass`, `iron_rule_compliance` object. Write to `/tmp/iterN_event.json`, then `python3 scripts/append_research_log.py --event-file /tmp/iterN_event.json`. Verify with `python3 scripts/verify_research_log.py`.
9. **Commit.** `git add` named files (never `-A` / `.`). Conventional-commit message: `research(iter-N): <scope> (AP-6-safe, diagnostic only)`. All six pre-commit hooks must pass. Never `--no-verify`.
10. **Update the research record.** Once per wave (not per iteration), append a `####` subsection under §Eighth Action in `docs/NYSE_ALPHA_RESEARCH_RECORD.md` summarizing the wave's iterations with commit hashes and log chain tips. Regenerate `docs/FRAMEWORK_AND_PIPELINE.pdf` via `scripts/regen_framework_pdf.sh` on the same day the doc is updated.

## Completion Criteria

All must be true in the same iteration before emitting the completion promise.

1. `results/research_log.jsonl` has chained iterations 0 through 20 (or the operator-authorized extension). `python3 scripts/verify_research_log.py` passes end-to-end.
2. Each iteration's `artifacts` list in the log points to files that exist at the listed paths in the git history of the branch.
3. `config/gates.yaml`, `config/falsification_triggers.yaml`, `config/strategy_params.yaml`, and the factor-sign conventions in `src/nyse_core/features/registry.py` have the **same values as they had at the iter-0 commit `c6d6be4`** — unless an explicit `correction` event is logged with operator approval and a pre-registration diff.
4. Holdout lockfile `results/holdout/.holdout_used` does not exist. `research.duckdb` has `MAX(date) ≤ 2023-12-31`.
5. `docs/NYSE_ALPHA_RESEARCH_RECORD.md` has subsections for each shipped wave with commit hashes and log chain tips.
6. `docs/FRAMEWORK_AND_PIPELINE.pdf` regenerated within the past 7 days via `scripts/regen_framework_pdf.sh`.
7. Full pytest suite passes (`test_optimizer::test_ap7_warning_fires` pre-existing timeout excluded from the pass requirement — this is the only known exception, documented in the iter-3 log entry).
8. mypy and ruff both exit zero on the entire repo.
9. No `--no-verify` commit in `git log` since iter-0.
10. TODO-11 and TODO-23 remain in their state at the start of the loop.

Only when every check passes in the same commit, emit: **ALL WAVES SHIPPED; 20-ITER RESEARCH LOOP COMPLETE; NO ADMISSION CHANGES TAKEN**.

If stuck, append a diagnostic `blocked_on` event to the research log explaining the obstacle, then continue to the next iteration. A false completion promise is an iron-rule violation.
