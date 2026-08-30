# MineOcclude Experiment II — Final Scientific Consolidation

This consolidation is based on read-only inspection of the frozen authority, source, production evidence, historical Regime A′ archive, and terminal closure artifacts. No source or evidence was modified, and no experiment, inference, extraction, or regeneration was run.

## Part I — Executive Scientific Conclusion

Experiment II executed successfully and produced a genuine scientific negative within its authorized scope. The completed `r72-v4-5` pipeline passed qualification, extraction, screening, refinement, independent verification, and archival closure. It terminated at M7 because the selected hidden-position decoder failed prespecified accuracy gates—not because software, extraction, controls, or storage failed.

The strongest candidate was `L19|COARSE_2X6_CONCAT|CURRENT`: decoder layer 19, coarse 2×6 spatial pooling, and the current-frame activation. On the 25 independent occluded trajectories it achieved macro \\(R^2=-13.8263\\), RMSE \\(=2.0711\\) blocks, MAE \\(=1.9244\\), and mean improvement over baseline \\(\Delta\_A=0.3992\\) blocks. Its selection-aware randomization result was \\(p\_A=0.02\\), but it remained dramatically below the required absolute-performance standard: \\(R^2\\) and its lower confidence bound had to exceed zero, and RMSE had to be at most 0.50 blocks. It missed those thresholds by 13.8263 \\(R^2\\) units and 1.5711 blocks, respectively.

Visible decoding remained strong using the same selected layer and representation: `NO_WALL` achieved \\(R^2=0.9582\\), RMSE \\(=0.1090\\); `WALL_VISIBLE` achieved \\(R^2=0.9301\\), RMSE \\(=0.1051\\). Both control gates passed. The contrast with `WALL_HIDDEN` therefore cannot be explained simply by a broken measurement path or by the presence of a wall.

Experiment II substantially narrows the “bad layer or destructive readout” explanation left open by Regime A′. Deeper layers and coarse spatial preservation modestly improved hidden metrics, but token-selective preservation did not rescue them, and no tested decoder qualified. Temporal alternatives were not tested under the locked T-C tier, so the result does not exclude them.

The strongest defensible conclusion is: **no candidate within the prespecified, actually evaluated Experiment II family of 11 decoder-layer locations, current-frame global/coarse spatial readouts, and layer-19 BEST-K refinement satisfied the complete qualification criteria for current hidden sheep position.** This does not establish that MineWorld contains no hidden information, that all layers lack it, that nonlinear readouts would fail, or that posterior uncertainty or causal use is absent.

---

## Part II — What Experiment II Found Scientifically

The scientific objective was to determine whether the severe hidden-position decoding failure observed in Regime A′ was merely an artifact of choosing layer 4 and a spatially destructive readout. A positive result would have required a decoder that not only improved on a simple training-mean baseline, but also explained positive held-out variance, achieved RMSE no greater than 0.50 blocks, remained stable across folds, directions, and phases, passed visible controls, and survived selection-aware null testing.

The experiment searched activations from layers 0, 2, 4, 6, 8, 10, 12, 14, 16, 18, and 19. M5 compared a global average of all visual tokens with a coarse spatial representation retaining a 2×6 grid. M6 added a training-only BEST-K token-selection representation at the advancing layer. Under T-C, every evaluated representation used only the current activation; the temporal difference and two-frame alternatives in the broader authored family were not retained.

The search found a real but weak ordering signal:

- Coarse spatial pooling beat global pooling at every screened layer.
- Later layers, especially 18 and 19, were generally better than early layers.
- Layer 19 coarse pooling was the best candidate.
- Relative to the Regime A′ hidden result, its RMSE improved from 2.1098 to 2.0711 blocks—only 0.0387 blocks, or about 1.8%.
- BEST-K token preservation at layer 19 performed worse than coarse pooling: RMSE increased by 0.0742 blocks and macro \\(R^2\\) decreased by approximately 1.166.

The best candidate produced a positive mean reduction in RMSE relative to its baseline, and the bootstrap interval for that reduction was wholly positive. Its selection-aware \\(p\_A=0.02\\) also passed. But these facts do not imply useful prediction: macro \\(R^2=-13.8263\\) means that, under the identity-macro scoring protocol, the decoder generalized much worse than the relevant mean predictor. Its 2.0711-block RMSE was 4.14 times the permitted ceiling.

The randomization analysis further tempers the positive \\(\Delta\_A\\). Across 49 full-funnel null reruns, the mean null statistic was 0.38457, compared with 0.39917 observed; the largest null value was 0.39896. Thus the observed statistic exceeded every sampled null, but only by 0.000207 over the maximum, and the null mean reproduced about 96.34% of the observed statistic. This is statistically separated at the available Monte Carlo resolution, yet scientifically weak in absolute predictive terms.

The visible controls give the negative result its main interpretive value. When the sheep was visible, the same selected activation/readout supported approximately 0.1-block error and \\(R^2\\) near 0.93–0.96. When fully occluded, error rose to 2.07 blocks and \\(R^2\\) became strongly negative. This supports an occlusion-associated loss of qualified linear accessibility, not a generic inability to encode position, not a wall-domain failure, and not a broken extraction or decoding apparatus.

Scientifically, the pipeline did not fail. It successfully reached the intended decision point and found that the authorized hidden-position candidates did not meet the qualification standard.

---

## Part III — Canonical Run Identity and Provenance

| FieldCanonical value              |                                                                    |
| --------------------------------- | ------------------------------------------------------------------ |
| Run namespace                     | `r72-v4-5`                                                         |
| Run UUID                          | `236003f9-144d-4451-9719-0ecd3a919bca`                             |
| Authority                         | v3.7.11                                                            |
| Authority SHA-256                 | `1992dc507fb3a9083fb376e31cc65cdcb0a74f196b12d671ee9ccd23f600d68d` |
| Freeze commit                     | `6db5b00afe8098fe21398b2d094705e771aaa0b6`                         |
| Source-closure digest             | `dd07298a1f77a1d9e7ba8965c568b14830d59d1e1f656149fbf208118d36d803` |
| M2 state                          | `M2_COMPLETE`                                                      |
| Locked tier                       | `T-C`                                                              |
| Whole locked-plan digest          | `ac0663747c082825ea9e4f1eed26bbe1d93602eaa4fdeebe62c1bcb5f7a1fa35` |
| Scientific-plan projection digest | `f43bac09e376710c33d9681dd7d078851ddfb064a2878fb71edf456245013d8c` |
| Evidence-seal root                | `92fff388e60de50a0ae3e529d9c042fc579b732182c3517f73f9b0c6d055a94c` |
| Terminal state                    | `NO_CANDIDATE_IN_AUTHORIZED_FAMILY`                                |
| Closure class                     | `SCIENCE`                                                          |
| Blocking stage                    | `M7`                                                               |
| Archive pass                      | `true`                                                             |
| Total elapsed time                | approximately 8.965 hours                                          |

Primary records:

- [v3.7.11 authority]\(/home/sagemaker-user/mineocclude-authorities/MineOcclude\_Continuation\_Experiment\_II\_Rapid\_72H\_Terminal\_Execution\_Authority\_v3.7.11.md)
- [M2 freeze record]\(/home/sagemaker-user/mineocclude-experiment-ii-r72-v4-5/evidence/m2/producer/M2\_IMPLEMENTATION\_LOCK\_AND\_SOURCE\_FREEZE.json)
- [R5 tier lock]\(/home/sagemaker-user/mineocclude-experiment-ii-r72-v4-5/evidence/r-5/producer/R5\_FINAL\_COMPUTE\_TIER\_LOCK.json)
- [Z4 canonical closure]\(/home/sagemaker-user/mineocclude-experiment-ii-r72-v4-5/evidence/z-4/Z4\_FINAL\_CLOSURE\_RECEIPT.json)

The M2 verifier independently rederived 91 frozen files, 1,318 definitions, and the exact source-closure digest. Its discrepancy list was empty.

---

## Part IV — Scientific Motivation From Regime A-prime

The canonical Regime A′ Stage-2 decision reported:

| Population/readoutMacro \\(R^2\\)RMSE, blocksBootstrap 95% \\(R^2\\) |             |           |                            |
| -------------------------------------------------------------------- | ----------- | --------- | -------------------------- |
| BEST-K `NO_WALL`                                                     | 0.9582681   | 0.1053344 | [0.9433884, 0.9695287]     |
| BEST-K `WALL` hidden                                                 | -14.7034147 | 2.1098101 | [-17.6713610, -12.1453290] |
| Full `NO_WALL`                                                       | 0.9505321   | 0.1118388 | [0.9321598, 0.9661492]     |
| Full `WALL` hidden                                                   | -14.6427002 | 2.1069310 | [-17.5943482, -12.1116162] |

Source: [Regime A′ Stage-2 decision]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/04\_SCIENTIFIC\_RESULTS/stage2\_decision.json).

That result established a strong visible/hidden contrast at the tested layer/readout, but it was classified `DEVELOPMENT_ONLY`. It could not exclude:

- hidden information emerging above or below layer 4;
- positional information being destroyed by global token aggregation;
- information distributed spatially across tokens;
- a small subset of informative tokens;
- information present only in temporal changes or multi-frame structure;
- selection artifacts from searching candidates without a full selection-aware null.

Experiment II was needed because failure of one layer/readout is not evidence of failure throughout a representation hierarchy. It separated candidate discovery from final qualification, froze the search and decision rules, grouped all splits by independent trajectory, restricted token selection to training data, and permitted exactly one finalist—or no candidate—to advance.

---

## Part V — Experimental Design

The primary estimand was current, direction-specific, causal-FIR-aligned sheep world-\\(x\\), in blocks, during complete occlusion. Experiment II principally addressed scientific ladder Level 1: whether current hidden position was linearly decodable.

Candidate discovery used only `WALL_HIDDEN` outcomes. Controls did not enter M5 ranking. The sequence was:

1. Qualify the apparatus, numerical implementation, and compute tier through R1–R5.
2. Extract a frozen activation corpus at M4.
3. Screen layer × compact-representation cells at M5.
4. Advance the authorized layer and evaluate refinements at M6.
5. Select one finalist through the frozen funnel.
6. Run bootstrap, controls, and a selection-aware full-funnel null at M7.
7. Lock a development candidate only if all nine Claim-A gates passed.

The design was capable of producing a meaningful negative because failure at M7 meant failure of prespecified scientific predicates after successful extraction and valid controls—not absence of an executable pipeline.

### Canonical evidence matrix

| StageRolePopulation / NLayers / representationResultMeaningArtifact |                           |                         |                                               |                              |                                   |                                                                                                                              |
| ------------------------------------------------------------------- | ------------------------- | ----------------------- | --------------------------------------------- | ---------------------------- | --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| R1                                                                  | Engineering qualification | Synthetic               | 20 layers, grouped hooks                      | PASS                         | Grouped hooks bit-exact           | [R1]\(/home/sagemaker-user/mineocclude-experiment-ii-r72-v4-5/evidence/r-1/producer/R1\_GROUPED\_HOOK\_EQUIVALENCE.json)     |
| R2                                                                  | Resource qualification    | Benchmark               | Tier projections                              | PASS                         | Extraction feasible               | [R2]\(/home/sagemaker-user/mineocclude-experiment-ii-r72-v4-5/evidence/r-2/producer/R2\_FORWARD\_LATENCY\_BENCHMARK.json)    |
| R3                                                                  | Numerical qualification   | Fixtures                | Ridge, BEST-K, PCA, bootstrap/null arithmetic | PASS                         | Numerical primitives conformed    | [R3]\(/home/sagemaker-user/mineocclude-experiment-ii-r72-v4-5/evidence/r-3/producer/R3\_NUMERICAL\_FIXTURE\_LEDGER.json)     |
| R4                                                                  | Tier qualification        | Synthetic funnels       | T-A/T-B/T-C                                   | PASS                         | T-C first feasible tier           | [R4]\(/home/sagemaker-user/mineocclude-experiment-ii-r72-v4-5/evidence/r-4/producer/R4\_PER\_TIER\_FUNNEL\_CONFORMANCE.json) |
| R5                                                                  | Blind tier lock           | No science outcomes     | T-C                                           | PASS                         | Scientific search frozen          | [R5]\(/home/sagemaker-user/mineocclude-experiment-ii-r72-v4-5/evidence/r-5/producer/R5\_FINAL\_COMPUTE\_TIER\_LOCK.json)     |
| M4                                                                  | Real extraction           | 1,796 rows              | 11 layers                                     | PASS                         | Complete verified corpus          | [M4]\(/home/sagemaker-user/mineocclude-experiment-ii-r72-v4-5/evidence/m4/producer/M4\_EXTRACTION\_INTEGRITY\_MANIFEST.json) |
| M5                                                                  | Development screen        | Hidden, N=25, 475 rows  | 11 layers × 2 reps                            | PASS; 22 cells, L19 advances | Candidate discovery               |                                                                                                                              |
| M6                                                                  | Development refinement    | Hidden, N=25            | L19 × 3 reps                                  | PASS                         | Coarse remains best               |                                                                                                                              |
| M7                                                                  | Prospective qualification | Hidden + controls, N=25 | One selected finalist; 3-cell funnel          | FAIL scientifically          | Zero qualifying candidates        |                                                                                                                              |
| M8                                                                  | Terminal refit            | —                       | —                                             | Not entered                  | Required a locked M7 candidate    |                                                                                                                              |
| H-0                                                                 | Holdout route             | —                       | —                                             | Not entered                  | Required terminal model objects   |                                                                                                                              |
| V1                                                                  | Independent verification  | Frozen evidence         | 14 rows                                       | PASS                         | 10 applicable exact, 0 mismatches |                                                                                                                              |
| Z1                                                                  | Evidence seal             | 19,917 pre-Z1 objects   | —                                             | PASS                         | Seal constructed                  |                                                                                                                              |
| Z2                                                                  | Durable readback          | 19,918 objects          | Contract A                                    | PASS                         | Archive readable                  |                                                                                                                              |
| Z3                                                                  | Terminal release          | —                       | Form Z-3S                                     | PASS                         | Scoped nonclaim issued            |                                                                                                                              |
| Z4                                                                  | Canonical closure         | —                       | —                                             | PASS                         | Science closure complete          |                                                                                                                              |

M5–M7 sources: [M5]\(/home/sagemaker-user/mineocclude-experiment-ii-r72-v4-5/evidence/m5/producer/M5\_SCREEN\_AND\_ADVANCEMENT.json), [M6]\(/home/sagemaker-user/mineocclude-experiment-ii-r72-v4-5/evidence/m6/producer/M6\_REFINEMENT.json), and [M7]\(/home/sagemaker-user/mineocclude-experiment-ii-r72-v4-5/evidence/m7/producer/M7\_NULL\_BOOTSTRAP\_CONTROLS\_DECISION.json).

---

## Part VI — Visibility / Occlusion Conditions

| ConditionWall?Sheep visible?TargetRoleStages |     |                             |                                  |                                                                                    |                                        |
| -------------------------------------------- | --- | --------------------------- | -------------------------------- | ---------------------------------------------------------------------------------- | -------------------------------------- |
| `NO_WALL`                                    | No  | Yes                         | Current true sheep world-\\(x\\) | Ordinary visible positive control; validates measurement path                      | Extracted M4; formally gated M7        |
| `WALL_VISIBLE`                               | Yes | Yes, outside full occlusion | Current true sheep world-\\(x\\) | Same-wall/domain visible control; tests whether wall-domain shift explains failure | Extracted M4; formally gated M7        |
| `WALL_HIDDEN`                                | Yes | No, fully occluded          | Current true sheep world-\\(x\\) | Primary hidden-state test                                                          | M5 ranking, M6 refinement, M7 decision |

The controls were fitted with the selected hidden candidate’s layer, representation, folds, and readout rules. They did not influence hidden candidate ranking.

The conceptual interpretation is therefore supported: `NO_WALL` tests ordinary visible recovery; `WALL_VISIBLE` tests visible recovery in the wall domain; `WALL_HIDDEN` tests hidden current-position accessibility.

---

## Part VII — Dataset and Independent Sample Structure

- Independent sample size: **25 trajectory identities**, never 475, 846, 950, or 1,796 frames.
- Direction balance: 13 left-to-right and 12 right-to-left.
- Layouts: one, `layout_01`.
- Speed: 2.0.
- Historical captures: 25 paired `WALL`/`NO_WALL` trajectories = 50 captures.
- Frames per capture: 180.
- Regime A′ scored rows: 950, consisting of 475 hidden and 475 visible/no-wall rows.
- Experiment II row universes:
  - `WALL_HIDDEN`: 475 rows, 19 per identity.
  - `NO_WALL`: 475 rows, 19 per identity.
  - `WALL_VISIBLE`: 846 rows.
  - Total M4 inference rows: 1,796.
- Stratification: direction × phase, with phases 0, 3, 6, 9, 12; ten strata, five of size 3 and five of size 2.
- Cross-validation: five outer folds, each containing five complete identities; four inner rotations within each outer training set.
- Grouping unit: trajectory identity. Frames from one identity could not be split across train/test partitions.

```
NEW_MINECRAFT_CAPTURE=false
RAW_CAPTURE_REUSE=true
NEW_MODEL_INFERENCE=true
```

Dataset source: [S3 roster and target ledger]\(/home/sagemaker-user/mineocclude-experiment-ii-r72-v4-5/evidence/s-3/producer/S3\_D0\_ROSTER\_TARGET\_BASELINE\_LEDGER.json).

---

## Part VIII — Activation Extraction

| PropertyValue             |                                                                    |
| ------------------------- | ------------------------------------------------------------------ |
| Model family              | MineWorld `700M_16f`                                               |
| Main checkpoint SHA-256   | `a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5` |
| VAE SHA-256               | `370d06be427e034476b6b95ba0080a4b48266e876c4776a757b944b87b87d9ab` |
| MineWorld source revision | `9f49ef…`                                                          |
| Decoder layers            | 20, `LlamaModel.layers[0..19]`                                     |
| Hidden width              | 2,048                                                              |
| Context                   | 16 frame/action pairs                                              |
| Tokens per pair           | 336 visual + 11 action = 347                                       |
| Full sequence length      | 5,552                                                              |
| Target pair               | ordinal 15                                                         |
| Target visual slice       | sequence positions 5,205–5,540                                     |
| Visual grid               | 14×24 = 336 tokens                                                 |
| Hook semantics            | Layer-edge output after complete teacher-forced context            |
| Realized dtype            | little-endian float16, `<f2`                                       |
| T-C extracted layers      | 0,2,4,6,8,10,12,14,16,18,19                                        |
| Forward count             | 1,796                                                              |
| Tensor count              | \\(1,796\times11=19,756\\)                                         |
| Tensor shape              | [336, 2,048]                                                       |
| Bytes/tensor              | \\(336\times2,048\times2=1,376,256\\)                              |
| Total bytes               | 27,189,313,536 = approximately 25.32 GiB                           |

An individual tensor is the 336-token visual activation grid at one selected decoder layer for one target row under its complete 16-pair teacher-forced context. It is not a fitted prediction and does not by itself demonstrate decodability.

Model identity source: [S1 identity record]\(/home/sagemaker-user/mineocclude-experiment-ii-r72-v4-5/evidence/s-1/producer/S1\_SOURCE\_ENVIRONMENT\_MODEL\_IDENTITY.json).

---

## Part IX — Representation Family

| RepresentationTransformationDimensionToken identitySpatial structureTemporal structure |                                                                                                                                                                        |               |                         |                          |              |
| -------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------- | ----------------------- | ------------------------ | ------------ |
| `GLOBAL_MEAN`                                                                          | Mean of all 336 token vectors                                                                                                                                          | 2,048         | No                      | No                       | Current only |
| `COARSE_2X6_CONCAT`                                                                    | Divide 14×24 grid into 2 row bands × 6 column bands; average each 7×4 cell and concatenate                                                                             | 24,576        | No within cell          | Coarse 2×6 layout        | Current only |
| `BEST_K_CONCAT`                                                                        | Within each training fold, rank tokens by maximum absolute feature–target Pearson association; select K∈{1,4,16,64}; concatenate selected token vectors in token order | Up to 131,072 | Yes for selected tokens | Token positions retained | Current only |

`GLOBAL_MEAN` tests whether position is accessible from a fully collapsed state summary. `COARSE_2X6_CONCAT` addresses destruction of coarse spatial information. `BEST_K_CONCAT` addresses sparse token localization while keeping selection inside the training fold.

The broader authored family also contained `WALL_BAND_ROI_CONCAT`, `PCA_FULL_GRID`, `FULL_TOKEN_GRID`, `CURRENT_MINUS_PREVIOUS`, and `TWO_FRAME_CONCAT`. They were not authorized for actual evaluation under T-C. Their absence must not be reinterpreted as failure.

---

## Part X — Probe and Statistical Methodology

The probe was linear ridge regression with:

- training-set feature standardization;
- an unpenalized intercept;
- alpha grid \\(\\{0.1,1,10,100,1000\\}\\);
- primal or dual solution depending on dimensionality; the high-dimensional evaluated cells generally used the dual;
- five identity-grouped outer folds;
- four inner rotations for hyperparameter selection;
- training-only scaling, alpha selection, token ranking, and K selection.

Candidate outcomes were computed only on held-out identities. Candidate selection used hidden-population outcomes, not visible-control performance. The final selected candidate was chosen by the frozen full funnel and anchor-band rule; runner-up substitution was forbidden.

Metrics were macro-averaged over identities:

- \\(R^2\_i=1-\mathrm{SSE}\_i/\mathrm{SST}\_i\\), then mean over identities.
- RMSE and MAE were first computed per identity and then averaged.
- Bias was the corresponding macro mean residual.
- \\(\Delta\_{A,i}=\mathrm{RMSE}\_{B0,i}-\mathrm{RMSE}\_{probe,i}\\).
- \\(T\_A\\) was the selected funnel’s maximum mean \\(\Delta\_A\\).
- \\(T\_D\\) was the incremental design-comparator statistic; here it was 0.
- \\(p\_A=(1+\\#\\{T\_A^{null}\ge T\_A^{obs}\\})/(B+1)\\), with \\(B=49\\).

Pearson and Spearman correlations were not reported as evaluation metrics. BEST-K used Pearson association internally for training-only token ranking; that is not a held-out predictive correlation and must not be reported as one.

---

## Part XI — R1-R5 Qualification Funnel

| StageQuestionResultPass basisNext |                                                               |      |                                                                                                                |    |
| --------------------------------- | ------------------------------------------------------------- | ---- | -------------------------------------------------------------------------------------------------------------- | -- |
| R1                                | Are grouped hooks equivalent to reference single-layer hooks? | PASS | 1,280 compared tensors; maximum absolute difference 0; shape/dtype exact                                       | R2 |
| R2                                | Is extraction feasible?                                       | PASS | Projected 1,796 forwards and approximately 1,246 extraction seconds; all tiers feasible for extraction/storage | R3 |
| R3                                | Are statistical primitives numerically conformant?            | PASS | Ridge, BEST-K, PCA, metrics, bootstrap, and null fixtures matched                                              | R4 |
| R4                                | Which tier can execute the full selection-aware funnel?       | PASS | T-A and T-B exceeded the 260-second null-feasibility ceiling; T-C completed its funnel in 140 seconds          | R5 |
| R5                                | Which tier is locked without scientific outcomes?             | PASS | T-C was the first feasible tier in fixed order T-A→T-B→T-C                                                     | M4 |

T-C locked:

- 11 screened layers;
- `GLOBAL_MEAN` and `COARSE_2X6_CONCAT` at M5;
- one advancing layer;
- refinement by global, coarse, and BEST-K;
- current-frame activations only;
- 49 null replicates.

Claims lost at the tier lock were `H4_UNTESTED` and `H5_UNTESTED`. The lock retained partial tests of H1/H7 and tests H2, H3, H6, and H8.

T-C was expected but not forced. R4 and R5 did not read the expected tier. The scientific-plan projection excludes five runtime measurements—funnel, extraction, null, verification, and archive timings—and retains 24 scientific/capacity fields. Thus host timing changes can affect feasibility without contaminating the scientific-plan identity.

---

## Part XII — M4 Extraction

```
M4_PRODUCER_STATUS=PASS
M4_VERIFIER_STATUS=PASS
M4_PASS=true
SCIENTIFIC_OUTCOMES_OPEN=true
TENSOR_COUNT=19,756
LAYER_COUNT=11
TENSOR_SHAPE=[336,2048]
DTYPE=<f2
TOTAL_BYTES=27,189,313,536
INTEGRITY_STATUS=COMPLETE
```

M4 performed 1,796 new MineWorld forwards and published all expected tensors. The verifier independently reproduced the 1,796-unit inventory, checked 19,756 objects, and reported no discrepancies.

M4 established that the intended model, rows, hooks, layer locations, tensor shapes, dtype, and object corpus were correctly realized. It did not establish successful hidden decoding.

This differs from v4.3: v4.3 produced a complete corpus, but its shared verifier publication call attempted to hash a directory root as though it were a file and could not publish the stage-verifier artifact. In v4.5 both producer and verifier completed.

Sources: [M4 producer]\(/home/sagemaker-user/mineocclude-experiment-ii-r72-v4-5/evidence/m4/producer/M4\_EXTRACTION\_INTEGRITY\_MANIFEST.json) and [M4 verifier]\(/home/sagemaker-user/mineocclude-experiment-ii-r72-v4-5/evidence/m4/verifier/M4\_INDEPENDENT\_VERIFICATION.json).

---

## Part XIII — M5 Candidate Screening

M5 evaluated 22 development cells: 11 layers × 2 representations × `CURRENT`. Exactly one layer, L19, advanced.

### Complete M5 hidden ranking

| RankCandidate\\(\Delta\_A\\)Macro \\(R^2\\)RMSEMAE |            |         |           |         |         |
| -------------------------------------------------- | ---------- | ------- | --------- | ------- | ------- |
| 1                                                  | L19 coarse | 0.39917 | -13.82629 | 2.07114 | 1.92440 |
| 2                                                  | L18 coarse | 0.38893 | -13.96234 | 2.08138 | 1.93101 |
| 3                                                  | L10 coarse | 0.38725 | -13.99467 | 2.08306 | 1.94263 |
| 4                                                  | L16 coarse | 0.38543 | -14.01057 | 2.08488 | 1.94505 |
| 5                                                  | L12 coarse | 0.38134 | -14.06280 | 2.08897 | 1.95096 |
| 6                                                  | L19 global | 0.38033 | -14.06582 | 2.08998 | 1.94450 |
| 7                                                  | L18 global | 0.37887 | -14.11266 | 2.09144 | 1.95940 |
| 8                                                  | L14 coarse | 0.37780 | -14.11412 | 2.09251 | 1.95672 |
| 9                                                  | L16 global | 0.36516 | -14.28780 | 2.10515 | 1.96912 |
| 10                                                 | L04 coarse | 0.36300 | -14.32354 | 2.10731 | 1.96793 |
| 11                                                 | L08 coarse | 0.35977 | -14.39747 | 2.11054 | 1.98166 |
| 12                                                 | L12 global | 0.35631 | -14.46795 | 2.11400 | 1.98065 |
| 13                                                 | L04 global | 0.35407 | -14.46758 | 2.11625 | 1.98363 |
| 14                                                 | L14 global | 0.35242 | -14.46087 | 2.11789 | 1.98679 |
| 15                                                 | L06 coarse | 0.34876 | -14.50657 | 2.12155 | 1.98575 |
| 16                                                 | L10 global | 0.34714 | -14.59791 | 2.12318 | 1.99267 |
| 17                                                 | L00 coarse | 0.33354 | -14.81765 | 2.13678 | 1.99833 |
| 18                                                 | L08 global | 0.33025 | -14.82354 | 2.14006 | 2.00359 |
| 19                                                 | L02 coarse | 0.31615 | -15.23987 | 2.15416 | 2.00488 |
| 20                                                 | L00 global | 0.31456 | -15.03357 | 2.15575 | 2.02730 |
| 21                                                 | L06 global | 0.30966 | -15.09943 | 2.16065 | 2.03459 |
| 22                                                 | L02 global | 0.28762 | -15.64227 | 2.18269 | 2.05500 |

All 22 cells had positive mean \\(\Delta\_A\\), but all had strongly negative macro \\(R^2\\) and RMSE above 2 blocks. Coarse pooling outperformed global pooling at every tested layer, providing consistent developmental evidence that coarse spatial organization carried some useful signal. It did not approach qualification.

M5 was a selection stage, not a confirmatory result. Its `hidden_support=true` field is a development/advancement indicator, not evidence that Claim A passed.

---

## Part XIV — M6 Candidate Refinement

| L19 representation\\(\Delta\_A\\)Macro \\(R^2\\)RMSEMAESelected alpha / K |         |           |         |         |                               |
| ------------------------------------------------------------------------- | ------- | --------- | ------- | ------- | ----------------------------- |
| Coarse 2×6                                                                | 0.39917 | -13.82629 | 2.07114 | 1.92440 | α=1000 in all folds           |
| Global mean                                                               | 0.38033 | -14.06582 | 2.08998 | 1.94450 | α=100/1000                    |
| BEST-K                                                                    | 0.32496 | -14.99216 | 2.14535 | 1.99960 | K=[16,64,1,16,64], modal K=16 |

The M5 coarse and global values were reproduced identically in M6. BEST-K did not improve signal, generalization, or stability. Relative to coarse pooling it:

- reduced \\(\Delta\_A\\) by 0.07420 blocks;
- increased RMSE by 0.07420 blocks;
- reduced macro \\(R^2\\) by about 1.166;
- used unstable fold-specific K choices.

```
BEST_M5_CANDIDATE=L19|COARSE_2X6_CONCAT|CURRENT
BEST_M6_CANDIDATE=L19|COARSE_2X6_CONCAT|CURRENT
M6_IMPROVED_SIGNAL=false
M6_IMPROVED_GENERALIZATION=false
M6_IMPROVED_STABILITY=false
```

No temporal refinement occurred because T-C retained only `CURRENT`.

---

## Part XV — M7 Terminal Scientific Decision

M7’s artifact has `status=FAIL` and `verdict=false`, but this is the intended encoding of a failed scientific qualification.

```
M7_PASS=false
TERMINAL_STATE=NO_CANDIDATE_IN_AUTHORIZED_FAMILY
SCIENTIFIC_OUTCOMES_OPEN=true
AUTHORIZES=null
CONTROLS_PASS=true
RUNNER_UP_SUBSTITUTION=false
```

The three M6 cells formed the evaluated funnel. The frozen selector chose exactly one finalist—L19 coarse current—for formal gating. Zero candidates passed.

### M7 gate ledger

| GateRequirementObservedMarginResult |                                                           |                            |                              |          |
| ----------------------------------- | --------------------------------------------------------- | -------------------------- | ---------------------------- | -------- |
| G1                                  | Provenance/implementation/cohort/target/leakage valid     | Recorded true              | —                            | PASS     |
| G2                                  | Mean \\(\Delta\_A>0\\) and bootstrap lower bound \\(>0\\) | 0.39917; lower 0.34850     | +0.39917; +0.34850           | PASS     |
| G3                                  | Macro \\(R^2>0\\) and lower bound \\(>0\\)                | -13.82629; lower -15.48063 | -13.82629; -15.48063         | **FAIL** |
| G4                                  | Macro RMSE ≤0.50                                          | 2.07114                    | +1.57114 blocks over ceiling | **FAIL** |
| G5                                  | ≥4/5 fold means >0; all >-0.10                            | 5/5; minimum 0.35533       | Pass                         | PASS     |
| G6                                  | Both direction means >0                                   | 0.37864, 0.42141           | minimum +0.37864             | PASS     |
| G7                                  | ≥4/5 phase means ≥0; all >-0.10                           | 4/5; minimum -0.00659      | above floor                  | PASS     |
| G8                                  | Both D0 control gates pass                                | Both pass                  | —                            | PASS     |
| G9                                  | \\(p\_A\le0.05\\)                                         | 0.02                       | 0.03 below threshold         | PASS     |

G3 was the first decisive failure; G4 independently failed. Descriptively applying their arithmetic to all 25 distinct development/refinement cells gives the same broad conclusion: none had positive macro \\(R^2\\), and none approached 0.50-block RMSE. Formally, however, M7 gated only the selected candidate.

The finalist’s fold \\(\Delta\_A\\) means were 0.38572, 0.42825, 0.44047, 0.38606, and 0.35533. Direction means were 0.37864 and 0.42141. Phase means were 1.04799, 0.64187, 0.30272, -0.00659, and 0.00985 for phases 0, 3, 6, 9, and 12.

Classification: **WEAK\_SUBTHRESHOLD\_SIGNAL**, not a near miss. It passed effect-direction, stability, control, and sampled-null gates but missed the principal absolute-accuracy requirements by very large margins.

---

## Part XVI — Why M8 / H-0 Were Not Entered

M8 required the M7 state `DEVELOPMENT_CANDIDATE_LOCKED`. M7 instead emitted `NO_CANDIDATE_IN_AUTHORIZED_FAMILY`; therefore no terminal D0 model could be refitted.

H-0 required the terminal model objects and the corresponding locked state. Because M8 did not exist, H-0’s preconditions were false.

```
M8_EXPECTED_AFTER_NO_CANDIDATE=false
H0_EXPECTED_AFTER_NO_CANDIDATE=false
```

Their absence is correct state-machine routing, not incomplete execution.

---

## Part XVII — V1 Independent Verification

```
V1_STATUS=PASS
V1_VERDICT=PASS
V1_TERMINAL_STATE=NO_CANDIDATE_IN_AUTHORIZED_FAMILY
V1_DISCREPANCIES=[]
```

V1 contained 14 verification rows:

- 10 applicable rows were exact;
- 4 were marked not applicable;
- 0 applicable rows mismatched.

It independently rederived authority identity, source/environment closure, model identity, 25 distinct realized paths, FIR targets, design-matrix digest, tensor integrity through the M4 verifier, feature samples, grouped folds/leakage properties, M5 screening, and M6 refinement.

The v4.3 realized/design-path confusion was corrected: v4.5 IV-4 reconstructed the noise-seed-driven realized path; IV-5 applied the causal FIR to that path while retaining the no-noise design path only for design covariates. It also used the producer’s canonical JCS digest over both design rows and anchor.

Important limitation: V1 did **not** rederive the M7 null, bootstrap, controls, or final gate arithmetic. IV-11–IV-13 were marked not applicable, including the inaccurate reason that M7 produced no artifact. The terminal negative’s decisive quantities nevertheless trace back to the M5/M6 cell rederived under IV-9/IV-10. V1 therefore verifies the governed applicable matrix and the decisive candidate metrics, but not every M7 operation independently.

Source: [V1 bundle]\(/home/sagemaker-user/mineocclude-experiment-ii-r72-v4-5/evidence/v-1/V1\_INDEPENDENT\_VERIFICATION\_BUNDLE.json).

---

## Part XVIII — Z1-Z4 Canonical Closure

- **Z1:** PASS. Constructed the per-object evidence seal over 19,917 pre-Z1 entries; including the Z1 manifest yielded 19,918 sealed objects.
- **Z2:** PASS under `CONTRACT_A`. Durable readback and receipt upload succeeded; no durability failure.
- **Z3:** PASS. Issued scientific terminal form `Z-3S`, recorded `HOLDOUT_NOT_RUN`, and limited the claim to the tested apparatus.
- **Z4:** PASS. Canonically recorded `M2_COMPLETE`, `SCIENCE`, blocking stage M7, `NO_CANDIDATE_IN_AUTHORIZED_FAMILY`, V1 PASS, and archive PASS.

Sources: [Z1]\(/home/sagemaker-user/mineocclude-experiment-ii-r72-v4-5/evidence/z-1/Z1\_EVIDENCE\_SEAL.json), [Z3 release]\(/home/sagemaker-user/mineocclude-experiment-ii-r72-v4-5/evidence/z-3/EXPERIMENT\_II\_TERMINAL\_RELEASE.json), and [Z4]\(/home/sagemaker-user/mineocclude-experiment-ii-r72-v4-5/evidence/z-4/Z4\_FINAL\_CLOSURE\_RECEIPT.json).

The detached supervisor retained `TERMINAL_STATE=EXPERIMENT_II_BLOCKED`, reflecting its generic process-level handling of a failing stage exit. Its same state document correctly selected `CLOSURE_CLASS=SCIENCE`, executed V1→Z1→Z2→Z3→Z4, and ended `CLOSED`. For scientific reporting, the governed Z4 terminal state is authoritative.

---

## Part XIX — Visibility vs Occlusion Scientific Analysis

| PopulationNRowsLayer/representationMacro \\(R^2\\)RMSEMAEMean \\(\Delta\_A\\)Bootstrap lower \\(R^2\\)Status |    |     |                    |           |         |         |         |           |              |
| ------------------------------------------------------------------------------------------------------------ | -- | --- | ------------------ | --------- | ------- | ------- | ------- | --------- | ------------ |
| `NO_WALL`                                                                                                    | 25 | 475 | L19 coarse/current | 0.95822   | 0.10899 | 0.08961 | 2.36132 | 0.94998   | Control PASS |
| `WALL_VISIBLE`                                                                                               | 25 | 846 | L19 coarse/current | 0.93015   | 0.10513 | 0.07790 | 7.63236 | 0.87523   | Control PASS |
| `WALL_HIDDEN`                                                                                                | 25 | 475 | L19 coarse/current | -13.82629 | 2.07114 | 1.92440 | 0.39917 | -15.48063 | Claim-A FAIL |

No held-out Pearson or Spearman correlations were computed.

The same measurement path worked when the target was visible, both without a wall and in the wall domain. Hidden failure was therefore specifically associated with full occlusion in this apparatus. Generic wall-domain shift alone is insufficient because `WALL_VISIBLE` remained strong.

The paired `NO_WALL` and `WALL_HIDDEN` universes share a macro B0 RMSE of approximately 2.47031. `WALL_VISIBLE` has a different row/target universe and a macro baseline of approximately 7.73749; its much larger \\(\Delta\_A\\) is not directly comparable as an effect magnitude.

---

## Part XX — Comparison With Regime A-prime

| QuestionRegime A′Experiment IIInterpretation |                                                                             |                                                             |                                                                  |
| -------------------------------------------- | --------------------------------------------------------------------------- | ----------------------------------------------------------- | ---------------------------------------------------------------- |
| Hidden layer coverage                        | Layer 4                                                                     | 11 real extracted layers                                    | Negative substantially broadened in depth, but not all 20 layers |
| Readout                                      | Historical BEST-K/full and authority-described collapsed layer-4 continuity | Global, coarse 2×6; L19 BEST-K                              | More structured family                                           |
| Best hidden \\(R^2\\)                        | -14.70341 for leading BEST-K                                                | -13.82629                                                   | Improvement 0.87712, still strongly negative                     |
| Best hidden RMSE                             | 2.10981                                                                     | 2.07114                                                     | Improvement 0.03867 blocks, 1.83%                                |
| Visible result                               | 0.95827 / 0.10533                                                           | 0.95822 / 0.10899 `NO_WALL`; 0.93015 / 0.10513 wall-visible | Visible measurement reproduced strongly                          |
| Selection-aware null                         | Not equivalent                                                              | Full-funnel B=49                                            | Stronger selection control                                       |
| Candidate qualified?                         | No, development-only failure                                                | No, prospective M7 failure                                  | Experiment II is the stronger bounded negative                   |
| Temporal alternatives                        | Not established                                                             | Not retained under T-C                                      | Still unresolved                                                 |

```
DID_ANOTHER_LAYER_HELP=YES, MODESTLY, BUT DID NOT QUALIFY
DID_TOKEN_PRESERVATION_HELP=NO AT L19
DID_SPATIAL_PRESERVATION_HELP=YES DEVELOPMENTALLY, NOT ENOUGH TO QUALIFY
DID_TEMPORAL_REFINEMENT_HELP=NOT TESTED
DID_ANY_CONFIGURATION_MATERIALLY_IMPROVE_HIDDEN_DECODING=NO
DID_ANY_CONFIGURATION_QUALIFY=NO
ORIGINAL_LAYER4_FAILURE_EXPLAINED_BY_READOUT_CHOICE=NO
```

The Experiment II best candidate improved slightly over the historical layer-4 result, but not remotely enough to turn it into useful or qualified prediction.

---

## Part XXI — Baseline / Null / Control Framework

### B0 baseline

B0 was the outer-training mean predictor. Because it was recomputed within each outer fold, \\(\Delta\_A\\) measured held-out RMSE reduction relative to information available without the activation features.

The selected hidden decoder’s positive \\(\Delta\_A\\) coexisted with strongly negative identity-macro \\(R^2\\). These metrics answer different aggregation questions; neither should be silently substituted for the other.

### Bootstrap

The identity-level bootstrap gave:

- hidden \\(\Delta\_A\\) interval: [0.34850, 0.45368];
- hidden macro \\(R^2\\) lower bound: -15.48063;
- `NO_WALL` lower \\(\Delta\_A\\): 2.29013;
- `NO_WALL` lower macro \\(R^2\\): 0.94998;
- `WALL_VISIBLE` lower \\(\Delta\_A\\): 7.54285;
- `WALL_VISIBLE` lower macro \\(R^2\\): 0.87523.

### Selection-aware null

The null reference group was \\(S\_3^5\times S\_2^5\\), order 248,832. The mapping permuted hidden activation blocks only within direction×phase strata; targets, folds, baselines, \\(\tau\\), and controls remained fixed. Every null draw reran the complete selection funnel, making the test selection-aware.

Sampling was i.i.d. uniform with replacement. Identity and repeated transformations were legal; no duplicate mapping IDs occurred.

| Null quantityValue      |           |
| ----------------------- | --------- |
| B                       | 49        |
| Observed \\(T\_A\\)     | 0.3991669 |
| Null mean               | 0.3845741 |
| Null sample SD          | 0.0149564 |
| Null minimum            | 0.3451834 |
| Null maximum            | 0.3989598 |
| Exceedances             | 0         |
| \\(p\_A\\)              | 0.02      |
| \\(T\_D\\) / \\(p\_D\\) | 0 / 1.0   |

Candidate rejection was not caused by control failure, directional instability, bootstrap sign uncertainty, or sampled-null failure. It was caused by poor absolute generalization: negative \\(R^2\\) and excessive RMSE.

---

## Part XXII — Engineering and Governance Lineage v4.1-v4.5

| EpochHighest stageFailureClassificationOutcomes open?TensorsValid scientific negative?Successor repair |                               |                                                                                                                                                 |                                            |     |        |                       |                      |
| ------------------------------------------------------------------------------------------------------ | ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ | --- | ------ | --------------------- | -------------------- |
| v4.1                                                                                                   | M4 entered                    | Preprocessed-frame label differed from runtime-bound identity                                                                                   | Provenance/metadata failure                | No  | 0      | No                    | `V42_REPAIR_1`       |
| v4.2                                                                                                   | M2 entered, prefreeze blocked | Independent verifier omitted `V42_REPAIR_1` from its closed class set                                                                           | Software/verifier registration defect      | No  | 0      | No                    | `V43_REPAIR_1`       |
| v4.3                                                                                                   | M4 producer complete          | Directory roots passed to file-binding publication; closure classifier defect; IV-4/IV-5 rederivation defects; ill-posed lock-neutrality digest | Software/evaluator/governance defects      | Yes | 19,756 | No M5–M7 result       | `V44_REPAIR_1..6`    |
| v4.4                                                                                                   | S1                            | Successor source pre-populated authoritative paths before M2                                                                                    | Source-staging topology/provenance failure | No  | 0      | No                    | `V45_REPAIR_1`       |
| v4.5                                                                                                   | Z4                            | No engineering failure; M7 candidate failed science gates                                                                                       | Scientific terminal negative               | Yes | 19,756 | **Yes, within scope** | None; terminal epoch |

v4.1–v4.4 are not four failed hidden-decoding experiments. They are immutable evidence of engineering, provenance, and governance failures. Only v4.5 reached the prespecified M7 scientific decision with qualified controls and closure.

---

## Part XXIII — Repair Ledger

| RepairDefect repairedScientific change?Validation in v4.5 |                                                                                           |    |                                                               |
| --------------------------------------------------------- | ----------------------------------------------------------------------------------------- | -- | ------------------------------------------------------------- |
| `V42_REPAIR_1`                                            | Reconcile capture preprocessing label to runtime-bound identity before tokenization       | No | Production M4 tokenization/extraction succeeded               |
| `V43_REPAIR_1`                                            | Add repair classes independently to M2 verifier’s closed class set                        | No | M2 independent verification PASS                              |
| `V44_REPAIR_1`                                            | Replace file binding of governed directory roots with root declarations                   | No | M4 verifier published and passed                              |
| `V44_REPAIR_2`                                            | Derive closure from published firewall state, not static stage membership                 | No | M7 closed as `SCIENCE` through V1 and Z4                      |
| `V44_REPAIR_3`                                            | Replace one-string root guard with AST-wide governed-root sweep                           | No | Prefreeze regression PASS                                     |
| `V44_REPAIR_4`                                            | Complete producer/verifier symmetry sweep over all 11 surfaces                            | No | M2 symmetry checks PASS                                       |
| `V44_REPAIR_5`                                            | Compare lock neutrality on a 24-field scientific projection, excluding five timing fields | No | Projection tests PASS; M4 proceeded after comparison          |
| `V44_REPAIR_6`                                            | Correct V1 realized-path, FIR, and canonical BD-digest rederivations                      | No | IV-4 and IV-5 exact                                           |
| `V45_REPAIR_1`                                            | Stage source outside repository until M2 installs it                                      | No | 91 files/1,680,196 bytes installed byte-exact; S1 and M2 PASS |

Final source-diff ledger:

```
SUBSTANTIVE_SOURCE_DIFF_ROWS=67
SCIENTIFIC_SOURCE_DIFF_COUNT=0
UNCLASSIFIED_SOURCE_DIFF_COUNT=0
UNAUTHORIZED_SOURCE_DIFF_COUNT=0
```

These repairs changed whether the experiment could validly execute, verify, and close. They did not change the scientific target, cohort, model, thresholds, seeds, search family, or decision rules.

---

## Part XXIV — Canonical Numerical Ledger

| NameValueExperiment/stagePopulation/candidateAggregation/statusSource |                         |            |                                             |                    |               |
| --------------------------------------------------------------------- | ----------------------- | ---------- | ------------------------------------------- | ------------------ | ------------- |
| Independent trajectories                                              | 25                      | A′ / II    | Paired identities                           | Independent N      | S3 / A′       |
| Historical captures                                                   | 50                      | A′         | 25 wall + 25 no-wall                        | Capture count      | A′ archive    |
| A′ scored rows                                                        | 950                     | A′         | 475 wall + 475 no-wall                      | Frames, not N      | A′ archive    |
| II inference rows                                                     | 1,796                   | M4         | 475 hidden + 475 no-wall + 846 wall-visible | Forward count      | M4            |
| Extracted layers                                                      | 11                      | M4         | 0,2,…,18,19                                 | T-C                | M4/R5         |
| Tensors                                                               | 19,756                  | M4         | All inference rows × layers                 | Complete           | M4            |
| Tensor shape                                                          | [336,2048]              | M4         | Each layer-row                              | `<f2`              | M4            |
| Corpus bytes                                                          | 27,189,313,536          | M4         | —                                           | Exact              | M4            |
| M5 cells                                                              | 22                      | M5         | 11×2×CURRENT                                | Development        | M5            |
| Advancing layers                                                      | 1                       | M5         | L19                                         | Development        | M5            |
| M6 cells                                                              | 3                       | M6         | L19 global/coarse/BEST-K                    | Development        | M6            |
| M7 funnel candidates                                                  | 3                       | M7         | M6 family                                   | One selected/gated | M7            |
| M7 passing candidates                                                 | 0                       | M7         | —                                           | Terminal           | M7            |
| Best hidden \\(R^2\\)                                                 | -13.8262907             | M7         | L19 coarse current                          | Macro over 25      | M6/M7         |
| \\(R^2\\) lower bound                                                 | -15.4806277             | M7         | Same                                        | Bootstrap          | M7            |
| Hidden RMSE                                                           | 2.0711448               | M7         | Same                                        | Macro              | M6            |
| Hidden MAE                                                            | 1.9244035               | M7         | Same                                        | Macro              | M6            |
| Hidden bias                                                           | 0.0131245               | M7         | Same                                        | Macro              | M5            |
| Hidden \\(\Delta\_A\\)                                                | 0.3991669               | M7         | Same                                        | Macro              | M7            |
| \\(\Delta\_A\\) 95% interval                                          | [0.3484978,0.4536795]   | M7         | Same                                        | Identity bootstrap | M7            |
| \\(p\_A\\)                                                            | 0.02                    | M7         | Selected funnel                             | B=49               | M7            |
| NO\_WALL \\(R^2\\)                                                    | 0.9582204               | M7 control | L19 coarse current                          | Macro N=25         | M7            |
| NO\_WALL RMSE / MAE                                                   | 0.1089887 / 0.0896090   | M7 control | Same                                        | Macro              | M7            |
| WALL\_VISIBLE \\(R^2\\)                                               | 0.9301484               | M7 control | L19 coarse current                          | Macro N=25         | M7            |
| WALL\_VISIBLE RMSE / MAE                                              | 0.1051274 / 0.0778953   | M7 control | Same                                        | Macro              | M7            |
| A′ visible \\(R^2\\) / RMSE                                           | 0.9582681 / 0.1053344   | A′ Stage 2 | BEST-K no-wall                              | Development        | A′            |
| A′ hidden \\(R^2\\) / RMSE                                            | -14.7034147 / 2.1098101 | A′ Stage 2 | BEST-K wall                                 | Development        | A′            |
| Pearson/Spearman                                                      | Not computed            | II         | All evaluated populations                   | UNKNOWN            | Evidence-wide |

---

## Part XXV — Main Quantitative Tables

### Table A — Stage Summary

| StagePurposeInputOutputTypeStatus |                                          |                                           |                       |                        |                                |
| --------------------------------- | ---------------------------------------- | ----------------------------------------- | --------------------- | ---------------------- | ------------------------------ |
| R1–R5                             | Qualify hooks, numerics, resources, tier | Synthetic/frozen non-outcome inputs       | T-C lock              | Engineering/governance | PASS                           |
| M4                                | Extract real activations                 | 1,796 target rows                         | 19,756 tensors        | Measurement            | PASS                           |
| M5                                | Screen layers/reps                       | Hidden activations                        | L19 advances          | Development            | PASS                           |
| M6                                | Refine L19                               | Three representations                     | Coarse selected       | Development            | PASS                           |
| M7                                | Final qualification                      | Selected funnel + controls/null/bootstrap | No candidate          | Scientific             | FAIL predicate; valid terminal |
| V1                                | Independent rederivation                 | Frozen evidence                           | Exact applicable rows | Verification           | PASS                           |
| Z1–Z4                             | Seal/archive/release                     | Complete evidence set                     | Canonical closure     | Governance             | PASS                           |

### Table B — Candidate Ranking

| RankCandidateLayerRepresentationTemporalHidden \\(R^2\\)RMSECorrelation\\(p\_A\\)M5M6M7 |                    |    |             |         |          |        |              |                         |                      |        |            |
| --------------------------------------------------------------------------------------- | ------------------ | -- | ----------- | ------- | -------- | ------ | ------------ | ----------------------- | -------------------- | ------ | ---------- |
| 1                                                                                       | L19 coarse current | 19 | Coarse 2×6  | Current | -13.8263 | 2.0711 | Not computed | 0.02                    | Rank 1/advance       | Rank 1 | G3/G4 fail |
| 2                                                                                       | L19 global current | 19 | Global mean | Current | -14.0658 | 2.0900 | Not computed | Not individually tested | Rank 6/advance layer | Rank 2 | Not gated  |
| 3                                                                                       | L19 BEST-K current | 19 | BEST-K      | Current | -14.9922 | 2.1453 | Not computed | Not individually tested | —                    | Rank 3 | Not gated  |

### Table C — M7 Gate Table

The complete nine-row gate table appears in Part XV. The decisive failures were G3 and G4.

### Table D — Visibility Comparison

| PopulationN\\(R^2\\)RMSEMAECorrelationNullStatus |    |          |        |        |              |                      |            |
| ------------------------------------------------ | -- | -------- | ------ | ------ | ------------ | -------------------- | ---------- |
| NO\_WALL                                         | 25 | 0.9582   | 0.1090 | 0.0896 | Not computed | No selection-null p  | PASS       |
| WALL\_VISIBLE                                    | 25 | 0.9301   | 0.1051 | 0.0779 | Not computed | No selection-null p  | PASS       |
| WALL\_HIDDEN                                     | 25 | -13.8263 | 2.0711 | 1.9244 | Not computed | \\(p\_A=.02\\), B=49 | FAIL G3/G4 |

### Table E — Regime A′ vs Experiment II

See Part XX. Experiment II expanded depth, spatial representation, selection control, same-wall visibility control, bootstrap, and full-funnel randomization; it did not retain temporal alternatives.

### Table F — Engineering Lineage

See Part XXII. Only v4.5 constitutes the completed scientific result.

### Table G — Claim Ledger

See Part XXVII.

---

## Part XXVI — Result Classification

| ResultNumerical performanceStatistical evidenceMeasurement validityScientific claim |                                                        |                                                 |                                    |                                                               |
| ----------------------------------------------------------------------------------- | ------------------------------------------------------ | ----------------------------------------------- | ---------------------------------- | ------------------------------------------------------------- |
| Regime A′ visible                                                                   | Very strong                                            | Supported by bootstrap                          | Qualified within development study | Supported with scope                                          |
| Regime A′ hidden                                                                    | Worse than baseline                                    | Failure interval wholly negative                | Qualified within development study | Layer/readout failure supported; global absence not supported |
| Experiment II best M5                                                               | Worse than baseline by \\(R^2\\); weak \\(\Delta\_A\\) | Developmental/unknown terminally                | Qualified                          | Not confirmatory                                              |
| Experiment II best M6                                                               | Worse than baseline by \\(R^2\\); weak \\(\Delta\_A\\) | Developmental/unknown terminally                | Qualified                          | Not confirmatory                                              |
| Experiment II final M7                                                              | Worse than baseline by \\(R^2\\); RMSE 4.14× ceiling   | \\(p\_A\\) supported, but accuracy gates failed | Qualified controls and extraction  | No qualifying candidate, supported with scope                 |

This is not a flat zero-signal result, because \\(\Delta\_A\\), bootstrap, folds, directions, and \\(p\_A\\) were positive. It is not a near miss, because the absolute predictive criteria were missed severely.

---

## Part XXVII — Claim Ledger

| ClaimStatusEvidence / caveat                         |                                  |                                                                          |
| ---------------------------------------------------- | -------------------------------- | ------------------------------------------------------------------------ |
| Visible current position is linearly decodable       | Established with scope           | Strong A′ and v4.5 visible controls                                      |
| Qualified measurement path recovers visible position | Established with scope           | Both M7 controls pass                                                    |
| Spatial structure carries positional information     | Provisional                      | Coarse beat global in all 11 hidden screen layers, but no cell qualified |
| Layer 4 is sufficient for visible position           | Established with scope           | Regime A′ visible result                                                 |
| Layer 4 is sufficient for hidden position            | Invalidated for tested readouts  | Strong negative A′ and II continuity results                             |
| Another tested layer has a qualifying hidden code    | Invalidated within tested family | L19 best, but failed G3/G4                                               |
| Token preservation rescues hidden decoding           | Invalidated for L19 BEST-K       | Performed worse than coarse                                              |
| Spatial preservation rescues hidden decoding         | Not established                  | Modest improvement, no qualification                                     |
| Temporal refinement rescues hidden decoding          | Not tested                       | T-C retained CURRENT only                                                |
| A hidden decoder qualifies in the II family          | Invalidated                      | Zero M7 passers                                                          |
| No tested II candidate satisfied qualification       | Established with scope           | Canonical M7/Z4 result                                                   |
| Hidden information is absent from MineWorld          | Not established                  | Decodability is representation/readout-specific                          |
| Hidden information is absent from all layers         | Not established                  | Only 11 of 20 layers were actually extracted                             |
| No nonlinear hidden information exists               | Not tested                       |                                                                          |
| No temporal hidden information exists                | Not tested                       |                                                                          |
| Posterior uncertainty is represented/calibrated      | Not tested                       |                                                                          |
| Model causally uses hidden state                     | Not tested                       |                                                                          |
| Object permanence has been established               | Not established                  |                                                                          |

---

## Part XXVIII — Exact Scope of the Negative Result

**Strongest defensible negative claim:** No candidate within the prespecified and actually evaluated Experiment II family—11 current-frame decoder-layer locations, global and coarse 2×6 spatial representations at each, and layer-19 BEST-K refinement—satisfied the complete hidden-position qualification criteria on the 25-identity `layout_01`, speed-2.0 D0 apparatus.

This supports the conclusion that the original Regime A′ failure is unlikely to be explained merely by selecting layer 4 or by fully collapsing spatial tokens. A deeper layer and coarse spatial preservation produced only a small improvement and remained far outside the accuracy envelope.

It does not establish:

- absence of information throughout MineWorld;
- failure at the nine unsampled decoder layers;
- failure of nonlinear probes;
- failure of temporal differences or multi-frame concatenation;
- failure of full-grid, PCA, or wall-ROI representations;
- generalization beyond the single layout and speed;
- absence of a distributional or uncertain hidden-state representation;
- absence of causal use.

“No qualifying decoder” is not logically equivalent to “no information exists.”

---

## Part XXIX — Valuable Subthreshold Signal Analysis

The best candidate’s positive features were:

- \\(\Delta\_A=0.39917\\) blocks;
- bootstrap interval [0.34850, 0.45368];
- positive fold and direction means;
- \\(p\_A=0.02\\);
- coarse spatial pooling consistently outperforming global pooling;
- modest improvement over Regime A′ hidden RMSE.

The negative features were much stronger:

- macro \\(R^2=-13.8263\\);
- lower bound \\(-15.4806\\);
- RMSE 2.0711 versus a 0.50 ceiling;
- null mean 0.38457 versus observed 0.39917;
- null maximum only 0.000207 below observed;
- α=1000 in every selected fold, indicating very strong regularization;
- late phase means essentially at zero.

The \\(\tau\\)-wise MAE diagnostic declined from approximately 1.625 at \\(\tau=1\\) to 2.406 near \\(\tau=9\\), then decreased toward 1.496 by \\(\tau=19\\); comparison with the phase-preserving B0 showed most advantage concentrated early, with near-zero or slightly negative advantage after roughly \\(\tau=10\\). Because the null preserves direction, phase, and \\(\tau\\), this cannot cleanly be interpreted as a memory trace. It is an outcome-aware forensic pattern, not a gate.

```
VALUABLE_SUBTHRESHOLD_SIGNAL=WEAK
NEAR_MISS=false
```

The scientifically useful residue is evidence that depth and coarse spatial organization affect the ranking of weak signals. It is not evidence of a qualified hidden-state code.

---

## Part XXX — Paper-Ready Methodology

### Scientific objective and relationship to Regime A′

Experiment II tested whether current sheep position during complete occlusion became linearly decodable after expanding beyond the Regime A′ layer-4/collapsed-readout limitation. The experiment reused the 25 qualified paired trajectories but performed new inference under a frozen MineWorld model and source closure.

### Model and apparatus

MineWorld `700M_16f` was fixed by checkpoint SHA-256. The D0 apparatus used `layout_01`, speed 2.0, paired left-to-right/right-to-left paths, and true current sheep world-\\(x\\) as target. Three visibility populations separated ordinary visible measurement, visible measurement in the wall domain, and complete occlusion.

### Independent sampling and targets

The independent unit was the trajectory identity. Twenty-five identities were assigned to five grouped outer folds. All frames belonging to an identity remained together. Hidden and no-wall populations contributed 19 target rows per identity; the wall-visible population contributed 846 rows in total. Targets were reconstructed from the realized noise-seed-driven paths and causal-FIR alignment.

### Extraction

For each target row, the model received a complete 16-pair teacher-forced context. The current pair’s 336 visual tokens were captured at 11 T-C decoder-layer edges. The resulting `<f2` tensors had shape [336,2048]. M4 published 19,756 tensors and an independent verifier checked the complete corpus.

### Representations

M5 evaluated global mean pooling and 2×6 coarse spatial pooling at every extracted layer. M6 evaluated those representations plus training-only BEST-K token concatenation at the advancing layer. Under T-C, all cells used the current activation only.

### Decoder and nested validation

Training features were standardized within each fold. Ridge regression used an unpenalized intercept and alpha grid 0.1–1000. Hyperparameters and BEST-K token selection were chosen solely from outer-training identities through nested inner rotations. Predictions and metrics were calculated on held-out identities.

### Candidate search and separation from controls

M5 candidate ranking and layer advancement used only `WALL_HIDDEN` outcomes. M6 refined the advancing layer. Visible controls could not influence layer, representation, temporal, token, or hyperparameter selection. The frozen full-funnel selector chose one finalist; runner-up substitution was prohibited.

### Final qualification

M7 ran an identity bootstrap, both visible controls, and 49 selection-aware full-funnel randomizations within direction×phase strata. Qualification required all nine Claim-A gates, including positive \\(\Delta\_A\\) and lower bound, positive macro \\(R^2\\) and lower bound, RMSE ≤0.50, fold/direction/phase stability, passing controls, and \\(p\_A≤0.05\\).

### Provenance and verification

Authority bytes, model/checkpoint identities, source closure, cohort, targets, folds, tensors, feature transformations, and stage results were frozen and hashed. M2 independently verified the source closure. V1 independently rederived the applicable scientific verification matrix. Z1–Z4 sealed, read back, released, and closed the evidence.

---

## Part XXXI — Paper-Ready Results

### Qualification and extraction

R1–R5 passed, locking T-C before scientific outcomes were available. M4 successfully executed 1,796 model forwards and stored 19,756 activations across 11 layers. Producer and verifier artifacts both passed.

### M5 screening

Twenty-two current-frame cells were screened. Layer 19 coarse pooling ranked first with \\(\Delta\_A=0.3992\\), macro \\(R^2=-13.8263\\), and RMSE 2.0711 blocks. Coarse pooling exceeded global pooling at every screened layer. One layer, L19, advanced.

### M6 refinement

At L19, BEST-K token concatenation failed to improve on coarse pooling, yielding \\(R^2=-14.9922\\) and RMSE 2.1453. The original L19 coarse cell remained the finalist.

### M7 qualification

The finalist passed positive-effect, bootstrap, fold, direction, phase, visible-control, and selection-aware \\(p\_A\\) gates. It failed the positive-\\(R^2\\) gate and the 0.50-block RMSE ceiling. Zero candidates qualified, and M7 emitted `NO_CANDIDATE_IN_AUTHORIZED_FAMILY`.

### Visibility comparison

The identical selected representation decoded visible position accurately: `NO_WALL` \\(R^2=0.9582\\), RMSE 0.1090; `WALL_VISIBLE` \\(R^2=0.9301\\), RMSE 0.1051. Under complete occlusion, \\(R^2=-13.8263\\) and RMSE 2.0711. Both visible controls passed.

### Verification and closure

V1 passed with no mismatched applicable rows. Z1–Z4 passed, and Z4 classified the run as a scientific closure with no qualifying candidate.

---

## Part XXXII — Paper-Ready Scientific Discussion

The evidence supports an occlusion-associated failure of qualified linear accessibility. The model’s selected activations carried enough information for highly accurate visible position recovery, including in the presence of the wall, but the same layer and representation did not support accurate current-position prediction after the sheep became fully hidden.

Testing depth and coarse spatial organization addressed two major alternatives left open by Regime A′. Layer 19 and coarse pooling improved the hidden result modestly, showing that readout choice was not wholly irrelevant. The improvement was nevertheless too small to explain the original failure as a poor layer/readout choice. A token-selective representation performed worse.

The positive \\(\Delta\_A\\) and \\(p\_A\\) indicate a weak structured deviation from the particular null, but do not overcome the severe absolute error. Statistical detectability of a small difference is not equivalent to scientifically adequate reconstruction of the target.

The visible controls argue against measurement-path failure and generic wall-domain shift. They do not prove that occlusion causally destroys an internal representation; the comparison is observational within the apparatus. Likewise, linear decodability does not establish that the model uses the decoded variable causally.

The result is negative rather than broken because the model was correctly identified, extraction completed, numerical fixtures and grouped hooks passed, visible controls worked, candidate selection and null testing executed, V1 passed its applicable matrix, and Z4 closed the scientific state. The failed objects were the candidate’s scientific accuracy predicates.

---

## Part XXXIII — Paper-Ready Scientific Result Paragraphs

### Version A — Plain English

We asked whether the earlier failure to read a hidden sheep’s position was caused by looking at the wrong layer or by averaging away useful spatial information. We tested 11 model depths and several ways of retaining token or spatial structure. The best decoder came from the final layer and a coarse spatial grid, but it still made errors of about 2.07 blocks and performed much worse than the required positive-\\(R^2\\) standard.

The same extraction and decoder path recovered position to about 0.1 blocks whenever the sheep was visible, including when a wall was present. The pipeline therefore worked; the negative was specific to full occlusion in this apparatus. Zero candidates passed the final gate. This does not prove that MineWorld contains no hidden information, only that none of the tested readouts recovered it to the prespecified standard.

### Version B — Abstract/results language

Using 25 identity-grouped trajectories, we screened current-frame activations from 11 MineWorld decoder layers with global and coarse-spatial linear readouts and refined the advancing layer with training-only BEST-K token selection. The best hidden-position candidate, layer-19 coarse 2×6 pooling, achieved macro \\(R^2=-13.826\\), RMSE \\(=2.071\\) blocks, and \\(\Delta\_A=0.399\\) [95% bootstrap interval 0.348–0.454]. Although its selection-aware randomization statistic passed at \\(p\_A=0.02\\), it failed prespecified positive-\\(R^2\\) and RMSE≤0.50 qualification gates. Matched visible controls remained strong (`NO_WALL`: \\(R^2=0.958\\), RMSE 0.109; `WALL_VISIBLE`: \\(R^2=0.930\\), RMSE 0.105). Thus no candidate in the evaluated family qualified for hidden current-position decoding.

### Version C — Skeptical reviewer language

Within one layout, one speed, 25 reused trajectory identities, 11 sampled decoder layers, current-frame linear ridge probes, two compact spatial summaries, and one layer-19 token-selection refinement, no selected candidate met the complete prospective accuracy and control criteria for current hidden sheep position. The result weakens—but does not eliminate—the hypothesis that the prior layer-4 failure resulted solely from depth or global spatial collapse. It does not constrain untested layers, temporal representations, nonlinear readouts, uncertainty representations, or causal use.

---

## Part XXXIV — Figure and Table Plan

1. **Scientific progression:** Regime A′ visible/hidden result → Experiment II search → M7 no-candidate closure. Sources: [A′ decision]\(/home/sagemaker-user/mineocclude-archives/regime\_a\_prime\_stage2\_v0\_4\_final\_20260820/04\_SCIENTIFIC\_RESULTS/stage2\_decision.json), [M5]\(/home/sagemaker-user/mineocclude-experiment-ii-r72-v4-5/evidence/m5/producer/M5\_SCREEN\_AND\_ADVANCEMENT.json), [M7]\(/home/sagemaker-user/mineocclude-experiment-ii-r72-v4-5/evidence/m7/producer/M7\_NULL\_BOOTSTRAP\_CONTROLS\_DECISION.json).
2. **Visibility conditions schematic:** no wall/visible, wall/visible, wall/hidden, with common target definition. Sources: [authority]\(/home/sagemaker-user/mineocclude-authorities/MineOcclude\_Continuation\_Experiment\_II\_Rapid\_72H\_Terminal\_Execution\_Authority\_v3.7.11.md), [S3]\(/home/sagemaker-user/mineocclude-experiment-ii-r72-v4-5/evidence/s-3/producer/S3\_D0\_ROSTER\_TARGET\_BASELINE\_LEDGER.json).
3. **Layer performance:** M5 \\(\Delta\_A\\), \\(R^2\\), and RMSE by layer, separate global/coarse lines. Source: M5.
4. **Representation performance:** paired coarse-minus-global differences across layers and the L19 BEST-K result. Sources: M5 and M6.
5. **M5→M6 funnel:** 22 screen cells → L19 → three refinements → one selected candidate. Sources: M5, M6, M7.
6. **M7 gates:** pass/fail plot with normalized distance from each threshold. Source: M7.
7. **A′ versus Experiment II:** hidden \\(R^2\\)/RMSE and visible controls, with clear readout/population labels. Sources: A′, M5, M7.
8. **Supplementary engineering lineage:** v4.1–v4.5 stages, defects, repairs, and closure classes. Sources: authority addenda and each epoch’s terminal evidence.

Tables A–G in Part XXV should accompany these figures. Error bars should be limited to intervals actually present in evidence; no correlation plot should be created.

---

## Part XXXV — Discrepancy Ledger

| DiscrepancySource ASource BLikely reasonCanonical interpretationConfidence              |                            |                                 |                                                                                   |                                                                                                                    |      |
| --------------------------------------------------------------------------------------- | -------------------------- | ------------------------------- | --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ | ---- |
| All three populations said to share B0≈2.47031                                          | Supplied secondary readout | M7 per-identity/control metrics | Secondary overgeneralization                                                      | NO\_WALL and hidden share ≈2.47031; wall-visible baseline ≈7.73749                                                 | High |
| M5 field labelled `SCREEN_NO_WALL_DIAGNOSTIC` contains hidden metrics                   | M5 artifact                | Frozen `stage_m5` source        | Hidden cell values were passed into the descriptive helper                        | Do not report this field as an actual no-wall diagnostic; it had no gate/ranking authority                         | High |
| G1 provenance gate recorded true from literal argument                                  | M7 artifact/source         | Broader M2/S3/V1 checks         | Integration used `provenance_pass=True` rather than recomputing a local predicate | G1’s local implementation is weak; independent provenance/leakage evidence exists elsewhere; G3/G4 remain decisive | High |
| V1 IV-11 says “M7 produced no artifact”                                                 | V1 bundle                  | Existing M7 artifact            | Terminal verifier applicability walker stopped at the failing stage               | V1 did not rederive M7 null/bootstrap/control logic                                                                | High |
| M4 authority says lock-neutrality record must be included in M4 artifact                | Authority                  | M4 artifact/source              | Comparison executes before model load but returned artifact omits `neutrality`    | It must have passed for M4 to proceed, but the mandated record is absent                                           | High |
| Whole-plan versus scientific-plan digest                                                | R5                         | Authority/M2 tests              | Whole plan includes five live timing fields                                       | Whole digest `ac066…`; scientific digest `f43bac…`; they are not interchangeable                                   | High |
| “All-layer” wording                                                                     | Program title/R1           | Real T-C extraction             | T-C scope reduction                                                               | R1 qualified all 20 hooks; real science extracted 11 layers                                                        | High |
| M7 candidate count 3 versus one                                                         | M7 observed statistics     | M7 gate record                  | Three-cell funnel, one selected candidate formally gated                          | Report 3 evaluated funnel cells, 1 gated, 0 passed                                                                 | High |
| Supervisor `EXPERIMENT_II_BLOCKED` versus Z4 no-candidate state                         | Supervisor scratch state   | Z4                              | Generic failed-stage process label versus governed scientific state               | Z4 is authoritative                                                                                                | High |
| Declared bfloat16 versus realized float16                                               | Configuration language     | M4 tensor manifest              | Runtime load realization                                                          | Report actual corpus as `<f2`                                                                                      | High |
| “26 GiB” corpus description                                                             | Informal summaries         | Exact byte count                | Decimal/binary rounding                                                           | 27.189 GB or 25.32 GiB                                                                                             | High |
| Regime A′ readout described as summed/collapsed versus Stage-2 `leading_readout=BEST_K` | Authority narrative        | Stage-2 decision                | Historical continuity terminology versus final Stage-2 estimator naming           | Use Stage-2 values/readout labels; avoid claiming exact method identity with II global mean                        | High |
| Correlation expected in requested tables                                                | Requested schema           | Production artifacts            | Metric not implemented/reported                                                   | `UNKNOWN — NOT COMPUTED`, never zero                                                                               | High |

These limitations merit disclosure, but none changes the numerical G3/G4 failures or visible-control contrast.

---

## Part XXXVI — Unknown / Missing Evidence

| UnknownWhy it mattersEvidence required                                        |                                                                  |                                                                       |
| ----------------------------------------------------------------------------- | ---------------------------------------------------------------- | --------------------------------------------------------------------- |
| Held-out Pearson/Spearman correlation for any final population                | Could distinguish ordering from calibration                      | Frozen predictions plus prospectively defined correlation computation |
| Performance at decoder layers 1,3,5,…,17                                      | Real T-C sampled only stride-2 layers plus L19                   | Prospectively authorized extraction/evaluation evidence               |
| Temporal-difference or two-frame performance                                  | T-C retained current only                                        | Authorized temporal candidate artifacts                               |
| Full-grid, PCA, or wall-ROI performance                                       | Not evaluated in T-C                                             | Authorized candidate artifacts                                        |
| Nonlinear hidden-position accessibility                                       | Linear ridge only                                                | A separately authorized nonlinear evaluation                          |
| Posterior uncertainty or calibration                                          | Point target only                                                | Distributional targets and scoring evidence                           |
| Causal use of hidden state                                                    | Decodability is observational                                    | Controlled intervention evidence                                      |
| Generalization to other layouts/speeds                                        | One layout and speed                                             | Independent qualified populations                                     |
| Fully independent rederivation of M7 null/bootstrap/controls                  | V1 rows were N/A                                                 | Independent verifier output over M7                                   |
| A single globally comparable baseline across all three visibility populations | Wall-visible row/target universe differs                         | A prospectively defined common-population comparison                  |
| Global absence of hidden information                                          | Candidate-family negative is not an information-theoretic result | Much broader, separately authorized evidence                          |

---

## Part XXXVII — Direct Answers to the 45 Final Scientific Questions

1. **What exactly was Experiment II testing?** Whether current occluded sheep world-\\(x\\) became linearly decodable after searching prespecified decoder depths and token/spatial readouts under controlled selection and qualification.
2. **Why was it needed after Regime A′?** Regime A′ could not exclude a wrong-layer or destructive-readout explanation.
3. **Did the pipeline successfully execute?** Yes, through M7, V1, and Z4.
4. **Did final v4.5 suffer an engineering failure?** No terminal engineering failure determined the result.
5. **Did M4 succeed?** Yes: producer/verifier PASS; 19,756 complete tensors.
6. **Did M5 succeed?** Yes; 22 cells screened and L19 advanced.
7. **Did M6 succeed?** Yes; three L19 representations were evaluated.
8. **What did M5 find?** L19 coarse/current was best; coarse beat global at all 11 layers, but every cell had strongly negative \\(R^2\\) and RMSE above 2 blocks.
9. **What changed during M6?** BEST-K token selection was added at L19; it performed worse than coarse pooling.
10. **Why did M7 terminate?** The selected candidate failed positive-\\(R^2\\) and RMSE≤0.50 gates.
11. **Scientific negative or software failure?** Scientific negative within scope.
12. **Why were M8 and H-0 not run?** M7 locked no candidate, so their required terminal-model preconditions were absent.
13. **Did V1 independently verify the terminal state?** Yes for its governed applicable matrix and the decisive M5/M6 metrics; it did not independently rederive M7’s null/bootstrap/control rows.
14. **Did Z4 canonically close the experiment?** Yes.
15. **Was visibility explicitly tested?** Yes, through `NO_WALL` and `WALL_VISIBLE`.
16. **NO\_WALL result?** \\(R^2=0.9582204\\), RMSE 0.1089887, MAE 0.0896090; PASS.
17. **WALL\_VISIBLE result?** \\(R^2=0.9301484\\), RMSE 0.1051274, MAE 0.0778953; PASS.
18. **WALL\_HIDDEN result?** \\(R^2=-13.8262907\\), RMSE 2.0711448, MAE 1.9244035; FAIL G3/G4.
19. **Did visible decoding remain strong?** Yes.
20. **Was hidden decoding specifically impaired under occlusion?** Strongly associated with occlusion in this apparatus; causal wording should be avoided.
21. **Could wall-domain shift alone explain it?** No; wall-visible decoding remained strong.
22. **Did another layer improve hidden decoding?** L19 modestly improved over layer 4, but did not qualify.
23. **Which layer was best?** Layer 19.
24. **Did token preservation improve hidden decoding?** No; L19 BEST-K was worse.
25. **Did spatial preservation improve hidden decoding?** Modestly and consistently versus global pooling, but not enough to rescue qualification.
26. **Did temporal refinement improve hidden decoding?** Unknown; it was not tested under T-C.
27. **Strongest representation/configuration?** L19 coarse 2×6 concatenation, current activation.
28. **Best hidden \\(R^2\\)?** -13.82629069261263.
29. **Best hidden RMSE?** 2.07114480506697 blocks.
30. **Best correlation?** Unknown—no held-out Pearson or Spearman correlation was computed.
31. **Best \\(p\_A\\)?** 0.02 for the selected funnel statistic.
32. **Which exact M7 gate eliminated it?** First G3; G4 independently failed.
33. **How far from threshold?** \\(R^2\\) was 13.8263 below zero; its lower bound was 15.4806 below zero; RMSE exceeded the 0.50 ceiling by 1.5711 blocks.
34. **Flat negative or near miss?** Neither flat nor near: weak subthreshold signal with severe absolute-performance failure.
35. **Scientifically valuable subthreshold signal?** Weak: depth and coarse spatial structure changed rankings, but the effect was mostly null-reproducible and not predictively adequate.
36. **Did II explain A′ as merely a bad readout?** No.
37. **How much broader is the negative?** It extends from one historical layer/readout to 11 layers, two compact readouts at all 11, and BEST-K at L19, with selection-aware qualification. It does not cover all layers or temporal/nonlinear families.
38. **What is established about linearly accessible hidden position?** No tested candidate met the complete qualification criteria.
39. **What is not established globally?** Absence of all hidden information, nonlinear/temporal information, uncertainty, or causal use.
40. **Did v4.1–v4.4 constitute valid scientific negatives?** No.
41. **What methodology is manuscript-defensible?** The frozen 25-identity grouped nested ridge study, 11-layer current-frame search, coarse/global screen, L19 BEST-K refinement, identity bootstrap, visible controls, selection-aware B=49 null, and nine-gate decision—with limitations disclosed.
42. **Which numbers belong in the paper?** The exact A′ values, M4 corpus size, M5/M6 candidate counts, best hidden \\(R^2\\)/RMSE/MAE/\\(\Delta\_A\\)/interval, \\(p\_A\\), gate thresholds/margins, and both visible-control results.
43. **Strongest supported conclusion?** No candidate in the actually evaluated Experiment II family qualified for current hidden-position decoding, despite strong matched visible decoding.
44. **What wording would mislead?** “MineWorld has no hidden state,” “all layers were negative,” “temporal decoding failed,” “the model forgot the sheep,” or “object permanence is absent.”
45. **In plain English, what happened?** The experiment looked harder and in more places for a readable hidden-position signal. It found small readout-dependent differences, but nothing accurate enough to qualify. The same machinery read position almost perfectly when the sheep was visible, so the experiment worked and returned a bounded negative about occluded linear decoding.

---

## Part XXXVIII — Required Final Summary Fields

```
EXPERIMENT_II_EXECUTION_STATUS=COMPLETED_AND_CANONICALLY_CLOSED

ENGINEERING_FAILURE_AT_TERMINAL=false

EXPERIMENT_II_TERMINAL_RESULT=NO_CANDIDATE_IN_AUTHORIZED_FAMILY

PIPELINE_COMPLETED_AS_DESIGNED=true

VISIBLE_CONTROL_STATUS=BOTH_D0_VISIBLE_CONTROLS_PASS

NO_WALL_RESULT=R2_0.9582204252479568_RMSE_0.10898870988252715_MAE_0.08960901443713683_PASS

WALL_VISIBLE_RESULT=R2_0.9301483642259436_RMSE_0.105127429355996_MAE_0.0778953355694566_PASS

WALL_HIDDEN_RESULT=R2_-13.82629069261263_RMSE_2.07114480506697_MAE_1.9244035029976125_FAIL_G3_G4

M5_TOTAL_CANDIDATES=22

M5_ADVANCING_CANDIDATES=1_LAYER_L19

M6_REFINED_CANDIDATES=3

M7_EVALUATED_CANDIDATES=3_FUNNEL_CELLS_1_FORMALLY_GATED

M7_PASSING_CANDIDATES=0

BEST_OVERALL_CANDIDATE=L19|COARSE_2X6_CONCAT|CURRENT

BEST_LAYER=19

BEST_REPRESENTATION=COARSE_2X6_CONCAT

BEST_TEMPORAL_CONFIGURATION=CURRENT

BEST_HIDDEN_R2=-13.82629069261263

BEST_HIDDEN_RMSE=2.07114480506697

BEST_HIDDEN_MAE=1.9244035029976125

BEST_CORRELATION=UNKNOWN_NOT_COMPUTED

BEST_P_A=0.02

DECISIVE_M7_GATE=G3_MACRO_R2_AND_LOWER_BOUND_POSITIVE_WITH_INDEPENDENT_G4_RMSE_FAILURE

DECISIVE_M7_VALUE=MACRO_R2_-13.82629069261263_LOWER_-15.480627717409206

DECISIVE_M7_THRESHOLD=MACRO_R2_GT_0_AND_LOWER_GT_0

DISTANCE_FROM_THRESHOLD=R2_13.82629069261263_BELOW_ZERO_LOWER_15.480627717409206_BELOW_ZERO_RMSE_1.57114480506697_ABOVE_CEILING

DID_ANOTHER_LAYER_HELP=YES_MODESTLY_BUT_NOT_QUALIFYING

DID_TOKEN_PRESERVATION_HELP=NO

DID_SPATIAL_PRESERVATION_HELP=YES_DEVELOPMENTALLY_BUT_NOT_ENOUGH_TO_QUALIFY

DID_TEMPORAL_REFINEMENT_HELP=NOT_TESTED_UNDER_T_C

ORIGINAL_LAYER4_FAILURE_EXPLAINED_BY_READOUT_CHOICE=NO

VALUABLE_SUBTHRESHOLD_SIGNAL=WEAK_NOT_A_NEAR_MISS

NULL_CONTROLS_BEHAVED_AS_EXPECTED=YES_VALID_SELECTION_AWARE_NULL_P_A_0.02_BUT_NULL_REPRODUCED_MOST_OF_EFFECT

EVIDENCE_OF_SHORTCUT_OR_LEAKAGE=NO_DETECTED_LEAKAGE_WITH_DISCLOSED_G1_AND_M5_DIAGNOSTIC_IMPLEMENTATION_LIMITATIONS

V1_INDEPENDENT_VERIFICATION_PASS=true_WITH_M7_NULL_BOOTSTRAP_CONTROL_ROWS_NOT_INDEPENDENTLY_REDERIVED

Z4_CANONICAL_CLOSURE_PASS=true

SUPPORTED_CONCLUSION=ZERO_TESTED_CANDIDATES_SATISFIED_COMPLETE_HIDDEN_POSITION_QUALIFICATION

SUPPORTED_WITH_SCOPE=11_T_C_DECODER_LAYERS_CURRENT_FRAME_GLOBAL_AND_COARSE_READOUTS_PLUS_L19_BEST_K_ON_25_LAYOUT_01_SPEED_2_IDENTITIES

NOT_ESTABLISHED=GLOBAL_ABSENCE_OF_HIDDEN_INFORMATION_ALL_LAYER_ABSENCE_NONLINEAR_OR_TEMPORAL_ABSENCE_UNCERTAINTY_CAUSAL_USE_OR_OBJECT_PERMANENCE

PLAIN_ENGLISH_SCIENTIFIC_RESULT=THE_PIPELINE_WORKED_AND_VISIBLE_POSITION_REMAINED_EASY_TO_READ_BUT_NONE_OF_THE_TESTED_READOUTS_RECOVERED_OCCLUDED_CURRENT_POSITION_ACCURATELY_ENOUGH_TO_QUALIFY
```

9:55 PM