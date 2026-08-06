"""Build the Person A Step 6.7 certification and Step 6.8 closeout package.

This command reads only committed receipts. It certifies the already-executed
ten-pilot expansion rather than re-extracting it, and it classifies every
pilot-phase engineering change before the 66-trajectory queue opens.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from mineocclude.experiments.pilot_certification import (  # noqa: E402
    ChangeClass,
    PilotChange,
    build_pilot_closeout,
    certify_ten_pilot_expansion,
    forecast_queue,
)

SESSION_ROOT = (
    ROOT
    / "docs"
    / "status"
    / "phase6_runtime"
    / "person-a-phase6-ten-pilot-expansion-seed-20260725"
)
FOLD_MANIFEST = (
    ROOT
    / "data"
    / "handoff_a"
    / "person_b_ten_pilot_fold_manifest_v0_1"
    / "ten_pilot_frame_fold_manifest.json"
)
LOCKED_CONTRACT = (
    ROOT / "docs" / "contracts" / "person_a_locked_extraction_contract_v1_0.md"
)
OUTPUT_ROOT = (
    ROOT / "docs" / "status" / "person_a_phase6_closeout_v0_1"
)

# Every engineering change made while the pilot path was being proven. The
# classification vocabulary is frozen by Step 6.8; a scientific change would
# require mentor/PI approval and a new run identity, and none is claimed here.
PILOT_CHANGES = (
    PilotChange(
        change_id="A6-C01",
        summary=(
            "Extend the activation store to carry global Phase 6 frame identity "
            "so an activation row joins one legal source frame."
        ),
        classification=ChangeClass.INTERFACE_MIGRATION,
        commit="a5841be",
        review="person_a_internal_plus_person_b_consumer_reratification",
    ),
    PilotChange(
        change_id="A6-C02",
        summary=(
            "Bind the SageMaker runtime identity and deterministic seed 20260725 "
            "to every Phase 6 extraction session."
        ),
        classification=ChangeClass.OPERATIONAL_IMPROVEMENT,
        commit="5cbb421",
        review="person_a_internal",
    ),
    PilotChange(
        change_id="A6-C03",
        summary=(
            "Repair the Phase 6 configuration path and add a Step 6.3 resume "
            "entry point after an interrupted context-alignment stage."
        ),
        classification=ChangeClass.DEFECT_CORRECTION,
        commit="5a4a42f",
        review="person_a_internal",
    ),
    PilotChange(
        change_id="A6-C04",
        summary=(
            "Parameterize the canonical pilot launcher so multiple layouts run "
            "from one immutable queue without editing the runner."
        ),
        classification=ChangeClass.OPERATIONAL_IMPROVEMENT,
        commit="65fa575",
        review="person_a_internal",
    ),
    PilotChange(
        change_id="A6-C05",
        summary=(
            "Add the ten-pilot expansion runner that reuses the existing "
            "checksum-valid pilot instead of re-extracting it."
        ),
        classification=ChangeClass.OPERATIONAL_IMPROVEMENT,
        commit="c099fe9",
        review="person_b_expansion_authorization_a838c97",
    ),
    PilotChange(
        change_id="A6-C06",
        summary=(
            "Recover from host OOM, a missing libGL runtime dependency, and an "
            "existing-output-root preflight rejection during the expansion."
        ),
        classification=ChangeClass.OPERATIONAL_IMPROVEMENT,
        commit="55776dc",
        review="person_a_internal_operational_retry_receipt",
    ),
)

REMAINING_BLOCKERS: tuple[dict[str, object], ...] = ()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, document: object) -> str:
    payload = json.dumps(document, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate without writing the package",
    )
    args = parser.parse_args()

    fold_manifest = json.loads(FOLD_MANIFEST.read_text(encoding="utf-8"))
    certification = certify_ten_pilot_expansion(
        SESSION_ROOT,
        downstream_fold_manifest=fold_manifest,
    )
    certification["downstream_fold_manifest_sha256"] = _sha256_file(FOLD_MANIFEST)
    certification["forecast"] = forecast_queue(
        certification["benchmark"],
        trajectory_count=66,
    )

    closeout = build_pilot_closeout(
        certification,
        PILOT_CHANGES,
        locked_contract_path=LOCKED_CONTRACT.relative_to(ROOT).as_posix(),
        locked_contract_sha256=_sha256_file(LOCKED_CONTRACT),
        remaining_blockers=REMAINING_BLOCKERS,
    )

    if args.check:
        print(
            json.dumps(
                {
                    "step_6_7": certification["status"],
                    "step_6_8": closeout["status"],
                    "activation_rows": certification["cardinality"][
                        "total_activation_row_count"
                    ],
                    "chunks": certification["cardinality"]["total_chunk_count"],
                },
                indent=2,
            )
        )
        return 0

    certification_hash = _write_json(
        OUTPUT_ROOT / "step_6_7_certification.json", certification
    )
    closeout_hash = _write_json(
        OUTPUT_ROOT / "step_6_8_closeout.json", closeout
    )
    inventory = {
        "schema_version": "person-a-phase6-closeout-inventory-v0.1",
        "files": {
            "step_6_7_certification.json": certification_hash,
            "step_6_8_closeout.json": closeout_hash,
        },
        "locked_contract": {
            "path": LOCKED_CONTRACT.relative_to(ROOT).as_posix(),
            "sha256": _sha256_file(LOCKED_CONTRACT),
        },
        "downstream_fold_manifest": {
            "path": FOLD_MANIFEST.relative_to(ROOT).as_posix(),
            "sha256": _sha256_file(FOLD_MANIFEST),
        },
    }
    _write_json(OUTPUT_ROOT / "sha256_inventory.json", inventory)
    print(f"wrote {OUTPUT_ROOT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
