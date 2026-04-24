# iter-14 Stream 5 — Sign-Flip Diagnostic on `ivol_20d` and `high_52w`

> **Stream ID:** `iter14_stream5_sign_flip`
> **Charter ref:** `docs/audit/wave_d_diagnostic_charter.md` §2 Stream 5
> **AP-6 posture:** observational single-factor diagnostic under the in-force
> gate family. No threshold, direction, metric, or admission decision is
> modified. The canonical admission records at
> `results/factors/ivol_20d/gate_results.json` and
> `results/factors/high_52w/gate_results.json` are **unchanged**; this
> stream produces *variant* re-screens at a separate path for comparison.
> **Source artefact:** `results/diagnostics/iter14_sign_flip/sign_flip_diagnostic.json`

## 1. What this stream measures

Re-screen `ivol_20d` and `high_52w` under the in-force gate family (G0–G5),
but first invert the rank-percentile score:

```
for each date d, symbol s:
    flipped_score(d, s) = 1 - original_score(d, s)
screen_factor(factor_name=<factor>, factor_scores=flipped_score, ...)
```

This is a direct test of the single hypothesis: "were the two failing
low-Sharpe factors originally scored with the wrong sign convention?"
The per-factor registration is unchanged, and no other factor in the
6-panel is flipped.

## 2. Panel-level diagnostic

| Factor | Status |
|---|---|
| `ivol_20d` | panel re-screened with inverted score |
| `high_52w` | panel **not** re-screened — registry did not produce a score panel for this factor name |

The `high_52w` skip is deliberate and documented: the Wave D charter's
Stream 5 is scoped to "factors whose score panel is reproducible from the
registry"; since the registry does not currently emit a `high_52w` panel
under that exact name (the registered function is `52w_high_proximity`),
the orchestrator records the skip rather than silently re-mapping names.

## 3. In-force gate metrics, sign-flipped vs raw (`ivol_20d`)

Raw metrics come from `results/factors/ivol_20d/gate_results.json`
(the canonical screening record). Sign-flipped metrics come from this
stream's JSON artefact.

| Metric | Raw (`gate_results.json`) | Sign-flipped | Direction of change |
|---|---|---|---|
| G0 OOS Sharpe | **−1.9156** | **+1.9220** | flipped sign (as expected) |
| G1 perm p | 1.000 | 0.00200 | ↓ (now significant) |
| G2 IC mean | −0.00791 | +0.00791 | flipped sign (as expected) |
| G3 IC IR | −0.05451 | +0.05451 | flipped sign (as expected) |
| G4 max drawdown | −0.5777 | −0.1325 | ↑ (reduced by 77%) |
| G5 marginal contribution | 1.00 | 1.00 | unchanged (single-factor screen) |
| `verdict_passed_all` | false (canonical) | false | unchanged |

## 4. Observational implications (not admission decisions)

1. **The raw `ivol_20d` was registered with the inverse of the economically
   expected sign.** A sign-flipped rank-percentile produces an OOS Sharpe
   of +1.92 versus the raw −1.92. The G1 permutation p-value moves from
   degenerate (p = 1.000) to highly significant (p = 0.002). This is
   consistent with the well-documented low-volatility anomaly (Baker et
   al. 2011, Frazzini-Pedersen 2014): high idiosyncratic volatility
   predicts **negative** forward excess returns, so a BUY signal should
   correspond to **low** ivol, i.e. `1 - rank_percentile(ivol)`.
2. **Sign-flipped ivol still fails G2 and G3.** IC mean flips from
   −0.0079 to +0.0079; IC IR flips from −0.055 to +0.055. Both remain
   well below G2 (≥0.02) and G3 (≥0.50). A sign correction alone does
   **not** admit ivol under the in-force family.
3. **Sign-flipped ivol passes G0, G1, G4, G5.** Only G2 and G3 fail.
   This is the same near-miss pattern observed for `momentum_2_12` and
   `profitability` in Stream 1 — the in-force gate family is effectively
   binding on IC-based criteria even when Sharpe, significance, and
   drawdown are comfortably in range.
4. **`high_52w` sign convention remains unmeasured by this iteration.**
   The charter explicitly scoped Stream 5 to factors whose score panel
   the registry emits under the exact failing name. iter-15 or iter-16
   may widen the diagnostic; iter-14 does not.

## 5. What this stream does NOT establish

- This stream does **not** change the registration of `ivol_20d` to flip
  its sign. The canonical gate_results file is unchanged. A registration
  change is a code-surface admission decision and is outside Wave D
  diagnostic scope.
- This stream does **not** propose sign-convention auditing as a
  construction-grammar feature. iter-15 will make that decision explicitly
  as part of its pre-registration event.
- The `high_52w` skip is **not** evidence for or against its sign; it is
  an observational gap that iter-15 or iter-16 may close by either
  registering a panel-emitting function or by running the diagnostic
  against the existing `52w_high_proximity` panel.
