"""Counterfactual rendered-extent classification (authority 4.5, 5.1).

The scientific primitive is **ported, not rewritten**. The exact A-prime v0.3
module is vendored byte-identically as
:mod:`mineocclude.experiment_iii._aprime_extent_geometry` and re-exported here;
:func:`verify_port_blob` reproduces its git blob SHA-1 so a drifted copy is loud.

What this module adds is Experiment III-native and small:

* :func:`counterfactual_wall` builds the occluder **with ``present=True`` for
  every condition, L0 included** (authority 4.5). The ported
  :func:`classify_extent` returns ``EXTENT_FULLY_VISIBLE`` immediately when
  ``present is False``; an L0 counterfactual built with ``present=False`` yields
  zero eligible L0 rows and silently destroys the pairing. That is the single
  most dangerous mistake available here, so the flag is not a parameter of the
  public entry point at all.
* :func:`classify_counterfactual_extent` is material-independent: it takes a
  world-x and nothing else about the condition, so L0..L4 classify identically.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Mapping, Sequence

from mineocclude.experiment_iii._aprime_extent_geometry import (
    EXTENT_SAMPLES_PER_AXIS,
    REFERENCE_MARCH_SAMPLES,
    SHEEP_FUR_MODEL_CONSTANTS,
    TARGET_EXTENT_HALF_BLOCKS,
    ExtentClass,
    ReferenceAgreementError,
    WallGeometry,
    classify_extent,
    derive_target_extent_half_blocks,
    extent_sample_points,
    segment_hits_wall,
    verify_reference_agreement,
)
from mineocclude.experiment_iii.authority import (
    APRIME_PORT_BLOBS,
    APRIME_PORT_COMMIT,
    CAMERA_EYE,
    LAYOUT_01,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.schema import ExtentClassName

__all__ = [
    "EXTENT_SAMPLES_PER_AXIS",
    "REFERENCE_MARCH_SAMPLES",
    "SHEEP_FUR_MODEL_CONSTANTS",
    "TARGET_EXTENT_HALF_BLOCKS",
    "APRIME_EXTENT_SOURCE_PATH",
    "ExtentClass",
    "ReferenceAgreementError",
    "WallGeometry",
    "classify_extent",
    "derive_target_extent_half_blocks",
    "extent_sample_points",
    "segment_hits_wall",
    "verify_reference_agreement",
    "counterfactual_wall",
    "target_centre",
    "classify_counterfactual_extent",
    "counterfactual_extent_classes",
    "fully_occluded_runs",
    "first_fully_occluded_run",
    "verify_port_blob",
    "aprime_port_receipt",
]

#: The vendored copy, checked against the bound blob SHA-1.
APRIME_EXTENT_SOURCE_PATH = (
    Path(__file__).with_name("_aprime_extent_geometry.py")
)
_APRIME_EXTENT_LOGICAL_PATH = "src/mineocclude/prospective/extent_geometry.py"


def counterfactual_wall(layout: Mapping[str, object] = LAYOUT_01) -> WallGeometry:
    """The material-independent counterfactual occluder (authority 4.5).

    ``present=True`` unconditionally. There is deliberately no way to ask this
    function for an absent wall: the counterfactual occluder is the *original*
    one-layer footprint, and it exists for every condition regardless of what
    blocks are physically standing.

    The as-built geometry is **computed** from the layout by the ported
    ``from_layout`` (floor/ceil exactly as ``ArenaBuilder`` places whole blocks),
    never read from a hard-coded interval, so a layout change fails closed.
    """
    return WallGeometry.from_layout(
        wall_axis=str(layout["wall_axis"]),
        wall_seg_min=float(layout["wall_seg_min"]),
        wall_seg_max=float(layout["wall_seg_max"]),
        wall_ortho_const=float(layout["wall_ortho_const"]),
        wall_ortho_offset=float(layout["wall_ortho_offset"]),
        lane_y=float(layout["lane_y"]),
        present=True,
    )


def target_centre(
    world_x: float, layout: Mapping[str, object] = LAYOUT_01
) -> tuple[float, float, float]:
    """The target centre the mod itself tests: ``(x, laneY + 0.5, laneOrtho)``.

    Matches ``EpisodeManager``'s ``sheep.sheepY() + 0.5`` call site and its
    integer-lane occlusion shadow, so the Python engine and the mod agree on the
    same point semantics.
    """
    lane_y = float(layout["lane_y"])
    lane_ortho = float(layout["wall_ortho_const"])
    if str(layout["wall_axis"]) == "X":
        return (float(world_x), lane_y + 0.5, lane_ortho)
    return (lane_ortho, lane_y + 0.5, float(world_x))


def classify_counterfactual_extent(
    world_x: float,
    *,
    layout: Mapping[str, object] = LAYOUT_01,
    camera: Sequence[float] = CAMERA_EYE,
    wall: WallGeometry | None = None,
) -> ExtentClassName:
    """Counterfactual extent class of one lane position, condition-independent.

    Takes no condition and no material: authority 4.4 makes
    ``counterfactual_extent_class`` the only geometric selector input, and it is
    computed against the unchanged original wall volume regardless of condition.
    """
    occluder = counterfactual_wall(layout) if wall is None else wall
    if not occluder.present:
        raise ExperimentIIIError(
            "FIR_COUNTERFACTUAL_PRESENCE_ERROR",
            "the counterfactual occluder must be present for every condition, "
            "L0 included; an absent counterfactual collapses L0 eligibility to "
            "zero rows and silently breaks the pairing",
        )
    ported = classify_extent(camera, target_centre(world_x, layout), occluder)
    return ExtentClassName[ported.name]


def counterfactual_extent_classes(
    positions: Sequence[float],
    *,
    layout: Mapping[str, object] = LAYOUT_01,
    camera: Sequence[float] = CAMERA_EYE,
    wall: WallGeometry | None = None,
) -> list[ExtentClassName]:
    occluder = counterfactual_wall(layout) if wall is None else wall
    return [
        classify_counterfactual_extent(
            position, layout=layout, camera=camera, wall=occluder
        )
        for position in positions
    ]


def fully_occluded_runs(
    classes: Sequence[ExtentClassName],
) -> list[tuple[int, int]]:
    """Maximal ``[start, stop)`` runs of ``EXTENT_FULLY_OCCLUDED`` rows."""
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(classes):
        if value is ExtentClassName.EXTENT_FULLY_OCCLUDED:
            if start is None:
                start = index
        elif start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, len(classes)))
    return runs


def first_fully_occluded_run(
    classes: Sequence[ExtentClassName], length: int
) -> tuple[int, int] | None:
    """First run long enough to contain ``length`` consecutive occluded rows.

    Returns the ``[start, start + length)`` window in ascending model-frame
    order — authority 2.5's "first 19 consecutive eligible rows", with no phase
    offset and no outcome-derived adjustment.
    """
    if length < 1:
        raise ExperimentIIIError(
            "TARGET_ROW_MISMATCH", "target window length must be positive"
        )
    for start, stop in fully_occluded_runs(classes):
        if stop - start >= length:
            return (start, start + length)
    return None


# --------------------------------------------------------------------------
# Port provenance (authority 5.1)
# --------------------------------------------------------------------------

def _git_blob_sha1(payload: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(payload) + payload).hexdigest()


def verify_port_blob() -> dict[str, str]:
    """Reproduce the bound blob SHA-1 of the vendored A-prime module.

    Retrieval failure or drift is ``APRIME_PORT_SOURCE_UNAVAILABLE``: the port
    must be the historical object, not a reconstruction.
    """
    if not APRIME_EXTENT_SOURCE_PATH.is_file():
        raise ExperimentIIIError(
            "APRIME_PORT_SOURCE_UNAVAILABLE",
            f"vendored A-prime extent module is absent: {APRIME_EXTENT_SOURCE_PATH}",
        )
    payload = APRIME_EXTENT_SOURCE_PATH.read_bytes()
    observed = _git_blob_sha1(payload)
    expected = APRIME_PORT_BLOBS[_APRIME_EXTENT_LOGICAL_PATH]
    if observed != expected:
        raise ExperimentIIIError(
            "APRIME_PORT_SOURCE_UNAVAILABLE",
            f"ported extent module drifted from the bound blob: expected "
            f"{expected}, observed {observed}",
        )
    return {
        "source_commit": APRIME_PORT_COMMIT,
        "source_path": _APRIME_EXTENT_LOGICAL_PATH,
        "blob_sha1": observed,
        "bytes": str(len(payload)),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def aprime_port_receipt() -> dict[str, object]:
    """The ``aprime_port_receipt.json`` body for the extent primitive."""
    blob = verify_port_blob()
    wall = counterfactual_wall()
    return {
        "schema_version": "mineocclude-experiment-iii-aprime-port-receipt-v1",
        "authority_section": "5.1",
        "ported_items": [
            "SHEEP_FUR_MODEL_CONSTANTS",
            "TARGET_EXTENT_HALF_BLOCKS",
            "derive_target_extent_half_blocks",
            "WallGeometry",
            "segment_hits_wall",
            "classify_extent",
            "extent_sample_points",
            "verify_reference_agreement",
        ],
        "provenance": blob,
        "target_extent_half_blocks": TARGET_EXTENT_HALF_BLOCKS,
        "target_extent_recomputed": derive_target_extent_half_blocks(),
        "extent_samples_per_axis": EXTENT_SAMPLES_PER_AXIS,
        "reference_march_samples": REFERENCE_MARCH_SAMPLES,
        "counterfactual_present_for_all_conditions_including_L0": True,
        "as_built_wall": {
            "wall_axis": wall.wall_axis,
            "wall_ortho": wall.wall_ortho,
            "wall_axis_min": wall.wall_axis_min,
            "wall_axis_max": wall.wall_axis_max,
            "wall_y_min": wall.wall_y_min,
            "wall_y_max": wall.wall_y_max,
            "half": wall.half,
            "present": wall.present,
        },
        "camera_eye": list(CAMERA_EYE),
        "layout": dict(LAYOUT_01),
    }
