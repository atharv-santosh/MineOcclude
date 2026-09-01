"""A6 -- the P2 prospective freeze (authority 6/A6).

A6's pass condition is that every binding is present, non-null and **verified
against the live artifact**, and its forbidden repair is "freezing with a
placeholder, a null, or a 'to be determined'". So these tests do two things the
prior suite did not do at all: they run the **committed producer** end to end
over the real banked evidence, and they corrupt one binding at a time to prove
each refusal actually fires.

Every negative case is built by copying the real evidence tree into ``tmp_path``
and damaging exactly one artifact, so a test that passes for the wrong reason
(an unrelated missing file) is not possible.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from mineocclude.experiment_iii.authority import canonical_sha256, machine_authority
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.p2_freeze import (
    BINDING_GROUPS,
    P2_FREEZE_SCHEMA_VERSION,
    build_p2_freeze_package,
    p2_freeze_passed,
    verify_p2_freeze_package,
)
from mineocclude.experiment_iii.source_closure import source_closure

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DOCS = REPOSITORY_ROOT / "docs" / "experiment_iii"
DATA = REPOSITORY_ROOT / "data" / "experiment_iii"
PRODUCER = REPOSITORY_ROOT / "scripts" / "experiment_iii" / "build_p2_freeze.py"

EXTRACTION_A3 = DOCS / "receipts" / "environment_receipt_gpu_extraction_host.json"
ACTIVATIONS = DATA / "p1" / "activations"
P1_RECEIPT = DOCS / "p1" / "p1_pilot_receipt.json"
P0_DIR = DOCS / "p0"

#: A6 stands on completed A4 and A5 evidence. Where that evidence is not in the
#: working tree there is nothing to freeze, and a test that pretended otherwise
#: would be asserting against fixtures rather than against the experiment.
_EVIDENCE_PRESENT = (
    EXTRACTION_A3.is_file()
    and P1_RECEIPT.is_file()
    and (P0_DIR / "P0_SELECTION_RECEIPT.json").is_file()
    and (P0_DIR / "P0_SENTINEL_ENVELOPE.json").is_file()
    and (ACTIVATIONS / "e3_p90__L0" / "extraction_inventory.json").is_file()
)

pytestmark = pytest.mark.skipif(
    not _EVIDENCE_PRESENT,
    reason="the banked A4/A5 evidence A6 freezes is not present in this working tree",
)


def _kwargs(**overrides: Any) -> dict[str, Any]:
    """The producer's real input set, with individual paths overridable."""
    base: dict[str, Any] = {
        "source_closure": source_closure(),
        "aprime_port_receipt_path": DOCS / "a1_receipts" / "aprime_port_receipt.json",
        "fir_recovery_receipt_path": (
            DOCS / "a1_receipts" / "fir_kernel_recovery_receipt.json"
        ),
        "capture_host_a3_path": (
            DOCS / "receipts" / "environment_receipt_wsl2_capture_host.json"
        ),
        "extraction_host_a3_path": EXTRACTION_A3,
        "production_manifest_path": DOCS / "cohort" / "production_identity_manifest.jsonl",
        "production_manifest_sha256_path": (
            DOCS / "cohort" / "production_identity_manifest.sha256"
        ),
        "pilot_manifest_path": DOCS / "cohort" / "pilot_identity_manifest.jsonl",
        "folds_path": DOCS / "cohort" / "folds.json",
        "priority_order_path": DOCS / "cohort" / "identity_priority_order.json",
        "p0_selection_receipt_path": P0_DIR / "P0_SELECTION_RECEIPT.json",
        "p0_selected_ladder_path": P0_DIR / "P0_SELECTED_LADDER.json",
        "p0_sentinel_envelope_path": P0_DIR / "P0_SENTINEL_ENVELOPE.json",
        "static_validation_receipt_path": (
            DOCS / "receipts" / "static_validation_receipt.json"
        ),
        "implementation_completion_receipt_path": (
            DOCS / "a1_receipts" / "implementation_completion_receipt.json"
        ),
        "p1_pilot_receipt_path": P1_RECEIPT,
        "activations_root": ACTIVATIONS,
    }
    base.update(overrides)
    return base


@pytest.fixture(scope="module")
def package() -> dict[str, Any]:
    return build_p2_freeze_package(**_kwargs())


def _producer_env() -> dict[str, str]:
    """The parent environment with this repository's ``src`` on ``PYTHONPATH``.

    Inherited, not replaced. An env built from scratch drops what the child needs
    to run at all: on Windows ``SYSTEMROOT``/``WINDIR`` are required for CPython
    to initialise, and a POSIX ``PATH`` finds no ``git`` -- which the producer
    shells out to for the source closure. Overlaying one variable keeps the test
    portable and keeps the subprocess a faithful stand-in for how an operator
    actually invokes the producer.
    """
    env = os.environ.copy()
    src = str(REPOSITORY_ROOT / "src")
    inherited = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        src if not inherited else src + os.pathsep + inherited
    )
    return env


def _copy(path: Path, tmp_path: Path, name: str) -> Path:
    target = tmp_path / name
    shutil.copy2(path, target)
    return target


def _rewrite(path: Path, mutate) -> Path:
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------


def test_a6_freeze_passes_on_the_real_evidence(package: dict[str, Any]) -> None:
    assert package["P2_RESULT"] == "PASS"
    assert p2_freeze_passed(package)
    assert package["missing_bindings"] == []
    assert package["null_bindings"] == []
    assert package["unverified_bindings"] == []
    assert package["verification"]["unverified"] == []


def test_a6_emits_the_exact_frozen_schema(package: dict[str, Any]) -> None:
    assert package["schema_version"] == P2_FREEZE_SCHEMA_VERSION
    assert package["schema_version"] == "mineocclude-experiment-iii-p2-freeze-v1"
    assert package["stage"] == "A6"


def test_a6_binds_all_seven_authority_groups(package: dict[str, Any]) -> None:
    lifecycle = json.loads(
        (
            DOCS / "final_authorities" / "EXPERIMENT_III_LIFECYCLE.json"
        ).read_text(encoding="utf-8")
    )
    a6 = next(state for state in lifecycle["states"] if state["id"] == "A6")
    assert a6["expected_counts"]["binding_groups"] == 7
    assert list(BINDING_GROUPS) == list(a6["expected_counts"]["groups"])
    assert package["binding_group_count"] == 7
    for group in BINDING_GROUPS:
        assert package["bindings"][group], group


def test_a6_output_is_deterministic() -> None:
    first = build_p2_freeze_package(**_kwargs())
    second = build_p2_freeze_package(**_kwargs())
    assert first["package_sha256"] == second["package_sha256"]
    assert canonical_sha256(first) == canonical_sha256(second)


def test_a6_package_hash_is_the_canonical_hash_of_its_own_content(
    package: dict[str, Any],
) -> None:
    recomputed = canonical_sha256(
        {key: value for key, value in package.items() if key != "package_sha256"}
    )
    assert package["package_sha256"] == recomputed
    assert verify_p2_freeze_package(package)["passed"]


def test_a6_independent_verifier_agrees(package: dict[str, Any]) -> None:
    audit = verify_p2_freeze_package(package)
    assert audit["passed"]
    assert audit["findings"] == []
    assert audit["binding_group_count"] == 7


# --------------------------------------------------------------------------
# Frozen scientific values -- bound, not restated
# --------------------------------------------------------------------------


def test_a6_freezes_the_production_matrix_exactly(package: dict[str, Any]) -> None:
    cohort = package["bindings"]["COHORT"]
    operations = package["bindings"]["EXTRACTION_ANALYSIS_AND_OPERATIONS"]
    assert cohort["production_identity_count"] == 25
    assert len(cohort["identities"]) == 25
    assert cohort["left_to_right_count"] == 13
    assert cohort["right_to_left_count"] == 12
    assert cohort["target_rows_per_capture"] == 19
    assert operations["production_captures"] == 125
    assert operations["production_target_rows"] == 2375
    assert operations["production_forwards"] == 2375
    assert operations["production_serialized_npy_arrays"] == 750
    for identity in cohort["identities"]:
        assert len(identity["target_model_frame_indices"]) == 19
        assert len(identity["expected_causal_fir_target_world_x_blocks"]) == 19


def test_a6_freezes_the_p0_selected_ladder_without_reselecting(
    package: dict[str, Any],
) -> None:
    conditions = package["bindings"]["CONDITIONS_AND_EVIDENCE"]
    ladder = json.loads(
        (P0_DIR / "P0_SELECTED_LADDER.json").read_text(encoding="utf-8")
    )
    assert conditions["L0_material"] == "minecraft:air"
    assert conditions["L4_material"] == "minecraft:stone"
    for level in ("L1", "L2", "L3"):
        assert conditions[f"{level}_material"] == ladder[level]
        assert conditions["V_c"][level] == ladder["V_c"][level]
    assert conditions["p0_result"] == "P0_PASS"


def test_a6_freezes_the_model_and_vae_the_authority_names(
    package: dict[str, Any],
) -> None:
    environment = package["bindings"]["ENVIRONMENT"]
    extraction = machine_authority()["extraction"]
    assert environment["main_checkpoint_sha256"] == extraction["main_checkpoint_sha256"]
    assert environment["vae_sha256"] == extraction["vae_sha256"]
    assert environment["preprocessing_change_allowed"] is False


def test_a6_freezes_the_token_geometry_p1_actually_used(
    package: dict[str, Any],
) -> None:
    operations = package["bindings"]["EXTRACTION_ANALYSIS_AND_OPERATIONS"]
    assert operations["layers"] == [4, 10, 19]
    assert operations["sequence_length"] == 5552
    assert operations["expected_shape"] == [19, 336, 2048]
    assert operations["expected_dtype"] == "<f2"
    assert operations["expected_npy_bytes"] == 26148992
    slices = operations["temporal_slices"]
    assert [slices["PREVIOUS"]["python_start"], slices["PREVIOUS"]["python_stop_exclusive"]] == [4858, 5194]
    assert [slices["CURRENT"]["python_start"], slices["CURRENT"]["python_stop_exclusive"]] == [5205, 5541]


def test_a6_freezes_both_direction_fir_kernels(package: dict[str, Any]) -> None:
    measurement = package["bindings"]["MEASUREMENT"]
    assert set(measurement["fir_kernels"]) == {"LEFT_TO_RIGHT", "RIGHT_TO_LEFT"}
    for taps in measurement["fir_kernels"].values():
        assert len(taps) == 9
    assert measurement["target_extent_half_blocks"] == 0.8727621336620037
    assert measurement["extent_samples_per_axis"] == 5


def test_a6_freezes_the_apparatus_constants(package: dict[str, Any]) -> None:
    apparatus = package["bindings"]["APPARATUS"]
    assert apparatus["speed_blocks_per_second"] == 2.0
    assert apparatus["process_noise_q_blocks_squared_per_second"] == 0.05
    assert apparatus["dt_seconds"] == 0.05
    assert apparatus["frames_per_capture"] == 180
    assert apparatus["framebuffer"] == {"width": 640, "height": 360}


def test_a6_freezes_the_ridge_recipe(package: dict[str, Any]) -> None:
    operations = package["bindings"]["EXTRACTION_ANALYSIS_AND_OPERATIONS"]
    readout = machine_authority()["readout"]
    assert operations["alpha_grid"] == list(readout["alpha_grid"])
    assert operations["inner_rotations"] == readout["inner_rotations"]
    assert operations["outer_folds"] == readout["outer_folds"]
    assert operations["bootstrap_replicates"] == 10000


# --------------------------------------------------------------------------
# Fail-closed: missing, null, unverified, placeholder
# --------------------------------------------------------------------------


def test_a6_refuses_a_missing_mandatory_binding(tmp_path: Path) -> None:
    with pytest.raises(ExperimentIIIError) as caught:
        build_p2_freeze_package(
            **_kwargs(p0_sentinel_envelope_path=tmp_path / "absent.json")
        )
    assert caught.value.blocker == "P2_BINDING_INCOMPLETE"


def test_a6_refuses_a_binding_that_names_no_path() -> None:
    with pytest.raises(ExperimentIIIError) as caught:
        build_p2_freeze_package(**_kwargs(p0_selected_ladder_path=None))
    assert caught.value.blocker == "P2_BINDING_INCOMPLETE"


def test_a6_refuses_a_null_mandatory_binding(tmp_path: Path) -> None:
    ladder = _copy(P0_DIR / "P0_SELECTED_LADDER.json", tmp_path, "ladder.json")
    _rewrite(ladder, lambda d: d["V_c"].__setitem__("L2", None))
    with pytest.raises(ExperimentIIIError) as caught:
        build_p2_freeze_package(**_kwargs(p0_selected_ladder_path=ladder))
    assert caught.value.blocker == "P2_BINDING_INCOMPLETE"


def test_a6_refuses_a_placeholder_mandatory_binding(tmp_path: Path) -> None:
    ladder = _copy(P0_DIR / "P0_SELECTED_LADDER.json", tmp_path, "ladder.json")
    _rewrite(ladder, lambda d: d.__setitem__("L2", "TO_BE_DETERMINED"))
    with pytest.raises(ExperimentIIIError) as caught:
        build_p2_freeze_package(**_kwargs(p0_selected_ladder_path=ladder))
    # Either the cross-check against the selection receipt or the placeholder
    # walk refuses it; both are correct refusals, neither may pass.
    assert caught.value.blocker in {"P2_BINDING_INCOMPLETE", "P2_BINDING_MISMATCH"}


def test_a6_refuses_an_unverified_binding(tmp_path: Path) -> None:
    """A manifest whose sidecar digest no longer matches its bytes."""
    manifest = _copy(
        DOCS / "cohort" / "production_identity_manifest.jsonl", tmp_path, "m.jsonl"
    )
    sidecar = tmp_path / "m.sha256"
    sidecar.write_text(json.dumps({"m.jsonl": "0" * 64}), encoding="utf-8")
    with pytest.raises(ExperimentIIIError) as caught:
        build_p2_freeze_package(
            **_kwargs(
                production_manifest_path=manifest,
                production_manifest_sha256_path=sidecar,
            )
        )
    assert caught.value.blocker == "P2_BINDING_MISMATCH"


def test_a6_refuses_an_incorrect_model_binding(tmp_path: Path) -> None:
    a3 = _copy(EXTRACTION_A3, tmp_path, "a3.json")
    _rewrite(
        a3,
        lambda d: d["model_identity_checks"]["main_checkpoint"].__setitem__(
            "observed_sha256", "b" * 64
        ),
    )
    with pytest.raises(ExperimentIIIError) as caught:
        build_p2_freeze_package(**_kwargs(extraction_host_a3_path=a3))
    assert caught.value.blocker == "P2_BINDING_MISMATCH"


def test_a6_refuses_an_unverified_model_identity(tmp_path: Path) -> None:
    a3 = _copy(EXTRACTION_A3, tmp_path, "a3.json")
    _rewrite(a3, lambda d: d["model_identity_checks"].__setitem__("verified", False))
    with pytest.raises(ExperimentIIIError) as caught:
        build_p2_freeze_package(**_kwargs(extraction_host_a3_path=a3))
    assert caught.value.blocker == "P2_BINDING_MISMATCH"


def test_a6_refuses_an_incorrect_production_cohort(tmp_path: Path) -> None:
    manifest = _copy(
        DOCS / "cohort" / "production_identity_manifest.jsonl", tmp_path, "m.jsonl"
    )
    rows = [
        line
        for line in manifest.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ][:24]
    manifest.write_text("\n".join(rows) + "\n", encoding="utf-8")
    sidecar = tmp_path / "m.sha256"
    import hashlib

    sidecar.write_text(
        json.dumps(
            {"m.jsonl": hashlib.sha256(manifest.read_bytes()).hexdigest()}
        ),
        encoding="utf-8",
    )
    with pytest.raises(ExperimentIIIError) as caught:
        build_p2_freeze_package(
            **_kwargs(
                production_manifest_path=manifest,
                production_manifest_sha256_path=sidecar,
            )
        )
    assert caught.value.blocker == "P2_BINDING_MISMATCH"


def test_a6_refuses_a_short_target_row_list(tmp_path: Path) -> None:
    manifest = _copy(
        DOCS / "cohort" / "production_identity_manifest.jsonl", tmp_path, "m.jsonl"
    )
    rows = [
        json.loads(line)
        for line in manifest.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows[0]["target_model_frame_indices"] = rows[0]["target_model_frame_indices"][:18]
    manifest.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
    )
    import hashlib

    sidecar = tmp_path / "m.sha256"
    sidecar.write_text(
        json.dumps({"m.jsonl": hashlib.sha256(manifest.read_bytes()).hexdigest()}),
        encoding="utf-8",
    )
    with pytest.raises(ExperimentIIIError) as caught:
        build_p2_freeze_package(
            **_kwargs(
                production_manifest_path=manifest,
                production_manifest_sha256_path=sidecar,
            )
        )
    assert caught.value.blocker == "P2_BINDING_MISMATCH"


# --------------------------------------------------------------------------
# Prerequisites A0-A5
# --------------------------------------------------------------------------


def test_a6_refuses_when_a5_did_not_pass(tmp_path: Path) -> None:
    receipt = _copy(P1_RECEIPT, tmp_path, "p1.json")
    _rewrite(
        receipt,
        lambda d: (d.__setitem__("P1_RESULT", "FAIL"), d.__setitem__("P1_FULL_PASS", False)),
    )
    with pytest.raises(ExperimentIIIError) as caught:
        build_p2_freeze_package(**_kwargs(p1_pilot_receipt_path=receipt))
    assert caught.value.blocker == "P2_PREREQUISITE_NOT_PASSED"


def test_a6_refuses_a_p1_receipt_with_failed_items(tmp_path: Path) -> None:
    receipt = _copy(P1_RECEIPT, tmp_path, "p1.json")
    _rewrite(receipt, lambda d: d.__setitem__("failed_items", ["forward_ledger_complete"]))
    with pytest.raises(ExperimentIIIError) as caught:
        build_p2_freeze_package(**_kwargs(p1_pilot_receipt_path=receipt))
    assert caught.value.blocker == "P2_PREREQUISITE_NOT_PASSED"


def test_a6_refuses_when_a2_did_not_pass(tmp_path: Path) -> None:
    static = _copy(DOCS / "receipts" / "static_validation_receipt.json", tmp_path, "s.json")
    _rewrite(static, lambda d: d.__setitem__("passed", False))
    with pytest.raises(ExperimentIIIError) as caught:
        build_p2_freeze_package(**_kwargs(static_validation_receipt_path=static))
    assert caught.value.blocker == "P2_PREREQUISITE_NOT_PASSED"


def test_a6_refuses_when_a4_did_not_pass(tmp_path: Path) -> None:
    receipt = _copy(P0_DIR / "P0_SELECTION_RECEIPT.json", tmp_path, "p0.json")
    _rewrite(receipt, lambda d: d.__setitem__("P0_RESULT", "P0_FAIL"))
    with pytest.raises(ExperimentIIIError) as caught:
        build_p2_freeze_package(**_kwargs(p0_selection_receipt_path=receipt))
    assert caught.value.blocker == "P2_PREREQUISITE_NOT_PASSED"


def test_a6_refuses_an_a3_that_does_not_authorize_a5_extraction(tmp_path: Path) -> None:
    a3 = _copy(EXTRACTION_A3, tmp_path, "a3.json")
    _rewrite(a3, lambda d: d.__setitem__("authorized_stages", ["A9", "A10"]))
    with pytest.raises(ExperimentIIIError) as caught:
        build_p2_freeze_package(**_kwargs(extraction_host_a3_path=a3))
    assert caught.value.blocker == "P2_PREREQUISITE_NOT_PASSED"


def test_a6_refuses_a_failed_capture_host_a3(tmp_path: Path) -> None:
    a3 = _copy(
        DOCS / "receipts" / "environment_receipt_wsl2_capture_host.json", tmp_path, "c.json"
    )
    _rewrite(a3, lambda d: d.__setitem__("passed", False))
    with pytest.raises(ExperimentIIIError) as caught:
        build_p2_freeze_package(**_kwargs(capture_host_a3_path=a3))
    assert caught.value.blocker == "P2_PREREQUISITE_NOT_PASSED"


# --------------------------------------------------------------------------
# The committed producer, end to end
# --------------------------------------------------------------------------


@pytest.fixture
def guarded_out(request) -> Path:
    """An output directory inside the Experiment III namespace.

    ``write_json_atomic`` refuses any write outside it (
    ``PROVENANCE_NAMESPACE_VIOLATION``), which is exactly the protection that
    stops a stray run from scattering scientific artifacts, so the producer
    cannot be driven at a bare ``tmp_path``.
    """
    out = REPOSITORY_ROOT / "data" / "experiment_iii" / f"_p2_test_{id(request)}"
    yield out
    shutil.rmtree(out, ignore_errors=True)


def test_committed_producer_writes_both_artifacts_and_authorizes(
    guarded_out: Path,
) -> None:
    """The authority-named entrypoint, run as a process, exactly as A6 names it.

    ``EXPECTED_ARTIFACT_INVENTORY.json`` names *two* A6 outputs; a producer that
    wrote only the package would leave A6 short of its expected outputs.
    """
    out = guarded_out
    result = subprocess.run(
        [
            sys.executable,
            str(PRODUCER),
            "--extraction-host-a3",
            str(EXTRACTION_A3),
            "--out",
            str(out),
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        env=_producer_env(),
    )
    assert result.returncode == 0, result.stderr
    package_path = out / "P2_FREEZE_PACKAGE.json"
    hash_path = out / "P2_FREEZE_PACKAGE.sha256"
    assert package_path.is_file()
    assert hash_path.is_file()

    package = json.loads(package_path.read_text(encoding="utf-8"))
    assert package["P2_RESULT"] == "PASS"
    assert package["schema_version"] == P2_FREEZE_SCHEMA_VERSION
    assert hash_path.read_text(encoding="utf-8").split()[0] == package["package_sha256"]

    # Authority 6/A6: only on this exit may these be emitted.
    assert package["PRODUCTION_AUTHORIZED"] is True
    assert package["MODEL_INFERENCE_AUTHORIZED"] is True
    assert package["next_authorized_state"] == "A7"
    assert "PRODUCTION_AUTHORIZED=true" in result.stdout
    assert "MODEL_INFERENCE_AUTHORIZED=true" in result.stdout


def test_committed_producer_emits_no_authorization_on_a_failed_freeze(
    tmp_path: Path, guarded_out: Path
) -> None:
    """A refused freeze writes nothing at all -- in particular no authorization.

    This is the failure mode A6 exists to prevent: a half-built package that
    still reads as permission to start production.
    """
    out = guarded_out
    broken = tmp_path / "p1.json"
    shutil.copy2(P1_RECEIPT, broken)
    _rewrite(broken, lambda d: d.__setitem__("P1_FULL_PASS", False))
    _rewrite(broken, lambda d: d.__setitem__("P1_RESULT", "FAIL"))

    result = subprocess.run(
        [
            sys.executable,
            str(PRODUCER),
            "--extraction-host-a3",
            str(EXTRACTION_A3),
            "--p1-pilot-receipt",
            str(broken),
            "--out",
            str(out),
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        env=_producer_env(),
    )
    assert result.returncode == 1
    assert "BLOCKER_CODE=P2_PREREQUISITE_NOT_PASSED" in result.stderr
    assert "P2_RESULT=FAIL" in result.stderr
    assert not (out / "P2_FREEZE_PACKAGE.json").exists()
    assert not (out / "P2_FREEZE_PACKAGE.sha256").exists()
    assert "PRODUCTION_AUTHORIZED=true" not in result.stdout
    assert "MODEL_INFERENCE_AUTHORIZED=true" not in result.stdout


def test_committed_producer_is_the_entrypoint_the_authority_names() -> None:
    lifecycle = json.loads(
        (
            DOCS / "final_authorities" / "EXPERIMENT_III_LIFECYCLE.json"
        ).read_text(encoding="utf-8")
    )
    a6 = next(state for state in lifecycle["states"] if state["id"] == "A6")
    named = a6["source_files_entrypoints"]
    assert named == ["scripts/experiment_iii/build_p2_freeze.py"]
    assert (REPOSITORY_ROOT / named[0]).is_file()

    inventory = json.loads(
        (
            DOCS / "final_authorities" / "EXPECTED_ARTIFACT_INVENTORY.json"
        ).read_text(encoding="utf-8")
    )
    rows = inventory["artifacts"] if isinstance(inventory, dict) else inventory
    freeze_rows = [
        row
        for row in rows
        if row.get("stage") == "A6"
        and "P2_FREEZE_PACKAGE" in row.get("path_or_pattern", "")
    ]
    # The package and its hash. A6 also lists an OPERATOR-produced deadline
    # decision receipt, which this producer neither owns nor writes.
    assert len(freeze_rows) == 2, [row["path_or_pattern"] for row in freeze_rows]
    for row in freeze_rows:
        assert row["producer"] == "scripts/experiment_iii/build_p2_freeze.py"
        assert (REPOSITORY_ROOT / row["producer"]).is_file()
        assert row["required_before_next_stage"] is True
        assert row["missing_blocker"] == "P2_BINDING_INCOMPLETE"


def test_a6_lifecycle_exit_opens_both_gates_and_only_here() -> None:
    lifecycle = json.loads(
        (
            DOCS / "final_authorities" / "EXPERIMENT_III_LIFECYCLE.json"
        ).read_text(encoding="utf-8")
    )
    gates = lifecycle["gate_opening_states"]
    assert gates["PRODUCTION_AUTHORIZED"] == "A6_EXIT_ONLY"
    assert gates["MODEL_INFERENCE_AUTHORIZED"] == "A6_EXIT_ONLY"
    a6 = next(state for state in lifecycle["states"] if state["id"] == "A6")
    assert a6["next_authorized_state"] == "A7"


def test_a6_does_not_read_authorization_from_p0(package: dict[str, Any]) -> None:
    """A4's ladder carries a historical ``PRODUCTION_AUTHORIZED`` field. A6 must
    emit its own on its own exit, never inherit A4's."""
    ladder = json.loads(
        (P0_DIR / "P0_SELECTED_LADDER.json").read_text(encoding="utf-8")
    )
    assert "PRODUCTION_AUTHORIZED" in ladder  # the historical field exists
    conditions = package["bindings"]["CONDITIONS_AND_EVIDENCE"]
    assert "PRODUCTION_AUTHORIZED" not in conditions
    assert package["PRODUCTION_AUTHORIZED"] is True
    assert package["prerequisites"]["A4_p0_visibility_calibration"] is True
