# Real capture excerpt (Person D ingest-adapter tests only)

Source: `origin/role/person-c-data` commit `260784e`, episode `layout_00_ep9403`
(`data/autonomous/layout_00_ep9403/package_v0_1/{server_state,visibility,
frame_map}.jsonl`).

Frames `15-34` (spans the real visible->occluded transition at frame 19) and
`224-233` (spans the real reveal at frame 228) were excerpted from the full
248-frame episode -- not the whole trajectory -- purely to keep this fixture
small while still exercising real transition behavior.

Provenance for this episode: `layout_id=layout_00`, `trajectory_id=
layout_00_ep9403`, `seed=94723083`, `v=1.0`, `q=0.02`, `duration=12.4s`,
`regime=regime_a`, `dt_seconds=0.05`.

**This is real captured data, not synthetic** -- but it is a partial excerpt
with no real fold assignment or oracle target attached, and must not be used
to support any scientific claim. It exists only to prove
`mineocclude.baselines.capture_ingest` parses Person C's real JSONL package
format correctly, including a real visible->hidden->visible cycle.
