#!/usr/bin/env python3
"""Fail-closed ingestion for one C1.5 reconstruction operator receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
SERVER = Path(r"C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server")
CLIENT = Path(r"C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client")
CONFIG = REPO / "configs/scenes/layouts_v0_4.yaml"
EXPECTED_VERSION = "person-c-layout-config-v0.4"
EXPECTED_LAYOUT = "layout_01"


def identity(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"path": str(path.resolve()), "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--operator", choices=("first", "second"), required=True)
    parser.add_argument("--geometry-receipt", type=Path, required=True)
    parser.add_argument("--screenshot", type=Path, required=True)
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    for path in (CONFIG, args.geometry_receipt, args.screenshot, args.attestation,
                 SERVER / "logs/latest.log", CLIENT / "logs/latest.log",
                 SERVER / "server.properties", CLIENT / "options.txt"):
        require(path.is_file(), f"required evidence file absent: {path}")
    require(not args.output.exists(), f"create-only output already exists: {args.output}")

    config = load(CONFIG)
    receipt = load(args.geometry_receipt)
    attestation = load(args.attestation)
    require(config["config_version"] == EXPECTED_VERSION, "accepted geometry version mismatch")
    layout = next(item for item in config["layouts"] if item["layout_id"] == EXPECTED_LAYOUT)
    expected_episode = 11501 if args.operator == "first" else 11502
    expected_receipt = ("c1_5_first_operator_layout_01" if args.operator == "first"
                        else "c1_5_second_operator_layout_01")
    require(receipt.get("receipt_id") == expected_receipt, "receipt identity mismatch")
    require(receipt.get("layout_id") == EXPECTED_LAYOUT, "layout identity mismatch")
    require(receipt.get("episode_id") == expected_episode, "episode identity mismatch")
    require(receipt.get("observation_only") is True, "receipt is not observation-only")
    require(receipt.get("scientific_use") == "forbidden", "receipt scientific-use field mismatch")
    target = receipt.get("target", {})
    require(target.get("valid") is True and target.get("tagged_target_count") == 1,
            "target status is not valid/exactly-one")
    for key, value in {
        "required": True, "tag": "mineocclude_experimental_target",
        "entity_type": "minecraft:sheep", "color": "magenta",
        "no_ai": True, "silent": True, "persistent": True,
        "invulnerable": True, "adult": True, "alive": True,
        "removed": False,
    }.items():
        require(target.get(key) == value, f"target field mismatch: {key}")
    require(target.get("actual_xyz") == target.get("expected_xyz"), "target location mismatch")
    require(target.get("problems") == [], "target receipt contains problems")

    receipt_markers = {row["color"]: row for row in receipt["markers"]}
    for expected in layout["markers"]:
        actual = receipt_markers[expected["color"]]
        require(actual["block_pos_xyz"] == expected["block_pos_xyz"],
                f"marker BlockPos mismatch: {expected['color']}")
        require(actual["top_face_centre_world_xyz"] == expected["top_face_centre_world_xyz"],
                f"marker top-face centre mismatch: {expected['color']}")
        require(actual["matches"] is True, f"marker block mismatch: {expected['color']}")
    require(receipt["camera"]["observed_players"], "no observed player camera")
    camera = receipt["camera"]["observed_players"][0]
    expected_camera = layout["camera"]
    require(camera["feet_xyz"] == expected_camera["feet_xyz"], "camera position mismatch")
    require(camera["yaw_degrees"] == expected_camera["yaw_degrees"], "camera yaw mismatch")
    require(camera["pitch_degrees"] == expected_camera["pitch_degrees"], "camera pitch mismatch")

    require(attestation.get("template") is False, "attestation remains a template")
    require(bool(attestation.get("operator_id")), "operator identity missing")
    require(attestation.get("operator_role") == args.operator, "operator role mismatch")
    if args.operator == "second":
        require(attestation.get("independent_from_first_operator") is True,
                "second operator independence not attested")
    server_log = (SERVER / "logs/latest.log").read_text(encoding="utf-8", errors="replace")
    client_log = (CLIENT / "logs/latest.log").read_text(encoding="utf-8", errors="replace")
    require(f"episode={expected_episode}" in server_log and "target status: valid=true" in server_log,
            "valid targetstatus line for episode missing")
    require("target retention failure" not in server_log, "server logged target retention failure")
    require("joined the game" in server_log and "left the game" in server_log,
            "client join/disconnect evidence incomplete")
    require("Stopping server" in server_log and "Saving worlds" in server_log,
            "server clean shutdown evidence incomplete")
    require("Connecting to 127.0.0.1, 25565" in client_log and "Stopping!" in client_log,
            "client connection/exit evidence incomplete")
    properties = (SERVER / "server.properties").read_text(encoding="utf-8-sig")
    require("spawn-animals=false" in properties.splitlines(), "spawn-animals=false not retained")
    png = args.screenshot.read_bytes()
    require(png[:8] == b"\x89PNG\r\n\x1a\n" and png[12:16] == b"IHDR", "screenshot is not PNG")
    width, height = struct.unpack(">II", png[16:24])
    require(width > 0 and height > 0, "invalid screenshot dimensions")

    result = {
        "schema_version": "person-c-c1.5-ingested-operator-receipt-v0.2",
        "operator_role": args.operator,
        "accepted_geometry_version": EXPECTED_VERSION,
        "layout_id": EXPECTED_LAYOUT,
        "episode_id": expected_episode,
        "status": "PASS",
        "c1_5_complete": False,
        "second_operator_still_required": args.operator == "first",
        "files": {
            "geometry_receipt": identity(args.geometry_receipt),
            "screenshot": {**identity(args.screenshot), "width": width, "height": height},
            "attestation": identity(args.attestation),
            "server_log": identity(SERVER / "logs/latest.log"),
            "client_log": identity(CLIENT / "logs/latest.log"),
            "server_properties": identity(SERVER / "server.properties"),
            "client_options": identity(CLIENT / "options.txt"),
            "accepted_geometry": identity(CONFIG),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as handle:
        handle.write((json.dumps(result, indent=2) + "\n").encode("utf-8"))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
