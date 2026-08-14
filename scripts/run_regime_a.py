#!/usr/bin/env python3
"""Fail-closed Regime-A first-slice runner boundary.

This runner intentionally cannot start A4 without a separate, hash-bound
operator authorization.  It owns deterministic manifest intake, per-spec
atomic staging, validation, durability verification, and exact resume state;
Minecraft capture and MineWorld inference are delegated to the repository's
already validated runtime adapters.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.regime_a import (  # noqa: E402
    AtomicTrajectoryStore,
    COMPLETE_STATE,
    HashChainLedger,
    RegimeAError,
    canonical_sha256,
    sha256_file,
    validate_a4_authorization,
    validate_scientific_specs,
    verified_local_durable_copy,
)


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def validate_manifest(path: Path, expected_sidecar: Path) -> tuple[list[dict[str, object]], str]:
    digest = sha256_file(path)
    if expected_sidecar.read_text(encoding="utf-8").strip() != digest:
        raise RegimeAError("trajectory manifest sidecar mismatch")
    rows = read_jsonl(path)
    validate_scientific_specs(rows)
    return rows, digest


def frozen_plan(rows: list[dict[str, object]], ledger: HashChainLedger) -> list[dict[str, object]]:
    complete = ledger.complete_ids()
    return [row for row in rows if str(row["trajectory_spec_id"]) not in complete]


def authorize_or_fail(authority_path: Path | None, manifest_hash: str, study_hash: str) -> None:
    if authority_path is None or not authority_path.is_file():
        raise RegimeAError("A4 execution is sealed: separate operator authorization is absent")
    validate_a4_authorization(json.loads(authority_path.read_text()), manifest_hash, study_hash)


def finalize_validated_unit(
    store: AtomicTrajectoryStore,
    ledger: HashChainLedger,
    partial: Path,
    spec: dict[str, object],
    durable_root: Path,
) -> Path:
    spec_id = str(spec["trajectory_spec_id"])
    spec_hash = str(spec["spec_hash"])
    final = store.finalize(partial, spec_id, spec_hash)
    store.validate(spec_id, spec_hash)
    ledger.append(spec_id, "VALIDATED", spec_hash=spec_hash, local_sha256=canonical_sha256(json.loads((final / "completion.json").read_text())))
    destination = durable_root / spec_id / "completion.json"
    receipt = verified_local_durable_copy(final / "completion.json", destination)
    ledger.append(spec_id, "DURABLE", spec_hash=spec_hash, durable_receipt=receipt)
    ledger.append(spec_id, COMPLETE_STATE, spec_hash=spec_hash)
    return final


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", type=Path, required=True)
    parser.add_argument("--study-manifest", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--durable-root", type=Path, required=True)
    parser.add_argument("--a4-authorization", type=Path)
    parser.add_argument("--authorize-execution", action="store_true")
    args = parser.parse_args()

    rows, manifest_hash = validate_manifest(args.manifest, args.manifest_sha256)
    study_hash = sha256_file(args.study_manifest)
    ledger = HashChainLedger(args.runtime_root / "progress_ledger.jsonl")
    plan = frozen_plan(rows, ledger)
    result = {
        "status": "VALIDATED_FROZEN_PLAN",
        "manifest_sha256": manifest_hash,
        "study_manifest_sha256": study_hash,
        "remaining_spec_ids": [row["trajectory_spec_id"] for row in plan],
        "complete_count": len(rows) - len(plan),
        "execution_started": False,
    }
    if args.authorize_execution:
        authorize_or_fail(args.a4_authorization, manifest_hash, study_hash)
        result["status"] = "AUTHORIZED_EXECUTION_BOUNDARY_VALIDATED"
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RegimeAError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"REGIME_A_REFUSAL: {exc}", file=sys.stderr)
        raise SystemExit(2)
