"""The v0.3 execution surface exists, selects v0.3, and refuses v0.2.

Freeze ``a5d763a`` froze the v0.3 scientific artefacts -- authority, Stage-1
manifest, Stage-2 locked manifest, the extent-geometry engine -- but wired no
execution path to them. Every runner in the repository resolved the ``_v0_2``
package as a module-level literal with no override, so the only executable
default would have collected the predecessor's ``a1q_*`` / 81xxx inventory:
the units whose Stage-1 already terminated in a scientific FAIL that must never
be recollected or reinterpreted.

These tests are the closure evidence for that repair. They assert what the
blocker note said was missing, one claim at a time, and they attack the repair
from the v0.2 side rather than only confirming it from the v0.3 side.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from mineocclude.prospective.development_workflow import (  # noqa: E402
    RUNTIME_CRITICAL_SOURCE_PATHS, load_json, require_preoutcome_provenance,
    require_stage_manifest_binding, runtime_critical_source_closure_sha256,
    sha256_file,
)
from mineocclude.prospective.package_binding import (  # noqa: E402
    PackageBindingError, artifact_version_tag, package_directory,
    resolve_package_binding,
)

V0_3_ENTRYPOINTS = (
    "scripts/regime_a_prime_qualification_v0_3/generate_receipts.py",
    "scripts/regime_a_prime_qualification_v0_3/development_controller.py",
    "scripts/regime_a_prime_qualification_v0_3/verify_package.py",
    "scripts/regime_a_prime_qualification_v0_3/acceptance_harness.py",
)

#: The predecessor inventory. Terminal, immutable, never to be recollected.
PREDECESSOR_UNIT_PREFIX = "a1q_"
PREDECESSOR_EPISODES = frozenset(range(81001, 81009))


@pytest.fixture()
def v0_3():
    return resolve_package_binding("v0.3", ROOT)


@pytest.fixture()
def v0_2():
    return resolve_package_binding("v0.2", ROOT)


def _module(relative: str):
    """Import an entrypoint by its repository path, as the CLI would."""
    import importlib

    return importlib.import_module(relative.removesuffix(".py").replace("/", "."))


# ------------------------------------------------------- 1. the runner exists


@pytest.mark.parametrize("relative", V0_3_ENTRYPOINTS)
def test_v0_3_entrypoint_exists_and_declares_v0_3(relative):
    """The missing execution surface is present and self-identifies as v0.3."""
    assert (ROOT / relative).is_file(), f"v0.3 entrypoint is absent: {relative}"
    assert _module(relative).VERSION_TAG == "v0.3"


# ------------------------------------------------- 2. default package is v0.3


def test_v0_3_default_package_resolution_selects_v0_3(v0_3):
    assert v0_3.package == package_directory("v0.3", ROOT)
    assert v0_3.package.name == "prospective_development_authority_v0_3"
    assert v0_3.authority_artifact_id.endswith("-v0.3")
    assert v0_3.stage1_manifest_artifact_id == "regime-a-prime-stage1-manifest-v0.3"
    assert v0_3.authorization_artifact_id == "regime-a-prime-stage1-authorization-v0.3"
    assert v0_3.provenance_artifact_id == (
        "regime-a-prime-prospective-pre-outcome-provenance-v0.3")
    assert v0_3.run_namespace == "mineocclude-regime-a-prime-development-v0-3-stage1"


def test_generate_receipts_entrypoint_binds_v0_3_not_v0_2():
    """The v0.3 receipt generator rebinds the shared module away from v0.2."""
    shared = _module("scripts/regime_a_prime_qualification_v0_2/generate_receipts.py")
    entry = _module("scripts/regime_a_prime_qualification_v0_3/generate_receipts.py")
    try:
        shared.bind_package("v0.2", entrypoint="v0.2")
        assert shared.PACKAGE.name.endswith("v0_2")
        shared.bind_package(entry.VERSION_TAG, entrypoint=entry.ENTRYPOINT)
        assert shared.PACKAGE.name.endswith("v0_3")
        assert shared.AUTHORITY_PATH == resolve_package_binding("v0.3", ROOT).authority_path
        assert shared.PROVENANCE_ARTIFACT_ID.endswith("-v0.3")
        assert shared.AUTHORIZATION_ARTIFACT_ID.endswith("-v0.3")
        assert shared.GENERATED_BY == entry.ENTRYPOINT
    finally:
        shared.bind_package(
            "v0.2",
            entrypoint="scripts/regime_a_prime_qualification_v0_2/generate_receipts.py")


def test_controller_entrypoint_binds_v0_3_package():
    shared = _module("scripts/regime_a_prime_qualification_v0_2/development_controller.py")
    entry = _module("scripts/regime_a_prime_qualification_v0_3/development_controller.py")
    original = shared.VERSION_TAG
    try:
        shared.VERSION_TAG = entry.VERSION_TAG
        authority, stage1, stage2 = shared.paths(ROOT)
        for path in (authority, stage1, stage2):
            assert "prospective_development_authority_v0_3" in path.as_posix()
    finally:
        shared.VERSION_TAG = original


def test_controller_main_resolves_its_package_without_shadowing(tmp_path):
    """``main`` binds the name ``binding`` locally to the resolved stage binding.
    A package-resolution helper sharing that name is unreachable from inside
    ``main`` and crashes run-stage1 with UnboundLocalError before a single
    authorization check runs, so the whole-``main`` path is exercised here
    rather than only the module-level ``paths`` helper."""
    state = tmp_path / "state"
    state.mkdir()
    result = subprocess.run(
        [sys.executable, "scripts/regime_a_prime_qualification_v0_3/development_controller.py",
         "monitor", str(state)],
        cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert "UnboundLocalError" not in result.stderr
    assert json.loads(result.stdout)["durable_units"] == 0


# ------------------------------------------- 3. inventory is the new a1x set


def test_v0_3_inventory_is_exactly_the_eight_new_units(v0_3):
    units, episodes = v0_3.unit_ids(), v0_3.episode_ids()
    assert len(units) == len(episodes) == 8
    assert all(unit.startswith("a1x_") for unit in units)
    assert sorted(episodes) == list(range(83001, 83009))


def test_v0_3_inventory_contains_no_predecessor_unit(v0_3):
    """The exact failure the blocker note said a v0.2-pinned default would cause."""
    units, episodes = v0_3.unit_ids(), v0_3.episode_ids()
    assert not any(unit.startswith(PREDECESSOR_UNIT_PREFIX) for unit in units)
    assert not (set(episodes) & PREDECESSOR_EPISODES)


def test_v0_3_and_v0_2_inventories_are_disjoint(v0_3, v0_2):
    assert not (set(v0_3.unit_ids()) & set(v0_2.unit_ids()))
    assert not (set(v0_3.episode_ids()) & set(v0_2.episode_ids()))
    assert v0_3.run_namespace != v0_2.run_namespace
    assert v0_3.durable_prefix != v0_2.durable_prefix


def test_every_v0_3_unit_has_one_seed(v0_3):
    """seed and noise_seed are ONE value; sending a separate noise_seed is the
    frozen contract break the predecessor freeze already ruled out."""
    manifest = load_json(v0_3.stage1_manifest_path)
    for unit in manifest["units"]:
        assert unit["seed"] == unit["noise_seed"], unit["unit_id"]


# --------------------------------------------- 4. v0.2 substitution refusals


def test_v0_3_binding_refuses_a_package_whose_bytes_are_v0_2(tmp_path):
    """Directory naming alone cannot make a package v0.3."""
    fake_repository = tmp_path / "repo"
    target = package_directory("v0.3", fake_repository)
    target.mkdir(parents=True)
    source = package_directory("v0.2", ROOT)
    for name in ("authority_parameters.json", "stage1_manifest.json",
                 "stage2_locked_manifest.json"):
        (target / name).write_bytes((source / name).read_bytes())
    with pytest.raises(PackageBindingError, match="v0.2"):
        resolve_package_binding("v0.3", fake_repository)


def test_v0_3_runner_refuses_the_v0_2_manifest(v0_3, v0_2):
    """A v0.2 manifest handed to the v0.3 stage gate dies on artifact identity."""
    authority = load_json(v0_3.authority_path)
    with pytest.raises(PermissionError):
        require_stage_manifest_binding(
            "stage1-capture", load_json(v0_2.stage1_manifest_path),
            manifest_path=v0_2.stage1_manifest_path, authority=authority,
            repository=ROOT)


def test_v0_3_runner_refuses_the_stage2_manifest_under_stage1(v0_3):
    """Cross-stage substitution stays closed under the v0.3 authority."""
    authority = load_json(v0_3.authority_path)
    with pytest.raises(PermissionError):
        require_stage_manifest_binding(
            "stage1-capture", load_json(v0_3.stage2_manifest_path),
            manifest_path=v0_3.stage2_manifest_path, authority=authority,
            repository=ROOT)


def test_v0_3_provenance_gate_refuses_a_v0_2_provenance_identity(v0_3):
    """A receipt carrying the predecessor's artifact_id cannot authorize v0.3."""
    receipt = {"artifact_id": "regime-a-prime-prospective-pre-outcome-provenance-v0.2",
               "status": "FROZEN_VERIFIED"}
    with pytest.raises(PermissionError, match="artifact_id"):
        require_preoutcome_provenance(
            receipt, authority_path=v0_3.authority_path,
            manifest_path=v0_3.stage1_manifest_path, required_source_paths=[],
            provenance_artifact_id=v0_3.provenance_artifact_id)


def test_provenance_gate_default_identity_is_the_predecessor(v0_3):
    """A v0.3 caller that forgets to pass its identity fails closed, rather than
    silently accepting whichever receipt it was handed."""
    receipt = {"artifact_id": v0_3.provenance_artifact_id, "status": "FROZEN_VERIFIED"}
    with pytest.raises(PermissionError, match="artifact_id"):
        require_preoutcome_provenance(
            receipt, authority_path=v0_3.authority_path,
            manifest_path=v0_3.stage1_manifest_path, required_source_paths=[])


def test_binding_refuses_an_authority_the_manifest_does_not_digest(tmp_path):
    """A stale authority digest in the manifest breaks the binding."""
    fake_repository = tmp_path / "repo"
    target = package_directory("v0.3", fake_repository)
    target.mkdir(parents=True)
    source = package_directory("v0.3", ROOT)
    for name in ("authority_parameters.json", "stage1_manifest.json",
                 "stage2_locked_manifest.json"):
        (target / name).write_bytes((source / name).read_bytes())
    authority = json.loads((target / "authority_parameters.json").read_text())
    authority["_perturbed"] = True
    (target / "authority_parameters.json").write_text(json.dumps(authority))
    with pytest.raises(PackageBindingError, match="digest"):
        resolve_package_binding("v0.3", fake_repository)


# ---------------------------------------------------------- 5. artifact ids


def test_artifact_version_tag_reads_the_experiment_not_the_directory():
    assert artifact_version_tag("regime-a-prime-stage1-manifest-v0.3") == "v0.3"
    assert artifact_version_tag("regime-a-prime-stage1-manifest-v0.2") == "v0.2"
    with pytest.raises(PackageBindingError):
        artifact_version_tag("regime-a-prime-stage1-manifest")


@pytest.mark.parametrize("source_relative, prefix", [
    ("scripts/regime_a_prime_qualification_v0_2/stage_unit_driver.py",
     "regime-a-prime-development-unit-receipt-"),
    ("scripts/regime_a_prime_qualification_v0_2/build_stage1_evidence.py",
     "regime-a-prime-stage1-evidence-"),
])
def test_shared_component_labels_follow_the_manifest(source_relative, prefix):
    """The frozen v0.3 manifest names the v0.2 driver in its own unit command, so
    these shared components must label their output after the manifest they were
    handed rather than after the directory they live in."""
    text = (ROOT / source_relative).read_text()
    assert f'"{prefix}v0.2"' not in text, "artifact identity is still a v0.2 literal"
    assert prefix in text and "artifact_version_tag" in text


def test_no_v0_3_entrypoint_spells_a_v0_2_identity():
    for relative in V0_3_ENTRYPOINTS:
        text = (ROOT / relative).read_text()
        for forbidden in ("-v0.2", "authority_v0_2", "a1q_", "81001"):
            # Prose may discuss the predecessor; only executable bindings are
            # forbidden, so this checks assignment and call syntax.
            assert f'"{forbidden}' not in text, f"{relative} binds {forbidden}"


# --------------------------------------------------- 6. package verification


def test_v0_3_package_verifier_checks_v0_3_bytes():
    result = subprocess.run(
        [sys.executable, "scripts/regime_a_prime_qualification_v0_3/verify_package.py"],
        cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert "PACKAGE_VERSION=v0.3" in result.stdout
    assert "PACKAGE_STAGE1_MANIFEST_ARTIFACT_ID=regime-a-prime-stage1-manifest-v0.3" \
        in result.stdout
    assert "PACKAGE_RUN_NAMESPACE=mineocclude-regime-a-prime-development-v0-3-stage1" \
        in result.stdout
    assert "COLLECTION_AUTHORIZED=false" in result.stdout


def test_v0_2_package_verifier_still_checks_v0_2_bytes():
    """The repair must not silently repoint the predecessor's own audit."""
    result = subprocess.run(
        [sys.executable, "scripts/regime_a_prime_qualification_v0_2/verify_package.py"],
        cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert "PACKAGE_VERSION=v0.2" in result.stdout


# ------------------------------------------------------------- 7. closure


@pytest.mark.parametrize("relative", V0_3_ENTRYPOINTS + (
    "src/mineocclude/prospective/package_binding.py",))
def test_version_binding_source_is_in_the_runtime_critical_closure(relative):
    """A file that decides WHICH experiment runs is runtime-critical even though
    it carries no scientific logic."""
    assert relative in RUNTIME_CRITICAL_SOURCE_PATHS


@pytest.mark.parametrize("relative", V0_3_ENTRYPOINTS + (
    "src/mineocclude/prospective/package_binding.py",))
def test_mutating_a_version_binding_source_changes_the_closure(tmp_path, relative):
    mirror = tmp_path / "repo"
    for path in RUNTIME_CRITICAL_SOURCE_PATHS:
        destination = mirror / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / path).read_bytes())
    before = runtime_critical_source_closure_sha256(mirror)
    assert before == runtime_critical_source_closure_sha256(ROOT)
    (mirror / relative).write_bytes((ROOT / relative).read_bytes() + b"\n# mutated\n")
    assert runtime_critical_source_closure_sha256(mirror) != before


# ------------------------------------------- 8. the old result stays terminal


def test_v0_3_authority_does_not_authorize_anything(v0_3):
    authority = load_json(v0_3.authority_path)
    assert authority["STAGE_1_COLLECTION_AUTHORIZED"] is False
    assert authority["STAGE_2_COLLECTION_AUTHORIZED"] is False
    assert authority["confirmatory_collection_authorized"] is False
    assert authority["REGIME_A_PRIME_COLLECTION_AUTHORIZED"] == "NO"


def test_v0_3_manifest_records_the_predecessor_as_unreused(v0_3):
    """v0.3 is a new prospective experiment, not a reinterpretation of 560bc01."""
    manifest = load_json(v0_3.stage1_manifest_path)
    assert manifest["predecessor_freeze_sha"] == (
        "560bc01e3b01ecdc266737c015fed6677b0611c3")
    assert manifest["predecessor_units_reused"] is False
    assert manifest["STAGE_2_COLLECTION_AUTHORIZED"] is False


def test_binding_refuses_a_package_that_preauthorizes_collection(tmp_path):
    fake_repository = tmp_path / "repo"
    target = package_directory("v0.3", fake_repository)
    target.mkdir(parents=True)
    source = package_directory("v0.3", ROOT)
    for name in ("stage1_manifest.json", "stage2_locked_manifest.json"):
        (target / name).write_bytes((source / name).read_bytes())
    authority = json.loads((source / "authority_parameters.json").read_text())
    authority["STAGE_1_COLLECTION_AUTHORIZED"] = True
    (target / "authority_parameters.json").write_text(json.dumps(authority))
    with pytest.raises(PackageBindingError):
        resolve_package_binding("v0.3", fake_repository)


# --------------------------------------------- 9. no live default fallback


def test_the_frozen_v0_3_unit_command_names_the_shared_driver(v0_3):
    """The frozen manifest -- which must not change -- designates the shared unit
    driver parameterised by the v0.3 manifest. A v0.3-specific driver would have
    required editing frozen bytes, so this records why none was created."""
    manifest = load_json(v0_3.stage1_manifest_path)
    for unit in manifest["units"]:
        command = unit["command"]
        assert command[1].endswith(
            "scripts/regime_a_prime_qualification_v0_2/stage_unit_driver.py")
        assert Path(command[command.index("--manifest") + 1]) == v0_3.stage1_manifest_path
        assert command[command.index("--unit-id") + 1] == unit["unit_id"]
        assert unit["scientific_run_id"] == v0_3.run_namespace


def test_v0_3_controller_cli_resolves_the_new_manifest_not_the_predecessor():
    """The exact default invocation path that previously selected v0.2."""
    probe = (
        "import sys;"
        "sys.path[:0]=['.','src'];"
        "from scripts.regime_a_prime_qualification_v0_3 import development_controller as e;"
        "from scripts.regime_a_prime_qualification_v0_2 import development_controller as s;"
        "s.VERSION_TAG=e.VERSION_TAG;"
        "import json;"
        "a,m,_=s.paths(__import__('pathlib').Path('.').resolve());"
        "print(json.dumps({'manifest':m.as_posix(),"
        "'units':[u['unit_id'] for u in json.load(open(m))['units']]}))"
    )
    result = subprocess.run([sys.executable, "-c", probe], cwd=ROOT, text=True,
                            capture_output=True)
    assert result.returncode == 0, result.stderr
    resolved = json.loads(result.stdout)
    assert resolved["manifest"].endswith(
        "prospective_development_authority_v0_3/stage1_manifest.json")
    assert all(unit.startswith("a1x_") for unit in resolved["units"])
    assert not any(unit.startswith("a1q_") for unit in resolved["units"])


def test_v0_3_stage1_manifest_digest_is_the_frozen_one(v0_3):
    """Pins the exact bytes every gate above was proved against.

    Rebound from the ``fa9d134`` digests by the probe-producer repair. That
    freeze's authority required a probe producer that has never existed, so
    correcting the producer allow-list changed the authority bytes and, through
    ``authority_binding``, both manifests. The scientific content is unchanged:
    the delta is three probe-producer strings and the binding digests that
    deterministically follow. See
    ``test_v0_3_probe_producer_authority.py`` for the producer contract itself.

    The Stage-2 digest was rebound a second time by the Stage-2 execution-path
    repair. 54 of the 104 Stage-2 units carried no ``scientific_run_id`` -- the
    physical-gate unit, all 50 extraction units, and the three readout/terminal
    units -- and ``DurableController.run`` refuses a unit without one, so the
    pipeline could finish capturing and only then refuse to process. The builder
    now stamps every unit of the Stage-2 workflow with its own campaign
    namespace, and the manifests were regenerated deterministically through it.
    The delta is exactly 108 added ``scientific_run_id`` lines and nothing else:
    no identity, window, fold, phase, seed or episode moved. The authority and
    Stage-1 manifest digests below are unchanged, which is itself the check that
    the repair stayed inside the Stage-2 template.
    """
    assert sha256_file(v0_3.stage1_manifest_path) == (
        "424b583f93a2fd77886e534543872dd3120f0470e5f3f341ee445443c64039a3")
    assert sha256_file(v0_3.authority_path) == (
        "495af6d19b73f35a4927e48d7def4ded587ddf4d7900a8d6827ffec3ad7e982f")
    assert sha256_file(v0_3.stage2_manifest_path) == (
        "d8a80d17e7974b76d32499e75e9eda9d45e4223b53f824e253eccf32fc610bb3")
