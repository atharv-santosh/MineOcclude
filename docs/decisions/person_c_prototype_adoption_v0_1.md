# Person C decision: adopt and harden the working capture prototype

Date: 2026-07-22 · Status: `ADOPTED_WITH_RECORDED_DEVIATIONS`

## What was decided

A working Fabric 1.16.5 capture prototype (single combined server+client mod
plus a Python data pipeline) existed outside this repository and had already
produced real collected episodes. Rather than reimplementing C2–C5 from
scratch, the prototype was imported, reviewed skeptically, and hardened to
the frozen Person C contracts:

- Mod source now lives at `fabric/mineocclude-mod/` (one combined project,
  not the separate `fabric/mineocclude-server` / `fabric/mineocclude-client`
  folders the execution manual sketched — splitting a proven mod was judged
  higher-risk than documenting the deviation; entrypoints are still cleanly
  separated in `com.mineocclude.server` / `com.mineocclude.client`).
- Python pipeline now lives in `src/mineocclude/data/` as `align.py`,
  `convert_mineworld.py`, `preprocess.py`, `visibility.py`, `impulse.py`,
  `qa_report.py`, `build_dataset.py`, `collect.py`, `collection_matrix.py`,
  `noise_schedule.py`, `fsretry.py`, with tests under `tests/data/`.

## Contract fixes applied during adoption

1. **RNG (C2.4).** The prototype generated noise with `java.util.Random`
   inside the server — a direct violation of the frozen RNG decision. Added
   `mineocclude.data.noise_schedule` (NumPy `Generator`/`PCG64`, canonical
   serialized bytes, SHA-256) and `NoiseSchedule.java`, which verifies the
   header, seed, consecutive `draw_idx`, and `sqrt(q*dt)` scaling, and
   consumes draws strictly in order. Schedule exhaustion fails the episode.
   The `java.util.Random` path remains only as an explicitly-labelled
   non-scientific fallback recorded as `rng_source` in the reset/finalization
   records. A committed Python-generated schedule is loaded byte-exactly by a
   Java unit test (`PythonScheduleCrossCheckTest`).
2. **Lifecycle (C2.2).** Added `EpisodeLifecycle.java` — an explicit
   IDLE→RESETTING→READY→RECORDING→FINALIZING→COMPLETED/FAILED state machine
   with illegal-transition enforcement and a per-episode `lifecycle.jsonl`.
   Duplicate episode IDs are now refused (an existing episode output
   directory is never overwritten).
3. **Reset result (C2.3).** `reset_result.json` records expected vs observed
   target count, start state, RNG source, and configuration identity before
   the first recorded tick; `finalization.json` records the terminal state,
   tick count, draws consumed, and failure reason.
4. **Protocol version (C2.6).** `TickSyncPacket`/`EpisodeEventPacket` now
   carry and validate an explicit `PROTOCOL_VERSION`.
5. **Strict join (C4.1–C4.3).** `align.py` additionally rejects duplicate
   identities and mixed episode IDs before joining, reports the first
   mismatched index with its neighborhood, and treats unreadable sources as
   rejections rather than crashes.
6. **Converter identity (C4.4/C4.5).** Token conversion and model-input
   preprocessing are pluggable; the built-in reference implementations carry
   explicit non-pinned identities (`person_c_reference_tokenizer_v0`,
   `person_c_reference_preprocess_v0`) so their outputs can never masquerade
   as Person A's pinned paths.
7. **Visibility (C5.2–C5.5).** New Python implementation of the frozen
   geometric convention (exact slab intersection with
   visible/occluded/boundary/invalid outputs), E-schema detector import with
   preserved provenance, AND-rule final flag with categorized quarantine, and
   stability-rule event derivation — all layout-parameterized and tested.
8. **Immutable QA (C4.8).** `qa_report.py` writes per-episode
   pass/fail/not-applicable results with measured vs expected values and a
   SHA-256 sidecar, and refuses to overwrite an existing report.

## Recorded deviations (open items)

- **Mod-internal layouts vs frozen `layouts.yaml`.** ~~The mod still uses its
  prototype layout table (`Layouts.java`, relative coordinates, ids
  `layout_00`–`layout_05`), which produced the existing real data.~~
  **RESOLVED for the mod in `1f1937a`**: `Layouts.java` now registers
  `layout_01`–`layout_06` matching the frozen contract, and `layouts.yaml`
  was revised to v0.3 (the v0.2 canonical-pose geometry defect referenced
  here is fixed; the cited geometry-audit report was never committed and the
  per-layout occlusion-arc assertions in
  `tests/data/test_visibility_geometry.py` are the surviving check).
  **NOT resolved for artifacts captured before `1f1937a`**: the C6 pilot
  bundles and the Person E handoff carry the legacy zero-based ids. That is
  handled by `docs/decisions/person_c_layout_id_supersession_v0_1.md`, which
  records the `layout_00→layout_01 … layout_05→layout_06` mapping, the
  evidence that it is a pure rename, and which artifacts were corrected
  versus preserved as historical provenance.
- **Integer episode IDs on the wire and in JSONL.** The canonical downstream
  string identity is `str(episode_id)` with
  `trajectory_id = "<layout_id>_ep<episode_id>"`, declared once in
  `align.py`.
- **Client captures at the native 16:9 framebuffer size**; the deterministic
  640x360 canonical source is produced by `preprocess.normalize_episode`,
  preserving the raw capture unchanged.
- The pre-existing circular import between `mineocclude.data` and
  `mineocclude.contracts` was resolved with lazy (PEP 562) exports in
  `mineocclude/contracts/__init__.py`; no exported name changed.

## Build evidence

- `fabric/mineocclude-mod`: `./gradlew build` with JDK 17, Gradle 8.3
  (wrapper), Loom 1.4-SNAPSHOT, Yarn `1.16.5+build.10`, Fabric Loader
  `0.15.11`, Fabric API `0.42.0+1.16`.
- Artifact `mineocclude-0.1.0.jar`, SHA-256
  `8b18dd79b5b0907c8da55be8cc854a36dccad8d5767f83b9d99140287f5a0c70`.
- Java unit tests: 18 passed, 0 failed.
- Python: full repository suite passes (the two pre-existing
  saved-evidence/environment failures in `tests/analysis` and
  `tests/integration` predate this change and are unrelated).
