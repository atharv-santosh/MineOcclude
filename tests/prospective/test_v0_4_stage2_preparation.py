"""Regime A' v0.4 Stage-2 preparation: materialization, producers, and refusals.

Stage 2 is the first rung that reads model activations, and until this module it
was unreachable in both directions. The launch barrier
``require_stage2_authorization`` existed and was tested only negatively; no
legitimate producer existed for the artifact it demands, so the only way to
satisfy it was to hand-author the receipt -- the exact failure this repository's
receipt generators were written to remove. And the Stage-2 manifest was still a
draft template: nothing had ever materialized its target windows from a Stage-1
decision, so no test had ever run the materializer against a real one.

Four groups, in the order the pipeline runs them:

* ``design``       -- what the materialized Stage-2 manifest must contain, read
                      against the frozen authority rather than restated;
* ``authority``    -- that v0.4 materializes against the *v0.4* authority, and
                      cannot silently fall back to v0.3's;
* ``producers``    -- that the Stage-2 provenance and authorization generators
                      derive their artifacts and that the real barrier accepts
                      the result;
* ``refusals``     -- one mutated binding at a time, each of which must fail
                      closed.

Nothing here authorizes the real campaign, collects data, starts a display, or
writes into an evidence directory. Every artifact is built in ``tmp_path``.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from mineocclude.prospective.development_workflow import (
    EvidenceError, Stage1Evaluator, canonical_json_bytes, canonical_payload_sha256,
    load_json, probe_evidence_digest, require_stage2_authorization,
    runtime_critical_source_closure_sha256, sha256_file, stage_run_inventory_sha256,
)
from mineocclude.prospective.extent_geometry import ExtentClass
from scripts.regime_a_prime_qualification_v0_2 import generate_receipts
from scripts.regime_a_prime_qualification_v0_3 import build_manifests as v0_3_manifests
from scripts.regime_a_prime_qualification_v0_4 import build_manifests as v0_4_manifests
from tests.prospective.test_provenance_authorization_and_stage_binding import runtime_receipt

ROOT = Path(__file__).resolve().parents[2]
PACKAGES = ROOT / "docs/status/integration/regime_a_prime_qualification_v0_1"
PACKAGE = PACKAGES / "prospective_development_authority_v0_4"
AUTHORITY_PATH = PACKAGE / "authority_parameters.json"
STAGE1_PATH = PACKAGE / "stage1_manifest.json"
STAGE2_PATH = PACKAGE / "stage2_locked_manifest.json"

#: The completed v0.4 Stage-1 campaign. Read-only, and outside the repository
#: because scientific evidence is never committed into the source tree -- the
#: same arrangement ``test_extent_geometry_v0_3`` uses for its predecessor.
FROZEN_CAMPAIGN = Path(
    "/home/sagemaker-user/mineocclude-stage1-successor-046b34a/"
    "collection_launch_01_20260817T225203Z")
FROZEN_DECISION = FROZEN_CAMPAIGN / "stage1_decision.json"
FROZEN_EVIDENCE = FROZEN_CAMPAIGN / "stage1_evidence.json"
#: That campaign's own frozen pre-outcome provenance receipt -- the authority
#: for which source actually ran at 046b34a, and therefore the only record a
#: later barrier may verify the campaign's evidence pins against. It sits one
#: level above the launch directory because it was frozen before collection.
FROZEN_STAGE1_PROVENANCE = FROZEN_CAMPAIGN.parent / "preoutcome_provenance.json"

STAGE2_AUTHORIZATION_ID = "regime-a-prime-stage2-post-stage1-authorization-v0.4"
MATERIALIZED = "POST_STAGE1_MATERIALIZED_AWAITING_SEPARATE_FREEZE_AND_AUTHORIZATION"


@pytest.fixture(scope="module")
def authority():
    return load_json(AUTHORITY_PATH)


@pytest.fixture(scope="module")
def stage2():
    return load_json(STAGE2_PATH)


@pytest.fixture(scope="module")
def stage1():
    return load_json(STAGE1_PATH)


# ======================================================================
# design -- the materialized Stage-2 manifest
# ======================================================================


def test_stage2_manifest_is_materialized_and_still_unauthorized(stage2):
    assert stage2["status"] == MATERIALIZED
    assert stage2["STAGE_2_COLLECTION_AUTHORIZED"] is False
    assert stage2["confirmatory_collection_authorized"] is False
    assert stage2["classification"] == "DEVELOPMENT_ONLY"
    assert stage2["post_stage1_authorization"] == {
        "required": True, "required_artifact_id": STAGE2_AUTHORIZATION_ID}


def test_stage2_carries_exactly_fifty_paired_captures(stage2, authority):
    policy = authority["stage2_policy"]
    identities = stage2["trajectory_identities"]
    captures = stage2["capture_units"]
    assert len(identities) == policy["paired_trajectory_identities"] == 25
    assert len(captures) == policy["scientific_capture_count"] == 50
    by_trajectory: dict[str, list[str]] = {}
    for unit in captures:
        by_trajectory.setdefault(unit["trajectory_id"], []).append(unit["scene"])
    assert set(by_trajectory) == {item["trajectory_id"] for item in identities}
    assert all(sorted(scenes) == ["NO_WALL", "WALL"] for scenes in by_trajectory.values())
    assert list(policy["scenes_per_identity"]) == ["WALL", "NO_WALL"]


def test_stage2_fold_and_phase_allocation_is_the_frozen_one(stage2, authority):
    policy = authority["stage2_policy"]
    identities = stage2["trajectory_identities"]
    assert sorted({item["outer_fold"] for item in identities}) == list(
        range(policy["outer_folds"])) == [0, 1, 2, 3, 4]
    assert sorted({item["phase_frames"] for item in identities}) == list(
        policy["phase_offsets_frames"]) == [0, 3, 6, 9, 12]
    # Every (fold, phase) cell is populated exactly once: 5 x 5 = 25.
    cells = [(item["outer_fold"], item["phase_frames"]) for item in identities]
    assert len(set(cells)) == len(cells) == 25


def test_every_capture_carries_nineteen_materialized_target_rows(stage2, authority):
    required = authority["stage2_policy"]["required_target_rows_per_capture"]
    assert required == 19
    for item in stage2["trajectory_identities"] + stage2["capture_units"]:
        assert item["target_window_status"] == "MATERIALIZED_FROM_STAGE1"
        assert len(item["target_model_frame_indices"]) == required
        assert len(item["expected_causal_fir_target_world_x_blocks"]) == required
        # Contiguous, and offset by this identity's frozen phase.
        indices = item["target_model_frame_indices"]
        assert indices == list(range(indices[0], indices[0] + required))


def test_target_rows_lie_inside_the_qualified_stable_occluded_extent(stage2, stage1, authority):
    """Every target is a hidden-position readout, by the frozen geometry itself.

    Scanned out of the extent engine rather than compared against a number typed
    here, so the fixture cannot encode a looser interval than the one Stage 1
    scored with.
    """
    evaluator = Stage1Evaluator(authority, stage1,
                                authority_sha256=sha256_file(AUTHORITY_PATH),
                                manifest_sha256=sha256_file(STAGE1_PATH))
    low, high = authority["apparatus"]["lane_world_x_blocks"]
    step = 0.001
    occluded = [low + index * step for index in range(int((high - low) / step) + 1)
                if evaluator.classify_extent_row(low + index * step, "WALL")
                is ExtentClass.EXTENT_FULLY_OCCLUDED]
    assert occluded
    occluded_low, occluded_high = min(occluded), max(occluded)
    targets = [value for item in stage2["trajectory_identities"]
               for value in item["expected_causal_fir_target_world_x_blocks"]]
    assert len(targets) == 25 * 19
    assert all(occluded_low <= value <= occluded_high for value in targets)


def test_stage2_extracts_layer_four_only_and_forbids_all_layers(stage2, authority):
    extraction = authority["stage2_policy"]["extraction"]
    assert extraction["all_layer_extraction_forbidden"] is True
    assert list(extraction["layers"]) == [4]
    assert {unit["layer"] for unit in stage2["extraction_units"]} == {4}
    assert len(stage2["extraction_units"]) == 50
    assert all(unit["pipeline_stage"] == "layer4_extraction"
               for unit in stage2["extraction_units"])
    assert stage2["pipeline_order"] == ["capture_and_durability", "physical_gates",
                                        "layer4_extraction", "best_k", "full", "terminal"]
    assert stage2["fail_closed_before_extraction"] is True


def test_stage2_remains_development_only_and_forbids_confirmatory_reuse(authority):
    post = authority["stage2_policy"]["post_stage2"]
    assert post["confirmatory_reuse_forbidden"] is True
    assert post["development_qualification_only"] is True
    assert post["may_authorize_confirmatory_collection"] is False
    assert authority["confirmatory_collection_authorized"] is False
    assert authority["confirmatory_interpretation_authorized"] is False


def test_stage2_temporal_labels_come_from_the_qualified_causal_fir(authority):
    labels = authority["stage2_policy"]["temporal_labels"]
    assert labels["source"] == "qualified_stage1_direction_specific_causal_fir"
    assert labels["raw_same_tick_server_state_forbidden"] is True


def test_stage2_inventory_is_a_fresh_86xxx_band_reusing_no_stage1_identity(stage2, stage1):
    episodes = [unit["episode_id"] for unit in stage2["capture_units"]]
    assert len(set(episodes)) == 50
    assert all(86000 < episode < 87000 for episode in episodes)
    trajectories = {item["trajectory_id"] for item in stage2["trajectory_identities"]}
    assert all(name.startswith("a2y_t") for name in trajectories)
    # No Stage-1 unit is reachable as a Stage-2 unit, and no closed-inventory
    # identity is reachable at all.
    stage1_units = {unit["unit_id"] for unit in stage1["units"]}
    stage1_episodes = {unit["episode_id"] for unit in stage1["units"]}
    stage2_units = {unit["unit_id"] for unit in stage2["units"]}
    assert stage1_units.isdisjoint(stage2_units)
    assert stage1_episodes.isdisjoint(set(episodes))
    # Closed *identities*, not implementation paths: the unit driver and the
    # Stage-2 backend deliberately live in the v0.2 scripts directory, because
    # they are the shared implementation every package parameterises. What must
    # be unreachable is a predecessor's units, episodes and namespaces.
    blob = json.dumps(stage2)
    for closed in ("a1y_", "a1x_", "a1q_", "a2x_", "a2q_",
                   "v0-2-stage", "v0-3-stage",
                   "prospective_development_authority_v0_2",
                   "prospective_development_authority_v0_3",
                   "prospective_development_v0_2", "prospective_development_v0_3"):
        assert closed not in blob, f"closed identity {closed!r} is reachable from Stage 2"
    assert stage2["run_namespace"] == "mineocclude-regime-a-prime-development-v0-4-stage2"
    assert stage2["durable_prefix"].endswith("prospective_development_v0_4/stage2")


def test_stage2_binds_the_frozen_stage1_pass_it_was_materialized_from(stage2, stage1):
    assert stage2["stage1_manifest_binding"] == sha256_file(STAGE1_PATH)
    assert stage2["authority_binding"]["sha256"] == sha256_file(AUTHORITY_PATH)
    assert len(stage2["stage1_evidence_sha256"]) == 64
    assert len(stage2["stage1_decision_sha256"]) == 64
    assert stage2["source_commit_binding"] == (
        "BOUND_AT_LAUNCH_BY_PREOUTCOME_PROVENANCE_RECEIPT")


# ======================================================================
# authority -- v0.4 materializes against v0.4
# ======================================================================


def _template(authority: dict) -> dict:
    return v0_4_manifests.build_stage2_template(
        sha256_file(AUTHORITY_PATH), sha256_file(STAGE1_PATH), authority)


@pytest.fixture(scope="module")
def frozen_decision():
    if not FROZEN_DECISION.is_file():
        pytest.skip(f"frozen v0.4 Stage-1 decision is absent: {FROZEN_DECISION}")
    return load_json(FROZEN_DECISION)


def test_materializer_has_no_authority_default_to_fall_back_to():
    """The defect was a default, not a wrong value: remove the default, remove it."""
    with pytest.raises(TypeError):
        v0_4_manifests.materialize_stage2({}, {})
    with pytest.raises(TypeError):
        v0_3_manifests.materialize_stage2({}, {})


def test_v0_4_materialization_follows_the_v0_4_authority_it_is_given(
        authority, frozen_decision):
    """A v0.4-only ``stage2_policy`` change must reach v0.4 materialization.

    This is the regression for the latent version-binding defect. The shared
    implementation used to read the v0.3 ``AUTHORITY`` constant, so a v0.4
    ``required_target_rows_per_capture`` of 11 would have been ignored and 19
    rows -- v0.3's number -- materialized instead.
    """
    mutated = deepcopy(authority)
    mutated["stage2_policy"]["required_target_rows_per_capture"] = 11
    result = v0_4_manifests.materialize_stage2(
        _template(mutated), deepcopy(frozen_decision), authority=mutated)
    assert {len(item["target_model_frame_indices"])
            for item in result["trajectory_identities"]} == {11}

    # And the unmutated v0.4 authority still gives the frozen 19, so the test
    # above is detecting the supplied authority rather than any authority.
    unchanged = v0_4_manifests.materialize_stage2(
        _template(authority), deepcopy(frozen_decision), authority=authority)
    assert {len(item["target_model_frame_indices"])
            for item in unchanged["trajectory_identities"]} == {19}


def test_v0_4_materialization_cannot_silently_read_the_v0_3_authority(
        authority, frozen_decision, monkeypatch):
    """Repointing the v0.3 module constant must not change a v0.4 materialization.

    ``v0_4_manifests.AUTHORITY`` is deliberately left alone: it still names the
    path the manifest records as its authority binding. What is repointed is the
    constant the shared implementation used to read, which is the one the defect
    consisted of reading.
    """
    monkeypatch.setattr(v0_3_manifests, "AUTHORITY",
                        PACKAGES / "prospective_development_authority_v0_2"
                        / "authority_parameters.json")
    result = v0_4_manifests.materialize_stage2(
        _template(authority), deepcopy(frozen_decision), authority=authority)
    assert result["status"] == MATERIALIZED
    assert {len(item["target_model_frame_indices"])
            for item in result["trajectory_identities"]} == {19}


def test_materialization_enforces_the_headroom_gate_of_the_supplied_authority(
        authority, frozen_decision):
    mutated = deepcopy(authority)
    mutated["stage2_policy"]["headroom"]["minimum_each_trajectory_target_sd_blocks"] = 99.0
    with pytest.raises(RuntimeError, match="headroom"):
        v0_4_manifests.materialize_stage2(
            _template(mutated), deepcopy(frozen_decision), authority=mutated)


def test_materialization_requires_a_stage1_pass(authority, frozen_decision):
    failed = deepcopy(frozen_decision)
    failed["status"] = "FAIL"
    with pytest.raises(RuntimeError, match="Stage-1 PASS"):
        v0_4_manifests.materialize_stage2(
            _template(authority), failed, authority=authority)


def test_materialization_refuses_a_decision_whose_two_intervals_disagree(
        authority, frozen_decision):
    """The reported summary and the row-derived measurement must still agree."""
    tampered = deepcopy(frozen_decision)
    detail = tampered["gates"]["prospective_transition_measurement"]["detail"]
    detail["reported"]["LEFT_TO_RIGHT"]["extent_fully_occluded_world_x_interval"] = [-1.0, 1.0]
    with pytest.raises(RuntimeError, match="disagrees with the reported"):
        v0_4_manifests.materialize_stage2(
            _template(authority), tampered, authority=authority)


def test_materialized_package_reproduces_the_committed_stage2_bytes(
        authority, frozen_decision, stage2):
    """The committed manifest is exactly what the materializer emits today."""
    result = v0_4_manifests.materialize_stage2(
        _template(authority), deepcopy(frozen_decision), authority=authority)
    assert json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n" == (
        STAGE2_PATH.read_text())
    assert result == stage2


# ======================================================================
# producers -- Stage-2 provenance and authorization
# ======================================================================


@pytest.fixture
def v0_4_binding():
    """Bind the shared receipt generator to v0.4, then put v0.2 back."""
    generate_receipts.bind_package(
        "v0.4", entrypoint="scripts/regime_a_prime_qualification_v0_4/generate_receipts.py")
    try:
        yield generate_receipts.BINDING
    finally:
        generate_receipts.bind_package(
            "v0.2", entrypoint="scripts/regime_a_prime_qualification_v0_2/generate_receipts.py")


@pytest.fixture
def clean_repository(monkeypatch):
    """Report the working tree as clean without touching it.

    The generators refuse a dirty repository, which is correct at freeze time
    and impossible to satisfy from a test run mid-change. Only ``git status`` is
    intercepted; ``rev-parse`` still returns the real HEAD, so every commit
    binding under test is the genuine one.
    """
    real = generate_receipts.git
    monkeypatch.setattr(generate_receipts, "git", lambda *args:
                        "" if args and args[0] == "status" else real(*args))
    return real


def stage2_provenance(tmp_path: Path, authority: dict, stage2: dict, **overrides) -> Path:
    """A Stage-2 pre-outcome provenance receipt whose bindings are genuinely correct.

    Built the same way the Stage-1 fixture in the sibling module is: only
    ``status`` and the commit-binding state are asserted rather than derived,
    because a real ``FROZEN_VERIFIED`` receipt cannot exist before the freeze.
    Everything the authorization generator reproduces is recomputed here from the
    artifacts the generator will recompute from.
    """
    probe = runtime_receipt(authority)
    execution = probe["probe_execution"]
    receipt = {
        "schema_version": "1.1",
        "artifact_id": "regime-a-prime-prospective-pre-outcome-provenance-v0.4",
        "classification": "DEVELOPMENT_ONLY", "status": "FROZEN_VERIFIED",
        "authority_sha256": sha256_file(AUTHORITY_PATH),
        "manifest_sha256": sha256_file(STAGE2_PATH),
        "stage1_manifest_sha256": sha256_file(STAGE1_PATH),
        "stage": "stage2-capture", "stage_role": "stage2",
        "run_namespace": stage2["run_namespace"],
        "run_inventory_sha256": stage_run_inventory_sha256(stage2),
        "runtime_critical_source_closure_sha256": runtime_critical_source_closure_sha256(ROOT),
        "runtime_identity_verified": True, "apparatus_identity_verified": True,
        "renderer_identity_verified": True,
        "source_paths_verified_bytes_and_modes": True,
        "remote_durable_prefix_read_write_probe_verified": True,
        "probe_evidence_sha256": probe_evidence_digest(execution),
        "probe_evidence_path_sha256": hashlib.sha256(canonical_json_bytes(probe)).hexdigest(),
        "probe_evidence": probe,
        "scientific_outcomes_observed": False,
        "confirmatory_collection_authorized": False,
        "independently_derived": True,
        "source_commit_binding_state": "BOUND_TO_FROZEN_COMMIT",
        "committed_bytes_equal_reviewed_bytes": True,
        "repository_clean_at_post_freeze_verification": True,
        "source_commit": generate_receipts.git("rev-parse", "HEAD"),
        "stage1_decision_sha256": sha256_file(FROZEN_DECISION),
        "stage1_evidence_sha256": sha256_file(FROZEN_EVIDENCE),
        "stage1_status": "PASS",
        "stage2_manifest_sha256": sha256_file(STAGE2_PATH),
        "stage2_run_inventory_sha256": stage_run_inventory_sha256(stage2),
        # Names the Stage-1 campaign whose PASS is being reused, so the
        # historical source authority cannot be swapped between the Stage-2
        # provenance and the Stage-2 authorization derived from it.
        "stage1_preoutcome_provenance_receipt_sha256":
            sha256_file(FROZEN_STAGE1_PROVENANCE),
        "all_layer_extraction_forbidden": True,
    }
    receipt.update(overrides)
    receipt["payload_sha256"] = canonical_payload_sha256(receipt)
    path = tmp_path / "stage2_provenance.json"
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return path


@pytest.fixture
def frozen_stage1_artifacts(frozen_decision):
    if not FROZEN_EVIDENCE.is_file():
        pytest.skip(f"frozen v0.4 Stage-1 evidence is absent: {FROZEN_EVIDENCE}")
    if not FROZEN_STAGE1_PROVENANCE.is_file():
        pytest.skip(f"frozen v0.4 Stage-1 provenance is absent: {FROZEN_STAGE1_PROVENANCE}")
    return FROZEN_DECISION, FROZEN_EVIDENCE


def authorize(tmp_path: Path, provenance: Path, decision: Path, evidence: Path,
              stage1_provenance: Path = FROZEN_STAGE1_PROVENANCE) -> Path:
    output = tmp_path / "stage2_authorization.json"
    assert generate_receipts.build_stage2_authorization(
        provenance, output, stage1_decision_path=decision,
        stage1_evidence_path=evidence,
        stage1_provenance_path=stage1_provenance) == 0
    return output


def test_stage2_producers_exist_as_receipt_generator_modes():
    """The blocker was a missing producer, not a missing barrier."""
    assert hasattr(generate_receipts, "build_stage2_provenance")
    assert hasattr(generate_receipts, "build_stage2_authorization")


def test_stage2_provenance_binds_the_stage2_manifest_not_the_stage1_one(
        tmp_path, v0_4_binding, authority, stage2, frozen_stage1_artifacts, monkeypatch):
    """The generator's own bindings, without running a live runtime probe."""
    decision, evidence = frozen_stage1_artifacts
    bindings = {**generate_receipts.stage1_pass_bindings(decision, evidence, FROZEN_STAGE1_PROVENANCE),
                **generate_receipts.stage2_manifest_bindings()}
    assert bindings["stage2_manifest_sha256"] == sha256_file(STAGE2_PATH)
    assert bindings["stage2_manifest_sha256"] != sha256_file(STAGE1_PATH)
    assert bindings["stage2_run_inventory_sha256"] == stage_run_inventory_sha256(stage2)
    assert bindings["stage2_run_namespace"] == stage2["run_namespace"]
    assert bindings["stage1_decision_sha256"] == sha256_file(decision)
    assert bindings["stage1_evidence_sha256"] == sha256_file(evidence)
    assert bindings["stage1_status"] == "PASS"
    assert bindings["stage1_decision_reproduced_from_evidence"] is True
    assert bindings["stage1_decision_artifact_id"] == "regime-a-prime-stage1-decision-v0.4"
    assert bindings["stage2_extraction_layers"] == [4]
    assert bindings["all_layer_extraction_forbidden"] is True
    assert bindings["confirmatory_reuse_forbidden"] is True
    assert bindings["stage2_scientific_capture_count"] == 50
    assert bindings["stage2_trajectory_identity_count"] == 25
    assert bindings["stage2_target_rows_per_capture"] == 19
    assert bindings["stage2_outer_folds"] == 5
    assert bindings["stage2_phase_offsets_frames"] == [0, 3, 6, 9, 12]
    assert len(bindings["stage2_capture_unit_ids"]) == 50


def test_stage2_manifest_bindings_refuse_an_unmaterialized_template(
        tmp_path, v0_4_binding, authority, monkeypatch):
    template = _template(authority)
    path = tmp_path / "stage2_locked_manifest.json"
    path.write_text(json.dumps(template, indent=2, sort_keys=True) + "\n")
    monkeypatch.setattr(generate_receipts, "STAGE2_MANIFEST_PATH", path)
    with pytest.raises(EvidenceError, match="not materialized"):
        generate_receipts.stage2_manifest_bindings()


def test_stage2_authorization_is_accepted_by_the_real_barrier(
        tmp_path, v0_4_binding, clean_repository, authority, stage2,
        frozen_stage1_artifacts):
    decision, evidence = frozen_stage1_artifacts
    provenance = stage2_provenance(tmp_path, authority, stage2)
    output = authorize(tmp_path, provenance, decision, evidence)
    receipt = load_json(output)

    assert receipt["artifact_id"] == STAGE2_AUTHORIZATION_ID
    assert receipt["schema_version"] == "1.1"
    assert receipt["status"] == "FROZEN_AUTHORIZED"
    assert receipt["STAGE_2_COLLECTION_AUTHORIZED"] is True
    assert receipt["STAGE_1_COLLECTION_AUTHORIZED"] is False
    assert receipt["confirmatory_collection_authorized"] is False
    assert receipt["confirmatory_interpretation_authorized"] is False
    assert receipt["stage1_status"] == "PASS"
    assert receipt["stage2_extraction_layers"] == [4]
    assert receipt["all_layer_extraction_forbidden"] is True
    assert receipt["authorization_payload_sha256"] == canonical_payload_sha256(
        receipt, omit="authorization_payload_sha256")

    # The barrier itself, run independently of the generator's own self-check.
    require_stage2_authorization(
        stage2, receipt, authorization_receipt_path=output,
        stage1_decision=load_json(decision), authority_path=AUTHORITY_PATH,
        manifest_path=STAGE2_PATH, stage1_manifest_path=STAGE1_PATH,
        stage1_decision_path=decision, stage1_evidence_path=evidence,
        current_source_commit=generate_receipts.git("rev-parse", "HEAD"),
        preoutcome_provenance_path=provenance,
        stage1_preoutcome_provenance_path=FROZEN_STAGE1_PROVENANCE)


def test_stage2_authorization_refuses_a_dirty_repository(
        tmp_path, v0_4_binding, authority, stage2, frozen_stage1_artifacts, monkeypatch):
    decision, evidence = frozen_stage1_artifacts
    provenance = stage2_provenance(tmp_path, authority, stage2)
    real = generate_receipts.git
    monkeypatch.setattr(generate_receipts, "git", lambda *args:
                        " M source.py" if args and args[0] == "status" else real(*args))
    with pytest.raises(EvidenceError, match="clean frozen repository"):
        authorize(tmp_path, provenance, decision, evidence)


def test_stage1_provenance_cannot_serve_as_stage2_provenance(
        tmp_path, v0_4_binding, clean_repository, authority, stage2,
        stage1, frozen_stage1_artifacts):
    decision, evidence = frozen_stage1_artifacts
    provenance = stage2_provenance(
        tmp_path, authority, stage2,
        stage="stage1-capture", stage_role="stage1",
        manifest_sha256=sha256_file(STAGE1_PATH),
        run_namespace=stage1["run_namespace"],
        run_inventory_sha256=stage_run_inventory_sha256(stage1))
    with pytest.raises(EvidenceError, match="prerequisites are unmet"):
        authorize(tmp_path, provenance, decision, evidence)


def test_stage2_provenance_from_another_package_is_refused(
        tmp_path, v0_4_binding, clean_repository, authority, stage2,
        frozen_stage1_artifacts):
    decision, evidence = frozen_stage1_artifacts
    provenance = stage2_provenance(
        tmp_path, authority, stage2,
        artifact_id="regime-a-prime-prospective-pre-outcome-provenance-v0.3")
    with pytest.raises(EvidenceError, match="prerequisites are unmet"):
        authorize(tmp_path, provenance, decision, evidence)


@pytest.mark.parametrize("field,value", [
    ("status", "PRE_FREEZE_VERIFIED"),
    ("authority_sha256", "a" * 64),
    ("stage2_manifest_sha256", "b" * 64),
    ("stage2_run_inventory_sha256", "c" * 64),
    ("runtime_critical_source_closure_sha256", "d" * 64),
    ("stage1_decision_sha256", "e" * 64),
    ("stage1_evidence_sha256", "f" * 64),
    ("source_commit", "0" * 40),
    ("runtime_identity_verified", False),
    ("remote_durable_prefix_read_write_probe_verified", False),
    ("scientific_outcomes_observed", True),
    ("confirmatory_collection_authorized", True),
    ("all_layer_extraction_forbidden", False),
])
def test_stage2_authorization_refuses_one_broken_provenance_binding_at_a_time(
        tmp_path, v0_4_binding, clean_repository, authority, stage2,
        frozen_stage1_artifacts, field, value):
    decision, evidence = frozen_stage1_artifacts
    provenance = stage2_provenance(tmp_path, authority, stage2, **{field: value})
    with pytest.raises(EvidenceError, match="prerequisites are unmet"):
        authorize(tmp_path, provenance, decision, evidence)
    assert not (tmp_path / "stage2_authorization.json").exists()


def test_stage2_authorization_refuses_a_rehashed_provenance_without_probe_evidence(
        tmp_path, v0_4_binding, clean_repository, authority, stage2,
        frozen_stage1_artifacts):
    decision, evidence = frozen_stage1_artifacts
    provenance = stage2_provenance(tmp_path, authority, stage2)
    receipt = load_json(provenance)
    del receipt["probe_evidence"]
    receipt["payload_sha256"] = canonical_payload_sha256(receipt, omit="payload_sha256")
    provenance.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    with pytest.raises(EvidenceError, match="no concrete probe evidence"):
        authorize(tmp_path, provenance, decision, evidence)


def test_stage2_authorization_refuses_an_edited_provenance_payload(
        tmp_path, v0_4_binding, clean_repository, authority, stage2,
        frozen_stage1_artifacts):
    decision, evidence = frozen_stage1_artifacts
    provenance = stage2_provenance(tmp_path, authority, stage2)
    receipt = load_json(provenance)
    receipt["generated_at_utc"] = "2000-01-01T00:00:00Z"
    provenance.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    with pytest.raises(EvidenceError, match="payload digest mismatch"):
        authorize(tmp_path, provenance, decision, evidence)


# ----------------------------------------------------------------------
# The two source identities are separate bindings, and both are checked.
#
# Making historical Stage-1 verification time-invariant must not have made
# Stage-2's own source unverified, and the two closures must not be
# interchangeable in either direction. The frozen Stage-1 closure is real,
# frozen, and correctly verified -- and still says nothing about the code
# Stage 2 is about to run.
# ----------------------------------------------------------------------


def test_stage2_source_is_still_verified_against_its_own_live_closure(
        tmp_path, v0_4_binding, clean_repository, authority, stage2,
        frozen_stage1_artifacts):
    """A Stage-2 provenance pinning any closure but the current one is refused."""
    decision, evidence = frozen_stage1_artifacts
    stale = stage2_provenance(
        tmp_path, authority, stage2,
        runtime_critical_source_closure_sha256=sha256_file(STAGE1_PATH))
    with pytest.raises(EvidenceError, match="prerequisites are unmet"):
        authorize(tmp_path, stale, decision, evidence)


def test_the_stage1_campaign_closure_cannot_serve_as_the_stage2_closure(
        tmp_path, v0_4_binding, clean_repository, authority, stage2,
        frozen_stage1_artifacts):
    """Requirement 3, stated as a substitution attempt.

    046b34a's closure is a genuine, frozen, fully verified closure -- and it is
    the wrong answer to "what is Stage 2 about to run". Supplying it as the
    Stage-2 closure must fail exactly as any other stale value does.
    """
    decision, evidence = frozen_stage1_artifacts
    campaign_closure = load_json(FROZEN_STAGE1_PROVENANCE)[
        "runtime_critical_source_closure_sha256"]
    assert campaign_closure != runtime_critical_source_closure_sha256(ROOT)
    smuggled = stage2_provenance(
        tmp_path, authority, stage2,
        runtime_critical_source_closure_sha256=campaign_closure)
    with pytest.raises(EvidenceError, match="prerequisites are unmet"):
        authorize(tmp_path, smuggled, decision, evidence)


def test_the_authorization_records_both_source_identities_distinctly(
        tmp_path, v0_4_binding, clean_repository, authority, stage2,
        frozen_stage1_artifacts):
    """Both bindings are written down, and they are not the same value."""
    decision, evidence = frozen_stage1_artifacts
    provenance = stage2_provenance(tmp_path, authority, stage2)
    receipt = load_json(authorize(tmp_path, provenance, decision, evidence))

    # Current: what Stage 2 will run, rehashed from the working tree.
    assert receipt["runtime_critical_source_closure_sha256"] == (
        runtime_critical_source_closure_sha256(ROOT))
    # Historical: what the reused Stage-1 PASS was collected under.
    campaign = load_json(FROZEN_STAGE1_PROVENANCE)
    assert receipt["stage1_runtime_critical_source_closure_sha256"] == (
        campaign["runtime_critical_source_closure_sha256"])
    assert receipt["stage1_source_commit"] == campaign["source_commit"]
    assert receipt["stage1_preoutcome_provenance_receipt_sha256"] == (
        sha256_file(FROZEN_STAGE1_PROVENANCE))
    # Distinct bindings, distinct values.
    assert (receipt["runtime_critical_source_closure_sha256"]
            != receipt["stage1_runtime_critical_source_closure_sha256"])
    assert (receipt["preoutcome_provenance_receipt_sha256"]
            != receipt["stage1_preoutcome_provenance_receipt_sha256"])


def test_the_barrier_refuses_a_swapped_stage1_campaign_provenance(
        tmp_path, v0_4_binding, clean_repository, authority, stage2,
        frozen_stage1_artifacts):
    """A predecessor campaign's real receipt cannot supply the historical closure."""
    decision, evidence = frozen_stage1_artifacts
    foreign = (FROZEN_CAMPAIGN.parent.parent / "mineocclude-stage1-successor-134a242"
               / "pre_outcome_provenance_receipt.json")
    if not foreign.is_file():
        pytest.skip(f"predecessor receipt is absent: {foreign}")
    provenance = stage2_provenance(tmp_path, authority, stage2)
    with pytest.raises(EvidenceError):
        authorize(tmp_path, provenance, decision, evidence, stage1_provenance=foreign)


def test_the_barrier_refuses_a_mutated_stage1_campaign_provenance(
        tmp_path, v0_4_binding, clean_repository, authority, stage2,
        frozen_stage1_artifacts):
    """Requirement 7, through the real producer rather than the binder alone."""
    decision, evidence = frozen_stage1_artifacts
    tampered = load_json(FROZEN_STAGE1_PROVENANCE)
    tampered["source_bindings"][
        "src/mineocclude/prospective/development_workflow.py"]["sha256"] = "f" * 64
    tampered.pop("payload_sha256", None)
    tampered["payload_sha256"] = canonical_payload_sha256(tampered)
    path = tmp_path / "mutated_stage1_provenance.json"
    path.write_text(json.dumps(tampered, indent=2, sort_keys=True) + "\n")
    provenance = stage2_provenance(tmp_path, authority, stage2)
    with pytest.raises(EvidenceError, match="does not reproduce from its inventory"):
        authorize(tmp_path, provenance, decision, evidence, stage1_provenance=path)


# ======================================================================
# refusals -- the Stage-1 PASS the barrier is tied to
# ======================================================================


def _decision_copy(tmp_path: Path, decision: dict, name: str = "decision.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(decision, sort_keys=True, separators=(",", ":"),
                               allow_nan=False) + "\n")
    return path


def test_the_frozen_v0_4_pass_satisfies_the_stage1_portion_of_the_barrier(
        tmp_path, v0_4_binding, frozen_stage1_artifacts):
    decision, evidence = frozen_stage1_artifacts
    bindings = generate_receipts.stage1_pass_bindings(decision, evidence, FROZEN_STAGE1_PROVENANCE)
    assert bindings["stage1_status"] == "PASS"
    assert bindings["stage1_decision_artifact_id"] == "regime-a-prime-stage1-decision-v0.4"


@pytest.mark.parametrize("artifact_id", [
    "regime-a-prime-stage1-decision-v0.2",
    "regime-a-prime-stage1-decision-v0.3",
])
def test_v0_4_stage2_refuses_a_predecessor_stage1_decision(
        tmp_path, v0_4_binding, frozen_decision, frozen_stage1_artifacts, artifact_id):
    _, evidence = frozen_stage1_artifacts
    foreign = deepcopy(frozen_decision)
    foreign["artifact_id"] = artifact_id
    with pytest.raises(EvidenceError, match="this package requires"):
        generate_receipts.stage1_pass_bindings(
            _decision_copy(tmp_path, foreign), evidence,
            FROZEN_STAGE1_PROVENANCE)


def test_v0_4_stage2_refuses_a_synthetic_fail_decision(
        tmp_path, v0_4_binding, frozen_decision, frozen_stage1_artifacts):
    _, evidence = frozen_stage1_artifacts
    failed = deepcopy(frozen_decision)
    failed["status"] = "FAIL"
    failed["reasons"] = ["unit_completeness"]
    with pytest.raises(EvidenceError, match="Stage-1 PASS"):
        generate_receipts.stage1_pass_bindings(
            _decision_copy(tmp_path, failed), evidence,
            FROZEN_STAGE1_PROVENANCE)


def test_v0_4_stage2_refuses_a_decision_with_one_gate_flipped_to_fail(
        tmp_path, v0_4_binding, frozen_decision, frozen_stage1_artifacts):
    _, evidence = frozen_stage1_artifacts
    tampered = deepcopy(frozen_decision)
    tampered["gates"]["hidden_row_contamination"]["status"] = "FAIL"
    with pytest.raises(EvidenceError, match="not reproduced"):
        generate_receipts.stage1_pass_bindings(
            _decision_copy(tmp_path, tampered), evidence,
            FROZEN_STAGE1_PROVENANCE)


def test_v0_4_stage2_refuses_a_decision_with_renamed_gates(
        tmp_path, v0_4_binding, frozen_decision, frozen_stage1_artifacts):
    _, evidence = frozen_stage1_artifacts
    tampered = deepcopy(frozen_decision)
    tampered["gates"]["a_gate_that_does_not_exist"] = tampered["gates"].pop(
        "unit_completeness")
    with pytest.raises(EvidenceError, match="not reproduced"):
        generate_receipts.stage1_pass_bindings(
            _decision_copy(tmp_path, tampered), evidence,
            FROZEN_STAGE1_PROVENANCE)


def test_v0_4_stage2_refuses_a_decision_with_a_wrong_evidence_digest(
        tmp_path, v0_4_binding, frozen_decision, frozen_stage1_artifacts):
    _, evidence = frozen_stage1_artifacts
    tampered = deepcopy(frozen_decision)
    tampered["stage1_evidence_sha256"] = "0" * 64
    with pytest.raises(EvidenceError, match="does not bind the supplied evidence"):
        generate_receipts.stage1_pass_bindings(
            _decision_copy(tmp_path, tampered), evidence,
            FROZEN_STAGE1_PROVENANCE)


@pytest.mark.parametrize("field", ["authority_sha256", "stage1_manifest_sha256"])
def test_v0_4_stage2_refuses_a_decision_bound_to_another_package(
        tmp_path, v0_4_binding, frozen_decision, frozen_stage1_artifacts, field):
    _, evidence = frozen_stage1_artifacts
    tampered = deepcopy(frozen_decision)
    tampered[field] = "9" * 64
    with pytest.raises(EvidenceError, match="binding mismatch"):
        generate_receipts.stage1_pass_bindings(
            _decision_copy(tmp_path, tampered), evidence,
            FROZEN_STAGE1_PROVENANCE)


def test_v0_4_stage2_refuses_a_confirmatory_escalation(
        tmp_path, v0_4_binding, frozen_decision, frozen_stage1_artifacts):
    _, evidence = frozen_stage1_artifacts
    escalated = deepcopy(frozen_decision)
    escalated["confirmatory_interpretation_authorized"] = True
    escalated["stage2_collection_authorized"] = True
    with pytest.raises(EvidenceError, match="not reproduced"):
        generate_receipts.stage1_pass_bindings(
            _decision_copy(tmp_path, escalated), evidence,
            FROZEN_STAGE1_PROVENANCE)


def test_the_barrier_refuses_a_predecessor_stage2_authorization(
        tmp_path, v0_4_binding, clean_repository, authority, stage2,
        frozen_stage1_artifacts):
    decision, evidence = frozen_stage1_artifacts
    provenance = stage2_provenance(tmp_path, authority, stage2)
    output = authorize(tmp_path, provenance, decision, evidence)
    for foreign in ("regime-a-prime-stage2-post-stage1-authorization-v0.2",
                    "regime-a-prime-stage2-post-stage1-authorization-v0.3"):
        receipt = load_json(output)
        receipt["artifact_id"] = foreign
        receipt["authorization_payload_sha256"] = canonical_payload_sha256(
            receipt, omit="authorization_payload_sha256")
        path = tmp_path / "foreign_authorization.json"
        path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        with pytest.raises(PermissionError, match="authorization is invalid"):
            require_stage2_authorization(
                stage2, receipt, authorization_receipt_path=path,
                stage1_decision=load_json(decision), authority_path=AUTHORITY_PATH,
                manifest_path=STAGE2_PATH, stage1_manifest_path=STAGE1_PATH,
                stage1_decision_path=decision, stage1_evidence_path=evidence,
                current_source_commit=generate_receipts.git("rev-parse", "HEAD"),
                preoutcome_provenance_path=provenance,
                stage1_preoutcome_provenance_path=FROZEN_STAGE1_PROVENANCE)


def test_the_barrier_refuses_an_unmaterialized_stage2_manifest(
        tmp_path, v0_4_binding, clean_repository, authority, stage2,
        frozen_stage1_artifacts):
    decision, evidence = frozen_stage1_artifacts
    provenance = stage2_provenance(tmp_path, authority, stage2)
    output = authorize(tmp_path, provenance, decision, evidence)
    template = _template(authority)
    with pytest.raises(PermissionError, match="no materialized target windows"):
        require_stage2_authorization(
            template, load_json(output), authorization_receipt_path=output,
            stage1_decision=load_json(decision), authority_path=AUTHORITY_PATH,
            manifest_path=STAGE2_PATH, stage1_manifest_path=STAGE1_PATH,
            stage1_decision_path=decision, stage1_evidence_path=evidence,
            current_source_commit=generate_receipts.git("rev-parse", "HEAD"),
            preoutcome_provenance_path=provenance,
            stage1_preoutcome_provenance_path=FROZEN_STAGE1_PROVENANCE)


def test_the_barrier_refuses_the_wrong_packages_stage2_manifest(
        tmp_path, v0_4_binding, clean_repository, authority, stage2,
        frozen_stage1_artifacts):
    decision, evidence = frozen_stage1_artifacts
    provenance = stage2_provenance(tmp_path, authority, stage2)
    output = authorize(tmp_path, provenance, decision, evidence)
    foreign = load_json(PACKAGES / "prospective_development_authority_v0_3"
                        / "stage2_locked_manifest.json")
    with pytest.raises(PermissionError):
        require_stage2_authorization(
            foreign, load_json(output), authorization_receipt_path=output,
            stage1_decision=load_json(decision), authority_path=AUTHORITY_PATH,
            manifest_path=STAGE2_PATH, stage1_manifest_path=STAGE1_PATH,
            stage1_decision_path=decision, stage1_evidence_path=evidence,
            current_source_commit=generate_receipts.git("rev-parse", "HEAD"),
            preoutcome_provenance_path=provenance,
            stage1_preoutcome_provenance_path=FROZEN_STAGE1_PROVENANCE)


@pytest.mark.parametrize("field,value", [
    ("authority_sha256", "a" * 64),
    ("stage1_manifest_sha256", "b" * 64),
    ("stage1_decision_sha256", "c" * 64),
    ("stage2_manifest_sha256", "d" * 64),
    ("stage1_evidence_sha256", "e" * 64),
    ("source_commit_sha", "f" * 40),
    ("expected_run_namespace", "mineocclude-regime-a-prime-development-v0-3-stage2"),
    ("preoutcome_provenance_receipt_sha256", "0" * 64),
    ("stage1_status", "FAIL"),
    ("STAGE_2_COLLECTION_AUTHORIZED", False),
    ("confirmatory_collection_authorized", True),
    ("status", "DRAFT"),
])
def test_the_barrier_refuses_one_broken_authorization_binding_at_a_time(
        tmp_path, v0_4_binding, clean_repository, authority, stage2,
        frozen_stage1_artifacts, field, value):
    decision, evidence = frozen_stage1_artifacts
    provenance = stage2_provenance(tmp_path, authority, stage2)
    receipt = load_json(authorize(tmp_path, provenance, decision, evidence))
    receipt[field] = value
    receipt["authorization_payload_sha256"] = canonical_payload_sha256(
        receipt, omit="authorization_payload_sha256")
    path = tmp_path / "mutated_authorization.json"
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    with pytest.raises(PermissionError):
        require_stage2_authorization(
            stage2, receipt, authorization_receipt_path=path,
            stage1_decision=load_json(decision), authority_path=AUTHORITY_PATH,
            manifest_path=STAGE2_PATH, stage1_manifest_path=STAGE1_PATH,
            stage1_decision_path=decision, stage1_evidence_path=evidence,
            current_source_commit=generate_receipts.git("rev-parse", "HEAD"),
            preoutcome_provenance_path=provenance,
            stage1_preoutcome_provenance_path=FROZEN_STAGE1_PROVENANCE)


def test_stage2_is_not_authorized_by_the_frozen_package_itself(authority, stage2):
    """Nothing committed in this package authorizes Stage 2 on its own."""
    assert authority["STAGE_2_COLLECTION_AUTHORIZED"] is False
    assert authority["REGIME_A_PRIME_COLLECTION_AUTHORIZED"] == "NO"
    assert stage2["STAGE_2_COLLECTION_AUTHORIZED"] is False
    assert not (PACKAGE / "stage2_authorization.json").exists()
