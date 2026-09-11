# Five-hour revision: completed work and claim boundaries

This revision adds executed experiments, not hypothetical results or a relabeling of older runs. Earlier captures, predictions, papers, and releases remain separate and unchanged.

## What changed

| Concern | Completed action | What the evidence supports |
|---|---|---|
| Reused identities | Captured 96 new identities, split into 48 training and 48 untouched test identities before scoring | A new held-out cohort, not an independent research-group replication |
| Narrow conditions | Two layouts, two speed bands within each direction, and 700M/300M checkpoints | Broader conditions and parameter scale within one model family; not generality across architectures or entities |
| Unclear use of history | Correct, reciprocal swapped, and repeated-current image histories with unchanged current images and actions | Removing history worsens decoding; swapped predictions do not reliably follow donor position |
| Linear probe restriction | Training-only PCA plus a small nonlinear probe, with fixed tuning and seeds | Converged 700M nonlinear RMSE is 1.240 rather than ridge's 1.603 blocks on the primary interval |
| Baseline information mismatch | Retained current/history pixels, metadata and oracle predictors; added a same-window image tracker and detector-coverage accounting | Metadata remains strong; tracker limitations and unequal resolution/pretraining remain explicit |
| Geometry confounding | Frozen transfer, visible-only affine output calibration, and native destination fits | Visible calibration improves visible transfer but does not restore hidden decoding |
| Reproducibility | Exact targets, splits, predictions, configurations, hashes, source, and CPU reconstruction | All three studies rebuild exactly on a clean Windows CPU environment; full inference additionally needs archived images and model checkpoints |
| Paper usability | Eight-page main text, references starting on page nine, complete appendix and checklist, all 29 rendered pages inspected | No unresolved references, overfull boxes, or observed overlap in the delivered version |

## Main new results

For 48 held-out identities at occlusion ages 1–10, mean identity RMSE is 1.603 blocks for 700M ridge, 1.588 for 300M ridge, 1.915 for history pixels, 1.240 for the converged 700M nonlinear readout, and 0.154 for direction-and-age metadata. The paired 700M ridge minus history-pixel interval crosses zero, so the new pooled comparison alone does not establish a reliable neural advantage.

Repeating the current image in place of history increases 700M ridge RMSE by 2.314 blocks, with a donor-pair bootstrap interval of [2.068, 2.560]. Swapping histories changes it by -0.094 [-0.144, -0.047]. Prediction changes agree with donor-minus-recipient position direction on only 32.1% of target rows. These findings distinguish history sensitivity from faithful donor-state tracking.

The original 500-iteration nonlinear fits are retained alongside a separately frozen, training-warning-triggered budget extension. No hyperparameter search was reopened. All 24 extended seed-level fits converged. A visibility-count validation shortcut was corrected using recorded flags; no capture, target, prediction, original statistic, or inclusion decision changed. The failed check and repair are included in provenance.

## Verification

- 192 paired production recordings and 34,560 frames passed capture checks.
- All 40,128 original prediction cells passed saved-fit replay and independent arithmetic checks.
- The separate optimizer check adds 7,296 replayed prediction cells.
- Nine diagnostic regression tests passed.
- The three-study package reconstructed exactly in 23.97 seconds on Windows/Python 3.11 with NumPy 1.26.4, without PyTorch or scikit-learn.
- All original deliveries remained byte-for-byte unchanged.

## Remaining release action

The existing anonymous repository remains on its older snapshot. Updating it requires the owner's authenticated session. Neither the private repository's visibility nor the live Overleaf project was changed. The new Overleaf ZIP is a separate importable project. The anonymous reproduction ZIP can also be attached through the submission system, after which unauthenticated reviewer access should be verified.

These additions strengthen the empirical characterization but do not establish a causal memory mechanism, broad physical-reasoning capability, or guaranteed acceptance.
