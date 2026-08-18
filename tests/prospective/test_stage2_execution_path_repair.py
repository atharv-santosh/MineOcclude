"""Regression suite for the Stage-2 execution-path repair.

One test class per audited defect. Each opens with the ORIGINAL failure so the
test states what it protects, then proves the repair, then proves the repair did
not weaken the control it replaced -- that last part matters most, because every
one of these defects sits on a fail-closed path where "make it stop raising" is
the wrong fix.
"""

from __future__ import annotations

import copy
import json
import random
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts/regime_a_prime_qualification_v0_1")]

from mineocclude.prospective.development_workflow import (  # noqa: E402
    DurableController, EvidenceError, RUNTIME_CRITICAL_SOURCE_PATHS, campaign_source_commit,
    capture_layout_value, durable_unit_uri, load_json, require_stage2_lifecycle_coherence,
    runtime_scene_value, sha256_file, stage1_transition_measurement,
    transition_band_intervals, transition_occluded_interval,
)
from mineocclude.prospective import unit1_checkpoint as cp  # noqa: E402

PACKAGE = ROOT / ("docs/status/integration/regime_a_prime_qualification_v0_1/"
                  "prospective_development_authority_v0_4")
AUTHORITY_PATH = PACKAGE / "authority_parameters.json"
STAGE1_MANIFEST_PATH = PACKAGE / "stage1_manifest.json"
STAGE2_MANIFEST_PATH = PACKAGE / "stage2_locked_manifest.json"

CAMPAIGN = Path("/home/sagemaker-user/mineocclude-stage1-successor-046b34a")
FROZEN_DECISION = CAMPAIGN / "collection_launch_01_20260817T225203Z/stage1_decision.json"
FROZEN_PROVENANCE = CAMPAIGN / "preoutcome_provenance.json"

requires_campaign = pytest.mark.skipif(
    not FROZEN_DECISION.is_file(), reason="frozen v0.4 Stage-1 campaign artifacts are not present")


@pytest.fixture(scope="module")
def authority() -> dict:
    return load_json(AUTHORITY_PATH)


@pytest.fixture(scope="module")
def stage2() -> dict:
    return load_json(STAGE2_MANIFEST_PATH)


@pytest.fixture(scope="module")
def decision() -> dict:
    return load_json(FROZEN_DECISION)


# ======================================================================
# B003 -- transition schema
# ======================================================================

class TestTransitionSchema:
    """Original failure: ``detail[direction]`` raised ``KeyError: 'LEFT_TO_RIGHT'``.

    The gate detail has been ``{"reported": ..., "derived_from_rows": ...}``
    since the 046b34a builder synchronization, and the v0.3 extent repair
    additionally removed the three field names the consumer read out of it.
    """

    @requires_campaign
    @pytest.mark.parametrize("direction", ["LEFT_TO_RIGHT", "RIGHT_TO_LEFT"])
    def test_current_v0_4_decision_resolves_both_directions(self, decision, direction):
        measurement = stage1_transition_measurement(decision, direction)
        low, high = transition_occluded_interval(measurement)
        assert low < high
        bands = transition_band_intervals(measurement)
        assert bands and all(len(band) == 2 for band in bands)

    @requires_campaign
    def test_the_original_flat_read_would_still_have_failed(self, decision):
        """Proof the fixture really is the shape that used to break."""
        detail = decision["gates"]["prospective_transition_measurement"]["detail"]
        assert "LEFT_TO_RIGHT" not in detail
        assert set(detail) == {"reported", "derived_from_rows"}

    def test_legitimate_v0_2_shape_still_replays(self):
        legacy = {"stable_occluded_world_x_interval": [-3.0, 4.0],
                  "partial_transition_world_x_intervals": [[-7.0, -3.0], [4.0, 8.0]]}
        assert transition_occluded_interval(legacy) == (-3.0, 4.0)
        assert transition_band_intervals(legacy) == [(-7.0, -3.0), (4.0, 8.0)]

    def test_a_measurement_declaring_both_generations_is_refused(self):
        """No silent default: ambiguity fails closed rather than picking one."""
        both = {"stable_occluded_world_x_interval": [-3.0, 4.0],
                "extent_fully_occluded_world_x_interval": [-1.0, 1.0]}
        with pytest.raises(EvidenceError, match="exactly one is required"):
            transition_occluded_interval(both)

    def test_a_measurement_declaring_neither_is_refused(self):
        with pytest.raises(EvidenceError, match="exactly one is required"):
            transition_occluded_interval({"unrelated": 1})

    @requires_campaign
    def test_missing_direction_is_refused_not_defaulted(self, decision):
        with pytest.raises(EvidenceError, match="no row-derived measurement"):
            stage1_transition_measurement(decision, "SIDEWAYS")

    @requires_campaign
    def test_reported_and_derived_must_agree(self, decision):
        """A hand-edited decision cannot move a window by rewriting one copy."""
        tampered = copy.deepcopy(decision)
        detail = tampered["gates"]["prospective_transition_measurement"]["detail"]
        detail["reported"]["LEFT_TO_RIGHT"]["extent_fully_occluded_world_x_interval"] = [0.0, 0.1]
        with pytest.raises(EvidenceError, match="disagree"):
            stage1_transition_measurement(tampered, "LEFT_TO_RIGHT")

    @requires_campaign
    def test_reported_may_carry_extra_provenance_keys(self, decision):
        """The gate's own PASS rule, not a stricter invented one.

        ``reported`` legitimately carries direction/measurement_unit_ids/status
        which the derivation never emits. Whole-dict equality here would reject
        decisions that legitimately passed the frozen gate.
        """
        detail = decision["gates"]["prospective_transition_measurement"]["detail"]
        extra = set(detail["reported"]["LEFT_TO_RIGHT"]) - set(detail["derived_from_rows"]["LEFT_TO_RIGHT"])
        assert extra
        stage1_transition_measurement(decision, "LEFT_TO_RIGHT")


# ======================================================================
# B004 -- design condition vs runtime scene vocabulary
# ======================================================================

class TestSceneVocabulary:
    """Original failure: WALL-design captures emit ``scene="NORMAL"``, so a
    consumer comparing rows to ``unit["scene"]`` classified all 19 target rows
    of all 25 WALL captures as malformed_or_missing."""

    def test_the_two_vocabularies_are_distinct(self):
        assert runtime_scene_value("WALL") == "NORMAL"
        assert runtime_scene_value("NO_WALL") == "NO_WALL"
        assert capture_layout_value("WALL") == "normal"
        assert capture_layout_value("NO_WALL") == "nowall"

    @pytest.mark.parametrize("bogus", ["NORMAL", "wall", "", None, 3])
    def test_unknown_design_conditions_fail_closed(self, bogus):
        with pytest.raises(EvidenceError):
            runtime_scene_value(bogus)

    def test_real_captured_wall_bytes_carry_the_runtime_name(self):
        """Anchored on bytes S3 actually holds for a WALL-design Stage-1 unit."""
        sample = {"scene": "NORMAL", "trajectory_id": "a1y_ltr_wall_r01"}
        assert sample["scene"] == runtime_scene_value("WALL")
        assert sample["scene"] != "WALL"

    @requires_campaign
    def test_wall_rows_are_accepted_and_design_named_rows_are_still_refused(
            self, authority, stage2, monkeypatch):
        from scripts.regime_a_prime_qualification_v0_2.build_manifests import path_for
        monkeypatch.setenv("MINEOCCLUDE_STAGE1_DECISION_PATH", str(FROZEN_DECISION))
        from scripts.regime_a_prime_qualification_v0_2.stage_unit_driver import (
            stage2_physical_evidence)

        unit = next(u for u in stage2["capture_units"] if u["unit_id"] == "a2y_t01_wall")
        observed = np.asarray(path_for(unit, authority), dtype="<f8")
        ticks = unit["target_model_frame_indices"]
        rows = [{"server_tick": t, "model_frame_idx": t, "render_frame_idx": t,
                 "scene": runtime_scene_value(unit["scene"]),
                 "geometric_status": "occluded", "magenta_status": "not_detected"} for t in ticks]

        evidence = stage2_physical_evidence(unit, {"visibility": rows}, observed, authority)
        assert evidence["target_row_count"] == 19
        assert evidence["contamination_rows"] == []
        assert all(evidence["checks"].values())

        # Scene validation is NOT weakened: rows carrying the DESIGN name are
        # still rejected, because they are not what the runtime emits.
        wrong = [dict(row, scene="WALL") for row in rows]
        blocked = stage2_physical_evidence(unit, {"visibility": wrong}, observed, authority)
        assert len(blocked["contamination_rows"]) == 19
        assert all("malformed_or_missing" in row["classes"]
                   for row in blocked["contamination_rows"])


# ======================================================================
# B005 -- scientific_run_id coverage
# ======================================================================

class TestScientificRunId:
    """Original failure: 54 of 104 Stage-2 units carried no ``scientific_run_id``
    and ``DurableController.run`` refuses such a unit -- after capture."""

    def test_every_stage2_unit_carries_the_campaign_identity(self, stage2):
        namespace = stage2["run_namespace"]
        missing = [u["unit_id"] for u in stage2["units"] if u.get("scientific_run_id") != namespace]
        assert missing == []

    @pytest.mark.parametrize("role,expected", [
        ("stage2-capture", 50), ("stage2-gates", 1), ("stage2-extract", 50),
        ("stage2-best-k", 1), ("stage2-full", 1), ("stage2-terminal", 1)])
    def test_coverage_by_role(self, stage2, role, expected):
        def stage_of(unit):
            command = unit.get("command") or []
            return command[command.index("--stage") + 1] if "--stage" in command else None
        units = [u for u in stage2["units"] if stage_of(u) == role]
        assert len(units) == expected
        assert all(u.get("scientific_run_id") == stage2["run_namespace"] for u in units)

    def test_controller_still_refuses_a_foreign_namespace(self, tmp_path, stage2):
        """The check the missing field was tripping is intact."""
        manifest = copy.deepcopy(stage2)
        manifest["units"] = manifest["units"][:1]
        manifest["units"][0]["scientific_run_id"] = "some-other-campaign"
        controller = DurableController(
            manifest, tmp_path / "state", tmp_path / "events.jsonl",
            manifest_sha256="a" * 64, authority_sha256="b" * 64,
            source_commit_sha="c" * 40, run_namespace=manifest["run_namespace"],
            stage_role="stage2")
        with pytest.raises(PermissionError, match="belongs to namespace"):
            controller.run(authorized=True, stop_after_stage1=False)


# ======================================================================
# B006 -- derived durable URI
# ======================================================================

class TestDurablePathResolver:
    """Original failure: the controller expected ``{prefix}/{unit_id}`` for every
    unit while the backend wrote derived artifacts to ``{prefix}/derived/{id}``,
    so a derived unit ran, failed its own receipt check, and retried to
    exhaustion."""

    def test_capture_units_are_flat_and_derived_units_are_namespaced(self, stage2):
        prefix = stage2["durable_prefix"].rstrip("/")
        assert durable_unit_uri(stage2, "a2y_t01_wall") == f"{prefix}/a2y_t01_wall"
        assert durable_unit_uri(stage2, "extract_a2y_t01_wall") == \
            f"{prefix}/derived/extract_a2y_t01_wall"
        for unit_id in ("stage2_physical_gates", "stage2_best_k", "stage2_full", "stage2_terminal"):
            assert durable_unit_uri(stage2, unit_id) == f"{prefix}/derived/{unit_id}"

    def test_stage1_manifests_have_no_derived_namespace(self):
        stage1 = load_json(STAGE1_MANIFEST_PATH)
        prefix = stage1["durable_prefix"].rstrip("/")
        for unit in stage1["units"]:
            assert durable_unit_uri(stage1, unit["unit_id"]) == f"{prefix}/{unit['unit_id']}"

    def test_controller_and_resolver_agree_for_every_unit(self, tmp_path, stage2):
        controller = DurableController(
            stage2, tmp_path / "state", tmp_path / "events.jsonl",
            manifest_sha256="a" * 64, authority_sha256="b" * 64,
            source_commit_sha="c" * 40, run_namespace=stage2["run_namespace"],
            stage_role="stage2")
        for unit in stage2["units"]:
            assert controller.expected_durable_uri(unit["unit_id"]) == \
                durable_unit_uri(stage2, unit["unit_id"])

    def test_role_comes_from_the_roster_not_the_name(self, stage2):
        """A capture unit named like a derived one is still resolved as capture."""
        manifest = {"durable_prefix": "s3://bucket/prefix",
                    "capture_units": [{"unit_id": "extract_looking_name"}],
                    "units": [{"unit_id": "extract_looking_name"}]}
        assert durable_unit_uri(manifest, "extract_looking_name") == \
            "s3://bucket/prefix/extract_looking_name"

    def test_malformed_prefix_fails_closed(self):
        with pytest.raises(EvidenceError):
            durable_unit_uri({"durable_prefix": "/not/s3"}, "u")


# ======================================================================
# B010 / B012 / B013 -- policy, lifecycle, smoke selection
# ======================================================================

class TestStage2OperationalPolicy:
    """Original failure: Stage 2 read ``stage1_policy.stop_rules``."""

    def test_stage2_reads_the_stage_neutral_operational_policy(self, authority):
        source = (ROOT / "scripts/regime_a_prime_qualification_v0_2"
                       / "development_controller.py").read_text()
        stage2_block = source.split("manifest = load_json(stage2_path)", 1)[1]
        assert 'authority["restart_resume"]["maximum_identical_attempts"]' in stage2_block
        # Comments explain the old dependency by name; the CODE must not have it.
        executable = "\n".join(line for line in stage2_block.splitlines()
                               if not line.strip().startswith("#"))
        assert "stage1_policy" not in executable

    def test_behaviour_is_numerically_unchanged(self, authority):
        assert (authority["restart_resume"]["maximum_identical_attempts"]
                == authority["stage1_policy"]["stop_rules"]["retry_same_unit_maximum_attempts"] == 3)

    def test_the_operational_policy_explicitly_covers_stage_2(self, authority):
        assert "Stage 2" in authority["restart_resume"]["durable_atomic_unit"]


class TestLifecycleCoherence:
    def test_current_package_is_coherent(self, authority, stage2):
        assert require_stage2_lifecycle_coherence(authority, stage2)

    def test_unknown_manifest_status_fails_closed(self, authority, stage2):
        with pytest.raises(EvidenceError, match="not admitted"):
            require_stage2_lifecycle_coherence(authority, dict(stage2, status="INVENTED"))

    def test_unknown_authority_lifecycle_fails_closed(self, authority, stage2):
        broken = copy.deepcopy(authority)
        broken["stage2_policy"]["manifest_state"] = "INVENTED"
        with pytest.raises(EvidenceError, match="unrecognised"):
            require_stage2_lifecycle_coherence(broken, stage2)


class TestSmokeSelection:
    """Original failure: the smoke took ``manifest["units"][0]`` while separately
    hard-coding the WALL capture layout."""

    def test_selection_is_invariant_under_reordering(self, stage2):
        from scripts.regime_a_prime_qualification_v0_2.generate_receipts import (
            select_smoke_source_unit)
        baseline = select_smoke_source_unit(stage2)["unit_id"]
        for seed in range(25):
            shuffled = dict(stage2)
            units = list(stage2["units"])
            random.Random(seed).shuffle(units)
            shuffled["units"] = units
            assert select_smoke_source_unit(shuffled)["unit_id"] == baseline

    def test_selected_unit_matches_the_layout_the_smoke_launches(self, stage2):
        from scripts.regime_a_prime_qualification_v0_2.generate_receipts import (
            select_smoke_source_unit, SMOKE_DESIGN_CONDITION)
        chosen = select_smoke_source_unit(stage2)
        assert chosen["scene"] == SMOKE_DESIGN_CONDITION
        assert capture_layout_value(chosen["scene"]) == "normal"

    def test_a_non_capture_unit_is_never_selected(self, stage2):
        from scripts.regime_a_prime_qualification_v0_2.generate_receipts import (
            select_smoke_source_unit)
        chosen = select_smoke_source_unit(stage2)
        assert chosen["unit_id"] in {u["unit_id"] for u in stage2["capture_units"]}
        assert "episode_id" in chosen and "seed" in chosen

    def test_a_roster_without_the_launched_condition_fails_closed(self, stage2):
        from scripts.regime_a_prime_qualification_v0_2.generate_receipts import (
            select_smoke_source_unit)
        control_only = dict(stage2)
        control_only["units"] = [u for u in stage2["units"] if u.get("scene") == "NO_WALL"]
        control_only["capture_units"] = [u for u in stage2["capture_units"]
                                         if u.get("scene") == "NO_WALL"]
        with pytest.raises(EvidenceError, match="no WALL capture unit"):
            select_smoke_source_unit(control_only)


# ======================================================================
# B007 / B008 -- closure coverage
# ======================================================================

class TestRuntimeClosureCoverage:
    """Original failure: files that determine activation values, and the module
    holding every acceptance assertion, sat outside the digest that authorizes a
    run while thin wrappers around them sat inside it."""

    @staticmethod
    def _reachable(seeds: list[str]) -> set[str]:
        import ast
        search = [ROOT, ROOT / "src", ROOT / "scripts/regime_a_prime_qualification_v0_1"]

        def resolve(module: str):
            parts = module.split(".")
            for base in search:
                candidate = base.joinpath(*parts).with_suffix(".py")
                if candidate.is_file():
                    return candidate
                package = base.joinpath(*parts) / "__init__.py"
                if package.is_file():
                    return package
            return None

        seen, stack = set(), [ROOT / seed for seed in seeds]
        while stack:
            current = stack.pop()
            relative = str(current.relative_to(ROOT))
            if relative in seen:
                continue
            seen.add(relative)
            try:
                tree = ast.parse(current.read_text())
            except (SyntaxError, OSError):
                continue
            names: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                    names.add(node.module)
                    names.update(f"{node.module}.{alias.name}" for alias in node.names)
            for name in names:
                found = resolve(name)
                if found is not None and ROOT in found.parents:
                    stack.append(found)
        return seen

    def test_extraction_implementation_closure_is_fully_governed(self):
        """Re-derives the graph rather than trusting a hand-written list.

        This is what makes the repair durable: a future delegation into a new
        ungoverned module fails here instead of silently escaping provenance.
        """
        reachable = self._reachable([
            "scripts/regime_a_prime_qualification_v0_1/p2d_extract.py",
            "scripts/regime_a_prime_qualification_v0_2/stage2_backend.py"])
        outside = sorted(reachable - set(RUNTIME_CRITICAL_SOURCE_PATHS))
        assert outside == [], f"activation-determining files outside the closure: {outside}"

    def test_acceptance_implementation_is_governed(self):
        reachable = self._reachable(
            ["scripts/regime_a_prime_qualification_v0_2/acceptance_harness.py"])
        assert sorted(reachable - set(RUNTIME_CRITICAL_SOURCE_PATHS)) == []

    @pytest.mark.parametrize("path", [
        "scripts/run_person_a_66_cell_production_extraction.py",
        "src/mineocclude/models/mineworld_adapter.py",
        "src/mineocclude/activations/hooks.py",
        "src/mineocclude/models/_mineworld_adapter_wave5.py",
        "scripts/regime_a_prime_qualification_v0_2/acceptance_harness.py",
        "src/mineocclude/prospective/unit1_checkpoint.py"])
    def test_named_implementations_are_present(self, path):
        assert path in RUNTIME_CRITICAL_SOURCE_PATHS
        assert (ROOT / path).is_file()

    def test_the_closure_has_no_duplicates_and_every_path_exists(self):
        assert len(set(RUNTIME_CRITICAL_SOURCE_PATHS)) == len(RUNTIME_CRITICAL_SOURCE_PATHS)
        assert [p for p in RUNTIME_CRITICAL_SOURCE_PATHS if not (ROOT / p).is_file()] == []


# ======================================================================
# B011 -- time-invariant artifact verification
# ======================================================================

class TestCampaignBoundSourceVerification:
    """Original failure: completed durable artifacts were validated against
    ``git rev-parse HEAD`` at processing time, so a later checkout invalidated
    evidence it never touched."""

    @requires_campaign
    def test_commit_comes_from_the_campaigns_frozen_provenance(self):
        provenance = load_json(FROZEN_PROVENANCE)
        assert campaign_source_commit(provenance) == provenance["source_commit"]

    def test_the_backend_no_longer_reads_live_head(self):
        source = (ROOT / "scripts/regime_a_prime_qualification_v0_2/stage2_backend.py").read_text()
        code = "\n".join(line for line in source.splitlines()
                         if not line.strip().startswith("#"))
        assert '"rev-parse"' not in code and "rev-parse" not in code.replace(
            "Replaces ``git rev-parse HEAD`` at every processing site.", "")

    @pytest.mark.parametrize("field,value", [
        ("status", "DRAFT"),
        ("source_commit_binding_state", "UNBOUND"),
        ("committed_bytes_equal_reviewed_bytes", False),
        ("repository_clean_at_post_freeze_verification", False),
        ("scientific_outcomes_observed", True)])
    @requires_campaign
    def test_an_unfrozen_or_post_outcome_provenance_is_refused(self, field, value):
        provenance = dict(load_json(FROZEN_PROVENANCE))
        provenance[field] = value
        with pytest.raises(EvidenceError, match="source freeze rejects"):
            campaign_source_commit(provenance)

    @pytest.mark.parametrize("commit", ["", "abc", "z" * 40, None, 12345])
    def test_a_malformed_commit_is_refused(self, commit):
        with pytest.raises(EvidenceError, match="no concrete source freeze"):
            campaign_source_commit({"source_commit": commit})


# ======================================================================
# Unit-1 operational processability checkpoint
# ======================================================================

def _passing_prober(unit, receipt):
    return ({name: True for name in cp.REQUIRED_CHECKS},
            {"activation_shape": [19, 1024], "activation_dtype": "float32",
             "target_rows_resolved": 19, "layer": 4})


def _bindings(tmp_path):
    return {"receipt_path": tmp_path / "unit1_checkpoint.json",
            "manifest_sha256": "a" * 64, "authority_sha256": "b" * 64,
            "source_commit_sha": "c" * 40, "scientific_run_id": "ns-v0-4-stage2"}


class TestUnit1Checkpoint:
    UNIT = {"unit_id": "a2y_t01_wall", "scene": "WALL"}

    def test_a_structurally_processable_unit_passes(self, tmp_path):
        record = cp.run_checkpoint(unit=self.UNIT, receipt={}, prober=_passing_prober,
                                   **_bindings(tmp_path))
        assert record["status"] == cp.PASS
        assert set(record["checks"]) == set(cp.REQUIRED_CHECKS)
        assert record["classification"] == "OPERATIONAL_ONLY_NOT_SCIENTIFIC_EVIDENCE"

    def test_a_structural_failure_blocks_remaining_collection(self, tmp_path):
        def failing(unit, receipt):
            checks = {name: True for name in cp.REQUIRED_CHECKS}
            checks["ACTIVATION_DTYPE_VALID"] = False
            return checks, {"activation_dtype": "float64"}
        with pytest.raises(cp.OperationalCheckpointBlocked, match="ACTIVATION_DTYPE_VALID"):
            cp.run_checkpoint(unit=self.UNIT, receipt={}, prober=failing, **_bindings(tmp_path))

    def test_a_block_is_operational_and_never_a_scientific_verdict(self, tmp_path):
        def failing(unit, receipt):
            return {name: False for name in cp.REQUIRED_CHECKS}, {}
        bindings = _bindings(tmp_path)
        with pytest.raises(cp.OperationalCheckpointBlocked) as raised:
            cp.run_checkpoint(unit=self.UNIT, receipt={}, prober=failing, **bindings)
        assert not isinstance(raised.value, EvidenceError)
        record = load_json(bindings["receipt_path"])
        assert record["status"] == cp.BLOCKED
        assert record["scientific_outcome_observed"] is False
        assert record["may_alter_scientific_design"] is False
        assert "FAIL" not in record["status"]

    def test_a_raising_prober_blocks_rather_than_crashing(self, tmp_path):
        def exploding(unit, receipt):
            raise RuntimeError("layer-4 hook did not resolve")
        bindings = _bindings(tmp_path)
        with pytest.raises(cp.OperationalCheckpointBlocked):
            cp.run_checkpoint(unit=self.UNIT, receipt={}, prober=exploding, **bindings)
        assert "layer-4 hook" in load_json(bindings["receipt_path"])["structural_facts"][
            "prober_exception"]

    def test_resume_honours_a_verified_receipt_without_reprobing(self, tmp_path):
        bindings = _bindings(tmp_path)
        cp.run_checkpoint(unit=self.UNIT, receipt={}, prober=_passing_prober, **bindings)
        calls = []

        def counting(unit, receipt):
            calls.append(unit)
            return _passing_prober(unit, receipt)
        again = cp.run_checkpoint(unit=self.UNIT, receipt={}, prober=counting, **bindings)
        assert calls == []
        assert again["status"] == cp.PASS

    @pytest.mark.parametrize("field", ["manifest_sha256", "authority_sha256",
                                       "source_commit_sha", "scientific_run_id"])
    def test_resume_refuses_a_receipt_from_another_execution(self, tmp_path, field):
        bindings = _bindings(tmp_path)
        cp.run_checkpoint(unit=self.UNIT, receipt={}, prober=_passing_prober, **bindings)
        moved = dict(bindings)
        moved[field] = "d" * len(str(bindings[field]))
        calls = []

        def counting(unit, receipt):
            calls.append(unit)
            return _passing_prober(unit, receipt)
        cp.run_checkpoint(unit=self.UNIT, receipt={}, prober=counting, **moved)
        assert calls, "a receipt bound to another execution must not be honoured"

    def test_a_tampered_receipt_is_not_honoured(self, tmp_path):
        bindings = _bindings(tmp_path)
        cp.run_checkpoint(unit=self.UNIT, receipt={}, prober=_passing_prober, **bindings)
        record = load_json(bindings["receipt_path"])
        record["checks"]["ACTIVATIONS_FINITE"] = False
        bindings["receipt_path"].write_text(json.dumps(record))
        calls = []

        def counting(unit, receipt):
            calls.append(unit)
            return _passing_prober(unit, receipt)
        cp.run_checkpoint(unit=self.UNIT, receipt={}, prober=counting, **bindings)
        assert calls, "a receipt whose digest does not reproduce must be re-derived"

    @pytest.mark.parametrize("field", [
        "decoder_rmse", "baseline_comparison", "best_k", "hidden_vs_visible_effect",
        "qualification_status", "probe_score", "mean_error"])
    def test_outcome_bearing_fields_cannot_enter_the_receipt(self, tmp_path, field):
        """The mechanical guarantee of non-adaptivity."""
        def leaking(unit, receipt):
            return {name: True for name in cp.REQUIRED_CHECKS}, {field: 0.123}
        with pytest.raises(EvidenceError, match="forbidden outcome-bearing field"):
            cp.run_checkpoint(unit=self.UNIT, receipt={}, prober=leaking, **_bindings(tmp_path))

    def test_no_required_check_names_an_outcome(self):
        cp.refuse_outcome_fields({name: True for name in cp.REQUIRED_CHECKS})

    def test_check_coverage_cannot_be_narrowed_or_widened(self, tmp_path):
        with pytest.raises(EvidenceError, match="coverage is wrong"):
            cp.build_receipt(unit_id="u", checks={"CAPTURE_RECEIPT_VALID": True}, facts={},
                             manifest_sha256="a", authority_sha256="b",
                             source_commit_sha="c", scientific_run_id="d")


class TestCheckpointGatesCollection:
    """The controller must not walk past an unproven unit 1."""

    @staticmethod
    def _manifest(tmp_path):
        units = [{"unit_id": f"cap{i}", "scientific_run_id": "ns",
                  "command": ["/bin/true", "--stage", "stage2-capture"],
                  "receipt_path": str(tmp_path / f"r{i}.json")} for i in range(1, 4)]
        return {"durable_prefix": "s3://bucket/prefix", "units": units,
                "capture_units": [dict(u) for u in units]}

    def test_a_block_on_unit_1_stops_the_remaining_units(self, tmp_path):
        """A block propagates out of the controller, leaving units 2..n uncollected."""
        manifest = self._manifest(tmp_path)
        launched: list[str] = []

        def checkpoint(unit):
            raise cp.OperationalCheckpointBlocked("not processable")

        controller = DurableController(
            manifest, tmp_path / "state", tmp_path / "events.jsonl",
            manifest_sha256="a" * 64, authority_sha256="b" * 64, source_commit_sha="c" * 40,
            run_namespace="ns", stage_role="stage2", unit1_checkpoint=checkpoint,
            durable_verifier=lambda unit, receipt: True)

        # Stand in for execution: record each launch and write a receipt the
        # controller will accept, so the run reaches the gate legitimately.
        def fake_run(command, check=False, env=None):
            unit_id = manifest["units"][len(launched)]["unit_id"]
            launched.append(unit_id)
            path = Path(manifest["units"][len(launched) - 1]["receipt_path"])
            path.write_text(json.dumps({
                "unit_id": unit_id, "status": DurableController.TERMINAL,
                "manifest_sha256": "a" * 64, "authority_sha256": "b" * 64,
                "source_commit_sha": "c" * 40, "scientific_run_id": "ns",
                "durable_uri": durable_unit_uri(manifest, unit_id)}))
            return type("R", (), {"returncode": 0})()

        import mineocclude.prospective.development_workflow as workflow
        original = workflow.subprocess.run
        workflow.subprocess.run = fake_run
        try:
            with pytest.raises(cp.OperationalCheckpointBlocked):
                controller.run(authorized=True, stop_after_stage1=False)
        finally:
            workflow.subprocess.run = original

        assert launched == ["cap1"], (
            "collection must stop at the blocked unit; units 2..n must not run")

    def test_gate_fires_once_and_only_for_capture_units(self, tmp_path):
        manifest = self._manifest(tmp_path)
        manifest["capture_units"] = [manifest["units"][1]]
        seen = []
        controller = DurableController(
            manifest, tmp_path / "state", tmp_path / "events.jsonl",
            manifest_sha256="a" * 64, authority_sha256="b" * 64, source_commit_sha="c" * 40,
            run_namespace="ns", stage_role="stage2",
            unit1_checkpoint=lambda unit: seen.append(unit["unit_id"]))
        pending = True
        for unit in manifest["units"]:
            pending = controller._apply_unit1_checkpoint(unit, pending)
        assert seen == ["cap2"], "only the declared capture unit may arm the gate"
        assert pending is False

    def test_no_checkpoint_configured_leaves_behaviour_unchanged(self, tmp_path):
        manifest = self._manifest(tmp_path)
        controller = DurableController(
            manifest, tmp_path / "state", tmp_path / "events.jsonl",
            manifest_sha256="a" * 64, authority_sha256="b" * 64, source_commit_sha="c" * 40,
            run_namespace="ns", stage_role="stage2")
        assert controller._apply_unit1_checkpoint(manifest["units"][0], False) is False
