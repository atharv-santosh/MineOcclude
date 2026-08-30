# Final Regime A′ Experiment — Canonical Scientific Reconstruction

## 1. Audit Identity

```
AUDIT_MODE=READ_ONLY
REPOSITORY_ROOT=/home/sagemaker-user/MineOcclude
CURRENT_BRANCH=exploration/regime-a-prime-qualification-v0-1
HEAD=020dfecea2caad179cf7d07fc13a34d389b82c4a
HEAD_SUBJECT=Regime A' v0.4 Stage-2 final pre-canary repair: extraction-only execution closure
HEAD_AUTHOR_DATE=2026-08-20T01:01:36+00:00
HEAD_COMMITTER_DATE=2026-08-20T01:19:23+00:00
PARENT_SHA=6f41ba467c0667e601076ed8fb2b6432a0edcb3f
HEAD_TREE=02343763b39f31a22dfa75780ca2913055375644
```

The requested branch is the current local branch. Its remote counterpart points to `85d1d043e3d07c39c6fac118dd8d5582233e8e8a`; the checked-out branch is two commits ahead. Its branch point from `exploration/regime-a-postmortem-v0-1` is `9b7d0c7f379956ae1fb52720cc15e10d07adb0e4`, with 33 branch-unique commits.

The terminal evidence is not committed into Git. It is archived at [regime\_a\_prime\_stage2\_v0\_4\_final\_20260820]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820). Thus `020dfec…` is the frozen processing source HEAD, while the actual data completion and adjudication are external, hash-bound experimental events.

## 2. Executive Summary

The final experiment was Regime A′ prospective development qualification v0.4, Stage 2:

```
SCIENTIFIC_RUN_ID=mineocclude-regime-a-prime-development-v0-4-stage2
CLASSIFICATION=DEVELOPMENT_ONLY
OPERATIONAL_STATUS=COMPLETE_VALIDATED_DURABLE
SCIENTIFIC_VERDICT=FAIL
```

It tested whether a prospectively frozen linear/kernel-ridge decoder of MineWorld layer-4 visual-token activations could recover the current, temporally aligned world-x position of a sheep while its complete rendered extent was hidden behind a wall. The control used the same 25 stochastic trajectories without the wall.

The apparatus qualified. Stage 1 passed all nine qualification gates. All 50 Stage-2 captures formed 25 complete WALL/NO\_WALL pairs. Every capture and extraction completed and validated. The cohort physical gate passed all ten required checks. Runtime provenance was ultimately admitted under an audited equivalence rule. The visible NO\_WALL control passed decisively:

- BEST-K NO\_WALL macro \\(R^2=0.9582680589\\)
- 95% whole-trajectory bootstrap interval `[0.9433883673, 0.9695287239]`
- trajectory-aggregated RMSE `0.1053344162` blocks, below the frozen `0.1556047776` ceiling.

The hidden WALL test failed decisively:

- BEST-K WALL macro \\(R^2=-14.7034147101\\)
- 95% interval `[-17.6713609520, -12.1453290303]`
- RMSE `2.1098100620` blocks, about 20 times the NO\_WALL RMSE and far above the frozen ceiling.
- WALL also lost to the only final-stage non-neural comparator, the training-only time baseline with RMSE `0.4135931190`.

FULL, the predeclared secondary non-rescuing readout, produced the same qualitative outcome: NO\_WALL \\(R^2=0.9505320784\\), WALL \\(R^2=-14.6427001722\\).

This is an interpretable scientific failure, not an apparatus failure. The experiment validates the measurement path and visible decodability but does not establish U1 hidden-position decodability for layer 4 under this apparatus. U2, U3, and U4 were not tested. No final-stage permutation null, last-seen baseline, or constant-velocity baseline was run.

## 3. Final Experiment Identity

| FieldCanonical value         |                                                         |
| ---------------------------- | ------------------------------------------------------- |
| Design authority             | `regime-a-prime-prospective-development-authority-v0.4` |
| Stage-2 manifest             | `regime-a-prime-stage2-locked-manifest-v0.4`            |
| Run                          | `mineocclude-regime-a-prime-development-v0-4-stage2`    |
| Branch                       | `exploration/regime-a-prime-qualification-v0-1`         |
| Frozen processing HEAD       | `020dfecea2caad179cf7d07fc13a34d389b82c4a`              |
| Experiment class             | `DEVELOPMENT_ONLY`                                      |
| Confirmatory status          | false; confirmatory reuse forbidden                     |
| Stage-1 result               | PASS                                                    |
| Stage-2 terminal result      | FAIL                                                    |
| Independent identities       | 25                                                      |
| Capture units                | 50                                                      |
| WALL/NO\_WALL pairs          | 25                                                      |
| Layout                       | `layout_01` only                                        |
| Directions                   | 13 LEFT\_TO\_RIGHT, 12 RIGHT\_TO\_LEFT                  |
| Frames per capture           | 180                                                     |
| Stage-2 capture frames       | 9,000                                                   |
| Scored rows                  | 950: 475 WALL and 475 NO\_WALL                          |
| Layer                        | 4 only                                                  |
| Activation shape per capture | `[19,336,2048]`, float16                                |

The frozen authority is [authority\_parameters.json]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/01\_FROZEN\_AUTHORITY/authority\_parameters.json); the terminal adjudication is [stage2\_decision.json]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/04\_SCIENTIFIC\_RESULTS/stage2\_decision.json).

## 4. Scientific Lineage

The lineage began with a failed original Regime A hidden-position experiment and proceeded through matched-control, timing, rendered-extent, builder/evaluator, provenance, and execution qualifications.

| Time UTCCommitPhaseScientific meaning |           |                                   |                                                                |
| ------------------------------------- | --------- | --------------------------------- | -------------------------------------------------------------- |
| Aug 15 06:55                          | `da2dd7c` | DESIGN                            | Bound initial Regime A′ P0 authority                           |
| 07:25                                 | `4ba4794` | FORENSIC/QUALIFICATION            | Existing-data P1 qualification                                 |
| 07:44                                 | `6943e04` | DESIGN                            | Froze P2 matched NO\_WALL diagnostic                           |
| 08:21                                 | `af8ab21` | FORENSIC                          | Recorded renderer-equivalence blocker                          |
| 08:22                                 | `76a2e7f` | DESIGN REPAIR                     | Amended P2 current-apparatus qualification                     |
| 08:51                                 | `76fdcf2` | APPARATUS REPAIR                  | Superseded inappropriate pixel gate                            |
| 08:56                                 | `9271b4a` | SOFTWARE REPAIR                   | Fixed Xvfb provenance preflight                                |
| 11:17                                 | `c2ca247` | QUALIFICATION                     | Closed P2 visible qualification                                |
| 11:32                                 | `e56d90b` | DESIGN                            | Froze P3 development authority                                 |
| Aug 16 02:04                          | `351da85` | FORENSIC                          | Froze terminal P3 forensic evidence                            |
| 05:13                                 | `db2e110` | APPARATUS REPAIR                  | Froze corrected temporal-alignment infrastructure              |
| 13:41                                 | `95d6fe9` | DESIGN                            | Stage-1 prospective authority v0.2                             |
| Aug 17 04:42                          | `237654b` | SOFTWARE REPAIR                   | Qualification-repair successor source                          |
| 06:34                                 | `1234d31` | SOFTWARE REPAIR                   | Seed-contract successor                                        |
| 08:30                                 | `560bc01` | APPARATUS REPAIR                  | Camera-apparatus verifier successor                            |
| 17:49                                 | `a5d763a` | DESIGN                            | v0.3 extent-visibility successor                               |
| 18:38                                 | `fa9d134` | VALIDATION                        | v0.3 execution closure                                         |
| 19:03                                 | `3977836` | VALIDATION                        | v0.3 probe authority                                           |
| 19:42                                 | `134a242` | STAGE-1                           | v0.3 provenance-bound qualification; terminal FAIL             |
| 22:47                                 | `046b34a` | SOFTWARE REPAIR/STAGE-1           | Builder/evaluator synchronization; v0.4 Stage-1 source         |
| Aug 18 03:49                          | `fd0891a` | DESIGN                            | v0.4 Stage-2 preparation                                       |
| 06:08                                 | `c9aad3e` | SOFTWARE REPAIR                   | Stage-2 execution-path qualification                           |
| 07:35                                 | `f2bc2c8` | DESIGN/ADJUDICATION               | Terminal authority and binding closure                         |
| 10:17                                 | `9448657` | VALIDATION                        | Operational and terminal verification closure                  |
| 14:56                                 | `49f0cca` | CAPTURE                           | Canonical trajectory arithmetic; one capture                   |
| 18:37                                 | `cb16335` | CAPTURE/PROVENANCE                | Split capture and processing provenance; remaining 49 captures |
| Aug 19 05:15                          | `d635318` | APPARATUS REPAIR                  | Physical-gate capture admission                                |
| 08:24                                 | `76098ae` | QUALIFICATION                     | Cohort runtime-provenance repair; physical gate PASS           |
| 11:44                                 | `1abb837` | SOFTWARE REPAIR                   | Extractor initialization and durable-gate admission            |
| 13:16                                 | `93a7cc4` | SOFTWARE REPAIR                   | Capture/model identity-namespace collision repair              |
| 15:42                                 | `85d1d04` | OPERATIONAL RECOVERY              | Mixed-freeze restore and historical gate-payload admission     |
| 19:03                                 | `6f41ba4` | VALIDATION                        | Canonical physical-gate admission for every consumer           |
| Aug 20 01:01/01:19                    | `020dfec` | SOFTWARE REPAIR/EXECUTION CLOSURE | Extraction-only final processing freeze                        |

There is no “scientific result commit.” The actual extraction completed at `2026-08-20T10:26:04Z`; BEST-K, FULL, and terminal adjudication ran at 11:42–11:54 under `020dfec…`. No later archive-only Git commit exists.

The original Regime A had already shown why the stricter reconstruction was needed: its layer-4 FULL trajectory-equal \\(R^2\\) was approximately `-1.2289`, and its grouped trajectory null gave empirical `p=0.90`. A very high pooled-row \\(R^2\\) coexisted with poor within-trajectory prediction, showing that pooled global structure was insufficient evidence of hidden state.

## 5. Scientific Question

The final question was:

> Under one fixed, qualified Minecraft/MineWorld apparatus, can a prospectively specified linear kernel-ridge readout of layer-4 activations decode the sheep’s temporally aligned world-x position while its full rendered extent is geometrically occluded, at no worse than twice the corrected accuracy of a matched visible reference?

This was narrower than “does MineWorld have object permanence?” It was a specific decoding qualification involving one checkpoint, one layer, one layout, one motion regime, one target variable, and two frozen readouts.

## 6. Claim Ladder

| RungMeaningFinal status                         |                                                               |                                    |
| ----------------------------------------------- | ------------------------------------------------------------- | ---------------------------------- |
| Apparatus                                       | Frames, state, geometry, timing, visibility, durability valid | ESTABLISHED                        |
| Visible measurement                             | Layer-4 readout decodes matched NO\_WALL trajectories         | ESTABLISHED                        |
| U1 hidden-position decoding                     | WALL decoder satisfies frozen criteria                        | NOT ESTABLISHED                    |
| Target-specific advantage over permutation null | Neural mapping exceeds structured null                        | NOT TESTED in final Stage 2        |
| Motion-alternative exclusion                    | Beats last-seen/constant velocity                             | NOT TESTED                         |
| U2 uncertainty representation/calibration       | Uncertainty encoded and calibrated                            | NOT TESTED                         |
| U3 uncertainty dynamics                         | Uncertainty changes appropriately over occlusion age          | NOT TESTED                         |
| U4 causal use/reappearance                      | Representation causally controls prediction/behavior          | NOT TESTED                         |
| Object permanence/belief                        | Cognitive or behavioral construct                             | NOT ESTABLISHED; outside authority |
| Generalization                                  | New layouts/speeds/noises/checkpoints                         | NOT ESTABLISHED                    |

## 7. Design Authority

The scientific authority SHA-256 is:

```
52b9590bc1695658b30304b557a4df65d38928ab15281ffd9800e014e839e728
```

The separately frozen Stage-2 decision authority SHA-256 is:

```
c2187e66773cbf80171390a44b65e18a88cd8eceac02bc396e882ae329cb0ca7
```

The authority fixed before outcome exposure:

- DEVELOPMENT\_ONLY classification.
- 25 paired identities and 50 captures.
- 13/12 directional balance.
- One layout, speed `2.0`, noise `q=0.05`, 180 frames.
- 19 rows per scene and identity.
- Extent-based physical truth and FIRST\_N selection.
- Direction-specific causal-FIR labels.
- Layer 4 only; all-layer extraction forbidden.
- BEST-K leading and FULL secondary/non-rescuing.
- K grid `[1,4,8,16,32,64,128]`.
- Alpha grid `[0.1,1,10,100]`.
- Five outer and five inner trajectory-grouped folds.
- Training and selection limited to \\(\tau\le15\\); evaluation on \\(\tau=1…19\\).
- Whole-trajectory bootstrap, 10,000 replicates, seed `2026081503`.
- RMSE ceiling `0.15560477763641264`.
- Six all-must-pass BEST-K gates.
- No authorization for confirmation, intervention, or a next rung.

The decision authority initially carries template status `DRAFT_PROSPECTIVE_UNFROZEN_NOT_AUTHORIZED`; it became operative through the locked manifest and the separate post-Stage-1 authorization receipt. That is a staged governance state, not a scientific discrepancy.

## 8. Authority / Supersession History

The central supersession sequence was:

```
Regime A
  ↓ negative primary result; pooled/trajectory discrepancy
P1 historical-baseline diagnosis
  ↓ stale and time/motion shortcuts not ruled out
P2 matched NO_WALL qualification
  ↓ visible readout works, but temporal labels need repair
P3 v0.1 point-versus-silhouette qualification
  ↓ physical truth predicate structurally mismatched to detector
v0.2 point/band qualification
  ↓ boundary false positive at 0.006282776508991 blocks
v0.3 renderer-derived extent qualification
  ↓ extent semantics correct, but stale builder + one true RTL timing failure
v0.4 synchronized Stage 1
  ↓ all apparatus gates PASS
v0.4 Stage 2
  ↓ visible control PASS; hidden decoder FAIL
```

v0.4’s scientific delta from v0.3 was explicitly `EMPTY`. It used a new inventory because the failed v0.3 units were immutable and forbidden from reuse. It did not change speed, extent, FIRST\_N, sample floor, temporal rule, or acceptance threshold.

## 9. Final Cohort

The inferential unit was a complete trajectory identity, not a frame. There were 25 independent stochastic identities, each appearing in two paired scenes. Therefore:

- Inferential/bootstrapping units: 25.
- Capture units: 50.
- Activation arrays: 50.
- Repeated target observations: 19 per capture.
- Target rows: 475 per scene, 950 total.
- Frames: 180 per capture, 9,000 total.

Rows within a trajectory were not treated as independent. Each outer fold held out five entire identities, with both scene-specific analyses using the same identity partition.

## 10. Wall / No-Wall Pairing

For each identity, the pair shared:

- trajectory and noise seed;
- exact motion schedule;
- speed and phase offset;
- direction;
- start position;
- expected path and labels;
- capture cadence;
- target window;
- fold membership.

The intended scene difference was wall presence:

- `WALL`: the target rows had to be fully occluded over the declared renderer-derived extent.
- `NO_WALL`: the matched target rows had to be stably visible.

Pair target labels were bitwise/equality-checked and totaled 950. Pair coverage passed for all 25 identities. No formal paired-difference estimator or CI was archived, however; scenes were evaluated separately against their gates.

## 11. Directions

There were 13 LEFT\_TO\_RIGHT and 12 RIGHT\_TO\_LEFT identities. Starts were:

```
LEFT_TO_RIGHT  x=-7.8
RIGHT_TO_LEFT  x=+7.8
```

The balance was intentional: one-direction-only designs make elapsed time and position nearly deterministic. Direction entered the time-baseline design matrix as `+1/-1`, with an interaction with \\(\tau\\).

Final per-direction decoder metrics were not preserved in the terminal artifacts. Consequently, whether both directions separately showed the same hidden failure is `UNKNOWN — INSUFFICIENT REPOSITORY EVIDENCE`, even though the combined bidirectional WALL result failed overwhelmingly.

## 12. Layouts

All captures used `layout_01`. This makes layout a fixed apparatus factor rather than a replicated experimental factor. There is:

- no fresh-layout test;
- no between-layout variance estimate;
- no evidence that performance generalizes to another camera/wall geometry.

The only tested layout failed the hidden decoding criteria while passing its visible control.

## 13. Environment Authority

Capture apparatus:

| ComponentFrozen identity |                             |
| ------------------------ | --------------------------- |
| Minecraft                | 1.16.5                      |
| Fabric Loader            | 0.15.11                     |
| Fabric API               | 0.42.0+1.16                 |
| Yarn mappings            | 1.16.5+build.10             |
| Fabric Loom              | 1.4.6                       |
| Mod version              | 0.1.1                       |
| Java                     | Corretto 17.0.20.8.1        |
| Mesa                     | 25.2.8                      |
| Renderer                 | llvmpipe LLVM 20.1.2        |
| Xvfb                     | 21.1.12                     |
| Display                  | `:99`, screen `1280x720x24` |
| Canonical capture        | 640×360, 20 Hz              |
| Model input              | 384×224                     |

The inference environment report records:

```
platform=Linux-6.12.95-124.187.amzn2023.x86_64-x86_64-with-glibc2.39
python=3.10.20, conda-forge, GCC 14.3.0
torch=2.6.0+cu126
torch_cuda=12.6
GPU=NVIDIA L4
GPU_MEMORY=23661248512 bytes
```

Critical artifact hashes included:

- installed mod: `febf31cad7c6de003a6d2d87ed9183c6a6739e086e293b30e92999520e3bfaba`
- mod source: `3c37227654415956ab34a0c3245fe25697ed8c2b8d18dcbca7373a21f5c32de0`
- detector: `99acc45e0a49b8526eca2ab777e21c07f88934d744bc5679e63ab8a00b181b8d`
- Minecraft server jar: `58f329c7d2696526f948470aa6fd0b45545039b64cb75015e64c12194b373da6`
- Fabric launcher: `1caefab680c8832254dd8644c6df536c169315188e715191c9b52ed69adee66e`

## 14. MineWorld Authority

| FieldExact value          |                                                                    |
| ------------------------- | ------------------------------------------------------------------ |
| Model class               | `LlamaLVM`                                                         |
| Transformer               | `LlamaForCausalLM`                                                 |
| Decoder path              | `transformer.model.layers`                                         |
| Layer count               | 20                                                                 |
| Hidden size               | 2048                                                               |
| Visual tokens/frame       | 336, grid 14×24                                                    |
| Action tokens/frame       | 11                                                                 |
| Tokens/pair               | 347                                                                |
| Maximum context pairs     | 16                                                                 |
| Precision                 | float16                                                            |
| Main checkpoint SHA       | `a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5` |
| Model config SHA          | `e13b3a80fb370547a05852809c2c8f02d05ebe2fce3b3bb2fd1ee54eee78c018` |
| VAE checkpoint SHA        | `370d06be427e034476b6b95ba0080a4b48266e876c4776a757b944b87b87d9ab` |
| VAE config SHA            | `32ca759d5b90f0c5aa5df0e312a81e03dd4d3af68896863c88f910d19f2526cb` |
| MineWorld source          | `9f49efbcc68a5f0cf60e78f0abc566eac409282f`                         |
| ModelScope asset revision | `0dd5561ab317115831badc50e09a6ebe98693d0e`                         |
| Adapter                   | `person-a-mineworld-adapter-v1.0`                                  |
| Preprocessing             | `person-a-bgr2rgb-inter-linear-224x384-v1.0`                       |
| Action conversion         | `mineworld_mcdataset_json_action_to_env_action@1.0:7e8d16db…`      |

A known frozen preprocessing defect feeds BGR ordering where the model path nominally expects RGB. It was known and retained rather than repaired after the apparatus was frozen. It applies to both scenes, so it does not invalidate the within-apparatus WALL/NO\_WALL comparison, but it limits inference to this exact preprocessing path.

## 15. Camera / Scene Geometry

```
camera feet = (0.5, 4.0, -5.5)
camera eye  = (0.5, 5.6200000048, -5.5)
yaw/pitch/roll = (0°,0°,0°)
FOV = 70°
lane = x∈[-8,8], y=4, z=6
target centre y = 4.5
wall-relative x origin = 0.5
```

The raw wall specification used segment bounds `[-2.5,2.5]` and orthogonal location `6-4=2`. Whole-block construction yielded the as-built occluder:

```
x ∈ [-3,4]
z ∈ [2,3]
y ∈ [4,7]
height = 3 blocks
```

The reference visibility primitive was `GeometryUtil.segmentHitsWall`, reproduced as the same discrete march with inclusive face tests, rather than replaced by an analytic line/slab intersection.

## 16. Sheep Physical Geometry

The occlusion truth used the rendered wool model, `SheepFurModel`, not the collision box and not the centre point alone. Its geometry was decompiled from the exact Minecraft 1.16.5 client jar, SHA-1:

```
37fd3c903861eeff3bc24b71eed48f828b5269c8
```

The body, head, and legs were bounded over all reachable animation states. The decisive longitudinal bound came from a rear leg:

\\[ \max |z'| = 7+\sqrt{6.5^2+2.5^2}=7+\sqrt{48.5}. \\]

Applying the Minecraft model scale of \\(1/16\\) block produced the horizontal half-extent.

## 17. Renderer-Derived Extent

\\[ w=\frac{7+\sqrt{48.5}}{16}=0.8727621336620037\ \text{blocks}. \\]

This was:

- renderer-derived;
- independent of the scored magenta detector;
- not fitted to outcomes;
- not fitted to transition locations;
- a yaw-independent upper bound;
- applied to world x and z.

The earlier draft value `0.8727621026470629` was corrected before outcome because it lay approximately `3.10×10^-8` blocks below the analytic supremum. The change widened the conservative partial region and did not change any frozen-schedule classification or sample count.

## 18. Visibility Semantics

Each target extent was classified into:

- `EXTENT_FULLY_VISIBLE`: none of the sampled extent points is occluded.
- `EXTENT_PARTIAL`: a mixture of visible and occluded points.
- `EXTENT_FULLY_OCCLUDED`: every extent corner/point is occluded.

The lattice used five samples per axis. Corners are exact for full occlusion because the occluded cone is convex; interior samples make the fully-visible rule conservative. Classifications were invariant at 3, 5, 9, and 17 samples per axis on the frozen schedule.

Mappings:

```
EXTENT_FULLY_VISIBLE  → stable_visible
EXTENT_PARTIAL        → partial_transition, unscored
EXTENT_FULLY_OCCLUDED → stable_occluded
```

The magenta detector could be scored against this truth but could not define it. Legacy `point_visible` remained diagnostic only.

## 19. Transition Semantics

A normal crossing progresses:

```
stable visible → partial transition → stable occluded
→ partial transition → stable visible
```

Direction changes spatial ordering, not the temporal sequence. Transition-measurement replicates reported geometric and rendered-detector intervals, but held-out truth was classified directly from each row’s own geometry. No detector-derived band was transferred to held-out rows in the final method.

## 20. Builder / Evaluator Synchronization

The v0.3 evidence builder still implemented v0.2 point/band semantics while the authority and evaluator implemented extent semantics. This produced:

- 166 builder/evaluator regime mismatches;
- all in the direction “builder stable, evaluator partial”;
- an obsolete transition schema;
- FIRST\_N selection over the wrong pool;
- four consequent failed gates.

The synchronized v0.4 builder and evaluator read the same aligned coordinate, geometry, extent, and admissibility filter. Every final Stage-1 unit had zero regime mismatches, zero wall-relative arithmetic violations, and zero support violations.

## 21. Temporal Alignment — Historical Problem

Raw server tick \\(N\\), client-rendered image \\(N\\), and a target labeled with raw state \\(N\\) were not interchangeable. Historical evidence showed rendered entity state behaved like a causal, smoothed, delayed response of server state. Using raw same-tick state materially degraded the visible decoder and could misclassify transition rows.

The corrected P2 visible BEST-K reference improved from RMSE `0.1660274234` to `0.0778023888`, with macro \\(R^2\\) rising from about `0.7906954` to `0.9555412`, after physically derived alignment while leaving the readout procedure unchanged.

## 22. Temporal Alignment — Final Method

For each direction, Stage 1 estimated a nonnegative causal FIR over lags 0–8. The label for model frame \\(t\\) was the FIR convolution of server-state positions at or before \\(t\\). Raw same-tick state was forbidden.

Two estimands were required:

1. FIR group delay: the kernel’s first moment \\(\sum\_k k h\_k\\).
2. Derivative cross-correlation lag: the modal lag with sub-tick parabolic refinement.

These quantities were not required to equal one another. Qualification required:

- all estimates and intervals within `[0,8]`;
- each estimate inside its own interval;
- each trajectory’s cross-correlation lag within one tick of its own FIR mode;
- the aggregate cross-correlation lag within one tick of aggregate mode;
- estimates within positive-mass support;
- every trajectory’s causal FIR to beat its own best pure delay.

The one-tick threshold was the estimator’s structural refinement clamp, not an outcome-fitted tolerance.

## 23. Temporal Alignment Results

All eight final Stage-1 units passed:

\| Unit | FIR group delay | FIR mode | X-corr lag | \\(|lag-mode|\\) |
\|---|---:|---:|---:|---:|
\| LTR WALL r01 | 3.127646 | 3 | 3.080344 | 0.080344 |
\| LTR WALL r02 | 3.755045 | 5 | 4.700150 | 0.299850 |
\| LTR NO\_WALL r01 | 2.910595 | 3 | 2.833099 | 0.166901 |
\| LTR NO\_WALL r02 | 3.566516 | 2 | 2.310687 | 0.310687 |
\| RTL WALL r01 | 2.023165 | 2 | 2.252131 | 0.252131 |
\| RTL WALL r02 | 2.627384 | 2 | 2.286905 | 0.286905 |
\| RTL NO\_WALL r01 | 2.954185 | 3 | 2.569729 | 0.430271 |
\| RTL NO\_WALL r02 | 3.077252 | 2 | 2.415752 | 0.415752 |

Aggregate LTR group delay was `3.3399504183`, x-correlation lag `3.2310698111`, mode 3. Aggregate RTL values were `2.6704961914`, `2.3811292984`, and mode 2. All deviations were below one tick, and every FIR beat its corresponding pure-delay fit.

## 24. Physical Evidence

Each capture preserved hashes for:

- 180 PNG frames;
- server state;
- client tick log;
- frame map;
- raw and normalized actions;
- motion/noise schedules;
- visibility classifications;
- capture package;
- QA artifacts;
- validation video;
- checksum manifests and receipts.

Typical capture receipts declared 204 durable objects. The final physical gate consumed 50 captures, checked all 25 pairs, and passed. The capture-critical closure contained 406 components and had digest:

```
b64bc70071d2efbbd90e04ca31f4fdaf508498eb51e36c69b584c3602284fa68
```

## 25. Runtime Provenance

Runtime provenance bound branch, commit, Java executable bytes, probe source, renderer, Xvfb, mod, server jars, camera, wall, detector, source closures, and durable manifests.

Capture provenance was deliberately split from processing provenance:

- one capture, `a2y_t01_wall`, was made under `49f0cca…`;
- the other 49 were made under `cb16335…`;
- all 50 had the identical capture-critical closure;
- extraction and readout ran under `020dfec…`.

This avoids the invalid proxy “same commit means same apparatus.” The stronger criterion was exact equality of every capture-critical component.

## 26. Runtime Equivalence

Every extraction subprocess generated an environment report containing a fresh `generated_at` timestamp. Consequently, 50 otherwise identical runtimes produced 50 different report digests, and the frozen verifier initially rejected them.

An external `sitecustomize.py` shim patched only the equality verifier. It:

1. authenticated both reports against their claimed SHA-256;
2. required all identity fields except `environment_report_sha256` to match;
3. compared the report content after removing only `generated_at`;
4. required the reduced digest to equal the pinned cohort digest beginning `4c965196…`;
5. delegated any other difference back to the original fail-closed verifier.

The audit log contained 341 records, 50 distinct original digests, one reduced digest, and only `generated_at` differing. A pre-freeze report with a different MineOcclude revision remained rejected.

This was an operational provenance-equivalence repair. It changed no activations, features, labels, folds, thresholds, seeds, or result.

## 27. Scientific Preflight

Preflight established:

- correct branch and HEAD;
- clean worktree;
- 50 valid captures and 25 complete pairs;
- 950 labels with pair equality;
- 17 distinct target windows spanning frames 36–80;
- no global 48–66 hardcode;
- Stage-1 PASS and bound hashes;
- Stage-2 authorization;
- capture/gate closure consistency;
- durable-prefix health;
- 50 completed extraction units;
- no scientific result yet exposed before the firewall crossing.

## 28. Stage 1

Stage 1 was an eight-run apparatus qualification:

| UnitEpisodeRoleVisiblePartialHiddenUnresolvedFIRST\_N |       |                        |     |    |    |   |                  |
| ----------------------------------------------------- | ----- | ---------------------- | --- | -- | -- | - | ---------------- |
| `a1y_ltr_wall_r01`                                    | 85001 | transition measurement | 39  | 54 | 79 | 8 | 0                |
| `a1y_ltr_wall_r02`                                    | 85002 | held-out validation    | 41  | 51 | 80 | 8 | 19, frames 44–62 |
| `a1y_ltr_nowall_r01`                                  | 85003 | calibration            | 172 | 0  | 0  | 8 | 0                |
| `a1y_ltr_nowall_r02`                                  | 85004 | held-out validation    | 172 | 0  | 0  | 8 | 0                |
| `a1y_rtl_wall_r01`                                    | 85005 | transition measurement | 36  | 50 | 86 | 8 | 0                |
| `a1y_rtl_wall_r02`                                    | 85006 | held-out validation    | 42  | 49 | 81 | 8 | 19, frames 33–51 |
| `a1y_rtl_nowall_r01`                                  | 85007 | calibration            | 172 | 0  | 0  | 8 | 0                |
| `a1y_rtl_nowall_r02`                                  | 85008 | held-out validation    | 172 | 0  | 0  | 8 | 0                |

The first eight rows of every unit were unresolved exactly because a nine-tap causal FIR requires history through lag 8. There were no unexcused unresolved rows.

All nine gates passed:

- calibration detector response;
- calibration support;
- hidden-row contamination;
- prospective transition measurement;
- temporal alignment;
- required evidence completeness;
- stable-visibility robustness;
- unit completeness;
- identity/runtime/path/durability.

Stage-1 status was PASS. Its decision still set `stage2_collection_authorized=false` because Stage 2 required a distinct post-Stage-1 authorization.

## 29. Stage 2

Stage 2 consisted of four controlled phases:

1. consume 50 already-authorized, durable captures;
2. require the cohort physical-gate PASS;
3. extract layer-4 activation tensors without executing readout;
4. after separate operator authorization, run BEST-K, FULL, and terminal adjudication.

The extraction-only entry point structurally scheduled zero capture, gate, or readout units. This maintained an outcome firewall between expensive activation production and scientific outcome computation.

## 30. Stage-2 Authorization

The final successor authorization was generated at `2026-08-20T01:21:07Z`:

```
artifact_id=regime-a-prime-stage2-post-stage1-authorization-v0.4
status=FROZEN_AUTHORIZED
STAGE_2_COLLECTION_AUTHORIZED=true
classification=DEVELOPMENT_ONLY
source_commit=020dfecea2caad179cf7d07fc13a34d389b82c4a
authorization_sha256=f0bb9cad78d8785e8a90b614d0dbbc20ae92bea751594d16eb75531544945d23
preoutcome_provenance_sha256=5305e7e4ee5d8506b59f41527ae1e69e2489e444da359dbfbb224506c2c737bd
```

It bound the passed Stage-1 decision/evidence, locked Stage-2 manifest, complete 50-unit roster, layer restriction, target rows, folds, temporal label source, durable prefix, and final source closure.

The final receipt postdates initial capture because it is a successor authorization/admission under `020dfec…`; the captures themselves were made under earlier authorized freezes and admitted by exact capture-closure equality. It was still pre-outcome: `scientific_outcomes_observed=false`.

## 31. Stage-2 Recovery History

The campaign experienced substantial operational recovery:

- an NVMe wipe removed the physical-gate wrapper receipt;
- the durable gate payload survived;
- the wrapper was neither regenerated nor replayed;
- a named historical durable-payload admission authority recorded the loss;
- capture and processing commit domains were separated;
- extractor initialization was made explicit;
- capture identity and model-runtime identity namespaces were separated;
- partial `.npy` writes were made atomic;
- a minimum-memory launch gate avoided OOM during model load;
- a false-negative T1 validator was corrected externally;
- an authorization artifact-ID mismatch was corrected in the launcher;
- the environment-report timestamp equivalence issue was handled by the audited shim.

None of these changes recaptured a scientific unit, re-extracted an admitted unit, reran a gate, changed a scientific method, or repeated a completed scientific readout.

## 32. Trajectory Generation

Every identity used:

```
speed = 2.0 blocks/second
noise q = 0.05
capture = 20 Hz
server tick = 0.05 seconds
frames = 180
phase ∈ {0,3,6,9,12}
```

Seeds were prospectively frozen. The motion schedule was stochastic but pair-matched. Fold membership was fixed in consecutive identity blocks: t01–t05 fold 0, t06–t10 fold 1, and so on.

## 33. Target Headroom

Every trajectory had to satisfy:

```
target SD ≥ 0.15560477763641264 blocks
candidate median target SD ≥ 0.23340716645461895 blocks
```

Observed frozen expected SDs ranged from `0.4365644873` to `0.6966072860`, with median `0.5509112238`. Thus all trajectories had large target variance relative to the floor. Failure cannot be attributed to nearly constant targets or undefined trajectory \\(R^2\\).

## 34. FIRST\_N

`FIRST_N=19`.

For each WALL trajectory, the target window was the first 19 qualified `stable_occluded` rows in ascending model-frame order. This deliberately selected rows nearest the occlusion boundary, the hardest qualified rows, rather than moving deeper behind the wall after a historical boundary failure.

The same model-frame indices and FIR target labels were used for the NO\_WALL mate. FIRST\_N was materialized after Stage-1 qualification but before Stage-2 manifest freeze.

## 35. Sample Floors

Prospective Stage-1 floor: at least 60 stable rows per direction and class.

The prospective extent calculation predicted:

- LTR stable visible 212, stable occluded 77;
- RTL stable visible 202, stable occluded 86.

The final held-out gate observed:

- LTR visible 213, hidden 80, partial 51, false positives 0, false negatives 0;
- RTL visible 214, hidden 81, partial 49, false positives 0, false negatives 0.

The declared extent could have increased to approximately `1.5028` blocks before any direction/class dropped below the floor, giving substantial conservatism margin.

## 36. Final Dataset Ledger

| Dataset componentUnitsFrames/rowsFinal disposition |    |                               |                                       |
| -------------------------------------------------- | -- | ----------------------------- | ------------------------------------- |
| Stage-1 capture                                    | 8  | 1,440 frames                  | apparatus qualification               |
| Stage-2 WALL capture                               | 25 | 4,500 frames                  | 475 scored stable-hidden target rows  |
| Stage-2 NO\_WALL capture                           | 25 | 4,500 frames                  | 475 scored stable-visible target rows |
| Stage-2 total                                      | 50 | 9,000 frames; 950 target rows | complete                              |
| Stage-1 + Stage-2 physical capture                 | 58 | 10,440 frames                 | supporting lineage total              |
| Partial Stage-2 target rows                        | —  | 0                             | never admitted                        |
| Missing target rows                                | —  | 0                             | none                                  |
| Excluded identities                                | —  | 0                             | none                                  |
| Replacement trajectories                           | —  | 0                             | none                                  |

Complete full-frame stable/partial/hidden counts for all Stage-2 captures are not carried in the archive’s terminal cohort summary. Only the 950 authoritative target-row classes should be quoted. Legacy QA `visible/hidden` fields must not be substituted for extent truth.

## 37. Model Input Construction

For each target model frame \\(t\\):

- frames \\(t-15,\ldots,t\\) and their corresponding actions formed 16 complete pairs;
- each pair contained 336 VAE visual tokens followed by 11 action tokens;
- total sequence length was \\(16\times347=5,552\\) tokens;
- attention mask was all ones;
- position IDs were context-relative `0…5551`;
- batch size was one;
- execution used inference/no-gradient mode;
- the layer-4 tensor for the final pair’s 336 visual positions was retained.

Every target row was a separate teacher-forced forward pass over its own 16-pair window. No cross-target persistent KV state is represented in the extractor implementation.

## 38. Activation Extraction

Each capture produced:

```
shape=[19,336,2048]
dtype=float16
layer=4
```

Each `.npy` was `26,148,992` bytes including its header. Fifty tensors totaled `1,307,449,600` bytes. Raw tensors were kept as durable S3 references rather than copied into the compact final archive.

Extraction ran from approximately 02:30 to `10:26:04Z`, elapsed `28,551.8 s`. One canary tensor, `a2y_t01_wall`, was adopted/reused; 49 units ran once each. Final extraction counts were:

```
expected=50
completed_valid=50
failed=0
blocked=0
invalid=[]
remaining=0
```

## 39. Primary Representation

The leading representation was `BEST_K` over layer-4 visual-token activations. Selected token vectors were summed, yielding the hidden-width feature representation used by standardized kernel ridge. Token ranking was spatially selective; hidden dimensions contributed through the summed 2048-dimensional vector.

`FULL` summed all 336 visual-token vectors and used the same ridge family. It was secondary and could not rescue BEST-K.

## 40. Representation Selection

BEST-K ranked tokens by the absolute maximum training correlation across hidden dimensions. Candidate K and alpha values were evaluated only inside the outer-training data.

Selected values:

| SceneFold 0Fold 1Fold 2Fold 3Fold 4 |         |         |         |         |        |
| ----------------------------------- | ------- | ------- | ------- | ------- | ------ |
| NO\_WALL K/α                        | 32/0.1  | 4/0.1   | 32/0.1  | 8/0.1   | 64/0.1 |
| WALL K/α                            | 128/100 | 128/100 | 128/100 | 128/100 | 64/100 |
| FULL α, NO\_WALL                    | 0.1     | 0.1     | 0.1     | 0.1     | 0.1    |
| FULL α, WALL                        | 100     | 100     | 100     | 100     | 100    |

The WALL selections’ consistently maximal regularization and mostly maximal K were frozen outputs of inner selection, not manually chosen repairs.

## 41. Leakage Controls

Leakage prevention included:

- outer folds grouped by trajectory identity;
- both scenes shared identity/fold structure;
- training and test identities disjoint;
- token ranking inside each training split;
- feature standardization fit on training rows only;
- target centering fit on training targets only;
- K and alpha chosen without outer-test rows;
- inner fold ordering derived by outcome-independent SHA-256 rules;
- selection/final fitting limited to training \\(\tau\le15\\);
- every held-out row predicted exactly once;
- no row-pooled estimator controlled the verdict;
- fold discipline independently rederived rather than trusting self-reported booleans.

## 42. Positive-Control Design

The positive control was not a separate convenience dataset. It was the matched NO\_WALL member of every trajectory pair:

- same stochastic path;
- same direction, speed, phase, and labels;
- same target times;
- same checkpoint, layer, preprocessing, and readout;
- sheep stably visible because the wall was absent.

This tests whether the frozen measurement and decoding path can recover position when current visual evidence exists.

## 43. Positive-Control Results

| ReadoutMacro \\(R^2\\)95% bootstrap CIRMSEMAE |              |                              |              |              |
| --------------------------------------------- | ------------ | ---------------------------- | ------------ | ------------ |
| BEST-K NO\_WALL                               | 0.9582680589 | [0.9433883673, 0.9695287239] | 0.1053344162 | 0.0821633884 |
| FULL NO\_WALL                                 | 0.9505320784 | [0.9321597792, 0.9661492035] | 0.1118387659 | 0.0872558887 |

BEST-K passed both controlling positive-control gates: strictly positive \\(R^2\\) with lower confidence bound above zero, and RMSE below `0.1556047776`.

Therefore: `POSITIVE CONTROL PASS`.

## 44. Hidden-State Target

The hidden target was the current direction-specific causal-FIR-aligned sheep world-x coordinate, in blocks, at each of the first 19 fully occluded target rows. It was not:

- raw same-tick server x;
- time since capture start;
- screen/token coordinate;
- last-seen location;
- an uncertainty parameter;
- a behavioral output.

The target values were exactly pair-matched between WALL and NO\_WALL.

## 45. Non-Neural Baselines

The final Stage 2 implemented only one non-neural family: the outer-training time baseline,

\\[ [1,\ direction,\ \tau,\ \tau\times direction], \\]

fit with `numpy.linalg.lstsq` on training identities and \\(\tau\le15\\).

| ScopeMacro \\(R^2\\)95% CIRMSEMAE |               |                               |              |              |
| --------------------------------- | ------------- | ----------------------------- | ------------ | ------------ |
| All \\(\tau=1…19\\)               | 0.2532082408  | [-0.0209612275, 0.5044127171] | 0.4135931190 | 0.4052244488 |
| Restricted \\(\tau=1…15\\)        | -0.1819203399 | [-0.6148201143, 0.2108101390] | 0.4120172224 | 0.4052342058 |

The WALL neural decoder did not beat this baseline. The NO\_WALL decoder did, descriptively. The authority warns that its two time gates were not independently binding relative to the much stricter RMSE ceiling, so a hypothetical overall PASS would still not have ruled out motion explanations.

Last-seen and constant-velocity baselines: `NOT TESTED` in the final experiment.

## 46. Null Model

No grouped permutation, trajectory-donor, label-shuffle, or other empirical null was run in final v0.4 Stage 2.

```
FINAL_NULL=NOT TESTED
FINAL_NULL_P_VALUE=NOT APPLICABLE
```

The grouped trajectory permutation and `p=0.90` belong to the earlier Regime A result and must not be attributed to this final experiment.

## 47. Primary Statistical Analysis

The primary estimand was the unweighted mean of trajectory-specific \\(R^2\\):

\\[ R^2\_i=1-\frac{\sum\_t(y\_{it}-\hat y\_{it})^2} {\sum\_t(y\_{it}-\bar y\_i)^2}, \qquad R^2\_{\mathrm{macro}}=\frac1{25}\sum\_i R^2\_i. \\]

RMSE was likewise the unweighted mean of per-trajectory RMSE. MAE was descriptive. Pooled-row metrics were secondary and non-gating; the terminal archive does not preserve their numeric values.

Each scene’s five outer prediction sets covered all 475 rows exactly once. The five fold metrics were not averaged; the out-of-fold predictions were pooled and then summarized trajectory-equally.

Confidence intervals resampled the 25 complete trajectory-specific \\(R^2\\) values with replacement 10,000 times using NumPy `default_rng`, seed `2026081503`, and 2.5/97.5 percentiles.

## 48. Final Hidden-State Result

| ReadoutMacro \\(R^2\\)95% CIRMSEMAE |                |                                  |              |              |
| ----------------------------------- | -------------- | -------------------------------- | ------------ | ------------ |
| BEST-K WALL                         | -14.7034147101 | [-17.6713609520, -12.1453290303] | 2.1098100620 | 1.9370599425 |
| FULL WALL                           | -14.6427001722 | [-17.5943481524, -12.1116161717] | 2.1069309567 | 1.9347209554 |

BEST-K failed:

- `WALL_r2`;
- `WALL_rmse`;
- `WALL_beats_training_time_baseline`.

The result is not borderline. Both the point estimate and entire bootstrap interval are deeply negative, and the RMSE exceeds the ceiling by approximately `1.9542` blocks.

## 49. Per-Unit Results

Per-unit capture, physical validation, extraction completion, shape, checksum, and durability are available for all 50 units.

Per-trajectory decoder predictions, \\(R^2\\), RMSE, MAE, bias, and correlation are not present in the terminal archive. They cannot be reconstructed without reopening/rerunning the frozen analysis beyond this audit’s remit.

Therefore:

```
PER_TRAJECTORY_DECODER_METRICS=UNKNOWN — INSUFFICIENT ARCHIVED EVIDENCE
PER_UNIT_SCIENTIFIC_PASS_COUNTS=UNKNOWN
```

This is a reporting-granularity limitation, not dataset missingness.

## 50. Pairwise Results

All 25 pairs passed identity, label, target-window, path, and coverage equality. No pair was excluded.

No per-pair WALL-minus-NO\_WALL metric, paired CI, or paired hypothesis test was archived. The design was paired physically; the terminal statistical analysis summarized scenes separately.

## 51. Direction Results

Final directional decoder estimates are `UNKNOWN — INSUFFICIENT ARCHIVED EVIDENCE`. The final aggregate includes both directions, and directional balance was preserved in every fold.

It would be unjustified to infer separate LTR and RTL scientific outcomes from the combined metric alone.

## 52. Layout Results

Only `layout_01` was tested. Its aggregate hidden result failed. There is no multi-layout analysis and no fresh-layout generalization estimate.

## 53. Occlusion-Age Results

All \\(\tau=1…19\\) rows were evaluated. Training/model selection used only \\(\tau\le15\\). The final archive does not retain per-\\(\tau\\), bin-specific, within-context, or beyond-context metrics.

Thus any claim that performance decayed, improved, or remained stable with occlusion age in this final experiment is `UNKNOWN — INSUFFICIENT ARCHIVED EVIDENCE`.

## 54. Wall vs No-Wall Analysis

Descriptive contrast:

| ReadoutWALL minus NO\_WALL RMSEWALL minus NO\_WALL \\(R^2\\) |                      |                |
| ------------------------------------------------------------ | -------------------- | -------------- |
| BEST-K                                                       | +2.0044756458 blocks | -15.6616827690 |
| FULL                                                         | +1.9950921908 blocks | -15.5932322506 |

BEST-K WALL RMSE was approximately `20.03×` the NO\_WALL RMSE.

This enormous scene divergence, combined with exact pairing and positive-control success, is consistent with current visual evidence supporting the visible decoder while the tested layer/readout did not track hidden position. It is not itself a formal paired causal estimate, because no paired effect statistic or confidence interval was specified.

## 55. U1 Adjudication

Assuming U1 denotes defensible hidden-position decoding under the frozen qualification criteria:

```
U1 NOT ESTABLISHED
```

It is not `U1 NOT INTERPRETABLE`, because the apparatus and positive control passed. It is an interpretable negative result for this exact layer, representation family, apparatus, and cohort.

It does not establish that MineWorld contains no hidden-object information in any layer or representation.

## 56. U2 Design

No uncertainty target, predictive distribution, variance head, calibration curve, scoring rule, or uncertainty authority was included in Stage 2.

## 57. U2 Result

```
U2 NOT TESTED
U2 NOT ESTABLISHED
UNCERTAINTY CALIBRATION=NOT TESTED
```

## 58. U3

No analysis tested whether uncertainty increased during occlusion, depended on \\(\tau\\), or contracted upon reappearance.

```
U3 NOT TESTED
U3 NOT ESTABLISHED
```

## 59. U4

No intervention modified layer-4 activations, no rollout or behavior was causally perturbed, and no reappearance prediction test was run.

```
U4 NOT TESTED
U4 NOT ESTABLISHED
CAUSAL_USE=NOT ESTABLISHED
BEHAVIORAL_RELIANCE=NOT ESTABLISHED
```

## 60. Per-Unit Validation Loop

Each capture unit required:

- correct authority, manifest, namespace, and unit identity;
- exact 180-frame count;
- path/state equality;
- valid scene/camera/target identity;
- aligned clocks;
- correct extent-class target rows;
- no contamination;
- runtime-provenance resolution;
- local SHA verification;
- durable checksum manifest;
- remote object existence/readback.

Each extraction required:

- admitted capture receipt;
- admitted physical gate;
- local capture inventory revalidation;
- exact authority-selected target rows;
- correct legacy and scientific trajectory namespaces;
- bound main and VAE checkpoints;
- shape/dtype/layer check;
- atomic output completion;
- durable activation publication and readback.

All 50 passed.

## 61. Cohort Validator

The cohort validator established:

```
valid captures=50/50
complete pairs=25/25
target labels=950
pair labels equal=true
distinct windows=17
window span=36…80
capture closure homogeneous=true
target rows authority-bound=true
```

It also independently rederived fold discipline, checkpoint equality under the accepted runtime-equivalence rule, complete out-of-fold row coverage, and readout configuration.

Cohort validation did not imply scientific success.

## 62. Final Physical Gate

The physical gate passed under source commit `76098ae…` with:

```
capture_units=50
paired_trajectories=25
status=PASS
gate_critical_closure=199ae4dd4a29d2dad9ee47984268171a5a667ab7f3adee48323f178dc946fa89
durable_payload_sha256=84fc5d24123d9bfa6c6f39f037babcec9b2b746baaaab2e0578e6ee0bf5890f4
checksum_manifest_sha256=3fb66617186a4930a3891a7173073846c77f00d48109b085bf941f0377ec57e3
```

Required checks:

1. capture admission;
2. clock alignment;
3. durability;
4. hidden-row validity;
5. pair coverage;
6. path state;
7. physical support;
8. runtime provenance;
9. stable visibility;
10. zero target-row contamination.

The wrapper receipt SHA `639f37d1…` was lost. The payload was admitted as `HISTORICAL_DURABLE_GATE_PAYLOAD_ADMITTED`; it was not regenerated or replayed.

## 63. Scientific Analysis Gate

| GateFrozen ruleObservedStatus |                                      |                            |      |
| ----------------------------- | ------------------------------------ | -------------------------- | ---- |
| NO\_WALL \\(R^2\\)            | point and lower CI >0                | 0.95827; lower 0.94339     | PASS |
| NO\_WALL RMSE                 | ≤0.15560478                          | 0.10533442                 | PASS |
| WALL \\(R^2\\)                | point and lower CI >0                | -14.70341; lower -17.67136 | FAIL |
| WALL RMSE                     | ≤0.15560478                          | 2.10981006                 | FAIL |
| WALL beats time baseline      | neural RMSE <0.41359312              | 2.10981006                 | FAIL |
| Time confound                 | \\(\tau\le15\\) time \\(R^2\le0.1\\) | -0.18192034                | PASS |

All six were required. Therefore terminal status was FAIL.

## 64. Final Execution Chronology

| UTCEvent     |                                                                |
| ------------ | -------------------------------------------------------------- |
| Aug 17       | v0.4 Stage-1 capture under `046b34a`; all eight units complete |
| Aug 18       | 50 Stage-2 captures under `49f0cca`/`cb16335`                  |
| Aug 19 08:24 | Physical gate PASS under `76098ae`                             |
| Aug 19 22:55 | T1 validator false-negative FAIL                               |
| 23:23        | Same T1 artifacts revalidated PASS; no re-extraction           |
| Aug 20 01:19 | Final HEAD `020dfec` frozen                                    |
| 01:21:07     | Final successor Stage-2 authorization generated                |
| 02:15–02:25  | Final T1 canary PASS, revalidation only                        |
| 02:30        | Extraction campaign launched                                   |
| 10:26:04     | 50/50 extraction complete; outcome still unexposed             |
| \~10:47      | External launcher artifact-ID refusal; no science ran          |
| \~11:06      | Environment-report digest refusal; three attempts, no fit ran  |
| 11:42:24     | Successful BEST-K attempt began/completed                      |
| 11:48:38     | FULL began/completed                                           |
| 11:54:28     | Terminal adjudication completed                                |
| 12:24:26     | Final archive created                                          |
| 12:24:42     | Archive root closure generated                                 |

## 65. Retries

- Capture recaptures: 0.
- Replacement trajectories: 0.
- Gate replays: 0.
- Extraction re-extractions: 0.
- Successful scientific readout retries: 0.
- Initial T1 validator: one false-negative verdict, then read-only revalidation.
- First BEST-K operational launch: three deterministic verifier refusals; no model fit or outcome.
- Final BEST-K/FULL/terminal: one attempt each.

The event log’s three early `stage2_best_k` failures are operational attempt records, not three scientific analyses.

## 66. Exclusions

Prospective exclusions:

- partial-transition rows were unscored;
- unresolved FIR-warmup rows could not enter aligned Stage-1 evidence;
- target rows failing identity, support, path, frame, provenance, or extent truth would fail closed;
- \\(\tau=16…19\\) could not enter hyperparameter selection or final fit but remained in evaluation;
- all layers except layer 4 were forbidden.

Observed exclusions:

- zero Stage-2 identities;
- zero captures;
- zero target rows after admission;
- zero replacement units;
- zero post-outcome guard bands or row removals.

## 67. Missingness

Scientific data missingness was zero for the frozen Stage-2 domain:

```
captures present=50/50
extractions present=50/50
target rows present=950/950
outer held-out predictions=950/950 across both scenes
```

Unavailable reporting summaries—per-trajectory metrics, direction metrics, \\(\tau\\) curves—are not missing scientific rows; they are absent derived artifacts.

## 68. Statistical Methods

- Five outer grouped folds, five identities held out each.
- Five inner grouped, direction-stratified folds on the 20 training identities.
- BEST-K token ranking and K/alpha selection inside training data.
- Standardization fitted within training splits.
- Ridge target centering without target standardization.
- Training limited to \\(\tau\le15\\); evaluation \\(\tau=1…19\\).
- Primary trajectory-equal macro \\(R^2\\).
- Error: unweighted mean per-trajectory RMSE.
- 10,000 whole-trajectory bootstrap resamples.
- No asymptotic p-value.
- No final permutation null.
- No formal scene-difference test.

## 69. Multiple Comparisons

The experiment did not perform an opportunistic layer search. Layer 4 was fixed, and all-layer extraction was forbidden.

BEST-K searched K and alpha inside nested cross-validation; this is model selection, not post-hoc selection on outer-test performance. FULL was explicitly secondary and non-rescuing. Six gates were jointly conjunctive: failure of any one caused FAIL. No multiplicity-adjusted p-values were required or calculated because the decision was gate-based rather than a family of null-hypothesis tests.

## 70. Final Decision Logic

Pseudocode:

```
if provenance/completeness/physical evidence invalid:
    BLOCKED
else:
    rederive BEST_K metrics and all six gates
    if every gate PASS:
        PASS
    else:
        FAIL

FULL never changes the status.
A completed FAIL is terminal.
An operational failure may never be reported as scientific FAIL.
```

The terminal evaluator independently rederived the status from bound evidence and checked that the producer’s self-grade agreed.

## 71. Final Adjudication

```
STATUS=FAIL
REASONS=[
  WALL_beats_training_time_baseline,
  WALL_r2,
  WALL_rmse
]
LEADING_READOUT=BEST_K
FULL_MAY_RESCUE=false
CONFIRMATORY_INTERPRETATION=false
MAY_AUTHORIZE_NEXT_RUNG=false
```

Decision file SHA-256:

```
991cccb33731a2694f5c5940392fb9861304caf21869cd494f561b3bc74fa615
```

Evidence file SHA-256:

```
d3e7d745b25b06d84e490c7e1a8b3d518674e6d7afee96b228332077abd7b4b0
```

## 72. Science vs Operations

Operationally, the campaign succeeded: `COMPLETE_VALIDATED_DURABLE`.

Scientifically, it failed: `FAIL`.

The distinction is essential. Lost wrappers, OOM risk, validator bugs, identity collisions, authorization bindings, and timestamp nonces were operational/provenance issues resolved before any successful scientific computation. The final WALL failure came from valid evidence after those issues were closed.

## 73. Science vs Apparatus

The apparatus passed:

- physical geometry;
- rendered visibility;
- clock alignment;
- target headroom;
- identity/path state;
- runtime provenance;
- durability;
- positive visible control.

Therefore the hidden negative should not be relabeled as apparatus failure or measurement failure. The frozen BGR preprocessing remains a design limitation, but the visible result shows that this exact model path was highly decodable when the target was visible.

## 74. Historical Failed Qualification Attempt 1

The first P3 development qualification evaluated three candidate cohorts, C01–C03, each with 25 paired trajectories at speeds 2.0, 2.5, and 3.0. All failed before extraction.

C01 had 475 clean target rows per scene but calibration precision `0.846847`; C02 and C03 also failed, with one and seven contaminated rows respectively. Pooled precision was base-rate-sensitive and concealed that the detector’s false-positive mechanism was stable across speeds. No P3 candidate activation extraction occurred.

## 75. Historical Physical-Extent Failure

The original truth predicate traced one ray to the sheep centre, while the detector responded to any sufficiently large magenta portion of the rendered wool silhouette. Near an occlusion boundary the centre could be hidden while most of the sheep remained visible. One examined boundary frame retained approximately 97% of the silhouette.

This was not detector noise. It was a mismatch between the physical quantity used as truth and the physical quantity sensed by the detector. The remedy was to define independent truth over renderer-derived extent.

## 76. Historical Extent-Corrected Attempt

The v0.3 attempt correctly adopted extent truth. Its held-out visibility gate itself passed:

| DirectionStable visibleStable hiddenPartialFP/FN |     |    |    |     |
| ------------------------------------------------ | --- | -- | -- | --- |
| LTR                                              | 217 | 74 | 53 | 0/0 |
| RTL                                              | 202 | 88 | 54 | 0/0 |

Nevertheless, the overall Stage-1 decision failed five gates. Four were caused by the stale builder’s old semantics. The fifth was a genuine temporal anomaly. The failed decision remained immutable and did not authorize Stage 2.

## 77. Historical Temporal Failure

In v0.3, `a1x_rtl_wall_r01` had FIR group delay approximately `3.800033` ticks but cross-correlation lag `3.821299` against FIR mode 2. Its mode departure was `1.821299` ticks, above the frozen 1.0 bound.

This result was not excluded, accommodated, or used to widen the threshold. v0.4 retained the same temporal rule and collected a new, prospectively named inventory.

Earlier detector-bound v0.2 also retained its exact failure: `a1q_rtl_wall_r02` frame 28 lay `0.006282776508991` blocks inside the transferred band and was detector-visible. No guard band was added around that value.

## 78. Final Repairs

The scientifically relevant repairs were:

- matched NO\_WALL pairing;
- renderer-equivalent apparatus qualification;
- causal-FIR temporal labels;
- extent-based truth;
- direct held-out geometry classification;
- builder/evaluator synchronization;
- FIRST\_N authority binding;
- capture/processing provenance split;
- physical-gate admission based on closures;
- explicit checkpoint and typed trajectory bindings;
- extraction-only outcome firewall;
- independently rederived fold discipline and decision;
- external timestamp-only runtime equivalence.

None changed the final scientific gate after an outcome.

## 79. Repair Legitimacy

Repairs fall into three classes:

1. **Pre-outcome scientific/apparatus repairs:** matched control, temporal method, extent truth, synchronized builder, v0.4 inventory. These were frozen before final Stage-2 outcomes.
2. **Pre-outcome execution/provenance repairs:** extractor initialization, typed identities, closure admission, atomic files, extraction-only launcher.
3. **Post-firewall-crossing but pre-fit operational repair:** runtime timestamp equivalence. The initial readout stopped before model fitting; the repair changed only equivalence of authenticated reports and left the repo and all scientific parameters frozen.

Post-outcome activity was archival/reporting plus the observation that ten WALL tensors shared a digest. It did not alter adjudication.

## 80. Final Evidence Archive

Archive location:

[Final archive]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820)

Durable URI:

```
s3://sagemaker-us-east-1-323206973672/mineocclude/
regime_a_prime_qualification_v0_1/prospective_development_v0_4/
stage2/archive/regime_a_prime_stage2_v0_4_final_20260820
```

Declared archive body:

```
ARCHIVE_FILE_COUNT=214
ARCHIVE_TOTAL_BYTES=5299828
ARCHIVE_MANIFEST_SHA256=7c3dee282f811d00d1c2a76dea2f33e8b03bafbc8b28518b06eb8ea5de1f9b2f
ARCHIVE_INVENTORY_SHA256=cc3ab83a52f70be2920e5e7125614f52ecc86d22b31f7f01f272545d1ff1615d
ARCHIVE_ROOT_SHA256=25f0a182b5d1aa35030c16b1b6fe96f85fe0f7d7f163464dfa4fb78b0a91fadc
```

The inventory additionally references 50 durable activation tensors totaling `1,307,449,600` bytes.

## 81. Evidence Durability

The archive record declares:

```
DURABLE_READBACK_VERIFIED=true
WORKTREE_CLEAN_AT_ARCHIVE=true
FROZEN_REPO_MODIFIED=false
SCIENTIFIC_ARTIFACTS_MODIFIED=false
BLOCKER=none
```

All 215 objects in the archive body upload pass—213 content files, inventory, and manifest—were downloaded and compared byte-for-byte. The final record and root digest were uploaded/read back in the closure pass.

Raw capture and derived activation payloads remained in their Stage-2 S3 prefixes with per-object checksum inventories.

## 82. Reproducibility

The package preserves:

- prospective authorities and manifests;
- source commit and critical-source closures;
- model/checkpoint/config identities;
- environment reports;
- all capture and extraction receipts;
- target labels/windows;
- fold selections and selected hyperparameters;
- BEST-K/FULL outputs;
- terminal decision/evidence;
- controller logs;
- runtime-equivalence implementation and audit log;
- archive inventory and closure digests.

A complete numerical rerun also requires access to the S3-referenced 50 tensors and capture objects. Those large tensors are not copied into the compact local archive.

## 83. Complete Quantitative Table

| QuantityValue                  |                                      |
| ------------------------------ | ------------------------------------ |
| Independent identities         | 25                                   |
| Capture units                  | 50                                   |
| Frames                         | 9,000                                |
| Scored rows                    | 950                                  |
| WALL stable-hidden rows        | 475                                  |
| NO\_WALL stable-visible rows   | 475                                  |
| Direction balance              | 13 LTR / 12 RTL                      |
| Distinct windows               | 17                                   |
| Window span                    | 36–80                                |
| Target rows/capture            | 19                                   |
| Target SD min/median/max       | 0.436564 / 0.550911 / 0.696607       |
| Layer/tokens/width             | 4 / 336 / 2048                       |
| Activation bytes               | 1,307,449,600                        |
| BEST-K NO\_WALL \\(R^2\\)      | 0.9582680589                         |
| BEST-K NO\_WALL CI             | [0.9433883673, 0.9695287239]         |
| BEST-K NO\_WALL RMSE           | 0.1053344162                         |
| BEST-K WALL \\(R^2\\)          | -14.7034147101                       |
| BEST-K WALL CI                 | [-17.6713609520, -12.1453290303]     |
| BEST-K WALL RMSE               | 2.1098100620                         |
| FULL NO\_WALL \\(R^2\\)/RMSE   | 0.9505320784 / 0.1118387659          |
| FULL WALL \\(R^2\\)/RMSE       | -14.6427001722 / 2.1069309567        |
| Time baseline \\(R^2\\)/RMSE   | 0.2532082408 / 0.4135931190          |
| Time \\(\tau\le15\\) \\(R^2\\) | -0.1819203399                        |
| Frozen RMSE ceiling            | 0.1556047776                         |
| Bootstrap                      | 10,000 trajectories; seed 2026081503 |
| Final status                   | FAIL                                 |

## 84. Complete Per-Unit Table

Each row below explicitly covers two capture/extraction units; `W/N` means WALL and NO\_WALL. Both members in every row were `COMPLETE_VALIDATED_DURABLE`, had 19 target rows, shape `[19,336,2048]`, and passed capture/extraction admission.

| IdentityUnits W / NEpisodes W / NDirFoldWindow |                                    |               |     |   |       |
| ---------------------------------------------- | ---------------------------------- | ------------- | --- | - | ----- |
| t01                                            | `a2y_t01_wall` / `a2y_t01_no_wall` | 86001 / 86501 | LTR | 0 | 48–66 |
| t02                                            | `a2y_t02_wall` / `a2y_t02_no_wall` | 86002 / 86502 | LTR | 0 | 53–71 |
| t03                                            | `a2y_t03_wall` / `a2y_t03_no_wall` | 86003 / 86503 | LTR | 0 | 50–68 |
| t04                                            | `a2y_t04_wall` / `a2y_t04_no_wall` | 86004 / 86504 | RTL | 0 | 49–67 |
| t05                                            | `a2y_t05_wall` / `a2y_t05_no_wall` | 86005 / 86505 | RTL | 0 | 47–65 |
| t06                                            | `a2y_t06_wall` / `a2y_t06_no_wall` | 86006 / 86506 | RTL | 1 | 36–54 |
| t07                                            | `a2y_t07_wall` / `a2y_t07_no_wall` | 86007 / 86507 | RTL | 1 | 38–56 |
| t08                                            | `a2y_t08_wall` / `a2y_t08_no_wall` | 86008 / 86508 | LTR | 1 | 49–67 |
| t09                                            | `a2y_t09_wall` / `a2y_t09_no_wall` | 86009 / 86509 | LTR | 1 | 59–77 |
| t10                                            | `a2y_t10_wall` / `a2y_t10_no_wall` | 86010 / 86510 | RTL | 1 | 50–68 |
| t11                                            | `a2y_t11_wall` / `a2y_t11_no_wall` | 86011 / 86511 | LTR | 2 | 51–69 |
| t12                                            | `a2y_t12_wall` / `a2y_t12_no_wall` | 86012 / 86512 | LTR | 2 | 51–69 |
| t13                                            | `a2y_t13_wall` / `a2y_t13_no_wall` | 86013 / 86513 | RTL | 2 | 38–56 |
| t14                                            | `a2y_t14_wall` / `a2y_t14_no_wall` | 86014 / 86514 | RTL | 2 | 42–60 |
| t15                                            | `a2y_t15_wall` / `a2y_t15_no_wall` | 86015 / 86515 | LTR | 2 | 58–76 |
| t16                                            | `a2y_t16_wall` / `a2y_t16_no_wall` | 86016 / 86516 | RTL | 3 | 37–55 |
| t17                                            | `a2y_t17_wall` / `a2y_t17_no_wall` | 86017 / 86517 | LTR | 3 | 46–64 |
| t18                                            | `a2y_t18_wall` / `a2y_t18_no_wall` | 86018 / 86518 | LTR | 3 | 53–71 |
| t19                                            | `a2y_t19_wall` / `a2y_t19_no_wall` | 86019 / 86519 | RTL | 3 | 39–57 |
| t20                                            | `a2y_t20_wall` / `a2y_t20_no_wall` | 86020 / 86520 | RTL | 3 | 48–66 |
| t21                                            | `a2y_t21_wall` / `a2y_t21_no_wall` | 86021 / 86521 | LTR | 4 | 46–64 |
| t22                                            | `a2y_t22_wall` / `a2y_t22_no_wall` | 86022 / 86522 | RTL | 4 | 41–59 |
| t23                                            | `a2y_t23_wall` / `a2y_t23_no_wall` | 86023 / 86523 | RTL | 4 | 41–59 |
| t24                                            | `a2y_t24_wall` / `a2y_t24_no_wall` | 86024 / 86524 | LTR | 4 | 56–74 |
| t25                                            | `a2y_t25_wall` / `a2y_t25_no_wall` | 86025 / 86525 | LTR | 4 | 62–80 |

## 85. Complete Pair Table

| IDPhaseSeedTarget SDPair integrity |    |                     |          |      |
| ---------------------------------- | -- | ------------------- | -------- | ---- |
| t01                                | 0  | 3915261969990919987 | 0.570091 | PASS |
| t02                                | 3  | 8508665832063723489 | 0.602114 | PASS |
| t03                                | 6  | 493046569211311644  | 0.555188 | PASS |
| t04                                | 9  | 792486241468217257  | 0.502310 | PASS |
| t05                                | 12 | 5404145764100272499 | 0.483110 | PASS |
| t06                                | 0  | 656450052195465550  | 0.550911 | PASS |
| t07                                | 3  | 3574419961633238087 | 0.618239 | PASS |
| t08                                | 6  | 1911162621253564828 | 0.541771 | PASS |
| t09                                | 9  | 7756503157389512178 | 0.568031 | PASS |
| t10                                | 12 | 5893190328731316447 | 0.501375 | PASS |
| t11                                | 0  | 263266720351843509  | 0.505444 | PASS |
| t12                                | 3  | 8301312004391973251 | 0.465943 | PASS |
| t13                                | 6  | 5483827162276972149 | 0.549412 | PASS |
| t14                                | 9  | 3274244584702731964 | 0.597085 | PASS |
| t15                                | 12 | 7250784209002864486 | 0.559476 | PASS |
| t16                                | 0  | 1453456186608874764 | 0.604845 | PASS |
| t17                                | 3  | 5774324499122541367 | 0.655302 | PASS |
| t18                                | 6  | 1447968820417449307 | 0.532495 | PASS |
| t19                                | 9  | 8925345204373466469 | 0.499291 | PASS |
| t20                                | 12 | 5869089012106000418 | 0.482697 | PASS |
| t21                                | 0  | 5883303364891532395 | 0.436564 | PASS |
| t22                                | 3  | 3846041916206366267 | 0.567181 | PASS |
| t23                                | 6  | 6685731264626020326 | 0.696607 | PASS |
| t24                                | 9  | 7092966032674853661 | 0.689675 | PASS |
| t25                                | 12 | 3468316064057876123 | 0.547277 | PASS |

## 86. Complete Gate Table

| StageGateStatus    |                                  |      |
| ------------------ | -------------------------------- | ---- |
| Stage 1            | calibration detector response    | PASS |
| Stage 1            | calibration world/wall support   | PASS |
| Stage 1            | hidden-row contamination         | PASS |
| Stage 1            | transition measurement           | PASS |
| Stage 1            | temporal alignment               | PASS |
| Stage 1            | evidence completeness            | PASS |
| Stage 1            | stable visibility robustness     | PASS |
| Stage 1            | unit completeness                | PASS |
| Stage 1            | identity/runtime/path/durability | PASS |
| Stage 2 physical   | all ten physical checks          | PASS |
| Stage 2 scientific | NO\_WALL \\(R^2\\)               | PASS |
| Stage 2 scientific | NO\_WALL RMSE                    | PASS |
| Stage 2 scientific | WALL \\(R^2\\)                   | FAIL |
| Stage 2 scientific | WALL RMSE                        | FAIL |
| Stage 2 scientific | WALL beats time baseline         | FAIL |
| Stage 2 scientific | time-confound ceiling            | PASS |
| Terminal           | all six BEST-K gates             | FAIL |

## 87. Complete Failure-History Table

| FailureTypeResolutionScientific data changed? |                               |                                            |                        |
| --------------------------------------------- | ----------------------------- | ------------------------------------------ | ---------------------- |
| Original Regime A trajectory-equal decoding   | SCIENTIFIC                    | terminal negative; motivated diagnosis     | no                     |
| P2 renderer equivalence                       | OPERATIONAL                   | current-apparatus qualification            | no outcome             |
| P3 point/silhouette mismatch                  | APPARATUS                     | renderer-derived extent                    | new prospective design |
| v0.2 boundary false positive                  | SCIENTIFIC QUALIFICATION FAIL | retained; no guard added                   | no                     |
| v0.3 stale builder                            | SOFTWARE                      | synchronized builder/evaluator             | new inventory          |
| v0.3 RTL timing anomaly                       | SCIENTIFIC QUALIFICATION FAIL | retained; same rule retested prospectively | no                     |
| Lost physical-gate wrapper                    | PROVENANCE/OPERATIONAL        | admitted surviving durable payload         | no replay              |
| Extractor uninitialized                       | SOFTWARE                      | explicit `ensure_loaded()`                 | no output              |
| Capture/runtime identity collision            | SOFTWARE                      | typed namespaces                           | no output              |
| T1 target/readback FAIL                       | VALIDATOR FALSE NEGATIVE      | read-only revalidation                     | no regeneration        |
| Authorization artifact ID                     | OPERATIONAL                   | external launcher binding                  | no fit                 |
| Environment timestamp hashes                  | OPERATIONAL/PROVENANCE        | audited timestamp-only equivalence         | no science change      |
| Final WALL gates                              | SCIENTIFIC                    | terminal FAIL; not repaired                | result stands          |

## 88. Claim Ledger

| ClaimStatus                                               |                             |
| --------------------------------------------------------- | --------------------------- |
| Physical apparatus qualified                              | SUPPORTED                   |
| Temporal alignment qualified                              | SUPPORTED                   |
| Visibility truth qualified                                | SUPPORTED                   |
| Every capture/extraction complete                         | SUPPORTED                   |
| Matched visible layer-4 decoding works                    | SUPPORTED                   |
| Hidden layer-4 decoding meets frozen criteria             | REFUTED for this experiment |
| Hidden target information absent from all representations | UNSUPPORTED                 |
| Layer 4 contains no hidden information whatsoever         | UNSUPPORTED                 |
| Target-specific permutation advantage                     | NOT TESTED                  |
| Beats last-seen                                           | NOT TESTED                  |
| Beats constant velocity                                   | NOT TESTED                  |
| Independently rules out time/motion                       | UNSUPPORTED                 |
| Object permanence                                         | UNSUPPORTED                 |
| Belief                                                    | UNSUPPORTED                 |
| Uncertainty representation/calibration                    | NOT TESTED                  |
| Causal/behavioral use                                     | NOT TESTED                  |
| Layout generalization                                     | NOT TESTED                  |
| Confirmatory result                                       | FORBIDDEN                   |

## 89. Validity-Threat Ledger

| ThreatHandling / residual     |                                                                    |
| ----------------------------- | ------------------------------------------------------------------ |
| Frames treated as independent | avoided; grouped trajectories and trajectory bootstrap             |
| Time/position shortcut        | bidirectional design and time baseline; motion alternatives remain |
| Visibility leakage            | full rendered-extent geometry; partial rows excluded               |
| Detector circularity          | detector did not define truth                                      |
| Temporal mislabeling          | direction-specific causal FIR                                      |
| Fold leakage                  | nested grouped CV and independent verification                     |
| Layer fishing                 | layer 4 fixed; all-layer extraction forbidden                      |
| Positive-control failure      | did not occur                                                      |
| Single layout                 | unresolved external validity threat                                |
| One speed/noise               | unresolved external validity threat                                |
| Frozen BGR preprocessing      | residual apparatus-specific limitation                             |
| Linear readout restriction    | cannot rule out nonlinear representation                           |
| No final permutation null     | target-specificity remains untested                                |
| No motion baselines           | last-seen/constant-velocity alternatives remain                    |
| Runtime shim                  | tightly audited but external to frozen repository                  |
| Lost gate wrapper             | transparently admitted payload; residual provenance discontinuity  |
| Identical WALL tensors        | post-hoc mechanistic clue; not a predeclared analysis              |
| Missing per-unit metrics      | limits heterogeneity diagnosis                                     |

Ten WALL activation tensors—t04, t05, t09, t10, t14, t15, t18, t20, t24, and t25—shared SHA `3f14b22e…`; WALL had 16 distinct tensor digests among 25, while NO\_WALL had 25/25 distinct. This is post-hoc and cannot change the verdict, but suggests substantial representational collapse/equivalence for fully occluded visual-action contexts.

## 90. Discrepancy Ledger

| DiscrepancySourcesResolutionCanonical report |                                                                                    |                                                                    |                                                          |
| -------------------------------------------- | ---------------------------------------------------------------------------------- | ------------------------------------------------------------------ | -------------------------------------------------------- |
| Archive physical file count                  | root says 216; filesystem and manifest arithmetic give 217                         | manifest has 214 entries plus three closure files                  | report declared 214 body, directly observed 217 physical |
| Inventory rows vs files                      | 263 inventory records vs 217 files                                                 | 50 rows are S3-only activation references                          | not physical files                                       |
| `ARCHIVE_FILE_COUNT=214`                     | final record                                                                       | explicitly means 213 content + inventory, excludes 3 closure files | accepted definition                                      |
| Visibility march wording                     | extent/sample prose says “63-sample”; authority says 64 march samples/63 interiors | machine-readable authority controls                                | 64 samples, 63 interior steps                            |
| Authority Java spelling                      | apparatus prose says Amazon Corretto; runtime token is `Corretto-17.0.20.8.1`      | runtime field deliberately corrected to emitted token              | same JDK build                                           |
| Stage-2 authority draft status               | authority file vs authorization receipt                                            | separate authorization activates locked method                     | authorized after Stage-1                                 |
| Capture commits differ                       | 1 at `49f0cca`, 49 at `cb16335`                                                    | exact 406-component capture closure equal                          | homogeneous apparatus                                    |
| Environment report SHA differs 50 ways       | receipts                                                                           | content differs only in generated timestamp                        | runtime-equivalent under audited shim                    |
| Lost physical-gate wrapper                   | local state vs durable payload                                                     | explicit historical-payload admission                              | provenance loss disclosed, gate not replayed             |
| Final full-frame visibility counts           | legacy QA vs extent target evidence                                                | QA labels are not final extent truth                               | full counts UNKNOWN; target counts authoritative         |
| Historical Regime A metrics                  | old phases vs final v0.4                                                           | different designs and labels                                       | never import old null/baselines into final result        |

## 91. Unknown / Missing Evidence

The following are not recoverable from the terminal archive without recomputation:

- final per-trajectory decoder metrics;
- pairwise decoder differences;
- direction-specific metrics;
- per-\\(\tau\\) or bin metrics;
- pooled-row \\(R^2\\);
- prediction bias or Pearson correlation;
- formal WALL-versus-NO\_WALL paired test;
- full-frame Stage-2 extent-class counts;
- final last-seen and constant-velocity baselines;
- final grouped permutation null and p-value;
- nonlinear readouts;
- other layers;
- other layouts, speeds, noise levels, targets, or checkpoints;
- uncertainty or causal analyses.

These are `UNKNOWN — INSUFFICIENT REPOSITORY EVIDENCE` or `NOT TESTED`, not negative findings.

## 92. What This Experiment Establishes

**Measurement validation:** The fixed capture, geometry, timing, provenance, activation, and layer-4 decoding pipeline was operationally valid. Visible position was strongly decodable on matched NO\_WALL trajectories.

**Hidden-state science:** The tested BEST-K and FULL layer-4 linear readouts failed to recover fully occluded current position under the frozen criteria. The leading result was \\(R^2=-14.7034\\), RMSE `2.10981`.

**Uncertainty science:** Nothing established.

**Causal science:** Nothing established.

**Generalization:** Only fresh stochastic trajectories within one fixed layout and motion regime were tested. The experiment establishes no fresh-layout or apparatus generalization.

## 93. What This Experiment Does Not Establish

It does not establish:

- object permanence;
- belief or knowledge;
- a general world model;
- absence of all hidden-object information;
- absence of nonlinear hidden-state structure;
- absence of information in other layers;
- calibrated uncertainty;
- uncertainty growth with occlusion;
- causal use of representation;
- behavioral reliance;
- superiority to last-seen or constant velocity;
- superiority to a structured permutation null;
- generalization across layouts, cameras, walls, speeds, noise, entities, or checkpoints;
- a confirmatory result.

A tempting but invalid sentence would be: “MineWorld has no representation of hidden objects.” The experiment is much narrower than that claim.

## 94. Paper-Ready Final Experiment Methodology

# Paper-Ready Final Experiment Methodology

Regime A′ v0.4 was a prospectively governed development experiment designed to determine whether MineWorld layer-4 activations supported accurate linear decoding of the current position of a fully occluded moving object under an independently qualified physical apparatus. It followed the negative original Regime A experiment, which had exposed a major difference between pooled-row prediction and trajectory-specific generalization, and subsequent forensics showing that a meaningful hidden-state result required a matched visible control, temporally aligned targets, renderer-appropriate occlusion truth, and a fail-closed provenance chain.

The study was explicitly classified `DEVELOPMENT_ONLY`. Its units were ineligible for confirmatory reuse, and neither PASS nor FAIL could by itself authorize confirmation, intervention, or stronger cognitive interpretation. Scientific methods were specified through `regime-a-prime-prospective-development-authority-v0.4`, the Stage-2 decision authority, and a separately locked manifest. The leading readout, layer, target windows, cross-validation, hyperparameter grids, bootstrap, baselines, and decision gates were fixed before Stage-2 outcome computation.

Minecraft 1.16.5 was run with Fabric Loader 0.15.11, Fabric API 0.42.0+1.16, a hash-bound MineOcclude 0.1.1 mod, Corretto 17.0.20.8.1, Mesa 25.2.8 software rendering through llvmpipe LLVM 20.1.2, and Xvfb 21.1.12. The capture display was 1280×720×24, canonical images were 640×360 at 20 Hz, and model inputs were resized to 384×224. The fixed camera feet position was `(0.5,4.0,-5.5)`, the eye position `(0.5,5.6200000048,-5.5)`, yaw/pitch/roll were zero, and FOV was 70°. The sheep moved along `x∈[-8,8]` at `y=4,z=6`. The as-built wall occupied `x∈[-3,4]`, `z∈[2,3]`, and `y∈[4,7]`.

Occlusion truth was defined independently of the rendered-image detector. Historical qualification had shown that a centre-point ray and an area-based magenta detector disagree structurally near the wall edge. The final method therefore bounded the rendered `SheepFurModel` over all reachable animation states. The largest horizontal model-space excursion was the rear-leg longitudinal bound \\(7+\sqrt{48.5}\\) sixteenths of a block, yielding a yaw-independent horizontal half-extent of `0.8727621336620037` blocks. The extent was classified by reproducing the mod’s discrete `GeometryUtil.segmentHitsWall` primitive. A five-per-axis lattice was used. No sampled point occluded meant fully visible; every corner/point occluded meant fully occluded; mixtures were partial and unscored. The detector did not enter this classification.

Stage 1 qualified the apparatus using eight prospectively named trajectories: two directions, two scenes, and two replicate roles. The first replicate measured transitions and timing; the second served as held-out validation. Each run contained 180 frames. Direction-specific nonnegative causal FIR kernels over lags 0–8 mapped server-state trajectories to aligned render-time world-x labels. Qualification required coherent group-delay and derivative cross-correlation estimands, mode agreement within the estimator’s one-tick refinement bound, and improvement over a best pure delay for every trajectory. The first eight frames were unresolved by construction because the FIR required complete lag history. Visibility calibration required zero false positives and false negatives on stable rows, at least 60 stable samples per direction/class, observed partial transitions, clean FIRST\_N rows, and complete identity, path, runtime, and durability evidence. All nine Stage-1 gates passed.

Stage 2 used 25 independently seeded trajectory identities, 13 LEFT\_TO\_RIGHT and 12 RIGHT\_TO\_LEFT. Every identity produced a WALL and matched NO\_WALL capture. Pair members shared seed, noise schedule, direction, speed `2.0` blocks/s, noise `q=0.05`, phase offset, path, labels, target frames, and fold. They differed in wall presence. Each capture contained 180 frames, for 9,000 frames total. Stage 1 materialized the first 19 qualified fully occluded WALL rows in model-frame order; the same frames and aligned labels were applied to NO\_WALL. This produced 475 rows per scene. Target windows spanned frames 36–80 and carried sufficient within-trajectory variance.

Before extraction, all 50 captures passed a cohort physical gate covering admission, clock alignment, durability, hidden-row validity, pair coverage, path state, physical support, runtime provenance, stable visibility, and zero target-row contamination. Capture objects were hash-inventoried and remotely read back. The first capture was made under commit `49f0cca…` and the remaining 49 under `cb16335…`; exact equality of a 406-component capture-critical closure established apparatus homogeneity. A later NVMe loss removed the physical-gate wrapper receipt but not its durable payload. A named authority admitted that payload while recording that the wrapper was not recovered, regenerated, or replayed.

MineWorld used a hash-bound 700M-class `LlamaLVM`/`LlamaForCausalLM` checkpoint with 20 decoder layers, hidden width 2048, 336 visual tokens per frame, 11 action tokens per frame, and maximum context 16 pairs. For each target frame, the extractor constructed the 16-pair interval from \\(t-15\\) through \\(t\\), giving 5,552 interleaved tokens. It ran a teacher-forced, batch-one inference call and retained the final frame’s 336 visual-token outputs from decoder layer 4. Only layer 4 was permitted. Each capture produced a `[19,336,2048]` float16 tensor. Fifty tensors were completed, hash-verified, durably stored, and referenced by the archive.

The leading BEST-K representation ranked spatial tokens by the maximum absolute correlation over hidden dimensions in training rows. It selected K from `[1,4,8,16,32,64,128]`, summed the selected token vectors, standardized features using training data only, and fitted kernel ridge with alpha in `[0.1,1,10,100]`. FULL used all 336 token vectors and was secondary/non-rescuing. Both used target centering but no target standardization.

Evaluation used five outer trajectory-grouped folds, five identities held out at a time, and nested five-fold direction-stratified selection on the remaining 20 identities. Inner assignment was generated by a frozen SHA-256 ordering rule independent of outcomes. Hyperparameter selection and final fitting used training rows with \\(\tau\le15\\), while all qualified rows \\(\tau=1…19\\) were evaluated. Each row received exactly one out-of-fold prediction.

The primary estimand was the unweighted mean of per-trajectory \\(R^2\\), each using that trajectory’s own target mean. Error was the unweighted mean per-trajectory RMSE in blocks. Confidence intervals used 10,000 whole-trajectory bootstrap resamples with seed `2026081503`. The matched NO\_WALL scene was the positive control. A training-only baseline used intercept, direction, \\(\tau\\), and direction-by-\\(\tau\\). No permutation null, last-seen baseline, constant-velocity baseline, uncertainty model, or causal intervention was part of final Stage 2.

The leading BEST-K readout had to pass six conjunctive gates: positive macro \\(R^2\\) with positive bootstrap lower bound in each scene, RMSE at or below `0.15560477763641264` in each scene, WALL RMSE below the training-time baseline, and time-baseline \\(R^2\le0.1\\) on training-range \\(\tau\\). FULL could not rescue failure. A terminal evaluator rederived the decision from bound evidence instead of copying the readout’s self-grade.

## 95. Paper-Ready Final Experiment Results

# Paper-Ready Final Experiment Results

The final apparatus qualified before model outcomes were inspected. All eight Stage-1 trajectories completed with no operational retries. Every unit had the expected 180 frames, exact identity and path, valid runtime provenance, complete durability evidence, and only the expected eight-row causal-FIR warmup prefix unresolved. The held-out LTR validation strata contained 213 stable-visible, 80 stable-occluded, and 51 partial rows; RTL contained 214 stable-visible, 81 stable-occluded, and 49 partial rows. The frozen detector had zero false positives and false negatives on scored stable rows. Both direction-specific temporal models passed all coherence rules, and every per-trajectory FIR improved on a pure delay. Stage 1 therefore passed all nine gates.

The Stage-2 cohort contained all 25 planned identities and both scenes for every identity. All 50 captures were complete, validated, and durable, contributing exactly 9,000 frames. The target manifest contained 19 rows per capture and 950 rows total, with 475 fully occluded WALL rows and 475 matched stable-visible NO\_WALL rows. No identity, capture, or target row was excluded or replaced. All target SDs exceeded the frozen floor. The final physical gate passed all ten required checks.

Layer-4 extraction completed for all 50 units. One previously generated T1 activation was revalidated and reused, and the remaining 49 were extracted once each. Every tensor had shape `[19,336,2048]`, dtype float16, an authority-bound target window, bound main and VAE checkpoint identities, and durable checksum/readback evidence. No capture was repeated, no physical gate was replayed, and no completed tensor was re-extracted.

The matched visible positive control succeeded. BEST-K achieved trajectory-equal macro \\(R^2=0.9582680589137229\\), with whole-trajectory bootstrap interval `[0.9433883673082907, 0.9695287238932228]`, RMSE `0.10533441619799568` blocks, and MAE `0.08216338844316161`. Its \\(R^2\\) and RMSE gates both passed. FULL similarly achieved macro \\(R^2=0.9505320783677215\\), interval `[0.9321597792050826, 0.9661492035271948]`, and RMSE `0.11183876592254306`.

The hidden WALL result was strongly negative. The leading BEST-K readout produced macro \\(R^2=-14.703414710120608\\), interval `[-17.671360952005408,-12.145329030278765]`, RMSE `2.109810061987133` blocks, and MAE `1.9370599425209607`. It therefore failed the positive-\\(R^2\\), RMSE-ceiling, and time-baseline-comparison gates. FULL did not improve the result materially: macro \\(R^2=-14.642700172224316\\), interval `[-17.594348152393437,-12.111616171701716]`, and RMSE `2.106930956729393`.

The training-only time baseline achieved RMSE `0.41359311896836387` and macro \\(R^2=0.2532082407755539\\) over all 19 rows. Its training-range \\(\tau=1…15\\) macro \\(R^2\\) was `-0.18192033993465678`, satisfying the frozen time-confound ceiling. The WALL neural readout nevertheless had much greater error than the time baseline. No last-seen, constant-velocity, or empirical permutation null was tested, and no p-value exists for final Stage 2.

BEST-K selected large K and alpha 100 in the WALL condition—K=128 in four folds and K=64 in one—while NO\_WALL selected smaller and more variable K with alpha 0.1. Ten WALL activation tensors were byte-identical, whereas every NO\_WALL tensor had a distinct digest. This observation was made post hoc and does not alter the decision, but it is compatible with a large loss of trajectory-specific activation variation during complete occlusion.

The terminal evaluator reproduced the decision from the frozen evidence and recorded `FAIL`, with failed gates `WALL_beats_training_time_baseline`, `WALL_r2`, and `WALL_rmse`. Operational status remained `COMPLETE_VALIDATED_DURABLE`. The result therefore cannot be attributed to incomplete collection, failed visibility, invalid timing, missing activations, or a failed visible control. It is an interpretable negative finding for the predeclared layer-4 linear decoding configuration.

## 96. Final Experiment Validation and Quality Assurance

Environment validation executed the exact JDK, renderer, and Xvfb probes and rehashed all critical apparatus files. Model validation bound both checkpoint hashes, both configuration hashes, MineWorld source revision, adapter identity, preprocessing identity, action conversion identity, architecture, precision, and context/token dimensions.

Physical validation independently reconstructed camera, as-built wall, target centre, trajectory path, and renderer-derived extent. It did not trust detector output as truth. Temporal validation fitted direction-specific causal FIRs, checked their group-delay and modal-lag estimands, required all support and mode-departure conditions, and excluded the unavoidable warmup prefix.

Capture validation operated per atomic unit. Every receipt bound raw and derived object digests, exact path/state, apparatus identity, target UUID/no-respawn status, and S3 readback. Pair validation compared trajectory identity, path, labels, windows, and scene membership. The cohort physical gate then evaluated all 50 units together.

Extraction validation rechecked the source capture immediately before loading frames, required the exact authority target indices, maintained separate legacy-capture and scientific identity namespaces, required an explicitly loaded runtime, and wrote tensors through a temporary sibling followed by size/header verification, fsync, and atomic rename. Downstream readout reopened and rehashed each tensor.

The runtime-equivalence shim was external because moving repository HEAD would have invalidated the 50 extraction receipts. Its scope was limited to a timestamp nonce in authenticated environment reports, and its behavior was itself audited. It admitted only the one pinned reduced environment identity.

The scientific evaluator did not trust producer assertions for folds, bootstrap configuration, row coverage, or status. It rederived all of them. FULL was enforced as non-rescuing. Operational refusals could only yield BLOCKED; scientific FAIL required complete bound evidence.

The final archive copied 213 content artifacts, generated an inventory, retained 50 activation references, and constructed manifest/final-record/root-digest closure. Durable readback was verified. The one archive count inconsistency is recorded in this report rather than concealed.

## 97. Historical Repair Narrative

The repeated qualification attempts reflect progressive testing of assumptions that could otherwise have produced a false conclusion.

Original Regime A showed that high pooled performance could coexist with poor prediction inside unseen trajectories. A matched visible control was therefore needed to distinguish representational failure from measurement failure. That control then revealed that raw same-tick server labels were not the same physical instant as rendered frames, motivating direction-specific causal alignment.

Physical qualification next exposed a deeper semantic error: the geometric centre ray and the area-sensitive silhouette detector did not measure the same event. Renderer-derived extent corrected the truth predicate without fitting to detector outcomes. The first extent-corrected campaign then exposed two independent problems: stale builder semantics and one legitimate temporal failure. The builder was synchronized, but the temporal failure was preserved and the unchanged rule was retested on a new inventory.

Stage 2 subsequently exposed execution and provenance weaknesses—mixed source freezes, a lost wrapper, typed-identity collisions, and timestamp-bearing environment hashes. Each was handled through stronger provenance semantics without changing the captures or scientific methods. Only after all these assumptions survived prospective qualification was the decoder run.

The final outcome is therefore more informative than an early negative result would have been. The visible control establishes that the tested activation/readout path can recover position. The hidden condition’s collapse is consequently a bounded scientific failure, not an uninterpretable apparatus malfunction.

## 98. Exact Evidence Index

| Claim / phaseBranch, commitExact source and fieldAuthority/status |                                      |                                                                                                                                                                                                                                                                                                                                                                                |                      |
| ----------------------------------------------------------------- | ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------- |
| Final archive verdict                                             | branch, `020dfec`                    | [FINAL\_ARCHIVE\_RECORD.txt]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/00\_ARCHIVE\_METADATA/FINAL\_ARCHIVE\_RECORD.txt), `SCIENTIFIC_VERDICT=FAIL`                                                                                                                                                                          | terminal/archive     |
| Final scientific status                                           | same                                 | [stage2\_decision.json]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/04\_SCIENTIFIC\_RESULTS/stage2\_decision.json), `status`, `reasons`, `gates`                                                                                                                                                                               | terminal, rederived  |
| Run/classification                                                | same                                 | decision: `scientific_run_id`, `classification`                                                                                                                                                                                                                                                                                                                                | terminal             |
| Frozen apparatus                                                  | v0.4 lineage                         | [authority\_parameters.json]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/01\_FROZEN\_AUTHORITY/authority\_parameters.json), `apparatus`, `runtime_identity_policy`                                                                                                                                                             | frozen               |
| Extent                                                            | `a5d763a` lineage                    | [TARGET\_EXTENT\_DERIVATION.md]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/01\_FROZEN\_AUTHORITY/TARGET\_EXTENT\_DERIVATION.md); authority `stage1_policy.visibility.target_extent`                                                                                                                                           | prospective          |
| Sample floor                                                      | v0.3/v0.4                            | [SAMPLE\_FLOOR\_ANALYSIS.md]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/01\_FROZEN\_AUTHORITY/SAMPLE\_FLOOR\_ANALYSIS.md)                                                                                                                                                                                                     | prospective          |
| Stage-1 inventory                                                 | `046b34a`                            | [stage1\_manifest.json]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/01\_FROZEN\_AUTHORITY/stage1\_manifest.json), `units`                                                                                                                                                                                                      | frozen               |
| Stage-1 PASS                                                      | `046b34a`                            | [stage1\_decision.json]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/02\_PROVENANCE\_AND\_MANIFEST/stage1/stage1\_decision.json), `status=PASS`, `gates`                                                                                                                                                                        | terminal Stage 1     |
| Stage-1 evidence                                                  | `046b34a`                            | [stage1\_evidence.json]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/02\_PROVENANCE\_AND\_MANIFEST/stage1/stage1\_evidence.json)                                                                                                                                                                                                | bound evidence       |
| Stage-2 inventory                                                 | v0.4                                 | [stage2\_locked\_manifest.json]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/01\_FROZEN\_AUTHORITY/stage2\_locked\_manifest.json), `trajectory_identities`, `capture_units`                                                                                                                                                     | frozen               |
| Stage-2 authorization                                             | `020dfec`                            | [stage2\_authorization.json]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/02\_PROVENANCE\_AND\_MANIFEST/stage2\_authorization.json), `status=FROZEN_AUTHORIZED`                                                                                                                                                                 | pre-outcome          |
| Pre-outcome provenance                                            | `020dfec`                            | [stage2\_preoutcome\_provenance.json]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/02\_PROVENANCE\_AND\_MANIFEST/stage2\_preoutcome\_provenance.json), `scientific_outcomes_observed=false`                                                                                                                                     | pre-outcome          |
| Statistical authority                                             | `f2bc2c8` lineage                    | [stage2\_decision\_authority.json]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/01\_FROZEN\_AUTHORITY/stage2\_decision\_authority.json), `readout_procedure`, `estimands`, `bootstrap_procedure`, `best_k_gates`                                                                                                                | frozen               |
| Physical gate                                                     | `76098ae`                            | [physical-gate payload]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/03\_EXTRACTION\_AND\_GATE/physical\_gate/payload.json), `physical_gates.status=PASS`                                                                                                                                                                       | qualified            |
| Historical gate admission                                         | `85d1d04` onward                     | [admission authority]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/01\_FROZEN\_AUTHORITY/stage2\_historical\_durable\_gate\_payload\_admission\_authority.json)                                                                                                                                                                 | explicit recovery    |
| Extraction preflight                                              | `020dfec`                            | [extraction\_preflight.json]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/03\_EXTRACTION\_AND\_GATE/extraction\_preflight.json)                                                                                                                                                                                                 | pre-extraction       |
| Extraction launch                                                 | `020dfec`                            | [extraction\_launch.json]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/03\_EXTRACTION\_AND\_GATE/extraction\_launch.json), scheduled units and firewall                                                                                                                                                                         | operational          |
| Extraction completion                                             | `020dfec`                            | [extraction\_summary.json]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/03\_EXTRACTION\_AND\_GATE/extraction\_summary.json), `completed_valid=50`                                                                                                                                                                               | terminal extraction  |
| Per-capture evidence                                              | capture commits                      | [capture\_receipts directory]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/03\_EXTRACTION\_AND\_GATE/capture\_receipts)                                                                                                                                                                                                         | raw/derived receipts |
| Per-extraction evidence                                           | `020dfec`                            | [extraction\_receipts directory]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/03\_EXTRACTION\_AND\_GATE/extraction\_receipts)                                                                                                                                                                                                   | activation receipts  |
| Environment                                                       | `020dfec`                            | [environment\_reports directory]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/03\_EXTRACTION\_AND\_GATE/environment\_reports)                                                                                                                                                                                                   | runtime evidence     |
| BEST-K metrics                                                    | `020dfec`                            | [best\_k.json]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/04\_SCIENTIFIC\_RESULTS/best\_k.json), `scenes.*.metrics`, `qualification_checks`                                                                                                                                                                                   | leading result       |
| FULL metrics                                                      | `020dfec`                            | [full.json]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/04\_SCIENTIFIC\_RESULTS/full.json), `scenes.*.metrics`                                                                                                                                                                                                                 | secondary            |
| Complete evidence binding                                         | `020dfec`                            | [stage2\_evidence.json]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/04\_SCIENTIFIC\_RESULTS/stage2\_evidence.json), model identity, capture inventory, readouts                                                                                                                                                                | terminal evidence    |
| Terminal reproduction                                             | `020dfec`                            | [terminal.json]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/04\_SCIENTIFIC\_RESULTS/terminal.json)                                                                                                                                                                                                                             | completed durable    |
| Runtime equivalence                                               | external tool, frozen HEAD unchanged | [runtime\_equivalence\_audit.jsonl]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/06\_CONTROLLER\_LOGS/runtime\_equivalence\_audit.jsonl) and [sitecustomize.py]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/05\_EXTERNAL\_RUNTIME\_TOOLS/runtime\_equivalence/sitecustomize.py) | operational audit    |
| Execution history                                                 | multiple                             | [events.jsonl]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/06\_CONTROLLER\_LOGS/events.jsonl), [engineering log]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/07\_REPORTS/05\_COMPLETE\_ENGINEERING\_AND\_EXPERIMENT\_LOG.md)                                                   | contemporaneous      |
| Archive inventory                                                 | archive                              | [ARCHIVE\_INVENTORY.tsv]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/00\_ARCHIVE\_METADATA/ARCHIVE\_INVENTORY.tsv)                                                                                                                                                                                                             | archive              |
| Archive manifest/root                                             | archive                              | [ARCHIVE\_MANIFEST.sha256]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/00\_ARCHIVE\_METADATA/ARCHIVE\_MANIFEST.sha256), [ROOT\_DIGEST.txt]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/00\_ARCHIVE\_METADATA/ROOT\_DIGEST.txt)                                                 | closure              |
| v0.3 stale-builder/timing failure                                 | `134a242`                            | `/home/sagemaker-user/mineocclude-stage1-successor-134a242/collection_launch_01_20260817T195006Z/stage1_decision.json`, gates and per-trajectory timing                                                                                                                                                                                                                        | historical terminal  |
| Exact extraction implementation                                   | `020dfec`                            | [p2d\_extract.py]\(/home/sagemaker-user/MineOcclude/scripts/regime\_a\_prime\_qualification\_v0\_1/p2d\_extract.py), `Layer4Extractor.extract`                                                                                                                                                                                                                                 | source               |
| Exact readout implementation                                      | `020dfec`                            | [stage2\_backend.py]\(/home/sagemaker-user/MineOcclude/scripts/regime\_a\_prime\_qualification\_v0\_2/stage2\_backend.py), `load_scene`, `readout`, decision                                                                                                                                                                                                                   | source               |
| Environment versions                                              | `020dfec`                            | [gradle.properties]\(/home/sagemaker-user/MineOcclude/fabric/mineocclude-mod/gradle.properties), [build.gradle]\(/home/sagemaker-user/MineOcclude/fabric/mineocclude-mod/build.gradle)                                                                                                                                                                                         | source/config        |

## 99. Final Scientific Verdict

# Final Scientific Verdict for the Final Regime A′ Experiment

- Exact branch/commit: `exploration/regime-a-prime-qualification-v0-1` at `020dfecea2caad179cf7d07fc13a34d389b82c4a`.
- Design: `regime-a-prime-prospective-development-authority-v0.4`, Stage 2.
- Independent inferential units: 25 trajectories.
- Capture units: 50.
- Pairs: 25 WALL/NO\_WALL.
- Layouts: `layout_01` only.
- Directions: 13 LTR, 12 RTL.
- Stage-2 frames: 9,000.
- Scored stable-visible rows: 475 NO\_WALL.
- Scored stable-hidden rows: 475 WALL.
- FIRST\_N: 19.
- Checkpoint: SHA-256 `a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5`.
- Layer: 4.
- Representation: BEST-K training-only spatial-token selection, standardized summed-token kernel ridge; FULL secondary.
- Matched positive control: identical trajectories without the wall.
- Positive control passed: yes.
- Hidden target: direction-specific causal-FIR-aligned sheep world-x in blocks.
- Primary metric: trajectory-equal macro \\(R^2\\).
- Hidden result: `-14.703414710120608`.
- Confidence interval: `[-17.671360952005408,-12.145329030278765]`.
- Hidden RMSE: `2.109810061987133` blocks.
- Null: not tested.
- p-value: not applicable.
- Strongest tested final baseline: training-only direction/time baseline, RMSE `0.41359311896836387`.
- Beat last-seen: not tested.
- Beat constant velocity: not tested.
- Beat time-only: no in WALL RMSE.
- Beat null: not tested.
- Both directions separately support conclusion: unknown; no directional metrics archived.
- All layouts support conclusion: no; only one layout was tested, and it failed the hidden gate.
- Temporal alignment passed: yes.
- Physical visibility passed: yes.
- Runtime provenance passed: yes, including audited timestamp-only equivalence.
- Every per-unit validator passed: yes.
- Cohort validator passed: yes.
- Final physical gate passed: yes.
- Stage 2 legitimately authorized: yes, as development-only and pre-outcome.
- Final scientific gate passed: no.
- U1 established: no.
- U2 tested/established: no/no.
- Uncertainty calibrated: not tested.
- U3 tested/established: no/no.
- U4 tested/established: no/no.

Strongest paper sentence:

> In a prospectively frozen, physically qualified single-layout apparatus, MineWorld layer-4 linear readouts accurately decoded matched visible sheep position but failed decisively to decode the same trajectories during full rendered-extent occlusion.

Overstatement:

> MineWorld lacks object permanence or contains no internal representation of hidden objects.

Final classifications:

| ClassificationVerdictReason  |                           |                                                                               |
| ---------------------------- | ------------------------- | ----------------------------------------------------------------------------- |
| APPARATUS QUALIFIED          | YES                       | Stage 1 and physical gate passed                                              |
| APPARATUS NOT QUALIFIED      | NO                        | contradicted by qualification evidence                                        |
| POSITIVE CONTROL PASS        | YES                       | NO\_WALL \\(R^2=.9583\\), RMSE=.1053                                          |
| POSITIVE CONTROL FAIL        | NO                        | both NO\_WALL gates passed                                                    |
| TARGET-SPECIFICITY PASS/FAIL | NOT APPLICABLE/NOT TESTED | no final target-specific null                                                 |
| U1 ESTABLISHED               | NO                        | WALL gates failed                                                             |
| U1 NOT ESTABLISHED           | YES                       | interpretable hidden negative                                                 |
| U1 NOT INTERPRETABLE         | NO                        | apparatus and positive control passed                                         |
| U2 ESTABLISHED               | NO                        | not tested                                                                    |
| U2 NOT TESTED                | YES                       | no uncertainty analysis                                                       |
| U3 ESTABLISHED               | NO                        | not tested                                                                    |
| U3 NOT TESTED                | YES                       | no uncertainty dynamics                                                       |
| U4 ESTABLISHED               | NO                        | not tested                                                                    |
| U4 NOT TESTED                | YES                       | no intervention/behavior                                                      |
| SCIENTIFIC PASS              | NO                        | three controlling gates failed                                                |
| SCIENTIFIC FAIL              | YES                       | terminal rederived verdict                                                    |
| MEASUREMENT FAILURE          | NO                        | visible control passed strongly                                               |
| APPARATUS FAILURE            | NO                        | qualification passed                                                          |
| PROVENANCE FAILURE           | NO terminal failure       | disclosed recovery and equivalence admitted                                   |
| OPERATIONAL RECOVERY         | YES                       | multiple blockers resolved without rerunning science                          |
| DESIGN WEAKNESS              | YES                       | single layout, one layer/readout family, BGR path, no final motion/null tests |

## 100. One-Page Executive Scientific Summary

Regime A′ v0.4 Stage 2 was a development-only test of whether MineWorld layer-4 activations linearly encode the current world-x position of a sheep while the sheep is completely hidden behind a wall. It was created after original Regime A and several qualification rounds revealed that a trustworthy hidden-state test required trajectory-equal evaluation, a matched visible control, physically aligned frame labels, rendered-extent rather than centre-point visibility, synchronized builder/evaluator semantics, and strict provenance.

The final apparatus used Minecraft 1.16.5, a fixed camera and `layout_01`, a renderer-derived sheep half-extent of `0.8727621336620037` blocks, and direction-specific causal-FIR temporal labels. Stage 1 comprised eight apparatus trajectories and passed all nine gates, including zero stable-row visibility errors and successful temporal qualification in both directions.

Stage 2 used 25 prospectively seeded stochastic trajectories, each captured with and without the wall. The resulting 50 captures contained 9,000 frames. Each scene contributed 475 target rows: fully occluded WALL rows and matched stable-visible NO\_WALL rows. All captures, pairs, target windows, physical gates, extraction tensors, hashes, and durable objects validated.

The model was the frozen MineWorld `LlamaLVM` checkpoint with SHA-256 `a92c311b…`. Only decoder layer 4 was extracted. Each capture produced a `[19,336,2048]` float16 tensor. The leading BEST-K decoder used nested trajectory-grouped cross-validation and training-only token selection; FULL was secondary and could not rescue failure.

The visible positive control passed strongly: BEST-K macro \\(R^2=0.9583\\), 95% CI `[0.9434,0.9695]`, RMSE `0.1053` blocks. The hidden WALL decoder failed strongly: macro \\(R^2=-14.7034\\), CI `[-17.6714,-12.1453]`, RMSE `2.1098` blocks. It failed the WALL \\(R^2\\), RMSE, and time-baseline gates. FULL produced the same qualitative result.

No final-stage permutation null, last-seen baseline, or constant-velocity baseline was tested; no p-value exists. U2 uncertainty, U3 uncertainty dynamics, and U4 causal use were outside the design. Only one layout, one speed/noise regime, one checkpoint, one layer, and linear readouts were tested.

The final interpretation is therefore narrow but clear: the apparatus and visible measurement path worked, yet the frozen layer-4 linear decoder did not recover hidden position. This does not show that MineWorld lacks all hidden-object information or object permanence. It establishes an interpretable scientific failure of this specific hidden-position decoding configuration and leaves other layers, nonlinear representations, motion-controlled tests, uncertainty, causal use, and generalization unresolved.

```
REPOSITORY_MODIFIED_DURING_AUDIT=false
FINAL_GIT_STATUS_PORCELAIN=<empty>
```