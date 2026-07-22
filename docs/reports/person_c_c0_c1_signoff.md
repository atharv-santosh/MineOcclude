# Person C C0/C1 signoff record

Status: C0 committed; C1 structural implementation pending review; runtime stop gate open.

## Frozen inputs and scope

- Person A Phase 1 schema remains `schema_version = "1.0"`.
- Person C C0 capture contract version remains `person_c_contract_version = "0.1"` at commit `b9c58f6`.
- C1 adds layout and environment-lock contract version `0.1`; it does not replace or reinterpret A or C0 fields.
- This change contains C1 configs, schemas, validators, tests, a read-only checker, and report/runbook templates only.
- C2, C3, C4, and C5 are not started by this change.

## C0 status

- Interface packet, ownership matrix, RNG/tick lifecycle decision, synthetic accepted/rejected episodes, validator, and tests: committed at `b9c58f6`.
- C0 protected artifacts modified during C1: no.
- C0 regression result: record after the complete test suite is run.

## C1 structural status

- Six stable IDs: `layout_01`, `layout_02`, `layout_03`, `layout_04`, `layout_05`, `layout_06`.
- Common grammar: superflat 40-by-20 arena, three-block-high stone wall, parallel lane, start/shadow/reset/safe regions, camera/canonical pose, four non-magenta markers, scalar axis, and full world coordinates.
- Explicit conditions: `core`, `no_wall_visible`, `occluder_only_no_sheep`.
- Environment lock: structurally checkable template with unresolved observed versions/provenance.
- Automated test result: record after review verification.

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

## Upstream review still required

- Person A: confirm canonical-pose/capture settings and future model-frame capture use remain compatible with the frozen trajectory/identity contract.
- Person B: confirm layout grouping, scientific condition fields, inclusion/exclusion use, and shadow/event interpretation after the Role B repair is current.
- Person E: confirm marker colors/blocks/coordinates, visibility at reveal, detector columns/provenance, and per-layout homography metadata.
- Runtime owner: pin the observed Java/Fabric/Yarn/API/Gradle/Loom/launcher/mod versions, world seed, packs, and client graphics values without silently editing an approved lock.

## Signoff

- Structural C1 author/date:
- Person A boundary review/date:
- Person B boundary review/date:
- Person E boundary review/date:
- Runtime reconstruction review/date: **RUNTIME EVIDENCE REQUIRED LATER**
- Final C1 stop-gate decision: not approved
