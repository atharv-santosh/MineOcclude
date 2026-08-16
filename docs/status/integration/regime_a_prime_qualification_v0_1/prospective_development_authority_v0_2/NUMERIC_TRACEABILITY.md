# Numeric traceability

There are no `UNJUSTIFIED` scientific numbers in this repaired draft.

| Choice | Value | Classification | Basis/disposition |
|---|---:|---|---|
| Forensic base | `db2e110…` | `FROZEN_EVIDENCE_DERIVED` | Accepted independent temporal-forensic freeze base |
| Camera/apparatus geometry | authority JSON values | `FROZEN_EVIDENCE_DERIVED` | Controlling P3 apparatus authority |
| Capture cadence | 20 Hz / 0.05 s | `FROZEN_EVIDENCE_DERIVED` | Controlling P3 motion/sampling authority |
| Fixed development speed | 2.0 blocks/s | `FROZEN_EVIDENCE_DERIVED` | P3 C01 qualified headroom; speed was not the visibility remedy |
| Motion noise / frames / path starts | 0.05 / 180 / ±7.8 | `FROZEN_EVIDENCE_DERIVED` | Controlling P3 design |
| Stage-1 run count | 8 | `FROZEN_EVIDENCE_DERIVED` | Minimum replicated 2-direction × 2-scene measurement/held-out design; within frozen redesign's 4–8 calibration range |
| Trajectories per direction | 4 | `PURE_IMPLEMENTATION_CONSTANT` | Exact consequence of the eight-run balanced design, not an acceptance precision claim |
| Temporal max search lag | 8 ticks | `FROZEN_EVIDENCE_DERIVED` | Frozen accepted temporal estimator scope |
| Temporal confidence level | 0.95 | `FROZEN_EVIDENCE_DERIVED` | Frozen temporal evidence procedure; no unused prospective bootstrap choice remains |
| Temporal CI width | measured, no cutoff | `PROSPECTIVE_STAGE1_MEASURED` | Invalid scaled historical cutoff removed |
| Historical delay interval | `[3.185002…,3.542259…]` | `FROZEN_EVIDENCE_DERIVED` | Reference only; explicitly not an acceptance gate |
| Inter-method agreement | 95% interval overlap | `PURE_IMPLEMENTATION_CONSTANT` | Transparent statistical consistency rule; no tick tolerance |
| Silhouette extent | Stage-1 measured; historical `0.6–0.8` reference | `PROSPECTIVE_STAGE1_MEASURED` | Frozen evidence does not identify an exact extent |
| Transition guard / hidden onset | Stage-1 measured | `PROSPECTIVE_STAGE1_MEASURED` | Unsupported fixed values removed |
| Lane and wall-relative origin | `[-8,8]`, `0.5` | `FROZEN_EVIDENCE_DERIVED` | Frozen apparatus geometry |
| Endpoint/gap/sample cutoffs | none | `PROSPECTIVE_STAGE1_MEASURED` | Unsupported `0.25/0.25/320` gates removed; summaries retained |
| Stable error support | 60/class/direction | `FROZEN_EVIDENCE_DERIVED` | Exact zero-error upper 95% bound is `0.04870291331009746` |
| Hidden target rows | 19 | `FROZEN_EVIDENCE_DERIVED` | Controlling P3 target-row design |
| Retry maximum | 3 | `FROZEN_EVIDENCE_DERIVED` | Controlling P3 recovery policy |
| Stage-2 identities/captures/folds | 25 / 50 / 5 | `FROZEN_EVIDENCE_DERIVED` | Controlling paired P3 design |
| Stage-2 phase offsets/direction balance | 0,3,6,9,12 / 13:12 | `FROZEN_EVIDENCE_DERIVED` | Controlling P3 fold×phase design; every fold contains every phase |
| Episode IDs, seeds, and replicate indices | manifest values | `PURE_IMPLEMENTATION_CONSTANT` | Deterministic fresh identity/allocation constants; no acceptance role |
| Corrected P2 BEST-K reference | `0.07780238881820632` | `FROZEN_EVIDENCE_DERIVED` | Independently frozen corrected P2 metric |
| Stage-2 RMSE and each-path headroom | `0.15560477763641264` | `FROZEN_EVIDENCE_DERIVED` | Controlling 2× formula applied to corrected P2 BEST-K |
| Median headroom | `0.23340716645461895` | `FROZEN_EVIDENCE_DERIVED` | Controlling 3× formula applied to corrected P2 BEST-K |
| Time-confound R² maximum | `0.10` | `FROZEN_EVIDENCE_DERIVED` | Controlling P3 authority |
| Readout bootstrap | 10,000, seed `2026081503` | `FROZEN_EVIDENCE_DERIVED` | Controlling P3 authority |
| Array dimensions, layer, tau indices | implementation values | `PURE_IMPLEMENTATION_CONSTANT` | Exact representation/data-shape identities, not scientific thresholds |

Runtime commit and SHA bindings are cryptographic materialization fields, not
scientific numeric choices. The independently created pre-outcome and
authorization receipts bind the exact post-freeze HEAD without requiring a
tracked artifact to contain the SHA of its own commit.
| Cross-correlation sub-tick refinement bound | 1.0 tick | `PURE_IMPLEMENTATION_CONSTANT` | Structural clamp of `derivative_cross_correlation_lag`, which returns `best_integer_lag + offset` with `offset` hard-limited to [-1, +1]. Not searched: frozen reference attains a maximum per-trajectory departure of `0.392766`, leaving `0.607234` unused slack |
| Frozen reference FIR group delay (method 1) | `3.363631073825902` ticks, t95 `[3.1850024634276997, 3.5422596842241045]` | `FROZEN_EVIDENCE_DERIVED` | `p2_temporal_alignment_forensic_v0_1/impulse_response_raw.json`, 12 trajectories; reference only, `acceptance_gate: false` |
| Frozen reference cross-correlation lag (method 2) | `2.4597455789132974` ticks, t95 `[2.2587886058224114, 2.6607025520041834]` | `FROZEN_EVIDENCE_DERIVED` | `p2_temporal_alignment_forensic_v0_1/lag_multimethod_raw.json` method B over the same 12 trajectories; reference only |
| Superseded agreement rule violation margin | `0.7252568845144023` ticks | `FROZEN_EVIDENCE_DERIVED` | Distance by which the frozen reference fails mutual containment; the disjointness that falsified the superseded rule |
| Aggregate frozen kernel mode | tick `2` | `FROZEN_EVIDENCE_DERIVED` | `argmax(mean_kernel)`; equals `delay_best_k` in 12/12 frozen trajectories, which is what identifies the cross-correlation estimand as the kernel mode |
| Observed first-moment minus mode margin | `0.4100623006769153` ticks minimum over 12/12 | `FROZEN_EVIDENCE_DERIVED` | Recorded observation only, `observed_ordering_is_an_acceptance_gate: false`; imposing right-skew on a prospective measurement is not justified by 12 trajectories |

