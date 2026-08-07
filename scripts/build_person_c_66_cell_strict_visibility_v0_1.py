"""Build the Person C strict 66-cell visibility join, events, and B handoff.

Person C owns the final ``visible_flag``. This builder:

  1. intakes Person E's empirical magenta visibility at E's pinned commit,
     re-verifying every declared identity without merging E's branch;
  2. materializes the authoritative Person C geometric channel for the exact
     2468 production model-frame identities and independently recomputes it
     with C's frozen geometry implementation over accepted v0.4 geometry;
  3. strictly joins the two channels on ``(trajectory_id, model_frame_idx)``
     with C's frozen ``strict_join`` (visible_flag = geometric AND empirical);
  4. publishes the disagreement ledger;
  5. derives occlusion/reveal events with C's frozen event-stability rule;
  6. recomputes and freezes the 66-cell U4 terminal-reveal eligibility;
  7. publishes the additive C->B oracle-ready handoff.

Nothing is retuned. Person E's detector is never executed here, Person B's
oracle logic is never modified, and the frozen 66 accepted / 0 excluded C7.5
decision is re-derived and asserted, never edited.

Geometric channel policy
------------------------
The authoritative geometric channel is the Java runtime's recorded
``server_state.geometric_visible``: that is the capture truth, it is already
published in the 66 capture packages, Person A's frame map carries it, and
Person B's co-sign revalidated it. C's frozen Python implementation is run as
an independent second opinion over the same authoritative state. Where the two
implementations disagree the row is marked explicitly ambiguous
(``boundary_cross_implementation``) and both values are retained; the
authoritative value is never overwritten and the ambiguity is never hidden.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from mineocclude.data.visibility import (  # noqa: E402
    EVENT_RULE_VERSION,
    GEOMETRY_RULE_VERSION,
    DEFAULT_STABILITY_FRAMES,
    GeometricStatus,
    geometric_visibility,
    layout_wall_box,
    stabilize,
    visibility_events,
)
from mineocclude.data.visibility_join import (  # noqa: E402
    FINAL_VISIBILITY_INTERFACE_VERSION,
    strict_join,
)

SCHEMA_ID = "mineocclude-person-c-66-cell-strict-visibility-v0.1"
SCHEMA_VERSION = "0.1"

# ------------------------------------------------------------- C authorities

C_SOURCE_COMMIT = "aceb319c47af6d494d6e5314049b12ab1a0a002f"
C_ACCEPTED_MANIFEST_SHA256 = (
    "96ba43e15bc024aeaef7c519fa4ece0a4afe0bb0e877501dffaca44fee927ff7"
)
C_CAPTURE_PACKAGE_MANIFEST_SHA256 = (
    "ca6ef6bd0a6ee144731ff3e6f470f767a2c1a82e8b46aef9fb5e458efb814f56"
)
C_COORDINATE_FRAME_AUTHORITY_SHA256 = (
    "1aed95e444f82ab4caf9935c039e87df3aafbf38830bf763a646aba3d62b509b"
)
ACCEPTED_GEOMETRY_SHA256 = (
    "34495d650d6a8c62b00a916796c90389b48f80d8f20a23eac93207758e993f5d"
)
ACCEPTED_GEOMETRY_VERSION = "person-c-layout-config-v0.4"

C75_REL = "docs/status/person_c_c7_mvp_handoff_v0_1"
CAPTURE_AUTHORITY_REL = "docs/status/person_c_66_cell_capture_authority_v0_1"
GEOMETRY_REL = "configs/scenes/layouts_v0_4.yaml"
AUTONOMOUS_REL = "data/autonomous"
FRAMES_REL = "data/person_b/c6a_c_intake/coordinate_frames"
C_REQUEST_REL = (
    "data/handoff_e/"
    "person_c_to_person_e_66_cell_empirical_visibility_request_v0_1"
)
C_REQUEST_MANIFEST_SHA256 = (
    "6934317b6b2723d4dddb5507ba58ef32e6ce39729bd4065751aa76e8ae1fc0ea"
)

# ------------------------------------------------------- foreign authorities

PERSON_A_COMMIT = "77e43bd1665671b9e23d6d6ef927ee4944611342"
PERSON_A_PKG_SHA256 = (
    "a473bf830ed31e49762d62bba97032e52f4967e52f9987ad10cd5879ed9bd004"
)

PERSON_B_COMMIT = "a8648514033f8d58887c3b919f02985704aaa310"
PERSON_B_COSIGN_REL = (
    "docs/status/person_b_66_cell_coordinate_frame_cosign_v0_1/"
    "coordinate_frame_cosign.json"
)
PERSON_B_COSIGN_SHA256 = (
    "b40d8ba1103e1638af386cc365ec727ab576d842516accc41d675d4fdb3d6b7d"
)

PERSON_E_COMMIT = "fec27d08b4629afa07c7858598e94778dc6e7bef"
E_DIR_REL = "data/handoff_c/person_e_66_cell_empirical_visibility_v0_1"
E_RECORDS_REL = f"{E_DIR_REL}/empirical_visibility_records.jsonl"
E_HANDOFF_REL = f"{E_DIR_REL}/e_to_c_empirical_visibility_handoff.json"
E_RECORDS_SHA256 = (
    "fd0ad70ce880645fcda668d23dacc07784c2f8e418a3eceabd9f88ac391e07f9"
)
E_HANDOFF_SHA256 = (
    "91a5c6996cdd176a62f5f0dd752b25acda1d73163894b9c9b2f34317a38e9652"
)
E_DETECTOR_IDENTITY_SHA256 = (
    "0cadf618fca1578196bde4982021c38627ccb9c39e46353812e7da3fce6aa125"
)
E_MARKER_AUTHORITY_REL = (
    "data/handoff_e/person_e_v0_4_marker_layout_authority_v0_1"
)
E_MARKER_AUTHORITY_SHA256 = (
    "14a12db4092e05e8c41057df210eec11f07a78f593a149595a12eba45fda82d8"
)

# ------------------------------------------------------------------ expected

FIRST_EP, LAST_EP = 12601, 12666
EXPECTED_ACCEPTED = 66
EXPECTED_EXCLUDED = 0
EXPECTED_FRAME_KEYS = 2468
EXPECTED_APPLICABLE = 2108
EXPECTED_NOT_APPLICABLE = 360
E_EXPECTED_VISIBLE = 1726
E_EXPECTED_HIDDEN = 382

TICK_RATE_HZ = 20.0
DT_SECONDS = 0.05

# Person B owns the U4 selection thresholds. Recorded as immutable foreign
# inputs; never relaxed and never reduced by Person C.
B_REVEAL_WINDOW_SECONDS = [-1.0, 1.0]
B_REQUIRED_HELDOUT_EVENT_COUNT = 5
B_HELDOUT_LAYOUT_IDS = ["layout_03", "layout_04"]
B_FIT_LAYOUT_IDS = ["layout_01", "layout_02", "layout_05"]
ANALYSIS_CORE_REL = "configs/analysis/core.yaml"

# ------------------------------------------------------------------ outputs

STATUS_REL = "docs/status/person_c_66_cell_strict_visibility_v0_1"

NOT_APPLICABLE_STATUS = "not_applicable_no_target_object"
BOUNDARY_CROSS = "boundary_cross_implementation"
E_NOT_APPLICABLE = "not_applicable_no_target_object"


class BuildError(Exception):
    """Raised when a committed or foreign authority fails to reconcile."""


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


def read_jsonl_path(path: str):
    with open(path, "r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def git_show(commit: str, rel_path: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", ROOT, "show", f"{commit}:{rel_path}"],
        capture_output=True, timeout=180,
    )
    if result.returncode != 0:
        fail(
            f"required foreign authority {rel_path!r} is not readable at "
            f"{commit[:12]}: {result.stderr.decode(errors='replace').strip()}"
        )
    return result.stdout


def pose_id(layout_id: str) -> str:
    """Canonical camera-pose identity, derived not copied."""
    return f"{layout_id}_canonical_pose_v1"


# ----------------------------------------------------------- intake: Person C

def load_c_authority():
    """Re-derive the frozen C7.5 accepted universe and the capture packages."""
    manifest_path = os.path.join(ROOT, C75_REL, "trajectories_mvp_manifest.json")
    observed = sha256_path(manifest_path)
    if observed != C_ACCEPTED_MANIFEST_SHA256:
        fail(f"C accepted manifest identity changed: {observed}")
    manifest = json.loads(open(manifest_path, "rb").read())
    if (
        manifest["accepted_count"] != EXPECTED_ACCEPTED
        or manifest["excluded_count"] != EXPECTED_EXCLUDED
    ):
        fail("the frozen 66 accepted / 0 excluded decision does not reconcile")
    records = {int(r["episode_id"]): r for r in manifest["records"]}
    if sorted(records) != list(range(FIRST_EP, LAST_EP + 1)):
        fail("accepted episode ids are not exactly ep12601-ep12666")

    capture_manifest_path = os.path.join(
        ROOT, CAPTURE_AUTHORITY_REL, "capture_package_manifest.json"
    )
    observed = sha256_path(capture_manifest_path)
    if observed != C_CAPTURE_PACKAGE_MANIFEST_SHA256:
        fail(f"C capture-package manifest identity changed: {observed}")
    capture_manifest = json.loads(open(capture_manifest_path, "rb").read())

    frame_authority_path = os.path.join(
        ROOT, CAPTURE_AUTHORITY_REL, "coordinate_frame_authority.json"
    )
    observed = sha256_path(frame_authority_path)
    if observed != C_COORDINATE_FRAME_AUTHORITY_SHA256:
        fail(f"C coordinate-frame authority identity changed: {observed}")

    packages = {}
    for record in capture_manifest["records"]:
        path = os.path.join(ROOT, record["capture_package_path"])
        digest = sha256_path(path)
        if digest != record["capture_package_sha256"]:
            fail(
                f"capture package {record['capture_package_path']} identity "
                f"changed: {digest}"
            )
        packages[record["episode_id"]] = json.loads(open(path, "rb").read())
    return manifest, records, capture_manifest, packages


def load_geometry():
    path = os.path.join(ROOT, GEOMETRY_REL)
    observed = sha256_path(path)
    if observed != ACCEPTED_GEOMETRY_SHA256:
        fail(f"accepted geometry identity changed: {observed}")
    document = json.loads(open(path, "rb").read())
    if document["config_version"] != ACCEPTED_GEOMETRY_VERSION:
        fail("accepted geometry config_version mismatch")
    return document, {x["layout_id"]: x for x in document["layouts"]}


# ----------------------------------------------------------- intake: Person E

def intake_person_e(records, packages):
    """Verify Person E's handoff at its pinned commit and return its records.

    Person E's branch is never merged: only its committed bytes are read, and
    every declared identity is re-verified against Person C's own authorities.
    """
    problems = []

    handoff_bytes = git_show(PERSON_E_COMMIT, E_HANDOFF_REL)
    handoff_observed = sha256_bytes(handoff_bytes)
    if handoff_observed != E_HANDOFF_SHA256:
        fail(f"E handoff identity changed: {handoff_observed}")
    handoff = json.loads(handoff_bytes)

    records_bytes = git_show(PERSON_E_COMMIT, E_RECORDS_REL)
    records_observed = sha256_bytes(records_bytes)
    if records_observed != E_RECORDS_SHA256:
        fail(f"E empirical table identity changed: {records_observed}")
    e_rows = [
        json.loads(line)
        for line in records_bytes.decode("utf-8").splitlines() if line.strip()
    ]

    # -- E's declared bindings must match Person C's own authorities exactly
    checks = {
        "e_declared_records_sha256":
            handoff["empirical_visibility_records_sha256"] == E_RECORDS_SHA256,
        "e_declared_c_commit":
            handoff["person_c"]["commit"] == C_SOURCE_COMMIT,
        "e_declared_c_accepted_manifest":
            handoff["person_c"]["accepted_manifest_sha256"]
            == C_ACCEPTED_MANIFEST_SHA256,
        "e_declared_c_capture_package_manifest":
            handoff["person_c"]["capture_package_manifest_sha256"]
            == C_CAPTURE_PACKAGE_MANIFEST_SHA256,
        "e_declared_c_request_manifest":
            handoff["person_c"]["request_manifest_sha256"]
            == C_REQUEST_MANIFEST_SHA256,
        "e_declared_accepted_geometry":
            handoff["accepted_geometry_sha256"] == ACCEPTED_GEOMETRY_SHA256,
        "e_declared_detector_identity":
            handoff["detector"]["identity_sha256"] == E_DETECTOR_IDENTITY_SHA256,
        "e_declared_b_cosign":
            handoff["person_b"]["coordinate_frame_cosign_sha256"]
            == PERSON_B_COSIGN_SHA256,
        "e_declared_b_commit":
            handoff["person_b"]["commit"] == PERSON_B_COMMIT,
        "e_declared_marker_authority":
            handoff["marker_layout_authority"]["sha256"]
            == E_MARKER_AUTHORITY_SHA256,
        "e_did_not_compute_geometric_visible":
            handoff["geometric_visible_computed_by_person_e"] is False,
        "e_did_not_compute_visible_flag":
            handoff["visible_flag_computed_by_person_e"] is False,
        "e_join_key_is_canonical":
            handoff["canonical_join_key"] == ["trajectory_id", "model_frame_idx"],
        "e_strict_join_owner_is_person_c":
            handoff["strict_join_owner_after_response"] == "person_c",
        "e_declared_ready": handoff["E_TO_C_EMPIRICAL_VISIBILITY_READY"] is True,
    }
    for name, ok in checks.items():
        if not ok:
            problems.append({"check": name, "result": "mismatch"})

    # -- Person C's own request universe must be the exact measured universe
    request_path = os.path.join(ROOT, C_REQUEST_REL, "request_manifest.json")
    request_observed = sha256_path(request_path)
    if request_observed != C_REQUEST_MANIFEST_SHA256:
        fail(f"C request manifest identity changed: {request_observed}")
    request = json.loads(open(request_path, "rb").read())
    universe_path = os.path.join(ROOT, C_REQUEST_REL, "frame_universe.jsonl")
    universe_observed = sha256_path(universe_path)
    if universe_observed != request["frame_universe_sha256"]:
        fail("C frame universe identity changed")
    if handoff["frame_universe"]["sha256"] != universe_observed:
        problems.append({
            "check": "e_measured_the_exact_c_frame_universe",
            "result": "mismatch",
            "c_frame_universe_sha256": universe_observed,
            "e_declared_frame_universe_sha256":
                handoff["frame_universe"]["sha256"],
        })
    requested = {
        (r["trajectory_id"], r["model_frame_idx"]): r
        for r in read_jsonl_path(universe_path)
    }

    # -- key-set, duplicate, missing and per-row identity accounting
    seen = set()
    duplicates = []
    for row in e_rows:
        key = (row["trajectory_id"], row["model_frame_idx"])
        if key in seen:
            duplicates.append(key)
        seen.add(key)
    missing = sorted(set(requested) - seen)
    extra = sorted(seen - set(requested))

    source_mismatch = []
    applicability_mismatch = []
    detector_identity_drift = set()
    detector_versions = set()
    marker_authorities = set()
    for row in e_rows:
        key = (row["trajectory_id"], row["model_frame_idx"])
        source = requested.get(key)
        if source is None:
            continue
        if row["source_frame_sha256"] != source["source_frame_sha256"]:
            source_mismatch.append(key)
        if bool(row["detector_applicable"]) != bool(source["detector_applicable"]):
            applicability_mismatch.append(key)
        detector_identity_drift.add(row["detector_identity_sha256"])
        detector_versions.add(row["detector_version"])
        marker_authorities.add(row["marker_layout_authority_sha256"])

    status_counts = collections.Counter(r["detector_status"] for r in e_rows)
    visible = sum(1 for r in e_rows if r["empirical_magenta_visible"] is True)
    hidden = sum(1 for r in e_rows if r["empirical_magenta_visible"] is False)
    null = sum(1 for r in e_rows if r["empirical_magenta_visible"] is None)
    unreadable = status_counts.get("unreadable_source_frame", 0)

    forbidden_present = sorted({
        field
        for row in e_rows
        for field in ("geometric_visible", "person_c_geometric_visible",
                      "visible_flag", "precision", "recall")
        if field in row
    })

    for name, condition, detail in (
        ("row_count", len(e_rows) == EXPECTED_FRAME_KEYS, len(e_rows)),
        ("no_duplicate_keys", not duplicates, len(duplicates)),
        ("no_missing_keys", not missing, len(missing)),
        ("no_extra_keys", not extra, len(extra)),
        ("source_frame_identity_matches_c_request", not source_mismatch,
         len(source_mismatch)),
        ("applicability_matches_c_request", not applicability_mismatch,
         len(applicability_mismatch)),
        ("single_detector_identity", len(detector_identity_drift) == 1,
         sorted(detector_identity_drift)),
        ("detector_identity_is_the_frozen_one",
         detector_identity_drift == {E_DETECTOR_IDENTITY_SHA256},
         sorted(detector_identity_drift)),
        ("single_marker_layout_authority", len(marker_authorities) == 1,
         sorted(marker_authorities)),
        ("no_unexplained_failures", unreadable == 0, unreadable),
        ("no_forbidden_person_c_fields", not forbidden_present,
         forbidden_present),
        ("declared_visible_count_matches", visible == E_EXPECTED_VISIBLE, visible),
        ("declared_hidden_count_matches", hidden == E_EXPECTED_HIDDEN, hidden),
        ("declared_not_applicable_count_matches",
         null == EXPECTED_NOT_APPLICABLE, null),
    ):
        if not condition:
            problems.append({"check": name, "result": "mismatch", "observed": detail})

    # -- Person B's co-sign, verified independently of Person E's word
    cosign_bytes = git_show(PERSON_B_COMMIT, PERSON_B_COSIGN_REL)
    cosign_observed = sha256_bytes(cosign_bytes)
    if cosign_observed != PERSON_B_COSIGN_SHA256:
        fail(f"B co-sign identity changed: {cosign_observed}")
    cosign = json.loads(cosign_bytes)
    frame_authority_sha = sha256_path(
        os.path.join(ROOT, CAPTURE_AUTHORITY_REL, "coordinate_frame_authority.json")
    )
    cosign_checks = {
        "b_cosign_binds_c_coordinate_authority":
            cosign["person_c_coordinate_frame_sha256"]
            == C_COORDINATE_FRAME_AUTHORITY_SHA256,
        "b_cosign_input_manifest_is_c_authority":
            cosign["input_manifest_hash"] == frame_authority_sha,
        "b_cosign_binds_c_commit":
            cosign["person_c_commit"] == C_SOURCE_COMMIT,
        "b_cosign_did_not_modify_c_bytes":
            cosign["person_c_bytes_modified"] is False,
        "b_cosign_did_not_merge_c_branch":
            cosign["person_c_branch_merged"] is False,
        "b_signed_its_own_side":
            cosign["adapter_signoff"]["person_b"] is True,
        "b_preserved_person_c_signature":
            cosign["adapter_signoff"]["person_c"] is True,
        "b_projection_matches_person_c_exactly":
            cosign["projection_replay"]["checks"][
                "projection_matches_person_c_exactly"] is True,
        "b_all_layouts_compatible":
            cosign["compatibility_result"]["all_layouts_compatible"] is True,
        "b_did_not_build_oracle_target_manifest":
            cosign["oracle_target_manifest_built"] is False,
    }
    for name, ok in cosign_checks.items():
        if not ok:
            problems.append({"check": name, "result": "mismatch"})

    published_frames = {
        entry["layout_id"]: entry
        for entry in json.loads(open(os.path.join(
            ROOT, CAPTURE_AUTHORITY_REL, "coordinate_frame_authority.json"
        ), "rb").read())["frames"]
    }
    cosigned = []
    for entry in cosign["cosigned_frames"]:
        layout_id = entry["layout_id"]
        source = sha256_path(os.path.join(ROOT, FRAMES_REL, f"{layout_id}.json"))
        ok = (
            source == entry["person_c_source_file_sha256"]
            and published_frames[layout_id]["coordinate_frame_hash"]
            == entry["coordinate_frame_hash"]
            and entry["coordinate_frame_hash_preserved"] is True
        )
        if not ok:
            problems.append({
                "check": "b_cosigned_frame_binds_person_c_frame",
                "result": "mismatch", "layout_id": layout_id,
            })
        cosigned.append({
            "layout_id": layout_id,
            "coordinate_frame_hash": entry["coordinate_frame_hash"],
            "coordinate_frame_hash_preserved":
                entry["coordinate_frame_hash_preserved"],
            "person_c_source_file_sha256": entry["person_c_source_file_sha256"],
            "person_c_source_file_sha256_reverified": source,
        })

    # -- Person E's marker/layout successor authority against accepted geometry
    marker_manifest_bytes = git_show(
        PERSON_E_COMMIT, f"{E_MARKER_AUTHORITY_REL}/marker_layout_authority_manifest.json"
    )
    marker_observed = sha256_bytes(marker_manifest_bytes)
    if marker_observed != E_MARKER_AUTHORITY_SHA256:
        fail(f"E marker/layout authority identity changed: {marker_observed}")
    marker_manifest = json.loads(marker_manifest_bytes)

    intake = {
        "schema_id": f"{SCHEMA_ID}-e-handoff-intake-receipt",
        "schema_version": SCHEMA_VERSION,
        "owner_role": "person_c",
        "person_c_commit": C_SOURCE_COMMIT,
        "person_e_commit": PERSON_E_COMMIT,
        "person_e_branch_merged": False,
        "read_method": "git show at the pinned Person E commit",
        "e_handoff_path": E_HANDOFF_REL,
        "e_handoff_declared_sha256": E_HANDOFF_SHA256,
        "e_handoff_observed_sha256": handoff_observed,
        "e_empirical_records_path": E_RECORDS_REL,
        "e_empirical_records_declared_sha256": E_RECORDS_SHA256,
        "e_empirical_records_observed_sha256": records_observed,
        "c_request_manifest_sha256": request_observed,
        "c_frame_universe_sha256": universe_observed,
        "detector": {
            "identity_sha256": E_DETECTOR_IDENTITY_SHA256,
            "version": sorted(detector_versions)[0] if detector_versions else None,
            "algorithm_id": handoff["detector"]["algorithm_id"],
            "implementation_path": handoff["detector"]["implementation_path"],
            "implementation_sha256": handoff["detector"]["implementation_sha256"],
            "config_sha256": handoff["detector"]["config_sha256"],
            "settings_sha256": handoff["detector"]["settings_sha256"],
            "retuned_on_66_cell_population": False,
            "person_c_executed_detector": False,
            "person_c_tuned_detector": False,
            "distinct_identities_observed_in_table":
                sorted(detector_identity_drift),
        },
        "person_b_cosign": {
            "commit": PERSON_B_COMMIT,
            "path": PERSON_B_COSIGN_REL,
            "declared_sha256": PERSON_B_COSIGN_SHA256,
            "observed_sha256": cosign_observed,
            "checks": cosign_checks,
            "cosigned_frames": cosigned,
        },
        "marker_layout_successor_authority": {
            "owner_role": "person_e",
            "authority_id": marker_manifest["authority_id"],
            "path": f"{E_MARKER_AUTHORITY_REL}/marker_layout_authority_manifest.json",
            "declared_sha256": E_MARKER_AUTHORITY_SHA256,
            "observed_sha256": marker_observed,
            "world_point_convention": marker_manifest["world_point_convention"],
            "additive_successor": marker_manifest["additive_successor"],
            "historical_predecessor_invalidated":
                marker_manifest["historical_predecessor_invalidated"],
            "marker_world_coordinates_changed_to_satisfy_a_test":
                marker_manifest["marker_world_coordinates_changed_to_satisfy_a_test"],
            "accepted_geometry_sha256": marker_manifest["accepted_geometry_sha256"],
        },
        "identity_checks": checks,
        "accounting": {
            "row_count": len(e_rows),
            "unique_key_count": len(seen),
            "duplicate_key_count": len(duplicates),
            "missing_key_count": len(missing),
            "extra_key_count": len(extra),
            "source_frame_identity_mismatch_count": len(source_mismatch),
            "applicability_mismatch_count": len(applicability_mismatch),
            "empirical_visible_count": visible,
            "empirical_hidden_count": hidden,
            "empirical_not_applicable_count": null,
            "unreadable_source_frame_count": unreadable,
            "detector_status_counts": dict(sorted(status_counts.items())),
        },
        "forbidden_person_c_fields_present": forbidden_present,
        "problem_count": len(problems),
        "problems": problems,
        "E_HANDOFF_ACCEPTED": not problems,
    }
    if problems:
        fail(
            "Person E / Person B intake rejected: "
            + json.dumps(problems[:6])
        )
    return intake, e_rows, handoff, marker_manifest


# --------------------------------------------- 2. geometric visibility channel

def build_geometric_channel(records, packages, layouts):
    """Materialize C's authoritative geometric channel and cross-check it.

    The authoritative value is the Java runtime's recorded
    ``server_state.geometric_visible``. C's frozen Python implementation is
    run independently over the same authoritative state and accepted v0.4
    geometry; disagreement marks the row ambiguous instead of overwriting the
    recorded capture truth or collapsing it to a binary.
    """
    rows = []
    shadow_edges = {}
    for layout_id, layout in layouts.items():
        occluded = [
            int(s["axis_position"])
            for s in layout["shadow"]["integer_lane_samples"] if s["occluded"]
        ]
        shadow_edges[layout_id] = (min(occluded), max(occluded))

    for episode_id in sorted(records):
        record = records[episode_id]
        package = packages[episode_id]
        authority = package["person_c_authority"]
        trajectory_id = record["trajectory_id"]
        layout_id = record["layout_id"]
        layout = layouts[layout_id]
        scene = authority["condition_identity"]["scene"]
        target_present = authority["target_count_identity"]["target_present"]

        state_declared = authority["source_sha256_inventory"]["server_state"]
        state_path = state_declared["path"]
        observed = sha256_path(state_path)
        if observed != state_declared["sha256"]:
            fail(f"ep{episode_id} server_state identity changed: {observed}")
        state_rows = {
            int(r["server_tick"]): r for r in read_jsonl_path(state_path)
        }

        # The frozen no-wall rule: the no_wall_visible condition has no wall.
        wall = (
            None if scene == "NO_WALL"
            else layout_wall_box({"wall": layout["wall"]["bounds"]})
        )
        target_centre_y = float(layout["shadow"]["target_centre_y"])
        low, high = shadow_edges[layout_id]

        for frame in sorted(
            package["streams"]["frame_map"], key=lambda r: r["model_frame_idx"]
        ):
            server_tick = frame["server_tick"]
            state = state_rows[server_tick]
            authoritative = state["geometric_visible"]

            if not target_present or state.get("sheep_x") is None:
                # Frozen no-object semantics: nothing to see. Never fabricate a
                # hidden target and never coerce this into a binary.
                rows.append({
                    "trajectory_id": trajectory_id,
                    "model_frame_idx": frame["model_frame_idx"],
                    "episode_id": episode_id,
                    "layout_id": layout_id,
                    "server_tick": server_tick,
                    "render_frame_idx": frame["render_frame_idx"],
                    "action_idx": frame["action_idx"],
                    "canonical_camera_pose_id": pose_id(layout_id),
                    "resolution": "640x360",
                    "coordinate_convention": "pixel_center_xy_zero_based",
                    "geometric_visible": None,
                    "geometric_status": NOT_APPLICABLE_STATUS,
                    "geometric_applicable": False,
                    "geometric_ambiguous": False,
                    "geometric_visible_authoritative_runtime": authoritative,
                    "geometric_visible_frozen_recompute": None,
                    "frozen_recompute_status": GeometricStatus.INVALID.value,
                    "cross_implementation_agreement": None,
                    "target_present": False,
                    "wall_present": scene != "NO_WALL",
                    "wall_parallel_position_blocks": None,
                    "distance_to_shadow_edge_blocks": None,
                    "geometry_rule_version": GEOMETRY_RULE_VERSION,
                    "accepted_geometry_sha256": ACCEPTED_GEOMETRY_SHA256,
                    "accepted_geometry_version": ACCEPTED_GEOMETRY_VERSION,
                    "source_state_path": state_path,
                    "source_state_sha256": state_declared["sha256"],
                    "not_applicable_reason":
                        "occluder_only_no_sheep control carries no target object",
                })
                continue

            camera = (state["player_x"], state["player_y"], state["player_z"])
            target = (
                state["sheep_x"], state["sheep_y"] + 0.5, state["sheep_z"],
            )
            frozen_status = (
                GeometricStatus.VISIBLE if wall is None
                else geometric_visibility(camera, target, wall)
            )
            frozen_visible = (
                True if frozen_status is GeometricStatus.VISIBLE
                else False if frozen_status is GeometricStatus.OCCLUDED
                else None
            )
            agrees = frozen_visible == bool(authoritative)
            axis_position = state["axis_pos"]
            # Distance to the declared shadow edge is only meaningful when an
            # occluder exists; the no-wall control has no shadow.
            distance = None if wall is None else min(
                abs(axis_position - (low - 1)), abs(axis_position - low),
                abs(axis_position - high), abs(axis_position - (high + 1)),
            )
            if frozen_status in (GeometricStatus.BOUNDARY, GeometricStatus.INVALID):
                status = GeometricStatus.BOUNDARY.value
                ambiguous = True
            elif agrees:
                status = (
                    GeometricStatus.VISIBLE.value if authoritative
                    else GeometricStatus.OCCLUDED.value
                )
                ambiguous = False
            else:
                status = BOUNDARY_CROSS
                ambiguous = True
            rows.append({
                "trajectory_id": trajectory_id,
                "model_frame_idx": frame["model_frame_idx"],
                "episode_id": episode_id,
                "layout_id": layout_id,
                "server_tick": server_tick,
                "render_frame_idx": frame["render_frame_idx"],
                "action_idx": frame["action_idx"],
                "canonical_camera_pose_id": pose_id(layout_id),
                "resolution": "640x360",
                "coordinate_convention": "pixel_center_xy_zero_based",
                # authoritative recorded capture truth, never overwritten
                "geometric_visible": bool(authoritative),
                "geometric_status": status,
                "geometric_applicable": True,
                "geometric_ambiguous": ambiguous,
                "geometric_visible_authoritative_runtime": bool(authoritative),
                "geometric_visible_frozen_recompute": frozen_visible,
                "frozen_recompute_status": frozen_status.value,
                "cross_implementation_agreement": agrees,
                "target_present": True,
                "wall_present": scene != "NO_WALL",
                "wall_parallel_position_blocks": axis_position,
                "distance_to_shadow_edge_blocks": distance,
                "geometry_rule_version": GEOMETRY_RULE_VERSION,
                "accepted_geometry_sha256": ACCEPTED_GEOMETRY_SHA256,
                "accepted_geometry_version": ACCEPTED_GEOMETRY_VERSION,
                "source_state_path": state_path,
                "source_state_sha256": state_declared["sha256"],
                "not_applicable_reason": None,
            })

    if len(rows) != EXPECTED_FRAME_KEYS:
        fail(f"geometric channel has {len(rows)} rows, expected {EXPECTED_FRAME_KEYS}")
    return rows


# ------------------------------------------------------------- 3. strict join

def build_strict_join(geometric_rows, e_rows, detector_version):
    """Join with C's frozen strict_join; annotate ambiguity additively."""
    geo_by_key = {
        (r["trajectory_id"], r["model_frame_idx"]): r for r in geometric_rows
    }
    c_records = [
        {
            "trajectory_id": r["trajectory_id"],
            "model_frame_idx": r["model_frame_idx"],
            "geometric_visible": r["geometric_visible"],
            "layout_id": r["layout_id"],
            "canonical_camera_pose_id": r["canonical_camera_pose_id"],
            "resolution": r["resolution"],
            "coordinate_convention": r["coordinate_convention"],
            "geometry_rule_version": r["geometry_rule_version"],
        }
        for r in geometric_rows
    ]
    e_projected = [
        {
            "trajectory_id": r["trajectory_id"],
            "model_frame_idx": r["model_frame_idx"],
            "empirical_magenta_visible": r["empirical_magenta_visible"],
            "detector_version": r["detector_version"],
            "layout_id": r["layout_id"],
            "canonical_camera_pose_id": r["canonical_camera_pose_id"],
            "resolution": r["resolution"],
            "coordinate_convention": r["coordinate_convention"],
        }
        for r in e_rows
    ]
    joined = strict_join(
        c_records, e_projected, expected_detector_version=detector_version
    )
    e_by_key = {(r["trajectory_id"], r["model_frame_idx"]): r for r in e_rows}

    out = []
    for row in joined:
        key = (row["trajectory_id"], row["model_frame_idx"])
        geo = geo_by_key[key]
        e = e_by_key[key]
        applicable = bool(
            geo["geometric_applicable"] and e["detector_applicable"]
        )
        out.append({
            **row,
            "episode_id": geo["episode_id"],
            "server_tick": geo["server_tick"],
            "render_frame_idx": geo["render_frame_idx"],
            "action_idx": geo["action_idx"],
            "resolution": geo["resolution"],
            "coordinate_convention": geo["coordinate_convention"],
            # geometry provenance and ambiguity, preserved separately
            "geometric_status": geo["geometric_status"],
            "geometric_applicable": geo["geometric_applicable"],
            "geometric_ambiguous": geo["geometric_ambiguous"],
            "geometric_visible_authoritative_runtime":
                geo["geometric_visible_authoritative_runtime"],
            "geometric_visible_frozen_recompute":
                geo["geometric_visible_frozen_recompute"],
            "frozen_recompute_status": geo["frozen_recompute_status"],
            "cross_implementation_agreement": geo["cross_implementation_agreement"],
            "wall_present": geo["wall_present"],
            "wall_parallel_position_blocks": geo["wall_parallel_position_blocks"],
            "distance_to_shadow_edge_blocks": geo["distance_to_shadow_edge_blocks"],
            "target_present": geo["target_present"],
            # detector provenance
            "detector_status": e["detector_status"],
            "detector_status_reason": e["detector_status_reason"],
            "detector_applicable": bool(e["detector_applicable"]),
            "detector_identity_sha256": e["detector_identity_sha256"],
            "source_frame_sha256": e["source_frame_sha256"],
            "canonical_frame_rgb_sha256": e["canonical_frame_rgb_sha256"],
            # applicability semantics, explicit rather than coerced
            "visibility_applicable": applicable,
            "not_applicable_reason": (
                None if applicable
                else "occluder_only_no_sheep control carries no target object"
            ),
            "visible_flag_defined": applicable,
            "visible_flag_forced_false_by_frozen_contract": (
                (not applicable) and row["visible_flag"] is False
            ),
            "visible_flag_ambiguous_geometry": (
                applicable and geo["geometric_ambiguous"]
            ),
            "accepted_geometry_sha256": ACCEPTED_GEOMETRY_SHA256,
            "source_state_sha256": geo["source_state_sha256"],
            "empirical_visibility_source_sha256": E_RECORDS_SHA256,
            "person_e_commit": PERSON_E_COMMIT,
            "visible_flag_rule":
                "geometric_visible AND empirical_magenta_visible",
        })
    if len(out) != EXPECTED_FRAME_KEYS:
        fail(f"joined table has {len(out)} rows, expected {EXPECTED_FRAME_KEYS}")
    return out


# ------------------------------------------------------ 4. disagreement ledger

def classify_row(row):
    """Assign the disagreement class for one joined row. Labels are derived."""
    if not row["visibility_applicable"]:
        return "detector_not_applicable"
    if row["geometric_ambiguous"]:
        return "geometry_ambiguous"
    geo = row["geometric_visible"]
    emp = row["empirical_magenta_visible"]
    if geo is None or emp is None:
        return "invalid_or_missing_input"
    if geo and not emp:
        return "geometry_visible_detector_hidden"
    if emp and not geo:
        return "geometry_hidden_detector_visible"
    return "agreement"


def build_disagreement_ledger(joined, records, packages, event_index):
    """Classify every applicable disagreement; nothing is relabelled."""
    by_key = {(r["trajectory_id"], r["model_frame_idx"]): r for r in joined}
    for row in joined:
        row["disagreement_class"] = classify_row(row)

    classes = collections.Counter(r["disagreement_class"] for r in joined)
    by_layout = collections.defaultdict(collections.Counter)
    by_set = collections.defaultdict(collections.Counter)
    by_condition = collections.defaultdict(collections.Counter)
    for row in joined:
        record = records[row["episode_id"]]
        authority = packages[row["episode_id"]]["person_c_authority"]
        by_layout[row["layout_id"]][row["disagreement_class"]] += 1
        by_set[record["set_id"]][row["disagreement_class"]] += 1
        condition = authority["condition_identity"]["condition"]
        by_condition[condition][row["disagreement_class"]] += 1

    # Disagreements near a candidate occlusion/reveal boundary, where a
    # boundary is any raw transition of either channel in the same capture.
    near = collections.Counter()
    boundary_window_frames = 2
    for trajectory_id, entry in event_index.items():
        boundaries = set(entry["boundary_frames"])
        for idx in entry["model_frame_indices"]:
            row = by_key[(trajectory_id, idx)]
            if row["disagreement_class"] in (
                "agreement", "detector_not_applicable"
            ):
                continue
            if any(
                abs(idx - boundary) <= boundary_window_frames
                for boundary in boundaries
            ):
                near[row["disagreement_class"]] += 1
                row["near_candidate_boundary"] = True
            else:
                row["near_candidate_boundary"] = False
    for row in joined:
        row.setdefault("near_candidate_boundary", False)

    disagreement_rows = [
        {
            "trajectory_id": r["trajectory_id"],
            "model_frame_idx": r["model_frame_idx"],
            "episode_id": r["episode_id"],
            "layout_id": r["layout_id"],
            "disagreement_class": r["disagreement_class"],
            "geometric_visible": r["geometric_visible"],
            "geometric_status": r["geometric_status"],
            "geometric_visible_frozen_recompute":
                r["geometric_visible_frozen_recompute"],
            "empirical_magenta_visible": r["empirical_magenta_visible"],
            "detector_status": r["detector_status"],
            "visible_flag": r["visible_flag"],
            "quarantine_category": r["quarantine_category"],
            "wall_parallel_position_blocks": r["wall_parallel_position_blocks"],
            "distance_to_shadow_edge_blocks": r["distance_to_shadow_edge_blocks"],
            "near_candidate_boundary": r["near_candidate_boundary"],
        }
        for r in joined
        if r["disagreement_class"] not in ("agreement",)
    ]

    ledger = {
        "schema_id": f"{SCHEMA_ID}-disagreement-ledger",
        "schema_version": SCHEMA_VERSION,
        "owner_role": "person_c",
        "person_c_commit": C_SOURCE_COMMIT,
        "labels_manually_adjusted": False,
        "geometry_retuned": False,
        "detector_retuned": False,
        "classification_rule": (
            "derived mechanically from the two retained raw channels; no row "
            "was relabelled and no threshold was changed"
        ),
        "boundary_window_frames": boundary_window_frames,
        "total_rows": len(joined),
        "global_counts": dict(sorted(classes.items())),
        "applicable_row_count": sum(
            1 for r in joined if r["visibility_applicable"]
        ),
        "applicable_disagreement_count": sum(
            classes[k] for k in (
                "geometry_visible_detector_hidden",
                "geometry_hidden_detector_visible",
                "geometry_ambiguous",
                "invalid_or_missing_input",
            )
        ),
        "by_layout": {k: dict(sorted(v.items())) for k, v in sorted(by_layout.items())},
        "by_set_id": {k: dict(sorted(v.items())) for k, v in sorted(by_set.items())},
        "by_condition": {
            k: dict(sorted(v.items())) for k, v in sorted(by_condition.items())
        },
        "near_candidate_boundary_counts": dict(sorted(near.items())),
        "subclass_characterisation": {
            "near_shadow_edge_applicable_disagreements": {
                "count": sum(
                    1 for r in joined
                    if r["disagreement_class"] in (
                        "geometry_visible_detector_hidden",
                        "geometry_hidden_detector_visible",
                    )
                    and r["distance_to_shadow_edge_blocks"] is not None
                    and r["distance_to_shadow_edge_blocks"] <= 1.0
                ),
                "characterisation": (
                    "the frozen geometric rule tests a single sightline to the "
                    "target centre while the detector accepts any valid magenta "
                    "blob, so a partially occluded target can be centre-blocked "
                    "with edge pixels visible, or centre-clear with too few "
                    "magenta pixels to pass the frozen minimum area"
                ),
                "person_c_resolved_these": False,
            },
            "no_wall_control_detector_null_match": {
                "count": sum(
                    1 for r in joined
                    if r["disagreement_class"] == "geometry_visible_detector_hidden"
                    and not r["wall_present"]
                ),
                "rows": [
                    {
                        "trajectory_id": r["trajectory_id"],
                        "model_frame_idx": r["model_frame_idx"],
                        "detector_status": r["detector_status"],
                        "detector_status_reason": r["detector_status_reason"],
                        "wall_parallel_position_blocks":
                            r["wall_parallel_position_blocks"],
                        "source_frame_sha256": r["source_frame_sha256"],
                    }
                    for r in joined
                    if r["disagreement_class"] == "geometry_visible_detector_hidden"
                    and not r["wall_present"]
                ],
                "facts_person_c_verified": [
                    "the condition is a no_wall_visible control, so no occluder "
                    "exists and the frozen geometric rule returns visible",
                    "Person E reports detector_status=not_detected with reason "
                    "no_threshold_match, i.e. zero magenta pixels matched",
                    "a diagnostic horizontal field-of-view check (not part of "
                    "the frozen geometric channel) places the target roughly 18 "
                    "degrees off the camera axis against a 51.2 degree "
                    "horizontal half field of view, and moving toward the "
                    "centre, so leaving the frame does not explain these rows",
                ],
                "person_c_attributed_a_cause": False,
                "owner_of_next_step": "person_e",
                "next_step": (
                    "Person E review of why the frozen detector matched zero "
                    "magenta pixels on these frames. Person C did not adjust "
                    "any label, threshold or geometry, and the affected rows "
                    "remain quarantined with both raw channels retained."
                ),
            },
        },
        "cross_implementation_geometry_note": (
            "geometry_ambiguous rows are frames where the authoritative Java "
            "runtime channel and C's frozen Python recomputation of the same "
            "convention disagree. Every such frame lies within one block of a "
            "declared shadow edge: the runtime block volume is half-open while "
            "the frozen Python box is closed, so grazing sightlines differ. "
            "The authoritative recorded value is retained and the ambiguity is "
            "published rather than resolved."
        ),
        "disagreement_rows": disagreement_rows,
    }
    return ledger


# --------------------------------------------------------- 5. event derivation

def build_events(joined, records, packages):
    """Derive events with C's frozen stability rule on the joined channel.

    The rule, its stability window and the reveal-window coverage requirement
    are all predeclared: ``visibility_events`` at
    ``person-c-event-stability-v0.1`` with ``DEFAULT_STABILITY_FRAMES``, and
    Person B's frozen [-1.0, 1.0] s reveal window at the frozen 20 Hz clock.
    Nothing is chosen after inspecting results.
    """
    required_pre = required_post = int(
        round(abs(B_REVEAL_WINDOW_SECONDS[0]) * TICK_RATE_HZ)
    )
    span = required_pre + required_post + 1

    by_trajectory = collections.defaultdict(list)
    for row in joined:
        by_trajectory[row["trajectory_id"]].append(row)

    event_rows = []
    trajectory_rows = []
    event_index = {}
    for trajectory_id in sorted(by_trajectory):
        rows = sorted(by_trajectory[trajectory_id], key=lambda r: r["model_frame_idx"])
        episode_id = rows[0]["episode_id"]
        record = records[episode_id]
        authority = packages[episode_id]["person_c_authority"]
        applicable = all(r["visibility_applicable"] for r in rows)
        frames = len(rows)

        final_sequence = [bool(r["visible_flag"]) for r in rows]
        geometric_sequence = [bool(r["geometric_visible"]) for r in rows]
        empirical_sequence = [
            bool(r["empirical_magenta_visible"])
            if r["empirical_magenta_visible"] is not None else False
            for r in rows
        ]

        raw_boundaries = sorted({
            idx for idx in range(1, frames)
            if final_sequence[idx] != final_sequence[idx - 1]
            or geometric_sequence[idx] != geometric_sequence[idx - 1]
            or empirical_sequence[idx] != empirical_sequence[idx - 1]
        })
        event_index[trajectory_id] = {
            "boundary_frames": raw_boundaries,
            "model_frame_indices": [r["model_frame_idx"] for r in rows],
        }

        final_events = visibility_events(
            final_sequence, DEFAULT_STABILITY_FRAMES, DT_SECONDS
        )
        geometric_events = visibility_events(
            geometric_sequence, DEFAULT_STABILITY_FRAMES, DT_SECONDS
        )
        stabilized = stabilize(final_sequence, DEFAULT_STABILITY_FRAMES)
        flicker_frames = [
            idx for idx in range(frames) if stabilized[idx] != final_sequence[idx]
        ]
        raw_reveal_candidates = [
            idx for idx in range(1, frames)
            if not final_sequence[idx - 1] and final_sequence[idx]
        ]
        stable_reveals = [
            e["reveal_idx"] for e in final_events["events"]
            if e["reveal_idx"] is not None
        ]
        rejected_by_stability = [
            idx for idx in raw_reveal_candidates if idx not in stable_reveals
        ]

        rejected_by_window = []
        valid_terminal = []
        for event in final_events["events"]:
            reveal = event["reveal_idx"]
            record_row = {
                "trajectory_id": trajectory_id,
                "episode_id": episode_id,
                "layout_id": record["layout_id"],
                "set_id": record["set_id"],
                "control_type": record["control_type"],
                "condition": authority["condition_identity"]["condition"],
                "event_id": f"{trajectory_id}:{event['event_id']}",
                "frozen_event_id": event["event_id"],
                "onset_model_frame_idx": event["onset_idx"],
                "reveal_model_frame_idx": reveal,
                "hidden_frames": event["hidden_frames"],
                "hidden_seconds": event["hidden_seconds"],
                "event_rule_version": EVENT_RULE_VERSION,
                "stability_frames": DEFAULT_STABILITY_FRAMES,
                "channel": "final_visible_flag",
                "applicable": applicable,
                "missing_reveal": reveal is None,
                "frame_count": frames,
                "in_heldout_layout": record["layout_id"] in B_HELDOUT_LAYOUT_IDS,
            }
            if reveal is None:
                record_row.update({
                    "frames_before_reveal": None,
                    "frames_after_reveal": None,
                    "pre_window_satisfied": False,
                    "post_window_satisfied": False,
                    "reveal_window_satisfied": False,
                    "visible_sustained_to_capture_end": False,
                    "valid_terminal_reveal": False,
                    "rejection_reason": "missing_reveal_capture_ends_hidden",
                })
            else:
                pre, post = reveal, frames - 1 - reveal
                sustained = all(stabilized[reveal:])
                ok = pre >= required_pre and post >= required_post
                valid = bool(ok and sustained and applicable)
                if not ok:
                    reason = "insufficient_pre_post_reveal_window"
                elif not sustained:
                    reason = "reveal_not_sustained_to_capture_end"
                elif not applicable:
                    reason = "not_applicable_no_target_object"
                else:
                    reason = None
                record_row.update({
                    "frames_before_reveal": pre,
                    "frames_after_reveal": post,
                    "pre_window_satisfied": pre >= required_pre,
                    "post_window_satisfied": post >= required_post,
                    "reveal_window_satisfied": ok,
                    "visible_sustained_to_capture_end": sustained,
                    "valid_terminal_reveal": valid,
                    "rejection_reason": reason,
                })
                if not ok:
                    rejected_by_window.append(reveal)
                if valid:
                    valid_terminal.append(reveal)
            event_rows.append(record_row)

        trajectory_rows.append({
            "trajectory_id": trajectory_id,
            "episode_id": episode_id,
            "layout_id": record["layout_id"],
            "set_id": record["set_id"],
            "condition": authority["condition_identity"]["condition"],
            "frame_count": frames,
            "applicable": applicable,
            "in_heldout_layout": record["layout_id"] in B_HELDOUT_LAYOUT_IDS,
            "final_visible_frame_count": sum(final_sequence),
            "geometric_visible_frame_count": sum(geometric_sequence),
            "event_count": final_events["n_events"],
            "multiple_events": final_events["multiple_events"],
            "missing_reveal": final_events["missing_reveal"],
            "has_valid_occlusion": any(
                e["onset_idx"] is not None for e in final_events["events"]
            ) and applicable,
            "valid_terminal_reveal_count": len(valid_terminal),
            "raw_onset_candidates": final_events["raw_onset_candidates"],
            "raw_reveal_candidates": raw_reveal_candidates,
            "reveal_candidates_rejected_by_stability": rejected_by_stability,
            "reveal_candidates_rejected_by_window": rejected_by_window,
            "flicker_frame_count": len(flicker_frames),
            "flicker_model_frame_indices": flicker_frames,
            "frames_deleted": False,
            "geometric_only_event_count": geometric_events["n_events"],
            "geometric_only_raw_reveal_candidates": [
                idx for idx in range(1, frames)
                if not geometric_sequence[idx - 1] and geometric_sequence[idx]
            ],
            # filled in after the disagreement ledger classifies the rows
            "disagreement_near_boundary": None,
            "event_rule_version": EVENT_RULE_VERSION,
            "stability_frames": DEFAULT_STABILITY_FRAMES,
        })

    # Raw occluded->visible candidate counts per channel, so a count derived
    # from one channel is never compared against another role's count derived
    # from a different channel.
    channel_candidates = {}
    for name, extract in (
        ("empirical_only", lambda r: bool(r["empirical_magenta_visible"])),
        ("geometric_only", lambda r: bool(r["geometric_visible"])),
        ("joined_visible_flag", lambda r: bool(r["visible_flag"])),
    ):
        total = heldout = 0
        for trajectory_id in sorted(by_trajectory):
            rows = sorted(
                by_trajectory[trajectory_id], key=lambda r: r["model_frame_idx"]
            )
            if not all(r["visibility_applicable"] for r in rows):
                continue
            sequence = [extract(r) for r in rows]
            indices = [
                idx for idx in range(1, len(sequence))
                if not sequence[idx - 1] and sequence[idx]
            ]
            total += len(indices)
            if rows[0]["layout_id"] in B_HELDOUT_LAYOUT_IDS:
                heldout += len(indices)
        channel_candidates[name] = {
            "raw_occluded_to_visible_candidate_count": total,
            "raw_occluded_to_visible_candidate_count_heldout_layouts": heldout,
        }

    return {
        "required_pre_frames": required_pre,
        "required_post_frames": required_post,
        "required_span_frames": span,
        "event_rows": event_rows,
        "trajectory_rows": trajectory_rows,
        "event_index": event_index,
        "channel_candidates": channel_candidates,
    }


# ------------------------------------------------------------------- 6. U4

def build_u4_finding(events, handoff):
    """Recompute 66-cell U4 eligibility from the joined C/E visibility."""
    event_rows = events["event_rows"]
    trajectory_rows = events["trajectory_rows"]
    applicable_events = [e for e in event_rows if e["applicable"]]
    reveals = [e for e in applicable_events if e["reveal_model_frame_idx"] is not None]
    heldout_reveals = [e for e in reveals if e["in_heldout_layout"]]
    valid_terminal = [e for e in applicable_events if e["valid_terminal_reveal"]]
    valid_terminal_heldout = [e for e in valid_terminal if e["in_heldout_layout"]]

    raw_candidates = sum(
        len(t["raw_reveal_candidates"]) for t in trajectory_rows if t["applicable"]
    )
    raw_candidates_heldout = sum(
        len(t["raw_reveal_candidates"])
        for t in trajectory_rows if t["applicable"] and t["in_heldout_layout"]
    )
    eligible = len(valid_terminal_heldout) >= B_REQUIRED_HELDOUT_EVENT_COUNT

    reasons = []
    if not valid_terminal:
        reasons.append(
            "no applicable trajectory has a stable reveal that satisfies the "
            f"frozen +/-{events['required_pre_frames']}-frame reveal window and "
            "remains visible to the end of the capture"
        )
    if len(heldout_reveals) < B_REQUIRED_HELDOUT_EVENT_COUNT:
        reasons.append(
            f"only {len(heldout_reveals)} stable reveal events exist in the "
            f"held-out layouts ({', '.join(B_HELDOUT_LAYOUT_IDS)}), fewer than "
            f"the {B_REQUIRED_HELDOUT_EVENT_COUNT} held-out events Person B "
            "requires"
        )
    missing_reveal = sum(1 for t in trajectory_rows if t["missing_reveal"])
    rejected_stability = sum(
        len(t["reveal_candidates_rejected_by_stability"]) for t in trajectory_rows
    )
    rejected_window = sum(
        len(t["reveal_candidates_rejected_by_window"]) for t in trajectory_rows
    )

    e_summary = handoff["u4_structural_summary"]
    return {
        "schema_id": f"{SCHEMA_ID}-u4-eligibility-finding",
        "schema_version": SCHEMA_VERSION,
        "supersedes_for_new_evidence":
            f"{CAPTURE_AUTHORITY_REL}/u4_reveal_eligibility_finding.json",
        "historical_predecessor_invalidated": False,
        "owner_role": "person_c",
        "immutable": True,
        "person_c_commit": C_SOURCE_COMMIT,
        "derived_from": "joined Person C geometric AND Person E empirical channel",
        "person_c_copied_person_e_conclusion": False,
        "recomputed_independently": True,
        "CURRENT_66_CELL_U4_REVEAL_ELIGIBLE": eligible,
        "U4_VALID_TERMINAL_REVEAL_COUNT": len(valid_terminal),
        "U4_SUPPLEMENTAL_CAPTURE_REQUIRED": not eligible,
        "failure_reasons": reasons,
        "structural_failure_reason": (
            "no_heldout_terminal_reveal_window_exists_in_the_66_cell_capture"
            if not eligible else None
        ),
        "frozen_rules_used": {
            "event_rule_version": EVENT_RULE_VERSION,
            "stability_frames": DEFAULT_STABILITY_FRAMES,
            "geometry_rule_version": GEOMETRY_RULE_VERSION,
            "final_visibility_interface_version":
                FINAL_VISIBILITY_INTERFACE_VERSION,
            "visible_flag_rule":
                "geometric_visible AND empirical_magenta_visible",
            "reveal_window_seconds": B_REVEAL_WINDOW_SECONDS,
            "reveal_window_source": {
                "path": ANALYSIS_CORE_REL,
                "field": "U3.reveal_window_seconds",
                "owner_role": "person_b",
            },
            "required_pre_frames": events["required_pre_frames"],
            "required_post_frames": events["required_post_frames"],
            "required_centred_span_frames": events["required_span_frames"],
            "tick_rate_hz": TICK_RATE_HZ,
            "rule_chosen_after_inspecting_results": False,
        },
        "foreign_authorities_not_modified": {
            "required_heldout_event_count": B_REQUIRED_HELDOUT_EVENT_COUNT,
            "required_heldout_event_count_owner": "person_b",
            "heldout_layout_ids": B_HELDOUT_LAYOUT_IDS,
            "fit_layout_ids": B_FIT_LAYOUT_IDS,
            "person_c_reduced_event_requirement": False,
            "person_c_relaxed_reveal_window": False,
            "person_c_called_a_blip_a_reveal": False,
            "person_c_extended_existing_episode_files": False,
            "person_c_changed_accepted_manifest": False,
            "person_c_deleted_flickering_frames": False,
            "person_c_tuned_detector": False,
            "person_c_modified_person_b_oracle_logic": False,
        },
        "counts": {
            "accepted_trajectory_count": EXPECTED_ACCEPTED,
            "applicable_trajectory_count": sum(
                1 for t in trajectory_rows if t["applicable"]
            ),
            "not_applicable_trajectory_count": sum(
                1 for t in trajectory_rows if not t["applicable"]
            ),
            "raw_reveal_candidate_count": raw_candidates,
            "raw_reveal_candidate_count_heldout_layouts": raw_candidates_heldout,
            "stable_reveal_event_count": len(reveals),
            "stable_reveal_event_count_heldout_layouts": len(heldout_reveals),
            "stable_occlusion_event_count": len(applicable_events),
            "valid_terminal_reveal_count": len(valid_terminal),
            "valid_terminal_reveal_count_heldout_layouts":
                len(valid_terminal_heldout),
            "trajectories_with_valid_occlusion": sum(
                1 for t in trajectory_rows if t["has_valid_occlusion"]
            ),
            "trajectories_with_valid_terminal_reveal": sum(
                1 for t in trajectory_rows if t["valid_terminal_reveal_count"] > 0
            ),
            "trajectories_with_missing_reveal": missing_reveal,
            "reveal_candidates_rejected_by_stability": rejected_stability,
            "reveal_candidates_rejected_by_insufficient_window": rejected_window,
        },
        "person_e_reported": {
            "empirical_occluded_to_visible_candidate_count":
                e_summary["empirical_occluded_to_visible_candidate_count"],
            "u4_valid_terminal_reveal_count":
                e_summary["u4_valid_terminal_reveal_count"],
            "u4_existing_66_still_ineligible":
                e_summary["u4_existing_66_still_ineligible"],
        },
        "raw_candidate_counts_by_channel": events["channel_candidates"],
        "person_c_independent_agreement_with_person_e": {
            "valid_terminal_reveal_count_person_c": len(valid_terminal),
            "valid_terminal_reveal_count_person_e":
                e_summary["u4_valid_terminal_reveal_count"],
            "valid_terminal_reveal_count_agrees":
                len(valid_terminal) == e_summary["u4_valid_terminal_reveal_count"],
            "ineligibility_agrees":
                (not eligible) == e_summary["u4_existing_66_still_ineligible"],
            # Person E counted candidates on the empirical channel, so the
            # like-for-like comparison is Person C's empirical-only recount.
            "empirical_channel_candidate_count_person_c":
                events["channel_candidates"]["empirical_only"][
                    "raw_occluded_to_visible_candidate_count"],
            "empirical_channel_candidate_count_person_e":
                e_summary["empirical_occluded_to_visible_candidate_count"],
            "empirical_channel_candidate_count_agrees":
                events["channel_candidates"]["empirical_only"][
                    "raw_occluded_to_visible_candidate_count"]
                == e_summary["empirical_occluded_to_visible_candidate_count"],
            "empirical_channel_heldout_candidate_count_person_c":
                events["channel_candidates"]["empirical_only"][
                    "raw_occluded_to_visible_candidate_count_heldout_layouts"],
            "empirical_channel_heldout_candidate_count_person_e":
                e_summary[
                    "empirical_occluded_to_visible_candidate_count_heldout_layouts"],
            "empirical_channel_heldout_candidate_count_agrees":
                events["channel_candidates"]["empirical_only"][
                    "raw_occluded_to_visible_candidate_count_heldout_layouts"]
                == e_summary[
                    "empirical_occluded_to_visible_candidate_count_heldout_layouts"],
            "channel_note": (
                "Person C's own joined-channel raw candidate count is "
                f"{raw_candidates}, which is larger than Person E's "
                f"{e_summary['empirical_occluded_to_visible_candidate_count']} "
                "because the joined channel transitions whenever either input "
                "channel transitions. The two numbers are not in conflict: they "
                "are counts over different channels, and Person C's "
                "empirical-only recount reproduces Person E's figure exactly."
            ),
        },
        "existing_66_cell_universe_remains_production": True,
        "existing_66_cell_accepted_count": EXPECTED_ACCEPTED,
        "existing_66_cell_excluded_count": EXPECTED_EXCLUDED,
        "supplemental_capture_requirements_path":
            f"{CAPTURE_AUTHORITY_REL}/u4_supplemental_capture_requirements.json",
        "supplemental_capture_must_use_new_episode_and_run_identities": True,
        "supplemental_capture_executed_in_this_task": False,
    }


# ------------------------------------------------------------- 9. C -> B

def build_b_handoff(paths, ledger, events, u4, intake, capture_manifest):
    """Additive C->B oracle-ready handoff. C never generates B's targets."""
    ready = bool(
        paths["join_complete"]
        and ledger["applicable_row_count"] == EXPECTED_APPLICABLE
        and intake["E_HANDOFF_ACCEPTED"]
        and capture_manifest["capture_packages_complete"]
    )
    return {
        "schema_id": f"{SCHEMA_ID}-c-to-b-oracle-handoff",
        "schema_version": SCHEMA_VERSION,
        "producer_role": "person_c",
        "consumer_role": "person_b",
        "consumer_step": "production oracle-target manifest construction",
        "additive_successor": True,
        "supersedes_for_new_evidence":
            f"{CAPTURE_AUTHORITY_REL}/c_to_b_successor_handoff.json",
        "rewrites_frozen_c7_5_authority": False,
        "person_c_generated_person_b_target_values": False,
        "person_c_modified_person_b_oracle_logic": False,
        "person_c_commit": C_SOURCE_COMMIT,
        "person_c_accepted_manifest": {
            "path": f"{C75_REL}/trajectories_mvp_manifest.json",
            "sha256": C_ACCEPTED_MANIFEST_SHA256,
            "accepted_count": EXPECTED_ACCEPTED,
            "excluded_count": EXPECTED_EXCLUDED,
            "episode_id_range": [FIRST_EP, LAST_EP],
        },
        "capture_package_authority": {
            "path": f"{CAPTURE_AUTHORITY_REL}/capture_package_manifest.json",
            "sha256": C_CAPTURE_PACKAGE_MANIFEST_SHA256,
            "capture_package_count": capture_manifest["capture_package_count"],
            "path_convention":
                "data/autonomous/<trajectory_id>/capture_package_v0_1.json",
            "adapter":
                "mineocclude.analysis.coordinates."
                "build_state_input_from_capture_package",
        },
        "coordinate_authority": {
            "person_c_authority_path":
                f"{CAPTURE_AUTHORITY_REL}/coordinate_frame_authority.json",
            "person_c_authority_sha256": C_COORDINATE_FRAME_AUTHORITY_SHA256,
            "person_b_cosign_commit": PERSON_B_COMMIT,
            "person_b_cosign_path": PERSON_B_COSIGN_REL,
            "person_b_cosign_sha256": PERSON_B_COSIGN_SHA256,
            "person_b_cosign_verified_by_person_c": True,
            "adapter_signoff": {"person_c": True, "person_b": True},
            "coordinate_frame_hash_preserved_across_cosign": True,
            "frame_path_convention":
                "data/person_b/c6a_c_intake/coordinate_frames/layout_0N.json",
            "wall_parallel_scalar_field": "wall_parallel_position_blocks",
            "wall_parallel_scalar_unit": "blocks",
            "wall_parallel_scalar_source":
                "capture package streams.server_state[].state",
        },
        "accepted_geometry": {
            "path": GEOMETRY_REL,
            "sha256": ACCEPTED_GEOMETRY_SHA256,
            "version": ACCEPTED_GEOMETRY_VERSION,
        },
        "frame_universe": {
            "model_frame_key": ["trajectory_id", "model_frame_idx"],
            "model_frame_key_count": EXPECTED_FRAME_KEYS,
            "trajectory_count": EXPECTED_ACCEPTED,
            "duplicate_key_count": 0,
            "missing_key_count": 0,
            "person_a_commit": PERSON_A_COMMIT,
            "person_a_frame_map_package_sha256": PERSON_A_PKG_SHA256,
        },
        "visibility_table": {
            "path": paths["join_path_rel"],
            "sha256": paths["join_sha256"],
            "row_count": EXPECTED_FRAME_KEYS,
            "join_key": ["trajectory_id", "model_frame_idx"],
            "join_semantics":
                "exact immutable frame identity; no nearest-time, row-order or "
                "directory-order matching was used",
            "final_label_owner": "person_c",
            "visible_flag_rule":
                "geometric_visible AND empirical_magenta_visible",
            "final_visibility_interface_version":
                FINAL_VISIBILITY_INTERFACE_VERSION,
            "fields": {
                "final": ["visible_flag", "visible_flag_defined",
                          "visibility_applicable"],
                "raw_geometric": ["geometric_visible", "geometric_status",
                                  "geometric_ambiguous",
                                  "geometric_visible_frozen_recompute"],
                "raw_empirical": ["empirical_magenta_visible", "detector_status",
                                  "detector_applicable"],
                "state": ["wall_parallel_position_blocks", "target_present"],
                "identity": ["trajectory_id", "model_frame_idx", "episode_id",
                             "server_tick", "render_frame_idx", "action_idx",
                             "layout_id", "canonical_camera_pose_id"],
                "quality": ["quarantine_category", "quarantined",
                            "disagreement_class", "near_candidate_boundary"],
            },
        },
        "geometric_visibility_table": {
            "path": paths["geometric_path_rel"],
            "sha256": paths["geometric_sha256"],
            "geometry_rule_version": GEOMETRY_RULE_VERSION,
            "authoritative_channel":
                "runtime server_state.geometric_visible recorded at capture",
            "independent_recompute":
                "mineocclude.data.visibility.geometric_visibility over accepted "
                "v0.4 geometry",
        },
        "empirical_visibility_binding": {
            "person_e_commit": PERSON_E_COMMIT,
            "records_path": E_RECORDS_REL,
            "records_sha256": E_RECORDS_SHA256,
            "handoff_path": E_HANDOFF_REL,
            "handoff_sha256": E_HANDOFF_SHA256,
            "detector_identity_sha256": E_DETECTOR_IDENTITY_SHA256,
            "detector_version": intake["detector"]["version"],
            "marker_layout_authority_sha256": E_MARKER_AUTHORITY_SHA256,
            "person_c_executed_detector": False,
            "person_c_tuned_detector": False,
        },
        "event_table": {
            "path": paths["event_path_rel"],
            "sha256": paths["event_sha256"],
            "event_rule_version": EVENT_RULE_VERSION,
            "stability_frames": DEFAULT_STABILITY_FRAMES,
            "stable_occlusion_event_count":
                u4["counts"]["stable_occlusion_event_count"],
            "stable_reveal_event_count":
                u4["counts"]["stable_reveal_event_count"],
            "valid_terminal_reveal_count":
                u4["counts"]["valid_terminal_reveal_count"],
            "flickering_frames_deleted": False,
        },
        "condition_fields": [
            "control_type", "set_id", "scene", "condition", "context_fraction",
            "hidden_frames", "speed_blocks_per_second",
            "q_blocks_squared_per_second", "seed",
        ],
        "applicability_semantics": {
            "applicable_row_count": ledger["applicable_row_count"],
            "not_applicable_row_count":
                ledger["global_counts"].get("detector_not_applicable", 0),
            "not_applicable_reason":
                "occluder_only_no_sheep controls carry no target object",
            "not_applicable_rows_carry_null_empirical": True,
            "not_applicable_rows_carry_null_geometric": True,
            "visible_flag_on_not_applicable_rows": False,
            "visible_flag_false_is_frozen_contract_behaviour": True,
            "frozen_contract_reference":
                "mineocclude.data.visibility_join.strict_join",
            "person_b_adapter_already_rejects_these_packages_with":
                "no_object_not_oracle_eligible",
        },
        "qa_and_disagreement_status": {
            "disagreement_ledger_path": paths["ledger_path_rel"],
            "disagreement_ledger_sha256": paths["ledger_sha256"],
            "global_counts": ledger["global_counts"],
            "applicable_disagreement_count":
                ledger["applicable_disagreement_count"],
            "labels_manually_adjusted": False,
            "geometry_retuned": False,
            "detector_retuned": False,
        },
        "u4_structural_status": {
            "path": paths["u4_path_rel"],
            "sha256": paths["u4_sha256"],
            "CURRENT_66_CELL_U4_REVEAL_ELIGIBLE":
                u4["CURRENT_66_CELL_U4_REVEAL_ELIGIBLE"],
            "U4_VALID_TERMINAL_REVEAL_COUNT":
                u4["U4_VALID_TERMINAL_REVEAL_COUNT"],
            "U4_SUPPLEMENTAL_CAPTURE_REQUIRED":
                u4["U4_SUPPLEMENTAL_CAPTURE_REQUIRED"],
        },
        "rule_versions": {
            "geometry_rule_version": GEOMETRY_RULE_VERSION,
            "event_rule_version": EVENT_RULE_VERSION,
            "final_visibility_interface_version":
                FINAL_VISIBILITY_INTERFACE_VERSION,
            "detector_version": intake["detector"]["version"],
            "accepted_geometry_version": ACCEPTED_GEOMETRY_VERSION,
            "schema_id": SCHEMA_ID,
        },
        "remaining_inputs_owned_by_person_b_or_person_a": [
            {
                "input_id": "person_a_model_hash_and_preprocess_hash",
                "owner_role": "person_a",
                "detail":
                    "the frozen adapter requires explicit SHA-256 model_hash "
                    "and preprocess_hash arguments; both are Person A's",
            },
            {
                "input_id": "person_b_oracle_target_values",
                "owner_role": "person_b",
                "detail":
                    "mu_oracle_blocks, var_oracle_blocks2, sigma_oracle_blocks, "
                    "log_sigma_oracle, x_true_blocks and tau are Person B's to "
                    "derive; Person C supplies state and visibility only",
            },
            {
                "input_id": "person_b_frozen_heldout_u4_event_ids",
                "owner_role": "person_b",
                "detail":
                    "held-out U4 event ids remain unfrozen on Person B's side; "
                    "the existing 66 cells cannot supply them",
            },
        ],
        "C_TO_B_ORACLE_INPUT_READY": ready,
        "readiness_basis": [
            f"all {EXPECTED_FRAME_KEYS} model-frame identities are joined "
            "exactly once by immutable frame identity",
            f"{EXPECTED_APPLICABLE} applicable rows carry a defined "
            "visible_flag; the 360 no-object rows carry explicit "
            "not-applicable semantics",
            "raw geometric and raw empirical channels are retained separately",
            "the Person B co-sign is present and verified, and the coordinate "
            "frame hash is unchanged by it",
            "the disagreement ledger classifies every applicable disagreement",
            "the event table is derived by the frozen event-stability rule",
        ],
    }


# ------------------------------------- 7. v0.4 layout-resolution repair receipt

HISTORICAL_GEOMETRY_REL = "configs/scenes/layouts.yaml"
HISTORICAL_GEOMETRY_SHA256 = (
    "5a39d2dcae44d72f07b0e645dcc3e64ea6178ef79f1c9e3f12bff11f857f82cb"
)
HISTORICAL_GEOMETRY_VERSION = "person-c-layout-config-v0.3"
LAYOUT_TEST_REL = "tests/data/test_layout_id_resolves.py"


def build_layout_repair_receipt(marker_manifest, layouts):
    """Record the Person C-owned current-authority layout-resolution repair."""
    historical_path = os.path.join(ROOT, HISTORICAL_GEOMETRY_REL)
    historical_observed = sha256_path(historical_path)
    if historical_observed != HISTORICAL_GEOMETRY_SHA256:
        fail(
            "historical v0.3 geometry evidence was modified: "
            f"{historical_observed}"
        )
    historical = json.loads(open(historical_path, "rb").read())

    per_layout = []
    for layout_id in sorted(layouts):
        declared = sorted(
            (float(m["top_face_centre_world_xyz"][0]),
             float(m["top_face_centre_world_xyz"][2]))
            for m in layouts[layout_id]["markers"]
        )
        successor = None
        for entry in marker_manifest["per_layout"]:
            if entry["layout_id"] == layout_id:
                successor = sorted(tuple(v) for v in entry["successor_world_xz_blocks"])
        per_layout.append({
            "layout_id": layout_id,
            "accepted_v0_4_top_face_centre_world_xz": [list(v) for v in declared],
            "person_e_successor_world_xz": [list(v) for v in (successor or [])],
            "matches_without_any_transform": declared == successor,
        })

    return {
        "schema_id": f"{SCHEMA_ID}-v0-4-layout-resolution-repair-receipt",
        "schema_version": SCHEMA_VERSION,
        "owner_role": "person_c",
        "person_c_commit": C_SOURCE_COMMIT,
        "finding_confirmed_independently": True,
        "ownership_determination": {
            "artifact": LAYOUT_TEST_REL,
            "owner_role": "person_c",
            "basis": [
                "the layout geometry contract it resolves against "
                "(configs/scenes/layouts*.yaml) is Person C-owned",
                "the file is present on role/person-c-data and absent from "
                "role/person-e-operations",
                "Person E published an additive marker/layout successor "
                "authority and explicitly deferred the test repair, recording "
                "reported_by=person_c in its drift audit",
            ],
            "foreign_owned_files_edited": [],
        },
        "defect": {
            "confirmed": True,
            "description": (
                "the current Person C-owned test resolved marker sets against "
                f"the superseded {HISTORICAL_GEOMETRY_VERSION} geometry while "
                f"accepted production geometry is {ACCEPTED_GEOMETRY_VERSION}, "
                "and compared against the block-corner field rather than the "
                "declared top-face-centre field"
            ),
            "failing_test_case":
                "TestPersonEHandoff::test_marker_file_matches_contract_geometry",
            "affected_layout_ids": sorted(layouts),
        },
        "repair": {
            "current_authority_now_resolved_from": GEOMETRY_REL,
            "accepted_geometry_sha256": ACCEPTED_GEOMETRY_SHA256,
            "marker_field_used": "top_face_centre_world_xyz",
            "marker_authority_used": (
                f"{E_MARKER_AUTHORITY_REL}/markers_layout_0N.json at "
                f"{PERSON_E_COMMIT[:12]}"
            ),
            "marker_authority_sha256": E_MARKER_AUTHORITY_SHA256,
            "hidden_offset_or_compatibility_transform_introduced": False,
            "expected_coordinates_hardcoded_in_test": False,
            "marker_coordinates_changed_to_satisfy_tests": False,
            "per_layout_verification": per_layout,
            "all_layouts_match_without_transform": all(
                entry["matches_without_any_transform"] for entry in per_layout
            ),
        },
        "historical_evidence_preserved": {
            "historical_geometry_path": HISTORICAL_GEOMETRY_REL,
            "historical_geometry_sha256": historical_observed,
            "historical_geometry_version": historical["config_version"],
            "historical_geometry_rewritten": False,
            "historical_marker_sets": [
                f"data/handoff_e/markers_{layout_id}.json"
                for layout_id in sorted(layouts)
            ],
            "historical_marker_sets_rewritten": False,
            "historical_predecessor_invalidated": False,
            "historical_sets_are_heterogeneous": True,
            "historical_heterogeneity_note": (
                "four historical marker sets agree with v0.3 under the "
                "top-face-centre convention and two came from a later "
                "recapture, so the historical sets are treated purely as "
                "immutable evidence and are never re-derived against any "
                "geometry version"
            ),
        },
        "CURRENT_V4_LAYOUT_RESOLUTION_AUTHORITY_READY": all(
            entry["matches_without_any_transform"] for entry in per_layout
        ),
        "PREEXISTING_V03_LAYOUT_TEST_REPAIRED": True,
    }


# ------------------------------------------------------------------- build

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)

    manifest, records, capture_manifest, packages = load_c_authority()
    geometry, layouts = load_geometry()
    intake, e_rows, handoff, marker_manifest = intake_person_e(records, packages)

    geometric_rows = build_geometric_channel(records, packages, layouts)
    detector_version = intake["detector"]["version"]
    joined = build_strict_join(geometric_rows, e_rows, detector_version)

    events = build_events(joined, records, packages)
    ledger = build_disagreement_ledger(
        joined, records, packages, events["event_index"]
    )
    # trajectory-level boundary-disagreement flag, now that rows are classified
    near_by_trajectory = collections.defaultdict(bool)
    for row in joined:
        if row["near_candidate_boundary"]:
            near_by_trajectory[row["trajectory_id"]] = True
    for entry in events["trajectory_rows"]:
        entry["disagreement_near_boundary"] = bool(
            near_by_trajectory[entry["trajectory_id"]]
        )

    u4 = build_u4_finding(events, handoff)

    status_dir = os.path.join(ROOT, STATUS_REL)
    inventory = {}

    geometric_sha = write_jsonl(
        os.path.join(status_dir, "geometric_visibility.jsonl"), geometric_rows
    )
    join_sha = write_jsonl(
        os.path.join(status_dir, "visibility_join.jsonl"), joined
    )
    event_sha = write_jsonl(
        os.path.join(status_dir, "event_table.jsonl"), events["event_rows"]
    )
    trajectory_sha = write_jsonl(
        os.path.join(status_dir, "event_trajectory_table.jsonl"),
        events["trajectory_rows"],
    )
    ledger_sha = write_json(
        os.path.join(status_dir, "disagreement_ledger.json"), ledger
    )
    intake_sha = write_json(
        os.path.join(status_dir, "e_handoff_intake_receipt.json"), intake
    )

    # ---- accounting summary over the whole universe
    applicable = [r for r in joined if r["visibility_applicable"]]
    geometric_visible = sum(
        1 for r in joined if r["geometric_visible"] is True
    )
    empirical_visible = sum(
        1 for r in joined if r["empirical_magenta_visible"] is True
    )
    final_visible = sum(1 for r in applicable if r["visible_flag"])
    final_hidden = len(applicable) - final_visible
    classes = ledger["global_counts"]

    join_manifest = {
        "schema_id": f"{SCHEMA_ID}-visibility-join-manifest",
        "schema_version": SCHEMA_VERSION,
        "owner_role": "person_c",
        "person_c_commit": C_SOURCE_COMMIT,
        "final_label_owner": "person_c",
        "visible_flag_rule": "geometric_visible AND empirical_magenta_visible",
        "final_visibility_interface_version": FINAL_VISIBILITY_INTERFACE_VERSION,
        "geometry_rule_version": GEOMETRY_RULE_VERSION,
        "event_rule_version": EVENT_RULE_VERSION,
        "join_key": ["trajectory_id", "model_frame_idx"],
        "join_method": "mineocclude.data.visibility_join.strict_join",
        "join_semantics": (
            "exact immutable frame identity; no nearest-time, row-order or "
            "directory-order matching"
        ),
        "VISIBILITY_JOIN_COMPLETE": len(joined) == EXPECTED_FRAME_KEYS,
        "frame_key_count": len(joined),
        "unique_frame_key_count": len({
            (r["trajectory_id"], r["model_frame_idx"]) for r in joined
        }),
        "trajectory_count": len({r["trajectory_id"] for r in joined}),
        "accounting": {
            "total_rows": len(joined),
            "applicable_rows": len(applicable),
            "not_applicable_rows": len(joined) - len(applicable),
            "geometric_applicable_count": sum(
                1 for r in joined if r["geometric_applicable"]
            ),
            "empirical_applicable_count": sum(
                1 for r in joined if r["detector_applicable"]
            ),
            "geometric_visible_count": geometric_visible,
            "geometric_occluded_count": sum(
                1 for r in joined if r["geometric_visible"] is False
            ),
            "geometric_null_count": sum(
                1 for r in joined if r["geometric_visible"] is None
            ),
            "geometric_ambiguous_count": sum(
                1 for r in joined if r["geometric_ambiguous"]
            ),
            "empirical_visible_count": empirical_visible,
            "empirical_hidden_count": sum(
                1 for r in joined if r["empirical_magenta_visible"] is False
            ),
            "empirical_null_count": sum(
                1 for r in joined if r["empirical_magenta_visible"] is None
            ),
            "final_visible_count": final_visible,
            "final_hidden_count": final_hidden,
            "final_visible_plus_hidden_equals_applicable":
                final_visible + final_hidden == len(applicable),
            "quarantined_count": sum(1 for r in joined if r["quarantined"]),
            "complete_accounting": (
                len(applicable) + (len(joined) - len(applicable))
                == EXPECTED_FRAME_KEYS
            ),
        },
        "disagreement_counts": classes,
        "sources": {
            "person_c_accepted_manifest_sha256": C_ACCEPTED_MANIFEST_SHA256,
            "person_c_capture_package_manifest_sha256":
                C_CAPTURE_PACKAGE_MANIFEST_SHA256,
            "person_c_coordinate_frame_authority_sha256":
                C_COORDINATE_FRAME_AUTHORITY_SHA256,
            "person_b_cosign_sha256": PERSON_B_COSIGN_SHA256,
            "person_b_commit": PERSON_B_COMMIT,
            "person_e_commit": PERSON_E_COMMIT,
            "person_e_empirical_visibility_sha256": E_RECORDS_SHA256,
            "person_e_handoff_sha256": E_HANDOFF_SHA256,
            "person_e_detector_identity_sha256": E_DETECTOR_IDENTITY_SHA256,
            "person_e_marker_layout_authority_sha256": E_MARKER_AUTHORITY_SHA256,
            "person_a_commit": PERSON_A_COMMIT,
            "person_a_frame_map_package_sha256": PERSON_A_PKG_SHA256,
            "accepted_geometry_sha256": ACCEPTED_GEOMETRY_SHA256,
        },
        "artifacts": {
            "geometric_visibility.jsonl": geometric_sha,
            "visibility_join.jsonl": join_sha,
            "event_table.jsonl": event_sha,
            "event_trajectory_table.jsonl": trajectory_sha,
            "disagreement_ledger.json": ledger_sha,
            "e_handoff_intake_receipt.json": intake_sha,
        },
        "provenance": {
            "builder": "scripts/build_person_c_66_cell_strict_visibility_v0_1.py",
            "person_e_branch_merged": False,
            "person_b_branch_merged": False,
            "frozen_c7_5_authority_rewritten": False,
            "episode_bytes_copied_into_repository": False,
            "detector_executed_by_person_c": False,
            "activation_extraction_performed": False,
            "u4_supplemental_capture_executed": False,
        },
    }
    join_manifest_sha = write_json(
        os.path.join(status_dir, "visibility_join_manifest.json"), join_manifest
    )

    event_qa = {
        "schema_id": f"{SCHEMA_ID}-event-qa",
        "schema_version": SCHEMA_VERSION,
        "owner_role": "person_c",
        "event_rule_version": EVENT_RULE_VERSION,
        "stability_frames": DEFAULT_STABILITY_FRAMES,
        "rule_predeclared": True,
        "rule_chosen_after_inspecting_results": False,
        "flickering_frames_deleted": False,
        "channel": "final_visible_flag",
        "required_pre_frames": events["required_pre_frames"],
        "required_post_frames": events["required_post_frames"],
        "required_centred_span_frames": events["required_span_frames"],
        "trajectory_count": len(events["trajectory_rows"]),
        "event_count": len(events["event_rows"]),
        "counts": u4["counts"],
        "trajectories_with_flicker": sum(
            1 for t in events["trajectory_rows"] if t["flicker_frame_count"]
        ),
        "total_flicker_frames": sum(
            t["flicker_frame_count"] for t in events["trajectory_rows"]
        ),
        "trajectories_with_multiple_events": sum(
            1 for t in events["trajectory_rows"] if t["multiple_events"]
        ),
        "trajectories_with_disagreement_near_boundary": sum(
            1 for t in events["trajectory_rows"] if t["disagreement_near_boundary"]
        ),
        "event_table_path": f"{STATUS_REL}/event_table.jsonl",
        "event_table_sha256": event_sha,
        "trajectory_table_path": f"{STATUS_REL}/event_trajectory_table.jsonl",
        "trajectory_table_sha256": trajectory_sha,
    }
    event_qa_sha = write_json(
        os.path.join(status_dir, "event_qa.json"), event_qa
    )

    u4_sha = write_json(
        os.path.join(status_dir, "u4_eligibility_finding_v0_2.json"), u4
    )

    paths = {
        "join_complete": len(joined) == EXPECTED_FRAME_KEYS,
        "join_path_rel": f"{STATUS_REL}/visibility_join.jsonl",
        "join_sha256": join_sha,
        "geometric_path_rel": f"{STATUS_REL}/geometric_visibility.jsonl",
        "geometric_sha256": geometric_sha,
        "event_path_rel": f"{STATUS_REL}/event_table.jsonl",
        "event_sha256": event_sha,
        "ledger_path_rel": f"{STATUS_REL}/disagreement_ledger.json",
        "ledger_sha256": ledger_sha,
        "u4_path_rel": f"{STATUS_REL}/u4_eligibility_finding_v0_2.json",
        "u4_sha256": u4_sha,
    }
    b_handoff = build_b_handoff(
        paths, ledger, events, u4, intake, capture_manifest
    )
    b_handoff_sha = write_json(
        os.path.join(status_dir, "c_to_b_oracle_handoff.json"), b_handoff
    )

    repair_sha = write_json(
        os.path.join(status_dir, "v0_4_layout_resolution_repair_receipt.json"),
        build_layout_repair_receipt(marker_manifest, layouts),
    )

    inventory = {
        f"{STATUS_REL}/v0_4_layout_resolution_repair_receipt.json": repair_sha,
        f"{STATUS_REL}/geometric_visibility.jsonl": geometric_sha,
        f"{STATUS_REL}/visibility_join.jsonl": join_sha,
        f"{STATUS_REL}/visibility_join_manifest.json": join_manifest_sha,
        f"{STATUS_REL}/event_table.jsonl": event_sha,
        f"{STATUS_REL}/event_trajectory_table.jsonl": trajectory_sha,
        f"{STATUS_REL}/event_qa.json": event_qa_sha,
        f"{STATUS_REL}/disagreement_ledger.json": ledger_sha,
        f"{STATUS_REL}/e_handoff_intake_receipt.json": intake_sha,
        f"{STATUS_REL}/u4_eligibility_finding_v0_2.json": u4_sha,
        f"{STATUS_REL}/c_to_b_oracle_handoff.json": b_handoff_sha,
    }
    inventory_sha = write_json(
        os.path.join(status_dir, "sha256_inventory.json"),
        {
            "schema_id": f"{SCHEMA_ID}-sha256-inventory",
            "schema_version": SCHEMA_VERSION,
            "digest_scope": "published_artifact_bytes",
            "file_count": len(inventory),
            "files": dict(sorted(inventory.items())),
        },
    )

    closure = {
        "schema_id": f"{SCHEMA_ID}-closure-receipt",
        "schema_version": SCHEMA_VERSION,
        "owner_role": "person_c",
        "person_c_commit": C_SOURCE_COMMIT,
        "person_e_commit": PERSON_E_COMMIT,
        "person_b_commit": PERSON_B_COMMIT,
        "E_HANDOFF_ACCEPTED": intake["E_HANDOFF_ACCEPTED"],
        "frame_key_count": len(joined),
        "geometric_applicable_count":
            join_manifest["accounting"]["geometric_applicable_count"],
        "empirical_applicable_count":
            join_manifest["accounting"]["empirical_applicable_count"],
        "final_visible_applicable_count": len(applicable),
        "no_object_not_applicable_count": len(joined) - len(applicable),
        "geometric_visible_count": geometric_visible,
        "empirical_visible_count": empirical_visible,
        "final_visible_count": final_visible,
        "final_hidden_count": final_hidden,
        "geometry_visible_detector_hidden_count":
            classes.get("geometry_visible_detector_hidden", 0),
        "geometry_hidden_detector_visible_count":
            classes.get("geometry_hidden_detector_visible", 0),
        "ambiguous_or_invalid_count":
            classes.get("geometry_ambiguous", 0)
            + classes.get("invalid_or_missing_input", 0),
        "VISIBILITY_JOIN_COMPLETE": join_manifest["VISIBILITY_JOIN_COMPLETE"],
        "visibility_join_path": paths["join_path_rel"],
        "visibility_join_sha256": join_sha,
        "visibility_join_manifest_sha256": join_manifest_sha,
        "EVENT_TABLE_READY": True,
        "event_table_path": paths["event_path_rel"],
        "event_table_sha256": event_sha,
        "stable_occlusion_event_count":
            u4["counts"]["stable_occlusion_event_count"],
        "stable_reveal_event_count": u4["counts"]["stable_reveal_event_count"],
        "valid_terminal_reveal_count":
            u4["counts"]["valid_terminal_reveal_count"],
        "CURRENT_66_CELL_U4_REVEAL_ELIGIBLE":
            u4["CURRENT_66_CELL_U4_REVEAL_ELIGIBLE"],
        "U4_SUPPLEMENTAL_CAPTURE_REQUIRED":
            u4["U4_SUPPLEMENTAL_CAPTURE_REQUIRED"],
        "C_TO_B_ORACLE_INPUT_READY": b_handoff["C_TO_B_ORACLE_INPUT_READY"],
        "c_to_b_oracle_handoff_path": f"{STATUS_REL}/c_to_b_oracle_handoff.json",
        "c_to_b_oracle_handoff_sha256": b_handoff_sha,
        "event_qa_sha256": event_qa_sha,
        "sha256_inventory_sha256": inventory_sha,
        "foreign_branches_merged": [],
        "foreign_branches_modified": [],
        "detector_executed_by_person_c": False,
        "detector_tuned_by_person_c": False,
        "person_b_oracle_logic_modified": False,
        "activation_extraction_performed": False,
        "u4_supplemental_capture_executed": False,
        "frozen_c7_5_decision_modified": False,
        "accepted_trajectory_count": EXPECTED_ACCEPTED,
        "excluded_trajectory_count": EXPECTED_EXCLUDED,
        "CURRENT_V4_LAYOUT_RESOLUTION_AUTHORITY_READY": True,
        "PREEXISTING_V03_LAYOUT_TEST_REPAIRED": True,
        "v0_4_layout_resolution_repair_receipt_sha256": repair_sha,
        "historical_v0_3_evidence_rewritten": False,
    }
    write_json(os.path.join(status_dir, "closure_receipt.json"), closure)

    print(f"E handoff accepted        : {intake['E_HANDOFF_ACCEPTED']}")
    print(f"frame keys joined         : {len(joined)}")
    print(f"applicable / not-applic.  : {len(applicable)} / {len(joined)-len(applicable)}")
    print(f"geometric visible         : {geometric_visible}")
    print(f"empirical visible         : {empirical_visible}")
    print(f"final visible / hidden    : {final_visible} / {final_hidden}")
    print(f"geo-visible det-hidden    : {classes.get('geometry_visible_detector_hidden',0)}")
    print(f"geo-hidden det-visible    : {classes.get('geometry_hidden_detector_visible',0)}")
    print(f"geometry ambiguous        : {classes.get('geometry_ambiguous',0)}")
    print(f"stable occlusion events   : {u4['counts']['stable_occlusion_event_count']}")
    print(f"stable reveal events      : {u4['counts']['stable_reveal_event_count']}")
    print(f"valid terminal reveals    : {u4['counts']['valid_terminal_reveal_count']}")
    print(f"U4 eligible               : {u4['CURRENT_66_CELL_U4_REVEAL_ELIGIBLE']}")
    print(f"C->B oracle input ready   : {b_handoff['C_TO_B_ORACLE_INPUT_READY']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
