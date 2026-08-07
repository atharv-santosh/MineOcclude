"""Validate the targeted correction and emit the additive v0.2 refit package.

Layouts 04 and 06 are fitted from the corrected annotation.  Passing layout
artifacts 01, 02, 03, and 05 are reused byte-for-byte only after the complete
failed-closed v0.1 inventory is verified.  C6A is authorized only when all six
layout records pass the unchanged repository tolerance; this script never
executes C6A.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import finalize_person_e_homography_refit_attempt_02 as v1
import repair_person_e_layout_04_06_annotations as repair
from mineocclude.vision.config import validate_person_e_config
from mineocclude.vision.homography import (
    HOMOGRAPHY_ALGORITHM_VERSION,
    fit_marker_homography,
    summarize_localization,
)


PACKAGE_DIR = (
    ROOT / "data" / "handoff_e" / "person_e_v0_4_homography_refit_v0_2"
)
ANNOTATION_PATH = PACKAGE_DIR / "person_e_attempt_02_image_points_v0_2.json"
ANNOTATION_SHA256 = (
    "9f4df0ddc91499271d556d1ece049fa246a61c1e7f410bb978ab30bfee50cda4"
)
ANNOTATION_SCHEMA_VERSION = repair.OUTPUT_ANNOTATION_SCHEMA
ANNOTATION_SOURCE_COMMIT = "98f94c2178d6b4ff9398f925d0bc75a6bc1bd656"
V1_PACKAGE_DIR = repair.BASE_ANNOTATION.parent
V1_PACKAGE_MANIFEST = repair.BASE_PACKAGE
V1_PACKAGE_MANIFEST_SHA256 = repair.BASE_PACKAGE_SHA256
V1_HANDOFF = repair.BASE_HANDOFF
V1_HANDOFF_SHA256 = repair.BASE_HANDOFF_SHA256
V1_INVENTORY = V1_PACKAGE_DIR / "sha256_inventory.json"
REUSED_LAYOUT_IDS = repair.REUSED_LAYOUT_IDS
REFITTED_LAYOUT_IDS = repair.TARGET_LAYOUT_IDS
EXPECTED_LAYOUT_IDS = repair.EXPECTED_LAYOUT_IDS
CONFIG_PATH = v1.CONFIG_PATH
PACKAGE_SCHEMA_VERSION = "person-e-v0.4-homography-refit-package-v0.2"
HANDOFF_SCHEMA_VERSION = "person-e-to-person-c-v0.4-refit-handoff-v0.2"
RESOLUTION_ID = v1.RESOLUTION_ID


class RefitV02Error(ValueError):
    """Raised when corrected annotation or package validation fails closed."""


def sha256_file(path: Path) -> str:
    return v1.sha256_file(path)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RefitV02Error(f"{path} must contain a JSON object.")
    return value


def _file_record(path: Path, *, relative_to_package: bool = False) -> dict[str, Any]:
    return {
        "path": (
            path.relative_to(PACKAGE_DIR).as_posix()
            if relative_to_package
            else str(path.resolve())
        ),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _verify_record(path: Path, record: dict[str, Any], label: str) -> None:
    if (
        not path.is_file()
        or record.get("size_bytes") != path.stat().st_size
        or record.get("sha256") != sha256_file(path)
    ):
        raise RefitV02Error(f"{label} artifact hash or size changed.")


def _layout_map(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    layouts = document.get("layouts")
    if not isinstance(layouts, list):
        raise RefitV02Error("Annotation layouts are malformed.")
    mapped: dict[str, dict[str, Any]] = {}
    for layout in layouts:
        if not isinstance(layout, dict) or not isinstance(layout.get("layout_id"), str):
            raise RefitV02Error("Annotation contains a malformed layout.")
        if layout["layout_id"] in mapped:
            raise RefitV02Error("Annotation duplicates a layout identity.")
        mapped[layout["layout_id"]] = layout
    if tuple(sorted(mapped)) != EXPECTED_LAYOUT_IDS:
        raise RefitV02Error("Annotation layout identities changed.")
    return mapped


def verify_v1_package() -> dict[str, Any]:
    repair.verify_preserved_artifacts()
    if sha256_file(V1_PACKAGE_MANIFEST) != V1_PACKAGE_MANIFEST_SHA256:
        raise RefitV02Error("v0.1 failed-closed package manifest changed.")
    if sha256_file(V1_HANDOFF) != V1_HANDOFF_SHA256:
        raise RefitV02Error("v0.1 failed-closed handoff changed.")
    manifest = load_json(V1_PACKAGE_MANIFEST)
    inventory_record = manifest.get("sha256_inventory")
    if not isinstance(inventory_record, dict):
        raise RefitV02Error("v0.1 package inventory binding is malformed.")
    _verify_record(V1_INVENTORY, inventory_record, "v0.1 SHA-256 inventory")
    inventory = load_json(V1_INVENTORY)
    records = inventory.get("files")
    if not isinstance(records, list) or not records:
        raise RefitV02Error("v0.1 SHA-256 inventory is empty or malformed.")
    if (
        inventory.get("package_bundle_sha256")
        != manifest.get("package_bundle_sha256")
        or v1.hash_json_value(records) != inventory.get("package_bundle_sha256")
    ):
        raise RefitV02Error("v0.1 package bundle hash changed.")
    records_by_path: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            raise RefitV02Error("v0.1 inventory contains a malformed record.")
        relative = Path(record["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise RefitV02Error("v0.1 inventory contains an unsafe path.")
        path = V1_PACKAGE_DIR / relative
        _verify_record(path, record, f"v0.1 {record['path']}")
        records_by_path[record["path"]] = record

    reused: dict[str, dict[str, Any]] = {}
    reused_records: dict[str, dict[str, Any]] = {}
    for layout_id in REUSED_LAYOUT_IDS:
        name = f"{layout_id}_homography.json"
        record = records_by_path.get(name)
        if record is None:
            raise RefitV02Error(f"v0.1 inventory omits {layout_id}.")
        layout = load_json(V1_PACKAGE_DIR / name)
        if (
            layout.get("layout_id") != layout_id
            or layout.get("status") != "PASS"
            or layout.get("tolerance_result") is not True
            or layout.get("repository_tolerance_passed") is not True
            or layout.get("matrix_gate_passed") is not True
            or layout.get("rank") != 3
            or layout.get("accepted_geometry_version")
            != repair.EXPECTED_GEOMETRY_VERSION
            or layout.get("accepted_geometry_sha256")
            != repair.EXPECTED_GEOMETRY_SHA256
            or layout.get("homography_algorithm")
            != "four_point_projective_gauss_jordan_v0.1"
        ):
            raise RefitV02Error(f"v0.1 {layout_id} is not a reusable passing fit.")
        reused[layout_id] = layout
        reused_records[layout_id] = copy.deepcopy(record)
    return {
        "manifest": manifest,
        "inventory": inventory,
        "inventory_records": records_by_path,
        "reused_layouts": reused,
        "reused_layout_records": reused_records,
    }


def _point_pair(value: Any, label: str) -> list[float]:
    try:
        return v1._point_pair(value, label)
    except v1.RefitFinalizeError as error:
        raise RefitV02Error(str(error)) from error


def validate_corrected_annotation(
    document: dict[str, Any], repair_inputs: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    if sha256_file(ANNOTATION_PATH) != ANNOTATION_SHA256:
        raise RefitV02Error("Corrected annotation SHA-256 changed.")
    if (
        document.get("schema_version") != "1.0"
        or document.get("annotation_schema_version") != ANNOTATION_SCHEMA_VERSION
        or document.get("status") != "IMAGE_POINTS_COMPLETE_PENDING_HOMOGRAPHY_FIT"
        or document.get("immutable_after_creation") is not True
        or document.get("person_e_source_commit") != ANNOTATION_SOURCE_COMMIT
        or document.get("accepted_geometry_version")
        != repair.EXPECTED_GEOMETRY_VERSION
        or document.get("accepted_geometry_sha256")
        != repair.EXPECTED_GEOMETRY_SHA256
        or document.get("framebuffer")
        != {"height_pixels": 1046, "width_pixels": 1920}
        or document.get("image_coordinate_convention") != "pixel_center_xy_zero_based"
    ):
        raise RefitV02Error("Corrected annotation authority or schema changed.")
    method = document.get("annotation_method")
    if (
        not isinstance(method, dict)
        or method.get("algorithm_id") != repair.ANNOTATION_METHOD
        or method.get("operator_final_confirmation") is not True
        or method.get("visibility_preflight", {}).get("status") != "passed"
        or method.get("visibility_preflight", {}).get(
            "fully_occluded_or_ambiguous_points_requested"
        )
        != 0
        or method.get("repair", {}).get("reannotated_layout_ids")
        != list(REFITTED_LAYOUT_IDS)
        or method.get("repair", {}).get("reused_layout_ids")
        != list(REUSED_LAYOUT_IDS)
        or method.get("repair", {}).get("reannotation_point_count") != 10
        or method.get("repair", {}).get("homography_fit_performed") is not False
        or method.get("repair", {}).get("replacement_package_emitted") is not False
    ):
        raise RefitV02Error("Corrected annotation method binding changed.")

    layouts = _layout_map(document)
    base_layouts = repair_inputs["layouts"]
    for layout_id in REUSED_LAYOUT_IDS:
        if layouts[layout_id] != base_layouts[layout_id]:
            raise RefitV02Error(f"{layout_id} was not reused unchanged.")

    base_tasks = repair.build_tasks(repair_inputs)
    regions = repair.build_feature_regions(repair_inputs, base_tasks)
    for layout_id in REFITTED_LAYOUT_IDS:
        layout = layouts[layout_id]
        base = base_layouts[layout_id]
        if layout.get("screenshot") != base.get("screenshot"):
            raise RefitV02Error(f"{layout_id} screenshot binding changed.")
        fit = layout.get("fit_correspondences")
        heldout = layout.get("independent_validation_points")
        if not isinstance(fit, list) or len(fit) != 4:
            raise RefitV02Error(f"{layout_id} requires four fit points.")
        if not isinstance(heldout, list) or len(heldout) != 1:
            raise RefitV02Error(f"{layout_id} requires one validation point.")
        corrected_by_id = {
            point.get("point_id"): point
            for point in fit + heldout
            if isinstance(point, dict)
        }
        layout_tasks = [
            (task, region)
            for task, region in zip(base_tasks, regions)
            if task["layout_id"] == layout_id
        ]
        if set(corrected_by_id) != {task["point_id"] for task, _ in layout_tasks}:
            raise RefitV02Error(f"{layout_id} point identities changed.")
        fit_ids = {point["point_id"] for point in fit}
        heldout_ids = {point["point_id"] for point in heldout}
        if fit_ids & heldout_ids:
            raise RefitV02Error(f"{layout_id} validation point is not independent.")
        for task, region in layout_tasks:
            record = corrected_by_id[task["point_id"]]
            expected = copy.deepcopy(task["source_point"])
            expected.pop("image_xy_pixels")
            expected.pop("selection_status")
            actual = copy.deepcopy(record)
            image_xy_raw = actual.pop("image_xy_pixels", None)
            selection_status = actual.pop("selection_status", None)
            if actual != expected or selection_status != (
                "operator_reselected_nearest_neighbour_crop"
            ):
                raise RefitV02Error(
                    f"{layout_id} {task['point_id']} world/source binding changed."
                )
            image_xy = _point_pair(
                image_xy_raw, f"{layout_id} {task['point_id']} image point"
            )
            if (
                any(isinstance(value, bool) or not isinstance(value, int) for value in image_xy_raw)
                or not (0 <= image_xy[0] < 1920 and 0 <= image_xy[1] < 1046)
                or not repair.is_click_allowed(
                    region, (int(image_xy[0]), int(image_xy[1]))
                )
            ):
                raise RefitV02Error(
                    f"{layout_id} {task['point_id']} is outside its visible feature."
                )
            expected_kind = (
                "fit_correspondence" if record in fit else "independent_validation"
            )
            if task["kind"] != expected_kind:
                raise RefitV02Error(
                    f"{layout_id} {task['point_id']} fit/validation role changed."
                )
        if not v1._no_three_collinear(
            [_point_pair(point["world_xz_blocks"], "fit world") for point in fit]
        ) or not v1._no_three_collinear(
            [_point_pair(point["image_xy_pixels"], "fit image") for point in fit]
        ):
            raise RefitV02Error(f"{layout_id} fit points are duplicate or collinear.")
    return layouts


def load_validated_inputs() -> dict[str, Any]:
    if not ANNOTATION_PATH.is_file():
        raise RefitV02Error(f"Corrected annotation is missing: {ANNOTATION_PATH}")
    prior = verify_v1_package()
    repair_inputs = repair.verify_inputs()
    annotation = load_json(ANNOTATION_PATH)
    layouts = validate_corrected_annotation(annotation, repair_inputs)
    config = load_json(CONFIG_PATH)
    validate_person_e_config(config)
    if (
        config.get("homography", {}).get(
            "maximum_median_wall_parallel_error_blocks"
        )
        != 0.2
    ):
        raise RefitV02Error("Repository wall-parallel tolerance changed.")
    return {
        "annotation": annotation,
        "annotation_layouts": layouts,
        "repair_inputs": repair_inputs,
        "prior": prior,
        "config": config,
        "config_sha256": sha256_file(CONFIG_PATH),
    }


def _fit_layout(
    layout_id: str, layout: dict[str, Any], config: dict[str, Any], code_sha: str
) -> dict[str, Any]:
    homography_config = config["homography"]
    fit_points = layout["fit_correspondences"]
    validation_points = layout["independent_validation_points"]
    marker_ids = [point["point_id"] for point in fit_points]
    image_points = {
        point["point_id"]: point["image_xy_pixels"] for point in fit_points
    }
    world_points = {
        point["point_id"]: point["world_xz_blocks"] for point in fit_points
    }
    implementation_path = ROOT / "src" / "mineocclude" / "vision" / "homography.py"
    implementation_hash = sha256_file(implementation_path)
    correspondence_hash = v1.hash_json_value(
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
        detector_version=repair.ANNOTATION_METHOD,
        software_runtime_hash=implementation_hash,
    )
    matrix = [list(row) for row in homography.matrix]
    try:
        inverse = v1.inverse_matrix(matrix)
    except v1.RefitFinalizeError as error:
        raise RefitV02Error(str(error)) from error
    determinant = v1.determinant(matrix)
    rank = v1.matrix_rank(matrix)
    condition = v1.infinity_condition_number(matrix, inverse)
    fit_residuals = [
        v1._residual_record(homography, inverse, point) for point in fit_points
    ]
    validation_residuals = [
        v1._residual_record(homography, inverse, point)
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
        image_regions=["opposite_wall_endpoint"],
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
    roundtrip = []
    for point in fit_points + validation_points:
        image = _point_pair(point["image_xy_pixels"], "roundtrip image point")
        mapped_world = list(homography.transform(image))
        mapped_image = v1.project(inverse, mapped_world)
        roundtrip.append(
            {
                "point_id": point["point_id"],
                "input_image_xy_pixels": image,
                "roundtrip_image_xy_pixels": mapped_image,
                "roundtrip_error_pixels": math.dist(mapped_image, image),
            }
        )
    validation_image = validation_points[0]["image_xy_pixels"]
    true_world = validation_points[0]["world_xz_blocks"]
    mirrored_world = list(
        homography.transform([1919.0 - validation_image[0], validation_image[1]])
    )
    transposed_point = [validation_image[1], validation_image[0]]
    transposed_inside = (
        0 <= transposed_point[0] < 1920 and 0 <= transposed_point[1] < 1046
    )
    transposed_error = (
        math.dist(list(homography.transform(transposed_point)), true_world)
        if transposed_inside
        else None
    )
    validation_error = validation_residuals[0]["world_euclidean_error_blocks"]
    coordinate_guard = validation_error < math.dist(
        mirrored_world, true_world
    ) and (
        not transposed_inside
        or (transposed_error is not None and validation_error < transposed_error)
    )
    matrix_gate = (
        rank == 3
        and math.isfinite(determinant)
        and abs(determinant) > float(homography_config["singular_pivot_tolerance"])
        and math.isfinite(condition)
        and coordinate_guard
    )
    tolerance_pass = matrix_gate and heldout["planning_gate_passed"]
    return {
        "schema_version": "person-e-v0.4-layout-homography-refit-v0.2",
        "layout_id": layout_id,
        "status": "PASS" if tolerance_pass else "FAIL_REPOSITORY_TOLERANCE",
        "result_origin": "refit_from_corrected_layout_annotation",
        "source_code_commit": code_sha,
        "source_annotation_sha256": ANNOTATION_SHA256,
        "accepted_geometry_version": repair.EXPECTED_GEOMETRY_VERSION,
        "accepted_geometry_sha256": repair.EXPECTED_GEOMETRY_SHA256,
        "homography_algorithm": HOMOGRAPHY_ALGORITHM_VERSION,
        "matrix": matrix,
        "inverse_matrix": inverse,
        "determinant": determinant,
        "rank": rank,
        "condition_number": condition,
        "condition_number_method": "matrix_infinity_norm_v0.1",
        "homography": homography.to_record(),
        "fit_correspondence_count": 4,
        "fit_residuals": fit_residuals,
        "maximum_fit_reprojection_error_pixels": max(
            record["reprojection_error_pixels"] for record in fit_residuals
        ),
        "independent_validation_count": 1,
        "independent_validation_residuals": validation_residuals,
        "maximum_independent_validation_error_pixels": validation_residuals[0][
            "reprojection_error_pixels"
        ],
        "heldout_localization": heldout,
        "roundtrip_residuals": roundtrip,
        "maximum_roundtrip_error_pixels": max(
            record["roundtrip_error_pixels"] for record in roundtrip
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


def build_summary(inputs: dict[str, Any], code_sha: str) -> dict[str, Any]:
    v1._full_git_sha(code_sha, "code_sha")
    refitted = {
        layout_id: _fit_layout(
            layout_id,
            inputs["annotation_layouts"][layout_id],
            inputs["config"],
            code_sha,
        )
        for layout_id in REFITTED_LAYOUT_IDS
    }
    layouts = []
    for layout_id in EXPECTED_LAYOUT_IDS:
        if layout_id in inputs["prior"]["reused_layouts"]:
            layouts.append(copy.deepcopy(inputs["prior"]["reused_layouts"][layout_id]))
        else:
            layouts.append(refitted[layout_id])
    all_pass = all(layout["tolerance_result"] for layout in layouts)
    return {
        "schema_version": "person-e-v0.4-homography-refit-summary-v0.2",
        "status": "PASS" if all_pass else "FAIL_REPOSITORY_TOLERANCE",
        "source_code_commit": code_sha,
        "annotation_path": str(ANNOTATION_PATH.resolve()),
        "annotation_sha256": ANNOTATION_SHA256,
        "accepted_geometry_version": repair.EXPECTED_GEOMETRY_VERSION,
        "accepted_geometry_sha256": repair.EXPECTED_GEOMETRY_SHA256,
        "framebuffer": {"width_pixels": 1920, "height_pixels": 1046},
        "fov_degrees": 70.0,
        "homography_algorithm": HOMOGRAPHY_ALGORITHM_VERSION,
        "config_path": str(CONFIG_PATH.resolve()),
        "config_sha256": inputs["config_sha256"],
        "layout_count": 6,
        "successor_homography_count": 6,
        "reused_layout_ids": list(REUSED_LAYOUT_IDS),
        "refitted_layout_ids": list(REFITTED_LAYOUT_IDS),
        "passing_layout_count": sum(layout["tolerance_result"] for layout in layouts),
        "all_tolerances_pass": all_pass,
        "maximum_reprojection_error_pixels": max(
            layout["maximum_fit_reprojection_error_pixels"] for layout in layouts
        ),
        "maximum_independent_validation_error_pixels": max(
            layout["maximum_independent_validation_error_pixels"] for layout in layouts
        ),
        "maximum_roundtrip_error_pixels": max(
            layout["maximum_roundtrip_error_pixels"] for layout in layouts
        ),
        "failed_layout_ids": [
            layout["layout_id"] for layout in layouts if not layout["tolerance_result"]
        ],
        "layouts": layouts,
    }


def _external_record(path: Path) -> dict[str, Any]:
    return _file_record(path)


def build_package_documents(
    summary: dict[str, Any], inputs: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    layouts = summary["layouts"]
    prior = inputs["prior"]
    source_manifest = {
        "schema_version": "person-e-v0.4-refit-source-handoff-v0.2",
        "corrected_annotation": _external_record(ANNOTATION_PATH),
        "base_annotation": _external_record(repair.BASE_ANNOTATION),
        "person_c_handoff": inputs["annotation"]["source_handoff"],
        "preserved_v0_1_package": _external_record(V1_PACKAGE_MANIFEST),
        "preserved_v0_1_handoff": _external_record(V1_HANDOFF),
        "accepted_geometry_version": repair.EXPECTED_GEOMETRY_VERSION,
        "accepted_geometry_sha256": repair.EXPECTED_GEOMETRY_SHA256,
    }
    consumed = {
        "schema_version": "person-e-v0.4-refit-consumed-input-inventory-v0.2",
        "corrected_annotation": _external_record(ANNOTATION_PATH),
        "config": _external_record(CONFIG_PATH),
        "preserved_v0_1_package": _external_record(V1_PACKAGE_MANIFEST),
        "preserved_v0_1_inventory": _external_record(V1_INVENTORY),
        "verified_reused_layout_artifacts": {
            layout_id: copy.deepcopy(prior["reused_layout_records"][layout_id])
            for layout_id in REUSED_LAYOUT_IDS
        },
        "screenshots": [
            inputs["annotation_layouts"][layout_id]["screenshot"]
            for layout_id in EXPECTED_LAYOUT_IDS
        ],
        "geometry_receipts": inputs["annotation"]["source_verification"][
            "geometry_receipts"
        ],
    }
    coordinate = {
        "schema_version": "person-e-v0.4-refit-coordinate-convention-v0.2",
        "image_coordinate_convention": "pixel_center_xy_zero_based",
        "image_origin": "top_left_pixel_center",
        "image_x_direction": "right",
        "image_y_direction": "down",
        "world_coordinate_convention": "ground_plane_world_xz_blocks",
        "framebuffer": {"width_pixels": 1920, "height_pixels": 1046},
        "coordinate_transform": "none",
        "v0_1_verified_source": copy.deepcopy(
            prior["inventory_records"]["coordinate_convention.json"]
        ),
    }
    fit_summary = {key: value for key, value in summary.items() if key != "layouts"}
    fit_summary["layouts"] = [
        {
            "layout_id": layout["layout_id"],
            "result_origin": (
                "verified_v0_1_byte_reuse"
                if layout["layout_id"] in REUSED_LAYOUT_IDS
                else "v0_2_corrected_annotation_refit"
            ),
            "status": layout["status"],
            "homography_version_id": layout["homography"]["homography_version_id"],
            "matrix": layout["matrix"],
            "determinant": layout["determinant"],
            "rank": layout["rank"],
            "condition_number": layout["condition_number"],
            "maximum_fit_reprojection_error_pixels": layout[
                "maximum_fit_reprojection_error_pixels"
            ],
            "maximum_independent_validation_error_pixels": layout[
                "maximum_independent_validation_error_pixels"
            ],
            "maximum_roundtrip_error_pixels": layout[
                "maximum_roundtrip_error_pixels"
            ],
            "heldout_wall_parallel_error_blocks": layout["heldout_localization"][
                "median_absolute_wall_parallel_error_blocks"
            ],
            "tolerance_result": layout["tolerance_result"],
        }
        for layout in layouts
    ]
    reprojection = {
        "schema_version": "person-e-v0.4-refit-reprojection-validation-v0.2",
        "maximum_reprojection_error_pixels": summary["maximum_reprojection_error_pixels"],
        "layouts": [
            {
                "layout_id": layout["layout_id"],
                "fit_residuals": layout["fit_residuals"],
                "maximum_fit_reprojection_error_pixels": layout[
                    "maximum_fit_reprojection_error_pixels"
                ],
            }
            for layout in layouts
        ],
    }
    inverse = {
        "schema_version": "person-e-v0.4-refit-inverse-validation-v0.2",
        "maximum_independent_validation_error_pixels": summary[
            "maximum_independent_validation_error_pixels"
        ],
        "maximum_roundtrip_error_pixels": summary["maximum_roundtrip_error_pixels"],
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
            for layout in layouts
        ],
    }
    reuse = {
        "schema_version": "person-e-v0.4-refit-reuse-verification-v0.2",
        "preserved_v0_1_package_manifest": _external_record(V1_PACKAGE_MANIFEST),
        "preserved_v0_1_handoff": _external_record(V1_HANDOFF),
        "reused_layouts": [
            {
                "layout_id": layout_id,
                "source_artifact": copy.deepcopy(
                    prior["reused_layout_records"][layout_id]
                ),
                "reuse_status": "verified_pass_artifact_reused_byte_for_byte",
            }
            for layout_id in REUSED_LAYOUT_IDS
        ],
        "refitted_layout_ids": list(REFITTED_LAYOUT_IDS),
    }
    supersession = {
        "schema_version": "person-e-v0.4-historical-homography-supersession-v0.2",
        "status": "V0_2_ACCEPTED_SUCCESSOR_FOR_PERSON_C_LAYOUT_CONFIG_V0.4",
        "v0_1_failed_closed_artifacts_unchanged": True,
        "v0_1_package_manifest": _external_record(V1_PACKAGE_MANIFEST),
        "v0_1_handoff": _external_record(V1_HANDOFF),
        "v0_1_historical_supersession_record": copy.deepcopy(
            prior["inventory_records"]["historical_supersession.json"]
        ),
        "accepted_geometry_version": repair.EXPECTED_GEOMETRY_VERSION,
        "accepted_geometry_sha256": repair.EXPECTED_GEOMETRY_SHA256,
        "successor_homography_count": 6,
        "successor_acceptance_status": "ACCEPTED",
    }
    registry = {
        "schema_version": "person-e-v0.4-refit-registry-records-v0.2",
        "records": [
            {
                "layout_id": layout["layout_id"],
                "homography_version_id": layout["homography"][
                    "homography_version_id"
                ],
                "accepted_geometry_version": repair.EXPECTED_GEOMETRY_VERSION,
                "accepted_geometry_sha256": repair.EXPECTED_GEOMETRY_SHA256,
                "lifecycle_status": "accepted_successor",
                "result_origin": (
                    "verified_v0_1_byte_reuse"
                    if layout["layout_id"] in REUSED_LAYOUT_IDS
                    else "v0_2_corrected_annotation_refit"
                ),
                "tolerance_result": layout["tolerance_result"],
            }
            for layout in layouts
        ],
    }
    return {
        "source_handoff_manifest.json": source_manifest,
        "consumed_input_inventory.json": consumed,
        "coordinate_convention.json": coordinate,
        "fit_summary.json": fit_summary,
        "reprojection_validation.json": reprojection,
        "inverse_validation.json": inverse,
        "reuse_verification.json": reuse,
        "historical_supersession.json": supersession,
        "registry_records.json": registry,
    }


def validation_markdown(summary: dict[str, Any]) -> str:
    rows = [
        "# Person E Attempt 02 v0.2 homography refit validation",
        "",
        f"Overall status: **{summary['status']}**",
        "",
        "| Layout | Origin | Status | Wall-parallel error (blocks) | Independent error (pixels) |",
        "|---|---|---:|---:|---:|",
    ]
    for layout in summary["layouts"]:
        origin = (
            "verified v0.1 reuse"
            if layout["layout_id"] in REUSED_LAYOUT_IDS
            else "corrected v0.2 refit"
        )
        rows.append(
            f"| {layout['layout_id']} | {origin} | {layout['status']} | "
            f"{layout['heldout_localization']['median_absolute_wall_parallel_error_blocks']!r} | "
            f"{layout['maximum_independent_validation_error_pixels']!r} |"
        )
    rows.extend(
        [
            "",
            "Repository maximum held-out wall-parallel error: 0.2 blocks.",
            "",
            f"C6A execution authorized: **{summary['all_tolerances_pass']}**",
            "",
            "C6A was not executed.",
            "",
        ]
    )
    return "\n".join(rows)


def write_json_exclusive(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, indent=2, sort_keys=True)
        stream.write("\n")


def write_text_exclusive(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def package_manifest_document(
    summary: dict[str, Any], bundle_hash: str, inventory_record: dict[str, Any]
) -> dict[str, Any]:
    return {
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "status": summary["status"],
        "immutable": True,
        "package_directory": str(PACKAGE_DIR.resolve()),
        "package_bundle_sha256": bundle_hash,
        "sha256_inventory": inventory_record,
        "annotation_sha256": ANNOTATION_SHA256,
        "source_code_commit": summary["source_code_commit"],
        "accepted_geometry_version": repair.EXPECTED_GEOMETRY_VERSION,
        "accepted_geometry_sha256": repair.EXPECTED_GEOMETRY_SHA256,
        "successor_homography_count": 6,
        "passing_layout_count": summary["passing_layout_count"],
        "failed_layout_ids": summary["failed_layout_ids"],
        "all_tolerances_pass": summary["all_tolerances_pass"],
        "c6a_execution_authorized": summary["all_tolerances_pass"],
        "c6a_executed": False,
        "preserved_v0_1_failed_closed_artifacts": True,
    }


def handoff_document(
    summary: dict[str, Any],
    bundle_hash: str,
    package_manifest_record: dict[str, Any],
    layout_records: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "status": "READY_FOR_C6A" if summary["all_tolerances_pass"] else (
            "REFIT_VALIDATION_FAILED_C6A_NOT_AUTHORIZED"
        ),
        "immutable": True,
        "person_e_refit_package": package_manifest_record,
        "package_bundle_sha256": bundle_hash,
        "source_code_commit": summary["source_code_commit"],
        "annotation": _external_record(ANNOTATION_PATH),
        "preserved_v0_1_package": _external_record(V1_PACKAGE_MANIFEST),
        "preserved_v0_1_handoff": _external_record(V1_HANDOFF),
        "person_c_calibration_handoff": inputs_source_handoff(),
        "accepted_geometry_version": repair.EXPECTED_GEOMETRY_VERSION,
        "accepted_geometry_sha256": repair.EXPECTED_GEOMETRY_SHA256,
        "homography_algorithm": HOMOGRAPHY_ALGORITHM_VERSION,
        "successor_homography_count": 6,
        "layout_results": [
            {
                "layout_id": layout["layout_id"],
                "result_origin": (
                    "verified_v0_1_byte_reuse"
                    if layout["layout_id"] in REUSED_LAYOUT_IDS
                    else "v0_2_corrected_annotation_refit"
                ),
                "tolerance_result": layout["tolerance_result"],
                "homography_file": layout_records[layout["layout_id"]],
            }
            for layout in summary["layouts"]
        ],
        "all_tolerances_pass": summary["all_tolerances_pass"],
        "c6a_execution_authorized": summary["all_tolerances_pass"],
        "c6a_execution_command": None,
        "c6a_executed": False,
        "blocking_layout_ids": summary["failed_layout_ids"],
    }


def inputs_source_handoff() -> dict[str, Any]:
    return load_json(ANNOTATION_PATH)["source_handoff"]


def emit_package(summary: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    if not summary["all_tolerances_pass"]:
        raise RefitV02Error("Refusing to emit a package with failed tolerances.")
    documents = build_package_documents(summary, inputs)
    output_paths = [PACKAGE_DIR / name for name in documents]
    output_paths.extend(
        PACKAGE_DIR / f"{layout_id}_homography.json"
        for layout_id in EXPECTED_LAYOUT_IDS
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
            "Create-only v0.2 outputs already exist: "
            + ", ".join(str(path) for path in existing)
        )
    for name, document in documents.items():
        write_json_exclusive(PACKAGE_DIR / name, document)
    summary_by_id = {layout["layout_id"]: layout for layout in summary["layouts"]}
    for layout_id in EXPECTED_LAYOUT_IDS:
        destination = PACKAGE_DIR / f"{layout_id}_homography.json"
        if layout_id in REUSED_LAYOUT_IDS:
            with (V1_PACKAGE_DIR / destination.name).open("rb") as source:
                with destination.open("xb") as target:
                    shutil.copyfileobj(source, target)
        else:
            write_json_exclusive(destination, summary_by_id[layout_id])
    report_path = PACKAGE_DIR / "validation_report.md"
    write_text_exclusive(report_path, validation_markdown(summary))
    payload_paths = [ANNOTATION_PATH, *[PACKAGE_DIR / name for name in documents]]
    payload_paths.extend(
        PACKAGE_DIR / f"{layout_id}_homography.json"
        for layout_id in EXPECTED_LAYOUT_IDS
    )
    payload_paths.append(report_path)
    inventory_records = [
        _file_record(path, relative_to_package=True) for path in payload_paths
    ]
    bundle_hash = v1.hash_json_value(inventory_records)
    inventory = {
        "schema_version": "person-e-v0.4-refit-sha256-inventory-v0.2",
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
    manifest = package_manifest_document(
        summary, bundle_hash, _file_record(inventory_path)
    )
    manifest_path = PACKAGE_DIR / "package_manifest.json"
    write_json_exclusive(manifest_path, manifest)
    layout_records = {
        layout_id: _file_record(PACKAGE_DIR / f"{layout_id}_homography.json")
        for layout_id in EXPECTED_LAYOUT_IDS
    }
    handoff = handoff_document(
        summary, bundle_hash, _file_record(manifest_path), layout_records
    )
    handoff_path = PACKAGE_DIR / "person_e_to_person_c_refit_handoff.json"
    write_json_exclusive(handoff_path, handoff)
    repair.verify_preserved_artifacts()
    return {
        "package_manifest_path": manifest_path,
        "package_manifest_sha256": sha256_file(manifest_path),
        "package_bundle_sha256": bundle_hash,
        "handoff_path": handoff_path,
        "handoff_sha256": sha256_file(handoff_path),
    }


def validate_emitted_package() -> dict[str, Any]:
    manifest_path = PACKAGE_DIR / "package_manifest.json"
    handoff_path = PACKAGE_DIR / "person_e_to_person_c_refit_handoff.json"
    manifest = load_json(manifest_path)
    handoff = load_json(handoff_path)
    if (
        manifest.get("schema_version") != PACKAGE_SCHEMA_VERSION
        or manifest.get("all_tolerances_pass") is not True
        or manifest.get("c6a_execution_authorized") is not True
        or manifest.get("c6a_executed") is not False
        or manifest.get("successor_homography_count") != 6
        or manifest.get("failed_layout_ids") != []
    ):
        raise RefitV02Error("Emitted v0.2 package manifest fails closed.")
    inventory_path = PACKAGE_DIR / "sha256_inventory.json"
    _verify_record(inventory_path, manifest["sha256_inventory"], "v0.2 inventory")
    inventory = load_json(inventory_path)
    records = inventory.get("files")
    if (
        not isinstance(records, list)
        or v1.hash_json_value(records) != inventory.get("package_bundle_sha256")
        or inventory.get("package_bundle_sha256")
        != manifest.get("package_bundle_sha256")
    ):
        raise RefitV02Error("Emitted v0.2 bundle hash is invalid.")
    for record in records:
        relative = Path(record["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise RefitV02Error("v0.2 inventory contains an unsafe path.")
        _verify_record(PACKAGE_DIR / relative, record, f"v0.2 {record['path']}")
    if (
        handoff.get("schema_version") != HANDOFF_SCHEMA_VERSION
        or handoff.get("status") != "READY_FOR_C6A"
        or handoff.get("immutable") is not True
        or handoff.get("all_tolerances_pass") is not True
        or handoff.get("c6a_execution_authorized") is not True
        or handoff.get("c6a_execution_command") is not None
        or handoff.get("c6a_executed") is not False
        or handoff.get("blocking_layout_ids") != []
        or handoff.get("person_e_refit_package", {}).get("sha256")
        != sha256_file(manifest_path)
    ):
        raise RefitV02Error("Emitted E-to-C authorization handoff is invalid.")
    for layout_id in REUSED_LAYOUT_IDS:
        new_path = PACKAGE_DIR / f"{layout_id}_homography.json"
        old_path = V1_PACKAGE_DIR / f"{layout_id}_homography.json"
        if sha256_file(new_path) != sha256_file(old_path):
            raise RefitV02Error(f"{layout_id} was not byte-reused from v0.1.")
    repair.verify_preserved_artifacts()
    return {
        "package_manifest_sha256": sha256_file(manifest_path),
        "handoff_sha256": sha256_file(handoff_path),
    }


def current_git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return v1._full_git_sha(result.stdout.strip(), "current Git commit")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Finalize the corrected Attempt 02 v0.2 Person E refit."
    )
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--validate-package-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.validate_package_only:
        result = validate_emitted_package()
        print("PACKAGE_VALID=True")
        print(f"PACKAGE_MANIFEST_SHA256={result['package_manifest_sha256']}")
        print(f"HANDOFF_SHA256={result['handoff_sha256']}")
        return
    code_sha = v1._full_git_sha(args.code_sha, "code_sha")
    if current_git_commit() != code_sha:
        raise RefitV02Error("--code-sha must equal the current Git commit.")
    inputs = load_validated_inputs()
    summary = build_summary(inputs, code_sha)
    by_id = {layout["layout_id"]: layout for layout in summary["layouts"]}
    print("CORRECTED_ANNOTATION_VALID=True")
    print(f"CORRECTED_ANNOTATION_SHA256={ANNOTATION_SHA256}")
    for layout_id in EXPECTED_LAYOUT_IDS:
        print(f"{layout_id.upper()}_REFIT_PASS={by_id[layout_id]['tolerance_result']}")
    for layout_id in REFITTED_LAYOUT_IDS:
        value = by_id[layout_id]["heldout_localization"][
            "median_absolute_wall_parallel_error_blocks"
        ]
        print(f"{layout_id.upper()}_VALIDATION_ERROR_BLOCKS={value!r}")
    print("SUCCESSOR_HOMOGRAPHY_COUNT=6")
    print(f"ALL_TOLERANCES_PASS={summary['all_tolerances_pass']}")
    if args.check_only:
        return
    emitted = emit_package(summary, inputs)
    for key, value in emitted.items():
        print(f"{key.upper()}={value}")


if __name__ == "__main__":
    try:
        main()
    except (
        RefitV02Error,
        v1.RefitFinalizeError,
        repair.RepairInputError,
        FileExistsError,
        OSError,
        ValueError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2) from error
