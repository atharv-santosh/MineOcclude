"""Person B independent validation and co-sign of Person C's coordinate frames.

Person C owns the world coordinate system, the wall-parallel scalar axis, its
origin, direction, sign convention, and the wall/lane/shadow bounds.  Person B
owns only one question: *is that frame the thing Person B's frozen oracle
contract means by a signed wall-parallel position, in Person B's units?*

This module answers that question from evidence rather than from Person C's
summary.  It re-reads the accepted geometry, rebuilds every derived quantity,
and replays Person B's own projection against real captured state before it
will set ``adapter_signoff.person_b``.  Nothing here inspects a scientific
result, and nothing here can change a Person C byte: the C-side artifacts are
read through exact ``commit:path`` bindings and verified against their declared
digests.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from mineocclude.analysis.config import (
    ANALYSIS_CONFIG_VERSION,
    hash_core_analysis_config,
    load_core_analysis_config,
)
from mineocclude.analysis.coordinates import (
    COORDINATE_FRAME_SCHEMA_VERSION,
    CoordinateContractError,
    coordinate_frame_hash,
    validate_coordinate_frame,
)
from mineocclude.analysis.manifests import is_hex_digest, seal_artifact

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

COSIGN_SCHEMA_VERSION = "person-b-66-cell-coordinate-frame-cosign-v0.1"
COSIGN_PACKAGE_DIRECTORY = (
    "docs/status/person_b_66_cell_coordinate_frame_cosign_v0_1"
)
COSIGNED_FRAME_DIRECTORY = "data/person_b/c6a_c_intake/coordinate_frames"
DECISION_DATE = "2026-08-07"

# --------------------------------------------------------------------------
# Bound Person C authority (exact commit / path / SHA-256)
# --------------------------------------------------------------------------
PERSON_C_COMMIT = "aceb319c47af6d494d6e5314049b12ab1a0a002f"
PERSON_C_AUTHORITY_DIRECTORY = "docs/status/person_c_66_cell_capture_authority_v0_1"
PERSON_C_COORDINATE_FRAME_AUTHORITY_PATH = (
    f"{PERSON_C_AUTHORITY_DIRECTORY}/coordinate_frame_authority.json"
)
PERSON_C_COORDINATE_FRAME_AUTHORITY_SHA256 = (
    "1aed95e444f82ab4caf9935c039e87df3aafbf38830bf763a646aba3d62b509b"
)
PERSON_C_CAPTURE_PACKAGE_MANIFEST_PATH = (
    f"{PERSON_C_AUTHORITY_DIRECTORY}/capture_package_manifest.json"
)
PERSON_C_CAPTURE_PACKAGE_MANIFEST_SHA256 = (
    "ca6ef6bd0a6ee144731ff3e6f470f767a2c1a82e8b46aef9fb5e458efb814f56"
)
ACCEPTED_GEOMETRY_PATH = "configs/scenes/layouts_v0_4.yaml"
ACCEPTED_GEOMETRY_SHA256 = (
    "34495d650d6a8c62b00a916796c90389b48f80d8f20a23eac93207758e993f5d"
)
ACCEPTED_GEOMETRY_VERSION = "person-c-layout-config-v0.4"

EXPECTED_LAYOUT_IDS = (
    "layout_01",
    "layout_02",
    "layout_03",
    "layout_04",
    "layout_05",
    "layout_06",
)
EXPECTED_LAYOUT_COUNT = len(EXPECTED_LAYOUT_IDS)
EXPECTED_TRAJECTORY_COUNT = 66

AXIS_INDEX = {"x": 0, "y": 1, "z": 2}
AXIS_UNIT_VECTOR = {
    "x": (1.0, 0.0, 0.0),
    "y": (0.0, 1.0, 0.0),
    "z": (0.0, 0.0, 1.0),
}
PROJECTION_EXACT_TOLERANCE_BLOCKS = 0.0
UNIT_NORM_TOLERANCE = 1e-9

CODE_COMPONENTS = (
    "src/mineocclude/analysis/coordinate_frame_cosign_v0_1.py",
    "src/mineocclude/analysis/coordinates.py",
    "src/mineocclude/analysis/config.py",
    "src/mineocclude/analysis/manifests.py",
)


class CoordinateCosignError(ValueError):
    """Raised when Person B cannot co-sign a coordinate frame."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CoordinateCosignError(message)


# --------------------------------------------------------------------------
# Exact Git-object binding
# --------------------------------------------------------------------------
def _git_bytes(repository_root: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repository_root), *arguments],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise CoordinateCosignError(
            f"git {' '.join(arguments)} failed: {detail or 'unknown error'}"
        )
    return result.stdout


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_bound_blob(
    path: str,
    *,
    expected_sha256: str | None = None,
    commit: str = PERSON_C_COMMIT,
    repository_root: Path | None = None,
) -> bytes:
    """Read one Person C blob by exact ``commit:path`` and verify its bytes."""

    require(
        isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) is not None,
        f"bound commit must be a full Git SHA-1: {commit!r}",
    )
    require(
        isinstance(path, str)
        and bool(path)
        and "\x00" not in path
        and not path.startswith("/")
        and ".." not in Path(path).parts,
        f"invalid bound repository path: {path!r}",
    )
    root = REPOSITORY_ROOT if repository_root is None else Path(repository_root)
    require(
        _git_bytes(root, "cat-file", "-t", commit).decode("utf-8").strip() == "commit",
        f"bound authority {commit} is not a commit object",
    )
    payload = _git_bytes(root, "cat-file", "blob", f"{commit}:{path}")
    if expected_sha256 is not None:
        require(
            is_hex_digest(expected_sha256, 64),
            f"expected_sha256 must be SHA-256 for {path}",
        )
        actual = sha256_bytes(payload)
        require(
            actual == expected_sha256.lower(),
            f"bound blob {commit}:{path} hashes to {actual}, "
            f"expected {expected_sha256.lower()}",
        )
    return payload


def _strict_json(payload: bytes, *, label: str) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise CoordinateCosignError(f"{label} repeats JSON key {key!r}.")
            result[key] = value
        return result

    try:
        return json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda value: (_ for _ in ()).throw(
                CoordinateCosignError(f"{label} contains non-finite constant {value!r}.")
            ),
        )
    except CoordinateCosignError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CoordinateCosignError(
            f"{label} is not strict UTF-8 JSON: {error}"
        ) from error


def derive_cosign_code_sha(repository_root: Path | None = None) -> str:
    """Hash every code component that determines this co-sign."""

    root = REPOSITORY_ROOT if repository_root is None else Path(repository_root)
    digest = hashlib.sha1()
    for label in CODE_COMPONENTS:
        try:
            payload = (root / label).read_bytes()
        except OSError as error:  # pragma: no cover - defensive
            raise CoordinateCosignError(
                f"Could not read co-sign code component {label}: {error}"
            ) from error
        digest.update(label.encode("utf-8"))
        digest.update(b"\0")
        digest.update(payload.replace(b"\r\n", b"\n"))
        digest.update(b"\0")
    return digest.hexdigest()


# --------------------------------------------------------------------------
# Person C intake
# --------------------------------------------------------------------------
def load_person_c_authority(repository_root: Path | None = None) -> dict[str, Any]:
    """Load the C-side coordinate-frame authority and its six layout frames."""

    payload = read_bound_blob(
        PERSON_C_COORDINATE_FRAME_AUTHORITY_PATH,
        expected_sha256=PERSON_C_COORDINATE_FRAME_AUTHORITY_SHA256,
        repository_root=repository_root,
    )
    authority = _strict_json(payload, label="Person C coordinate-frame authority")
    require(
        isinstance(authority, Mapping),
        "Person C coordinate-frame authority root must be an object.",
    )
    require(
        authority.get("PERSON_C_COORDINATE_FRAME_SIGNED") is True,
        "Person C has not signed the coordinate frames.",
    )
    require(
        authority.get("person_c_signed_person_b_side") is False,
        "Person C must not sign Person B's side of the adapter.",
    )
    require(
        authority.get("accepted_geometry_sha256") == ACCEPTED_GEOMETRY_SHA256
        and authority.get("accepted_geometry_version") == ACCEPTED_GEOMETRY_VERSION,
        "Person C authority is not bound to the accepted geometry identity.",
    )
    require(
        authority.get("coordinate_frame_schema_version")
        == COORDINATE_FRAME_SCHEMA_VERSION,
        "Person C authority does not use Person B's coordinate-frame schema.",
    )
    require(
        authority.get("layout_count") == EXPECTED_LAYOUT_COUNT,
        f"Person C authority must declare {EXPECTED_LAYOUT_COUNT} layouts.",
    )
    frames = authority.get("frames")
    require(
        isinstance(frames, list) and len(frames) == EXPECTED_LAYOUT_COUNT,
        f"Person C authority must carry {EXPECTED_LAYOUT_COUNT} frames.",
    )
    require(
        tuple(str(frame["layout_id"]) for frame in frames) == EXPECTED_LAYOUT_IDS,
        "Person C layout identities are not layout_01..layout_06 in order.",
    )

    documents: dict[str, dict[str, Any]] = {}
    raw_bytes: dict[str, bytes] = {}
    for entry in frames:
        layout_id = str(entry["layout_id"])
        frame_payload = read_bound_blob(
            str(entry["path"]),
            expected_sha256=str(entry["sha256"]),
            repository_root=repository_root,
        )
        document = _strict_json(
            frame_payload, label=f"Person C coordinate frame {layout_id}"
        )
        require(
            isinstance(document, Mapping),
            f"Person C coordinate frame {layout_id} must be an object.",
        )
        documents[layout_id] = dict(document)
        raw_bytes[layout_id] = frame_payload

    return {
        "authority": dict(authority),
        "authority_sha256": sha256_bytes(payload),
        "frames": documents,
        "frame_bytes": raw_bytes,
        "frame_index": {str(entry["layout_id"]): dict(entry) for entry in frames},
    }


def load_accepted_geometry(
    repository_root: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Load the accepted layout geometry Person C's frames must agree with."""

    payload = read_bound_blob(
        ACCEPTED_GEOMETRY_PATH,
        expected_sha256=ACCEPTED_GEOMETRY_SHA256,
        repository_root=repository_root,
    )
    geometry = _strict_json(payload, label="accepted layout geometry")
    require(isinstance(geometry, Mapping), "Accepted geometry root must be an object.")
    require(
        geometry.get("config_version") == ACCEPTED_GEOMETRY_VERSION,
        "Accepted geometry config_version is not the accepted version.",
    )
    layouts = geometry.get("layouts")
    require(
        isinstance(layouts, list) and len(layouts) == EXPECTED_LAYOUT_COUNT,
        f"Accepted geometry must define {EXPECTED_LAYOUT_COUNT} layouts.",
    )
    by_layout = {str(item["layout_id"]): dict(item) for item in layouts}
    require(
        tuple(sorted(by_layout)) == EXPECTED_LAYOUT_IDS,
        "Accepted geometry layout identities are not layout_01..layout_06.",
    )
    return by_layout


# --------------------------------------------------------------------------
# Independent per-layout validation
# --------------------------------------------------------------------------
def _vector(value: Any, name: str) -> tuple[float, float, float]:
    require(
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and len(value) == 3
        and all(
            not isinstance(item, bool)
            and isinstance(item, (int, float))
            and math.isfinite(float(item))
            for item in value
        ),
        f"{name} must be three finite numbers.",
    )
    return float(value[0]), float(value[1]), float(value[2])


def validate_layout_frame(
    layout_id: str,
    frame: Mapping[str, Any],
    geometry_layout: Mapping[str, Any],
) -> dict[str, Any]:
    """Rebuild every derived quantity in one frame from the accepted geometry."""

    checks: dict[str, bool] = {}
    authority = frame.get("person_c_authority")
    require(
        isinstance(authority, Mapping),
        f"{layout_id}: frame is missing person_c_authority.",
    )

    # --- world coordinate convention -------------------------------------
    grammar_axis_unit = authority.get("scalar_axis_unit")
    checks["world_coordinate_system_is_minecraft_world_xyz"] = (
        authority.get("world_coordinate_system") == "minecraft_world_x_y_z"
    )
    checks["scalar_axis_unit_is_blocks"] = grammar_axis_unit == "blocks"
    checks["coordinate_frame_schema_matches_person_b"] = (
        frame.get("coordinate_frame_schema_version") == COORDINATE_FRAME_SCHEMA_VERSION
    )
    checks["layout_identity_agrees"] = (
        authority.get("layout_id") == layout_id
        and geometry_layout.get("layout_id") == layout_id
    )

    # --- accepted layout/config version and geometry SHA ------------------
    checks["accepted_layout_config_version_agrees"] = (
        authority.get("layout_config_version") == ACCEPTED_GEOMETRY_VERSION
        and geometry_layout.get("config_version") == ACCEPTED_GEOMETRY_VERSION
    )
    checks["source_layout_manifest_hash_is_accepted_geometry"] = (
        frame.get("source_layout_manifest_hash") == ACCEPTED_GEOMETRY_SHA256
    )
    geometry_paths = {
        item.get("role"): item
        for item in authority.get("geometry_source_paths", [])
        if isinstance(item, Mapping)
    }
    accepted_source = geometry_paths.get("accepted_geometry_authority", {})
    checks["geometry_source_path_and_sha_agree"] = (
        accepted_source.get("path") == ACCEPTED_GEOMETRY_PATH
        and accepted_source.get("sha256") == ACCEPTED_GEOMETRY_SHA256
    )

    # --- wall-parallel scalar axis ----------------------------------------
    geometry_scalar = geometry_layout.get("scalar_axis", {})
    scalar_axis = authority.get("wall_parallel_scalar_axis")
    checks["scalar_axis_matches_accepted_geometry"] = (
        scalar_axis == geometry_scalar.get("world_axis")
        and scalar_axis == authority.get("source_world_axis_component")
        and scalar_axis in AXIS_INDEX
        and scalar_axis != "y"
    )
    checks["scalar_axis_is_wall_parallel"] = (
        authority.get("wall_axis") == scalar_axis
        and authority.get("lane_relation") == "wall_parallel"
        and str(geometry_layout.get("lane", {}).get("axis", "")).lower() == scalar_axis
    )

    # --- x/z projection roles ---------------------------------------------
    if scalar_axis == "x":
        expected_roles = ("wall_parallel_scalar", "orthogonal_fixed")
    else:
        expected_roles = ("orthogonal_fixed", "wall_parallel_scalar")
    checks["x_and_z_projection_roles_are_explicit"] = (
        authority.get("source_x_coordinate_role") == expected_roles[0]
        and authority.get("source_z_coordinate_role") == expected_roles[1]
    )
    checks["no_silent_axis_inference"] = (
        authority.get("silent_axis_inference") is False
        and authority.get("private_axis_reinterpretation") is False
    )

    # --- positive sign convention and unit vector -------------------------
    unit_vector = _vector(
        frame.get("wall_parallel_positive_unit_vector_world_xyz"),
        f"{layout_id}: unit vector",
    )
    expected_unit = AXIS_UNIT_VECTOR.get(str(scalar_axis))
    checks["unit_vector_is_positive_basis_of_scalar_axis"] = (
        expected_unit is not None and unit_vector == expected_unit
    )
    checks["unit_vector_norm_is_one"] = math.isclose(
        math.hypot(*unit_vector), 1.0, rel_tol=0.0, abs_tol=UNIT_NORM_TOLERANCE
    )
    direction = authority.get("axis_direction", {})
    checks["positive_world_direction_agrees"] = (
        direction.get("positive_world_direction") == f"+{scalar_axis}"
        and direction.get("positive_world_direction")
        == geometry_scalar.get("positive_world_direction")
        and _vector(
            direction.get("positive_unit_vector_world_xyz"),
            f"{layout_id}: authority unit vector",
        )
        == unit_vector
    )
    checks["positive_sign_convention_is_increasing_world_component"] = (
        authority.get("positive_sign_convention")
        == f"increasing world {scalar_axis} is increasing wall-parallel scalar "
        f"position (+{scalar_axis})"
    )

    # --- motion sign -------------------------------------------------------
    checks["motion_sign_is_positive_and_matches_geometry"] = (
        authority.get("motion_sign") == 1
        and geometry_layout.get("motion_sign") == 1
    )

    # --- origin -----------------------------------------------------------
    origin = _vector(
        frame.get("wall_parallel_origin_world_xyz"), f"{layout_id}: origin"
    )
    lane = geometry_layout.get("lane", {})
    lane_start = _vector(lane.get("world_start_xyz"), f"{layout_id}: lane start")
    axis_idx = AXIS_INDEX[str(scalar_axis)]
    declared_origin_scalar = geometry_scalar.get("origin_world_coordinate_blocks")
    rebuilt_origin = list(lane_start)
    rebuilt_origin[axis_idx] = float(declared_origin_scalar)
    checks["origin_is_lane_anchor_with_declared_scalar_component"] = (
        tuple(rebuilt_origin) == origin
    )
    checks["origin_scalar_component_agrees"] = (
        origin[axis_idx] == float(declared_origin_scalar)
        and authority.get("axis_origin", {}).get("origin_world_coordinate_blocks")
        == declared_origin_scalar
    )
    checks["origin_orthogonal_components_are_lane_anchor"] = all(
        origin[index] == lane_start[index]
        for index in range(3)
        if index != axis_idx
    )

    # --- wall bounds ------------------------------------------------------
    checks["wall_bounds_match_accepted_geometry"] = authority.get("wall_bounds") == (
        geometry_layout.get("wall", {}).get("bounds")
    )
    checks["wall_block_matches_accepted_geometry"] = authority.get("wall_block") == (
        geometry_layout.get("wall", {}).get("block")
    )

    # --- lane bounds ------------------------------------------------------
    frame_lane = authority.get("lane_bounds", {})
    checks["lane_bounds_match_accepted_geometry"] = all(
        frame_lane.get(field) == lane.get(field)
        for field in (
            "axis",
            "axis_min",
            "axis_max",
            "ortho",
            "feet_y",
            "world_start_xyz",
            "world_end_xyz",
        )
    )

    # --- shadow bounds ----------------------------------------------------
    frame_shadow = authority.get("shadow_bounds", {})
    geometry_shadow = geometry_layout.get("shadow", {})
    samples = geometry_shadow.get("integer_lane_samples", [])
    occluded_positions = [
        int(item["axis_position"]) for item in samples if item.get("occluded") is True
    ]
    checks["shadow_samples_match_accepted_geometry"] = (
        frame_shadow.get("integer_lane_samples") == samples
        and frame_shadow.get("definition") == geometry_shadow.get("definition")
        and frame_shadow.get("target_centre_y") == geometry_shadow.get("target_centre_y")
        and frame_shadow.get("camera_source") == geometry_shadow.get("camera_source")
    )
    checks["shadow_occluded_interval_is_rederived"] = (
        frame_shadow.get("occluded_integer_axis_positions") == occluded_positions
        and bool(occluded_positions)
        and frame_shadow.get("occluded_integer_axis_min") == min(occluded_positions)
        and frame_shadow.get("occluded_integer_axis_max") == max(occluded_positions)
        and frame_shadow.get("occluded_interval_contiguous")
        is (
            occluded_positions
            == list(range(min(occluded_positions), max(occluded_positions) + 1))
        )
    )
    checks["shadow_interval_lies_inside_lane"] = (
        float(min(occluded_positions)) >= float(lane["axis_min"])
        and float(max(occluded_positions)) <= float(lane["axis_max"])
    )
    checks["shadow_continuous_boundary_not_silently_interpolated"] = (
        frame_shadow.get("continuous_boundary_measured") is False
        and frame_shadow.get("sample_resolution") == "integer_lane_samples_only"
    )

    # --- camera -----------------------------------------------------------
    checks["camera_pose_matches_accepted_geometry"] = authority.get(
        "camera_canonical_pose"
    ) == geometry_layout.get("camera")

    # --- coordinate frame hash and Person B validator ---------------------
    checks["coordinate_frame_hash_reproduces"] = (
        coordinate_frame_hash(frame) == frame.get("coordinate_frame_hash")
    )
    try:
        validate_coordinate_frame(frame, require_cross_role_signoff=False)
        person_b_validator_accepts = True
    except CoordinateContractError:
        person_b_validator_accepts = False
    checks["person_b_validator_accepts_c_side_frame"] = person_b_validator_accepts
    checks["person_b_side_not_presigned_by_person_c"] = (
        frame.get("adapter_signoff", {}).get("person_b") is False
        and frame.get("adapter_signoff", {}).get("person_c") is True
    )

    return {
        "layout_id": layout_id,
        "wall_parallel_scalar_axis": scalar_axis,
        "positive_world_direction": direction.get("positive_world_direction"),
        "origin_world_xyz": list(origin),
        "positive_unit_vector_world_xyz": list(unit_vector),
        "motion_sign": authority.get("motion_sign"),
        "lane_axis_min": lane.get("axis_min"),
        "lane_axis_max": lane.get("axis_max"),
        "lane_ortho": lane.get("ortho"),
        "wall_bounds": authority.get("wall_bounds"),
        "shadow_occluded_integer_axis_min": frame_shadow.get(
            "occluded_integer_axis_min"
        ),
        "shadow_occluded_integer_axis_max": frame_shadow.get(
            "occluded_integer_axis_max"
        ),
        "coordinate_frame_hash": frame.get("coordinate_frame_hash"),
        "checks": dict(sorted(checks.items())),
        "compatible": all(checks.values()),
        "failed_checks": sorted(name for name, ok in checks.items() if not ok),
    }


# --------------------------------------------------------------------------
# Replay of Person B's own projection against real captured state
# --------------------------------------------------------------------------
def replay_projection_against_capture_packages(
    frames: Mapping[str, Mapping[str, Any]],
    *,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Replay Person B's projection over every captured state row.

    ``build_state_input_from_capture_package`` accepts a row only when Person
    B's own projection of the world position reproduces Person C's declared
    ``wall_parallel_position_blocks``.  Running that comparison here, before any
    oracle is built, is what turns Person C's declaration into evidence.
    """

    manifest = _strict_json(
        read_bound_blob(
            PERSON_C_CAPTURE_PACKAGE_MANIFEST_PATH,
            expected_sha256=PERSON_C_CAPTURE_PACKAGE_MANIFEST_SHA256,
            repository_root=repository_root,
        ),
        label="Person C capture-package manifest",
    )
    require(
        manifest.get("capture_package_count") == EXPECTED_TRAJECTORY_COUNT,
        f"Expected {EXPECTED_TRAJECTORY_COUNT} capture packages.",
    )

    projectors = {
        layout_id: validate_coordinate_frame(frame, require_cross_role_signoff=False)
        for layout_id, frame in frames.items()
    }

    per_layout: dict[str, dict[str, Any]] = {
        layout_id: {
            "layout_id": layout_id,
            "trajectory_count": 0,
            "state_row_count": 0,
            "target_bearing_row_count": 0,
            "max_abs_projection_error_blocks": 0.0,
            "max_abs_orthogonal_deviation_blocks": 0.0,
            "monotone_step_sign_disagreement_count": 0,
            "occluded_row_outside_shadow_bracket_count": 0,
        }
        for layout_id in frames
    }
    total_rows = 0
    total_target_rows = 0
    mismatches: list[dict[str, Any]] = []

    for record in manifest["records"]:
        layout_id = str(record["layout_id"])
        require(
            layout_id in frames,
            f"Capture package names unknown layout {layout_id!r}.",
        )
        package = _strict_json(
            read_bound_blob(
                str(record["capture_package_path"]),
                expected_sha256=str(record["capture_package_sha256"]),
                repository_root=repository_root,
            ),
            label=f"capture package {record['capture_package_path']}",
        )
        require(
            package["episode_manifest"]["layout_config_hash"] == ACCEPTED_GEOMETRY_SHA256,
            f"{record['trajectory_id']}: layout_config_hash is not the accepted "
            "geometry; Person B's adapter would reject this binding.",
        )
        require(
            record["coordinate_frame_hash"]
            == frames[layout_id]["coordinate_frame_hash"],
            f"{record['trajectory_id']}: capture package names a different "
            "coordinate frame hash.",
        )

        frame_document = frames[layout_id]
        projector = projectors[layout_id]
        authority = frame_document["person_c_authority"]
        axis_idx = AXIS_INDEX[str(authority["wall_parallel_scalar_axis"])]
        shadow = authority["shadow_bounds"]
        # The accepted geometry samples occlusion at integer lane positions
        # only, so the continuous shadow edge sits somewhere inside one sample
        # step of the bracket.  Widening by exactly one sample is the tightest
        # claim the evidence supports.
        shadow_low = float(shadow["occluded_integer_axis_min"]) - 1.0
        shadow_high = float(shadow["occluded_integer_axis_max"]) + 1.0

        summary = per_layout[layout_id]
        summary["trajectory_count"] += 1

        visibility_by_key = {
            (row["trajectory_id"], row["model_frame_idx"]): row
            for row in package["streams"]["visibility"]
        }
        previous_scalar: float | None = None
        previous_world: float | None = None
        for row in package["streams"]["server_state"]:
            state = row["state"]
            summary["state_row_count"] += 1
            total_rows += 1
            if state.get("target_present") is not True:
                previous_scalar = None
                previous_world = None
                continue
            summary["target_bearing_row_count"] += 1
            total_target_rows += 1

            position = (
                float(state["position_x_blocks"]),
                float(state["position_y_blocks"]),
                float(state["position_z_blocks"]),
            )
            projected = projector.project(position)
            declared = float(state["wall_parallel_position_blocks"])
            error = abs(projected - declared)
            if error > PROJECTION_EXACT_TOLERANCE_BLOCKS:
                summary["max_abs_projection_error_blocks"] = max(
                    summary["max_abs_projection_error_blocks"], error
                )
                if len(mismatches) < 20:
                    mismatches.append(
                        {
                            "trajectory_id": row["trajectory_id"],
                            "model_frame_idx": row["model_frame_idx"],
                            "layout_id": layout_id,
                            "projected_blocks": projected,
                            "declared_blocks": declared,
                            "abs_error_blocks": error,
                        }
                    )

            # The orthogonal components must stay pinned to the lane anchor,
            # otherwise the scalar axis is not the only degree of freedom.
            lane = authority["lane_bounds"]
            orthogonal_expected = list(lane["world_start_xyz"])
            deviation = max(
                abs(position[index] - float(orthogonal_expected[index]))
                for index in range(3)
                if index != axis_idx
            )
            summary["max_abs_orthogonal_deviation_blocks"] = max(
                summary["max_abs_orthogonal_deviation_blocks"], deviation
            )

            # Motion sign: the scalar must move with the world component.
            world_component = position[axis_idx]
            if previous_scalar is not None and previous_world is not None:
                scalar_step = projected - previous_scalar
                world_step = world_component - previous_world
                if scalar_step != world_step:
                    summary["monotone_step_sign_disagreement_count"] += 1
            previous_scalar = projected
            previous_world = world_component

            visibility = visibility_by_key.get(
                (row["trajectory_id"], row["model_frame_idx"])
            )
            if (
                visibility is not None
                and visibility.get("geometric_visible") is False
                and not shadow_low <= projected <= shadow_high
            ):
                summary["occluded_row_outside_shadow_bracket_count"] += 1

    checks = {
        "every_layout_replayed": all(
            item["trajectory_count"] > 0 for item in per_layout.values()
        ),
        "projection_matches_person_c_exactly": all(
            item["max_abs_projection_error_blocks"] == 0.0
            for item in per_layout.values()
        ),
        "orthogonal_components_pinned_to_lane": all(
            item["max_abs_orthogonal_deviation_blocks"] == 0.0
            for item in per_layout.values()
        ),
        "scalar_moves_with_world_component": all(
            item["monotone_step_sign_disagreement_count"] == 0
            for item in per_layout.values()
        ),
        "occluded_rows_inside_shadow_bracket": all(
            item["occluded_row_outside_shadow_bracket_count"] == 0
            for item in per_layout.values()
        ),
    }
    return {
        "capture_package_count": len(manifest["records"]),
        "state_row_count": total_rows,
        "target_bearing_row_count": total_target_rows,
        "per_layout": [per_layout[key] for key in sorted(per_layout)],
        "checks": dict(sorted(checks.items())),
        "mismatches": mismatches,
        "replay_pass": all(checks.values()),
    }


# --------------------------------------------------------------------------
# Person B co-sign
# --------------------------------------------------------------------------
def cosign_frame(
    frame: Mapping[str, Any],
    *,
    person_b_branch: str,
    person_b_commit: str | None,
    cosign_receipt_id: str,
) -> dict[str, Any]:
    """Return the Person B co-signed frame, preserving coordinate_frame_hash."""

    original_hash = frame["coordinate_frame_hash"]
    cosigned = json.loads(json.dumps(frame))
    require(
        cosigned["adapter_signoff"]["person_b"] is False,
        "Person B side is already signed; refusing to re-sign.",
    )
    cosigned["adapter_signoff"]["person_b"] = True
    cosigned["person_b_cosign"] = {
        "cosign_schema_version": COSIGN_SCHEMA_VERSION,
        "cosign_receipt_id": cosign_receipt_id,
        "decision_date": DECISION_DATE,
        "owner_role": "person_b",
        "person_b_branch": person_b_branch,
        "person_b_commit": person_b_commit,
        "person_c_commit": PERSON_C_COMMIT,
        "person_c_coordinate_frame_authority_path": (
            PERSON_C_COORDINATE_FRAME_AUTHORITY_PATH
        ),
        "person_c_coordinate_frame_authority_sha256": (
            PERSON_C_COORDINATE_FRAME_AUTHORITY_SHA256
        ),
        "person_c_bytes_modified": False,
        "coordinate_frame_hash_preserved": True,
        "scientific_result_inspected": False,
        "outcome_dependent_change": False,
    }
    require(
        coordinate_frame_hash(cosigned) == original_hash,
        "Co-sign changed the coordinate-frame hash; refusing to publish.",
    )
    validate_coordinate_frame(cosigned, require_cross_role_signoff=True)
    return cosigned


def build_cosign_document(
    *,
    layout_results: Sequence[Mapping[str, Any]],
    replay: Mapping[str, Any],
    cosigned_hashes: Mapping[str, str],
    person_c_frame_hashes: Mapping[str, str],
    code_sha: str,
    person_b_branch: str,
    person_b_commit: str | None,
) -> dict[str, Any]:
    """Seal Person B's machine-readable coordinate-frame sign-off."""

    config = load_core_analysis_config()
    contract = config["coordinate_contract"]
    compatible = all(item["compatible"] for item in layout_results) and bool(
        replay["replay_pass"]
    )
    return seal_artifact(
        {
            "artifact_type": "person_b_coordinate_frame_cosign",
            "artifact_id": "person-b-66-cell-coordinate-frame-cosign-v0.1",
            "code_sha": code_sha,
            "config_hash": hash_core_analysis_config(),
            "input_manifest_hash": PERSON_C_COORDINATE_FRAME_AUTHORITY_SHA256,
            "cosign_schema_version": COSIGN_SCHEMA_VERSION,
            "analysis_config_version": ANALYSIS_CONFIG_VERSION,
            "decision_date": DECISION_DATE,
            "producer_role": "person_b",
            "synthetic": False,
            "scientific_use": "permitted",
            "person_c_commit": PERSON_C_COMMIT,
            "person_c_coordinate_frame_path": (
                PERSON_C_COORDINATE_FRAME_AUTHORITY_PATH
            ),
            "person_c_coordinate_frame_sha256": (
                PERSON_C_COORDINATE_FRAME_AUTHORITY_SHA256
            ),
            "person_c_capture_package_manifest_path": (
                PERSON_C_CAPTURE_PACKAGE_MANIFEST_PATH
            ),
            "person_c_capture_package_manifest_sha256": (
                PERSON_C_CAPTURE_PACKAGE_MANIFEST_SHA256
            ),
            "person_c_bytes_modified": False,
            "person_c_branch_merged": False,
            "accepted_geometry_path": ACCEPTED_GEOMETRY_PATH,
            "accepted_geometry_sha256": ACCEPTED_GEOMETRY_SHA256,
            "accepted_geometry_version": ACCEPTED_GEOMETRY_VERSION,
            "layout_count": len(layout_results),
            "layout_ids": [item["layout_id"] for item in layout_results],
            "person_b_wall_parallel_interpretation": {
                "quantity": contract["quantity"],
                "unit": contract["unit"],
                "scalar_definition": contract["positive_direction_rule"],
                "projection": (
                    "wall_parallel_position_blocks = "
                    "dot(world_position_xyz - wall_parallel_origin_world_xyz, "
                    "wall_parallel_positive_unit_vector_world_xyz)"
                ),
                "implementation": (
                    "mineocclude.analysis.coordinates."
                    "WallParallelCoordinateFrame.project"
                ),
                "validator": "mineocclude.analysis.coordinates.validate_coordinate_frame",
                "unit_vector_norm_tolerance": contract["unit_vector_norm_tolerance"],
                "silent_axis_inference_forbidden": contract[
                    "silent_axis_inference_forbidden"
                ],
                "requires_person_c_adapter_signoff_before_live_use": contract[
                    "requires_person_c_adapter_signoff_before_live_use"
                ],
                "oracle_target_units": {
                    "mu_oracle_blocks": "blocks",
                    "sigma_oracle_blocks": "blocks",
                    "var_oracle_blocks2": "blocks_squared",
                    "x_true_blocks": "blocks",
                    "observed_position_blocks": "blocks",
                },
                "person_b_owns": (
                    "unit and sign compatibility of the scalar with Person B's "
                    "oracle targets; Person B does not own or redefine the world "
                    "coordinate system, the axis, the origin, or the bounds"
                ),
            },
            "per_layout_validation": list(layout_results),
            "projection_replay": dict(replay),
            "compatibility_result": {
                "coordinate_frame_compatible": compatible,
                "all_layouts_compatible": all(
                    item["compatible"] for item in layout_results
                ),
                "projection_replay_pass": replay["replay_pass"],
                "failed_layout_ids": [
                    item["layout_id"] for item in layout_results if not item["compatible"]
                ],
                "units_compatible_with_person_b_oracle": True,
                "sign_convention_compatible_with_person_b_oracle": True,
            },
            "adapter_signoff": {
                "person_b": compatible,
                "person_c": True,
                "person_b_signoff_scope": (
                    "Person B independently revalidated the world-coordinate "
                    "convention, scalar axis, origin, positive sign convention, "
                    "x/z projection roles, motion sign, wall bounds, lane bounds, "
                    "shadow bounds, accepted layout/config version, and geometry "
                    "SHA against the accepted geometry, then replayed Person B's "
                    "own projection over every captured target-bearing state row."
                ),
            },
            "cosigned_frames": [
                {
                    "layout_id": layout_id,
                    "path": f"{COSIGNED_FRAME_DIRECTORY}/{layout_id}.json",
                    "person_b_cosigned_file_sha256": cosigned_hashes[layout_id],
                    "person_c_source_file_sha256": person_c_frame_hashes[layout_id],
                    "coordinate_frame_hash": next(
                        item["coordinate_frame_hash"]
                        for item in layout_results
                        if item["layout_id"] == layout_id
                    ),
                    "coordinate_frame_hash_preserved": True,
                }
                for layout_id in sorted(cosigned_hashes)
            ],
            "person_b_branch": person_b_branch,
            "person_b_commit": person_b_commit,
            "scientific_result_inspected": False,
            "outcome_dependent_change": False,
            "activation_analysis_executed": False,
            "oracle_target_manifest_built": False,
            "scope_note": (
                "This artifact records only the Person B co-sign of Person C's "
                "coordinate frames. It does not build the oracle-target manifest "
                "and does not run any activation analysis."
            ),
        }
    )


__all__ = [
    "ACCEPTED_GEOMETRY_PATH",
    "ACCEPTED_GEOMETRY_SHA256",
    "ACCEPTED_GEOMETRY_VERSION",
    "COSIGNED_FRAME_DIRECTORY",
    "COSIGN_PACKAGE_DIRECTORY",
    "COSIGN_SCHEMA_VERSION",
    "DECISION_DATE",
    "EXPECTED_LAYOUT_COUNT",
    "EXPECTED_LAYOUT_IDS",
    "EXPECTED_TRAJECTORY_COUNT",
    "PERSON_C_CAPTURE_PACKAGE_MANIFEST_PATH",
    "PERSON_C_CAPTURE_PACKAGE_MANIFEST_SHA256",
    "PERSON_C_COMMIT",
    "PERSON_C_COORDINATE_FRAME_AUTHORITY_PATH",
    "PERSON_C_COORDINATE_FRAME_AUTHORITY_SHA256",
    "CoordinateCosignError",
    "build_cosign_document",
    "cosign_frame",
    "derive_cosign_code_sha",
    "load_accepted_geometry",
    "load_person_c_authority",
    "read_bound_blob",
    "replay_projection_against_capture_packages",
    "require",
    "sha256_bytes",
    "validate_layout_frame",
]
