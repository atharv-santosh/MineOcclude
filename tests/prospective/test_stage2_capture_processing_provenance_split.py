#!/usr/bin/env python3
"""Adversarial tests for the Stage-2 capture / processing provenance split.

Scoped deliberately to the changed architecture: the capture-critical closure
derivation, the typed trajectory-identity boundary, capture admission, the
anti-laundering rule and the cohort closure gate. Each class attacks one of them.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from mineocclude.prospective import capture_closure as cc
from mineocclude.prospective.activation_binding import (
    SCIENTIFIC_TRAJECTORY_NOT_AUTHORITY_BOUND, TARGET_ROWS_NOT_AUTHORITY_BOUND,
    resolve_authority_bound_target_rows,
)
from mineocclude.prospective.capture_admission import (
    CaptureAdmissionError, TypedCaptureIdentity, admit_completed_capture,
    build_capture_admission_context, expected_capture_apparatus,
    load_capture_provenance_authority, require_homogeneous_capture_closure,
    require_no_provenance_laundering, resolve_typed_capture_identity,
    verify_capture_package_identity, verify_visibility_rows_scientific_identity,
)
from mineocclude.prospective.development_workflow import (
    EvidenceError, RUNTIME_CRITICAL_SOURCE_PATHS,
)
from mineocclude.prospective.package_binding import package_directory

ROOT = Path(__file__).resolve().parents[2]
PREDECESSOR = "49f0cca9d0ec6d204444bf3c0d1fa5fc7e263936"
PACKAGE = package_directory("v0.4", ROOT)


# ======================================================================
# Fixtures: authority, manifest, and a synthetic capture receipt
# ======================================================================

@pytest.fixture(scope="module")
def authority() -> dict:
    return json.loads((PACKAGE / "authority_parameters.json").read_bytes())


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads((PACKAGE / "stage2_locked_manifest.json").read_bytes())


@pytest.fixture(scope="module")
def live_closure() -> str:
    digest, _ = cc.capture_critical_closure_at(cc.worktree_reader(ROOT), repository=ROOT)
    return digest


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def synthetic_receipt(authority, manifest, live_closure) -> dict:
    """A capture receipt for unit 1 that admits cleanly, built from frozen truth.

    Constructed rather than read from the live campaign tree so the whole suite runs
    without a completed capture on disk, and so each attack can mutate exactly one
    field of an otherwise-valid receipt.
    """
    unit = manifest["capture_units"][0]
    symbols = cc.derive_capture_critical_symbols(cc.git_reader(PREDECESSOR, ROOT),
                                                 repository=ROOT)
    read = cc.git_reader(PREDECESSOR, ROOT)
    recorded = {}
    for relative in RUNTIME_CRITICAL_SOURCE_PATHS:
        source = read(relative)
        if source is not None:
            recorded[relative] = hashlib.sha256(source.encode("utf-8")).hexdigest()
    apparatus = expected_capture_apparatus(authority)
    return {
        "unit_id": unit["unit_id"],
        "status": "COMPLETE_VALIDATED_DURABLE",
        "classification": "DEVELOPMENT_ONLY",
        "confirmatory_membership": False,
        "manifest_sha256": _sha(PACKAGE / "stage2_locked_manifest.json"),
        "authority_sha256": _sha(PACKAGE / "authority_parameters.json"),
        "scientific_run_id": manifest["run_namespace"],
        "durable_uri": manifest["durable_prefix"].rstrip("/") + "/" + unit["unit_id"],
        "source_commit_sha": PREDECESSOR,
        "durable_objects": {"raw/server_state.jsonl": "a" * 64,
                            "raw/visibility.jsonl": "b" * 64,
                            "capture_package_v0_1.json": "c" * 64},
        "remote_checksum_manifest_sha256": "d" * 64,
        "runtime_provenance_receipt": {
            "head": PREDECESSOR,
            "runtime_source_sha256": recorded,
            "critical_file_sha256": dict(apparatus["critical_file_sha256"]),
            "captured_apparatus_receipt": dict(apparatus["captured_apparatus"]),
            **{field: apparatus[field]
               for field in cc.CAPTURE_CRITICAL_NON_SOURCE_RUNTIME_IDENTITIES},
        },
    }


@pytest.fixture(scope="module")
def context(authority, manifest, live_closure):
    return build_capture_admission_context(
        authority=authority, manifest=manifest,
        manifest_sha256=_sha(PACKAGE / "stage2_locked_manifest.json"),
        authority_sha256=_sha(PACKAGE / "authority_parameters.json"),
        scientific_run_id=manifest["run_namespace"],
        processing_source_commit_sha="f" * 40,
        capture_provenance_authority_sha256=_sha(
            PACKAGE / "stage2_capture_processing_provenance_authority.json"),
        repository=ROOT,
        expected_capture_critical_closure_sha256=live_closure)


def _mutating_reader(overrides: dict[str, str]):
    """A source reader that returns modified bytes for named paths."""
    base = cc.worktree_reader(ROOT)

    def read(relative: str):
        if relative in overrides:
            return overrides[relative]
        return base(relative)
    return read


# ======================================================================
# Baseline: the split is actually in force
# ======================================================================

class TestTheSplitIsInForce:

    def test_predecessor_and_successor_capture_apparatus_are_equal(self, live_closure):
        """The session's central claim: the repair is downstream-only."""
        result = cc.compare_capture_critical_closures(
            PREDECESSOR, cc.worktree_reader(ROOT), repository=ROOT)
        assert result["capture_critical_closure_equal"] is True, (
            f"capture-determining components changed: "
            f"{result['components_with_changed_bytes']}")
        assert result["successor_capture_critical_closure_sha256"] == live_closure

    def test_the_two_closures_are_not_the_same_value(self, live_closure):
        """If they ever coincided the split would be silently inert."""
        from mineocclude.prospective.development_workflow import (
            runtime_critical_source_closure_sha256)
        assert runtime_critical_source_closure_sha256(ROOT) != live_closure

    def test_capture_closure_excludes_the_downstream_only_stack(self):
        symbols = cc.derive_capture_critical_symbols(repository=ROOT)
        paths = set(cc.capture_critical_paths(symbols))
        for downstream in (
                "scripts/regime_a_prime_qualification_v0_1/p2d_extract.py",
                "scripts/regime_a_prime_qualification_v0_1/p2e_analyze.py",
                "src/mineocclude/probes/p7_ridge.py",
                "src/mineocclude/models/mineworld_adapter.py",
                "src/mineocclude/activations/hooks.py",
                "src/mineocclude/prospective/stage2_evidence.py",
                "src/mineocclude/prospective/stage2_decision.py",
                "src/mineocclude/prospective/activation_binding.py",
                "src/mineocclude/prospective/capture_admission.py"):
            assert downstream not in paths, f"{downstream} must not be capture-critical"
        # ...and every downstream-only file is still GOVERNED, just not by this closure.
        assert set(RUNTIME_CRITICAL_SOURCE_PATHS) >= {
            "scripts/regime_a_prime_qualification_v0_1/p2d_extract.py",
            "src/mineocclude/prospective/capture_admission.py",
            "src/mineocclude/prospective/capture_closure.py"}

    def test_capture_closure_includes_every_capture_determining_component(self):
        symbols = set(cc.derive_capture_critical_symbols(repository=ROOT))
        names = {symbol for _, symbol in symbols}
        for required in ("capture", "derive_effective_capture_spec",
                         "require_capture_spec_contract", "generate_noise_schedule",
                         "CaptureSession", "derive_artifacts", "detect_magenta",
                         "launch_runtime", "LiveRuntime", "stop_runtime",
                         "verify_captured_apparatus", "stage2_physical_evidence"):
            assert required in names, f"{required} must be capture-critical"

    def test_the_authority_document_records_the_live_closure(self, live_closure):
        document = json.loads(
            (PACKAGE / "stage2_capture_processing_provenance_authority.json").read_bytes())
        assert document["capture_critical_closure"][
            "closure_sha256_at_generation"] == live_closure
        assert document["depends_on_scientific_outcome"] is False
        assert document["stage2_locked_manifest_modified"] is False
        assert document["historical_stage1_authority_modified"] is False

    def test_the_authority_verifies_through_the_consumer_path(self):
        document, digest = load_capture_provenance_authority(
            PACKAGE, version_tag="v0.4",
            authority_path=PACKAGE / "authority_parameters.json", repository=ROOT)
        assert digest == _sha(
            PACKAGE / "stage2_capture_processing_provenance_authority.json")
        assert document["authorized_option"].startswith("OPTION_3")


# ======================================================================
# A. Capture-closure attacks
# ======================================================================

class TestCaptureClosureAttacks:
    """Changing something that CAN change a capture must change the closure."""

    @pytest.mark.parametrize("relative,marker", [
        # the capture driver itself
        ("scripts/regime_a_prime_qualification_v0_2/stage_unit_driver.py",
         "def verify_captured_apparatus"),
        # the motion/noise schedule
        ("src/mineocclude/data/noise_schedule.py", "def generate_noise_schedule"),
        # the visibility/scene logic
        ("src/mineocclude/data/visibility.py", "def "),
        # the detector
        ("src/mineocclude/vision/magenta.py", "def detect_magenta"),
        # the episode startup / JVM launch
        ("scripts/run_large_scale_no_wall_campaign.py", "def launch_runtime"),
        # the capture session
        ("scripts/regime_a_prime_qualification_v0_1/p2_common.py", "class CaptureSession"),
        # the capture spec derivation
        ("src/mineocclude/prospective/development_workflow.py",
         "def derive_effective_capture_spec"),
    ])
    def test_one_changed_capture_producing_byte_blocks(self, relative, marker,
                                                       live_closure):
        source = cc.worktree_reader(ROOT)(relative)
        assert marker in source, f"marker not found in {relative}"
        # A syntactically valid edit on purpose: a file that merely fails to parse
        # would block for the wrong reason and would not show that the closure is
        # sensitive to real byte changes in capture-determining code.
        mutated = source + "\n\nimport os as _adversarial_capture_edit\n"
        digest, _ = cc.capture_critical_closure_at(
            _mutating_reader({relative: mutated}), repository=ROOT)
        assert digest != live_closure, (
            f"a change inside {relative} did not change the capture-critical closure")

    def test_the_closure_is_sensitive_at_DEFINITION_granularity(self, live_closure):
        """The granularity claim, both directions, in one shared file.

        ``development_workflow`` holds ``derive_effective_capture_spec`` (decides the
        seed, frames, speed and start position a capture runs under) and
        ``DurableController`` (cannot touch a captured byte). Editing the first must
        block; editing the second must not. If this test ever fails in the second
        direction, the closure has silently regressed to file granularity and every
        downstream repair would again invalidate valid raw captures.
        """
        relative = "src/mineocclude/prospective/development_workflow.py"
        source = cc.worktree_reader(ROOT)(relative)

        capture_marker = "One shared construction path"
        if capture_marker not in source:
            capture_marker = "def derive_effective_capture_spec"
        inside_capture = source.replace(
            "def derive_effective_capture_spec(unit: Mapping[str, Any],",
            "def derive_effective_capture_spec(unit: Mapping[str, Any],  # edit", 1)
        assert inside_capture != source
        digest, _ = cc.capture_critical_closure_at(
            _mutating_reader({relative: inside_capture}), repository=ROOT)
        assert digest != live_closure, (
            "editing the capture-spec derivation must change the capture closure")

        inside_controller = source.replace(
            "class DurableController:", "class DurableController:  # edit", 1)
        assert inside_controller != source
        digest, _ = cc.capture_critical_closure_at(
            _mutating_reader({relative: inside_controller}), repository=ROOT)
        assert digest == live_closure, (
            "editing the controller must NOT change the capture closure; the closure "
            "has regressed to whole-file granularity")

    def test_a_changed_camera_or_scene_authority_blocks_admission(
            self, context, synthetic_receipt, manifest):
        """Camera pose is capture-determining even at identical source bytes."""
        for field, value in (("camera_eye_world_xyz", [0.5, 5.62, -5.4]),
                             ("fov_degrees", 71.0),
                             ("layout_id", "layout_02"),
                             ("wall_authority", "layout_01_long_wall_v0.3"),
                             ("canonical_frame_pixels", [640, 361])):
            receipt = copy.deepcopy(synthetic_receipt)
            receipt["runtime_provenance_receipt"][
                "captured_apparatus_receipt"][field] = value
            with pytest.raises(CaptureAdmissionError, match="apparatus differs"):
                context.admit(manifest["capture_units"][0], receipt)

    @pytest.mark.parametrize("field,value", [
        ("minecraft_version", "1.16.4"),
        ("java", "Corretto-17.0.20.8.2"),
        ("mesa", "25.2.7"),
        ("xvfb", "21.1.11"),
        ("detector_config_id", "some_other_detector"),
    ])
    def test_a_changed_runtime_identity_blocks_admission(
            self, context, synthetic_receipt, manifest, field, value):
        receipt = copy.deepcopy(synthetic_receipt)
        receipt["runtime_provenance_receipt"][field] = value
        with pytest.raises(CaptureAdmissionError, match="apparatus differs"):
            context.admit(manifest["capture_units"][0], receipt)

    @pytest.mark.parametrize("apparatus_file", [
        "installed_mod", "minecraft_server_jar", "fabric_server_launcher_jar",
        "mod_source", "detector_config",
    ])
    def test_a_changed_fabric_mod_or_detector_file_blocks_admission(
            self, context, synthetic_receipt, manifest, apparatus_file):
        receipt = copy.deepcopy(synthetic_receipt)
        receipt["runtime_provenance_receipt"][
            "critical_file_sha256"][apparatus_file] = "9" * 64
        with pytest.raises(CaptureAdmissionError, match="apparatus differs"):
            context.admit(manifest["capture_units"][0], receipt)

    @pytest.mark.parametrize("relative", [
        "scripts/regime_a_prime_qualification_v0_1/p2d_extract.py",
        "src/mineocclude/prospective/stage2_evidence.py",
        "src/mineocclude/prospective/stage2_decision.py",
        "src/mineocclude/analysis/manifests.py",
    ])
    def test_a_downstream_only_change_leaves_the_capture_closure_alone(
            self, relative, live_closure):
        """The converse, and the whole point: processing may move, capture may not."""
        source = cc.worktree_reader(ROOT)(relative)
        mutated = source + "\n# adversarial downstream-only edit\n"
        digest, _ = cc.capture_critical_closure_at(
            _mutating_reader({relative: mutated}), repository=ROOT)
        assert digest == live_closure, (
            f"a downstream-only change in {relative} wrongly changed the capture closure")

    def test_governance_projection_admits_additions_and_refuses_removals(
            self, live_closure):
        """The governance list may grow; it may not drop a capture-critical path."""
        relative = "src/mineocclude/prospective/development_workflow.py"
        source = cc.worktree_reader(ROOT)(relative)

        grown = source.replace(
            '    "src/mineocclude/prospective/capture_closure.py",',
            '    "src/mineocclude/prospective/capture_closure.py",\n'
            '    "src/mineocclude/probes/p7a_execution.py",', 1)
        assert grown != source
        digest, _ = cc.capture_critical_closure_at(
            _mutating_reader({relative: grown}), repository=ROOT)
        assert digest == live_closure, (
            "governing an additional downstream file must not change the capture closure")

        shrunk = source.replace('    "src/mineocclude/data/noise_schedule.py",\n', "", 1)
        assert shrunk != source
        digest, _ = cc.capture_critical_closure_at(
            _mutating_reader({relative: shrunk}), repository=ROOT)
        assert digest != live_closure, (
            "dropping a capture-critical path from governance must change the closure")

    def test_the_reachable_capture_graph_cannot_escape_governance(self):
        """Re-derives the graph; a new reachable capture file must be governed."""
        symbols = cc.derive_capture_critical_symbols(repository=ROOT)
        outside = sorted(set(cc.capture_critical_paths(symbols))
                         - set(RUNTIME_CRITICAL_SOURCE_PATHS))
        assert outside == [], f"capture-determining files outside governance: {outside}"

    def test_import_only_modules_have_no_import_time_side_effects(self):
        """Soundness condition for pruning by call graph rather than by import."""
        import ast

        symbols = cc.derive_capture_critical_symbols(repository=ROOT)
        call_reachable = set(cc.capture_critical_paths(symbols))
        read = cc.worktree_reader(ROOT)
        seen, stack = set(), [path for path, _ in cc.CAPTURE_ENTRYPOINTS]
        while stack:
            relative = stack.pop()
            if relative in seen:
                continue
            source = read(relative)
            if source is None:
                continue
            seen.add(relative)
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                modules = []
                if isinstance(node, ast.Import):
                    modules += [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                    modules.append(node.module)
                    modules += [f"{node.module}.{alias.name}" for alias in node.names]
                for module in modules:
                    target = cc._resolve_module(module, read)
                    if target is not None:
                        stack.append(target)
        offenders = sorted(
            relative for relative in seen - call_reachable
            if not cc.module_body_is_definition_only(relative, read, repository=ROOT))
        assert offenders == [], (
            "these modules are pruned from the capture closure but do real work at "
            f"import time, so pruning them is unsound: {offenders}")


# ======================================================================
# B. Provenance attacks
# ======================================================================

class TestProvenanceAttacks:

    def test_a_valid_receipt_admits(self, context, synthetic_receipt, manifest):
        record = context.admit(manifest["capture_units"][0], synthetic_receipt)
        assert record["capture_compatibility"] == "PASS"
        assert record["capture_source_commit"] == PREDECESSOR
        assert record["processing_source_commit"] == "f" * 40
        assert record["capture_taken_under_processing_commit"] is False

    def test_a_faked_predecessor_commit_is_refused(self, context, synthetic_receipt,
                                                   manifest):
        receipt = copy.deepcopy(synthetic_receipt)
        receipt["source_commit_sha"] = "0" * 40
        receipt["runtime_provenance_receipt"]["head"] = "0" * 40
        with pytest.raises(CaptureAdmissionError):
            context.admit(manifest["capture_units"][0], receipt)

    def test_a_receipt_whose_two_commit_fields_disagree_is_refused(
            self, context, synthetic_receipt, manifest):
        receipt = copy.deepcopy(synthetic_receipt)
        receipt["runtime_provenance_receipt"]["head"] = "1" * 40
        with pytest.raises(CaptureAdmissionError, match="disagrees"):
            context.admit(manifest["capture_units"][0], receipt)

    def test_a_malformed_commit_is_refused(self, context, synthetic_receipt, manifest):
        for value in (None, "", "abc", "z" * 40, 49):
            receipt = copy.deepcopy(synthetic_receipt)
            receipt["source_commit_sha"] = value
            with pytest.raises(CaptureAdmissionError):
                context.admit(manifest["capture_units"][0], receipt)

    def test_recorded_source_digests_that_disagree_with_the_commit_are_refused(
            self, context, synthetic_receipt, manifest):
        """A receipt claiming a commit whose bytes it did not actually measure."""
        receipt = copy.deepcopy(synthetic_receipt)
        receipt["runtime_provenance_receipt"]["runtime_source_sha256"][
            "src/mineocclude/data/noise_schedule.py"] = "e" * 64
        with pytest.raises(CaptureAdmissionError, match="not the bytes"):
            context.admit(manifest["capture_units"][0], receipt)

    def test_a_receipt_missing_capture_critical_digests_is_refused(
            self, context, synthetic_receipt, manifest):
        receipt = copy.deepcopy(synthetic_receipt)
        del receipt["runtime_provenance_receipt"]["runtime_source_sha256"][
            "src/mineocclude/data/align.py"]
        with pytest.raises(CaptureAdmissionError):
            context.admit(manifest["capture_units"][0], receipt)

    @pytest.mark.parametrize("field,value", [
        ("manifest_sha256", "0" * 64),
        ("authority_sha256", "0" * 64),
        ("scientific_run_id", "some-other-campaign"),
        ("status", "INCOMPLETE"),
        ("classification", "CONFIRMATORY"),
        ("confirmatory_membership", True),
        ("durable_uri", "s3://somewhere-else/a2y_t01_wall"),
        ("unit_id", "a2y_t02_wall"),
    ])
    def test_a_wrong_design_binding_is_refused(self, context, synthetic_receipt,
                                              manifest, field, value):
        receipt = copy.deepcopy(synthetic_receipt)
        receipt[field] = value
        with pytest.raises(CaptureAdmissionError, match="scientific design|episode|trajectory"):
            context.admit(manifest["capture_units"][0], receipt)

    def test_a_receipt_with_no_durable_inventory_is_refused(
            self, context, synthetic_receipt, manifest):
        for value in ({}, None, "many"):
            receipt = copy.deepcopy(synthetic_receipt)
            receipt["durable_objects"] = value
            with pytest.raises(CaptureAdmissionError):
                context.admit(manifest["capture_units"][0], receipt)

    def test_the_durable_inventory_digest_is_sensitive_to_the_inventory(
            self, context, synthetic_receipt, manifest):
        first = context.admit(manifest["capture_units"][0], synthetic_receipt)
        receipt = copy.deepcopy(synthetic_receipt)
        receipt["durable_objects"]["raw/frames/000000.png"] = "f" * 64
        second = context.admit(manifest["capture_units"][0], receipt)
        assert (first["durable_object_inventory_sha256"]
                != second["durable_object_inventory_sha256"])
        assert second["durable_object_count"] == first["durable_object_count"] + 1

    def test_a_closure_mismatch_stops_rather_than_recollects(
            self, authority, manifest, synthetic_receipt):
        """The fail-closed stop: refusal, never automatic recapture."""
        context = build_capture_admission_context(
            authority=authority, manifest=manifest,
            manifest_sha256=_sha(PACKAGE / "stage2_locked_manifest.json"),
            authority_sha256=_sha(PACKAGE / "authority_parameters.json"),
            scientific_run_id=manifest["run_namespace"],
            processing_source_commit_sha="f" * 40,
            capture_provenance_authority_sha256="0" * 64, repository=ROOT,
            expected_capture_critical_closure_sha256="a" * 64)
        with pytest.raises(CaptureAdmissionError) as caught:
            context.admit(manifest["capture_units"][0], synthetic_receipt)
        message = str(caught.value)
        assert "NOT equivalent" in message
        assert "authority review" in message
        assert "rather than automatic recollection" in message


# ======================================================================
# C. Identity attacks
# ======================================================================

class TestTypedIdentityAttacks:

    def test_the_two_identities_are_derived_and_distinct(self, authority, manifest):
        identity = resolve_typed_capture_identity(authority, manifest["capture_units"][0])
        assert identity.legacy_capture_trajectory_id == "layout_01_ep86001"
        assert identity.scientific_trajectory_id == "a2y_t01"
        assert identity.scientific_capture_unit_id == "a2y_t01_wall"
        assert identity.episode_id == 86001
        assert identity.scene == "WALL"
        assert identity.layout_id == "layout_01"
        assert (identity.legacy_capture_trajectory_id
                != identity.scientific_trajectory_id)

    def test_the_legacy_identity_is_the_frozen_composition(self, authority, manifest):
        for unit in manifest["capture_units"]:
            identity = resolve_typed_capture_identity(authority, unit)
            assert identity.legacy_capture_trajectory_id == (
                f"{authority['apparatus']['layout_id']}_ep{unit['episode_id']}")

    def test_wall_and_no_wall_partners_differ_by_the_episode_offset(self, authority,
                                                                   manifest):
        by_key = {(unit["trajectory_id"], unit["scene"]): unit
                  for unit in manifest["capture_units"]}
        for (trajectory, scene), unit in by_key.items():
            if scene != "WALL":
                continue
            partner = by_key[(trajectory, "NO_WALL")]
            assert partner["episode_id"] == unit["episode_id"] + 500
            wall = resolve_typed_capture_identity(authority, unit)
            no_wall = resolve_typed_capture_identity(authority, partner)
            assert (wall.legacy_capture_trajectory_id
                    != no_wall.legacy_capture_trajectory_id)
            assert (wall.scientific_trajectory_id
                    == no_wall.scientific_trajectory_id)

    @pytest.mark.parametrize("field,value,match", [
        ("trajectory_id", None, "trajectory_id"),
        ("trajectory_id", "", "trajectory_id"),
        ("unit_id", None, "unit_id"),
        ("scene", "NORMAL", "scene is outside"),
        ("episode_id", "86001", "not an integer"),
        ("episode_id", True, "not an integer"),
        ("episode_id", None, "not an integer"),
    ])
    def test_a_malformed_unit_cannot_produce_an_identity(self, authority, manifest,
                                                        field, value, match):
        unit = dict(manifest["capture_units"][0])
        unit[field] = value
        with pytest.raises(CaptureAdmissionError, match=match):
            resolve_typed_capture_identity(authority, unit)

    def test_an_ambiguous_mapping_is_refused(self, authority, manifest):
        """The two namespaces must remain distinguishable."""
        unit = dict(manifest["capture_units"][0])
        unit["trajectory_id"] = f"{authority['apparatus']['layout_id']}_ep{unit['episode_id']}"
        with pytest.raises(CaptureAdmissionError, match="ambiguous"):
            resolve_typed_capture_identity(authority, unit)

    def test_a_missing_layout_authority_is_refused(self, manifest):
        with pytest.raises(CaptureAdmissionError, match="apparatus"):
            resolve_typed_capture_identity({}, manifest["capture_units"][0])

    # ---- the capture package side (legacy namespace) ----------------------

    def _identity(self, authority, manifest, index=0) -> TypedCaptureIdentity:
        return resolve_typed_capture_identity(authority, manifest["capture_units"][index])

    def test_a_correct_capture_package_is_accepted(self, authority, manifest):
        identity = self._identity(authority, manifest)
        verify_capture_package_identity(
            {"trajectory_id": "layout_01_ep86001", "episode_id": 86001,
             "layout_id": "layout_01"}, identity)

    @pytest.mark.parametrize("package,match", [
        ({"episode_id": 86001, "layout_id": "layout_01"}, "no legacy"),
        ({"trajectory_id": "a2y_t01", "episode_id": 86001, "layout_id": "layout_01"},
         "legacy capture trajectory identity is"),
        ({"trajectory_id": "layout_01_ep86501", "episode_id": 86501,
          "layout_id": "layout_01"}, "legacy capture trajectory identity is"),
        ({"trajectory_id": "layout_01_ep86001", "layout_id": "layout_01"},
         "no episode"),
        ({"trajectory_id": "layout_01_ep86001", "episode_id": 86002,
          "layout_id": "layout_01"}, "episode is"),
        ({"trajectory_id": "layout_01_ep86001", "episode_id": 86001,
          "layout_id": "layout_02"}, "layout is"),
        # The legacy-identity diagnosis is more specific than the layout one and
        # correctly fires first for a wholly foreign layout.
        ({"trajectory_id": "layout_02_ep86001", "episode_id": 86001,
          "layout_id": "layout_02"}, "legacy capture trajectory identity is"),
    ])
    def test_a_wrong_capture_package_is_refused(self, authority, manifest, package,
                                               match):
        identity = self._identity(authority, manifest)
        with pytest.raises(CaptureAdmissionError, match=match):
            verify_capture_package_identity(package, identity)

    def test_a_swapped_t1_t2_capture_package_is_refused(self, authority, manifest):
        """T2's real package offered for T1's unit."""
        first = self._identity(authority, manifest, 0)
        others = [unit for unit in manifest["capture_units"]
                  if unit["unit_id"] != manifest["capture_units"][0]["unit_id"]]
        second = resolve_typed_capture_identity(authority, others[0])
        with pytest.raises(CaptureAdmissionError):
            verify_capture_package_identity(
                {"trajectory_id": second.legacy_capture_trajectory_id,
                 "episode_id": second.episode_id,
                 "layout_id": second.layout_id}, first)

    def test_a_no_wall_package_substituted_for_wall_is_refused(self, authority,
                                                              manifest):
        wall = next(unit for unit in manifest["capture_units"]
                    if unit["scene"] == "WALL")
        partner = next(unit for unit in manifest["capture_units"]
                       if unit["trajectory_id"] == wall["trajectory_id"]
                       and unit["scene"] == "NO_WALL")
        identity = resolve_typed_capture_identity(authority, wall)
        substitute = resolve_typed_capture_identity(authority, partner)
        with pytest.raises(CaptureAdmissionError, match="episode|legacy"):
            verify_capture_package_identity(
                {"trajectory_id": substitute.legacy_capture_trajectory_id,
                 "episode_id": substitute.episode_id,
                 "layout_id": substitute.layout_id}, identity)

    # ---- the visibility-row side (scientific namespace) -------------------

    def test_correct_visibility_rows_are_accepted(self, authority, manifest):
        identity = self._identity(authority, manifest)
        assert verify_visibility_rows_scientific_identity(
            [{"trajectory_id": "a2y_t01"}] * 3, identity) == 3

    @pytest.mark.parametrize("rows,match", [
        ([{"trajectory_id": "layout_01_ep86001"}], "not"),
        ([{"trajectory_id": "a2y_t02"}], "not"),
        ([{"trajectory_id": "a2y_t01"}, {"trajectory_id": "a2y_t02"}], "not"),
        ([{}], "no scientific trajectory identity"),
        ([], "empty"),
        ([{"trajectory_id": "a2y_t01"}, {}], "no scientific"),
    ])
    def test_wrong_visibility_rows_are_refused(self, authority, manifest, rows, match):
        identity = self._identity(authority, manifest)
        with pytest.raises(CaptureAdmissionError, match=match):
            verify_visibility_rows_scientific_identity(rows, identity)

    # ---- the repaired resolver -------------------------------------------

    def _rows(self, trajectory="a2y_t01", count=19, **overrides):
        rows = []
        for tau in range(1, count + 1):
            frame = 47 + tau
            row = {"tau": tau, "model_frame_idx": frame, "server_tick": frame,
                   "render_frame_idx": frame, "trajectory_id": trajectory}
            row.update(overrides)
            rows.append(row)
        return rows

    def test_the_resolver_accepts_the_scientific_identity(self):
        expected = list(range(48, 67))
        assert resolve_authority_bound_target_rows(
            self._rows(), expected=expected, required_count=19,
            scientific_trajectory_id="a2y_t01") == expected

    def test_the_original_defect_is_gone(self):
        """The legacy identity fed to the Stage-2 resolver used to refuse every unit."""
        expected = list(range(48, 67))
        with pytest.raises(EvidenceError, match="not 'layout_01_ep86001'"):
            resolve_authority_bound_target_rows(
                self._rows(), expected=expected, required_count=19,
                scientific_trajectory_id="layout_01_ep86001")

    def test_a_row_with_no_scientific_identity_is_refused(self):
        """The superseded check passed a row that simply omitted the key."""
        rows = self._rows()
        del rows[0]["trajectory_id"]
        with pytest.raises(EvidenceError, match="carries no scientific trajectory"):
            resolve_authority_bound_target_rows(
                rows, expected=list(range(48, 67)), required_count=19,
                scientific_trajectory_id="a2y_t01")

    def test_rows_from_another_trajectory_are_refused(self):
        with pytest.raises(EvidenceError, match="bound to scientific trajectory"):
            resolve_authority_bound_target_rows(
                self._rows(trajectory="a2y_t07"), expected=list(range(48, 67)),
                required_count=19, scientific_trajectory_id="a2y_t01")

    def test_a_blank_or_wrongly_typed_identity_is_refused(self):
        for value in ("", "   ", 42, None, ["a2y_t01"]):
            with pytest.raises(EvidenceError, match="scientific trajectory identity"):
                resolve_authority_bound_target_rows(
                    self._rows(), expected=list(range(48, 67)), required_count=19,
                    scientific_trajectory_id=value)

    def test_the_historical_pilot_sentinel_still_skips_the_check(self):
        rows = self._rows(trajectory="layout_01_ep86001")
        assert resolve_authority_bound_target_rows(
            rows, expected=TARGET_ROWS_NOT_AUTHORITY_BOUND, required_count=19,
            scientific_trajectory_id=SCIENTIFIC_TRAJECTORY_NOT_AUTHORITY_BOUND
        ) == list(range(48, 67))

    def test_the_extractor_requires_both_identities_explicitly(self):
        """No default may reopen the hole: both are keyword-only and mandatory."""
        import ast

        source = (ROOT / "scripts/regime_a_prime_qualification_v0_1/p2d_extract.py"
                  ).read_text()
        tree = ast.parse(source)
        extract = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "extract")
        names = [argument.arg for argument in extract.args.kwonlyargs]
        assert "scientific_trajectory_id" in names
        assert "expected_legacy_capture_trajectory_id" in names
        assert all(default is None for default in extract.args.kw_defaults), (
            "a default on either typed identity would reopen the defect")


# ======================================================================
# D. Provenance laundering
# ======================================================================

class TestProvenanceLaundering:

    def test_a_truthful_record_passes(self, context, synthetic_receipt, manifest):
        record = context.admit(manifest["capture_units"][0], synthetic_receipt)
        require_no_provenance_laundering(record)

    def test_claiming_the_capture_was_taken_under_the_successor_is_refused(
            self, context, synthetic_receipt, manifest):
        record = context.admit(manifest["capture_units"][0], synthetic_receipt)
        laundered = dict(record)
        laundered["capture_taken_under_processing_commit"] = True
        with pytest.raises(CaptureAdmissionError, match="laundering"):
            require_no_provenance_laundering(laundered)

    def test_claiming_the_commits_are_equal_is_refused(self, context,
                                                      synthetic_receipt, manifest):
        record = context.admit(manifest["capture_units"][0], synthetic_receipt)
        laundered = dict(record)
        laundered["capture_and_processing_commits_equal"] = True
        with pytest.raises(CaptureAdmissionError, match="laundering"):
            require_no_provenance_laundering(laundered)

    def test_rewriting_the_capture_commit_to_the_processing_commit_is_refused(
            self, context, synthetic_receipt, manifest):
        record = context.admit(manifest["capture_units"][0], synthetic_receipt)
        laundered = dict(record)
        laundered["capture_source_commit"] = laundered["processing_source_commit"]
        with pytest.raises(CaptureAdmissionError, match="laundering"):
            require_no_provenance_laundering(laundered)

    def test_a_record_omitting_either_commit_is_refused(self):
        for missing in ("capture_source_commit", "processing_source_commit"):
            record = {"capture_source_commit": "a" * 40,
                      "processing_source_commit": "b" * 40,
                      "capture_and_processing_commits_equal": False,
                      "capture_taken_under_processing_commit": False}
            del record[missing]
            with pytest.raises(CaptureAdmissionError, match="both capture and processing"):
                require_no_provenance_laundering(record)

    def test_the_admission_record_is_not_a_capture_receipt(self, context,
                                                          synthetic_receipt, manifest):
        record = context.admit(manifest["capture_units"][0], synthetic_receipt)
        assert record["classification"] == (
            "OPERATIONAL_DERIVED_VERIFICATION_NOT_A_CAPTURE_RECEIPT")
        assert record["scientific_outcome_observed"] is False

    def test_admission_never_mutates_the_receipt(self, context, synthetic_receipt,
                                                manifest):
        before = json.dumps(synthetic_receipt, sort_keys=True)
        context.admit(manifest["capture_units"][0], synthetic_receipt)
        assert json.dumps(synthetic_receipt, sort_keys=True) == before


# ======================================================================
# E. Mixed-closure cohort
# ======================================================================

class TestCohortClosureGate:

    def test_a_homogeneous_cohort_resolves_to_one_closure(self):
        records = [{"unit_id": f"u{index}", "capture_critical_closure_sha256": "a" * 64}
                   for index in range(50)]
        assert require_homogeneous_capture_closure(records) == "a" * 64

    def test_a_cohort_spanning_two_apparatuses_is_refused(self):
        records = [{"unit_id": "a2y_t01_wall", "capture_critical_closure_sha256": "a" * 64},
                   {"unit_id": "a2y_t02_wall", "capture_critical_closure_sha256": "b" * 64}]
        with pytest.raises(CaptureAdmissionError, match="more than one capture-critical"):
            require_homogeneous_capture_closure(records)

    def test_the_refusal_names_the_units_on_each_side(self):
        records = [{"unit_id": "a2y_t01_wall", "capture_critical_closure_sha256": "a" * 64},
                   {"unit_id": "a2y_t02_wall", "capture_critical_closure_sha256": "b" * 64}]
        with pytest.raises(CaptureAdmissionError) as caught:
            require_homogeneous_capture_closure(records)
        assert "a2y_t01_wall" in str(caught.value)
        assert "a2y_t02_wall" in str(caught.value)

    def test_an_empty_cohort_is_refused(self):
        with pytest.raises(CaptureAdmissionError, match="no admitted captures"):
            require_homogeneous_capture_closure([])

    def test_a_malformed_closure_is_refused(self):
        with pytest.raises(CaptureAdmissionError, match="malformed"):
            require_homogeneous_capture_closure(
                [{"unit_id": "u", "capture_critical_closure_sha256": "short"}])

    def test_differing_full_commits_are_allowed_at_one_closure(self):
        """The cohort rule: mixed commits yes, mixed apparatus no."""
        records = [
            {"unit_id": "a2y_t01_wall", "capture_source_commit": PREDECESSOR,
             "capture_critical_closure_sha256": "a" * 64},
            {"unit_id": "a2y_t02_wall", "capture_source_commit": "b" * 40,
             "capture_critical_closure_sha256": "a" * 64}]
        assert require_homogeneous_capture_closure(records) == "a" * 64
        assert len({record["capture_source_commit"] for record in records}) == 2


# ======================================================================
# F. The physical gate itself, on a mixed-commit cohort
# ======================================================================

class TestThePhysicalGateAdmitsAMixedCommitCohort:
    """The gate that actually ran the real campaign, on the cohort it rejected.

    The v0.4 split repaired five source-homogeneity checks, but ``gates()`` kept a
    sixth: it validated the fifty RAW CAPTURE units with
    ``require_durable_unit_receipt``, whose contract is derived units and which
    therefore demands ``source_commit_sha == HEAD``. Every unit-level test above
    passed while the real campaign failed closed on ``a2y_t01_wall`` -- captured
    legitimately under the predecessor -- because nothing exercised ``gates()``.

    These tests drive the real ``gates()``, the real
    ``backend_capture_admission`` and the real capture-critical closure derivation
    at a real predecessor commit. Only S3 durability, the physical-evidence reader
    and receipt writing are stubbed: none of them is the defect.
    """

    SUCCESSOR = "c" * 40

    @pytest.fixture
    def gate_harness(self, monkeypatch, manifest, synthetic_receipt):
        import functools

        from scripts.regime_a_prime_qualification_v0_2 import stage2_backend as backend

        manifest_path = PACKAGE / "stage2_locked_manifest.json"
        unit = copy.deepcopy(manifest["capture_units"][0])
        trimmed = dict(manifest, capture_units=[unit])
        receipts = {unit["unit_id"]: copy.deepcopy(synthetic_receipt)}
        recorded: dict = {}

        monkeypatch.setattr(backend, "campaign_commit", lambda: self.SUCCESSOR)
        monkeypatch.setattr(backend, "capture_receipt",
                            lambda _manifest, unit_id: receipts[unit_id])
        monkeypatch.setattr(backend, "verify_bound_stage2_physical_evidence",
                            lambda *_args, **_kwargs: None)
        # The real admission logic, with only the S3 round trip stubbed. The
        # verifier is a default argument bound at definition, so it cannot be
        # replaced by patching the module attribute it was read from.
        monkeypatch.setattr(backend, "require_admitted_capture_receipt",
                            functools.partial(backend.require_admitted_capture_receipt,
                                              durable_verifier=lambda *_: True))

        def fake_validate(_manifest, _receipts, **kwargs):
            recorded["validate_kwargs"] = kwargs
            return {"status": "PASS"}

        def fake_complete(_manifest, _manifest_path, unit_id, payload, **_kwargs):
            recorded["completed"] = (unit_id, payload)

        monkeypatch.setattr(backend, "validate_physical_gate_receipts", fake_validate)
        monkeypatch.setattr(backend, "complete", fake_complete)
        return backend, trimmed, manifest_path, receipts, recorded

    def test_a_capture_taken_under_the_predecessor_does_not_fail_the_gate(
            self, gate_harness):
        """The exact campaign failure: RuntimeError on a valid durable capture."""
        backend, trimmed, manifest_path, _receipts, recorded = gate_harness

        backend.gates(trimmed, manifest_path, "stage2_physical_gates")

        assert recorded["completed"][0] == "stage2_physical_gates"
        assert recorded["completed"][1]["physical_gates"]["status"] == "PASS"

    def test_the_gate_hands_its_admission_context_to_the_cohort_validator(
            self, gate_harness):
        """The second, latent defect: the validator's required kwarg was omitted."""
        backend, trimmed, manifest_path, _receipts, recorded = gate_harness

        backend.gates(trimmed, manifest_path, "stage2_physical_gates")

        kwargs = recorded["validate_kwargs"]
        assert kwargs["capture_admission"] is not None
        assert kwargs["current_source_commit"] == self.SUCCESSOR
        assert kwargs["capture_admission"].processing_source_commit_sha == self.SUCCESSOR

    def test_the_gate_binds_the_capture_and_processing_commits_separately(
            self, gate_harness):
        """Admission must not launder the predecessor capture into the successor."""
        backend, trimmed, manifest_path, receipts, _recorded = gate_harness
        admission = backend.backend_capture_admission(
            trimmed, manifest_path, current_source_commit=self.SUCCESSOR)

        unit = trimmed["capture_units"][0]
        record = admission.admit(unit, receipts[unit["unit_id"]])

        assert record["capture_source_commit"] == PREDECESSOR
        assert record["processing_source_commit"] == self.SUCCESSOR
        assert record["capture_and_processing_commits_equal"] is False
        assert record["capture_critical_closure_sha256"] == (
            cc.capture_critical_closure_at(cc.worktree_reader(ROOT), repository=ROOT)[0])

    def test_the_gate_still_fails_closed_on_a_capture_it_must_refuse(
            self, gate_harness):
        """Admission replaced commit equality; it did not relax the gate."""
        backend, trimmed, manifest_path, receipts, _recorded = gate_harness
        unit_id = trimmed["capture_units"][0]["unit_id"]
        receipts[unit_id]["manifest_sha256"] = "0" * 64

        with pytest.raises(RuntimeError, match="capture admission refused"):
            backend.gates(trimmed, manifest_path, "stage2_physical_gates")

    def test_a_capture_whose_apparatus_differs_is_still_refused_by_the_gate(
            self, gate_harness):
        """Closure equality is the admission rule, and the gate enforces it."""
        backend, trimmed, manifest_path, receipts, _recorded = gate_harness
        unit_id = trimmed["capture_units"][0]["unit_id"]
        receipts[unit_id]["runtime_provenance_receipt"]["minecraft_version"] = "1.0.0"

        with pytest.raises(RuntimeError, match="capture admission refused"):
            backend.gates(trimmed, manifest_path, "stage2_physical_gates")
