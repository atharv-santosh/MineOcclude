"""CPU-only tests for Person A Phase 3 Wave 4 (Steps 3.8-3.9)."""

from __future__ import annotations

import contextlib
import copy
import dataclasses
import hashlib
import inspect
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.models import _mineworld_adapter_wave2 as wave2
from mineocclude.models import _mineworld_adapter_wave3 as wave3
from mineocclude.models import _mineworld_adapter_wave4 as wave4
from mineocclude.models import phase3_certification
from mineocclude.models.mineworld_adapter import (
    MINEWORLD_ADAPTER_API_VERSION,
    AcceptedTrajectoryInput,
    ActionConversionRequest,
    FramePreprocessRequest,
    FreeRolloutRequest,
    MineWorldAdapterError,
    RuntimeLoadRequest,
    TeacherForcedRequest,
)
from mineocclude.models.phase2_evidence import (
    EvidenceValidationError,
    canonical_json_bytes,
    sha256_file,
)
from tests.models import test_mineworld_adapter_wave3 as wave3_helpers


REPO_ROOT = Path(__file__).resolve().parents[2]
EXTERNAL_SOURCE = Path(r"C:\Users\lollo\MineWorld-Upstream")
FAILURE_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "models"
    / "phase3_wave4_failure_matrix.json"
)
TRAJECTORY_FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "trajectory" / "accepted_package.json"
)
RUNTIME_STUB = REPO_ROOT / "tests" / "fixtures" / "models" / "runtime_stub"
SHA256 = "a" * 64
CODE_INVENTORY = (
    ("a.py", "1" * 64, 1),
    ("b.py", "2" * 64, 2),
    ("c.py", "3" * 64, 3),
    ("d.py", "4" * 64, 4),
)
CODE_IDENTITY = wave4._AdapterCodeIdentity("5" * 64, CODE_INVENTORY)
PREFLIGHT_GIT_SHA = "0123456789abcdef0123456789abcdef01234567"


def _temporary_directory():
    return tempfile.TemporaryDirectory(
        ignore_cleanup_errors=True,
    )


def _environment_report() -> str:
    return """\
=== SYSTEM ===
OS: controlled-test
=== PACKAGE VERSIONS ===
controlled: PASS
=== IMPORT CHECKS ===
controlled: PASS
=== PYTORCH / CUDA ===
CUDA available: True
=== FINAL RESULT ===
PASS: Official CUDA-capable environment validated.
"""


def _expanded_package(count: int, media_path: Path) -> dict:
    package = json.loads(TRAJECTORY_FIXTURE.read_text(encoding="utf-8"))
    for name, artifact in package["artifacts"].items():
        artifact["sha256"] = hashlib.sha256(
            f"controlled-{name}".encode("ascii")
        ).hexdigest()
    package["impulse_orientation"]["evidence_hash"] = hashlib.sha256(
        b"controlled-verified-impulse-evidence"
    ).hexdigest()
    for stream_name, rows in package["streams"].items():
        template = copy.deepcopy(rows[0])
        expanded = []
        for index in range(count):
            row = copy.deepcopy(template)
            row.update(
                {
                    "server_tick": 100 + index,
                    "render_frame_idx": index,
                    "action_idx": index,
                    "model_frame_idx": index,
                }
            )
            if stream_name == "client_tick_log":
                row["client_tick"] = 200 + index
            elif stream_name == "seed_noise":
                row["noise_draw"] = index / 10
            expanded.append(row)
        package["streams"][stream_name] = expanded
    media_path.write_bytes(b"controlled bounded mp4 bytes")
    package["media"].update(
        {
            "path": media_path.name,
            "frame_count": count,
            "size_bytes": media_path.stat().st_size,
            "sha256": sha256_file(media_path),
        }
    )
    return package


def _preflight_case(root: Path, *, count: int = 3) -> dict:
    source_root = root / "MineWorld-Upstream"
    (source_root / "configs").mkdir(parents=True)
    (source_root / "configs" / "700M_16f.yaml").write_text(
        "controlled",
        encoding="utf-8",
    )
    asset_root = root / "MineWorld-Assets-Pinned"
    asset_paths = {
        "checkpoints/700M_16f.ckpt": (
            asset_root / "checkpoints" / "700M_16f.ckpt"
        ),
        "checkpoints/vae/config.json": (
            asset_root / "checkpoints" / "vae" / "config.json"
        ),
        "checkpoints/vae/vae.ckpt": (
            asset_root / "checkpoints" / "vae" / "vae.ckpt"
        ),
    }
    for path in asset_paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"controlled")
    evidence_root = root / "evidence"
    evidence_root.mkdir()
    input_mp4 = root / "accepted.mp4"
    package_path = root / "accepted.json"
    package = _expanded_package(count, input_mp4)
    package_path.write_bytes(canonical_json_bytes(package))
    environment = root / "environment.txt"
    environment.write_text(_environment_report(), encoding="utf-8")
    return {
        "root": root,
        "source_root": source_root,
        "asset_root": asset_root,
        "asset_paths": asset_paths,
        "evidence_root": evidence_root,
        "session_root": evidence_root / "phase3-preflight-test",
        "input_mp4": input_mp4,
        "package_path": package_path,
        "package": package,
        "environment": environment,
        "probe": {
            "width": 640,
            "height": 360,
            "r_frame_rate": "20/1",
            "avg_frame_rate": "20/1",
            "duration_seconds": count / 20,
            "declared_frames": count,
            "decoded_frames": count,
        },
    }


def _preflight_argv(case: dict, *, command: str = "preflight") -> list[str]:
    values = [
        command,
        "--mineworld-source-root",
        str(case["source_root"]),
        "--asset-root",
        str(case["asset_root"]),
        "--evidence-root",
        str(case["evidence_root"]),
        "--accepted-trajectory-package",
        str(case["package_path"]),
        "--input-mp4",
        str(case["input_mp4"]),
        "--environment-report",
        str(case["environment"]),
        "--session-id",
        "phase3-preflight-test",
        "--seed",
        "1",
        "--precision",
        "float16",
        "--device",
        "cuda:0",
        "--generated-frame-count",
        "1",
        "--mineocclude-revision",
        PREFLIGHT_GIT_SHA,
    ]
    if command == "run":
        values.append("--confirm-gpu-certification")
    return values


@contextlib.contextmanager
def _controlled_preflight_boundaries(case: dict, *, probe=None):
    original_import = phase3_certification.importlib.import_module

    def guarded_import(name):
        if name == "torch":
            raise AssertionError("torch must not be imported during preflight")
        return original_import(name)

    def git_stub(*arguments, root=REPO_ROOT):
        if arguments == ("rev-parse", "HEAD"):
            return (
                wave2.PINNED_SOURCE_REVISION
                if root == case["source_root"].resolve()
                else PREFLIGHT_GIT_SHA
            )
        if arguments == ("status", "--porcelain"):
            return ""
        raise AssertionError((arguments, root))

    with (
        mock.patch.object(
            phase3_certification,
            "_git",
            side_effect=git_stub,
        ),
        mock.patch.object(
            phase3_certification,
            "_verify_file",
            side_effect=lambda path, _expected, _role: Path(path).resolve(),
        ),
        mock.patch.object(
            phase3_certification,
            "_validate_asset_lock",
            return_value=case["asset_paths"],
        ),
        mock.patch.object(
            phase3_certification,
            "_probe_input_mp4",
            return_value=probe or case["probe"],
        ),
        mock.patch.object(
            phase3_certification.importlib,
            "import_module",
            side_effect=guarded_import,
        ),
        mock.patch.object(
            phase3_certification,
            "create_mineworld_adapter",
            side_effect=AssertionError("runtime adapter must not be created"),
        ),
        mock.patch.object(
            phase3_certification,
            "_adapter_code_identity",
            side_effect=AssertionError("runtime identity must not be computed"),
        ),
    ):
        yield


class _FakeRollout:
    def __init__(self, *, error: Exception | None = None):
        self.error = error
        self.calls = 0
        self.observed = []

    def __call__(self, runtime, context, request, source_root, output_video):
        self.calls += 1
        self.observed.append(
            {
                "runtime": runtime,
                "token_sha256": context.token_sha256,
                "seed": request.seed,
                "temperature": request.temperature,
                "top_k": request.top_k,
                "top_p": request.top_p,
                "actions": tuple(
                    action.token_ids for action in request.generation_actions
                ),
                "source_root": source_root,
                "output_video": output_video,
            }
        )
        if self.error is not None:
            raise self.error
        payload = (
            f"controlled-mp4:{request.seed}:"
            f"{request.generation_config_sha256}"
        ).encode("ascii")
        output_video.write_bytes(payload)
        tokens = tuple(
            index % 8192
            for index in range(
                request.generated_frame_count * wave2.PINNED_VISUAL_TOKENS
            )
        )
        return wave4._RolloutExecution(
            generated_token_ids=tokens,
            generated_token_sha256=hashlib.sha256(
                canonical_json_bytes(list(tokens))
            ).hexdigest(),
            generated_frame_count=request.generated_frame_count,
            elapsed_seconds=0.5,
            peak_cuda_allocated_bytes=100,
            peak_cuda_reserved_bytes=200,
            inference_mode_applied=True,
        )


def _probe(path: Path) -> wave4._VideoProbe:
    if not path.is_file():
        raise RuntimeError("missing controlled output")
    return wave4._VideoProbe(1, 384, 224, 6.0, 1 / 6)


def _runtime_identity(**changes):
    values = {
        "adapter_code_sha256": CODE_IDENTITY.sha256,
        "adapter_code_inventory": CODE_IDENTITY.inventory,
    }
    values.update(changes)
    return wave3_helpers._runtime_identity(**values)


def _seed_adapter(*, rollout=None, count=3, start=40):
    validated = dataclasses.replace(
        wave3_helpers._validated(count, start=start),
        adapter_code_sha256=CODE_IDENTITY.sha256,
        mineocclude_revision=wave3_helpers.GIT_SHA,
    )
    rollout = rollout or _FakeRollout()
    adapter = wave4._Wave4MineWorldAdapter(
        visual_tokenizer=wave3_helpers._VisualTokenizer(),
        teacher_executor=wave3_helpers._TeacherExecutor(),
        rollout_executor=rollout,
        video_probe=_probe,
        code_identity_provider=lambda: CODE_IDENTITY,
        repository_root=REPO_ROOT,
    )
    identity = _runtime_identity()
    runtime = wave3_helpers._seed_adapter(adapter, validated, identity)
    adapter._code_identity = CODE_IDENTITY
    request = wave3_helpers._request(validated)
    request = dataclasses.replace(
        request,
        runtime_identity=identity,
        frames=tuple(
            dataclasses.replace(
                frame,
                adapter_code_sha256=CODE_IDENTITY.sha256,
                mineocclude_revision=wave3_helpers.GIT_SHA,
            )
            for frame in request.frames
        ),
        actions=tuple(
            dataclasses.replace(
                action,
                adapter_code_sha256=CODE_IDENTITY.sha256,
                mineocclude_revision=wave3_helpers.GIT_SHA,
            )
            for action in request.actions
        ),
    )
    tokenized = adapter.tokenize_trajectory(request)
    return adapter, runtime, validated, tokenized, rollout


def _rollout_request(tokenized, output_directory, **changes):
    last = tokenized.included_frame_identities[-1]
    values = {
        "runtime_identity": tokenized.runtime_identity,
        "context": tokenized,
        "run_id": "phase3-wave4-controlled",
        "seed": 41,
        "generated_frame_count": 1,
        "output_directory": Path(output_directory),
        "generation_config_sha256": "0" * 64,
        "generation_actions": (
            dataclasses.replace(
                wave3_helpers._action(last),
                adapter_code_sha256=CODE_IDENTITY.sha256,
                mineocclude_revision=wave3_helpers.GIT_SHA,
            ),
        ),
        "temperature": 1.0,
        "top_k": 1,
        "top_p": None,
        "output_frame_rate": 6.0,
        "precision": "float16",
        "device": "cuda:0",
        "expected_adapter_code_sha256": CODE_IDENTITY.sha256,
        "accepted_manifest_sha256": tokenized.accepted_manifest_sha256,
    }
    values.update(changes)
    provisional = FreeRolloutRequest(**values)
    if "generation_config_sha256" not in changes:
        provisional = dataclasses.replace(
            provisional,
            generation_config_sha256=(
                wave4._rollout_generation_config_sha256(provisional)
            ),
        )
    return provisional


def _write_valid_certification_bundle(root: Path):
    code_identity = wave4._adapter_code_identity()
    runtime_identity = wave3_helpers._runtime_identity(
        runtime_id="phase3-certification-test-runtime",
        mineocclude_revision="a" * 40,
        environment_report_sha256="e" * 64,
        adapter_code_sha256=code_identity.sha256,
        adapter_code_inventory=code_identity.inventory,
    )
    package_path = root / "accepted.json"
    package_path.write_bytes(b"{}\n")
    media_path = root / "accepted.mp4"
    media_path.write_bytes(b"controlled-input-media")
    environment_path = root / "environment.txt"
    environment_path.write_bytes(b"controlled-environment")
    fixture = json.loads(
        phase3_certification._ACTION_FIXTURE.read_text(encoding="utf-8")
    )
    package_sha256 = sha256_file(package_path)
    media_sha256 = sha256_file(media_path)
    environment_sha256 = sha256_file(environment_path)
    runtime_identity = dataclasses.replace(
        runtime_identity,
        environment_report_sha256=environment_sha256,
    )
    runtime_path = root / "adapter_runtime_identity.json"
    runtime_path.write_bytes(
        canonical_json_bytes(
            {
                "schema_version": SCHEMA_VERSION,
                "certification_version": (
                    phase3_certification.CERTIFICATION_VERSION
                ),
                "status": "completed",
                "identity": dataclasses.asdict(runtime_identity),
                "model_load_seconds": 1.0,
            }
        )
    )
    sequence_length = 347
    hook_run = [
        {
            "module_name": f"transformer.model.layers.{index}",
            "layer_index": index,
            "shape": [1, sequence_length, 2048],
            "dtype": "torch.float16",
            "device": "cuda:0",
        }
        for index in range(20)
    ]
    teacher_path = root / "teacher_forced_certification.json"
    teacher_path.write_bytes(
        canonical_json_bytes(
            {
                "schema_version": SCHEMA_VERSION,
                "certification_version": (
                    phase3_certification.CERTIFICATION_VERSION
                ),
                "status": "completed",
                "operation": "teacher_forced",
                "runtime_identity": dataclasses.asdict(runtime_identity),
                "runtime_id": runtime_identity.runtime_id,
                "adapter_code_sha256": code_identity.sha256,
                "trajectory_id": "certification-trajectory",
                "accepted_manifest_sha256": package_sha256,
                "token_sha256": "1" * 64,
                "frame_token_map_sha256": "2" * 64,
                "repeat_count": 2,
                "precision": "float16",
                "device": "cuda:0",
                "batch_size": 1,
                "input_sequence_length": sequence_length,
                "included_frame_identities": [],
                "excluded_frame_identities": [],
                "repeat_output_sha256": ["3" * 64, "3" * 64],
                "repeatability_status": "PASS",
                "inference_mode_applied": True,
                "forward_seconds": [0.25, 0.25],
                "total_forward_seconds": 0.5,
                "hook_records": [hook_run, hook_run],
                "peak_cuda_allocated_bytes": 100,
                "peak_cuda_reserved_bytes": 200,
            }
        )
    )
    video_path = root / "rollout.mp4"
    video_path.write_bytes(b"controlled-video")
    video_sha256 = sha256_file(video_path)
    rollout_path = root / "rollout.json"
    rollout_path.write_bytes(
        canonical_json_bytes(
            {
                "schema_version": SCHEMA_VERSION,
                "adapter_api_version": MINEWORLD_ADAPTER_API_VERSION,
                "report_version": wave4.ROLLOUT_REPORT_VERSION,
                "status": "completed",
                "operation": "free_rollout",
                "identity": {
                    "runtime": dataclasses.asdict(runtime_identity),
                    "accepted_manifest_sha256": package_sha256,
                    "source_document_sha256": "4" * 64,
                    "trajectory_id": "certification-trajectory",
                    "token_sha256": "1" * 64,
                    "frame_token_map_sha256": "2" * 64,
                    "request_sha256": "5" * 64,
                },
                "request": {
                    "generated_frame_count": 1,
                    "precision": "float16",
                    "device": "cuda:0",
                    "output_frame_rate": 6.0,
                },
                "generation": {
                    "generated_frame_count": 1,
                    "generated_token_count": 336,
                    "generated_token_sha256": "6" * 64,
                    "inference_mode_applied": True,
                },
                "output": {
                    "path": str(video_path),
                    "size_bytes": video_path.stat().st_size,
                    "sha256": video_sha256,
                    "decoded_frames": 1,
                    "width": 384,
                    "height": 224,
                    "frame_rate": 6.0,
                    "duration_seconds": 1 / 6,
                },
                "runtime": {
                    "elapsed_seconds": 0.5,
                    "peak_cuda_allocated_bytes": 100,
                    "peak_cuda_reserved_bytes": 200,
                },
            }
        )
    )
    raw_path = root / "raw_stdout_stderr.log"
    raw_path.write_bytes(b"controlled-log")
    paths = {
        "runtime": runtime_path,
        "teacher_forced": teacher_path,
        "rollout": rollout_path,
        "rollout_video": video_path,
        "raw_log": raw_path,
    }
    reports = {
        role: {
            "path": path.relative_to(root).as_posix(),
            "sha256": sha256_file(path),
        }
        for role, path in paths.items()
    }
    summary_path = root / "certification_summary.json"
    summary = {
        "schema_version": SCHEMA_VERSION,
        "certification_version": phase3_certification.CERTIFICATION_VERSION,
        "status": "real_runtime_certified",
        "session_id": "phase3-certification-test",
        "mineocclude_revision": runtime_identity.mineocclude_revision,
        "runtime_id": runtime_identity.runtime_id,
        "adapter_code_sha256": code_identity.sha256,
        "source_revision": wave2.PINNED_SOURCE_REVISION,
        "asset_revision": wave2.PINNED_ASSET_REVISION,
        "checks": dict(phase3_certification._EXPECTED_CHECKS),
        "inputs": {
            "accepted_trajectory_package": {
                "path": str(package_path),
                "sha256": package_sha256,
            },
            "accepted_media": {
                "path": str(media_path),
                "sha256": media_sha256,
                "declared_sha256": media_sha256,
            },
            "environment_report": {
                "path": str(environment_path),
                "sha256": environment_sha256,
            },
            "action_fixture": {
                "classification": (
                    "committed_cpu_fixture_rechecked_on_gpu_host"
                ),
                "status": "PASS",
                "path": str(phase3_certification._ACTION_FIXTURE),
                "sha256": sha256_file(
                    phase3_certification._ACTION_FIXTURE
                ),
                "case_count": len(fixture["cases"]),
                "source_revision": wave2.PINNED_SOURCE_REVISION,
                "source_blob_sha256": wave2.MCDATASET_BLOB_SHA256,
                "converter_identity": wave2.ACTION_CONVERTER_IDENTITY,
            },
        },
        "reports": reports,
        "timings": {
            "action_fixture_seconds": 0.1,
            "model_load_seconds": 1.0,
            "frame_preprocessing_seconds": 0.1,
            "accepted_action_conversion_seconds": 0.1,
            "vae_tokenization_seconds": 0.1,
            "teacher_forward_seconds": [0.25, 0.25],
            "free_rollout_seconds": 0.5,
            "total_seconds": 2.5,
        },
        "large_outputs_outside_git": True,
        "command": [
            "run_phase3_adapter_certification.py",
            "run",
            "--mineocclude-revision",
            runtime_identity.mineocclude_revision,
        ],
        "environment": {
            "python_version": "3.10.20",
            "torch_version": "2.6.0+cu126",
            "cuda_version": "12.6",
            "device_name": "NVIDIA L4",
            "environment_report_sha256": environment_sha256,
        },
    }
    summary_path.write_bytes(canonical_json_bytes(summary))
    return summary_path, paths, summary


class Wave4RolloutTests(unittest.TestCase):
    def test_exact_request_reaches_separate_official_boundary_and_is_sealed(self):
        adapter, runtime, _validated, tokenized, rollout = _seed_adapter()
        with _temporary_directory() as root:
            request = _rollout_request(tokenized, Path(root) / "run")
            result = adapter.free_rollout(request)
            self.assertEqual(rollout.calls, 1)
            self.assertEqual(runtime.model.transformer.calls, 0)
            observed = rollout.observed[0]
            self.assertEqual(observed["seed"], 41)
            self.assertEqual(observed["temperature"], 1.0)
            self.assertEqual(observed["top_k"], 1)
            self.assertEqual(observed["actions"], (
                request.generation_actions[0].token_ids,
            ))
            self.assertEqual(
                observed["token_sha256"],
                tokenized.token_sha256,
            )
            self.assertEqual(result.generated_frame_count, 1)
            self.assertEqual(result.output_width, 384)
            self.assertEqual(result.output_height, 224)
            self.assertEqual(result.output_frame_rate, 6.0)
            self.assertEqual(result.video_sha256, sha256_file(result.video_path))
            self.assertEqual(
                result.metadata_sha256,
                sha256_file(result.metadata_path),
            )
            self.assertEqual(
                result.adapter_code_sha256,
                CODE_IDENTITY.sha256,
            )
            self.assertEqual(
                result.accepted_manifest_sha256,
                tokenized.accepted_manifest_sha256,
            )
            document = json.loads(result.metadata_path.read_text("utf-8"))
            self.assertEqual(document["status"], "completed")
            self.assertEqual(document["operation"], "free_rollout")
            self.assertEqual(
                document["identity"]["token_sha256"],
                tokenized.token_sha256,
            )
            self.assertEqual(
                document["output"]["storage_classification"],
                "runtime_only_outside_git",
            )
            self.assertNotIn("metadata_sha256", document)

    def test_deterministic_fake_rollouts_preserve_output_identity(self):
        first_adapter, _runtime, _validated, first_tokens, _executor = (
            _seed_adapter()
        )
        second_adapter, _runtime2, _validated2, second_tokens, _executor2 = (
            _seed_adapter()
        )
        with _temporary_directory() as root:
            first = first_adapter.free_rollout(
                _rollout_request(first_tokens, Path(root) / "first")
            )
            second = second_adapter.free_rollout(
                _rollout_request(second_tokens, Path(root) / "second")
            )
        self.assertEqual(first.video_sha256, second.video_sha256)
        self.assertEqual(first.generated_frame_ids, second.generated_frame_ids)
        self.assertEqual(
            first.generation_config_sha256,
            second.generation_config_sha256,
        )

    def test_generation_failure_is_actionable_and_durable(self):
        rollout = _FakeRollout(error=ValueError("controlled generation failure"))
        adapter, _runtime, _validated, tokenized, _rollout = _seed_adapter(
            rollout=rollout
        )
        with _temporary_directory() as root:
            output = Path(root) / "failed"
            with self.assertRaises(MineWorldAdapterError) as caught:
                adapter.free_rollout(_rollout_request(tokenized, output))
            failure = output / "phase3-wave4-controlled.failure.json"
            self.assertTrue(failure.is_file())
            document = json.loads(failure.read_text("utf-8"))
            self.assertEqual(document["status"], "failed")
            self.assertEqual(
                document["failure"]["code"],
                "runtime_execution_failed",
            )
            self.assertIn("controlled generation failure", str(caught.exception))

    def test_count_probe_collision_and_position_failures_close(self):
        cases = (
            (
                "wrong-execution-count",
                wave4._RolloutExecution(
                    tuple(range(336)),
                    hashlib.sha256(
                        canonical_json_bytes(list(range(336)))
                    ).hexdigest(),
                    2,
                    0.1,
                    0,
                    0,
                    True,
                ),
            ),
            (
                "not-inference-mode",
                wave4._RolloutExecution(
                    tuple(range(336)),
                    hashlib.sha256(
                        canonical_json_bytes(list(range(336)))
                    ).hexdigest(),
                    1,
                    0.1,
                    0,
                    0,
                    False,
                ),
            ),
        )
        for label, execution in cases:
            with self.subTest(label=label), _temporary_directory() as root:
                executor = mock.Mock(side_effect=lambda *args: (
                    args[-1].write_bytes(b"mp4"),
                    execution,
                )[1])
                adapter, _runtime, _validated, tokenized, _ = _seed_adapter(
                    rollout=executor
                )
                with self.assertRaises(MineWorldAdapterError):
                    adapter.free_rollout(
                        _rollout_request(tokenized, Path(root) / label)
                    )

        adapter, _runtime, _validated, tokenized, rollout = _seed_adapter(
            count=16
        )
        with _temporary_directory() as root:
            with self.assertRaises(MineWorldAdapterError) as caught:
                adapter.free_rollout(
                    _rollout_request(tokenized, Path(root) / "overflow")
                )
            self.assertIn("position_budget", str(caught.exception))
            self.assertEqual(rollout.calls, 0)

            collision_adapter, _r, _v, collision_tokens, collision_rollout = (
                _seed_adapter(count=3)
            )
            safe = _rollout_request(
                collision_tokens,
                Path(root) / "collision",
            )
            collision_adapter.free_rollout(safe)
            with self.assertRaises(MineWorldAdapterError):
                collision_adapter.free_rollout(safe)
            self.assertEqual(collision_rollout.calls, 1)

    def test_rollout_never_calls_teacher_forced(self):
        adapter, _runtime, _validated, tokenized, rollout = _seed_adapter()
        with _temporary_directory() as root:
            with mock.patch.object(
                adapter,
                "teacher_forced",
                side_effect=AssertionError("teacher forcing called"),
            ):
                adapter.free_rollout(
                    _rollout_request(tokenized, Path(root) / "run")
                )
        self.assertEqual(rollout.calls, 1)

    def test_sampling_action_and_probe_failures_precede_success(self):
        adapter, _runtime, _validated, tokenized, rollout = _seed_adapter()
        with _temporary_directory() as root:
            base = _rollout_request(tokenized, Path(root) / "base")
            with self.assertRaises(MineWorldAdapterError):
                dataclasses.replace(base, top_k=None, top_p=None)
            with self.assertRaises(MineWorldAdapterError):
                dataclasses.replace(base, top_k=1, top_p=0.5)

            missing_action = dataclasses.replace(
                base,
                generation_actions=(),
            )
            with self.assertRaises(MineWorldAdapterError):
                adapter.free_rollout(missing_action)
            wrong_action = dataclasses.replace(
                base.generation_actions[0],
                converter_identity="wrong",
            )
            wrong_request = dataclasses.replace(
                base,
                generation_actions=(wrong_action,),
            )
            with self.assertRaises(MineWorldAdapterError):
                adapter.free_rollout(wrong_request)
            self.assertEqual(rollout.calls, 0)

            bad_probe_adapter, _r, _v, bad_tokens, bad_rollout = _seed_adapter()
            bad_probe_adapter._video_probe = lambda _path: wave4._VideoProbe(
                0,
                384,
                224,
                6.0,
                0.0,
            )
            with self.assertRaises(MineWorldAdapterError):
                bad_probe_adapter.free_rollout(
                    _rollout_request(bad_tokens, Path(root) / "bad-probe")
                )
            self.assertEqual(bad_rollout.calls, 1)


class Wave4IdentityAndFailureTests(unittest.TestCase):
    def test_code_inventory_is_sorted_deterministic_and_byte_bound(self):
        with _temporary_directory() as root:
            root_path = Path(root)
            relative = ("z.py", "a.py", "nested/b.py")
            for index, name in enumerate(relative):
                path = root_path / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(f"payload-{index}".encode("ascii"))
            first = wave4._adapter_code_identity(
                root_path,
                relative_paths=relative,
            )
            second = wave4._adapter_code_identity(
                root_path,
                relative_paths=tuple(reversed(relative)),
            )
            self.assertEqual(first, second)
            self.assertEqual(
                tuple(row[0] for row in first.inventory),
                ("a.py", "nested/b.py", "z.py"),
            )
            (root_path / "a.py").write_bytes(b"changed")
            self.assertNotEqual(
                first.sha256,
                wave4._adapter_code_identity(
                    root_path,
                    relative_paths=relative,
                ).sha256,
            )

    def test_adapter_code_mismatch_rejects_before_runtime_loader(self):
        loader = mock.Mock(side_effect=AssertionError("loader called"))
        adapter = wave4._Wave4MineWorldAdapter(
            runtime_loader=loader,
            code_identity_provider=lambda: CODE_IDENTITY,
        )
        request = RuntimeLoadRequest(
            schema_version=SCHEMA_VERSION,
            runtime_id="wave4-code-mismatch",
            mineocclude_revision="a" * 40,
            mineworld_source_revision=wave2.PINNED_SOURCE_REVISION,
            modelscope_asset_revision=wave2.PINNED_ASSET_REVISION,
            mineworld_source_root=Path("missing-source"),
            model_config_path=Path("missing-config"),
            main_checkpoint_path=Path("missing-checkpoint"),
            vae_config_path=Path("missing-vae-config"),
            vae_checkpoint_path=Path("missing-vae-checkpoint"),
            model_config_sha256=wave2.PINNED_MODEL_CONFIG_SHA256,
            main_checkpoint_sha256=wave2.PINNED_MAIN_CHECKPOINT_SHA256,
            vae_config_sha256=wave2.PINNED_VAE_CONFIG_SHA256,
            vae_checkpoint_sha256=wave2.PINNED_VAE_CHECKPOINT_SHA256,
            environment_report_sha256=SHA256,
            precision="float16",
            device="cuda:0",
            expected_adapter_code_sha256="0" * 64,
        )
        with self.assertRaises(MineWorldAdapterError) as caught:
            adapter.load_runtime(request)
        self.assertIn("expected_adapter_code_sha256", str(caught.exception))
        self.assertEqual(loader.call_count, 0)
        self.assertIn(("expected", repr("0" * 64)), caught.exception.details)

    def test_rollout_mismatch_matrix_rejects_before_executor(self):
        fixture = json.loads(FAILURE_FIXTURE.read_text("utf-8"))
        self.assertEqual(len(fixture["cases"]), 18)
        adapter, _runtime, _validated, tokenized, rollout = _seed_adapter()
        with _temporary_directory() as root:
            base = _rollout_request(tokenized, Path(root) / "base")
            bad_context_profile = copy.copy(tokenized)
            object.__setattr__(
                bad_context_profile,
                "preprocessing_profile",
                "wrong",
            )
            bad_token_hash = copy.copy(tokenized)
            object.__setattr__(bad_token_hash, "token_sha256", "0" * 64)
            bad_map_hash = copy.copy(tokenized)
            object.__setattr__(
                bad_map_hash,
                "frame_token_map_sha256",
                "0" * 64,
            )
            wrong_runtime = copy.copy(tokenized.runtime_identity)
            object.__setattr__(wrong_runtime, "runtime_id", "wrong")
            wrong_runtime_request = copy.copy(base)
            object.__setattr__(
                wrong_runtime_request,
                "runtime_identity",
                wrong_runtime,
            )
            requests = {
                "adapter_code": dataclasses.replace(
                    base,
                    expected_adapter_code_sha256="0" * 64,
                ),
                "accepted_manifest": dataclasses.replace(
                    base,
                    accepted_manifest_sha256="0" * 64,
                ),
                "precision": dataclasses.replace(base, precision="bfloat16"),
                "device": dataclasses.replace(base, device="cpu"),
                "profile": dataclasses.replace(
                    base,
                    context=bad_context_profile,
                ),
                "token_hash": dataclasses.replace(
                    base,
                    context=bad_token_hash,
                ),
                "map_hash": dataclasses.replace(
                    base,
                    context=bad_map_hash,
                ),
                "runtime": wrong_runtime_request,
                "config": dataclasses.replace(
                    base,
                    generation_config_sha256="0" * 64,
                ),
            }
            for label, request in requests.items():
                with self.subTest(label=label):
                    before = rollout.calls
                    with self.assertRaises(MineWorldAdapterError):
                        adapter.free_rollout(request)
                    self.assertEqual(rollout.calls, before)

            unsafe = dataclasses.replace(
                base,
                output_directory=REPO_ROOT / "tracked-wave4-output",
            )
            with self.assertRaises(MineWorldAdapterError):
                adapter.free_rollout(unsafe)
            self.assertEqual(rollout.calls, 0)

    def test_teacher_result_references_complete_code_and_manifest_identity(self):
        adapter, _runtime, _validated, tokenized, _rollout = _seed_adapter()
        request = TeacherForcedRequest(
            runtime_identity=tokenized.runtime_identity,
            trajectory=tokenized,
            seed=7,
            precision="float16",
            expected_adapter_code_sha256=CODE_IDENTITY.sha256,
            accepted_manifest_sha256=tokenized.accepted_manifest_sha256,
        )
        result = adapter.teacher_forced(request)
        self.assertEqual(result.operation_type, "teacher_forced")
        self.assertEqual(result.adapter_code_sha256, CODE_IDENTITY.sha256)
        self.assertEqual(
            result.accepted_manifest_sha256,
            tokenized.accepted_manifest_sha256,
        )
        self.assertIsNotNone(result.request_sha256)
        self.assertIsNotNone(result.result_sha256)

        forged = dataclasses.replace(
            request,
            expected_adapter_code_sha256="0" * 64,
        )
        calls = adapter._teacher_executor.calls
        with self.assertRaises(MineWorldAdapterError):
            adapter.teacher_forced(forged)
        self.assertEqual(adapter._teacher_executor.calls, calls)

    def test_every_intermediate_output_carries_observed_code_identity(self):
        adapter, _runtime, _validated, _tokenized, _rollout = _seed_adapter()
        package = json.loads(
            (
                REPO_ROOT
                / "tests"
                / "fixtures"
                / "trajectory"
                / "accepted_package.json"
            ).read_text("utf-8")
        )
        validated = adapter.validate_trajectory(
            AcceptedTrajectoryInput(
                schema_version=SCHEMA_VERSION,
                trajectory_id=package["trajectory_id"],
                accepted_manifest_sha256=SHA256,
                document=package,
            )
        )
        first = validated.frame_identities[0]
        preprocessed = adapter.preprocess_frame(
            FramePreprocessRequest(
                identity=first,
                source_frame_idx=0,
                frame=np.zeros((360, 640, 3), dtype=np.uint8),
            )
        )

        class Converter:
            def convert(self, _raw_action):
                return {}, tuple(range(8192, 8203)), True

        adapter._converter = Converter()
        accepted = adapter._accepted_frames[first.key]
        converted = adapter.convert_action(
            ActionConversionRequest(
                identity=first,
                action_idx=accepted.action_idx,
                raw_action=accepted.raw_action,
            )
        )
        for record in (validated, preprocessed, converted):
            self.assertEqual(record.adapter_code_sha256, CODE_IDENTITY.sha256)
            self.assertEqual(
                record.mineocclude_revision,
                wave3_helpers.GIT_SHA,
            )

    def test_ownership_and_public_surface_remain_frozen(self):
        import mineocclude.models.mineworld_adapter as public

        self.assertEqual(len(public.__all__), 24)
        self.assertIsInstance(
            public.create_mineworld_adapter(),
            wave4._Wave4MineWorldAdapter,
        )
        source = inspect.getsource(wave4)
        for prohibited in (
            "mineocclude.activations.hooks",
            "mineocclude.activations.pool",
            "mineocclude.activations.store",
            "mineocclude.experiments.registry",
        ):
            self.assertNotIn(prohibited, source)
        self.assertNotIn("teacher_forced(", inspect.getsource(
            wave4._official_rollout_executor
        ))


class Wave4CertificationHarnessTests(unittest.TestCase):
    def test_cli_help_and_required_arguments_are_fail_closed(self):
        parser = phase3_certification.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args([])
        preflight_args = parser.parse_args(
            _preflight_argv(
                {
                    "source_root": Path("source"),
                    "asset_root": Path("assets"),
                    "evidence_root": Path("evidence"),
                    "package_path": Path("accepted.json"),
                    "input_mp4": Path("accepted.mp4"),
                    "environment": Path("environment.txt"),
                }
            )
        )
        self.assertEqual(preflight_args.command, "preflight")
        self.assertEqual(preflight_args.generated_frame_count, 1)
        args = parser.parse_args(
            [
                "validate",
                "--summary",
                "summary.json",
            ]
        )
        self.assertEqual(args.command, "validate")
        self.assertEqual(args.summary, Path("summary.json"))

    def test_invalid_seed_and_sampling_fail_before_git_or_runtime_work(self):
        base = [
            "run",
            "--mineworld-source-root",
            str(EXTERNAL_SOURCE),
            "--asset-root",
            "assets",
            "--evidence-root",
            "evidence",
            "--accepted-trajectory-package",
            "accepted.json",
            "--input-mp4",
            "input.mp4",
            "--environment-report",
            "environment.txt",
            "--session-id",
            "phase3-invalid",
            "--precision",
            "float16",
            "--device",
            "cuda:0",
            "--mineocclude-revision",
            "a" * 40,
            "--generated-frame-count",
            "1",
            "--dry-run",
        ]
        for extra in (
            ["--seed", str(0x100000000)],
            ["--seed", "1", "--top-k", "0"],
        ):
            with self.subTest(extra=extra):
                args = phase3_certification.build_parser().parse_args(
                    [*base, *extra]
                )
                with (
                    mock.patch.object(
                        phase3_certification,
                        "_git",
                        side_effect=AssertionError("git must not run"),
                    ),
                    self.assertRaises(EvidenceValidationError),
                ):
                    phase3_certification.execute_certification(args)

    def test_dry_run_never_imports_torch_or_loads_runtime(self):
        with _temporary_directory() as root:
            root_path = Path(root)
            case = _preflight_case(root_path)
            args = phase3_certification.build_parser().parse_args(
                [
                    *_preflight_argv(case, command="run"),
                    "--dry-run",
                ]
            )
            with (
                _controlled_preflight_boundaries(case),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                result = phase3_certification.execute_certification(args)
            self.assertEqual(result, case["session_root"])
            self.assertFalse(result.exists())

    def _assert_run_preflight_rejected(
        self,
        case,
        expected_code,
        *,
        probe=None,
        mutate_args=None,
    ):
        args = phase3_certification.build_parser().parse_args(
            _preflight_argv(case, command="run")
        )
        if mutate_args is not None:
            mutate_args(args)
        with _controlled_preflight_boundaries(case, probe=probe):
            with self.assertRaises(EvidenceValidationError) as raised:
                phase3_certification.execute_certification(args)
        self.assertEqual(raised.exception.code, expected_code)
        self.assertFalse(case["session_root"].exists())

    def test_real_preflight_passes_without_runtime_or_session_side_effects(self):
        with _temporary_directory() as root:
            case = _preflight_case(Path(root))
            args = phase3_certification.build_parser().parse_args(
                _preflight_argv(case)
            )
            with _controlled_preflight_boundaries(case):
                report = phase3_certification.execute_preflight(args)
            self.assertEqual(report["status"], "preflight_passed")
            self.assertEqual(report["context"]["complete_pairs"], 3)
            self.assertEqual(report["context"]["generated_frames"], 1)
            self.assertEqual(report["context"]["position_budget"], 1377)
            self.assertEqual(
                report["accepted_media"]["sha256"],
                case["package"]["media"]["sha256"],
            )
            self.assertFalse(report["session_directory_created"])
            self.assertFalse(report["torch_imported"])
            self.assertFalse(report["cuda_queried"])
            self.assertFalse(report["runtime_loaded"])
            self.assertFalse(case["session_root"].exists())

    def test_preflight_cli_emits_machine_readable_cpu_only_report(self):
        with _temporary_directory() as root:
            case = _preflight_case(Path(root))
            output = io.StringIO()
            with (
                _controlled_preflight_boundaries(case),
                contextlib.redirect_stdout(output),
            ):
                result = phase3_certification.main(_preflight_argv(case))
            self.assertEqual(result, 0)
            report = json.loads(output.getvalue())
            self.assertEqual(report["status"], "preflight_passed")
            self.assertFalse(report["session_directory_created"])
            self.assertFalse(case["session_root"].exists())

    def test_media_corruption_matrix_fails_before_runtime(self):
        cases = (
            (
                "wrong_hash",
                lambda case: case["package"]["media"].__setitem__(
                    "sha256", "f" * 64
                ),
                None,
                "accepted_media_hash_mismatch",
            ),
            (
                "wrong_size",
                lambda case: case["package"]["media"].__setitem__(
                    "size_bytes",
                    case["package"]["media"]["size_bytes"] + 1,
                ),
                None,
                "accepted_media_size_mismatch",
            ),
            (
                "cardinality",
                lambda _case: None,
                {"declared_frames": 2, "decoded_frames": 2},
                "accepted_media_metadata_mismatch",
            ),
            (
                "dimensions",
                lambda _case: None,
                {"width": 320},
                "accepted_media_metadata_mismatch",
            ),
            (
                "frame_rate",
                lambda _case: None,
                {"r_frame_rate": "10/1", "avg_frame_rate": "10/1"},
                "accepted_media_metadata_mismatch",
            ),
        )
        for name, mutate, probe_changes, expected_code in cases:
            with self.subTest(name=name), _temporary_directory() as root:
                case = _preflight_case(Path(root))
                mutate(case)
                case["package_path"].write_bytes(
                    canonical_json_bytes(case["package"])
                )
                probe = dict(case["probe"])
                if probe_changes:
                    probe.update(probe_changes)
                self._assert_run_preflight_rejected(
                    case,
                    expected_code,
                    probe=probe,
                )

    def test_package_rejection_matrix_fails_before_runtime(self):
        def duplicate_identity(case):
            case["package"]["streams"]["frame_map"][1].update(
                case["package"]["streams"]["frame_map"][0]
            )

        def missing_final_action(case):
            case["package"]["streams"]["raw_actions"].pop()

        def missing_orientation(case):
            case["package"]["impulse_orientation"]["status"] = "unverified"

        def missing_producer_fields(case):
            del case["package"]["streams"]["visibility"]

        def wrong_schema(case):
            case["package"]["schema_version"] = "2.0"

        cases = (
            ("frozen_rejection", 3, duplicate_identity),
            ("missing_final_action", 3, missing_final_action),
            ("missing_orientation", 3, missing_orientation),
            ("missing_producer_fields", 3, missing_producer_fields),
            ("wrong_schema", 3, wrong_schema),
        )
        for name, count, mutate in cases:
            with self.subTest(name=name), _temporary_directory() as root:
                case = _preflight_case(Path(root), count=count)
                mutate(case)
                case["package_path"].write_bytes(
                    canonical_json_bytes(case["package"])
                )
                self._assert_run_preflight_rejected(
                    case,
                    "trajectory_package_rejected",
                )

        with self.subTest(name="malformed_json"), _temporary_directory() as root:
            case = _preflight_case(Path(root))
            case["package_path"].write_text("{", encoding="utf-8")
            self._assert_run_preflight_rejected(
                case,
                "invalid_json_input",
            )

        with self.subTest(name="too_many_pairs"), _temporary_directory() as root:
            case = _preflight_case(Path(root), count=16)
            self._assert_run_preflight_rejected(
                case,
                "certification_context_too_long",
            )

        with (
            self.subTest(name="placeholder_producer_evidence"),
            _temporary_directory() as root,
        ):
            case = _preflight_case(Path(root))
            case["package"]["artifacts"]["config"]["sha256"] = "b" * 64
            case["package_path"].write_bytes(
                canonical_json_bytes(case["package"])
            )
            self._assert_run_preflight_rejected(
                case,
                "acceptance_evidence_placeholder",
            )

    def test_argument_and_environment_matrix_fails_before_runtime(self):
        cases = (
            (
                "placeholder_revision",
                lambda args, _case: setattr(
                    args, "mineocclude_revision", "a" * 40
                ),
                "mineocclude_revision_mismatch",
            ),
            (
                "unsupported_precision",
                lambda args, _case: setattr(args, "precision", "float32"),
                "runtime_identity_mismatch",
            ),
            (
                "unsupported_device",
                lambda args, _case: setattr(args, "device", "cpu"),
                "runtime_identity_mismatch",
            ),
            (
                "unsafe_session",
                lambda args, _case: setattr(args, "session_id", "../unsafe"),
                "invalid_session_id",
            ),
            (
                "missing_environment",
                lambda _args, case: case["environment"].unlink(),
                "missing_input",
            ),
            (
                "empty_environment",
                lambda _args, case: case["environment"].write_text(
                    "",
                    encoding="utf-8",
                ),
                "environment_report_invalid",
            ),
            (
                "placeholder_environment",
                lambda _args, case: case["environment"].write_text(
                    "<placeholder>",
                    encoding="utf-8",
                ),
                "environment_report_invalid",
            ),
            (
                "wrong_generated_count",
                lambda args, _case: setattr(args, "generated_frame_count", 2),
                "invalid_generated_frame_count",
            ),
        )
        for name, mutate, expected_code in cases:
            with self.subTest(name=name), _temporary_directory() as root:
                case = _preflight_case(Path(root))
                self._assert_run_preflight_rejected(
                    case,
                    expected_code,
                    mutate_args=lambda args, mutate=mutate, case=case: mutate(
                        args, case
                    ),
                )

    def test_summary_validator_checks_bounded_report_set_and_hashes(self):
        with _temporary_directory() as root:
            root_path = Path(root)
            summary, paths, _document = _write_valid_certification_bundle(
                root_path
            )
            phase3_certification.validate_certification_summary(
                summary,
                verify_files=True,
            )
            paths["runtime"].write_bytes(b"tampered")
            with self.assertRaises(EvidenceValidationError):
                phase3_certification.validate_certification_summary(
                    summary,
                    verify_files=True,
                )

    def test_semantic_validator_rejects_rehashed_incomplete_evidence(self):
        with _temporary_directory() as root:
            root_path = Path(root)
            summary_path, paths, summary = _write_valid_certification_bundle(
                root_path
            )
            teacher = json.loads(
                paths["teacher_forced"].read_text(encoding="utf-8")
            )
            teacher["hook_records"][0][0]["shape"] = [1, 347, 1024]
            paths["teacher_forced"].write_bytes(canonical_json_bytes(teacher))
            summary["reports"]["teacher_forced"]["sha256"] = sha256_file(
                paths["teacher_forced"]
            )
            summary_path.write_bytes(canonical_json_bytes(summary))
            with self.assertRaises(EvidenceValidationError):
                phase3_certification.validate_certification_summary(
                    summary_path,
                    verify_files=True,
                )

    def test_small_report_export_validates_without_rollout_video_bytes(self):
        with _temporary_directory() as root:
            root_path = Path(root)
            original = root_path / "original"
            original.mkdir()
            summary_path, paths, _summary = (
                _write_valid_certification_bundle(original)
            )
            exported = root_path / "exported-small-evidence"
            exported.mkdir()
            for path in (
                summary_path,
                paths["runtime"],
                paths["teacher_forced"],
                paths["rollout"],
                paths["raw_log"],
            ):
                shutil.copy2(path, exported / path.name)
            paths["rollout_video"].unlink()
            phase3_certification.validate_certification_summary(
                exported / summary_path.name,
                verify_files=False,
            )

    def test_validator_requires_exact_check_set_and_timing_evidence(self):
        with _temporary_directory() as root:
            root_path = Path(root)
            summary_path, _paths, summary = _write_valid_certification_bundle(
                root_path
            )
            summary["checks"].pop("real_vae_336_tokens")
            summary_path.write_bytes(canonical_json_bytes(summary))
            with self.assertRaises(EvidenceValidationError):
                phase3_certification.validate_certification_summary(
                    summary_path,
                    verify_files=True,
                )

    @unittest.skipUnless(
        EXTERNAL_SOURCE.is_dir(),
        "Pinned MineWorld source required for action fixture parity",
    )
    def test_certification_rechecks_committed_action_fixture(self):
        evidence = phase3_certification._certify_action_fixture(
            EXTERNAL_SOURCE
        )
        self.assertEqual(evidence["status"], "PASS")
        fixture = json.loads(
            phase3_certification._ACTION_FIXTURE.read_text(encoding="utf-8")
        )
        self.assertEqual(evidence["case_count"], len(fixture["cases"]))
        self.assertEqual(
            evidence["sha256"],
            sha256_file(phase3_certification._ACTION_FIXTURE),
        )

    @unittest.skipUnless(
        EXTERNAL_SOURCE.is_dir(),
        "Pinned MineWorld source required for direct Wave 4 parity",
    )
    def test_direct_pinned_source_generation_parity(self):
        revision = subprocess.run(
            ["git", "-C", str(EXTERNAL_SOURCE), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(EXTERNAL_SOURCE), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        tracked_changes = [
            line
            for line in status.splitlines()
            if line.strip()
            and not wave2._is_generated_cache_status(line)
        ]
        self.assertEqual(revision, wave2.PINNED_SOURCE_REVISION)
        self.assertEqual(tracked_changes, [])
        inference_source = (EXTERNAL_SOURCE / "inference.py").read_text("utf-8")
        lvm_source = (EXTERNAL_SOURCE / "lvm.py").read_text("utf-8")
        self.assertIn("model.transformer.naive_generate(", inference_source)
        self.assertIn("action_all=action_all", inference_source)
        self.assertIn("token2video(", inference_source)
        self.assertIn(
            "def naive_generate(self, input_ids, max_new_tokens",
            lvm_source,
        )
        adapter_source = inspect.getsource(wave4._official_rollout_executor)
        self.assertIn("transformer.naive_generate(", adapter_source)
        self.assertIn("upstream_inference.token2video(", adapter_source)
        self.assertIn("action_all=action_all", adapter_source)
