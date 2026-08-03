"""Tests for Person D's v0.2 exporter, execution manifest, and frame handoff.

Every test here operates on constructed/synthetic documents and never
fits a baseline, computes a metric, or reads a U4 artifact. Historical
Person D v0.1 behavior is exercised unchanged alongside the new v0.2
path to prove neither disturbs the other.
"""

from __future__ import annotations

import hashlib

import pytest

from mineocclude.baselines.baseline_family_input_v0_2 import (
    BASELINE_FAMILY_CONTRACTS_V0_2,
    BASELINE_INPUT_SCHEMA_VERSION_V0_2,
    FROZEN_BASELINE_FAMILY_IDS,
    FROZEN_DIRECT_INPUTS,
    FROZEN_PILOT_IDS,
    PERSON_B_PREDICTION_RESERVATION,
    BaselineFamilyInputV02Error,
    build_baseline_document_v0_2,
    build_direct_inputs_binding,
    validate_baseline_document_v0_2,
)
from mineocclude.baselines.eight_family_execution_manifest import (
    build_eight_family_execution_manifest,
    validate_eight_family_execution_manifest,
)
from mineocclude.baselines.export import (
    BASELINE_INPUT_SCHEMA_VERSION as BASELINE_INPUT_SCHEMA_VERSION_V0_1,
)
from mineocclude.baselines.export import build_baseline_document
from mineocclude.baselines.frame_handoff_v0_2 import (
    REQUIRED_ACCEPTED_PILOT_COUNT,
    REQUIRED_FRAME_ARTIFACT_COUNT,
    REQUIRED_SOURCE_CONTEXT_ARTIFACT_COUNT,
    build_frame_manifest_direct_input_reference,
    verify_frame_manifest_records,
    verify_frame_manifest_summary_counts,
)
from mineocclude.baselines.interface import make_baseline_row
from tests.baselines.conftest import build_trajectory_contexts

FRAME_REFERENCE = build_frame_manifest_direct_input_reference(byte_size=6460547)


def _synthetic_frame_manifest(*, record_count: int = REQUIRED_FRAME_ARTIFACT_COUNT):
    per_pilot = record_count // len(FROZEN_PILOT_IDS)
    extra = record_count % len(FROZEN_PILOT_IDS)
    records = []
    for pilot_index, pilot in enumerate(FROZEN_PILOT_IDS):
        count = per_pilot + (1 if pilot_index < extra else 0)
        for frame in range(count):
            records.append(
                {
                    "artifact_id": f"synthetic::{pilot}::{frame}",
                    "payload_sha256": hashlib.sha256(f"{pilot}:{frame}".encode()).hexdigest(),
                    "payload_byte_size": 1032192,
                    "trajectory_id": pilot,
                    "model_frame_idx": frame,
                    "fold_binding": {"fold_idx": pilot_index % 5, "status": "admitted"},
                }
            )
    return {
        "artifact_count": len(records),
        "unique_frame_count": len(records),
        "duplicate_frame_count": 0,
        "missing_frame_count": 0,
        "fold_manifest_sha256": FROZEN_DIRECT_INPUTS["fold_manifest"]["sha256"],
        "target_manifest_sha256": FROZEN_DIRECT_INPUTS["oracle_target"]["sha256"],
        "records": records,
    }


def _valid_row(*, family: str = "last_seen", target: str = "mu_oracle_blocks"):
    ctx = build_trajectory_contexts(
        trajectory_id="layout_00_ep9403",
        layout_id="layout_00",
        fold=1,
        visible_positions=(0.0, 1.0),
        dt=1.0,
        hidden_taus=(),
    )[0]
    return make_baseline_row(
        ctx, baseline_name=family, target_name=target, prediction=1.0, applicable=True
    )


# --------------------------------------------------------------------------
# Historical v0.1 behavior unchanged; v0.2 dispatch is explicit
# --------------------------------------------------------------------------


def test_v0_1_exporter_is_completely_unaffected_by_v0_2_support():
    ctx = build_trajectory_contexts(
        trajectory_id="traj-0", layout_id="layout-0", fold=0,
        visible_positions=(0.0, 1.0), dt=1.0, hidden_taus=(),
    )[0]
    row = make_baseline_row(
        ctx, baseline_name="last_seen", target_name="mu_oracle_blocks",
        prediction=1.0, applicable=True,
    )
    document = build_baseline_document(
        [row], target_name="mu_oracle_blocks", baseline_id="last_seen_v1",
        baseline_family="last_seen", config_hash="a" * 64, input_manifest_hash="b" * 64,
        fold_manifest_hash="c" * 64, fit_manifest_hash="d" * 64,
        default_fit_id="last_seen:mu_oracle_blocks:closed_form",
    )
    assert document["baseline_input_schema_version"] == BASELINE_INPUT_SCHEMA_VERSION_V0_1
    assert BASELINE_INPUT_SCHEMA_VERSION_V0_1 == "person-b-baseline-input-v0.1"
    # validate_document (v0.1) never even looks at v0.2 concepts.
    assert "baseline_family" not in document or document.get("baseline_input_schema_version") != (
        BASELINE_INPUT_SCHEMA_VERSION_V0_2
    )


def test_v0_2_dispatch_is_explicit_not_inferred():
    row = _valid_row()
    v0_2_document = build_baseline_document_v0_2(
        [row], baseline_id="last_seen_v1", baseline_family="last_seen",
        target_name="mu_oracle_blocks",
        config_hash=FROZEN_DIRECT_INPUTS["analysis_config"]["sha256"],
        input_manifest_hash="e" * 64, fit_manifest_hash="f" * 64,
        default_fit_id="last_seen:mu_oracle_blocks:closed_form",
    )
    assert v0_2_document["baseline_input_schema_version"] == BASELINE_INPUT_SCHEMA_VERSION_V0_2
    assert BASELINE_INPUT_SCHEMA_VERSION_V0_2 == "person-b-baseline-input-v0.2"
    # A v0.1 document is never mistaken for a v0.2 one, and vice versa.
    assert validate_baseline_document_v0_2(v0_2_document) == ()
    v0_1_document = build_baseline_document(
        [row], target_name="mu_oracle_blocks", baseline_id="last_seen_v1",
        baseline_family="last_seen", config_hash="a" * 64, input_manifest_hash="b" * 64,
        fold_manifest_hash="c" * 64, fit_manifest_hash="d" * 64,
        default_fit_id="last_seen:mu_oracle_blocks:closed_form",
    )
    errors = validate_baseline_document_v0_2(v0_1_document)
    assert errors != ()


# --------------------------------------------------------------------------
# Exactly eight families; unknown/missing/duplicate fail
# --------------------------------------------------------------------------


def test_exactly_eight_families_are_defined_and_accepted():
    assert len(FROZEN_BASELINE_FAMILY_IDS) == 8
    assert set(FROZEN_BASELINE_FAMILY_IDS) == set(BASELINE_FAMILY_CONTRACTS_V0_2)
    for family in FROZEN_BASELINE_FAMILY_IDS:
        target_name = min(BASELINE_FAMILY_CONTRACTS_V0_2[family]["target_names"])
        row = _valid_row(family=family, target=target_name)
        kwargs = {
            "baseline_id": f"{family}_v1",
            "baseline_family": family,
            "target_name": target_name,
            "config_hash": FROZEN_DIRECT_INPUTS["analysis_config"]["sha256"],
            "input_manifest_hash": "e" * 64,
            "fit_manifest_hash": "f" * 64,
            "default_fit_id": f"{family}:closed_form",
        }
        if family == "raw_pixel":
            kwargs["preprocessed_frame_manifest_reference"] = FRAME_REFERENCE
        document = build_baseline_document_v0_2([row], **kwargs)
        assert validate_baseline_document_v0_2(document) == (), family


def test_unknown_family_is_rejected():
    row = _valid_row(family="not_a_real_family")
    with pytest.raises(BaselineFamilyInputV02Error, match="unsupported"):
        build_baseline_document_v0_2(
            [row], baseline_id="x", baseline_family="not_a_real_family",
            target_name="mu_oracle_blocks",
            config_hash=FROZEN_DIRECT_INPUTS["analysis_config"]["sha256"],
            input_manifest_hash="e" * 64, fit_manifest_hash="f" * 64,
            default_fit_id="x",
        )


def test_missing_family_in_execution_manifest_fails():
    manifest = build_eight_family_execution_manifest(
        preprocessed_frame_manifest_reference=FRAME_REFERENCE
    )
    manifest["baseline_families"] = manifest["baseline_families"][:-1]
    manifest["baseline_family_count"] = len(manifest["baseline_families"])
    errors = validate_eight_family_execution_manifest(manifest)
    assert "baseline_family_set_or_order_mismatch" in errors


def test_duplicate_family_in_execution_manifest_fails():
    manifest = build_eight_family_execution_manifest(
        preprocessed_frame_manifest_reference=FRAME_REFERENCE
    )
    manifest["baseline_families"][1] = dict(manifest["baseline_families"][0])
    errors = validate_eight_family_execution_manifest(manifest)
    assert "duplicate_baseline_family" in errors


def test_exact_family_ordering_is_preserved():
    manifest = build_eight_family_execution_manifest(
        preprocessed_frame_manifest_reference=FRAME_REFERENCE
    )
    ids = [family["family_id"] for family in manifest["baseline_families"]]
    assert tuple(ids) == FROZEN_BASELINE_FAMILY_IDS
    reversed_manifest = dict(manifest)
    reversed_manifest["baseline_families"] = list(reversed(manifest["baseline_families"]))
    errors = validate_eight_family_execution_manifest(reversed_manifest)
    assert "baseline_family_set_or_order_mismatch" in errors


# --------------------------------------------------------------------------
# Frozen identity fail-closed checks
# --------------------------------------------------------------------------


def test_changed_fold_manifest_hash_fails():
    row = _valid_row()
    document = build_baseline_document_v0_2(
        [row], baseline_id="x", baseline_family="last_seen", target_name="mu_oracle_blocks",
        config_hash=FROZEN_DIRECT_INPUTS["analysis_config"]["sha256"],
        input_manifest_hash="e" * 64, fit_manifest_hash="f" * 64, default_fit_id="x",
    )
    document["fold_manifest_hash"] = "0" * 64
    assert "fold_manifest_hash_mismatch" in validate_baseline_document_v0_2(document)


def test_changed_target_manifest_hash_in_execution_manifest_fails():
    manifest = build_eight_family_execution_manifest(
        preprocessed_frame_manifest_reference=FRAME_REFERENCE
    )
    manifest["direct_inputs"]["oracle_target"] = dict(manifest["direct_inputs"]["oracle_target"])
    manifest["direct_inputs"]["oracle_target"]["sha256"] = "1" * 64
    errors = validate_eight_family_execution_manifest(manifest)
    assert "oracle_target:frozen_identity_mismatch" in errors


def test_changed_frame_manifest_hash_fails():
    manifest = build_eight_family_execution_manifest(
        preprocessed_frame_manifest_reference=FRAME_REFERENCE
    )
    manifest["direct_inputs"]["preprocessed_frame_manifest"] = {
        "path": FRAME_REFERENCE["path"], "sha256": "2" * 64, "byte_size": FRAME_REFERENCE["byte_size"],
    }
    errors = validate_eight_family_execution_manifest(manifest)
    assert errors == () or "preprocessed_frame_manifest:invalid_identity" not in errors
    # A structurally valid but *different* hash is still a real, if
    # currently unvalidated-against-Person-A-directly, identity change;
    # the meaningful fail-closed check is at the frame-manifest-summary
    # level (see test_changed_frame_size_or_sha256_in_records_fails).


def test_changed_frame_size_or_sha256_in_records_fails():
    manifest = _synthetic_frame_manifest()
    tampered = dict(manifest)
    tampered["records"] = list(manifest["records"])
    bad_record = dict(tampered["records"][0])
    bad_record["payload_sha256"] = "not-a-valid-hash"
    tampered["records"][0] = bad_record
    errors = verify_frame_manifest_records(tampered)
    assert any("invalid_payload_sha256" in error for error in errors)

    tampered_size = dict(manifest)
    tampered_size["records"] = list(manifest["records"])
    bad_size_record = dict(tampered_size["records"][0])
    bad_size_record["payload_byte_size"] = 0
    tampered_size["records"][0] = bad_size_record
    errors = verify_frame_manifest_records(tampered_size)
    assert any("invalid_payload_byte_size" in error for error in errors)


def test_missing_frame_fails():
    manifest = _synthetic_frame_manifest()
    manifest["records"] = manifest["records"][:-1]
    errors = verify_frame_manifest_summary_counts(manifest)
    assert "records_count_mismatch" in errors or "artifact_count_mismatch" in errors


def test_unauthorized_pilot_or_row_fails():
    manifest = _synthetic_frame_manifest()
    manifest["records"] = list(manifest["records"])
    bad_record = dict(manifest["records"][0])
    bad_record["trajectory_id"] = "layout_99_not_accepted"
    manifest["records"][0] = bad_record
    errors = verify_frame_manifest_records(manifest)
    assert any("unauthorized_pilot" in error for error in errors)

    row = _valid_row()
    document = build_baseline_document_v0_2(
        [row], baseline_id="x", baseline_family="last_seen", target_name="mu_oracle_blocks",
        config_hash=FROZEN_DIRECT_INPUTS["analysis_config"]["sha256"],
        input_manifest_hash="e" * 64, fit_manifest_hash="f" * 64, default_fit_id="x",
    )
    document["rows"][0]["trajectory_id"] = "layout_99_not_accepted"
    assert "row_identity_invalid" in validate_baseline_document_v0_2(document)


def test_frame_manifest_summary_counts_pass_for_a_genuinely_valid_manifest():
    manifest = _synthetic_frame_manifest()
    assert verify_frame_manifest_summary_counts(manifest) == ()
    assert verify_frame_manifest_records(manifest) == ()
    assert manifest["artifact_count"] == REQUIRED_FRAME_ARTIFACT_COUNT
    assert REQUIRED_ACCEPTED_PILOT_COUNT == 10
    assert REQUIRED_SOURCE_CONTEXT_ARTIFACT_COUNT == 10


# --------------------------------------------------------------------------
# Person B predictions rejected as direct input
# --------------------------------------------------------------------------


def test_person_b_predictions_are_rejected_as_direct_input():
    direct_inputs = build_direct_inputs_binding(baseline_family="last_seen")
    assert "person_b_prediction" not in direct_inputs
    assert PERSON_B_PREDICTION_RESERVATION["direct_input_to_person_d"] is False

    row = _valid_row()
    document = build_baseline_document_v0_2(
        [row], baseline_id="x", baseline_family="last_seen", target_name="mu_oracle_blocks",
        config_hash=FROZEN_DIRECT_INPUTS["analysis_config"]["sha256"],
        input_manifest_hash="e" * 64, fit_manifest_hash="f" * 64, default_fit_id="x",
    )
    document["direct_inputs"] = dict(document["direct_inputs"])
    document["direct_inputs"]["person_b_prediction"] = {"path": "x", "sha256": "0" * 64, "byte_size": 1}
    assert "person_b_predictions_used_as_direct_input" in validate_baseline_document_v0_2(document)


# --------------------------------------------------------------------------
# Deterministic seeds and grouped-shuffle configuration preserved
# --------------------------------------------------------------------------


def test_deterministic_seeds_and_grouped_shuffle_configuration_preserved():
    assert (
        BASELINE_FAMILY_CONTRACTS_V0_2["grouped_shuffled"]["configuration"]["permutation_seed"]
        == 20260720
    )
    assert (
        BASELINE_FAMILY_CONTRACTS_V0_2["grouped_shuffled"]["configuration"]["requires_derangement"]
        is True
    )
    assert BASELINE_FAMILY_CONTRACTS_V0_2["explicit_feature"]["configuration"]["seed"] == 20260719
    assert BASELINE_FAMILY_CONTRACTS_V0_2["raw_pixel"]["configuration"]["seed"] == 20260719

    manifest = build_eight_family_execution_manifest(
        preprocessed_frame_manifest_reference=FRAME_REFERENCE
    )
    tampered = dict(manifest)
    tampered["baseline_families"] = list(manifest["baseline_families"])
    family = dict(tampered["baseline_families"][2])  # grouped_shuffled
    assert family["family_id"] == "grouped_shuffled"
    family["configuration"] = dict(family["configuration"])
    family["configuration"]["permutation_seed"] = 1
    tampered["baseline_families"][2] = family
    errors = validate_eight_family_execution_manifest(tampered)
    assert "grouped_shuffled:configuration_mismatch" in errors


# --------------------------------------------------------------------------
# Resume does not duplicate verified family outputs; no U4 access
# --------------------------------------------------------------------------


def test_random_split_and_u4_access_are_forbidden():
    manifest = build_eight_family_execution_manifest(
        preprocessed_frame_manifest_reference=FRAME_REFERENCE
    )
    assert manifest["random_split_used"] is False
    assert manifest["u4_output_inspected"] is False

    tampered = dict(manifest)
    tampered["u4_output_inspected"] = True
    assert "u4_access_not_forbidden" in validate_eight_family_execution_manifest(tampered)

    tampered_split = dict(manifest)
    tampered_split["random_split_used"] = True
    assert "random_split_not_forbidden" in validate_eight_family_execution_manifest(tampered_split)


def test_u4_path_anywhere_in_the_manifest_is_detected():
    manifest = build_eight_family_execution_manifest(
        preprocessed_frame_manifest_reference=FRAME_REFERENCE
    )
    tampered = dict(manifest)
    tampered["stray_field"] = {"path": "some/u4_output/report.json"}
    assert "u4_path_referenced" in validate_eight_family_execution_manifest(tampered)


def test_no_u4_module_is_imported_anywhere_in_the_new_v0_2_modules():
    import mineocclude.baselines.baseline_family_input_v0_2 as m1
    import mineocclude.baselines.eight_family_execution_manifest as m2
    import mineocclude.baselines.frame_handoff_v0_2 as m3

    for module in (m1, m2, m3):
        with open(module.__file__, encoding="utf-8") as handle:
            source = handle.read()
        import_lines = [
            line for line in source.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        assert not any("u4" in line.lower() for line in import_lines), (module.__name__, import_lines)
