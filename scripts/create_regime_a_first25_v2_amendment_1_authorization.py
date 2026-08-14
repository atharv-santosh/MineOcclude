#!/usr/bin/env python3
"""Create the external post-commit authorization for v2 amendment 1."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from mineocclude.regime_a import sha256_file  # noqa: E402
from scripts.run_regime_a_first25_v2_amendment_1 import (  # noqa: E402
    AMENDMENT,
    BRANCH,
    RUN_ID,
    SCOPE,
    STATUS,
    authorization_bindings,
)

OPERATOR = "Kazim Abbas"
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"REGIME_A_AMENDMENT_1_AUTHORIZATION_REFUSAL: {message}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--final-commit-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--operator", default=OPERATOR)
    args = parser.parse_args()
    require(GIT_SHA.fullmatch(args.final_commit_sha) is not None, "invalid final commit SHA")
    require(args.operator == OPERATOR, "operator identity mismatch")
    require(git("branch", "--show-current") == BRANCH, "branch mismatch")
    require(git("rev-parse", "HEAD") == args.final_commit_sha, "HEAD is not final commit")
    require(not git("status", "--porcelain"), "worktree is not clean")
    require(
        git("rev-parse", f"origin/{BRANCH}") == args.final_commit_sha,
        "final commit is not pushed to origin",
    )
    require(not args.output.exists(), "authorization output already exists")
    manifest = AMENDMENT / "trajectory_manifest_v2_1_amendment_1.jsonl"
    replay = json.loads((AMENDMENT / "scientific_structural_replay_t01_t04.json").read_text())
    require(replay.get("pass") is True, "scientific structural replay did not pass")
    bindings = authorization_bindings(sha256_file(manifest))
    document = {
        "schema_version": "regime-a-a4-v2-amendment-1-operator-authorization-v1.0",
        "status": "AUTHORIZED_A4_SCIENTIFIC_EXECUTION",
        "operator": args.operator,
        "scientific_run_id": RUN_ID,
        "study_manifest_sha256": sha256_file(STATUS / "regime_a_study_manifest.json"),
        **bindings,
        "protocol_modification": False,
        "scientific_authority_amendment": True,
        "outcome_blind": True,
        "t04_used_in_numerical_authority": False,
        "scientific_outcomes_computed": 0,
        "authorization_scope": SCOPE,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(payload)
        stream.flush()
    print(
        json.dumps(
            {
                "status": "CREATED",
                "path": str(args.output),
                "sha256": hashlib.sha256(payload.encode()).hexdigest(),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
