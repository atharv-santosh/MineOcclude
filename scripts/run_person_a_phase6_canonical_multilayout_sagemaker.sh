#!/usr/bin/env bash
set -euo pipefail

: "${PERSON_A_MULTILAYOUT_PREPARATION_COMMIT:?PERSON_A_MULTILAYOUT_PREPARATION_COMMIT is required}"
: "${MINEWORLD_ROOT:?MINEWORLD_ROOT is required}"
: "${MODELSCOPE_ASSET_ROOT:?MODELSCOPE_ASSET_ROOT is required}"
: "${MINEWORLD_MAIN_CHECKPOINT:?MINEWORLD_MAIN_CHECKPOINT is required}"
: "${MINEWORLD_VAE_CONFIG:?MINEWORLD_VAE_CONFIG is required}"
: "${MINEWORLD_VAE_CHECKPOINT:?MINEWORLD_VAE_CHECKPOINT is required}"
: "${PERSON_A_PHASE6_APPROVED_INPUT_ROOT:?PERSON_A_PHASE6_APPROVED_INPUT_ROOT is required}"
: "${PERSON_A_PHASE6_APPROVED_OUTPUT_ROOT:?PERSON_A_PHASE6_APPROVED_OUTPUT_ROOT is required}"

export PYTHONHASHSEED=20260725
export CUBLAS_WORKSPACE_CONFIG=:4096:8
export CUDA_VISIBLE_DEVICES=0

repo_root="$(git rev-parse --show-toplevel)"
python_executable="/home/sagemaker-user/.conda/envs/mineworld/bin/python"
ffmpeg="/home/sagemaker-user/tools/ffmpeg/bin/ffmpeg"
ffprobe="/home/sagemaker-user/tools/ffmpeg/bin/ffprobe"
bundle_manifest="${repo_root}/data/handoff_a/person_a_canonical_c6a_multilayout_sagemaker_input_v0_1/bundle_manifest.json"
selection_record="${repo_root}/docs/status/person_a_canonical_c6a_multilayout_preparation_v0_1/selection_record.json"
existing_output="${repo_root}/docs/status/phase6_runtime/person-a-canonical-c6a-layout-01-ep12602-seed-20260725-retry-20260804T193204Z-package-retry-20260804T193627Z"
runtime_output_root="${repo_root}/docs/status/phase6_runtime"

[[ "$(git branch --show-current)" == "role/person-a-model" ]]
[[ "$(git rev-parse HEAD)" == "${PERSON_A_MULTILAYOUT_PREPARATION_COMMIT}" ]]
[[ -z "$(git status --porcelain=v1 -uall)" ]]

gpu_name="$(nvidia-smi --query-gpu=name --format=csv,noheader -i 0)"
[[ "${gpu_name}" == *"L4"* ]]
"${ffmpeg}" -version >/dev/null
"${ffprobe}" -version >/dev/null

"${python_executable}" \
  "${repo_root}/scripts/prepare_person_a_phase6_canonical_multilayout.py" \
  verify-input \
  --bundle-manifest "${bundle_manifest}" \
  --bundle-manifest-sha256 \
    ff7801c1a331f173bc5fc197454889b72d8554a8e31b5a88731de8eb7d9ed987

"${python_executable}" \
  "${repo_root}/scripts/prepare_person_a_phase6_canonical_multilayout.py" \
  run-missing \
  --repository-root "${repo_root}" \
  --preparation-commit "${PERSON_A_MULTILAYOUT_PREPARATION_COMMIT}" \
  --bundle-manifest "${bundle_manifest}" \
  --bundle-manifest-sha256 \
    ff7801c1a331f173bc5fc197454889b72d8554a8e31b5a88731de8eb7d9ed987 \
  --selection-record "${selection_record}" \
  --existing-output "${existing_output}" \
  --runtime-output-root "${runtime_output_root}" \
  --mineworld-root "${MINEWORLD_ROOT}" \
  --asset-root "${MODELSCOPE_ASSET_ROOT}" \
  --main-checkpoint "${MINEWORLD_MAIN_CHECKPOINT}" \
  --vae-config "${MINEWORLD_VAE_CONFIG}" \
  --vae-checkpoint "${MINEWORLD_VAE_CHECKPOINT}" \
  --approved-input-root "${PERSON_A_PHASE6_APPROVED_INPUT_ROOT}" \
  --approved-output-root "${PERSON_A_PHASE6_APPROVED_OUTPUT_ROOT}" \
  --ffmpeg "${ffmpeg}" \
  --ffprobe "${ffprobe}"

"${python_executable}" -m pytest -q \
  tests/models/test_person_a_canonical_c6a_multilayout_v0_1.py \
  tests/models/test_person_a_canonical_c6a_sagemaker_prep_v0_1.py \
  tests/models/test_person_a_canonical_c6a_launcher_v0_1.py \
  tests/activations/test_phase6_activation_store_v2.py \
  tests/activations/test_pool.py

git add -- docs/status/phase6_runtime
git diff --cached --check
git commit -m "Record canonical Person A multi-layout successor"
git push origin role/person-a-model
git status --short
