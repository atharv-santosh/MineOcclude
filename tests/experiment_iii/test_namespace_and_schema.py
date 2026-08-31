"""I01 — namespace isolation and the authority 4.4 row schema.

Covers the two task-graph tests for I01 plus the namespace half of A.30.
"""

from __future__ import annotations

import json

import pytest

from mineocclude.experiment_iii import authority
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.namespace import (
    guard_write_path,
    is_experiment_iii_path,
)
from mineocclude.experiment_iii.schema import (
    ConditionId,
    VISIBILITY_ROW_FIELDS,
    VisibilityRow,
    assert_not_a_selector,
    capture_unit_id,
    episode_dir_name,
    episode_id_for,
    validate_identity_id,
    write_json_atomic,
)


def _row(**overrides):
    base = {
        "model_frame_idx": 48,
        "condition_id": "L2",
        "wall_present": True,
        "wall_block_id": "minecraft:lime_stained_glass",
        "counterfactual_extent_class": "EXTENT_FULLY_OCCLUDED",
        "server_geometric_status": "occluded",
        "magenta_status": "detected",
        "magenta_area_pixels": 411,
        "rve_condition_score": 0.425,
        "target_eligible": True,
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# Namespace isolation
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "relative",
    [
        "docs/experiment_iii/cohort/production_identity_manifest.jsonl",
        "data/experiment_iii/captures/e3_t01__L0/wall_receipt.json",
        "tests/experiment_iii/fixtures/x.json",
    ],
)
def test_experiment_iii_roots_are_writable(relative):
    assert is_experiment_iii_path(relative)
    assert guard_write_path(relative).is_absolute()


@pytest.mark.parametrize(
    "relative",
    [
        "docs/status/integration/whatever.json",
        "data/regime_a/t01/coordinates.jsonl",
        "src/mineocclude/regime_a.py",
        "src/mineocclude/prospective/extent_geometry.py",
        "preauthority_creation_inputs/anything.json",
        "README.md",
    ],
)
def test_historical_paths_are_refused(relative):
    with pytest.raises(ExperimentIIIError) as caught:
        guard_write_path(relative)
    assert caught.value.blocker == "PROVENANCE_NAMESPACE_VIOLATION"


def test_frozen_authority_subtree_is_immutable():
    with pytest.raises(ExperimentIIIError) as caught:
        guard_write_path(
            "docs/experiment_iii/final_authorities/"
            "EXPERIMENT_III_PREIMPLEMENTATION_AUTHORITY.md"
        )
    assert caught.value.blocker == "PROVENANCE_NAMESPACE_VIOLATION"


def test_traversal_out_of_the_namespace_is_refused():
    with pytest.raises(ExperimentIIIError):
        guard_write_path("docs/experiment_iii/../status/escape.json")


def test_absolute_path_outside_the_repository_is_refused(tmp_path):
    with pytest.raises(ExperimentIIIError):
        guard_write_path(tmp_path / "escape.json")


def test_guarded_writer_refuses_and_writes_nothing(tmp_path):
    target = tmp_path / "docs" / "status" / "x.json"
    with pytest.raises(ExperimentIIIError):
        write_json_atomic(target, {"a": 1})
    assert not target.exists()


def test_guarded_writer_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(authority, "REPOSITORY_ROOT", tmp_path)
    import mineocclude.experiment_iii.namespace as namespace_module

    monkeypatch.setattr(namespace_module, "REPOSITORY_ROOT", tmp_path)
    target = tmp_path / "docs" / "experiment_iii" / "smoke.json"
    digest = write_json_atomic(target, {"b": 2, "a": 1})
    assert digest == authority.canonical_sha256({"a": 1, "b": 2})
    assert json.loads(target.read_text()) == {"a": 1, "b": 2}
    assert not target.with_name(target.name + ".tmp").exists()


# --------------------------------------------------------------------------
# Row schema (authority 4.4)
# --------------------------------------------------------------------------

def test_row_schema_field_set_matches_authority():
    machine = authority.machine_authority()["visibility_semantics"]["row_fields"]
    assert list(VISIBILITY_ROW_FIELDS) == list(machine)


def test_row_round_trips_and_keeps_five_fields_separate():
    row = VisibilityRow.from_mapping(_row())
    payload = row.to_dict()
    for field in VISIBILITY_ROW_FIELDS:
        assert field in payload
    # Physical presence, counterfactual geometry, image evidence and eligibility
    # are independent: an occluded counterfactual row can still show magenta.
    assert payload["counterfactual_extent_class"] == "EXTENT_FULLY_OCCLUDED"
    assert payload["magenta_status"] == "detected"
    assert payload["target_eligible"] is True


def test_missing_required_field_is_rejected_not_defaulted():
    incomplete = _row()
    del incomplete["rve_condition_score"]
    with pytest.raises(ExperimentIIIError) as caught:
        VisibilityRow.from_mapping(incomplete)
    assert caught.value.blocker == "PROVENANCE_BINDING_MISSING"


def test_condition_presence_must_agree_with_the_condition():
    with pytest.raises(ExperimentIIIError) as caught:
        VisibilityRow.from_mapping(_row(condition_id="L0", wall_present=True))
    assert caught.value.blocker == "WALL_CONDITION_SCENE_MISMATCH"


def test_l0_row_is_valid_with_air_and_no_wall():
    row = VisibilityRow.from_mapping(
        _row(
            condition_id="L0",
            wall_present=False,
            wall_block_id="minecraft:air",
            server_geometric_status="visible",
            rve_condition_score=1.0,
        )
    )
    assert ConditionId(row.condition_id).expected_scene == "NO_WALL"


@pytest.mark.parametrize(
    "field",
    [
        "server_geometric_status",
        "magenta_status",
        "magenta_area_pixels",
        "rve_condition_score",
    ],
)
def test_diagnostic_fields_are_refused_as_selectors(field):
    with pytest.raises(ExperimentIIIError) as caught:
        assert_not_a_selector(field)
    assert caught.value.blocker == "TARGET_LEGACY_SELECTOR_PRESENT"


def test_counterfactual_extent_class_is_an_admissible_selector():
    assert_not_a_selector("counterfactual_extent_class")


# --------------------------------------------------------------------------
# Identity namespace (authority 0.4, 8.2)
# --------------------------------------------------------------------------

def test_identity_namespace_and_episode_block():
    assert validate_identity_id("e3_t01") == "e3_t01"
    assert episode_id_for("e3_t01", 0) == 86001
    assert episode_id_for("e3_t25", 24) == 86025
    assert episode_id_for("e3_p90") == 86901
    assert episode_id_for("e3_p91") == 86902
    assert capture_unit_id("e3_t07", "L2") == "e3_t07__L2"
    assert episode_dir_name(86007, ConditionId.L2) == "episode_86007_L2"


def test_historical_identities_are_not_experiment_iii_identities():
    for foreign in ("t01", "regime_a_v1_t01", "a2x_t01"):
        with pytest.raises(ExperimentIIIError):
            validate_identity_id(foreign)


def test_pilot_is_refused_where_production_only_is_allowed():
    with pytest.raises(ExperimentIIIError) as caught:
        validate_identity_id("e3_p90", allow_pilot=False)
    assert caught.value.blocker == "COHORT_PILOT_CONTAMINATION"


def test_episode_ids_are_disjoint_from_historical_blocks():
    low, high = authority.EPISODE_ID_BLOCK
    assert (low, high) == (86001, 86999)
    # A-prime 81000-85999 and Regime A 51001+ must not intersect.
    assert low > 85999
    for rank in range(authority.PRODUCTION_IDENTITY_COUNT):
        assert low <= episode_id_for(f"e3_t{rank + 1:02d}", rank) <= high


def test_authority_binding_is_frozen():
    bound = authority.verify_authority_binding()
    assert bound["AUTHORITY_SHA256"] == authority.FROZEN_AUTHORITY_SHA256
    assert (
        bound["MACHINE_AUTHORITY_SHA256"] == authority.FROZEN_MACHINE_AUTHORITY_SHA256
    )
    assert bound["PHASE0_DESIGN_SHA256"] == authority.FROZEN_PHASE0_DESIGN_SHA256


def test_master_salt_is_derived_from_the_authority_bytes():
    import hashlib

    expected = hashlib.sha256(
        (
            "MINEOCCLUDE_EXPERIMENT_III_V1|"
            + authority.FROZEN_AUTHORITY_SHA256
            + "|"
            + authority.FROZEN_PHASE0_DESIGN_SHA256
        ).encode()
    ).hexdigest()
    assert authority.master_salt() == expected
