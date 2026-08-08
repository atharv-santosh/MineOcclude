"""Build the non-scientific Person A production-handoff preflight package.

This builder is deliberately limited to deterministic planning evidence.  It
does not import model, preprocessing, extraction, activation, or rollout
runtime modules and it never creates a scientific artifact.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = (
    ROOT
    / "docs"
    / "status"
    / "person_a_phase4_step4_1_production_handoff_preflight_v0_1"
)
BUILDER_PATH = (
    "scripts/build_person_a_phase4_step4_1_production_handoff_preflight_v0_1.py"
)
TEST_PATH = (
    "tests/models/test_person_a_phase4_step4_1_production_handoff_preflight_v0_1.py"
)
STARTING_AUTHORITY = "06b87fe1f43d2133c25db498fcc1fd234f958aad"
SCHEMA_VERSION = "1.0"
PROPOSED = "PROPOSED_FROZEN_CONFIGURATION"
FROZEN_REGISTRY_V2_PATHS = {
    "completed_fixture": {
        "path": ("tests/fixtures/person_e/immutable_registry_v2_completed.json"),
        "sha256": ("a66c8408de1fb0a03c1d1ff9e65d15f2c9a7a35cd8094d25b2def59c0c9b5ec4"),
    },
    "contract_document": {
        "path": "docs/contracts/immutable_registry_v2.md",
        "sha256": ("02c2190575c9dec296bcb963495edb119695465477c43a19720679eb53b5dd88"),
    },
    "validator": {
        "path": "src/mineocclude/contracts/rollout_registry.py",
        "sha256": ("386a6bce4f5ba727aa51b40c69ef444c0d984984697da63f6ea4045a44c07356"),
    },
}
FROZEN_REGISTRY_V2_FIELD_ASSIGNMENTS = {
    "artifact_authorization": ("_IMMUTABLE_V2_ARTIFACT_AUTHORIZATION_FIELDS"),
    "authorization_record": "_IMMUTABLE_V2_AUTHORIZATION_RECORD_FIELDS",
    "authorization_record_verification": (
        "_IMMUTABLE_V2_AUTHORIZATION_VERIFICATION_FIELDS"
    ),
    "authorization_receipt": ("_IMMUTABLE_V2_AUTHORIZATION_RECEIPT_FIELDS"),
    "trusted_artifact_authorization": (
        "_IMMUTABLE_V2_TRUSTED_ARTIFACT_AUTHORIZATION_FIELDS"
    ),
}
REGISTRY_V2_TEMPLATE_TYPES = (
    "artifact_byte_or_receipt_verification",
    "direct_input_lineage",
    "exact_artifact_authorization",
    "owner_status_record",
    "trusted_manifest",
    "verified_authorization_record",
)
VERIFIED_AUTHORIZATION_TEMPLATE_FIELDS = frozenset(
    {
        "authorization_record",
        "authorization_record_bytes",
        "authorization_receipt",
        "trusted_artifact_authorization",
        "verification_context",
    }
)

AUTHORITIES = {
    "person_a": {
        "branch": "role/person-a-model",
        "remote_ref": "origin/role/person-a-model",
        "commit": STARTING_AUTHORITY,
    },
    "person_b": {
        "branch": "role/person-b-analysis",
        "remote_ref": "origin/role/person-b-analysis",
        "commit": "a189c7f0c6a822f3dd0d9869a572e1e2d390c5f1",
    },
    "person_c": {
        "branch": "role/person-c-data",
        "remote_ref": "origin/role/person-c-data",
        "commit": "bf09c23bb12f59acae724811eed6b82bab17c0ed",
    },
    "person_d": {
        "branch": "role/person-d-baselines",
        "remote_ref": "origin/role/person-d-baselines",
        "commit": "853e0acadf050a0b1f318b399b524e57379d03bf",
    },
    "person_e": {
        "branch": "role/person-e-operations",
        "remote_ref": "origin/role/person-e-operations",
        "commit": "b27d404c6aa913bac559754fa8b7accdff46e886",
    },
}

SELECTED_TRAJECTORY_IDS = (
    "layout_00_ep9403",
    "layout_00_ep9410",
    "layout_00_ep9441",
    "layout_01_ep9405",
    "layout_01_ep9412",
    "layout_01_ep9442",
    "layout_02_ep9407",
    "layout_02_ep9432",
    "layout_03_ep9404",
    "layout_03_ep9409",
    "layout_03_ep9443",
    "layout_04_ep9406",
    "layout_04_ep9411",
    "layout_04_ep9444",
    "layout_05_ep9408",
)
EXCLUDED_TRAJECTORY_ID = "layout_05_ep9422"

B_PACKAGE_ROOT = "docs/status/person_b_phase4_step4_1_registry_v2_handoff_v0_1"
E_PACKAGE_ROOT = "docs/status/person_e_phase4_step4_1_slice3a_v0_1"

PROHIBITED_PROMOTIONS = {
    "smoke_model_input": {
        "path": (
            "docs/status/person_a_phase2_registry_handoff_v1/sessions/"
            "person-a-registry-smoke-20260728T000019Z/step2_6/scene.jsonl"
        ),
        "sha256": ("53fb9436345dc87febf955a2a0928c3d7caaa558f0886a57612ea5b2bfedac57"),
        "reason": "bounded_smoke_not_production_science",
    },
    "extraction_pilot": {
        "path": (
            "docs/status/phase4_runtime/"
            "person-a-phase4-wave3-v11-aws-20260727-045300/"
            "extraction_probe_report.json"
        ),
        "sha256": ("73f6ef771c06b6b06d82e3eb7d06b4adb840a0557c31e8bd0b6e5deacd3d32c5"),
        "reason": "bounded_non_scientific_extraction_probe",
    },
    "limited_activation_pilot": {
        "path": (
            "docs/status/phase4_runtime/"
            "person-a-phase4-wave3-v11-aws-20260727-045300/"
            "limited_unpooled_pilot.npz"
        ),
        "sha256": ("3032f93b2e47235363af1287dbeddbdbb85853d2e610d4658531d2fa39ae896e"),
        "reason": "limited_one_frame_unpooled_pilot",
    },
    "synthetic_activation_fixture": {
        "path": (
            "docs/status/fixtures/phase5_activation_store_handoff_v1_2/"
            "handoff_manifest.json"
        ),
        "sha256": ("3fa99342284b540ade254792c2cf125117ac1b925632f3444ccd767c49cb7df5"),
        "reason": "synthetic_non_scientific",
    },
    "certification_rollout": {
        "path": (
            "docs/status/phase3_runtime/"
            "person-a-phase3-aws-20260726-034000/rollout/"
            "person-a-phase3-aws-20260726-034000-rollout.rollout.json"
        ),
        "sha256": ("a2fa59e143b8904b43199335f182b4f9e3274c791ddb0fe33b6da63e7c9cc20a"),
        "reason": "runtime_certification_not_production_rollout",
    },
}

ALL_OUTPUT_PATHS = (
    "activation_contract.json",
    "authority_binding.json",
    "blocker_receipt.json",
    "extraction_contract.json",
    "handoff_plan.json",
    "immutable_runtime_configuration.json",
    "model_input_contract.json",
    "registry_v2_trust_templates.json",
    "rollout_contract.json",
    "selected_c_inputs.json",
    "sha256_inventory.json",
    "validation_receipt.json",
)

PROTECTED_FALSE_FIELDS = frozenset(
    {
        "accepted",
        "automatic_phase6_transition_allowed",
        "person_a_phase6_authorized",
        "promotion_allowed",
        "production_execution_performed",
        "project_integration_claimed",
        "registry_v2_acceptance_authorized",
        "scientific_execution_performed",
        "scientific_execution_authorized",
        "step4_1_complete",
        "u4_output_inspected",
        "verification_result",
        "verified",
    }
)


def _completed(command: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
    )


def _git_text(*arguments: str) -> str:
    completed = _completed(["git", *arguments])
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.decode("utf-8", errors="replace").strip())
    return completed.stdout.decode("utf-8").strip()


def _git_bytes(commit: str, path: str) -> bytes:
    completed = _completed(["git", "show", f"{commit}:{path}"])
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Unable to read {commit}:{path}: {detail}")
    return completed.stdout


def _git_json(commit: str, path: str) -> dict[str, Any]:
    value = json.loads(_git_bytes(commit, path))
    if not isinstance(value, dict):
        raise TypeError(f"{commit}:{path} is not a JSON object")
    return value


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _frozen_frozenset(source: bytes, assignment_name: str) -> tuple[str, ...]:
    tree = ast.parse(source.decode("utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == assignment_name
            for target in node.targets
        ):
            continue
        call = node.value
        if (
            not isinstance(call, ast.Call)
            or not isinstance(call.func, ast.Name)
            or call.func.id != "frozenset"
            or len(call.args) != 1
        ):
            break
        fields = ast.literal_eval(call.args[0])
        if not isinstance(fields, set) or not all(
            isinstance(field, str) for field in fields
        ):
            break
        return tuple(sorted(fields))
    raise RuntimeError(
        f"Frozen Registry v2 field assignment changed: {assignment_name}"
    )


def _frozen_registry_v2_binding() -> dict[str, Any]:
    commit = AUTHORITIES["person_e"]["commit"]
    records: dict[str, dict[str, Any]] = {}
    source_by_name: dict[str, bytes] = {}
    for name, expected in sorted(FROZEN_REGISTRY_V2_PATHS.items()):
        raw = _git_bytes(commit, expected["path"])
        if _sha256(raw) != expected["sha256"]:
            raise RuntimeError(f"Frozen Registry v2 {name} source bytes changed")
        source_by_name[name] = raw
        records[name] = {
            "byte_size": len(raw),
            "path": expected["path"],
            "sha256": expected["sha256"],
            "source_commit": commit,
        }
    validator_source = source_by_name["validator"]
    field_sets = {
        name: list(_frozen_frozenset(validator_source, assignment))
        for name, assignment in sorted(FROZEN_REGISTRY_V2_FIELD_ASSIGNMENTS.items())
    }
    return {
        "field_sets": field_sets,
        "records": records,
        "source_commit": commit,
        "source_read_policy": "exact_git_commit_object",
    }


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _source_path(trajectory_id: str) -> str:
    return f"data/autonomous/{trajectory_id}/capture_package_v0_1.json"


def verify_authority(owner: str) -> dict[str, str]:
    if owner not in AUTHORITIES:
        raise RuntimeError(f"Unknown authority owner: {owner}")
    authority = AUTHORITIES[owner]
    commit = authority["commit"]
    remote_ref = authority["remote_ref"]
    commit_check = _completed(["git", "cat-file", "-e", f"{commit}^{{commit}}"])
    if commit_check.returncode != 0:
        raise RuntimeError(f"Authority commit does not exist: {owner}:{commit}")
    ref_check = _completed(
        ["git", "show-ref", "--verify", "--quiet", f"refs/remotes/{remote_ref}"]
    )
    if ref_check.returncode != 0:
        raise RuntimeError(f"Authority remote ref does not exist: {remote_ref}")
    ancestor_check = _completed(
        ["git", "merge-base", "--is-ancestor", commit, remote_ref]
    )
    if ancestor_check.returncode != 0:
        raise RuntimeError(
            f"Authority commit is not an ancestor of {remote_ref}: {commit}"
        )
    return {
        "branch": authority["branch"],
        "remote_ref": remote_ref,
        "source_authority_commit": commit,
        "source_read_policy": "exact_git_commit_object",
    }


def verify_repository_authority() -> None:
    # The starting authority must remain in this branch's history. Pinning HEAD
    # to it instead would expire this guard the moment Person A commits again.
    # The package is sourced from immutable commit objects, so the verifier also
    # stays usable after promotion, when the checked-out branch has legitimately
    # advanced beyond the historical Person A preparation tip onto an
    # integration branch; the per-owner authority commits below are unchanged.
    if (
        _completed(
            ["git", "merge-base", "--is-ancestor", STARTING_AUTHORITY, "HEAD"]
        ).returncode
        != 0
    ):
        raise RuntimeError(
            f"Person A starting authority is not an ancestor of HEAD: "
            f"{STARTING_AUTHORITY}"
        )
    for owner in AUTHORITIES:
        verify_authority(owner)


def _verify_local_prohibited_bytes() -> None:
    for name, record in PROHIBITED_PROMOTIONS.items():
        path = ROOT / record["path"]
        if not path.is_file():
            raise RuntimeError(f"Missing prohibited-promotion evidence: {name}")
        if _sha256(path.read_bytes()) != record["sha256"]:
            raise RuntimeError(f"Changed prohibited-promotion evidence bytes: {name}")


def _selected_c_inputs() -> dict[str, Any]:
    b_commit = AUTHORITIES["person_b"]["commit"]
    c_commit = AUTHORITIES["person_c"]["commit"]
    b_inputs = _git_json(
        b_commit,
        f"{B_PACKAGE_ROOT}/accepted_c_oracle_inputs.json",
    )
    b_rows = b_inputs.get("accepted_inputs")
    if not isinstance(b_rows, list):
        raise TypeError("Person B accepted input list is missing")
    b_by_id = {row.get("trajectory_id"): row for row in b_rows if isinstance(row, dict)}
    if set(b_by_id) != set(SELECTED_TRAJECTORY_IDS):
        raise RuntimeError("Person B selected input identity set changed")
    if len(b_rows) != len(b_by_id):
        raise RuntimeError("Person B selected input list contains duplicates")

    rows: list[dict[str, Any]] = []
    source_frame_count = 0
    for trajectory_id in SELECTED_TRAJECTORY_IDS:
        source_path = _source_path(trajectory_id)
        raw = _git_bytes(c_commit, source_path)
        document = json.loads(raw)
        if not isinstance(document, dict):
            raise TypeError(f"Person C input is not an object: {source_path}")
        b_row = b_by_id[trajectory_id]
        if b_row.get("path") != source_path:
            raise RuntimeError(f"Person B path changed for {trajectory_id}")
        if document.get("trajectory_id") != trajectory_id:
            raise RuntimeError(f"Person C trajectory identity mismatch: {source_path}")
        if document.get("scientific_use") != "pending_cross_role_signoff":
            raise RuntimeError(
                f"Person C scientific-use state changed: {trajectory_id}"
            )
        if document.get("synthetic") is not False:
            raise RuntimeError(f"Person C selected input is synthetic: {trajectory_id}")
        package_local_status = (
            document.get("episode_manifest", {}).get("status")
            if isinstance(document.get("episode_manifest"), dict)
            else None
        )
        if package_local_status != "accepted":
            raise RuntimeError(
                f"Person C package-local status changed: {trajectory_id}"
            )
        frame_count = document.get("media", {}).get("frame_count")
        if not isinstance(frame_count, int) or isinstance(frame_count, bool):
            raise TypeError(f"Invalid frame count: {trajectory_id}")
        source_frame_count += frame_count
        rows.append(
            {
                "byte_size": len(raw),
                "frame_count": frame_count,
                "layout_id": document.get("layout_id"),
                "package_local_status": package_local_status,
                "person_b_local_classification": b_row.get("classification"),
                "person_b_recorded_literal_sha256": b_row.get("literal_sha256"),
                "registry_v2_accepted": False,
                "scientific_use": "pending_cross_role_signoff",
                "sha256": _sha256(raw),
                "source_commit": c_commit,
                "source_path": source_path,
                "synthetic": False,
                "trajectory_id": trajectory_id,
            }
        )

    excluded = b_inputs.get("excluded_input")
    if not isinstance(excluded, dict):
        raise TypeError("Person B excluded control is missing")
    if excluded.get("trajectory_id") != EXCLUDED_TRAJECTORY_ID:
        raise RuntimeError("Person B excluded control identity changed")
    excluded_path = _source_path(EXCLUDED_TRAJECTORY_ID)
    excluded_raw = _git_bytes(c_commit, excluded_path)
    excluded_document = json.loads(excluded_raw)
    if not isinstance(excluded_document, dict):
        raise TypeError("Excluded Person C control is not an object")
    source_set_digest = _sha256(
        "\n".join(f"{row['trajectory_id']}:{row['sha256']}" for row in rows).encode(
            "utf-8"
        )
    )
    return {
        "accepted_scientific_input_count": 0,
        "excluded_input": {
            "byte_size": len(excluded_raw),
            "classification": "excluded_no_object_control",
            "person_b_recorded_literal_sha256": excluded.get("literal_sha256"),
            "registry_v2_accepted": False,
            "scientific_use": excluded_document.get("scientific_use"),
            "sha256": _sha256(excluded_raw),
            "source_commit": c_commit,
            "source_path": excluded_path,
            "trajectory_id": EXCLUDED_TRAJECTORY_ID,
        },
        "input_count": len(rows),
        "inputs": rows,
        "package_local_acceptance_is_project_acceptance": False,
        "registry_v2_accepted_input_count": 0,
        "schema_id": (
            "person-a-phase4-step4-1-production-handoff-preflight-"
            "selected-c-inputs-v0.1"
        ),
        "schema_version": SCHEMA_VERSION,
        "scientific_use": "pending_cross_role_signoff",
        "sha256_basis": "exact_git_object_bytes_at_person_c_source_commit",
        "source_frame_count": source_frame_count,
        "source_set_digest": source_set_digest,
    }


def _proposed(name: str, value: Any, evidence: str) -> dict[str, Any]:
    return {
        "classification": PROPOSED,
        "evidence": evidence,
        "name": name,
        "value": value,
    }


def _runtime_configuration() -> dict[str, Any]:
    return {
        "acceptance_state": "not_accepted",
        "configuration": [
            _proposed(
                "main_checkpoint_sha256",
                "a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5",
                "verified Person A runtime engineering identity",
            ),
            _proposed(
                "vae_checkpoint_sha256",
                "370d06be427e034476b6b95ba0080a4b48266e876c4776a757b944b87b87d9ab",
                "verified Person A runtime engineering identity",
            ),
            _proposed(
                "model_config_sha256",
                "e13b3a80fb370547a05852809c2c8f02d05ebe2fce3b3bb2fd1ee54eee78c018",
                "verified Person A runtime engineering identity",
            ),
            _proposed(
                "preprocessing_identity",
                (
                    "mineworld_gradio_step_video_preprocessing@1.0:"
                    "036fa0b4899285e5499f88581f6e02426a25f732fcc26bd63c0f5b3863a9d9ab"
                ),
                "phase3 preprocessing golden and runtime certification",
            ),
            _proposed(
                "input_dimensions_hwc",
                [360, 640, 3],
                "selected Person C capture packages",
            ),
            _proposed(
                "preprocessed_dimensions_chw",
                [3, 224, 384],
                "phase3 preprocessing golden",
            ),
            _proposed(
                "extraction_hook",
                "decoder_layer_output_residual_stream",
                "phase4 extraction pilot",
            ),
            _proposed(
                "source_tensor_shape",
                [1, 2776, 2048],
                "phase4 extraction pilot",
            ),
            _proposed(
                "source_tensor_dtype",
                "float16",
                "phase4 extraction pilot",
            ),
            _proposed(
                "visual_tokens_per_frame",
                336,
                "frozen activation contract",
            ),
            _proposed(
                "pooling",
                {
                    "analysis_dtype": "float64",
                    "method": "mean",
                    "production_representation": "pooled_only",
                    "region": "visual",
                    "stored_dtype": "float32",
                    "vector_shape": [2048],
                },
                "frozen activation contract and Phase 5 storage decision",
            ),
            _proposed(
                "activation_layers",
                list(range(20)),
                "verified 20-layer adapter identity",
            ),
            _proposed(
                "activation_index_key",
                [
                    "trajectory_id",
                    "model_frame_idx",
                    "layer_idx",
                    "hook_site",
                ],
                "frozen activation contract",
            ),
            _proposed(
                "chunk_and_index_rules",
                {
                    "chunk_format": "npy",
                    "index_format": "canonical_json",
                    "no_overwrite": True,
                    "row_order": ("trajectory_id,model_frame_idx,layer_idx,hook_site"),
                    "run_binding_required": True,
                },
                "Phase 5 pooled activation storage decision",
            ),
            _proposed(
                "rollout_configuration",
                {
                    "action_tokens_per_frame": 11,
                    "context_pair_limit": 16,
                    "output_dimensions_hw": [224, 384],
                    "precision": "float16",
                    "temperature": 1.0,
                    "top_k": 1,
                    "visual_tokens_per_frame": 336,
                },
                "Phase 3 runtime certification engineering identity",
            ),
        ],
        "configuration_identity_is_artifact_acceptance": False,
        "configuration_identity_is_execution_authorization": False,
        "schema_id": (
            "person-a-phase4-step4-1-production-handoff-preflight-"
            "runtime-configuration-v0.1"
        ),
        "schema_version": SCHEMA_VERSION,
        "status": PROPOSED,
    }


def _trust_requirements() -> list[str]:
    return [
        "trusted_owner_authority",
        "verified_owner_status_record_bytes",
        "trusted_exact_artifact_authorization",
        "verified_authorization_record_bytes",
        "trusted_manifest_exact_artifact_entry",
        "verified_artifact_bytes_or_trusted_receipt",
        "exact_direct_input_artifact_identities",
    ]


def _prohibited_promotion_record(name: str) -> dict[str, Any]:
    record = PROHIBITED_PROMOTIONS[name]
    return {
        "path": record["path"],
        "promotion_allowed": False,
        "promotion_id": name,
        "reason": record["reason"],
        "registry_v2_accepted": False,
        "scientific_artifact": False,
        "sha256": record["sha256"],
    }


def _common_contract(artifact_type: str) -> dict[str, Any]:
    return {
        "artifact_type": artifact_type,
        "future_artifact_id": None,
        "future_byte_size": None,
        "future_sha256": None,
        "instantiated_output_artifact": False,
        "no_overwrite": True,
        "owner": "person_a",
        "registry_v2_accepted": False,
        "registry_v2_requirements": _trust_requirements(),
        "status": "contract_only_not_executed",
    }


def _model_input_contract(selected: dict[str, Any]) -> dict[str, Any]:
    contract = _common_contract("model_input")
    contract.update(
        {
            "artifact_id_rule": (
                "person_a_model_input__<source_set_digest>__"
                "<preprocessing_identity_digest>"
            ),
            "checkpoint_identity_required": True,
            "direct_input_artifact_ids": [
                row["trajectory_id"] for row in selected["inputs"]
            ],
            "direct_input_source_set_digest": selected["source_set_digest"],
            "expected_key": ["trajectory_id", "model_frame_idx"],
            "expected_row_count": selected["source_frame_count"],
            "expected_source_frame_count": selected["source_frame_count"],
            "package_schema_version": SCHEMA_VERSION,
            "preprocessing_identity_required": True,
            "prohibited_promotions": ["smoke_model_input"],
            "prohibited_promotion_records": [
                _prohibited_promotion_record("smoke_model_input")
            ],
            "schema_id": (
                "person-a-phase4-step4-1-production-handoff-preflight-"
                "model-input-contract-v0.1"
            ),
            "schema_version": SCHEMA_VERSION,
        }
    )
    return contract


def _extraction_contract(selected: dict[str, Any]) -> dict[str, Any]:
    contract = _common_contract("extraction")
    contract.update(
        {
            "artifact_id_rule": (
                "person_a_extraction__<model_input_artifact_id>__"
                "<runtime_configuration_digest>"
            ),
            "byte_verification_required": True,
            "dependency": {
                "accepted_required": True,
                "artifact_id": None,
                "artifact_type": "model_input",
            },
            "expected_frame_key": ["trajectory_id", "model_frame_idx"],
            "expected_layer_count": 20,
            "expected_layer_indices": list(range(20)),
            "expected_pooled_row_count": (selected["source_frame_count"] * 20),
            "hook_site": "decoder_layer_output_residual_stream",
            "output_dtype": "float32",
            "output_vector_shape": [2048],
            "prohibited_promotions": ["extraction_pilot"],
            "prohibited_promotion_records": [
                _prohibited_promotion_record("extraction_pilot")
            ],
            "schema_id": (
                "person-a-phase4-step4-1-production-handoff-preflight-"
                "extraction-contract-v0.1"
            ),
            "schema_version": SCHEMA_VERSION,
            "source_tensor_dtype": "float16",
            "source_tensor_shape": [1, 2776, 2048],
        }
    )
    return contract


def _activation_contract(selected: dict[str, Any]) -> dict[str, Any]:
    contract = _common_contract("activation")
    contract.update(
        {
            "artifact_id_rule": (
                "person_a_activation__<extraction_artifact_id>__"
                "<activation_store_identity_digest>"
            ),
            "byte_verification_required": True,
            "chunk_and_index_manifest": {
                "activation_key": [
                    "trajectory_id",
                    "model_frame_idx",
                    "layer_idx",
                    "hook_site",
                ],
                "chunk_format": "npy",
                "index_format": "canonical_json",
                "run_binding_required": True,
                "stable_row_order_required": True,
            },
            "dependency": {
                "accepted_required": True,
                "artifact_id": None,
                "artifact_type": "extraction",
            },
            "expected_row_count": selected["source_frame_count"] * 20,
            "hook_site": "decoder_layer_output_residual_stream",
            "layers": list(range(20)),
            "pooled_representation": {
                "analysis_dtype": "float64",
                "pooling_method": "mean",
                "stored_dtype": "float32",
                "vector_shape": [2048],
            },
            "prohibited_promotions": [
                "limited_activation_pilot",
                "synthetic_activation_fixture",
            ],
            "prohibited_promotion_records": [
                _prohibited_promotion_record("limited_activation_pilot"),
                _prohibited_promotion_record("synthetic_activation_fixture"),
            ],
            "production_unpooled_representation_allowed": False,
            "schema_id": (
                "person-a-phase4-step4-1-production-handoff-preflight-"
                "activation-contract-v0.1"
            ),
            "schema_version": SCHEMA_VERSION,
        }
    )
    return contract


def _rollout_contract() -> dict[str, Any]:
    contract = _common_contract("rollout")
    contract.update(
        {
            "artifact_id_rule": (
                "person_a_rollout__<accepted_model_input_artifact_id>__"
                "<runtime_configuration_digest>__<run_id>"
            ),
            "dependencies": [
                {
                    "accepted_required": True,
                    "artifact_id": None,
                    "artifact_type": "model_input",
                },
                {
                    "accepted_required": True,
                    "artifact_id": None,
                    "artifact_type": "runtime_configuration",
                },
            ],
            "direct_input_lineage_required": True,
            "manifest_requirements": [
                "canonical rollout manifest bytes",
                "rendered media SHA-256 and byte size",
                "checkpoint and preprocessing identities",
                "input artifact identities",
                "run identity and completed lifecycle",
            ],
            "package_schema_version": SCHEMA_VERSION,
            "prohibited_promotions": ["certification_rollout"],
            "prohibited_promotion_records": [
                _prohibited_promotion_record("certification_rollout")
            ],
            "rendered_byte_verification_required": True,
            "schema_id": (
                "person-a-phase4-step4-1-production-handoff-preflight-"
                "rollout-contract-v0.1"
            ),
            "schema_version": SCHEMA_VERSION,
        }
    )
    return contract


def _pending_frozen_record(
    fields: list[str],
    artifact_type: str,
) -> dict[str, Any]:
    record = dict.fromkeys(fields)
    if "artifact_type" in record:
        record["artifact_type"] = artifact_type
    if "decision" in record:
        record["decision"] = "pending"
    if "owner_id" in record:
        record["owner_id"] = "person_a"
    if "owner_status" in record:
        record["owner_status"] = "pending"
    return record


def _verified_authorization_template(
    artifact_type: str,
    field_sets: dict[str, list[str]],
) -> dict[str, Any]:
    authorization = _pending_frozen_record(
        field_sets["artifact_authorization"],
        artifact_type,
    )
    authorization_record = _pending_frozen_record(
        field_sets["authorization_record"],
        artifact_type,
    )
    authorization_receipt = dict.fromkeys(field_sets["authorization_receipt"])
    trusted_entry = {
        "authorization": authorization,
        "authorization_record_verification": {
            field: None for field in field_sets["authorization_record_verification"]
        },
    }
    return {
        "authorization_record": authorization_record,
        "authorization_record_bytes": {
            "authorization_record_id": None,
            "byte_size": None,
            "canonical_utf8_json_bytes": None,
            "sha256": None,
        },
        "authorization_receipt": authorization_receipt,
        "trusted_artifact_authorization": trusted_entry,
        "verification_context": {
            "accepted": False,
            "artifact_id": None,
            "owner_id": "person_a",
            "source_authority_revision": None,
            "status": "pending_future_authorization_verification",
            "verification_receipt_id": None,
            "verification_result": False,
            "verifier_authority_id": None,
            "verified": False,
        },
    }


def _trust_templates() -> dict[str, Any]:
    frozen_binding = _frozen_registry_v2_binding()
    field_sets = frozen_binding["field_sets"]
    templates: dict[str, Any] = {}
    for artifact_type in ("model_input", "extraction", "activation", "rollout"):
        templates[artifact_type] = {
            "artifact_byte_or_receipt_verification": {
                "artifact_byte_size": None,
                "artifact_sha256": None,
                "receipt_id": None,
                "state": "pending_future_execution",
            },
            "direct_input_lineage": {
                "direct_input_artifact_ids": None,
                "state": "pending_future_execution",
            },
            "exact_artifact_authorization": {
                "accepted": False,
                "artifact_id": None,
                "authorization_decision": None,
                "authorization_record_sha256": None,
                "state": "template_only",
            },
            "owner_status_record": {
                "artifact_id": None,
                "owner": "person_a",
                "record_sha256": None,
                "state": "pending_future_execution",
                "status": None,
            },
            "trusted_manifest": {
                "artifact_entry": None,
                "manifest_id": None,
                "manifest_sha256": None,
                "state": "template_only",
            },
            "verified_authorization_record": (
                _verified_authorization_template(
                    artifact_type,
                    field_sets,
                )
            ),
        }
    return {
        "accepted_record_count": 0,
        "all_future_output_values_null_or_pending": True,
        "artifact_type_template_count": len(templates),
        "frozen_registry_v2_binding": frozen_binding,
        "registry_v2_acceptance_authorized": False,
        "schema_id": (
            "person-a-phase4-step4-1-production-handoff-preflight-"
            "registry-v2-trust-templates-v0.1"
        ),
        "schema_version": SCHEMA_VERSION,
        "template_count": len(REGISTRY_V2_TEMPLATE_TYPES),
        "template_types": list(REGISTRY_V2_TEMPLATE_TYPES),
        "templates": templates,
    }


def _blocker_receipt() -> dict[str, Any]:
    blockers = [
        (
            "person_a_phase6_authorization",
            "required_signing_owners_under_person_b_contract",
            True,
            True,
            True,
        ),
        (
            "person_c_scientific_use_signoff",
            "person_c",
            True,
            True,
            True,
        ),
        (
            "person_c_registry_v2_input_trust_package",
            "person_c",
            True,
            True,
            True,
        ),
        (
            "production_model_input",
            "person_a_after_authorization",
            True,
            True,
            True,
        ),
        (
            "production_extraction",
            "person_a_after_authorization",
            True,
            True,
            True,
        ),
        (
            "production_activation",
            "person_a_after_authorization",
            True,
            True,
            True,
        ),
        (
            "production_rollout",
            "person_a_after_authorization",
            True,
            True,
            True,
        ),
    ]
    return {
        "blocker_count": len(blockers),
        "blockers": [
            {
                "blocker_id": blocker_id,
                "blocks_registry_v2_acceptance": registry,
                "blocks_runtime_execution": runtime,
                "blocks_scientific_use": science,
                "owner": (
                    "person_a"
                    if blocker_id.startswith(("production_", "person_a_"))
                    else "person_c"
                ),
                "resolver": resolver,
                "state": "blocked",
            }
            for blocker_id, resolver, runtime, science, registry in blockers
        ],
        "schema_id": (
            "person-a-phase4-step4-1-production-handoff-preflight-blocker-receipt-v0.1"
        ),
        "schema_version": SCHEMA_VERSION,
    }


def _handoff_plan() -> dict[str, Any]:
    steps = [
        ("explicit_phase6_authorization", "required_signing_owners"),
        ("accepted_c_input_freeze", "person_c"),
        ("production_model_input", "person_a"),
        ("production_extraction", "person_a"),
        ("production_activation", "person_a"),
        ("activation_key_set_handoff_to_b", "person_a"),
        ("final_b_frame_membership", "person_b"),
        ("production_rollout", "person_a"),
        ("person_a_registry_v2_trust_package", "person_a"),
        ("person_b_and_person_e_import", "person_b_and_person_e"),
    ]
    return {
        "execution_started": False,
        "plan_only": True,
        "schema_id": (
            "person-a-phase4-step4-1-production-handoff-preflight-handoff-plan-v0.1"
        ),
        "schema_version": SCHEMA_VERSION,
        "steps": [
            {
                "owner": owner,
                "sequence": index,
                "state": "future_blocked",
                "step_id": step_id,
            }
            for index, (step_id, owner) in enumerate(steps, start=1)
        ],
    }


def _authority_binding() -> dict[str, Any]:
    b_commit = AUTHORITIES["person_b"]["commit"]
    e_commit = AUTHORITIES["person_e"]["commit"]
    b_phase6 = _git_bytes(
        b_commit,
        f"{B_PACKAGE_ROOT}/phase6_authorization_conditions.json",
    )
    b_handoff = _git_bytes(
        b_commit,
        f"{B_PACKAGE_ROOT}/person_a_required_handoff.json",
    )
    e_handoff = _git_bytes(
        e_commit,
        f"{E_PACKAGE_ROOT}/owner_handoffs/person_a_requirements.json",
    )
    e_authority = _git_bytes(
        e_commit,
        f"{E_PACKAGE_ROOT}/authority_binding.json",
    )
    b_phase6_document = json.loads(b_phase6)
    e_handoff_document = json.loads(e_handoff)
    if b_phase6_document.get("person_a_phase6_authorized") is not False:
        raise RuntimeError("Person B Phase 6 authorization state changed")
    if (
        b_phase6_document.get("automatic_transition_defined_by_existing_documents")
        is not False
    ):
        raise RuntimeError("Person B automatic transition state changed")
    if e_handoff_document.get("phase6_authorized") is not False:
        raise RuntimeError("Person E Person A authorization state changed")
    return {
        "authorities": {
            owner: verify_authority(owner) for owner in sorted(AUTHORITIES)
        },
        "authorization": {
            "automatic_phase6_transition_allowed": False,
            "later_explicit_versioned_authorization_required": True,
            "person_a_phase6_authorized": False,
            "production_execution_performed": False,
            "registry_v2_acceptance_authorized": False,
            "scientific_execution_authorized": False,
        },
        "builder_path": BUILDER_PATH,
        "external_evidence": [
            {
                "byte_size": len(raw),
                "path": path,
                "sha256": _sha256(raw),
                "source_commit": commit,
            }
            for commit, path, raw in (
                (
                    b_commit,
                    f"{B_PACKAGE_ROOT}/phase6_authorization_conditions.json",
                    b_phase6,
                ),
                (
                    b_commit,
                    f"{B_PACKAGE_ROOT}/person_a_required_handoff.json",
                    b_handoff,
                ),
                (
                    e_commit,
                    f"{E_PACKAGE_ROOT}/owner_handoffs/person_a_requirements.json",
                    e_handoff,
                ),
                (
                    e_commit,
                    f"{E_PACKAGE_ROOT}/authority_binding.json",
                    e_authority,
                ),
            )
        ],
        "person_a_branch": AUTHORITIES["person_a"]["branch"],
        "project_integration_claimed": False,
        "schema_id": (
            "person-a-phase4-step4-1-production-handoff-preflight-"
            "authority-binding-v0.1"
        ),
        "schema_version": SCHEMA_VERSION,
        "starting_authority": STARTING_AUTHORITY,
        "step4_1_complete": False,
        "test_path": TEST_PATH,
        "u4_output_inspected": False,
    }


def _validation_receipt() -> dict[str, Any]:
    return {
        "accepted_artifact_count": 0,
        "accepted_placeholder_count": 0,
        "activation_run_count": 0,
        "ast_result": {
            "files": [BUILDER_PATH, TEST_PATH],
            "passed": True,
        },
        "combined_explicit_test_result": {
            "expected_passed": 82,
            "expected_subtests_passed": 76,
            "passed": True,
        },
        "deterministic_rebuild_result": {
            "byte_identical": True,
            "isolated_build_count": 2,
        },
        "existing_safe_contract_test_result": {
            "expected_passed": 44,
            "expected_subtests_passed": 3,
            "passed": True,
            "paths": [
                "tests/contracts/test_activation_contract.py",
                "tests/contracts/test_rollout_registry_contract.py",
            ],
        },
        "extraction_run_count": 0,
        "focused_test_result": {
            "expected_passed": 38,
            "expected_subtests_passed": 73,
            "passed": True,
            "path": TEST_PATH,
        },
        "git_diff_check_passed": True,
        "model_load_count": 0,
        "package_file_count": len(ALL_OUTPUT_PATHS),
        "package_inventory": list(ALL_OUTPUT_PATHS),
        "person_a_phase6_authorized": False,
        "production_execution_count": 0,
        "registry_v2_accepted_record_count": 0,
        "registry_v2_template_count": len(REGISTRY_V2_TEMPLATE_TYPES),
        "rollout_run_count": 0,
        "ruff_result": {
            "files": [BUILDER_PATH, TEST_PATH],
            "passed": True,
        },
        "schema_id": (
            "person-a-phase4-step4-1-production-handoff-preflight-"
            "validation-receipt-v0.1"
        ),
        "schema_version": SCHEMA_VERSION,
        "scientific_execution_performed": False,
        "u4_output_inspected": False,
        "verified_authorization_record_template_defined": True,
    }


def _claim_path(parent: str, key: str) -> str:
    if key.isidentifier():
        return f"{parent}.{key}"
    return f"{parent}[{json.dumps(key, ensure_ascii=True)}]"


def _protected_false_violations(value: Any, path: str) -> list[str]:
    violations: list[str] = []
    if isinstance(value, dict):
        for key in sorted(value):
            child = value[key]
            child_path = _claim_path(path, key)
            if key in PROTECTED_FALSE_FIELDS and child is not False:
                violations.append(
                    f"{child_path}: protected value must be boolean false; "
                    f"got {child!r}"
                )
            violations.extend(_protected_false_violations(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(_protected_false_violations(child, f"{path}[{index}]"))
    return violations


def validate_selected_c_inputs(document: dict[str, Any]) -> tuple[str, ...]:
    violations: list[str] = []
    rows = document.get("inputs")
    if not isinstance(rows, list):
        return ("selected_c_inputs.json.inputs must be a list",)
    identities = [row.get("trajectory_id") for row in rows if isinstance(row, dict)]
    if len(rows) != len(SELECTED_TRAJECTORY_IDS):
        violations.append("selected C input count must equal 15")
    duplicates = sorted(
        identity for identity, count in Counter(identities).items() if count > 1
    )
    if duplicates:
        violations.append(f"duplicate selected C inputs: {duplicates}")
    missing = sorted(set(SELECTED_TRAJECTORY_IDS) - set(identities))
    extra = sorted(set(identities) - set(SELECTED_TRAJECTORY_IDS))
    if missing:
        violations.append(f"missing selected C inputs: {missing}")
    if extra:
        violations.append(f"extra selected C inputs: {extra}")
    if EXCLUDED_TRAJECTORY_ID in identities:
        violations.append("excluded no-object control may not be selected")
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            violations.append(f"inputs[{index}] must be an object")
            continue
        if row.get("scientific_use") != "pending_cross_role_signoff":
            violations.append(
                f"inputs[{index}].scientific_use must remain pending_cross_role_signoff"
            )
        if row.get("registry_v2_accepted") is not False:
            violations.append(f"inputs[{index}].registry_v2_accepted must be false")
        trajectory_id = row.get("trajectory_id")
        if trajectory_id in SELECTED_TRAJECTORY_IDS:
            expected_path = _source_path(trajectory_id)
            if row.get("source_path") != expected_path:
                violations.append(
                    f"inputs[{index}].source_path changed for {trajectory_id}"
                )
            if row.get("source_commit") != AUTHORITIES["person_c"]["commit"]:
                violations.append(
                    f"inputs[{index}].source_commit changed for {trajectory_id}"
                )
            authoritative_bytes = _git_bytes(
                AUTHORITIES["person_c"]["commit"],
                expected_path,
            )
            if row.get("sha256") != _sha256(authoritative_bytes):
                violations.append(f"inputs[{index}].sha256 changed for {trajectory_id}")
            if row.get("byte_size") != len(authoritative_bytes):
                violations.append(
                    f"inputs[{index}].byte_size changed for {trajectory_id}"
                )
    excluded = document.get("excluded_input")
    if not isinstance(excluded, dict):
        violations.append("excluded_input must be an object")
    elif (
        excluded.get("trajectory_id") != EXCLUDED_TRAJECTORY_ID
        or excluded.get("classification") != "excluded_no_object_control"
    ):
        violations.append("excluded no-object control binding changed")
    else:
        excluded_bytes = _git_bytes(
            AUTHORITIES["person_c"]["commit"],
            _source_path(EXCLUDED_TRAJECTORY_ID),
        )
        if excluded.get("sha256") != _sha256(excluded_bytes):
            violations.append("excluded no-object control hash changed")
        if excluded.get("byte_size") != len(excluded_bytes):
            violations.append("excluded no-object control byte size changed")
    return tuple(violations)


def validate_registry_v2_trust_templates(
    document: dict[str, Any],
) -> tuple[str, ...]:
    violations: list[str] = []
    expected_binding = _frozen_registry_v2_binding()
    if document.get("accepted_record_count") != 0:
        violations.append("Registry v2 accepted record count must equal zero")
    if document.get("artifact_type_template_count") != 4:
        violations.append("Registry v2 artifact-type template count must equal four")
    if document.get("template_count") != 6:
        violations.append("Registry v2 template count must equal six")
    if document.get("template_types") != list(REGISTRY_V2_TEMPLATE_TYPES):
        violations.append("Registry v2 template-type inventory changed")
    if document.get("frozen_registry_v2_binding") != expected_binding:
        violations.append("Frozen Registry v2 contract binding changed")
    if document.get("registry_v2_acceptance_authorized") is not False:
        violations.append("Registry v2 acceptance must remain unauthorized")

    templates = document.get("templates")
    expected_artifact_types = {
        "activation",
        "extraction",
        "model_input",
        "rollout",
    }
    if not isinstance(templates, dict):
        return (*violations, "Registry v2 templates must be an object")
    if set(templates) != expected_artifact_types:
        violations.append("Registry v2 artifact-type template inventory changed")
    field_sets = expected_binding["field_sets"]
    for artifact_type in sorted(expected_artifact_types):
        template = templates.get(artifact_type)
        path = f"templates.{artifact_type}"
        if not isinstance(template, dict):
            violations.append(f"{path} must be an object")
            continue
        if set(template) != set(REGISTRY_V2_TEMPLATE_TYPES):
            violations.append(f"{path} must contain all six template types")
        verified = template.get("verified_authorization_record")
        if not isinstance(verified, dict):
            violations.append(f"{path}.verified_authorization_record must be separate")
            continue
        if set(verified) != VERIFIED_AUTHORIZATION_TEMPLATE_FIELDS:
            violations.append(f"{path}.verified_authorization_record shape changed")
            continue
        trusted_entry = verified.get("trusted_artifact_authorization")
        if not isinstance(trusted_entry, dict) or set(trusted_entry) != set(
            field_sets["trusted_artifact_authorization"]
        ):
            violations.append(f"{path} trusted authorization shape changed")
            continue
        authorization = trusted_entry.get("authorization")
        authorization_record = verified.get("authorization_record")
        authorization_verification = trusted_entry.get(
            "authorization_record_verification"
        )
        authorization_receipt = verified.get("authorization_receipt")
        expected_shapes = (
            (
                authorization,
                set(field_sets["artifact_authorization"]),
                "authorization",
            ),
            (
                authorization_record,
                set(field_sets["authorization_record"]),
                "authorization_record",
            ),
            (
                authorization_verification,
                set(field_sets["authorization_record_verification"]),
                "authorization_record_verification",
            ),
            (
                authorization_receipt,
                set(field_sets["authorization_receipt"]),
                "authorization_receipt",
            ),
        )
        invalid_shape = False
        for value, expected_fields, label in expected_shapes:
            if not isinstance(value, dict) or set(value) != expected_fields:
                violations.append(f"{path} {label} frozen shape changed")
                invalid_shape = True
        if invalid_shape:
            continue
        for record, label in (
            (authorization, "authorization"),
            (authorization_record, "authorization_record"),
        ):
            expected_non_null = {
                "artifact_type": artifact_type,
                "decision": "pending",
                "owner_id": "person_a",
                "owner_status": "pending",
            }
            for field, value in record.items():
                expected_value = expected_non_null.get(field)
                if value != expected_value:
                    violations.append(
                        f"{path} {label}.{field} must remain {expected_value!r}"
                    )
        if any(value is not None for value in authorization_verification.values()):
            violations.append(f"{path} authorization verification must remain pending")
        if any(value is not None for value in authorization_receipt.values()):
            violations.append(f"{path} authorization receipt must remain null")
        byte_template = verified.get("authorization_record_bytes")
        if (
            not isinstance(byte_template, dict)
            or set(byte_template)
            != {
                "authorization_record_id",
                "byte_size",
                "canonical_utf8_json_bytes",
                "sha256",
            }
            or any(value is not None for value in byte_template.values())
        ):
            violations.append(f"{path} authorization-record bytes must remain null")
        context = verified.get("verification_context")
        expected_context = {
            "accepted": False,
            "artifact_id": None,
            "owner_id": "person_a",
            "source_authority_revision": None,
            "status": "pending_future_authorization_verification",
            "verification_receipt_id": None,
            "verification_result": False,
            "verifier_authority_id": None,
            "verified": False,
        }
        if context != expected_context:
            violations.append(f"{path} verification context changed")
    return tuple(violations)


def validate_package_policy(documents: dict[str, Any]) -> tuple[str, ...]:
    violations: list[str] = []
    if set(documents) != set(ALL_OUTPUT_PATHS):
        violations.append("generated package path inventory changed")
    for relative_path in sorted(documents):
        violations.extend(
            _protected_false_violations(
                documents[relative_path],
                relative_path,
            )
        )
    selected = documents.get("selected_c_inputs.json")
    if isinstance(selected, dict):
        violations.extend(validate_selected_c_inputs(selected))
    else:
        violations.append("selected_c_inputs.json is missing")
    authority = documents.get("authority_binding.json", {})
    authorization = authority.get("authorization", {})
    for field in (
        "automatic_phase6_transition_allowed",
        "person_a_phase6_authorized",
        "production_execution_performed",
        "registry_v2_acceptance_authorized",
        "scientific_execution_authorized",
    ):
        if not isinstance(authorization, dict) or authorization.get(field) is not False:
            violations.append(f"authority_binding.json.authorization.{field} false")
    validation = documents.get("validation_receipt.json", {})
    expected_zero_fields = (
        "accepted_artifact_count",
        "accepted_placeholder_count",
        "activation_run_count",
        "extraction_run_count",
        "model_load_count",
        "production_execution_count",
        "registry_v2_accepted_record_count",
        "rollout_run_count",
    )
    for field in expected_zero_fields:
        if validation.get(field) != 0:
            violations.append(f"validation_receipt.json.{field} must equal zero")
    configuration = documents.get("immutable_runtime_configuration.json", {})
    for index, record in enumerate(configuration.get("configuration", [])):
        if not isinstance(record, dict) or record.get("classification") != PROPOSED:
            violations.append(
                "immutable_runtime_configuration.json.configuration"
                f"[{index}] must be proposed"
            )
    contracts = (
        "model_input_contract.json",
        "extraction_contract.json",
        "activation_contract.json",
        "rollout_contract.json",
    )
    for relative_path in contracts:
        contract = documents.get(relative_path, {})
        if contract.get("instantiated_output_artifact") is not False:
            violations.append(f"{relative_path} instantiates an output")
        if contract.get("future_artifact_id") is not None:
            violations.append(f"{relative_path} future_artifact_id must be null")
        if contract.get("future_sha256") is not None:
            violations.append(f"{relative_path} future_sha256 must be null")
        if contract.get("future_byte_size") is not None:
            violations.append(f"{relative_path} future_byte_size must be null")
    trust = documents.get("registry_v2_trust_templates.json", {})
    if isinstance(trust, dict):
        violations.extend(validate_registry_v2_trust_templates(trust))
    else:
        violations.append("registry_v2_trust_templates.json is missing")
    promotions: set[str] = set()
    promotion_records: dict[str, dict[str, Any]] = {}
    for relative_path in contracts:
        promotions.update(documents[relative_path].get("prohibited_promotions", []))
        for record in documents[relative_path].get(
            "prohibited_promotion_records",
            [],
        ):
            if not isinstance(record, dict):
                violations.append(
                    f"{relative_path} prohibited promotion record is invalid"
                )
                continue
            promotion_id = record.get("promotion_id")
            if not isinstance(promotion_id, str):
                violations.append(f"{relative_path} prohibited promotion ID is invalid")
                continue
            if promotion_id in promotion_records:
                violations.append(
                    f"duplicate prohibited promotion record: {promotion_id}"
                )
            promotion_records[promotion_id] = record
    if promotions != set(PROHIBITED_PROMOTIONS):
        violations.append("prohibited-promotion inventory changed")
    if set(promotion_records) != set(PROHIBITED_PROMOTIONS):
        violations.append("prohibited-promotion record inventory changed")
    for promotion_id, expected in PROHIBITED_PROMOTIONS.items():
        record = promotion_records.get(promotion_id, {})
        for field in ("path", "reason", "sha256"):
            if record.get(field) != expected[field]:
                violations.append(
                    f"prohibited promotion {promotion_id} {field} changed"
                )
        if record.get("promotion_allowed") is not False:
            violations.append(
                f"prohibited promotion {promotion_id} must remain forbidden"
            )
        if record.get("registry_v2_accepted") is not False:
            violations.append(
                f"prohibited promotion {promotion_id} Registry v2 state changed"
            )
        if record.get("scientific_artifact") is not False:
            violations.append(
                f"prohibited promotion {promotion_id} scientific state changed"
            )
    return tuple(violations)


def build_documents() -> dict[str, Any]:
    verify_repository_authority()
    _verify_local_prohibited_bytes()
    selected = _selected_c_inputs()
    documents: dict[str, Any] = {
        "activation_contract.json": _activation_contract(selected),
        "authority_binding.json": _authority_binding(),
        "blocker_receipt.json": _blocker_receipt(),
        "extraction_contract.json": _extraction_contract(selected),
        "handoff_plan.json": _handoff_plan(),
        "immutable_runtime_configuration.json": _runtime_configuration(),
        "model_input_contract.json": _model_input_contract(selected),
        "registry_v2_trust_templates.json": _trust_templates(),
        "rollout_contract.json": _rollout_contract(),
        "selected_c_inputs.json": selected,
        "validation_receipt.json": _validation_receipt(),
    }
    documents["sha256_inventory.json"] = {
        "files": {
            relative_path: _sha256(_json_bytes(document))
            for relative_path, document in sorted(documents.items())
        },
        "package_file_count": len(ALL_OUTPUT_PATHS),
        "schema_id": (
            "person-a-phase4-step4-1-production-handoff-preflight-sha256-inventory-v0.1"
        ),
        "schema_version": SCHEMA_VERSION,
        "self_exclusion": "sha256_inventory.json",
    }
    violations = validate_package_policy(documents)
    if violations:
        raise RuntimeError("; ".join(violations))
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
        description=("Build the Person A non-scientific production-handoff preflight.")
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_ROOT,
        help="Output directory; defaults to the authoritative evidence root.",
    )
    arguments = parser.parse_args()
    write_documents(arguments.output_dir.resolve())


if __name__ == "__main__":
    main()
