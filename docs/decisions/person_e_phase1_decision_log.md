# Person E Phase 1 decision log

Status: implementation foundation complete only after tests pass; live calibration
and measurement remain pending upstream artifacts.

## Sources of authority

- Shared schema and lifecycle: frozen schema v1.0 contracts and signed record.
- A-to-E rollout and A/E registry: `docs/contracts/rollout_registry_v1.md`.
- E-to-B compact measurement intake:
  `src/mineocclude/contracts/analysis_inputs.py`.
- E technical duties: mentor-aligned roadmap, Person E role reference.

No E module may rename shared fields, weaken validators, infer identity from a
filename, or silently repair invalid input.

## Decisions implemented before live artifacts

1. Image coordinates are zero-based pixel-center `(x, y)` coordinates.
2. Homographies map image `(x, y)` to ground-plane `(world_x, world_z)` in
   blocks. The signed wall axis must come from the B/C-approved coordinate
   frame; E never guesses it from marker order or image orientation.
3. Reappearance is the first post-reveal detection valid for two consecutive
   frame indices. The sensitivity is the median coordinate of the first three
   valid post-reveal detections.
4. Displacement is pushed wall coordinate minus matched alpha-zero wall
   coordinate. Matching uses exact `event_id + seed`.
5. A measured primary reappearance has persistence score `1.0`. Non-persistence,
   generation failure, and exclusion have null persistence/displacement/SSIM.
6. The implemented dependency-free coherence candidate is explicitly named
   `global_ssim_per_channel_mean_v0.1`. It evaluates exactly three RGB channels
   separately, uses sample covariance and a declared data range, and never
   clips. It is not described as conventional windowed SSIM.
7. Registry and measurement outputs are append-only. Writers refuse to
   overwrite an existing path.
8. Tests construct small known-answer values in memory. No new persisted
   synthetic experiment bundle or parallel synthetic pipeline is created.
9. A pending foundation config is valid for contract and known-answer tests but
   is rejected by every scientific U4 result workflow. A live config needs a
   new instance version, frozen calibration hashes and detector version, plus a
   signed SSIM mask/version.
10. Detector thresholds are evaluated under an explicit calibration or
    held-out split. Only held-out reports may carry a planning-gate result.
11. Missing frames, evidence, alpha-zero controls, negative consumer-incompatible
    SSIM, generation failures, and non-persistence remain distinct outcomes.

## Deliberately pending decisions

The following cannot be frozen honestly without calibration evidence or owner
signoff:

- HSV ranges, morphology, and valid blob-area limits: require C's calibration
  and held-out visible/negative frames.
- Background-mask margin: requires B/E signoff before real SSIM measurement.
- Per-layout homography matrices and detector/homography version IDs: require
  C's marker and held-out localization records.
- Final global-versus-windowed SSIM method selection: requires B/E method
  signoff. Any change receives a new algorithm/config/run identity; the current
  global method cannot be silently relabeled as scikit-image/windowed SSIM.

The Phase 1 config records these values as pending. A later result-bearing
config must use a new config version/hash and new run identity.

## Corrections

A result-affecting correction creates a new run/artifact. Prior records remain
accepted, excluded, or superseded according to the frozen lifecycle; they are
not overwritten or edited in place.
