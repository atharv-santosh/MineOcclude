# Person A Phase 2.10 Runtime Record

## 1. Record identity

| Field | Evidenced value |
|---|---|
| Role and roadmap step | Person A, Phase 2.10 |
| Formal session | `person-a-phase2-aws-20260725-055616` |
| MineOcclude revision | `35baf673312af5c21ae3f22168de405bd4ee8bd9` |
| MineWorld source revision | `9f49efbcc68a5f0cf60e78f0abc566eac409282f` |
| ModelScope asset revision | `0dd5561ab317115831badc50e09a6ebe98693d0e` |
| Imported evidence | `docs/status/phase2_runtime/person-a-phase2-aws-20260725-055616` |
| Session result | `PASS`; completed steps `2.6,2.7,2.8,2.9` |
| Evidence validation | `PASS` with `mineocclude.models.phase2_evidence` |
| Shared schema version | `1.0` |
| Runtime evidence schema | `mineocclude-phase2-runtime-evidence-v1.0` |

The session identifier contains `20260725-055616`. The imported reports do not
contain separate authoritative UTC `started_at` and `ended_at` fields, so this
record does not infer them from the identifier or filesystem metadata.

## 2. Executive verdict

**Person A Phase 2 runtime gate: PASS.**

The exact pinned 700M MineWorld model loaded and generated an output, its
loaded architecture matched the required configuration, a teacher-forced
forward captured every expected decoder layer, two identical forwards agreed
within the required tolerance, and runtime capacity was measured on the
actual GPU. This is an engineering/runtime gate. It is not evidence for a
scientific claim about hidden-object belief.

The Phase 2.10 human-readable runtime record is complete. The imported bundle
does not contain a Person E immutable-registry snapshot or the exact UTC run
timestamps required to create one. No registry entry is fabricated here; that
specific publication item remains **NOT EVIDENCED**.

## 3. Environment and compute

The environment report records an AWS SageMaker Linux environment with these
values:

| Item | Evidenced value |
|---|---|
| OS | `Linux-6.12.90-120.164.amzn2023.x86_64-x86_64-with-glibc2.39` |
| Machine | `x86_64` |
| Python | CPython `3.10.20` |
| Python executable | `/home/sagemaker-user/.conda/envs/mineworld/bin/python` |
| Python compiler | `GCC 14.3.0` |
| Runtime libc | `glibc 2.39` |
| Conda environment | `mineworld` |
| PyTorch | `2.6.0+cu126` |
| CUDA runtime reported by PyTorch | `12.6` |
| cuDNN | `90501` |
| GPU | `NVIDIA L4`, compute capability `8.9`, device `0` |
| GPU memory | `23,661,248,512` bytes from PyTorch; `23,034 MiB` from the NVIDIA driver report |
| NVIDIA driver | `595.71.05` |
| Teacher-forced precision | `float16` |
| System compiler commands | GCC/G++ `13.3.0`; `cl` not found |
| Standalone CUDA compiler | `nvcc` not found |

The environment check passed all required imports and `pip check` reported no
broken requirements. The absence of `nvcc` did not prevent the installed
CUDA-enabled PyTorch runtime from loading or executing the model.

## 4. Pinned provenance

| Identity | SHA-256 |
|---|---|
| Main checkpoint | `a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5` |
| VAE checkpoint | `370d06be427e034476b6b95ba0080a4b48266e876c4776a757b944b87b87d9ab` |
| Model configuration | `e13b3a80fb370547a05852809c2c8f02d05ebe2fce3b3bb2fd1ee54eee78c018` |
| VAE configuration | `32ca759d5b90f0c5aa5df0e312a81e03dd4d3af68896863c88f910d19f2526cb` |
| Environment report | `cf17cd5ff1a64889ed00f5bf16f856b6fe67e3e7e7ce018c49c33be8b1844239` |
| Canonical input MP4 | `b546e7657505004223742e2174e01d0b6a19091de7ee39a2f213bcf003c243de` |
| Canonical input JSONL | `0029daf06496bb974305431a20e8c9d419791f362098bf9d57ee8b8e0f036f9b` |

The MineWorld source and ModelScope asset revisions are the exact revisions in
the identity table above. The session reports record
`mineocclude_dirty=false`.

## 5. Step 2.6 — official rollout

Step 2.6 is `completed` and the process exit status is `0`. The command used
seed `20260724` and an eight-frame context. It requested one generated frame.
`ffprobe` declared and decoded exactly one frame at `384x224`, `6/1` fps, and
`0.166667` seconds duration.

| Timing | Seconds |
|---|---:|
| Model initialization | `38.94861279599991` |
| First generated frame | `157.15375202699988` |
| Generation kernel | `155.25881671905518` |
| Total runtime | `201.60856802499984` |

Peak CUDA allocation was `6,207,769,600` bytes and peak CUDA reservation was
`9,330,229,248` bytes on the NVIDIA L4.

The generated artifacts were:

| Output | Bytes | SHA-256 |
|---|---:|---|
| Generated MP4 | `12,234` | `e8c876cf717142e4eca995b12044c822589f462554d6c101937a34bd7804aca5` |
| Paired generated metadata | `1,169,029` | `53fb9436345dc87febf955a2a0928c3d7caaa558f0886a57612ea5b2bfedac57` |
| Raw log | `2,301` | `a7077e7b87852ee3f7354f91e8a1c2ee1eaa9cd59c24edb3d837f61648e030e6` |

The manifest's sealed canonical digest is
`b02060565a3bae610dde9eff468ab48d8347b4007e80d4b52f38d768dd037978`.
The generated output bytes were verified before import; the imported record
retains their hashes and sizes while the large generated MP4 stays outside
Git.

The canonical input remained the unchanged ModelScope `640x360`, 20 fps,
4,152-frame MP4 plus its 4,152-row JSONL. The runtime-only adapters preserved
those identities while producing:

- deterministic action JSONL compatible with the pinned batch parser, with no
  rows dropped, added, or reordered; and
- in-memory BGR-to-RGB `cv2.INTER_LINEAR` frame preprocessing from
  `360x640x3` to `224x384x3` `uint8`.

For the eight-frame rollout, the VAE emitted 336 visual tokens per frame and
the action encoder emitted 11 action tokens. The prompt used
`8 * 336 + 11 = 2,699` positions; including 336 requested generated positions,
the conservative budget was `3,035 <= 5,552`, recorded as `PASS`.

This proves that the official pinned free-generation path can load and
produce a decodable generated frame. It does not assess visual quality,
scientific correctness, or belief tracking.

## 6. Step 2.7 — loaded architecture

Step 2.7 is `completed`. The loaded architecture was:

| Field | Evidenced value |
|---|---|
| Model class | `LlamaLVM` |
| Transformer class | `LlamaForCausalLM` |
| VAE class | `VAE` |
| Decoder layer path | `transformer.model.layers` |
| Decoder layers | `20` |
| Hidden size | `2048` |
| Intermediate size | `4096` |
| Attention heads | `32` |
| Key/value heads | `4` |
| Vocabulary size | `8262` |
| Maximum positions | `5552` |
| Context pairs | `16` |
| Visual tokens per pair | `336` |
| Action tokens per pair | `11` |
| Tokens per pair | `347` |

The model had `872,229,955` parameters: `725,985,280` transformer parameters
and `146,244,675` VAE parameters. All `872,229,955` parameters were recorded
as `torch.float16` on `cuda:0`. The report contains a 537-entry
`named_modules()` tree and identifies all 20 decoder modules at
`transformer.model.layers.0` through `.19`.

Architecture loading peaked at `3,729,780,736` allocated CUDA bytes and
`3,900,702,720` reserved CUDA bytes.

## 7. Audited checkpoint load

The provenance-bound checkpoint profile is
`mineworld-700m-16f-pinned-runtime-load-v1`, version `1.0`. Its classification
and final decision are both `PASS`.

- Transformer missing keys: `0`.
- VAE missing keys: `0`.
- Transformer unexpected keys: `1,201`.
- VAE unexpected keys: `1,250`.
- Unmatched keys: `0` for both components.
- Duplicate keys: `0` for both components.

The exact accepted auxiliary families were:

| Component | Family | Count |
|---|---|---:|
| Transformer | `tokenizer.metrics_fid.*` | `566` |
| Transformer | `tokenizer.metrics_is.*` | `566` |
| Transformer | `tokenizer.metrics_lpips.*` | `36` |
| Transformer | `tokenizer.perceptual_loss.*` | `33` |
| VAE | `loss.discriminator.*` | `16` |
| VAE | `loss.perceptual_loss.*` | `33` |
| VAE | `perceptual_loss.*` | `33` |
| VAE | `metrics_fid.*` | `566` |
| VAE | `metrics_is.*` | `566` |
| VAE | `metrics_lpips.*` | `36` |

The sorted transformer key-list SHA-256 is
`9e9eb93cd04b24f4ef8faa4c2cdd1e6bd2c89a4a4a6eddfb11eedbb92c0734bf`;
the VAE digest is
`fcf2149ca82175f608c0d85b9173841eb9df75b2f38cbc9c3eb666ac5d2c5c85`.

These keys belong to training-time discriminator/perceptual-loss and
evaluation-metric modules, not missing runtime model or tokenizer weights.
Acceptance is still fail-closed: the complete raw key lists remain in the
architecture and teacher-forced reports, and the profile requires exact
source/asset/checkpoint provenance, exact family and total counts, exact
sorted-list digests, no missing/unmatched/duplicate keys, and an exact final
decision. It is not a prefix-only or generic checkpoint allowlist.

## 8. Steps 2.8–2.9 — teacher-forced execution and compute

The teacher-forced report is `completed` for accepted input
`modelscope-mineworld-scene-0dd5561`. It uses canonical MP4/JSONL hashes from
the provenance table and source frame indices `0` through `15`.

Execution used batch size `1`, `model.eval()`, `torch.no_grad()`, `float16`,
and two repeats. The token sequence contains 16 state-action pairs. Each pair
has 336 visual positions followed by 11 action positions, for 347 positions
per pair and a total sequence length of `5,552`. The token-position digest is
`d1e7b1923307bb93de4bd772b8bc5001bfe2c21ad8dfab88d2d0043b0d559f27`.

All 20 decoder layers were hooked on both repeats, producing 40 hook records.
Each activation is `torch.float16` on `cuda:0` with shape
`[1, 5552, 2048]`: batch, token position, and hidden dimension. The captured
sites are `transformer.model.layers.0` through `.19`. Hooks were removed
successfully after execution.

| Timing or memory | Evidenced value |
|---|---:|
| Model load | `43.24235929300039` seconds |
| Forward repeat 1 | `0.5368471219999265` seconds |
| Forward repeat 2 | `0.5284761090001666` seconds |
| Peak CPU RSS | `9,182,183,424` bytes |
| Peak CUDA allocated | `4,778,999,808` bytes |
| Peak CUDA reserved | `7,165,968,384` bytes |

For every layer, corresponding repeat outputs were `allclose` with
`rtol=0.001` and `atol=0.001`. The maximum absolute difference was `0.0`, and
the per-layer output hashes and summary statistics matched across repeats.
The result is deterministic for these two eval-mode forwards in this recorded
environment.

**Compute classification: GREEN for the tested 700M target on the evidenced
NVIDIA L4 configuration.** The real model loaded, two forwards completed, and
the measured memory stayed within the available device capacity. This
classification is bounded to this model, precision, batch size, sequence
length, software stack, and hardware; it is not a universal timing or memory
guarantee.

## 9. Phase gate

| Requirement | Decision | Evidence |
|---|---|---|
| Exact source pinned | PASS | Source revision is identical in all three reports. |
| Exact assets pinned | PASS | Asset revision and checkpoint/input identities agree. |
| Hashes verified | PASS | Required configuration, checkpoint, environment, and input hashes are recorded and consistent. |
| Official generation works | PASS | Step 2.6 exited `0`; one frame was generated and decoded. |
| Architecture matches expected configuration | PASS | All required classes, dimensions, token counts, heads, layers, and position limit match. |
| Expected transformer layers exposed | PASS | Twenty decoder modules were discovered at the authoritative path. |
| Teacher-forced forward works | PASS | Two eval/no-grad forwards completed on the accepted input. |
| Hooks capture expected activations | PASS | 20/20 layers yielded `[1,5552,2048]` hook outputs for both repeats. |
| Repeats completed | PASS | Two repeats completed; every layer passed tolerance with maximum difference `0.0`. |
| Compute measured and classified | PASS | Load/forward time, CPU memory, CUDA memory, and a bounded GREEN classification are recorded. |
| Formal evidence validated | PASS | All three imported JSON reports pass the project validator. |
| Human-readable runtime record completed | PASS | This record consolidates the immutable evidence paths and conclusions. |
| Person E immutable-registry entry | NOT EVIDENCED | No registry snapshot or exact UTC run timestamps are present in the imported bundle; none is fabricated. |

## 10. Interpretation

Phase 2 establishes that:

- the pinned MineWorld model and VAE can load and run on the recorded AWS GPU
  environment;
- the loaded model is the expected 20-layer, 2,048-hidden-dimension
  architecture;
- the official free-generation path can produce a decodable output;
- the teacher-forced path works over the full 16-pair token sequence;
- temporary hooks can capture the needed hidden states at all decoder layers;
  and
- the measured runtime and memory requirements for this configuration are now
  explicit.

The validated runtime is therefore suitable as the dependency for the next
adapter implementation phase, subject to closing the explicit registry
publication item above.

## 11. Non-claims and limitations

Phase 2 does not establish that:

- a hidden-object belief exists;
- a decoded posterior mean is accurate;
- uncertainty is calibrated;
- activations causally control generation;
- any final scientific hypothesis is supported;
- one generated frame demonstrates output quality; or
- timings from one NVIDIA L4 configuration generalize to other hardware,
  precision, sequence lengths, or workloads.

Additional bounded observations from the raw reports:

- the environment emits Gym's maintenance warning;
- the runtime emits a Diffusers configuration deprecation warning;
- Step 2.6 reports insufficient SMs for `max_autotune_gemm` and notes that
  TensorFloat32 matmul was available but not enabled;
- the standalone `nvcc` compiler was not installed; and
- the export hash inventory is not a detached cryptographic signature. Its
  entries for the other imported files match their bytes; its self-entry is
  the empty-file SHA-256 produced while the inventory itself was being
  written.

These observations did not prevent the validated runtime paths from
completing, but they must not be hidden or generalized away.

## 12. Evidence index

All paths below are repository-relative:

- [Session metadata](phase2_runtime/person-a-phase2-aws-20260725-055616/session_metadata.txt)
- [Environment report](phase2_runtime/person-a-phase2-aws-20260725-055616/environment_report.txt)
- [Step 2.6 manifest](phase2_runtime/person-a-phase2-aws-20260725-055616/step2_6/run_manifest.json)
- [Step 2.6 raw log](phase2_runtime/person-a-phase2-aws-20260725-055616/step2_6/raw_stdout_stderr.log)
- [Step 2.6 launcher log](phase2_runtime/person-a-phase2-aws-20260725-055616/launchers/step2_6.log)
- [Step 2.7 architecture report](phase2_runtime/person-a-phase2-aws-20260725-055616/step2_7/architecture_report.json)
- [Step 2.7 raw log](phase2_runtime/person-a-phase2-aws-20260725-055616/step2_7/raw_stdout_stderr.log)
- [Step 2.7 launcher log](phase2_runtime/person-a-phase2-aws-20260725-055616/launchers/step2_7.log)
- [Steps 2.8–2.9 teacher-forced report](phase2_runtime/person-a-phase2-aws-20260725-055616/step2_8_2_9/teacher_forced_report.json)
- [Steps 2.8–2.9 raw log](phase2_runtime/person-a-phase2-aws-20260725-055616/step2_8_2_9/raw_stdout_stderr.log)
- [Steps 2.8–2.9 launcher log](phase2_runtime/person-a-phase2-aws-20260725-055616/launchers/step2_8_2_9.log)
- [Export hash inventory](phase2_runtime/person-a-phase2-aws-20260725-055616/export_file_hashes.sha256)
- [AWS execution checklist and historical attempts](person_a_phase2_aws_execution_checklist.md)
- [Pinned asset acquisition record](person_a_mineworld_asset_acquisition.md)
- [Pinned asset lock](../../configs/assets/mineworld_assets_v1.json)

The generated MP4, paired generated metadata, checkpoints, and the original
external runtime directory remain outside Git. Their exact external paths,
sizes, and hashes are retained in the Step 2.6 manifest.

## 13. Next authorized work

The immediate next roadmap phase is **Person A Phase 3 — Build the MineWorld
adapter**. Its first step is to freeze the smallest public adapter API for
model loading and identity, accepted input validation, frame preprocessing,
action conversion, tokenization, teacher-forced forward, and free rollout.
Phase 3 implementation is not started by this record.

Before treating Phase 2.10 publication as fully closed, the formal smoke run
still needs a truthful entry in Person E's existing immutable run/artifact
registry. The imported evidence does not provide the exact UTC run
`started_at`/`ended_at` values required by that contract, so a conforming entry
cannot be reconstructed without additional source evidence or role-owner
direction.
