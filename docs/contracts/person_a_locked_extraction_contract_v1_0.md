# Person A Locked Extraction Contract v1.0

Status: `LOCKED_FOR_MVP` (Step 6.8 closeout)

Supersedes: the Phase 6 pilot-phase working assumptions.

This contract records the schema, throughput, storage, and context-timing
assumptions that Person C's MVP collection and Person B/D/E's MVP consumption
may rely on. It is engineering identity, not a scientific result.

## 1. Model and runtime identity

| Item | Locked value |
|---|---|
| Model | MineWorld 700M, `LlamaLVM` / `LlamaForCausalLM` |
| MineWorld source revision | `9f49efbcc68a5f0cf60e78f0abc566eac409282f` |
| ModelScope asset revision | `0dd5561ab317115831badc50e09a6ebe98693d0e` |
| Main checkpoint SHA-256 | `a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5` |
| VAE checkpoint SHA-256 | `370d06be427e034476b6b95ba0080a4b48266e876c4776a757b944b87b87d9ab` |
| Model config SHA-256 | `e13b3a80fb370547a05852809c2c8f02d05ebe2fce3b3bb2fd1ee54eee78c018` |
| VAE config SHA-256 | `32ca759d5b90f0c5aa5df0e312a81e03dd4d3af68896863c88f910d19f2526cb` |
| Decoder layers hooked | 20 (`transformer.model.layers.{i}`) |
| Conceptual hook site | `decoder_layer_output_residual_stream` |
| Teacher-forced precision | `float16` |
| Reference GPU | NVIDIA L4, 23,661,248,512 bytes |
| Deterministic seed | `20260725` |

## 2. Locked token and context geometry

| Item | Locked value |
|---|---|
| Visual tokens per frame | 336 |
| Action tokens per frame | 11 |
| Tokens per frame/action pair | 347 |
| Maximum model frames per context | 16 |
| Context pairs observed per window | 16, with a short final window |
| Frame rollover rule | global frame 15 maps to local 15; global 16 restarts at local 0 |

## 3. Locked activation schema

| Item | Locked value |
|---|---|
| Store format | `person-a-activation-store-v2` |
| Pooling | mean over exactly the 336 explicit visual positions |
| Pooling identity | `person-a-visual-token-mean-v1.0` |
| Stored dtype | 16-bit float |
| Vector width | 2048 |
| Rows per trajectory | `model_frames x 20` |
| Chunks per trajectory | 20 (one per decoder layer) |
| Scientific key | `(trajectory_id, model_frame_idx, layer_idx, hook_site)` |
| Analysis arithmetic | promoted only inside Person B's pipeline, never in storage |

## 4. Measured throughput and storage

Measured on the ten-pilot expansion `person-a-phase6-ten-pilot-expansion-seed-20260725`
(nine newly extracted pilots plus one checksum-valid reuse).

| Item | Measured value |
|---|---|
| Accepted pilots | 10 |
| Model frames | 1,874 |
| Activation rows | 37,480 |
| Activation chunks | 200 |
| Activation bytes | 307,061,760 |
| Bytes per activation row | 8,192.68 (2048 x float16 plus amortized chunk headers) |
| Bytes per model frame | 163,853.66 |
| Measured wall seconds (steps 6.1-6.5, nine pilots) | 1,834.08 |
| Measured frames in that window | 1,626 |
| Seconds per model frame | 1.128 |
| Mean seconds per trajectory | 203.79 |

Forecast values derived from these rates are projections, not runs, and are
published as such by `mineocclude.experiments.pilot_certification.forecast_queue`.

## 5. Admission and exclusion ownership

Person A extracts every model frame it can align and excludes none on
scientific grounds. Frame admission for analysis is Person B's frozen rule.

For the ten-pilot expansion: 1,874 source frames, 1,695 admitted, 179 excluded
by Person B. Person A's extraction exclusion count is 0.

## 6. Immutability rules carried into the MVP

- An accepted activation artifact is never overwritten; a corrected run gets a
  new run identity and supersedes the old one by reference.
- A filename is never scientific identity; the `(run_id, artifact_id, sha256)`
  triple is.
- Failed and superseded runs are retained, not deleted.
- Result-changing changes require a dated decision record and a new run identity.

## 7. Change classification vocabulary (Step 6.8)

`defect_correction`, `interface_migration`, `operational_improvement`,
`scientific_change`. Only `scientific_change` is result-changing and it requires
mentor/PI approval.

## 8. Frozen scientific decisions carried forward

The Step 4.1 scientific decision remains **FAIL** and is not rerun, relabelled,
or replaced by any Phase 6-9 work.
