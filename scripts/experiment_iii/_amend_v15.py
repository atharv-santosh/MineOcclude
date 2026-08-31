"""Apply Authority Amendment 2 (v1.5) to the machine-readable authority artifacts.

One-shot, idempotent-checked amendment writer. It edits only the fields the
amendment touches and leaves all unrelated authority prose alone.

Amendment 2 makes two changes, both prospective (no cohort, no capture, no
inference, no outcome exists):

  2a  candidate index bound per direction: 200 -> 2000
  2b  gate 12 scope clarified: the per-candidate gates (1-8, 10, 11) at every
      binding q; gate 9 is peer-dependent and is evaluated once on the
      production cohort at the III-A q. Gate 9's 0.10 threshold is unchanged.
"""

from __future__ import annotations

import io
import json
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "docs" / "experiment_iii" / "final_authorities"

OLD_BOUND = 200
NEW_BOUND = 2000

GATE_12_SCOPE = (
    "Gate 12 evaluates the PER-CANDIDATE gates - gates 1-8, 10 and 11 - at every "
    "binding q, each on that (identity,q) cell's own regenerated path. Gate 9 "
    "(between-identity diversity) is peer-dependent, has no well-defined "
    "per-candidate rate, and is evaluated ONCE on the production cohort at the "
    "III-A q = 0.05. Gate 9's threshold remains exactly 0.10 blocks and remains "
    "binding in full on the admitted cohort. This is the scope authority section "
    "18.4 already used: its 100.0% rate at q = 0.0125 and its identification of "
    "gate 3 as the dominant high-q rejection are only definable with gate 9 "
    "outside the per-q evaluation."
)

NEW_BOUND_RATIONALE = (
    "Raised from 200 to 2000 by Authority Amendment 2 (v1.5). The superseded 200 "
    "was justified by an expected requirement of ~14-16 candidates per direction, "
    "but that expectation was calibrated on historical A-prime between-identity "
    "label diversity, which was produced largely by the target-window phase "
    "offsets [0,3,6,9,12] that section 2.5 prospectively removes. Without those "
    "offsets every identity's target window anchors at the same counterfactual "
    "occlusion onset, between-identity label spread collapses (measured onset "
    "spread 0.266 blocks LTR / 0.345 RTL versus A-prime's 1.27 / 1.38), and gate 9 "
    "rejects far more candidates than the calibration anticipated. The 200 bound "
    "was therefore an incorrectly calibrated feasibility ceiling, not evidence "
    "that gate 9 is wrong. Measured under the amended rules the cohort completes "
    "at candidate index 460 (LTR) and 328 (RTL). The 2000 ceiling was selected "
    "prospectively, before the extended candidates were inspected, and is "
    "deliberately not set to the observed last-needed index. Exhausting it remains "
    "a genuine terminal signal, not ordinary scanning."
)


def load(name: str):
    with io.open(ROOT / name, "r", encoding="utf-8") as handle:
        return json.load(handle, object_pairs_hook=OrderedDict)


def save(name: str, payload) -> None:
    with io.open(ROOT / name, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def replace_text(name: str, pairs: list[tuple[str, str]]) -> None:
    path = ROOT / name
    text = path.read_text(encoding="utf-8")
    for old, new in pairs:
        if new in text and old not in text:
            continue
        if old not in text:
            raise SystemExit(f"{name}: expected text not found: {old[:90]!r}")
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8", newline="\n")


def main() -> int:
    # ---------------- machine authority ----------------
    authority = load("EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.json")
    authority["authority_version"] = "v1.5"
    authority["authority_amendment_2"] = OrderedDict(
        [
            ("name", "COHORT_ADMISSION_FEASIBILITY_REPAIR"),
            ("date", "2026-08-30"),
            ("predecessor_authority_version", "v1.4"),
            (
                "predecessor_authority_sha256",
                "993e5859fa53084889abbc8dda654cd9045dd871258e078cc1afb237f59b4daa",
            ),
            (
                "predecessor_authority_freeze_commit",
                "e86347b1275560f18cae79a9a3333d8af757adbe",
            ),
            ("discovery_stage", "I02"),
            ("prospective", True),
            ("cohort_materialized_before_amendment", False),
            ("capture_existed_before_amendment", False),
            ("scientific_outcomes_existed_before_amendment", False),
            ("changes", ["CANDIDATE_INDEX_BOUND_200_TO_2000", "GATE_12_SCOPE_CLARIFIED"]),
            ("selected_repair", "D"),
            (
                "rejected_alternatives",
                [
                    "OPTION_A_LOWER_GATE_9_THRESHOLD",
                    "OPTION_B_PRIME_FEASIBLE_SUBSET_SELECTION",
                    "OPTION_C_RESTORE_APRIME_PHASE_OFFSETS",
                ],
            ),
            ("gate_9_threshold_unchanged", 0.10),
            ("target_window_rule_unchanged", True),
            ("master_salt_unchanged", True),
            ("q_grid_unchanged", True),
            ("admission_order_unchanged", "STRICTLY_ASCENDING_INDEX_FIRST_QUALIFYING"),
        ]
    )
    cohort = authority["cohort"]
    assert cohort["candidate_index_bound_per_direction"] == OLD_BOUND
    cohort["candidate_index_bound_per_direction"] = NEW_BOUND
    cohort["candidate_index_bound_rationale"] = NEW_BOUND_RATIONALE
    cohort["candidate_index_bound_superseded_value"] = OLD_BOUND
    gate12 = cohort["all_q_qualification_gate"]
    gate12["scope"] = GATE_12_SCOPE
    gate12["per_q_gates"] = [1, 2, 3, 4, 5, 6, 7, 8, 10, 11]
    gate12["gate_9_is_peer_dependent_and_excluded_from_per_q_evaluation"] = True
    gate12["gate_9_evaluated_once_on_the_production_cohort_at_q"] = 0.05
    gate12["gate_9_threshold_unchanged"] = 0.10
    gate12["statement"] = (
        "A candidate is admitted to the III-A production cohort only if it "
        "independently satisfies the PER-CANDIDATE gates of section 2.4 (gates 1-8, "
        "10, 11) at EVERY frozen III-B q level, each evaluated on that (identity,q) "
        "cell's OWN path regenerated from the identity seed with the identical "
        "frozen arithmetic. Gate 9 is peer-dependent and is evaluated once on the "
        "production cohort at the III-A q = 0.05."
    )
    gate12["amended_by"] = "AUTHORITY_AMENDMENT_2_V1_5"
    # The v1.4 markdown hash is superseded; the successor hash is rebound after
    # every artifact is written, by _rebind_v15.py.
    authority["authority_markdown_sha256_superseded_v1_4"] = authority[
        "authority_markdown_sha256"
    ]
    authority["amended_by"] = "AUTHORITY_AMENDMENT_2_V1_5"
    save("EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.json", authority)

    # ---------------- blocker taxonomy ----------------
    blockers = load("BLOCKER_TAXONOMY.json")
    touched = 0
    for blocker in blockers["blockers"]:
        for field in ("detection_rule", "authority_amendment_required_if"):
            value = blocker.get(field)
            if isinstance(value, str) and "bound of 200 per direction" in value:
                blocker[field] = value.replace(
                    "bound of 200 per direction", "bound of 2000 per direction"
                )
                touched += 1
        if blocker["code"] == "COHORT_ALL_Q_QUALIFICATION_INFEASIBLE":
            blocker["detection_rule"] = blocker["detection_rule"].replace(
                "satisfy gates 1-11 at EVERY frozen q",
                "satisfy the per-candidate gates 1-8, 10 and 11 at EVERY frozen q "
                "(gate 9 being peer-dependent and evaluated once at the III-A q)",
            )
    blockers["amended_by"] = "AUTHORITY_AMENDMENT_2_V1_5"
    save("BLOCKER_TAXONOMY.json", blockers)

    # ---------------- change matrix ----------------
    matrix = load("IMPLEMENTATION_CHANGE_MATRIX.json")
    for item in matrix["items"]:
        if item["id"] in ("C02", "CB02"):
            item["required_experiment_iii_behavior"] = item[
                "required_experiment_iii_behavior"
            ].replace(
                "requires the candidate to satisfy gates 1-11 at every frozen q",
                "requires the candidate to satisfy the per-candidate gates 1-8, 10 "
                "and 11 at every frozen q (gate 9 is peer-dependent and is evaluated "
                "once on the production cohort at the III-A q)",
            )
            item["amended_by"] = "AUTHORITY_AMENDMENT_2_V1_5"
    matrix["amended_by"] = "AUTHORITY_AMENDMENT_2_V1_5"
    save("IMPLEMENTATION_CHANGE_MATRIX.json", matrix)

    # ---------------- prose artifacts ----------------
    replace_text(
        "EXPERIMENT_III_TEST_PLAN.md",
        [
            (
                "Assert the candidate scan honours the frozen index bound of 200 per",
                "Assert the candidate scan honours the frozen index bound of 2000 per",
            )
        ],
    )
    replace_text(
        "RECOVERY_AND_RESUME_RUNBOOK.md",
        [
            (
                "candidate index up to the frozen bound of **200 per direction**",
                "candidate index up to the frozen bound of **2000 per direction**",
            )
        ],
    )
    replace_text(
        "AUTHORITY_VALIDATION_REPORT.md",
        [
            (
                "index bound of **200 per direction** makes the pre-existing but never-materialized bound executable,",
                "index bound of **2000 per direction** (raised from 200 by Amendment 2, v1.5) makes the pre-existing but never-materialized bound executable,",
            )
        ],
    )
    replace_text(
        "final_audit/FINAL_SCIENTIFIC_VALIDITY_REPORT.md",
        [
            (
                "with a frozen 200/direction candidate bound",
                "with a frozen 2000/direction candidate bound",
            )
        ],
    )
    replace_text(
        "final_audit/audit_final.py",
        [
            (
                'chk("candidate index bound frozen", A["cohort"]["candidate_index_bound_per_direction"] == 200)',
                'chk("candidate index bound frozen", A["cohort"]["candidate_index_bound_per_direction"] == 2000)',
            ),
            ('"200 per direction" in [b for b in B["blockers"]', '"2000 per direction" in [b for b in B["blockers"]'),
        ],
    )

    traceability = load("final_audit/FINAL_REQUIREMENT_TRACEABILITY.json")
    for row in traceability.get("requirements", traceability if isinstance(traceability, list) else []):
        if isinstance(row, dict) and row.get("requirement") == "candidate index bound 200/direction":
            row["requirement"] = "candidate index bound 2000/direction"
            row["amended_by"] = "AUTHORITY_AMENDMENT_2_V1_5"
    save("final_audit/FINAL_REQUIREMENT_TRACEABILITY.json", traceability)

    print("amendment 2 applied to the machine artifacts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
