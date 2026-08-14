"""Run Step 4.3's real no-wall positive-control gate on the 66-cell universe.

The Step 6.4 preliminary report has, until now, honestly reported
``visible_positive_control`` as blocked -- not because real no-wall data
didn't exist (351 real ``no_wall_visible_control`` rows are already in
the real 66-cell execution universe), but because no gate had actually
been run and registered against them. It couldn't be: Person B's real
66-cell pre-activation fold manifest uses a later real schema
(``artifact_type="person_b_66_cell_fold_manifest"``) that
``mineocclude.baselines.export.attach_b_fold_assignments`` was never
extended to recognize, and its layout-to-fold assignment is
structurally unreproducible by recomputing from admitted-row counts
alone (every layout is deliberately balanced to exactly 164 admitted
rows).
``mineocclude.baselines.preactivation_fold_manifest_66_cell_v0_1`` closes
that gap by reusing Person B's own real recomputation basis (the full
2,468-row set, not just the 984 admitted), verified to reproduce the
real declared assignment exactly.

This script consumes only real, byte-verified bytes: Person B's real
row-universe/oracle-target records (``role/person-b-analysis@25e09cb6``)
and Person B's real 66-cell pre-activation fold manifest
(``role/person-b-analysis@3678cc9``).

Usage:

    python scripts/run_person_d_step4_3_real_positive_control_gate.py \\
        --authority-root <DIR WITH row_universe_records.jsonl,
                           oracle_target_records.jsonl, AND
                           fold_manifest.json> \\
        --output-root docs/status/person_d_66_cell_production_baselines_v0_1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from mineocclude.baselines import production_universe_66_cell_v0_1 as pu66
from mineocclude.baselines.positive_control_gate import (
    REAL_NO_WALL_DATA_PROVENANCE,
    PositiveControlGateError,
    evaluate_no_wall_positive_control_gate,
)
from mineocclude.baselines.preactivation_fold_manifest_66_cell_v0_1 import (
    FROZEN_FOLD_MANIFEST_SHA256,
    PERSON_B_PREACTIVATION_COMMIT,
    attach_66_cell_fold_assignments,
    validate_66_cell_fold_manifest_bytes,
)

RUN_ID = "person-d-step4-3-real-positive-control-gate-v0-1"


def _write(output_root: Path, name: str, text: str) -> str:
    path = output_root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run(authority_root: Path, output_root: Path) -> dict[str, Any]:
    row_universe = pu66.load_verified_jsonl(
        authority_root / "row_universe_records.jsonl", pu66.PERSON_B_ROW_UNIVERSE_RECORDS_SHA256
    )
    oracle_targets = pu66.load_verified_jsonl(
        authority_root / "oracle_target_records.jsonl",
        pu66.PERSON_B_ORACLE_TARGET_RECORDS_SHA256,
    )
    universe = pu66.build_execution_universe(row_universe=row_universe, oracle_targets=oracle_targets)

    fold_manifest_payload = (authority_root / "fold_manifest.json").read_bytes()
    fold_manifest = validate_66_cell_fold_manifest_bytes(fold_manifest_payload)
    if hashlib.sha256(fold_manifest_payload).hexdigest() != FROZEN_FOLD_MANIFEST_SHA256:
        raise RuntimeError("fold manifest byte identity changed since this script was written")

    no_wall_ids = {
        row["trajectory_id"] for row in row_universe if row.get("control_type") == "no_wall_visible_control"
    }
    no_wall_contexts = [ctx for ctx in universe.contexts if ctx.trajectory_id in no_wall_ids]

    try:
        finding = evaluate_no_wall_positive_control_gate(
            no_wall_contexts,
            universe.mu_oracle_by_key,
            fold_manifest=fold_manifest,
            data_provenance=REAL_NO_WALL_DATA_PROVENANCE,
            attach_fold_assignments=attach_66_cell_fold_assignments,
        )
    except PositiveControlGateError as error:
        raise RuntimeError(f"Step 4.3 gate could not be evaluated: {error}") from error

    document = {
        "schema_id": "person-d-step4-3-real-positive-control-gate-v0-1",
        "schema_version": "1.0",
        "producer_role": "person_d",
        "run_id": RUN_ID,
        "evidence_kind": "real",
        "source_authorities": {
            "person_b_66_cell_oracle_target_commit": pu66.PERSON_B_66_CELL_COMMIT,
            "person_b_66_cell_preactivation_commit": PERSON_B_PREACTIVATION_COMMIT,
            "fold_manifest_sha256": FROZEN_FOLD_MANIFEST_SHA256,
        },
        "no_wall_row_count": len(no_wall_contexts),
        "finding": {k: v for k, v in asdict(finding).items()},
    }
    inventory = {
        "schema_id": "person-d-step4-3-real-positive-control-gate-inventory-v0-1",
        "schema_version": "1.0",
        "evidence_kind": "real",
        "artifact_sha256": {
            "step4_3_positive_control_gate.json": _write(
                output_root,
                "step4_3_positive_control_gate.json",
                json.dumps(document, indent=2, sort_keys=True) + "\n",
            )
        },
    }
    _write(
        output_root,
        "sha256_inventory_step4_3.json",
        json.dumps(inventory, indent=2, sort_keys=True) + "\n",
    )
    return document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authority-root", required=True, type=Path)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "docs" / "status" / "person_d_66_cell_production_baselines_v0_1",
    )
    args = parser.parse_args(argv)

    document = run(args.authority_root, args.output_root)
    finding = document["finding"]
    print(f"status={finding['status']} r2={finding['r2']} ci=[{finding['ci_low']}, {finding['ci_high']}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
