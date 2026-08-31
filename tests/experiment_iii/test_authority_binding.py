"""Authority binding integrity (A.30) and the successor amendment record.

``AUTHORITY_SHA256`` is the SHA-256 of the canonical markdown's **bytes**, so the
byte-level properties are tested, not assumed.

The master salt derives from ``COHORT_SALT_AUTHORITY_SHA256`` -- the authority
under which A1 materialized the cohort -- rather than the current authority hash
(authority 2.2a, Amendment 3g). Before that pinning, any authority edit changed
the entire candidate stream and therefore the scientific population.
"""

from __future__ import annotations

import hashlib

import pytest

from mineocclude.experiment_iii import authority
from mineocclude.experiment_iii.errors import ExperimentIIIError

AMENDMENT_RECORD = (
    authority.AUTHORITY_ROOT
    / "AUTHORITY_AMENDMENT_2_COHORT_ADMISSION_FEASIBILITY.md"
)
AMENDMENT_3_RECORD = (
    authority.AUTHORITY_ROOT
    / "AUTHORITY_AMENDMENT_3_P0_OPERATIONAL_COMPLETENESS.md"
)


def test_amendment_3_record_exists_and_declares_prospective_status():
    assert AMENDMENT_3_RECORD.is_file()
    text = AMENDMENT_3_RECORD.read_text(encoding="utf-8")
    assert "Scientific outcomes existed before amendment | **false**" in text
    assert "P0 frames observed | **0**" in text


def test_authority_binding_matches_the_frozen_successor():
    bound = authority.verify_authority_binding()
    assert bound["AUTHORITY_SHA256"] == authority.FROZEN_AUTHORITY_SHA256
    assert (
        bound["MACHINE_AUTHORITY_SHA256"] == authority.FROZEN_MACHINE_AUTHORITY_SHA256
    )


def test_authority_version_is_the_successor():
    assert authority.AUTHORITY_VERSION == "v1.6"
    assert authority.machine_authority()["authority_version"] == "v1.6"


def test_predecessor_is_recorded_as_immutable_provenance():
    """The whole lineage stays addressable: v1.6 <- v1.5 <- v1.4."""
    assert (
        authority.PREDECESSOR_AUTHORITY_FREEZE_COMMIT
        == "3fd66eddfce017078b6af2774a381077759b98a0"
    )
    assert authority.PREDECESSOR_AUTHORITY_SHA256 == (
        "3d116d9713b2c7fa705a194023e271061f712d0693618abbd991efa45437d7fb"
    )
    assert (
        authority.PREDECESSOR_2_AUTHORITY_FREEZE_COMMIT
        == "e86347b1275560f18cae79a9a3333d8af757adbe"
    )
    assert authority.PREDECESSOR_2_AUTHORITY_SHA256 == (
        "993e5859fa53084889abbc8dda654cd9045dd871258e078cc1afb237f59b4daa"
    )
    assert (
        authority.PREDECESSOR_AUTHORITY_SHA256 != authority.FROZEN_AUTHORITY_SHA256
    )
    assert (
        authority.PREDECESSOR_2_AUTHORITY_SHA256 != authority.PREDECESSOR_AUTHORITY_SHA256
    )


def test_master_salt_is_pinned_to_the_cohort_authority_not_the_current_one():
    """Authority 2.2a — an operational amendment must not move the cohort.

    Before Amendment 3g the salt read the CURRENT authority hash, so v1.6 would
    have regenerated a different candidate stream and a different 25-identity
    cohort out of an edit that changed no scientific decision.
    """
    import hashlib

    assert authority.COHORT_SALT_AUTHORITY_SHA256 == (
        "3d116d9713b2c7fa705a194023e271061f712d0693618abbd991efa45437d7fb"
    )
    assert authority.COHORT_SALT_AUTHORITY_SHA256 != authority.FROZEN_AUTHORITY_SHA256
    expected = hashlib.sha256(
        (
            "MINEOCCLUDE_EXPERIMENT_III_V1|"
            + authority.COHORT_SALT_AUTHORITY_SHA256
            + "|"
            + authority.phase0_design_sha256()
        ).encode("utf-8")
    ).hexdigest()
    assert authority.master_salt() == expected
    cohort = authority.machine_authority()["cohort"]
    assert cohort["master_salt_floats_with_current_authority"] is False
    assert cohort["cohort_byte_identical_across_v1_5_and_v1_6"] is True


@pytest.mark.parametrize(
    "name",
    [
        "EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.md",
        "EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.json",
        "EXPERIMENT_III_TEST_PLAN.md",
        "BLOCKER_TAXONOMY.json",
        "README.md",
        "AUTHORITY_VALIDATION_REPORT.md",
        "RECOVERY_AND_RESUME_RUNBOOK.md",
        "IMPLEMENTATION_CHANGE_MATRIX.json",
        "AUTHORITY_AMENDMENT_2_COHORT_ADMISSION_FEASIBILITY.md",
    ],
)
def test_authority_artifacts_are_lf_only(name):
    """`.gitattributes` stores LF; a CRLF working copy would hash differently.

    The salt derives from the markdown bytes, so a stray CRLF rewrite silently
    changes the whole cohort. This makes that loud.
    """
    payload = (authority.AUTHORITY_ROOT / name).read_bytes()
    assert payload.count(b"\r\n") == 0, f"{name} contains CRLF line endings"


def test_authority_sha256_is_the_markdown_bytes():
    payload = authority.AUTHORITY_MARKDOWN_PATH.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == authority.FROZEN_AUTHORITY_SHA256


def test_master_salt_derives_from_the_pinned_cohort_authority_bytes():
    """Authority 2.2a: derived from immutable digests, never chosen."""
    expected = hashlib.sha256(
        (
            "MINEOCCLUDE_EXPERIMENT_III_V1|"
            + authority.COHORT_SALT_AUTHORITY_SHA256
            + "|"
            + authority.FROZEN_PHASE0_DESIGN_SHA256
        ).encode()
    ).hexdigest()
    assert authority.master_salt() == expected


def test_amendment_2_record_exists_and_declares_prospective_status():
    assert AMENDMENT_RECORD.is_file()
    text = AMENDMENT_RECORD.read_text(encoding="utf-8")
    for required in (
        "PREDECESSOR_AUTHORITY_FREEZE_COMMIT = e86347b1275560f18cae79a9a3333d8af757adbe",
        "SCIENTIFIC_OUTCOMES_EXISTED         = false",
        "CAPTURE_EXISTED                     = false",
        "COHORT_MATERIALIZED                 = false",
        "PROSPECTIVE_STATUS                  = true",
        "DISCOVERY_STAGE                     = I02",
    ):
        assert required in text, required


def test_machine_authority_records_amendment_2():
    amendment = authority.machine_authority()["authority_amendment_2"]
    assert amendment["selected_repair"] == "D"
    assert amendment["prospective"] is True
    assert amendment["cohort_materialized_before_amendment"] is False
    assert amendment["capture_existed_before_amendment"] is False
    assert amendment["scientific_outcomes_existed_before_amendment"] is False
    assert amendment["gate_9_threshold_unchanged"] == 0.10
    assert amendment["master_salt_unchanged"] is True
    assert amendment["q_grid_unchanged"] is True
    assert amendment["target_window_rule_unchanged"] is True
    assert (
        amendment["admission_order_unchanged"]
        == "STRICTLY_ASCENDING_INDEX_FIRST_QUALIFYING"
    )


def test_gate_12_scope_is_recorded_in_the_machine_authority():
    gate = authority.machine_authority()["cohort"]["all_q_qualification_gate"]
    assert gate["per_q_gates"] == [1, 2, 3, 4, 5, 6, 7, 8, 10, 11]
    assert gate["gate_9_is_peer_dependent_and_excluded_from_per_q_evaluation"] is True
    assert gate["gate_9_evaluated_once_on_the_production_cohort_at_q"] == 0.05
    assert gate["gate_9_threshold_unchanged"] == 0.10


def test_drifted_authority_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(authority, "FROZEN_AUTHORITY_SHA256", "0" * 64)
    authority.authority_sha256.cache_clear()
    try:
        with pytest.raises(ExperimentIIIError) as caught:
            authority.verify_authority_binding()
        assert caught.value.blocker == "PROVENANCE_AUTHORITY_DRIFT"
    finally:
        authority.authority_sha256.cache_clear()
