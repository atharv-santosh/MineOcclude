#!/usr/bin/env bash
# A5 / I22 — launch the P1 pilot capture detached on the qualified WSL2 host.
#
# The pilot must survive the operator disconnecting: authority 6A's ten units are
# a long-running stage, and a capture killed halfway leaves a partial unit that
# the resume contract then has to reason about. tmux keeps the driver attached to
# a session rather than to a terminal, so closing VS Code, dropping the network
# or ending the Claude session does not stop it.
#
# Everything scientific is decided by the runner from frozen evidence. This
# script only chooses where the process lives and where its logs land.
set -euo pipefail

REPO=/mnt/c/Users/lollo/MineOcclude-Exp3
RUNTIME=/home/overatedusername/mineocclude-exp3-runtime
SESSION="${P1_SESSION:-exp3-p1-capture-v17}"
LOGS="$RUNTIME/p1_ops"
CONFIG="$REPO/docs/experiment_iii/runtime/capture_runtime_wsl2_linux_p1.json"
LADDER="$REPO/docs/experiment_iii/p0/P0_SELECTED_LADDER.json"

mkdir -p "$LOGS"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
STDOUT="$LOGS/p1_capture_${STAMP}.out"
STDERR="$LOGS/p1_capture_${STAMP}.err"

if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "P1_SESSION_ALREADY_RUNNING=$SESSION" >&2
    exit 1
fi

# The display must exist before the client starts. CaptureRuntime starts Xvfb
# itself when the strategy is XVFB, so nothing is started here.
#
# wsl_env.sh is not a convenience. run_p1_pilot.py computes the source closure,
# which shells out to git, and this checkout is a worktree whose .git file names
# a Windows gitdir that git inside WSL cannot follow. Without GIT_DIR and
# GIT_WORK_TREE the pilot dies on SOURCE_CLOSURE_DRIFT before capturing anything.
tmux new-session -d -s "$SESSION" -c "$REPO" \
    "source $REPO/scripts/experiment_iii/wsl_env.sh && \
     exec python -u scripts/experiment_iii/run_p1_pilot.py \
        --execute \
        --runtime-config '$CONFIG' \
        --ladder '$LADDER' \
        > '$STDOUT' 2> '$STDERR'"

sleep 2
SUPERVISOR="$(tmux list-panes -t "$SESSION" -F '#{pane_pid}' | head -1)"
DRIVER="$(pgrep -P "$SUPERVISOR" -f run_p1_pilot.py || echo "$SUPERVISOR")"
PGID="$(ps -o pgid= -p "$SUPERVISOR" | tr -d ' ')"

cat <<EOF
P1_CAPTURE_SESSION=$SESSION
P1_SUPERVISOR_PID=$SUPERVISOR
P1_DRIVER_PID=$DRIVER
P1_PROCESS_GROUP=$PGID
P1_STDOUT_LOG=$STDOUT
P1_STDERR_LOG=$STDERR
P1_LIVE_STATUS=$REPO/docs/experiment_iii/status/A5_status.json
P1_STATE_PATH=$REPO/data/experiment_iii/p1/p1_capture_ledger.jsonl
P1_CAPTURE_ROOT=$REPO/data/experiment_iii/p1/captures
P1_CAPTURE_START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF
