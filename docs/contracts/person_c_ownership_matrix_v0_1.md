# Person C Ownership Matrix v0.1

Status: `C0_C1_STRUCTURALLY_INTEGRATED_PHASE_0_1_INTERFACE_SIGNOFF_COMPLETE_RUNTIME_PENDING`

Current repository checkpoint: `integration/mvp` at
`80d41c5ca0e341263a7b0c683fae4b51be376c55`. The ownership statements below
are included in the coordinator-confirmed five-role Phase 0/1 interface
approval recorded in `docs/contracts/schema_v1_0_signed_record.md`. That
approval does not imply real-runtime qualification.

This matrix separates ownership from consultation. A missing upstream decision
is recorded rather than selected privately by Person C.

| Interface or artifact | Producer/owner | Required reviewers/consumers | C0 status |
|---|---|---|---|
| Frozen universal identity, shared units, lifecycle vocabulary | Person A | B/C/D/E | Frozen schema `1.0`; imported unchanged. |
| C-to-A trajectory envelope and normalized-action field names | Person A | Person C | Frozen schema `1.0`; imported unchanged. |
| Raw action capture | Person C | Person A | Container frozen; exact raw vocabulary unresolved. |
| Raw-to-normalized action conversion | Person A | Person C | Unresolved; C preserves both streams and never converts silently. |
| Server authoritative state and full x/z coordinates | Person C | Persons A/B | C0 minimum payload defined. |
| Client tick log and packet-receipt evidence | Person C | Person A | Structural row defined; real timing evidence required later. |
| Frame map and capture-key alignment | Person C | Persons A/B | Implemented and tested synthetically. |
| Visibility labels | Person C | Persons B/E | Capture vocabulary is structurally defined. `visible`/`occluded` are B oracle eligible; no-object controls are explicitly rejected from oracle-target production rather than assigned a fabricated visibility/target. |
| Episode manifest and exclusion ledger | Person C | Persons A/B/E | Implemented and tested synthetically. |
| RNG schedule generation and schedule hashing | Person C | Persons A/B | PCG64 design recorded; exact compatible NumPy version unresolved. |
| `q`, oracle information set, target fields, scoring use | Person B | Persons A/C | Frozen B meaning is referenced; B repair is not imported. |
| C-to-B state adapter | B owns scientific projection; C supplies authoritative source; A supplies model/preprocess provenance | Persons A/B/C | Implemented synthetically in `src/mineocclude/analysis/coordinates.py`; Phase 0/1 interface compatibility is approved at the checkpoint above. Complete C validation and exact capture-key joins precede projection into B's frozen input; real rows remain pending. |
| Marker identity/roles and homography | C owns stable IDs/world geometry; E owns image observations and homography | Persons C/E | C layout v0.2 adds a stable-ID-to-canonical-role mapping; E homography v1.1 consumes it by explicit ID. E v1.0 remains supported. Formal real-camera qualification remains pending. |
| Layout geometry, condition variants, environment lock | Person C | Persons B/E | C1 structurally implemented for six layouts and three conditions; real environment/reconstruction evidence remains required. |
| Minecraft/Fabric runtime, reset, capture, screenshots | Person C | Persons A/E | Out of C0; runtime evidence required later. |
| MineWorld loading, preprocessing, inference, model-frame mapping | Person A | Person C | Adapter remains a skeleton; unresolved implementation details. |

## Change control

- Person C may add stricter producer checks without weakening A's validator.
- Shared names, units, keys, cardinality, or meaning cannot change under
  `schema_version = "1.0"`.
- A result-affecting shared change requires the frozen migration policy.
- C-owned additive changes require a new Person C contract version and fixture
  regeneration.
- Rejected and superseded evidence remains auditable.

## Signoff gate

Repository implementation and the current synthetic C-to-B/C-to-E tests are
not equivalent to A/B/E approval. Human signoff and every real-runtime item
remain pending or unverified as stated above.
