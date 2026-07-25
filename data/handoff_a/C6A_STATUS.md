# C6A handoff status — reconciled with Person A and Person E contracts

## Answers to your questions

- **Is C6A complete?** Yes — one fully accepted real trajectory, consumable
  by A, B, and E from the same rows. Passes the frozen C0 + schema-v1.0
  validator chain.
- **Commit SHA / branch:** branch `role/person-c-data`. This exact bundle
  (with the A-format action reconciliation) is in the working tree,
  uncommitted until the owner pushes.
- **Exact path:** `data/handoff_a/episodes/9410/`
- **Validator reports accepted?** Yes — `validate_capture_package` →
  ACCEPTED; `qa_report.json` status `accepted`.
- **Impulse & visibility real or synthetic?** Real. Impulse: server-scripted
  20° yaw step, pixel-verified at **offset 0** (`impulse_fixture_9440/`).
  Visibility: geometric server-authoritative; empirical from a real detector
  run.

## The trajectory: `episodes/9410/` (`layout_00_ep9410`)

129 accepted frames, arc visible→occluded→revealed, **4 ground markers
recorded** (for E's homography). Verified: consecutive server ticks ✓,
unique frame identities ✓, state=action=tick=frame_map=visibility=129 ✓,
valid final-frame action ✓, `trajectory_id`+`model_frame_idx` on every row ✓,
mp4 640×360 @ 20/1 fps 129 frames ✓.

## Reconciliation with your (A's) contract — the previous caveat is FIXED

**Raw actions are now in your official format.** `raw_actions.jsonl`
`raw_action` is `{"keyboard": {"keys": [...]}, "mouse": {"buttons": [...],
"dx": <yaw°>, "dy": <pitch°>}}` — the exact shape
`mineworld_adapter.convert_action` reads. Mapping verified **field-by-field
against your frozen golden matrix** (all 19 cases in
`phase3_wave2_action_matrix.json`) by
`tests/data/test_person_a_action_compat.py`:

- keys: w/s/a/d, space, left.shift, left.control, q, `key.keyboard.<n>`
  (hotbar switch only)
- mouse buttons: attack→0, use→1, pickItem→2
- camera: C `camera_dx`→`mouse.dx` (yaw°), `camera_dy`→`mouse.dy` (pitch°) —
  **units are degrees on both sides**, matched to your `dx=12.0`/`dy=-8.0`
  cases.

So your converter consumes `raw_actions.jsonl` **drop-in**. Regenerate the
authoritative 11 tokens from it with `convert_action`
(`vocabulary_offset=8192`, roles bos/camera_pitch/camera_yaw/hotbar/
forward_back/left_right/sprint_sneak/use_attack/jump/drop_pick/eos).
`mineworld_actions.jsonl` tokens remain C-reference only — do not certify
against them (this is by design: token vocabulary is yours).

## Correct ownership boundaries (not defects — your steps run on C's evidence)

- **Preprocessing is yours.** C ships the preserved 640×360 source PNGs
  (`frames_640x360/`, hashed in `frame_map.parquet`). Your golden spec
  (BGR→RGB, 384×224 `cv2.INTER_LINEAR`, /255 then Normalize mean/std 0.5,
  CHW, float32) runs on them; C asserts no `preprocess_hash`.
- **VAE/336-token count** is your GPU step; not asserted here.
- **Empirical detector**: C's `visible_flag` uses the interim RGB detector
  (`detector_id = interim_rgb_magenta_v0`); E's frozen HSV detector replaces
  it and consumes the same frames + the 4 recorded markers. Not used by your
  teacher-forcing path.

## Remaining honest notes (do not block your certification)

- **`tick_broadcast.jsonl` is reconstructed** 1:1 from `server_state.jsonl`
  (the mod broadcasts one packet per logged tick but does not separately
  file-log it); `client_tick.jsonl` is the native receipt evidence.
- **Camera is server-locked** in this trajectory, so causal-order proof is
  the separate scripted impulse fixture (`impulse_fixture_9440/`), per the
  manual's dedicated-impulse-episode design.
- **Duration condition label** is not controlled (reveal-window captures the
  full natural occlusion). Irrelevant to single-trajectory adapter
  certification; do not bin by hidden-duration.

## What you do
1. Preprocess `frames_640x360/` with your pinned path.
2. Tokenize `raw_actions.jsonl` with `convert_action` (drop-in, verified).
3. Select your 8–15-pair window from the 129 frames → CPU preflight → AWS.
