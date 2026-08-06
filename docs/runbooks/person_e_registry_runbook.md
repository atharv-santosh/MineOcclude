# Person E Registry Runbook (frozen)

Owner of record: Person E. Schema authority: `docs/contracts/immutable_registry_v2.md`.

This runbook is written for a second operator who has never run Person E's
pipelines. Everything needed is either in this repository or named as an
external dependency with its owner.

## What this workflow does

Registers runs and artifacts with immutable identity, direct-input lineage,
checksums, owners, seeds, and status, and answers forward ("what depends on
this?") and backward ("what produced this?") provenance queries.

## Required inputs

| Input | Owner | Where it comes from |
| --- | --- | --- |
| Upstream artifact manifest with authoritative IDs and status | A / B / C / D | the owning role's published package |
| Direct-input artifact IDs for the new record | caller | the run being registered |
| Config used by the producing run | Person E | `configs/vision/person_e_phase1.yaml` |

Never infer acceptance from a directory location, and never derive an identity
from a filename or a row's position in a file.

## Commands

```
python scripts/build_artifact_index.py <registry.json> <index-out.json>
python scripts/trace_artifact.py <registry.json> <artifact-id>
```

## Validators

```
python -m pytest tests/experiments/test_registry.py
python -m pytest tests/experiments/test_immutable_registry_v2_contract.py
python -m pytest tests/experiments/test_immutable_registry_v2_queries.py
python -m pytest tests/contracts/test_rollout_registry_contract.py
```

## Outputs

- Registry records with `run_id`, `artifact_id`, direct inputs, checksums,
  seeds, owner, status, and supersession fields.
- Artifact index report listing accepted / excluded / failed / superseded.
- Query results resolving a displayed value back to its direct inputs.

## Failure behaviour

Fail closed. Missing identity, duplicate identity, a broken direct-input
reference, a checksum mismatch, an illegal status transition, or a schema
mismatch rejects the record and names the exact record, field, and owner. A
rejected record is never partially written.

## Version and supersession rules

Completed runs are immutable. A correction creates a new run carrying
`supersedes_run_id` and a reason. Superseded and failed records stay queryable
and stay excluded from accepted selection. Nothing is deleted or relabelled.

## Permitted operational reruns

- Re-running a query or index build against an unchanged registry.
- Registering a new artifact whose owner has already published its status.

## Changes requiring Person A / Person B review

- Any schema field addition, removal, or semantic change.
- Any change to status transition rules or to what "accepted" selects.
- Any change that would alter an already-published lineage.

## Escalation

Registry schema or integration conflicts: Person A. Scientific impact of a
schema or status change: Person B.
