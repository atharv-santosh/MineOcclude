# Corrected-RGB and matched-history follow-up

Authorized 2026-09-11. This is a new follow-up, not a modification of the frozen
Experiment III-A run. The user extended the original 90-minute budget to a few
hours. Preparation and execution times will be reported separately.

## Fixed primary scope before examining new outcomes

- All 25 original identities, all five conditions, all 19 targets: 2,375 windows.
- Same checkpoint and VAE hashes, original actions, exact joined frames, targets,
  five outer identity folds and four inner rotations.
- Correct RGB at the actual visual tokenizer input. Preserve the original
  interpolation, normalization, float16 inference and fresh 16-pair cache reset.
- Primary representation: layer 19, current-pair coarse 2x6 concatenation.
- Also retain layers 4 and 10 from the same forwards as secondary sensitivity
  analyses. They are not alternative candidates for reselecting the primary.
- Ridge alpha {0.1,1,10,100,1000}, training-only feature standardization and
  unpenalized intercept. Select by mean identity RMSE over inner rotations.
- Current-pixel baseline and exact 16-frame pixel-history ridge, area 48x28 RGB
  per frame. No age, direction, state, identity or target enters image features.
  Verify recorded action constancy; if nonconstant, include the same action
  information in the history baseline and document its encoding before fitting.
- Compare to recovered legacy predictions, metadata and oracle-history models.
- Additional context-length or shuffle experiments require a separate recorded
  pre-outcome scope decision after engineering profiling. None is implicit here.

## Additional pre-outcome engineering allocation (2026-09-11, before new metric inspection)

The extended budget permits a matched-runtime BGR replay of all five conditions
if profiling projects at most 45 minutes. This controls the PyTorch/GPU change
when contrasting channel order. Historical BGR predictions remain distinct.
If each adds at most 20 minutes, also evaluate genuine 1-pair and 8-pair contexts
on all 25 identities in L0 and L4, using the last 1 or 8 actual recorded pairs,
context-relative positions and reset cache. No repeated-frame padding.
These are secondary context-length sensitivity analyses, not model selection.
Cost and native input support, never performance, determine whether they run.
This allocation precedes inspecting new prediction metrics.

## Evaluation

Report mean identity RMSE, MAE, trajectory R2, and paired whole-identity percentile
bootstrap intervals (10,000 draws, seed 20260911), conditional on fitted models.
Primary paired comparisons are corrected RGB versus legacy BGR and versus the
16-frame pixel-history baseline, with condition-specific intervals. These are
estimation analyses, not new prespecified confirmatory hypothesis tests.
Any age-sliced analysis uses actual last-preocclusion and context-window indices.
No independent cohort claim: these are the same recovered original identities.

## Integrity and runtime

Verify archive/file hashes, canonical prediction seal, all labels against the
capture logs, row uniqueness, exact folds and no identity leakage. Verify cached
visual tokens against complete-window tokenization; reject caching if unequal.
Validate efficient ridge predictions against the existing implementation.
Use a dedicated WSL environment. PyTorch 2.7.1/cu128 is required for this RTX5090,
versus original 2.6.0/cu126 on L4. Document this runtime change and numerical
checks, rather than attributing all cross-run differences solely to color order.
Do not alter historical code/results, recapture scenes or publish externally.
Export compact predictions, immutable configuration, checksums and CPU rebuild.
