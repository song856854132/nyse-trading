# Ralph Loop Task: Close P1 and P2 Gaps

You are closing the remaining plan-eng-review gaps for the NYSE ATS framework. The canonical gap list lives at docs/TODOS.md. Read it at the start of every iteration. The plan lives at /home/song856854132/.claude/plans/dreamy-riding-quasar.md. Never use ralph-loop as an excuse to skip a gate, skip a test, or touch holdout data.

## Iron Rules. Violating any is an immediate halt.

1. Never read, query, or backtest any date after 2023-12-31. Holdout is 2024-2025 and is off-limits.
2. Never change a threshold after seeing a result. AP-6 is absolute. Gate thresholds, F-trigger thresholds, abandonment criteria are frozen.
3. Never mock the database in integration tests. Prior incident, zero tolerance.
4. Never commit secrets. Never print API tokens. FinMind adapter must use header auth and redact query strings in every error path.
5. Never skip pre-commit or CI hooks with no-verify. If a hook fails, fix the root cause.
6. Every research artifact must be appended to results/research_log.jsonl with SHA-256 hash chaining. If the chain breaks, halt and repair.
7. All 6 factors screened so far (ivol_20d, piotroski, earnings_surprise, high_52w, momentum_2_12, short_ratio) have FAILED on real data. Do not touch TODO-11 factor screening or TODO-23 paper-trade in this loop. The strategy is in research, not pre-deployment.

## Priority Order

Each iteration picks the next unfinished P1 item, then P2, then P0-research. Do not skip ahead.

### P1 Infrastructure Gaps (close first)

- **TODO-3**: add a GitHub Actions workflow at .github/workflows/ci.yml that runs pytest, ruff, mypy, and a secret scan (gitleaks or trufflehog). Matrix Python 3.11 and 3.12. Cache pip. Fail on any ruff, mypy, or secret-scan violation.
- **TODO-4**: add .pre-commit-config.yaml with ruff, ruff-format, mypy, gitleaks, and a guard hook that rejects any commit touching results/holdout or any file under 2024 or 2025 dated paths. Document installation in docs/REPRODUCIBILITY.md.
- **TODO-5**: generate uv.lock via uv lock. Commit it. Update docs/REPRODUCIBILITY.md with the exact uv sync command plus python version pin. No poetry.
- **TODO-6**: write tests/property/test_no_holdout_leakage.py using Hypothesis. Property: for every function in nyse_core that accepts a date range, feeding any date strictly greater than 2023-12-31 raises HoldoutLeakageError. Add that exception type to nyse_core.contracts. Also scan research.duckdb at test time and assert MAX(date) is 2023-12-31 or earlier.
- **TODO-7**: write tests/integration/test_research_log_chain.py that reads results/research_log.jsonl end to end, recomputes each entry SHA-256 from the previous entry hash plus the canonical JSON body, and asserts the chain is unbroken. Break detection must print the first broken index.
- **TODO-8**: refactor src/nyse_ats/pipeline.py so it imports one normalization helper from nyse_core.normalize rather than calling winsorize and rank_percentile separately. Add a single entry point named normalize_cross_section that returns the rank-percentile result plus Diagnostics. Delete the duplicated call path. Update unit tests.

### P2 Governance Gaps (after all P1 items are green in CI)

- **TODO-14**: create docs/RISK_REGISTER.md with rows for every F1 through F8 trigger plus A1 through A12 abandonment criteria. Each row: ID, description, current value, threshold, data source, owner, last review date. Freeze the current numeric thresholds. Do not edit them.
- **TODO-15**: create docs/DATA_DICTIONARY.md. One section per source: FinMind OHLCV, EDGAR fundamentals, FINRA short interest, S&P 500 constituency. Each section lists field name, type, unit, publication lag, vendor SLA, PiT rule, known gotchas.
- **TODO-16**: create docs/REPRODUCIBILITY.md. Contents: exact uv sync command, python pin, duckdb version, how to rebuild research.duckdb from raw vendor pulls, how to verify the research-log hash chain, how to rerun the 6 completed factor screens end to end.
- **TODO-17**: create docs/GOVERNANCE_LOG.md. Append-only markdown. First entry: today, 2026-04-18, records that ivol_20d, piotroski, earnings_surprise, high_52w, momentum_2_12, short_ratio have all FAILED G0 through G5 on real data. Note that the strategy remains in research.
- **TODO-18**: create docs/EXECUTIVE_SUMMARY_NONQUANT.md. One page. Plain English. Current state: 6 of 6 factors failed; strategy in research; no live capital. Next milestones. Who to contact.
- **TODO-19**: create docs/vendors/finmind.md, docs/vendors/edgar.md, docs/vendors/finra.md. Each vendor doc lists: endpoint, rate limits, auth method, PiT publication lag, known outages, escalation contact.
- **TODO-20**: create docs/templates/factor_screen_memo.md. Template with sections: hypothesis, data window, G0-G5 verdict, permutation p, Romano-Wolf adjusted p, bootstrap CI, decision.
- **TODO-21**: update docs/FRAMEWORK_AND_PIPELINE.md to reflect the 6-for-6 failure state and the closure of all 3 critical failure modes from the 2026-04-18 review. Regenerate the PDF by running the script at scripts/regen_framework_pdf.sh. If that script does not exist, iteration 1 must create it. The script must call md-to-pdf on docs/FRAMEWORK_AND_PIPELINE.md with Puppeteer launch args no-sandbox, disable-setuid-sandbox, and disable-dev-shm-usage. Put the args inside a Puppeteer config file at config/puppeteer.config.js and have md-to-pdf read that config rather than passing JSON on the command line.
- **TODO-22**: update docs/OUTCOME_VS_FORECAST.md with a row per failed factor screen documenting predicted Sharpe range versus realized Sharpe.

### P0 Supporting Research Tasks (only after P1 and P2 are green)

- **TODO-9**: add RSP equal-weight benchmark alongside SPY in src/nyse_core/backtest.py. Report both in every backtest artifact. Do not change the regime overlay benchmark which stays on SPY.
- **TODO-10**: add a post-screen check that warns if any price-volume factor receives a negative Ridge weight on real data. Print a WARNING with the factor name and the fitted coefficient. Do not auto-flip signs.
- **TODO-12**: add tests/property/test_pit_no_leakage.py covering every feature compute function. Property: feature value at date t depends only on inputs strictly before t plus publication lag.
- **TODO-25 through TODO-29**: pick up only after P1 and P2 are fully green. Read the TODO file for details.

## Per-Iteration Workflow

1. Read docs/TODOS.md. Pick the lowest-numbered unfinished P1 item. If all P1 done, pick lowest-numbered unfinished P2. If all P2 done, move to P0.
2. Write a short plan in plain prose. One paragraph. No files touched yet.
3. Implement. Respect file-organization rules. Source under src. Tests under tests. Docs under docs. Config under config. Scripts under scripts. No working files in repo root.
4. Run the full test suite with pytest. Fix until green. No xfail, no skip, no mock on the database path.
5. Run ruff check and mypy. Fix until green.
6. If the change is research-relevant, append a new entry to results/research_log.jsonl using the append helper. The helper recomputes the SHA-256 chain. If the helper does not exist, iteration 1 must create it at scripts/append_research_log.py. Never hand-edit research_log.jsonl.
7. Update docs/TODOS.md. Mark the item CLOSED with a one-line evidence reference pointing at the exact file plus line range that closes it.
8. Commit with a clear conventional-commit message. Do not skip pre-commit.
9. Re-read docs/TODOS.md to confirm the remaining gap list shrank by exactly one.

## Completion Criteria

All of the following must be true, verified in the same iteration, before you emit the completion promise.

1. TODO-3 through TODO-8 all marked CLOSED in docs/TODOS.md with file-plus-line evidence.
2. TODO-14 through TODO-22 all marked CLOSED with file-plus-line evidence.
3. GitHub Actions CI on the current branch is green. Verify by reading the latest workflow run status.
4. Pre-commit passes on a freshly staged no-op file.
5. Pytest exits zero with zero skipped, zero xfailed, and includes the new holdout-leakage property test plus the research-log chain test plus the PiT-no-leakage property test for all features that exist today.
6. Ruff and mypy both exit zero.
7. results/research_log.jsonl hash chain verifies end to end. The chain-verification test passes.
8. docs/FRAMEWORK_AND_PIPELINE.pdf has been regenerated today via scripts/regen_framework_pdf.sh and committed.
9. docs/RISK_REGISTER.md, docs/DATA_DICTIONARY.md, docs/REPRODUCIBILITY.md, docs/GOVERNANCE_LOG.md, docs/EXECUTIVE_SUMMARY_NONQUANT.md all exist and contain real content, not placeholders.
10. No file under results/holdout exists. No code path can reach dates after 2023-12-31.
11. TODO-11 and TODO-23 remain in their current DEFERRED or IN-PROGRESS state. You did not touch them.

Only when every one of those eleven checks is true in the same commit, emit the exact phrase: ALL P1 AND P2 GAPS CLOSED AND CONSOLIDATED

If you are stuck, write a diagnostic note to docs/TODOS.md explaining what blocks you, then continue to the next item. Do not emit the completion promise under any circumstances other than the full eleven-check pass. A false completion promise is a violation of the iron rules.
