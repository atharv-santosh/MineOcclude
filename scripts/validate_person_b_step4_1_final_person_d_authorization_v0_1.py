#!/usr/bin/env python3
"""Validate Person B's additive Person D Step 4.1 authorization package.

This validator performs source and manifest identity checks only.  It does not
materialize inputs, read external frame payloads, fit a baseline, compute a
metric, inspect U4, or claim that execution has occurred.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_RELATIVE_PATH = Path(
    "docs/status/person_b_phase4_step4_1_final_person_d_authorization_v0_1"
)
DOCUMENT_NAMES = (
    "authority_binding.json",
    "person_d_compatibility_evidence.json",
    "person_d_runtime_authorization.json",
    "production_commands.json",
    "output_closure_requirements.json",
    "final_authorization_decision.json",
    "validation_receipt.json",
    "sha256_inventory.json",
)
INVENTORIED_NAMES = DOCUMENT_NAMES[:-1]

PERSON_A_FRAME_COMMIT = "380b9a392c7ad3a941dbdadcc777c61ed03e1206"
PERSON_A_FRAME_PATH = (
    "docs/status/person_a_phase4_step4_1_frame_handoff_v0_2/"
    "preprocessed_frame_manifest.json"
)
PERSON_A_FRAME_SHA256 = "f52a2ece32b00faf04b68b92b56c6f6a049b8a7bcb9c7f0af0f52de7fc4759c5"
PERSON_A_FRAME_SIZE = 6460547
PERSON_A_FRAME_COUNT = 1695

PERSON_B_FOLD_COMMIT = "a612ec29108c8f69f19cdc283e40873e75796ea7"
PERSON_B_PRODUCTION_COMMIT = "c9a519b42cf651e05f5b4f640fda6e1a0aed3e7c"
PERSON_B_BASELINE_COMMIT = "265cbbb394ee481439397879ad9a99c9038bf4cd"
PERSON_B_FOLD_PATH = (
    "docs/status/person_b_phase4_step4_1_production_handoff_v0_1/"
    "ten_pilot_frame_fold_manifest.json"
)
PERSON_B_FOLD_SHA256 = "53ca938c6ae936c3ecb6e6e8d95a3fda152f5fa130b52e7a000d297810738d71"
PERSON_B_FOLD_SIZE = 742601

PERSON_B_TARGET_PATH = (
    "docs/status/person_b_phase4_step4_1_production_handoff_v0_1/"
    "production_oracle_target_manifest.json"
)
PERSON_B_TARGET_SHA256 = "afcf3afae00db6330665afc5964608c6db89eeac3767c9486d8ba0a218858282"
PERSON_B_TARGET_SIZE = 4934874

PERSON_D_SIGNED_COMMIT = "4915252ce5a9f346fc39f1f2583478949c3787f5"
PERSON_D_RUNNER_COMMIT = "5b90e5bf6c6975119f509d766a82a9786d64300c"
PERSON_D_CLI_COMMIT = "bb2ebf7947c92c814dae85fc9cef29fef04e4c6f"
PERSON_D_EXPORTER_COMMIT = "fd9302e5d218193211f2f96986ca32dc1a365e66"
PERSON_D_BRANCH = "role/person-d-baselines"
PERSON_D_RUNNER_PATH = "scripts/run_person_d_step4_1_eight_family_production.py"
PERSON_D_SIGNED_VALIDATOR_PATH = (
    "src/mineocclude/baselines/production_fold_contract_v0_1.py"
)
PERSON_D_FAMILY_CONTRACT_PATH = "src/mineocclude/baselines/baseline_family_input_v0_2.py"
PERSON_D_FAMILY_CONTRACT_SHA256 = "91d842c2644bc5b14ec8dfe659bac894fe3f18e258fded1ebb6c0e4fff040b6b"
PERSON_D_FAMILY_CONTRACT_SIZE = 23620
PERSON_D_FAMILY_CONTRACT_SYMBOL = "BASELINE_FAMILY_CONTRACTS_V0_2"
PERSON_D_EXPORT_PATH = "src/mineocclude/baselines/export.py"
PERSON_D_REAL_RECEIPT_PATH = (
    "docs/status/person_d_phase4_step4_1_signed_fold_validation_v0_1/"
    "real_manifest_regression_result.json"
)
PERSON_D_REAL_RECEIPT_SHA256 = "a5a25cb4ca0c5a59df3c02786214efe9d64c3f9f1619272bd51a84417343681b"
PERSON_D_REAL_RECEIPT_SIZE = 1875
PERSON_D_BRANCH_AUTH_PATH = (
    "docs/status/person_d_phase4_step4_1_eight_family_production_v0_2/"
    "authorized_runner_commit.json"
)
PERSON_D_BRANCH_AUTH_SHA256 = "caba5883168d2ba5e509eb5b01e8c879ad447e3e8b1faf5bf89b1822472ea7e0"
PERSON_D_BRANCH_AUTH_SIZE = 1072

PERSON_E_COMMIT = "21d83c19c9d8f36c4dbeeaf45d4626eaf082e7a7"
PERSON_E_CLOSURE_PATH = (
    "docs/status/person_e_phase6_to_step4_1_handoff_v0_1/"
    "person_e_closure_requirements.json"
)
PERSON_E_CLOSURE_SHA256 = "c77148f0d2139bff6eef10da41bd55df2da878bee95029afd258bbcb63d741dd"
PERSON_E_CLOSURE_SIZE = 3556
PERSON_C_EXPANSION_COMMIT = "c6bff25b5ef4f5fdb0e1ef0ce0d22e3f8b5e4960"
SOURCE_CONTEXT_PATH = (
    "docs/status/person_b_phase4_step4_1_baseline_family_contract_v0_2/"
    "source_context_manifest.json"
)
SOURCE_CONTEXT_SHA256 = "ce4ba48c53ce57c6321a657e97c166772475a77d459e59ad8d20cc37b33aa74c"
SOURCE_CONTEXT_SIZE = 4654
ANALYSIS_CONFIG_PATH = "configs/analysis/core.yaml"
ANALYSIS_CONFIG_SHA256 = "b2e12e7049e0494c756be442a4f300cbc7dc0a6e262deecf682f1354e887f0ab"
ANALYSIS_CONFIG_SIZE = 4881

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
EXPECTED_ASSIGNMENT = (1, 2, 4, 0, 3)
EXPECTED_LAYOUT_IDS = tuple(f"layout_{idx:02d}" for idx in range(5))
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
AUTHORIZATION_RECORD_ABSOLUTE_PATH = (
    "/home/sagemaker-user/MineOcclude-person-b-analysis/docs/status/"
    "person_b_phase4_step4_1_final_person_d_authorization_v0_1/"
    "person_d_runtime_authorization.json"
)


class FinalPersonDAuthorizationError(ValueError):
    """Raised when an authorization condition fails closed."""


def _fail(code: str, message: str) -> None:
    raise FinalPersonDAuthorizationError(f"{code}: {message}")


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        _fail(code, message)


def canonical_json_bytes(value: Any) -> bytes:
    """Return repository-canonical JSON bytes."""

    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _git_bytes(repo_root: Path, commit: str, path: str) -> bytes:
    result = subprocess.run(
        ["git", "cat-file", "blob", f"{commit}:{path}"],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        _fail("git_source_error", detail or f"missing {commit}:{path}")
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
        _fail("git_source_error", result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def _is_ancestor(repo_root: Path, ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def validate_runtime_context(
    *,
    branch: str,
    head: str,
    worktree_dirty: bool,
    exporter_commit_is_ancestor: bool,
    authorized_runner_commit: str | None,
) -> tuple[str, ...]:
    """Return all fail-closed runtime authorization errors.

    This pure helper is intentionally separate from the B checkout's package
    validation: a real execution uses a clean D checkout, while this package
    is authored and validated from the B checkout.
    """

    errors: list[str] = []
    if branch != PERSON_D_BRANCH:
        errors.append(f"wrong_branch:{branch!r}")
    if worktree_dirty:
        errors.append("dirty_worktree")
    if not exporter_commit_is_ancestor:
        errors.append("exporter_commit_not_ancestor")
    if authorized_runner_commit is None:
        errors.append("no_authorized_runner_commit_recorded")
    elif head != authorized_runner_commit:
        errors.append(
            f"head_not_authorized:head={head}:authorized={authorized_runner_commit}"
        )
    return tuple(errors)


def _parse_json(raw: bytes, label: str, *, canonical: bool = True) -> Mapping[str, Any]:
    _require(not raw.startswith(b"\xef\xbb\xbf"), "noncanonical_json", f"{label} has a BOM")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail("invalid_json", f"{label}: {error}")
    _require(isinstance(value, Mapping), "invalid_json", f"{label} is not an object")
    if canonical:
        _require(raw == canonical_json_bytes(value), "noncanonical_json", f"{label} is not canonical")
    return value


def _extract_d_family_configuration(raw: bytes) -> Mapping[str, Mapping[str, Any]]:
    """Read only BASELINE_FAMILY_CONTRACTS_V0_2.configuration from D's object."""

    try:
        tree = ast.parse(raw.decode("utf-8"), filename=PERSON_D_FAMILY_CONTRACT_PATH)
        value_node = next(
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == PERSON_D_FAMILY_CONTRACT_SYMBOL
        )
        contracts = ast.literal_eval(value_node)
    except (StopIteration, SyntaxError, UnicodeDecodeError, ValueError) as error:
        _fail("configuration_source_mismatch", f"could not parse D contract: {error}")
    _require(isinstance(contracts, Mapping), "configuration_source_mismatch", "D contract is not a mapping")
    result: dict[str, Mapping[str, Any]] = {}
    for family in EXPECTED_FAMILIES:
        contract = contracts.get(family)
        _require(isinstance(contract, Mapping), "configuration_source_mismatch", f"missing {family}")
        configuration = contract.get("configuration")
        _require(isinstance(configuration, Mapping), "configuration_source_mismatch", f"missing {family}.configuration")
        result[family] = configuration
    _require(tuple(result) == EXPECTED_FAMILIES, "configuration_source_mismatch", "D family order")
    return result


def _load_package(package_root: Path) -> dict[str, Mapping[str, Any]]:
    actual = {path.name for path in package_root.glob("*.json")}
    _require(actual == set(DOCUMENT_NAMES), "package_inventory_mismatch", "unexpected package JSON files")
    documents: dict[str, Mapping[str, Any]] = {}
    for name in DOCUMENT_NAMES:
        document = _parse_json((package_root / name).read_bytes(), name)
        _require(document.get("schema_version") == "1.0", "schema_mismatch", f"{name} schema_version")
        _require(
            isinstance(document.get("schema_id"), str)
            and document["schema_id"].startswith(
                "person-b-phase4-step4-1-final-person-d-authorization-v0-1-"
            ),
            "schema_mismatch",
            f"{name} schema_id",
        )
        documents[name] = document
    return documents


def _validate_inventory(package_root: Path, documents: Mapping[str, Mapping[str, Any]]) -> None:
    inventory = documents["sha256_inventory.json"]
    _require(inventory.get("inventory_excludes_self") is True, "inventory_mismatch", "inventory must exclude itself")
    files = inventory.get("files")
    expected_paths = {
        f"{PACKAGE_RELATIVE_PATH.as_posix()}/{name}" for name in INVENTORIED_NAMES
    }
    _require(isinstance(files, Mapping) and set(files) == expected_paths, "inventory_mismatch", "inventory file set")
    for relative_path in expected_paths:
        name = Path(relative_path).name
        entry = files[relative_path]
        _require(isinstance(entry, Mapping), "inventory_mismatch", f"{relative_path} entry")
        raw = (package_root / name).read_bytes()
        _require(entry.get("byte_size") == len(raw), "inventory_mismatch", f"{name} byte size")
        _require(entry.get("sha256") == _sha256(raw), "inventory_mismatch", f"{name} hash")


def _validate_safety_claims(documents: Mapping[str, Mapping[str, Any]]) -> None:
    """Reject any package document that turns a bounded state into a claim."""

    guarded_false_keys = {
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
                if key in guarded_false_keys:
                    _require(child is False, "execution_claim_mismatch", f"{path}.{key}")
                walk(child, f"{path}.{key}")
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    for name, document in documents.items():
        walk(document, name)


def _validate_authority(
    document: Mapping[str, Any],
    repo_root: Path | None = None,
) -> None:
    authorities = document.get("authorities")
    _require(isinstance(authorities, Mapping), "authority_mismatch", "authorities missing")
    expected = {
        "person_a_frame_handoff_commit": PERSON_A_FRAME_COMMIT,
        "person_b_baseline_v0_2_commit": "265cbbb394ee481439397879ad9a99c9038bf4cd",
        "person_b_fold_contract_commit": "06bd2a17b90d95de37c0739d17d3a624964cc4fa",
        "person_b_production_ratification_commit": PERSON_B_PRODUCTION_COMMIT,
        "person_b_schema_correction_commit": "4e0e0f49d4642cf069de8c66c3a8fee47806c4b0",
        "person_b_start_fold_interface_ratification_commit": PERSON_B_FOLD_COMMIT,
        "person_d_cli_commit": PERSON_D_CLI_COMMIT,
        "person_d_exporter_commit": PERSON_D_EXPORTER_COMMIT,
        "person_d_runner_preparation_commit": PERSON_D_RUNNER_COMMIT,
        "person_d_signed_validator_commit": PERSON_D_SIGNED_COMMIT,
        "person_c_expansion_acceptance_commit": PERSON_C_EXPANSION_COMMIT,
        "person_e_handoff_commit": PERSON_E_COMMIT,
    }
    for key, value in expected.items():
        _require(authorities.get(key) == value, "authority_mismatch", key)
    _require(tuple(document.get("baseline_families", ())) == EXPECTED_FAMILIES, "family_mismatch", "family order")
    contract = document.get("contract")
    _require(isinstance(contract, Mapping), "contract_mismatch", "contract missing")
    _require(tuple(contract.get("assignment_by_ordered_layout", ())) == EXPECTED_ASSIGNMENT, "mapping_mismatch", "assignment")
    _require(contract.get("contract_version") == "person-b-step4-1-production-fold-contract-v0.1", "contract_mismatch", "contract version")
    _require(tuple(contract.get("layout_row_counts", ())) == EXPECTED_LAYOUT_COUNTS, "mapping_mismatch", "layout counts")
    _require(contract.get("seed") == 20260719, "mapping_mismatch", "seed")
    _require(contract.get("validation_mode") == "signed_explicit_mapping", "mapping_mismatch", "validation mode")
    for key, commit, path, digest, size in (
        ("frame_manifest", PERSON_A_FRAME_COMMIT, PERSON_A_FRAME_PATH, PERSON_A_FRAME_SHA256, PERSON_A_FRAME_SIZE),
        ("fold_manifest", PERSON_B_PRODUCTION_COMMIT, PERSON_B_FOLD_PATH, PERSON_B_FOLD_SHA256, PERSON_B_FOLD_SIZE),
        ("target_manifest", PERSON_B_PRODUCTION_COMMIT, PERSON_B_TARGET_PATH, PERSON_B_TARGET_SHA256, PERSON_B_TARGET_SIZE),
    ):
        reference = document.get(key)
        _require(isinstance(reference, Mapping), "authority_mismatch", f"{key} missing")
        _require(reference.get("source_commit") == commit, "authority_mismatch", f"{key} commit")
        _require(reference.get("path") == path, "authority_mismatch", f"{key} path")
        _require(reference.get("sha256") == digest, "authority_mismatch", f"{key} hash")
        _require(reference.get("byte_size") == size, "authority_mismatch", f"{key} size")
    frame = document["frame_manifest"]
    _require(frame.get("preprocessed_frame_count") == PERSON_A_FRAME_COUNT, "frame_mismatch", "frame count")
    _require(frame.get("unique_row_count") == PERSON_A_FRAME_COUNT, "frame_mismatch", "unique row count")
    predictions = document.get("person_b_predictions")
    _require(isinstance(predictions, Mapping), "prediction_boundary_mismatch", "prediction boundary missing")
    _require(predictions.get("direct_input_to_person_d") is False, "prediction_boundary_mismatch", "B predictions direct input")
    _require(predictions.get("metrics_pending_person_d") is True, "prediction_boundary_mismatch", "B metrics status")
    _require(predictions.get("reserved_for_later_comparison") is True, "prediction_boundary_mismatch", "B comparison reservation")
    _require(predictions.get("byte_size") == 84257218, "prediction_boundary_mismatch", "B prediction size")
    _require(predictions.get("sha256") == "01e792c4d7b58bbe4ae478195b1d9523802db5674ee06ebbf5364482f42061ba", "prediction_boundary_mismatch", "B prediction hash")
    _require(predictions.get("path") == "/home/sagemaker-user/person-b-step4-1-approved-outputs/person-b-step4-1-production-v0-1/fitted_probes_and_predictions.json", "prediction_boundary_mismatch", "B prediction path")
    runtime_inputs = document.get("runtime_inputs")
    _require(isinstance(runtime_inputs, Mapping), "runtime_input_mismatch", "runtime inputs missing")
    _require(runtime_inputs.get("person_a_frame_root") == "/home/sagemaker-user/person-a-step4-1-approved-outputs/person-a-step4-1-preprocessed-frames-v0-1", "runtime_input_mismatch", "A frame root")
    config = runtime_inputs.get("analysis_config")
    _require(isinstance(config, Mapping), "runtime_input_mismatch", "analysis config")
    _require(config.get("path") == ANALYSIS_CONFIG_PATH and config.get("sha256") == ANALYSIS_CONFIG_SHA256 and config.get("byte_size") == ANALYSIS_CONFIG_SIZE, "runtime_input_mismatch", "analysis config identity")
    source_context = runtime_inputs.get("source_context_manifest")
    _require(isinstance(source_context, Mapping), "runtime_input_mismatch", "source context")
    _require(source_context.get("source_commit") == PERSON_B_BASELINE_COMMIT and source_context.get("path") == SOURCE_CONTEXT_PATH and source_context.get("sha256") == SOURCE_CONTEXT_SHA256 and source_context.get("byte_size") == SOURCE_CONTEXT_SIZE, "runtime_input_mismatch", "source context identity")
    configuration = document.get("configuration")
    _require(isinstance(configuration, Mapping), "configuration_mismatch", "family configuration missing")
    expected_configuration = {
        "constant_velocity": {"fit_required": False, "randomness": "none"},
        "explicit_feature": {"alpha_grid": [0.1, 1.0, 10.0, 100.0], "inner_fold_count": 4, "scaler_fit_scope": "outer_training_rows_only", "seed": 20260719},
        "grouped_shuffled": {"alignment_key": "model_frame_idx", "grouping_unit": "trajectory_id", "permutation_seed": 20260720, "requires_derangement": True},
        "known_q_analytic": {"fair_baseline": False, "formula": "ln(sqrt(q_scripted_blocks2_per_s * tau))", "randomness": "none"},
        "last_seen": {"fit_required": False, "randomness": "none"},
        "raw_pixel": {"alpha_grid": [0.1, 1.0, 10.0, 100.0], "frame_scope": "exact_current_preprocessed_frame_only", "inner_fold_count": 4, "scaler_fit_scope": "outer_training_rows_only", "seed": 20260719},
        "time_only": {"fit_scope": "outer_training_folds_only", "primary_polynomial_degree": 1, "sensitivity_polynomial_degree": 2},
        "visible_history_q": {"dt_seconds": 0.05, "fit_scope": "outer_training_folds_only", "q_estimator": "visible_increment_residual_variance_over_dt"},
    }
    _require(configuration == expected_configuration, "configuration_mismatch", "frozen family configuration")
    contract_source = document.get("d_runner_family_contract_source")
    _require(isinstance(contract_source, Mapping), "configuration_source_mismatch", "D family contract source")
    _require(contract_source.get("commit") == PERSON_D_RUNNER_COMMIT, "configuration_source_mismatch", "D contract commit")
    _require(contract_source.get("path") == PERSON_D_FAMILY_CONTRACT_PATH, "configuration_source_mismatch", "D contract path")
    _require(contract_source.get("symbol") == PERSON_D_FAMILY_CONTRACT_SYMBOL, "configuration_source_mismatch", "D contract symbol")
    _require(contract_source.get("byte_size") == PERSON_D_FAMILY_CONTRACT_SIZE, "configuration_source_mismatch", "D contract size")
    _require(contract_source.get("sha256") == PERSON_D_FAMILY_CONTRACT_SHA256, "configuration_source_mismatch", "D contract hash")
    if repo_root is not None:
        source = _git_bytes(repo_root, PERSON_D_RUNNER_COMMIT, PERSON_D_FAMILY_CONTRACT_PATH)
        _require(len(source) == PERSON_D_FAMILY_CONTRACT_SIZE, "configuration_source_mismatch", "D contract object size")
        _require(_sha256(source) == PERSON_D_FAMILY_CONTRACT_SHA256, "configuration_source_mismatch", "D contract object hash")
        _require(configuration == _extract_d_family_configuration(source), "configuration_mismatch", "D contract configuration differs")
    _require(document.get("u4_output_inspected") is False, "u4_reference", "authority U4 claim")


def _artifact_reference_matches(
    repo_root: Path,
    *,
    commit: str,
    path: str,
    expected_sha256: str,
    expected_size: int,
) -> bytes:
    raw = _git_bytes(repo_root, commit, path)
    _require(len(raw) == expected_size, "artifact_size_mismatch", path)
    _require(_sha256(raw) == expected_sha256, "artifact_hash_mismatch", path)
    return raw


def _frame_key(record: Mapping[str, Any]) -> tuple[str, int]:
    trajectory = record.get("trajectory_id")
    frame_idx = record.get("model_frame_idx")
    _require(isinstance(trajectory, str) and isinstance(frame_idx, int), "frame_identity_mismatch", "frame key")
    return trajectory, frame_idx


def _validate_manifests(repo_root: Path, authority: Mapping[str, Any]) -> None:
    frame_raw = _artifact_reference_matches(
        repo_root,
        commit=PERSON_A_FRAME_COMMIT,
        path=PERSON_A_FRAME_PATH,
        expected_sha256=PERSON_A_FRAME_SHA256,
        expected_size=PERSON_A_FRAME_SIZE,
    )
    fold_raw = _artifact_reference_matches(
        repo_root,
        commit=PERSON_B_PRODUCTION_COMMIT,
        path=PERSON_B_FOLD_PATH,
        expected_sha256=PERSON_B_FOLD_SHA256,
        expected_size=PERSON_B_FOLD_SIZE,
    )
    target_raw = _artifact_reference_matches(
        repo_root,
        commit=PERSON_B_PRODUCTION_COMMIT,
        path=PERSON_B_TARGET_PATH,
        expected_sha256=PERSON_B_TARGET_SHA256,
        expected_size=PERSON_B_TARGET_SIZE,
    )
    runtime_inputs = authority["runtime_inputs"]
    config = runtime_inputs["analysis_config"]
    _artifact_reference_matches(
        repo_root,
        commit=PERSON_B_BASELINE_COMMIT,
        path=ANALYSIS_CONFIG_PATH,
        expected_sha256=config["sha256"],
        expected_size=config["byte_size"],
    )
    source_context = runtime_inputs["source_context_manifest"]
    _artifact_reference_matches(
        repo_root,
        commit=source_context["source_commit"],
        path=source_context["path"],
        expected_sha256=source_context["sha256"],
        expected_size=source_context["byte_size"],
    )
    frame = _parse_json(frame_raw, PERSON_A_FRAME_PATH)
    fold = _parse_json(fold_raw, PERSON_B_FOLD_PATH)
    target = _parse_json(target_raw, PERSON_B_TARGET_PATH)
    records = frame.get("records")
    memberships = fold.get("memberships")
    target_rows = target.get("rows")
    _require(isinstance(records, Sequence) and not isinstance(records, (str, bytes)), "frame_mismatch", "frame records")
    _require(isinstance(memberships, Sequence) and not isinstance(memberships, (str, bytes)), "fold_mismatch", "fold memberships")
    _require(isinstance(target_rows, Sequence) and not isinstance(target_rows, (str, bytes)), "target_mismatch", "target rows")
    _require(len(records) == PERSON_A_FRAME_COUNT, "frame_mismatch", "record count")
    _require(len(memberships) == PERSON_A_FRAME_COUNT, "fold_mismatch", "membership count")
    _require(len(target_rows) == PERSON_A_FRAME_COUNT, "target_mismatch", "target row count")
    _require(frame.get("artifact_count") == PERSON_A_FRAME_COUNT and frame.get("unique_frame_count") == PERSON_A_FRAME_COUNT, "frame_mismatch", "frame artifact counts")
    _require(frame.get("missing_frame_count") == 0 and frame.get("duplicate_frame_count") == 0, "frame_mismatch", "frame missing/duplicate counts")
    _require(fold.get("admitted_frame_count") == PERSON_A_FRAME_COUNT, "fold_mismatch", "admitted frame count")
    _require(fold.get("excluded_frame_count") == 179, "fold_mismatch", "excluded frame count")
    _require(fold.get("seed") == 20260719 and fold.get("n_splits") == 5, "fold_mismatch", "seed/fold count")
    _require(fold.get("fold_manifest_format_version") == "person-b-ten-pilot-frame-fold-v0.1", "fold_mismatch", "format version")
    _require(fold.get("fold_schema_version") == "person-b-fold-v0.1", "fold_mismatch", "schema version")
    _require(fold.get("random_split_used") is False and fold.get("synthetic") is False, "fold_mismatch", "fold safety flags")
    _require(tuple(fold.get("accepted_pilot_ids", ())) == EXPECTED_PILOTS, "fold_mismatch", "pilot order")
    _require(tuple(target.get("accepted_pilot_ids", ())) == EXPECTED_PILOTS, "target_mismatch", "target pilot order")
    assignments = fold.get("layout_assignments")
    _require(isinstance(assignments, Sequence) and not isinstance(assignments, (str, bytes)), "mapping_mismatch", "layout assignments")
    actual_mapping = tuple(item.get("fold_idx") for item in assignments if isinstance(item, Mapping))
    actual_layouts = tuple(item.get("layout_id") for item in assignments if isinstance(item, Mapping))
    _require(actual_layouts == EXPECTED_LAYOUT_IDS, "mapping_mismatch", "layout order")
    _require(actual_mapping == EXPECTED_ASSIGNMENT, "mapping_mismatch", "signed assignment")
    row_counts = fold.get("row_counts")
    _require(isinstance(row_counts, Mapping), "mapping_mismatch", "row counts")
    admitted_by_layout = row_counts.get("admitted_by_layout")
    _require(isinstance(admitted_by_layout, Sequence), "mapping_mismatch", "layout counts")
    counts = tuple(item.get("row_count") for item in admitted_by_layout if isinstance(item, Mapping))
    layouts = tuple(item.get("layout_id") for item in admitted_by_layout if isinstance(item, Mapping))
    _require(layouts == EXPECTED_LAYOUT_IDS and counts == EXPECTED_LAYOUT_COUNTS, "mapping_mismatch", "layout row counts")
    _require(target.get("row_count") == PERSON_A_FRAME_COUNT and target.get("schema_version") == "1.0", "target_mismatch", "target metadata")
    _require(target.get("input_manifest_hash") == fold.get("artifact_hash"), "target_mismatch", "target input binding")
    _require(target.get("synthetic") is False and target.get("u4_output_inspected") is False, "target_mismatch", "target safety flags")
    membership_by_key: dict[tuple[str, int], Mapping[str, Any]] = {}
    target_by_key: dict[tuple[str, int], Mapping[str, Any]] = {}
    for membership in memberships:
        _require(isinstance(membership, Mapping), "fold_mismatch", "membership object")
        key = _frame_key(membership)
        _require(key not in membership_by_key, "fold_mismatch", "duplicate membership")
        membership_by_key[key] = membership
    for target_row in target_rows:
        _require(isinstance(target_row, Mapping), "target_mismatch", "target row object")
        key = _frame_key(target_row)
        _require(key not in target_by_key, "target_mismatch", "duplicate target row")
        target_by_key[key] = target_row
    _require(set(membership_by_key) == set(target_by_key), "lineage_mismatch", "fold/target identities differ")
    frame_keys: set[tuple[str, int]] = set()
    mapping_by_layout = dict(zip(EXPECTED_LAYOUT_IDS, EXPECTED_ASSIGNMENT, strict=True))
    for record in records:
        _require(isinstance(record, Mapping), "frame_mismatch", "record object")
        key = _frame_key(record)
        _require(key not in frame_keys, "frame_mismatch", "duplicate frame identity")
        frame_keys.add(key)
        membership = membership_by_key.get(key)
        target_row = target_by_key.get(key)
        _require(membership is not None and target_row is not None, "lineage_mismatch", "unknown frame identity")
        _require(record.get("payload_sha256") and isinstance(record.get("payload_sha256"), str), "frame_mismatch", "payload hash")
        _require(record.get("payload_byte_size") == 1032192, "frame_mismatch", "payload byte size")
        _require(isinstance(record.get("output_relative_path"), str), "frame_mismatch", "payload path")
        _require(record.get("target_binding", {}).get("target_manifest_sha256") == PERSON_B_TARGET_SHA256, "lineage_mismatch", "frame target hash")
        _require(record.get("target_binding", {}).get("target_id") == target_row.get("target_id"), "lineage_mismatch", "frame target id")
        _require(record.get("fold_binding", {}).get("fold_idx") == membership.get("fold_idx"), "lineage_mismatch", "frame fold")
        _require(record.get("fold_binding", {}).get("fold_idx") == mapping_by_layout.get(record.get("layout_id")), "mapping_mismatch", "frame layout fold")
        _require(record.get("direct_input_eligibility_by_family", {}).get("raw_pixel") is True, "frame_mismatch", "raw pixel eligibility")
    _require(frame_keys == set(membership_by_key), "frame_mismatch", "frame identities do not cover all memberships")
    _require(frame.get("fold_manifest_sha256") == PERSON_B_FOLD_SHA256, "lineage_mismatch", "frame fold manifest hash")
    _require(frame.get("target_manifest_sha256") == PERSON_B_TARGET_SHA256, "lineage_mismatch", "frame target manifest hash")
    _require(authority.get("frame_manifest", {}).get("preprocessed_frame_count") == len(frame_keys), "frame_mismatch", "authority frame count")


def _validate_git_sources(repo_root: Path, evidence: Mapping[str, Any]) -> None:
    _validate_remote_head(repo_root)
    _require(_is_ancestor(repo_root, PERSON_D_SIGNED_COMMIT, PERSON_D_RUNNER_COMMIT), "git_ancestry_mismatch", "signed validator is not runner ancestor")
    _require(_is_ancestor(repo_root, PERSON_D_EXPORTER_COMMIT, PERSON_D_RUNNER_COMMIT), "git_ancestry_mismatch", "exporter is not runner ancestor")
    _require(_is_ancestor(repo_root, PERSON_D_CLI_COMMIT, PERSON_D_RUNNER_COMMIT), "git_ancestry_mismatch", "CLI is not runner ancestor")
    for field, commit, path in (
        ("signed_validator_source", PERSON_D_SIGNED_COMMIT, PERSON_D_SIGNED_VALIDATOR_PATH),
        ("signed_dispatch_source", PERSON_D_SIGNED_COMMIT, PERSON_D_EXPORT_PATH),
        ("d_runner_source", PERSON_D_RUNNER_COMMIT, PERSON_D_RUNNER_PATH),
        ("historical_cli_source", PERSON_D_CLI_COMMIT, PERSON_D_RUNNER_PATH),
    ):
        reference = evidence.get(field)
        _require(isinstance(reference, Mapping), "source_mismatch", f"{field} missing")
        raw = _git_bytes(repo_root, commit, path)
        _require(reference.get("source_commit") == commit, "source_mismatch", f"{field} commit")
        _require(reference.get("path") == path, "source_mismatch", f"{field} path")
        _require(reference.get("byte_size") == len(raw), "source_mismatch", f"{field} size")
        _require(reference.get("sha256") == _sha256(raw), "source_mismatch", f"{field} hash")
    dispatch = _git_bytes(repo_root, PERSON_D_SIGNED_COMMIT, PERSON_D_EXPORT_PATH).decode("utf-8")
    for needle in (
        "fold_manifest_format_version",
        "PRODUCTION_FOLD_MANIFEST_FORMAT_VERSION",
        "validate_production_fold_document",
        "validate_fold_manifest",
        "unknown fold_manifest_format_version",
    ):
        _require(needle in dispatch, "dispatch_mismatch", needle)
    runner = _git_bytes(repo_root, PERSON_D_RUNNER_COMMIT, PERSON_D_RUNNER_PATH).decode("utf-8")
    for needle in (
        'choices=("preflight", "materialize", "run")',
        "def run_materialize",
        "def run_preflight",
        "def run_production",
        "run_production(",
        "--authorization-record-path",
        "--frame-manifest-path",
        "--frame-root",
        "--verify-payloads",
        "--fold-manifest-path",
        "--target-manifest-path",
        "--source-context-manifest-path",
        "--source-context-root",
        "--analysis-config-path",
        "--resume",
        'verify_payloads = args.verify_payloads or args.mode == "run"',
        'if args.mode == "materialize"',
        'if args.mode == "preflight"',
    ):
        _require(needle in runner, "cli_wiring_mismatch", needle)


def _validate_compatibility(repo_root: Path, evidence: Mapping[str, Any]) -> None:
    checks = evidence.get("checks")
    _require(isinstance(checks, Mapping), "compatibility_mismatch", "checks missing")
    for key in (
        "cli_dispatches_materialize_preflight_and_run",
        "cli_forces_payload_verification_for_run",
        "cli_reuses_run_production",
        "d_real_manifest_receipt_is_pass",
        "historical_dispatch_preserved",
        "signed_explicit_mapping_dispatch_present",
    ):
        _require(checks.get(key) is True, "compatibility_mismatch", key)
    receipt_ref = evidence.get("d_real_manifest_receipt")
    _require(isinstance(receipt_ref, Mapping), "compatibility_mismatch", "real receipt reference")
    raw = _artifact_reference_matches(
        repo_root,
        commit=PERSON_D_RUNNER_COMMIT,
        path=PERSON_D_REAL_RECEIPT_PATH,
        expected_sha256=PERSON_D_REAL_RECEIPT_SHA256,
        expected_size=PERSON_D_REAL_RECEIPT_SIZE,
    )
    _require(receipt_ref.get("source_commit") == PERSON_D_RUNNER_COMMIT, "compatibility_mismatch", "receipt commit")
    _require(receipt_ref.get("path") == PERSON_D_REAL_RECEIPT_PATH, "compatibility_mismatch", "receipt path")
    _require(receipt_ref.get("sha256") == _sha256(raw) and receipt_ref.get("byte_size") == len(raw), "compatibility_mismatch", "receipt identity")
    receipt = _parse_json(raw, PERSON_D_REAL_RECEIPT_PATH)
    _require(receipt.get("real_contexts_built") == PERSON_A_FRAME_COUNT, "compatibility_mismatch", "receipt context count")
    _require(tuple(receipt.get("signed_fold_to_layout_assignment", ())) == EXPECTED_ASSIGNMENT, "compatibility_mismatch", "receipt assignment")
    _require(receipt.get("scientific_execution_performed") is False and receipt.get("u4_output_inspected") is False, "compatibility_mismatch", "receipt safety claims")
    checks_in_receipt = receipt.get("checks")
    _require(isinstance(checks_in_receipt, Mapping), "compatibility_mismatch", "receipt checks")
    for key in (
        "accepted_mapping_equals_signed_assignment",
        "all_admitted_row_identities_validate",
        "all_ten_pilots_exact",
        "fold_contract_version_exact",
        "production_preflight_accepts_the_exact_real_manifest",
        "target_binding_passes",
        "validation_mode_is_signed_explicit_mapping",
        "zero_cross_fold_leakage",
        "zero_duplicate_rows",
        "no_baseline_fit_occurred",
    ):
        _require(checks_in_receipt.get(key) is True, "compatibility_mismatch", f"receipt.{key}")
    branch_record = evidence.get("branch_local_authorization_record")
    _require(isinstance(branch_record, Mapping), "runtime_authorization_mismatch", "D branch authorization record")
    branch_raw = _artifact_reference_matches(
        repo_root,
        commit=PERSON_D_RUNNER_COMMIT,
        path=PERSON_D_BRANCH_AUTH_PATH,
        expected_sha256=PERSON_D_BRANCH_AUTH_SHA256,
        expected_size=PERSON_D_BRANCH_AUTH_SIZE,
    )
    _require(branch_record.get("source_commit") == PERSON_D_RUNNER_COMMIT, "runtime_authorization_mismatch", "D branch record commit")
    _require(branch_record.get("path") == PERSON_D_BRANCH_AUTH_PATH, "runtime_authorization_mismatch", "D branch record path")
    _require(branch_record.get("sha256") == _sha256(branch_raw) and branch_record.get("byte_size") == len(branch_raw), "runtime_authorization_mismatch", "D branch record identity")
    branch_document = _parse_json(branch_raw, PERSON_D_BRANCH_AUTH_PATH)
    _require(branch_document.get("authorized_branch") == PERSON_D_BRANCH, "runtime_authorization_mismatch", "D branch record branch")
    _require(branch_document.get("authorized_runner_commit") == PERSON_D_SIGNED_COMMIT, "runtime_authorization_mismatch", "D branch record HEAD")
    _require(branch_record.get("recorded_authorized_runner_commit") == PERSON_D_SIGNED_COMMIT, "runtime_authorization_mismatch", "D branch record citation")
    _require(branch_record.get("used_for_this_execution") is False, "runtime_authorization_mismatch", "stale D branch record use")
    _require(evidence.get("external_b_authorization_record_required") is True, "runtime_authorization_mismatch", "external B record requirement")
    _require(evidence.get("external_b_authorization_record_passed_via_cli") is True, "runtime_authorization_mismatch", "external B record CLI binding")
    _validate_git_sources(repo_root, evidence)
    _require(evidence.get("scientific_execution_performed") is False, "execution_claim_mismatch", "compatibility execution")
    _require(evidence.get("u4_output_inspected") is False, "u4_reference", "compatibility U4")


def _validate_remote_head(repo_root: Path, remote_head: str | None = None) -> None:
    """Require the fetched D remote to remain exactly the authorized HEAD."""

    actual = remote_head if remote_head is not None else _git_text(
        repo_root,
        "rev-parse",
        "origin/role/person-d-baselines",
    )
    _require(actual == PERSON_D_RUNNER_COMMIT, "remote_head_mismatch", "origin/role/person-d-baselines")


def _validate_runtime_record(record: Mapping[str, Any]) -> None:
    for key, expected in (
        ("authorized_branch", PERSON_D_BRANCH),
        ("authorized_exporter_ancestor", PERSON_D_EXPORTER_COMMIT),
        ("authorized_runner_commit", PERSON_D_RUNNER_COMMIT),
        ("authorization_record_path_absolute_sagemaker", AUTHORIZATION_RECORD_ABSOLUTE_PATH),
    ):
        _require(record.get(key) == expected, "runtime_authorization_mismatch", key)
    _require(record.get("clean_separate_b_checkout_required") is True, "runtime_authorization_mismatch", "clean B checkout")
    _require(record.get("synchronized_b_checkout_required") is True, "runtime_authorization_mismatch", "synchronized B checkout")
    _require(record.get("person_b_starting_authority") == PERSON_B_FOLD_COMMIT, "runtime_authorization_mismatch", "B starting authority")
    requirements = record.get("runtime_requirements")
    _require(isinstance(requirements, Mapping), "runtime_authorization_mismatch", "runtime requirements")
    _require(requirements.get("device") == "cpu", "runtime_authorization_mismatch", "device")
    _require(requirements.get("python_requires") == ">=3.10", "runtime_authorization_mismatch", "python")
    _require(requirements.get("seed_source") == "configs/analysis/core.yaml", "runtime_authorization_mismatch", "seed source")
    _require(requirements.get("split_seed") == 20260719, "runtime_authorization_mismatch", "seed")
    _require(record.get("scientific_execution_performed") is False and record.get("u4_output_inspected") is False, "runtime_authorization_mismatch", "runtime safety claims")


def _validate_commands(commands: Mapping[str, Any]) -> None:
    auth_path = AUTHORIZATION_RECORD_ABSOLUTE_PATH
    materialize = commands.get("materialize_command")
    preflight = commands.get("preflight_command")
    run = commands.get("run_command")
    _require(all(isinstance(value, str) for value in (materialize, preflight, run)), "command_mismatch", "missing command")
    for label, command in (("materialize", materialize), ("preflight", preflight), ("run", run)):
        _require(auth_path in command, "command_mismatch", f"{label} authorization path")
        _require(not re.search(r"<[^>]+>|\b(?:PLACEHOLDER|TODO)\b|\.\.\.", command), "command_mismatch", f"{label} placeholder")
        _require("scripts/run_person_d_step4_1_eight_family_production.py" in command, "command_mismatch", f"{label} runner")
    _require(" materialize " in materialize, "command_mismatch", "materialize mode")
    _require(" preflight " in preflight, "command_mismatch", "preflight mode")
    _require(" run " in run, "command_mismatch", "run mode")
    _require("--materialize-root /home/sagemaker-user/person-d-step4-1-approved-outputs/person-d-step4-1-materialized-inputs-v0-1" in materialize, "command_mismatch", "materialize root")
    required_run_parts = (
        "--frame-manifest-path /home/sagemaker-user/person-d-step4-1-approved-outputs/person-d-step4-1-materialized-inputs-v0-1/preprocessed_frame_manifest.json",
        "--frame-root /home/sagemaker-user/person-a-step4-1-approved-outputs/person-a-step4-1-preprocessed-frames-v0-1",
        "--fold-manifest-path /home/sagemaker-user/person-d-step4-1-approved-outputs/person-d-step4-1-materialized-inputs-v0-1/ten_pilot_frame_fold_manifest.json",
        "--target-manifest-path /home/sagemaker-user/person-d-step4-1-approved-outputs/person-d-step4-1-materialized-inputs-v0-1/production_oracle_target_manifest.json",
        "--source-context-manifest-path /home/sagemaker-user/person-d-step4-1-approved-outputs/person-d-step4-1-materialized-inputs-v0-1/source_context_manifest.json",
        "--source-context-root /home/sagemaker-user/person-d-step4-1-approved-outputs/person-d-step4-1-materialized-inputs-v0-1",
        "--analysis-config-path configs/analysis/core.yaml",
        "--output-root /home/sagemaker-user/person-d-step4-1-approved-outputs/person-d-step4-1-production-v0-1",
        "--resume resume",
    )
    for part in required_run_parts:
        _require(part in run, "command_mismatch", part)
    _require("--verify-payloads" in preflight and "--verify-payloads" in run, "command_mismatch", "payload verification")
    _require(commands.get("analysis_config_path") == "configs/analysis/core.yaml", "command_mismatch", "config path")
    _require(commands.get("resume") == "resume", "command_mismatch", "resume mode")
    _require(commands.get("scientific_execution_performed") is False and commands.get("u4_output_inspected") is False, "command_mismatch", "command safety claims")


def _validate_closure(repo_root: Path, closure: Mapping[str, Any]) -> None:
    documents = closure.get("baseline_prediction_documents")
    expected_documents = (
        "last_seen__mu_oracle_blocks.json",
        "constant_velocity__mu_oracle_blocks.json",
        "grouped_shuffled__log_sigma_oracle.json",
        "grouped_shuffled__mu_oracle_blocks.json",
        "time_only__log_sigma_oracle.json",
        "explicit_feature__mu_oracle_blocks.json",
        "raw_pixel__mu_oracle_blocks.json",
        "visible_history_q__log_sigma_oracle.json",
        "known_q_analytic__log_sigma_oracle.json",
    )
    _require(tuple(documents or ()) == expected_documents, "closure_mismatch", "family output order")
    _require(isinstance(closure.get("evidence_requirements"), Sequence), "closure_mismatch", "evidence requirements")
    state = closure.get("closure_state")
    _require(isinstance(state, Mapping), "closure_mismatch", "closure state")
    for key in ("artifacts_present_in_this_package", "execution_outputs_claimed", "final_comparison_complete", "step4_1_complete", "u4_output_inspected"):
        _require(state.get(key) is False, "closure_mismatch", key)
    _require(state.get("final_comparison_performed") is False, "closure_mismatch", "final comparison performed")
    run_state = closure.get("expected_run_state")
    _require(isinstance(run_state, Mapping) and run_state.get("family_count") == 8 and run_state.get("schema_version") == "1.0", "closure_mismatch", "run state")
    _require(run_state.get("path") == "/home/sagemaker-user/person-d-step4-1-approved-outputs/person-d-step4-1-production-v0-1/run_state.json", "closure_mismatch", "run state path")
    _require(run_state.get("status_required_before_completion") == "completed", "closure_mismatch", "run state status")
    reference = closure.get("person_e_closure_requirements")
    _require(isinstance(reference, Mapping), "closure_mismatch", "E reference")
    raw = _artifact_reference_matches(repo_root, commit=PERSON_E_COMMIT, path=PERSON_E_CLOSURE_PATH, expected_sha256=PERSON_E_CLOSURE_SHA256, expected_size=PERSON_E_CLOSURE_SIZE)
    _require(reference.get("source_commit") == PERSON_E_COMMIT and reference.get("path") == PERSON_E_CLOSURE_PATH, "closure_mismatch", "E source")
    _require(reference.get("sha256") == _sha256(raw) and reference.get("byte_size") == len(raw), "closure_mismatch", "E source identity")
    e_document = _parse_json(raw, PERSON_E_CLOSURE_PATH)
    _require(e_document.get("closure_claimed") is False and e_document.get("step4_1_scientific_execution_performed") is False and e_document.get("u4_output_inspected") is False, "closure_mismatch", "E closure state")


def _validate_decision(decision: Mapping[str, Any]) -> None:
    expected = {
        "assignment_by_ordered_layout": EXPECTED_ASSIGNMENT,
        "baseline_execution_authorized": True,
        "baseline_execution_performed": False,
        "baseline_family_count": 8,
        "execution_performed": False,
        "final_comparison_complete": False,
        "final_comparison_performed": False,
        "person_b_metrics_pending_person_d": True,
        "person_b_predictions_are_d_direct_input": False,
        "person_d_execution_authorized": True,
        "person_d_execution_ready": True,
        "preprocessed_frame_count": 1695,
        "signed_explicit_mapping_verified": True,
        "scientific_execution_performed": False,
        "step4_1_complete": False,
        "u4_output_inspected": False,
    }
    for key, value in expected.items():
        actual = decision.get(key)
        if key == "assignment_by_ordered_layout":
            actual = tuple(actual or ())
        _require(actual == value, "decision_mismatch", key)
    _require(decision.get("decision") == "AUTHORIZED_PERSON_D_EIGHT_FAMILY_BASELINE_EXECUTION", "decision_mismatch", "decision")


def _validate_receipt(receipt: Mapping[str, Any]) -> None:
    checks = receipt.get("checks")
    _require(isinstance(checks, Mapping), "receipt_mismatch", "checks")
    for key, value in checks.items():
        if key == "u4_output_inspected":
            _require(value is False, "u4_reference", "receipt U4")
        else:
            _require(value is True, "receipt_mismatch", key)
    for key in ("execution_performed", "final_comparison_complete", "final_comparison_performed", "step4_1_complete", "u4_output_inspected"):
        _require(receipt.get(key) is False, "receipt_mismatch", key)
    _require(receipt.get("frame_payload_bytes_read_locally") is False, "payload_claim_mismatch", "payload bytes claim")
    _require(receipt.get("runtime_frame_payload_verification_required") is True, "payload_claim_mismatch", "payload verification requirement")


def validate_package(repo_root: Path, package_root: Path) -> Mapping[str, Any]:
    """Validate package JSON, exact Git authorities, and D compatibility."""

    documents = _load_package(package_root)
    _validate_inventory(package_root, documents)
    _validate_safety_claims(documents)
    _validate_authority(documents["authority_binding.json"], repo_root)
    _validate_manifests(repo_root, documents["authority_binding.json"])
    _validate_compatibility(repo_root, documents["person_d_compatibility_evidence.json"])
    _validate_runtime_record(documents["person_d_runtime_authorization.json"])
    _validate_commands(documents["production_commands.json"])
    _validate_closure(repo_root, documents["output_closure_requirements.json"])
    _validate_decision(documents["final_authorization_decision.json"])
    _validate_receipt(documents["validation_receipt.json"])
    return {
        "accepted": True,
        "baseline_family_count": 8,
        "preprocessed_frame_count": 1695,
        "signed_explicit_mapping_verified": True,
        "person_d_execution_ready": True,
        "baseline_execution_performed": False,
        "execution_performed": False,
        "final_comparison_complete": False,
        "final_comparison_performed": False,
        "scientific_execution_performed": False,
        "step4_1_complete": False,
        "u4_output_inspected": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--package-root", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    package_root = (args.package_root or repo_root / PACKAGE_RELATIVE_PATH).resolve()
    try:
        result = validate_package(repo_root, package_root)
    except (FinalPersonDAuthorizationError, OSError) as error:
        if args.json:
            print(json.dumps({"accepted": False, "error": str(error)}, sort_keys=True))
        else:
            print(f"FAIL: {error}")
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print("PASS: Person B eight-family Person D execution authorization validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
