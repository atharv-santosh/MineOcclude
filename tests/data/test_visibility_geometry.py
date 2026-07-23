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


class TestLayoutShadowAudit:
    """AUDIT (C1.3 evidence gap, discovered by the C5.2 implementation).

    At the canonical camera pose, the true perspective occlusion shadow at
    lane depth covers essentially the entire lane: layouts 01, 02, and 05
    have ZERO geometrically visible lane positions, and layouts 03, 04, and
    06 are visible only in the immediate neighborhood of one lane endpoint.
    The declared ``shadow`` bounds in layouts v0.2 are therefore inconsistent
    with the actual geometry, and the required visible->hidden->visible arc
    cannot occur. See
    ``docs/reports/person_c_layout_geometry_audit.md``; the layouts need a
    reviewed v0.3 geometry revision before C1.5/C6 collection. These
    assertions pin the measured facts so any silent geometry change is
    caught.
    """

    FULLY_OCCLUDED = {"layout_01", "layout_02", "layout_05"}
    ENDPOINT_ONLY = {"layout_03": "min", "layout_04": "min", "layout_06": "min"}

    @pytest.mark.parametrize("layout", load_layouts(),
                             ids=lambda l: l["layout_id"])
    def test_measured_lane_visibility(self, layout):
        lane = layout["lane"]
        box = layout_wall_box(layout)
        camera = camera_of(layout)
        lane_min = geometric_visibility(
            camera, sheep_at(layout, lane["min_scalar_blocks"]), box
        )
        lane_max = geometric_visibility(
            camera, sheep_at(layout, lane["max_scalar_blocks"]), box
        )
        layout_id = layout["layout_id"]
        if layout_id in self.FULLY_OCCLUDED:
            assert lane_min is GeometricStatus.OCCLUDED
            assert lane_max is GeometricStatus.OCCLUDED
        else:
            assert layout_id in self.ENDPOINT_ONLY
            assert lane_min is GeometricStatus.VISIBLE
            assert lane_max is GeometricStatus.OCCLUDED


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
