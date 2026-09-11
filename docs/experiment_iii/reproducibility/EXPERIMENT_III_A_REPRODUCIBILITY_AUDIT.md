# Experiment III-A — reproducibility recovery audit

Scope: recover everything needed to reconstruct, audit and reuse the closed Experiment III-A run
**other than** the 22,500 PNG frames, which were recovered and published in a prior operation.

**Outcome: 28 of 30 requested categories recovered as original runtime artifacts or already published; one (`tokenizer hashes`) is not applicable to this model; one (`dependencies`) is recovered except for two unpinned transitive packages, documented in §3. One category, `corrected RGB outputs`, is `NOT_FOUND` because no such output was ever produced. Nothing was regenerated, refit or re-run.**

Identity of the run audited: authority v1.8 `472eae5e…`, source closure `cdee2a8b…`,
P2 `f0e9d954…`, implementation `a91502c` (tree `3846709e…`), prediction-lock seal `2a25bcb0…`.

---

## 1. Verification performed

Six independent cryptographic checks, each recomputed from bytes on disk on 2026-09-11:

| check | scope | result |
|---|---|---|
| Source closure recomputes | `git ls-files -s src fabric scripts`, 586 records, 58,706 stream bytes | `cdee2a8b…` — **exact match** |
| Prediction-lock seal recomputes | canonical JSON of the lock body | `2a25bcb0…` — **exact match** |
| Feature blocks ↔ lock | 750 blocks vs the `feature_block_hashes` sealed into the lock | **750/750, 0 mismatches** |
| Activation arrays ↔ A9 | 750 arrays vs the sha256 in each `extraction_inventory.json` | **750/750, 0 mismatches** |
| Targets ↔ capture layer | 2,375 lock targets vs the `fir_labels` A7 wrote per capture | **2,375/2,375, 0 mismatches** |
| Model assets | 700M checkpoint + VAE re-hashed in full | **both match**, `a92c311b…` / `370d06be…` |

The fourth and fifth are the load-bearing ones. A9's inventories and A7's completion receipts
were written by the run itself, days before this recovery, by stages that could not have
anticipated it — so matching them proves the published artifacts are the run's artifacts rather
than merely internally consistent.

## 2. Category-by-category disposition

| category | status | where / evidence |
|---|---|---|
| original frame corpus | `ALREADY_PUBLISHED` | branch `data/experiment-iii-final-trajectories`, release `exp3a-final-trajectories-v1`; 22,500 PNGs, verified against A7 durable receipts |
| recorded actions | `ALREADY_PUBLISHED` | `captures/*/raw/actions.jsonl`, 180 rows/capture, 22,500 total; indexed with hashes in `cohort/ACTION_INDEX.json` |
| timestamps / frame indices | `ALREADY_PUBLISHED` | `raw/client_tick.jsonl` carries `server_epoch_nanos`, `client_recv_nanos`, `client_capture_nanos`, `tick_queue_depth_at_capture`; `raw/frame_map.jsonl` carries `render_frame_idx` ↔ `server_tick` ↔ frame sha256. Re-indexed in `cohort/FRAME_TARGET_ALIGNMENT.json` |
| server-state logs | `ALREADY_PUBLISHED` | `raw/server_state.jsonl`, 180 rows/capture: scene, seed, `v`, `commanded_v`, `q`, `noise_draw`, `axis_pos`, `axis_velocity`, sheep x/y/z, target UUID, `spec_hash` |
| capture metadata | `RECOVERED_ORIGINAL` | 10 receipts per capture (physical, wall, camera, target, condition, path, timing, framebuffer, completion, durable); summarised in `cohort/CAPTURE_INDEX.json` |
| executed targets | `RECOVERED_ORIGINAL` | `cohort/EXECUTED_TARGETS.json`, 2,375 rows, each cross-verified against both the sealed lock and A7's `capture_completion.json` |
| target values | `RECOVERED_ORIGINAL` | FIR labels in world-x blocks; identical in three independent artifacts (identity manifest `expected_causal_fir_target_world_x_blocks`, capture completion `fir_labels`, lock `target`) |
| identity / condition mappings | `RECOVERED_ORIGINAL` | `cohort/production_identity_manifest.jsonl` (25 identities, seeds, directions, noise schedules, path hashes) + `capture_matrix.json` Latin square |
| visibility masks | `RECOVERED_ORIGINAL` | `raw/visibility.jsonl`, 180 rows/capture: counterfactual extent class, magenta status/area, server geometric status, `target_eligible`, RVE score |
| evaluation masks | `DERIVED_POST_HOC` | `cohort/MASKS.json` — assembled from the original visibility and completion receipts. All 125 captures: 19 evaluated rows, 0 excluded, 0 imputed, all target rows `EXTENT_FULLY_OCCLUDED`. Corroborated by A8 (`imputed_cells=0`, `dropped_conditions=[]`) |
| folds | `RECOVERED_ORIGINAL` | `cohort/FOLD_ASSIGNMENTS.json`, verbatim `folds.json`: 5 outer folds × 4 inner rotations, direction-balanced 3/2–2/3 |
| FIR alignment | `RECOVERED_ORIGINAL` | `provenance/receipts/fir_kernel_recovery_receipt.json` (9-tap causal kernels per direction, all acceptance gates passed) + per-capture labels in `cohort/FIR_ALIGNMENT.json` |
| prediction lock | `RECOVERED_ORIGINAL` | `prediction_lock/PREDICTION_LOCK.json`, 23,750 cells, untouched |
| prediction-lock seal | `RECOVERED_ORIGINAL` + **verified** | `2a25bcb0…` recomputed exactly; the raw-file-sha256 distinction is documented in `PREDICTION_LOCK_HASH_NOTE.md` |
| per-identity errors | `RECOVERED_ORIGINAL` | `primary_results.json` → `per_identity_estimands` (25), `identity_condition_metrics` (25); `temporal_results.json` → `per_identity_contrasts` (25); `context_age_results.json` → `per_identity_boundary_interaction` (25) |
| analysis inputs | `RECOVERED_ORIGINAL` | 750 A11 feature blocks (2.88 GB) and 750 A9 activation arrays (19.6 GB), both hash-verified and now durably archived to S3 |
| final result JSONs | `RECOVERED_ORIGINAL` | all 13 scientific-package artifacts + `prediction_fit_receipt.json` + `STATISTICAL_REPORT.md`; hashes match `scientific_package_manifest.json` |
| exact source commit | `RECOVERED_ORIGINAL` | `a91502c`, tree `3846709e…`; 586-record closure recomputes to `cdee2a8b…`; per-file sha256 in `code/EXECUTED_SOURCE_MANIFEST.json` |
| uncommitted changes | `NOT_APPLICABLE` — **proven none** | `closure_digest(working_tree=True) == closure_digest(working_tree=False)`, and `git status --porcelain -- src fabric scripts` is empty. No `UNCOMMITTED_CHANGES.patch` was written because there is nothing to write |
| extraction commands | `RECOVERED_ORIGINAL` | verbatim argv for A9 (and A7–A19) in `provenance/COMMAND_PROVENANCE.md`, taken from the surviving `supervise.py` and `launch_a7.sh` |
| probing commands | `RECOVERED_ORIGINAL` | hook configuration is not a separate command — `decoder_layer_output_residual_stream`, 20 layers registered transiently, layers {4,10,19} serialized, token-position hash `a375e640…`, slices PREVIOUS `[4858:5194]` / CURRENT `[5205:5541]`, one forward per target row (2,375 total) |
| dependencies | `RECOVERED_ORIGINAL` except numpy + Pillow | 15 packages pinned by three dated pre-run requirements files, all agreeing with the live interpreter; numpy and Pillow are pinned nowhere. See §3 |
| preprocessing | `RECOVERED_ORIGINAL` | exact five-step pipeline with constants, plus an empirical bit-for-bit replay, in `legacy_bgr/preprocessing/PREPROCESSING_PROVENANCE.json` |
| seeds | `RECOVERED_ORIGINAL` | 25 per-identity capture seeds (= `noise_seed`) in the identity manifest with `noise_schedule_sha256`; analysis bootstrap seed `8258108568742502015` **re-derived** from `MINEOCCLUDE_EXPERIMENT_III_ANALYSIS_BOOTSTRAP_V1\|` + `PHASE0_DESIGN_SHA256` and confirmed; A9 forward seed 0 |
| model hashes | `RECOVERED_ORIGINAL` + **verified today** | `a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5`, 3,798,736,924 bytes |
| VAE hashes | `RECOVERED_ORIGINAL` + **verified today** | `370d06be427e034476b6b95ba0080a4b48266e876c4776a757b944b87b87d9ab`, 1,657,555,486 bytes |
| tokenizer hashes | `NOT_APPLICABLE` | MineWorld has no separate text tokenizer. Video tokenization *is* the VAE (hashed above); the action vocabulary is 11 fixed tokens/pair inside the pinned adapter, which the source closure already covers. Vocab size 8262 |
| legacy BGR outputs | `RECOVERED_ORIGINAL` | every model-side artifact in the run; classified per-artifact in `legacy_bgr/CHANNEL_ORDER_MANIFEST.json` |
| corrected RGB outputs | **`NOT_FOUND`** | see §4 |
| final activations | `RECOVERED_ORIGINAL` | 750 arrays, `[19, 336, 2048]` float16, 26,148,992 B each, 19,617,105,515 B total; all 750 hash-verified against A9's inventories |

## 3. Dependencies: mostly pinned, two packages not

`ENVIRONMENT_PROVENANCE` separates what is receipted from what is merely observed.

**From the A3 environment receipt banked at execution time** — Python 3.10.20,
torch 2.6.0+cu126, CUDA 12.6, NVIDIA L4 (capability 8.9, 23,661,248,512 B), 4 CPUs,
`Linux-6.12.100-125.179.amzn2023.x86_64-x86_64-with-glibc2.39`, UTC; plus the full capture
runtime pins (Minecraft 1.16.5, Fabric loader 0.15.11, Fabric API 0.42.0+1.16, Yarn
1.16.5+build.10, 640x360 @ 20 Hz, 180 frames/capture, 2.0 blocks/s, mod jar `6513a967...`).

**From three dependency files that predate the run**, published under
`provenance/dependency_pins/` — `MineWorld-Upstream/requirements.txt` (tracked at the pinned
upstream revision `9f49efbc`, working tree clean), the mineworld-env install list from
`mineocclude-setup/`, and the repository's own `requirements.txt`:

```
torch 2.6.0 · torchvision 0.21.0 · opencv-python 4.11.0.86 · scikit-learn 1.6.1
scipy 1.15.2 · transformers 4.48.1 · diffusers 0.32.2 · omegaconf 2.3.0 · einops 0.8.1
gradio 5.24.0 · attrs 25.3.0 · torch-fidelity 0.3.0 · gym 0.26.2 · gym3 0.3.3
pyarrow 25.0.0 · Python 3.10
```

Every one of those agrees exactly with what the execution interpreter
(`~/.conda/envs/mineworld/bin/python`, still present on this host) reports today.

**The gap: `numpy` and `Pillow`.** Both are transitive dependencies pinned by no requirements
file and recorded by no receipt. They are the only two components of the executed stack whose
version at run time cannot be proven from an artifact dated on or before 2026-09-02. The live
interpreter reports numpy 1.26.4 and Pillow 11.3.0, published as observation only, under an
explicit `CURRENT_ENVIRONMENT_NOT_EXECUTION_PROVENANCE` header, alongside a full `pip freeze`
carrying the same caveat.

The impact is bounded. The sealed prediction lock holds the fitted predictions themselves, so
every downstream statistic re-derives exactly whatever numpy is installed. Only a from-scratch
refit of the A12 ridge models could in principle be sensitive to a numpy build difference — and
that refit is not part of reproducing this run, it would be a new one.

Searched and genuinely absent: any `requirements.lock`, `environment.yml`, `conda list
--explicit` export, or dated `pip freeze` covering numpy/Pillow — in the repository across all
refs, the ops directories, `exp3-incoming`, the P0/P1 transfer bundles, and S3.

## 4. Corrected RGB

```
CORRECTED_RGB_OUTPUTS=NONE_FOUND
```

Searched: `/home/sagemaker-user`, `/opt/ml`, `/tmp`, `/mnt/sagemaker-nvme` to depth 8 for
`*corrected*`, `*rgb_fix*`, `*bgr_fix*`, `*channel_fix*`, `*color_fix*`, `*rgb_rerun*`,
`*reextract*`, `*reprocess*`; `git log --all` across every local and remote ref grepped for RGB,
BGR and channel; the complete `mineocclude/experiment_iii/` S3 prefix. Every git hit belongs to
the Experiment-I / Regime-A 66-cell Person A/C/E lineage, not Experiment III.

No corrected-RGB output exists, and **none was created by this recovery** — the task is forensic,
and generating one would be a new experiment. No `corrected_rgb/` directory was invented.

The executed BGR ordering is not a latent defect: authority v1.8 disclosed it
(`mineworld_historical_preprocessing_channel_order: "BGR"`), forbade changing it
(`rgb_bgr_historical_behavior_change_allowed: false`), listed
`FIX_THE_HISTORICAL_RGB_BGR_PREPROCESSING_BEHAVIOR` among `states[9].forbidden_repairs`, and
carries a passing audit check named *"RVE disclosure names the BGR history."* Full forensics,
including the empirical replay, are in `legacy_bgr/`.

## 5. A naming hazard worth recording

Three distinct hashes in this run are all called some variant of "spec hash", and two of them
collide across corpora in a way that looks alarming and is not:

- `spec_sha256` = `867ce44a…` for `e3_t01__L0` — the **capture-schedule** spec, in the production
  ledger and `capture_completion.json`, distinct per capture unit.
- `spec_hash` / `source_capture_hash` = `c7123193…` for `e3_t01` — the **trajectory** spec, in
  `server_state.jsonl` and A9's extraction inventories. There are **25** of these, one per
  identity, shared across that identity's five conditions. That is the paired design, not a bug.
- The shadow-pipeline test fixture at `exp3-shadow-pipeline/` reuses that same trajectory spec
  hash `c7123193…` while carrying the literal string `"shadow"` as its source closure and only 19
  frames per unit. It is a synthetic harness fixture and is excluded everywhere.

## 6. What this operation changed

Additive only:

- Two **new** S3 prefixes, `a9_production_activations_p2_f0e9d954_lock_2a25bcb0/` (876 objects,
  19,617,105,515 B) and `a11_feature_blocks_p2_f0e9d954_lock_2a25bcb0/` (750 objects,
  2,878,368,000 B). Both were empty before; no predecessor key was read-modified or overwritten.
  Before this, both arrays existed in exactly one place — the working disk — which was a real
  durability single point of failure for a closed experiment.
- One new GitHub branch and its release.

Unchanged: every receipt, ledger, result, capture and superseded cohort. The scientific
conclusion of Experiment III-A is untouched, and no model inference was run.
