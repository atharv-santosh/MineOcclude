# Person E Phase 1 runbook

## Readiness boundary

The foundation config is intentionally pending. It supports validation and
known-answer tests only. Scientific localization, SSIM, U4 measurement, and
accepted figures require a new `calibrated_live_ready` config whose literal
bytes include the frozen detector/calibration identities and B/E-signed SSIM
version and mask margin. Never tune on U4 outcomes.

## Fast verification

```text
PYTHONPATH=src python -m pytest tests/vision tests/experiments -q
python -m compileall -q src scripts tests
```

Tests use small in-memory or temporary known-answer records; they do not create
a persisted synthetic research pipeline.

## Provenance and QA

```text
python scripts/trace_artifact.py MANIFEST REGISTRY SUBJECT_ID --subject-type rollout
python scripts/build_artifact_index.py MANIFEST REGISTRY ARTIFACT_INDEX.json
```

Both commands load and hash each input once, validate the complete frozen A/E
bundle, and refuse replacement. The artifact index includes accepted,
excluded, superseded, run-status and transitive claim-readiness QA. Registry
v1 cannot yet register E result/figure artifact types; see the schema-gap
proposal.

## Detector calibration and held-out gate

The calibration dataset contract requires, for every layout/canonical pose,
visible and negative frames in both `calibration` and `heldout` splits, unique
source identities and decoded-RGB hashes, and exactly four marker records.

```text
python scripts/evaluate_magenta_detector.py CALIBRATION_DATA.json REPORT.json \
  --split calibration --hsv-range H0 H1 S0 S1 V0 V1 --min-area N \
  --threshold-version VERSION --producer-run-id RUN --code-sha SHA --config CONFIG

python scripts/evaluate_magenta_detector.py CALIBRATION_DATA.json HELDOUT.json \
  --split heldout --calibration-report REPORT.json \
  --threshold-version VERSION --producer-run-id RUN --code-sha SHA --config CONFIG
```

Only held-out reports can claim the precision/recall planning gate. Both must
be at least 0.95 overall and by inspected layout.

## Homography qualification

```text
python scripts/fit_homographies.py HOMOGRAPHY_INPUT.json HOMOGRAPHY_REPORT.json \
  --config CONFIG --producer-run-id RUN --code-sha SHA
```

Each fit binds layout, canonical pose, four markers, coordinate conventions,
algorithm/tolerances, and validation-source hashes. The held-out gate is median
absolute signed wall error at most 0.20 blocks and p95 strictly below 0.50.

## Runtime U4 localization and SSIM

```text
python scripts/localize_u4_frames.py FRAMES.json HOMOGRAPHY_REPORT.json \
  MANIFEST REGISTRY LOCALIZATION.json --config LIVE_CONFIG --run-id E_RUN

python scripts/measure_ssim.py SSIM_INPUT.json MANIFEST REGISTRY SSIM_REPORT.json \
  --config LIVE_CONFIG --run-id E_RUN

python scripts/compose_u4_evidence.py LOCALIZATION.json SSIM_REPORT.json EVIDENCE.json
```

Localization runs the config-frozen detector, transforms centroids with only a
qualified layout/pose homography, and retains source/detector/result hashes.
SSIM requires exact pushed/alpha-zero event, seed, layout and frame identity,
retains both rollout/clip identities, and measures independent alpha-zero
natural variation with distinct rollout IDs and seeds. No interpolation is
permitted.

## Exact-coverage measurement

```text
python scripts/measure_u4.py MANIFEST REGISTRY EVIDENCE.json MEASUREMENTS.json \
  --evidence-output-dir NEW_EVIDENCE_DIRECTORY \
  --config LIVE_CONFIG --run-id REGISTERED_E_RUN
```

The command validates the registry, config and evidence joins; uses config
reappearance settings; event/seed-matches alpha-zero controls; creates one
immutable rich-evidence file per rollout; hashes its exact bytes into the B
row; and emits one measured or explicit missing/failure/non-persistence row per
manifest rollout. The producer run must exist in the registry with owner
`person_e` and the same config/code identity.

## Figure inputs and rendering

```text
python scripts/build_figure_input.py RESULT_ROWS.json FIGURE_INPUT.json \
  --figure-id ID --figure-family FAMILY --code-sha SHA --config CONFIG

python scripts/render_figure_svg.py FIGURE_INPUT.json FIGURE.svg FIGURE_MANIFEST.json \
  --caption-file CAPTION.txt --config CONFIG
```

Rows require units, positive sample count for valid values, frozen uncertainty
type, accepted/non-superseded source lifecycle, source result/artifact/run IDs,
literal source hash, accepted-manifest hash, and fold hash where applicable.
The SVG exposes units, n, uncertainty and source run IDs. Its companion
manifest seals the literal input, SVG, caption, config/code and source hashes.
Scientific figure registration remains blocked until the proposed E
artifact-type migration.

## Artifact arrival order

1. C supplies split calibration frames, marker/validation coordinates, and the
   signed coordinate-frame approval.
2. B/E approve the SSIM method and fixed mask margin; E freezes a new live
   config and passes held-out detector/homography gates.
3. A supplies accepted rollout manifest, registry and clips; the E run is
   registered against their literal hashes.
4. B supplies direction/dose interpretation; D supplies the complete control
   manifest.
5. E runs localization, SSIM, measurement, QA and scripted figures.

Any schema mismatch stops processing and becomes a migration proposal—not a
silent adapter repair.
