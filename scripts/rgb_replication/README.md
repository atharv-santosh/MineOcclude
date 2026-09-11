# MineOcclude: verified RGB and matched-history follow-up

This directory adds a separate analysis namespace. It never relabels the original
BGR run as RGB and does not change its frozen authority or predictions.

## Inputs

The parent repository is MineOcclude. The recovered capture release is
`exp3a-final-trajectories-v1` on `data/experiment-iii-final-trajectories`.
The prediction/configuration release is `exp3a-reproducibility-v1` on
`data/experiment-iii-reproducibility-package`. Archive and per-file hashes must
pass `audit_recovery.py --frames` before extraction. Inputs reside below
`recovery_inputs/`; generated outputs reside below `replication_outputs/`.

Use the pinned upstream MineWorld commit and exact checkpoint/VAE hashes in
`reproducibility/experiment_iii_a/provenance/MODEL_PROVENANCE.json`.
Set `MINEOCCLUDE_WEIGHTS` to a directory containing
`700M_16f.verified.ckpt`, `vae.verified.ckpt`, and `config.json`.
The upstream checkout goes in `recovery_inputs/MineWorld-Upstream`.
The input captures go in `recovery_inputs/corpus/captures/<capture_id>`.
Place the five release archives in `recovery_inputs/archives/`, keeping their
release filenames. Export the trajectory branch's tracked metadata under
`recovery_inputs/metadata/data/experiment_iii/final_trajectories/`; that directory
must contain `ARCHIVES.json` and `SHA256SUMS.txt`. The frame audit verifies and
safely unpacks the release archives before checking all 24,500 files.

## Full execution (from repository root)

Use the dedicated Python environment listed in the runtime report. `PYTHONPATH`
must include `src` (or install this repository editable without altering its
dependencies). No training or gradients are used in the frozen world model.

```sh
python scripts/rgb_replication/audit_recovery.py --frames
python scripts/rgb_replication/audit_recovery.py
python scripts/rgb_replication/build_pixels.py
python scripts/rgb_replication/fit_readouts.py
python scripts/rgb_replication/extract_features.py --profile --order RGB
python scripts/rgb_replication/extract_features.py --order RGB
python scripts/rgb_replication/fit_readouts.py --models MW_RGB_L19 MW_RGB_L04 MW_RGB_L10
python scripts/rgb_replication/extract_features.py --profile --order BGR
python scripts/rgb_replication/extract_features.py --order BGR
python scripts/rgb_replication/fit_readouts.py --models MW_BGR_L19 MW_BGR_L04 MW_BGR_L10
python scripts/rgb_replication/extract_features.py --order RGB --pairs 1
python scripts/rgb_replication/extract_features.py --order RGB --pairs 8
python scripts/rgb_replication/fit_readouts.py --models MW_RGB_L19_CTX1 MW_RGB_L19_CTX8 --conditions L0 L4
python scripts/rgb_replication/validate_new.py
python scripts/rgb_replication/summarize.py
python scripts/rgb_replication/make_figures.py
python scripts/rgb_replication/make_tables.py
```

Extraction checkpoints each completed capture atomically. Existing prediction
files are preserved, not silently overwritten. Use a fresh output namespace for
any changed protocol, implementation, weights, inputs, precision, or environment.
Validate all hashes before treating resumed outputs as the same run.

## Statistical reproduction without inference

The compact deliverable includes predictions, labels/folds, provenance, source,
and five matched example images. From its extracted root:

```sh
python -m pip install -r requirements-cpu.txt
python scripts/rgb_replication/reproduce.py
```

This verifies input hashes, rebuilds the identity-level summaries and paired
10,000-draw intervals, checks equality with the supplied snapshot, and redraws
the figures. It needs no GPU, model checkpoint, full captures, or activation
arrays. The full experiment still needs the recovered capture release and the
upstream model. The compact package is not a redistribution of model weights.

`PROTOCOL.md` records the pre-outcome analysis scope. The original historical
statistics and the new runs are separate. The new comparisons reuse the central
25 identities and are exploratory estimates, not an independent confirmation.

## Numerical verification

The efficient ridge procedure matches the original reference implementation on
the same host. Historical statistics reproduce exactly from the sealed original
predictions. Cross-host pixel refitting is not bitwise identical: floating-point
linear algebra and near-constant image features can affect tuning. The snapshot
therefore preserves actual held-out predictions, not just rounded aggregate
tables. No new run is represented as a byte-identical historical refit.
