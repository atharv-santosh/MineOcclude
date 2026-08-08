"""Every layout id and marker set in a *current* artifact must resolve against
the accepted geometry.

These guard the defects found in the C0-C6 audit:

* the mod's zero-based ``layout_00``-``layout_05`` ids leaking into committed
  artifacts, where they either do not resolve at all (``layout_00``) or
  resolve to the *wrong* geometry (each legacy id is one short of its
  contract meaning);
* marker sets drifting away from the layout geometry they claim.

Current authority
-----------------
The accepted production geometry is ``configs/scenes/layouts_v0_4.yaml``
(``person-c-layout-config-v0.4``), which declares ``block_pos_xyz`` and
``top_face_centre_world_xyz`` as *distinct* literal fields under
``no_compatibility_transforms``. The current marker/layout authority is Person
E's additive v0.4 successor, read at Person E's pinned commit. Marker world
coordinates are compared against the accepted geometry's declared
top-face-centre field directly: no offset is synthesised and no expected
coordinate is hardcoded.

Historical evidence
-------------------
``configs/scenes/layouts.yaml`` (``person-c-layout-config-v0.3``) and the
historical ``data/handoff_e/markers_layout_*.json`` sets are preserved
unmodified as immutable evidence. They are deliberately *not* re-derived or
re-validated against the accepted geometry: v0.4 supersedes v0.3 for new
evidence, the historical sets are heterogeneous (four agree with v0.3 under
the top-face-centre convention, two came from a later recapture), and
rewriting them to satisfy a test would destroy evidence. They are asserted
only to still exist, to still declare the superseded version, and to be
recorded as superseded rather than used as current authority.

Legacy C6 pilot bundles remain exempt from id resolution: they keep their
as-captured ids as historical evidence, per
``docs/decisions/person_c_layout_id_supersession_v0_1.md``.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

#: Accepted production geometry (current authority).
ACCEPTED_LAYOUTS = REPO / "configs" / "scenes" / "layouts_v0_4.yaml"
ACCEPTED_GEOMETRY_SHA256 = (
    "34495d650d6a8c62b00a916796c90389b48f80d8f20a23eac93207758e993f5d"
)
ACCEPTED_GEOMETRY_VERSION = "person-c-layout-config-v0.4"

#: Superseded predecessor, preserved as immutable historical evidence.
HISTORICAL_LAYOUTS = REPO / "configs" / "scenes" / "layouts.yaml"
HISTORICAL_GEOMETRY_SHA256 = (
    "5a39d2dcae44d72f07b0e645dcc3e64ea6178ef79f1c9e3f12bff11f857f82cb"
)
HISTORICAL_GEOMETRY_VERSION = "person-c-layout-config-v0.3"

HANDOFF_E = REPO / "data" / "handoff_e"

#: Person E's additive v0.4 marker/layout successor authority, pinned.
PERSON_E_COMMIT = "fec27d08b4629afa07c7858598e94778dc6e7bef"
E_MARKER_AUTHORITY_REL = (
    "data/handoff_e/person_e_v0_4_marker_layout_authority_v0_1"
)
E_MARKER_AUTHORITY_SHA256 = (
    "14a12db4092e05e8c41057df210eec11f07a78f593a149595a12eba45fda82d8"
)

LAYOUT_IDS = [f"layout_{i:02d}" for i in range(1, 7)]

#: Fields that name a *historical* capture rather than a contract layout.
#: These legitimately retain legacy ids and must not be resolved.
PROVENANCE_FIELDS = {
    "trajectory_id", "source_trajectory_id", "source_artifact_id",
    "capture_command", "capture_package", "capture_provenance",
    "legacy_layout_id", "scope", "note", "producer_note",
}


def accepted_layouts() -> dict:
    """The current accepted geometry, keyed by layout id."""
    document = json.loads(ACCEPTED_LAYOUTS.read_text(encoding="utf-8"))
    return {entry["layout_id"]: entry for entry in document["layouts"]}


def historical_layouts() -> dict:
    document = json.loads(HISTORICAL_LAYOUTS.read_text(encoding="utf-8"))
    return {entry["layout_id"]: entry for entry in document["layouts"]}


def accepted_marker_xz(layout_id: str) -> list[tuple[float, float]]:
    """Declared top-face-centre marker world xz, read literally.

    The accepted geometry publishes ``top_face_centre_world_xyz`` as its own
    field, so no offset is derived from ``block_pos_xyz`` here.
    """
    return sorted(
        (float(marker["top_face_centre_world_xyz"][0]),
         float(marker["top_face_centre_world_xyz"][2]))
        for marker in accepted_layouts()[layout_id]["markers"]
    )


def git_show(rel_path: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{PERSON_E_COMMIT}:{rel_path}"],
        capture_output=True, timeout=120,
    )
    if result.returncode != 0:
        pytest.skip(
            f"Person E commit {PERSON_E_COMMIT[:12]} is not available locally"
        )
    return result.stdout


def e_successor_manifest() -> dict:
    payload = git_show(
        f"{E_MARKER_AUTHORITY_REL}/marker_layout_authority_manifest.json"
    )
    assert hashlib.sha256(payload).hexdigest() == E_MARKER_AUTHORITY_SHA256
    return json.loads(payload)


def e_successor_markers(layout_id: str) -> dict:
    return json.loads(
        git_show(f"{E_MARKER_AUTHORITY_REL}/markers_{layout_id}.json")
    )


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


class TestAcceptedContract:
    def test_accepted_geometry_identity_is_pinned(self):
        digest = hashlib.sha256(ACCEPTED_LAYOUTS.read_bytes()).hexdigest()
        assert digest == ACCEPTED_GEOMETRY_SHA256
        document = json.loads(ACCEPTED_LAYOUTS.read_text(encoding="utf-8"))
        assert document["config_version"] == ACCEPTED_GEOMETRY_VERSION

    def test_contract_ids_are_one_based_and_complete(self):
        assert sorted(accepted_layouts()) == LAYOUT_IDS

    def test_legacy_zero_based_id_is_not_in_the_contract(self):
        # The specific id that silently resolved to nothing for all of C6.
        assert "layout_00" not in accepted_layouts()

    def test_accepted_geometry_forbids_compatibility_transforms(self):
        document = json.loads(ACCEPTED_LAYOUTS.read_text(encoding="utf-8"))
        assert document["no_compatibility_transforms"] is True
        assert "no hidden offsets" in document["coordinate_policy"]

    @pytest.mark.parametrize("layout_id", LAYOUT_IDS)
    def test_accepted_geometry_declares_both_marker_conventions(self, layout_id):
        """BlockPos and top-face-centre must be separate literal fields."""
        for marker in accepted_layouts()[layout_id]["markers"]:
            assert len(marker["block_pos_xyz"]) == 3
            assert len(marker["top_face_centre_world_xyz"]) == 3
            assert marker["world_point_convention"] == "block_top_face_centre"


class TestHistoricalEvidencePreserved:
    """The superseded v0.3 evidence must survive the v0.4 migration intact."""

    def test_historical_v03_geometry_is_unmodified(self):
        digest = hashlib.sha256(HISTORICAL_LAYOUTS.read_bytes()).hexdigest()
        assert digest == HISTORICAL_GEOMETRY_SHA256
        document = json.loads(HISTORICAL_LAYOUTS.read_text(encoding="utf-8"))
        assert document["config_version"] == HISTORICAL_GEOMETRY_VERSION

    def test_accepted_geometry_records_the_supersession(self):
        document = json.loads(ACCEPTED_LAYOUTS.read_text(encoding="utf-8"))
        assert document["supersedes_for_new_evidence"] == (
            HISTORICAL_GEOMETRY_VERSION
        )
        # Superseding must not retroactively invalidate historical evidence.
        assert document["historical_predecessor_invalidated"] is False

    @pytest.mark.parametrize("layout_id", LAYOUT_IDS)
    def test_historical_marker_sets_still_exist(self, layout_id):
        path = HANDOFF_E / f"markers_{layout_id}.json"
        assert path.exists(), f"historical marker evidence for {layout_id} was removed"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["layout_id"] == layout_id

    def test_historical_marker_sets_are_recorded_as_superseded(self):
        """They are historical evidence, not the current marker authority."""
        manifest = e_successor_manifest()
        superseded = set(manifest["supersedes_for_new_evidence"])
        for layout_id in LAYOUT_IDS:
            assert (
                f"data/handoff_e/markers_{layout_id}.json" in superseded
            ), f"historical {layout_id} marker set is not declared superseded"
        assert manifest["historical_predecessor_invalidated"] is False


@pytest.mark.skipif(not HANDOFF_E.is_dir(), reason="handoff not present")
class TestLayoutIdResolution:
    @pytest.mark.parametrize("path", handoff_e_files(), ids=lambda p: p.name)
    def test_every_layout_id_resolves(self, path):
        contract = accepted_layouts()
        unresolved = [
            (where, value)
            for where, value in iter_layout_ids(
                json.loads(path.read_text(encoding="utf-8"))
            )
            if value not in contract
        ]
        assert not unresolved, f"{path.name} has unresolvable layout ids: {unresolved}"


class TestPersonEV04MarkerSuccessorAuthority:
    """The current marker authority must match accepted v0.4 exactly."""

    def test_successor_authority_identity_is_pinned(self):
        manifest = e_successor_manifest()
        assert manifest["accepted_geometry_sha256"] == ACCEPTED_GEOMETRY_SHA256
        assert manifest["accepted_geometry_version"] == ACCEPTED_GEOMETRY_VERSION
        assert manifest["world_point_convention"] == "block_top_face_centre"
        assert manifest["additive_successor"] is True
        assert sorted(manifest["layout_ids"]) == LAYOUT_IDS
        # The successor must not have been produced by editing coordinates to
        # make a test pass.
        assert manifest["marker_world_coordinates_changed_to_satisfy_a_test"] is False

    @pytest.mark.parametrize("layout_id", LAYOUT_IDS)
    def test_marker_file_matches_accepted_geometry(self, layout_id):
        data = e_successor_markers(layout_id)
        assert data["layout_id"] == layout_id
        markers = data["marker_correspondences"]
        assert all(
            marker["world_point_convention"] == "block_top_face_centre"
            for marker in markers
        )
        got = sorted(tuple(marker["world_xz_blocks"]) for marker in markers)
        want = accepted_marker_xz(layout_id)
        assert got == want, (
            f"markers_{layout_id}.json world coordinates do not match the "
            f"accepted {ACCEPTED_GEOMETRY_VERSION} top-face-centre geometry; "
            f"got {got}, accepted geometry declares {want}"
        )

    @pytest.mark.parametrize("layout_id", LAYOUT_IDS)
    def test_marker_count_and_non_magenta_restriction(self, layout_id):
        data = e_successor_markers(layout_id)
        markers = data["marker_correspondences"]
        assert len(markers) == 4
        # Magenta is reserved for the target so the frozen detector is unambiguous.
        assert all(marker["marker_color"] != "magenta" for marker in markers)

    @pytest.mark.parametrize("layout_id", LAYOUT_IDS)
    def test_camera_matches_accepted_geometry(self, layout_id):
        data = e_successor_markers(layout_id)
        assert data["camera"] == accepted_layouts()[layout_id]["camera"]

    @pytest.mark.parametrize("layout_id", LAYOUT_IDS)
    def test_canonical_pose_id_is_stable_across_geometry_versions(self, layout_id):
        """The pose identity is derived, and v0.3 already used the same id."""
        expected = f"{layout_id}_canonical_pose_v1"
        assert e_successor_markers(layout_id)["canonical_camera_pose_id"] == expected
        # v0.4 dropped the canonical_pose block; v0.3 still carries the id, so
        # the identity is shown to be stable rather than newly invented here.
        assert historical_layouts()[layout_id]["canonical_pose"]["pose_id"] == expected

    @pytest.mark.parametrize("layout_id", LAYOUT_IDS)
    def test_declared_image_space_is_the_canonical_frame(self, layout_id):
        from mineocclude.data.visibility import CANONICAL_FRAME_H, CANONICAL_FRAME_W

        data = e_successor_markers(layout_id)
        assert data["image_width_px"] == CANONICAL_FRAME_W
        assert data["image_height_px"] == CANONICAL_FRAME_H
        projection = json.loads(
            ACCEPTED_LAYOUTS.read_text(encoding="utf-8")
        )["shared_capture_projection"]
        assert projection["canonical_derivative_width_pixels"] == CANONICAL_FRAME_W
        assert projection["canonical_derivative_height_pixels"] == CANONICAL_FRAME_H
