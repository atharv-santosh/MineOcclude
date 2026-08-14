# MineOcclude Regime A first25 scientific report

## A5_QUALITY_GATE

- Final authority binding: PASS; no conflicting canonical authority.
- Scientific identities: 25; `COMPLETE_VALIDATED_DURABLE`: 25; replacements/substitutions: 0.
- Split: five grouped outer folds of five trajectories; every trajectory held out exactly once; direction balance 13 LTR / 12 RTL.
- Eligible rows: SHORT 100, INTERMEDIATE 100, LONG 100, NEAR_CONTEXT 75, BEYOND_CONTEXT 100; total 475.
- Visibility: all target rows `OCCLUDED_AGREEMENT`; largest observed entry/exit transition runs 13/10 frames and every trajectory passes its final amended directional guard.
- Primary tau1..15 TSS: all positive (minimum 0.574819, maximum 3.091573).
- Confound, fold support, duplicate/near-duplicate, context revalidation, amendment replay, and donor feasibility receipts: PASS.
- Null donor manifest: 49 valid direction-stratified, no-self, outer-training-only mappings in each outer fold.
- Activation metadata: 20 layers per trajectory, `[19,336,2048]`, float16, exact frame/target alignment and durable hash binding.
- A5 state: PASS; `SCIENTIFIC_OUTCOME_OPENING_AUTHORIZED=YES`.

## PRIMARY_LAYER4_FULL

- Target: signed wall-parallel sheep world x, blocks.
- Representation: fixed layer 4 `FULL_TOKEN_GRID`; 688,128 features; training-only standardization and nested grouped alpha selection.
- Evaluation: 25 trajectories, 375 primary OOF rows (tau 1..15); predictions also preserved for 100 beyond-context rows.
- Equal-trajectory macro R²: **-1.228906**.
- Pooled-row R² (secondary only): 0.987131. This large contrast is why pooled rows cannot replace the frozen trajectory-equal statistic.
- Trajectory-aggregated RMSE: 0.417009 blocks; MAE: 0.338974 blocks.
- 10,000-trajectory bootstrap 95% interval for macro R²: [-2.165028, -0.465052].
- Outer-fold macro R² / RMSE / MAE:
  - fold 0: -0.560610 / 0.391311 / 0.323027
  - fold 1: -1.918276 / 0.462933 / 0.361167
  - fold 2: -0.281060 / 0.393841 / 0.335355
  - fold 3: -0.575388 / 0.357214 / 0.296825
  - fold 4: -2.809198 / 0.479747 / 0.378497
- Relative to the frozen R² > 0 component: FAIL.

## DURATION_RESULTS

The same OOF predictions were reused for every bin; no bin-specific fit, alpha, token, or layer selection occurred.

| Bin | Macro R² | RMSE blocks | MAE blocks |
|---|---:|---:|---:|
| SHORT | -102.253949 | 0.466692 | 0.395565 |
| INTERMEDIATE | -37.814900 | 0.385943 | 0.345484 |
| LONG | -97.388308 | 0.328243 | 0.291949 |
| NEAR_CONTEXT | -255.832039 | 0.361839 | 0.317540 |
| BEYOND_CONTEXT | -2862.797186 | 3.078303 | 3.011091 |

Absolute error decreases through LONG, rises modestly at NEAR_CONTEXT, and rises sharply beyond context. The single descriptive absolute-error trend is +0.138432 blocks per tau. The very negative per-bin R² values reflect small within-trajectory TSS over 3–4 rows and are reported continuously; no monotonicity rule was imposed.

## KINEMATIC_BASELINES

Overall primary-domain macro R² / trajectory-aggregated RMSE / MAE:

| Baseline | Macro R² | RMSE blocks | MAE blocks |
|---|---:|---:|---:|
| LAST_VISIBLE_POSITION | -23.204355 | 1.543380 | 1.508140 |
| CONSTANT_VELOCITY_EXTRAPOLATION | -0.183330 | 0.318421 | 0.300645 |
| TRAINING_MEAN (direction × duration-bin stratified) | 0.452178 | 0.204002 | 0.177346 |
| TIME_ONLY_LINEAR confound diagnostic | 0.504910 | 0.184947 | 0.166074 |

Per-bin macro R² / RMSE / MAE:

| Baseline | SHORT | INTERMEDIATE | LONG | NEAR_CONTEXT | BEYOND_CONTEXT |
|---|---|---|---|---|---|
| LAST_VISIBLE | -423.670 / 1.096 / 1.092 | -417.566 / 1.407 / 1.404 | -633.358 / 1.708 / 1.705 | -3696.534 / 1.940 / 1.939 | -1048.882 / 2.169 / 2.167 |
| CONSTANT_VELOCITY | -27.425 / 0.225 / 0.220 | -16.416 / 0.285 / 0.280 | -35.693 / 0.344 / 0.340 | -255.186 / 0.386 / 0.383 | -45.889 / 0.421 / 0.417 |
| TRAINING_MEAN | -9.431 / 0.147 / 0.128 | -6.453 / 0.182 / 0.164 | -20.213 / 0.226 / 0.207 | -130.057 / 0.227 / 0.221 | -16.429 / 0.253 / 0.238 |

There was no frozen neural-versus-kinematic inferential gate. Descriptively, FULL underperforms constant velocity, training mean, and the continuous time-only diagnostic on the primary macro statistic. The positive time-only/training-mean results reinforce that pooled direction/time structure is strong, while the fixed neural readout does not recover trajectory-specific variation under the primary metric.

## BEST_K_LAYER4

- Authority: exact frozen A2 absolute max-hidden-dimension correlation ranking, recomputed within each training-only inner fold; K candidates 1, 4, 8, 16, 32, 64, 128.
- Every outer fold selected K=8 and alpha=100.
- Selected token sets:
  - fold 0: 327, 326, 323, 301, 325, 241, 324, 333
  - fold 1: 326, 327, 323, 325, 301, 324, 241, 333
  - fold 2: 327, 326, 323, 301, 324, 325, 241, 333
  - fold 3: 327, 326, 323, 301, 241, 325, 324, 299
  - fold 4: 327, 323, 326, 301, 73, 325, 324, 333
- Pairwise token-set Jaccard range: 0.600–1.000.
- Overall macro R²: -0.509944; improvement over FULL: +0.718963 R², but still below zero.
- Bin macro R²: SHORT -88.666768; INTERMEDIATE -17.703903; LONG -85.325270; NEAR_CONTEXT -215.892098; BEYOND_CONTEXT -3203.573891.
- Role: secondary only; it does not rescue the failed FULL gate.

## SECONDARY_SCREEN_TOKEN_TARGET

- Layer-4 FULL joint row/column macro R²: -1.252891.
- Component macro R²: token row -1.252891; token column -1.252891.
- Trajectory-aggregated Euclidean RMSE: 0.337602 continuous token cells; Euclidean MAE: 0.274051 token cells.
- Bin joint R² / Euclidean RMSE / Euclidean MAE:
  - SHORT: -103.897528 / 0.378745 / 0.320809
  - INTERMEDIATE: -38.119575 / 0.311384 / 0.278411
  - LONG: -100.080916 / 0.265669 / 0.236133
  - NEAR_CONTEXT: -256.775303 / 0.292589 / 0.256450
  - BEYOND_CONTEXT: -2969.840124 / 2.501078 / 2.446439
- Role: secondary only; it cannot rescue the primary world-coordinate gate.

## ALL_LAYER_FULL_PROFILE

The profile is descriptive, correlated, and non-confirmatory. Macro R² by layer 0..19:

`[-0.479854, -0.849749, -0.749396, -0.876221, -1.228906, -1.568969, -1.469209, -1.678407, -2.054196, -2.086882, -0.761864, -0.701110, -0.754020, -0.771130, -0.782763, -0.865964, -0.837391, -1.084403, -1.059229, -1.050461]`

Layer 0 is descriptively best at -0.479854; fixed primary layer 4 is -1.228906. No layer achieved positive macro R², and no layer reselection occurred.

## TARGET_SPECIFIC_NULL

- B: 49 whole-trajectory, direction-stratified donor mappings.
- Observed statistic: -1.228906.
- Null min / median / max: -1.584266 / -0.943644 / -0.604058.
- Count null ≥ observed: 44.
- Empirical one-sided p: **0.90**.
- p ≤ 0.05: NO.

## BOOTSTRAP

- Replicates: 10,000.
- Resampling unit: whole held-out trajectory.
- Primary macro-R² 95% percentile interval: [-2.165028, -0.465052].
- Primary RMSE interval: [0.363882, 0.474337] blocks; MAE interval: [0.293148, 0.388393] blocks.
- Per-bin intervals are preserved in `slice_bootstrap_results.json`.
- Bootstrap was not used as a hard gate.

## CONTINUATION_GATE

- A5 quality PASS: YES.
- All primary TSS > 0: YES.
- Primary layer-4 FULL macro R² > 0: NO.
- B49 p ≤ 0.05: NO.
- Bootstrap used as hard gate: NO.
- BEST-K used to rescue gate: NO.
- Secondary target used to rescue gate: NO.

## SCIENTIFIC_ADJUDICATION

Exact state: `FAIL_NO_DEFENSIBLE_DECODING`.

The primary claim—that the approved sheep world position is linearly decodable from fixed layer-4 FULL MineWorld activations during genuine occlusion under this regime and trajectory-equal held-out evaluation—is not supported. Within-context errors are continuous and moderate in blocks, but they exceed the trajectory-specific variation required for positive macro R²; beyond-context error rises sharply. Strong pooled R² and positive time-only/training-mean diagnostics show that broad direction/time structure is predictable, but these cannot replace the frozen trajectory-unit statistic.

This result does not establish absence of all information in MineWorld, nor does it adjudicate causal importance, uncertainty, belief, fresh-layout generalization, or new occlusion types. It only fails the predeclared fixed layer/readout/linear-probe continuation test.

Authorized next step: stop Regime-A expansion, preserve the continuous package, and do not alter target/layer/tokens/bins/thresholds to obtain a positive result. Do not begin speed × noise expansion, Run B, or Run C.

## BLOCKERS

No operational or authority blocker remains. Scientific continuation is blocked by the frozen negative result, not by missing data or quality failure.

## RESULT_ARTIFACTS

All paths are relative to the repository and rooted at `docs/status/integration/regime_a_occlusion_extraction_v0_1/first25_analysis/`.

- `slice_predictions.parquet`: `4a8adbc6c2080da58fba1a64542301ae445a9ddc51b75b1e3a10ee175373e54a`
- `slice_primary_results.json`: `28c1c5725873df1c419dd2d9e283641a3dc74aa88b48ff0fd6de3fad2d40d226`
- `slice_duration_results.json`: `f75c519c83d85ea80aba02c497cd1621d2459f9dc354a795fd4a877c1080e9ed`
- `slice_baselines.json`: `0bdf9548c69569055b08c05f00f1206f3002deeeca4bc9b46f935bf159fdcac9`
- `slice_best_k_results.json`: `11d5d2f0527feb31a27a18a19ac76d342f5c72ca3326bee1863b75187dfc4427`
- `slice_secondary_target_results.json`: `45ba1b6862309b3a0671db10b2c31ed1998abf7ab3b154084d42db1b4b20b7f6`
- `slice_all_layer_profile.json`: `435f323fc01fde0fe042f4edcb1578975e06b8df356b0f12f3caa549ecdc6d1a`
- `slice_null_results.json`: `81a0fa0a5ead585e8eea69df2a9fb868bb44a229085048412e079559facd2bfd`
- `slice_bootstrap_results.json`: `b6413f581839c7a123c8b62b70193092b621014e89ed48363f112fe8b32e674a`
- `slice_validation_receipt.json`: `634fe4ea8885519e3b46be4409137ac47d0be41dc32bc0fd7598e36b9642760e`
- `continuation_adjudication.json`: `af67f3edd9821a793baf5d1b0b63a2a0227791e5a4ae131d2e5dbbe8b1f25a07`

Analysis code commit: `8c1b8ec921ac7cd2b742b926db162d99ff877395`.
