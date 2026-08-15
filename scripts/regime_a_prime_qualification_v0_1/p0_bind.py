from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

OUT = (
    ROOT
    / "docs"
    / "status"
    / "integration"
    / "regime_a_prime_qualification_v0_1"
)

EXPECTED_BRANCH = "exploration/regime-a-prime-qualification-v0-1"
PREDECESSOR_BRANCH = "exploration/regime-a-postmortem-v0-1"

CLOSED_REGIME_A_COMMIT = (
    "fa31aaca8af2872663ea81a54d6ed3a51e9f7f0a"
)
POSTMORTEM_FREEZE_COMMIT = (
    "1ad7e5396406d66365e0bf88963e586b4cfc89a1"
)
POSTMORTEM_FINAL_COMMIT = (
    "9b7d0c7f379956ae1fb52720cc15e10d07adb0e4"
)

BASE_PACKAGE = (
    "docs/status/integration/"
    "regime_a_occlusion_extraction_v0_1"
)

EXPECTED_HASHES = {
    f"{BASE_PACKAGE}/first25_analysis/continuation_adjudication.json":
        "af67f3edd9821a793baf5d1b0b63a2a0227791e5a4ae131d2e5dbbe8b1f25a07",

    f"{BASE_PACKAGE}/first25_analysis/result_durability_receipt.json":
        "bd5688041a7220b5216b12f7d27eebc5e26bbb4382990e87ee05c0936b3d84bf",

    f"{BASE_PACKAGE}/first25_analysis/scientific_report.md":
        "1d69caed87a5d4ca5319b2b494b11c2597d35c8fbee612dc9c316f77c9ae4850",

    f"{BASE_PACKAGE}/first25_analysis/slice_best_k_results.json":
        "11d5d2f0527feb31a27a18a19ac76d342f5c72ca3326bee1863b75187dfc4427",

    f"{BASE_PACKAGE}/first25_analysis/slice_predictions.parquet":
        "4a8adbc6c2080da58fba1a64542301ae445a9ddc51b75b1e3a10ee175373e54a",

    f"{BASE_PACKAGE}/postmortem_v0_1/postmortem_authority.json":
        "354fb2014a2efc90e535d7dd5a2d20f46acc99827f27c499b93609a39dc48ce0",

    f"{BASE_PACKAGE}/postmortem_v0_1/postmortem_input_binding.json":
        "3cc9ea3a882a728bd15a57946b29765b0e620c1ca5842de30cf93f8d69c2efe2",

    f"{BASE_PACKAGE}/postmortem_v0_1/postmortem_validation_receipt.json":
        "510723485d21b641d20caaa800f3e2c68cf1d5b048d94a9d78fc252316256d71",

    f"{BASE_PACKAGE}/postmortem_v0_1/postmortem_report.md":
        "8244d0a549a0143482646c4167f75c445f912eba231fe90607bc7ff0ba94b09c",

    f"{BASE_PACKAGE}/postmortem_v0_1/d6_visible_positive_control.json":
        "281950670d29dc9b9d83d8b2a9a8d3494113adae3f0aa347cbc17ec7beeb12c0",
}

ADDITIONAL_BOUND_SOURCES = [
    f"{BASE_PACKAGE}/first25_analysis/analysis_input_binding.json",
    f"{BASE_PACKAGE}/first25_analysis/slice_validation_receipt.json",
    f"{BASE_PACKAGE}/postmortem_v0_1/d2_context_visibility.parquet",
    f"{BASE_PACKAGE}/postmortem_v0_1/d2_context_visibility_summary.json",
]


def run_git(*args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed: {proc.stderr.strip()}"
        )
    return proc.stdout.strip()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(obj, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def source_record(rel: str, expected_hash: str | None = None) -> dict[str, Any]:
    path = ROOT / rel
    require(path.is_file(), f"required source missing: {rel}")

    digest = sha256_file(path)

    if expected_hash is not None:
        require(
            digest == expected_hash,
            f"historical source hash mismatch: {rel}",
        )

    owner_commit = run_git(
        "log",
        "-1",
        "--format=%H",
        "--",
        rel,
    )

    return {
        "path": rel,
        "byte_size": path.stat().st_size,
        "sha256": digest,
        "latest_commit_touching_path": owner_commit,
        "historical_source": True,
        "modified_by_p0": False,
    }


def is_ancestor(commit: str, descendant: str) -> bool:
    proc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, descendant],
        cwd=ROOT,
    )
    return proc.returncode == 0


def artifact_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(ROOT)),
        "byte_size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()

    branch = run_git("branch", "--show-current")
    head = run_git("rev-parse", "HEAD")
    successor_remote = run_git(
        "rev-parse",
        f"origin/{EXPECTED_BRANCH}",
    )
    predecessor_remote = run_git(
        "rev-parse",
        f"origin/{PREDECESSOR_BRANCH}",
    )

    require(branch == EXPECTED_BRANCH, "wrong successor branch")
    require(
        head == POSTMORTEM_FINAL_COMMIT,
        "P0 must execute before successor branch advances beyond base",
    )
    require(
        successor_remote == POSTMORTEM_FINAL_COMMIT,
        "successor remote is not at exact branch base",
    )
    require(
        predecessor_remote == POSTMORTEM_FINAL_COMMIT,
        "predecessor remote does not match frozen postmortem tip",
    )

    require(
        is_ancestor(CLOSED_REGIME_A_COMMIT, head),
        "closed Regime A commit is not an ancestor",
    )
    require(
        is_ancestor(POSTMORTEM_FREEZE_COMMIT, head),
        "postmortem freeze commit is not an ancestor",
    )
    require(
        is_ancestor(POSTMORTEM_FINAL_COMMIT, head),
        "postmortem final commit is not an ancestor",
    )

    historical_sources: list[dict[str, Any]] = []

    for rel, expected in EXPECTED_HASHES.items():
        historical_sources.append(
            source_record(rel, expected)
        )

    for rel in ADDITIONAL_BOUND_SOURCES:
        historical_sources.append(
            source_record(rel)
        )

    continuation_path = (
        ROOT
        / BASE_PACKAGE
        / "first25_analysis"
        / "continuation_adjudication.json"
    )
    scientific_report_path = (
        ROOT
        / BASE_PACKAGE
        / "first25_analysis"
        / "scientific_report.md"
    )

    closed_text = (
        continuation_path.read_text(encoding="utf-8", errors="replace")
        + "\n"
        + scientific_report_path.read_text(
            encoding="utf-8",
            errors="replace",
        )
    )

    require(
        "FAIL_NO_DEFENSIBLE_DECODING" in closed_text,
        "frozen Regime A adjudication token not found",
    )

    branch_authority = {
        "artifact_id":
            "regime-a-prime-qualification-branch-authority-v0.1",
        "schema_version": "1.0",
        "recorded_at": now,
        "status": "PASS",
        "predecessor": {
            "branch": PREDECESSOR_BRANCH,
            "local_sha": POSTMORTEM_FINAL_COMMIT,
            "remote": "origin",
            "remote_sha": predecessor_remote,
            "local_remote_sha_match":
                predecessor_remote == POSTMORTEM_FINAL_COMMIT,
            "package_path":
                f"{BASE_PACKAGE}/postmortem_v0_1/",
        },
        "successor": {
            "branch": EXPECTED_BRANCH,
            "branch_base_sha": POSTMORTEM_FINAL_COMMIT,
            "remote_sha_before_p0_commit": successor_remote,
            "created_from_exact_predecessor_sha": True,
            "package_path":
                "docs/status/integration/"
                "regime_a_prime_qualification_v0_1/",
        },
        "historical_commit_chain": {
            "closed_regime_a":
                CLOSED_REGIME_A_COMMIT,
            "postmortem_freeze":
                POSTMORTEM_FREEZE_COMMIT,
            "postmortem_final":
                POSTMORTEM_FINAL_COMMIT,
            "closed_regime_a_is_ancestor": True,
            "postmortem_freeze_is_ancestor": True,
            "postmortem_final_is_branch_base": True,
        },
        "scope_guards": {
            "p0_only": True,
            "minecraft_started_by_p0": False,
            "fresh_trajectories_collected_by_p0": False,
            "activations_extracted_by_p0": False,
            "new_decoder_fit_by_p0": False,
            "fresh_scientific_outcomes_computed_by_p0": False,
            "historical_regime_a_files_modified_by_p0": False,
            "historical_postmortem_files_modified_by_p0": False,
            "merge_performed_by_p0": False,
            "tag_created_by_p0": False,
            "confirmatory_collection_authorized": False,
        },
    }

    hierarchy = {
        "artifact_id":
            "regime-a-prime-authority-hierarchy-v0.1",
        "schema_version": "1.0",
        "recorded_at": now,
        "phase": "P0",
        "status": "PASS",
        "mutual_exclusivity_required": True,
        "tiers": [
            {
                "tier": 1,
                "name": "CLOSED_CONFIRMATORY_REGIME_A",
                "status": "CLOSED_IMMUTABLE",
                "source_commit": CLOSED_REGIME_A_COMMIT,
                "package_path":
                    f"{BASE_PACKAGE}/first25_analysis/",
                "allowed_use":
                    "Historical result and immutable provenance authority.",
                "forbidden_use": [
                    "Modification or rescue of the frozen result",
                    "Retesting under changed rules as Regime A confirmation",
                    "Membership in future Regime A prime confirmation",
                ],
            },
            {
                "tier": 2,
                "name": "OUTCOME_AWARE_POSTMORTEM",
                "status": "EXPLORATORY_COMPLETE",
                "freeze_commit": POSTMORTEM_FREEZE_COMMIT,
                "final_commit": POSTMORTEM_FINAL_COMMIT,
                "package_path":
                    f"{BASE_PACKAGE}/postmortem_v0_1/",
                "allowed_use":
                    "Explain failure modes and motivate prospective redesign.",
                "forbidden_use": [
                    "Rescue of closed Regime A",
                    "Independent confirmation",
                    "Unlabeled threshold setting",
                ],
            },
            {
                "tier": 3,
                "name": "NEW_MATCHED_DIAGNOSTICS",
                "status": "PENDING_P1",
                "planned_scope": [
                    "P1 existing-data BEST-K versus last-seen",
                    "P1 matched visible versus SHORT",
                    "P2 matched 25-specification no-wall diagnostic",
                ],
                "confirmatory_membership_allowed": False,
                "note":
                    "P1 may derive diagnostic outputs from historical data; "
                    "P2 trajectories are exploratory new data and are excluded "
                    "from future Regime A prime confirmation.",
            },
            {
                "tier": 4,
                "name": "DEVELOPMENT_PREFLIGHT",
                "status": "NOT_STARTED",
                "planned_scope": [
                    "camera qualification",
                    "motion/headroom qualification",
                    "stride/input qualification",
                    "readout/statistical freeze development",
                ],
                "confirmatory_membership_allowed": False,
                "contamination_rule":
                    "Any specification used to choose design parameters is "
                    "development data and cannot enter confirmatory A prime.",
            },
            {
                "tier": 5,
                "name": "CONFIRMATORY_REGIME_A_PRIME",
                "status": "NOT_AUTHORIZED",
                "required_identity": [
                    "new specification IDs",
                    "new random seeds",
                    "prospectively frozen generator authority",
                    "no diagnostic/development membership",
                ],
                "collection_authorized": False,
            },
        ],
        "contamination_rules": {
            "diagnostic_to_confirmatory_reuse": "PROHIBITED",
            "development_to_confirmatory_reuse": "PROHIBITED",
            "old_regime_a_to_a_prime_confirmatory_reuse": "PROHIBITED",
            "same_stochastic_identity_relabeling": "PROHIBITED",
            "new_confirmatory_ids_and_seeds_required": True,
        },
        "current_allowed_transition": "P0_TO_P1_ONLY",
        "scientific_collection_authorized": False,
    }

    historical_receipt = {
        "artifact_id":
            "regime-a-prime-closed-history-binding-receipt-v0.1",
        "schema_version": "1.0",
        "recorded_at": now,
        "phase": "P0",
        "status": "PASS",
        "closed_regime_a": {
            "commit": CLOSED_REGIME_A_COMMIT,
            "branch":
                "exploration/regime-a-occlusion-extraction-v0-1",
            "classification": "CLOSED_CONFIRMATORY",
            "frozen_verdict_token":
                "FAIL_NO_DEFENSIBLE_DECODING",
            "frozen_verdict_token_verified_in_historical_sources":
                True,
            "immutable": True,
            "later_exploratory_rescue_allowed": False,
        },
        "postmortem": {
            "freeze_commit": POSTMORTEM_FREEZE_COMMIT,
            "final_commit": POSTMORTEM_FINAL_COMMIT,
            "branch": PREDECESSOR_BRANCH,
            "classification": "OUTCOME_AWARE_EXPLORATORY",
            "complete": True,
            "may_modify_closed_regime_a_verdict": False,
        },
        "bound_historical_sources": historical_sources,
        "source_count": len(historical_sources),
        "all_expected_hashes_match": True,
        "scientific_collection_authorized": False,
    }

    branch_path = OUT / "branch_authority.json"
    hierarchy_path = OUT / "authority_hierarchy.json"
    history_path = OUT / "closed_regime_a_postmortem_receipt.json"

    write_json(branch_path, branch_authority)
    write_json(hierarchy_path, hierarchy)
    write_json(history_path, historical_receipt)

    created = [
        artifact_record(branch_path),
        artifact_record(hierarchy_path),
        artifact_record(history_path),
        artifact_record(Path(__file__).resolve()),
    ]

    p0_receipt = {
        "artifact_id":
            "regime-a-prime-qualification-p0-receipt-v0.1",
        "schema_version": "1.0",
        "recorded_at": now,
        "phase": "P0",
        "status": "PASS",
        "goal":
            "Bind closed Regime A and outcome-aware postmortem authorities, "
            "freeze successor lineage, and establish contamination tiers "
            "before P1 existing-data qualification.",
        "git_authority": {
            "predecessor_branch": PREDECESSOR_BRANCH,
            "predecessor_sha": POSTMORTEM_FINAL_COMMIT,
            "successor_branch": EXPECTED_BRANCH,
            "successor_branch_base_sha": POSTMORTEM_FINAL_COMMIT,
            "successor_remote_sha_before_p0_commit": successor_remote,
            "created_from_exact_predecessor_sha": True,
        },
        "historical_authority": {
            "closed_regime_a_commit": CLOSED_REGIME_A_COMMIT,
            "postmortem_freeze_commit": POSTMORTEM_FREEZE_COMMIT,
            "postmortem_final_commit": POSTMORTEM_FINAL_COMMIT,
            "frozen_result_preserved": True,
            "postmortem_labeled_exploratory": True,
        },
        "tier_authority": {
            "tier_count": 5,
            "mutually_exclusive": True,
            "confirmatory_a_prime_authorized": False,
        },
        "created_authority_artifacts": created,
        "scope_confirmation": {
            "p0_only": True,
            "fresh_trajectories_collected": False,
            "new_mineworld_extraction": False,
            "new_activations_generated": False,
            "new_decoder_fit": False,
            "fresh_scientific_outcomes_generated": False,
            "closed_regime_a_modified": False,
            "postmortem_modified": False,
            "confirmatory_collection_authorized": False,
        },
        "next_phase": {
            "phase": "P1",
            "classification": "EXPLORATORY_EXISTING_DATA",
            "new_mineworld_extraction_allowed": False,
            "new_trajectory_collection_allowed": False,
        },
    }

    p0_path = OUT / "p0_receipt.json"
    write_json(p0_path, p0_receipt)

    # Final parse/readback validation.
    for path in (
        branch_path,
        hierarchy_path,
        history_path,
        p0_path,
    ):
        with path.open("r", encoding="utf-8") as f:
            loaded = json.load(f)
        require(
            loaded.get("status") == "PASS",
            f"generated P0 artifact not PASS: {path}",
        )

    print("P0_BINDING_STATUS=PASS")
    print(f"P0_SUCCESSOR_BRANCH={EXPECTED_BRANCH}")
    print(f"P0_BRANCH_BASE={POSTMORTEM_FINAL_COMMIT}")
    print(f"P0_CLOSED_REGIME_A_COMMIT={CLOSED_REGIME_A_COMMIT}")
    print(f"P0_POSTMORTEM_FREEZE_COMMIT={POSTMORTEM_FREEZE_COMMIT}")
    print(f"P0_POSTMORTEM_FINAL_COMMIT={POSTMORTEM_FINAL_COMMIT}")
    print(f"P0_BOUND_HISTORICAL_SOURCE_COUNT={len(historical_sources)}")
    print("P0_TIER_COUNT=5")
    print("REGIME_A_PRIME_COLLECTION_AUTHORIZED=NO")
    print("P0_NEXT_PHASE=P1_EXISTING_DATA_ONLY")


if __name__ == "__main__":
    main()
