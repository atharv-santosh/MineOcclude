"""P1D: displacement-from-last-seen diagnostic -- DEFERRED, with descriptive record.

The optional P1D target is

    displacement_target = current_hidden_position - last_rendered_evidence_position

Scoring a displacement READOUT requires predicting displacement from layer-4
activations, i.e. reading the activation tensors and fitting a new decoder. P1
forbids activation reading, decoder fitting and new model inference, and the
frozen package contains no displacement predictions to reuse. The decoder half
of P1D is therefore DEFERRED rather than approximated.

What is free and is recorded here: the displacement target distribution itself,
computed from existing metadata. Note the identity that makes the deferral
harmless for the current decision -- a predicted displacement of exactly zero
reconstructs the last-seen baseline, so the zero-displacement reference RMSE is
already reported as the LAST_RENDERED_EVIDENCE_POSITION baseline in P1B.
"""

from __future__ import annotations

import numpy as np

from p1_common import DOMAINS, OUT, build_rows, domain_frame, write_json


def main() -> int:
    table = build_rows()
    domains = {}
    for name in DOMAINS:
        frame = domain_frame(table, name)
        disp = frame["displacement_from_last_rendered_evidence"].to_numpy(np.float64)
        per_traj = {
            str(traj): {
                "rows": int(len(g)),
                "mean_abs_displacement_blocks": float(
                    g["displacement_from_last_rendered_evidence"].abs().mean()),
                "max_abs_displacement_blocks": float(
                    g["displacement_from_last_rendered_evidence"].abs().max()),
            }
            for traj, g in frame.groupby("trajectory_id")
        }
        domains[name] = {
            "row_count": int(len(frame)),
            "trajectory_count": int(frame["trajectory_id"].nunique()),
            "displacement_blocks": {
                "mean": float(disp.mean()),
                "mean_abs": float(np.abs(disp).mean()),
                "sd": float(disp.std(ddof=0)),
                "min": float(disp.min()),
                "max": float(disp.max()),
                "rms": float(np.sqrt((disp ** 2).mean())),
            },
            "zero_displacement_reference_rmse_blocks": float(np.sqrt((disp ** 2).mean())),
            "zero_displacement_equals_last_seen_baseline": True,
            "per_trajectory": per_traj,
        }

    payload = {
        "artifact_id": "regime-a-prime-qualification-p1d-displacement-v0.1",
        "schema_version": "1.0",
        "phase": "P1",
        "classification": "EXPLORATORY_EXISTING_DATA",
        "P1_DISPLACEMENT_STATUS": "DEFERRED",
        "status": "DEFERRED",
        "target_definition": "displacement_target = current_hidden_position "
                             "- last_rendered_evidence_position",
        "deferral_reason": "Scoring a displacement readout requires reading layer-4 "
                           "activations and fitting a new decoder. P1 forbids activation "
                           "reading, decoder fitting and new model inference, and no "
                           "displacement predictions exist in the frozen package to reuse.",
        "not_deferred_for_outcome_reasons": True,
        "promoted_to_a_prime_primary": False,
        "descriptive_displacement_target": domains,
        "note": "A predicted displacement of zero reconstructs the last-seen baseline "
                "exactly, so zero_displacement_reference_rmse_blocks equals the "
                "LAST_RENDERED_EVIDENCE_POSITION row-level RMSE reported in P1B.",
    }

    digest = write_json(OUT / "p1_displacement_diagnostic.json", payload)
    print("P1_DISPLACEMENT_STATUS=DEFERRED")
    print(f"P1D_SHA256={digest}")
    for name, d in domains.items():
        print(f"{name}: mean_abs_displacement="
              f"{d['displacement_blocks']['mean_abs']:.4f} "
              f"rms={d['displacement_blocks']['rms']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
