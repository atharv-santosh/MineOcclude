#!/usr/bin/env python3
"""Create separate immutable operational and frozen-science P11 checkouts."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

SCIENTIFIC_COMMIT = "173a3ca3e92ffe771d19911c15c006dba6acc934"
IMMUTABLE_HANDOFF_COMMIT = "c701eef7ef4042802c489748fb3f1c532d322cf2"
SCIENTIFIC_BRANCH = "exploration/large-scale-no-wall-scaling-best-k-v0-1"
WORKERS = {"me", "alan", "atharv", "ayman", "sahil"}
STUDY_RELATIVE = Path(
    "docs/status/integration/exploratory_large_scale_no_wall_scaling_best_k_v0_1"
)


class BootstrapError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BootstrapError(message)


def run(command: list[str], *, cwd: Path | None = None) -> str:
    return subprocess.check_output(command, cwd=cwd, text=True).strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def immutable_paths(repository: Path) -> list[str]:
    paths = [
        "p11_distributed_handoff/common_authority.json",
        "p11_distributed_handoff/authority_bundle.sha256",
    ]
    for slug in sorted(WORKERS):
        paths.extend(
            (
                f"p11_distributed_handoff/{slug}/shard_manifest.json",
                f"p11_distributed_handoff/p11_shard_{slug}.json",
            )
        )
    bundle = run(
        [
            "git", "ls-tree", "-r", "--name-only", IMMUTABLE_HANDOFF_COMMIT,
            "--", "p11_distributed_handoff/authority_bundle",
        ],
        cwd=repository,
    ).splitlines()
    return paths + bundle


def verify_immutable_handoff(repository: Path, operational_commit: str) -> list[str]:
    paths = immutable_paths(repository)
    for relative in paths:
        require((repository / relative).is_file(), f"immutable handoff path absent: {relative}")
    completed = subprocess.run(
        ["git", "diff", "--quiet", IMMUTABLE_HANDOFF_COMMIT, operational_commit, "--", *paths],
        cwd=repository,
        check=False,
    )
    require(completed.returncode == 0, "immutable c701eef handoff authority changed")
    return paths


def install_authority_bundle(operational: Path, scientific: Path) -> dict[str, str]:
    checksum_path = operational / "p11_distributed_handoff/authority_bundle.sha256"
    claims: dict[str, str] = {}
    destination = scientific / STUDY_RELATIVE
    destination.mkdir(parents=True, exist_ok=True)
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split(None, 1)
        source = operational / relative.strip()
        require(source.is_file() and sha256(source) == expected, f"authority bundle hash mismatch: {relative}")
        target = destination / source.name
        shutil.copy2(source, target)
        require(sha256(target) == expected, f"installed authority hash mismatch: {source.name}")
        claims[target.name] = expected
    return claims


def bootstrap_worker(
    repository_url: str,
    destination: Path,
    operational_commit: str,
    worker_slug: str,
) -> dict[str, Any]:
    require(len(operational_commit) == 40, "full 40-character operational commit required")
    require(worker_slug in WORKERS, "unknown worker slug")
    require(not destination.exists(), "bootstrap destination already exists")
    operational = destination / "operational"
    scientific = destination / "scientific"
    destination.mkdir(parents=True)
    try:
        local_source = Path(repository_url)
        if local_source.is_dir():
            subprocess.run(
                ["git", "clone", "--shared", "--no-checkout", str(local_source.resolve()), str(operational)],
                check=True, capture_output=True, text=True,
            )
        else:
            subprocess.run(["git", "init", str(operational)], check=True, capture_output=True, text=True)
            subprocess.run(["git", "remote", "add", "origin", repository_url], cwd=operational, check=True)
            subprocess.run(
                ["git", "fetch", "--no-tags", "origin", operational_commit],
                cwd=operational, check=True,
            )
        subprocess.run(["git", "checkout", "--detach", operational_commit], cwd=operational, check=True)
        require(run(["git", "rev-parse", "HEAD"], cwd=operational) == operational_commit, "operational checkout moved")
        require(
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", IMMUTABLE_HANDOFF_COMMIT, operational_commit],
                cwd=operational, check=False,
            ).returncode == 0,
            "operational commit does not contain immutable handoff authority",
        )
        require(run(["git", "rev-parse", SCIENTIFIC_COMMIT], cwd=operational) == SCIENTIFIC_COMMIT, "scientific commit unavailable")
        immutable = verify_immutable_handoff(operational, operational_commit)
        subprocess.run(["git", "branch", "-f", SCIENTIFIC_BRANCH, SCIENTIFIC_COMMIT], cwd=operational, check=True)
        subprocess.run(["git", "worktree", "add", str(scientific), SCIENTIFIC_BRANCH], cwd=operational, check=True)
        require(run(["git", "branch", "--show-current"], cwd=scientific) == SCIENTIFIC_BRANCH, "scientific branch mismatch")
        require(run(["git", "rev-parse", "HEAD"], cwd=scientific) == SCIENTIFIC_COMMIT, "scientific HEAD mismatch")
        bundle_hashes = install_authority_bundle(operational, scientific)
        shard = json.loads(
            (operational / f"p11_distributed_handoff/{worker_slug}/shard_manifest.json").read_text(encoding="utf-8")
        )
        require(shard["worker_slug"] == worker_slug, "selected worker manifest mismatch")
        require(shard["implementation_commit_sha"] == SCIENTIFIC_COMMIT, "manifest science authority mismatch")
        require(shard["repository_branch"] == SCIENTIFIC_BRANCH, "manifest branch authority mismatch")
        receipt: dict[str, Any] = {
            "artifact_id": "large-scale-no-wall-p11-fresh-worker-bootstrap-v0.1",
            "status": "PASS_FRESH_WORKER_BOOTSTRAP",
            "repository_url": repository_url,
            "operational_root": str(operational.resolve()),
            "operational_handoff_commit": operational_commit,
            "immutable_handoff_commit": IMMUTABLE_HANDOFF_COMMIT,
            "immutable_handoff_path_count": len(immutable),
            "scientific_root": str(scientific.resolve()),
            "scientific_branch": SCIENTIFIC_BRANCH,
            "scientific_implementation_commit": SCIENTIFIC_COMMIT,
            "worker_slug": worker_slug,
            "worker_name": shard["worker_name"],
            "shard_manifest_sha": shard["shard_manifest_sha"],
            "authority_bundle_sha256": bundle_hashes,
            "moving_branch_head_used": False,
        }
        receipt_path = operational / "p11_worker_bootstrap_receipt.json"
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return receipt
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-url", required=True)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--operational-handoff-commit", required=True)
    parser.add_argument("--worker", required=True, choices=sorted(WORKERS))
    args = parser.parse_args()
    print(
        json.dumps(
            bootstrap_worker(
                args.repository_url, args.destination.resolve(),
                args.operational_handoff_commit, args.worker,
            ),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
