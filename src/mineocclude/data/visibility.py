"""Visibility and event labels (Person C, Phase C5).

Three layers, each preserved separately so the final label is reproducible
from raw evidence (C5.4) and no channel is silently overwritten:

1. **Geometric visibility (C5.1/C5.2).** The frozen convention:

   - camera origin: the frame's authoritative player eye position from server
     state (``player_x``, ``player_y``, ``player_z``; ``player_y`` is the eye
     Y as logged by the server);
   - target point: the sheep's authoritative world position plus a +0.5 block
     vertical offset to its body center
     (``sheep_x``, ``sheep_y + 0.5``, ``sheep_z``);
   - wall representation: the versioned layout wall as a closed axis-aligned
     block volume ``[min_x, max_x+1] x [min_y, max_y+1] x [min_z, max_z+1]``
     in world coordinates (a block at integer coordinate n occupies
     ``[n, n+1)``);
   - intersection rule: the open camera-to-target segment is tested against
     the wall volume with the exact slab method. Grazing contact within
     ``BOUNDARY_EPS_BLOCKS`` of the surface is ``BOUNDARY``, not forced into
     a binary label;
   - outputs: ``visible`` / ``occluded`` / ``boundary`` / ``invalid`` —
     missing or non-finite geometry is ``invalid``, never coerced.

2. **Empirical detector visibility (C5.3).** Person E's frozen magenta
   detector rows are *imported* through their approved schema and joined
   exactly on frame identity. Person C never reruns the detector with private
   thresholds; detector version/threshold/provenance fields are preserved as
   provided. (An explicitly-identified interim RGB detector exists for
   pre-freeze plumbing only.)

3. **Final flag and events (C5.4/C5.5).**
   ``visible_flag = geometric AND empirical`` for valid binary inputs;
   disagreements and invalid inputs are quarantined by category, never
   flipped. Occlusion/reveal events come from a predeclared consecutive-frame
   stability rule applied to the preserved raw sequence.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

import numpy as np

GEOMETRY_RULE_VERSION = "person-c-geometric-visibility-v0.1"
EVENT_RULE_VERSION = "person-c-event-stability-v0.1"
DEFAULT_STABILITY_FRAMES = 2

BOUNDARY_EPS_BLOCKS = 1e-6

INTERIM_DETECTOR_ID = "interim_rgb_magenta_v0"
SUPPORTED_DETECTION_SCHEMA = "person-e-detection-records-v1.0"


class GeometricStatus(str, Enum):
    VISIBLE = "visible"
    OCCLUDED = "occluded"
    BOUNDARY = "boundary"
    INVALID = "invalid"


# --------------------------------------------------------------------------
# C5.1/C5.2 — geometric visibility
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class WallBox:
    """Closed axis-aligned wall volume in world coordinates (blocks)."""

    min_x: float
    max_x: float
    min_y: float
    max_y: float
    min_z: float
    max_z: float


def layout_wall_box(layout: dict) -> WallBox:
    """Build the wall volume from one frozen layout definition (schema v0.2).

    Block coordinate ``n`` occupies ``[n, n+1)``, so the volume extends one
    block past each declared max coordinate.
    """
    wall = layout["wall"]
    return WallBox(
        min_x=float(wall["min_x"]),
        max_x=float(wall["max_x"]) + 1.0,
        min_y=float(wall["min_y"]),
        max_y=float(wall["max_y"]) + 1.0,
        min_z=float(wall["min_z"]),
        max_z=float(wall["max_z"]) + 1.0,
    )


def _segment_hits_box(p0, p1, box: WallBox, inflate: float) -> bool:
    """Exact slab test: does the segment p0->p1 intersect the inflated box?"""
    lo = (box.min_x - inflate, box.min_y - inflate, box.min_z - inflate)
    hi = (box.max_x + inflate, box.max_y + inflate, box.max_z + inflate)
    t_enter, t_exit = 0.0, 1.0
    for axis in range(3):
        origin, target = p0[axis], p1[axis]
        direction = target - origin
        if abs(direction) < 1e-15:
            if origin < lo[axis] or origin > hi[axis]:
                return False
            continue
        t0 = (lo[axis] - origin) / direction
        t1 = (hi[axis] - origin) / direction
        if t0 > t1:
            t0, t1 = t1, t0
        t_enter = max(t_enter, t0)
        t_exit = min(t_exit, t1)
        if t_enter > t_exit:
            return False
    return True


def geometric_visibility(
    camera_xyz,
    target_xyz,
    wall: WallBox | None,
    boundary_eps: float = BOUNDARY_EPS_BLOCKS,
) -> GeometricStatus:
    """Classify one camera->target sightline against the wall volume.

    ``wall=None`` means the condition has no wall (no-wall control): the
    target is geometrically visible whenever the geometry itself is valid.
    """
    values = tuple(camera_xyz) + tuple(target_xyz)
    if len(values) != 6 or any(
        not isinstance(v, (int, float)) or isinstance(v, bool)
        or not math.isfinite(float(v))
        for v in values
    ):
        return GeometricStatus.INVALID
    if wall is None:
        return GeometricStatus.VISIBLE
    hits_shrunk = _segment_hits_box(camera_xyz, target_xyz, wall, -boundary_eps)
    hits_grown = _segment_hits_box(camera_xyz, target_xyz, wall, boundary_eps)
    if hits_shrunk:
        return GeometricStatus.OCCLUDED
    if hits_grown:
        return GeometricStatus.BOUNDARY
    return GeometricStatus.VISIBLE


def compute_geometric_visibility(frame_map, layout: dict | None):
    """Apply the frozen convention to every frame's authoritative state.

    Adds ``geometric_status`` (the four-way label) and ``geometric_visible``
    (True/False for visible/occluded, ``None`` for boundary/invalid) plus
    ``geometry_rule_version``. Requires the server-state camera pose and
    sheep position columns; rows with missing/non-finite state are
    ``invalid``.

    ``layout=None`` or a layout whose condition has no wall applies the
    no-wall rule. The raw state columns are never modified.
    """
    wall = layout_wall_box(layout) if layout is not None else None
    statuses: list[str] = []
    flags: list[bool | None] = []
    for _, row in frame_map.iterrows():
        target_present = row.get("target_present")
        if target_present is False or (
            "sheep_x" in row and row["sheep_x"] is None
        ):
            # No-object control: nothing to see; label invalid-for-visibility
            # rather than fabricating a hidden sheep.
            statuses.append(GeometricStatus.INVALID.value)
            flags.append(None)
            continue
        camera = (row.get("player_x"), row.get("player_y"), row.get("player_z"))
        sheep_y = row.get("sheep_y")
        target = (
            row.get("sheep_x"),
            (sheep_y + 0.5) if isinstance(sheep_y, (int, float)) else sheep_y,
            row.get("sheep_z"),
        )
        try:
            status = geometric_visibility(camera, target, wall)
        except TypeError:
            status = GeometricStatus.INVALID
        statuses.append(status.value)
        if status is GeometricStatus.VISIBLE:
            flags.append(True)
        elif status is GeometricStatus.OCCLUDED:
            flags.append(False)
        else:
            flags.append(None)
    out = frame_map.copy()
    out["geometric_status"] = statuses
    out["geometric_visible"] = flags
    out["geometry_rule_version"] = GEOMETRY_RULE_VERSION
    return out


# --------------------------------------------------------------------------
# C5.3 — empirical detector visibility
# --------------------------------------------------------------------------

@dataclass
class DetectorImportReport:
    accepted: bool
    problems: list[str]


def import_detector_records(document: dict, frame_map):
    """Join Person E's frozen detector rows one-to-one onto the frame map.

    ``document`` is E's approved detection-records document. Rows join on
    ``(trajectory_id, model_frame_idx)``. Presence, centroid, area, bounding
    box, version, threshold, and rejection metadata are preserved as provided
    under ``detector_``-prefixed columns. Missing or version-incompatible
    detector output is a visible data-quality problem, never silently filled.

    Returns ``(frame_map_with_detector_columns_or_None, report)``.
    """
    problems: list[str] = []
    if document.get("detection_schema_version") != SUPPORTED_DETECTION_SCHEMA:
        problems.append(
            "unsupported detection_schema_version "
            f"{document.get('detection_schema_version')!r}"
        )
        return None, DetectorImportReport(False, problems)
    detector_version = document.get("detector_version")
    if not detector_version:
        problems.append("detector document is missing detector_version")
        return None, DetectorImportReport(False, problems)

    records = document.get("records", [])
    by_key: dict[tuple, dict] = {}
    for record in records:
        if record.get("detector_version") != detector_version:
            problems.append(
                f"record {record.get('detection_id')!r} has a mismatched "
                "detector_version"
            )
        key = (record.get("trajectory_id"), record.get("model_frame_idx"))
        if key in by_key:
            problems.append(f"duplicate detector record for frame {key}")
        by_key[key] = record

    out = frame_map.copy()
    detected: list[bool | None] = []
    kept = {
        "status": [], "centroid_xy": [], "area_pixels": [],
        "bounding_box_xyxy": [], "threshold_version": [],
        "rejection_reason": [], "detection_id": [],
    }
    for _, row in frame_map.iterrows():
        key = (str(row["trajectory_id"]), int(row["model_frame_idx"]))
        record = by_key.get(key)
        if record is None:
            problems.append(f"missing detector record for frame {key}")
            detected.append(None)
            for column in kept:
                kept[column].append(None)
            continue
        status = record.get("status")
        if status == "detected":
            detected.append(True)
        elif status == "not_detected":
            detected.append(False)
        else:
            detected.append(None)
        for column in kept:
            kept[column].append(record.get(column))
    out["empirical_visible"] = detected
    out["detector_id"] = detector_version
    for column, values in kept.items():
        out[f"detector_{column}"] = values
    accepted = not problems
    return (out if accepted else None), DetectorImportReport(accepted, problems)


# Interim C-side detector (pre-freeze plumbing only; identity is explicit). --

@dataclass
class Detection:
    detected: bool
    area_fraction: float
    cx: float  # centroid x in pixels (NaN if none)
    cy: float


def detect_magenta_rgb(rgb: np.ndarray,
                       g_margin: int = 35,
                       min_rb: int = 80,
                       min_area: float = 0.00004) -> Detection:
    """Interim magenta detector. ``rgb`` is HxWx3 uint8.

    Minecraft magenta wool (~RGB 191,76,201) is 'R and B clearly above G'.
    This is deliberately simple and is replaced by E's frozen detector for any
    scientific label; its identity is ``INTERIM_DETECTOR_ID``.
    """
    r = rgb[..., 0].astype(np.int16)
    g = rgb[..., 1].astype(np.int16)
    b = rgb[..., 2].astype(np.int16)
    mask = (r > g + g_margin) & (b > g + g_margin) & (r > min_rb) & (b > min_rb)
    area = float(mask.mean())
    if area < min_area or not mask.any():
        return Detection(False, area, float("nan"), float("nan"))
    ys, xs = np.nonzero(mask)
    return Detection(True, area, float(xs.mean()), float(ys.mean()))


def detect_frame(path: str, **kw) -> Detection:
    from mineocclude.data.fsretry import open_rgb_retry
    return detect_magenta_rgb(open_rgb_retry(path), **kw)


#: Declared source-frame geometry. Centroids are reported in this space, and
#: it is the space Person E's marker/homography contract is written against.
CANONICAL_FRAME_W, CANONICAL_FRAME_H = 640, 360

#: Column holding the canonical 640x360 source frame. The sibling
#: ``frame_abspath`` is the *raw* client framebuffer, which is the native
#: window size (1280x720 on a Retina display) — detecting there silently
#: reports centroids at 2x the canonical scale.
CANONICAL_FRAME_COLUMN = "frame_640_path"


def add_interim_empirical_visibility(frame_map, frame_column=CANONICAL_FRAME_COLUMN,
                                     **kw):
    """Run the interim detector over every frame (plumbing/QA only).

    Reads the canonical 640x360 frames, so ``blob_cx``/``blob_cy`` are in the
    same pixel space the layout/marker contract declares. Centroids outside
    that frame are a hard error rather than a silently exported coordinate.
    """
    if frame_column not in frame_map.columns:
        raise KeyError(
            f"frame map has no {frame_column!r} column; the interim detector "
            "must read canonical 640x360 frames, not the raw framebuffer"
        )
    detections = [detect_frame(p, **kw) for p in frame_map[frame_column]]
    for path, det in zip(frame_map[frame_column], detections):
        if not det.detected:
            continue
        if not (0 <= det.cx < CANONICAL_FRAME_W and 0 <= det.cy < CANONICAL_FRAME_H):
            raise ValueError(
                f"detector centroid ({det.cx:.1f}, {det.cy:.1f}) falls outside "
                f"the declared {CANONICAL_FRAME_W}x{CANONICAL_FRAME_H} source "
                f"frame for {path}; refusing to export out-of-space coordinates"
            )
    out = frame_map.copy()
    out["empirical_visible"] = [d.detected for d in detections]
    out["blob_area"] = [d.area_fraction for d in detections]
    out["blob_cx"] = [d.cx for d in detections]
    out["blob_cy"] = [d.cy for d in detections]
    out["detector_id"] = INTERIM_DETECTOR_ID
    out["detector_frame_space"] = f"{CANONICAL_FRAME_W}x{CANONICAL_FRAME_H}"
    return out


# --------------------------------------------------------------------------
# C5.4 — final flag and disagreement quarantine
# --------------------------------------------------------------------------

QUARANTINE_NONE = "none"
QUARANTINE_GEO_VISIBLE_DET_HIDDEN = "geometry_visible_detector_hidden"
QUARANTINE_GEO_HIDDEN_DET_VISIBLE = "geometry_hidden_detector_visible"
QUARANTINE_INVALID_GEOMETRY = "invalid_geometry"
QUARANTINE_MISSING_DETECTOR = "missing_detector"


def finalize_visibility(frame_map):
    """Compute ``visible_flag = geometric AND empirical`` with quarantine.

    Both raw channels stay untouched; disagreements and invalid inputs get a
    category, never a manual flip. ``visible_flag`` is ``False`` for any
    quarantined row (a frame is treated as observable only when both valid
    channels agree it is), and the quarantine category records why.
    """
    out = frame_map.copy()
    flags: list[bool] = []
    categories: list[str] = []
    for _, row in out.iterrows():
        geo = row.get("geometric_visible")
        emp = row.get("empirical_visible")
        if geo is None or (isinstance(geo, float) and math.isnan(geo)):
            categories.append(QUARANTINE_INVALID_GEOMETRY)
            flags.append(False)
            continue
        if emp is None or (isinstance(emp, float) and math.isnan(emp)):
            categories.append(QUARANTINE_MISSING_DETECTOR)
            flags.append(False)
            continue
        geo_b, emp_b = bool(geo), bool(emp)
        if geo_b and not emp_b:
            categories.append(QUARANTINE_GEO_VISIBLE_DET_HIDDEN)
        elif emp_b and not geo_b:
            categories.append(QUARANTINE_GEO_HIDDEN_DET_VISIBLE)
        else:
            categories.append(QUARANTINE_NONE)
        flags.append(geo_b and emp_b)
    out["visible_flag"] = flags
    out["visibility_quarantine"] = [c != QUARANTINE_NONE for c in categories]
    out["quarantine_category"] = categories
    return out


def disagreement_summary(frame_map) -> dict:
    """Counts by quarantine category, plus per-layout breakdown (C5.4)."""
    counts: dict[str, int] = {}
    by_layout: dict[str, dict[str, int]] = {}
    for _, row in frame_map.iterrows():
        category = row["quarantine_category"]
        counts[category] = counts.get(category, 0) + 1
        layout = str(row.get("layout_id", "unknown"))
        by_layout.setdefault(layout, {})
        by_layout[layout][category] = by_layout[layout].get(category, 0) + 1
    return {"total": counts, "by_layout": by_layout}


# --------------------------------------------------------------------------
# C5.5 — stable occlusion and reveal events
# --------------------------------------------------------------------------

def stabilize(visible: list[bool], stability: int = DEFAULT_STABILITY_FRAMES) -> list[bool]:
    """Apply the consecutive-frame stability rule without deleting frames.

    A state change is registered only once the new value has held for
    ``stability`` consecutive frames; shorter flickers keep the previous
    stable state. The raw sequence is untouched; this returns the stabilized
    view used for event derivation.
    """
    if not visible:
        return []
    stable = [bool(visible[0])]
    state = bool(visible[0])
    n = len(visible)
    index = 1
    while index < n:
        value = bool(visible[index])
        if value != state and all(
            index + k < n and bool(visible[index + k]) == value
            for k in range(stability)
        ):
            state = value
        stable.append(state)
        index += 1
    return stable


def visibility_events(
    visible: list[bool],
    stability: int = DEFAULT_STABILITY_FRAMES,
    dt_seconds: float = 0.05,
) -> dict:
    """Derive occlusion/reveal events from the raw per-frame sequence.

    Applies the predeclared stability rule, then extracts each hidden
    interval as one event: onset index (first stable-hidden frame), reveal
    index (first stable-visible frame after it, or ``None`` when the episode
    ends hidden), and hidden duration. Quarantine facts are explicit:
    ``multiple_events`` and ``missing_reveal`` mark sequences the analysis
    plan treats specially. Raw onset candidates (every raw True->False edge)
    are preserved for audit.
    """
    stable = stabilize(visible, stability)
    events = []
    onset: int | None = None
    for index in range(1, len(stable)):
        if stable[index - 1] and not stable[index]:
            onset = index
        elif not stable[index - 1] and stable[index] and onset is not None:
            events.append({
                "event_id": f"event_{len(events)}",
                "onset_idx": onset,
                "reveal_idx": index,
                "hidden_frames": index - onset,
                "hidden_seconds": (index - onset) * dt_seconds,
            })
            onset = None
    if onset is not None:
        events.append({
            "event_id": f"event_{len(events)}",
            "onset_idx": onset,
            "reveal_idx": None,
            "hidden_frames": len(stable) - onset,
            "hidden_seconds": (len(stable) - onset) * dt_seconds,
        })
    raw_onset_candidates = [
        index
        for index in range(1, len(visible))
        if bool(visible[index - 1]) and not bool(visible[index])
    ]
    return {
        "rule_version": EVENT_RULE_VERSION,
        "stability_frames": stability,
        "events": events,
        "n_events": len(events),
        "multiple_events": len(events) > 1,
        "missing_reveal": any(e["reveal_idx"] is None for e in events),
        "raw_onset_candidates": raw_onset_candidates,
    }
