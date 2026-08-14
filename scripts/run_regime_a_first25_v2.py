#!/usr/bin/env python3
"""Sealed Regime-A first25-v2 scientific entrypoint (validation by default)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from mineocclude.regime_a import (  # noqa: E402
    AtomicTrajectoryStore,
    HashChainLedger,
    RegimeAError,
    V2_CALIBRATION,
    sha256_file,
    validate_a4_authorization,
    validate_scientific_specs,
)
from mineocclude.regime_a_execution import A4ExecutionRunner, S3DurableStore  # noqa: E402
from scripts.run_regime_a import (  # noqa: E402
    CHECKPOINT_SHA256,
    PersistentMineWorldWorker,
    ProductionCaptureWorker,
    read_jsonl,
)

STATUS = ROOT / "docs/status/integration/regime_a_occlusion_extraction_v0_1"
V2 = STATUS / "v2"
BRANCH = "exploration/regime-a-occlusion-extraction-v0-1"
RUN_ID = "mineocclude-regime-a-first25-v2"


def _git(*arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def validate_manifest(path: Path, sidecar: Path) -> tuple[list[dict[str, object]], str]:
    digest = sha256_file(path)
    if sidecar.read_text(encoding="utf-8").strip() != digest:
        raise RegimeAError("first25-v2 manifest sidecar mismatch")
    rows = read_jsonl(path)
    validate_scientific_specs(rows, V2_CALIBRATION)
    if (
        len(rows) != 25
        or {row.get("scientific_run_id") for row in rows} != {RUN_ID}
        or sum(row.get("direction") == "LEFT_TO_RIGHT" for row in rows) != 13
        or sum(row.get("direction") == "RIGHT_TO_LEFT" for row in rows) != 12
    ):
        raise RegimeAError("first25-v2 frozen identity/count authority mismatch")
    return rows, digest


def authorization_bindings(manifest_hash: str) -> dict[str, str]:
    if _git("branch", "--show-current") != BRANCH:
        raise RegimeAError("first25-v2 branch mismatch")
    if _git("status", "--porcelain"):
        raise RegimeAError("first25-v2 governed worktree must be clean")
    return {
        "final_reviewed_regime_a_commit_sha": _git("rev-parse", "HEAD"),
        "branch": BRANCH,
        "scientific_run_id": RUN_ID,
        "trajectory_manifest_sha256": manifest_hash,
        "donor_manifest_sha256": sha256_file(V2 / "null_donor_manifest.jsonl"),
        "directional_visibility_authority_sha256": sha256_file(
            V2 / "directional_visibility_authority.json"
        ),
        "canonical_precollection_authority_sha256": sha256_file(
            V2 / "canonical_precollection_authority.json"
        ),
        "final_pre_scientific_qualification_sha256": sha256_file(
            V2 / "final_pre_scientific_qualification.json"
        ),
        "checkpoint_sha256": CHECKPOINT_SHA256,
        "authorization_scope": "launch the exact frozen 25-spec Regime-A first25-v2 A4 collection only",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=V2 / "trajectory_manifest.jsonl")
    parser.add_argument(
        "--manifest-sha256", type=Path, default=V2 / "trajectory_manifest.sha256"
    )
    parser.add_argument(
        "--study-manifest", type=Path, default=STATUS / "regime_a_study_manifest.json"
    )
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--durable-prefix", required=True)
    parser.add_argument("--a4-v2-authorization", type=Path)
    parser.add_argument("--authorize-execution", action="store_true")
    arguments = parser.parse_args()

    rows, manifest_hash = validate_manifest(arguments.manifest, arguments.manifest_sha256)
    canonical = json.loads((V2 / "canonical_precollection_authority.json").read_text())
    if (
        canonical.get("status") != "FROZEN_NOT_AUTHORIZED_FOR_EXECUTION"
        or canonical.get("a4_v2_authorization_created") is not False
        or canonical.get("scientific_trajectories_executed") != 0
        or canonical.get("scientific_activations_extracted") != 0
        or canonical.get("scientific_decoding_outcomes_computed") != 0
    ):
        raise RegimeAError("first25-v2 canonical precollection gate is not sealed")
    study_hash = sha256_file(arguments.study_manifest)
    ledger = HashChainLedger(arguments.runtime_root / "progress_ledger.jsonl")
    complete = ledger.complete_ids()
    remaining = [row for row in rows if row["trajectory_spec_id"] not in complete]
    result = {
        "status": "VALIDATED_FROZEN_FIRST25_V2_PLAN_NOT_AUTHORIZED",
        "scientific_run_id": RUN_ID,
        "manifest_sha256": manifest_hash,
        "study_manifest_sha256": study_hash,
        "trajectory_count": len(rows),
        "remaining_spec_ids": [row["trajectory_spec_id"] for row in remaining],
        "execution_started": False,
    }
    if arguments.authorize_execution:
        authority_path = arguments.a4_v2_authorization
        if authority_path is None or not authority_path.is_file():
            raise RegimeAError("A4-v2 scientific execution is sealed: authorization absent")
        validate_a4_authorization(
            json.loads(authority_path.read_text()),
            manifest_hash,
            study_hash,
            expected_bindings=authorization_bindings(manifest_hash),
        )
        runtime_root = arguments.runtime_root.resolve()
        if runtime_root == ROOT.resolve() or ROOT.resolve() in runtime_root.parents:
            raise RegimeAError("first25-v2 runtime root must be outside the repository")
        if "_non_scientific" in arguments.durable_prefix or RUN_ID not in arguments.durable_prefix:
            raise RegimeAError("first25-v2 scientific S3 namespace is not dedicated")
        runner = A4ExecutionRunner(
            store=AtomicTrajectoryStore(runtime_root / "trajectories"),
            ledger=ledger,
            capture_worker=ProductionCaptureWorker(runtime_root),
            model_worker=PersistentMineWorldWorker(),
            durable_store=S3DurableStore(arguments.durable_prefix),
        )
        dispatched = runner.run(rows)
        result.update(
            {
                "status": "COMPLETE_VALIDATED_DURABLE",
                "dispatched_spec_ids": dispatched,
                "execution_started": bool(dispatched),
            }
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RegimeAError, FileNotFoundError, json.JSONDecodeError) as error:
        print(f"REGIME_A_FIRST25_V2_REFUSAL: {error}", file=sys.stderr)
        raise SystemExit(2)
