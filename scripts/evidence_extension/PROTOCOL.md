# MineOcclude evidence extension, 2026-09-11

Status: implementation and engineering pilots. Existing studies remain immutable.

## Ordered work and boundaries
1. Cross-visibility transfer on the verified five-condition RGB cohort.
2. Disjoint engineering motion pilots, then a prospective production lock.
3. New family-grouped motion cohort, fixed-appearance opacity intervention.
4. Equal-history frame differences, optical flow, and frozen VideoMAE-S.
5. Independent prediction/statistics replay; new paper/PDF and reproduction bundle.
6. Anonymous reviewer access verification. Owner authentication is not assumed.

No outcome-dependent exclusions, no test-label tuning, and no overwrite of prior
experiments. Old 25-identity analyses are developmental, not independent evidence.
No claims of physical mechanisms or memory solely from decodability.

## Cross-visibility analysis, locked before execution
Reuse exact RGB layer-19 coarse features, targets and five identity-grouped folds
from the corrected-RGB replication. For each source condition, train normalization
and ridge alpha using source training identities alone and the existing four inner
rotations. Alpha grid {0.1,1,10,100,1000}. Freeze each outer fit and apply to all five
destinations on held-out identities without recalibration. Report all 25 cells,
mean identity RMSE and MAE, paired transfer penalty relative to each destination's
diagonal fit, and 10,000 identity-bootstrap percentile intervals (seed 94111).
Retain per-row predictions, fit coefficients, normalization, selection and hashes.
Check diagonal agreement with the already reported RGB predictions and independently
replay saved fits. Source-only constant-column removal is retained, never test-based.

## Motion design, engineering subject to admission
Four history-observable families: persistent entry velocity, visible acceleration,
periodic stop-resume, and predictable reversal. Two matched variants per family.
Same entry position, direction, layout and observation age, different informative
pre-occlusion histories. A separate unobservable-divergence control has identical
observed inputs and different hidden targets; successful branch decoding there is
a leakage alarm, not the expected result. Rendering, target alignment and schedule
inference must be verified on disjoint pilots before production is admitted.
Provisional production 128 independent families: 64 training, 64 test, balanced
across two layouts and four motion families; two variants and air/stone gives 512
recordings. Paired variants stay in the same split and resampling unit. Confirm or
amend the number using pilot variance/throughput before viewing production outcomes.
Primary early-hidden ages 1-10, secondary 11-15, context-expired 16-19 separately.

## Opacity and comparators
Fixed wall appearance and a geometry-defined, sheep-independent screen mask;
opacity {0,.25,.5,.75,1} applied to every frame of each 16-frame input. Alpha zero
must be byte-identical to air; pixels outside the mask unchanged; alpha one blocks
the designated occluded region. Report synthetic versus real-stone endpoints.
Matched-history comparators receive identical timestamps and no future frames or
hidden labels. VideoMAE-S uses a verified official checkpoint and frozen features;
document resolution and pretraining differences. Fit and tune only on training
families. Metadata and privileged oracle baselines remain explicitly distinguished.

## Completion checks
Each stage has exact inputs, immutable predictions, manifest hashes, validation
receipt and claim bounds. Reproduce tables in a fresh CPU-only location. Render
and inspect every final PDF page. Verify anonymous access rather than inferring
publication from private GitHub availability. Completion does not imply favorable
results; unresolvable dependencies must be reported explicitly.
