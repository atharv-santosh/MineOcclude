from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mineocclude.experiments.registry import (
    ProvenanceError,
    RegistryIndex,
    append_registry_records,
    hash_file_bytes,
    load_json_with_sha256,
    write_json_exclusive,
)


CODE_SHA = "a" * 40
CONFIG_HASH = "b" * 64
MODEL_HASH = "c" * 64
PREPROCESS_HASH = "d" * 64
CONTEXT_HASH = "e" * 64
REQUEST_HASH = "f" * 64
CLIP_HASH = "1" * 64
ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def registry_bundle() -> tuple[dict[str, object], dict[str, object]]:
    root_run = {
        "run_id": "run_inputs",
        "command": ["register-inputs"],
        "owner": "person_a",
        "parent_run_id": None,
        "input_artifact_ids": [],
        "output_artifact_ids": ["context_1", "request_1"],
        "code_sha": CODE_SHA,
        "config_hash": CONFIG_HASH,
        "model_hash": MODEL_HASH,
        "preprocess_hash": PREPROCESS_HASH,
        "execution_status": "completed",
        "failure_reason": None,
    }
    rollout_run = {
        "run_id": "run_rollout",
        "command": ["generate", "--rollout", "rollout_zero"],
        "owner": "person_a",
        "parent_run_id": "run_inputs",
        "input_artifact_ids": ["context_1", "request_1"],
        "output_artifact_ids": ["clip_zero"],
        "code_sha": CODE_SHA,
        "config_hash": CONFIG_HASH,
        "model_hash": MODEL_HASH,
        "preprocess_hash": PREPROCESS_HASH,
        "execution_status": "completed",
        "failure_reason": None,
    }

    def artifact(
        artifact_id: str,
        artifact_type: str,
        sha256: str,
        producer_run_id: str,
        uri: str,
    ) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "uri": uri,
            "sha256": sha256,
            "producer_run_id": producer_run_id,
            "status": "accepted",
            "exclusion_reason": None,
            "superseded_by": None,
        }

    registry = {
        "schema_version": "1.0",
        "registry_id": "registry_1",
        "handoff_id": "handoff_1",
        "runs": [root_run, rollout_run],
        "artifacts": [
            artifact(
                "context_1",
                "input_context",
                CONTEXT_HASH,
                "run_inputs",
                "memory://inputs/context_1",
            ),
            artifact(
                "request_1",
                "intervention_request",
                REQUEST_HASH,
                "run_inputs",
                "memory://inputs/request_1",
            ),
            artifact(
                "clip_zero",
                "rollout_clip",
                CLIP_HASH,
                "run_rollout",
                "memory://rollouts/clip_zero",
            ),
        ],
    }
    rollout = {
        "schema_version": "1.0",
        "rollout_id": "rollout_zero",
        "event_id": "event_1",
        "episode_id": "episode_1",
        "trajectory_id": "trajectory_1",
        "server_tick": 10,
        "render_frame_idx": 10,
        "action_idx": 10,
        "layout_id": "layout_1",
        "model_frame_idx": 10,
        "regime": "A",
        "visibility": "occluded",
        "tau": 0.5,
        "v": 1.0,
        "q": 0.05,
        "duration": 1.0,
        "seed": 7,
        "dose_id": "dose_zero",
        "alpha_requested": 0.0,
        "alpha_applied": 0.0,
        "cap_reduced": False,
        "intended_block_shift": 0.0,
        "direction_version": "direction_v1",
        "layer_idx": 3,
        "hook_site": "decoder_output",
        "timestep_idx": 15,
        "control_type": "alpha_zero",
        "input_context_id": "input_context_1",
        "input_context_artifact_id": "context_1",
        "input_context_hash": CONTEXT_HASH,
        "intervention_request_artifact_id": "request_1",
        "output_artifact_id": "clip_zero",
        "output_uri": "memory://rollouts/clip_zero",
        "output_hash": CLIP_HASH,
        "code_sha": CODE_SHA,
        "model_hash": MODEL_HASH,
        "config_hash": CONFIG_HASH,
        "preprocess_hash": PREPROCESS_HASH,
        "run_id": "run_rollout",
        "outcome": "measurable_continuation",
        "outcome_detail": None,
        "measurable": True,
        "status": "accepted",
        "exclusion_reason": None,
        "superseded_by": None,
    }
    manifest = {
        "schema_version": "1.0",
        "manifest_id": "manifest_1",
        "handoff_id": "handoff_1",
        "rollout_rows": [rollout],
    }
    return manifest, registry


def registry_bundle_with_invalid_source() -> tuple[
    dict[str, object], dict[str, object]
]:
    manifest, registry = registry_bundle()
    registry["runs"].extend(
        [
            {
                "run_id": "run_bad_source",
                "command": ["produce-known-bad-source"],
                "owner": "person_e",
                "parent_run_id": None,
                "input_artifact_ids": [],
                "output_artifact_ids": ["bad_source"],
                "code_sha": CODE_SHA,
                "config_hash": CONFIG_HASH,
                "model_hash": MODEL_HASH,
                "preprocess_hash": PREPROCESS_HASH,
                "execution_status": "completed",
                "failure_reason": None,
            },
            {
                "run_id": "run_derived",
                "command": ["derive-from-known-bad-source"],
                "owner": "person_e",
                "parent_run_id": "run_bad_source",
                "input_artifact_ids": ["bad_source"],
                "output_artifact_ids": ["derived_log"],
                "code_sha": CODE_SHA,
                "config_hash": CONFIG_HASH,
                "model_hash": MODEL_HASH,
                "preprocess_hash": PREPROCESS_HASH,
                "execution_status": "completed",
                "failure_reason": None,
            },
        ]
    )
    registry["artifacts"].extend(
        [
            {
                "schema_version": "1.0",
                "artifact_id": "bad_source",
                "artifact_type": "diagnostic_log",
                "uri": "memory://diagnostics/bad_source",
                "sha256": "2" * 64,
                "producer_run_id": "run_bad_source",
                "status": "excluded",
                "exclusion_reason": "known invalid source",
                "superseded_by": None,
            },
            {
                "schema_version": "1.0",
                "artifact_id": "derived_log",
                "artifact_type": "diagnostic_log",
                "uri": "memory://diagnostics/derived_log",
                "sha256": "3" * 64,
                "producer_run_id": "run_derived",
                "status": "accepted",
                "exclusion_reason": None,
                "superseded_by": None,
            },
        ]
    )
    return manifest, registry


class TestRegistryIndex(unittest.TestCase):
    def test_completed_run_lookup_binds_owner_and_config(self) -> None:
        manifest, registry = registry_bundle()
        index = RegistryIndex(manifest, registry)
        run = index.require_completed_run(
            "run_rollout",
            owner="person_a",
            config_hash=CONFIG_HASH,
        )
        self.assertEqual(run["run_id"], "run_rollout")
        with self.assertRaises(ProvenanceError):
            index.require_completed_run(
                "run_rollout",
                owner="person_e",
                config_hash=CONFIG_HASH,
            )

    def test_trace_and_index_use_explicit_lineage(self) -> None:
        manifest, registry = registry_bundle()
        index = RegistryIndex(manifest, registry)
        report = index.provenance_report("rollout_zero")
        self.assertEqual(report["subject_type"], "rollout")
        output_trace = report["trace"]["referenced_artifacts"][
            "output_artifact_id"
        ]
        self.assertEqual(output_trace["artifact"]["artifact_id"], "clip_zero")
        self.assertEqual(
            [run["run_id"] for run in output_trace["producer_to_root_run_chain"]],
            ["run_rollout", "run_inputs"],
        )
        self.assertEqual(
            {item["artifact"]["artifact_id"] for item in output_trace["direct_inputs"]},
            {"context_1", "request_1"},
        )
        rows = index.artifact_index()
        self.assertEqual([row["artifact_id"] for row in rows], sorted(
            row["artifact_id"] for row in rows
        ))
        clip = next(row for row in rows if row["artifact_id"] == "clip_zero")
        self.assertEqual(clip["artifact_uri"], "memory://rollouts/clip_zero")
        self.assertEqual(clip["run_command"], ["generate", "--rollout", "rollout_zero"])
        self.assertEqual(clip["referenced_by_rollout_ids"], ["rollout_zero"])
        self.assertEqual(clip["rollout_references"][0]["seed"], 7)
        self.assertTrue(clip["is_current"])
        self.assertTrue(clip["claim_eligible"])

        qa = index.provenance_qa_report()
        self.assertEqual(qa["summary"]["artifact_count"], 3)
        self.assertEqual(qa["summary"]["lifecycle_counts"]["accepted"], 3)
        self.assertEqual(qa["current_claim_ineligible_artifact_ids"], [])

    def test_qa_flags_transitive_invalid_sources(self) -> None:
        manifest, registry = registry_bundle_with_invalid_source()
        index = RegistryIndex(manifest, registry)
        derived = next(
            row
            for row in index.artifact_index()
            if row["artifact_id"] == "derived_log"
        )
        self.assertTrue(derived["is_current"])
        self.assertFalse(derived["claim_eligible"])
        self.assertTrue(derived["transitive_invalid_source"])
        self.assertEqual(derived["invalid_source_artifact_ids"], ["bad_source"])
        qa = index.provenance_qa_report()
        self.assertIn("derived_log", qa["current_claim_ineligible_artifact_ids"])
        self.assertEqual(
            qa["summary"]["transitive_invalid_source_artifact_count"], 1
        )

    def test_ambiguous_subject_requires_explicit_type(self) -> None:
        manifest, registry = registry_bundle()
        for artifact in registry["artifacts"]:
            if artifact["artifact_id"] == "context_1":
                artifact["artifact_id"] = "rollout_zero"
        for run in registry["runs"]:
            run["input_artifact_ids"] = [
                "rollout_zero" if value == "context_1" else value
                for value in run["input_artifact_ids"]
            ]
            run["output_artifact_ids"] = [
                "rollout_zero" if value == "context_1" else value
                for value in run["output_artifact_ids"]
            ]
        manifest["rollout_rows"][0]["input_context_artifact_id"] = "rollout_zero"
        index = RegistryIndex(manifest, registry)
        with self.assertRaisesRegex(ProvenanceError, "provide subject_type"):
            index.provenance_report("rollout_zero")
        self.assertEqual(
            index.provenance_report(
                "rollout_zero", subject_type="artifact"
            )["subject_type"],
            "artifact",
        )
        self.assertEqual(
            index.provenance_report(
                "rollout_zero", subject_type="rollout"
            )["subject_type"],
            "rollout",
        )

    def test_invalid_bundle_is_rejected_without_mutation(self) -> None:
        manifest, registry = registry_bundle()
        original = copy.deepcopy(registry)
        registry["artifacts"][2]["sha256"] = "0" * 64
        with self.assertRaises(ProvenanceError):
            RegistryIndex(manifest, registry)
        self.assertNotEqual(registry, original)
        clean_manifest, clean_registry = registry_bundle()
        updated = append_registry_records(clean_manifest, clean_registry)
        self.assertEqual(updated, clean_registry)
        self.assertIsNot(updated, clean_registry)

    def test_exclusive_writer_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "report.json"
            write_json_exclusive(path, {"value": 1})
            first_hash = hash_file_bytes(path)
            with self.assertRaises(ProvenanceError):
                write_json_exclusive(path, {"value": 2})
            self.assertEqual(hash_file_bytes(path), first_hash)
            self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])

    def test_one_read_loader_hashes_the_exact_parsed_bytes(self) -> None:
        payload = b'{\r\n  "value": 1\r\n}\r\n'
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "input.json"
            path.write_bytes(payload)
            document, digest = load_json_with_sha256(path)
            self.assertEqual(document, {"value": 1})
            self.assertEqual(digest, hashlib.sha256(payload).hexdigest())
            self.assertEqual(hash_file_bytes(path), digest)

    def test_artifact_index_cli_emits_lifecycle_qa(self) -> None:
        manifest, registry = registry_bundle_with_invalid_source()
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            manifest_path = temporary / "manifest.json"
            registry_path = temporary / "registry.json"
            output_path = temporary / "artifact_index.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            registry_path.write_text(json.dumps(registry), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "build_artifact_index.py"),
                    str(manifest_path),
                    str(registry_path),
                    str(output_path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            output = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertIn("provenance_qa", output)
            self.assertIn(
                "derived_log",
                output["provenance_qa"][
                    "current_claim_ineligible_artifact_ids"
                ],
            )


if __name__ == "__main__":
    unittest.main()
