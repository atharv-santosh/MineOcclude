# 16 — Prospective Authority-Neutrality Audit

**Result: PASS.** Reusable infrastructure measures; caller configuration or
authority adjudicates. No new scientific authority is created here.

## Classification of sweep hits

| Classification | Occurrences |
|---|---|
| Implementation constants | Boolean confusion-count zeroes; finite/non-negative/index checks; SHA-1/SHA-256 encoded lengths; mathematical fraction domain [0,1]; average-of-two definition; valid apparatus direction labels; FIR design needs at least `max_lag+1` equations; 10-decimal camera serialization tolerance (`1e-9`) |
| Test fixtures | 0.95 confidence request, bootstrap count/seed, synthetic minimum trajectories/samples, speed/direction/scene requirements, visibility fractions, support-gap requirements, historical-value examples |
| Descriptive historical values | Docstrings/tests referring to historical precision 0.95, measured lag ≈3.364, P2 RMSE/R², and historical hidden-bounds defect |
| Scientific authority choices | `SupportRequirements`, `AlignmentRequirements`, `UncertaintyRequest`, `VisibilityPolicy` (including its primary predicate), exact path/index mappings and hashes—all mandatory caller inputs or absent with UNADJUDICATED/MEASURED_NOT_ADJUDICATED result |

## Explicitly removed defaults

- source verification cannot omit expected commit or SHA-256;
- timebase cadence has no default;
- temporal `max_lag_ticks`, minimum trajectory/support coverage, required
  directions/speeds/scenes, uncertainty width, confidence level, bootstrap
  procedure, and FIR/pure-delay discrepancy are caller supplied;
- calibration maximum gap, endpoint tolerance, and minimum samples are caller
  supplied;
- the primary visibility predicate, fractional thresholds, and evidence
  requirements are caller supplied;
- confirmatory membership is explicit rather than defaulted.

Measurements without the needed policy remain unadjudicated. No reusable
prospective module contains a precision, recall, specificity, FPR, RMSE, R²,
bootstrap, development-N, hidden-bound, world-x-bound, or stable-fraction
acceptance default.

`AUTHORITY_CHOICES_EMBEDDED_IN_CODE = false`

`AUTHORITY_NEUTRALITY_STATUS = PASS`
