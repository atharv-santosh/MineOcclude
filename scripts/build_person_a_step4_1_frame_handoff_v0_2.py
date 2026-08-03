#!/usr/bin/env python3
"""Materialize and validate the complete Person A Step 4.1 frame handoff.

The command reuses the accepted Phase 6 decoder and preprocessor without
loading a model.  It writes only exact admitted-frame tensor bytes outside
Git and publishes bounded canonical-JSON lineage inside Git.  Existing frame
bytes are verification-only: a mismatch fails and is never overwritten.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import os
import platform
import stat
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

PACKAGE_REL = Path("docs/status/person_a_phase4_step4_1_frame_handoff_v0_2")
PACKAGE_ROOT = ROOT / PACKAGE_REL
OUTPUT_ROOT = Path(
    "/home/sagemaker-user/person-a-step4-1-approved-outputs/"
    "person-a-step4-1-preprocessed-frames-v0-1"
)
PREVIOUS_PACKAGE_REL = Path("docs/status/person_a_phase4_step4_1_frame_handoff_v0_1")
PREVIOUS_BUILDER = ROOT / "scripts/build_person_a_step4_1_frame_handoff_v0_1.py"

PREVIOUS_HANDOFF_COMMIT = "2799c1e95e4b3a7f65cd02e6557568a556010933"
PHASE6_AUTHORITY = "55776dc88302b89b52eef483a710fbf6811cf536"
PERSON_B_CONTRACT_COMMIT = "265cbbb394ee481439397879ad9a99c9038bf4cd"
PERSON_B_RATIFICATION_COMMIT = "c9a519b42cf651e05f5b4f640fda6e1a0aed3e7c"
PERSON_E_HANDOFF_COMMIT = "21d83c19c9d8f36c4dbeeaf45d4626eaf082e7a7"
PERSON_E_ACCEPTANCE_COMMIT = "5bbe7c7021fe3b1c4c35c78fadfbd92ab51484e8"
PERSON_D_AUTHORITY = "853e0acadf050a0b1f318b399b524e57379d03bf"

FOLD_SHA256 = "53ca938c6ae936c3ecb6e6e8d95a3fda152f5fa130b52e7a000d297810738d71"
TARGET_SHA256 = "afcf3afae00db6330665afc5964608c6db89eeac3767c9486d8ba0a218858282"
PREPROCESS_HASH = "036fa0b4899285e5499f88581f6e02426a25f732fcc26bd63c0f5b3863a9d9ab"
PREPROCESSING_PROFILE = (
    "mineworld_gradio_step_video_preprocessing@1.0:" + PREPROCESS_HASH
)

EXPECTED_BRANCH = "role/person-a-model"
EXPECTED_PILOT_COUNT = 10
EXPECTED_SOURCE_FRAME_COUNT = 1874
EXPECTED_ADMITTED_FRAME_COUNT = 1695
EXPECTED_EXCLUDED_FRAME_COUNT = 179
EXPECTED_EXTERNAL_SOURCE_FILE_COUNT = 90
FRAME_SHAPE = (3, 224, 384)
FRAME_DTYPE = "float32"
FRAME_PAYLOAD_SIZE = 3 * 224 * 384 * 4
SERIALIZATION_FORMAT = "raw-little-endian-float32-c-order"
FILENAME_TEMPLATE = "frames/{trajectory_id}/{model_frame_idx:06d}.f32le"
ARTIFACT_ID_TEMPLATE = (
    "person-a-step4-1-preprocessed-frame-v0-1::" "{trajectory_id}::{model_frame_idx}"
)

ACCEPTED_PILOTS = (
    "layout_00_ep9403",
    "layout_00_ep9441",
    "layout_01_ep9405",
    "layout_01_ep9442",
    "layout_02_ep9407",
    "layout_02_ep9432",
    "layout_03_ep9404",
    "layout_03_ep9443",
    "layout_04_ep9406",
    "layout_04_ep9444",
)
BASELINE_FAMILIES = (
    "last_seen",
    "constant_velocity",
    "grouped_shuffled",
    "time_only",
    "explicit_feature",
    "raw_pixel",
    "visible_history_q",
    "known_q_analytic",
)
SOURCE_CONTEXT_FAMILIES = frozenset(
    {
        "last_seen",
        "constant_velocity",
        "time_only",
        "explicit_feature",
        "visible_history_q",
        "known_q_analytic",
    }
)

PACKAGE_FILENAMES = (
    "authority_binding.json",
    "family_consumption_manifest.json",
    "handoff_decision.json",
    "preprocessed_frame_manifest.json",
    "preprocessing_and_serialization_contract.json",
    "source_context_manifest.json",
    "validation_receipt.json",
)


class MaterializationError(RuntimeError):
    """One fail-closed materialization or validation error."""


def fail(message: str) -> None:
    raise MaterializationError(message)


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(*arguments: str, binary: bool = False) -> bytes | str:
    result = subprocess.run(
        arguments,
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        fail(f"command failed ({' '.join(arguments)}): {detail}")
    if binary:
        return result.stdout
    return result.stdout.decode("utf-8", errors="strict").strip()


def git_object_bytes(commit: str, path: str) -> bytes:
    return run("git", "show", f"{commit}:{path}", binary=True)  # type: ignore[return-value]


def git_json(commit: str, path: str) -> Any:
    try:
        return json.loads(git_object_bytes(commit, path))
    except json.JSONDecodeError as error:
        fail(f"invalid JSON Git object {commit}:{path}: {error}")


def git_ref(commit: str, path: str, *, role: str) -> dict[str, object]:
    payload = git_object_bytes(commit, path)
    return {
        "byte_size": len(payload),
        "git_blob_oid": run("git", "rev-parse", f"{commit}:{path}"),
        "git_commit": commit,
        "path": path,
        "role": role,
        "sha256": sha256_bytes(payload),
    }


def load_previous_builder() -> ModuleType:
    specification = importlib.util.spec_from_file_location(
        "person_a_step4_1_frame_handoff_v0_1_builder",
        PREVIOUS_BUILDER,
    )
    if specification is None or specification.loader is None:
        fail("could not load the previous accepted handoff builder")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def repository_gate() -> None:
    if run("git", "branch", "--show-current") != EXPECTED_BRANCH:
        fail("materialization must remain on role/person-a-model")
    if (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", PREVIOUS_HANDOFF_COMMIT, "HEAD"],
            cwd=ROOT,
            check=False,
        ).returncode
        != 0
    ):
        fail("previous accepted handoff commit is not an ancestor of HEAD")
    if run("git", "rev-parse", PREVIOUS_HANDOFF_COMMIT) != PREVIOUS_HANDOFF_COMMIT:
        fail("previous accepted handoff Git object is unavailable")


def accepted_source_documents(
    previous: ModuleType,
) -> dict[str, object]:
    documents = previous.build_documents()
    previous.check_documents(documents)
    decision = documents["handoff_decision.json"]
    gap = documents["preprocessed_frame_gap_manifest.json"]
    source = documents["source_context_inventory.json"]
    preprocessing = documents["preprocessing_contract.json"]
    if (
        decision.get("status") != "FAIL_CLOSED_MISSING_PREPROCESSED_FRAME_DIRECT_INPUT"
        or decision.get("person_d_frame_handoff_ready") is not False
        or gap.get("missing_preprocessed_frame_count") != EXPECTED_ADMITTED_FRAME_COUNT
        or gap.get("preprocessed_frame_artifact_count") != 0
    ):
        fail("previous fail-closed handoff state drifted")
    if (
        source.get("accepted_pilot_count") != EXPECTED_PILOT_COUNT
        or tuple(source.get("accepted_pilot_ids", ())) != ACCEPTED_PILOTS
        or source.get("source_frame_count") != EXPECTED_SOURCE_FRAME_COUNT
        or source.get("admitted_frame_count") != EXPECTED_ADMITTED_FRAME_COUNT
        or source.get("fold_manifest_sha256") != FOLD_SHA256
        or source.get("target_manifest_sha256") != TARGET_SHA256
    ):
        fail("previous source-context inventory drifted")
    if (
        preprocessing.get("preprocess_hash") != PREPROCESS_HASH
        or preprocessing.get("preprocessing_profile") != PREPROCESSING_PROFILE
        or tuple(preprocessing.get("output_contract", {}).get("shape", ()))
        != FRAME_SHAPE
        or preprocessing.get("output_contract", {}).get("payload_byte_size")
        != FRAME_PAYLOAD_SIZE
    ):
        fail("accepted preprocessing contract drifted")
    return documents


def expected_rows(
    source_inventory: Mapping[str, object],
    gap_manifest: Mapping[str, object],
) -> tuple[list[Mapping[str, object]], dict[str, Mapping[str, object]]]:
    source_frames = source_inventory.get("source_frames")
    missing_artifacts = gap_manifest.get("missing_artifacts")
    if not isinstance(source_frames, list) or not isinstance(missing_artifacts, list):
        fail("accepted source/gap rows are unavailable")
    admitted: dict[tuple[str, int], Mapping[str, object]] = {}
    for row in source_frames:
        if not isinstance(row, Mapping):
            fail("source frame row is not a mapping")
        key = (row.get("trajectory_id"), row.get("model_frame_idx"))
        if not isinstance(key[0], str) or not isinstance(key[1], int):
            fail("source frame row has an invalid identity")
        if row.get("fold_binding", {}).get("status") == "admitted":
            if key in admitted:
                fail(f"duplicate admitted source identity: {key}")
            admitted[key] = row
    gap_by_key: dict[tuple[str, int], Mapping[str, object]] = {}
    for row in missing_artifacts:
        if not isinstance(row, Mapping):
            fail("gap row is not a mapping")
        key = (row.get("trajectory_id"), row.get("model_frame_idx"))
        if not isinstance(key[0], str) or not isinstance(key[1], int):
            fail("gap row has an invalid identity")
        if key in gap_by_key:
            fail(f"duplicate gap identity: {key}")
        gap_by_key[key] = row
    if (
        len(admitted) != EXPECTED_ADMITTED_FRAME_COUNT
        or len(gap_by_key) != EXPECTED_ADMITTED_FRAME_COUNT
        or set(admitted) != set(gap_by_key)
    ):
        fail("admitted source rows and the accepted gap do not match exactly")
    ordered = [
        admitted[(pilot, frame_idx)]
        for pilot in ACCEPTED_PILOTS
        for frame_idx in sorted(key[1] for key in admitted if key[0] == pilot)
    ]
    return ordered, {f"{key[0]}:{key[1]}": value for key, value in gap_by_key.items()}


def source_pilots(
    source_inventory: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    pilots = source_inventory.get("pilots")
    if not isinstance(pilots, list):
        fail("accepted pilot inventory is unavailable")
    by_id = {
        pilot.get("trajectory_id"): pilot
        for pilot in pilots
        if isinstance(pilot, Mapping)
    }
    if tuple(by_id) != ACCEPTED_PILOTS:
        fail("accepted pilot inventory identities or order drifted")
    return by_id  # type: ignore[return-value]


def import_preprocessing_runtime() -> tuple[Any, Any, Any, dict[str, object]]:
    try:
        numpy = importlib.import_module("numpy")
        cv2 = importlib.import_module("cv2")
        wave2 = importlib.import_module("mineocclude.models._mineworld_adapter_wave2")
        phase3 = importlib.import_module("mineocclude.models.phase3_certification")
    except Exception as error:  # noqa: BLE001
        fail(f"accepted preprocessing runtime is unavailable: {error}")
    if (
        wave2.PREPROCESSING_PROFILE != PREPROCESSING_PROFILE
        or wave2.MINEWORLD_PREPROCESS_BLOB_SHA256 != PREPROCESS_HASH
        or wave2.PINNED_SOURCE_WIDTH != 640
        or wave2.PINNED_SOURCE_HEIGHT != 360
    ):
        fail("imported accepted preprocessor identity drifted")
    accepted_files = (
        "src/mineocclude/models/_mineworld_adapter_wave2.py",
        "src/mineocclude/models/phase3_certification.py",
    )
    for relative_path in accepted_files:
        accepted = git_object_bytes(PHASE6_AUTHORITY, relative_path)
        if (ROOT / relative_path).read_bytes() != accepted:
            fail(f"accepted implementation worktree bytes drifted: {relative_path}")
    cv2_package_root = Path(cv2.__file__).resolve().parent
    cv2_binaries = tuple(sorted(cv2_package_root.glob("cv2*.so")))
    if len(cv2_binaries) != 1:
        fail(
            "accepted OpenCV runtime must expose exactly one native binary; "
            f"observed {len(cv2_binaries)}"
        )
    cv2_binary = cv2_binaries[0].resolve()
    numpy_binary = Path(numpy.core._multiarray_umath.__file__).resolve()
    libgl = Path("/opt/conda/lib/libGL.so.1").resolve()
    for dependency in (cv2_binary, numpy_binary, libgl):
        if not dependency.is_file():
            fail(f"existing preprocessing dependency is absent: {dependency}")
    runtime = {
        "cv2": {
            "binary_path": str(cv2_binary),
            "binary_sha256": sha256_file(cv2_binary),
            "version": cv2.__version__,
        },
        "environment_reused": True,
        "existing_environment_root": str(Path(sys.executable).resolve().parent.parent),
        "libgl": {
            "path": str(libgl),
            "sha256": sha256_file(libgl),
        },
        "library_installed_for_materialization": False,
        "model_loaded": False,
        "numpy": {
            "binary_path": str(numpy_binary),
            "binary_sha256": sha256_file(numpy_binary),
            "version": numpy.__version__,
        },
        "platform": platform.platform(),
        "python": {
            "executable": str(Path(sys.executable).resolve()),
            "version": platform.python_version(),
        },
    }
    return numpy, wave2, phase3, runtime


def frame_relative_path(trajectory_id: str, model_frame_idx: int) -> Path:
    return Path(
        FILENAME_TEMPLATE.format(
            trajectory_id=trajectory_id,
            model_frame_idx=model_frame_idx,
        )
    )


def exact_tensor_payload(
    frame: object,
    *,
    numpy: Any,
    wave2: Any,
) -> tuple[bytes, Mapping[str, object]]:
    tensor, evidence = wave2._preprocess_bgr_frame(frame)
    if (
        tuple(tensor.shape) != FRAME_SHAPE
        or str(tensor.dtype) != FRAME_DTYPE
        or not tensor.flags.c_contiguous
        or not numpy.isfinite(tensor).all()
        or float(tensor.min()) < -1.0
        or float(tensor.max()) > 1.0
        or tuple(evidence.get("output_shape", ())) != FRAME_SHAPE
        or evidence.get("output_dtype") != FRAME_DTYPE
    ):
        fail("accepted preprocessor emitted a contract-mismatched tensor")
    little_endian = tensor.astype(numpy.dtype("<f4"), copy=False)
    payload = little_endian.tobytes(order="C")
    if len(payload) != FRAME_PAYLOAD_SIZE or sha256_bytes(payload) != evidence.get(
        "output_sha256"
    ):
        fail("serialized tensor bytes do not match accepted content identity")
    round_trip = numpy.frombuffer(payload, dtype=numpy.dtype("<f4")).reshape(
        FRAME_SHAPE
    )
    if not numpy.array_equal(round_trip, tensor):
        fail("raw float32 serialization round trip changed the tensor")
    return payload, evidence


def verify_or_write_payload(path: Path, payload: bytes, *, creating: bool) -> None:
    if creating:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as handle:
                handle.write(payload)
        except FileExistsError:
            fail(f"staging payload unexpectedly exists: {path}")
        path.chmod(0o444)
    if not path.is_file() or path.is_symlink():
        fail(f"frame payload is absent or not an ordinary file: {path}")
    if path.stat().st_size != FRAME_PAYLOAD_SIZE:
        fail(f"frame payload size mismatch: {path}")
    if sha256_file(path) != sha256_bytes(payload):
        fail(f"frame payload hash mismatch; refusing overwrite: {path}")
    if stat.S_IMODE(path.stat().st_mode) & 0o222:
        fail(f"frame payload is not retained read-only: {path}")


def make_frame_record(
    source_row: Mapping[str, object],
    pilot: Mapping[str, object],
    gap_row: Mapping[str, object],
    evidence: Mapping[str, object],
    payload_sha256: str,
) -> dict[str, object]:
    trajectory_id = source_row["trajectory_id"]
    model_frame_idx = source_row["model_frame_idx"]
    relative = frame_relative_path(trajectory_id, model_frame_idx)
    if (
        gap_row.get("source_frame_id") != source_row.get("source_frame_id")
        or gap_row.get("source_tick") != source_row.get("source_tick")
        or gap_row.get("fold_idx") != source_row.get("fold_binding", {}).get("fold_idx")
    ):
        fail(f"gap/source lineage mismatch for {trajectory_id}:{model_frame_idx}")
    family_eligibility = {family: family == "raw_pixel" for family in BASELINE_FAMILIES}
    return {
        "accepted_c_manifest_sha256": source_row["accepted_c_manifest_sha256"],
        "artifact_id": ARTIFACT_ID_TEMPLATE.format(
            trajectory_id=trajectory_id,
            model_frame_idx=model_frame_idx,
        ),
        "c_frame_map_row_sha256": source_row["c_frame_map_row_sha256"],
        "c_frame_map_sha256": source_row["c_frame_map_sha256"],
        "c_state_row_sha256": source_row["c_state_row_sha256"],
        "c_state_sha256": source_row["c_state_sha256"],
        "color_order": "RGB",
        "content_sha256": payload_sha256,
        "context_idx": source_row["context_idx"],
        "context_local_pair_idx": source_row["context_local_pair_idx"],
        "direct_input_eligibility_by_family": family_eligibility,
        "dtype": FRAME_DTYPE,
        "fold_binding": source_row["fold_binding"],
        "global_frame_identity": source_row["global_frame_identity"],
        "global_model_frame_idx": source_row["global_model_frame_idx"],
        "layout": "CHW",
        "layout_id": source_row["layout_id"],
        "little_endian_dtype": "<f4",
        "materialization_authority": PREVIOUS_HANDOFF_COMMIT,
        "model_frame_idx": model_frame_idx,
        "normalized_value_range_inclusive": [-1.0, 1.0],
        "output_path": str(OUTPUT_ROOT / relative),
        "output_relative_path": relative.as_posix(),
        "payload_byte_size": FRAME_PAYLOAD_SIZE,
        "payload_format": SERIALIZATION_FORMAT,
        "payload_sha256": payload_sha256,
        "preprocess_hash": PREPROCESS_HASH,
        "preprocessing_profile": PREPROCESSING_PROFILE,
        "required_by_baseline_families": ["raw_pixel"],
        "shape": list(FRAME_SHAPE),
        "source_context_id": pilot["source_context_id"],
        "source_frame_id": source_row["source_frame_id"],
        "source_frame_idx": source_row["source_frame_idx"],
        "source_frame_sha256": evidence["source_sha256"],
        "source_media": pilot["source_artifacts"]["media"],
        "source_tick": source_row["source_tick"],
        "statistics": evidence["statistics"],
        "target_binding": source_row["target_binding"],
        "trajectory_id": trajectory_id,
    }


def materialize_frames(
    rows: Sequence[Mapping[str, object]],
    gap_by_identity: Mapping[str, Mapping[str, object]],
    pilots: Mapping[str, Mapping[str, object]],
    *,
    numpy: Any,
    wave2: Any,
    phase3: Any,
) -> tuple[list[dict[str, object]], bool]:
    creating = not OUTPUT_ROOT.exists()
    if OUTPUT_ROOT.is_symlink():
        fail("frame output root must not be a symlink")
    if not creating and not OUTPUT_ROOT.is_dir():
        fail("existing frame output root is not a directory")
    OUTPUT_ROOT.parent.mkdir(parents=True, exist_ok=True)
    staging = OUTPUT_ROOT.parent / f".{OUTPUT_ROOT.name}.staging-{os.getpid()}"
    active_root = OUTPUT_ROOT
    if creating:
        try:
            staging.mkdir()
        except FileExistsError:
            fail(f"exclusive staging root already exists: {staging}")
        active_root = staging

    rows_by_pilot = {
        pilot: [row for row in rows if row["trajectory_id"] == pilot]
        for pilot in ACCEPTED_PILOTS
    }
    records: list[dict[str, object]] = []
    expected_paths: set[Path] = set()
    for trajectory_id in ACCEPTED_PILOTS:
        pilot = pilots[trajectory_id]
        pilot_rows = rows_by_pilot[trajectory_id]
        indices = [row["source_frame_idx"] for row in pilot_rows]
        if len(indices) != len(set(indices)):
            fail(f"duplicate source frame index for {trajectory_id}")
        media = Path(pilot["source_artifacts"]["media"]["path"])
        decoded = phase3._decode_frames(media, indices)
        if len(decoded) != len(pilot_rows):
            fail(f"decoded admitted-frame count mismatch for {trajectory_id}")
        for source_row, frame in zip(pilot_rows, decoded, strict=True):
            payload, evidence = exact_tensor_payload(
                frame,
                numpy=numpy,
                wave2=wave2,
            )
            relative = frame_relative_path(
                source_row["trajectory_id"],
                source_row["model_frame_idx"],
            )
            expected_paths.add(relative)
            verify_or_write_payload(
                active_root / relative,
                payload,
                creating=creating,
            )
            identity = source_row["global_frame_identity"]
            records.append(
                make_frame_record(
                    source_row,
                    pilot,
                    gap_by_identity[identity],
                    evidence,
                    sha256_bytes(payload),
                )
            )

    observed_paths = {
        path.relative_to(active_root)
        for path in active_root.rglob("*")
        if path.is_file()
    }
    symlinks = [path for path in active_root.rglob("*") if path.is_symlink()]
    if symlinks:
        fail(f"frame output tree contains symlinks: {symlinks[:3]}")
    if observed_paths != expected_paths:
        missing = sorted(str(path) for path in expected_paths - observed_paths)
        extra = sorted(str(path) for path in observed_paths - expected_paths)
        fail(f"frame output file set mismatch; missing={missing[:3]} extra={extra[:3]}")
    if len(records) != EXPECTED_ADMITTED_FRAME_COUNT:
        fail("materialized frame cardinality mismatch")
    identities = {
        (record["trajectory_id"], record["model_frame_idx"]) for record in records
    }
    if len(identities) != EXPECTED_ADMITTED_FRAME_COUNT:
        fail("materialized frame identities are not unique")

    if creating:
        for directory in sorted(
            (path for path in active_root.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            directory.chmod(0o555)
        active_root.chmod(0o555)
        try:
            active_root.rename(OUTPUT_ROOT)
        except OSError as error:
            fail(f"could not atomically publish frame output root: {error}")
    if stat.S_IMODE(OUTPUT_ROOT.stat().st_mode) & 0o222:
        fail("published frame output root is not retained read-only")
    return records, creating


def determinism_self_test(
    rows: Sequence[Mapping[str, object]],
    pilots: Mapping[str, Mapping[str, object]],
    *,
    numpy: Any,
    wave2: Any,
    phase3: Any,
) -> dict[str, object]:
    sample_positions = (0, len(rows) // 2, len(rows) - 1)
    samples = []
    for position in sample_positions:
        row = rows[position]
        pilot = pilots[row["trajectory_id"]]
        media = Path(pilot["source_artifacts"]["media"]["path"])
        index = row["source_frame_idx"]
        first_frame = phase3._decode_frames(media, [index])[0]
        second_frame = phase3._decode_frames(media, [index])[0]
        first, first_evidence = exact_tensor_payload(
            first_frame,
            numpy=numpy,
            wave2=wave2,
        )
        second, second_evidence = exact_tensor_payload(
            second_frame,
            numpy=numpy,
            wave2=wave2,
        )
        if first != second or first_evidence != second_evidence:
            fail(
                f"preprocessing determinism mismatch for {row['global_frame_identity']}"
            )
        samples.append(
            {
                "global_frame_identity": row["global_frame_identity"],
                "payload_byte_size": len(first),
                "payload_sha256": sha256_bytes(first),
            }
        )
    return {
        "decoded_twice_per_sample": True,
        "determinism_mismatch_count": 0,
        "sample_count": len(samples),
        "samples": samples,
        "serialization_round_trip_verified": True,
        "status": "PASS",
    }


def preprocessing_contract(runtime: Mapping[str, object]) -> dict[str, object]:
    hash_scope = {
        "artifact_id_rule": ARTIFACT_ID_TEMPLATE,
        "filename_rule": FILENAME_TEMPLATE,
        "output_root": str(OUTPUT_ROOT),
        "payload_format": SERIALIZATION_FORMAT,
        "preprocess_hash": PREPROCESS_HASH,
        "preprocessing_profile": PREPROCESSING_PROFILE,
        "shape": list(FRAME_SHAPE),
    }
    contract_sha256 = sha256_bytes(canonical_json_bytes(hash_scope))
    return {
        "artifact_contract_id": (
            "person-a-step4-1-preprocessed-frame-artifact-v0.1:" + contract_sha256
        ),
        "artifact_contract_sha256": contract_sha256,
        "artifact_contract_sha256_scope": hash_scope,
        "artifact_id_rule": ARTIFACT_ID_TEMPLATE,
        "content_hash_rule": (
            "sha256(raw C-order bytes of the finite float32 CHW array); "
            "the payload file contains exactly those bytes"
        ),
        "decoder": {
            "accepted_function": (
                "mineocclude.models.phase3_certification._decode_frames"
            ),
            "color_order": "BGR",
            "implementation_authority": PHASE6_AUTHORITY,
            "source_dtype": "uint8",
            "source_shape": [360, 640, 3],
            "source_video_rule": (
                "the exact accepted per-pilot video_640x360.mp4 bound in "
                "source_context_manifest.json"
            ),
        },
        "filename_rule": FILENAME_TEMPLATE,
        "metadata_record_required_fields": [
            "artifact_id",
            "trajectory_id",
            "model_frame_idx",
            "global_frame_identity",
            "source_frame_id",
            "source_frame_idx",
            "source_tick",
            "fold_binding",
            "target_binding",
            "accepted_c_manifest_sha256",
            "c_frame_map_row_sha256",
            "c_state_row_sha256",
            "preprocess_hash",
            "preprocessing_profile",
            "output_path",
            "payload_format",
            "payload_byte_size",
            "payload_sha256",
            "shape",
            "dtype",
            "layout",
            "color_order",
            "direct_input_eligibility_by_family",
        ],
        "operations_in_order": [
            "decode the exact source_frame_idx with cv2.VideoCapture",
            "require source shape (360, 640, 3), dtype uint8, BGR, C-contiguous",
            "apply no crop and resize the complete RGB frame to width 384 and height 224",
            "convert BGR to RGB with cv2.cvtColor(COLOR_BGR2RGB)",
            "resize with cv2.INTER_LINEAR",
            "transpose HWC to CHW",
            "cast to float32 and divide by float32(255.0)",
            "normalize with (tensor - float32(0.5)) / float32(0.5)",
            "make the tensor C-contiguous",
            "serialize the exact tensor as little-endian float32 C-order bytes",
        ],
        "output_contract": {
            "byte_order": "little",
            "channels": 3,
            "color_order": "RGB",
            "dtype": FRAME_DTYPE,
            "height": 224,
            "layout": "CHW",
            "payload_byte_size": FRAME_PAYLOAD_SIZE,
            "payload_format": SERIALIZATION_FORMAT,
            "shape": list(FRAME_SHAPE),
            "value_range_inclusive": [-1.0, 1.0],
            "width": 384,
        },
        "preprocess_hash": PREPROCESS_HASH,
        "preprocessing_profile": PREPROCESSING_PROFILE,
        "preprocessor": {
            "accepted_function": (
                "mineocclude.models._mineworld_adapter_wave2._preprocess_bgr_frame"
            ),
            "implementation_authority": PHASE6_AUTHORITY,
            "new_image_library_used": False,
            "second_preprocessing_implementation_used": False,
        },
        "runtime_identity": runtime,
        "schema_id": "person-a-step4-1-frame-handoff-v0-2-preprocessing-and-serialization-contract",
        "schema_version": "1.0",
        "serialization_container": "none",
    }


def identity_set_sha256(rows: Sequence[Mapping[str, object]]) -> str:
    identities = [
        {
            "global_frame_identity": row["global_frame_identity"],
            "model_frame_idx": row["model_frame_idx"],
            "source_frame_id": row["source_frame_id"],
            "source_tick": row["source_tick"],
            "trajectory_id": row["trajectory_id"],
        }
        for row in rows
    ]
    return sha256_bytes(canonical_json_bytes(identities))


def build_documents(
    previous_documents: Mapping[str, object],
    records: Sequence[Mapping[str, object]],
    runtime: Mapping[str, object],
    self_test: Mapping[str, object],
) -> dict[str, object]:
    previous_source = previous_documents["source_context_inventory.json"]
    previous_gap = previous_documents["preprocessed_frame_gap_manifest.json"]
    previous_preprocessing = previous_documents["preprocessing_contract.json"]
    pilots = source_pilots(previous_source)

    fold_path = (
        "docs/status/person_b_phase4_step4_1_production_handoff_v0_1/"
        "ten_pilot_frame_fold_manifest.json"
    )
    target_path = (
        "docs/status/person_b_phase4_step4_1_production_handoff_v0_1/"
        "production_oracle_target_manifest.json"
    )
    fold_ref = git_ref(PERSON_B_RATIFICATION_COMMIT, fold_path, role="person_b")
    target_ref = git_ref(PERSON_B_RATIFICATION_COMMIT, target_path, role="person_b")
    if fold_ref["sha256"] != FOLD_SHA256 or target_ref["sha256"] != TARGET_SHA256:
        fail("fold or target authority hash drifted")

    previous_refs = {
        filename: git_ref(
            PREVIOUS_HANDOFF_COMMIT,
            (PREVIOUS_PACKAGE_REL / filename).as_posix(),
            role="person_a",
        )
        for filename in (
            "authority_binding.json",
            "handoff_decision.json",
            "preprocessed_frame_gap_manifest.json",
            "preprocessing_contract.json",
            "sha256_inventory.json",
            "source_context_inventory.json",
            "validation_receipt.json",
        )
    }
    authority_binding = {
        "authorities": {
            "person_a_phase6_completion": PHASE6_AUTHORITY,
            "person_a_previous_fail_closed_handoff": PREVIOUS_HANDOFF_COMMIT,
            "person_b_baseline_input_v0_2": PERSON_B_CONTRACT_COMMIT,
            "person_b_production_ratification": PERSON_B_RATIFICATION_COMMIT,
            "person_d_recorded_starting_authority": PERSON_D_AUTHORITY,
            "person_e_phase6_acceptance": PERSON_E_ACCEPTANCE_COMMIT,
            "person_e_phase6_to_step4_1_handoff": PERSON_E_HANDOFF_COMMIT,
        },
        "bindings": {
            "fold_manifest": fold_ref,
            "preprocess_hash": PREPROCESS_HASH,
            "preprocessing_profile": PREPROCESSING_PROFILE,
            "target_manifest": target_ref,
        },
        "materialization_boundary": {
            "activation_extraction_performed": False,
            "baseline_execution_performed": False,
            "model_loaded_or_executed": False,
            "probe_execution_performed": False,
            "source_trajectory_regenerated": False,
            "u4_output_inspected": False,
        },
        "person_a_accepted_implementation": [
            git_ref(
                PHASE6_AUTHORITY,
                "src/mineocclude/models/phase3_certification.py",
                role="person_a",
            ),
            git_ref(
                PHASE6_AUTHORITY,
                "src/mineocclude/models/_mineworld_adapter_wave2.py",
                role="person_a",
            ),
        ],
        "previous_handoff_package": previous_refs,
        "schema_id": "person-a-step4-1-frame-handoff-v0-2-authority-binding",
        "schema_version": "1.0",
        "supersedes_status_only": (
            "FAIL_CLOSED_MISSING_PREPROCESSED_FRAME_DIRECT_INPUT"
        ),
    }

    source_contexts = []
    for trajectory_id in ACCEPTED_PILOTS:
        pilot = pilots[trajectory_id]
        source_contexts.append(
            {
                "accepted_c_manifest_binding": pilot["accepted_c_manifest_binding"],
                "admitted_frame_count": pilot["admitted_frame_count"],
                "condition_role": pilot["condition_role"],
                "control": pilot["control"],
                "excluded_frame_count": pilot["excluded_frame_count"],
                "fold_idx": pilot["fold_idx"],
                "frame_count": pilot["frame_count"],
                "layout_id": pilot["layout_id"],
                "person_a_index_binding": pilot["person_a_index_binding"],
                "source_artifacts": pilot["source_artifacts"],
                "source_context_id": pilot["source_context_id"],
                "target_lineage": pilot["target_lineage"],
                "trajectory_id": trajectory_id,
            }
        )
    source_context_manifest = {
        "accepted_pilot_count": EXPECTED_PILOT_COUNT,
        "accepted_pilot_ids": list(ACCEPTED_PILOTS),
        "admitted_frame_count": EXPECTED_ADMITTED_FRAME_COUNT,
        "excluded_frame_count": EXPECTED_EXCLUDED_FRAME_COUNT,
        "external_referenced_file_count": EXPECTED_EXTERNAL_SOURCE_FILE_COUNT,
        "fold_manifest_sha256": FOLD_SHA256,
        "full_source_frame_inventory": previous_refs["source_context_inventory.json"],
        "schema_id": "person-a-step4-1-frame-handoff-v0-2-source-context-manifest",
        "schema_version": "1.0",
        "source_context_artifact_count": EXPECTED_PILOT_COUNT,
        "source_contexts": source_contexts,
        "source_frame_count": EXPECTED_SOURCE_FRAME_COUNT,
        "source_identity_set_sha256": identity_set_sha256(
            previous_source["source_frames"]
        ),
        "source_identities_verified": True,
        "target_manifest_sha256": TARGET_SHA256,
        "u4_output_inspected": False,
    }

    artifact_inventory = [
        {
            "artifact_id": record["artifact_id"],
            "output_relative_path": record["output_relative_path"],
            "payload_byte_size": record["payload_byte_size"],
            "payload_sha256": record["payload_sha256"],
        }
        for record in records
    ]
    preprocessed_frame_manifest = {
        "admitted_identity_set_sha256": identity_set_sha256(records),
        "artifact_count": len(records),
        "artifact_id_rule": ARTIFACT_ID_TEMPLATE,
        "artifact_inventory_sha256": sha256_bytes(
            canonical_json_bytes(artifact_inventory)
        ),
        "duplicate_frame_count": 0,
        "filename_rule": FILENAME_TEMPLATE,
        "fold_manifest_sha256": FOLD_SHA256,
        "immutable": True,
        "missing_frame_count": 0,
        "output_root": str(OUTPUT_ROOT),
        "payload_format": SERIALIZATION_FORMAT,
        "preprocess_hash": PREPROCESS_HASH,
        "preprocessing_profile": PREPROCESSING_PROFILE,
        "records": list(records),
        "retention_class": "retain_through_final_step4_1_closure_and_registry_v2_verification",
        "schema_id": "person-a-step4-1-preprocessed-frame-manifest-v0-1",
        "schema_version": "1.0",
        "target_manifest_sha256": TARGET_SHA256,
        "total_payload_byte_size": sum(
            record["payload_byte_size"] for record in records
        ),
        "unique_frame_count": len(records),
        "write_policy": "exclusive_create_no_overwrite_verify_existing_exactly",
    }

    b_contract_path = (
        "docs/status/person_b_phase4_step4_1_baseline_family_contract_v0_2/"
        "baseline_family_contract.json"
    )
    b_contract = git_json(PERSON_B_CONTRACT_COMMIT, b_contract_path)
    if (
        tuple(item["family_id"] for item in b_contract["baseline_families"])
        != BASELINE_FAMILIES
    ):
        fail("Person B eight-family contract drifted")
    families = []
    for item in b_contract["baseline_families"]:
        family_id = item["family_id"]
        if family_id == "raw_pixel":
            person_a_inputs = [
                "preprocessed_frame_manifest",
                "preprocessed_frame_payloads",
            ]
        elif family_id in SOURCE_CONTEXT_FAMILIES:
            person_a_inputs = ["source_context_manifest"]
        else:
            person_a_inputs = []
        families.append(
            {
                "definition": item["definition"],
                "family_id": family_id,
                "person_a_direct_inputs": person_a_inputs,
                "ready": True,
                "role": item["role"],
                "targets": item["targets"],
            }
        )
    family_consumption = {
        "baseline_family_count": 8,
        "baseline_families": families,
        "contract_authority": git_ref(
            PERSON_B_CONTRACT_COMMIT,
            b_contract_path,
            role="person_b",
        ),
        "fold_manifest": fold_ref,
        "person_b_predictions_direct_input_to_person_d": False,
        "preprocessed_frame_manifest_path": str(
            PACKAGE_ROOT / "preprocessed_frame_manifest.json"
        ),
        "schema_id": "person-a-step4-1-frame-handoff-v0-2-family-consumption-manifest",
        "schema_version": "1.0",
        "source_context_manifest_path": str(
            PACKAGE_ROOT / "source_context_manifest.json"
        ),
        "status": "ALL_EIGHT_FAMILY_DIRECT_INPUTS_AVAILABLE",
        "target_manifest": target_ref,
        "u4_output_inspected": False,
    }

    contract = preprocessing_contract(runtime)
    handoff_decision = {
        "all_required_artifacts_present": True,
        "all_required_hashes_verified": True,
        "all_required_sizes_verified": True,
        "baseline_execution_performed": False,
        "fold_manifest_bound": True,
        "immutable_artifact_requirements": [
            "retain the exact accepted Phase 6 source/input and output trees without overwrite, relocation, or deletion",
            "retain the exact read-only preprocessed-frame output root without overwrite, relocation, or deletion",
            "consume frame payloads only through explicit manifest identity, path, byte size, SHA-256, and preprocessing identity",
            "do not substitute source MP4, activations, or Person B predictions for preprocessed-frame direct inputs",
        ],
        "person_a_reextraction_authorized": False,
        "person_a_reextraction_required": False,
        "person_d_frame_handoff_ready": True,
        "preprocessed_frame_artifact_count": EXPECTED_ADMITTED_FRAME_COUNT,
        "preprocessed_frames_materialized": True,
        "preprocessed_frames_modified": False,
        "probe_execution_performed": False,
        "record_date": "2026-08-01",
        "retention_requirements": [
            {
                "path": "/home/sagemaker-user/person-a-phase6-approved-inputs",
                "requirement": "retain immutable accepted source contexts",
            },
            {
                "path": "/home/sagemaker-user/person-a-phase6-approved-outputs",
                "requirement": "retain accepted Phase 6 receipts and artifacts",
            },
            {
                "path": str(OUTPUT_ROOT),
                "requirement": "retain all 1,695 exact read-only frame payloads",
            },
        ],
        "schema_id": "person-a-step4-1-frame-handoff-v0-2-decision",
        "schema_version": "1.0",
        "scientific_execution_performed": False,
        "scientific_model_execution_performed": False,
        "source_contexts_modified": False,
        "source_identities_verified": True,
        "status": "COMPLETE_PREPROCESSED_FRAME_DIRECT_INPUT_HANDOFF",
        "superseded_handoff_commit": PREVIOUS_HANDOFF_COMMIT,
        "target_manifest_bound": True,
        "u4_output_inspected": False,
        "unresolved_blockers": [],
    }

    validation_receipt = {
        "accepted_pilot_count": EXPECTED_PILOT_COUNT,
        "actual_preprocessed_frame_count": len(records),
        "all_required_artifacts_present": True,
        "all_required_hashes_verified": True,
        "all_required_sizes_verified": True,
        "baseline_execution_performed": False,
        "canonical_json_generated": True,
        "duplicate_frame_count": 0,
        "exact_authority_git_objects_resolved": True,
        "external_referenced_source_file_count": EXPECTED_EXTERNAL_SOURCE_FILE_COUNT,
        "fold_manifest_bound": True,
        "fold_manifest_sha256_verified": True,
        "focused_validation_only": True,
        "hash_mismatch_count": 0,
        "missing_frame_count": 0,
        "output_root_created_by_initial_materialization": True,
        "person_a_reextraction_authorized": False,
        "person_a_reextraction_required": False,
        "person_b_v0_2_preprocessed_frame_direct_input_satisfied": True,
        "person_d_frame_handoff_ready": True,
        "preprocessing_determinism_check": self_test,
        "preprocessing_mismatch_count": 0,
        "probe_execution_performed": False,
        "required_preprocessed_frame_count": EXPECTED_ADMITTED_FRAME_COUNT,
        "schema_and_identity_checks_passed": True,
        "schema_id": "person-a-step4-1-frame-handoff-v0-2-validation-receipt",
        "schema_version": "1.0",
        "scientific_execution_performed": False,
        "scientific_model_execution_performed": False,
        "serialization_mismatch_count": 0,
        "size_mismatch_count": 0,
        "source_context_artifact_count": EXPECTED_PILOT_COUNT,
        "source_contexts_modified": False,
        "source_frame_identity_count": EXPECTED_SOURCE_FRAME_COUNT,
        "source_identities_verified": True,
        "status": "PASS_COMPLETE_PREPROCESSED_FRAME_HANDOFF",
        "target_manifest_bound": True,
        "target_manifest_sha256_verified": True,
        "u4_output_inspected": False,
        "unauthorized_pilot_count": 0,
        "unique_preprocessed_frame_count": len(records),
    }

    documents: dict[str, object] = {
        "authority_binding.json": authority_binding,
        "family_consumption_manifest.json": family_consumption,
        "handoff_decision.json": handoff_decision,
        "preprocessed_frame_manifest.json": preprocessed_frame_manifest,
        "preprocessing_and_serialization_contract.json": contract,
        "source_context_manifest.json": source_context_manifest,
        "validation_receipt.json": validation_receipt,
    }
    if not all(
        previous_documents.get(name) is not None
        for name in (
            "authority_binding.json",
            "handoff_decision.json",
            "preprocessed_frame_gap_manifest.json",
            "preprocessing_contract.json",
            "source_context_inventory.json",
            "validation_receipt.json",
        )
    ):
        fail("previous handoff package is incomplete")
    if previous_gap.get("missing_preprocessed_frame_count") != len(records):
        fail("materialized records do not exactly supersede the previous gap")
    if previous_preprocessing.get("preprocess_hash") != PREPROCESS_HASH:
        fail("previous preprocessing identity drifted")
    return documents


def inventory_bytes(documents: Mapping[str, object]) -> bytes:
    files = []
    for filename in PACKAGE_FILENAMES:
        payload = canonical_json_bytes(documents[filename])
        files.append(
            {
                "byte_size": len(payload),
                "path": filename,
                "sha256": sha256_bytes(payload),
            }
        )
    return canonical_json_bytes(
        {
            "algorithm": "sha256",
            "file_count": len(files),
            "files": files,
            "schema_id": "person-a-step4-1-frame-handoff-v0-2-sha256-inventory",
            "schema_version": "1.0",
        }
    )


def write_documents(documents: Mapping[str, object]) -> None:
    PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)
    expected_names = {*PACKAGE_FILENAMES, "sha256_inventory.json"}
    observed_names = {path.name for path in PACKAGE_ROOT.iterdir() if path.is_file()}
    if observed_names and observed_names != expected_names:
        fail("refusing to rewrite a package with an unexpected file set")
    for filename in PACKAGE_FILENAMES:
        (PACKAGE_ROOT / filename).write_bytes(canonical_json_bytes(documents[filename]))
    (PACKAGE_ROOT / "sha256_inventory.json").write_bytes(inventory_bytes(documents))


def check_documents(documents: Mapping[str, object]) -> None:
    expected_names = {*PACKAGE_FILENAMES, "sha256_inventory.json"}
    if not PACKAGE_ROOT.is_dir() or PACKAGE_ROOT.is_symlink():
        fail("committed package root is absent or invalid")
    observed_names = {path.name for path in PACKAGE_ROOT.iterdir() if path.is_file()}
    if observed_names != expected_names:
        fail("committed package file set mismatch")
    for filename in PACKAGE_FILENAMES:
        expected = canonical_json_bytes(documents[filename])
        observed = (PACKAGE_ROOT / filename).read_bytes()
        if observed != expected:
            fail(f"committed package drifted: {filename}")
        if canonical_json_bytes(json.loads(observed)) != observed:
            fail(f"committed package is not canonical JSON: {filename}")
    expected_inventory = inventory_bytes(documents)
    inventory_path = PACKAGE_ROOT / "sha256_inventory.json"
    if inventory_path.read_bytes() != expected_inventory:
        fail("committed SHA-256 inventory drifted")
    if canonical_json_bytes(json.loads(expected_inventory)) != expected_inventory:
        fail("committed SHA-256 inventory is not canonical JSON")


def execute(*, check: bool, self_test_only: bool) -> dict[str, object]:
    repository_gate()
    previous = load_previous_builder()
    previous_documents = accepted_source_documents(previous)
    rows, gap_by_identity = expected_rows(
        previous_documents["source_context_inventory.json"],
        previous_documents["preprocessed_frame_gap_manifest.json"],
    )
    pilots = source_pilots(previous_documents["source_context_inventory.json"])
    numpy, wave2, phase3, runtime = import_preprocessing_runtime()
    self_test = determinism_self_test(
        rows,
        pilots,
        numpy=numpy,
        wave2=wave2,
        phase3=phase3,
    )
    if self_test_only:
        return self_test
    records, _output_created = materialize_frames(
        rows,
        gap_by_identity,
        pilots,
        numpy=numpy,
        wave2=wave2,
        phase3=phase3,
    )
    after_documents = accepted_source_documents(previous)
    if canonical_json_bytes(
        previous_documents["source_context_inventory.json"]
    ) != canonical_json_bytes(after_documents["source_context_inventory.json"]):
        fail("accepted source identities changed during materialization")
    documents = build_documents(
        after_documents,
        records,
        runtime,
        self_test,
    )
    if check:
        check_documents(documents)
    else:
        write_documents(documents)
        check_documents(documents)
    receipt = documents["validation_receipt.json"]
    manifest_path = PACKAGE_ROOT / "preprocessed_frame_manifest.json"
    return {
        "actual_preprocessed_frame_count": receipt["actual_preprocessed_frame_count"],
        "frame_manifest_path": str(manifest_path),
        "frame_manifest_sha256": sha256_file(manifest_path),
        "frame_output_root": str(OUTPUT_ROOT),
        "person_d_frame_handoff_ready": receipt["person_d_frame_handoff_ready"],
        "status": receipt["status"],
        "unique_preprocessed_frame_count": receipt["unique_preprocessed_frame_count"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    arguments = parser.parse_args()
    result = execute(check=arguments.check, self_test_only=arguments.self_test)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MaterializationError as error:
        print(f"ERROR: {error}")
        raise SystemExit(1)
