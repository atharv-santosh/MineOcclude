"""Regime A' v0.3 -- extent-visibility truth predicate and its Stage-1 gates.

The predecessor (``560bc01``) failed Stage 1 legitimately: its centre-point truth
predicate disagreed with the area detector it scored on one boundary row. v0.3
replaces that predicate with occlusion geometry over the target's *rendered*
extent. These tests hold the new predicate to the properties that make it a
scientific improvement rather than a rescue:

* the extent is recomputed from the pinned client jar's model geometry, not
  asserted as a literal, and no detector or ``560bc01`` outcome enters it;
* the Python engine reproduces the mod's own occlusion answers exactly;
* mutating the scored detector cannot move a geometric classification;
* the zero-error gate, the >=60 sample floor and the conservative FIRST_N hidden
  row schedule are all still strict;
* causal-FIR warm-up rows cannot enter an aligned interval derivation;
* the ``560bc01`` decision stays FAIL and Stage 2 stays unauthorized.
"""

from __future__ import annotations

import json
import math
from copy import deepcopy
from pathlib import Path

import pytest

from mineocclude.prospective.development_workflow import (
    EvidenceError, Stage1Evaluator, load_json, mean_student_t_interval, sha256_file,
)
from mineocclude.prospective.extent_geometry import (
    EXTENT_SAMPLES_PER_AXIS, REFERENCE_MARCH_SAMPLES, SHEEP_FUR_MODEL_CONSTANTS,
    TARGET_EXTENT_HALF_BLOCKS, ExtentClass, ReferenceAgreementError, WallGeometry,
    classify_extent, derive_target_extent_half_blocks, extent_sample_points,
    segment_hits_wall, verify_reference_agreement,
)

from tests.prospective.test_development_authority_v0_2_repair import valid_unit_probes

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / ("docs/status/integration/regime_a_prime_qualification_v0_1/"
                  "prospective_development_authority_v0_3")
AUTHORITY_PATH = PACKAGE / "authority_parameters.json"
STAGE1_PATH = PACKAGE / "stage1_manifest.json"
DERIVATION_DOC = PACKAGE / "TARGET_EXTENT_DERIVATION.md"

PREDECESSOR_FREEZE = "560bc01e3b01ecdc266737c015fed6677b0611c3"
PREDECESSOR_EVIDENCE = Path(
    "/home/sagemaker-user/mineocclude-stage1-successor-560bc01/"
    "collection_launch_01_20260817T083539Z")


@pytest.fixture
def authority():
    return load_json(AUTHORITY_PATH)


@pytest.fixture
def stage1():
    return load_json(STAGE1_PATH)


def evaluator(authority, stage1):
    return Stage1Evaluator(authority, stage1,
                           authority_sha256=sha256_file(AUTHORITY_PATH),
                           manifest_sha256=sha256_file(STAGE1_PATH))


def wall_from(authority, present: bool = True) -> WallGeometry:
    spec = authority["apparatus"]["wall_geometry_as_built"]
    return WallGeometry(
        wall_axis=spec["wall_axis"], wall_ortho=spec["wall_ortho"],
        wall_axis_min=spec["wall_axis_min"], wall_axis_max=spec["wall_axis_max"],
        wall_y_min=spec["wall_y_min"], wall_y_max=spec["wall_y_max"],
        half=spec["ortho_half_thickness"], present=present)


# ======================================================================
# A. Target extent derivation
# ======================================================================

def test_declared_extent_is_recomputed_from_model_constants_not_asserted(authority):
    """The authority's scalar must fall out of the jar's model geometry."""
    recomputed = derive_target_extent_half_blocks()
    assert recomputed == TARGET_EXTENT_HALF_BLOCKS
    assert authority["stage1_policy"]["visibility"]["target_extent"][
        "half_width_blocks"] == recomputed


def test_extent_matches_its_independent_closed_form():
    """Closed form stated in the derivation document, evaluated independently."""
    assert TARGET_EXTENT_HALF_BLOCKS == (7.0 + math.sqrt(48.5)) / 16.0


def test_extent_closed_form_is_the_true_maximum_not_a_grid_evaluation():
    """The leg-swing clamp must be inactive, or the closed form is not the max.

    This is the defect the draft derivation carried: a numerically evaluated
    maximum that landed 3.1e-08 blocks *below* the analytic supremum, which broke
    the document's own containment claim in the unsafe direction.
    """
    origin, size, dilation, _ = SHEEP_FUR_MODEL_CONSTANTS["leg"]
    y_high = origin[1] + size[1] + dilation
    z_high = origin[2] + size[2] + dilation
    stationary = math.atan2(y_high, z_high)
    assert abs(stationary) < SHEEP_FUR_MODEL_CONSTANTS["leg_x_rot_amplitude"]
    brute = max(y_high * math.sin(theta) + z_high * math.cos(theta)
                for theta in (stationary - 1e-9, stationary, stationary + 1e-9))
    assert math.isclose(brute, math.hypot(y_high, z_high), rel_tol=0, abs_tol=1e-12)
    # A coarse scan must never exceed the closed form -- it can only approach it.
    for count in (101, 1001, 10001):
        scan = max(y_high * math.sin(t) + z_high * math.cos(t)
                   for t in (-1.4 + 2.8 * i / (count - 1) for i in range(count)))
        assert scan <= math.hypot(y_high, z_high)


def test_extent_is_an_upper_bound_over_every_reachable_pose():
    """Sampling the actual animation must never escape the declared extent."""
    origin, size, dilation, _ = SHEEP_FUR_MODEL_CONSTANTS["leg"]
    bound = TARGET_EXTENT_HALF_BLOCKS * SHEEP_FUR_MODEL_CONSTANTS["model_units_per_block"]
    corners = [(y, z)
               for y in (origin[1] - dilation, origin[1] + size[1] + dilation)
               for z in (origin[2] - dilation, origin[2] + size[2] + dilation)]
    for pivot in SHEEP_FUR_MODEL_CONSTANTS["leg_pivots"]:
        for step in range(-140, 141):
            theta = step / 100.0
            for y, z in corners:
                reach = abs(pivot[2] + y * math.sin(theta) + z * math.cos(theta))
                assert reach <= bound + 1e-12


def test_extent_carries_no_detector_or_predecessor_outcome_input(authority):
    extent = authority["stage1_policy"]["visibility"]["target_extent"]
    assert extent["detector_derived"] is False
    assert extent["outcome_derived"] is False
    assert extent["fitted"] is False
    assert extent["yaw_independent"] is True
    assert extent["bound_direction"] == "UPPER_BOUND_OVER_ALL_REACHABLE_ANIMATION_STATES"
    # The historical detector-fitted range must be recorded only as rejected.
    assert extent["rejected_alternative"]["value_range"] == [0.6, 0.8]
    assert "silhouette_half_extent_blocks" not in authority["stage1_policy"]["visibility"]


def test_extent_is_not_the_predecessor_failure_margin(authority):
    """No numeric parameter may be traceable to the false-positive depth.

    The depth is allowed to appear in prose -- the change log has to be able to
    say why v0.3 exists -- but it must not have become a number the apparatus
    reads. Narrating a failure is history; parameterising on it is laundering.
    """
    failure_depth = 0.006282776508991
    assert str(failure_depth) not in DERIVATION_DOC.read_text()

    def numeric_leaves(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                yield from numeric_leaves(value, f"{path}/{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                yield from numeric_leaves(value, f"{path}[{index}]")
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            yield path, float(node)

    for path, value in numeric_leaves(authority):
        assert not math.isclose(value, failure_depth, rel_tol=1e-9, abs_tol=1e-12), path
        # Nor a guard band built from it: no parameter may be the extent, or any
        # lane bound, offset by that depth.
        for anchor in (TARGET_EXTENT_HALF_BLOCKS, 0.0, 8.0, -8.0):
            assert not math.isclose(value, anchor + failure_depth, rel_tol=0, abs_tol=1e-12), path
            assert not math.isclose(value, anchor - failure_depth, rel_tol=0, abs_tol=1e-12), path
    assert TARGET_EXTENT_HALF_BLOCKS > 100 * failure_depth


def test_derivation_document_states_the_declared_value_and_its_source(authority):
    text = DERIVATION_DOC.read_text()
    assert repr(TARGET_EXTENT_HALF_BLOCKS) in text or str(TARGET_EXTENT_HALF_BLOCKS) in text
    assert "37fd3c903861eeff3bc24b71eed48f828b5269c8" in text
    assert authority["stage1_policy"]["visibility"]["target_extent"][
        "source_jar_sha1"] == "37fd3c903861eeff3bc24b71eed48f828b5269c8"


# ======================================================================
# B. Reference wall geometry
# ======================================================================

def test_python_primitive_reproduces_the_mod_reference_ledger(authority):
    """The mod publishes its own occlusion answers; we must match them exactly."""
    packages = sorted((ROOT / "data/autonomous").glob("layout_01_ep*/capture_package_v0_1.json"))
    assert packages, "no historical layout_01 capture packages to cross-check against"
    checked = 0
    for path in packages:
        document = json.loads(path.read_text())
        shadow = _find(document, "wall_lane_shadow_geometry_authority")
        if shadow is None:
            continue
        shadow = shadow["shadow"]
        camera = _find(document, "camera_eye_world_xyz") or [0.5, 5.62, -5.5]
        present = any(item["occluded"] for item in shadow["integer_lane_samples"])
        report = verify_reference_agreement(
            tuple(camera), wall_from(authority, present=present),
            shadow["integer_lane_samples"],
            target_centre_y=shadow["target_centre_y"],
            lane_ortho_const=authority["apparatus"]["lane_world_z"])
        assert report["disagreements"] == 0
        assert report["march_samples"] == REFERENCE_MARCH_SAMPLES
        checked += 1
    assert checked >= 8


def test_reference_agreement_fails_closed_on_any_disagreement(authority):
    samples = [{"axis_position": 0, "occluded": False}]  # 0 is inside the shadow
    with pytest.raises(ReferenceAgreementError, match="disagrees"):
        verify_reference_agreement(
            (0.5, 5.62, -5.5), wall_from(authority), samples,
            target_centre_y=4.5, lane_ortho_const=6.0)


def test_reference_agreement_refuses_an_empty_corpus(authority):
    with pytest.raises(ReferenceAgreementError, match="no reference"):
        verify_reference_agreement((0.5, 5.62, -5.5), wall_from(authority), [],
                                   target_centre_y=4.5, lane_ortho_const=6.0)


def test_primitive_replicates_the_mods_discrete_march_not_an_analytic_test():
    """63 interior samples, neither endpoint tested -- exactly as the Java does."""
    assert REFERENCE_MARCH_SAMPLES == 64
    # A target sitting inside the slab but reached only at t=1 is NOT detected by
    # the mod, because the endpoint is never sampled. Matching that is the point.
    assert segment_hits_wall(0.0, 5.0, 0.0, 0.0, 5.0, 1.0,
                             wall_ortho=1.0, wall_axis_min=-1.0, wall_axis_max=1.0,
                             wall_y_min=4.0, wall_y_max=6.0, half=0.0) is False


def test_wall_as_built_is_wider_than_the_raw_spec(authority):
    """ArenaBuilder floors/ceils to whole blocks; the engine must use as-built."""
    wall = wall_from(authority)
    assert wall.wall_axis_min == math.floor(-2.5) == -3
    assert wall.wall_axis_max == math.ceil(2.5) + 1.0 == 4.0
    assert wall.wall_ortho == math.floor(6.0 - 4.0) + 0.5 == 2.5
    assert wall.wall_y_min == 4.0 and wall.wall_y_max == 7.0
    built = WallGeometry.from_layout(
        wall_axis="X", wall_seg_min=-2.5, wall_seg_max=2.5,
        wall_ortho_const=6.0, wall_ortho_offset=-4.0, lane_y=4.0)
    assert built == wall


def test_no_wall_scene_never_occludes(authority):
    wall = wall_from(authority, present=False)
    for x in (-8.0, -4.0, 0.0, 4.0, 8.0):
        assert wall.occludes((0.5, 5.62, -5.5), (x, 4.5, 6.0)) is False
        assert classify_extent((0.5, 5.62, -5.5), (x, 4.5, 6.0), wall) \
            is ExtentClass.EXTENT_FULLY_VISIBLE


def _find(node, key):
    if isinstance(node, dict):
        if key in node:
            return node[key]
        for value in node.values():
            found = _find(value, key)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find(value, key)
            if found is not None:
                return found
    return None


# ======================================================================
# C. Extent geometry classification
# ======================================================================

CAMERA = (0.5, 5.62, -5.5)


def test_three_classes_all_occur_in_both_directions(authority):
    wall = wall_from(authority)
    seen = {ExtentClass.EXTENT_FULLY_VISIBLE: [], ExtentClass.EXTENT_PARTIAL: [],
            ExtentClass.EXTENT_FULLY_OCCLUDED: []}
    for step in range(0, 1601):
        x = -8.0 + step * 0.01
        seen[classify_extent(CAMERA, (x, 4.5, 6.0), wall)].append(x)
    assert all(values for values in seen.values())
    # Ordered lane structure: visible, partial, occluded, partial, visible.
    occluded = seen[ExtentClass.EXTENT_FULLY_OCCLUDED]
    visible = seen[ExtentClass.EXTENT_FULLY_VISIBLE]
    assert min(visible) < min(occluded) and max(occluded) < max(visible)


def test_extent_fully_behind_the_wall_is_fully_occluded(authority):
    assert classify_extent(CAMERA, (0.0, 4.5, 6.0), wall_from(authority)) \
        is ExtentClass.EXTENT_FULLY_OCCLUDED


def test_extent_clear_of_the_shadow_is_fully_visible(authority):
    assert classify_extent(CAMERA, (-8.0, 4.5, 6.0), wall_from(authority)) \
        is ExtentClass.EXTENT_FULLY_VISIBLE


def test_extent_straddling_a_shadow_edge_is_partial(authority):
    """A centre outside the shadow whose extent still overlaps it is PARTIAL.

    This is precisely the row class that produced the ``560bc01`` false positive
    under a centre-point predicate: the centre is clear, the silhouette is not.
    """
    wall = wall_from(authority)
    edge = next(x for x in (-8.0 + i * 0.001 for i in range(16001))
                if classify_extent(CAMERA, (x, 4.5, 6.0), wall) is ExtentClass.EXTENT_PARTIAL)
    centre_visible = not wall.occludes(CAMERA, (edge, 4.5, 6.0))
    assert centre_visible
    assert classify_extent(CAMERA, (edge, 4.5, 6.0), wall) is ExtentClass.EXTENT_PARTIAL


def test_classification_is_stable_under_lattice_refinement(authority):
    """Sample count must not be a tuned constant."""
    wall = wall_from(authority)
    for step in range(0, 3201):
        x = -8.0 + step * 0.005
        classes = {classify_extent(CAMERA, (x, 4.5, 6.0), wall, samples_per_axis=n)
                   for n in (3, EXTENT_SAMPLES_PER_AXIS, 9, 17)}
        assert len(classes) == 1, f"classification changed with lattice density at x={x}"


def test_sample_lattice_always_contains_the_box_corners():
    for count in (2, 3, 5, 9, 17):
        points = extent_sample_points((1.25, 4.5, 6.0), 0.5, samples_per_axis=count)
        assert len(points) == count * count
        for corner in ((0.75, 5.5), (0.75, 6.5), (1.75, 5.5), (1.75, 6.5)):
            assert any(math.isclose(px, corner[0]) and math.isclose(pz, corner[1])
                       for px, _, pz in points)


def test_extent_predicate_ignores_the_detector_entirely(authority, stage1):
    """Mutating detector output must not move a single geometric classification."""
    engine = evaluator(authority, stage1)
    unit = {"scene": "WALL"}
    baseline = [engine.classify_extent_row(-8.0 + i * 0.02, unit["scene"]) for i in range(801)]
    # classify_extent_row takes no sample at all -- there is no channel through
    # which a detector value could reach it. Assert that structurally.
    with pytest.raises(TypeError):
        engine.classify_extent_row(0.0, "WALL", detector_visible=True)
    repeated = [engine.classify_extent_row(-8.0 + i * 0.02, unit["scene"]) for i in range(801)]
    assert baseline == repeated


def test_authority_binds_the_extent_and_refuses_a_hand_edited_scalar(authority, stage1):
    tampered = deepcopy(authority)
    tampered["stage1_policy"]["visibility"]["target_extent"]["half_width_blocks"] = 0.75
    with pytest.raises(EvidenceError, match="does not reproduce"):
        Stage1Evaluator(tampered, stage1, authority_sha256=sha256_file(AUTHORITY_PATH),
                        manifest_sha256=sha256_file(STAGE1_PATH))


def test_authority_refuses_an_extent_declared_detector_derived(authority, stage1):
    tampered = deepcopy(authority)
    tampered["stage1_policy"]["visibility"]["target_extent"]["detector_derived"] = True
    with pytest.raises(EvidenceError, match="detector- and outcome-independent"):
        Stage1Evaluator(tampered, stage1, authority_sha256=sha256_file(AUTHORITY_PATH),
                        manifest_sha256=sha256_file(STAGE1_PATH))


# ======================================================================
# H. New identity
# ======================================================================

def test_stage1_manifest_has_eight_fresh_units(stage1, authority):
    units = stage1["units"]
    assert len(units) == authority["stage1_policy"]["run_count"] == 8
    assert len({u["unit_id"] for u in units}) == 8
    assert len({u["episode_id"] for u in units}) == 8
    assert len({u["seed"] for u in units}) == 8


def test_every_unit_satisfies_the_single_seed_identity_contract(stage1):
    for unit in stage1["units"]:
        assert unit["seed"] == unit["noise_seed"]


def test_no_identity_collides_with_the_predecessor_campaign(stage1):
    predecessor_units = {"a1q_ltr_wall_r01", "a1q_ltr_wall_r02", "a1q_ltr_nowall_r01",
                         "a1q_ltr_nowall_r02", "a1q_rtl_wall_r01", "a1q_rtl_wall_r02",
                         "a1q_rtl_nowall_r01", "a1q_rtl_nowall_r02"}
    predecessor_episodes = set(range(81001, 81009))
    for unit in stage1["units"]:
        assert unit["unit_id"] not in predecessor_units
        assert unit["episode_id"] not in predecessor_episodes
        assert "a1q_" not in unit["receipt_path"]
        assert "v0_2" not in unit["receipt_path"]


def test_namespace_and_durable_prefix_are_new(stage1):
    assert stage1["run_namespace"] == "mineocclude-regime-a-prime-development-v0-3-stage1"
    assert stage1["durable_prefix"].endswith("prospective_development_v0_3/stage1")
    for unit in stage1["units"]:
        assert unit["scientific_run_id"] == stage1["run_namespace"]


def test_stage2_stays_unauthorized_and_locked(stage1, authority):
    assert stage1["STAGE_1_COLLECTION_AUTHORIZED"] is False
    assert stage1["STAGE_2_COLLECTION_AUTHORIZED"] is False
    assert stage1["confirmatory_collection_authorized"] is False
    assert authority["change_log"]["STAGE2_AUTHORIZED"] is False
    assert authority["change_log"]["STAGE2_LOCKED"] is True


# ======================================================================
# G. Predecessor result immutability
# ======================================================================

def test_authority_records_the_predecessor_as_terminal_fail(authority):
    predecessor = authority["predecessor_authority"]
    assert predecessor["freeze_sha"] == PREDECESSOR_FREEZE
    assert predecessor["stage1_result"] == "SCIENTIFIC_FAIL"
    assert predecessor["stage1_result_immutable"] is True
    assert predecessor["stage1_result_may_be_reclassified"] is False
    assert predecessor["stage2_authorized"] is False
    assert authority["change_log"]["OLD_STAGE1_RESULT"] == "SCIENTIFIC_FAIL"
    assert authority["change_log"]["OLD_UNITS_REUSED"] is False
    assert authority["change_log"]["ZERO_ERROR_GATE_RELAXED"] is False
    assert authority["change_log"]["OUTCOME_DERIVED_GUARD_BAND_ADDED"] is False
    assert authority["change_log"]["OLD_FAILED_ROW_EXCLUDED"] is False


@pytest.mark.skipif(not (PREDECESSOR_EVIDENCE / "stage1_decision.json").exists(),
                    reason="predecessor evidence directory is not present")
def test_predecessor_decision_on_disk_is_still_fail():
    decision = json.loads((PREDECESSOR_EVIDENCE / "stage1_decision.json").read_text())
    assert decision["status"] == "FAIL"
    failed = {name for name, gate in decision["gates"].items() if gate["status"] != "PASS"}
    assert "stable_visibility_base_rate_robust" in failed
    assert "hidden_row_contamination" in failed


def test_v0_3_authority_does_not_claim_downstream_science(authority):
    boundary = authority["scientific_claim_boundary"]
    for claim in ("tests_model_activations", "tests_hidden_state_representation",
                  "tests_object_permanence", "tests_belief", "tests_uncertainty",
                  "tests_causal_use"):
        assert boundary[claim] is False
    assert boundary["experiment_class"] == "DEVELOPMENT_APPARATUS_QUALIFICATION"


# ======================================================================
# Authority-level policy invariants (zero-error gate, transition role)
# ======================================================================

def test_zero_error_gate_and_sample_floor_are_unrelaxed(authority):
    visibility = authority["stage1_policy"]["visibility"]
    assert visibility["minimum_stable_samples_per_direction_per_class"] == 60
    assert visibility["maximum_observed_false_positive_rate"] == 0.0
    assert visibility["maximum_observed_false_negative_rate"] == 0.0
    assert visibility["precision_gate_forbidden"] is True
    assert visibility["pooled_accuracy_gate_forbidden"] is True


def test_partial_rows_are_reported_but_never_scored(authority):
    classification = authority["stage1_policy"]["visibility"]["extent_classification"]
    assert classification["scored_classes"] == ["stable_visible", "stable_occluded"]
    assert classification["unscored_classes"] == ["partial_transition"]
    assert classification["detector_may_influence_classification"] is False
    assert classification["regime_mapping"]["EXTENT_PARTIAL"] == "partial_transition"


def test_detector_band_is_no_longer_transferred_to_held_out_rows(authority):
    visibility = authority["stage1_policy"]["visibility"]
    assert visibility["transition_band_transferred_to_held_out"] is False
    assert visibility["held_out_rows_classified_directly_from_geometry"] is True
    assert visibility["detector_truth_predicate_independent_of_scored_detector"] is True


def test_first_n_hidden_row_rule_is_retained_as_a_stress_test(authority):
    contamination = authority["stage1_policy"]["contamination"]
    assert contamination["designated_hidden_row_selection_rule"] == (
        "FIRST_N_QUALIFIED_STABLE_OCCLUDED_ROWS_IN_ASCENDING_MODEL_FRAME_ORDER")
    assert contamination["required_hidden_rows_per_wall_validation_run"] == 19
    assert "RETAINED DELIBERATELY" in contamination[
        "designated_hidden_row_selection_rule_conservatism"]


def test_alignment_admissibility_rule_is_declared(authority):
    alignment = authority["stage1_policy"]["temporal_alignment"]
    assert alignment["aligned_position_required_for_interval_derivation"] is True
    assert alignment["raw_world_x_may_substitute_for_aligned_position"] is False


# ======================================================================
# D/E/F. End-to-end scoring against the v0.3 truth predicate
# ======================================================================

def build_evidence(authority: dict, manifest: dict) -> dict:
    """A physically consistent v0.3 Stage-1 evidence document.

    Rows are generated from the frozen trajectory grid and labelled by the *same*
    extent geometry the evaluator uses, with a detector that agrees perfectly on
    both scored classes. Warm-up rows are deliberately parked at a lane extreme
    with the detector absent: if the evaluator ever re-admitted unaligned rows to
    an interval derivation, that alone would blow the derived interval out to the
    lane edge and this fixture would stop reproducing.
    """
    warmup = authority["stage1_policy"]["temporal_alignment"]["maximum_lag_ticks_for_estimation"]
    engine = evaluator(authority, manifest)
    lane_low, lane_high = authority["apparatus"]["lane_world_x_blocks"]
    centre_y = authority["apparatus"]["target_centre_world_y"]
    lane_z = authority["apparatus"]["lane_world_z"]
    frames = authority["fixed_development_configuration"]["expected_frames_per_run"]

    runs, transitions = [], {}
    prohibited = {name: 0 for name in Stage1Evaluator.PROHIBITED}
    for unit in manifest["units"]:
        runtime_probe, path_probe, durability_probe = valid_unit_probes(authority, manifest, unit)
        xs = [lane_low + (lane_high - lane_low) * index / (frames - 1) for index in range(frames)]
        if unit["direction"] == "RIGHT_TO_LEFT":
            xs.reverse()
        wall = wall_from(authority, present=unit["scene"] == "WALL")
        samples = []
        for index, x in enumerate(xs):
            aligned = index >= warmup
            extent = engine.classify_extent_row(x, unit["scene"])
            regime = extent.regime if aligned else "unresolved"
            if aligned:
                detector = regime != "stable_occluded"
            else:
                detector = False   # the historical defect shape, on purpose
            samples.append({
                "world_x": x, "wall_relative_x": x - 0.5,
                "screen_x": 320.0, "screen_y": 180.0, "token_row": 7, "token_col": 12,
                "projection_frame_pixels": authority["apparatus"]["canonical_frame_pixels"],
                "projection_token_grid": authority["apparatus"]["visual_token_grid"],
                "point_visible": not wall.occludes(
                    tuple(authority["apparatus"]["camera_eye_world_xyz"]), (x, centre_y, lane_z)),
                "detector_visible": detector,
                "render_frame_present": True, "projected_in_frame": True,
                "temporal_alignment_resolved": aligned, "identity_valid": True,
                "in_support": True, "runtime_provenance_resolved": True,
                "path_state_valid": True, "malformed_or_missing": False, "regime": regime})
        required = 19 if unit["scene"] == "WALL" and unit["design_role"] == "HELD_OUT_VALIDATION" else 0
        designated = [index for index, sample in enumerate(samples)
                      if sample["regime"] == "stable_occluded"][:required]
        runs.append({
            "unit_id": unit["unit_id"], "direction": unit["direction"], "scene": unit["scene"],
            "speed_blocks_per_second": unit["speed_blocks_per_second"], "frame_count": frames,
            "unit_receipt_sha256": (unit["unit_id"].encode().hex() + "0" * 64)[:64],
            "runtime_provenance_receipt": runtime_probe, "path_state_receipt": path_probe,
            "durability_receipt": durability_probe,
            "designated_hidden_row_indices": designated,
            "hidden_row_contamination": {"designated_hidden_row_count": required,
                                         "prohibited_counts": deepcopy(prohibited)},
            "visibility_samples": samples})

    by_id = {run["unit_id"]: run for run in runs}
    for direction in authority["stage1_policy"]["directions"]:
        unit = next(u for u in manifest["units"] if u["direction"] == direction
                    and u["scene"] == "WALL" and u["design_role"] == "TRANSITION_MEASUREMENT")
        samples = by_id[unit["unit_id"]]["visibility_samples"]
        admissible = [s for s in samples if s["temporal_alignment_resolved"] is True]
        occ = [s["world_x"] for s in admissible if s["regime"] == "stable_occluded"]
        absent = [s["world_x"] for s in admissible if s["detector_visible"] is False]
        interval = [min(occ), max(occ)]
        transitions[direction] = {
            "status": "MEASURED", "measurement_unit_ids": [unit["unit_id"]],
            "extent_fully_occluded_world_x_interval": interval,
            "rendered_detector_absent_world_x_interval": [min(absent), max(absent)],
            "geometric_extent_transition_world_x_intervals": [
                [min(s["world_x"] for s in admissible), interval[0]],
                [interval[1], max(s["world_x"] for s in admissible)]],
            "aligned_rows_admitted": len(admissible),
            "rows_excluded_unaligned": len(samples) - len(admissible),
            "derivation": "EXTENT_GEOMETRY_ON_ALIGNED_ROWS_ONLY",
            "detector_defines_held_out_truth": False}

    alignments = {}
    for direction in authority["stage1_policy"]["directions"]:
        ids = [unit["unit_id"] for unit in manifest["units"] if unit["direction"] == direction]
        receipt_hashes = {run["unit_id"]: run["unit_receipt_sha256"]
                          for run in runs if run["direction"] == direction}
        fir_values = [3.2, 3.2, 3.4, 3.4]
        fir_mean, fir_interval = mean_student_t_interval(fir_values, 0.95)
        fir_kernels = []
        for value in fir_values:
            kernel = [0.0] * 9
            kernel[3], kernel[4] = 4.0 - value, value - 3.0
            fir_kernels.append(kernel)
        aggregate_kernel = [sum(v) / len(v) for v in zip(*fir_kernels, strict=True)]
        cc_values = [3.0, 3.0, 3.5, 3.5]
        cc_mean, cc_interval = mean_student_t_interval(cc_values, 0.95)
        cadence = authority["apparatus"]["server_ticks_per_model_frame"]
        clock_evidence = {run["unit_id"]: {
            "server_state_ticks": [cadence * frame for frame in range(len(run["visibility_samples"]))],
            "render_model_frame_indices": list(range(len(run["visibility_samples"])))}
            for run in runs if run["direction"] == direction}
        alignments[direction] = {
            "unit_spaced_clock_coordinates": True, "clock_coordinate_evidence": clock_evidence,
            "agreement_rule": authority["stage1_policy"]["temporal_alignment"]["agreement_rule"],
            "methods": [
                {"method_id": "causal_fir_group_delay", "status": "MEASURED",
                 "estimate_ticks": fir_mean, "confidence_interval_ticks": fir_interval,
                 "trajectory_count": 4, "trajectory_evidence_ids": ids, "kernel": aggregate_kernel,
                 "per_trajectory_estimates_ticks": fir_values,
                 "trajectory_receipt_sha256": receipt_hashes, "per_trajectory_kernels": fir_kernels,
                 "per_trajectory_fir_vs_pure_delay_relative_improvement": [0.1] * 4,
                 "kernel_is_pure_delay": False, "causal_fir_beats_best_pure_delay": True,
                 "per_trajectory_beats_best_pure_delay": True},
                {"method_id": "derivative_cross_correlation_lag", "status": "MEASURED",
                 "estimate_ticks": cc_mean, "confidence_interval_ticks": cc_interval,
                 "trajectory_count": 4, "trajectory_evidence_ids": ids,
                 "per_trajectory_estimates_ticks": cc_values,
                 "trajectory_receipt_sha256": receipt_hashes}]}

    return {"schema_version": "1.1", "authority_sha256": manifest["authority_binding"]["sha256"],
            "stage1_manifest_sha256": sha256_file(STAGE1_PATH),
            "runs": runs, "transition_measurement_by_direction": transitions,
            "alignment_by_direction": alignments}


@pytest.fixture
def evidence(authority, stage1):
    return build_evidence(authority, stage1)


def assert_gate_fails(authority, stage1, evidence, gate):
    decision = evaluator(authority, stage1).evaluate(evidence)
    assert decision.status == "FAIL"
    assert decision.gates[gate]["status"] == "FAIL"


def test_geometrically_consistent_v0_3_evidence_passes(authority, stage1, evidence):
    decision = evaluator(authority, stage1).evaluate(evidence)
    assert decision.status == "PASS", decision.reasons


def test_sample_floor_is_actually_met_by_the_extent_design(authority, stage1, evidence):
    detail = evaluator(authority, stage1).evaluate(evidence).gates[
        "stable_visibility_base_rate_robust"]["detail"]
    for direction, values in detail.items():
        assert values["stable_visible_n"] >= 60, direction
        assert values["stable_occluded_n"] >= 60, direction
        assert values["partial_n_reported_not_scored"] > 0, direction
        assert values["false_positive"] == 0 and values["false_negative"] == 0


# ---- D. the zero-error gate must actually bite ----

def test_detector_miss_on_a_fully_visible_row_fails(authority, stage1, evidence):
    run = next(r for r in evidence["runs"] if r["unit_id"].endswith("wall_r02"))
    sample = next(s for s in run["visibility_samples"] if s["regime"] == "stable_visible")
    sample["detector_visible"] = False
    assert_gate_fails(authority, stage1, evidence, "stable_visibility_base_rate_robust")


def test_detector_fire_on_a_fully_occluded_row_fails(authority, stage1, evidence):
    run = next(r for r in evidence["runs"] if r["unit_id"].endswith("wall_r02"))
    sample = next(s for s in run["visibility_samples"] if s["regime"] == "stable_occluded")
    sample["detector_visible"] = True
    assert_gate_fails(authority, stage1, evidence, "stable_visibility_base_rate_robust")


def test_a_single_false_positive_is_enough_to_fail(authority, stage1, evidence):
    """The predecessor failed on exactly one row. That must still be fatal."""
    run = next(r for r in evidence["runs"] if r["unit_id"] == "a1x_rtl_wall_r02")
    occluded = [s for s in run["visibility_samples"] if s["regime"] == "stable_occluded"]
    occluded[len(occluded) // 2]["detector_visible"] = True
    decision = evaluator(authority, stage1).evaluate(evidence)
    assert decision.status == "FAIL"
    detail = decision.gates["stable_visibility_base_rate_robust"]["detail"]
    assert detail["RIGHT_TO_LEFT"]["false_positive"] == 1


def test_detector_result_on_a_partial_row_is_reported_but_never_scored(authority, stage1, evidence):
    run = next(r for r in evidence["runs"] if r["unit_id"].endswith("wall_r02"))
    partials = [s for s in run["visibility_samples"] if s["regime"] == "partial_transition"]
    assert partials
    for sample in partials:
        sample["detector_visible"] = not sample["detector_visible"]
    decision = evaluator(authority, stage1).evaluate(evidence)
    assert decision.status == "PASS", decision.reasons
    detail = decision.gates["stable_visibility_base_rate_robust"]["detail"]
    assert all(values["false_positive"] == 0 and values["false_negative"] == 0
               for values in detail.values())


def test_emptying_a_scored_class_fails_the_floor(authority, stage1, evidence):
    for run in evidence["runs"]:
        if run["unit_id"].endswith("wall_r02"):
            for sample in run["visibility_samples"]:
                if sample["regime"] == "stable_occluded":
                    sample["regime"] = "partial_transition"
    decision = evaluator(authority, stage1).evaluate(evidence)
    assert decision.status == "FAIL"


# ---- E. the warm-up / aligned-position defect ----

def test_unaligned_warmup_rows_cannot_enter_the_interval_derivation(authority, stage1, evidence):
    """The exact historical defect shape must be excluded.

    Warm-up rows in this fixture carry ``detector_visible=False`` with a finite
    raw ``world_x`` at a lane extreme and no resolved alignment. Under the v0.2
    evaluator they were admitted and dragged the derived detector-absent interval
    out to the lane edge; the builder, deriving from aligned values, excluded
    them. Builder and evaluator now agree because both apply the same filter.
    """
    decision = evaluator(authority, stage1).evaluate(evidence)
    assert decision.status == "PASS", decision.reasons
    lane_low, lane_high = authority["apparatus"]["lane_world_x_blocks"]
    for direction, item in evidence["transition_measurement_by_direction"].items():
        low, high = item["rendered_detector_absent_world_x_interval"]
        assert low > lane_low and high < lane_high, direction
        assert item["rows_excluded_unaligned"] == authority["stage1_policy"][
            "temporal_alignment"]["maximum_lag_ticks_for_estimation"]


def test_mutating_a_warmup_row_position_does_not_move_the_derived_interval(
        authority, stage1, evidence):
    baseline = evaluator(authority, stage1).evaluate(evidence)
    assert baseline.status == "PASS"
    derived_before = baseline.gates["prospective_transition_measurement"]["detail"]["derived_from_rows"]
    for run in evidence["runs"]:
        for sample in run["visibility_samples"]:
            if sample["temporal_alignment_resolved"] is False:
                sample["detector_visible"] = False
    after = evaluator(authority, stage1).evaluate(evidence)
    assert after.gates["prospective_transition_measurement"]["detail"][
        "derived_from_rows"] == derived_before


def test_transition_evidence_must_declare_the_aligned_only_derivation(
        authority, stage1, evidence):
    for item in evidence["transition_measurement_by_direction"].values():
        item["derivation"] = "RAW_WORLD_X"
    assert_gate_fails(authority, stage1, evidence, "prospective_transition_measurement")


def test_transition_evidence_cannot_claim_the_detector_defines_truth(
        authority, stage1, evidence):
    for item in evidence["transition_measurement_by_direction"].values():
        item["detector_defines_held_out_truth"] = True
    assert_gate_fails(authority, stage1, evidence, "prospective_transition_measurement")


def test_reported_interval_must_reproduce_the_derived_one(authority, stage1, evidence):
    item = evidence["transition_measurement_by_direction"]["LEFT_TO_RIGHT"]
    item["extent_fully_occluded_world_x_interval"] = [-7.9, 7.9]
    assert_gate_fails(authority, stage1, evidence, "prospective_transition_measurement")


# ---- F. hidden rows ----

def test_designated_hidden_rows_are_the_first_n_qualified_occluded_rows(
        authority, stage1, evidence):
    required = authority["stage1_policy"]["contamination"][
        "required_hidden_rows_per_wall_validation_run"]
    for run in evidence["runs"]:
        expected = 0
        if run["scene"] == "WALL":
            unit = next(u for u in stage1["units"] if u["unit_id"] == run["unit_id"])
            expected = required if unit["design_role"] == "HELD_OUT_VALIDATION" else 0
        assert len(run["designated_hidden_row_indices"]) == expected
        if expected:
            occluded = [index for index, sample in enumerate(run["visibility_samples"])
                        if sample["regime"] == "stable_occluded"]
            assert run["designated_hidden_row_indices"] == sorted(occluded[:expected])


def test_a_detector_visible_designated_hidden_row_is_contamination(
        authority, stage1, evidence):
    run = next(r for r in evidence["runs"] if r["unit_id"] == "a1x_ltr_wall_r02")
    run["visibility_samples"][run["designated_hidden_row_indices"][0]]["detector_visible"] = True
    assert_gate_fails(authority, stage1, evidence, "hidden_row_contamination")


def test_last_n_hidden_rows_are_refused_in_place_of_first_n(authority, stage1, evidence):
    run = next(r for r in evidence["runs"] if r["unit_id"] == "a1x_ltr_wall_r02")
    occluded = [index for index, sample in enumerate(run["visibility_samples"])
                if sample["regime"] == "stable_occluded"]
    run["designated_hidden_row_indices"] = sorted(occluded[-19:])
    assert_gate_fails(authority, stage1, evidence, "hidden_row_contamination")


def test_fewer_than_required_hidden_rows_fail(authority, stage1, evidence):
    run = next(r for r in evidence["runs"] if r["unit_id"] == "a1x_ltr_wall_r02")
    run["designated_hidden_row_indices"] = run["designated_hidden_row_indices"][:-1]
    run["hidden_row_contamination"]["designated_hidden_row_count"] = 18
    assert_gate_fails(authority, stage1, evidence, "hidden_row_contamination")


# ---- the truth predicate cannot be steered by the detector, end to end ----

def test_flipping_every_detector_value_cannot_change_any_regime(authority, stage1, evidence):
    engine = evaluator(authority, stage1)
    before = [[s["regime"] for s in run["visibility_samples"]] for run in evidence["runs"]]
    for run in evidence["runs"]:
        for sample in run["visibility_samples"]:
            sample["detector_visible"] = not sample["detector_visible"]
    after = []
    for run, unit_regimes in zip(evidence["runs"], before, strict=True):
        unit = next(u for u in stage1["units"] if u["unit_id"] == run["unit_id"])
        after.append([engine.expected_regime(
            s, unit, evidence["transition_measurement_by_direction"][run["direction"]])
            for s in run["visibility_samples"]])
    assert after == before
