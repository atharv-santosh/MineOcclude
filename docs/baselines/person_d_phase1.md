# Person D Phase 1 Baselines and Controls

Status: implemented and unit-tested against synthetic fixtures (92 D tests
passed on 2026-07-27); not yet run against real accepted rows, folds, or
oracle targets, except for a non-scientific real-data preview (see below).
See `docs/baselines/person_d_phase0.md` for the current ownership/dependency
record, `PERSON_D_ISSUE.md` for blockers, and
`docs/decisions/person_d_phase1_decision_log.md` for dated decisions.

Repository-side A/B compatibility is technically verified in
`docs/baselines/person_d_schema_v1_review.md`. Formal human approval by
Persons A and B for the Phase 0/1 interface checkpoint
(`80d41c5ca0e341263a7b0c683fae4b51be376c55`) is **COMPLETE**, recorded in
`docs/contracts/schema_v1_0_signed_record.md`. This covers only that exact
checkpoint's interface compatibility -- it does not cover real-data
baselines, final scientific comparisons, or the Step 4.3 positive-control
gate below, which remains unevaluated pending real no-wall data.

## Scope

Person D owns non-model baselines/floors/references/controls, leakage
diagnostics, and U4 control-matrix verification -- comparisons that let a
result be interpreted against something simpler than the real probe, not the
real probe or oracle themselves (those are Person B's).

## Module map

| Module | Role | Target(s) |
|---|---|---|
| `baselines/last_seen.py` | memory heuristic floor | `mu_oracle_blocks` only |
| `baselines/constant_velocity.py` | reference in Regime A, genuine baseline in Regime B | `mu_oracle_blocks` only |
| `baselines/shuffled.py` | grouped chance floor (trajectory-level derangement) | both |
| `baselines/time_only.py` | clock-substitution test | `log_sigma_oracle` only |
| `baselines/explicit_feature.py` | ceiling from known, non-privileged belief ingredients | `mu_oracle_blocks` only |
| `baselines/raw_pixel.py` | visual-leakage/scene-cue check | `mu_oracle_blocks` only |
| `baselines/visible_history_q.py` | fair same-information spread baseline | `log_sigma_oracle` only |
| `baselines/known_q_analytic.py` | privileged oracle-ceiling reference (`is_fair_baseline = False`) | `log_sigma_oracle` only |
| `baselines/controls.py` | no-wall (positive) / occluder-only (negative) control audits | n/a -- audits, not predictions |
| `baselines/random_weight.py` | architecture/random-feature decodability (deferred to Week 2) | `mu_oracle_blocks` only |
| `baselines/leakage.py` | metadata-only leakage diagnostics | n/a -- audits, not predictions |
| `baselines/u4_control_matrix.py` | U4 control-matrix completeness/norm/orthogonality audits | n/a -- audits, not predictions |
| `baselines/missingness.py` | consolidated accepted/missing tabulation and silent-exclusion/reason-code audit | n/a -- audits, not predictions |
| `baselines/capture_ingest.py` | joins Person C's real capture row streams into `TrajectoryContext`s (fold left `UNASSIGNED_FOLD` until a real B fold manifest exists) | n/a -- ingest adapter, not a baseline |
| `baselines/positive_control_gate.py` | Step 4.3 no-wall positive-control ridge/R^2/bootstrap gate; fails closed to `BLOCKED` on non-real `data_provenance` | n/a -- audits, not predictions |
| `baselines/export.py` | packages predictions into Person B's frozen consumer contract | n/a |
| `baselines/spec.py` | authoritative strict `BaselineSpec` and prediction schema | `mu_oracle_blocks` for the Phase 1 proof |
| `baselines/firewall.py` | exact pre-fit legal-feature selection and identity/provenance validation | n/a |
| `baselines/harness.py` | common B-fold/B-target/B-metric synthetic execution boundary | `mu_oracle_blocks` |

Every prediction-producing module returns
`list[mineocclude.baselines.interface.BaselineRow]`; `BaselineRow.applicable`
is `False` (with `prediction=None`) whenever a row's inputs are insufficient
to define a value -- never a fabricated zero.

`BaselineRow` is an internal execution representation, not a second public
schema. `mineocclude.baselines.spec.BaselineSpec` is the single strict D Phase
1 definition: it requires baseline name/version, B-owned target name, exact
legal features, outer-train fit scope, estimator, hyperparameter source,
seed, outputs, and A/B provenance. Unknown/missing fields, renamed baselines,
unsupported versions/features, altered fit scope, and malformed provenance
fail closed. The companion `person-d-baseline-prediction-v1.0` row requires
the exact `trajectory_id + model_frame_idx` key and out-of-fold fit identity.

## Legal-input firewall

`mineocclude.baselines.firewall.select_legal_inputs` executes before either
estimator method. It accepts only the exact feature list registered in the
validated `BaselineSpec` and produces a fresh selected mapping; target values,
hidden truth, q/oracle fields, future fields, layout-target hints, filenames,
paths, and arbitrary metadata therefore cannot reach estimator features.
Malformed/duplicate scientific identities and stale or malformed provenance
also fail before fit/predict. Tests use a spy estimator to prove neither
method is called after firewall rejection.

## Common synthetic harness

`mineocclude.baselines.harness.run_synthetic_baseline_harness` validates the
spec/firewall, calls B's `validate_fold_manifest`, requires exact input/target/
fold coverage, and takes one complete B-assigned outer fold as the requested
test set. Only the remaining identities reach fit. The held-out identities
reach predict, and exact prediction identity coverage is checked before the
current B-owned `metrics.u1_mean.regression_metrics` API is called.

The Phase 1 proof runs the existing `last_seen` and `constant_velocity`
implementations through this same boundary. Both emit strict prediction rows
for the identical requested `trajectory_id + model_frame_idx` set. Fit
metadata records train/test identities and hashes, fold/target/accepted
manifest hashes, config/preprocess/code provenance, seed, estimator,
hyperparameter source, and train-only preprocessing scope. This remains
synthetic contract evidence, not a real scientific result.

## Fold discipline

D never constructs or recomputes scientific fold membership. Every baseline
that needs folds reads `TrajectoryContext.fold`, populated by
`mineocclude.baselines.export.attach_b_fold_assignments` from a saved sealed
B-owned `fold_manifest`. The helper first calls B's authoritative
`validate_fold_manifest`, requires exact `trajectory_id + model_frame_idx`
coverage, rejects duplicate/conflicting identities and layouts, and copies
the recorded `fold_idx` unchanged. Phase 1 uses the explicitly synthetic
artifact at `tests/fixtures/person_d/synthetic_b_fold_manifest.json`.

## Handoff format

`mineocclude.baselines.export.build_baseline_document` packages one
target's applicable `BaselineRow`s into the `person-b-baseline-input-v0.1`
schema and `validate_document` checks the result against Person B's real
`mineocclude.contracts.analysis_inputs.validate_baseline_input` -- not a
paraphrase of it. One document covers exactly one `(baseline_id,
target_name)` pair; a baseline that cannot define every one of B's expected
frame keys for a target simply omits those keys rather than fabricating a
value, and coverage against B's expected key set is checked by passing
`expected_fold_by_frame` to `validate_document`.

## Step 4.3 status: implemented, UNEVALUATED

`controls.audit_no_wall_control` is only the structural half of Step 4.3
(every no-wall frame really is visible with `tau=0`). The scientific half --
fit the frozen visible-position ridge on no-wall rows and require held-out
R^2 >= 0.50 with a bootstrap CI strictly above zero -- is implemented in
`baselines/positive_control_gate.py`, calling Person B's real
`probes.ridge.fit_ridge_oof`, `metrics.u1_mean.regression_metrics`, and
`metrics.resampling` bootstrap primitives directly.

The gate's own status right now is **BLOCKED**, not passed and not failed:
real no-wall rows, a real Person B fold manifest, and real oracle targets do
not exist yet. `evaluate_no_wall_positive_control_gate` requires an explicit
`data_provenance` argument with no default; only the literal
`REAL_NO_WALL_DATA_PROVENANCE` unlocks a PASSED/FAILED verdict, so a
synthetic run can never be read as a satisfied gate.
`docs/status/person_d_step_4_3_positive_control_gate.json` records the
current BLOCKED run against synthetic fixtures -- this is machinery
evidence only. "Implemented" here must not be read as "passed."

## Wiring real data (once available)

- **Real folds:** provide B's persisted real `fold_manifest` to the same
  validator-backed `attach_b_fold_assignments` boundary. No D-side assignment
  or recomputation is permitted.
- **Real oracle targets:** supply `mu_oracle_by_key` /
  `mu_oracle_by_key`-shaped mappings (currently synthesized in tests) from
  Person B's real `oracle_targets.parquet`.
- **Real pixel features:** supply `pixel_features_by_key` to
  `raw_pixel.fit_predict_raw_pixel` from Person A's preprocessed frames.
- **Real random-weight activations:** supply
  `random_weight_activation_by_key` to
  `random_weight.fit_predict_random_weight` once Person A hands off a
  random-initialized-checkpoint activation extraction (Week 2).
- **Real visible-history sequences:** supply
  `visible_positions_by_trajectory` to
  `visible_history_q.fit_predict_visible_history_q` from Person C's
  authoritative visible-window state.
- **Real U4 control matrix:** call
  `u4_control_matrix.build_control_matrix` with Person B's real held-out
  event list and seed list, then audit against Person A's real rollout
  registry's control IDs and Person B's real fitted direction.
