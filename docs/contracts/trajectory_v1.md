# MineOcclude C→A Trajectory Contract

Current implementation version: `1.0`

Status: frozen for Phase 1 by the Step 1.8 internal schema sign-off.

## Purpose

This contract defines exactly what Person C must provide before Person A accepts a captured trajectory for MineWorld processing.

Person A validates every submitted trajectory package strictly.

Person A does not:

* invent missing rows
* duplicate frames
* duplicate actions
* interpolate missing data
* reorder mismatched data to make it fit
* use nearest-timestamp matching to repair synchronization
* silently remove invalid rows
* coerce malformed values into valid values

A package that violates the contract is rejected with one or more machine-readable reason codes.

## Producer and consumer

Producer:

* Person C — data collection and capture pipeline

Consumer:

* Person A — MineWorld model and integration pipeline

Person C owns capture correctness before handoff.

Person A owns validation of the received package against this interface.

## Package-level identity

Every trajectory package requires:

* `schema_version`
* `episode_id`
* `trajectory_id`
* `seed`

The current package schema version is:

`1.0`

## Media requirement

Each accepted trajectory must provide either:

1. one MP4 recording, or
2. one authoritative numbered-frame sequence

The capture specification is:

* width: `640`
* height: `360`
* capture rate: `20 Hz`

The media descriptor requires:

* `mode`
* `path`
* `width`
* `height`
* `fps`
* `frame_count`
* `sha256`

Allowed media modes are:

* `mp4`
* `numbered_frames`

For MP4 capture, the path must end in `.mp4`.

The media SHA-256 value must be a 64-character hexadecimal value.

The current contract validates the declared media metadata.

Physical file existence, real decoded frame count, actual video resolution, actual frame rate, and hashes recomputed from the real files remain runtime validation responsibilities when Person A validates a real capture package.

## Required capture artifacts

A trajectory package must describe all of the following artifacts.

### Raw actions

Required artifact name:

`raw_actions`

Required format:

`jsonl`

This preserves the original captured action data.

### Normalized MineWorld actions

Required artifact name:

`normalized_actions`

Required format:

`jsonl`

This contains actions represented in the agreed normalized MineWorld-compatible form.

The original raw actions remain preserved so action conversion can be audited.

### Authoritative server state

Required artifact name:

`server_state`

Required format:

`jsonl`

This records authoritative Minecraft server-side state associated with each capture identity.

### Client tick log

Required artifact name:

`client_tick_log`

Required format:

`jsonl`

This preserves corresponding client-side tick information for synchronization evidence and capture diagnostics.

### Frame map

Required artifact name:

`frame_map`

Required format:

`jsonl`

The frame map is the authoritative mapping between:

* episode
* trajectory
* server tick
* rendered frame
* action
* model-frame position

### Visibility

Required artifact name:

`visibility`

Required format:

`jsonl`

This records the visibility state associated with every capture identity.

Visibility is a non-empty, configuration-declared value whose vocabulary and
meaning are bound to the package `config_hash`.

### Capture configuration

Required artifact name:

`config`

Required format:

`json`

This records the capture configuration used to produce the trajectory.

### Seed and noise draws

Required artifact name:

`seed_noise`

Required format:

`jsonl`

This preserves the package seed and the recorded noise draw associated with each capture identity.

### Diagnostics

Required artifact name:

`diagnostics`

Required format:

`json`

This records capture-side diagnostic information required for later auditing.

## Artifact descriptor requirements

Every required artifact descriptor contains:

* `path`
* `format`
* `sha256`

The declared format must match the contract.

The SHA-256 value must be a 64-character hexadecimal value.

The current contract validates the descriptor itself.

Actual file existence and recomputation of hashes from real artifact bytes remain runtime validation responsibilities for real handoff packages.

## Row streams

The current structural validator requires the following row streams:

* `frame_map`
* `raw_actions`
* `normalized_actions`
* `server_state`
* `client_tick_log`
* `visibility`
* `seed_noise`

Each stream must contain one row for every accepted media frame.

## Row payload requirements

In addition to carrying the shared capture identity, each row stream has stream-specific payload requirements.

### `frame_map`

Each row contains the complete capture identity:

* `episode_id`
* `trajectory_id`
* `server_tick`
* `render_frame_idx`
* `action_idx`
* `model_frame_idx`

The four index fields must be non-negative integers.

### `raw_actions`

Each row must contain:

* `raw_action`

`raw_action` must be a non-empty mapping.

The exact Person C raw-action field vocabulary may be tightened through the cross-role review, but null, empty, or non-structured raw action records are not accepted.

### `normalized_actions`

Each row must contain:

* `normalized_action`

`normalized_action` must be a mapping containing:

* `camera_component_0`
* `camera_component_1`
* `hotbar`
* `forward_back`
* `left_right`
* `sprint_sneak`
* `use_attack`
* `jump`
* `drop_pick_item`

Every current normalized-action component must be represented as an integer.

Schema v1.0 freezes these fields as explicit integers produced by the converter
identified by the package's code/config/preprocess hashes. The contract does
not infer, clip, or silently convert values. Changing component meaning or
converter semantics is result-affecting and requires migration.

### `server_state`

Each row must contain:

* `state`

`state` must be a non-empty mapping.

The non-empty `state` mapping is the authoritative producer payload. Its
experiment-specific keys and meanings are configuration-declared and hash
bound; changing them in a result-affecting way requires migration.

### `client_tick_log`

Each row must contain:

* `client_tick`

`client_tick` must be a non-negative integer.

### `visibility`

Each row must contain:

* `visibility`

`visibility` must be a non-empty string.

The visibility value uses the same configuration-declared, hash-bound
vocabulary as the universal identity contract.

### `seed_noise`

Each row must contain:

* `seed`
* `noise_draw`

`seed` must be an integer and must agree with the package-level seed.

`noise_draw` must be a finite numeric value.

## Capture identity types

Every row-level capture identity requires:

* `episode_id`: non-empty string
* `trajectory_id`: non-empty string
* `server_tick`: non-negative integer
* `render_frame_idx`: non-negative integer
* `action_idx`: non-negative integer
* `model_frame_idx`: non-negative integer

Malformed identity values are rejected rather than coerced.

For example, the string `"100"` is not accepted as an integer server tick.

## Shared capture identity

Every row in every row-level stream carries:

* `episode_id`
* `trajectory_id`
* `server_tick`
* `render_frame_idx`
* `action_idx`
* `model_frame_idx`

The strict capture identity is therefore:

`episode_id + trajectory_id + server_tick + render_frame_idx + action_idx + model_frame_idx`

All row streams must contain exactly the same capture identities as the authoritative `frame_map`.

The order in which rows appear must not be used to infer correspondence.

## Package identity consistency

Every row must agree with the package-level:

* `episode_id`
* `trajectory_id`

Rows in `seed_noise` must also agree with the package-level `seed`.

## Equal-cardinality rule

For an accepted package, each required row stream must contain exactly:

`media.frame_count`

rows.

For example, if:

`media.frame_count = 100`

then every required row stream must contain exactly 100 corresponding rows.

A mismatch causes rejection.

The validator does not truncate longer streams or fill shorter streams.

## Unique-identity rule

The authoritative `frame_map` must not contain duplicate capture identities.

Within one trajectory, the following values must also be unique in the current contract:

* `server_tick`
* `render_frame_idx`
* `action_idx`
* `model_frame_idx`

Every additional row stream must also contain unique capture identities.

Duplicate identities cause rejection.

## Consecutive-server-tick rule

When the authoritative `frame_map` is ordered by `model_frame_idx`, accepted server ticks must advance exactly one tick at a time.

Example accepted sequence:

`100, 101, 102, 103`

Example rejected sequence:

`100, 101, 103, 104`

The validator does not create the missing tick or repair the sequence.

## Camera impulse-orientation requirement

The meaning of the indexed MineWorld camera components must be verified using an impulse-orientation fixture rather than inferred from variable names or UI labels.

The trajectory package requires an `impulse_orientation` record containing:

* `status`
* `fixture_id`
* `camera_component_0_observed_effect`
* `camera_component_1_observed_effect`
* `evidence_hash`

For acceptance:

`status` must equal `verified`.

Both observed effects must be explicitly recorded.

The evidence hash must be a valid SHA-256 value.

The synthetic fixture used during Step 1.3 proves only the contract mechanics.

It does not establish the real MineWorld camera-axis orientation.

The real orientation must be established from the later controlled impulse test against the pinned MineWorld implementation.

## Malformed-input safety

Invalid external packages must produce structured rejection records rather than uncaught Python type errors.

The validator performs type checks before operations such as:

* numeric comparison
* arithmetic
* sorting
* path string operations
* identity construction

Malformed package content is rejected and left unchanged.

The validator does not attempt to coerce invalid types into valid values.

## Rejection behavior

A rejected package remains unchanged.

Validation produces explicit machine-readable rejection records.

The validator does not mutate or repair the submitted package.

## Rejection codes

### `missing_required_field`

A required package or row field is absent.

### `invalid_schema_version`

The package uses a schema version other than the currently accepted contract version.

### `invalid_media_spec`

The declared capture media violates the required media specification or uses malformed media metadata.

### `missing_artifact`

A required artifact descriptor is absent.

### `invalid_artifact_descriptor`

A required artifact has an invalid path, format, or descriptor structure.

### `invalid_hash`

A declared SHA-256 value has an invalid format.

### `missing_stream`

A required row stream is absent or is not represented as the expected list structure.

### `invalid_identity_type`

A package or row identity field exists but has an invalid type or value.

Examples include:

* a string-valued server tick
* a negative frame index
* a null trajectory identifier

### `invalid_row_payload`

A row exists but its stream-specific payload has an invalid type, structure, or required value.

Examples include:

* a null normalized action
* an empty raw action mapping
* a null authoritative state
* a string-valued client tick
* a non-finite noise draw

### `cardinality_mismatch`

A required row stream does not contain exactly the declared number of media frames.

### `duplicate_identity`

A capture identity or required unique index is duplicated.

### `identity_mismatch`

A row or stream does not match the package identity or authoritative frame-map identity set.

### `non_consecutive_server_ticks`

The authoritative server-tick sequence contains a gap or invalid progression.

### `impulse_orientation_unverified`

Camera-axis orientation evidence exists but has not been marked verified.

### `impulse_orientation_incomplete`

Required camera-axis orientation evidence is absent or incomplete.

## Accepted synthetic fixture

Step 1.3 provides:

`tests/fixtures/trajectory/accepted_package.json`

This fixture is synthetic and non-scientific.

It demonstrates a package that satisfies the current structural C→A contract.

## Rejected synthetic fixtures

Step 1.3 provides intentionally invalid packages for:

* cardinality mismatch
* non-consecutive server ticks
* duplicate identity
* unverified camera orientation
* mismatched stream identity
* invalid capture identity type
* invalid normalized-action payload
* malformed media metadata
* invalid authoritative state
* invalid client tick

These fixtures are:

* `rejected_cardinality.json`
* `rejected_nonconsecutive_tick.json`
* `rejected_duplicate_identity.json`
* `rejected_impulse_orientation.json`
* `rejected_mismatched_stream_identity.json`
* `rejected_invalid_identity_type.json`
* `rejected_invalid_payload.json`
* `rejected_malformed_media.json`
* `rejected_invalid_state.json`
* `rejected_invalid_client_tick.json`

Each rejected fixture must fail with its intended rejection reason.

## Validator expectations

The validator must:

1. Accept the known-good synthetic package.
2. Reject cardinality mismatch.
3. Reject non-consecutive authoritative server ticks.
4. Reject duplicate identities.
5. Reject mismatched stream identities.
6. Reject malformed capture identity types.
7. Reject invalid stream payloads.
8. Reject malformed media metadata without crashing.
9. Reject unverified impulse-orientation evidence.
10. Return explicit machine-readable rejection codes.
11. Leave submitted packages unchanged.
12. Never repair or coerce malformed capture data.

## Current automated verification

The current Step 1.3 tests verify:

* the accepted synthetic package passes
* stream cardinality mismatches are rejected
* non-consecutive server ticks are rejected
* duplicate identities are rejected
* mismatched stream identities are rejected
* invalid capture identity types are rejected
* invalid normalized-action payloads are rejected
* invalid authoritative state payloads are rejected
* invalid client ticks are rejected
* malformed media metadata is rejected without crashing
* unverified camera orientation is rejected
* every accepted stream carries the same frame-map identities
* validation does not mutate the submitted package

The complete contract test suite currently contains:

* 14 universal identity tests
* 13 C→A trajectory-contract tests

Total:

`27 tests`

## Scope boundary

This C→A contract does not define:

* the A→B activation contract
* the B→A intervention contract
* the A→E rollout contract
* the run/artifact registry contract
* the full Step 1.7 cross-role synthetic pipeline

Those are defined in their respective later Phase 1 steps.

## Versioning status

The current implementation is frozen schema `1.0`. Result-changing changes to
fields, units, allowed values, filters, cardinality, or meaning require a
versioned migration and a new run identity under the Phase 1 signed record.
