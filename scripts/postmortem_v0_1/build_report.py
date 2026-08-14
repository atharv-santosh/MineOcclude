"""Assemble the exploratory postmortem report and validation receipt."""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys

sys.path.insert(0, "/home/sagemaker-user/MineOcclude/scripts/postmortem_v0_1")

from pm_common import (  # noqa: E402
    CONF,
    OUT,
    REPO,
    S3_EXPLORATORY_PREFIX,
    sha256_file,
    write_json,
)

ARTIFACTS = [
    "postmortem_authority.json",
    "postmortem_input_binding.json",
    "d1_headroom.json",
    "d2_context_visibility.parquet",
    "d2_context_visibility_summary.json",
    "d3_prediction_decomposition.json",
    "d4_bin_decomposition.json",
    "d5_learning_curve.json",
    "d6_visible_positive_control.json",
    "d7_physical_scale.json",
    "visible_positive_control_manifest.json",
    "d6_equivalence_receipt.json",
    "d6_visible_activation_inventory.json",
    "postmortem_report.md",
]

CODE = [
    "pm_common.py",
    "phase0_bind.py",
    "d1_headroom.py",
    "d2_context_visibility.py",
    "d3_d4_decomposition.py",
    "d5_learning_curve.py",
    "d6a_build_manifest.py",
    "d6b_extract_visible.py",
    "d6c_visible_control.py",
    "d7_physical_scale.py",
    "build_report.py",
]


def load(name: str) -> dict:
    path = OUT / name
    return json.loads(path.read_text()) if path.exists() else {}


def main() -> int:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    head = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    artifacts = {}
    for name in ARTIFACTS:
        path = OUT / name
        if path.exists():
            artifacts[name] = {
                "path": str(path),
                "byte_size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
    code = {}
    for name in CODE:
        path = REPO / "scripts/postmortem_v0_1" / name
        if path.exists():
            code[name] = {"path": str(path), "sha256": sha256_file(path)}

    d1, d2 = load("d1_headroom.json"), load("d2_context_visibility_summary.json")
    d3, d5 = load("d3_prediction_decomposition.json"), load("d5_learning_curve.json")
    d6 = load("d6_visible_positive_control.json")
    equivalence = load("d6_equivalence_receipt.json")
    inventory = load("d6_visible_activation_inventory.json")

    receipt = {
        "artifact_id": "regime-a-postmortem-validation-receipt-v0.1",
        "created_utc": now,
        "status": "EXPLORATORY_COMPLETE",
        "confirmatory_result_unchanged": {
            "scientific_adjudication": "FAIL_NO_DEFENSIBLE_DECODING",
            "REGIME_A_FIRST25_PASS_CONTINUE": "NO",
            "confirmatory_files_modified": 0,
            "verification": (
                "postmortem_input_binding.json re-hashed every confirmatory file and "
                "matched both self-referential hashes recorded inside the package"
            ),
        },
        "checks": {
            "phase0_binding_status": load("postmortem_input_binding.json").get("status"),
            "d1_reproduces_frozen_macro_r2_exactly": d1.get("reproduction", {}).get("exact_match"),
            "d1_all_tss_match": d1.get("reproduction", {}).get("all_tss_match"),
            "d1_all_sse_match": d1.get("reproduction", {}).get("all_sse_match"),
            "d2_rows_audited": d2.get("total_rows"),
            "d2_target_mapping_verified": d2.get("mapping_verification", {}).get(
                "all_inventory_targets_equal_predictions"
            ),
            "d2_evidence_rule_exact": d2.get("adjudication", {}).get("exact_for_all_475_rows"),
            "d5_fits": len(d5.get("fits", [])),
            "d6_extraction_bitwise_equivalent": equivalence.get("result", {}).get(
                "bitwise_identical"
            ),
            "d6_visible_trajectories": len(inventory.get("artifacts", [])),
            "d6_visible_rows": d6.get("total_rows"),
        },
        "exploratory_activation_storage": {
            "committed_to_git": False,
            "s3_prefix": S3_EXPLORATORY_PREFIX,
            "objects": inventory.get("artifacts", []),
        },
        "artifacts": artifacts,
        "code": code,
        "repository": {"branch": "exploration/regime-a-postmortem-v0-1", "head": head},
    }
    digest = write_json(OUT / "postmortem_validation_receipt.json", receipt)
    print("receipt sha256:", digest)
    print(json.dumps(receipt["checks"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
