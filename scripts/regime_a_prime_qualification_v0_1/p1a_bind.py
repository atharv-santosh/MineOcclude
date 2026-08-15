"""P1A: input and provenance binding for Regime A prime qualification P1.

EXPLORATORY_EXISTING_DATA. Binds every historical source actually consumed by
P1, records its role and provenance tier, and asserts the P1 scope negatives
before any P1 result is treated as valid.
"""

from __future__ import annotations

import json
from typing import Any

from p1_common import (
    BRANCH,
    CONF,
    INTEG,
    OUT,
    PM,
    REPO,
    build_rows,
    ensure_capture_metadata,
    run_git,
    sha256_file,
    write_json,
)

# Repository sources actually consumed by P1, with role and tier.
REPO_SOURCES: list[tuple[str, str, str]] = [
    (
        CONF / "slice_predictions.parquet",
        "frozen held-out layer-4 FULL and BEST_K predictions plus WORLD_WALL_PARALLEL_X "
        "targets and row identity for all 475 confirmatory rows; REUSED, never recomputed",
        "CLOSED_CONFIRMATORY_REGIME_A",
    ),
    (
        CONF / "analysis_input_binding.json",
        "row identity hash and durable-receipt hash authority used to bind immutable "
        "capture metadata",
        "CLOSED_CONFIRMATORY_REGIME_A",
    ),
    (
        CONF / "slice_validation_receipt.json",
        "closed Regime A validation authority for the frozen prediction package",
        "CLOSED_CONFIRMATORY_REGIME_A",
    ),
    (
        CONF / "slice_best_k_results.json",
        "frozen BEST_K readout authority (k/alpha selection recorded per outer fold)",
        "CLOSED_CONFIRMATORY_REGIME_A",
    ),
    (
        CONF / "slice_primary_results.json",
        "frozen confirmatory primary result; read-only reference",
        "CLOSED_CONFIRMATORY_REGIME_A",
    ),
    (
        CONF / "continuation_adjudication.json",
        "frozen verdict FAIL_NO_DEFENSIBLE_DECODING / PASS_CONTINUE=NO; read-only",
        "CLOSED_CONFIRMATORY_REGIME_A",
    ),
    (
        CONF / "scientific_report.md",
        "closed Regime A scientific report; read-only reference",
        "CLOSED_CONFIRMATORY_REGIME_A",
    ),
    (
        PM / "postmortem_authority.json",
        "outcome-aware exploratory postmortem authority and frozen model-input semantics",
        "OUTCOME_AWARE_POSTMORTEM",
    ),
    (
        PM / "d2_context_visibility.parquet",
        "independent reconciliation target for P1 causal last-evidence indexing",
        "OUTCOME_AWARE_POSTMORTEM",
    ),
    (
        PM / "d2_context_visibility_summary.json",
        "context visibility summary; reconciliation reference",
        "OUTCOME_AWARE_POSTMORTEM",
    ),
    (
        PM / "d6_visible_positive_control.json",
        "per-trajectory visible-control metrics and the frozen matched-span "
        "(tau 8..15) hidden comparator definition",
        "OUTCOME_AWARE_POSTMORTEM",
    ),
    (
        PM / "visible_positive_control_manifest.json",
        "metadata-only visible row selection (200 rows, 8 per trajectory) used as the "
        "visible side of P1C matching",
        "OUTCOME_AWARE_POSTMORTEM",
    ),
]


def main() -> int:
    head = run_git("rev-parse", "HEAD")
    branch = run_git("branch", "--show-current")
    if branch != BRANCH:
        raise RuntimeError(f"wrong branch: {branch}")

    p0_receipt = json.loads((OUT / "p0_receipt.json").read_text())
    if p0_receipt["status"] != "PASS":
        raise RuntimeError("P0 receipt is not PASS")

    # Historical packages must be byte-identical to their committed state.
    dirty = run_git("status", "--porcelain", str(INTEG.relative_to(REPO)))
    if dirty:
        raise RuntimeError(f"historical package is modified:\n{dirty}")

    repo_sources: list[dict[str, Any]] = []
    for path, role, tier in REPO_SOURCES:
        if not path.is_file():
            raise RuntimeError(f"missing P1 source: {path}")
        repo_sources.append({
            "path": str(path.relative_to(REPO)),
            "sha256": sha256_file(path),
            "byte_size": path.stat().st_size,
            "role": role,
            "provenance_tier": tier,
            "belongs_to_closed_regime_a": tier == "CLOSED_CONFIRMATORY_REGIME_A",
            "belongs_to_exploratory_postmortem": tier == "OUTCOME_AWARE_POSTMORTEM",
            "modified_by_p1": False,
        })

    capture_sources = ensure_capture_metadata()

    # Row identity / join authority.
    table = build_rows()
    row_identity = table[[
        "trajectory_id", "activation_row", "model_frame_idx",
        "server_tick", "tau", "duration_bin", "outer_fold",
    ]].to_dict("records")

    binding = {
        "artifact_id": "regime-a-prime-qualification-p1-input-binding-v0.1",
        "schema_version": "1.0",
        "phase": "P1",
        "classification": "EXPLORATORY_EXISTING_DATA",
        "status": "PASS",
        "git": {
            "branch": branch,
            "p0_commit_sha": head,
            "p0_receipt_status": p0_receipt["status"],
            "historical_package_worktree_clean": True,
        },
        "row_identity": {
            "join_authority": "(trajectory_id, tau) with (model_frame_idx, server_tick, "
                              "activation_row, outer_fold) carried verbatim from the "
                              "frozen confirmatory package",
            "closed_regime_a_row_identity_hash":
                json.loads((CONF / "analysis_input_binding.json").read_text())["row_identity_hash"],
            "p1_row_identity_sha256": __import__("hashlib").sha256(
                json.dumps(row_identity, sort_keys=True, separators=(",", ":"),
                           default=str).encode()
            ).hexdigest(),
            "total_frozen_rows": int(len(table)),
            "trajectories": int(table["trajectory_id"].nunique()),
        },
        "repository_sources": repo_sources,
        "immutable_capture_sources": capture_sources,
        "capture_source_note":
            "Per-frame coordinates.jsonl and raw/visibility.jsonl are existing immutable "
            "capture artifacts read from the original Regime A S3 prefixes. They are the "
            "only way to reconstruct a per-row causal last-evidence world position. Each "
            "is hash-verified against durable_receipt.json, which is itself hash-verified "
            "against the P0-bound analysis_input_binding.json. No activations were read.",
        "source_counts": {
            "repository_sources": len(repo_sources),
            "immutable_capture_sources": len(capture_sources),
        },
        "scope_negatives": {
            "new_trajectory_collection": False,
            "new_mineworld_extraction": False,
            "new_activation_generation": False,
            "new_model_inference": False,
            "decoder_refit": False,
            "frozen_predictions_recomputed": False,
            "minecraft_started": False,
            "gpu_used": False,
            "closed_regime_a_modified": False,
            "postmortem_modified": False,
        },
        "confirmatory_membership": {
            "p1_outputs_are_confirmatory_a_prime_evidence": False,
            "REGIME_A_PRIME_COLLECTION_AUTHORIZED": "NO",
        },
    }

    digest = write_json(OUT / "p1_input_binding.json", binding)
    table.to_parquet(OUT / "p1_last_seen_rows.parquet", index=False)

    print("P1A_STATUS=PASS")
    print(f"P1A_BINDING_SHA256={digest}")
    print(f"P1A_REPO_SOURCES={len(repo_sources)}")
    print(f"P1A_CAPTURE_SOURCES={len(capture_sources)}")
    print(f"P1A_ROWS={len(table)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
