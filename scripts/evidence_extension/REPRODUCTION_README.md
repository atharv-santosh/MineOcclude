# MineOcclude evidence extension

This snapshot preserves all preceding cohorts and adds five-condition decoder
transfer, stronger equal-history baselines, fixed-appearance opacity, and a new
paired-motion cohort. Numerical outcomes are not pooled across cohorts.

## CPU replay

Use Python 3.10 or 3.11 and NumPy 1.26.4. No GPU, API key, model checkpoint, or
network connection is needed to reconstruct the extension tables and intervals:

```
python extension/reproduce.py
```

From the snapshot root, the preserved `reproduce_all.py` reconstructs the earlier
central, fresh-cohort, and history-diagnostic studies using their original scripts.
Those preserved studies additionally use Pillow and Matplotlib as documented in
their respective readmes. The new script verifies its file inventory and compares
reconstructed values to the locked results at an absolute tolerance of 1e-8.

With Matplotlib installed, regenerate both extension figures without inference:

```
python extension/source/make_figures.py --root extension --output reconstructed-extension-figures
```

Use a new output directory: the generator preserves existing figures rather than
silently overwriting them. The numerical replay above is the correctness check;
PDF timestamps are not expected to be byte-identical between machines.

## Contents and scope

The extension includes row-level held-out predictions, targets, fold membership,
hyperparameter selections, motion schedules, analysis specifications, feature and
capture hashes, validation reports, and executable analysis source. Local
saved-weight/feature replay is documented separately in the validation receipts.
The compact snapshot does not bundle the large raw captures, activation arrays,
MineWorld checkpoint, or VideoMAE weights. Hashes identify those inputs; do not
mistake prediction-to-statistics replay for rerunning GPU extraction.

VideoMAE-S uses the official MCG-NJU VideoMAE pretrained Kinetics-400 small model
(1600 epochs). Its source and checkpoint provenance are recorded in configuration.
The upstream license is CC-BY-NC-4.0; this scientific comparison is noncommercial.
Official source: https://github.com/MCG-NJU/VideoMAE .

Pilot failures and all bounded motion/approach revisions are retained. An initial
training capture exposed insufficient visible approach; its superseded artifacts
were archived before a uniform approach amendment and before held-out capture or
fitting. The original lock and amended lock are both included. Engineering-only
captures never enter production fits or reported scientific intervals. The identical-input
control is explicitly constructed and is not presented as an empirical test of
successful hidden-future identification.

Private account paths in copied execution provenance are anonymized. The change
receipt distinguishes original execution hashes from distributed file hashes.
Prediction values and scientific results are unchanged. Anonymous website access
must be verified separately; possession of this local ZIP is not proof of upload.
