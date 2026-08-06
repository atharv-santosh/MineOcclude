"""Steps 7.5 and 7.6 — resume safety, retry policy, and cardinality certification."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mineocclude.experiments.extraction_queue import (
    CompletionRecord,
    ExpectedKeys,
    ExtractionQueue,
    ItemState,
    QueueError,
    QueueErrorCode,
    QueueItem,
    build_queue_from_matrix,
    certify_queue_cardinality,
)

LAYERS = 20


def _queue(*, retries=3):
    return ExtractionQueue(
        run_id="mineocclude-run-test",
        config_hash="a" * 64,
        code_sha="b" * 40,
        accepted_manifest_sha256="c" * 64,
        max_transient_retries=retries,
    )


def _item(item_id="layout_00_ep1", frames=10):
    return QueueItem(
        item_id=item_id,
        expected=ExpectedKeys(
            trajectory_id=item_id, frame_count=frames, layer_count=LAYERS
        ),
        layout_id="layout_00",
        group="core_regime_a",
        input_manifest_sha256="d" * 64,
    )


def _completion(item, *, salt="0", seconds=12.5):
    rows = item.expected.expected_row_count
    return CompletionRecord(
        activation_index_sha256=f"{salt}e" + "0" * 62,
        activation_row_count=rows,
        chunk_count=LAYERS,
        chunk_sha256=tuple(f"{salt}{index:063d}" for index in range(LAYERS)),
        activation_bytes=rows * 8192,
        elapsed_seconds=seconds,
        completed_at="2026-08-06T00:00:00Z",
    )


class ExpectedKeyTests(unittest.TestCase):
    def test_expected_rows_are_frames_times_layers(self):
        keys = ExpectedKeys(trajectory_id="t", frame_count=248, layer_count=20)
        self.assertEqual(keys.expected_row_count, 4960)
        self.assertEqual(keys.expected_chunk_count, 20)
        self.assertEqual(len(keys.keys()), 4960)

    def test_invalid_cardinality_is_rejected(self):
        with self.assertRaises(QueueError):
            ExpectedKeys(trajectory_id="t", frame_count=0, layer_count=20)


class CompletionTests(unittest.TestCase):
    def test_completion_requires_exact_cardinality(self):
        queue = _queue()
        item = _item()
        queue.add(item)
        queue.mark_running(item.item_id)
        wrong = CompletionRecord(
            activation_index_sha256="e" * 64,
            activation_row_count=199,
            chunk_count=LAYERS,
            chunk_sha256=tuple(f"{i:064d}" for i in range(LAYERS)),
            activation_bytes=1,
            elapsed_seconds=1.0,
            completed_at="2026-08-06T00:00:00Z",
        )
        with self.assertRaises(QueueError) as caught:
            queue.complete(item.item_id, wrong)
        self.assertIs(caught.exception.code, QueueErrorCode.CARDINALITY_MISMATCH)

    def test_duplicate_completion_is_refused(self):
        queue = _queue()
        item = _item()
        queue.add(item)
        queue.mark_running(item.item_id)
        queue.complete(item.item_id, _completion(item))
        with self.assertRaises(QueueError) as caught:
            queue.complete(item.item_id, _completion(item))
        self.assertIs(caught.exception.code, QueueErrorCode.DUPLICATE_COMPLETION)

    def test_repeated_chunk_digests_within_one_completion_are_refused(self):
        queue = _queue()
        item = _item()
        queue.add(item)
        queue.mark_running(item.item_id)
        record = CompletionRecord(
            activation_index_sha256="e" * 64,
            activation_row_count=item.expected.expected_row_count,
            chunk_count=LAYERS,
            chunk_sha256=tuple("f" * 64 for _ in range(LAYERS)),
            activation_bytes=1,
            elapsed_seconds=1.0,
            completed_at="2026-08-06T00:00:00Z",
        )
        with self.assertRaises(QueueError) as caught:
            queue.complete(item.item_id, record)
        self.assertIs(caught.exception.code, QueueErrorCode.CHECKSUM_MISMATCH)

    def test_duplicate_item_is_refused(self):
        queue = _queue()
        queue.add(_item())
        with self.assertRaises(QueueError) as caught:
            queue.add(_item())
        self.assertIs(caught.exception.code, QueueErrorCode.DUPLICATE_ITEM)


class RetryAndQuarantineTests(unittest.TestCase):
    def test_transient_failure_returns_the_item_to_pending(self):
        queue = _queue()
        item = _item()
        queue.add(item)
        queue.mark_running(item.item_id)
        updated = queue.fail(
            item.item_id, failure_kind="host_oom", detail="container OOM"
        )
        self.assertIs(updated.state, ItemState.PENDING)
        self.assertEqual(len(updated.attempts), 1)

    def test_transient_retries_are_bounded(self):
        queue = _queue(retries=2)
        item = _item()
        queue.add(item)
        for _ in range(3):
            queue.mark_running(item.item_id)
            queue.fail(item.item_id, failure_kind="host_oom", detail="OOM")
        self.assertIs(queue.items[item.item_id].state, ItemState.QUARANTINED)
        self.assertIn("retry budget", queue.items[item.item_id].quarantine_reason)

    def test_identity_failure_quarantines_immediately(self):
        queue = _queue()
        item = _item()
        queue.add(item)
        queue.mark_running(item.item_id)
        updated = queue.fail(
            item.item_id,
            failure_kind="identity_failure",
            detail="input hash mismatch",
        )
        self.assertIs(updated.state, ItemState.QUARANTINED)

    def test_unclassified_failure_quarantines_rather_than_retrying(self):
        queue = _queue()
        item = _item()
        queue.add(item)
        queue.mark_running(item.item_id)
        updated = queue.fail(
            item.item_id, failure_kind="mystery", detail="unknown"
        )
        self.assertIs(updated.state, ItemState.QUARANTINED)

    def test_failed_attempts_are_never_deleted(self):
        queue = _queue()
        item = _item()
        queue.add(item)
        queue.mark_running(item.item_id)
        queue.fail(item.item_id, failure_kind="io_failure", detail="disk")
        queue.mark_running(item.item_id)
        queue.complete(item.item_id, _completion(item))
        document = queue.items[item.item_id].to_document()
        self.assertEqual(document["attempt_count"], 2)
        self.assertEqual(document["attempts"][0]["failure_kind"], "io_failure")


class ResumeTests(unittest.TestCase):
    def test_resume_skips_checksum_valid_work_without_duplicating_it(self):
        queue = _queue()
        first, second = _item("a", 5), _item("b", 6)
        queue.extend((first, second))
        queue.mark_running("a")
        queue.complete("a", _completion(first, salt="1"))

        report = queue.resume(verifier=lambda record: True)
        self.assertEqual(report["skipped_checksum_valid"], ["a"])
        self.assertIs(queue.items["a"].state, ItemState.COMPLETED)
        self.assertEqual(queue.next_pending().item_id, "b")

    def test_resume_reopens_an_interrupted_running_item(self):
        queue = _queue()
        item = _item("a", 5)
        queue.add(item)
        queue.mark_running("a")

        report = queue.resume(verifier=lambda record: True)
        self.assertEqual(report["reopened_interrupted"], ["a"])
        self.assertIs(queue.items["a"].state, ItemState.PENDING)

    def test_resume_reopens_work_whose_checksums_no_longer_verify(self):
        queue = _queue()
        item = _item("a", 5)
        queue.add(item)
        queue.mark_running("a")
        queue.complete("a", _completion(item))

        report = queue.resume(verifier=lambda record: False)
        self.assertEqual(report["reopened_checksum_invalid"], ["a"])
        self.assertIs(queue.items["a"].state, ItemState.PENDING)
        self.assertIsNone(queue.items["a"].completion)
        self.assertEqual(
            queue.items["a"].attempts[-1].failure_kind, "checksum_failure"
        )

    def test_resume_does_not_change_the_run_identity(self):
        queue = _queue()
        item = _item("a", 5)
        queue.add(item)
        before = queue.identity_digest()
        queue.mark_running("a")
        queue.complete("a", _completion(item))
        queue.resume(verifier=lambda record: True)
        self.assertEqual(queue.identity_digest(), before)


class PersistenceTests(unittest.TestCase):
    def test_round_trip_preserves_state_and_history(self):
        queue = _queue()
        first, second = _item("a", 5), _item("b", 6)
        queue.extend((first, second))
        queue.mark_running("a")
        queue.fail("a", failure_kind="host_oom", detail="OOM")
        queue.mark_running("a")
        queue.complete("a", _completion(first, salt="1"))

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.json"
            queue.save(path)
            reloaded = ExtractionQueue.load(path, expected_identity=queue.identity())

        self.assertEqual(reloaded.identity_digest(), queue.identity_digest())
        self.assertIs(reloaded.items["a"].state, ItemState.COMPLETED)
        self.assertEqual(len(reloaded.items["a"].attempts), 2)
        self.assertIs(reloaded.items["b"].state, ItemState.PENDING)

    def test_changed_run_identity_is_refused_on_load(self):
        queue = _queue()
        queue.add(_item("a", 5))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.json"
            queue.save(path)
            with self.assertRaises(QueueError) as caught:
                ExtractionQueue.load(
                    path,
                    expected_identity={**queue.identity(), "config_hash": "9" * 64},
                )
        self.assertIs(caught.exception.code, QueueErrorCode.RUN_IDENTITY_CHANGED)


class StatusAndForecastTests(unittest.TestCase):
    def test_status_reports_every_state_and_a_measured_forecast(self):
        queue = _queue()
        first, second = _item("a", 10), _item("b", 20)
        queue.extend((first, second))
        queue.mark_running("a")
        queue.complete("a", _completion(first, salt="1", seconds=20.0))

        status = queue.status()
        self.assertEqual(status["state_counts"]["completed"], 1)
        self.assertEqual(status["state_counts"]["pending"], 1)
        self.assertEqual(status["remaining_frame_count"], 20)
        self.assertAlmostEqual(status["forecast"]["seconds_per_frame"], 2.0)
        self.assertAlmostEqual(
            status["forecast"]["estimated_remaining_seconds"], 40.0
        )
        self.assertEqual(status["forecast"]["basis"], "measured_completed_items")

    def test_status_falls_back_to_prior_measured_rates(self):
        queue = _queue()
        queue.add(_item("a", 10))
        status = queue.status(forecast_basis={"seconds_per_frame": 1.5})
        self.assertEqual(status["forecast"]["basis"], "prior_measured_pilot_rates")
        self.assertAlmostEqual(
            status["forecast"]["estimated_remaining_seconds"], 15.0
        )


class CardinalityCertificationTests(unittest.TestCase):
    def test_incomplete_queue_publishes_an_exact_shortfall(self):
        queue = _queue()
        first, second = _item("a", 5), _item("b", 6)
        queue.extend((first, second))
        queue.mark_running("a")
        queue.complete("a", _completion(first, salt="1"))

        report = certify_queue_cardinality(
            queue, expected_cell_count=66, vector_width=2048, stored_dtype="float16"
        )
        self.assertFalse(report["complete"])
        self.assertEqual(report["completed_item_count"], 1)
        self.assertEqual(report["shortfall_item_count"], 1)
        self.assertEqual(report["missing_queue_item_count"], 64)
        self.assertEqual(report["critical_path_owner"], "person_c_data")
        self.assertTrue(report["pooled_storage_preserved_16_bit"])

    def test_complete_queue_certifies(self):
        queue = _queue()
        items = [_item(f"c{index}", 5) for index in range(3)]
        queue.extend(items)
        for index, item in enumerate(items):
            queue.mark_running(item.item_id)
            queue.complete(item.item_id, _completion(item, salt=str(index + 1)))

        report = certify_queue_cardinality(
            queue, expected_cell_count=3, vector_width=2048, stored_dtype="float16"
        )
        self.assertTrue(report["complete"])
        self.assertEqual(report["completed_activation_row_count"], 300)
        self.assertFalse(report["duplicate_activation_index_digest"])

    def test_shared_index_digest_across_items_is_refused(self):
        queue = _queue()
        items = [_item("a", 5), _item("b", 5)]
        queue.extend(items)
        for item in items:
            queue.mark_running(item.item_id)
            queue.complete(item.item_id, _completion(item, salt="1"))

        with self.assertRaises(QueueError) as caught:
            certify_queue_cardinality(
                queue,
                expected_cell_count=2,
                vector_width=2048,
                stored_dtype="float16",
            )
        self.assertIs(caught.exception.code, QueueErrorCode.CHECKSUM_MISMATCH)


class BuildFromMatrixTests(unittest.TestCase):
    def test_only_accepted_cells_are_queued(self):
        reconciliation = {
            "cells": [
                {
                    "cell_id": "layout_00_ep1",
                    "state": "accepted",
                    "layout_id": "layout_00",
                    "group": "core_regime_a",
                    "evidence_sha256": "d" * 64,
                },
                {
                    "cell_id": "layout_00_ep2",
                    "state": "missing",
                    "layout_id": "layout_00",
                    "group": "core_regime_a",
                },
            ]
        }
        queue = build_queue_from_matrix(
            reconciliation,
            run_id="r",
            config_hash="a" * 64,
            code_sha="b" * 40,
            accepted_manifest_sha256="c" * 64,
            layer_count=LAYERS,
            frame_counts={"layout_00_ep1": 100},
        )
        self.assertEqual(list(queue.items), ["layout_00_ep1"])
        self.assertEqual(
            queue.items["layout_00_ep1"].expected.expected_row_count, 2000
        )

    def test_accepted_cell_without_a_frame_count_is_refused(self):
        reconciliation = {
            "cells": [{"cell_id": "x", "state": "accepted", "layout_id": "l"}]
        }
        with self.assertRaises(QueueError) as caught:
            build_queue_from_matrix(
                reconciliation,
                run_id="r",
                config_hash="a" * 64,
                code_sha="b" * 40,
                accepted_manifest_sha256="c" * 64,
                layer_count=LAYERS,
                frame_counts={},
            )
        self.assertIs(caught.exception.code, QueueErrorCode.INVALID_REQUEST)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
