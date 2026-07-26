# Person C → Person E handoff

Responses to all six items from E's report. Everything C owns is done;
the two co-owned completions (marker `image_xy` detection, `rgb` decode)
are E-owned and flagged where they occur.

## 1. Marker visibility — FIXED (was: 2 of 4 behind the camera)

Root cause confirmed exactly as you diagnosed: `ArenaBuilder` placed the far
marker row at `orthoMin + 2 = camOrtho − 1`, one block **behind** the camera.
Fixed: the far row is now `wallOrtho + 3` (beyond the wall, at the lane
extremes x = ±(laneMax−1), outside the wall's axis-shadow), so all four
markers are in-frame and unoccluded. **Verified visually on all 6 layouts**
(no-sheep captures ep9602–9607). Jar `be960a92…`.

Per-layout marker world coordinates (E fills `image_xy` by detection):
`markers_layout_00.json` … `markers_layout_05.json`.
Clean calibration frames (sheep absent, markers static, 640×360-normalizable):
`~/mineocclude-client/mineocclude_client_out/episode_960{2..7}/frames/`.

## 2. Marker image-point convention — CONFIRMED

Centre of the marker block's **top face** (blocks at y=3 occupy y=3→4; top
face y=4 = `sheep_y` foot-plane, so the homography is well-posed). Use the
top-face centre, not a raw blob centroid. Documented in every markers file.

## 3. Detector calibration / held-out split — C's HALF DELIVERED

`detector_calibration_inputs.json` + `calibration_frames/{visible,negative}/`.

C provides (authoritative):
- **72 labeled frames**, full coverage: 6 layouts × {visible, negative} ×
  {calibration, heldout}, 3 per cell.
- `truth_class`/`truth_present` = ground truth from server geometric
  visibility: **visible** = sheep present AND geometrically visible (clean
  committed pilots ep95xx); **negative** = no-sheep scene (ep9602–9607, wall +
  all 4 markers, so it also exercises wall/marker rejection).
- The **calibration/heldout split** (disjoint), `source_artifact_id`,
  `source_frame_idx`, `source_frame_hash`, and per-layout world markers.

E completes (E-owned) to pass `validate_detector_calibration_dataset`:
- each `markers[].image_xy` — detect on the calibration frames;
- each `frames[].rgb` + `decoded_rgb_hash` — decode the referenced `png_path`.
The C inputs doc carries `image_xy`/`rgb`/`decoded_rgb_hash` = null and an
extra `png_path` for exactly those steps; strip `png_path` in your final doc.

If you'd rather I emit a different split ratio or frame count, say so.

## 4. UTC timestamps — FIXED

`provenance_pilots_clean.json` re-emitted to second-precision `Z`
(`2026-07-25T20:51:46Z`), which parses with the registry's strict
`%Y-%m-%dT%H:%M:%SZ`. The capture recorder now emits `Z` form natively, so
future captures are correct at source.

## 5. Is ep9410 usable? — NO; superseded

Correct call not to use it. The marker geometry now comes from the fixed
no-sheep calibration captures (ep9602–9607), not ep9410. `markers_layout_00`
`source_trajectory_id` points at the clean no-sheep capture.

## 6. Remaining layouts — DONE

`markers_layout_01.json` … `markers_layout_05.json` produced alongside 00.

---

## Provenance note
The negative frames + marker captures (ep9602–9607) were collected after the
marker fix; that mod change is committed by the repo owner alongside this
handoff. The visible frames come from the previously committed clean pilots.
All `truth_class` labels are authoritative regardless of source.
