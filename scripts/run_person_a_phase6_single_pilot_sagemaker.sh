#!/usr/bin/env bash
set -euo pipefail

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

if [[ -n "${PERSON_A_CANONICAL_SAGEMAKER_BUNDLE_MANIFEST:-}" ]]; then
  : "${PERSON_A_CANONICAL_SAGEMAKER_BUNDLE_MANIFEST_SHA256:?PERSON_A_CANONICAL_SAGEMAKER_BUNDLE_MANIFEST_SHA256 is required}"
  : "${PERSON_A_CANONICAL_C6A_PACKAGE_SHA256:?PERSON_A_CANONICAL_C6A_PACKAGE_SHA256 is required}"
  : "${PERSON_A_CANONICAL_EPISODE_MANIFEST_SHA256:?PERSON_A_CANONICAL_EPISODE_MANIFEST_SHA256 is required}"
  : "${PERSON_A_CANONICAL_PERSON_E_HANDOFF_SHA256:?PERSON_A_CANONICAL_PERSON_E_HANDOFF_SHA256 is required}"
  python_executable="/home/sagemaker-user/.conda/envs/mineworld/bin/python"
  ffmpeg="/home/sagemaker-user/tools/ffmpeg/bin/ffmpeg"
  ffprobe="/home/sagemaker-user/tools/ffmpeg/bin/ffprobe"
  session_id="person-a-canonical-c6a-layout-01-ep12602-seed-20260725"
  retrieved_relative="docs/status/phase6_runtime/${session_id}"
  retrieved_root="${repo_root}/${retrieved_relative}"
  activation_root="${PERSON_A_PHASE6_APPROVED_OUTPUT_ROOT%/}/${session_id}-activation-store-v2"
  input_session_root="${PERSON_A_PHASE6_APPROVED_INPUT_ROOT%/}/${session_id}"
  output_session_root="${PERSON_A_PHASE6_APPROVED_OUTPUT_ROOT%/}/${session_id}"

  "${python_executable}" "${repo_root}/scripts/run_person_a_phase6_single_pilot_sagemaker.py" run \
    --repository-root "${repo_root}" \
    --mineworld-root "${MINEWORLD_ROOT}" \
    --asset-root "${MODELSCOPE_ASSET_ROOT}" \
    --main-checkpoint "${MINEWORLD_MAIN_CHECKPOINT}" \
    --vae-config "${MINEWORLD_VAE_CONFIG}" \
    --vae-checkpoint "${MINEWORLD_VAE_CHECKPOINT}" \
    --approved-input-root "${PERSON_A_PHASE6_APPROVED_INPUT_ROOT}" \
    --approved-output-root "${PERSON_A_PHASE6_APPROVED_OUTPUT_ROOT}" \
    --runtime-host aws_sagemaker_linux_gpu \
    --canonical-input-bundle-manifest \
      "${PERSON_A_CANONICAL_SAGEMAKER_BUNDLE_MANIFEST}" \
    --canonical-input-bundle-manifest-sha256 \
      "${PERSON_A_CANONICAL_SAGEMAKER_BUNDLE_MANIFEST_SHA256}" \
    --canonical-c6a-package-sha256 \
      "${PERSON_A_CANONICAL_C6A_PACKAGE_SHA256}" \
    --episode-artifact-manifest-sha256 \
      "${PERSON_A_CANONICAL_EPISODE_MANIFEST_SHA256}" \
    --person-e-provenance-handoff-sha256 \
      "${PERSON_A_CANONICAL_PERSON_E_HANDOFF_SHA256}" \
    --trajectory-id layout_01_ep12602 \
    --episode-id 12602 \
    --expected-model-config-sha256 \
      e13b3a80fb370547a05852809c2c8f02d05ebe2fce3b3bb2fd1ee54eee78c018 \
    --expected-main-checkpoint-sha256 \
      a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5 \
    --expected-vae-config-sha256 \
      32ca759d5b90f0c5aa5df0e312a81e03dd4d3af68896863c88f910d19f2526cb \
    --expected-vae-checkpoint-sha256 \
      370d06be427e034476b6b95ba0080a4b48266e876c4776a757b944b87b87d9ab \
    --expected-preprocessing-identity \
      mineworld_gradio_step_video_preprocessing@1.0:036fa0b4899285e5499f88581f6e02426a25f732fcc26bd63c0f5b3863a9d9ab \
    --expected-action-conversion-identity \
      mineworld_mcdataset_json_action_to_env_action@1.0:7e8d16db01f085481d41d340e5a0b84669b8e163f3338d5fd572731532c52746 \
    --expected-hook-site decoder_layer_output_residual_stream \
    --expected-pooling-method mean \
    --expected-token-region visual \
    --expected-activation-store-format person-a-activation-store-v2 \
    --expected-activation-index-format person-a-activation-index-v2 \
    --ffmpeg "${ffmpeg}" \
    --ffprobe "${ffprobe}" \
    --session-id "${session_id}" \
    --seed 20260725 \
    --device cuda:0 \
    --precision float16

  "${python_executable}" \
    "${repo_root}/scripts/prepare_person_a_phase6_canonical_sagemaker.py" \
    collect-output \
    --input-session-root "${input_session_root}" \
    --output-session-root "${output_session_root}" \
    --activation-store-root "${activation_root}" \
    --destination "${retrieved_root}"
  git add -- "${retrieved_relative}"
  git diff --cached --check
  git commit -m "Record canonical Person A SageMaker pilot output"
  git push origin role/person-a-model
  exit 0
fi

: "${PERSON_B_ACTIVATION_STORE_V2_RATIFICATION_OBJECT:?PERSON_B_ACTIVATION_STORE_V2_RATIFICATION_OBJECT is required}"
session_id="person-a-phase6-layout-00-ep9403-seed-20260725"
log_root="${PERSON_A_PHASE6_APPROVED_OUTPUT_ROOT%/}/wrapper-logs"
mkdir -p "${log_root}"
log_path="${log_root}/${session_id}.log"
if [[ -e "${log_path}" ]]; then
  echo "immutable wrapper log already exists: ${log_path}" >&2
  exit 98
fi

set +e
python "${repo_root}/scripts/run_person_a_phase6_single_pilot_sagemaker.py" run \
  --repository-root "${repo_root}" \
  --mineworld-root "${MINEWORLD_ROOT}" \
  --asset-root "${MODELSCOPE_ASSET_ROOT}" \
  --main-checkpoint "${MINEWORLD_MAIN_CHECKPOINT}" \
  --vae-config "${MINEWORLD_VAE_CONFIG}" \
  --vae-checkpoint "${MINEWORLD_VAE_CHECKPOINT}" \
  --approved-input-root "${PERSON_A_PHASE6_APPROVED_INPUT_ROOT}" \
  --approved-output-root "${PERSON_A_PHASE6_APPROVED_OUTPUT_ROOT}" \
  --activation-store-v2-ratification-object \
    "${PERSON_B_ACTIVATION_STORE_V2_RATIFICATION_OBJECT}" \
  --session-id "${session_id}" \
  --seed 20260725 \
  --device cuda:0 \
  --precision float16 \
  2>&1 | tee "${log_path}"
runner_status=${PIPESTATUS[0]}
set -e

exit "${runner_status}"
