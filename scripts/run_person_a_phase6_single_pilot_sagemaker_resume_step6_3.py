#!/usr/bin/env python3
"""Fail-closed continuation of Person A Phase 6 from Step 6.3.

The ``plan`` and ``continuation-id`` operations are preparation-only.  The
``resume`` operation is restricted to the exact immutable failed SageMaker
session and never invokes the Step 6.1 or Step 6.2 handlers.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time
import traceback
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_person_a_phase6_single_pilot_sagemaker as base

RUNNER_VERSION = "person-a-phase6-step6-3-resume-sagemaker-v0.2"
PRIOR_RUNNER_VERSION = "person-a-phase6-single-pilot-sagemaker-runner-v0.1"
PRIOR_PERSON_A_COMMIT = "a5841beea424f444bb364dae815d8a74de55f849"
PRIOR_SESSION_ID = "person-a-phase6-layout-00-ep9403-seed-20260725"
PRIOR_INPUT_ROOT = Path(
    "/home/sagemaker-user/person-a-phase6-approved-inputs"
) / PRIOR_SESSION_ID
PRIOR_OUTPUT_ROOT = Path(
    "/home/sagemaker-user/person-a-phase6-approved-outputs"
) / PRIOR_SESSION_ID
PRIOR_FINAL_REPORT_SHA256 = (
    "cff589a317fc9551822b8f29a6d3e75e8ee3d1294435338bc9b042a016fc4271"
)
PRIOR_WRAPPER_LOG_SHA256 = (
    "8b8ad48ee6a4fee8d6dedc9e617cfe75e3ae6f7f03bf938551bb556e33c39fb3"
)
RESUME_STEPS = ("6.3", "6.4", "6.5")
SOURCE_FILENAMES = {
    "accepted_manifest": "accepted_pilot_manifest.json",
    "capture_package": "capture_package_v0_1.json",
    "frame_map": "frame_map.jsonl",
    "media": "video_640x360.mp4",
    "normalized_actions": "normalized_actions.jsonl",
    "raw_actions": "raw_actions.jsonl",
    "state": "server_state.jsonl",
    "visibility": "visibility.jsonl",
}
MODEL_CONFIG_PROVENANCE_FILENAME = "700M_16f.git-blob.yaml"


@dataclass(frozen=True)
class PriorEvidence:
    final_report: dict[str, Any]
    runtime_receipt: dict[str, Any]
    step6_1_receipt: dict[str, Any]
    step6_2_receipt: dict[str, Any]
    input_paths: dict[str, Path]
    model_config_provenance_path: Path
    immutable_inventory: dict[str, str]
    wrapper_log_path: Path


@dataclass(frozen=True)
class ResumeArguments:
    base_arguments: base.RunnerArguments
    prior_input_root: Path
    prior_output_root: Path
    resume_ratification_object: str


def _fail(code: str, message: str, *, step: str = "resume-preflight") -> None:
    raise base.Phase6RunnerError(code, message, step=step)


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        document = json.loads(path.read_bytes())
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        _fail("prior_evidence_invalid", f"{label} cannot be read: {error}")
    if not isinstance(document, dict):
        _fail("prior_evidence_invalid", f"{label} must contain a JSON object")
    return document


def _immutable_inventory(*roots: Path) -> dict[str, str]:
    inventory: dict[str, str] = {}
    for root in roots:
        if root.is_symlink():
            _fail(
                "prior_evidence_invalid",
                f"immutable evidence path is a symlink: {root}",
            )
        if root.is_file():
            inventory[str(root)] = base._sha256_file(root)
            continue
        if not root.is_dir():
            _fail(
                "prior_evidence_invalid",
                f"immutable evidence root is unavailable: {root}",
            )
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                _fail(
                    "prior_evidence_invalid",
                    f"immutable evidence contains a symlink: {path}",
                )
            if path.is_file():
                inventory[str(path)] = base._sha256_file(path)
    return inventory


def _require_receipt(
    receipt: Mapping[str, Any],
    *,
    step: str,
) -> Mapping[str, Any]:
    result = receipt.get("result")
    if (
        receipt.get("status") != "PASS"
        or receipt.get("step") != step
        or not isinstance(result, Mapping)
        or result.get("status") != "PASS"
    ):
        _fail(
            "prior_receipt_invalid",
            f"prior Step {step} receipt must be an exact PASS",
        )
    return result


def validate_prior_evidence(
    *,
    prior_input_root: Path,
    prior_output_root: Path,
    expected_source_payloads: Mapping[str, bytes],
    model_config_git_blob: bytes,
    expected_final_report_sha256: str = PRIOR_FINAL_REPORT_SHA256,
    expected_wrapper_log_sha256: str = PRIOR_WRAPPER_LOG_SHA256,
    expected_identity_hashes: Mapping[str, str] | None = None,
    expected_model_config_sha256: str = (
        base.MODEL_CONFIG_GIT_BLOB_SHA256
    ),
    enforce_production_paths: bool = True,
) -> PriorEvidence:
    """Validate the immutable failed run without writing to either prior root."""

    if enforce_production_paths and (
        prior_input_root != PRIOR_INPUT_ROOT
        or prior_output_root != PRIOR_OUTPUT_ROOT
    ):
        _fail(
            "prior_path_mismatch",
            "resume is bound to the exact approved prior SageMaker roots",
        )
    if (
        prior_input_root.is_symlink()
        or not prior_input_root.is_dir()
        or prior_output_root.is_symlink()
        or not prior_output_root.is_dir()
    ):
        _fail(
            "prior_evidence_invalid",
            "prior input and output roots must be ordinary directories",
        )

    final_report_path = prior_output_root / "final_report.json"
    runtime_receipt_path = (
        prior_output_root / "runtime_preflight_receipt.json"
    )
    step6_1_path = prior_output_root / "step6_1.json"
    step6_2_path = prior_output_root / "step6_2.json"
    wrapper_log_path = (
        prior_output_root.parent
        / "wrapper-logs"
        / f"{PRIOR_SESSION_ID}.log"
    )
    required_files = (
        final_report_path,
        runtime_receipt_path,
        step6_1_path,
        step6_2_path,
        wrapper_log_path,
    )
    if any(
        path.is_symlink() or not path.is_file() for path in required_files
    ):
        _fail(
            "prior_evidence_invalid",
            "one or more required prior receipts/logs are absent or non-ordinary",
        )
    if base._sha256_file(final_report_path) != expected_final_report_sha256:
        _fail(
            "prior_final_report_hash_mismatch",
            "prior final_report.json SHA-256 differs",
        )
    if base._sha256_file(wrapper_log_path) != expected_wrapper_log_sha256:
        _fail(
            "prior_wrapper_log_hash_mismatch",
            "prior immutable wrapper-log SHA-256 differs",
        )

    final_report = _load_json_object(
        final_report_path,
        label="prior final report",
    )
    runtime_receipt = _load_json_object(
        runtime_receipt_path,
        label="prior runtime receipt",
    )
    step6_1_receipt = _load_json_object(
        step6_1_path,
        label="prior Step 6.1 receipt",
    )
    step6_2_receipt = _load_json_object(
        step6_2_path,
        label="prior Step 6.2 receipt",
    )
    step6_1_result = _require_receipt(step6_1_receipt, step="6.1")
    step6_2_result = _require_receipt(step6_2_receipt, step="6.2")
    sequence = final_report.get("sequence")
    report_receipts = final_report.get("step_receipts")
    if (
        final_report.get("status") != "FAIL"
        or final_report.get("runner_version") != PRIOR_RUNNER_VERSION
        or final_report.get("selected_pilot") != base.SELECTED_PILOT
        or final_report.get("deterministic_seed") != base.DETERMINISTIC_SEED
        or not isinstance(sequence, Mapping)
        or sequence.get("completed_steps") != ["6.1", "6.2"]
        or sequence.get("failed_step") != "6.3"
        or sequence.get("later_steps_executed_after_failure") is not False
        or final_report.get("handoff") is not None
        or report_receipts != [step6_1_receipt, step6_2_receipt]
    ):
        _fail(
            "prior_sequence_invalid",
            "prior report must show only Steps 6.1 and 6.2 completed",
        )
    identity_hashes = (
        {
            "capture_package": base.C_CAPTURE_PACKAGE_SHA256,
            "frame_map": base.C_FRAME_MAP_SHA256,
            "state": base.C_STATE_SHA256,
        }
        if expected_identity_hashes is None
        else dict(expected_identity_hashes)
    )
    observed_identity_hashes = {
        name: base._sha256_bytes(expected_source_payloads[name])
        for name in identity_hashes
    }
    if observed_identity_hashes != identity_hashes:
        _fail(
            "source_identity_mismatch",
            "C source payloads differ from the frozen source identities",
        )
    if (
        step6_1_result.get("pilot") != base.SELECTED_PILOT
        or step6_1_result.get("accepted_manifest_sha256")
        != base._sha256_bytes(expected_source_payloads["accepted_manifest"])
        or step6_1_result.get("capture_package_sha256")
        != identity_hashes["capture_package"]
        or Path(str(step6_1_result.get("input_root")))
        != prior_input_root
        or step6_2_result.get("pilot") != base.SELECTED_PILOT
        or step6_2_result.get("frame_count")
        != base.GLOBAL_MODEL_FRAME_COUNT
        or step6_2_result.get("identity_ambiguity_count") != 0
        or step6_2_result.get("stream_counts")
        != {
            "frame_map": base.GLOBAL_MODEL_FRAME_COUNT,
            "normalized_actions": base.GLOBAL_MODEL_FRAME_COUNT,
            "raw_actions": base.GLOBAL_MODEL_FRAME_COUNT,
            "server_state": base.GLOBAL_MODEL_FRAME_COUNT,
            "visibility": base.GLOBAL_MODEL_FRAME_COUNT,
        }
    ):
        _fail(
            "prior_receipt_invalid",
            "prior intake/model-boundary receipt identity differs",
        )
    direct_names = (
        "frame_map",
        "media",
        "normalized_actions",
        "raw_actions",
        "state",
        "visibility",
    )
    direct_hashes = {
        name: base._sha256_bytes(expected_source_payloads[name])
        for name in direct_names
    }
    if step6_1_result.get("direct_input_hashes") != direct_hashes:
        _fail(
            "prior_receipt_invalid",
            "prior Step 6.1 direct-input hashes differ",
        )

    if (
        runtime_receipt.get("status") != "PASS"
        or runtime_receipt.get("branch") != base.REQUIRED_BRANCH
        or runtime_receipt.get("runner_version") != PRIOR_RUNNER_VERSION
        or runtime_receipt.get("git_commit") != PRIOR_PERSON_A_COMMIT
        or runtime_receipt.get("mineworld_commit")
        != base.MINEWORLD_REVISION
        or runtime_receipt.get("model_config_git_blob_sha256")
        != expected_model_config_sha256
        or runtime_receipt.get("seed") != base.DETERMINISTIC_SEED
    ):
        _fail(
            "prior_runtime_identity_mismatch",
            "prior runtime receipt differs from the frozen pilot runtime",
        )

    input_paths = {
        name: prior_input_root / filename
        for name, filename in SOURCE_FILENAMES.items()
    }
    for name, path in input_paths.items():
        if path.is_symlink() or not path.is_file():
            _fail(
                "prior_input_invalid",
                f"prior materialized input is absent or non-ordinary: {name}",
            )
        if path.read_bytes() != expected_source_payloads[name]:
            _fail(
                "prior_input_hash_mismatch",
                f"prior materialized input differs from C Git bytes: {name}",
            )
    model_config_provenance_path = (
        prior_input_root / MODEL_CONFIG_PROVENANCE_FILENAME
    )
    if (
        model_config_provenance_path.is_symlink()
        or not model_config_provenance_path.is_file()
        or model_config_provenance_path.read_bytes() != model_config_git_blob
        or base._sha256_file(model_config_provenance_path)
        != expected_model_config_sha256
    ):
        _fail(
            "prior_input_hash_mismatch",
            "prior model-config provenance copy differs from Git-object bytes",
        )

    forbidden = (
        "step6_3.json",
        "step6_4.json",
        "step6_5.json",
        "step6_6_handoff.json",
        "bounded_audit",
    )
    if any(
        (prior_output_root / relative).exists()
        or (prior_output_root / relative).is_symlink()
        for relative in forbidden
    ):
        _fail(
            "prior_scientific_output_exists",
            "prior run contains Step 6.3+ completion evidence",
        )
    activation_store = prior_output_root.parent / (
        f"{PRIOR_SESSION_ID}-activation-store-v2"
    )
    if activation_store.exists() or activation_store.is_symlink():
        _fail(
            "prior_activation_output_exists",
            "prior Step 6.4 activation store already exists",
        )
    immutable_inventory = _immutable_inventory(
        prior_input_root,
        prior_output_root,
        wrapper_log_path,
    )
    return PriorEvidence(
        final_report=final_report,
        runtime_receipt=runtime_receipt,
        step6_1_receipt=step6_1_receipt,
        step6_2_receipt=step6_2_receipt,
        input_paths=input_paths,
        model_config_provenance_path=model_config_provenance_path,
        immutable_inventory=immutable_inventory,
        wrapper_log_path=wrapper_log_path,
    )


def continuation_identity(*, repaired_commit: str) -> str:
    """Return the deterministic distinct continuation session identifier."""

    identity = {
        "checkpoint_sha256": base.MAIN_CHECKPOINT_SHA256,
        "model_config_sha256": base.MODEL_CONFIG_GIT_BLOB_SHA256,
        "person_a_repaired_commit": repaired_commit,
        "pilot": base.SELECTED_PILOT,
        "preprocess_sha256": base.PREPROCESS_HASH,
        "prior_final_report_sha256": PRIOR_FINAL_REPORT_SHA256,
        "seed": base.DETERMINISTIC_SEED,
        "vae_checkpoint_sha256": base.VAE_CHECKPOINT_SHA256,
        "vae_config_sha256": base.VAE_CONFIG_SHA256,
    }
    digest = base._sha256_bytes(base._canonical_document_bytes(identity))
    return f"person-a-phase6-step6-3-continuation-{digest[:24]}"


def _validate_resume_ratification_document(
    document: object,
    *,
    current_commit: str,
    resume_runner_sha256: str,
) -> None:
    if not isinstance(document, Mapping):
        _fail(
            "missing_b_resume_ratification",
            "B resume ratification must contain a JSON object",
        )
    module_path = (
        ROOT / "src" / "mineocclude" / "activations" / "store_v2.py"
    )
    expected = {
        "activation_index_format_version": (
            base.ACTIVATION_INDEX_V2_FORMAT_VERSION
        ),
        "activation_store_format_version": (
            base.ACTIVATION_STORE_V2_FORMAT_VERSION
        ),
        "config_runtime_path_repair_authorized": True,
        "decision": "ratified",
        "expected_activation_row_count": (
            base.EXPECTED_ACTIVATION_ROW_COUNT
        ),
        "person_a_activation_store_v2_commit": current_commit,
        "person_a_activation_store_v2_module_sha256": (
            base._sha256_file(module_path)
        ),
        "person_a_repaired_commit": current_commit,
        "person_a_resume_runner_sha256": resume_runner_sha256,
        "prior_final_report_sha256": PRIOR_FINAL_REPORT_SHA256,
        "prior_wrapper_log_sha256": PRIOR_WRAPPER_LOG_SHA256,
        "reuse_prior_steps_6_1_6_2_authorized": True,
        "resume_start_step": "6.3",
        "scientific_execution_authorized": True,
        "seed": base.DETERMINISTIC_SEED,
        "selected_pilot": base.SELECTED_PILOT,
        "unchanged_authorization_boundary": True,
    }
    for field, value in expected.items():
        if document.get(field) != value:
            _fail(
                "missing_b_resume_ratification",
                f"B resume field {field!r} must equal {value!r}",
            )
    if document.get("owner") != "person_b":
        _fail(
            "missing_b_resume_ratification",
            "resume ratification must be owned by Person B",
        )


def verify_resume_ratification(
    *,
    repository: Path,
    object_expression: str,
    current_commit: str,
    resume_runner_sha256: str,
) -> dict[str, Any]:
    """Require an exact new B-owned object for this repaired commit."""

    if not object_expression or ":" not in object_expression:
        _fail(
            "missing_b_resume_ratification",
            "an exact <commit>:<path> B resume ratification is required",
        )
    commit, _separator, path = object_expression.partition(":")
    if (
        len(commit) != 40
        or not path
        or not base._git_commit_exists(repository, commit)
    ):
        _fail(
            "missing_b_resume_ratification",
            "B resume ratification commit/path does not resolve exactly",
        )
    try:
        payload = base._git_object_bytes(repository, object_expression)
        document = json.loads(payload)
    except (RuntimeError, UnicodeError, json.JSONDecodeError) as error:
        _fail(
            "missing_b_resume_ratification",
            f"B resume ratification cannot be verified: {error}",
        )
    _validate_resume_ratification_document(
        document,
        current_commit=current_commit,
        resume_runner_sha256=resume_runner_sha256,
    )
    return {
        "commit": commit,
        "git_object": object_expression,
        "sha256": base._sha256_bytes(payload),
        "verified": True,
    }


def plan_document() -> dict[str, Any]:
    """Return preparation metadata without importing torch or querying CUDA."""

    return {
        "b_new_resume_ratification_required": True,
        "config_runtime_path": (
            base.EXPECTED_SAGEMAKER_MODEL_CONFIG_PATH.as_posix()
        ),
        "expected_activation_rows": base.EXPECTED_ACTIVATION_ROW_COUNT,
        "local_scientific_execution_performed": False,
        "pilot": base.SELECTED_PILOT,
        "prior_final_report_sha256": PRIOR_FINAL_REPORT_SHA256,
        "prior_input_root": PRIOR_INPUT_ROOT.as_posix(),
        "prior_output_root": PRIOR_OUTPUT_ROOT.as_posix(),
        "prior_wrapper_log_sha256": PRIOR_WRAPPER_LOG_SHA256,
        "resume_start_step": "6.3",
        "resume_steps": list(RESUME_STEPS),
        "runner_version": RUNNER_VERSION,
        "seed": base.DETERMINISTIC_SEED,
        "steps_6_1_and_6_2_reexecuted": False,
    }


def _execute_resume_sequence(
    context: base.RunContext,
    handlers: Mapping[str, Callable[[base.RunContext], Mapping[str, Any]]],
) -> dict[str, Any]:
    completed: list[str] = []
    failure: dict[str, Any] | None = None
    failed_step: str | None = None
    for step in RESUME_STEPS:
        handler = handlers.get(step)
        if handler is None:
            _fail("missing_step_handler", f"missing resume handler {step}")
        started = time.perf_counter()
        try:
            result = dict(handler(context))
            if result.get("status") != "PASS":
                _fail(
                    "step_gate_failed",
                    f"Step {step} did not emit PASS",
                    step=step,
                )
            receipt = {
                "elapsed_seconds": time.perf_counter() - started,
                "result": result,
                "status": "PASS",
                "step": step,
            }
            context.step_receipts.append(receipt)
            completed.append(step)
            base._write_json(
                context.session_root / f"step{step.replace('.', '_')}.json",
                receipt,
            )
        except BaseException as error:  # noqa: BLE001
            failed_step = step
            failure = {
                "exception_message": str(error),
                "exception_type": type(error).__name__,
                "status": "FAIL",
                "step": step,
                "traceback": traceback.format_exc(),
            }
            break
    return {
        "completed_steps": completed,
        "failed_step": failed_step,
        "failure": failure,
        "later_steps_executed_after_failure": False,
        "resume_start_step": "6.3",
        "status": "PASS" if failed_step is None else "FAIL",
        "steps_6_1_and_6_2_reexecuted": False,
    }


def _rehydrate_prior_validated_state(
    context: base.RunContext,
    prior: PriorEvidence,
) -> None:
    """Recreate adapter memory from already-validated immutable source bytes."""

    adapter_module = importlib.import_module(
        "mineocclude.models.mineworld_adapter"
    )
    identity_module = importlib.import_module(
        "mineocclude.contracts.identity"
    )
    package = json.loads(prior.input_paths["capture_package"].read_bytes())
    names = (
        "frame_map",
        "raw_actions",
        "normalized_actions",
        "server_state",
        "visibility",
    )
    streams = {
        name: package["streams"][name]
        for name in names
    }
    adapter = adapter_module.create_mineworld_adapter()
    validated = adapter.validate_trajectory(
        adapter_module.AcceptedTrajectoryInput(
            schema_version=identity_module.SCHEMA_VERSION,
            trajectory_id=base.SELECTED_PILOT,
            accepted_manifest_sha256=base.C_CAPTURE_PACKAGE_SHA256,
            document=package,
        )
    )
    if len(validated.frame_identities) != base.GLOBAL_MODEL_FRAME_COUNT:
        _fail(
            "resume_state_rehydration_failed",
            "prior validated trajectory did not reconstruct 248 identities",
        )
    context.state.update(
        {
            "adapter": adapter,
            "capture_package": package,
            "input_paths": prior.input_paths,
            "model_config_provenance_path": (
                prior.model_config_provenance_path
            ),
            "streams": streams,
            "validated_trajectory": validated,
        }
    )


def run(arguments: ResumeArguments) -> int:
    """Execute only Steps 6.3 through 6.5 after every immutable gate passes."""

    repository = arguments.base_arguments.repository_root
    current_commit = str(base._run_git(repository, "rev-parse", "HEAD"))
    resume_runner_sha256 = base._sha256_file(Path(__file__).resolve())
    source_payloads = base._source_object_payloads(repository)
    model_config_blob = base._git_object_bytes(
        arguments.base_arguments.mineworld_root,
        f"{base.MINEWORLD_REVISION}:{base.MODEL_CONFIG_PATH}",
    )
    prior = validate_prior_evidence(
        prior_input_root=arguments.prior_input_root,
        prior_output_root=arguments.prior_output_root,
        expected_source_payloads=source_payloads,
        model_config_git_blob=model_config_blob,
    )
    ratification = verify_resume_ratification(
        repository=repository,
        object_expression=arguments.resume_ratification_object,
        current_commit=current_commit,
        resume_runner_sha256=resume_runner_sha256,
    )
    runtime_receipt = base.runtime_preflight(arguments.base_arguments)
    session_id = continuation_identity(repaired_commit=current_commit)
    if arguments.base_arguments.session_id != session_id:
        _fail(
            "continuation_identity_mismatch",
            "session ID must equal the deterministic continuation identity",
        )
    session_root = (
        arguments.base_arguments.approved_output_root / session_id
    )
    if session_root.exists() or session_root.is_symlink():
        _fail(
            "output_exists",
            "immutable continuation session already exists",
        )
    session_root.mkdir()
    runtime_receipt["b_resume_ratification"] = ratification
    runtime_receipt["resume_runner_sha256"] = resume_runner_sha256
    base._write_json(
        session_root / "runtime_preflight_receipt.json",
        runtime_receipt,
    )
    binding = {
        "continuation_session_id": session_id,
        "person_a_repaired_commit": current_commit,
        "prior_final_report_sha256": PRIOR_FINAL_REPORT_SHA256,
        "prior_input_root": str(arguments.prior_input_root),
        "prior_output_root": str(arguments.prior_output_root),
        "prior_step6_1_receipt_sha256": base._sha256_file(
            arguments.prior_output_root / "step6_1.json"
        ),
        "prior_step6_2_receipt_sha256": base._sha256_file(
            arguments.prior_output_root / "step6_2.json"
        ),
        "prior_wrapper_log_sha256": PRIOR_WRAPPER_LOG_SHA256,
        "resume_start_step": "6.3",
        "steps_6_1_and_6_2_reexecuted": False,
    }
    base._write_json(session_root / "resume_binding_receipt.json", binding)
    context = base.RunContext(
        arguments=arguments.base_arguments,
        session_root=session_root,
        runtime_receipt=runtime_receipt,
    )
    _rehydrate_prior_validated_state(context, prior)
    sequence = _execute_resume_sequence(
        context,
        {
            "6.3": base.step6_3_tokenize,
            "6.4": base.step6_4_extract_store,
            "6.5": base.step6_5_certify,
        },
    )
    handoff = (
        base._prepare_step6_6_handoff(context)
        if sequence["status"] == "PASS"
        else None
    )
    report = {
        "combined_steps": {
            "prior_completed_steps": ["6.1", "6.2"],
            "resume": sequence,
        },
        "deterministic_seed": base.DETERMINISTIC_SEED,
        "expected_activation_row_count": (
            base.EXPECTED_ACTIVATION_ROW_COUNT
        ),
        "handoff": handoff,
        "pilot": base.SELECTED_PILOT,
        "prior_receipts": {
            "final_report_sha256": PRIOR_FINAL_REPORT_SHA256,
            "step6_1_sha256": binding["prior_step6_1_receipt_sha256"],
            "step6_2_sha256": binding["prior_step6_2_receipt_sha256"],
            "wrapper_log_sha256": PRIOR_WRAPPER_LOG_SHA256,
        },
        "prior_session_modified": False,
        "prior_step6_2_adapter_state_rehydrated_without_receipt_rewrite": True,
        "resume_receipt_hashes": [
            {
                "path": f"step{receipt['step'].replace('.', '_')}.json",
                "sha256": base._sha256_file(
                    session_root
                    / f"step{receipt['step'].replace('.', '_')}.json"
                ),
                "step": receipt["step"],
            }
            for receipt in context.step_receipts
        ],
        "resume_step_receipts": context.step_receipts,
        "runner_version": RUNNER_VERSION,
        "status": sequence["status"],
    }
    current_inventory = _immutable_inventory(
        arguments.prior_input_root,
        arguments.prior_output_root,
        prior.wrapper_log_path,
    )
    if current_inventory != prior.immutable_inventory:
        _fail(
            "prior_evidence_modified",
            "prior immutable inputs, receipts, or logs changed during resume",
        )
    base._write_json(session_root / "combined_final_report.json", report)
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0 if sequence["status"] == "PASS" else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    operations = parser.add_subparsers(dest="operation", required=True)
    operations.add_parser("plan")
    identity = operations.add_parser("continuation-id")
    identity.add_argument("--repository-root", type=Path, default=ROOT)
    resume = operations.add_parser("resume")
    resume.add_argument("--repository-root", type=Path, default=ROOT)
    resume.add_argument("--mineworld-root", type=Path, required=True)
    resume.add_argument("--asset-root", type=Path, required=True)
    resume.add_argument("--main-checkpoint", type=Path, required=True)
    resume.add_argument("--vae-config", type=Path, required=True)
    resume.add_argument("--vae-checkpoint", type=Path, required=True)
    resume.add_argument("--approved-input-root", type=Path, required=True)
    resume.add_argument("--approved-output-root", type=Path, required=True)
    resume.add_argument(
        "--prior-input-root",
        type=Path,
        default=PRIOR_INPUT_ROOT,
    )
    resume.add_argument(
        "--prior-output-root",
        type=Path,
        default=PRIOR_OUTPUT_ROOT,
    )
    resume.add_argument(
        "--resume-ratification-object",
        default=os.environ.get(
            "PERSON_B_PHASE6_STEP6_3_RESUME_RATIFICATION_OBJECT",
            "",
        ),
    )
    resume.add_argument(
        "--activation-store-v2-ratification-object",
        default=os.environ.get(
            "PERSON_B_PHASE6_STEP6_3_RESUME_RATIFICATION_OBJECT",
            "",
        ),
    )
    resume.add_argument("--seed", type=int, default=base.DETERMINISTIC_SEED)
    resume.add_argument("--device", default=base.REQUIRED_DEVICE)
    resume.add_argument("--precision", choices=("float16",), default="float16")
    return parser


def _resume_arguments(namespace: argparse.Namespace) -> ResumeArguments:
    repository = namespace.repository_root.resolve()
    current_commit = str(base._run_git(repository, "rev-parse", "HEAD"))
    session_id = continuation_identity(repaired_commit=current_commit)
    base_arguments = base.RunnerArguments(
        repository_root=repository,
        mineworld_root=namespace.mineworld_root.resolve(),
        asset_root=namespace.asset_root.resolve(),
        main_checkpoint=namespace.main_checkpoint.resolve(),
        vae_config=namespace.vae_config.resolve(),
        vae_checkpoint=namespace.vae_checkpoint.resolve(),
        approved_input_root=namespace.approved_input_root.resolve(),
        approved_output_root=namespace.approved_output_root.resolve(),
        activation_store_v2_ratification_object=(
            namespace.activation_store_v2_ratification_object
        ),
        session_id=session_id,
        seed=namespace.seed,
        device=namespace.device,
        precision=namespace.precision,
    )
    return ResumeArguments(
        base_arguments=base_arguments,
        prior_input_root=namespace.prior_input_root,
        prior_output_root=namespace.prior_output_root,
        resume_ratification_object=namespace.resume_ratification_object,
    )


def main(argv: list[str] | None = None) -> int:
    namespace = _parser().parse_args(argv)
    if namespace.operation == "plan":
        print(json.dumps(plan_document(), sort_keys=True, allow_nan=False))
        return 0
    if namespace.operation == "continuation-id":
        commit = str(
            base._run_git(
                namespace.repository_root.resolve(),
                "rev-parse",
                "HEAD",
            )
        )
        print(continuation_identity(repaired_commit=commit))
        return 0
    try:
        return run(_resume_arguments(namespace))
    except BaseException as error:  # noqa: BLE001
        report = {
            "exception_message": str(error),
            "exception_type": type(error).__name__,
            "runner_version": RUNNER_VERSION,
            "status": "FAIL",
            "traceback": traceback.format_exc(),
        }
        print(json.dumps(report, sort_keys=True, allow_nan=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
