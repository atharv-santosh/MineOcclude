"""Publish Person E's additive v0.4 marker/layout successor authority.

Person C reported six pre-existing Person E-owned failures in
``tests/data/test_layout_id_resolves.py``: the committed Person E marker sets
(``data/handoff_e/markers_layout_01.json`` .. ``markers_layout_06.json``) are
bound to the superseded ``configs/scenes/layouts.yaml`` geometry while the
accepted production geometry is ``configs/scenes/layouts_v0_4.yaml``.

This script audits that claim against both accepted geometry and Person C's
own C-to-E request, then publishes an *additive* successor authority bound to
the accepted v0.4 geometry SHA-256. Historical v0.3-era marker artifacts are
read only as evidence and are never rewritten.

Marker world coordinates are taken verbatim from the accepted geometry's
declared ``top_face_centre_world_xyz`` values. Canonical corner roles are
*derived* from those coordinates, never chosen to satisfy a test: any layout
whose four markers do not form an unambiguous rectangle about their own
centroid fails closed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parents[1]
if str(REPOSITORY / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY / "src"))

from mineocclude.operations.person_e_66_cell_empirical_visibility import (
    ACCEPTED_GEOMETRY_PATH,
    ACCEPTED_GEOMETRY_SHA256,
    ACCEPTED_GEOMETRY_VERSION,
    C_REQUEST_MANIFEST_PATH,
    C_REQUEST_MANIFEST_SHA256,
    CANONICAL_CAMERA_POSE_IDS,
    CANONICAL_FRAME_HEIGHT,
    CANONICAL_FRAME_WIDTH,
    LAYOUT_IDS,
    PERSON_C_COMMIT,
    EmpiricalVisibilityError,
    git_blob,
    json_bytes,
    load_accepted_geometry,
    load_person_c_request,
    require,
    sha256_bytes,
    sha256_file,
)

AUTHORITY_ID = "person-e-v0-4-marker-layout-authority-v0.1"
AUTHORITY_SCHEMA_VERSION = "person-e-v0-4-marker-layout-authority-v1.0"
OUTPUT_RELATIVE_ROOT = Path(
    "data/handoff_e/person_e_v0_4_marker_layout_authority_v0_1"
)
HISTORICAL_MARKER_PATHS = {
    layout_id: f"data/handoff_e/markers_{layout_id}.json" for layout_id in LAYOUT_IDS
}
SUPERSEDED_GEOMETRY_PATH = "configs/scenes/layouts.yaml"
CANONICAL_MARKER_ROLES = ("north_west", "north_east", "south_east", "south_west")
CORNER_SIGNS = {
    "north_west": (-1, -1),
    "north_east": (1, -1),
    "south_east": (1, 1),
    "south_west": (-1, 1),
}
E_V0_4_IMAGE_POINT_PACKAGE = (
    "data/handoff_e/person_e_v0_4_homography_refit_v0_2/"
    "person_e_attempt_02_image_points_v0_2.json"
)


def derive_corner_roles(markers: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Assign the four canonical corner roles from world geometry alone."""

    require(len(markers) == 4, "A layout must declare exactly four markers.")
    points = {
        marker["role"]: (
            float(marker["top_face_centre_world_xyz"][0]),
            float(marker["top_face_centre_world_xyz"][2]),
        )
        for marker in markers
    }
    require(len(points) == 4, "Layout marker roles are not unique.")
    centre_x = sum(x for x, _ in points.values()) / 4.0
    centre_z = sum(z for _, z in points.values()) / 4.0
    by_role: dict[str, dict[str, Any]] = {}
    for canonical_role, (x_sign, z_sign) in CORNER_SIGNS.items():
        matches = [
            marker
            for marker in markers
            if (points[marker["role"]][0] - centre_x) * x_sign > 0
            and (points[marker["role"]][1] - centre_z) * z_sign > 0
        ]
        require(
            len(matches) == 1,
            f"Canonical role {canonical_role!r} is not uniquely determined by the "
            f"accepted geometry; {len(matches)} markers match its quadrant.",
        )
        by_role[canonical_role] = matches[0]
    require(
        len({id(marker) for marker in by_role.values()}) == 4,
        "Canonical corner assignment reused a marker.",
    )
    return by_role


def marker_document(
    layout: dict[str, Any],
    request_layout: dict[str, Any],
    historical: dict[str, Any],
) -> dict[str, Any]:
    layout_id = layout["layout_id"]
    accepted_markers = layout["markers"]
    request_markers = request_layout["markers"]
    accepted_points = sorted(
        tuple(float(value) for value in marker["top_face_centre_world_xyz"])
        for marker in accepted_markers
    )
    request_points = sorted(
        tuple(float(value) for value in marker["top_face_centre_world_xyz"])
        for marker in request_markers
    )
    require(
        accepted_points == request_points,
        f"{layout_id}: accepted geometry and Person C's request disagree on marker "
        f"world coordinates; geometry={accepted_points}, request={request_points}.",
    )
    require(
        layout["camera"] == request_layout["camera"],
        f"{layout_id}: accepted geometry and Person C's request disagree on the "
        "canonical camera pose.",
    )
    require(
        all(
            marker["world_point_convention"] == "block_top_face_centre"
            for marker in accepted_markers
        ),
        f"{layout_id}: accepted geometry marker convention changed.",
    )
    require(
        request_layout["any_magenta_marker"] is False,
        f"{layout_id}: a magenta marker would collide with the target colour.",
    )
    by_role = derive_corner_roles(accepted_markers)
    correspondences = []
    for canonical_role in CANONICAL_MARKER_ROLES:
        marker = by_role[canonical_role]
        world = [float(value) for value in marker["top_face_centre_world_xyz"]]
        correspondences.append(
            {
                "accepted_geometry_role": marker["role"],
                "block": marker["block"],
                "block_pos_xyz": [int(value) for value in marker["block_pos_xyz"]],
                "image_xy": None,
                "marker_color": marker["color"],
                "marker_id": canonical_role,
                "marker_kind": "non_magenta_geometry_marker",
                "marker_role": canonical_role,
                "world_point_convention": "block_top_face_centre",
                "world_xyz_blocks": world,
                "world_xz_blocks": [world[0], world[2]],
            }
        )
    historical_points = sorted(
        tuple(float(value) for value in marker["world_xz_blocks"])
        for marker in historical["marker_correspondences"]
    )
    successor_points = sorted(
        tuple(marker["world_xz_blocks"]) for marker in correspondences
    )
    return {
        "accepted_geometry_path": ACCEPTED_GEOMETRY_PATH,
        "accepted_geometry_sha256": ACCEPTED_GEOMETRY_SHA256,
        "accepted_geometry_version": ACCEPTED_GEOMETRY_VERSION,
        "authority_id": AUTHORITY_ID,
        "camera": layout["camera"],
        "canonical_camera_pose_id": CANONICAL_CAMERA_POSE_IDS[layout_id],
        "canonical_role_derivation": (
            "canonical corner roles are derived from the accepted top-face-centre "
            "world (x, z) coordinates about their own centroid; no role is chosen "
            "to satisfy a test"
        ),
        "historical_predecessor": {
            "geometry_path": SUPERSEDED_GEOMETRY_PATH,
            "historical_world_xz_blocks": [list(point) for point in historical_points],
            "path": HISTORICAL_MARKER_PATHS[layout_id],
            "preserved_unmodified": True,
            "supersession_reason": (
                "the historical Person E marker set is bound to the superseded "
                "layout geometry and its world coordinates do not match the "
                "accepted v0.4 geometry"
            ),
        },
        "image_coordinate_system": "pixel_center_xy_zero_based",
        "image_height_px": CANONICAL_FRAME_HEIGHT,
        "image_width_px": CANONICAL_FRAME_WIDTH,
        "image_xy_status": (
            "NULL — this authority binds world geometry only; Person E's v0.4 "
            f"image-point annotations live in {E_V0_4_IMAGE_POINT_PACKAGE}"
        ),
        "layout_id": layout_id,
        "marker_correspondences": correspondences,
        "marker_layout_authority_schema_version": AUTHORITY_SCHEMA_VERSION,
        "person_c_commit": PERSON_C_COMMIT,
        "person_c_request_manifest_sha256": C_REQUEST_MANIFEST_SHA256,
        "resolution_id": (
            f"resolution_{CANONICAL_FRAME_WIDTH}x{CANONICAL_FRAME_HEIGHT}_rgb8"
        ),
        "schema_version": "1.0",
        "scientific_use": "permitted",
        "successor_world_xz_blocks": [list(point) for point in successor_points],
        "synthetic": False,
        "world_coordinate_system": "ground_plane_world_xz_blocks_topface_centre",
        "world_point_convention": "block_top_face_centre",
        "world_geometry_matches_accepted_v0_4": True,
        "world_geometry_matched_historical_predecessor": (
            historical_points == successor_points
        ),
    }


def build(repository: Path) -> dict[str, bytes]:
    geometry = load_accepted_geometry(repository)
    request = load_person_c_request(repository)
    geometry_by_layout = {layout["layout_id"]: layout for layout in geometry["layouts"]}
    request_by_layout = {
        layout["layout_id"]: layout for layout in request["layout_marker_authority"]
    }
    require(
        sorted(request_by_layout) == list(LAYOUT_IDS),
        "Person C's request does not bind layout_01 through layout_06.",
    )
    payloads: dict[str, bytes] = {}
    documents: dict[str, dict[str, Any]] = {}
    drifted: list[str] = []
    for layout_id in LAYOUT_IDS:
        historical = json.loads(
            git_blob(
                repository, PERSON_C_COMMIT, HISTORICAL_MARKER_PATHS[layout_id]
            ).decode("utf-8")
        )
        require(
            historical["layout_id"] == layout_id,
            f"Historical marker set for {layout_id} claims a different layout.",
        )
        document = marker_document(
            geometry_by_layout[layout_id], request_by_layout[layout_id], historical
        )
        if not document["world_geometry_matched_historical_predecessor"]:
            drifted.append(layout_id)
        documents[layout_id] = document
        payloads[f"markers_{layout_id}.json"] = json_bytes(document)
    require(
        len(drifted) == len(LAYOUT_IDS),
        "The reported marker/layout drift was not reproduced for all six layouts; "
        f"drifted={drifted}.",
    )
    manifest = {
        "accepted_geometry_path": ACCEPTED_GEOMETRY_PATH,
        "accepted_geometry_sha256": ACCEPTED_GEOMETRY_SHA256,
        "accepted_geometry_version": ACCEPTED_GEOMETRY_VERSION,
        "additive_successor": True,
        "authority_id": AUTHORITY_ID,
        "cross_verification": {
            "accepted_geometry_and_person_c_request_agree": True,
            "independent_sources": [ACCEPTED_GEOMETRY_PATH, C_REQUEST_MANIFEST_PATH],
        },
        "drift_audit": {
            "confirmed": True,
            "drifted_layout_ids": sorted(drifted),
            "failing_test": "tests/data/test_layout_id_resolves.py",
            "failing_test_case": "TestPersonEHandoff::test_marker_file_matches_contract_geometry",
            "finding": (
                "every historical Person E marker set is bound to the superseded "
                "layout geometry; none of the six agrees with the accepted v0.4 "
                "top-face-centre world coordinates"
            ),
            "historical_artifacts_rewritten": False,
            "reported_by": "person_c",
            "superseded_geometry_path": SUPERSEDED_GEOMETRY_PATH,
        },
        "historical_predecessor_invalidated": False,
        "layout_count": len(LAYOUT_IDS),
        "layout_ids": list(LAYOUT_IDS),
        "marker_layout_authority_schema_version": AUTHORITY_SCHEMA_VERSION,
        "marker_world_coordinates_changed_to_satisfy_a_test": False,
        "owner_role": "person_e",
        "person_c_commit": PERSON_C_COMMIT,
        "person_c_request_manifest_sha256": C_REQUEST_MANIFEST_SHA256,
        "per_layout": [
            {
                "canonical_camera_pose_id": documents[layout_id][
                    "canonical_camera_pose_id"
                ],
                "historical_world_xz_blocks": documents[layout_id][
                    "historical_predecessor"
                ]["historical_world_xz_blocks"],
                "layout_id": layout_id,
                "marker_file": f"markers_{layout_id}.json",
                "successor_world_xz_blocks": documents[layout_id][
                    "successor_world_xz_blocks"
                ],
                "world_geometry_matches_accepted_v0_4": True,
            }
            for layout_id in LAYOUT_IDS
        ],
        "schema_id": f"{AUTHORITY_ID}-manifest",
        "schema_version": "1.0",
        "supersedes_for_new_evidence": sorted(HISTORICAL_MARKER_PATHS.values()),
        "world_point_convention": "block_top_face_centre",
    }
    payloads["marker_layout_authority_manifest.json"] = json_bytes(manifest)
    inventory = {
        "authority_id": AUTHORITY_ID,
        "files": {
            name: sha256_bytes(payload) for name, payload in sorted(payloads.items())
        },
        "package_file_count": len(payloads) + 1,
        "schema_id": f"{AUTHORITY_ID}-sha256-inventory",
        "schema_version": "1.0",
    }
    payloads["sha256_inventory.json"] = json_bytes(inventory)
    return payloads


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=str(REPOSITORY))
    parser.add_argument(
        "--check",
        action="store_true",
        help="Rebuild in memory and compare against the published package.",
    )
    arguments = parser.parse_args(argv)
    repository = Path(arguments.repository).resolve()
    output = repository / OUTPUT_RELATIVE_ROOT
    try:
        payloads = build(repository)
    except EmpiricalVisibilityError as error:
        print(f"FAIL_CLOSED: {error}", file=sys.stderr)
        return 2
    if arguments.check:
        existing = {
            path.name: path.read_bytes()
            for path in sorted(output.glob("*.json"))
        }
        if existing != payloads:
            print("FAIL_CLOSED: published marker authority differs.", file=sys.stderr)
            return 2
        print(f"OK {len(payloads)} files match {OUTPUT_RELATIVE_ROOT.as_posix()}")
        return 0
    output.mkdir(parents=True, exist_ok=True)
    for name, payload in sorted(payloads.items()):
        (output / name).write_bytes(payload)
    manifest_sha = sha256_file(output / "marker_layout_authority_manifest.json")
    print(f"wrote {len(payloads)} files to {OUTPUT_RELATIVE_ROOT.as_posix()}")
    print(f"marker_layout_authority_manifest.json sha256={manifest_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
