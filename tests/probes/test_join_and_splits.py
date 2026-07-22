from __future__ import annotations

import copy
import json
import random
import unittest
from pathlib import Path

from mineocclude.contracts.identity import FRAME_KEY, REQUIRED_FIELDS
from mineocclude.oracle.targets import build_regime_a_target_document
from mineocclude.probes.join import ActivationTargetJoinError, join_activation_targets
from mineocclude.probes.splits import (
    GroupedSplitError,
    annotate_grouped_folds,
    assign_layout_grouped_folds,
)


ROOT = Path(__file__).resolve().parents[2]


class TestActivationTargetJoin(unittest.TestCase):
    def setUp(self) -> None:
        self.activation = json.loads(
            (
                ROOT
                / "tests"
                / "fixtures"
                / "activation"
                / "accepted_activation_handoff.json"
            ).read_text(encoding="utf-8")
        )
        # Build a non-scientific compatibility target directly from Person A's
        # frozen activation identities. This keeps the A fixture untouched
        # while proving that B consumes its exact keys and metadata.
        frames = {
            (row["trajectory_id"], row["model_frame_idx"]): row
            for row in self.activation["index_rows"]
        }
        true_positions = {0: 10.0, 1: 11.2, 2: 11.9}
        state_rows = []
        for row in sorted(frames.values(), key=lambda item: item["model_frame_idx"]):
            state_row = {field: row[field] for field in REQUIRED_FIELDS}
            state_row.update(
                {
                    "run_id": "synthetic_activation_compat_state_run_001",
                    "accepted_manifest_hash": row["accepted_manifest_hash"],
                    "observed_position_blocks": (
                        10.0 if row["visibility"] == "visible" else None
                    ),
                    "x_true_blocks": true_positions[row["model_frame_idx"]],
                    "synthetic": True,
                    "scientific_use": "forbidden",
                }
            )
            state_rows.append(state_row)
        state_document = {
            "schema_version": "1.0",
            "join_key": list(FRAME_KEY),
            "fixture_metadata": {
                "synthetic": True,
                "scientific_use": "forbidden",
            },
            "rows": state_rows,
        }
        self.targets = build_regime_a_target_document(
            state_document,
            oracle_run_id="synthetic_person_b_compat_run_001",
            oracle_code_sha="a" * 40,
            oracle_config_hash="b" * 64,
        )["rows"]

    def test_person_b_joins_all_layers_without_row_order(self) -> None:
        random.Random(7).shuffle(self.activation["index_rows"])
        random.Random(11).shuffle(self.targets)
        joined = join_activation_targets(self.activation, self.targets)
        self.assertEqual(len(joined), 6)
        self.assertEqual(
            {(item.target_row["model_frame_idx"]) for item in joined},
            {0, 1, 2},
        )
        self.assertEqual(
            {(item.activation_index_row["layer_idx"]) for item in joined},
            {5, 12},
        )

    def test_manifest_mismatch_fails_closed(self) -> None:
        bad_targets = copy.deepcopy(self.targets)
        bad_targets[0]["accepted_manifest_hash"] = "f" * 64
        with self.assertRaises(ActivationTargetJoinError):
            join_activation_targets(self.activation, bad_targets)

    def test_missing_target_fails_closed(self) -> None:
        with self.assertRaises(ActivationTargetJoinError):
            join_activation_targets(self.activation, self.targets[:-1])

    def test_partial_activation_run_cannot_enter_scientific_join(self) -> None:
        partial = copy.deepcopy(self.activation)
        partial["run_status"] = "partial"
        for row in partial["index_rows"]:
            row["run_status"] = "partial"
        with self.assertRaisesRegex(ActivationTargetJoinError, "completed"):
            join_activation_targets(partial, self.targets)

    def test_incomplete_layer_site_grid_fails_closed(self) -> None:
        uneven = copy.deepcopy(self.activation)
        uneven["index_rows"][-1]["hook_site"] = "alternate_residual_stream"
        with self.assertRaisesRegex(ActivationTargetJoinError, "layer/site grid"):
            join_activation_targets(uneven, self.targets)

    def test_source_metadata_mismatch_reports_values(self) -> None:
        mismatched = copy.deepcopy(self.activation)
        mismatched["index_rows"][0]["q"] = 0.75
        with self.assertRaisesRegex(ActivationTargetJoinError, "activation=0.75"):
            join_activation_targets(mismatched, self.targets)

    def test_duplicate_and_excluded_targets_fail_closed(self) -> None:
        with self.assertRaises(ActivationTargetJoinError):
            join_activation_targets(self.activation, [*self.targets, self.targets[0]])

        excluded = copy.deepcopy(self.targets)
        excluded[0]["status"] = "excluded"
        excluded[0]["exclusion_reason"] = "synthetic exclusion test"
        with self.assertRaisesRegex(ActivationTargetJoinError, "accepted targets"):
            join_activation_targets(self.activation, excluded)


class TestLayoutGroupedSplits(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [
            {
                "trajectory_id": f"trajectory_{layout}",
                "layout_id": layout,
                "model_frame_idx": index,
            }
            for layout, count in (
                ("layout_a", 8),
                ("layout_b", 7),
                ("layout_c", 6),
                ("layout_d", 5),
                ("layout_e", 4),
                ("layout_f", 3),
            )
            for index in range(count)
        ]

    def test_layouts_never_cross_folds(self) -> None:
        annotated = annotate_grouped_folds(self.rows)
        observed: dict[str, set[int]] = {}
        for row in annotated:
            observed.setdefault(row["layout_id"], set()).add(row["fold_idx"])
        self.assertTrue(all(len(folds) == 1 for folds in observed.values()))
        self.assertEqual(set().union(*observed.values()), {0, 1, 2, 3, 4})

    def test_assignment_is_deterministic_without_row_order(self) -> None:
        shuffled = list(reversed(self.rows))
        self.assertEqual(
            assign_layout_grouped_folds(self.rows),
            assign_layout_grouped_folds(shuffled),
        )

    def test_insufficient_layouts_fail(self) -> None:
        with self.assertRaises(GroupedSplitError):
            assign_layout_grouped_folds(self.rows[:8], n_splits=5)

    def test_trajectory_cannot_cross_layouts(self) -> None:
        invalid = copy.deepcopy(self.rows)
        invalid[-1]["trajectory_id"] = invalid[0]["trajectory_id"]
        invalid[-1]["model_frame_idx"] = 999
        with self.assertRaisesRegex(GroupedSplitError, "multiple layouts"):
            assign_layout_grouped_folds(invalid)

    def test_duplicate_frame_identity_is_rejected(self) -> None:
        with self.assertRaisesRegex(GroupedSplitError, "Duplicate model-frame"):
            assign_layout_grouped_folds([*self.rows, self.rows[0]])

    def test_existing_fold_is_preserved_or_rejected(self) -> None:
        annotated = annotate_grouped_folds(self.rows)
        self.assertEqual(annotate_grouped_folds(annotated), annotated)

        conflicting = copy.deepcopy(annotated)
        conflicting[0]["fold_idx"] = (conflicting[0]["fold_idx"] + 1) % 5
        with self.assertRaisesRegex(GroupedSplitError, "conflicts"):
            annotate_grouped_folds(conflicting)

    def test_nonaccepted_rows_are_rejected(self) -> None:
        invalid = copy.deepcopy(self.rows)
        invalid[0]["status"] = "excluded"
        with self.assertRaisesRegex(GroupedSplitError, "accepted rows"):
            assign_layout_grouped_folds(invalid)


if __name__ == "__main__":
    unittest.main()
