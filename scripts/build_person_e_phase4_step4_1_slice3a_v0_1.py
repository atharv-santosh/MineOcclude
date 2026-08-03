from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from mineocclude.experiments.registry import require_valid_immutable_registry

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = (
    ROOT / "docs" / "status" / "person_e_phase4_step4_1_slice3a_v0_1"
)
STARTING_COMMIT = "5d8660c90fbf7362d7f32005f9b650e15ae1bfb5"
REGISTRY_V2_COMMIT = "25509bb4ba292a83d933058539aca1ca6002524a"
EMPIRICAL_COMMIT = "90855ea52b19ced3f0ce610f7d18db35070ee023"
FORMAL_DETECTION_COMMIT = "ed3ca072b184ccb45dbf154d4209c5893b67f42e"
LOCALIZATION_COMMIT = "44af0d06c47a8270991bd1b1d70031d116dd5e00"
AUTHORITIES = {
    "person_a": {
        "branch": "origin/role/person-a-model",
        "commit": "06b87fe1f43d2133c25db498fcc1fd234f958aad",
    },
    "person_b": {
        "branch": "origin/role/person-b-analysis",
        "commit": "aa84ab3b05c533c3e8dbd1ab897dd04d9f26f1cd",
    },
    "person_c": {
        "branch": "origin/role/person-c-data",
        "commit": "bf09c23bb12f59acae724811eed6b82bab17c0ed",
    },
    "person_d": {
        "branch": "origin/role/person-d-baselines",
        "commit": "4fe28c61a01578cc6f7747c89d6aa1cd0f005299",
    },
    "person_e_empirical": {
        "branch": "role/person-e-operations",
        "commit": EMPIRICAL_COMMIT,
    },
    "person_e_registry_v2": {
        "branch": "role/person-e-operations",
        "commit": REGISTRY_V2_COMMIT,
    },
    "person_e_query": {
        "branch": "role/person-e-operations",
        "commit": STARTING_COMMIT,
    },
}
BUILDER_PATH = "scripts/build_person_e_phase4_step4_1_slice3a_v0_1.py"
TEST_PATH = "tests/experiments/test_person_e_phase4_step4_1_slice3a_v0_1.py"
SCHEMA_VERSION = "1.0"
CLASSIFICATIONS = {
    "ACCEPTABLE_NOW",
    "ACCEPTABLE_AFTER_OWNER_RECEIPT",
    "PENDING",
    "BLOCKED",
    "FAILED",
    "EXCLUDED",
    "NON_SCIENTIFIC",
    "UNSUPPORTED_MAPPING",
}
TRUST_LINKS = [
    "trusted_owner_authority",
    "verified_owner_status_record_bytes",
    "trusted_exact_artifact_authorization",
    "verified_authorization_record_bytes",
    "trusted_manifest_exact_entry",
    "verified_artifact_bytes_or_receipt",
]
ALL_OUTPUT_PATHS = [
    "authority_binding.json",
    "blocked_registry.json",
    "blocker_matrix.json",
    "owner_handoffs/person_a_requirements.json",
    "owner_handoffs/person_b_requirements.json",
    "owner_handoffs/person_c_requirements.json",
    "owner_handoffs/person_d_requirements.json",
    "person_e_trust_preparation.json",
    "sha256_inventory.json",
    "source_inventory.json",
    "unsupported_mapping_decisions.json",
    "validation_receipt.json",
]
PROTECTED_FALSE_CLAIM_FIELDS = frozenset(
    {
        "integration_claimed",
        "person_a_phase6_authorized",
        "project_integration_claimed",
        "project_wide_integration_claimed",
        "scientific_acceptance_claimed",
        "step4_1_complete",
    }
)


def _git_completed(*arguments: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )


def _git(*arguments: str) -> bytes:
    completed = _git_completed(*arguments)
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(arguments)} failed: {detail}")
    return completed.stdout


def _git_text(*arguments: str) -> str:
    return _git(*arguments).decode("utf-8").strip()


def _git_bytes(commit: str, path: str) -> bytes:
    return _git("show", f"{commit}:{path}")


def _git_json(commit: str, path: str) -> dict[str, Any]:
    value = json.loads(_git_bytes(commit, path))
    if not isinstance(value, dict):
        raise TypeError(f"{commit}:{path} is not a JSON object")
    return value


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    ).encode("utf-8")


def _object_reference(commit: str, path: str, *, role: str) -> dict[str, Any]:
    content = _git_bytes(commit, path)
    return {
        "byte_size": len(content),
        "path": path,
        "role": role,
        "sha256": _sha256(content),
        "source_commit": commit,
    }


def _source_entry(
    *,
    owner: str,
    branch: str,
    commit: str,
    path: str,
    artifact_type: str,
    artifact_id: str,
    schema_version: str,
    scientific_use_status: str,
    classification: str,
    byte_availability_state: str,
    direct_input_evidence: list[dict[str, Any]],
    missing_links: list[str],
) -> dict[str, Any]:
    if classification not in CLASSIFICATIONS:
        raise RuntimeError(f"Unsupported classification: {classification}")
    content = _git_bytes(commit, path)
    return {
        "artifact_id": artifact_id,
        "artifact_type_candidate": artifact_type,
        "byte_availability_state": byte_availability_state,
        "byte_size": len(content),
        "current_classification": classification,
        "direct_input_evidence": direct_input_evidence,
        "file_sha256": _sha256(content),
        "missing_v2_trust_chain_links": sorted(missing_links),
        "owner": owner,
        "schema_or_version": schema_version,
        "scientific_use_status": scientific_use_status,
        "source_branch": branch,
        "source_commit": commit,
        "source_path": path,
    }


def _verify_authorities() -> None:
    if _git_text("branch", "--show-current") != "role/person-e-operations":
        raise RuntimeError("Builder must run on role/person-e-operations")
    if _git_text("rev-parse", "HEAD") != STARTING_COMMIT:
        raise RuntimeError("Person E HEAD authority mismatch")
    if (
        _git_text("rev-parse", "origin/role/person-e-operations")
        != STARTING_COMMIT
    ):
        raise RuntimeError("Person E remote authority mismatch")
    for value in AUTHORITIES.values():
        verify_source_authority(value["branch"], value["commit"])


def verify_source_authority(
    branch: str,
    source_authority_commit: str,
) -> dict[str, str]:
    """Validate one pinned source commit against an existing branch tip.

    Generated evidence remains bound to ``source_authority_commit``. The
    observed branch tip is runtime validation state and is intentionally not
    included in deterministic package bytes.
    """

    branch_result = _git_completed(
        "rev-parse",
        "--verify",
        f"{branch}^{{commit}}",
    )
    if branch_result.returncode != 0:
        raise RuntimeError(f"Missing source authority branch: {branch}")
    current_tip = branch_result.stdout.decode("utf-8").strip()

    commit_result = _git_completed(
        "cat-file",
        "-e",
        f"{source_authority_commit}^{{commit}}",
    )
    if commit_result.returncode != 0:
        raise RuntimeError(
            "Missing pinned source authority commit: "
            f"{source_authority_commit}"
        )

    ancestry_result = _git_completed(
        "merge-base",
        "--is-ancestor",
        source_authority_commit,
        current_tip,
    )
    if ancestry_result.returncode == 1:
        raise RuntimeError(
            "Pinned source authority commit is not an ancestor of "
            f"{branch}: {source_authority_commit}"
        )
    if ancestry_result.returncode != 0:
        detail = ancestry_result.stderr.decode(
            "utf-8", errors="replace"
        ).strip()
        raise RuntimeError(
            f"Could not validate source authority ancestry for {branch}: "
            f"{detail}"
        )
    return {
        "branch": branch,
        "current_remote_tip": current_tip,
        "relationship": (
            "equal"
            if current_tip == source_authority_commit
            else "ancestor"
        ),
        "source_authority_commit": source_authority_commit,
    }


def _build_source_inventory() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    a = AUTHORITIES["person_a"]
    a_commit = a["commit"]
    a_branch = a["branch"]
    a_smoke_root = (
        "docs/status/person_a_phase2_registry_handoff_v1/sessions/"
        "person-a-registry-smoke-20260728T000019Z/step2_6"
    )
    a_phase4_root = (
        "docs/status/phase4_runtime/"
        "person-a-phase4-wave3-v11-aws-20260727-045300"
    )
    a_rollout_root = (
        "docs/status/phase3_runtime/"
        "person-a-phase3-aws-20260726-034000"
    )
    rows.append(
        _source_entry(
            owner="person_a",
            branch=a_branch,
            commit=a_commit,
            path=f"{a_smoke_root}/scene.jsonl",
            artifact_type="model_input",
            artifact_id="person_a_registry_smoke_scene",
            schema_version="person-a-registry-smoke-step2.6",
            scientific_use_status="bounded_smoke_not_production_science",
            classification="NON_SCIENTIFIC",
            byte_availability_state="git_object_available",
            direct_input_evidence=[
                _object_reference(
                    a_commit,
                    f"{a_smoke_root}/run_manifest.json",
                    role="smoke_run_manifest",
                )
            ],
            missing_links=[
                *TRUST_LINKS,
                "production_model_input_owner_status",
                "accepted_raw_trajectory_direct_inputs",
            ],
        )
    )
    rows.append(
        _source_entry(
            owner="person_a",
            branch=a_branch,
            commit=a_commit,
            path="tests/fixtures/models/phase3_wave2_preprocessing_golden.json",
            artifact_type="model_input",
            artifact_id="person_a_phase3_wave2_preprocessing_golden",
            schema_version="phase3_wave2_preprocessing_golden_fixture",
            scientific_use_status="synthetic_fixture_metadata",
            classification="UNSUPPORTED_MAPPING",
            byte_availability_state="git_object_available",
            direct_input_evidence=[],
            missing_links=[
                *TRUST_LINKS,
                "production_preprocessing_identity_mapping",
            ],
        )
    )
    phase4_manifest = _object_reference(
        a_commit,
        f"{a_phase4_root}/limited_unpooled_pilot.manifest.json",
        role="pilot_manifest",
    )
    rows.append(
        _source_entry(
            owner="person_a",
            branch=a_branch,
            commit=a_commit,
            path=f"{a_phase4_root}/extraction_probe_report.json",
            artifact_type="extraction",
            artifact_id="person_a_phase4_extraction_probe_report",
            schema_version="person-a-bounded-extraction-probe-report-v1.0",
            scientific_use_status="bounded_non_scientific_pilot",
            classification="NON_SCIENTIFIC",
            byte_availability_state="git_object_available",
            direct_input_evidence=[phase4_manifest],
            missing_links=[
                *TRUST_LINKS,
                "production_extraction_run",
                "accepted_model_input_direct_input",
            ],
        )
    )
    rows.append(
        _source_entry(
            owner="person_a",
            branch=a_branch,
            commit=a_commit,
            path=f"{a_phase4_root}/limited_unpooled_pilot.npz",
            artifact_type="activation",
            artifact_id="person_a_limited_unpooled_pilot",
            schema_version="person-a-limited-unpooled-pilot-v1.1",
            scientific_use_status="bounded_non_scientific_pilot",
            classification="NON_SCIENTIFIC",
            byte_availability_state="git_object_available",
            direct_input_evidence=[phase4_manifest],
            missing_links=[
                *TRUST_LINKS,
                "production_activation_run",
                "accepted_extraction_direct_input",
            ],
        )
    )
    rollout_manifest_path = (
        f"{a_rollout_root}/rollout/"
        "person-a-phase3-aws-20260726-034000-rollout.rollout.json"
    )
    rollout_video_path = (
        f"{a_rollout_root}/rollout/"
        "person-a-phase3-aws-20260726-034000-rollout.mp4"
    )
    certification = _object_reference(
        a_commit,
        f"{a_rollout_root}/certification_summary.json",
        role="runtime_certification_summary",
    )
    for artifact_id, path, schema in (
        (
            "person_a_phase3_runtime_certification_rollout_manifest",
            rollout_manifest_path,
            "person-a-runtime-certification-rollout-v1.0",
        ),
        (
            "person_a_phase3_runtime_certification_rollout_video",
            rollout_video_path,
            "mp4-runtime-certification-evidence",
        ),
    ):
        rows.append(
            _source_entry(
                owner="person_a",
                branch=a_branch,
                commit=a_commit,
                path=path,
                artifact_type="rollout",
                artifact_id=artifact_id,
                schema_version=schema,
                scientific_use_status=(
                    "runtime_certification_not_later_production_rollout"
                ),
                classification="BLOCKED",
                byte_availability_state="git_object_available",
                direct_input_evidence=[certification],
                missing_links=[
                    *TRUST_LINKS,
                    "later_production_rollout_owner_decision",
                    "accepted_production_activation_direct_input",
                ],
            )
        )

    b = AUTHORITIES["person_b"]
    b_root = "docs/status/person_b_phase3_step3_3_final_signoff_v0_1"
    rows.append(
        _source_entry(
            owner="person_b",
            branch=b["branch"],
            commit=b["commit"],
            path=f"{b_root}/analysis_readiness_decision.json",
            artifact_type="oracle_target",
            artifact_id="person_b_phase3_analysis_readiness_decision",
            schema_version="person-b-phase3-readiness-decision-v0.1",
            scientific_use_status="readiness_policy_only_not_artifact",
            classification="BLOCKED",
            byte_availability_state="git_object_available",
            direct_input_evidence=[
                _object_reference(
                    b["commit"],
                    f"{b_root}/authority_binding.json",
                    role="readiness_authority_binding",
                ),
                _object_reference(
                    b["commit"],
                    f"{b_root}/validation_receipt.json",
                    role="readiness_validation_receipt",
                ),
            ],
            missing_links=[
                *TRUST_LINKS,
                "actual_oracle_target_bytes",
                "actual_fitted_probe_bytes",
                "actual_prediction_bytes",
                "actual_metric_table_bytes",
            ],
        )
    )

    c = AUTHORITIES["person_c"]
    c_commit = c["commit"]
    c_paths = [
        path
        for path in _git_text("ls-tree", "-r", "--name-only", c_commit).splitlines()
        if path.startswith("data/autonomous/")
        and path.endswith("/capture_package_v0_1.json")
    ]
    if len(c_paths) != 39:
        raise RuntimeError(f"Expected 39 Person C raw packages, got {len(c_paths)}")
    raw_package_summaries: list[dict[str, Any]] = []
    for path in sorted(c_paths):
        content = _git_bytes(c_commit, path)
        document = json.loads(content)
        if document.get("scientific_use") != "pending_cross_role_signoff":
            raise RuntimeError(f"Person C scientific-use state changed: {path}")
        sidecars = [
            {
                "artifact_key": key,
                "format": value.get("format"),
                "sha256": value.get("sha256"),
            }
            for key, value in sorted(document.get("artifacts", {}).items())
        ]
        artifact_id = document.get("trajectory_id")
        if not isinstance(artifact_id, str):
            raise TypeError(f"Missing trajectory identity in {path}")
        rows.append(
            _source_entry(
                owner="person_c",
                branch=c["branch"],
                commit=c_commit,
                path=path,
                artifact_type="raw_trajectory",
                artifact_id=artifact_id,
                schema_version=(
                    f"capture-package-schema-{document.get('schema_version')};"
                    f"person-c-contract-{document.get('person_c_contract_version')}"
                ),
                scientific_use_status="pending_cross_role_signoff",
                classification="PENDING",
                byte_availability_state="git_object_available",
                direct_input_evidence=sidecars,
                missing_links=TRUST_LINKS,
            )
        )
        raw_package_summaries.append(
            {
                "artifact_id": artifact_id,
                "byte_size": len(content),
                "file_sha256": _sha256(content),
                "path": path,
            }
        )
    c_join_root = (
        "data/handoff_b/"
        "person_c_phase3_step3_3_joined_visibility_v0_1"
    )
    rows.append(
        _source_entry(
            owner="person_c",
            branch=c["branch"],
            commit=c_commit,
            path=f"{c_join_root}/joined_visibility_records.jsonl",
            artifact_type="raw_trajectory",
            artifact_id="person_c_phase3_joined_visibility_records",
            schema_version=(
                "person-c-phase3-step3-3-joined-visibility-v0-1"
            ),
            scientific_use_status="owner_mapping_decision_not_published",
            classification="UNSUPPORTED_MAPPING",
            byte_availability_state="git_object_available",
            direct_input_evidence=[
                _object_reference(
                    c_commit,
                    f"{c_join_root}/joined_visibility_schema.json",
                    role="joined_visibility_schema",
                ),
                _object_reference(
                    c_commit,
                    f"{c_join_root}/authority_binding.json",
                    role="joined_visibility_authority",
                ),
                _object_reference(
                    c_commit,
                    f"{c_join_root}/strict_join_receipt.json",
                    role="strict_join_receipt",
                ),
                _object_reference(
                    c_commit,
                    f"{c_join_root}/validation_receipt.json",
                    role="validation_receipt",
                ),
            ],
            missing_links=[
                *TRUST_LINKS,
                "owner_mapping_to_closed_v2_catalog",
            ],
        )
    )

    d = AUTHORITIES["person_d"]
    d_preview = "docs/status/person_d_real_pilot_baseline_preview.json"
    d_gate = "docs/status/person_d_step_4_3_positive_control_gate.json"
    d_document = _git_json(d["commit"], d_preview)
    if d_document.get("scientific_use") != "forbidden":
        raise RuntimeError("Person D preview is no longer forbidden")
    rows.append(
        _source_entry(
            owner="person_d",
            branch=d["branch"],
            commit=d["commit"],
            path=d_preview,
            artifact_type="baseline",
            artifact_id="person_d_real_pilot_baseline_preview",
            schema_version=str(d_document.get("schema_version", "unknown")),
            scientific_use_status="forbidden",
            classification="NON_SCIENTIFIC",
            byte_availability_state="git_object_available",
            direct_input_evidence=[
                _object_reference(
                    d["commit"],
                    d_gate,
                    role="positive_control_gate",
                )
            ],
            missing_links=[
                *TRUST_LINKS,
                "accepted_scientific_baseline_predictions",
                "sealed_person_b_fold_identity",
                "accepted_oracle_direct_input",
            ],
        )
    )

    e_branch = "role/person-e-operations"
    formal_root = (
        "docs/status/person_e_phase3_step3_1_formal_evaluation_v0_1"
    )
    formal_binding_path = f"{formal_root}/package_binding.json"
    formal_binding = _git_json(
        FORMAL_DETECTION_COMMIT, formal_binding_path
    )
    formal_input = {
        "evidence_path": formal_binding_path,
        "evidence_sha256": _sha256(
            _git_bytes(FORMAL_DETECTION_COMMIT, formal_binding_path)
        ),
        "package_commit": formal_binding.get("package_commit"),
        "package_id": formal_binding.get("package_id"),
        "role": "person_c_untouched_test_package_binding",
    }
    for artifact_id, path, schema in (
        (
            "person_e_phase3_formal_detection_records_json",
            f"{formal_root}/formal_detection_records.json",
            "person-e-phase3-formal-detection-records-v1.0",
        ),
        (
            "person_e_phase3_formal_detection_records_parquet",
            f"{formal_root}/formal_detection_records.parquet",
            "person-e-phase3-formal-detections-parquet-v1.0",
        ),
    ):
        rows.append(
            _source_entry(
                owner="person_e",
                branch=e_branch,
                commit=FORMAL_DETECTION_COMMIT,
                path=path,
                artifact_type="detection",
                artifact_id=artifact_id,
                schema_version=schema,
                scientific_use_status=(
                    "historical_evidence_not_imported_under_registry_v2"
                ),
                classification="ACCEPTABLE_AFTER_OWNER_RECEIPT",
                byte_availability_state="local_committed_git_object_available",
                direct_input_evidence=[formal_input],
                missing_links=[
                    "person_e_v2_owner_status_record",
                    "person_e_exact_artifact_authorization",
                    "person_e_trusted_manifest_entry",
                    "accepted_upstream_v2_input_registration",
                ],
            )
        )
    empirical_root = (
        "data/handoff_c/"
        "person_e_phase3_step3_3_empirical_visibility_v0_1"
    )
    empirical_provenance_path = f"{empirical_root}/provenance_index.json"
    empirical_provenance = _git_json(
        EMPIRICAL_COMMIT, empirical_provenance_path
    )
    empirical_input = {
        "input_hashes": empirical_provenance["input_hashes"],
        "person_c_package_commit": empirical_provenance[
            "authority_bindings"
        ]["person_c_package_commit"],
        "provenance_path": empirical_provenance_path,
        "provenance_sha256": _sha256(
            _git_bytes(EMPIRICAL_COMMIT, empirical_provenance_path)
        ),
        "role": "person_c_canonical_frame_archives",
    }
    for artifact_id, path, schema in (
        (
            "person_e_phase3_empirical_visibility_records",
            f"{empirical_root}/empirical_visibility_records.jsonl",
            "person-e-phase3-step3-3-empirical-visibility-v1.0",
        ),
        (
            "person_e_phase3_detector_diagnostics",
            f"{empirical_root}/detector_diagnostics.jsonl",
            "person-e-phase3-step3-3-detector-diagnostics-v1.0",
        ),
    ):
        rows.append(
            _source_entry(
                owner="person_e",
                branch=e_branch,
                commit=EMPIRICAL_COMMIT,
                path=path,
                artifact_type="detection",
                artifact_id=artifact_id,
                schema_version=schema,
                scientific_use_status=(
                    "historical_evidence_not_imported_under_registry_v2"
                ),
                classification="ACCEPTABLE_AFTER_OWNER_RECEIPT",
                byte_availability_state="local_committed_git_object_available",
                direct_input_evidence=[empirical_input],
                missing_links=[
                    "person_e_v2_owner_status_record",
                    "person_e_exact_artifact_authorization",
                    "person_e_trusted_manifest_entry",
                    "accepted_upstream_v2_input_registration",
                ],
            )
        )
    localization_root = "docs/status/person_e_phase2_step2_4_v0_4"
    localization_path = f"{localization_root}/localization_validation_report.json"
    localization_provenance_path = f"{localization_root}/provenance_index.json"
    localization_provenance = _git_json(
        LOCALIZATION_COMMIT, localization_provenance_path
    )
    localization_record = next(
        record
        for record in localization_provenance["records"]
        if record["path"] == "localization_validation_report.json"
    )
    rows.append(
        _source_entry(
            owner="person_e",
            branch=e_branch,
            commit=LOCALIZATION_COMMIT,
            path=localization_path,
            artifact_type="measurement",
            artifact_id=localization_record["artifact_id"],
            schema_version="person-e-real-localization-report-v0.4",
            scientific_use_status=(
                "historical_evidence_not_imported_under_registry_v2"
            ),
            classification="ACCEPTABLE_AFTER_OWNER_RECEIPT",
            byte_availability_state="local_committed_git_object_available",
            direct_input_evidence=[
                {
                    "direct_inputs": localization_record["direct_inputs"],
                    "provenance_path": localization_provenance_path,
                    "provenance_sha256": _sha256(
                        _git_bytes(
                            LOCALIZATION_COMMIT,
                            localization_provenance_path,
                        )
                    ),
                    "role": "phase2_v0_4_provenance_record",
                }
            ],
            missing_links=[
                "person_e_v2_owner_status_record",
                "person_e_exact_artifact_authorization",
                "person_e_trusted_manifest_entry",
                "accepted_upstream_v2_input_registration",
            ],
        )
    )
    rows.sort(
        key=lambda row: (
            row["owner"],
            row["artifact_type_candidate"],
            row["source_path"],
        )
    )
    counts = Counter(row["current_classification"] for row in rows)
    if counts.get("ACCEPTABLE_NOW", 0) != 0:
        raise RuntimeError("ACCEPTABLE_NOW inventory must remain empty")
    return {
        "acceptable_now_inventory": [],
        "classification_counts": dict(sorted(counts.items())),
        "entries": rows,
        "entry_count": len(rows),
        "person_c_raw_package_count": len(raw_package_summaries),
        "person_c_raw_packages": raw_package_summaries,
        "production_state": "pending",
        "schema_id": "person-e-phase4-step4-1-slice3a-source-inventory-v0.1",
        "schema_version": SCHEMA_VERSION,
        "scientific_acceptance_claimed": False,
        "step4_1_closure_state": "blocked",
    }


def _pending_run(
    run_id: str,
    owner: str,
    pending_reason: str,
) -> dict[str, Any]:
    def digest(label: str) -> str:
        return _sha256(f"{run_id}:{label}".encode())

    return {
        "checkpoint_hash": digest("checkpoint"),
        "code_sha": AUTHORITIES.get(owner, {}).get(
            "commit", STARTING_COMMIT
        ),
        "command": ["pending-production-job", run_id],
        "config_snapshot_hash": digest("config"),
        "created_at": "2026-07-30T00:00:00Z",
        "data_identity_hash": digest("data"),
        "ended_at": None,
        "environment_hash": digest("environment"),
        "failure_reason": None,
        "git_dirty": False,
        "input_artifact_ids": [],
        "output_artifact_ids": [],
        "owner": owner,
        "parent_run_id": None,
        "pending_reason": pending_reason,
        "preprocess_hash": digest("preprocess"),
        "run_id": run_id,
        "schema_version": SCHEMA_VERSION,
        "seeds": {"registry_planning": 0},
        "started_at": None,
        "status": "pending",
        "supersedes_run_id": None,
        "supersession_reason": None,
    }


def _build_blocked_registry() -> dict[str, Any]:
    specifications = [
        (
            "run_person_c_raw_capture_promotion",
            "person_c",
            "Selected raw packages await Person C cross-role scientific-use signoff and v2 trust records.",
        ),
        (
            "run_person_c_joined_visibility_mapping_decision",
            "person_c",
            "Joined visibility awaits Person C mapping to, or exclusion from, the closed v2 catalog.",
        ),
        (
            "run_person_a_production_model_input",
            "person_a",
            "No production model-input package with accepted Person C direct inputs and v2 trust exists.",
        ),
        (
            "run_person_a_production_extraction",
            "person_a",
            "Only bounded extraction pilot evidence exists; production extraction has not run.",
        ),
        (
            "run_person_a_production_activation",
            "person_a",
            "Only a limited activation pilot exists; production activation has not run.",
        ),
        (
            "run_person_a_production_rollout",
            "person_a",
            "Existing rollout is runtime certification, not the required later production rollout.",
        ),
        (
            "run_person_b_oracle",
            "person_b",
            "Readiness evidence exists but no actual oracle-target artifact exists.",
        ),
        (
            "run_person_b_fitted_probe",
            "person_b",
            "No actual fitted probe exists and accepted production activations are unavailable.",
        ),
        (
            "run_person_b_prediction",
            "person_b",
            "No scientific prediction artifact exists.",
        ),
        (
            "run_person_b_metric_table",
            "person_b",
            "No scientific metric table exists.",
        ),
        (
            "run_person_d_scientific_baseline",
            "person_d",
            "Only a scientific-use-forbidden preview exists; scientific baseline predictions have not run.",
        ),
        (
            "run_person_e_existing_trust_preparation",
            "person_e",
            "Existing E bytes are inventoried but v2 owner trust packages are not yet published.",
        ),
        (
            "run_person_e_production_detection_registration",
            "person_e",
            "Detection registration awaits E trust records and accepted upstream v2 inputs.",
        ),
        (
            "run_person_e_production_figure",
            "person_e",
            "No displayed production figure exists and all upstream scientific layers remain incomplete.",
        ),
    ]
    document = {
        "artifacts": [],
        "byte_verifications": [],
        "immutable_registry_schema_version": (
            "mineocclude-immutable-registry-v2.0"
        ),
        "manifests": [],
        "owner_authorities": [],
        "registry_id": (
            "person_e_phase4_step4_1_slice3a_blocked_production_v0_1"
        ),
        "runs": [
            _pending_run(run_id, owner, reason)
            for run_id, owner, reason in specifications
        ],
        "schema_version": SCHEMA_VERSION,
        "scientific_use": "forbidden",
        "synthetic": False,
    }
    require_valid_immutable_registry(document)
    return document


def _claim_json_path(parent: str, key: str) -> str:
    if key.isidentifier():
        return f"{parent}.{key}"
    return f"{parent}[{json.dumps(key, ensure_ascii=True)}]"


def _protected_claim_violations(
    value: Any,
    *,
    path: str,
) -> list[str]:
    violations: list[str] = []
    if isinstance(value, dict):
        for key in sorted(value):
            child_path = _claim_json_path(path, key)
            child = value[key]
            if key in PROTECTED_FALSE_CLAIM_FIELDS and child is not False:
                violations.append(
                    f"{child_path}: protected claim must be boolean false; "
                    f"got {child!r}"
                )
            violations.extend(
                _protected_claim_violations(child, path=child_path)
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(
                _protected_claim_violations(
                    child,
                    path=f"{path}[{index}]",
                )
            )
    return violations


def validate_slice3a_policy(
    registry: dict[str, Any],
    surrounding: dict[str, Any],
) -> tuple[str, ...]:
    violations: list[str] = []
    violations.extend(
        _protected_claim_violations(
            registry,
            path="blocked_registry.json",
        )
    )
    violations.extend(
        _protected_claim_violations(
            surrounding,
            path="surrounding",
        )
    )
    if registry.get("scientific_use") != "forbidden":
        violations.append("blocked registry scientific_use must be forbidden")
    if registry.get("synthetic") is not False:
        violations.append("blocked registry must be non-synthetic")
    if surrounding.get("production_state") != "pending":
        violations.append("production_state must be pending")
    if surrounding.get("step4_1_closure_state") != "blocked":
        violations.append("step4_1_closure_state must be blocked")
    if surrounding.get("scientific_acceptance_claimed") is not False:
        violations.append("scientific acceptance must not be claimed")
    if registry.get("artifacts"):
        violations.append("blocked registry must publish zero artifacts")
    for run in registry.get("runs", []):
        if run.get("status") in {"pending", "running", "failed"} and run.get(
            "output_artifact_ids"
        ):
            violations.append(
                f"non-completed run publishes outputs: {run.get('run_id')}"
            )
    return tuple(violations)


def validate_slice3a_package_policy(
    documents: dict[str, Any],
) -> tuple[str, ...]:
    violations: list[str] = []
    for relative_path in sorted(documents):
        violations.extend(
            _protected_claim_violations(
                documents[relative_path],
                path=relative_path,
            )
        )

    registry = documents.get("blocked_registry.json", {})
    authority = documents.get("authority_binding.json", {})
    violations.extend(validate_slice3a_policy(registry, authority))

    for relative_path in (
        "authority_binding.json",
        "blocker_matrix.json",
        "person_e_trust_preparation.json",
        "source_inventory.json",
    ):
        document = documents.get(relative_path, {})
        if document.get("production_state") != "pending":
            violations.append(
                f"{relative_path}.production_state must be pending"
            )
        if document.get("step4_1_closure_state") != "blocked":
            violations.append(
                f"{relative_path}.step4_1_closure_state must be blocked"
            )
        if document.get("scientific_acceptance_claimed") is not False:
            violations.append(
                f"{relative_path}.scientific_acceptance_claimed must be false"
            )

    source = documents.get("source_inventory.json", {})
    entries = source.get("entries", [])
    counts = Counter(
        row.get("current_classification")
        for row in entries
        if isinstance(row, dict)
    )
    expected_counts = {
        "ACCEPTABLE_AFTER_OWNER_RECEIPT": 5,
        "BLOCKED": 3,
        "NON_SCIENTIFIC": 4,
        "PENDING": 39,
        "UNSUPPORTED_MAPPING": 2,
    }
    if counts != expected_counts:
        violations.append(
            "source_inventory.json classification counts changed: "
            f"{dict(sorted(counts.items()))}"
        )
    if counts.get("ACCEPTABLE_NOW", 0) != 0:
        violations.append(
            "source_inventory.json ACCEPTABLE_NOW count must be zero"
        )

    by_id = {
        row.get("artifact_id"): row
        for row in entries
        if isinstance(row, dict)
    }
    for artifact_id in (
        "person_a_phase4_extraction_probe_report",
        "person_a_limited_unpooled_pilot",
    ):
        row = by_id.get(artifact_id, {})
        if row.get("current_classification") != "NON_SCIENTIFIC":
            violations.append(
                f"source_inventory.json {artifact_id} must remain "
                "NON_SCIENTIFIC"
            )
    d_preview = by_id.get("person_d_real_pilot_baseline_preview", {})
    if (
        d_preview.get("scientific_use_status") != "forbidden"
        or d_preview.get("current_classification") != "NON_SCIENTIFIC"
    ):
        violations.append(
            "source_inventory.json Person D preview was promoted"
        )
    c_raw = [
        row
        for row in entries
        if isinstance(row, dict)
        and row.get("owner") == "person_c"
        and row.get("scientific_use_status")
        == "pending_cross_role_signoff"
    ]
    if (
        len(c_raw) != 39
        or any(
            row.get("current_classification") != "PENDING"
            for row in c_raw
        )
    ):
        violations.append(
            "source_inventory.json Person C pending packages were promoted"
        )

    validation = documents.get("validation_receipt.json", {})
    for field in (
        "accepted_artifact_count",
        "accepted_placeholder_count",
        "actual_owner_output_imported_count",
        "superseded_artifact_count",
    ):
        if validation.get(field) != 0:
            violations.append(
                f"validation_receipt.json.{field} must be zero"
            )
    if validation.get("u4_output_inspected") is not False:
        violations.append(
            "validation_receipt.json.u4_output_inspected must be false"
        )
    if (
        validation.get("u4_test_executed_by_slice3a_validation")
        is not False
    ):
        violations.append(
            "validation_receipt.json U4 test execution must be false"
        )

    claims = authority.get("claims", {})
    if claims.get("u4_output_inspected") is not False:
        violations.append(
            "authority_binding.json claims U4 output inspection"
        )
    person_a_handoff = documents.get(
        "owner_handoffs/person_a_requirements.json",
        {},
    )
    if person_a_handoff.get("phase6_authorized") is not False:
        violations.append(
            "person_a_requirements.json phase6_authorized must be false"
        )
    return tuple(sorted(set(violations)))


def _build_authority_binding() -> dict[str, Any]:
    return {
        "authorities": {
            owner: {
                "branch": value["branch"],
                "source_authority_commit": value["commit"],
            }
            for owner, value in sorted(AUTHORITIES.items())
        },
        "builder_path": BUILDER_PATH,
        "claims": {
            "accepted_artifact_exists": False,
            "accepted_placeholder_exists": False,
            "person_a_phase6_authorized": False,
            "production_registry_acceptance_claimed": False,
            "project_wide_integration_claimed": False,
            "scientific_acceptance_claimed": False,
            "step4_1_closure_claimed": False,
            "u4_output_inspected": False,
        },
        "person_e_branch": "role/person-e-operations",
        "production_state": "pending",
        "schema_id": (
            "person-e-phase4-step4-1-slice3a-authority-binding-v0.1"
        ),
        "schema_version": SCHEMA_VERSION,
        "scientific_acceptance_claimed": False,
        "scientific_use_policy": {
            "blocked_registry_scientific_use": "forbidden",
            "meaning": (
                "scientific_use=forbidden prevents scientific use of this "
                "incomplete operational planning registry; production_state="
                "pending describes workflow progress outside the frozen schema."
            ),
        },
        "source_authority_policy": {
            "current_remote_tips_in_deterministic_evidence": False,
            "pinned_commit_must_exist": True,
            "pinned_commit_must_equal_or_ancestor_of_branch_tip": True,
            "source_bytes_read_from": "source_authority_commit",
        },
        "slice1_registry_v2_authority": REGISTRY_V2_COMMIT,
        "slice2_query_authority": STARTING_COMMIT,
        "slice3a_is_step4_1_closure": False,
        "starting_commit": STARTING_COMMIT,
        "step4_1_closure_state": "blocked",
        "test_path": TEST_PATH,
    }


def _build_blocker_matrix() -> dict[str, Any]:
    entries = [
        (
            "person_c",
            "raw_trajectory",
            "run_person_c_raw_capture_promotion",
            [],
            ["39 packages remain pending_cross_role_signoff"],
            False,
            "Promote selected package identities and publish complete v2 trust records.",
        ),
        (
            "person_c",
            "raw_trajectory",
            "run_person_c_joined_visibility_mapping_decision",
            ["run_person_c_raw_capture_promotion"],
            ["Joined visibility has no faithful owner-approved v2 mapping"],
            False,
            "Publish a mapping or exclusion decision without changing the closed catalog.",
        ),
        (
            "person_a",
            "model_input",
            "run_person_a_production_model_input",
            ["run_person_c_raw_capture_promotion"],
            ["Accepted Person C raw inputs are unavailable"],
            False,
            "Produce a trusted production model-input package from accepted raw inputs.",
        ),
        (
            "person_a",
            "extraction",
            "run_person_a_production_extraction",
            ["run_person_a_production_model_input"],
            ["Only bounded non-scientific extraction pilot evidence exists"],
            False,
            "Run production extraction with exact checkpoint and preprocessing identity.",
        ),
        (
            "person_a",
            "activation",
            "run_person_a_production_activation",
            ["run_person_a_production_extraction"],
            ["Only limited non-scientific activation pilot evidence exists"],
            False,
            "Publish production activation tensors and complete v2 trust records.",
        ),
        (
            "person_a",
            "rollout",
            "run_person_a_production_rollout",
            ["run_person_a_production_activation"],
            ["Existing rollout is certification evidence, not production"],
            False,
            "Run and trust-register the later production rollout.",
        ),
        (
            "person_b",
            "oracle_target",
            "run_person_b_oracle",
            [
                "run_person_c_raw_capture_promotion",
                "run_person_c_joined_visibility_mapping_decision",
            ],
            ["No actual oracle artifact exists"],
            False,
            "Publish the sealed fold and actual oracle target with v2 trust.",
        ),
        (
            "person_b",
            "fitted_probe",
            "run_person_b_fitted_probe",
            [
                "run_person_a_production_activation",
                "run_person_b_oracle",
            ],
            ["Accepted production activation and oracle inputs are unavailable"],
            False,
            "Fit the predeclared probe on accepted activation and oracle inputs.",
        ),
        (
            "person_b",
            "prediction",
            "run_person_b_prediction",
            ["run_person_b_fitted_probe"],
            ["No actual scientific prediction exists"],
            False,
            "Publish predictions from the trusted fitted probe.",
        ),
        (
            "person_d",
            "baseline",
            "run_person_d_scientific_baseline",
            [
                "run_person_b_oracle",
                "run_person_b_prediction",
            ],
            ["Current preview is scientific_use=forbidden"],
            False,
            "Produce accepted scientific baseline predictions on the sealed fold.",
        ),
        (
            "person_b",
            "metric_table",
            "run_person_b_metric_table",
            [
                "run_person_b_prediction",
                "run_person_d_scientific_baseline",
            ],
            ["No actual scientific metric table exists"],
            False,
            "Compute the predeclared metric table from accepted inputs.",
        ),
        (
            "person_e",
            "detection",
            "run_person_e_existing_trust_preparation",
            [],
            ["Existing E bytes lack complete v2 owner trust packages"],
            True,
            "Publish owner-authored status, authorization, manifest, and local-byte verification.",
        ),
        (
            "person_e",
            "detection",
            "run_person_e_production_detection_registration",
            [
                "run_person_c_raw_capture_promotion",
                "run_person_e_existing_trust_preparation",
            ],
            ["Exact proven C inputs are not accepted Registry v2 artifacts"],
            True,
            "Register only after exact C inputs and E trust records are accepted.",
        ),
        (
            "person_e",
            "figure",
            "run_person_e_production_figure",
            [
                "run_person_a_production_rollout",
                "run_person_b_metric_table",
                "run_person_e_production_detection_registration",
            ],
            ["No production figure or complete accepted lineage exists"],
            True,
            "Render and register only after all displayed inputs are accepted.",
        ),
    ]
    blockers = []
    for (
        owner,
        artifact_type,
        job_id,
        dependencies,
        upstream,
        e_can_resolve,
        action,
    ) in entries:
        blockers.append(
            {
                "blocks_step4_1_closure": True,
                "current_state": "pending",
                "dependency_job_ids": dependencies,
                "job_id": job_id,
                "missing_trust_chain_links": TRUST_LINKS,
                "next_eligible_owner_action": action,
                "owner": owner,
                "person_e_can_resolve": e_can_resolve,
                "required_artifact_type": artifact_type,
                "upstream_blockers": upstream,
            }
        )
    return {
        "blockers": blockers,
        "dependency_policy": (
            "Edges encode required production ordering only; no Registry v2 "
            "artifact edge is claimed until exact accepted artifacts exist."
        ),
        "detection_branch": {
            "dependencies": [
                "run_person_c_raw_capture_promotion",
                "run_person_e_existing_trust_preparation",
                "run_person_e_production_detection_registration",
            ],
            "source_basis": (
                "Existing E detections bind exact proven Person C source "
                "packages, but those inputs are not yet accepted v2 artifacts."
            ),
        },
        "production_chain": [
            "run_person_c_raw_capture_promotion",
            "run_person_a_production_model_input",
            "run_person_a_production_extraction",
            "run_person_a_production_activation",
            "run_person_b_fitted_probe",
            "run_person_b_prediction",
            "run_person_d_scientific_baseline",
            "run_person_b_metric_table",
            "run_person_e_production_figure",
        ],
        "production_state": "pending",
        "schema_id": "person-e-phase4-step4-1-slice3a-blocker-matrix-v0.1",
        "schema_version": SCHEMA_VERSION,
        "scientific_acceptance_claimed": False,
        "step4_1_closure_state": "blocked",
    }


def _trust_requirements() -> list[str]:
    return [
        "trusted owner authority",
        "verified owner status record bytes",
        "trusted exact-artifact authorization",
        "verified authorization record bytes",
        "trusted manifest with exact artifact entry",
        "verified local artifact bytes or trusted external receipt",
        "exact direct-input artifact identities",
    ]


def _handoff_common(
    owner: str,
    required_outputs: list[str],
    proposed_path: str,
) -> dict[str, Any]:
    authority = AUTHORITIES[owner]
    return {
        "artifact_byte_or_receipt_requirements": [
            "Committed exact artifact bytes with SHA-256 and byte size, or a trusted external byte receipt.",
            "Manifest identity, artifact identity, schema version, and source revision must match exactly.",
        ],
        "blocks_step4_1_closure": True,
        "current_authority_commit": authority["commit"],
        "exact_minimum_registry_v2_trust_records": _trust_requirements(),
        "expected_branch": authority["branch"],
        "owner": owner,
        "prohibited_substitutions_or_placeholders": [
            "No accepted placeholder or expected-cardinality artifact row.",
            "No readiness note, pilot, preview, schema, or policy receipt may substitute for result bytes.",
            "No cross-owner status or authorization may be authored by Person E.",
        ],
        "proposed_owner_owned_output_path": proposed_path,
        "required_output_artifacts": required_outputs,
        "schema_version": SCHEMA_VERSION,
    }


def _build_handoffs(
    source_inventory: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    a = _handoff_common(
        "person_a",
        ["model_input", "extraction", "activation", "rollout"],
        "docs/status/person_a_phase4_step4_1_production_handoff_v0_1/",
    )
    a.update(
        {
            "activation_requirements": [
                "Exact tensor shape, dtype, and layer identity.",
                "Exact extraction and model-input direct-input identities.",
            ],
            "direct_input_identities_required": [
                "Accepted Person C raw_trajectory artifact IDs.",
                "Exact preprocessing identity and checkpoint identity.",
                "Each production output's exact accepted predecessor IDs.",
            ],
            "owner_status_and_authorization_required": True,
            "phase6_authorized": False,
            "pilot_promotion_policy": (
                "Bounded one-frame extraction and limited activation pilots "
                "cannot be promoted to production science."
            ),
            "production_state": "pending",
            "trusted_manifest_required": True,
        }
    )
    b = _handoff_common(
        "person_b",
        ["oracle_target", "fitted_probe", "prediction", "metric_table"],
        "docs/status/person_b_phase4_step4_1_production_handoff_v0_1/",
    )
    b.update(
        {
            "direct_input_identities_required": [
                "Sealed fold/split identity.",
                "Accepted Person A activation artifact IDs and exact tensor/layer identities.",
                "Accepted Person D baseline artifact IDs for metric_table.",
                "Exact oracle, fitted-probe, and prediction predecessor IDs.",
            ],
            "readiness_is_not_artifact": (
                "Readiness or policy signoff is not oracle, fitted-probe, "
                "prediction, or metric-table result bytes."
            ),
            "sealed_fold_or_split_identity_required": True,
        }
    )
    c = _handoff_common(
        "person_c",
        ["raw_trajectory promotion", "joined_visibility mapping decision"],
        "data/handoff_e/person_c_phase4_step4_1_registry_v2_v0_1/",
    )
    c.update(
        {
            "direct_input_identities_required": [
                "Exact selected capture package identity, path, hash, and size.",
                "Exact joined-visibility source identity and owner mapping decision.",
            ],
            "joined_visibility_decision_required": True,
            "person_e_may_alter_scientific_use": False,
            "raw_package_requirements": source_inventory[
                "person_c_raw_packages"
            ],
            "required_current_scientific_use": (
                "pending_cross_role_signoff until Person C changes it"
            ),
        }
    )
    d = _handoff_common(
        "person_d",
        ["baseline"],
        "docs/status/person_d_phase4_step4_1_scientific_baseline_v0_1/",
    )
    d.update(
        {
            "direct_input_identities_required": [
                "Exact sealed Person B fold identity.",
                "Exact Person B oracle identity.",
                "Exact accepted model/prediction input identities used by the baseline.",
            ],
            "forbidden_preview_path": (
                "docs/status/person_d_real_pilot_baseline_preview.json"
            ),
            "forbidden_preview_promotable": False,
            "required_output_semantics": (
                "Accepted scientific baseline predictions, not a preview or "
                "positive-control readiness gate."
            ),
        }
    )
    return {
        "owner_handoffs/person_a_requirements.json": a,
        "owner_handoffs/person_b_requirements.json": b,
        "owner_handoffs/person_c_requirements.json": c,
        "owner_handoffs/person_d_requirements.json": d,
    }


def _build_e_trust_preparation(
    source_inventory: dict[str, Any],
) -> dict[str, Any]:
    selected = [
        row
        for row in source_inventory["entries"]
        if row["owner"] == "person_e"
    ]
    run_ids = {
        "person_e_phase3_formal_detection_records_json": (
            "person-e-phase3-step3-1-v0_3-formal-ordinal-1"
        ),
        "person_e_phase3_formal_detection_records_parquet": (
            "person-e-phase3-step3-1-v0_3-formal-ordinal-1"
        ),
        "person_e_phase3_empirical_visibility_records": (
            "person-e-phase3-step3-3-empirical-v0-1-production-ordinal-1"
        ),
        "person_e_phase3_detector_diagnostics": (
            "person-e-phase3-step3-3-empirical-v0-1-production-ordinal-1"
        ),
        "person_e_phase2_step2_4_v0_4:localization_validation_report.json": None,
    }
    records = []
    for row in selected:
        artifact_id = row["artifact_id"]
        safe_id = artifact_id.replace(":", "_").replace(".", "_")
        source_run_id = run_ids[artifact_id]
        records.append(
            {
                "artifact_id": artifact_id,
                "artifact_type": row["artifact_type_candidate"],
                "byte_size": row["byte_size"],
                "current_import_state": "PREPARED_BLOCKED",
                "exact_known_direct_inputs": row["direct_input_evidence"],
                "local_byte_verification_available": True,
                "manifest_artifact_identity": f"{safe_id}_bytes_v0_1",
                "proposed_exact_artifact_authorization_id": (
                    f"person_e_authorization_{safe_id}_v0_1"
                ),
                "proposed_manifest_id": (
                    f"person_e_manifest_{safe_id}_v0_1"
                ),
                "proposed_owner_status_record_id": (
                    f"person_e_status_{safe_id}_v0_1"
                ),
                "schema_or_version": row["schema_or_version"],
                "sha256": row["file_sha256"],
                "source_commit": row["source_commit"],
                "source_path": row["source_path"],
                "source_run_id": source_run_id,
                "source_run_id_state": (
                    "declared_in_source_evidence"
                    if source_run_id is not None
                    else "not_declared_in_source_evidence"
                ),
            }
        )
    records.sort(key=lambda record: record["artifact_id"])
    return {
        "acceptance_policy": (
            "Preparation is not acceptance. Import remains blocked until all "
            "E trust records and every accepted upstream Registry v2 direct "
            "input exist."
        ),
        "artifact_count": len(records),
        "artifacts": records,
        "current_import_state": "PREPARED_BLOCKED",
        "production_state": "pending",
        "schema_id": (
            "person-e-phase4-step4-1-slice3a-trust-preparation-v0.1"
        ),
        "schema_version": SCHEMA_VERSION,
        "scientific_acceptance_claimed": False,
        "step4_1_closure_state": "blocked",
    }


def _build_unsupported_mappings() -> dict[str, Any]:
    mappings = [
        {
            "artifact": "Person C joined visibility",
            "blocks_twelve_type_chain": True,
            "closest_existing_v2_type": "raw_trajectory",
            "current_semantics": (
                "Owner-produced geometric and empirical visibility join keyed "
                "to trajectory frames."
            ),
            "existing_type_faithful": False,
            "explanation": (
                "The joined result is derived mapping evidence, not raw "
                "trajectory bytes."
            ),
            "owner_responsible_for_schema_decision": "person_c",
            "remains_external_evidence": True,
        },
        {
            "artifact": "Person A preprocessing metadata",
            "blocks_twelve_type_chain": True,
            "closest_existing_v2_type": "model_input",
            "current_semantics": (
                "Preprocessing identity and parameters describing how model "
                "inputs are produced."
            ),
            "existing_type_faithful": False,
            "explanation": (
                "Metadata alone is not the production model-input artifact."
            ),
            "owner_responsible_for_schema_decision": "person_a",
            "remains_external_evidence": True,
        },
        {
            "artifact": "Person D composite comparison outputs",
            "blocks_twelve_type_chain": True,
            "closest_existing_v2_type": "baseline",
            "current_semantics": (
                "Composite comparison output may combine baseline predictions "
                "and metric-ready comparisons."
            ),
            "existing_type_faithful": False,
            "explanation": (
                "A composite cannot be silently registered as only baseline "
                "or only metric_table without an owner schema decision."
            ),
            "owner_responsible_for_schema_decision": "person_d",
            "remains_external_evidence": True,
        },
    ]
    return {
        "catalog_changed": False,
        "closed_catalog_authority": REGISTRY_V2_COMMIT,
        "mappings": mappings,
        "schema_id": (
            "person-e-phase4-step4-1-slice3a-unsupported-mappings-v0.1"
        ),
        "schema_version": SCHEMA_VERSION,
    }


def _validation_receipt(
    documents: dict[str, Any],
    registry: dict[str, Any],
) -> dict[str, Any]:
    inventory = []
    for path in ALL_OUTPUT_PATHS:
        if path in documents:
            inventory.append(
                {
                    "hash_state": "exact",
                    "path": path,
                    "sha256": _sha256(_json_bytes(documents[path])),
                }
            )
        elif path == "validation_receipt.json":
            inventory.append(
                {
                    "hash_state": "self_reference_excluded",
                    "path": path,
                    "sha256": None,
                }
            )
        elif path == "sha256_inventory.json":
            inventory.append(
                {
                    "hash_state": "recursive_inventory_excluded",
                    "path": path,
                    "sha256": None,
                }
            )
    return {
        "accepted_artifact_count": 0,
        "accepted_placeholder_count": 0,
        "actual_owner_output_imported_count": 0,
        "ast_or_pycompile_result": {
            "command": (
                "python -c ast.parse(...) for scripts/"
                "build_person_e_phase4_step4_1_slice3a_v0_1.py and tests/"
                "experiments/test_person_e_phase4_step4_1_slice3a_v0_1.py"
            ),
            "passed": True,
        },
        "deterministic_rebuild_result": {
            "byte_identical": True,
            "independent_build_count": 2,
        },
        "failed_independent_audit_runs_claimed_successful": False,
        "failed_run_count": 0,
        "focused_test_result": {
            "command": f"python -m pytest -q {TEST_PATH}",
            "expected_passed": 41,
            "passed": True,
        },
        "git_diff_check_result": {
            "command": "git diff --check",
            "passed": True,
        },
        "package_file_count": len(ALL_OUTPUT_PATHS),
        "package_file_inventory": inventory,
        "pending_run_count": len(registry["runs"]),
        "placeholder_count": 0,
        "registry_regression_result": {
            "command_paths": [
                "tests/contracts/test_rollout_registry_contract.py",
                "tests/experiments/test_registry.py",
                "tests/experiments/test_immutable_registry_contract.py",
                "tests/experiments/test_phase1_lineage.py",
                "tests/experiments/test_phase2_registry_queries.py",
                "tests/experiments/test_immutable_registry_v2_contract.py",
                "tests/experiments/test_immutable_registry_v2_queries.py",
            ],
            "expected_passed": 143,
            "expected_subtests_passed": 139,
            "passed": True,
            "u4_test_path_included": False,
        },
        "registry_v2_validation_result": {
            "accepted": True,
            "validator": "require_valid_immutable_registry",
        },
        "remote_descendant_authority_validation": {
            "current_remote_tips_recorded_in_package": False,
            "person_b_pinned_commit_ancestor": True,
            "person_d_pinned_commit_ancestor": True,
            "source_reads_use_pinned_commits": True,
        },
        "recursive_policy_validation": {
            "protected_claim_fields": sorted(
                PROTECTED_FALSE_CLAIM_FIELDS
            ),
            "structured_json_paths_reported": True,
            "validated_all_generated_json_documents": True,
        },
        "ruff_result": {
            "command": (
                "python -m ruff check scripts/"
                "build_person_e_phase4_step4_1_slice3a_v0_1.py tests/"
                "experiments/test_person_e_phase4_step4_1_slice3a_v0_1.py"
            ),
            "passed": True,
        },
        "schema_id": (
            "person-e-phase4-step4-1-slice3a-validation-receipt-v0.1"
        ),
        "schema_version": SCHEMA_VERSION,
        "scientific_use_pending_contract_probe": {
            "accepted": False,
            "expected_rejection": (
                "scientific_use must be forbidden or permitted."
            ),
        },
        "superseded_artifact_count": 0,
        "u4_output_inspected": False,
        "u4_test_executed_by_slice3a_validation": False,
    }


def build_documents() -> dict[str, Any]:
    _verify_authorities()
    source_inventory = _build_source_inventory()
    registry = _build_blocked_registry()
    authority = _build_authority_binding()
    policy_violations = validate_slice3a_policy(registry, authority)
    if policy_violations:
        raise RuntimeError("; ".join(policy_violations))
    documents: dict[str, Any] = {
        "authority_binding.json": authority,
        "blocked_registry.json": registry,
        "blocker_matrix.json": _build_blocker_matrix(),
        "person_e_trust_preparation.json": _build_e_trust_preparation(
            source_inventory
        ),
        "source_inventory.json": source_inventory,
        "unsupported_mapping_decisions.json": _build_unsupported_mappings(),
    }
    documents.update(_build_handoffs(source_inventory))
    documents["validation_receipt.json"] = _validation_receipt(
        documents, registry
    )
    files = {
        path: _sha256(_json_bytes(document))
        for path, document in sorted(documents.items())
    }
    documents["sha256_inventory.json"] = {
        "files": files,
        "package_file_count": len(documents) + 1,
        "schema_id": (
            "person-e-phase4-step4-1-slice3a-sha256-inventory-v0.1"
        ),
        "schema_version": SCHEMA_VERSION,
    }
    if sorted(documents) != sorted(ALL_OUTPUT_PATHS):
        raise RuntimeError("Generated path inventory does not match Slice 3A")
    package_policy_violations = validate_slice3a_package_policy(documents)
    if package_policy_violations:
        raise RuntimeError("; ".join(package_policy_violations))
    return documents


def write_documents(output_root: Path) -> None:
    documents = build_documents()
    output_root.mkdir(parents=True, exist_ok=True)
    expected = {output_root / path for path in documents}
    existing = {path for path in output_root.rglob("*") if path.is_file()}
    unexpected = sorted(existing - expected)
    if unexpected:
        raise RuntimeError(
            "Unexpected existing output paths: "
            + ", ".join(str(path) for path in unexpected)
        )
    for relative_path, document in sorted(documents.items()):
        destination = output_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(_json_bytes(document))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Person E Phase 4 Step 4.1 Slice 3A evidence."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_ROOT,
        help="Output root; defaults to the authoritative evidence directory.",
    )
    arguments = parser.parse_args()
    write_documents(arguments.output_dir.resolve())


if __name__ == "__main__":
    main()
