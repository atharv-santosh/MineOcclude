#!/usr/bin/env bash
set -euo pipefail

: "${MINEWORLD_ROOT:?MINEWORLD_ROOT is required}"
: "${MODELSCOPE_ASSET_ROOT:?MODELSCOPE_ASSET_ROOT is required}"
: "${MINEWORLD_MAIN_CHECKPOINT:?MINEWORLD_MAIN_CHECKPOINT is required}"
: "${MINEWORLD_VAE_CONFIG:?MINEWORLD_VAE_CONFIG is required}"
: "${MINEWORLD_VAE_CHECKPOINT:?MINEWORLD_VAE_CHECKPOINT is required}"
: "${PERSON_A_PHASE6_APPROVED_INPUT_ROOT:?PERSON_A_PHASE6_APPROVED_INPUT_ROOT is required}"
: "${PERSON_A_PHASE6_APPROVED_OUTPUT_ROOT:?PERSON_A_PHASE6_APPROVED_OUTPUT_ROOT is required}"
: "${PERSON_A_PHASE6_EXISTING_ARTIFACT_ROOT:?PERSON_A_PHASE6_EXISTING_ARTIFACT_ROOT is required}"
: "${PERSON_B_PHASE6_EXPANSION_AUTHORIZATION_OBJECT:?PERSON_B_PHASE6_EXPANSION_AUTHORIZATION_OBJECT is required}"

export PYTHONHASHSEED=20260725
export CUBLAS_WORKSPACE_CONFIG=:4096:8
export CUDA_VISIBLE_DEVICES=0

repo_root="$(git rev-parse --show-toplevel)"
session_id="person-a-phase6-ten-pilot-expansion-seed-20260725"
log_root="${PERSON_A_PHASE6_APPROVED_OUTPUT_ROOT%/}/wrapper-logs"
mkdir -p "${log_root}"
log_path="${log_root}/${session_id}.log"
if [[ -e "${log_path}" ]]; then
  echo "immutable wrapper log already exists: ${log_path}" >&2
  exit 98
fi

set +e
python "${repo_root}/scripts/run_person_a_phase6_ten_pilot_sagemaker.py" run \
  --repository-root "${repo_root}" \
  --mineworld-root "${MINEWORLD_ROOT}" \
  --asset-root "${MODELSCOPE_ASSET_ROOT}" \
  --main-checkpoint "${MINEWORLD_MAIN_CHECKPOINT}" \
  --vae-config "${MINEWORLD_VAE_CONFIG}" \
  --vae-checkpoint "${MINEWORLD_VAE_CHECKPOINT}" \
  --approved-input-root "${PERSON_A_PHASE6_APPROVED_INPUT_ROOT}" \
  --approved-output-root "${PERSON_A_PHASE6_APPROVED_OUTPUT_ROOT}" \
  --existing-artifact-root "${PERSON_A_PHASE6_EXISTING_ARTIFACT_ROOT}" \
  --person-b-expansion-authorization-object \
    "${PERSON_B_PHASE6_EXPANSION_AUTHORIZATION_OBJECT}" \
  --session-id "${session_id}" \
  --seed 20260725 \
  --device cuda:0 \
  --precision float16 \
  2>&1 | tee "${log_path}"
runner_status=${PIPESTATUS[0]}
set -e

exit "${runner_status}"
