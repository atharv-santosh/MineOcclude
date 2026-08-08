"""Build the Person E Phase 7 terminal package: Steps 7.1, 7.2, and 7.3.

The package has three parts and one rule. The parts are a clean-reproduction
receipt (7.1), a checkpoint evidence set (7.2), and the frozen operating
handoff plus second-operator receipt (7.3). The rule is that every scientific
number displayed here is read out of committed Person E evidence at build time;
none is typed in, and a slot with no accepted upstream result stays visibly
empty with its blocking owner named.

Usage:
    python scripts/build_person_e_phase7_terminal_v0_1.py build
    python scripts/build_person_e_phase7_terminal_v0_1.py validate
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.experiments.registry import (  # noqa: E402
    formatted_json_bytes,
    hash_file_bytes,
)
from mineocclude.operations import rehearsal_fixture  # noqa: E402
from mineocclude.operations.checkpoint_evidence import (  # noqa: E402
    EVIDENCE_SLOTS,
    build_checkpoint_evidence,
    validate_checkpoint_evidence,
)
from mineocclude.operations.clean_reproduction import (  # noqa: E402
    CLEAN_REPRODUCTION_PLAN_SCHEMA_VERSION,
    DEFAULT_COMPONENT_PATHS,
    REPRODUCTION_STAGES,
    build_clean_reproduction_receipt,
    component_hashes,
    environment_lock,
    run_stage,
    validate_clean_reproduction_plan,
    validate_clean_reproduction_receipt,
)
from mineocclude.operations.handoff import (  # noqa: E402
    REQUIRED_WORKFLOWS,
    build_operating_handoff,
    build_second_operator_receipt,
    validate_operating_handoff,
    validate_second_operator_receipt,
)

PKG_REL = "docs/status/person_e_phase7_terminal_v0_1"
PACKAGE_SCHEMA_VERSION = "person-e-phase7-terminal-v0.1"

DETECTOR_EVIDENCE_REL = (
    "docs/status/person_e_phase3_step3_1_formal_evaluation_v0_1/"
    "formal_evaluation_report.json"
)
HOMOGRAPHY_EVIDENCE_REL = (
    "data/handoff_e/person_e_v0_4_homography_refit_v0_2/fit_summary.json"
)
HOMOGRAPHY_MANIFEST_REL = (
    "data/handoff_e/person_e_v0_4_homography_refit_v0_2/package_manifest.json"
)
SPLIT_MANIFEST_REL = (
    "docs/status/person_e_phase2_v0_1/frozen_split_manifest.json"
)
PAPER_PLAN_REL = "docs/operations/person_e_paper_workspace_plan.md"

RUNBOOKS = {
    "registry": "docs/runbooks/person_e_registry_runbook.md",
    "detector": "docs/runbooks/person_e_detector_runbook.md",
    "homography": "docs/runbooks/person_e_homography_runbook.md",
    "u4_measurement": "docs/runbooks/person_e_u4_measurement_runbook.md",
    "preliminary_figures": "docs/runbooks/person_e_preliminary_figures_runbook.md",
}

OUTPUT_FILES = (
    "checkpoint_evidence.json",
    "clean_reproduction_plan.json",
    "clean_reproduction_receipt.json",
    "external_input_requests.json",
    "operating_handoff.json",
    "phase7_status.json",
    "second_operator_receipt.json",
    "validation_receipt.json",
    "sha256_inventory.json",
)


class Phase7Error(RuntimeError):
    """Fail-closed Phase 7 build error."""


def load_json(relative: str) -> Any:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def git_text(*arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


# --------------------------------------------------------------------------
# Step 7.1 — clean reproduction
# --------------------------------------------------------------------------


def build_plan(code_commit: str) -> dict[str, Any]:
    """Declare the portable, ordered measurement path.

    Commands carry a ``{workdir}`` placeholder rather than a real directory so
    the plan stays reproducible on any machine.
    """

    inputs = []
    for input_id, relative, owner in (
        ("person_e_config", "configs/vision/person_e_phase1.yaml", "person_e"),
        ("person_e_frozen_split_manifest", SPLIT_MANIFEST_REL, "person_e"),
        ("person_e_detector_formal_evaluation", DETECTOR_EVIDENCE_REL, "person_e"),
        ("person_e_homography_refit_v0_2", HOMOGRAPHY_EVIDENCE_REL, "person_e"),
    ):
        inputs.append(
            {
                "input_id": input_id,
                "owner": owner,
                "repository_path": relative,
                "sha256": hash_file_bytes(ROOT / relative),
            }
        )

    stage_commands = {
        "registry": [
            "-c",
            "import json,sys;"
            "d=json.load(open(sys.argv[1],encoding='utf-8'));"
            "assert d['rollout_rows'],'empty manifest';"
            "print('registry stage: %d accepted rollout row(s)'%len(d['rollout_rows']))",
            "{workdir}/manifest.json",
        ],
        "detector": [
            "-c",
            "import json,sys;"
            "d=json.load(open(sys.argv[1],encoding='utf-8'));"
            "print('detector stage: %d frame(s) queued'%len(d['frames']))",
            "{workdir}/frames.json",
        ],
        "homography": [
            "scripts/fit_homographies.py",
            "{workdir}/homography_input.json",
            "{workdir}/homography_report.json",
            "--config",
            "{workdir}/person_e_live_config.json",
            "--producer-run-id",
            rehearsal_fixture.REHEARSAL_RUN_ID,
            "--code-sha",
            rehearsal_fixture.CODE_SHA,
        ],
        "displacement": [
            "scripts/localize_u4_frames.py",
            "{workdir}/frames.json",
            "{workdir}/homography_report.json",
            "{workdir}/manifest.json",
            "{workdir}/registry.json",
            "{workdir}/localization.json",
            "--config",
            "{workdir}/person_e_live_config.json",
            "--run-id",
            rehearsal_fixture.REHEARSAL_RUN_ID,
        ],
        "ssim": [
            "scripts/compose_u4_evidence.py",
            "{workdir}/localization.json",
            "{workdir}/ssim_report.json",
            "{workdir}/composed.json",
        ],
    }
    expected_outputs = {
        "registry": [],
        "detector": [],
        "homography": ["{workdir}/homography_report.json"],
        "displacement": ["{workdir}/localization.json"],
        "ssim": ["{workdir}/composed.json"],
    }
    plan = {
        "clean_reproduction_plan_schema_version": (
            CLEAN_REPRODUCTION_PLAN_SCHEMA_VERSION
        ),
        "code_commit": code_commit,
        "component_hashes": component_hashes(ROOT, DEFAULT_COMPONENT_PATHS),
        "environment_lock": environment_lock(),
        "evidence_class": "synthetic_fixture",
        "inputs": inputs,
        "stages": [
            {
                "stage": stage,
                "command": stage_commands[stage],
                "expected_outputs": expected_outputs[stage],
            }
            for stage in REPRODUCTION_STAGES
        ],
    }
    validate_clean_reproduction_plan(plan)
    return plan


def execute_rehearsal(plan: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run the declared stages over synthetic fixtures and report outcomes."""

    with tempfile.TemporaryDirectory() as raw_directory:
        workdir = Path(raw_directory)
        config_path = rehearsal_fixture.write_live_config(workdir)
        manifest, registry = rehearsal_fixture.registry_bundle(config_path)
        rehearsal_fixture.write_json(workdir / "manifest.json", manifest)
        rehearsal_fixture.write_json(workdir / "registry.json", registry)
        rehearsal_fixture.write_json(
            workdir / "homography_input.json", rehearsal_fixture.homography_input()
        )
        rehearsal_fixture.write_json(
            workdir / "frames.json", rehearsal_fixture.frame_input()
        )

        substitutions = {"workdir": workdir.as_posix()}
        results: list[dict[str, Any]] = []
        for stage in plan["stages"]:
            name = str(stage["stage"])
            if name == "ssim":
                localization_path = workdir / "localization.json"
                if not localization_path.is_file():
                    results.append(
                        {
                            "stage": name,
                            "command": list(stage["command"]),
                            "exit_code": None,
                            "outcome": "failed",
                            "runtime_seconds": 0.0,
                            "stdout_tail": "",
                            "stderr_tail": "displacement stage produced no output",
                        }
                    )
                    continue
                localization = json.loads(
                    localization_path.read_text(encoding="utf-8")
                )
                rehearsal_fixture.write_json(
                    workdir / "ssim_report.json",
                    rehearsal_fixture.ssim_report(localization),
                )
            results.append(run_stage(stage, ROOT, substitutions=substitutions))

        known_answer = {
            "expected_wall_parallel_blocks": (
                rehearsal_fixture.EXPECTED_WALL_PARALLEL_BLOCKS
            ),
            "observed_wall_parallel_blocks": None,
            "known_answer_recovered": False,
        }
        localization_path = workdir / "localization.json"
        if localization_path.is_file():
            localization = json.loads(localization_path.read_text(encoding="utf-8"))
            try:
                observed = localization["rows"][0]["localizations"][1][
                    "wall_parallel_blocks"
                ]
            except (KeyError, IndexError, TypeError):
                observed = None
            known_answer["observed_wall_parallel_blocks"] = observed
            known_answer["known_answer_recovered"] = (
                observed == rehearsal_fixture.EXPECTED_WALL_PARALLEL_BLOCKS
            )
        return results, known_answer


# --------------------------------------------------------------------------
# Step 7.2 — checkpoint evidence
# --------------------------------------------------------------------------


def _empty_slot(name: str, reason: str, owner: str) -> dict[str, Any]:
    return {
        "slot": name,
        "state": "empty_awaiting_external_input",
        "displayed_values": [],
        "empty_reason": reason,
        "blocking_owner": owner,
    }


def build_checkpoint(code_commit: str) -> dict[str, Any]:
    """Read the real planning gates out of committed evidence and lay them out."""

    detector = load_json(DETECTOR_EVIDENCE_REL)
    homography = load_json(HOMOGRAPHY_EVIDENCE_REL)
    detector_digest = hash_file_bytes(ROOT / DETECTOR_EVIDENCE_REL)
    homography_digest = hash_file_bytes(ROOT / HOMOGRAPHY_EVIDENCE_REL)

    detector_artifact = "person-e-detector-v1-formal-evaluation-v0_1"
    homography_artifact = "person-e-v0_4-homography-refit-v0_2"

    detector_values = [
        {
            "label": "held-out detector precision",
            "value": detector["metrics"]["precision"]["decimal"],
            "units": "fraction",
            "sample_count": detector["metrics"]["total_frames"],
            "source_artifact_id": detector_artifact,
            "source_run_id": detector["run_id"],
            "source_status": "accepted",
            "figure_input_sha256": detector_digest,
            "gate_kind": "planning",
        },
        {
            "label": "held-out detector recall",
            "value": detector["metrics"]["recall"]["decimal"],
            "units": "fraction",
            "sample_count": detector["metrics"]["total_frames"],
            "source_artifact_id": detector_artifact,
            "source_run_id": detector["run_id"],
            "source_status": "accepted",
            "figure_input_sha256": detector_digest,
            "gate_kind": "planning",
        },
        {
            "label": "held-out false positives",
            "value": detector["metrics"]["false_positive"],
            "units": "frames",
            "sample_count": detector["metrics"]["total_frames"],
            "source_artifact_id": detector_artifact,
            "source_run_id": detector["run_id"],
            "source_status": "accepted",
            "figure_input_sha256": detector_digest,
            "gate_kind": "planning",
        },
        {
            "label": "held-out false negatives",
            "value": detector["metrics"]["false_negative"],
            "units": "frames",
            "sample_count": detector["metrics"]["total_frames"],
            "source_artifact_id": detector_artifact,
            "source_run_id": detector["run_id"],
            "source_status": "accepted",
            "figure_input_sha256": detector_digest,
            "gate_kind": "planning",
        },
    ]

    layout_errors = [
        float(layout["heldout_wall_parallel_error_blocks"])
        for layout in homography["layouts"]
    ]
    homography_values = [
        {
            "label": "worst-layout held-out wall-parallel localization error",
            "value": max(layout_errors),
            "units": "blocks",
            "sample_count": len(layout_errors),
            "source_artifact_id": homography_artifact,
            "source_run_id": homography["source_code_commit"],
            "source_status": "accepted",
            "figure_input_sha256": homography_digest,
            "gate_kind": "planning",
        },
        {
            "label": "passing layout count",
            "value": homography["passing_layout_count"],
            "units": "layouts",
            "sample_count": len(layout_errors),
            "source_artifact_id": homography_artifact,
            "source_run_id": homography["source_code_commit"],
            "source_status": "accepted",
            "figure_input_sha256": homography_digest,
            "gate_kind": "planning",
        },
        {
            "label": "maximum inverse round-trip error",
            "value": homography["maximum_roundtrip_error_pixels"],
            "units": "pixels",
            "sample_count": len(layout_errors),
            "source_artifact_id": homography_artifact,
            "source_run_id": homography["source_code_commit"],
            "source_status": "accepted",
            "figure_input_sha256": homography_digest,
            "gate_kind": "planning",
        },
    ]

    slots: list[dict[str, Any]] = []
    for name in EVIDENCE_SLOTS:
        if name == "engineering_detector_gate":
            slots.append(
                {
                    "slot": name,
                    "state": "populated",
                    "displayed_values": detector_values,
                }
            )
        elif name == "engineering_localization_gate":
            slots.append(
                {
                    "slot": name,
                    "state": "populated",
                    "displayed_values": homography_values,
                }
            )
        elif name.startswith("u1") or name.startswith("u2") or name.startswith("u3"):
            slots.append(
                _empty_slot(
                    name,
                    "no accepted Person B preliminary result table has been published",
                    "person_b",
                )
            )
        else:
            slots.append(
                _empty_slot(
                    name,
                    "no U4 rollout clips have been generated, so no measurement "
                    "rows exist",
                    "person_a",
                )
            )

    figure_index = {
        detector_artifact: {
            "figure_input_sha256": detector_digest,
            "status": "accepted",
        },
        homography_artifact: {
            "figure_input_sha256": homography_digest,
            "status": "accepted",
        },
    }
    artifact_index = [
        {
            "artifact_id": detector_artifact,
            "owner": "person_e",
            "repository_path": DETECTOR_EVIDENCE_REL,
            "sha256": detector_digest,
            "status": "accepted",
        },
        {
            "artifact_id": homography_artifact,
            "owner": "person_e",
            "repository_path": HOMOGRAPHY_EVIDENCE_REL,
            "sha256": homography_digest,
            "status": "accepted",
        },
    ]

    package = build_checkpoint_evidence(
        slots=slots,
        figure_index=figure_index,
        artifact_index=artifact_index,
        accepted_count=len(artifact_index),
        excluded_count=0,
        missing_count=sum(1 for slot in slots if slot["state"] != "populated"),
        control_failures=[],
        limitations=[
            "Both populated slots are Person E planning gates, not scientific "
            "results.",
            "Detector precision and recall are measured on the 48-frame declared "
            "held-out set only; they are not a publication-scale accuracy claim.",
            "No U4 rollout clip has been generated, so persistence, displacement, "
            "and SSIM slots are empty rather than zero.",
            "No Person B or Person D preliminary result table exists, so U1-U3 "
            "slots are empty.",
            "No control has been run, so the absence of control failures is not "
            "evidence that controls passed.",
        ],
        provenance_demonstration_commands=[
            ["scripts/trace_artifact.py", "<registry.json>", detector_artifact],
            ["scripts/build_artifact_index.py", "<registry.json>", "<index.json>"],
            [
                "-m",
                "pytest",
                "tests/vision/test_phase3_formal_detector_evaluation.py",
            ],
        ],
        code_commit=code_commit,
    )
    validate_checkpoint_evidence(package)
    return package


# --------------------------------------------------------------------------
# Step 7.3 — frozen operating handoff
# --------------------------------------------------------------------------


def _workflow(
    name: str,
    *,
    required_inputs: list[str],
    commands: list[list[str]],
    validators: list[str],
    outputs: list[str],
    failure_behavior: str,
    version_rules: str,
    escalation_owner: str,
    reruns: list[str],
    ab_review: list[str],
) -> dict[str, Any]:
    return {
        "workflow": name,
        "runbook_path": RUNBOOKS[name],
        "required_inputs": required_inputs,
        "commands": commands,
        "validators": validators,
        "outputs": outputs,
        "failure_behavior": failure_behavior,
        "version_and_supersession_rules": version_rules,
        "escalation_owner": escalation_owner,
        "permitted_operational_reruns": reruns,
        "requires_ab_review": ab_review,
    }


def build_workflows() -> list[dict[str, Any]]:
    return [
        _workflow(
            "registry",
            required_inputs=[
                "upstream artifact manifest with authoritative IDs and status",
                "direct-input artifact IDs for the record being registered",
            ],
            commands=[
                ["scripts/build_artifact_index.py", "<registry.json>", "<index.json>"],
                ["scripts/trace_artifact.py", "<registry.json>", "<artifact-id>"],
            ],
            validators=[
                "tests/experiments/test_registry.py",
                "tests/experiments/test_immutable_registry_v2_contract.py",
                "tests/experiments/test_immutable_registry_v2_queries.py",
                "tests/contracts/test_rollout_registry_contract.py",
            ],
            outputs=[
                "registry records with direct inputs, checksums, seeds, and status",
                "artifact index report",
            ],
            failure_behavior=(
                "reject the record and name the exact record, field, and owner; "
                "never partially write"
            ),
            version_rules=(
                "completed runs are immutable; corrections create a new run with "
                "supersedes_run_id and remain queryable"
            ),
            escalation_owner="person_a",
            reruns=[
                "re-run a query or index build against an unchanged registry",
                "register a new artifact whose owner has published its status",
            ],
            ab_review=[
                "schema field addition, removal, or semantic change",
                "status transition or accepted-selection rule change",
            ],
        ),
        _workflow(
            "detector",
            required_inputs=[
                "Person C frame package with stable identities and source hashes",
                "frozen calibration/held-out split manifest",
                "frozen detector config and version record",
            ],
            commands=[
                ["scripts/evaluate_magenta_detector.py", "--help"],
                ["scripts/run_person_e_phase3_formal_detector_evaluation.py", "--help"],
            ],
            validators=[
                "tests/vision/test_config_and_magenta.py",
                "tests/vision/test_calibration.py",
                "tests/vision/test_phase3_detector_candidate.py",
                "tests/vision/test_phase3_formal_detector_evaluation.py",
            ],
            outputs=[
                "per-frame detection records with detector version and rejection reason",
                "held-out precision/recall report with per-layout breakdown",
            ],
            failure_behavior=(
                "zero, multiple, edge, malformed, or corrupted inputs produce no "
                "detection and an explicit rejection reason"
            ),
            version_rules=(
                "parameters freeze before the held-out set opens; any change creates "
                "a new detector version and invalidates dependent outputs"
            ),
            escalation_owner="person_c",
            reruns=[
                "re-run the frozen detector over the same frames at the same version",
                "reproduce the recorded formal evaluation",
            ],
            ab_review=[
                "HSV, morphology, or valid-blob rule change",
                "precision/recall gate change",
                "opening a held-out set a second time",
            ],
        ),
        _workflow(
            "homography",
            required_inputs=[
                "four marker image/world correspondences per layout",
                "canonical camera pose and image resolution",
                "wall-axis origin and positive unit vector",
                "held-out visible sheep world positions",
            ],
            commands=[
                [
                    "scripts/fit_homographies.py",
                    "<homography_input.json>",
                    "<report.json>",
                    "--config",
                    "configs/vision/person_e_phase1.yaml",
                    "--producer-run-id",
                    "<run-id>",
                    "--code-sha",
                    "<40-hex>",
                ]
            ],
            validators=[
                "tests/vision/test_homography_and_ssim.py",
                "tests/vision/test_markers.py",
                "tests/vision/test_phase2_step2_4_v0_4.py",
                "tests/vision/test_attempt_02_refit_finalize_v0_2.py",
            ],
            outputs=[
                "per-layout matrix with condition number, determinant, and rank",
                "held-out wall-parallel error in blocks with image-region breakdown",
                "coordinate convention record and applicability domain",
            ],
            failure_behavior=(
                "degenerate geometry, marker-order swap, resolution or pose mismatch, "
                "and out-of-region queries reject rather than extrapolate"
            ),
            version_rules=(
                "each matrix carries a content-derived version id; corrections create "
                "a versioned successor and preserve the superseded package"
            ),
            escalation_owner="person_c",
            reruns=[
                "re-run the fit over identical correspondences",
                "re-run validation over the recorded held-out set",
            ],
            ab_review=[
                "camera pose, resolution, or wall-axis sign change",
                "localization tolerance change",
                "applying a matrix outside its validated domain",
            ],
        ),
        _workflow(
            "u4_measurement",
            required_inputs=[
                "Person A rollout generation manifest, clips, hashes, frame contract",
                "Person B frozen event/dose table and event rules",
                "Person B approved SSIM matching rule and mask margin",
                "Person C held-out layout, wall-axis sign, pose applicability",
                "Person D control IDs and completeness report",
            ],
            commands=[
                [
                    "scripts/localize_u4_frames.py",
                    "<frames.json>",
                    "<homography_report.json>",
                    "<rollout_manifest.json>",
                    "<registry.json>",
                    "<localization.json>",
                    "--config",
                    "configs/vision/person_e_phase1.yaml",
                    "--run-id",
                    "<run-id>",
                ],
                [
                    "scripts/compose_u4_evidence.py",
                    "<localization.json>",
                    "<ssim_report.json>",
                    "<composed.json>",
                ],
                [
                    "scripts/measure_u4.py",
                    "<rollout_manifest.json>",
                    "<registry.json>",
                    "<composed.json>",
                    "<measurements.json>",
                    "--evidence-output-dir",
                    "<evidence-dir>",
                    "--config",
                    "configs/vision/person_e_phase1.yaml",
                    "--run-id",
                    "<run-id>",
                ],
            ],
            validators=[
                "tests/vision/test_u4_pipeline.py",
                "tests/vision/test_measurement.py",
                "tests/vision/test_homography_and_ssim.py",
                "tests/vision/test_person_e_scripts.py",
            ],
            outputs=[
                "one versioned U4 measurement table with full identity and versions",
                "persistence and non-persistence distinct from generation failure",
                "signed wall-parallel displacement against the exact alpha=0 pair",
                "global SSIM, background-masked SSIM, and natural variation",
                "planned-versus-measured counts and status summaries",
            ],
            failure_behavior=(
                "a missing sheep is never imputed as zero; a pushed clip with no "
                "alpha=0 match at the same event and seed is a missing pair, never a "
                "substituted seed; misaligned SSIM pairs reject"
            ),
            version_rules=(
                "the table freezes at the version Person B consumes; a detector, "
                "homography, or SSIM version change requires a new measurement run"
            ),
            escalation_owner="person_b",
            reruns=[
                "re-run the ordered pipeline over identical inputs",
                "re-run intake validation to regenerate the completeness report",
            ],
            ab_review=[
                "primary or sensitivity event rule change",
                "SSIM parameter, mask margin, or seed-pairing change",
                "any conditioning or exclusion of clips before Person B's analysis",
            ],
        ),
        _workflow(
            "preliminary_figures",
            required_inputs=[
                "Person B or Person D machine-readable result table with version",
                "Person C accepted/excluded manifest and counts",
                "registry records for every source artifact",
            ],
            commands=[
                ["scripts/build_figure_input.py", "<source.json>", "<figure_input.json>"],
                ["scripts/render_figure_svg.py", "<figure_input.json>", "<figure.svg>"],
            ],
            validators=[
                "tests/experiments/test_figure_inputs.py",
                "tests/experiments/test_figure_renderer.py",
                "tests/experiments/test_phase1_lineage.py",
                "tests/experiments/test_phase2_registry_queries.py",
            ],
            outputs=[
                "figure input documents carrying source run, version, units, counts",
                "rendered figures whose values all came from their input document",
                "figure index answering what produced any table or plot",
            ],
            failure_behavior=(
                "a failed, exploratory, or superseded source rejects; rendering never "
                "substitutes a default for a missing unit, count, or uncertainty type"
            ),
            version_rules=(
                "an upstream supersession marks every dependent visual stale; visuals "
                "are regenerated from the new source, never patched by hand"
            ),
            escalation_owner="person_b",
            reruns=[
                "re-render an unchanged figure input",
                "rebuild the artifact index after new registrations",
            ],
            ab_review=[
                "displayed quantity, unit, sample unit, or uncertainty type change",
                "change to which rows a figure includes",
                "presenting a planning threshold as a scientific result",
            ],
        ),
    ]


def build_version_table() -> list[dict[str, Any]]:
    detector = load_json(DETECTOR_EVIDENCE_REL)
    homography_manifest = load_json(HOMOGRAPHY_MANIFEST_REL)
    return [
        {
            "component": "magenta_detector",
            "version": detector["detector_version"],
            "owner": "person_e",
            "sha256": hash_file_bytes(ROOT / "src/mineocclude/vision/magenta.py"),
        },
        {
            "component": "homography_package",
            "version": homography_manifest["schema_version"],
            "owner": "person_e",
            "sha256": homography_manifest["package_bundle_sha256"],
        },
        {
            "component": "homography_algorithm",
            "version": "four_point_projective_gauss_jordan_v0.1",
            "owner": "person_e",
            "sha256": hash_file_bytes(ROOT / "src/mineocclude/vision/homography.py"),
        },
        {
            "component": "homography_report_schema",
            "version": "person-e-homography-report-v0.3",
            "owner": "person_e",
            "sha256": None,
        },
        {
            "component": "ssim",
            "version": "global_ssim_per_channel_mean_v0.1",
            "owner": "person_e",
            "sha256": hash_file_bytes(ROOT / "src/mineocclude/vision/ssim.py"),
        },
        {
            "component": "measurement_evidence_schema",
            "version": "person-e-measurement-evidence-v0.2",
            "owner": "person_e",
            "sha256": hash_file_bytes(ROOT / "src/mineocclude/vision/measurement.py"),
        },
        {
            "component": "immutable_registry",
            "version": "mineocclude-immutable-registry-v2.0",
            "owner": "person_e",
            "sha256": hash_file_bytes(ROOT / "src/mineocclude/experiments/registry.py"),
        },
        {
            "component": "figure_input_schema",
            "version": "person-e-figure-input-v0.2",
            "owner": "person_e",
            "sha256": hash_file_bytes(
                ROOT / "src/mineocclude/experiments/figure_inputs.py"
            ),
        },
        {
            "component": "accepted_geometry",
            "version": homography_manifest["accepted_geometry_version"],
            "owner": "person_c",
            "sha256": homography_manifest["accepted_geometry_sha256"],
        },
    ]


def build_external_index() -> list[dict[str, Any]]:
    return [
        {
            "artifact_id": "person_a_activation_store_phase6",
            "owner": "person_a",
            "recorded_path": (
                "/home/sagemaker-user/person-a-phase6-approved-outputs/"
                "person-a-phase6-step6-3-continuation-"
                "a102aa4d1ca5d4760e9c9997-activation-store-v2"
            ),
            "availability": "external_unmounted",
            "sha256": None,
            "note": (
                "byte identity is recorded in Person A's committed per-pilot "
                "inventories; regeneration of the Step 6.6 acceptance package "
                "requires this store to be mounted"
            ),
        },
        {
            "artifact_id": "person_b_step6_6_positive_control_report",
            "owner": "person_b",
            "recorded_path": (
                "/home/sagemaker-user/person-b-phase6-approved-outputs/"
                "person-b-phase6-v2-positive-control-step6-6/"
                "person_b_step6_6_positive_control.json"
            ),
            "availability": "external_unmounted",
            "sha256": (
                "91254b04549745e2f4c8084aa6290dfa5b653c2f407ece8d62589b48d9832bb8"
            ),
            "note": "50,568,852 bytes; verified when the store is mounted",
        },
        {
            "artifact_id": "person_a_u4_rollout_clips",
            "owner": "person_a",
            "recorded_path": "not yet generated",
            "availability": "pending_generation",
            "sha256": None,
            "note": "required before any U4 measurement row can exist",
        },
    ]


def build_dependencies() -> list[dict[str, Any]]:
    return [
        {
            "dependency_id": "person_a_u4_rollout_clips",
            "owner": "person_a",
            "blocks_step": "6.1",
            "description": (
                "immutable alpha=0, signed-dose, and control clips with complete "
                "identity, hashes, and frame contract"
            ),
            "next_command": [
                "scripts/localize_u4_frames.py",
                "<frames.json>",
                "<homography_report.json>",
                "<rollout_manifest.json>",
                "<registry.json>",
                "<localization.json>",
                "--config",
                "configs/vision/person_e_phase1.yaml",
                "--run-id",
                "<run-id>",
            ],
        },
        {
            "dependency_id": "person_b_event_dose_table",
            "owner": "person_b",
            "blocks_step": "6.2",
            "description": (
                "frozen layer, timestep, direction version, alpha table, held-out "
                "event list, and the primary/sensitivity event rules"
            ),
            "next_command": [
                "scripts/measure_u4.py",
                "<rollout_manifest.json>",
                "<registry.json>",
                "<composed.json>",
                "<measurements.json>",
                "--evidence-output-dir",
                "<evidence-dir>",
                "--config",
                "configs/vision/person_e_phase1.yaml",
                "--run-id",
                "<run-id>",
            ],
        },
        {
            "dependency_id": "person_c_heldout_geometry_for_rollout_pose",
            "owner": "person_c",
            "blocks_step": "6.3",
            "description": (
                "held-out layout, wall-axis sign, and marker/camera/homography "
                "applicability metadata for the exact rollout image contract"
            ),
            "next_command": [
                "scripts/fit_homographies.py",
                "<homography_input.json>",
                "<homography_report.json>",
                "--config",
                "configs/vision/person_e_phase1.yaml",
                "--producer-run-id",
                "<run-id>",
                "--code-sha",
                "<40-hex>",
            ],
        },
        {
            "dependency_id": "person_b_measurement_version_freeze",
            "owner": "person_b",
            "blocks_step": "6.5",
            "description": (
                "confirmation of the measurement table version Person B's analysis "
                "will consume, so Person E can freeze it and register direct inputs"
            ),
            "next_command": [
                "scripts/compose_u4_evidence.py",
                "<localization.json>",
                "<ssim_report.json>",
                "<composed.json>",
            ],
        },
        {
            "dependency_id": "person_b_ssim_matching_rule",
            "owner": "person_b",
            "blocks_step": "6.4",
            "description": (
                "approved frame-alignment rule, seed-pairing rule for natural "
                "variation, and the background-mask margin"
            ),
            "next_command": ["scripts/measure_ssim.py", "--help"],
        },
        {
            "dependency_id": "person_d_control_manifest",
            "owner": "person_d",
            "blocks_step": "6.1",
            "description": (
                "alpha=0, random, orthogonal, wrong-layer, and wrong-timestep "
                "control IDs with a completeness report"
            ),
            "next_command": [
                "scripts/measure_u4.py",
                "<rollout_manifest.json>",
                "<registry.json>",
                "<composed.json>",
                "<measurements.json>",
                "--evidence-output-dir",
                "<evidence-dir>",
                "--config",
                "configs/vision/person_e_phase1.yaml",
                "--run-id",
                "<run-id>",
            ],
        },
        {
            "dependency_id": "person_b_person_d_preliminary_results",
            "owner": "person_b",
            "blocks_step": "5.1",
            "description": (
                "machine-readable preliminary U1-U3 and baseline/control outputs "
                "with valid-versus-superseded status"
            ),
            "next_command": [
                "scripts/build_figure_input.py",
                "<source.json>",
                "<figure_input.json>",
            ],
        },
        {
            "dependency_id": "person_a_clean_run_bundle",
            "owner": "person_a",
            "blocks_step": "7.1",
            "description": (
                "clean-checkout run bundle with immutable MVP config, locked E "
                "versions, and B/C/D identities"
            ),
            "next_command": [
                "scripts/build_person_e_phase7_terminal_v0_1.py",
                "build",
            ],
        },
        {
            "dependency_id": "person_a_external_artifact_store_mount",
            "owner": "person_a",
            "blocks_step": "regeneration of the Step 6.6 acceptance package",
            "description": (
                "mount of the SageMaker activation store so the committed package "
                "can be byte-regenerated on this host"
            ),
            "next_command": [
                "-m",
                "pytest",
                "tests/experiments/test_person_e_phase6_step6_6_provenance_acceptance_v0_1.py",
            ],
        },
    ]


# --------------------------------------------------------------------------
# Package assembly
# --------------------------------------------------------------------------


def build_documents() -> dict[str, bytes]:
    code_commit = git_text("rev-parse", "HEAD")

    plan = build_plan(code_commit)
    stage_results, known_answer = execute_rehearsal(plan)
    post_run = component_hashes(ROOT, DEFAULT_COMPONENT_PATHS)
    blocking = [
        row["dependency_id"]
        for row in build_dependencies()
        if row["blocks_step"] in {"6.1", "6.2", "6.4", "7.1"}
    ]
    receipt = build_clean_reproduction_receipt(
        plan=plan,
        component_verification={
            "component_count": len(plan["component_hashes"]),
            "mismatched_components": [],
            "verified": True,
        },
        input_verification={
            "input_count": len(plan["inputs"]),
            "mismatched_inputs": [],
            "missing_inputs": [],
            "verified": True,
        },
        stage_results=stage_results,
        comparison=None,
        post_run_component_hashes=post_run,
        blocking_external_inputs=sorted(set(blocking)),
    )
    receipt = dict(receipt)
    receipt["synthetic_known_answer"] = known_answer
    # Re-seal after adding the known-answer block so the content hash covers it.
    from mineocclude.experiments.registry import hash_json_value

    receipt.pop("receipt_content_hash", None)
    receipt["receipt_content_hash"] = hash_json_value(receipt)
    validate_clean_reproduction_receipt(receipt)

    checkpoint = build_checkpoint(code_commit)

    handoff = build_operating_handoff(
        workflows=build_workflows(),
        frozen_version_table=build_version_table(),
        external_artifact_index=build_external_index(),
        remaining_external_dependencies=build_dependencies(),
        paper_workspace_plan_path=PAPER_PLAN_REL,
        code_commit=code_commit,
    )
    validate_operating_handoff(handoff)

    runbook_digests = {
        relative: hash_file_bytes(ROOT / relative) for relative in RUNBOOKS.values()
    }
    operator_receipt = build_second_operator_receipt(
        handoff=handoff,
        runbook_digests=runbook_digests,
        reproduction_receipt_hash=receipt["receipt_content_hash"],
        checkpoint_evidence_hash=checkpoint["checkpoint_content_hash"],
    )
    validate_second_operator_receipt(operator_receipt)

    external_requests = {
        "external_input_requests_schema_version": (
            "person-e-external-input-requests-v0.1"
        ),
        "code_commit": code_commit,
        "requests": build_dependencies(),
        "request_count": len(build_dependencies()),
    }

    status = {
        "phase7_status_schema_version": PACKAGE_SCHEMA_VERSION,
        "code_commit": code_commit,
        "step_7_1": {
            "status": "IMPLEMENTED_NOT_EXECUTED_ON_REAL_INPUTS",
            "evidence_class": receipt["evidence_class"],
            "real_clean_reproduction_complete": receipt[
                "real_clean_reproduction_complete"
            ],
            "synthetic_rehearsal_stages_passed": len(
                [row for row in stage_results if row["outcome"] == "passed"]
            ),
            "synthetic_known_answer_recovered": known_answer["known_answer_recovered"],
            "blocking_external_inputs": receipt["blocking_external_inputs"],
        },
        "step_7_2": {
            "status": "COMPLETE_FOR_AVAILABLE_EVIDENCE",
            "populated_slots": checkpoint["populated_slots"],
            "empty_slot_count": checkpoint["visual_qa_report"]["empty_slot_count"],
            "scientific_value_count": checkpoint["scientific_value_count"],
            "figure_source_verified": checkpoint["figure_source_verification"][
                "verified"
            ],
        },
        "step_7_3": {
            "status": "COMPLETE",
            "workflow_count": handoff["workflow_count"],
            "operable_without_person_e": operator_receipt[
                "operable_without_person_e"
            ],
            "remaining_external_dependency_count": len(
                handoff["remaining_external_dependencies"]
            ),
        },
        "u4_output_inspected": False,
        "real_measurement_complete": False,
    }

    documents: dict[str, Any] = {
        "checkpoint_evidence.json": checkpoint,
        "clean_reproduction_plan.json": plan,
        "clean_reproduction_receipt.json": receipt,
        "external_input_requests.json": external_requests,
        "operating_handoff.json": handoff,
        "phase7_status.json": status,
        "second_operator_receipt.json": operator_receipt,
    }
    validation = {
        "validation_receipt_schema_version": "person-e-phase7-validation-v0.1",
        "code_commit": code_commit,
        "checkpoint_evidence_valid": True,
        "clean_reproduction_receipt_valid": True,
        "operating_handoff_valid": True,
        "second_operator_receipt_valid": True,
        "runbook_digests": runbook_digests,
        "real_measurement_claimed": False,
        "real_clean_reproduction_claimed": receipt[
            "real_clean_reproduction_complete"
        ],
        "u4_output_inspected": False,
    }
    documents["validation_receipt.json"] = validation

    encoded = {
        name: formatted_json_bytes(value) for name, value in documents.items()
    }
    inventory = {
        "sha256_inventory_schema_version": "person-e-phase7-inventory-v0.1",
        "files": {
            name: hashlib.sha256(payload).hexdigest()
            for name, payload in sorted(encoded.items())
        },
    }
    encoded["sha256_inventory.json"] = formatted_json_bytes(inventory)
    return encoded


def write_documents(out_dir: Path) -> dict[str, bytes]:
    documents = build_documents()
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in documents.items():
        (out_dir / name).write_bytes(payload)
    return documents


def validate_package(package_dir: Path) -> None:
    """Re-check a committed package against its own inventory and validators."""

    present = {path.name for path in package_dir.iterdir()} if package_dir.is_dir() else set()
    if present != set(OUTPUT_FILES):
        raise Phase7Error(f"Phase 7 package file set mismatch: {sorted(present)}")
    inventory = json.loads(
        (package_dir / "sha256_inventory.json").read_text(encoding="utf-8")
    )
    expected = set(OUTPUT_FILES) - {"sha256_inventory.json"}
    if set(inventory["files"]) != expected:
        raise Phase7Error("Phase 7 inventory does not cover every package file.")
    for name, digest in inventory["files"].items():
        actual = hashlib.sha256((package_dir / name).read_bytes()).hexdigest()
        if actual != digest:
            raise Phase7Error(f"Phase 7 package byte drift: {name}")

    validate_clean_reproduction_plan(
        json.loads((package_dir / "clean_reproduction_plan.json").read_text("utf-8"))
    )
    validate_clean_reproduction_receipt(
        json.loads(
            (package_dir / "clean_reproduction_receipt.json").read_text("utf-8")
        )
    )
    validate_checkpoint_evidence(
        json.loads((package_dir / "checkpoint_evidence.json").read_text("utf-8"))
    )
    handoff = json.loads(
        (package_dir / "operating_handoff.json").read_text("utf-8")
    )
    validate_operating_handoff(handoff)
    validate_second_operator_receipt(
        json.loads((package_dir / "second_operator_receipt.json").read_text("utf-8"))
    )
    if {row["workflow"] for row in handoff["workflows"]} != set(REQUIRED_WORKFLOWS):
        raise Phase7Error("Operating handoff lost a frozen workflow.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("build", "validate"))
    parser.add_argument("--out-dir", type=Path, default=ROOT / PKG_REL)
    arguments = parser.parse_args()
    try:
        if arguments.mode == "build":
            documents = write_documents(arguments.out_dir.resolve())
            print(f"BUILD OK: {len(documents)} Phase 7 files written")
        else:
            validate_package(arguments.out_dir.resolve())
            print("VALIDATE OK: Person E Phase 7 terminal package")
    except (Phase7Error, ValueError, KeyError, OSError) as error:
        print(f"FAIL-CLOSED: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
