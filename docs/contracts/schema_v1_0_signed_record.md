# MineOcclude Phase 1 Schema v1.0 Signed Record

## Status

Schema version: `1.0`

Freeze status: `FROZEN_FOR_PHASE_1`

Approval status: `APPROVED_FOR_PHASE_1_FREEZE`

Previous version: `0.1-draft`

Freeze date: 2026-07-21

This is the authoritative internal Phase 1 interface record unless a later
versioned migration supersedes it. It freezes interchange meaning; it does not
claim that later scientific implementation or evaluation is complete.

## Scope

The freeze covers:

- the Person A file ownership map and skeleton boundaries;
- universal identity and lifecycle rows;
- the C-to-A trajectory package;
- the A-to-B activation handoff;
- the B-to-A intervention request;
- the A-to-E rollout manifest and A/E run-artifact registry; and
- the Step 1.7 synthetic cross-role bundle, joins, integrity checks, and
  synthetic target, baseline, context, rollout, and measurement rows.

Real capture, model execution, oracle computation, probe fitting, baseline
science, intervention generation, detection, homography, SSIM, and scientific
displacement measurement remain outside this freeze.

## Authoritative file map

| Responsibility | Authoritative implementation | Contract/evidence |
|---|---|---|
| MineWorld adapter | `src/mineocclude/models/mineworld_adapter.py` | `docs/architecture/person_a_file_map.md` |
| Activation hooks | `src/mineocclude/activations/hooks.py` | file-map responsibility note |
| Frame-token pooling | `src/mineocclude/activations/pool.py` | file-map responsibility note |
| Activation storage | `src/mineocclude/activations/store.py` | file-map responsibility note |
| Intervention injection | `src/mineocclude/intervention/inject.py` | file-map responsibility note |
| MVP runner/config/environment | `scripts/run_mvp.py`, `configs/experiments/mvp.yaml`, `scripts/check_env.py`, `requirements.txt` | `docs/architecture/person_a_file_map.md` |
| Universal identity | `src/mineocclude/contracts/identity.py` | `docs/contracts/identity_v1.md`, `tests/contracts/test_identity.py` |
| C-to-A trajectory | `src/mineocclude/contracts/trajectory.py` | `docs/contracts/trajectory_v1.md`, `tests/contracts/test_trajectory_contract.py` |
| A-to-B activation | `src/mineocclude/contracts/activation.py` | `docs/contracts/activation_v1.md`, `tests/contracts/test_activation_contract.py` |
| B-to-A request | `src/mineocclude/contracts/intervention_request.py` | `docs/contracts/intervention_request_v1.md`, `tests/contracts/test_intervention_request_contract.py` |
| A-to-E rollout/registry | `src/mineocclude/contracts/rollout_registry.py` | `docs/contracts/rollout_registry_v1.md`, `tests/contracts/test_rollout_registry_contract.py` |
| Synthetic integration | `src/mineocclude/integration/synthetic_pipeline.py` | `tests/integration/test_synthetic_pipeline.py`, `tests/fixtures/integration/` |
| v1.0 freeze | shared `SCHEMA_VERSION` plus this record | `tests/contracts/test_schema_v1_freeze.py`, decision log |

No duplicate Person A scientific implementation location is authorized by this
record.

## Frozen identity and units

The primary model-analysis frame key is the explicit composite:

`trajectory_id + model_frame_idx`

Source joins retain `episode_id`, `server_tick`, `render_frame_idx`, and
`action_idx`; indices are non-negative, zero-based integer indices. File order,
directory order, and filename meaning are never identity.

| Field/concept | Frozen unit or interpretation |
|---|---|
| `server_tick` | authoritative server ticks at 20 Hz (`0.05` seconds per tick) |
| media dimensions | pixels; exactly `640 x 360` |
| media rate | frames per second; exactly `20` Hz |
| `tau`, `duration` | seconds |
| `v` | blocks per second |
| `q` | blocks squared per second |
| true/mean/intended/measured displacement | blocks |
| variance | blocks squared |
| standard deviation | blocks |
| `alpha_requested`, `alpha_applied` | signed raw-activation direction coordinate; multiplied by a raw-space unit direction |
| `max_relative_activation_norm` | dimensionless ratio |
| layer, timestep, frame, row, and token positions | zero-based integer indices |
| content hashes | lowercase or uppercase hexadecimal SHA-256 where the validator permits hexadecimal case |

An intended block shift is a requested dose target, not a measured displacement.
Non-persistence and generation failure never imply zero displacement.

## Frozen allowed values and meanings

- Every accepted Phase 1 document uses `schema_version = "1.0"`.
- Lifecycle is `accepted`, `excluded`, or `superseded`, with the nullability and
  lineage rules implemented by the universal identity validator.
- `layout_id`, `regime`, `visibility`, and project owner names are non-empty,
  configuration-declared identifiers whose vocabulary is bound to hashes.
- Trajectory media mode is `mp4` or `numbered_frames`; required media and stream
  formats, normalized action field names, and capture orientation are those in
  the trajectory contract.
- MineWorld token structure is 336 visual tokens and 11 action tokens, for 347
  positions per frame/action pair. The frozen model window has 16 frames, layers
  are 0 through 19, and activation vectors have shape `[2048]`.
- Activation dtypes are `float16`, `bfloat16`, `float32`, and `float64`; run
  status is `completed`, `partial`, or `failed`.
- Intervention direction space is exactly `raw_activation`. The exported
  direction is approximately unit norm under the contract tolerances.
  `time_orthogonalization_checked` and `raw_space_equivalence_verified` are
  true; `near_zero_residual_detected` is false.
- Rollout controls are `intervention`, `alpha_zero`, and `random_direction`.
- Rollout outcomes are `measurable_continuation`, `non_persistence`, and
  `generation_failure`, with distinct output, measurability, and lifecycle
  semantics.
- Registry run status is `completed`, `completed_with_failures`, or `failed`.
  Registry artifact types are `input_context`, `intervention_request`,
  `rollout_clip`, `partial_rollout`, and `diagnostic_log`.
- Requested/applied alpha equality uses the validator's relative and absolute
  tolerance of `1e-12` when a dose is not cap-reduced.

## Filters and exclusion policy

- The trajectory adapter rejects capture mismatch and emits reason codes; it
  does not repair, interpolate, reorder, or infer missing capture data.
- Activation extraction selection cannot depend on targets, held-out labels,
  or downstream outcomes. Only accepted identity rows enter accepted handoffs.
- Intervention requests reject standardized exports, unverified raw-space
  equivalence, test-selected directions, split overlap, near-zero residuals,
  missing time checks, incomplete metadata, or illegal cap behavior.
- Rollout and registry rows preserve accepted, excluded, and superseded states.
  Generation failure is excluded and output-null; non-persistence can retain an
  output clip but remains non-measurable as displacement.
- Synthetic evidence is marked `synthetic = true` and
  `scientific_use = "forbidden"`; it cannot support scientific claims.

## Cardinality and join law

- Universal model-analysis rows are unique on
  (`trajectory_id`, `model_frame_idx`) within a table unless a role contract
  explicitly adds dimensions.
- Trajectory streams have equal cardinality and identical capture keys, with
  unique IDs and consecutive authoritative ticks.
- Activation identity adds `layer_idx` and `hook_site`; chunk row indices and
  exact per-layer/site coverage must match the cardinality report.
- Intervention dose IDs and held-out event IDs are unique. Fit, validation, and
  held-out event sets are disjoint.
- Rollout, run, and artifact IDs are unique. Each rollout resolves to exactly
  one producing run, its direct input context and request, and, when output
  bearing, exactly one output artifact. Parent and supersession graphs are
  acyclic and preserved.
- Person E synthetic measurements resolve exactly once to rollouts. Measurable
  continuation may have numeric displacement; non-persistence and generation
  failure require null displacement.
- The Step 1.7 acceptance gate is 4 real contracts, 13 explicit joins, 9
  integrity checks, and zero explicitly enumerated orphan claim-bearing rows.

## Rejection policy

Validators return machine-readable rejection codes, fail closed on malformed
types, do not mutate submitted data, and never silently repair or convert an
incompatible record. Producers must correct and resubmit rejected evidence.
Changing a rejection rule in a way that changes accepted scientific rows is a
result-changing schema change.

## Migration policy

After this freeze, any result-changing change to required fields, units,
allowed values, semantic meaning, filtering, cardinality, join identity,
hashing, tolerances, or lifecycle behavior requires:

1. a new schema version;
2. a documented migration and compatibility decision;
3. regenerated fixtures and validation evidence; and
4. a new run identity for every run produced under the changed meaning.

Old artifacts and supersession lineage remain auditable. They are never edited
in place to appear compliant with the new contract.

## Approval and sign-off

| Role | Approval recorded for Phase 1 interface meaning |
|---|---|
| Person A | `APPROVED_FOR_PHASE_1_FREEZE` |
| Person B | `APPROVED_FOR_PHASE_1_FREEZE` for activation/request interface meaning and units |
| Person C | `CONFIRMED_PRODUCER_CONSUMER_COMPATIBILITY` for trajectory production |
| Person D | `CONFIRMED_PRODUCER_CONSUMER_COMPATIBILITY` for synthetic baseline joins |
| Person E | `CONFIRMED_PRODUCER_CONSUMER_COMPATIBILITY` for rollout, registry, and measurement consumption |

These role labels record the repository's internal Phase 1 contract approval.
They do not represent external mentor, ethics, publication, or empirical-result
approval.

Approval declaration: `APPROVED_FOR_PHASE_1_FREEZE`.
