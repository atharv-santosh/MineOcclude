# Person C — Clean-machine trajectory collection runbook (C8.3)

This is the complete operator procedure for building, starting, resetting,
collecting, finalizing, validating, transferring, retrying, and shutting down
the Person C MineOcclude capture system for one MVP trajectory. A clean reader
can execute it without private instructions. Every step states its working
directory, purpose, expected output, success evidence, and failure response.

This runbook does **not** change experiment code, geometry, schedules, or the
accepted manifest. It reproduces the exact locked runtime that produced the
certified 66-trajectory C6A/C7 MVP (`person-c-c6a-post-c1-v0.1`,
authorization commit `28cac05`, capture source commit `538a176`).

## Pinned identities (verify before every session)

- Server/client build: `mineocclude-0.1.1-538a176e1c83dc3b40e220dee8ebb2ac841bd9b4.jar`,
  SHA-256 `9ecbb5e85b249409d38428ea479c3f09ec97dd884a97ecb48d79590e4c03de52`.
- Accepted geometry: `person-c-layout-config-v0.4`,
  SHA-256 `34495d650d6a8c62b00a916796c90389b48f80d8f20a23eac93207758e993f5d`.
- Environment lock: `person-c-c1-final-environment-lock-v1.0`
  (`docs/status/person_c_c1_runtime_ingestion_v0_1/final_environment_lock_receipt.json`).
- Noise schedules: `person-c-c6a-noise-schedules-v0.1`, set SHA-256
  `79a81668362421fa91cb591d355b655e9b1a60aae088057de7bda977df663806`.
- Runtime: Minecraft 1.16.5, Fabric loader 0.15.11, Fabric API 0.42.0+1.16,
  Yarn 1.16.5+build.10, Java 17.0.19.
- Frozen 66-cell plan: `configs/collection/mvp_matrix.parquet`.
- Runtime root (Windows): `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\`.

**Credentials.** Durable-storage (S3) credentials are supplied only through the
approved out-of-band secret channel. Never place credentials in this runbook,
Git, S3 object names, logs, notebooks, or chat.

---

## 1. Build / verify pinned artifacts

- Working directory: repository root of `MineOcclude-Person-C-C1-C6A`.
- Purpose: confirm the exact server/client JAR and configs before any capture.
- Command:
  `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\lollo\MineOcclude-Person-C-C1-C6A\scripts\person_c\verify-pinned-artifacts.ps1"`
  (or re-hash the JAR and compare to the pinned SHA-256 above).
- Expected output: reported JAR SHA-256 and geometry/environment/schedule hashes.
- Success evidence: every reported hash equals the pinned identity above.
- Failure response: stop. Do not substitute a rebuilt or differently-hashed JAR.
  Rebuild only from source commit `538a176` and re-verify; if it still differs,
  escalate — a changed build invalidates the locked collection.

## 2. Start the server

- Working directory: `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\`.
- Purpose: bring up the dedicated server with the pinned mod and locked world.
- Command:
  `powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\start-mineocclude-server.ps1"`
- Expected output: server log reaching "Done", the FIFO/command channel ready,
  `spawn-animals=false` in `server.properties`.
- Success evidence: `mineocclude markergeomstatus` at the console prints the
  expected geometry status; no marker override or block mismatch.
- Failure response: on any geometry mismatch, unexpected override, or FIFO not
  ready, stop and do not begin capture. Do **not** run `markergeom` /
  `markergeomreset`.

## 3. Start the client and verify canonical visuals

- Working directory: `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client\`.
- Purpose: connect the capture client at the canonical framebuffer/pose.
- Command:
  `powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\start-mineocclude-client.ps1"`
- Expected output: a 640x360 window/framebuffer, pinned client options,
  vanilla-only resource packs, direct connection to `127.0.0.1:25565`.
- Success evidence: client joins; canonical camera pose (feet `(0.5,4.0,-5.5)`,
  yaw 0, pitch 0, FOV 70) is observed; no HUD/menu contamination.
- Failure response: if resolution, pose, options, or connection are wrong, stop
  and correct before any episode. A wrong pose/resolution invalidates capture.

## 4. Reset and readiness for the planned cell

- Working directory: server console.
- Purpose: arm the exact planned cell (layout/v/q/hidden/seed) from the frozen
  matrix without improvising conditions.
- Command: the reset/ready sequence issued by the wrapper
  `scripts\person_c\run-c6a-after-e-refit.ps1` for the target
  `collection_order` (which selects layout, scene, `v`, `q`, hidden frames,
  seed, warmup, and the per-episode noise schedule).
- Expected output: server log lines `schedule_load`, `armed`, then the target
  spawn (magenta sheep `mineocclude_experimental_target`, `NoAI`, silent) for
  target-bearing cells; no target for `no_object` cells.
- Success evidence: `reset_result.json` written; target expected/observed counts
  match the cell (1 for core/nowall/sentinel, 0 for no-object); geometry status
  unchanged.
- Failure response: on target retention loss at warmup, layout mismatch, or
  schedule-hash mismatch, abort the cell (do not record). Fix the retention
  defect without changing `spawn-animals=false`; re-verify the target-retention
  gate before retrying.

## 5. Collect (record) the episode

- Working directory: server console (FIFO), client rendering.
- Purpose: record exactly one planned episode in balanced planned order.
- Command: the capture start issued by the wrapper for the cell (executes
  `mineocclude start <layout> <episode_id> <seed> <v> <q> <max_ticks>` with the
  locked warmup and impulse `axis=-1 at_tick=0`).
- Expected output: server log `recording started` then `completed`; client log
  `recording_started` then `completed`; raw frames + `server_state.jsonl` +
  `raw_actions.jsonl` + `client_tick.jsonl` written under
  `episode_<id>`.
- Success evidence: `recording_started` and `completed` present on both sides.
- Failure response: on warmup abort, missing player camera, or a capture that
  never starts, stop; preserve the partial logs; treat as an incidental failure
  (step 8) — never edit media/state to fix counts.

## 6. Finalize the episode

- Working directory: server/client output roots.
- Purpose: write the immutable per-episode finalization and lifecycle records.
- Command: the finalization step of the wrapper (writes `finalization.json`,
  `lifecycle.jsonl`, `layout_meta.json`).
- Expected output: `finalization.json` and `lifecycle.jsonl` per episode.
- Success evidence: `finalization.json` present; server/client row counts and
  frame count agree.
- Failure response: if finalization is missing or row counts disagree, mark the
  episode incidental-failure and recollect under a new ID (step 8).

## 7. Validate the episode and its realized conditions

- Working directory: repository root (Mac or Windows checkout).
- Purpose: confirm structural identity **and** that the planned condition
  actually occurred.
- Commands (fast structural first, then full):
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/... -q` for the
    C4/C5 validators; `ffprobe` on media; cardinality/continuity/impulse checks.
  - Compare planned vs realized: hidden duration, `v`/`q` + noise-schedule
    SHA-256, commanded/observed path, shadow containment, target count, camera
    return, marker visibility.
- Expected output: per-episode QA record (structural + realized-condition
  status, cardinality, continuity/alignment, duration error, target status).
- Success evidence: `status: PASS` — structural identity **and** realized-
  condition rules both hold; frame = action = server = client counts equal.
- Failure response: assign `EXCLUDED` with one or more structured reason codes
  and measured evidence; never repair IDs from timing/jitter; recollect (step 8).

## 8. Retry / recollection under a new ID

- Working directory: server console + repository.
- Purpose: re-run a failed planned cell without destroying evidence.
- Procedure:
  - Preserve the failed bundle, QA report, hashes, and exclusion reason.
  - Incidental failure, implementation frozen: assign a **new** episode ID and
    rerun the **same** planned cell (same layout/v/q/hidden/seed-policy).
  - Code/schema/config defect: pause affected collection, open a reviewed
    versioned correction, identify all affected earlier episodes, rerun the
    required gates, then resume.
- Success evidence: the new accepted attempt has a unique source identity and
  clear lineage to the same planned cell; the failed attempt remains visible.
- Failure response: never overwrite a failed attempt, never edit media/action/
  state to match counts, never delete prior attempts.

## 9. Transfer (durable storage)

- Working directory: repository + approved storage tooling.
- Purpose: move accepted episode bytes to durable storage and prove integrity.
- Procedure:
  - Obtain the S3 prefix/credentials only from the approved secret channel.
  - Upload the accepted episode bundle; then download a sample, re-hash, and
    re-run validation before appending the accepted result.
  - Record the durable URI + SHA-256 in the C7.5 handoff bundle
    (`docs/status/person_c_c7_mvp_handoff_v0_1/per_trajectory/ep<id>.json`,
    `locations.durable_uri`); until assigned, keep the runtime path with
    `durable_uri: null` and the explicit external-storage status.
- Success evidence: re-downloaded bytes re-hash to the committed `sha256`;
  validation re-passes; manifest/ledger counts unchanged.
- Failure response: on any hash mismatch, do not append; re-upload and re-verify.
  Never fabricate an S3 URI or commit episode payload bytes into Git.

## 10. Shut down cleanly

- Working directory: server and client consoles.
- Purpose: end the session without corrupting the world or leaving compute up.
- Procedure: stop the client, then `stop` the server from its console; confirm
  clean shutdown in both logs; archive `latest.log` (gzip) with its SHA-256.
- Success evidence: server and client logs show clean shutdown; no episode is
  mid-record; compute is released.
- Failure response: if either side did not shut down cleanly, record it, do not
  reuse the world save until verified, and note it for the next operator.

---

## Manifest-append validation (every accepted episode)

Before appending an accepted episode to the locked handoff:
cardinality, continuity, media, impulse, motion/noise, pose, marker, visibility
disagreement, hash, and upload/download re-hash checks all pass; the episode ID
is unique; and the accepted/excluded ledger still reconciles. Distinguish
operator error, incidental episode failure, and implementation defect in the
recorded reason. Regenerate the C7.5 handoff with
`python scripts/build_person_c_c7_5_mvp_handoff_v0_1.py build` and re-run its
focused validation.
