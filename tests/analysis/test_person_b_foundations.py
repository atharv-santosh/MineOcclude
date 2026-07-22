from __future__ import annotations

import copy
import hashlib
import unittest

from mineocclude.analysis.config import (
    DEFAULT_CONFIG_PATH,
    hash_core_analysis_config,
)
from mineocclude.analysis.coordinates import (
    CoordinateContractError,
    coordinate_frame_hash,
    validate_coordinate_frame,
)
from mineocclude.analysis.filters import (
    FilterRejectionCode,
    apply_ordered_filters,
    build_filter_audit_artifact,
)
from mineocclude.analysis.manifests import (
    AnalysisArtifactError,
    seal_artifact,
    validate_sealed_artifact,
)
from mineocclude.analysis.outputs import (
    append_correction,
    build_prediction_artifact,
    build_result_artifact,
    create_correction_log,
)
from mineocclude.probes.splits import (
    GroupedSplitError,
    annotate_grouped_folds,
    assign_u4_development_partition,
    build_fold_manifest,
    build_grouped_inner_folds,
    build_u4_partition_manifest,
    validate_fold_manifest,
    validate_u4_partition_manifest,
)
from mineocclude.oracle.schema import OracleValidationError
from mineocclude.oracle.targets import build_regime_a_target_document


CODE_SHA = "a" * 40
CONFIG_HASH = "b" * 64
MANIFEST_HASH = "c" * 64


def coordinate_document() -> dict[str, object]:
    document: dict[str, object] = {
        "coordinate_frame_schema_version": "person-b-wall-parallel-frame-v0.1",
        "coordinate_frame_id": "wall_parallel_layout_frame_v1",
        "wall_parallel_origin_world_xyz": [10.0, 64.0, -2.0],
        "wall_parallel_positive_unit_vector_world_xyz": [0.0, 0.0, 1.0],
        "source_layout_manifest_hash": MANIFEST_HASH,
        "adapter_signoff": {"person_b": True, "person_c": True},
    }
    document["coordinate_frame_hash"] = coordinate_frame_hash(document)
    return document


class TestConfigAndCoordinates(unittest.TestCase):
    def test_config_hash_is_literal_validated_file_bytes(self) -> None:
        expected = hashlib.sha256(DEFAULT_CONFIG_PATH.read_bytes()).hexdigest()
        self.assertEqual(hash_core_analysis_config(), expected)

    def test_claim_bearing_builder_rejects_caller_supplied_hash(self) -> None:
        state_document = {
            "schema_version": "1.0",
            "join_key": ["trajectory_id", "model_frame_idx"],
            "coordinate_frame": coordinate_document(),
            "rows": [],
        }
        with self.assertRaisesRegex(OracleValidationError, "actual analysis config"):
            build_regime_a_target_document(
                state_document,
                oracle_run_id="run_v1",
                oracle_code_sha=CODE_SHA,
                oracle_config_hash="f" * 64,
            )

    def test_signed_wall_projection_is_explicit(self) -> None:
        frame = validate_coordinate_frame(coordinate_document())
        self.assertEqual(frame.project([10.0, 64.0, 3.0]), 5.0)
        self.assertEqual(frame.project([10.0, 64.0, -5.0]), -3.0)

    def test_coordinate_frame_requires_cross_role_signoff(self) -> None:
        unsigned = coordinate_document()
        unsigned["adapter_signoff"] = {"person_b": True, "person_c": False}
        with self.assertRaises(CoordinateContractError):
            validate_coordinate_frame(unsigned)


class TestOrderedFilters(unittest.TestCase):
    def test_filters_report_first_reason_and_step_counts(self) -> None:
        rows = [
            {
                "trajectory_id": "trajectory_1",
                "model_frame_idx": 0,
                "layout_id": "layout_1",
                "visibility": "occluded",
                "status": "accepted",
                "accepted_manifest_hash": MANIFEST_HASH,
                "tau": 0.05,
                "v": 1.0,
                "q": 0.1,
                "duration": 1.0,
            },
            {
                "trajectory_id": "trajectory_1",
                "model_frame_idx": 1,
                "layout_id": "layout_1",
                "visibility": "visible",
                "status": "accepted",
                "accepted_manifest_hash": MANIFEST_HASH,
                "tau": 0.0,
                "v": 1.0,
                "q": 0.1,
                "duration": 1.0,
            },
            {
                "trajectory_id": "trajectory_1",
                "model_frame_idx": 2,
                "layout_id": "layout_1",
                "visibility": "occluded",
                "status": "accepted",
                "accepted_manifest_hash": MANIFEST_HASH,
                "tau": 0.05,
                "v": 1.0,
                "q": 0.1,
                "duration": 1.0,
            },
            {
                "trajectory_id": "trajectory_2",
                "model_frame_idx": 0,
                "layout_id": "layout_2",
                "visibility": "visible",
                "status": "excluded",
                "accepted_manifest_hash": MANIFEST_HASH,
                "tau": 0.0,
                "v": 1.0,
                "q": 0.1,
                "duration": 1.0,
            },
        ]
        result = apply_ordered_filters(
            rows, accepted_manifest_hash=MANIFEST_HASH
        )
        self.assertEqual(result.accepted_count, 2)
        self.assertEqual(
            {rejection.code for rejection in result.rejections},
            {
                FilterRejectionCode.PRE_FIRST_SEEN,
                FilterRejectionCode.LIFECYCLE_NOT_ACCEPTED,
            },
        )
        self.assertEqual(result.steps[-1].output_count, 2)
        audit = build_filter_audit_artifact(
            result,
            artifact_id="filter_audit_v1",
            code_sha=CODE_SHA,
            config_hash=CONFIG_HASH,
            input_manifest_hash=MANIFEST_HASH,
        )
        validate_sealed_artifact(audit, expected_type="filter_audit")
        self.assertEqual(audit["accepted_count"], 2)

    def test_wrong_manifest_visible_row_cannot_anchor_occluded_row(self) -> None:
        rows = [
            {
                "trajectory_id": "trajectory_1",
                "model_frame_idx": model_frame_idx,
                "layout_id": "layout_1",
                "visibility": visibility,
                "status": "accepted",
                "accepted_manifest_hash": manifest_hash,
                "tau": tau,
                "v": 1.0,
                "q": 0.1,
                "duration": 1.0,
            }
            for model_frame_idx, visibility, manifest_hash, tau in (
                (0, "visible", "d" * 64, 0.0),
                (1, "occluded", MANIFEST_HASH, 0.05),
            )
        ]
        original = copy.deepcopy(rows)

        result = apply_ordered_filters(
            rows,
            accepted_manifest_hash=MANIFEST_HASH,
        )

        self.assertEqual(result.accepted_count, 0)
        self.assertEqual(
            [rejection.code for rejection in result.rejections],
            [
                FilterRejectionCode.ACCEPTED_MANIFEST_MISMATCH,
                FilterRejectionCode.NO_VISIBLE_ANCHOR,
            ],
        )
        self.assertEqual(
            [step.step for step in result.steps][-2:],
            ["accepted_manifest_match", "post_first_seen"],
        )
        self.assertEqual(rows, original)


class TestFoldAndCorrectionArtifacts(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [
            {
                "trajectory_id": f"trajectory_{layout}",
                "layout_id": layout,
                "model_frame_idx": frame,
            }
            for layout in "abcdef"
            for frame in range(2)
        ]

    def test_fold_manifest_is_tamper_evident_and_supports_inner_folds(self) -> None:
        manifest = build_fold_manifest(
            self.rows,
            artifact_id="fold_manifest_v1",
            code_sha=CODE_SHA,
            config_hash=hash_core_analysis_config(DEFAULT_CONFIG_PATH),
            input_manifest_hash=MANIFEST_HASH,
        )
        validate_fold_manifest(manifest)
        altered = copy.deepcopy(manifest)
        altered["memberships"][0]["fold_idx"] = 4
        with self.assertRaises(GroupedSplitError):
            validate_fold_manifest(altered)

        resealed_alternative = copy.deepcopy(manifest)
        resealed_alternative.pop("artifact_hash")
        for membership in resealed_alternative["memberships"]:
            if membership["fold_idx"] in {0, 1}:
                membership["fold_idx"] = 1 - membership["fold_idx"]
        for assignment in resealed_alternative["layout_assignments"]:
            if assignment["fold_idx"] in {0, 1}:
                assignment["fold_idx"] = 1 - assignment["fold_idx"]
        resealed_alternative = seal_artifact(resealed_alternative)
        with self.assertRaises(GroupedSplitError):
            validate_fold_manifest(resealed_alternative)

        with self.assertRaises(GroupedSplitError):
            build_fold_manifest(
                self.rows,
                artifact_id="fold_manifest_wrong_config",
                code_sha=CODE_SHA,
                config_hash=CONFIG_HASH,
                input_manifest_hash=MANIFEST_HASH,
            )

        annotated = annotate_grouped_folds(self.rows)
        inner = build_grouped_inner_folds(annotated, outer_fold_idx=0)
        self.assertNotIn(0, {row["fold_idx"] for row in inner})
        self.assertEqual({row["inner_fold_idx"] for row in inner}, {0, 1, 2, 3})

    def test_u4_partition_is_fixed_from_layout_identity_only(self) -> None:
        partition = assign_u4_development_partition(list("abcdef"))
        self.assertEqual(list(partition.values()).count("fit"), 3)
        self.assertEqual(list(partition.values()).count("validation"), 1)
        self.assertEqual(list(partition.values()).count("test"), 2)
        self.assertEqual(
            partition,
            assign_u4_development_partition(list(reversed("abcdef"))),
        )
        manifest = build_u4_partition_manifest(
            list("abcdef"),
            artifact_id="u4_partition_v1",
            code_sha=CODE_SHA,
            config_hash=CONFIG_HASH,
            input_manifest_hash=MANIFEST_HASH,
        )
        validate_u4_partition_manifest(manifest)
        altered = copy.deepcopy(manifest)
        altered["layout_assignments"][0]["partition"] = "test"
        with self.assertRaises(GroupedSplitError):
            validate_u4_partition_manifest(altered)

    def test_correction_log_is_hash_chained(self) -> None:
        log = create_correction_log(
            artifact_id="person_b_corrections",
            code_sha=CODE_SHA,
            config_hash=CONFIG_HASH,
            input_manifest_hash=MANIFEST_HASH,
        )
        updated = append_correction(
            log,
            {
                "correction_id": "correction_001",
                "affected_artifact_hash": "d" * 64,
                "reason": "Incorrect metadata discovered during audit.",
                "resolution": "Invalidate the artifact and require a new run.",
                "requires_new_run": True,
                "approved_by_roles": ["person_b"],
            },
        )
        self.assertEqual(updated["previous_log_hash"], log["artifact_hash"])
        validate_sealed_artifact(updated, expected_type="correction_log")
        tampered = copy.deepcopy(updated)
        tampered["corrections"][0]["reason"] = "changed"
        with self.assertRaises(AnalysisArtifactError):
            validate_sealed_artifact(tampered)

    def test_prediction_and_result_artifacts_lock_provenance(self) -> None:
        prediction = build_prediction_artifact(
            [
                {
                    "trajectory_id": "trajectory_a",
                    "model_frame_idx": 0,
                    "layout_id": "a",
                    "fold_idx": 0,
                    "prediction": 1.25,
                    "fit_id": "ridge_fold_0",
                    "prediction_scope": "out_of_fold",
                }
            ],
            artifact_id="prediction_v1",
            code_sha=CODE_SHA,
            config_hash=CONFIG_HASH,
            input_manifest_hash=MANIFEST_HASH,
            fold_manifest_hash="d" * 64,
            model_family="ridge",
            target_name="mu_oracle_blocks",
            layer_idx=10,
            hook_site="residual_stream",
        )
        result = build_result_artifact(
            [
                {
                    "metric_id": "u1_r2_overall",
                    "metric_name": "r2",
                    "value": 0.5,
                    "unit": "dimensionless",
                    "sample_count": 1,
                    "sample_unit": "frame",
                    "status": "valid",
                    "diagnostic": None,
                }
            ],
            artifact_id="u1_results_v1",
            code_sha=CODE_SHA,
            config_hash=CONFIG_HASH,
            input_manifest_hash=MANIFEST_HASH,
            fold_manifest_hash="d" * 64,
            prediction_manifest_hashes=[prediction["artifact_hash"]],
            analysis_family="U1",
        )
        validate_sealed_artifact(prediction, expected_type="prediction_manifest")
        validate_sealed_artifact(result, expected_type="result_manifest")


if __name__ == "__main__":
    unittest.main()
