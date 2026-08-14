"""Restart-safe Regime-A A4 orchestration and S3 durability.

The workers are deliberately injected: production uses the repository's live
capture and MineWorld adapters, while focused tests use synthetic workers.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import urlparse

from mineocclude.regime_a import (
    AtomicTrajectoryStore,
    COMPLETE_STATE,
    HashChainLedger,
    RegimeAError,
    canonical_sha256,
    sha256_file,
)


REQUIRED_TRAJECTORY_FILES = (
    "raw/server_state.jsonl",
    "raw/client_tick.jsonl",
    "raw/actions.jsonl",
    "raw/frame_map.jsonl",
    "raw/visibility.jsonl",
    "coordinates.jsonl",
    "activation_inventory.json",
    "completion.json",
    "durable_receipt.json",
)


class CaptureWorker(Protocol):
    def capture(self, spec: Mapping[str, Any], partial: Path) -> None: ...

    def close(self) -> None: ...


class ModelWorker(Protocol):
    load_count: int

    def extract(self, spec: Mapping[str, Any], partial: Path) -> None: ...

    def close(self) -> None: ...


def _json_new(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with path.open("x", encoding="utf-8") as stream:
        stream.write(payload)
        stream.flush()


def validate_required_inventory(root: Path, *, durable: bool) -> list[dict[str, Any]]:
    required = REQUIRED_TRAJECTORY_FILES if durable else REQUIRED_TRAJECTORY_FILES[:-2]
    missing = [relative for relative in required if not (root / relative).is_file()]
    if missing:
        raise RegimeAError(f"trajectory required inventory missing: {missing}")
    activation = json.loads((root / "activation_inventory.json").read_text())
    if activation.get("layer_indices") != list(range(20)) or activation.get("target_tau") != list(range(1, 20)):
        raise RegimeAError("activation inventory is not the frozen 20-layer/19-target set")
    artifacts = activation.get("artifacts")
    if (
        not isinstance(artifacts, list)
        or len(artifacts) != 20
        or {row.get("layer_idx") for row in artifacts} != set(range(20))
    ):
        raise RegimeAError("activation inventory is not one complete artifact per frozen layer")
    for row in artifacts:
        relative = str(row.get("path", ""))
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts:
            raise RegimeAError("unsafe activation artifact path")
        path = root.joinpath(*pure.parts)
        if (
            not path.is_file()
            or path.stat().st_size != row.get("byte_size")
            or sha256_file(path) != row.get("sha256")
        ):
            raise RegimeAError("activation artifact size/hash mismatch")
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "byte_size": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


class S3DurableStore:
    """Publish and literally re-download every trajectory object."""

    def __init__(self, prefix: str, client: Any | None = None):
        parsed = urlparse(prefix)
        if parsed.scheme != "s3" or not parsed.netloc:
            raise RegimeAError("durable prefix must be an s3:// URI")
        self.bucket = parsed.netloc
        self.prefix = parsed.path.strip("/")
        if not self.prefix:
            raise RegimeAError("durable prefix must include a non-root key prefix")
        if client is None:
            try:
                import boto3
            except ImportError as error:
                raise RegimeAError("boto3 is required for S3 durability") from error
            client = boto3.client("s3")
        self.client = client

    def key_for(self, spec_id: str, relative: str) -> str:
        pure = PurePosixPath(relative)
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            raise RegimeAError("unsafe durable object relative path")
        return f"{self.prefix}/{spec_id}/{pure.as_posix()}"

    def _upload_and_verify(
        self, path: Path, key: str, spec_id: str, spec_hash: str
    ) -> dict[str, Any]:
        digest = sha256_file(path)
        size = path.stat().st_size
        metadata = {
            "sha256": digest,
            "trajectory-spec-id": spec_id,
            "spec-hash": spec_hash,
        }
        with path.open("rb") as stream:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=stream,
                Metadata=metadata,
                ChecksumAlgorithm="SHA256",
            )
        head = self.client.head_object(Bucket=self.bucket, Key=key)
        observed_metadata = {str(k).lower(): str(v) for k, v in head.get("Metadata", {}).items()}
        if int(head.get("ContentLength", -1)) != size or observed_metadata != metadata:
            raise RegimeAError("S3 size or SHA256 metadata verification failed")
        body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"]
        downloaded = hashlib.sha256()
        downloaded_size = 0
        while block := body.read(8 << 20):
            downloaded.update(block)
            downloaded_size += len(block)
        if downloaded_size != size or downloaded.hexdigest() != digest:
            raise RegimeAError("S3 downloaded-byte verification failed")
        return {
            "bucket": self.bucket,
            "key": key,
            "byte_size": size,
            "local_sha256": digest,
            "uploaded_object_verified": True,
            "downloaded_bytes_verified": True,
            "trajectory_spec_id": spec_id,
            "spec_hash": spec_hash,
            "checksum_sha256_base64": base64.b64encode(bytes.fromhex(digest)).decode("ascii"),
        }

    def publish(self, final: Path, spec: Mapping[str, Any]) -> dict[str, Any]:
        spec_id = str(spec["trajectory_spec_id"])
        spec_hash = str(spec["spec_hash"])
        validate_required_inventory(final, durable=False)
        receipt_path = final / "durable_receipt.json"
        if receipt_path.exists():
            receipt_path.unlink()
        objects = []
        for path in sorted(final.rglob("*")):
            if path.is_file() and path != receipt_path:
                relative = path.relative_to(final).as_posix()
                objects.append(
                    self._upload_and_verify(
                        path, self.key_for(spec_id, relative), spec_id, spec_hash
                    )
                )
        receipt = {
            "schema_version": "regime-a-s3-durable-receipt-v1.0",
            "status": "VERIFIED_DURABLE",
            "durable_prefix": f"s3://{self.bucket}/{self.prefix}/",
            "trajectory_spec_id": spec_id,
            "spec_hash": spec_hash,
            "object_count_excluding_receipt": len(objects),
            "objects": objects,
            "verification": "FULL_DOWNLOADED_BYTES_SHA256_EVERY_OBJECT",
        }
        _json_new(receipt_path, receipt)
        receipt_object = self._upload_and_verify(
            receipt_path,
            self.key_for(spec_id, "durable_receipt.json"),
            spec_id,
            spec_hash,
        )
        validate_required_inventory(final, durable=True)
        return {**receipt, "durable_receipt_object": receipt_object}


class A4ExecutionRunner:
    def __init__(
        self,
        *,
        store: AtomicTrajectoryStore,
        ledger: HashChainLedger,
        capture_worker: CaptureWorker,
        model_worker: ModelWorker,
        durable_store: S3DurableStore,
    ):
        self.store = store
        self.ledger = ledger
        self.capture_worker = capture_worker
        self.model_worker = model_worker
        self.durable_store = durable_store

    def _last_state(self, spec_id: str) -> str | None:
        return next(
            (str(row["state"]) for row in reversed(self.ledger.records) if row["trajectory_spec_id"] == spec_id),
            None,
        )

    def _finish_durability(self, spec: Mapping[str, Any], final: Path) -> None:
        spec_id, spec_hash = str(spec["trajectory_spec_id"]), str(spec["spec_hash"])
        state = self._last_state(spec_id)
        if state not in {"VALIDATED", "DURABLE"}:
            self.ledger.append(
                spec_id,
                "VALIDATED",
                spec_hash=spec_hash,
                completion_sha256=sha256_file(final / "completion.json"),
            )
        receipt = self.durable_store.publish(final, spec)
        if self._last_state(spec_id) != "DURABLE":
            self.ledger.append(
                spec_id,
                "DURABLE",
                spec_hash=spec_hash,
                durable_receipt_sha256=sha256_file(final / "durable_receipt.json"),
                durable_object_count=receipt["object_count_excluding_receipt"] + 1,
                durable_receipt_object=receipt["durable_receipt_object"],
            )
        self.ledger.append(spec_id, COMPLETE_STATE, spec_hash=spec_hash)

    def run(self, specs: Sequence[Mapping[str, Any]]) -> list[str]:
        completed = self.ledger.complete_ids()
        dispatched: list[str] = []
        try:
            for spec in specs:
                spec_id, spec_hash = str(spec["trajectory_spec_id"]), str(spec["spec_hash"])
                if spec_id in completed:
                    continue
                final = self.store.root / spec_id
                if final.exists():
                    self.store.validate(spec_id, spec_hash)
                    self._finish_durability(spec, final)
                    completed.add(spec_id)
                    continue
                partial = self.store.same_spec_partial(spec_id, spec_hash)
                last_state = self._last_state(spec_id)
                resume_packaged = getattr(
                    self.capture_worker, "resume_packaged_capture", None
                )
                packaged_resume = bool(
                    partial is not None
                    and last_state == "CAPTURED"
                    and callable(resume_packaged)
                    and resume_packaged(spec, partial)
                )
                if partial is not None and last_state == "CAPTURED" and not callable(
                    resume_packaged
                ):
                    packaged_resume = True
                resume_capture = getattr(self.capture_worker, "resume_capture", None)
                resumed = bool(
                    not packaged_resume
                    and partial is not None
                    and callable(resume_capture)
                    and resume_capture(spec, partial)
                )
                if packaged_resume:
                    dispatched.append(spec_id)
                elif resumed:
                    dispatched.append(spec_id)
                    self.ledger.append(
                        spec_id,
                        "CAPTURED",
                        spec_hash=spec_hash,
                        resumed_existing_raw_capture=True,
                    )
                else:
                    retried = self.store.discard_same_spec_partial(spec_id, spec_hash)
                    self.ledger.append(spec_id, "PLANNED", spec_hash=spec_hash, seed=int(spec["seed"]), retry_same_spec=retried)
                    partial = self.store.begin(spec_id, spec_hash)
                    self.ledger.append(spec_id, "RUNNING", spec_hash=spec_hash, seed=int(spec["seed"]), retry_same_spec=retried)
                    dispatched.append(spec_id)
                    self.capture_worker.capture(spec, partial)
                    self.ledger.append(spec_id, "CAPTURED", spec_hash=spec_hash)
                assert partial is not None
                self.model_worker.extract(spec, partial)
                validate_required_inventory(partial, durable=False)
                final = self.store.finalize(partial, spec_id, spec_hash)
                self.store.validate(spec_id, spec_hash)
                self._finish_durability(spec, final)
                completed.add(spec_id)
        finally:
            self.capture_worker.close()
            self.model_worker.close()
        return dispatched
