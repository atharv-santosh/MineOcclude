# 03 — Deep Visibility Forensics (highest-priority investigation)

**Label: EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY.**
Scripts: `a01_calibration_reconstruct.py`, `a02_boundary_profile.py`, `a03_transition_geometry.py`,
`a05_target_row_forensics.py`, `a06b_render_state_lag.py`, `a08_counterfactuals.py`.
Visual evidence: `03_visibility_boundary_frames_c01_ltr.png`.

## 1. What "visibility" means in P3 — three *different* definitions are in play

| # | Name | Defined by | Predicate |
|---|---|---|---|
| **G** | geometric visibility | Java mod, `EpisodeManager.java:453` | one ray, eye → **point** `(sheepX, sheepY+0.5, sheepZ)`, vs block-inflated wall AABB |
| **R** | rendered visibility | `detect_magenta` on the 640×360 PNG | **any** magenta component of area ∈ [19, 5000] px exists |
| **H** | *design* hidden bounds | `p3a_freeze.py:39-42` `HIDDEN_BOUNDS` (frozen constants) | world-x interval, **direction-dependent**, imported from the Regime A directional-visibility authority |

The freeze places target windows using **H**. The runtime labels rows using **G**. The gate scores **R against
G**. Nothing reconciles the three.

## 2. Where the calibration gate actually failed

All four calibration specs per candidate are `scene = NORMAL` (wall present), 180 frames each → 720 rows.

| Candidate | v | rows | TP | **FP** | TN | FN | precision | recall | specificity | **FP-rate on occluded rows** | visible base rate |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C01 | 2.0 | 720 | 282 | **51** | 381 | 6 | **0.8468** | 0.9792 | 0.8819 | **0.1181** | 0.4000 |
| C02 | 2.5 | 720 | 379 | **35** | 302 | 4 | **0.9155** | 0.9896 | 0.8961 | **0.1039** | 0.5319 |
| C03 | 3.0 | 720 | 436 | **29** | 253 | 2 | **0.9376** | 0.9954 | 0.8972 | **0.1028** | 0.6083 |

FP = "geometry says **occluded**, renderer still shows the target". Recall never failed. **Precision failed
every time, and only precision.**

> **The detector's actual error rate is flat (0.118 → 0.104 → 0.103).** Precision rose only because the
> *visible base rate* rose (0.400 → 0.532 → 0.608). The gate metric is confounded with the swept variable.

## 3. The disagreement is a single, structural, spatially-localised band

FPs are **not** scattered; they form contiguous runs at the occlusion boundary, in **both** directions, in
**every** run, at **every** speed.

Transition x-positions (mean over runs):

| Candidate | geometric shadow (G) | rendered shadow (R), LTR | rendered shadow (R), RTL |
|---|---|---|---|
| C01 | [−4.798, +5.875] | [−3.741, +5.670] | [−4.640, +4.771] |
| C02 | [−4.804, +5.894] | [−3.701, +5.875] | [−4.820, +4.761] |
| C03 | [−4.760, +5.962] | [−3.721, +5.962] | [−4.893, +4.767] |

- G is symmetric about **x = +0.53** — i.e. about the camera eye at x = 0.5. **The geometric model is
  self-consistent and correct.**
- The **entry band** (magenta persisting after G flips to occluded) is **1.04 ± 0.06 blocks**, invariant across
  direction and across all three speeds.
- FP magenta areas are **large** (median 100–300 px of a ~330–400 px full silhouette), i.e. this is not
  stray-pixel noise — a substantial fraction of the target is genuinely still on screen.

### Visual confirmation (`03_visibility_boundary_frames_c01_ltr.png`, run `p3dev_c01_viscal_ltr_r01`)

| tick | x | geometric | magenta | area px |
|---|---|---|---|---|
| 30 | −4.921 | visible | detected | 322 |
| **31** | **−4.785** | **occluded** | **detected** | **312** |
| 33 | −4.596 | occluded | detected | 306 |
| 35 | −4.433 | occluded | detected | 222 |
| 39 | −4.100 | occluded | detected | 56 |
| 41 | −3.838 | occluded | detected | 28 |
| 42 | −3.642 | occluded | not_detected | — |

At tick 31 — the exact frame the server declares the target **occluded** — the rendered sheep is **97 % as
large as when fully visible** and plainly beside the wall in the image. Eleven consecutive frames are labelled
"occluded" while the target is visibly on screen. **This is not a detector false alarm.**

## 4. Mechanism, decomposed — two independent effects

### 4a. Finite silhouette extent (point vs area predicate) — **dominant, gate-fatal**
G tests one point; R tests the whole body. Solving the entry/exit band geometry gives a silhouette
half-extent **w ≈ 0.6–0.8 blocks** (sheep collision box is 0.9 wide; the rendered wool model is wider). This
term sets the **width** of the FP band and is **invariant to any time-shift**.

### 4b. Render-vs-state temporal lag ≈ **3.3 server ticks** — real, independently measured
Measured directly from pixels on NO_WALL runs (no occluder, silhouette always whole) by cross-correlating the
magenta blob's image-space centroid against the logged `sheep_x`. The vectorised detector used was validated
against the frozen `detect_magenta` — **identical area and centroid on all 5 validation frames**.

| run | dir | v (b/tick) | best lag | rms @ best | rms @ lag 0 | px/block |
|---|---|---|---|---|---|---|
| `p3dev_c01_t01_nowall` | LTR | 0.100 | **+3.77** | 1.445 px | 2.54 px | −23.36 |
| `p3dev_c01_t06_nowall` | RTL | 0.100 | **+3.06** | 1.212 px | 1.94 px | −23.32 |
| `p3dev_c03_t01_nowall` | LTR | 0.150 | **+2.95** | 0.955 px | 1.94 px | −23.32 |
| `p3dev_c03_t06_nowall` | RTL | 0.150 | **+3.39** | 1.048 px | 1.97 px | −23.29 |

Positive lag ⇒ **frame index *i* shows the target where it was ≈3.3 ticks earlier than the state row written
with index *i***. The estimate is resolved by the frozen per-tick motion noise (σ = 0.05 blocks), is
**constant in ticks** across a 1.5× speed change (hence *temporal*, not spatial), and is consistent in both
directions. This is the classic signature of **Minecraft client-side entity interpolation**, which the
lockstep protocol does not cancel: the mod's own `capture_package_v0_1.json` records
`temporal_alignment.evidence_scope = "synthetic_contract_only"` — alignment was verified for
**action→camera** effects, never for **rendered entity position vs logged entity position**.

### Which effect caused which failure
Shifting the geometric label by the measured lag (counterfactual §7 of `08_…`):

| Candidate | lag corr. | precision | recall | FP |
|---|---|---|---|---|
| C01 | 0 → 4 ticks | 0.8468 → 0.8421 | 0.9792 → **1.0000** | 51 → 51 |
| C02 | 0 → 4 ticks | 0.9155 → 0.9152 | 0.9896 → **1.0000** | 35 → 34 |
| C03 | 0 → 4 ticks | 0.9376 → 0.9357 | 0.9954 → **1.0000** | 29 → 29 |

**The lag fully explains the false *negatives* (recall → 1.000) and explains none of the false *positives*.**
The precision failure is caused by **4a**, the point-vs-area predicate mismatch, and is **not fixable by
re-synchronisation, by detector tuning, or by any choice of speed**.

## 5. The target-row contamination has a different, speed-dependent cause

| Candidate | v | contaminated NORMAL target rows | all at τ | all at phase |
|---|---|---|---|---|
| C01 | 2.0 | **0** / 475 | — | — |
| C02 | 2.5 | **1** / 475 | τ=1 | 0 |
| C03 | 3.0 | **7** / 475 | τ∈{1,2} | 0 |

Every contaminated row sits at x ≈ −3.64…−3.72 (LTR) or +4.57…+4.80 (RTL) — i.e. **exactly at the frozen
`HIDDEN_BOUNDS` entry constant**, which is `LTR −3.7309960703951197`, `RTL +4.837594280703691`.

The true rendered-hidden entry boundary is `G_edge + w + lag·v`. Because of **4b** it **drifts in the
direction of travel in proportion to speed**, while `HIDDEN_BOUNDS` is a **fixed constant calibrated at Regime
A's speed**. Predicted boundary vs the frozen constant:

| Candidate | v (b/tick) | predicted rendered-hidden entry (LTR) | frozen bound | margin | observed contamination |
|---|---|---|---|---|---|
| C01 | 0.100 | ≈ −3.77 | −3.7310 | **+0.04 safe** | 0 |
| C02 | 0.125 | ≈ −3.70 | −3.7310 | **−0.03 unsafe** | 1 |
| C03 | 0.150 | ≈ −3.64 | −3.7310 | **−0.09 unsafe** | 7 |

**Monotonic agreement.** The stale constant's safety margin was ≈0.01 blocks at C01 and went negative between
C01 and C02. Only phase-0 specs (τ=1 flush against the boundary) were hit — exactly as predicted.

## 6. Failure classification

| Question | Answer |
|---|---|
| Broad/systematic or outliers? | **Systematic.** Present in 12/12 calibration runs, both directions, all speeds. Dropping the worst calibration run still fails (C01 0.848, C02 0.919, C03 0.940). |
| Concentrated in one direction? | **No** — symmetric about the camera. |
| Concentrated in WALL or NO_WALL? | **Entirely NORMAL/WALL** — NO_WALL target rows are 475/475 for all three candidates, and NO_WALL is never calibrated at all. |
| Concentrated near a τ? | Target contamination: **only τ=1, τ=2, only phase 0**. |
| Near screen edge? | No — at the wall shadow boundary, mid-frame. |
| Near wall transition? | **Yes — this is the entire effect.** |
| Due to one or two outliers? | **No.** |
| Calibration extrapolation? | Yes for §5: `HIDDEN_BOUNDS` applied outside the speed at which it was measured. |
| Timing? | Yes, secondary: ~3.3-tick render lag (drives recall FNs and the §5 drift). |
| Scene-state mismatch? | **No.** 0 scene-field mismatches in 27,000 rows. |
| Implementation? | Yes: the gate compares two non-equivalent predicates. |
