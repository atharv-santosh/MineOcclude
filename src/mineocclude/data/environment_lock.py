"""Structural and runtime-readiness checks for the C1 environment lock."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.data.capture_contract import PERSON_C_CONTRACT_VERSION


ENVIRONMENT_LOCK_VERSION = "0.1"
RUNTIME_EVIDENCE_REQUIRED = "RUNTIME EVIDENCE REQUIRED LATER"

VERSION_FIELDS = (
    "minecraft",
    "java",
    "fabric_loader",
    "yarn",
    "fabric_api",
    "gradle",
    "loom",
)

WORLD_FIELDS = (
    "world_seed",
    "world_type",
    "server_properties",
    "difficulty",
    "gamerules",
    "time",
    "weather",
    "resource_packs",
)

SERVER_PROPERTY_FIELDS = (
    "level-type",
    "generate-structures",
    "spawn-animals",
    "spawn-monsters",
    "allow-flight",
    "view-distance",
    "pvp",
)

GAMERULE_FIELDS = (
    "doMobSpawning",
    "doWeatherCycle",
    "doDaylightCycle",
    "mobGriefing",
    "randomTickSpeed",
    "doFireTick",
    "keepInventory",
)

GRAPHICS_FIELDS = (
    "graphics_mode",
    "render_distance_chunks",
    "entity_distance_scaling",
    "particles",
    "clouds",
    "smooth_lighting",
    "vsync",
    "max_fps",
    "mipmap_levels",
    "biome_blend_radius",
    "view_bobbing",
    "dynamic_fov",
    "capture_affecting_mod_settings",
)

RUNTIME_EVIDENCE_FIELDS = (
    "fresh_launch_manifest",
    "server_runtime_check",
    "client_runtime_check",
    "pixel_stability_check",
    "installed_mod_hash_check",
)


class EnvironmentRejectionCode(str, Enum):
    """Stable C1 environment-lock rejection codes."""

    MISSING_REQUIRED_FIELD = "missing_required_field"
    INVALID_SCHEMA_VERSION = "invalid_schema_version"
    INVALID_ENVIRONMENT_LOCK_VERSION = "invalid_environment_lock_version"
    INVALID_MINECRAFT_VERSION = "invalid_minecraft_version"
    MISSING_ENVIRONMENT_FIELD = "missing_environment_field"
    INVALID_ENVIRONMENT_FIELD = "invalid_environment_field"
    INVALID_CAPTURE_SETTING = "invalid_capture_setting"
    UNRESOLVED_RUNTIME_EVIDENCE = "unresolved_runtime_evidence"


@dataclass(frozen=True)
class EnvironmentRejection:
    """One immutable environment-lock issue."""

    code: EnvironmentRejectionCode
    message: str


@dataclass(frozen=True)
class EnvironmentValidationResult:
    """Separate structural validity from real runtime readiness."""

    structurally_valid: bool
    runtime_ready: bool
    rejections: tuple[EnvironmentRejection, ...]
    runtime_rejections: tuple[EnvironmentRejection, ...]


def load_environment_lock(path: str | Path) -> Any:
    """Load a dependency-free JSON-compatible YAML environment document."""

    return json.loads(Path(path).read_text(encoding="utf-8"))


def _reject(
    rejections: list[EnvironmentRejection],
    code: EnvironmentRejectionCode,
    message: str,
) -> None:
    rejections.append(EnvironmentRejection(code=code, message=message))


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _required_mapping(
    parent: Mapping[str, Any],
    field: str,
    label: str,
    rejections: list[EnvironmentRejection],
) -> Mapping[str, Any] | None:
    value = parent.get(field)
    if not isinstance(value, Mapping):
        _reject(
            rejections,
            EnvironmentRejectionCode.MISSING_ENVIRONMENT_FIELD,
            f"{label}.{field} must be a mapping.",
        )
        return None
    return value


def _contains_unresolved(value: Any) -> bool:
    if value == RUNTIME_EVIDENCE_REQUIRED:
        return True
    if isinstance(value, Mapping):
        return any(_contains_unresolved(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_unresolved(child) for child in value)
    return False


def _validate_versions(
    document: Mapping[str, Any],
    rejections: list[EnvironmentRejection],
) -> Mapping[str, Any] | None:
    versions = _required_mapping(document, "versions", "environment", rejections)
    if versions is None:
        return None
    for field in VERSION_FIELDS:
        if field not in versions:
            _reject(
                rejections,
                EnvironmentRejectionCode.MISSING_ENVIRONMENT_FIELD,
                f"versions.{field} is required.",
            )
        elif not _is_non_empty_string(versions[field]):
            _reject(
                rejections,
                EnvironmentRejectionCode.INVALID_ENVIRONMENT_FIELD,
                f"versions.{field} must be an explicit string.",
            )
    if versions.get("minecraft") != "1.16.5":
        _reject(
            rejections,
            EnvironmentRejectionCode.INVALID_MINECRAFT_VERSION,
            "Minecraft must be exactly 1.16.5.",
        )
    return versions


def _validate_world(
    document: Mapping[str, Any],
    rejections: list[EnvironmentRejection],
) -> None:
    world = _required_mapping(document, "world", "environment", rejections)
    if world is None:
        return
    for field in WORLD_FIELDS:
        if field not in world:
            _reject(
                rejections,
                EnvironmentRejectionCode.MISSING_ENVIRONMENT_FIELD,
                f"world.{field} is required.",
            )
    if world.get("world_type") != "superflat":
        _reject(
            rejections,
            EnvironmentRejectionCode.INVALID_ENVIRONMENT_FIELD,
            "world.world_type must be superflat.",
        )
    seed = world.get("world_seed")
    if not (_is_integer(seed) or seed == RUNTIME_EVIDENCE_REQUIRED):
        _reject(
            rejections,
            EnvironmentRejectionCode.INVALID_ENVIRONMENT_FIELD,
            "world.world_seed must be an integer or the runtime sentinel.",
        )
    if world.get("difficulty") != "peaceful":
        _reject(
            rejections,
            EnvironmentRejectionCode.INVALID_ENVIRONMENT_FIELD,
            "world.difficulty must be peaceful.",
        )

    server_properties = world.get("server_properties")
    if isinstance(server_properties, Mapping):
        properties = server_properties.get("properties")
        if not isinstance(properties, Mapping):
            _reject(
                rejections,
                EnvironmentRejectionCode.MISSING_ENVIRONMENT_FIELD,
                "world.server_properties.properties must be a mapping.",
            )
        else:
            for field in SERVER_PROPERTY_FIELDS:
                if field not in properties:
                    _reject(
                        rejections,
                        EnvironmentRejectionCode.MISSING_ENVIRONMENT_FIELD,
                        f"server.properties {field!r} is required.",
                    )
    elif "server_properties" in world:
        _reject(
            rejections,
            EnvironmentRejectionCode.INVALID_ENVIRONMENT_FIELD,
            "world.server_properties must be a mapping.",
        )

    gamerules = world.get("gamerules")
    if isinstance(gamerules, Mapping):
        for field in GAMERULE_FIELDS:
            if field not in gamerules:
                _reject(
                    rejections,
                    EnvironmentRejectionCode.MISSING_ENVIRONMENT_FIELD,
                    f"world.gamerules.{field} is required.",
                )
    elif "gamerules" in world:
        _reject(
            rejections,
            EnvironmentRejectionCode.INVALID_ENVIRONMENT_FIELD,
            "world.gamerules must be a mapping.",
        )

    time = world.get("time")
    if not isinstance(time, Mapping) or time.get("mode") != "fixed" or not _is_integer(
        time.get("ticks") if isinstance(time, Mapping) else None
    ):
        _reject(
            rejections,
            EnvironmentRejectionCode.INVALID_ENVIRONMENT_FIELD,
            "world.time must define a fixed integer tick.",
        )
    weather = world.get("weather")
    if not isinstance(weather, Mapping) or weather.get("mode") != "clear":
        _reject(
            rejections,
            EnvironmentRejectionCode.INVALID_ENVIRONMENT_FIELD,
            "world.weather must be fixed clear weather.",
        )
    packs = world.get("resource_packs")
    if not isinstance(packs, Mapping) or not isinstance(packs.get("client_packs"), list):
        _reject(
            rejections,
            EnvironmentRejectionCode.INVALID_ENVIRONMENT_FIELD,
            "world.resource_packs must explicitly list client packs.",
        )


def _validate_client(
    document: Mapping[str, Any],
    rejections: list[EnvironmentRejection],
) -> None:
    client = _required_mapping(document, "client", "environment", rejections)
    if client is None:
        return
    resolution = client.get("resolution")
    if (
        not isinstance(resolution, Mapping)
        or resolution.get("width_pixels") != 640
        or resolution.get("height_pixels") != 360
        or not isinstance(resolution.get("fullscreen"), bool)
    ):
        _reject(
            rejections,
            EnvironmentRejectionCode.INVALID_CAPTURE_SETTING,
            "client.resolution must explicitly define 640x360 and fullscreen state.",
        )
    fov = client.get("fov_degrees")
    if (
        not isinstance(fov, (int, float))
        or isinstance(fov, bool)
        or not 30 <= fov <= 110
    ):
        _reject(
            rejections,
            EnvironmentRejectionCode.INVALID_CAPTURE_SETTING,
            "client.fov_degrees must be in [30, 110].",
        )
    graphics = client.get("graphics")
    if not isinstance(graphics, Mapping):
        _reject(
            rejections,
            EnvironmentRejectionCode.MISSING_ENVIRONMENT_FIELD,
            "client.graphics must be a mapping.",
        )
    else:
        for field in GRAPHICS_FIELDS:
            if field not in graphics:
                _reject(
                    rejections,
                    EnvironmentRejectionCode.MISSING_ENVIRONMENT_FIELD,
                    f"client.graphics.{field} is required.",
                )


def _validate_server_and_mods(
    document: Mapping[str, Any],
    rejections: list[EnvironmentRejection],
) -> None:
    launcher = _required_mapping(
        document,
        "server_launcher",
        "environment",
        rejections,
    )
    if launcher is not None:
        for field in ("launcher_type", "version", "artifact_uri", "sha256", "status"):
            if field not in launcher:
                _reject(
                    rejections,
                    EnvironmentRejectionCode.MISSING_ENVIRONMENT_FIELD,
                    f"server_launcher.{field} is required.",
                )
    mods = _required_mapping(document, "installed_mods", "environment", rejections)
    if mods is not None:
        if "status" not in mods or not isinstance(mods.get("entries"), list):
            _reject(
                rejections,
                EnvironmentRejectionCode.MISSING_ENVIRONMENT_FIELD,
                "installed_mods requires status and an entries list.",
            )


def _runtime_issues(
    document: Mapping[str, Any],
    structurally_valid: bool,
) -> list[EnvironmentRejection]:
    if not structurally_valid:
        return [
            EnvironmentRejection(
                EnvironmentRejectionCode.UNRESOLVED_RUNTIME_EVIDENCE,
                "A structurally invalid lock cannot be runtime-ready.",
            )
        ]
    issues: list[EnvironmentRejection] = []
    if document.get("template") is not False:
        issues.append(
            EnvironmentRejection(
                EnvironmentRejectionCode.UNRESOLVED_RUNTIME_EVIDENCE,
                "An environment-lock template cannot be runtime-ready.",
            )
        )
    if document.get("runtime_status") != "runtime_verified":
        issues.append(
            EnvironmentRejection(
                EnvironmentRejectionCode.UNRESOLVED_RUNTIME_EVIDENCE,
                "runtime_status is not runtime_verified.",
            )
        )
    if _contains_unresolved(document):
        issues.append(
            EnvironmentRejection(
                EnvironmentRejectionCode.UNRESOLVED_RUNTIME_EVIDENCE,
                "The environment lock still contains runtime-evidence sentinels.",
            )
        )
    launcher = document.get("server_launcher")
    if isinstance(launcher, Mapping) and (
        launcher.get("artifact_uri") is None or launcher.get("sha256") is None
    ):
        issues.append(
            EnvironmentRejection(
                EnvironmentRejectionCode.UNRESOLVED_RUNTIME_EVIDENCE,
                "Server launcher artifact provenance is unresolved.",
            )
        )
    mods = document.get("installed_mods")
    if isinstance(mods, Mapping) and not mods.get("entries"):
        issues.append(
            EnvironmentRejection(
                EnvironmentRejectionCode.UNRESOLVED_RUNTIME_EVIDENCE,
                "The installed mod manifest has not been captured.",
            )
        )
    return issues


def validate_environment_lock(
    document: Mapping[str, Any],
) -> EnvironmentValidationResult:
    """Validate structure and separately assess real runtime readiness."""

    rejections: list[EnvironmentRejection] = []
    if not isinstance(document, Mapping):
        _reject(
            rejections,
            EnvironmentRejectionCode.MISSING_REQUIRED_FIELD,
            "Environment lock must be a mapping.",
        )
        runtime = _runtime_issues({}, False)
        return EnvironmentValidationResult(False, False, tuple(rejections), tuple(runtime))

    required = (
        "schema_version",
        "person_c_contract_version",
        "environment_lock_version",
        "template",
        "runtime_status",
        "versions",
        "server_launcher",
        "installed_mods",
        "world",
        "client",
        "runtime_evidence",
    )
    missing = [field for field in required if field not in document]
    if missing:
        _reject(
            rejections,
            EnvironmentRejectionCode.MISSING_REQUIRED_FIELD,
            "Environment lock is missing: " + ", ".join(missing),
        )
    if document.get("schema_version") != SCHEMA_VERSION:
        _reject(
            rejections,
            EnvironmentRejectionCode.INVALID_SCHEMA_VERSION,
            "Environment lock must preserve schema_version '1.0'.",
        )
    if (
        document.get("person_c_contract_version") != PERSON_C_CONTRACT_VERSION
        or document.get("environment_lock_version") != ENVIRONMENT_LOCK_VERSION
    ):
        _reject(
            rejections,
            EnvironmentRejectionCode.INVALID_ENVIRONMENT_LOCK_VERSION,
            "Environment/Person C versions must be C1 v0.1.",
        )
    if not isinstance(document.get("template"), bool):
        _reject(
            rejections,
            EnvironmentRejectionCode.INVALID_ENVIRONMENT_FIELD,
            "template must explicitly distinguish a template from an evidence copy.",
        )

    _validate_versions(document, rejections)
    _validate_server_and_mods(document, rejections)
    _validate_world(document, rejections)
    _validate_client(document, rejections)

    evidence = document.get("runtime_evidence")
    if not isinstance(evidence, Mapping):
        _reject(
            rejections,
            EnvironmentRejectionCode.MISSING_ENVIRONMENT_FIELD,
            "runtime_evidence must be a mapping.",
        )
    else:
        for field in RUNTIME_EVIDENCE_FIELDS:
            if field not in evidence:
                _reject(
                    rejections,
                    EnvironmentRejectionCode.MISSING_ENVIRONMENT_FIELD,
                    f"runtime_evidence.{field} is required.",
                )

    structurally_valid = not rejections
    runtime_rejections = _runtime_issues(document, structurally_valid)
    return EnvironmentValidationResult(
        structurally_valid=structurally_valid,
        runtime_ready=structurally_valid and not runtime_rejections,
        rejections=tuple(rejections),
        runtime_rejections=tuple(runtime_rejections),
    )
