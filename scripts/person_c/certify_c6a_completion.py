from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.person_c.prepare_c1_5_c6a import bundle_digest


ROOT = Path(__file__).resolve().parents[2]
SERVER = Path(r"C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server")
CLIENT = Path(r"C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client")
CAPTURE_MANIFEST = ROOT / "docs/status/person_c_c6a_capture_manifest_v0_2/c6a_capture_manifest.json"
SCHEDULE_MANIFEST = ROOT / "configs/collection/person_c_c6a_v0_1/schedule_set_manifest.json"
AUTHORIZATION = ROOT / "docs/status/person_c_c6a_e_refit_authorization_v0_1/c6a_execution_authorization.json"
PACKAGE_DIR = ROOT / "docs/status/person_c_c6a_completion_v0_1"

CANONICAL_ID = "person-c-c6a-post-c1-v0.1"
SOURCE_COMMIT = "c836641c894c88e3add207ef2190a2db88726024"
AUTHORIZATION_COMMIT = "28cac05a8c804372c71814fcf15c8f1a3b8fbe03"
PERSON_E_COMMIT = "c46d838b5a277e71a39090900f9e8ca814b743a7"
E_PACKAGE_SHA256 = "f5a90bb97d0f54e754cfa11c971532d8d2e29cbe6ce0151dfeb17faae61a17bc"
E_HANDOFF_SHA256 = "0937dcc6335927a1c724e8e3f1510be94b76ff91e3583c10d59d10ec60fb38ca"
GEOMETRY_VERSION = "person-c-layout-config-v0.4"
GEOMETRY_SHA256 = "34495d650d6a8c62b00a916796c90389b48f80d8f20a23eac93207758e993f5d"
JAR_SHA256 = "9ecbb5e85b249409d38428ea479c3f09ec97dd884a97ecb48d79590e4c03de52"
CAPTURE_MANIFEST_SHA256 = "174def13f71ad8c2df5615a0ef5ec7fc9e10b431c105fc995dc6508e87c2dc7d"
SCHEDULE_MANIFEST_SHA256 = "1abf0fc1e9f5633e17616a512d0bf84d66e048eef9986427c1908b834945346e"
SCHEDULE_SET_SHA256 = "79a81668362421fa91cb591d355b655e9b1a60aae088057de7bda977df663806"
SCENES = {"normal": "NORMAL", "nowall": "NO_WALL", "nosheep": "NO_SHEEP"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def identity(path: Path, display_path: str | None = None) -> dict[str, Any]:
    return {
        "path": display_path or str(path),
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def unique_event(lines: list[str], pattern: str, label: str) -> tuple[int, re.Match[str]]:
    matches = [(index, match) for index, line in enumerate(lines) if (match := re.search(pattern, line))]
    require(len(matches) == 1, f"{label}: expected exactly one event, found {len(matches)}")
    return matches[0]


def validate_runtime() -> dict[str, Any]:
    manifest = load_json(CAPTURE_MANIFEST)
    authorization = load_json(AUTHORIZATION)
    episodes = manifest["episodes"]
    require(sha256(CAPTURE_MANIFEST) == CAPTURE_MANIFEST_SHA256, "capture manifest SHA-256 mismatch")
    require(sha256(SCHEDULE_MANIFEST) == SCHEDULE_MANIFEST_SHA256, "schedule manifest SHA-256 mismatch")
    require(manifest["episode_count"] == len(episodes) == 66, "required episode count mismatch")
    require([episode["episode_id"] for episode in episodes] == list(range(12601, 12667)), "required episode IDs/order mismatch")
    require(len({episode["expected_output_paths"]["server"] for episode in episodes}) == 66, "duplicate server output path")
    require(len({episode["expected_output_paths"]["client"] for episode in episodes}) == 66, "duplicate client output path")
    require(manifest["accepted_geometry"]["version"] == GEOMETRY_VERSION, "accepted geometry version mismatch")
    require(manifest["accepted_geometry"]["sha256"] == GEOMETRY_SHA256, "accepted geometry manifest hash mismatch")
    require(sha256(ROOT / manifest["accepted_geometry"]["path"]) == GEOMETRY_SHA256, "accepted geometry disk hash mismatch")
    require(manifest["schedule_set_sha256"] == SCHEDULE_SET_SHA256, "schedule-set identity mismatch")
    require(manifest["mineocclude_jar"]["sha256"] == JAR_SHA256, "manifest JAR identity mismatch")
    for side in ("server", "client"):
        jar = manifest["installed_jars"][side]
        jar_path = Path(jar["path"])
        require(jar_path.is_file() and jar_path.stat().st_size == jar["size_bytes"] and sha256(jar_path) == JAR_SHA256, f"installed {side} JAR identity mismatch")
    require(authorization["person_e"]["commit"] == PERSON_E_COMMIT, "Person E commit binding mismatch")
    require(authorization["person_e"]["package"]["sha256"] == E_PACKAGE_SHA256, "Person E package binding mismatch")
    require(authorization["person_e"]["handoff"]["sha256"] == E_HANDOFF_SHA256, "E-to-C handoff binding mismatch")

    server_log_path = SERVER / "logs/latest.log"
    client_log_path = CLIENT / "logs/latest.log"
    server_lines = server_log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    client_lines = client_log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    episode_rows: list[dict[str, Any]] = []
    output_files: list[dict[str, Any]] = []
    schedule_rows: list[dict[str, Any]] = []

    for episode in episodes:
        episode_id = episode["episode_id"]
        layout_id = episode["layout_id"]
        scene = episode["scene"]
        seed = episode["seed"]
        velocity = episode["v"]
        noise_q = episode["q"]
        warmup_ticks = episode["warmup_ticks"]
        record_limit = episode["max_ticks"]
        draw_count = episode["noise_schedule"]["n_draws"]
        rng_source = "no_target" if scene == "nosheep" else "immutable_numpy_schedule"

        repository_schedule = ROOT / episode["noise_schedule"]["path"]
        installed_schedule = Path(episode["noise_schedule"]["runtime_install"]["path"])
        for path in (repository_schedule, installed_schedule):
            require(path.is_file(), f"episode {episode_id}: missing schedule {path}")
            require(path.stat().st_size == episode["noise_schedule"]["size_bytes"], f"episode {episode_id}: schedule size mismatch {path}")
            require(sha256(path) == episode["noise_schedule"]["sha256"], f"episode {episode_id}: schedule hash mismatch {path}")
        schedule = load_jsonl(repository_schedule)
        header, draws = schedule[0], schedule[1:]
        require(header["schedule_format_version"] == "person-c-noise-schedule-v0.1", f"episode {episode_id}: schedule schema")
        require(header["seed"] == seed and header["q"] == noise_q and header["n_draws"] == draw_count, f"episode {episode_id}: schedule header")
        require(len(draws) == draw_count and [draw["draw_idx"] for draw in draws] == list(range(draw_count)), f"episode {episode_id}: schedule rows")
        schedule_rows.append({
            "episode_id": episode_id,
            "seed": seed,
            "q": noise_q,
            "draw_count": draw_count,
            "repository": identity(repository_schedule, episode["noise_schedule"]["path"]),
            "runtime_install": identity(installed_schedule),
        })

        server_dir = Path(episode["expected_output_paths"]["server"])
        client_dir = Path(episode["expected_output_paths"]["client"])
        require(server_dir.is_dir() and client_dir.is_dir(), f"episode {episode_id}: output directory missing")
        require({path.name for path in server_dir.iterdir()} == {"finalization.json", "layout_meta.json", "lifecycle.jsonl", "reset_result.json", "server_state.jsonl"}, f"episode {episode_id}: server output schema")
        require({path.name for path in client_dir.iterdir()} == {"client_tick.jsonl", "frames", "raw_actions.jsonl"}, f"episode {episode_id}: client output schema")

        finalization = load_json(server_dir / "finalization.json")
        reset = load_json(server_dir / "reset_result.json")
        layout_meta = load_json(server_dir / "layout_meta.json")
        lifecycle = load_jsonl(server_dir / "lifecycle.jsonl")
        server_state = load_jsonl(server_dir / "server_state.jsonl")
        client_ticks = load_jsonl(client_dir / "client_tick.jsonl")
        actions = load_jsonl(client_dir / "raw_actions.jsonl")
        frames = sorted((client_dir / "frames").iterdir())
        observed_ticks = finalization["ticks"]
        expected_finalization = {
            "episode_id": episode_id,
            "state": "COMPLETED",
            "ticks": observed_ticks,
            "rng_source": rng_source,
            "schedule_draws_consumed": -1 if scene == "nosheep" else observed_ticks,
            "failure_reason": None,
        }
        require(finalization == expected_finalization, f"episode {episode_id}: finalization schema/identity")
        require(reset["episode_id"] == episode_id and reset["layout_id"] == layout_id and reset["seed"] == seed, f"episode {episode_id}: reset identity")
        require(reset["v"] == velocity and reset["q"] == noise_q and reset["rng_source"] == rng_source and reset["schedule_draws"] == draw_count, f"episode {episode_id}: reset parameters")
        require(reset["expected_target_count"] == reset["observed_target_count"] == episode["target"]["exact_count"] and reset["target_count_ok"] is True, f"episode {episode_id}: target check")
        require(layout_meta["layout_id"] == layout_id and layout_meta["scene"] == SCENES[scene], f"episode {episode_id}: layout metadata")
        expected_transitions = [("IDLE", "RESETTING"), ("RESETTING", "READY"), ("READY", "RECORDING"), ("RECORDING", "FINALIZING"), ("FINALIZING", "COMPLETED")]
        require([(row["from"], row["to"]) for row in lifecycle] == expected_transitions, f"episode {episode_id}: lifecycle")
        require("target verified" in lifecycle[1]["reason"], f"episode {episode_id}: target was not verified before recording")
        require(0 < observed_ticks <= record_limit, f"episode {episode_id}: invalid completion tick count")
        require(len(server_state) == len(client_ticks) == len(actions) == len(frames) == observed_ticks, f"episode {episode_id}: row/frame count mismatch")
        require([row["server_tick"] for row in server_state] == list(range(observed_ticks)), f"episode {episode_id}: server tick sequence")
        require([row["server_tick"] for row in client_ticks] == list(range(observed_ticks)), f"episode {episode_id}: client tick sequence")
        require([row["render_frame_idx"] for row in client_ticks] == list(range(observed_ticks)), f"episode {episode_id}: render-frame sequence")
        require([row["server_tick"] for row in actions] == list(range(observed_ticks)), f"episode {episode_id}: action tick sequence")
        require([row["action_idx"] for row in actions] == list(range(observed_ticks)), f"episode {episode_id}: action index sequence")
        require([path.name for path in frames] == [f"{index:06d}.png" for index in range(observed_ticks)], f"episode {episode_id}: frame names")
        require(all(path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" for path in frames), f"episode {episode_id}: invalid PNG output")
        require([row["frame_path"] for row in client_ticks] == [f"frames/{index:06d}.png" for index in range(observed_ticks)], f"episode {episode_id}: frame-path mapping")
        for index, row in enumerate(server_state):
            require(row["episode_id"] == episode_id and row["layout_id"] == layout_id and row["seed"] == seed, f"episode {episode_id}: server row identity")
            require(row["v"] == velocity and row["q"] == noise_q, f"episode {episode_id}: server row parameters")
            require(row["noise_draw"] is None if scene == "nosheep" else row["noise_draw"] == draws[index]["noise_draw"], f"episode {episode_id}: schedule consumption")
        require(all(row["episode_id"] == episode_id for row in client_ticks + actions), f"episode {episode_id}: client row identity")

        start_index, start = unique_event(server_lines, rf"/start requested: layout={layout_id} ep={episode_id} seed={seed} v=(?P<v>-?[0-9.]+) q=(?P<q>-?[0-9.]+) ticks=(?P<ticks>\d+) warmup=(?P<warmup>\d+)", f"episode {episode_id} start")
        require(float(start["v"]) == velocity and float(start["q"]) == noise_q and int(start["ticks"]) == record_limit and int(start["warmup"]) == warmup_ticks, f"episode {episode_id}: start parameters")
        load_index, load = unique_event(server_lines, rf"loaded immutable noise schedule \((?P<draws>\d+) draws\) from .*episode_{episode_id}\.jsonl", f"episode {episode_id} schedule load")
        require(int(load["draws"]) == draw_count, f"episode {episode_id}: schedule-load draw count")
        armed_index, armed = unique_event(server_lines, rf"episode {episode_id} armed \(layout={layout_id}, (?P<warmup>\d+) warmup \+ (?P<record>\d+) record ticks, v=(?P<v>-?[0-9.]+), q=(?P<q>-?[0-9.]+), seed=(?P<seed>-?\d+), rng={rng_source}\)", f"episode {episode_id} armed")
        require(int(armed["warmup"]) == warmup_ticks and int(armed["record"]) == record_limit and float(armed["v"]) == velocity and float(armed["q"]) == noise_q and int(armed["seed"]) == seed, f"episode {episode_id}: armed parameters")
        recording_index, _ = unique_event(server_lines, rf"\[MineOcclude\] episode {episode_id} recording started$", f"episode {episode_id} recording start")
        end_index, ended = unique_event(server_lines, rf"\[MineOcclude\] episode {episode_id} ended after (?P<ticks>\d+) ticks \((?P<visible>\d+) visible, (?P<hidden>\d+) hidden from camera; sheep respawns=(?P<respawns>-?\d+)\)", f"episode {episode_id} completion")
        require(start_index < load_index < armed_index < recording_index < end_index, f"episode {episode_id}: server chronology")
        visible = int(ended["visible"])
        hidden = int(ended["hidden"])
        respawns = int(ended["respawns"])
        require(int(ended["ticks"]) == observed_ticks and visible + hidden == observed_ticks, f"episode {episode_id}: completion counts")
        if scene == "normal":
            require(hidden == episode["hidden_frames"] and respawns == 0, f"episode {episode_id}: normal-scene completion")
        elif scene == "nowall":
            require(observed_ticks == record_limit and hidden == 0 and respawns == 0, f"episode {episode_id}: no-wall completion")
        else:
            require(observed_ticks == record_limit and visible == 0 and hidden == observed_ticks and respawns == -1, f"episode {episode_id}: no-sheep completion")
        candidate_lines = server_lines[start_index:end_index + 1]
        require(not any(re.search(rf"episode {episode_id} aborted|REFUSED:.*episode {episode_id}|target retention failure.*episode {episode_id}", line) for line in candidate_lines), f"episode {episode_id}: abort or hard-gate failure")
        client_recording_index, client_recording = unique_event(client_lines, rf"episode {episode_id} recording -> (?P<path>.*episode_{episode_id})$", f"episode {episode_id} client recording")
        client_end_index, client_ended = unique_event(client_lines, rf"episode {episode_id} finished, (?P<frames>\d+) frames$", f"episode {episode_id} client completion")
        require(client_recording_index < client_end_index and Path(client_recording["path"]) == client_dir and int(client_ended["frames"]) == observed_ticks, f"episode {episode_id}: client chronology/count/path")

        for side, directory in (("server", server_dir), ("client", client_dir)):
            for path in sorted(candidate for candidate in directory.rglob("*") if candidate.is_file()):
                output_files.append({
                    "episode_id": episode_id,
                    "side": side,
                    "relative_path": path.relative_to(directory).as_posix(),
                    **identity(path),
                })
        episode_rows.append({
            "episode_id": episode_id,
            "collection_order": episode["collection_order"],
            "layout_id": layout_id,
            "scene": scene,
            "seed": seed,
            "v": velocity,
            "q": noise_q,
            "warmup_ticks": warmup_ticks,
            "record_tick_limit": record_limit,
            "completed_record_ticks": observed_ticks,
            "visible_ticks": visible,
            "hidden_ticks": hidden,
            "schedule_draw_count": draw_count,
            "schedule_sha256": episode["noise_schedule"]["sha256"],
            "target_required": episode["target"]["required"],
            "target_expected_count": episode["target"]["exact_count"],
            "target_observed_count": reset["observed_target_count"],
            "target_check_valid": True,
            "recording_started": True,
            "recording_completed": True,
            "server_row_count": len(server_state),
            "client_tick_count": len(client_ticks),
            "action_row_count": len(actions),
            "frame_count": len(frames),
            "server_output_path": str(server_dir),
            "client_output_path": str(client_dir),
            "server_log_line_numbers": {
                "start": start_index + 1,
                "schedule_load": load_index + 1,
                "armed": armed_index + 1,
                "recording_started": recording_index + 1,
                "completed": end_index + 1,
            },
            "client_log_line_numbers": {
                "recording_started": client_recording_index + 1,
                "completed": client_end_index + 1,
            },
            "status": "PASS",
        })

    require(any("Stopping server" in line for line in server_lines), "server clean-shutdown event missing")
    require(any("All chunks are saved" in line for line in server_lines[-20:]), "server saved-chunks completion missing")
    require(any(line.endswith("Stopping!") for line in client_lines[-20:]), "client clean-shutdown event missing")
    prior_abort_logs: list[str] = []
    for path in sorted((SERVER / "logs").glob("*.log.gz")):
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as stream:
            text = stream.read()
        if "episode 12601 aborted during warmup" in text and "episode 12601 recording started" not in text:
            prior_abort_logs.append(str(path))
    require(prior_abort_logs, "earlier episode-12601 warmup-abort log was not found")
    return {
        "manifest": manifest,
        "episodes": episode_rows,
        "output_files": output_files,
        "schedules": schedule_rows,
        "server_log": server_log_path,
        "client_log": client_log_path,
        "prior_abort_logs": prior_abort_logs,
    }


def write_json_create_only(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def component_rows(paths: list[Path]) -> list[dict[str, Any]]:
    return [identity(path, path.relative_to(ROOT).as_posix()) for path in sorted(paths)]


def build_package(validation: dict[str, Any]) -> None:
    require(not PACKAGE_DIR.exists(), f"create-only C6A evidence package already exists: {PACKAGE_DIR}")
    PACKAGE_DIR.mkdir(parents=True)
    archived_server_log = PACKAGE_DIR / "server_latest.log.gz"
    archived_client_log = PACKAGE_DIR / "client_latest.log.gz"
    for source_path, archive_path in ((validation["server_log"], archived_server_log), (validation["client_log"], archived_client_log)):
        with archive_path.open("xb") as raw_target, source_path.open("rb") as source:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw_target, mtime=0) as compressed_target:
                shutil.copyfileobj(source, compressed_target)
        with gzip.open(archive_path, "rb") as archived, source_path.open("rb") as source:
            require(archived.read() == source.read(), f"log archive content mismatch: {archive_path}")

    output_inventory_path = PACKAGE_DIR / "output_inventory.json"
    output_rows = validation["output_files"]
    output_inventory = {
        "schema_version": "person-c-c6a-output-inventory-v0.1",
        "canonical_c6a_id": CANONICAL_ID,
        "episode_count": 66,
        "file_count": len(output_rows),
        "total_size_bytes": sum(row["size_bytes"] for row in output_rows),
        "output_bundle_sha256": bundle_digest(output_rows),
        "files": output_rows,
    }
    write_json_create_only(output_inventory_path, output_inventory)

    schedule_inventory_path = PACKAGE_DIR / "schedule_inventory.json"
    schedule_inventory = {
        "schema_version": "person-c-c6a-schedule-inventory-v0.1",
        "canonical_c6a_id": CANONICAL_ID,
        "schedule_count": 66,
        "schedule_set_sha256": SCHEDULE_SET_SHA256,
        "schedules": validation["schedules"],
    }
    write_json_create_only(schedule_inventory_path, schedule_inventory)

    episode_inventory_path = PACKAGE_DIR / "episode_inventory.json"
    episode_inventory = {
        "schema_version": "person-c-c6a-episode-inventory-v0.1",
        "canonical_c6a_id": CANONICAL_ID,
        "required_episode_count": 66,
        "completed_episode_count": 66,
        "episodes": validation["episodes"],
    }
    write_json_create_only(episode_inventory_path, episode_inventory)

    receipt_path = PACKAGE_DIR / "c6a_completion_receipt.json"
    receipt = {
        "schema_version": "person-c-c6a-completion-receipt-v0.1",
        "canonical_c6a_id": CANONICAL_ID,
        "status": "PASS",
        "immutable": True,
        "certified_utc": datetime.now(timezone.utc).isoformat(),
        "source_branch": "completion/person-c-c1-c6a",
        "source_commit": SOURCE_COMMIT,
        "authorization_commit": AUTHORIZATION_COMMIT,
        "schedule_observation_repair_commit": SOURCE_COMMIT,
        "required_episode_count": 66,
        "completed_episode_count": 66,
        "schedules_valid": True,
        "target_checks_valid": True,
        "recording_started_for_all": True,
        "recording_completed_for_all": True,
        "output_schemas_valid": True,
        "output_counts_valid": True,
        "earlier_12601_warmup_abort_distinguished": True,
        "earlier_12601_warmup_abort_logs": validation["prior_abort_logs"],
        "server_shutdown_clean": True,
        "client_shutdown_clean": True,
        "accepted_geometry": {"version": GEOMETRY_VERSION, "sha256": GEOMETRY_SHA256},
        "repaired_jar_sha256": JAR_SHA256,
        "person_e": {"commit": PERSON_E_COMMIT, "package_sha256": E_PACKAGE_SHA256, "handoff_sha256": E_HANDOFF_SHA256},
        "runtime_logs": {
            "server": identity(validation["server_log"]),
            "client": identity(validation["client_log"]),
        },
        "archived_logs": {
            "server": identity(archived_server_log, archived_server_log.relative_to(ROOT).as_posix()),
            "client": identity(archived_client_log, archived_client_log.relative_to(ROOT).as_posix()),
        },
        "unresolved_blockers": [],
    }
    write_json_create_only(receipt_path, receipt)

    handoff_path = PACKAGE_DIR / "person_c_to_person_e_c6a_provenance_handoff.json"
    handoff = {
        "schema_version": "person-c-to-person-e-c6a-provenance-handoff-v0.1",
        "status": "READY_FOR_PERSON_E_PROVENANCE_INGESTION",
        "canonical_c6a_id": CANONICAL_ID,
        "person_e_registry_closure_performed": False,
        "person_e_registry_closure_owner": "Person E",
        "person_c_authorization_commit": AUTHORIZATION_COMMIT,
        "person_c_schedule_observation_repair_commit": SOURCE_COMMIT,
        "person_e_refit_commit": PERSON_E_COMMIT,
        "person_e_refit_package_sha256": E_PACKAGE_SHA256,
        "person_e_to_person_c_refit_handoff_sha256": E_HANDOFF_SHA256,
        "accepted_geometry": {"version": GEOMETRY_VERSION, "sha256": GEOMETRY_SHA256},
        "repaired_jar_sha256": JAR_SHA256,
        "schedule_set_sha256": SCHEDULE_SET_SHA256,
        "required_episode_count": 66,
        "completed_episode_count": 66,
        "episode_inventory": identity(episode_inventory_path, episode_inventory_path.relative_to(ROOT).as_posix()),
        "output_inventory": identity(output_inventory_path, output_inventory_path.relative_to(ROOT).as_posix()),
        "schedule_inventory": identity(schedule_inventory_path, schedule_inventory_path.relative_to(ROOT).as_posix()),
        "completion_receipt": identity(receipt_path, receipt_path.relative_to(ROOT).as_posix()),
        "server_log": identity(archived_server_log, archived_server_log.relative_to(ROOT).as_posix()),
        "client_log": identity(archived_client_log, archived_client_log.relative_to(ROOT).as_posix()),
        "unresolved_blockers": [],
    }
    write_json_create_only(handoff_path, handoff)

    canonical_path = PACKAGE_DIR / "canonical_c6a_identity.json"
    canonical = {
        "schema_version": "person-c-c6a-canonical-identity-v0.1",
        "canonical_c6a_id": CANONICAL_ID,
        "status": "CANONICAL",
        "post_c1": True,
        "historical_pilots_and_failed_attempts_preserved": True,
        "person_e_registry_closure_performed": False,
        "completion_receipt": identity(receipt_path, receipt_path.relative_to(ROOT).as_posix()),
        "provenance_handoff": identity(handoff_path, handoff_path.relative_to(ROOT).as_posix()),
    }
    write_json_create_only(canonical_path, canonical)

    components = [archived_server_log, archived_client_log, output_inventory_path, schedule_inventory_path, episode_inventory_path, receipt_path, handoff_path, canonical_path]
    component_identities = component_rows(components)
    package_manifest_path = PACKAGE_DIR / "package_manifest.json"
    package_manifest = {
        "schema_version": "person-c-c6a-evidence-package-v0.1",
        "canonical_c6a_id": CANONICAL_ID,
        "status": "PASS",
        "immutable": True,
        "source_branch": "completion/person-c-c1-c6a",
        "source_commit": SOURCE_COMMIT,
        "authorization_commit": AUTHORIZATION_COMMIT,
        "capture_manifest": identity(CAPTURE_MANIFEST, CAPTURE_MANIFEST.relative_to(ROOT).as_posix()),
        "schedule_manifest": identity(SCHEDULE_MANIFEST, SCHEDULE_MANIFEST.relative_to(ROOT).as_posix()),
        "required_episode_count": 66,
        "completed_episode_count": 66,
        "component_files": component_identities,
        "evidence_bundle_sha256": bundle_digest(component_identities),
        "sha256_inventory_path": "docs/status/person_c_c6a_completion_v0_1/sha256_inventory.json",
    }
    write_json_create_only(package_manifest_path, package_manifest)

    inventory_rows = component_rows(components + [package_manifest_path])
    sha_inventory = {
        "schema_version": "person-c-package-sha256-inventory-v1.0",
        "self_excluded": "sha256_inventory.json",
        "canonical_c6a_id": CANONICAL_ID,
        "files": inventory_rows,
        "package_bundle_sha256": bundle_digest(inventory_rows),
    }
    write_json_create_only(PACKAGE_DIR / "sha256_inventory.json", sha_inventory)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-package", action="store_true")
    args = parser.parse_args()
    validation = validate_runtime()
    if args.write_package:
        build_package(validation)
    print("C6A_VALIDATION_PASS=True")
    print("REQUIRED_EPISODE_COUNT=66")
    print("COMPLETED_EPISODE_COUNT=66")
    if args.write_package:
        print(f"C6A_EVIDENCE_PACKAGE={PACKAGE_DIR / 'package_manifest.json'}")
        print(f"C_TO_E_PROVENANCE_HANDOFF={PACKAGE_DIR / 'person_c_to_person_e_c6a_provenance_handoff.json'}")


if __name__ == "__main__":
    main()
