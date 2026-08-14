#!/usr/bin/env python3
"""Bootstrap amended collection state from outcome-blind validated salvage."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.regime_a import (  # noqa: E402
    AtomicTrajectoryStore,
    COMPLETE_STATE,
    HashChainLedger,
    RegimeAError,
    sha256_file,
)


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--original-runtime", type=Path, required=True)
    parser.add_argument("--amended-runtime", type=Path, required=True)
    args = parser.parse_args()
    specs = read_jsonl(args.manifest)
    by_id = {str(row["trajectory_spec_id"]): row for row in specs}
    replay = json.loads(args.replay.read_text())
    if (
        replay.get("pass") is not True
        or replay.get("scientific_capture_salvage_classification")
        != "EXISTING_SCIENTIFIC_CAPTURE_SALVAGE_VALID"
        or replay.get("t01_t03_serialized_activations_reusable") is not True
        or replay.get("scientific_outcomes_computed") != 0
    ):
        raise RegimeAError("scientific salvage replay is not qualified")
    amended = args.amended_runtime.resolve()
    if amended == ROOT.resolve() or ROOT.resolve() in amended.parents:
        raise RegimeAError("amended runtime must be outside repository")
    receipt_path = amended / "salvage_bootstrap_receipt.json"
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if (
            receipt.get("amended_manifest_sha256") != sha256_file(args.manifest)
            or receipt.get("scientific_replay_sha256") != sha256_file(args.replay)
        ):
            raise RegimeAError("existing salvage bootstrap belongs to another authority")
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    amended.mkdir(parents=True, exist_ok=True)
    ledger = HashChainLedger(amended / "progress_ledger.jsonl")
    if ledger.records:
        raise RegimeAError("amended ledger exists without bootstrap receipt")
    salvaged = []
    for index in range(1, 4):
        identity = f"regime_a_v2_t{index:02d}"
        spec = by_id[identity]
        original = args.original_runtime / "trajectories" / identity
        durable = original / "durable_receipt.json"
        completion = original / "completion.json"
        if not durable.is_file() or not completion.is_file():
            raise RegimeAError(f"{identity}: original durable final is incomplete")
        durable_doc = json.loads(durable.read_text())
        if durable_doc.get("status") != "VERIFIED_DURABLE":
            raise RegimeAError(f"{identity}: original durable receipt is not verified")
        common = {
            "spec_hash": spec["spec_hash"],
            "original_v2_spec_hash": spec["original_v2_spec_hash"],
            "raw_capture_spec_hash": spec["raw_capture_spec_hash"],
            "salvaged_without_recapture": True,
        }
        ledger.append(identity, "PLANNED", seed=int(spec["seed"]), retry_same_spec=False, **common)
        ledger.append(identity, "RUNNING", seed=int(spec["seed"]), retry_same_spec=False, **common)
        ledger.append(identity, "CAPTURED", reused_original_raw_capture=True, **common)
        ledger.append(
            identity,
            "VALIDATED",
            reused_original_serialized_activations=True,
            original_completion_sha256=sha256_file(completion),
            **common,
        )
        ledger.append(
            identity,
            "DURABLE",
            reused_original_durable_receipt=True,
            original_durable_receipt_sha256=sha256_file(durable),
            original_durable_prefix=durable_doc["durable_prefix"],
            original_durable_object_count=int(durable_doc["object_count_excluding_receipt"]) + 1,
            **common,
        )
        ledger.append(identity, COMPLETE_STATE, **common)
        salvaged.append(
            {
                "trajectory_spec_id": identity,
                "original_final_path": str(original),
                "original_completion_sha256": sha256_file(completion),
                "original_durable_receipt_sha256": sha256_file(durable),
                "amended_spec_hash": spec["spec_hash"],
                "raw_capture_spec_hash": spec["raw_capture_spec_hash"],
                "raw_recaptured": False,
                "activation_reextracted": False,
            }
        )
    t04 = by_id["regime_a_v2_t04"]
    original_partial = (
        args.original_runtime
        / "trajectories"
        / f".regime_a_v2_t04.{str(t04['raw_capture_spec_hash'])[:16]}.partial"
    )
    if not original_partial.is_dir():
        raise RegimeAError("original t04 raw partial is absent")
    store = AtomicTrajectoryStore(amended / "trajectories")
    amended_partial = store.begin("regime_a_v2_t04", str(t04["spec_hash"]))
    shutil.copytree(original_partial / "raw", amended_partial / "raw")
    original_files = sorted(path for path in (original_partial / "raw").rglob("*") if path.is_file())
    copied_files = sorted(path for path in (amended_partial / "raw").rglob("*") if path.is_file())
    if [path.relative_to(original_partial / "raw") for path in original_files] != [
        path.relative_to(amended_partial / "raw") for path in copied_files
    ] or any(
        sha256_file(left) != sha256_file(right)
        for left, right in zip(original_files, copied_files, strict=True)
    ):
        raise RegimeAError("t04 amended raw copy differs from original bytes")
    common_t04 = {
        "spec_hash": t04["spec_hash"],
        "original_v2_spec_hash": t04["original_v2_spec_hash"],
        "raw_capture_spec_hash": t04["raw_capture_spec_hash"],
        "salvaged_raw_capture": True,
    }
    ledger.append(
        "regime_a_v2_t04",
        "PLANNED",
        seed=int(t04["seed"]),
        retry_same_spec=False,
        **common_t04,
    )
    ledger.append(
        "regime_a_v2_t04",
        "RUNNING",
        seed=int(t04["seed"]),
        retry_same_spec=False,
        **common_t04,
    )
    receipt = {
        "schema_version": "regime-a-v2-amendment-1-salvage-bootstrap-v1.0",
        "status": "EXISTING_SCIENTIFIC_CAPTURE_SALVAGE_VALID",
        "amended_manifest_sha256": sha256_file(args.manifest),
        "scientific_replay_sha256": sha256_file(args.replay),
        "original_runtime": str(args.original_runtime.resolve()),
        "amended_runtime": str(amended),
        "t01_t03": salvaged,
        "t04": {
            "trajectory_spec_id": "regime_a_v2_t04",
            "original_partial": str(original_partial),
            "amended_partial": str(amended_partial),
            "copied_raw_file_count": len(copied_files),
            "raw_bytes_identical": True,
            "raw_recaptured": False,
        },
        "recaptures": 0,
        "replacement_trajectories": 0,
        "scientific_outcomes_computed": 0,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RegimeAError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"REGIME_A_AMENDMENT_BOOTSTRAP_REFUSAL: {exc}", file=sys.stderr)
        raise SystemExit(2)
