"""Tests for the Person C C1 controlled-world layout contract."""

from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path

from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.data.capture_contract import PERSON_C_CONTRACT_VERSION
from mineocclude.data.layout_contract import (
    CANONICAL_MARKER_ROLES,
    EXPECTED_CONDITIONS,
    EXPECTED_LAYOUT_IDS,
    LAYOUT_SCHEMA_VERSION,
    RUNTIME_EVIDENCE_FIELDS,
    RUNTIME_EVIDENCE_REQUIRED,
    LayoutRejectionCode,
    load_layout_config,
    validate_layout_config,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "configs" / "scenes" / "layouts.yaml"
SCHEMA_PATH = ROOT / "schemas" / "person_c" / "layouts_v0_2.schema.json"
LEGACY_SCHEMA_PATH = ROOT / "schemas" / "person_c" / "layouts_v0_1.schema.json"


def load_config() -> dict:
    """Load a fresh copy of the checked C1 layout configuration."""

    return load_layout_config(CONFIG_PATH)


def rejection_codes(result) -> set[LayoutRejectionCode]:
    """Return the stable layout code set for a validation result."""

    return {rejection.code for rejection in result.rejections}


class TestPersonCLayoutContract(unittest.TestCase):
    """Prove stable layouts, explicit controls, and fail-closed validation."""

    def test_checked_config_is_valid_and_versions_are_additive(self) -> None:
        config = load_config()
        result = validate_layout_config(config)

        self.assertTrue(result.accepted, result.rejections)
        self.assertEqual(result.rejections, ())
        self.assertEqual(SCHEMA_VERSION, "1.0")
        self.assertEqual(config["schema_version"], "1.0")
        self.assertEqual(PERSON_C_CONTRACT_VERSION, "0.1")
        self.assertEqual(config["person_c_contract_version"], "0.1")
        self.assertEqual(config["layout_schema_version"], LAYOUT_SCHEMA_VERSION)

    def test_exactly_six_unique_stable_layout_ids(self) -> None:
        layouts = load_config()["layouts"]
        layout_ids = [layout["layout_id"] for layout in layouts]

        self.assertEqual(len(layout_ids), 6)
        self.assertEqual(len(set(layout_ids)), 6)
        self.assertEqual(tuple(layout_ids), EXPECTED_LAYOUT_IDS)

    def test_each_layout_has_four_unique_non_magenta_markers(self) -> None:
        for layout in load_config()["layouts"]:
            with self.subTest(layout_id=layout["layout_id"]):
                markers = layout["markers"]
                coordinates = {
                    tuple(marker["world_blocks"][axis] for axis in ("x", "y", "z"))
                    for marker in markers
                }
                self.assertEqual(len(markers), 4)
                self.assertEqual(len({marker["marker_id"] for marker in markers}), 4)
                self.assertEqual(
                    {marker["marker_role"] for marker in markers},
                    set(CANONICAL_MARKER_ROLES),
                )
                self.assertEqual(len(coordinates), 4)
                self.assertNotIn(
                    "magenta",
                    {marker["color"].lower() for marker in markers},
                )
                self.assertTrue(all(marker["intended_visible"] for marker in markers))

    def test_target_and_wall_counts_are_frozen_per_explicit_condition(self) -> None:
        conditions = {
            item["condition"]: item for item in load_config()["conditions"]
        }

        self.assertEqual(set(conditions), set(EXPECTED_CONDITIONS))
        for name, expected in EXPECTED_CONDITIONS.items():
            with self.subTest(condition=name):
                condition = conditions[name]
                self.assertEqual(condition["identity_source"], "explicit_condition_field")
                self.assertNotIn("path", condition)
                self.assertNotIn("folder", condition)
                self.assertEqual(condition["wall_count"], expected["wall_count"])
                self.assertEqual(condition["target_count"], expected["target_count"])
                if expected["target_count"]:
                    self.assertEqual(condition["target"]["entity_type"], "minecraft:sheep")
                    self.assertEqual(condition["target"]["color_id"], 2)
                    self.assertEqual(condition["target"]["color_name"], "magenta")
                else:
                    self.assertIsNone(condition["target"])

    def test_geometry_uses_full_coordinates_and_wall_parallel_axis(self) -> None:
        for layout in load_config()["layouts"]:
            with self.subTest(layout_id=layout["layout_id"]):
                arena = layout["arena"]
                wall = layout["wall"]
                lane = layout["lane"]
                self.assertEqual(arena["max_x"] - arena["min_x"] + 1, 40)
                self.assertEqual(arena["max_z"] - arena["min_z"] + 1, 20)
                self.assertEqual(wall["height_blocks"], 3)
                self.assertEqual(wall["axis"], lane["axis"])
                self.assertEqual(layout["scalar_axis"]["world_axis"], lane["axis"])
                self.assertIn(layout["motion_sign"], (-1, 1))
                for field in ("shadow", "sheep_start_region", "reset_area", "safe_area"):
                    region = layout[field]
                    self.assertLessEqual(arena["min_x"], region["min_x"])
                    self.assertLessEqual(region["max_x"], arena["max_x"])
                    self.assertLessEqual(arena["min_z"], region["min_z"])
                    self.assertLessEqual(region["max_z"], arena["max_z"])

    def test_runtime_evidence_is_not_fabricated(self) -> None:
        for layout in load_config()["layouts"]:
            evidence = layout["runtime_evidence"]
            self.assertEqual(set(evidence), set(RUNTIME_EVIDENCE_FIELDS))
            self.assertTrue(
                all(value == RUNTIME_EVIDENCE_REQUIRED for value in evidence.values())
            )
            for marker in layout["markers"]:
                self.assertEqual(
                    marker["visibility_evidence"],
                    RUNTIME_EVIDENCE_REQUIRED,
                )

    def test_invalid_layout_examples_fail_with_stable_codes(self) -> None:
        mutations = []

        bad_marker_count = deepcopy(load_config())
        bad_marker_count["layouts"][0]["markers"].pop()
        mutations.append((bad_marker_count, LayoutRejectionCode.INVALID_MARKER_COUNT))

        bad_marker_color = deepcopy(load_config())
        bad_marker_color["layouts"][0]["markers"][0]["color"] = "magenta"
        mutations.append((bad_marker_color, LayoutRejectionCode.FORBIDDEN_MARKER_COLOR))

        bad_target_count = deepcopy(load_config())
        bad_target_count["conditions"][0]["target_count"] = 0
        mutations.append((bad_target_count, LayoutRejectionCode.INVALID_TARGET_COUNT))

        bad_layout_id = deepcopy(load_config())
        bad_layout_id["layouts"][0]["layout_id"] = "layout_from_folder_name"
        mutations.append((bad_layout_id, LayoutRejectionCode.INVALID_LAYOUT_ID))

        bad_geometry = deepcopy(load_config())
        bad_geometry["layouts"][0]["arena"]["max_x"] += 1
        mutations.append((bad_geometry, LayoutRejectionCode.INVALID_GEOMETRY))

        inferred_condition = deepcopy(load_config())
        inferred_condition["conditions"][0]["path"] = "core/"
        mutations.append((inferred_condition, LayoutRejectionCode.CONDITION_NOT_EXPLICIT))

        variant_camera_override = deepcopy(load_config())
        variant_camera_override["conditions"][1]["camera"] = {"yaw": 45}
        mutations.append((variant_camera_override, LayoutRejectionCode.INVALID_CONDITION))

        for document, expected_code in mutations:
            with self.subTest(code=expected_code.value):
                result = validate_layout_config(document)
                self.assertFalse(result.accepted)
                self.assertIn(expected_code, rejection_codes(result))

    def test_validation_does_not_mutate_input(self) -> None:
        config = load_config()
        config["layouts"][0]["markers"].pop()
        before = json.dumps(config, sort_keys=True)

        result = validate_layout_config(config)

        self.assertFalse(result.accepted)
        self.assertEqual(before, json.dumps(config, sort_keys=True))

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
        self.assertEqual(missing_units, [])

        legacy = json.loads(LEGACY_SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(legacy["properties"]["layout_schema_version"]["const"], "0.1")

    def test_duplicate_missing_and_unknown_marker_roles_fail_closed(self) -> None:
        for mutation in ("duplicate", "missing", "unknown"):
            with self.subTest(mutation=mutation):
                document = deepcopy(load_config())
                if mutation == "duplicate":
                    document["layouts"][0]["markers"][1]["marker_role"] = "north_west"
                elif mutation == "missing":
                    document["layouts"][0]["markers"][1].pop("marker_role")
                else:
                    document["layouts"][0]["markers"][1]["marker_role"] = "screen_top_right"
                result = validate_layout_config(document)
                self.assertFalse(result.accepted)
                self.assertIn(LayoutRejectionCode.INVALID_GEOMETRY, rejection_codes(result))


if __name__ == "__main__":
    unittest.main()
