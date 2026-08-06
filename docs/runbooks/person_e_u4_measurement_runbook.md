# Person E U4 Measurement Runbook (frozen)

Owner of record: Person E. Covers manual Steps 6.1 through 6.5.

Person E owns the measurement instrument and the outcome table. Person B owns
every inferential statistic and all claim language. This runbook must not be
used to compute or label confirmatory significance.

## What this workflow does

Turns Person A's immutable U4 rollout clips into one versioned, measurement-
facing table: persistence, primary and sensitivity reappearance timing, world
coordinates, signed wall-parallel displacement, global and background-masked
SSIM, natural unpushed variation, and an explicit quality or missing reason for
every planned clip.

## Required inputs

| Input | Owner | Notes |
| --- | --- | --- |
| Rollout generation manifest, clips, hashes, frame contract | Person A | identity by ID, never by filename or row order |
| Frozen event/dose table, direction version, intended block shifts | Person B | includes the primary and sensitivity event rules |
| Approved SSIM matching and seed-pairing rule, mask margin | Person B | background mask excludes the union of sheep boxes plus this margin |
| Held-out layout, wall-axis sign, marker/pose applicability | Person C | must match the homography package |
| alpha=0 / random / orthogonal / wrong-layer / wrong-timestep control IDs | Person D | with a completeness report |

## Commands

Run in this order. Each stage consumes the previous stage's output.

```
python scripts/fit_homographies.py <homography_input.json> <homography_report.json> \
    --config configs/vision/person_e_phase1.yaml \
    --producer-run-id <run-id> --code-sha <40-hex>

python scripts/localize_u4_frames.py <frames.json> <homography_report.json> \
    <rollout_manifest.json> <registry.json> <localization.json> \
    --config configs/vision/person_e_phase1.yaml --run-id <run-id>

python scripts/measure_ssim.py --help

python scripts/compose_u4_evidence.py <localization.json> <ssim_report.json> \
    <composed.json>

python scripts/measure_u4.py <rollout_manifest.json> <registry.json> \
    <composed.json> <measurements.json> \
    --evidence-output-dir <evidence-dir> \
    --config configs/vision/person_e_phase1.yaml --run-id <run-id>
```

## Validators

```
python -m pytest tests/vision/test_u4_pipeline.py
python -m pytest tests/vision/test_measurement.py
python -m pytest tests/vision/test_homography_and_ssim.py
python -m pytest tests/vision/test_person_e_scripts.py
```

## Outputs

- One versioned U4 measurement table with clip / event / seed / dose / control /
  site identity, detector / homography / SSIM version identities, and source run
  and artifact IDs.
- Persistence and non-persistence status, distinct from generation failure.
- Primary event (first valid detection that stays valid for two consecutive
  frames) and sensitivity event (median of the first three valid frames).
- Signed wall-parallel displacement against the exact alpha=0 pair matched by
  event and rollout seed.
- Global SSIM, background-masked SSIM, and unpushed-versus-unpushed natural
  variation, each naming its exact frame pair, data range, channel handling,
  library version, and parameters.
- Planned-versus-measured counts and status summaries by alpha, control, event,
  and layout.

## Failure behaviour

Fail closed, and keep the distinction between kinds of absence:

- A missing sheep is never imputed as zero displacement.
- Non-persistence is recorded separately from generation failure and from a
  missing clip.
- If either member of a pushed / alpha=0 pair lacks a valid coordinate, no
  displacement is computed and the missing reason is preserved.
- A pushed clip with no alpha=0 match at the same held-out event and rollout
  seed is reported as a missing pair; another seed is never substituted.
- Misaligned or unresolvable SSIM frame pairs are rejected, never interpolated.
- Duplicate identities, checksum failures, and pose / resolution mismatches are
  quarantined and reported to the owning role.

## Version and supersession rules

The measurement table is frozen at the version Person B's analysis consumes.
A detector, homography, or SSIM version change invalidates every dependent row
and requires a new versioned measurement run; rows are never edited in place.

## Permitted operational reruns

- Re-running the full ordered pipeline over identical inputs.
- Re-running intake validation to regenerate the completeness report.

## Changes requiring Person A / Person B review

- Any change to the primary or sensitivity event rule.
- Any change to the SSIM parameters, mask margin, or seed-pairing rule.
- Any conditioning or exclusion of clips before Person B's analysis.

## Escalation

Missing or failed clips and generation shortfall: Person A. Event rules, dose
table, and conditioning: Person B. Geometry and wall-axis sign: Person C.
Control completeness: Person D.

## Current status

The full local pipeline, schemas, validators, and commands are implemented and
pass end to end over repository fixtures. No real measurement has been executed:
Person A's U4 rollout clips, Person B's frozen event/dose table and approved
SSIM matching rule, and Person D's control manifest are not yet available. Until
they are, this workflow produces no measurement rows.
