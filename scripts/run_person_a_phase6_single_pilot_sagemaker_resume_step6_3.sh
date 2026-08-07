#!/usr/bin/env bash
set -euo pipefail

: "${MINEWORLD_ROOT:?MINEWORLD_ROOT is required}"
: "${MODELSCOPE_ASSET_ROOT:?MODELSCOPE_ASSET_ROOT is required}"
: "${MINEWORLD_MAIN_CHECKPOINT:?MINEWORLD_MAIN_CHECKPOINT is required}"
: "${MINEWORLD_VAE_CONFIG:?MINEWORLD_VAE_CONFIG is required}"
: "${MINEWORLD_VAE_CHECKPOINT:?MINEWORLD_VAE_CHECKPOINT is required}"
: "${PERSON_A_PHASE6_APPROVED_INPUT_ROOT:?PERSON_A_PHASE6_APPROVED_INPUT_ROOT is required}"
: "${PERSON_A_PHASE6_APPROVED_OUTPUT_ROOT:?PERSON_A_PHASE6_APPROVED_OUTPUT_ROOT is required}"
: "${PERSON_B_PHASE6_STEP6_3_RESUME_RATIFICATION_OBJECT:?new Person B resume ratification is required}"

expected_input_root="/home/sagemaker-user/person-a-phase6-approved-inputs"
expected_output_root="/home/sagemaker-user/person-a-phase6-approved-outputs"
if [[ "${PERSON_A_PHASE6_APPROVED_INPUT_ROOT%/}" != "${expected_input_root}" ]]; then
  echo "approved input root differs from the frozen SageMaker path" >&2
  exit 96
fi
if [[ "${PERSON_A_PHASE6_APPROVED_OUTPUT_ROOT%/}" != "${expected_output_root}" ]]; then
  echo "approved output root differs from the frozen SageMaker path" >&2
  exit 97
fi

export PYTHONHASHSEED=20260725
export CUBLAS_WORKSPACE_CONFIG=:4096:8
export CUDA_VISIBLE_DEVICES=0

repo_root="$(git rev-parse --show-toplevel)"
runner="${repo_root}/scripts/run_person_a_phase6_single_pilot_sagemaker_resume_step6_3.py"
session_id="$(python "${runner}" continuation-id --repository-root "${repo_root}")"
log_root="${PERSON_A_PHASE6_APPROVED_OUTPUT_ROOT%/}/wrapper-logs"
mkdir -p "${log_root}"
log_path="${log_root}/${session_id}.log"
if [[ -e "${log_path}" ]]; then
  echo "immutable continuation wrapper log already exists: ${log_path}" >&2
  exit 98
fi

set +e
python "${runner}" resume \
  --repository-root "${repo_root}" \
  --mineworld-root "${MINEWORLD_ROOT}" \
  --asset-root "${MODELSCOPE_ASSET_ROOT}" \
  --main-checkpoint "${MINEWORLD_MAIN_CHECKPOINT}" \
  --vae-config "${MINEWORLD_VAE_CONFIG}" \
  --vae-checkpoint "${MINEWORLD_VAE_CHECKPOINT}" \
  --approved-input-root "${PERSON_A_PHASE6_APPROVED_INPUT_ROOT}" \
  --approved-output-root "${PERSON_A_PHASE6_APPROVED_OUTPUT_ROOT}" \
  --prior-input-root "${expected_input_root}/person-a-phase6-layout-00-ep9403-seed-20260725" \
  --prior-output-root "${expected_output_root}/person-a-phase6-layout-00-ep9403-seed-20260725" \
  --resume-ratification-object \
    "${PERSON_B_PHASE6_STEP6_3_RESUME_RATIFICATION_OBJECT}" \
  --activation-store-v2-ratification-object \
    "${PERSON_B_PHASE6_STEP6_3_RESUME_RATIFICATION_OBJECT}" \
  --seed 20260725 \
  --device cuda:0 \
  --precision float16 \
  2>&1 | tee "${log_path}"
runner_status=${PIPESTATUS[0]}
set -e

exit "${runner_status}"
