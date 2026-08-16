# 08 — Existing-Data Counterfactual Diagnostics

**Label: EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY.**
These are post-hoc analyses of *development* data. **None of them changes, or may be used to change, the frozen
P3 qualification outcome.** Script: `a08_counterfactuals.py`.

## 1. Exact margin to each threshold

| Candidate | precision | needed | FP observed | max FP allowed | **excess FP** | recall | headroom min | headroom median |
|---|---|---|---|---|---|---|---|---|
| C01 | 0.846847 | 0.95 | 51 | 14.8 | **+36.2** | 0.9792 ✓ | 0.4187 (≥0.3321 ✓) | 0.5683 (≥0.4981 ✓) |
| C02 | 0.915459 | 0.95 | 35 | 19.9 | **+15.1** | 0.9896 ✓ | 0.5930 ✓ | 0.7071 ✓ |
| C03 | 0.937634 | 0.95 | 29 | 22.9 | **+6.1** | 0.9954 ✓ | 0.6811 ✓ | 0.8235 ✓ |

Recall and headroom were never close to failing. Precision was the sole binding constraint, and C01 missed by
a wide margin (would have needed a 71 % reduction in FPs).

## 2. How many units caused the failure? Does excluding any single trajectory change it?
**No.** The FPs are spread across all 4 calibration runs of every candidate (C01: 13/13/12/13). Dropping the
single worst calibration run and its share of TPs still fails:

| Candidate | best precision after dropping worst run | verdict |
|---|---|---|
| C01 | 0.8480 | still FAIL |
| C02 | 0.9191 | still FAIL |
| C03 | 0.9397 | still FAIL |

The failure is structural, not outlier-driven.

## 3. Trajectory-equal vs pooled
The calibration gate is pooled by specification. Computed per-run, precision is 0.849/0.840/0.871/0.822 (C01) —
**every individual run fails independently.** Trajectory-equal aggregation does not rescue any candidate.

## 4. Do slight timing offsets change visibility? (alternative synchronisation)
Re-scoring with the geometric label shifted by the measured render lag:

| Candidate | shift | precision | recall | FP |
|---|---|---|---|---|
| C01 | 0 / 3 / 4 ticks | 0.8468 / 0.8436 / 0.8421 | 0.9792 / 0.9964 / **1.0000** | 51 / 51 / 51 |
| C02 | 0 / 3 / 4 ticks | 0.9155 / 0.9160 / 0.9152 | 0.9896 / **1.0000** / **1.0000** | 35 / 34 / 34 |
| C03 | 0 / 3 / 4 ticks | 0.9376 / 0.9363 / 0.9357 | 0.9954 / **1.0000** / **1.0000** | 29 / 29 / 29 |

**Re-synchronisation perfects recall and does nothing for precision.** Time-shifting translates the shadow
interval; it cannot change the *width* of the disagreement band, which is set by silhouette extent.

## 5. Do geometric and rendered visibility disagree? Do alternative definitions agree?
They disagree over a band of **1.04 ± 0.06 blocks** at every speed and in both directions
(`03_visibility_forensics.md` §3). A physically meaningful *area-based* geometric predicate (occluded ⇔ the
target's **bounding box** is fully behind the wall shadow) would, by construction, agree with the detector to
within the detector's min-area threshold. That reconciliation is a **prospective redesign**, not a post-hoc
re-score, and is proposed in `12_redesign_options.md`.

## 6. Is every evaluated point inside calibration support?
**No — and this is a second, independent defect.** `HIDDEN_BOUNDS` was measured at Regime A's speed and applied
unchanged at 2.0 / 2.5 / 3.0 b/s. Predicted rendered-hidden entry (LTR) vs the frozen constant −3.7310:

| Candidate | predicted boundary | margin | contaminated target rows |
|---|---|---|---|
| C01 (2.0) | ≈ −3.77 | **+0.04 (inside support)** | 0 |
| C02 (2.5) | ≈ −3.70 | **−0.03 (outside support)** | 1 |
| C03 (3.0) | ≈ −3.64 | **−0.09 (outside support)** | 7 |

## 7. Would a faster candidate pass? (the decisive counterfactual)
Fitting the speed-invariant geometry from the data — shadow span **10.635 blocks**, disagreement band
**1.152 blocks**, fixed 180-frame budget:

| v (b/s) | occluded frames | visible frames | FP | modelled precision | gate |
|---|---|---|---|---|---|
| 2.00 | 106.4 | 73.6 | 11.5 | 0.8647 | FAIL (actual 0.8468) |
| 2.50 | 85.1 | 94.9 | 9.2 | 0.9115 | FAIL (actual 0.9155) |
| 3.00 | 70.9 | 109.1 | 7.7 | 0.9342 | FAIL (actual 0.9376) |
| 3.25 | 65.4 | 114.6 | 7.1 | 0.9417 | FAIL |
| 3.50 | 60.8 | 119.2 | 6.6 | 0.9477 | FAIL (marginal) |
| **3.75** | 56.7 | 123.3 | 6.1 | **0.9525** | **PASS** |
| 4.00 | 53.2 | 126.8 | 5.8 | 0.9566 | PASS |

The model reproduces all three observed precisions to ≤0.02. **A hypothetical C04 at ≈3.75–4.0 b/s would pass
the frozen visibility calibration gate — purely because the fixed 180-frame window fills with visible frames
(including frames parked at the clamped lane end), with the detector↔geometry disagreement completely
unchanged.** That would be a scientifically indefensible pass, and it is the strongest evidence that the gate
does not measure what it claims to.

## 8. Would increasing speed improve the relevant quantity, or make another gate worse?
**It makes the scientifically important gate worse.** The two visibility sub-gates move in opposite directions:

| Candidate | calibration precision (↑ good) | NORMAL target rows clean (↓ bad) |
|---|---|---|
| C01 (2.0) | 0.8468 | **475/475** |
| C02 (2.5) | 0.9155 | 474/475 |
| C03 (3.0) | 0.9376 | **468/475** |

Extrapolating both: at the speed where calibration precision passes (~3.75 b/s), the frozen `HIDDEN_BOUNDS`
margin is ≈−0.15 blocks and target-row contamination would grow further — so the candidate would fail the
*other* half of the same gate. **No speed satisfies both halves of the P3 visibility gate as currently written.**

## 9. Is speed even the right redesign variable?
Speed was chosen to control **motion headroom** (target-x SD). It did so, correctly and monotonically
(0.4187 → 0.5930 → 0.6811 min SD; 0.5683 → 0.7071 → 0.8235 median), and **headroom passed comfortably at the
very first candidate.** Speed therefore succeeded at its stated purpose and was never the binding constraint.
What speed *also* controls, unintendedly, is (a) the class balance of the calibration set, (b) the frame-count
duration of the disagreement band, and (c) the validity of the fixed `HIDDEN_BOUNDS` constant. **The P3
candidate sequence swept a variable that was already satisfactory and could not address the actual blocker.**

## 10. Can existing P3 data support redesign without new capture?
**Yes, substantially.** Already measured from existing development data, at no new capture cost:
geometric shadow edges per direction; rendered-hidden edges per direction **per speed**; silhouette
half-extent w ≈ 0.6–0.8 blocks; render lag ≈3.3 ticks with a validated measurement method; the shadow span
10.635 blocks; the base-rate model. This is enough to *design* a corrected visibility gate and a corrected,
speed-aware hidden-onset rule. It is **not** enough to *qualify* one — qualification requires fresh
prospective development capture under a new authority.
