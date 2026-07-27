# Real no-sheep capture excerpt (Person D ingest/missingness tests only)

Source: `origin/role/person-c-data` commit `260784e`, episode
`layout_05_ep9422` (`data/autonomous/layout_05_ep9422/package_v0_1/
{server_state,visibility,frame_map}.jsonl`).

Frames `0-19` were excerpted from the full 200-frame episode purely to keep
this fixture small.

Provenance for this episode (`capture_package_v0_1.json`):
`layout_id=layout_05`, `trajectory_id=layout_05_ep9422`,
`condition=occluder_only_no_sheep`, `seed=94873544`, `v=1.0`, `q=0.05`,
`duration=10.0s`, `regime=regime_a`, `dt_seconds=0.05`.

**This is real captured data, not synthetic.** Every one of the 200 real
frames in the full episode has `visibility=occluded` and
`state.target_present=false` -- this is Person C's real occluder-only/
no-sheep negative-control condition, not a partial or corrupted capture.
There is no visible-target frame anywhere in this episode, by design.

This fixture exists to prove two things about
`mineocclude.baselines.capture_ingest.build_contexts_from_capture` and the
baselines that consume its output:

1. When a real episode never has a visible target, every resulting
   `TrajectoryContext.last_seen_position_blocks` is `None` for the entire
   episode (never a fabricated position) -- this is the documented, correct
   behavior of the adapter, not a parsing defect.
2. `predict_last_seen` / `predict_constant_velocity` therefore mark every
   row non-applicable, but every one of those rows carries an explicit
   `fit_metadata["reason"]` -- confirmed via
   `mineocclude.baselines.missingness.build_missingness_exclusion_report`
   reporting `has_silent_missingness is False` -- so a wholly-non-applicable
   real episode is legible, not a silent data-loss bug.
