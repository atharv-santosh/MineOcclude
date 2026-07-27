"""Preflight, run, or validate the bounded Phase 4 Wave 3 extraction probe.

Preflight imports no PyTorch module, queries no CUDA state, decodes no video,
loads no runtime, and creates no session directory. Run mode is prepared for
the qualified AWS runtime and must never be used as a local synthetic proof.
"""

from __future__ import annotations

import argparse
import contextlib
import gc
import hashlib
import json
import math
import re
import sys
import time
import traceback
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PROBE_VERSION = "person-a-phase4-wave3-extraction-probe-v1.0"
EXPECTED_LAYER_COUNT = 20
EXPECTED_HIDDEN_SIZE = 2048
EXPECTED_VISUAL_TOKENS = 336
EXPECTED_ACTION_TOKENS = 11
EXPECTED_CONTEXT_FRAMES = 8
EXPECTED_RUNTIME_LOAD_COUNT = 1
EXPECTED_FORWARD_ATTEMPT_COUNT = 3
EXPECTED_SUCCESSFUL_EXTRACTION_COUNT = 2
EXPECTED_FORCED_FAILURE_COUNT = 1
EXPECTED_UNPOOLED_FRAME_COUNT = 1
EXPECTED_CANDIDATE_COUNT = (
    EXPECTED_CONTEXT_FRAMES * EXPECTED_LAYER_COUNT
)
FORCED_FAILURE_LAYER = 10
MEMORY_TOLERANCE_BYTES = 1_048_576
CANDIDATE_COMPARISON_RTOL = 1e-3
CANDIDATE_COMPARISON_ATOL = 1e-3
HOOK_SITE = "decoder_layer_output_residual_stream"
REPORT_FILENAME = "extraction_probe_report.json"
RAW_LOG_FILENAME = "raw_stdout_stderr.log"
FAILURE_FILENAME = "failed_probe.json"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_FORBIDDEN_TENSOR_SUFFIXES = {
    ".ckpt",
    ".npy",
    ".npz",
    ".pt",
    ".pth",
    ".safetensors",
}


class ForcedExtractionProbeFailure(RuntimeError):
    """One deliberate probe-only callback failure at a fixed layer."""


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
        "--expected-visual-token-count",
        type=int,
        default=EXPECTED_VISUAL_TOKENS,
    )
    command.add_argument(
        "--expected-action-token-count",
        type=int,
        default=EXPECTED_ACTION_TOKENS,
    )
    command.add_argument(
        "--runtime-load-count",
        type=int,
        default=EXPECTED_RUNTIME_LOAD_COUNT,
    )
    command.add_argument(
        "--forward-attempt-count",
        type=int,
        default=EXPECTED_FORWARD_ATTEMPT_COUNT,
    )
    command.add_argument(
        "--successful-extraction-count",
        type=int,
        default=EXPECTED_SUCCESSFUL_EXTRACTION_COUNT,
    )
    command.add_argument(
        "--forced-failure-count",
        type=int,
        default=EXPECTED_FORCED_FAILURE_COUNT,
    )
    command.add_argument(
        "--unpooled-pilot-frame-count",
        type=int,
        default=EXPECTED_UNPOOLED_FRAME_COUNT,
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the exact preflight/run/validate command surface."""

    parser = argparse.ArgumentParser(
        description=(
            "Prepare, run, or validate one immutable Person A Phase 4 "
            "Wave 3 extraction-safety and limited-unpooled probe."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)
    preflight_parser = commands.add_parser(
        "preflight",
        help="CPU-only input validation without PyTorch or side effects",
    )
    _common_arguments(preflight_parser)
    run_parser = commands.add_parser(
        "run",
        help="execute the explicitly confirmed qualified CUDA probe",
    )
    _common_arguments(run_parser)
    run_parser.add_argument("--confirm-runtime-probe", action="store_true")
    validate_parser = commands.add_parser(
        "validate",
        help="independently validate completed bounded evidence",
    )
    validate_parser.add_argument("--report", required=True, type=Path)
    return parser


def _raise(code: str, message: str) -> None:
    from mineocclude.models.phase2_evidence import EvidenceValidationError

    raise EvidenceValidationError(code, message)


def _require_sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        _raise("invalid_sha256", f"{field} must be one lowercase SHA-256")
    return value


def _require_git_sha(value: object, field: str) -> str:
    if not isinstance(value, str) or _GIT_SHA.fullmatch(value) is None:
        _raise("invalid_revision", f"{field} must be one full lowercase Git SHA")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _strict_json(path: Path) -> Mapping[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _raise("duplicate_json_key", f"{path}: duplicate key {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        _raise("nonfinite_json", f"{path}: invalid constant {value!r}")

    try:
        document = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except Exception as exc:
        if type(exc).__name__ == "EvidenceValidationError":
            raise
        _raise("invalid_json", f"{path}: {type(exc).__name__}: {exc}")
    if not isinstance(document, dict):
        _raise("invalid_json", f"{path}: root must be an object")
    return document


def _requested_shape_is_exact(args: argparse.Namespace) -> bool:
    return (
        args.expected_layer_count == EXPECTED_LAYER_COUNT
        and args.expected_hidden_size == EXPECTED_HIDDEN_SIZE
        and args.expected_visual_token_count == EXPECTED_VISUAL_TOKENS
        and args.expected_action_token_count == EXPECTED_ACTION_TOKENS
        and args.runtime_load_count == EXPECTED_RUNTIME_LOAD_COUNT
        and args.forward_attempt_count == EXPECTED_FORWARD_ATTEMPT_COUNT
        and args.successful_extraction_count
        == EXPECTED_SUCCESSFUL_EXTRACTION_COUNT
        and args.forced_failure_count == EXPECTED_FORCED_FAILURE_COUNT
        and args.unpooled_pilot_frame_count
        == EXPECTED_UNPOOLED_FRAME_COUNT
    )


def preflight(args: argparse.Namespace) -> dict[str, Any]:
    """Run shared CPU input validation plus exact Wave 3 assertions."""

    if "torch" in sys.modules:
        _raise(
            "preflight_runtime_imported",
            "preflight must begin before torch is imported",
        )
    from mineocclude.models import phase3_certification as phase3

    if not _requested_shape_is_exact(args):
        _raise(
            "probe_shape_mismatch",
            "probe requires 20 layers, hidden 2048, 336 visual and 11 action "
            "tokens, one load, three attempts, two successes, one forced "
            "failure, and one unpooled frame",
        )
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
        args.precision != "float16"
        or args.device != "cuda:0"
        or prepared.get("context_pairs") != EXPECTED_CONTEXT_FRAMES
    ):
        _raise(
            "probe_runtime_identity_mismatch",
            "probe requires an eight-pair context at float16 on cuda:0",
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
                f"{role}: expected {expected}, observed {observed}",
            )
    _require_git_sha(
        prepared.get("mineocclude_revision"),
        "mineocclude_revision",
    )
    frame_rows = prepared["package"]["streams"]["frame_map"]
    identities = tuple(
        (
            prepared["package"]["trajectory_id"],
            row.get("model_frame_idx"),
        )
        for row in frame_rows
    )
    if (
        len(identities) != EXPECTED_CONTEXT_FRAMES
        or len(identities) != len(set(identities))
        or any(
            not isinstance(trajectory_id, str)
            or not trajectory_id
            or type(model_frame_idx) is not int
            or model_frame_idx < 0
            for trajectory_id, model_frame_idx in identities
        )
    ):
        _raise(
            "incomplete_context_identity",
            "accepted context must expose eight unique scientific identities",
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
        "runtime_load_count_requested": EXPECTED_RUNTIME_LOAD_COUNT,
        "forward_attempt_count_requested": EXPECTED_FORWARD_ATTEMPT_COUNT,
        "successful_extraction_count_requested": (
            EXPECTED_SUCCESSFUL_EXTRACTION_COUNT
        ),
        "forced_failure_count_requested": EXPECTED_FORCED_FAILURE_COUNT,
        "unpooled_pilot_frame_count_requested": (
            EXPECTED_UNPOOLED_FRAME_COUNT
        ),
        "expected_layer_count": EXPECTED_LAYER_COUNT,
        "expected_hidden_size": EXPECTED_HIDDEN_SIZE,
        "expected_visual_token_count": EXPECTED_VISUAL_TOKENS,
        "expected_action_token_count": EXPECTED_ACTION_TOKENS,
        "mineocclude_revision": prepared["mineocclude_revision"],
        "source_revision": prepared["source_revision"],
        "asset_revision": prepared["asset_revision"],
        "precision": args.precision,
        "device": args.device,
        "context": {
            "frame_count": EXPECTED_CONTEXT_FRAMES,
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

    expected_names = tuple(
        f"transformer.model.layers.{index}"
        for index in range(EXPECTED_LAYER_COUNT)
    )
    if (
        len(modules) != EXPECTED_LAYER_COUNT
        or tuple(name for name, _module in modules) != expected_names
    ):
        _raise(
            "hook_layer_identity_mismatch",
            "teacher boundary must expose the exact 20 decoder modules",
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


def _memory(torch: Any) -> dict[str, int]:
    torch.cuda.synchronize(0)
    return {
        "allocated_bytes": int(torch.cuda.memory_allocated(0)),
        "reserved_bytes": int(torch.cuda.memory_reserved(0)),
    }


def _tensor_sha256(tensor: object) -> str:
    array = tensor.detach().cpu().contiguous().numpy()
    return hashlib.sha256(array.tobytes(order="C")).hexdigest()


def _write_json(path: Path, document: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _exception_chain_contains(
    error: BaseException,
    expected_type: type[BaseException],
) -> bool:
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        if isinstance(current, expected_type):
            return True
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return False


def _candidate_record(candidate: object) -> dict[str, Any]:
    vector = candidate.vector
    return {
        "trajectory_id": candidate.trajectory_id,
        "model_frame_idx": candidate.model_frame_idx,
        "layer_idx": candidate.layer_idx,
        "hook_site": candidate.hook_site,
        "shape": list(vector.shape),
        "dtype": str(vector.dtype),
        "device": str(vector.device),
        "source_shape": [
            candidate.source_batch_size,
            candidate.source_sequence_length,
            candidate.hidden_size,
        ],
        "source_dtype": candidate.source_dtype,
        "source_device": candidate.source_device,
        "selected_visual_token_count": (
            candidate.selected_visual_token_count
        ),
        "detached": not vector.requires_grad and vector.grad_fn is None,
        "contiguous": bool(vector.is_contiguous()),
        "sha256": _tensor_sha256(vector),
    }


def _attempt_record(
    *,
    name: str,
    status: str,
    before_counts: list[int],
    during_total: int,
    after_counts: list[int],
    callback_counts: list[int],
    capture_keys: list[int],
    manager_closed: bool,
    unresolved_handles: int,
    candidates_accepted: bool,
    failure: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "hooks": {
            "before_counts": before_counts,
            "active_total": during_total,
            "after_counts": after_counts,
            "callback_counts_by_layer": callback_counts,
            "observed_capture_keys": capture_keys,
            "manager_closed": manager_closed,
            "unresolved_handle_count": unresolved_handles,
        },
        "candidates_accepted": candidates_accepted,
        "failure": dict(failure) if failure is not None else None,
    }


def run(args: argparse.Namespace) -> Path:
    """Execute success A, controlled failure, then success B once confirmed."""

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
    from mineocclude.activations.pool import select_visual_token_positions
    from mineocclude.activations.store import (
        UnpooledPilotIdentity,
        extract_complete_pooled_context,
        validate_limited_unpooled_pilot,
        write_limited_unpooled_pilot,
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
    if session_root.exists():
        _raise(
            "session_exists",
            "immutable session directory already exists",
        )
    session_root.mkdir(parents=True)
    raw_log = session_root / RAW_LOG_FILENAME
    report_path = session_root / REPORT_FILENAME
    runtime_load_count = 0
    try:
        with raw_log.open(  # noqa: SIM117
            "x",
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
                runtime_load_count += 1
                if (
                    runtime.layer_count != EXPECTED_LAYER_COUNT
                    or runtime.hidden_size != EXPECTED_HIDDEN_SIZE
                ):
                    _raise(
                        "runtime_shape_mismatch",
                        "loaded runtime must have 20 layers and hidden 2048",
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
                del decoded
                baseline = _memory(torch)
                torch.cuda.reset_peak_memory_stats(0)
                attempts: list[dict[str, Any]] = []

                def execute_attempt(
                    name: str,
                    *,
                    force_failure: bool,
                    write_pilot: bool,
                ):
                    holder: dict[str, Any] = {}
                    callback_counts = [0] * EXPECTED_LAYER_COUNT
                    active_total = 0

                    def hook_factory(modules: tuple[tuple[str, object], ...]):
                        nonlocal active_total
                        discovery = _discovery_from_modules(modules)
                        before = [
                            _hook_count(module)
                            for _module_name, module in modules
                        ]
                        if any(before):
                            _raise(
                                "preexisting_decoder_hooks",
                                "every decoder layer must begin with zero hooks",
                            )

                        def callback(capture):
                            nonlocal active_total
                            observed_active = sum(
                                _hook_count(module)
                                for _module_name, module in modules
                            )
                            if active_total == 0:
                                active_total = observed_active
                            elif active_total != observed_active:
                                _raise(
                                    "hook_count_changed_while_active",
                                    "active hook count changed during forward",
                                )
                            callback_counts[capture.layer.layer_idx] += 1
                            if (
                                force_failure
                                and capture.layer.layer_idx
                                == FORCED_FAILURE_LAYER
                            ):
                                raise ForcedExtractionProbeFailure(
                                    "controlled failure after all hooks registered"
                                )

                        manager = ScopedHookManager(
                            discovery,
                            capture_callback=callback,
                        )
                        holder["manager"] = manager
                        holder["modules"] = modules
                        holder["before"] = before
                        return manager

                    started = time.perf_counter()
                    caught: BaseException | None = None
                    teacher_result = None
                    try:
                        teacher_result = adapter.teacher_forced(
                            TeacherForcedRequest(
                                runtime_identity=runtime,
                                trajectory=tokenized,
                                seed=args.seed,
                                precision=args.precision,
                                batch_size=1,
                                hook_context_factory=hook_factory,
                                expected_adapter_code_sha256=(
                                    code_identity.sha256
                                ),
                                accepted_manifest_sha256=accepted_hash,
                            )
                        )
                    except BaseException as exc:  # noqa: BLE001
                        caught = exc
                    elapsed = time.perf_counter() - started
                    manager = holder.get("manager")
                    modules = holder.get("modules", ())
                    if manager is None or len(modules) != EXPECTED_LAYER_COUNT:
                        _raise(
                            "hook_registration_not_reached",
                            f"{name}: hook manager was not constructed",
                        )
                    after = [
                        _hook_count(module)
                        for _module_name, module in modules
                    ]
                    capture_keys = sorted(manager.captures)
                    if (
                        not manager.closed
                        or manager.registered_hook_count != 0
                        or any(after)
                    ):
                        _raise(
                            "hook_cleanup_failed",
                            f"{name}: temporary hooks were not fully removed",
                        )
                    if force_failure:
                        if (
                            caught is None
                            or not _exception_chain_contains(
                                caught,
                                ForcedExtractionProbeFailure,
                            )
                            or active_total != EXPECTED_LAYER_COUNT
                        ):
                            _raise(
                                "forced_failure_mismatch",
                                "middle attempt did not preserve deliberate "
                                "post-registration failure identity",
                            )
                        attempts.append(
                            _attempt_record(
                                name=name,
                                status="EXPECTED_FAILURE",
                                before_counts=holder["before"],
                                during_total=active_total,
                                after_counts=after,
                                callback_counts=callback_counts,
                                capture_keys=capture_keys,
                                manager_closed=manager.closed,
                                unresolved_handles=(
                                    manager.registered_hook_count
                                ),
                                candidates_accepted=False,
                                failure={
                                    "exception_type": (
                                        ForcedExtractionProbeFailure.__name__
                                    ),
                                    "exception_message": (
                                        "controlled failure after all hooks "
                                        "registered"
                                    ),
                                    "layer_idx": FORCED_FAILURE_LAYER,
                                    "occurred_after_registration": True,
                                    "forward_seconds": elapsed,
                                },
                            )
                        )
                        return (), None, teacher_result, manager
                    if caught is not None:
                        raise caught
                    captures = manager.require_complete()
                    candidates = extract_complete_pooled_context(
                        captures=captures,
                        frame_token_map=tokenized.frame_token_map,
                        hook_site=HOOK_SITE,
                    )
                    if len(candidates) != EXPECTED_CANDIDATE_COUNT:
                        _raise(
                            "candidate_count_mismatch",
                            f"{name}: expected 160 candidates",
                        )
                    pilot = None
                    if write_pilot:
                        span = tokenized.frame_token_map.spans[0]
                        selection = select_visual_token_positions(
                            tokenized.frame_token_map,
                            trajectory_id=span.identity.trajectory_id,
                            model_frame_idx=span.identity.model_frame_idx,
                            hooked_sequence_length=(
                                tokenized.frame_token_map.sequence_length
                            ),
                        )
                        pilot = write_limited_unpooled_pilot(
                            captures=captures,
                            frame_token_map=tokenized.frame_token_map,
                            selection=selection,
                            pooled_candidates=candidates,
                            identity=UnpooledPilotIdentity(
                                session_id=args.session_id,
                                trajectory_id=span.identity.trajectory_id,
                                model_frame_idx=span.identity.model_frame_idx,
                                hook_site=HOOK_SITE,
                                frame_token_map_sha256=(
                                    tokenized.frame_token_map_sha256
                                ),
                                mineocclude_revision=(
                                    runtime.mineocclude_revision
                                ),
                                mineworld_revision=(
                                    runtime.mineworld_source_revision
                                ),
                                asset_revision=(
                                    runtime.modelscope_asset_revision
                                ),
                                model_config_sha256=(
                                    runtime.model_config_sha256
                                ),
                                main_checkpoint_sha256=(
                                    runtime.main_checkpoint_sha256
                                ),
                                vae_config_sha256=(
                                    runtime.vae_config_sha256
                                ),
                                vae_checkpoint_sha256=(
                                    runtime.vae_checkpoint_sha256
                                ),
                                environment_report_sha256=(
                                    runtime.environment_report_sha256
                                ),
                                preprocessing_profile=(
                                    tokenized.preprocessing_profile
                                ),
                                action_conversion_profile=(
                                    tokenized.action_conversion_profile
                                ),
                                tokenization_profile=(
                                    tokenized.tokenization_profile
                                ),
                                accepted_trajectory_package_sha256=(
                                    accepted_hash
                                ),
                                input_mp4_sha256=(
                                    prepared["input_mp4_sha256"]
                                ),
                            ),
                            output_directory=session_root,
                            enabled=True,
                        )
                    attempts.append(
                        _attempt_record(
                            name=name,
                            status="PASS",
                            before_counts=holder["before"],
                            during_total=active_total,
                            after_counts=after,
                            callback_counts=callback_counts,
                            capture_keys=capture_keys,
                            manager_closed=manager.closed,
                            unresolved_handles=manager.registered_hook_count,
                            candidates_accepted=True,
                            failure=None,
                        )
                    )
                    attempts[-1]["forward_seconds"] = elapsed
                    return candidates, pilot, teacher_result, manager

                candidates_a, pilot, teacher_a, manager_a = execute_attempt(
                    "extraction_a",
                    force_failure=False,
                    write_pilot=True,
                )
                records_a = tuple(
                    _candidate_record(candidate)
                    for candidate in candidates_a
                )
                del teacher_a
                del manager_a
                gc.collect()
                after_a = _memory(torch)

                failed_candidates, _none_pilot, failed_result, failed_manager = (
                    execute_attempt(
                        "forced_failure",
                        force_failure=True,
                        write_pilot=False,
                    )
                )
                if failed_candidates:
                    _raise(
                        "failed_candidates_accepted",
                        "forced failure must not yield accepted candidates",
                    )
                del failed_result
                del failed_manager
                gc.collect()
                after_failure = _memory(torch)

                candidates_b, _none_pilot, teacher_b, manager_b = execute_attempt(
                    "extraction_b",
                    force_failure=False,
                    write_pilot=False,
                )
                records_b = tuple(
                    _candidate_record(candidate)
                    for candidate in candidates_b
                )
                del teacher_b
                del manager_b
                gc.collect()
                after_b = _memory(torch)

                comparison_records = []
                maximum_difference = 0.0
                unequal_count = 0
                for candidate_a, candidate_b in zip(
                    candidates_a,
                    candidates_b,
                    strict=True,
                ):
                    if candidate_a.key != candidate_b.key:
                        _raise(
                            "candidate_order_mismatch",
                            "successful candidate key ordering differs",
                        )
                    metadata_a = (
                        candidate_a.hidden_size,
                        candidate_a.source_batch_size,
                        candidate_a.source_sequence_length,
                        candidate_a.selected_visual_token_count,
                        candidate_a.source_dtype,
                        candidate_a.source_device,
                        candidate_a.returned_dtype,
                        candidate_a.returned_device,
                    )
                    metadata_b = (
                        candidate_b.hidden_size,
                        candidate_b.source_batch_size,
                        candidate_b.source_sequence_length,
                        candidate_b.selected_visual_token_count,
                        candidate_b.source_dtype,
                        candidate_b.source_device,
                        candidate_b.returned_dtype,
                        candidate_b.returned_device,
                    )
                    if metadata_a != metadata_b:
                        _raise(
                            "candidate_metadata_mismatch",
                            "successful candidate metadata differs",
                        )
                    equal = bool(
                        torch.allclose(
                            candidate_a.vector,
                            candidate_b.vector,
                            rtol=CANDIDATE_COMPARISON_RTOL,
                            atol=CANDIDATE_COMPARISON_ATOL,
                        )
                    )
                    absolute_difference = (
                        candidate_a.vector - candidate_b.vector
                    ).abs()
                    difference = float(
                        absolute_difference.max().item()
                    )
                    tolerance_ratio = float(
                        (
                            absolute_difference
                            / (
                                CANDIDATE_COMPARISON_ATOL
                                + CANDIDATE_COMPARISON_RTOL
                                * candidate_b.vector.abs()
                            )
                        )
                        .max()
                        .item()
                    )
                    maximum_difference = max(
                        maximum_difference,
                        difference,
                    )
                    unequal_count += int(not equal)
                    comparison_records.append(
                        {
                            "trajectory_id": candidate_a.trajectory_id,
                            "model_frame_idx": candidate_a.model_frame_idx,
                            "layer_idx": candidate_a.layer_idx,
                            "hook_site": candidate_a.hook_site,
                            "a_sha256": _tensor_sha256(
                                candidate_a.vector
                            ),
                            "b_sha256": _tensor_sha256(
                                candidate_b.vector
                            ),
                            "shape": list(candidate_a.vector.shape),
                            "dtype": str(candidate_a.vector.dtype),
                            "device": str(candidate_a.vector.device),
                            "source_shape": [
                                candidate_a.source_batch_size,
                                candidate_a.source_sequence_length,
                                candidate_a.hidden_size,
                            ],
                            "source_dtype": candidate_a.source_dtype,
                            "source_device": candidate_a.source_device,
                            "selected_visual_token_count": (
                                candidate_a.selected_visual_token_count
                            ),
                            "a_detached": (
                                not candidate_a.vector.requires_grad
                                and candidate_a.vector.grad_fn is None
                            ),
                            "b_detached": (
                                not candidate_b.vector.requires_grad
                                and candidate_b.vector.grad_fn is None
                            ),
                            "a_contiguous": bool(
                                candidate_a.vector.is_contiguous()
                            ),
                            "b_contiguous": bool(
                                candidate_b.vector.is_contiguous()
                            ),
                            "allclose": equal,
                            "maximum_absolute_difference": difference,
                            "maximum_tolerance_ratio": tolerance_ratio,
                        }
                    )
                if unequal_count:
                    _raise(
                        "consecutive_extraction_mismatch",
                        "successful candidates exceed committed repeatability "
                        "tolerances",
                    )

                validated_pilot = validate_limited_unpooled_pilot(
                    pilot.manifest_path,
                    expected_hidden_size=EXPECTED_HIDDEN_SIZE,
                )
                a_by_layer = {
                    record["layer_idx"]: record["sha256"]
                    for record in records_a
                    if record["trajectory_id"]
                    == tokenized.frame_token_map.spans[0].identity.trajectory_id
                    and record["model_frame_idx"]
                    == tokenized.frame_token_map.spans[
                        0
                    ].identity.model_frame_idx
                }
                for record in validated_pilot.pooling_audit:
                    if (
                        a_by_layer.get(record["layer_idx"])
                        != record["candidate_sha256"]
                    ):
                        _raise(
                            "unpooled_candidate_mismatch",
                            "pilot mean hash differs from extraction A",
                        )

                peak = {
                    "allocated_bytes": int(
                        torch.cuda.max_memory_allocated(0)
                    ),
                    "reserved_bytes": int(
                        torch.cuda.max_memory_reserved(0)
                    ),
                }
                memory = {
                    "baseline_after_load_before_extraction_a": baseline,
                    "after_extraction_a_cleanup": after_a,
                    "after_forced_failure_cleanup": after_failure,
                    "after_extraction_b_cleanup": after_b,
                    "peak": peak,
                    "allocated_tolerance_bytes": MEMORY_TOLERANCE_BYTES,
                }
                allocated_baseline = baseline["allocated_bytes"]
                cleanup_values = (after_a, after_failure, after_b)
                memory["post_cleanup_allocated_deltas_bytes"] = [
                    item["allocated_bytes"] - allocated_baseline
                    for item in cleanup_values
                ]
                memory["b_minus_a_allocated_bytes"] = (
                    after_b["allocated_bytes"]
                    - after_a["allocated_bytes"]
                )
                memory["status"] = (
                    "PASS"
                    if all(
                        item["allocated_bytes"]
                        <= allocated_baseline + MEMORY_TOLERANCE_BYTES
                        for item in cleanup_values
                    )
                    and after_b["allocated_bytes"]
                    <= after_a["allocated_bytes"]
                    + MEMORY_TOLERANCE_BYTES
                    else "FAIL"
                )
                if memory["status"] != "PASS":
                    _raise(
                        "memory_growth",
                        "post-cleanup allocated memory exceeds the 1 MiB rule",
                    )

                report = {
                    "schema_version": "1.0",
                    "probe_version": PROBE_VERSION,
                    "status": "PASS",
                    "session_id": args.session_id,
                    "identities": {
                        "mineocclude_revision": (
                            runtime.mineocclude_revision
                        ),
                        "source_revision": (
                            runtime.mineworld_source_revision
                        ),
                        "asset_revision": (
                            runtime.modelscope_asset_revision
                        ),
                        "environment_report_sha256": (
                            runtime.environment_report_sha256
                        ),
                        "accepted_trajectory_package_sha256": (
                            accepted_hash
                        ),
                        "input_mp4_sha256": (
                            prepared["input_mp4_sha256"]
                        ),
                        "runtime_id": runtime.runtime_id,
                        "frame_token_map_sha256": (
                            tokenized.frame_token_map_sha256
                        ),
                        "adapter_code_sha256": (
                            runtime.adapter_code_sha256
                        ),
                    },
                    "counts": {
                        "runtime_load_count": runtime_load_count,
                        "forward_attempt_count": len(attempts),
                        "successful_extraction_count": sum(
                            attempt["status"] == "PASS"
                            for attempt in attempts
                        ),
                        "forced_failure_count": sum(
                            attempt["status"] == "EXPECTED_FAILURE"
                            for attempt in attempts
                        ),
                        "frame_count": len(
                            tokenized.frame_token_map.spans
                        ),
                        "layer_count": EXPECTED_LAYER_COUNT,
                        "candidate_count_per_success": len(candidates_a),
                        "expected_candidate_count_per_success": (
                            EXPECTED_CANDIDATE_COUNT
                        ),
                    },
                    "attempts": attempts,
                    "candidate_comparison": {
                        "comparison": "torch.allclose",
                        "rtol": CANDIDATE_COMPARISON_RTOL,
                        "atol": CANDIDATE_COMPARISON_ATOL,
                        "maximum_absolute_difference": (
                            maximum_difference
                        ),
                        "unequal_candidate_count": unequal_count,
                        "records": comparison_records,
                        "status": "PASS",
                    },
                    "candidate_run_a": list(records_a),
                    "candidate_run_b": list(records_b),
                    "memory": memory,
                    "unpooled_pilot": {
                        "classification": (
                            "limited_one_frame_unpooled_pilot"
                        ),
                        "manifest_path": pilot.manifest_path.name,
                        "manifest_size_bytes": (
                            pilot.manifest_size_bytes
                        ),
                        "manifest_sha256": pilot.manifest_sha256,
                        "artifact_path": pilot.artifact_path.name,
                        "artifact_size_bytes": (
                            pilot.artifact_size_bytes
                        ),
                        "artifact_sha256": pilot.artifact_sha256,
                        "shape": list(pilot.token_shape),
                        "dtype": pilot.token_dtype,
                        "layer_indices": list(pilot.layer_indices),
                        "visual_positions": list(
                            pilot.visual_positions
                        ),
                        "action_positions_saved": False,
                        "dataset_wide_unpooled_storage_enabled": False,
                        "pooling_audit_status": "PASS",
                        "pooling_audit": [
                            dict(record)
                            for record in pilot.pooling_audit
                        ],
                    },
                    "files": {
                        RAW_LOG_FILENAME: {
                            "size_bytes": raw_log.stat().st_size,
                            "sha256": _sha256_file(raw_log),
                        }
                    },
                    "command": sys.argv,
                }
                log.flush()
                _write_json(report_path, report)
        validate(report_path, verify_files=True)
        return report_path
    except BaseException as exc:
        if not raw_log.exists():
            raw_log.write_text(
                f"{type(exc).__name__}: {exc}\n",
                encoding="utf-8",
            )
        else:
            with raw_log.open("a", encoding="utf-8") as log:
                traceback.print_exc(file=log)
        failure_path = session_root / FAILURE_FILENAME
        if not failure_path.exists():
            _write_json(
                failure_path,
                {
                    "schema_version": "1.0",
                    "probe_version": PROBE_VERSION,
                    "status": "FAIL",
                    "session_id": args.session_id,
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                    "runtime_load_count": runtime_load_count,
                    "immutable_failed_attempt": True,
                },
            )
        raise


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _raise("invalid_report", f"{field} must be an object")
    return value


def _integer(value: object, field: str, expected: int | None = None) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        _raise("invalid_report", f"{field} must be a non-negative integer")
    if expected is not None and value != expected:
        _raise(
            "invalid_report",
            f"{field}: expected {expected}, observed {value}",
        )
    return value


def _finite_number(value: object, field: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        _raise("invalid_report", f"{field} must be finite")
    return float(value)


def _validate_hook_attempts(attempts: object) -> None:
    if not isinstance(attempts, list) or len(attempts) != 3:
        _raise("attempt_count_mismatch", "exactly three attempt records required")
    expected = (
        ("extraction_a", "PASS"),
        ("forced_failure", "EXPECTED_FAILURE"),
        ("extraction_b", "PASS"),
    )
    for index, (attempt, expected_identity) in enumerate(
        zip(attempts, expected, strict=True)
    ):
        item = _mapping(attempt, f"attempts[{index}]")
        if (item.get("name"), item.get("status")) != expected_identity:
            _raise(
                "attempt_order_mismatch",
                "attempts must be success A, expected failure, success B",
            )
        hooks = _mapping(item.get("hooks"), f"attempts[{index}].hooks")
        before = hooks.get("before_counts")
        after = hooks.get("after_counts")
        callbacks = hooks.get("callback_counts_by_layer")
        captures = hooks.get("observed_capture_keys")
        if (
            before != [0] * EXPECTED_LAYER_COUNT
            or hooks.get("active_total") != EXPECTED_LAYER_COUNT
            or after != [0] * EXPECTED_LAYER_COUNT
            or hooks.get("manager_closed") is not True
            or hooks.get("unresolved_handle_count") != 0
            or not isinstance(callbacks, list)
            or len(callbacks) != EXPECTED_LAYER_COUNT
            or any(value not in (0, 1) for value in callbacks)
            or not isinstance(captures, list)
            or len(captures) != len(set(captures))
        ):
            _raise(
                "hook_cleanup_mismatch",
                f"attempt {index} hook lifecycle is incomplete",
            )
        expected_capture_keys = [
            layer_idx
            for layer_idx, callback_count in enumerate(callbacks)
            if callback_count == 1
        ]
        if captures != expected_capture_keys:
            _raise(
                "capture_callback_mismatch",
                f"attempt {index} capture keys differ from callback evidence",
            )
        if item.get("status") == "PASS":
            if (
                callbacks != [1] * EXPECTED_LAYER_COUNT
                or captures != list(range(EXPECTED_LAYER_COUNT))
                or item.get("candidates_accepted") is not True
                or item.get("failure") is not None
            ):
                _raise(
                    "successful_capture_mismatch",
                    f"attempt {index} must capture all layers exactly once",
                )
        else:
            failure = _mapping(item.get("failure"), "forced failure")
            if (
                item.get("candidates_accepted") is not False
                or failure.get("exception_type")
                != ForcedExtractionProbeFailure.__name__
                or failure.get("layer_idx") != FORCED_FAILURE_LAYER
                or failure.get("occurred_after_registration") is not True
                or callbacks[FORCED_FAILURE_LAYER] != 1
                or any(callbacks[layer] for layer in range(11, 20))
            ):
                _raise(
                    "forced_failure_mismatch",
                    "forced failure evidence is incomplete or mistimed",
                )


def _candidate_key(record: Mapping[str, Any]) -> tuple[str, int, int, str]:
    trajectory_id = record.get("trajectory_id")
    model_frame_idx = record.get("model_frame_idx")
    layer_idx = record.get("layer_idx")
    hook_site = record.get("hook_site")
    if (
        not isinstance(trajectory_id, str)
        or not trajectory_id
        or type(model_frame_idx) is not int
        or model_frame_idx < 0
        or type(layer_idx) is not int
        or layer_idx not in range(EXPECTED_LAYER_COUNT)
        or hook_site != HOOK_SITE
    ):
        _raise("candidate_identity_mismatch", "candidate key is invalid")
    return trajectory_id, model_frame_idx, layer_idx, hook_site


def _validate_candidates(report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    comparison = _mapping(
        report.get("candidate_comparison"),
        "candidate_comparison",
    )
    records = comparison.get("records")
    run_a = report.get("candidate_run_a")
    run_b = report.get("candidate_run_b")
    if (
        not isinstance(records, list)
        or len(records) != EXPECTED_CANDIDATE_COUNT
        or not isinstance(run_a, list)
        or len(run_a) != EXPECTED_CANDIDATE_COUNT
        or not isinstance(run_b, list)
        or len(run_b) != EXPECTED_CANDIDATE_COUNT
        or comparison.get("comparison") != "torch.allclose"
        or comparison.get("rtol") != CANDIDATE_COMPARISON_RTOL
        or comparison.get("atol") != CANDIDATE_COMPARISON_ATOL
        or not isinstance(
            comparison.get("maximum_absolute_difference"),
            (int, float),
        )
        or isinstance(
            comparison.get("maximum_absolute_difference"),
            bool,
        )
        or not math.isfinite(
            float(comparison.get("maximum_absolute_difference"))
        )
        or float(comparison.get("maximum_absolute_difference")) < 0.0
        or comparison.get("unequal_candidate_count") != 0
        or comparison.get("status") != "PASS"
    ):
        _raise(
            "candidate_comparison_mismatch",
            "candidate comparison must record 160 exact equal pairs",
        )
    keys = []
    recorded_maxima: list[float] = []
    for index, (record_value, a_value, b_value) in enumerate(
        zip(records, run_a, run_b, strict=True)
    ):
        record = _mapping(record_value, f"comparison.records[{index}]")
        a_record = _mapping(a_value, f"candidate_run_a[{index}]")
        b_record = _mapping(b_value, f"candidate_run_b[{index}]")
        key = _candidate_key(record)
        if key != _candidate_key(a_record) or key != _candidate_key(b_record):
            _raise(
                "candidate_order_mismatch",
                "A/B/comparison keys differ",
            )
        required = {
            "shape": [EXPECTED_HIDDEN_SIZE],
            "dtype": "torch.float32",
            "device": "cpu",
            "source_shape": [1, EXPECTED_CONTEXT_FRAMES * 347, EXPECTED_HIDDEN_SIZE],
            "source_dtype": "torch.float16",
            "source_device": "cuda:0",
            "selected_visual_token_count": EXPECTED_VISUAL_TOKENS,
        }
        recorded_difference = _finite_number(
            record.get("maximum_absolute_difference"),
            "maximum_absolute_difference",
        )
        recorded_ratio = _finite_number(
            record.get("maximum_tolerance_ratio"),
            "maximum_tolerance_ratio",
        )
        if (
            any(record.get(field) != value for field, value in required.items())
            or record.get("a_detached") is not True
            or record.get("b_detached") is not True
            or record.get("a_contiguous") is not True
            or record.get("b_contiguous") is not True
            or record.get("allclose") is not True
            or recorded_difference < 0.0
            or recorded_ratio > 1.0
            or _require_sha256(record.get("a_sha256"), "a_sha256")
            != _require_sha256(a_record.get("sha256"), "run A sha256")
            or _require_sha256(record.get("b_sha256"), "b_sha256")
            != _require_sha256(b_record.get("sha256"), "run B sha256")
        ):
            _raise(
                "candidate_metadata_mismatch",
                f"candidate {index} metadata or hash is invalid",
            )
        for side in (a_record, b_record):
            if (
                side.get("shape") != [EXPECTED_HIDDEN_SIZE]
                or side.get("dtype") != "torch.float32"
                or side.get("device") != "cpu"
                or side.get("source_shape")
                != [1, EXPECTED_CONTEXT_FRAMES * 347, EXPECTED_HIDDEN_SIZE]
                or side.get("source_dtype") != "torch.float16"
                or side.get("source_device") != "cuda:0"
                or side.get("selected_visual_token_count")
                != EXPECTED_VISUAL_TOKENS
                or side.get("detached") is not True
                or side.get("contiguous") is not True
            ):
                _raise(
                    "candidate_metadata_mismatch",
                    f"candidate {index} run metadata is invalid",
                )
        keys.append(key)
        recorded_maxima.append(recorded_difference)
    if len(keys) != len(set(keys)):
        _raise("duplicate_candidate", "candidate identities must be unique")
    frame_order: list[tuple[str, int]] = []
    for trajectory_id, model_frame_idx, _layer_idx, _hook_site in keys:
        identity = (trajectory_id, model_frame_idx)
        if not frame_order or frame_order[-1] != identity:
            frame_order.append(identity)
    expected_keys = [
        (trajectory_id, model_frame_idx, layer_idx, HOOK_SITE)
        for trajectory_id, model_frame_idx in frame_order
        for layer_idx in range(EXPECTED_LAYER_COUNT)
    ]
    if (
        len(frame_order) != EXPECTED_CONTEXT_FRAMES
        or keys != expected_keys
        or max(recorded_maxima) != float(
            comparison["maximum_absolute_difference"]
        )
    ):
        _raise(
            "candidate_coverage_mismatch",
            "candidate keys must cover eight frames x 20 ordered layers",
        )
    return [record for record in records if isinstance(record, Mapping)]


def _validate_memory(memory_value: object) -> None:
    memory = _mapping(memory_value, "memory")
    tolerance = _integer(
        memory.get("allocated_tolerance_bytes"),
        "memory.allocated_tolerance_bytes",
        MEMORY_TOLERANCE_BYTES,
    )
    labels = (
        "baseline_after_load_before_extraction_a",
        "after_extraction_a_cleanup",
        "after_forced_failure_cleanup",
        "after_extraction_b_cleanup",
        "peak",
    )
    measurements = {
        label: _mapping(memory.get(label), f"memory.{label}")
        for label in labels
    }
    for label, measurement in measurements.items():
        _integer(
            measurement.get("allocated_bytes"),
            f"memory.{label}.allocated_bytes",
        )
        _integer(
            measurement.get("reserved_bytes"),
            f"memory.{label}.reserved_bytes",
        )
    if (
        measurements["peak"]["allocated_bytes"]
        < max(
            measurement["allocated_bytes"]
            for label, measurement in measurements.items()
            if label != "peak"
        )
        or measurements["peak"]["reserved_bytes"]
        < max(
            measurement["reserved_bytes"]
            for label, measurement in measurements.items()
            if label != "peak"
        )
    ):
        _raise(
            "invalid_peak_memory",
            "peak memory must cover every recorded boundary",
        )
    baseline = measurements[
        "baseline_after_load_before_extraction_a"
    ]["allocated_bytes"]
    after_a = measurements["after_extraction_a_cleanup"]["allocated_bytes"]
    after_failure = measurements[
        "after_forced_failure_cleanup"
    ]["allocated_bytes"]
    after_b = measurements["after_extraction_b_cleanup"]["allocated_bytes"]
    deltas = [after_a - baseline, after_failure - baseline, after_b - baseline]
    if (
        any(value > tolerance for value in deltas)
        or after_b > after_a + tolerance
        or memory.get("post_cleanup_allocated_deltas_bytes") != deltas
        or memory.get("b_minus_a_allocated_bytes") != after_b - after_a
        or memory.get("status") != "PASS"
    ):
        _raise(
            "memory_growth",
            "post-cleanup allocated memory violates the fixed 1 MiB rule",
        )


def _validate_unpooled(
    report_path: Path,
    report: Mapping[str, Any],
    candidates: list[Mapping[str, Any]],
    *,
    verify_files: bool,
) -> None:
    pilot = _mapping(report.get("unpooled_pilot"), "unpooled_pilot")
    report_audit = pilot.get("pooling_audit")
    if (
        pilot.get("classification")
        != "limited_one_frame_unpooled_pilot"
        or pilot.get("shape")
        != [
            EXPECTED_LAYER_COUNT,
            EXPECTED_VISUAL_TOKENS,
            EXPECTED_HIDDEN_SIZE,
        ]
        or pilot.get("dtype") != "float16"
        or pilot.get("layer_indices")
        != list(range(EXPECTED_LAYER_COUNT))
        or pilot.get("action_positions_saved") is not False
        or pilot.get("dataset_wide_unpooled_storage_enabled") is not False
        or pilot.get("pooling_audit_status") != "PASS"
        or not isinstance(report_audit, list)
        or len(report_audit) != EXPECTED_LAYER_COUNT
    ):
        _raise(
            "unpooled_identity_mismatch",
            "limited pilot identity, shape, dtype, or scope is invalid",
        )
    for layer_idx, record_value in enumerate(report_audit):
        record = _mapping(
            record_value,
            f"unpooled_pilot.pooling_audit[{layer_idx}]",
        )
        if (
            record.get("layer_idx") != layer_idx
            or record.get("torch_equal") is not True
            or record.get("maximum_absolute_difference") != 0.0
            or _require_sha256(
                record.get("candidate_sha256"),
                "unpooled candidate sha256",
            )
            != _require_sha256(
                record.get("artifact_mean_sha256"),
                "unpooled artifact mean sha256",
            )
        ):
            _raise(
                "unpooled_pooling_audit_mismatch",
                "report pooling audit must preserve 20 exact layer results",
            )
    positions = pilot.get("visual_positions")
    if (
        not isinstance(positions, list)
        or len(positions) != EXPECTED_VISUAL_TOKENS
        or positions != sorted(set(positions))
        or any(type(value) is not int or value < 0 for value in positions)
    ):
        _raise(
            "unpooled_position_mismatch",
            "pilot must preserve 336 unique ordered visual positions",
        )
    action_positions = {
        pair_index * 347 + offset
        for pair_index in range(EXPECTED_CONTEXT_FRAMES)
        for offset in range(336, 347)
    }
    if set(positions) & action_positions:
        _raise(
            "unpooled_action_contamination",
            "pilot visual positions overlap action rows",
        )
    if not verify_files:
        return

    manifest_name = pilot.get("manifest_path")
    artifact_name = pilot.get("artifact_path")
    if (
        not isinstance(manifest_name, str)
        or Path(manifest_name).name != manifest_name
        or not isinstance(artifact_name, str)
        or Path(artifact_name).name != artifact_name
    ):
        _raise("unsafe_artifact_path", "pilot paths must be relative names")
    manifest_path = report_path.parent / manifest_name
    artifact_path = report_path.parent / artifact_name
    for path, size_field, sha_field in (
        (
            manifest_path,
            "manifest_size_bytes",
            "manifest_sha256",
        ),
        (
            artifact_path,
            "artifact_size_bytes",
            "artifact_sha256",
        ),
    ):
        if (
            not path.is_file()
            or path.stat().st_size != pilot.get(size_field)
            or _sha256_file(path)
            != _require_sha256(pilot.get(sha_field), sha_field)
        ):
            _raise(
                "artifact_identity_mismatch",
                f"{path.name}: size or SHA-256 mismatch",
            )
    tensor_files = sorted(
        path
        for path in report_path.parent.iterdir()
        if path.is_file()
        and path.suffix.lower() in _FORBIDDEN_TENSOR_SUFFIXES
    )
    if tensor_files != [artifact_path]:
        _raise(
            "extra_tensor_artifact",
            "session must contain exactly one approved .npz tensor artifact",
        )
    from mineocclude.activations.store import (
        validate_limited_unpooled_pilot,
    )

    validated = validate_limited_unpooled_pilot(
        manifest_path,
        expected_hidden_size=EXPECTED_HIDDEN_SIZE,
    )
    first_frame = (
        candidates[0]["trajectory_id"],
        candidates[0]["model_frame_idx"],
    )
    if (
        validated.session_id != report.get("session_id")
        or (
            validated.trajectory_id,
            validated.model_frame_idx,
        )
        != first_frame
        or validated.hook_site != HOOK_SITE
        or validated.source_sequence_length
        != EXPECTED_CONTEXT_FRAMES * 347
        or validated.source_hidden_size != EXPECTED_HIDDEN_SIZE
        or validated.source_dtype != "torch.float16"
        or validated.source_device != "cuda:0"
        or list(validated.visual_positions) != positions
        or list(validated.layer_indices) != list(range(EXPECTED_LAYER_COUNT))
        or list(validated.token_shape) != pilot.get("shape")
        or validated.token_dtype != pilot.get("dtype")
    ):
        _raise(
            "unpooled_identity_mismatch",
            "independent artifact identity differs from the runtime report",
        )
    audit = {
        int(record["layer_idx"]): record["candidate_sha256"]
        for record in validated.pooling_audit
    }
    expected = {
        int(record["layer_idx"]): record["a_sha256"]
        for record in candidates
        if (
            record["trajectory_id"],
            record["model_frame_idx"],
        )
        == first_frame
    }
    if audit != expected:
        _raise(
            "unpooled_pooling_audit_mismatch",
            "artifact-derived mean hashes differ from extraction A",
        )
    report_audit_hashes = {
        int(record["layer_idx"]): record["candidate_sha256"]
        for record in report_audit
    }
    if report_audit_hashes != audit:
        _raise(
            "unpooled_pooling_audit_mismatch",
            "report and independent manifest pooling audits differ",
        )


def validate(report_path: Path, *, verify_files: bool = True) -> None:
    """Validate bounded evidence without model import or CUDA execution."""

    if not report_path.is_file():
        _raise("missing_report", f"report does not exist: {report_path}")
    report = _strict_json(report_path)
    if (
        report.get("schema_version") != "1.0"
        or report.get("probe_version") != PROBE_VERSION
        or report.get("status") != "PASS"
    ):
        _raise(
            "invalid_report_identity",
            "schema, probe, or PASS identity is invalid",
        )
    counts = _mapping(report.get("counts"), "counts")
    expected_counts = {
        "runtime_load_count": EXPECTED_RUNTIME_LOAD_COUNT,
        "forward_attempt_count": EXPECTED_FORWARD_ATTEMPT_COUNT,
        "successful_extraction_count": (
            EXPECTED_SUCCESSFUL_EXTRACTION_COUNT
        ),
        "forced_failure_count": EXPECTED_FORCED_FAILURE_COUNT,
        "frame_count": EXPECTED_CONTEXT_FRAMES,
        "layer_count": EXPECTED_LAYER_COUNT,
        "candidate_count_per_success": EXPECTED_CANDIDATE_COUNT,
        "expected_candidate_count_per_success": EXPECTED_CANDIDATE_COUNT,
    }
    for field, expected in expected_counts.items():
        _integer(counts.get(field), f"counts.{field}", expected)
    identities = _mapping(report.get("identities"), "identities")
    for field in (
        "environment_report_sha256",
        "accepted_trajectory_package_sha256",
        "input_mp4_sha256",
        "frame_token_map_sha256",
        "adapter_code_sha256",
    ):
        _require_sha256(identities.get(field), f"identities.{field}")
    for field in (
        "mineocclude_revision",
        "source_revision",
        "asset_revision",
    ):
        _require_git_sha(identities.get(field), f"identities.{field}")
    _validate_hook_attempts(report.get("attempts"))
    candidates = _validate_candidates(report)
    _validate_memory(report.get("memory"))
    _validate_unpooled(
        report_path,
        report,
        candidates,
        verify_files=verify_files,
    )
    if verify_files:
        files = _mapping(report.get("files"), "files")
        raw = _mapping(files.get(RAW_LOG_FILENAME), RAW_LOG_FILENAME)
        raw_path = report_path.parent / RAW_LOG_FILENAME
        if (
            not raw_path.is_file()
            or raw_path.stat().st_size != raw.get("size_bytes")
            or _sha256_file(raw_path)
            != _require_sha256(raw.get("sha256"), "raw log sha256")
        ):
            _raise(
                "referenced_file_mismatch",
                "raw log size or SHA-256 mismatch",
            )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""

    args = build_parser().parse_args(argv)
    try:
        if args.command == "preflight":
            print(
                json.dumps(
                    _public_preflight(preflight(args)),
                    indent=2,
                    sort_keys=True,
                    allow_nan=False,
                )
            )
        elif args.command == "run":
            print(run(args))
        else:
            validate(args.report, verify_files=True)
            print("PASS")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
