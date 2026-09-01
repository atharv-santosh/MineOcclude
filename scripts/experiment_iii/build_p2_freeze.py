"""A6 — build ``docs/experiment_iii/p2/P2_FREEZE_PACKAGE.json`` and its hash.

The frozen lifecycle names this file as A6's ``source_files_entrypoints``, and
``EXPECTED_ARTIFACT_INVENTORY.json`` names it as the producer of both P2
artifacts. It is deliberately thin: every binding decision lives in
:mod:`mineocclude.experiment_iii.p2_freeze`, so the freeze logic is importable
and testable rather than trapped in a CLI.

    python scripts/experiment_iii/build_p2_freeze.py \\
        --extraction-host-a3 docs/experiment_iii/receipts/environment_receipt_gpu_extraction_host.json

Fails closed. Authority 6/A6 forbids freezing with a placeholder, a null or a
"to be determined", so a refused binding exits non-zero with its frozen blocker
code and writes nothing at all — no partial package, and in particular no
``PRODUCTION_AUTHORIZED``.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mineocclude.experiment_iii.errors import ExperimentIIIError  # noqa: E402
from mineocclude.experiment_iii.p2_freeze import (  # noqa: E402
    BINDING_GROUPS,
    build_p2_freeze_package,
    p2_freeze_passed,
    verify_p2_freeze_package,
)
from mineocclude.experiment_iii.schema import write_json_atomic  # noqa: E402
from mineocclude.experiment_iii.source_closure import source_closure  # noqa: E402

DOCS = REPOSITORY_ROOT / "docs" / "experiment_iii"
DATA = REPOSITORY_ROOT / "data" / "experiment_iii"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--aprime-port-receipt",
        type=Path,
        default=DOCS / "a1_receipts" / "aprime_port_receipt.json",
    )
    parser.add_argument(
        "--fir-recovery-receipt",
        type=Path,
        default=DOCS / "a1_receipts" / "fir_kernel_recovery_receipt.json",
    )
    parser.add_argument(
        "--implementation-completion-receipt",
        type=Path,
        default=DOCS / "a1_receipts" / "implementation_completion_receipt.json",
    )
    parser.add_argument(
        "--static-validation-receipt",
        type=Path,
        default=DOCS / "receipts" / "static_validation_receipt.json",
    )
    parser.add_argument(
        "--capture-host-a3",
        type=Path,
        default=DOCS / "receipts" / "environment_receipt_wsl2_capture_host.json",
    )
    parser.add_argument("--extraction-host-a3", type=Path, required=True)
    parser.add_argument(
        "--production-manifest",
        type=Path,
        default=DOCS / "cohort" / "production_identity_manifest.jsonl",
    )
    parser.add_argument(
        "--production-manifest-sha256",
        type=Path,
        default=DOCS / "cohort" / "production_identity_manifest.sha256",
    )
    parser.add_argument(
        "--pilot-manifest",
        type=Path,
        default=DOCS / "cohort" / "pilot_identity_manifest.jsonl",
    )
    parser.add_argument("--folds", type=Path, default=DOCS / "cohort" / "folds.json")
    parser.add_argument(
        "--priority-order",
        type=Path,
        default=DOCS / "cohort" / "identity_priority_order.json",
    )
    parser.add_argument(
        "--p0-selection-receipt",
        type=Path,
        default=DOCS / "p0" / "P0_SELECTION_RECEIPT.json",
    )
    parser.add_argument(
        "--p0-selected-ladder", type=Path, default=DOCS / "p0" / "P0_SELECTED_LADDER.json"
    )
    parser.add_argument(
        "--p0-sentinel-envelope",
        type=Path,
        default=DOCS / "p0" / "P0_SENTINEL_ENVELOPE.json",
    )
    parser.add_argument(
        "--p1-pilot-receipt", type=Path, default=DOCS / "p1" / "p1_pilot_receipt.json"
    )
    parser.add_argument(
        "--activations", type=Path, default=DATA / "p1" / "activations"
    )
    parser.add_argument("--out", type=Path, default=DOCS / "p2")
    args = parser.parse_args(argv)

    try:
        package = build_p2_freeze_package(
            source_closure=source_closure(),
            aprime_port_receipt_path=args.aprime_port_receipt,
            fir_recovery_receipt_path=args.fir_recovery_receipt,
            capture_host_a3_path=args.capture_host_a3,
            extraction_host_a3_path=args.extraction_host_a3,
            production_manifest_path=args.production_manifest,
            production_manifest_sha256_path=args.production_manifest_sha256,
            pilot_manifest_path=args.pilot_manifest,
            folds_path=args.folds,
            priority_order_path=args.priority_order,
            p0_selection_receipt_path=args.p0_selection_receipt,
            p0_selected_ladder_path=args.p0_selected_ladder,
            p0_sentinel_envelope_path=args.p0_sentinel_envelope,
            static_validation_receipt_path=args.static_validation_receipt,
            implementation_completion_receipt_path=(
                args.implementation_completion_receipt
            ),
            p1_pilot_receipt_path=args.p1_pilot_receipt,
            activations_root=args.activations,
        )
    except ExperimentIIIError as error:
        print(f"BLOCKER_CODE={error.blocker}", file=sys.stderr)
        print(error.message, file=sys.stderr)
        print("P2_RESULT=FAIL", file=sys.stderr)
        return 1

    # An independent re-check of the assembled package, before anything is
    # written and before any authorization is printed.
    audit = verify_p2_freeze_package(package)
    if not audit["passed"] or not p2_freeze_passed(package):
        print("BLOCKER_CODE=P2_BINDING_INCOMPLETE", file=sys.stderr)
        print(f"independent verification found: {audit['findings']}", file=sys.stderr)
        print("P2_RESULT=FAIL", file=sys.stderr)
        return 1

    package_path = args.out / "P2_FREEZE_PACKAGE.json"
    digest = write_json_atomic(package_path, package)
    hash_path = args.out / "P2_FREEZE_PACKAGE.sha256"
    hash_path.parent.mkdir(parents=True, exist_ok=True)
    hash_path.write_text(
        f"{package['package_sha256']}  P2_FREEZE_PACKAGE.json\n",
        encoding="utf-8",
        newline="\n",
    )

    print(f"P2_RESULT={package['P2_RESULT']}")
    print(f"P2_SCHEMA={package['schema_version']}")
    print(f"P2_BINDING_GROUPS={','.join(BINDING_GROUPS)}")
    print(f"P2_BINDING_GROUP_COUNT={package['binding_group_count']}")
    print(f"P2_VERIFICATION_CHECKS={package['verification']['check_count']}")
    print(f"P2_MISSING_BINDINGS={package['missing_bindings']}")
    print(f"P2_NULL_BINDINGS={package['null_bindings']}")
    print(f"P2_UNVERIFIED_BINDINGS={package['unverified_bindings']}")
    print(f"P2_FREEZE_PACKAGE={package_path.relative_to(REPOSITORY_ROOT).as_posix()}")
    print(f"P2_FREEZE_PACKAGE_SHA256={package['package_sha256']}")
    print(f"P2_FREEZE_PACKAGE_CANONICAL_SHA256={digest}")
    print(f"P2_FREEZE_PACKAGE_HASH_FILE={hash_path.relative_to(REPOSITORY_ROOT).as_posix()}")
    print(f"PRODUCTION_AUTHORIZED={str(package['PRODUCTION_AUTHORIZED']).lower()}")
    print(
        "MODEL_INFERENCE_AUTHORIZED="
        f"{str(package['MODEL_INFERENCE_AUTHORIZED']).lower()}"
    )
    print(f"NEXT_AUTHORIZED_STATE={package['next_authorized_state']}")
    print(f"SOURCE_CLOSURE={package['bindings']['AUTHORITY_AND_CODE']['source_closure']['source_closure_sha256']}")
    print(f"HEAD_COMMIT={package['bindings']['AUTHORITY_AND_CODE']['head_commit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
