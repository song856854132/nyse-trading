# NYSE ATS Code Review & Audit Checklist

Systematic review process to catch bugs before they reach production.
Run after every significant code change — especially before merging to main.

---

## 1. Contract Compliance Audit

Every `nyse_core/` public function must return `(result, Diagnostics)`.

```bash
# Find functions that might violate the tuple contract
grep -rn 'def ' src/nyse_core/ --include='*.py' | grep -v '__' | grep -v '_SRC'
```

**Check:**
- [ ] All public functions return `(result, Diagnostics)` tuples
- [ ] All callers unpack tuples correctly: `result, diag = func(...)`
- [ ] No bare `func(...)` calls that ignore the Diagnostics

---

## 2. Protocol Compliance Audit

CombinationModel protocol: `fit() -> predict() -> get_feature_importance()`

**Check:**
- [ ] `model.fit(X, y)` called BEFORE `model.predict(X)` in every code path
- [ ] Factory function `create_model()` returns `(model, Diagnostics)` tuple
- [ ] All model implementations satisfy the Protocol interface
- [ ] Fallback path exists when `fit()` fails (feature-mean scoring)

---

## 3. API Surface Verification

Scripts and wiring code must use the actual class APIs, not imagined ones.

**Check:**
- [ ] `VendorRegistry.from_config(config)` — NOT `VendorRegistry(config)`
- [ ] `registry.get("finmind")` — NOT `registry.get_ohlcv_adapter()`
- [ ] `FactorRegistry()` + `register_all_factors(registry)` wired in scripts
- [ ] `NautilusBridge(mode=...)` constructed with correct mode string

```bash
# Verify no phantom method calls exist
grep -rn 'get_ohlcv_adapter\|get_fundamentals_adapter\|get_short_interest_adapter' scripts/ src/
```

---

## 4. Weight-to-Shares Conversion Audit

Portfolio must convert abstract weights to concrete share counts.

**Check:**
- [ ] `target_shares` > 0 for BUY orders (not hardcoded 0)
- [ ] `current_shares` > 0 for SELL orders (not hardcoded 0)
- [ ] `notional` and `prices` config keys flow through to `build_portfolio`
- [ ] Division by zero guarded (`if price > 0`)

---

## 5. Data Path Coverage

All four data paths must be tested end-to-end:

| Path | Condition | Expected Behavior |
|------|-----------|-------------------|
| HAPPY | All features present | Generate TradePlan |
| NIL | >20% missing | HOLD, zero trades, warning |
| EMPTY | All NaN / empty DF | Skip rebalance, NO sell orders |
| ERROR | >50% missing | Skip, error diagnostic |

**Check:**
- [ ] Unit test for each path in `test_pipeline.py`
- [ ] EMPTY path explicitly asserts zero SELL orders
- [ ] NIL path has `skipped_reason == "nil_universe"`
- [ ] ERROR path has `diag.has_errors == True`

---

## 6. Storage Fallback Audit

Backtest must load data from storage when not passed directly.

**Check:**
- [ ] `run_backtest()` tries `self._storage.load_features()` when args are None
- [ ] Storage failure produces error diagnostic, not exception
- [ ] Empty result returned gracefully on total failure

---

## 7. Test Mock Fidelity

Mocks must match the actual API they replace.

**Check:**
- [ ] `mock_create_model.return_value = (model, Diagnostics())` — tuple, not bare model
- [ ] `mock_registry.get.return_value = adapter` — matches `.get()` not `.get_*_adapter()`
- [ ] `mock_adapter.fetch.return_value = (df, Diagnostics())` — tuple return
- [ ] Mock `VendorRegistry` uses `from_config` classmethod, not constructor

```bash
# Scan for mock return values that might not match real signatures
grep -rn 'return_value\s*=' tests/ --include='*.py' | grep -i 'vendor\|model\|adapter\|registry'
```

---

## 8. Script Wiring Completeness

Every script in `scripts/` must properly wire its dependencies.

| Script | Required Wiring |
|--------|----------------|
| `run_paper_trade.py` | VendorRegistry + FactorRegistry + NautilusBridge(paper) |
| `run_live_trade.py` | VendorRegistry + FactorRegistry + FalsificationMonitor + NautilusBridge(live) |
| `download_data.py` | VendorRegistry.from_config() + ResearchStore |
| `run_backtest.py` | ResearchStore + TradingPipeline |

**Check:**
- [ ] Every script uses `from_config()` for VendorRegistry
- [ ] Every script that touches factors wires `FactorRegistry` + `register_all_factors`
- [ ] Every script closes resources (`store.close()`, `live_store.close()`)

---

## 9. Full Test Gate

Run before merge. All must pass.

```bash
# Unit + integration + property tests
python3 -m pytest tests/ -v --tb=short

# Type checking
mypy src/ --ignore-missing-imports

# Linting
ruff check src/ scripts/ tests/
```

**Gate criteria:**
- [ ] 0 test failures
- [ ] 0 type errors (mypy)
- [ ] 0 lint violations (ruff)
- [ ] Coverage >= 90% on changed files

---

## 10. Parallel Audit Agent Protocol

For major changes, spawn 3 parallel audit agents:

1. **Execution Path Agent** — Trace every code path for correctness
2. **Test Coverage Agent** — Verify tests exist for every new/changed behavior
3. **Script/Wiring Agent** — Verify all scripts use correct APIs

Each agent independently reviews and reports findings. Cross-reference results
to catch issues that one reviewer might miss.

---

## Quick Pre-Merge Smoke Test

```bash
# 1. Run affected module tests
python3 -m pytest tests/unit/test_<changed_module>.py -v

# 2. Run integration tests
python3 -m pytest tests/integration/ -v

# 3. Run property tests
python3 -m pytest tests/property/ -v

# 4. Full suite (background)
python3 -m pytest tests/ --tb=short
```
