from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from mineocclude.contracts.analysis_inputs import (
    AnalysisInputRejectionCode,
    validate_baseline_input,
)
from mineocclude.contracts.baseline_family_inputs import (
    BASELINE_FAMILY_CONTRACTS_V0_2,
    BASELINE_FAMILY_MANIFEST_SCHEMA_ID,
    BASELINE_INPUT_SCHEMA_VERSION_V0_2,
    FROZEN_BASELINE_FAMILY_IDS,
    FROZEN_DIRECT_INPUTS,
    FROZEN_PILOT_IDS,
    FROZEN_SOURCE_CONTEXTS,
    FROZEN_TARGET_IDENTITY_BINDINGS,
    PERSON_B_PREDICTION_RESERVATION,
    validate_eight_family_input_manifest,
)
from scripts.validate_person_b_step4_1_baseline_family_inputs_v0_2 import (
    canonical_json_bytes,
    validate_manifest_path,
    verify_artifact_reference_bytes,
)

ROOT = Path(__file__).resolve().parents[2]
STATUS_ROOT = (
    ROOT
    / "docs"
    / "status"
    / "person_b_phase4_step4_1_baseline_family_contract_v0_2"
)


def artifact_reference(marker: str) -> dict[str, object]:
    return {
        "byte_size": 100,
        "path": f"external/{marker}.json",
        "producer_role": "person_a",
        "sha256": marker * 64,
    }


def baseline_document(family_id: str) -> dict[str, object]:
    contract = BASELINE_FAMILY_CONTRACTS_V0_2[family_id]
    direct_inputs = copy.deepcopy(FROZEN_DIRECT_INPUTS)
    if family_id == "raw_pixel":
        direct_inputs["preprocessed_frame_manifest"] = artifact_reference("b")
    return {
        "accepted_pilot_ids": list(FROZEN_PILOT_IDS),
        "baseline_family": family_id,
        "baseline_id": f"{family_id}_v0_2",
        "baseline_input_schema_version": BASELINE_INPUT_SCHEMA_VERSION_V0_2,
        "config_hash": FROZEN_DIRECT_INPUTS["analysis_config"]["sha256"],
        "direct_inputs": direct_inputs,
        "feature_access": sorted(contract["feature_access"]),
        "fit_manifest_hash": "f" * 64,
        "fold_manifest_hash": FROZEN_DIRECT_INPUTS["fold_manifest"]["sha256"],
        "input_manifest_hash": "e" * 64,
        "legal_information": copy.deepcopy(contract["legal_information"]),
        "person_b_prediction_reservation": copy.deepcopy(
            PERSON_B_PREDICTION_RESERVATION
        ),
        "producer_role": "person_d",
        "random_split_used": False,
        "rows": [
            {
                "fit_id": f"{family_id}_fold_1",
                "fold_idx": 1,
                "model_frame_idx": 19,
                "prediction": 1.25,
                "prediction_scope": "out_of_fold",
                "trajectory_id": "layout_00_ep9403",
            }
        ],
        "schema_version": "1.0",
        "target_name": min(contract["target_names"]),
        "u4_output_inspected": False,
    }


def family_manifest() -> dict[str, object]:
    families = []
    for family_id in FROZEN_BASELINE_FAMILY_IDS:
        contract = BASELINE_FAMILY_CONTRACTS_V0_2[family_id]
        families.append(
            {
                "configuration": copy.deepcopy(contract["configuration"]),
                "definition": contract["definition"],
                "expected_output_type": contract["expected_output_type"],
                "family_id": family_id,
                "feature_access": sorted(contract["feature_access"]),
                "legal_information": copy.deepcopy(
                    contract["legal_information"]
                ),
                "source": copy.deepcopy(contract["source"]),
                "target_identity_bindings": {
                    target_name: copy.deepcopy(
                        FROZEN_TARGET_IDENTITY_BINDINGS[target_name]
                    )
                    for target_name in sorted(contract["target_names"])
                },
                "targets": sorted(contract["target_names"]),
            }
        )
    direct_inputs = copy.deepcopy(FROZEN_DIRECT_INPUTS)
    direct_inputs.update(
        {
            "preprocessed_frame_manifest": artifact_reference("b"),
        }
    )
    source_contexts = copy.deepcopy(FROZEN_SOURCE_CONTEXTS)
    return {
        "accepted_pilot_ids": list(FROZEN_PILOT_IDS),
        "baseline_families": families,
        "baseline_family_count": 8,
        "baseline_input_schema_version": BASELINE_INPUT_SCHEMA_VERSION_V0_2,
        "direct_inputs": direct_inputs,
        "person_b_prediction_reservation": copy.deepcopy(
            PERSON_B_PREDICTION_RESERVATION
        ),
        "person_d_execution_ready": True,
        "random_split_used": False,
        "schema_id": BASELINE_FAMILY_MANIFEST_SCHEMA_ID,
        "schema_version": "1.0",
        "source_contexts": source_contexts,
        "u4_output_inspected": False,
    }


class TestBaselineFamilyInputV02(unittest.TestCase):
    def test_committed_contract_records_exact_eight_and_fail_closed_status(
        self,
    ) -> None:
        contract = json.loads(
            (STATUS_ROOT / "baseline_family_contract.json").read_text(
                encoding="utf-8"
            )
        )
        ratification = json.loads(
            (STATUS_ROOT / "contract_ratification.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            [item["family_id"] for item in contract["baseline_families"]],
            list(FROZEN_BASELINE_FAMILY_IDS),
        )
        self.assertTrue(ratification["baseline_input_v0_2_contract_ratified"])
        self.assertFalse(ratification["person_d_execution_ready"])
        self.assertFalse(ratification["person_d_handoff_authorized"])

    def test_contract_package_and_schema_are_canonical_json(self) -> None:
        json_paths = [
            *STATUS_ROOT.glob("*.json"),
            ROOT
            / "schemas"
            / "analysis"
            / "person_b_baseline_input_v0_2.schema.json",
        ]
        for path in json_paths:
            with self.subTest(path=path.name):
                raw = path.read_bytes()
                document = json.loads(raw.decode("utf-8"))
                self.assertEqual(raw, canonical_json_bytes(document))

    def test_contract_package_inventory_matches_exact_bytes(self) -> None:
        inventory = json.loads(
            (STATUS_ROOT / "sha256_inventory.json").read_text(encoding="utf-8")
        )
        self.assertTrue(inventory["inventory_excludes_self"])
        for filename, expected_hash in inventory["files"].items():
            actual_hash = hashlib.sha256(
                (STATUS_ROOT / filename).read_bytes()
            ).hexdigest()
            self.assertEqual(actual_hash, expected_hash)

    def test_source_context_manifest_binds_exact_ten_capture_objects(self) -> None:
        manifest = json.loads(
            (STATUS_ROOT / "source_context_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["accepted_pilot_count"], 10)
        self.assertEqual(
            tuple(manifest["accepted_pilot_ids"]), FROZEN_PILOT_IDS
        )
        for item in manifest["source_contexts"]:
            reference = item["capture_package"]
            raw = subprocess.check_output(
                [
                    "git",
                    "show",
                    f"c6bff25b5ef4f5fdb0e1ef0ce0d22e3f8b5e4960:{reference['path']}",
                ],
                cwd=ROOT,
            )
            self.assertEqual(len(raw), reference["byte_size"])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), reference["sha256"])

    def test_v0_1_historical_last_seen_only_behavior_is_preserved(self) -> None:
        from tests.contracts.test_analysis_inputs import baseline_document as v1

        document = v1()
        self.assertTrue(validate_baseline_input(document).accepted)
        for family_id in FROZEN_BASELINE_FAMILY_IDS[1:]:
            with self.subTest(family_id=family_id):
                candidate = copy.deepcopy(document)
                candidate["baseline_family"] = family_id
                result = validate_baseline_input(candidate)
                self.assertFalse(result.accepted)
                self.assertIn(
                    AnalysisInputRejectionCode.UNSUPPORTED_BASELINE_FAMILY,
                    {item.code for item in result.rejections},
                )

    def test_v0_2_accepts_each_exact_frozen_family(self) -> None:
        expected = {("layout_00_ep9403", 19): 1}
        for family_id in FROZEN_BASELINE_FAMILY_IDS:
            with self.subTest(family_id=family_id):
                document = baseline_document(family_id)
                original = copy.deepcopy(document)
                result = validate_baseline_input(
                    document, expected_fold_by_frame=expected
                )
                self.assertTrue(result.accepted, result.rejections)
                self.assertEqual(document, original)

    def test_v0_2_rejects_unknown_family(self) -> None:
        document = baseline_document("last_seen")
        document["baseline_family"] = "lastseen"
        result = validate_baseline_input(document)
        self.assertFalse(result.accepted)
        self.assertIn(
            AnalysisInputRejectionCode.UNSUPPORTED_BASELINE_FAMILY,
            {item.code for item in result.rejections},
        )

    def test_v0_2_rejects_changed_target_and_fold_hashes(self) -> None:
        cases = (
            ("config_hash", "0" * 64),
            ("fold_manifest_hash", "0" * 64),
        )
        for field, value in cases:
            with self.subTest(field=field):
                document = baseline_document("last_seen")
                document[field] = value
                self.assertFalse(validate_baseline_input(document).accepted)
        document = baseline_document("last_seen")
        document["direct_inputs"]["oracle_target"]["sha256"] = "0" * 64
        self.assertFalse(validate_baseline_input(document).accepted)

    def test_unknown_contract_version_fails_closed(self) -> None:
        document = baseline_document("last_seen")
        document["baseline_input_schema_version"] = "person-b-baseline-input-v9"
        result = validate_baseline_input(document)
        self.assertFalse(result.accepted)
        self.assertIn(
            AnalysisInputRejectionCode.INVALID_SCHEMA_VERSION,
            {item.code for item in result.rejections},
        )

    def test_v0_2_rejects_unauthorized_pilot_and_random_split(self) -> None:
        document = baseline_document("last_seen")
        document["accepted_pilot_ids"] = [*FROZEN_PILOT_IDS, "other"]
        document["rows"][0]["trajectory_id"] = "other"
        document["random_split_used"] = True
        result = validate_baseline_input(document)
        codes = {item.code for item in result.rejections}
        self.assertFalse(result.accepted)
        self.assertIn(AnalysisInputRejectionCode.MANIFEST_MISMATCH, codes)
        self.assertIn(AnalysisInputRejectionCode.FOLD_MISMATCH, codes)
        self.assertIn(AnalysisInputRejectionCode.INVALID_IDENTITY, codes)

    def test_raw_pixel_requires_exact_preprocessed_frame_manifest(self) -> None:
        document = baseline_document("raw_pixel")
        del document["direct_inputs"]["preprocessed_frame_manifest"]
        result = validate_baseline_input(document)
        self.assertFalse(result.accepted)
        self.assertIn(
            AnalysisInputRejectionCode.MISSING_REQUIRED_FIELD,
            {item.code for item in result.rejections},
        )

    def test_b_predictions_are_not_a_person_d_direct_input(self) -> None:
        document = baseline_document("last_seen")
        document["direct_inputs"]["person_b_predictions"] = copy.deepcopy(
            PERSON_B_PREDICTION_RESERVATION
        )
        result = validate_baseline_input(document)
        self.assertFalse(result.accepted)
        self.assertIn(
            AnalysisInputRejectionCode.LEGAL_INFORMATION_VIOLATION,
            {item.code for item in result.rejections},
        )
        self.assertEqual(
            document["person_b_prediction_reservation"],
            PERSON_B_PREDICTION_RESERVATION,
        )

    def test_manifest_accepts_exact_eight_once(self) -> None:
        self.assertEqual(validate_eight_family_input_manifest(family_manifest()), ())

    def test_manifest_rejects_missing_or_duplicate_family(self) -> None:
        missing = family_manifest()
        missing["baseline_families"].pop()
        self.assertIn(
            "baseline_family_set_or_order_mismatch",
            validate_eight_family_input_manifest(missing),
        )

        duplicate = family_manifest()
        duplicate["baseline_families"][1] = copy.deepcopy(
            duplicate["baseline_families"][0]
        )
        self.assertIn(
            "duplicate_baseline_family",
            validate_eight_family_input_manifest(duplicate),
        )

    def test_manifest_rejects_source_context_or_direct_input_mismatch(self) -> None:
        document = family_manifest()
        document["source_contexts"][0]["trajectory_id"] = "other"
        document["direct_inputs"]["fold_manifest"]["sha256"] = "0" * 64
        errors = validate_eight_family_input_manifest(document)
        self.assertIn("source_context_pilot_binding_mismatch", errors)
        self.assertIn("fold_manifest:frozen_identity_mismatch", errors)

    def test_manifest_rejects_b_prediction_direct_input_and_u4_access(self) -> None:
        document = family_manifest()
        document["direct_inputs"]["person_b_prediction"] = copy.deepcopy(
            PERSON_B_PREDICTION_RESERVATION
        )
        document["u4_output_inspected"] = True
        errors = validate_eight_family_input_manifest(document)
        self.assertIn("person_b_predictions_used_as_direct_input", errors)
        self.assertIn("u4_access_not_forbidden", errors)

    def test_focused_validator_requires_canonical_json(self) -> None:
        document = family_manifest()
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "manifest.json"
            path.write_bytes(canonical_json_bytes(document))
            self.assertEqual(validate_manifest_path(path), ())
            path.write_text(json.dumps(document), encoding="utf-8")
            self.assertIn("noncanonical_json_bytes", validate_manifest_path(path))

    def test_artifact_byte_verifier_rejects_hash_and_size_mismatches(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = root / "artifact.bin"
            path.write_bytes(b"exact bytes")
            reference = {
                "byte_size": len(b"exact bytes"),
                "path": path.name,
                "sha256": hashlib.sha256(b"exact bytes").hexdigest(),
            }
            self.assertTrue(verify_artifact_reference_bytes(reference, root))
            reference["byte_size"] += 1
            self.assertFalse(verify_artifact_reference_bytes(reference, root))
            reference["byte_size"] -= 1
            reference["sha256"] = "0" * 64
            self.assertFalse(verify_artifact_reference_bytes(reference, root))

    def test_manifest_rejects_execution_when_required_frame_input_is_absent(
        self,
    ) -> None:
        document = family_manifest()
        del document["direct_inputs"]["preprocessed_frame_manifest"]
        self.assertIn(
            "preprocessed_frame_manifest:invalid_identity",
            validate_eight_family_input_manifest(document),
        )


if __name__ == "__main__":
    unittest.main()
