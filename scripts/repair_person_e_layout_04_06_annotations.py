"""Create-only targeted reannotation for Attempt 02 layouts 04 and 06.

The original six-layout annotation and its failed-closed package are immutable
inputs.  This tool copies layouts 01, 02, 03, and 05 byte-for-byte at the JSON
value level, asks the operator to reselect all five authorized points in each
failed layout, and writes a new additive six-layout annotation.  It never fits
a homography or emits a package.
"""

from __future__ import annotations

import argparse
import colorsys
import copy
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.vision.markers import MARKER_COLOUR_GATES
from mineocclude.vision.png_decode import load_png_rgb


TARGET_LAYOUT_IDS = ("layout_04", "layout_06")
REUSED_LAYOUT_IDS = ("layout_01", "layout_02", "layout_03", "layout_05")
EXPECTED_LAYOUT_IDS = tuple(f"layout_{index:02d}" for index in range(1, 7))
EXPECTED_POINT_IDS = (
    "near_west",
    "near_east",
    "far_east",
    "wall_near_face_ground_negative_end",
    "wall_near_face_ground_positive_end",
)
FRAMEBUFFER = (1920, 1046)
BASE_ANNOTATION = (
    ROOT
    / "data"
    / "handoff_e"
    / "person_e_v0_4_homography_refit_v0_1"
    / "person_e_attempt_02_image_points_v0_1.json"
)
BASE_ANNOTATION_SHA256 = (
    "9747e1dc9a497d29df8aaff83fc605465a980a73edfaddee1f43d6e8a92671c0"
)
BASE_PACKAGE = BASE_ANNOTATION.parent / "package_manifest.json"
BASE_PACKAGE_SHA256 = (
    "bfc1124f98663bd988178ba79ecaf009ac9db7158f4b860682870117462f883b"
)
BASE_HANDOFF = BASE_ANNOTATION.parent / "person_e_to_person_c_refit_handoff.json"
BASE_HANDOFF_SHA256 = (
    "f9039150e42808e3477552467794a64c4f05543a9661c4a28f5251f6ea82fe74"
)
DEFAULT_OUTPUT = (
    ROOT
    / "data"
    / "handoff_e"
    / "person_e_v0_4_homography_refit_v0_2"
    / "person_e_attempt_02_image_points_v0_2.json"
)
EXPECTED_GEOMETRY_VERSION = "person-c-layout-config-v0.4"
EXPECTED_GEOMETRY_SHA256 = (
    "34495d650d6a8c62b00a916796c90389b48f80d8f20a23eac93207758e993f5d"
)
REQUIRED_ANCESTOR = "fd44bb40b20c7112a900e2495596f4d8605bbfbd"
OUTPUT_ANNOTATION_SCHEMA = (
    "person-e-v0.4-image-point-annotations-attempt-02-layout-04-06-repair-v0.1"
)
ANNOTATION_METHOD = (
    "person-e-layout-04-06-nearest-neighbour-manual-point-selector-v0.1"
)
ZOOM = 8
CROP_RADIUS = 32
REGION_RADIUS = 48

# Screen edge containing each world-axis endpoint.  These bindings are visible
# in the exact screenshots and agree with the receipt camera orientations.
WALL_SCREEN_EDGE = {
    ("layout_04", "wall_near_face_ground_negative_end"): "right",
    ("layout_04", "wall_near_face_ground_positive_end"): "left",
    ("layout_06", "wall_near_face_ground_negative_end"): "left",
    ("layout_06", "wall_near_face_ground_positive_end"): "right",
}


class RepairInputError(ValueError):
    """Raised when an immutable input or a selected point fails closed."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RepairInputError(f"{path} must contain a JSON object.")
    return value


def _verify_path(path: Path, expected_sha256: str, label: str) -> None:
    if not path.is_file():
        raise RepairInputError(f"Missing {label}: {path}")
    actual = sha256_file(path)
    if actual != expected_sha256:
        raise RepairInputError(
            f"{label} SHA-256 changed: expected {expected_sha256}, got {actual}."
        )


def verify_preserved_artifacts() -> None:
    _verify_path(BASE_ANNOTATION, BASE_ANNOTATION_SHA256, "base annotation")
    _verify_path(BASE_PACKAGE, BASE_PACKAGE_SHA256, "failed-closed package")
    _verify_path(BASE_HANDOFF, BASE_HANDOFF_SHA256, "failed-closed handoff")


def _layout_map(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    layouts = document.get("layouts")
    if not isinstance(layouts, list):
        raise RepairInputError("Base annotation layouts are malformed.")
    mapped = {
        layout.get("layout_id"): layout
        for layout in layouts
        if isinstance(layout, dict) and isinstance(layout.get("layout_id"), str)
    }
    if tuple(sorted(mapped)) != EXPECTED_LAYOUT_IDS or len(mapped) != 6:
        raise RepairInputError("Base annotation must contain the six exact layouts.")
    return mapped


def _verify_record(record: Any, label: str) -> Path:
    if not isinstance(record, dict):
        raise RepairInputError(f"{label} record is malformed.")
    try:
        path = Path(record["path"])
        expected_size = int(record["size_bytes"])
        expected_sha = str(record["sha256"])
    except (KeyError, TypeError, ValueError) as error:
        raise RepairInputError(f"{label} record is incomplete.") from error
    _verify_path(path, expected_sha, label)
    if path.stat().st_size != expected_size:
        raise RepairInputError(f"{label} size changed.")
    return path


def _point_map(layout: dict[str, Any]) -> dict[str, dict[str, Any]]:
    fit = layout.get("fit_correspondences")
    heldout = layout.get("independent_validation_points")
    if not isinstance(fit, list) or len(fit) != 4:
        raise RepairInputError(f"{layout.get('layout_id')} must have four fit points.")
    if not isinstance(heldout, list) or len(heldout) != 1:
        raise RepairInputError(
            f"{layout.get('layout_id')} must have one independent validation point."
        )
    points = fit + heldout
    mapped = {
        point.get("point_id"): point
        for point in points
        if isinstance(point, dict) and isinstance(point.get("point_id"), str)
    }
    if tuple(mapped) != EXPECTED_POINT_IDS or len(mapped) != 5:
        raise RepairInputError(
            f"{layout.get('layout_id')} point identities or ordering changed."
        )
    return mapped


def _verify_world_binding(
    layout_id: str,
    layout: dict[str, Any],
    receipt: dict[str, Any],
) -> None:
    if receipt.get("layout_id") != layout_id:
        raise RepairInputError(f"{layout_id} receipt identity changed.")
    points = _point_map(layout)
    receipt_markers = receipt.get("markers")
    if not isinstance(receipt_markers, list) or len(receipt_markers) != 4:
        raise RepairInputError(f"{layout_id} receipt marker set is malformed.")
    marker_by_role = {
        marker.get("role"): marker
        for marker in receipt_markers
        if isinstance(marker, dict)
    }
    for point_id in ("near_west", "near_east", "far_east"):
        point = points[point_id]
        marker = marker_by_role.get(point_id)
        expected_xyz = point.get("top_face_centre_world_xyz")
        if (
            not isinstance(marker, dict)
            or marker.get("matches") is not True
            or marker.get("color") != point.get("marker_color")
            or marker.get("top_face_centre_world_xyz") != expected_xyz
            or point.get("world_xz_blocks")
            != [expected_xyz[0], expected_xyz[2]]
        ):
            raise RepairInputError(
                f"{layout_id} {point_id} marker/world binding changed."
            )

    wall = receipt.get("wall")
    if (
        not isinstance(wall, dict)
        or wall.get("mismatches") != []
        or wall.get("matching_position_count") != wall.get("expected_position_count")
        or wall.get("y_min_block_inclusive") != 4
    ):
        raise RepairInputError(f"{layout_id} wall receipt is not authoritative.")
    minimum = float(wall["declared_axis_min_block_inclusive"])
    maximum_edge = float(wall["declared_axis_max_block_inclusive"] + 1)
    ortho = float(wall["ortho_block"])
    if wall.get("axis") == "X":
        negative_world = [minimum, ortho]
        positive_world = [maximum_edge, ortho]
    elif wall.get("axis") == "Z":
        negative_world = [ortho, minimum]
        positive_world = [ortho, maximum_edge]
    else:
        raise RepairInputError(f"{layout_id} wall axis changed.")
    if (
        [float(v) for v in points["wall_near_face_ground_negative_end"]["world_xz_blocks"]]
        != negative_world
        or [float(v) for v in points["wall_near_face_ground_positive_end"]["world_xz_blocks"]]
        != positive_world
    ):
        raise RepairInputError(f"{layout_id} wall endpoint/world binding changed.")


def verify_inputs() -> dict[str, Any]:
    verify_preserved_artifacts()
    document = load_json(BASE_ANNOTATION)
    if (
        document.get("accepted_geometry_version") != EXPECTED_GEOMETRY_VERSION
        or document.get("accepted_geometry_sha256") != EXPECTED_GEOMETRY_SHA256
        or document.get("framebuffer")
        != {"height_pixels": FRAMEBUFFER[1], "width_pixels": FRAMEBUFFER[0]}
        or document.get("image_coordinate_convention") != "pixel_center_xy_zero_based"
    ):
        raise RepairInputError("Base geometry or pixel coordinate convention changed.")

    layouts = _layout_map(document)
    receipt_records = document.get("source_verification", {}).get(
        "geometry_receipts"
    )
    if not isinstance(receipt_records, list):
        raise RepairInputError("Base geometry receipt records are malformed.")
    receipt_by_layout = {
        record.get("layout_id"): record
        for record in receipt_records
        if isinstance(record, dict)
    }
    frames: dict[str, list[list[list[int]]]] = {}
    target_receipts: dict[str, dict[str, Any]] = {}
    for layout_id in TARGET_LAYOUT_IDS:
        layout = layouts[layout_id]
        screenshot_path = _verify_record(
            layout.get("screenshot"), f"{layout_id} screenshot"
        )
        frame, _decoder = load_png_rgb(screenshot_path)
        if len(frame) != FRAMEBUFFER[1] or len(frame[0]) != FRAMEBUFFER[0]:
            raise RepairInputError(f"{layout_id} screenshot dimensions changed.")
        receipt_path = _verify_record(
            receipt_by_layout.get(layout_id), f"{layout_id} geometry receipt"
        )
        receipt = load_json(receipt_path)
        _verify_world_binding(layout_id, layout, receipt)
        frames[layout_id] = frame
        target_receipts[layout_id] = receipt
    return {
        "document": document,
        "layouts": layouts,
        "frames": frames,
        "receipts": target_receipts,
    }


def build_tasks(verified: dict[str, Any]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for layout_id in TARGET_LAYOUT_IDS:
        layout = verified["layouts"][layout_id]
        for kind, points in (
            ("fit_correspondence", layout["fit_correspondences"]),
            ("independent_validation", layout["independent_validation_points"]),
        ):
            for source_point in points:
                point = copy.deepcopy(source_point)
                image_xy = point.get("image_xy_pixels")
                if (
                    not isinstance(image_xy, list)
                    or len(image_xy) != 2
                    or any(not isinstance(value, int) for value in image_xy)
                ):
                    raise RepairInputError(
                        f"{layout_id} {point.get('point_id')} base pixel is malformed."
                    )
                tasks.append(
                    {
                        "layout_id": layout_id,
                        "kind": kind,
                        "point_id": point["point_id"],
                        "marker_color": point["marker_color"],
                        "location_description": point["location_description"],
                        "world_xz_blocks": point["world_xz_blocks"],
                        "source_kind": point["source_kind"],
                        "original_image_xy_pixels": tuple(image_xy),
                        "source_point": point,
                        "screenshot": layout["screenshot"],
                    }
                )
    if len(tasks) != 10:
        raise RepairInputError(f"Expected 10 targeted tasks, got {len(tasks)}.")
    return tasks


def _components(pixels: set[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    remaining = set(pixels)
    found: list[set[tuple[int, int]]] = []
    while remaining:
        seed = min(remaining, key=lambda point: (point[1], point[0]))
        stack = [seed]
        remaining.remove(seed)
        component: set[tuple[int, int]] = set()
        while stack:
            x, y = stack.pop()
            component.add((x, y))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    neighbour = (x + dx, y + dy)
                    if neighbour in remaining:
                        remaining.remove(neighbour)
                        stack.append(neighbour)
        found.append(component)
    return sorted(
        found,
        key=lambda component: (
            -len(component),
            min(point[1] for point in component),
            min(point[0] for point in component),
        ),
    )


def _marker_pixel_matches(pixel: list[int], colour: str) -> bool:
    red, green, blue = (channel / 255.0 for channel in pixel)
    hue, saturation, value = colorsys.rgb_to_hsv(red, green, blue)
    hue *= 360.0
    hue_min, hue_max, sat_min, sat_max, value_min, value_max = (
        MARKER_COLOUR_GATES[colour]
    )
    hue_ok = (
        hue_min <= hue <= hue_max
        if hue_min <= hue_max
        else hue >= hue_min or hue <= hue_max
    )
    return (
        hue_ok
        and sat_min <= saturation <= sat_max
        and value_min <= value <= value_max
    )


def _bounded_region(
    centre: tuple[int, int], radius: int
) -> tuple[int, int, int, int]:
    x, y = centre
    return (
        max(0, x - radius),
        max(0, y - radius),
        min(FRAMEBUFFER[0] - 1, x + radius),
        min(FRAMEBUFFER[1] - 1, y + radius),
    )


def _nearest_component(
    components: list[set[tuple[int, int]]], centre: tuple[int, int]
) -> set[tuple[int, int]]:
    if not components:
        raise RepairInputError("No visible feature region was detected.")
    cx, cy = centre
    return min(
        components,
        key=lambda component: (
            min((x - cx) ** 2 + (y - cy) ** 2 for x, y in component),
            -len(component),
        ),
    )


def _marker_region(
    frame: list[list[list[int]]], task: dict[str, Any]
) -> dict[str, Any]:
    colour = task["marker_color"]
    if colour not in MARKER_COLOUR_GATES:
        raise RepairInputError(f"No deterministic gate exists for {colour}.")
    bounds = _bounded_region(task["original_image_xy_pixels"], REGION_RADIUS)
    x0, y0, x1, y1 = bounds
    matched = {
        (x, y)
        for y in range(y0, y1 + 1)
        for x in range(x0, x1 + 1)
        if _marker_pixel_matches(frame[y][x], colour)
    }
    component = _nearest_component(_components(matched), task["original_image_xy_pixels"])
    if len(component) < 4:
        raise RepairInputError(
            f"{task['layout_id']} {task['point_id']} marker region is too small."
        )
    distance_squared = min(
        (x - task["original_image_xy_pixels"][0]) ** 2
        + (y - task["original_image_xy_pixels"][1]) ** 2
        for x, y in component
    )
    if distance_squared > 64:
        raise RepairInputError(
            f"{task['layout_id']} {task['point_id']} marker identity is ambiguous."
        )
    return {
        "allowed_pixels": component,
        "diagnostic": {
            "method": "repository_hsv_gate_nearest_8_connected_component",
            "confidence": "high",
            "component_pixels": len(component),
        },
    }


def _wall_region(
    frame: list[list[list[int]]], task: dict[str, Any]
) -> dict[str, Any]:
    bounds = _bounded_region(task["original_image_xy_pixels"], REGION_RADIUS)
    x0, y0, x1, y1 = bounds
    stone = set()
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            red, green, blue = frame[y][x]
            if max(red, green, blue) - min(red, green, blue) <= 3 and 30 <= max(
                red, green, blue
            ) <= 140:
                stone.add((x, y))
    component = _nearest_component(_components(stone), task["original_image_xy_pixels"])
    if len(component) < 100:
        raise RepairInputError(
            f"{task['layout_id']} {task['point_id']} wall region is too small."
        )
    screen_edge = WALL_SCREEN_EDGE[(task["layout_id"], task["point_id"])]
    anchor_x = (
        min(x for x, _y in component)
        if screen_edge == "left"
        else max(x for x, _y in component)
    )
    edge_pixels = [(x, y) for x, y in component if x == anchor_x]
    anchor_y = max(y for _x, y in edge_pixels)
    anchor = (anchor_x, anchor_y)
    allowed = {
        (x, y)
        for y in range(anchor_y - 2, anchor_y + 3)
        for x in range(anchor_x - 2, anchor_x + 3)
        if 0 <= x < FRAMEBUFFER[0] and 0 <= y < FRAMEBUFFER[1]
    }
    return {
        "allowed_pixels": allowed,
        "anchor": anchor,
        "diagnostic": {
            "method": (
                "single_local_grayscale_stone_component_visible_screen_edge_"
                "and_ground_contact"
            ),
            "confidence": "high_diagnostic_operator_selection_still_required",
            "component_pixels": len(component),
            "visible_corner_anchor_pixels": list(anchor),
        },
    }


def build_feature_regions(
    verified: dict[str, Any], tasks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    regions = []
    for task in tasks:
        frame = verified["frames"][task["layout_id"]]
        if task["source_kind"] == "marker":
            regions.append(_marker_region(frame, task))
        elif task["source_kind"] == "validation_feature":
            regions.append(_wall_region(frame, task))
        else:
            raise RepairInputError(
                f"{task['layout_id']} {task['point_id']} source kind changed."
            )
    return regions


def is_click_allowed(region: dict[str, Any], image_xy: tuple[int, int]) -> bool:
    return image_xy in region["allowed_pixels"]


def map_zoom_click(
    crop_origin: tuple[int, int], event_xy: tuple[int, int], zoom: int = ZOOM
) -> tuple[int, int]:
    if zoom <= 0:
        raise RepairInputError("Zoom must be positive.")
    return (
        crop_origin[0] + event_xy[0] // zoom,
        crop_origin[1] + event_xy[1] // zoom,
    )


def current_git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    value = result.stdout.strip()
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise RepairInputError("Current Git commit is not a full lowercase SHA.")
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", REQUIRED_ANCESTOR, value],
        cwd=ROOT,
        check=False,
    )
    if ancestor.returncode != 0:
        raise RepairInputError("Current commit does not descend from the repair base.")
    return value


def build_output_document(
    verified: dict[str, Any],
    tasks: list[dict[str, Any]],
    selections: list[tuple[int, int]],
) -> dict[str, Any]:
    if len(tasks) != 10 or len(selections) != 10:
        raise RepairInputError("All 10 targeted points are required.")
    output = copy.deepcopy(verified["document"])
    output["annotation_schema_version"] = OUTPUT_ANNOTATION_SCHEMA
    output["created_utc"] = datetime.now(timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )
    output["person_e_source_commit"] = current_git_commit()
    output["status"] = "IMAGE_POINTS_COMPLETE_PENDING_HOMOGRAPHY_FIT"
    layout_by_id = _layout_map(output)
    for task, image_xy in zip(tasks, selections):
        x, y = image_xy
        if not (0 <= x < FRAMEBUFFER[0] and 0 <= y < FRAMEBUFFER[1]):
            raise RepairInputError(
                f"{task['layout_id']} {task['point_id']} is outside the screenshot."
            )
        points = _point_map(layout_by_id[task["layout_id"]])
        record = points[task["point_id"]]
        if record["world_xz_blocks"] != task["world_xz_blocks"]:
            raise RepairInputError("A world-coordinate binding changed during repair.")
        record["image_xy_pixels"] = [x, y]
        record["selection_status"] = "operator_reselected_nearest_neighbour_crop"

    output["annotation_method"] = {
        "algorithm_id": ANNOTATION_METHOD,
        "selection": "manual_left_click_on_8x_nearest_neighbour_crop",
        "coordinate_transform": (
            "original_x=crop_left+floor(crop_x/8);"
            "original_y=crop_top+floor(crop_y/8)"
        ),
        "fit_point_definition": "receipt_authorized_visible_ground_plane_feature",
        "operator_final_confirmation": True,
        "repair": {
            "base_annotation": {
                "path": str(BASE_ANNOTATION.resolve()),
                "sha256": BASE_ANNOTATION_SHA256,
            },
            "preserved_failed_closed_package": {
                "path": str(BASE_PACKAGE.resolve()),
                "sha256": BASE_PACKAGE_SHA256,
            },
            "preserved_failed_closed_handoff": {
                "path": str(BASE_HANDOFF.resolve()),
                "sha256": BASE_HANDOFF_SHA256,
            },
            "reannotated_layout_ids": list(TARGET_LAYOUT_IDS),
            "reused_layout_ids": list(REUSED_LAYOUT_IDS),
            "reannotation_point_count": 10,
            "click_rejection": (
                "marker clicks must be inside the deterministic visible top-face "
                "color component; wall clicks must be inside the detected visible "
                "ground-contact corner neighbourhood"
            ),
            "homography_fit_performed": False,
            "replacement_package_emitted": False,
        },
        "visibility_preflight": {
            "status": "passed",
            "basis": (
                "exact layout_04/layout_06 screenshots, exact receipts, and "
                "deterministic local visible-feature regions"
            ),
            "fully_occluded_or_ambiguous_points_requested": 0,
        },
    }
    output["source_verification"]["repair_base_annotation"] = {
        "path": str(BASE_ANNOTATION.resolve()),
        "size_bytes": BASE_ANNOTATION.stat().st_size,
        "sha256": BASE_ANNOTATION_SHA256,
    }
    return output


def write_json_create_only(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, indent=2, sort_keys=True)
        stream.write("\n")


class RepairWindow:
    def __init__(
        self,
        verified: dict[str, Any],
        tasks: list[dict[str, Any]],
        regions: list[dict[str, Any]],
        output_path: Path,
    ) -> None:
        import tkinter as tk
        from tkinter import messagebox

        self.tk = tk
        self.messagebox = messagebox
        self.verified = verified
        self.tasks = tasks
        self.regions = regions
        self.output_path = output_path
        self.selections: list[tuple[int, int]] = []
        self.task_index = 0
        self.loaded_layout_id: str | None = None
        self.photo: Any = None
        self.crop_photo: Any = None
        self.zoom_photo: Any = None
        self.crop_centre = (0, 0)
        self.crop_origin = (0, 0)

        self.root = tk.Tk()
        self.root.title("Person E layouts 04/06 targeted annotation repair")
        try:
            self.root.state("zoomed")
        except tk.TclError:
            self.root.geometry("1600x900")
        self.prompt = tk.Label(
            self.root,
            anchor="w",
            justify="left",
            font=("TkDefaultFont", 11, "bold"),
            padx=8,
            pady=6,
        )
        self.prompt.grid(row=0, column=0, columnspan=3, sticky="ew")
        self.help = tk.Label(
            self.root,
            text=(
                "Click the 8x nearest-neighbour crop to select. Click the full "
                "image or use arrow keys to recenter. Backspace/right click "
                "undoes. Escape cancels without writing."
            ),
            anchor="w",
            padx=8,
        )
        self.help.grid(row=1, column=0, columnspan=3, sticky="ew")

        self.full_canvas = tk.Canvas(
            self.root, width=930, height=720, background="#202020", cursor="crosshair"
        )
        xbar = tk.Scrollbar(self.root, orient="horizontal", command=self.full_canvas.xview)
        ybar = tk.Scrollbar(self.root, orient="vertical", command=self.full_canvas.yview)
        self.full_canvas.configure(xscrollcommand=xbar.set, yscrollcommand=ybar.set)
        self.full_canvas.grid(row=2, column=0, sticky="nsew")
        ybar.grid(row=2, column=1, sticky="ns")
        xbar.grid(row=3, column=0, sticky="ew")
        zoom_size = (2 * CROP_RADIUS + 1) * ZOOM
        self.zoom_canvas = tk.Canvas(
            self.root,
            width=zoom_size,
            height=zoom_size,
            background="#101010",
            cursor="crosshair",
        )
        self.zoom_canvas.grid(row=2, column=2, padx=8, pady=8, sticky="n")
        self.root.rowconfigure(2, weight=1)
        self.root.columnconfigure(0, weight=1)

        self.full_canvas.bind("<Button-1>", self._recenter_from_full)
        self.zoom_canvas.bind("<Button-1>", self._select_from_zoom)
        self.full_canvas.bind("<Button-3>", self._undo)
        self.zoom_canvas.bind("<Button-3>", self._undo)
        self.root.bind("<BackSpace>", self._undo)
        self.root.bind("<Escape>", self._cancel)
        self.root.bind("<Left>", lambda _event: self._pan(-8, 0))
        self.root.bind("<Right>", lambda _event: self._pan(8, 0))
        self.root.bind("<Up>", lambda _event: self._pan(0, -8))
        self.root.bind("<Down>", lambda _event: self._pan(0, 8))
        self.root.protocol("WM_DELETE_WINDOW", self._cancel)
        self._show_current_task()

    def _show_current_task(self) -> None:
        task = self.tasks[self.task_index]
        if self.loaded_layout_id != task["layout_id"]:
            self.photo = self.tk.PhotoImage(file=task["screenshot"]["path"])
            self.loaded_layout_id = task["layout_id"]
            self.full_canvas.configure(
                scrollregion=(0, 0, self.photo.width(), self.photo.height())
            )
        self.crop_centre = task["original_image_xy_pixels"]
        self.prompt.configure(
            text=(
                f"Point {self.task_index + 1}/10 | layout={task['layout_id']} | "
                f"{task['kind']} | color={task['marker_color']} | "
                f"location={task['location_description']} | "
                f"world_xz={task['world_xz_blocks']}"
            )
        )
        self._redraw()

    def _crop_bounds(self) -> tuple[int, int, int, int]:
        cx = min(max(self.crop_centre[0], CROP_RADIUS), FRAMEBUFFER[0] - CROP_RADIUS - 1)
        cy = min(max(self.crop_centre[1], CROP_RADIUS), FRAMEBUFFER[1] - CROP_RADIUS - 1)
        self.crop_centre = (cx, cy)
        return (
            cx - CROP_RADIUS,
            cy - CROP_RADIUS,
            cx + CROP_RADIUS + 1,
            cy + CROP_RADIUS + 1,
        )

    def _redraw(self) -> None:
        x0, y0, x1, y1 = self._crop_bounds()
        self.crop_origin = (x0, y0)
        self.full_canvas.delete("all")
        self.full_canvas.create_image(0, 0, image=self.photo, anchor="nw")
        self.full_canvas.create_rectangle(
            x0, y0, x1 - 1, y1 - 1, outline="#ff40ff", width=2
        )
        for index, (selection, task) in enumerate(
            zip(self.selections, self.tasks[: len(self.selections)]), start=1
        ):
            if task["layout_id"] != self.loaded_layout_id:
                continue
            x, y = selection
            colour = "#00ffff" if task["kind"] == "fit_correspondence" else "#ff4040"
            self.full_canvas.create_line(x - 9, y, x + 9, y, fill=colour, width=2)
            self.full_canvas.create_line(x, y - 9, x, y + 9, fill=colour, width=2)
            self.full_canvas.create_text(
                x + 10, y - 10, text=str(index), fill=colour, anchor="sw"
            )
        self.crop_photo = self.photo.copy(from_coords=(x0, y0, x1, y1))
        self.zoom_photo = self.crop_photo.zoom(ZOOM, ZOOM)
        self.zoom_canvas.delete("all")
        self.zoom_canvas.create_image(0, 0, image=self.zoom_photo, anchor="nw")
        self.zoom_canvas.create_line(
            0,
            (CROP_RADIUS + 0.5) * ZOOM,
            (2 * CROP_RADIUS + 1) * ZOOM,
            (CROP_RADIUS + 0.5) * ZOOM,
            fill="#ff40ff",
        )
        self.zoom_canvas.create_line(
            (CROP_RADIUS + 0.5) * ZOOM,
            0,
            (CROP_RADIUS + 0.5) * ZOOM,
            (2 * CROP_RADIUS + 1) * ZOOM,
            fill="#ff40ff",
        )

    def _recenter_from_full(self, event: Any) -> None:
        self.crop_centre = (
            int(self.full_canvas.canvasx(event.x)),
            int(self.full_canvas.canvasy(event.y)),
        )
        self._redraw()

    def _pan(self, dx: int, dy: int) -> None:
        self.crop_centre = (self.crop_centre[0] + dx, self.crop_centre[1] + dy)
        self._redraw()

    def _select_from_zoom(self, event: Any) -> None:
        image_xy = map_zoom_click(self.crop_origin, (event.x, event.y))
        task = self.tasks[self.task_index]
        region = self.regions[self.task_index]
        if not is_click_allowed(region, image_xy):
            message = (
                "Click inside the visible marker top face."
                if task["source_kind"] == "marker"
                else "Click at the visible wall endpoint/ground-contact corner."
            )
            self.messagebox.showerror("Rejected click", message)
            return
        self.selections.append(image_xy)
        self.task_index += 1
        if self.task_index == len(self.tasks):
            self._finish()
        else:
            self._show_current_task()

    def _undo(self, _event: Any = None) -> None:
        if not self.selections:
            return
        self.selections.pop()
        self.task_index = max(0, self.task_index - 1)
        self._show_current_task()

    def _finish(self) -> None:
        if not self.messagebox.askyesno(
            "Confirm targeted repair",
            "All 10 points are selected. Write the additive annotation?",
        ):
            self.task_index -= 1
            self.selections.pop()
            self._show_current_task()
            return
        try:
            document = build_output_document(
                self.verified, self.tasks, self.selections
            )
            verify_preserved_artifacts()
            write_json_create_only(self.output_path, document)
            verify_preserved_artifacts()
        except Exception as error:
            self.messagebox.showerror("Write failed", str(error))
            self.task_index -= 1
            self.selections.pop()
            self._show_current_task()
            return
        self.messagebox.showinfo(
            "Targeted repair complete",
            f"Created:\n{self.output_path}\n\nSHA-256:\n{sha256_file(self.output_path)}",
        )
        self.root.destroy()

    def _cancel(self, _event: Any = None) -> None:
        if self.messagebox.askyesno(
            "Cancel targeted repair", "Cancel without writing an output file?"
        ):
            self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reannotate only layouts 04 and 06 using magnified crops."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="verify immutable inputs and feature click regions without a GUI",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(
            f"Create-only output already exists; refusing to overwrite: {output}"
        )
    verified = verify_inputs()
    tasks = build_tasks(verified)
    regions = build_feature_regions(verified, tasks)
    if args.verify_only:
        print(f"TARGET_LAYOUT_IDS={','.join(TARGET_LAYOUT_IDS)}")
        print("WORLD_COORDINATE_BINDINGS_VALID=True")
        print("COORDINATE_CONVENTION_VALID=True")
        print(f"REANNOTATION_POINT_COUNT={len(tasks)}")
        print("VISIBLE_FEATURE_CLICK_REGIONS_VALID=True")
        print("ORIGINAL_PACKAGE_PRESERVED=True")
        print(f"OUTPUT_PATH={output}")
        return
    RepairWindow(verified, tasks, regions, output).run()


if __name__ == "__main__":
    try:
        main()
    except (RepairInputError, FileExistsError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2) from error
