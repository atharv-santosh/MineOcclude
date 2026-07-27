# Person C → Person E handoff

Machine-readable files are authoritative; this README follows them. All
marker/calibration artifacts derive from the clean calibration captures
**ep9761–ep9772** (per layout: odd ep = normal/visible source, even ep =
nosheep/negative+markers), collected on committed code with
`git_dirty=false`. Provenance: `provenance_calibration_clean.json`.

## 1. Marker visibility — FIXED

Root cause confirmed as you diagnosed: the far marker row was at
`camOrtho − 1` (one block behind the camera). Fixed to `wallOrtho + 3`
(beyond the wall, at the lane extremes, outside the wall's axis-shadow);
all four markers are now in-frame and unoccluded, **verified on all 6
layouts**. World coords: `markers_layout_00.json … markers_layout_05.json`
(`source_trajectory_id` names the clean nosheep capture per layout). Detect
`image_xy` on that capture's frames
(`~/mineocclude-client/mineocclude_client_out/episode_976{2,4,6,8},977{0,2}/frames/`).

## 2. Marker image-point convention — CONFIRMED

Centre of the marker block's **top face** (y=4 = `sheep_y` foot-plane;
homography well-posed). Not a raw blob centroid.

## 3. Independent probe points — the homography error gate (your BLOCKER)

You're right: 4 markers determine the homography exactly (zero reprojection
error by construction), so they cannot evidence the ≥0.2-block median / 0.5
p95 gate. Delivered your option (b): **`independent_probe_points.json`** —
36 points (6 visible calibration frames × 6 layouts), each the authoritative
sheep **foot** world (x,z) at `y=4.0` (on the homography plane).
- These are **separate** from the 4 markers → valid gate evidence.
- The sheep sits at z≈6, ~5 blocks **beyond the marker hull** (markers span
  z∈[1,5]) — exactly the extrapolation region you flagged.
- World coords only; detecting the sheep **ground-contact** pixel (its base,
  not the body centroid) is yours.

If you'd rather have static extra ground markers instead of the sheep, say
so — that's a mod change + re-collection, but doable.

## 4. Detector calibration / held-out split

`detector_calibration_inputs.json` + `calibration_frames/`: 72 labeled
frames, full coverage (6 layouts × {visible, negative} × {calibration,
heldout}, 3 each). `truth_class`/`truth_present` are authoritative ground
truth from server geometric visibility (visible = sheep present &
geometrically visible; negative = no-sheep, which also exercises wall/marker
rejection). **Passes your `validate_detector_calibration_dataset`** once you
fill each `markers[].image_xy` (detection) and each `frames[].rgb` +
`decoded_rgb_hash` (decode `png_path`), then strip `png_path` + the 3
doc-only root keys. All frames from the clean ep9761–9772 captures.

## Provenance & registration

- `provenance_calibration_clean.json` — for all 12 calibration captures
  (ep9761–9772): `seed`, `capture_command`, `start_utc`/`end_utc` (Z,
  second-precision), `git_dirty=false`, `git_sha`, `capturing_jar_sha256`,
  `capture_package_sha256`. (Closes the earlier gap where the calibration
  captures had no aggregated provenance record — the ep95xx
  `provenance_pilots_clean.json` covers the *pilot* trajectories, a
  different set.)
- `provenance_pilots_clean.json` — the 10 ep95xx MVP pilots; timestamps in
  Z second-precision form (registry-parseable).

## ep9410

Not used for markers. Marker geometry comes from the clean nosheep
calibration captures (ep9762…9772), not ep9410.
