# Person E schema migrations and remaining gaps

Status: the repository-side Phase 1.2 gaps for artifact catalog, immutable run
provenance, direct artifact inputs, checksum/size evidence, status authority,
and supersession are implemented by the compatible
`mineocclude-immutable-registry-v1.0` sub-schema in the authoritative shared
`src/mineocclude/contracts/rollout_registry.py`. The frozen A rollout bundle
schema and validator remain unchanged. Phase 0/1 A/E interface approval is
recorded for `80d41c5ca0e341263a7b0c683fae4b51be376c55` in
`docs/contracts/schema_v1_0_signed_record.md`; A orchestration integration and
real-runtime qualification remain pending.

The sections below preserve the original proposals and record their current
resolution. They are not authority over the implemented validator.

## Gap 1: E-produced artifact types

Repository-side status: **resolved for Phase 1.2 representation**. The closed
shared catalog now includes the roadmap types, existing A rollout types, and
the E lineage products needed by the contract. Scientific producers remain
future work.

The roadmap requires detection, homography, measurement, metric-table, figure,
and paper/release artifacts to appear in the traceable artifact index. Frozen
A/E schema v1.0 currently accepts only:

- `input_context`
- `intervention_request`
- `rollout_clip`
- `partial_rollout`
- `diagnostic_log`

### Proposed migration

Create a new versioned registry contract that adds the required E artifact
types and preserves the existing fields, lifecycle, URI rules, direct lineage,
and checksums. Old v1.0 bundles remain valid under the old validator. Affected
fixtures/tests must be regenerated for the new version, and E result runs need
new run identities. Approval is required from A and E, plus consumers of the
new artifact index.

Until approved, E's detailed measurement evidence and reports remain separate
hash-bound documents. They are not mislabeled as a v1.0 registry artifact.

## Gap 2: run supersession

Repository-side status: **resolved for Phase 1.2** through required
`supersedes_run_id` and `supersession_reason`, existence/same-owner checks,
single-successor enforcement, and cycle rejection.

The roadmap asks corrections to use `supersedes_run_id` and a reason. Frozen
v1.0 run records have `parent_run_id` but no run-supersession fields. Artifact
supersession is supported.

### Proposed migration

Add explicit nullable `supersedes_run_id` and `supersession_reason` fields with
existence, non-self-reference, and acyclic validation. Do not reinterpret
`parent_run_id` as supersession because it represents execution lineage.

## Gap 3: extended U4 controls

Frozen rollout schema v1.0 permits `intervention`, `alpha_zero`, and
`random_direction`. D's roadmap also requires orthogonal, wrong-layer, and
wrong-timestep controls.

### Proposed resolution gate

A/B/D/E must decide whether those controls are:

1. existing `intervention` rows whose direction/layer/timestep identity carries
   the distinction, with an approved external control manifest; or
2. new `control_type` values requiring a versioned rollout and measurement
   migration.

E will preserve the submitted v1.0 value and will not infer a new control label.

## Gap 4: SSIM numeric range

The B intake requires `ssim` in `[0, 1]`; the declared SSIM formula can
mathematically produce negative values. E never clips such a value. If a real
measurement falls below zero, B/E must propose a versioned consumer rule or
exclude it with an explicit diagnostic pending approval.

## Gap 5: complete run and artifact provenance

Repository-side status: **resolved for Phase 1.2**. The shared sub-schema
requires every field listed below and validates immutable terminal snapshots,
legal status transitions, artifact direct inputs, status authority, checksum,
and size.

The roadmap additionally requires each run to retain the Git dirty flag,
literal config snapshot identity, data and environment identities, named seeds,
start/end times, and correction/supersession metadata. It also requires every
artifact—not only its producer run—to preserve its own direct-input artifact
IDs. Frozen v1.0 run records contain command, owner, parent, run-level inputs
and outputs, code/config/model/preprocess hashes, execution status, and failure
reason, but not those additional fields.

### Proposed migration

Add the missing fields in a new registry version with strict types and hashes:

- `git_dirty`, `config_snapshot_hash`, `data_identity_hash`,
  `environment_hash`;
- a named `seeds` mapping;
- UTC `started_at` and `ended_at` with ordering validation;
- `supersedes_run_id` and `supersession_reason`; and
- artifact-level `direct_input_artifact_ids`.

The migration must retain the v1 direct-run lineage and must not derive any
identity from paths. Existing v1 bundles remain valid only under v1. Before
approval, E reports bind literal inputs/config/code/run IDs and publish the
precise limitation instead of adding silent extra fields to v1 records.

## Gap 6: figure and result artifact registration

Repository-side status: **resolved at the contract/catalog level only**.
Figure, prediction, baseline, detection, metric-table, measurement, and related
types can be represented. Real producer registration and A orchestration are
not claimed.

Frozen v1 cannot register detector, homography, localization, SSIM,
measurement-evidence, metric-table, figure-input, SVG figure, or paper/release
artifacts. Therefore E can make these files immutable and hash-bound now, but
cannot truthfully place them in the accepted v1 artifact lifecycle.

### Proposed migration

Add explicit versioned artifact types, retain URI/checksum/producer/direct-input
fields, and require a figure manifest to link source result, accepted rollout
manifest, fold manifest where applicable, script/config/code/run, rendered
output, caption, and supersession state. Scientific publication is blocked
until those sources are accepted and current under the migrated registry.
