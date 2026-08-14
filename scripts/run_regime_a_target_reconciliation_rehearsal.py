#!/usr/bin/env python3
"""Run two isolated real captures to qualify Regime-A target reconciliation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from mineocclude.regime_a import (  # noqa: E402
    AtomicTrajectoryStore,
    HashChainLedger,
    RegimeAError,
    canonical_sha256,
    sha256_file,
)
from scripts.run_regime_a import ProductionCaptureWorker, read_jsonl  # noqa: E402


SCIENTIFIC_MANIFEST = (
    ROOT
    / "docs/status/integration/regime_a_occlusion_extraction_v0_1/trajectory_manifest.jsonl"
)
FROZEN_SCIENTIFIC_MANIFEST_SHA256 = (
    "54f47bfb7167cb0a74a58b42f363258080501a05ec5519cf1c9c3edb113fd785"
)
FROZEN_DONOR_MANIFEST_SHA256 = (
    "0b8b224ead6737ba24d17251955ae56d5cb0e5ab1ca37ba5f5fb87529508676b"
)
DONOR_MANIFEST = SCIENTIFIC_MANIFEST.with_name("null_donor_manifest.jsonl")


def write_new_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def validate_rehearsal_specs(path: Path) -> list[dict[str, object]]:
    specs = read_jsonl(path)
    if len(specs) != 2 or {row.get("direction") for row in specs} != {
        "LEFT_TO_RIGHT",
        "RIGHT_TO_LEFT",
    }:
        raise RegimeAError("rehearsal manifest must contain exactly one spec per direction")
    scientific = read_jsonl(SCIENTIFIC_MANIFEST)
    scientific_ids = {row["trajectory_spec_id"] for row in scientific}
    scientific_seeds = {row["seed"] for row in scientific}
    for spec in specs:
        body = dict(spec)
        claimed = body.pop("spec_hash", None)
        if canonical_sha256(body) != claimed:
            raise RegimeAError("rehearsal spec hash mismatch")
        if (
            spec.get("NON_SCIENTIFIC_INTEGRATION_REHEARSAL") is not True
            or spec.get("ELIGIBLE_FOR_REGIME_A_RESULTS") is not False
            or spec.get("trajectory_spec_id") in scientific_ids
            or spec.get("seed") in scientific_seeds
        ):
            raise RegimeAError("rehearsal identity is not isolated from science")
    if sha256_file(SCIENTIFIC_MANIFEST) != FROZEN_SCIENTIFIC_MANIFEST_SHA256:
        raise RegimeAError("frozen scientific trajectory manifest changed")
    if sha256_file(DONOR_MANIFEST) != FROZEN_DONOR_MANIFEST_SHA256:
        raise RegimeAError("frozen donor manifest changed")
    return specs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--durable-prefix", required=True)
    args = parser.parse_args()

    specs = validate_rehearsal_specs(args.manifest)
    runtime_root = args.runtime_root.resolve()
    if runtime_root == ROOT.resolve() or ROOT.resolve() in runtime_root.parents:
        raise RegimeAError("rehearsal runtime root must be outside the repository")
    if "_non_scientific_integration_rehearsal" not in args.durable_prefix:
        raise RegimeAError("rehearsal S3 prefix is not visibly non-scientific")

    store = AtomicTrajectoryStore(runtime_root / "trajectories")
    ledger = HashChainLedger(runtime_root / "progress_ledger.jsonl")
    worker = ProductionCaptureWorker(runtime_root)
    results: list[dict[str, object]] = []
    try:
        for spec in specs:
            spec_id = str(spec["trajectory_spec_id"])
            spec_hash = str(spec["spec_hash"])
            partial = store.same_spec_partial(spec_id, spec_hash)
            if partial is not None and not (partial / "raw").exists():
                observed_files = {
                    path.relative_to(partial).as_posix()
                    for path in partial.rglob("*")
                    if path.is_file()
                }
                if observed_files != {
                    "partial_identity.json",
                    "rehearsal_identity.json",
                }:
                    raise RegimeAError(
                        "pre-capture rehearsal partial contains unexpected artifacts"
                    )
                store.discard_same_spec_partial(spec_id, spec_hash)
                ledger.append(
                    spec_id,
                    "PLANNED",
                    spec_hash=spec_hash,
                    seed=int(spec["seed"]),
                    retry_same_spec=True,
                    pre_capture_retry=True,
                    NON_SCIENTIFIC_INTEGRATION_REHEARSAL=True,
                    ELIGIBLE_FOR_REGIME_A_RESULTS=False,
                )
                partial = None
            if partial is None:
                if not any(
                    row["trajectory_spec_id"] == spec_id
                    and row["state"] == "PLANNED"
                    for row in ledger.records[-1:]
                ):
                    ledger.append(
                        spec_id,
                        "PLANNED",
                        spec_hash=spec_hash,
                        seed=int(spec["seed"]),
                        NON_SCIENTIFIC_INTEGRATION_REHEARSAL=True,
                        ELIGIBLE_FOR_REGIME_A_RESULTS=False,
                    )
                partial = store.begin(spec_id, spec_hash)
                write_new_json(
                    partial / "rehearsal_identity.json",
                    {
                        "NON_SCIENTIFIC_INTEGRATION_REHEARSAL": True,
                        "ELIGIBLE_FOR_REGIME_A_RESULTS": False,
                        "trajectory_spec_id": spec_id,
                        "spec_hash": spec_hash,
                        "runtime_root": str(runtime_root),
                        "durable_prefix_reserved_for_full_rehearsal": args.durable_prefix,
                    },
                )
                ledger.append(
                    spec_id,
                    "RUNNING",
                    spec_hash=spec_hash,
                    seed=int(spec["seed"]),
                    NON_SCIENTIFIC_INTEGRATION_REHEARSAL=True,
                    ELIGIBLE_FOR_REGIME_A_RESULTS=False,
                )
                worker.capture(spec, partial, validate_and_package=False)
                ledger.append(
                    spec_id,
                    "CAPTURED",
                    spec_hash=spec_hash,
                    NON_SCIENTIFIC_INTEGRATION_REHEARSAL=True,
                    ELIGIBLE_FOR_REGIME_A_RESULTS=False,
                )
            elif not (partial / "raw").is_dir():
                raise RegimeAError("existing rehearsal partial has no raw capture")

            reconciliation = {
                "schema_version": "regime-a-target-reconciliation-rehearsal-v1.0",
                "NON_SCIENTIFIC_INTEGRATION_REHEARSAL": True,
                "ELIGIBLE_FOR_REGIME_A_RESULTS": False,
                "trajectory_spec_id": spec_id,
                "spec_hash": spec_hash,
                "direction": spec["direction"],
                "prospective_authority": "fixed world-x stable-hidden interval",
                "observed_authority": "frozen geometric plus magenta OCCLUDED_AGREEMENT",
                **worker.target_reconciliation(spec, partial),
            }
            receipt_path = partial / "target_reconciliation.json"
            if receipt_path.exists():
                observed = json.loads(receipt_path.read_text(encoding="utf-8"))
                if observed != reconciliation:
                    raise RegimeAError("existing target reconciliation receipt drift")
            else:
                write_new_json(receipt_path, reconciliation)
            results.append(reconciliation)
    finally:
        worker.close()

    report = {
        "schema_version": "regime-a-target-reconciliation-qualification-v1.0",
        "NON_SCIENTIFIC_INTEGRATION_REHEARSAL": True,
        "ELIGIBLE_FOR_REGIME_A_RESULTS": False,
        "runtime_root": str(runtime_root),
        "durable_prefix_reserved_for_full_rehearsal": args.durable_prefix,
        "scientific_manifest_sha256": sha256_file(SCIENTIFIC_MANIFEST),
        "donor_manifest_sha256": sha256_file(DONOR_MANIFEST),
        "EXPECTED_AND_OBSERVED_STABLE_HIDDEN_TARGETS_RECONCILE": all(
            row["exact_reconciliation"] for row in results
        ),
        "results": results,
    }
    report_path = runtime_root / "target_reconciliation_qualification.json"
    if report_path.exists():
        report_path.unlink()
    write_new_json(report_path, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["EXPECTED_AND_OBSERVED_STABLE_HIDDEN_TARGETS_RECONCILE"] else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RegimeAError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"REGIME_A_REHEARSAL_REFUSAL: {exc}", file=sys.stderr)
        raise SystemExit(2)
