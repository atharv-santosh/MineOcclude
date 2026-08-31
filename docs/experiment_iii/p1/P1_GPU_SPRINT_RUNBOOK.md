# Experiment III — P1 GPU Extraction Sprint Runbook

**Stage on arrival:** `A9 — ACTIVATION_EXTRACTION`
**Controlling authority:** `v1.7` (Amendment 4)
**Preceding stage:** `A5` P1 local capture — **complete**, ten units banked and durable
**This sprint does NOT complete P1.** Full P1 requires these 190 forwards and 60 arrays.

---

## 0. What already happened

The local capture host ran the complete P1 pilot: 2 pilot identities × 5 frozen conditions =
10 capture units, 180 frames each, 19 target rows each. Every unit passed the authority 3.3
physical receipts and was published with a read-back-verified durable receipt. No production
identity was touched. No GPU, no CUDA, no MineWorld — this program has still never run a model
forward under Experiment III.

The handoff package carries everything needed to start work immediately. **Do not reconstruct
pilot provenance by hand**; every binding is in `P1_GPU_HANDOFF_MANIFEST.json`.

---

## 1. Sequence

```
start SageMaker
  -> GPU-host A3 (environment preflight, extraction role)
  -> verify MineWorld checkpoint + VAE + preprocessing identity
  -> transfer and verify the P1 handoff bundle
  -> load MineWorld 700M_16f
  -> run 190 forwards (one per target row)
  -> persist 60 arrays
  -> validate arrays and inventory
  -> complete P1 engineering qualification
  -> P1 PASS
  -> A6 / P2
```

Each step below fails closed. A step that cannot prove its precondition stops the sprint; it
does not proceed on an assumption.

---

## 2. GPU-host A3

`GPU_HOST_A3_STATUS` is currently `NOT_RUN` and **must not be marked otherwise from the capture
host**. The capture host holds no weights and ran no CUDA; it is not in a position to certify a
GPU environment, and a fabricated GPU receipt is the exact failure mode authority A3 exists to
prevent.

```bash
python scripts/experiment_iii/preflight.py --host-role EXTRACTION_HOST
```

Require `passed: true` and the receipt naming `A9` among its authorized stages. A capture-only
receipt never authorizes A9.

---

## 3. Verify the model before loading it

From the manifest's `extraction_contract`:

| Item | Frozen value |
|---|---|
| Model | `MineWorld_700M_16f_FROZEN` |
| Main checkpoint SHA-256 | `a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5` |
| VAE SHA-256 | `370d06be427e034476b6b95ba0080a4b48266e876c4776a757b944b87b87d9ab` |
| Preprocessing | unchanged historical bytes, hash-bound; `preprocessing_change_allowed = false` |
| Source frame | opened as **RGB**, through the already-bound preprocessing path |

Experiment III does **not** "fix" or reinterpret the historical RGB/BGR channel-order behaviour.
All conditions use identical code. If a checkpoint hash disagrees, stop — that is not a
configuration problem, it is a different model.

---

## 4. Transfer and verify the bundle

```bash
python scripts/experiment_iii/build_p1_gpu_handoff.py --verify p1_gpu_handoff.tar.gz
```

This reads the manifest **out of the archive** and re-hashes every file the manifest names. It
must print `P1_TRANSFER_RECONSTRUCTION_VALIDATION=PASS` before anything is loaded. A path that
resolves only on the capture host fails here, which is the point.

---

## 5. The forward contract — read this before writing extraction code

**One forward per target row. 190 forwards, and no more.**

```
context      = 16 complete visual/action pairs for model frames [t-15, ..., t]
per pair     = 336 visual tokens then 11 action tokens = 347 tokens
sequence     = 16 x 347 = 5,552 tokens
hooked shape = [1, 5552, 2048] at every decoder layer
```

Both temporal slices and all three layers come from **the same forward**:

| Slice | Pair ordinal | Python slice | Shape per layer |
|---|---:|---:|---|
| `PREVIOUS` | 14 | `[4858:5194]` | `[1, 336, 2048]` |
| `CURRENT`  | 15 | `[5205:5541]` | `[1, 336, 2048]` |

Pair-14 action tokens (`5194–5204`) and pair-15 action tokens (`5541–5551`) are **excluded**.

Decoder causality means the pair-14 residual cannot attend to pair 15 even though both are
harvested from the same teacher-forced call. **No extra forward is authorized** for `PREVIOUS`
or for additional layers. Any excess is `EXTRACTION_FORWARD_COUNT_EXCESS`.

The hook manager may transiently register and validate all 20 decoder layers, but only
`{4, 10, 19}` are serialized.

---

## 6. Frame identity is mandatory — shape agreement is not evidence

A tensor of the correct shape drawn from the wrong frame is **not acceptable**. Per forward,
assert all of:

1. `spans[-1].pair_index == 15` and `spans[-2].pair_index == 14`
2. `spans[-1].visual_positions == tuple(range(5205, 5541))`
3. `spans[-2].visual_positions == tuple(range(4858, 5194))`
4. `spans[-1].identity.model_frame_idx == t` and `spans[-2].identity.model_frame_idx == t - 1`
   — the **frame identity**, not merely the ordinal
5. the full `FrameTokenMap` covers `range(5552)` exactly, no duplicate or missing position
6. selected visual positions are disjoint from every action position

Failures map to `TOKEN_SPAN_MISMATCH`, `TOKEN_FRAME_IDENTITY_MISMATCH`,
`TOKEN_ACTION_CONTAMINATION`, `TOKEN_SEQUENCE_LENGTH_MISMATCH`.

The metadata that makes this checkable travels in the bundle: each unit's
`capture_completion.json` carries `target_model_frame_indices`, `context_ages` and
`last_preocclusion_model_frame_idx`; `raw/frame_map.jsonl` binds every frame to its
`(episode_id, server_tick, render_frame_idx)` and its SHA-256.

---

## 7. What you owe back

```
10 captures x 3 layers x 2 slices = 60 persisted .npy arrays

shape  [19, 336, 2048]
dtype  float16, little-endian ("<f2")
bytes  26,148,992 per array   (19 x 336 x 2048 x 2 + 128-byte NumPy header)
total  1,568,939,520 bytes    (1.4612 GiB)
```

Path contract: `activations/<capture_unit_id>/layer_<NN>/<SLICE>.npy`, inventory at
`activations/activation_inventory.json`.

Each artifact must bind: identity; condition; layer; temporal slice; the 19 target rows **in
order**; hook site; token-position hash; preprocessing identity; checkpoint identity; shape;
dtype; byte size; SHA-256.

Each artifact must validate: all values finite; array non-empty; shape exactly `[19,336,2048]`;
dtype exactly little-endian float16; byte size exactly 26,148,992; layer in `{4,10,19}`; slice in
`{PREVIOUS, CURRENT}`; source capture hash matches the kept capture; checkpoint and preprocessing
identities match; target index order matches the manifest exactly.

```bash
python scripts/experiment_iii/validate_extraction.py
```

---

## 8. Resume

Unit of work is one `(capture unit × layer × slice)` array — 6 per capture.

```
PLANNED -> RUNNING -> EXTRACTED -> VALIDATED -> DURABLE -> COMPLETE
```

Same-spec resume only: `source_capture_hash`, `extraction_spec_hash` and `authority_sha256` must
all match, or the partial is discarded rather than adopted. Completed arrays are never
recomputed. Full procedure in `RECOVERY_AND_RESUME_RUNBOOK.md`.

**Do not reload the model per unit.** Reloading between units is the most expensive mistake
available here and buys nothing; the model is frozen for the whole stage.

---

## 9. After the arrays validate

P1 is complete only when the capture half *and* the extraction half both pass, and the pilot
analysis smoke run produces finite numbers. Then, and only then:

- `p1_pilot_receipt.json` = PASS, enumerating every 6A verification item with its observed value
- `I22_STATUS` = COMPLETE
- proceed to `A6` — P2 prospective freeze

**`PRODUCTION_AUTHORIZED` may be emitted at exactly one place in this program: the A6/P2 freeze
exit.** It is not a P0 output and not a P1 output. The A4 ladder verdict is named
`P0_LADDER_ACCEPTED` precisely so the two can never be confused; `run_production_capture.py
--execute` refuses with `P2_PREREQUISITE_NOT_PASSED` until P2 has genuinely passed.

---

## 10. Do not

- Do not tune anything on pilot results. Authority 6A forbids P1 from tuning materials, RVE
  rules, the cohort, the primary readout, the alpha grid, representations, estimands, thresholds,
  analysis families, target rows or folds. Pilot predictive accuracy may be inspected **only** to
  confirm the analysis code runs end to end and produces finite numbers.
- Do not promote a pilot identity into production.
- Do not touch `e3_t01`…`e3_t25` in this sprint.
- Do not re-run P0 or recompute the ladder. P0 is banked scientific evidence and is an immutable
  upstream input.
- Do not modify the authority.
