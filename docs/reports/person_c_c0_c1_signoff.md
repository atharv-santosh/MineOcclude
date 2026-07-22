# Person C C0/C1 signoff record

Status: C0 and C1 are structurally integrated, and the five role owners have
approved the Phase 0/1 interface meanings and compatibility at
`integration/mvp@80d41c5ca0e341263a7b0c683fae4b51be376c55`. The runtime stop gate
remains open.

## Frozen inputs and scope

- Person A Phase 1 schema remains `schema_version = "1.0"`.
- Person C C0 capture contract version remains `person_c_contract_version = "0.1"` at commit `b9c58f6`.
- C1 originally added layout and environment-lock contract version `0.1`.
  Additive layout schema `0.2` preserves every stable marker ID and adds an
  explicit canonical geometric role for C-to-E homography correspondence; it
  does not replace or reinterpret A or C0 fields, and v0.1 remains immutable.
- This change contains C1 configs, schemas, validators, tests, a read-only checker, and report/runbook templates only.
- C2, C3, C4, and C5 runtime/collection work is not claimed by this record.

## C0 status

- Interface packet, ownership matrix, RNG/tick lifecycle decision, synthetic accepted/rejected episodes, validator, and tests: committed at `b9c58f6`.
- C0 protected artifacts modified during C1: no.
- C0 regression result is established by the current repository test run; the
  exact final repair count is recorded in the repair handoff, not invented here.

## C1 structural status

- Six stable IDs: `layout_01`, `layout_02`, `layout_03`, `layout_04`, `layout_05`, `layout_06`.
- Common grammar: superflat 40-by-20 arena, three-block-high stone wall, parallel lane, start/shadow/reset/safe regions, camera/canonical pose, four non-magenta markers, scalar axis, and full world coordinates.
- Explicit conditions: `core`, `no_wall_visible`, `occluder_only_no_sheep`.
- Environment lock: structurally checkable template with unresolved observed versions/provenance.
- C-to-B: `build_state_input_from_capture_package` validates the complete C
  package, performs explicit capture-key joins, applies a validated B
  coordinate frame, binds A provenance, and emits the existing B state schema.
  No-object controls fail oracle-target handoff explicitly and remain available
  to their control consumers.
- C-to-E: layout v0.2 maps stable physical marker IDs to unique canonical
  roles; E homography v1.1 joins observations by stable ID and does not infer
  correspondence from order or image quadrant.
- Automated structural/compatibility tests exist. They are synthetic evidence,
  not runtime evidence.

## Runtime stop gate

The following claims have not been made and must remain **RUNTIME EVIDENCE REQUIRED LATER** until produced from a real Minecraft runtime:

- Minecraft server/client launch and approved lock comparison
- Installed mod and launcher artifact provenance
- Marker visibility and coordinate/block verification
- Canonical reference screenshots for all layouts
- Clean reconstruction of at least one layout
- Reference-versus-reconstructed real screenshot comparison
- Second-operator independent reconstruction

No scientific episode may be collected until the applicable runtime and reconstruction evidence is approved.

## Phase 0/1 review record and later requirements

- Person A: Phase 0/1 identity, capture-interface, RNG/event-order, and consumer
  compatibility review is approved at the checkpoint above. Future real
  canonical-pose/model-frame capture still requires runtime evidence.
- Person B: Phase 0/1 C-to-B projection, 20 Hz timing, visibility, no-object
  gating, RNG/event-order, and oracle-intake compatibility is approved at the
  checkpoint above. Real adapter rows and scientific results remain pending.
- Person E: Phase 0/1 stable-marker-ID to canonical-role and capture/measurement
  compatibility is approved at the checkpoint above. Real-camera calibration
  and homography qualification remain pending.
- Runtime owner: pin the observed Java/Fabric/Yarn/API/Gradle/Loom/launcher/mod versions, world seed, packs, and client graphics values without silently editing an approved lock.

## Signoff

- Central Phase 0/1 human signoff evidence:
  `docs/contracts/schema_v1_0_signed_record.md`.
- Person C interface/contract approval: recorded for
  `80d41c5ca0e341263a7b0c683fae4b51be376c55`.
- Person A boundary review: recorded for the same checkpoint.
- Person B boundary review: recorded for the same checkpoint.
- Person E boundary review: recorded for the same checkpoint.
- Runtime reconstruction review/date: **RUNTIME EVIDENCE REQUIRED LATER**
- Final C1 runtime stop-gate decision: not approved
