from __future__ import annotations

import io
import json
import math
import tempfile
import unittest
from contextlib import redirect_stderr
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from mineocclude.models.phase2_aws import (
    ACTION_COMPATIBILITY_SERIALIZATION,
    ACTION_COMPATIBILITY_TRANSFORMATION,
    ACTION_COMPATIBILITY_VERSION,
    PINNED_ASSET_REVISION,
    PINNED_MAIN_CHECKPOINT_SHA256,
    PINNED_SOURCE_REVISION,
    PINNED_VAE_CHECKPOINT_SHA256,
    PINNED_VAE_CONFIG_SHA256,
    build_architecture_parser,
    build_rollout_parser,
    build_teacher_forced_parser,
    convert_action_jsonl_for_pinned_inference,
)
from mineocclude.models.phase2_evidence import (
    ARCHITECTURE_EVIDENCE_TYPE,
    EVIDENCE_SCHEMA_VERSION,
    ROLLOUT_EVIDENCE_TYPE,
    EvidenceValidationError,
    artifact_record,
    canonical_json_bytes,
    compare_numeric_sequences,
    expected_teacher_token_layout,
    parse_ffprobe_output,
    seal_document,
    sha256_bytes,
    sha256_file,
    validate_action_compatibility_provenance,
    validate_architecture_facts,
    validate_hook_records,
    validate_output_file_completeness,
    validate_rollout_manifest,
    validate_timing_fields,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "phase2"
SCHEMA = ROOT / "schemas" / "person_a" / "phase2_runtime_evidence_v1.schema.json"
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
                    "upstream_byte_copy_of_derived_jsonl",
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
                "upstream_byte_copy_of_derived_jsonl",
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
