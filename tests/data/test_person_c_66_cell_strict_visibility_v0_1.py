"""Focused validation for the Person C strict 66-cell visibility closure.

Asserts the Person E intake, the geometric channel, the strict join, the
disagreement ledger, the frozen event derivation, the U4 finding and the C->B
oracle handoff:

  - Person E's handoff and empirical table verify at E's pinned commit, with
    the exact 2468-key set, 0 duplicates, 0 missing, 0 unexplained failures and
    a single frozen detector identity;
  - the geometric channel covers all 2468 identities, preserves the four-way
    status including ambiguity, and never coerces no-object controls;
  - the join is exact on (trajectory_id, model_frame_idx) and applies
    visible_flag = geometric AND empirical;
  - no-object rows keep explicit not-applicable semantics;
  - every applicable disagreement is classified and nothing was relabelled;
  - events come from the frozen stability rule, flickers are retained;
  - U4 remains ineligible with 0 valid terminal reveals;
  - the C->B handoff carries no Person B target values;
  - regeneration is byte-identical.

Person E's detector is never executed and no data is recollected.
"""
import collections
import hashlib
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "src"))

import build_person_c_66_cell_strict_visibility_v0_1 as mod  # noqa: E402

from mineocclude.data.visibility import (  # noqa: E402
    DEFAULT_STABILITY_FRAMES,
    EVENT_RULE_VERSION,
    GEOMETRY_RULE_VERSION,
    stabilize,
    visibility_events,
)
from mineocclude.data.visibility_join import (  # noqa: E402
    FINAL_VISIBILITY_INTERFACE_VERSION,
    VisibilityJoinError,
    strict_join,
)

STATUS = mod.STATUS_REL
LAYOUTS = [f"layout_0{n}" for n in range(1, 7)]


def load(rel_path):
    with open(os.path.join(ROOT, rel_path), "rb") as handle:
        return json.load(handle)


def load_jsonl(rel_path):
    with open(os.path.join(ROOT, rel_path), "r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def sha256(rel_path):
    with open(os.path.join(ROOT, rel_path), "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


@pytest.fixture(scope="module")
def joined():
    return load_jsonl(f"{STATUS}/visibility_join.jsonl")


@pytest.fixture(scope="module")
def geometric():
    return load_jsonl(f"{STATUS}/geometric_visibility.jsonl")


@pytest.fixture(scope="module")
def join_manifest():
    return load(f"{STATUS}/visibility_join_manifest.json")


@pytest.fixture(scope="module")
def ledger():
    return load(f"{STATUS}/disagreement_ledger.json")


@pytest.fixture(scope="module")
def intake():
    return load(f"{STATUS}/e_handoff_intake_receipt.json")


@pytest.fixture(scope="module")
def events():
    return load_jsonl(f"{STATUS}/event_table.jsonl")


@pytest.fixture(scope="module")
def trajectories():
    return load_jsonl(f"{STATUS}/event_trajectory_table.jsonl")


@pytest.fixture(scope="module")
def u4():
    return load(f"{STATUS}/u4_eligibility_finding_v0_2.json")


@pytest.fixture(scope="module")
def b_handoff():
    return load(f"{STATUS}/c_to_b_oracle_handoff.json")


@pytest.fixture(scope="module")
def e_rows():
    payload = subprocess.run(
        ["git", "-C", ROOT, "show", f"{mod.PERSON_E_COMMIT}:{mod.E_RECORDS_REL}"],
        capture_output=True, timeout=180,
    )
    assert payload.returncode == 0, "Person E commit is not available locally"
    return [
        json.loads(line)
        for line in payload.stdout.decode("utf-8").splitlines() if line.strip()
    ]


# ------------------------------------------------------------- E handoff intake

def test_e_handoff_and_table_hashes_verify_at_pinned_commit(intake):
    assert intake["person_e_commit"] == mod.PERSON_E_COMMIT
    assert intake["person_e_branch_merged"] is False
    assert intake["e_handoff_observed_sha256"] == mod.E_HANDOFF_SHA256
    assert intake["e_handoff_declared_sha256"] == mod.E_HANDOFF_SHA256
    assert intake["e_empirical_records_observed_sha256"] == mod.E_RECORDS_SHA256
    assert intake["e_empirical_records_declared_sha256"] == mod.E_RECORDS_SHA256
    assert intake["E_HANDOFF_ACCEPTED"] is True
    assert intake["problem_count"] == 0


def test_e_intake_identity_checks_all_pass(intake):
    for name, ok in intake["identity_checks"].items():
        assert ok is True, f"E identity check failed: {name}"
    assert intake["identity_checks"]["e_did_not_compute_geometric_visible"] is True
    assert intake["identity_checks"]["e_did_not_compute_visible_flag"] is True


def test_e_table_accounting_is_exact(intake):
    accounting = intake["accounting"]
    assert accounting["row_count"] == 2468
    assert accounting["unique_key_count"] == 2468
    assert accounting["duplicate_key_count"] == 0
    assert accounting["missing_key_count"] == 0
    assert accounting["extra_key_count"] == 0
    assert accounting["source_frame_identity_mismatch_count"] == 0
    assert accounting["applicability_mismatch_count"] == 0
    assert accounting["empirical_visible_count"] == 1726
    assert accounting["empirical_hidden_count"] == 382
    assert accounting["empirical_not_applicable_count"] == 360
    assert accounting["unreadable_source_frame_count"] == 0


def test_detector_identity_is_frozen_and_singular(intake):
    detector = intake["detector"]
    assert detector["identity_sha256"] == mod.E_DETECTOR_IDENTITY_SHA256
    assert detector["distinct_identities_observed_in_table"] == [
        mod.E_DETECTOR_IDENTITY_SHA256
    ]
    assert detector["retuned_on_66_cell_population"] is False
    assert detector["person_c_executed_detector"] is False
    assert detector["person_c_tuned_detector"] is False
    assert intake["forbidden_person_c_fields_present"] == []


def test_person_b_cosign_verified_independently(intake):
    cosign = intake["person_b_cosign"]
    assert cosign["commit"] == mod.PERSON_B_COMMIT
    assert cosign["observed_sha256"] == mod.PERSON_B_COSIGN_SHA256
    for name, ok in cosign["checks"].items():
        assert ok is True, f"B co-sign check failed: {name}"
    assert len(cosign["cosigned_frames"]) == 6
    for frame in cosign["cosigned_frames"]:
        assert frame["coordinate_frame_hash_preserved"] is True
        assert (
            frame["person_c_source_file_sha256"]
            == frame["person_c_source_file_sha256_reverified"]
        )


def test_e_records_source_frames_match_the_c_request(e_rows):
    universe = {
        (r["trajectory_id"], r["model_frame_idx"]): r
        for r in load_jsonl(f"{mod.C_REQUEST_REL}/frame_universe.jsonl")
    }
    assert len(universe) == 2468
    for row in e_rows:
        key = (row["trajectory_id"], row["model_frame_idx"])
        assert row["source_frame_sha256"] == universe[key]["source_frame_sha256"]


# ------------------------------------------------------- geometric visibility

def test_geometric_channel_covers_the_exact_2468_identities(geometric):
    assert len(geometric) == 2468
    keys = {(r["trajectory_id"], r["model_frame_idx"]) for r in geometric}
    assert len(keys) == 2468
    assert len({r["trajectory_id"] for r in geometric}) == 66


def test_geometric_channel_uses_the_frozen_rule_and_accepted_geometry(geometric):
    for row in geometric:
        assert row["geometry_rule_version"] == GEOMETRY_RULE_VERSION
        assert row["accepted_geometry_sha256"] == mod.ACCEPTED_GEOMETRY_SHA256
        assert row["accepted_geometry_version"] == mod.ACCEPTED_GEOMETRY_VERSION
    assert sha256(mod.GEOMETRY_REL) == mod.ACCEPTED_GEOMETRY_SHA256


def test_geometric_status_is_four_way_and_never_forced_binary(geometric):
    allowed = {"visible", "occluded", "boundary",
               mod.BOUNDARY_CROSS, mod.NOT_APPLICABLE_STATUS}
    for row in geometric:
        assert row["geometric_status"] in allowed
        if row["geometric_status"] == mod.NOT_APPLICABLE_STATUS:
            # no-object control: never coerced to a boolean
            assert row["geometric_visible"] is None
            assert row["geometric_applicable"] is False
            assert row["not_applicable_reason"]
        if row["geometric_ambiguous"]:
            # ambiguity is retained with both implementations' values
            assert row["geometric_status"] in ("boundary", mod.BOUNDARY_CROSS)


def test_geometric_channel_is_not_derived_from_the_detector(geometric):
    for row in geometric:
        assert "empirical_magenta_visible" not in row
        assert "detector_status" not in row
        assert "visible_flag" not in row


def test_authoritative_geometric_channel_matches_the_capture_packages(geometric):
    """The published channel must be the recorded capture truth."""
    by_key = {(r["trajectory_id"], r["model_frame_idx"]): r for r in geometric}
    capture_manifest = load(
        f"{mod.CAPTURE_AUTHORITY_REL}/capture_package_manifest.json"
    )
    checked = 0
    for record in capture_manifest["records"]:
        package = load(record["capture_package_path"])
        for row in package["streams"]["visibility"]:
            entry = by_key[(row["trajectory_id"], row["model_frame_idx"])]
            assert (
                entry["geometric_visible_authoritative_runtime"]
                == row["geometric_visible"]
            )
            checked += 1
    assert checked == 2468


def test_cross_implementation_ambiguity_is_edge_local(geometric):
    ambiguous = [r for r in geometric if r["geometric_ambiguous"]]
    assert ambiguous, "expected the recorded cross-implementation ambiguity"
    for row in ambiguous:
        assert row["cross_implementation_agreement"] is False
        assert row["geometric_visible_frozen_recompute"] is not None
        # every ambiguous frame grazes a declared shadow edge
        assert row["distance_to_shadow_edge_blocks"] is not None
        assert row["distance_to_shadow_edge_blocks"] <= 1.0


def test_no_wall_controls_have_no_shadow_distance(geometric):
    for row in geometric:
        if row["geometric_applicable"] and not row["wall_present"]:
            assert row["distance_to_shadow_edge_blocks"] is None


# --------------------------------------------------------------- strict join

def test_join_is_exact_on_the_frame_key(joined, join_manifest):
    assert len(joined) == 2468
    keys = [(r["trajectory_id"], r["model_frame_idx"]) for r in joined]
    assert len(set(keys)) == 2468
    assert join_manifest["VISIBILITY_JOIN_COMPLETE"] is True
    assert join_manifest["join_key"] == ["trajectory_id", "model_frame_idx"]
    assert join_manifest["frame_key_count"] == 2468
    assert join_manifest["unique_frame_key_count"] == 2468
    assert join_manifest["trajectory_count"] == 66
    assert "nearest" not in join_manifest["join_semantics"].lower().replace(
        "no nearest-time", ""
    )
    assert join_manifest["join_method"] == (
        "mineocclude.data.visibility_join.strict_join"
    )


def test_and_rule_holds_for_every_applicable_row(joined):
    checked = 0
    for row in joined:
        if not row["visibility_applicable"]:
            continue
        assert row["geometric_visible"] is not None
        assert row["empirical_magenta_visible"] is not None
        assert row["visible_flag"] == (
            bool(row["geometric_visible"]) and bool(row["empirical_magenta_visible"])
        )
        assert row["visible_flag_defined"] is True
        checked += 1
    assert checked == 2108


def test_raw_channels_are_retained_separately(joined):
    for row in joined:
        assert "geometric_visible" in row
        assert "empirical_magenta_visible" in row
        assert "visible_flag" in row
        assert row["geometry_rule_version"] == GEOMETRY_RULE_VERSION
        assert row["final_visibility_interface_version"] == (
            FINAL_VISIBILITY_INTERFACE_VERSION
        )
        assert row["label_owner"] == "Person C"
        assert row["visible_flag_rule"] == (
            "geometric_visible AND empirical_magenta_visible"
        )
        assert len(row["source_state_sha256"]) == 64
        assert row["empirical_visibility_source_sha256"] == mod.E_RECORDS_SHA256


def test_empirical_values_match_person_e_exactly(joined, e_rows):
    e_by_key = {(r["trajectory_id"], r["model_frame_idx"]): r for r in e_rows}
    for row in joined:
        source = e_by_key[(row["trajectory_id"], row["model_frame_idx"])]
        assert row["empirical_magenta_visible"] == source["empirical_magenta_visible"]
        assert row["detector_status"] == source["detector_status"]
        assert row["source_frame_sha256"] == source["source_frame_sha256"]


def test_no_object_rows_keep_explicit_not_applicable_semantics(joined):
    rows = [r for r in joined if not r["visibility_applicable"]]
    assert len(rows) == 360
    for row in rows:
        assert row["empirical_magenta_visible"] is None
        assert row["geometric_visible"] is None
        assert row["target_present"] is False
        assert row["detector_status"] == "not_applicable_no_target_object"
        assert row["not_applicable_reason"]
        assert row["visible_flag_defined"] is False
        # The frozen contract requires False here; that it is forced is explicit.
        assert row["visible_flag"] is False
        assert row["visible_flag_forced_false_by_frozen_contract"] is True
        assert row["quarantined"] is True
    assert len({r["trajectory_id"] for r in rows}) == 6


def test_complete_accounting_over_all_2468_keys(join_manifest):
    accounting = join_manifest["accounting"]
    assert accounting["total_rows"] == 2468
    assert accounting["applicable_rows"] == 2108
    assert accounting["not_applicable_rows"] == 360
    assert accounting["applicable_rows"] + accounting["not_applicable_rows"] == 2468
    assert accounting["final_visible_plus_hidden_equals_applicable"] is True
    assert accounting["complete_accounting"] is True
    assert accounting["empirical_visible_count"] == 1726
    assert accounting["empirical_hidden_count"] == 382
    assert accounting["empirical_null_count"] == 360


def test_join_fails_closed_on_a_tampered_key():
    """The frozen join must reject a missing counterpart rather than guess."""
    context = {
        "layout_id": "layout_01",
        "canonical_camera_pose_id": "layout_01_canonical_pose_v1",
        "resolution": "640x360",
        "coordinate_convention": "pixel_center_xy_zero_based",
    }
    c_records = [
        {"trajectory_id": "t", "model_frame_idx": 0,
         "geometric_visible": True, **context},
        {"trajectory_id": "t", "model_frame_idx": 1,
         "geometric_visible": True, **context},
    ]
    e_records = [
        {"trajectory_id": "t", "model_frame_idx": 0,
         "empirical_magenta_visible": True, "detector_version": "v", **context},
    ]
    with pytest.raises(VisibilityJoinError):
        strict_join(c_records, e_records, expected_detector_version="v")


# ------------------------------------------------------- disagreement ledger

def test_every_applicable_disagreement_is_classified(joined, ledger):
    allowed = {
        "agreement", "detector_not_applicable", "geometry_ambiguous",
        "geometry_visible_detector_hidden", "geometry_hidden_detector_visible",
        "invalid_or_missing_input",
    }
    counts = collections.Counter(r["disagreement_class"] for r in joined)
    assert set(counts) <= allowed
    assert dict(sorted(counts.items())) == ledger["global_counts"]
    assert sum(counts.values()) == 2468
    assert counts["detector_not_applicable"] == 360


def test_disagreement_classes_are_consistent_with_the_raw_channels(joined):
    for row in joined:
        cls = row["disagreement_class"]
        if cls == "geometry_visible_detector_hidden":
            assert row["geometric_visible"] is True
            assert row["empirical_magenta_visible"] is False
        elif cls == "geometry_hidden_detector_visible":
            assert row["geometric_visible"] is False
            assert row["empirical_magenta_visible"] is True
        elif cls == "agreement":
            assert bool(row["geometric_visible"]) == bool(
                row["empirical_magenta_visible"]
            )
        elif cls == "detector_not_applicable":
            assert row["visibility_applicable"] is False


def test_ledger_declares_no_manual_relabelling(ledger):
    assert ledger["labels_manually_adjusted"] is False
    assert ledger["geometry_retuned"] is False
    assert ledger["detector_retuned"] is False
    assert ledger["total_rows"] == 2468
    assert ledger["applicable_row_count"] == 2108


def test_ledger_reports_by_layout_set_and_condition(ledger):
    assert sorted(ledger["by_layout"]) == LAYOUTS
    assert set(ledger["by_set_id"]) == {"core", "nowall", "nosheep", "sentinel"}
    assert set(ledger["by_condition"]) == {
        "core", "no_wall_visible", "occluder_only_no_sheep"
    }
    for scope in (ledger["by_layout"], ledger["by_set_id"], ledger["by_condition"]):
        assert sum(sum(v.values()) for v in scope.values()) == 2468


def test_ledger_reports_boundary_proximity_and_subclasses(ledger):
    assert "near_candidate_boundary_counts" in ledger
    assert ledger["boundary_window_frames"] >= 1
    subclasses = ledger["subclass_characterisation"]
    edge = subclasses["near_shadow_edge_applicable_disagreements"]
    assert edge["count"] > 0
    assert edge["person_c_resolved_these"] is False
    no_wall = subclasses["no_wall_control_detector_null_match"]
    assert no_wall["person_c_attributed_a_cause"] is False
    assert no_wall["owner_of_next_step"] == "person_e"
    assert len(no_wall["rows"]) == no_wall["count"]


def test_ledger_rows_cover_every_non_agreement_row(joined, ledger):
    expected = sum(1 for r in joined if r["disagreement_class"] != "agreement")
    assert len(ledger["disagreement_rows"]) == expected


# ----------------------------------------------------------------- events

def test_events_use_the_frozen_rule(events, trajectories):
    for row in events:
        assert row["event_rule_version"] == EVENT_RULE_VERSION
        assert row["stability_frames"] == DEFAULT_STABILITY_FRAMES
    for row in trajectories:
        assert row["event_rule_version"] == EVENT_RULE_VERSION
        assert row["stability_frames"] == DEFAULT_STABILITY_FRAMES
        assert row["frames_deleted"] is False
    assert len(trajectories) == 66


def test_event_derivation_reproduces_the_frozen_rule(joined, trajectories):
    """Recompute events straight from the published join."""
    by_trajectory = collections.defaultdict(list)
    for row in joined:
        by_trajectory[row["trajectory_id"]].append(row)
    published = {r["trajectory_id"]: r for r in trajectories}
    for trajectory_id, rows in by_trajectory.items():
        rows = sorted(rows, key=lambda r: r["model_frame_idx"])
        sequence = [bool(r["visible_flag"]) for r in rows]
        expected = visibility_events(sequence, DEFAULT_STABILITY_FRAMES, 0.05)
        entry = published[trajectory_id]
        assert entry["event_count"] == expected["n_events"]
        assert entry["missing_reveal"] == expected["missing_reveal"]
        assert entry["multiple_events"] == expected["multiple_events"]
        assert entry["raw_onset_candidates"] == expected["raw_onset_candidates"]


def test_flickering_frames_are_retained_not_deleted(joined, trajectories):
    by_trajectory = collections.defaultdict(list)
    for row in joined:
        by_trajectory[row["trajectory_id"]].append(row)
    for entry in trajectories:
        rows = sorted(
            by_trajectory[entry["trajectory_id"]], key=lambda r: r["model_frame_idx"]
        )
        # every frame is still present
        assert len(rows) == entry["frame_count"]
        sequence = [bool(r["visible_flag"]) for r in rows]
        stabilized = stabilize(sequence, DEFAULT_STABILITY_FRAMES)
        flicker = [i for i in range(len(sequence)) if stabilized[i] != sequence[i]]
        assert entry["flicker_frame_count"] == len(flicker)
        assert entry["flicker_model_frame_indices"] == flicker


def test_reveal_rejections_are_recorded(events, trajectories, u4):
    for row in events:
        if row["reveal_model_frame_idx"] is None:
            assert row["missing_reveal"] is True
            assert row["valid_terminal_reveal"] is False
            assert row["rejection_reason"] == "missing_reveal_capture_ends_hidden"
        elif not row["valid_terminal_reveal"]:
            assert row["rejection_reason"] is not None
    counts = u4["counts"]
    assert counts["reveal_candidates_rejected_by_stability"] == sum(
        len(t["reveal_candidates_rejected_by_stability"]) for t in trajectories
    )
    assert counts["reveal_candidates_rejected_by_insufficient_window"] == sum(
        len(t["reveal_candidates_rejected_by_window"]) for t in trajectories
    )


def test_occlusion_and_reveal_determinations_are_explicit(u4, trajectories):
    counts = u4["counts"]
    assert counts["trajectories_with_valid_occlusion"] == sum(
        1 for t in trajectories if t["has_valid_occlusion"]
    )
    assert counts["trajectories_with_valid_terminal_reveal"] == sum(
        1 for t in trajectories if t["valid_terminal_reveal_count"] > 0
    )
    assert counts["trajectories_with_missing_reveal"] == sum(
        1 for t in trajectories if t["missing_reveal"]
    )
    assert counts["not_applicable_trajectory_count"] == 6


# ------------------------------------------------------------------- U4

def test_u4_remains_ineligible_with_zero_valid_terminal_reveals(u4):
    assert u4["CURRENT_66_CELL_U4_REVEAL_ELIGIBLE"] is False
    assert u4["U4_VALID_TERMINAL_REVEAL_COUNT"] == 0
    assert u4["U4_SUPPLEMENTAL_CAPTURE_REQUIRED"] is True
    assert u4["counts"]["valid_terminal_reveal_count"] == 0
    assert u4["counts"]["valid_terminal_reveal_count_heldout_layouts"] == 0
    assert u4["failure_reasons"]
    assert u4["immutable"] is True


def test_u4_was_recomputed_not_copied_from_person_e(u4):
    assert u4["person_c_copied_person_e_conclusion"] is False
    assert u4["recomputed_independently"] is True
    assert u4["derived_from"] == (
        "joined Person C geometric AND Person E empirical channel"
    )
    agreement = u4["person_c_independent_agreement_with_person_e"]
    assert agreement["valid_terminal_reveal_count_agrees"] is True
    assert agreement["ineligibility_agrees"] is True
    # like-for-like: E counted on the empirical channel
    assert agreement["empirical_channel_candidate_count_person_c"] == 7
    assert agreement["empirical_channel_candidate_count_person_e"] == 7
    assert agreement["empirical_channel_candidate_count_agrees"] is True
    assert agreement["empirical_channel_heldout_candidate_count_agrees"] is True


def test_u4_reports_per_channel_candidate_counts(u4, joined):
    channels = u4["raw_candidate_counts_by_channel"]
    by_trajectory = collections.defaultdict(list)
    for row in joined:
        by_trajectory[row["trajectory_id"]].append(row)
    for name, field in (
        ("empirical_only", "empirical_magenta_visible"),
        ("geometric_only", "geometric_visible"),
        ("joined_visible_flag", "visible_flag"),
    ):
        total = 0
        for rows in by_trajectory.values():
            rows = sorted(rows, key=lambda r: r["model_frame_idx"])
            if not all(r["visibility_applicable"] for r in rows):
                continue
            sequence = [bool(r[field]) for r in rows]
            total += sum(
                1 for i in range(1, len(sequence))
                if not sequence[i - 1] and sequence[i]
            )
        assert channels[name]["raw_occluded_to_visible_candidate_count"] == total


def test_u4_does_not_relax_any_frozen_foreign_rule(u4):
    foreign = u4["foreign_authorities_not_modified"]
    assert foreign["required_heldout_event_count"] == 5
    assert foreign["required_heldout_event_count_owner"] == "person_b"
    assert foreign["person_c_reduced_event_requirement"] is False
    assert foreign["person_c_relaxed_reveal_window"] is False
    assert foreign["person_c_called_a_blip_a_reveal"] is False
    assert foreign["person_c_extended_existing_episode_files"] is False
    assert foreign["person_c_changed_accepted_manifest"] is False
    assert foreign["person_c_deleted_flickering_frames"] is False
    assert foreign["person_c_tuned_detector"] is False
    assert foreign["person_c_modified_person_b_oracle_logic"] is False
    rules = u4["frozen_rules_used"]
    assert rules["reveal_window_seconds"] == [-1.0, 1.0]
    assert rules["required_pre_frames"] == 20
    assert rules["required_post_frames"] == 20
    assert rules["required_centred_span_frames"] == 41
    assert rules["rule_chosen_after_inspecting_results"] is False
    with open(os.path.join(ROOT, mod.ANALYSIS_CORE_REL), encoding="utf-8") as handle:
        assert '"reveal_window_seconds": [-1.0, 1.0]' in handle.read()


def test_frozen_c7_5_decision_is_untouched(u4):
    frozen = load(f"{mod.C75_REL}/trajectories_mvp_manifest.json")
    assert sha256(f"{mod.C75_REL}/trajectories_mvp_manifest.json") == (
        mod.C_ACCEPTED_MANIFEST_SHA256
    )
    assert frozen["accepted_count"] == 66
    assert frozen["excluded_count"] == 0
    assert u4["existing_66_cell_accepted_count"] == 66
    assert u4["existing_66_cell_excluded_count"] == 0
    assert u4["existing_66_cell_universe_remains_production"] is True
    assert u4["supplemental_capture_executed_in_this_task"] is False
    assert u4["supplemental_capture_must_use_new_episode_and_run_identities"] is True
    closure = load(f"{STATUS}/closure_receipt.json")
    assert closure["frozen_c7_5_decision_modified"] is False
    assert closure["accepted_trajectory_count"] == 66
    assert closure["excluded_trajectory_count"] == 0


# -------------------------------------------------- v0.4 layout resolution

def test_v0_4_layout_resolution_repair_receipt():
    receipt = load(f"{STATUS}/v0_4_layout_resolution_repair_receipt.json")
    assert receipt["CURRENT_V4_LAYOUT_RESOLUTION_AUTHORITY_READY"] is True
    assert receipt["PREEXISTING_V03_LAYOUT_TEST_REPAIRED"] is True
    assert receipt["ownership_determination"]["owner_role"] == "person_c"
    assert receipt["ownership_determination"]["foreign_owned_files_edited"] == []
    repair = receipt["repair"]
    assert repair["marker_field_used"] == "top_face_centre_world_xyz"
    assert repair["hidden_offset_or_compatibility_transform_introduced"] is False
    assert repair["expected_coordinates_hardcoded_in_test"] is False
    assert repair["marker_coordinates_changed_to_satisfy_tests"] is False
    assert repair["all_layouts_match_without_transform"] is True
    assert len(repair["per_layout_verification"]) == 6
    for entry in repair["per_layout_verification"]:
        assert entry["matches_without_any_transform"] is True
    historical = receipt["historical_evidence_preserved"]
    assert historical["historical_geometry_rewritten"] is False
    assert historical["historical_marker_sets_rewritten"] is False
    assert historical["historical_predecessor_invalidated"] is False
    # the superseded v0.3 evidence must still be byte-identical
    assert sha256(mod.HISTORICAL_GEOMETRY_REL) == mod.HISTORICAL_GEOMETRY_SHA256


# ------------------------------------------------------------- C -> B handoff

def test_c_to_b_handoff_is_ready_and_binds_every_authority(b_handoff):
    assert b_handoff["C_TO_B_ORACLE_INPUT_READY"] is True
    assert b_handoff["producer_role"] == "person_c"
    assert b_handoff["consumer_role"] == "person_b"
    assert b_handoff["additive_successor"] is True
    assert b_handoff["rewrites_frozen_c7_5_authority"] is False
    assert b_handoff["person_c_commit"] == mod.C_SOURCE_COMMIT
    assert b_handoff["person_c_accepted_manifest"]["sha256"] == (
        mod.C_ACCEPTED_MANIFEST_SHA256
    )
    assert b_handoff["capture_package_authority"]["sha256"] == (
        mod.C_CAPTURE_PACKAGE_MANIFEST_SHA256
    )
    coordinate = b_handoff["coordinate_authority"]
    assert coordinate["person_c_authority_sha256"] == (
        mod.C_COORDINATE_FRAME_AUTHORITY_SHA256
    )
    assert coordinate["person_b_cosign_sha256"] == mod.PERSON_B_COSIGN_SHA256
    assert coordinate["adapter_signoff"] == {"person_c": True, "person_b": True}
    assert coordinate["coordinate_frame_hash_preserved_across_cosign"] is True
    assert b_handoff["accepted_geometry"]["sha256"] == mod.ACCEPTED_GEOMETRY_SHA256
    empirical = b_handoff["empirical_visibility_binding"]
    assert empirical["records_sha256"] == mod.E_RECORDS_SHA256
    assert empirical["handoff_sha256"] == mod.E_HANDOFF_SHA256
    assert empirical["detector_identity_sha256"] == mod.E_DETECTOR_IDENTITY_SHA256
    assert empirical["person_c_executed_detector"] is False
    assert empirical["person_c_tuned_detector"] is False
    universe = b_handoff["frame_universe"]
    assert universe["model_frame_key_count"] == 2468
    assert universe["duplicate_key_count"] == 0
    assert universe["missing_key_count"] == 0


def test_c_to_b_handoff_does_not_generate_person_b_targets(b_handoff):
    assert b_handoff["person_c_generated_person_b_target_values"] is False
    assert b_handoff["person_c_modified_person_b_oracle_logic"] is False
    blob = json.dumps(b_handoff)
    for banned in ("mu_oracle_blocks\":", "var_oracle_blocks2\":",
                   "sigma_oracle_blocks\":", "log_sigma_oracle\":"):
        assert banned not in blob
    remaining = {
        item["input_id"]: item
        for item in b_handoff["remaining_inputs_owned_by_person_b_or_person_a"]
    }
    assert "person_b_oracle_target_values" in remaining
    assert remaining["person_b_oracle_target_values"]["owner_role"] == "person_b"
    assert "person_a_model_hash_and_preprocess_hash" in remaining


def test_c_to_b_handoff_tables_resolve_and_hash_match(b_handoff):
    for block in ("visibility_table", "geometric_visibility_table", "event_table"):
        entry = b_handoff[block]
        assert sha256(entry["path"]) == entry["sha256"], block
    assert b_handoff["visibility_table"]["row_count"] == 2468
    assert b_handoff["visibility_table"]["final_label_owner"] == "person_c"
    applicability = b_handoff["applicability_semantics"]
    assert applicability["applicable_row_count"] == 2108
    assert applicability["not_applicable_row_count"] == 360
    assert applicability["visible_flag_false_is_frozen_contract_behaviour"] is True


# ------------------------------------------------------------ housekeeping

def test_sha256_inventory_matches_every_published_artifact():
    inventory = load(f"{STATUS}/sha256_inventory.json")
    assert inventory["file_count"] == len(inventory["files"])
    for rel_path, digest in inventory["files"].items():
        assert os.path.exists(os.path.join(ROOT, rel_path)), rel_path
        assert sha256(rel_path) == digest, rel_path


def test_closure_receipt_declares_the_prohibited_actions_were_not_taken():
    closure = load(f"{STATUS}/closure_receipt.json")
    assert closure["foreign_branches_merged"] == []
    assert closure["foreign_branches_modified"] == []
    assert closure["detector_executed_by_person_c"] is False
    assert closure["detector_tuned_by_person_c"] is False
    assert closure["person_b_oracle_logic_modified"] is False
    assert closure["activation_extraction_performed"] is False
    assert closure["u4_supplemental_capture_executed"] is False
    assert closure["E_HANDOFF_ACCEPTED"] is True
    assert closure["VISIBILITY_JOIN_COMPLETE"] is True
    assert closure["EVENT_TABLE_READY"] is True
    assert closure["C_TO_B_ORACLE_INPUT_READY"] is True


def test_deterministic_regeneration():
    """Rebuilding must reproduce every published byte exactly."""
    inventory = load(f"{STATUS}/sha256_inventory.json")
    before = {rel: sha256(rel) for rel in inventory["files"]}
    result = subprocess.run(
        [sys.executable,
         os.path.join(ROOT, "scripts",
                      "build_person_c_66_cell_strict_visibility_v0_1.py")],
        capture_output=True, text=True, cwd=ROOT, timeout=1800,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    after = {rel: sha256(rel) for rel in inventory["files"]}
    drifted = sorted(rel for rel in before if before[rel] != after[rel])
    assert not drifted, f"non-deterministic artifacts: {drifted}"
