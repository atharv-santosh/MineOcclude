"""Verify Person A's Step 4.1 preprocessed-frame handoff (v0.2).

Reads and checks an already-loaded ``preprocessed_frame_manifest.json``
(the real one is 1,695 records / ~6.4MB, committed only on Person A's
``role/person-a-model`` at commit
``380b9a392c7ad3a941dbdadcc777c61ed03e1206`` -- read directly via Git
object access, never merged, never copied into this repository). This
module never touches a frame payload byte and never writes to Person
A's output root; it only validates the manifest's own declared
identities and summary counts.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mineocclude.baselines.baseline_family_input_v0_2 import (
    FROZEN_DIRECT_INPUTS,
    FROZEN_PILOT_IDS,
    is_valid_artifact_reference,
)

#: Person A's Step 4.1 frame-handoff commit and the exact literal
#: manifest-file SHA-256 it produced -- both required for the frozen
#: production CLI to bind an unambiguous input identity.
PERSON_A_FRAME_HANDOFF_COMMIT = "380b9a392c7ad3a941dbdadcc777c61ed03e1206"
PERSON_A_FRAME_MANIFEST_PATH = (
    "docs/status/person_a_phase4_step4_1_frame_handoff_v0_2/"
    "preprocessed_frame_manifest.json"
)
PERSON_A_FRAME_MANIFEST_SHA256 = (
    "f52a2ece32b00faf04b68b92b56c6f6a049b8a7bcb9c7f0af0f52de7fc4759c5"
)
PERSON_A_EXTERNAL_FRAME_ROOT = (
    "/home/sagemaker-user/person-a-step4-1-approved-outputs/"
    "person-a-step4-1-preprocessed-frames-v0-1"
)

REQUIRED_FRAME_ARTIFACT_COUNT = 1695
REQUIRED_ACCEPTED_PILOT_COUNT = 10
REQUIRED_SOURCE_CONTEXT_ARTIFACT_COUNT = 10

#: Frozen per-payload preprocessing facts, copied from Person A's own
#: committed sample record (commit 380b9a3) and required to hold for
#: every one of the 1,695 payloads -- not invented independently.
REQUIRED_PAYLOAD_DTYPE = "float32"
REQUIRED_PAYLOAD_LAYOUT = "CHW"
REQUIRED_PAYLOAD_COLOR_ORDER = "RGB"
REQUIRED_PAYLOAD_FORMAT = "raw-little-endian-float32-c-order"
REQUIRED_PAYLOAD_SHAPE = (3, 224, 384)


def _valid_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def verify_frame_manifest_summary_counts(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    """Check the manifest's own declared summary fields against the frozen facts.

    Every count here is required to equal the exact value Person A's
    own ``validation_receipt.json`` records at commit
    ``380b9a3`` -- this function does not invent a different threshold.
    """

    if not isinstance(manifest, Mapping):
        return ("manifest_not_mapping",)

    errors: list[str] = []
    if manifest.get("artifact_count") != REQUIRED_FRAME_ARTIFACT_COUNT:
        errors.append("artifact_count_mismatch")
    if manifest.get("unique_frame_count") != REQUIRED_FRAME_ARTIFACT_COUNT:
        errors.append("unique_frame_count_mismatch")
    if manifest.get("duplicate_frame_count") != 0:
        errors.append("duplicate_frame_count_nonzero")
    if manifest.get("missing_frame_count") != 0:
        errors.append("missing_frame_count_nonzero")
    if manifest.get("fold_manifest_sha256") != FROZEN_DIRECT_INPUTS["fold_manifest"]["sha256"]:
        errors.append("fold_manifest_sha256_mismatch")
    if manifest.get("target_manifest_sha256") != FROZEN_DIRECT_INPUTS["oracle_target"]["sha256"]:
        errors.append("target_manifest_sha256_mismatch")
    records = manifest.get("records")
    if not isinstance(records, list) or len(records) != REQUIRED_FRAME_ARTIFACT_COUNT:
        errors.append("records_count_mismatch")
    return tuple(errors)


def verify_frame_manifest_records(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    """Check every individual frame record's identity, hash, and size.

    Fails closed on: a changed/invalid payload SHA-256, a non-positive
    or missing byte size, a duplicate ``artifact_id`` or
    ``(trajectory_id, model_frame_idx)`` key, and any pilot not in the
    frozen ten-pilot set.
    """

    records = manifest.get("records") if isinstance(manifest, Mapping) else None
    if not isinstance(records, list):
        return ("records_not_a_list",)

    errors: list[str] = []
    seen_artifact_ids: set[str] = set()
    seen_frame_keys: set[tuple] = set()
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            errors.append(f"record[{index}]:not_a_mapping")
            continue
        artifact_id = record.get("artifact_id")
        if not isinstance(artifact_id, str) or not artifact_id:
            errors.append(f"record[{index}]:invalid_artifact_id")
        elif artifact_id in seen_artifact_ids:
            errors.append(f"record[{index}]:duplicate_artifact_id")
        else:
            seen_artifact_ids.add(artifact_id)

        if not _valid_sha256(record.get("payload_sha256")):
            errors.append(f"record[{index}]:invalid_payload_sha256")
        byte_size = record.get("payload_byte_size")
        if not isinstance(byte_size, int) or isinstance(byte_size, bool) or byte_size <= 0:
            errors.append(f"record[{index}]:invalid_payload_byte_size")

        trajectory_id = record.get("trajectory_id")
        model_frame_idx = record.get("model_frame_idx")
        if trajectory_id not in FROZEN_PILOT_IDS:
            errors.append(f"record[{index}]:unauthorized_pilot")
        if not isinstance(model_frame_idx, int) or isinstance(model_frame_idx, bool):
            errors.append(f"record[{index}]:invalid_model_frame_idx")
        else:
            key = (trajectory_id, model_frame_idx)
            if key in seen_frame_keys:
                errors.append(f"record[{index}]:duplicate_frame_identity")
            seen_frame_keys.add(key)

        fold_binding = record.get("fold_binding")
        if not isinstance(fold_binding, Mapping) or not isinstance(
            fold_binding.get("fold_idx"), int
        ) or isinstance(fold_binding.get("fold_idx"), bool):
            errors.append(f"record[{index}]:invalid_fold_binding")

    return tuple(errors)


def verify_frame_manifest_raw_bytes(manifest_path: Path) -> tuple[str, ...]:
    """Verify the manifest *file's own raw bytes* before trusting its parsed content.

    This must run before ``json.loads`` is trusted for anything: a
    byte-identical file is the only basis for claiming the manifest is
    genuinely Person A's committed one, independent of whatever its
    parsed JSON claims about itself.
    """

    if not manifest_path.exists():
        return ("manifest_file_not_found",)
    raw = manifest_path.read_bytes()
    errors: list[str] = []
    actual_sha256 = hashlib.sha256(raw).hexdigest()
    if actual_sha256 != PERSON_A_FRAME_MANIFEST_SHA256:
        errors.append(
            f"raw_sha256_mismatch:expected={PERSON_A_FRAME_MANIFEST_SHA256}:"
            f"actual={actual_sha256}"
        )
    return tuple(errors)


@dataclass(frozen=True)
class FramePayloadVerificationResult:
    expected_frame_count: int
    actual_frame_count: int
    missing_frame_count: int
    duplicate_frame_count: int
    size_mismatch_count: int
    hash_mismatch_count: int
    identity_mismatch_count: int
    preprocessing_mismatch_count: int
    errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def all_clear(self) -> bool:
        return (
            self.actual_frame_count == self.expected_frame_count
            and self.missing_frame_count == 0
            and self.duplicate_frame_count == 0
            and self.size_mismatch_count == 0
            and self.hash_mismatch_count == 0
            and self.identity_mismatch_count == 0
            and self.preprocessing_mismatch_count == 0
        )


def verify_frame_payloads_on_disk(
    manifest: Mapping[str, Any], *, frame_root: Path
) -> FramePayloadVerificationResult:
    """Verify every one of the 1,695 external frame payloads on disk.

    For every record: resolves its path from the exact manifest,
    requires the file to exist, and requires its actual byte size and
    SHA-256 to equal the manifest's declared values -- never trusting
    the manifest's own claims about a file this function can directly
    read. Also checks per-record identity/preprocessing consistency
    (``global_frame_identity`` matches ``trajectory_id``:
    ``model_frame_idx``; ``target_binding.target_id`` matches the
    frozen naming rule; dtype/layout/color_order/payload_format/shape
    match the one frozen preprocessing profile every payload must
    share) without touching any U4 path.
    """

    records = manifest.get("records") if isinstance(manifest, Mapping) else None
    if not isinstance(records, list):
        return FramePayloadVerificationResult(
            expected_frame_count=REQUIRED_FRAME_ARTIFACT_COUNT,
            actual_frame_count=0,
            missing_frame_count=REQUIRED_FRAME_ARTIFACT_COUNT,
            duplicate_frame_count=0,
            size_mismatch_count=0,
            hash_mismatch_count=0,
            identity_mismatch_count=0,
            preprocessing_mismatch_count=0,
            errors=("records_not_a_list",),
        )

    errors: list[str] = []
    seen_keys: set[tuple] = set()
    missing = duplicate = size_mismatch = hash_mismatch = identity_mismatch = 0
    preprocessing_mismatch = 0

    for record in records:
        if not isinstance(record, Mapping):
            missing += 1
            errors.append("record_not_a_mapping")
            continue
        trajectory_id = record.get("trajectory_id")
        model_frame_idx = record.get("model_frame_idx")
        key = (trajectory_id, model_frame_idx)
        if key in seen_keys:
            duplicate += 1
            errors.append(f"{key}:duplicate_payload_identity")
            continue
        seen_keys.add(key)

        relative_path = record.get("output_relative_path")
        if not isinstance(relative_path, str) or not relative_path:
            missing += 1
            errors.append(f"{key}:missing_output_relative_path")
            continue
        full_path = frame_root / relative_path
        if not full_path.exists():
            missing += 1
            errors.append(f"{key}:file_missing:{full_path}")
            continue

        payload = full_path.read_bytes()
        expected_size = record.get("payload_byte_size")
        if len(payload) != expected_size:
            size_mismatch += 1
            errors.append(
                f"{key}:size_mismatch:expected={expected_size}:actual={len(payload)}"
            )
        expected_hash = record.get("payload_sha256")
        actual_hash = hashlib.sha256(payload).hexdigest()
        if actual_hash != expected_hash:
            hash_mismatch += 1
            errors.append(f"{key}:hash_mismatch")

        expected_global_identity = f"{trajectory_id}:{model_frame_idx}"
        if record.get("global_frame_identity") != expected_global_identity:
            identity_mismatch += 1
            errors.append(f"{key}:global_frame_identity_mismatch")
        target_binding = record.get("target_binding")
        expected_target_id = f"{trajectory_id}:{model_frame_idx}:regime_a_primary_v1"
        if (
            not isinstance(target_binding, Mapping)
            or target_binding.get("target_id") != expected_target_id
        ):
            identity_mismatch += 1
            errors.append(f"{key}:target_binding_mismatch")
        fold_binding = record.get("fold_binding")
        if not isinstance(fold_binding, Mapping) or not isinstance(
            fold_binding.get("fold_idx"), int
        ) or isinstance(fold_binding.get("fold_idx"), bool):
            identity_mismatch += 1
            errors.append(f"{key}:fold_binding_mismatch")

        if record.get("dtype") != REQUIRED_PAYLOAD_DTYPE:
            preprocessing_mismatch += 1
            errors.append(f"{key}:dtype_mismatch")
        if record.get("layout") != REQUIRED_PAYLOAD_LAYOUT:
            preprocessing_mismatch += 1
            errors.append(f"{key}:layout_mismatch")
        if record.get("color_order") != REQUIRED_PAYLOAD_COLOR_ORDER:
            preprocessing_mismatch += 1
            errors.append(f"{key}:color_order_mismatch")
        if record.get("payload_format") != REQUIRED_PAYLOAD_FORMAT:
            preprocessing_mismatch += 1
            errors.append(f"{key}:payload_format_mismatch")
        shape = record.get("shape")
        if not isinstance(shape, list) or tuple(shape) != REQUIRED_PAYLOAD_SHAPE:
            preprocessing_mismatch += 1
            errors.append(f"{key}:shape_mismatch")

    return FramePayloadVerificationResult(
        expected_frame_count=REQUIRED_FRAME_ARTIFACT_COUNT,
        actual_frame_count=len(seen_keys),
        missing_frame_count=missing,
        duplicate_frame_count=duplicate,
        size_mismatch_count=size_mismatch,
        hash_mismatch_count=hash_mismatch,
        identity_mismatch_count=identity_mismatch,
        preprocessing_mismatch_count=preprocessing_mismatch,
        errors=tuple(errors),
    )


def build_frame_manifest_direct_input_reference(*, byte_size: int) -> dict:
    """Build the compact ``{path, sha256, byte_size}`` reference for ``direct_inputs``.

    ``byte_size`` must come from an actual local file stat of the real
    manifest (available only where Person A's committed manifest is
    checked out, e.g. on the frozen production CLI's SageMaker root) --
    this function never reads or copies that file itself.
    """

    if not isinstance(byte_size, int) or isinstance(byte_size, bool) or byte_size <= 0:
        raise ValueError("byte_size must be a positive integer")
    reference = {
        "path": PERSON_A_FRAME_MANIFEST_PATH,
        "sha256": PERSON_A_FRAME_MANIFEST_SHA256,
        "byte_size": byte_size,
    }
    if not is_valid_artifact_reference(reference):
        raise ValueError("constructed frame-manifest reference is invalid")
    return reference
