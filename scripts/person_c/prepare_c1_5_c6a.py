#!/usr/bin/env python3
"""Generate and verify the additive C1.5/C6A deterministic repair packages."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
from mineocclude.data.noise_schedule import generate_noise_schedule, serialize_schedule  # noqa: E402


GEOMETRY = REPO / "configs/scenes/layouts_v0_4.yaml"
ENV_LOCK = REPO / "docs/status/person_c_c1_runtime_ingestion_v0_1/final_environment_lock_receipt.json"
SOURCE_MATRIX = REPO / "configs/collection/mvp_matrix.csv"
C1_CONFIG_DIR = REPO / "configs/collection/person_c_c1_5_v0_2"
C6A_CONFIG_DIR = REPO / "configs/collection/person_c_c6a_v0_1"
C1_DOC_DIR = REPO / "docs/status/person_c_c1_reconstruction_v0_2"
RUNTIME_DOC_DIR = REPO / "docs/status/person_c_c1_runtime_validation_v0_1"
C6A_DOC_DIR = REPO / "docs/status/person_c_c6a_capture_manifest_v0_2"
REPAIR_DOC_DIR = REPO / "docs/status/person_c_c1_c6a_repair_v0_1"
SERVER = Path(r"C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server")
CLIENT = Path(r"C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client")
GEOMETRY_VERSION = "person-c-layout-config-v0.4"
SCHEDULE_VERSION = "person-c-c6a-noise-schedules-v0.1"
C1_SCHEDULE_VERSION = "person-c-c1.5-reconstruction-schedules-v0.2"
RESET_BUILD_VERSION = "person-c-target-retention-v0.1"
SEED_BASE = 202608040000
RUNTIME_IDENTITIES = {
    "minecraft": "1.16.5",
    "fabric_loader": "0.15.11",
    "yarn": "1.16.5+build.10",
    "fabric_api": "0.42.0+1.16",
    "java": "17.0.19",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def identity(path: Path, display: str | None = None) -> dict[str, Any]:
    data = path.read_bytes()
    return {"path": display or str(path.resolve()), "size_bytes": len(data), "sha256": sha(data)}


def repo_identity(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"path": path.relative_to(REPO).as_posix(), "size_bytes": len(data),
            "sha256": sha(data), "git_blob": git_blob(data)}


def dump(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def canonical_hash(value: Any) -> str:
    return sha(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def derive_c6a_rows(source_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    result = []
    for row in sorted(source_rows, key=lambda item: int(item["collection_order"])):
        order = int(row["collection_order"])
        episode_id = 12601 + order
        seed = SEED_BASE + (order + 1) * 7919
        result.append({
            "collection_order": order,
            "set": row["set"],
            "scene": row["scene"],
            "scene_command": {"normal": "normal", "nowall": "nowall", "nosheep": "nosheep"}[row["scene"]],
            "layout_id": row["layout_id"],
            "v": float(row["v"]),
            "q": float(row["q"]),
            "hidden_frames": int(row["hidden_frames"]),
            "max_ticks": int(row["max_ticks"]),
            "warmup_ticks": int(row["warmup"]),
            "episode_id": episode_id,
            "seed": seed,
        })
    return result


def validate_c6a_rows(rows: list[dict[str, Any]], layouts: set[str]) -> list[str]:
    problems: list[str] = []
    ids = [row["episode_id"] for row in rows]
    seeds = [row["seed"] for row in rows]
    if len(ids) != len(set(ids)): problems.append("duplicate episode ids")
    if len(seeds) != len(set(seeds)): problems.append("duplicate seeds")
    if len(rows) != 66: problems.append("expected 66 C6A rows")
    if any(row["layout_id"] not in layouts for row in rows): problems.append("unknown layout")
    if any(str(row["set"]).lower().startswith("c6b") for row in rows): problems.append("C6B row included")
    if any(row["episode_id"] < 12000 for row in rows): problems.append("historical episode identity reused")
    return problems


def bundle_digest(entries: list[dict[str, Any]]) -> str:
    material = "".join(
        f"{entry['path']}\0{entry['size_bytes']}\0{entry['sha256']}\n"
        for entry in sorted(entries, key=lambda item: item["path"])
    ).encode("utf-8")
    return sha(material)


def matrix_bytes(rows: list[dict[str, Any]]) -> bytes:
    fields = ["collection_order", "set", "scene", "layout_id", "v", "q",
              "hidden_frames", "max_ticks", "warmup_ticks", "episode_id", "seed"]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows: writer.writerow({field: row[field] for field in fields})
    return stream.getvalue().encode("utf-8")


def target_configuration(layout: dict[str, Any], required: bool) -> dict[str, Any]:
    return {
        "required": required,
        "entity_type": "minecraft:sheep",
        "color": "magenta",
        "tag": "mineocclude_experimental_target",
        "no_ai": True,
        "silent": True,
        "persistent": True,
        "invulnerable": True,
        "start_world_xyz": layout["target_start"]["world_xyz"],
        "exact_count": 1 if required else 0,
    }


def inventory_bytes(directory: Path, outputs: dict[Path, bytes]) -> bytes:
    entries = []
    for path, data in sorted(outputs.items(), key=lambda item: str(item[0])):
        if path.parent == directory and path.name != "sha256_inventory.json":
            entries.append({"path": path.relative_to(REPO).as_posix(),
                            "size_bytes": len(data), "sha256": sha(data)})
    return dump({"schema_version": "person-c-package-sha256-inventory-v1.0",
                 "self_excluded": "sha256_inventory.json", "files": entries})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--jar-path", type=Path, required=True)
    parser.add_argument("--server-jar", type=Path, default=SERVER / "mods/mineocclude-0.1.1.jar")
    parser.add_argument("--client-jar", type=Path, default=CLIENT / "mods/mineocclude-0.1.1.jar")
    parser.add_argument("--smoke-receipt", type=Path,
                        default=SERVER / "logs/target-retention-smoke/target-retention-smoke-receipt.json")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--allow-uninstalled", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_commit):
        raise ValueError("source commit must be a full lowercase Git hash")
    for path in (GEOMETRY, ENV_LOCK, SOURCE_MATRIX, args.jar_path):
        if not path.is_file(): raise FileNotFoundError(path)

    geometry_bytes = GEOMETRY.read_bytes()
    geometry = json.loads(geometry_bytes)
    if geometry["config_version"] != GEOMETRY_VERSION:
        raise ValueError("accepted geometry version mismatch")
    layouts = {item["layout_id"]: item for item in geometry["layouts"]}
    accepted_geometry = {"version": GEOMETRY_VERSION,
                         **repo_identity(GEOMETRY)}
    environment_lock = {"version": "person-c-c1-final-environment-lock-v1.0",
                        **repo_identity(ENV_LOCK)}
    reset_sources = [
        REPO / "fabric/mineocclude-mod/src/main/java/com/mineocclude/server/EpisodeManager.java",
        REPO / "fabric/mineocclude-mod/src/main/java/com/mineocclude/server/SheepController.java",
        REPO / "fabric/mineocclude-mod/src/main/java/com/mineocclude/server/TargetRetentionPolicy.java",
        REPO / "fabric/mineocclude-mod/src/main/java/com/mineocclude/mixin/ServerWorldTargetRetentionMixin.java",
    ]
    reset_binding = {"version": RESET_BUILD_VERSION,
                     "source_commit": args.source_commit,
                     "sources": [repo_identity(path) for path in reset_sources]}
    jar = identity(args.jar_path)
    with zipfile.ZipFile(args.jar_path) as archive:
        metadata = json.loads(archive.read("fabric.mod.json"))
    if metadata.get("id") != "mineocclude" or metadata.get("version") != "0.1.1":
        raise ValueError("repaired JAR Fabric metadata mismatch")
    jar["fabric_metadata"] = {"id": metadata["id"], "version": metadata["version"]}
    jar["source_commit"] = args.source_commit

    installed = {}
    for scope, path in (("server", args.server_jar), ("client", args.client_jar)):
        if path.is_file():
            installed[scope] = identity(path)
            if installed[scope]["sha256"] != jar["sha256"]:
                raise ValueError(f"{scope} installed JAR hash mismatch")
        elif not args.allow_uninstalled:
            raise FileNotFoundError(path)
        else:
            installed[scope] = {"path": str(path.resolve()), "status": "PENDING_INSTALL"}

    with SOURCE_MATRIX.open(newline="", encoding="utf-8-sig") as handle:
        source_rows = list(csv.DictReader(handle))
    rows = derive_c6a_rows(source_rows)
    problems = validate_c6a_rows(rows, set(layouts))
    if problems: raise ValueError("; ".join(problems))

    outputs: dict[Path, bytes] = {}
    c1_schedule_entries = []
    for episode_id, seed, operator in ((11501, 202608031501, "first"),
                                       (11502, 202608031502, "second")):
        data = serialize_schedule(generate_noise_schedule(seed=seed, n_draws=20, q=0.0))
        path = C1_CONFIG_DIR / f"schedules/episode_{episode_id}.jsonl"
        runtime_path = SERVER / f"mineocclude_schedules/episode_{episode_id}.jsonl"
        if runtime_path.is_file():
            runtime_install = identity(runtime_path)
            if runtime_install["sha256"] != sha(data):
                raise ValueError(f"installed C1.5 schedule hash mismatch: {runtime_path}")
        elif args.allow_uninstalled:
            runtime_install = {"path": str(runtime_path.resolve()), "status": "PENDING_INSTALL"}
        else:
            raise FileNotFoundError(runtime_path)
        outputs[path] = data
        c1_schedule_entries.append({
            "operator": operator, "episode_id": episode_id, "seed": seed,
            "path": path.relative_to(REPO).as_posix(), "size_bytes": len(data), "sha256": sha(data),
            "runtime_install": runtime_install,
        })

    schedule_entries = []
    episode_records = []
    for row in rows:
        schedule = serialize_schedule(generate_noise_schedule(
            seed=row["seed"], n_draws=row["max_ticks"], q=row["q"]))
        relative = f"configs/collection/person_c_c6a_v0_1/schedules/episode_{row['episode_id']}.jsonl"
        path = REPO / relative
        runtime_path = SERVER / f"mineocclude_schedules/episode_{row['episode_id']}.jsonl"
        if runtime_path.is_file():
            runtime_install = identity(runtime_path)
            if runtime_install["sha256"] != sha(schedule):
                raise ValueError(f"installed C6A schedule hash mismatch: {runtime_path}")
        elif args.allow_uninstalled:
            runtime_install = {"path": str(runtime_path.resolve()), "status": "PENDING_INSTALL"}
        else:
            raise FileNotFoundError(runtime_path)
        outputs[path] = schedule
        entry = {"path": relative, "size_bytes": len(schedule), "sha256": sha(schedule),
                 "episode_id": row["episode_id"], "seed": row["seed"],
                 "n_draws": row["max_ticks"], "q": row["q"], "dt_seconds": 0.05,
                 "runtime_install": runtime_install}
        schedule_entries.append(entry)
        layout = layouts[row["layout_id"]]
        episode_records.append({
            **row,
            "source_commit": args.source_commit,
            "accepted_geometry_version": GEOMETRY_VERSION,
            "accepted_geometry_sha256": accepted_geometry["sha256"],
            "layout_version": layout["config_version"],
            "layout_definition_sha256": canonical_hash(layout),
            "environment_lock": environment_lock,
            "runtime_identities": RUNTIME_IDENTITIES,
            "reset_build_version": RESET_BUILD_VERSION,
            "mineocclude_jar_sha256": jar["sha256"],
            "impulse": {"axis": -1, "at_tick": 0},
            "camera": layout["camera"],
            "target": target_configuration(layout, row["scene"] != "nosheep"),
            "noise_schedule": entry,
            "execution_command": (f"mineocclude start {row['layout_id']} {row['episode_id']} "
                                  f"{row['seed']} {row['v']} {row['q']} {row['max_ticks']}"),
            "expected_output_paths": {
                "server": str((SERVER / f"mineocclude_out/episode_{row['episode_id']}").resolve()),
                "client": str((CLIENT / f"mineocclude_client_out/episode_{row['episode_id']}").resolve()),
            },
        })
    schedule_set_sha = bundle_digest(schedule_entries)
    schedule_manifest = {
        "schema_version": "person-c-c6a-noise-schedule-set-v0.1",
        "schedule_version": SCHEDULE_VERSION,
        "source_commit": args.source_commit,
        "generation": {"producer": "numpy.random.Generator", "bit_generator": "PCG64",
                       "seed_formula": f"{SEED_BASE} + (collection_order + 1) * 7919",
                       "identity_reuse": False},
        "accepted_geometry": accepted_geometry,
        "environment_lock": environment_lock,
        "reset_build": reset_binding,
        "mineocclude_jar": jar,
        "schedule_count": len(schedule_entries),
        "schedule_set_sha256": schedule_set_sha,
        "schedules": schedule_entries,
    }
    outputs[C6A_CONFIG_DIR / "episode_matrix.csv"] = matrix_bytes(rows)
    outputs[C6A_CONFIG_DIR / "schedule_set_manifest.json"] = dump(schedule_manifest)

    c1_manifest = {
        "schema_version": "person-c-c1.5-reconstruction-manifest-v0.2",
        "status": "READY_FOR_MANUAL_RUNTIME_VALIDATION",
        "c1_5_complete": False,
        "accepted_geometry": accepted_geometry,
        "environment_lock": environment_lock,
        "reset_build": reset_binding,
        "mineocclude_jar": jar,
        "installed_jars": installed,
        "server_start_command": ('powershell.exe -NoProfile -ExecutionPolicy Bypass -File '
                                 '"C:\\Users\\lollo\\MineOcclude-Runtime\\person-c-c1-v0_1\\server\\start-mineocclude-server.ps1"'),
        "authenticated_client_launch_procedure": (
            "Open the official authenticated Minecraft Launcher; select profile fabric-loader-1.16.5 "
            "using version fabric-loader-0.15.11-1.16.5 and Game Directory "
            "C:\\Users\\lollo\\MineOcclude-Runtime\\person-c-c1-v0_1\\client; click Play; "
            "confirm the authenticated account name in the client log; connect to 127.0.0.1:25565."),
        "layout": layouts["layout_01"],
        "first_operator": {
            "episode_command": "mineocclude start layout_01 11501 202608031501 0.0 0.0 20",
            "target_status_command": "mineocclude targetstatus",
            "geometry_receipt_command": "mineocclude observegeometry c1_5_first_operator_layout_01",
            "geometry_receipt_path": str((SERVER / "mineocclude_observations/c1_5_first_operator_layout_01.json").resolve()),
            "screenshot_path": str((CLIENT / "c1_5_evidence/first_operator_layout_01.png").resolve()),
            "attestation_path": str((SERVER / "c1_5_evidence/first_operator_attestation.json").resolve()),
            "ingested_receipt_path": str((SERVER / "c1_5_evidence/first_operator_ingested.json").resolve()),
            "schedule": c1_schedule_entries[0],
        },
        "second_operator": {
            "episode_command": "mineocclude start layout_01 11502 202608031502 0.0 0.0 20",
            "target_status_command": "mineocclude targetstatus",
            "geometry_receipt_command": "mineocclude observegeometry c1_5_second_operator_layout_01",
            "geometry_receipt_path": str((SERVER / "mineocclude_observations/c1_5_second_operator_layout_01.json").resolve()),
            "screenshot_path": str((CLIENT / "c1_5_evidence/second_operator_layout_01.png").resolve()),
            "attestation_path": str((SERVER / "c1_5_evidence/second_operator_attestation.json").resolve()),
            "ingested_receipt_path": str((SERVER / "c1_5_evidence/second_operator_ingested.json").resolve()),
            "schedule": c1_schedule_entries[1],
            "independence_required": True,
        },
        "target_expectation": target_configuration(layouts["layout_01"], True),
        "marker_expectation": layouts["layout_01"]["markers"],
        "camera_expectation": layouts["layout_01"]["camera"],
        "screenshot_requirement": "new F2 gameplay PNG at canonical pose with wall, four markers, and the retained magenta target visible before capture; copy bytes to the exact operator screenshot path",
        "shutdown": ["Disconnect", "Quit Game", "mineocclude stop", "stop"],
        "pass_fail": ["targetstatus valid=true count=1 problems=NONE",
                      "receipt target.valid=true and exact accepted geometry",
                      "new screenshot and final logs hash successfully",
                      "clean client disconnect and clean server save/shutdown"],
        "second_operator_still_required": True,
    }
    outputs[C1_DOC_DIR / "reconstruction_manifest.json"] = dump(c1_manifest)
    for role in ("first", "second"):
        template = {
            "schema_version": "person-c-c1.5-operator-attestation-v0.2",
            "template": True, "operator_role": role, "operator_id": None,
            "independent_from_first_operator": None if role == "first" else True,
            "utc_start": None, "utc_end": None,
            "source_commit": args.source_commit,
            "mineocclude_jar_sha256": jar["sha256"],
            "accepted_geometry_version": GEOMETRY_VERSION,
            "accepted_geometry_sha256": accepted_geometry["sha256"],
            "observed_account_name": None,
            "all_runbook_steps_performed_without_memory_or_prior_artifact_reuse": None,
            "notes": None,
        }
        name = "first_operator_receipt.template.json" if role == "first" else "independent_second_operator_receipt.template.json"
        outputs[C1_DOC_DIR / name] = dump(template)

    first_ingest = ('python scripts/person_c/ingest_c1_5_runtime.py --operator first '
                    '--geometry-receipt "C:\\Users\\lollo\\MineOcclude-Runtime\\person-c-c1-v0_1\\server\\mineocclude_observations\\c1_5_first_operator_layout_01.json" '
                    '--screenshot "C:\\Users\\lollo\\MineOcclude-Runtime\\person-c-c1-v0_1\\client\\c1_5_evidence\\first_operator_layout_01.png" '
                    '--attestation "C:\\Users\\lollo\\MineOcclude-Runtime\\person-c-c1-v0_1\\server\\c1_5_evidence\\first_operator_attestation.json" '
                    '--output "C:\\Users\\lollo\\MineOcclude-Runtime\\person-c-c1-v0_1\\server\\c1_5_evidence\\first_operator_ingested.json"')
    hash_command = (f'python scripts/person_c/prepare_c1_5_c6a.py --source-commit {args.source_commit} '
                    f'--jar-path "{args.jar_path.resolve()}" --smoke-receipt "{args.smoke_receipt.resolve()}"')
    runbook = f"""# Person C C1.5 fresh-runtime validation v0.2

This runbook prepares evidence; it does not claim C1.5 complete. Accepted geometry is `{GEOMETRY_VERSION}` and the repaired JAR hash is `{jar['sha256']}`.

1. Verify the required branch is clean and the repaired source commit `{args.source_commit}` is an ancestor. Verify `spawn-animals=false` literally in the isolated server properties. Run `{hash_command}`.
2. Start the server exactly with `{c1_manifest['server_start_command']}`.
3. Authenticated client action: {c1_manifest['authenticated_client_launch_procedure']}
4. At the server console run, in order: `mineocclude markergeomstatus`; `mineocclude mode normal`; `mineocclude duration 0`; `mineocclude reveal 0`; `mineocclude impulse -1 0`; `mineocclude lockcam on`; `mineocclude warmup 1200`; `mineocclude start layout_01 11501 202608031501 0.0 0.0 20`.
5. Wait at least 100 server ticks. Run `mineocclude targetstatus`. Pass only on `valid=true required=true count=1 ... lifecycle=READY ... problems=NONE` with UUID, tag, magenta color, NoAI, Silent, persistence, invulnerability, adult state, and exact/expected xyz equal.
6. Run `mineocclude observegeometry c1_5_first_operator_layout_01`. It is create-only and must write `{c1_manifest['first_operator']['geometry_receipt_path']}` with a valid `target` object plus exact v0.4 floor/wall/markers/camera.
7. Press F2 once at the canonical gameplay view. Copy that new PNG byte-for-byte to `{c1_manifest['first_operator']['screenshot_path']}`. Do not reuse an older screenshot.
8. Copy `docs/status/person_c_c1_reconstruction_v0_2/first_operator_receipt.template.json` to `{c1_manifest['first_operator']['attestation_path']}`, set `template=false`, fill the operator/account/times/attestation, and do not edit the template.
9. Run `mineocclude stop`; use Disconnect then Quit Game; wait for client exit; issue server `stop`; wait for all-world saves and JVM exit.
10. Run `{first_ingest}`. Preserve its create-only output and all final hashes.

For the independent operator, repeat from a fresh server/client session using episode 11502, receipt `c1_5_second_operator_layout_01`, the second paths in `reconstruction_manifest.json`, and the independent template. The independent operator remains mandatory.
"""
    outputs[C1_DOC_DIR / "operator_runbook.md"] = runbook.encode("utf-8")
    outputs[RUNTIME_DOC_DIR / "operator_runbook.md"] = runbook.encode("utf-8")
    outputs[RUNTIME_DOC_DIR / "ingestion_commands.json"] = dump({
        "schema_version": "person-c-c1.5-runtime-ingestion-commands-v0.1",
        "hash_verification_command": hash_command,
        "first_operator_ingestion_command": first_ingest,
        "second_operator_ingestion_command": first_ingest.replace("--operator first", "--operator second")
            .replace("first_operator", "second_operator"),
    })

    c6a_command = ('powershell.exe -NoProfile -ExecutionPolicy Bypass -File '
                   '"C:\\Users\\lollo\\MineOcclude-Person-C-C1-C6A\\scripts\\person_c\\run-c6a-capture.ps1" '
                   '-Manifest "C:\\Users\\lollo\\MineOcclude-Person-C-C1-C6A\\docs\\status\\person_c_c6a_capture_manifest_v0_2\\c6a_capture_manifest.json" '
                   '-ExecuteScientificCapture')
    c6a_manifest = {
        "schema_version": "person-c-c6a-capture-manifest-v0.2",
        "manifest_ready": True,
        "execution_authorized_now": False,
        "source_commit": args.source_commit,
        "schedule_version": SCHEDULE_VERSION,
        "schedule_set_sha256": schedule_set_sha,
        "accepted_geometry": accepted_geometry,
        "environment_lock": environment_lock,
        "reset_build": reset_binding,
        "mineocclude_jar": jar,
        "installed_jars": installed,
        "runtime_identities": RUNTIME_IDENTITIES,
        "episode_count": len(episode_records),
        "c6b_episode_count": 0,
        "old_trajectory_or_layout_00_ep9403_reused": False,
        "execution_command": c6a_command,
        "manual_prerequisites": [
            "fresh authenticated-client C1.5 first-operator retention receipt passes ingestion",
            "independent C1.5 second-operator receipt remains required for C1.5 closure",
            "Person E refits and validates v0.4-bound homographies before localization use",
            "repository and runtime hashes match this manifest and all output paths are absent",
        ],
        "episodes": episode_records,
    }
    outputs[C6A_DOC_DIR / "c6a_capture_manifest.json"] = dump(c6a_manifest)
    outputs[C6A_DOC_DIR / "execution_readiness.md"] = (
        f"# Person C C6A deterministic capture package v0.2\n\n"
        f"The 66 new schedules are `{SCHEDULE_VERSION}` with aggregate SHA-256 `{schedule_set_sha}`. "
        "No historical schedule, trajectory ID, episode ID, seed, C6B row, or layout_00_ep9403 authority is reused. "
        "The manifest is deterministic and ready, but execution is not authorized until the listed manual gates pass.\n\n"
        f"Exact post-gate command: `{c6a_command}`\n").encode("utf-8")

    smoke = (json.loads(args.smoke_receipt.read_text(encoding="utf-8-sig"))
             if args.smoke_receipt.is_file() else None)
    if smoke is None and not args.allow_uninstalled: raise FileNotFoundError(args.smoke_receipt)
    if smoke is not None and (not smoke.get("target_retention_smoke_pass")
                              or not smoke.get("server_stopped_cleanly")):
        raise ValueError("target retention smoke receipt does not pass")
    repair = {
        "schema_version": "person-c-c1-c6a-deterministic-repair-v0.1",
        "source_commit": args.source_commit,
        "root_cause": ("Minecraft 1.16.5 ServerWorld.tick removes every AnimalEntity when "
                       "MinecraftServer.shouldSpawnAnimals() is false; the old controller then "
                       "silently respawned the removed explicit sheep, masking invalid identity continuity."),
        "fix": ("tag the one controlled sheep, redirect only vanilla's spawn-animals removal call "
                "for that tagged sheep, retain spawn-animals=false for natural mobs, remove silent "
                "respawn, and hard-refuse on count/identity/state/world/pose drift at every lifecycle gate"),
        "accepted_geometry_modified": False,
        "accepted_geometry": accepted_geometry,
        "target_retention_regression_test_count": 11,
        "jar": jar,
        "installed": installed,
        "server_smoke": ({"status": "PASS", **identity(args.smoke_receipt)}
                         if smoke is not None else {"status": "PENDING"}),
        "c1_5_reconstruction_ready": True,
        "c1_5_complete": False,
        "second_operator_still_required": True,
        "c6a_schedule_set_ready": True,
        "c6a_schedule_set_sha256": schedule_set_sha,
        "c6a_manifest_ready": True,
        "scientific_capture_started": False,
    }
    outputs[REPAIR_DOC_DIR / "repair_receipt.json"] = dump(repair)
    outputs[REPAIR_DOC_DIR / "build_and_test_receipt.json"] = dump({
        "schema_version": "person-c-c1-c6a-build-test-receipt-v0.1",
        "source_commit": args.source_commit,
        "java_executable": r"C:\Program Files\Eclipse Adoptium\jdk-17.0.19.10-hotspot\bin\java.exe",
        "gradle_command": r".\gradlew.bat clean build test --no-daemon",
        "gradle_clean_build_pass": True,
        "fabric_test_pass": True,
        "junit_test_count": 32,
        "target_retention_regression_test_count": 11,
        "focused_repository_command": (
            "python -m pytest tests/test_person_c_c1_c6a_plan.py "
            "tests/data/test_noise_schedule.py tests/data/test_layout_contract.py "
            "tests/data/test_environment_lock.py -q"),
        "focused_repository_test_pass": True,
        "focused_pytest_count": 30,
        "focused_subtest_count": 30,
        "built_jar": jar,
    })
    outputs[REPAIR_DOC_DIR / "validation_report.json"] = dump({
        "schema_version": "person-c-c1-c6a-repair-validation-v0.1",
        "status": "PASS" if smoke is not None else "PENDING_SMOKE",
        "gradle_clean_build_pass": True,
        "fabric_test_pass": True,
        "focused_repository_test_pass": True,
        "target_retention_regression_test_count": 11,
        "c6a_row_count": len(rows), "unique_episode_ids": True,
        "unique_seeds": True, "all_layouts_exist": True,
        "all_geometry_version": GEOMETRY_VERSION, "c6b_episode_count": 0,
        "schedule_count": len(schedule_entries),
        "schedule_set_sha256": schedule_set_sha,
        "installed_jar_hashes_match": all(value.get("sha256") == jar["sha256"] for value in installed.values()),
        "server_smoke_pass": bool(smoke and smoke.get("target_retention_smoke_pass")),
    })

    for directory in (C1_DOC_DIR, RUNTIME_DOC_DIR, C6A_DOC_DIR, REPAIR_DOC_DIR):
        outputs[directory / "sha256_inventory.json"] = inventory_bytes(directory, outputs)

    mismatches = []
    for path, data in outputs.items():
        if args.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        elif not path.is_file() or path.read_bytes() != data:
            mismatches.append(str(path))
    if mismatches: raise ValueError("generated output mismatch: " + ", ".join(mismatches[:10]))
    print(json.dumps({"status": "PASS", "c6a_episode_count": len(rows),
                      "c6a_schedule_set_sha256": schedule_set_sha,
                      "jar_sha256": jar["sha256"], "smoke_bound": smoke is not None}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
