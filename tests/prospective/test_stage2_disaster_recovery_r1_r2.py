#!/usr/bin/env python3
"""Regression suite for the two disaster-recovery defects, R1 and R2.

A SageMaker Space host rebuild wiped ``/mnt/sagemaker-nvme`` in full. Nothing
scientific was lost -- all fifty capture trees, all fifty capture receipts and
the physical-gate result were durable in S3 -- but two implementation defects
made intact evidence unreachable, which is operationally identical to losing it.

**R1** -- ``restore-unit`` derived the CAPTURE source commit from the PROCESSING
provenance receipt. ``require_preoutcome_provenance`` pins that receipt to the
live ``git HEAD``, so the composition of two individually correct rules produced
a third, incorrect one: *the commit that took a capture must be the commit
checked out now*. This campaign is mixed-freeze by design -- T1 was reused from
``49f0cca`` while the other forty-nine were taken under ``cb16335`` -- so no
value of ``HEAD`` satisfies it and the cohort was unrestorable. The repair reads
the capture freeze from the unit's OWN durable state record and then requires
capture admission at that commit, which is a strictly larger set of conditions
than the commit-equality proxy it replaces.

**R2** -- the physical-gate receipt WRAPPER was local-only and is genuinely gone.
Its durable PAYLOAD and checksum manifest survived, immutable. The repair admits
that surviving evidence on the same load-bearing condition wrapper admission
uses -- gate-critical closure equality -- and never reconstructs the wrapper.

Both classes open with the original failure, prove the repair, and then prove the
repair did not weaken the control it replaced. That last part carries most of the
weight here: on a recovery path, "make it stop refusing" is precisely the wrong
fix, and every test below that ends in a refusal exists to pin that down.
"""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src"),
                str(ROOT / "scripts/regime_a_prime_qualification_v0_1"),
                str(ROOT / "scripts/regime_a_prime_qualification_v0_2")]

from mineocclude.prospective import physical_gate_admission as pga  # noqa: E402
from mineocclude.prospective.capture_admission import (  # noqa: E402
    CaptureAdmissionError, build_capture_admission_context,
    load_capture_provenance_authority,
)
from mineocclude.prospective.development_workflow import (  # noqa: E402
    DurableStateError, canonical_payload_sha256, durable_capture_source_commit,
    durable_unit_state_uri, durable_unit_uri, restore_durable_unit_state,
    sha256_file, CAPTURE_RECEIPT_OBJECT, UNIT_STATE_OBJECT,
)
from mineocclude.prospective.package_binding import package_directory  # noqa: E402

PACKAGE = package_directory("v0.4", ROOT)
MANIFEST_PATH = PACKAGE / "stage2_locked_manifest.json"
AUTHORITY_PATH = PACKAGE / "authority_parameters.json"

#: The capture freeze T1 was reused from, and the freeze the other 49 were taken
#: under. That these differ is the whole point: the cohort is legitimately
#: cross-freeze, and any rule requiring one commit for all of it is unsatisfiable.
T1_CAPTURE_COMMIT = "49f0cca9d0ec6d204444bf3c0d1fa5fc7e263936"
OTHER_CAPTURE_COMMIT = "cb16335c936659b8105173db15f5a95d2be230d2"
#: The freeze that produced the physical-gate PASS whose wrapper was destroyed.
GATE_SOURCE_COMMIT = "76098ae8f4dcb9103ad8661cc0e0408de06d627a"
#: The frozen capture apparatus. Neither repair may move it.
CAPTURE_CRITICAL_CLOSURE = "b64bc70071d2efbbd90e04ca31f4fdaf508498eb51e36c69b584c3602284fa68"
#: The frozen gate verdict closure. Equal at the gate source and at every
#: successor that may admit it.
GATE_CRITICAL_CLOSURE = "199ae4dd4a29d2dad9ee47984268171a5a667ab7f3adee48323f178dc946fa89"
#: The processing freeze this recovery successor departs from: the one that
#: consumed the wrapper while it still existed.
PREDECESSOR_PROCESSING_COMMIT = "93a7cc4ed77a5a75f55e769f437995b011623d56"
#: The lost wrapper. Recorded so a test can assert nothing ever reproduces it.
LOST_WRAPPER_SHA = "639f37d129f30e1dddc13e343052e0fbe7ddd4632a97787857ccde9b2603a8a2"

REQUIRED_CHECKS = sorted({
    "clock_alignment", "stable_visibility", "hidden_row_validity", "physical_support",
    "zero_target_row_contamination", "path_state", "durability", "runtime_provenance",
    "pair_coverage", "capture_admission"})


def _head() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                          capture_output=True, check=True).stdout.strip()


def _fetch(uri: str) -> bytes | None:
    """One durable object, or None when the campaign namespace is unreachable."""
    result = subprocess.run(["aws", "s3", "cp", uri, "-", "--only-show-errors"],
                            capture_output=True, check=False)
    return result.stdout if result.returncode == 0 else None


class FakeTransport:
    """Serves a fixed map of durable bytes. Mutations are expressed by editing it."""

    def __init__(self, objects: dict[str, bytes]):
        self.objects = dict(objects)

    def download(self, uri: str) -> bytes:
        if uri not in self.objects:
            raise DurableStateError(f"durable object could not be read back: {uri}")
        return self.objects[uri]


def _reseal(document: dict) -> bytes:
    """Re-close a mutated durable record over its own payload digest.

    Without this every mutation below would be caught by the digest check alone,
    and the test would prove only that SHA-256 works rather than that the binding
    it guards is actually enforced.
    """
    document = {key: value for key, value in document.items() if key != "payload_sha256"}
    document["payload_sha256"] = canonical_payload_sha256(document, omit="payload_sha256")
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode()


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_bytes())


@pytest.fixture(scope="module")
def durable(manifest):
    """The real durable state and receipt bytes for one unit of each capture freeze."""
    objects: dict[str, bytes] = {}
    for unit_id in ("a2y_t01_wall", "a2y_t02_wall"):
        base = durable_unit_state_uri(manifest, unit_id)
        for name in (UNIT_STATE_OBJECT, CAPTURE_RECEIPT_OBJECT):
            raw = _fetch(f"{base}/{name}")
            if raw is None:
                pytest.skip("the campaign durable namespace is unreachable from this host")
            objects[f"{base}/{name}"] = raw
    return objects


@pytest.fixture(scope="module")
def admission_context(manifest):
    _document, authority_sha = load_capture_provenance_authority(
        PACKAGE, version_tag="v0.4", authority_path=AUTHORITY_PATH, repository=ROOT)
    return build_capture_admission_context(
        authority=json.loads(AUTHORITY_PATH.read_bytes()), manifest=manifest,
        manifest_sha256=sha256_file(MANIFEST_PATH),
        authority_sha256=sha256_file(AUTHORITY_PATH),
        scientific_run_id=manifest["run_namespace"],
        processing_source_commit_sha=_head(),
        capture_provenance_authority_sha256=authority_sha, repository=ROOT)


def _unit(manifest: dict, unit_id: str) -> dict:
    return next(u for u in manifest["capture_units"] if u["unit_id"] == unit_id)


def _restore(manifest, unit, objects, tmp_path, *, commit=None):
    """The repaired restore: derive the capture freeze, then restore against it."""
    transport = FakeTransport(objects)
    derived = commit or durable_capture_source_commit(
        manifest, unit, manifest_sha256=sha256_file(MANIFEST_PATH),
        authority_sha256=sha256_file(AUTHORITY_PATH),
        run_namespace=manifest["run_namespace"], transport=transport)
    return derived, restore_durable_unit_state(
        manifest, unit, receipt_path=tmp_path / f"{unit['unit_id']}.json",
        manifest_sha256=sha256_file(MANIFEST_PATH),
        authority_sha256=sha256_file(AUTHORITY_PATH), source_commit_sha=derived,
        run_namespace=manifest["run_namespace"], transport=transport)


# ======================================================================
# R1 -- mixed-freeze capture restoration
# ======================================================================

class TestMixedFreezeCaptureRestore:
    """The cohort spans two capture freezes, and both must restore under a third."""

    def test_t1_restores_under_its_own_historical_freeze(self, manifest, durable, tmp_path):
        """The case the predecessor could not express at all.

        T1 was captured under 49f0cca. The processing source is a successor. The
        restore must succeed and must name the historical commit, not the successor.
        """
        commit, receipt = _restore(manifest, _unit(manifest, "a2y_t01_wall"),
                                   durable, tmp_path)
        assert commit == T1_CAPTURE_COMMIT
        assert receipt["source_commit_sha"] == T1_CAPTURE_COMMIT
        assert commit != _head()

    def test_the_other_freeze_restores_under_the_same_successor(self, manifest, durable,
                                                                tmp_path):
        """Two different historical freezes, one processing source, both restorable."""
        commit, receipt = _restore(manifest, _unit(manifest, "a2y_t02_wall"),
                                   durable, tmp_path)
        assert commit == OTHER_CAPTURE_COMMIT
        assert receipt["source_commit_sha"] == OTHER_CAPTURE_COMMIT

    def test_the_two_freezes_really_are_different(self, manifest, durable, tmp_path):
        """Guards the premise. If these ever coincided the suite would pass vacuously."""
        first, _ = _restore(manifest, _unit(manifest, "a2y_t01_wall"), durable, tmp_path)
        second, _ = _restore(manifest, _unit(manifest, "a2y_t02_wall"), durable, tmp_path)
        assert first != second

    def test_the_predecessor_rule_fails_both_legitimate_cases(self, manifest, durable,
                                                              tmp_path):
        """The defect itself, stated as behaviour.

        The predecessor supplied ``campaign_source_commit(--provenance)``, which
        ``require_preoutcome_provenance`` has already pinned to live HEAD. Both
        legitimate units are refused, which is why the campaign was unrecoverable.
        """
        for unit_id in ("a2y_t01_wall", "a2y_t02_wall"):
            with pytest.raises(DurableStateError, match="source_commit_sha"):
                _restore(manifest, _unit(manifest, unit_id), durable, tmp_path,
                         commit=_head())

    def test_a_forged_capture_commit_is_refused(self, manifest, durable, tmp_path):
        """The repair reads evidence; it does not accept an assertion.

        A caller cannot reach the restore with a commit of its choosing, because the
        commit is derived. Supplying one anyway -- as the predecessor's call shape
        allowed -- is refused by the durable state record itself.
        """
        with pytest.raises(DurableStateError, match="source_commit_sha"):
            _restore(manifest, _unit(manifest, "a2y_t01_wall"), durable, tmp_path,
                     commit="d" * 40)

    def test_cross_unit_commit_substitution_is_refused(self, manifest, durable, tmp_path):
        """T1's freeze is not licence to restore a unit captured under the other one."""
        with pytest.raises(DurableStateError, match="source_commit_sha"):
            _restore(manifest, _unit(manifest, "a2y_t02_wall"), durable, tmp_path,
                     commit=T1_CAPTURE_COMMIT)

    def test_a_state_record_naming_no_valid_commit_is_refused(self, manifest, durable):
        """Derivation is not a licence to return whatever the record contains."""
        unit = _unit(manifest, "a2y_t01_wall")
        key = f"{durable_unit_state_uri(manifest, unit['unit_id'])}/{UNIT_STATE_OBJECT}"
        for forged in ("HEAD", "", "z" * 40, T1_CAPTURE_COMMIT[:39], None):
            state = json.loads(durable[key])
            state["source_commit_sha"] = forged
            objects = {**durable, key: _reseal(state)}
            with pytest.raises(DurableStateError, match="no valid capture source commit"):
                durable_capture_source_commit(
                    manifest, unit, manifest_sha256=sha256_file(MANIFEST_PATH),
                    authority_sha256=sha256_file(AUTHORITY_PATH),
                    run_namespace=manifest["run_namespace"],
                    transport=FakeTransport(objects))

    @pytest.mark.parametrize("field,value", [
        ("unit_id", "a2y_t09_no_wall"),
        ("manifest_sha256", "0" * 64),
        ("authority_sha256", "0" * 64),
        ("scientific_run_id", "some-other-campaign"),
        ("status", "IN_PROGRESS"),
        ("artifact_id", "some-other-artifact"),
        ("durable_uri", "s3://elsewhere/a2y_t01_wall"),
    ])
    def test_derivation_refuses_a_record_that_is_not_this_campaigns(
            self, manifest, durable, field, value):
        """Every binding except the commit is still required.

        Deriving the commit from evidence is only sound if the evidence is
        established to be THIS unit's, in THIS campaign, against THESE authority
        and manifest bytes. Each mutation below is resealed over its own digest,
        so what fails is the binding rather than the checksum.
        """
        unit = _unit(manifest, "a2y_t01_wall")
        key = f"{durable_unit_state_uri(manifest, unit['unit_id'])}/{UNIT_STATE_OBJECT}"
        state = json.loads(durable[key])
        state[field] = value
        objects = {**durable, key: _reseal(state)}
        with pytest.raises(DurableStateError, match="binding mismatch"):
            durable_capture_source_commit(
                manifest, unit, manifest_sha256=sha256_file(MANIFEST_PATH),
                authority_sha256=sha256_file(AUTHORITY_PATH),
                run_namespace=manifest["run_namespace"],
                transport=FakeTransport(objects))

    def test_an_unsealed_state_record_is_refused(self, manifest, durable):
        """The digest check is still first: an edit that forgets to reseal dies here."""
        unit = _unit(manifest, "a2y_t01_wall")
        key = f"{durable_unit_state_uri(manifest, unit['unit_id'])}/{UNIT_STATE_OBJECT}"
        state = json.loads(durable[key])
        state["source_commit_sha"] = "d" * 40
        objects = {**durable, key: json.dumps(state).encode()}
        with pytest.raises(DurableStateError, match="digest does not reproduce"):
            durable_capture_source_commit(
                manifest, unit, manifest_sha256=sha256_file(MANIFEST_PATH),
                authority_sha256=sha256_file(AUTHORITY_PATH),
                run_namespace=manifest["run_namespace"],
                transport=FakeTransport(objects))

    def test_receipt_and_state_record_disagreement_is_refused(self, manifest, durable,
                                                              tmp_path):
        """Two independently written documents; a restore may not straddle them.

        The state record is resealed to name the other freeze. The receipt still
        names T1's. The restore must refuse rather than pick one.
        """
        unit = _unit(manifest, "a2y_t01_wall")
        key = f"{durable_unit_state_uri(manifest, unit['unit_id'])}/{UNIT_STATE_OBJECT}"
        state = json.loads(durable[key])
        state["source_commit_sha"] = OTHER_CAPTURE_COMMIT
        objects = {**durable, key: _reseal(state)}
        with pytest.raises(DurableStateError, match="disagrees with its own durable state"):
            _restore(manifest, unit, objects, tmp_path)

    def test_a_substituted_receipt_is_refused(self, manifest, durable, tmp_path):
        """A receipt whose bytes are not the ones the state record binds."""
        unit = _unit(manifest, "a2y_t01_wall")
        base = durable_unit_state_uri(manifest, unit["unit_id"])
        objects = {**durable,
                   f"{base}/{CAPTURE_RECEIPT_OBJECT}":
                       durable[f"{durable_unit_state_uri(manifest, 'a2y_t02_wall')}"
                               f"/{CAPTURE_RECEIPT_OBJECT}"]}
        with pytest.raises(DurableStateError, match="different attempt's receipt"):
            _restore(manifest, unit, objects, tmp_path)

    def test_digest_corruption_of_the_receipt_is_refused(self, manifest, durable, tmp_path):
        """One flipped byte in the durable receipt stops the restore."""
        unit = _unit(manifest, "a2y_t01_wall")
        base = durable_unit_state_uri(manifest, unit["unit_id"])
        key = f"{base}/{CAPTURE_RECEIPT_OBJECT}"
        objects = {**durable, key: durable[key] + b" "}
        with pytest.raises(DurableStateError, match="different attempt's receipt"):
            _restore(manifest, unit, objects, tmp_path)

    @pytest.mark.parametrize("missing", [UNIT_STATE_OBJECT, CAPTURE_RECEIPT_OBJECT])
    def test_a_missing_durable_object_is_refused(self, manifest, durable, tmp_path, missing):
        unit = _unit(manifest, "a2y_t01_wall")
        base = durable_unit_state_uri(manifest, unit["unit_id"])
        objects = {k: v for k, v in durable.items() if k != f"{base}/{missing}"}
        with pytest.raises(DurableStateError):
            _restore(manifest, unit, objects, tmp_path)

    def test_restoration_alone_is_not_admission(self, manifest, durable, tmp_path,
                                                admission_context):
        """The second half of the repair, and the half that carries the apparatus rule.

        Knowing WHICH freeze took a capture does not say the apparatus at that
        freeze is one this campaign may process. Admission re-derives the
        capture-critical closure at the derived commit and requires the authorized
        value, and it is what stops the derivation from being a bare commit lookup.
        """
        for unit_id, expected in (("a2y_t01_wall", T1_CAPTURE_COMMIT),
                                  ("a2y_t02_wall", OTHER_CAPTURE_COMMIT)):
            unit = _unit(manifest, unit_id)
            commit, receipt = _restore(manifest, unit, durable, tmp_path)
            record = admission_context.admit(unit, receipt)
            assert record["capture_source_commit"] == expected == commit
            assert record["capture_critical_closure_sha256"] == CAPTURE_CRITICAL_CLOSURE
            # The provenance split, stated rather than inferred.
            assert record["capture_taken_under_processing_commit"] is False
            assert record["processing_source_commit"] == _head()

    def test_admission_refuses_an_unauthorized_capture_apparatus(self, manifest, durable,
                                                                 tmp_path):
        """A capture taken by a different instrument is refused however truthful its
        provenance. This is the check that makes the derived commit insufficient
        on its own, so it must fail for a closure the campaign did not authorize."""
        _document, authority_sha = load_capture_provenance_authority(
            PACKAGE, version_tag="v0.4", authority_path=AUTHORITY_PATH, repository=ROOT)
        context = build_capture_admission_context(
            authority=json.loads(AUTHORITY_PATH.read_bytes()), manifest=manifest,
            manifest_sha256=sha256_file(MANIFEST_PATH),
            authority_sha256=sha256_file(AUTHORITY_PATH),
            scientific_run_id=manifest["run_namespace"],
            processing_source_commit_sha=_head(),
            capture_provenance_authority_sha256=authority_sha, repository=ROOT,
            expected_capture_critical_closure_sha256="f" * 64)
        unit = _unit(manifest, "a2y_t01_wall")
        _commit, receipt = _restore(manifest, unit, durable, tmp_path)
        with pytest.raises(CaptureAdmissionError, match="NOT equivalent"):
            context.admit(unit, receipt)

    def test_the_historical_freezes_share_the_authorized_apparatus(self):
        """Why this cohort is one experiment despite spanning two commits.

        Not an incidental fact: it is the entire scientific justification for
        admitting a mixed-freeze cohort, so it is asserted rather than assumed.
        """
        from mineocclude.prospective.capture_closure import capture_critical_closure_at
        for commit in (T1_CAPTURE_COMMIT, OTHER_CAPTURE_COMMIT, _head()):
            closure, _ = capture_critical_closure_at(commit, repository=ROOT)
            assert closure == CAPTURE_CRITICAL_CLOSURE

    def test_refusal_is_operational_not_a_scientific_verdict(self):
        assert issubclass(DurableStateError, ValueError)
        assert issubclass(CaptureAdmissionError, RuntimeError)


# ======================================================================
# R2 -- admitting the surviving durable gate payload
# ======================================================================

@pytest.fixture(scope="module")
def gate_evidence(manifest):
    """The two surviving durable gate objects, as bytes."""
    base = durable_unit_uri(manifest, manifest["physical_gate_unit"]["unit_id"])
    payload = _fetch(f"{base}/payload.json")
    checksum = _fetch(f"{base}/sha256_manifest.json")
    if payload is None or checksum is None:
        pytest.skip("the durable physical-gate namespace is unreachable from this host")
    return payload, checksum


@pytest.fixture(scope="module")
def payload_authority():
    return pga.load_durable_payload_admission_authority(PACKAGE)[0]


def _admit(manifest, payload, checksum, authority_document, **overrides):
    kwargs = dict(
        payload_bytes=payload, checksum_manifest_bytes=checksum,
        authority=json.loads(AUTHORITY_PATH.read_bytes()),
        payload_authority=authority_document,
        authority_sha256=sha256_file(AUTHORITY_PATH),
        manifest_sha256=sha256_file(MANIFEST_PATH),
        processing_source_commit=_head(),
        expected_required_checks=REQUIRED_CHECKS,
        authorized_capture_critical_closure=CAPTURE_CRITICAL_CLOSURE,
        repository=ROOT)
    kwargs.update(overrides)
    return pga.admit_historical_durable_gate_payload(manifest, **kwargs)


def _repin(authority_document: dict, payload: bytes, checksum: bytes) -> dict:
    """Re-pin the authority's two digests to mutated bytes.

    Every mutation below would otherwise be caught by the digest pin alone. Re-pinning
    forces each test to prove the SEMANTIC check it targets, not the pin.
    """
    document = copy.deepcopy(authority_document)
    admitted = document["admitted_historical_durable_gate_payload"]
    admitted["durable_payload_sha256"] = hashlib.sha256(payload).hexdigest()
    admitted["durable_checksum_manifest_sha256"] = hashlib.sha256(checksum).hexdigest()
    return document


def _dumps(document: dict) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode()


def _forge(payload: bytes, checksum: bytes, authority_document: dict, mutate):
    """A maximally capable forger: mutate the payload, then make everything agree.

    ``mutate`` edits the parsed payload in place. The checksum manifest is then
    re-vouched for the mutated payload and both digest pins are re-derived, so the
    integrity layer is fully satisfied. What is left to refuse the document is the
    semantic check under test -- which is the only thing these cases are about.
    Without this, every mutation would die at the cross-vouching step and the suite
    would prove nothing beyond SHA-256 working.
    """
    document = json.loads(payload)
    mutate(document)
    forged_payload = _dumps(document)
    vouch = json.loads(checksum)
    vouch["files"]["payload.json"] = hashlib.sha256(forged_payload).hexdigest()
    forged_checksum = _dumps(vouch)
    return (forged_payload, forged_checksum,
            _repin(authority_document, forged_payload, forged_checksum))


class TestHistoricalDurableGatePayloadAdmission:
    """The wrapper is gone. The verdict is not."""

    def test_the_original_wrapper_is_not_recoverable(self, manifest):
        """States the premise as a fact about the world, not a convenience.

        If a wrapper ever reappears at the canonical path, this recovery route is
        the wrong one and the ordinary wrapper rule should be used instead.
        """
        assert not Path(manifest["physical_gate_unit"]["receipt_path"]).is_file()

    def test_the_surviving_payload_is_admitted(self, manifest, gate_evidence,
                                               payload_authority):
        payload, checksum = gate_evidence
        record = _admit(manifest, payload, checksum, payload_authority)
        assert record["admission_regime"] == "HISTORICAL_DURABLE_GATE_PAYLOAD_ADMITTED"
        assert record["gate_source_commit"] == GATE_SOURCE_COMMIT
        assert record["gate_result"] == "PASS"
        assert record["capture_units"] == 50
        assert record["paired_trajectories"] == 25
        assert record["cohort_capture_critical_closure_sha256"] == CAPTURE_CRITICAL_CLOSURE
        assert record["gate_critical_closure_sha256"] == GATE_CRITICAL_CLOSURE

    def test_the_record_never_claims_the_wrapper_survived(self, manifest, gate_evidence,
                                                          payload_authority):
        """The anti-laundering statement, as data rather than as prose.

        A downstream artifact copies this record verbatim, so an activation produced
        this way can never be read as one produced under a surviving wrapper.
        """
        record = _admit(manifest, *gate_evidence, payload_authority)
        assert record["physical_gate_wrapper_receipt_recovered"] is False
        assert record["physical_gate_wrapper_receipt_regenerated"] is False
        assert record["physical_gate_replay_performed"] is False
        assert record["lost_wrapper_receipt_sha256"] == LOST_WRAPPER_SHA
        # The historical and current sources are stated separately, never normalized.
        assert record["gate_source_commit"] != record["processing_source_commit"]

    def test_the_regime_cannot_be_confused_with_a_wrapper_admission(self):
        """Three regimes, three names. A consumer can always tell them apart."""
        assert pga.DURABLE_PAYLOAD_REGIME not in ("SAME_FREEZE", "HISTORICAL_ADMITTED")

    def test_nothing_reproduces_the_lost_wrapper_digest(self, manifest, gate_evidence,
                                                        payload_authority):
        """The one claim that must never be makeable: that this IS the receipt."""
        payload, checksum = gate_evidence
        record = _admit(manifest, payload, checksum, payload_authority)
        for value in (hashlib.sha256(payload).hexdigest(),
                      hashlib.sha256(checksum).hexdigest(),
                      record["durable_payload_sha256"],
                      record["durable_checksum_manifest_sha256"]):
            assert value != LOST_WRAPPER_SHA

    def test_it_writes_no_wrapper(self, manifest, gate_evidence, payload_authority):
        """Admission is a read. A local wrapper must not exist after it."""
        _admit(manifest, *gate_evidence, payload_authority)
        assert not Path(manifest["physical_gate_unit"]["receipt_path"]).is_file()

    # ---- digest and cross-vouching --------------------------------------

    def test_a_wrong_payload_digest_is_refused(self, manifest, gate_evidence,
                                               payload_authority):
        payload, checksum = gate_evidence
        with pytest.raises(pga.PhysicalGateAdmissionError, match="payload digest"):
            _admit(manifest, payload + b" ", checksum, payload_authority)

    def test_a_wrong_checksum_manifest_digest_is_refused(self, manifest, gate_evidence,
                                                         payload_authority):
        payload, checksum = gate_evidence
        with pytest.raises(pga.PhysicalGateAdmissionError, match="checksum manifest digest"):
            _admit(manifest, payload, checksum + b" ", payload_authority)

    def test_payload_and_manifest_disagreement_is_refused(self, manifest, gate_evidence,
                                                          payload_authority):
        """The two objects vouch for each other. Re-pinned, so the pin is not what fails."""
        payload, checksum = gate_evidence
        document = json.loads(checksum)
        document["files"]["payload.json"] = "0" * 64
        mutated = _dumps(document)
        with pytest.raises(pga.PhysicalGateAdmissionError, match="disagree"):
            _admit(manifest, payload, mutated,
                   _repin(payload_authority, payload, mutated))

    # ---- campaign bindings ------------------------------------------------

    @pytest.mark.parametrize("field,value,expected", [
        ("authority_sha256", "0" * 64, "authority binding"),
        ("manifest_sha256", "0" * 64, "manifest binding"),
        ("scientific_run_id", "another-campaign", "run-namespace"),
        ("unit_id", "a2y_t01_wall", "unit identity"),
        ("source_commit_sha", "d" * 40, "does not name as its admitted gate source"),
    ])
    def test_a_mis_bound_checksum_manifest_is_refused(self, manifest, gate_evidence,
                                                      payload_authority, field, value,
                                                      expected):
        payload, checksum = gate_evidence
        document = json.loads(checksum)
        document[field] = value
        mutated = _dumps(document)
        with pytest.raises(pga.PhysicalGateAdmissionError, match=expected):
            _admit(manifest, payload, mutated,
                   _repin(payload_authority, payload, mutated))

    # ---- the gate result and its semantics --------------------------------

    @pytest.mark.parametrize("label,mutate,expected", [
        ("gate FAIL", lambda g: g.update(status="FAIL"), "not PASS"),
        ("gate BLOCKED", lambda g: g.update(status="BLOCKED"), "not PASS"),
        ("gate absent", lambda g: g.update(status=None), "not PASS"),
        ("49 units", lambda g: g.update(capture_units=49), "cohort size"),
        ("51 units", lambda g: g.update(capture_units=51), "cohort size"),
        ("wrong pairs", lambda g: g.update(paired_trajectories=24), "pair count"),
        ("missing check", lambda g: g.update(
            required_checks=[c for c in g["required_checks"] if c != "path_state"]),
         "check vocabulary"),
        ("extra check", lambda g: g.update(
            required_checks=sorted(g["required_checks"] + ["some_new_check"])),
         "check vocabulary"),
    ])
    def test_a_gate_that_did_not_pass_this_design_is_refused(
            self, manifest, gate_evidence, payload_authority, label, mutate, expected):
        payload, checksum = gate_evidence
        forged = _forge(payload, checksum, payload_authority,
                        lambda d: mutate(d["physical_gates"]))
        with pytest.raises(pga.PhysicalGateAdmissionError, match=expected):
            _admit(manifest, *forged)

    def test_an_incomplete_payload_is_refused(self, manifest, gate_evidence,
                                              payload_authority):
        payload, checksum = gate_evidence
        forged = _forge(payload, checksum, payload_authority,
                        lambda d: d.update(physical_gates=None))
        with pytest.raises(pga.PhysicalGateAdmissionError, match="no gate result"):
            _admit(manifest, *forged)

    # ---- cohort identity ---------------------------------------------------

    @pytest.mark.parametrize("label,mutate,expected", [
        ("dropped unit", lambda s: s["capture_source_commit_by_unit"].pop("a2y_t25_wall"),
         "cohort identity"),
        ("substituted unit", lambda s: s["capture_source_commit_by_unit"].update(
            {"a2y_t99_wall": "0" * 40}), "cohort identity"),
        ("wrong apparatus", lambda s: s.update(
            cohort_capture_critical_closure_sha256="f" * 64), "apparatus closure"),
        ("two apparatuses", lambda s: s.update(all_admitted_capture_closures_equal=False),
         "one capture apparatus"),
        ("laundered commit", lambda s: s.update(processing_source_commit="d" * 40),
         "do not describe the same gate"),
    ])
    def test_a_gate_over_another_cohort_is_refused(self, manifest, gate_evidence,
                                                   payload_authority, label, mutate,
                                                   expected):
        payload, checksum = gate_evidence
        forged = _forge(payload, checksum, payload_authority,
                        lambda d: mutate(d["physical_gates"]["capture_provenance_split"]))
        with pytest.raises(pga.PhysicalGateAdmissionError, match=expected):
            _admit(manifest, *forged)

    def test_the_cohort_is_the_manifest_cohort_exactly(self, manifest, gate_evidence):
        """Not merely the right size: the right fifty identities."""
        payload, _checksum = gate_evidence
        by_unit = json.loads(payload)["physical_gates"][
            "capture_provenance_split"]["capture_source_commit_by_unit"]
        assert sorted(by_unit) == sorted(u["unit_id"] for u in manifest["capture_units"])
        assert by_unit["a2y_t01_wall"] == T1_CAPTURE_COMMIT
        assert {v for k, v in by_unit.items() if k != "a2y_t01_wall"} == {OTHER_CAPTURE_COMMIT}

    # ---- the load-bearing condition ---------------------------------------

    def test_a_successor_that_changed_the_verdict_is_refused(self, manifest, gate_evidence,
                                                             payload_authority):
        """The condition that makes this an admission rule and not a rubber stamp."""
        def moved(source, *, repository=None, entrypoints=None):
            return ("dead" * 16 if isinstance(source, str) else "beef" * 16), {}

        with pytest.raises(pga.PhysicalGateAdmissionError,
                           match="gate-critical closure changed"):
            _admit(manifest, *gate_evidence, payload_authority, closure_at=moved)

    def test_the_gate_critical_closure_is_equal_at_both_sources(self):
        """Re-derived, never asserted: the reason admission is sound at all."""
        historical, _ = pga.gate_critical_closure_at(GATE_SOURCE_COMMIT, repository=ROOT)
        current, _ = pga.gate_critical_closure_at(_head(), repository=ROOT)
        assert historical == current == GATE_CRITICAL_CLOSURE

    def test_the_payload_route_is_refused_at_the_gates_own_commit(self, manifest,
                                                                  gate_evidence,
                                                                  payload_authority):
        """A recovery route must not become a second, looser way to the same answer.

        At the gate's own freeze the wrapper question does not arise, so the payload
        path refuses rather than offering an alternative to the wrapper rule.
        """
        with pytest.raises(pga.PhysicalGateAdmissionError, match="recovery measure"):
            _admit(manifest, *gate_evidence, payload_authority,
                   processing_source_commit=GATE_SOURCE_COMMIT)

    # ---- governance --------------------------------------------------------

    @pytest.mark.parametrize("mutate,expected", [
        (lambda d: d.update(status="DRAFT"), "not FROZEN"),
        (lambda d: d.update(authorized_option="OPTION_1"), "different option"),
        (lambda d: d["lost_wrapper"].update(recoverable=True), "unrecoverable"),
        (lambda d: d["admitted_historical_durable_gate_payload"].update(
            gate_source_commit="short"), "names no gate source commit"),
    ])
    def test_an_authority_that_does_not_authorize_this_is_refused(
            self, manifest, gate_evidence, payload_authority, mutate, expected):
        document = copy.deepcopy(payload_authority)
        mutate(document)
        with pytest.raises(pga.PhysicalGateAdmissionError, match=expected):
            _admit(manifest, *gate_evidence, document)

    def test_a_successor_without_the_authority_admits_nothing(self, tmp_path):
        """The predecessor's position, and any successor that drops the document.

        Not shipping the governance file is not a soft default: it removes the
        route entirely, so a lost wrapper is simply a blocker.
        """
        with pytest.raises(pga.PhysicalGateAdmissionError, match="is absent"):
            pga.load_durable_payload_admission_authority(tmp_path)

    def test_the_predecessor_implementation_has_no_such_route(self):
        """R2 stated as a capability the predecessor lacked.

        The predecessor here is the processing freeze that consumed the wrapper --
        not the gate freeze, which predates this module entirely.
        """
        previous = subprocess.run(
            ["git", "show", f"{PREDECESSOR_PROCESSING_COMMIT}:src/mineocclude/"
             f"prospective/physical_gate_admission.py"], cwd=ROOT, text=True,
            capture_output=True, check=True).stdout
        assert "admit_historical_durable_gate_payload" not in previous
        assert "DURABLE_PAYLOAD_REGIME" not in previous

    def test_the_predecessor_extraction_path_demanded_the_local_wrapper(self):
        """The defect itself, in the predecessor's own bytes.

        ``extraction`` opened the wrapper by path as its first statement, so the
        host rebuild turned a lost serialization into an unrecoverable campaign.
        """
        previous = subprocess.run(
            ["git", "show", f"{PREDECESSOR_PROCESSING_COMMIT}:scripts/"
             f"regime_a_prime_qualification_v0_2/stage2_backend.py"], cwd=ROOT,
            text=True, capture_output=True, check=True).stdout
        assert 'gate = load_json(Path(manifest["physical_gate_unit"]["receipt_path"]))' \
            in previous
        assert "resolve_physical_gate_admission" not in previous

    def test_refusal_is_operational_not_a_scientific_verdict(self):
        assert issubclass(pga.PhysicalGateAdmissionError, RuntimeError)
        assert not issubclass(pga.PhysicalGateAdmissionError, AssertionError)
