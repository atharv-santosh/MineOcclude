# Regime A' qualification — P1 existing-data report (v0.1)

**Phase** P1 · **Classification** EXPLORATORY_EXISTING_DATA · **Status** PASS
**REGIME_A_PRIME_COLLECTION_AUTHORIZED = NO**

P1 PASS means the analysis executed validly on existing data. It does **not**
mean the neural readout won. Closed Regime A remains
`FAIL_NO_DEFENSIBLE_DECODING` / `REGIME_A_FIRST25_PASS_CONTINUE=NO`, unchanged
and unreinterpreted by anything below.

## 1. What was compared

The frozen held-out layer-4 **BEST-K** hidden-position predictions from the
closed Regime A package, reused verbatim, against a causal static last-seen
baseline on identical eligible rows.

**LAST_RENDERED_EVIDENCE_POSITION** — the sheep world x at the most recent
causally prior model-input frame (within the frozen window `[T-15, T]`) whose
magenta detector state is `detected`. This is an *exploratory implementation of
the currently recommended definition*. It is **not** the prospectively frozen
Regime A' baseline authority; that still requires operator approval before any
confirmatory design freeze. The baseline was not selected by outcome.

All 475 frozen targets are `OCCLUDED_AGREEMENT` with no rendered pixels at the
target frame, so the baseline frame is always strictly prior to its target
(minimum evidence age 1 frame). Independent reconstruction reproduces all four
postmortem D2 visibility columns on all 475 rows with zero mismatches.

## 2. Domains

Domain boundaries come from existing authority, not from this analysis:

- **FULL_EVIDENCE_BEARING_IN_CONTEXT** (tau 1..15) — simultaneously the frozen
  confirmatory primary domain and, empirically, the exact set of rows carrying
  any in-context rendered evidence. `BEYOND_CONTEXT` (tau 16..19, 100 rows)
  carries **none**, so the baseline is undefined there and those rows are
  excluded by definition, not by outcome.
- **SHORT** (tau 1..4) — the frozen duration bin.
- **MATCHED_SPAN_TAU8_15** (tau 8..15) — the matched temporal-span subset already
  defined by postmortem D6's `matched_span_hidden_comparator`.

Two independent reconciliations against frozen authority hold exactly:
tau 1..15 macro R2 = `-0.509944`
equals the closed Regime A BEST-K value, and tau 8..15 macro R2 =
`-8.806104`
equals D6's value.

## 3. FULL evidence-bearing in-context domain (tau 1..15)

| quantity | value |
|---|---|
| trajectories / rows | 25 / 375 |
| evidence age (frames, min/median/max) | 1 / 8.0 / 15 |
| target min / max / range / SD (blocks) | -3.975 / 5.074 / 9.049 / 3.878 |
| neural BEST-K RMSE (traj-equal / row) | **0.3502** / 0.3632 |
| neural BEST-K MAE (traj-equal / row) | 0.2814 / 0.2814 |
| neural signed bias (traj-equal) | -0.0114 |
| neural macro R2 (secondary, non-controlling) | -0.509944 |
| LAST_RENDERED_EVIDENCE RMSE (traj-equal / row) | **0.6955** / 0.7142 |
| LAST_RENDERED_EVIDENCE MAE (traj-equal / row) | 0.6131 / 0.6131 |
| equal-trajectory mean Delta | **+0.3453** |
| median Delta (descriptive) | +0.3561 |
| trajectories with Delta > 0 | 24/25 (96%) |
| bootstrap 95% interval (mean Delta) | **[+0.2629, +0.4214]** |
| oracle trajectory-mean RMSE (not causal) | 0.3249 |
| frozen TIME_ONLY_LINEAR RMSE (non-neural) | 0.1849 |
| frozen TRAINING_MEAN RMSE (non-neural) | 0.2040 |
| frozen CONSTANT_VELOCITY RMSE (non-neural) | 0.3184 |

## 4. SHORT domain (tau 1..4)

| quantity | value |
|---|---|
| trajectories / rows | 25 / 100 |
| evidence age (frames, min/median/max) | 1 / 2.5 / 4 |
| target min / max / range / SD (blocks) | -3.975 / 5.074 / 9.049 / 4.279 |
| neural BEST-K RMSE (traj-equal / row) | **0.3948** / 0.4315 |
| neural BEST-K MAE (traj-equal / row) | 0.3354 / 0.3354 |
| neural signed bias (traj-equal) | -0.0411 |
| neural macro R2 (secondary, non-controlling) | -88.666768 |
| LAST_RENDERED_EVIDENCE RMSE (traj-equal / row) | **0.2164** / 0.2375 |
| LAST_RENDERED_EVIDENCE MAE (traj-equal / row) | 0.1973 / 0.1973 |
| equal-trajectory mean Delta | **-0.1784** |
| median Delta (descriptive) | -0.1730 |
| trajectories with Delta > 0 | 3/25 (12%) |
| bootstrap 95% interval (mean Delta) | **[-0.2617, -0.1019]** |
| oracle trajectory-mean RMSE (not causal) | 0.0855 |
| frozen TIME_ONLY_LINEAR RMSE (non-neural) | 0.1193 |
| frozen TRAINING_MEAN RMSE (non-neural) | 0.1466 |
| frozen CONSTANT_VELOCITY RMSE (non-neural) | 0.2250 |

## 5. Matched temporal span (tau 8..15)

| quantity | value |
|---|---|
| trajectories / rows | 25 / 200 |
| evidence age (frames, min/median/max) | 8 / 11.5 / 15 |
| target min / max / range / SD (blocks) | -3.660 / 4.748 / 8.408 / 3.611 |
| neural BEST-K RMSE (traj-equal / row) | **0.3133** / 0.3441 |
| neural BEST-K MAE (traj-equal / row) | 0.2645 / 0.2645 |
| neural signed bias (traj-equal) | +0.0029 |
| neural macro R2 (secondary, non-controlling) | -8.806104 |
| LAST_RENDERED_EVIDENCE RMSE (traj-equal / row) | **0.8901** / 0.9120 |
| LAST_RENDERED_EVIDENCE MAE (traj-equal / row) | 0.8732 / 0.8732 |
| equal-trajectory mean Delta | **+0.5768** |
| median Delta (descriptive) | +0.6306 |
| trajectories with Delta > 0 | 24/25 (96%) |
| bootstrap 95% interval (mean Delta) | **[+0.4657, +0.6753]** |
| oracle trajectory-mean RMSE (not causal) | 0.1668 |
| frozen TIME_ONLY_LINEAR RMSE (non-neural) | 0.2086 |
| frozen TRAINING_MEAN RMSE (non-neural) | 0.2286 |
| frozen CONSTANT_VELOCITY RMSE (non-neural) | 0.3589 |

## 6. The direction of the result

The neural readout **beats** LAST_RENDERED_EVIDENCE on the full domain
(+0.3453 blocks,
95% interval
[+0.2629,
+0.4214],
96% of
trajectories) and more strongly on the matched span
(+0.5768).
It **loses** on SHORT
(-0.1784 blocks,
95% interval
[-0.2617,
-0.1019],
only 12% of
trajectories).

This pattern is what a stale-baseline effect looks like. Mean absolute
displacement from last evidence grows from
0.1973
blocks on SHORT to
0.8732
blocks on the matched span, so the static baseline degrades with evidence age
while the neural RMSE stays roughly flat.

**The decisive caveat.** On every domain the neural readout is beaten by
non-neural baselines already frozen in the closed package — TIME_ONLY_LINEAR
(0.1849
blocks on the full domain) and TRAINING_MEAN
(0.2040)
— and its macro R2 is negative everywhere, meaning it is worse than an oracle
constant at the per-trajectory target mean. Beating a stale static-position
baseline at long evidence age is therefore **not** evidence of hidden-position
decoding; it is consistent with a readout that regresses toward trajectory
centre while the baseline drifts away.

## 7. Visible versus SHORT

`sub_analysis_status = PARTIAL_UNSUPPORTED_ROW_LEVEL_SCORING`
`exact_row_level_visible_scoring_status = UNSUPPORTED_FROM_PERSISTED_PREDICTIONS`

Three different things are reported below and must not be conflated. **No
visible RMSE anywhere in P1 is computed from the 100 matched visible rows.**

### 7a. Metadata-selected visible/SHORT matching manifest

Manifest integrity `9e441b7287e8d3f7`, algorithm
`boundary_offset_rank_v1`, built from **metadata only** (trajectory id,
direction, outer fold, offset from the visibility boundary) and persisted before
any outcome column was joined. 100 matched pairs
across 25 trajectories;
100 unmatched rows, each with a recorded reason
(visible rows at boundary offset > 4 have no SHORT counterpart).

These 100 pairs remain a **valid metadata-only matching authority**. They were
**not scored row-for-row**: per-row visible BEST-K predictions were never
persisted (D6 stored per-trajectory aggregates only), and recovering them would
require re-reading visible activations and refitting the readout, which P1
forbids. The SHORT side of these pairs *is* row-level scored; the visible side
is `UNSUPPORTED_FROM_PERSISTED_PREDICTIONS`. This sub-analysis therefore yields
no matched-row visible RMSE at all.

### 7b. D6 visible-window versus matched-SHORT aggregate (row counts differ)

The visible term here is the **D6 visible-window** aggregate over 8 rows per
trajectory (200 rows), *not* the matched rows.

| quantity | population | value |
|---|---|---|
| D6 visible-window RMSE (traj-equal) | D6 window, 8 rows/traj | 0.1098 |
| D6 visible-window MAE (traj-equal) | D6 window, 8 rows/traj | 0.0919 |
| SHORT matched RMSE (traj-equal) | matched SHORT rows, 4 rows/traj | 0.3948 |
| SHORT matched MAE (traj-equal) | matched SHORT rows, 4 rows/traj | 0.3354 |
| paired difference (SHORT − D6 visible window) | 25 trajectories | +0.2850 |
| bootstrap 95% interval | 25 trajectories | [+0.2186, +0.3557] |
| trajectories where hidden is worse | 25 trajectories | 100% |

This contrast is **not row-count matched** (8 versus 4 rows per trajectory) and
is **not** derived from the 100 matched pairs.

### 7c. D6 visible window versus hidden tau 8..15 (equal 8-row support)

The only contrast here with equal support on both sides, both 8 rows per
trajectory, taken from existing authority.

| quantity | value |
|---|---|
| D6 visible-window RMSE (traj-equal) | 0.1098 |
| hidden tau 8..15 RMSE (traj-equal) | 0.3133 |
| paired difference (hidden − visible) | +0.2035 |
| trajectories where hidden is worse | 88% |

**Interpretation.** A visible-versus-hidden gap under the old design is
descriptively supported. It does **not** isolate hidden-state memory loss,
wall/background distribution change, retained evidence amount, estimator
mismatch, object permanence, belief, or causal use of hidden position.

## 8. Displacement diagnostic

`P1_DISPLACEMENT_STATUS = DEFERRED`. Scoring a displacement readout requires
reading activations and fitting a decoder, both forbidden in P1, and no
displacement predictions exist to reuse. The descriptive displacement target
distribution is recorded in `p1_displacement_diagnostic.json`. A predicted
displacement of zero reconstructs the last-seen baseline exactly, so the
zero-displacement reference is already reported in section 3–5.

## 9. What this analysis does not establish

It does not re-adjudicate closed Regime A, and does not claim object permanence,
belief, uncertainty, explicit memory mechanism, or causal use of hidden position.
It does not establish that the layer-4 readout decodes hidden position: it does
not beat trivial non-neural baselines, and its macro R2 is negative on every
domain. It does not fix the last-seen baseline authority for Regime A'.
