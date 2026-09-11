# Experiment III-A — complete reproducibility package

Everything needed to audit, re-derive and reuse the closed Experiment III-A run, **except the
22,500 captured PNG frames**, which are published separately and are deliberately not duplicated
here (see §2).

Nothing in this package was regenerated, refit, or re-run. Every artifact is either the original
runtime byte stream or an index derived from one, and the derived ones say so in their own
`derivation` field.

| | |
|---|---|
| Authority | **v1.8** · `472eae5eac83a2709808e64aa449a2ffba24a5a12715b4f1645ce88a3094a9f4` |
| Source closure | `cdee2a8ba0f6093fc6d9c961718adbee5315e71f1c640bbb1570f0e5b3b10dd0` |
| P2 package | `f0e9d954d187acdf2a479683cde40bd89d4cae5a8fabc6b3cefb010f0f99f7a8` |
| Implementation commit | `a91502ce2cd421721f8c638eaeea013a1fcddaf1` (tree `3846709e…`) |
| Prediction-lock seal | `2a25bcb01107a2b4e899bf5575c116d86a12400ca3aa5c12e6339f866778ddf9` |
| Run | A7 → A19, 2026-09-02T03:08:28Z → 05:33:11Z, `errors_seen=0`, closure `EXPERIMENT_III_COMPLETE` |
| Cohort | 25 identities × 5 conditions = 125 captures · 22,500 frames · 2,375 target rows |

## 1. What is here

```
reproducibility/experiment_iii_a/
    provenance/
        EXECUTION_PROVENANCE.json     per-stage A7→A19 outcomes + the supervisor's timeline
        SOURCE_IDENTITY.json          commit / tree / closure, and the no-uncommitted-changes proof
        ENVIRONMENT_PROVENANCE.json   hosts, GPU, interpreters, runtime pins
        MODEL_PROVENANCE.json         checkpoint + VAE hashes, architecture, hook sites, slices
        COMMAND_PROVENANCE.md         the exact executed commands, A7 → A19
        pip_freeze_…txt               CURRENT_ENVIRONMENT_NOT_EXECUTION_PROVENANCE
        receipts/                     26 original stage receipts, ledgers and manifests
    cohort/
        CAPTURE_INDEX.json            125 captures: seeds, specs, folds, windows, conditions
        ACTION_INDEX.json             per-capture action/tick/state stream hashes + shape
        FRAME_TARGET_ALIGNMENT.json   every target row → model frame → render frame → PNG hash
        EXECUTED_TARGETS.json         all 2,375 executed target rows with values
        FOLD_ASSIGNMENTS.json         5 outer folds × 4 inner rotations, verbatim
        MASKS.json                    extent / eligibility / evaluation masks per capture
        FIR_ALIGNMENT.json            per-capture FIR labels, context ages, target windows
    prediction_lock/
        PREDICTION_LOCK.json          23,750 sealed cells (prediction + target)
        PREDICTION_LOCK.sha256
        PREDICTION_LOCK_HASH_NOTE.md  why that file is NOT the file's sha256 — read this
    results/                          the 13-artifact A19 scientific package + the A12 fit receipt
    analysis_inputs/
        FEATURE_BLOCK_INDEX.json      750 A11 blocks, hashed, bound to the lock seal
        ACTIVATION_INDEX.json         750 A9 arrays, hashed against A9's own inventories
        S3_ARTIFACT_INDEX.json        every Experiment III S3 object and what it is
    legacy_bgr/
        README.md                     the channel-order forensics — read this before results
        CHANNEL_ORDER_MANIFEST.json   every artifact classified by channel condition
        preprocessing/PREPROCESSING_PROVENANCE.json
    code/
        EXECUTED_SOURCE_MANIFEST.json 586 closure records with per-file sha256
        SOURCE_SHA256SUMS.txt
        ops/                          launch_a7.sh, supervise.py, capture_runtime_config.json
        logs/                         supervisor.log + a7…a19 stage logs, verbatim
    manifests/
        ALL_ARTIFACTS.json
        SHA256SUMS.txt
        MISSING_ARTIFACTS.json
```

There is **no `corrected_rgb/` directory**, because no corrected-RGB artifact exists. See §5.

## 2. The frames live elsewhere

The 22,500 original A7 PNG frames and the 2,000 per-capture JSON/JSONL sidecars are published as
their own dataset:

- branch **`data/experiment-iii-final-trajectories`**, path `data/experiment_iii/final_trajectories/`
- release **`exp3a-final-trajectories-v1`** (5 × `tar.gz`, ~1.56 GiB total)

They are not copied into this branch. `cohort/ACTION_INDEX.json` and
`cohort/FRAME_TARGET_ALIGNMENT.json` carry the sha256 of every stream and every target frame, so
the two packages cross-verify each other.

## 3. Reconstructing the run locally

```bash
git clone https://github.com/atharv-santosh/MineOcclude.git && cd MineOcclude

# (a) the reproducibility package
git checkout data/experiment-iii-reproducibility-package

# (b) the frames, into the same tree
git checkout data/experiment-iii-final-trajectories -- data/experiment_iii/final_trajectories
gh release download exp3a-final-trajectories-v1 -p '*.tar.gz' \
   -D data/experiment_iii/final_trajectories
cd data/experiment_iii/final_trajectories
for f in mineocclude_exp3a_final_trajectories_part*.tar.gz; do tar -xzf "$f"; done
./verify_corpus.sh        # FULL_CORPUS_VERIFY=OK (24500 files)
cd -

# (c) the big derived arrays, from the durable S3 archive
aws s3 sync s3://sagemaker-us-east-1-323206973672/mineocclude/experiment_iii/a11_feature_blocks_p2_f0e9d954_lock_2a25bcb0/ \
            data/experiment_iii/features/                       #  2.9 GB, 750 arrays
aws s3 sync s3://sagemaker-us-east-1-323206973672/mineocclude/experiment_iii/a9_production_activations_p2_f0e9d954_lock_2a25bcb0/ \
            data/experiment_iii/production/activations/         # 19.6 GB, 876 objects
```

Step (c) needs credentials for that account. If you do not have them, the package is still
self-contained for everything except re-running A11/A12 from raw activations: the sealed
predictions, all targets, all folds and all results are in this branch.

Re-deriving the statistics needs nothing but `prediction_lock/PREDICTION_LOCK.json` — it carries
both the prediction and the target for all 23,750 cells.

## 4. Verifying what you got

```bash
cd reproducibility/experiment_iii_a
sha256sum -c manifests/SHA256SUMS.txt          # every file in this package
```

Five independent checks were run before publication, and you can repeat each:

1. **Prediction-lock seal** recomputes from the lock body — see `prediction_lock/PREDICTION_LOCK_HASH_NOTE.md`.
2. **750/750 feature blocks** match the digests sealed inside that lock (`block_digest` convention).
3. **750/750 activation arrays** match the sha256 A9 wrote into its own extraction inventories.
4. **2,375/2,375 targets** in the lock equal the `fir_labels` A7 wrote into `capture_completion.json`.
5. **Source closure** `cdee2a8b…` recomputes from the committed tree, with zero working-tree delta.

## 5. Channel order — read before interpreting any result

The model saw **BGR**. `scripts/experiment_iii/run_extraction.py::_load_frame` handed true-RGB
pixels to a preprocessing function whose first step is `cv2.cvtColor(src, COLOR_BGR2RGB)`, so the
channels were reversed on the way into MineWorld. The pixel baseline was *not* affected — it
reads the PNGs directly as RGB.

This was **known before production and frozen deliberately**: authority v1.8 records
`mineworld_historical_preprocessing_channel_order: "BGR"`, sets
`rgb_bgr_historical_behavior_change_allowed: false`, and lists
`FIX_THE_HISTORICAL_RGB_BGR_PREPROCESSING_BEHAVIOR` among the forbidden repairs. It is a declared
scope limitation, not an undetected bug.

```
CORRECTED_RGB_OUTPUTS=NONE_FOUND
```

No corrected-RGB rerun exists, and none was produced by this recovery. Full forensics, including
the empirical bit-for-bit proof, are in [`legacy_bgr/README.md`](legacy_bgr/README.md).

## 6. Scope

- **No verdict.** Experiment III emits no overall pass/fail and no success gate (authority
  §8.10.6). `EXPERIMENT_III_COMPLETE=true` is a statement about completeness, not outcome.
- **Model binaries are not redistributed.** The 700M checkpoint (3.80 GB) and VAE (1.66 GB) are
  identified by sha256, size, path and upstream revision in `provenance/MODEL_PROVENANCE.json`.
- **Nothing was altered.** This package reads the closed run and copies it outward. No receipt,
  ledger, result or capture was modified, and no predecessor S3 key was overwritten.
- **Superseded cohorts are excluded.** The P2 `7d94a1c7` and `0d286dde` predecessor runs are not
  represented here except as named exclusions.
- **Paths and bucket names are kept, not redacted.** The absolute host paths and the S3 bucket
  URI appear throughout because receipts recorded them and the reconstruction steps need them.
  No credential, token, key or personal identifier is present; this package was scanned before
  publication.
- **License.** The repository declares none; treat this as internal research data under its
  existing private status.
