"""Interactively annotate the six Person C Attempt 02 calibration frames.

The tool verifies every source byte before opening a window and writes one
create-only Person E annotation document after all fit and independent points
have been selected.  It deliberately performs no homography fit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HANDOFF = Path(
    r"C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server"
    r"\e_refit_calibration_v0_4_attempt_02_v0_1"
    r"\e_refit_calibration_v0_4_attempt_02_person_c_to_e_calibration_handoff.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "data"
    / "handoff_e"
    / "person_e_v0_4_homography_refit_v0_1"
    / "person_e_attempt_02_image_points_v0_1.json"
)
EXPECTED_HANDOFF_SHA256 = (
    "c27bcb9e56647bd01c650fd3360e7a8d4fbd0a44a456cf45073d1a926544ef39"
)
EXPECTED_GEOMETRY_VERSION = "person-c-layout-config-v0.4"
EXPECTED_GEOMETRY_SHA256 = (
    "34495d650d6a8c62b00a916796c90389b48f80d8f20a23eac93207758e993f5d"
)
EXPECTED_LAYOUT_IDS = tuple(f"layout_{index:02d}" for index in range(1, 7))
EXPECTED_FRAMEBUFFER = (1920, 1046)
ANNOTATION_METHOD = "person-e-tkinter-manual-point-selector-v0.2"
OUTPUT_SCHEMA_VERSION = "person-e-v0.4-image-point-annotations-attempt-02-v0.2"


def _point(
    source_kind: str,
    source_id: str,
    marker_color: str,
    location_description: str,
) -> dict[str, str]:
    return {
        "source_kind": source_kind,
        "source_id": source_id,
        "marker_color": marker_color,
        "location_description": location_description,
        "visibility_status": "visible_unambiguous",
    }


VISIBLE_POINT_PLAN = {
    "layout_01": {
        "fit": [
            _point(
                "marker",
                "near_west",
                "blue",
                "centre of the large blue ground-marker top face at screen right, immediately below the sheep",
            ),
            _point(
                "marker",
                "near_east",
                "yellow",
                "centre of the large yellow ground-marker top face at screen left",
            ),
            _point(
                "marker",
                "far_east",
                "white",
                "centre of the small white ground-marker top face above the yellow marker at screen left",
            ),
            _point(
                "validation_feature",
                "wall_near_face_ground_negative_end",
                "stone_gray",
                "right bottom corner of the gray wall where its right edge meets the near-face ground edge",
            ),
        ],
        "validation": [
            _point(
                "validation_feature",
                "wall_near_face_ground_positive_end",
                "stone_gray",
                "left bottom corner of the gray wall where its left edge meets the near-face ground edge",
            )
        ],
        "excluded_lime_reason": "far_west lime marker top-face centre is fully occluded by the wall",
    },
    "layout_02": {
        "fit": [
            _point(
                "marker",
                "near_west",
                "blue",
                "centre of the large blue ground-marker top face at screen left, immediately below the sheep",
            ),
            _point(
                "marker",
                "near_east",
                "yellow",
                "centre of the large yellow ground-marker top face at screen right",
            ),
            _point(
                "marker",
                "far_east",
                "white",
                "centre of the small white ground-marker top face above the yellow marker at screen right",
            ),
            _point(
                "validation_feature",
                "wall_near_face_ground_negative_end",
                "stone_gray",
                "left bottom corner of the gray wall where its left edge meets the near-face ground edge",
            ),
        ],
        "validation": [
            _point(
                "validation_feature",
                "wall_near_face_ground_positive_end",
                "stone_gray",
                "right bottom corner of the gray wall where its right edge meets the near-face ground edge",
            )
        ],
        "excluded_lime_reason": "far_west lime marker top-face centre is occluded by the target; only a partial fragment is visible",
    },
    "layout_03": {
        "fit": [
            _point(
                "marker",
                "near_west",
                "blue",
                "centre of the large blue ground-marker top face at screen right, immediately below the sheep",
            ),
            _point(
                "marker",
                "near_east",
                "yellow",
                "centre of the large yellow ground-marker top face at screen left",
            ),
            _point(
                "marker",
                "far_east",
                "white",
                "centre of the small white ground-marker top face above the yellow marker at screen left",
            ),
            _point(
                "validation_feature",
                "wall_near_face_ground_negative_end",
                "stone_gray",
                "right bottom corner of the gray wall where its right edge meets the near-face ground edge",
            ),
        ],
        "validation": [
            _point(
                "validation_feature",
                "wall_near_face_ground_positive_end",
                "stone_gray",
                "left bottom corner of the gray wall where its left edge meets the near-face ground edge",
            )
        ],
        "excluded_lime_reason": "far_west lime marker top-face centre is occluded by the target and wall; only a partial fragment is visible",
    },
    "layout_04": {
        "fit": [
            _point(
                "marker",
                "near_west",
                "blue",
                "centre of the blue ground-marker top face at screen right, immediately below the sheep",
            ),
            _point(
                "marker",
                "near_east",
                "yellow",
                "centre of the yellow ground-marker top face at screen left",
            ),
            _point(
                "marker",
                "far_east",
                "white",
                "centre of the small white ground-marker top face above the yellow marker at screen left",
            ),
            _point(
                "validation_feature",
                "wall_near_face_ground_negative_end",
                "stone_gray",
                "right bottom corner of the gray wall where its right edge meets the near-face ground edge",
            ),
        ],
        "validation": [
            _point(
                "validation_feature",
                "wall_near_face_ground_positive_end",
                "stone_gray",
                "left bottom corner of the gray wall where its left edge meets the near-face ground edge",
            )
        ],
        "excluded_lime_reason": "far_west lime marker top-face centre is occluded by the target; only a narrow fragment is visible",
    },
    "layout_05": {
        "fit": [
            _point(
                "marker",
                "near_west",
                "blue",
                "centre of the large blue ground-marker top face at screen right, immediately below the sheep",
            ),
            _point(
                "marker",
                "near_east",
                "yellow",
                "centre of the large yellow ground-marker top face at screen left",
            ),
            _point(
                "marker",
                "far_east",
                "white",
                "centre of the larger lower white ground-marker top face immediately above the yellow marker at screen left",
            ),
            _point(
                "validation_feature",
                "wall_near_face_ground_negative_end",
                "stone_gray",
                "right bottom corner of the gray wall where its right edge meets the near-face ground edge",
            ),
        ],
        "validation": [
            _point(
                "validation_feature",
                "wall_near_face_ground_positive_end",
                "stone_gray",
                "left bottom corner of the gray wall where its left edge meets the near-face ground edge",
            )
        ],
        "excluded_lime_reason": "far_west lime marker top-face centre is occluded by the target; only narrow lime strips are visible",
    },
    "layout_06": {
        "fit": [
            _point(
                "marker",
                "near_west",
                "blue",
                "centre of the blue ground-marker top face at screen left, immediately below the sheep",
            ),
            _point(
                "marker",
                "near_east",
                "yellow",
                "centre of the yellow ground-marker top face at screen right",
            ),
            _point(
                "marker",
                "far_east",
                "white",
                "centre of the small white ground-marker top face above the yellow marker at screen right",
            ),
            _point(
                "validation_feature",
                "wall_near_face_ground_negative_end",
                "stone_gray",
                "left bottom corner of the gray wall where its left edge meets the near-face ground edge",
            ),
        ],
        "validation": [
            _point(
                "validation_feature",
                "wall_near_face_ground_positive_end",
                "stone_gray",
                "right bottom corner of the gray wall where its right edge meets the near-face ground edge",
            )
        ],
        "excluded_lime_reason": "far_west lime marker top-face centre is not unambiguous because multiple comparable lime fragments are visible",
    },
}


class AnnotationInputError(ValueError):
    """Raised when an immutable Person C input fails closed verification."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AnnotationInputError(f"{path} must contain a JSON object.")
    return value


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        header = stream.read(24)
    if (
        len(header) != 24
        or header[:8] != b"\x89PNG\r\n\x1a\n"
        or header[12:16] != b"IHDR"
    ):
        raise AnnotationInputError(f"{path} is not a PNG with an IHDR header.")
    return struct.unpack(">II", header[16:24])


def verify_file_record(
    record: Any,
    label: str,
    *,
    expected_dimensions: tuple[int, int] | None = None,
) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise AnnotationInputError(f"{label} identity must be an object.")
    try:
        path = Path(record["path"])
        expected_size = record["size_bytes"]
        expected_hash = record["sha256"]
    except KeyError as error:
        raise AnnotationInputError(f"{label} identity is incomplete.") from error
    if not isinstance(expected_size, int) or isinstance(expected_size, bool):
        raise AnnotationInputError(f"{label} size is invalid.")
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise AnnotationInputError(f"{label} SHA-256 is invalid.")
    if not path.is_file():
        raise AnnotationInputError(f"{label} does not exist: {path}")
    actual_size = path.stat().st_size
    actual_hash = sha256_file(path)
    if actual_size != expected_size:
        raise AnnotationInputError(
            f"{label} size mismatch: expected {expected_size}, got {actual_size}."
        )
    if actual_hash != expected_hash:
        raise AnnotationInputError(
            f"{label} SHA-256 mismatch: expected {expected_hash}, got {actual_hash}."
        )
    verified = {
        "path": str(path),
        "size_bytes": actual_size,
        "sha256": actual_hash,
    }
    if expected_dimensions is not None:
        actual_dimensions = png_dimensions(path)
        if actual_dimensions != expected_dimensions:
            raise AnnotationInputError(
                f"{label} dimensions mismatch: expected {expected_dimensions}, "
                f"got {actual_dimensions}."
            )
        verified["width_pixels"], verified["height_pixels"] = actual_dimensions
    return verified


def _layouts_by_id(document: dict[str, Any], label: str) -> dict[str, dict[str, Any]]:
    layouts = document.get("layouts")
    if not isinstance(layouts, list):
        raise AnnotationInputError(f"{label}.layouts must be a list.")
    by_id: dict[str, dict[str, Any]] = {}
    for row in layouts:
        if not isinstance(row, dict) or not isinstance(row.get("layout_id"), str):
            raise AnnotationInputError(f"{label} contains a malformed layout.")
        layout_id = row["layout_id"]
        if layout_id in by_id:
            raise AnnotationInputError(f"{label} duplicates {layout_id}.")
        by_id[layout_id] = row
    if tuple(sorted(by_id)) != EXPECTED_LAYOUT_IDS:
        raise AnnotationInputError(
            f"{label} layout identities changed: {sorted(by_id)}."
        )
    return by_id


def _world_xz_from_xyz(value: Any, label: str) -> list[float]:
    if (
        not isinstance(value, list)
        or len(value) != 3
        or any(
            not isinstance(coordinate, (int, float))
            or isinstance(coordinate, bool)
            for coordinate in value
        )
    ):
        raise AnnotationInputError(f"{label} must be a three-coordinate list.")
    return [float(value[0]), float(value[2])]


def verify_receipt_geometry(
    receipt: dict[str, Any],
    annotation_layout: dict[str, Any],
    validation_layout: dict[str, Any],
    layout_id: str,
) -> None:
    if receipt.get("layout_id") != layout_id:
        raise AnnotationInputError(f"{layout_id} receipt identity changed.")
    receipt_markers = receipt.get("markers")
    if not isinstance(receipt_markers, list) or len(receipt_markers) != 4:
        raise AnnotationInputError(f"{layout_id} receipt marker set is malformed.")
    marker_by_role = {
        marker.get("role"): marker
        for marker in receipt_markers
        if isinstance(marker, dict) and isinstance(marker.get("role"), str)
    }
    if len(marker_by_role) != 4:
        raise AnnotationInputError(f"{layout_id} receipt marker identities changed.")
    for point in annotation_layout["fit_correspondences"]:
        marker = marker_by_role.get(point["marker_id"])
        if (
            marker is None
            or marker.get("matches") is not True
            or marker.get("color") != point["color"]
            or _world_xz_from_xyz(
                marker.get("top_face_centre_world_xyz"),
                f"{layout_id} receipt marker {point['marker_id']}",
            )
            != [float(value) for value in point["world_xz_blocks"]]
        ):
            raise AnnotationInputError(
                f"{layout_id} marker {point['marker_id']} disagrees with its receipt."
            )

    wall = receipt.get("wall")
    if not isinstance(wall, dict) or wall.get("mismatches") != []:
        raise AnnotationInputError(f"{layout_id} wall receipt is not clean.")
    axis = wall.get("axis")
    axis_min = wall.get("declared_axis_min_block_inclusive")
    axis_max = wall.get("declared_axis_max_block_inclusive")
    ortho = wall.get("ortho_block")
    if axis not in {"X", "Z"} or any(
        not isinstance(value, int) or isinstance(value, bool)
        for value in (axis_min, axis_max, ortho)
    ):
        raise AnnotationInputError(f"{layout_id} wall receipt geometry is malformed.")
    negative_axis = float(axis_min)
    positive_axis = float(axis_max + 1)
    midpoint_axis = (negative_axis + positive_axis) / 2.0
    if axis == "X":
        wall_world = {
            "wall_near_face_ground_negative_end": [negative_axis, float(ortho)],
            "wall_near_face_ground_midpoint": [midpoint_axis, float(ortho)],
            "wall_near_face_ground_positive_end": [positive_axis, float(ortho)],
        }
    else:
        wall_world = {
            "wall_near_face_ground_negative_end": [float(ortho), negative_axis],
            "wall_near_face_ground_midpoint": [float(ortho), midpoint_axis],
            "wall_near_face_ground_positive_end": [float(ortho), positive_axis],
        }
    target = receipt.get("target")
    if not isinstance(target, dict) or target.get("valid") is not True:
        raise AnnotationInputError(f"{layout_id} target receipt is not valid.")
    target_world = _world_xz_from_xyz(
        target.get("actual_xyz"), f"{layout_id} receipt target"
    )
    expected_validation_world = {
        "target_ground_contact": target_world,
        **wall_world,
    }
    for point in validation_layout["validation_points"]:
        point_id = point["point_id"]
        if expected_validation_world.get(point_id) != [
            float(value) for value in point["world_xz_blocks"]
        ]:
            raise AnnotationInputError(
                f"{layout_id} validation point {point_id} disagrees with its receipt."
            )


def verify_sources(handoff_path: Path) -> dict[str, Any]:
    if not handoff_path.is_file():
        raise AnnotationInputError(f"Handoff does not exist: {handoff_path}")
    handoff_hash = sha256_file(handoff_path)
    if handoff_hash != EXPECTED_HANDOFF_SHA256:
        raise AnnotationInputError(
            "Handoff SHA-256 mismatch: "
            f"expected {EXPECTED_HANDOFF_SHA256}, got {handoff_hash}."
        )
    handoff = load_json(handoff_path)
    if handoff.get("accepted_geometry_version") != EXPECTED_GEOMETRY_VERSION:
        raise AnnotationInputError("Accepted geometry version changed.")
    if handoff.get("accepted_geometry_sha256") != EXPECTED_GEOMETRY_SHA256:
        raise AnnotationInputError("Accepted geometry SHA-256 changed.")
    if handoff.get("framebuffer") != {
        "width_pixels": EXPECTED_FRAMEBUFFER[0],
        "height_pixels": EXPECTED_FRAMEBUFFER[1],
    }:
        raise AnnotationInputError("Framebuffer identity changed.")
    if handoff.get("fov_degrees") != 70.0:
        raise AnnotationInputError("FOV changed.")
    if handoff.get("preflight_screenshot_counted_as_layout") is not False:
        raise AnnotationInputError("Preflight screenshot was counted as a layout.")
    if handoff.get("person_c_invented_image_coordinates") is not False:
        raise AnnotationInputError("Person C image-coordinate ownership changed.")
    if handoff.get("person_c_fit_homographies") is not False:
        raise AnnotationInputError("Person C unexpectedly fit homographies.")

    annotation_record = verify_file_record(
        handoff.get("e_image_point_annotation_template"), "annotation template"
    )
    validation_record = verify_file_record(
        handoff.get("e_independent_validation_pair_template"),
        "independent validation template",
    )
    coordinate_record = verify_file_record(
        handoff.get("coordinate_convention"), "coordinate convention"
    )
    annotation = load_json(Path(annotation_record["path"]))
    validation = load_json(Path(validation_record["path"]))
    annotation_layouts = _layouts_by_id(annotation, "annotation template")
    validation_layouts = _layouts_by_id(validation, "validation template")
    handoff_layouts = _layouts_by_id(handoff, "handoff")

    screenshots: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    receipt_documents: dict[str, dict[str, Any]] = {}
    for layout_id in EXPECTED_LAYOUT_IDS:
        handoff_layout = handoff_layouts[layout_id]
        screenshot = verify_file_record(
            handoff_layout.get("canonical_screenshot"),
            f"{layout_id} screenshot",
            expected_dimensions=EXPECTED_FRAMEBUFFER,
        )
        receipt = verify_file_record(
            handoff_layout.get("geometry_receipt"), f"{layout_id} geometry receipt"
        )
        receipt_document = load_json(Path(receipt["path"]))
        verify_receipt_geometry(
            receipt_document,
            annotation_layouts[layout_id],
            validation_layouts[layout_id],
            layout_id,
        )
        for template_name, template_layout in (
            ("annotation", annotation_layouts[layout_id]),
            ("validation", validation_layouts[layout_id]),
        ):
            template_screenshot = template_layout.get("screenshot")
            if not isinstance(template_screenshot, dict):
                raise AnnotationInputError(
                    f"{layout_id} {template_name} screenshot identity is missing."
                )
            for field in ("path", "size_bytes", "sha256"):
                if template_screenshot.get(field) != screenshot[field]:
                    raise AnnotationInputError(
                        f"{layout_id} {template_name} screenshot {field} disagrees."
                    )
            if (
                template_screenshot.get("width_pixels"),
                template_screenshot.get("height_pixels"),
            ) != EXPECTED_FRAMEBUFFER:
                raise AnnotationInputError(
                    f"{layout_id} {template_name} dimensions disagree."
                )

        fit_points = annotation_layouts[layout_id].get("fit_correspondences")
        if not isinstance(fit_points, list) or len(fit_points) != 4:
            raise AnnotationInputError(f"{layout_id} requires exactly four fit points.")
        marker_ids = [point.get("marker_id") for point in fit_points if isinstance(point, dict)]
        if len(marker_ids) != 4 or len(set(marker_ids)) != 4:
            raise AnnotationInputError(f"{layout_id} fit marker identities are invalid.")
        if any(point.get("image_xy_pixels") is not None for point in fit_points):
            raise AnnotationInputError(f"{layout_id} fit template contains coordinates.")

        validation_points = validation_layouts[layout_id].get("validation_points")
        if not isinstance(validation_points, list) or len(validation_points) != 4:
            raise AnnotationInputError(
                f"{layout_id} requires exactly four independent validation points."
            )
        point_ids = [
            point.get("point_id") for point in validation_points if isinstance(point, dict)
        ]
        if len(point_ids) != 4 or len(set(point_ids)) != 4:
            raise AnnotationInputError(
                f"{layout_id} independent validation identities are invalid."
            )
        if any(point.get("image_xy_pixels") is not None for point in validation_points):
            raise AnnotationInputError(
                f"{layout_id} validation template contains coordinates."
            )
        screenshots.append({"layout_id": layout_id, **screenshot})
        receipts.append({"layout_id": layout_id, **receipt})
        receipt_documents[layout_id] = receipt_document

    return {
        "handoff": handoff,
        "handoff_record": {
            "path": str(handoff_path),
            "size_bytes": handoff_path.stat().st_size,
            "sha256": handoff_hash,
        },
        "annotation_template": annotation,
        "annotation_template_record": annotation_record,
        "validation_template": validation,
        "validation_template_record": validation_record,
        "coordinate_convention_record": coordinate_record,
        "screenshots": screenshots,
        "receipts": receipts,
        "receipt_documents": receipt_documents,
    }


def _fit_world_points_are_valid(points: list[list[float]]) -> bool:
    if len(points) != 4 or len({tuple(point) for point in points}) != 4:
        return False
    for first in range(4):
        for second in range(first + 1, 4):
            for third in range(second + 1, 4):
                ax, az = points[first]
                bx, bz = points[second]
                cx, cz = points[third]
                twice_area = (bx - ax) * (cz - az) - (bz - az) * (cx - ax)
                if abs(twice_area) <= 1e-12:
                    return False
    return True


def build_tasks(
    verified: dict[str, Any],
    point_plan: dict[str, dict[str, Any]] = VISIBLE_POINT_PLAN,
) -> list[dict[str, Any]]:
    annotation_layouts = _layouts_by_id(
        verified["annotation_template"], "annotation template"
    )
    validation_layouts = _layouts_by_id(
        verified["validation_template"], "validation template"
    )
    screenshots = {row["layout_id"]: row for row in verified["screenshots"]}
    if tuple(sorted(point_plan)) != EXPECTED_LAYOUT_IDS:
        raise AnnotationInputError("Visibility plan layout identities changed.")
    tasks: list[dict[str, Any]] = []
    for layout_id in EXPECTED_LAYOUT_IDS:
        marker_by_id = {
            point["marker_id"]: point
            for point in annotation_layouts[layout_id]["fit_correspondences"]
        }
        validation_by_id = {
            point["point_id"]: point
            for point in validation_layouts[layout_id]["validation_points"]
        }
        layout_plan = point_plan[layout_id]
        if (
            not isinstance(layout_plan.get("excluded_lime_reason"), str)
            or not layout_plan["excluded_lime_reason"].strip()
        ):
            raise AnnotationInputError(
                f"{layout_id} must document the excluded lime marker."
            )
        fit_plan = layout_plan.get("fit")
        validation_plan = layout_plan.get("validation")
        if not isinstance(fit_plan, list) or len(fit_plan) != 4:
            raise AnnotationInputError(
                f"{layout_id} visibility preflight requires four fit points."
            )
        if not isinstance(validation_plan, list) or not validation_plan:
            raise AnnotationInputError(
                f"{layout_id} visibility preflight requires validation points."
            )
        layout_tasks: list[dict[str, Any]] = []
        for kind, planned_points in (
            ("fit_correspondence", fit_plan),
            ("independent_validation", validation_plan),
        ):
            for plan_point in planned_points:
                if not isinstance(plan_point, dict):
                    raise AnnotationInputError(
                        f"{layout_id} visibility-plan point is malformed."
                    )
                if plan_point.get("visibility_status") != "visible_unambiguous":
                    raise AnnotationInputError(
                        f"{layout_id} requested point {plan_point.get('source_id')} "
                        "is not visible and unambiguous."
                    )
                if any(
                    not isinstance(plan_point.get(field), str)
                    or not plan_point[field].strip()
                    for field in (
                        "source_kind",
                        "source_id",
                        "marker_color",
                        "location_description",
                    )
                ):
                    raise AnnotationInputError(
                        f"{layout_id} visibility-plan description is incomplete."
                    )
                source_kind = plan_point["source_kind"]
                source_id = plan_point["source_id"]
                if source_kind == "marker":
                    source_point = marker_by_id.get(source_id)
                    if (
                        source_point is None
                        or source_point["color"] != plan_point["marker_color"]
                    ):
                        raise AnnotationInputError(
                            f"{layout_id} marker {source_id} is not source-authorized."
                        )
                    feature = f"{source_point['color']} marker top-face centre"
                elif source_kind == "validation_feature":
                    source_point = validation_by_id.get(source_id)
                    if source_point is None:
                        raise AnnotationInputError(
                            f"{layout_id} feature {source_id} is not source-authorized."
                        )
                    feature = source_point["feature"]
                else:
                    raise AnnotationInputError(
                        f"{layout_id} point {source_id} has an unknown source kind."
                    )
                layout_tasks.append(
                    {
                        "layout_id": layout_id,
                        "kind": kind,
                        "point_id": source_id,
                        "marker_color": plan_point["marker_color"],
                        "location_description": plan_point[
                            "location_description"
                        ],
                        "visibility_status": plan_point["visibility_status"],
                        "feature": feature,
                        "world_xz_blocks": source_point["world_xz_blocks"],
                        "source_kind": source_kind,
                        "source_point": dict(source_point),
                        "screenshot": screenshots[layout_id],
                    }
                )
        point_ids = [task["point_id"] for task in layout_tasks]
        if len(point_ids) != len(set(point_ids)):
            raise AnnotationInputError(
                f"{layout_id} fit and validation point identities overlap."
            )
        fit_tasks = [
            task for task in layout_tasks if task["kind"] == "fit_correspondence"
        ]
        if {task["point_id"] for task in fit_tasks if task["source_kind"] == "marker"} != {
            "near_west",
            "near_east",
            "far_east",
        }:
            raise AnnotationInputError(
                f"{layout_id} visible marker selection changed."
            )
        if not _fit_world_points_are_valid(
            [
                [float(value) for value in task["world_xz_blocks"]]
                for task in fit_tasks
            ]
        ):
            raise AnnotationInputError(
                f"{layout_id} fit world points are duplicate or collinear."
            )
        tasks.extend(layout_tasks)
    return tasks


def current_git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    commit = result.stdout.strip()
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        raise AnnotationInputError("Current Git revision is not a full lowercase SHA.")
    return commit


def build_output_document(
    verified: dict[str, Any],
    tasks: list[dict[str, Any]],
    selections: list[tuple[int, int]],
) -> dict[str, Any]:
    expected_task_count = sum(
        len(layout_plan["fit"]) + len(layout_plan["validation"])
        for layout_plan in VISIBLE_POINT_PLAN.values()
    )
    if len(tasks) != expected_task_count or len(selections) != len(tasks):
        raise AnnotationInputError(
            f"All {expected_task_count} visible fit and validation points are required."
        )
    layouts: dict[str, dict[str, Any]] = {}
    for task, image_xy in zip(tasks, selections):
        width = task["screenshot"]["width_pixels"]
        height = task["screenshot"]["height_pixels"]
        x, y = image_xy
        if not (0 <= x < width and 0 <= y < height):
            raise AnnotationInputError(f"Point {task['point_id']} is outside its frame.")
        layout = layouts.setdefault(
            task["layout_id"],
            {
                "layout_id": task["layout_id"],
                "screenshot": task["screenshot"],
                "fit_correspondences": [],
                "independent_validation_points": [],
            },
        )
        record = dict(task["source_point"])
        record["point_id"] = task["point_id"]
        record["source_kind"] = task["source_kind"]
        record["marker_color"] = task["marker_color"]
        record["location_description"] = task["location_description"]
        record["visibility_status"] = task["visibility_status"]
        record["image_xy_pixels"] = [x, y]
        record["selection_status"] = "operator_selected"
        destination = (
            "fit_correspondences"
            if task["kind"] == "fit_correspondence"
            else "independent_validation_points"
        )
        layout[destination].append(record)

    for layout_id, layout in layouts.items():
        if len(layout["fit_correspondences"]) != 4:
            raise AnnotationInputError(f"{layout_id} does not have four fit points.")
        if not layout["independent_validation_points"]:
            raise AnnotationInputError(
                f"{layout_id} has no independent validation points."
            )

    return {
        "schema_version": "1.0",
        "annotation_schema_version": OUTPUT_SCHEMA_VERSION,
        "status": "IMAGE_POINTS_COMPLETE_PENDING_HOMOGRAPHY_FIT",
        "immutable_after_creation": True,
        "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "person_e_source_commit": current_git_commit(),
        "source_handoff": verified["handoff_record"],
        "accepted_geometry_version": EXPECTED_GEOMETRY_VERSION,
        "accepted_geometry_sha256": EXPECTED_GEOMETRY_SHA256,
        "framebuffer": {
            "width_pixels": EXPECTED_FRAMEBUFFER[0],
            "height_pixels": EXPECTED_FRAMEBUFFER[1],
        },
        "image_coordinate_convention": "pixel_center_xy_zero_based",
        "annotation_method": {
            "algorithm_id": ANNOTATION_METHOD,
            "selection": "manual_left_click_on_original_resolution_pixels",
            "coordinate_transform": "none",
            "fit_point_definition": (
                "receipt_authorized_visible_ground_plane_feature"
            ),
            "validation_point_definitions_source": verified[
                "validation_template_record"
            ],
            "visibility_preflight": {
                "status": "passed",
                "basis": (
                    "manual_visibility_review_bound_to_exact_screenshot_sha256"
                ),
                "fully_occluded_or_ambiguous_points_requested": 0,
                "excluded_lime_markers": {
                    layout_id: VISIBLE_POINT_PLAN[layout_id][
                        "excluded_lime_reason"
                    ]
                    for layout_id in EXPECTED_LAYOUT_IDS
                },
            },
            "operator_final_confirmation": True,
        },
        "source_verification": {
            "handoff_sha256_valid": True,
            "six_screenshots_paths_dimensions_and_hashes_valid": True,
            "six_geometry_receipt_paths_and_hashes_valid": True,
            "accepted_geometry_identity_valid": True,
            "annotation_template": verified["annotation_template_record"],
            "validation_template": verified["validation_template_record"],
            "coordinate_convention": verified["coordinate_convention_record"],
            "geometry_receipts": verified["receipts"],
        },
        "layouts": [layouts[layout_id] for layout_id in EXPECTED_LAYOUT_IDS],
    }


def write_json_create_only(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, indent=2, sort_keys=True)
        stream.write("\n")


class AnnotationWindow:
    def __init__(
        self,
        verified: dict[str, Any],
        output_path: Path,
    ) -> None:
        import tkinter as tk
        from tkinter import messagebox

        self.tk = tk
        self.messagebox = messagebox
        self.verified = verified
        self.output_path = output_path
        self.tasks = build_tasks(verified)
        self.selections: list[tuple[int, int]] = []
        self.task_index = 0
        self.loaded_layout_id: str | None = None
        self.photo: Any = None

        self.root = tk.Tk()
        self.root.title("Person E Attempt 02 image-point annotation")
        try:
            self.root.state("zoomed")
        except tk.TclError:
            self.root.geometry("1500x900")

        self.prompt = tk.Label(
            self.root,
            anchor="w",
            justify="left",
            font=("TkDefaultFont", 11, "bold"),
            padx=8,
            pady=6,
        )
        self.prompt.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.help = tk.Label(
            self.root,
            text=(
                "Left click selects the prompted original-resolution pixel. "
                "Backspace/right click undoes. Scrollbars or mouse wheel pan. "
                "Escape cancels without writing."
            ),
            anchor="w",
            padx=8,
        )
        self.help.grid(row=1, column=0, columnspan=2, sticky="ew")

        self.canvas = tk.Canvas(self.root, background="#202020", cursor="crosshair")
        xbar = tk.Scrollbar(self.root, orient="horizontal", command=self.canvas.xview)
        ybar = tk.Scrollbar(self.root, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=xbar.set, yscrollcommand=ybar.set)
        self.canvas.grid(row=2, column=0, sticky="nsew")
        ybar.grid(row=2, column=1, sticky="ns")
        xbar.grid(row=3, column=0, sticky="ew")
        self.root.rowconfigure(2, weight=1)
        self.root.columnconfigure(0, weight=1)

        self.canvas.bind("<Button-1>", self._select)
        self.canvas.bind("<Button-3>", self._undo)
        self.root.bind("<BackSpace>", self._undo)
        self.root.bind("<Escape>", self._cancel)
        self.canvas.bind("<MouseWheel>", self._scroll_vertical)
        self.canvas.bind("<Shift-MouseWheel>", self._scroll_horizontal)
        self.root.protocol("WM_DELETE_WINDOW", self._cancel)
        self._show_current_task()

    def _scroll_vertical(self, event: Any) -> None:
        self.canvas.yview_scroll(-int(event.delta / 120), "units")

    def _scroll_horizontal(self, event: Any) -> None:
        self.canvas.xview_scroll(-int(event.delta / 120), "units")

    def _show_current_task(self) -> None:
        task = self.tasks[self.task_index]
        if self.loaded_layout_id != task["layout_id"]:
            self.photo = self.tk.PhotoImage(file=task["screenshot"]["path"])
            self.loaded_layout_id = task["layout_id"]
            self.canvas.configure(
                scrollregion=(0, 0, self.photo.width(), self.photo.height())
            )
            self.canvas.xview_moveto(0.0)
            self.canvas.yview_moveto(0.0)
        self.prompt.configure(
            text=(
                f"Point {self.task_index + 1}/{len(self.tasks)} | "
                f"layout={task['layout_id']} | {task['kind']} | "
                f"color={task['marker_color']} | "
                f"location={task['location_description']} | "
                f"world_xz={task['world_xz_blocks']}"
            )
        )
        self._redraw()

    def _redraw(self) -> None:
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        for index, ((x, y), task) in enumerate(
            zip(self.selections, self.tasks[: len(self.selections)]), start=1
        ):
            if task["layout_id"] != self.loaded_layout_id:
                continue
            colour = (
                "#00ffff"
                if task["kind"] == "fit_correspondence"
                else "#ff4040"
            )
            self.canvas.create_line(x - 10, y, x + 10, y, fill=colour, width=2)
            self.canvas.create_line(x, y - 10, x, y + 10, fill=colour, width=2)
            self.canvas.create_text(
                x + 12,
                y - 12,
                text=f"{index}:{task['point_id']}",
                fill=colour,
                anchor="sw",
                font=("TkDefaultFont", 9, "bold"),
            )

    def _select(self, event: Any) -> None:
        task = self.tasks[self.task_index]
        x = int(round(self.canvas.canvasx(event.x)))
        y = int(round(self.canvas.canvasy(event.y)))
        width = task["screenshot"]["width_pixels"]
        height = task["screenshot"]["height_pixels"]
        if not (0 <= x < width and 0 <= y < height):
            self.messagebox.showerror("Invalid point", "Click inside the screenshot.")
            return
        self.selections.append((x, y))
        self.task_index += 1
        if self.task_index == len(self.tasks):
            self._finish()
            return
        self._show_current_task()

    def _undo(self, _event: Any = None) -> None:
        if not self.selections:
            return
        self.selections.pop()
        self.task_index -= 1
        self.loaded_layout_id = None
        self._show_current_task()

    def _finish(self) -> None:
        confirmed = self.messagebox.askyesno(
            "Confirm annotation",
            f"All {len(self.tasks)} points are selected. "
            "Write the immutable create-only output?",
        )
        if not confirmed:
            self._undo()
            return
        try:
            document = build_output_document(
                self.verified, self.tasks, self.selections
            )
            write_json_create_only(self.output_path, document)
        except Exception as error:
            self.messagebox.showerror("Write failed", str(error))
            self._undo()
            return
        digest = sha256_file(self.output_path)
        self.messagebox.showinfo(
            "Annotation complete",
            f"Created:\n{self.output_path}\n\nSHA-256:\n{digest}",
        )
        self.root.destroy()

    def _cancel(self, _event: Any = None) -> None:
        if self.messagebox.askyesno(
            "Cancel annotation", "Cancel without writing an output file?"
        ):
            self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify and manually annotate all six Attempt 02 calibration frames."
        )
    )
    parser.add_argument("--handoff", type=Path, default=DEFAULT_HANDOFF)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="verify every immutable input without opening the annotation window",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = args.output.resolve()
    if output_path.exists():
        raise FileExistsError(
            f"Create-only output already exists; refusing to overwrite: {output_path}"
        )
    verified = verify_sources(args.handoff.resolve())
    tasks = build_tasks(verified)
    expected_tasks = 5 * len(EXPECTED_LAYOUT_IDS)
    if len(tasks) != expected_tasks:
        raise AnnotationInputError(
            f"Expected {expected_tasks} visible annotation tasks, got {len(tasks)}."
        )
    if args.verify_only:
        print("C_HANDOFF_VALID=True")
        print("SIX_SCREENSHOTS_VALID=True")
        print("SIX_GEOMETRY_RECEIPTS_VALID=True")
        print("VISIBILITY_PREFLIGHT_READY=True")
        for layout_id in EXPECTED_LAYOUT_IDS:
            layout_tasks = [task for task in tasks if task["layout_id"] == layout_id]
            fit_count = sum(
                task["kind"] == "fit_correspondence" for task in layout_tasks
            )
            validation_count = sum(
                task["kind"] == "independent_validation" for task in layout_tasks
            )
            print(f"{layout_id.upper()}_VISIBLE_FIT_POINT_COUNT={fit_count}")
            print(
                f"{layout_id.upper()}_VISIBLE_VALIDATION_POINT_COUNT="
                f"{validation_count}"
            )
        print(f"ANNOTATION_TASK_COUNT={len(tasks)}")
        return
    AnnotationWindow(verified, output_path).run()


if __name__ == "__main__":
    try:
        main()
    except (AnnotationInputError, FileExistsError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2) from error
