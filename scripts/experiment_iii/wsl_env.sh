#!/usr/bin/env bash
# Shared WSL environment for Experiment III commands run against this checkout.
#
# This repository is a git WORKTREE whose .git file records a Windows gitdir
# (C:/Users/lollo/MineOcclude/.git/worktrees/MineOcclude-Exp3). git inside WSL
# cannot follow that path, so every source-closure computation fails with
# SOURCE_CLOSURE_DRIFT unless GIT_DIR and GIT_WORK_TREE are set to the /mnt/c
# equivalents. Source this before any Experiment III entrypoint on the WSL host.
export GIT_DIR=/mnt/c/Users/lollo/MineOcclude/.git/worktrees/MineOcclude-Exp3
export GIT_WORK_TREE=/mnt/c/Users/lollo/MineOcclude-Exp3
export MINEOCCLUDE_RUNTIME=/home/overatedusername/mineocclude-exp3-runtime
# shellcheck disable=SC1091
source "$MINEOCCLUDE_RUNTIME/venv/bin/activate"
cd /mnt/c/Users/lollo/MineOcclude-Exp3
