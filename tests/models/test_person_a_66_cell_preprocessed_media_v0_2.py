"""Focused CPU-only tests for Person A's 66-cell model-facing frame materialization.

These tests never load MineWorld weights, never touch a GPU, and never run
activation extraction. Payload bytes live outside the repository, so tests that
need them skip when the external root is absent.
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
BUILDER_PATH = ROOT / "scripts" / "build_person_a_66_cell_preprocessed_media_v0_2.py"
STATUS_ROOT = ROOT / "docs" / "status" / "person_a_66_cell_preprocessed_media_v0_2"

EXPECTED_TRAJECTORIES = 66
EXPECTED_FRAMES = 2468
LAYER_COUNT = 20
EXPECTED_ROWS = EXPECTED_FRAMES * LAYER_COUNT
PAYLOAD_BYTES = 3 * 224 * 384 * 4

C_COMMIT = "3846230a4f141a8a55084eeaaa040f9a10cfc408"
C_MEDIA_SHA256 = "a11762bd9292404b58ddccc062ebcf5115d935d61426fff4cd4474c8def257c9"
C_TO_A_SHA256 = "94c852466167db01a678d0d7d6a3ae6e3211abaef995f95b20f5d182ed599b3e"
C_TO_D_SHA256 = "84b5b927ab41d34d51ebf30f1af9d48cf1b5af9d057518a6ca6338cef7f38a56"
C_CANONICALIZER_SHA256 = (
    "cc80f6eb889ee7794786b26a81dea3647439a2cbc3e7f85235e0215bbd2c319a"
)
PRIOR_RUN_ID = "mineocclude-run-836009cb74647b413ebc6f40218bc5bf"

_spec = importlib.util.spec_from_file_location(
    "person_a_66_cell_preprocessed_media_builder", BUILDER_PATH
)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"Unable to load builder: {BUILDER_PATH}")
builder = importlib.util.module_from_spec(_spec)
sys.modules["person_a_66_cell_preprocessed_media_builder"] = builder
_spec.loader.exec_module(builder)


def _json(name: str) -> Any:
    return json.loads((STATUS_ROOT / name).read_bytes())


class PersonA66CellPreprocessedMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.binding = _json("authority_binding.json")
        cls.manifest = _json("preprocessed_frame_manifest.json")
        cls.boundary = _json("rgb_bgr_boundary_proof.json")
        cls.config = _json("successor_extraction_config.json")
        cls.queue = _json("successor_extraction_queue_state.json")
        cls.handoff = _json("a_to_d_frame_handoff.json")
        cls.transport = _json("byte_transport_plan.json")
        cls.preconditions = _json("phase6_precondition_receipt.json")
        cls.validation = _json("validation_receipt.json")
        cls.inventory = _json("sha256_inventory.json")
        cls.payload_root = Path(cls.manifest["external_payload_root"])

    # ------------------------------------------------------------------
    # Person C canonical-media intake
    # ------------------------------------------------------------------
    def test_01_c_canonical_media_authorities_verify(self) -> None:
        self.assertEqual(builder.verify_authorities(), builder.A_STARTING_AUTHORITY)
        for path, expected in (
            (builder.C_MEDIA_MANIFEST_PATH, C_MEDIA_SHA256),
            (builder.C_TO_A_HANDOFF_PATH, C_TO_A_SHA256),
            (builder.C_TO_D_HANDOFF_PATH, C_TO_D_SHA256),
            (builder.C_CANONICALIZER_PATH, C_CANONICALIZER_SHA256),
        ):
            with self.subTest(path=path):
                raw = builder._git_bytes(C_COMMIT, path)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), expected)

    def test_02_canonical_frame_index_is_exactly_the_a_universe(self) -> None:
        rows, sources = builder.load_canonical_frame_index()
        self.assertEqual(len(rows), EXPECTED_FRAMES)
        keys = [(row["trajectory_id"], row["model_frame_idx"]) for row in rows]
        self.assertEqual(len(set(keys)), EXPECTED_FRAMES)
        self.assertEqual(
            len({row["trajectory_id"] for row in rows}), EXPECTED_TRAJECTORIES
        )
        self.assertEqual(
            sources["canonical_media_manifest"]["canonical_media"]["frame_count"],
            EXPECTED_FRAMES,
        )

    def test_03_every_canonical_frame_is_640x360_rgb(self) -> None:
        rows, _sources = builder.load_canonical_frame_index()
        dimensions = Counter(
            (row["canonical_width"], row["canonical_height"]) for row in rows
        )
        self.assertEqual(dimensions, Counter({(640, 360): EXPECTED_FRAMES}))
        handoff = json.loads(
            builder._git_bytes(C_COMMIT, builder.C_TO_A_HANDOFF_PATH)
        )
        self.assertEqual(
            handoff["canonical_source_media"]["channel_order"], "RGB"
        )
        self.assertEqual(
            handoff["canonical_source_media"]["dimensions"], "640x360"
        )
        self.assertIs(
            handoff["canonical_source_media"]["mp4_is_not_the_pixel_authority"], True
        )

    def test_04_canonical_pixels_reproduce_person_e_hashes(self) -> None:
        rows, _sources = builder.load_canonical_frame_index()
        for row in rows:
            self.assertEqual(
                row["canonical_pixel_sha256"],
                row["person_e_canonical_frame_rgb_sha256"],
            )
            self.assertIs(row["person_e_pixel_hash_agrees"], True)

    def test_05_canonicalizer_identity_is_pinned_on_every_row(self) -> None:
        rows, _sources = builder.load_canonical_frame_index()
        versions = {row["canonicalization_implementation_sha256"] for row in rows}
        self.assertEqual(versions, {C_CANONICALIZER_SHA256})
        rules = {row["canonicalization_rule"] for row in rows}
        self.assertEqual(rules, {"mineocclude.data.preprocess.to_canonical"})

    def test_06_a_frame_map_raw_hashes_agree_with_c_index(self) -> None:
        rows, _sources = builder.load_canonical_frame_index()
        by_key = {
            (row["trajectory_id"], row["model_frame_idx"]): row["raw_source_sha256"]
            for row in rows
        }
        index = json.loads(
            builder.repository_bytes(
                f"{builder.A_FRAME_MAP_PACKAGE_REL}/frame_map_index.json"
            )
        )
        checked = 0
        for trajectory_id in index["per_trajectory"]:
            payload = (
                ROOT
                / builder.A_FRAME_MAP_PACKAGE_REL
                / "frame_maps"
                / f"{trajectory_id}.jsonl"
            ).read_bytes()
            for line in payload.decode("utf-8").splitlines():
                if not line.strip():
                    continue
                frame = json.loads(line)
                key = (frame["trajectory_id"], frame["model_frame_idx"])
                self.assertEqual(by_key[key], frame["source_frame_sha256"])
                checked += 1
        self.assertEqual(checked, EXPECTED_FRAMES)

    # ------------------------------------------------------------------
    # RGB / BGR boundary
    # ------------------------------------------------------------------
    def test_07_rgb_bgr_boundary_composes_to_identity(self) -> None:
        proof = self.boundary
        self.assertIs(proof["restores_true_rgb"], True)
        self.assertIs(proof["cv2_array_is_channel_reversed_true_rgb"], True)
        self.assertIs(proof["implementation_applies_bgr2rgb"], True)
        self.assertIs(proof["pre_swap_applied"], False)
        self.assertIs(proof["pre_swap_would_double_swap"], True)
        self.assertIs(proof["verified_on_real_canonical_pixels"], True)
        self.assertEqual(proof["pinned_source_shape_hwc"], [360, 640, 3])

    def test_08_boundary_proof_reproduces_on_a_real_frame(self) -> None:
        source = Path(self.boundary["probe_canonical_path"])
        if not source.is_file():
            self.skipTest("Person C canonical frames are not on this host")
        import cv2
        import numpy as np
        from PIL import Image

        png = source.read_bytes()
        self.assertEqual(
            hashlib.sha256(png).hexdigest(), self.boundary["probe_canonical_png_sha256"]
        )
        true_rgb = np.asarray(Image.open(source).convert("RGB"))
        self.assertEqual(
            hashlib.sha256(
                np.ascontiguousarray(true_rgb).tobytes(order="C")
            ).hexdigest(),
            self.boundary["probe_canonical_pixel_sha256"],
        )
        loaded = cv2.imread(str(source), cv2.IMREAD_COLOR)
        self.assertTrue(np.array_equal(loaded, true_rgb[:, :, ::-1]))
        self.assertTrue(
            np.array_equal(cv2.cvtColor(loaded, cv2.COLOR_BGR2RGB), true_rgb)
        )

    def test_09_implementation_identity_is_the_frozen_one(self) -> None:
        self.assertEqual(
            self.boundary["implementation_path"],
            "src/mineocclude/models/_mineworld_adapter_wave2.py",
        )
        self.assertEqual(
            hashlib.sha256(
                builder.repository_bytes(self.boundary["implementation_path"])
            ).hexdigest(),
            self.boundary["implementation_sha256"],
        )
        self.assertEqual(
            self.manifest["person_a_preprocessing"]["implementation_sha256"],
            self.boundary["implementation_sha256"],
        )

    # ------------------------------------------------------------------
    # Preprocessed frame manifest
    # ------------------------------------------------------------------
    def test_10_manifest_cardinality_is_exact(self) -> None:
        self.assertEqual(self.manifest["artifact_count"], EXPECTED_FRAMES)
        self.assertEqual(self.manifest["unique_frame_count"], EXPECTED_FRAMES)
        self.assertEqual(self.manifest["duplicate_frame_count"], 0)
        self.assertEqual(self.manifest["missing_frame_count"], 0)
        self.assertEqual(self.manifest["failure_count"], 0)
        self.assertEqual(self.manifest["trajectory_count"], EXPECTED_TRAJECTORIES)
        self.assertEqual(len(self.manifest["records"]), EXPECTED_FRAMES)
        self.assertEqual(
            sum(self.manifest["per_trajectory_frame_counts"].values()), EXPECTED_FRAMES
        )

    def test_11_model_facing_shape_and_dtype_are_frozen(self) -> None:
        contract = self.manifest["output_contract"]
        self.assertEqual(contract["shape"], [3, 224, 384])
        self.assertEqual(contract["height"], 224)
        self.assertEqual(contract["width"], 384)
        self.assertEqual(contract["dtype"], "float32")
        self.assertEqual(contract["layout"], "CHW")
        self.assertEqual(contract["color_order"], "RGB")
        self.assertEqual(contract["payload_byte_size"], PAYLOAD_BYTES)
        self.assertEqual(contract["value_range_inclusive"], [-1.0, 1.0])

    def test_12_every_record_carries_the_required_provenance(self) -> None:
        required = {
            "artifact_id",
            "trajectory_id",
            "model_frame_idx",
            "source_canonical_path",
            "source_canonical_pixel_sha256",
            "source_canonical_png_sha256",
            "preprocess_hash",
            "preprocessing_implementation_path",
            "preprocessing_implementation_sha256",
            "model_facing_height",
            "model_facing_width",
            "dtype",
            "output_path",
            "payload_sha256",
            "payload_byte_size",
            "transformation_identity",
            "fold_binding",
        }
        keys: set[tuple[str, int]] = set()
        for record in self.manifest["records"]:
            with self.subTest(artifact=record["artifact_id"]):
                self.assertTrue(required <= set(record))
                self.assertEqual(record["payload_byte_size"], PAYLOAD_BYTES)
                self.assertEqual(len(record["payload_sha256"]), 64)
                self.assertEqual(record["dtype"], "float32")
                self.assertEqual(record["model_facing_height"], 224)
                self.assertEqual(record["model_facing_width"], 384)
                self.assertIsInstance(record["fold_binding"]["fold_idx"], int)
            keys.add((record["trajectory_id"], record["model_frame_idx"]))
        self.assertEqual(len(keys), EXPECTED_FRAMES)

    def test_13_payload_hashes_are_unique_per_distinct_frame(self) -> None:
        payload_by_source: dict[str, set[str]] = {}
        for record in self.manifest["records"]:
            payload_by_source.setdefault(
                record["source_canonical_pixel_sha256"], set()
            ).add(record["payload_sha256"])
        for source_hash, payloads in payload_by_source.items():
            with self.subTest(source=source_hash):
                self.assertEqual(
                    len(payloads),
                    1,
                    "identical canonical pixels must preprocess to one payload",
                )

    def test_14_manifest_declares_no_mp4_pixel_source(self) -> None:
        self.assertIs(self.manifest["mp4_used_as_pixel_source"], False)
        self.assertIs(self.manifest["payloads_committed_to_git"], False)
        media = self.manifest["person_c_canonical_media"]
        self.assertEqual(media["commit"], C_COMMIT)
        self.assertEqual(media["manifest_sha256"], C_MEDIA_SHA256)
        self.assertEqual(media["canonical_dimensions"], "640x360")
        self.assertEqual(media["source_channel_order"], "RGB")
        serialized = json.dumps(self.manifest["records"][:50])
        self.assertNotIn(".mp4", serialized)

    def test_15_environment_provenance_is_recorded(self) -> None:
        provenance = self.manifest["environment_provenance"]
        for field in (
            "python_version",
            "opencv_version",
            "numpy_version",
            "pillow_version",
        ):
            with self.subTest(field=field):
                self.assertTrue(provenance[field])
        self.assertIs(
            provenance["cross_library_version_byte_determinism_claimed"], False
        )

    def test_16_payload_bytes_match_the_manifest_on_this_host(self) -> None:
        if not self.payload_root.is_dir():
            self.skipTest("external payload root is not on this host")
        sample = self.manifest["records"][:: max(1, EXPECTED_FRAMES // 40)]
        self.assertTrue(sample)
        for record in sample:
            with self.subTest(artifact=record["artifact_id"]):
                path = self.payload_root / record["output_path"]
                self.assertTrue(path.is_file(), str(path))
                payload = path.read_bytes()
                self.assertEqual(len(payload), record["payload_byte_size"])
                self.assertEqual(
                    hashlib.sha256(payload).hexdigest(), record["payload_sha256"]
                )

    def test_17_payload_files_exist_for_every_record(self) -> None:
        if not self.payload_root.is_dir():
            self.skipTest("external payload root is not on this host")
        missing = [
            record["output_path"]
            for record in self.manifest["records"]
            if not (self.payload_root / record["output_path"]).is_file()
        ]
        self.assertEqual(missing, [])

    # ------------------------------------------------------------------
    # Determinism
    # ------------------------------------------------------------------
    def test_18_recorded_determinism_receipt_is_clean(self) -> None:
        determinism = self.validation["determinism"]
        self.assertIs(determinism["pass"], True)
        self.assertEqual(determinism["mismatch_count"], 0)
        self.assertEqual(determinism["compared_output_count"], EXPECTED_FRAMES)
        self.assertEqual(determinism["regenerated_key_count"], EXPECTED_FRAMES)
        self.assertEqual(determinism["manifest_hash_mismatch_count"], 0)
        self.assertEqual(determinism["disk_payload_mismatch_count"], 0)
        self.assertEqual(determinism["missing_payload_count"], 0)
        self.assertIs(determinism["independent_regeneration_performed"], True)
        self.assertIs(
            determinism["cross_library_version_determinism_claimed"], False
        )

    def test_19_a_sample_regenerates_byte_identically(self) -> None:
        rows, _sources = builder.load_canonical_frame_index()
        probe = [row for row in rows if row["model_frame_idx"] == 0][:4]
        if not Path(probe[0]["canonical_path"]).is_file():
            self.skipTest("Person C canonical frames are not on this host")
        records, summary = builder.materialize_frames(probe, write_payloads=False)
        self.assertEqual(summary["failure_count"], 0)
        declared = {
            (r["trajectory_id"], r["model_frame_idx"]): r["payload_sha256"]
            for r in self.manifest["records"]
        }
        for record in records:
            key = (record["trajectory_id"], record["model_frame_idx"])
            with self.subTest(key=key):
                self.assertEqual(record["payload_sha256"], declared[key])

    # ------------------------------------------------------------------
    # Successor identity and queue
    # ------------------------------------------------------------------
    def test_20_prior_successor_did_not_bind_canonical_media(self) -> None:
        audit = self.binding["prior_successor_binding_audit"]
        self.assertIs(audit["binds_c_canonical_media_sha256"], False)
        self.assertIs(audit["binds_c_to_a_media_handoff_sha256"], False)
        self.assertIs(
            audit["binds_person_a_preprocessed_frame_manifest_sha256"], False
        )
        self.assertIs(audit["new_run_identity_required"], True)
        self.assertIs(audit["mutated_in_place"], False)
        self.assertEqual(audit["prior_run_id"], PRIOR_RUN_ID)
        self.assertEqual(
            hashlib.sha256(
                builder.repository_bytes(audit["prior_path"])
            ).hexdigest(),
            audit["prior_sha256"],
        )

    def test_21_successor_binds_the_canonical_source_authorities(self) -> None:
        inputs = self.config["inputs"]
        self.assertEqual(inputs["person_c_canonical_media_manifest_sha256"], C_MEDIA_SHA256)
        self.assertEqual(inputs["person_c_to_a_media_handoff_sha256"], C_TO_A_SHA256)
        self.assertEqual(inputs["person_c_canonicalizer_sha256"], C_CANONICALIZER_SHA256)
        self.assertEqual(
            inputs["person_a_preprocessed_frame_manifest_sha256"],
            hashlib.sha256(
                (STATUS_ROOT / "preprocessed_frame_manifest.json").read_bytes()
            ).hexdigest(),
        )
        for field in (
            "person_b_fold_manifest_sha256",
            "person_b_oracle_target_manifest_sha256",
            "person_b_row_universe_sha256",
            "person_c_accepted_manifest_sha256",
            "person_c_visibility_join_sha256",
            "person_c_event_table_sha256",
        ):
            with self.subTest(field=field):
                self.assertEqual(len(inputs[field]), 64)

    def test_22_successor_run_identity_is_new_and_reproducible(self) -> None:
        from mineocclude.experiments.mvp_lineage import make_run_id

        identity = self.config["successor_run_identity"]
        self.assertNotEqual(identity["run_id"], PRIOR_RUN_ID)
        self.assertEqual(identity["superseded_run_id"], PRIOR_RUN_ID)
        hashable = {
            key: value
            for key, value in self.config.items()
            if key != "successor_run_identity"
        }
        self.assertEqual(identity["config_hash"], builder._canonical_sha256(hashable))
        self.assertEqual(
            identity["run_id"],
            make_run_id(
                stage_id=identity["stage_id"],
                config_hash=identity["config_hash"],
                code_sha=identity["code_sha"],
                seed=self.config["seed"],
            ),
        )

    def test_23_successor_is_additive_and_rewrites_no_history(self) -> None:
        self.assertIs(self.config["additive_successor"], True)
        self.assertIs(self.config["historical_evidence_rewritten"], False)
        self.assertIs(self.config["person_a_mvp_yaml_modified"], False)
        predecessor = self.config["predecessor"]
        self.assertIs(predecessor["predecessor_evidence_rewritten"], False)
        self.assertTrue((ROOT / predecessor["path"]).is_file())
        prior = json.loads(builder.repository_bytes(predecessor["path"]))
        self.assertEqual(prior["successor_run_identity"]["run_id"], PRIOR_RUN_ID)

    def test_24_successor_keeps_the_float32_storage_contract(self) -> None:
        self.assertEqual(self.config["extraction"]["stored_dtype"], "float32")
        self.assertEqual(self.config["analysis_arithmetic_dtype"], "float64")
        self.assertEqual(self.config["extraction"]["layer_indices"], list(range(20)))
        self.assertIs(
            self.config["extraction"]["restricted_to_person_b_admitted_rows"], False
        )
        self.assertEqual(
            self.config["expected_activation_row_count"], EXPECTED_ROWS
        )
        self.assertEqual(self.config["expected_model_frame_key_count"], EXPECTED_FRAMES)
        self.assertIs(
            self.config["scientific_pixel_source"]["mp4_used_as_pixel_source"], False
        )

    def test_25_queue_matches_the_successor_identity_and_cardinality(self) -> None:
        items = self.queue["items"]
        self.assertEqual(len(items), EXPECTED_TRAJECTORIES)
        self.assertEqual(sum(item["frame_count"] for item in items), EXPECTED_FRAMES)
        self.assertEqual(
            sum(item["expected_activation_row_count"] for item in items), EXPECTED_ROWS
        )
        self.assertEqual(
            Counter(item["state"] for item in items),
            Counter({"pending": EXPECTED_TRAJECTORIES}),
        )
        for item in items:
            with self.subTest(item=item["item_id"]):
                self.assertIsNone(item["completion"])
                self.assertEqual(item["layer_count"], LAYER_COUNT)
        identity = self.queue["identity"]
        successor = self.config["successor_run_identity"]
        self.assertEqual(identity["run_id"], successor["run_id"])
        self.assertEqual(identity["config_hash"], successor["config_hash"])
        self.assertNotEqual(identity["run_id"], PRIOR_RUN_ID)

    # ------------------------------------------------------------------
    # Person D handoff
    # ------------------------------------------------------------------
    def test_26_a_to_d_handoff_is_ready_and_complete(self) -> None:
        self.assertIs(self.handoff["ready"], True)
        self.assertEqual(self.handoff["blocking_findings"], [])
        frames = self.handoff["person_a_preprocessed_frames"]
        self.assertEqual(frames["artifact_count"], EXPECTED_FRAMES)
        self.assertEqual(frames["duplicate_frame_count"], 0)
        self.assertEqual(frames["missing_frame_count"], 0)
        self.assertEqual(frames["failure_count"], 0)
        self.assertEqual(
            frames["manifest_sha256"],
            hashlib.sha256(
                (STATUS_ROOT / "preprocessed_frame_manifest.json").read_bytes()
            ).hexdigest(),
        )
        self.assertEqual(
            frames["manifest_schema_id"], "person-a-preprocessed-frame-manifest-v0.2"
        )
        self.assertIs(
            self.handoff["person_d_consumer_note"][
                "requires_another_person_a_data_artifact"
            ],
            False,
        )

    def test_27_handoff_carries_every_semantic_d_needs(self) -> None:
        for section in (
            "channel_order_semantics",
            "deterministic_producer_environment",
            "person_a_preprocessing_authority",
            "person_c_canonical_media",
            "person_c_to_d_media_handoff",
            "source_and_output_dimensions",
            "entry_point",
        ):
            with self.subTest(section=section):
                self.assertTrue(self.handoff[section])
        preprocessing = self.handoff["person_a_preprocessing_authority"]
        self.assertEqual(preprocessing["interpolation"], "cv2.INTER_LINEAR")
        self.assertEqual(preprocessing["colour_conversion"], "cv2.COLOR_BGR2RGB")
        self.assertEqual(preprocessing["scaling"], "uint8 / float32(255.0)")
        self.assertEqual(
            preprocessing["normalization"], "(x - 0.5) / 0.5 per channel"
        )
        self.assertEqual(preprocessing["source_shape_hwc"], [360, 640, 3])
        dimensions = self.handoff["source_and_output_dimensions"]
        self.assertEqual(dimensions["scientific_source_dimensions"], "640x360")
        self.assertEqual(dimensions["model_facing_width_by_height"], "384x224")
        self.assertEqual(
            self.handoff["person_c_to_d_media_handoff"]["sha256"], C_TO_D_SHA256
        )
        self.assertIs(
            self.handoff["channel_order_semantics"]["pre_swap_applied"], False
        )

    def test_28_handoff_supersedes_the_not_ready_predecessor(self) -> None:
        supersedes = self.handoff["supersedes"]
        self.assertIs(supersedes["predecessor_ready"], False)
        self.assertIs(supersedes["predecessor_evidence_rewritten"], False)
        prior = json.loads(builder.repository_bytes(supersedes["path"]))
        self.assertIs(prior["ready"], False)
        self.assertEqual(
            hashlib.sha256(
                builder.repository_bytes(supersedes["path"])
            ).hexdigest(),
            supersedes["predecessor_sha256"],
        )

    # ------------------------------------------------------------------
    # Transport and Phase 6
    # ------------------------------------------------------------------
    def test_29_transport_inventory_is_exact_and_unfabricated(self) -> None:
        self.assertIsNone(self.transport["approved_durable_destination"])
        self.assertIs(self.transport["byte_transport_destination_pending"], True)
        self.assertIs(self.transport["sagemaker_byte_access_ready"], False)
        self.assertIs(self.transport["destination_fabricated"], False)
        self.assertIs(
            self.transport["reinspection"]["object_store_destination_found"], False
        )
        sources = self.transport["local_sources"]
        self.assertEqual(sources["model_facing_payload_file_count"], EXPECTED_FRAMES)
        self.assertEqual(
            sources["model_facing_payload_byte_total"],
            EXPECTED_FRAMES * PAYLOAD_BYTES,
        )
        self.assertEqual(sources["canonical_png_file_count"], EXPECTED_FRAMES)
        self.assertGreater(sources["canonical_png_byte_total"], 0)
        self.assertEqual(
            self.transport["transfer_procedure"]["unfilled_placeholders"],
            ["<APPROVED_DESTINATION_URI>"],
        )
        self.assertTrue(self.transport["transfer_procedure"]["verification_command"])

    def test_30_transport_follows_the_frozen_extraction_input(self) -> None:
        requirement = self.transport["extraction_host_requirement"]
        self.assertIs(requirement["option_b_person_a_model_facing_payloads"], True)
        self.assertIs(requirement["option_a_canonical_pngs_and_preprocess_on_host"], False)
        self.assertEqual(requirement["chosen"], "person_a_model_facing_payloads")

    def test_31_phase6_layers_are_separate_and_media_blocker_is_resolved(self) -> None:
        receipt = self.preconditions
        self.assertIs(receipt["phase6_contract_preconditions_ready"], True)
        self.assertIs(receipt["phase6_runtime_infrastructure_ready"], False)
        self.assertIs(receipt["aggregate_phase6_runtime_authorized"], False)
        self.assertIs(receipt["aggregate_authorization_authority_present"], False)
        self.assertIs(receipt["self_authorizes_phase6"], False)
        self.assertIn(
            "C-66-CELL-640x360-MEDIA-MISSING",
            receipt["resolved_since_previous_assessment"],
        )
        media = [
            entry
            for entry in receipt["contract_conditions"]
            if entry["condition"]
            == "model_input_source_media_at_frozen_source_resolution"
        ]
        self.assertEqual(len(media), 1)
        self.assertIs(media[0]["satisfied"], True)
        self.assertEqual(
            receipt["phase6_contract_preconditions_ready"],
            all(entry["satisfied"] for entry in receipt["contract_conditions"]),
        )
        self.assertEqual(
            receipt["phase6_runtime_infrastructure_ready"],
            all(entry["satisfied"] for entry in receipt["infrastructure_conditions"]),
        )
        for entry in receipt["infrastructure_conditions"]:
            with self.subTest(condition=entry["condition"]):
                self.assertTrue(entry["owner"])

    def test_32_no_credential_value_is_published(self) -> None:
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
    # Package integrity
    # ------------------------------------------------------------------
    def test_33_protected_false_claims_hold(self) -> None:
        for path in sorted(STATUS_ROOT.glob("*.json")):
            with self.subTest(path=path.name):
                self.assertEqual(
                    builder._protected_false_violations(_json(path.name), path.name),
                    [],
                )

    def test_34_inventory_matches_the_committed_bytes(self) -> None:
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

    def test_35_validation_receipt_agrees_with_the_package(self) -> None:
        receipt = self.validation
        self.assertEqual(receipt["canonical_frame_count"], EXPECTED_FRAMES)
        self.assertEqual(receipt["canonical_hash_verified_count"], EXPECTED_FRAMES)
        self.assertEqual(receipt["preprocessed_frame_count"], EXPECTED_FRAMES)
        self.assertEqual(receipt["preprocessed_duplicate_count"], 0)
        self.assertEqual(receipt["preprocessed_missing_count"], 0)
        self.assertEqual(receipt["preprocessed_failure_count"], 0)
        self.assertIs(receipt["rgb_bgr_boundary_verified"], True)
        self.assertIs(receipt["successor_run_id_changed"], True)
        self.assertEqual(receipt["queue_trajectory_count"], EXPECTED_TRAJECTORIES)
        self.assertEqual(
            receipt["queue_expected_activation_row_count"], EXPECTED_ROWS
        )
        self.assertEqual(
            receipt["successor_run_id"],
            self.config["successor_run_identity"]["run_id"],
        )


if __name__ == "__main__":
    unittest.main()
