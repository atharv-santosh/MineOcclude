"""Focused CPU-only tests for Person A's local 66-cell preparation.

These tests never load MineWorld weights, never touch a GPU, and never extract
activations. Frame-map regeneration is exercised against the real hash-verified
Person C runtime payloads.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import unittest
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BUILDER_PATH = ROOT / "scripts" / "build_person_a_66_cell_local_preparation_v0_1.py"
RUNNER_PATH = ROOT / "scripts" / "run_mvp.py"
DATA_ROOT = ROOT / "data" / "handoff_a" / "person_a_66_cell_production_input_v0_1"
STATUS_ROOT = ROOT / "docs" / "status" / "person_a_66_cell_local_preparation_v0_1"
PHASE7_ROOT = ROOT / "docs" / "status" / "person_a_phase7_mvp_v0_1"

EXPECTED_TRAJECTORIES = 66
EXPECTED_MODEL_FRAMES = 2468
LAYER_COUNT = 20
C_COMMIT = "a8bed8adf7e24ca7fe5b6b6afa3342da61434be3"
C_MANIFEST_SHA256 = (
    "96ba43e15bc024aeaef7c519fa4ece0a4afe0bb0e877501dffaca44fee927ff7"
)


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


builder = _load("person_a_66_cell_local_preparation_builder", BUILDER_PATH)
runner = _load("person_a_run_mvp", RUNNER_PATH)


def _json(path: Path) -> Any:
    return json.loads(path.read_bytes())


def _frame_rows(trajectory_id: str) -> list[dict[str, Any]]:
    payload = (DATA_ROOT / "frame_maps" / f"{trajectory_id}.jsonl").read_bytes()
    return [
        json.loads(line) for line in payload.decode("utf-8").splitlines() if line.strip()
    ]


class PersonA66CellLocalPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.index = _json(DATA_ROOT / "frame_map_index.json")
        cls.accepted = _json(DATA_ROOT / "bundle_manifest.json")
        cls.inventory = _json(DATA_ROOT / "source_byte_inventory.json")
        cls.data_hashes = _json(DATA_ROOT / "sha256_inventory.json")
        cls.matrix = _json(PHASE7_ROOT / "step_7_2_matrix_report.json")
        cls.queue = _json(PHASE7_ROOT / "extraction_queue_state.json")
        cls.queue_status = _json(PHASE7_ROOT / "step_7_5_queue_status.json")
        cls.dtype = _json(STATUS_ROOT / "storage_dtype_reconciliation.json")
        cls.transfer = _json(STATUS_ROOT / "byte_transfer_plan.json")
        cls.receipt = _json(STATUS_ROOT / "preparation_receipt.json")
        cls.validation = _json(STATUS_ROOT / "validation_receipt.json")

    # ------------------------------------------------------------------
    # Manifest authority
    # ------------------------------------------------------------------
    def test_01_authorities_verify_against_exact_git_objects(self) -> None:
        self.assertEqual(builder.verify_authorities(), builder.A_STARTING_AUTHORITY)
        raw = builder._git_bytes(C_COMMIT, builder.C_ACCEPTED_MANIFEST_PATH)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), C_MANIFEST_SHA256)

    def test_02_accepted_input_manifest_binds_the_c_manifest(self) -> None:
        self.assertEqual(self.accepted["c_source_commit"], C_COMMIT)
        self.assertEqual(self.accepted["c_accepted_manifest_sha256"], C_MANIFEST_SHA256)
        self.assertEqual(
            self.accepted["accepted_trajectory_count"], EXPECTED_TRAJECTORIES
        )
        self.assertEqual(self.accepted["excluded_trajectory_count"], 0)
        self.assertIsNone(self.accepted["current_certified_trajectory"])
        self.assertIn(
            "person_a_canonical_c6a_multilayout_sagemaker_input_v0_1",
            self.accepted["supersedes"],
        )

    def test_03_cli_reads_the_66_cell_manifest_as_current_authority(self) -> None:
        self.assertEqual(
            runner.accepted_input_manifest_path(), runner.HANDOFF_BUNDLE_66
        )
        bundles = runner.load_accepted_bundles()
        self.assertEqual(len(bundles), EXPECTED_TRAJECTORIES)
        self.assertEqual(
            len({bundle["trajectory_id"] for bundle in bundles}),
            EXPECTED_TRAJECTORIES,
        )
        identity = runner.accepted_input_manifest_identity()
        self.assertEqual(identity["person_c_accepted_manifest_sha256"], C_MANIFEST_SHA256)
        self.assertEqual(identity["person_c_source_commit"], C_COMMIT)

    # ------------------------------------------------------------------
    # 66-cell matrix
    # ------------------------------------------------------------------
    def test_04_matrix_reconciles_66_accepted_and_zero_shortfall(self) -> None:
        self.assertEqual(self.matrix["expected_cell_count"], EXPECTED_TRAJECTORIES)
        self.assertEqual(self.matrix["accepted_cell_count"], EXPECTED_TRAJECTORIES)
        self.assertEqual(self.matrix["shortfall_count"], 0)
        self.assertEqual(self.matrix["shortfall"], [])
        self.assertIs(self.matrix["complete"], True)
        counts = self.matrix["state_counts"]
        self.assertEqual(counts["accepted"], EXPECTED_TRAJECTORIES)
        for state in ("excluded", "missing", "recollection_pending"):
            self.assertEqual(counts[state], 0, state)
        self.assertEqual(
            self.matrix["accepted_group_counts"], self.matrix["expected_group_counts"]
        )

    def test_05_matrix_records_the_exact_c_manifest_sha(self) -> None:
        bound = self.matrix["accepted_input_manifest"]
        self.assertEqual(bound["person_c_accepted_manifest_sha256"], C_MANIFEST_SHA256)
        self.assertEqual(bound["person_c_source_commit"], C_COMMIT)
        self.assertEqual(
            bound["sha256"],
            hashlib.sha256((DATA_ROOT / "bundle_manifest.json").read_bytes()).hexdigest(),
        )

    def test_06_no_five_cell_authority_remains_current(self) -> None:
        serialized = json.dumps(self.matrix)
        self.assertNotIn(
            "person_a_canonical_c6a_multilayout_sagemaker_input_v0_1/bundle_manifest",
            json.dumps(
                [row["evidence_path"] for row in self.matrix["cells"]]
            ),
        )
        self.assertNotIn("No per-trajectory accepted handoff bundle", serialized)
        for row in self.matrix["cells"]:
            with self.subTest(cell=row["cell_id"]):
                self.assertTrue(
                    str(row["evidence_path"]).startswith(builder.DATA_ROOT_REL),
                    row["evidence_path"],
                )

    # ------------------------------------------------------------------
    # 66-cell queue planning
    # ------------------------------------------------------------------
    def test_07_queue_covers_all_66_trajectories(self) -> None:
        self.assertEqual(len(self.queue["items"]), EXPECTED_TRAJECTORIES)
        self.assertEqual(self.queue_status["item_count"], EXPECTED_TRAJECTORIES)
        identifiers = [item["trajectory_id"] for item in self.queue["items"]]
        self.assertEqual(len(set(identifiers)), EXPECTED_TRAJECTORIES)
        self.assertEqual(
            set(identifiers), set(self.index["per_trajectory"]),
        )

    def test_08_queue_items_are_pending_with_no_reused_completion(self) -> None:
        states = Counter(item["state"] for item in self.queue["items"])
        self.assertEqual(states["pending"], EXPECTED_TRAJECTORIES)
        self.assertEqual(sum(states.values()), EXPECTED_TRAJECTORIES)
        for item in self.queue["items"]:
            with self.subTest(item=item["item_id"]):
                self.assertIsNone(item["completion"])
                self.assertEqual(item["attempt_count"], 0)
        self.assertEqual(self.queue_status["completed_activation_row_count"], 0)
        self.assertEqual(self.queue_status["completed_chunk_count"], 0)

    def test_09_queue_expectations_match_the_frame_maps(self) -> None:
        by_id = {item["trajectory_id"]: item for item in self.queue["items"]}
        for trajectory_id, entry in self.index["per_trajectory"].items():
            with self.subTest(trajectory=trajectory_id):
                item = by_id[trajectory_id]
                self.assertEqual(item["frame_count"], entry["model_frame_count"])
                self.assertEqual(item["layer_count"], LAYER_COUNT)
                self.assertEqual(
                    item["expected_activation_row_count"],
                    entry["model_frame_count"] * LAYER_COUNT,
                )
                self.assertEqual(item["expected_chunk_count"], LAYER_COUNT)
        self.assertEqual(
            sum(item["expected_activation_row_count"] for item in self.queue["items"]),
            EXPECTED_MODEL_FRAMES * LAYER_COUNT,
        )

    def test_10_queue_identity_is_immutable_and_prior_state_superseded(self) -> None:
        identity = self.queue["identity"]
        for field in ("accepted_manifest_sha256", "code_sha", "config_hash", "run_id"):
            self.assertTrue(identity[field], field)
        self.assertEqual(
            identity["accepted_manifest_sha256"],
            hashlib.sha256(
                (DATA_ROOT / "bundle_manifest.json").read_bytes()
            ).hexdigest(),
        )
        superseded = sorted(
            path.name
            for path in PHASE7_ROOT.glob("extraction_queue_state.superseded.*.json")
        )
        self.assertTrue(superseded)
        for name in superseded:
            document = _json(PHASE7_ROOT / name)
            with self.subTest(name=name):
                self.assertTrue(document.get("superseded_by_run_id"))
                self.assertNotEqual(
                    document["identity"]["run_id"], identity["run_id"]
                )

    # ------------------------------------------------------------------
    # Frame-map generation and cardinality
    # ------------------------------------------------------------------
    def test_11_frame_map_package_has_66_trajectories(self) -> None:
        self.assertEqual(self.index["trajectory_count"], EXPECTED_TRAJECTORIES)
        self.assertEqual(len(self.index["per_trajectory"]), EXPECTED_TRAJECTORIES)
        files = sorted(path.name for path in (DATA_ROOT / "frame_maps").glob("*.jsonl"))
        self.assertEqual(len(files), EXPECTED_TRAJECTORIES)
        self.assertEqual(
            files,
            sorted(f"{trajectory}.jsonl" for trajectory in self.index["per_trajectory"]),
        )

    def test_12_global_model_frame_key_count_is_exact(self) -> None:
        self.assertEqual(self.index["model_frame_key_count"], EXPECTED_MODEL_FRAMES)
        self.assertEqual(
            self.index["expected_model_frame_key_count"], EXPECTED_MODEL_FRAMES
        )
        self.assertIs(self.index["model_frame_key_count_matches_expected"], True)
        total = sum(
            entry["model_frame_count"]
            for entry in self.index["per_trajectory"].values()
        )
        self.assertEqual(total, EXPECTED_MODEL_FRAMES)

    def test_13_no_duplicate_or_missing_model_frame_keys(self) -> None:
        self.assertEqual(self.index["duplicate_model_frame_keys"], [])
        self.assertEqual(self.index["duplicate_model_frame_key_count"], 0)
        self.assertEqual(self.index["missing_trajectory_ids"], [])
        self.assertEqual(self.index["missing_trajectory_count"], 0)
        keys: set[tuple[str, int]] = set()
        for trajectory_id, entry in self.index["per_trajectory"].items():
            rows = _frame_rows(trajectory_id)
            with self.subTest(trajectory=trajectory_id):
                self.assertEqual(len(rows), entry["model_frame_count"])
                self.assertEqual(len(rows), entry["declared_frame_count"])
                indices = [row["model_frame_idx"] for row in rows]
                self.assertEqual(sorted(indices), list(range(len(rows))))
            for row in rows:
                key = (row["trajectory_id"], row["model_frame_idx"])
                self.assertNotIn(key, keys)
                keys.add(key)
        self.assertEqual(len(keys), EXPECTED_MODEL_FRAMES)

    def test_14_every_model_frame_traces_to_its_immutable_source_keys(self) -> None:
        required = set(builder.FRAME_MAP_ROW_FIELDS)
        for trajectory_id in self.index["per_trajectory"]:
            rows = _frame_rows(trajectory_id)
            for row in rows[:3] + rows[-1:]:
                with self.subTest(trajectory=trajectory_id, frame=row["model_frame_idx"]):
                    self.assertEqual(set(row), required)
                    for field in (
                        "episode_id",
                        "layout_id",
                        "server_tick",
                        "render_frame_idx",
                        "action_idx",
                        "source_frame_sha256",
                        "source_raw_action_row_sha256",
                        "normalized_action_sha256",
                        "source_server_state_row_sha256",
                        "visibility_identity_sha256",
                        "condition_identity_sha256",
                        "c_manifest_sha256",
                        "preprocessing_identity",
                        "action_converter_identity",
                    ):
                        self.assertIsNotNone(row[field], field)
                    self.assertEqual(row["c_manifest_sha256"], C_MANIFEST_SHA256)
                    self.assertEqual(row["c_source_commit"], C_COMMIT)
                    self.assertEqual(len(row["action_tokens"]), 11)
                    self.assertTrue(
                        all(token >= 8192 for token in row["action_tokens"])
                    )

    def test_15_keys_not_row_order_define_identity(self) -> None:
        self.assertIs(self.index["row_order_is_not_identity"], True)
        self.assertEqual(self.index["model_facing_key"], ["trajectory_id", "model_frame_idx"])
        trajectory_id = min(self.index["per_trajectory"])
        rows = _frame_rows(trajectory_id)
        shuffled = list(reversed(rows))
        by_key = {
            (row["trajectory_id"], row["model_frame_idx"]): row for row in shuffled
        }
        for row in rows:
            key = (row["trajectory_id"], row["model_frame_idx"])
            self.assertEqual(by_key[key], row)

    def test_16_index_field_uniqueness_holds_per_trajectory(self) -> None:
        for trajectory_id in self.index["per_trajectory"]:
            rows = _frame_rows(trajectory_id)
            for field in ("server_tick", "render_frame_idx", "action_idx",
                          "model_frame_idx"):
                with self.subTest(trajectory=trajectory_id, field=field):
                    values = [row[field] for row in rows]
                    self.assertEqual(len(set(values)), len(values))

    # ------------------------------------------------------------------
    # Duplicate / missing rejection
    # ------------------------------------------------------------------
    def test_17_duplicate_model_frame_keys_are_rejected(self) -> None:
        trajectory_id = min(self.index["per_trajectory"])
        rows = _frame_rows(trajectory_id)
        duplicated = rows + [dict(rows[0])]
        summaries = {
            trajectory_id: {
                **self.index["per_trajectory"][trajectory_id],
                "model_frame_count": len(duplicated),
            }
        }
        index = builder.frame_map_index({trajectory_id: duplicated}, summaries)
        self.assertTrue(index["duplicate_model_frame_keys"])
        self.assertGreater(index["duplicate_model_frame_key_count"], 0)

    def test_18_declared_versus_observed_shortfall_is_reported(self) -> None:
        trajectory_id = min(self.index["per_trajectory"])
        rows = _frame_rows(trajectory_id)[:-1]
        summaries = {
            trajectory_id: {
                **self.index["per_trajectory"][trajectory_id],
                "model_frame_count": len(rows),
            }
        }
        index = builder.frame_map_index({trajectory_id: rows}, summaries)
        self.assertEqual(index["missing_trajectory_ids"], [trajectory_id])
        self.assertIs(index["model_frame_key_count_matches_expected"], False)

    def test_19_a_frame_count_disagreement_fails_closed(self) -> None:
        _manifest, bundles = builder.load_c_bundles()
        bundle = json.loads(json.dumps(bundles[0]))
        bundle["qa_summary"]["cardinality_counts"]["frame_count"] += 1
        with self.assertRaises(builder.PreparationError) as caught:
            builder.build_trajectory_frame_map(
                bundle,
                convert_action=lambda _row: ({}, tuple(range(11)), True),
                canonical_raw_action=lambda row: dict(row),
            )
        self.assertEqual(caught.exception.code, "declared_frame_count_mismatch")

    # ------------------------------------------------------------------
    # Source checksum verification and deterministic regeneration
    # ------------------------------------------------------------------
    def test_20_c_source_hashes_are_verified_before_consumption(self) -> None:
        _manifest, bundles = builder.load_c_bundles()
        self.assertEqual(len(bundles), EXPECTED_TRAJECTORIES)
        inventory = json.loads(
            builder._git_bytes(C_COMMIT, builder.C_INVENTORY_PATH)
        )["files"]
        for bundle in bundles:
            relative = bundle["_bundle_path"].split("/")[-1]
            with self.subTest(bundle=relative):
                self.assertEqual(
                    bundle["_bundle_sha256"],
                    inventory[f"per_trajectory/{relative}"],
                )

    def test_21_every_source_artifact_is_hash_verified_on_the_windows_host(
        self,
    ) -> None:
        self.assertEqual(
            self.inventory["artifact_hash_verified_count"],
            self.inventory["artifact_count"],
        )
        self.assertEqual(self.inventory["missing_paths"], [])
        self.assertEqual(self.inventory["trajectory_count"], EXPECTED_TRAJECTORIES)
        for trajectory_id, entry in self.inventory["per_trajectory"].items():
            with self.subTest(trajectory=trajectory_id):
                self.assertEqual(entry["state"], "available_hash_verified")

    def test_22_frame_map_regeneration_is_deterministic(self) -> None:
        trajectory_id = min(self.index["per_trajectory"])
        episode_id = int(trajectory_id.split("ep")[1])
        _manifest, bundles = builder.load_c_bundles()
        bundle = next(
            item for item in bundles if item["identity"]["episode_id"] == episode_id
        )
        from mineocclude.models._mineworld_adapter_wave2 import _OfficialActionConverter

        converter = _OfficialActionConverter(builder.MINEWORLD_SOURCE_ROOT)
        mapper = builder._load_canonical_raw_action_mapper()
        first, summary_a = builder.build_trajectory_frame_map(
            bundle, convert_action=converter.convert, canonical_raw_action=mapper
        )
        second, summary_b = builder.build_trajectory_frame_map(
            bundle, convert_action=converter.convert, canonical_raw_action=mapper
        )
        self.assertEqual(first, second)
        self.assertEqual(summary_a, summary_b)
        self.assertEqual(first, _frame_rows(trajectory_id))
        self.assertEqual(
            hashlib.sha256(builder._jsonl_bytes(first)).hexdigest(),
            self.index["per_trajectory"][trajectory_id]["frame_map_sha256"],
        )

    def test_23_committed_package_inventory_matches_the_committed_bytes(self) -> None:
        self.assertIs(self.data_hashes["inventory_excludes_self"], True)
        self.assertEqual(
            self.data_hashes["file_count"], len(self.data_hashes["files"]) + 1
        )
        for name, expected in self.data_hashes["files"].items():
            with self.subTest(name=name):
                self.assertEqual(
                    hashlib.sha256((DATA_ROOT / name).read_bytes()).hexdigest(),
                    expected,
                )

    # ------------------------------------------------------------------
    # Storage dtype reconciliation
    # ------------------------------------------------------------------
    def test_24_dtype_evidence_resolves_to_the_exact_committed_bytes(self) -> None:
        records = builder._verified_evidence()
        self.assertEqual(set(records), set(builder.DTYPE_EVIDENCE))
        for name, record in records.items():
            with self.subTest(name=name):
                self.assertEqual(
                    hashlib.sha256(
                        builder.repository_bytes(record["path"])
                    ).hexdigest(),
                    record["sha256"],
                )
                self.assertEqual(
                    record["digest_scope"], "repository_canonical_lf_bytes"
                )
                self.assertEqual(self.dtype["evidence"][name], record)

    def test_25_executed_production_bytes_imply_float32_storage(self) -> None:
        self.assertIs(self.dtype["executed_production_all_imply_float32"], True)
        measured = [
            entry
            for item in self.dtype["evidence_for_float32_storage"]
            for entry in item.get("measured", ())
        ]
        self.assertEqual(len(measured), 10)
        for entry in measured:
            with self.subTest(trajectory=entry["trajectory_id"]):
                self.assertAlmostEqual(entry["implied_element_bytes"], 4.0, places=2)
        self.assertEqual(self.dtype["stored_activation_dtype_executed"], "float32")
        self.assertEqual(self.dtype["hooked_source_tensor_dtype"], "float16")
        self.assertEqual(self.dtype["analysis_arithmetic_dtype"], "float64")

    def test_26_no_unilateral_dtype_change_was_made(self) -> None:
        self.assertIs(self.dtype["mvp_yaml_modified_by_this_package"], False)
        self.assertIs(self.dtype["person_a_unilateral_change_made"], False)
        self.assertIs(self.dtype["result_changing_review_required"], True)
        self.assertEqual(self.dtype["decision"], "PENDING_COORDINATED_A_B_REVIEW")
        self.assertIs(
            self.dtype["proposal"]["extraction_authorized_by_this_proposal"], False
        )
        self.assertEqual(
            sorted(self.dtype["proposal"]["authority_required"]),
            ["person_a_model", "person_b_analysis"],
        )
        self.assertEqual(len(self.dtype["proposal"]["options"]), 2)

    def test_27_frozen_config_still_declares_float16(self) -> None:
        text = (ROOT / "configs" / "experiments" / "mvp.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn('stored_dtype: "float16"', text)
        self.assertIn("bytes_per_activation_row: 8192.68303094984", text)
        self.assertEqual(
            hashlib.sha256(
                builder.repository_bytes("configs/experiments/mvp.yaml")
            ).hexdigest(),
            builder.DTYPE_EVIDENCE["frozen_mvp_configuration"][1],
        )

    # ------------------------------------------------------------------
    # Transport manifest schema
    # ------------------------------------------------------------------
    def test_28_transfer_plan_never_fabricates_a_destination(self) -> None:
        self.assertIsNone(self.transfer["approved_durable_destination"])
        self.assertIs(self.transfer["byte_transport_destination_pending"], True)
        self.assertIs(self.transfer["destination_fabricated"], False)
        self.assertIs(self.transfer["executable_transfer_command_available"], False)
        self.assertIs(self.transfer["transfer_launched"], False)
        self.assertTrue(self.transfer["destination_authorization_missing"])
        # "s3://" may appear only as a member of the approved-scheme vocabulary,
        # never as a concrete destination this package invented.
        audit = self.transfer["destination_audit"]
        self.assertIs(audit["s3_bucket_or_prefix_found"], False)
        self.assertEqual(audit["object_store_destination_count"], 0)
        self.assertIsNone(audit["approved_durable_destination"])
        without_vocabulary = dict(audit)
        without_vocabulary.pop("approved_schemes")
        self.assertNotIn("s3://", json.dumps(without_vocabulary))
        remainder = {
            key: value
            for key, value in self.transfer.items()
            if key != "destination_audit"
        }
        self.assertNotIn("s3://", json.dumps(remainder))

    def test_29_transfer_plan_carries_the_exact_66_source_inventory(self) -> None:
        sources = self.transfer["sources"]
        self.assertEqual(len(sources), EXPECTED_TRAJECTORIES)
        self.assertEqual(
            {entry["trajectory_id"] for entry in sources},
            set(self.index["per_trajectory"]),
        )
        for entry in sources:
            with self.subTest(trajectory=entry["trajectory_id"]):
                self.assertIs(entry["hash_verified"], True)
                self.assertIsNone(entry["intended_durable_destination"])
                self.assertGreater(entry["byte_size_total"], 0)
                self.assertIn("MineOcclude-Runtime", entry["windows_source_client_root"])
        expected = self.transfer["expected_byte_inventory"]
        self.assertEqual(expected["trajectory_count"], EXPECTED_TRAJECTORIES)
        self.assertEqual(
            expected["artifact_hash_verified_count"], expected["artifact_count"]
        )
        self.assertEqual(
            expected["byte_size_total"],
            sum(entry["byte_size_total"] for entry in sources),
        )

    def test_30_transfer_plan_documents_verification_and_materialization(self) -> None:
        self.assertTrue(self.transfer["verification_procedure"])
        self.assertTrue(self.transfer["sagemaker_materialization_procedure"])
        self.assertEqual(
            self.transfer["execution_environment"]["allowed_production_environment"],
            "aws_sagemaker_linux_gpu",
        )
        credential = self.transfer["credential_mechanism"]
        self.assertIs(credential["credential_value_present_in_repository"], False)
        self.assertIs(credential["accessible_from_this_environment"], False)

    def test_31_no_credential_value_is_present_in_any_published_document(self) -> None:
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
    # Preparation receipt
    # ------------------------------------------------------------------
    def test_32_receipt_binds_every_required_identity(self) -> None:
        self.assertEqual(self.receipt["person_c"]["commit"], C_COMMIT)
        self.assertEqual(
            self.receipt["person_c"]["accepted_manifest_sha256"], C_MANIFEST_SHA256
        )
        self.assertEqual(
            self.receipt["person_c"]["accepted_trajectory_count"],
            EXPECTED_TRAJECTORIES,
        )
        self.assertEqual(self.receipt["person_c"]["excluded_trajectory_count"], 0)
        for section, keys in (
            ("matrix", ("receipt", "expected_cell_count", "accepted_cell_count")),
            ("queue", ("receipt", "state_receipt", "run_id", "trajectory_count")),
            ("frame_maps", ("frame_map_index", "accepted_input_manifest")),
        ):
            for key in keys:
                with self.subTest(section=section, key=key):
                    self.assertIsNotNone(self.receipt[section][key])
        frames = self.receipt["frame_maps"]
        self.assertEqual(frames["model_frame_key_count"], EXPECTED_MODEL_FRAMES)
        self.assertEqual(
            frames["model_frame_key_count_expected"], EXPECTED_MODEL_FRAMES
        )
        self.assertEqual(
            len(frames["per_trajectory_model_frame_counts"]), EXPECTED_TRAJECTORIES
        )
        self.assertIs(frames["real_frame_maps_materialized"], True)

    def test_33_receipt_hashes_resolve_to_the_committed_bytes(self) -> None:
        records = [
            self.receipt["matrix"]["receipt"],
            self.receipt["queue"]["receipt"],
            self.receipt["queue"]["state_receipt"],
            self.receipt["frame_maps"]["frame_map_index"],
            self.receipt["frame_maps"]["accepted_input_manifest"],
            self.receipt["frame_maps"]["data_package_sha256_inventory"],
        ]
        for record in records:
            with self.subTest(path=record["path"]):
                raw = builder.repository_bytes(record["path"])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), record["sha256"])
                self.assertEqual(len(raw), record["byte_size"])

    def test_34_receipt_reports_both_byte_accessibility_states(self) -> None:
        access = self.receipt["byte_accessibility"]
        self.assertEqual(access["windows_trajectory_count"], EXPECTED_TRAJECTORIES)
        self.assertEqual(
            access["windows_trajectory_hash_verified_count"], EXPECTED_TRAJECTORIES
        )
        self.assertIs(access["sagemaker_byte_access_ready"], False)
        self.assertIs(access["byte_transport_destination_pending"], True)

    def test_35_receipt_never_claims_gpu_readiness_or_authorization(self) -> None:
        readiness = self.receipt["extraction_readiness"]
        self.assertIs(readiness["person_a_66_extraction_ready"], False)
        self.assertIs(readiness["gpu_extraction_started"], False)
        self.assertIs(readiness["model_loaded"], False)
        self.assertIs(readiness["person_a_66_local_preparation_complete"], True)
        self.assertIs(self.receipt["aggregate_phase6_runtime_authorized"], False)
        self.assertIn(
            "sagemaker_cannot_access_the_66_episode_payload_bytes",
            readiness["blockers"],
        )
        self.assertIn(
            "aggregate_phase6_runtime_authorization_absent", readiness["blockers"]
        )

    def test_36_protected_false_claims_hold_across_the_package(self) -> None:
        for path in sorted(STATUS_ROOT.glob("*.json")):
            document = _json(path)
            with self.subTest(path=path.name):
                self.assertEqual(
                    builder._protected_false_violations(document, path.name), []
                )

    def test_37_status_inventory_matches_the_committed_bytes(self) -> None:
        inventory = _json(STATUS_ROOT / "sha256_inventory.json")
        self.assertIs(inventory["inventory_excludes_self"], True)
        self.assertEqual(
            sorted(inventory["files"]),
            sorted(set(builder.STATUS_OUTPUT_PATHS) - {"sha256_inventory.json"}),
        )
        for name, expected in inventory["files"].items():
            with self.subTest(name=name):
                self.assertEqual(
                    hashlib.sha256((STATUS_ROOT / name).read_bytes()).hexdigest(),
                    expected,
                )

    def test_38_validation_receipt_agrees_with_the_package(self) -> None:
        self.assertIs(self.validation["frame_map_cardinality_pass"], True)
        self.assertEqual(self.validation["duplicate_model_frame_key_count"], 0)
        self.assertEqual(self.validation["missing_trajectory_count"], 0)
        self.assertEqual(
            self.validation["matrix_accepted_cell_count"], EXPECTED_TRAJECTORIES
        )
        self.assertEqual(
            self.validation["queue_trajectory_count"], EXPECTED_TRAJECTORIES
        )
        self.assertEqual(self.validation["source_artifact_missing_count"], 0)
        self.assertIs(self.validation["c_source_hashes_verified_before_consumption"], True)
        self.assertIs(self.validation["deterministic_regeneration"], True)


if __name__ == "__main__":
    unittest.main()
