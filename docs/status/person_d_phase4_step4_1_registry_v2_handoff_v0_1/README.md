# Person D Phase 4 Step 4.1: registry v2 handoff preparation package

Prepared: 2026-07-29. Starting authority:
`4fe28c61a01578cc6f7747c89d6aa1cd0f005299`
(`role/person-d-baselines`).

This package completes everything about the Step 4.1 scientific-baseline
handoff that is currently independent of Person B's outputs. It does not
generate, accept, or claim a scientific baseline: no real baseline has
been produced, and
`docs/status/person_d_real_pilot_baseline_preview.json`'s
`scientific_use: forbidden` marking is unaffected and unaltered by
anything here.

## What's in this package

| File | Covers |
|---|---|
| `contract.md` | Items 1-6 and 8: the exact scientific baseline input contract, in prose, with a table mapping each item-8 fail-closed guarantee to its implementation and test. |
| `registry_v2/owner_status.json` | Item 7 (owner-status): D's real, honest current owner-status record -- `owner_status: "pending"`, since no scientific `baseline_prediction_document` has been produced. |
| `registry_v2/exact_artifact_authorization_template.json` | Item 7 (exact-artifact authorization): a structural template scoped to one placeholder `target_artifact_id`. Every hash inside is an obviously-fake placeholder (repeated single hex digits) -- this authorizes nothing real. |
| `registry_v2/handoff_manifest_template.json` | Item 7 (manifest): a structural template for the ordered artifact-identity inventory a real handoff manifest would carry. |
| `registry_v2/verification_receipt_template.json` | Item 7 (verification-receipt): a structural template for a byte-verification receipt against the manifest template above. |
| `registry_v2/composite_validation_report.json` | Item 7 (validation): confirms the four templates above cross-reference each other correctly (`validate_registry_v2_handoff_package`). This validates internal template consistency, not any real artifact. |
| `scientific_readiness_best_case_check.json` | Machinery evidence for items 1-6/8: runs the readiness gate against the most structurally valid synthetic input buildable today, confirming it reports `BLOCKED` for exactly the `scientific_use=forbidden` reason. |
| `production_job_status.json` | Item 9: the production baseline job, recorded as `BLOCKED`, with exact reason codes, owners, and how each was confirmed. |
| `runbook.md` | Item 10: the exact command, inputs, outputs, and acceptance checks to run the moment Person B's real fold manifest and oracle-target document exist. |

## Why this is a separate schema from Person E's Registry v2

Person E owns the project's actual Immutable Registry v2 system
(`docs/contracts/immutable_registry_v2.md`, `role/person-e-operations`).
This package does not vendor, import, or merge that branch or its code --
the task instructions are explicit that this preparation must not merge
or integrate other role branches. `src/mineocclude/baselines
/registry_v2_artifacts.py` instead defines D's own, independent artifact
types that mirror the same four handoff concepts (owner-status,
exact-artifact authorization, manifest, verification-receipt) for
exactly D's own baseline-output domain, built entirely on Person B's real
`mineocclude.analysis.manifests.seal_artifact` /
`validate_sealed_artifact` sealing primitive -- the same one D already
uses for fold manifests and ridge-fit artifacts.

## Reproducing this package

```
python scripts/prepare_step_4_1_registry_v2_handoff.py
```

Regenerates every JSON file in `registry_v2/` and
`scientific_readiness_best_case_check.json` deterministically.
`contract.md`, `production_job_status.json`, and `runbook.md` are
hand-written prose/status records, not script output.

## Test coverage

- `tests/baselines/test_scientific_readiness.py` (11 tests): the fail-closed
  contract (items 1-6, 8).
- `tests/baselines/test_registry_v2_artifacts.py` (11 tests): the four
  registry v2 artifact schemas and their cross-references (item 7).

Full `tests/baselines` suite: 113 passing (was 92 before this package).

## What is explicitly out of scope here

Per the task's stop condition: this package prepares the gate and its
supporting schemas/templates. It does not fit, export, or persist any
scientific baseline. `runbook.md` Steps 1-6 remain unexecuted until
Person B supplies the real sealed fold manifest and oracle-target
document.
