"""Coverage for the two modules that complete the A1/A3 execution seam.

``placements.py`` supplies the nine P0 placement coordinates authority 7.2
delegates to A1, and ``host_preflight.py`` is the A3 entrypoint's engine. Both
are load-bearing before any frame is captured, so both are tested here rather
than discovered at A4.
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
from mineocclude.experiment_iii.placements import (
    PLACEMENT_COUNT,
    corridor_interval,
    placement_coordinates,
    placement_manifest,
    sentinel_placement_indices,
)
from mineocclude.experiment_iii.storage_preflight import GIB

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FABRIC_PROJECT = REPOSITORY_ROOT / "fabric" / "mineocclude-mod"


# --------------------------------------------------------------------------
# P0 placements
# --------------------------------------------------------------------------


def test_placement_count_is_nine() -> None:
    assert PLACEMENT_COUNT == 9
    assert len(placement_coordinates()) == 9


def test_corridor_is_the_frozen_verified_occluded_interval() -> None:
    """The corridor is read from the authority, never restated here."""
    low, high = corridor_interval()
    frozen = machine_authority()["visibility_semantics"][
        "verified_counterfactual_fully_occluded_lane_interval_blocks"
    ]
    assert [low, high] == [float(frozen[0]), float(frozen[1])]


def test_placements_span_the_corridor_inclusively_and_uniformly() -> None:
    low, high = corridor_interval()
    xs = [p["lane_x"] for p in placement_coordinates()]
    assert xs[0] == pytest.approx(low)
    assert xs[-1] == pytest.approx(high)
    steps = [b - a for a, b in zip(xs, xs[1:])]
    assert all(step == pytest.approx(steps[0]) for step in steps)
    assert steps[0] == pytest.approx((high - low) / 8)


def test_every_placement_lies_inside_the_frozen_corridor() -> None:
    low, high = corridor_interval()
    for placement in placement_coordinates():
        assert low - 1e-9 <= placement["lane_x"] <= high + 1e-9


def test_placements_stay_on_the_frozen_sheep_lane() -> None:
    lane = machine_authority()["apparatus"]["sheep_lane"]
    for placement in placement_coordinates():
        assert placement["lane_y"] == float(lane["y"])
        assert placement["lane_z"] == float(lane["z"])


def test_centre_placement_is_the_lane_centre() -> None:
    """A structural check on the construction, not a restated constant."""
    centre = placement_coordinates()[PLACEMENT_COUNT // 2]["lane_x"]
    low, high = corridor_interval()
    assert centre == pytest.approx((low + high) / 2)


def test_three_sentinel_placements_bracket_the_corridor() -> None:
    indices = sentinel_placement_indices()
    assert len(indices) == machine_authority()["p0_rve"]["sentinel_placements"]
    assert indices == (0, 4, 8)


def test_placement_manifest_is_deterministic_and_hash_bound() -> None:
    first = placement_manifest()
    second = placement_manifest()
    assert first["placements_sha256"] == second["placements_sha256"]
    assert first == second
    assert first["outcome_blind"] is True
    assert first["computed_not_hard_coded"] is True


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
    assert receipt["authorized_stages"] == list(CAPTURE_HOST_STAGES)
    assert "A9" not in receipt["authorized_stages"]
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
