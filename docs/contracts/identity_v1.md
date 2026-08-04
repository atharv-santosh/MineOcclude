# MineOcclude Universal Identity Contract

Current implementation version: `1.0`

Status: frozen for Phase 1 by the Step 1.8 internal schema sign-off.

## Purpose

The universal identity contract allows frames, actions, authoritative state,
targets, activations, predictions, and rollouts to be connected through
explicit identifiers rather than file order, directory order, or row position.

This document defines only the shared identity foundation.

The full C→A, A→B, B→A, A→E, and registry contracts are defined in later
Phase 1 steps.

## Shared model-analysis key

The shared frame-level projection is:

- `trajectory_id`
- `model_frame_idx`

Together, these identify one model-analysis frame within one trajectory.

Individual downstream tables may extend this key with table-specific fields.

For example, an activation contract may later include additional identity such
as layer or hook site because one model frame can legitimately produce multiple
activation rows.

## Source identity

The universal contract retains:

- `episode_id`
- `trajectory_id`
- `server_tick`
- `render_frame_idx`
- `action_idx`
- `model_frame_idx`

These fields allow model-analysis outputs to be traced back to the original
recording and authoritative Minecraft timeline.

## Identity meanings

### `episode_id`

Identifies the source Minecraft episode or recording session.

### `trajectory_id`

Identifies one model-analysis trajectory or context derived from an episode.

### `server_tick`

Identifies the authoritative Minecraft server tick associated with the frame.

### `render_frame_idx`

Identifies the corresponding recorded image or video frame.

### `action_idx`

Identifies the corresponding recorded action entry.

### `model_frame_idx`

Identifies the frame's position inside the model-analysis trajectory.

## Experimental condition identity

Claim-bearing rows currently retain:

- `layout_id`
- `regime`
- `visibility`
- `tau`
- `v`
- `q`
- `duration`

The frozen validator requires:

- `layout_id`, `regime`, and `visibility` to be non-empty strings.
- `tau`, `v`, `q`, and `duration` to be non-null finite numeric values.
- `tau` to be non-negative.
- `duration` to be non-negative.

The frozen units are:

- `tau`: seconds.
- `v`: blocks per second.
- `q`: blocks squared per second.
- `duration`: seconds.

`layout_id`, `regime`, and `visibility` are non-empty, configuration-declared
identifiers. Their project-specific vocabularies are bound to `config_hash`
rather than duplicated in this universal contract. A result-affecting change
to a vocabulary or its meaning requires the migration policy and a new run
identity.

## Provenance

Claim-bearing rows retain:

- `code_sha`
- `config_hash`
- `model_hash`
- `preprocess_hash`
- `seed`
- `schema_version`
- `run_id`

These fields make outputs traceable to the code, configuration, model,
preprocessing path, random seed, schema version, and producing run.

### Hash formats

`code_sha` must be a 40-character hexadecimal Git commit SHA.

`config_hash`, `model_hash`, and `preprocess_hash` must be 64-character
hexadecimal SHA-256 values.

The synthetic test fixtures use correctly formatted placeholder values and must
never be interpreted as hashes of real project artifacts.

## Lifecycle status

Allowed states are:

- `accepted`
- `excluded`
- `superseded`

### Accepted

An accepted row is currently valid for its intended downstream use.

An accepted row must have:

- `exclusion_reason = null`
- `superseded_by = null`

### Excluded

An excluded row is preserved for auditability but is not accepted for its
intended downstream use.

An excluded row must contain a non-empty `exclusion_reason`.

An excluded row must have:

- `superseded_by = null`

### Superseded

A superseded row was previously produced but has been replaced by a newer
artifact or run.

A superseded row must contain a non-empty `superseded_by` value identifying
the newer artifact or run that replaces it.

A superseded row must have:

- `exclusion_reason = null`

Excluded and superseded records are preserved for auditability rather than
silently deleted.

## Nullability

The universal fields defined by the frozen contract must always exist.

The following fields are conditionally nullable:

- `exclusion_reason`
- `superseded_by`

`exclusion_reason` is null except for excluded records.

`superseded_by` is null except for superseded records.

The frozen contract requires `tau`, `v`, `q`, and `duration` to contain explicit
finite numeric values rather than null values.

## Uniqueness

At the universal model-frame level, the combination:

`trajectory_id + model_frame_idx`

must be unique.

Table-specific contracts may extend this key when one model frame legitimately
produces multiple rows.

For example, the later activation contract may require a more specific key that
also includes activation-specific identity.

## Trajectory consistency

Rows sharing the same `trajectory_id` must currently agree on:

- `episode_id`
- `layout_id`
- `seed`

Frame-varying fields such as `visibility` and `tau` are intentionally not
required to remain constant across a trajectory.

Additional trajectory-level invariants may be defined by later role-specific
contracts.

## Join rule

Rows must be matched using explicit identity keys.

Directory order, filename order, and row position must never be used as
scientific join logic.

The Step 1.2 synthetic tests verify that frames, actions, authoritative state,
targets, activations, predictions, and rollouts can carry the same frame-level
identity and be matched even when their rows are deliberately placed in
different orders.

These synthetic tables test only the universal identity layer.

They do not replace the full role-specific contracts or the full cross-role
synthetic pipeline required by Steps 1.3 through 1.7.

## Versioning status

The current implementation is frozen schema `1.0`. Result-changing changes to
fields, units, allowed values, cardinality, or meaning require a versioned
migration and a new run identity. The authoritative approval and migration
record is `docs/contracts/schema_v1_0_signed_record.md`.
