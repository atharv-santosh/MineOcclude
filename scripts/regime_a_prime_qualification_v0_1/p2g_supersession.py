"""STEP 2/3: prospective P2 authority supersession (pre-outcome).

Narrows what P2 is allowed to claim, BEFORE any P2 neural outcome exists. The
original pre-outcome authority at commit 6943e04 is NOT modified or erased, and
the failed historical renderer-equivalence audit is preserved permanently.

Why this is legitimate: no P2 no-wall scientific trajectory has been captured,
no P2 activation exists, and no BEST-K or FULL outcome has been observed. The
supersession is therefore prospective, not outcome-aware.
"""

from __future__ import annotations

import json
from typing import Any

from p2_common import OUT, run_git, sha256_file, write_json

ORIGINAL_PREOUTCOME_COMMIT = "6943e04c114ad8be43b28be5342f7a6c0a49523f"
BLOCKER_COMMIT = "af8ab21087a1b4d08514721d19762ca2a00d4ed5"

FROZEN_PREOUTCOME = {
    "p2_preoutcome_authority.json":
        "ad9804ed7b8ae9770d0192dc8f9e863fc85c96429031600e251470ebdbaa03f7",
    "p2_source_spec_binding.json":
        "af8d243fceece6cc1736e3cd7ab1c1f27af70b3f4341b1be62e1aa267e387e17",
    "p2_target_row_manifest.json":
        "691dad6fe4ceb992e084098e4699892e25775183c28238168cede4b5f9d4b2ef",
    "p2_path_equivalence_authority.json":
        "4f3e68e46c22b73f27406dcc65efa3d81ef68f3e06177a9802d38b208b4d188d",
}


def main() -> int:
    render = json.loads((OUT / "p2_render_equivalence_receipt.json").read_text())
    capture = json.loads((OUT / "p2_capture_manifest.json").read_text())

    # Pre-outcome preconditions: nothing scientific may exist yet.
    if capture["no_wall_run_count"] != 0 or capture["complete_validated_durable_count"] != 0:
        raise RuntimeError("supersession refused: P2 captures already exist")
    for name in ("p2_best_k_results.json", "p2_full_results.json",
                 "p2_activation_manifest.json", "p2_visible_comparison.json"):
        if (OUT / name).exists():
            raise RuntimeError(f"supersession refused: P2 outcome artifact exists: {name}")
    unchanged = {n: sha256_file(OUT / n) == h for n, h in FROZEN_PREOUTCOME.items()}
    if not all(unchanged.values()):
        raise RuntimeError(f"original P2 authority was modified: {unchanged}")

    payload = {
        "artifact_id": "regime-a-prime-p2-authority-supersession-v0.1",
        "schema_version": "1.0",
        "phase": "P2",
        "classification": "EXPLORATORY_MATCHED_DIAGNOSTIC",
        "status": "FROZEN_PRE_OUTCOME",
        "supersession_type": "NARROWING_OF_INTERPRETATION_ONLY",
        "ORIGINAL_P2_PREOUTCOME_COMMIT": ORIGINAL_PREOUTCOME_COMMIT,
        "original_authority_modified": False,
        "original_authority_hashes_verified": unchanged,
        "blocker_evidence_commit": BLOCKER_COMMIT,
        "blocker_evidence_preserved": True,

        "HISTORICAL_RENDER_EQUIVALENCE": "FAIL",
        "ORIGINAL_RENDERER_IDENTITY": "UNRECOVERABLE_FROM_FROZEN_AUTHORITY",
        "historical_render_evidence": {
            "artifact": "p2_render_equivalence_receipt.json",
            "frames_tested": render["historical_pixel_frame_count"],
            "frames_pixel_identical": render["frames_decoded_pixel_identical"],
            "detector_area_changed": render["detector_area_changed_count"],
            "detector_status_flips": render["detector_status_changed_count"],
            "frozen_target_row_flips": render["frozen_target_frame_detector_flips"],
        },
        "reason":
            "The NVMe-resident bundled renderer/operator-tools were lost and renderer "
            "identity was never recorded in the historical capture authority, so the "
            "apparatus that produced the historical Regime A pixels cannot be "
            "reconstructed or verified.",

        "prohibited_interpretation":
            "new P2 no-wall differs from historical Regime A wall only by wall removal "
            "at the pixel/apparatus level",
        "prohibited_claim":
            "P2 proves a clean wall-vs-no-wall causal effect against historical Regime A",
        "historical_comparison_label": "DESCRIPTIVE_CROSS_APPARATUS_CONTEXT_ONLY",

        "P2_PRIMARY_ROLE":
            "CURRENT_APPARATUS_VISIBLE_READOUT_QUALIFICATION_AT_MATCHED_PHYSICAL_PATHS",
        "controlling_question":
            "Can the frozen layer-4 BEST-K/FULL readout recover sheep position when the "
            "sheep is visibly available on the CURRENT qualified apparatus, at the same "
            "frozen physical trajectories and target times as the original 25 Regime A "
            "specifications?",
        "no_new_wall_scientific_cohort_required": True,
        "historical_wall_captures_role": "IMMUTABLE_HISTORICAL_CONTEXT",

        "matched_quantities_unchanged": [
            "original specification mapping", "seed", "direction", "motion schedule",
            "noise authority", "initial state", "camera", "FOV", "target tick IDs",
            "target timestamps", "capture cadence", "frame/action semantics",
            "fold assignment", "target coordinates", "MineWorld checkpoint",
            "preprocessing", "layer 4", "BEST-K procedure", "FULL procedure",
        ],
        "path_requirement": {
            "epsilon_path": 0.0,
            "rule": "EXACT_EQUALITY_REQUIRED",
            "requirement": "new no-wall trajectories must reproduce historical target "
                           "coordinates and ticks exactly",
            "weakened": False,
        },
        "visible_qualification_rule": {
            "id": "P2_BEST_K_VISIBLE_QUALIFICATION_v0.1",
            "source_commit": ORIGINAL_PREOUTCOME_COMMIT,
            "changed_by_this_supersession": False,
        },
        "decoder_parameters_changed": False,
        "thresholds_changed": False,

        "future_renderer_provenance_requirement": {
            "applies_to": "ALL newly collected MineOcclude data",
            "must_record": [
                "Mesa version", "GL renderer string", "LLVM/llvmpipe identity",
                "DRI driver identity/path", "X server/Xvfb version",
                "screen depth and resolution", "relevant GL environment variables",
                "hashes of bundled rendering libraries where feasible",
            ],
        },
        "future_confirmatory_requirement":
            "confirmatory Regime A prime must use a fresh paired wall/no-wall cohort "
            "collected under one prospectively pinned rendering apparatus",

        "pre_outcome_evidence": {
            "no_wall_scientific_captures": 0,
            "p2_activations": 0,
            "best_k_outcomes_observed": False,
            "full_outcomes_observed": False,
            "gpu_used": False,
        },
        "classification_unchanged": "EXPLORATORY_MATCHED_DIAGNOSTIC",
        "confirmatory_membership": False,
        "P3_NOT_STARTED": True,
        "REGIME_A_PRIME_COLLECTION_AUTHORIZED": "NO",
    }
    digest = write_json(OUT / "p2_authority_supersession.json", payload)
    print("P2_SUPERSESSION_STATUS=FROZEN_PRE_OUTCOME")
    print(f"P2_SUPERSESSION_SHA256={digest}")
    print(f"ORIGINAL_AUTHORITY_UNCHANGED={all(unchanged.values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
