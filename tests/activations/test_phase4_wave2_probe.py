"""CPU-only boundary tests for the prepared Wave 2 runtime probe."""

from __future__ import annotations

import argparse
import contextlib
import copy
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run_phase4_wave2_pooling_probe.py"


def _torch_modules() -> set[str]:
    """Return the torch modules currently imported into this process."""

    return {
        name
        for name in sys.modules
        if name == "torch" or name.startswith("torch.")
    }


@contextlib.contextmanager
def _fresh_runtime_process():
    """Recreate the probe's documented precondition: torch not yet imported.

    The probe is a standalone command that runs in a fresh process and refuses
    to start once torch is loaded. A pytest session may already have imported
    torch through a sibling module, so the imported torch modules are removed
    for the duration of the call and restored exactly afterwards. Nothing is
    re-imported in between, because the property under test is that preflight
    imports no runtime of its own.
    """

    saved = {name: sys.modules[name] for name in _torch_modules()}
    for name in saved:
        del sys.modules[name]
    try:
        yield
    finally:
        sys.modules.update(saved)


def _assert_no_new_torch_import(test, before: set[str]) -> None:
    """Assert the guarded code path imported no torch module of its own."""

    test.assertEqual(_torch_modules() - before, set())

def _load_probe():
    spec = importlib.util.spec_from_file_location("phase4_wave2_probe", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load Wave 2 probe")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _valid_runtime_report(probe):
    frame_count = 2
    trajectory_id = "trajectory"
    candidates = []
    for model_frame_idx in (40, 41):
        for layer_idx in range(probe.EXPECTED_LAYER_COUNT):
            candidates.append(
                {
                    "trajectory_id": trajectory_id,
                    "model_frame_idx": model_frame_idx,
                    "layer_idx": layer_idx,
                    "hook_site": probe.HOOK_SITE,
                    "source_shape": [1, 694, probe.EXPECTED_HIDDEN_SIZE],
                    "returned_shape": [probe.EXPECTED_HIDDEN_SIZE],
                    "source_dtype": "torch.float16",
                    "source_device": "cuda:0",
                    "returned_dtype": "torch.float32",
                    "returned_device": "cpu",
                    "visual_token_count": probe.EXPECTED_VISUAL_TOKENS,
                    "direct_mean_equal": True,
                    "max_abs_difference": 0.0,
                    "candidate_sha256": "d" * 64,
                    "detached": True,
                    "contiguous": True,
                }
            )
    action_positions = list(range(336, 347))
    visual_hash = "e" * 64
    action_records = [
        {
            "layer_idx": layer_idx,
            "hook_site": probe.HOOK_SITE,
            "expected_action_positions": action_positions,
            "finite_actual_modified_positions": action_positions,
            "nonfinite_actual_modified_positions": action_positions,
            "visual_positions_before_sha256": visual_hash,
            "visual_positions_after_finite_sha256": visual_hash,
            "visual_positions_after_nonfinite_sha256": visual_hash,
            "finite_visual_positions_unchanged": True,
            "nonfinite_visual_positions_unchanged": True,
            "finite_action_equal": True,
            "nonfinite_action_equal": True,
        }
        for layer_idx in range(probe.EXPECTED_LAYER_COUNT)
    ]
    baseline_allocated = 10_000_000
    allocations = [10_100_000, 10_200_000]
    per_frame = [
        {
            "trajectory_id": trajectory_id,
            "model_frame_idx": model_frame_idx,
            "allocated_bytes": allocation,
            "reserved_bytes": 20_000_000,
            "allocated_delta_from_baseline_bytes": (
                allocation - baseline_allocated
            ),
        }
        for model_frame_idx, allocation in zip(
            (40, 41),
            allocations,
            strict=True,
        )
    ]
    source_revision = "2" * 40
    asset_revision = "3" * 40
    mineocclude_revision = "1" * 40
    environment_sha256 = "a" * 64
    adapter_sha256 = "b" * 64
    return {
        "schema_version": "1.0",
        "probe_version": probe.PROBE_VERSION,
        "status": "PASS",
        "session_id": "controlled-session",
        "identities": {
            "mineocclude_revision": mineocclude_revision,
            "source_revision": source_revision,
            "asset_revision": asset_revision,
            "environment_report_sha256": environment_sha256,
            "accepted_trajectory_package_sha256": "c" * 64,
            "input_mp4_sha256": "d" * 64,
            "runtime_id": "runtime",
            "runtime_identity": {
                "mineworld_source_revision": source_revision,
                "modelscope_asset_revision": asset_revision,
                "mineocclude_revision": mineocclude_revision,
                "environment_report_sha256": environment_sha256,
                "layer_count": probe.EXPECTED_LAYER_COUNT,
                "hidden_size": probe.EXPECTED_HIDDEN_SIZE,
                "precision": "float16",
                "device": "cuda:0",
                "adapter_code_sha256": adapter_sha256,
            },
            "frame_token_map_sha256": "5" * 64,
            "adapter_code_sha256": adapter_sha256,
            "tokenization_profile": "tokenization-v1",
            "preprocessing_profile": "preprocessing-v1",
            "action_conversion_profile": "actions-v1",
        },
        "layer_count": probe.EXPECTED_LAYER_COUNT,
        "hidden_size": probe.EXPECTED_HIDDEN_SIZE,
        "frame_count": frame_count,
        "candidate_count": frame_count * probe.EXPECTED_LAYER_COUNT,
        "expected_candidate_count": frame_count * probe.EXPECTED_LAYER_COUNT,
        "forward_count": 1,
        "teacher_output_sha256": "f" * 64,
        "forward_seconds": 1.0,
        "candidates": candidates,
        "action_exclusion": {
            "representative_identity": {
                "trajectory_id": trajectory_id,
                "model_frame_idx": 40,
            },
            "layer_records": action_records,
            "status": "PASS",
        },
        "memory": {
            "post_forward_baseline": {
                "allocated_bytes": baseline_allocated,
                "reserved_bytes": 20_000_000,
            },
            "after_each_frame": per_frame,
            "final": {
                "allocated_bytes": 10_050_000,
                "reserved_bytes": 20_000_000,
            },
            "peak_allocated_bytes": 10_500_000,
            "peak_reserved_bytes": 20_000_000,
            "allocated_tolerance_bytes": probe.MEMORY_TOLERANCE_BYTES,
            "maximum_after_frame_allocated_bytes": max(allocations),
            "maximum_after_frame_allocated_delta_bytes": max(
                allocation - baseline_allocated
                for allocation in allocations
            ),
            "all_after_frame_allocations_within_tolerance": True,
            "final_allocation_delta_bytes": 50_000,
            "final_allocation_within_tolerance": True,
            "monotonic_accumulation_detected": True,
            "status": "PASS",
        },
        "hooks": {
            "before_counts": [0] * probe.EXPECTED_LAYER_COUNT,
            "during_total": probe.EXPECTED_LAYER_COUNT,
            "after_counts": [0] * probe.EXPECTED_LAYER_COUNT,
            "capture_count": probe.EXPECTED_LAYER_COUNT,
            "cleanup_passed": True,
        },
        "files": {},
        "unpooled_activation_artifacts_saved": False,
        "command": ["controlled"],
    }


class PoolingProbePreflightTests(unittest.TestCase):
    def test_parser_exposes_exact_three_modes(self):
        probe = _load_probe()
        parser = probe.build_parser()
        subparser_action = next(
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        self.assertEqual(
            set(subparser_action.choices),
            {"preflight", "run", "validate"},
        )

    def test_preflight_records_no_runtime_or_session_side_effects(self):
        torch_before = _torch_modules()
        probe = _load_probe()
        from mineocclude.models import phase3_certification

        digest_a = "a" * 64
        digest_b = "b" * 64
        digest_c = "c" * 64
        session_root = ROOT / "never-created-evidence" / "session-new"
        prepared = {
            "status": "preflight_passed",
            "session_root": session_root,
            "mineocclude_revision": "1" * 40,
            "source_revision": "2" * 40,
            "asset_revision": "3" * 40,
            "context_pairs": 2,
            "position_budget": 1030,
            "package": {
                "trajectory_id": "trajectory",
                "streams": {
                    "frame_map": [
                        {"model_frame_idx": 40},
                        {"model_frame_idx": 41},
                    ]
                },
            },
            "package_path": SCRIPT,
            "accepted_manifest_sha256": digest_a,
            "input_mp4": SCRIPT,
            "input_mp4_size_bytes": SCRIPT.stat().st_size,
            "input_mp4_sha256": digest_b,
            "environment_report": SCRIPT,
            "environment_report_size_bytes": SCRIPT.stat().st_size,
            "environment_report_sha256": digest_c,
            "model_config": SCRIPT,
            "main_checkpoint": SCRIPT,
            "vae_config": SCRIPT,
            "vae_checkpoint": SCRIPT,
        }
        args = argparse.Namespace(
            mineworld_source_root=ROOT,
            asset_root=ROOT,
            evidence_root=ROOT / "never-created-evidence",
            accepted_trajectory_package=SCRIPT,
            accepted_trajectory_package_sha256=digest_a,
            input_mp4=SCRIPT,
            input_mp4_sha256=digest_b,
            environment_report=SCRIPT,
            environment_report_sha256=digest_c,
            session_id="session-new",
            seed=7,
            precision="float16",
            device="cuda:0",
            mineocclude_revision="1" * 40,
            ffprobe="ffprobe",
            expected_layer_count=20,
            expected_hidden_size=2048,
            forward_count=1,
        )
        with mock.patch.object(
            phase3_certification,
            "preflight_certification_inputs",
            return_value=prepared,
        ) as shared, _fresh_runtime_process():
            report = probe.preflight(args)

        shared.assert_called_once()
        self.assertEqual(report["status"], "preflight_passed")
        self.assertFalse(report["torch_imported"])
        self.assertFalse(report["cuda_queried"])
        self.assertFalse(report["runtime_loaded"])
        self.assertFalse(report["session_directory_created"])
        self.assertFalse(report["overwrite_allowed"])
        self.assertEqual(report["forward_count_requested"], 1)
        self.assertEqual(report["expected_layer_count"], 20)
        self.assertEqual(report["expected_hidden_size"], 2048)
        self.assertFalse(session_root.exists())
        _assert_no_new_torch_import(self, torch_before)

    def test_preflight_rejects_noncanonical_probe_shape(self):
        torch_before = _torch_modules()
        probe = _load_probe()
        from mineocclude.models import phase3_certification

        prepared = {
            "context_pairs": 1,
            "package": {
                "trajectory_id": "trajectory",
                "streams": {"frame_map": [{"model_frame_idx": 0}]},
            },
            "accepted_manifest_sha256": "a" * 64,
            "input_mp4_sha256": "b" * 64,
            "environment_report_sha256": "c" * 64,
        }
        args = argparse.Namespace(
            mineworld_source_root=Path("source"),
            asset_root=Path("assets"),
            evidence_root=Path("evidence"),
            accepted_trajectory_package=Path("accepted.json"),
            accepted_trajectory_package_sha256="a" * 64,
            input_mp4=Path("accepted.mp4"),
            input_mp4_sha256="b" * 64,
            environment_report=Path("environment.txt"),
            environment_report_sha256="c" * 64,
            session_id="session",
            seed=1,
            precision="float16",
            device="cuda:0",
            mineocclude_revision="1" * 40,
            ffprobe="ffprobe",
            expected_layer_count=19,
            expected_hidden_size=2048,
            forward_count=1,
        )
        with mock.patch.object(
            phase3_certification,
            "preflight_certification_inputs",
            return_value=prepared,
        ), _fresh_runtime_process(), self.assertRaises(Exception) as caught:
            probe.preflight(args)
        self.assertIn("probe_shape_mismatch", str(caught.exception))
        _assert_no_new_torch_import(self, torch_before)

    def test_validate_fails_closed_for_missing_report(self):
        probe = _load_probe()
        missing = ROOT / "missing-phase4-wave2-probe-report.json"
        self.assertFalse(missing.exists())
        with self.assertRaises(Exception) as caught:
            probe.validate(missing, verify_files=False)
        self.assertIn("missing_report", str(caught.exception))


class PoolingProbeValidatorCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.probe = _load_probe()
        self.report = _valid_runtime_report(self.probe)

    def _validate(self, report):
        with mock.patch.object(
            self.probe,
            "_strict_json",
            return_value=report,
        ):
            self.probe.validate(SCRIPT, verify_files=False)

    def _assert_rejected(self, report):
        with self.assertRaises(Exception) as caught:
            self._validate(report)
        self.assertNotEqual(str(caught.exception), "")

    def test_controlled_complete_report_passes_semantic_validation(self):
        self._validate(self.report)

    def test_action_modified_position_evidence_fails_closed(self):
        cases = []
        missing_finite = copy.deepcopy(self.report)
        missing_finite["action_exclusion"]["layer_records"][0][
            "finite_actual_modified_positions"
        ] = list(range(336, 346))
        cases.append(missing_finite)

        extra_nonfinite = copy.deepcopy(self.report)
        extra_nonfinite["action_exclusion"]["layer_records"][0][
            "nonfinite_actual_modified_positions"
        ] = list(range(335, 347))
        cases.append(extra_nonfinite)

        duplicated = copy.deepcopy(self.report)
        duplicated["action_exclusion"]["layer_records"][0][
            "expected_action_positions"
        ][-1] = 345
        cases.append(duplicated)

        for report in cases:
            with self.subTest():
                self._assert_rejected(report)

    def test_visual_hash_and_hardcoded_equality_disagreement_reject(self):
        cases = []
        changed_hash = copy.deepcopy(self.report)
        changed_hash["action_exclusion"]["layer_records"][0][
            "visual_positions_after_finite_sha256"
        ] = "9" * 64
        cases.append(changed_hash)

        forged_flags = copy.deepcopy(self.report)
        forged_flags["action_exclusion"]["layer_records"][0][
            "finite_visual_positions_unchanged"
        ] = True
        forged_flags["action_exclusion"]["layer_records"][0][
            "finite_actual_modified_positions"
        ] = list(range(336, 346))
        cases.append(forged_flags)

        malformed_hash = copy.deepcopy(self.report)
        malformed_hash["action_exclusion"]["layer_records"][0][
            "visual_positions_after_nonfinite_sha256"
        ] = "not-a-digest"
        cases.append(malformed_hash)

        for report in cases:
            with self.subTest():
                self._assert_rejected(report)

    def test_intermediate_memory_growth_rejects_even_if_final_recovers(self):
        report = copy.deepcopy(self.report)
        baseline = report["memory"]["post_forward_baseline"]["allocated_bytes"]
        excessive = baseline + self.probe.MEMORY_TOLERANCE_BYTES + 1
        report["memory"]["after_each_frame"][0]["allocated_bytes"] = excessive
        report["memory"]["after_each_frame"][0][
            "allocated_delta_from_baseline_bytes"
        ] = excessive - baseline
        report["memory"]["maximum_after_frame_allocated_bytes"] = excessive
        report["memory"]["maximum_after_frame_allocated_delta_bytes"] = (
            excessive - baseline
        )
        report["memory"]["all_after_frame_allocations_within_tolerance"] = True
        report["memory"]["final"]["allocated_bytes"] = baseline
        report["memory"]["final_allocation_delta_bytes"] = 0
        report["memory"]["final_allocation_within_tolerance"] = True
        report["memory"]["status"] = "PASS"
        self._assert_rejected(report)

    def test_reported_memory_maximum_and_delta_are_recomputed(self):
        for field in (
            "maximum_after_frame_allocated_bytes",
            "maximum_after_frame_allocated_delta_bytes",
        ):
            with self.subTest(field=field):
                report = copy.deepcopy(self.report)
                report["memory"][field] += 1
                self._assert_rejected(report)

    def test_negative_and_malformed_memory_values_reject(self):
        cases = []
        negative = copy.deepcopy(self.report)
        negative["memory"]["after_each_frame"][0]["reserved_bytes"] = -1
        cases.append(negative)

        malformed = copy.deepcopy(self.report)
        malformed["memory"]["post_forward_baseline"][
            "allocated_bytes"
        ] = "10000000"
        cases.append(malformed)

        for report in cases:
            with self.subTest():
                self._assert_rejected(report)

    def test_wrong_before_or_after_hook_counts_reject(self):
        for field, value in (
            ("before_counts", [1] + [0] * 19),
            ("after_counts", [0] * 19),
        ):
            with self.subTest(field=field):
                report = copy.deepcopy(self.report)
                report["hooks"][field] = value
                self._assert_rejected(report)


if __name__ == "__main__":
    unittest.main()
