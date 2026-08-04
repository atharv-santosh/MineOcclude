# Detector pixel-space correction (v0.1)

Date: 2026-07-27
Owner: Person C
Scope: the 68 C7 production bundles `data/autonomous/layout_{01..06}_ep1xxxx`

## Defect

`add_interim_empirical_visibility` ran the interim magenta detector over
`frame_map["frame_abspath"]` — the **raw client framebuffer**, which is the
native window size (1280×720 on this Retina display) — while every contract
that consumes the result declares a 640×360 source frame
(`configs/scenes/layouts.yaml`, `data/handoff_e/markers_layout_*.json`).

Exported `blob_cx`/`blob_cy` were therefore at **2× the declared scale**;
observed values reached `blob_cx = 941` on a nominally 640-wide frame. Any
homography or reprojection fitted against those centroids would have been
wrong by a factor of two.

## Fix

`src/mineocclude/data/visibility.py`:

- The detector now reads `frame_640_path` (the canonical 640×360 source).
  The frame column is a named constant, and a missing column is a hard error
  rather than a silent fallback.
- Detections outside the declared 640×360 frame now raise instead of being
  exported. This is the check that would have caught the original defect.
- Each row records `detector_frame_space` so the pixel space is explicit in
  the data rather than implied.

The 68 production frame maps were regenerated from the canonical frames.
`data/handoff_e/README.md` now directs Person E to `frames_640x360/` rather
than `frames/`.

## Impact on labels — none

`visible_flag = geometric_visible AND empirical_magenta_visible` is
**unchanged in all 68 bundles**. Re-detection flipped `empirical_visible` on
12 frames across 9 bundles, but every one of those frames has
`geometric_visible = False`, so the conjunction was already `False`.

No episode's accepted/excluded status changed, and no occlusion/reveal event
changed. The detector's area threshold is an area *fraction*, so it is
scale-invariant; only sub-pixel magenta at the wall edge behaved differently
between the 2× and 1× rasterizations.

## Superseded diagnostic counts in sealed QA reports

The sealed `qa_report_*.json` files are **not edited** — `qa_report.py`
refuses to overwrite an existing report, and C4.8 requires acceptance
evidence to stay immutable. For the nine bundles below, the
`visibility_labels_present.measured.quarantined` count in the sealed report
is superseded by the regenerated frame map. The `visible`/`hidden` counts
and the `accepted` status in those reports remain correct.

| Bundle | quarantined (sealed report) | quarantined (corrected frame map) |
|---|---|---|
| `layout_01_ep10021` | 17 | 16 |
| `layout_01_ep10056` | 11 | 10 |
| `layout_02_ep10012` | 9 | 10 |
| `layout_02_ep10049` | 8 | 9 |
| `layout_04_ep10045` | 11 | 10 |
| `layout_06_ep10019` | 3 | 4 |
| `layout_06_ep10026` | 3 | 4 |
| `layout_06_ep10043` | 7 | 6 |
| `layout_06_ep10063` | 5 | 6 |

The frame map is authoritative for these counts.

## Not in scope

The legacy C6 pilot bundles (`*_ep9xxx`) were **not** regenerated; their
`blob_*` columns remain in the raw 1280×720 space. They are legacy
engineering evidence per
`docs/decisions/person_c_layout_id_supersession_v0_1.md` and back no
scientific claim. Person E's marker and calibration inputs do not use them —
the committed `data/handoff_e/calibration_frames/*.png` are already 640×360.

This correction does not change the fact that the empirical channel is still
produced by Person C's **interim** detector (`interim_rgb_magenta_v0`).
Importing Person E's frozen detector (C5.3) remains open and externally
blocked.
