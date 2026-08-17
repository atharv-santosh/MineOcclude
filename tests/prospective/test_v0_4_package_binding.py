"""The v0.4 package resolves its own inventory and refuses both closed ones.

v0.4 carries no new science -- its scientific delta against v0.3 is empty, and
``build_authority`` proves that at build time. What it carries is a *new unit
inventory*, made necessary because the v0.3 Stage-1 terminated in a scientific
FAIL and a terminal decision permanently closes its package's units.

That makes identity the whole of this package's job, so identity is what these
tests attack. Two inventories are now closed -- v0.2's ``a1q_*`` / 81xxx and
v0.3's ``a1x_*`` / 83xxx -- and neither may be reachable from a v0.4 entrypoint,
by argument, by default, or by fallback.

Nothing here authorizes Stage-2, and nothing here collects.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from mineocclude.prospective.development_workflow import (  # noqa: E402
    RUNTIME_CRITICAL_SOURCE_PATHS, bind_manifest, load_json,
    require_stage_manifest_binding,
)
from mineocclude.prospective.package_binding import (  # noqa: E402
    PackageBindingError, provenance_artifact_id_for, resolve_package_binding,
    stage1_decision_artifact_id,
)
from scripts.regime_a_prime_qualification_v0_4.build_authority import (  # noqa: E402
    SCIENTIFIC_SUBTREES, build_authority, require_scientific_fields_unchanged,
    scientific_delta,
)

#: The two closed inventories. Both terminated in a scientific FAIL.
CLOSED_UNIT_PREFIXES = ("a1q_", "a1x_")
CLOSED_EPISODE_RANGE = (81000, 84999)
CURRENT_UNIT_PREFIX = "a1y_"

V0_4_ENTRYPOINTS = tuple(
    path for path in RUNTIME_CRITICAL_SOURCE_PATHS
    if path.startswith("scripts/regime_a_prime_qualification_v0_4/"))


@pytest.fixture(scope="module")
def v0_4():
    return resolve_package_binding("v0.4", ROOT)


@pytest.fixture(scope="module")
def stage1(v0_4):
    return load_json(v0_4.stage1_manifest_path)


# ------------------------------------------------------------------ identity


def test_every_v0_4_identity_is_v0_4(v0_4):
    assert v0_4.authority_artifact_id == (
        "regime-a-prime-prospective-development-authority-v0.4")
    assert v0_4.stage1_manifest_artifact_id == "regime-a-prime-stage1-manifest-v0.4"
    assert v0_4.stage2_manifest_artifact_id == "regime-a-prime-stage2-locked-manifest-v0.4"
    assert v0_4.authorization_artifact_id == "regime-a-prime-stage1-authorization-v0.4"
    assert v0_4.provenance_artifact_id == provenance_artifact_id_for("v0.4")
    assert v0_4.run_namespace == "mineocclude-regime-a-prime-development-v0-4-stage1"
    assert v0_4.durable_prefix.endswith("prospective_development_v0_4/stage1")
    assert v0_4.authority_status == "DRAFT_PROSPECTIVE_UNFROZEN_NOT_AUTHORIZED"


def test_the_stage1_decision_identity_follows_the_package(stage1):
    """The repair in this same freeze, exercised on the new package."""
    assert stage1_decision_artifact_id(stage1) == "regime-a-prime-stage1-decision-v0.4"


def test_the_three_packages_share_no_identity_string():
    ids = []
    for version_tag in ("v0.2", "v0.3", "v0.4"):
        binding = resolve_package_binding(version_tag, ROOT)
        ids.append({binding.authority_artifact_id, binding.stage1_manifest_artifact_id,
                    binding.stage2_manifest_artifact_id, binding.authorization_artifact_id,
                    binding.provenance_artifact_id, binding.run_namespace,
                    binding.durable_prefix})
    for left in range(len(ids)):
        for right in range(left + 1, len(ids)):
            assert not ids[left] & ids[right]


# ----------------------------------------------------------------- inventory


def test_the_inventory_is_new_complete_and_correctly_designed(stage1):
    units = stage1["units"]
    assert len(units) == 8
    assert stage1["run_count"] == 8
    assert stage1["predecessor_units_reused"] is False
    assert stage1["predecessor_freeze_sha"] == "134a242981e3131c9c61d46b0f112234c8e83fce"
    cells = {(unit["direction"], unit["scene"], unit["design_role"]) for unit in units}
    assert cells == {(direction, scene, role)
                     for direction in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT")
                     for scene in ("WALL", "NO_WALL")
                     for role in ("TRANSITION_MEASUREMENT", "HELD_OUT_VALIDATION")}
    assert {unit["speed_blocks_per_second"] for unit in units} == {2.0}
    assert {unit["expected_frames"] for unit in units} == {180}


def test_no_closed_inventory_identity_is_reachable(stage1):
    """OLD_134A242_UNITS_REUSED=false, and the same for 560bc01."""
    serialized = json.dumps(stage1)
    for prefix in CLOSED_UNIT_PREFIXES:
        assert prefix not in serialized
    for unit in stage1["units"]:
        assert unit["unit_id"].startswith(CURRENT_UNIT_PREFIX)
        assert not CLOSED_EPISODE_RANGE[0] <= unit["episode_id"] <= CLOSED_EPISODE_RANGE[1]
        assert 85001 <= unit["episode_id"] <= 85008
    assert len({unit["episode_id"] for unit in stage1["units"]}) == 8
    assert len({unit["unit_id"] for unit in stage1["units"]}) == 8


def test_seed_equals_noise_seed_and_is_minted_from_the_unit_id(stage1):
    """One seed identity per unit; the server refuses to arm otherwise."""
    from scripts.regime_a_prime_qualification_v0_2.build_manifests import unit_seed

    for unit in stage1["units"]:
        assert unit["seed"] == unit["noise_seed"]
        assert unit["seed"] == unit_seed(unit["unit_id"])
    assert len({unit["seed"] for unit in stage1["units"]}) == 8


def test_receipt_and_capture_paths_are_disjoint_from_both_predecessors(stage1):
    for unit in stage1["units"]:
        assert "regime_a_prime_a1y_v0_4" in unit["receipt_path"]
        assert "a1x" not in unit["receipt_path"] and "a1q" not in unit["receipt_path"]


def test_units_are_locked_to_stage1_capture_of_this_package(stage1, v0_4):
    manifest_path = str(v0_4.stage1_manifest_path)
    for unit in stage1["units"]:
        command = unit["command"]
        assert command[command.index("--stage") + 1] == "stage1-capture"
        assert command[command.index("--unit-id") + 1] == unit["unit_id"]
        assert command[command.index("--manifest") + 1] == manifest_path
        # The unit driver is a shared implementation, deliberately not forked.
        assert "regime_a_prime_qualification_v0_2/stage_unit_driver.py" in command[1]
        assert unit["scientific_run_id"] == v0_4.run_namespace
        assert unit["confirmatory_membership"] is False


# ----------------------------------------------------------------- non-change


def test_the_scientific_delta_is_empty_and_proved_empty():
    assert scientific_delta() == {}
    source, authority = build_authority()
    # Does not raise: every scientific subtree survived the version sweep.
    require_scientific_fields_unchanged(source, authority)
    for subtree in SCIENTIFIC_SUBTREES:
        before, after = source, authority
        for key in subtree:
            before, after = before[key], after[key]
        assert json.dumps(before, sort_keys=True) == json.dumps(after, sort_keys=True)


def test_a_scientific_change_would_fail_the_build():
    """The proof is a real check, not an assertion that always holds."""
    source, authority = build_authority()
    tampered = json.loads(json.dumps(authority))
    tampered["stage1_policy"]["temporal_alignment"][
        "cross_correlation_subtick_refinement_bound_ticks"] = 2.0
    with pytest.raises(RuntimeError, match="scientific subtree"):
        require_scientific_fields_unchanged(source, tampered)


def test_v0_4_inherits_the_frozen_extent_and_temporal_rules(v0_4):
    authority = load_json(v0_4.authority_path)
    visibility = authority["stage1_policy"]["visibility"]
    temporal = authority["stage1_policy"]["temporal_alignment"]
    assert visibility["primary_predicate"] == (
        "extent_occlusion_geometry_over_rendered_target_extent")
    assert visibility["target_extent"]["half_width_blocks"] == 0.8727621336620037
    assert visibility["maximum_observed_false_positive_rate"] == 0.0
    assert visibility["maximum_observed_false_negative_rate"] == 0.0
    assert visibility["minimum_stable_samples_per_direction_per_class"] == 60
    assert temporal["cross_correlation_subtick_refinement_bound_ticks"] == 1.0
    assert temporal["maximum_lag_ticks_for_estimation"] == 8
    assert temporal["pure_delay_interpretation_allowed"] is False
    assert (authority["stage1_policy"]["contamination"][
        "designated_hidden_row_selection_rule"]
        == "FIRST_N_QUALIFIED_STABLE_OCCLUDED_ROWS_IN_ASCENDING_MODEL_FRAME_ORDER")
    assert authority["stage1_policy"]["contamination"][
        "required_hidden_rows_per_wall_validation_run"] == 19


def test_the_failed_trajectory_is_not_mentioned_or_excluded(v0_4):
    """The one real 134a242 measurement is neither accommodated nor hidden."""
    authority = load_json(v0_4.authority_path)
    change_log = authority["change_log"]
    assert change_log["OLD_FAILED_TRAJECTORY_EXCLUDED"] is False
    assert change_log["OUTCOME_DERIVED_TEMPORAL_EXCEPTION_ADDED"] is False
    assert change_log["UNIMODALITY_GATE_ADDED"] is False
    assert change_log["TEMPORAL_REFINEMENT_BOUND_CHANGED"] is False
    assert change_log["SCIENTIFIC_DELTA"] == "EMPTY"
    # The failing unit id may appear in the predecessor narrative, but never in
    # any rule the evaluator reads.
    assert "a1x_rtl_wall_r01" not in json.dumps(authority["stage1_policy"])


# --------------------------------------------------------------- entrypoints


def test_the_v0_4_execution_surface_exists_and_is_closure_bound():
    assert len(V0_4_ENTRYPOINTS) == 6
    for relative in V0_4_ENTRYPOINTS:
        assert (ROOT / relative).is_file(), relative


@pytest.mark.parametrize("module", ["development_controller", "generate_receipts",
                                    "verify_package", "acceptance_harness"])
def test_each_entrypoint_declares_v0_4_and_delegates_to_the_shared_implementation(module):
    text = (ROOT / f"scripts/regime_a_prime_qualification_v0_4/{module}.py").read_text()
    assert 'VERSION_TAG = "v0.4"' in text
    assert "from scripts.regime_a_prime_qualification_v0_2 import" in text
    assert 'VERSION_TAG = "v0.3"' not in text
    assert 'VERSION_TAG = "v0.2"' not in text


def test_the_v0_4_package_audit_passes_on_its_own_bytes():
    result = subprocess.run(
        [sys.executable, "scripts/regime_a_prime_qualification_v0_4/verify_package.py"],
        cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert "PACKAGE_VERSION=v0.4" in result.stdout
    assert "PACKAGE_CONSISTENCY_STATUS=PASS" in result.stdout
    assert "COLLECTION_AUTHORIZED=false" in result.stdout


# ------------------------------------------------------------- cross-version


def test_the_v0_4_stage_binding_refuses_a_predecessor_manifest(v0_4):
    """A v0.3 or v0.2 manifest cannot be run through the v0.4 authority."""
    authority = load_json(v0_4.authority_path)
    for version_tag in ("v0.2", "v0.3"):
        other = resolve_package_binding(version_tag, ROOT)
        stale = load_json(other.stage1_manifest_path)
        with pytest.raises((PermissionError, Exception)):
            require_stage_manifest_binding(
                "stage1-capture", stale, manifest_path=other.stage1_manifest_path,
                authority=authority, repository=ROOT)


def test_a_predecessor_manifest_cannot_bind_the_v0_4_authority(v0_4):
    """bind_manifest compares the manifest's recorded authority digest."""
    for version_tag in ("v0.2", "v0.3"):
        other = resolve_package_binding(version_tag, ROOT)
        stale = load_json(other.stage1_manifest_path)
        with pytest.raises(Exception):
            bind_manifest(v0_4.authority_path, stale)


def test_resolving_v0_4_against_a_tree_without_it_fails_closed(tmp_path):
    with pytest.raises(PackageBindingError):
        resolve_package_binding("v0.4", tmp_path)


# --------------------------------------------------------------- authorization


def test_stage2_is_not_preauthorized_by_this_package(v0_4):
    authority = load_json(v0_4.authority_path)
    stage1 = load_json(v0_4.stage1_manifest_path)
    stage2 = load_json(v0_4.stage2_manifest_path)
    assert authority["STAGE_1_COLLECTION_AUTHORIZED"] is False
    assert authority["STAGE_2_COLLECTION_AUTHORIZED"] is False
    assert authority["confirmatory_collection_authorized"] is False
    assert stage1["STAGE_1_COLLECTION_AUTHORIZED"] is False
    assert stage1["STAGE_2_COLLECTION_AUTHORIZED"] is False
    assert stage2["STAGE_2_COLLECTION_AUTHORIZED"] is False
    assert stage2["status"] == "DRAFT_TEMPLATE_AWAITING_STAGE1_TARGET_MATERIALIZATION"
    assert all(identity["target_window_status"]
               == "TO_BE_MATERIALIZED_FROM_FROZEN_STAGE1_DECISION"
               for identity in stage2["trajectory_identities"])
