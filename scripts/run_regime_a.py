#!/usr/bin/env python3
"""Fail-closed Regime-A A4 collection and activation runner."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.regime_a import (  # noqa: E402
    AtomicTrajectoryStore,
    COMPLETE_STATE,
    HashChainLedger,
    RegimeAError,
    assign_stable_hidden_tau,
    project_world_to_coordinates,
    sha256_file,
    validate_a4_authorization,
    validate_scientific_specs,
)
from mineocclude.regime_a_execution import (  # noqa: E402
    A4ExecutionRunner,
    S3DurableStore,
)


STATUS = ROOT / "docs/status/integration/regime_a_occlusion_extraction_v0_1"
BRANCH = "exploration/regime-a-occlusion-extraction-v0-1"
CHECKPOINT_SHA256 = "a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5"
SCIENTIFIC_RUN_ID = "mineocclude-regime-a-first25-v1"
SERVER_ROOT = Path("/home/sagemaker-user/mineocclude-server")
CLIENT_ROOT = Path("/home/sagemaker-user/mineocclude-client")


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def validate_manifest(path: Path, expected_sidecar: Path) -> tuple[list[dict[str, object]], str]:
    digest = sha256_file(path)
    if expected_sidecar.read_text(encoding="utf-8").strip() != digest:
        raise RegimeAError("trajectory manifest sidecar mismatch")
    rows = read_jsonl(path)
    validate_scientific_specs(rows)
    return rows, digest


def frozen_plan(rows: list[dict[str, object]], ledger: HashChainLedger) -> list[dict[str, object]]:
    complete = ledger.complete_ids()
    return [row for row in rows if str(row["trajectory_spec_id"]) not in complete]


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def authorization_bindings() -> dict[str, str]:
    if _git("branch", "--show-current") != BRANCH:
        raise RegimeAError("A4 branch mismatch")
    if _git("status", "--porcelain"):
        raise RegimeAError("A4 governed worktree must be clean")
    return {
        "final_reviewed_regime_a_commit_sha": _git("rev-parse", "HEAD"),
        "branch": BRANCH,
        "pre_a4_canonical_authority_sha256": sha256_file(STATUS / "pre_a4_canonical_authority.json"),
        "a2_implementation_test_receipt_sha256": sha256_file(STATUS / "implementation_test_receipt.json"),
        "a3_validation_receipt_sha256": sha256_file(STATUS / "a3_validation_receipt.json"),
        "a2_execution_runner_supersession_receipt_sha256": sha256_file(STATUS / "a2_execution_runner_supersession_receipt.json"),
        "pre_a4_source_freeze_receipt_v2_sha256": sha256_file(STATUS / "pre_a4_source_freeze_receipt_v2.json"),
        "a4_launch_recovery_source_freeze_receipt_sha256": sha256_file(STATUS / "a4_launch_recovery_source_freeze_receipt.json"),
        "a4_launch_storage_recovery_source_freeze_receipt_sha256": sha256_file(STATUS / "a4_launch_storage_recovery_source_freeze_receipt.json"),
        "a4_display_tool_recovery_source_freeze_receipt_sha256": sha256_file(STATUS / "a4_display_tool_recovery_source_freeze_receipt.json"),
        "a4_java_launcher_guard_supersession_receipt_sha256": sha256_file(STATUS / "a4_java_launcher_guard_supersession_receipt.json"),
        "a4_client_focus_precheck_supersession_receipt_sha256": sha256_file(STATUS / "a4_client_focus_precheck_supersession_receipt.json"),
        "a4_magenta_adapter_supersession_receipt_sha256": sha256_file(STATUS / "a4_magenta_adapter_supersession_receipt.json"),
        "checkpoint_sha256": CHECKPOINT_SHA256,
        "scientific_run_id": SCIENTIFIC_RUN_ID,
        "authorization_scope": "launch the exact frozen 25-spec Regime-A A4 collection only",
    }


def authorize_or_fail(authority_path: Path | None, manifest_hash: str, study_hash: str) -> None:
    if authority_path is None or not authority_path.is_file():
        raise RegimeAError("A4 execution is sealed: separate operator authorization is absent")
    validate_a4_authorization(
        json.loads(authority_path.read_text()),
        manifest_hash,
        study_hash,
        expected_bindings=authorization_bindings(),
    )


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")


def detector_rgb_rows(
    path: Path, *, expected_size: tuple[int, int] | None = None
) -> list[list[tuple[int, int, int]]]:
    """Decode one RGB PNG into the detector's nested Sequence contract."""

    with Image.open(path) as image:
        image.load()
        if image.mode != "RGB":
            raise RegimeAError(f"detector frame must be RGB, not {image.mode}")
        if expected_size is not None and image.size != expected_size:
            raise RegimeAError(
                f"detector frame is {image.size[0]}x{image.size[1]}, not "
                f"{expected_size[0]}x{expected_size[1]}"
            )
        width, height = image.size
        pixels = list(image.getdata())
    if len(pixels) != width * height or any(
        not isinstance(pixel, tuple)
        or len(pixel) != 3
        or any(not isinstance(channel, int) or isinstance(channel, bool) for channel in pixel)
        for pixel in pixels
    ):
        raise RegimeAError("detector RGB decode did not yield exact integer RGB pixels")
    return [pixels[offset : offset + width] for offset in range(0, len(pixels), width)]


class ProductionCaptureWorker:
    """Thin wall-present adapter over the validated live capture runtime."""

    def __init__(self, runtime_root: Path):
        from scripts import run_large_scale_no_wall_campaign as live

        java_home = Path(os.environ.get("JAVA_HOME", ""))
        java_path = java_home / "bin/java"
        if not java_home.is_absolute() or not java_path.is_file():
            raise RegimeAError("JAVA_HOME must identify the qualified A4 JDK")
        server_root = Path(os.environ.get("MINEOCCLUDE_SERVER_ROOT", str(SERVER_ROOT))).resolve()
        client_root = Path(os.environ.get("MINEOCCLUDE_CLIENT_ROOT", str(CLIENT_ROOT))).resolve()
        if not server_root.is_dir() or not client_root.is_dir():
            raise RegimeAError("qualified capture runtime roots must already exist")
        live.JAVA_PATH = java_path
        live.SERVER_ROOT = server_root
        live.CLIENT_ROOT = client_root
        live.FIFO = server_root / "cmd.fifo"
        self.live = live
        self.java_home = java_home
        self.server_root = server_root
        self.client_root = client_root
        self.runtime_root = runtime_root
        self.processes: list[object] = []
        self.runtime = None

    def _capture_context(self, spec: dict[str, object]) -> dict[str, object]:
        from mineocclude.data.noise_schedule import generate_noise_schedule, serialize_schedule

        episode_id = int(spec["episode_id"])
        frames = int(spec["expected_max_frames"])
        schedule = generate_noise_schedule(
            int(spec["noise_seed"]), frames, float(spec["motion_noise_q"])
        )
        noise_values = np.asarray([row.noise_draw for row in schedule.rows], dtype="<f8")
        if hashlib.sha256(noise_values.tobytes()).hexdigest() != spec["noise_schedule_sha256"]:
            raise RegimeAError("frozen raw noise schedule hash mismatch")
        signed_speed = float(spec["speed_blocks_per_second"]) * (
            1 if spec["direction"] == "LEFT_TO_RIGHT" else -1
        )
        motion_document = {
            "schedule_format_version": "mineocclude-motion-schedule-v0.1",
            "trajectory_spec_id": spec["trajectory_spec_id"],
            "spec_hash": spec["spec_hash"],
            "expected_ticks": frames,
            "segments": [{
                "start_model_frame_idx": 0,
                "stop_model_frame_idx_exclusive": frames,
                "signed_speed_blocks_per_second": signed_speed,
            }],
        }
        return {
            "episode_id": episode_id,
            "frames": frames,
            "server_episode": self.server_root / f"mineocclude_out/episode_{episode_id}",
            "client_episode": self.client_root / f"mineocclude_client_out/episode_{episode_id}",
            "noise_path": self.server_root / f"mineocclude_schedules/episode_{episode_id}.jsonl",
            "motion_path": self.server_root / f"mineocclude_motion_schedules/episode_{episode_id}.json",
            "noise_bytes": serialize_schedule(schedule),
            "motion_bytes": (json.dumps(motion_document, sort_keys=True) + "\n").encode(),
            "schedule": schedule,
            "signed_speed": signed_speed,
        }

    def _validate_and_package(
        self, spec: dict[str, object], partial: Path, context: dict[str, object]
    ) -> None:
        from mineocclude.data.build_dataset import process_episode
        from mineocclude.data.package_episode import package_and_validate
        from mineocclude.vision.magenta import HsvRange, detect_magenta

        frames = int(context["frames"])
        server_episode = Path(context["server_episode"])
        client_episode = Path(context["client_episode"])
        noise_path = Path(context["noise_path"])
        motion_path = Path(context["motion_path"])
        schedule = context["schedule"]
        signed_speed = float(context["signed_speed"])
        raw = partial / "raw"
        state = read_jsonl(raw / "server_state.jsonl")
        ticks = read_jsonl(raw / "client_tick.jsonl")
        actions = read_jsonl(raw / "actions.jsonl")
        if not (len(state) == len(ticks) == len(actions) == frames):
            raise RegimeAError("capture stream cardinality mismatch")
        uuids = {row.get("target_entity_uuid") for row in state}
        expected_position = float(spec["start_world_x"])
        for index, row in enumerate(state):
            expected_position = min(
                8.0,
                max(
                    -8.0,
                    expected_position
                    + signed_speed * 0.05
                    + float(schedule.rows[index].noise_draw),
                ),
            )
            if (
                row.get("server_tick") != index
                or row.get("trajectory_spec_id") != spec["trajectory_spec_id"]
                or row.get("spec_hash") != spec["spec_hash"]
                or row.get("seed") != spec["seed"]
                or row.get("scene") != "NORMAL"
                or row.get("target_respawn_count") != 0
                or not np.isclose(
                    float(row["sheep_x"]), expected_position, atol=1e-9, rtol=0
                )
            ):
                raise RegimeAError(f"server state mismatch at frame {index}")
            if (
                ticks[index].get("server_tick") != index
                or actions[index].get("server_tick") != index
            ):
                raise RegimeAError("client/server frame alignment mismatch")
        if len(uuids) != 1 or None in uuids:
            raise RegimeAError("target entity UUID was not retained")

        config = json.loads(
            (
                ROOT
                / "docs/status/person_e_phase3_step3_1_candidate_freeze_v0_1/detector_candidate_config.json"
            ).read_text()
        )["configuration"]["detector_settings"]
        thresholds = tuple(HsvRange(*values) for values in config["hsv_ranges"])
        visibility = []
        frame_map = []
        homography = json.loads(
            (
                ROOT
                / "data/handoff_e/person_e_v0_4_homography_refit_v0_2/layout_01_homography.json"
            ).read_text()
        )
        coordinates = []
        for index, row in enumerate(state):
            result = detect_magenta(
                detector_rgb_rows(
                    raw / f"frames/{index:06d}.png", expected_size=(640, 360)
                ),
                hsv_ranges=thresholds,
                min_area_pixels=config["min_area_pixels"],
                max_area_pixels=config["max_area_pixels"],
                open_iterations=config["open_iterations"],
                close_iterations=config["close_iterations"],
                morphology_radius_pixels=config["morphology_radius_pixels"],
                connectivity=config["connectivity"],
            )
            key = {
                "trajectory_id": spec["trajectory_spec_id"],
                "model_frame_idx": index,
                "server_tick": index,
                "render_frame_idx": index,
                "action_idx": index,
            }
            visibility.append({
                **key,
                "geometric_status": "visible" if row["geometric_visible"] else "occluded",
                "magenta_status": result.status,
                "magenta_area_pixels": result.area_pixels,
            })
            frame_map.append({
                **key,
                "target_entity_uuid": next(iter(uuids)),
                "frame_path": f"raw/frames/{index:06d}.png",
            })
            coordinates.append({
                **key,
                **project_world_to_coordinates(
                    float(row["sheep_x"]),
                    float(row["sheep_z"]),
                    homography["inverse_matrix"],
                ),
            })
        visibility = assign_stable_hidden_tau(visibility, str(spec["direction"]))
        targets = [
            int(row["model_frame_idx"])
            for row in visibility
            if row["tau"] in range(1, 20)
        ]
        expected_targets = list(
            range(
                int(spec["expected_stable_hidden_onset_frame"]),
                int(spec["expected_stable_hidden_onset_frame"]) + 19,
            )
        )
        if targets != expected_targets:
            raise RegimeAError("observed stable-hidden targets differ from frozen targets")
        _write_jsonl(raw / "visibility.jsonl", visibility)
        _write_jsonl(raw / "frame_map.jsonl", frame_map)
        _write_jsonl(partial / "coordinates.jsonl", coordinates)

        processed = partial / "capture_validation"
        summary = process_episode(
            str(server_episode),
            str(client_episode),
            str(processed),
            run_empirical=True,
            canonical_640=True,
        )
        if not summary.get("accepted") or summary.get("n_frames") != frames:
            raise RegimeAError(
                f"validated capture adapter refused trajectory: {summary.get('problems')}"
            )
        _package, result = package_and_validate(
            str(processed),
            str(server_episode),
            str(client_episode),
            str(noise_path),
            str(ROOT),
            SCIENTIFIC_RUN_ID,
        )
        if not result.accepted:
            raise RegimeAError("frozen capture-package validator refused trajectory")
        shutil.copy2(
            processed / "capture_package_v0_1.json",
            partial / "capture_package_v0_1.json",
        )
        shutil.copy2(noise_path, partial / "noise_schedule.jsonl")
        shutil.copy2(motion_path, partial / "motion_schedule.json")

    def resume_capture(self, spec: dict[str, object], partial: Path) -> bool:
        """Resume only an exact, complete raw capture at post-capture validation."""

        context = self._capture_context(spec)
        raw = partial / "raw"
        if not raw.exists():
            return False
        frames = int(context["frames"])
        expected_partial_files = {"partial_identity.json"}
        expected_partial_files.update(
            {
                "raw/server_state.jsonl",
                "raw/client_tick.jsonl",
                "raw/actions.jsonl",
                *(f"raw/frames/{index:06d}.png" for index in range(frames)),
            }
        )
        observed_partial_files = {
            path.relative_to(partial).as_posix()
            for path in partial.rglob("*")
            if path.is_file()
        }
        if observed_partial_files != expected_partial_files:
            raise RegimeAError("raw partial inventory is incomplete or beyond the resumable boundary")

        server_episode = Path(context["server_episode"])
        client_episode = Path(context["client_episode"])
        reset_path = server_episode / "reset_result.json"
        complete_path = client_episode / "capture_complete.json"
        if not reset_path.is_file() or not complete_path.is_file():
            raise RegimeAError("reusable raw capture lacks runtime completion receipts")
        reset = json.loads(reset_path.read_text(encoding="utf-8"))
        if (
            reset.get("episode_id") != context["episode_id"]
            or reset.get("trajectory_spec_id") != spec["trajectory_spec_id"]
            or reset.get("spec_hash") != spec["spec_hash"]
            or reset.get("seed") != spec["seed"]
        ):
            raise RegimeAError("reusable raw capture runtime identity mismatch")
        complete = json.loads(complete_path.read_text(encoding="utf-8"))
        if (
            complete.get("episode_id") != context["episode_id"]
            or complete.get("frame_count") != frames
            or complete.get("final_render_frame_idx") != frames - 1
            or complete.get("pending_writes") != 0
            or complete.get("writer_errors") != 0
            or complete.get("drained") is not True
        ):
            raise RegimeAError("reusable raw capture is not completely drained")
        noise_path = Path(context["noise_path"])
        motion_path = Path(context["motion_path"])
        if (
            not noise_path.is_file()
            or noise_path.read_bytes() != context["noise_bytes"]
            or not motion_path.is_file()
            or motion_path.read_bytes() != context["motion_bytes"]
        ):
            raise RegimeAError("reusable raw capture schedule bytes mismatch")
        source_pairs = [
            (raw / "server_state.jsonl", server_episode / "server_state.jsonl"),
            (raw / "client_tick.jsonl", client_episode / "client_tick.jsonl"),
            (raw / "actions.jsonl", client_episode / "raw_actions.jsonl"),
        ]
        source_pairs.extend(
            (
                raw / f"frames/{index:06d}.png",
                client_episode / f"frames/{index:06d}.png",
            )
            for index in range(frames)
        )
        if any(
            not source.is_file()
            or sha256_file(copied) != sha256_file(source)
            for copied, source in source_pairs
        ):
            raise RegimeAError("reusable raw capture differs from runtime source bytes")
        self._validate_and_package(spec, partial, context)
        return True

    def _ensure_started(self) -> None:
        if self.runtime is not None:
            return
        jar = ROOT / "fabric/mineocclude-mod/build/libs/mineocclude-0.1.1.jar"
        subprocess.run(
            [str(ROOT / "fabric/mineocclude-mod/gradlew"), "-p", str(ROOT / "fabric/mineocclude-mod"), "build", "--no-daemon"],
            check=True,
            timeout=600,
            env={**os.environ, "JAVA_HOME": str(self.java_home)},
        )
        if not jar.is_file():
            raise RegimeAError("governed Fabric mod build did not produce the runtime JAR")
        destination = self.server_root / "mods/mineocclude-0.1.1.jar"
        shutil.copy2(jar, destination)
        if sha256_file(jar) != sha256_file(destination):
            raise RegimeAError("governed Fabric server mod installation mismatch")
        self.processes, _elapsed = self.live.launch_runtime(self.runtime_root)
        self.runtime = self.live.LiveRuntime()
        self.runtime.precheck()

    def capture(self, spec: dict[str, object], partial: Path) -> None:
        context = self._capture_context(spec)
        self._ensure_started()
        assert self.runtime is not None
        episode_id = int(context["episode_id"])
        frames = int(context["frames"])
        server_episode = Path(context["server_episode"])
        client_episode = Path(context["client_episode"])
        if server_episode.exists() or client_episode.exists():
            reset = server_episode / "reset_result.json"
            if not reset.is_file():
                raise RegimeAError(
                    "existing runtime episode lacks a same-spec identity receipt"
                )
            identity = json.loads(reset.read_text(encoding="utf-8"))
            if (
                identity.get("episode_id") != episode_id
                or identity.get("trajectory_spec_id") != spec["trajectory_spec_id"]
                or identity.get("spec_hash") != spec["spec_hash"]
            ):
                raise RegimeAError("existing runtime episode belongs to another spec")
            shutil.rmtree(server_episode)
            if client_episode.exists():
                shutil.rmtree(client_episode)

        noise_path = Path(context["noise_path"])
        motion_path = Path(context["motion_path"])
        noise_path.parent.mkdir(parents=True, exist_ok=True)
        motion_path.parent.mkdir(parents=True, exist_ok=True)
        noise_path.write_bytes(context["noise_bytes"])
        motion_path.write_bytes(context["motion_bytes"])
        offset = len(self.runtime.log_text())
        self.runtime.send([
            "mineocclude mode normal",
            "mineocclude duration 0",
            "mineocclude reveal 0",
            "mineocclude warmup 60",
            "mineocclude impulse -1 0",
            "mineocclude pairshift 0",
            "mineocclude lockcam on",
            (
                f"mineocclude startspec layout_01 {episode_id} {spec['seed']} "
                f"{spec['motion_noise_q']} {frames} {spec['start_world_x']} "
                f"{spec['trajectory_spec_id']} {spec['spec_hash']}"
            ),
        ])
        self.runtime.wait_log(rf"episode {episode_id} armed", 30, offset)
        self.runtime.wait_log(rf"episode {episode_id} recording started", 30, offset)
        self.runtime.wait_log(rf"episode {episode_id} ended after {frames} ticks", 30, offset)
        self.runtime.wait_file(client_episode / "capture_complete.json", 15)

        raw = partial / "raw"
        shutil.copytree(client_episode / "frames", raw / "frames")
        shutil.copy2(server_episode / "server_state.jsonl", raw / "server_state.jsonl")
        shutil.copy2(client_episode / "client_tick.jsonl", raw / "client_tick.jsonl")
        shutil.copy2(client_episode / "raw_actions.jsonl", raw / "actions.jsonl")
        self._validate_and_package(spec, partial, context)
    def close(self) -> None:
        if self.processes:
            self.live.stop_runtime(self.processes)
        self.processes = []
        self.runtime = None


class PersistentMineWorldWorker:
    """One checkpoint load, independent teacher-forced window calls."""

    def __init__(self):
        self.load_count = 0

    def extract(self, spec: dict[str, object], partial: Path) -> None:
        from mineocclude.contracts.identity import SCHEMA_VERSION
        from mineocclude.models import mineworld_adapter as api
        from scripts import run_person_a_66_cell_production_extraction as production

        if production._RUNTIME.adapter is None:
            production._RUNTIME.ensure_loaded()
            self.load_count += 1
        adapter = production._RUNTIME.adapter
        runtime = production._RUNTIME.runtime_identity
        package_path = partial / "capture_package_v0_1.json"
        package_bytes = package_path.read_bytes()
        package_hash = hashlib.sha256(package_bytes).hexdigest()
        document = json.loads(package_bytes)
        validated = adapter.validate_trajectory(api.AcceptedTrajectoryInput(schema_version=SCHEMA_VERSION, trajectory_id=document["trajectory_id"], accepted_manifest_sha256=package_hash, document=document))
        visibility = read_jsonl(partial / "raw/visibility.jsonl")
        targets = [int(row["model_frame_idx"]) for row in visibility if row.get("tau") in range(1, 20)]
        required_indices = range(targets[0] - 15, targets[-1] + 1)
        identities = {identity.model_frame_idx: identity for identity in validated.frame_identities}
        frames = {}
        for index in required_indices:
            identity = identities[index]
            rgb = np.asarray(Image.open(partial / f"raw/frames/{index:06d}.png").convert("RGB"))
            processed = adapter.preprocess_frame(api.FramePreprocessRequest(identity, index, rgb))
            frames[index] = dataclasses.replace(processed, preprocessing_profile=runtime.preprocessing_identity)
        raw_actions = {row["model_frame_idx"]: row for row in document["streams"]["raw_actions"]}
        actions = {
            index: adapter.convert_action(api.ActionConversionRequest(identities[index], int(raw_actions[index]["action_idx"]), raw_actions[index]["raw_action"]))
            for index in required_indices
        }
        activation_root = partial / "activations"
        activation_root.mkdir()
        arrays = {
            layer: np.lib.format.open_memmap(activation_root / f"layer_{layer:02d}.npy", mode="w+", dtype=np.float16, shape=(19, 336, 2048))
            for layer in range(20)
        }
        for tau_index, target in enumerate(targets):
            indices = list(range(target - 15, target + 1))
            window = dataclasses.replace(validated, frame_identities=tuple(identities[index] for index in indices))
            tokenized = adapter.tokenize_trajectory(api.TrajectoryTokenizationRequest(runtime_identity=runtime, trajectory=window, frames=tuple(frames[index] for index in indices), actions=tuple(actions[index] for index in indices)))
            _result, captures = production._teacher_capture(adapter, runtime, tokenized, package_hash)
            span = tokenized.frame_token_map.spans[-1]
            for capture in captures:
                layer = int(capture.layer.layer_idx)
                tensor = capture.output.tensor[:, span.visual_positions, :].detach().cpu().numpy()
                arrays[layer][tau_index] = tensor[0].astype(np.float16, copy=False)
            del captures, _result
        for array in arrays.values():
            array.flush()
        artifacts = [
            {"path": path.relative_to(partial).as_posix(), "layer_idx": layer, "shape": [19, 336, 2048], "dtype": "float16", "byte_size": path.stat().st_size, "sha256": sha256_file(path)}
            for layer, path in enumerate(sorted(activation_root.glob("layer_*.npy")))
        ]
        (partial / "activation_inventory.json").write_text(json.dumps({
            "schema_version": "regime-a-target-activation-inventory-v1.0",
            "trajectory_spec_id": spec["trajectory_spec_id"], "spec_hash": spec["spec_hash"],
            "checkpoint_sha256": CHECKPOINT_SHA256, "layer_indices": list(range(20)),
            "target_tau": list(range(1, 20)), "target_model_frame_indices": targets,
            "visual_tokens_per_target": 336, "hidden_width": 2048, "dtype": "float16",
            "serialization": "numpy-npy-little-endian-target-token-tensors", "artifacts": artifacts,
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def close(self) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", type=Path, required=True)
    parser.add_argument("--study-manifest", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--durable-prefix", required=True)
    parser.add_argument("--a4-authorization", type=Path)
    parser.add_argument("--authorize-execution", action="store_true")
    args = parser.parse_args()

    rows, manifest_hash = validate_manifest(args.manifest, args.manifest_sha256)
    study_hash = sha256_file(args.study_manifest)
    ledger = HashChainLedger(args.runtime_root / "progress_ledger.jsonl")
    plan = frozen_plan(rows, ledger)
    result = {
        "status": "VALIDATED_FROZEN_PLAN",
        "manifest_sha256": manifest_hash,
        "study_manifest_sha256": study_hash,
        "remaining_spec_ids": [row["trajectory_spec_id"] for row in plan],
        "complete_count": len(rows) - len(plan),
        "execution_started": False,
    }
    if args.authorize_execution:
        authorize_or_fail(args.a4_authorization, manifest_hash, study_hash)
        repository_root = ROOT.resolve()
        runtime_root = args.runtime_root.resolve()
        if runtime_root == repository_root or repository_root in runtime_root.parents:
            raise RegimeAError("runtime root must be outside the Git repository")
        runner = A4ExecutionRunner(
            store=AtomicTrajectoryStore(runtime_root / "trajectories"),
            ledger=ledger,
            capture_worker=ProductionCaptureWorker(runtime_root),
            model_worker=PersistentMineWorldWorker(),
            durable_store=S3DurableStore(args.durable_prefix),
        )
        dispatched = runner.run(rows)
        result["status"] = "COMPLETE_VALIDATED_DURABLE"
        result["dispatched_spec_ids"] = dispatched
        result["execution_started"] = bool(dispatched)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RegimeAError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"REGIME_A_REFUSAL: {exc}", file=sys.stderr)
        raise SystemExit(2)
