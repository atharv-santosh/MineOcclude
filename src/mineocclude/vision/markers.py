"""Sub-pixel detection of the four coloured ground-plane markers.

Person C places four coloured blocks flush with the ground plane (top face at
``y = 4``, the sheep foot plane), one per corner of the arena.  Their image
positions are the left-hand side of every homography fit, so this module turns
decoded frames into ``image_xy`` points that :mod:`mineocclude.vision.homography`
can consume.  It never fits anything itself.

Why sub-pixel accuracy is not optional
--------------------------------------
Frames are 640x360.  At the far edge of the arena a marker subtends only two to
three pixels, where one pixel of image error is worth roughly 0.29 blocks of
world depth -- already worse than the 0.2-block median gate.  A hard colour
threshold snaps each marker to whole pixels and biases the centroid toward
whichever side happens to survive the cut.

So each marker's centre is an *alpha-weighted* centroid.  Every pixel near the
marker is modelled as a blend of the pure marker colour and the local
background,

    pixel ~= alpha * pure_marker + (1 - alpha) * local_background

and ``alpha`` -- the marker's coverage fraction of that pixel -- is recovered by
projecting the pixel onto the ``pure - background`` colour axis.  Weighting by
coverage recovers the true centre of a partially covered edge pixel.

Everything here is deterministic: no randomness and no dependence on set
iteration order, so the same frame bytes always produce the same point.

Fail-closed policy
------------------
A wrong marker point silently corrupts every world coordinate downstream while
still looking like a plausible number, so every ambiguity is an error rather
than a best guess: no candidate blob, a blob too small to trust, a second blob
of comparable size (the colour was not unique), a blob touching the frame
border (the marker is clipped, so its centroid is biased), or a background
indistinguishable from the marker colour.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


MARKER_DETECTOR_VERSION = "person-e-marker-detect-v1.0"

#: Coarse HSV gates per marker colour, as
#: ``(hue_min_deg, hue_max_deg, sat_min, sat_max, value_min, value_max)``.
#:
#: These separate each marker from the specific scenery it competes with, and
#: were selected on Person C's *calibration*-split no-sheep frames only:
#:
#: * ``blue`` -- blue wool and the Minecraft sky share hue *and* saturation.
#:   Only brightness separates them, which is why the value cap at 0.70 is
#:   load-bearing rather than decorative.
#: * ``lime`` -- lime wool sits in the same hue family as grass.  Grass has a
#:   median value near 0.42 and a maximum near 0.647, so the saturation and
#:   value floors do the separating.
#: * ``white`` -- separated by near-zero saturation, so its hue range is the
#:   full circle.  Its saturation ceiling is the tight one: the horizon row,
#:   where grass blends into sky, is a desaturated blue-green that a looser
#:   ceiling admits as a rival blob.  Measured across all six layouts'
#:   calibration no-sheep frames, the white marker sits at saturation
#:   0.035-0.046 and the horizon blend at 0.169, so a 0.10 ceiling clears the
#:   marker by 2.2x and excludes the horizon by 1.7x.
MARKER_COLOUR_GATES: dict[str, tuple[float, float, float, float, float, float]] = {
    "yellow": (35.0, 70.0, 0.55, 1.00, 0.35, 1.00),
    "blue": (225.0, 250.0, 0.35, 0.90, 0.20, 0.70),
    "lime": (85.0, 120.0, 0.60, 1.00, 0.50, 0.95),
    "white": (0.0, 360.0, 0.00, 0.10, 0.60, 1.00),
}

#: A blob smaller than this cannot support a trustworthy centroid.
MINIMUM_CORE_PIXELS = 4

#: If a rival blob of the same colour reaches this fraction of the largest, the
#: colour did not uniquely identify one marker and the frame is rejected.
AMBIGUOUS_RIVAL_FRACTION = 0.5

#: Pixels of dilation used to collect partially covered edge pixels.
_BAND_RADIUS = 2


class MarkerDetectionError(ValueError):
    """Raised when a marker cannot be located unambiguously."""


def _rgb_to_hsv(red: int, green: int, blue: int) -> tuple[float, float, float]:
    """Convert one 0-255 RGB pixel to ``(hue_degrees, saturation, value)``."""

    r = red / 255.0
    g = green / 255.0
    b = blue / 255.0
    high = max(r, g, b)
    low = min(r, g, b)
    span = high - low
    if span <= 0.0:
        return 0.0, 0.0, high
    if high == r:
        hue = (60.0 * ((g - b) / span)) % 360.0
    elif high == g:
        hue = 60.0 * ((b - r) / span) + 120.0
    else:
        hue = 60.0 * ((r - g) / span) + 240.0
    return hue, (span / high if high > 0.0 else 0.0), high


def _gate_matches(
    hue: float,
    saturation: float,
    value: float,
    gate: tuple[float, float, float, float, float, float],
) -> bool:
    hue_min, hue_max, sat_min, sat_max, value_min, value_max = gate
    if hue_min <= hue_max:
        hue_ok = hue_min <= hue <= hue_max
    else:  # A gate that wraps through 0 degrees.
        hue_ok = hue >= hue_min or hue <= hue_max
    return (
        hue_ok
        and sat_min <= saturation <= sat_max
        and value_min <= value <= value_max
    )


def _require_rgb(rgb: Any) -> tuple[list[list[list[int]]], int, int]:
    if not isinstance(rgb, list) or not rgb:
        raise MarkerDetectionError("Frame must contain at least one image row.")
    height = len(rgb)
    width = len(rgb[0]) if isinstance(rgb[0], list) else 0
    if width == 0:
        raise MarkerDetectionError("Frame rows must contain at least one pixel.")
    for row in rgb:
        if not isinstance(row, list) or len(row) != width:
            raise MarkerDetectionError("Frame rows must all have equal width.")
    return rgb, width, height


def _matching_pixels(
    rgb: list[list[list[int]]],
    width: int,
    height: int,
    gate: tuple[float, float, float, float, float, float],
) -> set[tuple[int, int]]:
    matched: set[tuple[int, int]] = set()
    for y in range(height):
        row = rgb[y]
        for x in range(width):
            pixel = row[x]
            hue, saturation, value = _rgb_to_hsv(pixel[0], pixel[1], pixel[2])
            if _gate_matches(hue, saturation, value, gate):
                matched.add((x, y))
    return matched


def _components(pixels: set[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    """Split matched pixels into 8-connected blobs, largest first.

    Ties are broken by the blob's smallest ``(y, x)`` so ordering never depends
    on set iteration order.
    """

    remaining = set(pixels)
    found: list[set[tuple[int, int]]] = []
    while remaining:
        seed = min(remaining, key=lambda point: (point[1], point[0]))
        blob: set[tuple[int, int]] = set()
        stack = [seed]
        remaining.discard(seed)
        while stack:
            x, y = stack.pop()
            blob.add((x, y))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    neighbour = (x + dx, y + dy)
                    if neighbour in remaining:
                        remaining.discard(neighbour)
                        stack.append(neighbour)
        found.append(blob)
    found.sort(
        key=lambda blob: (
            -len(blob),
            min(point[1] for point in blob),
            min(point[0] for point in blob),
        )
    )
    return found


def _dilate(pixels: set[tuple[int, int]], radius: int) -> set[tuple[int, int]]:
    grown = set(pixels)
    for _ in range(radius):
        expanded: set[tuple[int, int]] = set()
        for x, y in grown:
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    expanded.add((x + dx, y + dy))
        grown = expanded
    return grown


def _erode(pixels: set[tuple[int, int]]) -> set[tuple[int, int]]:
    return {
        (x, y)
        for x, y in pixels
        if all(
            (x + dx, y + dy) in pixels
            for dy in (-1, 0, 1)
            for dx in (-1, 0, 1)
        )
    }


def _median_colour(
    rgb: list[list[list[int]]],
    pixels: Sequence[tuple[int, int]],
) -> tuple[float, float, float]:
    channels: list[list[int]] = [[], [], []]
    for x, y in pixels:
        pixel = rgb[y][x]
        for index in range(3):
            channels[index].append(pixel[index])
    medians: list[float] = []
    for values in channels:
        values.sort()
        middle = len(values) // 2
        if len(values) % 2:
            medians.append(float(values[middle]))
        else:
            medians.append((values[middle - 1] + values[middle]) / 2.0)
    return medians[0], medians[1], medians[2]


def _clip_to_frame(
    pixels: set[tuple[int, int]], width: int, height: int
) -> set[tuple[int, int]]:
    return {(x, y) for x, y in pixels if 0 <= x < width and 0 <= y < height}


def detect_marker_point(
    rgb: list[list[list[int]]],
    colour: str,
    *,
    minimum_core_pixels: int = MINIMUM_CORE_PIXELS,
) -> dict[str, Any]:
    """Locate one coloured marker and return its sub-pixel centre.

    ``colour`` must name one of :data:`MARKER_COLOUR_GATES`.  The returned
    mapping carries the point plus the diagnostics needed to judge it:
    ``image_xy``, ``core_pixels``, ``alpha_sum``, ``pure_rgb``,
    ``background_rgb`` and ``hard_centroid_offset_px`` (how far the sub-pixel
    answer moved from a naive threshold centroid).
    """

    if colour not in MARKER_COLOUR_GATES:
        raise MarkerDetectionError(
            f"No colour gate is defined for marker colour {colour!r}."
        )
    frame, width, height = _require_rgb(rgb)
    gate = MARKER_COLOUR_GATES[colour]

    blobs = _components(_matching_pixels(frame, width, height, gate))
    if not blobs:
        raise MarkerDetectionError(f"No pixel matched the {colour} marker gate.")
    core = blobs[0]
    if len(core) < minimum_core_pixels:
        raise MarkerDetectionError(
            f"The {colour} marker blob has {len(core)} pixels, below the "
            f"{minimum_core_pixels}-pixel minimum needed for a stable centroid."
        )
    if len(blobs) > 1 and len(blobs[1]) >= AMBIGUOUS_RIVAL_FRACTION * len(core):
        raise MarkerDetectionError(
            f"The {colour} marker gate matched two comparable blobs "
            f"({len(core)} and {len(blobs[1])} pixels); the colour is ambiguous."
        )
    if any(x in (0, width - 1) or y in (0, height - 1) for x, y in core):
        raise MarkerDetectionError(
            f"The {colour} marker touches the frame border, so its centroid "
            "would be biased by clipping."
        )

    interior = _erode(core)
    pure_source = sorted(interior if len(interior) >= 8 else core)
    pure = _median_colour(frame, pure_source)

    band = _clip_to_frame(_dilate(core, _BAND_RADIUS), width, height)
    ring = band - _dilate(core, 1)
    if len(ring) < 8:
        ring = band - core
    if not ring:
        raise MarkerDetectionError(
            f"The {colour} marker fills its neighbourhood, leaving no "
            "background to unmix against."
        )
    background = _median_colour(frame, sorted(ring))

    delta = (pure[0] - background[0], pure[1] - background[1], pure[2] - background[2])
    denominator = delta[0] ** 2 + delta[1] ** 2 + delta[2] ** 2
    if denominator <= 1e-12:
        raise MarkerDetectionError(
            f"The {colour} marker is indistinguishable from its background."
        )

    weighted_x = 0.0
    weighted_y = 0.0
    total_alpha = 0.0
    hard_x = 0.0
    hard_y = 0.0
    hard_count = 0
    for x, y in sorted(band):
        pixel = frame[y][x]
        offset = (
            pixel[0] - background[0],
            pixel[1] - background[1],
            pixel[2] - background[2],
        )
        projection = (
            offset[0] * delta[0] + offset[1] * delta[1] + offset[2] * delta[2]
        ) / denominator
        alpha = 0.0 if projection < 0.0 else (1.0 if projection > 1.0 else projection)
        if alpha <= 0.0:
            continue
        weighted_x += alpha * x
        weighted_y += alpha * y
        total_alpha += alpha
        if alpha >= 0.5:
            hard_x += x
            hard_y += y
            hard_count += 1
    if total_alpha <= 0.0:
        raise MarkerDetectionError(
            f"The {colour} marker has zero total coverage after unmixing."
        )

    centre_x = weighted_x / total_alpha
    centre_y = weighted_y / total_alpha
    if hard_count:
        offset_px = math.hypot(
            centre_x - hard_x / hard_count, centre_y - hard_y / hard_count
        )
    else:
        offset_px = 0.0
    return {
        "image_xy": [centre_x, centre_y],
        "core_pixels": len(core),
        "alpha_sum": total_alpha,
        "pure_rgb": [int(round(channel)) for channel in pure],
        "background_rgb": [int(round(channel)) for channel in background],
        "hard_centroid_offset_px": offset_px,
    }


def detect_layout_markers(
    rgb: list[list[list[int]]],
    colour_by_marker_id: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    """Detect every marker of one layout, keyed by ``marker_id``.

    ``colour_by_marker_id`` comes from Person C's
    ``marker_correspondences[].marker_color``, so the role-to-colour mapping
    stays Person C's authority rather than an assumption made here.
    """

    if not colour_by_marker_id:
        raise MarkerDetectionError("At least one marker id is required.")
    colours = list(colour_by_marker_id.values())
    if len(set(colours)) != len(colours):
        raise MarkerDetectionError(
            "Two markers share one colour, so they cannot be told apart."
        )
    detected: dict[str, dict[str, Any]] = {}
    for marker_id in sorted(colour_by_marker_id):
        colour = colour_by_marker_id[marker_id]
        try:
            detected[marker_id] = detect_marker_point(rgb, colour)
        except MarkerDetectionError as error:
            raise MarkerDetectionError(f"Marker {marker_id!r}: {error}") from error
    return detected
