# Person C — layout_id supersession and legacy mapping (v0.1)

Date: 2026-07-27
Owner: Person C
Status: ACCEPTED
Supersedes: the open item "Mod-internal layouts vs frozen `layouts.yaml`" in
`docs/decisions/person_c_prototype_adoption_v0_1.md`

## Problem

Two layout identifier namespaces existed simultaneously:

- The prototype mod's table (`fabric/mineocclude-mod/.../Layouts.java`) used
  zero-based ids `layout_00`–`layout_05`.
- The frozen C1 contract (`configs/scenes/layouts.yaml`) uses one-based ids
  `layout_01`–`layout_06`.

Every episode captured before commit `1f1937a` therefore carries a
`layout_id` that either does not resolve against the frozen contract
(`layout_00`) or resolves to the **wrong geometry** (`layout_01`–`layout_05`
are each one layout short of their contract meaning).

This affects the C6A/C6B pilot evidence and the Person C → Person E handoff.
It does not affect the C7 production collection, which was captured after the
mod was corrected.

## Mapping

| Legacy (mod-internal) | Frozen contract |
|---|---|
| `layout_00` | `layout_01` |
| `layout_01` | `layout_02` |
| `layout_02` | `layout_03` |
| `layout_03` | `layout_04` |
| `layout_04` | `layout_05` |
| `layout_05` | `layout_06` |

## Evidence that this is a pure rename

The mapping is an identifier shift only; no geometry changed. Three
independent confirmations:

1. **Source diff.** In `1f1937a`, `Layouts.java` re-registers the same six
   layouts with byte-identical geometry parameters and only the id string
   shifted by one. No numeric argument changed in any row.

2. **Observed capture geometry.** For each legacy pilot, the observed camera
   position, lane axis, and lane fixed-coordinate match the frozen contract
   entry one higher, exactly:

   | Legacy | observed (cam_x, cam_z, lane_fixed, axis) | Contract |
   |---|---|---|
   | `layout_00` | `(0.5, -5.5, 6, x)` | `layout_01` |
   | `layout_01` | `(-5.5, 0.5, 6, z)` | `layout_02` |
   | `layout_03` | `(0.5, -5.5, 8, x)` | `layout_04` |
   | `layout_04` | `(0.5, -4.5, 5, x)` | `layout_05` |
   | `layout_05` | `(-6.5, 0.5, 7, z)` | `layout_06` |

   (`layout_02` shares a camera pose with `layout_00` in the contract and is
   disambiguated by wall extent and marker span; its position in the ordered
   sequence is unambiguous.)

3. **Marker world coordinates.** `data/handoff_e/markers_layout_00.json`
   records markers at x=±7, z∈{1,5}. The frozen contract's `layout_01`
   records `world_blocks` at exactly x=±7, z∈{1,5}.

## Decision

1. **The C7 production collection is the sole scientific dataset.**
   `data/autonomous/layout_{01..06}_ep1xxxx` carry contract-correct
   `layout_id` values and are the only episodes that may back a scientific
   claim.

2. **The C6 pilot bundles are legacy engineering evidence.**
   `data/autonomous/*_ep9xxx` retain their as-captured `layout_id`. Their
   sealed `qa_report_*.json` files and SHA-256 sidecars are **not** edited —
   `qa_report.py` refuses to overwrite an existing report, and rewriting a
   sealed acceptance record to change its meaning is precisely what C4.8 and
   C7.4 forbid. Their ids are interpreted through the table above.

3. **The Person E handoff is corrected**, because it is an active input to a
   downstream role rather than a sealed historical record. See below for
   exactly what was and was not rewritten.

## What is rewritten in `data/handoff_e/`, and what is not

Corrected to the frozen contract (these are semantic join keys; a consumer
that resolves them against `layouts.yaml` must get the right geometry):

- `layout_id`
- `canonical_camera_pose_id`, `marker_set_id`
- `markers_layout_NN.json` filenames
- `calibration_frames/{visible,negative}/layout_NN/` directory names and the
  `frame_id` values that reference them
- `marker_set_source_hash` (recomputed after the marker files change)

Preserved verbatim (these are historical facts about what was executed; a
provenance record that is rewritten to look correct is no longer provenance):

- `trajectory_id`, `source_trajectory_id`, `episode_id`
- `capture_command` — including the literal `mineocclude start layout_00 …`
  arguments as issued to the prototype mod
- `seed`, `start_utc`/`end_utc`, `git_sha`, `capturing_jar_sha256`

Each corrected file carries a `layout_id_correction` block naming this
decision record, so the two namespaces are never silently conflated.

## Prevention

`tests/data/test_layout_id_resolves.py` asserts that every `layout_id`
appearing in a committed manifest or handoff artifact resolves against
`configs/scenes/layouts.yaml`, and that every Person E marker set matches
that layout's `world_blocks`. This fails on any reintroduction of an
unresolvable id.

The mod's `Layouts.get()` currently falls back to `layout_01` for an unknown
id, which would silently build the wrong arena for a typo'd or legacy id.
Converting that to a hard rejection is tracked separately as a C2.3/C2.7
fail-open defect and is not part of this change.
