"""Validate Attempt 02 annotations and build the six-layout E refit package."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from itertools import combinations
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import annotate_person_e_homography_refit_attempt_02 as annotation_tool
from mineocclude.vision.config import validate_person_e_config
from mineocclude.vision.homography import (
    HOMOGRAPHY_ALGORITHM_VERSION,
    fit_marker_homography,
    summarize_localization,
)


PACKAGE_DIR = (
    ROOT
    / "data"
    / "handoff_e"
    / "person_e_v0_4_homography_refit_v0_1"
)
ANNOTATION_PATH = PACKAGE_DIR / "person_e_attempt_02_image_points_v0_1.json"
ANNOTATION_SHA256 = (
    "9747e1dc9a497d29df8aaff83fc605465a980a73edfaddee1f43d6e8a92671c0"
)
C_HANDOFF_PATH = annotation_tool.DEFAULT_HANDOFF
C_HANDOFF_SHA256 = annotation_tool.EXPECTED_HANDOFF_SHA256
CONFIG_PATH = ROOT / "configs" / "vision" / "person_e_phase1.yaml"
REQUIRED_ANCESTRY = "7abc55af9c7d5bb2cbe855250670143f535fce19"
ANNOTATION_SCHEMA_VERSION = (
    "person-e-v0.4-image-point-annotations-attempt-02-v0.2"
)
PACKAGE_SCHEMA_VERSION = "person-e-v0.4-homography-refit-package-v0.1"
HANDOFF_SCHEMA_VERSION = "person-e-to-person-c-v0.4-refit-handoff-v0.1"
RESOLUTION_ID = "framebuffer_1920x1046_rgb8"
HISTORICAL_HOMOGRAPHIES = (
    ROOT / "docs" / "status" / "person_e_phase2_v0_1" / "homography_record.json",
    ROOT
    / "docs"
    / "status"
    / "person_e_phase2_step2_4_v0_2"
    / "homography_record.json",
    ROOT
    / "docs"
    / "status"
    / "person_e_phase2_step2_4_v0_3"
    / "homography_record.json",
    ROOT
    / "docs"
    / "status"
    / "person_e_phase2_step2_4_v0_4"
    / "homography_record.json",
)


class RefitFinalizeError(ValueError):
    """Raised when annotation, fit, or package validation fails closed."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_json_value(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RefitFinalizeError(f"{path} must contain a JSON object.")
    return value


def _full_git_sha(value: str, label: str) -> str:
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise RefitFinalizeError(f"{label} must be a full lowercase Git SHA.")
    return value


def current_git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return _full_git_sha(result.stdout.strip(), "current Git commit")


def _point_pair(value: Any, label: str) -> list[float]:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(
            not isinstance(coordinate, (int, float))
            or isinstance(coordinate, bool)
            or not math.isfinite(float(coordinate))
            for coordinate in value
        )
    ):
        raise RefitFinalizeError(f"{label} must be a finite coordinate pair.")
    return [float(value[0]), float(value[1])]


def _no_three_collinear(points: list[list[float]]) -> bool:
    if len(points) != 4 or len({tuple(point) for point in points}) != 4:
        return False
    for first, second, third in combinations(points, 3):
        twice_area = (
            (second[0] - first[0]) * (third[1] - first[1])
            - (second[1] - first[1]) * (third[0] - first[0])
        )
        if abs(twice_area) <= 1e-12:
            return False
    return True


def validate_annotation(
    document: dict[str, Any],
    verified_sources: dict[str, Any],
    expected_tasks: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    if sha256_file(ANNOTATION_PATH) != ANNOTATION_SHA256:
        raise RefitFinalizeError("Completed annotation SHA-256 changed.")
    required_root = {
        "accepted_geometry_sha256",
        "accepted_geometry_version",
        "annotation_method",
        "annotation_schema_version",
        "created_utc",
        "framebuffer",
        "image_coordinate_convention",
        "immutable_after_creation",
        "layouts",
        "person_e_source_commit",
        "schema_version",
        "source_handoff",
        "source_verification",
        "status",
    }
    if set(document) != required_root:
        raise RefitFinalizeError("Annotation root fields changed.")
    if (
        document["schema_version"] != "1.0"
        or document["annotation_schema_version"] != ANNOTATION_SCHEMA_VERSION
        or document["status"] != "IMAGE_POINTS_COMPLETE_PENDING_HOMOGRAPHY_FIT"
        or document["immutable_after_creation"] is not True
        or document["person_e_source_commit"] != REQUIRED_ANCESTRY
        or document["accepted_geometry_version"]
        != annotation_tool.EXPECTED_GEOMETRY_VERSION
        or document["accepted_geometry_sha256"]
        != annotation_tool.EXPECTED_GEOMETRY_SHA256
        or document["framebuffer"]
        != {"height_pixels": 1046, "width_pixels": 1920}
        or document["image_coordinate_convention"]
        != "pixel_center_xy_zero_based"
    ):
        raise RefitFinalizeError("Annotation authority or coordinate contract changed.")
    source_handoff = document["source_handoff"]
    if (
        not isinstance(source_handoff, dict)
        or source_handoff.get("path") != str(C_HANDOFF_PATH)
        or source_handoff.get("sha256") != C_HANDOFF_SHA256
    ):
        raise RefitFinalizeError("Annotation source handoff binding changed.")
    method = document["annotation_method"]
    if (
        not isinstance(method, dict)
        or method.get("algorithm_id") != annotation_tool.ANNOTATION_METHOD
        or method.get("coordinate_transform") != "none"
        or method.get("operator_final_confirmation") is not True
        or method.get("visibility_preflight", {}).get("status") != "passed"
        or method.get("visibility_preflight", {}).get(
            "fully_occluded_or_ambiguous_points_requested"
        )
        != 0
    ):
        raise RefitFinalizeError("Annotation method or visibility preflight changed.")

    layouts = document["layouts"]
    if not isinstance(layouts, list):
        raise RefitFinalizeError("Annotation layouts must be a list.")
    layout_by_id: dict[str, dict[str, Any]] = {}
    for layout in layouts:
        if not isinstance(layout, dict) or not isinstance(layout.get("layout_id"), str):
            raise RefitFinalizeError("Annotation contains a malformed layout.")
        if layout["layout_id"] in layout_by_id:
            raise RefitFinalizeError("Annotation duplicates a layout identity.")
        layout_by_id[layout["layout_id"]] = layout
    if tuple(sorted(layout_by_id)) != annotation_tool.EXPECTED_LAYOUT_IDS:
        raise RefitFinalizeError("Annotation layout identities changed.")
    tasks_by_layout = {
        layout_id: [task for task in expected_tasks if task["layout_id"] == layout_id]
        for layout_id in annotation_tool.EXPECTED_LAYOUT_IDS
    }
    screenshots = {
        row["layout_id"]: row for row in verified_sources["screenshots"]
    }
    for layout_id in annotation_tool.EXPECTED_LAYOUT_IDS:
        layout = layout_by_id[layout_id]
        if layout.get("screenshot") != screenshots[layout_id]:
            raise RefitFinalizeError(f"{layout_id} screenshot binding changed.")
        fit = layout.get("fit_correspondences")
        validation = layout.get("independent_validation_points")
        if not isinstance(fit, list) or len(fit) != 4:
            raise RefitFinalizeError(f"{layout_id} requires four fit points.")
        if not isinstance(validation, list) or len(validation) != 1:
            raise RefitFinalizeError(
                f"{layout_id} requires one independent validation point."
            )
        records = fit + validation
        record_by_id: dict[str, dict[str, Any]] = {}
        for record in records:
            if not isinstance(record, dict) or not isinstance(record.get("point_id"), str):
                raise RefitFinalizeError(f"{layout_id} has a malformed point.")
            if record["point_id"] in record_by_id:
                raise RefitFinalizeError(f"{layout_id} duplicates a point identity.")
            record_by_id[record["point_id"]] = record
        expected_ids = {task["point_id"] for task in tasks_by_layout[layout_id]}
        if set(record_by_id) != expected_ids or "far_west" in record_by_id:
            raise RefitFinalizeError(
                f"{layout_id} uses a missing, hidden, or historical point."
            )
        fit_ids = {record["point_id"] for record in fit}
        validation_ids = {record["point_id"] for record in validation}
        if fit_ids & validation_ids:
            raise RefitFinalizeError(f"{layout_id} validation is not independent.")
        for task in tasks_by_layout[layout_id]:
            record = record_by_id[task["point_id"]]
            image_xy = _point_pair(
                record.get("image_xy_pixels"),
                f"{layout_id} {task['point_id']} image point",
            )
            world_xz = _point_pair(
                record.get("world_xz_blocks"),
                f"{layout_id} {task['point_id']} world point",
            )
            if not (0.0 <= image_xy[0] < 1920.0 and 0.0 <= image_xy[1] < 1046.0):
                raise RefitFinalizeError(
                    f"{layout_id} {task['point_id']} lies outside the framebuffer."
                )
            if (
                world_xz != [float(value) for value in task["world_xz_blocks"]]
                or record.get("source_kind") != task["source_kind"]
                or record.get("marker_color") != task["marker_color"]
                or record.get("visibility_status") != "visible_unambiguous"
                or record.get("selection_status") != "operator_selected"
            ):
                raise RefitFinalizeError(
                    f"{layout_id} {task['point_id']} disagrees with accepted geometry."
                )
            expected_kind = (
                "fit_correspondence"
                if record in fit
                else "independent_validation"
            )
            if task["kind"] != expected_kind:
                raise RefitFinalizeError(
                    f"{layout_id} {task['point_id']} changed fit/validation role."
                )
        if not _no_three_collinear(
            [_point_pair(point["world_xz_blocks"], "fit world") for point in fit]
        ) or not _no_three_collinear(
            [_point_pair(point["image_xy_pixels"], "fit image") for point in fit]
        ):
            raise RefitFinalizeError(
                f"{layout_id} fit points are duplicate or collinear."
            )
    return layout_by_id


def load_validated_inputs() -> dict[str, Any]:
    if not ANNOTATION_PATH.is_file():
        raise RefitFinalizeError(f"Completed annotation is missing: {ANNOTATION_PATH}")
    if sha256_file(C_HANDOFF_PATH) != C_HANDOFF_SHA256:
        raise RefitFinalizeError("Person C handoff SHA-256 changed.")
    verified_sources = annotation_tool.verify_sources(C_HANDOFF_PATH)
    tasks = annotation_tool.build_tasks(verified_sources)
    annotation = load_json(ANNOTATION_PATH)
    layouts = validate_annotation(annotation, verified_sources, tasks)
    config = load_json(CONFIG_PATH)
    validate_person_e_config(config)
    return {
        "annotation": annotation,
        "annotation_layouts": layouts,
        "verified_sources": verified_sources,
        "tasks": tasks,
        "config": config,
        "config_sha256": sha256_file(CONFIG_PATH),
    }


def determinant(matrix: list[list[float]]) -> float:
    return (
        matrix[0][0]
        * (matrix[1][1] * matrix[2][2] - matrix[1][2] * matrix[2][1])
        - matrix[0][1]
        * (matrix[1][0] * matrix[2][2] - matrix[1][2] * matrix[2][0])
        + matrix[0][2]
        * (matrix[1][0] * matrix[2][1] - matrix[1][1] * matrix[2][0])
    )


def inverse_matrix(matrix: list[list[float]]) -> list[list[float]]:
    value = determinant(matrix)
    if not math.isfinite(value) or abs(value) <= 1e-15:
        raise RefitFinalizeError("Homography matrix is singular.")
    a, b, c = matrix[0]
    d, e, f = matrix[1]
    g, h, i = matrix[2]
    return [
        [(e * i - f * h) / value, (c * h - b * i) / value, (b * f - c * e) / value],
        [(f * g - d * i) / value, (a * i - c * g) / value, (c * d - a * f) / value],
        [(d * h - e * g) / value, (b * g - a * h) / value, (a * e - b * d) / value],
    ]


def matrix_rank(matrix: list[list[float]], tolerance: float = 1e-12) -> int:
    work = [row[:] for row in matrix]
    rows = len(work)
    columns = len(work[0])
    rank = 0
    for column in range(columns):
        pivot = max(range(rank, rows), key=lambda row: abs(work[row][column]))
        if abs(work[pivot][column]) <= tolerance:
            continue
        work[rank], work[pivot] = work[pivot], work[rank]
        pivot_value = work[rank][column]
        for index in range(column, columns):
            work[rank][index] /= pivot_value
        for row in range(rows):
            if row == rank:
                continue
            factor = work[row][column]
            for index in range(column, columns):
                work[row][index] -= factor * work[rank][index]
        rank += 1
        if rank == rows:
            break
    return rank


def infinity_condition_number(
    matrix: list[list[float]], inverse: list[list[float]]
) -> float:
    norm = max(sum(abs(value) for value in row) for row in matrix)
    inverse_norm = max(sum(abs(value) for value in row) for row in inverse)
    return norm * inverse_norm


def project(matrix: list[list[float]], point: list[float]) -> list[float]:
    denominator = matrix[2][0] * point[0] + matrix[2][1] * point[1] + matrix[2][2]
    if not math.isfinite(denominator) or abs(denominator) <= 1e-12:
        raise RefitFinalizeError("Projective denominator is singular at a point.")
    return [
        (matrix[0][0] * point[0] + matrix[0][1] * point[1] + matrix[0][2])
        / denominator,
        (matrix[1][0] * point[0] + matrix[1][1] * point[1] + matrix[1][2])
        / denominator,
    ]


def _residual_record(
    homography: Any,
    inverse: list[list[float]],
    point: dict[str, Any],
) -> dict[str, Any]:
    image = _point_pair(point["image_xy_pixels"], "residual image point")
    world = _point_pair(point["world_xz_blocks"], "residual world point")
    predicted_world = list(homography.transform(image))
    reprojected_image = project(inverse, world)
    return {
        "point_id": point["point_id"],
        "image_xy_pixels": image,
        "world_xz_blocks": world,
        "predicted_world_xz_blocks": predicted_world,
        "world_euclidean_error_blocks": math.dist(predicted_world, world),
        "reprojected_image_xy_pixels": reprojected_image,
        "reprojection_error_pixels": math.dist(reprojected_image, image),
    }


def fit_all(inputs: dict[str, Any], code_sha: str) -> dict[str, Any]:
    _full_git_sha(code_sha, "code_sha")
    config = inputs["config"]
    homography_config = config["homography"]
    homography_implementation = ROOT / "src" / "mineocclude" / "vision" / "homography.py"
    implementation_hash = sha256_file(homography_implementation)
    layouts: list[dict[str, Any]] = []
    for layout_id in annotation_tool.EXPECTED_LAYOUT_IDS:
        layout = inputs["annotation_layouts"][layout_id]
        fit_points = layout["fit_correspondences"]
        validation_points = layout["independent_validation_points"]
        marker_ids = [point["point_id"] for point in fit_points]
        image_points = {
            point["point_id"]: point["image_xy_pixels"] for point in fit_points
        }
        world_points = {
            point["point_id"]: point["world_xz_blocks"] for point in fit_points
        }
        correspondence_hash = hash_json_value(
            {
                "layout_id": layout_id,
                "fit_correspondences": fit_points,
                "annotation_sha256": ANNOTATION_SHA256,
            }
        )
        homography = fit_marker_homography(
            image_points,
            world_points,
            marker_ids=marker_ids,
            layout_id=layout_id,
            canonical_camera_pose_id=f"{layout_id}_canonical_pose_v1",
            pivot_tolerance=float(homography_config["singular_pivot_tolerance"]),
            resolution_id=RESOLUTION_ID,
            image_width_px=1920,
            image_height_px=1046,
            source_correspondence_hash=correspondence_hash,
            detector_version=annotation_tool.ANNOTATION_METHOD,
            software_runtime_hash=implementation_hash,
        )
        matrix = [list(row) for row in homography.matrix]
        inverse = inverse_matrix(matrix)
        matrix_determinant = determinant(matrix)
        rank = matrix_rank(matrix)
        condition = infinity_condition_number(matrix, inverse)
        fit_residuals = [
            _residual_record(homography, inverse, point) for point in fit_points
        ]
        validation_residuals = [
            _residual_record(homography, inverse, point)
            for point in validation_points
        ]
        negative = world_points["wall_near_face_ground_negative_end"]
        positive = validation_points[0]["world_xz_blocks"]
        span = math.dist(negative, positive)
        wall_unit = [
            (positive[0] - negative[0]) / span,
            (positive[1] - negative[1]) / span,
        ]
        heldout = summarize_localization(
            homography,
            [
                (point["image_xy_pixels"], point["world_xz_blocks"])
                for point in validation_points
            ],
            wall_parallel_origin_xz=negative,
            wall_parallel_positive_unit_xz=wall_unit,
            image_regions=["opposite_wall_endpoint" for _ in validation_points],
            maximum_median_wall_error_blocks=float(
                homography_config["maximum_median_wall_parallel_error_blocks"]
            ),
            maximum_p95_wall_error_blocks=float(
                homography_config["maximum_p95_wall_parallel_error_blocks"]
            ),
            minimum_shift_error_multiplier=float(
                homography_config["minimum_shift_error_multiplier_on_gate_failure"]
            ),
        )
        roundtrip: list[dict[str, Any]] = []
        for point in fit_points + validation_points:
            image = _point_pair(point["image_xy_pixels"], "roundtrip image point")
            mapped_world = list(homography.transform(image))
            mapped_image = project(inverse, mapped_world)
            roundtrip.append(
                {
                    "point_id": point["point_id"],
                    "input_image_xy_pixels": image,
                    "roundtrip_image_xy_pixels": mapped_image,
                    "roundtrip_error_pixels": math.dist(mapped_image, image),
                }
            )
        validation_point = validation_points[0]["image_xy_pixels"]
        true_world = validation_points[0]["world_xz_blocks"]
        mirrored_world = list(
            homography.transform([1919.0 - validation_point[0], validation_point[1]])
        )
        transposed_point = [validation_point[1], validation_point[0]]
        transposed_inside = (
            0.0 <= transposed_point[0] < 1920.0
            and 0.0 <= transposed_point[1] < 1046.0
        )
        transposed_error = (
            math.dist(list(homography.transform(transposed_point)), true_world)
            if transposed_inside
            else None
        )
        actual_validation_error = validation_residuals[0][
            "world_euclidean_error_blocks"
        ]
        coordinate_guard = (
            actual_validation_error < math.dist(mirrored_world, true_world)
            and (
                not transposed_inside
                or (
                    transposed_error is not None
                    and actual_validation_error < transposed_error
                )
            )
        )
        matrix_gate = (
            rank == 3
            and math.isfinite(matrix_determinant)
            and abs(matrix_determinant)
            > float(homography_config["singular_pivot_tolerance"])
            and math.isfinite(condition)
            and coordinate_guard
        )
        tolerance_pass = matrix_gate and heldout["planning_gate_passed"]
        layouts.append(
            {
                "schema_version": "person-e-v0.4-layout-homography-refit-v0.1",
                "layout_id": layout_id,
                "status": (
                    "PASS" if tolerance_pass else "FAIL_REPOSITORY_TOLERANCE"
                ),
                "source_code_commit": code_sha,
                "source_annotation_sha256": ANNOTATION_SHA256,
                "accepted_geometry_version": annotation_tool.EXPECTED_GEOMETRY_VERSION,
                "accepted_geometry_sha256": annotation_tool.EXPECTED_GEOMETRY_SHA256,
                "homography_algorithm": HOMOGRAPHY_ALGORITHM_VERSION,
                "matrix": matrix,
                "inverse_matrix": inverse,
                "determinant": matrix_determinant,
                "rank": rank,
                "condition_number": condition,
                "condition_number_method": "matrix_infinity_norm_v0.1",
                "homography": homography.to_record(),
                "fit_correspondence_count": len(fit_points),
                "fit_residuals": fit_residuals,
                "maximum_fit_reprojection_error_pixels": max(
                    row["reprojection_error_pixels"] for row in fit_residuals
                ),
                "independent_validation_count": len(validation_points),
                "independent_validation_residuals": validation_residuals,
                "maximum_independent_validation_error_pixels": max(
                    row["reprojection_error_pixels"]
                    for row in validation_residuals
                ),
                "heldout_localization": heldout,
                "roundtrip_residuals": roundtrip,
                "maximum_roundtrip_error_pixels": max(
                    row["roundtrip_error_pixels"] for row in roundtrip
                ),
                "coordinate_order_guard": {
                    "passed": coordinate_guard,
                    "mirrored_validation_error_blocks": math.dist(
                        mirrored_world, true_world
                    ),
                    "transposed_point_inside_frame": transposed_inside,
                    "transposed_validation_error_blocks": transposed_error,
                },
                "matrix_gate_passed": matrix_gate,
                "repository_tolerance_passed": heldout["planning_gate_passed"],
                "tolerance_result": tolerance_pass,
            }
        )
    return summarize_results(layouts, code_sha, inputs, implementation_hash)


def summarize_results(
    layouts: list[dict[str, Any]],
    code_sha: str,
    inputs: dict[str, Any],
    implementation_hash: str,
) -> dict[str, Any]:
    if len(layouts) != 6:
        raise RefitFinalizeError("Exactly six fitted layouts are required.")
    all_pass = all(layout["tolerance_result"] for layout in layouts)
    return {
        "schema_version": "person-e-v0.4-homography-refit-summary-v0.1",
        "status": "PASS" if all_pass else "FAIL_REPOSITORY_TOLERANCE",
        "source_code_commit": code_sha,
        "annotation_path": str(ANNOTATION_PATH),
        "annotation_sha256": ANNOTATION_SHA256,
        "person_c_handoff_path": str(C_HANDOFF_PATH),
        "person_c_handoff_sha256": C_HANDOFF_SHA256,
        "accepted_geometry_version": annotation_tool.EXPECTED_GEOMETRY_VERSION,
        "accepted_geometry_sha256": annotation_tool.EXPECTED_GEOMETRY_SHA256,
        "framebuffer": {"width_pixels": 1920, "height_pixels": 1046},
        "fov_degrees": 70.0,
        "homography_algorithm": HOMOGRAPHY_ALGORITHM_VERSION,
        "homography_implementation_sha256": implementation_hash,
        "config_path": str(CONFIG_PATH),
        "config_sha256": inputs["config_sha256"],
        "layout_count": len(layouts),
        "successor_homography_count": len(layouts),
        "passing_layout_count": sum(
            layout["tolerance_result"] for layout in layouts
        ),
        "all_tolerances_pass": all_pass,
        "maximum_reprojection_error_pixels": max(
            layout["maximum_fit_reprojection_error_pixels"] for layout in layouts
        ),
        "maximum_independent_validation_error_pixels": max(
            layout["maximum_independent_validation_error_pixels"]
            for layout in layouts
        ),
        "maximum_roundtrip_error_pixels": max(
            layout["maximum_roundtrip_error_pixels"] for layout in layouts
        ),
        "failed_layout_ids": [
            layout["layout_id"] for layout in layouts if not layout["tolerance_result"]
        ],
        "layouts": layouts,
    }


def _file_record(path: Path, *, relative_to_package: bool = False) -> dict[str, Any]:
    return {
        "path": (
            path.relative_to(PACKAGE_DIR).as_posix()
            if relative_to_package
            else str(path)
        ),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def write_json_exclusive(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, indent=2, sort_keys=True)
        stream.write("\n")


def write_text_exclusive(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def _historical_records() -> list[dict[str, Any]]:
    records = []
    for path in HISTORICAL_HOMOGRAPHIES:
        if not path.is_file():
            raise RefitFinalizeError(f"Historical homography is missing: {path}")
        records.append(_file_record(path))
    return records


def build_package_documents(
    summary: dict[str, Any], inputs: dict[str, Any]
) -> dict[str, Any]:
    historical = _historical_records()
    all_pass = summary["all_tolerances_pass"]
    source_manifest = {
        "schema_version": "person-e-v0.4-refit-source-handoff-v0.1",
        "person_c_handoff": _file_record(C_HANDOFF_PATH),
        "annotation": _file_record(ANNOTATION_PATH),
        "accepted_geometry_version": annotation_tool.EXPECTED_GEOMETRY_VERSION,
        "accepted_geometry_sha256": annotation_tool.EXPECTED_GEOMETRY_SHA256,
    }
    consumed = {
        "schema_version": "person-e-v0.4-refit-consumed-input-inventory-v0.1",
        "annotation": _file_record(ANNOTATION_PATH),
        "person_c_handoff": _file_record(C_HANDOFF_PATH),
        "config": _file_record(CONFIG_PATH),
        "screenshots": inputs["verified_sources"]["screenshots"],
        "geometry_receipts": inputs["verified_sources"]["receipts"],
        "historical_homographies_unchanged": historical,
    }
    coordinate = {
        "schema_version": "person-e-v0.4-refit-coordinate-convention-v0.1",
        "image_coordinate_convention": "pixel_center_xy_zero_based",
        "image_origin": "top_left_pixel_center",
        "image_x_direction": "right",
        "image_y_direction": "down",
        "world_coordinate_convention": "ground_plane_world_xz_blocks",
        "framebuffer": {"width_pixels": 1920, "height_pixels": 1046},
        "coordinate_transform": "none",
        "source": inputs["verified_sources"]["coordinate_convention_record"],
    }
    fit_summary = {
        key: value for key, value in summary.items() if key != "layouts"
    }
    fit_summary["layouts"] = [
        {
            "layout_id": layout["layout_id"],
            "status": layout["status"],
            "homography_version_id": layout["homography"]["homography_version_id"],
            "determinant": layout["determinant"],
            "rank": layout["rank"],
            "condition_number": layout["condition_number"],
            "tolerance_result": layout["tolerance_result"],
        }
        for layout in summary["layouts"]
    ]
    reprojection = {
        "schema_version": "person-e-v0.4-refit-reprojection-validation-v0.1",
        "maximum_reprojection_error_pixels": summary[
            "maximum_reprojection_error_pixels"
        ],
        "layouts": [
            {
                "layout_id": layout["layout_id"],
                "fit_residuals": layout["fit_residuals"],
                "maximum_fit_reprojection_error_pixels": layout[
                    "maximum_fit_reprojection_error_pixels"
                ],
            }
            for layout in summary["layouts"]
        ],
    }
    inverse = {
        "schema_version": "person-e-v0.4-refit-inverse-validation-v0.1",
        "maximum_independent_validation_error_pixels": summary[
            "maximum_independent_validation_error_pixels"
        ],
        "maximum_roundtrip_error_pixels": summary[
            "maximum_roundtrip_error_pixels"
        ],
        "layouts": [
            {
                "layout_id": layout["layout_id"],
                "inverse_matrix": layout["inverse_matrix"],
                "independent_validation_residuals": layout[
                    "independent_validation_residuals"
                ],
                "heldout_localization": layout["heldout_localization"],
                "roundtrip_residuals": layout["roundtrip_residuals"],
                "tolerance_result": layout["tolerance_result"],
            }
            for layout in summary["layouts"]
        ],
    }
    supersession = {
        "schema_version": "person-e-v0.4-historical-homography-supersession-v0.1",
        "status": "SUPERSEDED_FOR_PERSON_C_LAYOUT_CONFIG_V0.4_DO_NOT_USE",
        "historical_files_unchanged": True,
        "historical_homographies": historical,
        "accepted_geometry_version": annotation_tool.EXPECTED_GEOMETRY_VERSION,
        "accepted_geometry_sha256": annotation_tool.EXPECTED_GEOMETRY_SHA256,
        "successor_candidate_count": 6,
        "successor_acceptance_status": (
            "ACCEPTED" if all_pass else "NOT_ACCEPTED_VALIDATION_FAILED"
        ),
    }
    registry = {
        "schema_version": "person-e-v0.4-refit-registry-records-v0.1",
        "records": [
            {
                "layout_id": layout["layout_id"],
                "homography_version_id": layout["homography"][
                    "homography_version_id"
                ],
                "accepted_geometry_version": annotation_tool.EXPECTED_GEOMETRY_VERSION,
                "accepted_geometry_sha256": annotation_tool.EXPECTED_GEOMETRY_SHA256,
                "lifecycle_status": (
                    "accepted_successor"
                    if layout["tolerance_result"] and all_pass
                    else "candidate_not_accepted"
                ),
                "tolerance_result": layout["tolerance_result"],
            }
            for layout in summary["layouts"]
        ],
    }
    return {
        "source_handoff_manifest.json": source_manifest,
        "consumed_input_inventory.json": consumed,
        "coordinate_convention.json": coordinate,
        "fit_summary.json": fit_summary,
        "reprojection_validation.json": reprojection,
        "inverse_validation.json": inverse,
        "historical_supersession.json": supersession,
        "registry_records.json": registry,
    }


def validation_markdown(summary: dict[str, Any]) -> str:
    rows = [
        "# Person E Attempt 02 homography refit validation",
        "",
        f"Overall status: **{summary['status']}**",
        "",
        "| Layout | Status | Wall-parallel error (blocks) | Independent error (pixels) |",
        "|---|---:|---:|---:|",
    ]
    for layout in summary["layouts"]:
        rows.append(
            "| {layout} | {status} | {wall!r} | {pixels!r} |".format(
                layout=layout["layout_id"],
                status=layout["status"],
                wall=layout["heldout_localization"][
                    "median_absolute_wall_parallel_error_blocks"
                ],
                pixels=layout["maximum_independent_validation_error_pixels"],
            )
        )
    rows.extend(
        [
            "",
            "Repository tolerance requires median wall-parallel error <= 0.2 blocks ",
            "and p95 wall-parallel error < 0.5 blocks. C6A is authorized only if all layouts pass.",
            "",
            f"C6A authorized: **{summary['all_tolerances_pass']}**",
            "",
        ]
    )
    return "\n".join(rows)


def package_manifest_document(
    summary: dict[str, Any],
    bundle_hash: str,
    inventory_record: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "status": summary["status"],
        "immutable": True,
        "package_directory": str(PACKAGE_DIR),
        "package_bundle_sha256": bundle_hash,
        "sha256_inventory": inventory_record,
        "annotation_sha256": ANNOTATION_SHA256,
        "source_code_commit": summary["source_code_commit"],
        "accepted_geometry_version": annotation_tool.EXPECTED_GEOMETRY_VERSION,
        "accepted_geometry_sha256": annotation_tool.EXPECTED_GEOMETRY_SHA256,
        "successor_homography_count": 6,
        "passing_layout_count": summary["passing_layout_count"],
        "failed_layout_ids": summary["failed_layout_ids"],
        "all_tolerances_pass": summary["all_tolerances_pass"],
        "c6a_execution_authorized": summary["all_tolerances_pass"],
    }


def handoff_document(
    summary: dict[str, Any],
    bundle_hash: str,
    package_manifest_record: dict[str, Any],
    layout_file_records: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "status": (
            "READY_FOR_C6A"
            if summary["all_tolerances_pass"]
            else "REFIT_VALIDATION_FAILED_C6A_NOT_AUTHORIZED"
        ),
        "immutable": True,
        "person_e_refit_package": package_manifest_record,
        "package_bundle_sha256": bundle_hash,
        "source_code_commit": summary["source_code_commit"],
        "annotation": _file_record(ANNOTATION_PATH),
        "person_c_calibration_handoff": _file_record(C_HANDOFF_PATH),
        "accepted_geometry_version": annotation_tool.EXPECTED_GEOMETRY_VERSION,
        "accepted_geometry_sha256": annotation_tool.EXPECTED_GEOMETRY_SHA256,
        "homography_algorithm": HOMOGRAPHY_ALGORITHM_VERSION,
        "successor_homography_count": 6,
        "layout_results": [
            {
                "layout_id": layout["layout_id"],
                "tolerance_result": layout["tolerance_result"],
                "homography_file": layout_file_records[layout["layout_id"]],
            }
            for layout in summary["layouts"]
        ],
        "all_tolerances_pass": summary["all_tolerances_pass"],
        "c6a_execution_authorized": summary["all_tolerances_pass"],
        "c6a_execution_command": None,
        "c6a_executed": False,
        "blocking_layout_ids": summary["failed_layout_ids"],
    }


def emit_package(summary: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    documents = build_package_documents(summary, inputs)
    output_paths = [PACKAGE_DIR / name for name in documents]
    output_paths.extend(
        PACKAGE_DIR / f"{layout_id}_homography.json"
        for layout_id in annotation_tool.EXPECTED_LAYOUT_IDS
    )
    output_paths.extend(
        (
            PACKAGE_DIR / "validation_report.md",
            PACKAGE_DIR / "sha256_inventory.json",
            PACKAGE_DIR / "package_manifest.json",
            PACKAGE_DIR / "person_e_to_person_c_refit_handoff.json",
        )
    )
    existing = [path for path in output_paths if path.exists()]
    if existing:
        raise FileExistsError(
            "Create-only package outputs already exist: "
            + ", ".join(str(path) for path in existing)
        )
    for name, document in documents.items():
        write_json_exclusive(PACKAGE_DIR / name, document)
    for layout in summary["layouts"]:
        write_json_exclusive(
            PACKAGE_DIR / f"{layout['layout_id']}_homography.json", layout
        )
    report_path = PACKAGE_DIR / "validation_report.md"
    write_text_exclusive(report_path, validation_markdown(summary))
    payload_paths = [ANNOTATION_PATH, *[PACKAGE_DIR / name for name in documents]]
    payload_paths.extend(
        PACKAGE_DIR / f"{layout_id}_homography.json"
        for layout_id in annotation_tool.EXPECTED_LAYOUT_IDS
    )
    payload_paths.append(report_path)
    inventory_records = [
        _file_record(path, relative_to_package=True) for path in payload_paths
    ]
    bundle_hash = hash_json_value(inventory_records)
    inventory = {
        "schema_version": "person-e-v0.4-refit-sha256-inventory-v0.1",
        "hash_algorithm": "sha256",
        "hash_source": "literal_file_bytes",
        "scope_excludes": [
            "sha256_inventory.json",
            "package_manifest.json",
            "person_e_to_person_c_refit_handoff.json",
        ],
        "package_bundle_sha256": bundle_hash,
        "files": inventory_records,
    }
    inventory_path = PACKAGE_DIR / "sha256_inventory.json"
    write_json_exclusive(inventory_path, inventory)
    package_manifest = package_manifest_document(
        summary, bundle_hash, _file_record(inventory_path)
    )
    package_manifest_path = PACKAGE_DIR / "package_manifest.json"
    write_json_exclusive(package_manifest_path, package_manifest)
    layout_file_records = {
        layout["layout_id"]: _file_record(
            PACKAGE_DIR / f"{layout['layout_id']}_homography.json"
        )
        for layout in summary["layouts"]
    }
    handoff = handoff_document(
        summary,
        bundle_hash,
        _file_record(package_manifest_path),
        layout_file_records,
    )
    handoff_path = PACKAGE_DIR / "person_e_to_person_c_refit_handoff.json"
    write_json_exclusive(handoff_path, handoff)
    return {
        "package_manifest_path": package_manifest_path,
        "package_manifest_sha256": sha256_file(package_manifest_path),
        "package_bundle_sha256": bundle_hash,
        "handoff_path": handoff_path,
        "handoff_sha256": sha256_file(handoff_path),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Finalize the six-layout Person E Attempt 02 homography refit."
    )
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--check-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    code_sha = _full_git_sha(args.code_sha, "code_sha")
    if current_git_commit() != code_sha:
        raise RefitFinalizeError("--code-sha must equal the current Git commit.")
    inputs = load_validated_inputs()
    summary = fit_all(inputs, code_sha)
    print(f"ANNOTATION_FILE_VALID=True")
    print(f"ANNOTATION_SHA256={ANNOTATION_SHA256}")
    print(f"SUCCESSOR_HOMOGRAPHY_COUNT={summary['successor_homography_count']}")
    print(f"ALL_TOLERANCES_PASS={summary['all_tolerances_pass']}")
    print(f"FAILED_LAYOUT_IDS={summary['failed_layout_ids']}")
    if args.check_only:
        return
    emitted = emit_package(summary, inputs)
    for key, value in emitted.items():
        print(f"{key.upper()}={value}")


if __name__ == "__main__":
    try:
        main()
    except (RefitFinalizeError, FileExistsError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2) from error
