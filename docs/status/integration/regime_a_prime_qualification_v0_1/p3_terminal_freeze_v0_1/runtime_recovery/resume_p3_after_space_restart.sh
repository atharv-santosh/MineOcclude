#!/usr/bin/env bash
set -u

cd /home/sagemaker-user/MineOcclude

PROGRESS="/home/sagemaker-user/MineOcclude/docs/status/integration/regime_a_prime_qualification_v0_1/p3_progress.json"
LOG="/mnt/sagemaker-nvme/p3_sequential_development_v0_1/logs/p3_controller.log"
PIDFILE="/home/sagemaker-user/p3_restart_checkpoint/resumed_pid"

echo "Checking for an already-running P3 controller..."

EXISTING="$(pgrep -f 'p3_run_sequential.py' | head -1 || true)"

if [ -n "$EXISTING" ]; then
    echo "P3_CONTROLLER_ALREADY_RUNNING=true"
    echo "PID=$EXISTING"
    exit 0
fi

echo
echo "Current durable P3 state:"
python3 - <<'INNER'
import json
from pathlib import Path

p = Path(
    "/home/sagemaker-user/MineOcclude/docs/status/integration/"
    "regime_a_prime_qualification_v0_1/p3_progress.json"
)

d = json.loads(p.read_text())

for k in (
    "p3_status",
    "current_candidate",
    "current_candidate_speed",
    "current_stage",
    "current_run_id",
    "candidate_capture_complete",
    "candidate_capture_expected",
    "candidate_extraction_complete",
    "qualification_status",
    "selected_candidate",
    "last_error_code",
    "heartbeat_utc",
):
    if k in d:
        print(f"{k:32}: {d[k]}")
INNER

echo
echo "Resuming P3 controller from durable state..."

nohup /home/sagemaker-user/.conda/envs/mineworld/bin/python scripts/regime_a_prime_qualification_v0_1/p3_run_sequential.py >> "$LOG" 2>&1 &

NEWPID=$!
echo "$NEWPID" > "$PIDFILE"

sleep 3

if kill -0 "$NEWPID" 2>/dev/null; then
    echo
    echo "P3_RESUME_STATUS=RUNNING"
    echo "P3_CONTROLLER_PID=$NEWPID"
    echo "P3_CONTROLLER_LOG=$LOG"
else
    echo
    echo "P3_RESUME_STATUS=FAILED"
    echo "Recent controller log:"
    tail -50 "$LOG"
fi
