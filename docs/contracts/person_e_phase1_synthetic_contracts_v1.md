# Person E Phase 1.3 synthetic vision and lineage contracts

Status: repository-side technical contract integrated at
`integration/mvp@0d5f979e14e5c5f41f59233f1222db822d30cdd6`. All evidence described here is synthetic and carries
`scientific_use=forbidden`. It is not detector calibration, a real homography,
U4 measurement evidence, or a final figure.

## Detector calibration separation

`validate_detector_calibration_plan` freezes
`person-e-detector-calibration-plan-v1.0`. Calibration and held-out samples
carry explicit event, `trajectory_id + model_frame_idx`, source frame, layout,
canonical camera pose, resolution, and coordinate-system identity. An event,
model frame, source frame, or frame ID cannot occur in both roles. Only
calibration rows may be threshold-selection eligible.

The exact threshold-selection inputs are declared in the plan. C is requested
to supply visible magenta-sheep frames, negative wall frames, negative marker
frames, layout identity, canonical camera-pose identity, and resolution
identity. Held-out evidence never selects thresholds.

## Detection evidence

`validate_detection_document` freezes
`person-e-detection-records-v1.0`. Each record resolves exactly once to an
explicit source context and preserves source artifact, rollout/event,
trajectory/model frame, rollout frame, layout, pose, and resolution identity.
Detected rows carry centroid, area, bounding box, detector/threshold version,
quality, and null rejection reason. Missing frames remain explicit rejected
records with null geometry. E detection is empirical evidence and does not
replace C's final `visible_flag`.

## Homography evidence

`validate_homography_fixture` preserves
`person-e-homography-fixture-v1.0` and adds the compatible
`person-e-homography-fixture-v1.1` interpretation around the existing
four-point numerical implementation. Version 1.0 retains its canonical-marker
behavior. Version 1.1 separates C's stable physical `marker_id` from the
canonical `marker_role` (`north_west`, `north_east`, `south_east`,
`south_west`). It requires four unique IDs and the complete unique role set,
joins image observations to C world geometry by stable ID, and sorts only by
explicit role for deterministic computation. It never treats list order or an
image-screen quadrant as correspondence under a rotated camera. A known
synthetic probe must be recovered; missing, duplicate, ambiguous, degenerate,
or role-inconsistent geometry fails. Reuse under another layout, camera pose,
resolution, or coordinate system is rejected explicitly.

## Rollout and measurement scenarios

`validate_phase1_rollout_measurement_fixture` validates the embedded rollout
manifest/registry with A's schema-v1.0 validator and derives declared control
IDs through D's control-matrix implementation. The fixture covers alpha zero,
positive and negative signed doses, a random-direction control,
non-persistence, a missing frame, and a misaligned frame. Non-persistence has
null displacement; missing and misaligned frames are rejected rather than
interpolated or converted to zero.

## Figure sources and lineage

`validate_figure_input_against_registry` authenticates every figure-input
source artifact, creator run, checksum, and lifecycle against the one shared
immutable registry. Superseded, missing, or identity-mismatched sources cannot
become valid plot rows.

`trace_phase1_figure_lineage` performs one deterministic query from the saved
synthetic figure-input artifact through metric, prediction, activation, model
input, and raw trajectory artifacts. Direct-input edges use artifact IDs only.
The trace exposes source data identity, checkpoint hashes, config hashes, code
SHAs, seeds, preprocessing and environment hashes, and all intermediate IDs.
The result and hash are invariant to run/artifact record ordering.

## Saved fixture inventory

The deterministic builder is
`tests/fixtures/person_e/build_phase1_fixtures.py`. Its saved evidence includes:

- calibration plan plus overlapping-event rejection;
- detection records plus identity-mismatch rejection;
- known homography plus degenerate-geometry rejection;
- A-compatible rollout/registry and E measurement scenarios;
- current and superseded figure-source scenarios;
- missing-direct-input and figure-identity rejection fixtures; and
- the complete immutable registry and saved Phase 1 lineage trace.

## Later dependencies

Real calibration requires C capture/geometry evidence. Real U4 measurements
require A rollouts, B method approval, D controls, and a calibrated E config.
A orchestration adoption of the shared immutable registry remains an
integration dependency and is not claimed here. Formal human cross-role
approval remains unverified.
