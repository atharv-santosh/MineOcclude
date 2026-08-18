"""Time-invariant source verification for completed campaigns.

``verify_runtime_source_hashes`` answers one question -- "did the source that
produced this evidence match what was expected" -- and until this module it
could only consult one authority for the expectation: the working tree. That is
correct for a campaign about to run, and wrong for one that already ran. Every
gate below the runtime-provenance receipt is scientific; this one is not, and
its failure mode was to make a *frozen scientific PASS* unverifiable for no
reason other than that HEAD had moved. Adding a path to the runtime-critical
closure was fatal by itself, through the coverage check, before a single hash
was compared.

The repair gives the function a second, explicitly supplied authority: the pins
recorded in the campaign's own frozen pre-outcome provenance receipt, bound by
``bind_historical_source_closure`` only after that receipt has been verified end
to end. Nothing is relaxed -- historical mode still demands exact equality over
the complete inventory -- and nothing is skipped. The current tree remains the
authority for any campaign that has not run yet.

Four groups:

* ``time invariance``  -- the frozen v0.4 PASS re-derives across a moved HEAD,
                          and specifically across a *grown* closure;
* ``separation``       -- the historical and current bindings are distinct, and
                          neither is substituted for the other;
* ``receipt``          -- one mutated field at a time in the historical
                          provenance, each of which must fail closed;
* ``evidence``         -- one mutated source binding at a time in the Stage-1
                          evidence, each of which must fail closed.

Nothing here authorizes a campaign, collects data, or writes into an evidence
directory. The frozen artifacts are opened read-only and every mutation is made
on an in-memory copy.
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from pathlib import Path

import pytest

from mineocclude.prospective.development_workflow import (
    RUNTIME_CRITICAL_SOURCE_PATHS, EvidenceError, HistoricalSourceClosure,
    Stage1Evaluator, bind_historical_source_closure, canonical_json_bytes,
    canonical_payload_sha256, load_json, runtime_critical_source_closure_sha256,
    sha256_file, verify_runtime_source_hashes,
)
from mineocclude.prospective.package_binding import (
    artifact_version_tag, provenance_artifact_id_for, stage1_decision_artifact_id,
)

ROOT = Path(__file__).resolve().parents[2]
PACKAGES = ROOT / "docs/status/integration/regime_a_prime_qualification_v0_1"
PACKAGE = PACKAGES / "prospective_development_authority_v0_4"
AUTHORITY_PATH = PACKAGE / "authority_parameters.json"
STAGE1_PATH = PACKAGE / "stage1_manifest.json"

#: The completed v0.4 Stage-1 campaign, read-only and outside the repository.
CAMPAIGN = Path("/home/sagemaker-user/mineocclude-stage1-successor-046b34a")
LAUNCH = CAMPAIGN / "collection_launch_01_20260817T225203Z"
FROZEN_DECISION = LAUNCH / "stage1_decision.json"
FROZEN_EVIDENCE = LAUNCH / "stage1_evidence.json"
#: Frozen *before* collection, which is why it can say what the campaign ran.
FROZEN_PROVENANCE = CAMPAIGN / "preoutcome_provenance.json"

#: The commit and closure 046b34a was collected under.
CAMPAIGN_COMMIT = "046b34a3634f183b306fb48effaf62bf22d39d0a"
CAMPAIGN_CLOSURE = "8d947677910628024a234de39466c3938fc8e3a7d13ab3bb082f0663f39eef91"

FAKE = "f" * 64
#: A closure member mutated by several cases below.
VICTIM = "src/mineocclude/prospective/development_workflow.py"


def _require(path: Path):
    if not path.is_file():
        pytest.skip(f"frozen v0.4 Stage-1 artifact is absent: {path}")
    return path


@pytest.fixture(scope="module")
def authority():
    return load_json(AUTHORITY_PATH)


@pytest.fixture(scope="module")
def manifest():
    return load_json(STAGE1_PATH)


@pytest.fixture(scope="module")
def frozen_decision():
    return load_json(_require(FROZEN_DECISION))


@pytest.fixture
def evidence():
    return load_json(_require(FROZEN_EVIDENCE))


@pytest.fixture
def provenance():
    return load_json(_require(FROZEN_PROVENANCE))


@pytest.fixture(scope="module")
def expected_provenance_id(manifest):
    return provenance_artifact_id_for(artifact_version_tag(manifest.get("artifact_id")))


def reseal(receipt: dict) -> dict:
    """Recompute the payload digest so a tamper is not caught by that alone.

    Every mutation below is resealed unless the case is specifically about the
    payload digest. A control that fails only because the digest stopped
    reproducing would prove nothing about the binding under test.
    """
    receipt.pop("payload_sha256", None)
    receipt["payload_sha256"] = canonical_payload_sha256(receipt)
    return receipt


def bind(provenance: dict, *, artifact_id: str, authority_sha256: str | None = None,
         manifest_sha256: str | None = None) -> HistoricalSourceClosure:
    return bind_historical_source_closure(
        provenance, provenance_sha256=sha256_file(FROZEN_PROVENANCE),
        expected_artifact_id=artifact_id,
        authority_sha256=authority_sha256 or sha256_file(AUTHORITY_PATH),
        manifest_sha256=manifest_sha256 or sha256_file(STAGE1_PATH))


def rederive(authority: dict, manifest: dict, evidence: dict,
             closure: HistoricalSourceClosure | None) -> dict:
    authority_sha, manifest_sha = sha256_file(AUTHORITY_PATH), sha256_file(STAGE1_PATH)
    return Stage1Evaluator(
        authority, manifest, authority_sha256=authority_sha,
        manifest_sha256=manifest_sha, historical_source_closure=closure).evaluate(
            evidence).to_dict(
                authority_sha256=authority_sha, manifest_sha256=manifest_sha,
                evidence_sha256=sha256_file(FROZEN_EVIDENCE),
                artifact_id=stage1_decision_artifact_id(manifest))


# ======================================================================
# time invariance
# ======================================================================


def test_the_working_tree_has_actually_moved_since_the_campaign(provenance):
    """The precondition every test below depends on.

    If this ever fails the suite is running at exactly 046b34a with a clean
    tree, where the old semantics also worked and nothing here is being tested.
    """
    assert provenance["runtime_critical_source_closure_sha256"] == CAMPAIGN_CLOSURE
    assert runtime_critical_source_closure_sha256(ROOT) != CAMPAIGN_CLOSURE


def test_frozen_pass_rederives_byte_identically_against_its_own_provenance(
        authority, manifest, evidence, provenance, frozen_decision, expected_provenance_id):
    """The property the repair exists for: a later HEAD does not invalidate 046b34a."""
    closure = bind(provenance, artifact_id=expected_provenance_id)
    assert rederive(authority, manifest, evidence, closure) == frozen_decision


def test_the_rederived_decision_is_a_genuine_pass_on_every_gate(
        authority, manifest, evidence, provenance, expected_provenance_id):
    """Time invariance must not have been bought by weakening a scientific gate."""
    reproduced = rederive(authority, manifest, evidence,
                          bind(provenance, artifact_id=expected_provenance_id))
    assert reproduced["status"] == "PASS"
    assert reproduced["reasons"] == []
    assert len(reproduced["gates"]) == 9
    assert all(gate["status"] == "PASS" for gate in reproduced["gates"].values())


def test_growing_the_closure_no_longer_invalidates_the_frozen_campaign(
        authority, manifest, evidence, provenance, frozen_decision,
        expected_provenance_id, monkeypatch):
    """Adding a runtime-critical path was fatal by itself under the old rule.

    The coverage check compared the evidence's recorded paths to the *live*
    ``RUNTIME_CRITICAL_SOURCE_PATHS``, so extending the closure -- exactly what
    Stage-2 preparation must do -- refused every completed campaign before any
    hash was examined. The historical closure is the campaign's own, so growth
    of the current inventory is now irrelevant to it.
    """
    monkeypatch.setattr(
        "mineocclude.prospective.development_workflow.RUNTIME_CRITICAL_SOURCE_PATHS",
        RUNTIME_CRITICAL_SOURCE_PATHS + ("src/mineocclude/prospective/stage2_readout.py",))
    closure = bind(provenance, artifact_id=expected_provenance_id)
    assert len(closure.source_pins) == 56
    assert rederive(authority, manifest, evidence, closure) == frozen_decision


def test_the_bound_closure_is_the_campaigns_own(provenance, expected_provenance_id):
    closure = bind(provenance, artifact_id=expected_provenance_id)
    assert closure.source_commit == CAMPAIGN_COMMIT
    assert closure.closure_sha256 == CAMPAIGN_CLOSURE
    assert closure.artifact_id == expected_provenance_id
    assert closure.provenance_sha256 == sha256_file(FROZEN_PROVENANCE)
    # The recomputed digest over the itemized inventory, not a copied field.
    assert hashlib.sha256(canonical_json_bytes(
        dict(closure.source_pins))).hexdigest() == CAMPAIGN_CLOSURE


# ======================================================================
# separation -- historical and current bindings are distinct
# ======================================================================


def test_current_mode_still_rehashes_the_working_tree(evidence):
    """Requirement 3, from the other direction.

    The historical campaign's pins must NOT verify against today's tree. If this
    ever passes, historical semantics have leaked into the current-source mode
    and a stale receipt could authorize an edited apparatus.
    """
    pins = evidence["runs"][0]["runtime_provenance_receipt"]["runtime_source_sha256"]
    with pytest.raises(EvidenceError, match="runtime source bytes mismatch"):
        verify_runtime_source_hashes(pins)


def test_current_mode_accepts_the_tree_it_rehashes():
    """The unchanged half of the contract still holds."""
    verify_runtime_source_hashes(
        {relative: sha256_file(ROOT / relative) for relative in RUNTIME_CRITICAL_SOURCE_PATHS})


def test_current_mode_still_refuses_a_single_edited_file():
    pins = {relative: sha256_file(ROOT / relative)
            for relative in RUNTIME_CRITICAL_SOURCE_PATHS}
    pins[VICTIM] = FAKE
    with pytest.raises(EvidenceError, match="runtime source bytes mismatch"):
        verify_runtime_source_hashes(pins)


def test_current_mode_still_refuses_incomplete_coverage():
    pins = {relative: sha256_file(ROOT / relative)
            for relative in RUNTIME_CRITICAL_SOURCE_PATHS}
    del pins[VICTIM]
    with pytest.raises(EvidenceError, match="coverage is incomplete"):
        verify_runtime_source_hashes(pins)


def test_evaluating_without_a_historical_closure_uses_the_current_tree(
        authority, manifest, evidence, frozen_decision):
    """A Stage1Evaluator given no historical closure keeps the old semantics.

    This is the mode the controller and the evidence builder run in, and it is
    what qualified 046b34a live. Against a moved tree it must refuse -- which is
    precisely why the barrier had to be given the campaign's own record instead.
    """
    assert rederive(authority, manifest, evidence, None) != frozen_decision


def test_an_empty_historical_closure_is_refused():
    """A degenerate closure must not vacuously satisfy the coverage check."""
    with pytest.raises(EvidenceError, match="historical runtime source closure is empty"):
        verify_runtime_source_hashes({}, expected_source_pins={})


# ======================================================================
# receipt -- one mutated historical provenance field at a time
# ======================================================================


def test_a_predecessor_provenance_identity_is_refused(provenance, expected_provenance_id):
    """Requirement 8: a v0.2/v0.3 receipt names a real but different closure."""
    for tag in ("v0.2", "v0.3"):
        foreign = reseal({**deepcopy(provenance),
                          "artifact_id": f"regime-a-prime-prospective-pre-outcome-provenance-{tag}"})
        with pytest.raises(EvidenceError, match="but .* was required"):
            bind(foreign, artifact_id=expected_provenance_id)


@pytest.mark.parametrize("receipt_path", [
    CAMPAIGN.parent / "mineocclude-stage1-successor-134a242" / "pre_outcome_provenance_receipt.json",
    CAMPAIGN.parent / "mineocclude-stage1-successor-1234d319" / "pre_outcome_provenance_receipt.json",
])
def test_a_real_predecessor_receipt_cannot_stand_in(receipt_path, expected_provenance_id):
    """Not a synthetic identity swap: these are genuine frozen receipts."""
    if not receipt_path.is_file():
        pytest.skip(f"predecessor receipt is absent: {receipt_path}")
    with pytest.raises(EvidenceError):
        bind(load_json(receipt_path), artifact_id=expected_provenance_id)


@pytest.mark.parametrize("field,value", [
    ("status", "DRAFT"),
    ("status", "PRE_FREEZE_VERIFIED"),
    ("scientific_outcomes_observed", True),
    ("confirmatory_collection_authorized", True),
    ("independently_derived", False),
    ("source_paths_verified_bytes_and_modes", False),
    ("source_commit_binding_state", "PRE_FREEZE_VERIFIED"),
    ("committed_bytes_equal_reviewed_bytes", False),
    ("repository_clean_at_post_freeze_verification", False),
])
def test_one_broken_provenance_invariant_at_a_time(
        provenance, expected_provenance_id, field, value):
    tampered = reseal({**deepcopy(provenance), field: value})
    with pytest.raises(EvidenceError, match="historical provenance"):
        bind(tampered, artifact_id=expected_provenance_id)


def test_an_edited_provenance_payload_is_refused(provenance, expected_provenance_id):
    """Without resealing: the document's own digest must catch the edit."""
    tampered = deepcopy(provenance)
    tampered["source_commit"] = "0" * 40
    with pytest.raises(EvidenceError, match="payload digest does not reproduce"):
        bind(tampered, artifact_id=expected_provenance_id)


def test_a_malformed_source_commit_is_refused(provenance, expected_provenance_id):
    for bogus in ("", "046b34a", "z" * 40, None):
        tampered = reseal({**deepcopy(provenance), "source_commit": bogus})
        with pytest.raises(EvidenceError, match="no frozen source commit"):
            bind(tampered, artifact_id=expected_provenance_id)


@pytest.mark.parametrize("field", [
    "runtime_critical_source_closure_sha256",
    "reviewed_runtime_critical_source_closure_sha256",
])
def test_a_rewritten_closure_sha_does_not_reproduce(
        provenance, expected_provenance_id, field):
    """The summary digest and the itemized inventory cannot be made to disagree."""
    tampered = reseal({**deepcopy(provenance), field: FAKE})
    with pytest.raises(EvidenceError, match="does not reproduce from its inventory"):
        bind(tampered, artifact_id=expected_provenance_id)


def test_a_mutated_pin_inside_the_provenance_inventory_is_refused(
        provenance, expected_provenance_id):
    tampered = deepcopy(provenance)
    tampered["source_bindings"][VICTIM]["sha256"] = FAKE
    with pytest.raises(EvidenceError, match="does not reproduce from its inventory"):
        bind(reseal(tampered), artifact_id=expected_provenance_id)


def test_a_path_dropped_from_the_provenance_inventory_is_refused(
        provenance, expected_provenance_id):
    tampered = deepcopy(provenance)
    del tampered["source_bindings"]["src/mineocclude/vision/magenta.py"]
    with pytest.raises(EvidenceError, match="does not reproduce from its inventory"):
        bind(reseal(tampered), artifact_id=expected_provenance_id)


def test_a_path_smuggled_into_the_provenance_inventory_is_refused(
        provenance, expected_provenance_id):
    tampered = deepcopy(provenance)
    tampered["source_bindings"]["src/mineocclude/smuggled.py"] = {
        "git_mode": "100644", "sha256": FAKE}
    with pytest.raises(EvidenceError, match="does not reproduce from its inventory"):
        bind(reseal(tampered), artifact_id=expected_provenance_id)


def test_a_malformed_inventory_entry_is_refused(provenance, expected_provenance_id):
    tampered = deepcopy(provenance)
    tampered["source_bindings"][VICTIM] = {
        "sha256": tampered["source_bindings"][VICTIM]["sha256"]}
    with pytest.raises(EvidenceError, match="source binding is malformed"):
        bind(reseal(tampered), artifact_id=expected_provenance_id)


def test_a_missing_inventory_is_refused(provenance, expected_provenance_id):
    for empty in ({}, None):
        tampered = reseal({**deepcopy(provenance), "source_bindings": empty})
        with pytest.raises(EvidenceError, match="records no source inventory"):
            bind(tampered, artifact_id=expected_provenance_id)


def test_probe_evidence_pinning_another_closure_is_refused(
        provenance, expected_provenance_id):
    """The receipt's two independent records of what ran must agree."""
    tampered = deepcopy(provenance)
    tampered["probe_evidence"]["runtime_source_sha256"][VICTIM] = FAKE
    with pytest.raises(EvidenceError, match="pins a different source closure"):
        bind(reseal(tampered), artifact_id=expected_provenance_id)


def test_a_receipt_without_probe_evidence_is_refused(provenance, expected_provenance_id):
    tampered = reseal({**deepcopy(provenance), "probe_evidence": None})
    with pytest.raises(EvidenceError, match="no embedded probe evidence"):
        bind(tampered, artifact_id=expected_provenance_id)


@pytest.mark.parametrize("field", ["authority_sha256", "manifest_sha256"])
def test_a_provenance_bound_to_another_package_is_refused(
        provenance, expected_provenance_id, field):
    """A sibling campaign's receipt cannot supply this campaign's closure."""
    with pytest.raises(EvidenceError, match="binding mismatch"):
        bind(provenance, artifact_id=expected_provenance_id,
             **{field.replace("manifest_sha256", "manifest_sha256"): FAKE}
             if field == "manifest_sha256" else {"authority_sha256": FAKE})


# ======================================================================
# evidence -- one mutated Stage-1 source binding at a time
# ======================================================================


def _refuses(authority, manifest, evidence, provenance, expected_provenance_id,
             frozen_decision):
    closure = bind(provenance, artifact_id=expected_provenance_id)
    try:
        reproduced = rederive(authority, manifest, evidence, closure)
    except (EvidenceError, KeyError, TypeError, ValueError):
        return
    assert reproduced != frozen_decision, "tampered evidence reproduced the frozen PASS"


def test_a_mutated_unit_source_pin_is_refused(
        authority, manifest, evidence, provenance, expected_provenance_id, frozen_decision):
    evidence["runs"][0]["runtime_provenance_receipt"]["runtime_source_sha256"][VICTIM] = FAKE
    _refuses(authority, manifest, evidence, provenance, expected_provenance_id,
             frozen_decision)


def test_a_unit_naming_a_different_source_commit_is_refused(
        authority, manifest, evidence, provenance, expected_provenance_id, frozen_decision):
    """The evidence's own freeze binding, not just its hashes.

    Without this a receipt from another campaign that happened to agree on every
    pin would verify against these, because the pins alone do not say *when*.
    """
    evidence["runs"][3]["runtime_provenance_receipt"]["head"] = "0" * 40
    _refuses(authority, manifest, evidence, provenance, expected_provenance_id,
             frozen_decision)


def test_incomplete_unit_source_coverage_is_refused(
        authority, manifest, evidence, provenance, expected_provenance_id, frozen_decision):
    del evidence["runs"][2]["runtime_provenance_receipt"]["runtime_source_sha256"][VICTIM]
    _refuses(authority, manifest, evidence, provenance, expected_provenance_id,
             frozen_decision)


def test_a_rewritten_probe_source_hash_is_refused(
        authority, manifest, evidence, provenance, expected_provenance_id, frozen_decision):
    evidence["runs"][1]["runtime_provenance_receipt"]["probe_execution"][
        "probe_source_sha256"] = FAKE
    _refuses(authority, manifest, evidence, provenance, expected_provenance_id,
             frozen_decision)


def test_a_probe_source_outside_the_closure_is_refused(
        authority, manifest, evidence, provenance, expected_provenance_id, frozen_decision):
    evidence["runs"][1]["runtime_provenance_receipt"]["probe_execution"][
        "probe_source_path"] = "src/mineocclude/not_in_closure.py"
    _refuses(authority, manifest, evidence, provenance, expected_provenance_id,
             frozen_decision)
