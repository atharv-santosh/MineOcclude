# Person A Phase 2.6-2.9 AWS Execution Checklist

Status: **tooling prepared locally; AWS execution and all runtime pass claims
remain pending**.

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
metadata, raw log, and sealed JSON manifest.

## 4. Run the Step 2.7 loaded-architecture inspection

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
