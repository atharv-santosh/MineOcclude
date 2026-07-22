# Person E Phase 1 provenance and visual QA checklist

Use this checklist for every checkpoint package. Items requiring live A/B/C/D
artifacts remain blocked rather than being marked complete with placeholders.

## Provenance QA

- [ ] Registry and accepted rollout manifest pass the frozen validator.
- [ ] Literal manifest, registry, config, code, model/data and input hashes are
      recorded from the bytes actually processed.
- [ ] Producer run, owner, command, parent, status, inputs and outputs resolve.
- [ ] Artifact index reports accepted/excluded/superseded counts and no
      transitive invalid source enters a scientific claim.
- [ ] Correction uses a new run/artifact and a recorded supersession reason.
- [ ] Every E measurement row resolves to exactly one persisted evidence file
      whose literal SHA-256 equals `measurement_artifact_hash`.
- [ ] Figure sources are accepted/current and resolve through result,
      prediction/measurement, upstream data/model, config, code and seed.

## Measurement QA

- [ ] Detector thresholds came only from the calibration split.
- [ ] Held-out detector precision and recall are each at least 0.95.
- [ ] Homography median signed-wall absolute error is at most 0.20 blocks and
      p95 is below 0.50 blocks, overall and inspected by image region.
- [ ] Coordinate origin/unit/positive direction and layout/camera pose match.
- [ ] Post-reveal frame coverage begins immediately; no frame is interpolated.
- [ ] Alpha-zero match is exact on event and seed; baseline persistence is
      reported before persistence conditioning.
- [ ] Non-persistence, generation failure, exclusion and numeric zero remain
      distinct.
- [ ] SSIM has exact rollout/frame alignment, explicit RGB/data range/method,
      fixed union-box background mask, and independent alpha-zero context.

## Figure and table QA

- [ ] Figure input is generated from machine-readable source rows, not retyped.
- [ ] Axes, units, n, uncertainty/CI method and sample definition are visible.
- [ ] Planning gates and proposal success criteria are labeled distinctly.
- [ ] Caption, script/config/code/run IDs and source/output checksums are in the
      figure manifest.
- [ ] SVG/PDF is visually inspected for clipping, overlap, unreadable text,
      misleading scales, missing categories and color/accessibility issues.
- [ ] Superseded or invalid sources are listed in the checkpoint audit.

## Checkpoint release QA

- [ ] Clean-environment command list reproduces all accepted outputs.
- [ ] No output path was overwritten; reruns use new identities.
- [ ] Artifact index, QA reports, figures/tables and section ownership are
      included.
- [ ] Official paper template version/checksum and venue constraints are
      verified once the venue is selected.
