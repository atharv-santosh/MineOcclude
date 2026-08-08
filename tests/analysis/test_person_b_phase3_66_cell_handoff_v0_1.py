"""Focused regression tests for the additive 66-cell C consumer handoff."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from mineocclude.analysis.phase3_66_cell_validation_v0_1 import (
    PACKAGE_DIRECTORY,
    PERSON_C_ACCEPTED_MANIFEST_COMMIT,
    PERSON_C_ACCEPTED_MANIFEST_PATH,
    PERSON_C_ACCEPTED_MANIFEST_SHA256,
    PERSON_C_AUTHORITY_COMMIT,
    PERSON_C_JOIN_PATH,
    PERSON_C_JOIN_SHA256,
    Phase3ValidationError,
    read_git_blob,
    strict_json,
    strict_jsonl,
    validate_authority,
    validate_authority_binding,
    validate_join_rows,
    validate_package,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def authority() -> dict:
    return validate_authority(REPOSITORY_ROOT)


@pytest.fixture(scope="module")
def joined_rows() -> list[dict]:
    payload = read_git_blob(
        REPOSITORY_ROOT,
        PERSON_C_AUTHORITY_COMMIT,
        PERSON_C_JOIN_PATH,
        PERSON_C_JOIN_SHA256,
    )
    return strict_jsonl(payload, "C joined visibility")


def test_exact_c_manifest_authority_and_counts(authority: dict) -> None:
    assert authority["person_c_authority_commit"] == PERSON_C_AUTHORITY_COMMIT
    assert authority["accepted_manifest_sha256"] == PERSON_C_ACCEPTED_MANIFEST_SHA256
    assert authority["accepted_trajectory_count"] == 66
    assert authority["frame_key_count"] == 2468
    assert authority["visibility"]["unique_primary_key_count"] == 2468


def test_checked_in_authority_binding_is_verified_before_external_evidence() -> None:
    document = strict_json(
        (REPOSITORY_ROOT / PACKAGE_DIRECTORY / "authority_binding.json").read_bytes(),
        "B authority binding",
    )
    validate_authority_binding(document, REPOSITORY_ROOT)


def test_changed_authority_binding_is_rejected() -> None:
    document = strict_json(
        (REPOSITORY_ROOT / PACKAGE_DIRECTORY / "authority_binding.json").read_bytes(),
        "B authority binding",
    )
    document["accepted_data_authority"]["sha256"] = "0" * 64
    with pytest.raises(Phase3ValidationError, match="accepted-manifest hash"):
        validate_authority_binding(document, REPOSITORY_ROOT)


def test_accepted_manifest_is_exact_git_object() -> None:
    payload = read_git_blob(
        REPOSITORY_ROOT,
        PERSON_C_ACCEPTED_MANIFEST_COMMIT,
        PERSON_C_ACCEPTED_MANIFEST_PATH,
        PERSON_C_ACCEPTED_MANIFEST_SHA256,
    )
    document = strict_json(payload, "C accepted manifest")
    assert document["accepted_count"] == 66
    assert len(document["records"]) == 66


def test_joined_package_validates_as_a_whole(joined_rows: list[dict]) -> None:
    accepted = {
        row["trajectory_id"]
        for row in joined_rows
    }
    summary = validate_join_rows(joined_rows, accepted)
    assert summary["row_count"] == 2468
    assert summary["unique_primary_key_count"] == 2468


def test_exact_and_rule_is_fail_closed(joined_rows: list[dict]) -> None:
    altered = deepcopy(joined_rows)
    altered[0]["visible_flag"] = not altered[0]["visible_flag"]
    with pytest.raises(Phase3ValidationError, match="AND visibility rule"):
        validate_join_rows(altered, {row["trajectory_id"] for row in altered})


def test_duplicate_primary_key_is_rejected(joined_rows: list[dict]) -> None:
    altered = deepcopy(joined_rows)
    altered[1]["trajectory_id"] = altered[0]["trajectory_id"]
    altered[1]["model_frame_idx"] = altered[0]["model_frame_idx"]
    with pytest.raises(Phase3ValidationError, match="missing or duplicated"):
        validate_join_rows(altered, {row["trajectory_id"] for row in altered})


def test_quarantined_visible_row_is_rejected(joined_rows: list[dict]) -> None:
    altered = deepcopy(joined_rows)
    index = next(i for i, row in enumerate(altered) if row["quarantined"] is True)
    altered[index]["visible_flag"] = True
    with pytest.raises(Phase3ValidationError, match="AND visibility rule|quarantined row"):
        validate_join_rows(altered, {row["trajectory_id"] for row in altered})


def test_raw_channel_removal_is_rejected(joined_rows: list[dict]) -> None:
    altered = deepcopy(joined_rows)
    altered[0].pop("empirical_magenta_visible")
    with pytest.raises(Phase3ValidationError, match="raw channels"):
        validate_join_rows(altered, {row["trajectory_id"] for row in altered})


def test_invalid_quarantine_category_is_rejected(joined_rows: list[dict]) -> None:
    altered = deepcopy(joined_rows)
    altered[0]["quarantine_category"] = "unrecognized"
    with pytest.raises(Phase3ValidationError, match="quarantine category"):
        validate_join_rows(altered, {row["trajectory_id"] for row in altered})


def test_non_deterministic_row_order_is_rejected(joined_rows: list[dict]) -> None:
    altered = deepcopy(joined_rows)
    altered[0], altered[1] = altered[1], altered[0]
    with pytest.raises(Phase3ValidationError, match="deterministically ordered"):
        validate_join_rows(altered, {row["trajectory_id"] for row in altered})


def test_b_package_passes_and_keeps_formal_closure_fail_closed() -> None:
    result = validate_package(REPOSITORY_ROOT, REPOSITORY_ROOT / PACKAGE_DIRECTORY)
    assert result["receipt"]["decision"] == "PASS"
    assert result["phase3_status"]["step_3_3_final_joined_package_validation"] == "PASS"
    assert result["phase3_status"]["phase3_formally_closed"] is False
    assert result["phase3_status"]["independent_final_verification"] == "PENDING"
    assert result["closure_recommendation"]["phase3_closure_recommendation"] == "READY"


def test_u4_is_not_inspected(authority: dict) -> None:
    assert authority["u4_output_inspected"] is False
