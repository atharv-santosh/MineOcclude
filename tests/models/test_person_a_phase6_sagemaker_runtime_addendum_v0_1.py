"""Focused validation for Person A's Phase 6 SageMaker runtime addendum."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_ROOT = (
    ROOT / "docs" / "status" / "person_a_phase6_sagemaker_runtime_addendum_v0_1"
)
MINEWORLD_SOURCE_ROOT = Path(
    os.environ.get("MINEWORLD_SOURCE_ROOT", Path.home() / "MineWorld-Upstream")
)
OUTPUTS = {
    "authority_binding.json",
    "deterministic_seed_decision.json",
    "execution_host_contract.json",
    "git_blob_identity_receipt.json",
    "runtime_preflight_contract.json",
    "sha256_inventory.json",
    "validation_receipt.json",
}
PERSON_A_AUTHORITY = "ca3f5695dc37f9f2c8066e323b25485c042b6cf7"
PERSON_B_AUTHORITY = "43e5ac83004cce2145384c1383f2c3820311af14"
PERSON_C_AUTHORITY = "f0d4e895b56fc4ca3f4805aa13b73545744af1b0"
MINEWORLD_AUTHORITY = "9f49efbcc68a5f0cf60e78f0abc566eac409282f"
MODEL_CONFIG_PATH = "configs/700M_16f.yaml"
MODEL_CONFIG_SHA256 = "e13b3a80fb370547a05852809c2c8f02d05ebe2fce3b3bb2fd1ee54eee78c018"
WINDOWS_CONFIG_SHA256 = (
    "ec397bb74aae0decc46e8ef7ddf460555d15603276239200e90e1bc41d65d223"
)
CANONICAL_SEED = 20260725


def _git_bytes(commit: str, path: str, *, root: Path = ROOT) -> bytes:
    return subprocess.run(
        ["git", "-C", str(root), "show", f"{commit}:{path}"],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout


def _document(name: str) -> dict[str, Any]:
    return json.loads((EVIDENCE_ROOT / name).read_bytes())


def _seed_from_command(document: dict[str, Any]) -> int:
    command = document["command"]
    index = command.index("--seed")
    return int(command[index + 1])


class PersonAPhase6SageMakerRuntimeAddendumTests(unittest.TestCase):
    def test_exact_output_set(self) -> None:
        self.assertEqual(
            {path.name for path in EVIDENCE_ROOT.glob("*.json")},
            OUTPUTS,
        )

    def test_every_document_is_canonical_json(self) -> None:
        for path in EVIDENCE_ROOT.glob("*.json"):
            with self.subTest(path=path.name):
                document = json.loads(path.read_bytes())
                expected = (
                    json.dumps(
                        document,
                        indent=2,
                        sort_keys=True,
                        ensure_ascii=False,
                    )
                    + "\n"
                ).encode()
                self.assertEqual(path.read_bytes(), expected)

    def test_inventory_hashes_every_non_inventory_document(self) -> None:
        inventory = _document("sha256_inventory.json")
        self.assertEqual(inventory["file_count"], len(OUTPUTS))
        self.assertIs(inventory["inventory_excludes_self"], True)
        self.assertEqual(
            set(inventory["files"]),
            OUTPUTS - {"sha256_inventory.json"},
        )
        for name, expected in inventory["files"].items():
            with self.subTest(path=name):
                actual = hashlib.sha256((EVIDENCE_ROOT / name).read_bytes())
                self.assertEqual(actual.hexdigest(), expected)

    def test_bound_authority_documents_match_exact_git_objects(self) -> None:
        binding = _document("authority_binding.json")
        for authority in binding["authorities"].values():
            commit = authority["commit"]
            for source in authority["source_documents"]:
                raw = _git_bytes(commit, source["path"])
                self.assertEqual(len(raw), source["byte_size"])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), source["sha256"])

    def test_b_authorizes_only_the_selected_single_pilot(self) -> None:
        path = (
            "docs/status/person_b_phase4_step4_1_step6_"
            "final_runtime_authorization_v0_1/combined_runtime_authorization.json"
        )
        document = json.loads(_git_bytes(PERSON_B_AUTHORITY, path))
        scope = document["authorization_scope"]
        self.assertIs(document["person_a_runtime_execution"]["authorized"], True)
        self.assertEqual(scope["authorized_pilot_count"], 1)
        self.assertEqual(scope["selected_trajectory_id"], "layout_00_ep9403")
        self.assertIs(
            document["future_person_a_registry_v2_output_acceptance_authorized"],
            False,
        )

    def test_c_acceptance_is_exactly_bound(self) -> None:
        path = (
            "docs/status/person_c_phase4_step4_1_registry_v2_handoff_v0_1/"
            "selected_pilot_acceptance.json"
        )
        document = json.loads(_git_bytes(PERSON_C_AUTHORITY, path))
        self.assertEqual(
            document["decision"],
            "ACCEPT_SINGLE_PILOT_FOR_SCIENTIFIC_USE",
        )
        self.assertEqual(document["trajectory_id"], "layout_00_ep9403")
        self.assertEqual(
            document["git_object_sha256"],
            "21ea1dba91cf92ad82080088f70905fba053557392437b19591cad1333667213",
        )

    def test_a_acknowledgement_is_exactly_bound(self) -> None:
        path = (
            "docs/status/person_a_step6_runtime_acknowledgement_v0_1/"
            "runtime_acknowledgement.json"
        )
        document = json.loads(_git_bytes(PERSON_A_AUTHORITY, path))
        self.assertIs(
            document["person_a_signer_acknowledgement_complete"],
            True,
        )
        self.assertIs(document["production_execution_started"], False)
        self.assertIs(document["person_a_phase6_authorized"], False)

    def test_authoritative_model_config_is_exact_git_blob(self) -> None:
        raw = _git_bytes(
            MINEWORLD_AUTHORITY,
            MODEL_CONFIG_PATH,
            root=MINEWORLD_SOURCE_ROOT,
        )
        receipt = _document("git_blob_identity_receipt.json")
        authoritative = receipt["authoritative_git_blob"]
        self.assertEqual(len(raw), authoritative["byte_size"])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), MODEL_CONFIG_SHA256)
        self.assertEqual(authoritative["sha256"], MODEL_CONFIG_SHA256)
        self.assertIs(authoritative["verified"], True)

    def test_windows_crlf_hash_is_rejected_as_authority(self) -> None:
        receipt = _document("git_blob_identity_receipt.json")
        observation = receipt["windows_working_tree_observation"]
        self.assertEqual(observation["sha256"], WINDOWS_CONFIG_SHA256)
        self.assertIs(observation["crlf_materialization_only"], True)
        self.assertIs(observation["rejected_as_frozen_authority"], True)
        self.assertIs(
            receipt["execution_policy"][
                "altered_working_tree_bytes_authorize_execution"
            ],
            False,
        )

    def test_existing_gpu_runtime_seed_is_unique(self) -> None:
        decision = _document("deterministic_seed_decision.json")
        observed: set[int] = set()
        for source in decision["provenance"]:
            raw = _git_bytes(source["commit"], source["path"])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), source["sha256"])
            value = _seed_from_command(json.loads(raw))
            self.assertEqual(value, source["value"])
            observed.add(value)
        self.assertEqual(observed, {CANONICAL_SEED})
        self.assertEqual(decision["unique_existing_seed_count"], 1)
        self.assertEqual(decision["candidate_seed_values_found"], [CANONICAL_SEED])

    def test_seed_application_scope_is_complete(self) -> None:
        decision = _document("deterministic_seed_decision.json")
        self.assertEqual(decision["canonical_seed"], CANONICAL_SEED)
        self.assertEqual(
            set(decision["application_scope"]),
            {
                "python",
                "numpy",
                "pytorch_cpu",
                "pytorch_cuda",
                "model_execution",
                "repeat_extraction",
                "deterministic_audit_row_selection",
            },
        )
        self.assertIs(decision["decision_complete"], True)
        self.assertIs(decision["derived_from_wall_clock_time"], False)
        self.assertIs(decision["derived_from_machine_state"], False)
        self.assertIs(decision["derived_from_random_output"], False)

    def test_person_b_must_ratify_seed_before_execution(self) -> None:
        decision = _document("deterministic_seed_decision.json")
        preflight = _document("runtime_preflight_contract.json")
        self.assertIs(decision["b_ratification_present"], False)
        self.assertIs(decision["b_ratification_required_before_execution"], True)
        prerequisites = preflight["authority_prerequisites"]
        self.assertIs(prerequisites["person_b_seed_ratification_present"], False)
        self.assertIs(prerequisites["person_b_seed_ratification_required"], True)
        self.assertIs(preflight["execution_gate"]["preflight_gate_open"], False)

    def test_sagemaker_cuda_host_contract_is_fail_closed(self) -> None:
        contract = _document("execution_host_contract.json")
        boundary = contract["execution_boundary"]
        self.assertEqual(
            boundary["allowed_production_environment"],
            "aws_sagemaker_linux_gpu",
        )
        self.assertEqual(boundary["required_cuda_device"], "cuda:0")
        self.assertIs(boundary["sagemaker_gpu_execution_required"], True)
        self.assertIs(boundary["torch_cuda_is_available_required"], True)
        self.assertIs(boundary["local_cpu_execution_authorized"], False)
        self.assertIs(boundary["local_windows_host_cpu_only"], True)
        self.assertIs(
            boundary["production_execution_authorized_by_this_addendum"],
            False,
        )

    def test_runtime_receipt_is_required_before_step6_1(self) -> None:
        contract = _document("execution_host_contract.json")
        receipt = contract["required_pre_step6_1_runtime_receipt"]
        self.assertIs(receipt["capture_before_step6_1"], True)
        self.assertEqual(
            set(receipt["required_fields"]),
            {
                "aws_sagemaker_environment_identity",
                "cuda_device_identity",
                "cuda_runtime_and_toolkit_identity",
                "dependency_lock_and_installed_package_identity",
                "gpu_driver_identity",
                "gpu_model_and_memory_identity",
                "mineocclude_commit_and_clean_state",
                "mineworld_commit_and_clean_state",
                "python_identity",
                "pytorch_build_and_cuda_identity",
            },
        )

    def test_no_execution_or_scientific_output_is_claimed(self) -> None:
        receipt = _document("validation_receipt.json")
        self.assertIs(receipt["phase6_step_execution_started"], False)
        self.assertIs(receipt["model_loaded"], False)
        self.assertIs(receipt["scientific_execution_performed"], False)
        self.assertIs(receipt["scientific_artifacts_generated"], False)
        self.assertIs(receipt["u4_output_inspected"], False)
        states = _document("runtime_preflight_contract.json")["step_execution_state"]
        self.assertTrue(all(value is False for value in states.values()))


if __name__ == "__main__":
    unittest.main()
