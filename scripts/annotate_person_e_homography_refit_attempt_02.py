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
ANNOTATION_METHOD = "person-e-tkinter-manual-point-selector-v0.1"
OUTPUT_SCHEMA_VERSION = "person-e-v0.4-image-point-annotations-attempt-02-v0.1"


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
    }


def build_tasks(verified: dict[str, Any]) -> list[dict[str, Any]]:
    annotation_layouts = _layouts_by_id(
        verified["annotation_template"], "annotation template"
    )
    validation_layouts = _layouts_by_id(
        verified["validation_template"], "validation template"
    )
    screenshots = {row["layout_id"]: row for row in verified["screenshots"]}
    tasks: list[dict[str, Any]] = []
    for layout_id in EXPECTED_LAYOUT_IDS:
        for point in annotation_layouts[layout_id]["fit_correspondences"]:
            tasks.append(
                {
                    "layout_id": layout_id,
                    "kind": "fit_marker",
                    "point_id": point["marker_id"],
                    "feature": (
                        f"{point['color']} marker top-face centre "
                        f"({point['marker_id']})"
                    ),
                    "world_xz_blocks": point["world_xz_blocks"],
                    "source_point": dict(point),
                    "screenshot": screenshots[layout_id],
                }
            )
        for point in validation_layouts[layout_id]["validation_points"]:
            tasks.append(
                {
                    "layout_id": layout_id,
                    "kind": "independent_validation",
                    "point_id": point["point_id"],
                    "feature": point["feature"],
                    "world_xz_blocks": point["world_xz_blocks"],
                    "source_point": dict(point),
                    "screenshot": screenshots[layout_id],
                }
            )
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
    if len(tasks) != 48 or len(selections) != len(tasks):
        raise AnnotationInputError("All 48 fit and validation points are required.")
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
        record["image_xy_pixels"] = [x, y]
        record["selection_status"] = "operator_selected"
        destination = (
            "fit_correspondences"
            if task["kind"] == "fit_marker"
            else "independent_validation_points"
        )
        layout[destination].append(record)

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
            "fit_point_definition": "rendered_marker_top_face_centre",
            "validation_point_definitions_source": verified[
                "validation_template_record"
            ],
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
                f"Point {self.task_index + 1}/48 | {task['layout_id']} | "
                f"{task['kind']} | {task['feature']} | "
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
            colour = "#00ffff" if task["kind"] == "fit_marker" else "#ff4040"
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
            "All 48 points are selected. Write the immutable create-only output?",
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
    if len(tasks) != 48:
        raise AnnotationInputError(f"Expected 48 annotation tasks, got {len(tasks)}.")
    if args.verify_only:
        print("C_HANDOFF_VALID=True")
        print("SIX_SCREENSHOTS_VALID=True")
        print("SIX_GEOMETRY_RECEIPTS_VALID=True")
        print(f"ANNOTATION_TASK_COUNT={len(tasks)}")
        return
    AnnotationWindow(verified, output_path).run()


if __name__ == "__main__":
    try:
        main()
    except (AnnotationInputError, FileExistsError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2) from error
