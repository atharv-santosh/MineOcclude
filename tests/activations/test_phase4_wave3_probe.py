"""CPU-only boundary tests for the prepared Wave 3 runtime probe."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run_phase4_wave3_extraction_probe.py"


def _load_probe():
    spec = importlib.util.spec_from_file_location(
        "phase4_wave3_probe",
        SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load Wave 3 probe")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _attempt(name, status, *, forced=False):
    callbacks = [1] * 20
    captures = list(range(20))
    failure = None
    accepted = True
    if forced:
        callbacks = [1] * 11 + [0] * 9
        captures = list(range(11))
        accepted = False
        failure = {
            "exception_type": "ForcedExtractionProbeFailure",
            "exception_message": (
                "controlled failure after all hooks registered"
            ),
            "layer_idx": 10,
            "occurred_after_registration": True,
            "forward_seconds": 0.5,
        }
    return {
        "name": name,
        "status": status,
        "hooks": {
            "before_counts": [0] * 20,
            "active_total": 20,
            "after_counts": [0] * 20,
            "callback_counts_by_layer": callbacks,
            "observed_capture_keys": captures,
            "manager_closed": True,
            "unresolved_handle_count": 0,
        },
        "candidates_accepted": accepted,
        "failure": failure,
        "forward_seconds": 0.5,
    }


def _valid_report(probe):
    records = []
    run_a = []
    run_b = []
    for frame_idx in range(8):
        for layer_idx in range(20):
            digest = hashlib.sha256(
                f"{frame_idx}:{layer_idx}".encode()
            ).hexdigest()
            key = {
                "trajectory_id": "layout_00_ep9410",
                "model_frame_idx": frame_idx,
                "layer_idx": layer_idx,
                "hook_site": probe.HOOK_SITE,
            }
            records.append(
                {
                    **key,
                    "a_sha256": digest,
                    "b_sha256": digest,
                    "shape": [2048],
                    "dtype": "torch.float32",
                    "device": "cpu",
                    "source_shape": [1, 2776, 2048],
                    "source_dtype": "torch.float16",
                    "source_device": "cuda:0",
                    "selected_visual_token_count": 336,
                    "a_detached": True,
                    "b_detached": True,
                    "a_contiguous": True,
                    "b_contiguous": True,
                    "allclose": True,
                    "maximum_absolute_difference": 0.0,
                    "maximum_tolerance_ratio": 0.0,
                }
            )
            side = {
                **key,
                "shape": [2048],
                "dtype": "torch.float32",
                "device": "cpu",
                "source_shape": [1, 2776, 2048],
                "source_dtype": "torch.float16",
                "source_device": "cuda:0",
                "selected_visual_token_count": 336,
                "detached": True,
                "contiguous": True,
                "sha256": digest,
            }
            run_a.append(copy.deepcopy(side))
            run_b.append(copy.deepcopy(side))
    baseline = 10_000_000
    after_a = 10_100_000
    after_failure = 10_200_000
    after_b = 10_150_000
    pilot_audit = [
        {
            "layer_idx": layer_idx,
            "candidate_sha256": records[layer_idx]["a_sha256"],
            "artifact_mean_sha256": records[layer_idx]["a_sha256"],
            "torch_equal": True,
            "maximum_absolute_difference": 0.0,
        }
        for layer_idx in range(20)
    ]
    return {
        "schema_version": "1.0",
        "probe_version": probe.PROBE_VERSION,
        "status": "PASS",
        "session_id": "controlled-session",
        "identities": {
            "mineocclude_revision": "1" * 40,
            "source_revision": "2" * 40,
            "asset_revision": "3" * 40,
            "environment_report_sha256": "4" * 64,
            "accepted_trajectory_package_sha256": "5" * 64,
            "input_mp4_sha256": "6" * 64,
            "runtime_id": "runtime",
            "frame_token_map_sha256": "7" * 64,
            "adapter_code_sha256": "8" * 64,
        },
        "counts": {
            "runtime_load_count": 1,
            "forward_attempt_count": 3,
            "successful_extraction_count": 2,
            "forced_failure_count": 1,
            "frame_count": 8,
            "layer_count": 20,
            "candidate_count_per_success": 160,
            "expected_candidate_count_per_success": 160,
        },
        "attempts": [
            _attempt("extraction_a", "PASS"),
            _attempt("forced_failure", "EXPECTED_FAILURE", forced=True),
            _attempt("extraction_b", "PASS"),
        ],
        "candidate_comparison": {
            "comparison": "torch.allclose",
            "rtol": 1e-3,
            "atol": 1e-3,
            "maximum_absolute_difference": 0.0,
            "unequal_candidate_count": 0,
            "records": records,
            "status": "PASS",
        },
        "candidate_run_a": run_a,
        "candidate_run_b": run_b,
        "memory": {
            "baseline_after_load_before_extraction_a": {
                "allocated_bytes": baseline,
                "reserved_bytes": 20_000_000,
            },
            "after_extraction_a_cleanup": {
                "allocated_bytes": after_a,
                "reserved_bytes": 20_000_000,
            },
            "after_forced_failure_cleanup": {
                "allocated_bytes": after_failure,
                "reserved_bytes": 20_100_000,
            },
            "after_extraction_b_cleanup": {
                "allocated_bytes": after_b,
                "reserved_bytes": 20_200_000,
            },
            "peak": {
                "allocated_bytes": 30_000_000,
                "reserved_bytes": 40_000_000,
            },
            "allocated_tolerance_bytes": 1_048_576,
            "post_cleanup_allocated_deltas_bytes": [
                after_a - baseline,
                after_failure - baseline,
                after_b - baseline,
            ],
            "b_minus_a_allocated_bytes": after_b - after_a,
            "status": "PASS",
        },
        "unpooled_pilot": {
            "classification": "limited_one_frame_unpooled_pilot",
            "manifest_path": "limited_unpooled_pilot.manifest.json",
            "manifest_size_bytes": 1,
            "manifest_sha256": "9" * 64,
            "artifact_path": "limited_unpooled_pilot.npz",
            "artifact_size_bytes": 1,
            "artifact_sha256": "a" * 64,
            "shape": [20, 336, 2048],
            "dtype": "float16",
            "layer_indices": list(range(20)),
            "visual_positions": list(range(336)),
            "action_positions_saved": False,
            "dataset_wide_unpooled_storage_enabled": False,
            "pooling_audit_status": "PASS",
            "pooling_audit": pilot_audit,
        },
        "files": {},
        "command": ["controlled"],
    }


class ExtractionProbePreflightTests(unittest.TestCase):
    def test_parser_exposes_exact_three_modes(self):
        probe = _load_probe()
        parser = probe.build_parser()
        action = next(
            item
            for item in parser._actions
            if isinstance(item, argparse._SubParsersAction)
        )
        self.assertEqual(
            set(action.choices),
            {"preflight", "run", "validate"},
        )

    def test_validate_cli_has_no_file_verification_bypass(self):
        probe = _load_probe()
        with mock.patch.object(probe, "validate") as validate:
            status = probe.main(
                ["validate", "--report", str(SCRIPT)]
            )
        self.assertEqual(status, 0)
        validate.assert_called_once_with(SCRIPT, verify_files=True)

    def test_preflight_has_no_torch_cuda_or_session_side_effects(self):
        self.assertNotIn("torch", sys.modules)
        probe = _load_probe()
        from mineocclude.models import phase3_certification

        session_root = ROOT / "never-created-wave3" / "session"
        prepared = {
            "status": "preflight_passed",
            "session_root": session_root,
            "mineocclude_revision": "1" * 40,
            "source_revision": "2" * 40,
            "asset_revision": "3" * 40,
            "context_pairs": 8,
            "position_budget": 3112,
            "package": {
                "trajectory_id": "layout_00_ep9410",
                "streams": {
                    "frame_map": [
                        {"model_frame_idx": index}
                        for index in range(8)
                    ]
                },
            },
            "package_path": SCRIPT,
            "accepted_manifest_sha256": "a" * 64,
            "input_mp4": SCRIPT,
            "input_mp4_size_bytes": SCRIPT.stat().st_size,
            "input_mp4_sha256": "b" * 64,
            "environment_report": SCRIPT,
            "environment_report_size_bytes": SCRIPT.stat().st_size,
            "environment_report_sha256": "c" * 64,
            "model_config": SCRIPT,
            "main_checkpoint": SCRIPT,
            "vae_config": SCRIPT,
            "vae_checkpoint": SCRIPT,
        }
        args = argparse.Namespace(
            mineworld_source_root=ROOT,
            asset_root=ROOT,
            evidence_root=ROOT / "never-created-wave3",
            accepted_trajectory_package=SCRIPT,
            accepted_trajectory_package_sha256="a" * 64,
            input_mp4=SCRIPT,
            input_mp4_sha256="b" * 64,
            environment_report=SCRIPT,
            environment_report_sha256="c" * 64,
            session_id="new-session",
            seed=7,
            precision="float16",
            device="cuda:0",
            mineocclude_revision="1" * 40,
            ffprobe="ffprobe",
            expected_layer_count=20,
            expected_hidden_size=2048,
            expected_visual_token_count=336,
            expected_action_token_count=11,
            runtime_load_count=1,
            forward_attempt_count=3,
            successful_extraction_count=2,
            forced_failure_count=1,
            unpooled_pilot_frame_count=1,
        )
        with mock.patch.object(
            phase3_certification,
            "preflight_certification_inputs",
            return_value=prepared,
        ):
            report = probe.preflight(args)
        self.assertEqual(report["status"], "preflight_passed")
        for field in (
            "torch_imported",
            "cuda_queried",
            "runtime_loaded",
            "session_directory_created",
            "overwrite_allowed",
        ):
            self.assertFalse(report[field])
        self.assertFalse(session_root.exists())
        self.assertNotIn("torch", sys.modules)

    def test_invalid_requested_count_fails_before_shared_preflight(self):
        probe = _load_probe()
        from mineocclude.models import phase3_certification

        args = argparse.Namespace(
            expected_layer_count=20,
            expected_hidden_size=2048,
            expected_visual_token_count=336,
            expected_action_token_count=11,
            runtime_load_count=1,
            forward_attempt_count=2,
            successful_extraction_count=2,
            forced_failure_count=1,
            unpooled_pilot_frame_count=1,
        )
        with mock.patch.object(
            phase3_certification,
            "preflight_certification_inputs",
        ) as shared, self.assertRaises(ValueError):
            probe.preflight(args)
        shared.assert_not_called()


class ExtractionProbeSemanticValidatorTests(unittest.TestCase):
    def setUp(self):
        self.probe = _load_probe()
        self.report = _valid_report(self.probe)

    def _validate(self, report):
        with mock.patch.object(
            self.probe,
            "_strict_json",
            return_value=report,
        ):
            self.probe.validate(SCRIPT, verify_files=False)

    def _reject(self, report):
        with self.assertRaises(ValueError):
            self._validate(report)

    def test_valid_complete_synthetic_report_passes(self):
        self._validate(self.report)

    def test_missing_report_fails(self):
        missing = ROOT / "missing-wave3-report.json"
        self.assertFalse(missing.exists())
        with self.assertRaises(ValueError):
            self.probe.validate(missing)

    def test_wrong_execution_counts_fail(self):
        for field, value in (
            ("runtime_load_count", 2),
            ("forward_attempt_count", 2),
            ("successful_extraction_count", 1),
            ("forced_failure_count", 0),
        ):
            with self.subTest(field=field):
                report = copy.deepcopy(self.report)
                report["counts"][field] = value
                self._reject(report)

    def test_candidate_coverage_stale_and_duplicate_identity_fail(self):
        missing = copy.deepcopy(self.report)
        missing["candidate_comparison"]["records"].pop()
        self._reject(missing)

        duplicate = copy.deepcopy(self.report)
        for section in (
            duplicate["candidate_comparison"]["records"],
            duplicate["candidate_run_a"],
            duplicate["candidate_run_b"],
        ):
            section[1].update(
                {
                    "trajectory_id": section[0]["trajectory_id"],
                    "model_frame_idx": section[0]["model_frame_idx"],
                    "layer_idx": section[0]["layer_idx"],
                    "hook_site": section[0]["hook_site"],
                }
            )
        self._reject(duplicate)

    def test_hook_cleanup_failure_timing_and_remaining_handles_fail(self):
        cases = []
        cleanup = copy.deepcopy(self.report)
        cleanup["attempts"][0]["hooks"]["after_counts"][3] = 1
        cases.append(cleanup)

        early = copy.deepcopy(self.report)
        early["attempts"][1]["failure"]["occurred_after_registration"] = False
        cases.append(early)

        remaining = copy.deepcopy(self.report)
        remaining["attempts"][1]["hooks"]["unresolved_handle_count"] = 1
        cases.append(remaining)
        for report in cases:
            self._reject(report)

    def test_intermediate_and_second_run_memory_growth_fail(self):
        intermediate = copy.deepcopy(self.report)
        baseline = intermediate["memory"][
            "baseline_after_load_before_extraction_a"
        ]["allocated_bytes"]
        intermediate["memory"]["after_forced_failure_cleanup"][
            "allocated_bytes"
        ] = baseline + self.probe.MEMORY_TOLERANCE_BYTES + 1
        intermediate["memory"]["post_cleanup_allocated_deltas_bytes"][1] = (
            self.probe.MEMORY_TOLERANCE_BYTES + 1
        )
        self._reject(intermediate)

        second = copy.deepcopy(self.report)
        first = second["memory"]["after_extraction_a_cleanup"][
            "allocated_bytes"
        ]
        second["memory"]["after_extraction_b_cleanup"][
            "allocated_bytes"
        ] = first + self.probe.MEMORY_TOLERANCE_BYTES + 1
        self._reject(second)

    def test_unpooled_header_shape_dtype_positions_and_action_reject(self):
        cases = []
        missing = copy.deepcopy(self.report)
        missing.pop("unpooled_pilot")
        cases.append(missing)
        shape = copy.deepcopy(self.report)
        shape["unpooled_pilot"]["shape"] = [20, 335, 2048]
        cases.append(shape)
        dtype = copy.deepcopy(self.report)
        dtype["unpooled_pilot"]["dtype"] = "float32"
        cases.append(dtype)
        layers = copy.deepcopy(self.report)
        layers["unpooled_pilot"]["layer_indices"][0] = 1
        cases.append(layers)
        positions = copy.deepcopy(self.report)
        positions["unpooled_pilot"]["visual_positions"][0] = 336
        cases.append(positions)
        for report in cases:
            self._reject(report)


class ExtractionProbeArtifactValidatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.probe = _load_probe()
        cls.temp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temp.name)
        cls.report_path = cls.directory / cls.probe.REPORT_FILENAME
        cls.raw_path = cls.directory / cls.probe.RAW_LOG_FILENAME
        cls.raw_path.write_text("controlled\n", encoding="utf-8")
        token_values = numpy.zeros((20, 336, 2048), dtype=numpy.float16)
        layers = numpy.arange(20, dtype=numpy.int64)
        positions = numpy.arange(336, dtype=numpy.int64)
        from mineocclude.activations.store import _deterministic_npz

        payload = _deterministic_npz(
            {
                "token_values": token_values,
                "layer_indices": layers,
                "visual_positions": positions,
            }
        )
        cls.artifact_path = cls.directory / "limited_unpooled_pilot.npz"
        cls.artifact_path.write_bytes(payload)
        import torch

        mean = torch.zeros(2048, dtype=torch.float32)
        mean_sha = hashlib.sha256(
            mean.numpy().tobytes(order="C")
        ).hexdigest()
        position_hash = hashlib.sha256(
            json.dumps(
                list(range(336)),
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        cls.manifest_path = (
            cls.directory / "limited_unpooled_pilot.manifest.json"
        )
        manifest = {
            "schema_version": "1.0",
            "artifact_version": (
                "person-a-limited-unpooled-pilot-v1.0"
            ),
            "classification": "limited_one_frame_unpooled_pilot",
            "status": "PASS",
            "session_id": "controlled-session",
            "scientific_identity": {
                "trajectory_id": "layout_00_ep9410",
                "model_frame_idx": 0,
                "hook_site": cls.probe.HOOK_SITE,
            },
            "capture": {
                "layer_indices": list(range(20)),
                "source_sequence_length": 2776,
                "source_hidden_size": 2048,
                "source_dtype": "torch.float16",
                "source_device": "cuda:0",
                "normalization_identity": [
                    "direct_tensor",
                    None,
                    None,
                ],
                "visual_token_count": 336,
                "visual_positions": list(range(336)),
                "visual_positions_sha256": position_hash,
                "token_payload_shape": [20, 336, 2048],
                "token_payload_dtype": "float16",
                "serialized_device": "cpu",
            },
            "provenance": {
                "frame_token_map_sha256": "1" * 64,
                "mineocclude_revision": "2" * 40,
                "mineworld_revision": "3" * 40,
                "asset_revision": "4" * 40,
                "model_config_sha256": "5" * 64,
                "main_checkpoint_sha256": "6" * 64,
                "vae_config_sha256": "7" * 64,
                "vae_checkpoint_sha256": "8" * 64,
                "environment_report_sha256": "9" * 64,
                "preprocessing_profile": "preprocess-v1",
                "action_conversion_profile": "actions-v1",
                "tokenization_profile": "tokens-v1",
                "accepted_trajectory_package_sha256": "a" * 64,
                "input_mp4_sha256": "b" * 64,
            },
            "artifact": {
                "path": cls.artifact_path.name,
                "size_bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "array_names": [
                    "token_values",
                    "layer_indices",
                    "visual_positions",
                ],
                "allow_pickle": False,
                "maximum_size_bytes": 32 * 1024 * 1024,
            },
            "pooling_audit": {
                "comparison": "torch.equal",
                "rtol": None,
                "atol": None,
                "maximum_absolute_difference": 0.0,
                "layer_records": [
                    {
                        "layer_idx": layer_idx,
                        "candidate_sha256": mean_sha,
                        "artifact_mean_sha256": mean_sha,
                        "torch_equal": True,
                        "maximum_absolute_difference": 0.0,
                    }
                    for layer_idx in range(20)
                ],
                "status": "PASS",
            },
            "scope": {
                "one_frame_only": True,
                "all_twenty_layers": True,
                "visual_rows_only": True,
                "action_rows_saved": False,
                "neighbor_rows_saved": False,
                "whole_sequence_saved": False,
                "dataset_wide_unpooled_storage_enabled": False,
            },
        }
        cls.manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        cls.report = _valid_report(cls.probe)
        for layer_idx in range(20):
            index = layer_idx
            cls.report["candidate_comparison"]["records"][index][
                "a_sha256"
            ] = mean_sha
            cls.report["candidate_comparison"]["records"][index][
                "b_sha256"
            ] = mean_sha
            cls.report["candidate_run_a"][index]["sha256"] = mean_sha
            cls.report["candidate_run_b"][index]["sha256"] = mean_sha
            cls.report["unpooled_pilot"]["pooling_audit"][layer_idx][
                "candidate_sha256"
            ] = mean_sha
            cls.report["unpooled_pilot"]["pooling_audit"][layer_idx][
                "artifact_mean_sha256"
            ] = mean_sha
        cls.report["unpooled_pilot"].update(
            {
                "manifest_size_bytes": cls.manifest_path.stat().st_size,
                "manifest_sha256": hashlib.sha256(
                    cls.manifest_path.read_bytes()
                ).hexdigest(),
                "artifact_size_bytes": len(payload),
                "artifact_sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
        cls.report["files"] = {
            cls.probe.RAW_LOG_FILENAME: {
                "size_bytes": cls.raw_path.stat().st_size,
                "sha256": hashlib.sha256(
                    cls.raw_path.read_bytes()
                ).hexdigest(),
            }
        }
        cls.report_path.write_text(
            json.dumps(cls.report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def _write_report(self, report):
        self.report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def test_complete_files_and_artifact_pass(self):
        self._write_report(self.report)
        self.probe.validate(self.report_path, verify_files=True)

    def test_second_tensor_artifact_rejects(self):
        second = self.directory / "unexpected.npy"
        second.write_bytes(b"unexpected")
        try:
            self._write_report(self.report)
            with self.assertRaises(ValueError):
                self.probe.validate(self.report_path, verify_files=True)
        finally:
            second.unlink()

    def test_manifest_or_payload_hash_mismatch_rejects(self):
        report = copy.deepcopy(self.report)
        report["unpooled_pilot"]["manifest_sha256"] = "0" * 64
        self._write_report(report)
        with self.assertRaises(ValueError):
            self.probe.validate(self.report_path, verify_files=True)

    def test_artifact_derived_mean_mismatch_rejects(self):
        report = copy.deepcopy(self.report)
        wrong = "f" * 64
        for section in (
            report["candidate_comparison"]["records"],
            report["candidate_run_a"],
            report["candidate_run_b"],
        ):
            if "a_sha256" in section[0]:
                section[0]["a_sha256"] = wrong
                section[0]["b_sha256"] = wrong
            else:
                section[0]["sha256"] = wrong
        self._write_report(report)
        with self.assertRaises(ValueError):
            self.probe.validate(self.report_path, verify_files=True)

    def test_pickle_object_array_rejects(self):
        original = self.artifact_path.read_bytes()
        original_manifest = self.manifest_path.read_bytes()
        original_report = copy.deepcopy(self.report)
        try:
            numpy.savez(
                self.artifact_path,
                token_values=numpy.array([object()], dtype=object),
                layer_indices=numpy.arange(20, dtype=numpy.int64),
                visual_positions=numpy.arange(336, dtype=numpy.int64),
            )
            payload = self.artifact_path.read_bytes()
            manifest = json.loads(original_manifest)
            manifest["artifact"]["size_bytes"] = len(payload)
            manifest["artifact"]["sha256"] = hashlib.sha256(
                payload
            ).hexdigest()
            self.manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            report = copy.deepcopy(original_report)
            report["unpooled_pilot"]["artifact_size_bytes"] = len(payload)
            report["unpooled_pilot"]["artifact_sha256"] = hashlib.sha256(
                payload
            ).hexdigest()
            report["unpooled_pilot"][
                "manifest_size_bytes"
            ] = self.manifest_path.stat().st_size
            report["unpooled_pilot"]["manifest_sha256"] = hashlib.sha256(
                self.manifest_path.read_bytes()
            ).hexdigest()
            self._write_report(report)
            with self.assertRaises(ValueError):
                self.probe.validate(self.report_path, verify_files=True)
        finally:
            self.artifact_path.write_bytes(original)
            self.manifest_path.write_bytes(original_manifest)


if __name__ == "__main__":
    unittest.main()
