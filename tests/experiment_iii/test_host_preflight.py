"""Coverage for the A3 host preflight engine.

``host_preflight.py`` is the A3 entrypoint's engine and is load-bearing before
any frame is captured, so it is tested here rather than discovered at A4.

The P0 placement coverage that once lived alongside this moved to
``test_amendment_3_p0_bindings.py`` when Authority Amendment 3 replaced the
implementation-side corridor derivation with the frozen Phase 0 positions.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mineocclude.experiment_iii.authority import machine_authority
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
    assert receipt["not_authorized_stages"] == ["A9", "A10"]
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
