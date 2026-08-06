# Person E Detector Runbook (frozen)

Owner of record: Person E. Frozen detector version:
`hsv-largest-valid-blob-v1.0-candidate:sha256:0cadf618fca1578196bde4982021c38627ccb9c39e46353812e7da3fce6aa125`

## What this workflow does

Runs the frozen HSV magenta detector over frames, selecting the largest valid
blob after minimal morphological cleanup, and records presence, centroid, area,
bounding box, quality values, threshold version, and an explicit rejection
reason for every frame that does not yield a valid detection.

The detector reports what is visible on screen. It never produces the final
`visible_flag` — that label is Person C's, computed as
`geometric_visible AND empirical_magenta_visible`.

## Required inputs

| Input | Owner | Notes |
| --- | --- | --- |
| Frame package with stable frame identities and source hashes | Person C | never anonymous copies of frames |
| Frozen split manifest (calibration vs held-out) | Person E | `docs/status/person_e_phase2_v0_1/frozen_split_manifest.json` |
| Detector config and version record | Person E | `docs/status/person_e_phase3_step3_1_candidate_freeze_v0_1/` |

No U4 pushed output may enter threshold selection. The split predates the
freeze and no frame identity may appear in both halves.

## Commands

```
python scripts/evaluate_magenta_detector.py --help
python scripts/build_person_e_phase3_detector_candidate.py --help
python scripts/run_person_e_phase3_formal_detector_evaluation.py --help
```

## Validators

```
python -m pytest tests/vision/test_config_and_magenta.py
python -m pytest tests/vision/test_calibration.py
python -m pytest tests/vision/test_phase3_detector_candidate.py
python -m pytest tests/vision/test_phase3_formal_detector_evaluation.py
```

## Outputs

- Per-frame detection records with full scientific identity and detector version.
- Calibration-only diagnostic report (calibration frames only).
- Held-out formal evaluation report with precision, recall, and per-layout
  false-positive / false-negative counts.

## Failure behaviour

Fail closed. Zero blobs, multiple ambiguous blobs, an edge blob, a malformed
image, or a corrupted input produces no detection and an explicit rejection
reason; it never produces a guessed centroid. A frame missing its identity is
rejected before decoding.

## Version and supersession rules

Parameters are frozen before the held-out set is opened. Any parameter change
creates a new detector version and a new calibration decision record; the
previous held-out set may not then be described as untouched. Every output
carries the detector version that produced it, and changing the version
requires re-running every affected downstream output.

## Permitted operational reruns

- Re-running the frozen detector over the same frames with the same version.
- Re-running the recorded formal evaluation to reproduce the committed report.

## Changes requiring Person A / Person B review

- Any HSV, morphology, or valid-blob rule change.
- Any change to the precision / recall gate or to what counts as a detection.
- Opening a held-out set a second time.

## Escalation

Frame identity or label disputes: Person C. Gate interpretation and U4 go/no-go:
Person B. Rollout image-coordinate contract: Person A.

## Current frozen evidence

The formal held-out evaluation at
`docs/status/person_e_phase3_step3_1_formal_evaluation_v0_1/formal_evaluation_report.json`
records precision 1.0 and recall 1.0 over 48 real held-out frames (24 positive,
24 negative) across six layouts, with zero false positives and zero false
negatives. That is a planning gate over the declared held-out set, not a
scientific claim about detector accuracy at publication scale.
