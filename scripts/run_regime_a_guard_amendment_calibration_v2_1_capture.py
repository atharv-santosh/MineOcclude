#!/usr/bin/env python3
"""Capture the frozen 12-crossing Regime-A v2 amendment calibration set."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from mineocclude.regime_a import AtomicTrajectoryStore, RegimeAError, canonical_sha256  # noqa: E402
from scripts.run_regime_a import ProductionCaptureWorker, read_jsonl  # noqa: E402


def validate_specs(path: Path, sidecar: Path) -> list[dict[str, object]]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if sidecar.read_text(encoding="utf-8").strip() != digest:
        raise RegimeAError("calibration extension manifest sidecar mismatch")
    rows = read_jsonl(path)
    if len(rows) != 12:
        raise RegimeAError("calibration extension must contain exactly 12 crossings")
    directions = [row.get("direction") for row in rows]
    if directions.count("LEFT_TO_RIGHT") != 6 or directions.count("RIGHT_TO_LEFT") != 6:
        raise RegimeAError("calibration extension must contain six crossings per direction")
    ids: set[object] = set()
    seeds: set[object] = set()
    for row in rows:
        body = dict(row)
        claimed = body.pop("spec_hash", None)
        if canonical_sha256(body) != claimed:
            raise RegimeAError("calibration extension spec hash mismatch")
        if (
            row.get("NON_SCIENTIFIC_CALIBRATION") is not True
            or row.get("ELIGIBLE_FOR_REGIME_A_RESULTS") is not False
            or row.get("scientific_role") != "NON_SCIENTIFIC_DIRECTIONAL_CALIBRATION"
            or row.get("capture_protocol") != "capture_ack_lockstep"
        ):
            raise RegimeAError("calibration extension is not permanently ineligible")
        ids.add(row.get("trajectory_spec_id"))
        seeds.add(row.get("seed"))
    if len(ids) != 12 or len(seeds) != 12:
        raise RegimeAError("calibration extension identities/seeds are not unique")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    args = parser.parse_args()
    runtime_root = args.runtime_root.resolve()
    if runtime_root == ROOT.resolve() or ROOT.resolve() in runtime_root.parents:
        raise RegimeAError("calibration extension runtime root must be outside repository")
    rows = validate_specs(args.manifest, args.manifest_sha256)
    store = AtomicTrajectoryStore(runtime_root / "trajectories")
    worker = ProductionCaptureWorker(runtime_root)
    captured: list[dict[str, object]] = []
    try:
        for row in rows:
            spec_id = str(row["trajectory_spec_id"])
            spec_hash = str(row["spec_hash"])
            partial = store.same_spec_partial(spec_id, spec_hash)
            resumed_existing = partial is not None
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
                            "direction": row["direction"],
                            "calibration_replicate": row["calibration_replicate"],
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                worker.capture(row, partial, validate_and_package=False)
            elif not (partial / "raw").is_dir():
                raise RegimeAError("existing calibration extension partial lacks raw bytes")
            captured.append(
                {
                    "trajectory_spec_id": spec_id,
                    "spec_hash": spec_hash,
                    "seed": row["seed"],
                    "direction": row["direction"],
                    "partial": str(partial),
                    "resumed_existing_raw_capture": resumed_existing,
                }
            )
    finally:
        worker.close()
    report = {
        "schema_version": "regime-a-calibration-extension-capture-set-v2.1",
        "NON_SCIENTIFIC_CALIBRATION": True,
        "ELIGIBLE_FOR_REGIME_A_RESULTS": False,
        "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        "runtime_session_count": 1 if captured else 0,
        "launch_attempts": worker.launch_attempts,
        "launch_failures": worker.launch_failures,
        "crossings": captured,
    }
    runtime_root.mkdir(parents=True, exist_ok=True)
    (runtime_root / "calibration_extension_capture_set.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RegimeAError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"REGIME_A_CALIBRATION_EXTENSION_CAPTURE_REFUSAL: {exc}", file=sys.stderr)
        raise SystemExit(2)
