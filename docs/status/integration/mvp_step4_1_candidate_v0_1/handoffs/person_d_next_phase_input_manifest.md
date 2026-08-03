# Person D next-phase input handoff

Status: ready. The machine-readable authority is `person_d_next_phase_input_manifest.json`.

The handoff freezes Person B's exact five-fold membership and 1,695-row evaluation universe, activation-aligned sample identities, oracle targets, baseline input schema `person-b-baseline-input-v0.2`, applicability contract `person-b-step4-1-family-target-applicability-v0.1`, production leakage controls, current Registry v2 receipts, and the Step 4.1 `FAIL` decision.

| Input group | Active repository authority | Frozen |
| --- | --- | --- |
| Fold membership and row universe | `docs/status/person_b_phase4_step4_1_production_handoff_v0_1/ten_pilot_frame_fold_manifest.json` | Yes |
| Activation-aligned samples and oracle targets | Person B production handoff manifests | Yes |
| Baseline, applicability, and leakage contracts | Person B current v0.2 baseline and production contracts | Yes |
| U4 control matrix | `src/mineocclude/baselines/u4_control_matrix.py`, with frozen intervention-request v1.0 dependency | Yes |
| Registry v2 references | Person D trust evidence plus Person E closure receipt | Yes |
| Step 4.1 decision | `docs/status/person_b_phase4_step4_1_final_comparison_completion_v0_1/layer_band_decision.json` | Yes: `FAIL` |

Only the U4 control-matrix contract is an input. U4 outputs are not inputs and were not inspected; the accepted Person D receipt records `u4_input_used=false` and zero cross-fold leakage.

No blocking required input is missing.

`PERSON_D_NEXT_PHASE_HANDOFF_READY=True`
