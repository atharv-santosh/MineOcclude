#!/usr/bin/env python3
"""Execute one immutable, isolated, whole-seed P11 shard."""

from __future__ import annotations

import argparse
import json
import os
import resource
import shutil
import statistics
import subprocess
import sys
import tarfile
import tempfile
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

OPERATIONAL_ROOT = Path(__file__).resolve().parents[1]


def requested_scientific_root() -> Path:
    """Resolve the frozen science checkout before importing scientific modules."""

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--scientific-root", type=Path)
    known, _unknown = parser.parse_known_args()
    configured = known.scientific_root or os.environ.get("MINEOCCLUDE_SCIENTIFIC_ROOT")
    return Path(configured).resolve() if configured else OPERATIONAL_ROOT


ROOT = requested_scientific_root()
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import numpy as np

from mineocclude.probes import p11_sharding as authority
from scripts import optimize_large_scale_no_wall_p7a_execution as p7a
from scripts import run_large_scale_no_wall_p11_null as p11

QUALIFIED_PYTHON = Path("/home/sagemaker-user/.conda/envs/mineworld/bin/python")
P6_S3_PREFIX = (
    "s3://sagemaker-us-east-1-323206973672/"
    "mineocclude/exploratory_large_scale_no_wall_scaling_best_k_v0_1/"
    "repaired_v2/p6_layer4_activations_v0_1/"
)
P6_TRANSFER_BYTES = 9_968_056_320
TOKEN_CACHE_BYTES = 8_422_686_848
COARSE_CACHE_BYTES = 707_788_928
MAX_ATTEMPTS = 2
SCIENTIFIC_IMPLEMENTATION_COMMIT = "173a3ca3e92ffe771d19911c15c006dba6acc934"
IMMUTABLE_HANDOFF_COMMIT = "c701eef7ef4042802c489748fb3f1c532d322cf2"
CONTROL_RECEIPT_NAME = "durable_control_receipt.json"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def append_jsonl(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(dict(value), sort_keys=True, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def load_context(
    shard_path: Path, common_path: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    parent = read_json(p11.MANIFEST)
    parent_sha = authority.sha256_file(p11.MANIFEST)
    authority.require(p11.MANIFEST_LOCK.read_text(encoding="utf-8").strip() == parent_sha, "parent lock mismatch")
    common = read_json(common_path)
    shard_paths = [common_path.parent / name for name in common["shard_manifest_files"]]
    shards = [read_json(path) for path in shard_paths]
    authority.validate_common(common, parent, parent_sha, shards)
    shard = read_json(shard_path)
    matching = [document for document in shards if document["shard_manifest_sha"] == shard["shard_manifest_sha"]]
    authority.require(len(matching) == 1 and matching[0] == shard, "selected shard not in common authority")
    authority.validate_shard(
        shard, parent, parent_sha, completed_seed_indices=common["completed_seed_indices"]
    )
    return shard, common, parent, shards


def configure_namespace(shard: Mapping[str, Any]) -> None:
    p11.RESULT_ROOT = Path(str(shard["local_result_root"]))
    p11.JOB_ROOT = p11.RESULT_ROOT / "jobs"
    p11.LEDGER = Path(str(shard["ledger_path"]))
    p11.PROGRESS = Path(str(shard["progress_path"]))
    p11.S3_PREFIX = str(shard["durable_output_prefix"])
    p11.S3_URI = f"s3://{p11.p8.S3_BUCKET}/{p11.S3_PREFIX}/"


def assigned_jobs(shard: Mapping[str, Any], parent: Mapping[str, Any]) -> list[dict[str, Any]]:
    by_id = {job["job_id"]: job for job in parent["jobs"]}
    return [by_id[job_id] for job_id in shard["exact_original_job_ids"]]


def latest_ledger(path: Path) -> tuple[dict[str, dict[str, Any]], Counter[str], dict[str, int]]:
    latest: dict[str, dict[str, Any]] = {}
    attempts: dict[str, int] = defaultdict(int)
    for event in read_jsonl(path):
        latest[event["job_id"]] = event
        attempts[event["job_id"]] = max(attempts[event["job_id"]], int(event["attempt"]))
    return latest, Counter(event["state"] for event in latest.values()), attempts


def validate_ledger_authority(
    shard: Mapping[str, Any], parent: Mapping[str, Any], ledger: Path | None = None
) -> None:
    ledger = ledger or Path(str(shard["ledger_path"]))
    allowed = {job["job_id"]: job for job in assigned_jobs(shard, parent)}
    events = read_jsonl(ledger)
    seen_events: set[str] = set()
    by_job: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        authority.require(event.get("job_id") in allowed, "foreign job in shard ledger")
        job = allowed[event["job_id"]]
        authority.require(event.get("identity_sha256") == job["identity_sha256"], "ledger identity mismatch")
        authority.require(int(event.get("seed_index", job["seed_index"])) == job["seed_index"], "ledger seed mismatch")
        serialized = json.dumps(event, sort_keys=True, separators=(",", ":"))
        authority.require(serialized not in seen_events, "duplicate ledger event")
        seen_events.add(serialized)
        by_job[event["job_id"]].append(event)
    authority.require(set(by_job) == set(allowed), "ledger missing assigned job identity")
    for job_id, history in by_job.items():
        authority.require(
            history[0].get("state") == "PENDING" and int(history[0].get("attempt", -1)) == 0,
            f"ambiguous initial ledger state: {job_id}",
        )
        previous_state = "PENDING"
        previous_attempt = 0
        for event in history[1:]:
            state = str(event.get("state"))
            attempt = int(event.get("attempt", -1))
            if previous_state in {"VALIDATED", "BLOCKED"}:
                authority.require(False, f"event after terminal ledger state: {job_id}")
            if state == "RUNNING":
                authority.require(
                    previous_state in {"PENDING", "FAILED_RETRYABLE"}
                    and attempt == previous_attempt + 1,
                    f"ambiguous RUNNING transition: {job_id}",
                )
            else:
                authority.require(
                    previous_state == "RUNNING"
                    and state in {"VALIDATED", "FAILED_RETRYABLE", "BLOCKED"}
                    and attempt == previous_attempt,
                    f"ambiguous terminal/retry transition: {job_id}",
                )
            authority.require(0 <= attempt <= MAX_ATTEMPTS, f"foreign attempt count: {job_id}")
            previous_state, previous_attempt = state, attempt


def control_paths(shard: Mapping[str, Any], root: Path | None = None) -> list[Path]:
    actual_root = root or Path(str(shard["local_result_root"]))
    return [
        actual_root / "shard_manifest.json",
        actual_root / Path(str(shard["ledger_path"])).name,
        actual_root / Path(str(shard["progress_path"])).name,
    ]


def durable_control_receipt(
    shard: Mapping[str, Any], parent: Mapping[str, Any], root: Path | None = None
) -> dict[str, Any]:
    actual_root = root or Path(str(shard["local_result_root"]))
    ledger = actual_root / Path(str(shard["ledger_path"])).name
    validate_ledger_authority(shard, parent, ledger)
    latest, _counts, _attempts = latest_ledger(ledger)
    validated: dict[str, str] = {}
    for job in assigned_jobs(shard, parent):
        if latest[job["job_id"]]["state"] == "VALIDATED":
            result_path = actual_root / "jobs" / job["job_id"] / "job_result.json"
            authority.require(result_path.is_file(), f"validated job result absent: {job['job_id']}")
            validated[job["job_id"]] = authority.sha256_file(result_path)
    files = {
        path.name: {"byte_count": path.stat().st_size, "sha256": authority.sha256_file(path)}
        for path in control_paths(shard, actual_root)
    }
    return {
        "artifact_id": "large-scale-no-wall-p11-durable-shard-control-v0.1",
        "worker_name": shard["worker_name"],
        "worker_slug": shard["worker_slug"],
        "shard_manifest_sha": shard["shard_manifest_sha"],
        "parent_p11_manifest_sha": shard["parent_p11_manifest_sha"],
        "durable_output_prefix": shard["durable_output_prefix"],
        "control_files": files,
        "validated_jobs": validated,
        "written_at": now_utc(),
    }


def initialize(shard: Mapping[str, Any], parent: Mapping[str, Any], shard_path: Path) -> None:
    root = Path(str(shard["local_result_root"]))
    ledger = Path(str(shard["ledger_path"]))
    root.mkdir(parents=True, exist_ok=True)
    (root / "jobs").mkdir(exist_ok=True)
    if not ledger.exists():
        for job in assigned_jobs(shard, parent):
            append_jsonl(
                ledger,
                {
                    "attempt": 0,
                    "event_at": now_utc(),
                    "identity_sha256": job["identity_sha256"],
                    "job_id": job["job_id"],
                    "seed": job["seed"],
                    "seed_index": job["seed_index"],
                    "state": "PENDING",
                },
            )
        write_json(root / "shard_manifest.json", read_json(shard_path))
    validate_ledger_authority(shard, parent)
    write_progress(shard, parent, current_job=None)


def write_progress(
    shard: Mapping[str, Any], parent: Mapping[str, Any], *, current_job: str | None
) -> None:
    latest, counts, attempts = latest_ledger(Path(str(shard["ledger_path"])))
    complete_seeds = sum(
        all(latest.get(f"seed_{index:02d}__{rep.lower()}", {}).get("state") == "VALIDATED" for rep in authority.REPRESENTATIONS)
        for index in shard["seed_indices"]
    )
    current = next((job for job in parent["jobs"] if job["job_id"] == current_job), None)
    write_json(
        Path(str(shard["progress_path"])),
        {
            "artifact_id": "large-scale-no-wall-p11-shard-progress-v0.1",
            "shard_manifest_sha": shard["shard_manifest_sha"],
            "worker_name": shard["worker_name"],
            "blocked_jobs": counts["BLOCKED"],
            "current_job_id": current_job,
            "current_representation": None if current is None else current["representation"],
            "current_seed": None if current is None else current["seed"],
            "current_seed_index": None if current is None else current["seed_index"],
            "expected_jobs": shard["expected_job_count"],
            "expected_seeds": shard["expected_seed_count"],
            "failed_retryable_current_jobs": counts["FAILED_RETRYABLE"],
            "maximum_attempt": max(attempts.values(), default=0),
            "running_jobs": counts["RUNNING"],
            "updated_at": now_utc(),
            "validated_jobs": counts["VALIDATED"],
            "validated_seeds": complete_seeds,
        },
    )


def sync_control(shard: Mapping[str, Any], parent: Mapping[str, Any]) -> None:
    root = Path(str(shard["local_result_root"]))
    paths = control_paths(shard, root)
    receipt_path = root / CONTROL_RECEIPT_NAME
    write_json(receipt_path, durable_control_receipt(shard, parent, root))
    for path in paths:
        subprocess.run(
            ["aws", "s3", "cp", str(path), f"{p11.S3_URI}{path.name}", "--only-show-errors"],
            check=True,
        )
    subprocess.run(
        ["aws", "s3", "cp", str(receipt_path), f"{p11.S3_URI}{CONTROL_RECEIPT_NAME}", "--only-show-errors"],
        check=True,
    )


def sync_job(shard: Mapping[str, Any], parent: Mapping[str, Any], job_id: str) -> None:
    subprocess.run(
        [
            "aws", "s3", "sync", str(p11.JOB_ROOT / job_id),
            f"{p11.S3_URI}jobs/{job_id}/", "--only-show-errors",
        ],
        check=True,
    )
    sync_control(shard, parent)


def restore_job(job_id: str) -> None:
    (p11.JOB_ROOT / job_id).mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["aws", "s3", "sync", f"{p11.S3_URI}jobs/{job_id}/", str(p11.JOB_ROOT / job_id), "--only-show-errors"],
        check=True,
    )


class DurableTransport(Protocol):
    def download_file(self, relative: str, destination: Path) -> None: ...
    def download_tree(self, relative: str, destination: Path) -> None: ...
    def list_keys(self, relative_prefix: str) -> list[str]: ...


class S3DurableTransport:
    def __init__(self, shard: Mapping[str, Any]) -> None:
        self.bucket = p11.p8.S3_BUCKET
        self.prefix = str(shard["durable_output_prefix"]).strip("/")
        self.uri = f"s3://{self.bucket}/{self.prefix}/"

    def download_file(self, relative: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["aws", "s3", "cp", f"{self.uri}{relative}", str(destination), "--only-show-errors"],
            check=True,
        )

    def download_tree(self, relative: str, destination: Path) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["aws", "s3", "sync", f"{self.uri}{relative.rstrip('/')}/", str(destination), "--only-show-errors"],
            check=True,
        )

    def list_keys(self, relative_prefix: str) -> list[str]:
        prefix = f"{self.prefix}/{relative_prefix.lstrip('/')}"
        completed = subprocess.run(
            [
                "aws", "s3api", "list-objects-v2", "--bucket", self.bucket,
                "--prefix", prefix, "--output", "json",
            ],
            check=True, capture_output=True, text=True,
        )
        document = json.loads(completed.stdout)
        authority.require(not document.get("IsTruncated"), "durable job listing is truncated/ambiguous")
        marker = f"{self.prefix}/"
        keys = [str(item["Key"]) for item in document.get("Contents", [])]
        authority.require(len(keys) == len(set(keys)), "duplicate durable object key")
        authority.require(all(key.startswith(marker) for key in keys), "foreign durable object prefix")
        return [key[len(marker):] for key in keys]


def validate_control_receipt(receipt: Mapping[str, Any], shard: Mapping[str, Any]) -> None:
    authority.require(
        receipt.get("artifact_id") == "large-scale-no-wall-p11-durable-shard-control-v0.1",
        "foreign durable control receipt",
    )
    for key in (
        "worker_name", "worker_slug", "shard_manifest_sha", "parent_p11_manifest_sha",
        "durable_output_prefix",
    ):
        authority.require(receipt.get(key) == shard.get(key), f"durable control {key} mismatch")
    expected_names = {path.name for path in control_paths(shard)}
    authority.require(set(receipt.get("control_files", {})) == expected_names, "durable control file set mismatch")
    validated = receipt.get("validated_jobs", {})
    authority.require(isinstance(validated, dict), "ambiguous validated job map")
    authority.require(
        set(validated) <= set(shard["exact_original_job_ids"]), "foreign job in durable control receipt"
    )


def validate_restored_state(
    shard: Mapping[str, Any], parent: Mapping[str, Any], root: Path, receipt: Mapping[str, Any]
) -> None:
    validate_control_receipt(receipt, shard)
    for path in control_paths(shard, root):
        claim = receipt["control_files"][path.name]
        authority.require(path.is_file(), f"restored control file absent: {path.name}")
        authority.require(path.stat().st_size == int(claim["byte_count"]), f"restored control size mismatch: {path.name}")
        authority.require(authority.sha256_file(path) == claim["sha256"], f"restored control hash mismatch: {path.name}")
    authority.require(read_json(root / "shard_manifest.json") == dict(shard), "restored shard manifest mismatch")
    ledger = root / Path(str(shard["ledger_path"])).name
    validate_ledger_authority(shard, parent, ledger)
    latest, counts, _attempts = latest_ledger(ledger)
    expected_validated = {
        job_id for job_id, event in latest.items() if event["state"] == "VALIDATED"
    }
    authority.require(
        set(receipt["validated_jobs"]) == expected_validated,
        "validated jobs disagree between restored ledger and control receipt",
    )
    progress = read_json(root / Path(str(shard["progress_path"])).name)
    authority.require(progress.get("worker_name") == shard["worker_name"], "restored progress worker mismatch")
    authority.require(progress.get("shard_manifest_sha") == shard["shard_manifest_sha"], "restored progress shard mismatch")
    authority.require(int(progress.get("validated_jobs", -1)) == counts["VALIDATED"], "restored progress count mismatch")


def validate_takeover_attestation(
    path: Path, shard: Mapping[str, Any], operator_name: str
) -> dict[str, Any]:
    document = read_json(path)
    authority.require(document.get("process_proven_stopped") is True, "original process is not proven stopped")
    authority.require(document.get("original_worker_name") == shard["worker_name"], "takeover worker mismatch")
    authority.require(document.get("shard_manifest_sha") == shard["shard_manifest_sha"], "takeover shard mismatch")
    authority.require(document.get("durable_output_prefix") == shard["durable_output_prefix"], "takeover prefix mismatch")
    authority.require(document.get("replacement_operator") == operator_name, "takeover operator mismatch")
    authority.require(bool(document.get("observed_stopped_at")), "takeover stop observation absent")
    return document


def restore_durable_state(
    shard: Mapping[str, Any],
    parent: Mapping[str, Any],
    *,
    operator_name: str,
    takeover_attestation: Path | None = None,
    transport: DurableTransport | None = None,
) -> dict[str, Any]:
    """Restore one exact original shard after total local mutable-state loss."""

    configure_namespace(shard)
    root = Path(str(shard["local_result_root"]))
    authority.require(bool(operator_name.strip()), "restoring operator name required")
    authority.require(not root.exists(), "restore target already exists; refusing ambiguous merge")
    attestation = None
    if takeover_attestation is not None:
        attestation = validate_takeover_attestation(takeover_attestation, shard, operator_name)
    durable = transport or S3DurableTransport(shard)
    root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{shard['worker_slug']}.restore-", dir=root.parent))
    first_receipt = staging / CONTROL_RECEIPT_NAME
    installed = False
    try:
        durable.download_file(CONTROL_RECEIPT_NAME, first_receipt)
        receipt = read_json(first_receipt)
        validate_control_receipt(receipt, shard)
        for name in receipt["control_files"]:
            durable.download_file(name, staging / name)
        validated_jobs = set(receipt["validated_jobs"])
        keys = durable.list_keys("jobs/")
        observed_jobs: set[str] = set()
        for key in keys:
            parts = Path(key).parts
            authority.require(len(parts) >= 3 and parts[0] == "jobs", "ambiguous durable job key")
            observed_jobs.add(parts[1])
        authority.require(observed_jobs == validated_jobs, "missing or foreign durable jobs")
        for job_id in sorted(validated_jobs):
            durable.download_tree(f"jobs/{job_id}", staging / "jobs" / job_id)
        second_receipt = staging / f".{CONTROL_RECEIPT_NAME}.stable"
        durable.download_file(CONTROL_RECEIPT_NAME, second_receipt)
        authority.require(
            authority.sha256_file(first_receipt) == authority.sha256_file(second_receipt),
            "durable control changed during restoration; state is ambiguous",
        )
        validate_restored_state(shard, parent, staging, receipt)
        jobs = {job["job_id"]: job for job in assigned_jobs(shard, parent)}
        for job_id, expected_sha in receipt["validated_jobs"].items():
            result_path = staging / "jobs" / job_id / "job_result.json"
            authority.require(authority.sha256_file(result_path) == expected_sha, f"restored result hash mismatch: {job_id}")
        second_receipt.unlink()
        os.replace(staging, root)
        installed = True
        configure_namespace(shard)
        for job_id in receipt["validated_jobs"]:
            validate_result(jobs[job_id])
    except BaseException:
        if installed and root.exists() and not staging.exists():
            os.replace(root, staging)
        shutil.rmtree(staging, ignore_errors=True)
        raise
    configure_namespace(shard)
    restoration = {
        "artifact_id": "large-scale-no-wall-p11-durable-restoration-v0.1",
        "status": "PASS_EXACT_ORIGINAL_SHARD_RESTORED_FOR_RESUME",
        "worker_name": shard["worker_name"],
        "shard_manifest_sha": shard["shard_manifest_sha"],
        "parent_p11_manifest_sha": shard["parent_p11_manifest_sha"],
        "durable_output_prefix": shard["durable_output_prefix"],
        "restoring_operator": operator_name,
        "takeover": attestation is not None,
        "process_stopped_attestation_sha256": (
            authority.sha256_file(takeover_attestation) if takeover_attestation else None
        ),
        "restored_control_sha256": {
            name: claim["sha256"] for name, claim in receipt["control_files"].items()
        },
        "restored_validated_job_count": len(receipt["validated_jobs"]),
        "restored_at": now_utc(),
        "next_action": "run the same frozen shard manifest with --run --resume",
    }
    write_json(root / "restoration_receipt.json", restoration)
    return restoration


def validate_result(job: Mapping[str, Any]) -> dict[str, Any]:
    return p11.validate_job_result(dict(job))


def resume_job_ids(
    shard: Mapping[str, Any], parent: Mapping[str, Any], latest: Mapping[str, Mapping[str, Any]]
) -> list[str]:
    """Return only assigned jobs that are not already authoritatively validated."""

    return [
        job["job_id"]
        for job in assigned_jobs(shard, parent)
        if latest.get(job["job_id"], {}).get("state") != "VALIDATED"
    ]


def execute_assigned_worker(shard: Mapping[str, Any], job_id: str) -> None:
    """Dispatch through the unchanged frozen worker after the shard hard gate."""

    authority.require_assigned_job(shard, job_id)
    p11.run_worker(job_id)


def run_shard(
    shard_path: Path, common_path: Path, shard: dict[str, Any], parent: dict[str, Any]
) -> None:
    configure_namespace(shard)
    p11.validate_manifest(require_p10_complete=True)
    p11.p10.ensure_coarse_cache(full_hash=True)
    initialize(shard, parent, shard_path)
    sync_control(shard, parent)
    latest, _, attempts = latest_ledger(Path(str(shard["ledger_path"])))
    jobs_requiring_execution = set(resume_job_ids(shard, parent, latest))
    for job in assigned_jobs(shard, parent):
        event = latest[job["job_id"]]
        if job["job_id"] not in jobs_requiring_execution:
            try:
                validate_result(job)
            except Exception:  # noqa: BLE001 - exact frozen validator drives S3 restore
                restore_job(job["job_id"])
                validate_result(job)
            sync_job(shard, parent, job["job_id"])
            continue
        if event["state"] == "RUNNING":
            append_jsonl(
                Path(str(shard["ledger_path"])),
                {
                    "attempt": attempts[job["job_id"]], "event_at": now_utc(),
                    "identity_sha256": job["identity_sha256"], "job_id": job["job_id"],
                    "reason": "interrupted exact shard worker", "seed": job["seed"],
                    "seed_index": job["seed_index"], "state": "FAILED_RETRYABLE",
                },
            )
        succeeded = False
        while attempts[job["job_id"]] < MAX_ATTEMPTS and not succeeded:
            attempts[job["job_id"]] += 1
            attempt = attempts[job["job_id"]]
            append_jsonl(
                Path(str(shard["ledger_path"])),
                {
                    "attempt": attempt, "event_at": now_utc(),
                    "identity_sha256": job["identity_sha256"], "job_id": job["job_id"],
                    "seed": job["seed"], "seed_index": job["seed_index"], "state": "RUNNING",
                },
            )
            write_progress(shard, parent, current_job=job["job_id"])
            sync_control(shard, parent)
            log_path = p11.RESULT_ROOT / "attempt_logs" / f"{job['job_id']}__attempt_{attempt}.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("w", encoding="utf-8") as log:
                completed = subprocess.run(
                    [
                        str(QUALIFIED_PYTHON), str(Path(__file__).resolve()),
                        "--shard-manifest", str(shard_path.resolve()),
                        "--common-authority", str(common_path.resolve()),
                        "--scientific-root", str(ROOT),
                        "--worker", job["job_id"],
                    ],
                    cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, text=True, check=False,
                )
            failure: str | None = None
            if completed.returncode == 0:
                try:
                    result = validate_result(job)
                except Exception as error:  # noqa: BLE001 - record authoritative worker failure
                    failure = f"post-worker validation: {type(error).__name__}: {error}"
                else:
                    append_jsonl(
                        Path(str(shard["ledger_path"])),
                        {
                            "attempt": attempt, "event_at": now_utc(),
                            "identity_sha256": job["identity_sha256"], "job_id": job["job_id"],
                            "result_sha256": authority.sha256_file(p11.JOB_ROOT / job["job_id"] / "job_result.json"),
                            "runtime_seconds": result["runtime"]["total_seconds"], "seed": job["seed"],
                            "seed_index": job["seed_index"], "state": "VALIDATED",
                        },
                    )
                    write_progress(shard, parent, current_job=None)
                    sync_job(shard, parent, job["job_id"])
                    succeeded = True
            else:
                failure = f"worker exit {completed.returncode}; log={log_path}"
            if not succeeded:
                state = "FAILED_RETRYABLE" if attempt < MAX_ATTEMPTS else "BLOCKED"
                append_jsonl(
                    Path(str(shard["ledger_path"])),
                    {
                        "attempt": attempt, "event_at": now_utc(),
                        "identity_sha256": job["identity_sha256"], "job_id": job["job_id"],
                        "reason": failure, "seed": job["seed"], "seed_index": job["seed_index"],
                        "state": state,
                    },
                )
                write_progress(shard, parent, current_job=None)
                sync_control(shard, parent)
                authority.require(state != "BLOCKED", f"P11 shard job blocked: {job['job_id']}")
        latest, _, _ = latest_ledger(Path(str(shard["ledger_path"])))
    validate_complete(shard, parent)


def validate_complete(shard: Mapping[str, Any], parent: Mapping[str, Any]) -> dict[str, Any]:
    configure_namespace(shard)
    validate_ledger_authority(shard, parent)
    _latest, counts, _ = latest_ledger(Path(str(shard["ledger_path"])))
    jobs = assigned_jobs(shard, parent)
    authority.require(counts["VALIDATED"] == len(jobs), "shard validated job count mismatch")
    authority.require(not counts["RUNNING"] and not counts["BLOCKED"] and not counts["FAILED_RETRYABLE"], "shard has non-terminal jobs")
    results = [validate_result(job) for job in jobs]
    receipt = {
        "artifact_id": "large-scale-no-wall-p11-shard-completion-v0.1",
        "status": "PASS_P11_SHARD_COMPLETE_VALIDATED",
        "worker_name": shard["worker_name"],
        "shard_manifest_sha": shard["shard_manifest_sha"],
        "parent_p11_manifest_sha": shard["parent_p11_manifest_sha"],
        "validated_seed_count": shard["expected_seed_count"],
        "validated_job_count": len(results),
        "missing_jobs": 0, "duplicate_jobs": 0, "blocked_jobs": 0,
        "job_result_sha256": {
            result["job_id"]: authority.sha256_file(p11.JOB_ROOT / result["job_id"] / "job_result.json")
            for result in results
        },
        "validated_at": now_utc(),
    }
    write_json(Path(str(shard["local_result_root"])) / "completion_receipt.json", receipt)
    return receipt


def package_upload(shard: Mapping[str, Any], parent: Mapping[str, Any]) -> dict[str, Any]:
    receipt = validate_complete(shard, parent)
    root = Path(str(shard["local_result_root"]))
    package = root / f"p11_shard_{shard['worker_slug']}_return.tar.gz"
    members = [root / "jobs", root / "shard_manifest.json", Path(str(shard["ledger_path"])), Path(str(shard["progress_path"])), root / "completion_receipt.json"]
    with tarfile.open(package, "w:gz", compresslevel=6) as archive:
        for path in members:
            archive.add(path, arcname=path.relative_to(root), recursive=True)
    package_receipt = {
        **receipt,
        "durable_output_prefix": shard["durable_output_prefix"],
        "package_path": str(package),
        "package_byte_count": package.stat().st_size,
        "package_sha256": authority.sha256_file(package),
        "package_s3_uri": f"{p11.S3_URI}return/{package.name}",
    }
    write_json(root / "package_upload_receipt.json", package_receipt)
    subprocess.run(
        ["aws", "s3", "cp", str(package), package_receipt["package_s3_uri"], "--checksum-algorithm", "SHA256", "--only-show-errors"],
        check=True,
    )
    subprocess.run(
        ["aws", "s3", "cp", str(root / "package_upload_receipt.json"), f"{p11.S3_URI}return/package_upload_receipt.json", "--only-show-errors"],
        check=True,
    )
    return package_receipt


def reconstruct_caches() -> dict[str, Any]:
    token = p7a.build_training_token_cache()
    authority.require(token["sha256"] == authority.TOKEN_CACHE_SHA, "token cache reconstruction hash mismatch")
    coarse = p11.p10.ensure_coarse_cache(full_hash=True)
    authority.require(coarse["sha256"] == authority.COARSE_CACHE_SHA, "COARSE cache reconstruction hash mismatch")
    return {"token_cache": token, "coarse_cache": coarse}


def acquire_inputs() -> dict[str, Any]:
    """Download only the 240 immutable P6 arrays required by P11."""

    manifest = read_json(p11.p8.P6_MANIFEST)
    observed_bytes = 0
    downloaded = 0
    for chunk in manifest["chunks"]:
        for key in ("unpooled", "pooled"):
            artifact = chunk[key]
            destination = p11.p8.ACTIVATION_ROOT / artifact["path"]
            expected_size = int(artifact["byte_size"])
            expected_sha = str(artifact["sha256"])
            if (
                destination.is_file()
                and destination.stat().st_size == expected_size
                and authority.sha256_file(destination) == expected_sha
            ):
                observed_bytes += expected_size
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(f".{destination.name}.download-{os.getpid()}")
            source = f"{P6_S3_PREFIX}activations/{artifact['path']}"
            subprocess.run(
                ["aws", "s3", "cp", source, str(temporary), "--only-show-errors"],
                check=True,
            )
            authority.require(temporary.stat().st_size == expected_size, f"P6 size mismatch {artifact['path']}")
            authority.require(authority.sha256_file(temporary) == expected_sha, f"P6 SHA mismatch {artifact['path']}")
            os.replace(temporary, destination)
            observed_bytes += expected_size
            downloaded += 1
    authority.require(observed_bytes == P6_TRANSFER_BYTES, "P6 minimal input byte authority mismatch")
    return {
        "status": "PASS_MINIMUM_P6_INPUTS_VALIDATED",
        "array_count": 240,
        "downloaded_array_count": downloaded,
        "scientific_input_bytes": observed_bytes,
        "source_prefix": P6_S3_PREFIX,
    }


def immutable_handoff_paths() -> list[str]:
    paths = [
        "p11_distributed_handoff/common_authority.json",
        "p11_distributed_handoff/authority_bundle.sha256",
    ]
    paths.extend(
        f"p11_distributed_handoff/{slug}/shard_manifest.json" for _worker, slug, _shard in authority.WORKERS
    )
    paths.extend(
        f"p11_distributed_handoff/p11_shard_{slug}.json" for _worker, slug, _shard in authority.WORKERS
    )
    listed = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", IMMUTABLE_HANDOFF_COMMIT, "--", "p11_distributed_handoff/authority_bundle"],
        cwd=OPERATIONAL_ROOT, text=True,
    ).splitlines()
    return paths + listed


def prove_immutable_handoff() -> None:
    for relative in immutable_handoff_paths():
        path = OPERATIONAL_ROOT / relative
        authority.require(path.is_file(), f"immutable handoff path absent: {relative}")
        frozen = subprocess.check_output(
            ["git", "show", f"{IMMUTABLE_HANDOFF_COMMIT}:{relative}"], cwd=OPERATIONAL_ROOT
        )
        authority.require(path.read_bytes() == frozen, f"immutable handoff authority changed: {relative}")


def validate_bootstrap_receipt(path: Path, shard: Mapping[str, Any]) -> dict[str, Any]:
    document = read_json(path)
    authority.require(document.get("status") == "PASS_FRESH_WORKER_BOOTSTRAP", "bootstrap did not pass")
    authority.require(document.get("scientific_implementation_commit") == SCIENTIFIC_IMPLEMENTATION_COMMIT, "bootstrap science authority mismatch")
    authority.require(document.get("immutable_handoff_commit") == IMMUTABLE_HANDOFF_COMMIT, "bootstrap handoff authority mismatch")
    authority.require(document.get("worker_slug") == shard["worker_slug"], "bootstrap worker mismatch")
    authority.require(Path(document["scientific_root"]).resolve() == ROOT, "bootstrap science path mismatch")
    authority.require(Path(document["operational_root"]).resolve() == OPERATIONAL_ROOT, "bootstrap operational path mismatch")
    operational_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=OPERATIONAL_ROOT, text=True
    ).strip()
    authority.require(document.get("operational_handoff_commit") == operational_commit, "bootstrap operational commit mismatch")
    return document


def environment_preflight(
    shard: Mapping[str, Any], bootstrap_receipt: Path | None = None
) -> dict[str, Any]:
    import torch

    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    authority.require(ROOT != OPERATIONAL_ROOT, "scientific and operational checkouts must be separate")
    authority.require(branch == shard["repository_branch"], "wrong repository branch")
    authority.require(commit == shard["implementation_commit_sha"], "wrong implementation commit")
    authority.require(commit == SCIENTIFIC_IMPLEMENTATION_COMMIT, "unexpected scientific implementation authority")
    prove_immutable_handoff()
    bootstrap = validate_bootstrap_receipt(bootstrap_receipt, shard) if bootstrap_receipt else None
    authority.require(Path(sys.executable).resolve() == QUALIFIED_PYTHON.resolve(), "wrong qualified Python")
    authority.require(torch.cuda.is_available(), "CUDA unavailable")
    free_disk = os.statvfs("/mnt/sagemaker-nvme").f_bavail * os.statvfs("/mnt/sagemaker-nvme").f_frsize
    authority.require(free_disk >= 24_000_000_000, "less than 24 GB free NVMe")
    return {
        "status": "PASS", "branch": branch, "commit": commit, "python": sys.executable,
        "scientific_root": str(ROOT), "operational_root": str(OPERATIONAL_ROOT),
        "immutable_handoff_commit": IMMUTABLE_HANDOFF_COMMIT,
        "operational_handoff_commit": None if bootstrap is None else bootstrap["operational_handoff_commit"],
        "numpy": np.__version__, "torch": torch.__version__, "cuda": torch.version.cuda,
        "gpu_name": torch.cuda.get_device_name(0),
        "gpu_total_bytes": torch.cuda.get_device_properties(0).total_memory,
        "host_soft_limit_bytes": resource.getrlimit(resource.RLIMIT_AS)[0],
        "free_nvme_bytes": free_disk,
    }


def derive_completed(parent: Mapping[str, Any]) -> list[int]:
    latest, _, _ = p11.latest_ledger()
    completed: list[int] = []
    for index in range(49):
        jobs = [job for job in parent["jobs"] if job["seed_index"] == index]
        states = [latest[job["job_id"]]["state"] for job in jobs]
        if states == ["VALIDATED"] * 4:
            for job in jobs:
                p11.validate_job_result(job)
            completed.append(index)
        else:
            authority.require(not any(state == "VALIDATED" for state in states), f"partial seed present: {index}")
            authority.require(not any(state == "RUNNING" for state in states), f"running seed present: {index}")
    return completed


def runtime_summary(parent: Mapping[str, Any], completed: list[int], shards: list[Mapping[str, Any]]) -> dict[str, Any]:
    by_rep: dict[str, list[float]] = defaultdict(list)
    seed_times: list[float] = []
    for index in completed:
        values: list[float] = []
        for job in [entry for entry in parent["jobs"] if entry["seed_index"] == index]:
            result = p11.validate_job_result(job)
            value = float(result["runtime"]["total_seconds"])
            values.append(value)
            by_rep[job["representation"]].append(value)
        seed_times.append(sum(values))
    mean_seed = statistics.mean(seed_times)
    median_seed = statistics.median(seed_times)
    total = sum(sum(values) for values in by_rep.values())
    best_k = sum(by_rep["BEST_K_TOKENS"])
    workers = {
        shard["worker_slug"]: {
            "seed_count": shard["expected_seed_count"],
            "job_count": shard["expected_job_count"],
            "estimated_runtime_seconds": mean_seed * shard["expected_seed_count"],
            "approximate_gpu_hours": mean_seed * shard["expected_seed_count"] / 3600.0,
        }
        for shard in shards
    }
    return {
        "completed_seed_sample_count": len(completed),
        "median_seed_runtime_seconds": median_seed,
        "mean_seed_runtime_seconds": mean_seed,
        "median_representation_runtime_seconds": {key: statistics.median(values) for key, values in by_rep.items()},
        "best_k_fraction_of_total_compute": best_k / total,
        "serial_remaining_eta_seconds": mean_seed * sum(shard["expected_seed_count"] for shard in shards),
        "five_worker_remaining_eta_seconds": max(item["estimated_runtime_seconds"] for item in workers.values()),
        "workers": workers,
    }


def handoff_readme(slug: str, worker: str, shard: Mapping[str, Any], common: Mapping[str, Any]) -> str:
    manifest = f"p11_distributed_handoff/{slug}/shard_manifest.json"
    common_path = "p11_distributed_handoff/common_authority.json"
    python = str(QUALIFIED_PYTHON)
    runner = "scripts/run_large_scale_no_wall_p11_shard.py"
    log = str(shard["log_path"])
    return f"""# P11 shard handoff: {worker}

This shard is frozen to {shard['expected_seed_count']} whole seeds / {shard['expected_job_count']} jobs. Do not edit the manifests or seed lists. The immutable handoff authority is `{IMMUTABLE_HANDOFF_COMMIT}` and the scientific implementation authority is `{SCIENTIFIC_IMPLEMENTATION_COMMIT}`.

## 1. Fresh-worker bootstrap (exact commits, two checkouts)

Obtain `NEW_OPERATIONAL_HANDOFF_COMMIT` from `P11_DISTRIBUTED_OPERATIONAL_CLOSURE_RECEIPT`, then run the bootstrap script from that exact owner-delivered commit:

```bash
export P11_OPERATIONAL_HANDOFF_COMMIT=NEW_OPERATIONAL_HANDOFF_COMMIT
export P11_WORKER_HOME="$HOME/mineocclude-p11-{slug}"
python3 /path/to/exact-commit/scripts/bootstrap_large_scale_no_wall_p11_worker.py \\
  --repository-url https://github.com/atharv-santosh/MineOcclude.git \\
  --destination "$P11_WORKER_HOME" \\
  --operational-handoff-commit "$P11_OPERATIONAL_HANDOFF_COMMIT" \\
  --worker {slug}
export P11_OPERATIONAL_ROOT="$P11_WORKER_HOME/operational"
export P11_SCIENTIFIC_ROOT="$P11_WORKER_HOME/scientific"
cd "$P11_OPERATIONAL_ROOT"
```

The operational checkout is detached at the supplied exact closure commit. The separate scientific worktree is the named branch `{shard['repository_branch']}` at exact HEAD `{shard['implementation_commit_sha']}`. The bootstrap verifies that all common/shard/bundle authority bytes still equal commit `{IMMUTABLE_HANDOFF_COMMIT}` and installs the verified authority bundle into the scientific worktree. It never pulls a moving branch HEAD.

## 2. Environment preflight

```bash
{python} {runner} \\
  --scientific-root "$P11_SCIENTIFIC_ROOT" \\
  --bootstrap-receipt "$P11_OPERATIONAL_ROOT/p11_worker_bootstrap_receipt.json" \\
  --shard-manifest {manifest} --common-authority {common_path} \\
  --environment-preflight
```

The preflight deliberately requires the named scientific branch and exact frozen HEAD, plus separate operational/scientific roots, immutable `c701eef` handoff bytes, qualified Python, CUDA, a comparable GPU, and at least 24 GB free NVMe.

## 3. Acquire inputs and reconstruct caches

```bash
{python} {runner} --scientific-root "$P11_SCIENTIFIC_ROOT" --acquire-inputs
{python} {runner} --scientific-root "$P11_SCIENTIFIC_ROOT" --reconstruct-caches
```

The input command verifies exactly {P6_TRANSFER_BYTES} bytes of protected P6 arrays. Expected cache hashes are `{authority.TOKEN_CACHE_SHA}` and `{authority.COARSE_CACHE_SHA}`.

## 4. Validate and future launch (do not launch without owner approval)

```bash
{python} {runner} --scientific-root "$P11_SCIENTIFIC_ROOT" --shard-manifest {manifest} --common-authority {common_path} --validate-shard
nohup setsid {python} {runner} --scientific-root "$P11_SCIENTIFIC_ROOT" --shard-manifest {manifest} --common-authority {common_path} --run --resume </dev/null >{log} 2>&1 &
```

## 5. Full NVMe-loss recovery

After reacquiring P6 inputs and reconstructing caches, restore only into the absent original shard root, then resume the same manifest:

```bash
{python} {runner} --scientific-root "$P11_SCIENTIFIC_ROOT" --shard-manifest {manifest} --common-authority {common_path} --restore-durable --operator-name "$USER"
{python} {runner} --scientific-root "$P11_SCIENTIFIC_ROOT" --shard-manifest {manifest} --common-authority {common_path} --run --resume
```

Restoration validates worker, shard SHA, parent manifest SHA, durable prefix, control hashes, ledger transitions, job identities, foreign objects, and stable non-ambiguous durable state. Already validated jobs are restored, revalidated, and skipped.

## 6. Whole-shard takeover only

Partial reassignment manifests are not supported. A replacement operator must first create a stopped-process attestation naming the same original worker, shard SHA, durable prefix, replacement operator, observation time, and `process_proven_stopped: true`, then run:

```bash
{python} {runner} --scientific-root "$P11_SCIENTIFIC_ROOT" --shard-manifest {manifest} --common-authority {common_path} --takeover-restore --operator-name "$USER" --process-stopped-attestation /path/to/stopped_process_attestation.json
{python} {runner} --scientific-root "$P11_SCIENTIFIC_ROOT" --shard-manifest {manifest} --common-authority {common_path} --run --resume
```

Human operators may change; `worker_name`, shard manifest, durable prefix, original job identities, and seed ownership may not.

## 7. Status, completion, and durable return

```bash
{python} {runner} --scientific-root "$P11_SCIENTIFIC_ROOT" --shard-manifest {manifest} --common-authority {common_path} --status
{python} {runner} --scientific-root "$P11_SCIENTIFIC_ROOT" --shard-manifest {manifest} --common-authority {common_path} --validate-complete
{python} {runner} --scientific-root "$P11_SCIENTIFIC_ROOT" --shard-manifest {manifest} --common-authority {common_path} --package-upload
```

Completion requires {shard['expected_seed_count']}/{shard['expected_seed_count']} seeds and {shard['expected_job_count']}/{shard['expected_job_count']} jobs with no missing, duplicate, blocked, retryable, or running job. Return `p11_shard_{slug}_return.tar.gz`, `package_upload_receipt.json`, immutable shard identity, and its durable URI; never return P6 arrays or reconstructable caches.
"""


def generate_handoffs(output: Path, implementation_commit: str) -> dict[str, Any]:
    p11.validate_manifest(require_p10_complete=True)
    parent = read_json(p11.MANIFEST)
    parent_sha = authority.sha256_file(p11.MANIFEST)
    completed = derive_completed(parent)
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    shards = authority.build_shards(
        parent, parent_sha, completed,
        repository_branch=branch, implementation_commit_sha=implementation_commit,
    )
    output.mkdir(parents=True, exist_ok=True)
    manifest_files: list[str] = []
    for shard in shards:
        name = f"p11_shard_{shard['worker_slug']}.json"
        write_json(output / name, shard)
        manifest_files.append(name)
    common: dict[str, Any] = {
        "artifact_id": "large-scale-no-wall-p11-distributed-common-authority-v0.1",
        "parent_p11_manifest_sha": parent_sha,
        "original_seed_indices": list(range(49)),
        "original_seed_values": [next(job["seed"] for job in parent["jobs"] if job["seed_index"] == index) for index in range(49)],
        "completed_seed_indices": completed,
        "completed_seed_values": [next(job["seed"] for job in parent["jobs"] if job["seed_index"] == index) for index in completed],
        "remaining_seed_indices": [index for index in range(49) if index not in set(completed)],
        "representations": list(authority.REPRESENTATIONS),
        "shard_manifest_files": manifest_files,
        "shard_manifest_shas": {shard["worker_slug"]: shard["shard_manifest_sha"] for shard in shards},
        "repository_branch": branch,
        "implementation_commit_sha": implementation_commit,
        "minimum_scientific_input_transfer_bytes_per_worker": P6_TRANSFER_BYTES,
        "working_disk_requirement_bytes": P6_TRANSFER_BYTES + TOKEN_CACHE_BYTES + COARSE_CACHE_BYTES + 4_000_000_000,
        "distributed_work_launched": False,
    }
    common["runtime_analysis"] = runtime_summary(parent, completed, shards)
    common["common_authority_sha"] = authority.common_sha(common)
    write_json(output / "common_authority.json", common)
    authority.validate_common(common, parent, parent_sha, shards)
    bundle = output / "authority_bundle"
    bundle.mkdir(exist_ok=True)
    bundle_names = (
        "p8_receipt.json", "p8_run_manifest.json", "p8_run_manifest.sha256", "p9_receipt.json",
        "p10_run_manifest.json", "p10_run_manifest.sha256", "p10_receipt.json",
        "p10_validation_receipt.json", "p11_run_manifest.json", "p11_run_manifest.sha256",
        "p11_benchmark_receipt.json",
    )
    checksum_lines: list[str] = []
    for name in bundle_names:
        source = p11.STUDY_ROOT / name
        destination = bundle / name
        destination.write_bytes(source.read_bytes())
        checksum_lines.append(f"{authority.sha256_file(destination)}  p11_distributed_handoff/authority_bundle/{name}")
    (output / "authority_bundle.sha256").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    for shard in shards:
        directory = output / shard["worker_slug"]
        directory.mkdir(exist_ok=True)
        write_json(directory / "shard_manifest.json", shard)
        (directory / "RUNME.md").write_text(handoff_readme(shard["worker_slug"], shard["worker_name"], shard, common), encoding="utf-8")
    (output / "README.md").write_text(
        "# Frozen P11 five-worker handoff\n\nNo distributed shard has been launched. Review `common_authority.json` and all five immutable shard manifests before approving the commands in each `RUNME.md`.\n",
        encoding="utf-8",
    )
    return common


def status_document(shard: Mapping[str, Any], parent: Mapping[str, Any]) -> dict[str, Any]:
    ledger = Path(str(shard["ledger_path"]))
    if not ledger.exists():
        return {"worker_name": shard["worker_name"], "state": "NOT_STARTED", "validated_jobs": 0}
    validate_ledger_authority(shard, parent)
    _latest, counts, _attempts = latest_ledger(ledger)
    progress_path = Path(str(shard["progress_path"]))
    return {
        "worker_name": shard["worker_name"], "shard_manifest_sha": shard["shard_manifest_sha"],
        "expected_jobs": shard["expected_job_count"], "validated_jobs": counts["VALIDATED"],
        "blocked_jobs": counts["BLOCKED"], "failed_retryable_jobs": counts["FAILED_RETRYABLE"],
        "running_jobs": counts["RUNNING"],
        "progress": read_json(progress_path) if progress_path.is_file() else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shard-manifest", type=Path)
    parser.add_argument("--common-authority", type=Path)
    parser.add_argument("--scientific-root", type=Path)
    parser.add_argument("--bootstrap-receipt", type=Path)
    parser.add_argument("--validate-shard", action="store_true")
    parser.add_argument("--environment-preflight", action="store_true")
    parser.add_argument("--acquire-inputs", action="store_true")
    parser.add_argument("--reconstruct-caches", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--worker")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--validate-complete", action="store_true")
    parser.add_argument("--package-upload", action="store_true")
    parser.add_argument("--restore-durable", action="store_true")
    parser.add_argument("--takeover-restore", action="store_true")
    parser.add_argument("--operator-name")
    parser.add_argument("--process-stopped-attestation", type=Path)
    parser.add_argument("--generate-handoffs", type=Path)
    parser.add_argument("--implementation-commit")
    args = parser.parse_args()
    actions = [args.validate_shard, args.environment_preflight, args.acquire_inputs, args.reconstruct_caches, args.run, bool(args.worker), args.status, args.validate_complete, args.package_upload, args.restore_durable, args.takeover_restore, bool(args.generate_handoffs)]
    authority.require(sum(bool(value) for value in actions) == 1, "choose exactly one shard action")
    if args.acquire_inputs:
        print(json.dumps(acquire_inputs(), indent=2, sort_keys=True))
        return 0
    if args.reconstruct_caches:
        print(json.dumps(reconstruct_caches(), indent=2, sort_keys=True))
        return 0
    if args.generate_handoffs:
        authority.require(bool(args.implementation_commit), "--implementation-commit required")
        print(json.dumps(generate_handoffs(args.generate_handoffs, args.implementation_commit), indent=2, sort_keys=True))
        return 0
    authority.require(args.shard_manifest is not None and args.common_authority is not None, "shard and common authority paths required")
    shard, _common, parent, _shards = load_context(args.shard_manifest, args.common_authority)
    configure_namespace(shard)
    if args.validate_shard:
        p11.validate_manifest(require_p10_complete=True)
        print(f"PASS immutable P11 shard {shard['worker_name']} {shard['expected_seed_count']} seeds/{shard['expected_job_count']} jobs")
    elif args.environment_preflight:
        print(json.dumps(environment_preflight(shard, args.bootstrap_receipt), indent=2, sort_keys=True))
    elif args.restore_durable or args.takeover_restore:
        authority.require(bool(args.operator_name), "--operator-name required for restoration")
        if args.takeover_restore:
            authority.require(args.process_stopped_attestation is not None, "takeover requires --process-stopped-attestation")
        else:
            authority.require(args.process_stopped_attestation is None, "stopped-process attestation is takeover-only")
        print(json.dumps(
            restore_durable_state(
                shard, parent, operator_name=args.operator_name,
                takeover_attestation=args.process_stopped_attestation,
            ), indent=2, sort_keys=True,
        ))
    elif args.run:
        authority.require(args.resume, "distributed execution requires explicit --resume")
        run_shard(args.shard_manifest, args.common_authority, shard, parent)
        print(f"PASS P11 shard {shard['worker_name']} complete")
    elif args.worker:
        execute_assigned_worker(shard, args.worker)
    elif args.status:
        print(json.dumps(status_document(shard, parent), indent=2, sort_keys=True))
    elif args.validate_complete:
        print(json.dumps(validate_complete(shard, parent), indent=2, sort_keys=True))
    else:
        print(json.dumps(package_upload(shard, parent), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
