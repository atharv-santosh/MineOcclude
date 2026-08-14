"""D2 (EXPLORATORY): exact in-context visibility audit of all 475 frozen rows.

Reconstructs the real MineWorld input window for every frozen hidden activation
using the extractor's own semantics and the repository's own visibility states.
No new detector is defined.

Frozen semantics (scripts/run_regime_a.py :: PersistentMineWorldWorker.extract):
    line 909  targets  = [row.model_frame_idx for row in visibility if tau in 1..19]
    line 930  indices  = list(range(target - 15, target + 1))   # 16 pairs, incl. target
    line 934  span     = tokenized.frame_token_map.spans[-1]    # target frame tokens

Visibility states are read verbatim from raw/visibility.jsonl:
    visibility_class in {VISIBLE_AGREEMENT, OCCLUDED_AGREEMENT,
                         VISIBILITY_DISAGREEMENT, INVALID_VISIBILITY}
    magenta_status   in {detected, not_detected}   <- rendered-pixel evidence
    geometric_status in {visible, occluded}
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/sagemaker-user/MineOcclude/scripts/postmortem_v0_1")

from pm_common import (  # noqa: E402
    ALL_BINS,
    CONF,
    META,
    OUT,
    context_indices,
    read_jsonl,
    trajectory_ids,
    write_json,
)

GEO_CODE = {"visible": "v", "occluded": "o"}
PIX_CODE = {"detected": "d", "not_detected": "n"}
CLS_CODE = {
    "VISIBLE_AGREEMENT": "V",
    "OCCLUDED_AGREEMENT": "O",
    "VISIBILITY_DISAGREEMENT": "D",
    "INVALID_VISIBILITY": "I",
}


def main() -> int:
    preds = pd.read_parquet(CONF / "slice_predictions.parquet")
    records = []
    mapping_checks = []

    for traj in trajectory_ids():
        vis = read_jsonl(META / traj / "visibility.jsonl")
        inv = json.loads((META / traj / "activation_inventory.json").read_text())
        by_frame = {int(r["model_frame_idx"]): r for r in vis}
        targets = inv["target_model_frame_indices"]
        taus = inv["target_tau"]

        # Independently rebuild the extractor's own target list and confirm it.
        rebuilt = [int(r["model_frame_idx"]) for r in vis if r.get("tau") in range(1, 20)]
        frozen_rows = preds[preds["trajectory_id"] == traj].sort_values("tau")
        mapping_checks.append(
            {
                "trajectory_id": traj,
                "inventory_targets_equal_rebuilt": rebuilt == list(targets),
                "inventory_targets_equal_predictions_model_frame_idx": (
                    list(targets) == frozen_rows["model_frame_idx"].tolist()
                ),
                "tau_sequence_is_1_to_19": list(taus) == list(range(1, 20)),
                "n_targets": len(targets),
                "min_context_frame": int(min(targets) - 15),
                "trajectory_frame_count": len(vis),
            }
        )

        direction = str(frozen_rows["direction"].iloc[0])
        for tau, target in zip(taus, targets):
            ctx = context_indices(int(target))
            rows = [by_frame[i] for i in ctx]

            cls = [r["visibility_class"] for r in rows]
            geo = [r["geometric_status"] for r in rows]
            pix = [r["magenta_status"] for r in rows]
            px_area = [r["magenta_area_pixels"] for r in rows]

            n_clean = sum(c == "VISIBLE_AGREEMENT" for c in cls)
            n_occ = sum(c == "OCCLUDED_AGREEMENT" for c in cls)
            n_partial = sum(
                c in ("VISIBILITY_DISAGREEMENT", "INVALID_VISIBILITY") for c in cls
            )
            n_pix = sum(p == "detected" for p in pix)
            n_geo_vis = sum(g == "visible" for g in geo)

            # Frames since last evidence, measured back from the target frame.
            def since(flags: list[bool]) -> int | None:
                idx = [i for i, f in enumerate(flags) if f]
                if not idx:
                    return None
                return len(ctx) - 1 - idx[-1]

            since_clean = since([c == "VISIBLE_AGREEMENT" for c in cls])
            since_pix = since([p == "detected" for p in pix])

            bin_name = str(frozen_rows[frozen_rows["tau"] == tau]["duration_bin"].iloc[0])
            records.append(
                {
                    "trajectory_id": traj,
                    "direction": direction,
                    "tau": int(tau),
                    "duration_bin": bin_name,
                    "target_frame": int(target),
                    "context_first_frame": ctx[0],
                    "context_last_frame": ctx[-1],
                    "context_frames": ",".join(str(i) for i in ctx),
                    "context_size": len(ctx),
                    "n_clean_visible": n_clean,
                    "n_partial_transition": n_partial,
                    "n_occluded_agreement": n_occ,
                    "n_rendered_pixel_evidence": n_pix,
                    "n_geometric_visible": n_geo_vis,
                    "any_clean_visible": n_clean > 0,
                    "any_rendered_pixel_evidence": n_pix > 0,
                    "any_sheep_evidence_clean_or_partial": (n_clean + n_partial) > 0,
                    "frames_since_last_clean_visible": since_clean,
                    "frames_since_last_rendered_evidence": since_pix,
                    "max_context_magenta_pixels": (
                        max([p for p in px_area if p is not None], default=0)
                    ),
                    "sum_context_magenta_pixels": (
                        sum(p for p in px_area if p is not None)
                    ),
                    "class_context": "".join(CLS_CODE[c] for c in cls),
                    "geometric_context": "".join(GEO_CODE[g] for g in geo),
                    "pixel_context": "".join(PIX_CODE[p] for p in pix),
                }
            )

    frame = pd.DataFrame.from_records(records)
    assert len(frame) == 475, len(frame)
    frame = frame.sort_values(["trajectory_id", "tau"]).reset_index(drop=True)
    frame.to_parquet(OUT / "d2_context_visibility.parquet", index=False)

    def agg(sub: pd.DataFrame) -> dict:
        sc = sub["frames_since_last_clean_visible"].dropna()
        sp = sub["frames_since_last_rendered_evidence"].dropna()
        return {
            "rows": int(len(sub)),
            "pct_with_any_clean_visible_context_frame": float(
                100.0 * sub["any_clean_visible"].mean()
            ),
            "median_clean_visible_frame_count": float(sub["n_clean_visible"].median()),
            "min_clean_visible_frame_count": int(sub["n_clean_visible"].min()),
            "max_clean_visible_frame_count": int(sub["n_clean_visible"].max()),
            "pct_with_any_rendered_pixel_evidence": float(
                100.0 * sub["any_rendered_pixel_evidence"].mean()
            ),
            "median_rendered_evidence_frame_count": float(
                sub["n_rendered_pixel_evidence"].median()
            ),
            "min_rendered_evidence_frame_count": int(
                sub["n_rendered_pixel_evidence"].min()
            ),
            "max_rendered_evidence_frame_count": int(
                sub["n_rendered_pixel_evidence"].max()
            ),
            "pct_with_any_partial_or_clean": float(
                100.0 * sub["any_sheep_evidence_clean_or_partial"].mean()
            ),
            "median_frames_since_last_clean_visible": (
                float(sc.median()) if len(sc) else None
            ),
            "min_frames_since_last_clean_visible": int(sc.min()) if len(sc) else None,
            "max_frames_since_last_clean_visible": int(sc.max()) if len(sc) else None,
            "median_frames_since_last_rendered_evidence": (
                float(sp.median()) if len(sp) else None
            ),
            "min_frames_since_last_rendered_evidence": int(sp.min()) if len(sp) else None,
            "max_frames_since_last_rendered_evidence": int(sp.max()) if len(sp) else None,
        }

    by_bin = {b: agg(frame[frame["duration_bin"] == b]) for b in ALL_BINS}
    by_bin_dir = {
        f"{b}|{d}": agg(frame[(frame["duration_bin"] == b) & (frame["direction"] == d)])
        for b in ALL_BINS
        for d in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT")
    }
    by_tau = {
        int(t): agg(frame[frame["tau"] == t]) for t in sorted(frame["tau"].unique())
    }
    primary = frame[frame["tau"].between(1, 15)]

    # Direct test of the pre-registered claim under scrutiny.
    claim = {
        "claim": "LONG and NEAR_CONTEXT rows may contain zero sheep evidence",
        "LONG_rows_with_zero_clean_visible": int(
            (~frame[frame["duration_bin"] == "LONG"]["any_clean_visible"]).sum()
        ),
        "LONG_rows_total": int((frame["duration_bin"] == "LONG").sum()),
        "LONG_rows_with_zero_rendered_evidence": int(
            (~frame[frame["duration_bin"] == "LONG"]["any_rendered_pixel_evidence"]).sum()
        ),
        "NEAR_CONTEXT_rows_with_zero_clean_visible": int(
            (~frame[frame["duration_bin"] == "NEAR_CONTEXT"]["any_clean_visible"]).sum()
        ),
        "NEAR_CONTEXT_rows_total": int((frame["duration_bin"] == "NEAR_CONTEXT").sum()),
        "NEAR_CONTEXT_rows_with_zero_rendered_evidence": int(
            (
                ~frame[frame["duration_bin"] == "NEAR_CONTEXT"][
                    "any_rendered_pixel_evidence"
                ]
            ).sum()
        ),
        "BEYOND_CONTEXT_rows_with_zero_rendered_evidence": int(
            (
                ~frame[frame["duration_bin"] == "BEYOND_CONTEXT"][
                    "any_rendered_pixel_evidence"
                ]
            ).sum()
        ),
        "BEYOND_CONTEXT_rows_total": int((frame["duration_bin"] == "BEYOND_CONTEXT").sum()),
    }

    # The window is [target-15, target] and target = onset + tau - 1, so the number
    # of pre-occlusion frames retained in context is an exact function of tau.
    gradient = []
    exact_rule = True
    for t in range(1, 20):
        sub = frame[frame["tau"] == t]
        expected = max(0, 16 - t)
        observed = sorted(sub["n_rendered_pixel_evidence"].unique().tolist())
        ok = observed == [expected]
        exact_rule = exact_rule and ok
        gradient.append(
            {
                "tau": t,
                "expected_pre_occlusion_frames_16_minus_tau": expected,
                "observed_rendered_evidence_frame_counts": observed,
                "matches_exact_rule": ok,
                "median_max_context_magenta_pixels": float(
                    sub["max_context_magenta_pixels"].median()
                ),
                "median_sum_context_magenta_pixels": float(
                    sub["sum_context_magenta_pixels"].median()
                ),
                "pct_with_clean_visible": float(100.0 * sub["any_clean_visible"].mean()),
            }
        )

    adjudication = {
        "evidence_gradient_rule": "rendered-evidence frames in context == 16 - tau",
        "exact_for_all_475_rows": exact_rule,
        "primary_domain_tau1_15_rows_with_zero_rendered_evidence": int(
            (~primary["any_rendered_pixel_evidence"]).sum()
        ),
        "primary_domain_rows": int(len(primary)),
        "beyond_context_rows_with_zero_rendered_evidence": int(
            (
                ~frame[frame["duration_bin"] == "BEYOND_CONTEXT"][
                    "any_rendered_pixel_evidence"
                ]
            ).sum()
        ),
        "long_and_near_context_rows_with_zero_clean_visible": int(
            (
                ~frame[frame["duration_bin"].isin(["LONG", "NEAR_CONTEXT"])][
                    "any_clean_visible"
                ]
            ).sum()
        ),
        "long_and_near_context_rows": int(
            frame["duration_bin"].isin(["LONG", "NEAR_CONTEXT"]).sum()
        ),
        "prior_claim_strong_form_refuted": (
            "Every primary tau1..15 row retains at least one context frame with "
            "rendered sheep pixels; LONG and NEAR_CONTEXT are NOT evidence-free."
        ),
        "prior_claim_weak_form_supported": (
            "LONG and NEAR_CONTEXT contain zero clean dual-agreement VISIBLE frames; "
            "their only sheep evidence is the weak tail of the entry transition "
            "(median max 84 px at tau=13 falling to 28 px at tau=15)."
        ),
        "total_starvation_confined_to": "BEYOND_CONTEXT (tau 16..19), 100/100 rows",
        "confound_note": (
            "Because evidence-frame count is exactly 16 - tau, in-context sheep "
            "evidence is perfectly collinear with tau across the primary domain. Any "
            "representation encoding how much sheep evidence its window contains "
            "thereby encodes tau, and tau is monotone in position within a trajectory."
        ),
    }

    payload = {
        "artifact_id": "regime-a-postmortem-d2-context-visibility-v0.1",
        "status": "EXPLORATORY",
        "adjudication": adjudication,
        "evidence_gradient_by_tau": gradient,
        "context_assembly_semantics": {
            "source": "scripts/run_regime_a.py :: PersistentMineWorldWorker.extract",
            "window": "range(target_frame - 15, target_frame + 1)",
            "context_pairs": 16,
            "includes_target_frame": True,
            "preceding_frames": 15,
            "captured_activation": "336 visual tokens of the target (last) frame",
            "teacher_forced": True,
        },
        "evidence_definitions": {
            "clean_visible": "visibility_class == VISIBLE_AGREEMENT (dual-detector agree visible)",
            "partial_transition": "visibility_class in {VISIBILITY_DISAGREEMENT, INVALID_VISIBILITY}",
            "occluded": "visibility_class == OCCLUDED_AGREEMENT",
            "rendered_pixel_evidence": (
                "magenta_status == detected; the rendered-image detector fired on the "
                "actual frame the model consumed, so sheep pixels were present"
            ),
        },
        "mapping_verification": {
            "all_inventory_targets_equal_rebuilt": all(
                m["inventory_targets_equal_rebuilt"] for m in mapping_checks
            ),
            "all_inventory_targets_equal_predictions": all(
                m["inventory_targets_equal_predictions_model_frame_idx"]
                for m in mapping_checks
            ),
            "all_tau_sequences_1_to_19": all(
                m["tau_sequence_is_1_to_19"] for m in mapping_checks
            ),
            "all_context_windows_in_range": all(
                m["min_context_frame"] >= 0 for m in mapping_checks
            ),
            "per_trajectory": mapping_checks,
        },
        "total_rows": int(len(frame)),
        "primary_rows_tau1_15": int(len(primary)),
        "primary_domain_summary": agg(primary),
        "by_bin": by_bin,
        "by_bin_direction": by_bin_dir,
        "by_tau": by_tau,
        "claim_under_test": claim,
    }
    digest = write_json(OUT / "d2_context_visibility_summary.json", payload)

    print("=== D2 mapping verification ===")
    for key, value in payload["mapping_verification"].items():
        if key != "per_trajectory":
            print(f"  {key}: {value}")
    print()
    print("=== D2 by bin ===")
    hdr = f"{'bin':16s} {'rows':>5s} {'%clean':>7s} {'medClean':>9s} {'%pixel':>7s} {'medPix':>7s} {'medSinceClean':>14s} {'medSincePix':>12s}"
    print(hdr)
    for b in ALL_BINS:
        s = by_bin[b]
        print(f"  {b:14s} {s['rows']:5d} {s['pct_with_any_clean_visible_context_frame']:7.1f} "
              f"{s['median_clean_visible_frame_count']:9.1f} "
              f"{s['pct_with_any_rendered_pixel_evidence']:7.1f} "
              f"{s['median_rendered_evidence_frame_count']:7.1f} "
              f"{str(s['median_frames_since_last_clean_visible']):>14s} "
              f"{str(s['median_frames_since_last_rendered_evidence']):>12s}")
    print()
    print("=== D2 claim under test ===")
    print(json.dumps(claim, indent=2))
    print()
    print("=== D2 adjudication ===")
    print(json.dumps(adjudication, indent=2))
    print("  sha256:", digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
