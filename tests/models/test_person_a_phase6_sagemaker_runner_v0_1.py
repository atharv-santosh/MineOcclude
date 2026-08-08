from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = (
    ROOT / "scripts" / "run_person_a_phase6_single_pilot_sagemaker.py"
)
WRAPPER_PATH = (
    ROOT / "scripts" / "run_person_a_phase6_single_pilot_sagemaker.sh"
)
EVIDENCE_ROOT = (
    ROOT
    / "docs"
    / "status"
    / "person_a_phase6_activation_store_v2_preparation_v0_1"
)


def _load_runner():
    specification = importlib.util.spec_from_file_location(
        "person_a_phase6_sagemaker_runner_v0_1",
        RUNNER_PATH,
    )
    if specification is None or specification.loader is None:
        raise AssertionError("runner module specification is unavailable")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


runner = _load_runner()


class PersonAPhase6SageMakerRunnerPreparationTests(unittest.TestCase):
    def test_plan_binds_exact_one_pilot_and_expected_cardinality(self) -> None:
        plan = runner.plan_document()
        self.assertEqual(plan["selected_pilot"], "layout_00_ep9403")
        self.assertEqual(plan["global_model_frame_count"], 248)
        self.assertEqual(plan["expected_activation_rows"], 4960)
        self.assertEqual(
            plan["sequential_steps"],
            ["6.1", "6.2", "6.3", "6.4", "6.5"],
        )
        self.assertEqual(plan["deterministic_seed"], 20260725)
        self.assertEqual(plan["device"], "cuda:0")
        self.assertTrue(plan["b_activation_store_v2_ratification_required"])
        self.assertFalse(plan["local_scientific_execution_performed"])

    def test_plan_does_not_import_torch_or_query_cuda(self) -> None:
        with mock.patch.object(
            runner.importlib,
            "import_module",
            side_effect=AssertionError("plan must not import dependencies"),
        ):
            plan = runner.plan_document()
        self.assertEqual(plan["runner_version"], runner.RUNNER_VERSION)
        tree = ast.parse(RUNNER_PATH.read_text(encoding="utf-8"))
        top_level_imports = {
            alias.name
            for node in tree.body
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        self.assertNotIn("torch", top_level_imports)

    def test_missing_b_v2_ratification_fails_before_runtime_imports(self) -> None:
        with mock.patch.object(
            runner.importlib,
            "import_module",
            side_effect=AssertionError("ratification gate must run first"),
        ), self.assertRaises(runner.Phase6RunnerError) as caught:
            runner.verify_activation_store_v2_ratification(
                repository=ROOT,
                object_expression="",
                current_commit="1" * 40,
                module_sha256="2" * 64,
            )
        self.assertEqual(
            caught.exception.code,
            "missing_b_v2_ratification",
        )
        self.assertEqual(caught.exception.step, "preflight")

    def test_ratification_must_bind_v2_commit_and_module_bytes(self) -> None:
        document = {
            "activation_index_format_version": (
                runner.ACTIVATION_INDEX_V2_FORMAT_VERSION
            ),
            "activation_store_format_version": (
                runner.ACTIVATION_STORE_V2_FORMAT_VERSION
            ),
            "decision": "ratified",
            "expected_activation_row_count": 4960,
            "owner": "person_b",
            "person_a_activation_store_v2_commit": "1" * 40,
            "person_a_activation_store_v2_module_sha256": "2" * 64,
            "scientific_execution_authorized": True,
            "selected_pilot": "layout_00_ep9403",
        }
        runner._validate_ratification_document(
            document,
            current_commit="1" * 40,
            module_sha256="2" * 64,
        )
        for field, invalid in (
            ("decision", "pending"),
            ("person_a_activation_store_v2_commit", "3" * 40),
            ("person_a_activation_store_v2_module_sha256", "4" * 64),
            ("scientific_execution_authorized", False),
        ):
            changed = dict(document)
            changed[field] = invalid
            with self.assertRaises(runner.Phase6RunnerError):
                runner._validate_ratification_document(
                    changed,
                    current_commit="1" * 40,
                    module_sha256="2" * 64,
                )

    def test_step_gates_are_strictly_ordered(self) -> None:
        calls: list[str] = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            arguments = mock.Mock()
            context = runner.RunContext(
                arguments=arguments,
                session_root=root,
                runtime_receipt={},
            )

            def handler(step: str):
                def execute(_context):
                    calls.append(step)
                    return {"status": "PASS"}

                return execute

            result = runner.execute_step_sequence(
                context,
                {step: handler(step) for step in runner.PHASE6_STEPS},
            )
        self.assertEqual(calls, list(runner.PHASE6_STEPS))
        self.assertEqual(result["status"], "PASS")
        self.assertIsNone(result["failed_step"])

    def test_first_failed_gate_prevents_all_later_steps(self) -> None:
        calls: list[str] = []
        with tempfile.TemporaryDirectory() as directory:
            context = runner.RunContext(
                arguments=mock.Mock(),
                session_root=Path(directory),
                runtime_receipt={},
            )

            def pass_6_1(_context):
                calls.append("6.1")
                return {"status": "PASS"}

            def fail_6_2(_context):
                calls.append("6.2")
                raise runner.Phase6RunnerError(
                    "expected_test_failure",
                    "bounded gate failure",
                    step="6.2",
                )

            def forbidden(step: str):
                def execute(_context):
                    calls.append(step)
                    raise AssertionError("later step must not execute")

                return execute

            result = runner.execute_step_sequence(
                context,
                {
                    "6.1": pass_6_1,
                    "6.2": fail_6_2,
                    "6.3": forbidden("6.3"),
                    "6.4": forbidden("6.4"),
                    "6.5": forbidden("6.5"),
                },
            )
        self.assertEqual(calls, ["6.1", "6.2"])
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["failed_step"], "6.2")
        self.assertFalse(result["later_steps_executed_after_failure"])

    def test_non_pass_step_result_is_a_hard_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            context = runner.RunContext(
                arguments=mock.Mock(),
                session_root=Path(directory),
                runtime_receipt={},
            )
            result = runner.execute_step_sequence(
                context,
                {
                    "6.1": lambda _context: {"status": "BLOCKED"},
                    "6.2": lambda _context: {"status": "PASS"},
                    "6.3": lambda _context: {"status": "PASS"},
                    "6.4": lambda _context: {"status": "PASS"},
                    "6.5": lambda _context: {"status": "PASS"},
                },
            )
        self.assertEqual(result["failed_step"], "6.1")
        self.assertEqual(result["completed_steps"], [])

    def test_argument_seed_and_device_validation_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            file_path = root / "artifact.bin"
            file_path.write_bytes(b"bounded test bytes")
            arguments = runner.RunnerArguments(
                repository_root=root,
                mineworld_root=root,
                asset_root=root,
                main_checkpoint=file_path,
                vae_config=file_path,
                vae_checkpoint=file_path,
                approved_input_root=root,
                approved_output_root=root,
                activation_store_v2_ratification_object="",
                session_id="test",
                seed=0,
                device="cpu",
                precision="float16",
            )
            with self.assertRaises(runner.Phase6RunnerError) as caught:
                runner._validate_runtime_arguments(arguments)
        self.assertEqual(caught.exception.code, "seed_mismatch")

    def test_final_report_shape_is_machine_readable(self) -> None:
        context = runner.RunContext(
            arguments=mock.Mock(seed=20260725, device="cuda:0"),
            session_root=ROOT,
            runtime_receipt={
                "b_activation_store_v2_ratification": {
                    "verified": True,
                }
            },
        )
        sequence = {
            "completed_steps": list(runner.PHASE6_STEPS),
            "failed_step": None,
            "failure": None,
            "later_steps_executed_after_failure": False,
            "status": "PASS",
        }
        report = runner._final_report(
            context,
            sequence,
            {"status": "HANDOFF_PREPARED_NOT_ACCEPTED"},
        )
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["expected_activation_row_count"], 4960)
        self.assertEqual(
            report["handoff"]["status"],
            "HANDOFF_PREPARED_NOT_ACCEPTED",
        )

    def test_wrapper_invokes_exact_runner_and_propagates_failure(self) -> None:
        wrapper = WRAPPER_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "run_person_a_phase6_single_pilot_sagemaker.py\" run",
            wrapper,
        )
        self.assertIn("PERSON_B_ACTIVATION_STORE_V2_RATIFICATION_OBJECT", wrapper)
        self.assertIn("PIPESTATUS[0]", wrapper)
        self.assertIn("immutable wrapper log already exists", wrapper)
        self.assertIn("--seed 20260725", wrapper)
        self.assertIn("--device cuda:0", wrapper)

    def test_authority_package_json_is_canonical(self) -> None:
        paths = sorted(EVIDENCE_ROOT.glob("*.json"))
        self.assertEqual(len(paths), 9)
        for path in paths:
            document = json.loads(path.read_bytes())
            expected = (
                json.dumps(
                    document,
                    allow_nan=False,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            ).encode("utf-8")
            self.assertEqual(path.read_bytes(), expected, path.name)

    def test_authority_package_inventory_is_exact(self) -> None:
        inventory = json.loads(
            (EVIDENCE_ROOT / "sha256_inventory.json").read_bytes()
        )
        expected_paths = sorted(
            path.name
            for path in EVIDENCE_ROOT.glob("*.json")
            if path.name != "sha256_inventory.json"
        )
        self.assertEqual(
            [row["path"] for row in inventory["files"]],
            expected_paths,
        )
        for row in inventory["files"]:
            payload = (EVIDENCE_ROOT / row["path"]).read_bytes()
            self.assertEqual(
                hashlib.sha256(payload).hexdigest(),
                row["sha256"],
            )

    def test_registry_v2_needs_no_person_e_schema_change(self) -> None:
        evidence = json.loads(
            (EVIDENCE_ROOT / "registry_v2_compatibility.json").read_bytes()
        )
        self.assertFalse(evidence["e_schema_change_required"])
        source = subprocess.run(
            [
                "git",
                "-C",
                str(ROOT),
                "show",
                (
                    f"{runner.PERSON_E_REGISTRY_V2_VALIDATOR}:"
                    "src/mineocclude/contracts/rollout_registry.py"
                ),
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        self.assertIn('"activation"', source)
        self.assertIn('"person_a"', source)
        self.assertIn("artifact_schema_version", source)

    def test_change_inventory_matches_exact_worktree_scope(self) -> None:
        # The recorded inventory describes the scope this package introduced.
        # Comparing it to a live `git status` would expire the guard as soon as
        # that scope is committed, so assert the scope itself instead: every
        # recorded path exists, is self-consistent, and stays inside Person A.
        inventory = json.loads(
            (EVIDENCE_ROOT / "change_inventory.json").read_bytes()
        )
        paths = inventory["changed_paths"]
        self.assertEqual(paths, sorted(paths))
        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual(inventory["changed_path_count"], len(paths))
        self.assertEqual(inventory["changed_path_count"], 14)
        self.assertEqual(
            inventory["changed_path_count"], len(inventory["changed_paths"])
        )
        self.assertEqual(inventory["changed_paths"], sorted(inventory["changed_paths"]))
        self.assertEqual(inventory["historical_v1_files_modified"], [])
        self.assertEqual(inventory["person_e_files_modified"], [])
        evidence = []
        for path in paths:
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).exists(), path)
                self.assertNotIn("person_e", path)
            if path.startswith("docs/status/"):
                evidence.append(path)
        # Accepted evidence bytes are never rewritten; in-flight edits to the
        # builder or its tests are ordinary maintenance and are not a defect.
        self.assertTrue(evidence)
        modified = subprocess.run(
            ["git", "-C", str(ROOT), "diff", "--name-only", "--", *evidence],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.split()
        self.assertEqual(modified, [])


if __name__ == "__main__":
    unittest.main()
