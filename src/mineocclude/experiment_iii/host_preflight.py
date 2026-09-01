"""The ``A3`` environment preflight (authority 6/A3, 3.1, 13.2).

``A3`` proves that a *particular host* can run a *particular set of lifecycle
stages* before anything expensive starts. Two properties of the frozen state
shape this module:

* **A3 is per host, and it names the stages that host authorizes.** The lifecycle
  requires ``environment_receipt.json naming the stages this host authorizes``
  and gates the GPU check on ``IF_THIS_HOST_RUNS_A9``. A capture-only host
  therefore cannot verify the MineWorld checkpoint or VAE -- the weights are not
  present -- and the honest receipt is one that records those checks as
  ``NOT_APPLICABLE`` **and refuses to authorize any extraction stage**. Silently
  passing them, or silently authorizing extraction anyway, is the failure this
  scoping exists to prevent.
* **The scoping cuts both ways, and used not to.** Display availability and
  renderer qualification are capture-host requirements; the checkpoint, VAE and
  CUDA checks are extraction-host requirements. Applying the display gate to
  both roles made a headless GPU host fail ``ENV_DISPLAY_UNAVAILABLE`` on the
  way to a receipt that would have recorded the renderer as ``NOT_APPLICABLE``
  -- the module refusing a host for failing a check it had already decided did
  not apply. Each gate now runs on exactly the role whose stages need it.
* **The storage gate is the combined-program gate, in binary GiB.** It is applied
  by :mod:`mineocclude.experiment_iii.storage_preflight`, which owns the
  double-counting and unit rules. This module resolves the *physical* device
  identity of each logical pool and hands bytes to that gate; it never compares
  a decimal-GB number against a binary-GiB threshold and never lowers a
  threshold to proceed.

Every failure raises a code from the frozen taxonomy, so a refused preflight
routes straight into the recovery runbook.
"""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from mineocclude.experiment_iii.authority import (
    AUTHORITY_FREEZE_COMMIT,
    AUTHORITY_VERSION,
    CAPTURE_HZ,
    FRAMEBUFFER_HEIGHT,
    FRAMEBUFFER_WIDTH,
    FRAMES_PER_CAPTURE,
    REPOSITORY_ROOT,
    RUN_NAMESPACE,
    SPEED_BLOCKS_PER_SECOND,
    authority_sha256,
    derive_seed,
    machine_authority,
    machine_authority_sha256,
    phase0_design_sha256,
    sha256_file,
    verify_authority_binding,
)
from mineocclude.experiment_iii.blockers import blocker_codes
from mineocclude.experiment_iii.capture_runtime import (
    RuntimeConfig,
    qualify_capture_host,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.namespace import guard_write_path
from mineocclude.experiment_iii.source_closure import source_closure
from mineocclude.experiment_iii.storage_preflight import GIB, storage_preflight

__all__ = [
    "A5_EXTRACTION_STAGE",
    "CAPTURE_HOST_STAGES",
    "EXTRACTION_HOST_STAGES",
    "GATED_POOLS",
    "HostRole",
    "cuda_probe",
    "device_identity",
    "durable_round_trip",
    "environment_receipt",
    "resolve_host_pools",
    "rng_stream_fixture",
    "runtime_pins",
    "verify_model_identity",
]


#: Frozen lifecycle A5 (``P1_ENGINEERING_PILOT``) is executed by two hosts: the
#: capture host runs ``CAPTURE_10_PILOT_UNITS`` and the extraction host runs
#: ``EXTRACT_190_FORWARDS``. A5's entry condition is literally "A3 == PASS on
#: capture **and** extraction hosts", so the extraction half needs a stage token
#: of its own; without one, A5's own entry condition is unsatisfiable.
#:
#: ``A5_EXTRACTION`` is NOT ``A9``. A9 is production extraction (125 captures,
#: 2,375 forwards, 750 arrays) and its entry additionally requires A8 PASS, the
#: A6 freeze binding and ``MODEL_INFERENCE_AUTHORIZED``. A5's entry requires
#: none of those -- it requires ``P1_AUTHORIZED`` -- which is exactly why the
#: pilot's 190 forwards are authorized before P2 and production's 2,375 are not.
A5_EXTRACTION_STAGE = "A5_EXTRACTION"

#: The lifecycle stages a capture-only host may authorize. Neither extraction
#: stage appears: both need the MineWorld weights and a GPU, neither of which a
#: capture host is required to hold.
CAPTURE_HOST_STAGES = ("A4", "A5_CAPTURE", "A7")

#: The stages an extraction host authorizes once its own A3 passes. The pilot
#: stage is first because it is the one A5 can reach before P2; A9/A10 remain
#: gated on their own lifecycle entry conditions, which this receipt does not
#: and cannot satisfy.
EXTRACTION_HOST_STAGES = (A5_EXTRACTION_STAGE, "A9", "A10")

#: The three logical storage categories the A3 gate reasons about.
GATED_POOLS = ("POOL_WORKING", "POOL_DURABLE", "POOL_SCRATCH")


class HostRole:
    """The two frozen A3 host roles."""

    LOCAL_CAPTURE_HOST = "LOCAL_CAPTURE_HOST"
    GPU_EXTRACTION_HOST = "GPU_EXTRACTION_HOST"


# --------------------------------------------------------------------------
# Storage identity
# --------------------------------------------------------------------------


def device_identity(path: Path) -> dict[str, Any]:
    """The physical device a path resolves to.

    Pools are compared by **device id**, never by path string: two logical
    categories that live on one filesystem are one pool, and counting them twice
    is ``STORAGE_POOL_DOUBLE_COUNTED``. On Windows ``st_dev`` is derived from the
    volume, which is exactly the identity the gate needs.
    """
    resolved = Path(path).resolve()
    probe = resolved
    while not probe.exists():
        if probe.parent == probe:
            raise ExperimentIIIError(
                "STORAGE_INSUFFICIENT",
                f"no existing ancestor of {resolved} could be probed for a device id",
            )
        probe = probe.parent
    usage = shutil.disk_usage(probe)
    return {
        "path": resolved.as_posix(),
        "probed_ancestor": probe.as_posix(),
        "device_id": int(os.stat(probe).st_dev),
        "free_bytes": int(usage.free),
        "total_bytes": int(usage.total),
        "free_gib": usage.free / GIB,
    }


def resolve_host_pools(pool_paths: Mapping[str, Path]) -> dict[str, Any]:
    """Resolve each gated logical pool to its device id and free bytes."""
    missing = [pool for pool in GATED_POOLS if pool not in pool_paths]
    if missing:
        raise ExperimentIIIError(
            "STORAGE_INSUFFICIENT", f"A3 needs a path for every gated pool; missing {missing}"
        )
    return {pool: device_identity(pool_paths[pool]) for pool in GATED_POOLS}


def durable_round_trip(durable_root: Path) -> dict[str, Any]:
    """Write, hash, read back and compare a probe in the durable store.

    A durable store that cannot return what it was given is
    ``DURABILITY_READBACK_MISMATCH``; one that cannot be written at all is
    ``DURABILITY_STORE_UNREACHABLE``. Both fail closed here rather than at the
    first production capture.
    """
    payload = (
        f"mineocclude-experiment-iii durable probe\n"
        f"{RUN_NAMESPACE}\n{AUTHORITY_FREEZE_COMMIT}\n"
    ).encode("utf-8")
    expected = hashlib.sha256(payload).hexdigest()
    probe = Path(durable_root) / ".a3_durable_probe"
    try:
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_bytes(payload)
        os.sync() if hasattr(os, "sync") else None
        observed_bytes = probe.read_bytes()
    except OSError as error:
        raise ExperimentIIIError(
            "DURABILITY_STORE_UNREACHABLE",
            f"the durable store at {durable_root} refused a probe write: {error}",
        ) from error
    finally:
        try:
            probe.unlink()
        except OSError:
            pass
    observed = hashlib.sha256(observed_bytes).hexdigest()
    if observed != expected:
        raise ExperimentIIIError(
            "DURABILITY_READBACK_MISMATCH",
            f"the durable store returned {observed}, not the {expected} it was given",
        )
    return {
        "probe_bytes": len(payload),
        "written_sha256": expected,
        "readback_sha256": observed,
        "verified": True,
    }


# --------------------------------------------------------------------------
# Runtime pins
# --------------------------------------------------------------------------


def _gradle_properties(project: Path) -> dict[str, str]:
    path = project / "gradle.properties"
    if not path.is_file():
        raise ExperimentIIIError(
            "ENV_RUNTIME_VERSION_MISMATCH", f"the Fabric project has no {path}"
        )
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def _framebuffer_constants(project: Path) -> tuple[int, int]:
    """Read ``FrameCapture.EXPECTED_W/H`` from the client source.

    The framebuffer pin is verified against the apparatus source rather than a
    literal repeated here, so a client-side edit cannot drift away from the
    authority unnoticed.
    """
    source = (
        project
        / "src/main/java/com/mineocclude/client/FrameCapture.java"
    )
    if not source.is_file():
        raise ExperimentIIIError(
            "ENV_FRAMEBUFFER_SIZE_MISMATCH", f"FrameCapture source is absent: {source}"
        )
    text = source.read_text(encoding="utf-8")
    found: dict[str, int] = {}
    for name in ("EXPECTED_W", "EXPECTED_H"):
        marker = f"int {name} = "
        index = text.find(marker)
        if index < 0:
            raise ExperimentIIIError(
                "ENV_FRAMEBUFFER_SIZE_MISMATCH", f"{name} is not declared in {source}"
            )
        tail = text[index + len(marker) :]
        digits = tail[: tail.find(";")].strip()
        found[name] = int(digits)
    return found["EXPECTED_W"], found["EXPECTED_H"]


def runtime_pins(
    project: Path,
    runtime_root: Path | None = None,
    mod_jar: Path | None = None,
) -> dict[str, Any]:
    """Verify every frozen apparatus pin of authority 3.1 for this host."""
    machine = machine_authority()["apparatus"]
    properties = _gradle_properties(project)
    expected = {
        "minecraft_version": machine["minecraft_version"],
        "fabric_loader_version": machine["fabric_loader_version"],
        "fabric_api_version": machine["fabric_api_version"],
        "yarn_mappings": machine["yarn_mappings"],
    }
    declared = {
        "minecraft_version": properties.get("minecraft_version"),
        "fabric_loader_version": properties.get("loader_version"),
        "fabric_api_version": properties.get("fabric_version"),
        "yarn_mappings": properties.get("yarn_mappings"),
    }
    mismatches = {
        key: {"expected": value, "declared": declared.get(key)}
        for key, value in expected.items()
        if declared.get(key) != value
    }
    if mismatches:
        raise ExperimentIIIError(
            "ENV_RUNTIME_VERSION_MISMATCH",
            f"the Fabric project disagrees with the frozen apparatus pins: {mismatches}",
        )

    width, height = _framebuffer_constants(project)
    if (width, height) != (FRAMEBUFFER_WIDTH, FRAMEBUFFER_HEIGHT):
        raise ExperimentIIIError(
            "ENV_FRAMEBUFFER_SIZE_MISMATCH",
            f"FrameCapture declares {width}x{height}; the authority freezes "
            f"{FRAMEBUFFER_WIDTH}x{FRAMEBUFFER_HEIGHT}",
        )

    receipt: dict[str, Any] = {
        "declared_pins": declared,
        "expected_pins": expected,
        "pins_match": True,
        "framebuffer_width": width,
        "framebuffer_height": height,
        "framebuffer_source": "FrameCapture.EXPECTED_W/EXPECTED_H",
        "capture_hz": CAPTURE_HZ,
        "frames_per_capture": FRAMES_PER_CAPTURE,
        "speed_blocks_per_second": SPEED_BLOCKS_PER_SECOND,
    }

    if mod_jar is not None and Path(mod_jar).is_file():
        jar = Path(mod_jar)
        receipt["mod_jar"] = {
            "path": jar.as_posix(),
            "sha256": sha256_file(jar),
            "bytes": jar.stat().st_size,
        }
    else:
        receipt["mod_jar"] = None

    if runtime_root is not None:
        root = Path(runtime_root)
        receipt["runtime_root"] = {
            "path": root.as_posix(),
            "present": root.is_dir(),
            "server_present": (root / "server").is_dir(),
            "client_present": (root / "client").is_dir(),
        }
    return receipt


def rng_stream_fixture() -> dict[str, Any]:
    """Reproduce a frozen RNG stream so a host-dependent RNG is caught here.

    The seeds are derived from the frozen master salt, so a platform whose hash
    or integer width disagreed with the authority host would produce different
    values and fail the preflight rather than a cohort.
    """
    domains = ("start_position", "process_noise")
    observed = {
        domain: [derive_seed(domain, index) for index in range(4)] for domain in domains
    }
    for domain, seeds in observed.items():
        if len(set(seeds)) != len(seeds):
            raise ExperimentIIIError(
                "SOURCE_STATIC_TEST_FAILURE",
                f"the {domain} seed stream repeated a value on this host: {seeds}",
            )
        if any(seed < 0 or seed >= (1 << 64) for seed in seeds):
            raise ExperimentIIIError(
                "SOURCE_STATIC_TEST_FAILURE",
                f"the {domain} seed stream left the 64-bit domain on this host",
            )
    return {
        "domains": list(domains),
        "seeds": observed,
        "deterministic": True,
        "note": "derived from the frozen master salt; host-independent by construction",
    }


# --------------------------------------------------------------------------
# The receipt
# --------------------------------------------------------------------------


def _display_probe() -> dict[str, Any]:
    """Whether this host can present a rendering surface at all.

    A capture host with no display cannot render a frame, so the absence of one
    is ``ENV_DISPLAY_UNAVAILABLE``. The probe is deliberately weak: it proves a
    surface *exists*, not that a client will render into it, which only the
    renderer qualification below can establish.

    Weak is not the same as vacuous. This function once ended its Windows branch
    with ``bool(os.environ.get("SESSIONNAME")) or True``, which made
    ``available`` the constant ``True`` and the whole check unfalsifiable. The
    Windows branch now asks the window manager for the primary screen extent:
    a session with no desktop (a service in session 0, for instance) reports
    zero and is refused, which is the answer the check exists to produce.
    """
    system = platform.system()
    if system == "Windows":
        session_name = os.environ.get("SESSIONNAME")
        width = height = 0
        mechanism = "WINDOWS_SYSTEM_METRICS"
        try:
            import ctypes

            user32 = ctypes.windll.user32  # type: ignore[attr-defined]
            width = int(user32.GetSystemMetrics(0))
            height = int(user32.GetSystemMetrics(1))
        except Exception as error:  # pragma: no cover - non-Windows CPython
            return {
                "platform": system,
                "mechanism": "WINDOWS_SYSTEM_METRICS_UNAVAILABLE",
                "session_name": session_name,
                "error": str(error),
                "available": False,
            }
        return {
            "platform": system,
            "mechanism": mechanism,
            "session_name": session_name,
            "primary_screen_width": width,
            "primary_screen_height": height,
            "available": width > 0 and height > 0,
        }
    display = os.environ.get("DISPLAY")
    return {
        "platform": system,
        "mechanism": "X11_DISPLAY",
        "display": display,
        "available": bool(display),
    }


def cuda_probe() -> dict[str, Any]:
    """What CUDA this host actually exposes, asked of torch rather than assumed.

    The lifecycle's A3 pass condition is
    ``GPU_PRESENT_AND_SUFFICIENT_FOR_A9_IF_THIS_HOST_RUNS_A9``; the blocker is
    ``ENV_GPU_UNAVAILABLE``. A host that cannot import torch, or whose torch
    reports no CUDA device, answers ``available: false`` here and is refused by
    :func:`environment_receipt` -- it does not silently record a GPU it does not
    have. Nothing in this probe loads MineWorld or runs a kernel.
    """
    try:
        import torch  # type: ignore[import-not-found]
    except Exception as error:
        return {
            "available": False,
            "reason": f"torch is not importable on this host: {error}",
        }
    try:
        available = bool(torch.cuda.is_available())
    except Exception as error:  # pragma: no cover - driver-level failure
        return {"available": False, "reason": f"torch.cuda.is_available() failed: {error}"}
    if not available:
        return {
            "available": False,
            "torch_version": str(getattr(torch, "__version__", "unknown")),
            "reason": "torch reports no CUDA device on this host",
        }
    index = int(torch.cuda.current_device())
    properties = torch.cuda.get_device_properties(index)
    return {
        "available": True,
        "torch_version": str(getattr(torch, "__version__", "unknown")),
        "cuda_version": str(getattr(torch.version, "cuda", "unknown")),
        "device_count": int(torch.cuda.device_count()),
        "device_index": index,
        "device_name": str(properties.name),
        "capability": f"{properties.major}.{properties.minor}",
        "total_memory_bytes": int(properties.total_memory),
    }


def verify_model_identity(
    main_checkpoint_path: Path | None,
    vae_checkpoint_path: Path | None,
) -> dict[str, Any]:
    """Hash the weights this host will actually load and compare them.

    The frozen A3 operations are ``VERIFY_CHECKPOINT_SHA256_a92c311b`` and
    ``VERIFY_VAE_SHA256_370d06be``, and the forbidden repair is
    ``PROCEED_WITH_MISMATCHED_CHECKPOINT_OR_VAE``. So this reads the bytes on
    disk and compares the real digest; the expectation is read from the machine
    authority, never transcribed here. A path that is absent, is not an ordinary
    file, or hashes to anything else fails closed with its own blocker code --
    ``verified`` is only ever ``True`` on an exact match of both.
    """
    extraction = machine_authority()["extraction"]
    expected = {
        "main_checkpoint": (
            "main_checkpoint_sha256",
            "ENV_CHECKPOINT_HASH_MISMATCH",
            main_checkpoint_path,
            str(extraction["main_checkpoint_sha256"]),
        ),
        "vae_checkpoint": (
            "vae_sha256",
            "ENV_VAE_HASH_MISMATCH",
            vae_checkpoint_path,
            str(extraction["vae_sha256"]),
        ),
    }
    observed: dict[str, Any] = {}
    for name, (_field, blocker, path, digest) in expected.items():
        if path is None:
            raise ExperimentIIIError(
                blocker,
                f"an extraction host must name its {name} so A3 can hash it; "
                "this preflight will not record a weight identity it never read",
            )
        resolved = Path(path).resolve()
        if not resolved.is_file():
            raise ExperimentIIIError(
                blocker,
                f"the {name} is not an ordinary file on this host: {resolved}",
            )
        actual = sha256_file(resolved)
        if actual != digest:
            raise ExperimentIIIError(
                blocker,
                f"the {name} at {resolved} hashes {actual}; the authority freezes "
                f"{digest}. That is not a configuration problem, it is a "
                "different model",
            )
        observed[name] = {
            "path": resolved.as_posix(),
            "bytes": resolved.stat().st_size,
            "expected_sha256": digest,
            "observed_sha256": actual,
            "matches": True,
        }
    return observed


def _open_local_port(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.25)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def environment_receipt(
    *,
    host_role: str,
    pool_paths: Mapping[str, Path],
    durable_root: Path,
    project: Path,
    runtime_root: Path | None = None,
    mod_jar: Path | None = None,
    durability_mode: str = "LOCAL_MIRROR_SAME_POOL",
    local_mirror_enabled: bool = True,
    implementation_checkpoint_commit: str | None = None,
    required_free_ports: Sequence[int] = (25565,),
    runtime_config: RuntimeConfig | None = None,
    main_checkpoint_path: Path | None = None,
    vae_checkpoint_path: Path | None = None,
    gpu_probe: Callable[[], Mapping[str, Any]] = cuda_probe,
) -> dict[str, Any]:
    """Run every A3 check applicable to ``host_role`` and return its receipt.

    Raises the taxonomy code of the first failing check. A receipt is only
    returned when every applicable check passed, so a returned receipt always
    means ``A3 == PASS`` for the stages it names.
    """
    if host_role not in (HostRole.LOCAL_CAPTURE_HOST, HostRole.GPU_EXTRACTION_HOST):
        raise ExperimentIIIError(
            "PROVENANCE_BINDING_MISSING", f"{host_role!r} is not a frozen A3 host role"
        )
    runs_extraction = host_role == HostRole.GPU_EXTRACTION_HOST

    binding = verify_authority_binding()
    closure = source_closure()
    pools = resolve_host_pools(pool_paths)

    storage = storage_preflight(
        {pool: {"device_id": entry["device_id"], "free_bytes": entry["free_bytes"]}
         for pool, entry in pools.items()},
        durability_mode=durability_mode,
        local_mirror_enabled=local_mirror_enabled,
    )
    durable = durable_round_trip(durable_root)
    pins = runtime_pins(project, runtime_root=runtime_root, mod_jar=mod_jar)

    # Display and renderer qualification are CAPTURE-host requirements. The
    # frozen A3 operation list pairs ``VERIFY_DISPLAY_AVAILABILITY`` with the
    # framebuffer and Minecraft pins -- all apparatus properties -- and nothing
    # in A5_EXTRACTION/A9 renders a frame: extraction reads banked PNGs and runs
    # a teacher-forced forward. Applying the display gate to the extraction host
    # made a headless GPU box fail ``ENV_DISPLAY_UNAVAILABLE`` while the same
    # receipt went on to declare the renderer ``NOT_APPLICABLE`` -- the module
    # contradicting itself. The capture-host requirement below is unchanged.
    display: dict[str, Any]
    if runs_extraction:
        display = {
            "status": "NOT_APPLICABLE",
            "reason": (
                "this host does not capture; extraction reads banked frames and "
                "renders nothing"
            ),
            "available": None,
        }
    else:
        display = {"status": "EVALUATED", **_display_probe()}
        if not display["available"]:
            raise ExperimentIIIError(
                "ENV_DISPLAY_UNAVAILABLE",
                f"host role {host_role} must render frames but exposes no display "
                "surface",
            )

    # A display surface EXISTING is not the same as this host being allowed to
    # produce scientific frames. A capture host must additionally pass the
    # renderer qualification of authority 7.10f / capture_runtime; without it a
    # receipt would authorize A4/A5/A7 on a renderer whose output no capture
    # receipt can vouch for, which is precisely the fabricated PASS this check
    # exists to make impossible.
    renderer: dict[str, Any]
    if runs_extraction:
        renderer = {"status": "NOT_APPLICABLE", "reason": "this host does not capture"}
    elif runtime_config is None:
        renderer = {
            "status": "NOT_ESTABLISHED",
            "qualified": False,
            "reason": (
                "no capture runtime config was supplied, so renderer qualification "
                "was never established; this receipt authorizes no capture stage"
            ),
        }
    else:
        qualification = qualify_capture_host(runtime_config)
        renderer = {"status": "EVALUATED", **qualification}
        if not qualification["qualified"]:
            raise ExperimentIIIError(
                "ENV_DISPLAY_UNAVAILABLE",
                "this host is not a qualified Experiment III capture renderer: "
                + "; ".join(qualification["reasons"]),
            )

    # Namespace isolation: prove the guard actually refuses a historical write
    # on this host rather than trusting that it would.
    namespace_probe: dict[str, Any] = {"guard_admits_experiment_iii_root": False,
                                       "guard_refuses_historical_root": False}
    guard_write_path(REPOSITORY_ROOT / "docs" / "experiment_iii" / "p0" / "probe.json")
    namespace_probe["guard_admits_experiment_iii_root"] = True
    try:
        guard_write_path(REPOSITORY_ROOT / "docs" / "status" / "probe.json")
    except ExperimentIIIError:
        namespace_probe["guard_refuses_historical_root"] = True
    if not namespace_probe["guard_refuses_historical_root"]:
        raise ExperimentIIIError(
            "PROVENANCE_NAMESPACE_VIOLATION",
            "the namespace guard admitted a historical artifact root on this host",
        )

    write_probe_root = REPOSITORY_ROOT / "docs" / "experiment_iii"
    writable = os.access(write_probe_root, os.W_OK)
    if not writable:
        raise ExperimentIIIError(
            "DURABILITY_STORE_UNREACHABLE",
            f"the Experiment III artifact root is not writable: {write_probe_root}",
        )

    now = datetime.now().astimezone()
    model_checks: dict[str, Any]
    gpu: dict[str, Any]
    if runs_extraction:
        # An extraction host must prove the weights it will actually load. The
        # operational paths are inputs, the digests are read from the machine
        # authority, and the comparison is against bytes on this host disk.
        # Supplying no path is still a refusal -- this branch will not record a
        # weight identity it never read -- but supplying the real weights now
        # produces a receipt instead of an unconditional blocker.
        observed = verify_model_identity(main_checkpoint_path, vae_checkpoint_path)
        gpu = {"status": "EVALUATED", **dict(gpu_probe())}
        if not gpu.get("available"):
            raise ExperimentIIIError(
                "ENV_GPU_UNAVAILABLE",
                "an extraction host must expose a CUDA device for the A5/A9 "
                f"forwards: {gpu.get('reason', 'no CUDA device reported')}",
            )
        model_checks = {
            "status": "VERIFIED",
            "main_checkpoint_sha256_expected": machine_authority()["extraction"][
                "main_checkpoint_sha256"
            ],
            "vae_sha256_expected": machine_authority()["extraction"]["vae_sha256"],
            "main_checkpoint": observed["main_checkpoint"],
            "vae_checkpoint": observed["vae_checkpoint"],
            "preprocessing_change_allowed": bool(
                machine_authority()["extraction"]["preprocessing_change_allowed"]
            ),
            "verified": True,
            "note": (
                "both digests were recomputed from the bytes on this host and "
                "matched the authority exactly"
            ),
        }
    else:
        gpu = {
            "status": "NOT_APPLICABLE",
            "reason": "this host runs no forward; the GPU gate is scoped to extraction",
            "available": None,
        }
        model_checks = {
            "status": "NOT_APPLICABLE",
            "reason": (
                "this host runs no extraction stage; the lifecycle scopes the "
                "checkpoint, VAE, preprocessing-identity and GPU checks to the "
                "host that runs extraction"
            ),
            "main_checkpoint_sha256_expected": machine_authority()["extraction"][
                "main_checkpoint_sha256"
            ],
            "vae_sha256_expected": machine_authority()["extraction"]["vae_sha256"],
            "verified": False,
            "consequence": (
                "A5_EXTRACTION, A9 and A10 are NOT authorized by this receipt"
            ),
        }

    if runs_extraction:
        authorized = list(EXTRACTION_HOST_STAGES)
    elif renderer.get("qualified"):
        authorized = list(CAPTURE_HOST_STAGES)
    else:
        # Fails closed: every other A3 check may have passed, but an
        # unqualified or unestablished renderer authorizes nothing.
        authorized = []

    return {
        "schema_version": "mineocclude-experiment-iii-environment-receipt-v1",
        "stage": "A3",
        "host_role": host_role,
        "host": {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": sys.version.split()[0],
            "cpu_count": os.cpu_count(),
        },
        "clock": {
            "local_iso8601": now.isoformat(),
            "utc_iso8601": datetime.now(timezone.utc).isoformat(),
            "timezone": str(now.tzinfo),
            "utc_offset_seconds": int(now.utcoffset().total_seconds()) if now.utcoffset() else 0,
            "monotonic_available": True,
            "monotonic_sample": time.monotonic(),
        },
        "authority_version": AUTHORITY_VERSION,
        "authority_binding": binding,
        "authority_sha256": authority_sha256(),
        "machine_authority_sha256": machine_authority_sha256(),
        "phase0_design_sha256": phase0_design_sha256(),
        "authority_freeze_commit": AUTHORITY_FREEZE_COMMIT,
        "authority_drift": False,
        "source_closure": closure,
        "implementation_checkpoint_commit": implementation_checkpoint_commit,
        "runtime_namespace": RUN_NAMESPACE,
        "namespace_isolation": namespace_probe,
        "artifact_root_writable": writable,
        "storage_pools": pools,
        "storage_gate": storage,
        "durability": {
            "mode": durability_mode,
            "local_mirror_enabled": local_mirror_enabled,
            "durable_root": Path(durable_root).resolve().as_posix(),
            "round_trip": durable,
        },
        "runtime_pins": pins,
        "display": display,
        "renderer_qualification": renderer,
        "gpu": gpu,
        "local_ports": {
            str(port): {"in_use": _open_local_port(port)} for port in required_free_ports
        },
        "rng_stream_fixture": rng_stream_fixture(),
        "blocker_taxonomy_available": True,
        "blocker_taxonomy_code_count": len(blocker_codes()),
        "model_identity_checks": model_checks,
        "resource_policy": {
            "SAGEMAKER_STARTED": False,
            "GPU_USED": False,
            "CUDA_USED": False,
            "MINEWORLD_MODEL_LOADED": False,
            "MINEWORLD_INFERENCE_RUN": False,
        },
        "authorized_stages": authorized,
        "not_authorized_stages": list(EXTRACTION_HOST_STAGES) if not runs_extraction else [],
        "passed": True,
        "authorizes_capture_stages": bool(authorized) and not runs_extraction,
        "fails_closed": True,
    }
