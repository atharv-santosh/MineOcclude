"""AWS-only executors for Person A Phase 2.6-2.9.

The module imports PyTorch and the external MineWorld checkout lazily.  Merely
importing it, building parsers, or running its unit tests cannot execute model
code.  Every execution path requires an explicit confirmation flag and a real
CUDA runtime.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import json
import os
import random
import shutil
import subprocess
import sys
import time
import traceback
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator, Mapping, Sequence, TextIO

from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.models.phase2_evidence import (
    ARCHITECTURE_EVIDENCE_TYPE,
    EVIDENCE_SCHEMA_VERSION,
    ROLLOUT_EVIDENCE_TYPE,
    TEACHER_FORCED_EVIDENCE_TYPE,
    EvidenceValidationError,
    artifact_record,
    expected_teacher_token_layout,
    parse_ffprobe_output,
    seal_document,
    sha256_bytes,
    sha256_file,
    validate_architecture_facts,
    validate_architecture_report,
    validate_rollout_manifest,
    validate_teacher_forced_report,
    write_sealed_document,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
PINNED_SOURCE_REVISION = "9f49efbcc68a5f0cf60e78f0abc566eac409282f"
PINNED_ASSET_REVISION = "0dd5561ab317115831badc50e09a6ebe98693d0e"
PINNED_MAIN_CHECKPOINT_SHA256 = (
    "a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5"
)
PINNED_VAE_CONFIG_SHA256 = (
    "32ca759d5b90f0c5aa5df0e312a81e03dd4d3af68896863c88f910d19f2526cb"
)
PINNED_VAE_CHECKPOINT_SHA256 = (
    "370d06be427e034476b6b95ba0080a4b48266e876c4776a757b944b87b87d9ab"
)
EXPECTED_LAYERS = 20
EXPECTED_HIDDEN_SIZE = 2048
VISUAL_TOKENS = 336
ACTION_TOKENS = 11
TOKENS_PER_PAIR = 347
CONTEXT_PAIRS = 16
SEQUENCE_LENGTH = TOKENS_PER_PAIR * CONTEXT_PAIRS


class _Tee:
    """Write raw output to both the invoking terminal and the evidence log."""

    def __init__(self, *streams: TextIO) -> None:
        self._streams = streams

    def write(self, value: str) -> int:
        for stream in self._streams:
            stream.write(value)
            stream.flush()
        return len(value)

    def flush(self) -> None:
        for stream in self._streams:
            stream.flush()


@contextlib.contextmanager
def _raw_log(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        with contextlib.redirect_stdout(_Tee(sys.stdout, handle)):
            with contextlib.redirect_stderr(_Tee(sys.stderr, handle)):
                try:
                    yield
                except Exception:
                    traceback.print_exc()
                    raise


@contextlib.contextmanager
def _external_source_imports(source_root: Path) -> Iterator[None]:
    """Temporarily expose the pinned checkout without editing or vendoring it."""

    source_text = str(source_root)
    old_cwd = Path.cwd()
    inserted = source_text not in sys.path
    if inserted:
        sys.path.insert(0, source_text)
    os.chdir(source_root)
    try:
        yield
    finally:
        os.chdir(old_cwd)
        if inserted and source_text in sys.path:
            sys.path.remove(source_text)


def _sha256_argument(value: str) -> str:
    lowered = value.lower()
    if len(lowered) != 64 or any(character not in "0123456789abcdef" for character in lowered):
        raise argparse.ArgumentTypeError("Expected a 64-character SHA-256 value.")
    return lowered


def _git_sha_argument(value: str) -> str:
    lowered = value.lower()
    if len(lowered) != 40 or any(character not in "0123456789abcdef" for character in lowered):
        raise argparse.ArgumentTypeError("Expected a full 40-character Git SHA.")
    return lowered


def _nonnegative_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("Expected a non-negative integer.")
    return parsed


def _at_least_two(value: str) -> int:
    parsed = int(value)
    if parsed < 2:
        raise argparse.ArgumentTypeError("Expected at least two repeats.")
    return parsed


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mineworld-source-root", required=True, type=Path)
    parser.add_argument("--model-config", required=True, type=Path)
    parser.add_argument("--main-checkpoint", required=True, type=Path)
    parser.add_argument("--vae-config", required=True, type=Path)
    parser.add_argument("--vae-checkpoint", required=True, type=Path)
    parser.add_argument("--environment-report", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--seed", required=True, type=_nonnegative_integer)
    parser.add_argument("--source-revision", required=True, type=_git_sha_argument)
    parser.add_argument("--asset-revision", required=True, type=_git_sha_argument)
    parser.add_argument(
        "--model-config-sha256", required=True, type=_sha256_argument
    )
    parser.add_argument(
        "--main-checkpoint-sha256", required=True, type=_sha256_argument
    )
    parser.add_argument("--vae-config-sha256", required=True, type=_sha256_argument)
    parser.add_argument(
        "--vae-checkpoint-sha256", required=True, type=_sha256_argument
    )
    parser.add_argument(
        "--environment-report-sha256", required=True, type=_sha256_argument
    )
    parser.add_argument(
        "--confirm-aws-gpu-execution",
        action="store_true",
        help=(
            "Required acknowledgement. The command still fails unless PyTorch "
            "reports a real CUDA device."
        ),
    )


def build_rollout_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run and seal one formal MineWorld Step 2.6 rollout."
    )
    _add_common_arguments(parser)
    parser.add_argument("--input-mp4", required=True, type=Path)
    parser.add_argument("--input-jsonl", required=True, type=Path)
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument(
        "--context-frames",
        type=int,
        default=8,
        choices=range(1, CONTEXT_PAIRS + 1),
    )
    return parser


def build_architecture_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect and assert the loaded MineWorld architecture."
    )
    _add_common_arguments(parser)
    return parser


def build_teacher_forced_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the teacher-forced hook and repeatability gate."
    )
    _add_common_arguments(parser)
    parser.add_argument("--input-id", required=True)
    parser.add_argument(
        "--input-kind", required=True, choices=("accepted", "synthetic")
    )
    parser.add_argument("--input-mp4", required=True, type=Path)
    parser.add_argument("--input-jsonl", required=True, type=Path)
    parser.add_argument("--input-mp4-sha256", required=True, type=_sha256_argument)
    parser.add_argument(
        "--input-jsonl-sha256", required=True, type=_sha256_argument
    )
    parser.add_argument("--repeats", type=_at_least_two, default=2)
    parser.add_argument(
        "--precision", choices=("float16", "bfloat16"), default="float16"
    )
    return parser


def _run_git(arguments: Sequence[str], root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise EvidenceValidationError(
            "git_inspection_failed",
            (result.stderr or result.stdout or "git command failed").strip(),
        )
    return result.stdout.strip()


def _prepare_output_directory(path: Path) -> Path:
    resolved = path.resolve()
    if resolved.exists():
        if not resolved.is_dir():
            raise EvidenceValidationError(
                "invalid_output_directory", "Output path is not a directory."
            )
        if any(resolved.iterdir()):
            raise EvidenceValidationError(
                "nonempty_output_directory",
                "Output directory must be absent or empty to prevent in-place mutation.",
            )
    else:
        resolved.mkdir(parents=True)
    return resolved


def _verify_file(path: Path, expected_sha256: str, role: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_file():
        raise EvidenceValidationError(
            "missing_input", f"{role} does not exist: {resolved}"
        )
    actual = sha256_file(resolved)
    if actual != expected_sha256:
        raise EvidenceValidationError(
            "input_hash_mismatch",
            f"{role} SHA-256 mismatch: expected {expected_sha256}, observed {actual}.",
        )
    return resolved


def _require_cuda(confirmed: bool):
    if not confirmed:
        raise EvidenceValidationError(
            "gpu_execution_not_confirmed",
            "--confirm-aws-gpu-execution is required.",
        )
    try:
        import torch
    except Exception as exc:
        raise EvidenceValidationError(
            "pytorch_import_failed", f"Could not import PyTorch: {exc}"
        ) from exc
    if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
        raise EvidenceValidationError(
            "cuda_required",
            "A real CUDA-capable PyTorch runtime is required; CPU execution is refused.",
        )
    return torch


def _preflight(args: argparse.Namespace, command: Sequence[str]) -> dict[str, Any]:
    if not isinstance(args.run_id, str) or not args.run_id.strip():
        raise EvidenceValidationError(
            "invalid_run_id", "run_id must be a non-empty explicit identity."
        )
    source_root = args.mineworld_source_root.resolve()
    if not source_root.is_dir():
        raise EvidenceValidationError(
            "missing_source_root", f"MineWorld source root is absent: {source_root}"
        )
    if args.source_revision != PINNED_SOURCE_REVISION:
        raise EvidenceValidationError(
            "unpinned_source_revision",
            f"source_revision must equal {PINNED_SOURCE_REVISION}.",
        )
    if args.asset_revision != PINNED_ASSET_REVISION:
        raise EvidenceValidationError(
            "unpinned_asset_revision",
            f"asset_revision must equal {PINNED_ASSET_REVISION}.",
        )
    pinned_asset_hashes = {
        "main checkpoint": (
            args.main_checkpoint_sha256,
            PINNED_MAIN_CHECKPOINT_SHA256,
        ),
        "VAE configuration": (
            args.vae_config_sha256,
            PINNED_VAE_CONFIG_SHA256,
        ),
        "VAE checkpoint": (
            args.vae_checkpoint_sha256,
            PINNED_VAE_CHECKPOINT_SHA256,
        ),
    }
    for role, (observed, expected) in pinned_asset_hashes.items():
        if observed != expected:
            raise EvidenceValidationError(
                "unpinned_asset_hash",
                f"{role} SHA-256 must equal the frozen asset lock.",
            )
    source_head = _run_git(["rev-parse", "HEAD"], source_root)
    if source_head != args.source_revision:
        raise EvidenceValidationError(
            "source_revision_mismatch",
            f"Expected source {args.source_revision}, observed {source_head}.",
        )
    if _run_git(["status", "--porcelain"], source_root):
        raise EvidenceValidationError(
            "dirty_source_checkout",
            "External MineWorld checkout must be clean.",
        )

    mineocclude_sha = _run_git(["rev-parse", "HEAD"], REPO_ROOT)
    mineocclude_dirty = bool(_run_git(["status", "--porcelain"], REPO_ROOT))
    if mineocclude_dirty:
        raise EvidenceValidationError(
            "dirty_mineocclude_checkout",
            "Official runtime evidence requires committed MineOcclude tooling.",
        )

    expected_model_config = (source_root / "configs" / "700M_16f.yaml").resolve()
    if args.model_config.resolve() != expected_model_config:
        raise EvidenceValidationError(
            "unpinned_model_configuration",
            f"model configuration must be {expected_model_config}.",
        )
    model_config = _verify_file(
        expected_model_config,
        args.model_config_sha256,
        "model configuration",
    )
    main_checkpoint = _verify_file(
        args.main_checkpoint, args.main_checkpoint_sha256, "main checkpoint"
    )
    vae_config = _verify_file(
        args.vae_config, args.vae_config_sha256, "VAE configuration"
    )
    vae_checkpoint = _verify_file(
        args.vae_checkpoint, args.vae_checkpoint_sha256, "VAE checkpoint"
    )
    environment_report = _verify_file(
        args.environment_report,
        args.environment_report_sha256,
        "environment report",
    )
    return {
        "source_root": source_root,
        "model_config": model_config,
        "main_checkpoint": main_checkpoint,
        "vae_config": vae_config,
        "vae_checkpoint": vae_checkpoint,
        "environment_report": environment_report,
        "identity": {
            "run_id": args.run_id,
            "seed": args.seed,
            "source_revision": args.source_revision,
            "asset_revision": args.asset_revision,
            "mineocclude_code_sha": mineocclude_sha,
            "mineocclude_dirty": False,
            "model_config_sha256": args.model_config_sha256,
            "main_checkpoint_sha256": args.main_checkpoint_sha256,
            "vae_config_sha256": args.vae_config_sha256,
            "vae_checkpoint_sha256": args.vae_checkpoint_sha256,
            "environment_report_sha256": args.environment_report_sha256,
            "command": list(command),
        },
    }


def _patch_config_paths(config: Any, prepared: Mapping[str, Any]) -> None:
    params = config.model.params.tokenizer_config.params
    params.config_path = str(prepared["vae_config"])
    params.ckpt_path = str(prepared["vae_checkpoint"])


def _seed_everything(torch: Any, seed: int) -> None:
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except Exception as exc:
        raise EvidenceValidationError(
            "numpy_seed_failed", f"Could not seed NumPy: {exc}"
        ) from exc
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def _gpu_record(torch: Any, device_index: int = 0) -> dict[str, Any]:
    properties = torch.cuda.get_device_properties(device_index)
    return {
        "name": properties.name,
        "device_index": device_index,
        "total_memory_bytes": int(properties.total_memory),
        "capability": f"{properties.major}.{properties.minor}",
    }


def _input_artifacts(prepared: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        artifact_record("model_config", prepared["model_config"]),
        artifact_record("main_checkpoint", prepared["main_checkpoint"]),
        artifact_record("vae_config", prepared["vae_config"]),
        artifact_record("vae_checkpoint", prepared["vae_checkpoint"]),
        artifact_record("environment_report", prepared["environment_report"]),
    ]


def _ffprobe(path: Path, executable: str) -> dict[str, Any]:
    if shutil.which(executable) is None:
        raise EvidenceValidationError(
            "ffprobe_missing", f"ffprobe executable not found: {executable}"
        )
    command = [
        executable,
        "-v",
        "error",
        "-count_frames",
        "-select_streams",
        "v:0",
        "-show_entries",
        (
            "stream=width,height,r_frame_rate,avg_frame_rate,"
            "duration,nb_frames,nb_read_frames"
        ),
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise EvidenceValidationError(
            "ffprobe_failed",
            (result.stderr or result.stdout or "ffprobe failed").strip(),
        )
    return parse_ffprobe_output(result.stdout)


def execute_rollout(
    args: argparse.Namespace,
    *,
    command: Sequence[str],
) -> Path:
    """Execute and seal exactly one generated-frame rollout on CUDA."""

    output_dir = _prepare_output_directory(args.output_dir)
    raw_log = output_dir / "raw_stdout_stderr.log"
    state: dict[str, Any] = {}
    with _raw_log(raw_log):
        print("=== PERSON A PHASE 2.6 FORMAL ROLLOUT ===")
        prepared = _preflight(args, command)
        torch = _require_cuda(args.confirm_aws_gpu_execution)
        input_mp4 = args.input_mp4.resolve()
        input_jsonl = args.input_jsonl.resolve()
        if not input_mp4.is_file() or not input_jsonl.is_file():
            raise EvidenceValidationError(
                "missing_rollout_input", "Input MP4 and JSONL must both exist."
            )
        if (
            input_mp4.parent != input_jsonl.parent
            or input_mp4.stem != input_jsonl.stem
        ):
            raise EvidenceValidationError(
                "unpaired_rollout_input",
                "Input MP4 and JSONL must share a directory and basename.",
            )
        if input_mp4.suffix.lower() != ".mp4" or input_jsonl.suffix.lower() != ".jsonl":
            raise EvidenceValidationError(
                "invalid_rollout_input_extension",
                "Formal input extensions must be .mp4 and .jsonl.",
            )
        _seed_everything(torch, args.seed)
        torch.cuda.set_device(0)
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(0)
        total_start = time.perf_counter()

        with _external_source_imports(prepared["source_root"]):
            OmegaConf = importlib.import_module("omegaconf").OmegaConf
            upstream_utils = importlib.import_module("utils")
            upstream_inference = importlib.import_module("inference")
            config = OmegaConf.load(str(prepared["model_config"]))
            _patch_config_paths(config, prepared)

            load_start = time.perf_counter()
            model = upstream_utils.load_model(
                config,
                str(prepared["main_checkpoint"]),
                gpu=True,
                eval_mode=True,
            )
            torch.cuda.synchronize()
            initialization_seconds = time.perf_counter() - load_start
            if model.training:
                raise EvidenceValidationError(
                    "model_not_eval", "Official loader did not leave the model in eval mode."
                )

            upstream_inference.output_path = output_dir
            generation_args = SimpleNamespace(
                data_root=str(input_mp4.parent),
                frames=1,
                demo_num=args.context_frames,
                window_size=2,
                accelerate_algo="naive",
                fps=6,
                top_k=1,
                top_p=None,
            )
            generation_start = time.perf_counter()
            result = upstream_inference.lvm_generate(
                generation_args, model, output_dir, input_mp4.name
            )
            torch.cuda.synchronize()
            first_frame_seconds = time.perf_counter() - generation_start
            if not isinstance(result, Mapping) or result.get("token_num") != VISUAL_TOKENS:
                raise EvidenceValidationError(
                    "unexpected_generation_result",
                    "Exactly 336 generated visual tokens were required.",
                )
            kernel_seconds = result.get("time_costed")
            if (
                not isinstance(kernel_seconds, (int, float))
                or float(kernel_seconds) <= 0
            ):
                raise EvidenceValidationError(
                    "missing_generation_timing",
                    "Upstream generation did not report a positive kernel time.",
                )

        generated_video = output_dir / input_mp4.name
        paired_metadata = output_dir / input_jsonl.name
        if not generated_video.is_file() or not paired_metadata.is_file():
            raise EvidenceValidationError(
                "missing_rollout_output",
                "Upstream generation did not create both MP4 and paired metadata.",
            )
        probe = _ffprobe(generated_video, args.ffprobe)
        if probe["decoded_frames"] != 1:
            raise EvidenceValidationError(
                "unbounded_generation",
                "Formal smoke rollout must decode exactly one generated frame.",
            )
        total_seconds = time.perf_counter() - total_start
        state = {
            "prepared": prepared,
            "input_mp4": input_mp4,
            "input_jsonl": input_jsonl,
            "generated_video": generated_video,
            "paired_metadata": paired_metadata,
            "ffprobe": probe,
            "runtime": {
                "timings": {
                    "model_initialization_seconds": initialization_seconds,
                    "first_generated_frame_seconds": first_frame_seconds,
                    "generation_kernel_seconds": float(kernel_seconds),
                    "total_runtime_seconds": total_seconds,
                },
                "process_exit_status": 0,
                "peak_cuda_allocated_bytes": int(torch.cuda.max_memory_allocated(0)),
                "peak_cuda_reserved_bytes": int(torch.cuda.max_memory_reserved(0)),
                "gpu": _gpu_record(torch),
                "torch_version": str(torch.__version__),
                "cuda_version": str(torch.version.cuda),
                "generated_frames_requested": 1,
            },
        }
        print(json.dumps(state["runtime"], indent=2, sort_keys=True))
        print(json.dumps(probe, indent=2, sort_keys=True))
        print("PASS: generated video decoded and formal runtime fields captured.")

    prepared = state["prepared"]
    inputs = _input_artifacts(prepared)
    inputs.extend(
        [
            artifact_record("input_mp4", state["input_mp4"]),
            artifact_record("input_jsonl", state["input_jsonl"]),
        ]
    )
    outputs = [
        artifact_record("generated_video", state["generated_video"]),
        artifact_record("paired_metadata", state["paired_metadata"]),
        artifact_record("raw_stdout_stderr", raw_log),
    ]
    document = {
        "schema_version": SCHEMA_VERSION,
        "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
        "evidence_type": ROLLOUT_EVIDENCE_TYPE,
        "status": "completed",
        "identity": prepared["identity"],
        "inputs": inputs,
        "runtime": state["runtime"],
        "outputs": outputs,
        "ffprobe": state["ffprobe"],
    }
    manifest_path = output_dir / "run_manifest.json"
    sealed = write_sealed_document(manifest_path, document)
    result = validate_rollout_manifest(
        sealed,
        verify_output_bytes=True,
        literal_bytes=manifest_path.read_bytes(),
    )
    if not result.accepted:
        raise EvidenceValidationError(
            "manifest_validation_failed",
            "; ".join(f"{item.code}: {item.message}" for item in result.rejections),
        )
    return manifest_path


def _load_state_dict(path: Path, torch: Any) -> Mapping[str, Any]:
    payload = torch.load(str(path), map_location="cpu", weights_only=False)
    if isinstance(payload, Mapping) and isinstance(payload.get("state_dict"), Mapping):
        return payload["state_dict"]
    if isinstance(payload, Mapping):
        return payload
    raise EvidenceValidationError(
        "invalid_checkpoint_container", f"Checkpoint is not a state dictionary: {path}"
    )


def _load_model_with_key_evidence(
    prepared: Mapping[str, Any],
    torch: Any,
    *,
    precision: str,
) -> tuple[Any, Any, dict[str, list[str]], dict[str, Any]]:
    with _external_source_imports(prepared["source_root"]):
        OmegaConf = importlib.import_module("omegaconf").OmegaConf
        upstream_utils = importlib.import_module("utils")
        config = OmegaConf.load(str(prepared["model_config"]))
        _patch_config_paths(config, prepared)
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(0)
        load_start = time.perf_counter()
        model = upstream_utils.instantiate_from_config(config.model)
        transformer_weights = _load_state_dict(prepared["main_checkpoint"], torch)
        transformer_missing, transformer_unexpected = model.load_state_dict(
            transformer_weights, strict=False
        )
        vae_weights = _load_state_dict(prepared["vae_checkpoint"], torch)
        vae_missing, vae_unexpected = model.tokenizer.load_state_dict(
            vae_weights, strict=False
        )
        model.cuda()
        dtype = torch.float16 if precision == "float16" else torch.bfloat16
        model.to(dtype=dtype)
        model.eval()
        torch.cuda.synchronize()
        load_seconds = time.perf_counter() - load_start
        load_runtime = {
            "seconds": load_seconds,
            "peak_cuda_allocated_bytes": int(torch.cuda.max_memory_allocated(0)),
            "peak_cuda_reserved_bytes": int(torch.cuda.max_memory_reserved(0)),
        }
    return (
        model,
        config,
        {
            "transformer_missing_keys": sorted(transformer_missing),
            "transformer_unexpected_keys": sorted(transformer_unexpected),
            "vae_missing_keys": sorted(vae_missing),
            "vae_unexpected_keys": sorted(vae_unexpected),
        },
        load_runtime,
    )


def _decoder_layers(model: Any, torch: Any) -> tuple[str, list[Any]]:
    candidates: list[tuple[str, list[Any]]] = []
    for name, module in model.named_modules():
        if isinstance(module, torch.nn.ModuleList) and len(module) == EXPECTED_LAYERS:
            children = list(module)
            if children and all("DecoderLayer" in child.__class__.__name__ for child in children):
                candidates.append((name, children))
    if len(candidates) != 1:
        names = [name for name, _ in candidates]
        raise EvidenceValidationError(
            "ambiguous_decoder_path",
            f"Expected one 20-layer decoder ModuleList, found {names!r}.",
        )
    return candidates[0]


def _parameter_distribution(model: Any, attribute: str) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for parameter in model.parameters():
        key = str(getattr(parameter, attribute))
        counts[key] += parameter.numel()
    return dict(sorted(counts.items()))


def _architecture_document(
    prepared: Mapping[str, Any],
    model: Any,
    load_state: Mapping[str, list[str]],
    torch: Any,
) -> dict[str, Any]:
    decoder_path, layers = _decoder_layers(model, torch)
    config = model.config
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.float16):
        test_image = torch.zeros((1, 3, 224, 384), device="cuda")
        visual = model.tokenizer.tokenize_images(test_image)
    with _external_source_imports(prepared["source_root"]):
        MCDataset = importlib.import_module("mcdataset").MCDataset
        action_tokens = MCDataset().action_length
    architecture = {
        "layer_count": len(layers),
        "hidden_size": int(config.hidden_size),
        "intermediate_size": int(config.intermediate_size),
        "vocab_size": int(config.vocab_size),
        "max_position_embeddings": int(config.max_position_embeddings),
        "num_attention_heads": int(config.num_attention_heads),
        "num_key_value_heads": int(config.num_key_value_heads),
        "visual_tokens": int(visual.numel()),
        "action_tokens": int(action_tokens),
        "tokens_per_pair": int(visual.numel()) + int(action_tokens),
        "context_pairs": int(
            config.max_position_embeddings
            // (int(visual.numel()) + int(action_tokens))
        ),
        "decoder_layer_path": decoder_path,
        "model_class": model.__class__.__name__,
        "transformer_class": model.transformer.__class__.__name__,
        "vae_class": model.tokenizer.__class__.__name__,
        "dtype_distribution": _parameter_distribution(model, "dtype"),
        "device_distribution": _parameter_distribution(model, "device"),
        "parameter_counts": {
            "model": sum(parameter.numel() for parameter in model.parameters()),
            "transformer": sum(
                parameter.numel() for parameter in model.transformer.parameters()
            ),
            "vae": sum(parameter.numel() for parameter in model.tokenizer.parameters()),
        },
    }
    module_tree = [
        {
            "name": name,
            "class_name": module.__class__.__name__,
            "direct_parameters": sum(
                parameter.numel() for parameter in module.parameters(recurse=False)
            ),
        }
        for name, module in model.named_modules()
    ]
    return {
        "architecture": architecture,
        "load_state": dict(load_state),
        "module_tree": module_tree,
    }


def execute_architecture(
    args: argparse.Namespace,
    *,
    command: Sequence[str],
) -> Path:
    """Load, inspect, assert, and seal the Step 2.7 architecture report."""

    output_dir = _prepare_output_directory(args.output_dir)
    raw_log = output_dir / "raw_stdout_stderr.log"
    report_path = output_dir / "architecture_report.json"
    with _raw_log(raw_log):
        print("=== PERSON A PHASE 2.7 ARCHITECTURE INSPECTION ===")
        prepared = _preflight(args, command)
        torch = _require_cuda(args.confirm_aws_gpu_execution)
        _seed_everything(torch, args.seed)
        model, _, load_state, load_runtime = _load_model_with_key_evidence(
            prepared, torch, precision="float16"
        )
        payload = _architecture_document(prepared, model, load_state, torch)
        document = {
            "schema_version": SCHEMA_VERSION,
            "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
            "evidence_type": ARCHITECTURE_EVIDENCE_TYPE,
            "status": "completed",
            "identity": prepared["identity"],
            **payload,
            "cuda_memory": {
                "peak_allocated_bytes": load_runtime[
                    "peak_cuda_allocated_bytes"
                ],
                "peak_reserved_bytes": load_runtime["peak_cuda_reserved_bytes"],
            },
        }
        sealed = seal_document(document)
        validation = validate_architecture_report(sealed)
        if not validation.accepted:
            failed_document = dict(document)
            failed_document["status"] = "failed"
            write_sealed_document(report_path, failed_document)
            raise EvidenceValidationError(
                "architecture_validation_failed",
                "; ".join(
                    f"{item.code} at {item.path}: {item.message}"
                    for item in validation.rejections
                ),
            )
        write_sealed_document(report_path, document)
        print(json.dumps(payload["architecture"], indent=2, sort_keys=True))
        print("PASS: loaded architecture and state-dictionary evidence validated.")
    return report_path


def _cpu_peak_rss_bytes() -> int:
    try:
        import resource

        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except (ImportError, AttributeError, ValueError) as exc:
        raise EvidenceValidationError(
            "cpu_memory_unavailable",
            f"Could not obtain process peak RSS: {exc}",
        ) from exc
    # Linux reports KiB; macOS reports bytes.  The official AWS path is Linux.
    return value * 1024 if sys.platform.startswith("linux") else value


def _tensor_sha256(tensor: Any) -> str:
    cpu = tensor.detach().contiguous().cpu()
    # NumPy cannot expose bfloat16 directly.  Reinterpret the contiguous bytes.
    byte_view = cpu.view(dtype=importlib.import_module("torch").uint8)
    return sha256_bytes(byte_view.numpy().tobytes())


def _tensor_summary(tensor: Any) -> dict[str, float]:
    numeric = tensor.detach().float()
    return {
        "min": float(numeric.min().item()),
        "max": float(numeric.max().item()),
        "mean": float(numeric.mean().item()),
        "std": float(numeric.std(unbiased=False).item()),
    }


def _build_teacher_input(
    prepared: Mapping[str, Any],
    args: argparse.Namespace,
    model: Any,
    torch: Any,
    precision: str,
) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    input_mp4 = _verify_file(
        args.input_mp4, args.input_mp4_sha256, "teacher-forced MP4"
    )
    input_jsonl = _verify_file(
        args.input_jsonl, args.input_jsonl_sha256, "teacher-forced JSONL"
    )
    if input_mp4.parent != input_jsonl.parent or input_mp4.stem != input_jsonl.stem:
        raise EvidenceValidationError(
            "unpaired_teacher_input",
            "Teacher-forced MP4 and JSONL must share a directory and basename.",
        )
    cv2 = importlib.import_module("cv2")
    np = importlib.import_module("numpy")
    capture = cv2.VideoCapture(str(input_mp4))
    frames = []
    try:
        for frame_index in range(CONTEXT_PAIRS):
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = capture.read()
            if not ok:
                raise EvidenceValidationError(
                    "teacher_frame_decode_failed",
                    f"Could not decode required frame {frame_index}.",
                )
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame = cv2.resize(frame, (384, 224), interpolation=cv2.INTER_LINEAR)
            frames.append(torch.from_numpy(np.asarray(frame, dtype=np.uint8)))
    finally:
        capture.release()
    frame_tensor = torch.stack(frames).to("cuda")
    frame_tensor = frame_tensor.permute(0, 3, 1, 2).float() / 255.0
    frame_tensor = (frame_tensor - 0.5) / 0.5
    dtype = torch.float16 if precision == "float16" else torch.bfloat16
    with torch.no_grad(), torch.autocast("cuda", dtype=dtype):
        visual = model.tokenizer.tokenize_images(frame_tensor)
    visual = visual.reshape(CONTEXT_PAIRS, -1)
    if list(visual.shape) != [CONTEXT_PAIRS, VISUAL_TOKENS]:
        raise EvidenceValidationError(
            "visual_token_shape_mismatch",
            f"Expected [16, 336] visual tokens, observed {list(visual.shape)}.",
        )

    with _external_source_imports(prepared["source_root"]):
        MCDataset = importlib.import_module("mcdataset").MCDataset
        dataset = MCDataset()
        json_rows = dataset.read_jsonl(str(input_jsonl))
    if not isinstance(json_rows, list):
        raise EvidenceValidationError(
            "teacher_actions_decode_failed",
            "Teacher-forced JSONL did not decode to a row list.",
        )
    if len(json_rows) < CONTEXT_PAIRS:
        raise EvidenceValidationError(
            "insufficient_teacher_actions",
            "Teacher-forced JSONL has fewer than 16 records.",
        )
    action_rows = []
    for index in range(CONTEXT_PAIRS):
        action, _ = dataset.json_action_to_env_action(json_rows[index])
        encoded = dataset.get_action_index_from_actiondict(
            action, action_vocab_offset=8192
        )
        if len(encoded) != ACTION_TOKENS:
            raise EvidenceValidationError(
                "action_token_shape_mismatch",
                f"Action row {index} did not produce 11 tokens.",
            )
        action_rows.append(encoded)
    actions = torch.tensor(action_rows, dtype=torch.long, device="cuda")
    pairs = [
        torch.cat([visual[index], actions[index]], dim=0)
        for index in range(CONTEXT_PAIRS)
    ]
    input_ids = torch.cat(pairs, dim=0).reshape(1, -1)
    if list(input_ids.shape) != [1, SEQUENCE_LENGTH]:
        raise EvidenceValidationError(
            "teacher_sequence_shape_mismatch",
            f"Expected [1, 5552], observed {list(input_ids.shape)}.",
        )
    layout = expected_teacher_token_layout()
    input_record = {
        "input_id": args.input_id,
        "input_kind": args.input_kind,
        "mp4_sha256": args.input_mp4_sha256,
        "jsonl_sha256": args.input_jsonl_sha256,
        "frame_indices": list(range(CONTEXT_PAIRS)),
    }
    return input_ids, input_record, layout


def execute_teacher_forced(
    args: argparse.Namespace,
    *,
    command: Sequence[str],
) -> Path:
    """Execute the combined Step 2.8-2.9 hook/repeatability gate on CUDA."""

    if args.repeats < 2:
        raise EvidenceValidationError(
            "invalid_repeat_count", "--repeats must be at least 2."
        )
    output_dir = _prepare_output_directory(args.output_dir)
    raw_log = output_dir / "raw_stdout_stderr.log"
    report_path = output_dir / "teacher_forced_report.json"
    with _raw_log(raw_log):
        print("=== PERSON A PHASE 2.8-2.9 TEACHER-FORCED GATE ===")
        prepared = _preflight(args, command)
        torch = _require_cuda(args.confirm_aws_gpu_execution)
        _seed_everything(torch, args.seed)
        model, _, load_state, load_runtime = _load_model_with_key_evidence(
            prepared, torch, precision=args.precision
        )
        mismatches = {
            field: values for field, values in load_state.items() if values
        }
        if mismatches:
            raise EvidenceValidationError(
                "state_dict_mismatch",
                "Teacher-forced execution refused because load-key mismatches remain: "
                + ", ".join(sorted(mismatches)),
            )
        if model.training:
            raise EvidenceValidationError(
                "model_not_eval", "Teacher-forced model must be in eval mode."
            )
        architecture_payload = _architecture_document(
            prepared,
            model,
            load_state,
            torch,
        )
        architecture_rejections = validate_architecture_facts(
            architecture_payload["architecture"]
        )
        if architecture_rejections:
            raise EvidenceValidationError(
                "architecture_validation_failed",
                "; ".join(
                    f"{item.code} at {item.path}: {item.message}"
                    for item in architecture_rejections
                ),
            )
        input_ids, input_record, layout = _build_teacher_input(
            prepared, args, model, torch, args.precision
        )
        decoder_path, layers = _decoder_layers(model, torch)
        named_modules = dict(model.named_modules())
        layer_names = [f"{decoder_path}.{index}" for index in range(len(layers))]
        if len(layer_names) != len(set(layer_names)) or any(
            name not in named_modules for name in layer_names
        ):
            raise EvidenceValidationError(
                "hook_discovery_failed",
                "Decoder hook names are missing or duplicated in named_modules().",
            )

        positions = torch.arange(SEQUENCE_LENGTH, device="cuda")
        positions_hash = layout["positions_sha256"]
        current_repeat = {"index": -1}
        captured: dict[tuple[int, int], dict[str, Any]] = {}
        handles: list[tuple[Any, Any]] = []

        def make_hook(layer_index: int):
            def hook(_module: Any, _inputs: Any, output: Any) -> None:
                tensor = output[0] if isinstance(output, tuple) else output
                if not isinstance(tensor, torch.Tensor):
                    raise EvidenceValidationError(
                        "non_tensor_hook_output",
                        f"Layer {layer_index} did not emit a tensor.",
                    )
                key = (current_repeat["index"], layer_index)
                if key in captured:
                    raise EvidenceValidationError(
                        "duplicate_hook", f"Duplicate hook emission for {key}."
                    )
                captured[key] = {
                    "tensor": tensor.detach().cpu(),
                    "shape": list(tensor.shape),
                    "dtype": str(tensor.dtype),
                    "device": str(tensor.device),
                }

            return hook

        hooks_removed = False
        forward_seconds: list[float] = []
        try:
            for index, name in enumerate(layer_names):
                module = named_modules[name]
                handle = module.register_forward_hook(make_hook(index))
                handles.append((module, handle))
            dtype = (
                torch.float16 if args.precision == "float16" else torch.bfloat16
            )
            for repeat_index in range(args.repeats):
                current_repeat["index"] = repeat_index
                model.transformer.refresh_kvcache()
                torch.cuda.synchronize()
                start = time.perf_counter()
                with torch.no_grad(), torch.autocast("cuda", dtype=dtype):
                    _ = model.transformer(
                        input_ids=input_ids,
                        position_ids=positions,
                    )
                torch.cuda.synchronize()
                forward_seconds.append(time.perf_counter() - start)
                observed = {
                    layer
                    for repeat, layer in captured
                    if repeat == repeat_index
                }
                if observed != set(range(EXPECTED_LAYERS)):
                    raise EvidenceValidationError(
                        "incomplete_hook_coverage",
                        f"Repeat {repeat_index} observed layers {sorted(observed)}.",
                    )
        finally:
            for module, handle in reversed(handles):
                handle.remove()
            hooks_removed = all(
                handle.id not in module._forward_hooks for module, handle in handles
            )
        if not hooks_removed:
            raise EvidenceValidationError(
                "hook_cleanup_failure", "One or more temporary hooks remain attached."
            )

        hook_records: list[dict[str, Any]] = []
        for repeat_index in range(args.repeats):
            for layer_index, module_name in enumerate(layer_names):
                capture = captured[(repeat_index, layer_index)]
                tensor = capture["tensor"]
                hook_records.append(
                    {
                        "repeat_index": repeat_index,
                        "layer_index": layer_index,
                        "module_name": module_name,
                        "shape": capture["shape"],
                        "dtype": capture["dtype"],
                        "device": capture["device"],
                        "token_positions_sha256": positions_hash,
                        "output_sha256": _tensor_sha256(tensor),
                        "summary": _tensor_summary(tensor),
                    }
                )

        repeatability = []
        for layer_index in range(EXPECTED_LAYERS):
            reference = captured[(0, layer_index)]["tensor"]
            allclose = True
            maximum = 0.0
            for repeat_index in range(1, args.repeats):
                candidate = captured[(repeat_index, layer_index)]["tensor"]
                difference = float(
                    (reference.float() - candidate.float()).abs().max().item()
                )
                maximum = max(maximum, difference)
                allclose = allclose and bool(
                    torch.allclose(reference, candidate, rtol=1e-3, atol=1e-3)
                )
            repeatability.append(
                {
                    "layer_index": layer_index,
                    "allclose": allclose,
                    "max_absolute_difference": maximum,
                    "rtol": 1e-3,
                    "atol": 1e-3,
                }
            )

        document = {
            "schema_version": SCHEMA_VERSION,
            "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
            "evidence_type": TEACHER_FORCED_EVIDENCE_TYPE,
            "status": "completed",
            "identity": prepared["identity"],
            "execution": {
                "repeats": args.repeats,
                "precision": args.precision,
                "batch_size": 1,
                "eval_mode": not model.training,
                "no_grad": True,
            },
            "input": input_record,
            "token_layout": layout,
            "hooks": hook_records,
            "repeatability": repeatability,
            "timing": {
                "load_seconds": load_runtime["seconds"],
                "forward_seconds": forward_seconds,
            },
            "memory": {
                "cpu_peak_rss_bytes": _cpu_peak_rss_bytes(),
                "peak_cuda_allocated_bytes": int(torch.cuda.max_memory_allocated(0)),
                "peak_cuda_reserved_bytes": int(torch.cuda.max_memory_reserved(0)),
            },
            "cleanup": {"hooks_removed": hooks_removed},
        }
        sealed = seal_document(document)
        validation = validate_teacher_forced_report(sealed)
        if not validation.accepted:
            failed_document = dict(document)
            failed_document["status"] = "failed"
            write_sealed_document(report_path, failed_document)
            raise EvidenceValidationError(
                "teacher_forced_validation_failed",
                "; ".join(
                    f"{item.code} at {item.path}: {item.message}"
                    for item in validation.rejections
                ),
            )
        write_sealed_document(report_path, document)
        print(
            json.dumps(
                {
                    "decoder_layer_path": decoder_path,
                    "repeats": args.repeats,
                    "forward_seconds": forward_seconds,
                    "hooks_removed": hooks_removed,
                },
                indent=2,
                sort_keys=True,
            )
        )
        print("PASS: teacher-forced hooks and repeatability validated.")
    return report_path


def _run_main(
    parser: argparse.ArgumentParser,
    executor: Any,
    argv: Sequence[str] | None,
    program_name: str,
) -> int:
    args = parser.parse_args(argv)
    program_path = Path(program_name)
    if not program_path.is_absolute():
        program_path = REPO_ROOT / program_path
    command = [
        sys.executable,
        str(program_path.resolve()),
        *(list(argv) if argv is not None else sys.argv[1:]),
    ]
    try:
        output = executor(args, command=command)
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"EVIDENCE: {output}")
    return 0


def rollout_main(argv: Sequence[str] | None = None) -> int:
    return _run_main(
        build_rollout_parser(),
        execute_rollout,
        argv,
        "scripts/run_phase2_rollout.py",
    )


def architecture_main(argv: Sequence[str] | None = None) -> int:
    return _run_main(
        build_architecture_parser(),
        execute_architecture,
        argv,
        "scripts/inspect_phase2_architecture.py",
    )


def teacher_forced_main(argv: Sequence[str] | None = None) -> int:
    return _run_main(
        build_teacher_forced_parser(),
        execute_teacher_forced,
        argv,
        "scripts/run_phase2_teacher_forced.py",
    )
