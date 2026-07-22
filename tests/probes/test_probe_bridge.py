"""End-to-end synthetic A-to-B fold/vector/OOF probe bridge tests."""

from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

from mineocclude.analysis.manifests import seal_artifact, validate_sealed_artifact
from mineocclude.contracts.identity import REQUIRED_FIELDS
from mineocclude.oracle.targets import build_regime_a_target_document
from mineocclude.probes.bridge import (
    ProbeBridgeError,
    ProbeBridgeRejectionCode,
    build_frame_fold_manifest,
    build_joined_frame_table,
    build_probe_ready_matrices,
    load_activation_vectors,
    propagate_frame_folds,
    run_ridge_oof_probe,
    validate_joined_frame_table,
)


ROOT = Path(__file__).resolve().parents[2]
ACTIVATION_DIR = ROOT / "tests" / "fixtures" / "activation"
MANIFEST_HASH = "e" * 64
TARGET_CODE_SHA = "a" * 40
TARGET_CONFIG_HASH = "b" * 64
LAYOUT_COUNT = 5


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def fixture_bytes(value) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def make_multilayout_a_b_fixture():
    """Expand A's real synthetic vectors across five non-scientific layouts."""

    source_package = load_json(
        ACTIVATION_DIR / "accepted_activation_handoff.json"
    )
    source_chunk_path = ACTIVATION_DIR / "synthetic_activation_chunk.json"
    source_chunk_bytes = source_chunk_path.read_bytes()
    source_chunk = json.loads(source_chunk_bytes)
    source_descriptor = source_package["chunks"][0]

    if hashlib.sha256(source_chunk_bytes).hexdigest() != source_descriptor["sha256"]:
        raise AssertionError("The checked A synthetic chunk hash is stale.")

    source_frame_rows = {}
    for row in source_package["index_rows"]:
        source_frame_rows.setdefault(row["model_frame_idx"], row)

    package = copy.deepcopy(source_package)
    package["handoff_id"] = "synthetic_probe_bridge_handoff_001"
    package["run_id"] = "synthetic_probe_bridge_activation_run_001"
    package["accepted_manifest_hash"] = MANIFEST_HASH
    package["source_fixture_lineage"] = {
        "handoff_id": source_package["handoff_id"],
        "accepted_manifest_hash": source_package["accepted_manifest_hash"],
        "synthetic": True,
        "scientific_use": "forbidden",
    }

    descriptors = []
    index_rows = []
    chunk_payloads = {}
    state_rows = []

    for layout_index in range(LAYOUT_COUNT):
        layout_id = f"synthetic_probe_layout_{layout_index:02d}"
        trajectory_id = f"synthetic_probe_trajectory_{layout_index:02d}"
        episode_id = f"synthetic_probe_episode_{layout_index:02d}"
        chunk_id = f"synthetic_probe_activation_chunk_{layout_index:02d}"

        chunk = copy.deepcopy(source_chunk)
        chunk["chunk_id"] = chunk_id
        payload = fixture_bytes(chunk)
        chunk_payloads[chunk_id] = payload

        descriptor = copy.deepcopy(source_descriptor)
        descriptor["chunk_id"] = chunk_id
        descriptor["path"] = f"not_used_as_identity_{layout_index:02d}.json"
        descriptor["sha256"] = hashlib.sha256(payload).hexdigest()
        descriptors.append(descriptor)

        for source_row in source_package["index_rows"]:
            row = copy.deepcopy(source_row)
            row.update(
                {
                    "episode_id": episode_id,
                    "trajectory_id": trajectory_id,
                    "layout_id": layout_id,
                    "run_id": package["run_id"],
                    "accepted_manifest_hash": MANIFEST_HASH,
                    "activation_chunk_id": chunk_id,
                }
            )
            index_rows.append(row)

        visible_anchor = 10.0 + (2.0 * layout_index)
        for model_frame_idx, source_row in sorted(source_frame_rows.items()):
            identity = dict(source_row)
            identity.update(
                {
                    "episode_id": episode_id,
                    "trajectory_id": trajectory_id,
                    "layout_id": layout_id,
                    "run_id": "synthetic_probe_bridge_state_run_001",
                    "accepted_manifest_hash": MANIFEST_HASH,
                }
            )
            state = {field: identity[field] for field in REQUIRED_FIELDS}
            state.update(
                {
                    "accepted_manifest_hash": MANIFEST_HASH,
                    "observed_position_blocks": (
                        visible_anchor
                        if source_row["visibility"] == "visible"
                        else None
                    ),
                    "x_true_blocks": visible_anchor + (0.04 * model_frame_idx),
                    "synthetic": True,
                    "scientific_use": "forbidden",
                }
            )
            state_rows.append(state)

    package["chunks"] = descriptors
    package["index_rows"] = index_rows
    package["cardinality_report"] = {
        "accepted_manifest_rows": LAYOUT_COUNT * 3,
        "expected_activation_rows": LAYOUT_COUNT * 6,
        "actual_activation_rows": LAYOUT_COUNT * 6,
        "expected_rows_by_layer": {
            "5": LAYOUT_COUNT * 3,
            "12": LAYOUT_COUNT * 3,
        },
        "actual_rows_by_layer": {
            "5": LAYOUT_COUNT * 3,
            "12": LAYOUT_COUNT * 3,
        },
    }

    state_document = {
        "schema_version": "1.0",
        "join_key": ["trajectory_id", "model_frame_idx"],
        "fixture_metadata": {
            "synthetic": True,
            "scientific_use": "forbidden",
        },
        "rows": state_rows,
    }
    target_document = build_regime_a_target_document(
        state_document,
        oracle_run_id="synthetic_probe_bridge_target_run_001",
        oracle_code_sha=TARGET_CODE_SHA,
        oracle_config_hash=TARGET_CONFIG_HASH,
    )
    return (
        package,
        target_document,
        chunk_payloads,
        source_package,
        source_chunk,
    )


class TestSyntheticProbeBridge(unittest.TestCase):
    """Prove the real A fixture vectors reach B's grouped OOF ridge path."""

    @classmethod
    def setUpClass(cls) -> None:
        (
            cls.activation,
            cls.targets,
            cls.chunk_payloads,
            cls.source_activation,
            cls.source_chunk,
        ) = make_multilayout_a_b_fixture()
        cls.frame_table = build_joined_frame_table(
            cls.activation,
            cls.targets,
        )
        cls.fold_manifest = build_frame_fold_manifest(
            cls.frame_table,
            artifact_id="synthetic_probe_bridge_folds_001",
        )
        cls.propagated = propagate_frame_folds(
            cls.activation,
            cls.targets,
            cls.frame_table,
            cls.fold_manifest,
        )
        cls.loaded_vectors = load_activation_vectors(
            cls.activation,
            cls.chunk_payloads,
        )
        cls.matrices = build_probe_ready_matrices(
            cls.propagated,
            cls.loaded_vectors,
        )

    def assert_bridge_code(self, expected, callable_, *args, **kwargs):
        with self.assertRaises(ProbeBridgeError) as raised:
            callable_(*args, **kwargs)
        self.assertEqual(raised.exception.code, expected)

    def test_a_handoff_and_b_targets_build_one_frame_row_per_key(self):
        validate_joined_frame_table(self.frame_table)
        self.assertEqual(self.frame_table["schema_version"], "1.0")
        self.assertEqual(len(self.frame_table["rows"]), LAYOUT_COUNT * 3)
        keys = {
            (row["trajectory_id"], row["model_frame_idx"])
            for row in self.frame_table["rows"]
        }
        self.assertEqual(len(keys), len(self.frame_table["rows"]))
        for row in self.frame_table["rows"]:
            for field in (
                "episode_id",
                "layout_id",
                "server_tick",
                "tau",
                "regime",
                "visibility",
                "v",
                "q",
                "duration",
                "mu_oracle_blocks",
                "accepted_manifest_hash",
                "activation_run_id",
                "target_run_id",
            ):
                self.assertIn(field, row)

    def test_frame_table_rejects_duplicate_and_inconsistent_source_rows(self):
        duplicate_targets = copy.deepcopy(self.targets)
        duplicate_targets["rows"].append(copy.deepcopy(duplicate_targets["rows"][0]))
        self.assert_bridge_code(
            ProbeBridgeRejectionCode.INVALID_JOIN,
            build_joined_frame_table,
            self.activation,
            duplicate_targets,
        )

        inconsistent_activation = copy.deepcopy(self.activation)
        inconsistent_activation["index_rows"][0]["tau"] = 0.15
        self.assert_bridge_code(
            ProbeBridgeRejectionCode.INVALID_JOIN,
            build_joined_frame_table,
            inconsistent_activation,
            self.targets,
        )

    def test_fold_assignment_propagates_to_every_layer_site_row(self):
        self.assertIs(self.fold_manifest["synthetic"], True)
        self.assertEqual(self.fold_manifest["scientific_use"], "forbidden")
        self.assertEqual(len(self.propagated), LAYOUT_COUNT * 6)
        folds_by_frame = {}
        layout_folds = {}
        for row in self.propagated:
            frame = (row["trajectory_id"], row["model_frame_idx"])
            folds_by_frame.setdefault(frame, set()).add(row["outer_fold_idx"])
            layout_folds.setdefault(row["layout_id"], set()).add(
                row["outer_fold_idx"]
            )
            self.assertEqual(
                row["fold_manifest_hash"],
                self.fold_manifest["artifact_hash"],
            )
            self.assertEqual(row["fold_version"], "person-b-fold-v0.1")
            self.assertEqual(row["fold_config_hash"], TARGET_CONFIG_HASH)
        self.assertTrue(all(len(folds) == 1 for folds in folds_by_frame.values()))
        self.assertTrue(all(len(folds) == 1 for folds in layout_folds.values()))
        self.assertEqual(
            set().union(*layout_folds.values()),
            {0, 1, 2, 3, 4},
        )

    def test_vectors_resolve_by_chunk_id_and_row_not_filename(self):
        package = copy.deepcopy(self.activation)
        for descriptor in package["chunks"]:
            descriptor["path"] = "a_filename_with_no_scientific_meaning.bin"
        loaded = load_activation_vectors(package, self.chunk_payloads)
        self.assertEqual(loaded, self.loaded_vectors)

        source_vectors = {
            row["chunk_row_idx"]: tuple(float(value) for value in row["vector"])
            for row in self.source_chunk["rows"]
        }
        for chunk_id in self.chunk_payloads:
            for row_idx, expected in source_vectors.items():
                self.assertEqual(loaded[(chunk_id, row_idx)], expected)

    def test_stale_chunk_hash_and_missing_chunk_row_fail_closed(self):
        stale = copy.deepcopy(self.activation)
        stale["chunks"][0]["sha256"] = "f" * 64
        self.assert_bridge_code(
            ProbeBridgeRejectionCode.CHUNK_HASH_MISMATCH,
            load_activation_vectors,
            stale,
            self.chunk_payloads,
        )

        missing_package = copy.deepcopy(self.activation)
        missing_payloads = dict(self.chunk_payloads)
        chunk_id = missing_package["chunks"][0]["chunk_id"]
        chunk = json.loads(missing_payloads[chunk_id])
        chunk["rows"] = chunk["rows"][:-1]
        payload = fixture_bytes(chunk)
        missing_payloads[chunk_id] = payload
        missing_package["chunks"][0]["sha256"] = hashlib.sha256(payload).hexdigest()
        self.assert_bridge_code(
            ProbeBridgeRejectionCode.MISSING_CHUNK_ROW,
            load_activation_vectors,
            missing_package,
            missing_payloads,
        )

        missing_payload = dict(self.chunk_payloads)
        del missing_payload[next(iter(sorted(missing_payload)))]
        self.assert_bridge_code(
            ProbeBridgeRejectionCode.MISSING_CHUNK,
            load_activation_vectors,
            self.activation,
            missing_payload,
        )

    def test_duplicate_chunk_claim_fails_closed(self):
        duplicate = copy.deepcopy(self.activation)
        duplicate["index_rows"][1]["chunk_row_idx"] = duplicate["index_rows"][0][
            "chunk_row_idx"
        ]
        self.assert_bridge_code(
            ProbeBridgeRejectionCode.DUPLICATE_CHUNK_ROW_CLAIM,
            load_activation_vectors,
            duplicate,
            self.chunk_payloads,
        )

    def test_duplicate_missing_stale_and_conflicting_folds_fail_closed(self):
        duplicate = copy.deepcopy(self.fold_manifest)
        duplicate["memberships"].append(copy.deepcopy(duplicate["memberships"][0]))
        self.assert_bridge_code(
            ProbeBridgeRejectionCode.DUPLICATE_FOLD_ASSIGNMENT,
            propagate_frame_folds,
            self.activation,
            self.targets,
            self.frame_table,
            duplicate,
        )

        missing = copy.deepcopy(self.fold_manifest)
        missing["memberships"] = missing["memberships"][:-1]
        self.assert_bridge_code(
            ProbeBridgeRejectionCode.MISSING_FOLD_ASSIGNMENT,
            propagate_frame_folds,
            self.activation,
            self.targets,
            self.frame_table,
            missing,
        )

        stale = dict(self.fold_manifest)
        del stale["artifact_hash"]
        stale["input_manifest_hash"] = "f" * 64
        stale = seal_artifact(stale)
        self.assert_bridge_code(
            ProbeBridgeRejectionCode.STALE_FOLD_MANIFEST,
            propagate_frame_folds,
            self.activation,
            self.targets,
            self.frame_table,
            stale,
        )

        stale_code = dict(self.fold_manifest)
        del stale_code["artifact_hash"]
        stale_code["code_sha"] = "c" * 40
        stale_code = seal_artifact(stale_code)
        self.assert_bridge_code(
            ProbeBridgeRejectionCode.STALE_FOLD_MANIFEST,
            propagate_frame_folds,
            self.activation,
            self.targets,
            self.frame_table,
            stale_code,
        )

        conflicting = copy.deepcopy(self.fold_manifest)
        layout = conflicting["memberships"][0]["layout_id"]
        same_layout = [
            row for row in conflicting["memberships"] if row["layout_id"] == layout
        ]
        same_layout[-1]["fold_idx"] = (same_layout[-1]["fold_idx"] + 1) % 5
        self.assert_bridge_code(
            ProbeBridgeRejectionCode.CONFLICTING_FOLD_ASSIGNMENT,
            propagate_frame_folds,
            self.activation,
            self.targets,
            self.frame_table,
            conflicting,
        )

    def test_row_order_shuffle_produces_identical_bridge_outputs(self):
        activation = copy.deepcopy(self.activation)
        targets = copy.deepcopy(self.targets)
        activation["index_rows"].reverse()
        activation["chunks"].reverse()
        targets["rows"].reverse()

        frame_table = build_joined_frame_table(activation, targets)
        fold_manifest = build_frame_fold_manifest(
            frame_table,
            artifact_id="synthetic_probe_bridge_folds_001",
        )
        propagated = propagate_frame_folds(
            activation,
            targets,
            frame_table,
            fold_manifest,
        )
        loaded = load_activation_vectors(activation, self.chunk_payloads)
        matrices = build_probe_ready_matrices(propagated, loaded)

        self.assertEqual(frame_table, self.frame_table)
        self.assertEqual(fold_manifest, self.fold_manifest)
        self.assertEqual(propagated, self.propagated)
        self.assertEqual(loaded, self.loaded_vectors)
        self.assertEqual(matrices, self.matrices)

    def test_matrix_builder_rejects_missing_target_grid_and_lifecycle(self):
        missing_target = [dict(row) for row in self.propagated]
        del missing_target[0]["mu_oracle_blocks"]
        self.assert_bridge_code(
            ProbeBridgeRejectionCode.MISSING_TARGET,
            build_probe_ready_matrices,
            missing_target,
            self.loaded_vectors,
        )

        incomplete = list(self.propagated[:-1])
        self.assert_bridge_code(
            ProbeBridgeRejectionCode.INCOMPLETE_LAYER_SITE_GRID,
            build_probe_ready_matrices,
            incomplete,
            self.loaded_vectors,
        )

        excluded = [dict(row) for row in self.propagated]
        excluded[0]["status"] = "excluded"
        self.assert_bridge_code(
            ProbeBridgeRejectionCode.INVALID_LIFECYCLE,
            build_probe_ready_matrices,
            excluded,
            self.loaded_vectors,
        )

    def test_oof_ridge_uses_real_vectors_and_propagated_folds(self):
        self.assertEqual(
            {(matrix.layer_idx, matrix.hook_site) for matrix in self.matrices},
            {(5, "residual_stream"), (12, "residual_stream")},
        )
        matrix = self.matrices[0]
        execution = run_ridge_oof_probe(
            matrix,
            artifact_id_prefix="synthetic_probe_bridge_layer_5",
        )

        self.assertEqual(len(execution.oof_result.predictions), LAYOUT_COUNT * 3)
        for fit in execution.oof_result.fits:
            self.assertTrue(
                all(
                    matrix.outer_folds[index] != fit.outer_fold_idx
                    for index in fit.training_indices
                )
            )
            self.assertTrue(
                all(
                    matrix.outer_folds[index] == fit.outer_fold_idx
                    for index in fit.test_indices
                )
            )
        prediction_rows = execution.prediction_artifact["rows"]
        expected = {
            (
                row["trajectory_id"],
                row["model_frame_idx"],
                row["layer_idx"],
                row["hook_site"],
            )
            for row in matrix.metadata_rows
        }
        observed = {
            (
                row["trajectory_id"],
                row["model_frame_idx"],
                row["layer_idx"],
                row["hook_site"],
            )
            for row in prediction_rows
        }
        self.assertEqual(observed, expected)
        self.assertTrue(
            all(row["prediction_scope"] == "out_of_fold" for row in prediction_rows)
        )
        validate_sealed_artifact(
            execution.prediction_artifact,
            expected_type="prediction_manifest",
        )
        validate_sealed_artifact(
            execution.u1_result_artifact,
            expected_type="result_manifest",
        )
        for artifact in (
            execution.prediction_artifact,
            execution.u1_result_artifact,
        ):
            self.assertIs(artifact["synthetic"], True)
            self.assertEqual(artifact["scientific_use"], "forbidden")
        self.assertEqual(
            execution.u1_result_artifact["prediction_manifest_hashes"],
            [execution.prediction_artifact["artifact_hash"]],
        )

        repeated = run_ridge_oof_probe(
            matrix,
            artifact_id_prefix="synthetic_probe_bridge_layer_5",
        )
        self.assertEqual(execution, repeated)

        malformed = copy.deepcopy(matrix)
        object.__setattr__(malformed, "metadata_rows", malformed.metadata_rows[:-1])
        self.assert_bridge_code(
            ProbeBridgeRejectionCode.PROBE_FIT_FAILED,
            run_ridge_oof_probe,
            malformed,
            artifact_id_prefix="synthetic_probe_bridge_bad_metadata",
        )

    def test_bridge_does_not_mutate_submitted_evidence(self):
        activation = copy.deepcopy(self.activation)
        targets = copy.deepcopy(self.targets)
        payloads = dict(self.chunk_payloads)
        originals = (copy.deepcopy(activation), copy.deepcopy(targets), dict(payloads))

        frame_table = build_joined_frame_table(activation, targets)
        fold_manifest = build_frame_fold_manifest(
            frame_table,
            artifact_id="synthetic_probe_bridge_nonmutation_folds",
        )
        propagated = propagate_frame_folds(
            activation,
            targets,
            frame_table,
            fold_manifest,
        )
        loaded = load_activation_vectors(activation, payloads)
        build_probe_ready_matrices(propagated, loaded)

        self.assertEqual(activation, originals[0])
        self.assertEqual(targets, originals[1])
        self.assertEqual(payloads, originals[2])


if __name__ == "__main__":
    unittest.main()
