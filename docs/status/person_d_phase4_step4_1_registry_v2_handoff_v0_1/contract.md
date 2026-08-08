# Person D Phase 4 Step 4.1: the exact scientific baseline input contract

Schema version: `person-d-scientific-baseline-input-v0.1`
(`mineocclude.baselines.scientific_readiness
.SCIENTIFIC_BASELINE_INPUT_CONTRACT_SCHEMA_VERSION`)

This is the human-readable form of the contract implemented in
`src/mineocclude/baselines/scientific_readiness.py` and tested in
`tests/baselines/test_scientific_readiness.py`. It defines what "ready to
fit and export a *scientific* (not synthetic) Person D baseline" means.
Everything here is currently BLOCKED -- see `production_job_status.json`.

## 1. The contract, in full

A baseline export is scientific-ready only when **all** of the following
hold simultaneously. Every clause below is checked by
`validate_scientific_baseline_readiness`, and every violation is collected
and reported together rather than stopping at the first one found.

## 2. Exact B fold/split manifest identity

Every context's fold must come from a real, sealed Person B fold/split
manifest. D never assigns or recomputes fold membership. The supplied
manifest must validate against Person B's own authority,
`mineocclude.probes.splits.validate_fold_manifest` -- called directly, not
paraphrased. A manifest missing its sealed `artifact_hash`, or whose
content hash does not match, fails closed.

## 3. Exact B oracle_target identity

Every target value must come from a real Person B oracle-target document,
validated by Person B's own authority,
`mineocclude.oracle.schema.validate_oracle_target_document` -- called
directly. This transitively validates:

- the document envelope (`schema_version`, `target_schema_version`,
  `join_key`);
- every row's universal identity and lifecycle status (see item 4);
- the real coordinate frame and its Person B + Person C cross-role
  signoff, and that every row is bound to the literal current
  `configs/analysis/core.yaml` hash -- **unless** the document is
  explicitly marked `fixture_metadata.scientific_use == "forbidden"`, in
  which case those checks are skipped and this contract's item 8
  guarantee forces the whole readiness check to BLOCKED instead.

## 4. Exact accepted trajectory/model context identity

D does not re-implement this separately: every oracle-target row already
carries the full universal identity
(`mineocclude.contracts.identity.validate_identity`, checked inside
`validate_oracle_target`), including `status == "accepted"`. Calling B's
oracle-target validator (item 3) is therefore also the accepted-identity
check.

Beyond that, the contract additionally requires the *exact* key set
requested by D's contexts, the fold manifest's memberships, and the
oracle-target document's rows to be identical
(`(trajectory_id, model_frame_idx)` triplet-for-triplet). No row may be
scored from a fold or target it was never a member of; no membership or
target row may be silently dropped.

## 5. Deterministic baseline prediction artifact IDs

`mineocclude.baselines.scientific_readiness.build_baseline_prediction_artifact_id`
derives one deterministic ID from exactly the fields named in item 6 plus
the baseline/target identity (`baseline_id`, `target_name`). Identical
inputs always produce the identical ID; changing any one input changes
the ID (see
`test_artifact_id_is_deterministic_and_sensitive_to_every_direct_input`).
This ID is what Registry v2 exact-artifact authorization
(`registry_v2_artifacts.py`) binds to -- never a wildcard by baseline type
or owner.

## 6. Direct-input relationships

`BASELINE_PREDICTION_DIRECT_INPUTS = ("fold_manifest_hash",
"oracle_target_hash", "config_hash")` is the single frozen list of
upstream identities a scientific baseline prediction artifact directly
depends on. Both the artifact-ID builder (item 5) and
`registry_v2_artifacts.build_exact_artifact_authorization` read this same
constant, so code and documentation cannot drift apart by being edited
independently -- confirmed by
`test_direct_input_hashes_must_match_the_frozen_direct_inputs_constant`.

## 7. `candidate_scientific_use` -- the final, explicit declaration

The caller must pass `candidate_scientific_use="accepted"` in so many
words. There is no default and no boolean shortcut. Any other value --
including the existing
`docs/status/person_d_real_pilot_baseline_preview.json`'s own
`"scientific_use": "forbidden"`, or an oracle-target document whose
`fixture_metadata.scientific_use == "forbidden"` -- fails closed
unconditionally.

## 8. Item 8's four fail-closed guarantees, and why they cannot be bypassed

| Condition | Where it's checked | Test |
|---|---|---|
| A context still carries `UNASSIGNED_FOLD` | direct scan of every context's `.fold` | `test_unassigned_fold_cannot_pass` |
| Missing/invalid sealed B fold identity | `probes.splits.validate_fold_manifest` | `test_missing_sealed_fold_identity_cannot_pass` |
| Missing/invalid B oracle identity | `oracle.schema.validate_oracle_target_document` | `test_missing_oracle_identity_cannot_pass` |
| `scientific_use == "forbidden"` anywhere in the lineage | `fixture_metadata` check + `candidate_scientific_use` literal | `test_scientific_use_forbidden_cannot_pass`, `test_non_accepted_candidate_scientific_use_cannot_pass` |

`test_even_the_best_case_synthetic_fixture_is_blocked` is the strongest
form of this proof: the most structurally valid synthetic document this
project's own oracle schema will accept without Person B's real
coordinate-frame signoff is *still* BLOCKED, for exactly the
`scientific_use=forbidden` reason -- confirming this is not a gap in test
coverage but a structural property of the contract: it is currently
**impossible**, not merely discouraged, to construct an input that clears
both B's own oracle schema and this gate without genuine real data.
