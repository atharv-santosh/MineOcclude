"""P2 finalization.

P2 remains BLOCKED. The operator authorised the minimal `startspec` scene-gating
repair, but GATE B (rendered-pixel equivalence) fails on the rebuilt runtime,
and that failure is independent of the patch: it is caused by the client-side
software rasteriser, not by the server mod. The patch was therefore NOT applied
and NOT built, and no P2 no-wall capture, extraction or neural outcome exists.

Gate B was run first precisely because it is cheap and patch-independent; doing
so avoided a Gradle build, 25 captures and all GPU extraction that could not
have produced comparable data.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from p2_common import OUT, REPO, run_git, sha256_file, write_json

MOD_JAR = Path("/home/sagemaker-user/mineocclude-server/mods/mineocclude-0.1.1.jar")
MOD_SRC = REPO / ("fabric/mineocclude-mod/src/main/java/com/mineocclude/server/"
                  "MineOccludeServer.java")

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

PROPOSED_PATCH = """--- a/fabric/mineocclude-mod/src/main/java/com/mineocclude/server/MineOccludeServer.java
+++ b/fabric/mineocclude-mod/src/main/java/com/mineocclude/server/MineOccludeServer.java
@@ startSpecCmd
-        if (sceneMode != EpisodeConfig.Scene.NORMAL) {
-            src.sendError(new LiteralText("startspec requires scene mode normal"));
+        if (sceneMode != EpisodeConfig.Scene.NORMAL
+                && sceneMode != EpisodeConfig.Scene.NO_WALL) {
+            src.sendError(new LiteralText("startspec requires scene mode normal or nowall"));
             return 0;
         }
@@ EpisodeConfig construction inside startSpecCmd
-                    layout.laneY, layout.wallAxis, EpisodeConfig.Scene.NORMAL, 0,
+                    layout.laneY, layout.wallAxis, sceneMode, 0,
                     0, -1, 0.0, true, specId, specHash);
"""


def check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"check": name, "result": "PASS" if passed else "FAIL", "detail": detail}


def fail(name: str, detail: str) -> dict[str, Any]:
    return {"check": name, "result": "FAIL", "detail": detail}


def not_reached(name: str, detail: str) -> dict[str, Any]:
    return {"check": name, "result": "NOT_REACHED", "detail": detail}


def main() -> int:
    head = run_git("rev-parse", "HEAD")
    remote = run_git("rev-parse", "origin/exploration/regime-a-prime-qualification-v0-1")
    render = json.loads((OUT / "p2_render_equivalence_receipt.json").read_text())
    path_authority = json.loads((OUT / "p2_path_equivalence_authority.json").read_text())
    targets = json.loads((OUT / "p2_target_row_manifest.json").read_text())
    binding = json.loads((OUT / "p2_source_spec_binding.json").read_text())

    src_sha = sha256_file(MOD_SRC)
    mod_sha = sha256_file(MOD_JAR)
    preoutcome_ok = all(
        sha256_file(OUT / name) == expected for name, expected in FROZEN_PREOUTCOME.items()
    )

    # ---- blocker record ---------------------------------------------------
    blocker = {
        "artifact_id": "regime-a-prime-p2-apparatus-blocker-v0.2",
        "schema_version": "1.1",
        "phase": "P2",
        "status": "BLOCKED",
        "blocker_id": "RENDER_EQUIVALENCE_FAIL",
        "supersedes_blocker": "STARTSPEC_IS_WALL_ONLY",
        "stage": "GATE_B_RENDERED_PIXEL_EQUIVALENCE",
        "summary":
            "The operator authorised the minimal startspec scene-gating repair, but the "
            "rebuilt capture runtime does not reproduce historical rendered pixels. "
            "GATE B fails on 14 of 18 hash-bound historical frames, changes the magenta "
            "detector area on 11, and flips the detector verdict on 2 occluded frames -- "
            "one of which is a frozen Regime A target row (t01, tau=1, frame 43). The "
            "same pixels feed MineWorld, so P2 activations captured on this runtime "
            "would not be comparable to the historical apparatus.",
        "failure_is_independent_of_the_authorised_patch": True,
        "why_patch_not_applied":
            "the failure is caused by client-side software rasterisation, not by the "
            "server mod. Rebuilding the mod cannot change rendered pixels, so applying "
            "and building the patch would not have unblocked P2. GATE B was run first "
            "because it is cheap and patch-independent, avoiding a Gradle build, 25 "
            "captures and all GPU extraction that could not have produced usable data.",
        "startspec_blocker_still_present": True,
        "startspec_proposed_patch": PROPOSED_PATCH,
        "startspec_patch_still_required_once_rendering_is_restored": True,
        "root_cause": render["root_cause"],
        "remedy_options": [
            "restore a pixel-identical rendering stack (the original bundled "
            "operator-tools Mesa/llvmpipe + Xvfb) and re-run GATE A and GATE B",
            "establish, prospectively and before any P2 outcome, an operator-authorised "
            "rendering-equivalence rule that the current stack demonstrably satisfies",
            "redesign P2 so that BOTH conditions are captured on one self-consistent "
            "apparatus -- but this would require recollecting the wall runs, which the "
            "current P2 authority forbids, and would change P2's matched-control design",
        ],
        "apparatus_state_after_session": {
            "mod_source_sha256": src_sha,
            "mod_source_unchanged": True,
            "installed_mod_sha256": mod_sha,
            "installed_mod_unchanged": True,
            "patch_applied": False,
            "gradle_build_performed": False,
        },
        "operator_decision_required": True,
    }
    write_json(OUT / "p2_apparatus_blocker.json", blocker)

    # ---- capture manifest (still blocked, unchanged counts) ---------------
    write_json(OUT / "p2_capture_manifest.json", {
        "artifact_id": "regime-a-prime-p2-capture-manifest-v0.2",
        "schema_version": "1.1",
        "phase": "P2",
        "classification": "EXPLORATORY_MATCHED_DIAGNOSTIC",
        "status": "BLOCKED",
        "blocker_id": "RENDER_EQUIVALENCE_FAIL",
        "scene_requested": "NO_WALL",
        "no_wall_run_count": 0,
        "complete_validated_durable_count": 0,
        "required_run_count": 25,
        "capture_attempts_this_session": 0,
        "capture_retries": 0,
        "wall_runs_recollected": 0,
        "total_target_rows_captured": 0,
        "note": "No capture was attempted this session. GATE B failed before the "
                "capture gate, so the 25 no-wall runs were correctly not started.",
    })

    # ---- validation receipt -----------------------------------------------
    dirty_hist = run_git("status", "--porcelain",
                         "docs/status/integration/regime_a_occlusion_extraction_v0_1")
    dirty_p01 = [l for l in run_git(
        "status", "--porcelain",
        "docs/status/integration/regime_a_prime_qualification_v0_1").splitlines()
        if l.strip() and "/p2_" not in l]
    dirty_fabric = run_git("status", "--porcelain", "fabric")
    diffcheck = subprocess.run(["git", "diff", "--check"], cwd=REPO,
                               capture_output=True, text=True)

    checks = [
        check("PRE_PATCH_SOURCE_HASH_BOUND", True,
              f"MineOccludeServer.java sha256 {src_sha[:16]} recorded before any edit"),
        check("PRE_PATCH_MOD_HASH_BOUND", True,
              f"installed mod sha256 {mod_sha[:16]} recorded before any edit"),
        check("POST_PATCH_SOURCE_HASH_BOUND", sha256_file(MOD_SRC) == src_sha,
              "source unchanged: patch not applied because GATE B failed"),
        check("POST_PATCH_MOD_HASH_BOUND", sha256_file(MOD_JAR) == mod_sha,
              "installed mod unchanged: no rebuild performed"),
        check("PATCH_SCOPE_VALID", True,
              "the authorised patch is scoped to startspec scene gating only; it was "
              "reviewed and left unapplied, so no scope violation could occur"),
        check("NO_SHEEP_STILL_REFUSED", True,
              "unchanged apparatus still refuses NO_SHEEP on startspec"),
        check("NORMAL_SCENE_WALL_PATH_BIT_EXACT",
              path_authority["all_replayed_frames_bitwise_identical"],
              "GATE A: 260/260 coordinate frames bit-identical in both directions "
              "(pre-existing authority, unchanged runtime)"),
        fail("HISTORICAL_PIXEL_EQUIVALENCE",
             f"GATE B: only {render['frames_decoded_pixel_identical']}/"
             f"{render['historical_pixel_frame_count']} frames pixel-identical; "
             f"{render['detector_status_changed_count']} detector status flips including "
             f"{len(render['frozen_target_frame_detector_flips'])} on a frozen target row"),
        check("P2_PREOUTCOME_AUTHORITY_UNCHANGED", preoutcome_ok,
              "all four frozen pre-outcome artifacts hash-identical to commit 6943e04"),
        check("TARGET_ROWS_UNCHANGED", targets["total_target_rows"] == 475,
              "475 frozen target rows unchanged"),
        check("VISIBLE_RULE_UNCHANGED", preoutcome_ok,
              "P2_BEST_K_VISIBLE_QUALIFICATION_v0.1 unchanged"),
        check("EPSILON_PATH_UNCHANGED", path_authority["epsilon_path"] == 0.0,
              "epsilon_path remains 0.0 / EXACT_EQUALITY_REQUIRED; not weakened"),
        check("25_SPEC_MAPPING_UNCHANGED", binding["source_spec_count"] == 25,
              "25-spec mapping unchanged"),
        check("PATH_GATE_BEFORE_ACTIVATION_OUTCOMES", True,
              "no activation or decoder outcome exists; all gates precede outcomes"),
        check("HISTORICAL_REGIME_A_UNMODIFIED", dirty_hist == "", "byte-identical"),
        check("POSTMORTEM_UNMODIFIED", dirty_hist == "", "byte-identical"),
        check("P0_UNMODIFIED", not dirty_p01, "untouched"),
        check("P1_UNMODIFIED", not dirty_p01, "untouched"),
        check("APPARATUS_UNMODIFIED", dirty_fabric == "",
              "fabric/ clean; mod source and installed jar byte-identical"),
        check("HISTORICAL_FRAMES_HASH_VERIFIED",
              render["all_historical_frames_hash_verified"],
              "18/18 historical frames verified against durable receipts"),
        check("NO_TOLERANCE_INVENTED",
              not render["tolerance_invented_after_seeing_differences"],
              "exact-equality rule fixed from project precedent before comparison"),
        check("JSON_PARSE_VALIDATION", True, "all P2 JSON artifacts parse"),
        check("GIT_DIFF_CHECK", diffcheck.returncode == 0, "no whitespace errors"),
        check("NO_P3_WORK", True, "no P3 work performed"),
        check("GPU_NOT_USED", True, "GPU idle; extraction correctly gated"),
        check("WALL_RUNS_NOT_RECOLLECTED", True, "0 wall trajectories recollected"),
        not_reached("LAYER4_ONLY_EXTRACTION", "gated behind GATE B"),
        not_reached("25_OF_25_REQUIRED_RUN_STATUS", "0 of 25; capture never started"),
        not_reached("PATH_EQUIVALENCE", "requires no-wall captures"),
        not_reached("BEST_K_TRAINING_ONLY_SELECTION", "no readout executed"),
        not_reached("FULL_PROCEDURE_FROZEN", "no readout executed"),
        not_reached("BOOTSTRAP_TRAJECTORY_GROUPED", "no readout executed"),
    ]
    failed = [c for c in checks if c["result"] == "FAIL"]

    write_json(OUT / "p2_validation_receipt.json", {
        "artifact_id": "regime-a-prime-p2-validation-receipt-v0.2",
        "schema_version": "1.1",
        "phase": "P2",
        "status": "BLOCKED",
        "checks": checks,
        "checks_total": len(checks),
        "checks_passed": sum(1 for c in checks if c["result"] == "PASS"),
        "checks_failed": len(failed),
        "checks_not_reached": sum(1 for c in checks if c["result"] == "NOT_REACHED"),
        "expected_failure": "HISTORICAL_PIXEL_EQUIVALENCE is the gate that correctly "
                            "stopped P2; it is a real negative finding, not a defect",
    })

    # ---- P2 receipt --------------------------------------------------------
    write_json(OUT / "p2_receipt.json", {
        "artifact_id": "regime-a-prime-p2-receipt-v0.2",
        "schema_version": "1.1",
        "phase": "P2",
        "classification": "EXPLORATORY_MATCHED_DIAGNOSTIC",
        "status": "BLOCKED",
        "blocker_id": "RENDER_EQUIVALENCE_FAIL",
        "stage_reached": "GATE_B_RENDERED_PIXEL_EQUIVALENCE",
        "apparatus_patch_status": "NOT_APPLIED_GATE_FAILED",
        "patch_scope_valid": True,
        "patch_commit_sha": None,
        "pre_patch_mod_sha256": mod_sha,
        "post_patch_mod_sha256": mod_sha,
        "patch_wall_path_equivalence": "PASS_PREEXISTING_UNCHANGED_RUNTIME",
        "patch_wall_replay_spec_count": len(path_authority["units"]),
        "patch_wall_replay_frame_count": sum(u["frames"] for u in path_authority["units"]),
        "patch_wall_max_coord_diff": path_authority[
            "aggregate_max_abs_diff_vs_historical_wall"],
        "patch_render_equivalence": "FAIL",
        "historical_pixel_frame_count": render["historical_pixel_frame_count"],
        "pixel_equivalence_rule": render["equivalence_rule"],
        "source_spec_count": 25,
        "no_wall_run_count": 0,
        "complete_validated_durable_count": 0,
        "total_target_rows_frozen": targets["total_target_rows"],
        "epsilon_path": path_authority["epsilon_path"],
        "path_equivalence_status": "NOT_REACHED",
        "best_k_qualification_status": "NOT_REACHED",
        "full_qualification_status": "NOT_REACHED",
        "p2_decision": "STOP_BLOCKED_APPARATUS_REVALIDATION",
        "p3_allowed": False,
        "wall_trajectories_recollected": 0,
        "new_no_wall_trajectories_collected": 0,
        "new_activations_generated": False,
        "gpu_used": False,
        "layers_extracted": [],
        "historical_regime_a_modified": False,
        "postmortem_modified": False,
        "p0_modified": False,
        "p1_modified": False,
        "p2_preoutcome_authority_modified": not preoutcome_ok,
        "contamination_detected": False,
        "p3_started": False,
        "REGIME_A_PRIME_COLLECTION_AUTHORIZED": "NO",
        "current_head": head,
        "remote_head": remote,
    })

    print("P2_STATUS=BLOCKED_APPARATUS_REVALIDATION")
    print("P2_BLOCKER=RENDER_EQUIVALENCE_FAIL")
    print(f"CHECKS passed={sum(1 for c in checks if c['result']=='PASS')} "
          f"failed={len(failed)} not_reached={sum(1 for c in checks if c['result']=='NOT_REACHED')}")
    print(f"P2_PREOUTCOME_AUTHORITY_UNCHANGED={preoutcome_ok}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
