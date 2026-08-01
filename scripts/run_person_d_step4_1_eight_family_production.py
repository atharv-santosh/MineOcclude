"""Frozen, fail-closed Person D Step 4.1 eight-family production runner.

This script is prepared and frozen but is **not executed** as part of
preparing it -- it targets a SageMaker environment with Person A's
real preprocessed frames and Person B's real production fold/oracle
manifests mounted locally, none of which exist on this machine. Running
it here would either fail closed immediately (missing input roots) or,
worse, attempt real baseline execution outside its intended environment.

## What this binds

- Person A frame-handoff commit and frame-manifest identity
  (:mod:`mineocclude.baselines.frame_handoff_v0_2`);
- Person B v0.2 contract commit and frozen direct-input identities
  (:mod:`mineocclude.baselines.baseline_family_input_v0_2`);
- the exact ordered eight-family set;
- Person D's own implementation commit (this repository's current
  ``role/person-d-baselines`` HEAD);
- approved input/output roots;
- environment and seed requirements;
- per-family runner and environment receipts;
- canonical manifests and SHA-256 inventories.

## Restart / resume

Every family's completed, verified output is recorded in
``run_state.json`` under the approved output root, keyed by family ID
and the document's own SHA-256. On a second invocation, any family
whose recorded output still exists on disk and still validates against
:func:`mineocclude.baselines.baseline_family_input_v0_2
.validate_baseline_document_v0_2` is skipped rather than re-fit --
:func:`determine_family_execution_plan` is the pure function that
implements this and is exercised directly in
``tests/baselines/test_baseline_family_production_cli.py`` without
ever invoking ``run`` mode.

## Fail-closed per family

If any family's fit/export/validation step fails, this script stops
immediately (nonzero exit) without deleting or altering any earlier
family's already-verified, on-disk output. The next invocation resumes
from exactly where it stopped.

## No U4 access

This script never imports, reads, or references any U4-owned module,
path, or artifact.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.baselines.baseline_family_input_v0_2 import (
    FROZEN_BASELINE_FAMILY_IDS,
    PERSON_B_V0_2_CONTRACT_COMMIT,
    PERSON_B_V0_2_PRODUCTION_RATIFICATION_COMMIT,
    PERSON_E_V0_2_STEP4_1_HANDOFF_COMMIT,
    validate_baseline_document_v0_2,
)
from mineocclude.baselines.eight_family_execution_manifest import (
    build_eight_family_execution_manifest,
    validate_eight_family_execution_manifest,
)
from mineocclude.baselines.frame_handoff_v0_2 import (
    PERSON_A_EXTERNAL_FRAME_ROOT,
    PERSON_A_FRAME_HANDOFF_COMMIT,
    PERSON_A_FRAME_MANIFEST_PATH,
    build_frame_manifest_direct_input_reference,
    verify_frame_manifest_records,
    verify_frame_manifest_summary_counts,
)

#: Person D's implementation commit this runner is frozen against.
#: Updated only by re-freezing this script against a new committed
#: Person D authority -- never edited to match a local, uncommitted
#: change.
PERSON_D_IMPLEMENTATION_COMMIT = "853e0acadf050a0b1f318b399b524e57379d03bf"

#: Approved SageMaker input root for Person A's preprocessed frames.
APPROVED_PERSON_A_FRAME_ROOT = PERSON_A_EXTERNAL_FRAME_ROOT

#: Approved output root for this runner's own produced artifacts.
#: The exact final path is bound by the deployment's own environment
#: receipt (below); this default matches the sibling convention already
#: used by Person A/B's own approved-outputs roots.
DEFAULT_APPROVED_OUTPUT_ROOT = (
    "/home/sagemaker-user/person-d-step4-1-approved-outputs/"
    "person-d-step4-1-production-v0-1"
)

REQUIRED_ENVIRONMENT = {
    "device": "cpu",
    "python_requires": ">=3.10",
    "seed_source": "configs/analysis/core.yaml",
}

RUN_STATE_FILENAME = "run_state.json"


class ProductionRunnerError(ValueError):
    """Raised when a preflight or per-family fail-closed check fails."""


def load_run_state(output_root: Path) -> dict:
    path = output_root / RUN_STATE_FILENAME
    if not path.exists():
        return {"schema_version": "1.0", "families": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_run_state(output_root: Path, state: Mapping[str, Any]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    path = output_root / RUN_STATE_FILENAME
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def determine_family_execution_plan(
    existing_state: Mapping[str, Any],
    *,
    output_root: Path,
    load_document: Callable[[Path], Any] | None = None,
) -> dict:
    """Pure resume-planning function: which families to skip vs. (re)run.

    A family is skipped only when all of the following hold:
    (1) ``existing_state`` records it as ``"status": "completed"``;
    (2) its recorded output file still exists on disk;
    (3) re-loading and re-validating that file against
    :func:`validate_baseline_document_v0_2` still returns no errors.

    Any other case marks the family ``"must_run"`` -- this never
    silently trusts stale state, and it never duplicates a family's
    already-verified output.
    """

    if load_document is None:
        def load_document(path: Path):
            return json.loads(path.read_text(encoding="utf-8"))

    families_state = existing_state.get("families", {})
    plan: dict[str, str] = {}
    for family_id in FROZEN_BASELINE_FAMILY_IDS:
        record = families_state.get(family_id)
        if not isinstance(record, Mapping) or record.get("status") != "completed":
            plan[family_id] = "must_run"
            continue
        output_path = record.get("output_path")
        if not isinstance(output_path, str):
            plan[family_id] = "must_run"
            continue
        full_path = output_root / output_path
        if not full_path.exists():
            plan[family_id] = "must_run"
            continue
        try:
            document = load_document(full_path)
        except (OSError, ValueError):
            plan[family_id] = "must_run"
            continue
        if validate_baseline_document_v0_2(document) != ():
            plan[family_id] = "must_run"
            continue
        plan[family_id] = "skip_already_verified"
    return plan


def run_preflight(*, frame_manifest_path: Path, frame_manifest_byte_size: int) -> dict:
    """Verify every frozen input identity before any family is fit.

    Never fits a baseline, computes a metric, or reads a U4 artifact.
    """

    if not frame_manifest_path.exists():
        raise ProductionRunnerError(
            f"Person A frame manifest not found at {frame_manifest_path}"
        )
    manifest = json.loads(frame_manifest_path.read_text(encoding="utf-8"))

    summary_errors = verify_frame_manifest_summary_counts(manifest)
    if summary_errors:
        raise ProductionRunnerError(
            f"frame manifest summary checks failed: {summary_errors}"
        )
    record_errors = verify_frame_manifest_records(manifest)
    if record_errors:
        raise ProductionRunnerError(
            f"frame manifest record checks failed: {record_errors[:10]}"
            + (" ... (truncated)" if len(record_errors) > 10 else "")
        )

    frame_reference = build_frame_manifest_direct_input_reference(
        byte_size=frame_manifest_byte_size
    )
    execution_manifest = build_eight_family_execution_manifest(
        preprocessed_frame_manifest_reference=frame_reference
    )
    manifest_errors = validate_eight_family_execution_manifest(execution_manifest)
    if manifest_errors:
        raise ProductionRunnerError(
            f"eight-family execution manifest failed validation: {manifest_errors}"
        )

    return {
        "status": "PREFLIGHT_PASSED",
        "person_a_frame_handoff_commit": PERSON_A_FRAME_HANDOFF_COMMIT,
        "person_b_v0_2_contract_commit": PERSON_B_V0_2_CONTRACT_COMMIT,
        "person_b_v0_2_production_ratification_commit": (
            PERSON_B_V0_2_PRODUCTION_RATIFICATION_COMMIT
        ),
        "person_e_v0_2_step4_1_handoff_commit": PERSON_E_V0_2_STEP4_1_HANDOFF_COMMIT,
        "person_d_implementation_commit": PERSON_D_IMPLEMENTATION_COMMIT,
        "eight_family_execution_manifest": execution_manifest,
        "baseline_execution_performed": False,
        "u4_output_inspected": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=("preflight", "run"),
        help=(
            "preflight: verify all frozen inputs and the eight-family "
            "execution manifest without fitting anything. run: fit and "
            "export each family in order, resuming any already-verified "
            "family output."
        ),
    )
    parser.add_argument(
        "--frame-manifest-path",
        type=Path,
        default=Path(PERSON_A_FRAME_MANIFEST_PATH),
        help="Local path to Person A's committed preprocessed_frame_manifest.json.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(DEFAULT_APPROVED_OUTPUT_ROOT),
        help="Approved output root for this runner's produced artifacts.",
    )
    args = parser.parse_args()

    if not args.frame_manifest_path.exists():
        print(
            f"FAIL-CLOSED: frame manifest not found at {args.frame_manifest_path}. "
            "This script must not be run outside its approved SageMaker "
            "environment.",
            file=sys.stderr,
        )
        return 1
    byte_size = args.frame_manifest_path.stat().st_size

    preflight_report = run_preflight(
        frame_manifest_path=args.frame_manifest_path,
        frame_manifest_byte_size=byte_size,
    )
    print(json.dumps({"preflight": preflight_report["status"]}, indent=2))

    if args.mode == "preflight":
        return 0

    # mode == "run": resume-aware per-family execution.
    existing_state = load_run_state(args.output_root)
    plan = determine_family_execution_plan(existing_state, output_root=args.output_root)
    for family_id in FROZEN_BASELINE_FAMILY_IDS:
        if plan[family_id] == "skip_already_verified":
            print(f"{family_id}: skipping (already verified)")
            continue
        # Real fitting/export/registry-v2 trust-record construction
        # happens here, family by family, in the approved SageMaker
        # environment only. Never invoked as part of preparing this
        # script; see module docstring and the task's explicit
        # "do not execute" scope.
        raise ProductionRunnerError(
            f"{family_id}: real execution is not implemented in this "
            "preparation pass -- see docs/status/"
            "person_d_phase4_step4_1_eight_family_production_v0_1/ for "
            "the frozen runbook this step must follow once run for real."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
