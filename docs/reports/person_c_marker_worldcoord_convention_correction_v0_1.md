# Marker world-coordinate convention correction (v0.1)

Date: 2026-07-27
Owner: Person C
Scope: `data/handoff_e/markers_layout_01..06.json` (homography world points).

## Defect

Person E's Phase-2.4 localization gate failed on all evaluable layouts with a
**constant-sign** wall-parallel error: median 0.4221485104262732 blocks, p95
0.5884724982493275 blocks (gates: median <= 0.2, p95 < 0.5). All 30 evaluable
v0.2 errors had the same sign.

Root cause: the marker `world_xz_blocks` recorded the marker **BlockPos** — the
block's minimum corner (integers, e.g. layout_01 `[-7, 1]`) — while
`marker_image_point_convention` detects the **centre of the marker block's top
face**. A block at `BlockPos(X, Z)` has its top-face centre at
`(X + 0.5, y+1, Z + 0.5)`. So every marker's world point was offset from its own
image convention by a uniform `(-0.5, -0.5)`. Fitting a homography on that
inconsistent pairing produces a uniformly translated ground frame; localizing
the (correctly centre-referenced, continuous) sheep foot-origin then inherits a
constant ~0.5-block wall-parallel bias.

This is exactly why a probe-derived `+0.5` output correction "works" and is
nonetheless wrong: it fits the symptom. The cause is the input world coordinate.

## Proof (no evaluation probe used)

Synthetic pinhole homography over each layout's real marker rectangle:

- corner-labelled markers -> **0.5000** median abs wall-parallel error, all same
  sign (negative);
- top-face-centre-labelled markers -> **0.0000**.

The observed real value (0.4221) is the ideal 0.5 trimmed by perspective
foreshortening and detection spread (p95 - median = 0.166).

## Fix

`world_xz_blocks := BlockPos + (0.5, 0.5)` (top-face centre); the y-plane is
unchanged at 4 (the sheep foot-plane). Applied to all six marker files. Each
marker retains `world_xz_blocks_previous_corner` and a
`marker_convention_correction` block. `world_coordinate_system` is now
`ground_plane_world_xz_blocks_topface_centre`. The sheep foot-origin probe
points are the continuous entity position (already centre-referenced) and are
**unchanged**.

Mod source is corrected at the record site so future captures are born correct:
`EpisodeManager.writeLayoutMarkers` now emits `world_x/world_y/world_z`
(top-face centre) alongside the raw block `x/y/z`.

Expected post-fix gate for the five in-frame layouts: systematic bias removed
=> median ~= 0, p95 ~= 0.17 (detection spread only), inside both gates. No
recapture required for those five.

## Phase 2 — layout_02 coverage recapture (DONE)

layout_02 had two markers clipped at the image border (near row at shallow depth,
lane extremes, >half-FOV off-axis), so it was not evaluable regardless of world
coordinates. Fixed with **marker geometry v2**: a deeper row projects *more
central* (toward the wall), so the far row must be *wider* than the near row to
clear the wall silhouette. The geometry is runtime-tunable via the new
`mineocclude markergeom <nearOrtho> <farOrtho> <nearInset> <farInset>` command;
layout_02 uses `markergeom 0 7 5 0` (near row in front of the wall, far row at
the lane extremes behind it). All four markers verified in-frame with >=111px
border margin by colour detection; the quad area is 77 blocks^2 (well-posed
homography) and brackets the sheep depth (6).

Regenerated from clean captures (`git_dirty=false`, jar `aea241ec`):
- `markers_layout_02.json` — top-face-centre world coords, born correct from the
  mod (`world_x/world_z`); source `layout_02_ep31002` (nosheep);
- `calibration_frames/{visible,negative}/layout_02/` — 6+6 clean frames
  (visible from `ep31001`, negative from `ep31002`);
- `detector_calibration_inputs.json` / `independent_probe_points.json` — layout_02
  entries rebuilt (12 detector, 6 probe; splits 3 calibration / 3 heldout);
- `provenance_calibration_clean.json` — ep31001/ep31002 added.

## Residual note

For the five non-recaptured layouts the sheep lane (depth 6) sits ~0.5 block
beyond the far marker row — a mild extrapolation the convention bias had
dominated. If any corrected layout still marginally misses the gate, extend its
far marker row past the lane depth (the same geometry v2 lever, retrofittable).
