"""Fail-closed runtime boundary for the ratified Step 4.1 comparison."""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import shutil
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mineocclude.analysis.step4_1_bounded_reveal_v0_1 import (
    validate_bounded_reveal_contract,
    validate_prediction_rows,
)
from mineocclude.analysis.step4_1_final_comparison_v0_1 import (
    BOUNDED_REVEAL_CONTRACT_COMMIT,
    BOUNDED_REVEAL_PREDICTION_COUNT,
    BOUNDED_REVEAL_PREDICTIONS_SHA256,
    COMPARISON_CONTRACT_COMMIT,
    E_COMPARISON_RATIFICATION_COMMIT,
    FINAL_OUTPUT_FILENAMES,
    PERSON_B_PREDICTIONS_SHA256,
    PERSON_D_COMPLETION_COMMIT,
    PERSON_D_COMPLETION_SHA256,
    ComparisonDataset,
    FinalComparisonExecutionError,
    compute_final_comparison,
    frozen_method_configuration,
    inconclusive_output_documents,
    validate_frozen_contract,
    validate_method_configuration,
    validate_output_documents,
)
from mineocclude.analysis.step4_1_final_contract_v0_1 import (
    build_final_comparison_contract,
)
from mineocclude.experiments.registry import formatted_json_bytes

PERSON_B_BRANCH = "role/person-b-analysis"
FINAL_OUTPUT_ROOT = Path(
    "/home/sagemaker-user/person-b-step4-1-approved-outputs/"
    "person-b-step4-1-final-comparison-v0-1"
)
PERSON_B_PREDICTION_PATH = Path(
    "/home/sagemaker-user/person-b-step4-1-approved-outputs/"
    "person-b-step4-1-production-v0-1/fitted_probes_and_predictions.json"
)
PERSON_D_ROOT = Path(
    "/home/sagemaker-user/person-d-step4-1-approved-outputs/"
    "person-d-step4-1-production-v0-1"
)
POST_REVEAL_PATH = Path(
    "/home/sagemaker-user/person-b-step4-1-approved-outputs/"
    "person-b-step4-1-bounded-reveal-v0-1/post_reveal_predictions.json"
)


def exact_execution_command() -> list[str]:
    """Return the one non-placeholder SageMaker command ratified for execution."""

    return [
        "python",
        "scripts/run_person_b_step4_1_final_comparison.py",
        "--repository-root",
        "$PWD",
        "--person-b-contract-commit",
        BOUNDED_REVEAL_CONTRACT_COMMIT,
        "--person-e-ratification-commit",
        "origin/role/person-e-operations",
        "--person-b-predictions",
        PERSON_B_PREDICTION_PATH.as_posix(),
        "--person-d-root",
        PERSON_D_ROOT.as_posix(),
        "--post-reveal-predictions",
        POST_REVEAL_PATH.as_posix(),
        "--output-root",
        FINAL_OUTPUT_ROOT.as_posix(),
        "--mode",
        "run",
        "--resume",
        "validate-complete-no-write",
    ]

COMPARISON_PACKAGE = (
    "docs/status/person_b_phase4_step4_1_final_comparison_contract_v0_1"
)
COMPARISON_CONTRACT_PATH = f"{COMPARISON_PACKAGE}/final_comparison_contract.json"
COMPARISON_CONTRACT_SHA256 = (
    "ca80d850ce9a9d320dcba878de1abdfcfed3648d2770d6b91ab2156a6cb6340e"
)
COMPARISON_CONTRACT_BYTE_SIZE = 18881
BOUNDED_PACKAGE = (
    "docs/status/person_b_phase4_step4_1_bounded_reveal_contract_v0_1"
)
BOUNDED_CONTRACT_PATH = f"{BOUNDED_PACKAGE}/bounded_reveal_contract.json"
BOUNDED_CONTRACT_SHA256 = (
    "28684ece32b8898a7a669482f6b640504738cb4eaf3aea091e6988c79a79d835"
)
BOUNDED_CONTRACT_BYTE_SIZE = 15476
E_RATIFICATION_PATH = (
    "docs/status/person_e_phase4_step4_1_final_comparison_ratification_v0_1/"
    "final_comparison_ratification.json"
)
E_RATIFICATION_SHA256 = (
    "e3199cc3b44a6987fc3dec0ce65d32a65240bb442a702d391316bdd87a8e0e24"
)
E_RATIFICATION_BYTE_SIZE = 2727
E_EXECUTION_AUTHORIZATION_PATH = (
    "docs/status/person_e_phase4_step4_1_final_comparison_execution_authorization_v0_1/"
    "execution_authorization.json"
)
POSITIVE_CONTROL_PATH = (
    "docs/status/person_b_phase6_step6_6_positive_control_v0_1/"
    "positive_control_decision.json"
)
POSITIVE_CONTROL_COMMIT = "e39fef4a59142a84dfb5991d51deeb506eb23a7b"
POSITIVE_CONTROL_SHA256 = (
    "742557b32326180003b1cd83ed5db6f1a1ebfebd692d969809698d323f239056"
)

LOCAL_INPUT_REFERENCES = {
    "analysis_config": {
        "path": "configs/analysis/core.yaml",
        "byte_size": 4881,
        "sha256": "b2e12e7049e0494c756be442a4f300cbc7dc0a6e262deecf682f1354e887f0ab",
    },
    "fold_manifest": {
        "path": (
            "docs/status/person_b_phase4_step4_1_production_handoff_v0_1/"
            "ten_pilot_frame_fold_manifest.json"
        ),
        "byte_size": 742601,
        "sha256": "53ca938c6ae936c3ecb6e6e8d95a3fda152f5fa130b52e7a000d297810738d71",
    },
    "oracle_target": {
        "path": (
            "docs/status/person_b_phase4_step4_1_production_handoff_v0_1/"
            "production_oracle_target_manifest.json"
        ),
        "byte_size": 4934874,
        "sha256": "afcf3afae00db6330665afc5964608c6db89eeac3767c9486d8ba0a218858282",
    },
    "applicability": {
        "path": (
            "docs/status/person_b_phase4_step4_1_applicability_contract_v0_1/"
            "family_target_applicability_contract.json"
        ),
        "sha256": "3ee4991589b828007091811823cb6e26fbfecc14a2c0331629cf6a014b131103",
    },
}

D_PREDICTION_REFERENCES = (
    ("last_seen", "mu_oracle_blocks", "48481740b50d41f87ac78ef7e2a4a1be930c400f197613c13212f7bfdb4bf4ae", 404704, 1695),
    ("constant_velocity", "mu_oracle_blocks", "1156b6ca9bdc72355c23f8bcd2cbe9ba0324ad9e861fee47a246e5ef0a09fc7a", 417255, 1690),
    ("grouped_shuffled", "log_sigma_oracle", "cc182dfa1795eba5eb59c98dfb54d1d7eda9a39e6f3188846c863d9b12142fcc", 121603, 493),
    ("grouped_shuffled", "mu_oracle_blocks", "db190c7fdd99e0eb075cdf603b9e7bb516caa857d2f1167e5ecf8da84c315ba5", 346725, 1428),
    ("time_only", "log_sigma_oracle", "aa8a60d9ee36a27655abd0a13b5aba2665aa5d865a9332c3f2a840cfbae5d273", 168182, 695),
    ("explicit_feature", "mu_oracle_blocks", "c724dc1b8918556508e4b4260315b16cf294977d51231f7c05963bc27ea973e7", 416276, 1690),
    ("raw_pixel", "mu_oracle_blocks", "bb0a15f9d2d54f53e46c6a201d464958f2f8db90decba5784e81a99ff2298420", 405896, 1695),
    ("visible_history_q", "log_sigma_oracle", "5ef20829a26a09d4c1407c8d398cc1429266b2b45ae233fe4679d35f57c24bbc", 173068, 695),
    ("known_q_analytic", "log_sigma_oracle", "f589af2acc429460b8e9fc2725401e2adb5c0ce6424f73f3867fa43bda8ff2cd", 173176, 695),
)


@dataclass(frozen=True)
class ExecutionRequest:
    repository_root: Path
    person_b_contract_commit: str
    person_e_ratification_commit: str
    person_b_predictions: Path
    person_d_root: Path
    post_reveal_predictions: Path
    output_root: Path
    mode: str = "run"
    resume: str = "validate-complete-no-write"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _reject_constant(value: str) -> None:
    raise FinalComparisonExecutionError(f"Non-finite JSON constant {value!r} is forbidden.")


def _pairs_no_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FinalComparisonExecutionError(f"Duplicate JSON key {key!r} is forbidden.")
        result[key] = value
    return result


def decode_strict_json(payload: bytes, *, label: str) -> Any:
    """Decode canonical inputs while rejecting duplicate keys and NaN/Infinity."""

    try:
        document = json.loads(
            payload.decode("utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_pairs_no_duplicates,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FinalComparisonExecutionError(f"Could not decode {label}: {error}") from error
    return document


def _read_bytes(path: Path, *, label: str) -> bytes:
    if path.is_symlink():
        raise FinalComparisonExecutionError(f"{label} cannot be a symlink.")
    try:
        return path.read_bytes()
    except OSError as error:
        raise FinalComparisonExecutionError(f"Could not read {label}: {error}") from error


def _read_exact(
    path: Path,
    *,
    label: str,
    sha256: str,
    byte_size: int | None = None,
) -> tuple[bytes, Any]:
    payload = _read_bytes(path, label=label)
    if (byte_size is not None and len(payload) != byte_size) or _sha256(payload) != sha256:
        raise FinalComparisonExecutionError(f"{label} byte identity differs.")
    return payload, decode_strict_json(payload, label=label)


def _git(repository: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise FinalComparisonExecutionError(f"Git authority read failed: {error}") from error
    return result.stdout.strip()


def _git_bytes(repository: Path, revision: str, path: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "show", f"{revision}:{path}"],
            cwd=repository,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise FinalComparisonExecutionError(
            f"Could not read exact Git object {revision}:{path}: {error}"
        ) from error
    return result.stdout


def _exact_git_json(
    repository: Path,
    revision: str,
    path: str,
    *,
    sha256: str,
    byte_size: int | None = None,
) -> Mapping[str, Any]:
    payload = _git_bytes(repository, revision, path)
    if (byte_size is not None and len(payload) != byte_size) or _sha256(payload) != sha256:
        raise FinalComparisonExecutionError(f"Git object identity differs for {path}.")
    document = decode_strict_json(payload, label=path)
    if not isinstance(document, Mapping):
        raise FinalComparisonExecutionError(f"Git object {path} is not a JSON object.")
    return document


def validate_bounded_reveal_payload(
    payload: bytes,
    *,
    expected_sha256: str = BOUNDED_REVEAL_PREDICTIONS_SHA256,
    expected_count: int = BOUNDED_REVEAL_PREDICTION_COUNT,
) -> Mapping[str, Any]:
    """Validate completed reveal bytes without exposing their row payloads."""

    if _sha256(payload) != expected_sha256:
        raise FinalComparisonExecutionError("Bounded-reveal prediction SHA-256 differs.")
    document = decode_strict_json(payload, label="bounded-reveal predictions")
    if not isinstance(document, Mapping):
        raise FinalComparisonExecutionError("Bounded-reveal predictions are not an object.")
    rows = document.get("rows")
    if (
        document.get("schema_id")
        != "person-b-step4-1-bounded-reveal-predictions-v0-1"
        or document.get("schema_version") != "1.0"
        or document.get("prediction_count") != expected_count
        or document.get("u4_output_inspected") is not False
        or not isinstance(rows, list)
        or len(rows) != expected_count
    ):
        raise FinalComparisonExecutionError("Bounded-reveal prediction envelope differs.")
    required_authorities = {
        "comparison_contract_commit": COMPARISON_CONTRACT_COMMIT,
        "person_b_contract_commit": BOUNDED_REVEAL_CONTRACT_COMMIT,
        "person_e_authorization_commit": (
            "99fb896ed8e6a3b187272fe078706bc7b17666d8"
        ),
    }
    for field, expected in required_authorities.items():
        if document.get(field) != expected:
            raise FinalComparisonExecutionError(
                f"Bounded-reveal authority differs at {field}."
            )
    try:
        validate_prediction_rows(rows)
    except ValueError as error:
        raise FinalComparisonExecutionError(str(error)) from error
    events = {
        event["event_id"]: event
        for event in build_final_comparison_contract()["reveal_event_contract"]
    }
    for row in rows:
        event = events[row["event_id"]]
        exact_identity = {
            "fold_idx": event["fold_idx"],
            "layout_id": event["layout_id"],
            "model_frame_idx": event["post_model_frame_idx"],
            "trajectory_id": event["trajectory_id"],
        }
        for field, expected in exact_identity.items():
            if row.get(field) != expected:
                raise FinalComparisonExecutionError(
                    f"Bounded-reveal row differs at {field}."
                )
    return document


def load_bounded_reveal_artifact(path: Path) -> tuple[Mapping[str, Any], dict[str, str]]:
    payload = _read_bytes(path, label="bounded-reveal predictions")
    document = validate_bounded_reveal_payload(payload)
    root = path.parent
    inventory_payload = _read_bytes(root / "sha256_inventory.json", label="reveal inventory")
    inventory = decode_strict_json(inventory_payload, label="reveal inventory")
    receipt_payload = _read_bytes(root / "execution_receipt.json", label="reveal receipt")
    receipt = decode_strict_json(receipt_payload, label="reveal receipt")
    expected_files = {
        "execution_receipt.json": _sha256(receipt_payload),
        "post_reveal_predictions.json": BOUNDED_REVEAL_PREDICTIONS_SHA256,
    }
    if (
        not isinstance(inventory, Mapping)
        or inventory.get("files") != expected_files
        or inventory.get("inventory_excludes_self") is not True
        or not isinstance(receipt, Mapping)
    ):
        raise FinalComparisonExecutionError("Bounded-reveal package inventory differs.")
    required_receipt = {
        "additional_person_a_extraction_performed": False,
        "fitted_probe_input_sha256": PERSON_B_PREDICTIONS_SHA256,
        "metrics_computed": False,
        "person_b_contract_commit": BOUNDED_REVEAL_CONTRACT_COMMIT,
        "person_e_authorization_commit": (
            "99fb896ed8e6a3b187272fe078706bc7b17666d8"
        ),
        "prediction_count": BOUNDED_REVEAL_PREDICTION_COUNT,
        "probe_refit_performed": False,
        "u4_output_inspected": False,
    }
    for field, expected in required_receipt.items():
        if receipt.get(field) != expected:
            raise FinalComparisonExecutionError(f"Reveal receipt differs at {field}.")
    return document, {
        "bounded_reveal_predictions": BOUNDED_REVEAL_PREDICTIONS_SHA256,
        "bounded_reveal_execution_receipt": _sha256(receipt_payload),
        "bounded_reveal_inventory": _sha256(inventory_payload),
    }


def _load_contract_authorities(
    request: ExecutionRequest,
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    repository = request.repository_root
    if request.person_b_contract_commit != BOUNDED_REVEAL_CONTRACT_COMMIT:
        raise FinalComparisonExecutionError("Person B contract commit differs.")
    comparison = _exact_git_json(
        repository,
        COMPARISON_CONTRACT_COMMIT,
        COMPARISON_CONTRACT_PATH,
        sha256=COMPARISON_CONTRACT_SHA256,
        byte_size=COMPARISON_CONTRACT_BYTE_SIZE,
    )
    validate_frozen_contract(comparison)
    bounded = _exact_git_json(
        repository,
        BOUNDED_REVEAL_CONTRACT_COMMIT,
        BOUNDED_CONTRACT_PATH,
        sha256=BOUNDED_CONTRACT_SHA256,
        byte_size=BOUNDED_CONTRACT_BYTE_SIZE,
    )
    try:
        validate_bounded_reveal_contract(bounded)
    except ValueError as error:
        raise FinalComparisonExecutionError(str(error)) from error
    ratification = _exact_git_json(
        repository,
        E_COMPARISON_RATIFICATION_COMMIT,
        E_RATIFICATION_PATH,
        sha256=E_RATIFICATION_SHA256,
        byte_size=E_RATIFICATION_BYTE_SIZE,
    )
    ratification_requirements = {
        "exact_final_comparison_metrics_authorized": True,
        "exploratory_metrics_authorized": False,
        "manual_u4_inspection_authorized": False,
        "person_b_comparison_contract_commit": COMPARISON_CONTRACT_COMMIT,
        "person_b_post_reveal_contract_commit": BOUNDED_REVEAL_CONTRACT_COMMIT,
        "post_hoc_layer_selection_authorized": False,
        "post_hoc_test_selection_authorized": False,
        "probe_refitting_authorized": False,
        "step4_1_complete": False,
        "u4_output_inspected": False,
    }
    for field, expected in ratification_requirements.items():
        if ratification.get(field) != expected:
            raise FinalComparisonExecutionError(f"E ratification differs at {field}.")
    authorization_revision = _git(
        repository, "rev-parse", request.person_e_ratification_commit
    )
    authorization_payload = _git_bytes(
        repository, authorization_revision, E_EXECUTION_AUTHORIZATION_PATH
    )
    authorization = decode_strict_json(
        authorization_payload, label="Person E execution authorization"
    )
    if not isinstance(authorization, Mapping):
        raise FinalComparisonExecutionError("E execution authorization is not an object.")
    required = {
        "additional_person_a_extraction_authorized": False,
        "bounded_reveal_artifact_sha256": BOUNDED_REVEAL_PREDICTIONS_SHA256,
        "bounded_reveal_prediction_count": BOUNDED_REVEAL_PREDICTION_COUNT,
        "bounded_reveal_rerun_authorized": False,
        "bounded_reveal_reuse_authorized": True,
        "broad_hidden_state_interpretation_authorized": False,
        "comparison_contract_commit": COMPARISON_CONTRACT_COMMIT,
        "comparison_ratification_commit": E_COMPARISON_RATIFICATION_COMMIT,
        "exploratory_metrics_authorized": False,
        "final_comparison_implementation_ratified": True,
        "manual_u4_inspection_authorized": False,
        "person_b_bounded_reveal_contract_commit": BOUNDED_REVEAL_CONTRACT_COMMIT,
        "person_d_completion_commit": PERSON_D_COMPLETION_COMMIT,
        "probe_refitting_authorized": False,
        "step4_1_complete": False,
        "u4_output_inspected": False,
    }
    for field, expected in required.items():
        if authorization.get(field) != expected:
            raise FinalComparisonExecutionError(
                f"Superseding E authorization differs at {field}."
            )
    implementation_commit = authorization.get("person_b_comparison_implementation_commit")
    preparation_commit = authorization.get("person_b_execution_preparation_commit")
    if not all(
        isinstance(value, str) and len(value) == 40
        for value in (implementation_commit, preparation_commit)
    ):
        raise FinalComparisonExecutionError("E authorization lacks exact B commits.")
    if authorization.get("authorized_command") != exact_execution_command():
        raise FinalComparisonExecutionError("E authorized command differs.")
    if authorization.get("authorized_output_root") != FINAL_OUTPUT_ROOT.as_posix():
        raise FinalComparisonExecutionError("E authorized output root differs.")
    if (
        _git(repository, "show", "-s", "--format=%P", preparation_commit)
        != implementation_commit
    ):
        raise FinalComparisonExecutionError(
            "B implementation/preparation ancestry differs."
        )
    if (
        _git(repository, "show", "-s", "--format=%P", implementation_commit)
        != BOUNDED_REVEAL_CONTRACT_COMMIT
    ):
        raise FinalComparisonExecutionError(
            "B implementation authority ancestry differs."
        )
    if request.mode == "run":
        if _git(repository, "branch", "--show-current") != PERSON_B_BRANCH:
            raise FinalComparisonExecutionError("Execution requires the Person B branch.")
        if _git(repository, "status", "--porcelain"):
            raise FinalComparisonExecutionError("Execution requires a clean worktree.")
        if _git(repository, "rev-parse", "HEAD") != preparation_commit:
            raise FinalComparisonExecutionError("HEAD differs from the ratified B preparation.")
    return comparison, bounded, authorization


def _load_local_inputs(
    repository: Path,
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any], dict[str, str]]:
    documents: dict[str, Any] = {}
    hashes: dict[str, str] = {}
    for name, reference in LOCAL_INPUT_REFERENCES.items():
        path = repository / str(reference["path"])
        payload = _read_bytes(path, label=name)
        if (
            reference.get("byte_size") is not None
            and len(payload) != reference["byte_size"]
        ) or _sha256(payload) != reference["sha256"]:
            raise FinalComparisonExecutionError(f"Local input {name} differs.")
        hashes[name] = str(reference["sha256"])
        if path.suffix == ".json":
            documents[name] = decode_strict_json(payload, label=name)
    fold = documents["fold_manifest"]
    oracle = documents["oracle_target"]
    applicability = documents["applicability"]
    if (
        not isinstance(fold, Mapping)
        or not isinstance(fold.get("memberships"), list)
        or len(fold["memberships"]) != 1695
        or not isinstance(oracle, Mapping)
        or not isinstance(oracle.get("rows"), list)
        or len(oracle["rows"]) != 1695
        or not isinstance(applicability, Mapping)
        or applicability.get("applicability_entry_count") != 9
    ):
        raise FinalComparisonExecutionError("Frozen local input structure differs.")
    return fold, oracle, applicability, hashes


def _fold_by_key(fold: Mapping[str, Any]) -> dict[tuple[str, int], int]:
    result = {}
    for row in fold["memberships"]:
        key = (row.get("trajectory_id"), row.get("model_frame_idx"))
        value = row.get("fold_idx")
        if (
            key in result
            or not isinstance(key[0], str)
            or not isinstance(key[1], int)
            or isinstance(key[1], bool)
            or not isinstance(value, int)
            or isinstance(value, bool)
            or value not in range(5)
        ):
            raise FinalComparisonExecutionError("Fold membership is malformed.")
        result[key] = value
    return result


def _oracle_by_key(oracle: Mapping[str, Any]) -> dict[tuple[str, int], Mapping[str, Any]]:
    result = {}
    for row in oracle["rows"]:
        key = (row.get("trajectory_id"), row.get("model_frame_idx"))
        if key in result:
            raise FinalComparisonExecutionError("Oracle identities are duplicated.")
        for field in ("mu_oracle_blocks", "x_true_blocks", "tau"):
            value = row.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math_isfinite(value)
            ):
                raise FinalComparisonExecutionError(f"Oracle {field} is invalid.")
        log_sigma = row.get("log_sigma_oracle")
        if row.get("visibility") == "occluded" and (
            isinstance(log_sigma, bool)
            or not isinstance(log_sigma, (int, float))
            or not math_isfinite(log_sigma)
        ):
            raise FinalComparisonExecutionError("Hidden oracle spread is invalid.")
        result[key] = row
    return result


def math_isfinite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _load_person_b_predictions(
    path: Path,
    *,
    fold_by_key: Mapping[tuple[str, int], int],
    oracle_by_key: Mapping[tuple[str, int], Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    payload, document = _read_exact(
        path,
        label="Person B predictions",
        sha256=PERSON_B_PREDICTIONS_SHA256,
        byte_size=84257218,
    )
    if not isinstance(document, Mapping):
        raise FinalComparisonExecutionError("Person B predictions are not an object.")
    outputs = document.get("probe_outputs")
    if (
        document.get("schema_id") != "person-b-step4-1-production-ridge-oof-v0-1"
        or document.get("fitted_probe_count") != 40
        or document.get("metrics_computed") is not False
        or document.get("u4_output_inspected") is not False
        or not isinstance(outputs, list)
        or len(outputs) != 40
    ):
        raise FinalComparisonExecutionError("Person B prediction envelope differs.")
    normalized: list[dict[str, Any]] = []
    seen_matrices = set()
    for output in outputs:
        layer = output.get("layer_idx")
        hook = output.get("hook_site")
        target = output.get("target_name")
        matrix_key = (layer, hook, target)
        if (
            matrix_key in seen_matrices
            or layer not in range(20)
            or hook != "decoder_layer_output_residual_stream"
            or target not in {"mu_oracle_blocks", "log_sigma_oracle"}
        ):
            raise FinalComparisonExecutionError("Person B matrix identity differs.")
        seen_matrices.add(matrix_key)
        rows = output.get("oof_prediction_rows")
        fits = output.get("fold_fits")
        if not isinstance(rows, list) or len(rows) != 695 or not isinstance(fits, list):
            raise FinalComparisonExecutionError("Person B matrix coverage differs.")
        folds = {fit.get("outer_fold_idx"): fit for fit in fits if isinstance(fit, Mapping)}
        if set(folds) != set(range(5)):
            raise FinalComparisonExecutionError("Person B fold-fit coverage differs.")
        row_keys = []
        for row in rows:
            key = (row.get("trajectory_id"), row.get("model_frame_idx"))
            if key not in fold_by_key or key not in oracle_by_key:
                raise FinalComparisonExecutionError("Person B row identity is unknown.")
            prediction = row.get("prediction")
            if not math_isfinite(prediction):
                raise FinalComparisonExecutionError("Person B prediction is not finite.")
            row_keys.append(key)
            normalized.append(
                {
                    **dict(row),
                    "fold_idx": fold_by_key[key],
                    "hook_site": hook,
                    "layer_idx": layer,
                    "prediction": float(prediction),
                    "target_name": target,
                }
            )
        if len(set(row_keys)) != 695:
            raise FinalComparisonExecutionError("Person B OOF identities are duplicated.")
        for fold_idx, fit in folds.items():
            expected_test = {
                index for index, key in enumerate(row_keys) if fold_by_key[key] == fold_idx
            }
            test_indices = fit.get("test_indices")
            training_indices = fit.get("training_indices")
            if (
                not isinstance(test_indices, list)
                or set(test_indices) != expected_test
                or not isinstance(training_indices, list)
                or set(test_indices) & set(training_indices)
                or set(test_indices) | set(training_indices) != set(range(695))
            ):
                raise FinalComparisonExecutionError("Person B OOF fit leakage check failed.")
    expected_matrices = {
        (layer, "decoder_layer_output_residual_stream", target)
        for layer in range(20)
        for target in ("mu_oracle_blocks", "log_sigma_oracle")
    }
    if seen_matrices != expected_matrices or len(normalized) != 27800:
        raise FinalComparisonExecutionError("Person B prediction universe differs.")
    return normalized, {"person_b_predictions": _sha256(payload)}


def _expand_identity_set(
    applicability: Mapping[str, Any], name: str
) -> set[tuple[str, int]]:
    identity = applicability.get("identity_sets", {}).get(name)
    if not isinstance(identity, Mapping) or not isinstance(identity.get("ranges"), list):
        raise FinalComparisonExecutionError(f"Applicability identity set {name} is missing.")
    result = set()
    for row in identity["ranges"]:
        if (
            not isinstance(row, list)
            or len(row) != 3
            or not isinstance(row[0], str)
            or not isinstance(row[1], int)
            or not isinstance(row[2], int)
            or row[1] > row[2]
        ):
            raise FinalComparisonExecutionError("Applicability range is malformed.")
        result.update((row[0], frame) for frame in range(row[1], row[2] + 1))
    if len(result) != identity.get("expected_count"):
        raise FinalComparisonExecutionError("Applicability identity count differs.")
    return result


def _load_person_d_baselines(
    root: Path,
    *,
    applicability: Mapping[str, Any],
    fold_by_key: Mapping[tuple[str, int], int],
) -> tuple[dict[tuple[str, str], tuple[Mapping[str, Any], ...]], dict[str, str]]:
    run_payload, run_state = _read_exact(
        root / "run_state.json",
        label="Person D completion manifest",
        sha256=PERSON_D_COMPLETION_SHA256,
        byte_size=1480,
    )
    if not isinstance(run_state, Mapping):
        raise FinalComparisonExecutionError("Person D run state is not an object.")
    entries = {
        (entry["family"], entry["target"]): entry
        for entry in applicability["applicability_entries"]
    }
    documents: dict[tuple[str, str], tuple[Mapping[str, Any], ...]] = {}
    hashes = {"person_d_completion_manifest": _sha256(run_payload)}
    for family, target, sha256, byte_size, row_count in D_PREDICTION_REFERENCES:
        filename = f"{family}__{target}.json"
        payload, document = _read_exact(
            root / filename,
            label=f"Person D {family}/{target}",
            sha256=sha256,
            byte_size=byte_size,
        )
        if not isinstance(document, Mapping):
            raise FinalComparisonExecutionError("A Person D document is not an object.")
        rows = document.get("rows")
        if (
            document.get("baseline_input_schema_version")
            != "person-b-baseline-input-v0.2"
            or document.get("producer_role") != "person_d"
            or document.get("baseline_family") != family
            or document.get("target_name") != target
            or document.get("random_split_used") is not False
            or document.get("u4_output_inspected") is not False
            or not isinstance(rows, list)
            or len(rows) != row_count
        ):
            raise FinalComparisonExecutionError(f"Person D {family}/{target} differs.")
        expected = _expand_identity_set(
            applicability, str(entries[(family, target)]["admitted_identity_set"])
        )
        actual = set()
        normalized = []
        for row in rows:
            key = (row.get("trajectory_id"), row.get("model_frame_idx"))
            if key in actual or key not in fold_by_key or row.get("fold_idx") != fold_by_key[key]:
                raise FinalComparisonExecutionError("Person D row fold/identity differs.")
            if row.get("prediction_scope") != "out_of_fold" or not math_isfinite(
                row.get("prediction")
            ):
                raise FinalComparisonExecutionError("Person D row is not finite OOF.")
            actual.add(key)
            normalized.append({**dict(row), "target_name": target})
        if actual != expected:
            raise FinalComparisonExecutionError("Person D applicability coverage differs.")
        documents[(family, target)] = tuple(normalized)
        hashes[f"person_d_{family}_{target}"] = _sha256(payload)
    if sum(len(rows) for rows in documents.values()) != 10776:
        raise FinalComparisonExecutionError("Person D total prediction count differs.")
    return documents, hashes


def _validate_positive_control(repository: Path) -> tuple[bool, str]:
    payload = _git_bytes(repository, POSITIVE_CONTROL_COMMIT, POSITIVE_CONTROL_PATH)
    if _sha256(payload) != POSITIVE_CONTROL_SHA256:
        raise FinalComparisonExecutionError("Positive-control decision bytes differ.")
    document = decode_strict_json(payload, label="positive-control decision")
    if (
        not isinstance(document, Mapping)
        or document.get("decision") != "PASS_FROZEN_VISIBLE_POSITION_POSITIVE_CONTROL"
        or document.get("lineage_receipt_sha256")
        != "29fd15d6773f16843d3de6b8db58c2d100bcf47779b41bbd44a3c81a062f74f4"
        or document.get("positive_control_pass") is not True
        or document.get("u4_output_inspected") is not False
    ):
        raise FinalComparisonExecutionError("Positive-control decision differs.")
    return True, _sha256(payload)


def validate_execution_request(request: ExecutionRequest) -> None:
    """Reject changed paths, resume semantics, or an executing non-SageMaker host."""

    if request.mode not in {"validate", "run"}:
        raise FinalComparisonExecutionError("Mode must be validate or run.")
    if request.resume != "validate-complete-no-write":
        raise FinalComparisonExecutionError("Resume behavior differs from the contract.")
    exact_paths = {
        "person_b_predictions": (request.person_b_predictions, PERSON_B_PREDICTION_PATH),
        "person_d_root": (request.person_d_root, PERSON_D_ROOT),
        "post_reveal_predictions": (request.post_reveal_predictions, POST_REVEAL_PATH),
        "output_root": (request.output_root, FINAL_OUTPUT_ROOT),
    }
    changed = [name for name, (actual, expected) in exact_paths.items() if actual != expected]
    if changed:
        raise FinalComparisonExecutionError(
            f"Runtime paths differ from authorization: {', '.join(changed)}."
        )
    if request.mode == "run" and (
        platform.system() != "Linux"
        or not (
            Path("/home/sagemaker-user").exists()
            or Path("/opt/ml").exists()
            or os.environ.get("SM_MODEL_DIR")
        )
    ):
        raise FinalComparisonExecutionError("Scientific execution requires SageMaker Linux.")


def validate_all_inputs(request: ExecutionRequest) -> ComparisonDataset:
    """Validate all authorities, schemas, identities, hashes, and restrictions."""

    validate_execution_request(request)
    comparison, _, _ = _load_contract_authorities(request)
    validate_method_configuration(frozen_method_configuration())
    fold, oracle_document, applicability, hashes = _load_local_inputs(
        request.repository_root
    )
    fold_by_key = _fold_by_key(fold)
    oracle_by_key = _oracle_by_key(oracle_document)
    if set(fold_by_key) != set(oracle_by_key):
        raise FinalComparisonExecutionError("Fold and oracle universes differ.")
    for key, row in oracle_by_key.items():
        if row.get("fold_idx") != fold_by_key[key]:
            raise FinalComparisonExecutionError("Oracle and fold assignments differ.")
    probe_rows, probe_hashes = _load_person_b_predictions(
        request.person_b_predictions,
        fold_by_key=fold_by_key,
        oracle_by_key=oracle_by_key,
    )
    baseline_rows, baseline_hashes = _load_person_d_baselines(
        request.person_d_root,
        applicability=applicability,
        fold_by_key=fold_by_key,
    )
    post_reveal, reveal_hashes = load_bounded_reveal_artifact(
        request.post_reveal_predictions
    )
    positive, positive_hash = _validate_positive_control(request.repository_root)
    direct_hashes = {
        **hashes,
        **probe_hashes,
        **baseline_hashes,
        **reveal_hashes,
        "comparison_contract": COMPARISON_CONTRACT_SHA256,
        "bounded_reveal_contract": BOUNDED_CONTRACT_SHA256,
        "comparison_ratification": E_RATIFICATION_SHA256,
        "positive_control_decision": positive_hash,
        "execution_authorization": _sha256(
            _git_bytes(
                request.repository_root,
                _git(
                    request.repository_root,
                    "rev-parse",
                    request.person_e_ratification_commit,
                ),
                E_EXECUTION_AUTHORIZATION_PATH,
            )
        ),
    }
    validate_frozen_contract(comparison)
    return ComparisonDataset(
        oracle_rows=tuple(oracle_document["rows"]),
        probe_rows=tuple(probe_rows),
        baseline_rows=baseline_rows,
        post_reveal_rows=tuple(post_reveal["rows"]),
        direct_input_sha256s=direct_hashes,
        positive_control_valid=positive,
    )


def _build_registry_import_package(
    metric_payload: bytes,
    *,
    direct_input_sha256s: Mapping[str, str],
) -> dict[str, Any]:
    direct_ids = [f"sha256:{name}:{value}" for name, value in sorted(direct_input_sha256s.items())]
    return {
        "artifact_exact_fields": [
            "schema_version",
            "artifact_schema_version",
            "artifact_id",
            "direct_input_artifact_ids",
            "creator_run_id",
            "artifact_type",
            "uri",
            "sha256",
            "size_bytes",
            "status",
            "status_authority",
            "status_reason",
            "superseded_by",
        ],
        "metric_table_artifact": {
            "artifact_id": "person-b-step4-1-final-comparison-v0-1:metric-table",
            "artifact_schema_version": "person-b-analysis-artifact-v0.1",
            "artifact_type": "metric_table",
            "creator_run_id": "person-b-step4-1-final-comparison-v0-1",
            "direct_input_artifact_ids": direct_ids,
            "schema_version": "1.0",
            "sha256": _sha256(metric_payload),
            "size_bytes": len(metric_payload),
            "status": "accepted",
            "status_authority": "person_b",
            "status_reason": "exact_ratified_step4_1_final_comparison",
            "superseded_by": None,
            "uri": (
                FINAL_OUTPUT_ROOT / "comparison_metric_table.json"
            ).as_posix(),
        },
        "registry_generation": "v2",
        "required_registry_fields": [
            "immutable_registry_schema_version",
            "registry_id",
            "schema_version",
            "scientific_use",
            "synthetic",
            "owner_authorities",
            "owner_status_records",
            "trusted_artifact_authorizations",
            "trusted_authorization_record_bytes",
            "manifests",
            "byte_verifications",
            "runs",
            "artifacts",
        ],
        "schema_id": "person-b-step4-1-registry-v2-import-package-v0-1",
        "schema_version": "1.0",
        "u4_output_inspected": False,
    }


def _complete_documents(
    documents: dict[str, dict[str, Any]],
    *,
    request: ExecutionRequest,
    dataset: ComparisonDataset,
) -> dict[str, dict[str, Any]]:
    validate_output_documents(documents)
    metric_payload = formatted_json_bytes(documents["comparison_metric_table.json"])
    documents["registry_v2_import_package.json"] = _build_registry_import_package(
        metric_payload, direct_input_sha256s=dataset.direct_input_sha256s
    )
    documents["execution_receipt.json"] = {
        "additional_person_a_extraction_performed": False,
        "bounded_reveal_prediction_count": BOUNDED_REVEAL_PREDICTION_COUNT,
        "bounded_reveal_prediction_sha256": BOUNDED_REVEAL_PREDICTIONS_SHA256,
        "bounded_reveal_rerun_performed": False,
        "broad_hidden_state_interpretation": False,
        "direct_input_sha256s": dict(sorted(dataset.direct_input_sha256s.items())),
        "exploratory_metrics_computed": False,
        "manual_u4_inspection": False,
        "person_b_contract_commit": request.person_b_contract_commit,
        "person_e_ratification_commit": _git(
            request.repository_root, "rev-parse", request.person_e_ratification_commit
        ),
        "post_hoc_layer_selection_performed": False,
        "post_hoc_test_selection_performed": False,
        "probe_refit_performed": False,
        "schema_id": "person-b-step4-1-final-comparison-execution-receipt-v0-1",
        "schema_version": "1.0",
        "scientific_execution_performed": True,
        "u4_output_inspected": False,
    }
    return documents


def _publish_output_root(output_root: Path, documents: Mapping[str, Mapping[str, Any]]) -> None:
    if output_root.exists() or output_root.is_symlink():
        raise FinalComparisonExecutionError("Output root already exists.")
    if set(documents) != set(FINAL_OUTPUT_FILENAMES) - {"sha256_inventory.json"}:
        raise FinalComparisonExecutionError("Output document set is incomplete.")
    parent = output_root.parent
    parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".step4-1-final-comparison-", dir=parent))
    try:
        payloads = {
            name: formatted_json_bytes(document) for name, document in documents.items()
        }
        for name, payload in payloads.items():
            (stage / name).write_bytes(payload)
        inventory = {
            "files": {name: _sha256(payload) for name, payload in sorted(payloads.items())},
            "inventory_excludes_self": True,
            "schema_id": "person-b-step4-1-final-comparison-output-inventory-v0-1",
            "schema_version": "1.0",
            "u4_output_inspected": False,
        }
        (stage / "sha256_inventory.json").write_bytes(formatted_json_bytes(inventory))
        os.rename(stage, output_root)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def validate_existing_output_root(output_root: Path) -> None:
    if output_root.is_symlink() or not output_root.is_dir():
        raise FinalComparisonExecutionError("Existing output root is invalid.")
    names = {path.name for path in output_root.iterdir() if path.is_file()}
    if names != set(FINAL_OUTPUT_FILENAMES):
        raise FinalComparisonExecutionError("Existing output file set differs.")
    inventory = decode_strict_json(
        _read_bytes(output_root / "sha256_inventory.json", label="output inventory"),
        label="output inventory",
    )
    expected = {
        name: _sha256(_read_bytes(output_root / name, label=name))
        for name in FINAL_OUTPUT_FILENAMES
        if name != "sha256_inventory.json"
    }
    if not isinstance(inventory, Mapping) or inventory.get("files") != expected:
        raise FinalComparisonExecutionError("Existing output inventory differs.")
    documents = {
        name: decode_strict_json(
            _read_bytes(output_root / name, label=name), label=name
        )
        for name in (
            "comparison_metric_table.json",
            "paired_test_results.json",
            "confidence_intervals.json",
            "layer_band_decision.json",
        )
    }
    validate_output_documents(documents)


def run_final_comparison(request: ExecutionRequest) -> dict[str, Any]:
    """Validate-only or execute once; never refit, extract, reveal, or inspect U4."""

    dataset = validate_all_inputs(request)
    if request.mode == "validate":
        return {
            "bounded_reveal_reused": True,
            "command_complete": True,
            "input_count": len(dataset.direct_input_sha256s),
            "output_schema_valid": True,
            "schema_id": "person-b-step4-1-final-comparison-validation-v0-1",
            "scientific_execution_performed": False,
            "status": "VALIDATED_NO_SCIENTIFIC_EXECUTION",
            "u4_output_inspected": False,
        }
    if request.output_root.exists() or request.output_root.is_symlink():
        validate_existing_output_root(request.output_root)
        return {
            "scientific_execution_performed": False,
            "status": "ALREADY_COMPLETE_NO_WRITE",
            "u4_output_inspected": False,
        }
    try:
        documents = compute_final_comparison(dataset)
    except FinalComparisonExecutionError as error:
        documents = inconclusive_output_documents(
            direct_input_sha256s=dataset.direct_input_sha256s,
            reason=str(error),
        )
    complete = _complete_documents(
        documents, request=request, dataset=dataset
    )
    _publish_output_root(request.output_root, complete)
    return {
        "decision": complete["comparison_metric_table.json"]["decision"],
        "output_root": str(request.output_root),
        "scientific_execution_performed": True,
        "status": "COMPLETE",
        "u4_output_inspected": False,
    }


__all__ = [
    "BOUNDED_REVEAL_PREDICTIONS_SHA256",
    "FINAL_OUTPUT_ROOT",
    "PERSON_B_PREDICTION_PATH",
    "PERSON_D_ROOT",
    "POST_REVEAL_PATH",
    "ExecutionRequest",
    "decode_strict_json",
    "exact_execution_command",
    "load_bounded_reveal_artifact",
    "run_final_comparison",
    "validate_all_inputs",
    "validate_bounded_reveal_payload",
    "validate_execution_request",
    "validate_existing_output_root",
]
