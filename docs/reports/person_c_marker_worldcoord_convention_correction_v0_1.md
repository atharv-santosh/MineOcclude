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

## Not resolved by this correction

- **layout_02 coverage:** two markers are clipped at the image border, so
  layout_02 is not evaluable regardless of world coordinates. It needs new
  border-safe geometry and a targeted recapture (Phase 2).
- **depth bracketing:** for five layouts the sheep lane (depth 6) sits ~0.5
  block beyond the far marker row (depth span ends 5.5) — a mild extrapolation.
  The convention bias dominated it; if any corrected layout still marginally
  misses, extend the far marker row past the lane depth (built into the Phase-2
  geometry, retrofittable to all six).
