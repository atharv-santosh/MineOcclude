"""Step 7.2 — the 66-cell matrix is encoded and reconciled, never assumed."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mineocclude.experiments.mvp_matrix import (
    EXPECTED_CELL_COUNT,
    EXPECTED_GROUP_COUNTS,
    AcceptanceEvidence,
    CellState,
    MatrixError,
    MatrixErrorCode,
    acceptance_from_handoff_bundles,
    load_expected_matrix,
    parse_expected_matrix,
    reconcile_matrix,
)

ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = (
    ROOT
    / "data"
    / "handoff_a"
    / "person_c_mvp_expected_matrix_v0_1"
    / "episode_matrix.csv"
)
MATRIX_SHA256 = "016acbfdd65b8f77dba6ad7b4171fb95f7be4292d37d83269bc9e568627e4625"

HEADER = (
    "collection_order,set,scene,layout_id,v,q,hidden_frames,max_ticks,"
    "warmup_ticks,episode_id,seed"
)


def _row(order, set_name, layout, episode):
    return (
        f"{order},{set_name},normal,{layout},1.0,0.05,16,300,60,{episode},"
        f"{100000 + episode}"
    )


def _synthetic_matrix(counts=None):
    counts = counts or dict(EXPECTED_GROUP_COUNTS)
    inverse = {
        "core_regime_a": "core",
        "no_wall_visible_control": "nowall",
        "occluder_only_no_sheep_control": "nosheep",
        "context_sentinel": "sentinel",
    }
    lines = [HEADER]
    order = 0
    episode = 1000
    for group, count in counts.items():
        for _ in range(count):
            lines.append(
                _row(order, inverse[group], f"layout_{order % 6:02d}", episode)
            )
            order += 1
            episode += 1
    return "\n".join(lines) + "\n"


class ExpectedMatrixTests(unittest.TestCase):
    def test_person_c_matrix_encodes_exactly_sixty_six_cells(self):
        cells, digest = load_expected_matrix(
            MATRIX_PATH, expected_sha256=MATRIX_SHA256
        )
        self.assertEqual(len(cells), EXPECTED_CELL_COUNT)
        self.assertEqual(digest, MATRIX_SHA256)

    def test_group_counts_match_the_frozen_plan(self):
        cells, _ = load_expected_matrix(MATRIX_PATH)
        counts = {name: 0 for name in EXPECTED_GROUP_COUNTS}
        for cell in cells:
            counts[cell.group] += 1
        self.assertEqual(counts, dict(EXPECTED_GROUP_COUNTS))
        self.assertEqual(counts["core_regime_a"], 48)

    def test_every_cell_carries_its_full_condition_identity(self):
        cells, _ = load_expected_matrix(MATRIX_PATH)
        for cell in cells:
            document = cell.to_document()
            for field in (
                "layout_id",
                "v",
                "q",
                "hidden_frames",
                "seed",
                "episode_id",
                "group",
            ):
                self.assertIn(field, document)
                self.assertIsNotNone(document[field])

    def test_hash_mismatch_is_rejected(self):
        with self.assertRaises(MatrixError) as caught:
            load_expected_matrix(MATRIX_PATH, expected_sha256="0" * 64)
        self.assertIs(caught.exception.code, MatrixErrorCode.HASH_MISMATCH)

    def test_wrong_cardinality_is_rejected(self):
        counts = dict(EXPECTED_GROUP_COUNTS)
        counts["core_regime_a"] = 47
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "episode_matrix.csv"
            path.write_text(_synthetic_matrix(counts), encoding="utf-8")
            with self.assertRaises(MatrixError) as caught:
                load_expected_matrix(path)
        self.assertIs(caught.exception.code, MatrixErrorCode.CARDINALITY_MISMATCH)

    def test_wrong_group_split_is_rejected_even_at_the_right_total(self):
        counts = dict(EXPECTED_GROUP_COUNTS)
        counts["core_regime_a"] = 47
        counts["context_sentinel"] = 7
        self.assertEqual(sum(counts.values()), EXPECTED_CELL_COUNT)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "episode_matrix.csv"
            path.write_text(_synthetic_matrix(counts), encoding="utf-8")
            with self.assertRaises(MatrixError) as caught:
                load_expected_matrix(path)
        self.assertIs(caught.exception.code, MatrixErrorCode.CARDINALITY_MISMATCH)

    def test_unknown_collection_set_is_rejected(self):
        text = HEADER + "\n" + _row(0, "mystery", "layout_00", 1)
        with self.assertRaises(MatrixError) as caught:
            parse_expected_matrix(text + "\n")
        self.assertIs(caught.exception.code, MatrixErrorCode.UNKNOWN_SET)

    def test_duplicate_episode_is_rejected(self):
        text = "\n".join(
            [HEADER, _row(0, "core", "layout_00", 1), _row(1, "core", "layout_01", 1)]
        )
        with self.assertRaises(MatrixError) as caught:
            parse_expected_matrix(text + "\n")
        self.assertIs(caught.exception.code, MatrixErrorCode.DUPLICATE_CELL)


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.cells, _ = load_expected_matrix(MATRIX_PATH)

    def test_no_acceptance_leaves_every_cell_missing_with_an_owner(self):
        report = reconcile_matrix(self.cells, ())
        self.assertEqual(report["accepted_cell_count"], 0)
        self.assertEqual(report["shortfall_count"], EXPECTED_CELL_COUNT)
        self.assertEqual(report["shortfall_owners"], ["person_c_data"])
        self.assertTrue(report["every_cell_has_a_state_and_owner"])
        self.assertFalse(report["complete"])

    def test_partial_acceptance_publishes_an_exact_shortfall(self):
        accepted = acceptance_from_handoff_bundles(
            [
                {
                    "trajectory_id": self.cells[0].cell_id,
                    "bundle_manifest": "data/handoff_a/x/bundle_manifest.json",
                    "bundle_manifest_sha256": "a" * 64,
                }
            ]
        )
        report = reconcile_matrix(self.cells, accepted)
        self.assertEqual(report["accepted_cell_count"], 1)
        self.assertEqual(report["shortfall_count"], EXPECTED_CELL_COUNT - 1)
        self.assertTrue(report["no_data_invented"])

    def test_full_acceptance_is_reported_complete(self):
        accepted = acceptance_from_handoff_bundles(
            [
                {
                    "trajectory_id": cell.cell_id,
                    "bundle_manifest_sha256": "a" * 64,
                }
                for cell in self.cells
            ]
        )
        report = reconcile_matrix(self.cells, accepted)
        self.assertTrue(report["complete"])
        self.assertEqual(report["shortfall_count"], 0)
        self.assertEqual(
            report["accepted_group_counts"], dict(EXPECTED_GROUP_COUNTS)
        )

    def test_excluded_and_recollection_pending_states_are_supported(self):
        records = (
            AcceptanceEvidence(
                cell_id=self.cells[0].cell_id,
                state=CellState.EXCLUDED,
                owner="person_c_data",
                detail="capture failed acceptance validation",
            ),
            AcceptanceEvidence(
                cell_id=self.cells[1].cell_id,
                state=CellState.RECOLLECTION_PENDING,
                owner="person_c_data",
                detail="scheduled for recollection",
            ),
        )
        report = reconcile_matrix(self.cells, records)
        self.assertEqual(report["state_counts"]["excluded"], 1)
        self.assertEqual(report["state_counts"]["recollection_pending"], 1)
        self.assertEqual(report["shortfall_count"], EXPECTED_CELL_COUNT)

    def test_unplanned_accepted_cell_is_rejected(self):
        with self.assertRaises(MatrixError) as caught:
            reconcile_matrix(
                self.cells,
                (
                    AcceptanceEvidence(
                        cell_id="layout_99_ep99999",
                        state=CellState.ACCEPTED,
                        owner="person_c_data",
                    ),
                ),
            )
        self.assertIs(
            caught.exception.code, MatrixErrorCode.UNKNOWN_ACCEPTED_CELL
        )

    def test_duplicate_acceptance_record_is_rejected(self):
        record = AcceptanceEvidence(
            cell_id=self.cells[0].cell_id,
            state=CellState.ACCEPTED,
            owner="person_c_data",
        )
        with self.assertRaises(MatrixError) as caught:
            reconcile_matrix(self.cells, (record, record))
        self.assertIs(caught.exception.code, MatrixErrorCode.DUPLICATE_CELL)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
