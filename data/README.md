# Person C collected data (Week-1 pilots, 2026-07-22 session)

- `autonomous/` — 12 accepted trajectory bundles. Identity anchor:
  `autonomous/trajectories_pilot_2026_07_22.parquet` (+ .sha256). Each bundle:
  frozen-validated `capture_package_v0_1.json` (+ stream JSONLs in
  `package_v0_1/`), model-facing `video_640x360.mp4` (ffprobe-gated 20 fps),
  `frame_map.parquet`, `mineworld_actions.jsonl`, immutable QA report — all
  with SHA-256 sidecars/columns.
- `schedules/` — the immutable NumPy PCG64 noise schedules consumed by the
  server (byte-exact replay verified).
- `server_evidence/` — per-episode authoritative server records
  (state log, reset result, lifecycle, finalization, layout meta incl.
  marker world coordinates).

NOT in git (size): the preserved raw and canonical PNG frame directories
(`~/mineocclude-client/mineocclude_client_out/episode_<N>/frames*/`,
~1 GB total). Their SHA-256 hashes ARE committed via each
`frame_map.parquet` (`frame_640_sha256`), so integrity is verifiable; the
files transfer via storage on request. The committed MP4s are the
model-facing media.
