"""C layout v0.2 to E homography v1.1 compatibility evidence."""

from __future__ import annotations

import copy
import unittest
from pathlib import Path

from mineocclude.data.layout_contract import load_layout_config, validate_layout_config
from mineocclude.vision.homography import HomographyError, validate_homography_fixture


ROOT = Path(__file__).resolve().parents[2]


def compatible_fixture() -> dict:
    config = load_layout_config(ROOT / "configs" / "scenes" / "layouts.yaml")
    assert validate_layout_config(config).accepted
    layout = config["layouts"][0]
    # Deliberately rotated screen placement: world north_west is bottom-right.
    image_by_id = {
        "m1_blue": [500.0, 300.0],
        "m2_yellow": [500.0, 60.0],
        "m3_lime": [100.0, 300.0],
        "m4_white": [100.0, 60.0],
    }
    markers = [
        {
            "marker_id": marker["marker_id"],
            "marker_role": marker["marker_role"],
            "marker_kind": "non_magenta_geometry_marker",
            "image_xy": image_by_id[marker["marker_id"]],
            "world_xz_blocks": [
                marker["world_blocks"]["x"],
                marker["world_blocks"]["z"],
            ],
        }
        for marker in layout["markers"]
    ]
    return {
        "schema_version": "1.0",
        "homography_fixture_schema_version": "person-e-homography-fixture-v1.1",
        "fixture_id": "synthetic_c_e_layout_01_v1",
        "synthetic": True,
        "scientific_use": "forbidden",
        "layout_id": layout["layout_id"],
        "canonical_camera_pose_id": layout["canonical_pose"]["pose_id"],
        "resolution_id": "synthetic_640x360",
        "image_width_px": 640,
        "image_height_px": 360,
        "image_coordinate_system": "pixel_center_xy_zero_based",
        "world_coordinate_system": "ground_plane_world_xz_blocks",
        "marker_correspondences": markers,
        "expected_probe": {
            "image_xy": [300.0, 180.0],
            "world_xz_blocks": [19.5, 9.5],
            "absolute_tolerance_blocks": 1e-9,
        },
    }


class TestCEMarkerCompatibility(unittest.TestCase):
    def test_stable_ids_and_roles_fit_independently_of_order(self) -> None:
        document = compatible_fixture()
        original = copy.deepcopy(document)
        first = validate_homography_fixture(document)
        shuffled = copy.deepcopy(document)
        shuffled["marker_correspondences"] = list(reversed(shuffled["marker_correspondences"]))
        second = validate_homography_fixture(shuffled)
        self.assertEqual(first.fit_hash, second.fit_hash)
        self.assertEqual(document, original)

    def test_ambiguous_or_geometry_inconsistent_role_mapping_fails(self) -> None:
        for mutation in ("duplicate_id", "duplicate_role", "unknown_role", "wrong_geometry"):
            with self.subTest(mutation=mutation):
                document = compatible_fixture()
                markers = document["marker_correspondences"]
                if mutation == "duplicate_id":
                    markers[1]["marker_id"] = markers[0]["marker_id"]
                elif mutation == "duplicate_role":
                    markers[1]["marker_role"] = markers[0]["marker_role"]
                elif mutation == "unknown_role":
                    markers[1]["marker_role"] = "screen_top_right"
                else:
                    markers[0]["marker_role"], markers[1]["marker_role"] = (
                        markers[1]["marker_role"], markers[0]["marker_role"]
                    )
                with self.assertRaises(HomographyError):
                    validate_homography_fixture(document)


if __name__ == "__main__":
    unittest.main()
