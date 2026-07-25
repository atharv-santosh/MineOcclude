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
import math
import numbers
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
    ACTION_COMPATIBILITY_SERIALIZATION,
    ACTION_COMPATIBILITY_TRANSFORMATION,
    ACTION_COMPATIBILITY_VERSION,
    ARCHITECTURE_EVIDENCE_TYPE,
    EVIDENCE_SCHEMA_VERSION,
    ROLLOUT_EVIDENCE_TYPE,
    TEACHER_FORCED_EVIDENCE_TYPE,
    VIDEO_PREPROCESSING_NORMALIZATION,
    VIDEO_PREPROCESSING_SOURCE,
    VIDEO_PREPROCESSING_TRANSFORMATION,
    VIDEO_PREPROCESSING_VERSION,
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
PINNED_INPUT_JSONL_SIZE_BYTES = 15_326_380
PINNED_INPUT_JSONL_SHA256 = (
    "0029daf06496bb974305431a20e8c9d419791f362098bf9d57ee8b8e0f036f9b"
)
PINNED_INPUT_MP4_SIZE_BYTES = 124_782_221
PINNED_INPUT_MP4_SHA256 = (
    "b546e7657505004223742e2174e01d0b6a19091de7ee39a2f213bcf003c243de"
)
PINNED_INPUT_VIDEO_WIDTH = 640
PINNED_INPUT_VIDEO_HEIGHT = 360
PINNED_INPUT_VIDEO_FRAMES = 4_152
PINNED_PROCESSED_VIDEO_WIDTH = 384
PINNED_PROCESSED_VIDEO_HEIGHT = 224
PINNED_MAX_POSITION_EMBEDDINGS = 5_552
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


def _parse_original_action_row(line: str, row_index: int) -> dict[str, Any]:
    """Parse one canonical action row strictly as JSON, never as an expression."""

    def reject_constant(value: str) -> None:
        raise ValueError(f"Non-standard JSON numeric constant: {value}")

    try:
        value = json.loads(line, parse_constant=reject_constant)
    except (json.JSONDecodeError, ValueError) as exc:
        raise EvidenceValidationError(
            "malformed_action_json",
            f"Action row {row_index} is not strict finite JSON: {exc}",
            f"$.rows[{row_index}]",
        ) from exc
    if not isinstance(value, dict):
        raise EvidenceValidationError(
            "invalid_action_row",
            "Every nonempty action row must decode to an object.",
            f"$.rows[{row_index}]",
        )
    return value


def _validate_raw_action_fields(
    row: Mapping[str, Any],
    row_index: int,
    *,
    keyboard_mapping: Mapping[str, str],
) -> None:
    """Validate exactly the raw fields consumed by pinned MCDataset."""

    path = f"$.rows[{row_index}]"
    keyboard = row.get("keyboard")
    mouse = row.get("mouse")
    if not isinstance(keyboard, Mapping):
        raise EvidenceValidationError(
            "invalid_keyboard_action",
            "keyboard must be an object.",
            f"{path}.keyboard",
        )
    if not isinstance(mouse, Mapping):
        raise EvidenceValidationError(
            "invalid_mouse_action",
            "mouse must be an object.",
            f"{path}.mouse",
        )

    keys = keyboard.get("keys")
    if not isinstance(keys, list):
        raise EvidenceValidationError(
            "invalid_keyboard_keys",
            "keyboard.keys must be a list.",
            f"{path}.keyboard.keys",
        )
    if len(keys) != len(set(map(repr, keys))):
        raise EvidenceValidationError(
            "duplicate_keyboard_key",
            "keyboard.keys must not contain duplicate entries.",
            f"{path}.keyboard.keys",
        )
    for key_index, key in enumerate(keys):
        if not isinstance(key, str) or key not in keyboard_mapping:
            raise EvidenceValidationError(
                "unsupported_keyboard_key",
                "Every keyboard key must be a pinned MCDataset mapping key.",
                f"{path}.keyboard.keys[{key_index}]",
            )

    for field in ("dy", "dx"):
        value = mouse.get(field)
        if (
            not isinstance(value, numbers.Real)
            or isinstance(value, bool)
            or not math.isfinite(float(value))
        ):
            raise EvidenceValidationError(
                "invalid_camera_value",
                f"mouse.{field} must be a finite real number.",
                f"{path}.mouse.{field}",
            )

    buttons = mouse.get("buttons")
    if not isinstance(buttons, list):
        raise EvidenceValidationError(
            "invalid_mouse_buttons",
            "mouse.buttons must be a list.",
            f"{path}.mouse.buttons",
        )
    if len(buttons) != len(set(map(repr, buttons))):
        raise EvidenceValidationError(
            "duplicate_mouse_button",
            "mouse.buttons must not contain duplicate entries.",
            f"{path}.mouse.buttons",
        )
    for button_index, button in enumerate(buttons):
        if (
            not isinstance(button, int)
            or isinstance(button, bool)
            or button not in {0, 1, 2}
        ):
            raise EvidenceValidationError(
                "invalid_mouse_button",
                "Mouse buttons must be integer values from the pinned set {0,1,2}.",
                f"{path}.mouse.buttons[{button_index}]",
            )


def _normalize_flat_action(
    value: Any,
    row_index: int,
    *,
    required_action_keys: Sequence[str],
) -> dict[str, Any]:
    """Validate and reduce pinned MCDataset output to safe literal primitives."""

    path = f"$.rows[{row_index}]"
    if not isinstance(value, Mapping):
        raise EvidenceValidationError(
            "invalid_normalized_action",
            "Pinned MCDataset must return an action object.",
            path,
        )
    required = set(required_action_keys)
    if set(value) != required:
        missing = sorted(required - set(value))
        unknown = sorted(set(value) - required)
        raise EvidenceValidationError(
            "incomplete_normalized_action",
            f"Normalized action keys differ; missing={missing}, unknown={unknown}.",
            path,
        )
    camera = value.get("camera")
    if hasattr(camera, "tolist"):
        camera = camera.tolist()
    if (
        not isinstance(camera, (list, tuple))
        or isinstance(camera, (str, bytes))
        or len(camera) != 2
    ):
        raise EvidenceValidationError(
            "invalid_camera",
            "Normalized camera must contain exactly two values.",
            f"{path}.camera",
        )
    normalized_camera: list[int | float] = []
    for camera_index, item in enumerate(camera):
        if (
            not isinstance(item, numbers.Real)
            or isinstance(item, bool)
            or not math.isfinite(float(item))
        ):
            raise EvidenceValidationError(
                "invalid_camera_value",
                "Normalized camera entries must be finite real numbers.",
                f"{path}.camera[{camera_index}]",
            )
        if isinstance(item, numbers.Integral):
            normalized_camera.append(int(item))
        else:
            normalized_camera.append(float(item))

    normalized: dict[str, Any] = {}
    for key in sorted(required):
        if key == "camera":
            normalized[key] = normalized_camera
            continue
        item = value[key]
        if not isinstance(item, int) or isinstance(item, bool) or item not in {0, 1}:
            raise EvidenceValidationError(
                "invalid_binary_action",
                f"{key} must be the integer 0 or 1.",
                f"{path}.{key}",
            )
        normalized[key] = int(item)
    return normalized


def _restricted_eval_derived_action(
    line: str,
    row_index: int,
    *,
    safe_globals: Mapping[str, Any],
) -> dict[str, Any]:
    """Exercise the exact pinned parser on a project-generated safe literal.

    ``line`` is never caller input: it is emitted immediately beforehand from
    the strictly reduced numeric action object above.  Canonical source rows
    are parsed only with :func:`json.loads`.
    """

    try:
        value = eval(
            line.strip(),
            {"__builtins__": None},
            dict(safe_globals),
        )
    except Exception as exc:
        raise EvidenceValidationError(
            "derived_eval_incompatible",
            f"Pinned restricted eval could not parse derived row {row_index}: {exc}",
            f"$.rows[{row_index}]",
        ) from exc
    if not isinstance(value, dict):
        raise EvidenceValidationError(
            "derived_eval_incompatible",
            "Pinned restricted eval did not return an action object.",
            f"$.rows[{row_index}]",
        )
    return value


def convert_action_jsonl_for_pinned_inference(
    original_path: Path,
    derived_path: Path,
    *,
    mcdataset_module: Any,
    asset_revision: str,
    expected_original_size_bytes: int,
    expected_original_sha256: str,
) -> dict[str, Any]:
    """Create one deterministic, order-preserving batch-inference adapter."""

    original = Path(original_path).resolve()
    derived = Path(derived_path).resolve()
    if not original.is_file():
        raise EvidenceValidationError(
            "missing_action_jsonl", f"Original action JSONL is absent: {original}"
        )
    if derived.exists():
        raise EvidenceValidationError(
            "derived_action_exists",
            "Derived action JSONL must not be overwritten or reused.",
        )
    if derived == original:
        raise EvidenceValidationError(
            "invalid_derived_path",
            "Derived action JSONL must be distinct from the canonical input.",
        )
    if derived.is_relative_to(REPO_ROOT):
        raise EvidenceValidationError(
            "derived_action_inside_repository",
            "Derived compatibility JSONL must remain outside the MineOcclude tree.",
        )

    pre_size = original.stat().st_size
    pre_hash = sha256_file(original)
    if pre_size != expected_original_size_bytes or pre_hash != expected_original_sha256:
        raise EvidenceValidationError(
            "original_action_identity_mismatch",
            "Canonical action JSONL size or SHA-256 differs from the accepted lock.",
        )
    if asset_revision != PINNED_ASSET_REVISION:
        raise EvidenceValidationError(
            "unpinned_asset_revision",
            "Canonical action JSONL must use the pinned asset revision.",
        )

    keyboard_mapping = getattr(mcdataset_module, "KEYBOARD_BUTTON_MAPPING", None)
    noop_action = getattr(mcdataset_module, "NOOP_ACTION", None)
    dataset_class = getattr(mcdataset_module, "MCDataset", None)
    array_constructor = getattr(getattr(mcdataset_module, "np", None), "array", None)
    if (
        not isinstance(keyboard_mapping, Mapping)
        or not isinstance(noop_action, Mapping)
        or not callable(dataset_class)
        or not callable(array_constructor)
        or "camera" not in noop_action
    ):
        raise EvidenceValidationError(
            "invalid_pinned_action_contract",
            "Pinned MCDataset action constants or class are missing.",
        )
    required_action_keys = tuple(noop_action)
    if (
        any(not isinstance(key, str) or not key for key in required_action_keys)
        or len(required_action_keys) != len(set(required_action_keys))
        or any(
            not isinstance(source, str)
            or not isinstance(target, str)
            or target not in noop_action
            for source, target in keyboard_mapping.items()
        )
    ):
        raise EvidenceValidationError(
            "invalid_pinned_action_contract",
            "Pinned action keys or keyboard mapping are malformed.",
        )
    try:
        dataset = dataset_class()
    except Exception as exc:
        raise EvidenceValidationError(
            "invalid_pinned_action_contract",
            f"Pinned MCDataset could not be initialized: {exc}",
        ) from exc
    normalizer = getattr(dataset, "json_action_to_env_action", None)
    if not callable(normalizer):
        raise EvidenceValidationError(
            "invalid_pinned_action_contract",
            "Pinned MCDataset action normalizer is absent.",
        )

    try:
        original_bytes = original.read_bytes()
        original_text = original_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvidenceValidationError(
            "invalid_action_encoding", "Canonical action JSONL must be UTF-8."
        ) from exc
    lines = original_text.splitlines()
    if not lines:
        raise EvidenceValidationError(
            "empty_action_jsonl", "Canonical action JSONL contains no rows."
        )

    first_serialized: list[bytes] = []
    second_serialized: list[bytes] = []
    original_canonical_rows: list[bytes] = []
    pair_bindings: list[bytes] = []
    for row_index, line in enumerate(lines):
        if not line.strip():
            raise EvidenceValidationError(
                "blank_action_row",
                "Blank action rows are forbidden; no row may be dropped.",
                f"$.rows[{row_index}]",
            )
        row = _parse_original_action_row(line, row_index)
        _validate_raw_action_fields(
            row,
            row_index,
            keyboard_mapping=keyboard_mapping,
        )
        before = json.dumps(row, sort_keys=True, allow_nan=False)
        try:
            first_result = normalizer(row)
        except Exception as exc:
            raise EvidenceValidationError(
                "action_normalization_failed",
                f"Pinned action normalization failed: {exc}",
                f"$.rows[{row_index}]",
            ) from exc
        if (
            not isinstance(first_result, tuple)
            or len(first_result) != 2
        ):
            raise EvidenceValidationError(
                "invalid_normalizer_result",
                "Pinned action normalizer must return (action, is_null_action).",
                f"$.rows[{row_index}]",
            )
        first = _normalize_flat_action(
            first_result[0],
            row_index,
            required_action_keys=required_action_keys,
        )
        try:
            second_result = normalizer(row)
        except Exception as exc:
            raise EvidenceValidationError(
                "action_normalization_failed",
                f"Repeated pinned action normalization failed: {exc}",
                f"$.rows[{row_index}]",
            ) from exc
        if (
            not isinstance(second_result, tuple)
            or len(second_result) != 2
        ):
            raise EvidenceValidationError(
                "invalid_normalizer_result",
                "Pinned action normalizer must return (action, is_null_action).",
                f"$.rows[{row_index}]",
            )
        second = _normalize_flat_action(
            second_result[0],
            row_index,
            required_action_keys=required_action_keys,
        )
        if json.dumps(row, sort_keys=True, allow_nan=False) != before:
            raise EvidenceValidationError(
                "action_normalizer_mutation",
                "Pinned action normalization mutated the submitted source row.",
                f"$.rows[{row_index}]",
            )
        first_line = (
            json.dumps(
                first,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        second_line = (
            json.dumps(
                second,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        if first_line != second_line:
            raise EvidenceValidationError(
                "nondeterministic_action_conversion",
                "Repeated conversion produced different derived bytes.",
                f"$.rows[{row_index}]",
            )
        parsed = _restricted_eval_derived_action(
            first_line.decode("utf-8"),
            row_index,
            safe_globals={"array": array_constructor},
        )
        if parsed != first:
            raise EvidenceValidationError(
                "derived_eval_mismatch",
                "Pinned restricted eval changed the derived action value.",
                f"$.rows[{row_index}]",
            )
        canonical_source = (
            json.dumps(
                row,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        original_canonical_rows.append(canonical_source)
        pair_bindings.append(
            (
                sha256_bytes(canonical_source)
                + ":"
                + sha256_bytes(first_line)
                + "\n"
            ).encode("ascii")
        )
        first_serialized.append(first_line)
        second_serialized.append(second_line)

    payload = b"".join(first_serialized)
    if payload != b"".join(second_serialized):
        raise EvidenceValidationError(
            "nondeterministic_action_conversion",
            "Repeated complete conversion produced different derived bytes.",
        )
    derived.parent.mkdir(parents=True, exist_ok=False)
    derived.write_bytes(payload)
    derived_size = derived.stat().st_size
    derived_hash = sha256_file(derived)
    if derived_size != len(payload) or derived_hash != sha256_bytes(payload):
        raise EvidenceValidationError(
            "derived_action_integrity_mismatch",
            "Derived JSONL size or SHA-256 differs from generated bytes.",
        )

    post_size = original.stat().st_size
    post_hash = sha256_file(original)
    if post_size != pre_size or post_hash != pre_hash:
        raise EvidenceValidationError(
            "original_action_mutated",
            "Canonical action JSONL changed during compatibility conversion.",
        )
    row_count = len(lines)
    original_sequence_hash = sha256_bytes(b"".join(original_canonical_rows))
    derived_sequence_hash = sha256_bytes(payload)
    return {
        "original": {
            "classification": "original",
            "path": str(original),
            "size_bytes": pre_size,
            "sha256": pre_hash,
            "row_count": row_count,
            "asset_revision": asset_revision,
            "pre_size_bytes": pre_size,
            "pre_sha256": pre_hash,
            "post_size_bytes": post_size,
            "post_sha256": post_hash,
            "row_sequence_sha256": original_sequence_hash,
            "canonical_input": True,
            "unchanged": True,
        },
        "derived": {
            "classification": "derived",
            "path": str(derived),
            "size_bytes": derived_size,
            "sha256": derived_hash,
            "row_count": row_count,
            "transformation_name": ACTION_COMPATIBILITY_TRANSFORMATION,
            "transformation_version": ACTION_COMPATIBILITY_VERSION,
            "deterministic_serialization": ACTION_COMPATIBILITY_SERIALIZATION,
            "parent_original_sha256": pre_hash,
            "parent_row_sequence_sha256": original_sequence_hash,
            "row_sequence_sha256": derived_sequence_hash,
            "source_to_derived_sequence_sha256": sha256_bytes(
                b"".join(pair_bindings)
            ),
            "rows_dropped": 0,
            "rows_added": 0,
            "row_order_preserved": True,
            "storage_classification": "runtime_only_outside_git",
        },
    }


def _assert_action_file_unchanged(record: Mapping[str, Any], role: str) -> None:
    path = Path(record["path"])
    if (
        not path.is_file()
        or path.stat().st_size != record["size_bytes"]
        or sha256_file(path) != record["sha256"]
    ):
        raise EvidenceValidationError(
            f"{role}_action_mutated",
            f"{role} action JSONL changed after compatibility conversion.",
        )


def _generated_action_provenance(
    action_compatibility: Mapping[str, Any],
    paired_metadata: Path,
    generated_video: Path,
) -> dict[str, Any]:
    original = action_compatibility["original"]
    derived = action_compatibility["derived"]
    generated_record = artifact_record("paired_metadata", paired_metadata)
    if (
        generated_record["size_bytes"] != derived["size_bytes"]
        or generated_record["sha256"] != derived["sha256"]
    ):
        raise EvidenceValidationError(
            "generated_metadata_mismatch",
            "Upstream paired metadata is not a byte-identical copy of the derived input.",
        )
    return {
        "classification": "generated",
        "path": generated_record["path"],
        "size_bytes": generated_record["size_bytes"],
        "sha256": generated_record["sha256"],
        "row_count": derived["row_count"],
        "relationship_to_generated_mp4": "paired_action_metadata_for_generated_video",
        "generated_video_sha256": sha256_file(generated_video),
        "relationship_to_original": "derived_from_original_via_compatibility_jsonl",
        "original_jsonl_sha256": original["sha256"],
        "relationship_to_derived": "byte_identical_copy_of_derived_jsonl",
        "derived_jsonl_sha256": derived["sha256"],
        "materialization_method": "project_owned_byte_copy_of_derived_jsonl",
    }


def preprocess_rollout_frame(
    frame: Any,
    *,
    source_frame_index: int,
    cv2_module: Any,
    numpy_module: Any,
) -> tuple[Any, dict[str, Any]]:
    """Apply the exact pinned Gradio frame boundary to one canonical frame."""

    if not isinstance(source_frame_index, int) or isinstance(
        source_frame_index, bool
    ) or source_frame_index < 0:
        raise EvidenceValidationError(
            "invalid_source_frame_index",
            "Source frame index must be a non-negative integer.",
        )
    if not isinstance(frame, numpy_module.ndarray):
        raise EvidenceValidationError(
            "invalid_source_frame_type",
            "Decoded video frame must be a NumPy array.",
        )
    expected_source_shape = (
        PINNED_INPUT_VIDEO_HEIGHT,
        PINNED_INPUT_VIDEO_WIDTH,
        3,
    )
    if tuple(frame.shape) != expected_source_shape:
        raise EvidenceValidationError(
            "invalid_source_frame_shape",
            f"Decoded frame must have shape {expected_source_shape}.",
        )
    if frame.dtype != numpy_module.uint8:
        raise EvidenceValidationError(
            "invalid_source_frame_dtype",
            "Decoded frame must be uint8 before pinned preprocessing.",
        )

    rgb = cv2_module.cvtColor(frame, code=cv2_module.COLOR_BGR2RGB)
    rgb = numpy_module.asarray(
        numpy_module.clip(rgb, 0, 255),
        dtype=numpy_module.uint8,
    )
    processed = cv2_module.resize(
        rgb,
        (PINNED_PROCESSED_VIDEO_WIDTH, PINNED_PROCESSED_VIDEO_HEIGHT),
        interpolation=cv2_module.INTER_LINEAR,
    )
    expected_processed_shape = (
        PINNED_PROCESSED_VIDEO_HEIGHT,
        PINNED_PROCESSED_VIDEO_WIDTH,
        3,
    )
    if tuple(processed.shape) != expected_processed_shape:
        raise EvidenceValidationError(
            "invalid_processed_frame_shape",
            f"Processed frame must have shape {expected_processed_shape}.",
        )
    if processed.dtype != numpy_module.uint8:
        raise EvidenceValidationError(
            "invalid_processed_frame_dtype",
            "Processed frame must remain uint8 before normalization.",
        )
    payload = processed.tobytes(order="C")
    return processed, {
        "source_frame_index": source_frame_index,
        "processed_sha256": sha256_bytes(payload),
        "size_bytes": len(payload),
    }


def decode_and_preprocess_rollout_context(
    video_path: Path,
    *,
    context_frames: int,
    cv2_module: Any,
    numpy_module: Any,
) -> tuple[list[Any], dict[str, Any]]:
    """Decode an exact context and release the capture on every outcome."""

    if not isinstance(context_frames, int) or isinstance(
        context_frames, bool
    ) or context_frames <= 0:
        raise EvidenceValidationError(
            "invalid_context_frame_count",
            "context_frames must be a positive integer.",
        )
    capture = cv2_module.VideoCapture(str(video_path))
    if hasattr(capture, "isOpened") and not capture.isOpened():
        capture.release()
        raise EvidenceValidationError(
            "video_decode_failed",
            "Canonical input video could not be opened.",
        )
    selected_indices = list(range(context_frames))
    processed_frames: list[Any] = []
    frame_records: list[dict[str, Any]] = []
    try:
        for frame_index in selected_indices:
            if capture.set(cv2_module.CAP_PROP_POS_FRAMES, frame_index) is False:
                raise EvidenceValidationError(
                    "video_seek_failed",
                    f"Could not select required source frame {frame_index}.",
                )
            decoded, frame = capture.read()
            if not decoded or frame is None:
                raise EvidenceValidationError(
                    "video_decode_failed",
                    f"Could not decode required source frame {frame_index}.",
                    f"$.video_preprocessing.derived.selected_source_frame_indices[{frame_index}]",
                )
            processed, record = preprocess_rollout_frame(
                frame,
                source_frame_index=frame_index,
                cv2_module=cv2_module,
                numpy_module=numpy_module,
            )
            processed_frames.append(processed)
            frame_records.append(record)
    finally:
        capture.release()

    observed_indices = [record["source_frame_index"] for record in frame_records]
    if (
        len(processed_frames) != context_frames
        or len(frame_records) != context_frames
        or observed_indices != selected_indices
        or len(set(observed_indices)) != context_frames
    ):
        raise EvidenceValidationError(
            "frame_cardinality_mismatch",
            "Processed frames must preserve exact count, order, and identity.",
        )
    aggregate_payload = b"".join(
        frame.tobytes(order="C") for frame in processed_frames
    )
    return processed_frames, {
        "classification": "derived",
        "transformation_name": VIDEO_PREPROCESSING_TRANSFORMATION,
        "transformation_version": VIDEO_PREPROCESSING_VERSION,
        "matched_source_path": VIDEO_PREPROCESSING_SOURCE,
        "selected_source_frame_indices": selected_indices,
        "requested_context_frames": context_frames,
        "original_frame_shape": [
            PINNED_INPUT_VIDEO_HEIGHT,
            PINNED_INPUT_VIDEO_WIDTH,
            3,
        ],
        "processed_frame_shape": [
            PINNED_PROCESSED_VIDEO_HEIGHT,
            PINNED_PROCESSED_VIDEO_WIDTH,
            3,
        ],
        "color_conversion": "BGR_to_RGB",
        "interpolation": "cv2.INTER_LINEAR",
        "pre_normalization_dtype": "uint8",
        "normalization_rule": VIDEO_PREPROCESSING_NORMALIZATION,
        "processed_frame_count": len(processed_frames),
        "processed_frames_sha256": sha256_bytes(aggregate_payload),
        "processed_frames_size_bytes": len(aggregate_payload),
        "frame_records": frame_records,
        "frames_dropped": 0,
        "frames_added": 0,
        "frames_duplicated": 0,
        "frame_order_preserved": True,
        "storage_classification": "runtime_only_in_memory_outside_git",
    }


def validate_rollout_position_budget(
    *,
    context_frames: int,
    raw_visual_token_shape: Sequence[int],
    flattened_visual_token_shape: Sequence[int],
    action_token_shape: Sequence[int],
    max_position_embeddings: int,
    generated_visual_tokens: int = VISUAL_TOKENS,
) -> dict[str, Any]:
    """Fail before transformer prefill unless the pinned token budget is exact."""

    if not isinstance(context_frames, int) or isinstance(
        context_frames, bool
    ) or context_frames <= 0:
        raise EvidenceValidationError(
            "invalid_context_frame_count",
            "context_frames must be a positive integer.",
        )
    expected_raw_shape = (context_frames, 14, 24)
    if tuple(raw_visual_token_shape) != expected_raw_shape:
        raise EvidenceValidationError(
            "invalid_visual_token_shape",
            f"Tokenizer output must have shape {expected_raw_shape}.",
        )
    expected_flattened_shape = (1, context_frames, VISUAL_TOKENS)
    if tuple(flattened_visual_token_shape) != expected_flattened_shape:
        raise EvidenceValidationError(
            "invalid_flattened_visual_token_shape",
            f"Flattened visual tokens must have shape {expected_flattened_shape}.",
        )
    expected_action_shape = (1, 1, ACTION_TOKENS)
    if tuple(action_token_shape) != expected_action_shape:
        raise EvidenceValidationError(
            "invalid_action_token_shape",
            f"Action tokens must have shape {expected_action_shape}.",
        )
    if generated_visual_tokens != VISUAL_TOKENS:
        raise EvidenceValidationError(
            "invalid_generation_token_count",
            f"Exactly {VISUAL_TOKENS} generated visual tokens are required.",
        )
    if (
        not isinstance(max_position_embeddings, int)
        or isinstance(max_position_embeddings, bool)
        or max_position_embeddings != PINNED_MAX_POSITION_EMBEDDINGS
    ):
        raise EvidenceValidationError(
            "max_position_embeddings_mismatch",
            "Loaded max_position_embeddings must equal the pinned value 5552.",
        )

    total_visual_prompt_tokens = context_frames * VISUAL_TOKENS
    prompt_positions = total_visual_prompt_tokens + ACTION_TOKENS
    conservative_position_budget = prompt_positions + generated_visual_tokens
    if conservative_position_budget > max_position_embeddings:
        raise EvidenceValidationError(
            "position_budget_overflow",
            (
                f"Prompt plus generated positions ({conservative_position_budget}) "
                f"exceed max_position_embeddings ({max_position_embeddings})."
            ),
        )
    return {
        "classification": "tokenized",
        "raw_visual_token_shape": list(raw_visual_token_shape),
        "flattened_visual_token_shape": list(flattened_visual_token_shape),
        "visual_tokens_per_frame": VISUAL_TOKENS,
        "total_visual_prompt_tokens": total_visual_prompt_tokens,
        "action_token_shape": list(action_token_shape),
        "action_token_count": ACTION_TOKENS,
        "prompt_positions": prompt_positions,
        "requested_generated_positions": generated_visual_tokens,
        "conservative_position_budget": conservative_position_budget,
        "max_position_embeddings": max_position_embeddings,
        "position_budget_status": "PASS",
    }


def _tensor_sha256(tensor: Any) -> str:
    payload = tensor.detach().cpu().contiguous().numpy().tobytes(order="C")
    return sha256_bytes(payload)


def _project_owned_lvm_generate(
    args: SimpleNamespace,
    model: Any,
    output_dir: Path,
    demo_video: str,
    *,
    upstream_inference: Any,
) -> dict[str, Any]:
    """Use pinned generation with the missing Gradio preprocessing boundary."""

    if args.accelerate_algo != "naive":
        raise EvidenceValidationError(
            "unsupported_generation_algorithm",
            "Formal Step 2.6 compatibility execution requires naive generation.",
        )
    input_mp4_path = Path(args.data_root) / demo_video
    input_action_path = input_mp4_path.with_suffix(".jsonl")
    output_mp4_path = output_dir / demo_video
    output_action_path = output_mp4_path.with_suffix(".jsonl")
    if output_mp4_path.exists() or output_action_path.exists():
        raise EvidenceValidationError(
            "rollout_output_exists",
            "Formal rollout outputs must not already exist.",
        )
    shutil.copyfile(input_action_path, output_action_path)
    if (
        output_action_path.stat().st_size != input_action_path.stat().st_size
        or sha256_file(output_action_path) != sha256_file(input_action_path)
    ):
        raise EvidenceValidationError(
            "generated_metadata_mismatch",
            "Paired metadata copy differs from the compatibility input.",
        )

    action_list: list[Any] = []
    mcdataset = upstream_inference.MCDataset()
    with input_action_path.open("r", encoding="utf-8") as handle:
        for row_index, line in enumerate(handle):
            parsed = _restricted_eval_derived_action(
                line,
                row_index,
                safe_globals=upstream_inference.safe_globals,
            )
            parsed = dict(parsed)
            parsed["camera"] = upstream_inference.np.array(parsed["camera"])
            action_list.append(
                mcdataset.get_action_index_from_actiondict(
                    parsed,
                    action_vocab_offset=8192,
                )
            )
    required_action_index = args.demo_num
    if len(action_list) <= required_action_index:
        raise EvidenceValidationError(
            "missing_generation_action",
            "Compatibility JSONL lacks the action required after the context.",
        )

    processed_frames, derived = decode_and_preprocess_rollout_context(
        input_mp4_path,
        context_frames=args.demo_num,
        cv2_module=upstream_inference.cv2,
        numpy_module=upstream_inference.np,
    )
    device = model.transformer.device
    frames = upstream_inference.torch.stack(
        [upstream_inference.torch.from_numpy(frame) for frame in processed_frames],
        dim=0,
    ).to(device)
    if tuple(frames.shape) != (
        args.demo_num,
        PINNED_PROCESSED_VIDEO_HEIGHT,
        PINNED_PROCESSED_VIDEO_WIDTH,
        3,
    ):
        raise EvidenceValidationError(
            "invalid_processed_tensor_shape",
            "Stacked processed frames have an unexpected shape.",
        )
    frames = frames.permute(0, 3, 1, 2).float() / 255.0
    normalize = upstream_inference.transforms.Normalize(
        mean=[0.5, 0.5, 0.5],
        std=[0.5, 0.5, 0.5],
    )
    frames = normalize(frames)

    with upstream_inference.torch.no_grad(), upstream_inference.torch.autocast(
        device_type="cuda",
        dtype=upstream_inference.torch.float16,
    ):
        raw_visual_tokens = model.tokenizer.tokenize_images(frames)
    flattened_visual_tokens = upstream_inference.rearrange(
        raw_visual_tokens,
        "(b t) h w -> b t (h w)",
        b=1,
    )
    action_tokens = upstream_inference.torch.tensor(
        action_list[required_action_index : required_action_index + args.frames]
    ).unsqueeze(1).to(device)
    max_positions = getattr(getattr(model, "config", None), "max_position_embeddings", None)
    tokenization = validate_rollout_position_budget(
        context_frames=args.demo_num,
        raw_visual_token_shape=tuple(raw_visual_tokens.shape),
        flattened_visual_token_shape=tuple(flattened_visual_tokens.shape),
        action_token_shape=tuple(action_tokens.shape),
        max_position_embeddings=max_positions,
        generated_visual_tokens=VISUAL_TOKENS * args.frames,
    )
    image_input = upstream_inference.rearrange(
        flattened_visual_tokens,
        "b t c -> b (t c)",
    )
    if tuple(image_input.shape) != (
        1,
        args.demo_num * VISUAL_TOKENS,
    ):
        raise EvidenceValidationError(
            "invalid_visual_prompt_shape",
            "Visual prompt tensor shape does not match the validated token budget.",
        )
    tokenization.update(
        {
            "tokenizer_module": type(model.tokenizer).__module__,
            "tokenizer_class": type(model.tokenizer).__qualname__,
            "vae_config_sha256": PINNED_VAE_CONFIG_SHA256,
            "vae_checkpoint_sha256": PINNED_VAE_CHECKPOINT_SHA256,
            "visual_token_dtype": str(raw_visual_tokens.dtype),
            "visual_token_device": str(raw_visual_tokens.device),
            "visual_token_sha256": _tensor_sha256(raw_visual_tokens),
            "action_token_dtype": str(action_tokens.dtype),
            "action_token_device": str(action_tokens.device),
            "action_token_sha256": _tensor_sha256(action_tokens),
        }
    )

    generation_start = time.time()
    with upstream_inference.torch.no_grad(), upstream_inference.torch.autocast(
        device_type="cuda",
        dtype=upstream_inference.torch.float16,
    ):
        outputs = model.transformer.naive_generate(
            input_ids=image_input,
            max_new_tokens=VISUAL_TOKENS,
            action_all=action_tokens,
            top_k=args.top_k,
            top_p=args.top_p,
        )
    time_costed = time.time() - generation_start
    generated_tokens = outputs.tolist()[0]
    if len(generated_tokens) != VISUAL_TOKENS:
        raise EvidenceValidationError(
            "unexpected_generation_result",
            "Exactly 336 generated visual tokens were required.",
        )
    upstream_inference.token2video(
        generated_tokens,
        model.tokenizer,
        str(output_mp4_path),
        args.fps,
        device,
    )
    return {
        "time_costed": time_costed,
        "token_num": len(generated_tokens),
        "video_preprocessing": {
            "derived": derived,
            "tokenization": tokenization,
        },
    }


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


def _canonical_video_provenance(
    input_mp4: Path,
    *,
    ffprobe_executable: str,
    asset_revision: str,
) -> dict[str, Any]:
    pre_size = input_mp4.stat().st_size
    pre_hash = sha256_file(input_mp4)
    if (
        pre_size != PINNED_INPUT_MP4_SIZE_BYTES
        or pre_hash != PINNED_INPUT_MP4_SHA256
    ):
        raise EvidenceValidationError(
            "canonical_video_identity_mismatch",
            "Canonical ModelScope MP4 does not match the pinned size and SHA-256.",
        )
    probe = _ffprobe(input_mp4, ffprobe_executable)
    if (
        probe["width"] != PINNED_INPUT_VIDEO_WIDTH
        or probe["height"] != PINNED_INPUT_VIDEO_HEIGHT
        or probe["r_frame_rate"] != "20/1"
        or probe["avg_frame_rate"] != "20/1"
        or probe["declared_frames"] != PINNED_INPUT_VIDEO_FRAMES
        or probe["decoded_frames"] != PINNED_INPUT_VIDEO_FRAMES
    ):
        raise EvidenceValidationError(
            "canonical_video_media_mismatch",
            "Canonical ModelScope MP4 media facts do not match the pinned sample.",
        )
    return {
        "classification": "original",
        "path": str(input_mp4),
        "size_bytes": pre_size,
        "sha256": pre_hash,
        "asset_revision": asset_revision,
        "width": probe["width"],
        "height": probe["height"],
        "r_frame_rate": probe["r_frame_rate"],
        "avg_frame_rate": probe["avg_frame_rate"],
        "frame_count": probe["declared_frames"],
        "decoded_frame_count": probe["decoded_frames"],
        "duration_seconds": probe["duration_seconds"],
        "pre_size_bytes": pre_size,
        "pre_sha256": pre_hash,
        "post_size_bytes": pre_size,
        "post_sha256": pre_hash,
        "canonical_input": True,
        "unchanged": True,
    }


def _finalize_canonical_video_provenance(
    original: Mapping[str, Any],
) -> dict[str, Any]:
    finalized = dict(original)
    path = Path(finalized["path"])
    post_size = path.stat().st_size
    post_hash = sha256_file(path)
    finalized["post_size_bytes"] = post_size
    finalized["post_sha256"] = post_hash
    finalized["unchanged"] = (
        post_size == finalized["pre_size_bytes"]
        and post_hash == finalized["pre_sha256"]
    )
    if finalized["unchanged"] is not True:
        raise EvidenceValidationError(
            "canonical_video_mutated",
            "Canonical input MP4 changed during in-memory preprocessing.",
        )
    return finalized


def execute_rollout(
    args: argparse.Namespace,
    *,
    command: Sequence[str],
) -> Path:
    """Execute and seal exactly one generated-frame rollout on CUDA."""

    requested_output_dir = args.output_dir.resolve()
    if requested_output_dir.is_relative_to(REPO_ROOT):
        raise EvidenceValidationError(
            "runtime_output_inside_repository",
            "Formal Step 2.6 runtime evidence must remain outside the Git tree.",
        )
    output_dir = _prepare_output_directory(requested_output_dir)
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
        video_preprocessing = {
            "original": _canonical_video_provenance(
                input_mp4,
                ffprobe_executable=args.ffprobe,
                asset_revision=args.asset_revision,
            )
        }
        _seed_everything(torch, args.seed)
        torch.cuda.set_device(0)
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(0)
        total_start = time.perf_counter()

        with _external_source_imports(prepared["source_root"]):
            OmegaConf = importlib.import_module("omegaconf").OmegaConf
            upstream_mcdataset = importlib.import_module("mcdataset")
            upstream_utils = importlib.import_module("utils")
            upstream_inference = importlib.import_module("inference")
            compatibility_root = output_dir / "inference_input"
            derived_jsonl = compatibility_root / input_jsonl.name
            action_compatibility = convert_action_jsonl_for_pinned_inference(
                input_jsonl,
                derived_jsonl,
                mcdataset_module=upstream_mcdataset,
                asset_revision=args.asset_revision,
                expected_original_size_bytes=PINNED_INPUT_JSONL_SIZE_BYTES,
                expected_original_sha256=PINNED_INPUT_JSONL_SHA256,
            )
            staged_mp4 = compatibility_root / input_mp4.name
            try:
                staged_mp4.symlink_to(input_mp4)
            except OSError as exc:
                raise EvidenceValidationError(
                    "input_video_staging_failed",
                    f"Could not create the external-evidence MP4 symlink: {exc}",
                ) from exc
            if (
                not staged_mp4.is_file()
                or staged_mp4.stat().st_size != input_mp4.stat().st_size
                or sha256_file(staged_mp4) != sha256_file(input_mp4)
            ):
                raise EvidenceValidationError(
                    "input_video_staging_failed",
                    "Staged MP4 symlink does not resolve to the canonical input bytes.",
                )
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

            generation_args = SimpleNamespace(
                data_root=str(compatibility_root),
                frames=1,
                demo_num=args.context_frames,
                window_size=2,
                accelerate_algo="naive",
                fps=6,
                top_k=1,
                top_p=None,
            )
            generation_start = time.perf_counter()
            result = _project_owned_lvm_generate(
                generation_args,
                model,
                output_dir,
                input_mp4.name,
                upstream_inference=upstream_inference,
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
            generated_preprocessing = result.get("video_preprocessing")
            if not isinstance(generated_preprocessing, Mapping):
                raise EvidenceValidationError(
                    "missing_video_preprocessing_provenance",
                    "Project-owned generation omitted preprocessing provenance.",
                )
            video_preprocessing.update(generated_preprocessing)

        generated_video = output_dir / input_mp4.name
        paired_metadata = output_dir / input_jsonl.name
        if not generated_video.is_file() or not paired_metadata.is_file():
            raise EvidenceValidationError(
                "missing_rollout_output",
                "Upstream generation did not create both MP4 and paired metadata.",
            )
        _assert_action_file_unchanged(action_compatibility["original"], "original")
        _assert_action_file_unchanged(action_compatibility["derived"], "derived")
        video_preprocessing["original"] = (
            _finalize_canonical_video_provenance(
                video_preprocessing["original"],
            )
        )
        action_compatibility = dict(action_compatibility)
        action_compatibility["generated"] = _generated_action_provenance(
            action_compatibility,
            paired_metadata,
            generated_video,
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
            "action_compatibility": action_compatibility,
            "video_preprocessing": video_preprocessing,
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
        "action_compatibility": state["action_compatibility"],
        "video_preprocessing": state["video_preprocessing"],
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
