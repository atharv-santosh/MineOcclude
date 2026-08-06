"""Four-marker image-to-ground-plane homography and localization QA."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


class HomographyError(ValueError):
    """Raised when marker geometry or localization evidence is invalid."""


HOMOGRAPHY_ALGORITHM_VERSION = "four_point_projective_gauss_jordan_v0.1"
HOMOGRAPHY_FIXTURE_SCHEMA_VERSION = "person-e-homography-fixture-v1.0"
HOMOGRAPHY_FIXTURE_SCHEMA_VERSION_V1_1 = "person-e-homography-fixture-v1.1"
SUPPORTED_HOMOGRAPHY_FIXTURE_SCHEMA_VERSIONS = frozenset(
    {HOMOGRAPHY_FIXTURE_SCHEMA_VERSION, HOMOGRAPHY_FIXTURE_SCHEMA_VERSION_V1_1}
)
PERCENTILE_METHOD = "linear_interpolation_rank_n_minus_1"
CANONICAL_MARKER_ROLES = frozenset(
    {"north_west", "north_east", "south_east", "south_west"}
)
MARKER_LOCALIZATION_METHOD_VERSION = (
    "person-e-marker-color-top-face-diagonals-v0.1"
)
GROUND_CONTACT_LOCALIZATION_METHOD_VERSION = (
    "person-e-paired-background-silhouette-base-v0.1"
)


def _finite_pair(value: Any, name: str) -> tuple[float, float]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) != 2
    ):
        raise HomographyError(f"{name} must contain two coordinates.")
    coordinates: list[float] = []
    for item in value:
        if (
            not isinstance(item, (int, float))
            or isinstance(item, bool)
            or not math.isfinite(float(item))
        ):
            raise HomographyError(f"{name} coordinates must be finite numbers.")
        coordinates.append(float(item))
    return coordinates[0], coordinates[1]


def _solve_square_system(
    matrix: list[list[float]],
    right_hand_side: list[float],
    *,
    pivot_tolerance: float,
) -> list[float]:
    size = len(right_hand_side)
    augmented = [
        [*matrix[row_index], right_hand_side[row_index]]
        for row_index in range(size)
    ]
    for column in range(size):
        pivot_row = max(
            range(column, size),
            key=lambda row_index: abs(augmented[row_index][column]),
        )
        if abs(augmented[pivot_row][column]) <= pivot_tolerance:
            raise HomographyError(
                "Marker correspondences are singular or numerically degenerate."
            )
        if pivot_row != column:
            augmented[column], augmented[pivot_row] = (
                augmented[pivot_row],
                augmented[column],
            )
        pivot = augmented[column][column]
        augmented[column] = [value / pivot for value in augmented[column]]
        for row_index in range(size):
            if row_index == column:
                continue
            factor = augmented[row_index][column]
            if factor == 0.0:
                continue
            augmented[row_index] = [
                current - factor * pivot_value
                for current, pivot_value in zip(
                    augmented[row_index], augmented[column], strict=True
                )
            ]
    solution = [augmented[index][-1] for index in range(size)]
    if any(not math.isfinite(value) for value in solution):
        raise HomographyError("Homography solution contains non-finite values.")
    return solution


def _normalized_rgb_image(
    image: Sequence[Sequence[Sequence[float]]],
    name: str,
) -> tuple[int, int, list[list[tuple[int, int, int]]]]:
    if (
        not isinstance(image, Sequence)
        or isinstance(image, (str, bytes))
        or not image
    ):
        raise HomographyError(f"{name} must contain image rows.")
    width: int | None = None
    normalized: list[list[tuple[int, int, int]]] = []
    for row_index, row in enumerate(image):
        if (
            not isinstance(row, Sequence)
            or isinstance(row, (str, bytes))
            or not row
        ):
            raise HomographyError(f"{name} row {row_index} is invalid.")
        if width is None:
            width = len(row)
        elif len(row) != width:
            raise HomographyError(f"{name} rows have inconsistent widths.")
        normalized_row: list[tuple[int, int, int]] = []
        for pixel in row:
            if (
                not isinstance(pixel, Sequence)
                or isinstance(pixel, (str, bytes))
                or len(pixel) != 3
                or any(
                    not isinstance(channel, int)
                    or isinstance(channel, bool)
                    or not 0 <= channel <= 255
                    for channel in pixel
                )
            ):
                raise HomographyError(f"{name} requires RGB8 pixels.")
            normalized_row.append((pixel[0], pixel[1], pixel[2]))
        normalized.append(normalized_row)
    if width is None:
        raise HomographyError(f"{name} has no pixels.")
    return width, len(normalized), normalized


def _pixel_components(
    pixels: set[tuple[int, int]],
) -> list[list[tuple[int, int]]]:
    unvisited = set(pixels)
    components: list[list[tuple[int, int]]] = []
    offsets = (
        (-1, -1),
        (0, -1),
        (1, -1),
        (-1, 0),
        (1, 0),
        (-1, 1),
        (0, 1),
        (1, 1),
    )
    while unvisited:
        start = min(unvisited, key=lambda point: (point[1], point[0]))
        unvisited.remove(start)
        stack = [start]
        component: list[tuple[int, int]] = []
        while stack:
            x, y = stack.pop()
            component.append((x, y))
            for dx, dy in offsets:
                neighbor = (x + dx, y + dy)
                if neighbor in unvisited:
                    unvisited.remove(neighbor)
                    stack.append(neighbor)
        components.append(component)
    components.sort(
        key=lambda component: (
            -len(component),
            min(y for _, y in component),
            min(x for x, _ in component),
        )
    )
    return components


def _line_intersection(
    first_start: tuple[float, float],
    first_end: tuple[float, float],
    second_start: tuple[float, float],
    second_end: tuple[float, float],
) -> tuple[float, float]:
    x1, y1 = first_start
    x2, y2 = first_end
    x3, y3 = second_start
    x4, y4 = second_end
    denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denominator) <= 1e-12:
        raise HomographyError("Segmented marker diagonals do not intersect.")
    first_cross = x1 * y2 - y1 * x2
    second_cross = x3 * y4 - y3 * x4
    return (
        (first_cross * (x3 - x4) - (x1 - x2) * second_cross)
        / denominator,
        (first_cross * (y3 - y4) - (y1 - y2) * second_cross)
        / denominator,
    )


def localize_marker_top_face(
    image: Sequence[Sequence[Sequence[float]]],
    *,
    marker_color: str,
) -> dict[str, Any]:
    """Locate a C color-labelled marker with a fixed, world-blind rule."""

    width, height, rgb = _normalized_rgb_image(image, "marker image")
    if marker_color not in {"blue", "yellow", "lime", "white"}:
        raise HomographyError("marker_color is unsupported.")

    def matches(pixel: tuple[int, int, int]) -> bool:
        red, green, blue = pixel
        if marker_color == "blue":
            return (
                blue > 70
                and blue > red * 1.35
                and blue > green * 1.15
            )
        if marker_color == "yellow":
            return (
                red > 100
                and green > 80
                and red > blue * 2.2
                and green > blue * 1.8
                and 0.65 < green / red < 1.25
            )
        if marker_color == "lime":
            return green > 80 and green > red * 1.5 and green > blue * 1.35
        return min(pixel) > 105 and max(pixel) - min(pixel) < 30

    lower_y = int(height * 0.55)
    mask = {
        (x, y)
        for y in range(lower_y, height)
        for x in range(width)
        if matches(rgb[y][x])
    }
    candidates = [
        component
        for component in _pixel_components(mask)
        if 20 <= len(component) <= 2000
    ]
    if not candidates:
        raise HomographyError(f"No valid {marker_color} marker component.")
    selected = candidates[0]
    minimum_y = min(y for _, y in selected)
    maximum_y = max(y for _, y in selected)
    if minimum_y == maximum_y:
        raise HomographyError("Marker top face has no vertical extent.")
    top_x = sorted(x for x, y in selected if y == minimum_y)
    bottom_x = sorted(x for x, y in selected if y == maximum_y)
    top_left = (float(top_x[0]), float(minimum_y))
    top_right = (float(top_x[-1]), float(minimum_y))
    bottom_left = (float(bottom_x[0]), float(maximum_y))
    bottom_right = (float(bottom_x[-1]), float(maximum_y))
    image_xy = _line_intersection(
        top_left,
        bottom_right,
        top_right,
        bottom_left,
    )
    minimum_x = min(x for x, _ in selected)
    maximum_x = max(x for x, _ in selected)
    return {
        "localization_method_version": MARKER_LOCALIZATION_METHOD_VERSION,
        "marker_color": marker_color,
        "image_xy": list(image_xy),
        "segmentation_pixel_count": len(selected),
        "bounding_box_xyxy": [
            minimum_x,
            minimum_y,
            maximum_x + 1,
            maximum_y + 1,
        ],
        "top_face_corner_pixels": [
            list(top_left),
            list(top_right),
            list(bottom_right),
            list(bottom_left),
        ],
    }


def localize_ground_contact_from_background_pair(
    visible_image: Sequence[Sequence[Sequence[float]]],
    background_image: Sequence[Sequence[Sequence[float]]],
    *,
    absolute_channel_difference_threshold: int = 20,
) -> dict[str, Any]:
    """Locate silhouette base from a registered visible/no-sheep image pair."""

    width, height, visible = _normalized_rgb_image(
        visible_image, "visible image"
    )
    other_width, other_height, background = _normalized_rgb_image(
        background_image, "background image"
    )
    if (width, height) != (other_width, other_height):
        raise HomographyError("Paired images must have equal dimensions.")
    if (
        not isinstance(absolute_channel_difference_threshold, int)
        or isinstance(absolute_channel_difference_threshold, bool)
        or not 1 <= absolute_channel_difference_threshold <= 255
    ):
        raise HomographyError("Difference threshold must be an RGB8 integer.")
    mask = {
        (x, y)
        for y in range(height)
        for x in range(width)
        if max(
            abs(visible[y][x][channel] - background[y][x][channel])
            for channel in range(3)
        )
        >= absolute_channel_difference_threshold
    }
    candidates = [
        component
        for component in _pixel_components(mask)
        if len(component) >= 20
    ]
    if len(candidates) != 1:
        raise HomographyError(
            "Paired images require exactly one valid changed component."
        )
    selected = candidates[0]
    minimum_x = min(x for x, _ in selected)
    maximum_x = max(x for x, _ in selected)
    minimum_y = min(y for _, y in selected)
    maximum_y = max(y for _, y in selected)
    return {
        "localization_method_version": (
            GROUND_CONTACT_LOCALIZATION_METHOD_VERSION
        ),
        "absolute_channel_difference_threshold": (
            absolute_channel_difference_threshold
        ),
        "image_xy": [(minimum_x + maximum_x) / 2.0, float(maximum_y)],
        "changed_pixel_count": len(selected),
        "bounding_box_xyxy": [
            minimum_x,
            minimum_y,
            maximum_x + 1,
            maximum_y + 1,
        ],
    }


@dataclass(frozen=True)
class Homography:
    """A validated 3x3 image-XY to world-XZ projective mapping."""

    matrix: tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ]
    marker_ids: tuple[str, str, str, str]
    layout_id: str
    canonical_camera_pose_id: str
    fit_hash: str
    pivot_tolerance: float
    denominator_tolerance: float = 1e-12
    resolution_id: str | None = None
    image_width_px: int | None = None
    image_height_px: int | None = None
    source_correspondence_hash: str | None = None
    detector_version: str | None = None
    software_runtime_hash: str | None = None

    def transform(self, image_xy: Sequence[float]) -> tuple[float, float]:
        x, y = _finite_pair(image_xy, "image_xy")
        first, second, third = self.matrix
        denominator = third[0] * x + third[1] * y + third[2]
        if abs(denominator) <= self.denominator_tolerance:
            raise HomographyError(
                "Image point maps to an invalid projective denominator."
            )
        world_x = (first[0] * x + first[1] * y + first[2]) / denominator
        world_z = (second[0] * x + second[1] * y + second[2]) / denominator
        if not math.isfinite(world_x) or not math.isfinite(world_z):
            raise HomographyError("Transformed world coordinates are non-finite.")
        return world_x, world_z

    def to_record(self) -> dict[str, Any]:
        return {
            "matrix": [list(row) for row in self.matrix],
            "marker_ids": list(self.marker_ids),
            "layout_id": self.layout_id,
            "canonical_camera_pose_id": self.canonical_camera_pose_id,
            "fit_hash": self.fit_hash,
            "homography_version_id": (
                f"{HOMOGRAPHY_ALGORITHM_VERSION}:{self.fit_hash}"
            ),
            "algorithm_version": HOMOGRAPHY_ALGORITHM_VERSION,
            "pivot_tolerance": self.pivot_tolerance,
            "denominator_tolerance": self.denominator_tolerance,
            "image_coordinate_convention": "pixel_center_xy_zero_based",
            "world_coordinate_convention": "ground_plane_world_xz_blocks",
            "resolution_id": self.resolution_id,
            "image_width_px": self.image_width_px,
            "image_height_px": self.image_height_px,
            "source_correspondence_hash": self.source_correspondence_hash,
            "detector_version": self.detector_version,
            "software_runtime_hash": self.software_runtime_hash,
        }


def homography_from_record(record: Mapping[str, Any]) -> Homography:
    """Reconstruct a fitted homography from a versioned report record."""

    if not isinstance(record, Mapping):
        raise HomographyError("Homography record must be a mapping.")
    legacy_required = {
        "matrix",
        "marker_ids",
        "layout_id",
        "canonical_camera_pose_id",
        "fit_hash",
        "homography_version_id",
        "algorithm_version",
        "pivot_tolerance",
        "denominator_tolerance",
        "image_coordinate_convention",
        "world_coordinate_convention",
    }
    binding_fields = {
        "resolution_id",
        "image_width_px",
        "image_height_px",
        "source_correspondence_hash",
        "detector_version",
        "software_runtime_hash",
    }
    record_fields = frozenset(record)
    if record_fields not in {
        frozenset(legacy_required),
        frozenset(legacy_required | binding_fields),
    }:
        raise HomographyError("Homography record fields have changed.")
    if record["algorithm_version"] != HOMOGRAPHY_ALGORITHM_VERSION:
        raise HomographyError("Unknown homography algorithm version.")
    fit_hash = record["fit_hash"]
    if (
        not isinstance(fit_hash, str)
        or len(fit_hash) != 64
        or any(character not in "0123456789abcdef" for character in fit_hash)
    ):
        raise HomographyError("fit_hash must be lowercase SHA-256.")
    if record["homography_version_id"] != f"{HOMOGRAPHY_ALGORITHM_VERSION}:{fit_hash}":
        raise HomographyError("homography_version_id does not match fit identity.")
    marker_ids = record["marker_ids"]
    if (
        not isinstance(marker_ids, list)
        or len(marker_ids) != 4
        or len(set(marker_ids)) != 4
        or any(not isinstance(marker_id, str) or not marker_id for marker_id in marker_ids)
    ):
        raise HomographyError("Homography record requires four marker IDs.")
    matrix = record["matrix"]
    if (
        not isinstance(matrix, list)
        or len(matrix) != 3
        or any(not isinstance(row, list) or len(row) != 3 for row in matrix)
    ):
        raise HomographyError("Homography matrix must be 3x3.")
    normalized_rows: list[tuple[float, float, float]] = []
    for row in matrix:
        first, second = _finite_pair(row[:2], "matrix row")
        third = row[2]
        if (
            not isinstance(third, (int, float))
            or isinstance(third, bool)
            or not math.isfinite(float(third))
        ):
            raise HomographyError("Homography matrix entries must be finite numbers.")
        normalized_rows.append((first, second, float(third)))
    normalized_matrix = tuple(normalized_rows)
    for field in ("layout_id", "canonical_camera_pose_id"):
        if not isinstance(record[field], str) or not record[field].strip():
            raise HomographyError(f"{field} must be non-empty.")
    for field in ("pivot_tolerance", "denominator_tolerance"):
        value = record[field]
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            or value <= 0
        ):
            raise HomographyError(f"{field} must be finite and positive.")
    if (
        record["image_coordinate_convention"] != "pixel_center_xy_zero_based"
        or record["world_coordinate_convention"]
        != "ground_plane_world_xz_blocks"
    ):
        raise HomographyError("Homography coordinate conventions changed.")
    bound = binding_fields <= set(record)
    binding_values = (
        [record[field] for field in binding_fields] if bound else [None]
    )
    if any(value is None for value in binding_values) and any(
        value is not None for value in binding_values
    ):
        raise HomographyError("Homography identity binding must be all-or-none.")
    if bound and all(value is not None for value in binding_values):
        for field in ("resolution_id", "detector_version"):
            if (
                not isinstance(record[field], str)
                or not record[field].strip()
                or record[field] != record[field].strip()
            ):
                raise HomographyError(f"{field} must be a non-empty identity.")
        for field in ("image_width_px", "image_height_px"):
            if (
                not isinstance(record[field], int)
                or isinstance(record[field], bool)
                or record[field] <= 0
            ):
                raise HomographyError(f"{field} must be positive.")
        for field in ("source_correspondence_hash", "software_runtime_hash"):
            value = record[field]
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise HomographyError(f"{field} must be lowercase SHA-256.")
    return Homography(
        matrix=normalized_matrix,  # type: ignore[arg-type]
        marker_ids=tuple(marker_ids),  # type: ignore[arg-type]
        layout_id=record["layout_id"],
        canonical_camera_pose_id=record["canonical_camera_pose_id"],
        fit_hash=fit_hash,
        pivot_tolerance=float(record["pivot_tolerance"]),
        denominator_tolerance=float(record["denominator_tolerance"]),
        resolution_id=record.get("resolution_id"),
        image_width_px=record.get("image_width_px"),
        image_height_px=record.get("image_height_px"),
        source_correspondence_hash=record.get("source_correspondence_hash"),
        detector_version=record.get("detector_version"),
        software_runtime_hash=record.get("software_runtime_hash"),
    )


def fit_marker_homography(
    image_points_by_marker: Mapping[str, Sequence[float]],
    world_points_by_marker: Mapping[str, Sequence[float]],
    *,
    marker_ids: Sequence[str],
    layout_id: str,
    canonical_camera_pose_id: str,
    pivot_tolerance: float = 1e-12,
    resolution_id: str | None = None,
    image_width_px: int | None = None,
    image_height_px: int | None = None,
    source_correspondence_hash: str | None = None,
    detector_version: str | None = None,
    software_runtime_hash: str | None = None,
) -> Homography:
    """Fit an exact homography from four explicitly ordered marker IDs."""

    if (
        not isinstance(marker_ids, Sequence)
        or isinstance(marker_ids, (str, bytes))
        or len(marker_ids) != 4
        or any(not isinstance(marker_id, str) or not marker_id for marker_id in marker_ids)
        or len(set(marker_ids)) != 4
    ):
        raise HomographyError("marker_ids must contain four unique non-empty IDs.")
    for name, value in (
        ("layout_id", layout_id),
        ("canonical_camera_pose_id", canonical_camera_pose_id),
    ):
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise HomographyError(f"{name} must be a non-empty trimmed string.")
    if not isinstance(image_points_by_marker, Mapping) or not isinstance(
        world_points_by_marker, Mapping
    ):
        raise HomographyError("Image and world marker points must be mappings.")
    if set(image_points_by_marker) != set(marker_ids):
        raise HomographyError("Image marker IDs must exactly match marker_ids.")
    if set(world_points_by_marker) != set(marker_ids):
        raise HomographyError("World marker IDs must exactly match marker_ids.")
    if (
        not isinstance(pivot_tolerance, (int, float))
        or isinstance(pivot_tolerance, bool)
        or not math.isfinite(float(pivot_tolerance))
        or pivot_tolerance <= 0
    ):
        raise HomographyError("pivot_tolerance must be finite and positive.")
    binding = {
        "resolution_id": resolution_id,
        "image_width_px": image_width_px,
        "image_height_px": image_height_px,
        "source_correspondence_hash": source_correspondence_hash,
        "detector_version": detector_version,
        "software_runtime_hash": software_runtime_hash,
    }
    if any(value is None for value in binding.values()) and any(
        value is not None for value in binding.values()
    ):
        raise HomographyError("Production homography identity must be all-or-none.")
    if all(value is not None for value in binding.values()):
        if (
            not isinstance(resolution_id, str)
            or not resolution_id.strip()
            or not isinstance(detector_version, str)
            or not detector_version.strip()
        ):
            raise HomographyError("Resolution and detector IDs must be non-empty.")
        for name, value in (
            ("image_width_px", image_width_px),
            ("image_height_px", image_height_px),
        ):
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value <= 0
            ):
                raise HomographyError(f"{name} must be a positive integer.")
        for name, value in (
            ("source_correspondence_hash", source_correspondence_hash),
            ("software_runtime_hash", software_runtime_hash),
        ):
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise HomographyError(f"{name} must be lowercase SHA-256.")

    image_points = [
        _finite_pair(image_points_by_marker[marker_id], f"image point {marker_id}")
        for marker_id in marker_ids
    ]
    world_points = [
        _finite_pair(world_points_by_marker[marker_id], f"world point {marker_id}")
        for marker_id in marker_ids
    ]
    if len(set(image_points)) != 4 or len(set(world_points)) != 4:
        raise HomographyError("Marker coordinates must be unique in both spaces.")

    matrix: list[list[float]] = []
    right_hand_side: list[float] = []
    for (x, y), (world_x, world_z) in zip(
        image_points, world_points, strict=True
    ):
        matrix.append([x, y, 1.0, 0.0, 0.0, 0.0, -world_x * x, -world_x * y])
        right_hand_side.append(world_x)
        matrix.append([0.0, 0.0, 0.0, x, y, 1.0, -world_z * x, -world_z * y])
        right_hand_side.append(world_z)
    solution = _solve_square_system(
        matrix,
        right_hand_side,
        pivot_tolerance=float(pivot_tolerance),
    )
    fitted_matrix = (
        (solution[0], solution[1], solution[2]),
        (solution[3], solution[4], solution[5]),
        (solution[6], solution[7], 1.0),
    )
    fit_payload = {
        "algorithm_version": HOMOGRAPHY_ALGORITHM_VERSION,
        "layout_id": layout_id,
        "canonical_camera_pose_id": canonical_camera_pose_id,
        "pivot_tolerance": float(pivot_tolerance),
        "image_coordinate_convention": "pixel_center_xy_zero_based",
        "world_coordinate_convention": "ground_plane_world_xz_blocks",
        "marker_ids": list(marker_ids),
        "image_points": [list(point) for point in image_points],
        "world_points": [list(point) for point in world_points],
        "matrix": [list(row) for row in fitted_matrix],
        **binding,
    }
    fit_hash = hashlib.sha256(
        json.dumps(
            fit_payload,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    marker_tuple = (marker_ids[0], marker_ids[1], marker_ids[2], marker_ids[3])
    homography = Homography(
        matrix=fitted_matrix,
        marker_ids=marker_tuple,
        layout_id=layout_id,
        canonical_camera_pose_id=canonical_camera_pose_id,
        fit_hash=fit_hash,
        pivot_tolerance=float(pivot_tolerance),
        denominator_tolerance=float(pivot_tolerance),
        resolution_id=resolution_id,
        image_width_px=image_width_px,
        image_height_px=image_height_px,
        source_correspondence_hash=source_correspondence_hash,
        detector_version=detector_version,
        software_runtime_hash=software_runtime_hash,
    )
    for image_point, expected_world in zip(image_points, world_points, strict=True):
        predicted = homography.transform(image_point)
        if not all(
            math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9)
            for actual, expected in zip(predicted, expected_world, strict=True)
        ):
            raise HomographyError("Fitted homography does not reproduce marker points.")
    return homography


def validate_homography_fixture(
    document: Mapping[str, Any],
    *,
    required_context: Mapping[str, Any] | None = None,
) -> Homography:
    """Validate a resolution- and camera-bound four-marker fixture.

    The fitted :class:`Homography` remains the numerical implementation.  This
    wrapper freezes the Phase 1 provenance needed to decide whether that fit may
    be reused for a particular layout, camera pose, and decoded resolution.
    """

    if not isinstance(document, Mapping):
        raise HomographyError("Homography fixture must be a mapping.")
    fields = {
        "schema_version",
        "homography_fixture_schema_version",
        "fixture_id",
        "synthetic",
        "scientific_use",
        "layout_id",
        "canonical_camera_pose_id",
        "resolution_id",
        "image_width_px",
        "image_height_px",
        "image_coordinate_system",
        "world_coordinate_system",
        "marker_correspondences",
        "expected_probe",
    }
    if set(document) != fields:
        raise HomographyError("Homography fixture fields have changed.")
    if document["schema_version"] != "1.0":
        raise HomographyError("schema_version must remain '1.0'.")
    fixture_version = document["homography_fixture_schema_version"]
    if fixture_version not in SUPPORTED_HOMOGRAPHY_FIXTURE_SCHEMA_VERSIONS:
        raise HomographyError("Unsupported homography fixture schema.")
    for field in (
        "fixture_id",
        "layout_id",
        "canonical_camera_pose_id",
        "resolution_id",
    ):
        value = document[field]
        if not isinstance(value, str) or not value or value != value.strip():
            raise HomographyError(f"{field} must be a non-empty trimmed ID.")
    if not isinstance(document["synthetic"], bool):
        raise HomographyError("synthetic must be boolean.")
    if document["scientific_use"] not in {"forbidden", "permitted"}:
        raise HomographyError("scientific_use is invalid.")
    if document["synthetic"] and document["scientific_use"] != "forbidden":
        raise HomographyError("Synthetic homography evidence forbids scientific use.")
    for field in ("image_width_px", "image_height_px"):
        value = document[field]
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise HomographyError(f"{field} must be a positive integer.")
    if document["image_coordinate_system"] != "pixel_center_xy_zero_based":
        raise HomographyError("Unsupported image-coordinate convention.")
    if document["world_coordinate_system"] != "ground_plane_world_xz_blocks":
        raise HomographyError("Unsupported world-coordinate convention.")

    context_fields = {
        "layout_id",
        "canonical_camera_pose_id",
        "resolution_id",
        "image_width_px",
        "image_height_px",
        "image_coordinate_system",
    }
    if required_context is not None:
        if not isinstance(required_context, Mapping) or set(required_context) != context_fields:
            raise HomographyError("required_context fields have changed.")
        mismatches = sorted(
            field
            for field in context_fields
            if required_context[field] != document[field]
        )
        if mismatches:
            raise HomographyError(
                "Homography reuse context mismatch: " + ", ".join(mismatches) + "."
            )

    markers = document["marker_correspondences"]
    if not isinstance(markers, list) or len(markers) != 4:
        raise HomographyError("Exactly four marker correspondences are required.")
    marker_ids: list[str] = []
    marker_roles: list[str] = []
    image_points: dict[str, tuple[float, float]] = {}
    world_points: dict[str, tuple[float, float]] = {}
    marker_id_by_role: dict[str, str] = {}
    for index, marker in enumerate(markers):
        if not isinstance(marker, Mapping) or set(marker) != {
            "marker_id",
            "marker_role",
            "marker_kind",
            "image_xy",
            "world_xz_blocks",
        }:
            raise HomographyError(f"marker_correspondences[{index}] fields changed.")
        marker_id = marker["marker_id"]
        role = marker["marker_role"]
        if not isinstance(marker_id, str) or not marker_id or marker_id != marker_id.strip():
            raise HomographyError("marker_id must be a non-empty stable identity.")
        if role not in CANONICAL_MARKER_ROLES:
            raise HomographyError("Unknown canonical marker_role.")
        if fixture_version == HOMOGRAPHY_FIXTURE_SCHEMA_VERSION and marker_id != role:
            raise HomographyError("Marker IDs must use the canonical corner roles.")
        if marker["marker_kind"] != "non_magenta_geometry_marker":
            raise HomographyError("Homography markers must be explicitly non-magenta.")
        if marker_id in marker_ids:
            raise HomographyError(f"Duplicate marker_id {marker_id!r}.")
        if role in marker_roles:
            raise HomographyError(f"Duplicate marker_role {role!r}.")
        image_point = _finite_pair(marker["image_xy"], f"marker {marker_id} image_xy")
        world_point = _finite_pair(
            marker["world_xz_blocks"], f"marker {marker_id} world_xz_blocks"
        )
        if not (
            0.0 <= image_point[0] < document["image_width_px"]
            and 0.0 <= image_point[1] < document["image_height_px"]
        ):
            raise HomographyError(f"Marker {marker_id!r} lies outside the image.")
        marker_ids.append(marker_id)
        marker_roles.append(role)
        marker_id_by_role[role] = marker_id
        image_points[marker_id] = image_point
        world_points[marker_id] = world_point
    if set(marker_roles) != CANONICAL_MARKER_ROLES:
        raise HomographyError("All four canonical marker roles are required.")
    if fixture_version == HOMOGRAPHY_FIXTURE_SCHEMA_VERSION and set(marker_ids) != CANONICAL_MARKER_ROLES:
        raise HomographyError("All four canonical marker IDs are required by v1.0.")

    def require_corner_roles(points: Mapping[str, tuple[float, float]], name: str) -> None:
        center_x = sum(point[0] for point in points.values()) / 4.0
        center_y = sum(point[1] for point in points.values()) / 4.0
        expected_signs = {
            "north_west": (-1, -1),
            "north_east": (1, -1),
            "south_east": (1, 1),
            "south_west": (-1, 1),
        }
        for marker_id, (x_sign, y_sign) in expected_signs.items():
            x, y = points[marker_id]
            if (x - center_x) * x_sign <= 0 or (y - center_y) * y_sign <= 0:
                raise HomographyError(
                    f"{name} marker correspondence for {marker_id!r} is inconsistent."
                )

    image_points_by_role = {
        role: image_points[marker_id_by_role[role]] for role in CANONICAL_MARKER_ROLES
    }
    world_points_by_role = {
        role: world_points[marker_id_by_role[role]] for role in CANONICAL_MARKER_ROLES
    }
    # The legacy v1.0 fixture explicitly encoded screen-corner semantics.  In
    # v1.1 marker_role is a world-geometric role; a rotated camera may place a
    # role in any image quadrant, so only world geometry is role-constrained.
    if fixture_version == HOMOGRAPHY_FIXTURE_SCHEMA_VERSION:
        require_corner_roles(image_points_by_role, "Image")
    require_corner_roles(world_points_by_role, "World")
    ordered_marker_ids = tuple(
        marker_id_by_role[role]
        for role in ("north_west", "north_east", "south_east", "south_west")
    )
    homography = fit_marker_homography(
        image_points,
        world_points,
        marker_ids=ordered_marker_ids,
        layout_id=document["layout_id"],
        canonical_camera_pose_id=document["canonical_camera_pose_id"],
    )
    probe = document["expected_probe"]
    if not isinstance(probe, Mapping) or set(probe) != {
        "image_xy",
        "world_xz_blocks",
        "absolute_tolerance_blocks",
    }:
        raise HomographyError("expected_probe fields have changed.")
    probe_image = _finite_pair(probe["image_xy"], "expected_probe.image_xy")
    expected_world = _finite_pair(
        probe["world_xz_blocks"], "expected_probe.world_xz_blocks"
    )
    tolerance = probe["absolute_tolerance_blocks"]
    if (
        not isinstance(tolerance, (int, float))
        or isinstance(tolerance, bool)
        or not math.isfinite(float(tolerance))
        or tolerance <= 0.0
    ):
        raise HomographyError("expected_probe tolerance must be finite and positive.")
    actual_world = homography.transform(probe_image)
    if any(
        not math.isclose(actual, expected, rel_tol=0.0, abs_tol=float(tolerance))
        for actual, expected in zip(actual_world, expected_world, strict=True)
    ):
        raise HomographyError("Known synthetic transform probe was not recovered.")
    return homography


def _percentile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise HomographyError("Cannot summarize an empty localization sample.")
    position = (len(ordered) - 1) * probability
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    weight = position - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def summarize_localization(
    homography: Homography,
    validation_pairs: Sequence[tuple[Sequence[float], Sequence[float]]],
    *,
    wall_parallel_origin_xz: Sequence[float],
    wall_parallel_positive_unit_xz: Sequence[float],
    image_regions: Sequence[str] | None = None,
    maximum_median_wall_error_blocks: float = 0.2,
    maximum_p95_wall_error_blocks: float = 0.5,
    minimum_shift_error_multiplier: float = 2.0,
) -> dict[str, Any]:
    """Report signed/absolute wall error and Euclidean held-out error."""

    if not isinstance(homography, Homography):
        raise HomographyError("homography must be a Homography instance.")
    if (
        not isinstance(validation_pairs, Sequence)
        or isinstance(validation_pairs, (str, bytes))
        or not validation_pairs
    ):
        raise HomographyError("At least one held-out validation pair is required.")
    if image_regions is not None and (
        not isinstance(image_regions, Sequence)
        or isinstance(image_regions, (str, bytes))
        or len(image_regions) != len(validation_pairs)
        or any(not isinstance(region, str) or not region for region in image_regions)
    ):
        raise HomographyError(
            "image_regions must be null or one non-empty label per validation pair."
        )
    origin = _finite_pair(wall_parallel_origin_xz, "wall_parallel_origin_xz")
    unit = _finite_pair(
        wall_parallel_positive_unit_xz,
        "wall_parallel_positive_unit_xz",
    )
    norm = math.hypot(*unit)
    if not math.isclose(norm, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise HomographyError("Wall-parallel direction must be a unit vector.")
    for name, value in (
        ("maximum_median_wall_error_blocks", maximum_median_wall_error_blocks),
        ("maximum_p95_wall_error_blocks", maximum_p95_wall_error_blocks),
        ("minimum_shift_error_multiplier", minimum_shift_error_multiplier),
    ):
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            or float(value) <= 0.0
        ):
            raise HomographyError(f"{name} must be finite and positive.")

    records: list[dict[str, Any]] = []
    for index, pair in enumerate(validation_pairs):
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise HomographyError(
                f"Validation pair {index} must be (image_xy, true_world_xz)."
            )
        image_xy = _finite_pair(pair[0], f"validation image point {index}")
        true_world = _finite_pair(pair[1], f"validation world point {index}")
        predicted = homography.transform(image_xy)
        error_x = predicted[0] - true_world[0]
        error_z = predicted[1] - true_world[1]
        signed_wall_error = error_x * unit[0] + error_z * unit[1]
        predicted_coordinate = (
            (predicted[0] - origin[0]) * unit[0]
            + (predicted[1] - origin[1]) * unit[1]
        )
        true_coordinate = (
            (true_world[0] - origin[0]) * unit[0]
            + (true_world[1] - origin[1]) * unit[1]
        )
        records.append(
            {
                "sample_index": index,
                "image_xy": list(image_xy),
                "true_world_xz": list(true_world),
                "predicted_world_xz": list(predicted),
                "true_wall_parallel_blocks": true_coordinate,
                "predicted_wall_parallel_blocks": predicted_coordinate,
                "signed_wall_parallel_error_blocks": signed_wall_error,
                "absolute_wall_parallel_error_blocks": abs(signed_wall_error),
                "euclidean_error_blocks": math.hypot(error_x, error_z),
                "image_region": (
                    None if image_regions is None else image_regions[index]
                ),
            }
        )
    absolute_wall = [row["absolute_wall_parallel_error_blocks"] for row in records]
    euclidean = [row["euclidean_error_blocks"] for row in records]
    by_image_region: dict[str, dict[str, float | int]] = {}
    if image_regions is not None:
        for region in sorted(set(image_regions)):
            region_rows = [row for row in records if row["image_region"] == region]
            region_wall = [
                row["absolute_wall_parallel_error_blocks"] for row in region_rows
            ]
            region_euclidean = [row["euclidean_error_blocks"] for row in region_rows]
            by_image_region[region] = {
                "sample_count": len(region_rows),
                "median_absolute_wall_parallel_error_blocks": _percentile(
                    region_wall, 0.5
                ),
                "p95_absolute_wall_parallel_error_blocks": _percentile(
                    region_wall, 0.95
                ),
                "median_euclidean_error_blocks": _percentile(
                    region_euclidean, 0.5
                ),
                "p95_euclidean_error_blocks": _percentile(
                    region_euclidean, 0.95
                ),
            }
    median_wall = _percentile(absolute_wall, 0.5)
    p95_wall = _percentile(absolute_wall, 0.95)
    planning_gate_passed = (
        median_wall <= float(maximum_median_wall_error_blocks)
        and p95_wall < float(maximum_p95_wall_error_blocks)
    )
    return {
        "homography_fit_hash": homography.fit_hash,
        "homography_version_id": homography.to_record()["homography_version_id"],
        "percentile_method": PERCENTILE_METHOD,
        "sample_count": len(records),
        "median_absolute_wall_parallel_error_blocks": median_wall,
        "p95_absolute_wall_parallel_error_blocks": p95_wall,
        "median_euclidean_error_blocks": _percentile(euclidean, 0.5),
        "p95_euclidean_error_blocks": _percentile(euclidean, 0.95),
        "planning_gate_passed": planning_gate_passed,
        "minimum_shift_if_gate_fails_blocks": (
            None
            if planning_gate_passed
            else float(minimum_shift_error_multiplier) * p95_wall
        ),
        "by_image_region": by_image_region,
        "records": records,
    }
