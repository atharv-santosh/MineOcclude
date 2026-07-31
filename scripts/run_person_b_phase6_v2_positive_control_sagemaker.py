"""Execute the ratified Person B v2 visible-position control on SageMaker only.

This runner is intentionally not exercised by unit tests.  Tests validate the
consumer and bridge with deterministic fixtures; this command performs the
subsequent scientific Step 6.6 only after the owner-ratification commit exists.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.analysis.coordinates_v2 import (
    build_state_input_v2_from_capture_bytes,
)
from mineocclude.analysis.positive_control_v2 import (
    ALL_PILOT_IDS,
    PERSON_A_TEN_PILOT_COMMIT,
    PERSON_B_AUTHORIZATION_COMMIT,
    PERSON_B_SELECTION_COMMIT,
    PERSON_C_ACCEPTANCE_COMMIT,
    VISIBLE_CONTROL_PILOT_IDS,
    bridge_lineage_document,
    build_positive_control_bridge_v2,
    validate_ten_pilot_authority_documents,
)
from mineocclude.contracts.activation_v2 import (
    external_chunk_bindings,
    load_activation_index_v2,
)
from mineocclude.experiments.registry import write_json_exclusive

A_RUNTIME_ROOT = (
    "docs/status/phase6_runtime/person-a-phase6-ten-pilot-expansion-seed-20260725"
)
C_ACCEPTANCE_PATH = (
    "docs/status/person_c_phase6_ten_pilot_expansion_acceptance_v0_1/"
    "accepted_pilot_manifest.json"
)
B_RATIFICATION_PATH = (
    "docs/status/person_b_phase6_v2_consumer_ratification_v0_1/owner_ratification.json"
)
DEFAULT_OUTPUT_ROOT = Path(
    "/home/sagemaker-user/person-b-phase6-approved-outputs/"
    "person-b-phase6-v2-positive-control-step6-6"
)


class SageMakerPositiveControlError(RuntimeError):
    """Fail-closed runtime or authority error."""


def _fail(message: str) -> None:
    raise SageMakerPositiveControlError(message)


def _git(repository: Path, *arguments: str, text: bool = True) -> str | bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=True,
            capture_output=True,
            text=text,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        _fail(f"Git authority read failed: {error}")
    return completed.stdout


def _git_json(repository: Path, commit: str, path: str) -> Mapping[str, Any]:
    payload = _git(repository, "show", f"{commit}:{path}", text=False)
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail(f"Exact Git object {commit}:{path} is invalid JSON: {error}")
    if not isinstance(document, Mapping):
        _fail(f"Exact Git object {commit}:{path} must be an object.")
    return document


def _require_authorities(repository: Path, ratification_commit: str) -> None:
    for commit in (
        PERSON_A_TEN_PILOT_COMMIT,
        PERSON_B_SELECTION_COMMIT,
        PERSON_B_AUTHORIZATION_COMMIT,
        PERSON_C_ACCEPTANCE_COMMIT,
        ratification_commit,
    ):
        if _git(repository, "cat-file", "-t", commit).strip() != "commit":
            _fail(f"Required authority commit is unavailable: {commit}")
    _git(repository, "merge-base", "--is-ancestor", ratification_commit, "HEAD")
    ratification = _git_json(repository, ratification_commit, B_RATIFICATION_PATH)
    if (
        ratification.get("decision") != "RATIFY_EXACT_V2_POSITIVE_CONTROL_CONSUMER"
        or ratification.get("authorized_execution")
        != "person_b_frozen_visible_position_positive_control_only"
        or ratification.get("person_a_ten_pilot_commit") != PERSON_A_TEN_PILOT_COMMIT
        or ratification.get("person_b_expansion_selection_commit")
        != PERSON_B_SELECTION_COMMIT
        or ratification.get("person_b_expansion_authorization_commit")
        != PERSON_B_AUTHORIZATION_COMMIT
        or ratification.get("person_c_expansion_acceptance_commit")
        != PERSON_C_ACCEPTANCE_COMMIT
        or ratification.get("hidden_state_interpretation_authorized") is not False
        or ratification.get("u4_output_inspected") is not False
    ):
        _fail("Person B owner ratification is missing or expands the boundary.")


def _require_clean_sagemaker_runtime(repository: Path) -> None:
    if platform.system() != "Linux":
        _fail("Scientific Step 6.6 is authorized only on the SageMaker Linux host.")
    if not (
        os.environ.get("SM_MODEL_DIR")
        or os.environ.get("SM_NUM_GPUS")
        or Path("/opt/ml").exists()
        or Path("/home/sagemaker-user").exists()
    ):
        _fail("AWS SageMaker runtime identity was not detected.")
    try:
        import torch
    except ImportError as error:
        _fail(f"PyTorch is required for the frozen CUDA precondition: {error}")
    if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
        _fail("cuda:0 is unavailable; local CPU-only execution is forbidden.")
    if _git(repository, "status", "--porcelain").strip():
        _fail("Person B SageMaker worktree must be clean before Step 6.6.")
    if _git(repository, "branch", "--show-current").strip() != "role/person-b-analysis":
        _fail("Step 6.6 must run on role/person-b-analysis.")


def _load_authority_documents(repository: Path) -> tuple[Any, ...]:
    completion = _git_json(
        repository,
        PERSON_A_TEN_PILOT_COMMIT,
        f"{A_RUNTIME_ROOT}/completion_report.json",
    )
    artifact_manifest = _git_json(
        repository,
        PERSON_A_TEN_PILOT_COMMIT,
        f"{A_RUNTIME_ROOT}/artifact_manifest.json",
    )
    handoff = _git_json(
        repository,
        PERSON_A_TEN_PILOT_COMMIT,
        f"{A_RUNTIME_ROOT}/person_b_step6_6_positive_control_handoff.json",
    )
    inventories = {
        trajectory_id: _git_json(
            repository,
            PERSON_A_TEN_PILOT_COMMIT,
            f"{A_RUNTIME_ROOT}/per_pilot_inventories/{trajectory_id}.json",
        )
        for trajectory_id in ALL_PILOT_IDS
    }
    c_acceptance = _git_json(
        repository,
        PERSON_C_ACCEPTANCE_COMMIT,
        C_ACCEPTANCE_PATH,
    )
    return completion, artifact_manifest, handoff, inventories, c_acceptance


def _load_indices(
    inventories: Mapping[str, Mapping[str, Any]],
    *,
    accepted_manifest_by_trajectory: Mapping[str, str],
) -> dict[str, Any]:
    loaded = {}
    for trajectory_id in ALL_PILOT_IDS:
        inventory = inventories[trajectory_id]
        index = inventory["activation_index"]
        loaded[trajectory_id] = load_activation_index_v2(
            index["path"],
            expected_index_sha256=index["sha256"],
            expected_index_byte_size=index["byte_size"],
            expected_trajectory_id=trajectory_id,
            expected_manifest_sha256=accepted_manifest_by_trajectory[trajectory_id],
            chunk_bindings=external_chunk_bindings(inventory["chunks"]),
            retain_vectors=trajectory_id in VISIBLE_CONTROL_PILOT_IDS,
        )
    return loaded


def _load_control_states(
    repository: Path,
    *,
    indices: Mapping[str, Any],
    capture_path_by_trajectory: Mapping[str, str],
    accepted_manifest_by_trajectory: Mapping[str, str],
) -> dict[str, Mapping[str, Any]]:
    states = {}
    for trajectory_id in VISIBLE_CONTROL_PILOT_IDS:
        capture_object_path = capture_path_by_trajectory[trajectory_id]
        coordinate_path = (
            repository
            / "data"
            / "person_b"
            / "phase6_c_intake"
            / "coordinate_frames"
            / f"{trajectory_id}.json"
        )
        try:
            coordinate = json.loads(coordinate_path.read_text(encoding="utf-8"))
            capture_bytes = _git(
                repository,
                "show",
                f"{PERSON_C_ACCEPTANCE_COMMIT}:{capture_object_path}",
                text=False,
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            _fail(
                f"Could not read Person B/C state authority for {trajectory_id}: {error}"
            )
        store_identity = indices[trajectory_id].store_identity
        states[trajectory_id] = build_state_input_v2_from_capture_bytes(
            capture_bytes,
            expected_literal_capture_package_sha256=(
                accepted_manifest_by_trajectory[trajectory_id]
            ),
            coordinate_frame=coordinate,
            model_hash=store_identity["model_hash"],
            preprocess_hash=store_identity["preprocess_hash"],
        )
    return states


def _execute_positive_control(bridge: Any) -> list[dict[str, Any]]:
    """Run only the frozen visible-position ridge control after all gates pass."""

    from mineocclude.probes.ridge import fit_ridge_oof

    results = []
    for matrix in bridge.matrices:
        fitted = fit_ridge_oof(
            matrix.features,
            matrix.targets,
            matrix.outer_folds,
            matrix.layout_ids,
            alpha_grid=(0.1, 1.0, 10.0, 100.0),
            inner_fold_count=4,
            seed=20260719,
        )
        residuals = [
            prediction - target
            for prediction, target in zip(
                fitted.predictions, matrix.targets, strict=True
            )
        ]
        mse = sum(value * value for value in residuals) / len(residuals)
        target_mean = sum(matrix.targets) / len(matrix.targets)
        total = sum((target - target_mean) ** 2 for target in matrix.targets)
        r2 = (
            None
            if total <= 0.0
            else 1.0 - sum(value * value for value in residuals) / total
        )
        if not math.isfinite(mse) or (r2 is not None and not math.isfinite(r2)):
            _fail("Positive-control fit produced a non-finite diagnostic.")
        results.append(
            {
                "fold_fits": [
                    {
                        "inner_fold_count": fit.alpha_selection.inner_fold_count,
                        "mean_mse_by_alpha": [
                            {"alpha": alpha, "mean_mse": loss}
                            for alpha, loss in sorted(
                                fit.alpha_selection.mean_mse_by_alpha.items()
                            )
                        ],
                        "outer_fold_idx": fit.outer_fold_idx,
                        "selected_alpha": fit.alpha_selection.selected_alpha,
                        "test_indices": list(fit.test_indices),
                        "training_indices": list(fit.training_indices),
                    }
                    for fit in fitted.fits
                ],
                "hook_site": matrix.hook_site,
                "layer_idx": matrix.layer_idx,
                "matrix_hash": matrix.matrix_hash,
                "mse_blocks2": mse,
                "oof_predictions": list(fitted.predictions),
                "r2": r2,
                "row_count": len(matrix.targets),
            }
        )
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the ratified Person B Activation Store v2 positive control."
    )
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--ratification-commit", required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repository = args.repository_root.resolve()
    output_root = args.output_root
    _require_clean_sagemaker_runtime(repository)
    _require_authorities(repository, args.ratification_commit)
    completion, artifact_manifest, handoff, inventories, c_acceptance = (
        _load_authority_documents(repository)
    )
    authority = validate_ten_pilot_authority_documents(
        completion_report=completion,
        artifact_manifest=artifact_manifest,
        positive_control_handoff=handoff,
        per_pilot_inventories=inventories,
        c_accepted_manifest=c_acceptance,
    )
    indices = _load_indices(
        inventories,
        accepted_manifest_by_trajectory=authority.accepted_c_manifest_by_trajectory,
    )
    states = _load_control_states(
        repository,
        indices=indices,
        capture_path_by_trajectory=authority.c_capture_path_by_trajectory,
        accepted_manifest_by_trajectory=authority.accepted_c_manifest_by_trajectory,
    )
    try:
        fold_plan = json.loads(
            (
                repository / "data/person_b/phase6_c_intake/layout_fold_plan.json"
            ).read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        _fail(f"Could not read the frozen Person B fold plan: {error}")
    bridge = build_positive_control_bridge_v2(
        indices,
        states,
        authority=authority,
        fold_plan=fold_plan,
    )
    results = _execute_positive_control(bridge)
    if output_root.exists() or output_root.is_symlink():
        _fail(f"No-overwrite output root already exists: {output_root}")
    output_root.mkdir(parents=True, exist_ok=False)
    report = {
        "automatic_hidden_state_transition": False,
        "decision": "AWAITING_PERSON_B_POSITIVE_CONTROL_GATE_REVIEW",
        "e_registry_v2_lineage": bridge_lineage_document(bridge),
        "frozen_target": "x_true_blocks",
        "hidden_state_interpretation_authorized": False,
        "person_a_ten_pilot_commit": PERSON_A_TEN_PILOT_COMMIT,
        "person_b_owner_ratification_commit": args.ratification_commit,
        "positive_control_results": results,
        "schema_version": "1.0",
        "scientific_execution_performed": True,
        "u4_output_inspected": False,
    }
    write_json_exclusive(output_root / "person_b_step6_6_positive_control.json", report)
    print(f"PERSON_B_STEP6_6_OUTPUT={output_root}")


if __name__ == "__main__":
    main()
