"""The ``A3`` storage preflight (authority 13.2, 29.2, 29.5).

Three defects this module exists to prevent, all of them from the superseded
formulation ">= 60 GB durable free AND >= 40 GB scratch free":

* **Unit confusion.** Every threshold here is **GiB = 2^30 bytes**, frozen in
  exact bytes; free space is read as bytes and converted only for display.
  Decimal GB is forbidden by the authority.
* **Double counting.** Two logical pools that resolve to the **same device id**
  are one pool, and their free bytes are counted **once**. Pools are compared by
  device id, never by path string, and a gate that would double count fails
  ``STORAGE_POOL_DOUBLE_COUNTED``.
* **Gate incoherence.** The mandatory ``A3`` gate and the optional III-B launch
  gate must not contradict each other. A host that legitimately clears ``A3`` at
  exactly 64 GiB must still be able to pass the III-B launch gate; forcing it
  into a spurious ``CLEAN_SKIP`` is the specific failure ``B.13`` exists to
  prevent. The fix was to lower the **optional** gate to fit the structural
  headroom, never to raise the **mandatory** one.

Because III-B is prospectively authorized, ``A3`` always applies the
**combined-program** gate.
"""

from __future__ import annotations

from typing import Any, Mapping

from mineocclude.experiment_iii.authority import machine_authority
from mineocclude.experiment_iii.errors import ExperimentIIIError

__all__ = [
    "A3_COMBINED_NO_MIRROR_BYTES",
    "A3_COMBINED_WITH_MIRROR_BYTES",
    "A3_DISTINCT_DURABLE_POOL_BYTES",
    "DURABILITY_MODES",
    "GIB",
    "III_B_INCREMENTAL_EXPECTED_PEAK_GIB",
    "III_B_INCREMENTAL_LAUNCH_GATE_GIB",
    "MAX_III_A_STORAGE_SHARE_AT_B_GATE_GIB",
    "assert_gate_coherence",
    "resolve_pools",
    "storage_preflight",
]

GIB = 1 << 30

A3_COMBINED_WITH_MIRROR_BYTES = 64 * GIB
A3_COMBINED_NO_MIRROR_BYTES = 40 * GIB
A3_DISTINCT_DURABLE_POOL_BYTES = 28 * GIB

DURABILITY_MODES = (
    "LOCAL_MIRROR_SAME_POOL",
    "LOCAL_MIRROR_DISTINCT_POOL",
    "REMOTE_OBJECT_STORE",
)

A3_PASS_GIB = 64.0
MAX_III_A_STORAGE_SHARE_AT_B_GATE_GIB = 48.796
III_B_INCREMENTAL_LAUNCH_GATE_GIB = 15.0
III_B_INCREMENTAL_EXPECTED_PEAK_GIB = 10.508

_POOLS = ("POOL_WORKING", "POOL_DURABLE", "POOL_SCRATCH")


def resolve_pools(host: Mapping[str, Any]) -> dict[str, Any]:
    """Group the three logical pools by device id and count free bytes once.

    ``host`` gives, per pool, a ``device_id`` and ``free_bytes``. Pools sharing a
    device id form one physical pool; its free bytes are that device's, not the
    sum of the logical entries.
    """
    devices: dict[Any, dict[str, Any]] = {}
    for pool in _POOLS:
        entry = host.get(pool)
        if entry is None:
            continue
        device = entry["device_id"]
        free = int(entry["free_bytes"])
        record = devices.setdefault(
            device, {"device_id": device, "free_bytes": free, "logical_pools": []}
        )
        if record["free_bytes"] != free:
            raise ExperimentIIIError(
                "STORAGE_POOL_DOUBLE_COUNTED",
                f"device {device!r} reports two different free-byte values "
                f"({record['free_bytes']} and {free}); one device has one free size",
            )
        record["logical_pools"].append(pool)
    return {
        "physical_pools": list(devices.values()),
        "physical_pool_count": len(devices),
        "logical_pool_count": sum(1 for pool in _POOLS if host.get(pool) is not None),
        "pool_working_device_id": host["POOL_WORKING"]["device_id"],
        "scratch_is_a_distinct_pool": (
            host.get("POOL_SCRATCH") is not None
            and host["POOL_SCRATCH"]["device_id"] != host["POOL_WORKING"]["device_id"]
        ),
    }


def storage_preflight(
    host: Mapping[str, Any],
    *,
    durability_mode: str = "LOCAL_MIRROR_SAME_POOL",
    local_mirror_enabled: bool = True,
    iii_b_prospectively_authorized: bool = True,
) -> dict[str, Any]:
    """Apply the frozen ``A3`` gate. Fails closed; the threshold is never lowered."""
    if durability_mode not in DURABILITY_MODES:
        raise ExperimentIIIError(
            "STORAGE_INSUFFICIENT",
            f"{durability_mode!r} is not an admissible durability mode {DURABILITY_MODES}",
        )
    if "POOL_WORKING" not in host:
        raise ExperimentIIIError(
            "STORAGE_INSUFFICIENT", "A3 must resolve POOL_WORKING before it can gate"
        )
    pools = resolve_pools(host)

    # The double-count check: a gate that would count one device twice is
    # refused before any threshold comparison happens.
    if durability_mode == "LOCAL_MIRROR_DISTINCT_POOL":
        durable = host.get("POOL_DURABLE")
        if durable is None or durable["device_id"] == pools["pool_working_device_id"]:
            raise ExperimentIIIError(
                "STORAGE_POOL_DOUBLE_COUNTED",
                "LOCAL_MIRROR_DISTINCT_POOL was declared but POOL_DURABLE resolves "
                "to the POOL_WORKING device; counting one filesystem as two pools "
                "is forbidden",
            )

    threshold = (
        A3_COMBINED_WITH_MIRROR_BYTES
        if local_mirror_enabled
        else A3_COMBINED_NO_MIRROR_BYTES
    )
    gate_name = (
        "A3_COMBINED_PROGRAM_WITH_LOCAL_MIRROR"
        if local_mirror_enabled
        else "A3_COMBINED_PROGRAM_NO_LOCAL_MIRROR"
    )
    working_free = int(host["POOL_WORKING"]["free_bytes"])
    results = {gate_name: working_free >= threshold}

    durable_requirement: str
    round_trip_required = False
    if durability_mode == "REMOTE_OBJECT_STORE":
        # Remote storage has no meaningful LOCAL free-space bound; it must not be
        # treated as a local disk gate. Reachability and a hashed round trip
        # replace it.
        durable_requirement = "NO_LOCAL_FREE_SPACE_GATE"
        round_trip_required = True
        results["A3_REMOTE_OBJECT_STORE_HASHED_ROUND_TRIP"] = bool(
            host.get("remote_hashed_round_trip_verified")
        )
    elif durability_mode == "LOCAL_MIRROR_DISTINCT_POOL":
        durable_requirement = "A3_DISTINCT_DURABLE_POOL_IF_PRESENT"
        results[durable_requirement] = (
            int(host["POOL_DURABLE"]["free_bytes"]) >= A3_DISTINCT_DURABLE_POOL_BYTES
        )
    else:
        durable_requirement = "N/A_SAME_POOL_AS_POOL_WORKING"

    passed = all(results.values())
    receipt = {
        "schema_version": "mineocclude-experiment-iii-storage-preflight-v1",
        "unit_convention": "GIB_BINARY",
        "GiB_bytes": GIB,
        "free_space_read_as": "BYTES",
        "gate_applied": gate_name,
        "gate_threshold_bytes": threshold,
        "gate_threshold_gib": threshold / GIB,
        "uses_combined_program_gate": bool(iii_b_prospectively_authorized),
        "durability_mode": durability_mode,
        "local_mirror_enabled": bool(local_mirror_enabled),
        "durable_requirement": durable_requirement,
        "remote_hashed_round_trip_required": round_trip_required,
        "pool_working_device_id": pools["pool_working_device_id"],
        "pool_working_free_bytes": working_free,
        "scratch_is_a_distinct_pool": pools["scratch_is_a_distinct_pool"],
        "physical_pool_count": pools["physical_pool_count"],
        "logical_pool_count": pools["logical_pool_count"],
        "results": results,
        "passed": passed,
        "fails_closed": True,
        "threshold_lowered_to_proceed": False,
    }
    if not passed:
        raise ExperimentIIIError(
            "STORAGE_INSUFFICIENT",
            f"{gate_name} requires {threshold} bytes on POOL_WORKING; the host "
            f"reports {working_free}. The gate fails closed and is never lowered "
            f"to proceed. Receipt: {results}",
        )
    return receipt


def assert_gate_coherence(
    *,
    a3_pass_gib: float = A3_PASS_GIB,
    max_iii_a_share_gib: float = MAX_III_A_STORAGE_SHARE_AT_B_GATE_GIB,
    launch_gate_gib: float = III_B_INCREMENTAL_LAUNCH_GATE_GIB,
    incremental_peak_gib: float = III_B_INCREMENTAL_EXPECTED_PEAK_GIB,
) -> dict[str, Any]:
    """The two frozen invariants of authority 13.2 / ``B.13``.

    ``MAX_III_A_STORAGE_SHARE`` is **derived** -- whole-program mirrored peak
    minus the III-B incremental mirrored peak -- not asserted.
    """
    machine = machine_authority()["resources"]["storage"]
    whole_program_peak = machine["peak_derivation"]["peak_working_with_mirror_gib"]
    derived_share = whole_program_peak - incremental_peak_gib
    if abs(derived_share - max_iii_a_share_gib) > 1e-3:
        raise ExperimentIIIError(
            "STORAGE_INSUFFICIENT",
            f"MAX_III_A_STORAGE_SHARE must be derived as {whole_program_peak} - "
            f"{incremental_peak_gib} = {derived_share}, not asserted as "
            f"{max_iii_a_share_gib}",
        )
    headroom = a3_pass_gib - max_iii_a_share_gib
    if headroom < launch_gate_gib:
        raise ExperimentIIIError(
            "STORAGE_INSUFFICIENT",
            f"a host passing A3 at exactly {a3_pass_gib} GiB retains only "
            f"{headroom:.3f} GiB when the III-B launch gate fires, below the "
            f"{launch_gate_gib} GiB gate; that forces a spurious CLEAN_SKIP",
        )
    if launch_gate_gib <= incremental_peak_gib:
        raise ExperimentIIIError(
            "STORAGE_INSUFFICIENT",
            f"the III-B launch gate {launch_gate_gib} GiB must exceed the "
            f"incremental peak {incremental_peak_gib} GiB",
        )
    return {
        "A3_PASS_GIB": a3_pass_gib,
        "MAX_III_A_STORAGE_SHARE_AT_B_GATE_GIB": max_iii_a_share_gib,
        "MAX_III_A_STORAGE_SHARE_IS_DERIVED": True,
        "STRUCTURAL_HEADROOM_GIB": headroom,
        "III_B_INCREMENTAL_LAUNCH_GATE_GIB": launch_gate_gib,
        "III_B_INCREMENTAL_EXPECTED_PEAK_GIB": incremental_peak_gib,
        "MARGIN_GIB": launch_gate_gib - incremental_peak_gib,
        "holds": True,
        "second_invariant_holds": True,
        "units": "GIB_BINARY",
        "mandatory_a3_gate_raised_to_protect_optional_iii_b": False,
    }
