"""Build Person A's 66-cell Person C intake and owner acknowledgement.

This builder consumes Person C's committed C7.5 MVP handoff package at an exact
commit, verifies it independently, binds Person A's exact production
authorities, and publishes the Person A owner acknowledgement required before
Phase 6 extraction.

It never authorizes Phase 6, never loads a model, and never extracts anything.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "docs" / "status" / "person_a_phase6_66_cell_intake_v0_1"
BUILDER_PATH = "scripts/build_person_a_phase6_66_cell_intake_v0_1.py"
TEST_PATH = "tests/models/test_person_a_phase6_66_cell_intake_v0_1.py"
SCHEMA_VERSION = "1.0"
SCHEMA_PREFIX = "person-a-phase6-66-cell-intake-v0.1"

A_BRANCH = "role/person-a-model"
A_STARTING_AUTHORITY = "ef98d184aaed8f03757add4ecac4a48968bb6fcc"

# --------------------------------------------------------------------------
# Person C authority (read as exact Git objects; C's branch is never merged)
# --------------------------------------------------------------------------
C_BRANCH = "role/person-c-data"
C_REMOTE_REF = "origin/role/person-c-data"
C_COMMIT = "a8bed8adf7e24ca7fe5b6b6afa3342da61434be3"
C_PACKAGE_ROOT = "docs/status/person_c_c7_mvp_handoff_v0_1"
C_ACCEPTED_MANIFEST_PATH = f"{C_PACKAGE_ROOT}/trajectories_mvp_manifest.json"
C_ACCEPTED_MANIFEST_SHA256 = (
    "96ba43e15bc024aeaef7c519fa4ece0a4afe0bb0e877501dffaca44fee927ff7"
)
C_CONSUMER_RECEIPT_PATH = (
    f"{C_PACKAGE_ROOT}/consumer_handoffs/person_a_handoff_receipt.json"
)
C_INVENTORY_PATH = f"{C_PACKAGE_ROOT}/sha256_inventory.json"
C_LEDGER_PATH = f"{C_PACKAGE_ROOT}/accepted_excluded_ledger.json"
C_VALIDATION_RECEIPT_PATH = f"{C_PACKAGE_ROOT}/validation_receipt.json"
C_HANDOFF_RECEIPT_PATH = f"{C_PACKAGE_ROOT}/handoff_receipt.json"
C_QA_EXCLUSION_PATH = f"{C_PACKAGE_ROOT}/qa_exclusion_report.json"

EXPECTED_ACCEPTED_COUNT = 66
EXPECTED_EXCLUDED_COUNT = 0
EXPECTED_FIRST_EPISODE = 12601
EXPECTED_LAST_EPISODE = 12666

# --------------------------------------------------------------------------
# Person A production authorities (pinned; drift fails the build)
# --------------------------------------------------------------------------
A_CONFIG_PATH = "configs/experiments/mvp.yaml"
A_CONFIG_SHA256 = "3c20c014dddd9b2f8b9a9225b97d7d6d11994b08363f5026d8c26fd2f5aaaaa3"

# _preprocess_bgr_frame and _OfficialActionConverter are both defined in this
# module, so one file SHA-256 pins both implementations.
A_PREPROCESS_IMPLEMENTATION_PATH = (
    "src/mineocclude/models/_mineworld_adapter_wave2.py"
)
A_PREPROCESS_IMPLEMENTATION_SHA256 = (
    "02fd79fe5cd8463dc0117c3207f8d37c6c4f69b9f7017a9aaa4e8ef5e77609f8"
)
A_ACTION_CONVERTER_PATH = A_PREPROCESS_IMPLEMENTATION_PATH
A_ACTION_CONVERTER_SHA256 = A_PREPROCESS_IMPLEMENTATION_SHA256

A_FRAME_MAP_SCHEMA_PATH = "src/mineocclude/contracts/trajectory.py"
A_FRAME_MAP_SCHEMA_SHA256 = (
    "4cd00906b2bc55a8e4da26d0cd0a447c5acb53f175e09edd9bf7f77733dc3c67"
)
A_FRAME_TOKEN_MAP_PATH = "src/mineocclude/contracts/activation.py"
A_FRAME_TOKEN_MAP_SHA256 = (
    "ce1564ee831b04ea4afbf3437f8f985c8f39ce3ebbb6eba8ee2dd515333b5dba"
)
A_IDENTITY_CONTRACT_PATH = "src/mineocclude/contracts/identity.py"
A_IDENTITY_CONTRACT_SHA256 = (
    "dfd88378ddff219a39925a78a1c13e2978562dc64142d373cfb8d607e1f2729e"
)
A_HOOKS_PATH = "src/mineocclude/activations/hooks.py"
A_HOOKS_SHA256 = "6dc708dfc7a68030d5e83e920e7acce3664550bc33466a7f5efa5ff0acbe5088"
A_POOL_PATH = "src/mineocclude/activations/pool.py"
A_POOL_SHA256 = "a5fd4c5d7272883432c29401e90880e70b8f90af2c0d0365bf65bc2847b0ead7"
A_ACTIVATION_STORE_PATH = "src/mineocclude/activations/store_v2.py"
A_ACTIVATION_STORE_SHA256 = (
    "8c2313f4ab99c02abb302af1d0b688ba353e34a1cd7985492ed9e562995dd575"
)
A_PUBLIC_ADAPTER_PATH = "src/mineocclude/models/mineworld_adapter.py"
A_PUBLIC_ADAPTER_SHA256 = (
    "0d8f55fbd24a1552bd9242b3a4554f7cdc15240b24865904e2f77446128516a5"
)

PINNED_A_SOURCE_FILES = {
    "action_converter_implementation": (
        A_ACTION_CONVERTER_PATH,
        A_ACTION_CONVERTER_SHA256,
    ),
    "activation_store_v2": (A_ACTIVATION_STORE_PATH, A_ACTIVATION_STORE_SHA256),
    "frame_map_schema": (A_FRAME_MAP_SCHEMA_PATH, A_FRAME_MAP_SCHEMA_SHA256),
    "frame_token_map": (A_FRAME_TOKEN_MAP_PATH, A_FRAME_TOKEN_MAP_SHA256),
    "hook_implementation": (A_HOOKS_PATH, A_HOOKS_SHA256),
    "identity_contract": (A_IDENTITY_CONTRACT_PATH, A_IDENTITY_CONTRACT_SHA256),
    "mvp_configuration": (A_CONFIG_PATH, A_CONFIG_SHA256),
    "pooling_implementation": (A_POOL_PATH, A_POOL_SHA256),
    "preprocessing_implementation": (
        A_PREPROCESS_IMPLEMENTATION_PATH,
        A_PREPROCESS_IMPLEMENTATION_SHA256,
    ),
    "public_adapter_protocol": (A_PUBLIC_ADAPTER_PATH, A_PUBLIC_ADAPTER_SHA256),
}

# Previously frozen accepted Person A authority (Step 7.1 identity freeze).
A_IDENTITY_FREEZE_PATH = (
    "docs/status/person_a_phase7_mvp_v0_1/step_7_1_identity_freeze.json"
)
FROZEN_CONFIG_HASH = (
    "42ffaca8dd9e80012c89511b2fb7e767fe105a61b06301d8234be425f0eff314"
)
FROZEN_PREPROCESS_HASH = (
    "8b585e1ffe7d9b7c7bf549f8b5695825bbd2a5b2579e4adf607ca5fa5786635c"
)
FROZEN_MODEL_HASH = (
    "a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5"
)

A_PREFLIGHT_RUNTIME_CONFIG_PATH = (
    "docs/status/person_a_phase4_step4_1_production_handoff_preflight_v0_1"
    "/immutable_runtime_configuration.json"
)
A_EXECUTION_HOST_CONTRACT_PATH = (
    "docs/status/person_a_phase6_sagemaker_runtime_addendum_v0_1"
    "/execution_host_contract.json"
)

APPROVED_EXECUTION_ENVIRONMENT = "aws_sagemaker_linux_gpu"
LOCAL_HOST_ROLE = "preparation_only"

OUTPUT_PATHS = (
    "authority_binding.json",
    "byte_accessibility_receipt.json",
    "c_intake_verification.json",
    "expected_model_frame_universe.json",
    "person_a_owner_acknowledgement.json",
    "production_authorities.json",
    "sha256_inventory.json",
    "validation_receipt.json",
)

PROTECTED_FALSE_FIELDS = frozenset(
    {
        "aggregate_phase6_runtime_authorized",
        "automatic_phase6_transition_allowed",
        "gpu_extraction_started",
        "model_loaded",
        "person_a_66_extraction_ready",
        "person_a_phase6_authorized",
        "person_a_66_activation_index_exists",
        "production_activation_bytes_created",
        "production_extraction_bytes_created",
        "real_frame_maps_materialized",
        "registry_v2_acceptance_authorized",
        "scientific_execution_performed",
        "self_authorizes_phase6",
    }
)


# --------------------------------------------------------------------------
# Primitives
# --------------------------------------------------------------------------
def _completed(command: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(command, cwd=ROOT, check=False, capture_output=True)


def _git_text(*arguments: str) -> str:
    result = _completed(["git", *arguments])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout.decode("utf-8").strip()


def _git_bytes(commit: str, path: str) -> bytes:
    result = _completed(["git", "show", f"{commit}:{path}"])
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Unable to read {commit}:{path}: {detail}")
    return result.stdout


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _c_document(path: str) -> tuple[dict[str, Any], str, int]:
    raw = _git_bytes(C_COMMIT, path)
    document = json.loads(raw)
    if not isinstance(document, dict):
        raise TypeError(f"Person C source is not an object: {path}")
    return document, _sha256(raw), len(raw)


# --------------------------------------------------------------------------
# Authority verification
# --------------------------------------------------------------------------
def verify_authorities() -> str:
    """Verify the A branch, the C commit, and the C manifest bytes."""

    branch = _git_text("branch", "--show-current")
    if branch != A_BRANCH:
        raise RuntimeError(f"Unexpected Person A branch: {branch!r}")
    if (
        _completed(
            ["git", "cat-file", "-e", f"{A_STARTING_AUTHORITY}^{{commit}}"]
        ).returncode
        != 0
    ):
        raise RuntimeError(f"Missing Person A authority: {A_STARTING_AUTHORITY}")
    if (
        _completed(
            ["git", "merge-base", "--is-ancestor", A_STARTING_AUTHORITY, "HEAD"]
        ).returncode
        != 0
    ):
        raise RuntimeError("Person A starting authority is not an ancestor of HEAD")
    if _completed(["git", "cat-file", "-e", f"{C_COMMIT}^{{commit}}"]).returncode != 0:
        raise RuntimeError(f"Missing Person C commit: {C_COMMIT}")
    if (
        _completed(
            ["git", "merge-base", "--is-ancestor", C_COMMIT, C_REMOTE_REF]
        ).returncode
        != 0
    ):
        raise RuntimeError("Person C commit is not reachable from the remote C branch")
    if _sha256(_git_bytes(C_COMMIT, C_ACCEPTED_MANIFEST_PATH)) != (
        C_ACCEPTED_MANIFEST_SHA256
    ):
        raise RuntimeError("Person C accepted-manifest SHA-256 does not match")
    return A_STARTING_AUTHORITY


def verify_pinned_a_sources() -> dict[str, dict[str, Any]]:
    """Verify that every pinned Person A production file is unchanged."""

    records: dict[str, dict[str, Any]] = {}
    for name, (path, expected) in sorted(PINNED_A_SOURCE_FILES.items()):
        raw = (ROOT / path).read_bytes()
        digest = _sha256(raw)
        if digest != expected:
            raise RuntimeError(
                f"Person A production authority drifted: {path} "
                f"expected {expected}, observed {digest}"
            )
        records[name] = {
            "byte_size": len(raw),
            "path": path,
            "sha256": digest,
        }
    return records


# --------------------------------------------------------------------------
# Person C intake verification
# --------------------------------------------------------------------------
def verify_c_package() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Independently verify Person C's 66-cell package. Never trusts a claim."""

    manifest, manifest_sha, manifest_size = _c_document(C_ACCEPTED_MANIFEST_PATH)
    inventory, inventory_sha, _ = _c_document(C_INVENTORY_PATH)
    ledger, ledger_sha, _ = _c_document(C_LEDGER_PATH)
    c_receipt, receipt_sha, _ = _c_document(C_VALIDATION_RECEIPT_PATH)
    handoff, handoff_sha, _ = _c_document(C_HANDOFF_RECEIPT_PATH)
    qa_report, qa_sha, _ = _c_document(C_QA_EXCLUSION_PATH)
    consumer, consumer_sha, consumer_size = _c_document(C_CONSUMER_RECEIPT_PATH)

    violations: list[str] = []
    if manifest_sha != C_ACCEPTED_MANIFEST_SHA256:
        violations.append("accepted manifest SHA-256 mismatch")

    records = manifest.get("records")
    if not isinstance(records, list):
        raise TypeError("Person C manifest records are missing")

    episode_ids = [record["episode_id"] for record in records]
    trajectory_ids = [record["trajectory_id"] for record in records]
    planned_cells = [record["planned_cell_id"] for record in records]
    expected_episodes = list(range(EXPECTED_FIRST_EPISODE, EXPECTED_LAST_EPISODE + 1))

    accepted_true = sum(1 for record in records if record.get("accepted") is True)
    if manifest.get("accepted_count") != EXPECTED_ACCEPTED_COUNT:
        violations.append("manifest accepted_count is not 66")
    if manifest.get("excluded_count") != EXPECTED_EXCLUDED_COUNT:
        violations.append("manifest excluded_count is not 0")
    if len(records) != EXPECTED_ACCEPTED_COUNT or accepted_true != (
        EXPECTED_ACCEPTED_COUNT
    ):
        violations.append("manifest does not carry exactly 66 accepted records")
    if sorted(episode_ids) != expected_episodes:
        violations.append("episode set is not exactly ep12601 through ep12666")
    if len(set(trajectory_ids)) != len(trajectory_ids):
        violations.append("duplicate trajectory_id in manifest")
    if len(set(planned_cells)) != len(planned_cells):
        violations.append("duplicate planned_cell_id in manifest")
    if any(record.get("status") != "PASS" for record in records):
        violations.append("manifest contains a non-PASS record")
    if ledger.get("accepted_count") != EXPECTED_ACCEPTED_COUNT or ledger.get(
        "excluded_count"
    ) != EXPECTED_EXCLUDED_COUNT:
        violations.append("ledger does not reconcile 66 accepted / 0 excluded")
    if sorted(ledger.get("accepted_episode_ids", [])) != expected_episodes:
        violations.append("ledger episode identities do not match the manifest")
    if ledger.get("excluded_episode_ids"):
        violations.append("ledger declares excluded episodes")
    if qa_report.get("excluded_count") != EXPECTED_EXCLUDED_COUNT or qa_report.get(
        "exclusions"
    ):
        violations.append("QA exclusion report declares exclusions")
    if handoff.get("phase_6_runtime_authorized") is not False:
        violations.append("Person C package claims Phase 6 runtime authorization")

    # Person C's own validation receipt must agree with the independent checks.
    if c_receipt.get("episode_id_range_exact") != [
        EXPECTED_FIRST_EPISODE,
        EXPECTED_LAST_EPISODE,
    ]:
        violations.append("C validation receipt episode range disagrees")
    for claim in (
        "ledger_reconciles_66_0",
        "source_integrity_verified",
        "unique_episode_id",
        "unique_planned_cell_id",
        "unique_trajectory_id",
    ):
        if c_receipt.get(claim) is not True:
            violations.append(f"C validation receipt does not assert {claim}")
    if c_receipt.get("no_episode_payload_bytes_committed") is not True:
        violations.append("C validation receipt no longer excludes payload bytes")

    # Every declared package file must resolve at the exact C commit.
    declared = inventory.get("files")
    if not isinstance(declared, dict):
        raise TypeError("Person C sha256_inventory files map is missing")
    unresolved: list[str] = []
    for relative, expected in sorted(declared.items()):
        raw = _git_bytes(C_COMMIT, f"{C_PACKAGE_ROOT}/{relative}")
        if _sha256(raw) != expected:
            unresolved.append(relative)
    if unresolved:
        violations.append(f"{len(unresolved)} declared C package hashes do not resolve")

    # Every per-trajectory bundle must exist and agree with the manifest.
    bundles: list[dict[str, Any]] = []
    manifest_by_episode = {record["episode_id"]: record for record in records}
    for episode_id in expected_episodes:
        relative = f"per_trajectory/ep{episode_id}.json"
        if relative not in declared:
            violations.append(f"missing per-trajectory bundle: {relative}")
            continue
        raw = _git_bytes(C_COMMIT, f"{C_PACKAGE_ROOT}/{relative}")
        bundle = json.loads(raw)
        identity = bundle["identity"]
        manifest_record = manifest_by_episode[episode_id]
        if identity["trajectory_id"] != manifest_record["trajectory_id"]:
            violations.append(f"bundle/manifest trajectory mismatch: ep{episode_id}")
        if identity["layout_id"] != manifest_record["layout_id"]:
            violations.append(f"bundle/manifest layout mismatch: ep{episode_id}")
        if bundle["acceptance"]["accepted"] is not True:
            violations.append(f"bundle is not accepted: ep{episode_id}")
        bundles.append(bundle)

    # Every C-side metadata reference must resolve at the exact C commit.
    metadata_paths: dict[str, str] = {}
    for name, entry in sorted(manifest.get("source_inventories", {}).items()):
        metadata_paths[entry["path"]] = entry["sha256"]
    for bundle in bundles:
        for key in ("episode_inventory", "output_inventory", "sha256_inventory"):
            entry = bundle["provenance"][key]
            metadata_paths[entry["path"]] = entry["sha256"]
        acceptance = bundle["acceptance"]
        metadata_paths[acceptance["acceptance_authority_path"]] = acceptance[
            "acceptance_authority_sha256"
        ]
    metadata_unresolved: list[str] = []
    for path, expected in sorted(metadata_paths.items()):
        try:
            raw = _git_bytes(C_COMMIT, path)
        except RuntimeError:
            metadata_unresolved.append(path)
            continue
        if _sha256(raw) != expected:
            metadata_unresolved.append(path)
    if metadata_unresolved:
        violations.append(
            f"{len(metadata_unresolved)} C metadata references do not resolve"
        )

    if consumer.get("consumer_role") != "person_a":
        violations.append("Person A consumer handoff receipt is not addressed to A")
    if consumer.get("manifest_sha256") != C_ACCEPTED_MANIFEST_SHA256:
        violations.append("Person A consumer receipt binds a different manifest")
    if consumer.get("expected_count_by_consumer") != EXPECTED_ACCEPTED_COUNT:
        violations.append("Person A consumer receipt does not expect 66")

    verification = {
        "c_branch": C_BRANCH,
        "c_branch_merged": False,
        "c_commit": C_COMMIT,
        "c_commit_exists": True,
        "c_commit_remote_reachable": True,
        "c_manifest_declared_sha256": C_ACCEPTED_MANIFEST_SHA256,
        "c_manifest_observed_sha256": manifest_sha,
        "c_manifest_path": C_ACCEPTED_MANIFEST_PATH,
        "c_manifest_valid": not violations,
        "c_metadata_reference_count": len(metadata_paths),
        "c_metadata_references_unresolved": metadata_unresolved,
        "c_package_file_count": len(declared),
        "c_package_hashes_unresolved": unresolved,
        "c_source_commit": manifest.get("source_commit"),
        "canonical_collection_id": manifest.get("canonical_c6a_id"),
        "condition_counts": {
            "by_control_type": dict(
                sorted(Counter(record["control_type"] for record in records).items())
            ),
            "by_layout_id": dict(
                sorted(Counter(record["layout_id"] for record in records).items())
            ),
            "by_set_id": dict(
                sorted(Counter(record["set_id"] for record in records).items())
            ),
        },
        "duplicate_planned_cell_ids": sorted(
            {value for value, count in Counter(planned_cells).items() if count > 1}
        ),
        "duplicate_trajectory_ids": sorted(
            {value for value, count in Counter(trajectory_ids).items() if count > 1}
        ),
        "episode_id_range_observed": [min(episode_ids), max(episode_ids)],
        "episode_set_exact": sorted(episode_ids) == expected_episodes,
        "excluded_trajectory_count": EXPECTED_EXCLUDED_COUNT,
        "missing_episode_ids": sorted(set(expected_episodes) - set(episode_ids)),
        "observed_accepted_count": accepted_true,
        "per_trajectory_bundle_count": len(bundles),
        "person_a_consumer_receipt": {
            "byte_size": consumer_size,
            "downstream_a_production_handoff_status": consumer.get(
                "role_specific", {}
            ).get("downstream_a_production_handoff_status"),
            "exists": True,
            "path": C_CONSUMER_RECEIPT_PATH,
            "sha256": consumer_sha,
        },
        "person_c_reported_accepted_count": manifest.get("accepted_count"),
        "person_c_reported_excluded_count": manifest.get("excluded_count"),
        "schema_id": f"{SCHEMA_PREFIX}-c-intake-verification",
        "schema_version": SCHEMA_VERSION,
        "source_document_hashes": {
            C_ACCEPTED_MANIFEST_PATH: manifest_sha,
            C_CONSUMER_RECEIPT_PATH: consumer_sha,
            C_HANDOFF_RECEIPT_PATH: handoff_sha,
            C_INVENTORY_PATH: inventory_sha,
            C_LEDGER_PATH: ledger_sha,
            C_QA_EXCLUSION_PATH: qa_sha,
            C_VALIDATION_RECEIPT_PATH: receipt_sha,
        },
        "verification_violations": sorted(violations),
    }
    verification["c_manifest_byte_size"] = manifest_size
    return verification, bundles


# --------------------------------------------------------------------------
# Person A production authorities
# --------------------------------------------------------------------------
def _load_frozen_identity() -> dict[str, Any]:
    document = json.loads((ROOT / A_IDENTITY_FREEZE_PATH).read_bytes())
    identity = document["identity"]
    if identity["config_hash"] != FROZEN_CONFIG_HASH:
        raise RuntimeError("Frozen config hash changed")
    if identity["preprocess_hash"] != FROZEN_PREPROCESS_HASH:
        raise RuntimeError("Frozen preprocess hash changed")
    if identity["model_hash"] != FROZEN_MODEL_HASH:
        raise RuntimeError("Frozen model hash changed")
    return document


def _live_config_identity() -> dict[str, Any]:
    import sys

    source = str(ROOT / "src")
    if source not in sys.path:
        sys.path.insert(0, source)
    from mineocclude.experiments.mvp_config import load_mvp_config

    return load_mvp_config(ROOT / A_CONFIG_PATH).identity()


def production_authorities(source_records: dict[str, dict[str, Any]]) -> dict[str, Any]:
    freeze = _load_frozen_identity()
    live = _live_config_identity()
    values = freeze["result_changing_values"]

    unchanged = (
        live["config_hash"] == FROZEN_CONFIG_HASH
        and live["preprocess_hash"] == FROZEN_PREPROCESS_HASH
        and live["model_hash"] == FROZEN_MODEL_HASH
        and live["config_file_sha256"] == A_CONFIG_SHA256
    )

    runtime_configuration = json.loads(
        (ROOT / A_PREFLIGHT_RUNTIME_CONFIG_PATH).read_bytes()
    )
    runtime_values = {
        row["name"]: row["value"] for row in runtime_configuration["configuration"]
    }

    return {
        "action_converter": {
            "action_token_contract": {
                "positional_role_count": 11,
                "positional_roles": [
                    "bos",
                    "camera_pitch",
                    "camera_yaw",
                    "hotbar",
                    "forward_back",
                    "left_right",
                    "sprint_sneak",
                    "use_attack",
                    "jump",
                    "drop_pick",
                    "eos",
                ],
                "tokens_per_frame_action_pair": 347,
                "tokens_returned_per_action": 11,
                "vocabulary_size": 8262,
            },
            "action_vocab_offset": 8192,
            "converter_class": (
                "mineocclude.models._mineworld_adapter_wave2._OfficialActionConverter"
            ),
            "converter_identity": (
                "mineworld_action_compatibility@1.0:"
                "7e8d16db01f085481d41d340e5a0b84669b8e163f3338d5fd572731532c52746"
            ),
            "determinism_rule": "conversion is executed twice and must agree exactly",
            "implementation_path": A_ACTION_CONVERTER_PATH,
            "implementation_sha256": A_ACTION_CONVERTER_SHA256,
            "pinned_mcdataset_git_blob_sha256": (
                "7e8d16db01f085481d41d340e5a0b84669b8e163f3338d5fd572731532c52746"
            ),
            "pinned_mineworld_source_revision": values["model.source_revision"],
            "upstream_entry_points": [
                "MCDataset.json_action_to_env_action",
                "MCDataset.get_action_index_from_actiondict",
                "MCDataset.make_action_vocab",
            ],
        },
        "activation_storage": {
            "activation_index_format_version": "person-a-activation-index-v2",
            "activation_index_key": runtime_values["activation_index_key"],
            "activation_index_schema_version": SCHEMA_VERSION,
            "activation_store_format_version": "person-a-activation-store-v2",
            "activation_store_path": A_ACTIVATION_STORE_PATH,
            "activation_store_sha256": A_ACTIVATION_STORE_SHA256,
            "chunk_and_index_rules": runtime_values["chunk_and_index_rules"],
            "frozen_config_extraction_stored_dtype": values["extraction.stored_dtype"],
            "hooked_source_tensor_dtype": runtime_values["source_tensor_dtype"],
            "pooled_output_dtype": runtime_values["pooling"]["stored_dtype"],
            "stored_dtype_reconciliation_required": (
                values["extraction.stored_dtype"]
                != runtime_values["pooling"]["stored_dtype"]
            ),
            "stored_dtype_reconciliation_note": (
                "configs/experiments/mvp.yaml pins extraction.stored_dtype=float16 "
                "while the frozen preflight pooling contract and "
                "storage.bytes_per_activation_row=8192.68 (2048 x 4 bytes) imply "
                "float32 pooled storage. Person A does not resolve this here: "
                "extraction.stored_dtype is a result_changing path and a change "
                "requires a dated decision record and a new run identity."
            ),
            "vector_width": values["extraction.vector_width"],
        },
        "frame_map": {
            "authoritative_model_facing_key": ["trajectory_id", "model_frame_idx"],
            "capture_key": [
                "episode_id",
                "trajectory_id",
                "server_tick",
                "render_frame_idx",
                "action_idx",
                "model_frame_idx",
            ],
            "expected_stream_format": "jsonl",
            "identity_rule": (
                "keys define identity; row order never defines identity"
            ),
            "row_streams_joined_on_capture_key": [
                "frame_map",
                "raw_actions",
                "normalized_actions",
                "server_state",
                "client_tick_log",
                "visibility",
                "seed_noise",
            ],
            "schema_path": A_FRAME_MAP_SCHEMA_PATH,
            "schema_sha256": A_FRAME_MAP_SCHEMA_SHA256,
            "schema_version": SCHEMA_VERSION,
            "traceability": {
                "action_idx": "frame_map capture key field",
                "authoritative_state": "server_state stream on the capture key",
                "condition_identity": (
                    "Person C per-trajectory bundle condition block "
                    "(seed, noise schedule identity, scene, layout, control type)"
                ),
                "episode_id": "frame_map capture key field",
                "layout_id": "Person C per-trajectory bundle identity block",
                "model_frame_idx": "frame_map capture key field",
                "normalized_action": "normalized_actions stream on the capture key",
                "raw_action": "raw_actions stream on the capture key",
                "render_frame_idx": "frame_map capture key field",
                "server_tick": "frame_map capture key field",
                "source_frame": (
                    "render_frame_idx addresses the exact Person C client PNG frame"
                ),
                "visibility": "visibility stream on the capture key",
            },
            "uniqueness_rule": (
                "each of server_tick, render_frame_idx, action_idx and "
                "model_frame_idx uniquely identifies one row per trajectory, and "
                "every joined stream must carry the identical capture-key set"
            ),
            "validator_entry_point": (
                "mineocclude.contracts.trajectory.validate_trajectory_package"
            ),
        },
        "model_and_checkpoint": {
            "checkpoint_reference": (
                "https://www.modelscope.cn/models/MineWorld/"
                "0dd5561ab317115831badc50e09a6ebe98693d0e"
            ),
            "checkpoint_sha256": values["model.checkpoint_sha256"],
            "decoder_layer_count": values["model.decoder_layer_count"],
            "decoder_layer_module_pattern": "transformer.model.layers.{layer_idx}",
            "external_artifact_index_path": (
                "docs/status/person_a_phase9_clean_run_v0_1/"
                "external_artifact_index.json"
            ),
            "model_asset_revision": values["model.asset_revision"],
            "model_class": "LlamaLVM",
            "model_config_sha256": values["model.config_sha256"],
            "model_identity": "mineworld-700m",
            "model_source_revision": values["model.source_revision"],
            "precision": values["model.precision"],
            "transformer_class": "LlamaForCausalLM",
            "vae_checkpoint_sha256": values["model.vae_checkpoint_sha256"],
            "vae_class": "VAE",
            "vae_config_sha256": values["model.vae_config_sha256"],
            "vae_identity": "mineworld-vae",
        },
        "extraction_hooks": {
            "expected_layer_count": values["model.decoder_layer_count"],
            "hook_discovery_version": (
                "person-a-phase4-decoder-output-v1.0:"
                f"{values['model.source_revision']}"
            ),
            "hook_implementation_path": A_HOOKS_PATH,
            "hook_implementation_sha256": A_HOOKS_SHA256,
            "hook_sites": [values["extraction.hook_site"]],
            "layer_indices": list(runtime_values["activation_layers"]),
            "mode": values["extraction.mode"],
            "pooling": values["extraction.pooling"],
            "pooling_identity": values["extraction.pooling_identity"],
            "pooling_implementation_path": A_POOL_PATH,
            "pooling_implementation_sha256": A_POOL_SHA256,
        },
        "frame_token_map": {
            "expected_visual_token_cardinality_per_frame": 336,
            "action_tokens_per_frame": 11,
            "max_model_frames_per_context": 16,
            "path": A_FRAME_TOKEN_MAP_PATH,
            "sha256": A_FRAME_TOKEN_MAP_SHA256,
            "tokens_per_frame_action_pair": 347,
            "type": "mineocclude.contracts.activation.FrameTokenMap",
            "version": SCHEMA_VERSION,
        },
        "preprocessing": {
            "color_convention": "source BGR decoded, converted to RGB (COLOR_BGR2RGB)",
            "config_file_sha256": A_CONFIG_SHA256,
            "config_hash": live["config_hash"],
            "config_path": A_CONFIG_PATH,
            "function": (
                "mineocclude.models._mineworld_adapter_wave2._preprocess_bgr_frame"
            ),
            "implementation_path": A_PREPROCESS_IMPLEMENTATION_PATH,
            "implementation_sha256": A_PREPROCESS_IMPLEMENTATION_SHA256,
            "interpolation": values["preprocess.interpolation"],
            "model_facing_resolution_hw": list(values["preprocess.model_resolution"]),
            "model_facing_tensor_layout": "CHW",
            "normalization": "(x - 0.5) / 0.5 per channel, float32, range [-1.0, 1.0]",
            "preprocess_hash": live["preprocess_hash"],
            "preprocessing_identity": values["preprocess.identity"],
            "preprocessing_profile": runtime_values["preprocessing_identity"],
            "public_protocol_path": A_PUBLIC_ADAPTER_PATH,
            "public_protocol_sha256": A_PUBLIC_ADAPTER_SHA256,
            "scaling": "uint8 divided by float32(255.0) after HWC to CHW transpose",
            "source_dtype": "uint8",
            "source_resolution_hw": [360, 640],
            "unchanged_from_frozen_accepted_authority": unchanged,
        },
        "schema_id": f"{SCHEMA_PREFIX}-production-authorities",
        "schema_version": SCHEMA_VERSION,
        "source_records": source_records,
        "frozen_authority": {
            "frozen_step": freeze["step"],
            "identity_freeze_path": A_IDENTITY_FREEZE_PATH,
            "live_config_identity": live,
            "status": freeze["status"],
            "unchanged_from_frozen_accepted_authority": unchanged,
        },
    }


# --------------------------------------------------------------------------
# Expected model-frame universe
# --------------------------------------------------------------------------
def expected_model_frame_universe(bundles: list[dict[str, Any]]) -> dict[str, Any]:
    layer_count = 20
    per_trajectory: dict[str, Any] = {}
    duplicates: list[str] = []
    for bundle in bundles:
        trajectory_id = bundle["identity"]["trajectory_id"]
        counts = bundle["qa_summary"]["cardinality_counts"]
        if trajectory_id in per_trajectory:
            duplicates.append(trajectory_id)
        aligned = (
            counts["frame_count"]
            == counts["action_row_count"]
            == counts["server_row_count"]
            == counts["client_tick_count"]
        )
        per_trajectory[trajectory_id] = {
            "action_row_count": counts["action_row_count"],
            "client_tick_count": counts["client_tick_count"],
            "episode_id": bundle["identity"]["episode_id"],
            "expected_activation_row_count": counts["frame_count"] * layer_count,
            "expected_chunk_count": layer_count,
            "expected_model_frame_count": counts["frame_count"],
            "layout_id": bundle["identity"]["layout_id"],
            "planned_cell_id": bundle["identity"]["planned_cell_id"],
            "server_row_count": counts["server_row_count"],
            "source_frame_count": counts["frame_count"],
            "stream_cardinalities_aligned": aligned,
        }

    frame_total = sum(
        entry["expected_model_frame_count"] for entry in per_trajectory.values()
    )
    misaligned = sorted(
        key
        for key, entry in per_trajectory.items()
        if not entry["stream_cardinalities_aligned"]
    )

    return {
        "derivation": (
            "Per-trajectory expected model-frame counts are taken from Person C's "
            "per-trajectory qa_summary.cardinality_counts, which report equal "
            "frame_count, action_row_count, server_row_count and client_tick_count. "
            "The Person A frame-map contract requires model_frame_idx to uniquely "
            "identify one row per trajectory across every joined stream, so the "
            "expected (trajectory_id, model_frame_idx) key count per trajectory "
            "equals that source frame count."
        ),
        "derivation_is_contract_derived_not_materialized": True,
        "duplicate_trajectory_ids": sorted(set(duplicates)),
        "expected_activation_row_count_total": frame_total * layer_count,
        "expected_activation_rows_per_layer": frame_total,
        "expected_chunk_count_total": len(per_trajectory) * layer_count,
        "expected_chunk_plan": {
            "chunk_layout": "one_chunk_per_decoder_layer",
            "chunks_per_trajectory": layer_count,
            "index_format": "canonical_json",
            "no_overwrite": True,
            "row_order": "trajectory_id,model_frame_idx,layer_idx,hook_site",
        },
        "expected_model_frame_key_count": frame_total,
        "expected_model_frame_key_universe_enumerated": False,
        "expected_pooled_vector_width": 2048,
        "expected_trajectory_count": len(per_trajectory),
        "key": ["trajectory_id", "model_frame_idx"],
        "layer_indices": list(range(layer_count)),
        "materialization_status": (
            "Person C's C7.5 package publishes no per-trajectory frame_map artifact "
            "for these 66 trajectories, and no production Person A frame map exists "
            "for them. The exact (trajectory_id, model_frame_idx) identities are "
            "therefore NOT materialized and are not enumerated here."
        ),
        "missing_trajectory_ids": [],
        "per_trajectory": dict(sorted(per_trajectory.items())),
        "real_frame_maps_materialized": False,
        "schema_id": f"{SCHEMA_PREFIX}-expected-model-frame-universe",
        "schema_version": SCHEMA_VERSION,
        "stream_cardinality_misaligned_trajectory_ids": misaligned,
        "trajectories_with_unknown_frame_count": [],
    }


# --------------------------------------------------------------------------
# Byte accessibility
# --------------------------------------------------------------------------
def byte_accessibility(bundles: list[dict[str, Any]], *, scan: bool) -> dict[str, Any]:
    execution_host = json.loads((ROOT / A_EXECUTION_HOST_CONTRACT_PATH).read_bytes())
    boundary = execution_host["execution_boundary"]

    per_trajectory: dict[str, Any] = {}
    missing_paths: list[str] = []
    mismatched_paths: list[str] = []
    total_bytes = 0
    artifacts_present = 0
    artifacts_absent = 0
    durable_uris: set[str] = set()

    for bundle in bundles:
        trajectory_id = bundle["identity"]["trajectory_id"]
        locations = bundle["locations"]
        if locations.get("durable_uri"):
            durable_uris.add(str(locations["durable_uri"]))
        if locations.get("s3_uri"):
            durable_uris.add(str(locations["s3_uri"]))
        entry: dict[str, Any] = {
            "artifact_count": len(bundle["artifacts"]),
            "artifacts_absent": 0,
            "artifacts_hash_verified": 0,
            "byte_size_total": 0,
            "durable_uri": locations.get("durable_uri"),
            "runtime_client_path": locations["runtime_path"]["client"],
            "runtime_server_path": locations["runtime_path"]["server"],
            "s3_uri": locations.get("s3_uri"),
            "state": "not_scanned",
        }
        if scan:
            for artifact in bundle["artifacts"]:
                path = Path(artifact["path_or_uri"])
                if not path.is_file():
                    artifacts_absent += 1
                    entry["artifacts_absent"] += 1
                    missing_paths.append(artifact["path_or_uri"])
                    continue
                artifacts_present += 1
                payload = path.read_bytes()
                if (
                    _sha256(payload) == artifact["sha256"]
                    and len(payload) == artifact["byte_size"]
                ):
                    entry["artifacts_hash_verified"] += 1
                    entry["byte_size_total"] += len(payload)
                    total_bytes += len(payload)
                else:
                    mismatched_paths.append(artifact["path_or_uri"])
            if entry["artifacts_absent"]:
                entry["state"] = "unavailable"
            elif entry["artifacts_hash_verified"] == entry["artifact_count"]:
                entry["state"] = "available_hash_verified"
            else:
                entry["state"] = "available_hash_mismatch"
        per_trajectory[trajectory_id] = entry

    available = sum(
        1
        for entry in per_trajectory.values()
        if entry["state"].startswith("available")
    )
    hash_verified = sum(
        1
        for entry in per_trajectory.values()
        if entry["state"] == "available_hash_verified"
    )
    unavailable = sum(
        1 for entry in per_trajectory.values() if entry["state"] == "unavailable"
    )

    return {
        "approved_execution_environment": boundary["allowed_production_environment"],
        "byte_source": (
            "person_c_windows_runtime_local_filesystem: "
            "C:\\Users\\lollo\\MineOcclude-Runtime\\person-c-c1-v0_1"
        ),
        "byte_source_kind": "local_windows_runtime_filesystem",
        "byte_source_reference_origin": (
            "Person C per-trajectory bundle locations.runtime_path and "
            "artifacts[].path_or_uri at commit " + C_COMMIT
        ),
        "bytes_accessible_from_approved_execution_environment": False,
        "bytes_committed_to_git": False,
        "durable_uri_assigned": bool(durable_uris),
        "durable_uris_declared_by_person_c": sorted(durable_uris),
        "external_transfer_blocker": (
            "Person C assigns no durable/S3 URI for the 66 episode payloads "
            "(locations.durable_uri and locations.s3_uri are null in every "
            "bundle, and the C handoff receipt records durable_s3_assigned=false). "
            "The bytes exist only on the local Windows preparation host, which is "
            "not the approved production execution environment "
            f"({boundary['allowed_production_environment']}). No transfer path is "
            "bound, and Person A does not invent one."
        ),
        "local_host_role": LOCAL_HOST_ROLE,
        "local_scan_performed": scan,
        "person_c_capture_output_bundle_sha256": (
            "c8453cb8a459d0d56d69f5bf39233997537e28a14b10a3a2ba4aeb3f421c624b"
        ),
        "per_trajectory": dict(sorted(per_trajectory.items())),
        "scanned_artifact_count_absent": artifacts_absent,
        "scanned_artifact_count_present": artifacts_present,
        "scanned_byte_total": total_bytes,
        "scanned_paths_hash_mismatch": sorted(mismatched_paths),
        "scanned_paths_missing": sorted(missing_paths),
        "schema_id": f"{SCHEMA_PREFIX}-byte-accessibility-receipt",
        "schema_version": SCHEMA_VERSION,
        "trajectory_count_available_on_local_host": available,
        "trajectory_count_hash_verified_on_local_host": hash_verified,
        "trajectory_count_unavailable_on_local_host": unavailable,
    }


# --------------------------------------------------------------------------
# Owner acknowledgement
# --------------------------------------------------------------------------
def owner_acknowledgement(
    *,
    a_commit: str,
    verification: dict[str, Any],
    authorities: dict[str, Any],
    universe: dict[str, Any],
    bytes_receipt: dict[str, Any],
) -> dict[str, Any]:
    input_contract_ready = bool(
        verification["c_manifest_valid"]
        and verification["observed_accepted_count"] == EXPECTED_ACCEPTED_COUNT
        and verification["excluded_trajectory_count"] == EXPECTED_EXCLUDED_COUNT
        and verification["episode_set_exact"]
        and not verification["duplicate_trajectory_ids"]
        and not verification["missing_episode_ids"]
        and verification["person_a_consumer_receipt"]["exists"]
        and authorities["preprocessing"]["unchanged_from_frozen_accepted_authority"]
    )
    byte_access_ready = bool(
        bytes_receipt["bytes_accessible_from_approved_execution_environment"]
    )
    extraction_ready = bool(
        input_contract_ready
        and byte_access_ready
        and universe["real_frame_maps_materialized"]
    )
    preprocessing = authorities["preprocessing"]
    converter = authorities["action_converter"]
    frame_map = authorities["frame_map"]
    model = authorities["model_and_checkpoint"]
    hooks = authorities["extraction_hooks"]
    token_map = authorities["frame_token_map"]
    storage = authorities["activation_storage"]

    return {
        "acknowledgement_id": "person-a-phase6-66-cell-intake-v0-1",
        "aggregate_phase6_runtime_authorized": False,
        "automatic_phase6_transition_allowed": False,
        "byte_accessibility": {
            "approved_execution_environment": bytes_receipt[
                "approved_execution_environment"
            ],
            "byte_source": bytes_receipt["byte_source"],
            "durable_uri_assigned": bytes_receipt["durable_uri_assigned"],
            "trajectory_count_available_on_local_host": bytes_receipt[
                "trajectory_count_available_on_local_host"
            ],
            "trajectory_count_hash_verified_on_local_host": bytes_receipt[
                "trajectory_count_hash_verified_on_local_host"
            ],
            "trajectory_count_unavailable_on_local_host": bytes_receipt[
                "trajectory_count_unavailable_on_local_host"
            ],
        },
        "expected_model_frame_universe": {
            "expected_activation_row_count_total": universe[
                "expected_activation_row_count_total"
            ],
            "expected_chunk_count_total": universe["expected_chunk_count_total"],
            "expected_model_frame_key_count": universe[
                "expected_model_frame_key_count"
            ],
            "expected_model_frame_key_universe_enumerated": False,
            "expected_trajectory_count": universe["expected_trajectory_count"],
            "key": universe["key"],
            "real_frame_maps_materialized": False,
        },
        "extraction_blockers": sorted(
            filter(
                None,
                [
                    None
                    if byte_access_ready
                    else "66_episode_bytes_not_reachable_from_approved_gpu_environment",
                    None
                    if universe["real_frame_maps_materialized"]
                    else "production_frame_map_artifacts_not_materialized",
                    None
                    if not storage["stored_dtype_reconciliation_required"]
                    else "activation_stored_dtype_authorities_disagree",
                    "aggregate_phase6_runtime_authorization_absent",
                ],
            )
        ),
        "gpu_extraction_started": False,
        "immutability": {
            "no_overwrite": True,
            "supersession_rule": (
                "A correction is published as a new versioned acknowledgement "
                "package; this package is never edited in place."
            ),
        },
        "model_loaded": False,
        "owner": "person_a",
        "person_a_66_activation_index_exists": False,
        "person_a_66_byte_access_ready": byte_access_ready,
        "person_a_66_extraction_ready": extraction_ready,
        "person_a_66_input_contract_ready": input_contract_ready,
        "person_a_branch": A_BRANCH,
        "person_a_commit": a_commit,
        "person_a_phase6_acknowledgement_ready": bool(
            input_contract_ready and not verification["verification_violations"]
        ),
        "person_a_phase6_authorized": False,
        "person_c": {
            "accepted_trajectory_count": verification["observed_accepted_count"],
            "commit": C_COMMIT,
            "episode_id_range": [EXPECTED_FIRST_EPISODE, EXPECTED_LAST_EPISODE],
            "excluded_trajectory_count": verification["excluded_trajectory_count"],
            "manifest_path": C_ACCEPTED_MANIFEST_PATH,
            "manifest_sha256": C_ACCEPTED_MANIFEST_SHA256,
            "manifest_valid": verification["c_manifest_valid"],
            "person_a_consumer_receipt_sha256": verification[
                "person_a_consumer_receipt"
            ]["sha256"],
        },
        "production_authorities": {
            "action_converter_identity": converter["converter_identity"],
            "action_converter_path": converter["implementation_path"],
            "action_converter_sha256": converter["implementation_sha256"],
            "action_vocab_offset": converter["action_vocab_offset"],
            "activation_index_format_version": storage[
                "activation_index_format_version"
            ],
            "activation_index_key": storage["activation_index_key"],
            "activation_storage_dtype_reconciliation_required": storage[
                "stored_dtype_reconciliation_required"
            ],
            "checkpoint_sha256": model["checkpoint_sha256"],
            "frame_map_schema_path": frame_map["schema_path"],
            "frame_map_schema_sha256": frame_map["schema_sha256"],
            "frame_map_schema_version": frame_map["schema_version"],
            "frame_token_map_path": token_map["path"],
            "frame_token_map_sha256": token_map["sha256"],
            "frame_token_map_version": token_map["version"],
            "hook_sites": hooks["hook_sites"],
            "layer_indices": hooks["layer_indices"],
            "model_config_sha256": model["model_config_sha256"],
            "model_identity": model["model_identity"],
            "preprocessing_config_path": preprocessing["config_path"],
            "preprocessing_config_sha256": preprocessing["config_file_sha256"],
            "preprocessing_implementation_path": preprocessing["implementation_path"],
            "preprocessing_implementation_sha256": preprocessing[
                "implementation_sha256"
            ],
            "preprocessing_unchanged_from_frozen_authority": preprocessing[
                "unchanged_from_frozen_accepted_authority"
            ],
            "vae_checkpoint_sha256": model["vae_checkpoint_sha256"],
            "vae_config_sha256": model["vae_config_sha256"],
            "vae_identity": model["vae_identity"],
            "visual_tokens_per_frame": token_map[
                "expected_visual_token_cardinality_per_frame"
            ],
        },
        "production_activation_bytes_created": False,
        "production_extraction_bytes_created": False,
        "registry_v2_acceptance_authorized": False,
        "schema_id": f"{SCHEMA_PREFIX}-owner-acknowledgement",
        "schema_version": SCHEMA_VERSION,
        "scientific_execution_performed": False,
        "scientific_settings_changed_by_this_package": False,
        "self_authorizes_phase6": False,
        "status": (
            "PERSON_A_66_CELL_INPUT_CONTRACT_ACKNOWLEDGED_"
            "AWAITING_BYTE_TRANSPORT_FRAME_MAPS_AND_AGGREGATE_AUTHORIZATION"
        ),
    }


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------
def _authority_binding(
    a_commit: str,
    verification: dict[str, Any],
    source_records: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "authorities": {
            "person_a": {
                "branch": A_BRANCH,
                "starting_commit": a_commit,
            },
            "person_c": {
                "branch": C_BRANCH,
                "branch_merged": False,
                "remote_ref": C_REMOTE_REF,
                "source_authority_commit": C_COMMIT,
                "source_read_policy": "exact_git_commit_object",
            },
        },
        "builder_path": BUILDER_PATH,
        "claims": {
            "aggregate_phase6_runtime_authorized": False,
            "gpu_extraction_started": False,
            "model_loaded": False,
            "person_a_66_activation_index_exists": False,
            "person_a_phase6_authorized": False,
            "production_activation_bytes_created": False,
            "production_extraction_bytes_created": False,
            "registry_v2_acceptance_authorized": False,
            "scientific_execution_performed": False,
            "self_authorizes_phase6": False,
        },
        "person_a_pinned_source_files": source_records,
        "person_c_source_records": [
            {
                "path": path,
                "sha256": digest,
                "source_commit": C_COMMIT,
                "source_read_policy": "exact_git_commit_object",
            }
            for path, digest in sorted(
                verification["source_document_hashes"].items()
            )
        ],
        "schema_id": f"{SCHEMA_PREFIX}-authority-binding",
        "schema_version": SCHEMA_VERSION,
        "test_path": TEST_PATH,
    }


def _validation_receipt(
    verification: dict[str, Any],
    authorities: dict[str, Any],
    universe: dict[str, Any],
    bytes_receipt: dict[str, Any],
    acknowledgement: dict[str, Any],
) -> dict[str, Any]:
    return {
        "aggregate_phase6_runtime_authorized": False,
        "c_commit_verified": True,
        "c_manifest_sha256_verified": verification["c_manifest_observed_sha256"]
        == C_ACCEPTED_MANIFEST_SHA256,
        "c_metadata_references_all_resolve": not verification[
            "c_metadata_references_unresolved"
        ],
        "c_package_hashes_all_resolve": not verification["c_package_hashes_unresolved"],
        "canonical_json_valid": True,
        "duplicate_or_missing_trajectory_identities": bool(
            verification["duplicate_trajectory_ids"]
            or verification["missing_episode_ids"]
        ),
        "episode_set_exact_12601_12666": verification["episode_set_exact"],
        "gpu_extraction_started": False,
        "model_loaded": False,
        "person_a_66_activation_index_exists": False,
        "person_a_consumer_receipt_present": verification["person_a_consumer_receipt"][
            "exists"
        ],
        "person_a_phase6_authorized": False,
        "person_a_pinned_authorities_unchanged": True,
        "preprocessing_unchanged_from_frozen_authority": authorities["preprocessing"][
            "unchanged_from_frozen_accepted_authority"
        ],
        "production_activation_bytes_created": False,
        "production_extraction_bytes_created": False,
        "real_frame_maps_materialized": universe["real_frame_maps_materialized"],
        "readiness": {
            "person_a_66_byte_access_ready": acknowledgement[
                "person_a_66_byte_access_ready"
            ],
            "person_a_66_extraction_ready": acknowledgement[
                "person_a_66_extraction_ready"
            ],
            "person_a_66_input_contract_ready": acknowledgement[
                "person_a_66_input_contract_ready"
            ],
            "person_a_phase6_acknowledgement_ready": acknowledgement[
                "person_a_phase6_acknowledgement_ready"
            ],
        },
        "registry_v2_acceptance_authorized": False,
        "schema_id": f"{SCHEMA_PREFIX}-validation-receipt",
        "schema_version": SCHEMA_VERSION,
        "scientific_execution_performed": False,
        "trajectory_count_hash_verified_on_local_host": bytes_receipt[
            "trajectory_count_hash_verified_on_local_host"
        ],
        "verification_violations": verification["verification_violations"],
    }


def _protected_false_violations(value: Any, path: str) -> list[str]:
    violations: list[str] = []
    if isinstance(value, dict):
        for key in sorted(value):
            child = value[key]
            child_path = f"{path}.{key}"
            if key in PROTECTED_FALSE_FIELDS and child is not False:
                violations.append(f"{child_path} must be exact Boolean false")
            violations.extend(_protected_false_violations(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(_protected_false_violations(child, f"{path}[{index}]"))
    return violations


def validate_package(documents: dict[str, Any]) -> tuple[str, ...]:
    violations: list[str] = []
    if set(documents) != set(OUTPUT_PATHS):
        violations.append("Package path inventory changed")
    for path, document in sorted(documents.items()):
        violations.extend(_protected_false_violations(document, path))

    verification = documents.get("c_intake_verification.json", {})
    if verification.get("verification_violations"):
        violations.append("Person C intake verification reported violations")
    if verification.get("observed_accepted_count") != EXPECTED_ACCEPTED_COUNT:
        violations.append("Accepted trajectory count is not 66")
    if verification.get("excluded_trajectory_count") != EXPECTED_EXCLUDED_COUNT:
        violations.append("Excluded trajectory count is not 0")
    if verification.get("c_branch_merged") is not False:
        violations.append("Person C branch must never be merged wholesale")

    universe = documents.get("expected_model_frame_universe.json", {})
    if universe.get("expected_trajectory_count") != EXPECTED_ACCEPTED_COUNT:
        violations.append("Expected trajectory count is not 66")
    if universe.get("expected_model_frame_key_universe_enumerated") is not False:
        violations.append("Model-frame key identities must not be fabricated")
    if universe.get("duplicate_trajectory_ids") or universe.get(
        "missing_trajectory_ids"
    ):
        violations.append("Expected universe has duplicate or missing trajectories")

    acknowledgement = documents.get("person_a_owner_acknowledgement.json", {})
    for field in (
        "person_a_66_byte_access_ready",
        "person_a_66_extraction_ready",
        "person_a_66_input_contract_ready",
        "person_a_phase6_acknowledgement_ready",
    ):
        if not isinstance(acknowledgement.get(field), bool):
            violations.append(f"{field} must be a Boolean readiness field")
    if acknowledgement.get("immutability", {}).get("no_overwrite") is not True:
        violations.append("Acknowledgement no-overwrite rule changed")
    if acknowledgement.get("scientific_settings_changed_by_this_package") is not False:
        violations.append("This package must not change scientific settings")
    return tuple(violations)


def build_documents(*, scan_bytes: bool = True) -> dict[str, Any]:
    a_commit = verify_authorities()
    source_records = verify_pinned_a_sources()
    verification, bundles = verify_c_package()
    authorities = production_authorities(source_records)
    universe = expected_model_frame_universe(bundles)
    bytes_receipt = byte_accessibility(bundles, scan=scan_bytes)
    acknowledgement = owner_acknowledgement(
        a_commit=a_commit,
        verification=verification,
        authorities=authorities,
        universe=universe,
        bytes_receipt=bytes_receipt,
    )
    documents: dict[str, Any] = {
        "authority_binding.json": _authority_binding(
            a_commit, verification, source_records
        ),
        "byte_accessibility_receipt.json": bytes_receipt,
        "c_intake_verification.json": verification,
        "expected_model_frame_universe.json": universe,
        "person_a_owner_acknowledgement.json": acknowledgement,
        "production_authorities.json": authorities,
        "validation_receipt.json": _validation_receipt(
            verification, authorities, universe, bytes_receipt, acknowledgement
        ),
    }
    documents["sha256_inventory.json"] = {
        "file_count": len(documents) + 1,
        "files": {
            path: _sha256(_json_bytes(document))
            for path, document in sorted(documents.items())
        },
        "inventory_excludes_self": True,
        "schema_id": f"{SCHEMA_PREFIX}-sha256-inventory",
        "schema_version": SCHEMA_VERSION,
    }
    violations = validate_package(documents)
    if violations:
        raise RuntimeError("; ".join(violations))
    return documents


def write_documents(output_root: Path, *, scan_bytes: bool = True) -> None:
    documents = build_documents(scan_bytes=scan_bytes)
    output_root.mkdir(parents=True, exist_ok=True)
    expected = {output_root / path for path in documents}
    existing = {path for path in output_root.rglob("*") if path.is_file()}
    if existing - expected:
        raise RuntimeError("Unexpected output paths exist")
    for path, document in sorted(documents.items()):
        (output_root / path).write_bytes(_json_bytes(document))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Person A's 66-cell intake and owner acknowledgement."
    )
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT)
    parser.add_argument(
        "--skip-byte-scan",
        action="store_true",
        help="Record byte accessibility as not scanned instead of reading payloads.",
    )
    arguments = parser.parse_args()
    write_documents(
        arguments.output_dir.resolve(),
        scan_bytes=not arguments.skip_byte_scan,
    )


if __name__ == "__main__":
    main()
