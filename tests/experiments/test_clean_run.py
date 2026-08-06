"""Steps 9.1-9.3 — clean-start identity, artifact resolution, and repeatability."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from mineocclude.experiments.clean_run import (
    DEFAULT_ATOL,
    DEFAULT_RTOL,
    CleanRunError,
    CleanRunErrorCode,
    WorkflowCapture,
    WorkflowStep,
    build_clean_run_record,
    compare_repeat,
    environment_hash,
    environment_report,
    resolve_external_artifacts,
    sha256_file,
    verify_clean_start,
)

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_CONFIG = ROOT / "configs" / "experiments" / "clean_run.yaml"


def _index(**overrides):
    document = {
        "index_id": "test-index",
        "local_cache_root": None,
        "artifacts": [
            {
                "artifact_id": "a1",
                "uri": "s3://bucket/a1.json",
                "sha256": "a" * 64,
                "byte_size": 10,
            }
        ],
    }
    document.update(overrides)
    return document


class WorkflowConfigTests(unittest.TestCase):
    def test_the_clean_run_workflow_is_readable_and_complete(self):
        document = yaml.safe_load(WORKFLOW_CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(document["workflow_id"], "person-a-clean-run-v1.0")
        self.assertTrue(document["require_clean_worktree"])
        self.assertTrue(document["steps"])
        self.assertTrue(document["real_only_steps"])

    def test_every_verified_identity_file_exists(self):
        document = yaml.safe_load(WORKFLOW_CONFIG.read_text(encoding="utf-8"))
        for name in document["verify_file_identities"]:
            self.assertIsNotNone(sha256_file(ROOT / name), name)

    def test_every_workflow_step_names_a_real_script(self):
        document = yaml.safe_load(WORKFLOW_CONFIG.read_text(encoding="utf-8"))
        for entry in document["steps"]:
            script = entry["command"][1]
            self.assertTrue((ROOT / script).is_file(), script)

    def test_repeatability_tolerances_match_the_roadmap(self):
        document = yaml.safe_load(WORKFLOW_CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(document["repeatability"]["rtol"], DEFAULT_RTOL)
        self.assertEqual(document["repeatability"]["atol"], DEFAULT_ATOL)


class ArtifactResolverTests(unittest.TestCase):
    def test_approved_artifacts_resolve(self):
        report = resolve_external_artifacts(_index())
        self.assertEqual(report["resolved_count"], 1)
        self.assertEqual(report["unresolved_count"], 0)
        self.assertTrue(report["resolves_through_approved_manifest_only"])

    def test_an_operator_private_directory_is_flagged(self):
        report = resolve_external_artifacts(
            _index(
                artifacts=[
                    {
                        "artifact_id": "a1",
                        "uri": "file:///Users/someone/private/index.json",
                        "sha256": "a" * 64,
                    }
                ]
            )
        )
        self.assertEqual(len(report["private_directory_references"]), 1)
        self.assertFalse(report["resolves_through_approved_manifest_only"])

    def test_an_artifact_without_a_checksum_is_unresolved(self):
        report = resolve_external_artifacts(
            _index(artifacts=[{"artifact_id": "a1", "uri": "s3://bucket/a"}])
        )
        self.assertEqual(report["unresolved_count"], 1)

    def test_an_unapproved_scheme_is_unresolved(self):
        report = resolve_external_artifacts(
            _index(
                artifacts=[
                    {"artifact_id": "a1", "uri": "ftp://host/a", "sha256": "a" * 64}
                ]
            )
        )
        self.assertEqual(report["unresolved_count"], 1)


class CleanStartTests(unittest.TestCase):
    def test_matching_identities_report_ready(self):
        report = verify_clean_start(
            repository_root=ROOT,
            declared={"code_sha": _head()},
            file_identities={
                "configs/experiments/mvp.yaml": sha256_file(
                    ROOT / "configs" / "experiments" / "mvp.yaml"
                )
            },
            external_artifact_index=_index(),
            require_clean_worktree=False,
        )
        self.assertEqual(report["mismatched_identity_count"], 0)
        self.assertTrue(report["ready"])
        self.assertEqual(report["status"], "READY")

    def test_a_mismatched_file_identity_blocks_the_start(self):
        report = verify_clean_start(
            repository_root=ROOT,
            declared={"code_sha": _head()},
            file_identities={"configs/experiments/mvp.yaml": "0" * 64},
            external_artifact_index=_index(),
            require_clean_worktree=False,
        )
        self.assertFalse(report["ready"])
        self.assertEqual(report["mismatched_identity_count"], 1)

    def test_a_private_artifact_reference_blocks_the_start(self):
        report = verify_clean_start(
            repository_root=ROOT,
            declared={"code_sha": _head()},
            file_identities={},
            external_artifact_index=_index(
                artifacts=[
                    {
                        "artifact_id": "a1",
                        "uri": "file:///Users/someone/private/index.json",
                        "sha256": "a" * 64,
                    }
                ]
            ),
            require_clean_worktree=False,
        )
        self.assertFalse(report["ready"])

    def test_the_environment_hash_ignores_the_interpreter_path(self):
        first = environment_report()
        second = {**first, "python_executable": "/somewhere/else/python"}
        self.assertEqual(environment_hash(first), environment_hash(second))


def _head() -> str:
    import subprocess

    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()


class RepeatabilityTests(unittest.TestCase):
    def test_identical_repeats_pass_the_gate(self):
        values = [0.5, -1.25, 3.0]
        report = compare_repeat(values, list(values))
        self.assertTrue(report["within_tolerance"])
        self.assertTrue(report["bitwise_identical"])
        self.assertEqual(report["reproducibility_gate"], "PASS")
        self.assertFalse(report["cross_gpu_bitwise_equality_claimed"])

    def test_a_difference_inside_tolerance_passes(self):
        report = compare_repeat([1.0, 2.0], [1.0004, 2.0005])
        self.assertTrue(report["within_tolerance"])
        self.assertFalse(report["bitwise_identical"])

    def test_a_difference_outside_tolerance_fails_visibly(self):
        report = compare_repeat([1.0, 2.0], [1.0, 2.5])
        self.assertFalse(report["within_tolerance"])
        self.assertEqual(report["reproducibility_gate"], "FAIL")
        self.assertEqual(report["failure_count"], 1)
        self.assertEqual(report["failures"][0]["index"], 1)

    def test_nondeterministic_operations_are_recorded_not_hidden(self):
        report = compare_repeat(
            [1.0], [1.0], nondeterministic_operations=("scatter_add",)
        )
        self.assertEqual(report["nondeterministic_operations"], ["scatter_add"])

    def test_comparison_runs_in_float64_regardless_of_storage_precision(self):
        report = compare_repeat([1.0], [1.0], precision="float16")
        self.assertEqual(report["comparison_precision"], "float64")
        self.assertEqual(report["stored_precision"], "float16")

    def test_mismatched_lengths_are_refused(self):
        with self.assertRaises(CleanRunError) as caught:
            compare_repeat([1.0, 2.0], [1.0])
        self.assertIs(caught.exception.code, CleanRunErrorCode.SHAPE_MISMATCH)

    def test_empty_input_is_refused(self):
        with self.assertRaises(CleanRunError) as caught:
            compare_repeat([], [])
        self.assertIs(caught.exception.code, CleanRunErrorCode.INVALID_REQUEST)

    def test_nested_sequences_are_flattened(self):
        report = compare_repeat([[1.0, 2.0], [3.0]], [[1.0, 2.0], [3.0]])
        self.assertEqual(report["value_count"], 3)


class CleanRunRecordTests(unittest.TestCase):
    def _steps(self):
        return (
            WorkflowStep(
                step_id="s1",
                description="first",
                command=("echo", "hello"),
            ),
        )

    def _capture(self, returncode=0):
        return WorkflowCapture(
            step_id="s1",
            command=("echo", "hello"),
            returncode=returncode,
            stdout="hello\n",
            stderr="",
            wall_seconds=0.01,
        )

    def test_a_synthetic_run_is_never_a_reproduction_claim(self):
        record = build_clean_run_record(
            start_report={"status": "READY"},
            steps=self._steps(),
            captures=(self._capture(),),
            real_inputs_used=False,
            identity={"config_hash": "a" * 64},
        )
        self.assertTrue(record["all_documented_steps_passed"])
        self.assertFalse(record["clean_reproduction_of_real_outputs"])
        self.assertEqual(record["status"], "WORKFLOW_VALIDATED_SYNTHETIC_ONLY")
        self.assertTrue(record["synthetic_run_is_not_a_reproduction_claim"])

    def test_real_inputs_with_passing_steps_is_a_reproduction(self):
        record = build_clean_run_record(
            start_report={"status": "READY"},
            steps=self._steps(),
            captures=(self._capture(),),
            real_inputs_used=True,
            identity={"config_hash": "a" * 64},
        )
        self.assertTrue(record["clean_reproduction_of_real_outputs"])
        self.assertEqual(record["status"], "CLEAN_REPRODUCTION_COMPLETE")

    def test_a_failed_step_is_reported(self):
        record = build_clean_run_record(
            start_report={"status": "READY"},
            steps=self._steps(),
            captures=(self._capture(returncode=1),),
            real_inputs_used=True,
            identity={},
        )
        self.assertEqual(record["failed_step_ids"], ["s1"])
        self.assertEqual(record["status"], "WORKFLOW_FAILED")
        self.assertFalse(record["clean_reproduction_of_real_outputs"])

    def test_a_missing_required_step_is_reported(self):
        record = build_clean_run_record(
            start_report={"status": "READY"},
            steps=(
                *self._steps(),
                WorkflowStep(step_id="s2", description="second", command=("echo",)),
            ),
            captures=(self._capture(),),
            real_inputs_used=True,
            identity={},
        )
        self.assertEqual(record["missing_required_step_ids"], ["s2"])

    def test_stdout_and_stderr_are_captured_and_hashed(self):
        record = build_clean_run_record(
            start_report={},
            steps=self._steps(),
            captures=(self._capture(),),
            real_inputs_used=False,
            identity={},
        )
        capture = record["captures"][0]
        self.assertEqual(capture["stdout"], "hello\n")
        self.assertEqual(len(capture["stdout_sha256"]), 64)
        self.assertIn("wall_seconds", capture)


class WorkflowStepExecutionTests(unittest.TestCase):
    def test_a_step_captures_output_and_return_code(self):
        from mineocclude.experiments.clean_run import run_workflow_step

        with tempfile.TemporaryDirectory() as directory:
            step = WorkflowStep(
                step_id="s1",
                description="print",
                command=(
                    __import__("sys").executable,
                    "-c",
                    "print('captured')",
                ),
            )
            capture = run_workflow_step(step, cwd=directory)
        self.assertEqual(capture.returncode, 0)
        self.assertIn("captured", capture.stdout)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
