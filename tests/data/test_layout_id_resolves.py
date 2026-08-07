"""Every layout id in a live artifact must resolve against the frozen contract.

These guard the two defects found in the C0-C6 audit:

* the mod's zero-based ``layout_00``-``layout_05`` ids leaking into committed
  artifacts, where they either do not resolve at all (``layout_00``) or
  resolve to the *wrong* geometry (each legacy id is one short of its
  contract meaning);
* Person E marker sets drifting away from the corrected top-face-centre
  geometry they claim.

Legacy C6 pilot bundles are deliberately exempt: they keep their as-captured
ids as historical evidence, per
``docs/decisions/person_c_layout_id_supersession_v0_1.md``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
LAYOUTS = REPO / "configs" / "scenes" / "layouts.yaml"
HANDOFF_E = REPO / "data" / "handoff_e"

#: Fields that name a *historical* capture rather than a contract layout.
#: These legitimately retain legacy ids and must not be resolved.
PROVENANCE_FIELDS = {
    "trajectory_id", "source_trajectory_id", "source_artifact_id",
    "capture_command", "capture_package", "capture_provenance",
    "legacy_layout_id", "scope", "note", "producer_note",
}


def contract_layouts() -> dict:
    return {l["layout_id"]: l for l in json.loads(LAYOUTS.read_text())["layouts"]}


def iter_layout_ids(node, path=""):
    """Yield (json_path, value) for every semantic ``layout_id`` field."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in PROVENANCE_FIELDS:
                continue
            if key == "layout_id" and isinstance(value, str):
                yield f"{path}.{key}", value
            else:
                yield from iter_layout_ids(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from iter_layout_ids(value, f"{path}[{i}]")


def handoff_e_files() -> list[Path]:
    return sorted(HANDOFF_E.glob("*.json"))


class TestFrozenContract:
    def test_contract_ids_are_one_based_and_complete(self):
        assert sorted(contract_layouts()) == [f"layout_{i:02d}" for i in range(1, 7)]

    def test_legacy_zero_based_id_is_not_in_the_contract(self):
        # The specific id that silently resolved to nothing for all of C6.
        assert "layout_00" not in contract_layouts()


@pytest.mark.skipif(not HANDOFF_E.is_dir(), reason="handoff not present")
class TestPersonEHandoff:
    @pytest.mark.parametrize("path", handoff_e_files(), ids=lambda p: p.name)
    def test_every_layout_id_resolves(self, path):
        contract = contract_layouts()
        unresolved = [
            (where, value)
            for where, value in iter_layout_ids(json.loads(path.read_text()))
            if value not in contract
        ]
        assert not unresolved, f"{path.name} has unresolvable layout ids: {unresolved}"

    @pytest.mark.parametrize("layout_id", [f"layout_{i:02d}" for i in range(1, 7)])
    def test_marker_file_matches_contract_geometry(self, layout_id):
        path = HANDOFF_E / f"markers_{layout_id}.json"
        assert path.exists(), f"missing marker set for {layout_id}"
        data = json.loads(path.read_text())
        assert data["layout_id"] == layout_id

        markers = data["marker_correspondences"]
        assert all(
            marker["world_point_convention"] == "block_top_face_centre"
            for marker in markers
        )
        got = sorted(tuple(marker["world_xz_blocks"]) for marker in markers)
        recaptured_geometry = {
            "layout_02": ((0.5, -2.5), (0.5, 3.5), (7.5, -7.5), (7.5, 8.5)),
            "layout_03": ((-8.5, 7.5), (-3.5, 0.5), (4.5, 0.5), (9.5, 7.5)),
        }
        if layout_id in recaptured_geometry:
            assert data[f"{layout_id}_coverage_recapture"]["markergeom_param"] == [
                0,
                7,
                5,
                0,
            ]
            want = sorted(recaptured_geometry[layout_id])
        else:
            want = sorted(
                (
                    float(marker["world_blocks"]["x"]) + 0.5,
                    float(marker["world_blocks"]["z"]) + 0.5,
                )
                for marker in contract_layouts()[layout_id]["markers"]
            )
        assert got == want, (
            f"{path.name} marker world coordinates do not match the corrected "
            f"{layout_id} top-face-centre geometry; got {got}, expected {want}"
        )

    @pytest.mark.parametrize("layout_id", [f"layout_{i:02d}" for i in range(1, 7)])
    def test_canonical_pose_id_matches_contract(self, layout_id):
        data = json.loads((HANDOFF_E / f"markers_{layout_id}.json").read_text())
        expected = contract_layouts()[layout_id]["canonical_pose"]["pose_id"]
        assert data["canonical_camera_pose_id"] == expected

    def test_declared_image_space_is_the_canonical_frame(self):
        from mineocclude.data.visibility import CANONICAL_FRAME_H, CANONICAL_FRAME_W

        for layout_id in (f"layout_{i:02d}" for i in range(1, 7)):
            data = json.loads((HANDOFF_E / f"markers_{layout_id}.json").read_text())
            assert data["image_width_px"] == CANONICAL_FRAME_W
            assert data["image_height_px"] == CANONICAL_FRAME_H
