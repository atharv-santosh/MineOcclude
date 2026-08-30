# MineOcclude Experiment III — Phase 0 Adjudicated Design

**Design identity:** Experiment III — Graded Partial Observability  
**Document role:** canonical Phase 0 successor to the historical Fable design input  
**Status:** preauthority design; not a final authority; no execution or implementation is authorized  
**Audited repository state:** `experiment/exp3-graded-partial-observability` at `4c8dd7c1a7e8ff6ac0042361579da27e362996fe`  
**Design date:** 2026-08-30

## 1. Executive decision

Experiment III will measure how linear accessibility of a moving sheep's current position changes as direct visual evidence is weakened between a no-wall anchor and an opaque-wall anchor. It will use five fully paired conditions on **25 fresh, prospectively generated trajectory identities**, not the 25 development identities used by Regime A-prime and Experiment II. The five conditions are L0 (no wall), three one-layer stained-glass materials selected by an outcome-blind image calibration, and L4 (the original one-layer stone wall). All conditions share the same fresh seed, path, direction, motion schedule, FIR target labels, and 19 target frames within an identity.

The primary readout remains the already selected Experiment II family: decoder layer 19, `COARSE_2X6_CONCAT`, `CURRENT`, linear ridge. No layer or representation search may change that readout. Layers 4 and 10 are descriptive depth checks. `CURRENT_MINUS_PREVIOUS` and `TWO_FRAME_CONCAT` are predeclared secondary temporal diagnostics extracted from the same forwards.

The Fable `SPRE/RelV` proposal is replaced by **Robust Visual Evidence (RVE)**: noise-corrected squared residual energy in linear RGB between repeated, settled sheep-present and sheep-absent renders, measured inside an L0-derived sheep support mask and normalized to L0 at the same placement. RVE is image-only and is frozen before any Experiment III model inference. It is a calibrated evidence coordinate, not a claim that Minecraft glass implements Bayesian observation noise.

The primary inferential unit is the trajectory identity (`N=25`), not the 2,375 target rows or 125 captures. The primary family contains three ordered-observability estimands. MineWorld-versus-current-pixel behavior, temporal representations, context age, baselines, and the three-layer panel are secondary. Arbitrary qualification cliffs—including the proposed discontinuity ratio of 3 and an expected opaque-failure gate—are removed.

## 2. Scientific purpose and relationship to prior work

Regime A-prime established a valid, paired, single-layout apparatus at speed 2.0 blocks/s and process noise `q=0.05`. It showed that layer-4 position decoding was accurate when the sheep was visible and severely inaccurate on 19 qualified fully occluded rows. Experiment II reused those same 25 development identities and outcomes to search 11 layers and spatial representations. It selected `L19 | COARSE_2X6_CONCAT | CURRENT`, which remained severely inaccurate under full occlusion (`R²=-13.8263`, RMSE `2.0711` blocks) while retaining strong visible controls.

Experiment III is not another search. It prospectively applies that one selected readout to a fresh cohort and fills the unmeasured region between full visibility and full occlusion. Historical t01–t25 results remain manuscript context and external continuity anchors only; they are not Experiment III production members and are not pooled into Experiment III inference.

### 2.1 Primary scientific question

How does held-out current-position error from the frozen L19 coarse-current linear readout change as an outcome-blind, image-measured coordinate of direct sheep evidence decreases from L0 to L4?

### 2.2 Secondary scientific questions

1. Does any partial-evidence condition degrade relative to L0?
2. Is there an additional error increase from the heaviest qualified partial condition L3 to opaque L4?
3. How does the frozen MineWorld readout compare with a linear current-frame raw-pixel baseline?
4. Do `CURRENT_MINUS_PREVIOUS` or `TWO_FRAME_CONCAT` improve on `CURRENT` without new forwards?
5. Is the opaque-condition error pattern consistent with the last potentially informative frame leaving the 16-pair context?
6. How do last-seen, constant-velocity, training-mean, and time-only baselines contextualize model error?
7. Do descriptive layers 4 and 10 show the same condition ordering as layer 19?

### 2.3 Explicit exclusions

The experiment does not test calibrated posterior uncertainty (U2), uncertainty dynamics (U3), causal intervention or steering (U4), a process-noise grid, another speed, another layout, player-turn-away, Regime B, another checkpoint/model size, broad layer or representation searches, BEST-K, nonlinear MLP rescue, a resource-pack opacity intervention, multi-layer glass, glass panes, perforated/geometric fallback walls, or reveal-recovery dynamics. Deterministic glass attenuation is not interpreted as principled observation noise.

## 3. Cohort, identity, motion, and folds

### 3.1 Production cohort

Phase 1 must materialize and hash-bind exactly 25 new production identities named in a new Experiment III namespace (for example `e3_t01`–`e3_t25`). None may share a seed with A-prime/Experiment II t01–t25 or the engineering pilots. The roster contains 13 left-to-right and 12 right-to-left identities and five fixed outer folds of five identities, with each fold as direction-balanced as arithmetically possible.

Generation is deterministic from a Phase-1-frozen master salt and uses NumPy `Generator(PCG64)`. Candidates are admitted in deterministic order using only state, geometry, and timing—not frames, activations, or model outcomes. A candidate must:

- contain 180 schedule-covered model frames at 20 Hz with no lane clamp;
- use speed `2.0` blocks/s and `q=0.05` blocks²/s;
- reproduce the exact immutable noise schedule and path hash;
- retain complete history for the direction-specific A-prime causal FIR;
- provide at least 19 consecutive material-independent `EXTENT_FULLY_OCCLUDED` target rows under the original wall footprint;
- provide nonzero within-identity target variation and satisfy the Phase-1-frozen minimum target standard deviation of `0.10` blocks; and
- preserve exact current-FIR labels and target indices across all five conditions.

The first 19 eligible rows in ascending model-frame order are the production target window. There is no outcome-derived phase adjustment. The two pilot identities are generated by the same rules but are permanently excluded from production and all scientific inference.

### 3.2 Identity pairing and folds

Within identity, L0–L4 share the exact seed, standard-normal draws, scaled noise schedule, signed speed, 180-frame path, direction, start, causal FIR kernel, FIR-aligned labels, target indices, and outer fold. Only wall presence/material and its recorded scientific condition differ. Capture failures may be retried only for the same frozen identity-condition unit. No replacement identity may be minted after outcomes exist.

Outer test folds are identity-disjoint and shared across conditions, representations, baselines, and targets. Four fixed inner identity rotations operate only inside each outer training set for ridge-alpha selection. Every preprocessing/scaler quantity is fit on the relevant outer/inner training identities only.

### 3.3 Frozen physical settings

| Quantity | Experiment III value |
|---|---:|
| Layout | `layout_01` only |
| Minecraft | 1.16.5 |
| Capture rate / `dt` | 20 Hz / 0.05 s |
| Speed | 2.0 blocks/s |
| Process noise | `q=0.05` blocks²/s |
| Frames per capture | 180 |
| Sheep lane | world `x∈[-8,8]`, `y=4`, `z=6` |
| Camera feet | `(0.5, 4.0, -5.5)` |
| Camera eye | `(0.5, 5.6200000048, -5.5)` |
| Camera orientation / FOV | yaw 0, pitch 0, roll 0 / 70° |
| As-built wall volume | `x∈[-3,4]`, `z∈[2,3]`, `y∈[4,7]` |
| Wall construction | one full-cube block thick, three blocks high |
| Target | adult, AI-disabled, silent, persistent, invulnerable magenta sheep |

Speed 2.0 is chosen because A-prime, Experiment II, and the current manuscript all use and report 2.0. The 1.5 constant in the original checked-out Regime A generator is an implementation-base default, not the most recent scientific apparatus. Fresh qualification is therefore performed at 2.0; target windows may not be inherited from a 1.5 simulation.

## 4. Conditions and visibility semantics

### 4.1 Five scientific conditions

| ID | Physical condition | Scientific meaning | Target eligibility |
|---|---|---|---|
| L0 | no blocks in the original wall cells | fully visible anchor | frozen counterfactual footprint rows |
| L1 | one full-cube layer of P0-selected stained glass | high partial evidence | same rows |
| L2 | one full-cube layer of P0-selected stained glass | medium partial evidence | same rows |
| L3 | one full-cube layer of P0-selected stained glass | low but measurable partial evidence | same rows |
| L4 | one full-cube layer of `minecraft:stone` | opaque anchor | same rows |

L1–L3 are selected only from Phase-1-frozen Minecraft 1.16.5 full-cube stained-glass block IDs. The candidate roster is the 12 non-target-colored blocks `white`, `orange`, `light_blue`, `yellow`, `lime`, `gray`, `light_gray`, `cyan`, `blue`, `brown`, `green`, and `black`, each as `minecraft:<color>_stained_glass`. Magenta, pink, purple, and red are excluded prospectively because their target-adjacent hue can contaminate the magenta measurement channel. Clear glass is an engineering diagnostic only because Minecraft 1.16.5 renders clear glass through the cutout path while stained glass is translucent. Glass panes, repeated layers, air gaps, mixed-color stacks, and hole-pattern walls are not eligible: they alter geometry, surface count, or rendering family.

If a valid three-level ladder cannot be selected from the one-layer candidate roster, P0 returns `NO_VALID_LADDER` and production stops. It does not silently introduce a new wall design.

### 4.2 Separate geometry, image evidence, and condition labels

Each aligned row carries separate fields:

- `condition_id`: one of L0–L4;
- `wall_present`: physical block presence;
- `wall_block_id`: exact registry ID or `minecraft:air`;
- `counterfactual_extent_class`: `EXTENT_FULLY_VISIBLE`, `EXTENT_PARTIAL`, or `EXTENT_FULLY_OCCLUDED`, computed against the unchanged original wall volume regardless of condition;
- `server_geometric_status`: the runtime center-ray diagnostic, never a target selector;
- `magenta_status` and magenta area: image diagnostics, never a target selector;
- `rve_condition_score`: P0-frozen condition-level visual-evidence coordinate; and
- `target_eligible`: equality to a frozen manifest target row plus complete FIR/path/alignment and `counterfactual_extent_class=EXTENT_FULLY_OCCLUDED`.

“Behind the wall footprint” therefore does not mean “no visible evidence.” L0–L3 can have direct evidence on the same counterfactual-occlusion row. Neither magenta detectability nor RVE can admit or remove a production target row.

## 5. P0 outcome-blind visibility calibration

P0 is a bounded image-calibration stage conducted before any Experiment III MineWorld inference. It may select materials but may not read activations, decoder errors, pilot scientific outcomes, or historical material-performance outcomes.

### 5.1 Robust Visual Evidence (RVE)

Let `P(c,p,b)` and `A(c,p,b)` be settled 640×360 source-RGB frames for condition/candidate `c`, static placement `p`, and replicate block `b`, with the sheep present and absent respectively. Source sRGB channels are converted to linear light. For each of nine Phase-1-frozen placements spanning the target corridor, capture two ABBA blocks and at least eight settled frames per state per block. Coordinate-wise frame medians produce robust present and absent images.

An outcome-independent sheep support mask `M_p` is derived once from the L0 present-minus-absent residual: pixels above the frozen L0 noise threshold are unioned across replicate blocks and dilated by two pixels. The same `M_p` is used for every candidate. The authoritative projected sheep center may gate gross placement errors, and the magenta detector may verify target presence, but neither defines residual magnitude or candidate ordering.

For condition `c`, placement `p`, and block `b`, define

`D(c,p,b) = Σ[u∈M_p] ||P_lin(c,p,b,u) - A_lin(c,p,b,u)||²₂`.

Let `N(c,p,b)` be the same energy from a deterministic split-half comparison of repeated absent frames. Define excess sheep-attributable energy

`E(c,p,b) = max(D(c,p,b) - N(c,p,b), 0)`

and normalized evidence

`RVE(c,p,b) = E(c,p,b) / E(L0,p,b)`.

The placement score is the median over replicate blocks, and the condition score `V_c` is the median over nine placements. L0 is defined as `V_0=1`; L4 is measured and expected near zero, not forced to zero. Uncapped values are retained for QA. This metric measures the image perturbation attributable to inserting the sheep in a matched rendered scene. It does not claim silhouette recovery, perceptual equivalence, posterior variance, or pure opacity.

Linear RGB is used instead of Lab ΔE because squared radiometric residual has a direct energy interpretation, requires no new color-science dependency, and supports an explicit absent-frame noise subtraction. The ABBA sequence, medians, fixed camera, zero random ticks, fixed noon/weather, warm-up, framebuffer hash, and outside-mask residual gate control remeshing, antialiasing, and client timing artifacts.

### 5.2 P0 material selection rule

Candidate selection uses only RVE and image QA. A valid ladder must contain three distinct eligible blocks ordered L1>L2>L3 and satisfy all of:

- L1 median RVE in `[0.60, 0.85]`;
- L2 median RVE in `[0.30, 0.55]`;
- L3 median RVE in `[0.08, 0.25]`;
- adjacent median separation at least `0.12`;
- the same strict order at at least eight of nine placements;
- a deterministic 10,000-resample placement bootstrap lower bound above zero for both adjacent differences;
- L3 excess-energy-to-noise ratio at least 5 at at least eight placements;
- within-placement replicate coefficient of variation at most 0.15 where the mean is nonzero; and
- outside-mask present/absent residual no larger than the Phase-1-frozen background tolerance.

Among valid triples, choose the lexicographically earliest triple after minimizing squared distance to targets `(0.725, 0.425, 0.165)`, with candidate registry IDs as the tie-break. These zones are engineering design constraints, not scientific success criteria. All candidate scores, failures, masks, images, code hash, and the selected triple are retained. If no triple passes, production is blocked and the design returns to authority adjudication.

### 5.3 Production drift sentinels

Before and after each condition batch, repeat three frozen sentinel placements. Their image-only RVE order must match P0 and each score must lie inside the Phase-1-frozen repeatability envelope derived from P0. A failed sentinel invalidates only the affected as-yet-unmodeled capture batch for technical retry; it cannot alter materials, target rows, or analysis.

## 6. P1 engineering pilot and P2 freeze

P1 uses two sacrificial fresh identities (`p90`, `p91` or equivalently frozen names), one per direction, in all five conditions: 10 captures, 190 target rows, and 190 forwards. It verifies material switching, arena-cache invalidation, exact block receipts, camera and target identity, path replay, FIR labels, counterfactual target semantics, frame/action timing, one-forward layer hooks, both temporal slices, array shapes/dtypes, durability, and resume. Pilot outputs are permanently excluded from production inference.

P1 is not allowed to tune the scientific metric, material ladder, readout, alpha grid, representations, estimands, thresholds, or cohort. If the pilot exposes an engineering defect, Phase 1 authority must define the repair-and-repilot rule; no production unit launches on a failed pilot.

P2 is the future preproduction freeze. Before production model inference, it must hash-bind the final P0 material receipt, exact 25-identity manifest, pilot exclusion list, capture order, code/source closure, Minecraft/mod/runtime identities, checkpoint/VAE, preprocessing identity, direction-specific FIR kernels, target rows and labels, condition schema, folds, alpha grid, representations, metrics, analysis seed, storage inventory, retry/attrition policy, and all stop rules. Phase 0 does not perform or authorize P0, P1, P2, or production.

## 7. Production capture design

### 7.1 Matrix and order

The full matrix is `25 identities × 5 conditions = 125` production captures. Each capture has 180 frames and exactly 19 scored target rows, giving 2,375 production target rows. Capture order is frozen before outcomes using five blocks of five identities. Within each block, all five identities are captured under a condition before switching material; condition order follows a balanced five-period Latin rotation across blocks, and identity order within a condition block is frozen. This balances time/order while limiting expensive wall rebuilds to approximately 25 transitions.

Every material transition forces an arena rebuild and a complete observed block receipt. The arena-cache key must include condition and wall block ID. The capture may begin only after the standard warm-up, remesh settling, camera lock, exact target retention, and no-stale-frame checks pass.

### 7.2 Attrition and retries

Technical failure is defined without model outcomes: path/hash mismatch, missing frame/action/state, timing mismatch, wrong block receipt, camera drift, target identity failure, target-row mismatch, stale capture, durability failure, or sentinel failure. Retry the same unit only. Keep the first technically valid frozen attempt; retain all failed-attempt provenance.

The primary dataset is the complete five-way paired identity subset. With at least 15 complete identities, report the prespecified analysis with reduced precision and conspicuous attrition disclosure. With fewer than 15, do not make a graded Experiment III inferential claim. Conditions are not dropped reactively, identities are not replaced, and missing cells are not imputed. A Phase-1-frozen identity priority order controls schedule fallbacks, never observed performance.

## 8. FIR targets and context age

The prediction target is current sheep world-x in blocks aligned to the rendered model frame by the frozen direction-specific A-prime causal FIR. Labels are computed with the canonical normalized causal sum and require full FIR history. The FIR is measurement calibration inherited from the same speed-2.0 apparatus, not a learned outcome readout.

Target frames are the first 19 consecutive rows whose material-independent counterfactual rendered extent is fully occluded by the original wall footprint. These indices and FIR labels are frozen per fresh identity and applied unchanged to L0–L4.

For context analysis, define `a=1` at the first fully occluded target row and increment through `a=19`. Equivalently, `a` is ticks since the last row whose counterfactual extent was not fully occluded. With target context `[t-15,…,t]`, the last potentially informative pre-occlusion pair is present for `a≤15` and absent for `a≥16`. This is checked from explicit frame identities, not inferred from a generic `tau` label.

## 9. MineWorld preprocessing and one-forward extraction

The frozen MineWorld 700M_16f checkpoint, VAE, adapter, action conversion, and historical preprocessing bytes are unchanged. The source PNG is opened as RGB and passed through the already bound preprocessing path. Experiment III does not “fix” or reinterpret the historical RGB/BGR channel-order behavior; all conditions use identical code and the exact preprocessing identity is hash-bound. RVE is computed from source RGB frames, not model-normalized tensors.

Each target forward contains the 16 complete visual/action pairs for model frames `[t-15,…,t]`. Each pair is 336 visual tokens followed by 11 action tokens, so the hooked sequence is `[1,5552,2048]` at every decoder layer.

| Slice | Pair ordinal | Inclusive positions | Python slice | Shape per selected layer |
|---|---:|---:|---:|---:|
| PREVIOUS | 14 | 4,858–5,193 | `[4858:5194]` | `[1,336,2048]` |
| CURRENT | 15 | 5,205–5,540 | `[5205:5541]` | `[1,336,2048]` |

Positions 5,194–5,204 are pair-14 action tokens and are excluded. Pair-15 action tokens occupy 5,541–5,551 and are excluded. Decoder causality means the pair-14 residual cannot attend to pair 15 even though both are harvested after the same teacher-forced call. The current branch already installs scoped hooks on all 20 decoder modules in one forward. It may transiently validate all 20, but only layers `{4,10,19}` and the two explicit visual slices are serialized. No extra inference is required for PREVIOUS or for multiple layers.

## 10. Activation inventory, shapes, and representations

For each capture, layer, and temporal slice, store one NumPy array of shape `[19,336,2048]`, dtype little-endian float16. This is 19 logical row tensors of shape `[336,2048]`. Every file records trajectory, condition, target indices, slice, layer, hook site, token-position hash, preprocessing/checkpoint identities, shape, dtype, byte size, and SHA-256.

The 336 visual tokens form the frozen 14×24 MineWorld grid. The `COARSE_2X6_CONCAT` representation means-average-pools each non-overlapping 7×4 token cell and concatenates 12 width-2,048 vectors, yielding 24,576 features. It is implemented and tested directly from the consolidation contract because the exact Experiment II source commit is not present in this checkout.

Representation roles are:

| Representation | Definition | Role |
|---|---|---|
| CURRENT | coarse pooling of CURRENT | frozen primary at L19; descriptive at L4/L10 |
| CURRENT_MINUS_PREVIOUS | coarse(CURRENT) − coarse(PREVIOUS) | secondary temporal diagnostic at L19 |
| TWO_FRAME_CONCAT | `[coarse(PREVIOUS), coarse(CURRENT)]` = 49,152 features | secondary temporal diagnostic at L19 |

No global mean, BEST-K, alternative grid, layer search, PCA selection, or nonlinear rescue is permitted.

## 11. Readouts and baselines

### 11.1 Frozen neural readout

Fit condition-specific ridge coefficients with a shared recipe: alpha in `{0.1,1,10,100,1000}`, unpenalized intercept, training-only feature standardization, high-dimensional dual solve, five frozen outer identity folds, and four frozen inner identity rotations. Alpha is selected inside each outer training set by the predeclared identity-macro inner validation criterion with the smallest-alpha tie-break. Held-out predictions are generated once and locked before statistics are opened.

The primary cell is `L19 | COARSE_2X6_CONCAT | CURRENT`. L4 and L10 depth cells and the two temporal cells cannot replace or rescue it.

### 11.2 Current-frame pixel baseline

Resize each source RGB target frame to 48×28 with a frozen area interpolation, flatten 4,032 values, standardize on training identities, and fit the same grouped nested ridge recipe. This baseline asks whether a linear readout of **current pixels** tracks the evidence curve. It is not a capacity-matched neural comparison and does not represent all possible pixel-history models. Claims must use the phrase “linear current-frame pixel baseline.”

### 11.3 Motion and clock baselines

- **Last-seen:** hold the FIR-aligned world-x from the last counterfactual row that was not fully occluded.
- **Constant velocity:** fit velocity from the last 10 FIR-aligned non-occluded positions and extrapolate to the target tick; the window and arithmetic are frozen.
- **Training mean:** outer-training mean target, stratified only by direction if Phase 1 confirms that stratification is estimable in every fold.
- **Time-only:** outer-training linear model `[1, direction sign, a, direction×a]`.

The last-seen and constant-velocity baselines are oracle-state heuristics, not model inputs. They are identical across L0–L4 within identity and contextualize motion difficulty; they are not evidence that the model had access to authoritative state.

## 12. Metrics and statistical plan

For identity `i` and condition `c`, compute held-out `RMSE_ic`, MAE, and R² from its 19 rows. RMSE is the primary error metric because per-identity R² can be unstable when within-window target variance is small. Report condition-level identity-macro RMSE/MAE/R² and pooled metrics only as clearly labeled secondary descriptions.

Let `V_c` be the frozen RVE condition score and `O_c=1−V_c`. For each identity, derive:

1. **Ordered evidence-response slope (`S_i`):** ordinary least-squares slope of `RMSE_ic` on `O_c` over L0–L4. Positive values mean error increases as evidence weakens.
2. **Partial degradation (`Dpartial_i`):** mean RMSE over L1–L3 minus L0 RMSE.
3. **Opaque increment (`Dopaque_i`):** L4 RMSE minus L3 RMSE.

These three identity-level estimands form `FINAL_PRIMARY_ANALYSIS_FAMILY`. Their directional hypotheses are positive. Report means, standard errors, one-sided repeated-measures t-test p-values, and two-sided 95% identity-bootstrap confidence intervals. Apply Holm correction across exactly these three p-values. The confidence intervals remain estimates, not pass/fail gates; there is no omnibus experiment-success label.

The identity bootstrap uses `B=10,000` whole-identity resamples with all five conditions, predictions, representations, and rows kept together. Phase 1 freezes the seed. Captures and rows are never resampled as independent units.

### 12.1 Secondary families

`FINAL_SECONDARY_ANALYSIS_FAMILY` contains:

- **MineWorld versus pixel:** identity-level mean over L1–L3 of `RMSE_pixel − RMSE_MW`; two-sided 95% identity-bootstrap interval. L0 and L4 differences are descriptive. No “internal support beyond pixels” claim is allowed unless the partial-condition interval excludes zero in favor of MineWorld, and even then the claim is limited to the frozen linear current-pixel baseline.
- **Temporal rescue:** for each identity, average over L1–L4 the RMSE reduction of `CURRENT_MINUS_PREVIOUS` versus CURRENT and of `TWO_FRAME_CONCAT` versus CURRENT. Use two one-sided paired t tests with Holm correction across these two comparisons plus 95% identity-bootstrap intervals. Condition-specific temporal deltas are descriptive.
- **Context boundary:** report RMSE in `a=1–5`, `6–10`, `11–15`, and `16–19`. The one prespecified descriptive boundary interaction is `[(L4 a16–19 − L4 a12–15) − (mean L1–L3 a16–19 − mean L1–L3 a12–15)]`, summarized by an identity-bootstrap interval. It is mechanistic consistency evidence, not a causal forgetting test, because age and target position/time remain coupled.
- **Baselines:** paired RMSE differences from last-seen, constant-velocity, training-mean, and time-only with identity-bootstrap intervals; descriptive, with no qualification gate.
- **Depth:** L4 and L10 condition curves and slopes; descriptive correlated checks only.

No secondary result may change the primary readout or primary-family interpretation.

### 12.2 Removed or revised gates

The following Fable elements are removed: discontinuity ratio `≥3`; opaque R²/RMSE reproduction band; four-statistic Holm family including pixels; B=199 per-condition decoder nulls; all-row pseudo-replication; MLP stretch; outcome-dependent condition dropping; and an overall pass/fail qualification verdict. The partial and opaque contrasts survive as effect estimates against zero. The context boundary is computed from explicit last-evidence age and adjacent four-row windows, not assumed from a generic tau bin. Historical `R²>0` and RMSE `≤0.50` thresholds may appear as manuscript reference lines only, not Experiment III success gates.

The L0 positive control has one meaningful interpretability check: the 95% identity-bootstrap interval for its RMSE improvement over the outer-training mean must exclude zero in the favorable direction. Failure does not trigger redesign or replacement; it limits the result to an apparatus/readout failure report. No expected L4 failure is required.

## 13. Fail-closed technical criteria

Production analysis is blocked until all included units satisfy:

- clean, hash-bound source/runtime/checkpoint/preprocessing and exact manifest identities;
- exact wall cells and block ID receipt, with material in the arena cache key;
- fixed camera, FOV, framebuffer, lighting, weather, and target identity/state;
- exact 180-frame state/action/frame cardinality and lockstep timing;
- exact immutable path/noise replay and causal-FIR labels;
- exact 19 frozen target indices and condition-independent extent eligibility;
- exact one-forward layer and token-slice identities;
- arrays `[19,336,2048]`, float16, finite, expected byte size, and SHA-256;
- P0/P2 RVE sentinel stability;
- durable copy plus read-back hash before local deletion; and
- a complete five-condition paired subset meeting the attrition rule.

Scientific signs or magnitudes are never technical gates. Failures are classified before outcome access where possible. Analysis code emits immutable held-out predictions and a provenance receipt before summary statistics.

## 14. Engineering reuse plan

| Component | Decision | Experiment III action |
|---|---|---|
| Multi-layer scoped hooks | ALREADY_PRESENT | Use the current 20-layer verified manager; persist layers 4/10/19 only |
| Layer-index verification | ALREADY_PRESENT | Retain complete 0–19 discovery and callback checks |
| Current slice | ALREADY_PRESENT | Use explicit final `FrameTokenSpan` |
| Previous slice | REIMPLEMENT_MINIMALLY | Select explicit penultimate span and verify numeric positions |
| Activation inventory checks | REIMPLEMENT_MINIMALLY | Generalize hard-coded 20-layer/current inventory to 3 layers × 2 slices |
| A-prime rendered-extent truth | PORT | Port the small detector-independent extent module and tests |
| A-prime causal FIR sum/binding | PORT | Port canonical causal label computation and frozen direction kernels |
| `COARSE_2X6_CONCAT` | REIMPLEMENT_MINIMALLY | Implement 14×24→2×6 pooling from the consolidation contract with invariance tests |
| Temporal formulas | REIMPLEMENT_MINIMALLY | Deterministic vector difference/concatenation after extraction |
| Grouped folds and inner rotations | ALREADY_PRESENT | Generate fresh fixed folds; retain identity-only separation |
| Standardized dual ridge | ALREADY_PRESENT | Use existing training-only standardized ridge machinery |
| Baselines | ALREADY_PRESENT / MINIMAL | Reuse last-seen, constant-velocity, mean/time logic; add pixel baseline |
| Identity bootstrap | ALREADY_PRESENT | Retain 10,000 whole-identity resamples |
| Experiment II B=49 funnel null | DO_NOT_PORT | It answers a searched-family question that Experiment III does not ask |
| Tensor hash/durability | ALREADY_PRESENT / MINIMAL | Retain atomic write, SHA-256, read-back; simplify inventory schema |
| Resume | ALREADY_PRESENT | Resume exact manifest units only; no identity replacement |
| Source freeze/hash binding | PORT LIGHTLY | One reviewed source closure, manifest hashes, and launch receipt |
| Experiment II lifecycle superstructure | DO_NOT_PORT | Omit recovery-era multi-authority ceremony unrelated to correctness |

The exact Experiment II implementation commit named by its consolidation is not available in this repository object database. Phase 1 must not pretend to literal-port it. The coarse/temporal behavior is small enough to implement from the canonical consolidation specification and validate with unit fixtures; if an authenticated historical artifact becomes available, it may be used only for equivalence testing.

## 15. Exact workload and storage

One logical row/layer/slice tensor is `[336,2048]` float16:

`336 × 2048 × 2 = 1,376,256 bytes`.

One persisted capture/layer/slice `.npy` array is `[19,336,2048]`:

`19 × 1,376,256 + 128-byte NumPy header = 26,148,992 bytes`.

| Scope | Captures | Target rows / forwards | Logical row tensors | `.npy` arrays | Exact activation bytes | GiB |
|---|---:|---:|---:|---:|---:|---:|
| Production | 125 | 2,375 | 14,250 | 750 | 19,611,744,000 | 18.2649 |
| P1 pilot (excluded) | 10 | 190 | 1,140 | 60 | 1,568,939,520 | 1.4612 |
| Total if pilot retained | 135 | 2,565 | 15,390 | 810 | 21,180,683,520 | 19.7260 |

“Logical tensor” counts each row/layer/slice; serialized-file counts reflect the actual per-capture array layout. Exact bytes are activation arrays only. Raw PNGs, JSONL, checksums, temporary copies, and reports are additional; provision at least 30 GiB working space and 45 GiB if a local durability mirror is retained.

The extra PREVIOUS slice does not add forwards. Pure forward time projected from Experiment II's 0.69 s/forward is approximately 27 minutes for production, but preprocessing, hooks, 19.6 GB of writes, validation, and durability make **1.5–4 hours** the operational extraction envelope. Capture remains approximately **6–13 hours**, resumable and suitable for overnight execution. CPU analysis is **2–4 hours**. Fresh path generation is minutes of CPU work; engineering review, extent/FIR qualification, and manifest freeze add approximately **2–4 person-hours**, not another capture campaign.

## 16. Execution schedule and fallbacks

### 16.1 Normal schedule

| Date (2026) | Future phase work |
|---|---|
| Sun Aug 30 | Phase 0 design complete; no execution |
| Mon Aug 31 | Phase 1 authority, fresh cohort materialization, implementation, CPU/unit tests, P0 image calibration |
| Tue Sep 1 | P1 two-identity end-to-end pilot; repair/re-pilot if necessary; P2 freeze and separate authorization |
| Tue night–Wed Sep 2 | 125 captures; durable read-back; extraction |
| Wed Sep 2 | prediction lock, CPU analysis, result receipt |
| Thu Sep 3 | buffer, figures/tables, manuscript integration |
| Fri Sep 4 | writing only |
| Sat Sep 5 | submission buffer |

Target capture launch is Tuesday 20:00; target result lock is Wednesday 23:00; latest safe lock is Thursday 20:00.

### 16.2 One day behind

If the Phase-1-frozen clock trigger is crossed before production launch, retain all five conditions but restrict production to the first 20 frozen identities (100 captures) and persist layer 19 only. Retain CURRENT and PREVIOUS so temporal analyses remain possible. Report `N=20`; do not combine historical identities. This reduces capture, storage, and depth-panel work without changing the graded question.

### 16.3 Two days behind

If the second frozen trigger is crossed before launch, run the first 15 frozen identities across all five conditions (75 captures), layer 19, CURRENT only. This preserves a five-point evidence curve at reduced precision and drops temporal/depth analyses. It is preferable to a three-condition design because the primary question is curve shape.

### 16.4 Disaster fallback

If new capture cannot safely launch by the final trigger, Experiment III produces no new confirmatory result. A zero-capture archival analysis may add last-seen, constant-velocity, current-pixel, and correctly defined context-age descriptions to the existing Experiment II corpus, explicitly labeled post hoc/developmental. It may not be presented as the fresh Experiment III primary cohort or as evidence for glass/graded observability.

## 17. Manuscript interpretation matrix

| Major pattern | Permitted interpretation | Prohibited leap |
|---|---|---|
| Smooth error increase as RVE falls | Linear accessibility tracks the calibrated direct-evidence ladder in this apparatus | Universal psychometric law; posterior uncertainty |
| Partial conditions already near opaque | The selected linear representation is fragile even with measured residual evidence | The model has no hidden-object representation anywhere |
| L1–L3 strong, L4 sharply worse | Weak direct evidence supports the frozen readout; complete occlusion adds a discontinuity | A causal memory module has been identified |
| MineWorld parallels current pixels | The frozen neural and current-pixel linear readouts have similar condition response | MineWorld merely copies pixels in general |
| MineWorld exceeds current pixels | The frozen neural readout is more robust than this linear current-frame pixel baseline | It beats pixel histories, nonlinear vision, or all sensory baselines |
| Temporal representation improves | Position information is more linearly accessible in the predeclared two-frame transform | Calibrated belief state or causal object permanence |
| No temporal improvement | These two linear two-frame transforms do not rescue the selected family | No temporal information exists in MineWorld |
| Opaque boundary interaction near `a=16` | Pattern is consistent with finite-context loss in this coupled trajectory | Causal forgetting isolated from time/position |
| L0 control fails | Fresh apparatus/readout interpretability is limited; report the failure | Refit, replace identities, or tune thresholds after seeing it |

All claims remain limited to one layout, one speed/noise regime, one checkpoint, a fresh 25-identity cohort (or prespecified reduced cohort), the selected layers/representations, linear probes, and the calibrated wall family. A negative result is publishable and does not authorize model-wide absence claims. A positive partial-visibility result does not establish uncertainty calibration, causal use, or generalized object permanence.

## 18. Phase 1 authority freeze checklist

The final prospective preimplementation authority must freeze, at minimum:

1. the exact 25 production and two excluded pilot identities, seeds, directions, paths, hashes, folds, and priority order;
2. speed 2.0, `q=0.05`, `dt=0.05`, frame count, layout, camera, sheep, and wall cells;
3. the exact supported P0 candidate IDs, RVE code/equations, masks, placements, replicate order, thresholds, selection/tie-break rule, and failure state;
4. condition/material schema and exact builder/parser/cache/receipt behavior;
5. renderer-extent constant and classification code, FIR kernels, canonical sum, target indices, and labels;
6. capture Latin rotation, warm-up, retries, sentinels, attrition and deadline fallbacks;
7. MineWorld/checkpoint/VAE/source/preprocessing/action identities;
8. layers `{4,10,19}`, token indices, shapes, dtype, serialization, hashes, and durability/resume;
9. coarse pooling and temporal representation formulas;
10. folds, alpha grid, scaling, solver, raw-pixel and motion/clock baseline recipes;
11. held-out prediction lock, metrics, three primary estimands, secondary estimands, bootstrap seed/B, tests, and Holm families;
12. technical gates, L0 interpretability check, claim matrix, and explicit exclusions; and
13. the precise normal/reduced/disaster schedule triggers.

Phase 1 must treat this adjudicated successor—not the hash-bound historical Fable file—as the controlling design input. It may express these decisions as authority but may not silently change them.

## 19. Remaining uncertainties

Two uncertainties require bounded future tests but do not block authority construction:

1. Static code proves the Minecraft 1.16.5 stained-glass IDs exist and use the translucent render layer, but only the bounded P0 renders can establish whether this exact renderer/camera/sheep combination yields three stable RVE levels. The prospective `NO_VALID_LADDER` stop handles failure.
2. Exact Experiment II source bytes are unavailable in the current Git object database. The coarse representation and temporal transforms therefore require a small specification-based implementation plus fixtures, not an unverifiable claim of literal source reuse.

No production outcomes are needed to resolve either uncertainty. The design is ready to be converted into Phase 1 authority, but implementation and all execution remain unauthorized.
