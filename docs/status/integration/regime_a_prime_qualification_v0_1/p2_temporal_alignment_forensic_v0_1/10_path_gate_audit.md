# 10 — Path/State Gate Authority-Scope Audit

**Label: EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY.** Script: `audit_scripts/b10_path_gate_blast_radius.py`.

## Claim under test
The prior P3 audit reported `PATH_IMPLEMENTATION_MATCHES_AUTHORITY = false`, describing the
implementation as narrower than authority while the historical verdict remained correct. Both
halves were re-verified independently.

## Authority vs implementation

`p3_preoutcome_authority.json → path_and_state_gate` declares 13 `exact_fields` and
`rows_checked_per_scene_per_candidate: 4500`.

`p3_run_sequential.py::non_neural_gates` verified **two** things:
1. `sha256` of the `<f8` byte image of the **`sheep_x` column only**, vs `expected_path_sha256`;
2. `np.array_equal(NORMAL.sheep_x, NO_WALL.sheep_x)`.

The remaining identity fields were asserted inside `derive_artifacts` at **capture** time, so a
**resumed or reused durable unit was never re-checked** — and 41 of C01's 50 units were in fact
reused across a restart. No row count was computed or recorded anywhere.

**`PATH_IMPLEMENTATION_MATCHES_AUTHORITY = false` — CONFIRMED (scope).**

## Blast radius — measured on all 150 historical units

Twenty authority-scope invariants were re-checked on every unit of every candidate
(9,000 state rows per candidate; 27,000 total):

| Check | C01 | C02 | C03 |
|---|---|---|---|
| `sheep_x_sha` | 50/50 | 50/50 | 50/50 |
| `paired_x_equal` | 25/25 | 25/25 | 25/25 |
| `sheep_y_const`, `sheep_z_const` | 50/50 | 50/50 | 50/50 |
| `camera_eye_xyz`, `camera_bitwise_constant`, `camera_yaw_pitch` | 50/50 | 50/50 | 50/50 |
| `tick_dense`, `tick_order` | 50/50 | 50/50 | 50/50 |
| `scene_field`, `seed_field`, `spec_hash_field`, `spec_id_field` | 50/50 | 50/50 | 50/50 |
| `q_field`, `v_field`, `v_sign_matches_direction`, `commanded_v_field` | 50/50 | 50/50 | 50/50 |
| `respawn_zero`, `uuid_single`, `row_count` | 50/50 | 50/50 | 50/50 |

**BLAST RADIUS = ZERO.** A complete authority-scope gate would have returned `PASS` for all
three candidates, exactly as the historical gate did. `rows_checked` is 9,000 per candidate,
matching the authority's declared 4,500 per scene.

## Two apparent failures that were NOT defects (recorded so they are not re-reported)

A first pass of this audit flagged two checks as failing. Both were artifacts of the audit
check, not of the pipeline, and were falsified before being reported:

1. **`camera_eye_xyz` 0/50.** The authority stores the eye height as `5.6200000048`, a 10-decimal
   rounding of the true float `5.620000004768372` (Δ = 3.16 × 10⁻¹¹). Exact equality against the
   stored constant is not a meaningful test. *This is a genuine but minor **documentation**
   finding*: an authority that demands "exact_fields" should not store a rounded constant. The
   repair compares within the rounding **and** separately requires the camera to be bitwise
   constant across the run.
2. **`v_field` 26/50.** `server_state.v` is the **signed** commanded velocity; the spec records
   **unsigned** `speed_blocks_per_second` plus a separate `direction`. 26/50 is exactly the 13
   LEFT_TO_RIGHT specs × 2 scenes. The repair compares magnitude and checks the sign against the
   spec direction.

## Repair (future-facing only)
`src/mineocclude/prospective/path_state_gate.py` checks the complete named scope, including
run/episode/spec and target identity, noise schedule, camera eye/yaw/pitch/FOV, and exact
server/render/action/model mapping, on **every** unit, **every** time (including resumed units).
It reports `rows_checked` and verifies paired field equality at ε = 0.

Tests: `tests/prospective/test_path_state_gate.py`, including a parametrised case per
authority field asserting that a single-row violation is detected — **every one of which would
have passed the historical two-field gate** — plus explicit regression tests for the camera
rounding and signed-velocity traps above.
