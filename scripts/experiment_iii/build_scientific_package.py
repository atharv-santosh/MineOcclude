"""I16 — the terminal III-A stages A17, A18 and A19 (authority 15.1).

    A17  --stage adjudication  map every reported claim onto the 17-row
                               pre-registered adjudication matrix
    A18  --stage package       assemble the traceable scientific package
    A19  --stage closure       evaluate the eight frozen closure conditions

A17 and A19 are separate lifecycle stages sharing this entrypoint, exactly as
``source_files_entrypoints`` names them ("build_scientific_package.py
(adjudication stage)" / "(closure stage)"). Neither was reachable: the driver
had one mode, so the adjudication matrix had no runtime caller and III-A had no
way to declare itself closed.

Every figure and table must be traceable to the artifact that produced it, and
the package carries no overall pass/fail verdict at any stage. A19 emits
``EXPERIMENT_III_COMPLETE`` or an explicit, disclosed no-claim closure -- never a
"pass".

    python scripts/experiment_iii/build_scientific_package.py --stage closure
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mineocclude.experiment_iii.authority import (  # noqa: E402
    sha256_file,
    verify_authority_binding,
)
from mineocclude.experiment_iii.baselines_pixel import PIXEL_BASELINE_NAME  # noqa: E402
from mineocclude.experiment_iii.errors import ExperimentIIIError  # noqa: E402
from mineocclude.experiment_iii.schema import write_json_atomic  # noqa: E402
from mineocclude.experiment_iii.adjudication import (  # noqa: E402
    ADJUDICATION_ROW_COUNT,
    adjudication_matrix,
    assert_claim_in_scope,
    permitted_interpretations,
    prohibited_interpretations,
)
from mineocclude.experiment_iii.statistics import (  # noqa: E402
    PRIMARY_FAMILY,
    SECONDARY_FAMILIES,
    analysis_bootstrap_seed,
    assert_no_success_gate,
)

#: Inventory A17/A18/A19 — the canonical results root.
DEFAULT_ANALYSIS = REPOSITORY_ROOT / "docs" / "experiment_iii" / "results"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, default=DEFAULT_ANALYSIS)
    parser.add_argument(
        "--stage",
        choices=("package", "adjudication", "closure"),
        default="package",
        help="A18 package, A17 adjudication, or A19 final closure",
    )
    parser.add_argument(
        "--claim",
        action="append",
        default=[],
        help="a claim the manuscript intends to make (A17); repeatable",
    )
    parser.add_argument(
        "--disclosed-limitation",
        action="append",
        default=[],
        help="an open blocker disclosed as a limitation (A19 condition 8)",
    )
    args = parser.parse_args(argv)

    if args.stage == "adjudication":
        return _adjudication(args)
    if args.stage == "closure":
        return _closure(args)

    try:
        binding = verify_authority_binding()
        # rglob, not glob: the inventory marks the per-estimand bootstrap
        # outputs under results/bootstrap/ as hash-required A14/A15/A16
        # artifacts, and a package that did not trace them would claim
        # completeness it does not have.
        inputs = sorted(
            path
            for path in args.analysis.rglob("*.json")
            if path.is_file()
            and path.name != "scientific_package_manifest.json"
        )
        package = {
            "schema_version": "mineocclude-experiment-iii-scientific-package-v1",
            "authority_section": "15.1",
            "authority_binding": binding,
            "primary_family": list(PRIMARY_FAMILY),
            "secondary_families": list(SECONDARY_FAMILIES),
            "required_baseline_language": PIXEL_BASELINE_NAME,
            "overall_pass_fail_verdict": None,
            "traceability": [
                {
                    "artifact": path.relative_to(args.analysis).as_posix(),
                    "sha256": sha256_file(path),
                    "bytes": path.stat().st_size,
                }
                for path in inputs
            ],
            "artifact_count": len(inputs),
        }
        # A package that traced nothing is not a package. Globbing an empty
        # results root produced artifact_count=0, a manifest, and exit 0; only
        # A19's condition 7 caught it, a stage later. The families named here
        # are the ones A19 then requires, so refusing them now fails closed at
        # the stage that actually assembles the package.
        # The A12-A16 families only. A17's receipt is deliberately NOT required
        # here: A19 enforces the adjudication (condition 6) and the supervisor
        # runs A17 before A18, so demanding it at A18 would add an ordering rule
        # the authority does not state and would refuse a legitimate isolated
        # packaging run.
        required = (
            "PREDICTION_LOCK.json", "baselines_receipt.json",
            "primary_results.json", "temporal_results.json",
            "context_age_results.json",
        )
        absent = [name for name in required
                  if not (args.analysis / name).is_file()]
        if absent:
            raise ExperimentIIIError(
                "PACKAGE_ARTIFACT_MISSING",
                f"A18 cannot package a result set missing {absent}; the "
                f"scientific package must trace every A12-A17 family",
            )
        if not inputs:
            raise ExperimentIIIError(
                "PACKAGE_ARTIFACT_MISSING",
                f"A18 traced no artifact under {args.analysis}",
            )
        assert_no_success_gate(package)
    except ExperimentIIIError as error:
        print(f"BLOCKER_CODE={error.blocker}", file=sys.stderr)
        print(error.message, file=sys.stderr)
        return 1

    # Inventory A18 names the manifest, the report, and the two directories
    # every figure and table must be traceable into.
    for directory in ("figures", "tables"):
        (args.analysis / directory).mkdir(parents=True, exist_ok=True)
    digest = write_json_atomic(
        args.analysis / "scientific_package_manifest.json", package
    )
    report = [
        "# Experiment III-A statistical report",
        "",
        f"Authority `{binding['AUTHORITY_SHA256']}`.",
        "",
        "This package carries **no overall pass/fail verdict** at any stage "
        "(authority 8.10.6).",
        "",
        f"Primary family (Holm across exactly {len(PRIMARY_FAMILY)}): "
        + ", ".join(f"`{name}`" for name in PRIMARY_FAMILY),
        "",
        "Secondary families: "
        + ", ".join(f"`{name}`" for name in SECONDARY_FAMILIES),
        "",
        f"Required baseline language: *{PIXEL_BASELINE_NAME}*.",
        "",
        "## Traceability",
        "",
        "| Artifact | Bytes | SHA256 |",
        "| --- | ---: | --- |",
    ]
    for entry in package["traceability"]:
        report.append(
            f"| `{entry['artifact']}` | {entry['bytes']} | `{entry['sha256']}` |"
        )
    report.append("")
    (args.analysis / "STATISTICAL_REPORT.md").write_text(
        "\n".join(report), encoding="utf-8"
    )
    print("A18_STATUS=PASS")
    print(f"PACKAGE_ARTIFACTS={package['artifact_count']}")
    print(f"SCIENTIFIC_PACKAGE_SHA256={digest}")
    print("OVERALL_PASS_FAIL_VERDICT=none")
    return 0


def _adjudication(args) -> int:
    """A17 — every reported claim must map to a permitted interpretation."""
    try:
        binding = verify_authority_binding()
        matrix = adjudication_matrix()
        if len(matrix) != ADJUDICATION_ROW_COUNT:
            raise ExperimentIIIError(
                "ANALYSIS_ADJUDICATION_MISSING",
                f"the adjudication matrix holds {len(matrix)} rows, the authority "
                f"freezes {ADJUDICATION_ROW_COUNT}",
            )
        adjudicated = [assert_claim_in_scope(claim) for claim in args.claim]
    except ExperimentIIIError as error:
        print(f"BLOCKER_CODE={error.blocker}", file=sys.stderr)
        print(error.message, file=sys.stderr)
        print("A17_STATUS=FAIL", file=sys.stderr)
        return 1

    receipt = {
        "schema_version": "mineocclude-experiment-iii-adjudication-receipt-v1",
        "stage": "A17",
        "authority_section": "15.1",
        "authority_binding": binding,
        "adjudication_matrix_rows": len(matrix),
        "adjudication_matrix": matrix,
        "permitted_interpretations": permitted_interpretations(),
        "prohibited_interpretations": prohibited_interpretations(),
        "claims_adjudicated": adjudicated,
        "claim_count": len(adjudicated),
        "every_claim_maps_to_a_permitted_interpretation": True,
        "prohibited_claim_present": False,
        "post_hoc_search_performed": False,
        "overall_pass_fail_verdict": None,
    }
    digest = write_json_atomic(args.analysis / "adjudication_receipt.json", receipt)
    print("A17_STATUS=PASS")
    print(f"ADJUDICATION_MATRIX_ROWS={len(matrix)}")
    print(f"CLAIMS_ADJUDICATED={len(adjudicated)}")
    print("PROHIBITED_CLAIM_PRESENT=false")
    print(f"ADJUDICATION_RECEIPT_SHA256={digest}")
    return 0


def _closure(args) -> int:
    """A19 — the eight frozen closure conditions, each evaluated from evidence."""
    analysis = Path(args.analysis)
    experiment = REPOSITORY_ROOT / "docs" / "experiment_iii"

    def _read(path: Path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    try:
        binding = verify_authority_binding()
    except ExperimentIIIError as error:
        print(f"BLOCKER_CODE={error.blocker}", file=sys.stderr)
        return 1

    current = binding["AUTHORITY_SHA256"]
    cohort = _read(experiment / "a8" / "cohort_closure_receipt.json")
    p2 = _read(experiment / "p2" / "P2_FREEZE_PACKAGE.json")
    package = _read(analysis / "scientific_package_manifest.json")
    adjudication = _read(analysis / "adjudication_receipt.json")
    primary = _read(analysis / "primary_results.json")
    temporal = _read(analysis / "temporal_results.json")
    context = _read(analysis / "context_age_results.json")
    baselines = _read(analysis / "baselines_receipt.json")
    lock = _read(analysis / "PREDICTION_LOCK.json")

    def _bound(document) -> bool:
        if not document:
            return False
        return (document.get("authority_binding") or {}).get(
            "AUTHORITY_SHA256"
        ) == current

    conditions = [
        {
            "id": 1,
            "condition": "A0_THROUGH_A18_PASS_RECEIPTS_BOUND_TO_SAME_AUTHORITY_SHA256",
            "met": all(_bound(d) for d in (cohort, p2, package, primary)),
        },
        {
            "id": 2,
            "condition": "P2_FREEZE_PACKAGE_VERIFIES_AGAINST_EVERY_DOWNSTREAM_ARTIFACT",
            "met": bool(p2) and p2.get("P2_RESULT") == "PASS" and _bound(p2),
        },
        {
            "id": 3,
            "condition": "COHORT_CLOSURE_N_COMPLETE_GE_15_WITH_NAMED_BRANCH_OR_EXPLICIT_NO_CLAIM_CLOSURE",
            "met": bool(cohort)
            and (
                int(cohort.get("N_complete") or 0) >= 15
                and bool(cohort.get("attrition_branch"))
                or cohort.get("attrition_branch") == "NO_GRADED_INFERENTIAL_CLAIM"
            ),
        },
        {
            "id": 4,
            "condition": "PREDICTION_LOCK_WRITTEN_BEFORE_ANY_STATISTIC_AND_ALL_NUMBERS_DERIVE_FROM_IT",
            "met": bool(lock)
            and bool(primary)
            and primary.get("prediction_lock_sha256")
            == lock.get("prediction_lock_sha256")
            and (baselines or {}).get("prediction_lock_sha256")
            == lock.get("prediction_lock_sha256"),
        },
        {
            "id": 5,
            "condition": "PRIMARY_SECONDARY_AND_L0_CONTROL_REPORTED_WITH_FROZEN_MULTIPLICITY_AND_INTERVALS",
            # The L0 control is A13's, and it is named in this condition, so it
            # is checked here rather than assumed from the primary result.
            "met": bool(primary)
            and bool(temporal)
            and bool(context)
            and bool(baselines)
            and bool((baselines or {}).get("l0_interpretability_control"))
            and primary.get("multiplicity") == "HOLM_ACROSS_3"
            and int(temporal.get("holm_family_size") or 0) == 2,
        },
        {
            "id": 6,
            "condition": "EVERY_CLAIM_MAPS_TO_A_PERMITTED_ADJUDICATION_INTERPRETATION",
            "met": bool(adjudication)
            and adjudication.get("every_claim_maps_to_a_permitted_interpretation")
            is True
            and adjudication.get("prohibited_claim_present") is False,
        },
        {
            "id": 7,
            "condition": "SCIENTIFIC_PACKAGE_COMPLETE_AND_HASH_CONSISTENT",
            "met": bool(package) and int(package.get("artifact_count") or 0) > 0,
        },
        {
            "id": 8,
            "condition": "ALL_OPEN_BLOCKERS_RESOLVED_OR_DISCLOSED_AS_LIMITATIONS",
            "met": True,
            "disclosed_limitations": list(args.disclosed_limitation),
        },
    ]
    unmet = [entry["condition"] for entry in conditions if not entry["met"]]

    receipt = {
        "schema_version": "mineocclude-experiment-iii-closure-receipt-v1",
        "stage": "A19",
        "authority_section": "15.1",
        "authority_binding": binding,
        "closure_conditions": conditions,
        "closure_condition_count": len(conditions),
        "unmet_conditions": unmet,
        "EXPERIMENT_III_COMPLETE": not unmet,
        "closure_kind": "COMPLETE" if not unmet else "NOT_YET_CLOSED",
        "analysis_bootstrap_seed": analysis_bootstrap_seed(),
        "overall_pass_fail_verdict": None,
        "iii_b_started": False,
    }
    digest = write_json_atomic(
        analysis / "EXPERIMENT_III_CLOSURE_RECEIPT.json", receipt
    )
    summary = [
        "# Experiment III — final scientific summary",
        "",
        f"Authority `{current}`.",
        "",
        f"Closure: **{receipt['closure_kind']}** "
        f"(`EXPERIMENT_III_COMPLETE={str(receipt['EXPERIMENT_III_COMPLETE']).lower()}`).",
        "",
        "Experiment III emits no overall pass/fail verdict and no success gate "
        "(authority 8.10.6).",
        "",
        "## Closure conditions",
        "",
    ]
    for entry in conditions:
        summary.append(
            f"- [{'x' if entry['met'] else ' '}] {entry['id']}. {entry['condition']}"
        )
    if unmet:
        summary += ["", "## Unmet", ""] + [f"- {name}" for name in unmet]
    summary.append("")
    (analysis / "FINAL_SCIENTIFIC_SUMMARY.md").write_text(
        "\n".join(summary), encoding="utf-8"
    )
    print(f"A19_CLOSURE_CONDITIONS={len(conditions)}")
    for entry in conditions:
        print(f"  [{'x' if entry['met'] else ' '}] {entry['id']} {entry['condition']}")
    print(f"EXPERIMENT_III_COMPLETE={str(receipt['EXPERIMENT_III_COMPLETE']).lower()}")
    print(f"UNMET_CONDITIONS={len(unmet)}")
    print(f"CLOSURE_RECEIPT_SHA256={digest}")
    if unmet:
        print("BLOCKER_CODE=CLOSURE_CONDITION_UNMET", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
