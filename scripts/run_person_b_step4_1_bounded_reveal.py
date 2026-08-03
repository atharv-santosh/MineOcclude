"""Produce only the E-authorized five-event post-reveal probe predictions.

This script is not run during contract preparation. It is a fail-closed future
entry point requiring the exact Person E authorization Git object.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import sys
from collections.abc import Mapping
from itertools import pairwise
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.analysis.step4_1_bounded_reveal_v0_1 import (
    COMPARISON_CONTRACT_COMMIT,
    HOOK_SITE,
    predict_with_raw_probe,
    validate_bounded_reveal_contract,
    validate_prediction_rows,
)
from mineocclude.experiments.registry import canonical_json_bytes, write_json_exclusive
from scripts.run_person_b_step4_1_production_sagemaker import (
    _decode_object,
    _git,
    _git_bytes,
    _load_authority_documents,
    _load_external_activation_evidence,
    _sha256,
)

CONTRACT_PACKAGE = (
    "docs/status/person_b_phase4_step4_1_bounded_reveal_contract_v0_1"
)
E_AUTHORIZATION_PATH = (
    "docs/status/person_e_phase4_step4_1_bounded_reveal_authorization_v0_1/"
    "bounded_reveal_authorization.json"
)
DEFAULT_OUTPUT_ROOT = Path(
    "/home/sagemaker-user/person-b-step4-1-approved-outputs/"
    "person-b-step4-1-bounded-reveal-v0-1"
)


class BoundedRevealRunnerError(RuntimeError):
    """Raised before any output when reveal authority or inputs differ."""


def _fail(message: str) -> None:
    raise BoundedRevealRunnerError(message)


def _require_runtime(repository: Path, contract_commit: str) -> None:
    if platform.system() != "Linux" or not (
        Path("/home/sagemaker-user").exists()
        or Path("/opt/ml").exists()
        or os.environ.get("SM_MODEL_DIR")
    ):
        _fail("Bounded reveal production requires the authorized SageMaker Linux host.")
    if _git(repository, "status", "--porcelain", text=True).strip():
        _fail("Person B worktree must be clean.")
    if _git(repository, "branch", "--show-current", text=True).strip() != (
        "role/person-b-analysis"
    ):
        _fail("Bounded reveal must remain on role/person-b-analysis.")
    if _git(repository, "rev-parse", "HEAD", text=True).strip() != contract_commit:
        _fail("HEAD differs from the exact bounded reveal contract commit.")
    parent = _git(
        repository, "show", "-s", "--format=%P", contract_commit, text=True
    ).strip()
    if parent != COMPARISON_CONTRACT_COMMIT:
        _fail("Bounded reveal contract is not the direct comparison-contract child.")


def _load_contract(repository: Path, contract_commit: str) -> Mapping[str, Any]:
    inventory = _decode_object(
        _git_bytes(repository, contract_commit, f"{CONTRACT_PACKAGE}/sha256_inventory.json"),
        label="bounded reveal package inventory",
    )
    if inventory.get("inventory_excludes_self") is not True:
        _fail("Bounded reveal package inventory is malformed.")
    files = inventory.get("files")
    if not isinstance(files, Mapping):
        _fail("Bounded reveal package files are missing.")
    documents = {}
    for name, reference in files.items():
        if not isinstance(name, str) or not isinstance(reference, Mapping):
            _fail("Bounded reveal inventory row is malformed.")
        payload = _git_bytes(repository, contract_commit, f"{CONTRACT_PACKAGE}/{name}")
        if (
            len(payload) != reference.get("byte_size")
            or _sha256(payload) != reference.get("sha256")
        ):
            _fail(f"Bounded reveal contract package differs at {name}.")
        documents[name] = _decode_object(payload, label=f"bounded reveal {name}")
    contract = documents.get("bounded_reveal_contract.json")
    try:
        validate_bounded_reveal_contract(contract)
    except ValueError as error:
        _fail(str(error))
    return contract


def _load_e_authorization(
    repository: Path,
    authorization_commit: str,
    *,
    person_b_contract_commit: str,
) -> Mapping[str, Any]:
    authorization = _decode_object(
        _git_bytes(repository, authorization_commit, E_AUTHORIZATION_PATH),
        label="Person E bounded reveal authorization",
    )
    required = {
        "bounded_reveal_authorized": True,
        "broad_hidden_state_interpretation_authorized": False,
        "exploratory_metrics_authorized": False,
        "manual_u4_inspection_authorized": False,
        "person_b_comparison_contract_commit": COMPARISON_CONTRACT_COMMIT,
        "person_b_post_reveal_contract_commit": person_b_contract_commit,
        "post_hoc_layer_selection_authorized": False,
        "post_hoc_test_selection_authorized": False,
        "post_reveal_probe_predictions_authorized": True,
        "probe_refitting_authorized": False,
        "step4_1_complete": False,
        "u4_output_inspected": False,
    }
    for field, expected in required.items():
        if authorization.get(field) != expected:
            _fail(f"Person E authorization differs at {field}.")
    if (
        authorization.get("authorized_output_root") != str(DEFAULT_OUTPUT_ROOT)
        or authorization.get("expected_prediction_count") != 100
        or authorization.get("output_schema_id")
        != "person-b-step4-1-bounded-reveal-predictions-v0-1"
    ):
        _fail("Person E authorization output scope differs.")
    return authorization


def _load_prediction_artifact(path: Path, contract: Mapping[str, Any]) -> Mapping[str, Any]:
    reference = contract["authorities"]["person_b_prediction_artifact"]
    try:
        payload = path.read_bytes()
    except OSError as error:
        _fail(f"Could not read fitted probe artifact: {error}")
    if len(payload) != reference["byte_size"] or _sha256(payload) != reference["sha256"]:
        _fail("Fitted probe artifact byte identity differs.")
    document = _decode_object(payload, label="fitted probes and predictions")
    outputs = document.get("probe_outputs")
    if (
        document.get("schema_id") != "person-b-step4-1-production-ridge-oof-v0-1"
        or document.get("fitted_probe_count") != 40
        or document.get("metrics_computed") is not False
        or document.get("u4_output_inspected") is not False
        or not isinstance(outputs, list)
        or len(outputs) != 40
    ):
        _fail("Fitted probe artifact structure differs.")
    row_count = sum(len(output.get("oof_prediction_rows", ())) for output in outputs)
    if row_count != reference["prediction_count"]:
        _fail("Fitted probe prediction count differs.")
    return document


def _validate_capture_transition(
    repository: Path,
    event: Mapping[str, Any],
) -> None:
    capture = event["capture_package"]
    payload = _git_bytes(repository, capture["git_commit"], capture["path"])
    if _sha256(payload) != capture["sha256"]:
        _fail("Capture package SHA-256 differs.")
    document = _decode_object(payload, label=f"capture {event['trajectory_id']}")
    rows = sorted(document["streams"]["visibility"], key=lambda row: row["model_frame_idx"])
    transitions = [
        (left, right)
        for left, right in pairwise(rows)
        if left["visibility"] == "occluded" and right["visibility"] == "visible"
    ]
    if len(transitions) != 1:
        _fail("Capture does not contain exactly one reveal.")
    left, right = transitions[0]
    for name, observed in (("pre_identity", left), ("post_identity", right)):
        for field, expected in event[name].items():
            if observed.get(field) != expected:
                _fail(f"Capture transition differs at {event['event_id']}:{field}.")


def _produce_rows(
    contract: Mapping[str, Any],
    indices: Mapping[str, Any],
    prediction_document: Mapping[str, Any],
) -> list[dict[str, Any]]:
    probes = {
        (output["layer_idx"], output["hook_site"]): output
        for output in prediction_document["probe_outputs"]
        if output.get("target_name") == "log_sigma_oracle"
    }
    if set(probes) != {(layer, HOOK_SITE) for layer in range(20)}:
        _fail("Fitted spread probe layer coverage differs.")
    rows = []
    for event in contract["input_contract"]["events"]:
        index = indices[event["trajectory_id"]]
        if index.index_sha256 != event["activation_index"]["sha256"]:
            _fail("Activation index identity differs from reveal contract.")
        post_idx = event["post_identity"]["model_frame_idx"]
        activation_rows = [
            row
            for row in index.rows
            if row["global_model_frame_idx"] == post_idx
            and row["hook_site"] == HOOK_SITE
        ]
        if len(activation_rows) != 20:
            _fail("Post-reveal activation layer coverage differs.")
        by_layer = {row["layer_idx"]: row for row in activation_rows}
        if set(by_layer) != set(range(20)):
            _fail("Post-reveal activation layers are missing or duplicated.")
        for layer in range(20):
            activation_row = by_layer[layer]
            probe = probes[(layer, HOOK_SITE)]
            fits = [
                fit
                for fit in probe["fold_fits"]
                if fit["outer_fold_idx"] == event["fold_idx"]
            ]
            if len(fits) != 1:
                _fail("Exactly one held-out fold fit is required.")
            fit = fits[0]
            prediction = predict_with_raw_probe(
                index.vector_for_row(activation_row),
                fit["raw_coefficients"],
                fit["raw_intercept"],
            )
            post = event["post_identity"]
            rows.append(
                {
                    "action_idx": post["action_idx"],
                    "activation_index_sha256": index.index_sha256,
                    "activation_row_identity_sha256": hashlib.sha256(
                        canonical_json_bytes(dict(activation_row))
                    ).hexdigest(),
                    "episode_id": event["episode_id"],
                    "event_id": event["event_id"],
                    "fit_id": (
                        f"log_sigma_oracle:layer_{layer:02d}:"
                        f"outer_fold_{event['fold_idx']}"
                    ),
                    "fold_idx": event["fold_idx"],
                    "hook_site": HOOK_SITE,
                    "layer_idx": layer,
                    "layout_id": event["layout_id"],
                    "model_frame_idx": post_idx,
                    "model_hash": contract["input_contract"]["model_hash"],
                    "prediction": prediction,
                    "prediction_scope": "held_out",
                    "preprocess_hash": contract["input_contract"]["preprocess_hash"],
                    "relative_time_seconds": 0.0,
                    "render_frame_idx": post["render_frame_idx"],
                    "server_tick": post["server_tick"],
                    "target_name": "log_sigma_oracle",
                    "trajectory_id": event["trajectory_id"],
                    "visibility": "visible",
                }
            )
    rows.sort(key=lambda row: (row["trajectory_id"], row["layer_idx"]))
    validate_prediction_rows(rows)
    return rows


def _write_outputs(
    output_root: Path,
    *,
    contract_commit: str,
    authorization_commit: str,
    prediction_input_sha256: str,
    rows: list[dict[str, Any]],
) -> None:
    if output_root.exists() or output_root.is_symlink():
        _fail("Output root already exists; overwrite and partial resume are forbidden.")
    output_root.mkdir(parents=True, exist_ok=False)
    prediction = {
        "comparison_contract_commit": COMPARISON_CONTRACT_COMMIT,
        "person_b_contract_commit": contract_commit,
        "person_e_authorization_commit": authorization_commit,
        "prediction_count": len(rows),
        "rows": rows,
        "schema_id": "person-b-step4-1-bounded-reveal-predictions-v0-1",
        "schema_version": "1.0",
        "u4_output_inspected": False,
    }
    write_json_exclusive(output_root / "post_reveal_predictions.json", prediction)
    receipt = {
        "additional_person_a_extraction_performed": False,
        "fitted_probe_input_sha256": prediction_input_sha256,
        "metrics_computed": False,
        "person_b_contract_commit": contract_commit,
        "person_e_authorization_commit": authorization_commit,
        "prediction_count": len(rows),
        "probe_refit_performed": False,
        "schema_id": "person-b-step4-1-bounded-reveal-execution-receipt-v0-1",
        "schema_version": "1.0",
        "u4_output_inspected": False,
    }
    write_json_exclusive(output_root / "execution_receipt.json", receipt)
    inventory = {
        "files": {
            name: _sha256((output_root / name).read_bytes())
            for name in ("execution_receipt.json", "post_reveal_predictions.json")
        },
        "inventory_excludes_self": True,
        "schema_id": "person-b-step4-1-bounded-reveal-output-inventory-v0-1",
        "schema_version": "1.0",
    }
    write_json_exclusive(output_root / "sha256_inventory.json", inventory)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run exact bounded reveal predictions.")
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--person-b-contract-commit", required=True)
    parser.add_argument("--person-e-authorization-commit", required=True)
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repository = args.repository_root.resolve()
    _require_runtime(repository, args.person_b_contract_commit)
    contract = _load_contract(repository, args.person_b_contract_commit)
    _load_e_authorization(
        repository,
        args.person_e_authorization_commit,
        person_b_contract_commit=args.person_b_contract_commit,
    )
    if args.output_root != DEFAULT_OUTPUT_ROOT:
        _fail("Output root differs from exact authorization.")
    for event in contract["input_contract"]["events"]:
        _validate_capture_transition(repository, event)
    prediction_path = Path(
        contract["authorities"]["person_b_prediction_artifact"]["path"]
    )
    predictions = _load_prediction_artifact(prediction_path, contract)
    completion, artifact_manifest, handoff, inventories, c_acceptance = (
        _load_authority_documents(repository)
    )
    from mineocclude.analysis.positive_control_v2 import (
        validate_ten_pilot_authority_documents,
    )

    authority = validate_ten_pilot_authority_documents(
        completion_report=completion,
        artifact_manifest=artifact_manifest,
        positive_control_handoff=handoff,
        per_pilot_inventories=inventories,
        c_accepted_manifest=c_acceptance,
    )
    _, indices = _load_external_activation_evidence(
        inventories,
        accepted_manifest_by_trajectory=authority.accepted_c_manifest_by_trajectory,
    )
    rows = _produce_rows(contract, indices, predictions)
    _write_outputs(
        args.output_root,
        contract_commit=args.person_b_contract_commit,
        authorization_commit=args.person_e_authorization_commit,
        prediction_input_sha256=contract["authorities"]["person_b_prediction_artifact"]["sha256"],
        rows=rows,
    )
    print(f"PERSON_B_STEP4_1_BOUNDED_REVEAL_OUTPUT={args.output_root}")


if __name__ == "__main__":
    main()
