#!/usr/bin/env bash
# A5 / I22 -- the authority-required deliberate mid-run kill and restart.
#
# Authority 6A: "a deliberate mid-run kill and restart resumes on the same spec,
# skips completed verified units, and recomputes nothing that was already
# DURABLE."
#
# The demonstration runs into its OWN capture root and its OWN ledger, so the ten
# accepted P1 units are never at risk. Sprint section 20 is explicit that the
# demonstration should exercise the state machine, not destroy valid pilot
# evidence, and authority 6A permits unlimited retries on pilot identities -- so
# recapturing e3_p90/e3_p91 here costs nothing and touches no production
# identity.
set -euo pipefail

REPO=/mnt/c/Users/lollo/MineOcclude-Exp3
RUNTIME=/home/overatedusername/mineocclude-exp3-runtime
SESSION="${DEMO_SESSION:-exp3-p1-resume-demo}"
DEMO="$REPO/data/experiment_iii/p1/resume_demo"
LOGS="$RUNTIME/p1_ops"
CONFIG="$REPO/docs/experiment_iii/runtime/capture_runtime_wsl2_linux_p1.json"
LADDER="$REPO/docs/experiment_iii/p0/P0_SELECTED_LADDER.json"

PHASE="${1:?usage: run_p1_resume_demo.sh <first|second>}"
mkdir -p "$LOGS" "$DEMO/captures"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$LOGS/resume_${PHASE}_${STAMP}.out"
ERR="$LOGS/resume_${PHASE}_${STAMP}.err"

if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "DEMO_SESSION_ALREADY_RUNNING=$SESSION" >&2
    exit 1
fi

tmux new-session -d -s "$SESSION" -c "$REPO" \
    "source $REPO/scripts/experiment_iii/wsl_env.sh && \
     exec python -u scripts/experiment_iii/run_p1_pilot.py \
        --execute \
        --runtime-config '$CONFIG' \
        --ladder '$LADDER' \
        --captures '$DEMO/captures' \
        > '$OUT' 2> '$ERR'"

sleep 2
PID="$(tmux list-panes -t "$SESSION" -F '#{pane_pid}' | head -1)"
echo "DEMO_PHASE=$PHASE"
echo "DEMO_SESSION=$SESSION"
echo "DEMO_PID=$PID"
echo "DEMO_STDOUT=$OUT"
echo "DEMO_STDERR=$ERR"
echo "DEMO_LEDGER=$DEMO/p1_capture_ledger.jsonl"
echo "DEMO_STARTED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
