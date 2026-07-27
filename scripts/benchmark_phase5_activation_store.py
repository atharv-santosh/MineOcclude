#!/usr/bin/env python
"""CPU-only bounded benchmark for the Phase 5 pooled activation store."""

from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import math
import platform
import sys
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy

from mineocclude.activations.store import (
    ACTIVATION_INDEX_FORMAT_VERSION,
    ACTIVATION_STORE_FORMAT_VERSION,
    ActivationRowKey,
    ActivationStoreIdentity,
    build_activation_eligibility_proof,
    load_activation_index_snapshot,
    publish_activation_chunk,
    read_activation_vectors,
)
from mineocclude.analysis.config import (
    DEFAULT_CONFIG_PATH,
    hash_core_analysis_config,
    load_core_analysis_config,
)
from mineocclude.analysis.filters import apply_ordered_filters
from mineocclude.analysis.manifests import sha256_value
from mineocclude.contracts.activation import validate_activation_handoff
from mineocclude.contracts.identity import (
    FRAME_KEY,
    REQUIRED_FIELDS,
    SCHEMA_VERSION,
    validate_identity,
)
from mineocclude.oracle.schema import (
    ORACLE_TARGET_SCHEMA_VERSION,
    validate_oracle_target_document,
)
from mineocclude.oracle.targets import build_regime_a_target_document
from mineocclude.probes.bridge import (
    build_frame_fold_manifest,
    build_joined_frame_table,
    build_probe_ready_matrices,
    run_ridge_oof_probe,
)
from mineocclude.probes.splits import build_grouped_inner_folds

REPORT_NAME = "benchmark_report.json"
SUMMARY_NAME = "benchmark_summary.txt"
CREATION_TIMESTAMP = "2026-07-27T00:00:00Z"
REQUIRED_SCENARIO_TRAJECTORY_COUNTS = {
    "10-pilot": 10,
    "66-trajectory-mvp": 66,
    "regime-a": None,
    "full-372-trajectory": 372,
}
SCENARIO_INPUT_FIELDS = (
    "assumption_classification",
    "chunk_row_count",
    "dtype",
    "hidden_width",
    "label",
    "layer_count",
    "model_frames_per_trajectory",
    "trajectory_count",
)
INDEX_CHUNK_DESCRIPTOR_ESTIMATE_BYTES = 1024
EXAMPLE_README_NAME = "README.md"
EXAMPLE_CHECKSUM_NAME = "SHA256SUMS"
EXAMPLE_PACKAGE_VERSION = "1.1"
EXAMPLE_APPROVED_RELATIVE_FILES = frozenset(
    {
        EXAMPLE_README_NAME,
        EXAMPLE_CHECKSUM_NAME,
        "chunks/activation-chunk-106b16904a4ae44c7bac4903.npy",
        (
            "indexes/index-"
            "834f1070e8d77680e06d7713caf618624211c0bcf5ce4cfef8b692011ebd67e4"
            ".json"
        ),
        (
            "run_bindings/run-"
            "480e36150b993ebec1bdf1ba66a872366e7daa5ffed790e70c46351257e9238f"
            ".json"
        ),
    }
)
EXAMPLE_APPROVED_RELATIVE_DIRECTORIES = frozenset(
    {"chunks", "indexes", "run_bindings"}
)
HANDOFF_V12_PACKAGE_VERSION = "1.2"
HANDOFF_V12_FORMAT = "mineocclude-phase5-coordinated-synthetic-handoff"
HANDOFF_V12_SCIENTIFIC_STATUS = "synthetic_non_scientific"
HANDOFF_V12_SEED = 20260727
HANDOFF_V12_TRAJECTORY_COUNT = 10
HANDOFF_V12_FRAME_COUNT = 10
HANDOFF_V12_LAYER = 0
HANDOFF_V12_HOOK_SITE = "residual_stream"
HANDOFF_V12_WIDTH = 2048
HANDOFF_V12_DTYPE = "float32"
HANDOFF_V12_RUN_ID = "phase5-synthetic-handoff-v1-2-activation-run"
HANDOFF_V12_TARGET_RUN_ID = "phase5-synthetic-handoff-v1-2-target-run"
HANDOFF_V12_GENERATION_SOURCE_SHA = (
    "9c8a2f63d88d0c648e3f702557727be87ab56487"
)
HANDOFF_V12_AUDIT2_STORAGE_SHA = (
    "b0b71653311902fffce769aca6c4e81475ba0766"
)
HANDOFF_V12_FAILED_RECEIPT_COMMITS = (
    "1b229fdec74eb602c03d8301fd5744bc9c73b30e",
    "7791c938ce2d97014216974a02f5174b42893874",
)
HANDOFF_V12_ACCEPTED_PATH = (
    "accepted_manifest/accepted_manifest_rows.json"
)
HANDOFF_V12_TARGET_PATH = "targets/synthetic_oracle_targets.json"
HANDOFF_V12_MANIFEST_PATH = "handoff_manifest.json"
HANDOFF_V12_README_PATH = "README.md"
HANDOFF_V12_CHECKSUM_PATH = "SHA256SUMS"
HANDOFF_V12_APPROVED_DIRECTORIES = frozenset(
    {
        "accepted_manifest",
        "chunks",
        "indexes",
        "run_bindings",
        "targets",
    }
)
HANDOFF_V12_FIXED_FILES = frozenset(
    {
        HANDOFF_V12_ACCEPTED_PATH,
        HANDOFF_V12_TARGET_PATH,
        HANDOFF_V12_MANIFEST_PATH,
        HANDOFF_V12_README_PATH,
        HANDOFF_V12_CHECKSUM_PATH,
    }
)
HANDOFF_V12_CONSUMER_CHUNK_ID = (
    "phase5-handoff-v1-2-person-b-consumer-chunk"
)


def _positive(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _scenario(value: str) -> dict[str, Any]:
    fields = value.split(",")
    if len(fields) != 7:
        raise argparse.ArgumentTypeError(
            "scenario must be label,trajectories,frames,layers,width,dtype,chunk_rows"
        )
    label, _trajectories, _frames, _layers, _width, dtype, chunk_rows = fields
    if not label.strip() or dtype not in {"float16", "float32", "float64"}:
        raise argparse.ArgumentTypeError("scenario label/dtype is invalid")
    try:
        counts = [int(item) for item in fields[1:5]] + [int(chunk_rows)]
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "scenario counts must be integers"
        ) from error
    if any(item <= 0 for item in counts):
        raise argparse.ArgumentTypeError("scenario counts must be positive")
    return {
        "assumption_classification": "caller_supplied_input",
        "chunk_row_count": counts[4],
        "dtype": dtype,
        "hidden_width": counts[3],
        "label": label,
        "layer_count": counts[2],
        "model_frames_per_trajectory": counts[1],
        "trajectory_count": counts[0],
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _identity(
    dtype: str,
    *,
    run_id: str = "phase5-benchmark-controlled",
) -> ActivationStoreIdentity:
    checkpoint_hash = "1" * 64
    return ActivationStoreIdentity(
        schema_version=SCHEMA_VERSION,
        run_id=run_id,
        checkpoint_hash=checkpoint_hash,
        model_hash=checkpoint_hash,
        config_hash="3" * 64,
        preprocess_hash="4" * 64,
        accepted_manifest_hash="5" * 64,
        code_sha="6" * 40,
        hook_site="residual_stream",
        requested_layers=(0,),
        dtype=dtype,
        hidden_width=2048,
    )


def _rows(count: int, identity: ActivationStoreIdentity) -> list[dict[str, Any]]:
    return [
        {
            "accepted_manifest_hash": identity.accepted_manifest_hash,
            "action_idx": index,
            "checkpoint_hash": identity.checkpoint_hash,
            "code_sha": identity.code_sha,
            "config_hash": identity.config_hash,
            "duration": 1.0,
            "episode_id": "phase5-benchmark-episode",
            "exclusion_reason": None,
            "frame_token_positions": list(
                range(index * 347, index * 347 + 336)
            ),
            "hook_site": identity.hook_site,
            "layer_idx": 0,
            "layout_id": "phase5-benchmark-layout",
            "model_frame_idx": index,
            "model_hash": identity.model_hash,
            "preprocess_hash": identity.preprocess_hash,
            "q": 0.5,
            "regime": "non_scientific_benchmark",
            "render_frame_idx": index,
            "run_id": identity.run_id,
            "schema_version": SCHEMA_VERSION,
            "seed": 0,
            "server_tick": index,
            "status": "accepted",
            "superseded_by": None,
            "tau": index / 20.0,
            "trajectory_id": "phase5-benchmark-trajectory",
            "v": 1.0,
            "visibility": "visible",
        }
        for index in range(count)
    ]


def _manifest_rows(
    count: int,
    identity: ActivationStoreIdentity,
) -> list[dict[str, Any]]:
    result = _rows(count, identity)
    for row in result:
        row.pop("hook_site")
        row.pop("layer_idx")
    return result


def _rate(byte_count: int, elapsed: float) -> float:
    return byte_count / max(elapsed, sys.float_info.min)


def _validate_required_scenarios(
    scenarios: list[dict[str, Any]],
) -> None:
    by_label = {scenario["label"]: scenario for scenario in scenarios}
    if len(by_label) != len(scenarios):
        raise ValueError("scenario labels must be unique")
    missing = sorted(set(REQUIRED_SCENARIO_TRAJECTORY_COUNTS) - set(by_label))
    additional = sorted(set(by_label) - set(REQUIRED_SCENARIO_TRAJECTORY_COUNTS))
    if missing or additional:
        raise ValueError(
            "exactly these authoritative scenario names are required: "
            + ", ".join(REQUIRED_SCENARIO_TRAJECTORY_COUNTS)
            + f"; missing={missing}; additional={additional}"
        )
    for label, expected_count in REQUIRED_SCENARIO_TRAJECTORY_COUNTS.items():
        if (
            expected_count is not None
            and by_label[label]["trajectory_count"] != expected_count
        ):
            raise ValueError(
                f"{label} requires authoritative trajectory_count="
                f"{expected_count}"
            )


def _npy_header_bytes(row_count: int, width: int, dtype: str) -> int:
    stream = io.BytesIO()
    numpy.lib.format.write_array_header_1_0(
        stream,
        {
            "descr": numpy.lib.format.dtype_to_descr(numpy.dtype(dtype)),
            "fortran_order": False,
            "shape": (row_count, width),
        },
    )
    return len(stream.getvalue())


def forecast_scenario(
    scenario: dict[str, Any],
    *,
    measured: dict[str, float | int],
    smoke_rows: int,
    approved_capacity_bytes: int | None,
) -> dict[str, Any]:
    """Return one deterministic physical/index/staging capacity forecast."""

    vector_count = (
        scenario["trajectory_count"]
        * scenario["model_frames_per_trajectory"]
        * scenario["layer_count"]
    )
    item_size = numpy.dtype(scenario["dtype"]).itemsize
    raw_bytes_per_vector = scenario["hidden_width"] * item_size
    raw_vector_bytes = vector_count * raw_bytes_per_vector
    chunk_rows = scenario["chunk_row_count"]
    full_chunks, remainder = divmod(vector_count, chunk_rows)
    chunk_count = full_chunks + int(remainder > 0)
    header_bytes = full_chunks * _npy_header_bytes(
        chunk_rows,
        scenario["hidden_width"],
        scenario["dtype"],
    )
    if remainder:
        header_bytes += _npy_header_bytes(
            remainder,
            scenario["hidden_width"],
            scenario["dtype"],
        )
    persisted_chunk_bytes = raw_vector_bytes + header_bytes
    measured_index_bytes = int(measured["index_bytes"])
    row_component = max(
        1.0,
        (
            measured_index_bytes - INDEX_CHUNK_DESCRIPTOR_ESTIMATE_BYTES
        )
        / smoke_rows,
    )
    estimated_index_bytes = math.ceil(
        row_component * vector_count
        + INDEX_CHUNK_DESCRIPTOR_ESTIMATE_BYTES * chunk_count
    )
    total_persisted_bytes = persisted_chunk_bytes + estimated_index_bytes
    maximum_rows = min(chunk_rows, vector_count)
    largest_chunk_bytes = (
        maximum_rows * raw_bytes_per_vector
        + _npy_header_bytes(
            maximum_rows,
            scenario["hidden_width"],
            scenario["dtype"],
        )
    )
    staging_bytes = max(largest_chunk_bytes, estimated_index_bytes)
    staging_peak_bytes = total_persisted_bytes + staging_bytes
    capacity_status = "UNRESOLVED"
    if approved_capacity_bytes is not None:
        capacity_status = (
            "PASS"
            if staging_peak_bytes <= approved_capacity_bytes
            else "FAIL"
        )
    return {
        **scenario,
        "archive_s3_transfer_bytes": total_persisted_bytes,
        "archive_s3_transfer_compression": "none_uncompressed",
        "capacity": {
            "approved_capacity_bytes": approved_capacity_bytes,
            "basis": "persisted_bytes_plus_largest_simultaneous_staging_object",
            "status": capacity_status,
        },
        "chunk_count": chunk_count,
        "estimated_checksum_seconds": (
            persisted_chunk_bytes
            / float(measured["checksum_bytes_per_second"])
        ),
        "estimated_full_read_seconds": (
            persisted_chunk_bytes
            / float(measured["chunk_read_bytes_per_second"])
        ),
        "estimated_index_bytes": estimated_index_bytes,
        "estimated_selective_read_bytes": largest_chunk_bytes,
        "estimated_selective_read_seconds": (
            largest_chunk_bytes
            / float(measured["selective_read_bytes_per_second"])
        ),
        "estimated_write_seconds": (
            persisted_chunk_bytes
            / float(measured["chunk_write_bytes_per_second"])
        ),
        "float32_analysis_bytes": vector_count
        * scenario["hidden_width"]
        * numpy.dtype("float32").itemsize,
        "float_to_float32_promotion_input_bytes": raw_vector_bytes,
        "estimated_float_to_float32_promotion_seconds": (
            raw_vector_bytes
            / float(measured["float_to_float32_promotion_bytes_per_second"])
        ),
        "index_estimate_basis": {
            "measured_smoke_index_bytes": measured_index_bytes,
            "measured_smoke_rows": smoke_rows,
            "per_additional_chunk_descriptor_bytes": (
                INDEX_CHUNK_DESCRIPTOR_ESTIMATE_BYTES
            ),
        },
        "largest_chunk_bytes": largest_chunk_bytes,
        "numpy_header_overhead_bytes": header_bytes,
        "persisted_chunk_bytes": persisted_chunk_bytes,
        "raw_bytes_per_model_frame": (
            raw_bytes_per_vector * scenario["layer_count"]
        ),
        "raw_bytes_per_trajectory": (
            raw_bytes_per_vector
            * scenario["layer_count"]
            * scenario["model_frames_per_trajectory"]
        ),
        "raw_bytes_per_vector": raw_bytes_per_vector,
        "raw_vector_bytes": raw_vector_bytes,
        "simultaneous_staging_bytes": staging_bytes,
        "staging_peak_bytes": staging_peak_bytes,
        "total_persisted_bytes": total_persisted_bytes,
        "vector_count": vector_count,
        "resume_policy": (
            "checksum_and_index_validation_required_before_selective_skip"
        ),
    }


def _deterministic_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _run(args: argparse.Namespace) -> int:
    _validate_required_scenarios(args.scenario)
    output = args.output_dir.resolve()
    if output.exists():
        raise ValueError(f"refusing to overwrite output directory: {output}")
    output.mkdir(parents=True)
    store_root = output / "store"
    store_root.mkdir()
    identity = _identity(args.smoke_dtype)
    vectors = numpy.arange(
        args.smoke_rows * identity.hidden_width,
        dtype=numpy.float32,
    ).reshape(args.smoke_rows, identity.hidden_width)
    vectors = (vectors % 127).astype(args.smoke_dtype)
    started = time.perf_counter()
    snapshot = publish_activation_chunk(
        store_root=store_root,
        store_identity=identity,
        accepted_manifest_rows=_manifest_rows(args.smoke_rows, identity),
        eligibility_proof=build_activation_eligibility_proof(
            store_identity=identity,
            accepted_manifest_rows=_manifest_rows(args.smoke_rows, identity),
        ),
        rows=_rows(args.smoke_rows, identity),
        vectors=vectors,
        creation_timestamp=CREATION_TIMESTAMP,
    )
    write_seconds = time.perf_counter() - started
    keys = tuple(ActivationRowKey.from_row(row) for row in snapshot.index_rows)
    started = time.perf_counter()
    read_activation_vectors(
        store_root=store_root,
        snapshot=snapshot,
        row_keys=keys,
    )
    read_seconds = time.perf_counter() - started
    started = time.perf_counter()
    read_activation_vectors(
        store_root=store_root,
        snapshot=snapshot,
        row_keys=keys[:1],
    )
    selective_seconds = time.perf_counter() - started
    chunk = snapshot.chunks[0]
    chunk_path = store_root / chunk.relative_path
    started = time.perf_counter()
    checksum = _sha256(chunk_path)
    checksum_seconds = time.perf_counter() - started
    index_path = store_root / snapshot.relative_path
    started = time.perf_counter()
    load_activation_index_snapshot(index_path, store_root=store_root)
    parse_seconds = time.perf_counter() - started
    started = time.perf_counter()
    numpy.load(chunk_path, allow_pickle=False).astype(numpy.float32)
    promotion_seconds = time.perf_counter() - started
    item_size = numpy.dtype(args.smoke_dtype).itemsize
    measured = {
        "checksum_bytes_per_second": _rate(
            chunk.byte_size,
            checksum_seconds,
        ),
        "checksum_seconds": checksum_seconds,
        "chunk_read_bytes_per_second": _rate(vectors.nbytes, read_seconds),
        "chunk_read_seconds": read_seconds,
        "chunk_write_bytes_per_second": _rate(
            vectors.nbytes,
            write_seconds,
        ),
        "chunk_write_seconds": write_seconds,
        "float_to_float32_promotion_bytes_per_second": _rate(
            vectors.nbytes,
            promotion_seconds,
        ),
        "float_to_float32_promotion_seconds": promotion_seconds,
        "index_bytes": index_path.stat().st_size,
        "index_parse_validation_seconds": parse_seconds,
        "persisted_bytes_per_vector": chunk.byte_size / args.smoke_rows,
        "raw_bytes_per_vector": identity.hidden_width * item_size,
        "selective_read_bytes_per_second": _rate(
            identity.hidden_width * item_size,
            selective_seconds,
        ),
        "selective_read_seconds": selective_seconds,
    }
    scenarios = [
        forecast_scenario(
            scenario,
            measured=measured,
            smoke_rows=args.smoke_rows,
            approved_capacity_bytes=args.approved_capacity_bytes,
        )
        for scenario in sorted(args.scenario, key=lambda item: item["label"])
    ]
    report = {
        "benchmark_classification": "bounded_cpu_smoke_not_capacity_approval",
        "environment": {
            "numpy_version": numpy.__version__,
            "platform": platform.platform(),
            "python_version": platform.python_version(),
        },
        "formats": {
            "index": ACTIVATION_INDEX_FORMAT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "store": ACTIVATION_STORE_FORMAT_VERSION,
        },
        "forecast_classification": {
            "capacity_basis": (
                "caller-supplied approved capacity or unresolved"
            ),
            "counts": "input_based_authoritative_or_caller_supplied",
            "physical_overheads": (
                "npy_headers_plus_index_estimate_plus_simultaneous_staging"
            ),
        },
        "measured": measured,
        "scenarios": scenarios,
        "smoke_input": {
            "dtype": args.smoke_dtype,
            "hidden_width": identity.hidden_width,
            "row_count": args.smoke_rows,
        },
        "store_evidence": {
            "chunk_relative_path": chunk.relative_path,
            "chunk_sha256": checksum,
            "index_relative_path": snapshot.relative_path,
            "snapshot_id": snapshot.snapshot_id,
        },
    }
    report_path = output / REPORT_NAME
    report_path.write_bytes(_deterministic_json_bytes(report))
    capacity_lines = "\n".join(
        f"{scenario['label']} capacity: {scenario['capacity']['status']}"
        for scenario in scenarios
    )
    summary = (
        "Phase 5 bounded CPU smoke benchmark\n"
        f"rows: {args.smoke_rows}\n"
        f"dtype: {args.smoke_dtype}\n"
        f"chunk bytes: {chunk.byte_size}\n"
        f"index bytes: {index_path.stat().st_size}\n"
        f"{capacity_lines}\n"
    )
    (output / SUMMARY_NAME).write_text(summary, encoding="utf-8")
    print(summary, end="")
    return 0


def _validate(args: argparse.Namespace) -> int:
    output = args.output_dir.resolve()
    report_path = output / REPORT_NAME
    if not report_path.is_file() or not (output / SUMMARY_NAME).is_file():
        raise ValueError("benchmark report or summary is missing")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if (
        report.get("benchmark_classification")
        != "bounded_cpu_smoke_not_capacity_approval"
        or report.get("formats", {}).get("schema_version") != SCHEMA_VERSION
    ):
        raise ValueError("benchmark report identity is invalid")
    scenarios = report.get("scenarios")
    if not isinstance(scenarios, list):
        raise TypeError("benchmark scenarios are missing")
    _validate_required_scenarios(scenarios)
    for scenario in scenarios:
        capacity = scenario.get("capacity")
        if (
            not isinstance(capacity, dict)
            or capacity.get("status") not in {"PASS", "FAIL", "UNRESOLVED"}
        ):
            raise ValueError("benchmark capacity decision is invalid")
        try:
            scenario_input = {
                field: scenario[field] for field in SCENARIO_INPUT_FIELDS
            }
        except KeyError as error:
            raise ValueError(
                f"benchmark scenario input field is missing: {error}"
            ) from error
        recomputed = forecast_scenario(
            scenario_input,
            measured=report["measured"],
            smoke_rows=report["smoke_input"]["row_count"],
            approved_capacity_bytes=capacity["approved_capacity_bytes"],
        )
        if scenario != recomputed:
            raise ValueError(
                f"benchmark forecast does not recompute: {scenario['label']}"
            )
    store_root = output / "store"
    snapshot_path = store_root / report["store_evidence"]["index_relative_path"]
    snapshot = load_activation_index_snapshot(
        snapshot_path,
        store_root=store_root,
    )
    if snapshot.snapshot_id != report["store_evidence"]["snapshot_id"]:
        raise ValueError("benchmark snapshot identity mismatch")
    chunk_path = store_root / report["store_evidence"]["chunk_relative_path"]
    if _sha256(chunk_path) != report["store_evidence"]["chunk_sha256"]:
        raise ValueError("benchmark chunk checksum mismatch")
    print("Phase 5 benchmark output: VALID")
    return 0


def _example_files(output: Path) -> tuple[Path, Path, Path]:
    chunk = output / next(
        path
        for path in EXAMPLE_APPROVED_RELATIVE_FILES
        if path.startswith("chunks/")
    )
    index = output / next(
        path
        for path in EXAMPLE_APPROVED_RELATIVE_FILES
        if path.startswith("indexes/")
    )
    binding = output / next(
        path
        for path in EXAMPLE_APPROVED_RELATIVE_FILES
        if path.startswith("run_bindings/")
    )
    if not all(path.is_file() and not path.is_symlink() for path in (
        chunk,
        index,
        binding,
    )):
        raise ValueError(
            "example requires the exact approved chunk, index, and run binding"
        )
    return chunk, index, binding


def _read_lf_utf8(path: Path, *, label: str) -> str:
    payload = path.read_bytes()
    if payload.startswith(b"\xef\xbb\xbf") or b"\r" in payload:
        raise ValueError(f"{label} must be BOM-free UTF-8 with LF line endings")
    if not payload.endswith(b"\n"):
        raise ValueError(f"{label} must end with an LF line ending")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{label} must be valid UTF-8") from error


def _write_example(args: argparse.Namespace) -> int:
    output = args.output_dir.resolve()
    if output.exists():
        raise ValueError(f"refusing to overwrite output directory: {output}")
    output.mkdir(parents=True)
    identity = _identity(
        "float32",
        run_id="phase5-synthetic-non-scientific-example",
    )
    rows = _rows(1, identity)
    rows[0]["episode_id"] = "synthetic-phase5-example-episode"
    rows[0]["trajectory_id"] = "synthetic-phase5-example-trajectory"
    rows[0]["layout_id"] = "synthetic-phase5-example-layout"
    rows[0]["regime"] = "synthetic_non_scientific_example"
    manifest = [dict(rows[0])]
    manifest[0].pop("hook_site")
    manifest[0].pop("layer_idx")
    vectors = (
        numpy.arange(identity.hidden_width, dtype=numpy.float32) % 127
    ).reshape(1, identity.hidden_width)
    snapshot = publish_activation_chunk(
        store_root=output,
        store_identity=identity,
        accepted_manifest_rows=manifest,
        eligibility_proof=build_activation_eligibility_proof(
            store_identity=identity,
            accepted_manifest_rows=manifest,
        ),
        rows=rows,
        vectors=vectors,
        creation_timestamp=CREATION_TIMESTAMP,
    )
    chunk, index, binding = _example_files(output)
    readme_bytes = bytes(
        (
            "# Synthetic Phase 5 activation-store example\n\n"
            f"Fixture package version: `{EXAMPLE_PACKAGE_VERSION}`.\n\n"
            "Package v1.0 was independently rejected because its README "
            "checksum was computed from pre-Git-normalization CRLF bytes. "
            "Package v1.1 binds the canonical committed LF bytes.\n\n"
            "This is deterministic, synthetic, non-scientific documentation "
            "data. It is not accepted runtime evidence and is not a Person B "
            "receipt.\n\n"
            "Validate and read it with:\n\n"
            "```powershell\n"
            "python scripts/benchmark_phase5_activation_store.py "
            "validate-example --output-dir "
            "docs/status/fixtures/phase5_activation_store_example\n"
            "```\n"
        ),
        "utf-8",
    )
    if b"\r" in readme_bytes:
        raise ValueError("example README generation produced non-LF bytes")
    readme_path = output / EXAMPLE_README_NAME
    readme_path.write_bytes(readme_bytes)
    inventory_paths = (binding, chunk, index, readme_path)
    inventory_bytes = bytes(
        "".join(
            f"{_sha256(path)}  {path.relative_to(output).as_posix()}\n"
            for path in sorted(
                inventory_paths,
                key=lambda item: item.relative_to(output).as_posix(),
            )
        ),
        "utf-8",
    )
    if b"\r" in inventory_bytes:
        raise ValueError("example checksum generation produced non-LF bytes")
    (output / EXAMPLE_CHECKSUM_NAME).write_bytes(inventory_bytes)
    if snapshot.relative_path != index.relative_to(output).as_posix():
        raise ValueError("example snapshot path is inconsistent")
    return _validate_example(
        argparse.Namespace(output_dir=output),
    )


def _validate_example(args: argparse.Namespace) -> int:
    selected_output = args.output_dir.absolute()
    if selected_output.is_symlink():
        raise ValueError("example root must not be a symbolic link")
    output = selected_output.resolve()
    if not output.is_dir():
        raise ValueError("example root must be an ordinary directory")
    observed_files: set[str] = set()
    observed_directories: set[str] = set()
    for path in output.rglob("*"):
        relative = path.relative_to(output).as_posix()
        if path.is_symlink():
            raise ValueError(f"example inventory contains a symlink: {relative}")
        if path.is_dir():
            observed_directories.add(relative)
        elif path.is_file():
            observed_files.add(relative)
        else:
            raise ValueError(
                f"example inventory contains an unsupported entry: {relative}"
            )
    if observed_directories != EXAMPLE_APPROVED_RELATIVE_DIRECTORIES:
        raise ValueError(
            "example directory inventory differs from the exact approved "
            f"inventory; observed={sorted(observed_directories)!r}"
        )
    if observed_files != EXAMPLE_APPROVED_RELATIVE_FILES:
        raise ValueError(
            "example file inventory differs from the exact approved inventory; "
            f"observed={sorted(observed_files)!r}"
        )
    chunk, index, _binding = _example_files(output)
    inventory_path = output / EXAMPLE_CHECKSUM_NAME
    readme_path = output / EXAMPLE_README_NAME
    if not inventory_path.is_file() or not readme_path.is_file():
        raise ValueError("example checksum inventory or README is missing")
    inventory_text = _read_lf_utf8(
        inventory_path,
        label="example checksum inventory",
    )
    readme_text = _read_lf_utf8(
        readme_path,
        label="example README",
    )
    entries: dict[str, str] = {}
    for line in inventory_text.splitlines():
        fields = line.split("  ", maxsplit=1)
        if (
            len(fields) != 2
            or len(fields[0]) != 64
            or fields[1] in entries
        ):
            raise ValueError("example checksum inventory is malformed")
        entries[fields[1]] = fields[0]
    expected_paths = {
        path.relative_to(output).as_posix()
        for path in (*_example_files(output), readme_path)
    }
    if set(entries) != expected_paths:
        raise ValueError("example checksum inventory is incomplete")
    for relative, expected_hash in entries.items():
        if _sha256(output / relative) != expected_hash:
            raise ValueError(f"example checksum mismatch: {relative}")
    snapshot = load_activation_index_snapshot(index, store_root=output)
    if (
        len(snapshot.index_rows) != 1
        or snapshot.index_rows[0]["regime"]
        != "synthetic_non_scientific_example"
        or "synthetic, non-scientific" not in readme_text
        or f"package version: `{EXAMPLE_PACKAGE_VERSION}`" not in readme_text
    ):
        raise ValueError("example classification or cardinality is invalid")
    key = ActivationRowKey.from_row(snapshot.index_rows[0])
    observed = read_activation_vectors(
        store_root=output,
        snapshot=snapshot,
        row_keys=(key,),
    )
    expected = (
        numpy.arange(snapshot.store_identity.hidden_width, dtype=numpy.float32)
        % 127
    ).reshape(1, snapshot.store_identity.hidden_width)
    numpy.testing.assert_array_equal(observed, expected)
    if chunk.stat().st_size != snapshot.chunks[0].byte_size:
        raise ValueError("example chunk byte size mismatch")
    print("Phase 5 synthetic activation-store example: VALID")
    return 0


def _strict_json(path: Path, *, label: str) -> Mapping[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{label} contains duplicate JSON key {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"{label} contains nonfinite JSON value {value!r}")

    try:
        document = json.loads(
            _read_lf_utf8(path, label=label),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except json.JSONDecodeError as error:
        raise ValueError(f"{label} is malformed JSON: {error}") from error
    if not isinstance(document, Mapping):
        raise TypeError(f"{label} root must be a JSON object")
    if path.read_bytes() != _deterministic_json_bytes(document):
        raise ValueError(f"{label} bytes are not canonical deterministic JSON")
    return document


def _handoff_v12_base_manifest_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in range(HANDOFF_V12_TRAJECTORY_COUNT):
        rows.append(
            {
                "action_idx": 0,
                "code_sha": HANDOFF_V12_GENERATION_SOURCE_SHA,
                "config_hash": "3" * 64,
                "duration": 0.05,
                "episode_id": f"phase5-handoff-v1-2-episode-{index:02d}",
                "exclusion_reason": None,
                "layout_id": f"phase5-handoff-v1-2-layout-{index:02d}",
                "model_frame_idx": 0,
                "model_hash": "1" * 64,
                "preprocess_hash": "4" * 64,
                "q": 0.125,
                "regime": "synthetic_test",
                "render_frame_idx": 0,
                "run_id": HANDOFF_V12_RUN_ID,
                "schema_version": SCHEMA_VERSION,
                "seed": HANDOFF_V12_SEED,
                "server_tick": 1000 + index,
                "status": "accepted",
                "superseded_by": None,
                "tau": 0.0,
                "trajectory_id": (
                    f"phase5-handoff-v1-2-trajectory-{index:02d}"
                ),
                "v": 0.25,
                "visibility": "visible",
            }
        )
    return rows


def _handoff_v12_accepted_manifest_hash(
    rows_without_hash: Sequence[Mapping[str, Any]],
) -> str:
    return sha256_value(
        {
            "identity_definition": (
                "sha256_canonical_json_of_rows_before_hash_injection"
            ),
            "rows": [dict(row) for row in rows_without_hash],
            "schema_version": SCHEMA_VERSION,
            "scientific_status": HANDOFF_V12_SCIENTIFIC_STATUS,
        }
    )


def _handoff_v12_manifest_rows() -> list[dict[str, Any]]:
    rows = _handoff_v12_base_manifest_rows()
    accepted_manifest_hash = _handoff_v12_accepted_manifest_hash(rows)
    for row in rows:
        row["accepted_manifest_hash"] = accepted_manifest_hash
        validate_identity(row)
    return rows


def _handoff_v12_activation_rows(
    manifest_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for source in manifest_rows:
        row = dict(source)
        row.update(
            {
                "checkpoint_hash": "1" * 64,
                "frame_token_positions": list(range(336)),
                "hook_site": HANDOFF_V12_HOOK_SITE,
                "layer_idx": HANDOFF_V12_LAYER,
            }
        )
        result.append(row)
    return result


def _handoff_v12_vectors() -> numpy.ndarray:
    generator = numpy.random.Generator(numpy.random.PCG64(HANDOFF_V12_SEED))
    integers = generator.integers(
        -1000,
        1001,
        size=(HANDOFF_V12_FRAME_COUNT, HANDOFF_V12_WIDTH),
        dtype=numpy.int32,
    )
    return (integers.astype(numpy.float32) / numpy.float32(1000.0)).astype(
        numpy.float32
    )


def _handoff_v12_state_document(
    manifest_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for index, source in enumerate(manifest_rows):
        position = 5.0 + (0.75 * index) + (0.1 * (index % 3))
        state = {field: source[field] for field in REQUIRED_FIELDS}
        state.update(
            {
                "accepted_manifest_hash": source["accepted_manifest_hash"],
                "observed_position_blocks": position,
                "scientific_use": "forbidden",
                "synthetic": True,
                "x_true_blocks": position,
            }
        )
        rows.append(state)
    return {
        "fixture_metadata": {
            "scientific_use": "forbidden",
            "synthetic": True,
        },
        "join_key": list(FRAME_KEY),
        "rows": rows,
        "schema_version": SCHEMA_VERSION,
    }


def _handoff_from_snapshot(
    snapshot: Any,
    vectors: numpy.ndarray,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    if (
        vectors.ndim != 2
        or vectors.shape
        != (len(snapshot.index_rows), snapshot.store_identity.hidden_width)
        or vectors.dtype.name != HANDOFF_V12_DTYPE
        or not numpy.isfinite(vectors).all()
    ):
        raise ValueError(
            "public-reader vectors do not match the coordinated fixture"
        )
    rows = [
        copy.deepcopy(row)
        for row in snapshot.to_document()["index_rows"]
    ]
    for offset, row in enumerate(rows):
        row["activation_chunk_id"] = HANDOFF_V12_CONSUMER_CHUNK_ID
        row["chunk_row_idx"] = offset
    compatibility_document = {
        "chunk_id": HANDOFF_V12_CONSUMER_CHUNK_ID,
        "dtype": HANDOFF_V12_DTYPE,
        "rows": [
            {
                "chunk_row_idx": index,
                "vector": [float(value) for value in vectors[index]],
            }
            for index in range(vectors.shape[0])
        ],
        "vector_shape": [snapshot.store_identity.hidden_width],
    }
    compatibility_payload = _deterministic_json_bytes(
        compatibility_document
    )
    layer_counts = Counter(int(row["layer_idx"]) for row in rows)
    frame_keys = {
        (str(row["trajectory_id"]), int(row["model_frame_idx"]))
        for row in rows
    }
    counts = {
        str(layer): count for layer, count in sorted(layer_counts.items())
    }
    package = {
        "accepted_manifest_hash": (
            snapshot.store_identity.accepted_manifest_hash
        ),
        "cardinality_report": {
            "accepted_manifest_rows": len(frame_keys),
            "actual_activation_rows": len(rows),
            "actual_rows_by_layer": counts,
            "expected_activation_rows": len(rows),
            "expected_rows_by_layer": counts,
        },
        "checkpoint_hash": snapshot.store_identity.checkpoint_hash,
        "chunks": [
            {
                "chunk_id": HANDOFF_V12_CONSUMER_CHUNK_ID,
                "dtype": HANDOFF_V12_DTYPE,
                "path": (
                    "in_memory/"
                    f"{HANDOFF_V12_CONSUMER_CHUNK_ID}.json"
                ),
                "row_count": len(rows),
                "sha256": hashlib.sha256(
                    compatibility_payload
                ).hexdigest(),
                "vector_shape": [snapshot.store_identity.hidden_width],
            }
        ],
        "handoff_id": snapshot.snapshot_id,
        "index_rows": rows,
        "preprocess_hash": snapshot.store_identity.preprocess_hash,
        "run_id": snapshot.store_identity.run_id,
        "run_status": snapshot.run_status,
        "schema_version": SCHEMA_VERSION,
        "selection_policy": {
            "description": (
                "Accepted-manifest and requested-layer extraction independent "
                "of target and held-out labels."
            ),
            "uses_heldout_labels": False,
            "uses_target_labels": False,
        },
    }
    validation = validate_activation_handoff(package)
    if not validation.accepted:
        details = "; ".join(item.message for item in validation.rejections)
        raise ValueError(
            f"public activation handoff validation failed: {details}"
        )
    return package, {
        HANDOFF_V12_CONSUMER_CHUNK_ID: compatibility_payload
    }


def _handoff_v12_probe(
    *,
    output: Path,
    snapshot: Any,
    target_document: Mapping[str, Any],
) -> dict[str, Any]:
    keys = tuple(
        ActivationRowKey.from_row(row) for row in snapshot.index_rows
    )
    vectors = read_activation_vectors(
        store_root=output,
        snapshot=snapshot,
        row_keys=keys,
    )
    activation_package, chunk_payloads = _handoff_from_snapshot(
        snapshot,
        vectors,
    )
    frame_table = build_joined_frame_table(
        activation_package,
        target_document,
    )
    fold_manifest = build_frame_fold_manifest(
        frame_table,
        artifact_id="phase5-handoff-v1-2-folds",
    )
    matrices = build_probe_ready_matrices(
        activation_package,
        target_document,
        frame_table,
        fold_manifest,
        chunk_payloads,
        target_name="mu_oracle_blocks",
    )
    if len(matrices) != 1:
        raise ValueError("coordinated handoff must build exactly one matrix")
    matrix = matrices[0]
    execution = run_ridge_oof_probe(
        matrix,
        artifact_id_prefix="phase5-handoff-v1-2-tiny-probe",
    )
    fold_by_key = {
        (
            membership["trajectory_id"],
            membership["model_frame_idx"],
        ): membership["fold_idx"]
        for membership in fold_manifest["memberships"]
    }
    annotated = [
        {
            **dict(row),
            "fold_idx": fold_by_key[
                (row["trajectory_id"], row["model_frame_idx"])
            ],
        }
        for row in frame_table["rows"]
    ]
    inner_facts: list[dict[str, Any]] = []
    for outer_fold_idx in range(5):
        inner_rows = build_grouped_inner_folds(
            annotated,
            outer_fold_idx=outer_fold_idx,
            n_splits=4,
            seed=HANDOFF_V12_SEED - 8,
        )
        inner_counts = Counter(
            int(row["inner_fold_idx"]) for row in inner_rows
        )
        inner_facts.append(
            {
                "inner_fold_counts": {
                    str(index): inner_counts[index] for index in range(4)
                },
                "outer_fold_idx": outer_fold_idx,
                "outer_training_group_count": len(
                    {row["layout_id"] for row in inner_rows}
                ),
                "outer_training_row_count": len(inner_rows),
            }
        )
    output_document = {
        "matrix_hash": matrix.matrix_hash,
        "output_shape": [len(execution.oof_result.predictions)],
        "prediction_artifact_hash": (
            execution.prediction_artifact["artifact_hash"]
        ),
        "predictions": list(execution.oof_result.predictions),
        "u1_result_artifact_hash": (
            execution.u1_result_artifact["artifact_hash"]
        ),
    }
    if not all(
        math.isfinite(float(value))
        for value in execution.oof_result.predictions
    ):
        raise ValueError("tiny public probe produced nonfinite predictions")
    return {
        "activation_package": activation_package,
        "chunk_payloads": chunk_payloads,
        "execution": execution,
        "fold_manifest": fold_manifest,
        "frame_table": frame_table,
        "inner_facts": inner_facts,
        "matrix": matrix,
        "output_document": output_document,
        "probe_output_hash": sha256_value(output_document),
        "vectors": vectors,
    }


def _handoff_v12_readme() -> bytes:
    return (
        b"# Phase 5 coordinated synthetic handoff v1.2\n\n"
        b"This package is deterministic `synthetic_non_scientific` "
        b"engineering data. It is not runtime evidence, a scientific result, "
        b"or an independent Person B receipt.\n\n"
        b"Version 1.0 failed canonical-byte/checksum integrity. Version 1.1 "
        b"fixed package integrity but its activation and target identities did "
        b"not join and it lacked enough groups for the frozen Person B probe. "
        b"Version 1.2 coordinates accepted-manifest, activation, and target "
        b"identities across ten independent layouts.\n\n"
        b"The persisted activation data is the production Phase 5 `.npy` "
        b"store written and loaded through public Person A APIs. Person B's "
        b"frozen bridge authenticates a JSON fixture envelope, so the public "
        b"consumer path reads the `.npy` vectors first and creates a "
        b"deterministic in-memory envelope; no second persisted activation "
        b"authority is introduced.\n\n"
        b"Validate and execute the bounded consumer proof with:\n\n"
        b"```powershell\n"
        b"python scripts/benchmark_phase5_activation_store.py "
        b"validate-handoff-v1-2 --output-dir "
        b"docs/status/fixtures/"
        b"phase5_activation_store_handoff_v1_2\n"
        b"```\n\n"
        b"The public sequence is "
        b"`load_activation_index_snapshot` -> `read_activation_vectors` -> "
        b"`validate_oracle_target_document` -> "
        b"`build_joined_frame_table` -> `build_probe_ready_matrices` -> "
        b"`run_ridge_oof_probe`. The universal join key is exactly "
        b"`trajectory_id + model_frame_idx`; row and file order are never "
        b"identity.\n\n"
        b"Fresh independent Person B acceptance is still required before "
        b"Step 5.8 can pass.\n"
    )


def _handoff_v12_inventory(
    output: Path,
    manifest: Mapping[str, Any],
) -> tuple[set[str], set[str]]:
    activation = manifest.get("activation_store")
    if not isinstance(activation, Mapping):
        raise TypeError("handoff manifest activation_store is malformed")
    chunks = activation.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise ValueError("handoff manifest chunk inventory is malformed")
    declared = {
        *HANDOFF_V12_FIXED_FILES,
        activation.get("index_path"),
        activation.get("run_binding_path"),
        *(chunk.get("path") for chunk in chunks if isinstance(chunk, Mapping)),
    }
    if any(not isinstance(path, str) or not path for path in declared):
        raise ValueError("handoff manifest contains invalid inventory paths")
    files = {str(path) for path in declared}
    directories = {
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_dir()
    }
    return files, directories


def _write_handoff_v12(args: argparse.Namespace) -> int:
    output = args.output_dir.resolve()
    if output.exists():
        raise ValueError(f"refusing to overwrite output directory: {output}")
    output.mkdir(parents=True)
    (output / "accepted_manifest").mkdir()
    (output / "targets").mkdir()

    manifest_rows = _handoff_v12_manifest_rows()
    accepted_manifest_hash = manifest_rows[0]["accepted_manifest_hash"]
    accepted_document = {
        "accepted_manifest_hash": accepted_manifest_hash,
        "accepted_manifest_identity_definition": (
            "sha256_canonical_json_of_rows_before_hash_injection"
        ),
        "join_key": list(FRAME_KEY),
        "package_version": HANDOFF_V12_PACKAGE_VERSION,
        "rows": manifest_rows,
        "schema_version": SCHEMA_VERSION,
        "scientific_status": HANDOFF_V12_SCIENTIFIC_STATUS,
    }
    accepted_path = output / HANDOFF_V12_ACCEPTED_PATH
    accepted_path.write_bytes(_deterministic_json_bytes(accepted_document))

    identity = ActivationStoreIdentity(
        schema_version=SCHEMA_VERSION,
        run_id=HANDOFF_V12_RUN_ID,
        checkpoint_hash="1" * 64,
        model_hash="1" * 64,
        config_hash="3" * 64,
        preprocess_hash="4" * 64,
        accepted_manifest_hash=accepted_manifest_hash,
        code_sha=HANDOFF_V12_GENERATION_SOURCE_SHA,
        hook_site=HANDOFF_V12_HOOK_SITE,
        requested_layers=(HANDOFF_V12_LAYER,),
        dtype=HANDOFF_V12_DTYPE,
        hidden_width=HANDOFF_V12_WIDTH,
    )
    proof = build_activation_eligibility_proof(
        store_identity=identity,
        accepted_manifest_rows=manifest_rows,
    )
    snapshot = publish_activation_chunk(
        store_root=output,
        store_identity=identity,
        accepted_manifest_rows=manifest_rows,
        eligibility_proof=proof,
        rows=_handoff_v12_activation_rows(manifest_rows),
        vectors=_handoff_v12_vectors(),
        creation_timestamp=CREATION_TIMESTAMP,
    )

    target_document = build_regime_a_target_document(
        _handoff_v12_state_document(manifest_rows),
        oracle_run_id=HANDOFF_V12_TARGET_RUN_ID,
        oracle_code_sha=HANDOFF_V12_GENERATION_SOURCE_SHA,
        oracle_config_hash=hash_core_analysis_config(DEFAULT_CONFIG_PATH),
    )
    target_path = output / HANDOFF_V12_TARGET_PATH
    target_path.write_bytes(_deterministic_json_bytes(target_document))

    probe = _handoff_v12_probe(
        output=output,
        snapshot=snapshot,
        target_document=target_document,
    )
    index_path = output / snapshot.relative_path
    run_binding = next((output / "run_bindings").glob("run-*.json"))
    chunks = [
        {
            "byte_size": (output / chunk.relative_path).stat().st_size,
            "chunk_id": chunk.chunk_id,
            "path": chunk.relative_path,
            "row_count": chunk.row_count,
            "sha256": _sha256(output / chunk.relative_path),
        }
        for chunk in snapshot.chunks
    ]
    fold_counts = Counter(int(value) for value in probe["matrix"].outer_folds)
    config = load_core_analysis_config(DEFAULT_CONFIG_PATH)
    manifest = {
        "accepted_manifest": {
            "accepted_manifest_hash": accepted_manifest_hash,
            "byte_size": accepted_path.stat().st_size,
            "path": HANDOFF_V12_ACCEPTED_PATH,
            "row_count": len(manifest_rows),
            "sha256": _sha256(accepted_path),
        },
        "activation_store": {
            "analysis_dtype_expected_by_person_b": "float64",
            "chunks": chunks,
            "index_path": snapshot.relative_path,
            "index_sha256": _sha256(index_path),
            "index_snapshot_id": snapshot.snapshot_id,
            "row_count": len(snapshot.index_rows),
            "run_binding_digest": json.loads(
                run_binding.read_text(encoding="utf-8")
            )["binding_digest"],
            "run_binding_path": run_binding.relative_to(output).as_posix(),
            "run_binding_sha256": _sha256(run_binding),
            "store_identity_digest": snapshot.store_identity.digest,
            "stored_dtype": HANDOFF_V12_DTYPE,
            "vector_width": HANDOFF_V12_WIDTH,
        },
        "audit2_certified_storage_sha": HANDOFF_V12_AUDIT2_STORAGE_SHA,
        "consumer_compatibility": {
            "activation_handoff_hash": sha256_value(
                probe["activation_package"]
            ),
            "consumer_chunk_id": HANDOFF_V12_CONSUMER_CHUNK_ID,
            "consumer_chunk_sha256": hashlib.sha256(
                probe["chunk_payloads"][HANDOFF_V12_CONSUMER_CHUNK_ID]
            ).hexdigest(),
            "description": (
                "deterministic in-memory Person B JSON fixture envelope built "
                "only from vectors verified by the public Phase 5 reader"
            ),
            "persisted": False,
            "private_assistance_required": False,
        },
        "deterministic_probe": {
            "alpha_grid": config["ridge"]["alpha_grid"],
            "feature_shape": [
                len(probe["matrix"].features),
                len(probe["matrix"].features[0]),
            ],
            "finite": True,
            "horizon": {
                "kind": "same_model_frame",
                "model_frame_offset": 0,
            },
            "inner_fold_count": config["cross_validation"][
                "inner_fold_count"
            ],
            "outer_fold_assignments": probe["fold_manifest"][
                "layout_assignments"
            ],
            "outer_fold_counts": {
                str(index): fold_counts[index] for index in range(5)
            },
            "outer_fold_manifest_hash": probe["fold_manifest"][
                "artifact_hash"
            ],
            "outer_fold_seed": config["cross_validation"]["split_seed"],
            "output_shape": probe["output_document"]["output_shape"],
            "probe_output_hash": probe["probe_output_hash"],
            "target_name": probe["matrix"].target_name,
        },
        "expected_join": {
            "duplicate_activation_key_count": 0,
            "duplicate_target_key_count": 0,
            "joined_row_count": HANDOFF_V12_FRAME_COUNT,
            "unmatched_activation_count": 0,
            "unmatched_target_count": 0,
            "universal_join_key": list(FRAME_KEY),
        },
        "fixed_seed": HANDOFF_V12_SEED,
        "generation_source_sha": HANDOFF_V12_GENERATION_SOURCE_SHA,
        "grouped_inner_fold_viability": probe["inner_facts"],
        "handoff_format": HANDOFF_V12_FORMAT,
        "migration_required": False,
        "model_frame_count": HANDOFF_V12_FRAME_COUNT,
        "package_version": HANDOFF_V12_PACKAGE_VERSION,
        "person_b_public_functions": [
            "mineocclude.oracle.schema.validate_oracle_target_document",
            "mineocclude.probes.bridge.build_joined_frame_table",
            "mineocclude.probes.bridge.build_probe_ready_matrices",
            "mineocclude.probes.bridge.run_ridge_oof_probe",
        ],
        "person_b_target": {
            "byte_size": target_path.stat().st_size,
            "horizons": [
                {
                    "kind": "same_model_frame",
                    "model_frame_offset": 0,
                }
            ],
            "path": HANDOFF_V12_TARGET_PATH,
            "row_count": len(target_document["rows"]),
            "sha256": _sha256(target_path),
            "target_names": ["mu_oracle_blocks"],
            "target_schema_version": ORACLE_TARGET_SCHEMA_VERSION,
        },
        "prior_failed_receipt_commits": list(
            HANDOFF_V12_FAILED_RECEIPT_COMMITS
        ),
        "private_assistance_required": False,
        "producing_run_id": HANDOFF_V12_RUN_ID,
        "public_store_functions": [
            "mineocclude.activations.store.publish_activation_chunk",
            "mineocclude.activations.store.load_activation_index_snapshot",
            "mineocclude.activations.store.read_activation_vectors",
        ],
        "schema_version": SCHEMA_VERSION,
        "scientific_status": HANDOFF_V12_SCIENTIFIC_STATUS,
        "site": {
            "hook_site": HANDOFF_V12_HOOK_SITE,
            "layer_idx": HANDOFF_V12_LAYER,
        },
        "trajectory_group_count": HANDOFF_V12_TRAJECTORY_COUNT,
    }
    manifest_path = output / HANDOFF_V12_MANIFEST_PATH
    manifest_path.write_bytes(_deterministic_json_bytes(manifest))
    readme = _handoff_v12_readme()
    if b"\r" in readme or not readme.endswith(b"\n"):
        raise ValueError("handoff README is not canonical LF text")
    (output / HANDOFF_V12_README_PATH).write_bytes(readme)

    payload_paths = sorted(
        (
            path
            for path in output.rglob("*")
            if path.is_file()
            and path.relative_to(output).as_posix()
            != HANDOFF_V12_CHECKSUM_PATH
        ),
        key=lambda path: path.relative_to(output).as_posix(),
    )
    checksum_bytes = "".join(
        f"{_sha256(path)}  {path.relative_to(output).as_posix()}\n"
        for path in payload_paths
    ).encode("utf-8")
    (output / HANDOFF_V12_CHECKSUM_PATH).write_bytes(checksum_bytes)
    return _validate_handoff_v12(
        argparse.Namespace(output_dir=output),
    )


def _validate_handoff_v12(args: argparse.Namespace) -> int:
    selected = args.output_dir.absolute()
    if selected.is_symlink():
        raise ValueError("handoff root must not be a symbolic link")
    output = selected.resolve()
    if not output.is_dir():
        raise ValueError("handoff root must be an ordinary directory")
    for path in output.rglob("*"):
        if path.is_symlink():
            raise ValueError(
                "handoff inventory contains a symlink: "
                + path.relative_to(output).as_posix()
            )
        if not path.is_file() and not path.is_dir():
            raise ValueError("handoff inventory contains an unsupported entry")

    manifest = _strict_json(
        output / HANDOFF_V12_MANIFEST_PATH,
        label="handoff manifest",
    )
    expected_files, observed_directories = _handoff_v12_inventory(
        output,
        manifest,
    )
    observed_files = {
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_file()
    }
    if observed_directories != HANDOFF_V12_APPROVED_DIRECTORIES:
        raise ValueError(
            "handoff directory inventory differs from the approved inventory"
        )
    if observed_files != expected_files:
        raise ValueError(
            "handoff file inventory differs from the exact declared inventory; "
            f"observed={sorted(observed_files)!r}"
        )
    checksum_text = _read_lf_utf8(
        output / HANDOFF_V12_CHECKSUM_PATH,
        label="handoff checksum inventory",
    )
    entries: dict[str, str] = {}
    for line in checksum_text.splitlines():
        fields = line.split("  ", maxsplit=1)
        if (
            len(fields) != 2
            or len(fields[0]) != 64
            or fields[1] in entries
        ):
            raise ValueError("handoff checksum inventory is malformed")
        try:
            int(fields[0], 16)
        except ValueError as error:
            raise ValueError(
                "handoff checksum inventory contains a non-hex digest"
            ) from error
        entries[fields[1]] = fields[0]
    if set(entries) != expected_files - {HANDOFF_V12_CHECKSUM_PATH}:
        raise ValueError("handoff checksum inventory coverage is incomplete")
    for relative, expected_hash in entries.items():
        if _sha256(output / relative) != expected_hash:
            raise ValueError(f"handoff checksum mismatch: {relative}")
    for relative in expected_files:
        if relative.endswith((".json", ".md")) or relative == (
            HANDOFF_V12_CHECKSUM_PATH
        ):
            _read_lf_utf8(output / relative, label=relative)

    if (
        manifest.get("handoff_format") != HANDOFF_V12_FORMAT
        or manifest.get("package_version") != HANDOFF_V12_PACKAGE_VERSION
        or manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("scientific_status")
        != HANDOFF_V12_SCIENTIFIC_STATUS
        or manifest.get("generation_source_sha")
        != HANDOFF_V12_GENERATION_SOURCE_SHA
        or manifest.get("audit2_certified_storage_sha")
        != HANDOFF_V12_AUDIT2_STORAGE_SHA
        or manifest.get("prior_failed_receipt_commits")
        != list(HANDOFF_V12_FAILED_RECEIPT_COMMITS)
        or manifest.get("migration_required") is not False
        or manifest.get("private_assistance_required") is not False
    ):
        raise ValueError("handoff manifest identity or classification is invalid")

    accepted = _strict_json(
        output / HANDOFF_V12_ACCEPTED_PATH,
        label="accepted manifest",
    )
    rows = accepted.get("rows")
    if not isinstance(rows, list) or len(rows) != HANDOFF_V12_FRAME_COUNT:
        raise ValueError("accepted manifest row cardinality is invalid")
    expected_accepted_hash = _handoff_v12_accepted_manifest_hash(
        [
            {
                key: value
                for key, value in row.items()
                if key != "accepted_manifest_hash"
            }
            for row in rows
            if isinstance(row, Mapping)
        ]
    )
    accepted_hash = accepted.get("accepted_manifest_hash")
    if (
        len(rows)
        != len(
            [row for row in rows if isinstance(row, Mapping)]
        )
        or accepted_hash != expected_accepted_hash
        or any(row.get("accepted_manifest_hash") != accepted_hash for row in rows)
    ):
        raise ValueError("accepted manifest identity is inconsistent")
    for row in rows:
        validate_identity(row)
    filter_result = apply_ordered_filters(
        rows,
        accepted_manifest_hash=str(accepted_hash),
    )
    if (
        filter_result.rejections
        or len(filter_result.accepted_rows) != HANDOFF_V12_FRAME_COUNT
    ):
        raise ValueError("accepted rows do not all pass ordered eligibility")

    activation = manifest["activation_store"]
    if (
        activation.get("row_count") != HANDOFF_V12_FRAME_COUNT
        or activation.get("vector_width") != HANDOFF_V12_WIDTH
        or activation.get("stored_dtype") != HANDOFF_V12_DTYPE
        or activation.get("analysis_dtype_expected_by_person_b")
        != "float64"
    ):
        raise ValueError("activation-store summary is inconsistent")
    index_path = output / activation["index_path"]
    if (
        index_path.stat().st_size <= 0
        or _sha256(index_path) != activation["index_sha256"]
    ):
        raise ValueError("activation index identity is inconsistent")
    snapshot = load_activation_index_snapshot(index_path, store_root=output)
    if (
        snapshot.snapshot_id != activation["index_snapshot_id"]
        or snapshot.store_identity.digest
        != activation["store_identity_digest"]
        or snapshot.store_identity.accepted_manifest_hash != accepted_hash
        or len(snapshot.index_rows) != HANDOFF_V12_FRAME_COUNT
    ):
        raise ValueError("activation snapshot identity is inconsistent")
    run_binding = _strict_json(
        output / activation["run_binding_path"],
        label="run binding",
    )
    if (
        _sha256(output / activation["run_binding_path"])
        != activation["run_binding_sha256"]
        or run_binding.get("binding_digest")
        != activation["run_binding_digest"]
    ):
        raise ValueError("run-binding identity is inconsistent")
    declared_chunks = {
        item["path"]: item for item in activation["chunks"]
    }
    observed_chunks = {
        chunk.relative_path: chunk for chunk in snapshot.chunks
    }
    if set(declared_chunks) != set(observed_chunks):
        raise ValueError("activation chunk inventory is inconsistent")
    for relative, chunk in observed_chunks.items():
        declared = declared_chunks[relative]
        path = output / relative
        if (
            declared.get("chunk_id") != chunk.chunk_id
            or declared.get("row_count") != chunk.row_count
            or declared.get("byte_size") != path.stat().st_size
            or declared.get("sha256") != _sha256(path)
        ):
            raise ValueError("activation chunk identity is inconsistent")

    target = _strict_json(
        output / HANDOFF_V12_TARGET_PATH,
        label="Person B target document",
    )
    validate_oracle_target_document(target)
    target_rows = target.get("rows")
    if (
        not isinstance(target_rows, list)
        or len(target_rows) != HANDOFF_V12_FRAME_COUNT
        or len({float(row["mu_oracle_blocks"]) for row in target_rows}) <= 1
    ):
        raise ValueError("target cardinality or variation is invalid")
    if (
        manifest["accepted_manifest"]["sha256"]
        != _sha256(output / HANDOFF_V12_ACCEPTED_PATH)
        or manifest["accepted_manifest"]["byte_size"]
        != (output / HANDOFF_V12_ACCEPTED_PATH).stat().st_size
        or manifest["accepted_manifest"]["accepted_manifest_hash"]
        != accepted_hash
        or manifest["person_b_target"]["sha256"]
        != _sha256(output / HANDOFF_V12_TARGET_PATH)
        or manifest["person_b_target"]["byte_size"]
        != (output / HANDOFF_V12_TARGET_PATH).stat().st_size
    ):
        raise ValueError("accepted-manifest or target file provenance differs")

    activation_keys = {
        (row["trajectory_id"], row["model_frame_idx"])
        for row in snapshot.index_rows
    }
    target_keys = {
        (row["trajectory_id"], row["model_frame_idx"])
        for row in target_rows
    }
    if (
        len(activation_keys) != len(snapshot.index_rows)
        or len(target_keys) != len(target_rows)
        or activation_keys != target_keys
    ):
        raise ValueError("activation and target universal keys do not match")
    probe = _handoff_v12_probe(
        output=output,
        snapshot=snapshot,
        target_document=target,
    )
    matrix = probe["matrix"]
    fold_counts = Counter(int(value) for value in matrix.outer_folds)
    expected_fold_counts = {
        str(index): fold_counts[index] for index in range(5)
    }
    if (
        len(probe["frame_table"]["rows"]) != HANDOFF_V12_FRAME_COUNT
        or len(matrix.features) != HANDOFF_V12_FRAME_COUNT
        or any(len(vector) != HANDOFF_V12_WIDTH for vector in matrix.features)
        or set(fold_counts) != set(range(5))
        or any(count <= 0 for count in fold_counts.values())
        or probe["inner_facts"]
        != manifest["grouped_inner_fold_viability"]
        or expected_fold_counts
        != manifest["deterministic_probe"]["outer_fold_counts"]
        or probe["fold_manifest"]["layout_assignments"]
        != manifest["deterministic_probe"]["outer_fold_assignments"]
        or probe["fold_manifest"]["artifact_hash"]
        != manifest["deterministic_probe"]["outer_fold_manifest_hash"]
        or probe["probe_output_hash"]
        != manifest["deterministic_probe"]["probe_output_hash"]
        or manifest["deterministic_probe"]["feature_shape"]
        != [HANDOFF_V12_FRAME_COUNT, HANDOFF_V12_WIDTH]
        or manifest["deterministic_probe"]["output_shape"]
        != [HANDOFF_V12_FRAME_COUNT]
    ):
        raise ValueError("join, matrix, fold, or probe evidence is inconsistent")
    compatibility = manifest["consumer_compatibility"]
    if (
        compatibility["activation_handoff_hash"]
        != sha256_value(probe["activation_package"])
        or compatibility["consumer_chunk_sha256"]
        != hashlib.sha256(
            probe["chunk_payloads"][HANDOFF_V12_CONSUMER_CHUNK_ID]
        ).hexdigest()
        or compatibility.get("persisted") is not False
    ):
        raise ValueError("consumer compatibility identity is inconsistent")
    join_facts = manifest["expected_join"]
    if join_facts != {
        "duplicate_activation_key_count": 0,
        "duplicate_target_key_count": 0,
        "joined_row_count": HANDOFF_V12_FRAME_COUNT,
        "unmatched_activation_count": 0,
        "unmatched_target_count": 0,
        "universal_join_key": list(FRAME_KEY),
    }:
        raise ValueError("expected join facts are inconsistent")
    if (
        manifest.get("trajectory_group_count")
        != HANDOFF_V12_TRAJECTORY_COUNT
        or manifest.get("model_frame_count") != HANDOFF_V12_FRAME_COUNT
        or manifest.get("site")
        != {
            "hook_site": HANDOFF_V12_HOOK_SITE,
            "layer_idx": HANDOFF_V12_LAYER,
        }
    ):
        raise ValueError("handoff row/group/site facts are inconsistent")

    target_values = numpy.asarray(matrix.targets, dtype=numpy.float64)
    feature_values = numpy.asarray(matrix.features, dtype=numpy.float64)
    if any(
        numpy.array_equal(feature_values[:, index], target_values)
        for index in range(feature_values.shape[1])
    ):
        raise ValueError("fixture contains an obvious direct target feature")
    readme = _read_lf_utf8(
        output / HANDOFF_V12_README_PATH,
        label="handoff README",
    )
    if (
        HANDOFF_V12_SCIENTIFIC_STATUS not in readme
        or "Fresh independent Person B acceptance is still required" not in readme
    ):
        raise ValueError("handoff README classification is incomplete")
    print(
        "Phase 5 coordinated synthetic handoff v1.2: VALID\n"
        f"joined rows: {len(matrix.features)}\n"
        f"feature width: {len(matrix.features[0])}\n"
        f"groups: {len(set(matrix.layout_ids))}\n"
        f"probe output hash: {probe['probe_output_hash']}"
    )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    run = subparsers.add_parser("run", help="run a bounded CPU smoke benchmark")
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument(
        "--scenario",
        action="append",
        type=_scenario,
        required=True,
        help=(
            "label,trajectories,frames,layers,width,dtype,chunk_rows; "
            "repeat for every authoritative scenario"
        ),
    )
    run.add_argument("--smoke-rows", type=_positive, default=2)
    run.add_argument("--approved-capacity-bytes", type=_positive)
    run.add_argument(
        "--smoke-dtype",
        choices=("float16", "float32", "float64"),
        default="float16",
    )
    run.set_defaults(handler=_run)
    validate = subparsers.add_parser(
        "validate", help="validate an existing bounded benchmark output"
    )
    validate.add_argument("--output-dir", type=Path, required=True)
    validate.set_defaults(handler=_validate)
    example = subparsers.add_parser(
        "write-example",
        help="write the deterministic synthetic documentation example",
    )
    example.add_argument("--output-dir", type=Path, required=True)
    example.set_defaults(handler=_write_example)
    validate_example = subparsers.add_parser(
        "validate-example",
        help="validate the synthetic documentation example",
    )
    validate_example.add_argument("--output-dir", type=Path, required=True)
    validate_example.set_defaults(handler=_validate_example)
    handoff_v12 = subparsers.add_parser(
        "write-handoff-v1-2",
        help=(
            "write the coordinated synthetic activation/target handoff v1.2"
        ),
    )
    handoff_v12.add_argument("--output-dir", type=Path, required=True)
    handoff_v12.set_defaults(handler=_write_handoff_v12)
    validate_handoff_v12 = subparsers.add_parser(
        "validate-handoff-v1-2",
        help=(
            "validate and run the public consumer path for handoff v1.2"
        ),
    )
    validate_handoff_v12.add_argument(
        "--output-dir",
        type=Path,
        required=True,
    )
    validate_handoff_v12.set_defaults(handler=_validate_handoff_v12)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.operation == "run" and args.smoke_rows > 16:
        raise ValueError("smoke rows cannot exceed the 16-frame model context")
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
