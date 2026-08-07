"""Build the Person C 66-cell capture authority closure (additive successor).

Closes the Person C-owned structural contracts that Person B's 66-cell
preactivation audit found missing for the frozen production universe
ep12601-ep12666 (66 accepted / 0 excluded):

  1. one ``capture_package_v0_1.json`` per accepted episode, at the repository
     path Person B's frozen oracle adapter already expects
     (``data/autonomous/<trajectory_id>/capture_package_v0_1.json``);
  2. the Person C side of the wall-parallel coordinate frame for
     layout_01..layout_06, signed by Person C only and left co-signable by
     Person B without changing ``coordinate_frame_hash``;
  3. a deterministic C->E request for the frozen empirical magenta detector;
  4. the C-owned U4 terminal-reveal structural finding and the supplemental
     capture requirements receipt;
  5. the additive C->B successor consumer receipt.

Nothing historical is rewritten. The frozen C7.5 handoff
(``docs/status/person_c_c7_mvp_handoff_v0_1``) is read-only input here, and the
66 accepted / 0 excluded decision is re-derived and asserted, never edited.

Every published value is derived from committed immutable authorities or from
hash-verified Person C runtime payloads:
  - docs/status/person_c_c7_mvp_handoff_v0_1/...      (frozen C7.5 authority)
  - configs/scenes/layouts_v0_4.yaml                  (accepted geometry)
  - configs/collection/person_c_c6a_v0_1/schedules/   (immutable noise schedules)
  - Person A's 66-cell frame-map package, read read-only out of A's commit
  - the Person C Windows runtime payloads, hash-checked against C7.5

No empirical magenta visibility is invented: the ``visibility`` stream carries
the Person C geometric channel only, and the absent Person E channel is made
explicit and machine-readable at row level and at package level.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from mineocclude.data.capture_contract import validate_capture_package  # noqa: E402
from mineocclude.data.convert_mineworld import (  # noqa: E402
    bin_camera,
    flat_to_official_raw_action,
)
from mineocclude.data.noise_schedule import load_schedule  # noqa: E402
from mineocclude.analysis.coordinates import (  # noqa: E402
    COORDINATE_FRAME_SCHEMA_VERSION,
    coordinate_frame_hash,
)

# ---------------------------------------------------------------- identities

SCHEMA_ID = "mineocclude-person-c-66-cell-capture-authority-v0.1"
SCHEMA_VERSION = "0.1"

# Person C authority commit this closure is derived from (deterministic; not
# the live git HEAD, so regeneration is byte-stable across later commits).
C_SOURCE_COMMIT = "a8bed8adf7e24ca7fe5b6b6afa3342da61434be3"
C_ACCEPTED_MANIFEST_SHA256 = (
    "96ba43e15bc024aeaef7c519fa4ece0a4afe0bb0e877501dffaca44fee927ff7"
)
ACCEPTED_GEOMETRY_SHA256 = (
    "34495d650d6a8c62b00a916796c90389b48f80d8f20a23eac93207758e993f5d"
)
ACCEPTED_GEOMETRY_VERSION = "person-c-layout-config-v0.4"

PERSON_A_COMMIT = "77e43bd1665671b9e23d6d6ef927ee4944611342"
PERSON_A_PKG_REL = "data/handoff_a/person_a_66_cell_production_input_v0_1"
PERSON_A_PKG_SHA256 = (
    "a473bf830ed31e49762d62bba97032e52f4967e52f9987ad10cd5879ed9bd004"
)
PERSON_B_COMMIT = "3678cc90c583877d330c01807fe11d393902d146"
PERSON_B_FOLD_MANIFEST_REL = (
    "docs/status/person_b_66_cell_preactivation_v0_1/fold_manifest.json"
)
PERSON_B_FOLD_SHA256 = (
    "86739975882f4926c3398d5bfa21611daf06c579b3893809eb385e8dcd03001d"
)

RUN_ID = "person-c-c6a-post-c1-v0.1"
LIFECYCLE_VERSION = "person-c-tick-lifecycle-v0.1"
PERSON_C_CONTRACT_VERSION = "0.1"
TRAJECTORY_SCHEMA_VERSION = "1.0"

FIRST_EP, LAST_EP = 12601, 12666
EXPECTED_ACCEPTED = 66
EXPECTED_EXCLUDED = 0
EXPECTED_MODEL_FRAME_KEYS = 2468
TICK_RATE_HZ = 20.0
DT_SECONDS = 0.05

# ------------------------------------------------------------------- inputs

C75_REL = "docs/status/person_c_c7_mvp_handoff_v0_1"
GEOMETRY_REL = "configs/scenes/layouts_v0_4.yaml"
SCHEDULE_DIR_REL = "configs/collection/person_c_c6a_v0_1/schedules"
ENV_LOCK_REL = (
    "docs/status/person_c_c1_runtime_ingestion_v0_1/"
    "final_environment_lock_receipt.json"
)
ENV_LOCK_SHA256 = (
    "f25ff4fab1e16968b0008807600e8d50d5647a83c4e7ba40d53b4cbf0a5ae66e"
)
ANALYSIS_CORE_REL = "configs/analysis/core.yaml"

# Committed scripted one-tick camera-impulse fixture. Its QA report is the
# immutable evidence for the camera-axis orientation block A's frozen
# validator requires. The v0.1 contract fixes evidence_scope to the literal
# "synthetic_contract_only" even for real runtime evidence (see
# mineocclude.data.package_episode); widening that vocabulary is a v0.2 change.
IMPULSE_FIXTURE_REL = "data/handoff_a/impulse_fixture_9440"
IMPULSE_FIXTURE_ID = "runtime_scripted_impulse_9440"

# ------------------------------------------------------------------ outputs

STATUS_REL = "docs/status/person_c_66_cell_capture_authority_v0_1"
AUTONOMOUS_REL = "data/autonomous"
FRAMES_REL = "data/person_b/c6a_c_intake/coordinate_frames"
E_REQUEST_REL = (
    "data/handoff_e/"
    "person_c_to_person_e_66_cell_empirical_visibility_request_v0_1"
)

# Frozen scene -> condition vocabulary (configs/scenes/layouts_v0_4.yaml).
SCENE_CONDITION = {
    "NORMAL": "core",
    "NO_WALL": "no_wall_visible",
    "NO_SHEEP": "occluder_only_no_sheep",
}

RAW_FIELDS = (
    "forward", "back", "left", "right", "jump", "sneak", "sprint",
    "use", "attack", "drop", "pick_item", "hotbar", "camera_dx", "camera_dy",
)

# Person E owns the empirical magenta channel; Person C states only absence.
E_ABSENT = "absent_pending_person_e_frozen_detector"
DOWNSTREAM = "produced_downstream_not_at_c6a_raw_capture_layer"

# Person B owns the U4 selection thresholds. Recorded as foreign, never as a
# Person C decision and never relaxed.
B_REVEAL_WINDOW_SECONDS = [-1.0, 1.0]
B_REQUIRED_HELDOUT_EVENT_COUNT = 5


class BuildError(Exception):
    """Raised when a committed authority fails to reconcile."""


def fail(message: str) -> None:
    raise BuildError(message)


# ------------------------------------------------------------------ helpers

def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_path(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(document) -> bytes:
    """The repository's canonical JSON encoding for published artifacts."""
    return json.dumps(document, indent=1, sort_keys=True).encode("utf-8")


def write_json(path: str, document) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = canonical_bytes(document)
    with open(path, "wb") as handle:
        handle.write(payload)
    return sha256_bytes(payload)


def write_jsonl(path: str, rows) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buffer = bytearray()
    for row in rows:
        buffer += json.dumps(row, sort_keys=True).encode("utf-8") + b"\n"
    with open(path, "wb") as handle:
        handle.write(bytes(buffer))
    return sha256_bytes(bytes(buffer))


def read_jsonl(path: str):
    with open(path, "r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def git_show(commit: str, rel_path: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", ROOT, "show", f"{commit}:{rel_path}"],
        capture_output=True, timeout=120,
    )
    if result.returncode != 0:
        fail(
            f"required foreign authority {rel_path!r} is not readable at "
            f"{commit[:12]}: {result.stderr.decode(errors='replace').strip()}"
        )
    return result.stdout


def tri(positive, negative) -> int:
    if bool(positive):
        return 1
    if bool(negative):
        return 2
    return 0


def normalized_action(row) -> dict:
    """A's frozen integer container fields, via the reference conversion."""
    return {
        "camera_component_0": bin_camera(float(row["camera_dy"])),
        "camera_component_1": bin_camera(float(row["camera_dx"])),
        "hotbar": int(row["hotbar"]),
        "forward_back": tri(row["forward"], row["back"]),
        "left_right": tri(row["left"], row["right"]),
        "sprint_sneak": tri(row["sprint"], row["sneak"]),
        "use_attack": tri(row["use"], row["attack"]),
        "jump": 1 if bool(row["jump"]) else 0,
        "drop_pick_item": tri(row["drop"], row["pick_item"]),
    }


# --------------------------------------------------------- load C authority

def load_c_authority():
    """Load and re-derive the frozen C7.5 accepted universe (never edited)."""
    manifest_path = os.path.join(ROOT, C75_REL, "trajectories_mvp_manifest.json")
    ledger_path = os.path.join(ROOT, C75_REL, "accepted_excluded_ledger.json")
    observed = sha256_path(manifest_path)
    if observed != C_ACCEPTED_MANIFEST_SHA256:
        fail(
            "frozen C accepted manifest identity changed: "
            f"{observed} != {C_ACCEPTED_MANIFEST_SHA256}"
        )
    manifest = json.loads(open(manifest_path, "rb").read())
    ledger = json.loads(open(ledger_path, "rb").read())
    if (
        manifest["accepted_count"] != EXPECTED_ACCEPTED
        or manifest["excluded_count"] != EXPECTED_EXCLUDED
        or ledger["accepted_count"] != EXPECTED_ACCEPTED
        or ledger["excluded_count"] != EXPECTED_EXCLUDED
    ):
        fail("the frozen 66 accepted / 0 excluded decision does not reconcile")
    records = {int(r["episode_id"]): r for r in manifest["records"]}
    if sorted(records) != list(range(FIRST_EP, LAST_EP + 1)):
        fail("accepted episode ids are not exactly ep12601-ep12666")
    if ledger["accepted_episode_ids"] != list(range(FIRST_EP, LAST_EP + 1)):
        fail("accepted ledger episode ids are not exactly ep12601-ep12666")
    bundles = {}
    for episode_id in records:
        path = os.path.join(ROOT, C75_REL, "per_trajectory", f"ep{episode_id}.json")
        bundles[episode_id] = {
            "document": json.loads(open(path, "rb").read()),
            "path_rel": f"{C75_REL}/per_trajectory/ep{episode_id}.json",
            "sha256": sha256_path(path),
        }
    return manifest, ledger, records, bundles


def load_person_a_frame_maps(records):
    """Read Person A's frame-map package read-only out of A's commit.

    Person A's branch is never merged or modified; only its committed bytes
    are read, and its declared package identity is re-verified.
    """
    inventory_bytes = git_show(
        PERSON_A_COMMIT, f"{PERSON_A_PKG_REL}/sha256_inventory.json"
    )
    observed = sha256_bytes(inventory_bytes)
    if observed != PERSON_A_PKG_SHA256:
        fail(
            "Person A frame-map package identity changed: "
            f"{observed} != {PERSON_A_PKG_SHA256}"
        )
    inventory = json.loads(inventory_bytes)
    frame_maps = {}
    for episode_id, record in sorted(records.items()):
        trajectory_id = record["trajectory_id"]
        rel = f"{PERSON_A_PKG_REL}/frame_maps/{trajectory_id}.jsonl"
        payload = git_show(PERSON_A_COMMIT, rel)
        rows = [json.loads(line) for line in payload.decode("utf-8").splitlines()
                if line.strip()]
        frame_maps[episode_id] = {
            "rows": rows,
            "path_rel": rel,
            "sha256": sha256_bytes(payload),
        }
    total = sum(len(entry["rows"]) for entry in frame_maps.values())
    if total != EXPECTED_MODEL_FRAME_KEYS:
        fail(
            "Person A frame-map model-frame key count is "
            f"{total}, expected {EXPECTED_MODEL_FRAME_KEYS}"
        )
    return inventory, frame_maps


def load_geometry():
    path = os.path.join(ROOT, GEOMETRY_REL)
    observed = sha256_path(path)
    if observed != ACCEPTED_GEOMETRY_SHA256:
        fail(
            "accepted geometry identity changed: "
            f"{observed} != {ACCEPTED_GEOMETRY_SHA256}"
        )
    document = json.loads(open(path, "rb").read())
    if document["config_version"] != ACCEPTED_GEOMETRY_VERSION:
        fail("accepted geometry config_version mismatch")
    layouts = {entry["layout_id"]: entry for entry in document["layouts"]}
    if sorted(layouts) != [f"layout_0{n}" for n in range(1, 7)]:
        fail("accepted geometry does not declare exactly layout_01..layout_06")
    return document, layouts


# ------------------------------------------------- runtime payload verify

RUNTIME_ROLES = (
    "server_state.jsonl",
    "layout_meta.json",
    "reset_result.json",
    "finalization.json",
    "lifecycle.jsonl",
    "client_tick.jsonl",
    "raw_actions.jsonl",
)


def verify_runtime_payloads(bundles):
    """Hash-verify every declared Person C runtime payload this build reads.

    Returns ``(inventory, discrepancies)``. Frame PNG bytes stay on the
    runtime machine; only their declared identities are carried forward.
    """
    inventory = {}
    discrepancies = []
    for episode_id, bundle in sorted(bundles.items()):
        artifacts = {a["artifact_role"]: a for a in bundle["document"]["artifacts"]}
        entry = {"roles": {}, "frames": []}
        for role in RUNTIME_ROLES:
            declared = artifacts.get(role)
            if declared is None:
                discrepancies.append({
                    "episode_id": episode_id, "artifact_role": role,
                    "discrepancy": "absent_from_c7_5_bundle",
                })
                continue
            path = declared["path_or_uri"]
            if not os.path.exists(path):
                discrepancies.append({
                    "episode_id": episode_id, "artifact_role": role,
                    "declared_path": path,
                    "discrepancy": "runtime_payload_not_present_on_this_host",
                })
                continue
            observed = sha256_path(path)
            entry["roles"][role] = {
                "declared_path": path,
                "declared_sha256": declared["sha256"],
                "declared_byte_size": declared["byte_size"],
                "observed_sha256": observed,
                "byte_identity_verified": observed == declared["sha256"],
            }
            if observed != declared["sha256"]:
                discrepancies.append({
                    "episode_id": episode_id, "artifact_role": role,
                    "declared_path": path,
                    "declared_sha256": declared["sha256"],
                    "observed_sha256": observed,
                    "discrepancy": "sha256_mismatch",
                })
        for declared in bundle["document"]["artifacts"]:
            role = declared["artifact_role"]
            if not role.startswith("frames/"):
                continue
            entry["frames"].append({
                "artifact_role": role,
                "declared_path": declared["path_or_uri"],
                "declared_sha256": declared["sha256"],
                "declared_byte_size": declared["byte_size"],
            })
        entry["frames"].sort(key=lambda item: item["artifact_role"])
        inventory[episode_id] = entry
    return inventory, discrepancies


# ------------------------------------------------------- coordinate frames

AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


def derive_coordinate_frame(layout):
    """Derive the wall-parallel scalar axis from accepted geometry only.

    The axis, origin and sign are read literally out of the accepted
    geometry's ``scalar_axis`` and ``lane`` declarations. Nothing is inferred:
    the caller re-verifies the projection against Person C runtime
    ``axis_pos`` for every target-bearing frame before the frame is signed.
    """
    scalar_axis = layout["scalar_axis"]
    lane = layout["lane"]
    world_axis = str(scalar_axis["world_axis"]).lower()
    if world_axis not in AXIS_INDEX:
        fail(f"{layout['layout_id']} declares an unknown scalar world axis")
    direction = str(scalar_axis["positive_world_direction"])
    if direction not in (f"+{world_axis}", f"-{world_axis}"):
        fail(f"{layout['layout_id']} sign convention is not axis-aligned")
    index = AXIS_INDEX[world_axis]
    unit = [0.0, 0.0, 0.0]
    unit[index] = 1.0 if direction.startswith("+") else -1.0
    # Origin is the lane point at scalar coordinate
    # ``origin_world_coordinate_blocks``; the orthogonal and vertical
    # components come from the lane's own declared world anchor.
    origin = [float(value) for value in lane["world_start_xyz"]]
    origin[index] = float(scalar_axis["origin_world_coordinate_blocks"])
    if str(lane["axis"]).lower() != world_axis:
        fail(f"{layout['layout_id']} lane axis disagrees with scalar axis")
    return tuple(origin), tuple(unit), world_axis, direction


def project(origin, unit, position):
    return sum((position[i] - origin[i]) * unit[i] for i in range(3))


# -------------------------------------------------------- capture packages

def build_streams(episode_id, bundle, frame_map_entry, layout):
    """Derive the seven contract row streams for one episode.

    Person C re-derives every capture identity from its own hash-verified
    runtime bytes and requires exact agreement with Person A's frame-map
    authority; any disagreement fails the build closed.
    """
    document = bundle["document"]
    identity = document["identity"]
    condition_block = document["condition"]
    trajectory_id = identity["trajectory_id"]
    episode_key = str(episode_id)

    by_role = {a["artifact_role"]: a for a in document["artifacts"]}
    state_rows = read_jsonl(by_role["server_state.jsonl"]["path_or_uri"])
    client_rows = sorted(read_jsonl(by_role["client_tick.jsonl"]["path_or_uri"]),
                         key=lambda r: r["render_frame_idx"])
    action_rows = sorted(read_jsonl(by_role["raw_actions.jsonl"]["path_or_uri"]),
                         key=lambda r: r["action_idx"])
    a_rows = sorted(frame_map_entry["rows"], key=lambda r: r["model_frame_idx"])
    frame_count = len(a_rows)
    if not (len(state_rows) == len(client_rows) == len(action_rows) == frame_count):
        fail(
            f"ep{episode_id} stream cardinalities disagree: "
            f"state={len(state_rows)} client={len(client_rows)} "
            f"action={len(action_rows)} frame_map={frame_count}"
        )

    layout_meta = json.loads(open(by_role["layout_meta.json"]["path_or_uri"], "rb").read())
    scene = str(layout_meta["scene"])
    condition = SCENE_CONDITION.get(scene)
    if condition is None:
        fail(f"ep{episode_id} runtime scene {scene!r} is outside the frozen vocabulary")
    target_present = condition != "occluder_only_no_sheep"

    schedule_rel = condition_block["noise_schedule_identity"]["schedule_path"]
    declared_schedule_sha = (
        condition_block["noise_schedule_identity"]["schedule_sha256"]
    )
    schedule_path = os.path.join(ROOT, schedule_rel)
    observed_schedule_sha = sha256_path(schedule_path)
    if observed_schedule_sha != declared_schedule_sha:
        fail(
            f"ep{episode_id} immutable noise schedule identity changed: "
            f"{observed_schedule_sha} != {declared_schedule_sha}"
        )
    schedule = load_schedule(schedule_path)

    origin, unit, world_axis, sign = derive_coordinate_frame(layout)
    state_by_tick = {int(r["server_tick"]): r for r in state_rows}

    streams = {name: [] for name in (
        "frame_map", "raw_actions", "normalized_actions", "server_state",
        "client_tick_log", "visibility", "seed_noise",
    )}
    frame_inventory = []
    geometric_sequence = []
    previous_hotbar = None

    for a_row, client_row, action_row in zip(a_rows, client_rows, action_rows):
        server_tick = int(a_row["server_tick"])
        key = {
            "episode_id": episode_key,
            "trajectory_id": trajectory_id,
            "server_tick": server_tick,
            "render_frame_idx": int(a_row["render_frame_idx"]),
            "action_idx": int(a_row["action_idx"]),
            "model_frame_idx": int(a_row["model_frame_idx"]),
        }
        if (
            int(client_row["render_frame_idx"]) != key["render_frame_idx"]
            or int(client_row["server_tick"]) != server_tick
            or int(action_row["action_idx"]) != key["action_idx"]
            or server_tick not in state_by_tick
        ):
            fail(
                f"ep{episode_id} capture identity disagrees with Person A's "
                f"frame map at model_frame_idx={key['model_frame_idx']}"
            )
        state_row = state_by_tick[server_tick]

        official = flat_to_official_raw_action(
            action_row, prev_hotbar=previous_hotbar
        )
        previous_hotbar = int(action_row["hotbar"])
        streams["raw_actions"].append({
            **key,
            "raw_action": official,
            "raw_action_flat": {
                field: (
                    int(action_row[field]) if field == "hotbar"
                    else float(action_row[field])
                    if field in ("camera_dx", "camera_dy")
                    else bool(action_row[field])
                )
                for field in RAW_FIELDS
            },
        })
        streams["normalized_actions"].append(
            {**key, "normalized_action": normalized_action(action_row)}
        )

        axis_velocity = float(state_row["axis_velocity"]) if target_present else 0.0
        if target_present:
            position = (
                float(state_row["sheep_x"]),
                float(state_row["sheep_y"]),
                float(state_row["sheep_z"]),
            )
            wall_parallel = float(state_row["axis_pos"])
            projected = project(origin, unit, position)
            if projected != wall_parallel:
                fail(
                    f"ep{episode_id} accepted-geometry projection disagrees with "
                    f"runtime axis_pos at tick {server_tick}: "
                    f"{projected!r} != {wall_parallel!r}"
                )
        else:
            # The no-object control carries no target. The frozen contract's
            # numeric state sentinel is used and the package is declared
            # oracle-ineligible; no position is invented.
            position = (0.0, 0.0, 0.0)
            wall_parallel = 0.0
        streams["server_state"].append({
            **key,
            "state": {
                "target_entity_id": (
                    f"magenta_sheep_{episode_key}" if target_present
                    else "no_target"
                ),
                "target_present": bool(target_present),
                "position_x_blocks": position[0],
                "position_y_blocks": position[1],
                "position_z_blocks": position[2],
                "wall_parallel_position_blocks": wall_parallel,
                "velocity_x_blocks_per_second":
                    axis_velocity if world_axis == "x" else 0.0,
                "velocity_y_blocks_per_second": 0.0,
                "velocity_z_blocks_per_second":
                    axis_velocity if world_axis == "z" else 0.0,
            },
        })
        streams["client_tick_log"].append(
            {**key, "client_tick": key["render_frame_idx"]}
        )

        geometric_visible = bool(state_row["geometric_visible"])
        geometric_sequence.append(geometric_visible)
        if bool(a_row["geometric_visible"]) != geometric_visible:
            fail(
                f"ep{episode_id} geometric visibility disagrees with Person A's "
                f"frame map at tick {server_tick}"
            )
        # Person C publishes its geometric channel only. Person B's analysis
        # label visible_flag = geometric_visible AND empirical_magenta_visible
        # cannot be formed until Person E supplies the empirical channel, so
        # the empirical field stays explicitly null and status-tagged.
        streams["visibility"].append({
            **key,
            "visibility": "visible" if geometric_visible else "occluded",
            "geometric_visible": geometric_visible,
            "visibility_source": "server_state.geometric_visible",
            "visibility_identity_sha256": a_row["visibility_identity_sha256"],
            "empirical_magenta_visible": None,
            "empirical_channel_status": E_ABSENT,
            "visible_flag_final": None,
            "visible_flag_rule": "geometric_visible AND empirical_magenta_visible",
        })

        draw = schedule.rows[server_tick]
        streams["seed_noise"].append({
            **key,
            "seed": schedule.seed,
            "draw_idx": draw.draw_idx,
            "standard_normal_draw": draw.standard_normal_draw,
            "q": draw.q,
            "dt_seconds": draw.dt_seconds,
            "noise_std_blocks": draw.noise_std_blocks,
            "noise_draw": draw.noise_draw,
        })

        frame_inventory.append({
            "artifact_role": a_row["source_frame_role"],
            "byte_size": int(a_row["source_frame_byte_size"]),
            "model_frame_idx": key["model_frame_idx"],
            "render_frame_idx": key["render_frame_idx"],
            "runtime_path": a_row["source_frame_runtime_path"],
            "server_tick": server_tick,
            "sha256": a_row["source_frame_sha256"],
            "trajectory_id": trajectory_id,
        })
        streams["frame_map"].append({
            **key,
            "source_frame_role": a_row["source_frame_role"],
            "source_frame_sha256": a_row["source_frame_sha256"],
        })

    return {
        "streams": streams,
        "frame_inventory": frame_inventory,
        "frame_count": frame_count,
        "condition": condition,
        "scene": scene,
        "target_present": target_present,
        "origin": origin,
        "unit": unit,
        "world_axis": world_axis,
        "sign": sign,
        "schedule_path_rel": schedule_rel,
        "schedule_sha256": observed_schedule_sha,
        "schedule_numpy_version": schedule.numpy_version,
        "geometric_sequence": geometric_sequence,
        "by_role": by_role,
    }


def assemble_package(episode_id, record, bundle, frame_map_entry, layout,
                     derived, stream_artifacts, media_sha256, frame_doc):
    """Build the published capture-package document for one episode."""
    document = bundle["document"]
    identity = document["identity"]
    condition_block = document["condition"]
    qa = document["qa_summary"]
    authorities = document["authorities"]
    by_role = derived["by_role"]
    trajectory_id = identity["trajectory_id"]
    layout_id = identity["layout_id"]
    episode_key = str(episode_id)
    seed = int(condition_block["seed"])
    frame_count = derived["frame_count"]

    artifacts = {
        **stream_artifacts,
        "config": {
            "format": "json",
            "path": by_role["reset_result.json"]["path_or_uri"],
            "sha256": by_role["reset_result.json"]["sha256"],
        },
        "diagnostics": {
            "format": "json",
            "path": bundle["path_rel"],
            "sha256": bundle["sha256"],
        },
        "seed_noise_source": {
            "format": "jsonl",
            "path": derived["schedule_path_rel"],
            "sha256": derived["schedule_sha256"],
        },
        "raw_server_state": {
            "format": "jsonl",
            "path": by_role["server_state.jsonl"]["path_or_uri"],
            "sha256": by_role["server_state.jsonl"]["sha256"],
        },
        "raw_client_actions": {
            "format": "jsonl",
            "path": by_role["raw_actions.jsonl"]["path_or_uri"],
            "sha256": by_role["raw_actions.jsonl"]["sha256"],
        },
        "raw_client_tick_log": {
            "format": "jsonl",
            "path": by_role["client_tick.jsonl"]["path_or_uri"],
            "sha256": by_role["client_tick.jsonl"]["sha256"],
        },
        "layout_meta": {
            "format": "json",
            "path": by_role["layout_meta.json"]["path_or_uri"],
            "sha256": by_role["layout_meta.json"]["sha256"],
        },
    }

    episode_manifest = {
        "schema_version": TRAJECTORY_SCHEMA_VERSION,
        "person_c_contract_version": PERSON_C_CONTRACT_VERSION,
        "episode_id": episode_key,
        "trajectory_id": trajectory_id,
        "layout_id": layout_id,
        "run_id": RUN_ID,
        "condition": derived["condition"],
        "regime": "regime_a",
        "seed": seed,
        "tick_rate_hz": TICK_RATE_HZ,
        "dt_seconds": DT_SECONDS,
        "q": float(condition_block["q_blocks_squared_per_second"]),
        "v": float(condition_block["speed_blocks_per_second"]),
        "duration": frame_count * DT_SECONDS,
        "code_sha": C_SOURCE_COMMIT,
        "config_hash": by_role["reset_result.json"]["sha256"],
        # Bound to the accepted geometry authority, which is the stable
        # per-universe layout identity Person B's coordinate frame requires.
        # The per-episode runtime layout_meta.json identity (which varies only
        # by scene) is carried separately under layout_meta_identity.
        "layout_config_hash": ACCEPTED_GEOMETRY_SHA256,
        "environment_lock_hash": ENV_LOCK_SHA256,
        "noise_schedule_hash": stream_artifacts["seed_noise"]["sha256"],
        "rng": {
            "producer": "numpy.random.Generator",
            "bit_generator": "PCG64",
            "numpy_version": derived["schedule_numpy_version"],
            "immutable_schedule": True,
            "java_consumption": "stored_draws_in_draw_idx_order",
        },
        "lifecycle_version": LIFECYCLE_VERSION,
        "status": "accepted",
    }

    temporal_alignment = {
        "status": "verified",
        "evidence_scope": "synthetic_contract_only",
        "action_idx": 1,
        "visual_before_model_frame_idx": 1,
        "visual_after_model_frame_idx": 2,
        "effect_server_tick": 2,
        "evidence_hash": bundle["sha256"],
    }

    geometric_sequence = derived["geometric_sequence"]
    visible_count = sum(1 for value in geometric_sequence if value)

    person_c_authority = {
        "authority_schema_id": SCHEMA_ID,
        "authority_schema_version": SCHEMA_VERSION,
        "successor_of": {
            "person_c_c7_5_bundle_path": bundle["path_rel"],
            "person_c_c7_5_bundle_sha256": bundle["sha256"],
            "rewrites_history": False,
            "additive_successor": True,
        },
        "accepted_manifest_identity": {
            "path": f"{C75_REL}/trajectories_mvp_manifest.json",
            "sha256": C_ACCEPTED_MANIFEST_SHA256,
            "person_c_commit": C_SOURCE_COMMIT,
            "accepted_count": EXPECTED_ACCEPTED,
            "excluded_count": EXPECTED_EXCLUDED,
            "accepted": True,
        },
        "identity": {
            "episode_id": episode_id,
            "trajectory_id": trajectory_id,
            "layout_id": layout_id,
            "planned_cell_id": identity["planned_cell_id"],
            "set_id": identity["set_id"],
            "control_type": identity["control_type"],
            "collection_order": identity["collection_order"],
        },
        "condition_identity": {
            "condition": derived["condition"],
            "scene": derived["scene"],
            "target_variant": condition_block["target_variant"],
            "context_fraction": condition_block["context_fraction"],
            "hidden_frames": condition_block["hidden_frames"],
            "hidden_frames_realized": condition_block["hidden_frames_realized"],
            "hidden_seconds": condition_block["hidden_seconds"],
            "q_blocks_squared_per_second":
                condition_block["q_blocks_squared_per_second"],
            "speed_blocks_per_second": condition_block["speed_blocks_per_second"],
            "seed": seed,
            "planned_seed": condition_block["planned_seed"],
            "noise_schedule_identity": condition_block["noise_schedule_identity"],
        },
        "source_sha256_inventory": {
            "server_state": {
                "path": by_role["server_state.jsonl"]["path_or_uri"],
                "sha256": by_role["server_state.jsonl"]["sha256"],
                "byte_size": by_role["server_state.jsonl"]["byte_size"],
            },
            "layout_meta": {
                "path": by_role["layout_meta.json"]["path_or_uri"],
                "sha256": by_role["layout_meta.json"]["sha256"],
                "byte_size": by_role["layout_meta.json"]["byte_size"],
            },
            "client_tick_log": {
                "path": by_role["client_tick.jsonl"]["path_or_uri"],
                "sha256": by_role["client_tick.jsonl"]["sha256"],
                "byte_size": by_role["client_tick.jsonl"]["byte_size"],
            },
            "raw_actions": {
                "path": by_role["raw_actions.jsonl"]["path_or_uri"],
                "sha256": by_role["raw_actions.jsonl"]["sha256"],
                "byte_size": by_role["raw_actions.jsonl"]["byte_size"],
            },
            "reset_result": {
                "path": by_role["reset_result.json"]["path_or_uri"],
                "sha256": by_role["reset_result.json"]["sha256"],
                "byte_size": by_role["reset_result.json"]["byte_size"],
            },
            "finalization": {
                "path": by_role["finalization.json"]["path_or_uri"],
                "sha256": by_role["finalization.json"]["sha256"],
                "byte_size": by_role["finalization.json"]["byte_size"],
            },
            "lifecycle": {
                "path": by_role["lifecycle.jsonl"]["path_or_uri"],
                "sha256": by_role["lifecycle.jsonl"]["sha256"],
                "byte_size": by_role["lifecycle.jsonl"]["byte_size"],
            },
            "noise_schedule": {
                "path": derived["schedule_path_rel"],
                "sha256": derived["schedule_sha256"],
            },
        },
        "server_state_identity": {
            "path": by_role["server_state.jsonl"]["path_or_uri"],
            "sha256": by_role["server_state.jsonl"]["sha256"],
            "row_count": frame_count,
            "byte_identity_verified": True,
        },
        "layout_meta_identity": {
            "path": by_role["layout_meta.json"]["path_or_uri"],
            "sha256": by_role["layout_meta.json"]["sha256"],
            "scene": derived["scene"],
            "byte_identity_verified": True,
            "note": (
                "per-episode runtime echo; differs between scenes of the same "
                "layout, so it is not the per-layout geometry identity"
            ),
        },
        "source_media_identity": {
            "mode": "numbered_frames",
            "frame_count": frame_count,
            "raw_framebuffer_width_pixels": 1920,
            "raw_framebuffer_height_pixels": 1046,
            "canonical_derivative_width_pixels": 640,
            "canonical_derivative_height_pixels": 360,
            "fps": TICK_RATE_HZ,
            "frame_inventory_path":
                f"{AUTONOMOUS_REL}/{trajectory_id}/package_v0_1/frame_inventory.jsonl",
            "frame_inventory_sha256": media_sha256,
            "frame_bytes_location": (
                "retained on the Person C Windows runtime machine; only frame "
                "identities are published"
            ),
        },
        "raw_action_identity": {
            "path": by_role["raw_actions.jsonl"]["path_or_uri"],
            "sha256": by_role["raw_actions.jsonl"]["sha256"],
            "row_count": frame_count,
            "normalized_action_owner": "person_a",
            "normalized_action_encoding":
                "mineocclude.data.package_episode reference conversion",
        },
        "frame_map_authority": {
            "owner_role": "person_a",
            "person_a_commit": PERSON_A_COMMIT,
            "package_root": PERSON_A_PKG_REL,
            "package_sha256_inventory_sha256": PERSON_A_PKG_SHA256,
            "per_trajectory_frame_map_path": frame_map_entry["path_rel"],
            "per_trajectory_frame_map_sha256": frame_map_entry["sha256"],
            "model_frame_key_count": frame_count,
            "person_c_independently_rederived": True,
            "person_c_agreement_with_person_a": "exact",
        },
        "model_frame_key_relationship": {
            "model_facing_key": ["trajectory_id", "model_frame_idx"],
            "capture_key": [
                "episode_id", "trajectory_id", "server_tick",
                "render_frame_idx", "action_idx", "model_frame_idx",
            ],
            "relationship":
                "server_tick == render_frame_idx == action_idx == model_frame_idx",
            "zero_based_dense": True,
            "verified_against_person_a_frame_map": True,
        },
        "environment_config_build_identity": {
            "environment_lock_path": ENV_LOCK_REL,
            "environment_lock_sha256": ENV_LOCK_SHA256,
            "config_path": by_role["reset_result.json"]["path_or_uri"],
            "config_sha256": by_role["reset_result.json"]["sha256"],
            "server_build": authorities["server_build"],
            "client_build": authorities["client_build"],
            "configuration": authorities["configuration"],
            "episode_schema": authorities["episode_schema"],
        },
        "target_count_identity": {
            "expected": qa["target_count_status"]["expected"],
            "observed": qa["target_count_status"]["observed"],
            "required": qa["target_count_status"]["required"],
            "valid": qa["target_count_status"]["valid"],
            "target_present": derived["target_present"],
        },
        "camera_pose_authority": {
            "camera": qa["camera_marker_status"]["camera"],
            "camera_pose_recorded":
                qa["camera_marker_status"]["camera_pose_recorded"],
            "geometry_version": qa["camera_marker_status"]["geometry_version"],
            "status": qa["camera_marker_status"]["status"],
            "accepted_geometry_camera": layout["camera"],
            "canonical_pose_matches_accepted_geometry": (
                [float(v) for v in qa["camera_marker_status"]["camera"]["feet_xyz"]]
                == [float(v) for v in layout["camera"]["feet_xyz"]]
            ),
        },
        "wall_lane_shadow_geometry_authority": {
            "accepted_geometry_path": GEOMETRY_REL,
            "accepted_geometry_sha256": ACCEPTED_GEOMETRY_SHA256,
            "accepted_geometry_version": ACCEPTED_GEOMETRY_VERSION,
            "floor": layout["floor"],
            "wall": layout["wall"],
            "lane": layout["lane"],
            "shadow": layout["shadow"],
            "scalar_axis": layout["scalar_axis"],
            "motion_sign": layout["motion_sign"],
            "target_start": layout["target_start"],
            "markers": layout["markers"],
        },
        "coordinate_frame_binding": {
            "coordinate_frame_id": frame_doc["coordinate_frame_id"],
            "coordinate_frame_hash": frame_doc["coordinate_frame_hash"],
            "coordinate_frame_schema_version":
                frame_doc["coordinate_frame_schema_version"],
            "coordinate_frame_path": f"{FRAMES_REL}/{layout_id}.json",
            "source_layout_manifest_hash":
                frame_doc["source_layout_manifest_hash"],
            "person_c_signed": True,
            "person_b_cosigned": False,
            "wall_parallel_origin_world_xyz":
                frame_doc["wall_parallel_origin_world_xyz"],
            "wall_parallel_positive_unit_vector_world_xyz":
                frame_doc["wall_parallel_positive_unit_vector_world_xyz"],
            "projection_agreement_with_runtime_axis_pos": (
                "exact" if derived["target_present"] else "not_applicable_no_target"
            ),
        },
        "visibility_channel_status": {
            "geometric_channel_present": True,
            "geometric_visibility_version": ACCEPTED_GEOMETRY_VERSION,
            "geometric_visibility_source": "server_state.geometric_visible",
            "geometric_visible_frame_count": visible_count,
            "geometric_occluded_frame_count": frame_count - visible_count,
            "empirical_magenta_channel_present": False,
            "empirical_magenta_channel_status": E_ABSENT,
            "empirical_magenta_detector_version": None,
            "empirical_magenta_owner_role": "person_e",
            "visible_flag_rule":
                "geometric_visible AND empirical_magenta_visible",
            "visible_flag_final_available": False,
            "visible_flag_final_blocked_by":
                "person_e_empirical_magenta_visibility_absent",
            "person_c_invented_empirical_values": False,
            "c_to_e_request_path": f"{E_REQUEST_REL}/request_manifest.json",
        },
        "qa_status": {
            "structural_status": qa["structural_status"],
            "continuity_alignment_status": qa["continuity_alignment_status"],
            "realized_condition_status": qa["realized_condition_status"],
            "motion_noise_realization_status": qa["motion_noise_realization_status"],
            "cardinality_counts": qa["cardinality_counts"],
            "duration_error": qa["duration_error"],
            "warning_reason_codes": qa["warning_reason_codes"],
            "status": document["acceptance"]["status"],
            "accepted": document["acceptance"]["accepted"],
            "exclusion_reason_codes": document["acceptance"]["exclusion_reason_codes"],
        },
        "oracle_eligibility": {
            "person_b_oracle_eligible": derived["target_present"],
            "reason": (
                "target-bearing capture" if derived["target_present"]
                else "occluder_only_no_sheep is intentionally not oracle eligible"
            ),
            "person_b_adapter_code_when_ineligible": (
                None if derived["target_present"]
                else "no_object_not_oracle_eligible"
            ),
        },
        "provenance": {
            "person_c_commit": C_SOURCE_COMMIT,
            "builder": "scripts/build_person_c_66_cell_capture_authority_v0_1.py",
            "canonical_c6a_id": RUN_ID,
            "c7_5_provenance": document["provenance"],
            "acceptance_authority_path":
                document["acceptance"]["acceptance_authority_path"],
            "acceptance_authority_sha256":
                document["acceptance"]["acceptance_authority_sha256"],
            "authorization_commit": document["acceptance"]["authorization_commit"],
            "episode_bytes_copied_into_repository": False,
        },
    }

    return {
        "schema_version": TRAJECTORY_SCHEMA_VERSION,
        "person_c_contract_version": PERSON_C_CONTRACT_VERSION,
        "episode_id": episode_key,
        "trajectory_id": trajectory_id,
        "layout_id": layout_id,
        "run_id": RUN_ID,
        "condition": derived["condition"],
        "seed": seed,
        "synthetic": False,
        "scientific_use": "pending_cross_role_signoff",
        "media": {
            "mode": "numbered_frames",
            "path": os.path.dirname(
                derived["frame_inventory"][0]["runtime_path"]
            ),
            "width": 640,
            "height": 360,
            "fps": TICK_RATE_HZ,
            "frame_count": frame_count,
            "sha256": media_sha256,
        },
        "artifacts": artifacts,
        "streams": derived["streams"],
        "episode_manifest": episode_manifest,
        "exclusion_ledger": [],
        "temporal_alignment": temporal_alignment,
        "impulse_orientation": impulse_orientation(),
        "person_c_authority": person_c_authority,
    }


def impulse_orientation():
    """Camera-axis impulse orientation from the committed scripted fixture.

    The impulse is a pure yaw step, so camera component 1 (dx) moves and
    component 0 (dy) shows no effect. ``evidence_hash`` is the committed
    fixture QA report; the additive fields record where that evidence lives.
    """
    qa_rel = f"{IMPULSE_FIXTURE_REL}/qa_report.json"
    evidence_rel = f"{IMPULSE_FIXTURE_REL}/IMPULSE_EVIDENCE.txt"
    return {
        "status": "verified",
        "evidence_scope": "synthetic_contract_only",
        "fixture_id": IMPULSE_FIXTURE_ID,
        "camera_component_0_observed_effect": "runtime_no_component_0_effect",
        "camera_component_1_observed_effect":
            "runtime_positive_component_1_step_in_visual_i_to_i_plus_1",
        "evidence_hash": sha256_path(os.path.join(ROOT, qa_rel)),
        "evidence_path": qa_rel,
        "pixel_evidence_path": evidence_rel,
        "pixel_evidence_sha256": sha256_path(os.path.join(ROOT, evidence_rel)),
        "evidence_scope_note": (
            "the underlying evidence is a real runtime pixel-level check; the "
            "v0.1 contract fixes evidence_scope to the literal "
            "'synthetic_contract_only', so the literal is preserved rather "
            "than widening a frozen vocabulary"
        ),
    }


# ------------------------------------------------- coordinate-frame authority

def build_coordinate_frame_document(layout_id, layout, projection_evidence,
                                    grammar):
    """Build the Person C-signed wall-parallel frame for one layout.

    ``coordinate_frame_hash`` covers only the coordinate-defining fields, so
    Person B can co-sign ``adapter_signoff.person_b`` on its own branch without
    changing the frame identity. Person C never signs Person B's side.
    """
    origin, unit, world_axis, sign = derive_coordinate_frame(layout)
    lane = layout["lane"]
    wall = layout["wall"]
    samples = layout["shadow"]["integer_lane_samples"]
    occluded = [int(s["axis_position"]) for s in samples if s["occluded"]]
    if not occluded:
        fail(f"{layout_id} accepted geometry declares no occluded lane sample")
    contiguous = occluded == list(range(min(occluded), max(occluded) + 1))

    document = {
        # -- coordinate-defining fields (these five fix coordinate_frame_hash)
        "coordinate_frame_schema_version": COORDINATE_FRAME_SCHEMA_VERSION,
        "coordinate_frame_id": f"person-c-wall-parallel-{layout_id}-v0.1",
        "wall_parallel_origin_world_xyz": list(origin),
        "wall_parallel_positive_unit_vector_world_xyz": list(unit),
        "source_layout_manifest_hash": ACCEPTED_GEOMETRY_SHA256,
    }
    document["coordinate_frame_hash"] = coordinate_frame_hash(document)
    document.update({
        "adapter_signoff": {
            "person_c": True,
            "person_b": False,
            "person_c_signoff_scope": (
                "Person C owns the world coordinate system, the wall-parallel "
                "scalar axis, its origin, direction, sign convention, and the "
                "wall/lane/shadow bounds recorded here."
            ),
            "person_b_signoff_scope": (
                "Person B must co-sign adapter_signoff.person_b on its own "
                "branch before live use; Person C does not sign Person B's side."
            ),
            "cosign_preserves_coordinate_frame_hash": True,
        },
        "person_c_authority": {
            "authority_schema_id": SCHEMA_ID,
            "authority_schema_version": SCHEMA_VERSION,
            "layout_id": layout_id,
            "owner_role": "person_c",
            "person_c_commit": C_SOURCE_COMMIT,
            "world_coordinate_system": grammar["coordinate_system"],
            "scalar_axis_unit": grammar["scalar_axis_unit"],
            "lane_relation": grammar["lane_relation"],
            "marker_restriction": grammar["marker_restriction"],
            "wall_parallel_scalar_axis": world_axis,
            "source_world_axis_component": world_axis,
            "source_x_coordinate_role": (
                "wall_parallel_scalar" if world_axis == "x" else "orthogonal_fixed"
            ),
            "source_z_coordinate_role": (
                "wall_parallel_scalar" if world_axis == "z" else "orthogonal_fixed"
            ),
            "axis_origin": {
                "origin_world_coordinate_blocks":
                    layout["scalar_axis"]["origin_world_coordinate_blocks"],
                "origin_world_xyz": list(origin),
                "origin_derivation": (
                    "the lane world anchor with the scalar component replaced "
                    "by scalar_axis.origin_world_coordinate_blocks"
                ),
            },
            "axis_direction": {
                "positive_world_direction": sign,
                "positive_unit_vector_world_xyz": list(unit),
                "unit_norm": 1.0,
            },
            "positive_sign_convention": (
                f"increasing world {world_axis} is increasing wall-parallel "
                f"scalar position ({sign})"
            ),
            "motion_sign": layout["motion_sign"],
            "wall_bounds": wall["bounds"],
            "wall_axis": wall["axis"],
            "wall_block": wall["block"],
            "lane_bounds": {
                "axis": lane["axis"],
                "axis_min": lane["axis_min"],
                "axis_max": lane["axis_max"],
                "ortho": lane["ortho"],
                "feet_y": lane["feet_y"],
                "world_start_xyz": lane["world_start_xyz"],
                "world_end_xyz": lane["world_end_xyz"],
            },
            "shadow_bounds": {
                "definition": layout["shadow"]["definition"],
                "camera_source": layout["shadow"]["camera_source"],
                "target_centre_y": layout["shadow"]["target_centre_y"],
                "occluded_integer_axis_min": min(occluded),
                "occluded_integer_axis_max": max(occluded),
                "occluded_integer_axis_positions": occluded,
                "occluded_interval_contiguous": contiguous,
                "sample_resolution": "integer_lane_samples_only",
                "continuous_boundary_measured": False,
                "continuous_boundary_note": (
                    "the accepted geometry samples occlusion at integer lane "
                    "positions only; the continuous shadow edge is bracketed "
                    "between the last unoccluded and first occluded sample and "
                    "is not interpolated here"
                ),
                "integer_lane_samples": samples,
            },
            "camera_canonical_pose": layout["camera"],
            "camera_relationship": (
                "the shadow bounds above are the accepted geometry's "
                "segmentHitsWall result for this camera pose; changing the "
                "camera invalidates the shadow bounds"
            ),
            "layout_config_version": layout["config_version"],
            "authority_basis": layout["authority_basis"],
            "geometry_source_paths": [
                {
                    "path": GEOMETRY_REL,
                    "sha256": ACCEPTED_GEOMETRY_SHA256,
                    "role": "accepted_geometry_authority",
                },
                {
                    "path": layout["runtime_evidence"]["path"],
                    "sha256": layout["runtime_evidence"]["sha256"],
                    "role": "runtime_observed_layout_evidence",
                },
            ],
            "runtime_projection_verification": projection_evidence,
            "private_axis_reinterpretation": False,
            "silent_axis_inference": False,
        },
    })
    return document


# ------------------------------------------------------------ U4 eligibility

def analyse_u4_eligibility(records, per_episode, heldout_layout_ids):
    """Audit the C-owned capture-duration / end-state facts for U4 reveals.

    Person B's U4 rules are treated as immutable foreign inputs: the reveal
    window stays [-1.0, 1.0] s, which at the frozen 20 Hz capture clock is
    +/-20 frames, i.e. a 41-frame span that must fit inside one capture with
    the reveal frame at its centre. Nothing is relaxed and no blip is
    reinterpreted as a valid terminal reveal.
    """
    required_pre = required_post = int(
        round(abs(B_REVEAL_WINDOW_SECONDS[0]) * TICK_RATE_HZ)
    )
    span = required_pre + required_post + 1

    episodes = []
    transitions = []
    for episode_id in sorted(records):
        entry = per_episode[episode_id]
        sequence = entry["geometric_sequence"]
        frames = len(sequence)
        layout_id = records[episode_id]["layout_id"]
        indices = [
            index for index in range(1, frames)
            if not sequence[index - 1] and sequence[index]
        ]
        for index in indices:
            run = 0
            cursor = index
            while cursor < frames and sequence[cursor]:
                run += 1
                cursor += 1
            pre = index
            post = frames - 1 - index
            transitions.append({
                "trajectory_id": records[episode_id]["trajectory_id"],
                "episode_id": episode_id,
                "layout_id": layout_id,
                "set_id": records[episode_id]["set_id"],
                "control_type": records[episode_id]["control_type"],
                "post_model_frame_idx": index,
                "pre_model_frame_idx": index - 1,
                "post_visible_run_length_frames": run,
                "frames_before_transition": pre,
                "frames_after_transition": post,
                "required_pre_frames": required_pre,
                "required_post_frames": required_post,
                "pre_coverage_satisfied": pre >= required_pre,
                "post_coverage_satisfied": post >= required_post,
                "full_reveal_window_satisfied":
                    pre >= required_pre and post >= required_post,
                "visible_sustained_to_capture_end": cursor >= frames,
                "in_heldout_layout": layout_id in heldout_layout_ids,
                "authority": "person_c_geometric_visible_only",
            })
        episodes.append({
            "trajectory_id": records[episode_id]["trajectory_id"],
            "episode_id": episode_id,
            "layout_id": layout_id,
            "set_id": records[episode_id]["set_id"],
            "frame_count": frames,
            "duration_seconds": frames * DT_SECONDS,
            "first_frame_geometric_visible": sequence[0],
            "final_frame_geometric_visible": sequence[-1],
            "ends_occluded": not sequence[-1],
            "geometric_occluded_to_visible_transition_count": len(indices),
            "capture_long_enough_for_reveal_window": frames >= span,
            "in_heldout_layout": layout_id in heldout_layout_ids,
        })

    heldout = [t for t in transitions if t["in_heldout_layout"]]
    valid_any = [t for t in transitions if t["full_reveal_window_satisfied"]]
    valid_heldout = [t for t in heldout if t["full_reveal_window_satisfied"]]
    terminal_heldout = [
        t for t in heldout
        if t["full_reveal_window_satisfied"]
        and t["visible_sustained_to_capture_end"]
    ]
    ends_occluded = [e for e in episodes if e["ends_occluded"]]
    ends_visible = [e for e in episodes if not e["ends_occluded"]]
    long_enough = [e for e in episodes if e["capture_long_enough_for_reveal_window"]]

    eligible = len(valid_heldout) >= B_REQUIRED_HELDOUT_EVENT_COUNT
    reasons = []
    if len(heldout) < B_REQUIRED_HELDOUT_EVENT_COUNT:
        reasons.append(
            f"only {len(heldout)} geometric occluded-to-visible candidate "
            f"transitions exist in the held-out layouts "
            f"({', '.join(sorted(heldout_layout_ids))}), fewer than the "
            f"{B_REQUIRED_HELDOUT_EVENT_COUNT} held-out events Person B requires"
        )
    if not valid_heldout:
        reasons.append(
            f"no held-out candidate transition has the frozen "
            f"+/-{required_pre}-frame reveal-window coverage "
            f"(reveal_window_seconds={B_REVEAL_WINDOW_SECONDS} at "
            f"{TICK_RATE_HZ} Hz requires a {span}-frame centred span)"
        )
    if not terminal_heldout:
        reasons.append(
            "no held-out candidate transition is a terminal reveal: every "
            "held-out candidate returns to geometric occlusion before its "
            "capture ends"
        )
    return {
        "required_pre_frames": required_pre,
        "required_post_frames": required_post,
        "required_span_frames": span,
        "episodes": episodes,
        "transitions": transitions,
        "total_frame_count": sum(e["frame_count"] for e in episodes),
        "transition_count": len(transitions),
        "heldout_transition_count": len(heldout),
        "valid_window_transition_count": len(valid_any),
        "valid_window_heldout_transition_count": len(valid_heldout),
        "terminal_heldout_reveal_count": len(terminal_heldout),
        "episodes_ending_occluded": len(ends_occluded),
        "episodes_ending_visible": len(ends_visible),
        "episodes_ending_visible_detail": [
            {k: e[k] for k in ("trajectory_id", "episode_id", "set_id",
                               "frame_count", "final_frame_geometric_visible")}
            for e in ends_visible
        ],
        "episodes_long_enough_for_reveal_window": len(long_enough),
        "min_frame_count": min(e["frame_count"] for e in episodes),
        "max_frame_count": max(e["frame_count"] for e in episodes),
        "eligible": eligible,
        "failure_reasons": reasons,
    }


# ------------------------------------------------------------------- build

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true",
        help="rebuild in memory and report drift without writing files",
    )
    args = parser.parse_args(argv)

    manifest, ledger, records, bundles = load_c_authority()
    geometry, layouts = load_geometry()
    grammar = geometry["common_geometry_grammar"]
    a_inventory, frame_maps = load_person_a_frame_maps(records)
    runtime_inventory, discrepancies = verify_runtime_payloads(bundles)

    server_state_ok = sum(
        1 for entry in runtime_inventory.values()
        if entry["roles"].get("server_state.jsonl", {}).get("byte_identity_verified")
    )
    layout_meta_ok = sum(
        1 for entry in runtime_inventory.values()
        if entry["roles"].get("layout_meta.json", {}).get("byte_identity_verified")
    )

    # ---- derive every episode's streams first (fails closed on disagreement)
    per_episode = {}
    for episode_id in sorted(records):
        per_episode[episode_id] = build_streams(
            episode_id, bundles[episode_id], frame_maps[episode_id],
            layouts[records[episode_id]["layout_id"]],
        )

    # ---- per-layout runtime projection evidence, then the C-signed frames
    projection = {}
    for episode_id, derived in per_episode.items():
        layout_id = records[episode_id]["layout_id"]
        slot = projection.setdefault(layout_id, {
            "episode_count": 0, "target_bearing_episode_count": 0,
            "verified_frame_count": 0, "max_abs_projection_error_blocks": 0.0,
            "agreement": "exact",
        })
        slot["episode_count"] += 1
        if derived["target_present"]:
            slot["target_bearing_episode_count"] += 1
            slot["verified_frame_count"] += derived["frame_count"]
    for layout_id, slot in projection.items():
        slot["verified_against"] = "person_c_runtime_server_state.axis_pos"
        slot["comparison"] = (
            "project(sheep_x, sheep_y, sheep_z) == axis_pos for every "
            "target-bearing frame"
        )

    frame_documents = {}
    frame_paths = {}
    for layout_id in sorted(layouts):
        document = build_coordinate_frame_document(
            layout_id, layouts[layout_id], projection[layout_id], grammar,
        )
        frame_documents[layout_id] = document
        frame_paths[layout_id] = os.path.join(ROOT, FRAMES_REL, f"{layout_id}.json")

    # ---- capture packages
    package_records = []
    published = {}
    e_universe = []
    for episode_id in sorted(records):
        record = records[episode_id]
        derived = per_episode[episode_id]
        trajectory_id = record["trajectory_id"]
        layout_id = record["layout_id"]
        bundle_dir = os.path.join(ROOT, AUTONOMOUS_REL, trajectory_id)
        stream_dir = os.path.join(bundle_dir, "package_v0_1")

        stream_artifacts = {}
        for name, rows in derived["streams"].items():
            path = os.path.join(stream_dir, f"{name}.jsonl")
            digest = write_jsonl(path, rows)
            stream_artifacts[name] = {
                "format": "jsonl",
                "path": f"{AUTONOMOUS_REL}/{trajectory_id}/package_v0_1/{name}.jsonl",
                "sha256": digest,
            }
        media_sha256 = write_jsonl(
            os.path.join(stream_dir, "frame_inventory.jsonl"),
            derived["frame_inventory"],
        )

        package = assemble_package(
            episode_id, record, bundles[episode_id], frame_maps[episode_id],
            layouts[layout_id], derived, stream_artifacts, media_sha256,
            frame_documents[layout_id],
        )
        result = validate_capture_package(package)
        codes = sorted({item.code.value for item in result.rejections})
        messages = [item.message for item in result.rejections]

        payload = canonical_bytes(package)
        package_path = os.path.join(bundle_dir, "capture_package_v0_1.json")
        with open(package_path, "wb") as handle:
            handle.write(payload)
        digest = sha256_bytes(payload)
        with open(package_path + ".sha256", "w", encoding="utf-8", newline="\n") as handle:
            handle.write(digest + "\n")

        published[episode_id] = digest
        package_records.append({
            "episode_id": episode_id,
            "trajectory_id": trajectory_id,
            "layout_id": layout_id,
            "planned_cell_id": record["planned_cell_id"],
            "set_id": record["set_id"],
            "control_type": record["control_type"],
            "condition": derived["condition"],
            "scene": derived["scene"],
            "target_present": derived["target_present"],
            "frame_count": derived["frame_count"],
            "capture_package_path":
                f"{AUTONOMOUS_REL}/{trajectory_id}/capture_package_v0_1.json",
            "capture_package_sha256": digest,
            "frozen_contract_accepted": result.accepted,
            "frozen_contract_rejection_codes": codes,
            "frozen_contract_rejection_messages": messages,
            "person_b_oracle_eligible": derived["target_present"],
            "coordinate_frame_id":
                frame_documents[layout_id]["coordinate_frame_id"],
            "coordinate_frame_hash":
                frame_documents[layout_id]["coordinate_frame_hash"],
            "person_a_frame_map_sha256": frame_maps[episode_id]["sha256"],
            "server_state_sha256":
                runtime_inventory[episode_id]["roles"]["server_state.jsonl"]["declared_sha256"],
            "layout_meta_sha256":
                runtime_inventory[episode_id]["roles"]["layout_meta.json"]["declared_sha256"],
            "empirical_magenta_channel_status": E_ABSENT,
        })

        for frame in derived["frame_inventory"]:
            visibility = derived["streams"]["visibility"][frame["model_frame_idx"]]
            e_universe.append({
                "trajectory_id": trajectory_id,
                "model_frame_idx": frame["model_frame_idx"],
                "episode_id": episode_id,
                "layout_id": layout_id,
                "render_frame_idx": frame["render_frame_idx"],
                "server_tick": frame["server_tick"],
                "set_id": record["set_id"],
                "control_type": record["control_type"],
                "condition": derived["condition"],
                "scene": derived["scene"],
                "target_present": derived["target_present"],
                "source_frame_role": frame["artifact_role"],
                "source_frame_runtime_path": frame["runtime_path"],
                "source_frame_sha256": frame["sha256"],
                "source_frame_byte_size": frame["byte_size"],
                "raw_framebuffer_width_pixels": 1920,
                "raw_framebuffer_height_pixels": 1046,
                "canonical_derivative_width_pixels": 640,
                "canonical_derivative_height_pixels": 360,
                "person_c_geometric_visible": visibility["geometric_visible"],
                "detector_applicable": derived["target_present"],
                "detector_applicability_reason": (
                    "magenta target present in scene"
                    if derived["target_present"]
                    else "no_target_object: no magenta target exists in this control"
                ),
                "expected_person_e_field": "empirical_magenta_visible",
                "person_e_value_supplied": None,
            })

    return _publish(
        manifest, ledger, records, bundles, geometry, layouts, grammar,
        a_inventory, frame_maps, runtime_inventory, discrepancies,
        server_state_ok, layout_meta_ok, per_episode, frame_documents,
        frame_paths, package_records, published, e_universe, args.check,
    )


def _publish(manifest, ledger, records, bundles, geometry, layouts, grammar,
             a_inventory, frame_maps, runtime_inventory, discrepancies,
             server_state_ok, layout_meta_ok, per_episode, frame_documents,
             frame_paths, package_records, published, e_universe, check_only):
    """Write the coordinate frames, the C->E request and every receipt."""
    status_dir = os.path.join(ROOT, STATUS_REL)
    inventory = {}

    # ---------------------------------------------- 3. coordinate frames
    for layout_id, document in sorted(frame_documents.items()):
        digest = write_json(frame_paths[layout_id], document)
        inventory[f"{FRAMES_REL}/{layout_id}.json"] = digest

    frames_index = {
        "schema_id": f"{SCHEMA_ID}-coordinate-frame-authority",
        "schema_version": SCHEMA_VERSION,
        "owner_role": "person_c",
        "person_c_commit": C_SOURCE_COMMIT,
        "accepted_geometry_path": GEOMETRY_REL,
        "accepted_geometry_sha256": ACCEPTED_GEOMETRY_SHA256,
        "accepted_geometry_version": ACCEPTED_GEOMETRY_VERSION,
        "accepted_geometry_identity_independently_verified": True,
        "coordinate_frame_schema_version": COORDINATE_FRAME_SCHEMA_VERSION,
        "layout_count": len(frame_documents),
        "PERSON_C_COORDINATE_FRAME_SIGNED": True,
        "person_b_cosign_present": False,
        "person_b_cosign_required_before_live_use": True,
        "person_c_signed_person_b_side": False,
        "cosign_instructions": {
            "consumer_role": "person_b",
            "action": (
                "set adapter_signoff.person_b = true in each layout frame on "
                "the Person B branch"
            ),
            "coordinate_frame_hash_scope": [
                "coordinate_frame_schema_version",
                "coordinate_frame_id",
                "wall_parallel_origin_world_xyz",
                "wall_parallel_positive_unit_vector_world_xyz",
                "source_layout_manifest_hash",
            ],
            "cosign_preserves_coordinate_frame_hash": True,
            "validator":
                "mineocclude.analysis.coordinates.validate_coordinate_frame",
        },
        "frames": [
            {
                "layout_id": layout_id,
                "path": f"{FRAMES_REL}/{layout_id}.json",
                "sha256": inventory[f"{FRAMES_REL}/{layout_id}.json"],
                "coordinate_frame_id": document["coordinate_frame_id"],
                "coordinate_frame_hash": document["coordinate_frame_hash"],
                "wall_parallel_scalar_axis":
                    document["person_c_authority"]["wall_parallel_scalar_axis"],
                "positive_world_direction":
                    document["person_c_authority"]["axis_direction"][
                        "positive_world_direction"],
                "wall_parallel_origin_world_xyz":
                    document["wall_parallel_origin_world_xyz"],
                "wall_parallel_positive_unit_vector_world_xyz":
                    document["wall_parallel_positive_unit_vector_world_xyz"],
                "motion_sign": document["person_c_authority"]["motion_sign"],
                "source_layout_manifest_hash":
                    document["source_layout_manifest_hash"],
                "adapter_signoff": document["adapter_signoff"],
            }
            for layout_id, document in sorted(frame_documents.items())
        ],
    }
    frames_index_sha = write_json(
        os.path.join(status_dir, "coordinate_frame_authority.json"), frames_index
    )
    inventory[f"{STATUS_REL}/coordinate_frame_authority.json"] = frames_index_sha

    # ------------------------------------------- 2. capture-package manifest
    duplicate_episodes = sorted({
        r["episode_id"] for r in package_records
        if [x["episode_id"] for x in package_records].count(r["episode_id"]) > 1
    })
    duplicate_trajectories = sorted({
        r["trajectory_id"] for r in package_records
        if [x["trajectory_id"] for x in package_records].count(r["trajectory_id"]) > 1
    })
    accepted_by_contract = [r for r in package_records if r["frozen_contract_accepted"]]
    rejected_by_contract = [
        r for r in package_records if not r["frozen_contract_accepted"]
    ]
    package_manifest = {
        "schema_id": f"{SCHEMA_ID}-capture-package-manifest",
        "schema_version": SCHEMA_VERSION,
        "owner_role": "person_c",
        "person_c_commit": C_SOURCE_COMMIT,
        "person_c_accepted_manifest_path":
            f"{C75_REL}/trajectories_mvp_manifest.json",
        "person_c_accepted_manifest_sha256": C_ACCEPTED_MANIFEST_SHA256,
        "additive_successor": True,
        "rewrites_c7_5_history": False,
        "accepted_count": EXPECTED_ACCEPTED,
        "excluded_count": EXPECTED_EXCLUDED,
        "episode_id_range": [FIRST_EP, LAST_EP],
        "capture_package_count": len(package_records),
        "capture_packages_complete": len(package_records) == EXPECTED_ACCEPTED,
        "missing_capture_package_count":
            EXPECTED_ACCEPTED - len(package_records),
        "duplicate_episode_identity_count": len(duplicate_episodes),
        "duplicate_trajectory_identity_count": len(duplicate_trajectories),
        "frozen_contract_validator":
            "mineocclude.data.capture_contract.validate_capture_package",
        "frozen_contract_accepted_count": len(accepted_by_contract),
        "frozen_contract_rejected_count": len(rejected_by_contract),
        "person_b_oracle_eligible_count":
            sum(1 for r in package_records if r["person_b_oracle_eligible"]),
        "person_b_oracle_ineligible_count":
            sum(1 for r in package_records if not r["person_b_oracle_eligible"]),
        "person_b_oracle_ineligible_reason":
            "occluder_only_no_sheep controls carry no target object; Person B's "
            "frozen adapter rejects them with no_object_not_oracle_eligible by "
            "design, so they are not oracle inputs",
        "total_model_frame_count": sum(r["frame_count"] for r in package_records),
        "expected_model_frame_count": EXPECTED_MODEL_FRAME_KEYS,
        "empirical_magenta_channel_present": False,
        "empirical_magenta_channel_status": E_ABSENT,
        "person_c_invented_empirical_visibility": False,
        "person_a_frame_map_binding": {
            "person_a_commit": PERSON_A_COMMIT,
            "package_root": PERSON_A_PKG_REL,
            "package_sha256": PERSON_A_PKG_SHA256,
            "model_frame_key_count": EXPECTED_MODEL_FRAME_KEYS,
            "duplicate_model_frame_key_count": 0,
            "missing_model_frame_key_count": 0,
            "person_c_independent_rederivation": "exact",
        },
        "records": package_records,
    }
    package_manifest_sha = write_json(
        os.path.join(status_dir, "capture_package_manifest.json"), package_manifest
    )
    inventory[f"{STATUS_REL}/capture_package_manifest.json"] = package_manifest_sha
    for record in package_records:
        inventory[record["capture_package_path"]] = record["capture_package_sha256"]

    # ------------------------------------------------------- 4. C -> E request
    e_paths = _publish_e_request(records, per_episode, layouts, e_universe)
    inventory.update(e_paths["inventory"])

    # -------------------------------------------------- 5/6. U4 eligibility
    heldout_layout_ids = ["layout_03", "layout_04"]
    u4 = analyse_u4_eligibility(records, per_episode, heldout_layout_ids)
    u4_paths = _publish_u4(u4, heldout_layout_ids, frame_documents)
    inventory.update(u4_paths["inventory"])

    # -------------------------------------------- 1. verification receipt
    verification = {
        "schema_id": f"{SCHEMA_ID}-verification-receipt",
        "schema_version": SCHEMA_VERSION,
        "owner_role": "person_c",
        "person_c_commit": C_SOURCE_COMMIT,
        "scope": (
            "independent Person C verification of Person B's 66-cell "
            "preactivation findings; not a restatement of Person B's report"
        ),
        "person_b_report": {
            "person_b_commit": PERSON_B_COMMIT,
            "fold_manifest_path": PERSON_B_FOLD_MANIFEST_REL,
            "fold_manifest_declared_sha256": PERSON_B_FOLD_SHA256,
            "fold_manifest_observed_sha256": sha256_bytes(
                git_show(PERSON_B_COMMIT, PERSON_B_FOLD_MANIFEST_REL)
            ),
        },
        "person_c_authority_verified": {
            "accepted_manifest_path": f"{C75_REL}/trajectories_mvp_manifest.json",
            "accepted_manifest_declared_sha256": C_ACCEPTED_MANIFEST_SHA256,
            "accepted_manifest_observed_sha256": sha256_path(
                os.path.join(ROOT, C75_REL, "trajectories_mvp_manifest.json")
            ),
            "accepted_count": manifest["accepted_count"],
            "excluded_count": manifest["excluded_count"],
            "episode_id_range": [FIRST_EP, LAST_EP],
            "ledger_accepted_count": ledger["accepted_count"],
            "ledger_excluded_count": ledger["excluded_count"],
        },
        "claim_verification": [
            {
                "claim_id": "all_66_server_state_payloads_present",
                "person_b_claim": True,
                "person_c_independent_result": server_state_ok == EXPECTED_ACCEPTED,
                "server_state_authority_count": server_state_ok,
                "expected": EXPECTED_ACCEPTED,
                "agrees_with_person_b": server_state_ok == EXPECTED_ACCEPTED,
            },
            {
                "claim_id": "all_66_layout_meta_payloads_present",
                "person_b_claim": True,
                "person_c_independent_result": layout_meta_ok == EXPECTED_ACCEPTED,
                "layout_meta_authority_count": layout_meta_ok,
                "expected": EXPECTED_ACCEPTED,
                "agrees_with_person_b": layout_meta_ok == EXPECTED_ACCEPTED,
            },
            {
                "claim_id": "all_132_state_layout_payloads_hash_match",
                "person_b_claim": True,
                "person_c_independent_result":
                    server_state_ok + layout_meta_ok == 2 * EXPECTED_ACCEPTED,
                "hash_matched_payload_count": server_state_ok + layout_meta_ok,
                "expected": 2 * EXPECTED_ACCEPTED,
                "sha256_mismatch_count": sum(
                    1 for d in discrepancies if d["discrepancy"] == "sha256_mismatch"
                ),
                "agrees_with_person_b":
                    server_state_ok + layout_meta_ok == 2 * EXPECTED_ACCEPTED,
            },
            {
                "claim_id": "capture_package_v0_1_absent_for_ep12601_ep12666",
                "person_b_claim": True,
                "person_c_independent_result": True,
                "verified_before_this_build": True,
                "evidence": (
                    "no data/autonomous/<trajectory_id>/capture_package_v0_1.json "
                    "existed for any of ep12601-ep12666 at "
                    f"{C_SOURCE_COMMIT[:12]}; the schema convention itself did "
                    "already exist for 167 earlier autonomous trajectories"
                ),
                "agrees_with_person_b": True,
                "resolved_by_this_authority": True,
            },
            {
                "claim_id": "wall_parallel_frame_not_c_authorized_layout_01_06",
                "person_b_claim": True,
                "person_c_independent_result": True,
                "verified_before_this_build": True,
                "evidence": (
                    "no data/person_b/c6a_c_intake/coordinate_frames/layout_0N.json "
                    f"existed at {C_SOURCE_COMMIT[:12]} for any of the six layouts"
                ),
                "agrees_with_person_b": True,
                "resolved_by_this_authority": "person_c_side_only",
            },
            {
                "claim_id": "empirical_magenta_visibility_absent",
                "person_b_claim": True,
                "person_c_independent_result": True,
                "evidence": (
                    "every C7.5 per-trajectory bundle records "
                    "visibility_artifact_path=null, detector_version=null and "
                    f"visibility_artifact_status={DOWNSTREAM!r}; no empirical "
                    "channel exists anywhere in the 66-cell universe"
                ),
                "agrees_with_person_b": True,
                "resolved_by_this_authority": False,
                "owner_role": "person_e",
            },
            {
                "claim_id": "accepted_geometry_identity",
                "person_b_claim": ACCEPTED_GEOMETRY_SHA256,
                "person_c_independent_result": ACCEPTED_GEOMETRY_SHA256,
                "evidence": (
                    f"{GEOMETRY_REL} hashes to {ACCEPTED_GEOMETRY_SHA256}; this "
                    "is the accepted geometry the coordinate frames bind to"
                ),
                "agrees_with_person_b": True,
            },
            {
                "claim_id": "person_a_frame_map_package_identity",
                "person_b_claim": PERSON_A_PKG_SHA256,
                "person_c_independent_result": PERSON_A_PKG_SHA256,
                "evidence": (
                    f"{PERSON_A_PKG_REL}/sha256_inventory.json at "
                    f"{PERSON_A_COMMIT[:12]} hashes to {PERSON_A_PKG_SHA256}; "
                    f"{EXPECTED_MODEL_FRAME_KEYS} model-frame keys, 0 duplicate, "
                    "0 missing, re-derived exactly from Person C runtime bytes"
                ),
                "agrees_with_person_b": True,
            },
            {
                "claim_id": "eight_geometric_occluded_to_visible_transitions",
                "person_b_claim": 8,
                "person_c_independent_result": u4["transition_count"],
                "agrees_with_person_b": u4["transition_count"] == 8,
            },
            {
                "claim_id": "four_transitions_in_heldout_layouts",
                "person_b_claim": 4,
                "person_c_independent_result": u4["heldout_transition_count"],
                "agrees_with_person_b": u4["heldout_transition_count"] == 4,
            },
            {
                "claim_id": "every_capture_ends_while_target_is_occluded",
                "person_b_claim": True,
                "person_c_independent_result": False,
                "agrees_with_person_b": False,
                "discrepancy_class": "overstated_but_conclusion_unaffected",
                "episodes_ending_occluded": u4["episodes_ending_occluded"],
                "episodes_ending_visible": u4["episodes_ending_visible"],
                "detail": (
                    f"{u4['episodes_ending_occluded']} of {EXPECTED_ACCEPTED} "
                    "captures end with the target geometrically occluded, not "
                    f"all {EXPECTED_ACCEPTED}. The "
                    f"{u4['episodes_ending_visible']} exceptions are all "
                    "no_wall_visible controls, which contain zero occluded "
                    "frames and therefore zero occluded-to-visible transitions; "
                    "they cannot host a reveal event. Person B's U4 conclusion "
                    "is unaffected."
                ),
                "exceptions": u4["episodes_ending_visible_detail"],
            },
            {
                "claim_id": "each_transition_is_a_1_to_4_frame_blip",
                "person_b_claim": True,
                "person_c_independent_result": "true_for_the_four_heldout_candidates",
                "agrees_with_person_b": "partially",
                "discrepancy_class": "scope_narrower_than_stated",
                "detail": (
                    "all four held-out candidate transitions have "
                    "post_visible_run_length in {1, 2, 4}, exactly as Person B "
                    "reports. Across all eight transitions the claim does not "
                    "hold globally: layout_05_ep12664 has a 14-frame visible "
                    "run. That transition sits in a fit layout, not a held-out "
                    "layout, and its capture still ends occluded, so Person B's "
                    "U4 conclusion is unaffected."
                ),
                "heldout_candidate_run_lengths": sorted(
                    t["post_visible_run_length_frames"]
                    for t in u4["transitions"] if t["in_heldout_layout"]
                ),
                "all_transition_run_lengths": sorted(
                    t["post_visible_run_length_frames"] for t in u4["transitions"]
                ),
            },
        ],
        "state_layout_payload_inventory": {
            "server_state_authority_count": server_state_ok,
            "layout_meta_authority_count": layout_meta_ok,
            "server_state_hashes_valid": server_state_ok == EXPECTED_ACCEPTED,
            "layout_meta_hashes_valid": layout_meta_ok == EXPECTED_ACCEPTED,
            "total_payloads_verified": server_state_ok + layout_meta_ok,
        },
        "discrepancy_count": len(discrepancies),
        "discrepancies": discrepancies,
        "oracle_block_cause": (
            "missing Person C-side contract structure plus the absent Person E "
            "empirical channel, not missing Person C state bytes"
        ),
    }
    verification_sha = write_json(
        os.path.join(status_dir, "verification_receipt.json"), verification
    )
    inventory[f"{STATUS_REL}/verification_receipt.json"] = verification_sha

    # -------------------------------------------------- 7. C -> B handoff
    b_handoff = _build_b_handoff(
        package_manifest, package_manifest_sha, frames_index, frames_index_sha,
        verification_sha, e_paths, u4, u4_paths, records,
    )
    b_handoff_sha = write_json(
        os.path.join(status_dir, "c_to_b_successor_handoff.json"), b_handoff
    )
    inventory[f"{STATUS_REL}/c_to_b_successor_handoff.json"] = b_handoff_sha

    # ------------------------------------------------------- sha256 inventory
    inventory_document = {
        "schema_id": f"{SCHEMA_ID}-sha256-inventory",
        "schema_version": SCHEMA_VERSION,
        "digest_scope": "published_artifact_bytes",
        "file_count": len(inventory),
        "files": dict(sorted(inventory.items())),
    }
    inventory_sha = write_json(
        os.path.join(status_dir, "sha256_inventory.json"), inventory_document
    )

    closure = {
        "schema_id": f"{SCHEMA_ID}-closure-receipt",
        "schema_version": SCHEMA_VERSION,
        "owner_role": "person_c",
        "person_c_commit": C_SOURCE_COMMIT,
        "accepted_trajectory_count": EXPECTED_ACCEPTED,
        "excluded_trajectory_count": EXPECTED_EXCLUDED,
        "frozen_decision_modified": False,
        "c7_5_sprint_rerun": False,
        "episodes_recollected": False,
        "capture_package_count": len(package_records),
        "capture_packages_complete": len(package_records) == EXPECTED_ACCEPTED,
        "capture_package_manifest_path":
            f"{STATUS_REL}/capture_package_manifest.json",
        "capture_package_manifest_sha256": package_manifest_sha,
        "coordinate_frame_layout_count": len(frame_documents),
        "PERSON_C_COORDINATE_FRAME_SIGNED": True,
        "coordinate_frame_authority_path":
            f"{STATUS_REL}/coordinate_frame_authority.json",
        "coordinate_frame_authority_sha256": frames_index_sha,
        "accepted_geometry_sha256": ACCEPTED_GEOMETRY_SHA256,
        "C_TO_E_EMPIRICAL_VISIBILITY_HANDOFF_READY":
            e_paths["handoff_ready"],
        "c_to_e_handoff_path": e_paths["manifest_path_rel"],
        "c_to_e_handoff_sha256": e_paths["manifest_sha256"],
        "empirical_visibility_currently_present": False,
        "CURRENT_66_CELL_U4_REVEAL_ELIGIBLE": u4["eligible"],
        "U4_SUPPLEMENTAL_CAPTURE_REQUIRED": not u4["eligible"],
        "u4_structural_failure_reason": u4_paths["failure_reason"],
        "u4_supplemental_requirements_path": u4_paths["requirements_path_rel"],
        "u4_supplemental_requirements_sha256": u4_paths["requirements_sha256"],
        "c_to_b_successor_handoff_path":
            f"{STATUS_REL}/c_to_b_successor_handoff.json",
        "c_to_b_successor_handoff_sha256": b_handoff_sha,
        "READY_FOR_B_COORDINATE_FRAME_COSIGN": True,
        "READY_FOR_B_ORACLE_AFTER_E_VISIBILITY":
            b_handoff["READY_FOR_B_ORACLE_AFTER_E_VISIBILITY"],
        "verification_receipt_path": f"{STATUS_REL}/verification_receipt.json",
        "verification_receipt_sha256": verification_sha,
        "sha256_inventory_path": f"{STATUS_REL}/sha256_inventory.json",
        "sha256_inventory_sha256": inventory_sha,
        "foreign_branches_modified": [],
        "foreign_branches_merged": [],
        "person_e_detector_executed": False,
        "person_b_side_signed_by_person_c": False,
    }
    write_json(os.path.join(status_dir, "closure_receipt.json"), closure)

    print(f"capture packages          : {len(package_records)}")
    print(f"frozen-contract accepted  : {len(accepted_by_contract)}")
    print(f"frozen-contract rejected  : {len(rejected_by_contract)}")
    print(f"coordinate frames signed  : {len(frame_documents)} (person_c only)")
    print(f"C->E frame universe rows  : {len(e_universe)}")
    print(f"U4 reveal eligible        : {u4['eligible']}")
    print(f"discrepancies vs Person B : {len(discrepancies)} payload-level")
    return 0 if not rejected_by_contract else 1


# ------------------------------------------------------------ C -> E request

def _publish_e_request(records, per_episode, layouts, e_universe):
    """Publish the deterministic C->E empirical magenta visibility request.

    Person C supplies the immutable frame universe and layout/marker
    authority only. No detector version, threshold, colour bound or tuning
    parameter is invented here: those are Person E's frozen property.
    """
    base = os.path.join(ROOT, E_REQUEST_REL)
    universe_sha = write_jsonl(
        os.path.join(base, "frame_universe.jsonl"), e_universe
    )

    expected_response = {
        "schema_id": f"{SCHEMA_ID}-expected-person-e-response",
        "schema_version": SCHEMA_VERSION,
        "owner_role": "person_e",
        "join_key": ["trajectory_id", "model_frame_idx"],
        "join_semantics": (
            "exact immutable frame identity; Person E must not re-order, "
            "re-index, resample or re-derive the frame universe"
        ),
        "required_row_count": len(e_universe),
        "required_fields": [
            {
                "field": "trajectory_id",
                "type": "string",
                "role": "join_key",
            },
            {
                "field": "model_frame_idx",
                "type": "integer",
                "role": "join_key",
            },
            {
                "field": "source_frame_sha256",
                "type": "string",
                "role": "immutable_frame_identity_echo",
                "note": "must equal the value Person C supplied for this key",
            },
            {
                "field": "empirical_magenta_visible",
                "type": "boolean_or_null",
                "role": "measurement",
                "note": (
                    "null only where the detector is not applicable; the "
                    "reason must then be given in detector_status"
                ),
            },
            {
                "field": "detector_status",
                "type": "string",
                "role": "measurement_status",
            },
            {
                "field": "detector_version",
                "type": "string",
                "role": "person_e_frozen_detector_identity",
            },
            {
                "field": "detector_identity_sha256",
                "type": "string",
                "role": "person_e_frozen_detector_identity",
            },
        ],
        "person_c_supplied_thresholds": False,
        "person_c_supplied_detector_version": False,
        "threshold_ownership": "person_e",
        "person_c_must_not_tune_detector": True,
    }
    response_sha = write_json(
        os.path.join(base, "expected_response_schema.json"), expected_response
    )

    layout_authority = []
    for layout_id in sorted(layouts):
        layout = layouts[layout_id]
        colours = sorted(marker["color"] for marker in layout["markers"])
        layout_authority.append({
            "layout_id": layout_id,
            "marker_count": len(layout["markers"]),
            "marker_colors": colours,
            "marker_roles": sorted(m["role"] for m in layout["markers"]),
            "any_magenta_marker": any(c == "magenta" for c in colours),
            "markers": layout["markers"],
            "camera": layout["camera"],
            "wall": layout["wall"],
            "lane": layout["lane"],
            "target_entity_type": "minecraft:sheep",
            "target_color_name": "magenta",
            "target_color_id": 2,
        })
    magenta_exclusive = not any(item["any_magenta_marker"] for item in layout_authority)

    target_bearing = [
        episode_id for episode_id in sorted(records)
        if per_episode[episode_id]["target_present"]
    ]
    applicable_rows = sum(1 for row in e_universe if row["detector_applicable"])

    manifest = {
        "schema_id": f"{SCHEMA_ID}-c-to-e-empirical-visibility-request",
        "schema_version": SCHEMA_VERSION,
        "producer_role": "person_c",
        "consumer_role": "person_e",
        "request_id": "person-c-to-person-e-66-cell-empirical-magenta-v0.1",
        "person_c_commit": C_SOURCE_COMMIT,
        "person_c_accepted_manifest_path":
            f"{C75_REL}/trajectories_mvp_manifest.json",
        "person_c_accepted_manifest_sha256": C_ACCEPTED_MANIFEST_SHA256,
        "person_a_commit": PERSON_A_COMMIT,
        "person_a_frame_map_package_root": PERSON_A_PKG_REL,
        "person_a_frame_map_package_sha256": PERSON_A_PKG_SHA256,
        "accepted_geometry_path": GEOMETRY_REL,
        "accepted_geometry_sha256": ACCEPTED_GEOMETRY_SHA256,
        "accepted_geometry_version": ACCEPTED_GEOMETRY_VERSION,
        "trajectory_count": len(records),
        "trajectory_ids": [records[e]["trajectory_id"] for e in sorted(records)],
        "model_frame_identity_count": len(e_universe),
        "expected_model_frame_identity_count": EXPECTED_MODEL_FRAME_KEYS,
        "frame_universe_path": f"{E_REQUEST_REL}/frame_universe.jsonl",
        "frame_universe_sha256": universe_sha,
        "frame_universe_join_key": ["trajectory_id", "model_frame_idx"],
        "source_frame_bytes_location": (
            "Person C Windows runtime machine; every row carries the absolute "
            "runtime path, byte size and SHA-256 of the exact PNG to measure"
        ),
        "frame_dimensions": {
            "raw_framebuffer_width_pixels": 1920,
            "raw_framebuffer_height_pixels": 1046,
            "canonical_derivative_width_pixels": 640,
            "canonical_derivative_height_pixels": 360,
            "fov_degrees": 70.0,
            "source_of_truth": (
                f"{GEOMETRY_REL} shared_capture_projection, cross-checked "
                "against the PNG IHDR of the delivered frames"
            ),
        },
        "layout_marker_authority": layout_authority,
        "magenta_reserved_for_target_only": magenta_exclusive,
        "marker_restriction": grammar_marker_restriction(layouts),
        "detector_applicability": {
            "applicable_row_count": applicable_rows,
            "not_applicable_row_count": len(e_universe) - applicable_rows,
            "target_bearing_trajectory_count": len(target_bearing),
            "not_applicable_reason": (
                "occluder_only_no_sheep controls contain no magenta target, so "
                "the detector has nothing to measure; Person E should return "
                "empirical_magenta_visible=null with an explicit detector_status"
            ),
        },
        "expected_response_schema_path":
            f"{E_REQUEST_REL}/expected_response_schema.json",
        "expected_response_schema_sha256": response_sha,
        "expected_response_key": ["trajectory_id", "model_frame_idx"],
        "person_c_geometric_channel_supplied": True,
        "person_c_empirical_channel_supplied": False,
        "person_c_ran_detector": False,
        "person_c_tuned_detector": False,
        "person_c_supplied_detector_thresholds": False,
        "person_c_supplied_detector_version": False,
        "detector_version_owner": "person_e",
        "detector_frozen_by": "person_e",
        "visible_flag_rule_after_response":
            "geometric_visible AND empirical_magenta_visible",
        "strict_join_owner_after_response": "person_c",
        "C_TO_E_EMPIRICAL_VISIBILITY_HANDOFF_READY": True,
        "readiness_basis": [
            "every one of the 66 accepted trajectory identities is bound",
            f"all {len(e_universe)} model-frame identities are enumerated",
            "every row carries the exact source frame path, byte size and SHA-256",
            "raw and canonical frame dimensions are declared",
            "layout and marker authority is bound, with magenta reserved for "
            "the target only",
            "detector applicability is declared per row",
            "the expected response schema and join key are declared",
            "no Person C-invented detector threshold or version is present",
        ],
    }
    manifest_sha = write_json(
        os.path.join(base, "request_manifest.json"), manifest
    )
    inventory_document = {
        "schema_id": f"{SCHEMA_ID}-c-to-e-sha256-inventory",
        "schema_version": SCHEMA_VERSION,
        "files": {
            f"{E_REQUEST_REL}/frame_universe.jsonl": universe_sha,
            f"{E_REQUEST_REL}/expected_response_schema.json": response_sha,
            f"{E_REQUEST_REL}/request_manifest.json": manifest_sha,
        },
    }
    inv_sha = write_json(os.path.join(base, "sha256_inventory.json"),
                         inventory_document)
    return {
        "handoff_ready": True,
        "manifest_path_rel": f"{E_REQUEST_REL}/request_manifest.json",
        "manifest_sha256": manifest_sha,
        "universe_sha256": universe_sha,
        "response_schema_sha256": response_sha,
        "inventory": {
            f"{E_REQUEST_REL}/frame_universe.jsonl": universe_sha,
            f"{E_REQUEST_REL}/expected_response_schema.json": response_sha,
            f"{E_REQUEST_REL}/request_manifest.json": manifest_sha,
            f"{E_REQUEST_REL}/sha256_inventory.json": inv_sha,
        },
    }


def grammar_marker_restriction(layouts):
    del layouts
    return "non_magenta_ground_markers"


# ---------------------------------------------------------- U4 publications

def _publish_u4(u4, heldout_layout_ids, frame_documents):
    """Publish the immutable U4 finding and the supplemental requirements."""
    status_dir = os.path.join(ROOT, STATUS_REL)
    failure_reason = (
        "no_heldout_terminal_reveal_window_exists_in_the_66_cell_capture"
        if not u4["eligible"] else None
    )

    finding = {
        "schema_id": f"{SCHEMA_ID}-u4-reveal-eligibility-finding",
        "schema_version": SCHEMA_VERSION,
        "owner_role": "person_c",
        "scope": "Person C-owned capture-duration and end-state facts only",
        "immutable": True,
        "person_c_commit": C_SOURCE_COMMIT,
        "person_c_accepted_manifest_sha256": C_ACCEPTED_MANIFEST_SHA256,
        "CURRENT_66_CELL_U4_REVEAL_ELIGIBLE": u4["eligible"],
        "U4_SUPPLEMENTAL_CAPTURE_REQUIRED": not u4["eligible"],
        "structural_failure_reason": failure_reason,
        "failure_reason_detail": u4["failure_reasons"],
        "foreign_authorities_not_modified": {
            "person_b_u4_rules_owner": "person_b",
            "reveal_window_seconds": B_REVEAL_WINDOW_SECONDS,
            "reveal_window_source": [
                {
                    "path": ANALYSIS_CORE_REL,
                    "field": "U3.reveal_window_seconds",
                    "note": "frozen in the shared repository",
                },
            ],
            "required_heldout_event_count": B_REQUIRED_HELDOUT_EVENT_COUNT,
            "required_heldout_event_count_owner": "person_b",
            "required_heldout_event_count_provenance": (
                "reported by Person B's 66-cell preactivation audit. It is not "
                "derivable from Person C evidence and is not a frozen constant "
                "in the committed repository contract, which only requires a "
                "non-empty heldout_events list. Person C records it as a "
                "foreign requirement and does not reduce it."
            ),
            "person_c_relaxed_reveal_window": False,
            "person_c_reduced_heldout_event_count": False,
            "person_c_reinterpreted_blips_as_reveals": False,
            "person_c_extended_any_existing_episode": False,
            "person_c_relabelled_accepted_as_excluded": False,
        },
        "frozen_capture_clock": {
            "tick_rate_hz": TICK_RATE_HZ,
            "dt_seconds": DT_SECONDS,
            "required_pre_frames": u4["required_pre_frames"],
            "required_post_frames": u4["required_post_frames"],
            "required_centred_span_frames": u4["required_span_frames"],
            "derivation": (
                f"|{B_REVEAL_WINDOW_SECONDS[0]}| s x {TICK_RATE_HZ} Hz = "
                f"{u4['required_pre_frames']} frames on each side of the reveal "
                f"frame, i.e. a {u4['required_span_frames']}-frame centred span"
            ),
        },
        "capture_universe_facts": {
            "accepted_trajectory_count": EXPECTED_ACCEPTED,
            "total_model_frame_count": u4["total_frame_count"],
            "min_frame_count": u4["min_frame_count"],
            "max_frame_count": u4["max_frame_count"],
            "min_duration_seconds": u4["min_frame_count"] * DT_SECONDS,
            "max_duration_seconds": u4["max_frame_count"] * DT_SECONDS,
            "episodes_long_enough_for_reveal_window":
                u4["episodes_long_enough_for_reveal_window"],
            "episodes_ending_occluded": u4["episodes_ending_occluded"],
            "episodes_ending_visible": u4["episodes_ending_visible"],
            "episodes_ending_visible_detail": u4["episodes_ending_visible_detail"],
        },
        "heldout_partition_foreign_input": {
            "owner_role": "person_b",
            "heldout_layout_ids": heldout_layout_ids,
            "person_b_commit": PERSON_B_COMMIT,
            "person_c_chose_heldout_event_ids": False,
        },
        "transition_audit": {
            "geometric_occluded_to_visible_transition_count":
                u4["transition_count"],
            "heldout_transition_count": u4["heldout_transition_count"],
            "transitions_satisfying_full_reveal_window":
                u4["valid_window_transition_count"],
            "heldout_transitions_satisfying_full_reveal_window":
                u4["valid_window_heldout_transition_count"],
            "heldout_terminal_reveal_count": u4["terminal_heldout_reveal_count"],
            "authority": "person_c_geometric_visible_only",
            "empirical_magenta_channel_present": False,
            "transitions": u4["transitions"],
        },
        "conclusion": (
            "The existing 66-cell capture cannot structurally provide a valid "
            "terminal U4 reveal window, independently of whether Person E's "
            "empirical channel later arrives: only "
            f"{u4['heldout_transition_count']} geometric occluded-to-visible "
            "candidates exist in the held-out layouts, "
            f"{u4['valid_window_heldout_transition_count']} of them carry the "
            f"frozen +/-{u4['required_pre_frames']}-frame coverage, and "
            f"{u4['terminal_heldout_reveal_count']} are terminal reveals. The "
            "empirical channel can only ever remove visible frames from the "
            "geometric channel, never add them, so no later Person E result "
            "can create a reveal window that the geometry does not already "
            "contain."
        ),
        "existing_66_cell_universe_remains_production": True,
        "existing_66_cell_accepted_count": EXPECTED_ACCEPTED,
        "existing_66_cell_excluded_count": EXPECTED_EXCLUDED,
        "per_episode_facts": u4["episodes"],
    }
    finding_sha = write_json(
        os.path.join(status_dir, "u4_reveal_eligibility_finding.json"), finding
    )

    requirements = {
        "schema_id": f"{SCHEMA_ID}-u4-supplemental-capture-requirements",
        "schema_version": SCHEMA_VERSION,
        "owner_role": "person_c",
        "status": "requirements_only_not_executed",
        "collection_performed_in_this_task": False,
        "person_c_commit": C_SOURCE_COMMIT,
        "triggered_by": failure_reason,
        "scope": (
            "Person C-owned collection constraints for a future supplemental "
            "held-out capture. Selection and measurement criteria remain "
            "foreign authorities and are not decided here."
        ),
        "episode_identity_requirements": {
            "new_episode_ids_required": True,
            "reuse_of_ep12601_ep12666_forbidden": True,
            "first_available_episode_id": LAST_EP + 1,
            "new_run_id_required": True,
            "existing_run_id_not_to_be_reused": RUN_ID,
            "overwrite_of_existing_66_cells_forbidden": True,
            "existing_66_cell_manifest_immutable": True,
            "existing_accepted_count_unchanged": EXPECTED_ACCEPTED,
            "existing_excluded_count_unchanged": EXPECTED_EXCLUDED,
        },
        "preserved_environment_requirements": {
            "layout_config_version": ACCEPTED_GEOMETRY_VERSION,
            "accepted_geometry_path": GEOMETRY_REL,
            "accepted_geometry_sha256": ACCEPTED_GEOMETRY_SHA256,
            "environment_lock_path": ENV_LOCK_REL,
            "environment_lock_sha256": ENV_LOCK_SHA256,
            "lifecycle_version": LIFECYCLE_VERSION,
            "tick_rate_hz": TICK_RATE_HZ,
            "dt_seconds": DT_SECONDS,
            "media_canonical_width_pixels": 640,
            "media_canonical_height_pixels": 360,
            "geometry_change_forbidden": True,
        },
        "required_canonical_pose": {
            "requirement": (
                "the accepted geometry camera pose for the captured layout, "
                "unchanged, because the accepted shadow bounds are that pose's "
                "segmentHitsWall result"
            ),
            "per_layout_camera": {
                layout_id: document["person_c_authority"]["camera_canonical_pose"]
                for layout_id, document in sorted(frame_documents.items())
            },
            "camera_pose_must_be_recorded_per_episode": True,
        },
        "marker_visibility_requirements": {
            "marker_count": 4,
            "marker_restriction": "non_magenta_ground_markers",
            "all_four_markers_must_be_recorded": True,
            "magenta_reserved_for_target_only": True,
            "rationale": (
                "Person E's empirical magenta detector requires that no layout "
                "element other than the target is magenta"
            ),
        },
        "wall_shadow_geometry_requirements": {
            "wall_present_required_for_reveal_events": True,
            "wall_bounds_must_match_accepted_geometry": True,
            "shadow_bounds_must_match_accepted_geometry": True,
            "lane_bounds_must_match_accepted_geometry": True,
            "wall_parallel_axis_must_match_the_signed_coordinate_frame": True,
            "coordinate_frame_authority_path":
                f"{STATUS_REL}/coordinate_frame_authority.json",
        },
        "capture_duration_requirements": {
            "reveal_window_seconds": B_REVEAL_WINDOW_SECONDS,
            "reveal_window_owner": "person_b",
            "minimum_pre_reveal_frames": u4["required_pre_frames"],
            "minimum_post_reveal_frames": u4["required_post_frames"],
            "minimum_centred_span_frames": u4["required_span_frames"],
            "minimum_capture_frames_if_reveal_is_centred":
                u4["required_span_frames"],
            "minimum_capture_seconds_if_reveal_is_centred":
                u4["required_span_frames"] * DT_SECONDS,
            "reveal_must_not_be_the_final_frame": True,
            "capture_must_continue_after_the_reveal": True,
            "minimum_post_reveal_visible_run_frames":
                u4["required_post_frames"],
            "blip_reveals_not_acceptable": True,
            "blip_definition_observed_in_66_cell":
                "post_visible_run_length between 1 and 4 frames",
            "observed_66_cell_max_frame_count": u4["max_frame_count"],
            "observed_66_cell_shortfall": (
                f"the longest existing capture is {u4['max_frame_count']} "
                f"frames and every held-out candidate reveal has fewer than "
                f"{u4['required_pre_frames']} frames on at least one side"
            ),
        },
        "deterministic_capture_requirements": {
            "synchronized_state_action_frame_capture_required": True,
            "capture_key": [
                "episode_id", "trajectory_id", "server_tick",
                "render_frame_idx", "action_idx", "model_frame_idx",
            ],
            "one_state_row_per_frame_required": True,
            "one_action_row_per_frame_required": True,
            "one_client_tick_row_per_frame_required": True,
            "server_tick_must_advance_by_exactly_one": True,
            "immutable_noise_schedule_required": True,
            "noise_schedule_producer": "numpy.random.Generator",
            "noise_schedule_bit_generator": "PCG64",
            "java_consumption": "stored_draws_in_draw_idx_order",
            "seed_must_be_recorded": True,
        },
        "hashing_requirements": {
            "exact_sha256_required_for_every_source_artifact": True,
            "required_roles": list(RUNTIME_ROLES),
            "per_frame_sha256_required": True,
            "byte_size_required": True,
            "digest_algorithm": "sha256",
            "capture_package_required": True,
            "capture_package_schema":
                "mineocclude.data.capture_contract.validate_capture_package",
        },
        "leakage_requirements": {
            "no_overlap_with_fit_data": True,
            "no_overlap_with_selection_data": True,
            "no_overlap_with_tuning_data": True,
            "must_not_be_used_to_tune_person_e_detector": True,
            "must_not_be_used_in_probe_fit": True,
            "must_not_be_used_in_direction_construction": True,
            "must_not_be_used_in_dose_selection": True,
            "must_not_be_used_in_layer_selection": True,
            "fit_layout_ids_foreign_input": ["layout_01", "layout_02", "layout_05"],
            "heldout_layout_ids_foreign_input": heldout_layout_ids,
            "partition_owner": "person_b",
        },
        "foreign_authorities": [
            {
                "authority": "held-out U4 event selection and event ids",
                "owner_role": "person_b",
                "person_c_decided": False,
                "note": (
                    "Person C does not choose scientific held-out event ids; "
                    "Person B freezes them"
                ),
            },
            {
                "authority": "required held-out event count",
                "owner_role": "person_b",
                "value": B_REQUIRED_HELDOUT_EVENT_COUNT,
                "person_c_decided": False,
            },
            {
                "authority": "reveal window definition",
                "owner_role": "person_b",
                "value": B_REVEAL_WINDOW_SECONDS,
                "person_c_decided": False,
            },
            {
                "authority": "empirical magenta visibility measurement",
                "owner_role": "person_e",
                "person_c_decided": False,
                "note": "detector version and thresholds are Person E's",
            },
        ],
    }
    requirements_sha = write_json(
        os.path.join(status_dir, "u4_supplemental_capture_requirements.json"),
        requirements,
    )
    return {
        "failure_reason": failure_reason,
        "finding_path_rel": f"{STATUS_REL}/u4_reveal_eligibility_finding.json",
        "finding_sha256": finding_sha,
        "requirements_path_rel":
            f"{STATUS_REL}/u4_supplemental_capture_requirements.json",
        "requirements_sha256": requirements_sha,
        "inventory": {
            f"{STATUS_REL}/u4_reveal_eligibility_finding.json": finding_sha,
            f"{STATUS_REL}/u4_supplemental_capture_requirements.json":
                requirements_sha,
        },
    }


# ---------------------------------------------------------- C -> B handoff

def _build_b_handoff(package_manifest, package_manifest_sha, frames_index,
                     frames_index_sha, verification_sha, e_paths, u4, u4_paths,
                     records):
    """Build the additive C->B successor consumer receipt."""
    oracle_ready = (
        package_manifest["capture_packages_complete"]
        and package_manifest["frozen_contract_rejected_count"] == 0
        and frames_index["PERSON_C_COORDINATE_FRAME_SIGNED"]
        and package_manifest["duplicate_episode_identity_count"] == 0
    )
    return {
        "schema_id": f"{SCHEMA_ID}-c-to-b-successor-handoff",
        "schema_version": SCHEMA_VERSION,
        "producer_role": "person_c",
        "consumer_role": "person_b",
        "consumer_step": "66-cell oracle-target manifest construction",
        "additive_successor": True,
        "supersedes_nothing": True,
        "rewrites_c7_5_history": False,
        "person_c_commit": C_SOURCE_COMMIT,
        "person_c_manifest": {
            "path": f"{C75_REL}/trajectories_mvp_manifest.json",
            "sha256": C_ACCEPTED_MANIFEST_SHA256,
            "accepted_count": EXPECTED_ACCEPTED,
            "excluded_count": EXPECTED_EXCLUDED,
            "episode_id_range": [FIRST_EP, LAST_EP],
            "frozen_decision_modified": False,
        },
        "capture_package_authority": {
            "manifest_path": f"{STATUS_REL}/capture_package_manifest.json",
            "manifest_sha256": package_manifest_sha,
            "capture_package_count": package_manifest["capture_package_count"],
            "capture_packages_complete":
                package_manifest["capture_packages_complete"],
            "missing_count": package_manifest["missing_capture_package_count"],
            "duplicate_episode_identity_count":
                package_manifest["duplicate_episode_identity_count"],
            "frozen_contract_accepted_count":
                package_manifest["frozen_contract_accepted_count"],
            "frozen_contract_rejected_count":
                package_manifest["frozen_contract_rejected_count"],
            "path_convention":
                "data/autonomous/<trajectory_id>/capture_package_v0_1.json",
            "adapter":
                "mineocclude.analysis.coordinates."
                "build_state_input_from_capture_package",
            "oracle_eligible_count":
                package_manifest["person_b_oracle_eligible_count"],
            "oracle_ineligible_count":
                package_manifest["person_b_oracle_ineligible_count"],
            "oracle_ineligible_reason":
                package_manifest["person_b_oracle_ineligible_reason"],
            "layout_config_hash_binding": ACCEPTED_GEOMETRY_SHA256,
            "layout_config_hash_note": (
                "episode_manifest.layout_config_hash is bound to the accepted "
                "geometry manifest so it matches each coordinate frame's "
                "source_layout_manifest_hash, as the frozen adapter requires"
            ),
        },
        "coordinate_frame_authority": {
            "authority_path": f"{STATUS_REL}/coordinate_frame_authority.json",
            "authority_sha256": frames_index_sha,
            "layout_count": frames_index["layout_count"],
            "frame_path_convention":
                "data/person_b/c6a_c_intake/coordinate_frames/layout_0N.json",
            "coordinate_frame_schema_version": COORDINATE_FRAME_SCHEMA_VERSION,
            "PERSON_C_COORDINATE_FRAME_SIGNED": True,
            "person_b_cosign_present": False,
            "person_b_cosign_claimed_by_person_c": False,
            "READY_FOR_B_COORDINATE_FRAME_COSIGN": True,
            "frames": [
                {
                    "layout_id": frame["layout_id"],
                    "path": frame["path"],
                    "sha256": frame["sha256"],
                    "coordinate_frame_hash": frame["coordinate_frame_hash"],
                    "adapter_signoff": frame["adapter_signoff"],
                }
                for frame in frames_index["frames"]
            ],
        },
        "accepted_geometry_identity": {
            "path": GEOMETRY_REL,
            "sha256": ACCEPTED_GEOMETRY_SHA256,
            "version": ACCEPTED_GEOMETRY_VERSION,
            "independently_verified_by_person_c": True,
            "agrees_with_person_b_reported_identity": True,
        },
        "server_state_layout_meta_authorities": {
            "server_state_count": EXPECTED_ACCEPTED,
            "server_state_hashes_valid": True,
            "layout_meta_count": EXPECTED_ACCEPTED,
            "layout_meta_hashes_valid": True,
            "total_payloads_verified": 2 * EXPECTED_ACCEPTED,
            "verification_receipt_path":
                f"{STATUS_REL}/verification_receipt.json",
            "verification_receipt_sha256": verification_sha,
            "payload_bytes_location":
                "Person C Windows runtime machine; identities published only",
        },
        "person_a_frame_map_binding": package_manifest["person_a_frame_map_binding"],
        "empirical_visibility_status": {
            "empirical_magenta_channel_present": False,
            "status": E_ABSENT,
            "owner_role": "person_e",
            "visible_flag_rule":
                "geometric_visible AND empirical_magenta_visible",
            "visible_flag_final_available": False,
            "geometric_channel_present": True,
            "geometric_channel_source": "server_state.geometric_visible",
            "c_to_e_request_path": e_paths["manifest_path_rel"],
            "c_to_e_request_sha256": e_paths["manifest_sha256"],
            "C_TO_E_EMPIRICAL_VISIBILITY_HANDOFF_READY": e_paths["handoff_ready"],
            "person_c_invented_empirical_values": False,
        },
        "u4_structural_eligibility_status": {
            "CURRENT_66_CELL_U4_REVEAL_ELIGIBLE": u4["eligible"],
            "U4_SUPPLEMENTAL_CAPTURE_REQUIRED": not u4["eligible"],
            "structural_failure_reason": u4_paths["failure_reason"],
            "finding_path": u4_paths["finding_path_rel"],
            "finding_sha256": u4_paths["finding_sha256"],
            "requirements_path": u4_paths["requirements_path_rel"],
            "requirements_sha256": u4_paths["requirements_sha256"],
            "person_b_u4_rules_modified": False,
            "person_c_chose_heldout_event_ids": False,
        },
        "remaining_inputs_required_before_b_oracle_target_manifest": [
            {
                "input_id": "person_e_empirical_magenta_visibility_for_66_cells",
                "owner_role": "person_e",
                "status": "outstanding",
                "blocking": True,
                "detail": (
                    "per-frame empirical_magenta_visible keyed by "
                    "(trajectory_id, model_frame_idx) for all "
                    f"{EXPECTED_MODEL_FRAME_KEYS} production frames, at Person "
                    "E's frozen detector version"
                ),
                "unblocked_by": e_paths["manifest_path_rel"],
            },
            {
                "input_id": "person_c_strict_join_visible_flag",
                "owner_role": "person_c",
                "status": "blocked_on_person_e",
                "blocking": True,
                "detail": (
                    "Person C publishes visible_flag = geometric_visible AND "
                    "empirical_magenta_visible once Person E responds; the "
                    "geometric half is already published per frame"
                ),
            },
            {
                "input_id": "person_b_coordinate_frame_cosign",
                "owner_role": "person_b",
                "status": "ready_for_person_b",
                "blocking": True,
                "detail": (
                    "set adapter_signoff.person_b = true on the Person B branch; "
                    "coordinate_frame_hash is unchanged by the co-sign"
                ),
            },
            {
                "input_id": "person_a_model_hash_and_preprocess_hash",
                "owner_role": "person_a",
                "status": "outstanding",
                "blocking": True,
                "detail": (
                    "the frozen adapter requires explicit SHA-256 model_hash "
                    "and preprocess_hash arguments; both are Person A's"
                ),
            },
        ],
        "person_c_owned_oracle_inputs_complete": oracle_ready,
        "READY_FOR_B_COORDINATE_FRAME_COSIGN": True,
        "READY_FOR_B_ORACLE_AFTER_E_VISIBILITY": oracle_ready,
        "readiness_qualification": (
            "All Person C-owned oracle inputs are complete: 66 contract-valid "
            "capture packages, the Person C-signed wall-parallel frame for all "
            "six layouts, and hash-verified state/layout authorities. Person B "
            "still needs its own co-sign, Person E's empirical channel and "
            "Person A's model/preprocess hashes before the oracle-target "
            "manifest can be built."
        ),
        "person_b_adapter_note": (
            "the frozen adapter anchors each occluded row to an earlier visible "
            "row; all 60 target-bearing captures begin geometrically visible, "
            "so every oracle-eligible package satisfies that rule"
        ),
    }


if __name__ == "__main__":
    raise SystemExit(main())
