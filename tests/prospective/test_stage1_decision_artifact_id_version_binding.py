"""The Stage-1 decision identity follows the package version, through the binding.

``Decision.to_dict`` serialized a module-level literal::

    "artifact_id": "regime-a-prime-stage1-decision-v0.2"

and ``require_stage2_authorization`` compared the presented decision against that
same literal. Every other artifact identity in this repository is version-aware
-- the authority, both manifests, the authorization receipt and the pre-outcome
provenance receipt all resolve through the package binding -- and this one was
not.

It never reached a live gate: Stage-2 has never been authorized, and the Stage-1
gate itself does not read the decision's own identity, so the ``134a242``
decision was correct in substance while mislabelled ``v0.2``. That is exactly why
it is repaired *now*, prospectively, while Stage-2 is still unauthorized. Left
alone it would have become a live cross-version substitution hole the moment a
v0.3 Stage-1 produced a PASS: the v0.3 Stage-2 gate would have refused its own
genuine v0.3 decision and accepted a v0.2 one.

These tests attack the repair from both sides -- v0.3 is emitted and demanded,
v0.2 replay is unchanged, the two cannot be crossed, and an unversioned manifest
fails closed rather than defaulting to either.

Nothing here authorizes Stage-2. The last test asserts it stays unauthorized.
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from mineocclude.prospective.development_workflow import (  # noqa: E402
    Decision, EvidenceError, canonical_payload_sha256, load_json, sha256_file,
)
from mineocclude.prospective.package_binding import (  # noqa: E402
    PackageBindingError, resolve_package_binding, stage1_decision_artifact_id,
    stage1_decision_artifact_id_for,
)
from tests.prospective.test_development_authority_v0_2_repair import (  # noqa: E402
    authorize, bound_stage2,
)

V0_2_DECISION_ARTIFACT_ID = "regime-a-prime-stage1-decision-v0.2"
V0_3_DECISION_ARTIFACT_ID = "regime-a-prime-stage1-decision-v0.3"


def test_each_package_version_gets_its_own_decision_identity():
    assert stage1_decision_artifact_id_for("v0.2") == V0_2_DECISION_ARTIFACT_ID
    assert stage1_decision_artifact_id_for("v0.3") == V0_3_DECISION_ARTIFACT_ID


@pytest.mark.parametrize("version_tag,expected", [
    ("v0.2", V0_2_DECISION_ARTIFACT_ID),
    ("v0.3", V0_3_DECISION_ARTIFACT_ID),
])
def test_identity_is_read_out_of_the_bound_package_manifest(version_tag, expected):
    """Resolved from the manifest actually evaluated, not from a literal."""
    binding = resolve_package_binding(version_tag, ROOT)
    manifest = load_json(binding.stage1_manifest_path)
    assert stage1_decision_artifact_id(manifest) == expected


@pytest.mark.parametrize("artifact_id", [None, "", "regime-a-prime-stage1-manifest", 17])
def test_an_unversioned_manifest_identity_fails_closed(artifact_id):
    """No default. A manifest that cannot say which experiment it is, is refused."""
    with pytest.raises(PackageBindingError):
        stage1_decision_artifact_id({"artifact_id": artifact_id})


def test_serializing_a_decision_without_an_identity_is_refused():
    """The parameter is required, so no caller can fall back to a literal again."""
    decision = Decision("PASS", {"unit_completeness": {"status": "PASS"}}, ())
    with pytest.raises(TypeError):
        decision.to_dict(authority_sha256="a" * 64, manifest_sha256="b" * 64,
                         evidence_sha256="e" * 64)
    for empty in (None, ""):
        with pytest.raises(EvidenceError):
            decision.to_dict(authority_sha256="a" * 64, manifest_sha256="b" * 64,
                             evidence_sha256="e" * 64, artifact_id=empty)


def test_a_serialized_decision_carries_the_identity_it_was_given():
    decision = Decision("PASS", {"unit_completeness": {"status": "PASS"}}, ())
    payload = decision.to_dict(authority_sha256="a" * 64, manifest_sha256="b" * 64,
                               evidence_sha256="e" * 64,
                               artifact_id=V0_3_DECISION_ARTIFACT_ID)
    assert payload["artifact_id"] == V0_3_DECISION_ARTIFACT_ID
    assert payload["stage2_collection_authorized"] is False
    assert payload["confirmatory_interpretation_authorized"] is False


def _rebind(bundle, decision):
    """Rewrite a Stage-2 bundle around a mutated decision, consistently.

    Every digest that depends on the decision is recomputed, so the bundle is
    internally sound and the decision's *identity* is the only defect left. A
    refusal therefore proves the identity gate fired, not a stale hash.
    """
    (authority, provenance, stage1_manifest, evidence_path, decision_path, _,
     manifest_path, manifest, _) = bundle
    decision_path.write_text(json.dumps(decision, sort_keys=True) + "\n")
    manifest = deepcopy(manifest)
    manifest["stage1_decision_sha256"] = sha256_file(decision_path)
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
    receipt = {"schema_version": "1.1",
        "artifact_id": "regime-a-prime-stage2-post-stage1-authorization-v0.2",
        "status": "FROZEN_AUTHORIZED", "STAGE_2_COLLECTION_AUTHORIZED": True,
        "confirmatory_collection_authorized": False, "authority_sha256": sha256_file(authority),
        "stage1_manifest_sha256": sha256_file(stage1_manifest),
        "stage1_decision_sha256": sha256_file(decision_path),
        "stage1_evidence_sha256": sha256_file(evidence_path),
        "stage1_status": "PASS",
        "stage2_manifest_sha256": sha256_file(manifest_path), "source_commit_sha": "c" * 40,
        "expected_run_namespace": manifest["run_namespace"],
        "preoutcome_provenance_receipt_sha256": sha256_file(provenance)}
    receipt["authorization_payload_sha256"] = canonical_payload_sha256(receipt)
    return (authority, provenance, stage1_manifest, evidence_path, decision_path, decision,
            manifest_path, manifest, receipt)


def test_the_stage2_gate_refuses_a_decision_from_another_package_version(tmp_path):
    """A v0.3-identity decision cannot unlock a v0.2 Stage-2, and vice versa.

    The bundle is the v0.2 package's, so the gate must demand
    ``...-decision-v0.2``. Presenting the v0.3 identity -- with every dependent
    digest rebound so nothing else is wrong -- must still be refused. This is the
    substitution the old literal comparison would have permitted in the mirror
    direction.
    """
    bundle = bound_stage2(tmp_path)
    genuine_decision = bundle[5]
    assert genuine_decision["artifact_id"] == V0_2_DECISION_ARTIFACT_ID
    crossed = dict(genuine_decision, artifact_id=V0_3_DECISION_ARTIFACT_ID)
    with pytest.raises(PermissionError, match="genuine Stage-1 PASS decision is required"):
        authorize(_rebind(bundle, crossed))


def test_the_stage2_gate_still_accepts_its_own_versions_genuine_decision(tmp_path):
    """The repair refuses the wrong version without refusing the right one.

    A gate that failed closed on everything would pass the test above while
    making Stage-2 permanently unreachable, so the positive control runs on the
    identical rebinding path.
    """
    bundle = bound_stage2(tmp_path)
    authorize(_rebind(bundle, dict(bundle[5])))


def test_every_other_stage2_condition_is_still_required(tmp_path):
    """Correct identity alone authorizes nothing."""
    bundle = bound_stage2(tmp_path)
    failed = dict(bundle[5], status="FAIL")
    assert failed["artifact_id"] == V0_2_DECISION_ARTIFACT_ID
    with pytest.raises(PermissionError, match="genuine Stage-1 PASS decision is required"):
        authorize(_rebind(bundle, failed))


def test_the_stage2_authorization_identity_is_version_aware_too():
    """The sibling literal on the same code path, read from the stage table.

    ``require_stage2_authorization`` also spelled the *authorization* receipt's
    identity as a v0.2 literal, so a v0.3 Stage-2 would have demanded a v0.2
    authorization receipt. The authority already declares the correct value per
    version in ``stage_binding_policy``.
    """
    for version_tag in ("v0.2", "v0.3"):
        binding = resolve_package_binding(version_tag, ROOT)
        authority = load_json(binding.authority_path)
        declared = (authority["stage_binding_policy"]["stages"]["stage2-capture"]
                    ["authorization_artifact_id"])
        assert declared == f"regime-a-prime-stage2-post-stage1-authorization-{version_tag}"


def test_stage2_remains_unauthorized_in_every_package():
    """STAGE2_AUTHORIZED=false. This session authorizes nothing."""
    for version_tag in ("v0.2", "v0.3"):
        binding = resolve_package_binding(version_tag, ROOT)
        authority = load_json(binding.authority_path)
        stage2 = load_json(binding.stage2_manifest_path)
        assert authority["STAGE_2_COLLECTION_AUTHORIZED"] is False
        assert authority["confirmatory_collection_authorized"] is False
        assert stage2["STAGE_2_COLLECTION_AUTHORIZED"] is False
