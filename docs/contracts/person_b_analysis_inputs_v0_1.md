# Person B Cross-Role Analysis Intake Requirements v0.1

Status: B-owned consumer requirements implemented; producer-owner signoff is
required before live use.

These requirements do not manufacture C/D/E artifacts and do not replace the
frozen universal, A→B activation, B→A request, or rollout-registry contracts.

## C → B state input

Schema: `person-b-state-input-v0.1`

Person C supplies accepted universal-identity rows, one accepted-manifest hash,
the exact frame join key, scoring-only truth, authoritative visible position,
and a signed wall-parallel coordinate frame. The intake rejects ambiguous
orientation, unsigned adapters, duplicate frames, manifest mixing, nonfinite
truth, hidden observed positions, and visible rows without an observation.

This contract can be validated now. Actual adapter approval and real rows
require Person C.

## D → B baseline predictions

Schema: `person-b-baseline-input-v0.1`

Every baseline document identifies its baseline family, target, input/fold/fit
manifests, and config. Each prediction row contains the exact universal frame
key, B's frozen fold index, a finite prediction, a fit ID, and
`prediction_scope = "out_of_fold"`. B requires exact key coverage and exact
fold agreement before computing any baseline comparison.

The currently accepted family is the contract-tested `last_seen` baseline;
new families require an explicit contract update rather than passing as an
arbitrary string. For `last_seen`, `target_name` must be
`mu_oracle_blocks`, and `feature_access` must contain exactly
`last_visible_position_blocks`, `tau`, and `visibility`. Missing, additional,
renamed, or unknown features fail closed. The document also declares a
`legal_information` mapping with boolean `uses_hidden_truth`,
`uses_future_information`, and `uses_scripted_q` fields. All three flags must
be false and must exactly match the family contract; caller-declared false
flags do not authorize an unrecognized feature.

Person B owns this consumer contract. Baseline implementations and their real
prediction artifacts remain Person D work.

## E → B U4 measurements

Schema: `person-b-u4-measurement-input-v0.1`

The minimum B intake binds measurements to the accepted rollout manifest and
registry, measurement config, rollout/event/direction identities, control
type, applied alpha, producing run, lifecycle status, and the measurement
artifact hash. The actual A rollout manifest and registry documents are
mandatory and are first validated with A's rollout/registry validator. B then
derives expected rollout facts internally. The measurement envelope carries
canonical SHA-256 content hashes for both validated A documents, exact rollout
coverage is required, and event, direction, control, alpha, outcome,
measurable, lifecycle, producing run, and producing-run status must agree.
An optional caller-supplied rollout lookup is only an assertion and is rejected
if it differs from the internally derived facts; it never supplies scientific
truth. A measured row has finite displacement in blocks, persistence in
`[0,1]`, and SSIM in `[0,1]`.
Generation failure, non-persistence, and excluded outcomes carry null
measurements plus a reason; they are never encoded as zero displacement.

The B validator is ready, but Person E must review and sign the payload names
and produce the real measurement artifacts before U4 analysis.

## Stable intake rejection codes

- `missing_required_field`
- `invalid_schema_version`
- `invalid_producer_role`
- `invalid_hash`
- `invalid_coordinate_frame`
- `invalid_identity`
- `duplicate_identity`
- `manifest_mismatch`
- `invalid_value`
- `invalid_lifecycle`
- `fold_mismatch`
- `non_oof_prediction`
- `outcome_conflation`
- `unsupported_baseline_family`
- `legal_information_violation`
- `mixed_episode_id`
- `nonconsecutive_server_tick`
- `timebase_mismatch`
- `invalid_rollout_registry_bundle`
- `rollout_lookup_mismatch`

Validators report these codes and never repair a submitted document.
