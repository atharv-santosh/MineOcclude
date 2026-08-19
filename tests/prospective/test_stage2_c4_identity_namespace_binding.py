#!/usr/bin/env python3
"""Regression suite for C4 -- the Stage-2 identity namespace collision.

The T1 scientific canary survived governance, survived the checkpoint load that
C3 had been killing, extracted layer 4, wrote a 26MB activation, and then died
building its receipt::

    AttributeError: 'dict' object has no attribute 'legacy_capture_trajectory_id'

``extraction()`` binds two identities that are different *types* in different
*namespaces*:

* ``resolve_typed_capture_identity()`` -> ``TypedCaptureIdentity``, a frozen
  dataclass read with ``.``, carrying the capture's four typed identities.
* ``require_activation_identity()`` -> ``dict``, read with ``[]``, carrying the
  producing model's checkpoint digests. It knows nothing about trajectories.

Both were bound to the name ``identity``. The second rebinding shadowed the
first, so the receipt asked a mapping of checkpoint digests for a trajectory
identity -- after fifty minutes of model load and extraction, on a path with no
earlier failure. ``extract()`` itself was fine: its call site sits *above* the
rebinding, which is exactly why no test and no probe ever saw this.

The mapping-access "fix" (``identity["legacy_capture_trajectory_id"]``) is wrong
and this suite refuses it: the runtime identity dict has no such key, and forcing
one there would write a checkpoint namespace into a trajectory field. The
semantic fix is two names for two namespaces, and the tests below pin the type
contract, the production-path binding, and the fail-closed behaviour on each side
of the namespace boundary.
"""

from __future__ import annotations

import ast
import copy
import io
import json
import sys
from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src"),
                str(ROOT / "scripts/regime_a_prime_qualification_v0_1"),
                str(ROOT / "scripts/regime_a_prime_qualification_v0_2")]

from mineocclude.prospective import capture_closure as cc  # noqa: E402
from mineocclude.prospective import physical_gate_admission as pga  # noqa: E402
from mineocclude.prospective.activation_binding import (  # noqa: E402
    ACTIVATION_IDENTITY_FIELDS, EvidenceError, REQUIRED_IDENTITY_DIGESTS,
    REQUIRED_IDENTITY_INTEGERS, REQUIRED_IDENTITY_TEXT,
    require_activation_identity)
from mineocclude.prospective.capture_admission import (  # noqa: E402
    CaptureAdmissionError, TypedCaptureIdentity, resolve_typed_capture_identity,
    verify_capture_package_identity, verify_visibility_rows_scientific_identity)
from mineocclude.prospective.package_binding import package_directory  # noqa: E402

PACKAGE = package_directory("v0.4", ROOT)
MANIFEST_PATH = PACKAGE / "stage2_locked_manifest.json"
AUTHORITY_PATH = PACKAGE / "authority_parameters.json"

BACKEND = ROOT / "scripts/regime_a_prime_qualification_v0_2/stage2_backend.py"
PROBE = ROOT / "src/mineocclude/prospective/stage2_processability.py"

#: The frozen capture apparatus. A processing repair may never move it.
CAPTURE_CRITICAL_CLOSURE = "b64bc70071d2efbbd90e04ca31f4fdaf508498eb51e36c69b584c3602284fa68"
#: The gate-critical closure that admits the historical 50/50 physical-gate PASS.
GATE_CRITICAL_CLOSURE = "199ae4dd4a29d2dad9ee47984268171a5a667ab7f3adee48323f178dc946fa89"

#: The unit the canary ran, and the two identities it must carry.
CANARY_UNIT = "a2y_t01_wall"
CANARY_LEGACY_ID = "layout_01_ep86001"
CANARY_SCIENTIFIC_ID = "a2y_t01"

#: The constructors whose results must never share a name.
CAPTURE_IDENTITY_CALL = "resolve_typed_capture_identity"
RUNTIME_IDENTITY_CALL = "require_activation_identity"

#: The attributes that only the typed capture identity has.
TRAJECTORY_ATTRIBUTES = ("legacy_capture_trajectory_id", "scientific_trajectory_id",
                         "scientific_capture_unit_id", "episode_id", "layout_id")


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_bytes())


@pytest.fixture(scope="module")
def authority() -> dict:
    return json.loads(AUTHORITY_PATH.read_bytes())


@pytest.fixture(scope="module")
def canary_unit(manifest) -> dict:
    return next(unit for unit in manifest["capture_units"]
                if unit["unit_id"] == CANARY_UNIT)


@pytest.fixture(scope="module")
def capture_identity(authority, canary_unit) -> TypedCaptureIdentity:
    """The REAL typed identity, from the frozen authority and the frozen manifest.

    Not a stand-in: this is the object ``extraction()`` builds for the unit the
    canary actually ran.
    """
    return resolve_typed_capture_identity(authority, canary_unit)


def _runtime_identity_payload() -> dict:
    """A model runtime identity shaped exactly as ``ensure_loaded()`` emits one.

    Every required field is present and well-formed, so the object under test is
    an ACCEPTED identity rather than a rejected one -- the canary's dict had
    already passed ``require_activation_identity`` when the AttributeError fired.
    """
    payload: dict[str, object] = {}
    for index, name in enumerate(REQUIRED_IDENTITY_DIGESTS):
        payload[name] = f"{index + 1:x}" * 64
    for name in REQUIRED_IDENTITY_TEXT:
        payload[name] = f"frozen-{name.replace('_', '-')}"
    for name in REQUIRED_IDENTITY_INTEGERS:
        payload[name] = 1
    return payload


@pytest.fixture(scope="module")
def runtime_identity() -> dict:
    """The REAL return value of ``require_activation_identity`` -- a plain dict.

    Produced by running the production function, not by hand-building a mapping,
    so the type under test is the type the canary held.
    """
    identity = _runtime_identity_payload()
    record = {"model_runtime_identity": identity,
              "main_checkpoint_sha256": identity["main_checkpoint_sha256"],
              "vae_checkpoint_sha256": identity["vae_checkpoint_sha256"]}
    return require_activation_identity(record, label=CANARY_UNIT)


# ======================================================================
# The runtime representations, as the canary actually held them
# ======================================================================

class TestTheTwoIdentityRepresentations:
    """C4 stated as types: what each object IS, and what it therefore cannot do."""

    def test_runtime_identity_is_a_plain_dict(self, runtime_identity):
        """IDENTITY_RUNTIME_TYPE. The canary's traceback said 'dict'; so does this."""
        assert type(runtime_identity) is dict

    def test_the_exact_canary_attributeerror_reproduces(self, runtime_identity):
        """The failure, verbatim. This is the line-593 expression on the real object."""
        with pytest.raises(AttributeError) as raised:
            runtime_identity.legacy_capture_trajectory_id      # noqa: B018
        assert "'dict' object has no attribute 'legacy_capture_trajectory_id'" \
            in str(raised.value)

    def test_the_scientific_attribute_fails_the_same_way(self, runtime_identity):
        """Repairing only line 593 would have died on the very next line."""
        with pytest.raises(AttributeError):
            runtime_identity.scientific_trajectory_id           # noqa: B018

    def test_typed_capture_identity_is_not_a_mapping(self, capture_identity):
        """IDENTITY_EXPECTED_TYPE. The two types are not interchangeable in either
        direction: this one refuses subscripting as firmly as the dict refuses
        attributes, which is why one name could never serve both."""
        assert isinstance(capture_identity, TypedCaptureIdentity)
        assert not isinstance(capture_identity, Mapping)
        with pytest.raises(TypeError):
            capture_identity["legacy_capture_trajectory_id"]    # noqa: B018

    def test_mapping_access_on_the_runtime_identity_is_not_the_fix(self, runtime_identity):
        """The tempting one-character patch, refused on evidence.

        ``identity["legacy_capture_trajectory_id"]`` does not raise AttributeError
        -- it raises KeyError, because the model runtime identity has no
        trajectory namespace at all. Mapping access is not the canonical form of
        this value; it is a different value that does not exist.
        """
        with pytest.raises(KeyError):
            runtime_identity["legacy_capture_trajectory_id"]    # noqa: B018
        assert not any(name in runtime_identity for name in TRAJECTORY_ATTRIBUTES)

    def test_the_runtime_identity_carries_only_the_model_namespace(self, runtime_identity):
        """What it DOES carry, so the two namespaces are visibly disjoint."""
        assert set(runtime_identity) == set(ACTIVATION_IDENTITY_FIELDS)

    def test_the_typed_identity_is_frozen(self, capture_identity):
        """It cannot be mutated into carrying the other namespace either."""
        with pytest.raises(FrozenInstanceError):
            capture_identity.legacy_capture_trajectory_id = "anything"


# ======================================================================
# The identities themselves, on the unit the canary ran
# ======================================================================

class TestTheIdentityRuleIsUnchanged:
    """The historical namespace rule, re-proved after the repair."""

    def test_scientific_identity_is_the_a2y_form(self, capture_identity):
        assert capture_identity.scientific_trajectory_id == CANARY_SCIENTIFIC_ID

    def test_legacy_identity_is_the_apparatus_derived_form(self, capture_identity):
        assert capture_identity.legacy_capture_trajectory_id == CANARY_LEGACY_ID

    def test_the_two_namespaces_are_never_string_equal(self, capture_identity):
        assert (capture_identity.legacy_capture_trajectory_id
                != capture_identity.scientific_trajectory_id)

    def test_the_legacy_identity_is_derived_from_authority_not_read_from_bytes(
            self, capture_identity, authority, canary_unit):
        """LEGACY_CAPTURE_TRAJECTORY_ID_SOURCE, stated as behaviour.

        It is the frozen authority's ``layout_id`` composed with the manifest
        unit's ``episode_id``. A capture package cannot supply it.
        """
        layout = authority["apparatus"]["layout_id"]
        assert capture_identity.legacy_capture_trajectory_id == (
            f"{layout}_ep{canary_unit['episode_id']}")

    def test_the_scientific_identity_comes_from_the_manifest_unit(
            self, capture_identity, canary_unit):
        """SCIENTIFIC_TRAJECTORY_ID_SOURCE."""
        assert capture_identity.scientific_trajectory_id == canary_unit["trajectory_id"]

    def test_all_fifty_units_resolve_both_namespaces_disjointly(self, authority, manifest):
        """Not just the canary's unit: the rule holds across the whole cohort."""
        legacy, scientific = set(), set()
        for unit in manifest["capture_units"]:
            identity = resolve_typed_capture_identity(authority, unit)
            legacy.add(identity.legacy_capture_trajectory_id)
            scientific.add(identity.scientific_trajectory_id)
        assert len(manifest["capture_units"]) == 50
        assert not (legacy & scientific), "the two namespaces overlap"


# ======================================================================
# The production path -- the test that fails on the predecessor
# ======================================================================

def _function_ast(path: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{path.name} defines no {name}()")


def _names_bound_from(function: ast.AST, call: str) -> set[str]:
    """Every simple name assigned the result of ``call(...)`` in this function."""
    bound: set[str] = set()
    for node in ast.walk(function):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        callee = node.value.func
        callee_name = callee.id if isinstance(callee, ast.Name) else getattr(
            callee, "attr", None)
        if callee_name != call:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                bound.add(target.id)
    return bound


def _attribute_bases(function: ast.AST, attribute: str) -> set[str]:
    """Every simple name ``x`` appearing as ``x.<attribute>`` in this function."""
    return {node.value.id for node in ast.walk(function)
            if isinstance(node, ast.Attribute) and node.attr == attribute
            and isinstance(node.value, ast.Name)}


PRODUCTION_SITES = [
    pytest.param(BACKEND, "extraction", id="scientific-backend-extraction"),
    pytest.param(PROBE, "prober", id="operational-processability-prober"),
]


class TestProductionPathBindsTheNamespacesToDistinctNames:
    """The regression proper. On the predecessor both names are ``identity``."""

    @pytest.mark.parametrize("path,function_name", PRODUCTION_SITES)
    def test_the_two_constructors_never_share_a_name(self, path, function_name):
        """C4 itself: the shadowing that produced the AttributeError.

        Checked on the shipped source, not on a copy, and at BOTH production
        sites -- the probe carried the identical shadow latently, surviving only
        because it never read the typed identity back after rebinding.
        """
        function = _function_ast(path, function_name)
        capture_names = _names_bound_from(function, CAPTURE_IDENTITY_CALL)
        runtime_names = _names_bound_from(function, RUNTIME_IDENTITY_CALL)
        assert capture_names, f"{function_name}() binds no typed capture identity"
        assert runtime_names, f"{function_name}() binds no model runtime identity"
        shared = capture_names & runtime_names
        assert not shared, (
            f"{path.name}::{function_name} binds the typed capture identity and the "
            f"model runtime identity to the same name(s) {sorted(shared)}; the "
            f"second rebinding shadows the first and every later '.'-access on it "
            f"raises AttributeError")

    @pytest.mark.parametrize("path,function_name", PRODUCTION_SITES)
    @pytest.mark.parametrize("attribute", ["legacy_capture_trajectory_id",
                                           "scientific_trajectory_id"])
    def test_trajectory_attributes_are_only_read_off_the_typed_identity(
            self, path, function_name, attribute):
        """The follow-on failures, refused as a class.

        Fixing line 593 alone would have died on line 594. Rather than pin two
        lines, this asserts the invariant: every ``.<trajectory attribute>`` in
        the function reads a name bound from ``resolve_typed_capture_identity``.
        """
        function = _function_ast(path, function_name)
        capture_names = _names_bound_from(function, CAPTURE_IDENTITY_CALL)
        for base in _attribute_bases(function, attribute):
            assert base in capture_names, (
                f"{path.name}::{function_name} reads .{attribute} off {base!r}, "
                f"which is not a typed capture identity")

    @pytest.mark.parametrize("path,function_name", PRODUCTION_SITES)
    def test_the_runtime_identity_is_never_read_with_attribute_access(
            self, path, function_name):
        """The mirror image: no name bound from the runtime constructor may be
        read with ``.`` for a trajectory attribute."""
        function = _function_ast(path, function_name)
        runtime_names = _names_bound_from(function, RUNTIME_IDENTITY_CALL)
        for attribute in TRAJECTORY_ATTRIBUTES:
            offenders = _attribute_bases(function, attribute) & runtime_names
            assert not offenders, (
                f"{path.name}::{function_name} reads .{attribute} off the model "
                f"runtime identity {sorted(offenders)}")

    def test_the_receipt_still_records_both_namespaces(self):
        """The repair must not have dropped a field to make the error go away.

        The activation receipt carries the model identity AND both trajectory
        identities; a rename that quietly deleted one would leave the activation
        unattributable.
        """
        backend_source = BACKEND.read_text()
        function_source = ast.get_source_segment(
            backend_source, _function_ast(BACKEND, "extraction"))
        for field in ("model_runtime_identity", "legacy_capture_trajectory_id",
                      "scientific_trajectory_id", "main_checkpoint_sha256",
                      "vae_checkpoint_sha256"):
            assert f'"{field}"' in function_source, f"receipt no longer records {field}"

    def test_the_receipt_payload_evaluates_on_the_real_objects(
            self, capture_identity, runtime_identity):
        """The repaired expression, executed against both REAL objects.

        This is the line-593 receipt fragment with the successor's names. On the
        predecessor the single name ``identity`` holds ``runtime_identity`` here
        and the same fragment raises. Nothing synthetic stands in for either type.
        """
        payload = {
            "model_runtime_identity": runtime_identity,
            "main_checkpoint_sha256": runtime_identity["main_checkpoint_sha256"],
            "vae_checkpoint_sha256": runtime_identity["vae_checkpoint_sha256"],
            "legacy_capture_trajectory_id": (
                capture_identity.legacy_capture_trajectory_id),
            "scientific_trajectory_id": capture_identity.scientific_trajectory_id}
        assert payload["legacy_capture_trajectory_id"] == CANARY_LEGACY_ID
        assert payload["scientific_trajectory_id"] == CANARY_SCIENTIFIC_ID
        assert payload["main_checkpoint_sha256"] != payload["vae_checkpoint_sha256"]
        # And the receipt is serialisable, which the predecessor never reached.
        assert json.loads(json.dumps(payload))["scientific_trajectory_id"] == (
            CANARY_SCIENTIFIC_ID)

    def test_the_predecessor_expression_still_raises_on_a_shadowed_name(
            self, runtime_identity):
        """The predecessor semantics, preserved as an executable statement.

        If a future edit reintroduces the shadow, this is what that code does.
        """
        identity = runtime_identity          # the rebinding, verbatim
        with pytest.raises(AttributeError):
            {"legacy_capture_trajectory_id": identity.legacy_capture_trajectory_id}


# ======================================================================
# Fail-closed on each side of the namespace boundary
# ======================================================================

class TestIdentityFailsClosed:
    """Neither namespace may be absent, wrong, or silently normalised."""

    def test_a_missing_legacy_identity_refuses(self, authority, canary_unit):
        """The legacy identity is composed from the episode; without one there is
        nothing to compose and the unit is refused rather than defaulted."""
        unit = copy.deepcopy(canary_unit)
        del unit["episode_id"]
        with pytest.raises(CaptureAdmissionError, match="episode_id"):
            resolve_typed_capture_identity(authority, unit)

    def test_a_missing_layout_refuses(self, authority, canary_unit):
        broken = copy.deepcopy(authority)
        del broken["apparatus"]["layout_id"]
        with pytest.raises(CaptureAdmissionError, match="layout_id"):
            resolve_typed_capture_identity(broken, canary_unit)

    def test_a_missing_scientific_identity_refuses(self, authority, canary_unit):
        unit = copy.deepcopy(canary_unit)
        del unit["trajectory_id"]
        with pytest.raises(CaptureAdmissionError, match="trajectory_id"):
            resolve_typed_capture_identity(authority, unit)

    def test_a_wrong_legacy_identity_on_the_package_refuses(self, capture_identity):
        """A capture package for another episode cannot authenticate itself."""
        package = {"trajectory_id": "layout_01_ep86002",
                   "episode_id": capture_identity.episode_id,
                   "layout_id": capture_identity.layout_id}
        with pytest.raises(CaptureAdmissionError, match="legacy capture trajectory"):
            verify_capture_package_identity(package, capture_identity)

    def test_a_wrong_scientific_identity_on_the_rows_refuses(self, capture_identity):
        """The Stage-2 side of the boundary, checked independently."""
        rows = [{"trajectory_id": "a2y_t02"}]
        with pytest.raises(CaptureAdmissionError, match="scientific trajectory"):
            verify_visibility_rows_scientific_identity(rows, capture_identity)

    def test_the_legacy_identity_cannot_masquerade_as_the_scientific_one(
            self, capture_identity):
        """History cannot be normalised by swapping the namespaces.

        Handing the scientific checker the legacy value -- the exact conflation
        ``TypedCaptureIdentity`` exists to prevent -- is refused, not accepted as
        an alias.
        """
        rows = [{"trajectory_id": capture_identity.legacy_capture_trajectory_id}]
        with pytest.raises(CaptureAdmissionError):
            verify_visibility_rows_scientific_identity(rows, capture_identity)

    def test_the_scientific_identity_cannot_masquerade_as_the_legacy_one(
            self, capture_identity):
        package = {"trajectory_id": capture_identity.scientific_trajectory_id,
                   "episode_id": capture_identity.episode_id,
                   "layout_id": capture_identity.layout_id}
        with pytest.raises(CaptureAdmissionError):
            verify_capture_package_identity(package, capture_identity)

    def test_colliding_namespaces_refuse_at_construction(self, authority, canary_unit):
        """If the two identities were ever made string-equal, a legacy check and a
        scientific check could not be told apart. That is refused up front."""
        unit = copy.deepcopy(canary_unit)
        unit["trajectory_id"] = (
            f"{authority['apparatus']['layout_id']}_ep{unit['episode_id']}")
        with pytest.raises(CaptureAdmissionError, match="collides"):
            resolve_typed_capture_identity(authority, unit)

    def test_a_runtime_identity_missing_a_field_refuses(self):
        """The other namespace fails closed too: an activation whose producing
        model cannot be fully named is never accepted."""
        identity = _runtime_identity_payload()
        del identity["runtime_id"]
        record = {"model_runtime_identity": identity,
                  "main_checkpoint_sha256": identity["main_checkpoint_sha256"],
                  "vae_checkpoint_sha256": identity["vae_checkpoint_sha256"]}
        with pytest.raises(EvidenceError, match="incomplete"):
            require_activation_identity(record, label=CANARY_UNIT)

    def test_a_runtime_identity_is_never_accepted_as_a_trajectory_identity(self):
        """The two namespaces cannot be substituted for one another at the API
        level either: the model identity has no trajectory field to check."""
        identity = _runtime_identity_payload()
        with pytest.raises(CaptureAdmissionError):
            verify_visibility_rows_scientific_identity(
                [identity],
                TypedCaptureIdentity(
                    legacy_capture_trajectory_id=CANARY_LEGACY_ID,
                    scientific_trajectory_id=CANARY_SCIENTIFIC_ID,
                    scientific_capture_unit_id=CANARY_UNIT,
                    episode_id=86001, scene="WALL", layout_id="layout_01"))


# ======================================================================
# Governance: a processing repair may not move capture or gate closure
# ======================================================================

class TestClosureInvariance:
    """The repair is confined to processing; the frozen apparatus must not move."""

    def test_capture_critical_closure_is_unchanged(self):
        closure, _ = cc.capture_critical_closure_at(
            cc.worktree_reader(ROOT), repository=ROOT)
        assert closure == CAPTURE_CRITICAL_CLOSURE

    def test_gate_critical_closure_is_unchanged(self):
        """``extraction()`` is not reachable from ``gates()``, so repairing it
        cannot refuse the historical 50/50 physical-gate PASS."""
        closure, _ = pga.gate_critical_closure_at(
            cc.worktree_reader(ROOT), repository=ROOT)
        assert closure == GATE_CRITICAL_CLOSURE

    def test_extraction_is_not_a_gate_critical_component(self):
        """Stated directly, so a future edit that makes it gate-reachable is seen
        as a governance change rather than as a mysterious closure move."""
        _, components = pga.gate_critical_closure_at(
            cc.worktree_reader(ROOT), repository=ROOT)
        names = {str(component) for component in components}
        assert not any(name.endswith("stage2_backend.py::extraction") for name in names)
        assert any(name.endswith("stage2_backend.py::gates") for name in names)
