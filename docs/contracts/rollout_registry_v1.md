# MineOcclude A-to-E Rollout and A/E Registry Contract

Current implementation version: `0.1-draft`

Target frozen version: `1.0`

Status: Phase 1 draft pending final cross-role sign-off in Step 1.8.

## Purpose

This contract defines the rollout manifest Person A hands to Person E and the
run/artifact registry shared by A and E. It makes every rollout outcome,
generated artifact, input, and producing run traceable without interpreting a
filename.

The rollout manifest and registry are separate handoff documents with one
combined validator. Combined validation is intentional: output metadata,
producer lineage, lifecycle, and hashes cannot be checked reliably one file at
a time.

The validator does not repair records and does not implement Person E's
scientific measurements.

## Version and handoff identity

Both documents require:

* `schema_version = "0.1-draft"`
* the same non-empty `handoff_id`

The rollout document also requires `manifest_id`. The registry requires
`registry_id`. These IDs are authoritative fields; paths, directory order, and
filenames are never scientific identity.

## Rollout manifest

The top-level rollout document contains:

* `schema_version`
* `manifest_id`
* `handoff_id`
* `rollout_rows`

Every rollout row requires the fields below.

### Event and universal identity

* `rollout_id`: immutable identity of this rollout record
* `event_id`: held-out event identity
* `episode_id`
* `trajectory_id`
* `server_tick`
* `render_frame_idx`
* `action_idx`
* `layout_id`
* `model_frame_idx`
* `regime`
* `visibility`
* `tau`
* `v`
* `q`
* `duration`
* `seed`

The row is validated against the complete universal identity contract from
Step 1.2, including source indices and experimental-condition identity.
`rollout_id` must be unique within the manifest. Event identity must be present
even when the output URI happens to contain a human-readable event name.

### Dose and intervention identity

* `dose_id`
* `alpha_requested`
* `alpha_applied`
* `cap_reduced`
* `intended_block_shift`
* `direction_version`
* `layer_idx`
* `hook_site`
* `timestep_idx`
* `control_type`

The allowed control types are:

* `intervention`
* `alpha_zero`
* `random_direction`

Requested alpha, applied alpha, and intended block shift are finite numeric
values. An unflagged requested/applied alpha change is rejected. A flagged cap
reduction must reduce magnitude without reversing sign. For `alpha_zero`, both
alphas and the intended shift must be zero and `cap_reduced` must be false.

The current MineWorld bounds reused from Step 1.5 are layers `0` through `19`
and timesteps `0` through `15`.

`intended_block_shift` is a requested dose target from Person B's intervention
request. It is not a measured displacement.

### Input context and request provenance

* `input_context_id`
* `input_context_artifact_id`
* `input_context_hash`
* `intervention_request_artifact_id`

The context and intervention request must be accepted registry artifacts and
must appear in the producing run's direct inputs. The context hash must equal
the registry artifact checksum.

### Output provenance

* `output_artifact_id`
* `output_uri`
* `output_hash`

For output-bearing outcomes, all three fields are required and must exactly
match a `rollout_clip` artifact produced by the declared run. A URI must have an
explicit scheme; a bare filename or Windows filesystem path is rejected.

For generation failure, these three fields must be null. Partial files and
diagnostics remain independently recorded as artifacts of the failed run, but
they are not misrepresented as a completed rollout clip.

### Model, configuration, and run identity

* `code_sha`
* `config_hash`
* `model_hash`
* `preprocess_hash`
* `run_id`

`code_sha` is a full 40-character Git SHA; the remaining hashes use SHA-256.
All four values must equal the producing run's provenance.

### Outcome and lifecycle

* `outcome`
* `outcome_detail`
* `measurable`
* `status`
* `exclusion_reason`
* `superseded_by`

Outcomes are mutually exclusive:

* `measurable_continuation`: generation completed and the subject persists to
  the measurement endpoint. It has a rollout clip, null `outcome_detail`, and
  is measurable while accepted.
* `non_persistence`: generation produced a clip but the subject did not persist
  to the measurement endpoint. It requires a non-empty `outcome_detail` and is
  not measurable as displacement.
* `generation_failure`: generation did not produce a completed rollout clip.
  It requires a non-empty `outcome_detail`, is not measurable, and the rollout
  row must be excluded.

Non-persistence and generation failure are not aliases. Neither outcome has a
zero displacement. Rollout rows may not contain Person E measurement fields
such as displacement variants, `persistence_score`, `detections`, `homography`,
or `ssim`.

Lifecycle uses the Step 1.2 field names and meanings:

* accepted: `status = "accepted"`, with null `exclusion_reason` and
  `superseded_by`
* excluded: `status = "excluded"`, with a non-empty `exclusion_reason` and null
  `superseded_by`
* superseded: `status = "superseded"`, with null `exclusion_reason` and an
  existing replacement in `superseded_by`

Rollout supersession must preserve `event_id` and cannot be cyclic.

## Run registry

The registry's `runs` list contains immutable run records with:

* `run_id`
* `command`
* `owner`
* `parent_run_id`
* `input_artifact_ids`
* `output_artifact_ids`
* `code_sha`
* `config_hash`
* `model_hash`
* `preprocess_hash`
* `execution_status`
* `failure_reason`

`command` is a non-empty argument list, preserving command boundaries without
requiring shell parsing. Input and output lists contain direct dependencies,
not a transitive summary. A run cannot list the same artifact as both input and
output.

`code_sha` is a full 40-character Git SHA. Config, model, and preprocess hashes
are SHA-256 values. The hashes of each direct input and output are obtained by
joining its artifact ID to the artifact registry; this avoids duplicating hash
values that could disagree.

`parent_run_id` is null for a root run or points to an existing run. Parent
lineage is acyclic and auditable. Parent lineage does not replace the direct
artifact-input list.

Allowed execution states are:

* `completed`, with null `failure_reason`
* `completed_with_failures`, with a non-empty `failure_reason`
* `failed`, with a non-empty `failure_reason`

A rollout with an output-bearing outcome cannot point to a failed run. A
generation failure must point to a failed or completed-with-failures run.

## Artifact registry

The registry's `artifacts` list contains:

* `schema_version`
* `artifact_id`
* `artifact_type`
* `uri`
* `sha256`
* `producer_run_id`
* `status`
* `exclusion_reason`
* `superseded_by`

Supported draft artifact types are:

* `input_context`
* `intervention_request`
* `rollout_clip`
* `partial_rollout`
* `diagnostic_log`

Every artifact points to exactly one producing run, and that run must list the
artifact among its direct outputs. Conversely, every run input and output ID
must resolve to a registry artifact. Artifact IDs are unique.

Artifact lifecycle supports accepted, excluded, and superseded with the same
Step 1.2 semantics described above. A replacement artifact must exist, have the
same artifact type, differ from the superseded artifact, and form no cycle.
The old record remains in the registry, preserving audit history.

## Cross-document pass check

A combined handoff passes only when:

* manifest and registry versions and `handoff_id` agree
* rollout, run, and artifact identities are unique
* every rollout points to an existing producing run
* every context and intervention request is an accepted direct run input
* every completed rollout clip is an exact run output
* row URI and hashes match the artifact record
* row code/config/model/preprocess hashes match the run record
* output, execution, outcome, measurable, and lifecycle states agree
* all parent and supersession lineage resolves without cycles

These joins give Person E enough information to classify each row and trace
every rollout and artifact to its producing run without a private naming
convention.

## Machine-readable rejection codes

The validator can return:

* `missing_required_field`
* `invalid_schema_version`
* `invalid_rollout_row`
* `duplicate_rollout_id`
* `invalid_outcome`
* `outcome_output_mismatch`
* `generation_status_mismatch`
* `displacement_encoding_forbidden`
* `invalid_run_record`
* `duplicate_run_id`
* `invalid_parent_lineage`
* `invalid_artifact_record`
* `duplicate_artifact_id`
* `invalid_lifecycle`
* `invalid_supersession`
* `invalid_uri`
* `invalid_hash`
* `missing_registry_reference`
* `lineage_mismatch`
* `metadata_mismatch`

One invalid submission may produce several codes. Records are rejected as
submitted: the validator does not infer missing identity, rewrite a URI,
substitute hashes, alter lifecycle, or convert outcomes.

Malformed mappings, lists, scalar types, numeric values, hashes, and URIs return
structured rejections rather than uncaught exceptions. Validation never mutates
the submitted documents.

## Synthetic evidence

`tests/fixtures/rollout_registry/accepted_rollout_manifest.json` contains one
explicit example of each outcome. Only the continuation row is measurable.

`tests/fixtures/rollout_registry/accepted_registry.json` contains:

* an input-registration root run
* an earlier rollout run
* a successful rollout run
* a failed rollout run
* accepted, excluded, and superseded artifacts
* direct input/output provenance and checksums

Both accepted documents include:

```json
{
  "fixture_metadata": {
    "synthetic": true,
    "scientific_use": "forbidden"
  }
}
```

Rejected bundle fixtures cover filename-only identity, bare filename output,
missing universal identity, outcome conflation, zero-displacement encoding for
both failure and non-persistence, missing run lineage, bad supersession, parent
cycles, malformed types/URI, inconsistent lifecycle, cross-record metadata
mismatch, and duplicate rollout identity.

The fixture builder is deterministic and CPU-only.

## No automatic repair

The validator never:

* derives event or run identity from a path
* changes requested or applied alpha
* supplies a missing output or checksum
* converts non-persistence or failure to zero displacement
* changes accepted, excluded, or superseded status
* rewrites parent or supersession lineage
* computes Person E measurement outputs

Incompatible records must be corrected at the producer and resubmitted.

## Scope boundary

This Step 1.6 implementation defines interchange and provenance only. It does
not implement detection, homography, displacement, SSIM, persistence scoring,
or other Person E scientific evaluation logic. It also does not construct the
Step 1.7 cross-role synthetic pipeline or freeze/sign schema version 1.0.

## Draft assumptions pending Step 1.8

The following remain draft choices for cross-role approval:

* final control-type and artifact-type vocabularies
* whether run and artifact IDs must adopt a UUID format
* the final owner vocabulary
* the allowed production URI schemes and storage roots
* final run-status vocabulary and partial-success policy
* final numeric tolerance for requested/applied alpha equivalence
* approvers, migration rules, and the version-1.0 freeze record

Changing any of these result-affecting meanings after freeze will require the
Step 1.8 migration and run-identity policy.
