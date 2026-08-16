# P3 Terminal Forensic Audit — Summary

**Label: EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY.** Read-only. No commit, no push, no capture, no authority change,
no existing file modified.

## Verdict in one paragraph
All three P3 development candidates failed the **same single predicate**: the pre-candidate visibility
**calibration precision** requirement (≥0.95), which they missed at 0.8468, 0.9155 and 0.9376. Capture, path,
headroom, the geometric component and recall passed for every candidate. That precision requirement compares
the server's **point-visibility** predicate (one ray to the target's centre point) against the detector's
**area-visibility** predicate (any magenta blob ≥19 px). These two quantities disagree over a ~1.04-block band
at the occlusion boundary — a band the project's own bound authority (`directional_visibility_authority_v2.1
amendment 1`) already records as a 17–19-frame "partial/disagreement run". Direct frame inspection shows the
target still **97 % visible** at the exact frame the server first labels it occluded. The requirement was
therefore **unsatisfiable by construction** in the tested range, and — because pooled precision is base-rate
dependent while the base rate is a direct function of the swept speed — it would have become satisfiable at
≈3.75 b/s **purely as a class-balance artifact**, with the detector↔geometry disagreement completely unchanged.
P3 failed for a gate-definition reason, not a scientific one.

## Handoff answers

| Field | Value |
|---|---|
| `AUDIT_STATUS` | `PASS_COMPLETE` |
| `P3_TERMINAL_RESULT_CONFIRMED` | `true` |
| `C01_FAILED_GATE` | `VISIBILITY → visibility_calibration.rendered_magenta_component_status = FAIL` (precision 0.846847 < 0.95). Target rows perfect 475/475 NORMAL + 475/475 NO_WALL |
| `C02_FAILED_GATE` | same calibration-precision failure (0.915459) **+** 1 contaminated NORMAL target row (`p3dev_c02_t21`, τ=1, tick 28, x = −3.7113) |
| `C03_FAILED_GATE` | same calibration-precision failure (0.937634) **+** 7 contaminated NORMAL target rows (t01, t06, t11, t16, t21; all τ∈{1,2}, all phase 0) |
| `P3_CONTROLLER_DECISION_REPRODUCED_INDEPENDENTLY` | `true` |
| `VISIBILITY_IMPLEMENTATION_MATCHES_AUTHORITY` | `false` |
| `PATH_IMPLEMENTATION_MATCHES_AUTHORITY` | `false` (narrower than specified; verdict nevertheless correct) |
| `HEADROOM_IMPLEMENTATION_MATCHES_AUTHORITY` | `true` |
| `DATA_INTEGRITY_STATUS` | `PASS` |
| `RUNTIME_RECOVERY_CONTAMINATION` | `false` |
| `P2_TO_P3_SEMANTIC_DRIFT` | `material` (entirely in the visibility gate) |
| `TOP_ROOT_CAUSE_1` | Gate definition: point-visibility vs area-visibility predicates scored against each other over a ~1.04-block band where disagreement is structural — **very high** |
| `TOP_ROOT_CAUSE_2` | Gate definition: pooled `precision` is base-rate confounded with the swept variable (FP-rate flat 0.118/0.104/0.103 while precision rose 0.847/0.915/0.938) — **very high** |
| `TOP_ROOT_CAUSE_3` | Apparatus: ≈3.3-server-tick render-vs-state temporal lag, measured directly from pixels — **high** |
| `SOFTWARE_DEFECT_FOUND` | `true` (none of which produced a wrong verdict) |
| `SCIENTIFIC_DESIGN_DEFECT_FOUND` | `true` (speed swept a variable that had already passed at C01) |
| `GATE_DEFINITION_DEFECT_FOUND` | `true` (primary cause) |
| `APPARATUS_DEFECT_FOUND` | `true` (render/state lag) |
| `DOES_EXISTING_P3_FAILURE_REMAIN_VALID` | `yes` — the labels are correct as the gate was written |
| `IS_SPEED_THE_RIGHT_REDESIGN_VARIABLE` | `no` |
| `NEW_CAPTURE_REQUIRED` | `true` |
| `NEW_PROSPECTIVE_AUTHORITY_REQUIRED` | `true` |
| `CONFIRMATORY_COLLECTION_AUTHORIZED` | `false` |
| `REGIME_A_PRIME_COLLECTION_AUTHORIZED` | `NO` |
| `CONTAMINATION_DETECTED` | `false` |
| `COMMIT_CREATED` | `false` |
| `PUSH_PERFORMED` | `false` |

## Key numbers

| | C01 (2.0 b/s) | C02 (2.5) | C03 (3.0) |
|---|---|---|---|
| captures | 50/50 | 50/50 | 50/50 |
| path / headroom | PASS / PASS | PASS / PASS | PASS / PASS |
| calibration precision | **0.846847** | **0.915459** | **0.937634** |
| calibration recall | 0.979167 | 0.989556 | 0.995434 |
| **FP-rate on occluded rows** | **0.1181** | **0.1039** | **0.1028** |
| visible base rate | 0.4000 | 0.5319 | 0.6083 |
| NORMAL target rows clean | **475/475** | 474/475 | **468/475** |
| headroom min / median SD | 0.4187 / 0.5683 | 0.5930 / 0.7071 | 0.6811 / 0.8235 |

Note the two diverging trends: calibration precision **improves** with speed while scientific target-row purity
**degrades**. No speed satisfies both halves of the P3 visibility gate as written.

## Documents
`00_evidence_inventory.json` · `01_experiment_reconstruction.md` · `02_gate_traceability.md` ·
`03_visibility_forensics.md` + `03_visibility_boundary_frames_c01_ltr.png` · `04_candidate_comparison.json` ·
`05_p2_vs_p3_delta.md` · `06_git_regression_audit.md` · `07_runtime_recovery_audit.md` ·
`08_exploratory_counterfactuals.md` · `09_bug_hypothesis_log.md` · `10_root_cause_matrix.md` ·
`11_scientific_interpretation.md` · `12_redesign_options.md` · `audit_scripts/` (9 deterministic scripts).

## Next allowed action
Draft — do **not** yet freeze — a corrected prospective visibility authority per `12_redesign_options.md`
(Option B, then A), holding speed at the already-qualified v = 2.0 b/s and holding the apparatus, detector
config and P2-derived thresholds unchanged. Nothing may be captured until that authority is frozen.
