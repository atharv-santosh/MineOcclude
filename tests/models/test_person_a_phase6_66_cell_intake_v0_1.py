"""Focused CPU-only tests for Person A's 66-cell intake and acknowledgement.

These tests never load a model, never touch a GPU, and never extract anything.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BUILDER_PATH = ROOT / "scripts" / "build_person_a_phase6_66_cell_intake_v0_1.py"
EVIDENCE_ROOT = ROOT / "docs" / "status" / "person_a_phase6_66_cell_intake_v0_1"

spec = importlib.util.spec_from_file_location(
    "person_a_phase6_66_cell_intake_builder", BUILDER_PATH
)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load builder: {BUILDER_PATH}")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

EXPECTED_EPISODES = list(range(12601, 12667))


def _documents() -> dict[str, Any]:
    return {
        path.name: json.loads(path.read_bytes())
        for path in sorted(EVIDENCE_ROOT.glob("*.json"))
    }


class PersonA66CellIntakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.documents = _documents()

    # ------------------------------------------------------------------
    # Authority
    # ------------------------------------------------------------------
    def test_01_person_a_and_person_c_authorities_verify(self) -> None:
        self.assertEqual(builder.verify_authorities(), builder.A_STARTING_AUTHORITY)
        authorities = self.documents["authority_binding.json"]["authorities"]
        self.assertEqual(authorities["person_a"]["branch"], "role/person-a-model")
        self.assertEqual(
            authorities["person_c"]["source_authority_commit"],
            "a8bed8adf7e24ca7fe5b6b6afa3342da61434be3",
        )
        self.assertIs(authorities["person_c"]["branch_merged"], False)
        self.assertEqual(
            authorities["person_c"]["source_read_policy"], "exact_git_commit_object"
        )

    def test_02_person_c_source_records_match_exact_git_objects(self) -> None:
        records = self.documents["authority_binding.json"]["person_c_source_records"]
        self.assertTrue(records)
        for record in records:
            raw = builder._git_bytes(record["source_commit"], record["path"])
            self.assertEqual(record["sha256"], hashlib.sha256(raw).hexdigest())

    def test_03_pinned_person_a_production_files_are_unchanged(self) -> None:
        records = builder.verify_pinned_a_sources()
        bound = self.documents["authority_binding.json"]["person_a_pinned_source_files"]
        self.assertEqual(records, bound)
        for name, (path, expected) in builder.PINNED_A_SOURCE_FILES.items():
            observed = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            self.assertEqual(observed, expected, name)
            self.assertEqual(len(expected), 64)

    # ------------------------------------------------------------------
    # Person C intake
    # ------------------------------------------------------------------
    def test_04_c_accepted_manifest_sha256_matches_exactly(self) -> None:
        raw = builder._git_bytes(builder.C_COMMIT, builder.C_ACCEPTED_MANIFEST_PATH)
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(),
            "96ba43e15bc024aeaef7c519fa4ece0a4afe0bb0e877501dffaca44fee927ff7",
        )
        verification = self.documents["c_intake_verification.json"]
        self.assertEqual(
            verification["c_manifest_observed_sha256"],
            verification["c_manifest_declared_sha256"],
        )
        self.assertIs(verification["c_manifest_valid"], True)

    def test_05_c_universe_is_exactly_66_accepted_and_0_excluded(self) -> None:
        verification = self.documents["c_intake_verification.json"]
        self.assertEqual(verification["observed_accepted_count"], 66)
        self.assertEqual(verification["excluded_trajectory_count"], 0)
        self.assertEqual(verification["person_c_reported_accepted_count"], 66)
        self.assertEqual(verification["person_c_reported_excluded_count"], 0)
        self.assertEqual(verification["per_trajectory_bundle_count"], 66)

    def test_06_episode_set_is_exactly_ep12601_through_ep12666(self) -> None:
        raw = builder._git_bytes(builder.C_COMMIT, builder.C_ACCEPTED_MANIFEST_PATH)
        episodes = sorted(record["episode_id"] for record in json.loads(raw)["records"])
        self.assertEqual(episodes, EXPECTED_EPISODES)
        verification = self.documents["c_intake_verification.json"]
        self.assertIs(verification["episode_set_exact"], True)
        self.assertEqual(verification["episode_id_range_observed"], [12601, 12666])

    def test_07_no_duplicate_or_missing_trajectory_identities(self) -> None:
        verification = self.documents["c_intake_verification.json"]
        self.assertEqual(verification["duplicate_trajectory_ids"], [])
        self.assertEqual(verification["duplicate_planned_cell_ids"], [])
        self.assertEqual(verification["missing_episode_ids"], [])
        universe = self.documents["expected_model_frame_universe.json"]
        self.assertEqual(universe["duplicate_trajectory_ids"], [])
        self.assertEqual(universe["missing_trajectory_ids"], [])
        self.assertEqual(len(universe["per_trajectory"]), 66)

    def test_08_person_a_consumer_handoff_receipt_exists_and_binds_this_manifest(
        self,
    ) -> None:
        receipt = self.documents["c_intake_verification.json"][
            "person_a_consumer_receipt"
        ]
        self.assertIs(receipt["exists"], True)
        raw = builder._git_bytes(builder.C_COMMIT, receipt["path"])
        self.assertEqual(receipt["sha256"], hashlib.sha256(raw).hexdigest())
        document = json.loads(raw)
        self.assertEqual(document["consumer_role"], "person_a")
        self.assertEqual(document["expected_count_by_consumer"], 66)
        self.assertEqual(
            document["manifest_sha256"], builder.C_ACCEPTED_MANIFEST_SHA256
        )

    def test_09_all_c_side_paths_and_hashes_resolve(self) -> None:
        verification = self.documents["c_intake_verification.json"]
        self.assertEqual(verification["c_package_hashes_unresolved"], [])
        self.assertEqual(verification["c_metadata_references_unresolved"], [])
        self.assertGreater(verification["c_metadata_reference_count"], 0)
        self.assertEqual(verification["verification_violations"], [])

    # ------------------------------------------------------------------
    # Person A production authorities
    # ------------------------------------------------------------------
    def test_10_preprocessing_authority_is_exact_and_unchanged(self) -> None:
        preprocessing = self.documents["production_authorities.json"]["preprocessing"]
        self.assertEqual(
            preprocessing["implementation_path"],
            "src/mineocclude/models/_mineworld_adapter_wave2.py",
        )
        self.assertEqual(preprocessing["config_path"], "configs/experiments/mvp.yaml")
        self.assertEqual(len(preprocessing["implementation_sha256"]), 64)
        self.assertEqual(len(preprocessing["config_file_sha256"]), 64)
        self.assertEqual(preprocessing["source_resolution_hw"], [360, 640])
        self.assertEqual(preprocessing["model_facing_resolution_hw"], [224, 384])
        self.assertEqual(preprocessing["interpolation"], "cv2.INTER_LINEAR")
        self.assertIn("BGR2RGB", preprocessing["color_convention"])
        self.assertIs(
            preprocessing["unchanged_from_frozen_accepted_authority"], True
        )

    def test_11_live_config_identity_reproduces_the_frozen_identity(self) -> None:
        live = builder._live_config_identity()
        self.assertEqual(live["config_hash"], builder.FROZEN_CONFIG_HASH)
        self.assertEqual(live["preprocess_hash"], builder.FROZEN_PREPROCESS_HASH)
        self.assertEqual(live["model_hash"], builder.FROZEN_MODEL_HASH)
        self.assertEqual(live["config_file_sha256"], builder.A_CONFIG_SHA256)

    def test_12_action_converter_authority_is_exact(self) -> None:
        converter = self.documents["production_authorities.json"]["action_converter"]
        self.assertEqual(converter["action_vocab_offset"], 8192)
        self.assertEqual(len(converter["implementation_sha256"]), 64)
        self.assertEqual(
            converter["action_token_contract"]["tokens_returned_per_action"], 11
        )
        self.assertEqual(
            len(converter["action_token_contract"]["positional_roles"]), 11
        )
        self.assertIn("mineworld_action_compatibility@1.0:", converter[
            "converter_identity"
        ])
        self.assertEqual(
            converter["action_vocab_offset"],
            builder_action_vocab_offset(),
        )

    def test_13_frame_map_model_facing_key_is_trajectory_and_model_frame(self) -> None:
        frame_map = self.documents["production_authorities.json"]["frame_map"]
        self.assertEqual(
            frame_map["authoritative_model_facing_key"],
            ["trajectory_id", "model_frame_idx"],
        )
        self.assertEqual(len(frame_map["schema_sha256"]), 64)
        self.assertIn("keys define identity", frame_map["identity_rule"])
        for field in (
            "episode_id",
            "layout_id",
            "server_tick",
            "render_frame_idx",
            "action_idx",
            "source_frame",
            "raw_action",
            "normalized_action",
            "authoritative_state",
            "visibility",
            "condition_identity",
        ):
            self.assertIn(field, frame_map["traceability"])

    def test_14_frame_map_key_matches_the_live_capture_contract(self) -> None:
        from mineocclude.contracts import trajectory as contract

        frame_map = self.documents["production_authorities.json"]["frame_map"]
        self.assertEqual(list(contract.CAPTURE_KEY), frame_map["capture_key"])
        self.assertEqual(
            contract.TRAJECTORY_SCHEMA_VERSION, frame_map["schema_version"]
        )
        for field in frame_map["authoritative_model_facing_key"]:
            self.assertIn(field, contract.CAPTURE_KEY)
        self.assertIn("model_frame_idx", contract.INDEX_FIELDS)

    def test_15_model_checkpoint_vae_and_hook_authority_is_recorded(self) -> None:
        authorities = self.documents["production_authorities.json"]
        model = authorities["model_and_checkpoint"]
        hooks = authorities["extraction_hooks"]
        token_map = authorities["frame_token_map"]
        storage = authorities["activation_storage"]
        self.assertEqual(model["model_identity"], "mineworld-700m")
        self.assertEqual(len(model["checkpoint_sha256"]), 64)
        self.assertEqual(len(model["vae_checkpoint_sha256"]), 64)
        self.assertEqual(model["decoder_layer_count"], 20)
        self.assertEqual(hooks["hook_sites"], ["decoder_layer_output_residual_stream"])
        self.assertEqual(hooks["layer_indices"], list(range(20)))
        self.assertEqual(
            token_map["expected_visual_token_cardinality_per_frame"], 336
        )
        self.assertEqual(len(token_map["sha256"]), 64)
        self.assertEqual(
            storage["activation_index_format_version"], "person-a-activation-index-v2"
        )
        self.assertEqual(
            storage["activation_index_key"],
            ["trajectory_id", "model_frame_idx", "layer_idx", "hook_site"],
        )

    def test_16_hook_and_token_authority_matches_live_code(self) -> None:
        from mineocclude.activations import hooks as hook_module
        from mineocclude.activations import store_v2
        from mineocclude.contracts import activation as activation_module

        authorities = self.documents["production_authorities.json"]
        self.assertEqual(
            hook_module.CONCEPTUAL_HOOK_SITE,
            authorities["extraction_hooks"]["hook_sites"][0],
        )
        token_map = authorities["frame_token_map"]
        self.assertEqual(
            activation_module.VISUAL_TOKENS_PER_FRAME,
            token_map["expected_visual_token_cardinality_per_frame"],
        )
        self.assertEqual(
            activation_module.TOKENS_PER_FRAME_ACTION_PAIR,
            token_map["tokens_per_frame_action_pair"],
        )
        self.assertEqual(
            activation_module.MAX_MODEL_FRAMES,
            token_map["max_model_frames_per_context"],
        )
        self.assertEqual(
            store_v2.ACTIVATION_INDEX_V2_FORMAT_VERSION,
            authorities["activation_storage"]["activation_index_format_version"],
        )

    def test_17_activation_dtype_disagreement_is_reported_not_silently_resolved(
        self,
    ) -> None:
        storage = self.documents["production_authorities.json"]["activation_storage"]
        self.assertEqual(storage["hooked_source_tensor_dtype"], "float16")
        self.assertIs(storage["stored_dtype_reconciliation_required"], True)
        self.assertNotEqual(
            storage["frozen_config_extraction_stored_dtype"],
            storage["pooled_output_dtype"],
        )
        acknowledgement = self.documents["person_a_owner_acknowledgement.json"]
        self.assertIn(
            "activation_stored_dtype_authorities_disagree",
            acknowledgement["extraction_blockers"],
        )

    # ------------------------------------------------------------------
    # Expected model-frame universe
    # ------------------------------------------------------------------
    def test_18_expected_universe_is_derived_from_c_metadata_only(self) -> None:
        universe = self.documents["expected_model_frame_universe.json"]
        self.assertEqual(universe["expected_trajectory_count"], 66)
        self.assertEqual(universe["key"], ["trajectory_id", "model_frame_idx"])
        total = 0
        for trajectory_id, entry in universe["per_trajectory"].items():
            episode_id = int(trajectory_id.split("ep")[1])
            raw = builder._git_bytes(
                builder.C_COMMIT,
                f"{builder.C_PACKAGE_ROOT}/per_trajectory/ep{episode_id}.json",
            )
            counts = json.loads(raw)["qa_summary"]["cardinality_counts"]
            self.assertEqual(entry["expected_model_frame_count"], counts["frame_count"])
            self.assertIs(entry["stream_cardinalities_aligned"], True)
            total += entry["expected_model_frame_count"]
        self.assertEqual(universe["expected_model_frame_key_count"], total)
        self.assertEqual(universe["stream_cardinality_misaligned_trajectory_ids"], [])

    def test_19_expected_activation_cardinality_and_chunk_plan_are_consistent(
        self,
    ) -> None:
        universe = self.documents["expected_model_frame_universe.json"]
        frames = universe["expected_model_frame_key_count"]
        layers = len(universe["layer_indices"])
        self.assertEqual(layers, 20)
        self.assertEqual(universe["expected_activation_row_count_total"], frames * layers)
        self.assertEqual(universe["expected_activation_rows_per_layer"], frames)
        self.assertEqual(universe["expected_chunk_count_total"], 66 * layers)
        self.assertEqual(
            universe["expected_chunk_plan"]["chunks_per_trajectory"], layers
        )
        self.assertIs(universe["expected_chunk_plan"]["no_overwrite"], True)
        for entry in universe["per_trajectory"].values():
            self.assertEqual(
                entry["expected_activation_row_count"],
                entry["expected_model_frame_count"] * layers,
            )
            self.assertEqual(entry["expected_chunk_count"], layers)

    def test_20_frame_maps_are_not_claimed_to_be_materialized(self) -> None:
        universe = self.documents["expected_model_frame_universe.json"]
        self.assertIs(universe["real_frame_maps_materialized"], False)
        self.assertIs(universe["expected_model_frame_key_universe_enumerated"], False)
        self.assertIs(universe["derivation_is_contract_derived_not_materialized"], True)
        # Counts only: no entry may enumerate individual frame identities.
        for trajectory_id, entry in universe["per_trajectory"].items():
            for name, value in entry.items():
                self.assertNotIsInstance(value, list, f"{trajectory_id}.{name}")
                self.assertNotIsInstance(value, dict, f"{trajectory_id}.{name}")

    def test_21_previously_accepted_cells_reconcile_with_the_new_c_universe(
        self,
    ) -> None:
        queue = json.loads(
            (
                ROOT
                / "docs"
                / "status"
                / "person_a_phase7_mvp_v0_1"
                / "step_7_5_queue_status.json"
            ).read_bytes()
        )
        universe = self.documents["expected_model_frame_universe.json"]
        self.assertTrue(queue["items"])
        for item in queue["items"]:
            entry = universe["per_trajectory"][item["trajectory_id"]]
            self.assertEqual(entry["expected_model_frame_count"], item["frame_count"])
            self.assertEqual(
                entry["expected_activation_row_count"],
                item["expected_activation_row_count"],
            )
            self.assertEqual(entry["expected_chunk_count"], item["expected_chunk_count"])

    # ------------------------------------------------------------------
    # Byte accessibility
    # ------------------------------------------------------------------
    def test_22_byte_source_comes_only_from_person_c_handoff_references(self) -> None:
        receipt = self.documents["byte_accessibility_receipt.json"]
        self.assertIn("MineOcclude-Runtime", receipt["byte_source"])
        self.assertIn(builder.C_COMMIT, receipt["byte_source_reference_origin"])
        self.assertIs(receipt["durable_uri_assigned"], False)
        self.assertEqual(receipt["durable_uris_declared_by_person_c"], [])
        self.assertNotIn("s3://", json.dumps(receipt))
        self.assertEqual(len(receipt["per_trajectory"]), 66)
        for trajectory_id, entry in receipt["per_trajectory"].items():
            self.assertIn(trajectory_id.split("ep")[1], entry["runtime_client_path"])
            self.assertIsNone(entry["durable_uri"])
            self.assertIsNone(entry["s3_uri"])

    def test_23_byte_counts_partition_the_66_cell_universe(self) -> None:
        receipt = self.documents["byte_accessibility_receipt.json"]
        total = (
            receipt["trajectory_count_available_on_local_host"]
            + receipt["trajectory_count_unavailable_on_local_host"]
        )
        self.assertEqual(total, 66)
        self.assertLessEqual(
            receipt["trajectory_count_hash_verified_on_local_host"],
            receipt["trajectory_count_available_on_local_host"],
        )
        self.assertEqual(receipt["scanned_paths_hash_mismatch"], [])

    def test_24_approved_execution_environment_byte_access_is_not_claimed(self) -> None:
        receipt = self.documents["byte_accessibility_receipt.json"]
        self.assertEqual(
            receipt["approved_execution_environment"], "aws_sagemaker_linux_gpu"
        )
        self.assertEqual(receipt["local_host_role"], "preparation_only")
        self.assertIs(
            receipt["bytes_accessible_from_approved_execution_environment"], False
        )
        self.assertIs(receipt["bytes_committed_to_git"], False)
        self.assertTrue(receipt["external_transfer_blocker"])

    # ------------------------------------------------------------------
    # Owner acknowledgement
    # ------------------------------------------------------------------
    def test_25_acknowledgement_carries_every_required_binding(self) -> None:
        acknowledgement = self.documents["person_a_owner_acknowledgement.json"]
        self.assertEqual(acknowledgement["owner"], "person_a")
        self.assertEqual(acknowledgement["person_a_branch"], "role/person-a-model")
        self.assertEqual(
            acknowledgement["person_a_commit"], builder.A_STARTING_AUTHORITY
        )
        person_c = acknowledgement["person_c"]
        self.assertEqual(person_c["commit"], builder.C_COMMIT)
        self.assertEqual(
            person_c["manifest_path"], builder.C_ACCEPTED_MANIFEST_PATH
        )
        self.assertEqual(
            person_c["manifest_sha256"], builder.C_ACCEPTED_MANIFEST_SHA256
        )
        self.assertEqual(person_c["accepted_trajectory_count"], 66)
        self.assertEqual(person_c["excluded_trajectory_count"], 0)
        bound = acknowledgement["production_authorities"]
        for field in (
            "preprocessing_implementation_path",
            "preprocessing_implementation_sha256",
            "action_converter_path",
            "action_converter_sha256",
            "frame_map_schema_path",
            "frame_map_schema_version",
            "frame_map_schema_sha256",
            "model_identity",
            "checkpoint_sha256",
            "vae_checkpoint_sha256",
            "frame_token_map_sha256",
            "hook_sites",
            "layer_indices",
        ):
            self.assertTrue(bound[field], field)

    def test_26_readiness_fields_are_separate_and_extraction_is_not_ready(self) -> None:
        acknowledgement = self.documents["person_a_owner_acknowledgement.json"]
        self.assertIs(acknowledgement["person_a_66_input_contract_ready"], True)
        self.assertIs(acknowledgement["person_a_66_byte_access_ready"], False)
        self.assertIs(acknowledgement["person_a_66_extraction_ready"], False)
        self.assertIs(acknowledgement["person_a_phase6_acknowledgement_ready"], True)
        self.assertIs(acknowledgement["aggregate_phase6_runtime_authorized"], False)
        self.assertTrue(acknowledgement["extraction_blockers"])

    def test_27_acknowledgement_never_claims_a_66_cell_activation_index(self) -> None:
        acknowledgement = self.documents["person_a_owner_acknowledgement.json"]
        self.assertIs(acknowledgement["person_a_66_activation_index_exists"], False)
        self.assertIs(acknowledgement["production_activation_bytes_created"], False)
        self.assertIs(acknowledgement["production_extraction_bytes_created"], False)
        self.assertIs(acknowledgement["gpu_extraction_started"], False)
        self.assertIs(acknowledgement["model_loaded"], False)
        self.assertIs(
            acknowledgement["expected_model_frame_universe"][
                "real_frame_maps_materialized"
            ],
            False,
        )

    def test_28_phase6_is_never_authorized_unilaterally(self) -> None:
        for name, document in self.documents.items():
            violations = builder._protected_false_violations(document, name)
            self.assertEqual(violations, [], name)
        acknowledgement = self.documents["person_a_owner_acknowledgement.json"]
        self.assertIs(acknowledgement["self_authorizes_phase6"], False)
        self.assertIs(acknowledgement["automatic_phase6_transition_allowed"], False)
        self.assertIs(acknowledgement["person_a_phase6_authorized"], False)
        self.assertIs(acknowledgement["registry_v2_acceptance_authorized"], False)

    def test_29_acknowledgement_is_immutable_and_changes_no_science(self) -> None:
        acknowledgement = self.documents["person_a_owner_acknowledgement.json"]
        self.assertIs(acknowledgement["immutability"]["no_overwrite"], True)
        self.assertTrue(acknowledgement["immutability"]["supersession_rule"])
        self.assertIs(
            acknowledgement["scientific_settings_changed_by_this_package"], False
        )

    # ------------------------------------------------------------------
    # Package integrity
    # ------------------------------------------------------------------
    def test_30_committed_inventory_matches_the_committed_bytes(self) -> None:
        inventory = self.documents["sha256_inventory.json"]
        self.assertIs(inventory["inventory_excludes_self"], True)
        self.assertEqual(inventory["file_count"], len(builder.OUTPUT_PATHS))
        self.assertEqual(
            sorted(inventory["files"]),
            sorted(set(builder.OUTPUT_PATHS) - {"sha256_inventory.json"}),
        )
        for name, expected in inventory["files"].items():
            raw = (EVIDENCE_ROOT / name).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), expected, name)

    def test_31_package_path_inventory_is_exact(self) -> None:
        present = sorted(path.name for path in EVIDENCE_ROOT.glob("*"))
        self.assertEqual(present, sorted(builder.OUTPUT_PATHS))

    def test_32_builder_output_is_deterministic_and_matches_the_committed_package(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "package"
            builder.write_documents(output, scan_bytes=False)
            first = {
                path.name: path.read_bytes() for path in sorted(output.glob("*.json"))
            }
            for path in output.glob("*.json"):
                path.unlink()
            builder.write_documents(output, scan_bytes=False)
            second = {
                path.name: path.read_bytes() for path in sorted(output.glob("*.json"))
            }
        self.assertEqual(first, second)
        # Every document except the byte scan is byte-identical to the commit.
        scan_scoped = {
            "byte_accessibility_receipt.json",
            "person_a_owner_acknowledgement.json",
            "validation_receipt.json",
            "sha256_inventory.json",
        }
        for name, payload in first.items():
            if name in scan_scoped:
                continue
            self.assertEqual(
                payload, (EVIDENCE_ROOT / name).read_bytes(), name
            )

    def test_33_validation_receipt_agrees_with_the_package(self) -> None:
        receipt = self.documents["validation_receipt.json"]
        acknowledgement = self.documents["person_a_owner_acknowledgement.json"]
        self.assertIs(receipt["c_commit_verified"], True)
        self.assertIs(receipt["c_manifest_sha256_verified"], True)
        self.assertIs(receipt["c_package_hashes_all_resolve"], True)
        self.assertIs(receipt["c_metadata_references_all_resolve"], True)
        self.assertIs(receipt["episode_set_exact_12601_12666"], True)
        self.assertIs(receipt["duplicate_or_missing_trajectory_identities"], False)
        self.assertIs(receipt["person_a_consumer_receipt_present"], True)
        self.assertIs(receipt["person_a_pinned_authorities_unchanged"], True)
        self.assertEqual(receipt["verification_violations"], [])
        for field in (
            "person_a_66_byte_access_ready",
            "person_a_66_extraction_ready",
            "person_a_66_input_contract_ready",
            "person_a_phase6_acknowledgement_ready",
        ):
            self.assertEqual(receipt["readiness"][field], acknowledgement[field])

    def test_34_package_validation_rejects_a_fabricated_activation_index_claim(
        self,
    ) -> None:
        documents = {name: json.loads(json.dumps(value)) for name, value in (
            self.documents.items()
        )}
        documents["person_a_owner_acknowledgement.json"][
            "person_a_66_activation_index_exists"
        ] = True
        self.assertTrue(builder.validate_package(documents))

    def test_35_package_validation_rejects_a_fabricated_key_enumeration_claim(
        self,
    ) -> None:
        documents = {name: json.loads(json.dumps(value)) for name, value in (
            self.documents.items()
        )}
        documents["expected_model_frame_universe.json"][
            "expected_model_frame_key_universe_enumerated"
        ] = True
        self.assertTrue(builder.validate_package(documents))


def builder_action_vocab_offset() -> int:
    """Read the live pinned action vocabulary offset from production code."""

    from mineocclude.models import _mineworld_adapter_wave2 as adapter

    return adapter.ACTION_VOCABULARY_OFFSET


if __name__ == "__main__":
    unittest.main()
