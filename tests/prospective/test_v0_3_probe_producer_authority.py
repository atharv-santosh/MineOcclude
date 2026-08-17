"""The v0.3 authority's probe producers name the code that actually runs.

Freeze ``fa9d134`` completed the v0.3 execution surface and then failed at the
first live command:

    EvidenceError: runtime_provenance_receipt was not produced by an independent
    probe: 'scripts.regime_a_prime_qualification_v0_2.stage_unit_driver.probe_runtime'

``build_authority.py`` derives the v0.3 authority from the v0.2 authority by a
blanket ``v0_2 -> v0_3`` string sweep. That sweep is correct for versioned
artifact identities -- artifact IDs, namespaces, manifest paths -- and wrong for
Python import paths. v0.3 changes the visibility truth predicate, not the
apparatus, so the runtime probe still lives in the v0.2 package and
``build_manifests.py`` still binds all 8 unit commands to the v0.2
``stage_unit_driver``. The sweep renamed the one real producer to a module that
has never existed on any branch, and renamed both forbidden entries to modules
that have never existed either -- so the allow-list blocked the real probe while
the deny-list forbade nothing at all.

These tests are the closure evidence for that repair. They assert the producer
contract from both ends: that the authority names the implementation the
manifest actually executes, and that the substitutions which would satisfy the
string while defeating the control -- a wrong producer, a forbidden producer, a
thin v0.3 re-export wrapper -- are still refused.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from mineocclude.prospective.development_workflow import (  # noqa: E402
    EvidenceError, RUNTIME_CRITICAL_SOURCE_PATHS, canonical_payload_sha256,
    load_json, probe_evidence_digest, sha256_file, verify_probe_execution,
)
from mineocclude.prospective.package_binding import (  # noqa: E402
    resolve_package_binding,
)

#: The shared implementation that both v0.2 and v0.3 execute. v0.3 deliberately
#: leaves the apparatus unmodified, so this path is intentionally not versioned
#: alongside the scientific package.
SHARED_DRIVER_RELATIVE = "scripts/regime_a_prime_qualification_v0_2/stage_unit_driver.py"
SHARED_PROBE_PRODUCER = (
    "scripts.regime_a_prime_qualification_v0_2.stage_unit_driver.probe_runtime")

#: The producer path the sweep invented. It has never existed in any commit.
SWEPT_PROBE_PRODUCER = (
    "scripts.regime_a_prime_qualification_v0_3.stage_unit_driver.probe_runtime")

EXPECTED_FORBIDDEN_PRODUCERS = [
    "scripts.regime_a_prime_qualification_v0_2.build_stage1_evidence.main",
    "scripts.regime_a_prime_qualification_v0_2.build_stage1_evidence.build_evidence",
    "mineocclude.prospective.development_workflow.Stage1Evaluator",
]

PREDECESSOR_UNIT_PREFIX = "a1q_"
PREDECESSOR_EPISODES = frozenset(range(81001, 81009))


@pytest.fixture(scope="module")
def binding():
    return resolve_package_binding("v0.3", ROOT)


@pytest.fixture(scope="module")
def authority(binding):
    return load_json(binding.authority_path)


@pytest.fixture(scope="module")
def probe_policy(authority):
    return authority["runtime_identity_policy"]["probe_evidence_policy"]


@pytest.fixture(scope="module")
def stage1_manifest(binding):
    return load_json(binding.stage1_manifest_path)


@pytest.fixture(scope="module")
def driver():
    return importlib.import_module(
        "scripts.regime_a_prime_qualification_v0_2.stage_unit_driver")


def _producer_source(producer: str) -> Path | None:
    """The file defining a dotted producer path, or None if there is no module."""
    parts = producer.split(".")
    for root in (ROOT, ROOT / "src"):
        candidate = root.joinpath(*parts[:-1]).with_suffix(".py")
        if candidate.is_file():
            return candidate
    return None


def _sealed(payload: dict) -> dict:
    """Close a receipt under its own payload digest, as the driver does."""
    receipt = {"status": "PASS", **payload}
    receipt["payload_sha256"] = canonical_payload_sha256(receipt, omit="payload_sha256")
    return receipt


def _receipt_with(producer: str, source_relative: str, source_sha: str) -> dict:
    """A digest-consistent receipt carrying a chosen probe identity.

    The invocation record is deliberately empty: these tests exercise gate A
    (producer identity and probe source bytes), which runs before any invocation
    is examined. A receipt that clears gate A therefore fails later, on
    invocation coverage, and the distinct failure message is what lets each test
    below assert *which* gate rejected it.
    """
    execution = {"producer": producer, "probe_source_path": source_relative,
                 "probe_source_sha256": source_sha, "invocations": []}
    return _sealed({"probe_execution": execution,
                    "probe_evidence_sha256": probe_evidence_digest(execution)})


def _real_identity_receipt(driver) -> dict:
    """A receipt carrying the genuine producer identity and real source bytes."""
    return _receipt_with(driver.PROBE_PRODUCER, driver.PROBE_SOURCE_RELATIVE,
                         sha256_file(ROOT / driver.PROBE_SOURCE_RELATIVE))


# ------------------------------- 1. the required producer is the real function


def test_required_producer_is_the_shared_implementation(probe_policy):
    assert probe_policy["independent_probe_producers"] == [SHARED_PROBE_PRODUCER]


def test_required_producer_resolves_to_a_real_module(probe_policy):
    """The producer names a file on disk, not a string that merely looks right."""
    for producer in probe_policy["independent_probe_producers"]:
        source = _producer_source(producer)
        assert source is not None, f"required producer has no implementation: {producer}"
        assert source == ROOT / SHARED_DRIVER_RELATIVE


def test_required_producer_is_the_function_the_driver_actually_executes(
        probe_policy, driver):
    """The authority string equals the constant the running probe stamps in.

    Comparing against the module constant, rather than a literal, is what makes
    the allow-list track the implementation instead of a transcription of it.
    """
    assert driver.PROBE_PRODUCER in probe_policy["independent_probe_producers"]
    assert callable(driver.probe_runtime)
    assert driver.PROBE_PRODUCER.endswith(".probe_runtime")
    assert driver.PROBE_PRODUCER.rsplit(".", 1)[0] == (
        driver.__name__ if driver.__name__.startswith("scripts.")
        else "scripts.regime_a_prime_qualification_v0_2.stage_unit_driver")


# ---------------------------- 2-3. the source digest binds the implementation


def test_probe_source_path_is_the_shared_driver(driver):
    assert driver.PROBE_SOURCE_RELATIVE == SHARED_DRIVER_RELATIVE
    assert (ROOT / driver.PROBE_SOURCE_RELATIVE).is_file()


def test_probe_source_is_runtime_critical(driver):
    """Gate A requires the probe source to be a runtime-critical source.

    This is the structural reason a v0.3 wrapper cannot be introduced quietly:
    the frozen closure enumerates the implementation, not the caller.
    """
    assert driver.PROBE_SOURCE_RELATIVE in RUNTIME_CRITICAL_SOURCE_PATHS


def test_probe_source_sha_binds_real_implementation_bytes(driver):
    """The declared digest is the digest of the implementation on disk."""
    declared = sha256_file(ROOT / driver.PROBE_SOURCE_RELATIVE)
    assert declared == sha256_file(ROOT / SHARED_DRIVER_RELATIVE)
    assert len(declared) == 64


def test_real_producer_identity_clears_the_producer_and_source_gate(driver, authority):
    """A genuine producer and genuine source bytes are accepted by gate A.

    The receipt still fails -- it carries no invocations -- but it fails *past*
    the producer and source checks, which is exactly the acceptance being
    asserted. The live probe supplies the invocations that gate A never sees.
    """
    with pytest.raises(EvidenceError) as excinfo:
        verify_probe_execution(_real_identity_receipt(driver),
                               "runtime_provenance_receipt", authority=authority)
    message = str(excinfo.value)
    assert "not produced by an independent probe" not in message
    assert "probe source" not in message
    assert "invocation" in message


# ---------------------------- 4. the invented v0.3 producer is not required


def test_swept_v0_3_producer_is_not_required(probe_policy):
    assert SWEPT_PROBE_PRODUCER not in probe_policy["independent_probe_producers"]


def test_swept_v0_3_driver_does_not_exist():
    """The module the sweep named has never existed, in the tree or in history."""
    assert not (ROOT / "scripts/regime_a_prime_qualification_v0_3/stage_unit_driver.py").exists()
    assert not (ROOT / "scripts/regime_a_prime_qualification_v0_3/build_stage1_evidence.py").exists()
    log = subprocess.run(
        ["git", "log", "--all", "--oneline", "--",
         "scripts/regime_a_prime_qualification_v0_3/stage_unit_driver.py"],
        cwd=ROOT, capture_output=True, text=True, check=True)
    assert log.stdout.strip() == ""


def test_no_authority_producer_names_a_nonexistent_module(probe_policy):
    """Neither list may contain an entry with no implementation behind it.

    A missing allow-list entry blocks the real probe; a missing deny-list entry
    forbids nothing. Both are failures of the same control.
    """
    for field in ("independent_probe_producers", "forbidden_probe_producers"):
        for producer in probe_policy[field]:
            assert _producer_source(producer) is not None, (
                f"{field} entry has no implementation: {producer}")


# ------------------------------- 5-6. the forbidden list forbids real things


def test_forbidden_producers_are_the_intended_real_paths(probe_policy):
    assert probe_policy["forbidden_probe_producers"] == EXPECTED_FORBIDDEN_PRODUCERS


def test_forbidden_producers_name_real_self_assertion_risks(probe_policy):
    """Every forbidden entry names a module that really exists.

    Module existence is the property that matters and the property the sweep
    destroyed. The attribute need not currently be defined:
    ``build_stage1_evidence.build_evidence`` is a prophylactic entry, inherited
    verbatim from the frozen v0.2 authority, that forbids a plausible future
    entrypoint in the evidence builder before anyone can add one. Forbidding an
    undefined name inside a real builder is meaningful; forbidding a name inside
    a module that has never existed -- which is what the v0.3 sweep produced --
    is not.
    """
    defined = {"scripts.regime_a_prime_qualification_v0_2.build_stage1_evidence.main",
               "mineocclude.prospective.development_workflow.Stage1Evaluator"}
    for producer in probe_policy["forbidden_probe_producers"]:
        source = _producer_source(producer)
        assert source is not None, f"forbidden producer has no module: {producer}"
        module, attribute = producer.rsplit(".", 1)
        if producer in defined:
            text = source.read_text()
            assert f"def {attribute}" in text or f"class {attribute}" in text, (
                f"{producer} should be a defined symbol")


def test_forbidden_list_covers_the_evidence_builder_and_the_evaluator(probe_policy):
    """The two self-assertion risks the policy exists to exclude are both named."""
    forbidden = probe_policy["forbidden_probe_producers"]
    assert any("build_stage1_evidence" in entry for entry in forbidden)
    assert any(entry.endswith("development_workflow.Stage1Evaluator") for entry in forbidden)
    assert all(".v0_3." not in entry for entry in forbidden)


@pytest.mark.parametrize("producer", EXPECTED_FORBIDDEN_PRODUCERS)
def test_forbidden_producer_is_rejected(producer, driver, authority):
    """A receipt authored by the evidence builder or evaluator is refused."""
    receipt = _receipt_with(producer, driver.PROBE_SOURCE_RELATIVE,
                            sha256_file(ROOT / driver.PROBE_SOURCE_RELATIVE))
    with pytest.raises(EvidenceError, match="not produced by an independent probe"):
        verify_probe_execution(receipt, "runtime_provenance_receipt", authority=authority)


# ------------------------------------- 7-8. substitutions are still refused


def test_wrong_producer_string_is_rejected(driver, authority):
    """Including the exact string the sweep invented."""
    for producer in (SWEPT_PROBE_PRODUCER, "", "probe_runtime",
                     "scripts.regime_a_prime_qualification_v0_2.generate_receipts.main"):
        receipt = _receipt_with(producer, driver.PROBE_SOURCE_RELATIVE,
                                sha256_file(ROOT / driver.PROBE_SOURCE_RELATIVE))
        with pytest.raises(EvidenceError, match="not produced by an independent probe"):
            verify_probe_execution(receipt, "runtime_provenance_receipt",
                                   authority=authority)


def test_wrapper_source_substitution_is_rejected(tmp_path, driver, authority):
    """A v0.3 re-export cannot stand in for the implementation.

    This is the workaround the repair deliberately refused: create
    ``scripts/regime_a_prime_qualification_v0_3/stage_unit_driver.py`` that
    re-exports ``probe_runtime`` so the swept string becomes literally true. It
    fails twice over -- the wrapper path is not runtime-critical, and its bytes
    are not the probing code -- so the provenance control still binds the
    implementation rather than a naming shim.
    """
    wrapper = "scripts/regime_a_prime_qualification_v0_3/stage_unit_driver.py"
    assert wrapper not in RUNTIME_CRITICAL_SOURCE_PATHS
    receipt = _receipt_with(driver.PROBE_PRODUCER, wrapper,
                            sha256_file(ROOT / driver.PROBE_SOURCE_RELATIVE))
    with pytest.raises(EvidenceError, match="not a runtime-critical source"):
        verify_probe_execution(receipt, "runtime_provenance_receipt", authority=authority)


def test_correct_producer_with_foreign_source_bytes_is_rejected(driver, authority):
    """Right name, wrong bytes: the source digest is rehashed from disk."""
    other = "scripts/regime_a_prime_qualification_v0_2/generate_receipts.py"
    assert other in RUNTIME_CRITICAL_SOURCE_PATHS
    receipt = _receipt_with(driver.PROBE_PRODUCER, other,
                            sha256_file(ROOT / driver.PROBE_SOURCE_RELATIVE))
    with pytest.raises(EvidenceError, match="probe source bytes differ"):
        verify_probe_execution(receipt, "runtime_provenance_receipt", authority=authority)


# ------------------------- 9-10. manifest and authority agree on the driver


def test_all_eight_unit_commands_use_the_approved_shared_driver(stage1_manifest):
    units = stage1_manifest["units"]
    assert len(units) == 8
    drivers = {Path(unit["command"][1]) for unit in units}
    assert drivers == {ROOT / SHARED_DRIVER_RELATIVE}


def test_manifest_driver_and_authority_producer_are_coherent(
        stage1_manifest, probe_policy):
    """The module the manifest executes is the module the authority requires.

    This is the exact invariant ``fa9d134`` violated: the two frozen artifacts
    disagreed, so every unit would have failed at ``probe_runtime``.
    """
    producer = probe_policy["independent_probe_producers"][0]
    producer_module = ROOT.joinpath(*producer.split(".")[:-1]).with_suffix(".py")
    for unit in stage1_manifest["units"]:
        assert Path(unit["command"][1]) == producer_module


def test_manifest_authority_binding_matches_the_authority_on_disk(
        binding, stage1_manifest):
    assert stage1_manifest["authority_binding"]["sha256"] == sha256_file(
        binding.authority_path)


# ------------------- 11-13. package, inventory and Stage-2 guards still hold


def test_v0_2_scientific_package_substitution_remains_refused(binding, authority):
    assert binding.package.name == "prospective_development_authority_v0_3"
    assert authority["artifact_id"].endswith("-v0.3")
    assert binding.run_namespace == "mineocclude-regime-a-prime-development-v0-3-stage1"


def test_no_a1q_unit_can_enter_v0_3_stage1(stage1_manifest):
    """The predecessor inventory terminated in a scientific FAIL and is closed."""
    for unit in stage1_manifest["units"]:
        assert not unit["unit_id"].startswith(PREDECESSOR_UNIT_PREFIX)
        assert unit["episode_id"] not in PREDECESSOR_EPISODES
        assert 83001 <= unit["episode_id"] <= 83008
        assert unit["seed"] == unit["noise_seed"]


def test_stage2_remains_unauthorized(authority, binding):
    assert authority["change_log"]["STAGE2_AUTHORIZED"] is False
    assert authority["change_log"]["STAGE2_LOCKED"] is True
    assert authority["predecessor_authority"]["stage2_authorized"] is False
    locked = load_json(binding.package / "stage2_locked_manifest.json")
    assert locked["authority_binding"]["sha256"] == sha256_file(binding.authority_path)


# ---------------------------------- 14. the repaired build is deterministic


def test_authority_and_manifests_rebuild_byte_identically(tmp_path, binding):
    """Regeneration reproduces the committed bytes exactly."""
    build_authority = importlib.import_module(
        "scripts.regime_a_prime_qualification_v0_3.build_authority")
    rebuilt = build_authority.build_authority()
    build_authority.require_producers_exist(rebuilt)
    rendered = json.dumps(rebuilt, indent=2, sort_keys=True, allow_nan=False) + "\n"
    assert rendered == binding.authority_path.read_text()

    for name in ("stage1_manifest.json", "stage2_locked_manifest.json"):
        before = (binding.package / name).read_bytes()
        subprocess.run([sys.executable,
                        "scripts/regime_a_prime_qualification_v0_3/build_manifests.py"],
                       cwd=ROOT, capture_output=True, text=True, check=True)
        assert (binding.package / name).read_bytes() == before


def test_generator_refuses_a_producer_with_no_implementation():
    """The guard that makes this defect class unshippable actually fires."""
    build_authority = importlib.import_module(
        "scripts.regime_a_prime_qualification_v0_3.build_authority")
    broken = build_authority.build_authority()
    broken["runtime_identity_policy"]["probe_evidence_policy"][
        "independent_probe_producers"] = [SWEPT_PROBE_PRODUCER]
    with pytest.raises(RuntimeError, match="no implementation"):
        build_authority.require_producers_exist(broken)
