"""Focused tests for the non-scientific Person A production preflight."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BUILDER_PATH = (
    ROOT
    / "scripts"
    / "build_person_a_phase4_step4_1_production_handoff_preflight_v0_1.py"
)
EVIDENCE_ROOT = (
    ROOT
    / "docs"
    / "status"
    / "person_a_phase4_step4_1_production_handoff_preflight_v0_1"
)
spec = importlib.util.spec_from_file_location(
    "person_a_preflight_builder", BUILDER_PATH
)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load builder: {BUILDER_PATH}")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def _git(*arguments: str) -> bytes:
    return subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout


def _load_documents() -> dict[str, Any]:
    return {
        path.name: json.loads(path.read_bytes())
        for path in sorted(EVIDENCE_ROOT.glob("*.json"))
    }


def _policy_violations(documents: dict[str, Any]) -> tuple[str, ...]:
    return builder.validate_package_policy(documents)


class ProductionHandoffPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.documents = _load_documents()

    def test_01_exact_authorities_are_bound(self) -> None:
        builder.verify_repository_authority()
        observed = self.documents["authority_binding.json"]["authorities"]
        self.assertEqual(set(observed), set(builder.AUTHORITIES))
        for owner, expected in builder.AUTHORITIES.items():
            with self.subTest(owner=owner):
                self.assertEqual(
                    observed[owner]["source_authority_commit"],
                    expected["commit"],
                )
                self.assertEqual(observed[owner]["remote_ref"], expected["remote_ref"])

    def test_02_selected_inputs_match_exact_person_c_git_objects(self) -> None:
        selected = self.documents["selected_c_inputs.json"]
        self.assertEqual(selected["input_count"], 15)
        for row in selected["inputs"]:
            raw = _git(
                "show",
                f"{builder.AUTHORITIES['person_c']['commit']}:{row['source_path']}",
            )
            with self.subTest(trajectory_id=row["trajectory_id"]):
                self.assertEqual(row["sha256"], hashlib.sha256(raw).hexdigest())
                self.assertEqual(row["byte_size"], len(raw))
        for field, changed in (("sha256", "0" * 64), ("byte_size", 0)):
            mutated = copy.deepcopy(selected)
            mutated["inputs"][0][field] = changed
            with self.subTest(changed_field=field):
                self.assertTrue(builder.validate_selected_c_inputs(mutated))

    def test_03_selected_inputs_remain_pending_scientific_use(self) -> None:
        rows = self.documents["selected_c_inputs.json"]["inputs"]
        self.assertEqual(
            {row["scientific_use"] for row in rows},
            {"pending_cross_role_signoff"},
        )
        self.assertEqual(
            {row["registry_v2_accepted"] for row in rows},
            {False},
        )

    def test_04_layout_05_ep9422_remains_excluded(self) -> None:
        selected = self.documents["selected_c_inputs.json"]
        self.assertNotIn(
            builder.EXCLUDED_TRAJECTORY_ID,
            {row["trajectory_id"] for row in selected["inputs"]},
        )
        self.assertEqual(
            selected["excluded_input"]["classification"],
            "excluded_no_object_control",
        )

    def test_05_selected_input_set_mutations_fail_closed(self) -> None:
        original = self.documents["selected_c_inputs.json"]
        cases = {}
        missing = copy.deepcopy(original)
        missing["inputs"].pop()
        cases["missing"] = missing
        extra = copy.deepcopy(original)
        extra["inputs"].append(
            {
                **copy.deepcopy(extra["inputs"][0]),
                "trajectory_id": "layout_99_ep9999",
            }
        )
        cases["extra"] = extra
        duplicate = copy.deepcopy(original)
        duplicate["inputs"][-1] = copy.deepcopy(duplicate["inputs"][0])
        cases["duplicate"] = duplicate
        substituted = copy.deepcopy(original)
        substituted["inputs"][-1]["trajectory_id"] = builder.EXCLUDED_TRAJECTORY_ID
        cases["substituted"] = substituted
        for name, document in cases.items():
            with self.subTest(name=name):
                self.assertTrue(builder.validate_selected_c_inputs(document))

    def test_06_phase6_authorization_true_fails_closed(self) -> None:
        mutated = copy.deepcopy(self.documents)
        mutated["authority_binding.json"]["authorization"][
            "person_a_phase6_authorized"
        ] = True
        violations = _policy_violations(mutated)
        self.assertTrue(
            any("person_a_phase6_authorized" in item for item in violations)
        )

    def test_07_automatic_transition_true_fails_closed(self) -> None:
        mutated = copy.deepcopy(self.documents)
        mutated["authority_binding.json"]["authorization"][
            "automatic_phase6_transition_allowed"
        ] = True
        violations = _policy_violations(mutated)
        self.assertTrue(
            any("automatic_phase6_transition_allowed" in item for item in violations)
        )

    def test_08_runtime_execution_remains_unauthorized(self) -> None:
        authorization = self.documents["authority_binding.json"]["authorization"]
        self.assertIs(authorization["production_execution_performed"], False)
        self.assertIs(
            authorization["person_a_phase6_authorized"],
            False,
        )

    def test_09_scientific_use_remains_unauthorized(self) -> None:
        authorization = self.documents["authority_binding.json"]["authorization"]
        self.assertIs(authorization["scientific_execution_authorized"], False)
        self.assertIs(
            self.documents["validation_receipt.json"]["scientific_execution_performed"],
            False,
        )

    def test_10_registry_v2_acceptance_remains_unauthorized(self) -> None:
        authorization = self.documents["authority_binding.json"]["authorization"]
        self.assertIs(authorization["registry_v2_acceptance_authorized"], False)
        self.assertEqual(
            self.documents["registry_v2_trust_templates.json"]["accepted_record_count"],
            0,
        )

    def test_11_smoke_model_input_cannot_be_promoted(self) -> None:
        contract = self.documents["model_input_contract.json"]
        self.assertIn("smoke_model_input", contract["prohibited_promotions"])
        self.assertIs(contract["instantiated_output_artifact"], False)
        self.assertIs(
            contract["prohibited_promotion_records"][0]["promotion_allowed"],
            False,
        )

    def test_12_extraction_pilot_cannot_be_promoted(self) -> None:
        contract = self.documents["extraction_contract.json"]
        self.assertIn("extraction_pilot", contract["prohibited_promotions"])
        self.assertIs(contract["instantiated_output_artifact"], False)
        self.assertIs(
            contract["prohibited_promotion_records"][0]["promotion_allowed"],
            False,
        )

    def test_13_limited_activation_pilot_cannot_be_promoted(self) -> None:
        contract = self.documents["activation_contract.json"]
        self.assertIn(
            "limited_activation_pilot",
            contract["prohibited_promotions"],
        )
        record = contract["prohibited_promotion_records"][0]
        self.assertIs(record["promotion_allowed"], False)
        self.assertEqual(
            record["sha256"],
            builder.PROHIBITED_PROMOTIONS["limited_activation_pilot"]["sha256"],
        )

    def test_14_synthetic_activation_fixture_cannot_be_promoted(self) -> None:
        contract = self.documents["activation_contract.json"]
        self.assertIn(
            "synthetic_activation_fixture",
            contract["prohibited_promotions"],
        )
        self.assertIs(
            contract["prohibited_promotion_records"][1]["promotion_allowed"],
            False,
        )

    def test_15_certification_rollout_cannot_be_promoted(self) -> None:
        contract = self.documents["rollout_contract.json"]
        self.assertIn("certification_rollout", contract["prohibited_promotions"])
        self.assertIs(contract["instantiated_output_artifact"], False)
        self.assertIs(
            contract["prohibited_promotion_records"][0]["promotion_allowed"],
            False,
        )

    def test_16_four_production_contracts_are_defined(self) -> None:
        expected = {
            "model_input_contract.json": "model_input",
            "extraction_contract.json": "extraction",
            "activation_contract.json": "activation",
            "rollout_contract.json": "rollout",
        }
        for path, artifact_type in expected.items():
            with self.subTest(path=path):
                self.assertEqual(
                    self.documents[path]["artifact_type"],
                    artifact_type,
                )
                self.assertEqual(
                    self.documents[path]["status"],
                    "contract_only_not_executed",
                )

    def test_17_proposed_configuration_is_not_accepted_output(self) -> None:
        document = self.documents["immutable_runtime_configuration.json"]
        self.assertEqual(document["status"], builder.PROPOSED)
        self.assertEqual(document["acceptance_state"], "not_accepted")
        self.assertTrue(
            all(
                row["classification"] == builder.PROPOSED
                for row in document["configuration"]
            )
        )
        self.assertIs(
            document["configuration_identity_is_artifact_acceptance"],
            False,
        )

    def test_18_registry_v2_records_remain_templates_only(self) -> None:
        document = self.documents["registry_v2_trust_templates.json"]
        self.assertEqual(document["template_count"], 6)
        self.assertEqual(
            set(document["template_types"]),
            set(builder.REGISTRY_V2_TEMPLATE_TYPES),
        )
        for artifact_type, template in document["templates"].items():
            with self.subTest(artifact_type=artifact_type):
                self.assertEqual(
                    set(template),
                    set(builder.REGISTRY_V2_TEMPLATE_TYPES),
                )
                self.assertIsNone(
                    template["exact_artifact_authorization"]["artifact_id"]
                )
                self.assertIs(
                    template["exact_artifact_authorization"]["accepted"],
                    False,
                )
                self.assertIn("verified_authorization_record", template)
                self.assertIsNot(
                    template["verified_authorization_record"],
                    template["exact_artifact_authorization"],
                )

    def test_18a_verified_authorization_shape_matches_frozen_v2(self) -> None:
        document = self.documents["registry_v2_trust_templates.json"]
        binding = builder._frozen_registry_v2_binding()
        self.assertEqual(document["frozen_registry_v2_binding"], binding)
        field_sets = binding["field_sets"]
        for template in document["templates"].values():
            verified = template["verified_authorization_record"]
            trusted = verified["trusted_artifact_authorization"]
            self.assertEqual(
                set(trusted),
                set(field_sets["trusted_artifact_authorization"]),
            )
            self.assertEqual(
                set(trusted["authorization"]),
                set(field_sets["artifact_authorization"]),
            )
            self.assertEqual(
                set(trusted["authorization_record_verification"]),
                set(field_sets["authorization_record_verification"]),
            )
            self.assertEqual(
                set(verified["authorization_record"]),
                set(field_sets["authorization_record"]),
            )
            self.assertEqual(
                set(verified["authorization_receipt"]),
                set(field_sets["authorization_receipt"]),
            )

    def test_18b_verified_authorization_future_values_are_unset(self) -> None:
        document = self.documents["registry_v2_trust_templates.json"]
        for artifact_type, template in document["templates"].items():
            verified = template["verified_authorization_record"]
            trusted = verified["trusted_artifact_authorization"]
            for record in (
                trusted["authorization"],
                verified["authorization_record"],
            ):
                self.assertEqual(record["artifact_type"], artifact_type)
                self.assertEqual(record["owner_id"], "person_a")
                self.assertEqual(record["owner_status"], "pending")
                self.assertEqual(record["decision"], "pending")
            self.assertTrue(
                all(
                    value is None
                    for value in trusted["authorization_record_verification"].values()
                )
            )
            self.assertTrue(
                all(
                    value is None
                    for value in verified["authorization_record_bytes"].values()
                )
            )
            self.assertTrue(
                all(
                    value is None
                    for value in verified["authorization_receipt"].values()
                )
            )

    def test_18c_verified_template_is_not_accepted_or_verified(self) -> None:
        document = self.documents["registry_v2_trust_templates.json"]
        self.assertFalse(builder.validate_registry_v2_trust_templates(document))
        for template in document["templates"].values():
            context = template["verified_authorization_record"]["verification_context"]
            self.assertIs(context["accepted"], False)
            self.assertIs(context["verified"], False)
            self.assertIs(context["verification_result"], False)
            self.assertEqual(
                context["status"],
                "pending_future_authorization_verification",
            )

    def test_18d_true_verification_or_acceptance_fails_policy(self) -> None:
        original = self.documents["registry_v2_trust_templates.json"]
        verified_true = copy.deepcopy(original)
        verified_true["templates"]["activation"]["verified_authorization_record"][
            "verification_context"
        ]["verified"] = True
        verification_result_true = copy.deepcopy(original)
        verification_result_true["templates"]["activation"][
            "verified_authorization_record"
        ]["verification_context"]["verification_result"] = True
        accepted_true = copy.deepcopy(original)
        accepted_true["templates"]["activation"]["verified_authorization_record"][
            "verification_context"
        ]["accepted"] = True
        self.assertTrue(builder.validate_registry_v2_trust_templates(verified_true))
        self.assertTrue(
            builder.validate_registry_v2_trust_templates(verification_result_true)
        )
        self.assertTrue(builder.validate_registry_v2_trust_templates(accepted_true))

    def test_18e_removing_verified_template_fails_closed(self) -> None:
        mutated = copy.deepcopy(self.documents["registry_v2_trust_templates.json"])
        del mutated["templates"]["activation"]["verified_authorization_record"]
        self.assertTrue(builder.validate_registry_v2_trust_templates(mutated))

    def test_18f_renaming_verified_template_fails_closed(self) -> None:
        mutated = copy.deepcopy(self.documents["registry_v2_trust_templates.json"])
        template = mutated["templates"]["activation"]
        template["verified_authorization"] = template.pop(
            "verified_authorization_record"
        )
        self.assertTrue(builder.validate_registry_v2_trust_templates(mutated))

    def test_18g_substituting_exact_authorization_fails_closed(self) -> None:
        mutated = copy.deepcopy(self.documents["registry_v2_trust_templates.json"])
        template = mutated["templates"]["activation"]
        template["verified_authorization_record"] = copy.deepcopy(
            template["exact_artifact_authorization"]
        )
        self.assertTrue(builder.validate_registry_v2_trust_templates(mutated))

    def test_19_accepted_artifact_count_is_zero(self) -> None:
        receipt = self.documents["validation_receipt.json"]
        self.assertEqual(receipt["accepted_artifact_count"], 0)
        self.assertEqual(receipt["registry_v2_accepted_record_count"], 0)

    def test_20_accepted_placeholder_count_is_zero(self) -> None:
        self.assertEqual(
            self.documents["validation_receipt.json"]["accepted_placeholder_count"],
            0,
        )

    def test_21_no_output_artifact_bytes_were_generated(self) -> None:
        for path in (
            "model_input_contract.json",
            "extraction_contract.json",
            "activation_contract.json",
            "rollout_contract.json",
        ):
            with self.subTest(path=path):
                contract = self.documents[path]
                self.assertIsNone(contract["future_sha256"])
                self.assertIsNone(contract["future_byte_size"])
                self.assertIsNone(contract["future_artifact_id"])

    def test_22_no_model_load_occurred(self) -> None:
        self.assertEqual(
            self.documents["validation_receipt.json"]["model_load_count"],
            0,
        )

    def test_23_no_extraction_occurred(self) -> None:
        self.assertEqual(
            self.documents["validation_receipt.json"]["extraction_run_count"],
            0,
        )

    def test_24_no_activation_generation_occurred(self) -> None:
        self.assertEqual(
            self.documents["validation_receipt.json"]["activation_run_count"],
            0,
        )

    def test_25_no_rollout_occurred(self) -> None:
        self.assertEqual(
            self.documents["validation_receipt.json"]["rollout_run_count"],
            0,
        )

    def test_26_builder_output_is_deterministic(self) -> None:
        first = builder.build_documents()
        second = builder.build_documents()
        self.assertEqual(
            {path: builder._json_bytes(document) for path, document in first.items()},
            {path: builder._json_bytes(document) for path, document in second.items()},
        )
        with (
            tempfile.TemporaryDirectory() as first_root,
            tempfile.TemporaryDirectory() as second_root,
        ):
            builder.write_documents(Path(first_root))
            builder.write_documents(Path(second_root))
            for path in builder.ALL_OUTPUT_PATHS:
                with self.subTest(path=path):
                    self.assertEqual(
                        (Path(first_root) / path).read_bytes(),
                        (Path(second_root) / path).read_bytes(),
                    )

    def test_27_every_json_file_is_canonical(self) -> None:
        self.assertEqual(
            {path.name for path in EVIDENCE_ROOT.glob("*.json")},
            set(builder.ALL_OUTPUT_PATHS),
        )
        for path in sorted(EVIDENCE_ROOT.glob("*.json")):
            with self.subTest(path=path.name):
                self.assertEqual(
                    path.read_bytes(),
                    builder._json_bytes(json.loads(path.read_bytes())),
                )

    def test_28_inventory_hashes_match(self) -> None:
        inventory = self.documents["sha256_inventory.json"]
        self.assertEqual(
            set(inventory["files"]),
            set(builder.ALL_OUTPUT_PATHS) - {"sha256_inventory.json"},
        )
        for path, expected in inventory["files"].items():
            with self.subTest(path=path):
                self.assertEqual(
                    hashlib.sha256((EVIDENCE_ROOT / path).read_bytes()).hexdigest(),
                    expected,
                )

    def test_29_no_existing_tracked_file_changed(self) -> None:
        # The invariants worth protecting are that accepted evidence bytes are
        # never rewritten and that this package never reaches into another
        # role's files. Requiring a pristine worktree, or an exact match against
        # the untracked-file set, instead expires the moment this package is
        # committed or any later Person A work is in flight.
        evidence_paths = {
            str((EVIDENCE_ROOT / path).relative_to(ROOT)).replace("\\", "/")
            for path in builder.ALL_OUTPUT_PATHS
        }
        tracked = set(_git("ls-files").decode("utf-8").splitlines())
        untracked = set(
            _git("ls-files", "--others", "--exclude-standard")
            .decode("utf-8")
            .splitlines()
        )
        owned = evidence_paths | {
            str(BUILDER_PATH.relative_to(ROOT)).replace("\\", "/"),
            str(Path(__file__).resolve().relative_to(ROOT)).replace("\\", "/"),
        }
        for path in sorted(owned):
            with self.subTest(path=path):
                self.assertTrue(path in tracked or path in untracked, path)
        modified = set(
            _git("diff", "--name-only").decode("utf-8").splitlines()
        ) | set(_git("diff", "--cached", "--name-only").decode("utf-8").splitlines())
        self.assertEqual(sorted(modified & evidence_paths), [])
        for path in sorted(modified):
            with self.subTest(path=path):
                self.assertNotIn("person_b", path)
                self.assertNotIn("person_c", path)
                self.assertNotIn("person_d", path)
                self.assertNotIn("person_e", path)

    def test_30_no_project_integration_or_step4_1_closure_claim(self) -> None:
        authority = self.documents["authority_binding.json"]
        self.assertIs(authority["project_integration_claimed"], False)
        self.assertIs(authority["step4_1_complete"], False)
        self.assertFalse(_policy_violations(copy.deepcopy(self.documents)))

    def test_31_no_u4_output_was_inspected(self) -> None:
        self.assertIs(
            self.documents["authority_binding.json"]["u4_output_inspected"],
            False,
        )
        self.assertIs(
            self.documents["validation_receipt.json"]["u4_output_inspected"],
            False,
        )


if __name__ == "__main__":
    unittest.main()
