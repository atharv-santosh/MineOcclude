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
    ROOT
    / "scripts"
    / "run_person_a_phase6_single_pilot_sagemaker_resume_step6_3.py"
)
WRAPPER_PATH = (
    ROOT
    / "scripts"
    / "run_person_a_phase6_single_pilot_sagemaker_resume_step6_3.sh"
)
EVIDENCE_ROOT = (
    ROOT
    / "docs"
    / "status"
    / "person_a_phase6_step6_3_resume_preparation_v0_1"
)


def _load_runner():
    specification = importlib.util.spec_from_file_location(
        "person_a_phase6_step6_3_resume_preparation_v0_1",
        RUNNER_PATH,
    )
    if specification is None or specification.loader is None:
        raise AssertionError("resume runner module is unavailable")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


runner = _load_runner()
base = runner.base


def _write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        (
            json.dumps(
                document,
                allow_nan=False,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    )


def _prior_fixture(root: Path) -> dict:
    prior_input = root / "approved-inputs" / runner.PRIOR_SESSION_ID
    prior_output = root / "approved-outputs" / runner.PRIOR_SESSION_ID
    prior_input.mkdir(parents=True)
    prior_output.mkdir(parents=True)
    payloads = {
        name: f"fixture:{name}\n".encode()
        for name in runner.SOURCE_FILENAMES
    }
    for name, filename in runner.SOURCE_FILENAMES.items():
        (prior_input / filename).write_bytes(payloads[name])
    config_blob = b"fixture:model-config\n"
    (
        prior_input / runner.MODEL_CONFIG_PROVENANCE_FILENAME
    ).write_bytes(config_blob)
    identity_hashes = {
        name: hashlib.sha256(payloads[name]).hexdigest()
        for name in ("capture_package", "frame_map", "state")
    }
    direct_hashes = {
        name: hashlib.sha256(payloads[name]).hexdigest()
        for name in (
            "frame_map",
            "media",
            "normalized_actions",
            "raw_actions",
            "state",
            "visibility",
        )
    }
    step6_1 = {
        "elapsed_seconds": 1.0,
        "result": {
            "accepted_manifest_sha256": hashlib.sha256(
                payloads["accepted_manifest"]
            ).hexdigest(),
            "capture_package_sha256": identity_hashes["capture_package"],
            "direct_input_hashes": direct_hashes,
            "input_root": str(prior_input),
            "pilot": base.SELECTED_PILOT,
            "status": "PASS",
        },
        "status": "PASS",
        "step": "6.1",
    }
    step6_2 = {
        "elapsed_seconds": 1.0,
        "result": {
            "frame_count": base.GLOBAL_MODEL_FRAME_COUNT,
            "identity_ambiguity_count": 0,
            "pilot": base.SELECTED_PILOT,
            "status": "PASS",
            "stream_counts": {
                "frame_map": base.GLOBAL_MODEL_FRAME_COUNT,
                "normalized_actions": base.GLOBAL_MODEL_FRAME_COUNT,
                "raw_actions": base.GLOBAL_MODEL_FRAME_COUNT,
                "server_state": base.GLOBAL_MODEL_FRAME_COUNT,
                "visibility": base.GLOBAL_MODEL_FRAME_COUNT,
            },
        },
        "status": "PASS",
        "step": "6.2",
    }
    _write_json(prior_output / "step6_1.json", step6_1)
    _write_json(prior_output / "step6_2.json", step6_2)
    runtime = {
        "branch": base.REQUIRED_BRANCH,
        "git_commit": runner.PRIOR_PERSON_A_COMMIT,
        "mineworld_commit": base.MINEWORLD_REVISION,
        "model_config_git_blob_sha256": hashlib.sha256(
            config_blob
        ).hexdigest(),
        "runner_version": runner.PRIOR_RUNNER_VERSION,
        "seed": base.DETERMINISTIC_SEED,
        "status": "PASS",
    }
    _write_json(
        prior_output / "runtime_preflight_receipt.json",
        runtime,
    )
    report = {
        "deterministic_seed": base.DETERMINISTIC_SEED,
        "handoff": None,
        "runner_version": runner.PRIOR_RUNNER_VERSION,
        "selected_pilot": base.SELECTED_PILOT,
        "sequence": {
            "completed_steps": ["6.1", "6.2"],
            "failed_step": "6.3",
            "later_steps_executed_after_failure": False,
            "status": "FAIL",
        },
        "status": "FAIL",
        "step_receipts": [step6_1, step6_2],
    }
    report_path = prior_output / "final_report.json"
    _write_json(report_path, report)
    wrapper_log = (
        prior_output.parent
        / "wrapper-logs"
        / f"{runner.PRIOR_SESSION_ID}.log"
    )
    wrapper_log.parent.mkdir()
    wrapper_log.write_bytes(b"immutable fixture log\n")
    return {
        "config_blob": config_blob,
        "identity_hashes": identity_hashes,
        "input": prior_input,
        "log_hash": hashlib.sha256(wrapper_log.read_bytes()).hexdigest(),
        "output": prior_output,
        "payloads": payloads,
        "report_hash": hashlib.sha256(report_path.read_bytes()).hexdigest(),
    }


def _validate_fixture(fixture: dict):
    return runner.validate_prior_evidence(
        prior_input_root=fixture["input"],
        prior_output_root=fixture["output"],
        expected_source_payloads=fixture["payloads"],
        model_config_git_blob=fixture["config_blob"],
        expected_final_report_sha256=fixture["report_hash"],
        expected_wrapper_log_sha256=fixture["log_hash"],
        expected_identity_hashes=fixture["identity_hashes"],
        expected_model_config_sha256=hashlib.sha256(
            fixture["config_blob"]
        ).hexdigest(),
        enforce_production_paths=False,
    )


class PersonAPhase6Step63ResumePreparationTests(unittest.TestCase):
    def test_confirmed_defect_is_reproduced_from_starting_authority(
        self,
    ) -> None:
        source = base._git_object_bytes(
            ROOT,
            (
                f"{runner.PRIOR_PERSON_A_COMMIT}:"
                "scripts/run_person_a_phase6_single_pilot_sagemaker.py"
            ),
        ).decode("utf-8")
        self.assertIn(
            '"model_config_path": model_config_path',
            source,
        )
        self.assertIn(
            'model_config_path=context.state["model_config_path"]',
            source,
        )
        self.assertIn('intake_root / "700M_16f.git-blob.yaml"', source)

    def test_physical_config_matches_git_object_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / base.MODEL_CONFIG_PATH
            path.parent.mkdir()
            payload = b"authoritative bytes\n"
            path.write_bytes(payload)
            resolved = base.validated_physical_model_config_path(
                mineworld_root=root,
                git_blob_bytes=payload,
                expected_path=path.resolve(),
                expected_sha256=hashlib.sha256(payload).hexdigest(),
            )
        self.assertEqual(resolved, path.resolve())

    def test_incorrect_config_path_or_bytes_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / base.MODEL_CONFIG_PATH
            path.parent.mkdir()
            path.write_bytes(b"physical")
            with self.assertRaises(base.Phase6RunnerError):
                base.validated_physical_model_config_path(
                    mineworld_root=root,
                    git_blob_bytes=b"physical",
                    expected_path=root / "alternate.yaml",
                    expected_sha256=hashlib.sha256(b"physical").hexdigest(),
                )
            with self.assertRaises(base.Phase6RunnerError):
                base.validated_physical_model_config_path(
                    mineworld_root=root,
                    git_blob_bytes=b"different",
                    expected_path=path.resolve(),
                    expected_sha256=hashlib.sha256(b"different").hexdigest(),
                )

    def test_symlink_model_config_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / base.MODEL_CONFIG_PATH
            path.parent.mkdir()
            path.write_bytes(b"same")
            with mock.patch.object(
                Path,
                "is_symlink",
                return_value=True,
            ), self.assertRaises(base.Phase6RunnerError):
                base.validated_physical_model_config_path(
                    mineworld_root=root,
                    git_blob_bytes=b"same",
                    expected_path=path.resolve(),
                    expected_sha256=hashlib.sha256(b"same").hexdigest(),
                )

    def test_adapter_request_uses_physical_not_provenance_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = root / "runtime_preflight_receipt.json"
            receipt.write_bytes(b"{}\n")
            physical = root / base.MODEL_CONFIG_PATH
            provenance = root / "700M_16f.git-blob.yaml"
            arguments = mock.Mock(
                repository_root=ROOT,
                mineworld_root=root,
                main_checkpoint=root / "main.pt",
                vae_config=root / "vae.json",
                vae_checkpoint=root / "vae.pt",
                session_id="resume",
                precision="float16",
                device="cuda:0",
                # RuntimeLoadRequest validates every checkpoint identity as a
                # 64-hex digest, so these must be supplied rather than left as
                # auto-generated Mock attributes.
                expected_model_config_sha256="a" * 64,
                expected_main_checkpoint_sha256="b" * 64,
                expected_vae_config_sha256="c" * 64,
                expected_vae_checkpoint_sha256="d" * 64,
            )
            context = base.RunContext(
                arguments=arguments,
                session_root=root,
                runtime_receipt={},
                state={"model_config_provenance_path": provenance},
            )
            with mock.patch.object(
                base,
                "_git_object_bytes",
                return_value=b"blob",
            ), mock.patch.object(
                base,
                "validated_physical_model_config_path",
                return_value=physical,
            ) as validate:
                request = base._runtime_load_request(context)
        self.assertEqual(request.model_config_path, physical)
        self.assertNotEqual(request.model_config_path, provenance)
        self.assertEqual(validate.call_args.kwargs["git_blob_bytes"], b"blob")

    def test_prior_report_log_and_pass_receipts_validate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = _prior_fixture(Path(directory))
            prior = _validate_fixture(fixture)
        self.assertEqual(
            prior.final_report["sequence"]["completed_steps"],
            ["6.1", "6.2"],
        )
        self.assertEqual(prior.step6_1_receipt["status"], "PASS")
        self.assertEqual(prior.step6_2_receipt["status"], "PASS")

    def test_changed_prior_input_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = _prior_fixture(Path(directory))
            (
                fixture["input"]
                / runner.SOURCE_FILENAMES["media"]
            ).write_bytes(b"changed")
            with self.assertRaises(base.Phase6RunnerError):
                _validate_fixture(fixture)

    def test_changed_report_or_log_hash_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = _prior_fixture(Path(directory))
            fixture["report_hash"] = "0" * 64
            with self.assertRaises(base.Phase6RunnerError) as caught:
                _validate_fixture(fixture)
        self.assertEqual(
            caught.exception.code,
            "prior_final_report_hash_mismatch",
        )

    def test_existing_step6_4_activation_store_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = _prior_fixture(Path(directory))
            store = fixture["output"].parent / (
                f"{runner.PRIOR_SESSION_ID}-activation-store-v2"
            )
            store.mkdir()
            with self.assertRaises(base.Phase6RunnerError) as caught:
                _validate_fixture(fixture)
        self.assertEqual(
            caught.exception.code,
            "prior_activation_output_exists",
        )

    def test_prior_directories_remain_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = _prior_fixture(Path(directory))
            prior = _validate_fixture(fixture)
            after = runner._immutable_inventory(
                fixture["input"],
                fixture["output"],
                prior.wrapper_log_path,
            )
        self.assertEqual(after, prior.immutable_inventory)

    def test_resume_sequence_starts_at_6_3_and_never_calls_prior_steps(
        self,
    ) -> None:
        calls: list[str] = []
        with tempfile.TemporaryDirectory() as directory:
            context = base.RunContext(
                arguments=mock.Mock(),
                session_root=Path(directory),
                runtime_receipt={},
            )

            def handler(step: str):
                def execute(_context):
                    calls.append(step)
                    return {"status": "PASS"}

                return execute

            result = runner._execute_resume_sequence(
                context,
                {
                    step: handler(step)
                    for step in runner.RESUME_STEPS
                },
            )
        self.assertEqual(calls, ["6.3", "6.4", "6.5"])
        self.assertTrue(result["steps_6_1_and_6_2_reexecuted"] is False)
        self.assertEqual(result["resume_start_step"], "6.3")

    def test_continuation_identity_is_distinct_and_deterministic(self) -> None:
        first = runner.continuation_identity(repaired_commit="1" * 40)
        second = runner.continuation_identity(repaired_commit="1" * 40)
        changed = runner.continuation_identity(repaired_commit="2" * 40)
        self.assertEqual(first, second)
        self.assertNotEqual(first, changed)
        self.assertNotEqual(first, runner.PRIOR_SESSION_ID)

    def test_old_b_object_is_insufficient_and_new_object_is_exact(self) -> None:
        current = "1" * 40
        runner_hash = "2" * 64
        module_hash = base._sha256_file(
            ROOT
            / "src"
            / "mineocclude"
            / "activations"
            / "store_v2.py"
        )
        old = {
            "activation_index_format_version": (
                base.ACTIVATION_INDEX_V2_FORMAT_VERSION
            ),
            "activation_store_format_version": (
                base.ACTIVATION_STORE_V2_FORMAT_VERSION
            ),
            "decision": "ratified",
            "expected_activation_row_count": 4960,
            "owner": "person_b",
            "person_a_activation_store_v2_commit": current,
            "person_a_activation_store_v2_module_sha256": module_hash,
            "scientific_execution_authorized": True,
            "selected_pilot": "layout_00_ep9403",
        }
        base._validate_ratification_document(
            old,
            current_commit=current,
            module_sha256=module_hash,
        )
        with self.assertRaises(base.Phase6RunnerError):
            runner._validate_resume_ratification_document(
                old,
                current_commit=current,
                resume_runner_sha256=runner_hash,
            )
        document = {
            "activation_index_format_version": (
                base.ACTIVATION_INDEX_V2_FORMAT_VERSION
            ),
            "activation_store_format_version": (
                base.ACTIVATION_STORE_V2_FORMAT_VERSION
            ),
            "config_runtime_path_repair_authorized": True,
            "decision": "ratified",
            "expected_activation_row_count": 4960,
            "owner": "person_b",
            "person_a_activation_store_v2_commit": current,
            "person_a_activation_store_v2_module_sha256": module_hash,
            "person_a_repaired_commit": current,
            "person_a_resume_runner_sha256": runner_hash,
            "prior_final_report_sha256": (
                runner.PRIOR_FINAL_REPORT_SHA256
            ),
            "prior_wrapper_log_sha256": (
                runner.PRIOR_WRAPPER_LOG_SHA256
            ),
            "reuse_prior_steps_6_1_6_2_authorized": True,
            "resume_start_step": "6.3",
            "scientific_execution_authorized": True,
            "seed": 20260725,
            "selected_pilot": "layout_00_ep9403",
            "unchanged_authorization_boundary": True,
        }
        runner._validate_resume_ratification_document(
            document,
            current_commit=current,
            resume_runner_sha256=runner_hash,
        )

    def test_plan_does_not_import_runtime_or_query_cuda(self) -> None:
        with mock.patch.object(
            runner.importlib,
            "import_module",
            side_effect=AssertionError("plan must not import runtime modules"),
        ):
            plan = runner.plan_document()
        self.assertEqual(plan["resume_start_step"], "6.3")
        self.assertEqual(plan["resume_steps"], ["6.3", "6.4", "6.5"])
        self.assertFalse(plan["local_scientific_execution_performed"])
        tree = ast.parse(RUNNER_PATH.read_text(encoding="utf-8"))
        top_level = {
            alias.name
            for node in tree.body
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        self.assertNotIn("torch", top_level)

    def test_wrapper_is_explicit_resume_and_requires_new_b_object(self) -> None:
        wrapper = WRAPPER_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "run_person_a_phase6_single_pilot_sagemaker_resume_step6_3.py",
            wrapper,
        )
        self.assertIn(
            "PERSON_B_PHASE6_STEP6_3_RESUME_RATIFICATION_OBJECT",
            wrapper,
        )
        self.assertIn(" continuation-id ", wrapper)
        self.assertIn(" resume ", wrapper)
        self.assertIn("--seed 20260725", wrapper)

    def test_evidence_is_canonical_and_inventory_is_exact(self) -> None:
        paths = sorted(EVIDENCE_ROOT.glob("*.json"))
        self.assertGreaterEqual(len(paths), 7)
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
        inventory = json.loads(
            (EVIDENCE_ROOT / "sha256_inventory.json").read_bytes()
        )
        expected_paths = sorted(
            path.name
            for path in paths
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
        # The recorded scope is asserted against itself and the worktree, not
        # against a live `git status`, which would expire once this package is
        # committed.
        change_inventory = json.loads(
            (EVIDENCE_ROOT / "change_inventory.json").read_bytes()
        )
        changed_paths = change_inventory["changed_paths"]
        self.assertEqual(changed_paths, sorted(changed_paths))
        self.assertEqual(len(changed_paths), len(set(changed_paths)))
        self.assertEqual(
            len(changed_paths),
            change_inventory["changed_path_count"],
        )
        evidence = []
        for path in changed_paths:
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).exists(), path)
            if path.startswith("docs/status/"):
                evidence.append(path)
        # Accepted evidence bytes are never rewritten; in-flight edits to the
        # runner or its tests are ordinary maintenance and are not a defect.
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
