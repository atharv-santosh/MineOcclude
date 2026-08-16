"""Adversarial coverage for A4 provenance, A6 stage binding, and the receipt generators.

Every test here is an attack that must fail closed. They are grouped by the
control they target:

* temporal   -- the repaired estimand-pairing agreement rule;
* provenance -- ``verify_probe_execution``, which replaced a self-hash;
* stage      -- ``require_stage_manifest_binding`` at every entrypoint;
* authorize  -- the Stage-1 authorization generator's prerequisite reproduction;
* runtime    -- the pinned JDK and apparatus artefact identities.

The positive cases are built from the real tree: real file bytes, the real
authority, the real manifest. Nothing here collects data or starts Minecraft.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from mineocclude.prospective.development_workflow import (
    EvidenceError, RUNTIME_CRITICAL_SOURCE_PATHS, Stage1Evaluator,
    canonical_json_bytes, canonical_payload_sha256, load_json,
    probe_evidence_digest, require_preoutcome_provenance,
    require_stage_manifest_binding, runtime_critical_source_closure_sha256,
    sha256_file, stage_run_inventory_sha256, verify_probe_execution,
)
from scripts.regime_a_prime_qualification_v0_2 import generate_receipts
from tests.prospective.test_development_authority_v0_2_repair import (
    probe_execution_record, signed_probe, valid_evidence,
)

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = (ROOT / "docs/status/integration/regime_a_prime_qualification_v0_1"
           / "prospective_development_authority_v0_2")
AUTHORITY_PATH = PACKAGE / "authority_parameters.json"
STAGE1_PATH = PACKAGE / "stage1_manifest.json"
STAGE2_PATH = PACKAGE / "stage2_locked_manifest.json"


@pytest.fixture
def authority():
    return load_json(AUTHORITY_PATH)


@pytest.fixture
def stage1():
    return load_json(STAGE1_PATH)


@pytest.fixture
def stage2():
    return load_json(STAGE2_PATH)


def runtime_receipt(authority: dict, execution: dict | None = None) -> dict:
    execution = probe_execution_record(authority) if execution is None else execution
    fields = authority["runtime_identity_policy"]["required_fields"]
    return signed_probe(**fields, probe_execution=execution,
                        critical_file_sha256=execution["apparatus_file_sha256"],
                        probe_evidence_sha256=probe_evidence_digest(execution))


# ------------------------------------------------------------------ temporal


def test_frozen_forensic_reference_satisfies_the_repaired_agreement_rule():
    """The rule must be satisfiable by the apparatus this package will measure.

    The superseded rule required the FIR first moment and the single-tap
    cross-correlation lag to fall inside each other's intervals. On the frozen
    P2/P3 reference those intervals are disjoint, because the two methods
    estimate different functionals of the same causal kernel. Reproduced here
    from the frozen artefacts so the authority's recorded arithmetic cannot
    drift from the evidence it claims.
    """
    forensic = PACKAGE.parent / "p2_temporal_alignment_forensic_v0_1"
    impulse = json.loads((forensic / "impulse_response_raw.json").read_text())
    lags = json.loads((forensic / "lag_multimethod_raw.json").read_text())
    check = load_json(AUTHORITY_PATH)["stage1_policy"]["temporal_alignment"][
        "frozen_forensic_reference_agreement_check"]
    bound = load_json(AUTHORITY_PATH)["stage1_policy"]["temporal_alignment"][
        "cross_correlation_subtick_refinement_bound_ticks"]

    assert [unit["unit"] for unit in impulse["units"]] == [row["unit"] for row in lags["rows"]]
    assert len(impulse["units"]) == check["trajectory_count"]

    def mode(kernel):
        return max(range(len(kernel)), key=lambda lag: (kernel[lag], -lag))

    # The superseded rule genuinely fails on the frozen reference.
    assert check["superseded_rule_satisfied"] is False
    assert check["superseded_rule_intervals_overlap"] is False

    # The repaired rule pairs matched estimands, and the frozen reference
    # satisfies it with real slack.
    departures = [abs(row["B_sub"] - mode(unit["h"]))
                  for unit, row in zip(impulse["units"], lags["rows"], strict=True)]
    assert max(departures) == pytest.approx(
        check["repaired_rule_maximum_per_trajectory_mode_departure_ticks"], abs=1e-9)
    assert max(departures) <= bound
    assert mode(impulse["mean_kernel"]) == check["aggregate_kernel_mode_lag"]
    assert impulse["group_delay_mean"] == check[
        "method_1_causal_fir_group_delay_estimate_ticks"]
    # The two estimands are genuinely distinct, which is the whole point: the
    # frozen kernel's mode precedes its first moment in every trajectory.
    assert all(unit["group_delay"] > row["B_sub"]
               for unit, row in zip(impulse["units"], lags["rows"], strict=True))
    assert check["repaired_rule_satisfied"] is True


def test_superseded_equality_style_agreement_rule_is_rejected(authority, stage1):
    """A package still declaring the old rule cannot be evaluated at all."""
    poisoned = deepcopy(authority)
    poisoned["stage1_policy"]["temporal_alignment"]["agreement_rule"] = (
        "confidence_interval_overlap_and_mutual_estimate_containment"
        "_within_admissible_causal_lag_range")
    evaluator = Stage1Evaluator(poisoned, stage1,
                                authority_sha256=sha256_file(AUTHORITY_PATH),
                                manifest_sha256=sha256_file(STAGE1_PATH))
    decision = evaluator.evaluate(valid_evidence(poisoned, stage1))
    assert decision.status == "FAIL"
    assert any("temporal agreement rule" in reason for reason in decision.reasons), decision.reasons


def test_absent_refinement_bound_fails_closed(authority, stage1):
    """A package that omits the bound must not silently adopt one."""
    poisoned = deepcopy(authority)
    del poisoned["stage1_policy"]["temporal_alignment"][
        "cross_correlation_subtick_refinement_bound_ticks"]
    evaluator = Stage1Evaluator(poisoned, stage1,
                                authority_sha256=sha256_file(AUTHORITY_PATH),
                                manifest_sha256=sha256_file(STAGE1_PATH))
    decision = evaluator.evaluate(valid_evidence(poisoned, stage1))
    assert decision.status == "FAIL"
    assert any("cross_correlation_subtick_refinement_bound_ticks" in reason
               for reason in decision.reasons), decision.reasons


def test_unrelated_cross_correlation_estimator_does_not_qualify(authority, stage1):
    """An estimator not tracking the bound kernel's mode cannot manufacture agreement.

    This is the attack the repaired rule must still stop: replacing the
    independent method's per-trajectory series with values that have nothing to
    do with the fitted response. The superseded rule would have been satisfied
    by any series whose interval happened to be wide enough.
    """
    evidence = valid_evidence(authority, stage1)
    for item in evidence["alignment_by_direction"].values():
        cross = next(method for method in item["methods"]
                     if method["method_id"] == "derivative_cross_correlation_lag")
        count = cross["trajectory_count"]
        # Deliberately acausal-adjacent but in range, and far from the mode.
        cross["per_trajectory_estimates_ticks"] = [7.5] * count
        from mineocclude.prospective.development_workflow import mean_student_t_interval
        mean, interval = mean_student_t_interval([7.5] * count, 0.95)
        cross["estimate_ticks"], cross["confidence_interval_ticks"] = mean, list(interval)
    decision = Stage1Evaluator(authority, stage1,
                               authority_sha256=sha256_file(AUTHORITY_PATH),
                               manifest_sha256=sha256_file(STAGE1_PATH)).evaluate(evidence)
    assert decision.status == "FAIL"
    assert "render_server_temporal_alignment" in decision.reasons


def test_widening_an_interval_cannot_manufacture_agreement(authority, stage1):
    """Imprecision is no longer a route to agreement, unlike interval overlap."""
    evidence = valid_evidence(authority, stage1)
    for item in evidence["alignment_by_direction"].values():
        cross = next(method for method in item["methods"]
                     if method["method_id"] == "derivative_cross_correlation_lag")
        cross["confidence_interval_ticks"] = [0.0, 8.0]
    decision = Stage1Evaluator(authority, stage1,
                               authority_sha256=sha256_file(AUTHORITY_PATH),
                               manifest_sha256=sha256_file(STAGE1_PATH)).evaluate(evidence)
    assert decision.status == "FAIL"


# ---------------------------------------------------------------- provenance


def test_probe_execution_evidence_verifies_against_the_real_tree(authority):
    result = verify_probe_execution(runtime_receipt(authority),
                                    "runtime_provenance_receipt", authority=authority)
    assert result["status"] == "PASS"
    assert result["invocations_verified"] == ["java_version", "renderer", "xvfb"]
    assert result["producer"] == authority["runtime_identity_policy"][
        "probe_evidence_policy"]["independent_probe_producers"][0]


def test_fabricated_pass_booleans_without_probe_evidence_are_refused(authority):
    """The exact defect A4 names: a PASS assembled from self-assertions."""
    fabricated = signed_probe(**authority["runtime_identity_policy"]["required_fields"],
                              runtime_identity_verified=True,
                              apparatus_identity_verified=True,
                              renderer_identity_verified=True)
    with pytest.raises(EvidenceError, match="no probe execution record"):
        verify_probe_execution(fabricated, "runtime_provenance_receipt", authority=authority)


def test_evidence_builder_may_not_author_probe_evidence(authority):
    execution = probe_execution_record(authority)
    execution["producer"] = authority["runtime_identity_policy"][
        "probe_evidence_policy"]["forbidden_probe_producers"][0]
    with pytest.raises(EvidenceError, match="not produced by an independent probe"):
        verify_probe_execution(runtime_receipt(authority, execution),
                               "runtime_provenance_receipt", authority=authority)


def test_altered_probe_source_bytes_are_refused(authority):
    execution = probe_execution_record(authority)
    execution["probe_source_sha256"] = "0" * 64
    with pytest.raises(EvidenceError, match="probe source bytes"):
        verify_probe_execution(runtime_receipt(authority, execution),
                               "runtime_provenance_receipt", authority=authority)


def test_probe_source_outside_the_runtime_critical_closure_is_refused(authority):
    execution = probe_execution_record(authority)
    execution["probe_source_path"] = "README.md"
    with pytest.raises(EvidenceError, match="not a runtime-critical source"):
        verify_probe_execution(runtime_receipt(authority, execution),
                               "runtime_provenance_receipt", authority=authority)


def test_altered_invocation_command_is_refused(authority):
    execution = probe_execution_record(authority)
    invocation = execution["invocations"][0]
    invocation["argv"] = ["/bin/echo", "Corretto-17.0.20.8.1"]
    with pytest.raises(EvidenceError, match="absolute executable|pinned JDK"):
        verify_probe_execution(runtime_receipt(authority, execution),
                               "runtime_provenance_receipt", authority=authority)


def test_nonzero_probe_exit_status_is_refused(authority):
    execution = probe_execution_record(authority)
    execution["invocations"][0]["exit_status"] = 1
    with pytest.raises(EvidenceError, match="exited"):
        verify_probe_execution(runtime_receipt(authority, execution),
                               "runtime_provenance_receipt", authority=authority)


def test_altered_normalized_output_is_refused(authority):
    execution = probe_execution_record(authority)
    execution["invocations"][0]["normalized_output"] = "some other jdk\n"
    with pytest.raises(EvidenceError, match="output digest mismatch"):
        verify_probe_execution(runtime_receipt(authority, execution),
                               "runtime_provenance_receipt", authority=authority)


def test_output_without_the_authority_identity_token_is_refused(authority):
    """A rehashed but wrong-runtime output: consistent, and still not the pinned JDK."""
    execution = probe_execution_record(authority)
    invocation = execution["invocations"][0]
    invocation["normalized_output"] = "openjdk version 1.8.0_402\n"
    invocation["normalized_output_sha256"] = hashlib.sha256(
        invocation["normalized_output"].encode()).hexdigest()
    with pytest.raises(EvidenceError, match="identity tokens"):
        verify_probe_execution(runtime_receipt(authority, execution),
                               "runtime_provenance_receipt", authority=authority)


def test_missing_invocation_is_refused(authority):
    execution = probe_execution_record(authority)
    execution["invocations"] = execution["invocations"][:2]
    with pytest.raises(EvidenceError, match="invocation coverage"):
        verify_probe_execution(runtime_receipt(authority, execution),
                               "runtime_provenance_receipt", authority=authority)


def test_malformed_probe_digest_is_refused(authority):
    receipt = runtime_receipt(authority)
    receipt["probe_evidence_sha256"] = "not-a-digest"
    receipt["payload_sha256"] = canonical_payload_sha256(receipt, omit="payload_sha256")
    with pytest.raises(EvidenceError, match="probe evidence digest"):
        verify_probe_execution(receipt, "runtime_provenance_receipt", authority=authority)


def test_receipt_copied_from_another_run_loses_its_payload_digest(authority):
    receipt = runtime_receipt(authority)
    receipt["unit_id"] = "some-other-unit"
    with pytest.raises(EvidenceError, match="payload digest mismatch"):
        verify_probe_execution(receipt, "runtime_provenance_receipt", authority=authority)


# ------------------------------------------------------------------ runtime


def test_unpinned_java_from_path_is_refused(authority):
    """A `java` resolved from PATH is an unpinned runtime, even if it runs."""
    execution = probe_execution_record(authority)
    invocation = next(item for item in execution["invocations"]
                      if item["command_id"] == "java_version")
    import sys
    invocation["argv"] = [sys.executable, "-version"]
    invocation["executable_path"] = sys.executable
    invocation["executable_sha256"] = sha256_file(Path(sys.executable))
    with pytest.raises(EvidenceError, match="pinned JDK"):
        verify_probe_execution(runtime_receipt(authority, execution),
                               "runtime_provenance_receipt", authority=authority)


def test_absent_pinned_jdk_fails_runtime_reconstruction_closed(authority):
    from mineocclude.prospective.development_workflow import resolve_qualified_runtime
    poisoned = deepcopy(authority)
    poisoned["runtime_identity_policy"]["runtime_reconstruction"]["java_home"] = "/nonexistent/jdk"
    with pytest.raises(EvidenceError, match="qualified JDK is absent"):
        resolve_qualified_runtime(poisoned)


@pytest.mark.parametrize("artefact", ["minecraft_server_jar", "fabric_server_launcher_jar",
                                      "installed_mod", "detector_config"])
def test_apparatus_artefact_hash_mismatch_is_refused(authority, artefact):
    execution = probe_execution_record(authority)
    execution["apparatus_file_sha256"][artefact] = "0" * 64
    with pytest.raises(EvidenceError, match="apparatus pin mismatch"):
        verify_probe_execution(runtime_receipt(authority, execution),
                               "runtime_provenance_receipt", authority=authority)


def test_every_apparatus_pin_matches_the_bytes_on_disk(authority):
    """JAR/mod pins are real digests of real artefacts, not placeholders."""
    policy = authority["runtime_identity_policy"]
    for name, location in policy["critical_file_paths"].items():
        path = Path(location) if Path(location).is_absolute() else ROOT / location
        if not path.is_file():
            pytest.skip(f"apparatus artefact is absent from this environment: {name}")
        assert sha256_file(path) == policy["critical_file_sha256"][name], name


def test_altered_runtime_critical_source_is_refused(authority, tmp_path):
    execution = probe_execution_record(authority)
    relative = "src/mineocclude/prospective/development_workflow.py"
    execution["runtime_source_sha256"][relative] = "0" * 64
    with pytest.raises(EvidenceError, match="runtime source bytes mismatch"):
        verify_probe_execution(runtime_receipt(authority, execution),
                               "runtime_provenance_receipt", authority=authority)


# -------------------------------------------------------------- stage binding


def test_stage1_request_with_the_stage2_manifest_is_refused(authority, stage2):
    """The headline A6 attack: --stage stage1-capture --manifest stage2_locked_manifest.json."""
    with pytest.raises(PermissionError, match="requires manifest"):
        require_stage_manifest_binding("stage1-capture", stage2,
                                       manifest_path=STAGE2_PATH, authority=authority)


def test_stage2_request_with_the_stage1_manifest_is_refused(authority, stage1):
    with pytest.raises(PermissionError, match="requires manifest"):
        require_stage_manifest_binding("stage2-capture", stage1,
                                       manifest_path=STAGE1_PATH, authority=authority)


def test_stage1_authorization_cannot_launch_a_stage2_unit(authority, stage1, stage2):
    """A Stage-2 unit smuggled into a Stage-1 request, manifest identity intact."""
    stage2_unit = next(unit for unit in stage2["units"]
                       if unit.get("pipeline_stage") == "capture_and_durability")
    smuggled = deepcopy(stage1)
    smuggled["units"] = [*smuggled["units"], deepcopy(stage2_unit)]
    with pytest.raises(PermissionError, match="belongs to namespace"):
        require_stage_manifest_binding("stage1-capture", smuggled,
                                       manifest_path=STAGE1_PATH, authority=authority,
                                       unit=stage2_unit)


def test_relabelled_namespace_still_fails_on_the_declared_unit_stage(authority, stage1, stage2):
    """Rewriting scientific_run_id is not enough: the unit's own command declares its stage."""
    stage2_unit = deepcopy(next(unit for unit in stage2["units"]
                                if unit.get("pipeline_stage") == "capture_and_durability"))
    stage2_unit["scientific_run_id"] = stage1["run_namespace"]
    smuggled = deepcopy(stage1)
    smuggled["units"] = [*smuggled["units"], stage2_unit]
    with pytest.raises(PermissionError, match="is a 'stage2-capture' unit"):
        require_stage_manifest_binding("stage1-capture", smuggled,
                                       manifest_path=STAGE1_PATH, authority=authority,
                                       unit=stage2_unit)


def test_altered_manifest_artifact_id_is_refused(authority, stage1):
    poisoned = deepcopy(stage1)
    poisoned["artifact_id"] = "regime-a-prime-stage2-locked-manifest-v0.2"
    with pytest.raises(PermissionError, match="requires manifest"):
        require_stage_manifest_binding("stage1-capture", poisoned,
                                       manifest_path=STAGE1_PATH, authority=authority)


def test_manifest_copied_outside_its_declared_location_is_refused(authority, stage1, tmp_path):
    copied = tmp_path / "stage1_manifest.json"
    copied.write_text(STAGE1_PATH.read_text())
    with pytest.raises(PermissionError, match="outside the repository|manifest must be"):
        require_stage_manifest_binding("stage1-capture", stage1,
                                       manifest_path=copied, authority=authority)


def test_undeclared_stage_is_refused(authority, stage1):
    with pytest.raises(PermissionError, match="not declared by the frozen authority"):
        require_stage_manifest_binding("stage3-exfiltrate", stage1,
                                       manifest_path=STAGE1_PATH, authority=authority)


def test_cross_stage_restart_is_refused_before_reuse_or_launch(tmp_path):
    """Durable state is keyed by unit_id, so resume must check the stage too."""
    from mineocclude.prospective.development_workflow import DurableController

    controller = DurableController(
        {"units": [{"unit_id": "u1", "receipt_path": str(tmp_path / "r.json"),
                    "scientific_run_id": "mineocclude-regime-a-prime-development-v0-2-stage2",
                    "command": ["cmd", "--stage", "stage2-capture"]}],
         "durable_prefix": "s3://bucket/prefix"},
        tmp_path / "state", tmp_path / "events", manifest_sha256="m" * 64,
        authority_sha256="a" * 64, source_commit_sha="c" * 40,
        run_namespace="mineocclude-regime-a-prime-development-v0-2-stage1",
        stage_role="stage1", durable_verifier=lambda unit, receipt: True)
    with pytest.raises(PermissionError, match="belongs to namespace"):
        controller.run(authorized=True)


def test_controller_without_a_stage_role_refuses_to_run(tmp_path):
    from mineocclude.prospective.development_workflow import DurableController

    controller = DurableController(
        {"units": [{"unit_id": "u1", "receipt_path": str(tmp_path / "r.json"),
                    "scientific_run_id": "run", "command": ["cmd", "--stage", "stage1-capture"]}],
         "durable_prefix": "s3://bucket/prefix"},
        tmp_path / "state", tmp_path / "events", manifest_sha256="m" * 64,
        authority_sha256="a" * 64, source_commit_sha="c" * 40, run_namespace="run")
    with pytest.raises(EvidenceError, match="stage role binding"):
        controller.run(authorized=True)


# ------------------------------------------------------------- authorization


def frozen_provenance(tmp_path: Path, authority: dict, stage1: dict, **overrides) -> Path:
    """A provenance receipt whose bindings are genuinely correct for this tree.

    Only ``status`` and the commit-binding state are asserted rather than
    derived, because a real ``FROZEN_VERIFIED`` receipt cannot exist until the
    package is committed. Everything the authorization generator reproduces --
    authority, manifest, inventory, source closure -- is recomputed here from
    the same artefacts the generator will recompute from, so a mismatch means
    the generator failed to reproduce, not that the fixture disagreed.
    """
    probe = runtime_receipt(authority)
    execution = probe["probe_execution"]
    receipt = {
        "schema_version": "1.1",
        "artifact_id": "regime-a-prime-prospective-pre-outcome-provenance-v0.2",
        "classification": "DEVELOPMENT_ONLY", "status": "FROZEN_VERIFIED",
        "authority_sha256": sha256_file(AUTHORITY_PATH),
        "manifest_sha256": sha256_file(STAGE1_PATH),
        "stage1_manifest_sha256": sha256_file(STAGE1_PATH),
        "stage": "stage1-capture", "stage_role": "stage1",
        "run_namespace": stage1["run_namespace"],
        "run_inventory_sha256": stage_run_inventory_sha256(stage1),
        "runtime_critical_source_closure_sha256": runtime_critical_source_closure_sha256(ROOT),
        "runtime_identity_verified": True, "apparatus_identity_verified": True,
        "renderer_identity_verified": True,
        "source_paths_verified_bytes_and_modes": True,
        "remote_durable_prefix_read_write_probe_verified": True,
        "probe_evidence_sha256": probe_evidence_digest(execution),
        "probe_evidence_path_sha256": hashlib.sha256(
            canonical_json_bytes(probe)).hexdigest(),
        "probe_evidence": probe,
        "scientific_outcomes_observed": False,
        "confirmatory_collection_authorized": False,
        "independently_derived": True,
        "source_commit_binding_state": "BOUND_TO_FROZEN_COMMIT",
        "committed_bytes_equal_reviewed_bytes": True,
        "repository_clean_at_post_freeze_verification": True,
        "source_commit": generate_receipts.git("rev-parse", "HEAD"),
    }
    receipt.update(overrides)
    receipt["payload_sha256"] = canonical_payload_sha256(receipt)
    path = tmp_path / "provenance.json"
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return path


def test_stage1_authorization_is_derived_from_verified_prerequisites(
        tmp_path, authority, stage1, monkeypatch):
    real_git = generate_receipts.git
    monkeypatch.setattr(generate_receipts, "git", lambda *args:
                        "" if args and args[0] == "status" else real_git(*args))
    provenance = frozen_provenance(tmp_path, authority, stage1)
    output = tmp_path / "authorization.json"
    assert generate_receipts.build_stage1_authorization(provenance, output) == 0
    receipt = load_json(output)
    assert receipt["status"] == "FROZEN_AUTHORIZED"
    assert receipt["STAGE_1_COLLECTION_AUTHORIZED"] is True
    # Stage 2 stays unauthorized, and says so in every place that matters.
    assert receipt["STAGE_2_COLLECTION_AUTHORIZED"] is False
    assert receipt["confirmatory_collection_authorized"] is False
    assert receipt["authorized_stage"] == "stage1-capture"
    assert receipt["stage1_run_count"] == len(stage1["units"])
    assert receipt["stage1_run_inventory_sha256"] == stage_run_inventory_sha256(stage1)
    assert receipt["runtime_critical_source_closure_sha256"] == (
        runtime_critical_source_closure_sha256(ROOT))
    assert receipt["authorization_payload_sha256"] == canonical_payload_sha256(
        receipt, omit="authorization_payload_sha256")


def test_stage1_authorization_refuses_rehashed_summary_without_probe(
        tmp_path, authority, stage1):
    """True summary booleans and a fresh outer digest are not probe evidence."""
    provenance = frozen_provenance(tmp_path, authority, stage1)
    receipt = load_json(provenance)
    del receipt["probe_evidence"]
    receipt["payload_sha256"] = canonical_payload_sha256(receipt, omit="payload_sha256")
    provenance.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    with pytest.raises(EvidenceError, match="no concrete probe evidence"):
        generate_receipts.build_stage1_authorization(provenance, tmp_path / "out.json")


def test_stage1_authorization_replays_embedded_probe_instead_of_trusting_digest(
        tmp_path, authority, stage1):
    """A consistently rehashed probe from the wrong runtime still fails closed."""
    provenance = frozen_provenance(tmp_path, authority, stage1)
    receipt = load_json(provenance)
    probe = receipt["probe_evidence"]
    java = next(item for item in probe["probe_execution"]["invocations"]
                if item["command_id"] == "java_version")
    java["normalized_output"] = "openjdk version 1.8.0_402\n"
    java["normalized_output_sha256"] = hashlib.sha256(
        java["normalized_output"].encode()).hexdigest()
    probe["probe_evidence_sha256"] = probe_evidence_digest(probe["probe_execution"])
    probe["payload_sha256"] = canonical_payload_sha256(probe, omit="payload_sha256")
    receipt["probe_evidence_sha256"] = probe["probe_evidence_sha256"]
    receipt["probe_evidence_path_sha256"] = hashlib.sha256(
        canonical_json_bytes(probe)).hexdigest()
    receipt["payload_sha256"] = canonical_payload_sha256(receipt, omit="payload_sha256")
    provenance.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    with pytest.raises(EvidenceError, match="identity tokens"):
        generate_receipts.build_stage1_authorization(provenance, tmp_path / "out.json")


def test_stage1_authorization_refuses_dirty_repository(
        tmp_path, authority, stage1, monkeypatch):
    provenance = frozen_provenance(tmp_path, authority, stage1)
    real_git = generate_receipts.git
    monkeypatch.setattr(generate_receipts, "git", lambda *args:
                        " M source.py" if args and args[0] == "status" else real_git(*args))
    with pytest.raises(EvidenceError, match="clean frozen repository"):
        generate_receipts.build_stage1_authorization(provenance, tmp_path / "out.json")


def test_receipt_generator_is_inside_runtime_critical_source_closure():
    assert "scripts/regime_a_prime_qualification_v0_2/generate_receipts.py" in set(
        RUNTIME_CRITICAL_SOURCE_PATHS)


def test_durable_probe_lists_reads_and_verifies_exact_key_cleanup(monkeypatch):
    objects: dict[str, bytes] = {}
    calls: list[list[str]] = []

    def run(argv, *, input=None, check=False, capture_output=False, **_kwargs):
        calls.append(list(argv))
        if argv[1:3] == ["s3", "cp"] and argv[3] == "-":
            objects[argv[4]] = input
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        if argv[1:3] == ["s3", "cp"] and argv[4] == "-":
            return subprocess.CompletedProcess(argv, 0, objects[argv[3]], b"")
        if argv[1:3] == ["s3", "rm"]:
            objects.pop(argv[3])
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        if argv[1:3] == ["s3api", "list-objects-v2"]:
            bucket = argv[argv.index("--bucket") + 1]
            prefix = argv[argv.index("--prefix") + 1]
            keys = [{"Key": uri.split("/", 3)[3]} for uri in objects
                    if uri.startswith(f"s3://{bucket}/")
                    and uri.split("/", 3)[3].startswith(prefix)]
            return subprocess.CompletedProcess(
                argv, 0, json.dumps({"Contents": keys}).encode(), b"")
        raise AssertionError(argv)

    monkeypatch.setattr(generate_receipts.subprocess, "run", run)
    result = generate_receipts.durable_round_trip(
        "s3://prospective-bucket/isolated/stage1")
    assert result["verified"] is True
    assert result["listing_verified"] is True
    assert result["cleanup_verified"] is True
    assert result["probe_namespace"] == (
        "s3://prospective-bucket/isolated/stage1/.preflight/")
    assert objects == {}
    removal = next(call for call in calls if call[1:3] == ["s3", "rm"])
    assert "--recursive" not in removal
    assert removal[3] == result["probe_key"]
    assert sum(call[1:3] == ["s3api", "list-objects-v2"] for call in calls) == 2


def test_durable_probe_cleans_only_its_key_after_readback_failure(monkeypatch):
    objects: dict[str, bytes] = {"s3://prospective-bucket/isolated/stage1/existing": b"keep"}

    def run(argv, *, input=None, check=False, capture_output=False, **_kwargs):
        if argv[1:3] == ["s3", "cp"] and argv[3] == "-":
            objects[argv[4]] = input
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        if argv[1:3] == ["s3", "cp"] and argv[4] == "-":
            return subprocess.CompletedProcess(argv, 0, b"wrong bytes", b"")
        if argv[1:3] == ["s3", "rm"]:
            objects.pop(argv[3])
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        if argv[1:3] == ["s3api", "list-objects-v2"]:
            bucket = argv[argv.index("--bucket") + 1]
            prefix = argv[argv.index("--prefix") + 1]
            keys = [{"Key": uri.split("/", 3)[3]} for uri in objects
                    if uri.startswith(f"s3://{bucket}/")
                    and uri.split("/", 3)[3].startswith(prefix)]
            return subprocess.CompletedProcess(
                argv, 0, json.dumps({"Contents": keys}).encode(), b"")
        raise AssertionError(argv)

    monkeypatch.setattr(generate_receipts.subprocess, "run", run)
    with pytest.raises(EvidenceError, match="different bytes"):
        generate_receipts.durable_round_trip(
            "s3://prospective-bucket/isolated/stage1")
    assert objects == {"s3://prospective-bucket/isolated/stage1/existing": b"keep"}


def test_pre_freeze_provenance_cannot_authorize_stage1(tmp_path, authority, stage1):
    """Step 1 of the two-step binding names no commit, so it authorizes nothing."""
    provenance = frozen_provenance(tmp_path, authority, stage1,
                                   status="PRE_FREEZE_VERIFIED",
                                   source_commit_binding_state="AWAITING_FREEZE",
                                   source_commit=None)
    with pytest.raises(EvidenceError, match="prerequisites are unmet"):
        generate_receipts.build_stage1_authorization(provenance, tmp_path / "out.json")
    assert not (tmp_path / "out.json").exists()


@pytest.mark.parametrize("field,value", [
    ("runtime_identity_verified", False),
    ("apparatus_identity_verified", False),
    ("renderer_identity_verified", False),
    ("remote_durable_prefix_read_write_probe_verified", False),
    ("source_paths_verified_bytes_and_modes", False),
    ("authority_sha256", "0" * 64),
    ("manifest_sha256", "0" * 64),
    ("stage1_manifest_sha256", "0" * 64),
    ("run_inventory_sha256", "0" * 64),
    ("runtime_critical_source_closure_sha256", "0" * 64),
    ("run_namespace", "mineocclude-regime-a-prime-development-v0-2-stage2"),
    ("stage", "stage2-capture"),
    ("source_commit", "0" * 40),
    ("scientific_outcomes_observed", True),
])
def test_mismatched_prerequisite_blocks_authorization(tmp_path, authority, stage1,
                                                      field, value):
    provenance = frozen_provenance(tmp_path, authority, stage1, **{field: value})
    with pytest.raises(EvidenceError, match="prerequisites are unmet"):
        generate_receipts.build_stage1_authorization(provenance, tmp_path / "out.json")
    assert not (tmp_path / "out.json").exists()


def test_edited_provenance_payload_digest_blocks_authorization(tmp_path, authority, stage1):
    """A receipt edited after assembly, with every binding otherwise correct."""
    path = frozen_provenance(tmp_path, authority, stage1)
    receipt = load_json(path)
    receipt["generated_by"] = "an-untracked-hand-edit"
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    with pytest.raises(EvidenceError, match="payload digest mismatch"):
        generate_receipts.build_stage1_authorization(path, tmp_path / "out.json")


def test_launch_gate_refuses_a_pre_freeze_provenance_receipt(tmp_path, authority, stage1):
    provenance = frozen_provenance(tmp_path, authority, stage1,
                                   status="PRE_FREEZE_VERIFIED",
                                   source_commit_binding_state="AWAITING_FREEZE")
    with pytest.raises(PermissionError, match="rejects status"):
        require_preoutcome_provenance(load_json(provenance),
            authority_path=AUTHORITY_PATH, manifest_path=STAGE1_PATH,
            required_source_paths=[ROOT / "src/mineocclude/prospective/development_workflow.py"])


def test_launch_gate_refuses_a_stage2_namespace_provenance_receipt(tmp_path, authority, stage1):
    provenance = frozen_provenance(
        tmp_path, authority, stage1,
        run_namespace="mineocclude-regime-a-prime-development-v0-2-stage2")
    with pytest.raises(PermissionError, match="rejects run_namespace"):
        require_preoutcome_provenance(load_json(provenance),
            authority_path=AUTHORITY_PATH, manifest_path=STAGE1_PATH,
            required_source_paths=[ROOT / "src/mineocclude/prospective/development_workflow.py"])
