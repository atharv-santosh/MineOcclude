"""Deterministic, non-scientific memory-plan preflight (Person D Step 4.1).

The authorized production command (Person B authorization
``76e1d33788bcf1482b310d2b41a5db3d734d98a7``) was invoked exactly once
on the approved 15 GiB, zero-swap SageMaker host and was OOM-killed
(exit 137) before any baseline family executed. The confirmed root
cause: ``build_pixel_features_by_key`` (production_input_ingest.py)
decoded every one of the 1,695 admitted frames' 258,048 float32 pixel
values into a Python ``list[float]`` -- 437,391,360 individually boxed
``float`` objects (24+ bytes each, plus 8-byte list pointers), a
minimum of 13.035 GiB before ``raw_pixel`` ever reached
:func:`mineocclude.probes.ridge.fit_ridge_oof`. That representation is
fixed in ``production_input_ingest.py`` (compact float32 NumPy arrays,
never boxed Python floats).

This module exists for the *next* question the boxing fix does not
answer by itself: does the unchanged ridge-fitting pipeline
(``mineocclude.probes.ridge`` -- an estimator this repair must not
touch) fit in the host's memory once boxing is removed? That pipeline
is not free even with a compact source array:

* ``ridge._matrix`` upcasts every input to ``float64`` before any
  linear-algebra step (``np.asarray(values, dtype=np.float64)``) --
  double the compact array's size, and it coexists with the compact
  source for the whole ``fit_ridge_oof`` call (the caller,
  ``raw_pixel.fit_predict_raw_pixel``, still holds its own reference to
  the float32 feature list the whole time).
* Every NumPy fancy-index slice (``matrix[list(indices)]``) always
  copies, never views -- both the outer 5-fold and the inner 4-fold
  splits each produce a fresh, same-dtype copy of their training rows.
* ``StandardScaler.transform`` allocates one more same-shape copy
  (``(matrix - mean) / scale``) per fit.

:func:`estimate_raw_pixel_ridge_working_copy_bytes` models exactly
these allocations from reading that code directly -- a documented,
conservative approximation, not a live profiler (this module never
fits a baseline or reads real data). :func:`build_raw_pixel_memory_plan`
combines that estimate with best-effort host memory detection into a
pass/fail admission decision, enforced before ``raw_pixel`` ever calls
into the ridge estimator.

Nothing in this module computes a metric or reads a U4 artifact.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

BYTES_PER_GIB = 1024**3

#: The frame payloads' own on-disk dtype (frame_handoff_v0_2
#: .REQUIRED_PAYLOAD_DTYPE) -- the compact representation this repair
#: requires; never a Python-object-boxed list of ``float``.
COMPACT_FEATURE_ITEMSIZE_BYTES = 4
COMPACT_FEATURE_DTYPE_NAME = "float32"

#: mineocclude.probes.ridge._matrix always upcasts to float64 before any
#: linear-algebra step -- an unavoidable, unchanged property of the
#: existing ridge estimator this module plans around, never eliminates.
RIDGE_WORKING_DTYPE_ITEMSIZE_BYTES = 8

#: Documented, conservative allowance for the Python interpreter,
#: NumPy/BLAS internals, and this run's other (comparatively small)
#: already-resident state (contexts, oracle-target lookups, run_state).
#: Not zero, and not tuned to make any particular host pass.
FIXED_OVERHEAD_BYTES = int(0.5 * BYTES_PER_GIB)


class MemoryPlanError(ValueError):
    """Raised when a memory plan cannot be honestly computed from its inputs."""


@dataclass(frozen=True)
class MemoryPlan:
    feature_value_count: int
    source_dtype: str
    compact_payload_bytes: int
    expected_largest_resident_matrix_bytes: int
    expected_working_copy_bytes: int
    estimated_peak_bytes: int
    detected_host_physical_bytes: int | None
    detected_host_available_bytes: int | None
    admitted: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def estimated_peak_gib(self) -> float:
        return self.estimated_peak_bytes / BYTES_PER_GIB

    @property
    def compact_payload_gib(self) -> float:
        return self.compact_payload_bytes / BYTES_PER_GIB


def _detect_host_memory_windows() -> dict[str, int | None]:
    """Read physical/available memory from the Win32 memory-status API.

    POSIX ``sysconf`` does not exist on Windows, so without this branch
    every plan built on a Windows development machine fails closed with
    ``host_memory_undetected`` -- a portability defect, not a real
    memory shortage. ``GlobalMemoryStatusEx`` is the direct Win32
    equivalent and needs no third-party dependency. Returns ``None``
    values (never a guess) if the call is unavailable or fails.
    """

    try:
        import ctypes
        from ctypes import wintypes
    except (ImportError, ValueError):  # pragma: no cover - non-Windows
        return {"physical_bytes": None, "available_bytes": None}

    class _MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("dwLength", wintypes.DWORD),
            ("dwMemoryLoad", wintypes.DWORD),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = _MemoryStatusEx()
    status.dwLength = ctypes.sizeof(_MemoryStatusEx)
    try:
        ok = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    except (AttributeError, OSError):  # pragma: no cover - non-Windows
        return {"physical_bytes": None, "available_bytes": None}
    if not ok:  # pragma: no cover - API failure
        return {"physical_bytes": None, "available_bytes": None}

    physical = int(status.ullTotalPhys) or None
    available = int(status.ullAvailPhys) or None
    return {"physical_bytes": physical, "available_bytes": available}


def detect_host_memory() -> dict[str, int | None]:
    """Best-effort, dependency-free host memory detection.

    ``physical_bytes`` uses POSIX ``sysconf`` (portable across the
    Linux SageMaker target and any POSIX development machine) and falls
    back to the Win32 ``GlobalMemoryStatusEx`` API on Windows, where
    ``sysconf`` does not exist at all. ``available_bytes`` reads Linux's
    ``/proc/meminfo`` ``MemAvailable`` line when present, or Win32
    ``ullAvailPhys`` on Windows; ``None`` elsewhere -- this function
    never guesses at a value it cannot actually read, and the admission
    decision in :func:`build_raw_pixel_memory_plan` still fails closed
    on ``None``.
    """

    physical_bytes: int | None
    try:
        physical_bytes = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        physical_bytes = None

    available_bytes: int | None = None
    meminfo_path = Path("/proc/meminfo")
    if meminfo_path.exists():
        try:
            lines = meminfo_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        for line in lines:
            if line.startswith("MemAvailable:"):
                parts = line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    available_bytes = int(parts[1]) * 1024
                break

    if physical_bytes is None and sys.platform == "win32":
        windows = _detect_host_memory_windows()
        physical_bytes = windows["physical_bytes"]
        if available_bytes is None:
            available_bytes = windows["available_bytes"]

    return {"physical_bytes": physical_bytes, "available_bytes": available_bytes}


def estimate_raw_pixel_ridge_working_copy_bytes(
    *,
    row_count: int,
    feature_dim: int,
    outer_fold_row_counts: Sequence[int],
    inner_fold_count: int,
) -> dict[str, int]:
    """Model every large array the unchanged ridge pipeline allocates for raw_pixel.

    Derived directly from reading ``mineocclude.probes.ridge`` (never
    from running it): the compact float32 source, its float64 upcast
    (``_matrix``), the largest outer-fold training-row copy (fancy
    indexing always copies), that slice's standardized transform, the
    largest inner-fold training-row copy within it, and that slice's
    own standardized transform. Sequential inner-loop iterations and
    per-alpha refits are not additive here -- each transient copy is
    freed before the next is created, so only one of each layer is ever
    concurrently resident.
    """

    if row_count <= 0 or feature_dim <= 0:
        raise MemoryPlanError("row_count and feature_dim must be positive")
    if not outer_fold_row_counts or sum(outer_fold_row_counts) != row_count:
        raise MemoryPlanError("outer_fold_row_counts must sum to row_count")
    if inner_fold_count < 2:
        raise MemoryPlanError("inner_fold_count must be at least 2")

    compact_source_bytes = row_count * feature_dim * COMPACT_FEATURE_ITEMSIZE_BYTES
    upcast_matrix_bytes = row_count * feature_dim * RIDGE_WORKING_DTYPE_ITEMSIZE_BYTES

    largest_test_fold_rows = min(outer_fold_row_counts)
    largest_outer_training_rows = row_count - largest_test_fold_rows
    outer_training_fraction = largest_outer_training_rows / row_count
    outer_training_bytes = int(upcast_matrix_bytes * outer_training_fraction)
    outer_standardized_bytes = outer_training_bytes

    inner_training_fraction = (inner_fold_count - 1) / inner_fold_count
    inner_training_bytes = int(outer_training_bytes * inner_training_fraction)
    inner_standardized_bytes = inner_training_bytes

    working_copy_bytes = (
        upcast_matrix_bytes
        + outer_training_bytes
        + outer_standardized_bytes
        + inner_training_bytes
        + inner_standardized_bytes
    )

    return {
        "compact_source_bytes": compact_source_bytes,
        "upcast_matrix_bytes": upcast_matrix_bytes,
        "outer_training_bytes": outer_training_bytes,
        "outer_standardized_bytes": outer_standardized_bytes,
        "inner_training_bytes": inner_training_bytes,
        "inner_standardized_bytes": inner_standardized_bytes,
        "working_copy_bytes": working_copy_bytes,
    }


def build_raw_pixel_memory_plan(
    *,
    row_count: int,
    feature_dim: int,
    outer_fold_row_counts: Sequence[int],
    inner_fold_count: int,
    host_memory: dict[str, int | None] | None = None,
) -> MemoryPlan:
    """Build the pass/fail memory admission decision for raw_pixel's fit.

    Fails closed (``admitted=False``) whenever host memory could not be
    detected at all, or whenever the conservative peak estimate exceeds
    whatever budget was detected (available memory when known, else raw
    physical memory) -- never silently admits execution it cannot
    justify.
    """

    resolved_host_memory = host_memory if host_memory is not None else detect_host_memory()
    breakdown = estimate_raw_pixel_ridge_working_copy_bytes(
        row_count=row_count,
        feature_dim=feature_dim,
        outer_fold_row_counts=outer_fold_row_counts,
        inner_fold_count=inner_fold_count,
    )
    estimated_peak_bytes = (
        breakdown["compact_source_bytes"] + breakdown["working_copy_bytes"] + FIXED_OVERHEAD_BYTES
    )

    physical = resolved_host_memory.get("physical_bytes")
    available = resolved_host_memory.get("available_bytes")
    budget = available if available is not None else physical

    reasons: list[str] = []
    admitted = True
    if budget is None:
        admitted = False
        reasons.append("host_memory_undetected")
    elif estimated_peak_bytes > budget:
        admitted = False
        reasons.append(
            f"estimated_peak_bytes={estimated_peak_bytes} exceeds "
            f"detected_budget_bytes={budget}"
        )

    return MemoryPlan(
        feature_value_count=row_count * feature_dim,
        source_dtype=COMPACT_FEATURE_DTYPE_NAME,
        compact_payload_bytes=breakdown["compact_source_bytes"],
        expected_largest_resident_matrix_bytes=breakdown["upcast_matrix_bytes"],
        expected_working_copy_bytes=breakdown["working_copy_bytes"],
        estimated_peak_bytes=estimated_peak_bytes,
        detected_host_physical_bytes=physical,
        detected_host_available_bytes=available,
        admitted=admitted,
        reasons=tuple(reasons),
    )


__all__ = [
    "BYTES_PER_GIB",
    "COMPACT_FEATURE_DTYPE_NAME",
    "COMPACT_FEATURE_ITEMSIZE_BYTES",
    "FIXED_OVERHEAD_BYTES",
    "RIDGE_WORKING_DTYPE_ITEMSIZE_BYTES",
    "MemoryPlan",
    "MemoryPlanError",
    "build_raw_pixel_memory_plan",
    "detect_host_memory",
    "estimate_raw_pixel_ridge_working_copy_bytes",
]
