"""Step 7.1 — the frozen MVP configuration identity cannot drift silently."""

from __future__ import annotations

import copy
import unittest
from pathlib import Path

import yaml

from mineocclude.activations.hooks import HOOK_DISCOVERY_VERSION
from mineocclude.contracts.activation import (
    MAX_MODEL_FRAMES,
    TOKENS_PER_FRAME_ACTION_PAIR,
    VISUAL_TOKENS_PER_FRAME,
)
from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.experiments.mvp_config import (
    MVP_CONFIG_ID,
    OPERATIONAL_PATHS,
    RESULT_CHANGING_PATHS,
    MvpConfigError,
    MvpConfigErrorCode,
    build_freeze_record,
    compare_configs,
    config_hash,
    load_mvp_config,
    validate_mvp_config,
)

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "configs" / "experiments" / "mvp.yaml"


def _document() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


class RepositoryConfigTests(unittest.TestCase):
    def test_repository_config_loads_and_validates(self):
        config = load_mvp_config(CONFIG_PATH)
        self.assertEqual(config.config_id, MVP_CONFIG_ID)
        self.assertEqual(config.expected_cell_count, 66)
        self.assertEqual(config.extraction_seed, 20260725)

    def test_identity_is_content_addressed_and_portable(self):
        config = load_mvp_config(CONFIG_PATH)
        identity = config.identity()
        self.assertEqual(identity["schema_version"], SCHEMA_VERSION)
        self.assertEqual(len(identity["config_hash"]), 64)
        self.assertEqual(len(identity["config_file_sha256"]), 64)
        self.assertEqual(identity["config_path"], "configs/experiments/mvp.yaml")

    def test_config_agrees_with_the_frozen_token_contracts(self):
        config = load_mvp_config(CONFIG_PATH)
        self.assertEqual(
            config.get("tokens.visual_tokens_per_frame"), VISUAL_TOKENS_PER_FRAME
        )
        self.assertEqual(
            config.get("tokens.tokens_per_frame_action_pair"),
            TOKENS_PER_FRAME_ACTION_PAIR,
        )
        self.assertEqual(
            config.get("tokens.max_model_frames_per_context"), MAX_MODEL_FRAMES
        )
        self.assertEqual(
            config.get("extraction.hook_discovery_version"), HOOK_DISCOVERY_VERSION
        )

    def test_frozen_step_4_1_decision_remains_fail(self):
        config = load_mvp_config(CONFIG_PATH)
        self.assertEqual(config.get("frozen_decisions.step_4_1_decision"), "FAIL")
        self.assertFalse(config.get("frozen_decisions.step_4_1_rerun_authorized"))

    def test_u4_matrix_arithmetic_is_encoded_not_asserted(self):
        config = load_mvp_config(CONFIG_PATH)
        events = config.get("u4_pilot.heldout_event_count")
        shifts = config.get("u4_pilot.intended_block_shifts")
        seeds = config.get("u4_pilot.seeds_per_cell")
        self.assertEqual(
            events * len(shifts) * seeds, config.get("u4_pilot.primary_clip_count")
        )


class RejectionTests(unittest.TestCase):
    def test_missing_file_is_rejected(self):
        with self.assertRaises(MvpConfigError) as caught:
            load_mvp_config(ROOT / "configs" / "experiments" / "absent.yaml")
        self.assertIs(caught.exception.code, MvpConfigErrorCode.MISSING_FILE)

    def test_unfrozen_config_is_rejected(self):
        document = _document()
        document["frozen"] = False
        with self.assertRaises(MvpConfigError) as caught:
            validate_mvp_config(document)
        self.assertIs(caught.exception.code, MvpConfigErrorCode.NOT_FROZEN)

    def test_moved_step_4_1_decision_is_rejected(self):
        document = _document()
        document["frozen_decisions"]["step_4_1_decision"] = "PASS"
        with self.assertRaises(MvpConfigError) as caught:
            validate_mvp_config(document)
        self.assertIs(
            caught.exception.code, MvpConfigErrorCode.FROZEN_DECISION_MOVED
        )

    def test_contract_disagreement_is_rejected(self):
        document = _document()
        document["tokens"]["visual_tokens_per_frame"] = 128
        with self.assertRaises(MvpConfigError) as caught:
            validate_mvp_config(document)
        self.assertIs(
            caught.exception.code, MvpConfigErrorCode.CONTRACT_DISAGREEMENT
        )

    def test_matrix_group_arithmetic_is_enforced(self):
        document = _document()
        document["matrix"]["core_regime_a_cells"] = 40
        with self.assertRaises(MvpConfigError) as caught:
            validate_mvp_config(document)
        self.assertIs(
            caught.exception.code, MvpConfigErrorCode.CONTRACT_DISAGREEMENT
        )

    def test_missing_section_is_rejected(self):
        document = _document()
        del document["queue"]
        with self.assertRaises(MvpConfigError) as caught:
            validate_mvp_config(document)
        self.assertIs(caught.exception.code, MvpConfigErrorCode.MISSING_SECTION)


class ChangeClassificationTests(unittest.TestCase):
    def test_identical_configs_compare_equal(self):
        document = _document()
        report = compare_configs(document, copy.deepcopy(document))
        self.assertTrue(report["identical"])
        self.assertFalse(report["requires_new_run_identity"])

    def test_result_changing_edit_requires_a_new_run_identity(self):
        baseline = _document()
        candidate = copy.deepcopy(baseline)
        candidate["seeds"]["extraction_seed"] = 1
        report = compare_configs(baseline, candidate)
        self.assertTrue(report["requires_new_run_identity"])
        self.assertTrue(report["requires_dated_decision_record"])
        self.assertEqual(len(report["result_changing_differences"]), 1)

    def test_operational_edit_does_not_require_a_new_run_identity(self):
        baseline = _document()
        candidate = copy.deepcopy(baseline)
        candidate["queue"]["max_transient_retries"] = 9
        report = compare_configs(baseline, candidate)
        self.assertFalse(report["requires_new_run_identity"])
        self.assertEqual(len(report["operational_differences"]), 1)

    def test_unclassified_edit_is_surfaced_not_waved_through(self):
        baseline = _document()
        candidate = copy.deepcopy(baseline)
        candidate["freeze_date"] = "2099-01-01"
        report = compare_configs(baseline, candidate)
        self.assertTrue(report["unclassified_differences"])
        self.assertTrue(report["requires_new_run_identity"])

    def test_every_declared_path_is_readable(self):
        document = _document()
        report = compare_configs(document, document)
        self.assertEqual(report["result_changing_differences"], [])
        self.assertEqual(report["operational_differences"], [])
        self.assertEqual(
            len(set(RESULT_CHANGING_PATHS) & set(OPERATIONAL_PATHS)), 0
        )


class FreezeRecordTests(unittest.TestCase):
    def test_freeze_record_lists_every_classified_path(self):
        config = load_mvp_config(CONFIG_PATH)
        record = build_freeze_record(
            config, code_sha="a" * 40, signed_by=("person_a_model",)
        )
        self.assertEqual(record["status"], "FROZEN")
        self.assertEqual(
            record["result_changing_paths"], list(RESULT_CHANGING_PATHS)
        )
        self.assertEqual(record["operational_paths"], list(OPERATIONAL_PATHS))
        self.assertEqual(record["frozen_step_4_1_decision"], "FAIL")

    def test_freeze_record_requires_a_validating_role(self):
        config = load_mvp_config(CONFIG_PATH)
        with self.assertRaises(MvpConfigError):
            build_freeze_record(config, code_sha="a" * 40, signed_by=())

    def test_config_hash_is_order_independent(self):
        document = _document()
        reordered = dict(reversed(list(document.items())))
        self.assertEqual(config_hash(document), config_hash(reordered))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
