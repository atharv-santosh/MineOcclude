"""Build the immutable Person E terminal status package.

One document set answering, for every step of the Person E execution manual
through terminal Step 7.3: what is done, what evidence proves it, whether that
evidence is real or synthetic, what remains, who owns what remains, and the
exact command that unblocks it.

Test results are supplied by the operator from an observed run rather than
invented here; the exact selection command is recorded alongside them so the
numbers can be re-derived.

Usage:
    python scripts/build_person_e_terminal_status_v0_1.py build \
        --passed 597 --failed 0 --skipped 5 --subtests-passed 637 \
        --duration-seconds 314.05
    python scripts/build_person_e_terminal_status_v0_1.py validate
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.experiments.registry import (  # noqa: E402
    formatted_json_bytes,
    hash_file_bytes,
)

PKG_REL = "docs/status/person_e_terminal_status_v0_1"
SCHEMA_VERSION = "person-e-terminal-status-v0.1"

MANUAL = {
    "title": "MineOcclude — Person E MVP Execution Manual",
    "scope": "Week 1 only, Phase 0 through Phase 7",
    "source_document": "MineOcclude_Person_E_MVP_Week_1_Only (3).docx",
    "source_document_sha256": (
        "08804f049510df03c258c63df615bd4495e9e002c85305d1360f293fb72173f0"
    ),
    "terminal_step": "7.3",
}

TEST_SELECTION = [
    "-m",
    "pytest",
    "tests/vision",
    "tests/experiments",
    "tests/operations",
    "tests/contracts/test_rollout_registry_contract.py",
    "tests/contracts/test_identity.py",
    "tests/integration/test_c_e_marker_compatibility.py",
    "tests/data/test_environment_lock.py",
    "-p",
    "no:cacheprovider",
]

#: Every manual step, its status, and the evidence a reviewer should open.
#: "real" means measured from authoritative upstream bytes. "synthetic" means
#: fixture-driven proof that an interface or workflow behaves as specified.
STEPS: list[dict[str, Any]] = [
    {
        "step": "0.1",
        "title": "Inventory existing E-related work",
        "status": "COMPLETE_AND_VERIFIED",
        "evidence_class": "real",
        "evidence": ["docs/operations/person_e_phase1_deliverable_matrix.md"],
        "remaining": None,
    },
    {
        "step": "0.2",
        "title": "Compare existing work with shared contracts",
        "status": "COMPLETE_AND_VERIFIED",
        "evidence_class": "real",
        "evidence": [
            "docs/contracts/person_e_interface_ownership_v0_1.md",
            "docs/decisions/person_e_schema_gap_proposals.md",
        ],
        "remaining": None,
    },
    {
        "step": "0.3",
        "title": "Validate, preserve, or quarantine existing artifacts",
        "status": "COMPLETE_AND_VERIFIED",
        "evidence_class": "real",
        "evidence": ["docs/operations/person_e_phase1_qa_checklist.md"],
        "remaining": None,
    },
    {
        "step": "0.4",
        "title": "Choose the resume point and freeze current status",
        "status": "COMPLETE_AND_VERIFIED",
        "evidence_class": "real",
        "evidence": ["docs/decisions/person_e_phase1_decision_log.md"],
        "remaining": None,
    },
    {
        "step": "1.1",
        "title": "Confirm the Person E interface and ownership map",
        "status": "COMPLETE_AND_VERIFIED",
        "evidence_class": "real",
        "evidence": ["docs/contracts/person_e_interface_ownership_v0_1.md"],
        "remaining": None,
    },
    {
        "step": "1.2",
        "title": "Define the immutable run and artifact contract",
        "status": "COMPLETE_AND_VERIFIED",
        "evidence_class": "synthetic",
        "evidence": [
            "docs/contracts/immutable_registry_v2.md",
            "src/mineocclude/experiments/registry.py",
            "tests/experiments/test_immutable_registry_v2_contract.py",
        ],
        "remaining": None,
    },
    {
        "step": "1.3",
        "title": "Specify vision calibration and synthetic measurement fixtures",
        "status": "COMPLETE_AND_VERIFIED",
        "evidence_class": "synthetic",
        "evidence": [
            "docs/contracts/person_e_phase1_synthetic_contracts_v1.md",
            "tests/fixtures/person_e/",
        ],
        "remaining": None,
    },
    {
        "step": "2.1",
        "title": "Register A's smoke run and C's pilot",
        "status": "COMPLETE_AND_VERIFIED",
        "evidence_class": "real",
        "evidence": [
            "docs/status/person_e_phase2_v0_1/step2_1_registry_receipt.json",
            "docs/status/person_e_phase2_v0_1/registry_query_example.json",
        ],
        "remaining": None,
    },
    {
        "step": "2.2",
        "title": "Build the calibration and held-out frame sets",
        "status": "COMPLETE_AND_VERIFIED",
        "evidence_class": "real",
        "evidence": [
            "docs/status/person_e_phase2_v0_1/frozen_split_manifest.json",
            "docs/status/person_e_phase2_v0_1/split_coverage_report.json",
        ],
        "remaining": None,
    },
    {
        "step": "2.3",
        "title": "Prototype the magenta detector",
        "status": "COMPLETE_AND_VERIFIED",
        "evidence_class": "real",
        "evidence": [
            "docs/status/person_e_phase2_v0_1/calibration_report.json",
            "docs/status/person_e_phase2_v0_1/detector_version_record.json",
            "src/mineocclude/vision/magenta.py",
        ],
        "remaining": None,
    },
    {
        "step": "2.4",
        "title": "Fit and validate the first homography",
        "status": "COMPLETE_AND_VERIFIED",
        "evidence_class": "real",
        "evidence": [
            "docs/status/person_e_phase2_step2_4_v0_4/phase2_status.json",
            "docs/status/person_e_phase2_step2_4_v0_4/localization_validation_report.json",
        ],
        "remaining": None,
    },
    {
        "step": "3.1",
        "title": "Freeze and evaluate detector v1",
        "status": "COMPLETE_AND_VERIFIED",
        "evidence_class": "real",
        "evidence": [
            "docs/status/person_e_phase3_step3_1_candidate_freeze_v0_1/",
            "docs/status/person_e_phase3_step3_1_formal_evaluation_v0_1/formal_evaluation_report.json",
        ],
        "remaining": None,
    },
    {
        "step": "3.2",
        "title": "Validate homographies across layouts and regions",
        "status": "COMPLETE_AND_VERIFIED",
        "evidence_class": "real",
        "evidence": [
            "docs/status/person_e_phase3_step3_2_homography_closure_v0_1/",
            "data/handoff_e/person_e_v0_4_homography_refit_v0_2/",
        ],
        "remaining": None,
    },
    {
        "step": "3.3",
        "title": "Integrate empirical visibility without taking C's authority",
        "status": "BLOCKED_EXTERNAL_INPUT",
        "evidence_class": "real",
        "evidence": [
            "data/handoff_c/person_e_phase3_step3_3_empirical_visibility_v0_1/",
        ],
        "remaining": (
            "Person C's final strict join and Person B's joined-package "
            "validation are both PENDING; the E-side generation interface, "
            "schema, coverage report, and receipt are READY"
        ),
    },
    {
        "step": "4.1",
        "title": "Register every workstream through direct inputs",
        "status": "PARTIALLY_COMPLETE",
        "evidence_class": "real",
        "evidence": [
            "docs/status/person_e_phase4_step4_1_registry_v2_closure_v0_1/",
            "docs/status/person_e_phase4_step4_1_slice3a_v0_1/",
            "docs/status/person_e_phase4_step4_1_final_comparison_ratification_v0_1/",
        ],
        "remaining": (
            "result-bearing workstream outputs from B and D are not yet "
            "published, so only representative and authorized artifact types "
            "are registered"
        ),
    },
    {
        "step": "4.2",
        "title": "Add fast CPU and fail-closed compatibility checks",
        "status": "COMPLETE_AND_VERIFIED",
        "evidence_class": "synthetic",
        "evidence": ["tests/", "conftest.py"],
        "remaining": None,
    },
    {
        "step": "4.3",
        "title": "Prepare result templates and the artifact index",
        "status": "COMPLETE_AND_VERIFIED",
        "evidence_class": "synthetic",
        "evidence": [
            "docs/contracts/person_e_figure_manifest_v0_1.md",
            "src/mineocclude/experiments/figure_inputs.py",
            "scripts/build_artifact_index.py",
            "scripts/trace_artifact.py",
        ],
        "remaining": None,
    },
    {
        "step": "5.1",
        "title": "Verify the preliminary result source chain",
        "status": "BLOCKED_EXTERNAL_INPUT",
        "evidence_class": "synthetic",
        "evidence": [
            "tests/experiments/test_phase1_lineage.py",
            "tests/experiments/test_phase2_registry_queries.py",
        ],
        "remaining": (
            "no Person B or Person D preliminary machine-readable result table "
            "exists to audit"
        ),
    },
    {
        "step": "5.2",
        "title": "Generate preliminary diagnostic visuals",
        "status": "IMPLEMENTED_NOT_EXECUTED",
        "evidence_class": "synthetic",
        "evidence": [
            "scripts/build_figure_input.py",
            "scripts/render_figure_svg.py",
            "tests/experiments/test_figure_renderer.py",
        ],
        "remaining": "awaiting approved real inputs from Step 5.1",
    },
    {
        "step": "5.3",
        "title": "Audit and invalidate preliminary figures correctly",
        "status": "IMPLEMENTED_NOT_EXECUTED",
        "evidence_class": "synthetic",
        "evidence": [
            "tests/fixtures/person_e/figure_supersession_scenarios_v1.json",
            "tests/experiments/test_figure_inputs.py",
        ],
        "remaining": "no real preliminary figure exists to audit",
    },
    {
        "step": "6.1",
        "title": "Validate the rollout intake and pairing contract",
        "status": "IMPLEMENTED_NOT_EXECUTED",
        "evidence_class": "synthetic",
        "evidence": [
            "src/mineocclude/vision/measurement.py",
            "src/mineocclude/contracts/rollout_registry.py",
            "tests/contracts/test_rollout_registry_contract.py",
            "tests/vision/test_measurement.py",
        ],
        "remaining": "no real rollout queue exists",
    },
    {
        "step": "6.2",
        "title": "Detect reappearance and record persistence",
        "status": "IMPLEMENTED_NOT_EXECUTED",
        "evidence_class": "synthetic",
        "evidence": [
            "scripts/localize_u4_frames.py",
            "tests/vision/test_u4_pipeline.py",
            "tests/vision/test_measurement.py",
        ],
        "remaining": "no detector-qualified real clips exist",
    },
    {
        "step": "6.3",
        "title": "Transform to world coordinates and compute signed displacement",
        "status": "IMPLEMENTED_NOT_EXECUTED",
        "evidence_class": "synthetic",
        "evidence": [
            "src/mineocclude/vision/homography.py",
            "scripts/localize_u4_frames.py",
            "tests/vision/test_homography_and_ssim.py",
        ],
        "remaining": (
            "the validated six-layout homography exists; real rollout clips and "
            "the rollout-pose geometry handoff do not"
        ),
    },
    {
        "step": "6.4",
        "title": "Compute SSIM and background-masked sensitivity",
        "status": "IMPLEMENTED_NOT_EXECUTED",
        "evidence_class": "synthetic",
        "evidence": [
            "src/mineocclude/vision/ssim.py",
            "scripts/measure_ssim.py",
            "tests/vision/test_homography_and_ssim.py",
        ],
        "remaining": (
            "config ssim_version and background_mask_margin_pixels are null and "
            "mask_status is pending_person_b_person_e_signoff"
        ),
    },
    {
        "step": "6.5",
        "title": "Publish the U4 measurement table and QA record",
        "status": "IMPLEMENTED_NOT_EXECUTED",
        "evidence_class": "synthetic",
        "evidence": [
            "scripts/measure_u4.py",
            "scripts/compose_u4_evidence.py",
            "docs/contracts/person_e_measurement_v0_1.md",
            "tests/vision/test_u4_pipeline.py",
        ],
        "remaining": "no measurement row can exist without Steps 6.1-6.4 inputs",
    },
    {
        "step": "7.1",
        "title": "Reproduce E measurement from clean inputs",
        "status": "IMPLEMENTED_NOT_EXECUTED",
        "evidence_class": "synthetic",
        "evidence": [
            "src/mineocclude/operations/clean_reproduction.py",
            "docs/status/person_e_phase7_terminal_v0_1/clean_reproduction_plan.json",
            "docs/status/person_e_phase7_terminal_v0_1/clean_reproduction_receipt.json",
        ],
        "remaining": (
            "the synthetic rehearsal passes all five stages and recovers the "
            "known answer; a real reproduction needs Person A's clean-run bundle"
        ),
    },
    {
        "step": "7.2",
        "title": "Assemble and audit checkpoint evidence",
        "status": "PARTIALLY_COMPLETE",
        "evidence_class": "real",
        "evidence": [
            "docs/status/person_e_phase7_terminal_v0_1/checkpoint_evidence.json",
        ],
        "remaining": (
            "both populated slots are real Person E planning gates; the seven "
            "U1-U4 scientific slots are explicitly empty with owners named"
        ),
    },
    {
        "step": "7.3",
        "title": "Freeze the E pipeline and complete the written handoff",
        "status": "COMPLETE_AND_VERIFIED",
        "evidence_class": "real",
        "evidence": [
            "docs/runbooks/person_e_registry_runbook.md",
            "docs/runbooks/person_e_detector_runbook.md",
            "docs/runbooks/person_e_homography_runbook.md",
            "docs/runbooks/person_e_u4_measurement_runbook.md",
            "docs/runbooks/person_e_preliminary_figures_runbook.md",
            "docs/status/person_e_phase7_terminal_v0_1/operating_handoff.json",
            "docs/status/person_e_phase7_terminal_v0_1/second_operator_receipt.json",
        ],
        "remaining": None,
    },
]

FROZEN_HASHES = {
    "person_e_successor_provenance_receipt_sha256": (
        "946a856bf704b43c13ba08ba692bda49cc2ecea4c1cc15096a35c53b31c522b3"
    ),
    "person_e_homography_provenance_completion_authority": (
        "340ecb7339fab41bd11280f52cd5a1e7be07cdf5"
    ),
    "person_e_portability_repair_authority": (
        "f7f9a83ed2a8fa8a5030d000eb725be295210924"
    ),
    "accepted_geometry_sha256": (
        "34495d650d6a8c62b00a916796c90389b48f80d8f20a23eac93207758e993f5d"
    ),
    "homography_refit_v0_2_bundle_sha256": (
        "d26b43f202489c000b4af686c7b21bf5993459714f91676d368308e3c055b588"
    ),
    "person_c_untouched_test_package_revision": (
        "3ba6c091426a537d60c950dd1bb38f5fc02826d5"
    ),
    "person_a_parquet_authority_revision": (
        "06b87fe1f43d2133c25db498fcc1fd234f958aad"
    ),
}

UPSTREAM_BRANCHES = {
    "person_a": "origin/role/person-a-model",
    "person_b": "origin/role/person-b-analysis",
    "person_c": "origin/role/person-c-data",
    "person_d": "origin/role/person-d-baselines",
    "person_e": "origin/role/person-e-operations",
    "main": "origin/main",
}

OUTPUT_FILES = (
    "external_blockers.json",
    "implementation_inventory.json",
    "sha256_inventory.json",
    "step_status.json",
    "terminal_status.json",
    "test_inventory.json",
    "version_table.json",
)


class TerminalStatusError(RuntimeError):
    """Fail-closed terminal status error."""


def git_text(*arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def load_json(relative: str) -> Any:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def verify_frozen_hashes() -> dict[str, Any]:
    """Confirm every frozen commit and bundle hash is still exactly as recorded."""

    results: list[dict[str, Any]] = []

    for name in (
        "person_e_homography_provenance_completion_authority",
        "person_e_portability_repair_authority",
    ):
        commit = FROZEN_HASHES[name]
        reachable = (
            subprocess.run(
                ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", commit, "HEAD"],
                check=False,
                capture_output=True,
            ).returncode
            == 0
        )
        results.append(
            {"name": name, "kind": "commit", "value": commit, "valid": reachable}
        )

    for name, branch in (
        ("person_c_untouched_test_package_revision", "origin/role/person-c-data"),
        ("person_a_parquet_authority_revision", "origin/role/person-a-model"),
    ):
        commit = FROZEN_HASHES[name]
        reachable = (
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(ROOT),
                    "merge-base",
                    "--is-ancestor",
                    commit,
                    branch,
                ],
                check=False,
                capture_output=True,
            ).returncode
            == 0
        )
        results.append(
            {
                "name": name,
                "kind": "upstream_commit",
                "value": commit,
                "branch": branch,
                "valid": reachable,
            }
        )

    manifest = load_json(
        "data/handoff_e/person_e_v0_4_homography_refit_v0_2/package_manifest.json"
    )
    for name, observed in (
        ("accepted_geometry_sha256", manifest["accepted_geometry_sha256"]),
        (
            "homography_refit_v0_2_bundle_sha256",
            manifest["package_bundle_sha256"],
        ),
    ):
        results.append(
            {
                "name": name,
                "kind": "artifact_sha256",
                "value": FROZEN_HASHES[name],
                "observed": observed,
                "valid": observed == FROZEN_HASHES[name],
            }
        )

    receipt_path = (
        ROOT
        / "docs/status/person_e_a_multilayout_activation_provenance_acceptance_v0_1"
        / "person_e_to_person_a_multilayout_activation_provenance_receipt.json"
    )
    observed = hash_file_bytes(receipt_path) if receipt_path.is_file() else None
    results.append(
        {
            "name": "person_e_successor_provenance_receipt_sha256",
            "kind": "artifact_sha256",
            "value": FROZEN_HASHES["person_e_successor_provenance_receipt_sha256"],
            "observed": observed,
            "valid": observed
            == FROZEN_HASHES["person_e_successor_provenance_receipt_sha256"],
        }
    )

    return {
        "checks": results,
        "all_valid": all(row["valid"] for row in results),
        "invalid": sorted(row["name"] for row in results if not row["valid"]),
    }


def build_version_table() -> dict[str, Any]:
    detector = load_json(
        "docs/status/person_e_phase3_step3_1_formal_evaluation_v0_1/"
        "formal_evaluation_report.json"
    )
    homography = load_json(
        "data/handoff_e/person_e_v0_4_homography_refit_v0_2/package_manifest.json"
    )
    config = load_json("configs/vision/person_e_phase1.yaml")
    return {
        "version_table_schema_version": "person-e-terminal-version-table-v0.1",
        "registry_version": "mineocclude-immutable-registry-v2.0",
        "detector_version": detector["detector_version"],
        "homography_version": homography["schema_version"],
        "homography_algorithm_version": "four_point_projective_gauss_jordan_v0.1",
        "homography_report_schema_version": "person-e-homography-report-v0.3",
        "ssim": {
            "algorithm": config["ssim"]["algorithm"],
            "ssim_version": config["ssim"]["ssim_version"],
            "data_range": config["ssim"]["data_range"],
            "channel_handling": config["ssim"]["channel_handling"],
            "sample_covariance": config["ssim"]["sample_covariance"],
            "k1": config["ssim"]["k1"],
            "k2": config["ssim"]["k2"],
            "alignment": config["ssim"]["alignment"],
            "background_mask": config["ssim"]["background_mask"],
            "background_mask_margin_pixels": config["ssim"][
                "background_mask_margin_pixels"
            ],
            "mask_status": config["ssim"]["mask_status"],
        },
        "rollout_intake_schema_version": "mineocclude-rollout-registry-v1.0",
        "measurement_evidence_schema_version": "person-e-measurement-evidence-v0.2",
        "measurement_input_schema_version": "person-b-u4-measurement-input-v0.1",
        "u4_evidence_input_schema_version": "person-e-u4-evidence-input-v0.1",
        "u4_frame_input_schema_version": "person-e-u4-frame-input-v0.1",
        "ssim_report_schema_version": "person-e-ssim-report-v0.2",
        "figure_input_schema_version": "person-e-figure-input-v0.2",
        "checkpoint_evidence_schema_version": "person-e-checkpoint-evidence-v0.1",
        "clean_reproduction_plan_schema_version": (
            "person-e-clean-reproduction-plan-v0.1"
        ),
        "clean_reproduction_receipt_schema_version": (
            "person-e-clean-reproduction-receipt-v0.1"
        ),
        "operating_handoff_schema_version": "person-e-operating-handoff-v0.1",
        "second_operator_receipt_schema_version": (
            "person-e-second-operator-receipt-v0.1"
        ),
    }


def build_implementation_inventory() -> dict[str, Any]:
    modules = [
        "src/mineocclude/vision/magenta.py",
        "src/mineocclude/vision/homography.py",
        "src/mineocclude/vision/calibration.py",
        "src/mineocclude/vision/detection_records.py",
        "src/mineocclude/vision/measurement.py",
        "src/mineocclude/vision/ssim.py",
        "src/mineocclude/vision/config.py",
        "src/mineocclude/vision/markers.py",
        "src/mineocclude/vision/png_decode.py",
        "src/mineocclude/vision/phase3_detector_candidate.py",
        "src/mineocclude/vision/report_schemas.py",
        "src/mineocclude/experiments/registry.py",
        "src/mineocclude/experiments/figure_inputs.py",
        "src/mineocclude/operations/clean_reproduction.py",
        "src/mineocclude/operations/checkpoint_evidence.py",
        "src/mineocclude/operations/handoff.py",
        "src/mineocclude/operations/rehearsal_fixture.py",
    ]
    entry_points = [
        "scripts/fit_homographies.py",
        "scripts/localize_u4_frames.py",
        "scripts/measure_ssim.py",
        "scripts/compose_u4_evidence.py",
        "scripts/measure_u4.py",
        "scripts/evaluate_magenta_detector.py",
        "scripts/build_artifact_index.py",
        "scripts/trace_artifact.py",
        "scripts/build_figure_input.py",
        "scripts/render_figure_svg.py",
        "scripts/build_person_e_phase7_terminal_v0_1.py",
        "scripts/build_person_e_terminal_status_v0_1.py",
    ]
    runbooks = [
        "docs/runbooks/person_e_registry_runbook.md",
        "docs/runbooks/person_e_detector_runbook.md",
        "docs/runbooks/person_e_homography_runbook.md",
        "docs/runbooks/person_e_u4_measurement_runbook.md",
        "docs/runbooks/person_e_preliminary_figures_runbook.md",
    ]
    missing = [
        relative
        for relative in modules + entry_points + runbooks
        if not (ROOT / relative).is_file()
    ]
    if missing:
        raise TerminalStatusError(f"declared implementation is missing: {missing}")
    return {
        "implementation_inventory_schema_version": (
            "person-e-terminal-implementation-inventory-v0.1"
        ),
        "entry_points": {
            relative: hash_file_bytes(ROOT / relative) for relative in entry_points
        },
        "modules": {
            relative: hash_file_bytes(ROOT / relative) for relative in modules
        },
        "runbooks": {
            relative: hash_file_bytes(ROOT / relative) for relative in runbooks
        },
    }


def build_evidence_inventories() -> tuple[list[dict], list[dict]]:
    detector = load_json(
        "docs/status/person_e_phase3_step3_1_formal_evaluation_v0_1/"
        "formal_evaluation_report.json"
    )
    homography = load_json(
        "data/handoff_e/person_e_v0_4_homography_refit_v0_2/fit_summary.json"
    )
    real = [
        {
            "evidence_id": "person_e_detector_v1_formal_heldout_evaluation",
            "path": (
                "docs/status/person_e_phase3_step3_1_formal_evaluation_v0_1/"
                "formal_evaluation_report.json"
            ),
            "measured": {
                "precision": detector["metrics"]["precision"]["decimal"],
                "recall": detector["metrics"]["recall"]["decimal"],
                "total_frames": detector["metrics"]["total_frames"],
                "false_positive": detector["metrics"]["false_positive"],
                "false_negative": detector["metrics"]["false_negative"],
            },
            "gate_kind": "planning",
            "upstream_package": detector["package_id"],
        },
        {
            "evidence_id": "person_e_v0_4_homography_refit_v0_2",
            "path": "data/handoff_e/person_e_v0_4_homography_refit_v0_2/",
            "measured": {
                "passing_layout_count": homography["passing_layout_count"],
                "worst_heldout_wall_parallel_error_blocks": max(
                    float(row["heldout_wall_parallel_error_blocks"])
                    for row in homography["layouts"]
                ),
                "maximum_roundtrip_error_pixels": homography[
                    "maximum_roundtrip_error_pixels"
                ],
            },
            "gate_kind": "planning",
            "upstream_package": homography["accepted_geometry_version"],
        },
        {
            "evidence_id": "person_e_phase2_registry_and_split",
            "path": "docs/status/person_e_phase2_v0_1/",
            "measured": {"steps_passing": ["2.1", "2.2", "2.3"]},
            "gate_kind": "planning",
            "upstream_package": "person_a_smoke_run_and_person_c_pilot",
        },
    ]
    synthetic = [
        {
            "evidence_id": "person_e_step7_1_rehearsal",
            "path": (
                "docs/status/person_e_phase7_terminal_v0_1/"
                "clean_reproduction_receipt.json"
            ),
            "proves": (
                "the five measurement entry points run in order and recover the "
                "known-answer geometry"
            ),
            "labelled_synthetic": True,
        },
        {
            "evidence_id": "person_e_phase1_synthetic_fixtures",
            "path": "tests/fixtures/person_e/",
            "proves": (
                "registry, detection, homography, rollout, and figure interfaces "
                "accept valid records and reject corrupted ones"
            ),
            "labelled_synthetic": True,
        },
        {
            "evidence_id": "person_e_u4_pipeline_composition",
            "path": "tests/vision/test_u4_pipeline.py",
            "proves": (
                "detector, homography, SSIM, and measurement compose end to end "
                "through their frozen schemas"
            ),
            "labelled_synthetic": True,
        },
    ]
    return real, synthetic


def build_documents(
    *,
    passed: int,
    failed: int,
    skipped: int,
    subtests_passed: int,
    duration_seconds: float,
) -> dict[str, bytes]:
    head = git_text("rev-parse", "HEAD")
    branch = git_text("rev-parse", "--abbrev-ref", "HEAD")
    if branch != "role/person-e-operations":
        raise TerminalStatusError(f"terminal status must be built on E's branch: {branch}")

    upstream = {}
    for owner, reference in UPSTREAM_BRANCHES.items():
        upstream[owner] = {
            "branch": reference,
            "commit": git_text("rev-parse", reference),
        }

    frozen = verify_frozen_hashes()
    versions = build_version_table()
    implementation = build_implementation_inventory()
    real_evidence, synthetic_evidence = build_evidence_inventories()
    phase7 = load_json(
        "docs/status/person_e_phase7_terminal_v0_1/phase7_status.json"
    )
    handoff = load_json(
        "docs/status/person_e_phase7_terminal_v0_1/operating_handoff.json"
    )

    blockers = {
        "external_blockers_schema_version": "person-e-terminal-blockers-v0.1",
        "blockers": handoff["remaining_external_dependencies"],
        "blocker_count": len(handoff["remaining_external_dependencies"]),
        "external_artifact_index": handoff["external_artifact_index"],
    }

    step_status = {
        "step_status_schema_version": "person-e-terminal-step-status-v0.1",
        "manual": MANUAL,
        "steps": STEPS,
        "status_counts": {
            status: sum(1 for row in STEPS if row["status"] == status)
            for status in sorted({row["status"] for row in STEPS})
        },
    }

    tests = {
        "test_inventory_schema_version": "person-e-terminal-test-inventory-v0.1",
        "selection_command": TEST_SELECTION,
        "interpreter": "C:/Users/lollo/MineOcclude-TestRunner/Scripts/python.exe",
        "environment": {"PYTHONDONTWRITEBYTECODE": "1"},
        "results": {
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "subtests_passed": subtests_passed,
            "duration_seconds": duration_seconds,
        },
        "skips_are_external_input_conditions": [
            {
                "test": (
                    "tests/vision/"
                    "test_person_e_phase3_step3_3_empirical_visibility_v0_1.py"
                ),
                "count": 4,
                "reason": "MINEOCCLUDE_PERSON_C_STEP3_3_ROOT is not configured",
                "owner": "person_c",
            },
            {
                "test": (
                    "tests/experiments/"
                    "test_person_e_phase6_step6_6_provenance_acceptance_v0_1.py"
                ),
                "count": 1,
                "reason": (
                    "Person A activation store and Person B positive-control "
                    "report are on an unmounted external host"
                ),
                "owner": "person_a",
            },
        ],
        "zero_failures": failed == 0,
    }

    all_local_complete = all(
        row["status"]
        in {
            "COMPLETE_AND_VERIFIED",
            "IMPLEMENTED_NOT_EXECUTED",
            "PARTIALLY_COMPLETE",
            "BLOCKED_EXTERNAL_INPUT",
        }
        for row in STEPS
    ) and not any(row["status"] == "NOT_STARTED" for row in STEPS)

    terminal = {
        "terminal_status_schema_version": SCHEMA_VERSION,
        "branch": branch,
        "head_commit": head,
        "manual": MANUAL,
        "upstream_role_commits": upstream,
        "frozen_hash_verification": frozen,
        "real_evidence_inventory": real_evidence,
        "synthetic_evidence_inventory": synthetic_evidence,
        "test_results": tests["results"],
        "registry_version": versions["registry_version"],
        "detector_version": versions["detector_version"],
        "homography_version": versions["homography_version"],
        "ssim": versions["ssim"],
        "rollout_intake_schema_version": versions["rollout_intake_schema_version"],
        "measurement_schema_version": versions[
            "measurement_evidence_schema_version"
        ],
        "checkpoint_evidence_schema_version": versions[
            "checkpoint_evidence_schema_version"
        ],
        "external_blocker_count": blockers["blocker_count"],
        "all_person_e_local_implementation_complete": all_local_complete,
        "real_measurement_complete": False,
        "real_clean_reproduction_complete": phase7["step_7_1"][
            "real_clean_reproduction_complete"
        ],
        "measurement_row_count": None,
        "real_rollout_count": 0,
        "u4_output_inspected": False,
        "mvp_tag_created_from_this_branch": False,
        "integration_readiness": {
            "decision": "READY_FOR_COORDINATED_INTEGRATION_REVIEW",
            "rationale": (
                "every Person E local implementation, validator, schema, "
                "runbook, and receipt through Step 7.3 exists and passes; the "
                "remaining work is real A/B/C/D inputs, real rollouts, the "
                "clean-run bundle, interpretation locks, and coordinated final "
                "tagging"
            ),
            "final_tag_owner": "coordinated integration review, not Person E",
        },
    }

    documents = {
        "external_blockers.json": blockers,
        "implementation_inventory.json": implementation,
        "step_status.json": step_status,
        "terminal_status.json": terminal,
        "test_inventory.json": tests,
        "version_table.json": versions,
    }
    encoded = {name: formatted_json_bytes(value) for name, value in documents.items()}
    inventory = {
        "sha256_inventory_schema_version": "person-e-terminal-inventory-v0.1",
        "files": {
            name: hashlib.sha256(payload).hexdigest()
            for name, payload in sorted(encoded.items())
        },
    }
    encoded["sha256_inventory.json"] = formatted_json_bytes(inventory)
    return encoded


def validate_package(package_dir: Path) -> None:
    present = (
        {path.name for path in package_dir.iterdir()} if package_dir.is_dir() else set()
    )
    if present != set(OUTPUT_FILES):
        raise TerminalStatusError(f"terminal package file set mismatch: {sorted(present)}")
    inventory = json.loads(
        (package_dir / "sha256_inventory.json").read_text(encoding="utf-8")
    )
    if set(inventory["files"]) != set(OUTPUT_FILES) - {"sha256_inventory.json"}:
        raise TerminalStatusError("terminal inventory does not cover every file")
    for name, digest in inventory["files"].items():
        actual = hashlib.sha256((package_dir / name).read_bytes()).hexdigest()
        if actual != digest:
            raise TerminalStatusError(f"terminal package byte drift: {name}")

    terminal = json.loads(
        (package_dir / "terminal_status.json").read_text(encoding="utf-8")
    )
    if terminal["real_measurement_complete"] is not False:
        raise TerminalStatusError("real measurement may not be claimed")
    if terminal["u4_output_inspected"] is not False:
        raise TerminalStatusError("U4 output inspection may not be claimed")
    if terminal["mvp_tag_created_from_this_branch"] is not False:
        raise TerminalStatusError("the MVP tag may not be created from E's branch")
    if not terminal["frozen_hash_verification"]["all_valid"]:
        raise TerminalStatusError(
            "frozen hashes invalid: "
            f"{terminal['frozen_hash_verification']['invalid']}"
        )
    steps = json.loads((package_dir / "step_status.json").read_text(encoding="utf-8"))
    if len(steps["steps"]) != len(STEPS):
        raise TerminalStatusError("step status lost a manual step")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("build", "validate"))
    parser.add_argument("--out-dir", type=Path, default=ROOT / PKG_REL)
    parser.add_argument("--passed", type=int, default=0)
    parser.add_argument("--failed", type=int, default=0)
    parser.add_argument("--skipped", type=int, default=0)
    parser.add_argument("--subtests-passed", type=int, default=0)
    parser.add_argument("--duration-seconds", type=float, default=0.0)
    arguments = parser.parse_args()
    try:
        if arguments.mode == "build":
            documents = build_documents(
                passed=arguments.passed,
                failed=arguments.failed,
                skipped=arguments.skipped,
                subtests_passed=arguments.subtests_passed,
                duration_seconds=arguments.duration_seconds,
            )
            out = arguments.out_dir.resolve()
            out.mkdir(parents=True, exist_ok=True)
            for name, payload in documents.items():
                (out / name).write_bytes(payload)
            print(f"BUILD OK: {len(documents)} terminal status files written")
        else:
            validate_package(arguments.out_dir.resolve())
            print("VALIDATE OK: Person E terminal status package")
    except (TerminalStatusError, ValueError, KeyError, OSError) as error:
        print(f"FAIL-CLOSED: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
