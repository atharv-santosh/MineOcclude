"""The provenance identity follows the package version, through the binding.

Freeze ``3977836`` repaired the probe-producer contract and launched. All eight
v0.3 units then failed identically, before any capture, with::

    PermissionError: pre-outcome provenance rejects artifact_id

``stage_unit_driver.require_capture_authorization`` called
``require_preoutcome_provenance`` without naming its own provenance identity, so
the gate fell back to ``DEFAULT_PREOUTCOME_PROVENANCE_ARTIFACT_ID`` -- the v0.2
value -- while the v0.3 generator correctly emitted a v0.3 receipt.

The default is not the defect and is not changed here. It is deliberately the
predecessor's, so that a runner which cannot say which experiment it is running
is refused rather than handed whatever receipt it was given. The defect was that
the shared driver *could* say, and didn't: it already resolves its authorization
identity through ``require_stage_manifest_binding`` three lines further down,
and the provenance identity was the one identity never routed through that
binding. Under v0.2 the default happened to be right, so the omission was
invisible until a v0.3 receipt was presented for the first time.

These tests attack the repair from both sides: they prove v0.3 is propagated and
accepted, and equally that v0.2 is unchanged and that the two cannot be crossed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from mineocclude.prospective import development_workflow  # noqa: E402
from mineocclude.prospective.development_workflow import (  # noqa: E402
    DEFAULT_PREOUTCOME_PROVENANCE_ARTIFACT_ID, RUNTIME_CRITICAL_SOURCE_PATHS,
    load_json, require_preoutcome_provenance, require_stage_manifest_binding,
)
from mineocclude.prospective.package_binding import (  # noqa: E402
    PackageBindingError, provenance_artifact_id_for, resolve_package_binding,
)

V0_2_PROVENANCE_ARTIFACT_ID = "regime-a-prime-prospective-pre-outcome-provenance-v0.2"
V0_3_PROVENANCE_ARTIFACT_ID = "regime-a-prime-prospective-pre-outcome-provenance-v0.3"

#: The predecessor inventory, whose Stage-1 already terminated in scientific FAIL.
PREDECESSOR_UNIT_PREFIX = "a1q_"
#: The v0.3 inventory this repair exists to let run.
CURRENT_UNIT_PREFIX = "a1x_"

#: The exact message the blocked campaign emitted, eight times.
BLOCKED_MESSAGE = "pre-outcome provenance rejects artifact_id"

DRIVER_RELATIVE = "scripts/regime_a_prime_qualification_v0_2/stage_unit_driver.py"


@pytest.fixture()
def v0_3():
    return resolve_package_binding("v0.3", ROOT)


@pytest.fixture()
def v0_2():
    return resolve_package_binding("v0.2", ROOT)


@pytest.fixture()
def driver():
    """The shared unit driver, imported the way the locked unit command runs it."""
    import importlib

    return importlib.import_module(DRIVER_RELATIVE.removesuffix(".py").replace("/", "."))


def _stage1_binding(package):
    return require_stage_manifest_binding(
        "stage1-capture", load_json(package.stage1_manifest_path),
        manifest_path=package.stage1_manifest_path,
        authority=load_json(package.authority_path), repository=ROOT)


def _first_rejection(receipt, package, **kwargs) -> str:
    """The first expectation the gate refuses on, or ``<accepted>``.

    The gate checks ``artifact_id`` before anything else, so the key it names is
    a precise probe for whether the identity check passed -- without needing a
    receipt that satisfies every later binding.
    """
    try:
        require_preoutcome_provenance(
            receipt, authority_path=package.authority_path,
            manifest_path=package.stage1_manifest_path,
            required_source_paths=[ROOT / r for r in RUNTIME_CRITICAL_SOURCE_PATHS],
            **kwargs)
        return "<accepted>"
    except PermissionError as exc:
        return str(exc)


# --------------------------------------- 1-2. the binding exposes the identity


def test_v0_3_stage_binding_exposes_its_own_provenance_identity(v0_3):
    """The value the driver was missing is now on the binding it already had."""
    binding = _stage1_binding(v0_3)
    assert binding["provenance_artifact_id"] == V0_3_PROVENANCE_ARTIFACT_ID


def test_v0_2_stage_binding_exposes_its_own_provenance_identity(v0_2):
    binding = _stage1_binding(v0_2)
    assert binding["provenance_artifact_id"] == V0_2_PROVENANCE_ARTIFACT_ID


def test_stage_binding_agrees_with_the_package_binding(v0_2, v0_3):
    """Two independent routes to the same identity must not diverge."""
    for package in (v0_2, v0_3):
        assert _stage1_binding(package)["provenance_artifact_id"] == (
            package.provenance_artifact_id)


def test_stage2_binding_carries_its_own_version_too(v0_3):
    """Every declared stage resolves an identity, not just stage1-capture."""
    binding = require_stage_manifest_binding(
        "stage2-capture", load_json(v0_3.stage2_manifest_path),
        manifest_path=v0_3.stage2_manifest_path,
        authority=load_json(v0_3.authority_path), repository=ROOT)
    assert binding["provenance_artifact_id"] == V0_3_PROVENANCE_ARTIFACT_ID


# ------------------------------- 3-4. the driver propagates it, both versions


@pytest.mark.parametrize("tag,expected", [("v0.2", V0_2_PROVENANCE_ARTIFACT_ID),
                                          ("v0.3", V0_3_PROVENANCE_ARTIFACT_ID)])
def test_unit_driver_passes_the_bound_provenance_identity(driver, monkeypatch,
                                                          tmp_path, tag, expected):
    """The regression itself: the driver must NAME its provenance identity.

    Intercepts the gate rather than satisfying it, so the assertion is about what
    the driver passes -- which is the thing that was missing -- and not about
    whether a fixture receipt happens to reproduce a live apparatus.
    """
    package = resolve_package_binding(tag, ROOT)
    captured = {}

    def _capture(receipt, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(driver, "require_preoutcome_provenance", _capture)
    monkeypatch.setattr(driver, "subprocess_text", lambda *a, **k: "deadbeef\n")
    provenance = tmp_path / "provenance.json"
    provenance.write_text(json.dumps({"artifact_id": expected}))
    monkeypatch.setenv("MINEOCCLUDE_PREOUTCOME_PROVENANCE_PATH", str(provenance))
    # No authorization receipt: the run must reach the gate *after* provenance,
    # which proves propagation happened and that provenance was not the stop.
    monkeypatch.setenv("MINEOCCLUDE_STAGE1_AUTHORIZATION_PATH", str(tmp_path / "absent"))

    manifest = load_json(package.stage1_manifest_path)
    with pytest.raises(PermissionError, match="Stage-1 authorization receipt is required"):
        driver.require_capture_authorization(
            "stage1-capture", manifest, package.stage1_manifest_path,
            package.authority_path)

    assert captured.get("provenance_artifact_id") == expected


def test_unit_driver_startup_reaches_beyond_provenance_for_a_valid_v0_3_binding(
        driver, monkeypatch, tmp_path, v0_3):
    """The blocked campaign never got past provenance. This proves it now does."""
    reached = []
    monkeypatch.setattr(driver, "require_preoutcome_provenance",
                        lambda receipt, **kwargs: reached.append(kwargs))
    monkeypatch.setattr(driver, "subprocess_text", lambda *a, **k: "deadbeef\n")
    provenance = tmp_path / "provenance.json"
    provenance.write_text(json.dumps({"artifact_id": V0_3_PROVENANCE_ARTIFACT_ID}))
    monkeypatch.setenv("MINEOCCLUDE_PREOUTCOME_PROVENANCE_PATH", str(provenance))
    monkeypatch.setenv("MINEOCCLUDE_STAGE1_AUTHORIZATION_PATH", str(tmp_path / "absent"))

    with pytest.raises(PermissionError) as exc:
        driver.require_capture_authorization(
            "stage1-capture", load_json(v0_3.stage1_manifest_path),
            v0_3.stage1_manifest_path, v0_3.authority_path)

    assert reached, "provenance gate was never reached"
    assert BLOCKED_MESSAGE not in str(exc.value)


# ------------------------------------------- 5-7. acceptance and cross-refusal


def test_v0_3_provenance_identity_is_accepted_by_the_v0_3_gate(v0_3):
    """A v0.3 receipt no longer dies on artifact_id when v0.3 is named."""
    receipt = {"artifact_id": V0_3_PROVENANCE_ARTIFACT_ID}
    rejection = _first_rejection(receipt, v0_3,
                                 provenance_artifact_id=V0_3_PROVENANCE_ARTIFACT_ID)
    assert rejection != BLOCKED_MESSAGE


def test_v0_3_provenance_is_refused_when_evaluated_as_v0_2(v0_3):
    """The exact historical failure, preserved as a control."""
    receipt = {"artifact_id": V0_3_PROVENANCE_ARTIFACT_ID}
    assert _first_rejection(
        receipt, v0_3, provenance_artifact_id=V0_2_PROVENANCE_ARTIFACT_ID
    ) == BLOCKED_MESSAGE


def test_v0_2_provenance_is_refused_by_the_v0_3_gate(v0_3):
    """A predecessor receipt cannot authorize the successor campaign."""
    receipt = {"artifact_id": V0_2_PROVENANCE_ARTIFACT_ID}
    assert _first_rejection(
        receipt, v0_3, provenance_artifact_id=V0_3_PROVENANCE_ARTIFACT_ID
    ) == BLOCKED_MESSAGE


# ------------------------------------------------ 8-9. the default stays closed


def test_the_v0_2_default_is_unchanged():
    """Changing this constant was the forbidden repair. It must still be v0.2."""
    assert DEFAULT_PREOUTCOME_PROVENANCE_ARTIFACT_ID == V0_2_PROVENANCE_ARTIFACT_ID


def test_omitting_the_identity_still_fails_closed_on_a_v0_3_receipt(v0_3):
    """A runner that names no identity is refused, not quietly upgraded to v0.3."""
    receipt = {"artifact_id": V0_3_PROVENANCE_ARTIFACT_ID}
    assert _first_rejection(receipt, v0_3) == BLOCKED_MESSAGE


def test_wrong_artifact_id_is_refused_even_when_later_bindings_would_hold(v0_3):
    """Identity is checked first and independently of every other expectation."""
    receipt = {"artifact_id": "regime-a-prime-prospective-pre-outcome-provenance-v9.9",
               "status": "FROZEN_VERIFIED", "independently_derived": True,
               "scientific_outcomes_observed": False}
    assert _first_rejection(
        receipt, v0_3, provenance_artifact_id=V0_3_PROVENANCE_ARTIFACT_ID
    ) == BLOCKED_MESSAGE


# ----------------------------------- 10-11. the identity derivation is honest


def test_provenance_identity_is_derived_from_the_tag_not_hardcoded():
    assert provenance_artifact_id_for("v0.2") == V0_2_PROVENANCE_ARTIFACT_ID
    assert provenance_artifact_id_for("v0.3") == V0_3_PROVENANCE_ARTIFACT_ID


@pytest.mark.parametrize("malformed", ["v0", "0.3", "v0.3-extra", "", "V0.3"])
def test_malformed_version_tags_are_refused(malformed):
    """Derivation must not silently mint an identity from garbage."""
    with pytest.raises(PackageBindingError):
        provenance_artifact_id_for(malformed)


def test_a_stage_table_mixing_versions_is_refused(v0_3):
    """The symmetry check: manifest and authorization must name one version.

    A stage entry binding a v0.3 manifest to a v0.2 authorization would otherwise
    yield an identity derived from whichever field was consulted first.
    """
    authority = load_json(v0_3.authority_path)
    authority["stage_binding_policy"]["stages"]["stage1-capture"][
        "authorization_artifact_id"] = "regime-a-prime-stage1-authorization-v0.2"
    with pytest.raises(PermissionError, match="v0.3 manifest to an v0.2 authorization"):
        require_stage_manifest_binding(
            "stage1-capture", load_json(v0_3.stage1_manifest_path),
            manifest_path=v0_3.stage1_manifest_path, authority=authority,
            repository=ROOT)


# ------------------------------- 12-14. the inventory and Stage-2 are unmoved


def test_v0_3_binding_still_selects_the_a1x_inventory(v0_3):
    units = v0_3.unit_ids()
    assert len(units) == 8
    assert all(unit.startswith(CURRENT_UNIT_PREFIX) for unit in units)
    assert not any(unit.startswith(PREDECESSOR_UNIT_PREFIX) for unit in units)
    assert list(v0_3.episode_ids()) == list(range(83001, 83009))


def test_a1q_substitution_into_the_v0_3_stage_is_still_refused(v0_3, v0_2):
    """The predecessor units cannot be drawn into a v0.3 stage-1 run."""
    predecessor = load_json(v0_2.stage1_manifest_path)["units"][0]
    assert predecessor["unit_id"].startswith(PREDECESSOR_UNIT_PREFIX)
    with pytest.raises(PermissionError):
        require_stage_manifest_binding(
            "stage1-capture", load_json(v0_3.stage1_manifest_path),
            manifest_path=v0_3.stage1_manifest_path,
            authority=load_json(v0_3.authority_path), unit=predecessor,
            repository=ROOT)


def test_v0_3_authority_still_carries_the_unauthorized_baseline(v0_3):
    """Stage-2 stays unauthorized across this repair."""
    authority = load_json(v0_3.authority_path)
    assert authority["STAGE_1_COLLECTION_AUTHORIZED"] is False
    assert authority["STAGE_2_COLLECTION_AUTHORIZED"] is False
    assert authority["confirmatory_collection_authorized"] is False


def test_v0_3_controller_hands_the_driver_a_v0_3_identity():
    """The delegated route resolves the same identity the direct route does."""
    import importlib

    controller = importlib.import_module(
        "scripts.regime_a_prime_qualification_v0_3.development_controller")
    assert controller.VERSION_TAG == "v0.3"
    assert resolve_package_binding(
        controller.VERSION_TAG, ROOT).provenance_artifact_id == V0_3_PROVENANCE_ARTIFACT_ID


def test_package_binding_source_is_runtime_critical():
    """The derivation lives in bytes the closure certifies."""
    assert "src/mineocclude/prospective/package_binding.py" in RUNTIME_CRITICAL_SOURCE_PATHS
    assert DRIVER_RELATIVE in RUNTIME_CRITICAL_SOURCE_PATHS
