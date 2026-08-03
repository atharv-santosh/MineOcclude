#!/usr/bin/env python3
"""Validate and preflight Person B's memory-bounded Step 4.1 reauthorization.

The package is intentionally additive.  The default command validates the
committed package and frozen Git authorities without reading SageMaker
payloads or executing a baseline.  ``reuse-validate`` revalidates a
materialized D input root, while ``runtime-preflight`` is the B-owned gate
that must run immediately before D's production CLI.  Runtime memory is
never inferred from swap and both physical and MemAvailable measurements are
required to be at least 20 GiB.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_RELATIVE_PATH = Path(
    "docs/status/person_b_phase4_step4_1_memory_reauthorization_v0_1"
)

DOCUMENT_NAMES = (
    "authority_binding.json",
    "incident_and_repair.json",
    "memory_contract.json",
    "compatibility_evidence.json",
    "person_d_authorization_record.json",
    "materialized_input_reuse.json",
    "production_commands.json",
    "output_closure_requirements.json",
    "final_authorization_decision.json",
    "validation_receipt.json",
    "sha256_inventory.json",
)
INVENTORIED_NAMES = DOCUMENT_NAMES[:-1]

PERSON_B_STARTING_AUTHORITY = "76e1d33788bcf1482b310d2b41a5db3d734d98a7"
PERSON_B_APPLICABILITY_STARTING_AUTHORITY = (
    "a6f1cedd390ecde129fc5b25ad50f81a0848530b"
)
PERSON_B_PROVENANCE_STARTING_AUTHORITY = (
    "60353157874d8d095ac29d76a40b8a8fa86b3d29"
)
PERSON_B_APPLICABILITY_VALIDATOR_COMMIT = (
    "248b7a174cb38a522f3638d7789b0e1d1b5befdf"
)
PERSON_D_MEMORY_IMPLEMENTATION_COMMIT = (
    "f6fb6e542f87462c366ea657ded2dc8a47c3428f"
)
PERSON_D_RUNNER_COMMIT = "683077b58fdb73176936fcb131e9297eb102ea10"
PERSON_D_PRIOR_RUNNER_COMMIT = "5b90e5bf6c6975119f509d766a82a9786d64300c"
PERSON_D_SIGNED_VALIDATOR_COMMIT = "4915252ce5a9f346fc39f1f2583478949c3787f5"
PERSON_D_EXPORTER_COMMIT = "fd9302e5d218193211f2f96986ca32dc1a365e66"
PERSON_D_CLI_COMMIT = "bb2ebf7947c92c814dae85fc9cef29fef04e4c6f"
PERSON_D_BRANCH = "role/person-d-baselines"

PERSON_A_FRAME_COMMIT = "380b9a392c7ad3a941dbdadcc777c61ed03e1206"
PERSON_B_BASELINE_COMMIT = "265cbbb394ee481439397879ad9a99c9038bf4cd"
PERSON_B_FOLD_COMMIT = "06bd2a17b90d95de37c0739d17d3a624964cc4fa"
PERSON_B_FOLD_RATIFICATION_COMMIT = "a612ec29108c8f69f19cdc283e40873e75796ea7"
PERSON_B_PRODUCTION_COMMIT = "c9a519b42cf651e05f5b4f640fda6e1a0aed3e7c"
PERSON_B_SCHEMA_COMMIT = "4e0e0f49d4642cf069de8c66c3a8fee47806c4b0"
PERSON_C_COMMIT = "c6bff25b5ef4f5fdb0e1ef0ce0d22e3f8b5e4960"
PERSON_E_COMMIT = "21d83c19c9d8f36c4dbeeaf45d4626eaf082e7a7"
AUTH_RECORD_ABSOLUTE_PATH = (
    "/home/sagemaker-user/MineOcclude-person-b-analysis/docs/status/"
    "person_b_phase4_step4_1_memory_reauthorization_v0_1/person_d_authorization_record.json"
)
MATERIALIZED_ROOT_ABSOLUTE_PATH = (
    "/home/sagemaker-user/person-d-step4-1-approved-outputs/"
    "person-d-step4-1-materialized-inputs-v0-1"
)
OUTPUT_ROOT_ABSOLUTE_PATH = (
    "/home/sagemaker-user/person-d-step4-1-approved-outputs/"
    "person-d-step4-1-production-v0-1"
)
FRAME_ROOT_ABSOLUTE_PATH = (
    "/home/sagemaker-user/person-a-step4-1-approved-outputs/"
    "person-a-step4-1-preprocessed-frames-v0-1"
)

FRAME_MANIFEST_PATH = (
    "docs/status/person_a_phase4_step4_1_frame_handoff_v0_2/"
    "preprocessed_frame_manifest.json"
)
FOLD_MANIFEST_PATH = (
    "docs/status/person_b_phase4_step4_1_production_handoff_v0_1/"
    "ten_pilot_frame_fold_manifest.json"
)
TARGET_MANIFEST_PATH = (
    "docs/status/person_b_phase4_step4_1_production_handoff_v0_1/"
    "production_oracle_target_manifest.json"
)
SOURCE_CONTEXT_MANIFEST_PATH = (
    "docs/status/person_b_phase4_step4_1_baseline_family_contract_v0_2/"
    "source_context_manifest.json"
)
ANALYSIS_CONFIG_PATH = "configs/analysis/core.yaml"

FRAME_MANIFEST_SHA256 = "f52a2ece32b00faf04b68b92b56c6f6a049b8a7bcb9c7f0af0f52de7fc4759c5"
FRAME_MANIFEST_SIZE = 6460547
FOLD_MANIFEST_SHA256 = "53ca938c6ae936c3ecb6e6e8d95a3fda152f5fa130b52e7a000d297810738d71"
FOLD_MANIFEST_SIZE = 742601
TARGET_MANIFEST_SHA256 = "afcf3afae00db6330665afc5964608c6db89eeac3767c9486d8ba0a218858282"
TARGET_MANIFEST_SIZE = 4934874
SOURCE_CONTEXT_SHA256 = "ce4ba48c53ce57c6321a657e97c166772475a77d459e59ad8d20cc37b33aa74c"
SOURCE_CONTEXT_SIZE = 4654
ANALYSIS_CONFIG_SHA256 = "b2e12e7049e0494c756be442a4f300cbc7dc0a6e262deecf682f1354e887f0ab"
ANALYSIS_CONFIG_SIZE = 4881
EXPECTED_INPUT_MANIFEST_HASH = "69191b712cfc137388e0a7f27f25be4b3af2c672cf56c569feb3a8af707d3c37"
EXPECTED_FIT_MANIFEST_HASH = "d754329cbc13d82b593908901d74d4b6539b0548db94a041e4db62bf835ecc8b"

APPLICABILITY_CONTRACT_VERSION = (
    "person-b-step4-1-family-target-applicability-v0.1"
)
APPLICABILITY_CONTRACT_RELATIVE_PATH = Path(
    "docs/status/person_b_phase4_step4_1_applicability_contract_v0_1/"
    "family_target_applicability_contract.json"
)
PRESERVED_PROVENANCE_FILENAME = "preserved_output_provenance.json"
PRESERVED_PROVENANCE_SCHEMA_ID = (
    "person-b-step4-1-preserved-output-provenance-audit-receipt-v0-2"
)
PROVENANCE_AUTHORIZATION_SCHEMA_ID = (
    "person-b-phase4-step4-1-provenance-reauthorization-v0-2-"
    "person-d-authorization-record"
)
VALIDATOR_RELATIVE_PATH = Path(
    "scripts/validate_person_b_step4_1_memory_reauthorization_v0_1.py"
)
PREDECESSOR_AUTHORIZATION_RECORD_SHA256 = (
    "f923ce73c111549fd63ab2679e4fe354406dcf525f03930e6f63b2239bd317ae"
)
PREDECESSOR_AUTHORIZATION_RECORD_PATH = (
    "/home/sagemaker-user/MineOcclude-person-b-analysis/docs/status/"
    "person_b_phase4_step4_1_memory_reauthorization_v0_1/"
    "person_d_authorization_record.json"
)
PRESERVED_COMPLETED_FAMILIES = (
    "last_seen",
    "constant_velocity",
    "grouped_shuffled",
    "time_only",
    "explicit_feature",
)
PRESERVED_PREDICTION_COUNT = 7691

EXPECTED_FAMILIES = (
    "last_seen",
    "constant_velocity",
    "grouped_shuffled",
    "time_only",
    "explicit_feature",
    "raw_pixel",
    "visible_history_q",
    "known_q_analytic",
)
EXPECTED_MAPPING = (1, 2, 4, 0, 3)
EXPECTED_LAYOUTS = tuple(f"layout_{index:02d}" for index in range(5))
EXPECTED_LAYOUT_COUNTS = (409, 387, 335, 292, 272)
EXPECTED_PILOTS = (
    "layout_00_ep9403",
    "layout_00_ep9441",
    "layout_01_ep9405",
    "layout_01_ep9442",
    "layout_02_ep9407",
    "layout_02_ep9432",
    "layout_03_ep9404",
    "layout_03_ep9443",
    "layout_04_ep9406",
    "layout_04_ep9444",
)
EXPECTED_CAPTURE_IDENTITIES = (
    ("layout_00_ep9403", "data/autonomous/layout_00_ep9403/capture_package_v0_1.json", 662116, "21ea1dba91cf92ad82080088f70905fba053557392437b19591cad1333667213"),
    ("layout_00_ep9441", "data/autonomous/layout_00_ep9441/capture_package_v0_1.json", 531375, "5e5d5d8cbeecaa07bd93af1faab23d6bdd0643df4f59e9b72397842efc3d3664"),
    ("layout_01_ep9405", "data/autonomous/layout_01_ep9405/capture_package_v0_1.json", 610140, "c139247e3be9132ddf2781f6d8abbe7d4498fa158464e3f47c534cf19b5c614f"),
    ("layout_01_ep9442", "data/autonomous/layout_01_ep9442/capture_package_v0_1.json", 531371, "4cb40c2b8b62268fba0556ed38f25644710dede5c1be9cf579e3aea445ab4096"),
    ("layout_02_ep9407", "data/autonomous/layout_02_ep9407/capture_package_v0_1.json", 422479, "ed7884bcc5e72db1d8b1c642f0ce668544c7cb348567b0ec820d69db6016004f"),
    ("layout_02_ep9432", "data/autonomous/layout_02_ep9432/capture_package_v0_1.json", 531379, "fae0107e2ceb60e62dbc5a89fe459b4d7a952ce8c28cb97faa490d3fde4d4d0c"),
    ("layout_03_ep9404", "data/autonomous/layout_03_ep9404/capture_package_v0_1.json", 332665, "c9bc91d934643a53c5b3c39d519e5b3533788021adac57373af5edea12795ac7"),
    ("layout_03_ep9443", "data/autonomous/layout_03_ep9443/capture_package_v0_1.json", 531261, "affb4273939c84a869548633f51888a8c2e429466360d906049b63e9e0f6bb83"),
    ("layout_04_ep9406", "data/autonomous/layout_04_ep9406/capture_package_v0_1.json", 302914, "3cc2917fb0698d83d4ec12aa7cd7288e4a929dd5f13e810d303fbd1cc348f021"),
    ("layout_04_ep9444", "data/autonomous/layout_04_ep9444/capture_package_v0_1.json", 531250, "4fe5bd8bedfdb78be17c580662dda5511b1314d7ee522c64db529d50dfc7c0a0"),
)

EXPECTED_CONFIGURATION = {
    "constant_velocity": {"fit_required": False, "randomness": "none"},
    "explicit_feature": {
        "alpha_grid": [0.1, 1.0, 10.0, 100.0],
        "inner_fold_count": 4,
        "scaler_fit_scope": "outer_training_rows_only",
        "seed": 20260719,
    },
    "grouped_shuffled": {
        "alignment_key": "model_frame_idx",
        "grouping_unit": "trajectory_id",
        "permutation_seed": 20260720,
        "requires_derangement": True,
    },
    "known_q_analytic": {
        "fair_baseline": False,
        "formula": "ln(sqrt(q_scripted_blocks2_per_s * tau))",
        "randomness": "none",
    },
    "last_seen": {"fit_required": False, "randomness": "none"},
    "raw_pixel": {
        "alpha_grid": [0.1, 1.0, 10.0, 100.0],
        "frame_scope": "exact_current_preprocessed_frame_only",
        "inner_fold_count": 4,
        "scaler_fit_scope": "outer_training_rows_only",
        "seed": 20260719,
    },
    "time_only": {
        "fit_scope": "outer_training_folds_only",
        "primary_polynomial_degree": 1,
        "sensitivity_polynomial_degree": 2,
    },
    "visible_history_q": {
        "dt_seconds": 0.05,
        "fit_scope": "outer_training_folds_only",
        "q_estimator": "visible_increment_residual_variance_over_dt",
    },
}

BYTES_PER_GIB = 1024**3
MINIMUM_PHYSICAL_MEMORY_GIB = 20.0
MINIMUM_AVAILABLE_MEMORY_GIB = 20.0
MINIMUM_PHYSICAL_MEMORY_BYTES = int(MINIMUM_PHYSICAL_MEMORY_GIB * BYTES_PER_GIB)
MINIMUM_AVAILABLE_MEMORY_BYTES = int(MINIMUM_AVAILABLE_MEMORY_GIB * BYTES_PER_GIB)

# The frame handoff freezes one payload profile for every admitted row.  These
# values are copied from Person A's frame-handoff authority and are used by the
# B-owned reuse check before a D runner is allowed to start.
REQUIRED_PAYLOAD_DTYPE = "float32"
REQUIRED_PAYLOAD_LAYOUT = "CHW"
REQUIRED_PAYLOAD_COLOR_ORDER = "RGB"
REQUIRED_PAYLOAD_FORMAT = "raw-little-endian-float32-c-order"
REQUIRED_PAYLOAD_SHAPE = (3, 224, 384)

# D's exporter emits only applicable rows.  In particular, log_sigma is
# defined only for the 695 occluded rows, while grouped_shuffled additionally
# omits rows whose seeded donor lacks the explicit model_frame_idx.  Resume
# validation therefore checks family/target-specific identities, not a blanket
# 1,695-row count.
EXPECTED_RESUME_TARGET_FAMILIES = {
    "last_seen": ("mu_oracle_blocks",),
    "constant_velocity": ("mu_oracle_blocks",),
    "grouped_shuffled": ("log_sigma_oracle", "mu_oracle_blocks"),
    "time_only": ("log_sigma_oracle",),
    "explicit_feature": ("mu_oracle_blocks",),
    "raw_pixel": ("mu_oracle_blocks",),
    "visible_history_q": ("log_sigma_oracle",),
    "known_q_analytic": ("log_sigma_oracle",),
}

# Exact result of D's ``make_shuffle_permutation`` (sorted ten-pilot IDs,
# NumPy default_rng seed 20260720) at the authorized runner.  Freezing this
# donor map lets B validate grouped-shuffled row identities without importing
# or executing D's scientific code.
EXPECTED_GROUPED_SHUFFLE_DONORS = {
    "layout_00_ep9403": "layout_03_ep9404",
    "layout_00_ep9441": "layout_01_ep9442",
    "layout_01_ep9405": "layout_04_ep9406",
    "layout_01_ep9442": "layout_00_ep9441",
    "layout_02_ep9407": "layout_02_ep9432",
    "layout_02_ep9432": "layout_04_ep9444",
    "layout_03_ep9404": "layout_01_ep9405",
    "layout_03_ep9443": "layout_00_ep9403",
    "layout_04_ep9406": "layout_02_ep9407",
    "layout_04_ep9444": "layout_03_ep9443",
}

EXPECTED_PERSON_B_PREDICTION_RESERVATION = {
    "path": "/home/sagemaker-user/person-b-step4-1-approved-outputs/"
    "person-b-step4-1-production-v0-1/fitted_probes_and_predictions.json",
    "sha256": "01e792c4d7b58bbe4ae478195b1d9523802db5674ee06ebbf5364482f42061ba",
    "byte_size": 84257218,
    "direct_input_to_person_d": False,
    "immutable": True,
    "reserved_for_later_comparison": True,
}


class MemoryReauthorizationError(ValueError):
    """Raised for a fail-closed package, reuse, or runtime-gate violation."""


PersonBMemoryReauthorizationError = MemoryReauthorizationError


def _fail(code: str, message: str) -> None:
    raise MemoryReauthorizationError(f"{code}: {message}")


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        _fail(code, message)


def canonical_json_bytes(value: Any) -> bytes:
    """Encode repository-canonical JSON (sorted, UTF-8, final newline)."""

    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        _fail("noncanonical_json", str(error))
    return (text + "\n").encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _git_blob(repo_root: Path, commit: str, path: str) -> bytes:
    result = subprocess.run(
        ["git", "cat-file", "blob", f"{commit}:{path}"],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        _fail("git_object_missing", detail or f"{commit}:{path}")
    return result.stdout


def _git_text(repo_root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repo_root,
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        _fail("git_command_failed", result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def _is_ancestor(repo_root: Path, ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _parse_bytes(raw: bytes, label: str, *, canonical: bool = True) -> Mapping[str, Any]:
    _require(not raw.startswith(b"\xef\xbb\xbf"), "noncanonical_json", f"{label} has a BOM")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail("invalid_json", f"{label}: {error}")
    _require(isinstance(value, Mapping), "invalid_json", f"{label} is not an object")
    if canonical:
        _require(raw == canonical_json_bytes(value), "noncanonical_json", label)
    return value


def _parse_path(path: Path, label: str, *, canonical: bool = True) -> Mapping[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        _fail("artifact_missing", f"{label}: {error}")
    return _parse_bytes(raw, label, canonical=canonical)


def _artifact_reference(
    reference: Mapping[str, Any],
    *,
    label: str,
    expected_commit: str,
    expected_path: str,
    expected_sha256: str,
    expected_size: int,
    repo_root: Path,
) -> bytes:
    _require(reference.get("source_commit") == expected_commit, "authority_mismatch", f"{label}.source_commit")
    _require(reference.get("path") == expected_path, "authority_mismatch", f"{label}.path")
    raw = _git_blob(repo_root, expected_commit, expected_path)
    _require(len(raw) == expected_size, "artifact_identity_mismatch", f"{label}.byte_size source")
    _require(_sha256(raw) == expected_sha256, "artifact_identity_mismatch", f"{label}.sha256 source")
    _require(reference.get("byte_size") == expected_size, "artifact_identity_mismatch", f"{label}.byte_size")
    _require(reference.get("sha256") == expected_sha256, "artifact_identity_mismatch", f"{label}.sha256")
    return raw


def _load_documents(package_root: Path) -> dict[str, Mapping[str, Any]]:
    try:
        actual = {path.name for path in package_root.iterdir() if path.is_file()}
    except OSError as error:
        _fail("package_missing", str(error))
    _require(actual == set(DOCUMENT_NAMES), "package_inventory_mismatch", "package JSON set")
    documents: dict[str, Mapping[str, Any]] = {}
    for name in DOCUMENT_NAMES:
        document = _parse_path(package_root / name, name)
        _require(document.get("schema_version") == "1.0", "schema_mismatch", name)
        _require(
            isinstance(document.get("schema_id"), str)
            and document["schema_id"].startswith(
                "person-b-phase4-step4-1-memory-reauthorization-v0-1-"
            ),
            "schema_mismatch",
            name,
        )
        documents[name] = document
    return documents


def _validate_inventory(package_root: Path, documents: Mapping[str, Mapping[str, Any]]) -> None:
    inventory = documents["sha256_inventory.json"]
    _require(inventory.get("algorithm") == "sha256", "inventory_mismatch", "algorithm")
    _require(inventory.get("inventory_excludes_self") is True, "inventory_mismatch", "self exclusion")
    files = inventory.get("files")
    expected = {f"{PACKAGE_RELATIVE_PATH.as_posix()}/{name}" for name in INVENTORIED_NAMES}
    _require(isinstance(files, Mapping) and set(files) == expected, "inventory_mismatch", "file set")
    for relative in expected:
        name = Path(relative).name
        entry = files[relative]
        _require(isinstance(entry, Mapping), "inventory_mismatch", f"{name} entry")
        raw = (package_root / name).read_bytes()
        _require(entry.get("byte_size") == len(raw), "inventory_mismatch", f"{name} size")
        _require(entry.get("sha256") == _sha256(raw), "inventory_mismatch", f"{name} hash")


def _reject_u4_references(value: Any, path: str = "package") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            lowered = str(key).lower()
            if "u4" in lowered:
                if lowered == "u4_output_inspected":
                    _require(child is False, "u4_reference", f"{path}.{key}")
                elif lowered in {"no_u4_access", "u4_access_forbidden", "u4_inputs_forbidden"}:
                    _require(child is True, "u4_reference", f"{path}.{key}")
                else:
                    _fail("u4_reference", f"{path}.{key}")
            _reject_u4_references(child, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, child in enumerate(value):
            _reject_u4_references(child, f"{path}[{index}]")
    elif isinstance(value, str) and re.search(
        r"(?:--|/|\\|\\.json|\\.npy|\\.npz)[^\n]*u4|u4[^\n]*(?:/|\\|\\.json|\\.npy|\\.npz)",
        value,
        re.IGNORECASE,
    ):
        # A real path/CLI argument is forbidden.  Ordinary prose is allowed,
        # but package values containing an option or path-like U4 reference
        # are not.
        _fail("u4_reference", path)


def _validate_safety_claims(documents: Mapping[str, Mapping[str, Any]]) -> None:
    guarded_false = {
        "baseline_execution_performed",
        "execution_performed",
        "final_comparison_complete",
        "final_comparison_performed",
        "metric_computed",
        "metrics_computed",
        "production_execution_performed",
        "scientific_execution_performed",
        "step4_1_complete",
        "u4_output_inspected",
    }

    def walk(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if key in guarded_false:
                    _require(child is False, "execution_claim_mismatch", f"{path}.{key}")
                walk(child, f"{path}.{key}")
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    for name, document in documents.items():
        walk(document, name)
        _reject_u4_references(document, name)


def _validate_exact_git_objects(repo_root: Path) -> None:
    for commit in (
        PERSON_B_STARTING_AUTHORITY,
        PERSON_D_MEMORY_IMPLEMENTATION_COMMIT,
        PERSON_D_RUNNER_COMMIT,
        PERSON_D_PRIOR_RUNNER_COMMIT,
        PERSON_D_SIGNED_VALIDATOR_COMMIT,
        PERSON_D_EXPORTER_COMMIT,
        PERSON_D_CLI_COMMIT,
        PERSON_A_FRAME_COMMIT,
        PERSON_B_BASELINE_COMMIT,
        PERSON_B_FOLD_COMMIT,
        PERSON_B_FOLD_RATIFICATION_COMMIT,
        PERSON_B_PRODUCTION_COMMIT,
        PERSON_B_SCHEMA_COMMIT,
        PERSON_C_COMMIT,
        PERSON_E_COMMIT,
    ):
        _require(_git_text(repo_root, "cat-file", "-t", commit) == "commit", "git_authority_missing", commit)
    _require(
        _is_ancestor(repo_root, PERSON_D_MEMORY_IMPLEMENTATION_COMMIT, PERSON_D_RUNNER_COMMIT),
        "git_ancestry_mismatch",
        "D memory implementation must be an ancestor of D runner HEAD",
    )


def _validate_authority(repo_root: Path, authority: Mapping[str, Any]) -> None:
    _require(authority.get("supersedes_authorization_commit") == PERSON_B_STARTING_AUTHORITY, "supersession_mismatch", "prior authorization")
    _require(authority.get("person_d_branch") == PERSON_D_BRANCH, "authority_mismatch", "D branch")
    _require(authority.get("authorized_person_d_head") == PERSON_D_RUNNER_COMMIT, "authority_mismatch", "D HEAD")
    _require(authority.get("person_d_memory_implementation_commit") == PERSON_D_MEMORY_IMPLEMENTATION_COMMIT, "authority_mismatch", "D memory commit")
    _require(authority.get("baseline_family_count") == 8, "family_mismatch", "family count")
    _require(tuple(authority.get("baseline_families", ())) == EXPECTED_FAMILIES, "family_mismatch", "family order")
    _require(authority.get("preprocessed_frame_count") == 1695, "frame_mismatch", "frame count")
    authorities = authority.get("authorities")
    _require(isinstance(authorities, Mapping), "authority_mismatch", "authorities")
    expected_authorities = {
        "person_a_frame_handoff_commit": PERSON_A_FRAME_COMMIT,
        "person_b_baseline_v0_2_commit": PERSON_B_BASELINE_COMMIT,
        "person_b_fold_contract_commit": PERSON_B_FOLD_COMMIT,
        "person_b_fold_interface_ratification_commit": PERSON_B_FOLD_RATIFICATION_COMMIT,
        "person_b_production_ratification_commit": PERSON_B_PRODUCTION_COMMIT,
        "person_b_schema_correction_commit": PERSON_B_SCHEMA_COMMIT,
        "person_c_expansion_acceptance_commit": PERSON_C_COMMIT,
        "person_d_cli_commit": PERSON_D_CLI_COMMIT,
        "person_d_exporter_commit": PERSON_D_EXPORTER_COMMIT,
        "person_d_memory_implementation_commit": PERSON_D_MEMORY_IMPLEMENTATION_COMMIT,
        "person_d_prior_runner_commit": PERSON_D_PRIOR_RUNNER_COMMIT,
        "person_d_runner_commit": PERSON_D_RUNNER_COMMIT,
        "person_d_signed_validator_commit": PERSON_D_SIGNED_VALIDATOR_COMMIT,
        "person_e_handoff_commit": PERSON_E_COMMIT,
    }
    _require(set(authorities) == set(expected_authorities), "authority_mismatch", "authority fields")
    for key, expected in expected_authorities.items():
        _require(authorities.get(key) == expected, "authority_mismatch", key)
    artifacts = authority.get("artifacts")
    _require(isinstance(artifacts, Mapping), "authority_mismatch", "artifacts")
    _require(
        set(artifacts)
        == {"analysis_config", "fold_manifest", "frame_manifest", "source_context_manifest", "target_manifest"},
        "authority_mismatch",
        "artifact fields",
    )
    for key, commit, path, digest, size in (
        ("frame_manifest", PERSON_A_FRAME_COMMIT, FRAME_MANIFEST_PATH, FRAME_MANIFEST_SHA256, FRAME_MANIFEST_SIZE),
        ("fold_manifest", PERSON_B_PRODUCTION_COMMIT, FOLD_MANIFEST_PATH, FOLD_MANIFEST_SHA256, FOLD_MANIFEST_SIZE),
        ("target_manifest", PERSON_B_PRODUCTION_COMMIT, TARGET_MANIFEST_PATH, TARGET_MANIFEST_SHA256, TARGET_MANIFEST_SIZE),
        ("source_context_manifest", PERSON_B_BASELINE_COMMIT, SOURCE_CONTEXT_MANIFEST_PATH, SOURCE_CONTEXT_SHA256, SOURCE_CONTEXT_SIZE),
    ):
        reference = artifacts.get(key)
        _require(isinstance(reference, Mapping), "authority_mismatch", f"{key} reference")
        _artifact_reference(reference, label=key, expected_commit=commit, expected_path=path, expected_sha256=digest, expected_size=size, repo_root=repo_root)
    config = artifacts.get("analysis_config")
    _require(isinstance(config, Mapping), "authority_mismatch", "analysis config")
    _require(config.get("source_commit") == PERSON_B_PRODUCTION_COMMIT, "authority_mismatch", "analysis config commit")
    _require(config.get("path") == ANALYSIS_CONFIG_PATH, "authority_mismatch", "analysis config path")
    _require(config.get("sha256") == ANALYSIS_CONFIG_SHA256 and config.get("byte_size") == ANALYSIS_CONFIG_SIZE, "artifact_identity_mismatch", "analysis config")
    config_raw = _git_blob(repo_root, PERSON_B_PRODUCTION_COMMIT, ANALYSIS_CONFIG_PATH)
    _require(
        len(config_raw) == ANALYSIS_CONFIG_SIZE and _sha256(config_raw) == ANALYSIS_CONFIG_SHA256,
        "artifact_identity_mismatch",
        "analysis config source identity",
    )
    contract = authority.get("contract")
    _require(isinstance(contract, Mapping), "mapping_mismatch", "contract")
    _require(
        set(contract)
        == {"assignment_by_ordered_layout", "contract_version", "layout_row_counts", "seed", "validation_mode"},
        "mapping_mismatch",
        "contract fields",
    )
    _require(contract.get("assignment_by_ordered_layout") == list(EXPECTED_MAPPING), "mapping_mismatch", "assignment")
    _require(contract.get("layout_row_counts") == list(EXPECTED_LAYOUT_COUNTS), "mapping_mismatch", "layout counts")
    _require(contract.get("seed") == 20260719, "mapping_mismatch", "seed")
    _require(contract.get("validation_mode") == "signed_explicit_mapping", "mapping_mismatch", "validation mode")
    _require(authority.get("configuration") == EXPECTED_CONFIGURATION, "configuration_mismatch", "family configuration")
    prediction = authority.get("person_b_predictions")
    _require(isinstance(prediction, Mapping), "prediction_boundary_mismatch", "B prediction boundary")
    _require(
        set(prediction)
        == {"byte_size", "direct_input_to_person_d", "metrics_pending_person_d", "path", "reserved_for_later_comparison", "sha256"},
        "prediction_boundary_mismatch",
        "B prediction fields",
    )
    for key, expected in (("direct_input_to_person_d", False), ("reserved_for_later_comparison", True), ("metrics_pending_person_d", True)):
        _require(prediction.get(key) is expected, "prediction_boundary_mismatch", key)
    _require(authority.get("u4_output_inspected") is False, "u4_reference", "authority U4")


def _validate_incident(document: Mapping[str, Any]) -> None:
    _require(document.get("failed_execution_exit_code") == 137, "incident_mismatch", "exit code")
    _require(document.get("materialization_complete") is True, "incident_mismatch", "materialization")
    _require(document.get("completed_baseline_family_count") == 0, "incident_mismatch", "completed families")
    _require(document.get("baseline_prediction_count") == 0, "incident_mismatch", "prediction count")
    _require(document.get("scientific_execution_performed") is False, "execution_claim_mismatch", "incident execution")
    _require(document.get("u4_output_inspected") is False, "u4_reference", "incident U4")
    _require(document.get("feature_value_count") == 437391360, "memory_contract_mismatch", "incident feature count")
    _require(document.get("previous_representation") == "boxed_python_float", "incident_mismatch", "representation")
    _require(document.get("repaired_representation") == "owned_float32_numpy", "incident_mismatch", "repair representation")
    _require(document.get("memory_implementation_commit") == PERSON_D_MEMORY_IMPLEMENTATION_COMMIT, "authority_mismatch", "repair commit")
    repair_facts = document.get("repair_facts")
    _require(isinstance(repair_facts, Mapping), "incident_mismatch", "repair facts")
    _require(
        set(repair_facts)
        == {"family_execution", "raw_pixel_construction", "release_after_family", "resume_behavior", "source_operation_removed", "storage"},
        "incident_mismatch",
        "repair fact fields",
    )
    _require(
        repair_facts
        == {
            "family_execution": "sequential",
            "raw_pixel_construction": "lazy_provider_only_for_raw_pixel",
            "release_after_family": True,
            "resume_behavior": "fail_closed",
            "source_operation_removed": "list(struct.unpack(...))",
            "storage": "np.frombuffer(payload, dtype='<f4').copy()",
        },
        "incident_mismatch",
        "repair facts",
    )


def _validate_memory_contract(document: Mapping[str, Any]) -> None:
    _require(
        1695 * REQUIRED_PAYLOAD_SHAPE[0] * REQUIRED_PAYLOAD_SHAPE[1] * REQUIRED_PAYLOAD_SHAPE[2]
        == 437391360,
        "memory_contract_mismatch",
        "feature value arithmetic",
    )
    expected = {
        "feature_value_count": 437391360,
        "feature_dtype": "float32",
        "compact_primary_matrix_gib": 1.629,
        "estimated_peak_memory_gib": 14.96,
        "minimum_detected_physical_memory_gib": MINIMUM_PHYSICAL_MEMORY_GIB,
        "minimum_detected_physical_memory_bytes": MINIMUM_PHYSICAL_MEMORY_BYTES,
        "minimum_available_memory_gib": MINIMUM_AVAILABLE_MEMORY_GIB,
        "minimum_available_memory_bytes": MINIMUM_AVAILABLE_MEMORY_BYTES,
        "swap_required": False,
        "previous_15_gib_host_supported": False,
        "runtime_preflight_required": True,
        "swap_counts_as_capacity": False,
    }
    for key, value in expected.items():
        _require(document.get(key) == value, "memory_contract_mismatch", key)
    _require(document.get("missing_detection_fails_closed") is True, "memory_contract_mismatch", "missing detection")
    _require(document.get("physical_memory_source") == "linux_sysconf_SC_PHYS_PAGES", "memory_contract_mismatch", "physical source")
    _require(document.get("available_memory_source") == "linux_/proc/meminfo_MemAvailable", "memory_contract_mismatch", "available source")
    _require(isinstance(document.get("cgroup_capacity_accounting"), str), "memory_contract_mismatch", "cgroup accounting")


def _validate_compatibility(repo_root: Path, document: Mapping[str, Any]) -> None:
    _require(document.get("authorized_runner_commit") == PERSON_D_RUNNER_COMMIT, "compatibility_mismatch", "D HEAD")
    _require(document.get("memory_repair_commit") == PERSON_D_MEMORY_IMPLEMENTATION_COMMIT, "compatibility_mismatch", "memory repair")
    _require(document.get("raw_pixel_boxing_removed") is True, "compatibility_mismatch", "boxing")
    _require(document.get("direct_pixel_features_by_key_bypass_authorized") is False, "compatibility_mismatch", "direct pixel bypass")
    _require(document.get("raw_pixel_construction_lazy") is True, "compatibility_mismatch", "lazy raw pixel")
    _require(document.get("family_execution_sequential") is True, "compatibility_mismatch", "sequential families")
    _require(document.get("family_state_released_after_each") is True, "compatibility_mismatch", "release")
    _require(document.get("resume_fail_closed_preserved") is True, "compatibility_mismatch", "resume")
    _require(document.get("expected_input_manifest_hash") == EXPECTED_INPUT_MANIFEST_HASH, "compatibility_mismatch", "input lineage hash")
    _require(document.get("expected_fit_manifest_hash") == EXPECTED_FIT_MANIFEST_HASH, "compatibility_mismatch", "fit lineage hash")
    _require(document.get("scientific_semantics_changed") is False, "compatibility_mismatch", "semantics")
    _require(document.get("all_eight_family_semantics_preserved") is True, "compatibility_mismatch", "families")
    _require(document.get("scientific_execution_performed") is False, "execution_claim_mismatch", "compatibility execution")
    _require(document.get("u4_output_inspected") is False, "u4_reference", "compatibility U4")
    sources = document.get("sources")
    _require(isinstance(sources, Sequence), "compatibility_mismatch", "source list")
    expected_sources = {
        ("baseline_family_contract", "src/mineocclude/baselines/baseline_family_input_v0_2.py", PERSON_D_RUNNER_COMMIT, 23620, "91d842c2644bc5b14ec8dfe659bac894fe3f18e258fded1ebb6c0e4fff040b6b"),
        ("eight_family_execution_manifest", "src/mineocclude/baselines/eight_family_execution_manifest.py", PERSON_D_RUNNER_COMMIT, 14566, "15a0ed801fd51d493a8ed42c555c9cb352c0f29fb134ac3b8114f8f457da02d0"),
        ("eight_family_runner", "src/mineocclude/baselines/eight_family_runner.py", PERSON_D_RUNNER_COMMIT, 7532, "30a1a4db22cc87e80f38c21451ee0999d87feea5b2239c48a22291e0c876d516"),
        ("frame_handoff", "src/mineocclude/baselines/frame_handoff_v0_2.py", PERSON_D_RUNNER_COMMIT, 13984, "0875544dc0a9b4947346b2270c30436a151aa40baa46da9f97bf26ca550af42c"),
        ("runner", "scripts/run_person_d_step4_1_eight_family_production.py", PERSON_D_RUNNER_COMMIT, 45956, "b35df13a76fa5ec9faa055ad4228d0d8834a90dacaf7dd65024f5afe61bbd055"),
        ("memory_planning", "src/mineocclude/baselines/memory_planning.py", PERSON_D_RUNNER_COMMIT, 10367, "9a159f7c427f48bf1cfcae5cbf31ed50dd967c4c16082062348df5c1f3d5a5f1"),
        ("production_fold_contract", "src/mineocclude/baselines/production_fold_contract_v0_1.py", PERSON_D_RUNNER_COMMIT, 21947, "a7320652122cf0544d9d7bdfd067eb449c3e851bce59b1ed3d9c12eaf2371799"),
        ("production_input_ingest", "src/mineocclude/baselines/production_input_ingest.py", PERSON_D_RUNNER_COMMIT, 21496, "979f42e877a06fcd5d03db4c05b42cbd55b80b4c41152e52eec31f29dafdd54a"),
        ("exporter", "src/mineocclude/baselines/export.py", PERSON_D_RUNNER_COMMIT, 10947, "dd81389342d174b989ffe7029596fbd05f25ba8f638846837a97a0f1f07634df"),
        ("semantic_equivalence_tests", "tests/baselines/test_memory_repair_semantic_equivalence.py", PERSON_D_RUNNER_COMMIT, 10631, "4c3494e1abef729209674020f479d2b01c4d6ebaa78e5d6301652021a8a71ff2"),
    }
    _require(len(sources) == len(expected_sources), "compatibility_mismatch", "source count")
    actual_keys: set[tuple[Any, ...]] = set()
    for reference in sources:
        _require(isinstance(reference, Mapping), "compatibility_mismatch", "source reference")
        key = (reference.get("id"), reference.get("path"), reference.get("source_commit"), reference.get("byte_size"), reference.get("sha256"))
        actual_keys.add(key)
        if key in expected_sources:
            raw = _git_blob(repo_root, reference["source_commit"], reference["path"])
            _require(len(raw) == reference["byte_size"] and _sha256(raw) == reference["sha256"], "compatibility_mismatch", str(key))
    _require(actual_keys == expected_sources, "compatibility_mismatch", "source identities")
    ingest_source = _git_blob(
        repo_root,
        PERSON_D_RUNNER_COMMIT,
        "src/mineocclude/baselines/production_input_ingest.py",
    )
    _require(
        b"list(struct.unpack" not in ingest_source,
        "compatibility_mismatch",
        "boxed raw-pixel decode remains",
    )
    _require(
        b'np.frombuffer(payload, dtype="<f4").copy()' in ingest_source,
        "compatibility_mismatch",
        "compact float32 decode missing",
    )
    runner_source = _git_blob(
        repo_root,
        PERSON_D_RUNNER_COMMIT,
        "scripts/run_person_d_step4_1_eight_family_production.py",
    )
    _require(
        b"pixel_features_provider" in runner_source
        and b"family_id == \"raw_pixel\"" in runner_source
        and b"gc.collect()" in runner_source,
        "compatibility_mismatch",
        "raw-pixel family scoping/release",
    )
    historical = document.get("historical_prior_authorization")
    _require(isinstance(historical, Mapping), "compatibility_mismatch", "historical prior authorization")
    for label, commit, path, size, digest in (
        ("runner_source", PERSON_D_PRIOR_RUNNER_COMMIT, "scripts/run_person_d_step4_1_eight_family_production.py", 40031, "944b5651c575e81679c1fdd5b0c122af91d1042ebc1720aa4edddbe446eaf6a7"),
        ("branch_authorization_record", PERSON_D_PRIOR_RUNNER_COMMIT, "docs/status/person_d_phase4_step4_1_eight_family_production_v0_2/authorized_runner_commit.json", 1072, "caba5883168d2ba5e509eb5b01e8c879ad447e3e8b1faf5bf89b1822472ea7e0"),
        ("real_manifest_receipt", PERSON_D_PRIOR_RUNNER_COMMIT, "docs/status/person_d_phase4_step4_1_signed_fold_validation_v0_1/real_manifest_regression_result.json", 1875, "a5a25cb4ca0c5a59df3c02786214efe9d64c3f9f1619272bd51a84417343681b"),
    ):
        reference = historical.get(label)
        _require(isinstance(reference, Mapping), "compatibility_mismatch", f"historical {label}")
        raw = _git_blob(repo_root, commit, path)
        _require(len(raw) == size and _sha256(raw) == digest, "compatibility_mismatch", f"historical {label} source")
        _require(reference.get("source_commit") == commit and reference.get("path") == path and reference.get("byte_size") == size and reference.get("sha256") == digest, "compatibility_mismatch", f"historical {label}")


def _validate_applicability_external_auth(
    repo_root: Path, document: Mapping[str, Any]
) -> None:
    expected_decisions = {
        family: ("reusable" if family in PRESERVED_COMPLETED_FAMILIES else "absent")
        for family in EXPECTED_FAMILIES
    }
    expected_producing = {
        family: PERSON_D_RUNNER_COMMIT for family in PRESERVED_COMPLETED_FAMILIES
    }
    expected_authorizations = {
        family: PERSON_B_APPLICABILITY_STARTING_AUTHORITY
        for family in PRESERVED_COMPLETED_FAMILIES
    }
    expected_fields = {
        "accepted_authorization_authority_by_reusable_family",
        "accepted_producing_authority_by_reusable_family",
        "applicability_contract_path",
        "applicability_contract_sha256",
        "applicability_contract_version",
        "authorization_scope",
        "authorized_branch",
        "authorized_runner_commit",
        "frame_root",
        "materialized_root",
        "minimum_available_memory_gib",
        "minimum_physical_memory_gib",
        "output_root",
        "preserved_output_decisions",
        "preserved_output_runtime_revalidation_required",
        "record_purpose",
        "schema_id",
        "schema_version",
        "scientific_execution_performed",
        "source_commit",
        "supersedes_authorization_commit",
        "u4_output_inspected",
    }
    _require(
        set(document) == expected_fields,
        "runtime_authorization_mismatch",
        "applicability record fields",
    )
    _require(
        document.get("schema_version") == "1.0"
        and document.get("schema_id")
        == "person-b-phase4-step4-1-applicability-reauthorization-v0-1-person-d-authorization-record",
        "runtime_authorization_mismatch",
        "applicability record schema",
    )
    _require(
        document.get("authorized_runner_commit") == PERSON_D_RUNNER_COMMIT
        and document.get("authorized_branch") == PERSON_D_BRANCH,
        "runtime_authorization_mismatch",
        "runner lineage",
    )
    _require(
        document.get("supersedes_authorization_commit")
        == PERSON_B_APPLICABILITY_STARTING_AUTHORITY,
        "runtime_authorization_mismatch",
        "supersession",
    )
    _require(
        document.get("applicability_contract_version")
        == APPLICABILITY_CONTRACT_VERSION
        and document.get("applicability_contract_path")
        == APPLICABILITY_CONTRACT_RELATIVE_PATH.as_posix(),
        "runtime_authorization_mismatch",
        "applicability binding",
    )
    contract_path = repo_root / APPLICABILITY_CONTRACT_RELATIVE_PATH
    _require(
        contract_path.is_file()
        and document.get("applicability_contract_sha256")
        == _sha256(contract_path.read_bytes()),
        "runtime_authorization_mismatch",
        "applicability hash",
    )
    _require(
        document.get("preserved_output_decisions") == expected_decisions
        and document.get("accepted_producing_authority_by_reusable_family")
        == expected_producing
        and document.get("accepted_authorization_authority_by_reusable_family")
        == expected_authorizations
        and document.get("preserved_output_runtime_revalidation_required") is True,
        "runtime_authorization_mismatch",
        "preserved output decisions",
    )
    _require(
        document.get("minimum_physical_memory_gib")
        == MINIMUM_PHYSICAL_MEMORY_GIB
        and document.get("minimum_available_memory_gib")
        == MINIMUM_AVAILABLE_MEMORY_GIB,
        "runtime_authorization_mismatch",
        "memory thresholds",
    )
    _require(
        document.get("materialized_root") == MATERIALIZED_ROOT_ABSOLUTE_PATH
        and document.get("frame_root") == FRAME_ROOT_ABSOLUTE_PATH
        and document.get("output_root") == OUTPUT_ROOT_ABSOLUTE_PATH,
        "runtime_authorization_mismatch",
        "approved roots",
    )
    _require(
        document.get("authorization_scope")
        == "Person B applicability-aware fail-closed resume authorization for exact Person D runner HEAD"
        and document.get("record_purpose")
        == "External superseding authorization passed explicitly from the clean Person B checkout to D's loader"
        and document.get("source_commit") == "external_person_b_package",
        "runtime_authorization_mismatch",
        "record purpose",
    )
    _require(
        document.get("scientific_execution_performed") is False
        and document.get("u4_output_inspected") is False,
        "runtime_authorization_mismatch",
        "safety",
    )


def _provenance_validator_commit(repo_root: Path = ROOT) -> str:
    """Return the committed authority that most recently changed this validator."""

    commit = _git_text(
        repo_root,
        "log",
        "-1",
        "--format=%H",
        "--",
        VALIDATOR_RELATIVE_PATH.as_posix(),
    )
    _require(
        re.fullmatch(r"[0-9a-f]{40}", commit) is not None,
        "runtime_authorization_mismatch",
        "provenance validator commit",
    )
    return commit


def _validate_provenance_external_auth(
    repo_root: Path, document: Mapping[str, Any]
) -> None:
    """Validate the non-circular v0.2 Person B resume authorization record."""

    expected_fields = {
        "accepted_authorization_authority_by_reusable_family",
        "accepted_producing_authority_by_reusable_family",
        "applicability_contract_path",
        "applicability_contract_sha256",
        "applicability_contract_version",
        "atomic_receipt_generation_required",
        "authorization_scope",
        "authorized_branch",
        "authorized_runner_commit",
        "direct_output_validation_required",
        "existing_receipt_revalidation_required",
        "frame_root",
        "materialized_root",
        "minimum_available_memory_gib",
        "minimum_physical_memory_gib",
        "output_root",
        "preserved_reusable_families",
        "provenance_audit_validator_commit",
        "provenance_receipt_is_audit_output",
        "record_purpose",
        "schema_id",
        "schema_version",
        "scientific_execution_performed",
        "source_commit",
        "supersedes_authorization_commit",
        "u4_output_inspected",
    }
    _require(
        set(document) == expected_fields,
        "runtime_authorization_mismatch",
        "provenance record fields",
    )
    _require(
        document.get("schema_version") == "2.0"
        and document.get("schema_id") == PROVENANCE_AUTHORIZATION_SCHEMA_ID,
        "runtime_authorization_mismatch",
        "provenance record schema",
    )
    _require(
        document.get("authorized_runner_commit") == PERSON_D_RUNNER_COMMIT
        and document.get("authorized_branch") == PERSON_D_BRANCH,
        "runtime_authorization_mismatch",
        "runner lineage",
    )
    _require(
        document.get("supersedes_authorization_commit")
        == PERSON_B_PROVENANCE_STARTING_AUTHORITY,
        "runtime_authorization_mismatch",
        "provenance supersession",
    )
    _require(
        document.get("provenance_audit_validator_commit")
        == _provenance_validator_commit(repo_root),
        "runtime_authorization_mismatch",
        "provenance validator authority",
    )
    contract_path = repo_root / APPLICABILITY_CONTRACT_RELATIVE_PATH
    _require(
        document.get("applicability_contract_version")
        == APPLICABILITY_CONTRACT_VERSION
        and document.get("applicability_contract_path")
        == APPLICABILITY_CONTRACT_RELATIVE_PATH.as_posix()
        and contract_path.is_file()
        and document.get("applicability_contract_sha256")
        == _sha256(contract_path.read_bytes()),
        "runtime_authorization_mismatch",
        "applicability binding",
    )
    expected_producing = {
        family: PERSON_D_RUNNER_COMMIT for family in PRESERVED_COMPLETED_FAMILIES
    }
    expected_authorizations = {
        family: PERSON_B_APPLICABILITY_STARTING_AUTHORITY
        for family in PRESERVED_COMPLETED_FAMILIES
    }
    _require(
        tuple(document.get("preserved_reusable_families", ()))
        == PRESERVED_COMPLETED_FAMILIES
        and document.get("accepted_producing_authority_by_reusable_family")
        == expected_producing
        and document.get("accepted_authorization_authority_by_reusable_family")
        == expected_authorizations,
        "runtime_authorization_mismatch",
        "preserved output lineage",
    )
    _require(
        document.get("direct_output_validation_required") is True
        and document.get("provenance_receipt_is_audit_output") is True
        and document.get("atomic_receipt_generation_required") is True
        and document.get("existing_receipt_revalidation_required") is True,
        "runtime_authorization_mismatch",
        "corrected audit lifecycle",
    )
    _require(
        document.get("minimum_physical_memory_gib")
        == MINIMUM_PHYSICAL_MEMORY_GIB
        and document.get("minimum_available_memory_gib")
        == MINIMUM_AVAILABLE_MEMORY_GIB,
        "runtime_authorization_mismatch",
        "memory thresholds",
    )
    _require(
        document.get("materialized_root") == MATERIALIZED_ROOT_ABSOLUTE_PATH
        and document.get("frame_root") == FRAME_ROOT_ABSOLUTE_PATH
        and document.get("output_root") == OUTPUT_ROOT_ABSOLUTE_PATH,
        "runtime_authorization_mismatch",
        "approved roots",
    )
    _require(
        document.get("authorization_scope")
        == "Person B provenance-audited fail-closed resume authorization for exact Person D runner HEAD"
        and document.get("record_purpose")
        == "External superseding authorization whose receipt is generated only after direct Person B audit"
        and document.get("source_commit") == "external_person_b_package",
        "runtime_authorization_mismatch",
        "record purpose",
    )
    _require(
        document.get("scientific_execution_performed") is False
        and document.get("u4_output_inspected") is False,
        "runtime_authorization_mismatch",
        "safety",
    )


def _validate_external_auth(repo_root: Path, document: Mapping[str, Any]) -> None:
    if document.get("schema_id") == PROVENANCE_AUTHORIZATION_SCHEMA_ID:
        _validate_provenance_external_auth(repo_root, document)
        return
    if (
        document.get("schema_id")
        == "person-b-phase4-step4-1-applicability-reauthorization-v0-1-person-d-authorization-record"
    ):
        _validate_applicability_external_auth(repo_root, document)
        return
    _require(document.get("schema_version") == "1.0", "runtime_authorization_mismatch", "schema_version")
    _require(
        document.get("schema_id")
        == "person-b-phase4-step4-1-memory-reauthorization-v0-1-person-d-authorization-record",
        "runtime_authorization_mismatch",
        "schema_id",
    )
    _require(
        set(document)
        == {
            "authorization_scope",
            "authorized_branch",
            "authorized_runner_commit",
            "record_purpose",
            "schema_id",
            "schema_version",
            "scientific_execution_performed",
            "source_commit",
            "u4_output_inspected",
        },
        "runtime_authorization_mismatch",
        "record fields",
    )
    _require(document.get("authorized_runner_commit") == PERSON_D_RUNNER_COMMIT, "runtime_authorization_mismatch", "authorized_runner_commit")
    _require(document.get("authorized_branch") == PERSON_D_BRANCH, "runtime_authorization_mismatch", "authorized_branch")
    _require(document.get("authorization_scope") == "Person B superseding authorization for exact Person D runner HEAD", "runtime_authorization_mismatch", "scope")
    _require(
        document.get("record_purpose")
        == "External authorization record passed explicitly from the clean Person B checkout to D's loader",
        "runtime_authorization_mismatch",
        "record purpose",
    )
    _require(document.get("source_commit") == "external_person_b_package", "runtime_authorization_mismatch", "source")
    _require(document.get("scientific_execution_performed") is False and document.get("u4_output_inspected") is False, "runtime_authorization_mismatch", "safety")


def _validate_reuse_contract(document: Mapping[str, Any]) -> None:
    _require(document.get("reuse_permitted") is True, "reuse_contract_mismatch", "reuse permission")
    _require(document.get("materialized_root") == "/home/sagemaker-user/person-d-step4-1-approved-outputs/person-d-step4-1-materialized-inputs-v0-1", "reuse_contract_mismatch", "materialized root")
    _require(document.get("required_pilot_count") == 10, "reuse_contract_mismatch", "pilot count")
    _require(document.get("required_admitted_row_count") == 1695, "reuse_contract_mismatch", "row count")
    _require(document.get("frame_payload_count") == 1695, "reuse_contract_mismatch", "payload count")
    _require(document.get("frame_payload_revalidation_required") is True, "reuse_contract_mismatch", "payload revalidation")
    _require(document.get("frame_root") == FRAME_ROOT_ABSOLUTE_PATH, "reuse_contract_mismatch", "frame root")
    _require(tuple(document.get("accepted_pilot_ids", ())) == EXPECTED_PILOTS, "reuse_contract_mismatch", "pilots")
    _require(tuple(document.get("signed_explicit_mapping", ())) == EXPECTED_MAPPING, "reuse_contract_mismatch", "mapping")
    _require(document.get("zero_cross_fold_leakage") is True, "reuse_contract_mismatch", "leakage")
    _require(document.get("zero_duplicate_admitted_rows") is True, "reuse_contract_mismatch", "duplicate rows")
    _require(document.get("raw_sha256_and_byte_size_revalidation_required") is True, "reuse_contract_mismatch", "raw revalidation")
    _require(document.get("producing_git_authority_revalidation_required") is True, "reuse_contract_mismatch", "authority revalidation")
    _require(tuple(document.get("capture_package_source_commits", ())) == (PERSON_C_COMMIT,), "reuse_contract_mismatch", "capture authority")
    _require(document.get("validated_at_authorization_time") is False, "reuse_contract_mismatch", "validation claim")
    captures = document.get("capture_packages")
    _require(isinstance(captures, Sequence) and len(captures) == 10, "reuse_contract_mismatch", "capture package count")
    actual = tuple((c.get("trajectory_id"), c.get("path"), c.get("byte_size"), c.get("sha256"), c.get("source_commit")) for c in captures if isinstance(c, Mapping))
    expected = tuple((p, path, size, digest, PERSON_C_COMMIT) for p, path, size, digest in EXPECTED_CAPTURE_IDENTITIES)
    _require(actual == expected, "reuse_contract_mismatch", "capture identities")


def _validate_commands(commands: Mapping[str, Any]) -> None:
    reuse = commands.get("reuse_validation_command")
    preflight = commands.get("runtime_preflight_command")
    run = commands.get("production_run_command")
    fallback = commands.get("fallback_materialize_command")
    for label, command in (("reuse", reuse), ("preflight", preflight), ("run", run), ("fallback", fallback)):
        _require(isinstance(command, str) and command.strip(), "command_mismatch", f"{label} missing")
        _require(not re.search(r"<[^>]+>|\b(?:PLACEHOLDER|TODO)\b|\.\.\.", command), "command_mismatch", f"{label} placeholder")
        _require("u4" not in command.lower(), "u4_reference", f"{label} command")
    _require("reuse-validate" in reuse, "command_mismatch", "reuse mode")
    _require("runtime-preflight" in preflight, "command_mismatch", "preflight mode")
    _require("--json" in reuse and "--json" in preflight, "command_mismatch", "machine-readable gate output")
    _require("scripts/run_person_d_step4_1_eight_family_production.py run" in run, "command_mismatch", "D run mode")
    _require("scripts/run_person_d_step4_1_eight_family_production.py materialize" in fallback, "command_mismatch", "fallback mode")
    _require("--authorization-record-path" in run and "--authorization-record-path" in preflight, "command_mismatch", "authorization argument")
    _require(AUTH_RECORD_ABSOLUTE_PATH in run and AUTH_RECORD_ABSOLUTE_PATH in preflight and AUTH_RECORD_ABSOLUTE_PATH in fallback, "command_mismatch", "external authorization path")
    _require(f"--frame-root {FRAME_ROOT_ABSOLUTE_PATH}" in reuse, "command_mismatch", "reuse frame root")
    _require(f"--materialized-root {MATERIALIZED_ROOT_ABSOLUTE_PATH}" in reuse, "command_mismatch", "reuse materialized root")
    _require(f"--output-root {OUTPUT_ROOT_ABSOLUTE_PATH}" in preflight, "command_mismatch", "preflight output root")
    _require(f"--materialized-root {MATERIALIZED_ROOT_ABSOLUTE_PATH}" in preflight, "command_mismatch", "preflight materialized root")
    _require("--verify-payloads" in run, "command_mismatch", "payload argument")
    _require("--resume resume" in run, "command_mismatch", "resume argument")
    _require("--frame-manifest-path /home/sagemaker-user/person-d-step4-1-approved-outputs/person-d-step4-1-materialized-inputs-v0-1/preprocessed_frame_manifest.json" in run, "command_mismatch", "frame manifest")
    _require(f"--frame-root {FRAME_ROOT_ABSOLUTE_PATH}" in run, "command_mismatch", "frame root")
    _require(f"--fold-manifest-path {MATERIALIZED_ROOT_ABSOLUTE_PATH}/ten_pilot_frame_fold_manifest.json" in run, "command_mismatch", "fold manifest")
    _require(f"--target-manifest-path {MATERIALIZED_ROOT_ABSOLUTE_PATH}/production_oracle_target_manifest.json" in run, "command_mismatch", "target manifest")
    _require(f"--source-context-manifest-path {MATERIALIZED_ROOT_ABSOLUTE_PATH}/source_context_manifest.json" in run, "command_mismatch", "source context")
    _require(f"--source-context-root {MATERIALIZED_ROOT_ABSOLUTE_PATH}" in run, "command_mismatch", "source context root")
    _require("--analysis-config-path configs/analysis/core.yaml" in run, "command_mismatch", "analysis config")
    _require(f"--output-root {OUTPUT_ROOT_ABSOLUTE_PATH}" in run, "command_mismatch", "output root")
    _require(f"--materialize-root {MATERIALIZED_ROOT_ABSOLUTE_PATH}" in fallback, "command_mismatch", "materialize root")
    _require(commands.get("d_head_requirement") == PERSON_D_RUNNER_COMMIT, "command_mismatch", "D HEAD requirement")
    # The shell chain is part of the authorization boundary: reuse first,
    # then B's memory/D-worktree gate, then D run; fallback is separate.
    _require(reuse.find("&&") >= 0 and reuse.find("&&") < len(reuse), "command_mismatch", "reuse command chain")
    _require("&&" in commands.get("authorized_production_chain", ""), "command_mismatch", "authorized chain")
    chain = commands["authorized_production_chain"]
    reuse_index = chain.find("reuse-validate")
    preflight_index = chain.find("runtime-preflight")
    run_index = chain.find("scripts/run_person_d_step4_1_eight_family_production.py run")
    _require(0 <= reuse_index < preflight_index < run_index, "command_order_mismatch", "reuse, preflight, D run order")


def _validate_closure(repo_root: Path, document: Mapping[str, Any]) -> None:
    _require(document.get("person_b_post_d_comparison_required") is True, "closure_mismatch", "B comparison")
    _require(document.get("person_e_closure_required") is True, "closure_mismatch", "E closure")
    _require(document.get("final_comparison_complete") is False, "execution_claim_mismatch", "comparison")
    _require(document.get("step4_1_complete") is False, "execution_claim_mismatch", "Step 4.1")
    _require(document.get("u4_output_inspected") is False, "u4_reference", "closure U4")
    _require(document.get("required_family_receipts") == list(EXPECTED_FAMILIES), "closure_mismatch", "family receipts")
    e = document.get("person_e_handoff")
    _require(isinstance(e, Mapping), "closure_mismatch", "E handoff")
    _require(e.get("source_commit") == PERSON_E_COMMIT, "closure_mismatch", "E commit")
    _require(e.get("path") == "docs/status/person_e_phase6_to_step4_1_handoff_v0_1/person_e_closure_requirements.json", "closure_mismatch", "E path")
    raw = _git_blob(repo_root, PERSON_E_COMMIT, e["path"])
    _require(len(raw) == e.get("byte_size") and _sha256(raw) == e.get("sha256"), "closure_mismatch", "E identity")


def _validate_decision(document: Mapping[str, Any]) -> None:
    expected = {
        "previous_authorization_superseded": True,
        "baseline_family_count": 8,
        "preprocessed_frame_count": 1695,
        "minimum_available_memory_gib": 20.0,
        "minimum_detected_physical_memory_gib": 20.0,
        "person_b_predictions_are_d_direct_input": False,
        "person_d_execution_ready": True,
        "person_d_baseline_execution_performed": False,
        "final_b_vs_d_comparison_complete": False,
        "step4_1_complete": False,
        "u4_output_inspected": False,
    }
    for key, value in expected.items():
        _require(document.get(key) == value, "decision_mismatch", key)
    _require(document.get("authorized_person_d_head") == PERSON_D_RUNNER_COMMIT, "decision_mismatch", "D HEAD")
    _require(tuple(document.get("baseline_families", ())) == EXPECTED_FAMILIES, "decision_mismatch", "families")


def _validate_receipt(document: Mapping[str, Any]) -> None:
    _require(document.get("status") == "PASS_AUTHORIZATION_ISSUED_NO_EXECUTION", "receipt_mismatch", "status")
    for key in ("canonical_json_validated", "inventory_validated", "exact_git_authorities_validated", "memory_contract_validated", "payload_revalidation_contract_validated", "commands_validated", "reuse_contract_validated", "d_head_exact"):
        _require(document.get("checks", {}).get(key) is True, "receipt_mismatch", key)
    for key in ("scientific_execution_performed", "execution_performed", "final_comparison_complete", "step4_1_complete", "u4_output_inspected"):
        _require(document.get(key) is False, "receipt_mismatch", key)


def validate_package(repo_root: Path = ROOT, package_root: Path | None = None) -> Mapping[str, Any]:
    """Validate the complete additive package and its exact Git authorities."""

    repo_root = repo_root.resolve()
    package_root = (package_root or repo_root / PACKAGE_RELATIVE_PATH).resolve()
    documents = _load_documents(package_root)
    _validate_inventory(package_root, documents)
    _validate_safety_claims(documents)
    _validate_exact_git_objects(repo_root)
    _validate_authority(repo_root, documents["authority_binding.json"])
    _validate_incident(documents["incident_and_repair.json"])
    _validate_memory_contract(documents["memory_contract.json"])
    _validate_compatibility(repo_root, documents["compatibility_evidence.json"])
    _validate_external_auth(repo_root, documents["person_d_authorization_record.json"])
    _validate_reuse_contract(documents["materialized_input_reuse.json"])
    _validate_commands(documents["production_commands.json"])
    _validate_closure(repo_root, documents["output_closure_requirements.json"])
    _validate_decision(documents["final_authorization_decision.json"])
    _validate_receipt(documents["validation_receipt.json"])
    return {
        "accepted": True,
        "baseline_family_count": 8,
        "preprocessed_frame_count": 1695,
        "minimum_detected_physical_memory_gib": 20.0,
        "minimum_available_memory_gib": 20.0,
        "person_d_execution_ready": True,
        "person_d_baseline_execution_performed": False,
        "final_b_vs_d_comparison_complete": False,
        "step4_1_complete": False,
        "u4_output_inspected": False,
    }


def detect_linux_memory() -> dict[str, int | None]:
    """Read host and finite cgroup capacities without counting swap."""

    physical: int | None = None
    try:
        physical = int(os.sysconf("SC_PAGE_SIZE")) * int(os.sysconf("SC_PHYS_PAGES"))
    except (AttributeError, OSError, ValueError):
        pass
    available: int | None = None
    swap_total: int | None = None
    swap_free: int | None = None
    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        try:
            for line in meminfo.read_text(encoding="ascii").splitlines():
                parts = line.split()
                if len(parts) < 2 or not parts[1].isdigit():
                    continue
                value = int(parts[1]) * 1024
                if parts[0] == "MemAvailable:":
                    available = value
                elif parts[0] == "SwapTotal:":
                    swap_total = value
                elif parts[0] == "SwapFree:":
                    swap_free = value
        except (OSError, UnicodeError):
            pass
    cgroup_limit: int | None = None
    cgroup_usage: int | None = None
    cgroup_version: str | None = None
    # cgroup v2 is preferred when its unified files are present; v1 is the
    # fallback used by older SageMaker images.  A literal ``max`` means no
    # finite cgroup ceiling and therefore does not replace host detection.
    for version, limit_path, usage_path in (
        ("v2", Path("/sys/fs/cgroup/memory.max"), Path("/sys/fs/cgroup/memory.current")),
        ("v1", Path("/sys/fs/cgroup/memory/memory.limit_in_bytes"), Path("/sys/fs/cgroup/memory/memory.usage_in_bytes")),
    ):
        if not limit_path.is_file():
            continue
        try:
            limit_text = limit_path.read_text(encoding="ascii").strip()
            cgroup_version = version
            if limit_text != "max" and limit_text.isdigit():
                cgroup_limit = int(limit_text)
                if usage_path.is_file():
                    usage_text = usage_path.read_text(encoding="ascii").strip()
                    if usage_text.isdigit():
                        cgroup_usage = int(usage_text)
            break
        except (OSError, UnicodeError):
            cgroup_version = version
            break
    cgroup_available: int | None = None
    if cgroup_limit is not None and cgroup_usage is not None:
        cgroup_available = max(0, cgroup_limit - cgroup_usage)
    return {
        "physical_bytes": physical,
        "available_bytes": available,
        "swap_total_bytes": swap_total,
        "swap_free_bytes": swap_free,
        "cgroup_limit_bytes": cgroup_limit,
        "cgroup_usage_bytes": cgroup_usage,
        "cgroup_available_bytes": cgroup_available,
        "cgroup_version": cgroup_version,
    }


def validate_memory_gate(memory: Mapping[str, Any]) -> Mapping[str, Any]:
    """Require both exact host capacities; swap can only be reported."""

    physical = memory.get("physical_bytes")
    available = memory.get("available_bytes")
    _require(
        isinstance(physical, int) and not isinstance(physical, bool),
        "memory_physical_missing",
        "physical memory detection missing",
    )
    _require(
        isinstance(available, int) and not isinstance(available, bool),
        "memory_available_missing",
        "MemAvailable detection missing",
    )
    cgroup_limit = memory.get("cgroup_limit_bytes")
    cgroup_usage = memory.get("cgroup_usage_bytes")
    cgroup_available = memory.get("cgroup_available_bytes")
    if cgroup_limit is not None:
        _require(
            isinstance(cgroup_limit, int) and not isinstance(cgroup_limit, bool),
            "memory_cgroup_invalid",
            "cgroup limit is not numeric",
        )
        _require(cgroup_limit >= 0, "memory_cgroup_invalid", "cgroup limit is negative")
        _require(
            isinstance(cgroup_usage, int) and not isinstance(cgroup_usage, bool),
            "memory_cgroup_missing",
            "finite cgroup usage detection missing",
        )
        _require(cgroup_usage >= 0, "memory_cgroup_invalid", "cgroup usage is negative")
        if cgroup_available is None:
            cgroup_available = max(0, cgroup_limit - cgroup_usage)
        _require(
            isinstance(cgroup_available, int) and not isinstance(cgroup_available, bool),
            "memory_cgroup_invalid",
            "cgroup available is not numeric",
        )
        _require(cgroup_available >= 0, "memory_cgroup_invalid", "cgroup available is negative")
        _require(
            cgroup_available == max(0, cgroup_limit - cgroup_usage),
            "memory_cgroup_invalid",
            "cgroup available disagrees with limit and usage",
        )
        physical = min(physical, cgroup_limit)
        available = min(available, cgroup_available)
    else:
        _require(
            cgroup_available is None,
            "memory_cgroup_invalid",
            "cgroup available supplied without a finite limit",
        )
    _require(physical >= MINIMUM_PHYSICAL_MEMORY_BYTES, "memory_physical_low", f"{physical / BYTES_PER_GIB:.3f} GiB < 20.0 GiB")
    _require(available >= MINIMUM_AVAILABLE_MEMORY_BYTES, "memory_available_low", f"{available / BYTES_PER_GIB:.3f} GiB < 20.0 GiB")
    return {
        "physical_memory_bytes": physical,
        "available_memory_bytes": available,
        "physical_memory_gib": physical / BYTES_PER_GIB,
        "available_memory_gib": available / BYTES_PER_GIB,
        "swap_total_gib": (memory.get("swap_total_bytes") or 0) / BYTES_PER_GIB,
        "cgroup_limit_gib": (cgroup_limit / BYTES_PER_GIB) if isinstance(cgroup_limit, int) else None,
        "cgroup_available_gib": (cgroup_available / BYTES_PER_GIB) if isinstance(cgroup_available, int) else None,
        "swap_counted_as_capacity": False,
        "minimum_physical_memory_gib": MINIMUM_PHYSICAL_MEMORY_GIB,
        "minimum_available_memory_gib": MINIMUM_AVAILABLE_MEMORY_GIB,
        "minimum_physical_memory_bytes": MINIMUM_PHYSICAL_MEMORY_BYTES,
        "minimum_available_memory_bytes": MINIMUM_AVAILABLE_MEMORY_BYTES,
        "passed": True,
    }


# Familiar names for focused callers/tests; both aliases retain the strict
# two-threshold semantics above.
detect_host_memory = detect_linux_memory
validate_runtime_memory = validate_memory_gate


def validate_d_checkout(d_checkout: Path, *, repo_root: Path = ROOT) -> Mapping[str, Any]:
    """Require D's independent checkout to be clean and exactly authorized."""

    d_checkout = d_checkout.resolve()
    _require(d_checkout.is_dir(), "d_checkout_missing", str(d_checkout))
    branch = _git_text(d_checkout, "branch", "--show-current")
    head = _git_text(d_checkout, "rev-parse", "HEAD")
    dirty = bool(_git_text(d_checkout, "status", "--porcelain"))
    _require(branch == PERSON_D_BRANCH, "d_wrong_branch", branch)
    _require(head == PERSON_D_RUNNER_COMMIT, "d_wrong_head", head)
    _require(not dirty, "d_dirty_worktree", str(d_checkout))
    _require(_git_text(d_checkout, "cat-file", "-t", PERSON_D_RUNNER_COMMIT) == "commit", "d_head_missing", PERSON_D_RUNNER_COMMIT)
    return {"branch": branch, "head": head, "dirty": dirty, "passed": True}


def _safe_output_path(output_root: Path, relative_path: Any) -> Path:
    _require(isinstance(relative_path, str) and relative_path, "resume_output_path_invalid", "missing output_path")
    candidate = Path(relative_path)
    _require(not candidate.is_absolute(), "resume_output_path_unsafe", relative_path)
    resolved_root = output_root.resolve()
    resolved = (output_root / candidate).resolve()
    _require(resolved == resolved_root or resolved_root in resolved.parents, "resume_output_path_unsafe", relative_path)
    _require(resolved.suffix == ".json" and resolved.name != "run_state.json", "resume_output_path_invalid", relative_path)
    return resolved


def _load_resume_lineage(
    repo_root: Path,
    materialized_root: Path | None,
) -> tuple[dict[tuple[str, int], dict[str, Any]], dict[tuple[str, int], int]]:
    """Load the exact target/fold identities used to validate resume output.

    A completed output is reusable only when its row keys and fold assignments
    are a subset-exact match for the frozen manifests.  When a materialized
    root is supplied, its fold and target bytes are checked against the frozen
    Git objects before parsing; otherwise the Git objects are read directly.
    """

    def load_artifact(
        *,
        label: str,
        commit: str,
        path: str,
        digest: str,
        size: int,
        local_name: str,
    ) -> Mapping[str, Any]:
        if materialized_root is not None:
            local = materialized_root.resolve() / local_name
            _require(local.is_file(), "resume_manifest_missing", str(local))
            raw = local.read_bytes()
            _require(
                len(raw) == size and _sha256(raw) == digest,
                "resume_manifest_identity_mismatch",
                label,
            )
        else:
            raw = _git_blob(repo_root, commit, path)
            _require(
                len(raw) == size and _sha256(raw) == digest,
                "resume_manifest_identity_mismatch",
                label,
            )
        return _parse_bytes(raw, label)

    target = load_artifact(
        label="resume target manifest",
        commit=PERSON_B_PRODUCTION_COMMIT,
        path=TARGET_MANIFEST_PATH,
        digest=TARGET_MANIFEST_SHA256,
        size=TARGET_MANIFEST_SIZE,
        local_name="production_oracle_target_manifest.json",
    )
    fold = load_artifact(
        label="resume fold manifest",
        commit=PERSON_B_PRODUCTION_COMMIT,
        path=FOLD_MANIFEST_PATH,
        digest=FOLD_MANIFEST_SHA256,
        size=FOLD_MANIFEST_SIZE,
        local_name="ten_pilot_frame_fold_manifest.json",
    )
    target_rows = target.get("rows")
    fold_rows = fold.get("memberships")
    _require(
        isinstance(target_rows, list) and len(target_rows) == 1695,
        "resume_manifest_lineage_invalid",
        "target rows",
    )
    _require(
        isinstance(fold_rows, list) and len(fold_rows) == 1695,
        "resume_manifest_lineage_invalid",
        "fold rows",
    )

    target_by_key: dict[tuple[str, int], dict[str, Any]] = {}
    for row in target_rows:
        _require(isinstance(row, Mapping), "resume_manifest_lineage_invalid", "target row")
        trajectory = row.get("trajectory_id")
        frame_idx = row.get("model_frame_idx")
        _require(
            trajectory in EXPECTED_PILOTS
            and isinstance(frame_idx, int)
            and not isinstance(frame_idx, bool)
            and isinstance(row.get("fold_idx"), int)
            and not isinstance(row.get("fold_idx"), bool),
            "resume_manifest_lineage_invalid",
            "target row identity",
        )
        key = (trajectory, frame_idx)
        _require(key not in target_by_key, "resume_manifest_lineage_invalid", "duplicate target key")
        target_by_key[key] = {
            "condition_role": row.get("condition_role"),
            "fold_idx": row["fold_idx"],
            "mu_available": row.get("mu_oracle_blocks") is not None,
            "log_sigma_available": row.get("log_sigma_oracle") is not None,
            "visibility": row.get("visibility"),
        }

    fold_by_key: dict[tuple[str, int], int] = {}
    for row in fold_rows:
        _require(isinstance(row, Mapping), "resume_manifest_lineage_invalid", "fold row")
        trajectory = row.get("trajectory_id")
        frame_idx = row.get("model_frame_idx")
        fold_idx = row.get("fold_idx")
        _require(
            trajectory in EXPECTED_PILOTS
            and isinstance(frame_idx, int)
            and not isinstance(frame_idx, bool)
            and isinstance(fold_idx, int)
            and not isinstance(fold_idx, bool)
            and fold_idx in range(5),
            "resume_manifest_lineage_invalid",
            "fold row identity",
        )
        key = (trajectory, frame_idx)
        _require(key not in fold_by_key, "resume_manifest_lineage_invalid", "duplicate fold key")
        fold_by_key[key] = fold_idx

    _require(
        set(target_by_key) == set(fold_by_key) and len(target_by_key) == 1695,
        "resume_manifest_lineage_invalid",
        "target/fold identity join",
    )
    for key, target_row in target_by_key.items():
        _require(
            target_row["fold_idx"] == fold_by_key[key],
            "resume_manifest_lineage_invalid",
            "target/fold fold assignment",
        )
    return target_by_key, fold_by_key


def _expand_identity_set(
    set_name: str, specification: Any
) -> set[tuple[str, int]]:
    """Expand one compact, exact trajectory/frame-range identity set."""

    _require(isinstance(specification, Mapping), "applicability_set_invalid", set_name)
    _require(
        set(specification) == {"expected_count", "identity_sha256", "ranges"},
        "applicability_set_invalid",
        f"{set_name}.fields",
    )
    ranges = specification.get("ranges")
    _require(isinstance(ranges, list), "applicability_set_invalid", f"{set_name}.ranges")
    ordered: list[dict[str, Any]] = []
    identities: set[tuple[str, int]] = set()
    pilot_order = {pilot: index for index, pilot in enumerate(EXPECTED_PILOTS)}
    previous_order: tuple[int, int] | None = None
    for item in ranges:
        _require(
            isinstance(item, list) and len(item) == 3,
            "applicability_set_invalid",
            f"{set_name}.range",
        )
        trajectory, start, end = item
        _require(
            trajectory in pilot_order
            and isinstance(start, int)
            and not isinstance(start, bool)
            and isinstance(end, int)
            and not isinstance(end, bool)
            and 0 <= start <= end,
            "applicability_set_invalid",
            f"{set_name}.range_values",
        )
        current_order = (pilot_order[trajectory], start)
        _require(
            previous_order is None or current_order > previous_order,
            "applicability_set_invalid",
            f"{set_name}.range_order",
        )
        previous_order = current_order
        for frame_idx in range(start, end + 1):
            key = (trajectory, frame_idx)
            _require(
                key not in identities,
                "applicability_set_invalid",
                f"{set_name}.duplicate_identity",
            )
            identities.add(key)
            ordered.append(
                {"model_frame_idx": frame_idx, "trajectory_id": trajectory}
            )
    _require(
        specification.get("expected_count") == len(identities),
        "applicability_set_count_mismatch",
        set_name,
    )
    _require(
        specification.get("identity_sha256") == _sha256(canonical_json_bytes(ordered)),
        "applicability_set_hash_mismatch",
        set_name,
    )
    return identities


def validate_applicability_contract(
    document: Any,
    target_by_key: Mapping[tuple[str, int], Mapping[str, Any]],
    fold_by_key: Mapping[tuple[str, int], int],
    *,
    repo_root: Path = ROOT,
) -> Mapping[str, Any]:
    """Validate and expand the frozen family-by-target applicability contract.

    The independent expected sets below are derived only from the frozen target
    and fold manifests plus the exact scientific rules at the authorized D Git
    objects.  No prediction output participates in this derivation.
    """

    _require(isinstance(document, Mapping), "applicability_contract_invalid", "document")
    _require(
        document.get("contract_version") == APPLICABILITY_CONTRACT_VERSION,
        "applicability_contract_version_unknown",
        str(document.get("contract_version")),
    )
    _require(
        document.get("schema_id")
        == "person-b-phase4-step4-1-family-target-applicability-contract-v0-1"
        and document.get("schema_version") == "1.0",
        "applicability_contract_invalid",
        "schema",
    )
    _require(
        document.get("identity_encoding")
        == "ordered_trajectory_inclusive_frame_ranges_v1",
        "applicability_contract_invalid",
        "identity_encoding",
    )
    _require(
        tuple(document.get("ordered_families", ())) == EXPECTED_FAMILIES,
        "applicability_contract_invalid",
        "family order",
    )
    _require(
        document.get("producing_runner_commit") == PERSON_D_RUNNER_COMMIT,
        "applicability_contract_invalid",
        "runner authority",
    )
    _require(
        document.get("global_candidate_count") == 1695,
        "applicability_contract_invalid",
        "global candidate count",
    )
    _require(
        document.get("u4_output_inspected") is False,
        "u4_reference",
        "applicability contract",
    )

    reason_vocabulary = document.get("exclusion_reason_vocabulary")
    expected_reasons = {
        "missing_prior_visible_observation_for_estimated_velocity",
        "seeded_donor_missing_target_at_explicit_model_frame_idx",
        "target_visible_no_log_sigma_oracle",
    }
    _require(
        isinstance(reason_vocabulary, Mapping)
        and set(reason_vocabulary) == expected_reasons
        and all(isinstance(value, str) and value for value in reason_vocabulary.values()),
        "applicability_exclusion_reason_unknown",
        "reason vocabulary",
    )

    raw_sets = document.get("identity_sets")
    _require(isinstance(raw_sets, Mapping), "applicability_contract_invalid", "identity sets")
    expanded = {
        name: _expand_identity_set(name, specification)
        for name, specification in raw_sets.items()
    }
    expected_set_names = {
        "empty",
        "estimated_velocity_admitted_1690",
        "estimated_velocity_excluded_5",
        "global_candidate_1695",
        "grouped_shuffled_log_sigma_admitted_493",
        "grouped_shuffled_log_sigma_excluded_1202",
        "grouped_shuffled_mu_admitted_1428",
        "grouped_shuffled_mu_excluded_267",
        "hidden_target_admitted_695",
        "visible_target_excluded_1000",
    }
    _require(
        set(expanded) == expected_set_names,
        "applicability_contract_invalid",
        "identity set names",
    )

    global_candidates = set(target_by_key)
    _require(
        global_candidates == set(fold_by_key)
        and len(global_candidates) == 1695
        and expanded["global_candidate_1695"] == global_candidates,
        "applicability_global_identity_mismatch",
        "target/fold/global candidate identities",
    )
    exact_velocity_exclusions = {
        ("layout_00_ep9441", 0),
        ("layout_01_ep9442", 0),
        ("layout_02_ep9432", 0),
        ("layout_03_ep9443", 0),
        ("layout_04_ep9444", 0),
    }
    for key in exact_velocity_exclusions:
        row = target_by_key.get(key, {})
        _require(
            row.get("condition_role") == "no_wall_visible_control"
            and row.get("visibility") == "visible"
            and row.get("mu_available") is True,
            "applicability_velocity_exclusion_mismatch",
            str(key),
        )
    velocity_admitted = global_candidates - exact_velocity_exclusions
    hidden_admitted = {
        key for key, row in target_by_key.items() if row.get("log_sigma_available") is True
    }
    mu_available = {
        key for key, row in target_by_key.items() if row.get("mu_available") is True
    }
    _require(
        mu_available == global_candidates and len(hidden_admitted) == 695,
        "applicability_target_binding_mismatch",
        "frozen target availability",
    )
    grouped_mu = {
        key
        for key in global_candidates
        if (EXPECTED_GROUPED_SHUFFLE_DONORS[key[0]], key[1]) in mu_available
    }
    grouped_log_sigma = {
        key
        for key in global_candidates
        if (EXPECTED_GROUPED_SHUFFLE_DONORS[key[0]], key[1]) in hidden_admitted
    }
    expected_sets = {
        "empty": set(),
        "estimated_velocity_admitted_1690": velocity_admitted,
        "estimated_velocity_excluded_5": exact_velocity_exclusions,
        "global_candidate_1695": global_candidates,
        "grouped_shuffled_log_sigma_admitted_493": grouped_log_sigma,
        "grouped_shuffled_log_sigma_excluded_1202": global_candidates - grouped_log_sigma,
        "grouped_shuffled_mu_admitted_1428": grouped_mu,
        "grouped_shuffled_mu_excluded_267": global_candidates - grouped_mu,
        "hidden_target_admitted_695": hidden_admitted,
        "visible_target_excluded_1000": global_candidates - hidden_admitted,
    }
    for name, expected in expected_sets.items():
        _require(
            expanded[name] == expected,
            "applicability_identity_set_mismatch",
            name,
        )

    entries = document.get("applicability_entries")
    expected_pairs = tuple(
        (family, target)
        for family in EXPECTED_FAMILIES
        for target in EXPECTED_RESUME_TARGET_FAMILIES[family]
    )
    _require(
        isinstance(entries, list)
        and document.get("applicability_entry_count") == len(expected_pairs)
        and tuple(
            (entry.get("family"), entry.get("target"))
            for entry in entries
            if isinstance(entry, Mapping)
        )
        == expected_pairs,
        "applicability_entry_coverage_mismatch",
        "family-target entries",
    )
    expected_admitted_names = {
        ("last_seen", "mu_oracle_blocks"): "global_candidate_1695",
        ("constant_velocity", "mu_oracle_blocks"): "estimated_velocity_admitted_1690",
        ("grouped_shuffled", "log_sigma_oracle"): "grouped_shuffled_log_sigma_admitted_493",
        ("grouped_shuffled", "mu_oracle_blocks"): "grouped_shuffled_mu_admitted_1428",
        ("time_only", "log_sigma_oracle"): "hidden_target_admitted_695",
        ("explicit_feature", "mu_oracle_blocks"): "estimated_velocity_admitted_1690",
        ("raw_pixel", "mu_oracle_blocks"): "global_candidate_1695",
        ("visible_history_q", "log_sigma_oracle"): "hidden_target_admitted_695",
        ("known_q_analytic", "log_sigma_oracle"): "hidden_target_admitted_695",
    }
    expected_excluded_names = {
        ("last_seen", "mu_oracle_blocks"): "empty",
        ("constant_velocity", "mu_oracle_blocks"): "estimated_velocity_excluded_5",
        ("grouped_shuffled", "log_sigma_oracle"): "grouped_shuffled_log_sigma_excluded_1202",
        ("grouped_shuffled", "mu_oracle_blocks"): "grouped_shuffled_mu_excluded_267",
        ("time_only", "log_sigma_oracle"): "visible_target_excluded_1000",
        ("explicit_feature", "mu_oracle_blocks"): "estimated_velocity_excluded_5",
        ("raw_pixel", "mu_oracle_blocks"): "empty",
        ("visible_history_q", "log_sigma_oracle"): "visible_target_excluded_1000",
        ("known_q_analytic", "log_sigma_oracle"): "visible_target_excluded_1000",
    }
    expected_reason_by_excluded_set = {
        "empty": [],
        "estimated_velocity_excluded_5": [
            "missing_prior_visible_observation_for_estimated_velocity"
        ],
        "grouped_shuffled_log_sigma_excluded_1202": [
            "seeded_donor_missing_target_at_explicit_model_frame_idx"
        ],
        "grouped_shuffled_mu_excluded_267": [
            "seeded_donor_missing_target_at_explicit_model_frame_idx"
        ],
        "visible_target_excluded_1000": ["target_visible_no_log_sigma_oracle"],
    }
    by_pair: dict[tuple[str, str], Mapping[str, Any]] = {}
    for entry in entries:
        _require(isinstance(entry, Mapping), "applicability_contract_invalid", "entry")
        pair = (entry.get("family"), entry.get("target"))
        family, _target = pair
        admitted_name = expected_admitted_names[pair]
        excluded_name = expected_excluded_names[pair]
        admitted = expanded[admitted_name]
        excluded = expanded[excluded_name]
        _require(
            entry.get("candidate_identity_set") == "global_candidate_1695"
            and entry.get("admitted_identity_set") == admitted_name
            and entry.get("excluded_identity_set") == excluded_name
            and entry.get("expected_admitted_row_count") == len(admitted)
            and entry.get("expected_excluded_row_count") == len(excluded)
            and admitted.isdisjoint(excluded)
            and admitted | excluded == global_candidates,
            "applicability_entry_identity_mismatch",
            f"{family}/{_target}",
        )
        reasons = entry.get("exclusion_reasons")
        _require(
            reasons == expected_reason_by_excluded_set[excluded_name]
            and set(reasons).issubset(expected_reasons),
            "applicability_exclusion_reason_unknown",
            f"{family}/{_target}",
        )
        _require(
            entry.get("configuration") == EXPECTED_CONFIGURATION[family],
            "applicability_configuration_mismatch",
            str(family),
        )
        _require(
            entry.get("fold_binding")
            == {
                "sha256": FOLD_MANIFEST_SHA256,
                "validation_mode": "signed_explicit_mapping",
            },
            "applicability_fold_binding_mismatch",
            f"{family}/{_target}",
        )
        target_binding = entry.get("target_binding")
        _require(
            isinstance(target_binding, Mapping)
            and target_binding.get("sha256") == TARGET_MANIFEST_SHA256
            and isinstance(target_binding.get("availability_rule"), str)
            and bool(target_binding.get("availability_rule")),
            "applicability_target_binding_mismatch",
            f"{family}/{_target}",
        )
        _require(
            isinstance(entry.get("history_visibility_requirements"), str)
            and bool(entry.get("history_visibility_requirements")),
            "applicability_history_requirement_missing",
            f"{family}/{_target}",
        )
        _require(
            entry.get("validation_rule")
            == "actual prediction identities must equal the referenced admitted identity set",
            "applicability_validation_rule_mismatch",
            f"{family}/{_target}",
        )
        authority = entry.get("producing_scientific_authority")
        _require(
            isinstance(authority, Mapping)
            and set(authority) == {"commit", "path", "sha256"}
            and authority.get("commit") == PERSON_D_RUNNER_COMMIT,
            "applicability_scientific_authority_mismatch",
            f"{family}/{_target}",
        )
        source_path = authority.get("path")
        _require(
            isinstance(source_path, str)
            and _sha256(_git_blob(repo_root, PERSON_D_RUNNER_COMMIT, source_path))
            == authority.get("sha256"),
            "applicability_scientific_authority_mismatch",
            f"{family}/{_target}.source",
        )
        by_pair[pair] = entry
    return {
        "contract_version": APPLICABILITY_CONTRACT_VERSION,
        "entries": by_pair,
        "identity_sets": expanded,
        "global_candidate_count": len(global_candidates),
    }


def load_applicability_contract(
    target_by_key: Mapping[tuple[str, int], Mapping[str, Any]],
    fold_by_key: Mapping[tuple[str, int], int],
    *,
    repo_root: Path = ROOT,
) -> Mapping[str, Any]:
    path = repo_root / APPLICABILITY_CONTRACT_RELATIVE_PATH
    document = _parse_path(path, "family-target applicability contract")
    return validate_applicability_contract(
        document, target_by_key, fold_by_key, repo_root=repo_root
    )


def _expected_resume_keys(
    family: str,
    target_name: str,
    target_by_key: Mapping[tuple[str, int], Mapping[str, Any]],
    fold_by_key: Mapping[tuple[str, int], int] | None = None,
    *,
    repo_root: Path = ROOT,
) -> set[tuple[str, int]]:
    """Return the exact applicable row keys for one frozen D output."""

    _require(
        family in EXPECTED_RESUME_TARGET_FAMILIES
        and target_name in EXPECTED_RESUME_TARGET_FAMILIES[family],
        "applicability_family_target_unknown",
        f"{family}/{target_name}",
    )
    if fold_by_key is None:
        fold_by_key = {key: int(row["fold_idx"]) for key, row in target_by_key.items()}
    contract = load_applicability_contract(
        target_by_key, fold_by_key, repo_root=repo_root
    )
    entry = contract["entries"][(family, target_name)]
    return set(contract["identity_sets"][entry["admitted_identity_set"]])


def _validate_resume_prediction_document(
    *,
    family: str,
    target_name: str,
    path: Path,
    target_by_key: Mapping[tuple[str, int], Mapping[str, Any]],
    fold_by_key: Mapping[tuple[str, int], int],
    repo_root: Path,
) -> Mapping[str, Any]:
    """Validate one preserved prediction file against its exact admitted set."""

    raw = path.read_bytes()
    document = _parse_bytes(
        raw, f"resume output {family}/{target_name}", canonical=False
    )
    _require(document.get("schema_version") == "1.0", "resume_schema_mismatch", family)
    _require(
        document.get("baseline_input_schema_version")
        == "person-b-baseline-input-v0.2",
        "resume_schema_mismatch",
        family,
    )
    _require(
        document.get("baseline_id") == f"{family}_v1",
        "resume_family_mismatch",
        family,
    )
    _require(
        document.get("producer_role") == "person_d",
        "resume_lineage_mismatch",
        f"{family}.producer_role",
    )
    _require(
        document.get("baseline_family") == family,
        "resume_family_mismatch",
        family,
    )
    _require(
        document.get("target_name") == target_name,
        "resume_target_mismatch",
        family,
    )
    _require(
        document.get("config_hash") == ANALYSIS_CONFIG_SHA256,
        "resume_config_mismatch",
        family,
    )
    _require(
        document.get("fold_manifest_hash") == FOLD_MANIFEST_SHA256,
        "resume_fold_hash_mismatch",
        family,
    )
    _require(
        tuple(document.get("accepted_pilot_ids", ())) == EXPECTED_PILOTS,
        "resume_pilot_mismatch",
        family,
    )
    _require(document.get("random_split_used") is False, "resume_split_mismatch", family)
    _require(document.get("u4_output_inspected") is False, "u4_reference", family)
    _require(
        document.get("person_b_prediction_reservation")
        == EXPECTED_PERSON_B_PREDICTION_RESERVATION,
        "resume_prediction_boundary_mismatch",
        family,
    )
    expected_direct_inputs = {
        "analysis_config": {
            "path": ANALYSIS_CONFIG_PATH,
            "sha256": ANALYSIS_CONFIG_SHA256,
            "byte_size": ANALYSIS_CONFIG_SIZE,
            "producer_role": "person_b",
        },
        "fold_manifest": {
            "path": FOLD_MANIFEST_PATH,
            "sha256": FOLD_MANIFEST_SHA256,
            "byte_size": FOLD_MANIFEST_SIZE,
            "producer_role": "person_b",
        },
        "oracle_target": {
            "path": TARGET_MANIFEST_PATH,
            "sha256": TARGET_MANIFEST_SHA256,
            "byte_size": TARGET_MANIFEST_SIZE,
            "producer_role": "person_b",
        },
        "source_context_manifest": {
            "path": SOURCE_CONTEXT_MANIFEST_PATH,
            "sha256": SOURCE_CONTEXT_SHA256,
            "byte_size": SOURCE_CONTEXT_SIZE,
            "producer_role": "person_b",
        },
    }
    direct_inputs = document.get("direct_inputs")
    _require(isinstance(direct_inputs, Mapping), "resume_input_lineage_missing", family)
    required_input_keys = set(expected_direct_inputs)
    if family == "raw_pixel":
        required_input_keys.add("preprocessed_frame_manifest")
    _require(
        set(direct_inputs) == required_input_keys,
        "resume_input_lineage_mismatch",
        f"{family}.direct_inputs",
    )
    for key, expected in expected_direct_inputs.items():
        _require(
            direct_inputs.get(key) == expected,
            "resume_input_lineage_mismatch",
            f"{family}.{key}",
        )
    if family == "raw_pixel":
        _require(
            direct_inputs.get("preprocessed_frame_manifest")
            == {
                "path": FRAME_MANIFEST_PATH,
                "sha256": FRAME_MANIFEST_SHA256,
                "byte_size": FRAME_MANIFEST_SIZE,
            },
            "resume_frame_lineage_mismatch",
            family,
        )
    _require(
        document.get("input_manifest_hash") == EXPECTED_INPUT_MANIFEST_HASH,
        "resume_input_hash_mismatch",
        family,
    )
    _require(
        document.get("fit_manifest_hash") == EXPECTED_FIT_MANIFEST_HASH,
        "resume_fit_hash_mismatch",
        family,
    )
    rows = document.get("rows")
    _require(isinstance(rows, list), "resume_row_lineage_mismatch", family)
    applicability = load_applicability_contract(
        target_by_key, fold_by_key, repo_root=repo_root
    )
    applicability_entry = applicability["entries"][(family, target_name)]
    expected_keys = set(
        applicability["identity_sets"][
            applicability_entry["admitted_identity_set"]
        ]
    )
    actual_keys: set[tuple[str, int]] = set()
    for row in rows:
        _require(isinstance(row, Mapping), "resume_row_lineage_mismatch", family)
        trajectory = row.get("trajectory_id")
        frame_idx = row.get("model_frame_idx")
        fold_idx = row.get("fold_idx")
        _require(
            trajectory in EXPECTED_PILOTS
            and isinstance(frame_idx, int)
            and not isinstance(frame_idx, bool)
            and isinstance(fold_idx, int)
            and not isinstance(fold_idx, bool),
            "resume_row_lineage_mismatch",
            family,
        )
        key = (trajectory, frame_idx)
        _require(key not in actual_keys, "resume_duplicate_row", family)
        actual_keys.add(key)
        _require(
            fold_by_key.get(key) == fold_idx,
            "resume_fold_lineage_mismatch",
            family,
        )
        _require(
            row.get("prediction_scope") == "out_of_fold",
            "resume_row_lineage_mismatch",
            family,
        )
        _require(
            row.get("fit_id") == f"{family}:{target_name}:v0_2",
            "resume_fit_lineage_mismatch",
            family,
        )
        prediction = row.get("prediction")
        _require(
            isinstance(prediction, (int, float))
            and not isinstance(prediction, bool)
            and math.isfinite(prediction),
            "resume_prediction_invalid",
            family,
        )
    extras = actual_keys - expected_keys
    missing = expected_keys - actual_keys
    _require(
        not extras,
        "resume_unauthorized_extra_identity",
        f"{family}/{target_name}:{sorted(extras)[:3]}",
    )
    _require(
        not missing,
        "resume_missing_admitted_identity",
        f"{family}/{target_name}:{sorted(missing)[:3]}",
    )
    _require(
        len(rows) == len(expected_keys),
        "resume_row_count_mismatch",
        f"{family}/{target_name}",
    )
    _require(
        raw == canonical_json_bytes(document),
        "noncanonical_json",
        f"resume output {family}/{target_name}",
    )
    return {
        "byte_size": len(raw),
        "family": family,
        "identity_set_sha256": _sha256(
            canonical_json_bytes(
                [
                    {"model_frame_idx": frame_idx, "trajectory_id": trajectory}
                    for trajectory, frame_idx in sorted(
                        actual_keys,
                        key=lambda key: (EXPECTED_PILOTS.index(key[0]), key[1]),
                    )
                ]
            )
        ),
        "path": path.name,
        "producing_scientific_authority": dict(
            applicability_entry["producing_scientific_authority"]
        ),
        "row_count": len(rows),
        "sha256": _sha256(raw),
        "target": target_name,
    }


def validate_output_resume_state(
    output_root: Path,
    *,
    materialized_root: Path | None = None,
    repo_root: Path = ROOT,
) -> Mapping[str, Any]:
    """Reject unsafe, stale, or cross-input completed D resume entries.

    D's own resume planner verifies an output document but does not constrain
    the recorded path to the approved root or bind its lineage to the current
    input set.  This B gate performs those checks before D is launched.  An
    absent state file is a valid first run; every existing completed entry is
    checked fail-closed.
    """

    output_root = output_root.resolve()
    state_path = output_root / "run_state.json"
    if not state_path.exists():
        stray = sorted(
            path.name
            for path in output_root.glob("*__*.json")
            if path.is_file()
        ) if output_root.is_dir() else []
        _require(
            not stray and not (output_root / PRESERVED_PROVENANCE_FILENAME).exists(),
            "resume_invalid_conflicting",
            f"outputs exist without run_state: {stray[:3]}",
        )
        return {
            "checked": False,
            "completed_families": [],
            "completed_family_count": 0,
            "decisions": {family: "absent" for family in EXPECTED_FAMILIES},
            "direct_output_validation_required": True,
            "no_u4_input": True,
            "passed": True,
            "prediction_count": 0,
        }
    state_raw = state_path.read_bytes()
    state = _parse_bytes(state_raw, "D run_state", canonical=False)
    _require(
        set(state) == {"families", "schema_version"}
        and state.get("schema_version") == "1.0",
        "resume_state_invalid",
        "schema",
    )
    families = state.get("families")
    _require(isinstance(families, Mapping), "resume_state_invalid", "families")
    unknown = set(families) - set(EXPECTED_FAMILIES)
    _require(not unknown, "resume_unknown_family", ",".join(sorted(unknown)))
    # The manifests are loaded only when a completed output must be checked;
    # a fresh run with no run_state remains a constant-time no-op.
    target_by_key, fold_by_key = _load_resume_lineage(repo_root.resolve(), materialized_root)
    decisions: dict[str, str] = {family: "absent" for family in EXPECTED_FAMILIES}
    completed_families: list[str] = []
    inventory: list[Mapping[str, Any]] = []
    expected_prediction_paths: set[str] = set()
    for family in EXPECTED_FAMILIES:
        record = families.get(family)
        expected_targets = EXPECTED_RESUME_TARGET_FAMILIES[family]
        family_paths = {
            f"{family}__{target_name}.json" for target_name in expected_targets
        }
        present_paths = {
            path.name for path in output_root.glob(f"{family}__*.json") if path.is_file()
        }
        if record is None:
            _require(
                not present_paths,
                "resume_invalid_conflicting",
                f"{family}: outputs exist without completed run_state entry",
            )
            continue
        _require(isinstance(record, Mapping), "resume_state_invalid", family)
        _require(record.get("status") in {"completed", "failed"}, "resume_state_invalid", family)
        if record.get("status") != "completed":
            _require(
                not present_paths,
                "resume_invalid_conflicting",
                f"{family}: outputs exist for failed run_state entry",
            )
            continue
        completed_families.append(family)
        decisions[family] = "reusable"
        expected_prediction_paths.update(family_paths)
        recorded_path = _safe_output_path(output_root, record.get("output_path"))
        _require(
            present_paths == family_paths,
            "resume_output_inventory_mismatch",
            family,
        )
        _require(
            record.get("targets") == sorted(expected_targets),
            "resume_state_invalid",
            f"{family}.targets",
        )
        expected_recorded_path = output_root / f"{family}__{min(expected_targets)}.json"
        _require(
            recorded_path == expected_recorded_path,
            "resume_output_path_mismatch",
            family,
        )
        for target_name in expected_targets:
            path = _safe_output_path(
                output_root, f"{family}__{target_name}.json"
            )
            _require(path.is_file(), "resume_output_missing", str(path))
            inventory.append(
                _validate_resume_prediction_document(
                    family=family,
                    target_name=target_name,
                    path=path,
                    target_by_key=target_by_key,
                    fold_by_key=fold_by_key,
                    repo_root=repo_root,
                )
            )
    actual_prediction_paths = {
        path.name for path in output_root.glob("*__*.json") if path.is_file()
    }
    _require(
        actual_prediction_paths == expected_prediction_paths,
        "resume_output_inventory_mismatch",
        "unexpected prediction files",
    )
    state_reference = {
        "byte_size": len(state_raw),
        "path": "run_state.json",
        "sha256": _sha256(state_raw),
    }
    inventory_by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in inventory:
        inventory_by_family[str(item["family"])].append(dict(item))
    family_evidence: dict[str, Mapping[str, Any]] = {}
    for family in completed_families:
        family_inventory = sorted(
            inventory_by_family[family], key=lambda item: str(item["target"])
        )
        family_evidence[family] = {
            "audit_decision": "reusable",
            "configuration": EXPECTED_CONFIGURATION[family],
            "exact_prediction_count": sum(
                int(item["row_count"]) for item in family_inventory
            ),
            "identity_set_sha256_by_target": {
                str(item["target"]): item["identity_set_sha256"]
                for item in family_inventory
            },
            "output_manifest": {
                "family_status": "completed",
                "run_state": state_reference,
                "targets": sorted(EXPECTED_RESUME_TARGET_FAMILIES[family]),
            },
            "prediction_inventory": family_inventory,
            "prediction_inventory_sha256": _sha256(
                canonical_json_bytes(family_inventory)
            ),
        }
    total_predictions = sum(int(item["row_count"]) for item in inventory)
    contract_path = repo_root / APPLICABILITY_CONTRACT_RELATIVE_PATH
    return {
        "checked": True,
        "applicability_contract": {
            "path": APPLICABILITY_CONTRACT_RELATIVE_PATH.as_posix(),
            "sha256": _sha256(contract_path.read_bytes()),
            "version": APPLICABILITY_CONTRACT_VERSION,
        },
        "completed_families": completed_families,
        "completed_family_count": len(completed_families),
        "decisions": decisions,
        "direct_output_validation_required": True,
        "family_evidence": family_evidence,
        "fold_manifest_sha256": FOLD_MANIFEST_SHA256,
        "frame_manifest_sha256": FRAME_MANIFEST_SHA256,
        "no_u4_input": True,
        "output_manifest": state_reference,
        "output_inventory": inventory,
        "passed": True,
        "prediction_count": total_predictions,
        "source_context_manifest_sha256": SOURCE_CONTEXT_SHA256,
        "target_manifest_sha256": TARGET_MANIFEST_SHA256,
    }


def _validate_audit_environment_receipt(receipt: Any) -> None:
    _require(
        isinstance(receipt, Mapping)
        and set(receipt)
        == {
            "available_memory_bytes",
            "available_memory_gib",
            "minimum_available_memory_gib",
            "minimum_physical_memory_gib",
            "physical_memory_bytes",
            "physical_memory_gib",
            "u4_output_inspected",
        },
        "resume_environment_receipt_mismatch",
        "environment receipt fields",
    )
    physical = receipt.get("physical_memory_gib")
    available = receipt.get("available_memory_gib")
    physical_bytes = receipt.get("physical_memory_bytes")
    available_bytes = receipt.get("available_memory_bytes")
    _require(
        isinstance(physical, (int, float))
        and not isinstance(physical, bool)
        and math.isfinite(physical)
        and physical >= MINIMUM_PHYSICAL_MEMORY_GIB
        and isinstance(available, (int, float))
        and not isinstance(available, bool)
        and math.isfinite(available)
        and available >= MINIMUM_AVAILABLE_MEMORY_GIB
        and isinstance(physical_bytes, int)
        and not isinstance(physical_bytes, bool)
        and physical == physical_bytes / BYTES_PER_GIB
        and isinstance(available_bytes, int)
        and not isinstance(available_bytes, bool)
        and available == available_bytes / BYTES_PER_GIB
        and receipt.get("minimum_physical_memory_gib")
        == MINIMUM_PHYSICAL_MEMORY_GIB
        and receipt.get("minimum_available_memory_gib")
        == MINIMUM_AVAILABLE_MEMORY_GIB
        and receipt.get("u4_output_inspected") is False,
        "resume_environment_receipt_mismatch",
        "environment thresholds",
    )


def build_provenance_audit_context(
    *,
    authorization_record: Mapping[str, Any],
    authorization_record_path: Path,
    d_checkout_receipt: Mapping[str, Any],
    memory_gate: Mapping[str, Any],
    repo_root: Path = ROOT,
) -> Mapping[str, Any]:
    """Build trusted receipt inputs from already-validated live runtime gates."""

    _require(
        authorization_record.get("schema_id") == PROVENANCE_AUTHORIZATION_SCHEMA_ID,
        "resume_authorization_lineage_mismatch",
        "corrected provenance authorization required",
    )
    auth_raw = authorization_record_path.read_bytes()
    _require(
        _parse_bytes(auth_raw, "provenance authorization record")
        == authorization_record,
        "resume_authorization_lineage_mismatch",
        "authorization record bytes",
    )
    _require(
        d_checkout_receipt.get("branch") == PERSON_D_BRANCH
        and d_checkout_receipt.get("head") == PERSON_D_RUNNER_COMMIT
        and d_checkout_receipt.get("dirty") is False
        and d_checkout_receipt.get("passed") is True,
        "resume_runner_lineage_mismatch",
        "live D checkout receipt",
    )
    runner_receipt = {
        "branch": PERSON_D_BRANCH,
        "producing_runner_commit": PERSON_D_RUNNER_COMMIT,
        "worktree_clean": True,
    }
    environment_receipt = {
        "available_memory_bytes": memory_gate["available_memory_bytes"],
        "available_memory_gib": memory_gate["available_memory_gib"],
        "minimum_available_memory_gib": MINIMUM_AVAILABLE_MEMORY_GIB,
        "minimum_physical_memory_gib": MINIMUM_PHYSICAL_MEMORY_GIB,
        "physical_memory_bytes": memory_gate["physical_memory_bytes"],
        "physical_memory_gib": memory_gate["physical_memory_gib"],
        "u4_output_inspected": False,
    }
    _validate_audit_environment_receipt(environment_receipt)
    return {
        "accepted_authorization_authority_by_reusable_family": dict(
            authorization_record[
                "accepted_authorization_authority_by_reusable_family"
            ]
        ),
        "accepted_producing_authority_by_reusable_family": dict(
            authorization_record["accepted_producing_authority_by_reusable_family"]
        ),
        "authorization_record": {
            "path": str(authorization_record_path.resolve()),
            "sha256": _sha256(auth_raw),
        },
        "environment_receipt": environment_receipt,
        "runner_receipt": runner_receipt,
        "validator_commit": authorization_record[
            "provenance_audit_validator_commit"
        ],
    }


def _receipt_payload_sha256(document: Mapping[str, Any]) -> str:
    payload = dict(document)
    payload.pop("canonical_receipt_sha256", None)
    return _sha256(canonical_json_bytes(payload))


def _build_provenance_receipt(
    direct_audit: Mapping[str, Any], audit_context: Mapping[str, Any]
) -> Mapping[str, Any]:
    runner_receipt = dict(audit_context["runner_receipt"])
    environment_receipt = dict(audit_context["environment_receipt"])
    runner_sha256 = _sha256(canonical_json_bytes(runner_receipt))
    environment_sha256 = _sha256(canonical_json_bytes(environment_receipt))
    auth_reference = dict(audit_context["authorization_record"])
    producing = audit_context[
        "accepted_producing_authority_by_reusable_family"
    ]
    authorizations = audit_context[
        "accepted_authorization_authority_by_reusable_family"
    ]
    families: dict[str, Mapping[str, Any]] = {}
    family_evidence = direct_audit["family_evidence"]
    for family in direct_audit["completed_families"]:
        _require(
            family in producing and family in authorizations,
            "resume_authorization_lineage_mismatch",
            family,
        )
        evidence = family_evidence[family]
        families[family] = {
            **dict(evidence),
            "environment_receipt_sha256": environment_sha256,
            "producing_authorization_lineage": {
                "authorization_authority_commit": authorizations[family],
                "authorization_record_path": PREDECESSOR_AUTHORIZATION_RECORD_PATH,
                "authorization_record_sha256": PREDECESSOR_AUTHORIZATION_RECORD_SHA256,
            },
            "producing_person_d_authority": producing[family],
            "runner_receipt_sha256": runner_sha256,
        }
    document: dict[str, Any] = {
        "applicability_contract": dict(direct_audit["applicability_contract"]),
        "audit_decisions": dict(direct_audit["decisions"]),
        "direct_output_validation_required": True,
        "environment_receipt": environment_receipt,
        "environment_receipt_sha256": environment_sha256,
        "families": families,
        "fold_manifest_sha256": direct_audit["fold_manifest_sha256"],
        "frame_manifest_sha256": direct_audit["frame_manifest_sha256"],
        "generating_person_b_validator_commit": audit_context["validator_commit"],
        "no_u4_input": True,
        "output_manifest": dict(direct_audit["output_manifest"]),
        "output_root": direct_audit["output_root"],
        "person_d_runner_commit": PERSON_D_RUNNER_COMMIT,
        "receipt_is_person_b_generated_audit_output": True,
        "runner_receipt": runner_receipt,
        "runner_receipt_sha256": runner_sha256,
        "schema_id": PRESERVED_PROVENANCE_SCHEMA_ID,
        "schema_version": "2.0",
        "source_context_manifest_sha256": direct_audit[
            "source_context_manifest_sha256"
        ],
        "superseding_authorization_record": auth_reference,
        "target_manifest_sha256": direct_audit["target_manifest_sha256"],
        "total_prediction_count": direct_audit["prediction_count"],
        "u4_output_inspected": False,
    }
    document["canonical_receipt_sha256"] = _receipt_payload_sha256(document)
    return document


def _validate_provenance_receipt(
    path: Path,
    direct_audit: Mapping[str, Any],
    audit_context: Mapping[str, Any],
) -> Mapping[str, Any]:
    raw = path.read_bytes()
    document = _parse_bytes(raw, "Person B preserved-output audit receipt")
    _require(
        document.get("schema_id") == PRESERVED_PROVENANCE_SCHEMA_ID
        and document.get("schema_version") == "2.0",
        "resume_provenance_invalid",
        "receipt schema",
    )
    _require(
        document.get("canonical_receipt_sha256")
        == _receipt_payload_sha256(document),
        "resume_provenance_hash_mismatch",
        "canonical receipt payload",
    )
    _validate_audit_environment_receipt(document.get("environment_receipt"))
    comparison_context = dict(audit_context)
    comparison_context["environment_receipt"] = document["environment_receipt"]
    expected = _build_provenance_receipt(direct_audit, comparison_context)
    _require(
        document == expected,
        "resume_provenance_binding_mismatch",
        "receipt does not match direct audit",
    )
    return {
        "canonical_receipt_sha256": document["canonical_receipt_sha256"],
        "file_sha256": _sha256(raw),
        "path": str(path.resolve()),
        "validated": True,
    }


def _atomic_write_provenance_receipt(
    path: Path,
    document: Mapping[str, Any],
    *,
    replace_func: Callable[[Path, Path], Any] = os.replace,
) -> None:
    """Write only the Person B receipt via a same-directory atomic rename."""

    raw = canonical_json_bytes(document)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        replace_func(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def audit_preserved_outputs(
    output_root: Path,
    *,
    materialized_root: Path | None = None,
    repo_root: Path = ROOT,
    audit_context: Mapping[str, Any] | None = None,
    atomic_replace: Callable[[Path, Path], Any] = os.replace,
) -> Mapping[str, Any]:
    """Directly audit preserved files, then create/revalidate the B receipt."""

    try:
        result = validate_output_resume_state(
            output_root,
            materialized_root=materialized_root,
            repo_root=repo_root,
        )
    except (MemoryReauthorizationError, OSError, ValueError) as error:
        resolved = output_root.resolve()
        families: Mapping[str, Any] = {}
        state_path = resolved / "run_state.json"
        if state_path.is_file():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
                candidate = state.get("families", {}) if isinstance(state, Mapping) else {}
                if isinstance(candidate, Mapping):
                    families = candidate
            except (OSError, ValueError):
                families = {}
        decisions: dict[str, str] = {}
        for family in EXPECTED_FAMILIES:
            expected_files = tuple(
                resolved / f"{family}__{target}.json"
                for target in EXPECTED_RESUME_TARGET_FAMILIES[family]
            )
            present = any(path.exists() for path in expected_files)
            record = families.get(family)
            recorded = isinstance(record, Mapping) and record.get("status") == "completed"
            decisions[family] = (
                "invalid-conflicting" if present or recorded else "absent"
            )
        return {
            "checked": state_path.exists(),
            "decisions": decisions,
            "error": str(error),
            "passed": False,
            "receipt_accepted": False,
            "receipt_generated": False,
        }
    result = dict(result)
    result["output_root"] = str(output_root.resolve())
    if not result["completed_families"]:
        result.update(
            {
                "receipt_accepted": False,
                "receipt_generated": False,
                "receipt_required": False,
            }
        )
        return result
    _require(
        all(
            result["decisions"][family] == "reusable"
            for family in result["completed_families"]
        ),
        "resume_invalid_conflicting",
        "every present family must be reusable",
    )
    _require(
        audit_context is not None,
        "resume_provenance_context_missing",
        "validated runner, authorization, and environment receipts required",
    )
    receipt_path = output_root.resolve() / PRESERVED_PROVENANCE_FILENAME
    generated = False
    if not receipt_path.exists():
        receipt = _build_provenance_receipt(result, audit_context)
        _atomic_write_provenance_receipt(
            receipt_path, receipt, replace_func=atomic_replace
        )
        generated = True
    receipt_validation = _validate_provenance_receipt(
        receipt_path, result, audit_context
    )
    result.update(
        {
            "preserved_output_provenance": {
                **receipt_validation,
                "prediction_count": result["prediction_count"],
            },
            "receipt_accepted": True,
            "receipt_generated": generated,
            "receipt_required": True,
        }
    )
    return result


def validate_external_authorization_record(path: Path) -> Mapping[str, Any]:
    """Validate the external JSON object consumed by D's loader."""

    document = _parse_path(path, "external authorization record")
    _validate_external_auth(ROOT, document)
    return document


def _identity(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("trajectory_id"),
        row.get("model_frame_idx"),
        row.get("source_frame_id"),
    )


def _verify_frame_payloads(frame: Mapping[str, Any], frame_root: Path) -> Mapping[str, Any]:
    """Hash and structurally verify every one of the 1,695 frame payloads.

    This is a compatibility/integrity check only.  It decodes no feature
    values and never enters a baseline estimator.  Relative paths are checked
    after resolution so a malformed manifest cannot make the reuse gate read
    outside the approved frame root.
    """

    frame_root = frame_root.resolve()
    _require(frame_root.is_dir(), "reuse_frame_root_missing", str(frame_root))
    for field, expected in (
        ("artifact_count", 1695),
        ("unique_frame_count", 1695),
        ("duplicate_frame_count", 0),
        ("missing_frame_count", 0),
        ("fold_manifest_sha256", FOLD_MANIFEST_SHA256),
        ("target_manifest_sha256", TARGET_MANIFEST_SHA256),
    ):
        _require(frame.get(field) == expected, "reuse_frame_manifest_mismatch", field)
    records = frame.get("records")
    _require(isinstance(records, list) and len(records) == 1695, "reuse_frame_count_mismatch", "frame records")
    seen: set[tuple[str, int]] = set()
    missing = 0
    for index, record in enumerate(records):
        _require(isinstance(record, Mapping), "reuse_payload_record_invalid", str(index))
        trajectory = record.get("trajectory_id")
        frame_idx = record.get("model_frame_idx")
        _require(
            trajectory in EXPECTED_PILOTS
            and isinstance(frame_idx, int)
            and not isinstance(frame_idx, bool),
            "reuse_payload_identity_mismatch",
            str(index),
        )
        key = (trajectory, frame_idx)
        _require(key not in seen, "reuse_payload_duplicate", str(key))
        seen.add(key)
        relative = record.get("output_relative_path")
        _require(isinstance(relative, str) and relative, "reuse_payload_path_invalid", str(key))
        candidate = Path(relative)
        _require(not candidate.is_absolute(), "reuse_payload_path_unsafe", relative)
        payload_path = (frame_root / candidate).resolve()
        _require(
            payload_path == frame_root or frame_root in payload_path.parents,
            "reuse_payload_path_unsafe",
            relative,
        )
        _require(payload_path.is_file(), "reuse_payload_missing", str(payload_path))
        payload = payload_path.read_bytes()
        expected_size = record.get("payload_byte_size")
        expected_digest = record.get("payload_sha256")
        _require(
            isinstance(expected_size, int)
            and not isinstance(expected_size, bool)
            and expected_size > 0,
            "reuse_payload_size_invalid",
            str(key),
        )
        _require(
            isinstance(expected_digest, str)
            and re.fullmatch(r"[0-9a-f]{64}", expected_digest) is not None,
            "reuse_payload_hash_invalid",
            str(key),
        )
        if len(payload) != expected_size:
            missing += 1
            _fail(
                "reuse_payload_size_mismatch",
                f"{key}: expected {expected_size}, got {len(payload)}",
            )
        _require(
            _sha256(payload) == expected_digest,
            "reuse_payload_hash_mismatch",
            str(key),
        )
        _require(
            record.get("global_frame_identity") == f"{trajectory}:{frame_idx}",
            "reuse_payload_identity_mismatch",
            str(key),
        )
        target_binding = record.get("target_binding")
        _require(
            isinstance(target_binding, Mapping)
            and target_binding.get("target_id") == f"{trajectory}:{frame_idx}:regime_a_primary_v1",
            "reuse_payload_target_mismatch",
            str(key),
        )
        fold_binding = record.get("fold_binding")
        _require(
            isinstance(fold_binding, Mapping)
            and isinstance(fold_binding.get("fold_idx"), int)
            and not isinstance(fold_binding.get("fold_idx"), bool)
            and fold_binding.get("fold_idx") in range(5),
            "reuse_payload_fold_mismatch",
            str(key),
        )
        _require(record.get("dtype") == REQUIRED_PAYLOAD_DTYPE, "reuse_payload_profile_mismatch", str(key))
        _require(record.get("layout") == REQUIRED_PAYLOAD_LAYOUT, "reuse_payload_profile_mismatch", str(key))
        _require(record.get("color_order") == REQUIRED_PAYLOAD_COLOR_ORDER, "reuse_payload_profile_mismatch", str(key))
        _require(record.get("payload_format") == REQUIRED_PAYLOAD_FORMAT, "reuse_payload_profile_mismatch", str(key))
        shape = record.get("shape")
        _require(
            isinstance(shape, list) and tuple(shape) == REQUIRED_PAYLOAD_SHAPE,
            "reuse_payload_profile_mismatch",
            str(key),
        )
    _require(len(seen) == 1695 and missing == 0, "reuse_payload_count_mismatch", "payloads")
    return {
        "expected_frame_count": 1695,
        "actual_frame_count": len(seen),
        "payload_hashes_revalidated": True,
        "passed": True,
    }


def validate_reuse_semantics(
    frame: Mapping[str, Any],
    fold: Mapping[str, Any],
    target: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Validate row/pilot/fold identity using small in-memory fixtures.

    This pure check deliberately does not read frame payload bytes.  The
    materialized-root entry point performs raw-byte and Git-object checks
    first, then applies this same semantic contract to the parsed manifests.
    """

    records = frame.get("records")
    memberships = fold.get("memberships")
    target_rows = target.get("rows")
    _require(isinstance(records, Sequence) and len(records) == 1695, "reuse_frame_count_mismatch", "frame records")
    _require(isinstance(memberships, Sequence) and len(memberships) == 1695, "reuse_row_count_mismatch", "fold memberships")
    _require(isinstance(target_rows, Sequence) and len(target_rows) == 1695 and target.get("row_count") == 1695, "reuse_target_count_mismatch", "target rows")
    _require(tuple(fold.get("accepted_pilot_ids", ())) == EXPECTED_PILOTS, "reuse_pilot_mismatch", "fold pilots")
    expected_fold_counts = tuple({"fold_idx": idx, "row_count": count} for idx, count in enumerate((292, 409, 387, 272, 335)))
    _require(tuple(fold.get("row_counts", {}).get("admitted_by_fold", ())) == expected_fold_counts, "reuse_fold_count_mismatch", "fold counts")
    assignments = fold.get("layout_assignments", ())
    _require(tuple(item.get("fold_idx") for item in assignments) == EXPECTED_MAPPING, "reuse_mapping_mismatch", "layout assignment order")
    frame_ids = [_identity(row) for row in records if isinstance(row, Mapping)]
    fold_ids = [_identity(row) for row in memberships if isinstance(row, Mapping)]
    target_ids = [_identity(row) for row in target_rows if isinstance(row, Mapping)]
    _require(len(set(frame_ids)) == 1695, "reuse_duplicate_rows", "frame identities")
    _require(len(set(fold_ids)) == 1695, "reuse_duplicate_rows", "fold identities")
    _require(len(set(target_ids)) == 1695, "reuse_duplicate_rows", "target identities")
    _require(set(frame_ids) == set(fold_ids) == set(target_ids), "reuse_identity_join_mismatch", "frame/fold/target identities")
    frame_by_id = {key: row for key, row in zip(frame_ids, records)}
    fold_by_id = {key: row for key, row in zip(fold_ids, memberships)}
    target_by_id = {key: row for key, row in zip(target_ids, target_rows)}
    layout_to_fold = dict(zip(EXPECTED_LAYOUTS, EXPECTED_MAPPING))
    folds_by_trajectory: dict[str, set[int]] = defaultdict(set)
    for key, row in fold_by_id.items():
        _require(isinstance(row, Mapping), "reuse_row_mismatch", "fold row")
        trajectory = row.get("trajectory_id")
        layout = row.get("layout_id")
        fold_idx = row.get("fold_idx")
        _require(layout_to_fold.get(layout) == fold_idx, "reuse_mapping_mismatch", str(key))
        folds_by_trajectory[str(trajectory)].add(int(fold_idx))
        frame_row = frame_by_id[key]
        _require(frame_row.get("global_frame_identity", f"{trajectory}:{key[1]}") == f"{trajectory}:{key[1]}", "reuse_frame_identity_mismatch", str(key))
        _require(frame_row.get("target_binding", {}).get("target_id") == target_by_id[key].get("target_id"), "reuse_target_binding_mismatch", str(key))
    _require(all(len(values) == 1 for values in folds_by_trajectory.values()), "reuse_cross_fold_leakage", "trajectory spans folds")
    _require(len(folds_by_trajectory) == 10, "reuse_pilot_mismatch", "trajectory count")
    return {
        "accepted": True,
        "frame_count": len(records),
        "row_count": len(memberships),
        "pilot_count": len(folds_by_trajectory),
        "mapping": list(EXPECTED_MAPPING),
        "cross_fold_leakage_count": 0,
    }


def validate_materialized_reuse(
    materialized_root: Path,
    *,
    frame_root: Path | None = None,
    repo_root: Path = ROOT,
    package_root: Path | None = None,
) -> Mapping[str, Any]:
    """Revalidate all materialized bytes, source authorities, rows, folds, and payloads."""

    repo_root = repo_root.resolve()
    package_root = (package_root or repo_root / PACKAGE_RELATIVE_PATH).resolve()
    package = _load_documents(package_root)
    _validate_inventory(package_root, package)
    reuse = package["materialized_input_reuse.json"]
    _validate_reuse_contract(reuse)
    materialized_root = materialized_root.resolve()
    _require(materialized_root.is_dir(), "reuse_root_missing", str(materialized_root))

    bindings = (
        ("frame_manifest", FRAME_MANIFEST_PATH, PERSON_A_FRAME_COMMIT, FRAME_MANIFEST_SHA256, FRAME_MANIFEST_SIZE, "preprocessed_frame_manifest.json"),
        ("fold_manifest", FOLD_MANIFEST_PATH, PERSON_B_PRODUCTION_COMMIT, FOLD_MANIFEST_SHA256, FOLD_MANIFEST_SIZE, "ten_pilot_frame_fold_manifest.json"),
        ("target_manifest", TARGET_MANIFEST_PATH, PERSON_B_PRODUCTION_COMMIT, TARGET_MANIFEST_SHA256, TARGET_MANIFEST_SIZE, "production_oracle_target_manifest.json"),
        ("source_context_manifest", SOURCE_CONTEXT_MANIFEST_PATH, PERSON_B_BASELINE_COMMIT, SOURCE_CONTEXT_SHA256, SOURCE_CONTEXT_SIZE, "source_context_manifest.json"),
    )
    parsed: dict[str, Mapping[str, Any]] = {}
    for label, source_path, commit, digest, size, filename in bindings:
        source = _git_blob(repo_root, commit, source_path)
        _require(len(source) == size and _sha256(source) == digest, "source_identity_mismatch", label)
        local = materialized_root / filename
        raw = local.read_bytes() if local.is_file() else b""
        _require(len(raw) == size and _sha256(raw) == digest, "reuse_identity_mismatch", label)
        parsed[label] = _parse_bytes(raw, label)

    source_context = parsed["source_context_manifest"]
    _require(tuple(source_context.get("accepted_pilot_ids", ())) == EXPECTED_PILOTS, "reuse_pilot_mismatch", "source context pilots")
    _require(source_context.get("accepted_pilot_count") == 10, "reuse_pilot_mismatch", "source context count")
    captures = source_context.get("source_contexts")
    _require(isinstance(captures, Sequence) and len(captures) == 10, "reuse_capture_mismatch", "capture count")
    expected_capture_map = {item[0]: item for item in EXPECTED_CAPTURE_IDENTITIES}
    for context in captures:
        _require(isinstance(context, Mapping), "reuse_capture_mismatch", "capture context")
        trajectory = context.get("trajectory_id")
        _require(trajectory in expected_capture_map, "reuse_capture_mismatch", str(trajectory))
        _, capture_path, size, digest = expected_capture_map[trajectory]
        reference = context.get("capture_package")
        _require(isinstance(reference, Mapping), "reuse_capture_mismatch", f"{trajectory} reference")
        _require(reference.get("path") == capture_path and reference.get("byte_size") == size and reference.get("sha256") == digest, "reuse_capture_mismatch", trajectory)
        source = _git_blob(repo_root, PERSON_C_COMMIT, capture_path)
        _require(len(source) == size and _sha256(source) == digest, "capture_source_identity_mismatch", trajectory)
        local = (materialized_root / Path(capture_path)).resolve()
        _require(
            local == materialized_root or materialized_root in local.parents,
            "capture_path_unsafe",
            capture_path,
        )
        raw = local.read_bytes() if local.is_file() else b""
        _require(len(raw) == size and _sha256(raw) == digest, "capture_reuse_identity_mismatch", trajectory)

    frame = parsed["frame_manifest"]
    fold = parsed["fold_manifest"]
    target = parsed["target_manifest"]
    _require(frame_root is not None, "reuse_frame_root_missing", "--frame-root is required")
    payload_result = _verify_frame_payloads(frame, frame_root)
    records = frame.get("records")
    memberships = fold.get("memberships")
    target_rows = target.get("rows")
    _require(isinstance(records, Sequence) and len(records) == 1695, "reuse_frame_count_mismatch", "frame records")
    _require(isinstance(memberships, Sequence) and len(memberships) == 1695, "reuse_row_count_mismatch", "fold memberships")
    _require(isinstance(target_rows, Sequence) and len(target_rows) == 1695 and target.get("row_count") == 1695, "reuse_target_count_mismatch", "target rows")
    _require(tuple(fold.get("accepted_pilot_ids", ())) == EXPECTED_PILOTS, "reuse_pilot_mismatch", "fold pilots")
    _require(tuple(fold.get("row_counts", {}).get("admitted_by_fold", ())) == tuple({"fold_idx": idx, "row_count": count} for idx, count in enumerate((292, 409, 387, 272, 335))), "reuse_fold_count_mismatch", "fold counts")
    _require(tuple(item.get("fold_idx") for item in fold.get("layout_assignments", ())) == (1, 2, 4, 0, 3), "reuse_mapping_mismatch", "layout assignment order")

    frame_ids = [_identity(row) for row in records if isinstance(row, Mapping)]
    fold_ids = [_identity(row) for row in memberships if isinstance(row, Mapping)]
    target_ids = [_identity(row) for row in target_rows if isinstance(row, Mapping)]
    _require(len(set(frame_ids)) == 1695, "reuse_duplicate_rows", "frame identities")
    _require(len(set(fold_ids)) == 1695, "reuse_duplicate_rows", "fold identities")
    _require(len(set(target_ids)) == 1695, "reuse_duplicate_rows", "target identities")
    _require(set(frame_ids) == set(fold_ids) == set(target_ids), "reuse_identity_join_mismatch", "frame/fold/target identities")
    frame_by_id = {key: row for key, row in zip(frame_ids, records)}
    fold_by_id = {key: row for key, row in zip(fold_ids, memberships)}
    layout_to_fold = dict(zip(EXPECTED_LAYOUTS, EXPECTED_MAPPING))
    folds_by_trajectory: dict[str, set[int]] = defaultdict(set)
    for key, row in fold_by_id.items():
        _require(isinstance(row, Mapping), "reuse_row_mismatch", "fold row")
        trajectory = row.get("trajectory_id")
        layout = row.get("layout_id")
        fold_idx = row.get("fold_idx")
        _require(layout_to_fold.get(layout) == fold_idx, "reuse_mapping_mismatch", str(key))
        folds_by_trajectory[str(trajectory)].add(int(fold_idx))
        frame_row = frame_by_id[key]
        _require(frame_row.get("target_binding", {}).get("target_id") == next((target_row.get("target_id") for target_row in target_rows if _identity(target_row) == key), None), "reuse_target_binding_mismatch", str(key))
    _require(all(len(values) == 1 for values in folds_by_trajectory.values()), "reuse_cross_fold_leakage", "trajectory spans folds")
    _require(len(folds_by_trajectory) == 10, "reuse_pilot_mismatch", "trajectory count")
    semantic_result = validate_reuse_semantics(frame, fold, target)
    return {
        **semantic_result,
        "cross_fold_leakage_count": 0,
        "raw_hashes_revalidated": True,
        "source_authorities_revalidated": True,
        **payload_result,
    }


def runtime_preflight(
    d_checkout: Path,
    authorization_record_path: Path,
    *,
    output_root: Path | None = None,
    materialized_root: Path | None = None,
    memory: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """Run the B-owned D-checkout and immediate memory gate."""

    d_receipt = validate_d_checkout(d_checkout)
    record = validate_external_authorization_record(authorization_record_path)
    detected = dict(memory) if memory is not None else detect_linux_memory()
    _require(platform.system() == "Linux" or memory is not None, "memory_platform_unsupported", "runtime gate requires Linux detection")
    gate = validate_memory_gate(detected)
    if output_root is not None:
        _require(
            record.get("output_root") == str(output_root.resolve()),
            "resume_output_root_mismatch",
            str(output_root.resolve()),
        )
        audit_context = build_provenance_audit_context(
            authorization_record=record,
            authorization_record_path=authorization_record_path,
            d_checkout_receipt=d_receipt,
            memory_gate=gate,
        )
        resume = audit_preserved_outputs(
            output_root,
            materialized_root=materialized_root,
            audit_context=audit_context,
        )
        _require(
            resume.get("passed") is True,
            "resume_invalid_conflicting",
            str(resume.get("error", "direct preserved-output audit failed")),
        )
        _require(
            not resume.get("completed_families")
            or resume.get("receipt_accepted") is True,
            "resume_provenance_invalid",
            "completed outputs require a generated or revalidated receipt",
        )
    else:
        resume = {"checked": False, "passed": True}
    return {"accepted": True, "authorization_record": dict(record), "d_checkout": str(d_checkout.resolve()), "memory": gate, "resume": resume}


def _run_cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode")
    package = sub.add_parser("validate-package")
    package.add_argument("--repo-root", type=Path, default=ROOT)
    package.add_argument("--package-root", type=Path)
    package.add_argument("--json", action="store_true")
    reuse = sub.add_parser("reuse-validate")
    reuse.add_argument("--repo-root", type=Path, default=ROOT)
    reuse.add_argument("--package-root", type=Path)
    reuse.add_argument("--materialized-root", type=Path, required=True)
    reuse.add_argument("--frame-root", type=Path, required=True)
    reuse.add_argument("--json", action="store_true")
    preflight = sub.add_parser("runtime-preflight")
    preflight.add_argument("--d-checkout", type=Path, required=True)
    preflight.add_argument("--authorization-record-path", type=Path, required=True)
    preflight.add_argument("--output-root", type=Path)
    preflight.add_argument("--materialized-root", type=Path)
    preflight.add_argument("--json", action="store_true")
    audit = sub.add_parser("resume-audit")
    audit.add_argument("--repo-root", type=Path, default=ROOT)
    audit.add_argument("--d-checkout", type=Path, required=True)
    audit.add_argument("--authorization-record-path", type=Path, required=True)
    audit.add_argument("--output-root", type=Path, required=True)
    audit.add_argument("--materialized-root", type=Path)
    audit.add_argument("--json", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.mode in (None, "validate-package"):
            result = validate_package(args.repo_root.resolve(), args.package_root)
        elif args.mode == "reuse-validate":
            result = validate_materialized_reuse(
                args.materialized_root,
                frame_root=args.frame_root,
                repo_root=args.repo_root,
                package_root=args.package_root,
            )
        elif args.mode == "runtime-preflight":
            result = runtime_preflight(
                args.d_checkout,
                args.authorization_record_path,
                output_root=args.output_root,
                materialized_root=args.materialized_root,
            )
        else:
            result = runtime_preflight(
                args.d_checkout,
                args.authorization_record_path,
                output_root=args.output_root,
                materialized_root=args.materialized_root,
            )
    except (MemoryReauthorizationError, OSError) as error:
        if getattr(args, "json", False):
            print(json.dumps({"accepted": False, "error": str(error)}, sort_keys=True))
        else:
            print(f"FAIL-CLOSED: {error}", file=sys.stderr)
        return 1
    if getattr(args, "json", False):
        print(json.dumps(result, sort_keys=True))
    else:
        print("PASS: Person B Step 4.1 memory reauthorization preflight validated")
    return 0


def main() -> int:
    return _run_cli(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
