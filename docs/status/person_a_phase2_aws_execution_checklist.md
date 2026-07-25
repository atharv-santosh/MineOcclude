# Person A Phase 2.6-2.9 AWS Execution Checklist

Status: **Step 2.6 completed and independently byte-verified in immutable AWS
session `person-a-phase2-aws-20260725-035027`; Steps 2.7-2.9 remain pending**.

This checklist runs the project-owned evidence commands in their required
order. It does not replace the pinned-source, asset-lock, or environment
records. Checkpoints, generated video, and complete runtime directories remain
outside Git.

## Fixed identities

```bash
set -euo pipefail
export MINEOCCLUDE=/home/sagemaker-user/MineOcclude
export MINEWORLD=/home/sagemaker-user/MineWorld-Upstream
export ASSETS=/home/sagemaker-user/MineWorld-Assets-Pinned
export SOURCE_REV=9f49efbcc68a5f0cf60e78f0abc566eac409282f
export ASSET_REV=0dd5561ab317115831badc50e09a6ebe98693d0e
export MODEL_CONFIG="$MINEWORLD/configs/700M_16f.yaml"
export MAIN_CKPT="$ASSETS/checkpoints/700M_16f.ckpt"
export VAE_CONFIG="$ASSETS/checkpoints/vae/config.json"
export VAE_CKPT="$ASSETS/checkpoints/vae/vae.ckpt"
export INPUT_MP4="$ASSETS/gradio_scene/scene.mp4"
export INPUT_JSONL="$ASSETS/gradio_scene/scene.jsonl"
export SESSION_ID=person-a-phase2-aws-YYYYMMDD-HHMMSS
export EVIDENCE_ROOT="/home/sagemaker-user/mineocclude-phase2-evidence/$SESSION_ID"
mkdir -p "$EVIDENCE_ROOT"
```

Replace `SESSION_ID` with one immutable session identity before running any
command. Do not reuse an existing evidence directory.

## 1. Activate `mineworld`

```bash
conda activate mineworld
cd "$MINEOCCLUDE"
export PYTHONPATH="$MINEOCCLUDE/src"
python --version
```

The MineOcclude checkout must be committed and clean. Each runtime command
refuses a dirty MineOcclude checkout.

## 2. Verify pinned source, assets, and environment

```bash
test "$(git -C "$MINEWORLD" rev-parse HEAD)" = "$SOURCE_REV"
test -z "$(git -C "$MINEWORLD" status --porcelain)"
test -z "$(git -C "$MINEOCCLUDE" status --porcelain)"

test "$(stat -c %s "$MAIN_CKPT")" = 3798736924
test "$(sha256sum "$MAIN_CKPT" | cut -d' ' -f1)" = a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5
test "$(stat -c %s "$VAE_CONFIG")" = 805
test "$(sha256sum "$VAE_CONFIG" | cut -d' ' -f1)" = 32ca759d5b90f0c5aa5df0e312a81e03dd4d3af68896863c88f910d19f2526cb
test "$(stat -c %s "$VAE_CKPT")" = 1657555486
test "$(sha256sum "$VAE_CKPT" | cut -d' ' -f1)" = 370d06be427e034476b6b95ba0080a4b48266e876c4776a757b944b87b87d9ab
test "$(stat -c %s "$INPUT_MP4")" = 124782221
test "$(sha256sum "$INPUT_MP4" | cut -d' ' -f1)" = b546e7657505004223742e2174e01d0b6a19091de7ee39a2f213bcf003c243de
test "$(stat -c %s "$INPUT_JSONL")" = 15326380
test "$(sha256sum "$INPUT_JSONL" | cut -d' ' -f1)" = 0029daf06496bb974305431a20e8c9d419791f362098bf9d57ee8b8e0f036f9b

python scripts/check_env.py --require-cuda \
  > "$EVIDENCE_ROOT/environment_report.txt" 2>&1
test "$?" = 0

export MODEL_CONFIG_SHA="$(sha256sum "$MODEL_CONFIG" | cut -d' ' -f1)"
export MAIN_CKPT_SHA="$(sha256sum "$MAIN_CKPT" | cut -d' ' -f1)"
export VAE_CONFIG_SHA="$(sha256sum "$VAE_CONFIG" | cut -d' ' -f1)"
export VAE_CKPT_SHA="$(sha256sum "$VAE_CKPT" | cut -d' ' -f1)"
export INPUT_MP4_SHA="$(sha256sum "$INPUT_MP4" | cut -d' ' -f1)"
export INPUT_JSONL_SHA="$(sha256sum "$INPUT_JSONL" | cut -d' ' -f1)"
export ENVIRONMENT_SHA="$(sha256sum "$EVIDENCE_ROOT/environment_report.txt" | cut -d' ' -f1)"
```

Any failed `test`, hash, environment check, or missing file stops the session.
Do not continue using a manually inferred identity.

## 3. Run the formal Step 2.6 rollout

### Required action compatibility boundary

The first formal attempt,
`person-a-phase2-aws-20260724-194620`, is immutable failed evidence at:

```text
/home/sagemaker-user/mineocclude-phase2-evidence/person-a-phase2-aws-20260724-194620
```

That attempt exited with status 1 after the pinned batch path tried to read the
accepted raw VPT-style JSON action rows with its restricted Python `eval`
expression. It produced `raw_stdout_stderr.log` and a copied `scene.jsonl`, but
no `run_manifest.json` and no generated MP4. It is not successful Step 2.6
evidence. Do not delete, overwrite, rename, reuse, or reseal that directory.

The accepted ModelScope `scene.jsonl` is valid JSON. The pinned Gradio path
reads it with `json.loads`, then calls
`MCDataset.json_action_to_env_action`, then calls
`get_action_index_from_actiondict`. The pinned batch path omitted the first two
operations and instead applied:

```python
eval(line.strip(), {"__builtins__": None}, safe_globals)
```

MineWorld-Upstream remains untouched. The MineOcclude Step 2.6 command now
creates a compatibility input by:

1. parsing every nonempty canonical row only with strict `json.loads`;
2. validating the raw `keyboard.keys`, `mouse.dx`, `mouse.dy`, and
   `mouse.buttons` fields consumed by the pinned converter;
3. calling the pinned `MCDataset.json_action_to_env_action` implementation;
4. requiring the complete action-key set from pinned `NOOP_ACTION`, a
   two-value finite numeric camera, and integer `0`/`1` binary fields; and
5. emitting one deterministic flat action object per source row.

Absent action events are normalized only through pinned `NOOP_ACTION` to the
integer no-op value `0`. Missing source structures, unknown keyboard/button
values, malformed JSON, blank rows, strings or nested values in action-bearing
fields, non-finite camera values, or an incomplete normalized action fail the
command.

The serialization is a UTF-8 JSON/Python-literal subset with sorted keys,
compact separators, finite numbers, integer binary values, and one
LF-terminated object per row. Each emitted row is immediately checked with the
exact pinned restricted-eval expression. Conversion runs twice and must
produce byte-identical output. Row count and order are preserved; no row is
dropped or added.

The original `$INPUT_JSONL` remains the canonical accepted input and is never
replaced. Its locked size and SHA-256 are checked before conversion and again
after generation. The runtime-only derived file is:

```text
$EVIDENCE_ROOT/step2_6/inference_input/scene.jsonl
```

It stays outside Git. The input MP4 is exposed beside it by a runtime symlink;
the canonical MP4 identity is unchanged. The project-owned generation boundary
copies the derived compatibility input byte-for-byte to
`$EVIDENCE_ROOT/step2_6/scene.jsonl`; that file is recorded separately as
generated paired metadata.

The sealed manifest distinguishes:

- `original`: canonical path, asset revision, pre/post size and SHA-256, row
  count, row-sequence hash, and unchanged confirmation;
- `derived`: runtime-only path, size and SHA-256, row count, transformation
  name/version, deterministic serialization rule, parent hashes, and explicit
  zero-dropped/zero-added/order-preserved assertions; and
- `generated`: paired-metadata path, size and SHA-256, and explicit links to
  the generated MP4 plus both original and derived JSONL identities.

Any missing or inconsistent identity, relationship, hash, size, row count, or
transformation fact prevents manifest acceptance.

### Required frame-preprocessing compatibility boundary

The second formal attempt,
`person-a-phase2-aws-20260725-025635`, is also immutable failed evidence at:

```text
/home/sagemaker-user/mineocclude-phase2-evidence/person-a-phase2-aws-20260725-025635
```

Its action compatibility conversion succeeded: the restricted-eval error did
not recur, the deterministic derived `scene.jsonl` was 1,169,029 bytes, and
model/VAE loading reached generation. The attempt then failed during compiled
transformer prefill with a device-side position-index assertion. It contains
`environment_report.txt`, the canonical and derived action JSONLs,
`raw_stdout_stderr.log`, and `step2_6_launcher.log`, but no
`run_manifest.json`. It is not successful Step 2.6 evidence. Do not delete,
overwrite, rename, reuse, or reseal it.

The cause is a second pinned batch/Gradio mismatch. The canonical ModelScope
video is 640x360. `mineworld.py:step_video`, the successful pinned Gradio path,
decodes each selected frame in order, converts BGR to RGB, clips/casts to
`uint8`, resizes to 384x224 with `cv2.INTER_LINEAR`, divides CHW float data by
255, applies channel mean/std 0.5, and only then calls the pinned VAE tokenizer.
The pinned batch `inference.py:lvm_generate` omitted the resize and tokenized
the 640x360 frames directly.

MineWorld-Upstream remains untouched. The MineOcclude command now uses a
narrow in-memory generation wrapper: it retains the pinned video decoder,
action encoder, VAE tokenizer, transformer `naive_generate`, and video decoder,
but inserts exactly the Gradio preprocessing before tokenization. It does not
write or re-encode a derived MP4 and does not monkeypatch global state.
Processed frames exist only in memory outside Git.

Before transformer prefill, the wrapper requires:

- exactly the requested eight decoded source indices, in order, with no
  dropped, added, or duplicated frames;
- source frames shaped `360x640x3` and typed `uint8`;
- processed frames shaped `224x384x3` and typed `uint8`;
- tokenizer output shaped `8x14x24`, exactly 336 visual tokens per frame;
- flattened visual tokens shaped `1x8x336`;
- one action shaped `1x1x11`; and
- loaded `max_position_embeddings` exactly 5,552.

For the formal eight-frame context, the prompt has:

```text
8 * 336 visual positions + 11 action positions = 2699 prompt positions
2699 + 336 requested generated positions = 3035 conservative positions
3035 <= 5552
```

Any shape, count, loaded-config, or budget mismatch fails before
`naive_generate`, so an invalid position request cannot reach a CUDA prefill
kernel.

The sealed manifest keeps three identities separate:

- `video_preprocessing.original` binds the unchanged canonical MP4 bytes,
  640x360 media facts, 20 fps, 4,152 declared/decoded frames, asset revision,
  and pre/post size and SHA-256;
- `video_preprocessing.derived` binds the transformation name/version, matched
  pinned source function, selected source indices, shapes, BGR-to-RGB rule,
  `cv2.INTER_LINEAR`, `uint8` boundary, normalization rule, per-frame hashes,
  aggregate processed-byte hash, and cardinality/order assertions; and
- `video_preprocessing.tokenization` binds the tokenizer identity, VAE hashes,
  exact visual/action shapes and hashes, prompt/generation counts, 5,552
  position limit, and explicit budget PASS.

These are distinct from generated MP4 and generated paired-metadata artifacts.
The original video is canonical; processed frame bytes are runtime-only
derived evidence; token IDs are tokenizer output; generated bytes remain
outputs.

### Successful Step 2.6 evidence

The corrected formal rollout completed under:

```text
person-a-phase2-aws-20260725-035027
/home/sagemaker-user/mineocclude-phase2-evidence/person-a-phase2-aws-20260725-035027/step2_6
```

It exited zero, generated and decoded exactly one frame, produced a sealed
`run_manifest.json`, and passed independent output-byte verification. This is
successful immutable Step 2.6 evidence. Preserve it as successful evidence;
do not overwrite, rename, reuse, or represent it as failed.

Because the CUDA initialization correction below changes the MineOcclude code
revision, the cleanest next formal bundle must use a **new** `SESSION_ID` and
**new** `EVIDENCE_ROOT`, then rerun Steps 2.6 through 2.9 under one committed
revision. This does not invalidate the successful Step 2.6 session above; it
avoids mixing code revisions in a new combined evidence bundle. Never point a
new command at either earlier failed session or the successful session root.

```bash
python scripts/run_phase2_rollout.py \
  --mineworld-source-root "$MINEWORLD" \
  --model-config "$MODEL_CONFIG" \
  --main-checkpoint "$MAIN_CKPT" \
  --vae-config "$VAE_CONFIG" \
  --vae-checkpoint "$VAE_CKPT" \
  --input-mp4 "$INPUT_MP4" \
  --input-jsonl "$INPUT_JSONL" \
  --environment-report "$EVIDENCE_ROOT/environment_report.txt" \
  --output-dir "$EVIDENCE_ROOT/step2_6" \
  --run-id "$SESSION_ID-step2.6" \
  --seed 20260724 \
  --source-revision "$SOURCE_REV" \
  --asset-revision "$ASSET_REV" \
  --model-config-sha256 "$MODEL_CONFIG_SHA" \
  --main-checkpoint-sha256 "$MAIN_CKPT_SHA" \
  --vae-config-sha256 "$VAE_CONFIG_SHA" \
  --vae-checkpoint-sha256 "$VAE_CKPT_SHA" \
  --environment-report-sha256 "$ENVIRONMENT_SHA" \
  --confirm-aws-gpu-execution
```

This command requests exactly one generated frame. A UI observation is not
accepted as evidence: the command must write and validate the MP4, paired
metadata, raw log, compatibility provenance, and sealed JSON manifest.
The existing Step 2.6 evidence has passed these checks. Its rerun in the next
bundle is required only to keep Steps 2.6-2.9 under one clean code revision.

## 4. Run the Step 2.7 loaded-architecture inspection

The Step 2.7 attempt at:

```text
/home/sagemaker-user/mineocclude-phase2-evidence/person-a-phase2-aws-20260725-035027/step2_7
```

is immutable failed evidence containing only its raw failure log. It failed
before model/checkpoint loading because `reset_peak_memory_stats(0)` ran while
CUDA was still uninitialized and raised `RuntimeError: Invalid device
argument`. Do not delete, overwrite, rename, reuse, or represent that directory
as successful.

The bounded SageMaker diagnostic confirmed CUDA initialization ordering as the
cause. Every project-owned Phase 2.6-2.9 execution path now applies this exact
order before memory-stat reset or model loading:

1. require `torch.cuda.is_available() is True`;
2. require `torch.cuda.device_count() >= 1`;
3. call `torch.cuda.init()`;
4. call `torch.cuda.set_device(0)`;
5. require `torch.cuda.current_device() == 0`;
6. query device 0 name and properties;
7. clear the CUDA cache; and
8. call `torch.cuda.reset_peak_memory_stats(0)`.

Initialization, device selection/query, and reset failures propagate and stop
the command. CUDA memory measurement remains required. Step 2.7 remains
pending until it succeeds in a new immutable session and produces a validated
architecture report.

```bash
python scripts/inspect_phase2_architecture.py \
  --mineworld-source-root "$MINEWORLD" \
  --model-config "$MODEL_CONFIG" \
  --main-checkpoint "$MAIN_CKPT" \
  --vae-config "$VAE_CONFIG" \
  --vae-checkpoint "$VAE_CKPT" \
  --environment-report "$EVIDENCE_ROOT/environment_report.txt" \
  --output-dir "$EVIDENCE_ROOT/step2_7" \
  --run-id "$SESSION_ID-step2.7" \
  --seed 20260724 \
  --source-revision "$SOURCE_REV" \
  --asset-revision "$ASSET_REV" \
  --model-config-sha256 "$MODEL_CONFIG_SHA" \
  --main-checkpoint-sha256 "$MAIN_CKPT_SHA" \
  --vae-config-sha256 "$VAE_CONFIG_SHA" \
  --vae-checkpoint-sha256 "$VAE_CKPT_SHA" \
  --environment-report-sha256 "$ENVIRONMENT_SHA" \
  --confirm-aws-gpu-execution
```

Do not suppress missing or unexpected state-dictionary keys. Any architecture
or load-state mismatch must remain a nonzero result and must be reviewed before
Step 2.8.

## 5. Run the Step 2.8-2.9 teacher-forced repeat test

```bash
python scripts/run_phase2_teacher_forced.py \
  --mineworld-source-root "$MINEWORLD" \
  --model-config "$MODEL_CONFIG" \
  --main-checkpoint "$MAIN_CKPT" \
  --vae-config "$VAE_CONFIG" \
  --vae-checkpoint "$VAE_CKPT" \
  --environment-report "$EVIDENCE_ROOT/environment_report.txt" \
  --output-dir "$EVIDENCE_ROOT/step2_8_2_9" \
  --run-id "$SESSION_ID-step2.8-2.9" \
  --seed 20260724 \
  --source-revision "$SOURCE_REV" \
  --asset-revision "$ASSET_REV" \
  --model-config-sha256 "$MODEL_CONFIG_SHA" \
  --main-checkpoint-sha256 "$MAIN_CKPT_SHA" \
  --vae-config-sha256 "$VAE_CONFIG_SHA" \
  --vae-checkpoint-sha256 "$VAE_CKPT_SHA" \
  --environment-report-sha256 "$ENVIRONMENT_SHA" \
  --input-id modelscope-mineworld-scene-0dd5561 \
  --input-kind accepted \
  --input-mp4 "$INPUT_MP4" \
  --input-jsonl "$INPUT_JSONL" \
  --input-mp4-sha256 "$INPUT_MP4_SHA" \
  --input-jsonl-sha256 "$INPUT_JSONL_SHA" \
  --repeats 2 \
  --precision float16 \
  --confirm-aws-gpu-execution
```

The command uses frames/actions 0 through 15, batch size one, `eval()`,
`no_grad()`, all 20 discovered decoder layers, and the frozen 5,552-position
layout. It must fail if hooks are incomplete, duplicated, or not removed.

## 6. Copy small evidence into MineOcclude

First validate the evidence while all external outputs remain available:

```bash
python -m mineocclude.models.phase2_evidence --verify-output-bytes \
  "$EVIDENCE_ROOT/step2_6/run_manifest.json"
python -m mineocclude.models.phase2_evidence \
  "$EVIDENCE_ROOT/step2_7/architecture_report.json" \
  "$EVIDENCE_ROOT/step2_8_2_9/teacher_forced_report.json"
```

Then copy only JSON reports and raw text logs into a new evidence directory.
Do not copy generated MP4 files or checkpoints into Git.

```bash
export EVIDENCE_DST="$MINEOCCLUDE/docs/status/phase2_runtime/$SESSION_ID"
mkdir -p "$EVIDENCE_DST"
cp "$EVIDENCE_ROOT/environment_report.txt" "$EVIDENCE_DST/"
cp "$EVIDENCE_ROOT/step2_6/run_manifest.json" "$EVIDENCE_DST/step2_6_run_manifest.json"
cp "$EVIDENCE_ROOT/step2_6/raw_stdout_stderr.log" "$EVIDENCE_DST/step2_6_raw.log"
cp "$EVIDENCE_ROOT/step2_7/architecture_report.json" "$EVIDENCE_DST/step2_7_architecture_report.json"
cp "$EVIDENCE_ROOT/step2_7/raw_stdout_stderr.log" "$EVIDENCE_DST/step2_7_raw.log"
cp "$EVIDENCE_ROOT/step2_8_2_9/teacher_forced_report.json" "$EVIDENCE_DST/step2_8_2_9_report.json"
cp "$EVIDENCE_ROOT/step2_8_2_9/raw_stdout_stderr.log" "$EVIDENCE_DST/step2_8_2_9_raw.log"
```

The external evidence root is the durable location for the generated video and
paired metadata referenced by the Step 2.6 manifest. It must remain immutable.

## 7. Validate copied evidence and repository tests

```bash
python -m mineocclude.models.phase2_evidence \
  "$EVIDENCE_DST/step2_6_run_manifest.json" \
  "$EVIDENCE_DST/step2_7_architecture_report.json" \
  "$EVIDENCE_DST/step2_8_2_9_report.json"
python -m pytest tests/models/test_phase2_evidence.py -q
git diff --check
git status --short
```

The copied Step 2.6 manifest receives a self-integrity check here. Its durable
output bytes were already re-hashed in Step 6 and remain outside Git.

## 8. Commit and push evidence

Review the diff and confirm that it contains only small reports, raw text logs,
and truthful status updates. Never add checkpoints, generated MP4s, secrets, or
temporary public URLs.

```bash
git add docs/status/phase2_runtime
git diff --cached --check
git commit -m "Record Person A Phase 2.6-2.9 AWS evidence"
git push
```

Only change a roadmap status after the corresponding sealed report passes and
the raw evidence has been reviewed.

## 9. Stop SageMaker

After push confirmation, stop the SageMaker space/application or instance from
the AWS console and verify that billing resources are no longer running.
