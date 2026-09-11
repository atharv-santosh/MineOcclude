#!/usr/bin/env bash
# A7 production capture launcher (ops orchestration only; calls the committed entrypoint).
set -u
REPO=/home/sagemaker-user/MineOcclude-Exp3
OPS=/home/sagemaker-user/exp3-terminal-ops
export GIT_DISCOVERY_ACROSS_FILESYSTEM=1
exec /opt/conda/bin/python3.12 -u "$REPO/scripts/experiment_iii/run_production_capture.py" \
  --execute \
  --p2 "$REPO/docs/experiment_iii/p2/P2_FREEZE_PACKAGE.json" \
  --capture-host-receipt "$REPO/docs/experiment_iii/receipts/environment_receipt_sagemaker_capture_host.json" \
  --ladder "$REPO/docs/experiment_iii/p0/P0_SELECTED_LADDER.json" \
  --runtime-config "$OPS/capture_runtime_config.json"
