"""Focused validation for the Person C 66-cell capture authority closure.

Asserts the additive successor authority actually closes the Person C-owned
structural contracts Person B's preactivation audit found missing:

  - exactly 66 capture packages for ep12601-ep12666, 0 missing, 0 duplicate;
  - every package accepted by the frozen capture contract, and consumable by
    Person B's frozen oracle adapter once Person B co-signs;
  - every declared server_state / layout_meta source hash still matching;
  - the Person A frame-map binding and model-frame key relationship;
  - one Person C-signed wall-parallel coordinate frame per layout, bound to the
    independently verified accepted geometry, with the sign convention proven
    against runtime axis_pos and Person B's side left unsigned;
  - the C->E empirical visibility request carrying no C-invented thresholds;
  - the C->B successor receipt not claiming a co-sign that does not exist;
  - the U4 terminal-reveal structural finding;
  - the frozen 66 accepted / 0 excluded decision untouched;
  - deterministic byte-identical regeneration.

Person E's detector is never run and no episode is recollected.
"""
import copy
import hashlib
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "src"))

import build_person_c_66_cell_capture_authority_v0_1 as mod  # noqa: E402

from mineocclude.analysis.coordinates import (  # noqa: E402
    CaptureStateHandoffError,
    build_state_input_from_capture_package,
    coordinate_frame_hash,
    validate_coordinate_frame,
)
from mineocclude.data.capture_contract import validate_capture_package  # noqa: E402

STATUS = os.path.join(ROOT, mod.STATUS_REL)
EPISODES = list(range(mod.FIRST_EP, mod.LAST_EP + 1))
LAYOUTS = [f"layout_0{n}" for n in range(1, 7)]


def load(rel_path):
    with open(os.path.join(ROOT, rel_path), "rb") as handle:
        return json.load(handle)


def sha256(rel_path):
    with open(os.path.join(ROOT, rel_path), "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


@pytest.fixture(scope="module")
def package_manifest():
    return load(f"{mod.STATUS_REL}/capture_package_manifest.json")


@pytest.fixture(scope="module")
def frames_index():
    return load(f"{mod.STATUS_REL}/coordinate_frame_authority.json")


@pytest.fixture(scope="module")
def packages(package_manifest):
    return {
        record["episode_id"]: load(record["capture_package_path"])
        for record in package_manifest["records"]
    }


@pytest.fixture(scope="module")
def cosigned_frames():
    """Person C's frames with a simulated Person B co-sign, for adapter tests.

    The co-sign is applied in memory only; the published frames stay unsigned
    on Person B's side.
    """
    frames = {}
    for layout_id in LAYOUTS:
        document = load(f"{mod.FRAMES_REL}/{layout_id}.json")
        document = copy.deepcopy(document)
        document["adapter_signoff"]["person_b"] = True
        frames[layout_id] = document
    return frames


# ------------------------------------------------------ 66 capture packages

def test_exactly_66_capture_packages_no_missing_no_duplicate(package_manifest):
    records = package_manifest["records"]
    assert len(records) == 66
    assert package_manifest["capture_package_count"] == 66
    assert package_manifest["capture_packages_complete"] is True
    assert package_manifest["missing_capture_package_count"] == 0
    assert package_manifest["duplicate_episode_identity_count"] == 0
    assert package_manifest["duplicate_trajectory_identity_count"] == 0
    assert len({r["episode_id"] for r in records}) == 66
    assert len({r["trajectory_id"] for r in records}) == 66
    assert len({r["capture_package_path"] for r in records}) == 66


def test_episode_set_is_exactly_ep12601_through_ep12666(package_manifest):
    assert sorted(r["episode_id"] for r in package_manifest["records"]) == EPISODES
    assert package_manifest["episode_id_range"] == [12601, 12666]


def test_every_capture_package_exists_and_matches_its_declared_sha256(
    package_manifest,
):
    for record in package_manifest["records"]:
        path = record["capture_package_path"]
        assert os.path.exists(os.path.join(ROOT, path)), path
        assert sha256(path) == record["capture_package_sha256"], path
        sidecar = os.path.join(ROOT, path + ".sha256")
        assert os.path.exists(sidecar)
        with open(sidecar, encoding="utf-8") as handle:
            assert handle.read().strip() == record["capture_package_sha256"]


def test_every_package_passes_the_frozen_capture_contract(packages):
    for episode_id, package in sorted(packages.items()):
        result = validate_capture_package(package)
        codes = sorted({item.code.value for item in result.rejections})
        assert result.accepted, f"ep{episode_id} rejected: {codes}"


def test_capture_package_schema_identity_fields(packages, package_manifest):
    by_episode = {r["episode_id"]: r for r in package_manifest["records"]}
    for episode_id, package in sorted(packages.items()):
        record = by_episode[episode_id]
        assert package["schema_version"] == mod.TRAJECTORY_SCHEMA_VERSION
        assert package["person_c_contract_version"] == "0.1"
        assert package["episode_id"] == str(episode_id)
        assert package["trajectory_id"] == record["trajectory_id"]
        assert package["layout_id"] == record["layout_id"]
        assert package["run_id"] == mod.RUN_ID
        assert package["synthetic"] is False
        assert package["exclusion_ledger"] == []
        manifest = package["episode_manifest"]
        assert manifest["status"] == "accepted"
        assert manifest["regime"] == "regime_a"
        assert manifest["tick_rate_hz"] == 20.0
        assert manifest["dt_seconds"] == 0.05
        assert manifest["layout_config_hash"] == mod.ACCEPTED_GEOMETRY_SHA256
        assert manifest["environment_lock_hash"] == mod.ENV_LOCK_SHA256
        assert manifest["code_sha"] == mod.C_SOURCE_COMMIT
        # The seven contract row streams are present and frame-aligned.
        streams = package["streams"]
        expected = package["media"]["frame_count"]
        for name in ("frame_map", "raw_actions", "normalized_actions",
                     "server_state", "client_tick_log", "visibility",
                     "seed_noise"):
            assert len(streams[name]) == expected, f"ep{episode_id}.{name}"


def test_cross_package_capture_identities_are_globally_unique(packages):
    seen = set()
    for package in packages.values():
        for row in package["streams"]["frame_map"]:
            key = (
                row["episode_id"], row["trajectory_id"], row["server_tick"],
                row["render_frame_idx"], row["action_idx"], row["model_frame_idx"],
            )
            assert key not in seen, f"duplicate capture identity {key}"
            seen.add(key)
    assert len(seen) == mod.EXPECTED_MODEL_FRAME_KEYS


def test_model_frame_universe_totals_2468(package_manifest):
    assert package_manifest["total_model_frame_count"] == 2468
    assert package_manifest["expected_model_frame_count"] == 2468


# ------------------------------------------------------ source hash identity

def test_declared_server_state_and_layout_meta_hashes_still_match(packages):
    server_state_ok = layout_meta_ok = 0
    for package in packages.values():
        authority = package["person_c_authority"]
        for role, counter in (("server_state", "server"), ("layout_meta", "layout")):
            declared = authority["source_sha256_inventory"][role]
            path = declared["path"]
            assert os.path.exists(path), path
            digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
            assert digest == declared["sha256"], path
            if counter == "server":
                server_state_ok += 1
            else:
                layout_meta_ok += 1
    assert server_state_ok == 66
    assert layout_meta_ok == 66


def test_verification_receipt_reports_66_verified_state_and_layout_authorities():
    receipt = load(f"{mod.STATUS_REL}/verification_receipt.json")
    inventory = receipt["state_layout_payload_inventory"]
    assert inventory["server_state_authority_count"] == 66
    assert inventory["layout_meta_authority_count"] == 66
    assert inventory["server_state_hashes_valid"] is True
    assert inventory["layout_meta_hashes_valid"] is True
    assert inventory["total_payloads_verified"] == 132
    assert receipt["discrepancy_count"] == 0
    report = receipt["person_b_report"]
    assert report["fold_manifest_observed_sha256"] == report[
        "fold_manifest_declared_sha256"
    ]


def test_verification_receipt_publishes_the_two_person_b_discrepancies():
    receipt = load(f"{mod.STATUS_REL}/verification_receipt.json")
    claims = {c["claim_id"]: c for c in receipt["claim_verification"]}
    ends = claims["every_capture_ends_while_target_is_occluded"]
    assert ends["agrees_with_person_b"] is False
    assert ends["episodes_ending_occluded"] == 60
    assert ends["episodes_ending_visible"] == 6
    assert all(e["set_id"] == "nowall" for e in ends["exceptions"])
    blips = claims["each_transition_is_a_1_to_4_frame_blip"]
    assert blips["agrees_with_person_b"] == "partially"
    assert max(blips["heldout_candidate_run_lengths"]) <= 4
    assert max(blips["all_transition_run_lengths"]) > 4


# ------------------------------------------------- C manifest reconciliation

def test_frozen_accepted_excluded_decision_is_untouched(package_manifest):
    frozen = load(f"{mod.C75_REL}/trajectories_mvp_manifest.json")
    ledger = load(f"{mod.C75_REL}/accepted_excluded_ledger.json")
    assert sha256(f"{mod.C75_REL}/trajectories_mvp_manifest.json") == (
        mod.C_ACCEPTED_MANIFEST_SHA256
    )
    assert frozen["accepted_count"] == 66
    assert frozen["excluded_count"] == 0
    assert ledger["accepted_count"] == 66
    assert ledger["excluded_count"] == 0
    assert ledger["excluded_episode_ids"] == []
    assert package_manifest["accepted_count"] == 66
    assert package_manifest["excluded_count"] == 0
    assert package_manifest["rewrites_c7_5_history"] is False
    closure = load(f"{mod.STATUS_REL}/closure_receipt.json")
    assert closure["frozen_decision_modified"] is False
    assert closure["c7_5_sprint_rerun"] is False
    assert closure["episodes_recollected"] is False
    assert closure["accepted_trajectory_count"] == 66
    assert closure["excluded_trajectory_count"] == 0


def test_every_package_binds_the_c_accepted_manifest_identity(packages):
    for package in packages.values():
        accepted = package["person_c_authority"]["accepted_manifest_identity"]
        assert accepted["sha256"] == mod.C_ACCEPTED_MANIFEST_SHA256
        assert accepted["person_c_commit"] == mod.C_SOURCE_COMMIT
        assert accepted["accepted_count"] == 66
        assert accepted["excluded_count"] == 0


def test_capture_package_records_match_the_frozen_manifest_records(
    package_manifest,
):
    frozen = {
        int(r["episode_id"]): r
        for r in load(f"{mod.C75_REL}/trajectories_mvp_manifest.json")["records"]
    }
    for record in package_manifest["records"]:
        source = frozen[record["episode_id"]]
        assert record["trajectory_id"] == source["trajectory_id"]
        assert record["layout_id"] == source["layout_id"]
        assert record["planned_cell_id"] == source["planned_cell_id"]
        assert record["set_id"] == source["set_id"]
        assert record["control_type"] == source["control_type"]


# ------------------------------------------------------- A frame-map binding

def test_person_a_frame_map_binding(package_manifest, packages):
    binding = package_manifest["person_a_frame_map_binding"]
    assert binding["person_a_commit"] == mod.PERSON_A_COMMIT
    assert binding["package_sha256"] == mod.PERSON_A_PKG_SHA256
    assert binding["model_frame_key_count"] == 2468
    assert binding["duplicate_model_frame_key_count"] == 0
    assert binding["missing_model_frame_key_count"] == 0
    assert binding["person_c_independent_rederivation"] == "exact"
    observed = hashlib.sha256(
        mod.git_show(
            mod.PERSON_A_COMMIT, f"{mod.PERSON_A_PKG_REL}/sha256_inventory.json"
        )
    ).hexdigest()
    assert observed == mod.PERSON_A_PKG_SHA256
    for package in packages.values():
        authority = package["person_c_authority"]["frame_map_authority"]
        assert authority["owner_role"] == "person_a"
        assert authority["package_sha256_inventory_sha256"] == mod.PERSON_A_PKG_SHA256
        assert authority["person_c_agreement_with_person_a"] == "exact"


def test_model_frame_key_relationship_is_the_identity_relation(packages):
    for episode_id, package in sorted(packages.items()):
        relationship = package["person_c_authority"]["model_frame_key_relationship"]
        assert relationship["model_facing_key"] == ["trajectory_id", "model_frame_idx"]
        assert relationship["zero_based_dense"] is True
        assert relationship["verified_against_person_a_frame_map"] is True
        for row in package["streams"]["frame_map"]:
            assert (
                row["server_tick"]
                == row["render_frame_idx"]
                == row["action_idx"]
                == row["model_frame_idx"]
            ), f"ep{episode_id}"


# --------------------------------------------------- coordinate-frame authority

def test_six_layout_coordinate_frames_are_published(frames_index):
    assert frames_index["layout_count"] == 6
    assert [f["layout_id"] for f in frames_index["frames"]] == LAYOUTS
    for layout_id in LAYOUTS:
        assert os.path.exists(os.path.join(ROOT, mod.FRAMES_REL, f"{layout_id}.json"))
    assert len({f["coordinate_frame_id"] for f in frames_index["frames"]}) == 6
    assert len({f["coordinate_frame_hash"] for f in frames_index["frames"]}) == 6


def test_accepted_geometry_identity_is_independently_verified(frames_index):
    assert sha256(mod.GEOMETRY_REL) == mod.ACCEPTED_GEOMETRY_SHA256
    assert frames_index["accepted_geometry_sha256"] == mod.ACCEPTED_GEOMETRY_SHA256
    assert frames_index["accepted_geometry_identity_independently_verified"] is True
    for frame in frames_index["frames"]:
        assert frame["source_layout_manifest_hash"] == mod.ACCEPTED_GEOMETRY_SHA256


def test_person_c_signed_and_person_b_left_unsigned(frames_index):
    assert frames_index["PERSON_C_COORDINATE_FRAME_SIGNED"] is True
    assert frames_index["person_b_cosign_present"] is False
    assert frames_index["person_c_signed_person_b_side"] is False
    for layout_id in LAYOUTS:
        document = load(f"{mod.FRAMES_REL}/{layout_id}.json")
        signoff = document["adapter_signoff"]
        assert signoff["person_c"] is True
        assert signoff["person_b"] is False
        # Person C must not be able to pass the live cross-role gate alone.
        with pytest.raises(Exception):
            validate_coordinate_frame(document)
        validate_coordinate_frame(document, require_cross_role_signoff=False)


def test_coordinate_frame_hash_survives_a_person_b_cosign(cosigned_frames):
    for layout_id in LAYOUTS:
        published = load(f"{mod.FRAMES_REL}/{layout_id}.json")
        assert coordinate_frame_hash(published) == published["coordinate_frame_hash"]
        cosigned = cosigned_frames[layout_id]
        assert coordinate_frame_hash(cosigned) == published["coordinate_frame_hash"]
        frame = validate_coordinate_frame(cosigned)
        assert frame.coordinate_frame_hash == published["coordinate_frame_hash"]


def test_coordinate_frame_geometry_matches_accepted_geometry():
    geometry = load(mod.GEOMETRY_REL)
    layouts = {entry["layout_id"]: entry for entry in geometry["layouts"]}
    for layout_id in LAYOUTS:
        document = load(f"{mod.FRAMES_REL}/{layout_id}.json")
        authority = document["person_c_authority"]
        source = layouts[layout_id]
        assert authority["wall_bounds"] == source["wall"]["bounds"]
        assert authority["lane_bounds"]["axis_min"] == source["lane"]["axis_min"]
        assert authority["lane_bounds"]["axis_max"] == source["lane"]["axis_max"]
        assert authority["lane_bounds"]["ortho"] == source["lane"]["ortho"]
        assert authority["motion_sign"] == source["motion_sign"]
        assert authority["camera_canonical_pose"] == source["camera"]
        assert authority["layout_config_version"] == source["config_version"]
        occluded = [
            int(s["axis_position"])
            for s in source["shadow"]["integer_lane_samples"] if s["occluded"]
        ]
        shadow = authority["shadow_bounds"]
        assert shadow["occluded_integer_axis_min"] == min(occluded)
        assert shadow["occluded_integer_axis_max"] == max(occluded)
        assert shadow["continuous_boundary_measured"] is False
        assert authority["private_axis_reinterpretation"] is False
        assert authority["silent_axis_inference"] is False


def test_sign_convention_reproduces_runtime_axis_pos_exactly(packages):
    """The published frame must project C's own runtime state onto axis_pos."""
    frames = {
        layout_id: load(f"{mod.FRAMES_REL}/{layout_id}.json")
        for layout_id in LAYOUTS
    }
    checked = 0
    for package in packages.values():
        if not package["person_c_authority"]["target_count_identity"]["target_present"]:
            continue
        frame = frames[package["layout_id"]]
        origin = frame["wall_parallel_origin_world_xyz"]
        unit = frame["wall_parallel_positive_unit_vector_world_xyz"]
        assert sum(component * component for component in unit) == 1.0
        for row in package["streams"]["server_state"]:
            state = row["state"]
            position = (
                state["position_x_blocks"],
                state["position_y_blocks"],
                state["position_z_blocks"],
            )
            projected = sum(
                (position[i] - origin[i]) * unit[i] for i in range(3)
            )
            assert projected == state["wall_parallel_position_blocks"]
            checked += 1
    assert checked == 2108


def test_frames_carry_the_full_axis_contract():
    for layout_id in LAYOUTS:
        authority = load(f"{mod.FRAMES_REL}/{layout_id}.json")["person_c_authority"]
        assert authority["world_coordinate_system"] == "minecraft_world_x_y_z"
        assert authority["scalar_axis_unit"] == "blocks"
        assert authority["wall_parallel_scalar_axis"] in ("x", "z")
        assert authority["axis_direction"]["positive_world_direction"] in (
            "+x", "+z", "-x", "-z",
        )
        assert authority["axis_direction"]["unit_norm"] == 1.0
        assert "origin_world_xyz" in authority["axis_origin"]
        assert authority["positive_sign_convention"]
        for source in authority["geometry_source_paths"]:
            assert len(source["sha256"]) == 64


# ------------------------------------------- Person B adapter consumability

def test_person_b_adapter_builds_state_input_for_all_60_target_bearing(
    packages, cosigned_frames, package_manifest,
):
    by_episode = {r["episode_id"]: r for r in package_manifest["records"]}
    built = rows = 0
    refusals = []
    for episode_id, package in sorted(packages.items()):
        try:
            output = build_state_input_from_capture_package(
                package,
                coordinate_frame=cosigned_frames[package["layout_id"]],
                model_hash="a" * 64,
                preprocess_hash="b" * 64,
            )
        except CaptureStateHandoffError as error:
            refusals.append((episode_id, error.code.value))
            continue
        built += 1
        rows += len(output["rows"])
    assert built == 60
    assert rows == 2108
    assert len(refusals) == 6
    assert {code for _, code in refusals} == {"no_object_not_oracle_eligible"}
    for episode_id, _ in refusals:
        assert by_episode[episode_id]["set_id"] == "nosheep"


def test_oracle_ineligible_packages_are_declared_as_such(package_manifest):
    assert package_manifest["person_b_oracle_eligible_count"] == 60
    assert package_manifest["person_b_oracle_ineligible_count"] == 6
    for record in package_manifest["records"]:
        expected = record["set_id"] != "nosheep"
        assert record["person_b_oracle_eligible"] is expected


# --------------------------------------------------- empirical visibility gap

def test_no_empirical_visibility_is_invented_anywhere(packages, package_manifest):
    assert package_manifest["empirical_magenta_channel_present"] is False
    assert package_manifest["person_c_invented_empirical_visibility"] is False
    for episode_id, package in sorted(packages.items()):
        status = package["person_c_authority"]["visibility_channel_status"]
        assert status["empirical_magenta_channel_present"] is False
        assert status["empirical_magenta_detector_version"] is None
        assert status["visible_flag_final_available"] is False
        assert status["person_c_invented_empirical_values"] is False
        assert status["geometric_channel_present"] is True
        for row in package["streams"]["visibility"]:
            assert row["empirical_magenta_visible"] is None
            assert row["visible_flag_final"] is None
            assert row["visibility"] in ("visible", "occluded")
            assert row["visibility_source"] == "server_state.geometric_visible"
            assert row["visibility"] == (
                "visible" if row["geometric_visible"] else "occluded"
            ), f"ep{episode_id}"


# -------------------------------------------------------- C -> E empirical request

def test_c_to_e_request_is_ready_and_complete():
    request = load(f"{mod.E_REQUEST_REL}/request_manifest.json")
    assert request["C_TO_E_EMPIRICAL_VISIBILITY_HANDOFF_READY"] is True
    assert request["producer_role"] == "person_c"
    assert request["consumer_role"] == "person_e"
    assert request["person_c_accepted_manifest_sha256"] == (
        mod.C_ACCEPTED_MANIFEST_SHA256
    )
    assert request["person_c_commit"] == mod.C_SOURCE_COMMIT
    assert request["person_a_frame_map_package_sha256"] == mod.PERSON_A_PKG_SHA256
    assert request["accepted_geometry_sha256"] == mod.ACCEPTED_GEOMETRY_SHA256
    assert request["trajectory_count"] == 66
    assert len(request["trajectory_ids"]) == 66
    assert len(set(request["trajectory_ids"])) == 66
    assert request["model_frame_identity_count"] == 2468
    assert request["expected_model_frame_identity_count"] == 2468
    assert request["expected_response_key"] == ["trajectory_id", "model_frame_idx"]
    assert request["magenta_reserved_for_target_only"] is True
    assert sha256(request["frame_universe_path"]) == request["frame_universe_sha256"]
    dimensions = request["frame_dimensions"]
    assert dimensions["raw_framebuffer_width_pixels"] == 1920
    assert dimensions["raw_framebuffer_height_pixels"] == 1046
    assert dimensions["canonical_derivative_width_pixels"] == 640
    assert dimensions["canonical_derivative_height_pixels"] == 360


def test_c_to_e_request_contains_no_person_c_invented_detector_parameters():
    request = load(f"{mod.E_REQUEST_REL}/request_manifest.json")
    assert request["person_c_supplied_detector_thresholds"] is False
    assert request["person_c_supplied_detector_version"] is False
    assert request["person_c_ran_detector"] is False
    assert request["person_c_tuned_detector"] is False
    assert request["detector_version_owner"] == "person_e"
    assert request["person_c_empirical_channel_supplied"] is False
    schema = load(f"{mod.E_REQUEST_REL}/expected_response_schema.json")
    assert schema["person_c_supplied_thresholds"] is False
    assert schema["threshold_ownership"] == "person_e"
    # No detector parameter may carry an actual value anywhere in the request.
    # Fields whose whole purpose is to declare absence (a boolean False, a null,
    # or an ownership string) are exactly what this handoff is supposed to say.
    banned_tokens = ("threshold", "hsv", "rgb_min", "rgb_max", "tolerance",
                     "min_pixel", "saturation", "hue", "channel_bound")
    offenders = []

    def walk(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                lowered = key.lower()
                if any(token in lowered for token in banned_tokens):
                    declares_absence = (
                        value is False
                        or value is None
                        or (isinstance(value, str) and value in ("person_e",))
                    )
                    if not declares_absence:
                        offenders.append((path + key, value))
                walk(value, path + key + ".")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, path + f"[{index}].")

    walk(request)
    walk(load(f"{mod.E_REQUEST_REL}/expected_response_schema.json"))
    assert not offenders, f"C must not invent detector parameters: {offenders}"


def test_c_to_e_frame_universe_joins_by_immutable_frame_identity():
    request = load(f"{mod.E_REQUEST_REL}/request_manifest.json")
    rows = mod.read_jsonl(os.path.join(ROOT, request["frame_universe_path"]))
    assert len(rows) == 2468
    keys = {(row["trajectory_id"], row["model_frame_idx"]) for row in rows}
    assert len(keys) == 2468
    applicable = 0
    for row in rows:
        assert len(row["source_frame_sha256"]) == 64
        assert row["source_frame_byte_size"] > 0
        assert row["source_frame_runtime_path"].endswith(".png")
        assert row["expected_person_e_field"] == "empirical_magenta_visible"
        assert row["person_e_value_supplied"] is None
        assert isinstance(row["person_c_geometric_visible"], bool)
        applicable += 1 if row["detector_applicable"] else 0
    assert applicable == 2108
    assert request["detector_applicability"]["applicable_row_count"] == 2108


def test_c_to_e_frame_identities_match_the_capture_packages(packages):
    request = load(f"{mod.E_REQUEST_REL}/request_manifest.json")
    rows = mod.read_jsonl(os.path.join(ROOT, request["frame_universe_path"]))
    universe = {(r["trajectory_id"], r["model_frame_idx"]): r for r in rows}
    for package in packages.values():
        for row in package["streams"]["frame_map"]:
            entry = universe[(row["trajectory_id"], row["model_frame_idx"])]
            assert entry["source_frame_sha256"] == row["source_frame_sha256"]
            assert entry["source_frame_role"] == row["source_frame_role"]


# ------------------------------------------------------ U4 structural finding

def test_u4_finding_declares_ineligibility_with_a_reason():
    finding = load(f"{mod.STATUS_REL}/u4_reveal_eligibility_finding.json")
    assert finding["CURRENT_66_CELL_U4_REVEAL_ELIGIBLE"] is False
    assert finding["U4_SUPPLEMENTAL_CAPTURE_REQUIRED"] is True
    assert finding["structural_failure_reason"] == (
        "no_heldout_terminal_reveal_window_exists_in_the_66_cell_capture"
    )
    assert finding["failure_reason_detail"]
    assert finding["immutable"] is True
    assert finding["existing_66_cell_universe_remains_production"] is True
    assert finding["existing_66_cell_accepted_count"] == 66
    assert finding["existing_66_cell_excluded_count"] == 0


def test_u4_capture_duration_facts_are_derived_from_person_c_evidence(packages):
    finding = load(f"{mod.STATUS_REL}/u4_reveal_eligibility_finding.json")
    clock = finding["frozen_capture_clock"]
    assert clock["tick_rate_hz"] == 20.0
    assert clock["required_pre_frames"] == 20
    assert clock["required_post_frames"] == 20
    assert clock["required_centred_span_frames"] == 41
    facts = finding["capture_universe_facts"]
    assert facts["accepted_trajectory_count"] == 66
    assert facts["total_model_frame_count"] == 2468
    assert facts["episodes_ending_occluded"] == 60
    assert facts["episodes_ending_visible"] == 6
    # Re-derive the per-episode end state straight from the packages.
    ends_occluded = 0
    for package in packages.values():
        rows = sorted(
            package["streams"]["visibility"], key=lambda r: r["model_frame_idx"]
        )
        if not rows[-1]["geometric_visible"]:
            ends_occluded += 1
    assert ends_occluded == facts["episodes_ending_occluded"]
    per_episode = {e["episode_id"]: e for e in finding["per_episode_facts"]}
    assert len(per_episode) == 66
    for package in packages.values():
        entry = per_episode[int(package["episode_id"])]
        assert entry["frame_count"] == package["media"]["frame_count"]
        assert entry["duration_seconds"] == entry["frame_count"] * 0.05


def test_u4_transition_audit_matches_an_independent_recount(packages):
    finding = load(f"{mod.STATUS_REL}/u4_reveal_eligibility_finding.json")
    audit = finding["transition_audit"]
    total = heldout = 0
    for package in packages.values():
        rows = sorted(
            package["streams"]["visibility"], key=lambda r: r["model_frame_idx"]
        )
        sequence = [r["geometric_visible"] for r in rows]
        indices = [
            i for i in range(1, len(sequence))
            if not sequence[i - 1] and sequence[i]
        ]
        total += len(indices)
        if package["layout_id"] in ("layout_03", "layout_04"):
            heldout += len(indices)
    assert audit["geometric_occluded_to_visible_transition_count"] == total == 8
    assert audit["heldout_transition_count"] == heldout == 4
    assert audit["heldout_transitions_satisfying_full_reveal_window"] == 0
    assert audit["heldout_terminal_reveal_count"] == 0
    for transition in audit["transitions"]:
        if transition["in_heldout_layout"]:
            assert transition["full_reveal_window_satisfied"] is False


def test_u4_finding_does_not_relax_any_frozen_foreign_rule():
    finding = load(f"{mod.STATUS_REL}/u4_reveal_eligibility_finding.json")
    foreign = finding["foreign_authorities_not_modified"]
    assert foreign["reveal_window_seconds"] == [-1.0, 1.0]
    assert foreign["required_heldout_event_count"] == 5
    assert foreign["required_heldout_event_count_owner"] == "person_b"
    assert foreign["person_c_relaxed_reveal_window"] is False
    assert foreign["person_c_reduced_heldout_event_count"] is False
    assert foreign["person_c_reinterpreted_blips_as_reveals"] is False
    assert foreign["person_c_extended_any_existing_episode"] is False
    assert foreign["person_c_relabelled_accepted_as_excluded"] is False
    # The frozen reveal window is still what the shared repo declares.
    with open(os.path.join(ROOT, mod.ANALYSIS_CORE_REL), encoding="utf-8") as handle:
        assert '"reveal_window_seconds": [-1.0, 1.0]' in handle.read()


def test_u4_supplemental_requirements_are_requirements_only():
    receipt = load(f"{mod.STATUS_REL}/u4_supplemental_capture_requirements.json")
    assert receipt["status"] == "requirements_only_not_executed"
    assert receipt["collection_performed_in_this_task"] is False
    identity = receipt["episode_identity_requirements"]
    assert identity["new_episode_ids_required"] is True
    assert identity["reuse_of_ep12601_ep12666_forbidden"] is True
    assert identity["first_available_episode_id"] == 12667
    assert identity["overwrite_of_existing_66_cells_forbidden"] is True
    assert identity["existing_accepted_count_unchanged"] == 66
    assert identity["existing_excluded_count_unchanged"] == 0
    duration = receipt["capture_duration_requirements"]
    assert duration["minimum_pre_reveal_frames"] == 20
    assert duration["minimum_post_reveal_frames"] == 20
    assert duration["minimum_centred_span_frames"] == 41
    assert duration["reveal_must_not_be_the_final_frame"] is True
    assert duration["blip_reveals_not_acceptable"] is True
    preserved = receipt["preserved_environment_requirements"]
    assert preserved["accepted_geometry_sha256"] == mod.ACCEPTED_GEOMETRY_SHA256
    assert preserved["layout_config_version"] == mod.ACCEPTED_GEOMETRY_VERSION
    assert preserved["tick_rate_hz"] == 20.0
    leakage = receipt["leakage_requirements"]
    assert leakage["no_overlap_with_fit_data"] is True
    assert leakage["no_overlap_with_selection_data"] is True
    assert leakage["no_overlap_with_tuning_data"] is True
    assert leakage["must_not_be_used_to_tune_person_e_detector"] is True
    assert leakage["partition_owner"] == "person_b"
    assert receipt["hashing_requirements"][
        "exact_sha256_required_for_every_source_artifact"
    ] is True
    assert receipt["deterministic_capture_requirements"][
        "synchronized_state_action_frame_capture_required"
    ] is True


def test_person_c_does_not_choose_heldout_event_ids():
    receipt = load(f"{mod.STATUS_REL}/u4_supplemental_capture_requirements.json")
    owners = {item["authority"]: item for item in receipt["foreign_authorities"]}
    for item in owners.values():
        assert item["person_c_decided"] is False
    selection = owners["held-out U4 event selection and event ids"]
    assert selection["owner_role"] == "person_b"
    finding = load(f"{mod.STATUS_REL}/u4_reveal_eligibility_finding.json")
    assert finding["heldout_partition_foreign_input"][
        "person_c_chose_heldout_event_ids"
    ] is False


# ---------------------------------------------------------- C -> B receipt

def test_c_to_b_receipt_does_not_claim_a_person_b_cosign():
    receipt = load(f"{mod.STATUS_REL}/c_to_b_successor_handoff.json")
    frame_authority = receipt["coordinate_frame_authority"]
    assert frame_authority["READY_FOR_B_COORDINATE_FRAME_COSIGN"] is True
    assert frame_authority["person_b_cosign_present"] is False
    assert frame_authority["person_b_cosign_claimed_by_person_c"] is False
    assert frame_authority["PERSON_C_COORDINATE_FRAME_SIGNED"] is True
    for frame in frame_authority["frames"]:
        assert frame["adapter_signoff"]["person_c"] is True
        assert frame["adapter_signoff"]["person_b"] is False


def test_c_to_b_receipt_binds_every_required_authority():
    receipt = load(f"{mod.STATUS_REL}/c_to_b_successor_handoff.json")
    assert receipt["producer_role"] == "person_c"
    assert receipt["consumer_role"] == "person_b"
    assert receipt["additive_successor"] is True
    assert receipt["rewrites_c7_5_history"] is False
    assert receipt["person_c_manifest"]["sha256"] == mod.C_ACCEPTED_MANIFEST_SHA256
    assert receipt["person_c_manifest"]["accepted_count"] == 66
    assert receipt["person_c_manifest"]["excluded_count"] == 0
    capture = receipt["capture_package_authority"]
    assert capture["capture_package_count"] == 66
    assert capture["capture_packages_complete"] is True
    assert capture["missing_count"] == 0
    assert capture["frozen_contract_rejected_count"] == 0
    assert capture["layout_config_hash_binding"] == mod.ACCEPTED_GEOMETRY_SHA256
    assert receipt["accepted_geometry_identity"]["sha256"] == (
        mod.ACCEPTED_GEOMETRY_SHA256
    )
    state = receipt["server_state_layout_meta_authorities"]
    assert state["server_state_count"] == 66
    assert state["layout_meta_count"] == 66
    assert state["server_state_hashes_valid"] is True
    assert state["layout_meta_hashes_valid"] is True
    assert receipt["person_a_frame_map_binding"]["package_sha256"] == (
        mod.PERSON_A_PKG_SHA256
    )
    visibility = receipt["empirical_visibility_status"]
    assert visibility["empirical_magenta_channel_present"] is False
    assert visibility["C_TO_E_EMPIRICAL_VISIBILITY_HANDOFF_READY"] is True
    assert visibility["visible_flag_final_available"] is False
    u4 = receipt["u4_structural_eligibility_status"]
    assert u4["CURRENT_66_CELL_U4_REVEAL_ELIGIBLE"] is False
    assert u4["U4_SUPPLEMENTAL_CAPTURE_REQUIRED"] is True
    assert u4["person_b_u4_rules_modified"] is False


def test_c_to_b_receipt_lists_the_remaining_foreign_inputs():
    receipt = load(f"{mod.STATUS_REL}/c_to_b_successor_handoff.json")
    remaining = {
        item["input_id"]: item
        for item in receipt["remaining_inputs_required_before_b_oracle_target_manifest"]
    }
    assert "person_e_empirical_magenta_visibility_for_66_cells" in remaining
    assert "person_b_coordinate_frame_cosign" in remaining
    assert "person_a_model_hash_and_preprocess_hash" in remaining
    assert remaining[
        "person_e_empirical_magenta_visibility_for_66_cells"
    ]["owner_role"] == "person_e"
    assert all(item["blocking"] for item in remaining.values())
    assert receipt["READY_FOR_B_ORACLE_AFTER_E_VISIBILITY"] is True
    assert receipt["person_c_owned_oracle_inputs_complete"] is True


# ------------------------------------------------------------ housekeeping

def test_sha256_inventory_matches_every_published_artifact():
    inventory = load(f"{mod.STATUS_REL}/sha256_inventory.json")
    assert inventory["file_count"] == len(inventory["files"])
    for rel_path, digest in inventory["files"].items():
        assert os.path.exists(os.path.join(ROOT, rel_path)), rel_path
        assert sha256(rel_path) == digest, rel_path


def test_no_episode_payload_bytes_were_copied_into_the_repository(packages):
    for package in packages.values():
        media = package["person_c_authority"]["source_media_identity"]
        assert media["mode"] == "numbered_frames"
        assert "runtime" in media["frame_bytes_location"]
        provenance = package["person_c_authority"]["provenance"]
        assert provenance["episode_bytes_copied_into_repository"] is False
    for dirpath, _, filenames in os.walk(os.path.join(ROOT, mod.STATUS_REL)):
        for name in filenames:
            assert not name.endswith((".png", ".mp4")), name


def test_closure_receipt_reports_no_foreign_branch_modification():
    closure = load(f"{mod.STATUS_REL}/closure_receipt.json")
    assert closure["foreign_branches_modified"] == []
    assert closure["foreign_branches_merged"] == []
    assert closure["person_e_detector_executed"] is False
    assert closure["person_b_side_signed_by_person_c"] is False
    assert closure["PERSON_C_COORDINATE_FRAME_SIGNED"] is True
    assert closure["READY_FOR_B_COORDINATE_FRAME_COSIGN"] is True
    assert closure["empirical_visibility_currently_present"] is False


def test_deterministic_regeneration(tmp_path):
    """Rebuilding must reproduce every published byte exactly."""
    inventory = load(f"{mod.STATUS_REL}/sha256_inventory.json")
    before = {rel: sha256(rel) for rel in inventory["files"]}
    result = subprocess.run(
        [sys.executable,
         os.path.join(ROOT, "scripts",
                      "build_person_c_66_cell_capture_authority_v0_1.py")],
        capture_output=True, text=True, cwd=ROOT, timeout=1800,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    after = {rel: sha256(rel) for rel in inventory["files"]}
    drifted = sorted(rel for rel in before if before[rel] != after[rel])
    assert not drifted, f"non-deterministic artifacts: {drifted[:10]}"
