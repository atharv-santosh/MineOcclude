"""Coverage for the A3 host preflight engine.

``host_preflight.py`` is the A3 entrypoint's engine and is load-bearing before
any frame is captured, so it is tested here rather than discovered at A4.

The P0 placement coverage that once lived alongside this moved to
``test_amendment_3_p0_bindings.py`` when Authority Amendment 3 replaced the
implementation-side corridor derivation with the frozen Phase 0 positions.
"""

from __future__ import annotations

import platform
from pathlib import Path

import pytest

from mineocclude.experiment_iii import host_preflight
from mineocclude.experiment_iii.authority import machine_authority, sha256_file
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.host_preflight import (
    CAPTURE_HOST_STAGES,
    HostRole,
    device_identity,
    durable_round_trip,
    environment_receipt,
    resolve_host_pools,
    rng_stream_fixture,
    runtime_pins,
)
from mineocclude.experiment_iii.capture_runtime import RuntimeConfig
from mineocclude.experiment_iii.storage_preflight import GIB

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FABRIC_PROJECT = REPOSITORY_ROOT / "fabric" / "mineocclude-mod"


# --------------------------------------------------------------------------
# A3 host preflight
# --------------------------------------------------------------------------


def test_device_identity_reports_bytes_not_decimal_gb(tmp_path: Path) -> None:
    entry = device_identity(tmp_path)
    assert entry["free_bytes"] > 0
    assert entry["free_gib"] == pytest.approx(entry["free_bytes"] / GIB)


def test_resolve_host_pools_requires_every_gated_pool(tmp_path: Path) -> None:
    with pytest.raises(ExperimentIIIError) as error:
        resolve_host_pools({"POOL_WORKING": tmp_path})
    assert error.value.blocker == "STORAGE_INSUFFICIENT"


def test_pools_on_one_filesystem_resolve_to_one_device(tmp_path: Path) -> None:
    """Two logical categories on one filesystem are one physical pool."""
    pools = resolve_host_pools(
        {
            "POOL_WORKING": tmp_path,
            "POOL_DURABLE": tmp_path / "durable",
            "POOL_SCRATCH": tmp_path / "scratch",
        }
    )
    device_ids = {entry["device_id"] for entry in pools.values()}
    assert len(device_ids) == 1


def test_durable_round_trip_verifies_readback(tmp_path: Path) -> None:
    receipt = durable_round_trip(tmp_path)
    assert receipt["verified"] is True
    assert receipt["written_sha256"] == receipt["readback_sha256"]


def test_durable_round_trip_refuses_an_unwritable_store(tmp_path: Path) -> None:
    blocker = tmp_path / "not_a_directory"
    blocker.write_text("", encoding="utf-8")
    with pytest.raises(ExperimentIIIError) as error:
        durable_round_trip(blocker / "child")
    assert error.value.blocker == "DURABILITY_STORE_UNREACHABLE"


def test_runtime_pins_match_the_frozen_apparatus() -> None:
    pins = runtime_pins(FABRIC_PROJECT)
    assert pins["pins_match"] is True
    assert (pins["framebuffer_width"], pins["framebuffer_height"]) == (640, 360)
    apparatus = machine_authority()["apparatus"]
    assert pins["declared_pins"]["minecraft_version"] == apparatus["minecraft_version"]
    assert pins["declared_pins"]["yarn_mappings"] == apparatus["yarn_mappings"]


def test_rng_stream_fixture_is_deterministic() -> None:
    assert rng_stream_fixture()["seeds"] == rng_stream_fixture()["seeds"]


def _unqualified_runtime(tmp_path: Path) -> RuntimeConfig:
    return RuntimeConfig.from_mapping(
        {
            "runtime_root": str(tmp_path),
            "java_executable": str(tmp_path / "java"),
            "output_root": str(tmp_path / "out"),
            "display_strategy": "NATIVE",
            "mesa_software_rendering": False,
        }
    )


def test_an_unqualified_renderer_refuses_the_capture_receipt(tmp_path: Path) -> None:
    """Authority 7.10f / A3: a display EXISTING is not permission to capture.

    Without this, a receipt could authorize A4/A5/A7 on an interactive
    compositor whose output no capture receipt can vouch for.
    """
    with pytest.raises(ExperimentIIIError) as error:
        environment_receipt(
            host_role=HostRole.LOCAL_CAPTURE_HOST,
            pool_paths={
                "POOL_WORKING": REPOSITORY_ROOT,
                "POOL_DURABLE": tmp_path,
                "POOL_SCRATCH": tmp_path,
            },
            durable_root=tmp_path,
            project=FABRIC_PROJECT,
            runtime_config=_unqualified_runtime(tmp_path),
        )
    assert error.value.blocker == "ENV_DISPLAY_UNAVAILABLE"


def test_without_a_runtime_config_no_capture_stage_is_authorized(
    tmp_path: Path,
) -> None:
    """Renderer qualification unestablished authorizes nothing, not everything."""
    receipt = environment_receipt(
        host_role=HostRole.LOCAL_CAPTURE_HOST,
        pool_paths={
            "POOL_WORKING": REPOSITORY_ROOT,
            "POOL_DURABLE": tmp_path,
            "POOL_SCRATCH": tmp_path,
        },
        durable_root=tmp_path,
        project=FABRIC_PROJECT,
    )
    assert receipt["renderer_qualification"]["status"] == "NOT_ESTABLISHED"
    assert receipt["authorized_stages"] == []
    assert receipt["authorizes_capture_stages"] is False


def test_capture_host_receipt_never_authorizes_extraction(tmp_path: Path) -> None:
    """The defect this scoping exists to prevent: a capture-only host that
    silently authorizes A9 because it 'passed' checks it never ran."""
    receipt = environment_receipt(
        host_role=HostRole.LOCAL_CAPTURE_HOST,
        pool_paths={
            "POOL_WORKING": REPOSITORY_ROOT,
            "POOL_DURABLE": tmp_path,
            "POOL_SCRATCH": tmp_path,
        },
        durable_root=tmp_path,
        project=FABRIC_PROJECT,
    )
    assert "A9" not in receipt["authorized_stages"]
    assert set(receipt["authorized_stages"]) <= set(CAPTURE_HOST_STAGES)
    # A5_EXTRACTION joined this list when A5's extraction half got a stage token
    # of its own; a capture host authorizes none of the three.
    assert receipt["not_authorized_stages"] == ["A5_EXTRACTION", "A9", "A10"]
    assert receipt["model_identity_checks"]["status"] == "NOT_APPLICABLE"
    assert receipt["model_identity_checks"]["verified"] is False
    assert receipt["resource_policy"]["MINEWORLD_MODEL_LOADED"] is False
    assert receipt["passed"] is True


def test_extraction_host_preflight_refuses_to_fabricate_weight_hashes(
    tmp_path: Path,
) -> None:
    """A GPU-host receipt may only be produced on a host holding the weights."""
    with pytest.raises(ExperimentIIIError) as error:
        environment_receipt(
            host_role=HostRole.GPU_EXTRACTION_HOST,
            pool_paths={
                "POOL_WORKING": REPOSITORY_ROOT,
                "POOL_DURABLE": tmp_path,
                "POOL_SCRATCH": tmp_path,
            },
            durable_root=tmp_path,
            project=FABRIC_PROJECT,
        )
    assert error.value.blocker == "ENV_CHECKPOINT_HASH_MISMATCH"


def test_unknown_host_role_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ExperimentIIIError) as error:
        environment_receipt(
            host_role="LAPTOP",
            pool_paths={
                "POOL_WORKING": REPOSITORY_ROOT,
                "POOL_DURABLE": tmp_path,
                "POOL_SCRATCH": tmp_path,
            },
            durable_root=tmp_path,
            project=FABRIC_PROJECT,
        )
    assert error.value.blocker == "PROVENANCE_BINDING_MISSING"


# --------------------------------------------------------------------------
# Blocker A -- display and renderer scoping per host role
# --------------------------------------------------------------------------


def test_the_x11_display_probe_is_falsifiable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A probe that cannot answer ``False`` records nothing."""
    monkeypatch.setattr(host_preflight.platform, "system", lambda: "Linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    assert host_preflight._display_probe()["available"] is False
    monkeypatch.setenv("DISPLAY", ":99")
    assert host_preflight._display_probe()["available"] is True


@pytest.mark.skipif(
    platform.system() != "Windows", reason="the Windows branch needs user32"
)
def test_the_windows_display_probe_is_falsifiable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Windows branch once ended in ``or True`` and could not fail.

    ``bool(os.environ.get("SESSIONNAME")) or True`` is the constant ``True``:
    ``ENV_DISPLAY_UNAVAILABLE`` became unreachable on Windows and a host with no
    desktop passed A3 on the strength of a tautology. The branch now reads the
    primary screen extent, so a session that reports none is refused.
    """
    import ctypes

    class _NoDesktop:
        @staticmethod
        def GetSystemMetrics(index: int) -> int:  # noqa: N802 - Win32 name
            return 0

    real = ctypes.windll.user32
    monkeypatch.setattr(ctypes.windll, "user32", _NoDesktop(), raising=False)
    try:
        probe = host_preflight._display_probe()
    finally:
        monkeypatch.setattr(ctypes.windll, "user32", real, raising=False)
    assert probe["mechanism"] == "WINDOWS_SYSTEM_METRICS"
    assert probe["primary_screen_width"] == 0
    assert probe["available"] is False

    # And the real host, which does have a desktop, answers the other way.
    assert host_preflight._display_probe()["available"] is True


def test_a_capture_host_without_a_display_is_still_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The capture-host display requirement is unchanged by the role scoping."""
    monkeypatch.setattr(host_preflight.platform, "system", lambda: "Linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    with pytest.raises(ExperimentIIIError) as error:
        environment_receipt(
            host_role=HostRole.LOCAL_CAPTURE_HOST,
            pool_paths={
                "POOL_WORKING": REPOSITORY_ROOT,
                "POOL_DURABLE": tmp_path,
                "POOL_SCRATCH": tmp_path,
            },
            durable_root=tmp_path,
            project=FABRIC_PROJECT,
        )
    assert error.value.blocker == "ENV_DISPLAY_UNAVAILABLE"


def test_the_extraction_host_display_check_is_not_applicable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A headless GPU box must not fail a check the same receipt calls N/A.

    This is the defect the role scoping exists to fix: the display gate ran on
    both roles, so a Linux extraction host with no ``DISPLAY`` was refused
    ``ENV_DISPLAY_UNAVAILABLE`` on its way to a receipt that would have recorded
    the renderer as ``NOT_APPLICABLE`` because "this host does not capture".
    """
    monkeypatch.setattr(host_preflight.platform, "system", lambda: "Linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    receipt = _extraction_receipt(tmp_path, monkeypatch)
    assert receipt["display"]["status"] == "NOT_APPLICABLE"
    assert receipt["renderer_qualification"]["status"] == "NOT_APPLICABLE"
    assert receipt["passed"] is True


# --------------------------------------------------------------------------
# Blocker B -- the extraction host hashes the weights it will load
# --------------------------------------------------------------------------


def _weights(tmp_path: Path) -> tuple[Path, Path]:
    model = tmp_path / "weights" / "model.pt"
    vae = tmp_path / "weights" / "vae.pt"
    model.parent.mkdir(parents=True, exist_ok=True)
    model.write_bytes(b"main-checkpoint-bytes")
    vae.write_bytes(b"vae-checkpoint-bytes")
    return model, vae


def _authority_expecting(model: Path, vae: Path):
    """A machine authority whose frozen digests are these files real digests.

    The comparison under test is "recompute the digest of the bytes on disk and
    demand an exact match". Pointing the expectation at a fixture rather than
    the unobtainable production weights tests exactly that, and
    ``test_the_expected_digests_are_the_frozen_authority_values`` separately
    pins the real values.
    """
    real = host_preflight.machine_authority()
    patched = dict(real)
    patched["extraction"] = {
        **real["extraction"],
        "main_checkpoint_sha256": sha256_file(model),
        "vae_sha256": sha256_file(vae),
    }
    return lambda: patched


def test_the_expected_digests_are_the_frozen_authority_values() -> None:
    extraction = machine_authority()["extraction"]
    assert extraction["main_checkpoint_sha256"] == (
        "a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5"
    )
    assert extraction["vae_sha256"] == (
        "370d06be427e034476b6b95ba0080a4b48266e876c4776a757b944b87b87d9ab"
    )


def test_a_matching_checkpoint_and_vae_verify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model, vae = _weights(tmp_path)
    monkeypatch.setattr(
        host_preflight, "machine_authority", _authority_expecting(model, vae)
    )
    observed = host_preflight.verify_model_identity(model, vae)
    assert observed["main_checkpoint"]["matches"] is True
    assert observed["main_checkpoint"]["observed_sha256"] == sha256_file(model)
    assert observed["vae_checkpoint"]["observed_sha256"] == sha256_file(vae)
    assert observed["main_checkpoint"]["path"].endswith("model.pt")


def test_a_mismatched_checkpoint_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model, vae = _weights(tmp_path)
    monkeypatch.setattr(
        host_preflight, "machine_authority", _authority_expecting(model, vae)
    )
    model.write_bytes(b"a different model entirely")
    with pytest.raises(ExperimentIIIError) as error:
        host_preflight.verify_model_identity(model, vae)
    assert error.value.blocker == "ENV_CHECKPOINT_HASH_MISMATCH"


def test_a_mismatched_vae_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model, vae = _weights(tmp_path)
    monkeypatch.setattr(
        host_preflight, "machine_authority", _authority_expecting(model, vae)
    )
    vae.write_bytes(b"a different vae entirely")
    with pytest.raises(ExperimentIIIError) as error:
        host_preflight.verify_model_identity(model, vae)
    assert error.value.blocker == "ENV_VAE_HASH_MISMATCH"


def test_a_missing_weight_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ExperimentIIIError) as error:
        host_preflight.verify_model_identity(
            tmp_path / "absent.pt", tmp_path / "also_absent.pt"
        )
    assert error.value.blocker == "ENV_CHECKPOINT_HASH_MISMATCH"
    assert "ordinary file" in error.value.message


def test_a_directory_is_not_a_checkpoint(tmp_path: Path) -> None:
    directory = tmp_path / "checkpoint_dir"
    directory.mkdir()
    with pytest.raises(ExperimentIIIError) as error:
        host_preflight.verify_model_identity(directory, directory)
    assert error.value.blocker == "ENV_CHECKPOINT_HASH_MISMATCH"


def test_an_extraction_host_naming_no_weights_is_still_refused() -> None:
    """Repairing A3 must not turn it into a check that passes on nothing."""
    with pytest.raises(ExperimentIIIError) as error:
        host_preflight.verify_model_identity(None, None)
    assert error.value.blocker == "ENV_CHECKPOINT_HASH_MISMATCH"
    assert "never read" in error.value.message


# --------------------------------------------------------------------------
# The GPU gate
# --------------------------------------------------------------------------


def test_the_cuda_probe_reports_this_host_honestly() -> None:
    """No torch and no CUDA here, and the probe says so rather than assuming."""
    probe = host_preflight.cuda_probe()
    assert "available" in probe
    if not probe["available"]:
        assert probe["reason"]


def test_an_extraction_host_without_cuda_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model, vae = _weights(tmp_path)
    monkeypatch.setattr(
        host_preflight, "machine_authority", _authority_expecting(model, vae)
    )
    with pytest.raises(ExperimentIIIError) as error:
        environment_receipt(
            host_role=HostRole.GPU_EXTRACTION_HOST,
            pool_paths={
                "POOL_WORKING": REPOSITORY_ROOT,
                "POOL_DURABLE": tmp_path,
                "POOL_SCRATCH": tmp_path,
            },
            durable_root=tmp_path,
            project=FABRIC_PROJECT,
            main_checkpoint_path=model,
            vae_checkpoint_path=vae,
            gpu_probe=lambda: {"available": False, "reason": "no CUDA device"},
        )
    assert error.value.blocker == "ENV_GPU_UNAVAILABLE"


# --------------------------------------------------------------------------
# Blocker D -- the A5_EXTRACTION stage token
# --------------------------------------------------------------------------


def _extraction_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    model, vae = _weights(tmp_path)
    monkeypatch.setattr(
        host_preflight, "machine_authority", _authority_expecting(model, vae)
    )
    return environment_receipt(
        host_role=HostRole.GPU_EXTRACTION_HOST,
        pool_paths={
            "POOL_WORKING": REPOSITORY_ROOT,
            "POOL_DURABLE": tmp_path,
            "POOL_SCRATCH": tmp_path,
        },
        durable_root=tmp_path,
        project=FABRIC_PROJECT,
        main_checkpoint_path=model,
        vae_checkpoint_path=vae,
        gpu_probe=lambda: {
            "available": True,
            "device_name": "Test CUDA Device",
            "capability": "8.0",
            "total_memory_bytes": 42 * 1024**3,
        },
    )


def test_a_qualified_extraction_host_authorizes_a5_extraction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without this token A5 own entry condition is unsatisfiable.

    A5 requires ``A3 == PASS on capture and extraction hosts``, and the
    extraction host had no stage to authorize: the tuple was ``("A9", "A10")``,
    both of which are production and post-P2.
    """
    receipt = _extraction_receipt(tmp_path, monkeypatch)
    assert host_preflight.A5_EXTRACTION_STAGE == "A5_EXTRACTION"
    assert "A5_EXTRACTION" in receipt["authorized_stages"]
    assert receipt["model_identity_checks"]["verified"] is True
    assert receipt["gpu"]["status"] == "EVALUATED"
    assert receipt["passed"] is True


def test_a5_extraction_is_not_the_same_stage_as_a9() -> None:
    assert "A5_EXTRACTION" in host_preflight.EXTRACTION_HOST_STAGES
    assert "A9" in host_preflight.EXTRACTION_HOST_STAGES
    assert "A5_EXTRACTION" not in CAPTURE_HOST_STAGES
    assert "A5_CAPTURE" in CAPTURE_HOST_STAGES


def test_a_capture_host_authorizes_no_extraction_stage(tmp_path: Path) -> None:
    receipt = environment_receipt(
        host_role=HostRole.LOCAL_CAPTURE_HOST,
        pool_paths={
            "POOL_WORKING": REPOSITORY_ROOT,
            "POOL_DURABLE": tmp_path,
            "POOL_SCRATCH": tmp_path,
        },
        durable_root=tmp_path,
        project=FABRIC_PROJECT,
    )
    assert "A5_EXTRACTION" not in receipt["authorized_stages"]
    assert receipt["not_authorized_stages"] == ["A5_EXTRACTION", "A9", "A10"]
    assert receipt["gpu"]["status"] == "NOT_APPLICABLE"
