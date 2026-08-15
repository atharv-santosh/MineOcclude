"""Validate and hash-bind the completed Regime A-prime P2 package."""

from __future__ import annotations

import json
import time
from pathlib import Path

from p2_common import OUT, REPO, sha256_file, write_json


def read(name: str) -> dict:
    return json.loads((OUT / name).read_text())


def main() -> int:
    started = time.monotonic()
    for path in OUT.glob("p2_*.json"):
        json.loads(path.read_text())

    capture = read("p2_capture_manifest.json")
    path = read("p2_path_equivalence_receipt.json")
    visibility = read("p2_visibility_qualification_receipt.json")
    activation = read("p2_activation_manifest.json")
    extraction = read("p2_extraction_validation_receipt.json")
    authority = read("p2_readout_authority_receipt.json")
    best = read("p2_best_k_results.json")
    full = read("p2_full_results.json")
    final = read("p2_final_analysis_receipt.json")
    receipt = read("p2_receipt.json")
    report = (OUT / "p2_report.md").read_text()

    checks = {
        "all_machine_readable_artifacts_parse": True,
        "capture_25_of_25": capture["status"] == "PASS"
        and capture["complete_validated_durable_count"] == 25,
        "path_exact": path["path_equivalence_status"] == "PASS"
        and path["path_trajectories_pass"] == 25
        and path["path_trajectories_fail"] == 0
        and path["max_path_difference"] == 0.0,
        "visibility_exact": visibility["visibility_qualification_status"] == "PASS"
        and visibility["qualified_rendered_evidence_rows"] == 475
        and visibility["ambiguous_or_partial_rows"] == 0
        and visibility["zero_evidence_rows"] == 0,
        "extraction_valid": extraction["extraction_validation_status"] == "PASS"
        and activation["status"] == "PASS"
        and activation["run_count"] == 25
        and activation["total_activation_rows"] == 475
        and activation["layers_extracted"] == [4],
        "activation_manifest_hash_authorized": sha256_file(
            OUT / "p2_activation_manifest.json"
        ) == "35b15e96e31962ebc6d15ca3c101b1278e10d877536fb8c9084d0d722949b93c",
        "readout_authority_bound_before_scoring": authority["status"]
        == "BOUND_BEFORE_P2_SCORING",
        "best_k_qualified": best["qualification_status"] == "PASS"
        and all(best["qualification_checks"].values()),
        "full_qualified": full["qualification_status"] == "PASS"
        and all(full["qualification_checks"].values()),
        "decision_exact": final["p2_decision"] == "GO_BEST_K_FULL_VISIBLE"
        and receipt["p2_decision"] == "GO_BEST_K_FULL_VISIBLE",
        "p3_allowed_not_started": final["p3_allowed"] is True
        and final["p3_started"] is False
        and receipt["p3_allowed"] is True
        and receipt["p3_started"] is False,
        "confirmatory_collection_not_authorized": final[
            "REGIME_A_PRIME_COLLECTION_AUTHORIZED"
        ] == "NO" and receipt["REGIME_A_PRIME_COLLECTION_AUTHORIZED"] == "NO",
        "historical_comparison_narrowed": final["historical_comparison"]
        == "DESCRIPTIVE_CROSS_APPARATUS_CONTEXT_ONLY",
        "classification_nonconfirmatory": best["classification"]
        == "EXPLORATORY_MATCHED_DIAGNOSTIC"
        and full["classification"] == "EXPLORATORY_MATCHED_DIAGNOSTIC",
        "report_matches_best_k": all(
            f"{best['visible_metrics'][key]:.6f}" in report
            for key in ("rmse_blocks", "mae_blocks", "macro_r2")
        ),
        "report_matches_full": all(
            f"{full['visible_metrics'][key]:.6f}" in report
            for key in ("rmse_blocks", "mae_blocks", "macro_r2")
        ),
        "report_decision_exact": "P2_DECISION=GO_BEST_K_FULL_VISIBLE" in report,
        "report_interpretation_bounded": all(text in report for text in (
            "current-apparatus visible-readout qualification",
            "does not establish hidden-state decoding",
            "DESCRIPTIVE_CROSS_APPARATUS_CONTEXT_ONLY",
        )),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"P2 closeout validation failed: {failed}")

    artifacts = [
        "p2_capture_manifest.json",
        "p2_path_equivalence_receipt.json",
        "p2_visibility_qualification_receipt.json",
        "p2_activation_manifest.json",
        "p2_extraction_validation_receipt.json",
        "p2_readout_authority_receipt.json",
        "p2_best_k_results.json",
        "p2_full_results.json",
        "p2_final_analysis_receipt.json",
        "p2_report.md",
    ]
    closeout = {
        "artifact_id": "regime-a-prime-p2-closeout-v0.1",
        "schema_version": "1.0",
        "phase": "P2_CLOSEOUT",
        "status": "PASS",
        "classification": "EXPLORATORY_MATCHED_DIAGNOSTIC",
        "confirmatory_membership": False,
        "controlling_authorities": {
            "original_preoutcome_commit": "6943e04c114ad8be43b28be5342f7a6c0a49523f",
            "historical_renderer_blocker_commit": "af8ab21087a1b4d08514721d19762ca2a00d4ed5",
            "narrowed_role_supersession_commit": "76a2e7fdf6db02816a9df5d07dea33792bbeca86",
            "patch_acceptance_supersession": "p2_patch_acceptance_supersession.json",
            "readout_authority": "p2_preoutcome_authority.json",
        },
        "capture_cohort": {
            "scene": "NO_WALL",
            "source_spec_count": 25,
            "run_count": 25,
            "complete_validated_durable": 25,
            "retries": 0,
            "confirmatory_membership": False,
        },
        "artifact_sha256": {name: sha256_file(OUT / name) for name in artifacts},
        "checks": checks,
        "checks_failed": 0,
        "p2_final_status": "PASS_CURRENT_APPARATUS_VISIBLE_READOUT_QUALIFICATION",
        "p2_role": "CURRENT_APPARATUS_VISIBLE_READOUT_QUALIFICATION_AT_MATCHED_PHYSICAL_PATHS",
        "best_k_qualification_status": "PASS",
        "full_qualification_status": "PASS",
        "p2_decision": "GO_BEST_K_FULL_VISIBLE",
        "p3_allowed": True,
        "p3_started": False,
        "REGIME_A_PRIME_COLLECTION_AUTHORIZED": "NO",
        "contamination_detected": False,
        "historical_comparison": "DESCRIPTIVE_CROSS_APPARATUS_CONTEXT_ONLY",
        "interpretation_boundary": {
            "establishes": "visible-position recovery on the current qualified apparatus at matched physical paths/times",
            "does_not_establish": [
                "hidden-state decoding",
                "object permanence",
                "memory",
                "belief",
                "historical pixel causality",
                "confirmatory Regime A-prime success",
                "rescue of closed Regime A",
            ],
        },
        "validation_runtime_seconds": time.monotonic() - started,
    }
    digest = write_json(OUT / "p2_closeout_receipt.json", closeout)
    print("P2_CLOSEOUT_VALIDATION_STATUS=PASS")
    print(f"P2_CLOSEOUT_RECEIPT_SHA256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
