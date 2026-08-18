#!/usr/bin/env python3
"""Deterministic generators for the pre-outcome provenance and Stage-1 authorization receipts.

Both receipts used to be hand-written. A hand-written receipt saying
``runtime_identity_verified: true`` is a claim about a verification nobody
performed, and ``status: FROZEN_VERIFIED`` typed into a file is not a freeze.
Everything emitted here is *derived*: each boolean is the return of the verifier
that establishes it, and every binding is recomputed from the artefact it names.
If a verifier raises, no receipt is written.

Nothing in this module collects data, starts Minecraft, or observes a scientific
outcome. It performs read-only probes of the runtime and, when explicitly asked,
one round-trip probe of the durable prefix.

Commands
--------
``runtime-preflight``
    Reconstruct the pinned JDK/display runtime, execute the identity probes, and
    write the probe evidence artefact the provenance receipt consumes.

``provenance``
    Verify that probe evidence against the frozen authority and write the
    pre-outcome provenance receipt.

``stage1-authorization``
    Re-verify the provenance receipt and every controlling precondition, then
    write the Stage-1 authorization receipt. Stage 2 stays unauthorized.

``stage2-provenance``
    The same controls as ``provenance``, bound to the materialized Stage-2
    manifest and namespace, plus the frozen Stage-1 PASS re-derived from its own
    evidence. Authorizes nothing.

``stage2-authorization``
    Re-verify that Stage-2 provenance, the frozen Stage-1 PASS and the
    materialized Stage-2 design, write the post-Stage-1 authorization, and then
    run the real ``require_stage2_authorization`` barrier over the result. A
    document the barrier would refuse is deleted instead of returned.

Source-commit binding is two-step, because a receipt cannot contain the hash of
a commit that does not exist until the receipt is committed:

1. ``provenance`` before the freeze records the reviewed source closure and
   emits ``PRE_FREEZE_VERIFIED``, which the launch gate refuses;
2. the package is frozen into a commit;
3. ``provenance --freeze-commit <sha>`` re-runs every verifier against the
   committed tree, confirms the committed bytes equal the reviewed bytes, and
   emits ``FROZEN_VERIFIED``, which the launch gate accepts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Both the repository root and ``src``: this module imports the unit driver by
# its package path, and the driver itself imports ``mineocclude`` from ``src``.
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from mineocclude.prospective.development_workflow import (  # noqa: E402
    OPERATIONAL_SMOKE_ARTIFACT_ID, OPERATIONAL_SMOKE_CLASSIFICATION,
    OPERATIONAL_SMOKE_DISPLAY_GEOMETRY as CAPTURE_DISPLAY_GEOMETRY,
    OPERATIONAL_SMOKE_HANDSHAKE_SCHEMA, OPERATIONAL_SMOKE_SCHEMA,
    RUNTIME_CRITICAL_SOURCE_PATHS, EvidenceError, Stage1Evaluator, atomic_write_json,
    bind_historical_source_closure,
    canonical_json_bytes, canonical_payload_sha256, capture_contract_preflight,
    capture_toolchain_evidence, derive_effective_capture_spec, load_json,
    operational_smoke_namespace, require_capture_spec_contract,
    require_capture_toolchain, require_operational_smoke,
    require_stage2_authorization, require_stage_manifest_binding, resolve_qualified_runtime,
    runtime_critical_source_closure_sha256, sha256_file, stage_run_inventory_sha256,
    validate_stage2_manifest_design, verify_probe_execution, verify_runtime_identity,
    verify_runtime_source_hashes,
)
from mineocclude.prospective.source_provenance import CriticalSource, verify_sources  # noqa: E402
from mineocclude.prospective.package_binding import (  # noqa: E402
    PackageBinding, artifact_version_tag, provenance_artifact_id_for,
    resolve_package_binding, stage1_decision_artifact_id,
)

SCHEMA_VERSION = "1.1"
RUNTIME_POLICY = "BOUND_AT_LAUNCH_BY_PREOUTCOME_PROVENANCE_RECEIPT"

#: Package version this process generates receipts for. Rebound -- once, before
#: ``main`` -- by the sibling v0.3 entrypoint. Every function below reads these
#: as globals at call time, so rebinding is what makes one implementation serve
#: two experiments without either being able to impersonate the other.
BINDING: PackageBinding
PACKAGE: Path
AUTHORITY_PATH: Path
STAGE1_MANIFEST_PATH: Path
STAGE2_MANIFEST_PATH: Path
PROVENANCE_ARTIFACT_ID: str
AUTHORIZATION_ARTIFACT_ID: str
GENERATED_BY: str


def bind_package(version_tag: str, *, entrypoint: str) -> PackageBinding:
    """Point this module at one verified qualification package.

    ``resolve_package_binding`` refuses unless the package's own bytes identify
    it as ``version_tag``, so a receipt generated here cannot carry a version it
    was not actually built against. ``entrypoint`` is recorded verbatim in every
    artifact's ``generated_by``, so the receipt names the command that made it.
    """
    global BINDING, PACKAGE, AUTHORITY_PATH, STAGE1_MANIFEST_PATH, STAGE2_MANIFEST_PATH
    global PROVENANCE_ARTIFACT_ID, AUTHORIZATION_ARTIFACT_ID, GENERATED_BY
    BINDING = resolve_package_binding(version_tag, ROOT)
    PACKAGE = BINDING.package
    AUTHORITY_PATH = BINDING.authority_path
    STAGE1_MANIFEST_PATH = BINDING.stage1_manifest_path
    STAGE2_MANIFEST_PATH = BINDING.stage2_manifest_path
    PROVENANCE_ARTIFACT_ID = BINDING.provenance_artifact_id
    AUTHORIZATION_ARTIFACT_ID = BINDING.authorization_artifact_id
    GENERATED_BY = entrypoint
    return BINDING


bind_package("v0.2", entrypoint="scripts/regime_a_prime_qualification_v0_2/generate_receipts.py")


def git(*arguments: str) -> str:
    return subprocess.run(["git", *arguments], cwd=ROOT, text=True,
                          capture_output=True, check=True).stdout.strip()


def generation_time() -> str:
    """Wall-clock stamp. Scientifically inert: no gate reads it."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------------------------------------------------------------- preflight


def ensure_display(authority: dict) -> tuple[str, subprocess.Popen | None]:
    """Bring up the pinned virtual display if it is not already serving.

    Recorded because overlay-installed components may not survive a Space
    rebuild: the display is reconstructed from the authority's own pins rather
    than inherited from whatever a shell exported.
    """
    reconstruction = authority["runtime_identity_policy"]["runtime_reconstruction"]
    display = reconstruction["display"]
    # Readiness is the display's unix socket, not a TCP port: Xvfb runs
    # -nolisten tcp by default, so nothing ever binds 6000+N and a TCP probe
    # would time out against a perfectly healthy server.
    endpoint = Path(f"/tmp/.X11-unix/X{display.lstrip(':').split('.')[0]}")
    if endpoint.exists():
        return display, None
    server = subprocess.Popen(
        ["Xvfb", display, "-screen", *reconstruction["xvfb_screen"].split(" ", 1)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        time.sleep(0.2)
        if endpoint.exists():
            return display, server
        if server.poll() is not None:
            raise EvidenceError(
                f"Xvfb exited {server.returncode} while reconstructing display {display}")
    server.terminate()
    raise EvidenceError(f"pinned virtual display {display} could not be reconstructed")


def runtime_preflight(output: Path) -> int:
    """Reconstruct the runtime, probe it, and write verified probe evidence."""
    authority = load_json(AUTHORITY_PATH)
    runtime = resolve_qualified_runtime(authority)
    display, server = ensure_display(authority)
    try:
        # Imported here: the driver pulls in numpy/PIL and the legacy capture
        # tree, which a preflight has no reason to load if the JDK is missing.
        from scripts.regime_a_prime_qualification_v0_2 import stage_unit_driver

        receipt = stage_unit_driver.probe_runtime(authority)
    finally:
        if server is not None:
            server.terminate()
            server.wait(timeout=10)
    # Reproduce, do not trust: the same verifier the launch gate will run.
    verify_probe_execution(receipt, "runtime_provenance_receipt", authority=authority)
    atomic_write_json(output, receipt)
    print("RUNTIME_RECONSTRUCTION_STATUS=READY")
    print(f"JAVA_EXECUTABLE={runtime['java_executable']}")
    print(f"DISPLAY_RECONSTRUCTED={display}")
    print(f"PROBE_EVIDENCE_SHA256={receipt['probe_evidence_sha256']}")
    print(f"PROBE_EVIDENCE_PATH={output}")
    return 0


# ---------------------------------------------------------------- durable probe


def durable_round_trip(prefix: str) -> dict:
    """Write, list, read back, and remove one isolated prospective probe object.

    A real round trip, because ``remote_durable_prefix_read_write_probe_verified``
    must be a result rather than a claim. Touches only a ``.preflight/`` key
    outside any scientific namespace.
    """
    clean_prefix = prefix.rstrip("/")
    if not clean_prefix.startswith("s3://"):
        raise EvidenceError("durable probe prefix is not an S3 URI")
    parts = clean_prefix[5:].split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise EvidenceError("durable probe prefix has no isolated bucket/key namespace")
    bucket, base_key = parts
    token = uuid.uuid4().hex
    object_key = f"{base_key}/.preflight/{token}.json"
    key = f"s3://{bucket}/{object_key}"
    payload = json.dumps({"probe": "pre-outcome-durable-round-trip", "token": token}).encode()
    payload_sha = hashlib.sha256(payload).hexdigest()
    uploaded = False
    primary_error: Exception | None = None

    def listed_keys() -> set[str]:
        result = subprocess.run(
            ["aws", "s3api", "list-objects-v2", "--bucket", bucket,
             "--prefix", object_key, "--output", "json"],
            check=True, capture_output=True)
        try:
            listing = json.loads(result.stdout)
            return {item["Key"] for item in listing.get("Contents", [])}
        except (json.JSONDecodeError, KeyError, TypeError, UnicodeDecodeError) as exc:
            raise EvidenceError("durable probe listing was malformed") from exc

    try:
        subprocess.run(["aws", "s3", "cp", "-", key, "--only-show-errors"],
                       input=payload, check=True)
        uploaded = True
        if listed_keys() != {object_key}:
            raise EvidenceError("durable probe object was not uniquely listable")
        readback = subprocess.run(["aws", "s3", "cp", key, "-", "--only-show-errors"],
                                  check=True, capture_output=True).stdout
        if hashlib.sha256(readback).hexdigest() != payload_sha or readback != payload:
            raise EvidenceError("durable prefix round-trip returned different bytes")
    except Exception as exc:
        primary_error = exc
    finally:
        cleanup_error: Exception | None = None
        if uploaded:
            try:
                # The target is the one UUID-qualified key constructed above;
                # no prefix or recursive deletion is ever issued.
                subprocess.run(["aws", "s3", "rm", key, "--only-show-errors"], check=True)
                if listed_keys():
                    raise EvidenceError("durable probe cleanup did not remove its object")
            except Exception as exc:
                cleanup_error = exc
        if cleanup_error is not None:
            raise EvidenceError("durable probe cleanup could not be verified") from cleanup_error
    if primary_error is not None:
        raise primary_error
    return {"verified": True, "probe_namespace": f"s3://{bucket}/{base_key}/.preflight/",
            "probe_key": key, "payload_sha256": payload_sha,
            "byte_exact_readback": True, "listing_verified": True,
            "cleanup_verified": True}


# ---------------------------------------------------------------- provenance


def display_socket(display: str) -> Path:
    """The unix socket a given X display serves on.

    Readiness is the socket, not a TCP port: Xvfb runs ``-nolisten tcp``, so
    nothing ever binds 6000+N and a TCP probe would time out against a healthy
    server.
    """
    return Path(f"/tmp/.X11-unix/X{display.lstrip(':').split('.')[0]}")


def require_no_pre_existing_display(display: str) -> None:
    """Refuse to run the smoke against a display this smoke did not start.

    This is the D4 control. A display that is already serving makes the
    production ``start_display`` early-return, so the real 640x360x24 capture
    Xvfb and openbox never start and the smoke silently degrades into "a display
    exists" -- which is what the generic 1280x720 renderer-probe display already
    proved. Failing closed here is what makes display ownership provable.
    """
    socket = display_socket(display)
    if socket.exists():
        raise EvidenceError(
            f"display {display} is already serving ({socket}); the operational smoke must "
            "start the production capture display itself. Stop the pre-existing display "
            "-- a generic renderer-probe display cannot stand in for the capture display.")


def xdpyinfo_geometry(display: str) -> tuple[int, int, int]:
    """Ask the running X server for its actual dimensions and depth."""
    result = subprocess.run(["xdpyinfo"], env={**os.environ, "DISPLAY": display},
                            text=True, capture_output=True, check=True)
    dimensions = re.search(r"dimensions:\s+(\d+)x(\d+)\s+pixels", result.stdout)
    depth = re.search(r"depth of root window:\s+(\d+)\s+planes", result.stdout)
    if not dimensions or not depth:
        raise EvidenceError(f"xdpyinfo did not report a geometry for {display}")
    return int(dimensions.group(1)), int(dimensions.group(2)), int(depth.group(1))


def stage_evidence(source: str, excerpt: str, started: float) -> dict:
    """One replayable stage record: the text, its digest, and when it was seen."""
    return {"source_path": str(source), "excerpt": excerpt,
            "excerpt_sha256": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
            "observed_monotonic": round(time.monotonic() - started, 6)}


def probe_capture_display(display: str, started: float) -> dict:
    """Confirm the running display really is the production capture geometry."""
    width, height, depth = xdpyinfo_geometry(display)
    excerpt = (f"dimensions:    {width}x{height} pixels\n"
               f"depth of root window: {depth} planes\n")
    return {"name": display, "geometry": f"{width}x{height}x{depth}",
            "xdpyinfo_width": width, "xdpyinfo_height": height, "xdpyinfo_depth": depth,
            "started_by_smoke": True,
            "stage_evidence": stage_evidence(f"xdpyinfo {display}", excerpt, started)}


def probe_openbox(display: str, started: float) -> dict:
    """Confirm the production start_display path actually started openbox.

    openbox is started by ``start_display`` right after the X server comes up and
    is what gives the focus gate an ``_NET_ACTIVE_WINDOW`` authority, so a smoke
    without it did not exercise that path.
    """
    result = subprocess.run(["pgrep", "-af", "openbox"], text=True, capture_output=True)
    matches = [line for line in result.stdout.splitlines() if "openbox" in line]
    return {"started_by_smoke": bool(matches),
            "pid": int(matches[0].split()[0]) if matches else None,
            "observed_monotonic": round(time.monotonic() - started, 6)}


def log_stage_evidence(path: Path, marker: str, started: float, *,
                       context: int = 2) -> dict:
    """Extract the lines around a startup marker from a runtime log.

    The excerpt is the evidence the stage is concluded from, so it must contain
    the marker ``launch_runtime`` itself waits on. Bounded to a few lines so the
    receipt stays small and reviewable.
    """
    if not path.exists():
        raise EvidenceError(f"runtime log {path} is absent; the stage cannot be evidenced")
    lines = path.read_text(errors="replace").splitlines()
    for index in range(len(lines) - 1, -1, -1):
        if marker in lines[index]:
            window = lines[max(0, index - context):index + 1]
            return stage_evidence(path, "\n".join(window) + "\n", started)
    raise EvidenceError(f"runtime log {path} never reported {marker!r}")


def teardown_stage_evidence(launched: list[dict], stranded: list[int],
                            started: float) -> dict:
    """Evidence that every process the smoke started is gone."""
    pids = ", ".join(str(record["pid"]) for record in launched)
    if stranded:
        raise EvidenceError(f"operational smoke stranded processes: {stranded}")
    excerpt = f"smoke: launched pids [{pids}] all exited; teardown_complete\n"
    return stage_evidence("operational-smoke-teardown", excerpt, started)


def world_session_lock_present() -> bool:
    """Whether a server still holds the Minecraft world lock after teardown.

    Tests whether the lock is *held*, not whether the file exists. ``session.lock``
    is an ordinary file that Minecraft leaves on disk after a clean shutdown; what
    the server JVM actually holds for its lifetime is a POSIX record lock on it.
    Treating the file's presence as the lock made this report ``True`` for every
    world that had ever been run, so a healthy smoke that tore its server down
    correctly was still refused as having stranded one.

    ``fcntl.lockf`` is the same POSIX record lock Java's ``FileChannel.lock``
    takes, so the two interoperate -- ``flock`` would not, and would report free
    while the JVM held it. Acquiring and immediately releasing from this process
    cannot disturb the server: if a server holds it, the acquisition fails, which
    is the answer being sought.
    """
    import fcntl

    try:
        from scripts import run_large_scale_no_wall_campaign as live
    except Exception:  # noqa: BLE001 - absence is reported, not raised
        return False
    for candidate in live.SERVER_ROOT.glob("*/session.lock"):
        try:
            with candidate.open("r+b") as handle:
                try:
                    fcntl.lockf(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    return True  # someone else holds it: a server outlived teardown
                fcntl.lockf(handle, fcntl.LOCK_UN)
        except OSError:
            # Unreadable/unwritable lock file: cannot prove it is free, so do not.
            return True
    return False


def qualified_java_identity(authority: dict) -> dict:
    """Which JVM ran, by path and content digest."""
    runtime = resolve_qualified_runtime(authority)
    executable = Path(runtime["java_executable"])
    version = subprocess.run([str(executable), "-version"], text=True,
                             capture_output=True, check=False)
    return {"path": str(executable), "sha256": sha256_file(executable),
            "version_line": (version.stderr or version.stdout).splitlines()[0]
            if (version.stderr or version.stdout) else None}


def operational_startup_smoke(output: Path, *, stage: str = "stage1-capture",
                              manifest_path: Path | None = None) -> int:
    """Start the real apparatus, cross the capture contract, tear it down.

    Deliberately captures no frame, and now goes as far as the server: the
    previous version stopped at ``capture_context``, which proved only that the
    Python side of the v0.2 -> v0.1 interface holds. It never issued a
    ``startspec``, so the server never saw an episode identity, never loaded a
    schedule, and never checked the schedule header seed against the episode
    seed -- and a spec whose two seed fields disagreed passed this control and
    was first refused by a real Stage-1 launch.

    ``CaptureSession.arm_only`` closes that: schedule materialization, the same
    startspec line production sends, schedule load, seed verification and arming,
    then stop. Arming is strictly before ``beginCapture()``, so no pixel is ever
    read; the handshake record asserts that absence rather than assuming it.
    """
    # Which stage's units this smoke exercises. Stage 2 runs its own captures
    # under its own namespace, and ``require_preoutcome_provenance`` checks the
    # embedded smoke against the namespace of whichever manifest is being
    # authorized -- so a Stage-1 smoke cannot stand in for a Stage-2 one, and
    # the smoke has to be able to name the stage it ran for.
    manifest_path = STAGE1_MANIFEST_PATH if manifest_path is None else manifest_path
    authority = load_json(AUTHORITY_PATH)
    manifest = load_json(manifest_path)
    require_stage_manifest_binding(stage, manifest, manifest_path=manifest_path,
                                   authority=authority)
    namespace = operational_smoke_namespace(str(manifest["run_namespace"]))

    toolchain = capture_toolchain_evidence()
    require_capture_toolchain(toolchain)
    contract = capture_contract_preflight(manifest, authority)

    # Unit-shaped, never a unit: the identity is rewritten into the smoke
    # namespace so this spec cannot collide with, or stand in for, a real unit.
    template = dict(manifest["units"][0])
    template["unit_id"] = f"smoke_{template['unit_id']}"
    template["scientific_run_id"] = namespace
    template["episode_id"] = int(authority["apparatus"].get(
        "operational_smoke_episode_id", 990001))
    spec = derive_effective_capture_spec(template, authority)
    require_capture_spec_contract(spec)

    # D4. The display is NOT pre-created here. ``ensure_display`` starts the
    # generic renderer-probe display -- authority pin "0 1280x720x24" -- and the
    # production start_display path then early-returns, because its first act is
    #     if DISPLAY="$display" xdpyinfo >/dev/null 2>&1; then ... return
    # So pre-creating :99 meant the smoke never started the real 640x360x24
    # capture Xvfb and never started openbox: it proved a display existed, not
    # that the production display path works. launch_runtime owns the display
    # now, and a pre-existing display is refused rather than reused.
    display = authority["runtime_identity_policy"]["runtime_reconstruction"]["display"]
    require_no_pre_existing_display(display)

    stages: dict[str, dict] = {}
    launched: list[dict] = []
    handles: list = []
    stranded: list[int] = []
    display_evidence: dict = {"name": display, "geometry": CAPTURE_DISPLAY_GEOMETRY,
                              "started_by_smoke": False}
    openbox_evidence: dict = {"started_by_smoke": False}
    contract_crossed = False
    handshake: dict = {}
    failure: str | None = None
    started = time.monotonic()

    try:
        sys.path.insert(0, str(ROOT / "scripts/regime_a_prime_qualification_v0_1"))
        from p2_common import CaptureSession, capture_context

        session = CaptureSession("normal")
        with session:
            # Reaching here means the production start-display, start-server and
            # start-client path all completed: the client join is what the frozen
            # launch precheck blocks on.
            display_evidence = probe_capture_display(display, started)
            openbox_evidence = probe_openbox(display, started)
            stages["display_ready"] = display_evidence.pop("stage_evidence")
            stages["server_ready"] = log_stage_evidence(
                session.live.SERVER_ROOT / "logs/latest.log", "server ready", started)
            # Read from the *server* log, which is where the join is recorded and
            # exactly what launch_runtime blocks on. "joined the game" is a
            # server-side message; the client never prints it, so sourcing this
            # from the client log could not be satisfied by a client that had in
            # fact joined -- a real, fully successful startup still failed here.
            stages["client_joined"] = log_stage_evidence(
                session.live.SERVER_ROOT / "logs/latest.log", "joined the game", started)
            # Keep our own handles: __exit__ hands its process list to the
            # teardown and clears session.processes, so reading that attribute
            # afterwards yields an empty list. Zipping against it silently
            # iterated nothing, every record kept exited=False, and a perfectly
            # clean teardown was reported as having stranded all three.
            handles = list(session.processes)
            launched = [{"pid": process.pid, "role": role, "exited": False}
                        for role, process in zip(("display", "server", "client"),
                                                 handles)]
            # The exact call that used to raise KeyError: 'spec_hash'.
            context = capture_context(spec, int(spec["episode_id"]),
                                      session.live.SERVER_ROOT)
            contract_crossed = bool(context["frames"]) and "schedule" in context

            # Now the half the old smoke never reached: hand the identity to the
            # server and require it to accept the schedule against the episode
            # seed. Stops at armed -- strictly before the first captured frame.
            handshake = {"schema": OPERATIONAL_SMOKE_HANDSHAKE_SCHEMA,
                         **session.arm_only(spec, int(spec["episode_id"]))}
            # Sourced at the server log the line was read from, like the other
            # stages, so the record names where the claim can be checked.
            stages["episode_armed"] = stage_evidence(
                session.live.SERVER_ROOT / "logs/latest.log",
                (handshake.get("armed_log_line") or "") + "\n", started)

        # After __exit__: every process the smoke started must be gone.
        for record, process in zip(launched, handles):
            record["exited"] = process.poll() is not None
        stranded = [record["pid"] for record in launched if not record["exited"]]
        stages["teardown"] = teardown_stage_evidence(launched, stranded, started)
    except BaseException as exc:  # noqa: BLE001 - recorded, then reported
        failure = f"{type(exc).__name__}: {exc}"

    smoke = {
        "schema": OPERATIONAL_SMOKE_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "artifact_id": OPERATIONAL_SMOKE_ARTIFACT_ID,
        "classification": OPERATIONAL_SMOKE_CLASSIFICATION,
        "run_namespace": namespace,
        "smoke_for_stage": stage,
        "smoke_for_manifest_sha256": sha256_file(manifest_path),
        "scientific_evidence": False,
        "counts_toward_stage1_units": False,
        "generated_at_utc": generation_time(),
        "generated_by": GENERATED_BY,
        "source_commit": git("rev-parse", "HEAD"),
        "runtime_critical_source_closure_sha256": runtime_critical_source_closure_sha256(ROOT),
        "java_executable": qualified_java_identity(authority),
        "display": display_evidence,
        "openbox": openbox_evidence,
        "stage_evidence": stages,
        "launched_processes": launched,
        "stranded_processes": stranded,
        "session_lock_present_after_teardown": world_session_lock_present(),
        "capture_toolchain": toolchain,
        "capture_contract_preflight": contract,
        "smoke_capture_spec_sha256": spec["spec_hash"],
        "capture_contract_crossed": contract_crossed,
        "startspec_handshake": handshake,
        # Verified as counts by require_operational_smoke; a smoke that captured
        # anything is refused rather than relabelled.
        "frames_captured": 0,
        "scientific_receipts_written": 0,
        "stage1_durable_objects_written": 0,
        "failure": failure,
    }
    smoke["status"] = "PASS" if (contract_crossed and not stranded and failure is None
                                 and set(stages) == {"display_ready", "server_ready",
                                                     "client_joined", "episode_armed",
                                                     "teardown"}) else "FAIL"
    smoke["payload_sha256"] = canonical_payload_sha256(smoke, omit="payload_sha256")

    # Reproduce, do not trust: the document must satisfy the same verifier the
    # launch gate will run, so a smoke that cannot authorize is never written PASS.
    if smoke["status"] == "PASS":
        try:
            require_operational_smoke(
                smoke, run_namespace=str(manifest["run_namespace"]),
                source_commit=smoke["source_commit"],
                closure_sha256=smoke["runtime_critical_source_closure_sha256"])
        except EvidenceError as exc:
            smoke["status"] = "FAIL"
            smoke["failure"] = f"self-verification rejected the smoke: {exc}"
            smoke["payload_sha256"] = canonical_payload_sha256(smoke, omit="payload_sha256")

    atomic_write_json(output, smoke)
    print(f"OPERATIONAL_SMOKE_STATUS={smoke['status']}")
    print(f"SMOKE_SERVER_START={'server_ready' in stages}")
    print(f"SMOKE_CLIENT_JOIN={'client_joined' in stages}")
    print(f"SMOKE_CAPTURE_INTERFACE={contract_crossed}")
    print(f"SMOKE_DISPLAY_OWNER={'smoke' if display_evidence.get('started_by_smoke') else 'none'}")
    print(f"SMOKE_DISPLAY_GEOMETRY={display_evidence.get('geometry')}")
    print(f"SMOKE_OPENBOX_STARTED={openbox_evidence.get('started_by_smoke')}")
    print(f"SMOKE_CLEANUP={not stranded}")
    print("SMOKE_FRAMES_CAPTURED=0")
    print("SMOKE_SCIENTIFIC_RECEIPTS=0")
    print("SMOKE_STAGE1_DURABLE_OBJECTS=0")
    if smoke["failure"]:
        print(f"SMOKE_FAILURE={smoke['failure']}")
    return 0 if smoke["status"] == "PASS" else 2


def build_provenance(probe_evidence_path: Path, output: Path, *,
                     freeze_commit: str | None, durable_probe: bool,
                     smoke_path: Path, stage: str = "stage1-capture",
                     manifest_path: Path | None = None,
                     extra_bindings: dict | None = None) -> int:
    """Write the pre-outcome provenance receipt for one stage of this package.

    ``stage`` and ``manifest_path`` default to Stage 1, which is the only stage
    that existed when this generator was written. Stage 2 reuses every control
    here unchanged -- the runtime and apparatus identity probes, the source
    closure, the two-step commit binding, the capture toolchain, the capture
    contract preflight and the operational smoke -- and differs only in which
    manifest those controls are applied to. Parameterising is therefore what
    keeps the Stage-2 receipt as strong as the Stage-1 one instead of a second,
    weaker generator that happens to emit the same field names.
    """
    manifest_path = STAGE1_MANIFEST_PATH if manifest_path is None else manifest_path
    authority = load_json(AUTHORITY_PATH)
    manifest = load_json(manifest_path)
    binding = require_stage_manifest_binding(stage, manifest,
        manifest_path=manifest_path, authority=authority)
    if (authority.get("prospective_source_commit_binding") != RUNTIME_POLICY
            or manifest.get("source_commit_binding") != RUNTIME_POLICY):
        raise EvidenceError("authority/manifest runtime source-commit policy mismatch")

    receipt = load_json(probe_evidence_path)
    # Every identity boolean below is the outcome of running the verifier that
    # establishes it. None of them is written unless its verifier returned.
    runtime_identity = verify_runtime_identity(authority["runtime_identity_policy"], receipt)
    probe = verify_probe_execution(receipt, "runtime_provenance_receipt", authority=authority)
    verify_runtime_source_hashes(receipt["probe_execution"]["runtime_source_sha256"])
    execution = receipt["probe_execution"]
    by_id = {item["command_id"]: item for item in execution["invocations"]}

    durable = ({"verified": False, "reason": "durable round-trip probe was not executed"}
               if not durable_probe else durable_round_trip(manifest["durable_prefix"]))

    # Capture-path runnability. Re-derived here rather than copied from the smoke
    # artifact, so a stale smoke cannot carry a toolchain that no longer resolves.
    capture_toolchain = capture_toolchain_evidence()
    require_capture_toolchain(capture_toolchain)
    contract_preflight = capture_contract_preflight(manifest, authority)
    smoke = load_json(smoke_path)
    require_operational_smoke(smoke, run_namespace=str(manifest["run_namespace"]),
                              source_commit=git("rev-parse", "HEAD"))
    if smoke.get("capture_contract_preflight", {}).get("capture_spec_sha256_by_unit") != \
            contract_preflight["capture_spec_sha256_by_unit"]:
        raise EvidenceError("operational smoke preflight does not match current manifest")

    closure = runtime_critical_source_closure_sha256()
    source_bindings = {relative: {"sha256": sha256_file(ROOT / relative)}
                       for relative in RUNTIME_CRITICAL_SOURCE_PATHS}
    head = git("rev-parse", "HEAD")

    if freeze_commit is None:
        # Step 1 of the two-step commit binding. The commit that will carry these
        # bytes does not exist yet, so no commit is claimed and the launch gate
        # refuses this receipt by status.
        status = "PRE_FREEZE_VERIFIED"
        commit_state = {"source_commit_binding_state": "AWAITING_FREEZE",
                        "source_commit": None,
                        "reviewed_runtime_critical_source_closure_sha256": closure,
                        "post_freeze_verification_command":
                            f"python3 {GENERATED_BY} "
                            "provenance --probe-evidence <probe.json> --output <receipt.json> "
                            "--freeze-commit <commit-sha>"}
    else:
        # Step 3. The committed tree must reproduce the reviewed bytes exactly,
        # so the freeze cannot quietly differ from what was verified.
        dirty = git("status", "--porcelain=v1", "--untracked-files=all")
        if dirty:
            raise EvidenceError(
                "post-freeze provenance requires a completely clean repository")
        critical = [CriticalSource(relative, binding_value["sha256"])
                    for relative, binding_value in source_bindings.items()]
        result = verify_sources(ROOT, critical, expected_head=freeze_commit)
        if not result.verified:
            raise EvidenceError("post-freeze source provenance failed: "
                                + "; ".join(result.violations))
        modes = {record["relative_path"]: record.get("tree_mode") for record in result.sources}
        for relative in source_bindings:
            source_bindings[relative]["git_mode"] = modes.get(relative)
        status = "FROZEN_VERIFIED"
        commit_state = {"source_commit_binding_state": "BOUND_TO_FROZEN_COMMIT",
                        "source_commit": freeze_commit,
                        "reviewed_runtime_critical_source_closure_sha256": closure,
                        "committed_bytes_equal_reviewed_bytes": True,
                        "repository_clean_at_post_freeze_verification": True}

    provenance = {
        "schema_version": SCHEMA_VERSION, "artifact_id": PROVENANCE_ARTIFACT_ID,
        "classification": "DEVELOPMENT_ONLY", "status": status,
        "generated_at_utc": generation_time(),
        "generated_by": GENERATED_BY,
        "authority_sha256": sha256_file(AUTHORITY_PATH),
        # ``manifest_sha256`` is the manifest this receipt authorizes -- Stage 1's
        # or Stage 2's. ``stage1_manifest_sha256`` always names the Stage-1
        # manifest, so a Stage-2 receipt still carries the identity of the
        # qualification that preceded it.
        "manifest_sha256": sha256_file(manifest_path),
        "stage1_manifest_sha256": sha256_file(STAGE1_MANIFEST_PATH),
        "stage": binding["stage"], "stage_role": binding["stage_role"],
        "run_namespace": binding["run_namespace"],
        "run_inventory_sha256": stage_run_inventory_sha256(manifest),
        # Derived, not declared: each is the verifier's own return value.
        "runtime_identity_verified": runtime_identity["status"] == "PASS",
        "apparatus_identity_verified": set(execution["apparatus_file_sha256"]) == set(
            authority["runtime_identity_policy"]["critical_file_sha256"]),
        "renderer_identity_verified": by_id["renderer"]["exit_status"] == 0,
        "source_paths_verified_bytes_and_modes": freeze_commit is not None,
        "remote_durable_prefix_read_write_probe_verified": durable["verified"],
        "durable_probe": durable,
        "probe_evidence_sha256": probe["probe_evidence_sha256"],
        "probe_evidence_path_sha256": sha256_file(probe_evidence_path),
        # Preserve the concrete independent record so downstream authorization
        # and launch gates can replay its evidence instead of trusting these
        # summary booleans or a copied digest.
        "probe_evidence": receipt,
        "probe_producer": probe["producer"],
        "probe_invocations_verified": probe["invocations_verified"],
        # Runnability of the capture path, which identity probing cannot show.
        "capture_toolchain": capture_toolchain,
        "capture_contract_preflight": contract_preflight,
        "operational_startup_smoke": smoke,
        "runtime_critical_source_closure_sha256": closure,
        "source_bindings": source_bindings,
        "minecraft_server_jar_sha256":
            execution["apparatus_file_sha256"]["minecraft_server_jar"],
        "fabric_server_launcher_jar_sha256":
            execution["apparatus_file_sha256"]["fabric_server_launcher_jar"],
        "installed_mod_sha256": execution["apparatus_file_sha256"]["installed_mod"],
        "java_identity": receipt["java"], "java_home": execution["java_home"],
        "renderer_identity": receipt["renderer"], "mesa_identity": receipt["mesa"],
        "xvfb_identity": receipt["xvfb"], "display": execution["display"],
        "detector_config_id": receipt["detector_config_id"],
        "minecraft_version": receipt["minecraft_version"],
        "repository_head_at_generation": head,
        "independently_derived": True,
        "scientific_outcomes_observed": False,
        "minecraft_started_by_receipt_generation": False,
        "STAGE_1_COLLECTION_AUTHORIZED": False,
        "STAGE_2_COLLECTION_AUTHORIZED": False,
        "REGIME_A_PRIME_COLLECTION_AUTHORIZED": "NO",
        "confirmatory_collection_authorized": False,
        "confirmatory_interpretation_authorized": False,
        **(extra_bindings or {}),
        **commit_state,
    }
    provenance["payload_sha256"] = canonical_payload_sha256(provenance)
    atomic_write_json(output, provenance)
    print(f"PROVENANCE_RECEIPT_STATUS={status}")
    print(f"PROVENANCE_RECEIPT_SHA256={sha256_file(output)}")
    print(f"DURABLE_PROBE_VERIFIED={durable['verified']}")
    return 0


# ---------------------------------------------------------------- Stage 2
#
# Stage 2 is the first rung that reads model activations, and it is reachable
# only through ``require_stage2_authorization``. That barrier already existed;
# what did not exist was any legitimate way to produce an artifact it accepts,
# so the only route to a Stage-2 launch was hand-authoring the receipt -- which
# is exactly the failure mode every other receipt in this module was written to
# remove. The two generators below close that gap without touching the barrier.
#
# Neither one authorizes anything by itself. ``stage2-provenance`` runs the same
# controls Stage 1 runs, against the Stage-2 manifest. ``stage2-authorization``
# consumes that receipt plus the frozen Stage-1 PASS, and its last act is to run
# the real barrier over what it just wrote: if the barrier refuses, the file is
# removed and nothing is authorized.


def stage1_pass_bindings(stage1_decision_path: Path, stage1_evidence_path: Path,
                         stage1_provenance_path: Path) -> dict:
    """Verify the frozen Stage-1 PASS and return what a Stage-2 receipt binds to it.

    The decision is not read for its ``status`` field. It is *re-derived*: the
    bound evidence is re-evaluated through ``Stage1Evaluator`` and the result
    must equal the decision byte for byte, which is the same reproduction the
    Stage-2 barrier performs. A decision with a gate flipped to PASS, a wrong
    evidence digest, a wrong artifact identity or a foreign version therefore
    fails here, at production time, rather than surviving into a receipt that
    the barrier then rejects at launch.

    ``stage1_provenance_path`` is that completed campaign's own frozen
    pre-outcome provenance receipt, and it is what the re-derivation verifies
    the evidence's source pins against. The Stage-1 campaign ran at its own
    freeze; by the time Stage 2 is being prepared the working tree has
    necessarily moved on -- Stage-2 preparation edits the runtime-critical
    closure itself -- so the tree can neither confirm nor refute what Stage 1
    ran. The campaign's frozen receipt can, and is the only artifact that may.
    The Stage-2 source is a separate binding, verified against the live closure
    where this generator's own provenance is produced and checked.
    """
    authority = load_json(AUTHORITY_PATH)
    stage1_manifest = load_json(STAGE1_MANIFEST_PATH)
    decision = load_json(stage1_decision_path)
    decision_sha = sha256_file(stage1_decision_path)
    evidence_sha = sha256_file(stage1_evidence_path)
    provenance_sha = sha256_file(stage1_provenance_path)

    # The historical source authority. Its identity is resolved from the
    # Stage-1 manifest's own version tag, so a predecessor package's receipt --
    # frozen, valid, and about a different experiment -- cannot supply it.
    historical_closure = bind_historical_source_closure(
        load_json(stage1_provenance_path), provenance_sha256=provenance_sha,
        expected_artifact_id=provenance_artifact_id_for(
            artifact_version_tag(stage1_manifest.get("artifact_id"))),
        authority_sha256=sha256_file(AUTHORITY_PATH),
        manifest_sha256=sha256_file(STAGE1_MANIFEST_PATH))

    expected_decision_id = stage1_decision_artifact_id(stage1_manifest)
    if decision.get("artifact_id") != expected_decision_id:
        raise EvidenceError(
            f"Stage-1 decision is {decision.get('artifact_id')!r}, "
            f"but this package requires {expected_decision_id!r}")
    if decision.get("status") != "PASS":
        raise EvidenceError("Stage-2 requires a Stage-1 PASS decision")
    if decision.get("stage1_evidence_sha256") != evidence_sha:
        raise EvidenceError("Stage-1 decision does not bind the supplied evidence")
    authority_sha = sha256_file(AUTHORITY_PATH)
    stage1_manifest_sha = sha256_file(STAGE1_MANIFEST_PATH)
    if (decision.get("authority_sha256") != authority_sha
            or decision.get("stage1_manifest_sha256") != stage1_manifest_sha):
        raise EvidenceError("Stage-1 decision binding mismatch")
    try:
        reproduced = Stage1Evaluator(
            authority, stage1_manifest, authority_sha256=authority_sha,
            manifest_sha256=stage1_manifest_sha,
            historical_source_closure=historical_closure).evaluate(
                load_json(stage1_evidence_path)).to_dict(
                    authority_sha256=authority_sha, manifest_sha256=stage1_manifest_sha,
                    evidence_sha256=evidence_sha, artifact_id=expected_decision_id)
    except (EvidenceError, KeyError, TypeError, ValueError) as exc:
        raise EvidenceError("Stage-1 evidence cannot reproduce its decision") from exc
    if reproduced != decision:
        raise EvidenceError("Stage-1 decision is not reproduced from its bound evidence")
    return {"stage1_decision_sha256": decision_sha,
            "stage1_evidence_sha256": evidence_sha,
            "stage1_decision_artifact_id": expected_decision_id,
            "stage1_status": "PASS",
            "stage1_decision_reproduced_from_evidence": True,
            "stage1_preoutcome_provenance_receipt_sha256": provenance_sha,
            "stage1_source_commit": historical_closure.source_commit,
            "stage1_runtime_critical_source_closure_sha256": historical_closure.closure_sha256}


def stage2_manifest_bindings() -> dict:
    """The materialized Stage-2 design, re-derived rather than restated.

    Every value returned is read out of the frozen authority or the materialized
    manifest and checked against the other, so a receipt cannot claim a design
    the package does not actually carry -- a different layer, an extra capture,
    an escalated classification.
    """
    authority = load_json(AUTHORITY_PATH)
    manifest = load_json(STAGE2_MANIFEST_PATH)
    policy = authority["stage2_policy"]
    if manifest.get("status") != "POST_STAGE1_MATERIALIZED_AWAITING_SEPARATE_FREEZE_AND_AUTHORIZATION":
        raise EvidenceError(
            f"Stage-2 manifest is not materialized: {manifest.get('status')!r}")
    validate_stage2_manifest_design(authority, manifest, require_materialized=True)

    layers = sorted({unit["layer"] for unit in manifest["extraction_units"]})
    if layers != list(policy["extraction"]["layers"]) or layers != [4]:
        raise EvidenceError(f"Stage-2 extraction layers are {layers}, not the frozen [4]")
    if policy["extraction"].get("all_layer_extraction_forbidden") is not True:
        raise EvidenceError("frozen authority does not forbid all-layer extraction")
    if policy["post_stage2"].get("confirmatory_reuse_forbidden") is not True:
        raise EvidenceError("frozen authority does not forbid confirmatory reuse")
    if (manifest.get("classification") != "DEVELOPMENT_ONLY"
            or manifest.get("STAGE_2_COLLECTION_AUTHORIZED") is not False
            or manifest.get("confirmatory_collection_authorized") is not False):
        raise EvidenceError("Stage-2 manifest does not carry the development-only baseline")
    return {
        "stage2_manifest_sha256": sha256_file(STAGE2_MANIFEST_PATH),
        "stage2_manifest_artifact_id": manifest["artifact_id"],
        "stage2_run_inventory_sha256": stage_run_inventory_sha256(manifest),
        "stage2_run_namespace": manifest["run_namespace"],
        "stage2_durable_prefix": manifest["durable_prefix"],
        "stage2_scientific_capture_count": len(manifest["capture_units"]),
        "stage2_trajectory_identity_count": len(manifest["trajectory_identities"]),
        "stage2_target_rows_per_capture": policy["required_target_rows_per_capture"],
        "stage2_outer_folds": policy["outer_folds"],
        "stage2_phase_offsets_frames": list(policy["phase_offsets_frames"]),
        "stage2_extraction_layers": layers,
        "stage2_capture_unit_ids": sorted(
            str(unit["unit_id"]) for unit in manifest["capture_units"]),
        "stage2_temporal_label_source": policy["temporal_labels"]["source"],
        "all_layer_extraction_forbidden": True,
        "confirmatory_reuse_forbidden": True,
        "development_qualification_only": True,
    }


def build_stage2_provenance(probe_evidence_path: Path, output: Path, *,
                            freeze_commit: str | None, durable_probe: bool,
                            smoke_path: Path, stage1_decision_path: Path,
                            stage1_evidence_path: Path,
                            stage1_provenance_path: Path) -> int:
    """Pre-outcome provenance for Stage 2: Stage-1's controls, Stage-2's manifest.

    Two source identities are recorded and neither substitutes for the other.
    ``build_provenance`` verifies and pins the *current* runtime-critical
    closure -- the Stage-2 apparatus about to run, rehashed from the working
    tree. ``stage1_pass_bindings`` verifies and pins the *historical* closure
    the reused Stage-1 PASS was collected under, taken from that campaign's own
    frozen receipt.
    """
    bindings = {**stage1_pass_bindings(stage1_decision_path, stage1_evidence_path,
                                       stage1_provenance_path),
                **stage2_manifest_bindings()}
    return build_provenance(probe_evidence_path, output, freeze_commit=freeze_commit,
                            durable_probe=durable_probe, smoke_path=smoke_path,
                            stage="stage2-capture", manifest_path=STAGE2_MANIFEST_PATH,
                            extra_bindings=bindings)


def build_stage2_authorization(provenance_path: Path, output: Path, *,
                               stage1_decision_path: Path,
                               stage1_evidence_path: Path,
                               stage1_provenance_path: Path) -> int:
    """Derive the post-Stage-1 Stage-2 authorization from verified prerequisites only.

    The field set is not invented here. ``require_stage2_authorization`` names
    every binding it compares, and this generator computes exactly those from
    the artifacts they name. The last step runs that barrier over the finished
    document: an artifact this generator cannot get past the real gate is
    deleted rather than written, so the generator can never be the reason a
    launch succeeds.
    """
    authority = load_json(AUTHORITY_PATH)
    manifest = load_json(STAGE2_MANIFEST_PATH)
    binding = require_stage_manifest_binding("stage2-capture", manifest,
        manifest_path=STAGE2_MANIFEST_PATH, authority=authority)
    stage1 = stage1_pass_bindings(stage1_decision_path, stage1_evidence_path,
                                  stage1_provenance_path)
    design = stage2_manifest_bindings()
    provenance = load_json(provenance_path)
    head = git("rev-parse", "HEAD")

    # The controlling preconditions, reproduced rather than assumed -- the same
    # treatment ``build_stage1_authorization`` gives its own provenance, applied
    # to the Stage-2 manifest and namespace.
    required = {
        "artifact_id": PROVENANCE_ARTIFACT_ID,
        "status": "FROZEN_VERIFIED",
        "authority_sha256": sha256_file(AUTHORITY_PATH),
        "manifest_sha256": design["stage2_manifest_sha256"],
        "stage1_manifest_sha256": sha256_file(STAGE1_MANIFEST_PATH),
        "stage": binding["stage"],
        "stage_role": binding["stage_role"],
        "run_namespace": binding["run_namespace"],
        "run_inventory_sha256": design["stage2_run_inventory_sha256"],
        "runtime_critical_source_closure_sha256": runtime_critical_source_closure_sha256(),
        "runtime_identity_verified": True,
        "apparatus_identity_verified": True,
        "renderer_identity_verified": True,
        "source_paths_verified_bytes_and_modes": True,
        "remote_durable_prefix_read_write_probe_verified": True,
        "scientific_outcomes_observed": False,
        "confirmatory_collection_authorized": False,
        "source_commit_binding_state": "BOUND_TO_FROZEN_COMMIT",
        "source_commit": head,
        "repository_clean_at_post_freeze_verification": True,
        # The Stage-2 receipt must be the Stage-2 receipt: a Stage-1 provenance
        # carries the Stage-1 manifest digest and namespace above, and is refused
        # there, but these make the substitution explicit rather than incidental.
        "stage1_decision_sha256": stage1["stage1_decision_sha256"],
        "stage1_evidence_sha256": stage1["stage1_evidence_sha256"],
        "stage2_manifest_sha256": design["stage2_manifest_sha256"],
        "stage2_run_inventory_sha256": design["stage2_run_inventory_sha256"],
        # The Stage-2 provenance must name the same Stage-1 campaign this
        # authorization reuses, so the historical source authority cannot be
        # swapped between the two receipts.
        "stage1_preoutcome_provenance_receipt_sha256":
            stage1["stage1_preoutcome_provenance_receipt_sha256"],
        "all_layer_extraction_forbidden": True,
    }
    unmet = {key: {"required": value, "observed": provenance.get(key)}
             for key, value in required.items() if provenance.get(key) != value}
    if unmet:
        raise EvidenceError(f"Stage-2 authorization prerequisites are unmet: {unmet}")
    if provenance.get("payload_sha256") != canonical_payload_sha256(
            provenance, omit="payload_sha256"):
        raise EvidenceError("pre-outcome provenance payload digest mismatch")
    probe_evidence = provenance.get("probe_evidence")
    if not isinstance(probe_evidence, dict):
        raise EvidenceError("pre-outcome provenance has no concrete probe evidence")
    runtime_result = verify_runtime_identity(
        authority["runtime_identity_policy"], probe_evidence)
    probe_result = verify_probe_execution(
        probe_evidence, "embedded pre-outcome probe evidence", authority=authority)
    embedded_file_sha = hashlib.sha256(canonical_json_bytes(probe_evidence)).hexdigest()
    if (runtime_result.get("status") != "PASS"
            or probe_result.get("probe_evidence_sha256") != provenance.get("probe_evidence_sha256")
            or embedded_file_sha != provenance.get("probe_evidence_path_sha256")):
        raise EvidenceError("pre-outcome concrete probe binding mismatch")
    if git("status", "--porcelain=v1", "--untracked-files=all"):
        raise EvidenceError("Stage-2 authorization requires a clean frozen repository")
    if authority.get("STAGE_2_COLLECTION_AUTHORIZED") is not False:
        raise EvidenceError("frozen authority does not carry the unauthorized collection baseline")

    authorization = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": binding["authorization_artifact_id"],
        "classification": "DEVELOPMENT_ONLY",
        "status": "FROZEN_AUTHORIZED",
        "generated_at_utc": generation_time(),
        "generated_by": GENERATED_BY,
        "authority_sha256": required["authority_sha256"],
        "stage1_manifest_sha256": required["stage1_manifest_sha256"],
        "stage1_decision_sha256": stage1["stage1_decision_sha256"],
        "stage1_evidence_sha256": stage1["stage1_evidence_sha256"],
        "stage1_decision_artifact_id": stage1["stage1_decision_artifact_id"],
        "stage1_status": "PASS",
        "stage2_manifest_sha256": design["stage2_manifest_sha256"],
        "authorized_stage": binding["stage"],
        "stage_role": binding["stage_role"],
        "expected_run_namespace": binding["run_namespace"],
        "runtime_critical_source_closure_sha256":
            required["runtime_critical_source_closure_sha256"],
        "preoutcome_provenance_receipt_sha256": sha256_file(provenance_path),
        # The historical Stage-1 source authority, kept distinct from the
        # current Stage-2 closure pinned above.
        "stage1_preoutcome_provenance_receipt_sha256":
            stage1["stage1_preoutcome_provenance_receipt_sha256"],
        "stage1_source_commit": stage1["stage1_source_commit"],
        "stage1_runtime_critical_source_closure_sha256":
            stage1["stage1_runtime_critical_source_closure_sha256"],
        "probe_evidence_sha256": provenance["probe_evidence_sha256"],
        "source_commit_sha": head,
        "STAGE_1_COLLECTION_AUTHORIZED": False,
        "STAGE_2_COLLECTION_AUTHORIZED": True,
        "confirmatory_collection_authorized": False,
        "confirmatory_interpretation_authorized": False,
        **{key: design[key] for key in (
            "stage2_manifest_artifact_id", "stage2_run_inventory_sha256",
            "stage2_scientific_capture_count", "stage2_trajectory_identity_count",
            "stage2_target_rows_per_capture", "stage2_outer_folds",
            "stage2_phase_offsets_frames", "stage2_extraction_layers",
            "stage2_capture_unit_ids", "stage2_temporal_label_source",
            "stage2_durable_prefix", "all_layer_extraction_forbidden",
            "confirmatory_reuse_forbidden", "development_qualification_only")},
    }
    authorization["authorization_payload_sha256"] = canonical_payload_sha256(authorization)
    atomic_write_json(output, authorization)

    # Self-check against the real barrier, not a copy of it. Anything this
    # generator produces that the launch gate would refuse is removed here.
    try:
        require_stage2_authorization(
            manifest, authorization, authorization_receipt_path=output,
            stage1_decision=load_json(stage1_decision_path),
            authority_path=AUTHORITY_PATH, manifest_path=STAGE2_MANIFEST_PATH,
            stage1_manifest_path=STAGE1_MANIFEST_PATH,
            stage1_decision_path=stage1_decision_path,
            stage1_evidence_path=stage1_evidence_path,
            current_source_commit=head, preoutcome_provenance_path=provenance_path,
            stage1_preoutcome_provenance_path=stage1_provenance_path)
    except PermissionError as exc:
        output.unlink(missing_ok=True)
        raise EvidenceError(f"generated Stage-2 authorization does not satisfy the barrier: {exc}") from exc

    print("STAGE2_AUTHORIZATION_STATUS=FROZEN_AUTHORIZED")
    print(f"STAGE2_AUTHORIZATION_SHA256={sha256_file(output)}")
    print(f"STAGE2_AUTHORIZATION_ARTIFACT_ID={authorization['artifact_id']}")
    print("STAGE_2_COLLECTION_AUTHORIZED=true")
    print("confirmatory_collection_authorized=false")
    return 0


# ---------------------------------------------------------------- authorization


def build_stage1_authorization(provenance_path: Path, output: Path) -> int:
    """Derive a Stage-1 authorization from verified prerequisites only."""
    authority = load_json(AUTHORITY_PATH)
    manifest = load_json(STAGE1_MANIFEST_PATH)
    binding = require_stage_manifest_binding("stage1-capture", manifest,
        manifest_path=STAGE1_MANIFEST_PATH, authority=authority)
    provenance = load_json(provenance_path)

    authority_sha = sha256_file(AUTHORITY_PATH)
    manifest_sha = sha256_file(STAGE1_MANIFEST_PATH)
    inventory = stage_run_inventory_sha256(manifest)
    closure = runtime_critical_source_closure_sha256()
    head = git("rev-parse", "HEAD")

    # The controlling preconditions, reproduced rather than assumed.
    required = {
        "artifact_id": PROVENANCE_ARTIFACT_ID,
        "status": "FROZEN_VERIFIED",
        "authority_sha256": authority_sha,
        "manifest_sha256": manifest_sha,
        "stage1_manifest_sha256": manifest_sha,
        "stage": binding["stage"],
        "run_namespace": binding["run_namespace"],
        "run_inventory_sha256": inventory,
        "runtime_critical_source_closure_sha256": closure,
        "runtime_identity_verified": True,
        "apparatus_identity_verified": True,
        "renderer_identity_verified": True,
        "source_paths_verified_bytes_and_modes": True,
        "remote_durable_prefix_read_write_probe_verified": True,
        "scientific_outcomes_observed": False,
        "confirmatory_collection_authorized": False,
        "source_commit_binding_state": "BOUND_TO_FROZEN_COMMIT",
        "source_commit": head,
        "repository_clean_at_post_freeze_verification": True,
    }
    unmet = {key: {"required": value, "observed": provenance.get(key)}
             for key, value in required.items() if provenance.get(key) != value}
    if unmet:
        raise EvidenceError(f"Stage-1 authorization prerequisites are unmet: {unmet}")
    if provenance.get("payload_sha256") != canonical_payload_sha256(
            provenance, omit="payload_sha256"):
        raise EvidenceError("pre-outcome provenance payload digest mismatch")
    probe_evidence = provenance.get("probe_evidence")
    if not isinstance(probe_evidence, dict):
        raise EvidenceError("pre-outcome provenance has no concrete probe evidence")
    runtime_result = verify_runtime_identity(
        authority["runtime_identity_policy"], probe_evidence)
    probe_result = verify_probe_execution(
        probe_evidence, "embedded pre-outcome probe evidence", authority=authority)
    embedded_file_sha = hashlib.sha256(
        canonical_json_bytes(probe_evidence)).hexdigest()
    if (runtime_result.get("status") != "PASS"
            or probe_result.get("probe_evidence_sha256")
               != provenance.get("probe_evidence_sha256")
            or embedded_file_sha != provenance.get("probe_evidence_path_sha256")):
        raise EvidenceError("pre-outcome concrete probe binding mismatch")
    if git("status", "--porcelain=v1", "--untracked-files=all"):
        raise EvidenceError("Stage-1 authorization requires a clean frozen repository")
    if authority.get("STAGE_1_COLLECTION_AUTHORIZED") is not False or authority.get(
            "STAGE_2_COLLECTION_AUTHORIZED") is not False:
        raise EvidenceError("frozen authority does not carry the unauthorized collection baseline")

    authorization = {
        "schema_version": SCHEMA_VERSION, "artifact_id": AUTHORIZATION_ARTIFACT_ID,
        "classification": "DEVELOPMENT_ONLY", "status": "FROZEN_AUTHORIZED",
        "generated_at_utc": generation_time(),
        "generated_by": GENERATED_BY,
        "authority_sha256": authority_sha,
        "stage1_manifest_sha256": manifest_sha,
        "authorized_stage": binding["stage"],
        "stage_role": binding["stage_role"],
        "expected_run_namespace": binding["run_namespace"],
        "stage1_run_inventory_sha256": inventory,
        "stage1_run_count": len(manifest["units"]),
        "runtime_critical_source_closure_sha256": closure,
        "preoutcome_provenance_receipt_sha256": sha256_file(provenance_path),
        "probe_evidence_sha256": provenance["probe_evidence_sha256"],
        "source_commit_sha": head,
        "STAGE_1_COLLECTION_AUTHORIZED": True,
        "STAGE_2_COLLECTION_AUTHORIZED": False,
        "confirmatory_collection_authorized": False,
        "confirmatory_interpretation_authorized": False,
    }
    authorization["authorization_payload_sha256"] = canonical_payload_sha256(authorization)
    atomic_write_json(output, authorization)
    print("STAGE1_AUTHORIZATION_STATUS=FROZEN_AUTHORIZED")
    print(f"STAGE1_AUTHORIZATION_SHA256={sha256_file(output)}")
    print("STAGE_2_COLLECTION_AUTHORIZED=false")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    preflight = sub.add_parser("runtime-preflight")
    preflight.add_argument("--output", type=Path, required=True)
    smoke = sub.add_parser("operational-smoke",
                           help="non-scientific apparatus startup smoke; captures no frame")
    smoke.add_argument("--output", type=Path, required=True)
    smoke.add_argument("--stage", default="stage1-capture",
                       choices=("stage1-capture", "stage2-capture"),
                       help="which stage's manifest and namespace the smoke runs for")
    provenance = sub.add_parser("provenance")
    provenance.add_argument("--probe-evidence", type=Path, required=True)
    provenance.add_argument("--output", type=Path, required=True)
    provenance.add_argument("--freeze-commit")
    provenance.add_argument("--durable-probe", action="store_true",
                            help="execute the real durable-prefix round trip")
    provenance.add_argument("--operational-smoke", type=Path, required=True,
                            help="passing NON_SCIENTIFIC_OPERATIONAL_SMOKE artifact")
    authorize = sub.add_parser("stage1-authorization")
    authorize.add_argument("--provenance", type=Path, required=True)
    authorize.add_argument("--output", type=Path, required=True)
    stage2_provenance = sub.add_parser(
        "stage2-provenance",
        help="pre-outcome provenance bound to the materialized Stage-2 manifest")
    stage2_provenance.add_argument("--probe-evidence", type=Path, required=True)
    stage2_provenance.add_argument("--output", type=Path, required=True)
    stage2_provenance.add_argument("--freeze-commit")
    stage2_provenance.add_argument("--durable-probe", action="store_true",
                                   help="execute the real durable-prefix round trip")
    stage2_provenance.add_argument("--operational-smoke", type=Path, required=True,
                                   help="passing Stage-2 NON_SCIENTIFIC_OPERATIONAL_SMOKE artifact")
    stage2_provenance.add_argument("--stage1-decision", type=Path, required=True)
    stage2_provenance.add_argument("--stage1-evidence", type=Path, required=True)
    stage2_provenance.add_argument(
        "--stage1-provenance", type=Path, required=True,
        help="the Stage-1 campaign's own frozen pre-outcome provenance receipt, "
             "which is the authority for the source that campaign ran")
    stage2_authorize = sub.add_parser(
        "stage2-authorization",
        help="post-Stage-1 Stage-2 authorization; refused unless the real barrier accepts it")
    stage2_authorize.add_argument("--provenance", type=Path, required=True)
    stage2_authorize.add_argument("--stage1-decision", type=Path, required=True)
    stage2_authorize.add_argument("--stage1-evidence", type=Path, required=True)
    stage2_authorize.add_argument(
        "--stage1-provenance", type=Path, required=True,
        help="the Stage-1 campaign's own frozen pre-outcome provenance receipt, "
             "which is the authority for the source that campaign ran")
    stage2_authorize.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "runtime-preflight":
        return runtime_preflight(args.output)
    if args.command == "operational-smoke":
        manifest_path = (STAGE2_MANIFEST_PATH if args.stage == "stage2-capture"
                         else STAGE1_MANIFEST_PATH)
        return operational_startup_smoke(args.output, stage=args.stage,
                                         manifest_path=manifest_path)
    if args.command == "provenance":
        return build_provenance(args.probe_evidence, args.output,
                                freeze_commit=args.freeze_commit,
                                durable_probe=args.durable_probe,
                                smoke_path=args.operational_smoke)
    if args.command == "stage2-provenance":
        return build_stage2_provenance(args.probe_evidence, args.output,
                                       freeze_commit=args.freeze_commit,
                                       durable_probe=args.durable_probe,
                                       smoke_path=args.operational_smoke,
                                       stage1_decision_path=args.stage1_decision,
                                       stage1_evidence_path=args.stage1_evidence,
                                       stage1_provenance_path=args.stage1_provenance)
    if args.command == "stage2-authorization":
        return build_stage2_authorization(args.provenance, args.output,
                                          stage1_decision_path=args.stage1_decision,
                                          stage1_evidence_path=args.stage1_evidence,
                                          stage1_provenance_path=args.stage1_provenance)
    return build_stage1_authorization(args.provenance, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
