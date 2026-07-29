# Person B Analysis Artifact Contract v0.1

Status: implemented before live results.

## Provenance envelope

Every B-owned analysis artifact carries:

- `artifact_schema_version = "person-b-analysis-artifact-v0.1"`
- `artifact_type` and `artifact_id`
- 40-character hexadecimal `code_sha` derived from the producing code bytes
- literal-file `config_hash`
- `input_manifest_hash`
- `artifact_hash`

The artifact hash is SHA-256 over canonical UTF-8 JSON containing every other
field. Finite floats are published at 12 decimal places so final-bit BLAS
differences cannot change evidence identity; nonfinite floats are not
serializable. Any alteration invalidates the artifact.

Within B-owned bridge artifacts, `code_sha` is byte-level code provenance, not
a claim that the value names a Git commit. The producing code defines the
exact ordered source-byte set used to derive it.

## Ordered filters

Filters run once in this order:

1. required fields and unique frame identity;
2. accepted lifecycle;
3. finite numeric values;
4. accepted-manifest equality;
5. post-first-seen eligibility.

Each input receives at most one first-failure code. Every step records input,
rejected, and output counts. Rows are never clipped, repaired, or silently
dropped.

## Fold and preprocessing artifacts

Before Person A joins, `layout_fold_plan` freezes layout-to-fold and
trajectory-to-fold assignments from accepted Person C condition rows only. It
records per-layout row/trajectory evidence, per-scope five-fold coverage,
source/intake hashes, the literal config, code, seed, and the explicit absence
of A artifacts and outcome fields.

Later fold manifests save exact frame memberships, layout-to-fold assignments,
strategy, seed, fold count, input manifest, config, code, and content hash.
The real pilot runner rejects them unless they exactly preserve the pre-A
layout plan, then embeds `source_layout_fold_plan_hash` in the frame manifest
and both hashes in the pilot receipt.
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

## Real-pilot artifact chain

The compatible Phase 6 implementation adds sealed artifacts without changing
the frozen targets, folds, metrics, or selection rules:

- `capture_intake_report`, which authenticates literal C package bytes,
  records signed coordinate projections and no-object quarantine, and remains
  explicitly pending A provenance/activations;
- `layout_fold_plan`, which freezes real outcome-independent layout and
  trajectory assignments from accepted C rows before A arrives;
- `oracle_target_document` and `oracle_audit`;
- `joined_frame_table`, `filter_audit`, and `pilot_intake_receipt`;
- `analysis_selection_manifest` and `fold_manifest`;
- `probe_matrix_manifest`, `scaler_manifest`, and `ridge_fit_manifest`;
- `prediction_manifest`, `result_manifest`, `probe_scope_bundle`, and
  `u2_calibration_bundle`;
- `positive_control_gate` and `pilot_failure`;
- `baseline_request_manifest` and `cross_role_schema_report`.

The matrix, scaler, fit, prediction, and result chain contains direct artifact
hashes suitable for E's immutable registry. Failure outcomes use null, never a
scientific zero. D/E/A request packets remain requests until their separately
owned acknowledgements exist.

## Correction policy

Corrections are append-only. Every updated log points to the prior log hash and
records the affected artifact, reason, resolution, new-run requirement, and
approving roles. Result-affecting corrections require a new run and may not
overwrite prior artifacts.
