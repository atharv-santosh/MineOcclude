"""Focused tests for Person A's non-executing Step 6 acknowledgement."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BUILDER_PATH = ROOT / "scripts" / "build_person_a_step6_runtime_acknowledgement_v0_1.py"
EVIDENCE_ROOT = ROOT / "docs" / "status" / "person_a_step6_runtime_acknowledgement_v0_1"
spec = importlib.util.spec_from_file_location(
    "person_a_step6_ack_builder", BUILDER_PATH
)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load builder: {BUILDER_PATH}")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def _documents() -> dict[str, Any]:
    return {
        path.name: json.loads(path.read_bytes())
        for path in sorted(EVIDENCE_ROOT.glob("*.json"))
    }


class PersonAStep6RuntimeAcknowledgementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.documents = _documents()

    def test_exact_person_a_and_b_authorities_exist(self) -> None:
        builder.verify_authorities()
        authority = self.documents["authority_binding.json"]["authorities"]
        self.assertEqual(
            authority["person_a"]["starting_authority"],
            builder.A_STARTING_AUTHORITY,
        )
        self.assertEqual(
            authority["person_b_refresh"]["refresh_authority"],
            builder.B_REFRESH_AUTHORITY,
        )

    def test_all_source_records_match_exact_git_objects(self) -> None:
        records = self.documents["authority_binding.json"]["source_records"]
        self.assertEqual(len(records), len(builder.A_SOURCES) + len(builder.B_SOURCES))
        for record in records:
            raw = builder._git_bytes(record["source_commit"], record["path"])
            self.assertEqual(record["sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(record["byte_size"], len(raw))

    def test_b_refresh_is_conditional_scope_approval(self) -> None:
        raw = builder._git_bytes(
            builder.B_REFRESH_AUTHORITY,
            builder.B_SOURCES["authorization_decision"]["path"],
        )
        decision = json.loads(raw)
        runtime = decision["decision_layers"]["person_a_runtime_execution"]
        self.assertIs(runtime["authorized"], False)
        self.assertEqual(
            runtime["b_decision_contribution"]["decision"],
            "CONDITIONAL_SCOPE_APPROVAL",
        )

    def test_b_required_acknowledgement_fields_are_present(self) -> None:
        raw = builder._git_bytes(
            builder.B_REFRESH_AUTHORITY,
            builder.B_SOURCES["person_a_required_acknowledgement"]["path"],
        )
        required = set(json.loads(raw)["required_acknowledgement_fields"])
        acknowledgement = self.documents["runtime_acknowledgement.json"]
        self.assertTrue(required <= set(acknowledgement))

    def test_person_a_signer_acknowledgement_is_complete(self) -> None:
        acknowledgement = self.documents["runtime_acknowledgement.json"]
        self.assertIs(
            acknowledgement["person_a_signer_acknowledgement_complete"],
            True,
        )
        self.assertEqual(acknowledgement["owner"], "person_a")
        self.assertEqual(
            acknowledgement["owner_authority_commit"],
            builder.A_STARTING_AUTHORITY,
        )

    def test_person_a_accepts_bounded_step_responsibility(self) -> None:
        acknowledgement = self.documents["runtime_acknowledgement.json"]
        self.assertIs(
            acknowledgement["accepts_responsibility_for_bounded_steps"],
            True,
        )
        self.assertEqual(
            acknowledgement["bounded_steps"],
            list(builder.BOUNDED_STEPS),
        )

    def test_acknowledgement_does_not_self_authorize_phase6(self) -> None:
        acknowledgement = self.documents["runtime_acknowledgement.json"]
        self.assertIs(acknowledgement["self_authorizes_phase6"], False)
        self.assertIs(acknowledgement["person_a_phase6_authorized"], False)
        self.assertIs(
            acknowledgement["automatic_phase6_transition_allowed"],
            False,
        )

    def test_frozen_configuration_identity_is_exact(self) -> None:
        configuration = self.documents["frozen_runtime_configuration.json"]
        expected = builder.A_SOURCES["immutable_runtime_configuration"]["sha256"]
        self.assertEqual(configuration["configuration_identity"], expected)
        self.assertEqual(configuration["source_commit"], builder.A_STARTING_AUTHORITY)

    def test_checkpoint_and_preprocessing_are_frozen(self) -> None:
        configuration = self.documents["frozen_runtime_configuration.json"]
        self.assertEqual(
            configuration["checkpoint"]["main_checkpoint_sha256"],
            "a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5",
        )
        self.assertEqual(
            configuration["input_and_preprocessing"]["preprocessing_identity"],
            (
                "mineworld_gradio_step_video_preprocessing@1.0:"
                "036fa0b4899285e5499f88581f6e02426a25f732fcc26bd63c0f5b3863a9d9ab"
            ),
        )

    def test_hook_layers_and_tensor_configuration_are_frozen(self) -> None:
        configuration = self.documents["frozen_runtime_configuration.json"]
        self.assertEqual(
            configuration["extraction"]["hook"],
            "decoder_layer_output_residual_stream",
        )
        self.assertEqual(configuration["activation"]["layers"], list(range(20)))
        self.assertEqual(
            configuration["extraction"]["source_tensor_shape"],
            [1, 2776, 2048],
        )
        self.assertEqual(
            configuration["extraction"]["source_tensor_dtype"],
            "float16",
        )

    def test_every_no_overwrite_rule_is_preserved(self) -> None:
        no_overwrite = self.documents["frozen_runtime_configuration.json"][
            "no_overwrite"
        ]
        self.assertIs(no_overwrite["activation_contract"], True)
        self.assertIs(no_overwrite["extraction_contract"], True)
        self.assertIs(no_overwrite["model_input_contract"], True)
        self.assertIs(no_overwrite["rollout_contract"], True)
        self.assertIs(no_overwrite["chunk_and_index"]["no_overwrite"], True)

    def test_exact_c_signed_accepted_pilot_is_required(self) -> None:
        gate = self.documents["execution_gate.json"]
        self.assertIs(gate["c_accepted_pilot_required"], True)
        required = gate["required_person_c_pilot_decision"]
        self.assertEqual(required["owner"], "person_c")
        self.assertEqual(
            required["decision"],
            "ACCEPT_SINGLE_PILOT_FOR_SCIENTIFIC_USE",
        )

    def test_missing_c_pilot_identity_is_not_fabricated(self) -> None:
        acknowledgement = self.documents["runtime_acknowledgement.json"]
        self.assertIsNone(acknowledgement["accepted_person_c_decision_id"])
        self.assertIsNone(acknowledgement["selected_trajectory_id"])
        self.assertIsNone(acknowledgement["selected_git_object_sha256"])
        required = self.documents["execution_gate.json"][
            "required_person_c_pilot_decision"
        ]
        self.assertIsNone(required["owner_authority_commit"])
        self.assertIsNone(required["source_path"])

    def test_execution_gate_remains_closed(self) -> None:
        gate = self.documents["execution_gate.json"]
        self.assertIs(gate["execution_gate_open"], False)
        self.assertIs(gate["aggregate_authorization_present"], False)
        self.assertIs(gate["aggregate_authorization_required"], True)
        self.assertIs(gate["production_execution_started"], False)

    def test_scientific_and_registry_acceptance_are_separate(self) -> None:
        acknowledgement = self.documents["runtime_acknowledgement.json"]
        self.assertIs(acknowledgement["scientific_use_authorized"], False)
        self.assertIs(
            acknowledgement["registry_v2_acceptance_authorized"],
            False,
        )

    def test_no_production_or_scientific_output_was_created(self) -> None:
        receipt = self.documents["validation_receipt.json"]
        self.assertEqual(receipt["accepted_artifact_count"], 0)
        self.assertEqual(receipt["accepted_placeholder_count"], 0)
        self.assertIs(receipt["model_input_bytes_created"], False)
        self.assertIs(receipt["production_extraction_bytes_created"], False)
        self.assertIs(receipt["production_activation_bytes_created"], False)
        self.assertIs(receipt["production_rollout_bytes_created"], False)
        self.assertIs(receipt["scientific_execution_performed"], False)

    def test_base_package_policy_accepts(self) -> None:
        self.assertFalse(builder.validate_package(copy.deepcopy(self.documents)))

    def test_protected_true_mutations_fail_closed(self) -> None:
        cases = (
            ("person_a_phase6_authorized",),
            ("production_execution_started",),
            ("scientific_use_authorized",),
            ("registry_v2_acceptance_authorized",),
            ("self_authorizes_phase6",),
            ("u4_output_inspected",),
        )
        for (field,) in cases:
            with self.subTest(field=field):
                mutated = copy.deepcopy(self.documents)
                mutated["runtime_acknowledgement.json"][field] = True
                self.assertTrue(builder.validate_package(mutated))

    def test_builder_is_deterministic(self) -> None:
        first = builder.build_documents()
        second = builder.build_documents()
        self.assertEqual(
            {path: builder._json_bytes(document) for path, document in first.items()},
            {path: builder._json_bytes(document) for path, document in second.items()},
        )
        with tempfile.TemporaryDirectory() as directory:
            builder.write_documents(Path(directory))
            self.assertEqual(
                {path.name for path in Path(directory).glob("*.json")},
                set(builder.OUTPUT_PATHS),
            )

    def test_all_json_is_canonical(self) -> None:
        self.assertEqual(
            {path.name for path in EVIDENCE_ROOT.glob("*.json")},
            set(builder.OUTPUT_PATHS),
        )
        for path in EVIDENCE_ROOT.glob("*.json"):
            document = json.loads(path.read_bytes())
            self.assertEqual(path.read_bytes(), builder._json_bytes(document))

    def test_sha256_inventory_is_exact(self) -> None:
        inventory = self.documents["sha256_inventory.json"]
        expected = set(builder.OUTPUT_PATHS) - {"sha256_inventory.json"}
        self.assertEqual(set(inventory["files"]), expected)
        self.assertIs(inventory["inventory_excludes_self"], True)
        for path, digest in inventory["files"].items():
            self.assertEqual(
                hashlib.sha256((EVIDENCE_ROOT / path).read_bytes()).hexdigest(),
                digest,
            )


if __name__ == "__main__":
    unittest.main()
