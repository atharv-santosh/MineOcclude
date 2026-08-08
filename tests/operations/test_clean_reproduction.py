"""Step 7.1 contract tests: the reproduction workflow must fail closed."""

from __future__ import annotations

import copy
import unittest
from pathlib import Path

from mineocclude.operations.clean_reproduction import (
    CLEAN_REPRODUCTION_PLAN_SCHEMA_VERSION,
    DEFAULT_COMPONENT_PATHS,
    REPRODUCTION_STAGES,
    CleanReproductionError,
    build_clean_reproduction_receipt,
    compare_outputs,
    component_hashes,
    environment_lock,
    is_private_path_token,
    private_path_tokens,
    repository_relative,
    run_stage,
    validate_clean_reproduction_plan,
    validate_clean_reproduction_receipt,
    verify_component_hashes,
    verify_input_hashes,
)

ROOT = Path(__file__).resolve().parents[2]


def minimal_plan() -> dict:
    return {
        "clean_reproduction_plan_schema_version": (
            CLEAN_REPRODUCTION_PLAN_SCHEMA_VERSION
        ),
        "code_commit": "0" * 40,
        "component_hashes": {"src/mineocclude/vision/ssim.py": "a" * 64},
        "environment_lock": {"python_version": "3.10.20"},
        "evidence_class": "synthetic_fixture",
        "inputs": [
            {
                "input_id": "fixture_registry",
                "owner": "person_e",
                "repository_path": "tests/fixtures/person_e/immutable_registry_v1.json",
                "sha256": "b" * 64,
            }
        ],
        "stages": [
            {
                "stage": stage,
                "command": ["scripts/measure_u4.py", "--help"],
                "expected_outputs": [],
            }
            for stage in REPRODUCTION_STAGES
        ],
    }


class TestPlanValidation(unittest.TestCase):
    def test_minimal_plan_validates(self) -> None:
        self.assertEqual(
            validate_clean_reproduction_plan(minimal_plan())["evidence_class"],
            "synthetic_fixture",
        )

    def test_unknown_schema_version_rejects(self) -> None:
        plan = minimal_plan()
        plan["clean_reproduction_plan_schema_version"] = "person-e-something-else"
        with self.assertRaises(CleanReproductionError):
            validate_clean_reproduction_plan(plan)

    def test_unknown_evidence_class_rejects(self) -> None:
        plan = minimal_plan()
        plan["evidence_class"] = "probably_real"
        with self.assertRaises(CleanReproductionError):
            validate_clean_reproduction_plan(plan)

    def test_out_of_order_stages_reject(self) -> None:
        plan = minimal_plan()
        plan["stages"] = list(reversed(plan["stages"]))
        with self.assertRaises(CleanReproductionError):
            validate_clean_reproduction_plan(plan)

    def test_missing_stage_rejects(self) -> None:
        plan = minimal_plan()
        plan["stages"] = plan["stages"][:-1]
        with self.assertRaises(CleanReproductionError):
            validate_clean_reproduction_plan(plan)

    def test_duplicate_input_identity_rejects(self) -> None:
        plan = minimal_plan()
        plan["inputs"] = [plan["inputs"][0], dict(plan["inputs"][0])]
        with self.assertRaises(CleanReproductionError):
            validate_clean_reproduction_plan(plan)

    def test_non_digest_input_hash_rejects(self) -> None:
        plan = minimal_plan()
        plan["inputs"][0]["sha256"] = "not-a-digest"
        with self.assertRaises(CleanReproductionError):
            validate_clean_reproduction_plan(plan)

    def test_private_path_in_command_rejects(self) -> None:
        plan = minimal_plan()
        plan["stages"][0]["command"] = [
            "C:/Users/someone/secret/measure_u4.py",
        ]
        with self.assertRaises(CleanReproductionError):
            validate_clean_reproduction_plan(plan)

    def test_private_path_in_input_rejects(self) -> None:
        plan = minimal_plan()
        plan["inputs"][0]["repository_path"] = "/home/sagemaker-user/registry.json"
        with self.assertRaises(CleanReproductionError):
            validate_clean_reproduction_plan(plan)


class TestPrivatePathDetection(unittest.TestCase):
    def test_known_private_prefixes_detected(self) -> None:
        for token in (
            "C:/Users/lollo/x.json",
            "C:\\Users\\lollo\\x.json",
            "\\\\share\\x.json",
            "/home/sagemaker-user/x.json",
            "/Users/someone/x.json",
            "/mnt/data/x.json",
            "~/x.json",
        ):
            self.assertTrue(is_private_path_token(token), token)

    def test_repository_relative_tokens_allowed(self) -> None:
        for token in ("scripts/measure_u4.py", "--config", "docs/status/a.json"):
            self.assertFalse(is_private_path_token(token), token)

    def test_private_path_tokens_reports_every_offender(self) -> None:
        self.assertEqual(
            private_path_tokens(["scripts/x.py", "/home/a", "~/b"]),
            ["/home/a", "~/b"],
        )


class TestComponentAndInputVerification(unittest.TestCase):
    def test_every_default_component_exists_and_hashes(self) -> None:
        digests = component_hashes(ROOT)
        self.assertEqual(set(digests), set(DEFAULT_COMPONENT_PATHS))
        self.assertTrue(all(len(value) == 64 for value in digests.values()))

    def test_missing_component_rejects(self) -> None:
        with self.assertRaises(CleanReproductionError):
            component_hashes(ROOT, ("src/mineocclude/vision/not_a_file.py",))

    def test_component_mismatch_is_reported_not_raised(self) -> None:
        plan = minimal_plan()
        result = verify_component_hashes(plan, ROOT)
        self.assertFalse(result["verified"])
        self.assertEqual(
            result["mismatched_components"], ["src/mineocclude/vision/ssim.py"]
        )

    def test_matching_component_verifies(self) -> None:
        plan = minimal_plan()
        plan["component_hashes"] = component_hashes(
            ROOT, ("src/mineocclude/vision/ssim.py",)
        )
        self.assertTrue(verify_component_hashes(plan, ROOT)["verified"])

    def test_missing_input_file_is_reported(self) -> None:
        plan = minimal_plan()
        plan["inputs"][0]["repository_path"] = "tests/fixtures/person_e/absent.json"
        result = verify_input_hashes(plan, ROOT)
        self.assertEqual(result["missing_inputs"], ["fixture_registry"])
        self.assertFalse(result["verified"])

    def test_input_hash_mismatch_is_reported(self) -> None:
        result = verify_input_hashes(minimal_plan(), ROOT)
        self.assertEqual(result["mismatched_inputs"], ["fixture_registry"])
        self.assertFalse(result["verified"])


class TestStageExecution(unittest.TestCase):
    def test_stage_runs_and_captures_exit_code_and_runtime(self) -> None:
        result = run_stage(
            {"stage": "registry", "command": ["-c", "print('ok')"]},
            ROOT,
        )
        self.assertEqual(result["outcome"], "passed")
        self.assertEqual(result["exit_code"], 0)
        self.assertIn("ok", result["stdout_tail"])
        self.assertGreaterEqual(result["runtime_seconds"], 0.0)

    def test_failing_stage_captures_stderr_without_raising(self) -> None:
        result = run_stage(
            {"stage": "detector", "command": ["-c", "raise SystemExit(3)"]},
            ROOT,
        )
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["exit_code"], 3)


class TestComparison(unittest.TestCase):
    def test_identical_summaries_compare_equal(self) -> None:
        summary = {
            "schema_version": "v1",
            "row_count": 4,
            "status_counts": {"measured": 4},
            "output_sha256": "c" * 64,
        }
        result = compare_outputs(summary, copy.deepcopy(summary))
        self.assertTrue(result["identical"])
        self.assertEqual(result["differences"], [])

    def test_row_count_difference_is_named(self) -> None:
        locked = {"schema_version": "v1", "row_count": 4}
        reproduced = {"schema_version": "v1", "row_count": 5}
        result = compare_outputs(locked, reproduced)
        self.assertFalse(result["identical"])
        self.assertEqual(result["differences"][0]["field"], "row_count")


class TestReceipt(unittest.TestCase):
    def _receipt(self, **overrides):
        plan = overrides.pop("plan", None) or minimal_plan()
        pinned = plan["component_hashes"]
        defaults = {
            "plan": plan,
            "component_verification": {"verified": True, "mismatched_components": []},
            "input_verification": {"verified": True, "mismatched_inputs": []},
            "stage_results": [
                {
                    "stage": stage,
                    "outcome": "passed",
                    "runtime_seconds": 0.1,
                    "exit_code": 0,
                }
                for stage in REPRODUCTION_STAGES
            ],
            "comparison": {"identical": True, "differences": []},
            "post_run_component_hashes": dict(pinned),
        }
        defaults.update(overrides)
        return build_clean_reproduction_receipt(**defaults)

    def test_synthetic_run_never_claims_real_reproduction(self) -> None:
        receipt = self._receipt()
        self.assertEqual(receipt["evidence_class"], "synthetic_fixture")
        self.assertFalse(receipt["real_clean_reproduction_complete"])
        validate_clean_reproduction_receipt(receipt)

    def test_real_run_with_clean_evidence_completes(self) -> None:
        plan = minimal_plan()
        plan["evidence_class"] = "real"
        receipt = self._receipt(plan=plan)
        self.assertTrue(receipt["real_clean_reproduction_complete"])
        validate_clean_reproduction_receipt(receipt)

    def test_real_run_with_failed_stage_does_not_complete(self) -> None:
        plan = minimal_plan()
        plan["evidence_class"] = "real"
        stages = [
            {"stage": stage, "outcome": "passed", "runtime_seconds": 0.1}
            for stage in REPRODUCTION_STAGES
        ]
        stages[2]["outcome"] = "failed"
        receipt = self._receipt(plan=plan, stage_results=stages)
        self.assertFalse(receipt["real_clean_reproduction_complete"])
        self.assertEqual(receipt["failed_stages"], ["homography"])

    def test_real_run_with_blocking_external_input_does_not_complete(self) -> None:
        plan = minimal_plan()
        plan["evidence_class"] = "real"
        receipt = self._receipt(
            plan=plan, blocking_external_inputs=["person_a_clean_run_bundle"]
        )
        self.assertFalse(receipt["real_clean_reproduction_complete"])

    def test_source_edit_between_stages_is_detected(self) -> None:
        plan = minimal_plan()
        plan["evidence_class"] = "real"
        receipt = self._receipt(
            plan=plan,
            post_run_component_hashes={"src/mineocclude/vision/ssim.py": "f" * 64},
        )
        self.assertTrue(receipt["source_edited_between_stages"])
        self.assertFalse(receipt["real_clean_reproduction_complete"])

    def test_unsupported_stage_outcome_rejects(self) -> None:
        with self.assertRaises(CleanReproductionError):
            self._receipt(
                stage_results=[
                    {"stage": "registry", "outcome": "probably_fine"},
                ]
            )

    def test_forged_completion_claim_rejects_on_validation(self) -> None:
        receipt = self._receipt()
        receipt["real_clean_reproduction_complete"] = True
        with self.assertRaises(CleanReproductionError):
            validate_clean_reproduction_receipt(receipt)

    def test_tampered_receipt_fails_content_hash(self) -> None:
        plan = minimal_plan()
        plan["evidence_class"] = "real"
        receipt = self._receipt(plan=plan)
        receipt["executed_stage_count"] = 99
        with self.assertRaises(CleanReproductionError):
            validate_clean_reproduction_receipt(receipt)


class TestRepositoryRelative(unittest.TestCase):
    def test_inside_root_returns_posix_relative(self) -> None:
        self.assertEqual(
            repository_relative(ROOT / "scripts" / "measure_u4.py", ROOT),
            "scripts/measure_u4.py",
        )

    def test_outside_root_rejects(self) -> None:
        with self.assertRaises(CleanReproductionError):
            repository_relative(ROOT.parent / "elsewhere.json", ROOT)


class TestEnvironmentLock(unittest.TestCase):
    def test_lock_names_the_interpreter(self) -> None:
        lock = environment_lock()
        self.assertIn("python_version", lock)
        self.assertIn("implementation", lock)


if __name__ == "__main__":
    unittest.main()
