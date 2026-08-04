"""Preflight, run, or validate the bounded Phase 4 Wave 2 pooling probe.

``preflight`` deliberately imports no PyTorch module, performs no CUDA query,
and creates no session directory. ``run`` is prepared for the qualified AWS
runtime and is not a local execution path.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import hashlib
import json
import math
import re
import sys
import time
from collections.abc import Mapping
from itertools import pairwise
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PROBE_VERSION = "person-a-phase4-wave2-pooling-probe-v1.0"
EXPECTED_LAYER_COUNT = 20
EXPECTED_HIDDEN_SIZE = 2048
EXPECTED_VISUAL_TOKENS = 336
EXPECTED_ACTION_TOKENS = 11
EXPECTED_FORWARD_COUNT = 1
MEMORY_TOLERANCE_BYTES = 1_048_576
HOOK_SITE = "decoder_layer_output_residual_stream"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _common_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--mineworld-source-root", required=True, type=Path)
    command.add_argument("--asset-root", required=True, type=Path)
    command.add_argument("--evidence-root", required=True, type=Path)
    command.add_argument(
        "--accepted-trajectory-package",
        required=True,
        type=Path,
    )
    command.add_argument(
        "--accepted-trajectory-package-sha256",
        required=True,
    )
    command.add_argument("--input-mp4", required=True, type=Path)
    command.add_argument("--input-mp4-sha256", required=True)
    command.add_argument("--environment-report", required=True, type=Path)
    command.add_argument("--environment-report-sha256", required=True)
    command.add_argument("--session-id", required=True)
    command.add_argument("--seed", required=True, type=int)
    command.add_argument("--precision", required=True)
    command.add_argument("--device", required=True)
    command.add_argument("--mineocclude-revision", required=True)
    command.add_argument("--ffprobe", default="ffprobe")
    command.add_argument(
        "--expected-layer-count",
        type=int,
        default=EXPECTED_LAYER_COUNT,
    )
    command.add_argument(
        "--expected-hidden-size",
        type=int,
        default=EXPECTED_HIDDEN_SIZE,
    )
    command.add_argument(
        "--forward-count",
        type=int,
        default=EXPECTED_FORWARD_COUNT,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare, run, or validate one immutable Person A Phase 4 "
            "Wave 2 real-runtime pooling probe."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser(
        "preflight",
        help="CPU-only validation without PyTorch, CUDA, or session creation",
    )
    _common_arguments(preflight)
    run = commands.add_parser(
        "run",
        help="execute one explicitly confirmed real CUDA pooling probe",
    )
    _common_arguments(run)
    run.add_argument("--confirm-runtime-probe", action="store_true")
    validate = commands.add_parser(
        "validate",
        help="independently validate a completed real-runtime report",
    )
    validate.add_argument("--report", required=True, type=Path)
    validate.add_argument("--verify-files", action="store_true")
    return parser


def _raise(code: str, message: str) -> None:
    from mineocclude.models.phase2_evidence import EvidenceValidationError

    raise EvidenceValidationError(code, message)


def _require_sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value.lower()) is None:
        _raise("invalid_sha256", f"{field} must be one lowercase SHA-256")
    return value.lower()


def _sha256_file(path: Path) -> str:
    from mineocclude.models.phase2_evidence import sha256_file

    return sha256_file(path)


def preflight(args: argparse.Namespace) -> dict[str, Any]:
    """Run the shared Phase 3 CPU boundary plus Wave 2-specific assertions."""

    torch_was_loaded = "torch" in sys.modules
    if torch_was_loaded:
        _raise(
            "preflight_runtime_imported",
            "preflight must begin before torch is imported",
        )
    from mineocclude.models import phase3_certification as phase3

    phase3_args = argparse.Namespace(
        mineworld_source_root=args.mineworld_source_root,
        asset_root=args.asset_root,
        evidence_root=args.evidence_root,
        accepted_trajectory_package=args.accepted_trajectory_package,
        input_mp4=args.input_mp4,
        environment_report=args.environment_report,
        session_id=args.session_id,
        seed=args.seed,
        generated_frame_count=1,
        precision=args.precision,
        device=args.device,
        top_k=5,
        output_frame_rate=20.0,
        mineocclude_revision=args.mineocclude_revision,
        ffprobe=args.ffprobe,
    )
    prepared = phase3.preflight_certification_inputs(phase3_args)
    if "torch" in sys.modules:
        _raise(
            "preflight_runtime_imported",
            "CPU preflight imported torch unexpectedly",
        )
    if (
        args.expected_layer_count != EXPECTED_LAYER_COUNT
        or args.expected_hidden_size != EXPECTED_HIDDEN_SIZE
        or args.forward_count != EXPECTED_FORWARD_COUNT
    ):
        _raise(
            "probe_shape_mismatch",
            "probe requires 20 layers, hidden size 2048, and one forward",
        )
    expected_hashes = {
        "accepted trajectory package": (
            args.accepted_trajectory_package_sha256,
            prepared["accepted_manifest_sha256"],
        ),
        "input MP4": (
            args.input_mp4_sha256,
            prepared["input_mp4_sha256"],
        ),
        "environment report": (
            args.environment_report_sha256,
            prepared["environment_report_sha256"],
        ),
    }
    for role, (expected, observed) in expected_hashes.items():
        if _require_sha256(expected, role) != observed:
            _raise(
                "input_hash_mismatch",
                f"{role}: expected {expected.lower()}, observed {observed}",
            )
    frame_rows = prepared["package"]["streams"]["frame_map"]
    identities = [
        (
            prepared["package"]["trajectory_id"],
            row.get("model_frame_idx"),
        )
        for row in frame_rows
    ]
    if (
        len(identities) != prepared["context_pairs"]
        or len(identities) != len(set(identities))
        or any(
            not isinstance(identity[0], str)
            or not identity[0]
            or type(identity[1]) is not int
            or identity[1] < 0
            for identity in identities
        )
    ):
        _raise(
            "incomplete_context_identity",
            "accepted context lacks complete unique FrameTokenMap identities",
        )
    return {
        "schema_version": "1.0",
        "probe_version": PROBE_VERSION,
        "status": "preflight_passed",
        "session_id": args.session_id,
        "session_root": str(prepared["session_root"]),
        "torch_imported": False,
        "cuda_queried": False,
        "runtime_loaded": False,
        "session_directory_created": False,
        "overwrite_allowed": False,
        "forward_count_requested": EXPECTED_FORWARD_COUNT,
        "expected_layer_count": EXPECTED_LAYER_COUNT,
        "expected_hidden_size": EXPECTED_HIDDEN_SIZE,
        "mineocclude_revision": prepared["mineocclude_revision"],
        "source_revision": prepared["source_revision"],
        "asset_revision": prepared["asset_revision"],
        "precision": args.precision,
        "device": args.device,
        "context": {
            "frame_count": prepared["context_pairs"],
            "complete_frame_identities": [
                {
                    "trajectory_id": trajectory_id,
                    "model_frame_idx": model_frame_idx,
                }
                for trajectory_id, model_frame_idx in identities
            ],
            "position_budget": prepared["position_budget"],
            "max_position_embeddings": 5552,
        },
        "inputs": {
            "accepted_trajectory_package": {
                "path": str(prepared["package_path"]),
                "size_bytes": prepared["package_path"].stat().st_size,
                "sha256": prepared["accepted_manifest_sha256"],
            },
            "input_mp4": {
                "path": str(prepared["input_mp4"]),
                "size_bytes": prepared["input_mp4_size_bytes"],
                "sha256": prepared["input_mp4_sha256"],
            },
            "environment_report": {
                "path": str(prepared["environment_report"]),
                "size_bytes": prepared["environment_report_size_bytes"],
                "sha256": prepared["environment_report_sha256"],
            },
            "model_config": {
                "path": str(prepared["model_config"]),
                "size_bytes": prepared["model_config"].stat().st_size,
                "sha256": phase3.PINNED_MODEL_CONFIG_SHA256,
            },
            "main_checkpoint": {
                "path": str(prepared["main_checkpoint"]),
                "size_bytes": prepared["main_checkpoint"].stat().st_size,
                "sha256": phase3.PINNED_MAIN_CHECKPOINT_SHA256,
            },
            "vae_config": {
                "path": str(prepared["vae_config"]),
                "size_bytes": prepared["vae_config"].stat().st_size,
                "sha256": phase3.PINNED_VAE_CONFIG_SHA256,
            },
            "vae_checkpoint": {
                "path": str(prepared["vae_checkpoint"]),
                "size_bytes": prepared["vae_checkpoint"].stat().st_size,
                "sha256": phase3.PINNED_VAE_CHECKPOINT_SHA256,
            },
        },
        "_prepared": prepared,
    }


def _public_preflight(report: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if key != "_prepared"}


def _discovery_from_modules(modules: tuple[tuple[str, object], ...]) -> Any:
    from mineocclude.activations.hooks import (
        CONCEPTUAL_HOOK_SITE,
        HOOK_DISCOVERY_VERSION,
        FrozenHookDiscovery,
        HookLayerMetadata,
    )

    if len(modules) != EXPECTED_LAYER_COUNT:
        _raise(
            "hook_layer_count_mismatch",
            "teacher-forward boundary did not expose exactly 20 modules",
        )
    names = tuple(name for name, _module in modules)
    expected = tuple(
        f"transformer.model.layers.{index}"
        for index in range(EXPECTED_LAYER_COUNT)
    )
    if names != expected:
        _raise(
            "hook_layer_identity_mismatch",
            "teacher-forward modules do not match the frozen decoder path",
        )
    layers = tuple(
        HookLayerMetadata(
            layer_idx=index,
            module_name=name,
            module_type=f"{type(module).__module__}.{type(module).__qualname__}",
            conceptual_site=CONCEPTUAL_HOOK_SITE,
            discovery_version=HOOK_DISCOVERY_VERSION,
        )
        for index, (name, module) in enumerate(modules)
    )
    return FrozenHookDiscovery(
        layers=layers,
        module_name_pattern="transformer.model.layers.{layer_idx}",
        conceptual_site=CONCEPTUAL_HOOK_SITE,
        discovery_version=HOOK_DISCOVERY_VERSION,
        _modules=tuple(module for _name, module in modules),
    )


def _hook_count(module: object) -> int:
    hooks = getattr(module, "_forward_hooks", None)
    return len(hooks) if isinstance(hooks, Mapping) else 0


def _tensor_sha256(tensor: object) -> str:
    array = tensor.detach().cpu().contiguous().numpy()
    return hashlib.sha256(array.tobytes(order="C")).hexdigest()


def _position_sha256(positions: tuple[int, ...]) -> str:
    return hashlib.sha256(
        json.dumps(
            list(positions),
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _actual_changed_positions(
    torch: Any,
    original: object,
    modified: object,
) -> list[int]:
    if original.shape != modified.shape or original.ndim != 3:
        _raise(
            "action_mutation_shape_mismatch",
            "action proof tensors must retain identical rank-3 shapes",
        )
    equal_values = torch.eq(original, modified)
    equal_nan = torch.isnan(original) & torch.isnan(modified)
    changed_rows = (~(equal_values | equal_nan)).any(dim=2).any(dim=0)
    return [
        int(position)
        for position in torch.nonzero(
            changed_rows,
            as_tuple=False,
        )
        .flatten()
        .tolist()
    ]


def _memory(torch: Any) -> dict[str, int]:
    torch.cuda.synchronize(0)
    return {
        "allocated_bytes": int(torch.cuda.memory_allocated(0)),
        "reserved_bytes": int(torch.cuda.memory_reserved(0)),
    }


def _write_json(path: Path, document: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def run(args: argparse.Namespace) -> Path:
    """Execute the bounded real-runtime probe after side-effect-free preflight."""

    preflight_report = preflight(args)
    prepared = preflight_report["_prepared"]
    if not args.confirm_runtime_probe:
        _raise(
            "runtime_probe_not_confirmed",
            "--confirm-runtime-probe is required for run mode",
        )

    import importlib

    torch = importlib.import_module("torch")
    if not torch.cuda.is_available():
        _raise("cuda_required", "real CUDA is required for run mode")
    torch.cuda.init()
    torch.cuda.set_device(0)
    if torch.cuda.current_device() != 0:
        _raise("cuda_device_mismatch", "run mode requires cuda:0")

    from mineocclude.activations.hooks import ScopedHookManager
    from mineocclude.activations.pool import (
        mean_pool_visual_tokens,
        select_visual_token_positions,
    )
    from mineocclude.contracts.identity import SCHEMA_VERSION
    from mineocclude.models import phase3_certification as phase3
    from mineocclude.models._mineworld_adapter_wave2 import (
        PINNED_ASSET_REVISION,
        PINNED_MAIN_CHECKPOINT_SHA256,
        PINNED_MODEL_CONFIG_SHA256,
        PINNED_SOURCE_REVISION,
        PINNED_VAE_CHECKPOINT_SHA256,
        PINNED_VAE_CONFIG_SHA256,
    )
    from mineocclude.models._mineworld_adapter_wave4 import (
        _adapter_code_identity,
    )
    from mineocclude.models.mineworld_adapter import (
        AcceptedTrajectoryInput,
        ActionConversionRequest,
        FramePreprocessRequest,
        RuntimeLoadRequest,
        TeacherForcedRequest,
        TrajectoryTokenizationRequest,
        create_mineworld_adapter,
    )

    session_root = prepared["session_root"]
    session_root.mkdir(parents=True)
    raw_log = session_root / "raw_stdout_stderr.log"
    report_path = session_root / "pooling_probe_report.json"
    try:
        with raw_log.open(  # noqa: SIM117
            "w",
            encoding="utf-8",
            newline="\n",
        ) as log:
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                adapter = create_mineworld_adapter()
                package = prepared["package"]
                accepted_hash = prepared["accepted_manifest_sha256"]
                code_identity = _adapter_code_identity()
                validated = adapter.validate_trajectory(
                    AcceptedTrajectoryInput(
                        schema_version=SCHEMA_VERSION,
                        trajectory_id=package["trajectory_id"],
                        accepted_manifest_sha256=accepted_hash,
                        document=package,
                    )
                )
                runtime = adapter.load_runtime(
                    RuntimeLoadRequest(
                        schema_version=SCHEMA_VERSION,
                        runtime_id=f"{args.session_id}:runtime",
                        mineocclude_revision=prepared["mineocclude_revision"],
                        mineworld_source_revision=PINNED_SOURCE_REVISION,
                        modelscope_asset_revision=PINNED_ASSET_REVISION,
                        mineworld_source_root=prepared["source_root"],
                        model_config_path=prepared["model_config"],
                        main_checkpoint_path=prepared["main_checkpoint"],
                        vae_config_path=prepared["vae_config"],
                        vae_checkpoint_path=prepared["vae_checkpoint"],
                        model_config_sha256=PINNED_MODEL_CONFIG_SHA256,
                        main_checkpoint_sha256=PINNED_MAIN_CHECKPOINT_SHA256,
                        vae_config_sha256=PINNED_VAE_CONFIG_SHA256,
                        vae_checkpoint_sha256=PINNED_VAE_CHECKPOINT_SHA256,
                        environment_report_sha256=prepared[
                            "environment_report_sha256"
                        ],
                        precision=args.precision,
                        device=args.device,
                        expected_adapter_code_sha256=code_identity.sha256,
                    )
                )
                if (
                    runtime.layer_count != EXPECTED_LAYER_COUNT
                    or runtime.hidden_size != EXPECTED_HIDDEN_SIZE
                ):
                    _raise(
                        "runtime_shape_mismatch",
                        "loaded runtime does not match 20 layers x hidden 2048",
                    )
                frame_rows = sorted(
                    package["streams"]["frame_map"],
                    key=lambda row: row["model_frame_idx"],
                )
                decoded = phase3._decode_frames(
                    prepared["input_mp4"],
                    [row["render_frame_idx"] for row in frame_rows],
                )
                frames = tuple(
                    adapter.preprocess_frame(
                        FramePreprocessRequest(
                            identity=identity,
                            source_frame_idx=row["render_frame_idx"],
                            frame=frame,
                        )
                    )
                    for identity, row, frame in zip(
                        validated.frame_identities,
                        frame_rows,
                        decoded,
                        strict=True,
                    )
                )
                raw_by_index = {
                    row["model_frame_idx"]: row
                    for row in package["streams"]["raw_actions"]
                }
                actions = tuple(
                    adapter.convert_action(
                        ActionConversionRequest(
                            identity=identity,
                            action_idx=row["action_idx"],
                            raw_action=raw_by_index[
                                identity.model_frame_idx
                            ]["raw_action"],
                        )
                    )
                    for identity, row in zip(
                        validated.frame_identities,
                        frame_rows,
                        strict=True,
                    )
                )
                tokenized = adapter.tokenize_trajectory(
                    TrajectoryTokenizationRequest(
                        runtime_identity=runtime,
                        trajectory=validated,
                        frames=frames,
                        actions=actions,
                    )
                )

                holder: dict[str, Any] = {}
                before_hook_count: list[int] = []
                during_hook_count: list[int] = []

                def hook_factory(modules: tuple[tuple[str, object], ...]):
                    discovery = _discovery_from_modules(modules)
                    before_hook_count.extend(
                        _hook_count(module)
                        for _name, module in modules
                    )
                    if (
                        len(before_hook_count) != EXPECTED_LAYER_COUNT
                        or any(before_hook_count)
                    ):
                        _raise(
                            "preexisting_decoder_hooks",
                            "runtime probe requires 20 decoder modules with "
                            "zero pre-existing forward hooks",
                        )
                    manager = ScopedHookManager(
                        discovery,
                        capture_callback=lambda _capture: (
                            during_hook_count.append(
                                sum(
                                    _hook_count(module)
                                    for _name, module in modules
                                )
                            )
                            if not during_hook_count
                            else None
                        ),
                    )
                    holder["manager"] = manager
                    holder["modules"] = modules
                    return manager

                torch.cuda.reset_peak_memory_stats(0)
                forward_started = time.perf_counter()
                teacher_result = adapter.teacher_forced(
                    TeacherForcedRequest(
                        runtime_identity=runtime,
                        trajectory=tokenized,
                        seed=args.seed,
                        precision=args.precision,
                        batch_size=1,
                        hook_context_factory=hook_factory,
                        expected_adapter_code_sha256=code_identity.sha256,
                        accepted_manifest_sha256=accepted_hash,
                    )
                )
                forward_seconds = time.perf_counter() - forward_started
                manager = holder["manager"]
                captures = manager.require_complete()
                modules = holder["modules"]
                after_hook_count = [
                    _hook_count(module) for _name, module in modules
                ]
                if (
                    len(after_hook_count) != EXPECTED_LAYER_COUNT
                    or not manager.closed
                    or any(after_hook_count)
                ):
                    _raise(
                        "hook_cleanup_failed",
                        "all temporary hook handles must be removed",
                    )
                baseline = _memory(torch)
                candidates: list[dict[str, Any]] = []
                per_frame_memory: list[dict[str, Any]] = []
                for span in tokenized.frame_token_map.spans:
                    selection = select_visual_token_positions(
                        tokenized.frame_token_map,
                        trajectory_id=span.identity.trajectory_id,
                        model_frame_idx=span.identity.model_frame_idx,
                        hooked_sequence_length=(
                            tokenized.frame_token_map.sequence_length
                        ),
                    )
                    for layer_idx in range(EXPECTED_LAYER_COUNT):
                        source = captures[layer_idx].output.tensor
                        candidate = mean_pool_visual_tokens(
                            activation=source,
                            selection=selection,
                            layer_idx=layer_idx,
                            hook_site=HOOK_SITE,
                        )
                        index = torch.tensor(
                            selection.positions,
                            dtype=torch.long,
                            device=source.device,
                        )
                        direct = (
                            source.detach()
                            .index_select(1, index)[0]
                            .to(torch.float32)
                            .mean(dim=0)
                            .cpu()
                            .contiguous()
                        )
                        equal = bool(torch.equal(candidate.vector, direct))
                        difference = float(
                            (candidate.vector - direct).abs().max().item()
                        )
                        if not equal or difference != 0.0:
                            _raise(
                                "direct_mean_mismatch",
                                "candidate differs from independent explicit mean",
                            )
                        candidates.append(
                            {
                                "trajectory_id": candidate.trajectory_id,
                                "model_frame_idx": candidate.model_frame_idx,
                                "layer_idx": candidate.layer_idx,
                                "hook_site": candidate.hook_site,
                                "source_shape": list(source.shape),
                                "returned_shape": list(candidate.vector.shape),
                                "source_dtype": candidate.source_dtype,
                                "source_device": candidate.source_device,
                                "returned_dtype": candidate.returned_dtype,
                                "returned_device": candidate.returned_device,
                                "visual_token_count": 336,
                                "direct_mean_equal": equal,
                                "max_abs_difference": difference,
                                "candidate_sha256": _tensor_sha256(
                                    candidate.vector
                                ),
                                "detached": (
                                    not candidate.vector.requires_grad
                                    and candidate.vector.grad_fn is None
                                ),
                                "contiguous": candidate.vector.is_contiguous(),
                            }
                        )
                        del direct, index, candidate
                    frame_memory = _memory(torch)
                    per_frame_memory.append(
                        {
                            "trajectory_id": span.identity.trajectory_id,
                            "model_frame_idx": span.identity.model_frame_idx,
                            **frame_memory,
                            "allocated_delta_from_baseline_bytes": (
                                frame_memory["allocated_bytes"]
                                - baseline["allocated_bytes"]
                            ),
                        }
                    )

                representative = tokenized.frame_token_map.spans[0]
                original_selection = select_visual_token_positions(
                    tokenized.frame_token_map,
                    trajectory_id=representative.identity.trajectory_id,
                    model_frame_idx=representative.identity.model_frame_idx,
                    hooked_sequence_length=(
                        tokenized.frame_token_map.sequence_length
                    ),
                )
                expected_action_positions = list(
                    representative.action_positions
                )
                visual_positions_before_sha256 = _position_sha256(
                    original_selection.positions
                )
                action_records: list[dict[str, Any]] = []
                for layer_idx in range(EXPECTED_LAYER_COUNT):
                    source = captures[layer_idx].output.tensor
                    original = mean_pool_visual_tokens(
                        activation=source,
                        selection=original_selection,
                        layer_idx=layer_idx,
                        hook_site=HOOK_SITE,
                    )

                    finite_selection = select_visual_token_positions(
                        tokenized.frame_token_map,
                        trajectory_id=representative.identity.trajectory_id,
                        model_frame_idx=(
                            representative.identity.model_frame_idx
                        ),
                        hooked_sequence_length=(
                            tokenized.frame_token_map.sequence_length
                        ),
                    )
                    finite_clone = source.detach().clone()
                    for action_index, position in enumerate(
                        expected_action_positions
                    ):
                        sentinel = (
                            60_000.0
                            if action_index % 2 == 0
                            else -60_000.0
                        )
                        if bool(
                            torch.eq(
                                source[0, position, :],
                                sentinel,
                            )
                            .all()
                            .item()
                        ):
                            sentinel = -sentinel
                        finite_clone[0, position, :] = sentinel
                    finite_actual_modified_positions = (
                        _actual_changed_positions(
                            torch,
                            source,
                            finite_clone,
                        )
                    )
                    finite_visual_positions_sha256 = _position_sha256(
                        finite_selection.positions
                    )
                    finite_visual_positions_unchanged = (
                        finite_selection.positions
                        == original_selection.positions
                    )
                    if (
                        finite_actual_modified_positions
                        != expected_action_positions
                        or not finite_visual_positions_unchanged
                    ):
                        _raise(
                            "action_mutation_scope_mismatch",
                            "finite mutation did not change exactly the "
                            "declared 11 action rows",
                        )
                    finite_result = mean_pool_visual_tokens(
                        activation=finite_clone,
                        selection=finite_selection,
                        layer_idx=layer_idx,
                        hook_site=HOOK_SITE,
                    )
                    finite_equal = bool(
                        torch.equal(original.vector, finite_result.vector)
                    )
                    finite_evidence = {
                        "finite_actual_modified_positions": (
                            finite_actual_modified_positions
                        ),
                        "visual_positions_after_finite_sha256": (
                            finite_visual_positions_sha256
                        ),
                        "finite_visual_positions_unchanged": (
                            finite_visual_positions_unchanged
                        ),
                        "finite_action_equal": finite_equal,
                    }
                    del (
                        finite_actual_modified_positions,
                        finite_clone,
                        finite_result,
                        finite_selection,
                    )

                    nonfinite_selection = select_visual_token_positions(
                        tokenized.frame_token_map,
                        trajectory_id=representative.identity.trajectory_id,
                        model_frame_idx=(
                            representative.identity.model_frame_idx
                        ),
                        hooked_sequence_length=(
                            tokenized.frame_token_map.sequence_length
                        ),
                    )
                    nonfinite_clone = source.detach().clone()
                    nonfinite_values = (torch.nan, torch.inf, -torch.inf)
                    for action_index, position in enumerate(
                        expected_action_positions
                    ):
                        value_index = action_index % len(nonfinite_values)
                        nonfinite_value = nonfinite_values[value_index]
                        original_row = source[0, position, :]
                        if bool(
                            (
                                torch.isnan(original_row)
                                if math.isnan(nonfinite_value)
                                else torch.eq(
                                    original_row,
                                    nonfinite_value,
                                )
                            )
                            .all()
                            .item()
                        ):
                            nonfinite_value = nonfinite_values[
                                (value_index + 1) % len(nonfinite_values)
                            ]
                        nonfinite_clone[0, position, :] = (
                            nonfinite_value
                        )
                    nonfinite_actual_modified_positions = (
                        _actual_changed_positions(
                            torch,
                            source,
                            nonfinite_clone,
                        )
                    )
                    nonfinite_visual_positions_sha256 = _position_sha256(
                        nonfinite_selection.positions
                    )
                    nonfinite_visual_positions_unchanged = (
                        nonfinite_selection.positions
                        == original_selection.positions
                    )
                    if (
                        nonfinite_actual_modified_positions
                        != expected_action_positions
                        or not nonfinite_visual_positions_unchanged
                    ):
                        _raise(
                            "action_mutation_scope_mismatch",
                            "nonfinite mutation did not change exactly the "
                            "declared 11 action rows",
                        )
                    nonfinite_result = mean_pool_visual_tokens(
                        activation=nonfinite_clone,
                        selection=nonfinite_selection,
                        layer_idx=layer_idx,
                        hook_site=HOOK_SITE,
                    )
                    nonfinite_equal = bool(
                        torch.equal(original.vector, nonfinite_result.vector)
                    )
                    if not finite_equal or not nonfinite_equal:
                        _raise(
                            "action_exclusion_failed",
                            "action-only mutations changed visual pooling",
                        )
                    action_records.append(
                        {
                            "layer_idx": layer_idx,
                            "hook_site": HOOK_SITE,
                            "expected_action_positions": (
                                expected_action_positions
                            ),
                            "visual_positions_before_sha256": (
                                visual_positions_before_sha256
                            ),
                            **finite_evidence,
                            "nonfinite_actual_modified_positions": (
                                nonfinite_actual_modified_positions
                            ),
                            "visual_positions_after_nonfinite_sha256": (
                                nonfinite_visual_positions_sha256
                            ),
                            "nonfinite_visual_positions_unchanged": (
                                nonfinite_visual_positions_unchanged
                            ),
                            "nonfinite_action_equal": nonfinite_equal,
                        }
                    )
                    del (
                        nonfinite_clone,
                        nonfinite_result,
                        nonfinite_actual_modified_positions,
                        nonfinite_selection,
                        original,
                    )
                final_memory = _memory(torch)
                measurements = [
                    entry["allocated_bytes"] for entry in per_frame_memory
                ]
                monotonic_growth = len(measurements) > 1 and all(
                    right > left
                    for left, right in pairwise(measurements)
                )
                maximum_after_frame_allocated_bytes = max(measurements)
                maximum_after_frame_allocated_delta_bytes = max(
                    measurement - baseline["allocated_bytes"]
                    for measurement in measurements
                )
                all_after_frame_allocations_within_tolerance = all(
                    measurement
                    <= baseline["allocated_bytes"]
                    + MEMORY_TOLERANCE_BYTES
                    for measurement in measurements
                )
                final_allocation_delta_bytes = (
                    final_memory["allocated_bytes"]
                    - baseline["allocated_bytes"]
                )
                final_allocation_within_tolerance = (
                    final_memory["allocated_bytes"]
                    <= baseline["allocated_bytes"]
                    + MEMORY_TOLERANCE_BYTES
                )
                memory_pass = (
                    all_after_frame_allocations_within_tolerance
                    and final_allocation_within_tolerance
                )
                if not memory_pass:
                    _raise(
                        "pooling_memory_failed",
                        "bounded pooling retained CUDA allocation",
                    )
                candidate_count = len(candidates)
                expected_count = (
                    len(tokenized.frame_token_map.spans)
                    * EXPECTED_LAYER_COUNT
                )
                if candidate_count != expected_count:
                    _raise(
                        "candidate_count_mismatch",
                        "pooling did not cover every frame/layer identity",
                    )
                report = {
                    "schema_version": SCHEMA_VERSION,
                    "probe_version": PROBE_VERSION,
                    "status": "PASS",
                    "session_id": args.session_id,
                    "identities": {
                        "mineocclude_revision": prepared[
                            "mineocclude_revision"
                        ],
                        "source_revision": prepared["source_revision"],
                        "asset_revision": prepared["asset_revision"],
                        "environment_report_sha256": prepared[
                            "environment_report_sha256"
                        ],
                        "accepted_trajectory_package_sha256": accepted_hash,
                        "input_mp4_sha256": prepared["input_mp4_sha256"],
                        "runtime_id": runtime.runtime_id,
                        "runtime_identity": dataclasses.asdict(runtime),
                        "frame_token_map_sha256": (
                            tokenized.frame_token_map_sha256
                        ),
                        "adapter_code_sha256": runtime.adapter_code_sha256,
                        "tokenization_profile": (
                            tokenized.tokenization_profile
                        ),
                        "preprocessing_profile": (
                            tokenized.preprocessing_profile
                        ),
                        "action_conversion_profile": (
                            tokenized.action_conversion_profile
                        ),
                    },
                    "layer_count": EXPECTED_LAYER_COUNT,
                    "hidden_size": EXPECTED_HIDDEN_SIZE,
                    "frame_count": len(tokenized.frame_token_map.spans),
                    "candidate_count": candidate_count,
                    "expected_candidate_count": expected_count,
                    "forward_count": 1,
                    "teacher_output_sha256": teacher_result.output_sha256,
                    "forward_seconds": forward_seconds,
                    "candidates": candidates,
                    "action_exclusion": {
                        "representative_identity": dataclasses.asdict(
                            representative.identity
                        ),
                        "layer_records": action_records,
                        "status": "PASS",
                    },
                    "memory": {
                        "post_forward_baseline": baseline,
                        "after_each_frame": per_frame_memory,
                        "final": final_memory,
                        "peak_allocated_bytes": int(
                            torch.cuda.max_memory_allocated(0)
                        ),
                        "peak_reserved_bytes": int(
                            torch.cuda.max_memory_reserved(0)
                        ),
                        "allocated_tolerance_bytes": (
                            MEMORY_TOLERANCE_BYTES
                        ),
                        "maximum_after_frame_allocated_bytes": (
                            maximum_after_frame_allocated_bytes
                        ),
                        "maximum_after_frame_allocated_delta_bytes": (
                            maximum_after_frame_allocated_delta_bytes
                        ),
                        "all_after_frame_allocations_within_tolerance": (
                            all_after_frame_allocations_within_tolerance
                        ),
                        "final_allocation_delta_bytes": (
                            final_allocation_delta_bytes
                        ),
                        "final_allocation_within_tolerance": (
                            final_allocation_within_tolerance
                        ),
                        "monotonic_accumulation_detected": monotonic_growth,
                        "status": "PASS",
                    },
                    "hooks": {
                        "before_counts": before_hook_count,
                        "during_total": (
                            during_hook_count[0]
                            if during_hook_count
                            else None
                        ),
                        "after_counts": after_hook_count,
                        "capture_count": len(captures),
                        "cleanup_passed": manager.closed,
                    },
                    "files": {
                        key: {
                            "path": value["path"],
                            "size_bytes": value["size_bytes"],
                            "sha256": value["sha256"],
                        }
                        for key, value in _public_preflight(
                            preflight_report
                        )["inputs"].items()
                        if isinstance(value, Mapping)
                        and "sha256" in value
                    },
                    "unpooled_activation_artifacts_saved": False,
                    "command": list(sys.argv),
                }
        report["files"]["raw_log"] = {
            "path": str(raw_log),
            "size_bytes": raw_log.stat().st_size,
            "sha256": _sha256_file(raw_log),
        }
        _write_json(report_path, report)
        validate(report_path, verify_files=True)
        return report_path
    except Exception as exc:
        failure_path = session_root / "pooling_probe_failure.json"
        if not failure_path.exists():
            _write_json(
                failure_path,
                {
                    "schema_version": "1.0",
                    "probe_version": PROBE_VERSION,
                    "status": "FAIL",
                    "session_id": args.session_id,
                    "mineocclude_revision": prepared[
                        "mineocclude_revision"
                    ],
                    "source_revision": prepared["source_revision"],
                    "asset_revision": prepared["asset_revision"],
                    "exception_type": type(exc).__name__,
                    "message": str(exc),
                    "forward_count_requested": EXPECTED_FORWARD_COUNT,
                    "unpooled_activation_artifacts_saved": False,
                },
            )
        # The new session remains immutable failure evidence.
        raise


def _strict_json(path: Path) -> dict[str, Any]:
    def reject(value: str) -> None:
        raise ValueError(f"non-finite constant {value}")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key {key}")
            result[key] = value
        return result

    document = json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=reject,
        object_pairs_hook=unique,
    )
    if not isinstance(document, dict):
        _raise("invalid_report", "probe report must be a JSON object")
    return document


def validate(path: Path, *, verify_files: bool) -> None:
    """Validate a completed probe independently of model execution."""

    report_path = path.resolve()
    if not report_path.is_file():
        _raise("missing_report", f"probe report does not exist: {report_path}")
    report = _strict_json(report_path)
    frame_count = report.get("frame_count")
    expected_count = (
        frame_count * EXPECTED_LAYER_COUNT
        if type(frame_count) is int
        else -1
    )
    candidates = report.get("candidates")
    identities = report.get("identities")
    runtime_identity = (
        identities.get("runtime_identity")
        if isinstance(identities, Mapping)
        else None
    )
    if (
        report.get("schema_version") != "1.0"
        or report.get("probe_version") != PROBE_VERSION
        or report.get("status") != "PASS"
        or report.get("layer_count") != EXPECTED_LAYER_COUNT
        or report.get("hidden_size") != EXPECTED_HIDDEN_SIZE
        or type(frame_count) is not int
        or frame_count <= 0
        or report.get("candidate_count") != expected_count
        or report.get("expected_candidate_count") != expected_count
        or report.get("forward_count") != EXPECTED_FORWARD_COUNT
        or not isinstance(candidates, list)
        or len(candidates) != expected_count
        or report.get("unpooled_activation_artifacts_saved") is not False
        or not isinstance(identities, Mapping)
        or not isinstance(runtime_identity, Mapping)
        or runtime_identity.get("mineworld_source_revision")
        != identities.get("source_revision")
        or runtime_identity.get("modelscope_asset_revision")
        != identities.get("asset_revision")
        or runtime_identity.get("mineocclude_revision")
        != identities.get("mineocclude_revision")
        or runtime_identity.get("environment_report_sha256")
        != identities.get("environment_report_sha256")
        or runtime_identity.get("layer_count") != EXPECTED_LAYER_COUNT
        or runtime_identity.get("hidden_size") != EXPECTED_HIDDEN_SIZE
        or runtime_identity.get("precision") != "float16"
        or runtime_identity.get("device") != "cuda:0"
        or runtime_identity.get("adapter_code_sha256")
        != identities.get("adapter_code_sha256")
        or not all(
            isinstance(identities.get(field), str)
            and identities.get(field)
            for field in (
                "frame_token_map_sha256",
                "tokenization_profile",
                "preprocessing_profile",
                "action_conversion_profile",
            )
        )
    ):
        _raise(
            "invalid_report",
            "probe identity, counts, status, or forward bound is invalid",
        )
    coverage: set[tuple[str, int, int, str]] = set()
    frame_identities: set[tuple[str, int]] = set()
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            _raise("invalid_candidate", "candidate must be one mapping")
        identity = (
            candidate.get("trajectory_id"),
            candidate.get("model_frame_idx"),
            candidate.get("layer_idx"),
            candidate.get("hook_site"),
        )
        frame_identities.add((identity[0], identity[1]))
        coverage.add(identity)
        source_shape = candidate.get("source_shape")
        if (
            not isinstance(identity[0], str)
            or not identity[0]
            or type(identity[1]) is not int
            or type(identity[2]) is not int
            or not 0 <= identity[2] < EXPECTED_LAYER_COUNT
            or identity[3] != HOOK_SITE
            or not isinstance(source_shape, list)
            or len(source_shape) != 3
            or source_shape[0] != 1
            or source_shape[2] != EXPECTED_HIDDEN_SIZE
            or candidate.get("returned_shape") != [EXPECTED_HIDDEN_SIZE]
            or candidate.get("source_dtype") != "torch.float16"
            or candidate.get("source_device") != "cuda:0"
            or candidate.get("returned_dtype") != "torch.float32"
            or candidate.get("returned_device") != "cpu"
            or candidate.get("visual_token_count") != EXPECTED_VISUAL_TOKENS
            or candidate.get("direct_mean_equal") is not True
            or candidate.get("max_abs_difference") != 0.0
            or candidate.get("detached") is not True
            or candidate.get("contiguous") is not True
            or _SHA256.fullmatch(
                str(candidate.get("candidate_sha256"))
            )
            is None
        ):
            _raise(
                "invalid_candidate",
                f"candidate identity or pooling proof is invalid: {identity}",
            )
    expected_coverage = {
        (trajectory_id, model_frame_idx, layer_idx, HOOK_SITE)
        for trajectory_id, model_frame_idx in frame_identities
        for layer_idx in range(EXPECTED_LAYER_COUNT)
    }
    if len(frame_identities) != frame_count or coverage != expected_coverage:
        _raise(
            "candidate_coverage_mismatch",
            "candidate identities do not cover every frame/layer exactly",
        )
    action = report.get("action_exclusion")
    records = action.get("layer_records") if isinstance(action, Mapping) else None
    if (
        not isinstance(action, Mapping)
        or action.get("status") != "PASS"
        or not isinstance(records, list)
        or len(records) != EXPECTED_LAYER_COUNT
    ):
        _raise(
            "action_exclusion_invalid",
            "20-layer action-only mutation evidence is incomplete",
        )
    for expected_layer_idx, record in enumerate(records):
        if not isinstance(record, Mapping):
            _raise(
                "action_exclusion_invalid",
                "each action-exclusion layer record must be a mapping",
            )
        expected_positions = record.get("expected_action_positions")
        finite_positions = record.get(
            "finite_actual_modified_positions"
        )
        nonfinite_positions = record.get(
            "nonfinite_actual_modified_positions"
        )
        position_hashes = (
            record.get("visual_positions_before_sha256"),
            record.get("visual_positions_after_finite_sha256"),
            record.get("visual_positions_after_nonfinite_sha256"),
        )
        if (
            record.get("layer_idx") != expected_layer_idx
            or record.get("hook_site") != HOOK_SITE
            or not isinstance(expected_positions, list)
            or len(expected_positions) != EXPECTED_ACTION_TOKENS
            or any(type(position) is not int for position in expected_positions)
            or expected_positions != sorted(set(expected_positions))
            or finite_positions != expected_positions
            or nonfinite_positions != expected_positions
            or any(
                not isinstance(digest, str)
                or _SHA256.fullmatch(digest) is None
                for digest in position_hashes
            )
            or len(set(position_hashes)) != 1
            or record.get("finite_visual_positions_unchanged") is not True
            or record.get("nonfinite_visual_positions_unchanged") is not True
            or record.get("finite_action_equal") is not True
            or record.get("nonfinite_action_equal") is not True
        ):
            _raise(
                "action_exclusion_invalid",
                "derived action-row or visual-selection evidence is invalid",
            )
    memory = report.get("memory")
    baseline = (
        memory.get("post_forward_baseline")
        if isinstance(memory, Mapping)
        else None
    )
    final = memory.get("final") if isinstance(memory, Mapping) else None
    per_frame = (
        memory.get("after_each_frame")
        if isinstance(memory, Mapping)
        else None
    )
    if (
        not isinstance(memory, Mapping)
        or memory.get("allocated_tolerance_bytes")
        != MEMORY_TOLERANCE_BYTES
        or not isinstance(baseline, Mapping)
        or not isinstance(final, Mapping)
        or not isinstance(per_frame, list)
        or len(per_frame) != frame_count
    ):
        _raise("memory_evidence_invalid", "bounded memory pass rule failed")
    memory_records = [baseline, *per_frame, final]
    if any(
        type(record.get(field)) is not int or record[field] < 0
        for record in memory_records
        for field in ("allocated_bytes", "reserved_bytes")
    ):
        _raise(
            "memory_evidence_invalid",
            "allocated/reserved memory values must be non-negative integers",
        )
    baseline_allocated = baseline["allocated_bytes"]
    allocations = [record["allocated_bytes"] for record in per_frame]
    allocation_deltas = [
        allocation - baseline_allocated for allocation in allocations
    ]
    if any(
        type(record.get("allocated_delta_from_baseline_bytes")) is not int
        or record["allocated_delta_from_baseline_bytes"] != delta
        for record, delta in zip(
            per_frame,
            allocation_deltas,
            strict=True,
        )
    ):
        _raise(
            "memory_evidence_invalid",
            "per-frame allocated-memory deltas are inconsistent",
        )
    maximum_after_frame_allocated = max(allocations)
    maximum_after_frame_delta = max(allocation_deltas)
    all_after_within_tolerance = all(
        allocation <= baseline_allocated + MEMORY_TOLERANCE_BYTES
        for allocation in allocations
    )
    final_delta = final["allocated_bytes"] - baseline_allocated
    final_within_tolerance = (
        final["allocated_bytes"]
        <= baseline_allocated + MEMORY_TOLERANCE_BYTES
    )
    monotonic_growth = len(allocations) > 1 and all(
        right > left for left, right in pairwise(allocations)
    )
    peak_allocated = memory.get("peak_allocated_bytes")
    peak_reserved = memory.get("peak_reserved_bytes")
    if (
        type(peak_allocated) is not int
        or peak_allocated < max(
            baseline_allocated,
            *allocations,
            final["allocated_bytes"],
        )
        or type(peak_reserved) is not int
        or peak_reserved
        < max(
            baseline["reserved_bytes"],
            *(record["reserved_bytes"] for record in per_frame),
            final["reserved_bytes"],
        )
        or memory.get("maximum_after_frame_allocated_bytes")
        != maximum_after_frame_allocated
        or memory.get("maximum_after_frame_allocated_delta_bytes")
        != maximum_after_frame_delta
        or memory.get("all_after_frame_allocations_within_tolerance")
        is not all_after_within_tolerance
        or memory.get("final_allocation_delta_bytes") != final_delta
        or memory.get("final_allocation_within_tolerance")
        is not final_within_tolerance
        or memory.get("monotonic_accumulation_detected")
        is not monotonic_growth
        or memory.get("status")
        != (
            "PASS"
            if all_after_within_tolerance and final_within_tolerance
            else "FAIL"
        )
        or not all_after_within_tolerance
        or not final_within_tolerance
    ):
        _raise(
            "memory_evidence_invalid",
            "reported bounded-memory facts do not match measurements",
        )
    hooks = report.get("hooks")
    if (
        not isinstance(hooks, Mapping)
        or hooks.get("capture_count") != EXPECTED_LAYER_COUNT
        or hooks.get("cleanup_passed") is not True
        or hooks.get("during_total") != EXPECTED_LAYER_COUNT
        or hooks.get("before_counts") != [0] * EXPECTED_LAYER_COUNT
        or hooks.get("after_counts") != [0] * EXPECTED_LAYER_COUNT
    ):
        _raise("hook_evidence_invalid", "hook coverage or cleanup failed")
    if verify_files:
        files = report.get("files")
        if not isinstance(files, Mapping) or not files:
            _raise("file_evidence_invalid", "referenced files are absent")
        for role, record in files.items():
            if not isinstance(record, Mapping):
                _raise("file_evidence_invalid", f"{role} is malformed")
            referenced = Path(str(record.get("path"))).resolve()
            if (
                not referenced.is_file()
                or referenced.stat().st_size != record.get("size_bytes")
                or _sha256_file(referenced) != record.get("sha256")
            ):
                _raise(
                    "file_evidence_invalid",
                    f"{role} size/hash verification failed",
                )
    prohibited = {".pt", ".pth", ".npy", ".npz", ".ckpt", ".safetensors"}
    if any(
        child.suffix.lower() in prohibited
        for child in report_path.parent.rglob("*")
        if child.is_file()
    ):
        _raise(
            "unpooled_artifact_found",
            "session contains a prohibited tensor/checkpoint artifact",
        )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "preflight":
            print(json.dumps(_public_preflight(preflight(args)), indent=2))
        elif args.command == "run":
            print(run(args))
        else:
            validate(args.report, verify_files=args.verify_files)
            print(f"validated: {args.report.resolve()}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
