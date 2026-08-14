#!/usr/bin/env python3
"""Create the post-commit Regime-A A4 launch authorization.

This must be run only after the reviewed pre-A4 commit is pushed. The output
is deliberately external to Git and binds the complete repaired pre-A4
provenance set enforced by the production runner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "docs/status/integration/regime_a_occlusion_extraction_v0_1"
BRANCH = "exploration/regime-a-occlusion-extraction-v0-1"
OPERATOR = "Kazim Abbas"
SCIENTIFIC_RUN_ID = "mineocclude-regime-a-first25-v1"
CHECKPOINT_SHA256 = "a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"A4_AUTHORIZATION_REFUSAL: {message}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--final-commit-sha", required=True)
    parser.add_argument("--scientific-run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--operator", default=OPERATOR)
    args = parser.parse_args()

    require(GIT_SHA.fullmatch(args.final_commit_sha) is not None, "invalid final commit SHA")
    require(args.operator == OPERATOR, "operator identity mismatch")
    require(args.scientific_run_id == SCIENTIFIC_RUN_ID, "scientific run identity mismatch")
    require(git("branch", "--show-current") == BRANCH, "branch mismatch")
    require(git("rev-parse", "HEAD") == args.final_commit_sha, "HEAD is not the reviewed final commit")
    require(not git("status", "--porcelain"), "worktree is not clean")
    require(git("rev-parse", f"origin/{BRANCH}") == args.final_commit_sha, "reviewed commit is not pushed to origin")
    require(not args.output.exists(), "authorization output already exists")

    manifest = STATUS / "trajectory_manifest.jsonl"
    manifest_sidecar = STATUS / "trajectory_manifest.sha256"
    study = STATUS / "regime_a_study_manifest.json"
    canonical = STATUS / "pre_a4_canonical_authority.json"
    a2 = STATUS / "implementation_test_receipt.json"
    a3 = STATUS / "a3_validation_receipt.json"
    a2_runner = STATUS / "a2_execution_runner_supersession_receipt.json"
    source_freeze_v2 = STATUS / "pre_a4_source_freeze_receipt_v2.json"
    launch_recovery = STATUS / "a4_launch_recovery_source_freeze_receipt.json"
    manifest_sha256 = sha256_file(manifest)
    require(manifest_sidecar.read_text().strip() == manifest_sha256, "manifest sidecar mismatch")

    document = {
        "schema_version": "regime-a-a4-operator-authorization-v2.0",
        "status": "AUTHORIZED_A4_SCIENTIFIC_EXECUTION",
        "operator": args.operator,
        "scientific_run_id": args.scientific_run_id,
        "final_reviewed_regime_a_commit_sha": args.final_commit_sha,
        "branch": BRANCH,
        "trajectory_manifest_sha256": manifest_sha256,
        "study_manifest_sha256": sha256_file(study),
        "pre_a4_canonical_authority_sha256": sha256_file(canonical),
        "a2_implementation_test_receipt_sha256": sha256_file(a2),
        "a3_validation_receipt_sha256": sha256_file(a3),
        "a2_execution_runner_supersession_receipt_sha256": sha256_file(a2_runner),
        "pre_a4_source_freeze_receipt_v2_sha256": sha256_file(source_freeze_v2),
        "a4_launch_recovery_source_freeze_receipt_sha256": sha256_file(launch_recovery),
        "checkpoint_sha256": CHECKPOINT_SHA256,
        "protocol_modification": False,
        "authorization_scope": "launch the exact frozen 25-spec Regime-A A4 collection only",
    }
    require(all(SHA256.fullmatch(value) for key, value in document.items() if key.endswith("_sha256")), "invalid SHA256 binding")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(payload)
        stream.flush()
    print(json.dumps({"status": "CREATED", "path": str(args.output), "sha256": hashlib.sha256(payload.encode()).hexdigest()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
