# Person C layout reconstruction checklist

Status: **RUNTIME EVIDENCE REQUIRED LATER**

This checklist is for reconstructing one approved Person C C1 layout from versioned definitions on a clean Minecraft 1.16.5 server/client pair. Completing this document requires a real runtime and a second operator; the repository template is not evidence that reconstruction occurred.

## Before reconstruction

- [ ] Record operator, reviewer, UTC date, host, branch, and commit.
- [ ] Select one of `layout_01` through `layout_06` from `configs/scenes/layouts.yaml`.
- [ ] Record the selected `layout_id`, layout `config_version`, and layout file SHA-256.
- [ ] Copy `configs/scenes/environment_lock.template.yaml` to the approved evidence location without overwriting the template.
- [ ] Set `template: false` in that evidence copy; never change this repository template into evidence in place.
- [ ] Replace every `RUNTIME EVIDENCE REQUIRED LATER` value in that evidence copy with observed runtime data or a traceable artifact reference.
- [ ] Run the environment checker without `--structure-only`; proceed only when it reports `runtime_ready: true`.
- [ ] Verify the running environment matches Minecraft 1.16.5, Java, Fabric Loader, Yarn, Fabric API, Gradle/Loom, launcher, installed mods, world seed, server properties, gamerules, time, weather, packs, resolution, FOV, and capture-affecting graphics settings.

## Rebuild from saved definitions only

- [ ] Use a clean/reset experimental area; do not use remembered placements.
- [ ] Recreate the superflat layers and exact 40-by-20-block arena bounds.
- [ ] Recreate the three-block-high stone wall at its full x/z/y bounds.
- [ ] Recreate the wall-parallel lane, sheep start region, occlusion shadow, reset area, and safe area.
- [ ] Recreate the camera anchor and canonical position, yaw, pitch, roll, and FOV.
- [ ] Place the four marker blocks at their saved full x/y/z coordinates; confirm that none is magenta.
- [ ] Verify the wall-parallel scalar axis, origin, positive direction, and `motion_sign`.
- [ ] Check that the planned lane passes through the sheep start region and occlusion shadow.

## Check all explicit conditions

- [ ] `core`: one wall and exactly one magenta sheep with color ID 2, NoAI, Silent, and PersistenceRequired.
- [ ] `no_wall_visible`: wall absent; sheep, lane, camera, markers, and environment unchanged from `core`.
- [ ] `occluder_only_no_sheep`: wall present; no sheep; camera, markers, and environment unchanged from `core`.
- [ ] Record the explicit `condition` field. Do not infer it from a path, folder, or screenshot.
- [ ] Reset between checks and confirm no entity, item, block, weather, or time state leaked from the previous condition.

## Runtime evidence

- [ ] Save the real startup manifest and environment-lock comparison output.
- [ ] Save coordinate/block checks for arena, wall, lane, shadow, reset/safe areas, markers, camera, and target count.
- [ ] Capture a real canonical screenshot and link it to layout/environment versions and hashes.
- [ ] Compare the new screenshot with the real reference screenshot and record visible drift; do not synthesize either image.
- [ ] Have a second operator repeat the reconstruction using only the repository definitions and this checklist.
- [ ] Record the second operator's independent outcome and artifact references.

Until every runtime item is completed with traceable artifacts, record each corresponding result exactly as **RUNTIME EVIDENCE REQUIRED LATER** and do not approve scientific collection.
