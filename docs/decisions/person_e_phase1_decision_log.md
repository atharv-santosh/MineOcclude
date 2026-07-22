# Person E Phase 1 decision log

Status: the repository-side Person E Phase 0/1 technical foundation and
cross-role interface compatibility are approved at
`integration/mvp@80d41c5ca0e341263a7b0c683fae4b51be376c55`. Central human signoff
evidence is `docs/contracts/schema_v1_0_signed_record.md`. A runner integration,
live calibration, real measurement, final results, and later-phase method
approvals remain pending.

## Sources of authority

- Shared schema and lifecycle: frozen schema v1.0 contracts and signed record.
- A-to-E rollout and A/E registry: `docs/contracts/rollout_registry_v1.md`.
- E-to-B compact measurement intake:
  `src/mineocclude/contracts/analysis_inputs.py`.
- Shared immutable run/artifact lineage:
  `validate_immutable_run_artifact_registry` in
  `src/mineocclude/contracts/rollout_registry.py`.
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
8. Phase 1 tests use deterministic known-answer values and the saved
   `tests/fixtures/person_e/` bundle. This is contract evidence only, not a
   parallel scientific pipeline or real result.
9. A pending foundation config is valid for contract and known-answer tests but
   is rejected by every scientific U4 result workflow. A live config needs a
   new instance version, frozen calibration hashes and detector version, plus a
   signed SSIM mask/version.
10. Detector thresholds are evaluated under an explicit calibration or
    held-out split. Only held-out reports may carry a planning-gate result.
11. Missing frames, evidence, alpha-zero controls, negative consumer-incompatible
    SSIM, generation failures, and non-persistence remain distinct outcomes.
12. The shared Phase 1.2 registry is a compatible, explicitly versioned
    sub-schema. It requires immutable run identity and provenance, explicit
    artifact direct inputs and status authority, literal checksum/size evidence
    when supplied, and append-only transition comparison. Frozen A rollout
    schema `1.0` remains valid under its existing validator.
13. Runs may transition only from `in_progress` to `completed` or `failed`.
    Terminal runs cannot change in place. Corrections use a new `run_id`,
    `supersedes_run_id`, and reason. Artifact content/provenance is immutable;
    an accepted artifact may change only to an explicit superseded lifecycle
    pointing to a same-type replacement.
14. `src/mineocclude/experiments/registry.py` delegates immutable-registry
    validation to the shared contract. It is not a second schema authority.
    A's orchestration integration remains pending and is not claimed here.
15. Calibration events and frame identities are disjoint between calibration
    and held-out roles. Only calibration rows may influence threshold choice.
16. Homography reuse is bound to explicit layout, canonical camera pose,
    resolution, and coordinate-system identity. No cross-resolution or
    cross-pose transfer is assumed.
17. Figure inputs authenticate source run, artifact, hash, and lifecycle
    against the shared registry. Superseded sources are ineligible.
18. The Phase 1 trace starts from an explicit figure-input artifact and follows
    direct artifact IDs through metric, prediction/baseline,
    activation/oracle, model input, and source data. Run provenance supplies
    checkpoint, config, code, environment, preprocessing, and seed identity.

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

## Unresolved interface and ownership decisions

These questions are not silently resolved by E. The safe behavior remains in
force until the named approver accepts a versioned contract or decision.

| ID and question | Current safe behavior | Owner | Approver | Dependency or deadline |
|---|---|---|---|---|
| `PE-OWN-001`: Who writes `rollouts.parquet` or its final measurement-facing equivalent? | A is the sole writer of generation rows and clip IDs. E writes a separate measurement/evidence projection keyed by `rollout_id` and never edits A rows. | A | A and E | Freeze before the first real A-to-E rollout handoff. |
| `PE-OWN-002`: How does A orchestration use E-owned shared-registry lineage behavior? | The shared validator in `contracts/rollout_registry.py` is authoritative and E's wrapper delegates to it. A must submit snapshots/transitions to this contract; no A runner integration is yet evidenced. | E for data model; A for orchestration | A and E | Resolve before the first orchestration-produced immutable registry snapshot. |
| `PE-OWN-003`: Can E artifact status override an upstream accepted manifest? | No. E records and audits the declared status authority. Scientific acceptance remains with the upstream producer/contract owner; corrections append new records and preserve prior lineage. | E for lifecycle behavior; source owner for acceptance | A/B/C/D/E as affected | Resolve before accepting new E artifact types in registry vNext. |
| `PE-OWN-004`: Can empirical magenta detection define final visibility? | No. E emits detection presence and quality evidence only. C remains writer and authority for final logical `visible_flag`. | C | C and E, with B as consumer | Resolve before any real visibility-bearing measurement or analysis. |
| `PE-OWN-005`: Does E measurement own U4 statistical conclusions? | No. E produces displacement, persistence outcomes, SSIM, and quality evidence. B owns metric definitions, inferential statistics, and claim language. | E for measurement; B for statistics | B and E | Resolve method details before real U4 analysis or claim-bearing figures. |
| `PE-OWN-006`: What is the final U4 image-coordinate/resolution contract? | C supplies explicit width, height, camera pose, markers, and source identity. E uses zero-based pixel-center `(x,y)` and rejects missing/mismatched resolution or geometry; it never infers either from a filename. | C for capture/camera; E for detector/homography | A, C, and E; B approves the signed analysis axis | Freeze before real homography calibration. |

## Corrections

A result-affecting correction creates a new run/artifact. Prior records remain
accepted, excluded, or superseded according to the frozen lifecycle; they are
not overwritten or edited in place.
