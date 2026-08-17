#!/usr/bin/env python3
"""Materialize the Regime A' v0.4 prospective development authority.

v0.4 exists for one reason: the v0.3 Stage-1 terminated in a scientific FAIL at
freeze ``134a242``, and a completed terminal decision closes its package's unit
inventory permanently. Those eight ``a1x_*`` / 83xxx units are historical
evidence and are never recollected, so a new prospective run needs a new
inventory -- and in this repository the package version *is* the unit of
inventory identity. Every identifier a runner resolves (authority, both
manifests, the authorization receipt, the pre-outcome provenance receipt, the
Stage-1 decision, the run namespace, the durable prefix) is templated off the
version tag in ``package_binding``, so advancing the tag advances all of them
together and coherently.

**The scientific delta is empty.** Unlike v0.2 -> v0.3, which replaced the truth
predicate, v0.4 changes no scientific parameter whatsoever. The apparatus, the
extent geometry, the zero-error gate, the sample floor, the FIRST_N hidden-row
rule, the temporal-alignment estimators and the 1.0-tick refinement bound are
inherited byte-for-byte from the frozen v0.3 authority. :func:`scientific_delta`
is deliberately empty and :func:`require_scientific_fields_unchanged` proves it,
so this build cannot become a place where a rule quietly moves.

What v0.4 *does* carry is the repaired software: the Stage-1 evidence builder now
resolves row classification, the transition schema and the designated-row
schedule through the authority-selected semantics rather than a hand-copied v0.2
twin. That was a source defect, not an authority defect, which is exactly why
the authority's science is untouched here.

The open scientific question v0.4 exists to answer is unchanged and unweakened:
does the frozen temporal-alignment qualification pass prospectively, including
the RIGHT_TO_LEFT WALL trajectory class that legitimately failed at 134a242?

v0.3 is never overwritten. ``134a242``'s Stage-1 result stays terminal FAIL.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

PACKAGE_V03 = ROOT / ("docs/status/integration/regime_a_prime_qualification_v0_1/"
                      "prospective_development_authority_v0_3")
PACKAGE_V04 = ROOT / ("docs/status/integration/regime_a_prime_qualification_v0_1/"
                      "prospective_development_authority_v0_4")

from mineocclude.prospective.extent_geometry import (  # noqa: E402
    TARGET_EXTENT_HALF_BLOCKS,
    derive_target_extent_half_blocks,
)
from scripts.regime_a_prime_qualification_v0_3.build_authority import (  # noqa: E402
    SHARED_IMPLEMENTATION_PRODUCER_FIELDS,
    _retarget,
    require_producers_exist,
    write,
)

PREDECESSOR_FREEZE = "134a242981e3131c9c61d46b0f112234c8e83fce"

#: Authority subtrees that carry scientific content. Every one of them must
#: survive the version sweep bit-identical; see
#: :func:`require_scientific_fields_unchanged`.
SCIENTIFIC_SUBTREES = (
    ("apparatus",),
    ("apparatus_observation_policy",),
    ("clock_domains",),
    ("fixed_development_configuration",),
    ("stage1_policy",),
    ("stage2_policy",),
)

CHANGE_LOG = {
    "OLD_FREEZE_SHA": PREDECESSOR_FREEZE,
    "OLD_STAGE1_RESULT": "SCIENTIFIC_FAIL",
    "OLD_STAGE1_IMMUTABLE": True,
    "OLD_STAGE1_UNITS_COMPLETE": "8/8",
    "OLD_STAGE1_OPERATIONAL_RETRIES": 0,
    "OLD_STAGE1_EVIDENCE_SHA256":
        "e87b8382e27aa2bcafca3a9be511268736a43091341a8c1b08d6d725ba94239a",
    "OLD_STAGE2_AUTHORIZED": False,
    "WHY_NEW_AUTHORITY_EXISTS": (
        "NOT a scientific redesign. The v0.3 Stage-1 terminated in a scientific "
        "FAIL, which permanently closes its a1x_* / 83xxx unit inventory: those "
        "units are historical evidence and may never be recollected. A new "
        "prospective run therefore requires a new inventory, and package version "
        "is this repository's unit of inventory identity -- every artifact id, "
        "namespace and durable prefix a runner resolves is templated off the "
        "version tag. v0.4 advances the tag and nothing else. Its scientific "
        "delta against v0.3 is empty and is proved empty at build time."),
    "SCIENTIFIC_DELTA": "EMPTY",
    "AUTHORITY_SCIENTIFIC_FIELDS_CHANGED": False,
    "AUTHORITY_BINDING_FIELDS_CHANGED": True,
    "AUTHORITY_BINDING_FIELDS_CHANGED_DERIVATION": (
        "artifact_id, predecessor_authority, change_log, and the identity strings "
        "swept by the version retarget: stage_binding_policy artifact ids, "
        "manifest relative paths and run namespaces. These are cryptographic and "
        "naming bindings, not scientific parameters."),
    "WHY_THE_V0_3_STAGE1_FAILED": (
        "Two independent roots. (1) A stale Stage-1 evidence builder: it remained "
        "on v0.2 point/band semantics while the authority and evaluator had moved "
        "to v0.3 rendered-extent semantics, producing 166 builder/evaluator regime "
        "mismatches, a v0.2 transition schema the v0.3 evaluator could not read, "
        "and a FIRST_N hidden-row schedule selected over the stale pool. That is a "
        "SOURCE defect and is repaired in the freeze that accompanies this "
        "authority. (2) One genuinely anomalous temporal-alignment trajectory, "
        "a1x_rtl_wall_r01, whose trimodal causal kernel put its cross-correlation "
        "lag 1.8213 ticks from its kernel mode against a 1.0-tick bound. That is a "
        "RESULT, not a defect. It is not repaired, excluded, or accommodated."),
    "VISIBILITY_TRUTH_CHANGE": "NONE",
    "TARGET_EXTENT_CHANGED": False,
    "TARGET_EXTENT_HALF_WIDTH": TARGET_EXTENT_HALF_BLOCKS,
    "ZERO_ERROR_GATE_RELAXED": False,
    "SAMPLE_FLOOR_CHANGED": False,
    "HIDDEN_FIRST_N_RULE_CHANGED": False,
    "TEMPORAL_FIR_RULE_CHANGED": False,
    "TEMPORAL_REFINEMENT_BOUND_CHANGED": False,
    "ALIGNMENT_ESTIMANDS_CHANGED": False,
    "TRAJECTORY_STRUCTURE_CHANGED": False,
    "SPEED_CHANGED": False,
    "OUTCOME_DERIVED_GUARD_BAND_ADDED": False,
    "OUTCOME_DERIVED_TEMPORAL_EXCEPTION_ADDED": False,
    "UNIMODALITY_GATE_ADDED": False,
    "OLD_FAILED_ROW_EXCLUDED": False,
    "OLD_FAILED_TRAJECTORY_EXCLUDED": False,
    "OLD_UNITS_REUSED": False,
    "STAGE2_LOCKED": True,
    "STAGE2_AUTHORIZED": False,
    "OPEN_SCIENTIFIC_QUESTION": (
        "Does the frozen temporal-alignment qualification pass prospectively, "
        "including the RIGHT_TO_LEFT WALL trajectory class? The rule is unchanged, "
        "so the next campaign answers this on the same terms the last one failed."),
}


def scientific_delta() -> dict:
    """The scientific changes v0.4 makes to v0.3. Deliberately empty.

    Kept as a function rather than an absent concept so that any future edit
    that wants to change science through this build has to put it here, in the
    open, where :func:`require_scientific_fields_unchanged` will fail on it.
    """
    return {}


def require_scientific_fields_unchanged(v0_3: dict, v0_4: dict) -> None:
    """Refuse unless every scientific subtree survived bit-identical.

    The version sweep rewrites strings anywhere in the tree, so a scientific
    field whose value merely *contained* a version token would be silently
    rewritten. Comparing the canonical JSON of each scientific subtree before and
    after is what makes ``AUTHORITY_SCIENTIFIC_FIELDS_CHANGED=false`` a proof
    rather than a claim.
    """
    for subtree in SCIENTIFIC_SUBTREES:
        before, after = v0_3, v0_4
        for key in subtree:
            before, after = before[key], after[key]
        if json.dumps(before, sort_keys=True) != json.dumps(after, sort_keys=True):
            raise RuntimeError(
                f"v0.4 changed a scientific subtree it must inherit: {'.'.join(subtree)}")


def build_authority() -> tuple[dict, dict]:
    source = json.loads((PACKAGE_V03 / "authority_parameters.json").read_text())
    authority = json.loads(json.dumps(source))

    # Preserve values the version retarget must not touch. The producer fields
    # name Python implementations that really execute, not versioned artifact
    # identities; sweeping them would point the runtime probe allow-list and the
    # evidence-builder forbid-list at modules that have never existed. The
    # forensic base SHA is a historical commit, not a package identity.
    forensic_base = authority["immutable_software_forensic_base_sha"]
    shared_producers = {
        field: list(authority["runtime_identity_policy"]["probe_evidence_policy"][field])
        for field in SHARED_IMPLEMENTATION_PRODUCER_FIELDS}

    authority = _retarget(authority, "v0_3", "v0_4")
    authority = _retarget(authority, "v0-3", "v0-4")
    authority = _retarget(authority, "v0.3", "v0.4")
    authority["immutable_software_forensic_base_sha"] = forensic_base
    authority["runtime_identity_policy"]["probe_evidence_policy"].update(shared_producers)

    authority["status"] = "DRAFT_PROSPECTIVE_UNFROZEN_NOT_AUTHORIZED"
    authority["classification"] = "DEVELOPMENT_ONLY"

    # The scientific subtrees are restored from the v0.3 source outright. The
    # sweep is a naming operation and has no business inside them; restoring
    # rather than trusting it to have missed them is what the equality check
    # below then verifies.
    for subtree in SCIENTIFIC_SUBTREES:
        target, origin = authority, source
        for key in subtree[:-1]:
            target, origin = target[key], origin[key]
        target[subtree[-1]] = json.loads(json.dumps(origin[subtree[-1]]))

    authority.update(scientific_delta())

    authority["predecessor_authority"] = {
        "artifact_id": "regime-a-prime-prospective-development-authority-v0.3",
        "freeze_sha": PREDECESSOR_FREEZE,
        "stage1_result": "SCIENTIFIC_FAIL",
        "stage1_result_immutable": True,
        "stage1_result_may_be_reclassified": False,
        "stage2_authorized": False,
        "stage1_evidence_sha256":
            "e87b8382e27aa2bcafca3a9be511268736a43091341a8c1b08d6d725ba94239a",
        "failed_gates": [
            "prospective_transition_measurement",
            "calibration_world_and_wall_relative_support",
            "hidden_row_contamination",
            "unit_identity_runtime_path_durability",
            "render_server_temporal_alignment",
        ],
        "note": (
            "The predecessor Stage-1 is complete historical scientific evidence: "
            "8/8 units, 0 operational retries, terminal FAIL. Four of its five "
            "failed gates trace to a stale evidence builder and are repaired in "
            "source; the fifth, render_server_temporal_alignment, is a real "
            "measurement on trajectory a1x_rtl_wall_r01 and is neither repaired "
            "nor excluded. Nothing in v0.4 may rewrite that decision or authorize "
            "Stage-2 from it."),
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
            "A v0.4 PASS qualifies the apparatus for the next authority-permitted "
            "development stage and establishes nothing about representation, "
            "permanence, belief, uncertainty, or causal use."),
    }
    authority["change_log"] = dict(CHANGE_LOG)
    authority["artifact_id"] = "regime-a-prime-prospective-development-authority-v0.4"
    return source, authority


def main() -> None:
    if derive_target_extent_half_blocks() != TARGET_EXTENT_HALF_BLOCKS:
        raise RuntimeError("target extent is not reproducible from model constants")
    source, authority = build_authority()
    require_scientific_fields_unchanged(source, authority)
    require_producers_exist(authority)
    path = PACKAGE_V04 / "authority_parameters.json"
    write(path, authority)
    print("AUTHORITY_SCIENTIFIC_FIELDS_CHANGED=false")
    print(f"authority_parameters.json sha256 = {hashlib.sha256(path.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
