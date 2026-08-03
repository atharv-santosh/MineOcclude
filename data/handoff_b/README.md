# Person C → Person B handoff

## What B receives

For each accepted trajectory in
`../autonomous/trajectories_pilot_2026_07_22.parquet` (status == `accepted`):

- `../autonomous/<trajectory_id>/capture_package_v0_1.json` — the frozen,
  C0+schema-v1.0-validated capture package. This is the authoritative input.

## How B consumes it

B's own adapter turns a package into B's frozen state-input rows:

```python
from mineocclude.analysis.coordinates import build_state_input_from_capture_package
doc = build_state_input_from_capture_package(
    package,                       # json.load of capture_package_v0_1.json
    coordinate_frame=SIGNED_FRAME, # see below — B confirms + co-signs
    model_hash=A_MODEL_HASH,       # Person A supplies (SHA-256)
    preprocess_hash=A_PREPROC_HASH # Person A supplies (SHA-256)
)
```

Each output row carries authoritative timing (`server_tick`, `tau` derived at
exactly 20 Hz), state (wall-parallel scalar projection +
`last_visible_position_blocks`), `visibility` (`visible`/`occluded`), layout
identity, the coordinate-frame binding, and scoring-only `x_true_blocks`.
Verified end-to-end on real data: `layout_00_ep9403` → 248 rows
(39 visible, 209 occluded, one reveal).

## Reference C→B outputs (already generated, for cross-checking)

`state_input_layout_00_ep9403.json`, `state_input_layout_00_ep9410.json` —
produced with the DRAFT coordinate frame below so B can diff against its own
run. These are cross-check artifacts, not the signed scientific input.

## TWO things B must resolve before scientific use

1. **Coordinate frame — jointly signed.** The reference outputs used a C
   *draft* frame (`coordinate_frame_id` prefixed
   `DRAFT_C_PROPOSAL_PENDING_B_SIGNATURE_...`): origin `[0,0,0]`, positive
   unit vector `[1,0,0]` (layout_00 wall axis is X), bound to the package's
   `layout_config_hash`. B must confirm or replace the origin/direction and
   set a real `adapter_signoff` — B's contract (`person-b-wall-parallel-
   frame-v0.1`) fails closed until BOTH `person_b` and `person_c` are true.
   The `person_b:true` in the draft is a C placeholder, not B's signature.

2. **Event stability rule.** C5.5 events use
   `person-c-event-stability-v0.1` (2 consecutive frames). B/E must sign that
   number (or supply theirs) before reveal-aligned analysis (U3).

Person A separately owes the real `model_hash` / `preprocess_hash`
(placeholders were used above).

## Not included / pending

- `layout_02_ep9421` (no-wall positive control, first attempt) is
  **`superseded_pending_recollection`** — captured before the phantom-wall
  geometric-visibility fix (geometric 5/200 vs detector 200/200). It is
  replaced by `layout_02_ep9432`, collected after the fix:
  **200/200 visible, zero occluded, zero quarantine** — a correct positive
  control. Its C->B state input (`state_input_layout_02_ep9432.json`) is 200
  rows, all visible. The negative control `layout_05_ep9422` (no-sheep) is
  unaffected and accepted. ep9421 is retained (not deleted) for audit;
  `replaces_episode` in the manifest records the lineage.
