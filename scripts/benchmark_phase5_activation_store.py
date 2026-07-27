#!/usr/bin/env python
"""CPU-only bounded benchmark for the Phase 5 pooled activation store."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import platform
import sys
import time
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
from mineocclude.contracts.identity import SCHEMA_VERSION

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
    readme = (
        "# Synthetic Phase 5 activation-store example\n\n"
        "This is deterministic, synthetic, non-scientific documentation data. "
        "It is not accepted runtime evidence and is not a Person B receipt.\n\n"
        "Validate and read it with:\n\n"
        "```powershell\n"
        "python scripts/benchmark_phase5_activation_store.py "
        "validate-example --output-dir "
        "docs/status/fixtures/phase5_activation_store_example\n"
        "```\n"
    )
    readme_path = output / EXAMPLE_README_NAME
    readme_path.write_text(readme, encoding="utf-8")
    inventory_paths = (binding, chunk, index, readme_path)
    inventory = "".join(
        f"{_sha256(path)}  {path.relative_to(output).as_posix()}\n"
        for path in sorted(
            inventory_paths,
            key=lambda item: item.relative_to(output).as_posix(),
        )
    )
    (output / EXAMPLE_CHECKSUM_NAME).write_text(inventory, encoding="utf-8")
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
    entries: dict[str, str] = {}
    for line in inventory_path.read_text(encoding="utf-8").splitlines():
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
        or "synthetic, non-scientific"
        not in readme_path.read_text(encoding="utf-8")
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.operation == "run" and args.smoke_rows > 16:
        raise ValueError("smoke rows cannot exceed the 16-frame model context")
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
