"""Tests for the Person C C1 capture-environment lock contract."""

from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path

from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.data.capture_contract import PERSON_C_CONTRACT_VERSION
from mineocclude.data.environment_lock import (
    ENVIRONMENT_LOCK_VERSION,
    RUNTIME_EVIDENCE_REQUIRED,
    EnvironmentRejectionCode,
    load_environment_lock,
    validate_environment_lock,
)


ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = ROOT / "configs" / "scenes" / "environment_lock.template.yaml"
SCHEMA_PATH = (
    ROOT / "schemas" / "person_c" / "environment_lock_v0_1.schema.json"
)


def load_lock() -> dict:
    """Load a fresh copy of the checked environment-lock template."""

    return load_environment_lock(LOCK_PATH)


def structural_codes(result) -> set[EnvironmentRejectionCode]:
    """Return the stable structural rejection codes."""

    return {rejection.code for rejection in result.rejections}


class TestPersonCEnvironmentLock(unittest.TestCase):
    """Prove the template is complete without claiming runtime readiness."""

    def test_template_is_structurally_valid_but_not_runtime_ready(self) -> None:
        lock = load_lock()
        result = validate_environment_lock(lock)

        self.assertIs(lock["template"], True)
        self.assertTrue(result.structurally_valid, result.rejections)
        self.assertEqual(result.rejections, ())
        self.assertFalse(result.runtime_ready)
        self.assertIn(
            EnvironmentRejectionCode.UNRESOLVED_RUNTIME_EVIDENCE,
            {rejection.code for rejection in result.runtime_rejections},
        )
        self.assertTrue(
            any(
                "template cannot be runtime-ready" in rejection.message
                for rejection in result.runtime_rejections
            )
        )

    def test_required_versions_and_environment_fields_exist(self) -> None:
        lock = load_lock()
        versions = lock["versions"]
        world = lock["world"]
        client = lock["client"]

        self.assertEqual(lock["schema_version"], SCHEMA_VERSION)
        self.assertEqual(lock["person_c_contract_version"], PERSON_C_CONTRACT_VERSION)
        self.assertEqual(lock["environment_lock_version"], ENVIRONMENT_LOCK_VERSION)
        self.assertEqual(versions["minecraft"], "1.16.5")
        for field in (
            "java",
            "fabric_loader",
            "yarn",
            "fabric_api",
            "gradle",
            "loom",
        ):
            self.assertIn(field, versions)
        for field in (
            "world_seed",
            "server_properties",
            "difficulty",
            "gamerules",
            "time",
            "weather",
            "resource_packs",
        ):
            self.assertIn(field, world)
        self.assertEqual(client["resolution"]["width_pixels"], 640)
        self.assertEqual(client["resolution"]["height_pixels"], 360)
        self.assertIn("fov_degrees", client)
        self.assertIn("graphics", client)
        self.assertIn("server_launcher", lock)
        self.assertIn("installed_mods", lock)

    def test_runtime_evidence_uses_only_the_unresolved_sentinel(self) -> None:
        lock = load_lock()
        self.assertEqual(lock["runtime_status"], RUNTIME_EVIDENCE_REQUIRED)
        self.assertTrue(
            all(
                value == RUNTIME_EVIDENCE_REQUIRED
                for value in lock["runtime_evidence"].values()
            )
        )

    def test_invalid_environment_examples_fail_with_stable_codes(self) -> None:
        mutations = []

        missing_version = deepcopy(load_lock())
        del missing_version["versions"]["java"]
        mutations.append(
            (missing_version, EnvironmentRejectionCode.MISSING_ENVIRONMENT_FIELD)
        )

        wrong_minecraft = deepcopy(load_lock())
        wrong_minecraft["versions"]["minecraft"] = "1.20.1"
        mutations.append(
            (wrong_minecraft, EnvironmentRejectionCode.INVALID_MINECRAFT_VERSION)
        )

        missing_weather = deepcopy(load_lock())
        del missing_weather["world"]["weather"]
        mutations.append(
            (missing_weather, EnvironmentRejectionCode.MISSING_ENVIRONMENT_FIELD)
        )

        bad_world = deepcopy(load_lock())
        bad_world["world"]["world_type"] = "default"
        mutations.append(
            (bad_world, EnvironmentRejectionCode.INVALID_ENVIRONMENT_FIELD)
        )

        bad_resolution = deepcopy(load_lock())
        bad_resolution["client"]["resolution"]["width_pixels"] = 1920
        mutations.append(
            (bad_resolution, EnvironmentRejectionCode.INVALID_CAPTURE_SETTING)
        )

        for document, expected_code in mutations:
            with self.subTest(code=expected_code.value):
                result = validate_environment_lock(document)
                self.assertFalse(result.structurally_valid)
                self.assertFalse(result.runtime_ready)
                self.assertIn(expected_code, structural_codes(result))

    def test_validation_does_not_mutate_input(self) -> None:
        lock = load_lock()
        del lock["world"]["gamerules"]
        before = json.dumps(lock, sort_keys=True)

        result = validate_environment_lock(lock)

        self.assertFalse(result.structurally_valid)
        self.assertEqual(before, json.dumps(lock, sort_keys=True))

    def test_schema_versions_and_numeric_units_are_explicit(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        missing_units: list[str] = []

        def visit(value, path: str) -> None:
            if isinstance(value, dict):
                schema_type = value.get("type")
                numeric = (
                    schema_type in {"integer", "number"}
                    if isinstance(schema_type, str)
                    else isinstance(schema_type, list)
                    and bool({"integer", "number"}.intersection(schema_type))
                )
                if numeric and "x-unit" not in value:
                    missing_units.append(path)
                for key, child in value.items():
                    visit(child, f"{path}/{key}")
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    visit(child, f"{path}/{index}")

        visit(schema, "#")
        self.assertEqual(schema["properties"]["schema_version"]["const"], "1.0")
        self.assertEqual(
            schema["properties"]["person_c_contract_version"]["const"],
            "0.1",
        )
        self.assertEqual(
            schema["properties"]["environment_lock_version"]["const"],
            "0.1",
        )
        self.assertEqual(missing_units, [])


if __name__ == "__main__":
    unittest.main()
