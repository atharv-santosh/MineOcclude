"""Phase 0: freeze the exploratory postmortem authority and bind frozen inputs.

Verifies the closed confirmatory package by hash WITHOUT rerunning any science,
then writes postmortem_authority.json and postmortem_input_binding.json.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys

sys.path.insert(0, "/home/sagemaker-user/MineOcclude/scripts/postmortem_v0_1")

from pm_common import (  # noqa: E402
    CONF,
    CONTEXT_INCLUDES_TARGET,
    CONTEXT_PAIRS,
    EFFECTIVE_PRECEDING,
    FROZEN_BEST_K_MACRO_R2,
    FROZEN_MAE,
    FROZEN_NULL_P,
    FROZEN_POOLED_R2,
    FROZEN_PRIMARY_MACRO_R2,
    FROZEN_RMSE,
    FROZEN_VERDICT,
    GUARDS,
    INTEG,
    OUT,
    REPO,
    S3_EXPLORATORY_PREFIX,
    sha256_file,
    trajectory_ids,
    write_json,
)


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def main() -> int:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    head = git("rev-parse", "HEAD")
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    dirty = git("status", "--porcelain")

    # --- bind and verify the closed confirmatory package ---
    confirmatory = {}
    for path in sorted(CONF.iterdir()):
        if path.is_file():
            confirmatory[path.name] = {
                "path": str(path),
                "byte_size": path.stat().st_size,
                "sha256": sha256_file(path),
            }

    # Cross-check the two self-referential hashes the confirmatory package records.
    primary = json.loads((CONF / "slice_primary_results.json").read_text())
    binding_recorded = primary["analysis_input_binding_sha256"]
    binding_actual = confirmatory["analysis_input_binding.json"]["sha256"]
    a5_recorded = primary["a5_receipt_sha256"]
    a5_actual = confirmatory["a5_quality_visibility_confound_receipt.json"]["sha256"]

    verification = {
        "analysis_input_binding_sha256_recorded": binding_recorded,
        "analysis_input_binding_sha256_actual": binding_actual,
        "analysis_input_binding_match": binding_recorded == binding_actual,
        "a5_receipt_sha256_recorded": a5_recorded,
        "a5_receipt_sha256_actual": a5_actual,
        "a5_receipt_match": a5_recorded == a5_actual,
        "analysis_code_commit": primary["analysis_code_commit"],
    }

    # --- bind the frozen authorities the confirmatory analysis itself bound ---
    upstream = {}
    inbind = json.loads((CONF / "analysis_input_binding.json").read_text())
    for name, entry in inbind["artifacts"].items():
        path = entry.get("path")
        record = {"recorded_sha256": entry.get("sha256"), "path": path}
        try:
            from pathlib import Path

            candidate = Path(path)
            if candidate.is_file():
                record["actual_sha256"] = sha256_file(candidate)
                record["match"] = record["actual_sha256"] == entry.get("sha256")
                record["present"] = True
            else:
                record["present"] = False
        except (OSError, TypeError):
            record["present"] = False
        upstream[name] = record

    adjudication = json.loads((CONF / "continuation_adjudication.json").read_text())

    authority = {
        "artifact_id": "regime-a-first25-postmortem-authority-v0.1",
        "created_utc": now,
        "mode": "OUTCOME_AWARE_EXPLORATORY_POSTMORTEM",
        "confirmatory_status": {
            "scientific_adjudication": FROZEN_VERDICT,
            "REGIME_A_FIRST25_PASS_CONTINUE": "NO",
            "state": "CLOSED_IMMUTABLE",
            "primary_layer": 4,
            "primary_readout": "FULL_TOKEN_GRID",
            "primary_target": "WORLD_WALL_PARALLEL_X",
            "primary_rows": "tau1..15",
            "frozen_macro_r2": FROZEN_PRIMARY_MACRO_R2,
            "frozen_pooled_r2": FROZEN_POOLED_R2,
            "frozen_rmse_blocks": FROZEN_RMSE,
            "frozen_mae_blocks": FROZEN_MAE,
            "frozen_best_k_macro_r2": FROZEN_BEST_K_MACRO_R2,
            "frozen_grouped_null_p": FROZEN_NULL_P,
            "adjudication_recorded": adjudication["scientific_adjudication"],
        },
        "constraints": {
            "confirmatory_result_unchanged": True,
            "no_exploratory_metric_may_replace_the_primary_result": True,
            "no_exploratory_result_may_be_reinterpreted_as_confirmatory": True,
            "no_new_minecraft_scientific_collection_authorized": True,
            "no_regime_a_expansion_authorized": True,
            "no_run_b_or_run_c_authorized": True,
            "confirmatory_artifacts_are_read_only": True,
            "visible_frame_activation_extraction_from_existing_immutable_captures": (
                "ALLOWED_ONLY_FOR_D6_MATCHED_POSITIVE_CONTROL"
            ),
            "visible_extraction_forbids": [
                "minecraft_recapture",
                "new_trajectories",
                "changed_camera",
                "changed_speed_or_noise",
                "changed_checkpoint",
                "changed_trajectory_seeds",
                "recomputation_of_hidden_scientific_outcomes",
                "modification_of_the_closed_confirmatory_package",
            ],
            "exploratory_activation_s3_prefix": S3_EXPLORATORY_PREFIX,
        },
        "frozen_model_input_semantics": {
            "source_of_truth": "scripts/run_regime_a.py :: PersistentMineWorldWorker.extract",
            "context_assembly_line_930": "indices = list(range(target - 15, target + 1))",
            "activation_capture_line_934": "span = tokenized.frame_token_map.spans[-1]",
            "context_pairs": CONTEXT_PAIRS,
            "effective_preceding_frames": EFFECTIVE_PRECEDING,
            "context_includes_target_frame": CONTEXT_INCLUDES_TARGET,
            "captured_tokens": "336 visual tokens of the TARGET (last) frame",
            "teacher_forced": True,
        },
        "frozen_amended_guards": GUARDS,
        "guard_rule": (
            "directional maximum consecutive partial/disagreement run plus one "
            "captured frame; a REJECTION THRESHOLD on transition length, not a "
            "temporal offset applied before scoring"
        ),
        "diagnostics": {
            "D1": "target headroom on exact tau1..15 rows; reproduce frozen macro R2",
            "D2": "exact in-context visibility audit of all 475 frozen target rows",
            "D3": "trajectory bias / motion decomposition from frozen OOF predictions",
            "D4": "bin-specific descriptive decomposition (no per-bin refit)",
            "D5": "training-size learning curve on frozen layer-4 activations",
            "D6": "matched visible-sheep positive control (same readout/folds/target)",
            "D7": "optional descriptive physical-scale context",
        },
        "interpretive_constraints": {
            "token_pitch_is_not_a_hard_resolution_bound": True,
            "d3_centering_is_oracle_descriptive_not_an_operational_decoder": True,
            "d3_centering_may_not_rescue_regime_a": True,
        },
        "repository": {
            "branch": branch,
            "starting_head": head,
            "worktree_clean_at_phase0": dirty == "",
        },
    }

    binding = {
        "artifact_id": "regime-a-first25-postmortem-input-binding-v0.1",
        "created_utc": now,
        "status": "PASS" if (verification["analysis_input_binding_match"] and verification["a5_receipt_match"]) else "HASH_MISMATCH",
        "confirmatory_package_verification": verification,
        "confirmatory_artifacts": confirmatory,
        "upstream_authorities_bound_by_confirmatory_analysis": upstream,
        "trajectory_ids": trajectory_ids(),
        "trajectory_count": len(trajectory_ids()),
        "repository": {"branch": branch, "starting_head": head},
    }

    OUT.mkdir(parents=True, exist_ok=True)
    a_hash = write_json(OUT / "postmortem_authority.json", authority)
    b_hash = write_json(OUT / "postmortem_input_binding.json", binding)

    print("phase0 status:", binding["status"])
    print("  analysis_input_binding match:", verification["analysis_input_binding_match"])
    print("  a5 receipt match            :", verification["a5_receipt_match"])
    missing = [k for k, v in upstream.items() if not v.get("present")]
    mismatch = [k for k, v in upstream.items() if v.get("present") and not v.get("match")]
    print("  upstream bound   :", len(upstream))
    print("  upstream missing :", missing)
    print("  upstream mismatch:", mismatch)
    print("  authority sha256 :", a_hash)
    print("  binding   sha256 :", b_hash)
    return 0 if binding["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
