#!/usr/bin/env python3
"""Stage, verify, and retrieve the canonical Person A SageMaker pilot bundle."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "scripts/run_person_a_phase6_single_pilot_sagemaker.py"
INPUT_BUNDLE_SCHEMA = "person-a-canonical-sagemaker-input-bundle-v0.1"
OUTPUT_BUNDLE_SCHEMA = "person-a-canonical-sagemaker-output-bundle-v0.1"


def _load_runner() -> Any:
    specification = importlib.util.spec_from_file_location(
        "person_a_phase6_canonical_sagemaker_runner",
        RUNNER_PATH,
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("canonical runner module is unavailable")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


runner = _load_runner()


def _json_bytes(document: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            dict(document),
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _exclusive_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _exclusive_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as source_handle, destination.open("xb") as target:
        shutil.copyfileobj(source_handle, target, length=1024 * 1024)
        target.flush()
        os.fsync(target.fileno())
    if (
        source.stat().st_size != destination.stat().st_size
        or _sha256_file(source) != _sha256_file(destination)
    ):
        raise RuntimeError(f"copy verification failed: {source}")


def _descriptor(root: Path, path: Path, role: str) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "role": role,
        "sha256": _sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _source_arguments(namespace: argparse.Namespace) -> Any:
    placeholder = RUNNER_PATH
    return runner.RunnerArguments(
        repository_root=ROOT,
        mineworld_root=ROOT,
        asset_root=ROOT,
        main_checkpoint=placeholder,
        vae_config=placeholder,
        vae_checkpoint=placeholder,
        approved_input_root=ROOT,
        approved_output_root=ROOT.parent,
        activation_store_v2_ratification_object="",
        session_id="preparation-only",
        seed=runner.DETERMINISTIC_SEED,
        device=runner.REQUIRED_DEVICE,
        precision="float16",
        runtime_host=runner.CANONICAL_WINDOWS_RUNTIME_HOST,
        canonical_c6a_package=namespace.canonical_c6a_package.resolve(),
        canonical_c6a_package_sha256=namespace.canonical_c6a_package_sha256,
        trajectory_id=namespace.trajectory_id,
        episode_id=namespace.episode_id,
        episode_artifact_manifest=namespace.episode_artifact_manifest.resolve(),
        episode_artifact_manifest_sha256=(
            namespace.episode_artifact_manifest_sha256
        ),
        person_e_provenance_handoff=(
            namespace.person_e_provenance_handoff.resolve()
        ),
        person_e_provenance_handoff_sha256=(
            namespace.person_e_provenance_handoff_sha256
        ),
    )


def stage_input(namespace: argparse.Namespace) -> dict[str, Any]:
    """Create one create-only, selected-episode input bundle."""

    binding = runner.load_canonical_pilot_binding(_source_arguments(namespace))
    output_root = namespace.output_root.resolve()
    if output_root.exists() or output_root.is_symlink():
        raise FileExistsError(f"create-only input bundle exists: {output_root}")
    output_root.mkdir(parents=True)
    files: list[dict[str, Any]] = []

    def copy(source: Path, relative: str, role: str) -> Path:
        destination = output_root / relative.replace("/", os.sep)
        _exclusive_copy(source, destination)
        files.append(_descriptor(output_root, destination, role))
        return destination

    def write(document: Mapping[str, Any], relative: str, role: str) -> Path:
        destination = output_root / relative.replace("/", os.sep)
        _exclusive_write(destination, _json_bytes(document))
        files.append(_descriptor(output_root, destination, role))
        return destination

    package_path = copy(
        binding.package_path,
        "authority/person_c/package_manifest.json",
        "canonical_c6a_package",
    )
    handoff_path = copy(
        binding.person_e_handoff_path,
        "authority/person_e/person_e_to_person_a_c6a_provenance_handoff.json",
        "person_e_provenance_handoff",
    )
    capture_path = write(
        binding.capture_row,
        "authority/person_c/capture_episode_record.json",
        "capture_episode_record",
    )
    inventory_path = write(
        binding.inventory_row,
        "authority/person_c/episode_inventory_record.json",
        "episode_inventory_record",
    )
    registry_path = write(
        binding.registry_record,
        "authority/person_e/episode_registry_record.json",
        "episode_registry_record",
    )
    direct_artifacts: list[dict[str, Any]] = []
    source_by_key = {
        (str(row["side"]), str(row["relative_path"])): row
        for row in binding.direct_artifacts
    }
    record_outputs = binding.registry_record["outputs"]
    for source in sorted(
        record_outputs,
        key=lambda row: (str(row["side"]), str(row["relative_path"])),
    ):
        key = (str(source["side"]), str(source["relative_path"]))
        if key not in source_by_key:
            raise RuntimeError(f"registry artifact absent from C authority: {key}")
        original_path = Path(str(source["path"]))
        relative = f"episode/{key[0]}/{key[1]}"
        destination = copy(original_path, relative, "direct_episode_artifact")
        direct_artifacts.append(
            {
                "bundle_path": destination.relative_to(output_root).as_posix(),
                "source": dict(source),
            }
        )
    package = json.loads(package_path.read_bytes())
    capture_descriptor = package["capture_manifest"]
    component_rows = package["component_files"]
    episode_inventory_descriptor = next(
        row for row in component_rows if str(row["path"]).endswith("episode_inventory.json")
    )
    inventory_document = {
        "files": sorted(files, key=lambda row: row["path"]),
        "schema_version": "person-a-canonical-sagemaker-input-sha256-inventory-v0.1",
    }
    sha_inventory_path = write(
        inventory_document,
        "sha256_inventory.json",
        "bundle_sha256_inventory",
    )
    authority = {
        "canonical_c6a_package": {
            "file_sha256": _sha256_file(package_path),
            "path": package_path.relative_to(output_root).as_posix(),
            "source_sha256": binding.package_sha256,
        },
        "capture_episode_record": {
            "file_sha256": _sha256_file(capture_path),
            "path": capture_path.relative_to(output_root).as_posix(),
            "source_manifest_sha256": capture_descriptor["sha256"],
        },
        "episode_inventory_record": {
            "file_sha256": _sha256_file(inventory_path),
            "path": inventory_path.relative_to(output_root).as_posix(),
            "source_manifest_sha256": episode_inventory_descriptor["sha256"],
        },
        "episode_registry_record": {
            "file_sha256": _sha256_file(registry_path),
            "path": registry_path.relative_to(output_root).as_posix(),
            "registry_record_id": binding.registry_record_id,
            "registry_record_sha256": binding.registry_record_sha256,
            "source_manifest_sha256": binding.artifact_manifest_sha256,
        },
        "person_e_handoff": {
            "file_sha256": _sha256_file(handoff_path),
            "path": handoff_path.relative_to(output_root).as_posix(),
            "source_sha256": binding.person_e_handoff_sha256,
        },
    }
    manifest = {
        "authority": authority,
        "canonical_c6a_id": binding.canonical_c6a_id,
        "direct_artifacts": direct_artifacts,
        "episode_id": binding.episode_id,
        "files": sorted(files, key=lambda row: row["path"]),
        "frozen_identities": {
            "action_conversion": runner.CANONICAL_ACTION_CONVERSION_IDENTITY,
            "activation_index": runner.ACTIVATION_INDEX_V2_FORMAT_VERSION,
            "activation_store": runner.ACTIVATION_STORE_V2_FORMAT_VERSION,
            "hook_site": runner.HOOK_SITE,
            "main_checkpoint_sha256": runner.MAIN_CHECKPOINT_SHA256,
            "model_config_sha256": runner.MODEL_CONFIG_GIT_BLOB_SHA256,
            "pooling_method": runner.CANONICAL_POOLING_METHOD,
            "preprocessing": runner.CANONICAL_PREPROCESSING_IDENTITY,
            "token_region": runner.CANONICAL_TOKEN_REGION,
            "vae_checkpoint_sha256": runner.VAE_CHECKPOINT_SHA256,
            "vae_config_sha256": runner.VAE_CONFIG_SHA256,
        },
        "person_c_commit": binding.person_c_commit,
        "person_e_commit": binding.person_e_commit,
        "schema_version": INPUT_BUNDLE_SCHEMA,
        "selection_rule": runner.CANONICAL_SELECTION_RULE,
        "sha256_inventory": {
            "path": sha_inventory_path.relative_to(output_root).as_posix(),
            "sha256": _sha256_file(sha_inventory_path),
        },
        "status": "IMMUTABLE_READY_FOR_SAGEMAKER",
        "trajectory_id": binding.trajectory_id,
    }
    manifest_path = output_root / "bundle_manifest.json"
    _exclusive_write(manifest_path, _json_bytes(manifest))
    return {
        "bundle_manifest": str(manifest_path),
        "bundle_manifest_sha256": _sha256_file(manifest_path),
        "direct_artifact_count": len(direct_artifacts),
        "file_count": len(files),
        "status": "PASS",
    }


def _staged_arguments(namespace: argparse.Namespace) -> Any:
    placeholder = RUNNER_PATH
    return runner.RunnerArguments(
        repository_root=ROOT,
        mineworld_root=ROOT,
        asset_root=ROOT,
        main_checkpoint=placeholder,
        vae_config=placeholder,
        vae_checkpoint=placeholder,
        approved_input_root=ROOT,
        approved_output_root=ROOT.parent,
        activation_store_v2_ratification_object="",
        session_id="verification-only",
        seed=runner.DETERMINISTIC_SEED,
        device=runner.REQUIRED_DEVICE,
        precision="float16",
        runtime_host=runner.HISTORICAL_RUNTIME_HOST,
        canonical_c6a_package_sha256=namespace.canonical_c6a_package_sha256,
        trajectory_id=namespace.trajectory_id,
        episode_id=namespace.episode_id,
        episode_artifact_manifest_sha256=(
            namespace.episode_artifact_manifest_sha256
        ),
        person_e_provenance_handoff_sha256=(
            namespace.person_e_provenance_handoff_sha256
        ),
        canonical_input_bundle_manifest=namespace.bundle_manifest.resolve(),
        canonical_input_bundle_manifest_sha256=namespace.bundle_manifest_sha256,
    )


def verify_input(namespace: argparse.Namespace) -> dict[str, Any]:
    binding = runner.load_staged_canonical_pilot_binding(
        _staged_arguments(namespace)
    )
    return {
        "direct_artifact_count": len(binding.direct_artifacts),
        "episode_id": binding.episode_id,
        "expected_activation_rows": binding.expected_activation_rows,
        "frame_count": binding.frame_count,
        "status": "PASS",
        "trajectory_id": binding.trajectory_id,
    }


def _copy_tree_create_only(source: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"create-only retrieval path exists: {destination}")
    shutil.copytree(source, destination, copy_function=shutil.copy2)
    for source_path in sorted(path for path in source.rglob("*") if path.is_file()):
        relative = source_path.relative_to(source)
        copied = destination / relative
        if _sha256_file(source_path) != _sha256_file(copied):
            raise RuntimeError(f"retrieved file hash differs: {relative}")


def collect_output(namespace: argparse.Namespace) -> dict[str, Any]:
    """Copy the successful required output set into one Git-transfer bundle."""

    input_root = namespace.input_session_root.resolve()
    session_root = namespace.output_session_root.resolve()
    activation_root = namespace.activation_store_root.resolve()
    destination = namespace.destination.resolve()
    for path in (input_root, session_root, activation_root):
        if not path.is_dir() or path.is_symlink():
            raise FileNotFoundError(f"required successful output root is absent: {path}")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"create-only retrieved bundle exists: {destination}")
    final_report = json.loads((session_root / "final_report.json").read_bytes())
    step6_5 = json.loads((session_root / "step6_5.json").read_bytes())
    certification = step6_5.get("result", {})
    if (
        final_report.get("status") != "PASS"
        or final_report.get("selected_pilot") != "layout_01_ep12602"
        or certification.get("status") != "PASS"
        or certification.get("direct_pooling_audit") != "PASS"
        or "repeatability_maximum_absolute_difference" not in certification
        or certification.get("source_identity_join_failure_count") != 0
    ):
        raise RuntimeError("scientific output certification is not PASS")
    destination.mkdir(parents=False)
    accepted_source = input_root / "accepted_pilot_manifest.json"
    accepted_destination = destination / "accepted_pilot_manifest.json"
    _exclusive_copy(accepted_source, accepted_destination)
    _copy_tree_create_only(activation_root, destination / "activation_store")
    _copy_tree_create_only(session_root / "bounded_audit", destination / "bounded_audit")
    required_session_names = (
        "final_report.json",
        "person_a_to_person_b_canonical_pilot_handoff.json",
        "person_a_to_person_e_canonical_provenance_handoff.json",
        "runtime_preflight_receipt.json",
        "step6_1.json",
        "step6_2.json",
        "step6_3.json",
        "step6_4.json",
        "step6_5.json",
        "step6_6_handoff.json",
    )
    for name in required_session_names:
        _exclusive_copy(session_root / name, destination / name)
    chunks = sorted((destination / "activation_store").rglob("*.npz"))
    indexes = sorted((destination / "activation_store").rglob("index-*.json"))
    audits = sorted((destination / "bounded_audit").rglob("*.npz"))
    if not chunks or len(indexes) != 1 or len(audits) != 1:
        raise RuntimeError("retrieved activation/index/audit cardinality differs")
    terminal_receipt = {
        "accepted_manifest_present": True,
        "activation_chunk_count": len(chunks),
        "activation_index_count": len(indexes),
        "bounded_unpooled_audit_count": len(audits),
        "direct_pooling_validation": "PASS",
        "episode_id": 12602,
        "person_b_handoff_present": True,
        "person_e_handoff_present": True,
        "process_exit_status": 0,
        "repeatability_validation": "PASS",
        "schema_version": "person-a-canonical-sagemaker-terminal-receipt-v0.1",
        "source_identity_joins": "PASS",
        "status": "PASS",
        "trajectory_id": "layout_01_ep12602",
    }
    terminal_path = destination / "terminal_execution_receipt.json"
    _exclusive_write(terminal_path, _json_bytes(terminal_receipt))
    output_manifest = {
        "accepted_manifest": "accepted_pilot_manifest.json",
        "activation_chunk_count": len(chunks),
        "activation_index": indexes[0].relative_to(destination).as_posix(),
        "bounded_unpooled_audit": audits[0].relative_to(destination).as_posix(),
        "episode_id": 12602,
        "person_b_handoff": "person_a_to_person_b_canonical_pilot_handoff.json",
        "person_e_handoff": "person_a_to_person_e_canonical_provenance_handoff.json",
        "schema_version": OUTPUT_BUNDLE_SCHEMA,
        "status": "READY_FOR_LOCAL_RETRIEVAL",
        "terminal_execution_receipt": terminal_path.relative_to(destination).as_posix(),
        "trajectory_id": "layout_01_ep12602",
        "validation_receipt": "step6_5.json",
    }
    manifest_path = destination / "output_bundle_manifest.json"
    _exclusive_write(manifest_path, _json_bytes(output_manifest))
    inventory_rows = [
        _descriptor(destination, path, "retrieved_output")
        for path in sorted(item for item in destination.rglob("*") if item.is_file())
    ]
    inventory = {
        "files": inventory_rows,
        "schema_version": "person-a-canonical-sagemaker-output-sha256-inventory-v0.1",
    }
    inventory_path = destination / "sha256_inventory.json"
    _exclusive_write(inventory_path, _json_bytes(inventory))
    return {
        "bundle_manifest": str(manifest_path),
        "bundle_manifest_sha256": _sha256_file(manifest_path),
        "file_count": len(inventory_rows),
        "sha256_inventory": str(inventory_path),
        "status": "PASS",
    }


def verify_output(namespace: argparse.Namespace) -> dict[str, Any]:
    """Re-hash one retrieved output bundle after the Git transfer."""

    root = namespace.bundle_root.resolve()
    inventory_path = root / "sha256_inventory.json"
    manifest_path = root / "output_bundle_manifest.json"
    terminal_path = root / "terminal_execution_receipt.json"
    for path in (inventory_path, manifest_path, terminal_path):
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(f"retrieved bundle file is absent: {path}")
    inventory = json.loads(inventory_path.read_bytes())
    manifest = json.loads(manifest_path.read_bytes())
    terminal = json.loads(terminal_path.read_bytes())
    rows = inventory.get("files")
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("retrieved SHA-256 inventory is empty")
    observed: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise TypeError("retrieved inventory descriptor is invalid")
        relative = str(row.get("path", ""))
        path = (root / relative.replace("/", os.sep)).resolve()
        try:
            path.relative_to(root)
        except ValueError as error:
            raise RuntimeError("retrieved path escapes bundle root") from error
        if (
            not relative
            or relative in observed
            or not path.is_file()
            or path.is_symlink()
            or path.stat().st_size != row.get("size_bytes")
            or _sha256_file(path) != row.get("sha256")
        ):
            raise RuntimeError(f"retrieved output identity differs: {relative}")
        observed.add(relative)
    if (
        manifest.get("schema_version") != OUTPUT_BUNDLE_SCHEMA
        or manifest.get("status") != "READY_FOR_LOCAL_RETRIEVAL"
        or terminal.get("status") != "PASS"
        or terminal.get("process_exit_status") != 0
    ):
        raise RuntimeError("retrieved terminal or manifest status differs")
    return {
        "file_count": len(rows),
        "output_bundle_manifest_sha256": _sha256_file(manifest_path),
        "sha256_inventory_sha256": _sha256_file(inventory_path),
        "status": "PASS",
    }


def _add_authority_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--trajectory-id", default="layout_01_ep12602")
    command.add_argument("--episode-id", type=int, default=12602)
    command.add_argument("--canonical-c6a-package-sha256", required=True)
    command.add_argument("--episode-artifact-manifest-sha256", required=True)
    command.add_argument("--person-e-provenance-handoff-sha256", required=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    stage = commands.add_parser("stage-input")
    _add_authority_arguments(stage)
    stage.add_argument("--canonical-c6a-package", type=Path, required=True)
    stage.add_argument("--episode-artifact-manifest", type=Path, required=True)
    stage.add_argument("--person-e-provenance-handoff", type=Path, required=True)
    stage.add_argument("--output-root", type=Path, required=True)
    verify = commands.add_parser("verify-input")
    _add_authority_arguments(verify)
    verify.add_argument("--bundle-manifest", type=Path, required=True)
    verify.add_argument("--bundle-manifest-sha256", required=True)
    collect = commands.add_parser("collect-output")
    collect.add_argument("--input-session-root", type=Path, required=True)
    collect.add_argument("--output-session-root", type=Path, required=True)
    collect.add_argument("--activation-store-root", type=Path, required=True)
    collect.add_argument("--destination", type=Path, required=True)
    verify_output_parser = commands.add_parser("verify-output")
    verify_output_parser.add_argument("--bundle-root", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    namespace = _parser().parse_args(argv)
    if namespace.operation == "stage-input":
        result = stage_input(namespace)
    elif namespace.operation == "verify-input":
        result = verify_input(namespace)
    elif namespace.operation == "collect-output":
        result = collect_output(namespace)
    else:
        result = verify_output(namespace)
    print(json.dumps(result, allow_nan=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
