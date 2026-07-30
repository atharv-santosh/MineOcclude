# Step 4.1 arrival runbook: what happens the moment B's handoff exists

This is the exact command, inputs, outputs, and acceptance checks Person D
will run the moment Person B publishes a real sealed fold manifest and a
real oracle-target document. Nothing in this runbook can be executed today
-- it is written now so no time is lost re-deriving this sequence once the
inputs exist. See `production_job_status.json` for why this is currently
BLOCKED, and `contract.md` for the exact requirements every input below
must satisfy.

## Step 0: confirm the inputs actually landed

```
git fetch origin role/person-b-methods
git log -1 --format='%H %s' origin/role/person-b-methods
```

Locate the real artifacts. Expected paths (Person B owns exact naming;
confirm against whatever B actually publishes):

- a real fold manifest, structurally the same shape as
  `tests/fixtures/person_d/synthetic_b_fold_manifest.json` but sealed over
  Person C's real accepted trajectories;
- a real oracle-target document, structurally the same shape as
  `mineocclude.oracle.targets.build_regime_a_target_document`'s output,
  with a real `coordinate_frame` (Person B + Person C signed) and rows
  bound to the literal current `configs/analysis/core.yaml` hash -- i.e.
  **no** `fixture_metadata.scientific_use == "forbidden"` marker.

## Step 1: run the readiness gate against the real inputs

```python
from mineocclude.baselines import validate_scientific_baseline_readiness, READY_SCIENTIFIC_USE

finding = validate_scientific_baseline_readiness(
    real_contexts,               # built via mineocclude.baselines.capture_ingest
                                   # .build_contexts_from_capture, folds attached via
                                   # mineocclude.baselines.export.attach_b_fold_assignments
    fold_manifest=real_fold_manifest,
    oracle_target_document=real_oracle_target_document,
    candidate_scientific_use=READY_SCIENTIFIC_USE,
)
```

**Acceptance check:** `finding.status == "READY"` and
`finding.blocked_reasons == ()`. If `BLOCKED`, stop -- read every reason in
`finding.blocked_reasons` and do not proceed to Step 2 until they are all
resolved. Do not weaken, skip, or special-case this gate to force a READY
result; if it's not genuinely READY, the inputs are not actually ready.

## Step 2: fit and export the real baselines

Only after Step 1 reports READY. Use the existing D baseline modules
exactly as documented in `docs/baselines/person_d_phase1.md` ("Wiring real
data"): `last_seen.predict_last_seen`, `constant_velocity
.predict_constant_velocity`, etc., feeding real `mu_oracle_by_key` /
`log_sigma_by_key` extracted from `real_oracle_target_document["rows"]`.

## Step 3: mint the exact deterministic artifact ID

```python
from mineocclude.baselines import build_baseline_prediction_artifact_id

artifact_id = build_baseline_prediction_artifact_id(
    baseline_id="last_seen_v1",
    target_name="mu_oracle_blocks",
    fold_manifest_hash=real_fold_manifest["artifact_hash"],
    oracle_target_hash=real_oracle_target_document_hash,  # sha256_value(...) of the sealed document
    config_hash=hash_core_analysis_config(),
)
```

**Acceptance check:** re-running this exact call with the exact same four
inputs always reproduces the exact same `artifact_id` (see
`tests/baselines/test_scientific_readiness.py
::test_artifact_id_is_deterministic_and_sensitive_to_every_direct_input`).

## Step 4: build the export document and validate against B's real contract

```python
from mineocclude.baselines import build_baseline_document, validate_document

document = build_baseline_document(
    rows, target_name="mu_oracle_blocks", baseline_id="last_seen_v1",
    baseline_family="last_seen", config_hash=..., input_manifest_hash=...,
    fold_manifest_hash=real_fold_manifest["artifact_hash"], fit_manifest_hash=...,
    default_fit_id="last_seen:mu_oracle_blocks:closed_form",
)
result = validate_document(document)
```

**Acceptance check:** `result.accepted is True`, `result.rejections == ()`.

## Step 5: build the Registry v2-style handoff package for real

```python
from mineocclude.baselines import (
    build_owner_status_record, build_exact_artifact_authorization,
    build_handoff_manifest, build_verification_receipt,
    RegistryV2HandoffPackage, validate_registry_v2_handoff_package,
)

owner_status = build_owner_status_record(
    owner_status="accepted", authority_revision=<current git HEAD>,
    authorized_artifact_types=["baseline_prediction_document"],
    artifact_id=..., code_sha=..., config_hash=..., input_manifest_hash=...,
)
authorization = build_exact_artifact_authorization(
    target_artifact_id=artifact_id, target_artifact_type="baseline_prediction_document",
    target_artifact_sha256=sha256_value(document),
    owner_status_record_hash=owner_status["artifact_hash"],
    direct_input_hashes={
        "fold_manifest_hash": real_fold_manifest["artifact_hash"],
        "oracle_target_hash": real_oracle_target_document_hash,
        "config_hash": hash_core_analysis_config(),
    },
    artifact_id=..., code_sha=..., config_hash=..., input_manifest_hash=...,
)
# ... handoff_manifest, verification_receipt built the same way as
# scripts/prepare_step_4_1_registry_v2_handoff.py's templates, but with
# real hashes in place of every PLACEHOLDER_* constant.

validate_registry_v2_handoff_package(RegistryV2HandoffPackage(
    owner_status_record=owner_status,
    exact_artifact_authorization=authorization,
    handoff_manifest=handoff_manifest,
    verification_receipt=verification_receipt,
))
```

**Acceptance check:** `validate_registry_v2_handoff_package` raises nothing.

## Step 6: persist and update status

- Write the real baseline document, the real registry v2 package, and a
  new `production_job_status.json` with `"status": "ACCEPTED"` (never edit
  the BLOCKED one in place -- append a new dated record, matching this
  project's append-only decision-log convention).
- Update `docs/baselines/person_d_phase1.md` and `PERSON_D_ISSUE.md` to
  reflect real-data execution, exactly as was done for the Step 4.3 gate's
  BLOCKED status in the 2026-07-27 documentation reconciliation.
- Add a dated entry to `docs/decisions/person_d_phase1_decision_log.md`.

## What must never happen at any step above

- Treating `docs/status/person_d_real_pilot_baseline_preview.json` (still
  `scientific_use: forbidden`) as if it were the real oracle-target
  document or a substitute for Step 1.
- Constructing a `regime="regime_a"` oracle-target row without `synthetic`
  set, or omitting `fixture_metadata.scientific_use` from a document that
  is not genuinely real, purely to make Step 1 report READY.
- Skipping Step 1 "because the data looks fine" -- the gate exists
  precisely because "looks fine" is not the same as "passed the exact
  identity and coverage checks."
