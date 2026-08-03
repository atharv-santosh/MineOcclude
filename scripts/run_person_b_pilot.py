"""Run the authenticated Person B pilot path when real inputs become available."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.analysis.pilot import (  # noqa: E402
    build_pilot_failure_artifact,
    build_u2_pilot_metrics,
    prepare_pilot_inputs,
    require_positive_control_pass,
    run_plumbing_smoke,
    run_probe_scope,
)
from mineocclude.analysis.layout_fold_plan import (  # noqa: E402
    LayoutFoldPlanError,
    bind_frame_fold_artifacts_to_layout_plan,
    validate_layout_fold_plan,
)
from mineocclude.analysis.selection import (  # noqa: E402
    SCOPE_HIDDEN_MEAN,
    SCOPE_HIDDEN_SPREAD,
    SCOPE_VISIBLE_NO_WALL,
    build_analysis_selection_manifest,
    selections_from_condition_source,
)
from mineocclude.experiments.registry import (  # noqa: E402
    hash_file_bytes,
    load_json_with_sha256,
    write_json_exclusive,
)
from mineocclude.probes.bridge import derive_probe_code_sha  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Authenticate A activations and B targets, freeze filters/folds/"
            "selection, and run one declared probe scope."
        )
    )
    parser.add_argument("activation_handoff", type=Path)
    parser.add_argument("target_document", type=Path)
    parser.add_argument("selection_source", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument(
        "--layout-fold-plan",
        required=True,
        type=Path,
        help=(
            "Sealed pre-A fold plan derived from accepted Person C rows."
        ),
    )
    parser.add_argument("--artifact-id-prefix", required=True)
    parser.add_argument(
        "--scope",
        required=True,
        choices=[
            "visible_no_wall_control",
            "hidden_mean",
            "hidden_spread",
        ],
    )
    parser.add_argument(
        "--chunk-root",
        type=Path,
        help="Base directory for descriptor paths (default: handoff directory).",
    )
    parser.add_argument(
        "--control-gate",
        type=Path,
        help=(
            "Required for hidden scopes. The visible control is rerun and this "
            "sealed gate must approve that exact bundle."
        ),
    )
    parser.add_argument(
        "--permutation-count",
        type=int,
        help="Known-answer override; real evidence must match core.yaml.",
    )
    return parser.parse_args()


def _chunk_payloads(
    activation: dict[str, Any],
    *,
    chunk_root: Path,
) -> dict[str, bytes]:
    payloads: dict[str, bytes] = {}
    for descriptor in activation["chunks"]:
        chunk_id = descriptor["chunk_id"]
        relative_path = Path(descriptor["path"])
        path = (
            relative_path
            if relative_path.is_absolute()
            else chunk_root / relative_path
        )
        payloads[chunk_id] = path.read_bytes()
    return payloads


def _filename(artifact: dict[str, Any]) -> str:
    artifact_id = str(artifact["artifact_id"])
    safe = artifact_id.replace(":", "_").replace("/", "_").replace("\\", "_")
    return safe + ".json"


def _write_artifact(output_directory: Path, artifact: dict[str, Any]) -> None:
    write_json_exclusive(output_directory / _filename(artifact), artifact)


def _write_scope_run(output_directory: Path, run: Any) -> None:
    for ridge in run.ridge_runs:
        _write_artifact(output_directory, dict(ridge.matrix_artifact))
        for artifact in (*ridge.scaler_artifacts, *ridge.fit_artifacts):
            _write_artifact(output_directory, dict(artifact))
        _write_artifact(output_directory, dict(ridge.prediction_artifact))
        _write_artifact(output_directory, dict(ridge.u1_result_artifact))
    for permutation in run.permutation_runs:
        _write_artifact(output_directory, dict(permutation.result_artifact))
    _write_artifact(output_directory, dict(run.bundle))


def execute(args: argparse.Namespace) -> None:
    activation, _activation_file_hash = load_json_with_sha256(
        args.activation_handoff
    )
    targets, _target_file_hash = load_json_with_sha256(args.target_document)
    selection_source, selection_source_file_hash = load_json_with_sha256(
        args.selection_source
    )
    layout_fold_plan, _layout_fold_plan_file_hash = load_json_with_sha256(
        args.layout_fold_plan
    )
    validate_layout_fold_plan(layout_fold_plan)
    if (
        layout_fold_plan.get("input_manifest_hash")
        != selection_source_file_hash
    ):
        raise LayoutFoldPlanError(
            "Layout fold plan belongs to a different condition source."
        )
    selections = selections_from_condition_source(selection_source)
    chunk_root = args.chunk_root or args.activation_handoff.parent
    chunk_payloads = _chunk_payloads(activation, chunk_root=chunk_root)

    preparation = prepare_pilot_inputs(
        activation,
        targets,
        chunk_payloads,
        artifact_id_prefix=args.artifact_id_prefix,
    )
    if preparation.fold_manifest is None:
        raise LayoutFoldPlanError(
            "Real pilot inputs do not cover the C-frozen evaluative folds."
        )
    bound_fold_manifest, bound_intake_receipt = (
        bind_frame_fold_artifacts_to_layout_plan(
            layout_fold_plan,
            preparation.fold_manifest,
            preparation.intake_receipt,
        )
    )
    preparation = replace(
        preparation,
        fold_manifest=bound_fold_manifest,
        intake_receipt=bound_intake_receipt,
    )
    selection = build_analysis_selection_manifest(
        preparation.frame_table,
        selections,
        artifact_id=f"{args.artifact_id_prefix}:selection",
        code_sha=derive_probe_code_sha(),
        source_condition_manifest_hash=selection_source_file_hash,
    )

    # Preparation evidence is written before any fit. Exclusive writes make a
    # rerun choose a new artifact identity rather than replacing prior evidence.
    write_json_exclusive(
        args.output_directory / "joined_frame_table.json",
        preparation.frame_table,
    )
    _write_artifact(args.output_directory, dict(preparation.oracle_audit))
    _write_artifact(args.output_directory, dict(preparation.filter_audit))
    _write_artifact(args.output_directory, dict(preparation.intake_receipt))
    if preparation.fold_manifest is not None:
        _write_artifact(args.output_directory, dict(preparation.fold_manifest))
    _write_artifact(args.output_directory, selection)

    if preparation.fold_manifest is None:
        smoke = run_plumbing_smoke(
            preparation,
            activation,
            targets,
            chunk_payloads,
            selection,
            scope=args.scope,
            artifact_id=f"{args.artifact_id_prefix}:{args.scope}:plumbing_smoke",
        )
        _write_artifact(args.output_directory, smoke)
        return

    if args.scope == SCOPE_VISIBLE_NO_WALL:
        run = run_probe_scope(
            preparation,
            activation,
            targets,
            chunk_payloads,
            selection,
            scope=args.scope,
            artifact_id_prefix=args.artifact_id_prefix,
            permutation_count=args.permutation_count,
        )
        _write_scope_run(args.output_directory, run)
        return

    if args.control_gate is None:
        raise ValueError(
            "Hidden scopes require --control-gate after the visible control review."
        )
    control = run_probe_scope(
        preparation,
        activation,
        targets,
        chunk_payloads,
        selection,
        scope=SCOPE_VISIBLE_NO_WALL,
        artifact_id_prefix=args.artifact_id_prefix,
        permutation_count=args.permutation_count,
    )
    gate, _gate_file_hash = load_json_with_sha256(args.control_gate)
    require_positive_control_pass(gate, control_run=control)
    run = run_probe_scope(
        preparation,
        activation,
        targets,
        chunk_payloads,
        selection,
        scope=args.scope,
        artifact_id_prefix=args.artifact_id_prefix,
        permutation_count=args.permutation_count,
    )
    _write_scope_run(args.output_directory, run)
    if args.scope == SCOPE_HIDDEN_SPREAD:
        mean_run = run_probe_scope(
            preparation,
            activation,
            targets,
            chunk_payloads,
            selection,
            scope=SCOPE_HIDDEN_MEAN,
            artifact_id_prefix=args.artifact_id_prefix,
            permutation_count=args.permutation_count,
        )
        _write_scope_run(args.output_directory, mean_run)
        u2 = build_u2_pilot_metrics(
            mean_run,
            run,
            control_run=control,
            control_gate=gate,
            artifact_id_prefix=args.artifact_id_prefix,
        )
        for artifact in u2.result_artifacts:
            _write_artifact(args.output_directory, dict(artifact))
        _write_artifact(args.output_directory, dict(u2.bundle))


def main() -> None:
    args = parse_args()
    try:
        execute(args)
    except Exception as error:
        try:
            target_document, _ = load_json_with_sha256(args.target_document)
            source_synthetic = isinstance(target_document, dict) and isinstance(
                target_document.get("fixture_metadata"),
                dict,
            )
            failure = build_pilot_failure_artifact(
                artifact_id=f"{args.artifact_id_prefix}:failure",
                stage="pilot_cli",
                input_manifest_hash=hash_file_bytes(args.target_document),
                error=error,
                source_synthetic=source_synthetic,
            )
            _write_artifact(args.output_directory, failure)
        except Exception:
            # Preserve the scientific/contract exception as the primary error.
            pass
        raise


if __name__ == "__main__":
    main()
