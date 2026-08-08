"""Tests for Person E's sub-pixel ground-marker detector.

Frames are painted here as nested RGB lists whose correct marker centre is known
by construction.  Every expected centroid is written out as closed-form
arithmetic in the test and never obtained by calling the detector's internals, so
a sign error in :mod:`mineocclude.vision.markers` cannot be cancelled out by the
same error here.

Partially covered edge pixels are built by mixing the pure marker colour into the
background at an exact coverage fraction.  The two colours are chosen so that
every channel of their difference is divisible by five; mixing at a coverage of
0.6 therefore lands on whole 0-255 channel values, the detector recovers that
coverage exactly rather than approximately, and the expected centre is a ratio of
small integers.

Two guards in the detector are unreachable through its public interface, so they
are deliberately left unexercised rather than faked.  The empty-ring guard
("fills its neighbourhood") needs the dilated band to equal the core, which means
the marker fills the whole frame -- and the border guard rejects that first.  The
zero-total-coverage guard cannot fire while any core pixel projects to a coverage
of one.  Both stay in place as defence in depth.
"""

from __future__ import annotations

import unittest

from mineocclude.vision.markers import (
    MARKER_COLOUR_GATES,
    MARKER_DETECTOR_VERSION,
    MarkerDetectionError,
    detect_layout_markers,
    detect_marker_point,
)


#: Grass.  Rejected by all four marker gates, so it is a safe neutral backdrop.
BACKGROUND = (60, 110, 40)

#: The yellow marker used for the geometric fixtures.  Its difference from
#: ``BACKGROUND`` is ``(190, 100, -40)``; every channel is divisible by five, so
#: a 0.6 coverage blend has whole-numbered channels.
MARKER = (250, 210, 0)

#: Coverage fraction of the partially covered edge column in the sub-pixel test.
BLEND_ALPHA = 0.6

#: ``BACKGROUND`` mixed with ``MARKER`` at ``BLEND_ALPHA``.  Asserted to be an
#: exact mixture by :meth:`TestMarkerFixtures.test_the_edge_blend_is_exact`.
BLEND = (174, 170, 16)

#: The solid marker core shared by the geometric fixtures.
CORE_COLUMNS = (8, 9, 10, 11, 12)
CORE_ROWS = (8, 9, 10, 11, 12)

#: The partially covered column added immediately right of the core.
EDGE_COLUMN = 13

#: Each marker colour with the scenery it competes against in real captures, and
#: the gate bound that does the separating.  These pairs are what the gates were
#: selected against on Person C's calibration-split no-sheep frames.
COLOUR_SCENERY_CASES = (
    ("yellow", (250, 210, 0), "sand", (219, 207, 163), "saturation floor"),
    ("blue", (53, 57, 157), "bright sky", (85, 91, 250), "value ceiling"),
    ("lime", (106, 190, 48), "shadowed grass", (60, 107, 33), "value floor"),
    ("white", (245, 240, 236), "horizon blend", (149, 170, 180), "saturation ceiling"),
)

#: The white marker and the horizon row it must be told apart from, measured on
#: Person C's calibration frames.  See
#: :meth:`TestMarkerGates.test_white_saturation_ceiling_excludes_the_horizon`.
WHITE_MARKER = (245, 240, 236)
HORIZON_BLEND = (149, 170, 180)

#: The saturation ceiling this detector replaced.  Kept only so the regression
#: test can show the horizon used to slip through it.
SUPERSEDED_WHITE_SATURATION_CEILING = 0.18


def _saturation(rgb: tuple[int, int, int]) -> float:
    """Saturation of one RGB triple, reimplemented independently of the module."""

    high = max(rgb)
    low = min(rgb)
    return 0.0 if high == 0 else (high - low) / high


def _frame(
    width: int, height: int, colour: tuple[int, int, int] = BACKGROUND
) -> list[list[list[int]]]:
    return [[list(colour) for _ in range(width)] for _ in range(height)]


def _paint(
    frame: list[list[list[int]]],
    columns: range | tuple[int, ...],
    rows: range | tuple[int, ...],
    colour: tuple[int, int, int],
) -> None:
    for y in rows:
        for x in columns:
            frame[y][x] = list(colour)


def _solid_marker_frame() -> list[list[list[int]]]:
    """A 5x5 marker centred on (10, 10), every pixel fully covered."""

    frame = _frame(21, 21)
    _paint(frame, CORE_COLUMNS, CORE_ROWS, MARKER)
    return frame


def _half_covered_edge_frame() -> list[list[list[int]]]:
    """The solid marker plus one column covered at :data:`BLEND_ALPHA`."""

    frame = _solid_marker_frame()
    _paint(frame, (EDGE_COLUMN,), CORE_ROWS, BLEND)
    return frame


def _indistinguishable_background_frame() -> list[list[list[int]]]:
    """A marker whose only background sample is the marker colour itself.

    The detector samples background from the ring two pixels out from the core.
    Painting exactly that ring in the marker colour leaves nothing to unmix
    against.  The ring is 56 pixels against a 121-pixel core, which stays under
    the ambiguity threshold, so the degenerate-difference guard is what fires.
    """

    frame = _frame(21, 21)
    _paint(frame, range(5, 16), range(5, 16), MARKER)
    for y in range(3, 18):
        for x in range(3, 18):
            if x in (3, 17) or y in (3, 17):
                frame[y][x] = list(MARKER)
    return frame


class TestMarkerFixtures(unittest.TestCase):
    def test_the_edge_blend_is_exact(self) -> None:
        """The blend must be a whole-numbered mixture, or the test is fiction."""

        for channel, (background, marker, blend) in enumerate(
            zip(BACKGROUND, MARKER, BLEND)
        ):
            with self.subTest(channel=channel):
                self.assertEqual(
                    background + BLEND_ALPHA * (marker - background), float(blend)
                )

    def test_the_detector_version_is_declared(self) -> None:
        self.assertEqual(MARKER_DETECTOR_VERSION, "person-e-marker-detect-v1.0")


class TestMarkerCentroid(unittest.TestCase):
    def test_a_fully_covered_blob_lands_on_its_geometric_centre(self) -> None:
        result = detect_marker_point(_solid_marker_frame(), "yellow")

        self.assertAlmostEqual(result["image_xy"][0], 10.0, places=9)
        self.assertAlmostEqual(result["image_xy"][1], 10.0, places=9)
        self.assertEqual(result["core_pixels"], len(CORE_COLUMNS) * len(CORE_ROWS))
        self.assertAlmostEqual(result["alpha_sum"], 25.0, places=9)
        self.assertAlmostEqual(result["hard_centroid_offset_px"], 0.0, places=9)
        self.assertEqual(result["pure_rgb"], list(MARKER))
        self.assertEqual(result["background_rgb"], list(BACKGROUND))

    def test_partial_coverage_is_recovered_from_colour_alone(self) -> None:
        """The blended column must weigh exactly its coverage, not zero or one."""

        solid = detect_marker_point(_solid_marker_frame(), "yellow")
        blended = detect_marker_point(_half_covered_edge_frame(), "yellow")

        expected_alpha_sum = len(CORE_ROWS) * (len(CORE_COLUMNS) + BLEND_ALPHA)
        self.assertAlmostEqual(blended["alpha_sum"], expected_alpha_sum, places=9)
        self.assertAlmostEqual(
            blended["alpha_sum"] - solid["alpha_sum"],
            len(CORE_ROWS) * BLEND_ALPHA,
            places=9,
        )

    def test_sub_pixel_centre_beats_a_hard_threshold_on_a_covered_edge(self) -> None:
        """A hard threshold counts the 0.6 column in full and overshoots.

        Both centres are derived here from first principles.  The sub-pixel
        answer weighs the edge column by its coverage; the hard threshold takes
        every pixel at or above half coverage at full weight, which drags the
        centre a known distance to the right.
        """

        weighted_columns = len(CORE_ROWS) * (
            sum(CORE_COLUMNS) + EDGE_COLUMN * BLEND_ALPHA
        )
        total_coverage = len(CORE_ROWS) * (len(CORE_COLUMNS) + BLEND_ALPHA)
        expected_x = weighted_columns / total_coverage

        counted = len(CORE_ROWS) * (len(CORE_COLUMNS) + 1)
        expected_hard_x = (
            len(CORE_ROWS) * (sum(CORE_COLUMNS) + EDGE_COLUMN)
        ) / counted

        result = detect_marker_point(_half_covered_edge_frame(), "yellow")

        self.assertAlmostEqual(result["image_xy"][0], expected_x, places=9)
        self.assertAlmostEqual(result["image_xy"][1], 10.0, places=9)
        self.assertAlmostEqual(expected_x, 289 / 28, places=12)
        self.assertAlmostEqual(expected_hard_x, 10.5, places=12)
        self.assertAlmostEqual(
            result["hard_centroid_offset_px"], expected_hard_x - expected_x, places=9
        )
        self.assertGreater(result["hard_centroid_offset_px"], 0.17)
        self.assertEqual(result["core_pixels"], counted)

    def test_the_blended_column_does_not_disturb_the_sampled_colours(self) -> None:
        """Pure comes from the eroded core, background from two pixels out."""

        result = detect_marker_point(_half_covered_edge_frame(), "yellow")

        self.assertEqual(result["pure_rgb"], list(MARKER))
        self.assertEqual(result["background_rgb"], list(BACKGROUND))

    def test_repeated_detection_is_bit_identical(self) -> None:
        """Marker points feed provenance records, so they must not drift."""

        results = [
            detect_marker_point(_half_covered_edge_frame(), "yellow")["image_xy"]
            for _ in range(3)
        ]
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[1], results[2])


class TestMarkerGates(unittest.TestCase):
    def test_each_gate_separates_its_marker_from_its_scenery(self) -> None:
        """One marker on a full frame of the scenery it competes with."""

        for colour, marker, scenery_name, scenery, bound in COLOUR_SCENERY_CASES:
            with self.subTest(colour=colour, scenery=scenery_name, bound=bound):
                frame = _frame(21, 21, scenery)
                _paint(frame, CORE_COLUMNS, CORE_ROWS, marker)
                result = detect_marker_point(frame, colour)

                self.assertAlmostEqual(result["image_xy"][0], 10.0, places=9)
                self.assertAlmostEqual(result["image_xy"][1], 10.0, places=9)
                self.assertEqual(result["pure_rgb"], list(marker))
                self.assertEqual(result["background_rgb"], list(scenery))

    def test_scenery_alone_matches_nothing(self) -> None:
        """The scenery is rejected outright, not merely out-voted by the blob."""

        for colour, _, scenery_name, scenery, bound in COLOUR_SCENERY_CASES:
            with self.subTest(colour=colour, scenery=scenery_name, bound=bound):
                with self.assertRaises(MarkerDetectionError) as caught:
                    detect_marker_point(_frame(21, 21, scenery), colour)
                self.assertIn("No pixel matched", str(caught.exception))

    def test_white_saturation_ceiling_excludes_the_horizon(self) -> None:
        """Pins the 0.18 -> 0.10 ceiling that separates white from the horizon.

        Where grass blends into sky the horizon row is a desaturated blue-green
        that the previous ceiling admitted as a rival blob.  Loosening the
        ceiling back toward 0.18 must break this test.
        """

        ceiling = MARKER_COLOUR_GATES["white"][3]
        marker_saturation = _saturation(WHITE_MARKER)
        horizon_saturation = _saturation(HORIZON_BLEND)

        self.assertAlmostEqual(ceiling, 0.10, places=9)
        self.assertLessEqual(marker_saturation, ceiling)
        self.assertGreater(horizon_saturation, ceiling)
        self.assertLessEqual(
            horizon_saturation,
            SUPERSEDED_WHITE_SATURATION_CEILING,
            "the horizon must be the thing the tightened ceiling newly excludes",
        )

    def test_blue_is_separated_from_sky_by_brightness_alone(self) -> None:
        """The value cap is load-bearing: hue and saturation cannot separate these."""

        marker = (53, 57, 157)
        sky = (85, 91, 250)
        _, _, saturation_floor, saturation_ceiling, _, value_ceiling = (
            MARKER_COLOUR_GATES["blue"]
        )

        self.assertAlmostEqual(_saturation(marker), _saturation(sky), places=2)
        self.assertLessEqual(saturation_floor, _saturation(sky))
        self.assertLessEqual(_saturation(sky), saturation_ceiling)
        self.assertGreater(max(sky) / 255.0, value_ceiling)
        self.assertLessEqual(max(marker) / 255.0, value_ceiling)


class TestMarkerDetectionFailsClosed(unittest.TestCase):
    def test_each_ambiguity_rejects_with_its_own_message(self) -> None:
        two_rivals = _frame(21, 21)
        _paint(two_rivals, range(4, 9), CORE_ROWS, MARKER)
        _paint(two_rivals, range(12, 17), CORE_ROWS, MARKER)

        on_border = _frame(21, 21)
        _paint(on_border, range(0, 5), CORE_ROWS, MARKER)

        single_pixel = _frame(21, 21)
        _paint(single_pixel, (10,), (10,), MARKER)

        cases: list[tuple[str, list[list[list[int]]], str, str]] = [
            (
                "unknown_colour",
                _solid_marker_frame(),
                "magenta",
                "No colour gate is defined",
            ),
            ("no_blob", _frame(21, 21), "yellow", "No pixel matched"),
            (
                "blob_too_small",
                single_pixel,
                "yellow",
                "below the 4-pixel minimum",
            ),
            (
                "ambiguous_rival",
                two_rivals,
                "yellow",
                "the colour is ambiguous",
            ),
            (
                "touches_border",
                on_border,
                "yellow",
                "touches the frame border",
            ),
            (
                "indistinguishable_background",
                _indistinguishable_background_frame(),
                "yellow",
                "indistinguishable from its background",
            ),
        ]

        seen: set[str] = set()
        for label, frame, colour, expected in cases:
            with self.subTest(case=label):
                with self.assertRaises(MarkerDetectionError) as caught:
                    detect_marker_point(frame, colour)
                message = str(caught.exception)
                self.assertIn(expected, message)
                self.assertNotIn(
                    message, seen, f"{label} reuses another case's message"
                )
                seen.add(message)

    def test_a_blob_below_a_raised_minimum_is_rejected(self) -> None:
        """The minimum is a parameter, so a caller can demand a larger blob."""

        with self.assertRaises(MarkerDetectionError) as caught:
            detect_marker_point(
                _solid_marker_frame(), "yellow", minimum_core_pixels=26
            )
        self.assertIn("below the 26-pixel minimum", str(caught.exception))

    def test_malformed_frames_are_rejected(self) -> None:
        """``_require_rgb`` shares messages across shapes, so no distinctness here."""

        pixel = [0, 0, 0]
        cases: list[tuple[str, object, str]] = [
            ("not_a_list", "not a frame", "at least one image row"),
            ("no_rows", [], "at least one image row"),
            ("empty_row", [[]], "at least one pixel"),
            ("row_is_not_a_list", [123], "at least one pixel"),
            ("ragged_rows", [[pixel, pixel], [pixel]], "equal width"),
        ]
        for label, frame, expected in cases:
            with self.subTest(case=label):
                with self.assertRaises(MarkerDetectionError) as caught:
                    detect_marker_point(frame, "yellow")  # type: ignore[arg-type]
                self.assertIn(expected, str(caught.exception))


class TestLayoutMarkers(unittest.TestCase):
    #: Person C's colour-to-role mapping, laid out so each blob sits in the
    #: corner its role names.  Blobs are far enough apart that no blob falls in
    #: another's background ring.
    LAYOUT = {
        "north_west": ("blue", (53, 57, 157), range(6, 11), range(6, 11), (8.0, 8.0)),
        "north_east": (
            "yellow",
            (250, 210, 0),
            range(28, 33),
            range(6, 11),
            (30.0, 8.0),
        ),
        "south_west": (
            "lime",
            (106, 190, 48),
            range(6, 11),
            range(28, 33),
            (8.0, 30.0),
        ),
        "south_east": (
            "white",
            (245, 240, 236),
            range(28, 33),
            range(28, 33),
            (30.0, 30.0),
        ),
    }

    def _layout_frame(self, skip: str | None = None) -> list[list[list[int]]]:
        frame = _frame(40, 40)
        for marker_id, (_, colour, columns, rows, _) in self.LAYOUT.items():
            if marker_id == skip:
                continue
            _paint(frame, columns, rows, colour)
        return frame

    def _colour_by_marker_id(self) -> dict[str, str]:
        return {marker_id: entry[0] for marker_id, entry in self.LAYOUT.items()}

    def test_every_marker_of_a_layout_is_located(self) -> None:
        detected = detect_layout_markers(
            self._layout_frame(), self._colour_by_marker_id()
        )

        self.assertEqual(sorted(detected), sorted(self.LAYOUT))
        self.assertEqual(list(detected), sorted(self.LAYOUT))
        for marker_id, (_, _, _, _, expected) in self.LAYOUT.items():
            with self.subTest(marker_id=marker_id):
                point = detected[marker_id]["image_xy"]
                self.assertAlmostEqual(point[0], expected[0], places=9)
                self.assertAlmostEqual(point[1], expected[1], places=9)

    def test_a_missing_marker_names_the_marker_that_failed(self) -> None:
        with self.assertRaises(MarkerDetectionError) as caught:
            detect_layout_markers(
                self._layout_frame(skip="north_west"), self._colour_by_marker_id()
            )
        message = str(caught.exception)
        self.assertIn("Marker 'north_west'", message)
        self.assertIn("No pixel matched", message)

    def test_two_markers_sharing_a_colour_are_rejected(self) -> None:
        colours = self._colour_by_marker_id()
        colours["south_east"] = colours["north_west"]
        with self.assertRaises(MarkerDetectionError) as caught:
            detect_layout_markers(self._layout_frame(), colours)
        self.assertIn("share one colour", str(caught.exception))

    def test_an_empty_layout_is_rejected(self) -> None:
        with self.assertRaises(MarkerDetectionError) as caught:
            detect_layout_markers(self._layout_frame(), {})
        self.assertIn("At least one marker id is required", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
