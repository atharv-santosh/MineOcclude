from __future__ import annotations

import unittest

from mineocclude.regime_a import RegimeAError, validate_capture_temporal_alignment


TICK_NANOS = 50_000_000


def streams(capture_offsets: list[int]) -> tuple[list[dict], list[dict]]:
    """Build joined server/client streams whose screenshots lag by the given offsets."""

    state = [
        {"server_tick": index, "server_epoch_nanos": index * TICK_NANOS}
        for index in range(len(capture_offsets))
    ]
    ticks = [
        {
            "server_tick": index,
            "render_frame_idx": index,
            "server_epoch_nanos": index * TICK_NANOS,
            "client_capture_nanos": index * TICK_NANOS + offset,
        }
        for index, offset in enumerate(capture_offsets)
    ]
    return state, ticks


class CaptureTemporalAlignmentTests(unittest.TestCase):
    def test_accepts_screenshots_taken_inside_their_own_tick(self) -> None:
        state, ticks = streams([1_000_000, 26_800_000, 49_999_999, 0])
        summary = validate_capture_temporal_alignment(state, ticks)
        self.assertEqual(summary["frame_count"], 4)
        self.assertEqual(summary["stale_frame_count"], 0)
        self.assertIsNone(summary["first_stale_frame_idx"])
        self.assertEqual(summary["capture_lag_nanos_max"], 49_999_999)

    def test_refuses_screenshot_taken_after_the_next_tick_was_emitted(self) -> None:
        state, ticks = streams([1_000_000, 60_000_000, 1_000_000, 0])
        with self.assertRaises(RegimeAError) as caught:
            validate_capture_temporal_alignment(state, ticks)
        self.assertIn("later tick", str(caught.exception))
        self.assertIn("frame 1", str(caught.exception))

    def test_refuses_the_multi_second_backlog_that_invalidated_t01(self) -> None:
        # Observed scientific t01 signature: ~1.07 s median screenshot lag, i.e.
        # every frame depicting a world roughly twenty ticks after its own row.
        state, ticks = streams([1_067_000_000] * 40)
        with self.assertRaises(RegimeAError) as caught:
            validate_capture_temporal_alignment(state, ticks)
        self.assertIn("frame 0", str(caught.exception))

    def test_refuses_screenshot_predating_its_own_tick(self) -> None:
        state, ticks = streams([1_000_000, -1, 1_000_000, 0])
        with self.assertRaises(RegimeAError) as caught:
            validate_capture_temporal_alignment(state, ticks)
        self.assertIn("captured before its own tick", str(caught.exception))

    def test_refuses_cross_stream_timestamp_join_mismatch(self) -> None:
        state, ticks = streams([1_000_000] * 4)
        state[2]["server_epoch_nanos"] += 1
        with self.assertRaises(RegimeAError) as caught:
            validate_capture_temporal_alignment(state, ticks)
        self.assertIn("timestamp join mismatch", str(caught.exception))

    def test_refuses_missing_or_nonintegral_timestamps(self) -> None:
        state, ticks = streams([1_000_000] * 3)
        ticks[1].pop("client_capture_nanos")
        with self.assertRaises(RegimeAError):
            validate_capture_temporal_alignment(state, ticks)
        state, ticks = streams([1_000_000] * 3)
        ticks[1]["client_capture_nanos"] = float(ticks[1]["client_capture_nanos"])
        with self.assertRaises(RegimeAError):
            validate_capture_temporal_alignment(state, ticks)

    def test_refuses_nonmonotonic_server_ticks(self) -> None:
        state, ticks = streams([1_000_000] * 4)
        state[2]["server_epoch_nanos"] = state[1]["server_epoch_nanos"]
        ticks[2]["server_epoch_nanos"] = ticks[1]["server_epoch_nanos"]
        with self.assertRaises(RegimeAError) as caught:
            validate_capture_temporal_alignment(state, ticks)
        self.assertIn("strictly increasing", str(caught.exception))

    def test_refuses_unequal_or_empty_streams(self) -> None:
        state, ticks = streams([1_000_000] * 3)
        with self.assertRaises(RegimeAError):
            validate_capture_temporal_alignment(state[:2], ticks)
        with self.assertRaises(RegimeAError):
            validate_capture_temporal_alignment([], [])


if __name__ == "__main__":
    unittest.main()
