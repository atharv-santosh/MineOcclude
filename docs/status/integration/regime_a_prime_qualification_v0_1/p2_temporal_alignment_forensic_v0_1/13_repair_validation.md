# 13 — Repair Validation

**Label: EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY.**

## Test suite
```
cd /home/sagemaker-user/MineOcclude && python3 -m pytest tests/prospective/ -q
```
**196 passed.** All deterministic (fixed seeds where randomness is used); no capture or Minecraft.
The separate existing-data Regime A refit used the GPU and read only receipt-hashed persisted
objects.

| File | Tests | Covers |
|---|---|---|
The suite covers strict clock/domain typing; caller-adjudicated temporal evidence;
policy-separated visibility; strict detection values and D-10 joins; physical support gaps and
invalid observations; every path/state/camera/index invariant; explicit cohort identity; all
tree/index/work provenance divergences; and focused temporal/Regime A forensic receipts.
Bounded repair #2 adds executable-mode provenance, strict authority schema,
in-support sample counting, physical tick-spacing/mapping, and visibility
contradiction/explicit-primary regressions; see `20_bounded_repair_2.md`.

## Negative-control tests that matter most

1. **`test_spread_kernel_is_measured_and_strict_pure_delay_requirement_fails`** — the estimator must not
   silently report a smoothing response as a delay. This is the property that let this audit
   falsify the prior "≈3.3-tick pure delay" model.
2. **`test_precision_moves_with_prevalence_while_error_rate_is_fixed`** — reproduces D-05 exactly:
   identical detector, three class balances, precision rises 0.85 → 0.94 while FPR is unchanged
   to within 1e-9.
3. **`test_file_only_staged_and_absent_from_expected_head_fails`** and the clean-worktree staged
   edit test reproduce D-08's independent-review attack.
4. **`test_one_run_id_may_not_span_multiple_cohort_tiers`** — reproduces D-07 with the actual
   historical identity string.
5. **Twenty-five parametrised path/state mutations** include yaw, pitch, FOV, render frame,
   action index, and server tick.
6. **`test_short_last_seen_comparison_materially_flips_when_target_is_fixed`** locks the direct
   R7 result and rejects a return to the quadrature-bound argument.

## Independent validation of the P2 recomputation harness
`audit_scripts/b05_p2_corrected_metrics.py` imports `best_k_readout`, `full_readout` and
`summarize` **verbatim** from the frozen `p2e_analyze`, changing only the label vector. Running it
under `MODEL A (historical pairing)` reproduces the frozen P2 result **exactly**:

| Metric | Frozen historical | Recomputed MODEL A |
|---|---|---|
| BEST-K RMSE | 0.1660274234445584 | **0.166027** |
| BEST-K MAE | 0.13315757524309618 | **0.133158** |
| BEST-K macro R² | 0.7906954002303574 | **0.790695** |
| BEST-K bootstrap 95 % | [0.7238731, 0.8472415] | **[0.7239, 0.8472]** |
| FULL RMSE | 0.16657677302324672 | **0.166577** |
| FULL macro R² | 0.7548030087626074 | **0.754803** |

Every subsequent model differs from this baseline **only** in the label alignment.

## Adversarial control on the corrected metrics
`audit_scripts/b06_label_variance_control.py` tests whether MODEL B's lower RMSE is a trivial
variance artifact of using a smoothed label. **It is not:**

| Model | mean within-trajectory label SD | ratio vs historical |
|---|---|---|
| A_historical | 0.39773 | 1.0000× |
| B_kernel_convolved | 0.41687 | **1.0481×** |
| B2_point_group_delay | 0.41836 | 1.0519× |
| C_int3 (pure shift, no smoothing) | 0.41607 | 1.0461× |
| D_int4 (pure shift, no smoothing) | 0.42417 | 1.0665× |

The corrected labels are **slightly harder** (more within-trajectory variance), not easier.
Normalised error still falls from 0.4174 to 0.1866. The pure integer-shift models apply no
smoothing at all, so they isolate alignment from variance entirely.
