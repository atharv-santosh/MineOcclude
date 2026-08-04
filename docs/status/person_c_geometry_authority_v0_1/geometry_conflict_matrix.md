# Person C versus Person E geometry conflict matrix

## Scope and comparison convention

All coordinates below are copied literally from the records. Delta is `E - C` as `[dx, dy, dz]`. No offset, +0.5 correction, layout-ID shift, renumbering, or adapter was applied.

C source for every row is `configs/scenes/layouts.yaml`, version `person-c-layout-config-v0.3`, source commit `1f1937ad850b2476aca528032410a1938d0abe7f`, Git blob `55b609d343cea47c098e01921018bd3b9a1e405d`, SHA-256 `5a39d2dcae44d72f07b0e645dcc3e64ea6178ef79f1c9e3f12bff11f857f82cb`. Its coordinates are specification-only; its runtime-evidence fields are all `RUNTIME EVIDENCE REQUIRED LATER`.

E calls its coordinates `ground_plane_world_xz_blocks_topface_centre` at y=4. C records integer x/y/z `world_blocks`; its x/z values equal historical builder-v1 marker `BlockPos` values while y=4 is the marker top/sheep-foot plane. This hybrid C declaration is reported literally and is not silently converted.

## Coordinate matrix

| Layout | Marker | C world xyz | E world xyz | Exact E-C delta |
|---|---|---:|---:|---:|
| 01 | blue | `[-7,4,1]` | `[-6.5,4,1.5]` | `[0.5,0,0.5]` |
| 01 | yellow | `[7,4,1]` | `[7.5,4,1.5]` | `[0.5,0,0.5]` |
| 01 | lime | `[-7,4,5]` | `[-6.5,4,5.5]` | `[0.5,0,0.5]` |
| 01 | white | `[7,4,5]` | `[7.5,4,5.5]` | `[0.5,0,0.5]` |
| 02 | blue | `[1,4,-7]` | `[0.5,4,-2.5]` | `[-0.5,0,4.5]` |
| 02 | yellow | `[1,4,7]` | `[0.5,4,3.5]` | `[-0.5,0,-3.5]` |
| 02 | lime | `[5,4,-7]` | `[7.5,4,-7.5]` | `[2.5,0,-0.5]` |
| 02 | white | `[5,4,7]` | `[7.5,4,8.5]` | `[2.5,0,1.5]` |
| 03 | blue | `[-8,4,1]` | `[-3.5,4,0.5]` | `[4.5,0,-0.5]` |
| 03 | yellow | `[8,4,1]` | `[4.5,4,0.5]` | `[-3.5,0,-0.5]` |
| 03 | lime | `[-8,4,5]` | `[-8.5,4,7.5]` | `[-0.5,0,2.5]` |
| 03 | white | `[8,4,5]` | `[9.5,4,7.5]` | `[1.5,0,2.5]` |
| 04 | blue | `[-7,4,2]` | `[-6.5,4,2.5]` | `[0.5,0,0.5]` |
| 04 | yellow | `[7,4,2]` | `[7.5,4,2.5]` | `[0.5,0,0.5]` |
| 04 | lime | `[-7,4,6]` | `[-6.5,4,6.5]` | `[0.5,0,0.5]` |
| 04 | white | `[7,4,6]` | `[7.5,4,6.5]` | `[0.5,0,0.5]` |
| 05 | blue | `[-6,4,1]` | `[-5.5,4,1.5]` | `[0.5,0,0.5]` |
| 05 | yellow | `[6,4,1]` | `[6.5,4,1.5]` | `[0.5,0,0.5]` |
| 05 | lime | `[-6,4,5]` | `[-5.5,4,5.5]` | `[0.5,0,0.5]` |
| 05 | white | `[6,4,5]` | `[6.5,4,5.5]` | `[0.5,0,0.5]` |
| 06 | blue | `[2,4,-8]` | `[2.5,4,-7.5]` | `[0.5,0,0.5]` |
| 06 | yellow | `[2,4,8]` | `[2.5,4,8.5]` | `[0.5,0,0.5]` |
| 06 | lime | `[6,4,-8]` | `[6.5,4,-7.5]` | `[0.5,0,0.5]` |
| 06 | white | `[6,4,8]` | `[6.5,4,8.5]` | `[0.5,0,0.5]` |

All six layouts are conflicted under literal equality.

## Layout IDs, axes, camera, and resolution

Camera feet pose, yaw, and pitch are runtime-observed in the capture-specific `frame_map.parquet`. Eye y is `5.6200000047683725` (feet y 4 plus observed eye height). Roll 0 and vertical FOV 70 degrees are declarations; FOV is not runtime-locked. Canonical E resolution is 640 by 360 with pixel-centre coordinates; its template source is commit `4b724329338d9251697f458ce182efcbaf27a312`, Git blob `75e97445ccb1cdd504ab3b15e89f4d4e3afb9d4f`. The historical raw framebuffer was 1280 by 720, recorded by `data/handoff_e/README.md` at source commit `487532ba1e7745fe07174090c0851269fb70a6a7`, Git blob `bc2fc81cd7eebbb3a3452346eddc394d12c14f42`.

| Current layout | Historical lineage / capture | Wall axis and positive direction | Camera feet xyz | Yaw/pitch/roll | Image |
|---|---|---|---:|---:|---:|
| 01 | `layout_00` / `layout_00_ep9762` | x / increasing x | `[0.5,4,-5.5]` | `[0,0,0]` | `640x360` |
| 02 | `layout_01` lineage; current-ID recapture `layout_02_ep31002` | z / increasing z | `[-5.5,4,0.5]` | `[-90,0,0]` | `640x360` |
| 03 | `layout_02` lineage; current-ID recapture `layout_03_ep33005` | x / increasing x | `[0.5,4,-5.5]` | `[0,0,0]` | `640x360` |
| 04 | `layout_03` / `layout_03_ep9768` | x / increasing x | `[0.5,4,-5.5]` | `[0,0,0]` | `640x360` |
| 05 | `layout_04` / `layout_04_ep9770` | x / increasing x | `[0.5,4,-4.5]` | `[0,0,0]` | `640x360` |
| 06 | `layout_05` / `layout_05_ep9772` | z / increasing z | `[-6.5,4,0.5]` | `[-90,0,0]` | `640x360` |

The zero-based to one-based relation is historical rename lineage only. It must not be applied as a layout-ID compatibility shift. Layouts 02 and 03 already use the current IDs in their recaptures.

## Source identity and runtime status by layout

| Layout | E marker source commit / Git blob | Capture source and runtime commit | Coordinate evidence | Does HEAD build C? | Did E fit the same geometry? |
|---|---|---|---|---|---|
| 01 | `3cc5f619689da42e4d6a01c319d2ce1d3636d356` / `e65374b0f980c564c51cf43f399a56be1cbce838` | provenance blob `0fbdfeb974c37425762805099dea97021147415b`; runtime `1dc322af7e461b9a4744c177e9e40b02f10b2e58` | C spec-only; E capture-associated, marker blocks unreceipted | No | Not proven |
| 02 | `aa2e8ed127b829092e866af1f2c099acc3a20051` / `5e929b4e246d4914047a389b631954f9a05277af` | provenance blob `d2f47f3f71a5d3e8ed0f4053b2d9e374746f4a91`; runtime `3cc5f619689da42e4d6a01c319d2ce1d3636d356` | C spec-only; E override claim unreceipted | No | Not proven |
| 03 | `fa70424530f422a2e6140e0e90d0ff18f583141e` / `42d37b75b8f88e9401c90e52b1f9a4173fcf96a6` | provenance blob `b33a69cb2ef667e284edd8eb58a317b9a8eb1b4a`; runtime `aa2e8ed127b829092e866af1f2c099acc3a20051` | C spec-only; E override claim unreceipted | No | Not proven |
| 04 | `3cc5f619689da42e4d6a01c319d2ce1d3636d356` / `6e427a71782c01ea2de74afe9b2c6e07ecda4459` | provenance blob `871b7fb578db55eee7fb6e268bebb837c26aa399`; runtime `1dc322af7e461b9a4744c177e9e40b02f10b2e58` | C spec-only; E capture-associated, marker blocks unreceipted | No | Not proven |
| 05 | `3cc5f619689da42e4d6a01c319d2ce1d3636d356` / `788babe0413151a1ad633387f7968f76e966e842` | provenance blob `26664aa4475823b589922488c03d0b0840229d39`; runtime `1dc322af7e461b9a4744c177e9e40b02f10b2e58` | C spec-only; E capture-associated, marker blocks unreceipted | No | Not proven |
| 06 | `3cc5f619689da42e4d6a01c319d2ce1d3636d356` / `f7bfeacf10df3b06ff9f693770f2106af2fe4b32` | provenance blob `07a9bc100b1498dd7be231da6528306d184fa87d`; runtime `1dc322af7e461b9a4744c177e9e40b02f10b2e58` | C spec-only; E capture-associated, marker blocks unreceipted | No | Not proven |

`ArenaBuilder.java` at HEAD is source commit `3cc5f619689da42e4d6a01c319d2ce1d3636d356`, Git blob `3c157928d2e001cb4cc7fc0c3de12f66e2562727`. Its default marker positions match neither C nor E in all six layouts; it also builds grass with dynamic bounds rather than C's full declared arena. Historical builder-v1 at commit `1dc322af7e461b9a4744c177e9e40b02f10b2e58`, blob `0a319c947d00368d2bd1701e38b3c32929d22066`, constructed C's x/z marker block positions and underlies E captures 01, 04, 05, and 06. Older observed receipts record yet another geometry.

## Downstream dependence

Every row feeds or constrains `data/handoff_e/detector_calibration_inputs.json`, `data/handoff_e/independent_probe_points.json`, and `data/handoff_e/phase3_homography_authority_v0_1/`, as well as capture-specific screenshots and any future C6A geometry. The detector input aggregation contains stale integer C/corner coordinates and old hashes relative to the current E marker/recapture records. The phase-3 package supplies binding and direction records but no E fit matrix or held-out fit validation. See `downstream_impact_report.json` for supersession requirements.

## Classification

`MIXED_OR_VERSIONED_GEOMETRY` is the only evidence-supported classification. C matches a historical builder-v1 block placement, E 01/04/05/06 expresses the centres of those physical blocks, E 02/03 claims an unreceipted override, older receipts prove a different generation, and HEAD defaults match neither. A clean C1.1 runtime observation is required before accepting an owner/version.
