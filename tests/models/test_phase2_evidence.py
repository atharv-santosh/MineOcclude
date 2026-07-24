from __future__ import annotations

import json
import io
import unittest
from contextlib import redirect_stderr
from copy import deepcopy
from pathlib import Path

from mineocclude.models.phase2_aws import (
    PINNED_ASSET_REVISION,
    PINNED_MAIN_CHECKPOINT_SHA256,
    PINNED_SOURCE_REVISION,
    PINNED_VAE_CHECKPOINT_SHA256,
    PINNED_VAE_CONFIG_SHA256,
    build_architecture_parser,
    build_rollout_parser,
    build_teacher_forced_parser,
)
from mineocclude.models.phase2_evidence import (
    ARCHITECTURE_EVIDENCE_TYPE,
    EVIDENCE_SCHEMA_VERSION,
    ROLLOUT_EVIDENCE_TYPE,
    artifact_record,
    canonical_json_bytes,
    compare_numeric_sequences,
    expected_teacher_token_layout,
    parse_ffprobe_output,
    seal_document,
    sha256_bytes,
    sha256_file,
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


def _rollout_document() -> dict[str, object]:
    shared_input = FIXTURES / "ffprobe_valid.json"
    generated = FIXTURES / "ffprobe_valid.json"
    paired = FIXTURES / "ffprobe_invalid.json"
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
        "inputs": [artifact_record(role, shared_input) for role in input_roles],
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
        self.tmp_path = FIXTURES

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
        document = _rollout_document()
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
        document = _rollout_document()
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
        document = _rollout_document()
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
