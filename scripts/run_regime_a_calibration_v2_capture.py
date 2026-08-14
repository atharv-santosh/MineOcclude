#!/usr/bin/env python3
"""Collect qualified non-scientific calibration crossings without packaging."""

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
    RegimeAError,
    canonical_sha256,
)
from scripts.run_regime_a import ProductionCaptureWorker, read_jsonl  # noqa: E402


def validate_specs(path: Path) -> list[dict[str, object]]:
    rows = read_jsonl(path)
    if len(rows) != 4:
        raise RegimeAError("calibration manifest must contain exactly four crossings")
    directions = [row.get("direction") for row in rows]
    if directions.count("LEFT_TO_RIGHT") != 2 or directions.count("RIGHT_TO_LEFT") != 2:
        raise RegimeAError("calibration manifest must contain two crossings per direction")
    ids: set[object] = set()
    seeds: set[object] = set()
    for row in rows:
        body = dict(row)
        claimed = body.pop("spec_hash", None)
        if canonical_sha256(body) != claimed:
            raise RegimeAError("calibration spec hash mismatch")
        if (
            row.get("NON_SCIENTIFIC_CALIBRATION") is not True
            or row.get("ELIGIBLE_FOR_REGIME_A_RESULTS") is not False
            or row.get("scientific_role") != "NON_SCIENTIFIC_DIRECTIONAL_CALIBRATION"
        ):
            raise RegimeAError("calibration identity is not permanently ineligible")
        ids.add(row.get("trajectory_spec_id"))
        seeds.add(row.get("seed"))
    if len(ids) != 4 or len(seeds) != 4:
        raise RegimeAError("calibration identities and seeds must be unique")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    args = parser.parse_args()
    runtime_root = args.runtime_root.resolve()
    if runtime_root == ROOT.resolve() or ROOT.resolve() in runtime_root.parents:
        raise RegimeAError("calibration runtime root must be outside the repository")
    rows = validate_specs(args.manifest)
    store = AtomicTrajectoryStore(runtime_root / "trajectories")
    worker = ProductionCaptureWorker(runtime_root)
    captured: list[dict[str, object]] = []
    try:
        for row in rows:
            spec_id = str(row["trajectory_spec_id"])
            spec_hash = str(row["spec_hash"])
            partial = store.same_spec_partial(spec_id, spec_hash)
            if partial is None:
                partial = store.begin(spec_id, spec_hash)
                (partial / "calibration_identity.json").write_text(
                    json.dumps(
                        {
                            "NON_SCIENTIFIC_CALIBRATION": True,
                            "ELIGIBLE_FOR_REGIME_A_RESULTS": False,
                            "trajectory_spec_id": spec_id,
                            "spec_hash": spec_hash,
                            "seed": row["seed"],
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                worker.capture(row, partial, validate_and_package=False)
            elif not (partial / "raw").is_dir():
                raise RegimeAError("existing calibration partial is incomplete")
            captured.append(
                {
                    "trajectory_spec_id": spec_id,
                    "spec_hash": spec_hash,
                    "seed": row["seed"],
                    "direction": row["direction"],
                    "partial": str(partial),
                }
            )
    finally:
        worker.close()
    report = {
        "schema_version": "regime-a-calibration-capture-set-v2.0",
        "NON_SCIENTIFIC_CALIBRATION": True,
        "ELIGIBLE_FOR_REGIME_A_RESULTS": False,
        "launch_attempts": worker.launch_attempts,
        "launch_failures": worker.launch_failures,
        "crossings": captured,
    }
    (runtime_root / "calibration_capture_set.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RegimeAError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"REGIME_A_CALIBRATION_CAPTURE_REFUSAL: {exc}", file=sys.stderr)
        raise SystemExit(2)
