"""Apply Authority Amendment 4 (v1.7) -- the capture-liveness successor rule.

One-shot amendment writer. Every edit is an exact-string replacement asserted
before it is applied, so a drifted predecessor fails loudly rather than silently
producing a half-amended authority.

Amendment 4 is prospective in the strongest available sense: it is raised at A4
entry with zero P0 frames in existence. It resolves an ambiguity that Amendment 3
left in §7.10f and that only a live apparatus could expose.

**The ambiguity.** 7.10f required the framebuffer to demonstrate a transition "at
every point where the image *must* change", and listed the target present/absent
transitions among those points. It also stated -- as the reason the v1.5
byte-duplicate rule was withdrawn -- that an opaque condition "can legitimately
render pixel-identical frames while a fully hidden target moves". Those two
statements are in tension for any condition that occludes the target, and 7.10f
never said which transition then discharges the mandatory pre-capture probe.

**Why it mattered.** §7.2 freezes the nine placements at world-x -2.0 .. +2.0 and
the as-built wall spans x in [-3, 4], so the camera-to-target ray crosses the wall
slab at EVERY placement. An opaque wall therefore occludes the target everywhere
in P0, its present/absent settled frames are byte-identical by construction, and
the implementation -- which demanded the change unconditionally -- refused 18 of
the 252 P0 units on physically correct observations.

**The resolution.** Renderer liveness is established independently of the
scientific visibility condition being measured. A fixed ENGINEERING_ONLY witness,
whose visual change is guaranteed regardless of wall material, runs before each
scientific capture unit. Scientific present/absent transitions keep recording
their hashes as diagnostics, and their equality is no longer, by itself,
CAPTURE_STALE_FRAME. The rule is uniform: no material-specific exemption, no L4
special case, and no inference from opacity, RVE, ladder or model behaviour.

Nothing scientific moves: placements, roster, RVE, ladder thresholds, selection,
target geometry, capture contents, cohort and downstream analysis are unchanged.
"""

from __future__ import annotations

import io
import json
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "docs" / "experiment_iii" / "final_authorities"
MD = ROOT / "EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.md"
JS = ROOT / "EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.json"

PRED_AUTHORITY_SHA256 = "62519701bbe08f94839b6dab4e612826f902f31c736727e8c268cf738897ab4c"
PRED_MACHINE_SHA256 = "d9de26163df4ca599a5049fb75fd68d010169e53f90aceeb9e4063e60da50609"
PRED_FREEZE_COMMIT = "a1f5dd1a959ff477edbf469cd12bb4db606371ea"

# --------------------------------------------------------------------------
# The markdown clause this amendment replaces
# --------------------------------------------------------------------------

OLD_PROBES = """**Transition probes.** At every point where the image *must* change, the framebuffer is required
to demonstrate the transition after settling:

- target present → absent, and absent → present;
- a wall material change;
- a mandatory controlled pre-capture liveness probe on every unit.

```
CAPTURE_STALE_FRAME  iff  the server tick advanced across a known scene transition
                          AND the settled framebuffer is byte-identical across it
```

Within one genuinely static settled state, repeated framebuffer bytes are **not** evidence of
staleness and must not invalidate the block. A tick that fails to advance, or a duplicated or
missing tick identity, is `TIMING_CARDINALITY_MISMATCH`.
"""

NEW_PROBES = """**Successor rule (Authority Amendment 4, v1.7).** Renderer liveness MUST be established
independently of the scientific visibility condition being measured. A scientific P0 condition
MUST NOT be required to demonstrate framebuffer inequality merely because the target changes
`PRESENT`/`ABSENT` state, because a correctly rendered condition may physically occlude the
target so that `TARGET_PRESENT` and `TARGET_ABSENT` produce pixel-identical settled
framebuffers. Framebuffer equality in such a condition is not, by itself, evidence of a stale
renderer.

**Mandatory pre-capture liveness witness.** Before each authority-required scientific capture
unit, execute a fixed **`ENGINEERING_ONLY`** liveness witness whose visual change is guaranteed
independently of candidate wall material and of P0 visibility. The witness uses one
prospectively frozen configuration common to every P0 unit:

| | |
|---|---|
| Scene | `NO_WALL` |
| Target | fixed authority-bound visible calibration position |
| Transition | `TARGET_PRESENT` → `TARGET_ABSENT` → `TARGET_PRESENT` |

The witness must establish: tick evidence advances correctly; the requested transition is
acknowledged; the settled framebuffer changes across transitions whose visual effect is
independently guaranteed; `client_tick.jsonl` validates; `capture_complete.json` validates;
`drained = true`; `writer_errors = 0`; and the actual framebuffer dimensions validate. Failure
of the witness emits `CAPTURE_STALE_FRAME` or the corresponding frozen technical blocker.

**Scientific-unit present/absent transitions.** For the subsequent scientific P0 unit,
`TARGET_PRESENT_TO_ABSENT` and `TARGET_ABSENT_TO_PRESENT` framebuffer hashes remain recorded,
and their equality or inequality remains useful technical evidence and diagnostics. However:

```
PIXEL_INEQUALITY IS NOT A SCIENTIFIC-UNIT VALIDITY REQUIREMENT
```

unless the controlling authority independently guarantees that the particular transition must
visibly alter the framebuffer. Therefore equal settled hashes are **not**, by themselves,
`CAPTURE_STALE_FRAME`. This applies **uniformly to all scientific conditions**: there is no
material-specific exemption, no special case for `L4`, and no inference from material identity,
expected opacity, candidate ranking, RVE, the selected ladder or model behaviour when deciding
whether renderer liveness has been satisfied.

**Separation from scientific evidence.** Mandatory liveness-witness artifacts are
`ENGINEERING_ONLY` and MUST be excluded from P0 RVE computation, material validity, ladder
selection, the bootstrap, sentinel measurements, P1, P2 scientific artifact discovery,
production and every scientific statistic. The witness proves apparatus liveness only; it does
not measure scientific visibility.

```
CAPTURE_STALE_FRAME  may be emitted when the mandatory engineering liveness witness
                     fails; tick evidence fails; capture completion evidence fails;
                     framebuffer dimensions/evidence fail; or another authority-defined
                     transition whose framebuffer change is independently guaranteed
                     fails to change.

                     A scientific PRESENT/ABSENT transition with equal framebuffers
                     MUST NOT, by itself, emit CAPTURE_STALE_FRAME.
```

Within one genuinely static settled state, repeated framebuffer bytes are **not** evidence of
staleness and must not invalidate the block. A tick that fails to advance, or a duplicated or
missing tick identity, is `TIMING_CARDINALITY_MISMATCH`.
"""


def amend_markdown() -> None:
    text = MD.read_text(encoding="utf-8")
    if NEW_PROBES in text:
        raise SystemExit("AMENDMENT_4_ALREADY_APPLIED: markdown already carries the successor rule")
    if OLD_PROBES not in text:
        raise SystemExit("AMENDMENT_4_PRECONDITION_FAILED: the v1.6 7.10f probe clause is not present verbatim")
    text = text.replace(OLD_PROBES, NEW_PROBES, 1)
    header = "#### 7.10f Capture liveness contract (frozen, replacing the byte-duplicate rule)"
    new_header = "#### 7.10f Capture liveness contract (frozen; successor rule, Amendment 4 v1.7)"
    if header not in text:
        raise SystemExit("AMENDMENT_4_PRECONDITION_FAILED: 7.10f header not found")
    text = text.replace(header, new_header, 1)
    MD.write_text(text, encoding="utf-8", newline="\n")


def amend_machine() -> None:
    authority = json.loads(JS.read_text(encoding="utf-8"), object_pairs_hook=OrderedDict)
    if authority["authority_version"] != "v1.6":
        raise SystemExit(
            f"AMENDMENT_4_PRECONDITION_FAILED: authority_version is "
            f"{authority['authority_version']!r}, expected 'v1.6'"
        )

    contract = authority["capture_liveness_contract"]
    contract["schema"] = "mineocclude-experiment-iii-capture-liveness-v2"
    contract["supersedes"] = "AMENDMENT_3_UNCONDITIONAL_TARGET_TRANSITION_PROBES"
    contract["withdrawn_rule"] = (
        "a scientific target PRESENT/ABSENT transition must demonstrate framebuffer "
        "inequality on every capture unit"
    )
    contract["withdrawal_reason"] = (
        "a correctly rendered condition may physically occlude the target, so "
        "PRESENT and ABSENT produce pixel-identical settled framebuffers; requiring "
        "inequality made liveness conditional on the unknown visibility quantity P0 "
        "exists to measure, and refused physically correct observations"
    )

    #: The witness is one frozen configuration, common to every P0 unit, whose
    #: visual change does not depend on the candidate wall material.
    contract["mandatory_pre_capture_liveness_witness"] = OrderedDict(
        [
            ("required_before_every_scientific_capture_unit", True),
            ("classification", "ENGINEERING_ONLY"),
            ("scene", "NO_WALL"),
            ("target", "FIXED_AUTHORITY_BOUND_VISIBLE_CALIBRATION_POSITION"),
            (
                "transition",
                ["TARGET_PRESENT", "TARGET_ABSENT", "TARGET_PRESENT"],
            ),
            ("visual_change_guaranteed_independently_of_wall_material", True),
            ("frozen_configuration_common_to_every_p0_unit", True),
            (
                "must_establish",
                [
                    "TICK_EVIDENCE_ADVANCES_CORRECTLY",
                    "REQUESTED_TRANSITION_ACKNOWLEDGED",
                    "SETTLED_FRAMEBUFFER_CHANGES_ACROSS_GUARANTEED_TRANSITIONS",
                    "CLIENT_TICK_JSONL_VALIDATES",
                    "CAPTURE_COMPLETE_JSON_VALIDATES",
                    "DRAINED_TRUE",
                    "WRITER_ERRORS_ZERO",
                    "ACTUAL_FRAMEBUFFER_DIMENSIONS_VALIDATE",
                ],
            ),
            ("failure_blocker", "CAPTURE_STALE_FRAME"),
        ]
    )

    contract["scientific_unit_present_absent_transitions"] = OrderedDict(
        [
            ("framebuffer_hashes_recorded", True),
            ("equality_is_technical_evidence_and_diagnostics", True),
            ("pixel_inequality_is_a_scientific_unit_validity_requirement", False),
            ("equal_settled_hashes_are_capture_stale_frame", False),
            ("applies_uniformly_to_all_scientific_conditions", True),
            ("material_specific_exemption", False),
            ("special_case_for_l4", False),
            (
                "liveness_must_not_be_inferred_from",
                [
                    "MATERIAL_IDENTITY",
                    "EXPECTED_OPACITY",
                    "CANDIDATE_RANKING",
                    "RVE",
                    "SELECTED_LADDER",
                    "MODEL_BEHAVIOR",
                ],
            ),
        ]
    )

    contract["witness_artifact_separation"] = OrderedDict(
        [
            ("classification", "ENGINEERING_ONLY"),
            (
                "excluded_from",
                [
                    "P0_RVE_COMPUTATION",
                    "MATERIAL_VALIDITY",
                    "LADDER_SELECTION",
                    "BOOTSTRAP",
                    "SENTINEL_MEASUREMENTS",
                    "P1",
                    "P2_SCIENTIFIC_ARTIFACT_DISCOVERY",
                    "PRODUCTION",
                    "SCIENTIFIC_STATISTICS",
                ],
            ),
            ("proves", "APPARATUS_LIVENESS_ONLY"),
            ("measures_scientific_visibility", False),
        ]
    )

    contract["stale_rule"] = (
        "CAPTURE_STALE_FRAME iff the mandatory engineering liveness witness fails, OR "
        "tick evidence fails, OR capture completion evidence fails, OR framebuffer "
        "dimensions/evidence fail, OR an authority-defined transition whose framebuffer "
        "change is independently guaranteed fails to change. A scientific PRESENT/ABSENT "
        "transition with equal framebuffers MUST NOT, by itself, emit CAPTURE_STALE_FRAME."
    )
    contract["transition_probes_requiring_a_guaranteed_change"] = [
        "MANDATORY_PRE_CAPTURE_LIVENESS_WITNESS",
        "WALL_MATERIAL_CHANGE",
    ]
    contract["transition_probes_recorded_as_diagnostics"] = [
        "TARGET_PRESENT_TO_ABSENT",
        "TARGET_ABSENT_TO_PRESENT",
    ]

    authority["authority_version"] = "v1.7"
    authority["amended_by"] = "AUTHORITY_AMENDMENT_4"
    authority["authority_amendment_4"] = OrderedDict(
        [
            ("name", "Capture liveness successor rule"),
            ("date", "2026-08-31"),
            ("predecessor_authority_version", "v1.6"),
            ("predecessor_authority_sha256", PRED_AUTHORITY_SHA256),
            ("predecessor_machine_authority_sha256", PRED_MACHINE_SHA256),
            ("predecessor_authority_freeze_commit", PRED_FREEZE_COMMIT),
            ("discovery_stage", "A4_ENTRY_PRE_P0_ON_QUALIFIED_CAPTURE_HOST"),
            ("prospective", True),
            ("p0_frames_observed", 0),
            ("mineworld_outcomes_observed", 0),
            ("production_outcomes_observed", 0),
            ("scientific_outcomes_existed_before_amendment", False),
            ("cohort_materialized_before_amendment", True),
            ("cohort_changed_by_amendment", False),
            (
                "statement",
                "Renderer liveness must be established independently of the scientific "
                "visibility condition being measured. A scientific P0 condition must not "
                "be required to demonstrate framebuffer inequality merely because the "
                "target changes PRESENT/ABSENT state.",
            ),
            (
                "defect_resolved",
                "7.10f required the target present/absent transitions to demonstrate a "
                "framebuffer change on every unit, while also recognising that an opaque "
                "condition legitimately renders pixel-identical frames with a hidden "
                "target. The nine frozen placements all lie inside the as-built wall "
                "extent, so an opaque wall occludes the target at every placement and 18 "
                "of the 252 P0 units refused on physically correct observations.",
            ),
            (
                "changes",
                [
                    "4a a fixed ENGINEERING_ONLY pre-capture liveness witness (NO_WALL, "
                    "fixed visible calibration position, PRESENT->ABSENT->PRESENT) is "
                    "required before each scientific capture unit",
                    "4b scientific PRESENT/ABSENT framebuffer equality is diagnostic only "
                    "and is never, by itself, CAPTURE_STALE_FRAME",
                    "4c the rule is uniform across conditions: no material-specific "
                    "exemption, no L4 special case, no inference from opacity, RVE, "
                    "ladder or model behaviour",
                    "4d witness artifacts are ENGINEERING_ONLY and excluded from every "
                    "scientific consumer",
                ],
            ),
            (
                "unchanged",
                [
                    "P0 placements",
                    "the material roster and the frozen exclusions",
                    "RVE and its aggregation and normalization",
                    "the ladder zones, separations, SNR and CV bounds",
                    "the deterministic selection rule and tie-break",
                    "target geometry and scientific capture contents",
                    "the cohort, folds, target rows, FIR kernels and q grid",
                    "downstream model analysis and every statistic",
                ],
            ),
            ("iii_a_scientific_design_changed", False),
            ("iii_b_scientific_design_changed", False),
            ("scientific_invalidation", "NONE_NO_MEASUREMENT_EXISTED"),
        ]
    )

    with io.open(JS, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(authority, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def main() -> int:
    amend_markdown()
    amend_machine()
    print("AMENDMENT_4_APPLIED=true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
