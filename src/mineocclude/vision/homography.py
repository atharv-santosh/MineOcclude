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
PERCENTILE_METHOD = "linear_interpolation_rank_n_minus_1"
CANONICAL_MARKER_ROLES = frozenset(
    {"north_west", "north_east", "south_east", "south_west"}
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
        }


def homography_from_record(record: Mapping[str, Any]) -> Homography:
    """Reconstruct a fitted homography from a versioned report record."""

    if not isinstance(record, Mapping):
        raise HomographyError("Homography record must be a mapping.")
    required = {
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
    if set(record) != required:
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
    return Homography(
        matrix=normalized_matrix,  # type: ignore[arg-type]
        marker_ids=tuple(marker_ids),  # type: ignore[arg-type]
        layout_id=record["layout_id"],
        canonical_camera_pose_id=record["canonical_camera_pose_id"],
        fit_hash=fit_hash,
        pivot_tolerance=float(record["pivot_tolerance"]),
        denominator_tolerance=float(record["denominator_tolerance"]),
    )


def fit_marker_homography(
    image_points_by_marker: Mapping[str, Sequence[float]],
    world_points_by_marker: Mapping[str, Sequence[float]],
    *,
    marker_ids: Sequence[str],
    layout_id: str,
    canonical_camera_pose_id: str,
    pivot_tolerance: float = 1e-12,
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
    if document["homography_fixture_schema_version"] != HOMOGRAPHY_FIXTURE_SCHEMA_VERSION:
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
    image_points: dict[str, tuple[float, float]] = {}
    world_points: dict[str, tuple[float, float]] = {}
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
        if (
            not isinstance(marker_id, str)
            or not marker_id
            or role not in CANONICAL_MARKER_ROLES
            or marker_id != role
        ):
            raise HomographyError("Marker IDs must use the canonical corner roles.")
        if marker["marker_kind"] != "non_magenta_geometry_marker":
            raise HomographyError("Homography markers must be explicitly non-magenta.")
        if marker_id in marker_ids:
            raise HomographyError(f"Duplicate marker_id {marker_id!r}.")
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
        image_points[marker_id] = image_point
        world_points[marker_id] = world_point
    if set(marker_ids) != CANONICAL_MARKER_ROLES:
        raise HomographyError("All four canonical marker roles are required.")

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

    require_corner_roles(image_points, "Image")
    require_corner_roles(world_points, "World")
    homography = fit_marker_homography(
        image_points,
        world_points,
        marker_ids=("north_west", "north_east", "south_east", "south_west"),
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
