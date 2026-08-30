# Final pre-implementation audit — Experiment III

**Authority:** `docs/experiment_iii/final_authorities/` `v1.4`
**Date:** 2026-08-30  ·  **Verdict:** `FINAL_AUDIT_STATUS = PASS`, `IMPLEMENTATION_GO = true`

```
machine checks     2401 / 2401
independent checks  132 / 132     (reconstructed from source, git objects and formulas)
regression checks    89 / 89
blocking defects      0
```

## What was reconstructed independently, not read back

| Claim | Method | Result |
|---|---|---|
| FIR kernel recovery | re-solved least squares from git commit `f2bc2c8` | 50/50 path hashes, rank 9, residuals ≤ 1e-12, taps match to 10 dp |
| FIX-3 drift-before-noise | re-ran both operand orders | noise-first reproduces 0/50 |
| Oracle `H`, `S(τ)`, `gbar`, `c` | recomputed from fsum-normalized taps | exact to `0.0`; unnormalized LTR fails 1e-12 |
| Affine boundary | derived from `c_direction` | LTR last-negative 4, RTL 3, no integer zero |
| σ table and `q` ratio | `sqrt(q·dt·S(τ))` | exact; ratio 4.0 at every τ |
| Generator law | live `noise_schedule.py`, `SheepController.java` | `std=sqrt(q·dt)`, `z ⟂ q`, drift-then-noise, then clamp |
| D.2 reference | retrieved v0_3 manifest from git | blob/bytes/sha256/unit match; hash regenerates |
| D.11 fixture | rebuilt and executed | zero-`q` exact; `ρ|τ = 0.0905724833`; residual var `0.0 ≤ TOL`; mapped `ρ=0.0`, `p=1.0` |
| Implementation totals | resummed from 22 tasks + 3 buckets | 20.70 / 38.40 / 65.00 — exact |
| III-B incremental peak | rebuilt from byte primitives | 10.508 GiB |
| Storage coherence | recomputed | 64 − 48.796 = 15.204 ≥ 15 and 15 > 10.508 |
| Source closure | recomputed under the frozen path-field sort | matches `077236e7…` |

## Verdicts

- `A1_IMPLEMENTATION_TIME_MODEL_REPRODUCIBLE` = **PASS**
- `A2_ZERO_VARIANCE_U2_S2_DEFINED` = **PASS**
- `SCIENTIFIC_FEASIBILITY` = **PASS**
- `III_A_SCIENTIFIC_VALIDITY` = **PASS**
- `III_B_SCIENTIFIC_VALIDITY` = **PASS**
- `ORIGINAL_PROPOSAL_ALIGNMENT` = **PASS**
- `GUARANTEED_SCIENTIFIC_VALUE` = **PASS**
- `ORACLE_MATCHES_GENERATOR` = **PASS**
- `ORACLE_MATHEMATICS_VALID` = **PASS**
- `FIR_AUTHORITY_VALID` = **PASS**
- `Q_GRID_VALID` = **PASS**
- `Q_PAIRING_VALID` = **PASS**
- `Q_MID_REGRESSION_PROTECTED` = **PASS**
- `U2_IDENTIFICATION_VALID` = **PASS**
- `U2_STATISTICS_VALID` = **PASS**
- `D11_NEGATIVE_CONTROL` = **PASS**
- `U3_IDENTIFICATION_VALID` = **PASS**
- `U3_STATISTICS_VALID` = **PASS**
- `CALIBRATION_PLAN_VALID` = **PASS**
- `NEGATIVE_SIGMA_HANDLING_DEFINED` = **PASS**
- `COHORT_VALID` = **PASS**
- `FOLDS_VALID` = **PASS**
- `NO_IDENTITY_LEAKAGE` = **PASS**
- `TARGET_SELECTION_VALID` = **PASS**
- `CONTEXT_BOUNDARY_VALID` = **PASS**
- `TOKEN_SLICE_INDEXING_VALID` = **PASS**
- `REPRESENTATION_CONSTRUCTION_VALID` = **PASS**
- `BASELINES_VALID` = **PASS**
- `VIS6_VALID` = **PASS**
- `WALL_CACHE_DEFECT_COVERED` = **PASS**
- `L0_PATH_DEFECT_COVERED` = **PASS**
- `RVE_CONTRACT_VALID` = **PASS**
- `WORKLOAD_ARITHMETIC` = **PASS**
- `STORAGE_FEASIBILITY` = **PASS**
- `IMPLEMENTATION_TIME_MODEL_REPRODUCIBLE` = **PASS**
- `DEADLINE_PLAN_VALIDATED` = **PASS**
- `IMPLEMENTATION_CHANGE_MAP_COMPLETE` = **PASS**
- `IMPLEMENTATION_TASK_GRAPH_VALID` = **PASS**
- `TEST_PLAN_COMPLETE` = **PASS**
- `BLOCKER_LOCALIZATION_COMPLETE` = **PASS**
- `RECOVERY_RESUME_COMPLETE` = **PASS**
- `LIVE_STATUS_COMPLETE` = **PASS**
- `EXPECTED_ARTIFACTS_COMPLETE` = **PASS**
- `AUTHORITY_SELF_CONTAINED` = **PASS**
- `MACHINE_HUMAN_AUTHORITY_CONSISTENT` = **PASS**
- `III_A_PROTECTED_FROM_III_B` = **PASS**
- `III_B_OPTIONALITY_VALID` = **PASS**
- `III_B_LAUNCH_GATE_OUTCOME_INDEPENDENT` = **PASS**
- `III_B_DROP_LADDER_OUTCOME_INDEPENDENT` = **PASS**
- `THURSDAY_HARD_STOP_ENFORCEABLE` = **PASS**

## Residual risk

The dominant risk is **implementation time**, not authority correctness. The agent compression
factor of 2.0 is an assumption, and it is the reason the §10.5 checkpoints key on observed
milestones rather than on the estimate. NORMAL is tight: it closes at best and nominal
implementation and does **not** close if implementation runs conservative — in which case plans
10.2 and 10.3 close with +5.37 h and +11.73 h, and III-B `CLEAN_SKIP` is the expected, pre-registered
outcome.

## Next action

Commit and freeze `docs/experiment_iii/final_authorities/`, record the freeze commit SHA, and begin
Phase 2 at that instant. Do not run another discretionary authority audit.
