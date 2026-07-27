"""C5.2 geometric-visibility tests: hand fixtures plus all six frozen layouts.

The convention under test is frozen in ``mineocclude.data.visibility``:
camera eye -> sheep center segment against the closed wall block volume,
with explicit visible/occluded/boundary/invalid outputs.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

import mineocclude.contracts  # noqa: F401  (pre-existing import-order cycle)
from mineocclude.data.visibility import (
    GEOMETRY_RULE_VERSION,
    GeometricStatus,
    WallBox,
    compute_geometric_visibility,
    geometric_visibility,
    layout_wall_box,
)

LAYOUTS_PATH = Path(__file__).resolve().parents[2] / "configs" / "scenes" / "layouts.yaml"


def load_layouts():
    with open(LAYOUTS_PATH, encoding="utf-8") as handle:
        return json.load(handle)["layouts"]


def sheep_at(layout, scalar):
    lane = layout["lane"]
    y = lane["y_blocks"] + 0.5
    if lane["axis"] == "x":
        return (scalar, y, lane["fixed_coordinate_blocks"])
    return (lane["fixed_coordinate_blocks"], y, scalar)


def camera_of(layout):
    position = layout["canonical_pose"]["position_blocks"]
    return (position["x"], position["y"], position["z"])


UNIT_BOX = WallBox(0.0, 1.0, 0.0, 3.0, 5.0, 6.0)


class TestHandFixtures:
    def test_clear_segment_is_visible(self):
        assert geometric_visibility(
            (0.5, 1.5, 0.0), (0.5, 1.5, 4.0), UNIT_BOX
        ) is GeometricStatus.VISIBLE

    def test_segment_through_box_is_occluded(self):
        assert geometric_visibility(
            (0.5, 1.5, 0.0), (0.5, 1.5, 10.0), UNIT_BOX
        ) is GeometricStatus.OCCLUDED

    def test_segment_over_box_top_is_visible(self):
        assert geometric_visibility(
            (0.5, 5.0, 0.0), (0.5, 5.0, 10.0), UNIT_BOX
        ) is GeometricStatus.VISIBLE

    def test_grazing_segment_is_boundary(self):
        # The segment lies exactly in the plane of the box top (y = 3.0).
        assert geometric_visibility(
            (0.5, 3.0, 0.0), (0.5, 3.0, 10.0), UNIT_BOX
        ) is GeometricStatus.BOUNDARY

    def test_non_finite_state_is_invalid(self):
        assert geometric_visibility(
            (float("nan"), 1.0, 0.0), (0.5, 1.5, 10.0), UNIT_BOX
        ) is GeometricStatus.INVALID
        assert geometric_visibility(
            (0.5, 1.0, 0.0), (None, 1.5, 10.0), UNIT_BOX
        ) is GeometricStatus.INVALID

    def test_no_wall_control_is_visible_when_geometry_valid(self):
        assert geometric_visibility(
            (0.5, 1.5, 0.0), (0.5, 1.5, 10.0), None
        ) is GeometricStatus.VISIBLE
        assert geometric_visibility(
            (float("inf"), 1.5, 0.0), (0.5, 1.5, 10.0), None
        ) is GeometricStatus.INVALID


class TestAllSixLayouts:
    """Layout-specific boundary tests across both wall axes and motion signs."""

    @pytest.mark.parametrize("layout", load_layouts(),
                             ids=lambda l: l["layout_id"])
    def test_wall_center_is_occluded(self, layout):
        wall = layout["wall"]
        wall_axis = layout["lane"]["axis"]
        center = 0.5 * (wall[f"min_{wall_axis}"] + wall[f"max_{wall_axis}"])
        status = geometric_visibility(
            camera_of(layout), sheep_at(layout, center), layout_wall_box(layout)
        )
        assert status is GeometricStatus.OCCLUDED

    @pytest.mark.parametrize("layout", load_layouts(),
                             ids=lambda l: l["layout_id"])
    def test_point_between_camera_and_wall_is_visible(self, layout):
        camera = camera_of(layout)
        wall_box = layout_wall_box(layout)
        # A short probe from the camera toward the scene never reaches the
        # wall volume, so it must be visible.
        wall = layout["wall"]
        wall_center = (
            0.5 * (wall["min_x"] + wall["max_x"] + 1),
            0.5 * (wall["min_y"] + wall["max_y"] + 1),
            0.5 * (wall["min_z"] + wall["max_z"] + 1),
        )
        probe = tuple(
            c + 0.15 * (w - c) for c, w in zip(camera, wall_center)
        )
        status = geometric_visibility(camera, probe, wall_box)
        assert status is GeometricStatus.VISIBLE

    @pytest.mark.parametrize("layout", load_layouts(),
                             ids=lambda l: l["layout_id"])
    def test_target_above_wall_top_is_visible(self, layout):
        wall = layout["wall"]
        wall_axis = layout["lane"]["axis"]
        center = 0.5 * (wall[f"min_{wall_axis}"] + wall[f"max_{wall_axis}"])
        x, _, z = sheep_at(layout, center)
        high_target = (x, wall["max_y"] + 3.0, z)
        status = geometric_visibility(
            camera_of(layout), high_target, layout_wall_box(layout)
        )
        assert status is GeometricStatus.VISIBLE


class TestLayoutArcValidity:
    """v0.3 geometry validity (supersedes the v0.2 shadow audit).

    layouts v0.2 were geometrically defective — at the canonical pose the
    occlusion shadow covered essentially the whole lane, so the required
    visible->hidden->visible arc was impossible (see
    ``docs/reports/person_c_layout_geometry_audit.md``). v0.3 exports the
    mod's real working geometry (validated by accepted runtime captures).
    These assertions now pin the *good* facts: every layout must produce the
    arc — visible lane positions on BOTH ends and an occluded middle — so a
    silent regression back to broken geometry is caught.

    The camera EYE is the pose feet + 1.62 (ServerPlayerEntity eye height),
    matching how the mod computes visibility.
    """

    @pytest.mark.parametrize("layout", load_layouts(),
                             ids=lambda l: l["layout_id"])
    def test_layout_produces_occlusion_arc(self, layout):
        import numpy as np
        lane = layout["lane"]
        box = layout_wall_box(layout)
        pos = layout["canonical_pose"]["position_blocks"]
        eye = (pos["x"], pos["y"] + 1.62, pos["z"])

        def sheep_scalar(scalar):
            return sheep_at(layout, scalar)

        span = np.arange(lane["min_scalar_blocks"],
                         lane["max_scalar_blocks"] + 0.01, 0.25)
        statuses = [geometric_visibility(eye, sheep_scalar(float(s)), box).value
                    for s in span]
        n_visible = statuses.count("visible")
        n_occluded = statuses.count("occluded")
        mid = statuses[len(statuses) // 2]
        # arc: substantial visible span, an occluded region, occluded middle
        assert n_visible >= 5, (layout["layout_id"], "too few visible lane positions")
        assert n_occluded >= 5, (layout["layout_id"], "no occlusion")
        assert mid == "occluded", (layout["layout_id"], "middle not occluded")


def test_compute_geometric_visibility_dataframe():
    layout = load_layouts()[0]
    camera = camera_of(layout)
    wall = layout["wall"]
    center = 0.5 * (wall["min_x"] + wall["max_x"])
    occluded_target = sheep_at(layout, center)
    frame_map = pd.DataFrame([
        {   # occluded row
            "player_x": camera[0], "player_y": camera[1], "player_z": camera[2],
            "sheep_x": occluded_target[0], "sheep_y": occluded_target[1] - 0.5,
            "sheep_z": occluded_target[2], "target_present": True,
        },
        {   # invalid row (missing sheep state)
            "player_x": camera[0], "player_y": camera[1], "player_z": camera[2],
            "sheep_x": float("nan"), "sheep_y": float("nan"),
            "sheep_z": float("nan"), "target_present": True,
        },
        {   # no-object control row
            "player_x": camera[0], "player_y": camera[1], "player_z": camera[2],
            "sheep_x": float("nan"), "sheep_y": float("nan"),
            "sheep_z": float("nan"), "target_present": False,
        },
    ])
    out = compute_geometric_visibility(frame_map, layout)
    assert list(out["geometric_status"]) == ["occluded", "invalid", "invalid"]
    assert list(out["geometric_visible"]) == [False, None, None]
    assert set(out["geometry_rule_version"]) == {GEOMETRY_RULE_VERSION}
    # Raw state columns are untouched.
    assert out["sheep_x"].iloc[0] == frame_map["sheep_x"].iloc[0]
