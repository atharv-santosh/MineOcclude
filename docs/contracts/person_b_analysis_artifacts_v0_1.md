# Person B Analysis Artifact Contract v0.1

Status: implemented before live results.

## Provenance envelope

Every B-owned analysis artifact carries:

- `artifact_schema_version = "person-b-analysis-artifact-v0.1"`
- `artifact_type` and `artifact_id`
- full `code_sha`
- literal-file `config_hash`
- `input_manifest_hash`
- `artifact_hash`

The artifact hash is SHA-256 over canonical UTF-8 JSON containing every other
field. Nonfinite floats are not serializable. Any alteration invalidates the
artifact.

## Ordered filters

Filters run once in this order:

1. required fields and unique frame identity;
2. accepted lifecycle;
3. finite numeric values;
4. post-first-seen eligibility;
5. accepted-manifest equality.

Each input receives at most one first-failure code. Every step records input,
rejected, and output counts. Rows are never clipped, repaired, or silently
dropped.

## Fold and preprocessing artifacts

Fold manifests save exact frame memberships, layout-to-fold assignments,
strategy, seed, fold count, input manifest, config, code, and content hash.
Inner folds are rebuilt using outer-training layouts only. Scaler artifacts
record training-row count, feature means/scales, constant feature indices, and
outer fold. Constant features use scale `1` and are explicitly listed rather
than silently removed.

The fixed U4 development partition uses only layout IDs and the frozen seed:
three fit layouts, one validation layout, and two test layouts. Its sealed
manifest stores exact membership and recomputes it during validation. Outcomes
are absent from the selection interface.

## Fits, predictions, and results

Ridge fit manifests contain selected alpha, every inner-validation loss,
standardized/raw coefficients and intercepts, scaler/fold hashes, and exact
training/test row indices. Prediction manifests require every row to be
`out_of_fold` or `held_out`. Result manifests require explicit sample count,
sample unit, metric unit, and `valid`/`invalid` status. Invalid metrics use
`value = null` and retain a diagnostic; they are not deleted.

## Correction policy

Corrections are append-only. Every updated log points to the prior log hash and
records the affected artifact, reason, resolution, new-run requirement, and
approving roles. Result-affecting corrections require a new run and may not
overwrite prior artifacts.
