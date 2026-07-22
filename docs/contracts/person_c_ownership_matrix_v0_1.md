# Person C Ownership Matrix v0.1

Status: `C0_SYNTHETIC_INTERFACE_IMPLEMENTED_PENDING_CROSS_ROLE_SIGNOFF`

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
| Visibility labels | Person C | Persons B/E | Non-empty capture value defined; control vocabulary unresolved. |
| Episode manifest and exclusion ledger | Person C | Persons A/B/E | Implemented and tested synthetically. |
| RNG schedule generation and schedule hashing | Person C | Persons A/B | PCG64 design recorded; exact compatible NumPy version unresolved. |
| `q`, oracle information set, target fields, scoring use | Person B | Persons A/C | Frozen B meaning is referenced; B repair is not imported. |
| C/A-to-B state adapter | Persons A/B boundary; C supplies source | Persons A/B/C | Unresolved and not implemented in this pass. |
| Marker restrictions, detector output, homography metadata | Person E | Person C | No E-owned repository contract found; unresolved. |
| Layout geometry, condition variants, environment lock | Person C | Persons B/E | Phase C1; not started. |
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

Repository implementation of the synthetic C0 interface is not equivalent to
A/B/E approval. Signoff remains pending for every row marked unresolved above.
