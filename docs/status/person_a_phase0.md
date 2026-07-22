# Person A Phase 0 evidence and command center

Status: repository-side evidence reconstructed on 2026-07-22. Historical
actions or access that Git cannot prove are marked `UNVERIFIED`; this record
does not manufacture a retrospective pass or a human approval.

## Verified checkpoint and history

- Current integrated checkpoint: `integration/mvp` at
  `0d5f979e14e5c5f41f59233f1222db822d30cdd6`.
- Current repair work is based on that checkpoint. The branch name itself is
  operational state, not scientific identity.
- Existing Person A history includes `9dec159` (owned skeleton boundaries),
  `f166aec` (Phase 1 contracts through intervention requests), `ad7a4f0`
  (rollout/registry contract), `2b070b2` (synthetic integration pipeline), and
  `21f24bb` (schema v1.0 freeze). Later compatibility lineage is recorded by
  `9f9967c`, and the A/B runner connection by `82c9468` and `363c256`.
- Git proves these commits and the present files. It does not prove which
  uncommitted files, accounts, hardware, or external manuals a person inspected
  before those commits; those historical claims remain `UNVERIFIED`.

## Responsibility and repository inventory

| Responsibility | Authoritative repository location | State | Owner |
|---|---|---|---|
| Universal identity/lifecycle | `src/mineocclude/contracts/identity.py` | AVAILABLE, frozen schema `1.0` | A |
| C-to-A trajectory intake | `src/mineocclude/contracts/trajectory.py` | AVAILABLE | A contract; C producer |
| A-to-B activations | `src/mineocclude/contracts/activation.py` | AVAILABLE | A |
| B-to-A requests | `src/mineocclude/contracts/intervention_request.py` | AVAILABLE | A contract; B producer |
| A-to-E rollout/shared registry | `src/mineocclude/contracts/rollout_registry.py` | AVAILABLE | A rollout/orchestration; E lineage model |
| MineWorld adapter | `src/mineocclude/models/mineworld_adapter.py` | AVAILABLE skeleton; real runtime UNVERIFIED | A |
| Hooks/pooling/storage/injection/runner | `src/mineocclude/activations/hooks.py`, `src/mineocclude/activations/pool.py`, `src/mineocclude/activations/store.py`, `src/mineocclude/intervention/inject.py`, `scripts/run_mvp.py` | AVAILABLE boundaries; real runtime UNVERIFIED | A |
| Shared synthetic contract runner | `src/mineocclude/integration/synthetic_pipeline.py` | AVAILABLE, CPU-only evidence | A integration boundary |

The reviewed file map is `docs/architecture/person_a_file_map.md`. No second
authoritative location is declared here.

## Dependency, access, compute, and storage matrix

`AVAILABLE` means the named repository evidence exists. It does not assert
external account or hardware access.

| Dependency | Status | Evidence / truthful limitation | Owner or provider | Pass condition |
|---|---|---|---|---|
| Frozen A/B/C/D/E contracts and synthetic fixtures | AVAILABLE | Current repository and tests | Role owners | Validators and joins pass |
| Local CPU test execution | AVAILABLE | Repository test history and current repair verification | Project environment | CPU synthetic suite passes |
| MineWorld source/assets/checkpoint | UNVERIFIED | No repository evidence proves local bytes or access | A/project | Record exact paths and hashes after access is verified |
| GPU capacity | UNVERIFIED | No measured device or allocation record | A/project | Save device/capacity check |
| AWS/account permissions | UNVERIFIED | No permission evidence in repository | Project owner | Save non-secret access check |
| Durable artifact storage and quota | UNVERIFIED | URI conventions are frozen; deployment root/quota are not | Project owner/E | Record approved root, quota, and retention |
| Real Minecraft/C capture input | BLOCKED | Assigned to later C runtime/capture phases | C | Accepted real package exists |
| Human interface/scientific approval | UNVERIFIED | No signed human evidence | A/B/C/D/E approvers | Dated approval record |

## Pinned MineWorld reading checklist

These are the repository-controlled materials that must be read together
before real runtime implementation. A checked path is evidence that the file
exists, not evidence of a person's historical reading.

| Path or subject | Repository state | Reading/real-runtime verification |
|---|---|---|
| `docs/contracts/activation_v1.md` token/layer/hook contract | AVAILABLE | Personal reading UNVERIFIED |
| `docs/contracts/trajectory_v1.md` preprocessing/action boundary | AVAILABLE | Personal reading UNVERIFIED |
| `docs/contracts/intervention_request_v1.md` layer/timestep/dose limits | AVAILABLE | Personal reading UNVERIFIED |
| `docs/contracts/rollout_registry_v1.md` rollout/runtime provenance | AVAILABLE | Personal reading UNVERIFIED |
| `src/mineocclude/models/mineworld_adapter.py` owned runtime boundary | AVAILABLE skeleton | Pinned upstream code/checkpoint UNVERIFIED |
| `configs/analysis/core.yaml` downstream analysis contract | AVAILABLE | Runtime compatibility UNVERIFIED |

## Dependency and decision register

| Issue | Safe current rule | Owner / approver | Resolve before |
|---|---|---|---|
| Exact upstream MineWorld revision and checkpoint bytes | Do not run claim-bearing extraction without explicit hashes | A; project approver | First real model run |
| RGB/BGR, resize, interpolation, scaling, normalization | Preserve frozen provenance fields; do not guess | A with C | First real C-to-A preprocessing |
| Camera-component orientation | Require controlled impulse evidence | A with C | First real trajectory acceptance |
| GPU/AWS/storage availability | Treat as `UNVERIFIED`; do not schedule scale work from assumptions | Project owner | Runtime planning |
| Shared registry orchestration adoption | A integrates; E owns lineage behavior; no second registry | A/E | First orchestration registry snapshot |
| Formal Phase 0/1 approval | Do not infer from passing tests | Role owners/approver | Formal checkpoint declaration |

## Command center

| Milestone | Status | Owner | Output path | Pass condition |
|---|---|---|---|---|
| Repository/ownership reconstruction | COMPLETED from current evidence | A | This file and `docs/architecture/person_a_file_map.md` | Locations and Git evidence are explicit |
| Frozen Phase 1 interfaces | COMPLETED technically | A with consumers | `src/mineocclude/contracts/`, `docs/contracts/` | Schema-v1 tests pass |
| Cross-role synthetic integration | CURRENT | A integration boundary | `src/mineocclude/integration/synthetic_pipeline.py`, saved report | Current validators pass deterministically |
| Human approval | BLOCKED/UNVERIFIED | A/B/C/D/E approvers | Dated signoff record | Actual approvers sign |
| Real MineWorld/runtime work | NEXT LATER PHASE | A with C/runtime owners | Future run artifacts | Access, pins, and runtime gates are evidenced first |
