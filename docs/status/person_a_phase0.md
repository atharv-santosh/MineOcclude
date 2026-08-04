# Person A Phase 0 evidence and command center

Status: repository-side evidence reconstructed on 2026-07-22. Historical
actions or access that Git cannot prove are marked `UNVERIFIED`; this record
does not manufacture a retrospective pass or a human approval.

## Verified checkpoint and history

- Current approved Phase 0/1 interface checkpoint: `integration/mvp` at
  `80d41c5ca0e341263a7b0c683fae4b51be376c55`.
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
| Pinned MineWorld source and A0.4 code-reading evidence | COMPLETE | `docs/status/person_a_mineworld_code_reading.md`; Microsoft revision `9f49efbcc68a5f0cf60e78f0abc566eac409282f`; paired ModelScope sample hashes recorded | A | Re-open only if the pinned source revision or reviewed evidence changes |
| MineWorld 700M_16f checkpoint and VAE runtime bytes | UNVERIFIED | Required runtime assets have not yet been locally hash-verified in this record | A/project | Download, inspect, and record exact checkpoint/VAE paths and SHA-256 hashes before the first real model run |
| GPU capacity | UNVERIFIED | No measured device or allocation record | A/project | Save device/capacity check |
| AWS/account permissions | UNVERIFIED | No permission evidence in repository | Project owner | Save non-secret access check |
| Durable artifact storage and quota | UNVERIFIED | URI conventions are frozen; deployment root/quota are not | Project owner/E | Record approved root, quota, and retention |
| Real Minecraft/C capture input | BLOCKED | Assigned to later C runtime/capture phases | C | Accepted real package exists |
| Phase 0/1 interface approval | COMPLETE at `80d41c5ca0e341263a7b0c683fae4b51be376c55` | Coordinator-confirmed five-role signoff in `docs/contracts/schema_v1_0_signed_record.md` | A/B/C/D/E role owners | New approval required for any result-changing contract revision |
| Runtime, experimental, and final scientific approval | PENDING | No real-runtime or result evidence is claimed by the Phase 0/1 signoff | Applicable later-phase owners | Applicable runtime or result gate |

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
| `src/mineocclude/models/mineworld_adapter.py` owned runtime boundary | AVAILABLE skeleton | Pinned upstream code reading COMPLETE for A0.4; real checkpoint/runtime verification still pending |
| `configs/analysis/core.yaml` downstream analysis contract | AVAILABLE | Runtime compatibility UNVERIFIED |

## A0.4 completion record

Status: **COMPLETE**

Evidence:

- `docs/status/person_a_mineworld_code_reading.md`
- Microsoft MineWorld source revision:
  `9f49efbcc68a5f0cf60e78f0abc566eac409282f`

Reviewed pinned upstream materials:

- `mcdataset.py`
- `utils.py`
- `configs/700M_16f.yaml`
- `mineworld.py`
- `inference.py`
- paired `gradio_scene/scene.jsonl`
- paired `gradio_scene/scene.mp4`

The review records authoritative evidence for:

- 640 × 360 source frames;
- 20 FPS paired sample cadence;
- 384 × 224 model preprocessing in the interactive path;
- 336 visual tokens per frame;
- 11 action tokens;
- 347 tokens per complete visual/action group;
- 16-frame context for `700M_16f`;
- action vocabulary offset 8192;
- pinned model/config/tokenizer ownership paths;
- exact paired-sample SHA-256 identities.

The actual `700M_16f` checkpoint and shared VAE runtime bytes remain a later runtime verification requirement. A0.4 completion does not claim that those model assets have already been downloaded, loaded, or hash-verified.

## Dependency and decision register

| Issue | Safe current rule | Owner / approver | Resolve before |
|---|---|---|---|
| Exact upstream MineWorld revision and checkpoint bytes | Do not run claim-bearing extraction without explicit hashes | A; project approver | First real model run |
| RGB/BGR, resize, interpolation, scaling, normalization | Preserve frozen provenance fields; do not guess | A with C | First real C-to-A preprocessing |
| Camera-component orientation | Require controlled impulse evidence | A with C | First real trajectory acceptance |
| GPU/AWS/storage availability | Treat as `UNVERIFIED`; do not schedule scale work from assumptions | Project owner | Runtime planning |
| Shared registry orchestration adoption | A integrates; E owns lineage behavior; no second registry | A/E | First orchestration registry snapshot |
| Formal Phase 0/1 interface approval | Complete only for checkpoint `80d41c5ca0e341263a7b0c683fae4b51be376c55`; do not extend it to runtime or results | A/B/C/D/E role owners; coordinator confirmation | Re-review before any result-changing contract revision |

## Command center

| Milestone | Status | Owner | Output path | Pass condition |
|---|---|---|---|---|
| Repository/ownership reconstruction | COMPLETED from current evidence | A | This file and `docs/architecture/person_a_file_map.md` | Locations and Git evidence are explicit |
| Frozen Phase 1 interfaces | COMPLETED technically | A with consumers | `src/mineocclude/contracts/`, `docs/contracts/` | Schema-v1 tests pass |
| Cross-role synthetic integration | CURRENT | A integration boundary | `src/mineocclude/integration/synthetic_pipeline.py`, saved report | Current validators pass deterministically |
| A1.8 Phase 0/1 interface signoff | COMPLETED for `80d41c5ca0e341263a7b0c683fae4b51be376c55` | A/B/C/D/E role owners | `docs/contracts/schema_v1_0_signed_record.md` | Re-open only for a result-changing contract revision |
| Real MineWorld/runtime work | NEXT LATER PHASE | A with C/runtime owners | Future run artifacts | Access, pins, and runtime gates are evidenced first |
