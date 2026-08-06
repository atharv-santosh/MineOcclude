# Person E Homography Runbook (frozen)

Owner of record: Person E. Accepted package:
`data/handoff_e/person_e_v0_4_homography_refit_v0_2/`
Algorithm version: `four_point_projective_gauss_jordan_v0.1`
Accepted geometry: `person-c-layout-config-v0.4`
(sha256 `34495d650d6a8c62b00a916796c90389b48f80d8f20a23eac93207758e993f5d`)

## What this workflow does

Fits one 3x3 image-to-world mapping per layout and canonical camera pose from
exactly four registered marker correspondences, then validates it on visible
sheep positions that were not used to fit it.

A pixel shift is not a displacement. This mapping is what converts a detected
screen position into Minecraft blocks, so it is versioned per layout, per pose,
and per resolution, and is never reused across any of those without a
validated, versioned transformation.

## Required inputs

| Input | Owner | Notes |
| --- | --- | --- |
| Four marker image/world correspondences per layout | Person C | order and identity verified before fitting |
| Canonical camera pose and image resolution | Person C | `1920 x 1046`, FOV 70 degrees in the accepted package |
| Wall-axis origin and positive unit vector | Person C | sign convention is C's to declare |
| Held-out visible sheep world positions | Person C | must not be fit inputs |

## Commands

```
python scripts/fit_homographies.py <homography_input.json> <report-out.json> \
    --config configs/vision/person_e_phase1.yaml \
    --producer-run-id <run-id> --code-sha <40-hex>
```

The report this writes carries `homography_report_schema_version`
`person-e-homography-report-v0.3`, which is the version
`scripts/localize_u4_frames.py` consumes.

## Validators

```
python -m pytest tests/vision/test_homography_and_ssim.py
python -m pytest tests/vision/test_markers.py
python -m pytest tests/vision/test_phase2_step2_4_v0_4.py
python -m pytest tests/vision/test_attempt_02_refit_finalize_v0_2.py
```

## Outputs

- Per-layout matrix with condition number, determinant, and rank.
- Fit reprojection error, inverse round-trip error, and independent validation
  error in pixels.
- Held-out wall-parallel localization error in blocks, with the image-region
  breakdown.
- Coordinate convention record and applicability domain.

## Failure behaviour

Fail closed. Degenerate geometry, a marker-order swap, a resolution or pose
mismatch, a non-unit wall-parallel direction, or an out-of-region query is
rejected rather than extrapolated. A layout that fails its tolerance is
recorded as failed and kept; it is not quietly refitted into the accepted set.

## Version and supersession rules

Each matrix carries a `homography_version_id` derived from its own content. A
correction produces a new versioned successor package; the superseded package
and its failed-closed artifacts are preserved. The accepted six-layout refit
v0.2 supersedes v0.1 for layouts 04 and 06 only, and reuses the verified v0.1
bytes for layouts 01, 02, 03, and 05 — that reuse is recorded per layout in
`fit_summary.json` as `result_origin`.

## Permitted operational reruns

- Re-running the fit over identical correspondences to reproduce the package.
- Re-running validation over the recorded held-out set.

## Changes requiring Person A / Person B review

- Any change of camera pose, resolution, or wall-axis sign convention.
- Any change to the localization tolerance.
- Applying an existing matrix to a layout, pose, or resolution it was not
  validated for.

## Escalation

Marker geometry, pose, and axis sign: Person C. Rollout-versus-capture
coordinate contract: Person A. Tolerance interpretation: Person B.

## Current frozen evidence

Six layouts pass. Held-out wall-parallel errors are 0.085, 0.074, 0.167, 0.015,
0.165, and 0.037 blocks for layouts 01 through 06, all within the 0.20-block
median planning tolerance. Maximum inverse round-trip error is 4.7e-13 pixels.
