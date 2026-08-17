#!/usr/bin/env python3
"""Materialize the Regime A' v0.3 prospective development authority.

v0.3 is derived from the frozen v0.2 authority by an explicit, enumerated delta
rather than being retyped, so every parameter v0.3 did **not** deliberately
change is provably byte-identical to the authority the ``560bc01`` Stage-1 ran
under. The deltas are listed in :data:`CHANGE_LOG` and applied by
:func:`build_authority`; anything not named there is inherited.

v0.2 is never overwritten. ``560bc01``'s Stage-1 result stays terminal FAIL.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

PACKAGE_V02 = ROOT / ("docs/status/integration/regime_a_prime_qualification_v0_1/"
                      "prospective_development_authority_v0_2")
PACKAGE_V03 = ROOT / ("docs/status/integration/regime_a_prime_qualification_v0_1/"
                      "prospective_development_authority_v0_3")

from mineocclude.prospective.extent_geometry import (  # noqa: E402
    EXTENT_SAMPLES_PER_AXIS,
    REFERENCE_MARCH_SAMPLES,
    TARGET_EXTENT_HALF_BLOCKS,
    WallGeometry,
    derive_target_extent_half_blocks,
)

PREDECESSOR_FREEZE = "560bc01e3b01ecdc266737c015fed6677b0611c3"

CHANGE_LOG = {
    "OLD_FREEZE_SHA": PREDECESSOR_FREEZE,
    "OLD_STAGE1_RESULT": "SCIENTIFIC_FAIL",
    "OLD_STAGE1_IMMUTABLE": True,
    "OLD_STAGE1_UNITS_COMPLETE": "8/8",
    "OLD_STAGE2_AUTHORIZED": False,
    "WHY_NEW_AUTHORITY_EXISTS": (
        "The v0.2 truth predicate was point visibility outside a detector-measured "
        "transition band transferred from an independent replicate. The scored "
        "detector is an AREA predicate over the rendered silhouette, so a "
        "centre-point truth predicate and the detector necessarily disagree on rows "
        "where the silhouette straddles the occlusion edge. At 560bc01 exactly one "
        "such row -- a1q_rtl_wall_r02 frame 28, 0.006282776508991 blocks inside the "
        "transferred band -- produced a legitimate false positive and, because the "
        "frozen FIRST_N hidden-row schedule selects rows nearest the boundary, a "
        "consequent hidden_row_contamination failure. v0.3 adopts historical "
        "redesign Option A: the independent truth predicate measures the target's "
        "RENDERED EXTENT, matching the physical quantity the detector responds to. "
        "The 560bc01 failure is not repaired, reclassified, or excluded; it stands, "
        "and v0.3 is a new prospective experiment."),
    "TARGET_EXTENT_SOURCE": (
        "Closed-form bound over the full reachable animation set of the Minecraft "
        "1.16.5 SheepFurModel (obfuscated dvm) wool geometry, read from the capture "
        "client jar sha1 37fd3c903861eeff3bc24b71eed48f828b5269c8, which is "
        "byte-identical to Mojang's published 1.16.5 client."),
    "TARGET_EXTENT_HALF_WIDTH": TARGET_EXTENT_HALF_BLOCKS,
    "TARGET_EXTENT_CLOSED_FORM": "(7 + sqrt(48.5)) / 16",
    "TARGET_EXTENT_YAW_INDEPENDENT": True,
    "TARGET_EXTENT_DETECTOR_FITTED_RANGE_REJECTED": [0.6, 0.8],
    "VISIBILITY_TRUTH_CHANGE": (
        "point_visibility_only_outside_prospectively_measured_transition_band -> "
        "extent_occlusion_geometry_over_rendered_target_extent"),
    "TRANSITION_DERIVATION_FIX": (
        "Interval derivation now admits only rows with "
        "temporal_alignment_resolved == true and reads the aligned coordinate "
        "source. At v0.2 the builder derived intervals from aligned values (whose "
        "causal-FIR warm-up prefix is unavailable and therefore self-excluding) "
        "while the evaluator re-derived them from raw sample['world_x'] with no "
        "alignment filter, so warm-up rows contributed finite RAW coordinates and "
        "inflated the interval toward the lane extremes."),
    "ZERO_ERROR_GATE_RELAXED": False,
    "OUTCOME_DERIVED_GUARD_BAND_ADDED": False,
    "OLD_FAILED_ROW_EXCLUDED": False,
    "OLD_UNITS_REUSED": False,
    "STAGE2_LOCKED": True,
    "STAGE2_AUTHORIZED": False,
}


def _retarget(value, old: str, new: str):
    """Rewrite v0.2 identifiers to v0.3 through the whole tree."""
    if isinstance(value, dict):
        return {key: _retarget(item, old, new) for key, item in value.items()}
    if isinstance(value, list):
        return [_retarget(item, old, new) for item in value]
    if isinstance(value, str):
        return value.replace(old, new)
    return value


def build_authority() -> dict:
    authority = json.loads((PACKAGE_V02 / "authority_parameters.json").read_text())

    # Preserve values that must NOT be swept by the version retarget.
    forensic_base = authority["immutable_software_forensic_base_sha"]

    authority = _retarget(authority, "v0_2", "v0_3")
    authority = _retarget(authority, "v0-2", "v0-3")
    authority = _retarget(authority, "v0.2", "v0.3")
    authority["immutable_software_forensic_base_sha"] = forensic_base

    authority["status"] = "DRAFT_PROSPECTIVE_UNFROZEN_NOT_AUTHORIZED"
    authority["classification"] = "DEVELOPMENT_ONLY"

    # ---- provenance of this authority relative to its predecessor -----------
    authority["predecessor_authority"] = {
        "artifact_id": "regime-a-prime-prospective-development-authority-v0.2",
        "freeze_sha": PREDECESSOR_FREEZE,
        "stage1_result": "SCIENTIFIC_FAIL",
        "stage1_result_immutable": True,
        "stage1_result_may_be_reclassified": False,
        "stage2_authorized": False,
        "note": (
            "The predecessor Stage-1 is complete historical scientific evidence: "
            "8/8 units, 0 operational retries, terminal FAIL on "
            "stable_visibility_base_rate_robust and hidden_row_contamination. "
            "Nothing in v0.3 may rewrite that decision or authorize Stage-2 from it."),
    }
    authority["scientific_claim_boundary"] = {
        "purpose": "qualify the measurement apparatus before any downstream model experiment",
        "experiment_class": "DEVELOPMENT_APPARATUS_QUALIFICATION",
        "tests_model_activations": False,
        "tests_hidden_state_representation": False,
        "tests_object_permanence": False,
        "tests_belief": False,
        "tests_uncertainty": False,
        "tests_causal_use": False,
        "note": (
            "A v0.3 PASS qualifies the apparatus for the next authority-permitted "
            "development stage and establishes nothing about representation, "
            "permanence, belief, uncertainty, or causal use."),
    }
    authority["change_log"] = dict(CHANGE_LOG)

    # ---- apparatus: publish the occluder the engine binds to ---------------
    wall = WallGeometry.from_layout(
        wall_axis="X", wall_seg_min=-2.5, wall_seg_max=2.5,
        wall_ortho_const=6.0, wall_ortho_offset=-4.0, lane_y=4.0)
    authority["apparatus"]["wall_geometry_as_built"] = {
        "derivation": (
            "ArenaBuilder places whole blocks and a block at coordinate n occupies "
            "[n, n+1), so the realised occluder is wider and thicker than the raw "
            "layout spec. EpisodeManager therefore floors/ceils the spec at the "
            "call site, and these are those same expressions evaluated on "
            "layout_01. Binding them here stops the Python engine from carrying a "
            "second, privately hardcoded wall."),
        "layout_id": "layout_01",
        "wall_axis": wall.wall_axis,
        "wall_ortho": wall.wall_ortho,
        "wall_axis_min": wall.wall_axis_min,
        "wall_axis_max": wall.wall_axis_max,
        "wall_y_min": wall.wall_y_min,
        "wall_y_max": wall.wall_y_max,
        "ortho_half_thickness": wall.half,
        "wall_height_blocks": WallGeometry.WALL_HEIGHT,
        "spec_wall_seg_min": -2.5,
        "spec_wall_seg_max": 2.5,
        "spec_wall_ortho_const": 6.0,
        "spec_wall_ortho_offset": -4.0,
    }
    authority["apparatus"]["target_centre_world_y"] = 4.5
    authority["apparatus"]["target_centre_world_y_derivation"] = (
        "cfg.laneY + 0.5, the target centre height EpisodeManager itself tests.")
    authority["apparatus"]["reference_geometry_primitive"] = {
        "definition": "GeometryUtil.segmentHitsWall",
        "march_samples": REFERENCE_MARCH_SAMPLES,
        "interior_samples": REFERENCE_MARCH_SAMPLES - 1,
        "note": (
            "A discrete march, not an analytic slab intersection. The Python engine "
            "replicates it exactly -- including the sample count and the inclusive "
            "face tests -- because the mod is the trusted reference and is "
            "deliberately unmodified in v0.3, so every pinned apparatus artefact "
            "keeps its hash."),
    }

    # ---- the new visibility truth predicate --------------------------------
    visibility = authority["stage1_policy"]["visibility"]
    # The v0.2 detector-fitted silhouette range is removed outright rather than
    # retained as a reference: it was back-solved from the detector transition
    # and must not be reachable from a prospective authority.
    visibility.pop("silhouette_half_extent_blocks", None)
    visibility.pop("transition_guard_blocks", None)
    visibility["primary_predicate"] = "extent_occlusion_geometry_over_rendered_target_extent"
    visibility["primary_predicate_derivation"] = (
        "Historical redesign Option A. The scored detector responds to rendered "
        "AREA, so the independent geometric truth predicate is an area predicate "
        "over the target's rendered extent rather than a centre ray. Rows are "
        "classified directly from camera geometry, wall geometry, target centre "
        "and declared target extent -- never from the detector, a detector edge, "
        "or a band transferred from another replicate.")
    visibility["target_extent"] = {
        "half_width_blocks": TARGET_EXTENT_HALF_BLOCKS,
        "closed_form": "(7 + sqrt(48.5)) / 16",
        "classification": "PROSPECTIVE_RENDERER_MODEL_DERIVED",
        "yaw_independent": True,
        "applied_to_axes": ["world_x", "world_z"],
        "source_artifact": "TARGET_EXTENT_DERIVATION.md",
        "source_jar_sha1": "37fd3c903861eeff3bc24b71eed48f828b5269c8",
        "source_model_class": "net.minecraft.client.model.SheepFurModel (obfuscated dvm)",
        "detector_derived": False,
        "outcome_derived": False,
        "fitted": False,
        "bound_direction": "UPPER_BOUND_OVER_ALL_REACHABLE_ANIMATION_STATES",
        "rejected_alternative": {
            "value_range": [0.6, 0.8],
            "reason": (
                "back-solved from the observed detector transition; adopting it "
                "would make the truth predicate a function of the detector it "
                "scores. Used only as an after-the-fact corroboration check."),
        },
    }
    visibility["extent_classification"] = {
        "classes": ["EXTENT_FULLY_VISIBLE", "EXTENT_PARTIAL", "EXTENT_FULLY_OCCLUDED"],
        "regime_mapping": {
            "EXTENT_FULLY_VISIBLE": "stable_visible",
            "EXTENT_FULLY_OCCLUDED": "stable_occluded",
            "EXTENT_PARTIAL": "partial_transition",
        },
        "samples_per_axis": EXTENT_SAMPLES_PER_AXIS,
        "fully_occluded_semantics": (
            "every point of the declared extent is geometrically occluded. Decided "
            "exactly by the extent box corners: beyond the occluder the occluded "
            "set is the cone from the camera through the convex wall box, which is "
            "convex, so it contains the box iff it contains every corner. The "
            "sample lattice is closed on both faces of each axis and therefore "
            "always contains the corners."),
        "fully_visible_semantics": "no sampled point of the declared extent is occluded",
        "partial_semantics": "any mixture; reported and never scored",
        "scored_classes": ["stable_visible", "stable_occluded"],
        "unscored_classes": ["partial_transition"],
        "detector_may_influence_classification": False,
        "samples_per_axis_derivation": (
            "PURE_IMPLEMENTATION_CONSTANT. Corners alone are exact for "
            "FULLY_OCCLUDED; interior samples only make FULLY_VISIBLE "
            "conservative. Classification is invariant across 3, 5, 9 and 17 "
            "samples per axis on the frozen trajectory schedule, so this is not a "
            "tuned threshold."),
    }
    visibility["transition_policy"] = (
        "Transition intervals are derived GEOMETRICALLY from the extent predicate "
        "on the predeclared WALL TRANSITION_MEASUREMENT replicates. They calibrate "
        "and report the rendered detector's response across the geometric "
        "transition; they never define held-out truth. Every held-out row is "
        "classified directly from its own geometry, so no detector edge and no "
        "band transferred from another replicate enters the truth predicate.")
    visibility["transition_band_transferred_to_held_out"] = False
    visibility["held_out_rows_classified_directly_from_geometry"] = True
    visibility["legacy_point_visible_role"] = (
        "DIAGNOSTIC_AND_REFERENCE_CROSS_CHECK_ONLY. point_visible retains its v0.2 "
        "meaning and is neither redefined nor scored; it is the primitive the "
        "Python engine is validated against.")
    visibility["detector_truth_predicate_derivation"] = (
        "Ground truth for detector scoring is the detector-independent extent "
        "occlusion class computed from camera geometry, as-built wall geometry, "
        "target centre and the renderer-derived target extent. The scored detector "
        "may never participate in deriving it.")

    # ---- the transition/alignment derivation fix ---------------------------
    alignment = authority["stage1_policy"]["temporal_alignment"]
    alignment["aligned_position_required_for_interval_derivation"] = True
    alignment["raw_world_x_may_substitute_for_aligned_position"] = False
    alignment["interval_derivation_admissibility_rule"] = (
        "A row may contribute to any interval or transition derivation that "
        "requires aligned physical position ONLY IF "
        "temporal_alignment_resolved == true. A finite raw world_x is NOT a "
        "substitute for a resolved aligned coordinate: during the causal-FIR "
        "warm-up prefix the raw coordinate exists and the aligned one does not, "
        "and admitting it inflates derived intervals toward the lane extremes. "
        "Builder and evaluator must read the same single aligned-position field "
        "through the same admissibility filter.")
    alignment["aligned_position_field"] = "world_x"
    alignment["aligned_position_field_derivation"] = (
        "Rows emit exactly one aligned physical coordinate. It is admissible only "
        "under the rule above; there is deliberately no second raw field for a "
        "consumer to reach for instead.")

    authority["stage1_policy"]["contamination"]["designated_hidden_row_selection_rule_conservatism"] = (
        "RETAINED DELIBERATELY. FIRST_N selects the qualified stable-occluded rows "
        "nearest the occlusion boundary, which is the hardest available stress "
        "test. It is not moved away from the boundary because the predecessor's "
        "first row failed there -- that would weaken the test in response to an "
        "outcome. Under extent geometry a FIRST_N row is fully occluded over the "
        "whole rendered extent, not merely at its centre.")

    authority["artifact_id"] = "regime-a-prime-prospective-development-authority-v0.3"
    return authority


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def main() -> None:
    if derive_target_extent_half_blocks() != TARGET_EXTENT_HALF_BLOCKS:
        raise RuntimeError("target extent is not reproducible from model constants")
    authority = build_authority()
    path = PACKAGE_V03 / "authority_parameters.json"
    write(path, authority)
    print(f"authority_parameters.json sha256 = {hashlib.sha256(path.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
