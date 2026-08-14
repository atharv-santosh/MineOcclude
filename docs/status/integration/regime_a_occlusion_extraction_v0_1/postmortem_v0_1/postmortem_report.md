# Regime A first25 — outcome-aware exploratory postmortem v0.1

**Status: EXPLORATORY. The confirmatory Regime A first25 result is unchanged and closed.**

| | |
|---|---|
| Confirmatory adjudication | `FAIL_NO_DEFENSIBLE_DECODING` |
| `REGIME_A_FIRST25_PASS_CONTINUE` | `NO` |
| Confirmatory artifacts modified | 0 |
| Postmortem mode | `OUTCOME_AWARE_EXPLORATORY_POSTMORTEM` |

Nothing in this document re-adjudicates the closed result. No exploratory metric
replaces the primary. The purpose is solely to establish **why** the frozen
experiment failed, and whether a new prospectively frozen Regime A-prime is
scientifically justified.

---

## Phase 0 — authority binding

`postmortem_input_binding.json` = **PASS**.

* All 16 confirmatory files re-hashed and recorded.
* Both self-referential hashes inside the confirmatory package verified:
  `analysis_input_binding_sha256` and `a5_receipt_sha256` match their recorded values.
* All 22 upstream authorities bound by the confirmatory analysis are present and hash-matched.

Two provenance facts were established mechanically rather than assumed, and both
correct earlier informal reasoning.

### The model input window includes the target frame

From the extractor that actually produced the confirmatory activations
(`scripts/run_regime_a.py`, `PersistentMineWorldWorker.extract`):

```python
line 909  targets = [row.model_frame_idx for row in visibility if tau in 1..19]
line 930  indices = list(range(target - 15, target + 1))   # 16 pairs, INCLUSIVE of target
line 934  span    = tokenized.frame_token_map.spans[-1]    # target frame's 336 tokens
```

So the causal window is `[target-15, target]`: the target frame itself plus **15**
preceding frames.

### The guards are a rejection threshold, not an offset

The amended authority states the rule verbatim as *"directional maximum
consecutive partial/disagreement run plus one captured frame"*, and
`assign_stable_hidden_tau` assigns `tau = 1` to the **first frame of the stable
19-frame `OCCLUDED_AGREEMENT` run**, raising if `onset - transition_start`
exceeds the guard.

The guards (LTR 18/11, RTL 20/8) therefore **reject** trajectories whose entry
transition was too long. They do **not** skip 18–20 frames forward before
scoring. Any argument that the long guard pushed evidence out of the context
window is based on a false premise and is discarded here.

---

## D1 — target headroom

The recomputation reproduces the frozen primary **exactly**:

```
macro R2 recomputed from per-trajectory SSE/TSS = -1.228906417118
frozen primary macro R2                        = -1.228906417118
all 25 TSS match: True     all 25 SSE match: True
```

Across the 25 trajectories on the primary `tau1..15` domain:

| quantity | min | median | mean | max |
|---|---|---|---|---|
| target SD (blocks) | 0.1958 | **0.3112** | 0.3249 | 0.4540 |
| target range (blocks) | 0.5538 | 0.9984 | 1.0193 | 1.3716 |
| hidden displacement τ1→τ15 (blocks) | 0.5369 | 0.9984 | 1.0139 | 1.3716 |
| FULL RMSE (blocks) | 0.1968 | 0.3755 | 0.4170 | 0.7251 |
| **RMSE / target SD** | 0.5808 | **1.2291** | 1.3589 | 3.1586 |

The decoder's absolute error exceeds the entire within-trajectory signal in the
median trajectory. Descriptive counterfactuals on the *same frozen errors*:

| within-trajectory target SD | resulting macro R² |
|---|---|
| ×1 (as run) | −1.2289 |
| ×2 | +0.4428 |
| ×3 | +0.7523 |
| ×4 | +0.8607 |

At the observed RMSE, reaching macro R² = 0 needs SD ≈ 0.417 blocks and macro
R² = 0.8 needs ≈ 0.932 blocks, against the 0.311 actually available.

**`HEADROOM_LIMITATION_SUPPORTED = YES`.**

---

## D2 — exact in-context visibility audit

**This is the diagnostic that most changes the picture, and it refutes the strong
form of the hypothesis it was written to test.**

Mapping verification passed on all counts: the inventory's
`target_model_frame_indices` equal both the independently rebuilt extractor
target list and the `model_frame_idx` column of the frozen predictions, for all
25 trajectories; every `tau` sequence is 1..19; every context window is in range.

Evidence is measured with the repository's own states. `magenta_status ==
detected` is the signal for *"the rendered frame the model consumed contained
sheep pixels"* — during the entry transition the geometric ray test reports
`occluded` while the sheep is still plainly on screen (e.g. t01 frames 35–42
carry 313→28 magenta pixels).

| bin | rows | % with clean-visible frame | median clean | % with rendered pixels | median evidence frames | median max px |
|---|---|---|---|---|---|---|
| SHORT (τ1–4) | 100 | 91.0 | 3.0 | **100.0** | 13.5 | 339 |
| INTERMEDIATE (τ5–8) | 100 | 21.0 | 0.0 | **100.0** | 9.5 | 323 |
| LONG (τ9–12) | 100 | **0.0** | 0.0 | **100.0** | 5.5 | 196 |
| NEAR_CONTEXT (τ13–15) | 75 | **0.0** | 0.0 | **100.0** | 2.0 | 56 |
| BEYOND_CONTEXT (τ16–19) | 100 | 0.0 | 0.0 | **0.0** | 0.0 | 0 |

An exact structural rule holds for **all 475 rows without exception**:

```
rendered-evidence frames in context == 16 - tau
```

with evidence quality decaying monotonically from 340 px at τ=1 to 28 px at
τ=15 and 0 at τ≥16.

**Adjudication.** The prior claim that LONG and NEAR_CONTEXT may contain *zero
sheep evidence* is **refuted in its strong form**: every one of the 375 primary
rows retains at least one context frame with real rendered sheep pixels. It is
**supported in a weaker form**: LONG and NEAR_CONTEXT contain zero clean
dual-agreement visible frames (175/175 rows), their only evidence being the weak
tail of the entry transition. Total evidence starvation is confined to
BEYOND_CONTEXT (100/100 rows), which was already descriptive-only.

A consequence worth recording: because evidence-frame count is exactly `16 − τ`,
in-context sheep evidence is **perfectly collinear with τ** across the primary
domain. Any representation that encodes how much sheep evidence its window holds
thereby encodes τ, and τ is monotone in position within a trajectory. This is a
plausible mechanism for the high pooled R² and for the time-only baseline
(0.5049) outperforming the neural readout.

**`CONTEXT_EVIDENCE_STARVATION_SUPPORTED = PARTIAL`** — a steep, exactly
characterized evidence gradient within the primary domain, and total starvation
only beyond it.

---

## D3 — trajectory offset vs motion tracking

Frozen out-of-fold predictions, no refit.

| statistic | layer-4 FULL | layer-4 BEST-K |
|---|---|---|
| macro R² | −1.2289 | −0.5099 |
| **macro oracle-centered R²** | **−0.2844** | **+0.0718** |
| macro RMSE (blocks) | 0.4170 | 0.3502 |
| macro centered RMSE (blocks) | 0.3167 | 0.2783 |
| median OLS slope ŷ on y | **1.0091** | 1.1186 |
| trajectories with positive slope | **25/25** | — |
| median Pearson r | **0.7666** | 0.8318 |
| trajectories with positive r | **25/25** | — |
| mean absolute trajectory offset (blocks) | **0.2407** | — |
| offset share of SSE | **35.9 %** | — |
| trajectories with positive centered R² | 15/25 | 18/25 |

The frozen predictions genuinely track within-trajectory motion: every
trajectory has positive slope and positive correlation, and the median slope is
essentially 1. Superimposed on that is a trajectory-specific offset averaging
0.241 blocks — comparable to the entire 0.311-block within-trajectory SD — which
accounts for 35.9 % of squared error.

Removing that offset with oracle knowledge moves FULL from −1.2289 to −0.2844.
Substantial, but **still negative**: offset alone does not explain the failure,
because the centered RMSE (0.317) remains at the target SD (0.311).

> The centering uses the held-out trajectory's own mean. It is descriptive only,
> is not an operational decoder, and does not rescue Regime A.

**`TRAJECTORY_OFFSET_FAILURE_SUPPORTED = PARTIAL`.**

---

## D4 — bin decomposition

Descriptive breakdown of the frozen predictions; no per-bin refit. Per-bin R² is
deliberately not reported: each bin spans 3–4 frames per trajectory and the
within-bin TSS is far too small for R² to be meaningful.

| bin | rows | within-traj target SD | RMSE | RMSE/SD | signed bias | median evidence frames | median max px |
|---|---|---|---|---|---|---|---|
| SHORT | 100 | 0.0855 | 0.5066 | 5.93 | −0.0078 | 13.5 | 339 |
| INTERMEDIATE | 100 | 0.0846 | 0.4508 | 5.33 | +0.0082 | 9.5 | 323 |
| LONG | 100 | 0.0939 | **0.3760** | 4.01 | +0.0111 | 5.5 | 196 |
| NEAR_CONTEXT | 75 | 0.0491 | 0.4076 | 8.31 | +0.0072 | 2.0 | 56 |
| BEYOND_CONTEXT | 100 | 0.0854 | **3.2732** | 38.34 | **+1.1449** | 0.0 | 0 |

Two findings matter.

1. **Within the primary domain, error is not monotone in occlusion duration.** It
   is *lowest* at LONG (0.376) and higher at both SHORT (0.507) and
   NEAR_CONTEXT (0.408), even though in-context evidence decays strictly
   monotonically (13.5 → 2.0 frames, 339 → 56 px). This is the signature of a fit
   that captures each trajectory's central tendency and mis-scales the
   excursion, not of progressive loss of a maintained hidden state.
2. **The collapse at BEYOND_CONTEXT is total and directional** — RMSE 3.27 with a
   +1.14 block bias — and coincides exactly with the bin where in-context sheep
   evidence is 0/16 frames.

---

## D5 — training-size / estimator variance

Original five outer held-out sets preserved; deterministic direction-balanced
training subsets; alpha and K selected by leave-one-trajectory-out **inside the
training subset only**.

**Validation:** at N=20 the reimplementation reproduces the frozen per-fold macro
R² exactly (fold 0 = −0.560610, fold 1 = −1.918276) and the frozen overall
−1.2289, so the FULL curve is directly comparable to the confirmatory result.

### FULL

| N_train | fits | mean macro R² | SD across fits | RMSE | Δ |
|---|---|---|---|---|---|
| 5 | 25 | −2.8361 | 1.8127 | 0.5777 | — |
| 10 | 25 | −1.7600 | 1.4400 | 0.4834 | +1.0761 |
| 15 | 25 | −1.3188 | 0.8284 | 0.4448 | +0.4413 |
| 20 | 5 | **−1.2289** | 0.9741 | 0.4367 | **+0.0899** |

### BEST-K

| N_train | fits | mean macro R² | SD across fits | RMSE |
|---|---|---|---|---|
| 5 | 25 | −3.6467 | 1.7654 | 0.6246 |
| 10 | 25 | −2.5887 | 2.0671 | 0.5470 |
| 15 | 25 | −1.8408 | 1.1123 | 0.4897 |
| 20 | 5 | −1.9726 | 0.7212 | 0.5152 |

> Caveat: D5's BEST-K at N=20 (−1.973) does **not** reproduce the frozen BEST-K
> (−0.510), because K and alpha selection here uses leave-one-trajectory-out
> rather than the frozen five inner folds of four, and K selection is sensitive
> to that choice. The D5 BEST-K column is internally comparable across N only.
> The FULL column is comparable to the frozen result.

FULL improves monotonically and its variance shrinks (1.81 → 0.83), so the
estimator is genuinely sample-limited. But the increments decelerate sharply —
+1.08, +0.44, +0.09 — roughly quartering each step. The curve is flattening
toward an asymptote **far below zero**, not approaching it. More trajectories at
this effect size would not have produced a positive primary result.

**`SAMPLE_LIMITATION_SUPPORTED = PARTIAL`** — real and measurable, but not
sufficient on its own. No required future N is extrapolated; the curve does not
support one.

---

## D6 — matched visible-sheep positive control

New extraction **was** required; no visible-frame activations existed for these
trajectories.

* Manifest frozen from metadata only and committed at `1ad7e53` **before** any
  visible activation existed.
* **8** clean dual-agreement visible rows per trajectory (200 rows). The limit is
  not a visibility break — every trajectory's run is capped by the extractor's own
  full-context requirement (`target − 15 ≥ 0`), so frame 15 is the earliest
  eligible target.
* Direction balance (13/12) and the five outer folds preserved. All 25
  trajectories have positive TSS.

**Extraction equivalence: bitwise identical.** Re-extracting the known frozen
hidden target (t01, τ=1, frame 43, layer 4) through the generalized
arbitrary-target path reproduced the stored array with `max_abs_diff = 0.0`.

### Results — same layer, readout, folds, target, checkpoint, camera

| | macro R² | pooled R² | RMSE | MAE | trajectories > 0 | bootstrap 95 % CI |
|---|---|---|---|---|---|---|
| **VISIBLE FULL** | **−0.5425** | 0.9986 | 0.2007 | 0.1623 | 11/25 | [−1.1783, −0.0133] |
| **VISIBLE BEST-K** | **+0.5892** | 0.9996 | 0.1098 | 0.0919 | **24/25** | **[+0.4717, +0.6922]** |

All five folds selected **K = 1** for the visible control.

### Matched-span contrast (8 rows per trajectory, near-matched headroom)

| readout | condition | mean target SD | RMSE | RMSE/SD | macro R² |
|---|---|---|---|---|---|
| FULL | visible | 0.1820 | 0.2007 | 1.10 | −0.5425 |
| FULL | hidden τ8–15 | 0.1668 | 0.3650 | 2.19 | −11.0032 |
| BEST-K | visible | 0.1820 | **0.1098** | **0.60** | **+0.5892** |
| BEST-K | hidden τ8–15 | 0.1668 | 0.3133 | 1.88 | −8.8061 |

Three conclusions follow.

1. **The confirmatory primary readout fails its own positive control.** Layer-4
   FULL cannot decode the sheep even when it is plainly visible (−0.5425, only
   11/25 trajectories positive, CI upper bound −0.013). A 688 k-dimensional
   readout fit from ~20 trajectories is not a sound instrument at this cohort
   size, so the mechanistic interpretation of the hidden FULL negative is
   materially weakened.
2. **The geometry and representation are not inherently incapable.** In reduced
   dimension the same layer-4 activations decode a visible sheep well:
   macro R² +0.5892, 24/25 trajectories positive, CI entirely above zero, RMSE
   0.110 blocks — below the 0.182-block target SD. A single token (K=1) suffices.
3. **A genuine occlusion-specific gap remains.** At matched window length and
   near-matched headroom, BEST-K error rises 2.9× from visible (0.110) to hidden
   (0.313), and FULL rises 1.8×. This gap is not explained by headroom, window
   length, or readout capacity, because the positive control holds all three
   roughly fixed.

**`MATCHED_READOUT_FAILURE` = SUPPORTED for FULL, NOT_SUPPORTED for BEST-K.**

---

## D7 — descriptive physical scale

Descriptive context only. **Token pitch is not claimed as a hard representational
bound** — token activations are continuous high-dimensional features and can in
principle encode sub-token position. D6's K=1 visible result (RMSE 0.110 blocks
≈ 0.09 token columns) directly demonstrates sub-token decoding.

| quantity | value |
|---|---|
| blocks per token column | 1.230 (min 1.227, max 1.239) |
| sheep rendered footprint | 379 px ≈ 0.553 token cells |
| primary hidden displacement | 0.998 blocks median |
| **primary hidden displacement in token columns** | **0.812** |

The whole motion the probe was asked to resolve spans under one token column.

---

## Integrated interpretation

1. **Was the sheep physically and visually hidden correctly?** Yes. All 475 target
   frames are `OCCLUDED_AGREEMENT` under both independent detectors, the target
   mapping is verified against three independent sources, and the guard authority
   was applied as a rejection threshold exactly as specified.
2. **SHORT (τ1–4) in-context evidence?** Yes — 91 % have clean dual-agreement
   visible frames, median 3; 100 % have rendered pixels, median 13.5 frames.
3. **INTERMEDIATE (τ5–8)?** Partial — 21 % clean-visible, but 100 % retain
   rendered pixels, median 9.5 frames.
4. **LONG (τ9–12)?** Degraded but non-zero — 0 % clean-visible, 100 % retain
   rendered pixels, median 5.5 frames at median 196 px.
5. **NEAR_CONTEXT (τ13–15)?** Severely degraded — 0 % clean-visible, 100 % retain
   rendered pixels but median only 2.0 frames at 56 px.
6. **BEYOND_CONTEXT (τ16–19)?** None. 0/16 evidence frames in 100/100 rows.
7. **Was target TSS unusually small relative to decoder error?** Yes. Median
   within-trajectory SD 0.311 blocks against median RMSE 0.376; median
   RMSE/SD = 1.229.
8. **Did predictions track within-trajectory motion after removing offsets?**
   Partly. Median slope 1.009 and median r 0.767 with all 25 trajectories
   positive, and oracle centering lifts FULL from −1.2289 to −0.2844 — real
   tracking, but still negative.
9. **Does the learning curve indicate sample limitation?** Yes, but bounded.
   Monotone improvement with shrinking variance, and sharply decelerating
   increments (+1.08, +0.44, +0.09) flattening well below zero.
10. **Can the same layer-4 readout decode a visible sheep?** FULL: no (−0.5425).
    BEST-K: yes, strongly (+0.5892, 24/25, CI entirely above zero).

### Diagnosis matrix

| diagnosis | verdict | evidence |
|---|---|---|
| `HEADROOM_LIMITATION` | **SUPPORTED** | Median RMSE/target-SD = 1.229; the same frozen errors give macro R² +0.44 at 2× SD and +0.75 at 3× SD. |
| `CONTEXT_EVIDENCE_STARVATION` | **PARTIALLY_SUPPORTED** | Evidence frames = `16 − τ` exactly for all 475 rows; every primary row keeps rendered sheep pixels, but LONG/NEAR_CONTEXT keep zero clean-visible frames and total starvation is confined to BEYOND_CONTEXT. |
| `TRAJECTORY_OFFSET_FAILURE` | **PARTIALLY_SUPPORTED** | Mean absolute offset 0.241 blocks = 35.9 % of SSE; oracle centering lifts FULL to −0.2844 but not above zero. |
| `SAMPLE_LIMITATION` | **PARTIALLY_SUPPORTED** | Monotone rise −2.84 → −1.23 with variance 1.81 → 0.83, but increments decelerate +1.08 → +0.44 → +0.09, flattening far below zero. |
| `MATCHED_READOUT_FAILURE` | **SUPPORTED for FULL; NOT_SUPPORTED for BEST-K** | Visible FULL −0.5425 (11/25, CI upper −0.013); visible BEST-K +0.5892 (24/25, CI [+0.47, +0.69], RMSE 0.110). |

### What Regime A actually established

* The pipeline is sound: lockstep capture, dual-detector visibility, exact target
  mapping, hash-chained durability, and an extraction path that reproduces
  bitwise on replay.
* The sheep was genuinely hidden at every scored target frame.
* Under the preregistered criterion, layer-4 FULL did not yield a defensible
  trajectory-specific linear decode of hidden world position. That verdict stands.
* Layer-4 activations do carry substantial trajectory-, direction- and
  time-correlated structure (pooled R² 0.987), and the frozen predictions do track
  within-trajectory motion (all 25 slopes and correlations positive).

### What Regime A did not establish

* It did **not** establish that MineWorld lacks a linearly decodable hidden
  position estimate. The primary readout (FULL) fails its own visible positive
  control, so the hidden FULL negative cannot be attributed to occlusion.
* It did **not** measure a well-posed quantity: within-trajectory target SD
  (0.311 blocks) was below the decoder's own error, so even a good decoder scores
  negative.
* It did **not** separate hidden-state maintenance from τ-tracking, because
  in-context evidence is exactly collinear with τ.
* It did **not** test a converged estimator; the learning curve is still rising at
  the cohort ceiling.
* The BEYOND_CONTEXT collapse is uninformative about object permanence — those
  rows contain no sheep evidence at all.

---

## Regime A-prime

**`REGIME_A_PRIME_JUSTIFIED = YES`**, on one specific ground: the matched visible
positive control shows the representation and geometry **can** support a
trajectory-generalizing decode (BEST-K +0.589, 24/25, CI above zero), while the
same readout on hidden frames at matched span degrades 2.9×. That gap is real and
was not measurable under the frozen design. Regime A could not have answered the
question it posed.

The smallest evidence-driven redesign, and only what the diagnostics support:

1. **Give the target measurable headroom** *(D1, D7)*. Within-trajectory SD must
   exceed decoder error by a clear margin; D1 puts the requirement near 0.9–1.3
   blocks of SD against current error, versus 0.311 actually present. The lever
   is the hidden-window displacement, bounded by the 0.75 s effective context.
   **Not adopted:** the previously floated "4–6 blocks/s". The required speed
   should be derived from a measured pilot RMSE, not assumed.
2. **Preregister a reduced-dimension primary readout** *(D5, D6)*. FULL fails the
   visible positive control; BEST-K passes it decisively at K=1. FULL should not
   be the confirmatory primary again. **Not adopted:** PCA — untested here;
   BEST-K is what the evidence supports.
3. **Require a visible positive control to pass before any hidden claim** *(D6)*.
   This is the single highest-value addition and is cheap. A hidden negative is
   only interpretable if the same readout clears the visible control on matched
   rows with matched headroom.
4. **Break the τ / evidence collinearity** *(D2)*. In-context evidence is exactly
   `16 − τ`, so the design cannot distinguish hidden-state maintenance from
   τ-tracking. Vary occlusion onset relative to the context window, or vary
   pre-occlusion speed across trajectories, so position is not recoverable from
   elapsed time. Time-only scored 0.5049 and beat the neural readout; that must
   go to ≈ 0 for the test to be meaningful.
5. **Solve target purity and evidence retention separately** *(Phase 0, D2)*.
   The guard must **not** be shortened merely because it is long — it was
   measured from real transition ambiguity and it is a rejection threshold, not
   an offset, so it never cost context. Keep dual-detector purity on the target
   frame. Retention is a separate axis, controlled by where occlusion onset sits
   relative to the 16-frame window; make it an explicit, prospectively varied
   design factor with evidence-retention recorded per row.
6. **Report a scale-explicit criterion alongside macro R²** *(D1, D4)*. Macro R²
   is uninformative when within-trajectory TSS is this small. Preregister an
   absolute-error criterion in blocks, and do not report per-bin R² for 3–4 row
   bins.

**Not adopted on this evidence:** N = 100–200 (D5's curve flattens far below zero;
sample size alone does not fix it), and a narrower FOV (D7 shows the sheep already
decodes sub-token when visible, so pitch is not the binding constraint).

Cohort size should still rise above 25 to reduce estimator variance, but as a
secondary measure, sized from a pilot rather than asserted.
