"""Regeneration test for the Phase 6-8 completion package.

The published package under
``docs/status/person_d_phase6to8_completion_v0_1/`` must be exactly what
the generator produces: if it is not, the committed evidence was edited
by hand, which is the failure mode this whole sprint's provenance rules
exist to prevent.

The test also re-validates every document through its own validator, and
asserts the two claims that matter most about this package: nothing in it
is labeled real, and every blocked section names an actionable blocker.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "docs" / "status" / "person_d_phase6to8_completion_v0_1"
GENERATOR = REPO_ROOT / "scripts" / "run_person_d_phase6to8_completion.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "run_person_d_phase6to8_completion", GENERATOR
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def regenerated(tmp_path_factory):
    module = _load_generator()
    output_root = tmp_path_factory.mktemp("phase6to8")
    module.build_all(output_root, REPO_ROOT)
    return output_root


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_published_package_exists():
    assert PACKAGE_ROOT.is_dir(), "the Phase 6-8 completion package is not published"
    assert (PACKAGE_ROOT / "sha256_inventory.json").is_file()


def test_regeneration_is_byte_identical_to_the_published_package(regenerated):
    published = sorted(p.name for p in PACKAGE_ROOT.iterdir() if p.is_file())
    produced = sorted(p.name for p in regenerated.iterdir() if p.is_file())
    assert published == produced

    differing = [
        name
        for name in published
        if _sha256(PACKAGE_ROOT / name) != _sha256(regenerated / name)
    ]
    assert not differing, (
        f"published artifacts differ from a fresh generation: {differing}; the "
        "committed evidence must be exactly what the generator produces"
    )


def test_inventory_hashes_match_the_published_bytes():
    inventory = json.loads((PACKAGE_ROOT / "sha256_inventory.json").read_text("utf-8"))
    for name, expected in inventory["artifact_sha256"].items():
        artifact = PACKAGE_ROOT / name
        assert artifact.is_file(), f"{name} is in the inventory but not on disk"
        assert _sha256(artifact) == expected, f"{name} does not match its recorded hash"
    assert inventory["artifact_count"] == len(inventory["artifact_sha256"])


def test_no_artifact_claims_to_be_real_evidence():
    for artifact in sorted(PACKAGE_ROOT.glob("*.json")):
        document = json.loads(artifact.read_text("utf-8"))
        if "evidence_kind" in document:
            assert document["evidence_kind"] == "synthetic", (
                f"{artifact.name} claims real evidence; no real Person B/E "
                "artifact has been consumed"
            )
    inventory = json.loads((PACKAGE_ROOT / "sha256_inventory.json").read_text("utf-8"))
    assert inventory["real_execution_performed"] is False


def test_every_document_revalidates_through_its_own_validator():
    from mineocclude.baselines.clean_workflow_v0_1 import (
        validate_checkpoint_classification,
        validate_checkpoint_demonstration,
        validate_clean_workflow_run,
    )
    from mineocclude.baselines.control_failure_record_v0_1 import (
        validate_control_failure_record,
    )
    from mineocclude.baselines.direction_control_audit_v0_1 import (
        validate_direction_control_audit,
    )
    from mineocclude.baselines.grouped_nulls_v0_1 import (
        validate_grouped_null_document,
        validate_paired_comparison_document,
    )
    from mineocclude.baselines.missingness_audit_v0_1 import (
        validate_missingness_exclusion_report,
    )
    from mineocclude.baselines.preliminary_report_v0_1 import (
        validate_preliminary_report,
    )
    from mineocclude.baselines.result_lock_v0_1 import validate_result_lock
    from mineocclude.baselines.specificity_damage_report_v0_1 import (
        validate_specificity_damage_report,
    )
    from mineocclude.baselines.u4_control_manifest_v0_1 import (
        validate_control_manifest,
    )
    from mineocclude.baselines.u4_measurement_join_v0_1 import (
        validate_u4_control_matrix,
    )

    validators = {
        "step4_5_missingness_exclusion_report.json": validate_missingness_exclusion_report,
        "step6_3_grouped_nulls.json": validate_grouped_null_document,
        "step6_3_paired_comparisons.json": validate_paired_comparison_document,
        "step6_4_preliminary_comparison_report.json": validate_preliminary_report,
        "step6_5_result_lock.json": validate_result_lock,
        "step7_1_u4_control_manifest.json": validate_control_manifest,
        "step7_2_direction_control_audit.json": validate_direction_control_audit,
        "step7_3_u4_control_matrix.json": validate_u4_control_matrix,
        "step7_4_specificity_damage_report.json": validate_specificity_damage_report,
        "step7_5_control_failure_record.json": validate_control_failure_record,
        "step8_1_clean_workflow_run.json": validate_clean_workflow_run,
        "step8_2_checkpoint_demonstration.json": validate_checkpoint_demonstration,
        "step8_3_checkpoint_classification.json": validate_checkpoint_classification,
    }
    for name, validator in validators.items():
        document = json.loads((PACKAGE_ROOT / name).read_text("utf-8"))
        validator(document)


def test_every_blocked_section_names_an_actionable_blocker():
    report = json.loads(
        (PACKAGE_ROOT / "step6_4_preliminary_comparison_report.json").read_text("utf-8")
    )
    assert report["blockers"]
    for blocker in report["blockers"]:
        assert blocker["missing_artifact"]
        assert blocker["expected_owner"] in {"person_a", "person_b", "person_c", "person_e"}
        assert blocker["expected_schema_or_version"]
        assert blocker["exact_command_after_receipt"]


def test_the_checkpoint_is_yellow_on_unavailable_inputs_not_green():
    classification = json.loads(
        (PACKAGE_ROOT / "step8_3_checkpoint_classification.json").read_text("utf-8")
    )
    assert classification["classification"] == "YELLOW"
    assert classification["unavailable_input_count"] == 3
    assert classification["engineering_failure_count"] == 0
    assert classification["negative_science_count"] == 0
    owners = {finding["owner_role"] for finding in classification["findings"]}
    assert owners == {"person_b", "person_e"}


def test_the_control_manifest_is_frozen_but_not_real():
    manifest = json.loads(
        (PACKAGE_ROOT / "step7_1_u4_control_manifest.json").read_text("utf-8")
    )
    assert manifest["status"] == "frozen"
    assert manifest["evidence_kind"] == "synthetic"
    assert manifest["pre_outcome"] is True
    handoff = json.loads(
        (PACKAGE_ROOT / "step7_1_control_handoff_to_a_and_e.json").read_text("utf-8")
    )
    assert handoff["real_manifest_status"] == "NOT_FROZEN_AS_REAL_EVIDENCE"
    assert handoff["blocking_inputs"]
