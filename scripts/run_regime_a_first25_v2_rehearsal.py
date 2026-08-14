#!/usr/bin/env python3
"""Run the complete non-scientific first25-v2 production rehearsal path."""

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
    COMPLETE_STATE,
    HashChainLedger,
    RegimeAError,
    canonical_sha256,
)
from mineocclude.regime_a_execution import A4ExecutionRunner, S3DurableStore  # noqa: E402
from scripts.run_regime_a import (  # noqa: E402
    PersistentMineWorldWorker,
    ProductionCaptureWorker,
    read_jsonl,
)

SCIENTIFIC = (
    ROOT
    / "docs/status/integration/regime_a_occlusion_extraction_v0_1/v2/trajectory_manifest.jsonl"
)


def validate_specs(path: Path) -> list[dict[str, object]]:
    rows = read_jsonl(path)
    scientific = read_jsonl(SCIENTIFIC)
    scientific_ids = {row["trajectory_spec_id"] for row in scientific}
    scientific_seeds = {row["seed"] for row in scientific}
    if len(rows) != 2 or {row.get("direction") for row in rows} != {
        "LEFT_TO_RIGHT",
        "RIGHT_TO_LEFT",
    }:
        raise RegimeAError("full v2 rehearsal requires one spec per direction")
    for row in rows:
        body = dict(row)
        claimed = body.pop("spec_hash", None)
        if canonical_sha256(body) != claimed:
            raise RegimeAError("full v2 rehearsal spec hash mismatch")
        if (
            row.get("NON_SCIENTIFIC_INTEGRATION_REHEARSAL") is not True
            or row.get("ELIGIBLE_FOR_REGIME_A_RESULTS") is not False
            or row.get("trajectory_spec_id") in scientific_ids
            or row.get("seed") in scientific_seeds
        ):
            raise RegimeAError("full v2 rehearsal identity overlaps science")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--durable-prefix", required=True)
    args = parser.parse_args()
    if "_non_scientific_first25_v2_rehearsal" not in args.durable_prefix:
        raise RegimeAError("S3 prefix is not dedicated to the non-scientific v2 rehearsal")
    specs = validate_specs(args.manifest)
    runtime_root = args.runtime_root.resolve()
    if runtime_root == ROOT.resolve() or ROOT.resolve() in runtime_root.parents:
        raise RegimeAError("full v2 rehearsal runtime root must be outside repository")
    reconciliation_path = runtime_root / "target_reconciliation_qualification.json"
    reconciliation = json.loads(reconciliation_path.read_text())
    if reconciliation.get("PASS") is not True:
        raise RegimeAError("LTR/RTL target reconciliation gate has not passed")

    ledger = HashChainLedger(runtime_root / "progress_ledger.jsonl")
    capture = ProductionCaptureWorker(runtime_root)
    model = PersistentMineWorldWorker()
    before_complete = ledger.complete_ids()
    runner = A4ExecutionRunner(
        store=AtomicTrajectoryStore(runtime_root / "trajectories"),
        ledger=ledger,
        capture_worker=capture,
        model_worker=model,
        durable_store=S3DurableStore(args.durable_prefix),
    )
    dispatched = runner.run(specs)
    after = HashChainLedger(runtime_root / "progress_ledger.jsonl")
    completed = after.complete_ids()
    report = {
        "schema_version": "regime-a-first25-v2-full-rehearsal-run-v1.0",
        "NON_SCIENTIFIC_INTEGRATION_REHEARSAL": True,
        "ELIGIBLE_FOR_REGIME_A_RESULTS": False,
        "runtime_root": str(runtime_root),
        "durable_prefix": args.durable_prefix,
        "complete_before": sorted(before_complete),
        "dispatched_spec_ids": dispatched,
        "complete_after": sorted(completed),
        "checkpoint_load_count_this_run": model.load_count,
        "all_complete_validated_durable": all(
            str(spec["trajectory_spec_id"]) in completed for spec in specs
        ),
        "completed_units_skipped": sorted(
            str(spec["trajectory_spec_id"])
            for spec in specs
            if str(spec["trajectory_spec_id"]) in before_complete
            and str(spec["trajectory_spec_id"]) not in dispatched
        ),
        "ledger_last_states": {
            str(spec["trajectory_spec_id"]): next(
                row["state"]
                for row in reversed(after.records)
                if row["trajectory_spec_id"] == spec["trajectory_spec_id"]
            )
            for spec in specs
        },
        "expected_terminal_state": COMPLETE_STATE,
    }
    report["PASS"] = report["all_complete_validated_durable"]
    output = runtime_root / (
        "full_rehearsal_restart_report.json"
        if before_complete
        else "full_rehearsal_initial_report.json"
    )
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["PASS"] else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RegimeAError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"REGIME_A_V2_REHEARSAL_REFUSAL: {exc}", file=sys.stderr)
        raise SystemExit(2)
