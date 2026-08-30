# MineOcclude Experiment III — Phase 0 Design Adjudication

**Role:** evidence-backed design decision memo; not a final preimplementation authority  
**Implementation authorized:** no  
**Scientific execution authorized:** no

## Repository and input verification

The audited repository root was `C:/Users/lollo/MineOcclude-Exp3`. The current branch was `experiment/exp3-graded-partial-observability` at HEAD `4c8dd7c1a7e8ff6ac0042361579da27e362996fe`, tracking `origin/experiment/exp3-graded-partial-observability`. The worktree was clean before temporary document-inspection tooling was created. HEAD's direct parent and merge base with the expected original executable lineage was `fa31aaca8af2872663ea81a54d6ed3a51e9f7f0a`; no checkout or lineage change occurred. Remote `origin` was `https://github.com/atharv-santosh/MineOcclude.git`.

`preauthority_creation_inputs/README.md`, the manifest, and all five canonical sources were read in full. Both PDFs were rendered page-by-page and visually inspected; the proposal has nine pages and the manuscript five. The DOCX was inspected in document order, including 584 paragraphs and 13 tables; it contains no embedded figures, comments, footnotes, endnotes, or highlighted runs. Manifest byte counts and SHA-256 values all reproduced:

| Input | SHA-256 |
|---|---|
| `AAKA-Proposal-Final (4).pdf` | `67b6c8bdb8ee43fbe9ec931c83a2ee980d7c950da88e7b1324360c0f1283dab1` |
| `final-regime-a-prime-canonical-scientific-reconstruction.md` | `9f6d9fcf89f8a631c5660b8b9854c7f370c47673e35c837f8b1a444618d27277` |
| `MineOcclude_Experiment_II_Final_Scientific_Consolidation.md` | `7e4c70f59fd2cdb74703567c4db59f91d969c460a3b15f2b657b2c88fe1b5dcd` |
| `MineOcclude_Final_PreSubmission_Experiment_Design.docx` | `a55a26e15155cce5d98df153b46fdd7059345e335e3a1f599bc2f7eb30dcf33b` |
| `nickb_aaka.pdf` | `2ffffb12e1ef5d8d9da6d9601886035e35680cb2a3c77c69725044184f8f14f0` |

## Q1 — Reuse t01–t25 or generate fresh production identities?

DECISION:
`IDENTITY_DECISION = FRESH_25`. Generate and freeze 25 new speed-2.0 production identities, 13 LTR and 12 RTL, plus two excluded fresh pilot identities. Historical t01–t25 are evidence-only continuity anchors and are neither recaptured nor pooled.

STATUS:
RESOLVED

CONFIDENCE:
HIGH

SCIENTIFIC JUSTIFICATION:
Experiment II selected L19 and `COARSE_2X6_CONCAT` using outcomes from the same t01–t25 cohort. Reusing those identities for the principal Experiment III result would be a paired developmental follow-up, not clean prospective confirmation of the selected readout. A fresh cohort preserves exact five-way pairing within Experiment III while separating selection data from evaluation data. It adds no production capture count because Fable already proposed 25 identities × five conditions.

CODE EVIDENCE:
- `src/mineocclude/regime_a.py:614-634` — `fold_assignment` enforces exactly 25 identities and the 13/12 direction split.
- `src/mineocclude/regime_a.py:637-733` — deterministic candidate generation, seed derivation, path simulation, target-window qualification, and diversity are already CPU-local; the speed default must be parameterized.
- `src/mineocclude/regime_a.py:87-109` — paths are deterministic functions of seed, signed speed, `q`, and `dt`.
- `scripts/run_regime_a.py:235-272` — the capture context emits immutable noise and motion schedules bound to the spec.
- Commit-qualified A-prime `scripts/regime_a_prime_qualification_v0_2/build_manifests.py:224-250` — target windows and causal-FIR labels are materialized from frozen physical calibration before Stage-2 outcomes.

HISTORICAL EVIDENCE:
The A-prime reconstruction explicitly classifies the study `DEVELOPMENT_ONLY` and its units ineligible for confirmatory reuse (`preauthority_creation_inputs/final-regime-a-prime-canonical-scientific-reconstruction.md:1566-1566`). It records 25 speed-2.0 paired identities and identical wall/no-wall paths/labels (`:1574-1574`). Experiment II identifies M5 as a development screen and reused the same 25 identities (`preauthority_creation_inputs/MineOcclude_Experiment_II_Final_Scientific_Consolidation.md:127-129,158-162`).

IMPLEMENTATION CONSEQUENCE:
Parameterize the existing generator at 2.0; deterministically admit the first 25 candidates satisfying path, FIR-history, rendered-extent, 19-row, direction, no-clamp, and target-SD constraints. Freeze paths, hashes, FIR labels, target rows, folds, and priority order in Phase 1.

TIME/COST CONSEQUENCE:
Path generation is minutes of CPU work. Review, tests, manifest materialization, and freeze add approximately 2–4 engineering hours. Runtime P1 and production counts do not increase.

RISKS:
Fresh identities can expose unexpected path-edge cases. The outcome-blind generator gates and two fresh pilots bound that risk. The historical anchors lose exact within-identity comparability, but the fresh L0/L4 anchors are scientifically stronger.

REJECTED ALTERNATIVES:
`REUSE_25` was rejected because it reuses the selected family's development cohort. `HYBRID` was rejected because recapturing historical anchors adds capture/analysis complexity without improving the fresh primary comparison; historical results can be cited without recapture.

REQUIRED DESIGN-DOCUMENT CHANGES:
Replace every t01–t25 reuse statement, archived-anchor fallback, fold definition, identity label, target-window claim, and “only material changes” claim. Keep 125 production captures but make every row/count fresh.

REQUIRED PHASE-1 AUTHORITY LANGUAGE:
Bind the exact fresh roster, deterministic selection algorithm, master salt, pilot exclusions, directions, folds, seeds, paths, schedules, path hashes, target indices, FIR labels, target-SD floor, no-replacement rule, and deadline priority order before any Experiment III model outcome.

## Q2 — Can wall material be parameterized without changing geometry?

DECISION:
`WALL_PARAMETERIZATION = CLEAN_WITH_BOUNDED_CHANGE`. One full-cube stained-glass block may replace stone in exactly the same cells, but the current apparatus is not configurable: the material, runtime receipt, validation, command schema, and arena cache key are hard-coded. All must be changed together and piloted.

STATUS:
RESOLVED

CONFIDENCE:
MEDIUM

SCIENTIFIC JUSTIFICATION:
The physical wall is one block thick and three blocks high; substituting a full-cube block state preserves the occupied cells and sightline volume. Minecraft 1.16.5 contains clear glass and all 16 stained-glass full blocks. Static inspection of the pinned mapped client jar showed stained glass assigned to the translucent render layer and clear glass to cutout; consequently only one-layer stained-glass full blocks belong to the L1–L3 family. Actual evidence levels remain a bounded P0 rendering question.

CODE EVIDENCE:
- `fabric/mineocclude-mod/src/main/java/com/mineocclude/server/ArenaBuilder.java:23-31` — height is three and `wall` is fixed to `Blocks.STONE`.
- `fabric/mineocclude-mod/src/main/java/com/mineocclude/server/ArenaBuilder.java:211-220` — one material is written to the exact axis cells at one orthogonal block coordinate.
- `fabric/mineocclude-mod/src/main/java/com/mineocclude/server/Layouts.java:50-57` — `layout_01` geometry is fixed independently of block material.
- `fabric/mineocclude-mod/src/main/java/com/mineocclude/server/EpisodeConfig.java:39-58,61-108` — config contains wall geometry and scene, but no block/material identity.
- `fabric/mineocclude-mod/src/main/java/com/mineocclude/server/MineOccludeServer.java:116-134,288-326` — `startspec` has no material argument and forces `Scene.NORMAL`.
- `fabric/mineocclude-mod/src/main/java/com/mineocclude/server/EpisodeManager.java:885-919` — observation and validation hard-code `minecraft:stone`/`Blocks.STONE`.
- `fabric/mineocclude-mod/src/main/java/com/mineocclude/server/EpisodeManager.java:1138-1150` — arena rebuild caching omits material, so a material swap would otherwise leave the previous wall standing.
- `fabric/mineocclude-mod/gradle.properties:7-13` — runtime is pinned to Minecraft 1.16.5/Fabric 0.42.0.

HISTORICAL EVIDENCE:
A-prime's as-built wall was `x∈[-3,4], z∈[2,3], y∈[4,7]` (`preauthority_creation_inputs/final-regime-a-prime-canonical-scientific-reconstruction.md:1568-1568`). The A-prime failure history shows why builder/evaluator semantic synchronization is load-bearing (`:1197-1228,1630-1630`).

IMPLEMENTATION CONSEQUENCE:
Add a fail-closed wall-material enum/registry allowlist to the spec and `EpisodeConfig`; pass it directly through `startspec`; make `ArenaBuilder`, observed block receipts, expected-block validation, log schema, and cache key read the same value. L0 maps to air/no wall, L4 to stone, and L1–L3 to P0-frozen full-cube stained glass. Geometry code remains material-independent.

TIME/COST CONSEQUENCE:
Estimated 2–4 engineering hours plus tests and P1 switching validation. Material changes should be batched; the revised Latin-block order limits remesh transitions.

RISKS:
Translucent sorting, client remeshing, color blending, and evidence separation cannot be proven statically. Clear glass has a different render path. Multiple layers may cull internal faces and do not guarantee attenuation. Cache omission would silently invalidate conditions.

REJECTED ALTERNATIVES:
`CLEAN` was rejected because the present code cannot vary material safely. `NOT_CLEAN` was rejected because the exact coordinate loop cleanly accepts another full-cube `BlockState` after bounded plumbing. Clear glass, panes, multi-layer/air-gap stacks, mixed colors, and perforated fallback walls were rejected from production.

REQUIRED DESIGN-DOCUMENT CHANGES:
Define one-layer full-cube stained glass only; remove double-black and geometric fallback language; add exact material seam, cache/receipt requirements, P0 `NO_VALID_LADDER`, and batched switching.

REQUIRED PHASE-1 AUTHORITY LANGUAGE:
Freeze candidate registry IDs, exact block-state lookup, condition/material schema, unchanged cell coordinates, cache key, observed-block receipt, rebuild/settle gate, and fail-closed response to an unsupported ID or invalid ladder.

## Q3 — Is Fable's RelV calibration implementable and valid?

DECISION:
`VISIBILITY_METRIC_DECISION = REPLACE_RELV`. Replace Lab-ΔE SPRE/RelV with noise-corrected linear-RGB Robust Visual Evidence (RVE), defined in the adjudicated design.

STATUS:
RESOLVED

CONFIDENCE:
MEDIUM

SCIENTIFIC JUSTIFICATION:
Fable's core sheep-present/absent idea is sound, but its exact window and single residual are fragile. The repository projects a sheep center, not an authoritative rendered silhouette polygon; glass changes the visible background inside the silhouette; and exact single-frame subtraction is vulnerable to remesh/render timing. RVE retains outcome independence while using repeated settled medians, an empirical L0 support mask, absent-frame noise subtraction, linear-light energy, nine placements, and explicit repeatability/background gates. It measures sheep-attributable image perturbation, not opacity or Bayesian uncertainty.

CODE EVIDENCE:
- `src/mineocclude/regime_a.py:312-337` — homography projection supplies center/screen/token coordinates but not a renderer-authoritative silhouette support.
- `src/mineocclude/vision/magenta.py` and `scripts/run_regime_a.py:118-153` — the magenta detector can verify presence/area but is a thresholded color detector, unsuitable as the continuous primary x-axis.
- `fabric/mineocclude-mod/src/main/java/com/mineocclude/server/EpisodeConfig.java:55-59` — `NO_SHEEP` and `NO_WALL` states exist, permitting matched static scene construction after material plumbing.
- `fabric/mineocclude-mod/src/main/java/com/mineocclude/server/EpisodeManager.java:163-165` — noon/weather are controlled.
- `fabric/mineocclude-mod/src/main/java/com/mineocclude/client/MineOccludeClient.java:279-325` — capture is framebuffer-based with acknowledgement; settled repeated captures and queue/stale QA are implementable.
- `src/mineocclude/models/_mineworld_adapter_wave2.py:408-473` — model preprocessing performs OpenCV channel conversion/resize; RVE should remain on source RGB and avoid coupling calibration to model preprocessing.

HISTORICAL EVIDENCE:
A-prime found a structural disagreement between a center ray and an area detector and replaced it with renderer-derived extent (`preauthority_creation_inputs/final-regime-a-prime-canonical-scientific-reconstruction.md:1197-1201,1570-1572`). That history argues against another point/window shortcut.

IMPLEMENTATION CONSEQUENCE:
Implement a CPU-only P0 calibrator with ABBA present/absent blocks, linear-sRGB conversion, L0 masks, split-half noise, excess-energy normalization, placement bootstrap, candidate table, deterministic selection/tie-break, and `NO_VALID_LADDER`. Freeze P0 artifacts before any Experiment III model inference. Production uses the frozen condition score and image-only drift sentinels; RVE never selects target rows.

TIME/COST CONSEQUENCE:
P0 remains a bounded half-day task. It adds static frames but no production trajectory capture and no GPU/model inference.

RISKS:
Natural stained glass may not produce three valid levels; hue/context changes remain coupled to measured evidence; static poses may not cover every production pixel configuration. Claims are therefore limited to the calibrated wall family. Failure to find a ladder stops production rather than authorizing improvisation.

REJECTED ALTERNATIVES:
`KEEP_RELV_AS_WRITTEN` was rejected for unsupported silhouette/window and uncorrected render noise. `MODIFY_RELV` was rejected because replacing Lab ΔE, support construction, replication, noise handling, selection, and production use is substantively a replacement. Pure magenta area discards non-magenta silhouette/background replacement and saturates. Per-row subtraction from one occluder-only reference is not truly matched.

REQUIRED DESIGN-DOCUMENT CHANGES:
Replace every RelV/SPRE equation, target zone, occluder-only reference count, per-row evidence claim, calibration gate, and visibility-axis label with RVE and its bounded P0/sentinel procedure.

REQUIRED PHASE-1 AUTHORITY LANGUAGE:
Freeze the exact linearization, image dtype/range, placements, ABBA order, replicate/frame count, masks/dilation, noise estimator, equations, candidate set, target zones, separation/SNR/repeatability/background gates, 10,000-placement bootstrap seed, tie-break, artifacts, sentinels, and stop state.

## Q4 — Can CURRENT and PREVIOUS activations be extracted from one forward?

DECISION:
`TEMPORAL_EXTRACTION = VERIFIED_ONE_FORWARD`. Both slices and layers `{4,10,19}` are available from one 16-pair teacher-forced call per target.

STATUS:
RESOLVED

CONFIDENCE:
HIGH

SCIENTIFIC JUSTIFICATION:
The token map is explicit and validates every complete visual-then-action pair. A 16-pair context contains 5,552 tokens. PREVIOUS is pair ordinal 14, positions 4,858–5,193 inclusive; CURRENT is pair ordinal 15, positions 5,205–5,540 inclusive. Causal decoder masking prevents the earlier residual from reading the later pair. The existing runner already obtains all 20 layer residuals from one call and serializes the current span; adding the penultimate span changes selection/writes, not inference.

CODE EVIDENCE:
- `src/mineocclude/contracts/activation.py:32-34` — 336 visual tokens, 347 tokens/pair, 16 pairs.
- `src/mineocclude/models/_mineworld_adapter_wave3.py:637-720` — last 16 accepted frames, visual then action, explicit spans, all-ones mask, sequential positions.
- `src/mineocclude/models/mineworld_adapter.py:626-701` — each `FrameTokenSpan` must equal its context-relative complete 336+11 pair.
- `src/mineocclude/activations/pool.py:303-383` — validates pair order, full sequence coverage, and exact visual/action positions.
- `src/mineocclude/models/_mineworld_adapter_wave3.py:727-815` — one teacher-forced execution occurs inside the hook context and returns sequence-matched output.
- `src/mineocclude/activations/hooks.py:419-528` — one scoped manager registers and validates all 20 decoder hooks.
- `scripts/run_regime_a.py:929-939` — one forward per target already captures every layer and indexes the final span.
- `scripts/run_person_a_66_cell_production_extraction.py:399-430` — `_teacher_capture` returns complete multi-layer captures from one teacher call.

HISTORICAL EVIDENCE:
Experiment II completed 1,796 forwards and 19,756 layer tensors (`preauthority_creation_inputs/MineOcclude_Experiment_II_Final_Scientific_Consolidation.md:204-207,297-297`), demonstrating multi-layer one-call extraction. It did not evaluate temporal representations (`:225-225,367-367`).

IMPLEMENTATION CONSEQUENCE:
Use Python slices `[4858:5194]` and `[5205:5541]` after validating `spans[-2]` and `spans[-1]`; exclude intervening action tokens. Persist `[19,336,2048]` float16 arrays for two slices at three selected layers. Keep preprocessing and context identical.

TIME/COST CONSEQUENCE:
No new forwards. Production remains 2,375 forwards. Exact activation storage is 19,611,744,000 bytes (18.2649 GiB) in 750 `.npy` arrays; logical row tensor count is 14,250. Pilot plus production totals 2,565 forwards and 21,180,683,520 bytes (19.7260 GiB).

RISKS:
The existing hook manager transiently retains all 20 layers, increasing GPU memory even though only three are saved; this path has historical evidence but P1 must verify it. Incorrect span arithmetic could include action tokens, so explicit map equality—not magic constants alone—is a gate.

REJECTED ALTERNATIVES:
Multiple forwards were rejected as unnecessary and potentially context-divergent. Porting a separate Experiment II multi-layer hook was rejected because equivalent verified machinery is already present.

REQUIRED DESIGN-DOCUMENT CHANGES:
Retain one-forward claim with authoritative half-open indices, exact shapes, array/file distinction, recomputed bytes/GiB, and all-20-transient/three-layer-persist behavior.

REQUIRED PHASE-1 AUTHORITY LANGUAGE:
Bind pair identities, half-open slices, action exclusions, layer indices and conceptual hook site, context frames, sequence shape, causality/preprocessing identity, dtype, per-file shape/header size, inventory/hash checks, and no-extra-forward invariant.

## Q5 — Which statistics and gates should survive?

DECISION:
`FINAL_PRIMARY_ANALYSIS_FAMILY = {ordered RVE–RMSE slope, mean partial-minus-L0 RMSE, L4-minus-L3 RMSE}`, evaluated on identity-level held-out RMSE with Holm correction across three directional tests and 10,000 whole-identity bootstrap intervals.

`FINAL_SECONDARY_ANALYSIS_FAMILY = {MineWorld versus linear current-pixel contrast, two temporal rescue contrasts, context-boundary interaction, motion/clock baselines, descriptive depth panel}` with the limited families and roles in the revised design.

`REMOVED_OR_REVISED_GATES = {ratio≥3 removed; opaque expected-failure band removed; B=199 condition nulls removed; four-primary family reduced to three; pixel moved secondary; context statistic redefined by explicit last-evidence age; no overall pass/fail cliff; no MLP; no reactive condition dropping}`.

STATUS:
RESOLVED

CONFIDENCE:
HIGH

SCIENTIFIC JUSTIFICATION:
The primary question is an ordered within-identity response, not qualification of a searched candidate. Identity-level RMSE is stable and interpretable; identity R² is retained descriptively. The slope, partial degradation, and opaque increment directly address the three condition-shape questions. The ratio of two noisy contrasts has no scientific null at 3 and becomes unstable near a zero denominator. Expected opaque failure is an outcome prediction, not apparatus validity. Whole identities must remain intact in resampling.

CODE EVIDENCE:
- `src/mineocclude/regime_a_first25_analysis.py:78-113` — existing metrics macro-average by identity and separate pooled metrics.
- `src/mineocclude/regime_a_first25_analysis.py:226-251` — existing bootstrap resamples whole identities at `B=10,000`.
- `scripts/run_regime_a_first25_science.py:158-176` — nested alpha selection is performed inside outer training folds.
- `scripts/run_regime_a_first25_science.py:378-404` — historical analysis used 10,000 bootstrap replicates and treated intervals as non-gating.
- `src/mineocclude/regime_a.py:571-612` — the current B=49 derangement null is tied to the old identity/phase structure and is not a generic graded-condition test.
- `src/mineocclude/regime_a.py:450-471` — last-seen, constant-velocity, and training-mean baselines already exist.

HISTORICAL EVIDENCE:
Experiment II confirms that the independent N is 25, not row/capture counts (`preauthority_creation_inputs/MineOcclude_Experiment_II_Final_Scientific_Consolidation.md:158-158`). Its p=.02 coexisted with catastrophic absolute error, demonstrating why a p-value is not an adequacy gate (`:9-37`). A-prime tested no last-seen/CV/permutation null (`preauthority_creation_inputs/final-regime-a-prime-canonical-scientific-reconstruction.md:1602-1602`).

IMPLEMENTATION CONSEQUENCE:
Lock held-out predictions before summaries. Compute per-identity 19-row metrics, three primary estimands, one-sided repeated-measures t tests, Holm-3, and two-sided 10,000 identity-bootstrap intervals. Use Holm-2 only for the two predeclared temporal improvement tests. Treat pixels, baselines, depth, and context as specified secondaries; do not promote them based on results.

TIME/COST CONSEQUENCE:
Simpler than Fable's per-condition null plan; expected CPU analysis remains 2–4 hours.

RISKS:
Only five evidence levels make curve form coarse; RVE is condition-level; t tests assume identity-estimand regularity. Intervals and all identity points must be shown. The context boundary remains time/position-confounded and is expressly noncausal.

REJECTED ALTERNATIVES:
The discontinuity ratio, B=199 per-condition nulls, row-level tests, success qualification, and expected L4 failure gate were rejected. A four-primary family was rejected because the pixel comparator is not capacity/context matched. Exact condition-label randomization was not claimed because material potential outcomes are not made exchangeable merely by capture-order randomization.

REQUIRED DESIGN-DOCUMENT CHANGES:
Replace the old P1–P4 gates and every success/failure reference; rewrite temporal/context multiplicity; define identity metrics and estimands; limit pixel claims; replace attrition condition-drop ladder.

REQUIRED PHASE-1 AUTHORITY LANGUAGE:
Freeze prediction lock, identity metric formulas, RVE scores, primary/secondary estimands, hypothesis direction, t-test implementation, Holm families, bootstrap B/seed/unit, reporting, L0 interpretability check, and prohibited rescue/reselection.

## Q6 — What should be ported from Experiment II?

DECISION:
`EXP2_REUSE_MATRIX` is the following bounded architecture.

| Candidate | Classification | Source/evidence and rationale |
|---|---|---|
| Multi-layer hooks | ALREADY_PRESENT | `src/mineocclude/activations/hooks.py:177-309,419-528`; verified 20-layer discovery/capture already on this base |
| Layer-index verification | ALREADY_PRESENT | same source; exact 0–19 group and callback completeness |
| Activation tensor verification | REIMPLEMENT_MINIMALLY | `src/mineocclude/regime_a_execution.py:62-97` is hard-coded to old 20-layer/current inventory; generalize to 3×2 |
| `COARSE_2X6_CONCAT` | REIMPLEMENT_MINIMALLY | canonical contract at Experiment II consolidation `:220-223`; exact source commit unavailable locally |
| CURRENT | ALREADY_PRESENT | `scripts/run_regime_a.py:929-939` final explicit span |
| CURRENT_MINUS_PREVIOUS | REIMPLEMENT_MINIMALLY | deterministic transform from two verified slices |
| TWO_FRAME_CONCAT | REIMPLEMENT_MINIMALLY | deterministic transform from two verified slices |
| Grouped CV | ALREADY_PRESENT | `src/mineocclude/regime_a.py:614-634`; fresh fold roster required |
| Nested alpha selection | ALREADY_PRESENT | `src/mineocclude/regime_a_first25_analysis.py:27-70`; `scripts/run_regime_a_first25_science.py:158-176` |
| Standardized dual ridge | ALREADY_PRESENT | `src/mineocclude/probes/ridge.py:192-223` |
| Controls | REIMPLEMENT_MINIMALLY | L0/L4 are fresh conditions; retain control logic without old outcome bands |
| Bootstrap | ALREADY_PRESENT | `src/mineocclude/regime_a_first25_analysis.py:226-251` |
| Experiment II permutation funnel | DO_NOT_PORT | selection-aware B=49 answers a searched-family question absent here |
| Tensor durability checks | REIMPLEMENT_MINIMALLY | retain SHA/read-back; simplify hard-coded inventory |
| Resume logic | ALREADY_PRESENT | `src/mineocclude/regime_a_execution.py:204-312` exact-unit restart/resume |
| Source freeze/hash binding | PORT LIGHTLY | one reviewed source closure/manifest/launch receipt materially protects provenance |
| Huge lifecycle gate hierarchy | DO_NOT_PORT | recovery-era governance adds deadline risk without changing scientific validity |

STATUS:
RESOLVED

CONFIDENCE:
HIGH

SCIENTIFIC JUSTIFICATION:
Reuse is selected by whether it prevents wrong layers, leakage, corrupt arrays, irreproducible paths, or lost work. Experiment II's exhaustive lifecycle hierarchy is not itself scientific evidence and should not be copied wholesale. The exact Experiment II source commit (`6db5b…`, as named by the consolidation) is not present in the current object database, so claims of literal code porting would be false.

CODE EVIDENCE:
- Locations are embedded in the matrix.
- `scripts/run_person_a_66_cell_production_extraction.py:399-430` confirms current one-call multi-layer machinery.
- `src/mineocclude/activations/pool.py:303-383,437-556` provides exact visual selection and safe mean pooling primitives.
- `src/mineocclude/regime_a_execution.py:100-201` provides durable local/remote inventory validation worth retaining in compact form.

HISTORICAL EVIDENCE:
Experiment II extracted 19,756 objects with independent inventory verification (`preauthority_creation_inputs/MineOcclude_Experiment_II_Final_Scientific_Consolidation.md:204-207,297-297`) but also records multiple software/governance repair epochs before a scientifically clean terminal run (`:551-553`). Coarse beat global at every sampled layer and L19 advanced (`:309-360`).

IMPLEMENTATION CONSEQUENCE:
Build a compact Experiment III runner around existing capture, adapter, hook, grouped-ridge, hash, and resume code. Port the small A-prime measurement semantics separately (Q9). Reimplement coarse pooling and temporal vector arithmetic with unit tests and a fixed synthetic 14×24 grid fixture.

TIME/COST CONSEQUENCE:
Avoiding the lifecycle superstructure keeps implementation within approximately one workday plus P0/P1. Compact provenance still protects source, manifest, checkpoint, arrays, and resume.

RISKS:
Specification-based coarse reimplementation could transpose the 14×24 grid. Tests must assert exact 7×4 cells, concatenation order, and 24,576 dimensions. Simplification must not remove capture/readback hashes or unit identity.

REJECTED ALTERNATIVES:
Whole-pipeline porting was rejected as unavailable and disproportionate. Reusing Experiment II's selected-family null was rejected as scientifically mismatched. Rewriting hooks/ridge from scratch was rejected because verified implementations exist.

REQUIRED DESIGN-DOCUMENT CHANGES:
Replace generic “inherit Experiment II machinery” language with the explicit matrix, disclose unavailable source, and make small reimplementations/test obligations concrete.

REQUIRED PHASE-1 AUTHORITY LANGUAGE:
Name exact reused source files/hashes, reimplemented formulas/tests, minimal provenance artifacts, inventory/resume invariants, and excluded lifecycle/null machinery.

## Q7 — Regime A speed 1.5 versus A-prime/Fable speed 2.0

DECISION:
`EXP3_SPEED_BLOCKS_PER_SECOND = 2.0`.

STATUS:
RESOLVED

CONFIDENCE:
HIGH

SCIENTIFIC JUSTIFICATION:
The latest qualified apparatus, Experiment II selection evidence, and the current manuscript all use 2.0. Retaining the original implementation default 1.5 would create a new speed, break direct continuity with the selected L19/coarse family, and require its own target qualification. Fresh identities remove the only possible rationale for retaining 1.5—the old generator's exact paths.

CODE EVIDENCE:
- `src/mineocclude/regime_a.py:24-31` — current original-base constant is 1.5 and `q=0.05`; this must not remain implicit.
- `src/mineocclude/regime_a.py:87-109,637-733` — speed directly changes simulated path and therefore target-window qualification.
- `fabric/mineocclude-mod/src/main/java/com/mineocclude/server/SheepController.java:125-151` — runtime advances `axisPos` by commanded velocity × `dt` plus the frozen noise draw.
- `fabric/mineocclude-mod/src/main/java/com/mineocclude/server/MotionSchedule.java:58-99` — the server consumes explicit signed speed segments from a spec-bound schedule.
- A-prime v0.4 locked manifests inspected read-only record `speed_blocks_per_second: 2.0` for every Stage-2 unit.

HISTORICAL EVIDENCE:
A-prime specifies speed 2.0 and `q=0.05` (`preauthority_creation_inputs/final-regime-a-prime-canonical-scientific-reconstruction.md:163-163,617-620,1574-1574`). Experiment II specifies speed 2.0 (`preauthority_creation_inputs/MineOcclude_Experiment_II_Final_Scientific_Consolidation.md:158-162`). The current manuscript reports 2.0 in Methodology (visually inspected page 3, lines 62–65 of extracted text).

IMPLEMENTATION CONSEQUENCE:
Parameterize generation and validation at 2.0; regenerate the fresh cohort; use speed-2.0 A-prime direction-specific FIR calibration; freeze new targets. Reject any spec/path validated under 1.5.

TIME/COST CONSEQUENCE:
No production cost increase. The fresh CPU qualification already required by Q1 absorbs the change.

RISKS:
The checked-out base has assertions/defaults tied to 1.5. Phase 1 must audit every literal and manifest validator. Historical t01–t25 paths cannot be reused as fresh 2.0 identities.

REJECTED ALTERNATIVES:
1.5 was rejected as implementation inertia and weaker manuscript continuity. Multiple speeds were rejected as scope expansion and confounding.

REQUIRED DESIGN-DOCUMENT CHANGES:
Use 2.0 everywhere, remove ambiguous “Regime A speed,” and tie all fresh path/target qualification and timing to it.

REQUIRED PHASE-1 AUTHORITY LANGUAGE:
Bind 2.0 in generator, motion schedule, server receipt, path replay, manifest, validation, pilot, and claims; bind `q=0.05` and `dt=0.05` unchanged.

## Q8 — Redefine partial-visibility semantics

DECISION:
`EXP3_VISIBILITY_SEMANTICS = CONDITION_LABEL + MATERIAL_INDEPENDENT_COUNTERFACTUAL_EXTENT + P0_FROZEN_RVE`, with condition-independent frozen target rows. Geometry, image evidence, and scientific condition are separate fields.

STATUS:
RESOLVED

CONFIDENCE:
HIGH

SCIENTIFIC JUSTIFICATION:
Partial glass is intentionally a state in which the target is behind the original wall footprint while retaining image evidence. The old `OCCLUDED_AGREEMENT` predicate encodes the opposite and would make eligibility condition/outcome-dependent. The correct paired experiment selects rows from a counterfactual opaque-footprint geometry schedule once and applies them to every material.

CODE EVIDENCE:
- `src/mineocclude/regime_a.py:245-254` — `classify_visibility` only recognizes visible+detected and occluded+not-detected agreement.
- `src/mineocclude/regime_a.py:257-300` — `assign_stable_hidden_tau` requires 19 consecutive old agreement rows.
- `scripts/run_regime_a.py:283-409` — post-capture target construction reads center-ray geometry and magenta status and assigns old tau semantics.
- `fabric/mineocclude-mod/src/main/java/com/mineocclude/server/EpisodeManager.java:434-459` — runtime `geometricVisible` is a center-ray/material-presence diagnostic, not rendered-extent truth.
- A-prime `src/mineocclude/prospective/extent_geometry.py:290-324` (commit-qualified remote path) — detector-independent full-visible/partial/full-occluded classification over rendered extent.

HISTORICAL EVIDENCE:
A-prime's final truth explicitly excluded detector output and classified a renderer-derived extent (`preauthority_creation_inputs/final-regime-a-prime-canonical-scientific-reconstruction.md:1570-1572`). It applied the same 19 WALL target frames/labels to NO_WALL (`:1574-1574`), directly supporting material-independent pairing.

IMPLEMENTATION CONSEQUENCE:
Add the explicit schema in the revised design. Eligibility is exact frozen manifest membership, complete alignment/FIR/path, and counterfactual `EXTENT_FULLY_OCCLUDED`; detector and RVE are QA/covariates only. L0 has no physical wall, L1–L3 have one selected stained-glass layer, L4 has stone, and all use the same target rows.

TIME/COST CONSEQUENCE:
Small schema and selector work after the Q9 extent/FIR port; no extra captures or forwards.

RISKS:
Terminology can drift between runtime `Scene.NORMAL`, design condition `L*`, actual wall presence, and counterfactual geometry. Unknown values must fail closed; no string pass-through.

REJECTED ALTERNATIVES:
Per-condition detector eligibility was rejected as outcome-dependent and destructive to pairing. Treating all behind-wall rows as “hidden” was rejected because it erases the manipulation. Using runtime center-ray status as extent truth was rejected by A-prime's failure history.

REQUIRED DESIGN-DOCUMENT CHANGES:
Replace every “19 hidden rows” with “19 counterfactual fully occluded target rows,” except L4-specific complete-occlusion descriptions; add field schema and L0–L4 definitions.

REQUIRED PHASE-1 AUTHORITY LANGUAGE:
Freeze vocabularies and mappings, counterfactual wall geometry, renderer extent, eligibility equation, target indices, condition-invariant labels, and the non-authoritative roles of center ray, magenta detector, and RVE.

## Q9 — Can the original executable base supply the required extent/FIR target semantics directly?

DECISION:
No. Port the **minimal A-prime measurement subset**—renderer-derived extent geometry, canonical causal-FIR label construction, direction-kernel binding, and builder/evaluator agreement tests—without porting the A-prime campaign lifecycle.

STATUS:
RESOLVED

CONFIDENCE:
HIGH

SCIENTIFIC JUSTIFICATION:
The current branch is correctly based on the original executable lineage, but that lineage predates the two most important A-prime measurement repairs. Experiment III cannot safely reinterpret its center-ray/magenta target rows. This is a bounded semantic port, not a lineage change.

CODE EVIDENCE:
- `src/mineocclude/regime_a.py:200-300` — current selector is stable center-ray/detector agreement.
- `src/mineocclude/regime_a.py:29` — current generator also embeds the superseded 1.5 speed.
- Commit-qualified A-prime `src/mineocclude/prospective/extent_geometry.py:56-114` — derives the renderer half-extent `0.8727621336620037` from pinned sheep-fur geometry.
- Same A-prime source `:290-324` — defines extent class independently of detector outcomes.
- Commit-qualified A-prime `src/mineocclude/prospective/development_workflow.py:878-916` — canonical normalized causal FIR sum and complete-history gate.
- Commit-qualified A-prime `scripts/regime_a_prime_qualification_v0_2/build_manifests.py:224-250` — materializes target rows and labels before outcomes.

HISTORICAL EVIDENCE:
A-prime documents that point/silhouette mismatch caused the earlier failure and that synchronized extent semantics fixed it (`preauthority_creation_inputs/final-regime-a-prime-canonical-scientific-reconstruction.md:1197-1228,1630-1630`). Its final half-extent and causal-FIR procedure are reconstructed at `:1570-1574`.

IMPLEMENTATION CONSEQUENCE:
Copy/reconcile only the scientific primitives and tests into Experiment III-native modules, adapting them to fresh identity generation and a five-condition schema. Keep the original branch ancestry. Do not import remote campaign authorities, recovery admissions, S3 lifecycle, or development verdict logic.

TIME/COST CONSEQUENCE:
Approximately 3–6 engineering hours including equivalence tests against static A-prime fixtures. This work is necessary for validity and fits the implementation day.

RISKS:
Partial copying could revive stale v0.2 point semantics or noncanonical floating summation. Phase 1 must bind exact source provenance and fixture outputs.

REJECTED ALTERNATIVES:
Using old tau rows was rejected as invalid for glass. Checking out or rebasing onto A-prime was rejected because it violates the mandated implementation lineage. Porting the full A-prime governance stack was rejected as unnecessary.

REQUIRED DESIGN-DOCUMENT CHANGES:
Make the semantic port an explicit implementation prerequisite and separate it from Experiment II reuse.

REQUIRED PHASE-1 AUTHORITY LANGUAGE:
Name exact A-prime source commit/path provenance, copied formulas/constants, canonical-sum behavior, fixture hashes, and the explicit exclusion of lifecycle/governance code.

## Q10 — Does MineWorld versus raw pixels support an unrestricted “internal support beyond pixels” claim?

DECISION:
No. Retain a **linear current-frame pixel baseline** as a secondary comparator and narrow all claims to that comparator. Do not describe it as all raw-pixel accessibility or a context/capacity-matched test.

STATUS:
RESOLVED

CONFIDENCE:
HIGH

SCIENTIFIC JUSTIFICATION:
MineWorld CURRENT is causally conditioned on up to 16 visual/action pairs, whereas the proposed raw baseline sees one downsampled current image. Differences can reflect context, pretrained nonlinear visual processing, dimensionality, and representation—not an isolated internal-memory advantage. The comparison remains useful as an empirical sensory floor if named precisely.

CODE EVIDENCE:
- `src/mineocclude/models/_mineworld_adapter_wave3.py:637-720` — CURRENT residual is produced in a 16-pair context.
- `src/mineocclude/models/mineworld_adapter.py:663-681` — visual and action pairs are causally ordered.
- `scripts/run_regime_a.py:929-937` — current activation is harvested after the full context call.
- No current production module implements a capacity-matched raw-pixel history baseline; adding one would introduce a new high-dimensional family and tuning burden.

HISTORICAL EVIDENCE:
The manuscript explicitly limits prior work to current-frame linear neural readouts and lists temporal alternatives as untested. Experiment II similarly says temporal representations were authored but not evaluated (`preauthority_creation_inputs/MineOcclude_Experiment_II_Final_Scientific_Consolidation.md:225-225,367-367`).

IMPLEMENTATION CONSEQUENCE:
Implement exactly one frozen 48×28×3 current-RGB ridge baseline with the same outer identities and nested-alpha protocol. Move its contrast out of the primary Holm family. Report MineWorld-minus-pixel behavior with a two-sided identity-bootstrap interval and constrained wording.

TIME/COST CONSEQUENCE:
Low CPU cost; no new capture or model forward. Avoids a large pixel-history design under deadline.

RISKS:
Readers may still overinterpret a positive difference. Figures/tables/captions must carry “linear current-frame” explicitly. The baseline's spatial downsampling can remove fine evidence, so source-frame RVE remains the manipulation coordinate.

REJECTED ALTERNATIVES:
Dropping pixels entirely was rejected because it is a useful floor and proposal gap. Adding pixel histories, CNNs, optical flow, or capacity matching was rejected as a new search family and deadline risk.

REQUIRED DESIGN-DOCUMENT CHANGES:
Rename every “raw-pixel accessibility/internal support beyond pixels” claim, move P4 to secondary, and state the context/capacity limitations.

REQUIRED PHASE-1 AUTHORITY LANGUAGE:
Freeze RGB source, 48×28 resize/interpolation/flattening, scaling, ridge/folds/alpha, contrast sign, secondary role, interval, and prohibited generalizations.

## Cross-document quantitative reconciliation

The controlling quantitative inventory is:

- production identities: 25 fresh;
- production captures: 125;
- production rows and forwards: 2,375 each;
- layers: 3; temporal slices: 2;
- logical production row tensors: 14,250;
- serialized production arrays: 750 of `[19,336,2048]` float16;
- exact production activation bytes: 19,611,744,000 (18.2649 GiB);
- excluded P1 pilot: 10 captures, 190 forwards, 1,140 logical tensors, 60 arrays, 1,568,939,520 bytes;
- combined retained pilot+production: 135 captures, 2,565 forwards, 15,390 logical tensors, 810 arrays, 21,180,683,520 bytes (19.7260 GiB).

## Consistency and equivalence audit

**PASS.** The successor was searched for superseded cohort, speed, RelV, ratio, target, layer, count, byte, and fallback language. All decision-matrix fields parsed successfully, and the capture, forward, tensor, array, temporal-index, feature-dimension, and byte totals recomputed from their primitives without discrepancy. All eight Markdown tables are rectangular. The generated DOCX is a valid, reloadable OOXML package with eight tables, one coherent section, explicit preauthority notices in both body and header, repeatable table headers, and page-number fields.

Normalized source-to-DOCX comparison found exact equivalence across all 407 scientific paragraph and table-cell blocks; the only extra body block is the deliberate preauthority notice. Unicode replacement-character checks were clean in Markdown, JSON, and DOCX XML. The original Fable document was rehashed after output generation and remains exactly `a55a26e15155cce5d98df153b46fdd7059345e335e3a1f599bc2f7eb30dcf33b`.

## Readiness conclusion

`AUTHORITY_CREATION_READY=true`. The design decisions are complete. P0's empirical material result is intentionally not known; the Phase-1 authority can prospectively bind its exact selection and `NO_VALID_LADDER` stop. Phase 1 must treat `MineOcclude_Experiment_III_Phase0_Adjudicated_Design.md` and its materially equivalent DOCX as the controlling design input. `IMPLEMENTATION_AUTHORIZED=false`.
