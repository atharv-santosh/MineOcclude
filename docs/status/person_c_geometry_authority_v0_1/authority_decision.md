# Person C geometry authority decision v0.1

## Decision

`MIXED_OR_VERSIONED_GEOMETRY`

No geometry owner or geometry version is accepted by this audit. `ACCEPTED_GEOMETRY_OWNER=UNRESOLVED` and `ACCEPTED_GEOMETRY_VERSION=NONE`. The conflict is not resolved; it requires direct observation during C1.1.

This is not an ownership tie-break. C normally owns world/layout geometry, but ownership of the schema does not prove that a mutable runtime constructed it. The evidence demonstrates at least three runtime generations and does not supply an authoritative receipt for the geometry to use next.

## Evidence supporting the decision

1. C's `person-c-layout-config-v0.3` is specification-only. Every runtime-evidence field in `configs/scenes/layouts.yaml` says `RUNTIME EVIDENCE REQUIRED LATER`.
2. The HEAD Fabric builder's default marker rule (builder-v2) constructs neither C nor E marker coordinates for any of the six layouts. It also constructs a dynamic grass arena rather than C's declared 40 by 20 smooth-stone arena. It does construct the C-derived layout choice, wall/lane axes, and camera pose.
3. Exact older `layout_meta.json` receipts prove a pre-builder-v1 marker geometry that differs from C, E, and HEAD.
4. Historical builder-v1 source at commit `1dc322af7e461b9a4744c177e9e40b02f10b2e58` placed marker blocks whose x/z positions equal C's declared x/z positions. The E layout 01, 04, 05, and 06 top-face-centre points identify those same physical blocks, but that physical equivalence does not make the literal coordinate records equal and does not prove the current runtime.
5. E layout 02 and 03 files claim recaptures made after a live `markergeom 0 7 5 0` override. The committed capture command lists, provenance, and reset receipts do not record the command or its resulting marker blocks. The override is mutable process-global state.
6. The six capture frame maps observe camera feet position plus eye height and yaw/pitch. The 70-degree FOV is specification-only, and the observed development environment explicitly leaves the production C1.1 client lock pending. Historical raw frames were 1280 by 720; canonical E inputs are 640 by 360.
7. No committed E homography matrix, fit hash, fit output, or held-out fit-validation report was found. E marker `image_xy` values are null. The phase-3 authority package validates bindings and wall-axis direction but explicitly does not refit E matrices.
8. The focused Python compatibility run reports one literal C/E marker mismatch per layout. Existing Python layout validation checks schema/internal constraints, not Fabric builder equivalence.

The complete literal comparison is in `geometry_conflict_matrix.json`; builder generations and positions are in `runtime_builder_comparison.json`.

## Accepted geometry and versioning consequences

Accepted geometry version: **NONE**.

C layout update required: **True**. If C1.1 accepts the current builder geometry, C must issue a new, immutable C-owned layout version. `person-c-layout-config-v0.3` must not be edited or silently reinterpreted. If C1.1 instead deliberately restores a prior geometry, that restored builder/JAR and its new authority binding still require an explicit version and fresh receipts.

E homography refit required: **True** for any new screenshot or C6A capture under the subsequently accepted geometry. All six layouts are affected. A historical E artifact may remain usable only inside its explicit capture/version applicability boundary; this audit does not certify any existing fit because no fitted matrix and validation record are committed.

## Affected historical artifacts

The affected set includes all six `data/handoff_e/markers_layout_*.json` files, `detector_calibration_inputs.json`, `independent_probe_points.json`, the phase-3 homography authority package, the historical +0.5 convention-correction report, the six calibration capture provenance/frame-map records, and the older server `layout_meta.json` receipts. The exact impacts and source identities are enumerated in `downstream_impact_report.json`.

These artifacts remain evidence of their own historical states. They are not proof of a single geometry across builder generations.

## Supersession and frozen evidence

Do not edit frozen scientific evidence. Do not alter existing C specifications, E marker files, captures, frame maps, calibration inputs, homography records, or reset receipts to manufacture agreement.

Supersession is additive only. A successor must use a new version identifier and state its predecessor, accepted builder commit and Git blob, built JAR hash, clean-server identity, exact runtime-observed block and world coordinates, camera/resolution lock, capture IDs, and applicability interval. Historical records remain addressable and must not be redirected through hidden offsets, layout-ID shifts, +0.5 corrections, coordinate renumbering, or compatibility adapters.

The legacy-to-current mapping (`layout_00` to `layout_01`, ..., `layout_05` to `layout_06`) is capture lineage from the historical rename. It is not a geometry transform. The layout 02 and 03 recaptures already use one-based IDs; their `legacy_layout_id` fields do not authorize shifting IDs.

## Exact prerequisites before screenshots or new C6A capture

No screenshot set or new C6A capture is authorized until every item below is satisfied:

1. Start C1.1 from a clean server process/world with no inherited `markergeom` state; record the server commit, `ArenaBuilder.java` and `Layouts.java` Git blobs, built JAR SHA-256, Minecraft/Fabric versions, seed, and reset command.
2. Select and assign one new immutable C-owned geometry version. State whether it intentionally uses HEAD builder-v2, restores builder-v1, or introduces another explicit construction. Do not reuse or edit `person-c-layout-config-v0.3`.
3. For layouts 01 through 06, execute reset and persist a machine-readable receipt containing the requested/resolved layout ID, wall axis and sign, floor/wall bounds and materials, every marker block `BlockPos`, every exported marker world point/convention, sheep spawn/lane, and camera feet/eye pose and yaw/pitch/roll.
4. Prove from those receipts that the running builder constructed exactly the new C version. Add and pass a validator comparing C's declared geometry with Fabric's runtime output for all six layouts.
5. Lock the capture client and record raw framebuffer width/height, canonical output width/height, normalization method, pixel-centre convention, FOV, GUI scale, fullscreen/window state, and any other projection-affecting setting. FOV and resolution must be observed, not inherited only from a template.
6. Generate new E marker correspondences directly from the receipted world blocks and the captured canonical frames. Record source capture IDs and source file hashes. Do not correct or adapt historical coordinates.
7. Refit all six E homographies against exactly those accepted world points and canonical image points. Commit each matrix, input manifest, algorithm/version, fit hash, residual metrics, and degeneracy diagnostics.
8. Perform independent held-out validation for all six fits, including the known positive wall-axis direction check, and publish pass/fail thresholds and results tied to the accepted geometry/camera/resolution version.
9. Publish a new applicability/supersession manifest that bounds both the new C geometry and E fits to the recorded runtime/capture version, then have the focused C/E and builder-layout validators pass without changing historical evidence.

Until these prerequisites are met, the exact blockers are: `C1.1_FRESH_RUNTIME_BLOCK_RECEIPTS`, `MARKER_OVERRIDE_STATE_NOT_RECEIPTED`, `FOV_AND_RAW_RESOLUTION_NOT_RUNTIME_LOCKED`, `NO_COMMITTED_E_HOMOGRAPHY_FIT_OR_VALIDATION`, and `ACCEPTED_GEOMETRY_VERSION_NOT_ASSIGNED`.
