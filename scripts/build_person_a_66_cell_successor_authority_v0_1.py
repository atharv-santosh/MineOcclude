"""Publish Person A's final 66-cell pre-extraction successor authority.

This builder closes Person A's remaining local authority work before the real
66-cell activation run. It binds Person B's production oracle authorities and
Person C's strict visibility authority as exact Git objects, freezes Person A's
model and preprocessing authorities as distinct quantities, publishes the
additive float32 successor extraction contract under a new run identity, builds
the final 2468-key extraction queue, supersedes the stale owner acknowledgement,
publishes the Person A to Person D frame/preprocessing handoff, re-checks byte
transport, and records the Phase 6 precondition state.

It never loads model weights, never generates activations, never edits another
role's branch, and never authorizes Phase 6.
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
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from mineocclude.experiments.extraction_queue import (
    ExtractionQueue,
    build_queue_from_matrix,
)
from mineocclude.experiments.mvp_lineage import make_run_id

SCHEMA_VERSION = "1.0"
SCHEMA_PREFIX = "person-a-66-cell-successor-authority-v0.1"
BUILDER_PATH = "scripts/build_person_a_66_cell_successor_authority_v0_1.py"
TEST_PATH = "tests/models/test_person_a_66_cell_successor_authority_v0_1.py"
DECISION_DATE = "2026-08-07"

A_BRANCH = "role/person-a-model"
A_STARTING_AUTHORITY = "77e43bd1665671b9e23d6d6ef927ee4944611342"

STATUS_ROOT = ROOT / "docs" / "status" / "person_a_66_cell_successor_authority_v0_1"
STATUS_ROOT_REL = "docs/status/person_a_66_cell_successor_authority_v0_1"

# --------------------------------------------------------------------------
# Foreign authorities, read as exact Git objects and never merged
# --------------------------------------------------------------------------
B_COMMIT = "25e09cb605699cdcb00dec1fbb1726977bec55e0"
B_REMOTE_REF = "origin/role/person-b-analysis"
B_ROOT = "docs/status/person_b_66_cell_oracle_target_v0_1"
B_FOLD_MANIFEST_PATH = (
    "docs/status/person_b_66_cell_preactivation_v0_1/fold_manifest.json"
)
B_FOLD_MANIFEST_SHA256 = (
    "86739975882f4926c3398d5bfa21611daf06c579b3893809eb385e8dcd03001d"
)

C_COMMIT = "e908ead4a7ff5ab3ae310bb846969a7859fdb26b"
C_REMOTE_REF = "origin/role/person-c-data"
C_ROOT = "docs/status/person_c_66_cell_strict_visibility_v0_1"
C_ACCEPTED_MANIFEST_COMMIT = "a8bed8adf7e24ca7fe5b6b6afa3342da61434be3"
C_ACCEPTED_MANIFEST_PATH = (
    "docs/status/person_c_c7_mvp_handoff_v0_1/trajectories_mvp_manifest.json"
)
C_ACCEPTED_MANIFEST_SHA256 = (
    "96ba43e15bc024aeaef7c519fa4ece0a4afe0bb0e877501dffaca44fee927ff7"
)
C_VISIBILITY_JOIN_SHA256 = (
    "6fcfaba99feed706e7106d0f1d9b758700d920ee2001b3ca6f150320f09313b7"
)
C_EVENT_TABLE_SHA256 = (
    "fadc0fc4c2afab2b39b992979317d4576fa2618263c8b09e29ca6c215528bb49"
)

D_REMOTE_REF = "origin/role/person-d-baselines"
E_REMOTE_REF = "origin/role/person-e-operations"

# Values supplied to this task that did not survive independent verification.
# Both share only a 16-hex prefix with the real digest, which is the signature
# of an abbreviated hash completed from conversation rather than from bytes.
DISPUTED_SUPPLIED_HASHES = {
    f"{B_ROOT}/row_universe_receipt_v0_2.json": (
        "e897c31cda46e2db2b0e2a0b0e0d0ad4ba76d0a63a5f2c6ab8b1a91fcb50a55e"
    ),
    f"{B_ROOT}/b_to_a_successor_handoff.json": (
        "6ca406342b700cf3d1cb5e2d0f5c2ba86ab8b7d3b8b1e19bb0b5e0f60e9dbd7a"
    ),
}

B_SOURCES = (
    "oracle_target_manifest.json",
    "row_universe_receipt_v0_2.json",
    "b_to_a_successor_handoff.json",
    "person_a_identity_resolution.json",
    "sha256_inventory.json",
)
C_SOURCES = (
    "visibility_join.jsonl",
    "event_table.jsonl",
    "visibility_join_manifest.json",
    "c_to_b_oracle_handoff.json",
    "sha256_inventory.json",
)

# --------------------------------------------------------------------------
# Person A frozen production identity (verified, never taken from chat)
# --------------------------------------------------------------------------
A_CONFIG_PATH = "configs/experiments/mvp.yaml"
A_PREPROCESS_IMPLEMENTATION_PATH = (
    "src/mineocclude/models/_mineworld_adapter_wave2.py"
)
A_NONEXISTENT_IMPLEMENTATION_PATH = (
    "src/mineocclude/models/mineworld_adapter_wave2.py"
)
A_FRAME_MAP_SCHEMA_PATH = "src/mineocclude/contracts/trajectory.py"
A_FRAME_TOKEN_MAP_PATH = "src/mineocclude/contracts/activation.py"
A_HOOKS_PATH = "src/mineocclude/activations/hooks.py"
A_POOL_PATH = "src/mineocclude/activations/pool.py"
A_STORE_PATH = "src/mineocclude/activations/store_v2.py"

#: The exact Person A implementation files whose bytes determine extraction
#: behaviour. Their combined digest is the successor run's code identity, which
#: is stable across the commit that publishes it, unlike a commit hash.
SUCCESSOR_CODE_IDENTITY_FILES = (
    A_PREPROCESS_IMPLEMENTATION_PATH,
    A_FRAME_MAP_SCHEMA_PATH,
    A_FRAME_TOKEN_MAP_PATH,
    A_HOOKS_PATH,
    A_POOL_PATH,
    A_STORE_PATH,
    "src/mineocclude/models/mineworld_adapter.py",
    "src/mineocclude/models/_mineworld_adapter_wave3.py",
    "src/mineocclude/models/_mineworld_adapter_wave4.py",
)

A_FRAME_MAP_PACKAGE_REL = "data/handoff_a/person_a_66_cell_production_input_v0_1"
A_FRAME_MAP_PACKAGE_SHA256 = (
    "a473bf830ed31e49762d62bba97032e52f4967e52f9987ad10cd5879ed9bd004"
)
A_MATRIX_REPORT_PATH = (
    "docs/status/person_a_phase7_mvp_v0_1/step_7_2_matrix_report.json"
)
A_STALE_OWNER_ACK_PATH = (
    "docs/status/person_a_phase6_66_cell_intake_v0_1/"
    "person_a_owner_acknowledgement.json"
)
A_PRIOR_PREPARATION_RECEIPT_PATH = (
    "docs/status/person_a_66_cell_local_preparation_v0_1/preparation_receipt.json"
)
A_EXECUTION_HOST_CONTRACT_PATH = (
    "docs/status/person_a_phase6_sagemaker_runtime_addendum_v0_1"
    "/execution_host_contract.json"
)
A_BYTE_TRANSFER_PLAN_PATH = (
    "docs/status/person_a_66_cell_local_preparation_v0_1/byte_transfer_plan.json"
)
A_STORAGE_DTYPE_RECONCILIATION_PATH = (
    "docs/status/person_a_66_cell_local_preparation_v0_1/"
    "storage_dtype_reconciliation.json"
)

EXPECTED_TRAJECTORY_COUNT = 66
EXPECTED_MODEL_FRAME_KEY_COUNT = 2468
LAYER_COUNT = 20
VECTOR_WIDTH = 2048
EXTRACTION_SEED = 20260725
STORED_ACTIVATION_DTYPE = "float32"
ANALYSIS_ARITHMETIC_DTYPE = "float64"
HOOK_SITE = "decoder_layer_output_residual_stream"

# Person A's frozen preprocessing source contract.
FROZEN_SOURCE_RESOLUTION_HW = (360, 640)
MODEL_FACING_RESOLUTION_HW = (224, 384)
#: The C6A client frames materialised on the preparation host. Person C's own
#: capture package declares media 640x360 while recording this raw framebuffer.
OBSERVED_C6A_FRAMEBUFFER_HW = (1046, 1920)

OUTPUT_PATHS = (
    "a_to_d_frame_handoff.json",
    "authority_binding.json",
    "byte_transport_preflight.json",
    "model_preprocess_authority.json",
    "phase6_precondition_receipt.json",
    "sha256_inventory.json",
    "successor_extraction_config.json",
    "successor_extraction_queue_state.json",
    "successor_owner_acknowledgement.json",
    "validation_receipt.json",
)

PROTECTED_FALSE_FIELDS = frozenset(
    {
        "activations_generated",
        "aggregate_phase6_runtime_authorized",
        "destination_fabricated",
        "foreign_branch_merged",
        "gpu_extraction_started",
        "historical_evidence_rewritten",
        "model_loaded",
        "person_a_phase6_authorized",
        "phase6_runtime_infrastructure_ready",
        "restricted_to_person_b_admitted_rows",
        "sagemaker_byte_access_ready",
        "scientific_execution_performed",
        "self_authorizes_phase6",
        "value_accepted_from_conversation",
    }
)


class SuccessorAuthorityError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _fail(code: str, message: str) -> None:
    raise SuccessorAuthorityError(code, message)


# --------------------------------------------------------------------------
# Primitives
# --------------------------------------------------------------------------
def _completed(command: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(command, cwd=ROOT, check=False, capture_output=True)


def _git_text(*arguments: str) -> str:
    result = _completed(["git", *arguments])
    if result.returncode != 0:
        _fail("git_failed", result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout.decode("utf-8").strip()


def _git_bytes(commit: str, path: str) -> bytes:
    result = _completed(["git", "show", f"{commit}:{path}"])
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        _fail("git_object_missing", f"{commit}:{path}: {detail}")
    return result.stdout


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def repository_bytes(path: str) -> bytes:
    """Return a tracked text file's repository-canonical (LF) bytes."""

    return (ROOT / path).read_bytes().replace(b"\r\n", b"\n")


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return _sha256(_canonical_bytes(value))


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _source_record(commit: str, path: str) -> dict[str, Any]:
    raw = _git_bytes(commit, path)
    return {
        "byte_size": len(raw),
        "path": path,
        "sha256": _sha256(raw),
        "source_commit": commit,
        "source_read_policy": "exact_git_commit_object",
    }


def _local_record(path: str) -> dict[str, Any]:
    raw = repository_bytes(path)
    return {
        "byte_size": len(raw),
        "digest_scope": "repository_canonical_lf_bytes",
        "path": path,
        "sha256": _sha256(raw),
    }


# --------------------------------------------------------------------------
# Authority verification
# --------------------------------------------------------------------------
def verify_authorities() -> str:
    branch = _git_text("branch", "--show-current")
    if branch != A_BRANCH:
        _fail("unexpected_branch", f"Person A branch is {branch!r}")
    if (
        _completed(
            ["git", "merge-base", "--is-ancestor", A_STARTING_AUTHORITY, "HEAD"]
        ).returncode
        != 0
    ):
        _fail("authority_not_ancestor", A_STARTING_AUTHORITY)
    for commit, ref in ((B_COMMIT, B_REMOTE_REF), (C_COMMIT, C_REMOTE_REF)):
        if _completed(["git", "cat-file", "-e", f"{commit}^{{commit}}"]).returncode:
            _fail("missing_foreign_commit", commit)
        if _completed(
            ["git", "merge-base", "--is-ancestor", commit, ref]
        ).returncode:
            _fail("foreign_commit_not_remote", f"{commit} not reachable from {ref}")
    for commit, path, expected in (
        (C_ACCEPTED_MANIFEST_COMMIT, C_ACCEPTED_MANIFEST_PATH, C_ACCEPTED_MANIFEST_SHA256),
        (C_COMMIT, f"{C_ROOT}/visibility_join.jsonl", C_VISIBILITY_JOIN_SHA256),
        (C_COMMIT, f"{C_ROOT}/event_table.jsonl", C_EVENT_TABLE_SHA256),
        (B_COMMIT, B_FOLD_MANIFEST_PATH, B_FOLD_MANIFEST_SHA256),
    ):
        observed = _sha256(_git_bytes(commit, path))
        if observed != expected:
            _fail("authority_hash_mismatch", f"{path}: {observed} != {expected}")
    return A_STARTING_AUTHORITY


def verify_supplied_hashes() -> list[dict[str, Any]]:
    """Check every hash supplied to this task against the real Git object."""

    findings: list[dict[str, Any]] = []
    inventory = json.loads(_git_bytes(B_COMMIT, f"{B_ROOT}/sha256_inventory.json"))
    by_path = {row["path"]: row["sha256"] for row in inventory["files"]}
    for path, supplied in sorted(DISPUTED_SUPPLIED_HASHES.items()):
        actual = _sha256(_git_bytes(B_COMMIT, path))
        common = 0
        for left, right in zip(supplied, actual):
            if left != right:
                break
            common += 1
        findings.append(
            {
                "bound_value": actual,
                "common_prefix_hex_characters": common,
                "matches": supplied == actual,
                "path": path,
                "producer_inventory_sha256": by_path.get(path),
                "producer_inventory_confirms_bound_value": by_path.get(path) == actual,
                "supplied_value": supplied,
                "value_accepted_from_conversation": False,
            }
        )
    return findings


def verify_b_inventory() -> dict[str, Any]:
    inventory = json.loads(_git_bytes(B_COMMIT, f"{B_ROOT}/sha256_inventory.json"))
    mismatches = []
    for row in inventory["files"]:
        raw = _git_bytes(B_COMMIT, row["path"])
        if _sha256(raw) != row["sha256"] or len(raw) != row["byte_size"]:
            mismatches.append(row["path"])
    return {
        "declared_file_count": inventory["file_count"],
        "mismatched_paths": sorted(mismatches),
        "verified_file_count": len(inventory["files"]) - len(mismatches),
    }


# --------------------------------------------------------------------------
# Section 1 - model and preprocessing authority
# --------------------------------------------------------------------------
def model_preprocess_authority() -> dict[str, Any]:
    from mineocclude.experiments.mvp_config import load_mvp_config

    config = load_mvp_config(ROOT / A_CONFIG_PATH)
    identity = config.identity()
    implementation = _local_record(A_PREPROCESS_IMPLEMENTATION_PATH)
    checkpoint_sha256 = str(config.get("model.checkpoint_sha256"))

    tracked = set(
        _git_text("ls-tree", "-r", "--name-only", "HEAD", "--", "src/mineocclude/models")
        .splitlines()
    )
    if A_PREPROCESS_IMPLEMENTATION_PATH not in tracked:
        _fail("implementation_path_absent", A_PREPROCESS_IMPLEMENTATION_PATH)
    if A_NONEXISTENT_IMPLEMENTATION_PATH in tracked:
        _fail("unexpected_alias_path", A_NONEXISTENT_IMPLEMENTATION_PATH)

    if identity["model_hash"] != checkpoint_sha256:
        _fail("model_hash_not_checkpoint", identity["model_hash"])
    if identity["preprocess_hash"] == implementation["sha256"]:
        _fail(
            "collapsed_preprocess_fields",
            "preprocess_hash must not equal the implementation digest",
        )

    return {
        "action_converter": {
            "action_vocab_offset": 8192,
            "converter_identity": (
                "mineworld_action_compatibility@1.0:"
                "7e8d16db01f085481d41d340e5a0b84669b8e163f3338d5fd572731532c52746"
            ),
            "path": A_PREPROCESS_IMPLEMENTATION_PATH,
            "same_file_as_preprocessing_implementation": True,
            "sha256": implementation["sha256"],
            "symbol": "_OfficialActionConverter",
        },
        "distinct_quantities": {
            "collapsed_in_this_package": False,
            "model_hash_is_the_checkpoint_digest": True,
            "note": (
                "preprocess_hash is the canonical digest of the frozen "
                "preprocess: block of configs/experiments/mvp.yaml, computed by "
                "MvpConfig.preprocess_hash. It is NOT the digest of the file that "
                "implements preprocessing. The three quantities are recorded "
                "separately and none is derived from another."
            ),
            "preprocess_hash_is_the_config_block_digest": True,
            "preprocessing_implementation_sha256_is_a_file_digest": True,
        },
        "model": {
            "checkpoint_reference": (
                "https://www.modelscope.cn/models/MineWorld/"
                "0dd5561ab317115831badc50e09a6ebe98693d0e"
            ),
            "checkpoint_sha256": checkpoint_sha256,
            "decoder_layer_count": int(config.get("model.decoder_layer_count")),
            "model_class": str(config.get("model.model_class")),
            "model_config_sha256": str(config.get("model.config_sha256")),
            "model_hash": identity["model_hash"],
            "model_identity": str(config.get("model.name")),
            "precision": str(config.get("model.precision")),
            "source_revision": str(config.get("model.source_revision")),
            "transformer_class": str(config.get("model.transformer_class")),
            "vae_checkpoint_sha256": str(config.get("model.vae_checkpoint_sha256")),
            "vae_class": str(config.get("model.vae_class")),
            "vae_config_sha256": str(config.get("model.vae_config_sha256")),
        },
        "model_hash_equals_checkpoint_sha256": True,
        "model_hash_equality_contract": {
            "bound_because": (
                "Person A's own activation store and activation contract require "
                "the universal model_hash to equal the explicit checkpoint hash; "
                "the equality is defined by A-owned code, not asserted here."
            ),
            "evidence": [
                {
                    "path": A_STORE_PATH,
                    "rule": "model_hash must equal the frozen checkpoint hash",
                    "sha256": _local_record(A_STORE_PATH)["sha256"],
                    "symbol": "ActivationStoreV2Identity.__post_init__",
                },
                {
                    "path": A_FRAME_TOKEN_MAP_PATH,
                    "rule": (
                        "universal model_hash must agree with the explicit "
                        "checkpoint hash on every activation index row"
                    ),
                    "sha256": _local_record(A_FRAME_TOKEN_MAP_PATH)["sha256"],
                    "symbol": "activation index row validation",
                },
            ],
        },
        "preprocessing": {
            "color_convention": "source BGR decoded, converted to RGB (COLOR_BGR2RGB)",
            "config_file_sha256": identity["config_file_sha256"],
            "config_hash": identity["config_hash"],
            "config_path": A_CONFIG_PATH,
            "frozen_source_resolution_hw": list(FROZEN_SOURCE_RESOLUTION_HW),
            "function": "_preprocess_bgr_frame",
            "interpolation": str(config.get("preprocess.interpolation")),
            "model_facing_resolution_hw": list(MODEL_FACING_RESOLUTION_HW),
            "model_facing_tensor_layout": "CHW",
            "normalization": "(x - 0.5) / 0.5 per channel, float32, range [-1.0, 1.0]",
            "preprocess_hash": identity["preprocess_hash"],
            "preprocessing_identity": str(config.get("preprocess.identity")),
            "preprocessing_implementation_byte_size": implementation["byte_size"],
            "preprocessing_implementation_path": A_PREPROCESS_IMPLEMENTATION_PATH,
            "preprocessing_implementation_sha256": implementation["sha256"],
            "scaling": "uint8 divided by float32(255.0) after HWC to CHW transpose",
            "source_dtype": "uint8",
        },
        "resolved_implementation_path": {
            "absent_alias_path": A_NONEXISTENT_IMPLEMENTATION_PATH,
            "absent_alias_path_exists": False,
            "leading_underscore": True,
            "resolved_from": "git ls-tree at the Person A HEAD commit",
            "resolved_path": A_PREPROCESS_IMPLEMENTATION_PATH,
            "value_accepted_from_conversation": False,
        },
        "schema_id": f"{SCHEMA_PREFIX}-model-preprocess-authority",
        "schema_version": SCHEMA_VERSION,
    }


# --------------------------------------------------------------------------
# Section 2 - additive float32 successor extraction contract
# --------------------------------------------------------------------------
def successor_code_identity() -> dict[str, Any]:
    files = {
        path: _sha256(repository_bytes(path))
        for path in sorted(SUCCESSOR_CODE_IDENTITY_FILES)
    }
    return {
        "code_identity_sha256": _canonical_sha256(files),
        "digest_scope": "repository_canonical_lf_bytes",
        "files": files,
        "note": (
            "The successor run's code identity is the canonical digest of the "
            "exact Person A implementation files that determine extraction "
            "behaviour. It is stable across the commit that publishes this "
            "package, unlike a commit hash, and the runner must re-verify these "
            "digests before Step 6.1."
        ),
    }


def successor_extraction_config(
    authority: dict[str, Any], code_identity: dict[str, Any]
) -> dict[str, Any]:
    preprocessing = authority["preprocessing"]
    model = authority["model"]
    converter = authority["action_converter"]
    document: dict[str, Any] = {
        "additive_successor": True,
        "analysis_arithmetic_dtype": ANALYSIS_ARITHMETIC_DTYPE,
        "config_id": "person-a-66-cell-successor-float32-v0.1",
        "config_version": "0.1",
        "decision_date": DECISION_DATE,
        "dtype_review": {
            "analysis_arithmetic_dtype": ANALYSIS_ARITHMETIC_DTYPE,
            "coordinated_review_complete": True,
            "person_a_reconciliation_path": A_STORAGE_DTYPE_RECONCILIATION_PATH,
            "person_a_reconciliation_sha256": _local_record(
                A_STORAGE_DTYPE_RECONCILIATION_PATH
            )["sha256"],
            "person_b_approval_commit": B_COMMIT,
            "person_b_approval_path": f"{B_ROOT}/b_to_a_successor_handoff.json",
            "person_b_approval_sha256": _sha256(
                _git_bytes(B_COMMIT, f"{B_ROOT}/b_to_a_successor_handoff.json")
            ),
            "stored_activation_dtype": STORED_ACTIVATION_DTYPE,
        },
        "expected_activation_chunk_count": EXPECTED_TRAJECTORY_COUNT * LAYER_COUNT,
        "expected_activation_row_count": (
            EXPECTED_MODEL_FRAME_KEY_COUNT * LAYER_COUNT
        ),
        "expected_model_frame_key_count": EXPECTED_MODEL_FRAME_KEY_COUNT,
        "expected_trajectory_count": EXPECTED_TRAJECTORY_COUNT,
        "extraction": {
            "activation_index_key": [
                "trajectory_id",
                "model_frame_idx",
                "layer_idx",
                "hook_site",
            ],
            "chunk_layout": "one_chunk_per_decoder_layer",
            "extract_full_model_frame_universe": True,
            "hook_site": HOOK_SITE,
            "hook_implementation_path": A_HOOKS_PATH,
            "hook_implementation_sha256": _local_record(A_HOOKS_PATH)["sha256"],
            "layer_indices": list(range(LAYER_COUNT)),
            "mode": "teacher_forced",
            "pooling": "mean_over_visual_tokens",
            "pooling_identity": "person-a-visual-token-mean-v1.0",
            "pooling_implementation_path": A_POOL_PATH,
            "pooling_implementation_sha256": _local_record(A_POOL_PATH)["sha256"],
            "restricted_to_person_b_admitted_rows": False,
            "restriction_note": (
                "Person B's 662 admitted analysis rows are a post-extraction "
                "scientific subset. Extraction covers the full 2468-key "
                "production universe, as Person B's own successor handoff "
                "requires."
            ),
            "source_tensor_dtype": "float16",
            "stored_dtype": STORED_ACTIVATION_DTYPE,
            "vector_width": VECTOR_WIDTH,
        },
        "frame_token_map": {
            "action_tokens_per_frame": 11,
            "max_model_frames_per_context": 16,
            "path": A_FRAME_TOKEN_MAP_PATH,
            "sha256": _local_record(A_FRAME_TOKEN_MAP_PATH)["sha256"],
            "type": "mineocclude.contracts.activation.FrameTokenMap",
            "version": SCHEMA_VERSION,
            "visual_tokens_per_frame": 336,
        },
        "historical_evidence_rewritten": False,
        "inputs": {
            "person_a_frame_map_package_path": A_FRAME_MAP_PACKAGE_REL,
            "person_a_frame_map_package_sha256": A_FRAME_MAP_PACKAGE_SHA256,
            "person_b_fold_manifest_path": B_FOLD_MANIFEST_PATH,
            "person_b_fold_manifest_sha256": B_FOLD_MANIFEST_SHA256,
            "person_b_oracle_target_manifest_path": (
                f"{B_ROOT}/oracle_target_manifest.json"
            ),
            "person_b_oracle_target_manifest_sha256": _sha256(
                _git_bytes(B_COMMIT, f"{B_ROOT}/oracle_target_manifest.json")
            ),
            "person_b_row_universe_path": f"{B_ROOT}/row_universe_receipt_v0_2.json",
            "person_b_row_universe_sha256": _sha256(
                _git_bytes(B_COMMIT, f"{B_ROOT}/row_universe_receipt_v0_2.json")
            ),
            "person_b_source_commit": B_COMMIT,
            "person_c_accepted_manifest_commit": C_ACCEPTED_MANIFEST_COMMIT,
            "person_c_accepted_manifest_path": C_ACCEPTED_MANIFEST_PATH,
            "person_c_accepted_manifest_sha256": C_ACCEPTED_MANIFEST_SHA256,
            "person_c_event_table_path": f"{C_ROOT}/event_table.jsonl",
            "person_c_event_table_sha256": C_EVENT_TABLE_SHA256,
            "person_c_strict_visibility_commit": C_COMMIT,
            "person_c_visibility_join_path": f"{C_ROOT}/visibility_join.jsonl",
            "person_c_visibility_join_sha256": C_VISIBILITY_JOIN_SHA256,
        },
        "model": dict(model),
        "person_a_mvp_yaml_modified": False,
        "predecessor": {
            "path": A_CONFIG_PATH,
            "predecessor_evidence_rewritten": False,
            "predecessor_stored_dtype": "float16",
            "reason": (
                "configs/experiments/mvp.yaml is frozen historical evidence for "
                "the executed ten-pilot run. It is not edited in place; this "
                "successor config carries the reviewed float32 storage contract "
                "under a new run identity."
            ),
            "sha256": _local_record(A_CONFIG_PATH)["sha256"],
        },
        "preprocessing": {
            "action_converter_path": converter["path"],
            "action_converter_sha256": converter["sha256"],
            "action_vocab_offset": converter["action_vocab_offset"],
            "preprocess_hash": preprocessing["preprocess_hash"],
            "preprocessing_identity": preprocessing["preprocessing_identity"],
            "preprocessing_implementation_path": preprocessing[
                "preprocessing_implementation_path"
            ],
            "preprocessing_implementation_sha256": preprocessing[
                "preprocessing_implementation_sha256"
            ],
        },
        "producer_role": "person_a",
        "schema_id": f"{SCHEMA_PREFIX}-successor-extraction-config",
        "schema_version": SCHEMA_VERSION,
        "seed": EXTRACTION_SEED,
        "successor_code_identity": code_identity,
        "supersedes": {
            "path": A_CONFIG_PATH,
            "superseded_field": "extraction.stored_dtype",
            "superseded_value": "float16",
            "successor_value": STORED_ACTIVATION_DTYPE,
        },
    }
    # The config hash is taken over the document without its own identity
    # fields, so publishing the identity cannot change the identity.
    hashable = {k: v for k, v in document.items() if k != "successor_run_identity"}
    config_hash = _canonical_sha256(hashable)
    run_id = make_run_id(
        stage_id="model_extraction",
        config_hash=config_hash,
        code_sha=code_identity["code_identity_sha256"],
        seed=EXTRACTION_SEED,
    )
    document["successor_run_identity"] = {
        "accepted_manifest_sha256": C_ACCEPTED_MANIFEST_SHA256,
        "code_sha": code_identity["code_identity_sha256"],
        "config_hash": config_hash,
        "identity_inputs": [
            "stage_id",
            "config_hash",
            "code_sha",
            "seed",
        ],
        "run_id": run_id,
        "stage_id": "model_extraction",
    }
    return document


# --------------------------------------------------------------------------
# Section 3 - final 66-cell extraction queue
# --------------------------------------------------------------------------
def build_successor_queue(config: dict[str, Any]) -> ExtractionQueue:
    matrix = json.loads(repository_bytes(A_MATRIX_REPORT_PATH))
    index = json.loads(
        repository_bytes(f"{A_FRAME_MAP_PACKAGE_REL}/frame_map_index.json")
    )
    frame_counts = {
        trajectory_id: int(entry["model_frame_count"])
        for trajectory_id, entry in index["per_trajectory"].items()
    }
    if len(frame_counts) != EXPECTED_TRAJECTORY_COUNT:
        _fail("frame_count_cardinality", str(len(frame_counts)))
    if sum(frame_counts.values()) != EXPECTED_MODEL_FRAME_KEY_COUNT:
        _fail("frame_key_cardinality", str(sum(frame_counts.values())))
    identity = config["successor_run_identity"]
    queue = build_queue_from_matrix(
        matrix,
        run_id=identity["run_id"],
        config_hash=identity["config_hash"],
        code_sha=identity["code_sha"],
        accepted_manifest_sha256=identity["accepted_manifest_sha256"],
        layer_count=LAYER_COUNT,
        frame_counts=frame_counts,
        max_transient_retries=3,
    )
    if len(queue.items) != EXPECTED_TRAJECTORY_COUNT:
        _fail("queue_cardinality", str(len(queue.items)))
    rows = sum(item.expected.expected_row_count for item in queue.items.values())
    if rows != EXPECTED_MODEL_FRAME_KEY_COUNT * LAYER_COUNT:
        _fail("queue_row_cardinality", str(rows))
    for item in queue.items.values():
        if item.completion is not None:
            _fail("queue_preseeded_completion", item.item_id)
    return queue


# --------------------------------------------------------------------------
# Section 5 - Person A to Person D frame and preprocessing handoff
# --------------------------------------------------------------------------
def a_to_d_frame_handoff(authority: dict[str, Any]) -> dict[str, Any]:
    index = json.loads(
        repository_bytes(f"{A_FRAME_MAP_PACKAGE_REL}/frame_map_index.json")
    )
    preprocessing = authority["preprocessing"]
    blocker = {
        "blocker_id": "C-66-CELL-640x360-MEDIA-MISSING",
        "detail": (
            "Person A's frozen preprocessing requires a "
            f"{FROZEN_SOURCE_RESOLUTION_HW[0]}x{FROZEN_SOURCE_RESOLUTION_HW[1]} "
            "BGR uint8 source and _preprocess_bgr_frame rejects any other shape. "
            "Person C's capture package for the 66 cells declares media "
            "width 640 / height 360, but the only materialised pixels are the "
            f"{OBSERVED_C6A_FRAMEBUFFER_HW[1]}x{OBSERVED_C6A_FRAMEBUFFER_HW[0]} "
            "raw client framebuffer PNGs, and no 640x360 derivative exists in "
            "the repository or on the preparation host for any ep126xx episode. "
            "The two aspect ratios differ (1.836 versus 1.778), so any downscale "
            "is a scientific choice about cropping or letterboxing. Person A does "
            "not invent one."
        ),
        "owner": "person_c_data",
        "blocks_person_a_activation_extraction": True,
        "blocks_person_d_raw_pixel_baseline": True,
        "blocks_scope_note": (
            "The same pinned preprocessing produces Person A's model input and "
            "Person D's raw-pixel features, so this gap blocks the activation "
            "run itself, not only the Person D baseline."
        ),
        "resolution_options": [
            (
                "Person C publishes the declared 640x360 media derivative for "
                "all 66 episodes, as already exists for the earlier ep94xx and "
                "ep100xx pilots (video_640x360.mp4)"
            ),
            (
                "a coordinated result-changing decision redefines Person A's "
                "frozen preprocessing source resolution and the exact downscale "
                "rule"
            ),
        ],
    }
    return {
        "applicability": {
            "all_66_cells_applicable": True,
            "excluded_trajectory_count": 0,
            "trajectory_count": EXPECTED_TRAJECTORY_COUNT,
        },
        "blocking_findings": [blocker],
        "canonicalization_rules": {
            "frame_map_row_encoding": (
                "canonical JSON, sorted keys, ASCII, compact separators, one row "
                "per line"
            ),
            "key_defines_identity": True,
            "model_facing_frame_identity": ["trajectory_id", "model_frame_idx"],
            "row_order_defines_identity": False,
        },
        "consumer_role": "person_d",
        "decision_date": DECISION_DATE,
        "deterministic_entry_point": {
            "frame_manifest_argument": (
                "--frame-manifest <A_66_CELL_FRAME_MANIFEST>  # unavailable until "
                "the blocking finding is resolved"
            ),
            "person_a_regeneration_command": (
                "python scripts/build_person_a_66_cell_local_preparation_v0_1.py "
                "frame-maps"
            ),
            "person_d_production_command": (
                "python scripts/run_person_d_step4_1_eight_family_production.py "
                "--fold-manifest <B_66_CELL_FOLD_MANIFEST> --oracle-targets "
                "<B_66_CELL_ORACLE_TARGETS> --frame-manifest "
                "<A_66_CELL_FRAME_MANIFEST> --output-root <PERSON_D_PRODUCTION_ROOT> "
                "--resume auto"
            ),
        },
        "frame_map": {
            "index_path": f"{A_FRAME_MAP_PACKAGE_REL}/frame_map_index.json",
            "index_sha256": _local_record(
                f"{A_FRAME_MAP_PACKAGE_REL}/frame_map_index.json"
            )["sha256"],
            "model_frame_key_count": index["model_frame_key_count"],
            "package_path": A_FRAME_MAP_PACKAGE_REL,
            "package_sha256": A_FRAME_MAP_PACKAGE_SHA256,
            "per_trajectory": {
                trajectory_id: {
                    "frame_map_path": (
                        f"{A_FRAME_MAP_PACKAGE_REL}/{entry['frame_map_path']}"
                    ),
                    "frame_map_sha256": entry["frame_map_sha256"],
                    "model_frame_count": entry["model_frame_count"],
                }
                for trajectory_id, entry in sorted(index["per_trajectory"].items())
            },
            "source_frame_reference_fields": [
                "source_frame_role",
                "source_frame_runtime_path",
                "source_frame_sha256",
                "source_frame_byte_size",
            ],
            "source_frame_hashes_present": True,
            "trajectory_count": index["trajectory_count"],
        },
        "person_c_accepted_manifest": {
            "commit": C_ACCEPTED_MANIFEST_COMMIT,
            "path": C_ACCEPTED_MANIFEST_PATH,
            "sha256": C_ACCEPTED_MANIFEST_SHA256,
        },
        "preprocessed_frame_artifact": {
            "artifact_id_rule": (
                "person-a-66-cell-preprocessed-frame-v0-2::{trajectory_id}::"
                "{model_frame_idx}"
            ),
            "expected_payload_byte_size": 3 * 224 * 384 * 4,
            "expected_record_count": EXPECTED_MODEL_FRAME_KEY_COUNT,
            "materialized": False,
            "materialization_blocked_by": blocker["blocker_id"],
            "payload_color_order": "RGB",
            "payload_dtype": "float32",
            "payload_format": "raw-little-endian-float32-c-order",
            "payload_layout": "CHW",
            "payload_shape": [3, 224, 384],
            "required_manifest_schema": "person-a-preprocessed-frame-manifest-v0.2",
            "required_record_fields": [
                "artifact_id",
                "trajectory_id",
                "model_frame_idx",
                "payload_sha256",
                "payload_byte_size",
                "preprocess_hash",
                "fold_binding",
            ],
        },
        "preprocessing_authority": {
            "color_convention": preprocessing["color_convention"],
            "config_path": preprocessing["config_path"],
            "config_sha256": preprocessing["config_file_sha256"],
            "frozen_source_resolution_hw": preprocessing[
                "frozen_source_resolution_hw"
            ],
            "interpolation": preprocessing["interpolation"],
            "model_facing_resolution_hw": preprocessing[
                "model_facing_resolution_hw"
            ],
            "model_facing_tensor_layout": preprocessing[
                "model_facing_tensor_layout"
            ],
            "normalization": preprocessing["normalization"],
            "observed_c6a_framebuffer_hw": list(OBSERVED_C6A_FRAMEBUFFER_HW),
            "operations_in_order": [
                "decode the exact source frame as BGR uint8",
                "require source shape (360, 640, 3), dtype uint8, C-contiguous",
                "convert BGR to RGB with cv2.cvtColor(COLOR_BGR2RGB)",
                "resize to width 384 and height 224 with cv2.INTER_LINEAR",
                "transpose HWC to CHW",
                "cast to float32 and divide by float32(255.0)",
                "normalize with (tensor - float32(0.5)) / float32(0.5)",
                "serialize as little-endian float32 C-order bytes",
            ],
            "preprocess_hash": preprocessing["preprocess_hash"],
            "preprocessing_identity": preprocessing["preprocessing_identity"],
            "preprocessing_implementation_path": preprocessing[
                "preprocessing_implementation_path"
            ],
            "preprocessing_implementation_sha256": preprocessing[
                "preprocessing_implementation_sha256"
            ],
            "scaling": preprocessing["scaling"],
            "source_dtype": preprocessing["source_dtype"],
        },
        "person_d_consumer_note": {
            "person_d_frozen_module": "src/mineocclude/baselines/frame_handoff_v0_2.py",
            "person_d_must_repin_constants": [
                "PERSON_A_FRAME_HANDOFF_COMMIT",
                "PERSON_A_FRAME_MANIFEST_PATH",
                "PERSON_A_FRAME_MANIFEST_SHA256",
                "PERSON_A_EXTERNAL_FRAME_ROOT",
                "REQUIRED_FRAME_ARTIFACT_COUNT",
                "FROZEN_PILOT_IDS",
            ],
            "person_d_module_is_pinned_to_ten_pilot_scope": True,
            "person_d_owns_this_change": True,
            "reason": (
                "Person D's frozen validator requires exactly 1695 records over "
                "ten ep94xx pilots and rejects any other trajectory. Person A "
                "does not modify Person D's branch or module."
            ),
        },
        "producer_role": "person_a",
        "ready": False,
        "schema_id": f"{SCHEMA_PREFIX}-a-to-d-frame-handoff",
        "schema_version": SCHEMA_VERSION,
    }


# --------------------------------------------------------------------------
# Section 6 - byte transport preflight
# --------------------------------------------------------------------------
def byte_transport_preflight() -> dict[str, Any]:
    prior = json.loads(repository_bytes(A_BYTE_TRANSFER_PLAN_PATH))
    host = json.loads(repository_bytes(A_EXECUTION_HOST_CONTRACT_PATH))
    searched = []
    found: list[str] = []
    # Require at least one bucket character after the scheme. A bare "s3://"
    # token is the approved-scheme vocabulary, not an assigned destination.
    destination_pattern = "s3://[A-Za-z0-9]"
    for ref in (B_REMOTE_REF, C_REMOTE_REF, D_REMOTE_REF, E_REMOTE_REF, "HEAD"):
        result = _completed(
            [
                "git",
                "grep",
                "-lIE",
                destination_pattern,
                ref,
                "--",
                "docs",
                "configs",
                "scripts",
            ]
        )
        hits = [
            line
            for line in result.stdout.decode("utf-8", errors="replace").splitlines()
            if line.strip()
        ]
        searched.append({"hits": hits, "ref": ref})
        found.extend(hits)
    return {
        "approved_durable_destination": None,
        "byte_transport_destination_pending": True,
        "destination_fabricated": False,
        "execution_environment": host["execution_boundary"][
            "allowed_production_environment"
        ],
        "executable_transfer_procedure": {
            "credential_rule": (
                "credentials travel only through the approved out-of-band "
                "channel and never appear in Git, a log, an object, or a receipt"
            ),
            "steps": [
                (
                    "1. an owner assigns <APPROVED_DESTINATION_URI> and records "
                    "it in docs/status/person_a_phase9_clean_run_v0_1/"
                    "external_artifact_index.json"
                ),
                (
                    "2. python "
                    "scripts/build_person_a_66_cell_local_preparation_v0_1.py "
                    "frame-maps  # re-verify all 2930 source artifacts"
                ),
                (
                    "3. upload each artifact from its exact windows_source_path "
                    f"in {A_FRAME_MAP_PACKAGE_REL}/source_byte_inventory.json to "
                    "<APPROVED_DESTINATION_URI>/person-c-c6a-post-c1-v0.1/"
                    "episode_<episode_id>/<side>/<artifact_role>"
                ),
                (
                    "4. recompute SHA-256 for every uploaded object and require "
                    "an exact match against source_byte_inventory.json"
                ),
                (
                    "5. materialize on aws_sagemaker_linux_gpu and re-verify "
                    "every digest and byte size before Step 6.1"
                ),
            ],
            "unfilled_placeholders": ["<APPROVED_DESTINATION_URI>"],
        },
        "prior_plan_path": A_BYTE_TRANSFER_PLAN_PATH,
        "prior_plan_sha256": _local_record(A_BYTE_TRANSFER_PLAN_PATH)["sha256"],
        "reinspection": {
            "bare_scheme_token_is_not_a_destination": True,
            "destination_pattern": destination_pattern,
            "object_store_destination_found": bool(found),
            "refs_searched": [entry["ref"] for entry in searched],
            "results": searched,
            "roles_reinspected": ["person_b", "person_c", "person_d", "person_e"],
        },
        "sagemaker_byte_access_ready": False,
        "schema_id": f"{SCHEMA_PREFIX}-byte-transport-preflight",
        "schema_version": SCHEMA_VERSION,
        "windows_byte_state": {
            "artifact_count": prior["expected_byte_inventory"]["artifact_count"],
            "artifact_hash_verified_count": prior["expected_byte_inventory"][
                "artifact_hash_verified_count"
            ],
            "byte_size_total": prior["expected_byte_inventory"]["byte_size_total"],
            "trajectory_count": prior["expected_byte_inventory"]["trajectory_count"],
            "trajectory_hash_verified_count": prior["expected_byte_inventory"][
                "trajectory_count"
            ],
        },
    }


# --------------------------------------------------------------------------
# Section 7 - Phase 6 precondition assessment
# --------------------------------------------------------------------------
def phase6_precondition_receipt(
    config: dict[str, Any],
    handoff: dict[str, Any],
    transport: dict[str, Any],
) -> dict[str, Any]:
    contract_conditions = [
        {
            "condition": "person_c_accepted_66_cell_manifest_bound",
            "owner": "person_c_data",
            "satisfied": True,
        },
        {
            "condition": "person_c_strict_visibility_authority_bound",
            "owner": "person_c_data",
            "satisfied": True,
        },
        {
            "condition": "person_a_2468_key_frame_map_materialized",
            "owner": "person_a_model",
            "satisfied": True,
        },
        {
            "condition": "person_b_fold_and_oracle_target_authorities_bound",
            "owner": "person_b_analysis",
            "satisfied": True,
        },
        {
            "condition": "person_b_row_universe_bound",
            "owner": "person_b_analysis",
            "satisfied": True,
        },
        {
            "condition": "storage_dtype_review_complete_float32",
            "owner": "person_a_model+person_b_analysis",
            "satisfied": True,
        },
        {
            "condition": "model_preprocess_converter_identities_hash_bound",
            "owner": "person_a_model",
            "satisfied": True,
        },
        {
            "condition": "successor_run_identity_established",
            "owner": "person_a_model",
            "satisfied": True,
        },
        {
            "condition": "model_input_source_media_at_frozen_source_resolution",
            "detail": (
                f"{handoff['blocking_findings'][0]['blocker_id']}: the frozen "
                "preprocessing that produces the model input requires a "
                "640x360 source and only the 1920x1046 raw client framebuffer "
                "exists for the 66 cells. This blocks Person A's own activation "
                "extraction, not only Person D's raw-pixel baseline, because "
                "both consume the same pinned preprocessing."
            ),
            "owner": "person_c_data",
            "satisfied": False,
        },
        {
            "condition": "person_d_66_cell_frame_preprocess_handoff_consumable",
            "detail": handoff["blocking_findings"][0]["blocker_id"],
            "owner": "person_c_data",
            "satisfied": False,
        },
    ]
    infrastructure_conditions = [
        {
            "condition": "durable_byte_transport_to_approved_gpu_environment",
            "owner": "person_c_data",
            "satisfied": False,
        },
        {
            "condition": "approved_gpu_runtime_session",
            "owner": "person_a_model",
            "satisfied": False,
        },
        {
            "condition": "model_and_vae_checkpoint_accessible_in_that_environment",
            "owner": "person_a_model",
            "satisfied": False,
        },
    ]
    contract_ready = all(entry["satisfied"] for entry in contract_conditions)
    infrastructure_ready = all(
        entry["satisfied"] for entry in infrastructure_conditions
    )
    return {
        "aggregate_phase6_runtime_authorized": False,
        "aggregate_authorization_authority_present": False,
        "aggregate_authorization_requirement": {
            "person_b_conditions_path": (
                "docs/status/person_b_phase4_step4_1_registry_v2_handoff_v0_1/"
                "phase6_authorization_conditions.json"
            ),
            "required_signers": [
                "person_a_model",
                "person_b_analysis",
                "person_c_data",
                "person_e_operations",
            ],
            "rule": (
                "Person B's frozen conditions require a new explicit versioned "
                "authorization decision signed by the required owners; silent "
                "authorization is forbidden and no automatic transition exists."
            ),
            "silent_authorization_forbidden": True,
        },
        "assessed_roles": {
            "person_a": {"commit": A_STARTING_AUTHORITY, "ref": "HEAD"},
            "person_b": {"commit": B_COMMIT, "ref": B_REMOTE_REF},
            "person_c": {"commit": C_COMMIT, "ref": C_REMOTE_REF},
            "person_d": {
                "commit": _git_text("rev-parse", D_REMOTE_REF),
                "ref": D_REMOTE_REF,
            },
            "person_e": {
                "commit": _git_text("rev-parse", E_REMOTE_REF),
                "ref": E_REMOTE_REF,
            },
        },
        "contract_conditions": contract_conditions,
        "infrastructure_conditions": infrastructure_conditions,
        "phase6_contract_preconditions_ready": contract_ready,
        "phase6_runtime_infrastructure_ready": infrastructure_ready,
        "schema_id": f"{SCHEMA_PREFIX}-phase6-precondition-receipt",
        "schema_version": SCHEMA_VERSION,
        "self_authorizes_phase6": False,
        "successor_run_id": config["successor_run_identity"]["run_id"],
        "transport_state": {
            "byte_transport_destination_pending": transport[
                "byte_transport_destination_pending"
            ],
            "sagemaker_byte_access_ready": transport["sagemaker_byte_access_ready"],
        },
    }


# --------------------------------------------------------------------------
# Section 4 - additive successor owner acknowledgement
# --------------------------------------------------------------------------
def successor_owner_acknowledgement(
    *,
    a_commit: str,
    authority: dict[str, Any],
    config: dict[str, Any],
    queue: ExtractionQueue,
    handoff: dict[str, Any],
    transport: dict[str, Any],
    preconditions: dict[str, Any],
) -> dict[str, Any]:
    stale = _local_record(A_STALE_OWNER_ACK_PATH)
    stale_document = json.loads(repository_bytes(A_STALE_OWNER_ACK_PATH))
    identity = config["successor_run_identity"]
    return {
        "acknowledgement_id": "person-a-66-cell-successor-acknowledgement-v0-1",
        "aggregate_phase6_runtime_authorized": False,
        "byte_state": {
            "gpu_environment": transport["execution_environment"],
            "sagemaker_byte_access_ready": transport["sagemaker_byte_access_ready"],
            "windows_artifact_hash_verified_count": transport["windows_byte_state"][
                "artifact_hash_verified_count"
            ],
            "windows_trajectory_count": transport["windows_byte_state"][
                "trajectory_count"
            ],
            "windows_trajectory_hash_verified_count": transport["windows_byte_state"][
                "trajectory_hash_verified_count"
            ],
        },
        "decision_date": DECISION_DATE,
        "extraction_authorization_status": {
            "activations_generated": False,
            "gpu_extraction_started": False,
            "model_loaded": False,
            "person_a_66_extraction_ready": False,
            "person_a_phase6_authorized": False,
            "phase6_contract_preconditions_ready": preconditions[
                "phase6_contract_preconditions_ready"
            ],
            "phase6_runtime_infrastructure_ready": preconditions[
                "phase6_runtime_infrastructure_ready"
            ],
            "self_authorizes_phase6": False,
        },
        "foreign_branch_merged": False,
        "frame_maps": {
            "duplicate_model_frame_key_count": 0,
            "missing_trajectory_count": 0,
            "model_facing_key": ["trajectory_id", "model_frame_idx"],
            "model_frame_key_count": EXPECTED_MODEL_FRAME_KEY_COUNT,
            "package_path": A_FRAME_MAP_PACKAGE_REL,
            "package_sha256": A_FRAME_MAP_PACKAGE_SHA256,
            "real_frame_maps_materialized": True,
            "trajectory_count": EXPECTED_TRAJECTORY_COUNT,
        },
        "historical_evidence_rewritten": False,
        "model_preprocess_authority": {
            "action_converter_path": authority["action_converter"]["path"],
            "action_converter_sha256": authority["action_converter"]["sha256"],
            "checkpoint_sha256": authority["model"]["checkpoint_sha256"],
            "model_hash": authority["model"]["model_hash"],
            "model_hash_equals_checkpoint_sha256": True,
            "preprocess_hash": authority["preprocessing"]["preprocess_hash"],
            "preprocessing_implementation_path": authority["preprocessing"][
                "preprocessing_implementation_path"
            ],
            "preprocessing_implementation_sha256": authority["preprocessing"][
                "preprocessing_implementation_sha256"
            ],
            "three_fields_are_distinct": True,
        },
        "owner": "person_a",
        "person_a_branch": A_BRANCH,
        "person_a_commit": a_commit,
        "person_a_to_person_d_handoff": {
            "blocking_finding": handoff["blocking_findings"][0]["blocker_id"],
            "path": f"{STATUS_ROOT_REL}/a_to_d_frame_handoff.json",
            "ready": handoff["ready"],
        },
        "person_b_authorities": {
            "commit": B_COMMIT,
            "fold_manifest_sha256": B_FOLD_MANIFEST_SHA256,
            "oracle_target_manifest_sha256": config["inputs"][
                "person_b_oracle_target_manifest_sha256"
            ],
            "row_universe_sha256": config["inputs"]["person_b_row_universe_sha256"],
            "successor_handoff_sha256": config["dtype_review"][
                "person_b_approval_sha256"
            ],
        },
        "person_c_authorities": {
            "accepted_manifest_sha256": C_ACCEPTED_MANIFEST_SHA256,
            "accepted_trajectory_count": EXPECTED_TRAJECTORY_COUNT,
            "event_table_sha256": C_EVENT_TABLE_SHA256,
            "excluded_trajectory_count": 0,
            "strict_visibility_commit": C_COMMIT,
            "visibility_join_sha256": C_VISIBILITY_JOIN_SHA256,
        },
        "producer_role": "person_a",
        "schema_id": f"{SCHEMA_PREFIX}-successor-owner-acknowledgement",
        "schema_version": SCHEMA_VERSION,
        "status": (
            "SUCCESSOR_AUTHORITY_PUBLISHED_AWAITING_BYTE_TRANSPORT_"
            "GPU_RUNTIME_AND_AGGREGATE_AUTHORIZATION"
        ),
        "storage_contract": {
            "analysis_arithmetic_dtype": ANALYSIS_ARITHMETIC_DTYPE,
            "person_b_approval_commit": B_COMMIT,
            "stored_activation_dtype": STORED_ACTIVATION_DTYPE,
        },
        "successor_queue": {
            "expected_activation_row_count": EXPECTED_MODEL_FRAME_KEY_COUNT
            * LAYER_COUNT,
            "expected_chunk_count": EXPECTED_TRAJECTORY_COUNT * LAYER_COUNT,
            "layer_count": LAYER_COUNT,
            "run_id": identity["run_id"],
            "trajectory_count": len(queue.items),
        },
        "supersedes": {
            "path": A_STALE_OWNER_ACK_PATH,
            "predecessor_evidence_rewritten": False,
            "predecessor_real_frame_maps_materialized": stale_document[
                "expected_model_frame_universe"
            ]["real_frame_maps_materialized"],
            "predecessor_sha256": stale["sha256"],
            "reason": (
                "The predecessor acknowledgement recorded "
                "real_frame_maps_materialized=false, which was true when it was "
                "written and is now stale. It is superseded additively and never "
                "rewritten."
            ),
            "supersession_is_additive": True,
        },
    }


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------
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
        for offset, child in enumerate(value):
            violations.extend(_protected_false_violations(child, f"{path}[{offset}]"))
    return violations


def _authority_binding(
    a_commit: str, supplied: list[dict[str, Any]], inventory: dict[str, Any]
) -> dict[str, Any]:
    return {
        "authorities": {
            "person_a": {"branch": A_BRANCH, "starting_commit": a_commit},
            "person_b": {
                "branch": "role/person-b-analysis",
                "remote_ref": B_REMOTE_REF,
                "source_authority_commit": B_COMMIT,
                "source_read_policy": "exact_git_commit_object",
            },
            "person_c": {
                "branch": "role/person-c-data",
                "remote_ref": C_REMOTE_REF,
                "source_authority_commit": C_COMMIT,
                "source_read_policy": "exact_git_commit_object",
            },
            "person_d": {
                "branch": "role/person-d-baselines",
                "remote_ref": D_REMOTE_REF,
                "source_authority_commit": _git_text("rev-parse", D_REMOTE_REF),
                "source_read_policy": "exact_git_commit_object",
            },
            "person_e": {
                "branch": "role/person-e-operations",
                "remote_ref": E_REMOTE_REF,
                "source_authority_commit": _git_text("rev-parse", E_REMOTE_REF),
                "source_read_policy": "exact_git_commit_object",
            },
        },
        "builder_path": BUILDER_PATH,
        "claims": {
            "activations_generated": False,
            "aggregate_phase6_runtime_authorized": False,
            "foreign_branch_merged": False,
            "gpu_extraction_started": False,
            "historical_evidence_rewritten": False,
            "model_loaded": False,
            "person_a_phase6_authorized": False,
            "scientific_execution_performed": False,
            "self_authorizes_phase6": False,
        },
        "person_b_package_inventory_verification": inventory,
        "person_b_source_records": [
            _source_record(B_COMMIT, f"{B_ROOT}/{name}") for name in sorted(B_SOURCES)
        ]
        + [_source_record(B_COMMIT, B_FOLD_MANIFEST_PATH)],
        "person_c_source_records": [
            _source_record(C_COMMIT, f"{C_ROOT}/{name}") for name in sorted(C_SOURCES)
        ]
        + [_source_record(C_ACCEPTED_MANIFEST_COMMIT, C_ACCEPTED_MANIFEST_PATH)],
        "schema_id": f"{SCHEMA_PREFIX}-authority-binding",
        "schema_version": SCHEMA_VERSION,
        "supplied_hash_verification": {
            "all_supplied_hashes_matched": all(
                entry["matches"] for entry in supplied
            ),
            "findings": supplied,
            "policy": (
                "Every hash supplied to this task was recomputed from the exact "
                "Git object. Where a supplied value disagreed, the recomputed "
                "value was bound and the supplied value was recorded as rejected. "
                "No value was accepted from conversation."
            ),
            "rejected_count": sum(1 for entry in supplied if not entry["matches"]),
        },
        "test_path": TEST_PATH,
    }


def _validation_receipt(
    config: dict[str, Any],
    queue: ExtractionQueue,
    preconditions: dict[str, Any],
    supplied: list[dict[str, Any]],
) -> dict[str, Any]:
    states: dict[str, int] = {}
    for item in queue.items.values():
        states[item.state.value] = states.get(item.state.value, 0) + 1
    return {
        "aggregate_phase6_runtime_authorized": False,
        "canonical_json_valid": True,
        "foreign_branch_merged": False,
        "gpu_extraction_started": False,
        "historical_evidence_rewritten": False,
        "model_loaded": False,
        "person_b_authorities_verified": True,
        "person_c_authorities_verified": True,
        "phase6_contract_preconditions_ready": preconditions[
            "phase6_contract_preconditions_ready"
        ],
        "phase6_runtime_infrastructure_ready": preconditions[
            "phase6_runtime_infrastructure_ready"
        ],
        "queue_expected_activation_row_count": sum(
            item.expected.expected_row_count for item in queue.items.values()
        ),
        "queue_layer_count": LAYER_COUNT,
        "queue_model_frame_key_count": sum(
            item.expected.frame_count for item in queue.items.values()
        ),
        "queue_states": dict(sorted(states.items())),
        "queue_trajectory_count": len(queue.items),
        "schema_id": f"{SCHEMA_PREFIX}-validation-receipt",
        "schema_version": SCHEMA_VERSION,
        "scientific_execution_performed": False,
        "stored_activation_dtype": STORED_ACTIVATION_DTYPE,
        "successor_run_id": config["successor_run_identity"]["run_id"],
        "supplied_hash_rejected_count": sum(
            1 for entry in supplied if not entry["matches"]
        ),
    }


def build_documents() -> dict[str, Any]:
    a_commit = verify_authorities()
    supplied = verify_supplied_hashes()
    inventory = verify_b_inventory()
    authority = model_preprocess_authority()
    code_identity = successor_code_identity()
    config = successor_extraction_config(authority, code_identity)
    queue = build_successor_queue(config)
    handoff = a_to_d_frame_handoff(authority)
    transport = byte_transport_preflight()
    preconditions = phase6_precondition_receipt(config, handoff, transport)
    acknowledgement = successor_owner_acknowledgement(
        a_commit=a_commit,
        authority=authority,
        config=config,
        queue=queue,
        handoff=handoff,
        transport=transport,
        preconditions=preconditions,
    )
    documents: dict[str, Any] = {
        "a_to_d_frame_handoff.json": handoff,
        "authority_binding.json": _authority_binding(a_commit, supplied, inventory),
        "byte_transport_preflight.json": transport,
        "model_preprocess_authority.json": authority,
        "phase6_precondition_receipt.json": preconditions,
        "successor_extraction_config.json": config,
        "successor_extraction_queue_state.json": queue.to_document(),
        "successor_owner_acknowledgement.json": acknowledgement,
        "validation_receipt.json": _validation_receipt(
            config, queue, preconditions, supplied
        ),
    }
    violations: list[str] = []
    for name, document in sorted(documents.items()):
        violations.extend(_protected_false_violations(document, name))
    if violations:
        _fail("protected_claim_violation", "; ".join(violations))
    documents["sha256_inventory.json"] = {
        "file_count": len(documents) + 1,
        "files": {
            name: _sha256(_json_bytes(document))
            for name, document in sorted(documents.items())
        },
        "inventory_excludes_self": True,
        "schema_id": f"{SCHEMA_PREFIX}-sha256-inventory",
        "schema_version": SCHEMA_VERSION,
    }
    if set(documents) != set(OUTPUT_PATHS):
        _fail("path_inventory_changed", str(sorted(documents)))
    return documents


def write_documents(output_root: Path) -> dict[str, Any]:
    documents = build_documents()
    output_root.mkdir(parents=True, exist_ok=True)
    for name, document in sorted(documents.items()):
        (output_root / name).write_bytes(_json_bytes(document))
    return documents


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Person A's 66-cell pre-extraction successor authority."
    )
    parser.add_argument("--output-dir", type=Path, default=STATUS_ROOT)
    arguments = parser.parse_args()
    documents = write_documents(arguments.output_dir.resolve())
    config = documents["successor_extraction_config.json"]
    receipt = documents["phase6_precondition_receipt.json"]
    print(
        f"successor run_id={config['successor_run_identity']['run_id']} "
        f"contract_ready={receipt['phase6_contract_preconditions_ready']} "
        f"infrastructure_ready={receipt['phase6_runtime_infrastructure_ready']}"
    )


if __name__ == "__main__":
    main()
