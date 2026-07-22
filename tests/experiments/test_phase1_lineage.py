from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

from mineocclude.contracts.rollout_registry import (
    validate_immutable_run_artifact_registry,
)
from mineocclude.experiments.figure_inputs import (
    FigureInputError,
    validate_figure_input,
    validate_figure_input_against_registry,
)
from mineocclude.experiments.registry import (
    ProvenanceError,
    formatted_json_bytes,
    hash_json_value,
    trace_phase1_figure_lineage,
)
from tests.fixtures.person_e.build_phase1_fixtures import build_all


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "person_e"


def load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class TestRegistryBackedFigureInputs(unittest.TestCase):
    def test_current_figure_input_passes_and_is_literal_hash_bound(self) -> None:
        figure_input = load_fixture("figure_input_v1.json")
        registry = load_fixture("phase1_trace_registry_v1.json")
        validate_figure_input_against_registry(figure_input, registry)
        artifact = next(
            item
            for item in registry["artifacts"]
            if item["artifact_id"] == "artifact_figure_input"
        )
        payload = formatted_json_bytes(figure_input)
        self.assertEqual(artifact["sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(artifact["size_bytes"], len(payload))

    def test_superseded_source_is_ineligible_but_current_replacement_passes(self) -> None:
        scenarios = load_fixture("figure_supersession_scenarios_v1.json")
        validation = validate_immutable_run_artifact_registry(scenarios["registry"])
        self.assertTrue(validation.accepted, validation.rejections)
        validate_figure_input_against_registry(
            scenarios["current_figure_input"], scenarios["registry"]
        )
        validate_figure_input(scenarios["stale_figure_input"])
        with self.assertRaisesRegex(FigureInputError, "not current"):
            validate_figure_input_against_registry(
                scenarios["stale_figure_input"], scenarios["registry"]
            )

    def test_missing_direct_input_and_identity_mismatch_fail(self) -> None:
        broken_registry = load_fixture(
            "rejected_registry_missing_direct_input_v1.json"
        )
        self.assertFalse(
            validate_immutable_run_artifact_registry(broken_registry).accepted
        )
        with self.assertRaises(ProvenanceError):
            trace_phase1_figure_lineage(
                broken_registry, "artifact_figure_input"
            )
        identity_mismatch = load_fixture(
            "rejected_figure_identity_mismatch_v1.json"
        )
        validate_figure_input(identity_mismatch)
        with self.assertRaisesRegex(FigureInputError, "source_run_id"):
            validate_figure_input_against_registry(
                identity_mismatch,
                load_fixture("phase1_trace_registry_v1.json"),
            )


class TestPhase1LineageTrace(unittest.TestCase):
    def test_complete_trace_matches_saved_evidence(self) -> None:
        registry = load_fixture("phase1_trace_registry_v1.json")
        expected = load_fixture("phase1_lineage_trace_v1.json")
        trace = trace_phase1_figure_lineage(registry, "artifact_figure_input")
        self.assertEqual(trace, expected)
        self.assertEqual(trace["synthetic"], True)
        self.assertEqual(trace["scientific_use"], "forbidden")
        self.assertEqual(
            trace["trace_hash"],
            hash_json_value({key: value for key, value in trace.items() if key != "trace_hash"}),
        )
        self.assertEqual(
            set(trace["phase1_chain_artifact_ids"]),
            {
                "figure_input",
                "metric",
                "prediction_or_baseline",
                "activation_or_oracle",
                "model_input",
                "raw_trajectory",
            },
        )
        self.assertTrue(trace["provenance"]["source_data_identity_hash"])
        self.assertTrue(trace["provenance"]["checkpoint_hashes"])
        self.assertTrue(trace["provenance"]["config_snapshot_hashes"])
        self.assertTrue(trace["provenance"]["code_shas"])
        self.assertTrue(trace["provenance"]["seeds_by_run_id"])

    def test_trace_is_order_independent_and_non_mutating(self) -> None:
        registry = load_fixture("phase1_trace_registry_v1.json")
        original = copy.deepcopy(registry)
        expected = trace_phase1_figure_lineage(registry, "artifact_figure_input")
        self.assertEqual(registry, original)
        registry["runs"].reverse()
        registry["artifacts"].reverse()
        self.assertEqual(
            trace_phase1_figure_lineage(registry, "artifact_figure_input"),
            expected,
        )

    def test_broken_or_ambiguous_lineage_fails_closed(self) -> None:
        registry = load_fixture("phase1_trace_registry_v1.json")
        figure_artifact = next(
            item
            for item in registry["artifacts"]
            if item["artifact_id"] == "artifact_figure_input"
        )
        figure_artifact["direct_input_artifact_ids"].append("artifact_metric")
        figure_run = next(
            item for item in registry["runs"] if item["run_id"] == "run_figure_input"
        )
        figure_run["input_artifact_ids"].append("artifact_metric")
        with self.assertRaises(ProvenanceError):
            trace_phase1_figure_lineage(registry, "artifact_figure_input")

    def test_saved_fixtures_are_deterministically_rebuildable(self) -> None:
        rebuilt = build_all()
        for name, document in rebuilt.items():
            with self.subTest(name=name):
                self.assertEqual(load_fixture(name), document)


if __name__ == "__main__":
    unittest.main()
