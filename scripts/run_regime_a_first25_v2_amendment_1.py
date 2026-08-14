#!/usr/bin/env python3
"""Governed Regime-A first25-v2 amendment-1 scientific entrypoint."""

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
    VisibilityCalibration,
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
AMENDMENT = STATUS / "v2_amendment_1"
BRANCH = "exploration/regime-a-occlusion-extraction-v0-1"
RUN_ID = "mineocclude-regime-a-first25-v2"
SCOPE = "resume the exact frozen Regime-A first25-v2 amendment-1 collection only"


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def load_calibration(authority: dict[str, object]) -> VisibilityCalibration:
    value = dict(authority["planning_calibration"])
    return VisibilityCalibration(
        hidden_left=float(value["hidden_left"]),
        hidden_right=float(value["hidden_right"]),
        geometric_entry={key: float(item) for key, item in dict(value["geometric_entry"]).items()},
        entry_guard={key: int(item) for key, item in dict(value["entry_guard_frames"]).items()},
        exit_guard={key: int(item) for key, item in dict(value["exit_guard_frames"]).items()},
        directional_hidden_entry={
            key: float(item) for key, item in dict(value["directional_hidden_entry"]).items()
        },
        directional_hidden_exit={
            key: float(item) for key, item in dict(value["directional_hidden_exit"]).items()
        },
    )


def validate_manifest(
    path: Path, sidecar: Path, authority_path: Path
) -> tuple[list[dict[str, object]], str]:
    digest = sha256_file(path)
    if sidecar.read_text().strip() != digest:
        raise RegimeAError("amended scientific manifest sidecar mismatch")
    authority = json.loads(authority_path.read_text())
    if (
        authority.get("status") != "FROZEN_OUTCOME_BLIND_AFTER_STRUCTURAL_QC_TRIGGER"
        or authority.get("t04_used_in_numerical_derivation") is not False
        or authority.get("scientific_decoding_outcomes_computed_before_freeze") != 0
    ):
        raise RegimeAError("amended authority is not outcome-blind and frozen")
    rows = read_jsonl(path)
    validate_scientific_specs(rows, load_calibration(authority))
    if (
        len(rows) != 25
        or {row.get("scientific_run_id") for row in rows} != {RUN_ID}
        or any(row.get("physical_capture_protocol_changed") is not False for row in rows)
        or any(row.get("raw_capture_spec_hash") != row.get("original_v2_spec_hash") for row in rows)
    ):
        raise RegimeAError("amended manifest identity/provenance mismatch")
    return rows, digest


def authorization_bindings(manifest_hash: str) -> dict[str, str]:
    if git("branch", "--show-current") != BRANCH:
        raise RegimeAError("amended collection branch mismatch")
    if git("status", "--porcelain"):
        raise RegimeAError("amended governed worktree must be clean")
    return {
        "final_reviewed_regime_a_commit_sha": git("rev-parse", "HEAD"),
        "branch": BRANCH,
        "scientific_run_id": RUN_ID,
        "trajectory_manifest_sha256": manifest_hash,
        "original_v2_trajectory_manifest_sha256": sha256_file(V2 / "trajectory_manifest.jsonl"),
        "directional_visibility_authority_amendment_sha256": sha256_file(
            AMENDMENT / "directional_visibility_authority_v2_1_amendment_1.json"
        ),
        "context_bin_revalidation_sha256": sha256_file(
            AMENDMENT / "context_bin_revalidation.json"
        ),
        "scientific_salvage_replay_sha256": sha256_file(
            AMENDMENT / "scientific_structural_replay_t01_t04.json"
        ),
        "donor_manifest_sha256": sha256_file(V2 / "null_donor_manifest.jsonl"),
        "checkpoint_sha256": CHECKPOINT_SHA256,
        "authorization_scope": SCOPE,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest", type=Path, default=AMENDMENT / "trajectory_manifest_v2_1_amendment_1.jsonl"
    )
    parser.add_argument(
        "--manifest-sha256",
        type=Path,
        default=AMENDMENT / "trajectory_manifest_v2_1_amendment_1.sha256",
    )
    parser.add_argument(
        "--authority",
        type=Path,
        default=AMENDMENT / "directional_visibility_authority_v2_1_amendment_1.json",
    )
    parser.add_argument("--study-manifest", type=Path, default=STATUS / "regime_a_study_manifest.json")
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--durable-prefix", required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--authorize-execution", action="store_true")
    args = parser.parse_args()
    rows, manifest_hash = validate_manifest(args.manifest, args.manifest_sha256, args.authority)
    study_hash = sha256_file(args.study_manifest)
    result: dict[str, object] = {
        "status": "VALIDATED_FROZEN_AMENDMENT_1_NOT_AUTHORIZED",
        "scientific_run_id": RUN_ID,
        "manifest_sha256": manifest_hash,
        "authority_sha256": sha256_file(args.authority),
        "execution_started": False,
    }
    if args.authorize_execution:
        if not args.authorization.is_file():
            raise RegimeAError("amendment-1 operator authorization is absent")
        validate_a4_authorization(
            json.loads(args.authorization.read_text()),
            manifest_hash,
            study_hash,
            expected_bindings=authorization_bindings(manifest_hash),
        )
        runtime = args.runtime_root.resolve()
        if runtime == ROOT.resolve() or ROOT.resolve() in runtime.parents:
            raise RegimeAError("amended runtime must be outside repository")
        if RUN_ID not in args.durable_prefix or "amendment-1" not in args.durable_prefix:
            raise RegimeAError("amended durable namespace is not dedicated")
        bootstrap_path = runtime / "salvage_bootstrap_receipt.json"
        if not bootstrap_path.is_file():
            raise RegimeAError("amended salvage bootstrap receipt is absent")
        bootstrap = json.loads(bootstrap_path.read_text())
        if (
            bootstrap.get("status") != "EXISTING_SCIENTIFIC_CAPTURE_SALVAGE_VALID"
            or bootstrap.get("amended_manifest_sha256") != manifest_hash
            or bootstrap.get("scientific_replay_sha256")
            != sha256_file(AMENDMENT / "scientific_structural_replay_t01_t04.json")
            or bootstrap.get("scientific_outcomes_computed") != 0
        ):
            raise RegimeAError("amended salvage bootstrap binding mismatch")
        ledger = HashChainLedger(runtime / "progress_ledger.jsonl")
        if ledger.complete_ids() != {
            "regime_a_v2_t01",
            "regime_a_v2_t02",
            "regime_a_v2_t03",
        }:
            raise RegimeAError("amended bootstrap complete set mismatch")
        runner = A4ExecutionRunner(
            store=AtomicTrajectoryStore(runtime / "trajectories"),
            ledger=ledger,
            capture_worker=ProductionCaptureWorker(runtime),
            model_worker=PersistentMineWorldWorker(),
            durable_store=S3DurableStore(args.durable_prefix),
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
    except (RegimeAError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"REGIME_A_FIRST25_V2_AMENDMENT_1_REFUSAL: {exc}", file=sys.stderr)
        raise SystemExit(2)
