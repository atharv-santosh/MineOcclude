# MineOcclude reproduction snapshot

This package keeps three separate studies separate. No hypothetical outcomes
are included, and no prior prediction is relabeled as a different input convention.

## Reproduce the reported statistics on a CPU

In a fresh Python 3.10--3.12 environment, from an extracted working copy:

```sh
python -m pip install -r requirements-cpu.txt
python reproduce_all.py
```

The command checks the complete input inventory and reconstructs every supplied
statistical summary. It needs no GPU, Minecraft installation, model checkpoint,
activation tensor, network connection, or author account after installation.
The central-study command also redraws its figures, so use a working copy if
you want to retain the archive byte-for-byte. Generated PDF metadata may differ
across machines; numerical summaries are checked exactly.

## Contents and independent units

- `central/`: 25 graded-evidence identities, five materials, verified RGB,
  same-runtime BGR, history pixels, and context/depth checks. This follow-up
  reuses the central identities and is not a new cohort.
- `fresh/`: 75 subsequently captured identities, 25 each in the original
  setting, changed geometry, and higher speed. Within-setting refits and
  unchanged-probe transfer are separate analyses, totaling 25,650 cells.
- `diagnostic/`: a prospectively frozen variable-speed study with 48 training
  and 48 untouched test identities across two layouts. Air and stone, two model
  sizes, linear/nonlinear readouts, correct/swapped/removed histories, image
  tracking, and visible-only calibration total 40,128 prediction cells.
- `execution_source/`: capture, extraction, fitting, and validation source.
  Local account paths are anonymized, not silently presented as the original
  byte-identical execution source. The adaptation ledger and separate hashes
  make this distinction explicit. Configure runtime/capture roots before full
  execution on a different machine.

Predictions are indexed by identity, material, target age/time, model, and
analysis setting. Targets, train/test assignments, tuning folds, model choices,
hashes, and protocols accompany them. Paired observations and repeated frames
must never be treated as independent identities. The diagnostic's interventions
resample reciprocal donor pairs because the two recipients share donor data.

## Statistics versus full experiment reproduction

The command above reconstructs statistics from held-out predictions. It does
not rerun world-model inference or manufacture new captures. Full inference
requires the separately archived recordings and hash-pinned upstream MineWorld
checkpoints, including the shared VAE. Full recapture additionally requires a
licensed Minecraft installation and the Fabric capture mod. No Minecraft
binaries or MineWorld weights are redistributed here. See each study's
configuration, runtime receipts, and execution documentation for exact inputs.

Fitted ridge/PCA/MLP arrays are available in the separate optional
`mineocclude_fitted_readouts.zip`, saved without Python pickle. They support
inspection and replay when the corresponding feature arrays are available.
They are not needed for the compact statistics rebuild, whose JSON fit records
include the selected parameters and hashes. The compact package intentionally
avoids multi-gigabyte activations.

## Scope

The protocol compares visual evidence, finite-window readout accuracy, and
motion predictability. Input-history substitutions are not identified causal
circuits, and two sizes of one pretrained family do not establish broad model
generality. All comparisons, uncertainty intervals, tracker fallbacks, and
unfavorable outcomes remain in the prediction and statistics files.

Public reviewer access must be verified on the actual distribution channel.
Possession of this local package or access to an older project mirror does not
by itself establish that a newly submitted snapshot is accessible.
