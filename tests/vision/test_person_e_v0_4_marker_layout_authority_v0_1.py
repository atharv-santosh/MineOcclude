"""Person E's additive v0.4 marker/layout successor authority.

These are the repaired Person E-owned layout-resolution tests. Person C
reported six pre-existing failures in ``tests/data/test_layout_id_resolves.py``
(``TestPersonEHandoff::test_marker_file_matches_contract_geometry`` for
``layout_01`` .. ``layout_06``): the historical Person E marker sets are bound
to the superseded ``configs/scenes/layouts.yaml`` geometry while the accepted
production geometry is ``configs/scenes/layouts_v0_4.yaml``.

The six cases below are the same six checks, re-anchored on the accepted v0.4
geometry and on the additive successor authority. The historical artifacts are
never rewritten; they are read only as evidence that the drift is real.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from mineocclude.operations.person_e_66_cell_empirical_visibility import (
    ACCEPTED_GEOMETRY_PATH,
    ACCEPTED_GEOMETRY_SHA256,
    ACCEPTED_GEOMETRY_VERSION,
    CANONICAL_CAMERA_POSE_IDS,
    CANONICAL_FRAME_HEIGHT,
    CANONICAL_FRAME_WIDTH,
    LAYOUT_IDS,
    PERSON_C_COMMIT,
    git_blob,
    load_accepted_geometry,
    load_person_c_request,
    sha256_bytes,
)

ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = ROOT / "data/handoff_e/person_e_v0_4_marker_layout_authority_v0_1"
HISTORICAL_MARKER_PATHS = {
    layout_id: f"data/handoff_e/markers_{layout_id}.json" for layout_id in LAYOUT_IDS
}
CANONICAL_MARKER_ROLES = frozenset(
    {"north_west", "north_east", "south_east", "south_west"}
)


def marker_document(layout_id: str) -> dict:
    return json.loads((AUTHORITY / f"markers_{layout_id}.json").read_text("utf-8"))


def accepted_world_xz(layout: dict) -> list[tuple[float, float]]:
    return sorted(
        (
            float(marker["top_face_centre_world_xyz"][0]),
            float(marker["top_face_centre_world_xyz"][2]),
        )
        for marker in layout["markers"]
    )


class TestSuccessorAuthorityIsPublished(unittest.TestCase):
    def test_package_is_complete_and_hash_consistent(self) -> None:
        inventory = json.loads(
            (AUTHORITY / "sha256_inventory.json").read_text("utf-8")
        )
        published = {path.name for path in AUTHORITY.glob("*.json")}
        self.assertEqual(
            published, set(inventory["files"]) | {"sha256_inventory.json"}
        )
        self.assertEqual(inventory["package_file_count"], len(published))
        for name, expected in inventory["files"].items():
            with self.subTest(file=name):
                self.assertEqual(
                    sha256_bytes((AUTHORITY / name).read_bytes()), expected
                )

    def test_manifest_binds_the_accepted_v0_4_geometry(self) -> None:
        manifest = json.loads(
            (AUTHORITY / "marker_layout_authority_manifest.json").read_text("utf-8")
        )
        self.assertEqual(manifest["accepted_geometry_sha256"], ACCEPTED_GEOMETRY_SHA256)
        self.assertEqual(manifest["accepted_geometry_path"], ACCEPTED_GEOMETRY_PATH)
        self.assertEqual(
            manifest["accepted_geometry_version"], ACCEPTED_GEOMETRY_VERSION
        )
        self.assertEqual(manifest["layout_ids"], list(LAYOUT_IDS))
        self.assertTrue(manifest["additive_successor"])
        self.assertFalse(manifest["historical_predecessor_invalidated"])
        self.assertFalse(manifest["drift_audit"]["historical_artifacts_rewritten"])
        self.assertFalse(
            manifest["marker_world_coordinates_changed_to_satisfy_a_test"]
        )

    def test_drift_audit_reproduces_all_six_reported_failures(self) -> None:
        manifest = json.loads(
            (AUTHORITY / "marker_layout_authority_manifest.json").read_text("utf-8")
        )
        self.assertTrue(manifest["drift_audit"]["confirmed"])
        self.assertEqual(
            manifest["drift_audit"]["drifted_layout_ids"], list(LAYOUT_IDS)
        )
        for layout_id in LAYOUT_IDS:
            with self.subTest(layout_id=layout_id):
                historical = json.loads(
                    git_blob(
                        ROOT, PERSON_C_COMMIT, HISTORICAL_MARKER_PATHS[layout_id]
                    ).decode("utf-8")
                )
                historical_points = sorted(
                    tuple(float(value) for value in marker["world_xz_blocks"])
                    for marker in historical["marker_correspondences"]
                )
                successor_points = sorted(
                    tuple(marker["world_xz_blocks"])
                    for marker in marker_document(layout_id)["marker_correspondences"]
                )
                self.assertNotEqual(historical_points, successor_points)


class TestLayoutResolution(unittest.TestCase):
    """The six repaired Person E-owned layout-resolution cases."""

    def test_every_layout_id_resolves_against_the_accepted_geometry(self) -> None:
        accepted = {
            layout["layout_id"] for layout in load_accepted_geometry(ROOT)["layouts"]
        }
        self.assertEqual(accepted, set(LAYOUT_IDS))
        self.assertNotIn("layout_00", accepted)
        for path in sorted(AUTHORITY.glob("*.json")):
            document = json.loads(path.read_text("utf-8"))
            for layout_id in _iter_layout_ids(document):
                with self.subTest(file=path.name, layout_id=layout_id):
                    self.assertIn(layout_id, accepted)

    def test_marker_file_matches_accepted_v0_4_geometry(self) -> None:
        geometry = {
            layout["layout_id"]: layout
            for layout in load_accepted_geometry(ROOT)["layouts"]
        }
        for layout_id in LAYOUT_IDS:
            with self.subTest(layout_id=layout_id):
                document = marker_document(layout_id)
                self.assertEqual(document["layout_id"], layout_id)
                self.assertEqual(
                    document["accepted_geometry_sha256"], ACCEPTED_GEOMETRY_SHA256
                )
                got = sorted(
                    tuple(marker["world_xz_blocks"])
                    for marker in document["marker_correspondences"]
                )
                self.assertEqual(got, accepted_world_xz(geometry[layout_id]))

    def test_marker_world_coordinates_agree_with_person_c_request(self) -> None:
        request = {
            layout["layout_id"]: layout
            for layout in load_person_c_request(ROOT)["layout_marker_authority"]
        }
        for layout_id in LAYOUT_IDS:
            with self.subTest(layout_id=layout_id):
                got = sorted(
                    tuple(marker["world_xz_blocks"])
                    for marker in marker_document(layout_id)["marker_correspondences"]
                )
                self.assertEqual(got, accepted_world_xz(request[layout_id]))

    def test_canonical_pose_id_matches_the_person_e_consumer_contract(self) -> None:
        for layout_id in LAYOUT_IDS:
            with self.subTest(layout_id=layout_id):
                self.assertEqual(
                    marker_document(layout_id)["canonical_camera_pose_id"],
                    CANONICAL_CAMERA_POSE_IDS[layout_id],
                )

    def test_camera_pose_matches_the_accepted_geometry(self) -> None:
        geometry = {
            layout["layout_id"]: layout
            for layout in load_accepted_geometry(ROOT)["layouts"]
        }
        for layout_id in LAYOUT_IDS:
            with self.subTest(layout_id=layout_id):
                self.assertEqual(
                    marker_document(layout_id)["camera"],
                    geometry[layout_id]["camera"],
                )

    def test_declared_image_space_is_the_canonical_frame(self) -> None:
        for layout_id in LAYOUT_IDS:
            with self.subTest(layout_id=layout_id):
                document = marker_document(layout_id)
                self.assertEqual(document["image_width_px"], CANONICAL_FRAME_WIDTH)
                self.assertEqual(document["image_height_px"], CANONICAL_FRAME_HEIGHT)
                self.assertEqual(
                    document["image_coordinate_system"], "pixel_center_xy_zero_based"
                )


class TestMarkerCorrespondences(unittest.TestCase):
    def test_roles_ids_and_colors_are_unique_and_canonical(self) -> None:
        for layout_id in LAYOUT_IDS:
            with self.subTest(layout_id=layout_id):
                markers = marker_document(layout_id)["marker_correspondences"]
                self.assertEqual(len(markers), 4)
                self.assertEqual(
                    {marker["marker_role"] for marker in markers},
                    CANONICAL_MARKER_ROLES,
                )
                self.assertEqual(
                    {marker["marker_id"] for marker in markers},
                    CANONICAL_MARKER_ROLES,
                )
                self.assertEqual(
                    len({marker["marker_color"] for marker in markers}), 4
                )
                for marker in markers:
                    self.assertEqual(
                        marker["marker_kind"], "non_magenta_geometry_marker"
                    )
                    self.assertNotIn("magenta", marker["marker_color"])
                    self.assertNotIn("magenta", marker["block"])
                    self.assertEqual(
                        marker["world_point_convention"], "block_top_face_centre"
                    )

    def test_corner_roles_are_geometrically_consistent(self) -> None:
        signs = {
            "north_west": (-1, -1),
            "north_east": (1, -1),
            "south_east": (1, 1),
            "south_west": (-1, 1),
        }
        for layout_id in LAYOUT_IDS:
            with self.subTest(layout_id=layout_id):
                markers = marker_document(layout_id)["marker_correspondences"]
                centre_x = sum(m["world_xz_blocks"][0] for m in markers) / 4.0
                centre_z = sum(m["world_xz_blocks"][1] for m in markers) / 4.0
                for marker in markers:
                    x_sign, z_sign = signs[marker["marker_role"]]
                    x, z = marker["world_xz_blocks"]
                    self.assertGreater((x - centre_x) * x_sign, 0)
                    self.assertGreater((z - centre_z) * z_sign, 0)

    def test_world_xz_is_the_top_face_centre_of_the_declared_block(self) -> None:
        for layout_id in LAYOUT_IDS:
            with self.subTest(layout_id=layout_id):
                for marker in marker_document(layout_id)["marker_correspondences"]:
                    block_x, _, block_z = marker["block_pos_xyz"]
                    self.assertEqual(
                        marker["world_xz_blocks"],
                        [block_x + 0.5, block_z + 0.5],
                    )


def _iter_layout_ids(node, provenance=frozenset({"historical_predecessor"})):
    if isinstance(node, dict):
        for key, value in node.items():
            if key in provenance:
                continue
            if key == "layout_id" and isinstance(value, str):
                yield value
            else:
                yield from _iter_layout_ids(value, provenance)
    elif isinstance(node, list):
        for value in node:
            yield from _iter_layout_ids(value, provenance)


if __name__ == "__main__":
    unittest.main()
