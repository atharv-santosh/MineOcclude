from __future__ import annotations

import io
import inspect
import json
import math
import tempfile
import unittest
from contextlib import redirect_stderr
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import mineocclude.models.phase2_aws as phase2_aws_module
from mineocclude.models.phase2_aws import (
    ACTION_COMPATIBILITY_SERIALIZATION,
    ACTION_COMPATIBILITY_TRANSFORMATION,
    ACTION_COMPATIBILITY_VERSION,
    PINNED_ASSET_REVISION,
    PINNED_INPUT_MP4_SHA256,
    PINNED_INPUT_MP4_SIZE_BYTES,
    PINNED_MAIN_CHECKPOINT_SHA256,
    PINNED_SOURCE_REVISION,
    PINNED_VAE_CHECKPOINT_SHA256,
    PINNED_VAE_CONFIG_SHA256,
    _initialize_cuda_device,
    _require_valid_checkpoint_load_state,
    build_architecture_parser,
    build_rollout_parser,
    build_teacher_forced_parser,
    convert_action_jsonl_for_pinned_inference,
    decode_and_preprocess_rollout_context,
    preprocess_rollout_frame,
    validate_rollout_position_budget,
)
from mineocclude.models.phase2_evidence import (
    ARCHITECTURE_EVIDENCE_TYPE,
    EVIDENCE_SCHEMA_VERSION,
    ROLLOUT_EVIDENCE_TYPE,
    TEACHER_FORCED_EVIDENCE_TYPE,
    VIDEO_PREPROCESSING_NORMALIZATION,
    VIDEO_PREPROCESSING_SOURCE,
    VIDEO_PREPROCESSING_TRANSFORMATION,
    VIDEO_PREPROCESSING_VERSION,
    CHECKPOINT_KEY_HASH_SERIALIZATION,
    CHECKPOINT_LOAD_COMPONENT_PROFILES,
    CHECKPOINT_LOAD_PROFILE_ID,
    CHECKPOINT_LOAD_PROFILE_PROVENANCE,
    CHECKPOINT_LOAD_PROFILE_VERSION,
    EvidenceValidationError,
    artifact_record,
    canonical_json_bytes,
    checkpoint_key_list_sha256,
    classify_checkpoint_load_state,
    compare_numeric_sequences,
    expected_teacher_token_layout,
    parse_ffprobe_output,
    seal_document,
    sha256_bytes,
    sha256_file,
    validate_action_compatibility_provenance,
    validate_architecture_facts,
    validate_architecture_report,
    validate_checkpoint_load_state,
    validate_hook_records,
    validate_output_file_completeness,
    validate_rollout_manifest,
    validate_timing_fields,
    validate_teacher_forced_report,
    validate_video_preprocessing_provenance,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "phase2"
SCHEMA = ROOT / "schemas" / "person_a" / "phase2_runtime_evidence_v1.schema.json"
AUDITED_LOAD_KEYS = (
    FIXTURES / "audited_checkpoint_load_keys_v1.json"
)
SHA256 = "a" * 64
GIT_SHA = "b" * 40


def _common_cli_arguments(tmp_path: Path) -> list[str]:
    return [
        "--mineworld-source-root",
        str(tmp_path / "source"),
        "--model-config",
        str(tmp_path / "model.yaml"),
        "--main-checkpoint",
        str(tmp_path / "model.ckpt"),
        "--vae-config",
        str(tmp_path / "vae.json"),
        "--vae-checkpoint",
        str(tmp_path / "vae.ckpt"),
        "--environment-report",
        str(tmp_path / "environment.txt"),
        "--output-dir",
        str(tmp_path / "output"),
        "--run-id",
        "phase2-test-run",
        "--seed",
        "7",
        "--source-revision",
        GIT_SHA,
        "--asset-revision",
        GIT_SHA,
        "--model-config-sha256",
        SHA256,
        "--main-checkpoint-sha256",
        SHA256,
        "--vae-config-sha256",
        SHA256,
        "--vae-checkpoint-sha256",
        SHA256,
        "--environment-report-sha256",
        SHA256,
    ]


def _identity() -> dict[str, object]:
    return {
        "run_id": "phase2-test-run",
        "seed": 7,
        "source_revision": GIT_SHA,
        "asset_revision": GIT_SHA,
        "mineocclude_code_sha": GIT_SHA,
        "mineocclude_dirty": False,
        "model_config_sha256": SHA256,
        "main_checkpoint_sha256": SHA256,
        "vae_config_sha256": SHA256,
        "vae_checkpoint_sha256": SHA256,
        "environment_report_sha256": SHA256,
        "command": ["python", "scripts/run_phase2_rollout.py"],
    }


def _pinned_identity() -> dict[str, object]:
    identity = _identity()
    identity.update(CHECKPOINT_LOAD_PROFILE_PROVENANCE)
    return identity


def _audited_raw_load_state() -> dict[str, list[str]]:
    fixture = json.loads(AUDITED_LOAD_KEYS.read_text(encoding="utf-8"))
    assert fixture["schema_version"] == "1.0"
    assert fixture["profile_id"] == CHECKPOINT_LOAD_PROFILE_ID
    assert fixture["profile_version"] == CHECKPOINT_LOAD_PROFILE_VERSION
    assert (
        fixture["key_hash_serialization"]
        == CHECKPOINT_KEY_HASH_SERIALIZATION
    )
    for field, expected in CHECKPOINT_LOAD_PROFILE_PROVENANCE.items():
        assert fixture[field] == expected
    assert (
        fixture["transformer_sorted_key_list_sha256"]
        == CHECKPOINT_LOAD_COMPONENT_PROFILES["transformer"][
            "sorted_key_list_sha256"
        ]
    )
    assert (
        fixture["vae_sorted_key_list_sha256"]
        == CHECKPOINT_LOAD_COMPONENT_PROFILES["vae"][
            "sorted_key_list_sha256"
        ]
    )
    return {
        "transformer_missing_keys": fixture["transformer_missing_keys"],
        "transformer_unexpected_keys": fixture[
            "transformer_unexpected_keys"
        ],
        "vae_missing_keys": fixture["vae_missing_keys"],
        "vae_unexpected_keys": fixture["vae_unexpected_keys"],
    }


def _architecture_report() -> dict[str, object]:
    identity = _pinned_identity()
    raw_load_state = _audited_raw_load_state()
    load_state = {
        **deepcopy(raw_load_state),
        "classification": classify_checkpoint_load_state(
            raw_load_state,
            identity,
        ),
    }
    document = {
        "schema_version": "1.0",
        "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
        "evidence_type": ARCHITECTURE_EVIDENCE_TYPE,
        "status": "completed",
        "identity": identity,
        "architecture": _architecture_facts(),
        "load_state": load_state,
        "module_tree": [
            {
                "name": "",
                "class_name": "LlamaLVM",
                "direct_parameters": 1,
            }
        ],
        "cuda_memory": {
            "peak_allocated_bytes": 1,
            "peak_reserved_bytes": 2,
        },
    }
    return seal_document(document)


def _teacher_forced_report() -> dict[str, object]:
    identity = _pinned_identity()
    raw_load_state = _audited_raw_load_state()
    load_state = {
        **deepcopy(raw_load_state),
        "classification": classify_checkpoint_load_state(
            raw_load_state,
            identity,
        ),
    }
    layout = expected_teacher_token_layout()
    hooks = [
        {
            "repeat_index": repeat_index,
            "layer_index": layer_index,
            "module_name": f"transformer.model.layers.{layer_index}",
            "shape": [1, 5552, 2048],
            "dtype": "torch.float16",
            "device": "cuda:0",
            "token_positions_sha256": layout["positions_sha256"],
            "output_sha256": (
                f"{repeat_index:02x}{layer_index:02x}".ljust(64, "0")
            ),
            "summary": {
                "min": -1.0,
                "max": 1.0,
                "mean": 0.0,
                "std": 0.5,
            },
        }
        for repeat_index in range(2)
        for layer_index in range(20)
    ]
    document = {
        "schema_version": "1.0",
        "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
        "evidence_type": TEACHER_FORCED_EVIDENCE_TYPE,
        "status": "completed",
        "identity": identity,
        "load_state": load_state,
        "execution": {
            "repeats": 2,
            "precision": "float16",
            "batch_size": 1,
            "eval_mode": True,
            "no_grad": True,
        },
        "input": {
            "input_id": "audited-teacher-fixture",
            "input_kind": "accepted",
            "mp4_sha256": SHA256,
            "jsonl_sha256": SHA256,
            "frame_indices": list(range(16)),
        },
        "token_layout": layout,
        "hooks": hooks,
        "repeatability": [
            {
                "layer_index": layer_index,
                "allclose": True,
                "max_absolute_difference": 0.0,
                "rtol": 1e-3,
                "atol": 1e-3,
            }
            for layer_index in range(20)
        ],
        "timing": {
            "load_seconds": 1.0,
            "forward_seconds": [0.5, 0.5],
        },
        "memory": {
            "cpu_peak_rss_bytes": 1,
            "peak_cuda_allocated_bytes": 2,
            "peak_cuda_reserved_bytes": 3,
        },
        "cleanup": {"hooks_removed": True},
    }
    return seal_document(document)


def _rollout_document(runtime_root: Path) -> dict[str, object]:
    shared_input = FIXTURES / "ffprobe_valid.json"
    generated = FIXTURES / "ffprobe_valid.json"
    original = runtime_root / "original.jsonl"
    original_row = _raw_action()
    original.write_text(
        json.dumps(original_row, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    paired = runtime_root / "paired.jsonl"
    paired.write_text(
        '{"camera":[0,0],"forward":0}\n',
        encoding="utf-8",
        newline="\n",
    )
    derived = runtime_root / "derived.jsonl"
    derived.write_bytes(paired.read_bytes())
    raw_log = SCHEMA
    input_roles = [
        "model_config",
        "main_checkpoint",
        "vae_config",
        "vae_checkpoint",
        "input_mp4",
        "input_jsonl",
        "environment_report",
    ]
    document = {
        "schema_version": "1.0",
        "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
        "evidence_type": ROLLOUT_EVIDENCE_TYPE,
        "status": "completed",
        "identity": _identity(),
        "inputs": [
            artifact_record(
                role,
                original if role == "input_jsonl" else shared_input,
            )
            for role in input_roles
        ],
        "runtime": {
            "timings": {
                "model_initialization_seconds": 2.0,
                "first_generated_frame_seconds": 1.0,
                "generation_kernel_seconds": 0.5,
                "total_runtime_seconds": 3.5,
            },
            "process_exit_status": 0,
            "peak_cuda_allocated_bytes": 1,
            "peak_cuda_reserved_bytes": 2,
            "gpu": {
                "name": "fixture-only GPU identity",
                "device_index": 0,
                "total_memory_bytes": 3,
                "capability": "0.0",
            },
            "torch_version": "fixture",
            "cuda_version": "fixture",
            "generated_frames_requested": 1,
        },
        "outputs": [
            artifact_record("generated_video", generated),
            artifact_record("paired_metadata", paired),
            artifact_record("raw_stdout_stderr", raw_log),
        ],
        "action_compatibility": {
            "original": {
                "classification": "original",
                "path": str(original.resolve()),
                "size_bytes": original.stat().st_size,
                "sha256": sha256_file(original),
                "row_count": 1,
                "asset_revision": GIT_SHA,
                "pre_size_bytes": original.stat().st_size,
                "pre_sha256": sha256_file(original),
                "post_size_bytes": original.stat().st_size,
                "post_sha256": sha256_file(original),
                "row_sequence_sha256": sha256_bytes(
                    canonical_json_bytes(original_row)
                ),
                "canonical_input": True,
                "unchanged": True,
            },
            "derived": {
                "classification": "derived",
                "path": str(derived.resolve()),
                "size_bytes": derived.stat().st_size,
                "sha256": sha256_file(derived),
                "row_count": 1,
                "transformation_name": ACTION_COMPATIBILITY_TRANSFORMATION,
                "transformation_version": ACTION_COMPATIBILITY_VERSION,
                "deterministic_serialization": ACTION_COMPATIBILITY_SERIALIZATION,
                "parent_original_sha256": sha256_file(original),
                "parent_row_sequence_sha256": sha256_bytes(
                    canonical_json_bytes(original_row)
                ),
                "row_sequence_sha256": sha256_file(derived),
                "source_to_derived_sequence_sha256": sha256_bytes(
                    (
                        sha256_bytes(canonical_json_bytes(original_row))
                        + ":"
                        + sha256_file(derived)
                        + "\n"
                    ).encode("ascii")
                ),
                "rows_dropped": 0,
                "rows_added": 0,
                "row_order_preserved": True,
                "storage_classification": "runtime_only_outside_git",
            },
            "generated": {
                "classification": "generated",
                "path": str(paired.resolve()),
                "size_bytes": paired.stat().st_size,
                "sha256": sha256_file(paired),
                "row_count": 1,
                "relationship_to_generated_mp4":
                    "paired_action_metadata_for_generated_video",
                "generated_video_sha256": sha256_file(generated),
                "relationship_to_original":
                    "derived_from_original_via_compatibility_jsonl",
                "original_jsonl_sha256": sha256_file(original),
                "relationship_to_derived":
                    "byte_identical_copy_of_derived_jsonl",
                "derived_jsonl_sha256": sha256_file(derived),
                "materialization_method":
                    "project_owned_byte_copy_of_derived_jsonl",
            },
        },
        "video_preprocessing": {
            "original": {
                "classification": "original",
                "path": str(shared_input.resolve()),
                "size_bytes": shared_input.stat().st_size,
                "sha256": sha256_file(shared_input),
                "asset_revision": GIT_SHA,
                "width": 640,
                "height": 360,
                "r_frame_rate": "20/1",
                "avg_frame_rate": "20/1",
                "frame_count": 4152,
                "decoded_frame_count": 4152,
                "duration_seconds": 207.6,
                "pre_size_bytes": shared_input.stat().st_size,
                "pre_sha256": sha256_file(shared_input),
                "post_size_bytes": shared_input.stat().st_size,
                "post_sha256": sha256_file(shared_input),
                "canonical_input": True,
                "unchanged": True,
            },
            "derived": {
                "classification": "derived",
                "transformation_name": VIDEO_PREPROCESSING_TRANSFORMATION,
                "transformation_version": VIDEO_PREPROCESSING_VERSION,
                "matched_source_path": VIDEO_PREPROCESSING_SOURCE,
                "selected_source_frame_indices": list(range(8)),
                "requested_context_frames": 8,
                "original_frame_shape": [360, 640, 3],
                "processed_frame_shape": [224, 384, 3],
                "color_conversion": "BGR_to_RGB",
                "interpolation": "cv2.INTER_LINEAR",
                "pre_normalization_dtype": "uint8",
                "normalization_rule": VIDEO_PREPROCESSING_NORMALIZATION,
                "processed_frame_count": 8,
                "processed_frames_sha256": SHA256,
                "processed_frames_size_bytes": 8 * 224 * 384 * 3,
                "frame_records": [
                    {
                        "source_frame_index": index,
                        "processed_sha256": SHA256,
                        "size_bytes": 224 * 384 * 3,
                    }
                    for index in range(8)
                ],
                "frames_dropped": 0,
                "frames_added": 0,
                "frames_duplicated": 0,
                "frame_order_preserved": True,
                "storage_classification":
                    "runtime_only_in_memory_outside_git",
            },
            "tokenization": {
                "classification": "tokenized",
                "raw_visual_token_shape": [8, 14, 24],
                "flattened_visual_token_shape": [1, 8, 336],
                "visual_tokens_per_frame": 336,
                "total_visual_prompt_tokens": 2688,
                "action_token_shape": [1, 1, 11],
                "action_token_count": 11,
                "prompt_positions": 2699,
                "requested_generated_positions": 336,
                "conservative_position_budget": 3035,
                "max_position_embeddings": 5552,
                "position_budget_status": "PASS",
                "tokenizer_module": "fixture",
                "tokenizer_class": "FixtureTokenizer",
                "vae_config_sha256": SHA256,
                "vae_checkpoint_sha256": SHA256,
                "visual_token_dtype": "torch.int64",
                "visual_token_device": "cuda:0",
                "visual_token_sha256": SHA256,
                "action_token_dtype": "torch.int64",
                "action_token_device": "cuda:0",
                "action_token_sha256": SHA256,
            },
        },
        "ffprobe": {
            "width": 640,
            "height": 360,
            "r_frame_rate": "6/1",
            "avg_frame_rate": "6/1",
            "duration_seconds": 1 / 6,
            "declared_frames": 1,
            "decoded_frames": 1,
        },
    }
    return seal_document(document)


_FAKE_KEYBOARD_MAPPING = {
    "key.keyboard.w": "forward",
    "key.keyboard.s": "back",
    "key.keyboard.a": "left",
    "key.keyboard.d": "right",
    "key.keyboard.space": "jump",
}
_FAKE_NOOP_ACTION = {
    "ESC": 0,
    "back": 0,
    "drop": 0,
    "forward": 0,
    "hotbar.1": 0,
    "inventory": 0,
    "jump": 0,
    "left": 0,
    "right": 0,
    "sneak": 0,
    "sprint": 0,
    "swapHands": 0,
    "camera": [0, 0],
    "attack": 0,
    "use": 0,
    "pickItem": 0,
}


def _fake_mcdataset_module(
    mutate_flat: object | None = None,
    *,
    nondeterministic: bool = False,
) -> object:
    class Dataset:
        calls = 0

        def json_action_to_env_action(
            self, row: dict[str, object]
        ) -> tuple[dict[str, object], bool]:
            Dataset.calls += 1
            action = deepcopy(_FAKE_NOOP_ACTION)
            for key in row["keyboard"]["keys"]:
                action[_FAKE_KEYBOARD_MAPPING[key]] = 1
            mouse = row["mouse"]
            action["camera"] = [mouse["dy"] * 0.15, mouse["dx"] * 0.15]
            for button, field in ((0, "attack"), (1, "use"), (2, "pickItem")):
                if button in mouse["buttons"]:
                    action[field] = 1
            if nondeterministic and Dataset.calls % 2 == 0:
                action["jump"] = 1 - action["jump"]
            if callable(mutate_flat):
                mutate_flat(action)
            return action, not any(
                value
                for key, value in action.items()
                if key != "camera"
            )

    return SimpleNamespace(
        KEYBOARD_BUTTON_MAPPING=deepcopy(_FAKE_KEYBOARD_MAPPING),
        NOOP_ACTION=deepcopy(_FAKE_NOOP_ACTION),
        MCDataset=Dataset,
        np=SimpleNamespace(array=lambda items: items),
    )


def _raw_action(
    *,
    keys: object | None = None,
    buttons: object | None = None,
    dx: object = 2,
    dy: object = -3,
) -> dict[str, object]:
    return {
        "keyboard": {"keys": [] if keys is None else keys},
        "mouse": {
            "buttons": [] if buttons is None else buttons,
            "dx": dx,
            "dy": dy,
        },
        "isGuiOpen": True,
        "isGuiInventory": False,
        "unused_nullable_state": None,
    }


def _architecture_facts() -> dict[str, object]:
    return {
        "layer_count": 20,
        "hidden_size": 2048,
        "intermediate_size": 4096,
        "vocab_size": 8262,
        "max_position_embeddings": 5552,
        "num_attention_heads": 32,
        "num_key_value_heads": 4,
        "visual_tokens": 336,
        "action_tokens": 11,
        "tokens_per_pair": 347,
        "context_pairs": 16,
        "decoder_layer_path": "transformer.model.layers",
        "model_class": "MineWorldModel",
        "transformer_class": "LlamaForCausalLM",
        "vae_class": "VQModel",
        "dtype_distribution": {"torch.float16": 1},
        "device_distribution": {"cuda:0": 1},
        "parameter_counts": {"model": 3, "transformer": 2, "vae": 1},
    }


def _hook_records() -> list[dict[str, object]]:
    positions_hash = sha256_bytes(canonical_json_bytes([0, 1, 2, 3]))
    return [
        {
            "repeat_index": repeat,
            "layer_index": layer,
            "module_name": f"transformer.model.layers.{layer}",
            "shape": [1, 4, 3],
            "dtype": "torch.float16",
            "device": "cuda:0",
            "token_positions_sha256": positions_hash,
            "output_sha256": f"{repeat}{layer}".ljust(64, "0"),
            "summary": {"min": -1.0, "max": 1.0, "mean": 0.0, "std": 0.5},
        }
        for repeat in range(2)
        for layer in range(2)
    ]


class _FakeCapture:
    def __init__(self, frames: list[np.ndarray | None]) -> None:
        self.frames = frames
        self.current_index = 0
        self.released = False

    def isOpened(self) -> bool:
        return True

    def set(self, property_id: int, value: int) -> bool:
        self.current_index = int(value)
        return property_id == _FakeCv2.CAP_PROP_POS_FRAMES

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self.current_index >= len(self.frames):
            return False, None
        frame = self.frames[self.current_index]
        return frame is not None, None if frame is None else frame.copy()

    def release(self) -> None:
        self.released = True


class _FakeCv2:
    COLOR_BGR2RGB = 4
    INTER_LINEAR = 1
    CAP_PROP_POS_FRAMES = 1

    def __init__(self, frames: list[np.ndarray | None]) -> None:
        self.capture = _FakeCapture(frames)
        self.interpolations: list[int] = []

    def VideoCapture(self, path: str) -> _FakeCapture:
        del path
        return self.capture

    def cvtColor(self, frame: np.ndarray, *, code: int) -> np.ndarray:
        if code != self.COLOR_BGR2RGB:
            raise AssertionError("unexpected color conversion")
        return frame[:, :, ::-1].copy()

    def resize(
        self,
        frame: np.ndarray,
        size: tuple[int, int],
        *,
        interpolation: int,
    ) -> np.ndarray:
        self.interpolations.append(interpolation)
        if interpolation != self.INTER_LINEAR:
            raise AssertionError("unexpected interpolation")
        width, height = size
        source_y = np.linspace(0, frame.shape[0] - 1, height).astype(int)
        source_x = np.linspace(0, frame.shape[1] - 1, width).astype(int)
        return frame[source_y][:, source_x].copy()


class _FakeCuda:
    def __init__(
        self,
        *,
        available: bool = True,
        device_count: int = 1,
        current_device: int = 0,
        fail_on: str | None = None,
    ) -> None:
        self.available = available
        self.count = device_count
        self.selected = current_device
        self.fail_on = fail_on
        self.calls: list[str] = []

    def _call(self, name: str) -> None:
        self.calls.append(name)
        if self.fail_on == name:
            raise RuntimeError(f"controlled {name} failure")

    def is_available(self) -> bool:
        self._call("is_available")
        return self.available

    def device_count(self) -> int:
        self._call("device_count")
        return self.count

    def init(self) -> None:
        self._call("init")

    def set_device(self, index: int) -> None:
        self._call(f"set_device:{index}")

    def current_device(self) -> int:
        self._call("current_device")
        return self.selected

    def get_device_name(self, index: int) -> str:
        self._call(f"get_device_name:{index}")
        return "NVIDIA controlled fixture"

    def get_device_properties(self, index: int) -> object:
        self._call(f"get_device_properties:{index}")
        return SimpleNamespace(
            name="NVIDIA controlled fixture",
            total_memory=24_000_000_000,
            major=8,
            minor=9,
        )

    def empty_cache(self) -> None:
        self._call("empty_cache")

    def reset_peak_memory_stats(self, index: int) -> None:
        self._call(f"reset_peak_memory_stats:{index}")


class Phase2EvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.runtime_root = Path(self._temporary_directory.name)
        self.tmp_path = FIXTURES

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()

    def _convert_payload(
        self,
        payload: bytes,
        *,
        module: object | None = None,
        case_name: str = "case",
    ) -> tuple[Path, Path, dict[str, object]]:
        case_root = self.runtime_root / case_name
        case_root.mkdir()
        original = case_root / "scene.jsonl"
        original.write_bytes(payload)
        derived = case_root / "runtime" / "scene.jsonl"
        provenance = convert_action_jsonl_for_pinned_inference(
            original,
            derived,
            mcdataset_module=module or _fake_mcdataset_module(),
            asset_revision=PINNED_ASSET_REVISION,
            expected_original_size_bytes=original.stat().st_size,
            expected_original_sha256=sha256_file(original),
        )
        return original, derived, provenance

    def _convert_rows(
        self,
        rows: list[dict[str, object]],
        *,
        module: object | None = None,
        case_name: str = "case",
    ) -> tuple[Path, Path, dict[str, object]]:
        payload = b"".join(
            (
                json.dumps(
                    row,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                + "\n"
            ).encode("utf-8")
            for row in rows
        )
        return self._convert_payload(
            payload,
            module=module,
            case_name=case_name,
        )

    def test_cuda_initialization_is_fail_closed_and_strictly_ordered(self) -> None:
        unavailable = _FakeCuda(available=False)
        with self.assertRaises(EvidenceValidationError) as raised:
            _initialize_cuda_device(SimpleNamespace(cuda=unavailable))
        self.assertEqual(raised.exception.code, "cuda_required")
        self.assertEqual(unavailable.calls, ["is_available"])

        no_devices = _FakeCuda(device_count=0)
        with self.assertRaises(EvidenceValidationError) as raised:
            _initialize_cuda_device(SimpleNamespace(cuda=no_devices))
        self.assertEqual(raised.exception.code, "cuda_device_missing")
        self.assertEqual(no_devices.calls, ["is_available", "device_count"])

        expected_order = [
            "is_available",
            "device_count",
            "init",
            "set_device:0",
            "current_device",
            "get_device_name:0",
            "get_device_properties:0",
            "empty_cache",
            "reset_peak_memory_stats:0",
        ]
        successful = _FakeCuda()
        evidence = _initialize_cuda_device(SimpleNamespace(cuda=successful))
        self.assertEqual(successful.calls, expected_order)
        self.assertEqual(
            evidence,
            {
                "name": "NVIDIA controlled fixture",
                "device_index": 0,
                "device_count": 1,
                "total_memory_bytes": 24_000_000_000,
                "capability": "8.9",
            },
        )

        repeated = _initialize_cuda_device(SimpleNamespace(cuda=successful))
        self.assertEqual(repeated, evidence)
        self.assertEqual(successful.calls, expected_order + expected_order)

    def test_cuda_initialization_failures_propagate_without_reset(self) -> None:
        for failure in ("init", "set_device:0"):
            with self.subTest(failure=failure):
                cuda = _FakeCuda(fail_on=failure)
                with self.assertRaisesRegex(
                    RuntimeError,
                    f"controlled {failure} failure",
                ):
                    _initialize_cuda_device(SimpleNamespace(cuda=cuda))
                self.assertNotIn("reset_peak_memory_stats:0", cuda.calls)

        mismatch = _FakeCuda(current_device=1)
        with self.assertRaises(EvidenceValidationError) as raised:
            _initialize_cuda_device(SimpleNamespace(cuda=mismatch))
        self.assertEqual(
            raised.exception.code,
            "cuda_device_selection_mismatch",
        )
        self.assertNotIn("get_device_name:0", mismatch.calls)
        self.assertNotIn("reset_peak_memory_stats:0", mismatch.calls)

        reset_failure = _FakeCuda(fail_on="reset_peak_memory_stats:0")
        with self.assertRaisesRegex(
            RuntimeError,
            "controlled reset_peak_memory_stats:0 failure",
        ):
            _initialize_cuda_device(SimpleNamespace(cuda=reset_failure))
        self.assertEqual(
            reset_failure.calls[-3:],
            [
                "get_device_properties:0",
                "empty_cache",
                "reset_peak_memory_stats:0",
            ],
        )

    def test_all_cuda_reset_paths_use_initialization_helper(self) -> None:
        module_source = inspect.getsource(phase2_aws_module)
        helper_source = inspect.getsource(_initialize_cuda_device)
        loader_source = inspect.getsource(
            phase2_aws_module._load_model_with_key_evidence
        )
        rollout_source = inspect.getsource(phase2_aws_module.execute_rollout)
        teacher_source = inspect.getsource(
            phase2_aws_module.execute_teacher_forced
        )

        self.assertEqual(module_source.count("reset_peak_memory_stats("), 1)
        self.assertIn("reset_peak_memory_stats(device_index)", helper_source)
        self.assertLess(
            helper_source.index("cuda.init()"),
            helper_source.index("reset_peak_memory_stats"),
        )
        self.assertLess(
            helper_source.index("cuda.set_device(device_index)"),
            helper_source.index("reset_peak_memory_stats"),
        )
        self.assertLess(
            loader_source.index("_initialize_cuda_device(torch)"),
            loader_source.index("instantiate_from_config"),
        )
        self.assertLess(
            rollout_source.index("_require_cuda"),
            rollout_source.index("upstream_utils.load_model"),
        )
        self.assertLess(
            teacher_source.index("_require_cuda"),
            teacher_source.index("_load_model_with_key_evidence"),
        )

    @staticmethod
    def _complete_action_provenance(
        provenance: dict[str, object],
        *,
        generated_metadata: Path,
        generated_video: Path,
    ) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
        complete = deepcopy(provenance)
        original = complete["original"]
        derived = complete["derived"]
        generated_metadata.write_bytes(Path(derived["path"]).read_bytes())
        generated_video.write_bytes(b"controlled generated-video fixture")
        complete["generated"] = {
            "classification": "generated",
            "path": str(generated_metadata.resolve()),
            "size_bytes": generated_metadata.stat().st_size,
            "sha256": sha256_file(generated_metadata),
            "row_count": derived["row_count"],
            "relationship_to_generated_mp4":
                "paired_action_metadata_for_generated_video",
            "generated_video_sha256": sha256_file(generated_video),
            "relationship_to_original":
                "derived_from_original_via_compatibility_jsonl",
            "original_jsonl_sha256": original["sha256"],
            "relationship_to_derived":
                "byte_identical_copy_of_derived_jsonl",
            "derived_jsonl_sha256": derived["sha256"],
            "materialization_method":
                "project_owned_byte_copy_of_derived_jsonl",
        }
        inputs = [
            {
                "role": "input_jsonl",
                "path": original["path"],
                "size_bytes": original["size_bytes"],
                "sha256": original["sha256"],
            }
        ]
        outputs = [
            artifact_record("paired_metadata", generated_metadata),
            artifact_record("generated_video", generated_video),
        ]
        return complete, inputs, outputs

    def test_cli_parsing_and_teacher_repeat_default(self) -> None:
        common = _common_cli_arguments(self.tmp_path)
        rollout = build_rollout_parser().parse_args(
            common
            + [
                "--input-mp4",
                str(self.tmp_path / "input.mp4"),
                "--input-jsonl",
                str(self.tmp_path / "input.jsonl"),
            ]
        )
        self.assertEqual(rollout.run_id, "phase2-test-run")
        self.assertEqual(rollout.context_frames, 8)

        architecture = build_architecture_parser().parse_args(common)
        self.assertEqual(architecture.seed, 7)

        teacher = build_teacher_forced_parser().parse_args(
            common
            + [
                "--input-id",
                "accepted-sample",
                "--input-kind",
                "accepted",
                "--input-mp4",
                str(self.tmp_path / "input.mp4"),
                "--input-jsonl",
                str(self.tmp_path / "input.jsonl"),
                "--input-mp4-sha256",
                SHA256,
                "--input-jsonl-sha256",
                SHA256,
            ]
        )
        self.assertEqual(teacher.repeats, 2)
        self.assertEqual(teacher.precision, "float16")

    def test_cli_required_arguments_fail_closed(self) -> None:
        for parser in (
            build_rollout_parser(),
            build_architecture_parser(),
            build_teacher_forced_parser(),
        ):
            with self.subTest(parser=parser.prog):
                with redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        parser.parse_args([])

    def test_teacher_repeat_count_rejected_during_parsing(self) -> None:
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                build_teacher_forced_parser().parse_args(
                    _common_cli_arguments(self.tmp_path)
                    + [
                        "--input-id",
                        "accepted-sample",
                        "--input-kind",
                        "accepted",
                        "--input-mp4",
                        "input.mp4",
                        "--input-jsonl",
                        "input.jsonl",
                        "--input-mp4-sha256",
                        SHA256,
                        "--input-jsonl-sha256",
                        SHA256,
                        "--repeats",
                        "1",
                    ]
                )

    def test_schema_is_versioned_and_keeps_frozen_schema_version(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(
            schema["$defs"]["header"]["properties"]["schema_version"]["const"],
            "1.0",
        )
        self.assertEqual(
            schema["$defs"]["header"]["properties"]["evidence_schema_version"][
                "const"
            ],
            EVIDENCE_SCHEMA_VERSION,
        )
        self.assertEqual(len(schema["oneOf"]), 3)

    def test_pinned_gradio_preprocessing_is_exact_and_deterministic(self) -> None:
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        frame[:, :] = [7, 19, 233]
        original = frame.copy()
        fake_cv2 = _FakeCv2([frame])
        first, first_record = preprocess_rollout_frame(
            frame,
            source_frame_index=4,
            cv2_module=fake_cv2,
            numpy_module=np,
        )
        second, second_record = preprocess_rollout_frame(
            frame,
            source_frame_index=4,
            cv2_module=fake_cv2,
            numpy_module=np,
        )

        self.assertEqual(first.shape, (224, 384, 3))
        self.assertEqual(first.dtype, np.uint8)
        self.assertTrue(np.all(first == np.array([233, 19, 7], dtype=np.uint8)))
        self.assertEqual(first.tobytes(), second.tobytes())
        self.assertEqual(first_record, second_record)
        self.assertEqual(first_record["source_frame_index"], 4)
        self.assertEqual(
            first_record["processed_sha256"],
            sha256_bytes(first.tobytes()),
        )
        self.assertEqual(
            fake_cv2.interpolations,
            [_FakeCv2.INTER_LINEAR, _FakeCv2.INTER_LINEAR],
        )
        np.testing.assert_array_equal(frame, original)

    def test_context_decode_preserves_frame_identity_cardinality_and_hashes(
        self,
    ) -> None:
        frames = [
            np.full((360, 640, 3), [index, index + 1, index + 2], np.uint8)
            for index in range(3)
        ]
        canonical = self.runtime_root / "canonical.mp4"
        canonical.write_bytes(b"canonical-video-fixture")
        before = canonical.read_bytes()
        first_cv2 = _FakeCv2(frames)
        processed, provenance = decode_and_preprocess_rollout_context(
            canonical,
            context_frames=3,
            cv2_module=first_cv2,
            numpy_module=np,
        )
        second, repeated = decode_and_preprocess_rollout_context(
            canonical,
            context_frames=3,
            cv2_module=_FakeCv2(frames),
            numpy_module=np,
        )

        self.assertEqual(canonical.read_bytes(), before)
        self.assertEqual(len(processed), 3)
        self.assertEqual([item.mean() for item in processed], [1.0, 2.0, 3.0])
        self.assertEqual(
            provenance["selected_source_frame_indices"],
            [0, 1, 2],
        )
        self.assertEqual(
            [record["source_frame_index"] for record in provenance["frame_records"]],
            [0, 1, 2],
        )
        self.assertEqual(provenance["processed_frame_count"], 3)
        self.assertEqual(provenance["frames_dropped"], 0)
        self.assertEqual(provenance["frames_added"], 0)
        self.assertEqual(provenance["frames_duplicated"], 0)
        self.assertTrue(provenance["frame_order_preserved"])
        self.assertEqual(
            provenance["processed_frames_sha256"],
            repeated["processed_frames_sha256"],
        )
        self.assertEqual(
            [item.tobytes() for item in processed],
            [item.tobytes() for item in second],
        )
        self.assertTrue(first_cv2.capture.released)
        self.assertEqual(
            first_cv2.interpolations,
            [
                _FakeCv2.INTER_LINEAR,
                _FakeCv2.INTER_LINEAR,
                _FakeCv2.INTER_LINEAR,
            ],
        )

    def test_frame_preprocessing_fails_closed_and_releases_capture(self) -> None:
        valid = np.zeros((360, 640, 3), dtype=np.uint8)
        invalid_frames = [
            (
                "shape",
                np.zeros((359, 640, 3), dtype=np.uint8),
                "invalid_source_frame_shape",
            ),
            (
                "dtype",
                np.zeros((360, 640, 3), dtype=np.float32),
                "invalid_source_frame_dtype",
            ),
        ]
        for name, frame, code in invalid_frames:
            with self.subTest(name=name):
                with self.assertRaises(EvidenceValidationError) as raised:
                    preprocess_rollout_frame(
                        frame,
                        source_frame_index=0,
                        cv2_module=_FakeCv2([frame]),
                        numpy_module=np,
                    )
                self.assertEqual(raised.exception.code, code)

        for name, frames in (
            ("failed_decode", [valid, None]),
            ("short_video", [valid]),
        ):
            with self.subTest(name=name):
                fake_cv2 = _FakeCv2(frames)
                with self.assertRaises(EvidenceValidationError) as raised:
                    decode_and_preprocess_rollout_context(
                        self.runtime_root / f"{name}.mp4",
                        context_frames=2,
                        cv2_module=fake_cv2,
                        numpy_module=np,
                    )
                self.assertEqual(raised.exception.code, "video_decode_failed")
                self.assertTrue(fake_cv2.capture.released)

        failed_seek = _FakeCv2([valid])
        failed_seek.capture.set = lambda property_id, value: False
        with self.assertRaises(EvidenceValidationError) as raised:
            decode_and_preprocess_rollout_context(
                self.runtime_root / "failed-seek.mp4",
                context_frames=1,
                cv2_module=failed_seek,
                numpy_module=np,
            )
        self.assertEqual(raised.exception.code, "video_seek_failed")
        self.assertTrue(failed_seek.capture.released)

    def test_token_shapes_and_position_budget_fail_before_prefill(self) -> None:
        budget = validate_rollout_position_budget(
            context_frames=8,
            raw_visual_token_shape=(8, 14, 24),
            flattened_visual_token_shape=(1, 8, 336),
            action_token_shape=(1, 1, 11),
            max_position_embeddings=5552,
        )
        self.assertEqual(budget["visual_tokens_per_frame"], 336)
        self.assertEqual(budget["total_visual_prompt_tokens"], 8 * 336)
        self.assertEqual(budget["prompt_positions"], 8 * 336 + 11)
        self.assertEqual(
            budget["conservative_position_budget"],
            8 * 336 + 11 + 336,
        )
        self.assertEqual(budget["conservative_position_budget"], 3035)
        self.assertEqual(budget["position_budget_status"], "PASS")

        invalid_cases = [
            (
                "335_visual",
                {
                    "raw_visual_token_shape": (8, 5, 67),
                    "flattened_visual_token_shape": (1, 8, 335),
                },
                "invalid_visual_token_shape",
            ),
            (
                "337_visual",
                {
                    "raw_visual_token_shape": (8, 337, 1),
                    "flattened_visual_token_shape": (1, 8, 337),
                },
                "invalid_visual_token_shape",
            ),
            (
                "10_actions",
                {"action_token_shape": (1, 1, 10)},
                "invalid_action_token_shape",
            ),
            (
                "12_actions",
                {"action_token_shape": (1, 1, 12)},
                "invalid_action_token_shape",
            ),
            (
                "wrong_config",
                {"max_position_embeddings": 5553},
                "max_position_embeddings_mismatch",
            ),
            (
                "overflow",
                {
                    "context_frames": 16,
                    "raw_visual_token_shape": (16, 14, 24),
                    "flattened_visual_token_shape": (1, 16, 336),
                },
                "position_budget_overflow",
            ),
        ]
        defaults = {
            "context_frames": 8,
            "raw_visual_token_shape": (8, 14, 24),
            "flattened_visual_token_shape": (1, 8, 336),
            "action_token_shape": (1, 1, 11),
            "max_position_embeddings": 5552,
        }
        for name, changes, code in invalid_cases:
            with self.subTest(name=name):
                arguments = defaults | changes
                with self.assertRaises(EvidenceValidationError) as raised:
                    validate_rollout_position_budget(**arguments)
                self.assertEqual(raised.exception.code, code)

    def test_video_preprocessing_provenance_is_separate_and_non_mutating(
        self,
    ) -> None:
        document = _rollout_document(self.runtime_root)
        provenance = document["video_preprocessing"]
        before = deepcopy(provenance)
        rejections = validate_video_preprocessing_provenance(
            provenance,
            inputs=document["inputs"],
            identity=document["identity"],
            verify_bytes=True,
        )
        self.assertEqual(rejections, ())
        self.assertEqual(provenance, before)
        self.assertEqual(provenance["original"]["classification"], "original")
        self.assertEqual(provenance["derived"]["classification"], "derived")
        self.assertEqual(
            provenance["derived"]["transformation_name"],
            VIDEO_PREPROCESSING_TRANSFORMATION,
        )
        self.assertEqual(
            provenance["derived"]["transformation_version"],
            VIDEO_PREPROCESSING_VERSION,
        )
        self.assertEqual(
            provenance["derived"]["processed_frame_shape"],
            [224, 384, 3],
        )
        self.assertEqual(
            provenance["tokenization"]["conservative_position_budget"],
            3035,
        )
        self.assertEqual(
            {item["role"] for item in document["outputs"]},
            {"generated_video", "paired_metadata", "raw_stdout_stderr"},
        )

    def test_video_preprocessing_provenance_mutations_fail_closed(self) -> None:
        document = _rollout_document(self.runtime_root)
        base = document["video_preprocessing"]
        cases = []
        missing = deepcopy(base)
        del missing["derived"]["transformation_version"]
        cases.append(("missing", missing, "missing_required_field"))
        wrong_classification = deepcopy(base)
        wrong_classification["derived"]["classification"] = "original"
        cases.append(
            (
                "classification",
                wrong_classification,
                "invalid_video_preprocessing_contract",
            )
        )
        wrong_order = deepcopy(base)
        wrong_order["derived"]["selected_source_frame_indices"] = list(
            reversed(range(8))
        )
        cases.append(("order", wrong_order, "frame_cardinality_mismatch"))
        wrong_shape = deepcopy(base)
        wrong_shape["derived"]["processed_frame_shape"] = [360, 640, 3]
        cases.append(
            ("processed_shape", wrong_shape, "invalid_video_preprocessing_contract")
        )
        wrong_hash = deepcopy(base)
        wrong_hash["derived"]["processed_frames_sha256"] = "not-a-hash"
        cases.append(
            ("processed_hash", wrong_hash, "invalid_processed_frame_integrity")
        )
        wrong_budget = deepcopy(base)
        wrong_budget["tokenization"]["conservative_position_budget"] = 5553
        cases.append(("position_budget", wrong_budget, "invalid_position_budget"))
        wrong_token_count = deepcopy(base)
        wrong_token_count["tokenization"]["visual_tokens_per_frame"] = 335
        cases.append(("token_count", wrong_token_count, "invalid_position_budget"))

        for name, value, code in cases:
            with self.subTest(name=name):
                codes = {
                    item.code
                    for item in validate_video_preprocessing_provenance(
                        value,
                        inputs=document["inputs"],
                        identity=document["identity"],
                    )
                }
                self.assertIn(code, codes)

    def test_action_conversion_is_deterministic_ordered_and_complete(self) -> None:
        rows = [
            _raw_action(keys=["key.keyboard.w"], buttons=[0], dx=1, dy=-2),
            _raw_action(keys=["key.keyboard.s"], buttons=[1], dx=3.5, dy=4),
            _raw_action(keys=["key.keyboard.a"], buttons=[], dx=0, dy=0),
        ]
        original, first_path, first = self._convert_rows(
            rows, case_name="deterministic_first"
        )
        original_bytes = original.read_bytes()
        second_path = self.runtime_root / "deterministic_second" / "scene.jsonl"
        second = convert_action_jsonl_for_pinned_inference(
            original,
            second_path,
            mcdataset_module=_fake_mcdataset_module(),
            asset_revision=PINNED_ASSET_REVISION,
            expected_original_size_bytes=len(original_bytes),
            expected_original_sha256=sha256_bytes(original_bytes),
        )

        self.assertEqual(first_path.read_bytes(), second_path.read_bytes())
        self.assertEqual(first["derived"]["sha256"], second["derived"]["sha256"])
        self.assertEqual(original.read_bytes(), original_bytes)
        self.assertEqual(first["original"]["pre_size_bytes"], len(original_bytes))
        self.assertEqual(first["original"]["post_size_bytes"], len(original_bytes))
        self.assertEqual(first["original"]["pre_sha256"], sha256_bytes(original_bytes))
        self.assertEqual(first["original"]["post_sha256"], sha256_bytes(original_bytes))
        self.assertTrue(first["original"]["canonical_input"])
        self.assertTrue(first["original"]["unchanged"])
        self.assertEqual(first["original"]["row_count"], 3)
        self.assertEqual(first["derived"]["row_count"], 3)
        self.assertEqual(first["derived"]["rows_dropped"], 0)
        self.assertEqual(first["derived"]["rows_added"], 0)
        self.assertTrue(first["derived"]["row_order_preserved"])
        self.assertEqual(
            first["derived"]["storage_classification"],
            "runtime_only_outside_git",
        )
        self.assertEqual(first["derived"]["size_bytes"], first_path.stat().st_size)
        self.assertEqual(first["derived"]["sha256"], sha256_file(first_path))
        self.assertEqual(
            first["derived"]["parent_original_sha256"],
            first["original"]["sha256"],
        )

        derived_rows = []
        for line in first_path.read_text(encoding="utf-8").splitlines():
            # Controlled bytes were emitted by the strict adapter immediately above.
            parsed = eval(
                line,
                {"__builtins__": None},
                {"array": lambda items: items},
            )
            derived_rows.append(parsed)
            self.assertNotIn("true", line)
            self.assertNotIn("false", line)
            self.assertNotIn("null", line)
        self.assertEqual(len(derived_rows), 3)
        self.assertEqual(
            [
                (row["forward"], row["back"], row["left"])
                for row in derived_rows
            ],
            [(1, 0, 0), (0, 1, 0), (0, 0, 1)],
        )
        self.assertEqual(set(derived_rows[0]), set(_FAKE_NOOP_ACTION))

    def test_json_booleans_and_unused_null_do_not_enter_derived_actions(self) -> None:
        row = _raw_action()
        row["isGuiOpen"] = True
        row["isGuiInventory"] = False
        row["unused_nullable_state"] = None
        _, derived, provenance = self._convert_rows(
            [row], case_name="json_primitives"
        )
        parsed = json.loads(derived.read_text(encoding="utf-8"))
        self.assertEqual(set(parsed), set(_FAKE_NOOP_ACTION))
        self.assertNotIn("isGuiOpen", parsed)
        self.assertNotIn("unused_nullable_state", parsed)
        self.assertEqual(provenance["original"]["row_count"], 1)

    def test_missing_action_events_use_pinned_noop_normalization(self) -> None:
        _, derived, _ = self._convert_rows(
            [_raw_action(keys=[], buttons=[], dx=0, dy=0)],
            case_name="noop_normalization",
        )
        action = json.loads(derived.read_text(encoding="utf-8"))
        self.assertEqual(action["camera"], [0.0, 0.0])
        self.assertTrue(
            all(value == 0 for key, value in action.items() if key != "camera")
        )

    def test_malformed_action_inputs_fail_closed_with_stable_codes(self) -> None:
        raw_cases: list[tuple[str, bytes, str]] = [
            ("malformed", b'{"keyboard":\n', "malformed_action_json"),
            (
                "blank",
                (
                    json.dumps(_raw_action())
                    + "\n\n"
                    + json.dumps(_raw_action())
                    + "\n"
                ).encode("utf-8"),
                "blank_action_row",
            ),
            ("nondict", b"[]\n", "invalid_action_row"),
            (
                "missing_keyboard",
                json.dumps({"mouse": {"dx": 0, "dy": 0, "buttons": []}}).encode()
                + b"\n",
                "invalid_keyboard_action",
            ),
            (
                "missing_camera_source",
                json.dumps(
                    {"keyboard": {"keys": []}, "mouse": {"buttons": [], "dx": 0}}
                ).encode()
                + b"\n",
                "invalid_camera_value",
            ),
            (
                "null_camera",
                json.dumps(_raw_action(dx=None)).encode() + b"\n",
                "invalid_camera_value",
            ),
            (
                "string_camera",
                json.dumps(_raw_action(dx="2")).encode() + b"\n",
                "invalid_camera_value",
            ),
            (
                "nested_camera",
                json.dumps(_raw_action(dx={"value": 2})).encode() + b"\n",
                "invalid_camera_value",
            ),
            (
                "nan_camera",
                b'{"keyboard":{"keys":[]},"mouse":{"buttons":[],"dx":NaN,"dy":0}}\n',
                "malformed_action_json",
            ),
            (
                "positive_infinity",
                b'{"keyboard":{"keys":[]},"mouse":{"buttons":[],"dx":1e999,"dy":0}}\n',
                "invalid_camera_value",
            ),
            (
                "negative_infinity",
                b'{"keyboard":{"keys":[]},"mouse":{"buttons":[],"dx":-1e999,"dy":0}}\n',
                "invalid_camera_value",
            ),
            (
                "invalid_keyboard_type",
                json.dumps(_raw_action(keys=[1])).encode() + b"\n",
                "unsupported_keyboard_key",
            ),
            (
                "unknown_keyboard_string",
                json.dumps(_raw_action(keys=["key.keyboard.unknown"])).encode() + b"\n",
                "unsupported_keyboard_key",
            ),
            (
                "nested_keyboard",
                json.dumps(_raw_action(keys=[["key.keyboard.w"]])).encode() + b"\n",
                "unsupported_keyboard_key",
            ),
            (
                "null_buttons",
                json.dumps(
                    {
                        "keyboard": {"keys": []},
                        "mouse": {"buttons": None, "dx": 0, "dy": 0},
                    }
                ).encode()
                + b"\n",
                "invalid_mouse_buttons",
            ),
            (
                "boolean_button",
                json.dumps(_raw_action(buttons=[True])).encode() + b"\n",
                "invalid_mouse_button",
            ),
            (
                "unknown_button",
                json.dumps(_raw_action(buttons=[3])).encode() + b"\n",
                "invalid_mouse_button",
            ),
            (
                "nested_button",
                json.dumps(_raw_action(buttons=[[0]])).encode() + b"\n",
                "invalid_mouse_button",
            ),
        ]
        for index, (name, payload, code) in enumerate(raw_cases):
            with self.subTest(name=name):
                with self.assertRaises(EvidenceValidationError) as raised:
                    self._convert_payload(
                        payload,
                        case_name=f"invalid_raw_{index}",
                    )
                self.assertEqual(raised.exception.code, code)

    def test_invalid_normalized_actions_and_nondeterminism_fail_closed(self) -> None:
        mutations = [
            (
                "missing_camera",
                lambda action: action.pop("camera"),
                "incomplete_normalized_action",
            ),
            (
                "short_camera",
                lambda action: action.update(camera=[0]),
                "invalid_camera",
            ),
            (
                "string_camera",
                lambda action: action.update(camera=["0", 0]),
                "invalid_camera_value",
            ),
            (
                "nan_camera",
                lambda action: action.update(camera=[math.nan, 0]),
                "invalid_camera_value",
            ),
            (
                "positive_infinity",
                lambda action: action.update(camera=[math.inf, 0]),
                "invalid_camera_value",
            ),
            (
                "negative_infinity",
                lambda action: action.update(camera=[-math.inf, 0]),
                "invalid_camera_value",
            ),
            (
                "invalid_binary",
                lambda action: action.update(forward=2),
                "invalid_binary_action",
            ),
            (
                "nested_binary",
                lambda action: action.update(forward={"value": 1}),
                "invalid_binary_action",
            ),
            (
                "unknown_field",
                lambda action: action.update(filename="shortcut"),
                "incomplete_normalized_action",
            ),
        ]
        for index, (name, mutation, code) in enumerate(mutations):
            with self.subTest(name=name):
                with self.assertRaises(EvidenceValidationError) as raised:
                    self._convert_rows(
                        [_raw_action()],
                        module=_fake_mcdataset_module(mutation),
                        case_name=f"invalid_flat_{index}",
                    )
                self.assertEqual(raised.exception.code, code)

        with self.assertRaises(EvidenceValidationError) as raised:
            self._convert_rows(
                [_raw_action()],
                module=_fake_mcdataset_module(nondeterministic=True),
                case_name="nondeterministic",
            )
        self.assertEqual(
            raised.exception.code,
            "nondeterministic_action_conversion",
        )

    def test_original_locked_identity_mismatch_fails_before_conversion(self) -> None:
        case_root = self.runtime_root / "identity_mismatch"
        case_root.mkdir()
        original = case_root / "scene.jsonl"
        original.write_text(json.dumps(_raw_action()) + "\n", encoding="utf-8")
        for index, (expected_size, expected_hash) in enumerate((
            (original.stat().st_size + 1, sha256_file(original)),
            (original.stat().st_size, "f" * 64),
        )):
            with self.subTest(size=expected_size, sha=expected_hash):
                with self.assertRaises(EvidenceValidationError) as raised:
                    convert_action_jsonl_for_pinned_inference(
                        original,
                        case_root / f"runtime-{index}" / "scene.jsonl",
                        mcdataset_module=_fake_mcdataset_module(),
                        asset_revision=PINNED_ASSET_REVISION,
                        expected_original_size_bytes=expected_size,
                        expected_original_sha256=expected_hash,
                    )
                self.assertEqual(
                    raised.exception.code,
                    "original_action_identity_mismatch",
                )

    def test_action_provenance_is_complete_linked_and_non_mutating(self) -> None:
        original, _, partial = self._convert_rows(
            [_raw_action(keys=["key.keyboard.w"])],
            case_name="provenance_valid",
        )
        complete, inputs, outputs = self._complete_action_provenance(
            partial,
            generated_metadata=self.runtime_root / "generated.jsonl",
            generated_video=self.runtime_root / "generated.mp4",
        )
        before = deepcopy(complete)
        rejections = validate_action_compatibility_provenance(
            complete,
            inputs=inputs,
            outputs=outputs,
            identity={"asset_revision": PINNED_ASSET_REVISION},
            verify_bytes=True,
        )
        self.assertEqual(rejections, ())
        self.assertEqual(complete, before)
        self.assertTrue(complete["original"]["canonical_input"])
        self.assertEqual(
            complete["derived"]["transformation_name"],
            ACTION_COMPATIBILITY_TRANSFORMATION,
        )
        self.assertEqual(
            complete["derived"]["transformation_version"],
            ACTION_COMPATIBILITY_VERSION,
        )
        self.assertEqual(
            complete["derived"]["parent_original_sha256"],
            complete["original"]["sha256"],
        )
        self.assertEqual(
            complete["generated"]["original_jsonl_sha256"],
            complete["original"]["sha256"],
        )
        self.assertEqual(
            complete["generated"]["derived_jsonl_sha256"],
            complete["derived"]["sha256"],
        )
        self.assertEqual(
            original.read_bytes(),
            Path(complete["original"]["path"]).read_bytes(),
        )

    def test_action_provenance_mutation_and_malformed_claims_fail_closed(self) -> None:
        original, derived, partial = self._convert_rows(
            [_raw_action()],
            case_name="provenance_negative",
        )
        generated = self.runtime_root / "negative-generated.jsonl"
        video = self.runtime_root / "negative-generated.mp4"
        complete, inputs, outputs = self._complete_action_provenance(
            partial,
            generated_metadata=generated,
            generated_video=video,
        )
        identity = {"asset_revision": PINNED_ASSET_REVISION}

        malformed_cases = []
        missing = deepcopy(complete)
        del missing["derived"]["transformation_version"]
        malformed_cases.append(("missing", missing, "missing_required_field"))
        wrong_class = deepcopy(complete)
        wrong_class["derived"]["classification"] = "original"
        malformed_cases.append(
            ("classification", wrong_class, "invalid_provenance_classification")
        )
        wrong_hash = deepcopy(complete)
        wrong_hash["derived"]["sha256"] = "f" * 64
        malformed_cases.append(("hash", wrong_hash, "invalid_action_cardinality"))
        wrong_size = deepcopy(complete)
        wrong_size["generated"]["size_bytes"] += 1
        malformed_cases.append(("size", wrong_size, "broken_generated_action_lineage"))
        wrong_count = deepcopy(complete)
        wrong_count["derived"]["row_count"] += 1
        malformed_cases.append(
            ("row_count", wrong_count, "invalid_action_cardinality")
        )
        wrong_order = deepcopy(complete)
        wrong_order["derived"]["row_order_preserved"] = False
        malformed_cases.append(
            ("row_order", wrong_order, "invalid_action_cardinality")
        )
        malformed_cases.append(
            ("asset_revision", deepcopy(complete), "asset_revision_provenance_mismatch")
        )

        for name, value, code in malformed_cases:
            with self.subTest(name=name):
                current_identity = (
                    {"asset_revision": "c" * 40}
                    if name == "asset_revision"
                    else identity
                )
                codes = {
                    item.code
                    for item in validate_action_compatibility_provenance(
                        value,
                        inputs=inputs,
                        outputs=outputs,
                        identity=current_identity,
                    )
                }
                self.assertIn(code, codes)

        false_counts = deepcopy(complete)
        false_counts["original"]["row_count"] = 9
        false_counts["derived"]["row_count"] = 9
        false_counts["generated"]["row_count"] = 9
        codes = {
            item.code
            for item in validate_action_compatibility_provenance(
                false_counts,
                inputs=inputs,
                outputs=outputs,
                identity=identity,
                verify_bytes=True,
            )
        }
        self.assertIn("action_sequence_integrity_mismatch", codes)

        original_bytes = original.read_bytes()
        original.write_bytes(original_bytes + b" ")
        codes = {
            item.code
            for item in validate_action_compatibility_provenance(
                complete,
                inputs=inputs,
                outputs=outputs,
                identity=identity,
                verify_bytes=True,
            )
        }
        self.assertIn("provenance_integrity_mismatch", codes)
        original.write_bytes(original_bytes)

        derived_bytes = derived.read_bytes()
        derived.write_bytes(derived_bytes + b" ")
        codes = {
            item.code
            for item in validate_action_compatibility_provenance(
                complete,
                inputs=inputs,
                outputs=outputs,
                identity=identity,
                verify_bytes=True,
            )
        }
        self.assertIn("provenance_integrity_mismatch", codes)
        derived.write_bytes(derived_bytes)

    def test_runtime_constants_match_the_committed_asset_lock(self) -> None:
        lock = json.loads(
            (ROOT / "configs" / "assets" / "mineworld_assets_v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            lock["source"]["revision"].lower(),
            PINNED_ASSET_REVISION,
        )
        self.assertEqual(
            lock["files"]["checkpoints/700M_16f.ckpt"]["sha256"].lower(),
            PINNED_MAIN_CHECKPOINT_SHA256,
        )
        self.assertEqual(
            lock["files"]["checkpoints/vae/config.json"]["sha256"].lower(),
            PINNED_VAE_CONFIG_SHA256,
        )
        self.assertEqual(
            lock["files"]["checkpoints/vae/vae.ckpt"]["sha256"].lower(),
            PINNED_VAE_CHECKPOINT_SHA256,
        )
        self.assertEqual(
            lock["files"]["gradio_scene/scene.mp4"]["size_bytes"],
            PINNED_INPUT_MP4_SIZE_BYTES,
        )
        self.assertEqual(
            lock["files"]["gradio_scene/scene.mp4"]["sha256"].lower(),
            PINNED_INPUT_MP4_SHA256,
        )
        self.assertEqual(
            PINNED_SOURCE_REVISION,
            "9f49efbcc68a5f0cf60e78f0abc566eac409282f",
        )

    def test_hashing_uses_literal_bytes(self) -> None:
        path = FIXTURES / "ffprobe_valid.json"
        literal = path.read_bytes()
        expected = (
            "ba7816bf8f01cfea414140de5dae2223"
            "b00361a396177a9cb410ff61f20015ad"
        )
        self.assertEqual(sha256_bytes(b"abc"), expected)
        self.assertEqual(sha256_file(path), sha256_bytes(literal))
        self.assertNotEqual(sha256_file(path), expected)

    def test_ffprobe_fixture_parses_canonically(self) -> None:
        payload = (FIXTURES / "ffprobe_valid.json").read_text(encoding="utf-8")
        self.assertEqual(
            parse_ffprobe_output(payload),
            {
                "width": 640,
                "height": 360,
                "r_frame_rate": "6/1",
                "avg_frame_rate": "6/1",
                "duration_seconds": 0.166667,
                "declared_frames": 1,
                "decoded_frames": 1,
            },
        )

    def test_ffprobe_invalid_fixture_fails_closed(self) -> None:
        payload = (FIXTURES / "ffprobe_invalid.json").read_text(encoding="utf-8")
        with self.assertRaises(ValueError):
            parse_ffprobe_output(payload)

    def test_timing_fields_reject_bad_values(self) -> None:
        valid = {
            "model_initialization_seconds": 2.0,
            "first_generated_frame_seconds": 1.0,
            "generation_kernel_seconds": 0.5,
            "total_runtime_seconds": 3.0,
        }
        self.assertEqual(validate_timing_fields(valid), ())
        self.assertEqual(
            {item.code for item in validate_timing_fields({**valid, "extra": 1})},
            {"unknown_field"},
        )
        malformed = deepcopy(valid)
        malformed["total_runtime_seconds"] = "3.0"
        self.assertIn(
            "invalid_timing",
            {item.code for item in validate_timing_fields(malformed)},
        )
        inconsistent = deepcopy(valid)
        inconsistent["total_runtime_seconds"] = 2.5
        self.assertIn(
            "inconsistent_timing",
            {item.code for item in validate_timing_fields(inconsistent)},
        )

    def test_rollout_identity_and_non_mutation(self) -> None:
        document = _rollout_document(self.runtime_root)
        before = deepcopy(document)
        result = validate_rollout_manifest(document, verify_output_bytes=True)
        self.assertTrue(result.accepted, result.rejections)
        self.assertEqual(document, before)

        missing = deepcopy(document)
        del missing["identity"]["environment_report_sha256"]
        result = validate_rollout_manifest(missing)
        self.assertFalse(result.accepted)
        self.assertTrue(
            any(item.code == "missing_required_field" for item in result.rejections)
        )

    def test_output_file_completeness_rehashes(self) -> None:
        document = _rollout_document(self.runtime_root)
        outputs = document["outputs"]
        self.assertEqual(validate_output_file_completeness(outputs), ())

        stale = deepcopy(outputs)
        stale[0]["sha256"] = "f" * 64
        self.assertIn(
            "output_integrity_mismatch",
            {item.code for item in validate_output_file_completeness(stale)},
        )

        missing = deepcopy(outputs)
        missing.pop()
        self.assertIn(
            "incomplete_outputs",
            {item.code for item in validate_output_file_completeness(missing)},
        )

    def test_architecture_assertions_reject_changed_facts(self) -> None:
        valid = _architecture_facts()
        self.assertEqual(validate_architecture_facts(valid), ())
        for field in (
            "layer_count",
            "hidden_size",
            "intermediate_size",
            "vocab_size",
            "max_position_embeddings",
            "num_attention_heads",
            "num_key_value_heads",
            "visual_tokens",
            "action_tokens",
            "tokens_per_pair",
            "context_pairs",
        ):
            with self.subTest(field=field):
                malformed = deepcopy(valid)
                malformed[field] = int(malformed[field]) + 1
                self.assertTrue(
                    any(
                        item.code == "architecture_mismatch"
                        for item in validate_architecture_facts(malformed)
                    )
                )

    def test_architecture_malformed_type_is_stable_rejection(self) -> None:
        malformed = _architecture_facts()
        malformed["hidden_size"] = ["2048"]
        self.assertTrue(
            any(
                item.code == "architecture_mismatch"
                for item in validate_architecture_facts(malformed)
            )
        )

    def test_exact_audited_checkpoint_profiles_pass(self) -> None:
        raw_load_state = _audited_raw_load_state()
        before = deepcopy(raw_load_state)
        classification = classify_checkpoint_load_state(
            raw_load_state,
            _pinned_identity(),
        )
        self.assertEqual(raw_load_state, before)
        self.assertEqual(classification["classification_status"], "PASS")
        self.assertEqual(classification["final_decision"], "PASS")
        self.assertEqual(
            classification["profile_id"],
            CHECKPOINT_LOAD_PROFILE_ID,
        )
        self.assertEqual(
            classification["profile_version"],
            CHECKPOINT_LOAD_PROFILE_VERSION,
        )
        self.assertTrue(classification["provenance_matches"])

        for component in ("transformer", "vae"):
            with self.subTest(component=component):
                observed = classification[component]
                profile = CHECKPOINT_LOAD_COMPONENT_PROFILES[component]
                self.assertEqual(observed["decision"], "PASS")
                self.assertEqual(observed["observed_missing_key_count"], 0)
                self.assertEqual(
                    observed["observed_unexpected_key_count"],
                    profile["expected_unexpected_key_count"],
                )
                self.assertEqual(
                    observed["sorted_key_list_sha256"],
                    profile["sorted_key_list_sha256"],
                )
                self.assertEqual(observed["unmatched_keys"], [])
                self.assertEqual(observed["duplicate_keys"], [])
                self.assertEqual(
                    observed["key_hash_serialization"],
                    CHECKPOINT_KEY_HASH_SERIALIZATION,
                )

    def test_checkpoint_profile_rejects_missing_unknown_extra_and_duplicate_keys(
        self,
    ) -> None:
        cases = []

        transformer_missing = _audited_raw_load_state()
        transformer_missing["transformer_missing_keys"].append(
            "transformer.required.weight"
        )
        cases.append(("transformer_missing", transformer_missing))

        vae_missing = _audited_raw_load_state()
        vae_missing["vae_missing_keys"].append("encoder.required.weight")
        cases.append(("vae_missing", vae_missing))

        unknown_transformer = _audited_raw_load_state()
        unknown_transformer["transformer_unexpected_keys"][0] = (
            "tokenizer.runtime_weight"
        )
        cases.append(("unknown_transformer", unknown_transformer))

        unknown_vae = _audited_raw_load_state()
        unknown_vae["vae_unexpected_keys"][0] = "decoder.runtime_weight"
        cases.append(("unknown_vae", unknown_vae))

        extra_transformer = _audited_raw_load_state()
        extra_transformer["transformer_unexpected_keys"].append(
            "tokenizer.metrics_fid.audit_extra"
        )
        cases.append(("extra_transformer", extra_transformer))

        missing_allowed = _audited_raw_load_state()
        missing_allowed["vae_unexpected_keys"].pop()
        cases.append(("missing_allowed", missing_allowed))

        duplicate = _audited_raw_load_state()
        duplicate["transformer_unexpected_keys"].append(
            duplicate["transformer_unexpected_keys"][0]
        )
        cases.append(("duplicate", duplicate))

        for name, load_state in cases:
            with self.subTest(name=name):
                classification = classify_checkpoint_load_state(
                    load_state,
                    _pinned_identity(),
                )
                self.assertEqual(classification["final_decision"], "FAIL")

        duplicate_classification = classify_checkpoint_load_state(
            duplicate,
            _pinned_identity(),
        )
        self.assertEqual(
            duplicate_classification["transformer"]["duplicate_keys"],
            [duplicate["transformer_unexpected_keys"][0]],
        )
        self.assertEqual(
            duplicate_classification["transformer"][
                "observed_unexpected_key_count"
            ],
            1202,
        )

    def test_checkpoint_profile_rejects_family_count_and_digest_changes(
        self,
    ) -> None:
        family_mismatch = _audited_raw_load_state()
        family_mismatch["transformer_unexpected_keys"][0] = (
            "tokenizer.metrics_is.audit_family_count_change"
        )
        classification = classify_checkpoint_load_state(
            family_mismatch,
            _pinned_identity(),
        )
        self.assertEqual(
            classification["transformer"]["decision"],
            "FAIL",
        )
        self.assertEqual(
            classification["transformer"]["observed_unexpected_key_count"],
            1201,
        )
        self.assertNotEqual(
            classification["transformer"]["observed_family_counts"],
            {
                prefix: count
                for prefix, count in CHECKPOINT_LOAD_COMPONENT_PROFILES[
                    "transformer"
                ]["allowed_families"]
            },
        )

        transformer_digest = _audited_raw_load_state()
        original_transformer_key = transformer_digest[
            "transformer_unexpected_keys"
        ][0]
        transformer_digest["transformer_unexpected_keys"][0] = (
            original_transformer_key + "_changed"
        )
        classification = classify_checkpoint_load_state(
            transformer_digest,
            _pinned_identity(),
        )
        self.assertEqual(
            classification["transformer"]["observed_unexpected_key_count"],
            1201,
        )
        self.assertNotEqual(
            classification["transformer"]["sorted_key_list_sha256"],
            classification["transformer"][
                "expected_sorted_key_list_sha256"
            ],
        )
        self.assertEqual(classification["transformer"]["decision"], "FAIL")

        vae_digest = _audited_raw_load_state()
        original_vae_key = vae_digest["vae_unexpected_keys"][0]
        vae_digest["vae_unexpected_keys"][0] = original_vae_key + "_changed"
        classification = classify_checkpoint_load_state(
            vae_digest,
            _pinned_identity(),
        )
        self.assertNotEqual(
            classification["vae"]["sorted_key_list_sha256"],
            classification["vae"]["expected_sorted_key_list_sha256"],
        )
        self.assertEqual(classification["vae"]["decision"], "FAIL")

    def test_checkpoint_key_hash_is_deterministic_and_order_independent(
        self,
    ) -> None:
        keys = _audited_raw_load_state()["transformer_unexpected_keys"]
        expected = (
            "9e9eb93cd04b24f4ef8faa4c2cdd1e6bd2c89a4a4a6eddfb11eedbb92c0734bf"
        )
        self.assertEqual(checkpoint_key_list_sha256(keys), expected)
        self.assertEqual(
            checkpoint_key_list_sha256(list(reversed(keys))),
            expected,
        )
        self.assertEqual(checkpoint_key_list_sha256(list(keys)), expected)

        malformed = _audited_raw_load_state()
        malformed["vae_unexpected_keys"][0] = 7
        with self.assertRaises(EvidenceValidationError) as raised:
            classify_checkpoint_load_state(
                malformed,
                _pinned_identity(),
            )
        self.assertEqual(raised.exception.code, "non_string_checkpoint_key")

    def test_checkpoint_profile_is_bound_to_all_pinned_provenance(self) -> None:
        for field in (
            "source_revision",
            "asset_revision",
            "main_checkpoint_sha256",
            "vae_checkpoint_sha256",
        ):
            with self.subTest(field=field):
                identity = _pinned_identity()
                identity[field] = (
                    "f" * 40 if field.endswith("revision") else "f" * 64
                )
                classification = classify_checkpoint_load_state(
                    _audited_raw_load_state(),
                    identity,
                )
                self.assertFalse(classification["provenance_matches"])
                self.assertEqual(
                    classification["classification_status"],
                    "FAIL",
                )
                self.assertEqual(classification["final_decision"], "FAIL")
                self.assertEqual(
                    classification["expected_provenance"][field],
                    CHECKPOINT_LOAD_PROFILE_PROVENANCE[field],
                )
                self.assertEqual(
                    classification["observed_provenance"][field],
                    identity[field],
                )

    def test_architecture_report_requires_recomputed_exact_profile(self) -> None:
        report = _architecture_report()
        before = deepcopy(report)
        result = validate_architecture_report(report)
        self.assertTrue(result.accepted, result.rejections)
        self.assertEqual(report, before)
        raw = _audited_raw_load_state()
        for field in raw:
            self.assertEqual(report["load_state"][field], raw[field])

        stale_classification = deepcopy(report)
        stale_classification["load_state"]["transformer_unexpected_keys"][0] += (
            "_changed"
        )
        stale_classification = seal_document(
            {
                key: value
                for key, value in stale_classification.items()
                if key != "manifest_integrity"
            }
        )
        codes = {
            rejection.code
            for rejection in validate_architecture_report(
                stale_classification
            ).rejections
        }
        self.assertIn("checkpoint_classification_mismatch", codes)
        self.assertIn("checkpoint_load_profile_mismatch", codes)

        failed_profile = deepcopy(stale_classification)
        raw_failed = {
            field: failed_profile["load_state"][field]
            for field in raw
        }
        failed_profile["load_state"]["classification"] = (
            classify_checkpoint_load_state(
                raw_failed,
                failed_profile["identity"],
            )
        )
        failed_profile = seal_document(
            {
                key: value
                for key, value in failed_profile.items()
                if key != "manifest_integrity"
            }
        )
        codes = {
            rejection.code
            for rejection in validate_architecture_report(
                failed_profile
            ).rejections
        }
        self.assertNotIn("checkpoint_classification_mismatch", codes)
        self.assertIn("checkpoint_load_profile_mismatch", codes)

    def test_checkpoint_classification_matches_runtime_schema_shape(self) -> None:
        report = _architecture_report()
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        definitions = schema["$defs"]
        load_definition = definitions["architectureLoadState"]
        classification_definition = definitions[
            "checkpointLoadClassification"
        ]
        component_definition = definitions[
            "checkpointComponentClassification"
        ]
        self.assertFalse(load_definition["additionalProperties"])
        self.assertFalse(classification_definition["additionalProperties"])
        self.assertFalse(component_definition["additionalProperties"])
        self.assertEqual(
            set(report["load_state"]),
            set(load_definition["required"]),
        )
        self.assertEqual(
            set(report["load_state"]["classification"]),
            set(classification_definition["required"]),
        )
        for component in ("transformer", "vae"):
            self.assertEqual(
                set(report["load_state"]["classification"][component]),
                set(component_definition["required"]),
            )
        self.assertEqual(
            schema["$defs"]["header"]["properties"]["schema_version"]["const"],
            "1.0",
        )

    def test_teacher_checkpoint_gate_accepts_exact_nonempty_audited_profile(
        self,
    ) -> None:
        report = _teacher_forced_report()
        load_state = report["load_state"]
        self.assertEqual(
            len(load_state["transformer_unexpected_keys"]),
            1201,
        )
        self.assertEqual(len(load_state["vae_unexpected_keys"]), 1250)
        self.assertTrue(load_state["classification"])
        self.assertEqual(
            load_state["classification"]["final_decision"],
            "PASS",
        )
        self.assertEqual(
            validate_checkpoint_load_state(
                load_state,
                report["identity"],
            ),
            (),
        )
        self.assertIsNone(
            _require_valid_checkpoint_load_state(
                load_state,
                report["identity"],
            )
        )
        teacher_source = inspect.getsource(
            phase2_aws_module.execute_teacher_forced
        )
        self.assertIn(
            "_require_valid_checkpoint_load_state",
            teacher_source,
        )
        self.assertNotIn(
            "field: values for field, values in load_state.items() if values",
            teacher_source,
        )

    def test_teacher_checkpoint_gate_recomputes_and_rejects_forged_evidence(
        self,
    ) -> None:
        valid_report = _teacher_forced_report()
        valid_load_state = valid_report["load_state"]
        identity = valid_report["identity"]
        cases = []

        forged_pass = deepcopy(valid_load_state)
        forged_pass["transformer_unexpected_keys"][0] += "_tampered"
        cases.append(("forged_pass", forged_pass, identity))

        missing_classification = deepcopy(valid_load_state)
        del missing_classification["classification"]
        cases.append(
            ("missing_classification", missing_classification, identity)
        )

        failed_decision = deepcopy(valid_load_state)
        failed_decision["classification"]["classification_status"] = "FAIL"
        failed_decision["classification"]["final_decision"] = "FAIL"
        cases.append(("failed_decision", failed_decision, identity))

        transformer_missing = deepcopy(valid_load_state)
        transformer_missing["transformer_missing_keys"].append(
            "transformer.required.weight"
        )
        transformer_missing["classification"] = (
            classify_checkpoint_load_state(
                {
                    field: transformer_missing[field]
                    for field in _audited_raw_load_state()
                },
                identity,
            )
        )
        cases.append(("transformer_missing", transformer_missing, identity))

        vae_missing = deepcopy(valid_load_state)
        vae_missing["vae_missing_keys"].append("vae.required.weight")
        cases.append(("vae_missing", vae_missing, identity))

        unknown_transformer = deepcopy(valid_load_state)
        unknown_transformer["transformer_unexpected_keys"][0] = (
            "tokenizer.runtime.weight"
        )
        cases.append(("unknown_transformer", unknown_transformer, identity))

        unknown_vae = deepcopy(valid_load_state)
        unknown_vae["vae_unexpected_keys"][0] = "decoder.runtime.weight"
        cases.append(("unknown_vae", unknown_vae, identity))

        additional_key = deepcopy(valid_load_state)
        additional_key["transformer_unexpected_keys"].append(
            "tokenizer.metrics_fid.additional"
        )
        cases.append(("additional_key", additional_key, identity))

        removed_key = deepcopy(valid_load_state)
        removed_key["vae_unexpected_keys"].pop()
        cases.append(("removed_key", removed_key, identity))

        duplicate_key = deepcopy(valid_load_state)
        duplicate_key["transformer_unexpected_keys"].append(
            duplicate_key["transformer_unexpected_keys"][0]
        )
        cases.append(("duplicate_key", duplicate_key, identity))

        non_string_key = deepcopy(valid_load_state)
        non_string_key["vae_unexpected_keys"][0] = 7
        cases.append(("non_string_key", non_string_key, identity))

        for field in (
            "source_revision",
            "asset_revision",
            "main_checkpoint_sha256",
            "vae_checkpoint_sha256",
        ):
            wrong_identity = deepcopy(identity)
            wrong_identity[field] = (
                "f" * 40 if field.endswith("revision") else "f" * 64
            )
            cases.append((f"wrong_{field}", valid_load_state, wrong_identity))

        for name, load_state, current_identity in cases:
            with self.subTest(name=name):
                with self.assertRaises(EvidenceValidationError) as raised:
                    _require_valid_checkpoint_load_state(
                        load_state,
                        current_identity,
                    )
                self.assertEqual(raised.exception.code, "state_dict_mismatch")

    def test_teacher_checkpoint_gate_is_order_independent(self) -> None:
        report = _teacher_forced_report()
        reordered = deepcopy(report["load_state"])
        reordered["transformer_unexpected_keys"].reverse()
        reordered["vae_unexpected_keys"].reverse()
        self.assertEqual(
            validate_checkpoint_load_state(
                reordered,
                report["identity"],
            ),
            (),
        )
        self.assertIsNone(
            _require_valid_checkpoint_load_state(
                reordered,
                report["identity"],
            )
        )

    def test_teacher_report_preserves_and_validates_checkpoint_evidence(
        self,
    ) -> None:
        report = _teacher_forced_report()
        before = deepcopy(report)
        result = validate_teacher_forced_report(report)
        self.assertTrue(result.accepted, result.rejections)
        self.assertEqual(report, before)
        self.assertEqual(
            report["load_state"],
            _architecture_report()["load_state"],
        )

        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        teacher_schema = schema["$defs"]["teacherForced"]["allOf"][1]
        self.assertIn("load_state", teacher_schema["required"])
        self.assertEqual(
            teacher_schema["properties"]["load_state"]["$ref"],
            "#/$defs/architectureLoadState",
        )

        malformed = deepcopy(report)
        malformed["load_state"]["classification"]["profile_version"] = "9.9"
        malformed = seal_document(
            {
                key: value
                for key, value in malformed.items()
                if key != "manifest_integrity"
            }
        )
        codes = {
            rejection.code
            for rejection in validate_teacher_forced_report(
                malformed
            ).rejections
        }
        self.assertIn("checkpoint_classification_mismatch", codes)

    def test_hook_records_exact_grid_and_non_mutation(self) -> None:
        records = _hook_records()
        before = deepcopy(records)
        positions_hash = sha256_bytes(canonical_json_bytes([0, 1, 2, 3]))
        arguments = {
            "repeats": 2,
            "expected_layers": 2,
            "sequence_length": 4,
            "hidden_size": 3,
            "expected_token_positions_sha256": positions_hash,
        }
        self.assertEqual(validate_hook_records(records, **arguments), ())
        self.assertEqual(records, before)

        duplicate = deepcopy(records)
        duplicate[-1] = deepcopy(duplicate[0])
        codes = {
            item.code for item in validate_hook_records(duplicate, **arguments)
        }
        self.assertIn("duplicate_hook", codes)
        self.assertIn("incomplete_hook_coverage", codes)

    def test_teacher_token_layout_has_exact_nonoverlapping_pair_ranges(self) -> None:
        layout = expected_teacher_token_layout()
        self.assertEqual(layout["sequence_length"], 5552)
        self.assertEqual(len(layout["positions"]), 5552)
        self.assertEqual(len(layout["pair_ranges"]), 16)
        for pair_index, pair_range in enumerate(layout["pair_ranges"]):
            with self.subTest(pair_index=pair_index):
                expected_start = pair_index * 347
                self.assertEqual(pair_range["pair_index"], pair_index)
                self.assertEqual(pair_range["visual_start"], expected_start)
                self.assertEqual(
                    pair_range["visual_end_exclusive"],
                    expected_start + 336,
                )
                self.assertEqual(pair_range["action_start"], expected_start + 336)
                self.assertEqual(
                    pair_range["action_end_exclusive"],
                    expected_start + 347,
                )

    def test_hook_summary_malformed_type_is_stable_rejection(self) -> None:
        records = _hook_records()
        records[0]["summary"]["mean"] = "not-a-number"
        positions_hash = sha256_bytes(canonical_json_bytes([0, 1, 2, 3]))
        codes = {
            item.code
            for item in validate_hook_records(
                records,
                repeats=2,
                expected_layers=2,
                sequence_length=4,
                hidden_size=3,
                expected_token_positions_sha256=positions_hash,
            )
        }
        self.assertIn("invalid_output_summary", codes)

    def test_hook_dtype_and_device_are_observed_not_caller_agnostic(self) -> None:
        records = _hook_records()
        records[0]["dtype"] = "torch.float32"
        records[1]["device"] = "cpu"
        positions_hash = sha256_bytes(canonical_json_bytes([0, 1, 2, 3]))
        codes = {
            item.code
            for item in validate_hook_records(
                records,
                repeats=2,
                expected_layers=2,
                sequence_length=4,
                hidden_size=3,
                expected_token_positions_sha256=positions_hash,
                expected_dtype="torch.float16",
                require_cuda=True,
            )
        }
        self.assertIn("hook_dtype_mismatch", codes)
        self.assertIn("hook_device_mismatch", codes)

    def test_repeatability_uses_required_tolerances(self) -> None:
        accepted = compare_numeric_sequences([1.0, 2.0], [1.0005, 2.0005])
        self.assertTrue(accepted["allclose"])
        self.assertEqual(accepted["rtol"], 1e-3)
        self.assertEqual(accepted["atol"], 1e-3)

        rejected = compare_numeric_sequences([1.0], [1.1])
        self.assertFalse(rejected["allclose"])
        self.assertEqual(rejected["reason"], "tolerance_exceeded")
        self.assertEqual(
            compare_numeric_sequences([1.0], [1.0, 2.0])["reason"],
            "length_mismatch",
        )

    def test_deterministic_serialization_and_non_aliasing(self) -> None:
        first = {"z": 1, "nested": {"b": 2, "a": 1}}
        second = {"nested": {"a": 1, "b": 2}, "z": 1}
        self.assertEqual(canonical_json_bytes(first), canonical_json_bytes(second))

        sealed = seal_document(first)
        first["nested"]["a"] = 99
        self.assertEqual(sealed["nested"]["a"], 1)
        self.assertEqual(
            canonical_json_bytes(sealed),
            canonical_json_bytes(seal_document(second)),
        )

    def test_manifest_tampering_fails_closed(self) -> None:
        document = _rollout_document(self.runtime_root)
        document["runtime"]["timings"]["total_runtime_seconds"] = 99.0
        result = validate_rollout_manifest(document)
        self.assertFalse(result.accepted)
        self.assertTrue(
            any(item.code == "manifest_hash_mismatch" for item in result.rejections)
        )

    def test_schema_catalog_names_all_evidence_types(self) -> None:
        schema_text = SCHEMA.read_text(encoding="utf-8")
        self.assertIn(ROLLOUT_EVIDENCE_TYPE, schema_text)
        self.assertIn(ARCHITECTURE_EVIDENCE_TYPE, schema_text)
        self.assertIn("phase2.8_2.9_teacher_forced", schema_text)


if __name__ == "__main__":
    unittest.main()
