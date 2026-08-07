from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any


EXPECTED_SESSION_PREFIX = "person-a-phase4-hookprobe-aws-"
EXPECTED_MINEOCCLUDE_REVISION = (
    "619d9c051106ed6c68122dccc846bd4109a4fda5"
)
EXPECTED_MINEWORLD_REVISION = (
    "9f49efbcc68a5f0cf60e78f0abc566eac409282f"
)
EXPECTED_ASSET_REVISION = (
    "0dd5561ab317115831badc50e09a6ebe98693d0e"
)
EXPECTED_ENVIRONMENT_SHA256 = (
    "8e0bffcf11827d5b8d08a5f717765dc37bbc84de9604399e78d2c8ec4cfd6619"
)

MODEL_CONFIG_SHA256 = (
    "e13b3a80fb370547a05852809c2c8f02d05ebe2fce3b3bb2fd1ee54eee78c018"
)
MAIN_CHECKPOINT_SHA256 = (
    "a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5"
)
VAE_CONFIG_SHA256 = (
    "32ca759d5b90f0c5aa5df0e312a81e03dd4d3af68896863c88f910d19f2526cb"
)
VAE_CHECKPOINT_SHA256 = (
    "370d06be427e034476b6b95ba0080a4b48266e876c4776a757b944b87b87d9ab"
)

MINEOCCLUDE_ROOT = Path("/home/sagemaker-user/MineOcclude")
MINEWORLD_ROOT = Path("/home/sagemaker-user/MineWorld-Upstream")
ASSET_ROOT = Path("/home/sagemaker-user/MineWorld-Assets-Pinned")

MODEL_CONFIG = MINEWORLD_ROOT / "configs/700M_16f.yaml"
MAIN_CHECKPOINT = ASSET_ROOT / "checkpoints/700M_16f.ckpt"
VAE_CONFIG = ASSET_ROOT / "checkpoints/vae/config.json"
VAE_CHECKPOINT = ASSET_ROOT / "checkpoints/vae/vae.ckpt"

EXPECTED_LAYER_COUNT = 20
EXPECTED_HIDDEN_SIZE = 2048
PROBE_SEQUENCE_LENGTH = 347


def git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def qualified_type(value: object) -> str:
    value_type = type(value)
    return f"{value_type.__module__}.{value_type.__qualname__}"


def module_hook_count(module: object) -> int:
    hooks = getattr(module, "_forward_hooks", None)
    if hooks is None:
        raise RuntimeError(
            f"{qualified_type(module)} does not expose _forward_hooks"
        )
    return len(hooks)


def write_json(path: Path, document: dict[str, Any]) -> str:
    encoded = (
        json.dumps(
            document,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    path.write_bytes(encoded)
    return hashlib.sha256(encoded).hexdigest()


def main() -> int:
    session_id = os.environ.get("SESSION_ID", "")
    evidence_root_text = os.environ.get("EVIDENCE_ROOT", "")

    if not session_id.startswith(EXPECTED_SESSION_PREFIX):
        print("ERROR: SESSION_ID is missing or invalid", file=sys.stderr)
        return 2
    if not evidence_root_text:
        print("ERROR: EVIDENCE_ROOT is missing", file=sys.stderr)
        return 2

    evidence_root = Path(evidence_root_text).resolve()
    expected_root = Path(
        f"/home/sagemaker-user/mineocclude-phase4-evidence/{session_id}"
    ).resolve()
    if evidence_root != expected_root:
        print(
            "ERROR: EVIDENCE_ROOT does not match SESSION_ID",
            file=sys.stderr,
        )
        return 2

    report_path = evidence_root / "hook_probe_report.json"
    if report_path.exists():
        print(
            f"ERROR: refusing to overwrite existing report: {report_path}",
            file=sys.stderr,
        )
        return 2

    evidence_root.mkdir(parents=True, exist_ok=True)

    manager = None
    discovery = None
    runtime_layers: list[tuple[Any, object]] = []
    hook_counts_before: dict[int, int] = {}
    hook_counts_registered: dict[int, int] = {}
    hook_counts_after_forward: dict[int, int] = {}
    hook_counts_after: dict[int, int] = {}
    cleanup_errors: list[str] = []

    base_report: dict[str, Any] = {
        "schema_version": "1.0",
        "probe_version": "person-a-phase4-hook-output-probe-v1.0",
        "session_id": session_id,
        "classification": (
            "bounded_non_scientific_runtime_structure_probe"
        ),
        "probe_input": {
            "classification": "synthetic_valid_token_ids",
            "batch_size": 1,
            "sequence_length": PROBE_SEQUENCE_LENGTH,
            "token_value": 0,
            "scientific_result_claimed": False,
        },
        "expected_identity": {
            "mineocclude_revision": EXPECTED_MINEOCCLUDE_REVISION,
            "mineworld_revision": EXPECTED_MINEWORLD_REVISION,
            "asset_revision": EXPECTED_ASSET_REVISION,
            "environment_report_sha256": EXPECTED_ENVIRONMENT_SHA256,
            "layer_count": EXPECTED_LAYER_COUNT,
            "hidden_size": EXPECTED_HIDDEN_SIZE,
            "device": "cuda:0",
            "precision": "float16",
        },
        "paths": {
            "mineocclude_root": str(MINEOCCLUDE_ROOT),
            "mineworld_root": str(MINEWORLD_ROOT),
            "asset_root": str(ASSET_ROOT),
            "model_config": str(MODEL_CONFIG),
            "main_checkpoint": str(MAIN_CHECKPOINT),
            "vae_config": str(VAE_CONFIG),
            "vae_checkpoint": str(VAE_CHECKPOINT),
        },
    }

    try:
        environment_report = evidence_root / "environment_report.txt"
        required_paths = (
            MINEOCCLUDE_ROOT,
            MINEWORLD_ROOT,
            ASSET_ROOT,
            MODEL_CONFIG,
            MAIN_CHECKPOINT,
            VAE_CONFIG,
            VAE_CHECKPOINT,
            environment_report,
        )
        missing = [str(path) for path in required_paths if not path.exists()]
        if missing:
            raise RuntimeError(f"required paths are missing: {missing}")

        from mineocclude.models.phase3_certification import (
            _validate_asset_lock,
        )

        verified_assets = _validate_asset_lock(ASSET_ROOT)

        actual_identity = {
            "branch": git(
                MINEOCCLUDE_ROOT,
                "branch",
                "--show-current",
            ),
            "mineocclude_revision": git(
                MINEOCCLUDE_ROOT,
                "rev-parse",
                "HEAD",
            ),
            "mineworld_revision": git(
                MINEWORLD_ROOT,
                "rev-parse",
                "HEAD",
            ),
            "asset_revision": EXPECTED_ASSET_REVISION,
            "asset_identity_source": (
                "configs/assets/mineworld_assets_v1.json"
            ),
            "verified_asset_paths": {
                relative_path: str(asset_path)
                for relative_path, asset_path in sorted(
                    verified_assets.items()
                )
            },
            "mineocclude_status": git(
                MINEOCCLUDE_ROOT,
                "status",
                "--porcelain",
            ),
            "mineworld_status": git(
                MINEWORLD_ROOT,
                "status",
                "--porcelain",
            ),
            "asset_status": (
                "verified_by_project_lock_size_and_sha256"
            ),
            "environment_report_sha256": sha256_file(
                environment_report
            ),
        }
        base_report["actual_identity"] = actual_identity

        if actual_identity["branch"] != "role/person-a-model":
            raise RuntimeError(
                f"unexpected branch: {actual_identity['branch']}"
            )
        if (
            actual_identity["mineocclude_revision"]
            != EXPECTED_MINEOCCLUDE_REVISION
        ):
            raise RuntimeError("MineOcclude revision mismatch")
        if (
            actual_identity["mineworld_revision"]
            != EXPECTED_MINEWORLD_REVISION
        ):
            raise RuntimeError("MineWorld revision mismatch")
        if actual_identity["asset_revision"] != EXPECTED_ASSET_REVISION:
            raise RuntimeError("asset revision mismatch")
        if actual_identity["environment_report_sha256"] != (
            EXPECTED_ENVIRONMENT_SHA256
        ):
            raise RuntimeError("environment report hash mismatch")
        if actual_identity["mineocclude_status"]:
            raise RuntimeError("MineOcclude worktree is dirty")
        if actual_identity["mineworld_status"]:
            raise RuntimeError("MineWorld worktree is dirty")
        if actual_identity["asset_status"] != (
            "verified_by_project_lock_size_and_sha256"
        ):
            raise RuntimeError("asset verification did not complete")

        from mineocclude.activations.hooks import (
            ScopedHookManager,
            discover_decoder_hook_site,
            normalize_hook_output,
        )
        from mineocclude.models.mineworld_adapter import (
            RuntimeLoadRequest,
            create_mineworld_adapter,
        )

        adapter = create_mineworld_adapter()
        load_request = RuntimeLoadRequest(
            schema_version="1.0",
            runtime_id=f"{session_id}:runtime",
            mineocclude_revision=EXPECTED_MINEOCCLUDE_REVISION,
            mineworld_source_revision=EXPECTED_MINEWORLD_REVISION,
            modelscope_asset_revision=EXPECTED_ASSET_REVISION,
            mineworld_source_root=MINEWORLD_ROOT,
            model_config_path=MODEL_CONFIG,
            main_checkpoint_path=MAIN_CHECKPOINT,
            vae_config_path=VAE_CONFIG,
            vae_checkpoint_path=VAE_CHECKPOINT,
            model_config_sha256=MODEL_CONFIG_SHA256,
            main_checkpoint_sha256=MAIN_CHECKPOINT_SHA256,
            vae_config_sha256=VAE_CONFIG_SHA256,
            vae_checkpoint_sha256=VAE_CHECKPOINT_SHA256,
            environment_report_sha256=EXPECTED_ENVIRONMENT_SHA256,
            precision="float16",
            device="cuda:0",
            expected_adapter_code_sha256=None,
        )

        load_started = time.perf_counter()
        runtime_identity = adapter.load_runtime(load_request)
        model_load_seconds = time.perf_counter() - load_started

        loaded_runtime = getattr(adapter, "_runtime", None)
        if loaded_runtime is None:
            raise RuntimeError(
                "loaded adapter does not expose its private runtime"
            )

        model = getattr(loaded_runtime, "model", None)
        if model is None:
            raise RuntimeError("loaded runtime does not expose model")

        transformer = getattr(model, "transformer", None)
        if transformer is None or not callable(transformer):
            raise RuntimeError(
                "loaded model does not expose callable transformer"
            )

        refresh_kvcache = getattr(transformer, "refresh_kvcache", None)
        if not callable(refresh_kvcache):
            raise RuntimeError(
                "loaded transformer does not expose refresh_kvcache"
            )

        discovery = discover_decoder_hook_site(model)
        runtime_layers = list(discovery.iter_runtime_layers())

        if len(runtime_layers) != EXPECTED_LAYER_COUNT:
            raise RuntimeError(
                f"expected 20 discovered layers, got {len(runtime_layers)}"
            )
        if discovery.module_name_pattern != (
            "transformer.model.layers.{layer_idx}"
        ):
            raise RuntimeError(
                "unexpected discovered module-name pattern: "
                f"{discovery.module_name_pattern}"
            )

        hook_counts_before = {
            metadata.layer_idx: module_hook_count(module)
            for metadata, module in runtime_layers
        }

        raw_pending: dict[int, dict[str, Any]] = {}
        raw_by_layer: dict[int, dict[str, Any]] = {}

        def observe_raw_output(output: object):
            normalized = normalize_hook_output(output)
            tensor_identity = id(normalized.tensor)
            if tensor_identity in raw_pending:
                raise RuntimeError(
                    "raw output tensor identity was unexpectedly reused"
                )

            raw_pending[tensor_identity] = {
                "raw_python_type": qualified_type(output),
                "is_tuple": isinstance(output, tuple),
                "tuple_length": (
                    len(output) if isinstance(output, tuple) else None
                ),
                "tuple_element_types": (
                    [qualified_type(value) for value in output]
                    if isinstance(output, tuple)
                    else None
                ),
            }
            return normalized

        def record_raw_identity(capture: object) -> None:
            output = getattr(capture, "output")
            layer = getattr(capture, "layer")
            tensor_identity = id(output.tensor)

            raw = raw_pending.pop(tensor_identity, None)
            if raw is None:
                raise RuntimeError(
                    "could not bind raw output to its exact normalized tensor"
                )

            raw_by_layer[layer.layer_idx] = raw

        manager = ScopedHookManager(
            discovery,
            output_normalizer=observe_raw_output,
            capture_callback=record_raw_identity,
        )

        import torch

        input_ids = torch.zeros(
            (1, PROBE_SEQUENCE_LENGTH),
            dtype=torch.long,
            device="cuda:0",
        )
        position_ids = torch.arange(
            PROBE_SEQUENCE_LENGTH,
            dtype=torch.long,
            device="cuda:0",
        )

        refresh_kvcache()
        torch.cuda.reset_peak_memory_stats(0)
        torch.cuda.synchronize()

        forward_started = time.perf_counter()
        with manager:
            hook_counts_registered = {
                metadata.layer_idx: module_hook_count(module)
                for metadata, module in runtime_layers
            }
            registered_hook_count_during = (
                manager.registered_hook_count
            )

            with torch.inference_mode(), torch.autocast(
                "cuda",
                dtype=torch.float16,
            ):
                transformer_output = transformer(
                    input_ids=input_ids,
                    position_ids=position_ids,
                )

            torch.cuda.synchronize()
            forward_seconds = time.perf_counter() - forward_started

            hook_counts_after_forward = {
                metadata.layer_idx: module_hook_count(module)
                for metadata, module in runtime_layers
            }
            captures = dict(manager.require_complete())

        hook_counts_after = {
            metadata.layer_idx: module_hook_count(module)
            for metadata, module in runtime_layers
        }

        if raw_pending:
            raise RuntimeError(
                "one or more raw outputs were not bound to captures"
            )

        expected_indices = list(range(EXPECTED_LAYER_COUNT))
        observed_indices = sorted(captures)
        raw_indices = sorted(raw_by_layer)

        if observed_indices != expected_indices:
            raise RuntimeError(
                f"capture indices mismatch: {observed_indices}"
            )
        if raw_indices != expected_indices:
            raise RuntimeError(
                f"raw-output indices mismatch: {raw_indices}"
            )
        if registered_hook_count_during != EXPECTED_LAYER_COUNT:
            raise RuntimeError(
                "manager did not register exactly 20 handles"
            )
        if not manager.closed:
            raise RuntimeError("manager did not close after context exit")
        if manager.registered_hook_count != 0:
            raise RuntimeError(
                "manager retained handles after context exit"
            )

        for layer_idx in expected_indices:
            if hook_counts_registered[layer_idx] != (
                hook_counts_before[layer_idx] + 1
            ):
                raise RuntimeError(
                    f"layer {layer_idx} did not gain exactly one hook"
                )
            if hook_counts_after_forward[layer_idx] != (
                hook_counts_registered[layer_idx]
            ):
                raise RuntimeError(
                    f"layer {layer_idx} hook count changed during forward"
                )
            if hook_counts_after[layer_idx] != (
                hook_counts_before[layer_idx]
            ):
                raise RuntimeError(
                    f"layer {layer_idx} hook count was not restored"
                )

        capture_rows: list[dict[str, Any]] = []
        for layer_idx in expected_indices:
            capture = captures[layer_idx]
            normalized = capture.output
            tensor = normalized.tensor
            raw = raw_by_layer[layer_idx]

            row = {
                "layer_idx": layer_idx,
                "module_name": capture.layer.module_name,
                "module_type": capture.layer.module_type,
                "conceptual_site": capture.layer.conceptual_site,
                "raw_python_type": raw["raw_python_type"],
                "raw_is_tuple": raw["is_tuple"],
                "raw_tuple_length": raw["tuple_length"],
                "raw_tuple_element_types": raw[
                    "tuple_element_types"
                ],
                "normalization_container_kind": (
                    normalized.container_kind
                ),
                "normalization_tuple_index": normalized.tuple_index,
                "normalization_structured_field": (
                    normalized.structured_field
                ),
                "shape": list(normalized.shape),
                "dtype": str(tensor.dtype),
                "device": str(tensor.device),
            }
            capture_rows.append(row)

        expected_shape = [
            1,
            PROBE_SEQUENCE_LENGTH,
            EXPECTED_HIDDEN_SIZE,
        ]
        if any(row["shape"] != expected_shape for row in capture_rows):
            raise RuntimeError("one or more capture shapes are unexpected")
        if any(
            row["dtype"] != "torch.float16"
            for row in capture_rows
        ):
            raise RuntimeError("one or more capture dtypes are unexpected")
        if any(row["device"] != "cuda:0" for row in capture_rows):
            raise RuntimeError("one or more capture devices are unexpected")

        raw_types = {
            row["raw_python_type"] for row in capture_rows
        }
        container_kinds = {
            row["normalization_container_kind"]
            for row in capture_rows
        }
        tuple_indices = {
            row["normalization_tuple_index"]
            for row in capture_rows
        }

        if len(raw_types) != 1:
            raise RuntimeError(
                f"raw output types differ across depth: {raw_types}"
            )
        if len(container_kinds) != 1:
            raise RuntimeError(
                "normalization container kind differs across depth"
            )

        container_kind = next(iter(container_kinds))
        if container_kind == "tuple":
            if tuple_indices != {0}:
                raise RuntimeError(
                    "tuple residual was not consistently at index 0"
                )
            if any(
                not row["raw_is_tuple"] for row in capture_rows
            ):
                raise RuntimeError(
                    "tuple normalization disagrees with raw type"
                )
        elif container_kind == "direct_tensor":
            if tuple_indices != {None}:
                raise RuntimeError(
                    "direct tensor unexpectedly recorded tuple index"
                )
            if any(row["raw_is_tuple"] for row in capture_rows):
                raise RuntimeError(
                    "direct normalization disagrees with raw type"
                )
        else:
            raise RuntimeError(
                f"unexpected real-runtime container kind: {container_kind}"
            )

        report = {
            **base_report,
            "status": "passed",
            "runtime_identity": dataclasses.asdict(runtime_identity),
            "discovery": {
                "conceptual_site": discovery.conceptual_site,
                "discovery_version": discovery.discovery_version,
                "module_name_pattern": discovery.module_name_pattern,
                "layer_count": len(runtime_layers),
                "layer_indices": expected_indices,
                "module_types": sorted(
                    {
                        metadata.module_type
                        for metadata, _module in runtime_layers
                    }
                ),
            },
            "result": {
                "raw_python_type": next(iter(raw_types)),
                "normalization_container_kind": container_kind,
                "normalization_tuple_indices": sorted(
                    value
                    for value in tuple_indices
                    if value is not None
                ),
                "stable_across_all_layers": True,
                "capture_shape": expected_shape,
                "dtype": "torch.float16",
                "device": "cuda:0",
                "final_transformer_output_type": qualified_type(
                    transformer_output
                ),
            },
            "captures": capture_rows,
            "hook_cleanup": {
                "manager_closed": manager.closed,
                "manager_registered_hook_count_after": (
                    manager.registered_hook_count
                ),
                "registered_hook_count_during": (
                    registered_hook_count_during
                ),
                "counts_before": hook_counts_before,
                "counts_registered": hook_counts_registered,
                "counts_after_forward": hook_counts_after_forward,
                "counts_after": hook_counts_after,
                "all_layer_counts_restored": (
                    hook_counts_after == hook_counts_before
                ),
            },
            "timings": {
                "model_load_seconds": model_load_seconds,
                "forward_seconds": forward_seconds,
            },
            "cuda": {
                "peak_allocated_bytes": (
                    torch.cuda.max_memory_allocated(0)
                ),
                "peak_reserved_bytes": (
                    torch.cuda.max_memory_reserved(0)
                ),
            },
        }

        report_sha256 = write_json(report_path, report)

        print("PHASE4_HOOK_PROBE_STATUS=PASS")
        print(f"REPORT_PATH={report_path}")
        print(f"REPORT_SHA256={report_sha256}")
        print(
            "RAW_OUTPUT_TYPE="
            f"{report['result']['raw_python_type']}"
        )
        print(
            "CONTAINER_KIND="
            f"{report['result']['normalization_container_kind']}"
        )
        print(
            "CAPTURE_SHAPE="
            f"{report['result']['capture_shape']}"
        )
        print(
            "HOOK_COUNTS_RESTORED="
            f"{report['hook_cleanup']['all_layer_counts_restored']}"
        )
        return 0

    except Exception as exc:
        if manager is not None and not manager.closed:
            try:
                manager.close()
            except Exception as cleanup_exc:
                cleanup_errors.append(
                    f"{type(cleanup_exc).__name__}: {cleanup_exc}"
                )

        if discovery is not None and runtime_layers:
            try:
                hook_counts_after = {
                    metadata.layer_idx: module_hook_count(module)
                    for metadata, module in runtime_layers
                }
            except Exception as cleanup_exc:
                cleanup_errors.append(
                    "post-failure hook inspection failed: "
                    f"{type(cleanup_exc).__name__}: {cleanup_exc}"
                )

        failure_report = {
            **base_report,
            "status": "failed",
            "error": {
                "type": qualified_type(exc),
                "message": str(exc),
                "traceback": traceback.format_exc(),
            },
            "hook_cleanup": {
                "manager_closed": (
                    None if manager is None else manager.closed
                ),
                "manager_registered_hook_count_after": (
                    None
                    if manager is None
                    else manager.registered_hook_count
                ),
                "counts_before": hook_counts_before,
                "counts_registered": hook_counts_registered,
                "counts_after_forward": hook_counts_after_forward,
                "counts_after": hook_counts_after,
                "cleanup_errors": cleanup_errors,
            },
        }

        report_sha256 = write_json(report_path, failure_report)
        print("PHASE4_HOOK_PROBE_STATUS=FAIL", file=sys.stderr)
        print(f"REPORT_PATH={report_path}", file=sys.stderr)
        print(f"REPORT_SHA256={report_sha256}", file=sys.stderr)
        print(
            f"ERROR_TYPE={qualified_type(exc)}",
            file=sys.stderr,
        )
        print(f"ERROR={exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
