"""Focused CPU-only tests for Person A's 66-cell successor authority.

These tests never load MineWorld weights, never touch a GPU, and never generate
activations.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import unittest
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BUILDER_PATH = ROOT / "scripts" / "build_person_a_66_cell_successor_authority_v0_1.py"
STATUS_ROOT = ROOT / "docs" / "status" / "person_a_66_cell_successor_authority_v0_1"

EXPECTED_TRAJECTORIES = 66
EXPECTED_MODEL_FRAMES = 2468
LAYER_COUNT = 20
EXPECTED_ROWS = EXPECTED_MODEL_FRAMES * LAYER_COUNT
EXPECTED_CHUNKS = EXPECTED_TRAJECTORIES * LAYER_COUNT

B_COMMIT = "25e09cb605699cdcb00dec1fbb1726977bec55e0"
C_COMMIT = "e908ead4a7ff5ab3ae310bb846969a7859fdb26b"
C_MANIFEST_SHA256 = (
    "96ba43e15bc024aeaef7c519fa4ece0a4afe0bb0e877501dffaca44fee927ff7"
)

_spec = importlib.util.spec_from_file_location(
    "person_a_66_cell_successor_authority_builder", BUILDER_PATH
)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"Unable to load builder: {BUILDER_PATH}")
builder = importlib.util.module_from_spec(_spec)
sys.modules["person_a_66_cell_successor_authority_builder"] = builder
_spec.loader.exec_module(builder)


def _json(name: str) -> Any:
    return json.loads((STATUS_ROOT / name).read_bytes())


class PersonA66CellSuccessorAuthorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.binding = _json("authority_binding.json")
        cls.authority = _json("model_preprocess_authority.json")
        cls.config = _json("successor_extraction_config.json")
        cls.queue = _json("successor_extraction_queue_state.json")
        cls.ack = _json("successor_owner_acknowledgement.json")
        cls.handoff = _json("a_to_d_frame_handoff.json")
        cls.transport = _json("byte_transport_preflight.json")
        cls.preconditions = _json("phase6_precondition_receipt.json")
        cls.validation = _json("validation_receipt.json")
        cls.inventory = _json("sha256_inventory.json")

    # ------------------------------------------------------------------
    # Authority intake
    # ------------------------------------------------------------------
    def test_01_authorities_verify_as_exact_git_objects(self) -> None:
        self.assertEqual(builder.verify_authorities(), builder.A_STARTING_AUTHORITY)
        authorities = self.binding["authorities"]
        self.assertEqual(authorities["person_b"]["source_authority_commit"], B_COMMIT)
        self.assertEqual(authorities["person_c"]["source_authority_commit"], C_COMMIT)
        for role in ("person_b", "person_c", "person_d", "person_e"):
            with self.subTest(role=role):
                self.assertEqual(
                    authorities[role]["source_read_policy"], "exact_git_commit_object"
                )

    def test_02_every_bound_foreign_record_matches_its_git_object(self) -> None:
        records = (
            self.binding["person_b_source_records"]
            + self.binding["person_c_source_records"]
        )
        self.assertTrue(records)
        for record in records:
            with self.subTest(path=record["path"]):
                raw = builder._git_bytes(record["source_commit"], record["path"])
                self.assertEqual(record["sha256"], hashlib.sha256(raw).hexdigest())
                self.assertEqual(record["byte_size"], len(raw))

    def test_03_b_package_is_internally_consistent(self) -> None:
        result = builder.verify_b_inventory()
        self.assertEqual(result["mismatched_paths"], [])
        self.assertEqual(result["verified_file_count"], result["declared_file_count"])
        self.assertEqual(
            self.binding["person_b_package_inventory_verification"], result
        )

    def test_04_supplied_hashes_were_recomputed_not_trusted(self) -> None:
        findings = builder.verify_supplied_hashes()
        self.assertEqual(self.binding["supplied_hash_verification"]["findings"], findings)
        self.assertIs(
            self.binding["supplied_hash_verification"]["all_supplied_hashes_matched"],
            False,
        )
        self.assertEqual(
            self.binding["supplied_hash_verification"]["rejected_count"], 2
        )
        for finding in findings:
            with self.subTest(path=finding["path"]):
                self.assertIs(finding["value_accepted_from_conversation"], False)
                actual = hashlib.sha256(
                    builder._git_bytes(B_COMMIT, finding["path"])
                ).hexdigest()
                self.assertEqual(finding["bound_value"], actual)
                self.assertIs(finding["producer_inventory_confirms_bound_value"], True)
                if not finding["matches"]:
                    self.assertNotEqual(finding["supplied_value"], actual)
                    self.assertEqual(finding["common_prefix_hex_characters"], 16)

    def test_05_c_strict_visibility_authority_is_bound(self) -> None:
        inputs = self.config["inputs"]
        self.assertEqual(inputs["person_c_strict_visibility_commit"], C_COMMIT)
        for path, digest in (
            (
                inputs["person_c_visibility_join_path"],
                inputs["person_c_visibility_join_sha256"],
            ),
            (
                inputs["person_c_event_table_path"],
                inputs["person_c_event_table_sha256"],
            ),
        ):
            with self.subTest(path=path):
                raw = builder._git_bytes(C_COMMIT, path)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), digest)
        self.assertEqual(
            inputs["person_c_accepted_manifest_sha256"], C_MANIFEST_SHA256
        )

    def test_06_b_fold_and_oracle_bindings_resolve(self) -> None:
        inputs = self.config["inputs"]
        for path, digest in (
            (inputs["person_b_fold_manifest_path"], inputs["person_b_fold_manifest_sha256"]),
            (
                inputs["person_b_oracle_target_manifest_path"],
                inputs["person_b_oracle_target_manifest_sha256"],
            ),
            (
                inputs["person_b_row_universe_path"],
                inputs["person_b_row_universe_sha256"],
            ),
        ):
            with self.subTest(path=path):
                raw = builder._git_bytes(B_COMMIT, path)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), digest)
        fold = json.loads(
            builder._git_bytes(B_COMMIT, inputs["person_b_fold_manifest_path"])
        )
        self.assertEqual(fold["model_frame_key_count"], EXPECTED_MODEL_FRAMES)
        self.assertEqual(
            fold["person_a_frame_map_package_sha256"],
            builder.A_FRAME_MAP_PACKAGE_SHA256,
        )

    # ------------------------------------------------------------------
    # Model / preprocess authority
    # ------------------------------------------------------------------
    def test_07_model_hash_equals_checkpoint_and_is_contract_bound(self) -> None:
        model = self.authority["model"]
        self.assertEqual(model["model_hash"], model["checkpoint_sha256"])
        self.assertIs(self.authority["model_hash_equals_checkpoint_sha256"], True)
        evidence = self.authority["model_hash_equality_contract"]["evidence"]
        self.assertTrue(evidence)
        for entry in evidence:
            with self.subTest(path=entry["path"]):
                self.assertEqual(
                    hashlib.sha256(
                        builder.repository_bytes(entry["path"])
                    ).hexdigest(),
                    entry["sha256"],
                )
                self.assertIn("model_hash", builder.repository_bytes(
                    entry["path"]
                ).decode("utf-8"))

    def test_08_preprocess_hash_and_implementation_hash_are_distinct(self) -> None:
        preprocessing = self.authority["preprocessing"]
        self.assertNotEqual(
            preprocessing["preprocess_hash"],
            preprocessing["preprocessing_implementation_sha256"],
        )
        self.assertNotEqual(
            preprocessing["preprocess_hash"], self.authority["model"]["model_hash"]
        )
        distinct = self.authority["distinct_quantities"]
        self.assertIs(distinct["collapsed_in_this_package"], False)
        self.assertIs(distinct["preprocess_hash_is_the_config_block_digest"], True)
        self.assertIs(
            distinct["preprocessing_implementation_sha256_is_a_file_digest"], True
        )

    def test_09_preprocess_hash_reproduces_from_the_frozen_config(self) -> None:
        from mineocclude.experiments.mvp_config import load_mvp_config

        identity = load_mvp_config(ROOT / builder.A_CONFIG_PATH).identity()
        preprocessing = self.authority["preprocessing"]
        self.assertEqual(identity["preprocess_hash"], preprocessing["preprocess_hash"])
        self.assertEqual(identity["config_hash"], preprocessing["config_hash"])
        self.assertEqual(
            identity["model_hash"], self.authority["model"]["model_hash"]
        )

    def test_10_implementation_path_is_the_underscore_path_that_exists(self) -> None:
        resolved = self.authority["resolved_implementation_path"]
        self.assertEqual(
            resolved["resolved_path"], "src/mineocclude/models/_mineworld_adapter_wave2.py"
        )
        self.assertIs(resolved["leading_underscore"], True)
        self.assertIs(resolved["absent_alias_path_exists"], False)
        self.assertIs(resolved["value_accepted_from_conversation"], False)
        self.assertTrue((ROOT / resolved["resolved_path"]).is_file())
        self.assertFalse((ROOT / resolved["absent_alias_path"]).exists())
        tracked = set(
            builder._git_text(
                "ls-tree", "-r", "--name-only", "HEAD", "--", "src/mineocclude/models"
            ).splitlines()
        )
        self.assertIn(resolved["resolved_path"], tracked)
        self.assertNotIn(resolved["absent_alias_path"], tracked)

    def test_11_action_converter_authority_is_recorded(self) -> None:
        converter = self.authority["action_converter"]
        self.assertEqual(converter["action_vocab_offset"], 8192)
        self.assertEqual(
            hashlib.sha256(
                builder.repository_bytes(converter["path"])
            ).hexdigest(),
            converter["sha256"],
        )
        self.assertIs(converter["same_file_as_preprocessing_implementation"], True)

    def test_12_person_b_identity_resolution_agrees_with_person_a(self) -> None:
        resolution = json.loads(
            builder._git_bytes(
                B_COMMIT, f"{builder.B_ROOT}/person_a_identity_resolution.json"
            )
        )
        preprocessing = self.authority["preprocessing"]
        self.assertEqual(
            resolution["preprocess_hash"], preprocessing["preprocess_hash"]
        )
        self.assertEqual(
            resolution["preprocessing_implementation_sha256"],
            preprocessing["preprocessing_implementation_sha256"],
        )
        self.assertEqual(
            resolution["preprocessing_implementation_path"],
            preprocessing["preprocessing_implementation_path"],
        )
        self.assertEqual(
            resolution["model_hash"], self.authority["model"]["model_hash"]
        )
        self.assertIs(
            resolution["preprocessing_implementation_digest_is_not_preprocess_hash"],
            True,
        )

    # ------------------------------------------------------------------
    # Successor float32 config and run identity
    # ------------------------------------------------------------------
    def test_13_successor_contract_is_float32_with_float64_analysis(self) -> None:
        self.assertEqual(self.config["extraction"]["stored_dtype"], "float32")
        self.assertEqual(self.config["analysis_arithmetic_dtype"], "float64")
        review = self.config["dtype_review"]
        self.assertIs(review["coordinated_review_complete"], True)
        self.assertEqual(review["person_b_approval_commit"], B_COMMIT)
        self.assertEqual(
            hashlib.sha256(
                builder._git_bytes(B_COMMIT, review["person_b_approval_path"])
            ).hexdigest(),
            review["person_b_approval_sha256"],
        )
        approval = json.loads(
            builder._git_bytes(B_COMMIT, review["person_b_approval_path"])
        )
        self.assertEqual(
            approval["dtype_decision"]["stored_activation_dtype"], "float32"
        )
        self.assertEqual(
            approval["dtype_decision"]["analysis_arithmetic_dtype"], "float64"
        )

    def test_14_successor_is_additive_and_rewrites_no_history(self) -> None:
        self.assertIs(self.config["additive_successor"], True)
        self.assertIs(self.config["historical_evidence_rewritten"], False)
        self.assertIs(self.config["person_a_mvp_yaml_modified"], False)
        predecessor = self.config["predecessor"]
        self.assertEqual(predecessor["path"], "configs/experiments/mvp.yaml")
        self.assertEqual(predecessor["predecessor_stored_dtype"], "float16")
        self.assertIs(predecessor["predecessor_evidence_rewritten"], False)
        self.assertEqual(
            hashlib.sha256(
                builder.repository_bytes("configs/experiments/mvp.yaml")
            ).hexdigest(),
            predecessor["sha256"],
        )
        text = (ROOT / "configs" / "experiments" / "mvp.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn('stored_dtype: "float16"', text)

    def test_15_successor_run_identity_is_new_and_reproducible(self) -> None:
        from mineocclude.experiments.mvp_lineage import make_run_id

        identity = self.config["successor_run_identity"]
        hashable = {
            key: value
            for key, value in self.config.items()
            if key != "successor_run_identity"
        }
        self.assertEqual(
            identity["config_hash"], builder._canonical_sha256(hashable)
        )
        self.assertEqual(
            identity["run_id"],
            make_run_id(
                stage_id=identity["stage_id"],
                config_hash=identity["config_hash"],
                code_sha=identity["code_sha"],
                seed=self.config["seed"],
            ),
        )
        prior = json.loads(
            builder.repository_bytes(
                "docs/status/person_a_phase7_mvp_v0_1/extraction_queue_state.json"
            )
        )
        self.assertNotEqual(identity["run_id"], prior["identity"]["run_id"])
        self.assertNotEqual(identity["config_hash"], prior["identity"]["config_hash"])

    def test_16_successor_code_identity_covers_the_execution_files(self) -> None:
        code_identity = self.config["successor_code_identity"]
        self.assertEqual(
            sorted(code_identity["files"]),
            sorted(builder.SUCCESSOR_CODE_IDENTITY_FILES),
        )
        for path, digest in code_identity["files"].items():
            with self.subTest(path=path):
                self.assertEqual(
                    hashlib.sha256(builder.repository_bytes(path)).hexdigest(), digest
                )
        self.assertEqual(
            code_identity["code_identity_sha256"],
            builder._canonical_sha256(code_identity["files"]),
        )

    def test_17_config_binds_every_required_authority(self) -> None:
        inputs = self.config["inputs"]
        for field in (
            "person_a_frame_map_package_sha256",
            "person_b_fold_manifest_sha256",
            "person_b_oracle_target_manifest_sha256",
            "person_b_row_universe_sha256",
            "person_c_accepted_manifest_sha256",
            "person_c_event_table_sha256",
            "person_c_visibility_join_sha256",
        ):
            with self.subTest(field=field):
                self.assertEqual(len(inputs[field]), 64)
        extraction = self.config["extraction"]
        self.assertEqual(extraction["layer_indices"], list(range(LAYER_COUNT)))
        self.assertEqual(
            extraction["hook_site"], "decoder_layer_output_residual_stream"
        )
        self.assertEqual(self.config["expected_trajectory_count"], EXPECTED_TRAJECTORIES)
        self.assertEqual(
            self.config["expected_model_frame_key_count"], EXPECTED_MODEL_FRAMES
        )
        self.assertEqual(self.config["expected_activation_row_count"], EXPECTED_ROWS)
        self.assertEqual(
            self.config["expected_activation_chunk_count"], EXPECTED_CHUNKS
        )
        self.assertEqual(self.config["frame_token_map"]["visual_tokens_per_frame"], 336)

    def test_18_extraction_covers_the_full_universe_not_b_admitted_rows(self) -> None:
        extraction = self.config["extraction"]
        self.assertIs(extraction["extract_full_model_frame_universe"], True)
        self.assertIs(extraction["restricted_to_person_b_admitted_rows"], False)
        row_universe = json.loads(
            builder._git_bytes(
                B_COMMIT, self.config["inputs"]["person_b_row_universe_path"]
            )
        )
        self.assertEqual(row_universe["admitted_analysis_row_count"], 662)
        self.assertEqual(
            row_universe["total_model_frame_key_count"], EXPECTED_MODEL_FRAMES
        )
        self.assertEqual(
            self.config["expected_model_frame_key_count"],
            row_universe["total_model_frame_key_count"],
        )

    # ------------------------------------------------------------------
    # Successor queue
    # ------------------------------------------------------------------
    def test_19_queue_covers_66_trajectories_and_2468_frames(self) -> None:
        items = self.queue["items"]
        self.assertEqual(len(items), EXPECTED_TRAJECTORIES)
        self.assertEqual(
            len({item["trajectory_id"] for item in items}), EXPECTED_TRAJECTORIES
        )
        self.assertEqual(sum(item["frame_count"] for item in items), EXPECTED_MODEL_FRAMES)
        self.assertEqual(
            sum(item["expected_activation_row_count"] for item in items), EXPECTED_ROWS
        )
        self.assertEqual(
            sum(item["expected_chunk_count"] for item in items), EXPECTED_CHUNKS
        )
        for item in items:
            with self.subTest(item=item["item_id"]):
                self.assertEqual(item["layer_count"], LAYER_COUNT)

    def test_20_queue_is_wholly_pending_with_nothing_reused(self) -> None:
        states = Counter(item["state"] for item in self.queue["items"])
        self.assertEqual(states, Counter({"pending": EXPECTED_TRAJECTORIES}))
        for item in self.queue["items"]:
            with self.subTest(item=item["item_id"]):
                self.assertIsNone(item["completion"])
                self.assertEqual(item["attempt_count"], 0)
                self.assertEqual(item["attempts"], [])
                self.assertIsNone(item["quarantine_reason"])

    def test_21_queue_carries_the_successor_identity_only(self) -> None:
        identity = self.queue["identity"]
        successor = self.config["successor_run_identity"]
        self.assertEqual(identity["run_id"], successor["run_id"])
        self.assertEqual(identity["config_hash"], successor["config_hash"])
        self.assertEqual(identity["code_sha"], successor["code_sha"])
        self.assertEqual(
            identity["accepted_manifest_sha256"], C_MANIFEST_SHA256
        )

    def test_22_queue_frame_counts_match_the_frame_map_package(self) -> None:
        index = json.loads(
            builder.repository_bytes(
                f"{builder.A_FRAME_MAP_PACKAGE_REL}/frame_map_index.json"
            )
        )
        by_id = {item["trajectory_id"]: item for item in self.queue["items"]}
        self.assertEqual(sorted(by_id), sorted(index["per_trajectory"]))
        for trajectory_id, entry in index["per_trajectory"].items():
            with self.subTest(trajectory=trajectory_id):
                self.assertEqual(
                    by_id[trajectory_id]["frame_count"], entry["model_frame_count"]
                )

    # ------------------------------------------------------------------
    # Owner acknowledgement supersession
    # ------------------------------------------------------------------
    def test_23_successor_acknowledgement_supersedes_additively(self) -> None:
        supersedes = self.ack["supersedes"]
        self.assertIs(supersedes["supersession_is_additive"], True)
        self.assertIs(supersedes["predecessor_evidence_rewritten"], False)
        self.assertIs(
            supersedes["predecessor_real_frame_maps_materialized"], False
        )
        raw = builder.repository_bytes(supersedes["path"])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), supersedes["predecessor_sha256"])
        stale = json.loads(raw)
        self.assertIs(
            stale["expected_model_frame_universe"]["real_frame_maps_materialized"],
            False,
        )

    def test_24_successor_acknowledgement_records_the_new_state(self) -> None:
        frames = self.ack["frame_maps"]
        self.assertIs(frames["real_frame_maps_materialized"], True)
        self.assertEqual(frames["model_frame_key_count"], EXPECTED_MODEL_FRAMES)
        self.assertEqual(frames["trajectory_count"], EXPECTED_TRAJECTORIES)
        self.assertEqual(frames["duplicate_model_frame_key_count"], 0)
        self.assertEqual(frames["missing_trajectory_count"], 0)
        authority = self.ack["model_preprocess_authority"]
        self.assertIs(authority["three_fields_are_distinct"], True)
        self.assertNotEqual(
            authority["preprocess_hash"],
            authority["preprocessing_implementation_sha256"],
        )
        self.assertEqual(authority["model_hash"], authority["checkpoint_sha256"])
        self.assertEqual(
            self.ack["storage_contract"]["stored_activation_dtype"], "float32"
        )
        self.assertEqual(
            self.ack["successor_queue"]["run_id"],
            self.config["successor_run_identity"]["run_id"],
        )

    # ------------------------------------------------------------------
    # Person A to Person D handoff
    # ------------------------------------------------------------------
    def test_25_handoff_carries_the_full_frame_and_preprocessing_contract(self) -> None:
        self.assertEqual(
            self.handoff["frame_map"]["model_frame_key_count"], EXPECTED_MODEL_FRAMES
        )
        self.assertEqual(
            len(self.handoff["frame_map"]["per_trajectory"]), EXPECTED_TRAJECTORIES
        )
        self.assertIs(self.handoff["applicability"]["all_66_cells_applicable"], True)
        preprocessing = self.handoff["preprocessing_authority"]
        for field in (
            "preprocess_hash",
            "preprocessing_implementation_path",
            "preprocessing_implementation_sha256",
            "interpolation",
            "normalization",
            "scaling",
            "color_convention",
        ):
            with self.subTest(field=field):
                self.assertTrue(preprocessing[field], field)
        self.assertEqual(preprocessing["frozen_source_resolution_hw"], [360, 640])
        self.assertEqual(preprocessing["model_facing_resolution_hw"], [224, 384])
        self.assertEqual(
            self.handoff["canonicalization_rules"]["model_facing_frame_identity"],
            ["trajectory_id", "model_frame_idx"],
        )
        self.assertIs(
            self.handoff["canonicalization_rules"]["row_order_defines_identity"], False
        )

    def test_26_handoff_per_trajectory_hashes_resolve(self) -> None:
        for trajectory_id, entry in self.handoff["frame_map"]["per_trajectory"].items():
            with self.subTest(trajectory=trajectory_id):
                raw = (ROOT / entry["frame_map_path"]).read_bytes()
                self.assertEqual(
                    hashlib.sha256(raw).hexdigest(), entry["frame_map_sha256"]
                )

    def test_27_handoff_reports_the_source_media_blocker_truthfully(self) -> None:
        self.assertIs(self.handoff["ready"], False)
        self.assertIs(
            self.handoff["preprocessed_frame_artifact"]["materialized"], False
        )
        findings = self.handoff["blocking_findings"]
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding["blocker_id"], "C-66-CELL-640x360-MEDIA-MISSING")
        self.assertEqual(finding["owner"], "person_c_data")
        self.assertIs(finding["blocks_person_a_activation_extraction"], True)
        self.assertIs(finding["blocks_person_d_raw_pixel_baseline"], True)
        self.assertTrue(finding["resolution_options"])

    def test_28_the_source_media_gap_is_real(self) -> None:
        """The frozen preprocessing genuinely rejects the materialised frames."""

        from mineocclude.models._mineworld_adapter_wave2 import (
            PINNED_SOURCE_HEIGHT,
            PINNED_SOURCE_WIDTH,
        )

        self.assertEqual(
            [PINNED_SOURCE_HEIGHT, PINNED_SOURCE_WIDTH],
            self.handoff["preprocessing_authority"]["frozen_source_resolution_hw"],
        )
        observed = self.handoff["preprocessing_authority"][
            "observed_c6a_framebuffer_hw"
        ]
        self.assertNotEqual(observed, [PINNED_SOURCE_HEIGHT, PINNED_SOURCE_WIDTH])
        index = json.loads(
            builder.repository_bytes(
                f"{builder.A_FRAME_MAP_PACKAGE_REL}/frame_map_index.json"
            )
        )
        trajectory_id = min(index["per_trajectory"])
        rows = [
            json.loads(line)
            for line in (
                ROOT
                / builder.A_FRAME_MAP_PACKAGE_REL
                / "frame_maps"
                / f"{trajectory_id}.jsonl"
            )
            .read_bytes()
            .decode("utf-8")
            .splitlines()
            if line.strip()
        ]
        source = Path(rows[0]["source_frame_runtime_path"])
        if not source.is_file():
            self.skipTest("Person C runtime payloads are not on this host")
        import cv2

        image = cv2.imread(str(source), cv2.IMREAD_COLOR)
        self.assertIsNotNone(image)
        self.assertEqual(list(image.shape[:2]), observed)

    def test_29_handoff_names_person_d_owned_repinning(self) -> None:
        note = self.handoff["person_d_consumer_note"]
        self.assertIs(note["person_d_module_is_pinned_to_ten_pilot_scope"], True)
        self.assertIs(note["person_d_owns_this_change"], True)
        self.assertIn("PERSON_A_FRAME_MANIFEST_SHA256", note["person_d_must_repin_constants"])
        self.assertTrue(
            self.handoff["deterministic_entry_point"]["person_d_production_command"]
        )

    # ------------------------------------------------------------------
    # Byte transport
    # ------------------------------------------------------------------
    def test_30_byte_transport_remains_pending_without_invention(self) -> None:
        self.assertIsNone(self.transport["approved_durable_destination"])
        self.assertIs(self.transport["byte_transport_destination_pending"], True)
        self.assertIs(self.transport["sagemaker_byte_access_ready"], False)
        self.assertIs(self.transport["destination_fabricated"], False)
        self.assertIs(
            self.transport["reinspection"]["object_store_destination_found"], False
        )
        for entry in self.transport["reinspection"]["results"]:
            with self.subTest(ref=entry["ref"]):
                self.assertEqual(entry["hits"], [])
        self.assertEqual(
            self.transport["executable_transfer_procedure"]["unfilled_placeholders"],
            ["<APPROVED_DESTINATION_URI>"],
        )
        self.assertTrue(self.transport["executable_transfer_procedure"]["steps"])

    def test_31_windows_byte_state_is_fully_verified(self) -> None:
        state = self.transport["windows_byte_state"]
        self.assertEqual(state["trajectory_count"], EXPECTED_TRAJECTORIES)
        self.assertEqual(
            state["trajectory_hash_verified_count"], EXPECTED_TRAJECTORIES
        )
        self.assertEqual(
            state["artifact_hash_verified_count"], state["artifact_count"]
        )

    def test_32_no_credential_value_appears_in_the_package(self) -> None:
        for path in sorted(STATUS_ROOT.glob("*.json")):
            text = path.read_text(encoding="utf-8").lower()
            with self.subTest(path=path.name):
                for marker in (
                    "aws_secret_access_key",
                    "aws_access_key_id",
                    "-----begin",
                    "password",
                ):
                    self.assertNotIn(marker, text)

    # ------------------------------------------------------------------
    # Phase 6 preconditions
    # ------------------------------------------------------------------
    def test_33_precondition_layers_are_reported_separately(self) -> None:
        receipt = self.preconditions
        self.assertIn("phase6_contract_preconditions_ready", receipt)
        self.assertIn("phase6_runtime_infrastructure_ready", receipt)
        self.assertIn("aggregate_phase6_runtime_authorized", receipt)
        self.assertIs(receipt["phase6_runtime_infrastructure_ready"], False)
        self.assertIs(receipt["aggregate_phase6_runtime_authorized"], False)
        self.assertIs(receipt["aggregate_authorization_authority_present"], False)
        self.assertIs(receipt["self_authorizes_phase6"], False)
        self.assertEqual(
            receipt["phase6_contract_preconditions_ready"],
            all(entry["satisfied"] for entry in receipt["contract_conditions"]),
        )
        self.assertEqual(
            receipt["phase6_runtime_infrastructure_ready"],
            all(entry["satisfied"] for entry in receipt["infrastructure_conditions"]),
        )

    def test_34_every_role_commit_is_recorded(self) -> None:
        roles = self.preconditions["assessed_roles"]
        self.assertEqual(
            sorted(roles), ["person_a", "person_b", "person_c", "person_d", "person_e"]
        )
        for role, entry in roles.items():
            with self.subTest(role=role):
                self.assertEqual(len(entry["commit"]), 40)
                if role == "person_a":
                    continue
                # The recorded commit is the snapshot this package assessed. A
                # role branch may advance afterwards, so require the commit to
                # exist and remain reachable from its ref rather than to equal
                # the moving tip, which would expire this guard on any push.
                self.assertEqual(
                    builder._completed(
                        ["git", "cat-file", "-e", f"{entry['commit']}^{{commit}}"]
                    ).returncode,
                    0,
                )
                self.assertEqual(
                    builder._completed(
                        [
                            "git",
                            "merge-base",
                            "--is-ancestor",
                            entry["commit"],
                            entry["ref"],
                        ]
                    ).returncode,
                    0,
                )

    def test_35_unsatisfied_conditions_name_an_owner(self) -> None:
        unsatisfied = [
            entry
            for entry in (
                self.preconditions["contract_conditions"]
                + self.preconditions["infrastructure_conditions"]
            )
            if not entry["satisfied"]
        ]
        self.assertTrue(unsatisfied)
        for entry in unsatisfied:
            with self.subTest(condition=entry["condition"]):
                self.assertTrue(entry["owner"])

    # ------------------------------------------------------------------
    # Package integrity
    # ------------------------------------------------------------------
    def test_36_protected_false_claims_hold(self) -> None:
        for path in sorted(STATUS_ROOT.glob("*.json")):
            document = _json(path.name)
            with self.subTest(path=path.name):
                self.assertEqual(
                    builder._protected_false_violations(document, path.name), []
                )

    def test_37_inventory_matches_the_committed_bytes(self) -> None:
        self.assertIs(self.inventory["inventory_excludes_self"], True)
        self.assertEqual(
            sorted(self.inventory["files"]),
            sorted(set(builder.OUTPUT_PATHS) - {"sha256_inventory.json"}),
        )
        for name, expected in self.inventory["files"].items():
            with self.subTest(name=name):
                self.assertEqual(
                    hashlib.sha256((STATUS_ROOT / name).read_bytes()).hexdigest(),
                    expected,
                )

    def test_38_builder_output_is_deterministic(self) -> None:
        first = builder.build_documents()
        second = builder.build_documents()
        self.assertEqual(first, second)
        for name, document in first.items():
            with self.subTest(name=name):
                self.assertEqual(
                    builder._json_bytes(document),
                    (STATUS_ROOT / name).read_bytes(),
                )

    def test_39_validation_receipt_agrees_with_the_package(self) -> None:
        receipt = self.validation
        self.assertEqual(receipt["queue_trajectory_count"], EXPECTED_TRAJECTORIES)
        self.assertEqual(receipt["queue_model_frame_key_count"], EXPECTED_MODEL_FRAMES)
        self.assertEqual(receipt["queue_layer_count"], LAYER_COUNT)
        self.assertEqual(receipt["queue_expected_activation_row_count"], EXPECTED_ROWS)
        self.assertEqual(receipt["stored_activation_dtype"], "float32")
        self.assertEqual(receipt["supplied_hash_rejected_count"], 2)
        self.assertEqual(
            receipt["successor_run_id"],
            self.config["successor_run_identity"]["run_id"],
        )
        self.assertEqual(receipt["queue_states"], {"pending": EXPECTED_TRAJECTORIES})


if __name__ == "__main__":
    unittest.main()
