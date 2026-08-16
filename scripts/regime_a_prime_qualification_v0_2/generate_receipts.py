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
    RUNTIME_CRITICAL_SOURCE_PATHS, EvidenceError, atomic_write_json,
    canonical_json_bytes, canonical_payload_sha256, load_json,
    require_stage_manifest_binding, resolve_qualified_runtime,
    runtime_critical_source_closure_sha256, sha256_file, stage_run_inventory_sha256,
    verify_probe_execution, verify_runtime_identity, verify_runtime_source_hashes,
)
from mineocclude.prospective.source_provenance import CriticalSource, verify_sources  # noqa: E402

PACKAGE = (ROOT / "docs/status/integration/regime_a_prime_qualification_v0_1"
           / "prospective_development_authority_v0_2")
AUTHORITY_PATH = PACKAGE / "authority_parameters.json"
STAGE1_MANIFEST_PATH = PACKAGE / "stage1_manifest.json"
PROVENANCE_ARTIFACT_ID = "regime-a-prime-prospective-pre-outcome-provenance-v0.2"
AUTHORIZATION_ARTIFACT_ID = "regime-a-prime-stage1-authorization-v0.2"
SCHEMA_VERSION = "1.1"
RUNTIME_POLICY = "BOUND_AT_LAUNCH_BY_PREOUTCOME_PROVENANCE_RECEIPT"


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


def build_provenance(probe_evidence_path: Path, output: Path, *,
                     freeze_commit: str | None, durable_probe: bool) -> int:
    authority = load_json(AUTHORITY_PATH)
    manifest = load_json(STAGE1_MANIFEST_PATH)
    binding = require_stage_manifest_binding("stage1-capture", manifest,
        manifest_path=STAGE1_MANIFEST_PATH, authority=authority)
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
                            "python3 scripts/regime_a_prime_qualification_v0_2/generate_receipts.py "
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
        "generated_by": "scripts/regime_a_prime_qualification_v0_2/generate_receipts.py",
        "authority_sha256": sha256_file(AUTHORITY_PATH),
        "manifest_sha256": sha256_file(STAGE1_MANIFEST_PATH),
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
        **commit_state,
    }
    provenance["payload_sha256"] = canonical_payload_sha256(provenance)
    atomic_write_json(output, provenance)
    print(f"PROVENANCE_RECEIPT_STATUS={status}")
    print(f"PROVENANCE_RECEIPT_SHA256={sha256_file(output)}")
    print(f"DURABLE_PROBE_VERIFIED={durable['verified']}")
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
        "generated_by": "scripts/regime_a_prime_qualification_v0_2/generate_receipts.py",
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
    provenance = sub.add_parser("provenance")
    provenance.add_argument("--probe-evidence", type=Path, required=True)
    provenance.add_argument("--output", type=Path, required=True)
    provenance.add_argument("--freeze-commit")
    provenance.add_argument("--durable-probe", action="store_true",
                            help="execute the real durable-prefix round trip")
    authorize = sub.add_parser("stage1-authorization")
    authorize.add_argument("--provenance", type=Path, required=True)
    authorize.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "runtime-preflight":
        return runtime_preflight(args.output)
    if args.command == "provenance":
        return build_provenance(args.probe_evidence, args.output,
                                freeze_commit=args.freeze_commit,
                                durable_probe=args.durable_probe)
    return build_stage1_authorization(args.provenance, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
