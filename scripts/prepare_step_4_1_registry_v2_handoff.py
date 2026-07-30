"""Build the Person D Phase 4 Step 4.1 registry v2 handoff preparation package.

This produces every machine-readable artifact under
``docs/status/person_d_phase4_step4_1_registry_v2_handoff_v0_1/``. It
does not generate, accept, or claim a scientific baseline: every
document written here is either a structural template (clearly
placeholder hashes/artifact IDs) or the honest current status --
``pending``/``BLOCKED`` -- because Person B has not yet supplied a
real sealed fold manifest or oracle-target document.

Usage:
    python scripts/prepare_step_4_1_registry_v2_handoff.py [--out-dir DIR]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude import baselines
from mineocclude.baselines.interface import TrajectoryContext
from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.oracle.schema import (
    ORACLE_INFORMATION_SET,
    ORACLE_METHOD,
    ORACLE_TARGET_SCHEMA_VERSION,
    TARGET_ID_SUFFIX,
    TARGET_SOURCE,
)

FOLD_FIXTURE_PATH = ROOT / "tests" / "fixtures" / "person_d" / "synthetic_b_fold_manifest.json"

#: Placeholder authority revision for the owner-status record -- the
#: exact git revision this preparation package was built from.
AUTHORITY_REVISION = "4fe28c61a01578cc6f7747c89d6aa1cd0f005299"

#: Deliberately obviously-fake placeholder hashes: repeated single hex
#: digits, never mistakable for a real SHA-256.
PLACEHOLDER_FOLD_MANIFEST_HASH = "0" * 64
PLACEHOLDER_ORACLE_TARGET_HASH = "1" * 64
PLACEHOLDER_CONFIG_HASH = "2" * 64
PLACEHOLDER_TARGET_SHA256 = "3" * 64
_CODE_SHA = "d" * 40
_INPUT_MANIFEST_HASH = "e" * 64


def _best_case_but_blocked_scientific_readiness_check() -> dict:
    """Same construction as tests/baselines/test_scientific_readiness.py.

    The most structurally valid synthetic input this project's own
    oracle schema will accept without Person B's real coordinate-frame
    signoff -- and it is still BLOCKED, for exactly one reason:
    scientific_use=forbidden. See that test module's docstring for why
    this is the intended, load-bearing property under test, not a gap.
    """

    fold_manifest = json.loads(FOLD_FIXTURE_PATH.read_text(encoding="utf-8"))
    keys = [
        (m["trajectory_id"], m["model_frame_idx"]) for m in fold_manifest["memberships"]
    ]
    fold_by_key = {
        (m["trajectory_id"], m["model_frame_idx"]): m["fold_idx"]
        for m in fold_manifest["memberships"]
    }

    contexts = [
        TrajectoryContext(
            trajectory_id=trajectory_id,
            layout_id=trajectory_id.replace("traj-", "layout-"),
            model_frame_idx=frame,
            fold=fold_by_key[(trajectory_id, frame)],
            regime="A",
            tau_seconds=0.0,
            visibility=True,
            last_seen_position_blocks=float(frame),
            last_seen_velocity_blocks_per_s=None,
            v_scripted_blocks_per_s=None,
            q_scripted_blocks2_per_s=None,
            duration_seconds=None,
            config_hash="cfg-test",
            seed=123,
        )
        for trajectory_id, frame in keys
    ]

    const_run_id = "run-synthetic-d-readiness-check"
    const_code_sha = "d" * 40
    const_config_hash = "b" * 64
    const_model_hash = "c" * 64
    const_preprocess_hash = "e" * 64
    const_accepted_manifest_hash = "a" * 64
    const_source_run_id = "source-run-1"

    rows = []
    for trajectory_id, frame in keys:
        position = float(frame)
        rows.append(
            {
                "episode_id": f"ep-{trajectory_id}",
                "trajectory_id": trajectory_id,
                "server_tick": frame,
                "render_frame_idx": frame,
                "action_idx": frame,
                "model_frame_idx": frame,
                "layout_id": trajectory_id.replace("traj-", "layout-"),
                "regime": "synthetic_test",
                "visibility": "visible",
                "tau": 0.0,
                "v": 1.0,
                "q": 0.02,
                "duration": 3.0,
                "code_sha": const_code_sha,
                "config_hash": const_config_hash,
                "model_hash": const_model_hash,
                "preprocess_hash": const_preprocess_hash,
                "seed": 20260719,
                "schema_version": SCHEMA_VERSION,
                "run_id": const_run_id,
                "status": "accepted",
                "exclusion_reason": None,
                "superseded_by": None,
                "target_schema_version": ORACLE_TARGET_SCHEMA_VERSION,
                "target_id": f"{trajectory_id}:{frame}:{TARGET_ID_SUFFIX}",
                "target_source": TARGET_SOURCE,
                "oracle_method": ORACLE_METHOD,
                "oracle_information_set": list(ORACLE_INFORMATION_SET),
                "accepted_manifest_hash": const_accepted_manifest_hash,
                "source_run_id": const_source_run_id,
                "last_visible_position_blocks": position,
                "mu_oracle_blocks": position,
                "var_oracle_blocks2": 0.0,
                "sigma_oracle_blocks": 0.0,
                "log_sigma_oracle": None,
                "x_true_blocks": position,
                "synthetic": True,
                "scientific_use": "forbidden",
            }
        )
    oracle_target_document = {
        "schema_version": SCHEMA_VERSION,
        "target_schema_version": ORACLE_TARGET_SCHEMA_VERSION,
        "join_key": ["trajectory_id", "model_frame_idx"],
        "rows": rows,
        "fixture_metadata": {"synthetic": True, "scientific_use": "forbidden"},
    }

    finding = baselines.validate_scientific_baseline_readiness(
        contexts,
        fold_manifest=fold_manifest,
        oracle_target_document=oracle_target_document,
        candidate_scientific_use=baselines.READY_SCIENTIFIC_USE,
    )
    return {
        "check_type": "person_d_step_4_1_scientific_readiness_best_case_check",
        "scientific_use": "forbidden",
        "reason": (
            "the most structurally valid synthetic input buildable without "
            "Person B's real coordinate-frame signoff; confirms the gate "
            "blocks on scientific_use=forbidden alone, not any structural defect"
        ),
        "finding": asdict(finding),
    }


def _registry_v2_templates() -> dict:
    owner_status = baselines.build_owner_status_record(
        owner_status="pending",
        authority_revision=AUTHORITY_REVISION,
        authorized_artifact_types=["baseline_prediction_document"],
        artifact_id="person_d_baseline_owner_status_v1",
        code_sha=_CODE_SHA,
        config_hash=PLACEHOLDER_CONFIG_HASH,
        input_manifest_hash=_INPUT_MANIFEST_HASH,
    )

    target_artifact_id = baselines.build_baseline_prediction_artifact_id(
        baseline_id="last_seen_v1",
        target_name="mu_oracle_blocks",
        fold_manifest_hash=PLACEHOLDER_FOLD_MANIFEST_HASH,
        oracle_target_hash=PLACEHOLDER_ORACLE_TARGET_HASH,
        config_hash=PLACEHOLDER_CONFIG_HASH,
    )

    authorization = baselines.build_exact_artifact_authorization(
        target_artifact_id=target_artifact_id,
        target_artifact_type="baseline_prediction_document",
        target_artifact_sha256=PLACEHOLDER_TARGET_SHA256,
        owner_status_record_hash=owner_status["artifact_hash"],
        direct_input_hashes={
            "fold_manifest_hash": PLACEHOLDER_FOLD_MANIFEST_HASH,
            "oracle_target_hash": PLACEHOLDER_ORACLE_TARGET_HASH,
            "config_hash": PLACEHOLDER_CONFIG_HASH,
        },
        artifact_id="person_d_baseline_exact_artifact_authorization_template_v1",
        code_sha=_CODE_SHA,
        config_hash=PLACEHOLDER_CONFIG_HASH,
        input_manifest_hash=_INPUT_MANIFEST_HASH,
    )

    handoff_manifest = baselines.build_handoff_manifest(
        artifact_identities=[
            {
                "artifact_id": target_artifact_id,
                "artifact_type": "baseline_prediction_document",
                "artifact_sha256": PLACEHOLDER_TARGET_SHA256,
            }
        ],
        owner_status_record_hash=owner_status["artifact_hash"],
        artifact_id="person_d_baseline_handoff_manifest_template_v1",
        code_sha=_CODE_SHA,
        config_hash=PLACEHOLDER_CONFIG_HASH,
        input_manifest_hash=_INPUT_MANIFEST_HASH,
    )

    verification_receipt = baselines.build_verification_receipt(
        verified_artifact_id=target_artifact_id,
        verified_sha256=PLACEHOLDER_TARGET_SHA256,
        verification_mode="local_bytes",
        verification_result="pass",
        artifact_id="person_d_baseline_verification_receipt_template_v1",
        code_sha=_CODE_SHA,
        config_hash=PLACEHOLDER_CONFIG_HASH,
        input_manifest_hash=_INPUT_MANIFEST_HASH,
    )

    package = baselines.RegistryV2HandoffPackage(
        owner_status_record=owner_status,
        exact_artifact_authorization=authorization,
        handoff_manifest=handoff_manifest,
        verification_receipt=verification_receipt,
    )
    baselines.validate_registry_v2_handoff_package(package)

    return {
        "owner_status": owner_status,
        "exact_artifact_authorization_template": authorization,
        "handoff_manifest_template": handoff_manifest,
        "verification_receipt_template": verification_receipt,
        "composite_validation_report": {
            "report_type": "person_d_registry_v2_composite_validation",
            "validated": True,
            "detail": (
                "owner-status, exact-artifact authorization, handoff manifest, "
                "and verification receipt cross-references (owner_status_record_hash, "
                "target_artifact_id membership, verified_sha256 match) all agree. "
                "This validates internal consistency of the templates -- it does "
                "not authorize any real artifact, since target_artifact_sha256 and "
                "direct_input_hashes above are placeholder values."
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT
        / "docs"
        / "status"
        / "person_d_phase4_step4_1_registry_v2_handoff_v0_1",
    )
    args = parser.parse_args()
    registry_v2_dir = args.out_dir / "registry_v2"
    registry_v2_dir.mkdir(parents=True, exist_ok=True)

    templates = _registry_v2_templates()
    for name, document in (
        ("owner_status.json", templates["owner_status"]),
        (
            "exact_artifact_authorization_template.json",
            templates["exact_artifact_authorization_template"],
        ),
        ("handoff_manifest_template.json", templates["handoff_manifest_template"]),
        (
            "verification_receipt_template.json",
            templates["verification_receipt_template"],
        ),
        (
            "composite_validation_report.json",
            templates["composite_validation_report"],
        ),
    ):
        path = registry_v2_dir / name
        path.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"Wrote {path}")

    readiness_check = _best_case_but_blocked_scientific_readiness_check()
    readiness_path = args.out_dir / "scientific_readiness_best_case_check.json"
    readiness_path.write_text(
        json.dumps(readiness_check, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Wrote {readiness_path}")


if __name__ == "__main__":
    main()
