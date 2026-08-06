"""Steps 7.4 and 7.7 — run/artifact lineage and the U1-U3 invocation record."""

from __future__ import annotations

import unittest

from mineocclude.experiments.mvp_lineage import (
    AnalysisEntryPoint,
    ArtifactRecord,
    LineageError,
    LineageErrorCode,
    MvpLineage,
    RunIdentity,
    RunRecord,
    build_u1_u3_invocation_record,
    make_artifact_id,
    make_run_id,
)


def _identity(seed=20260725):
    return RunIdentity(
        code_sha="b" * 40,
        git_dirty=False,
        config_snapshot_hash="a" * 64,
        checkpoint_hash="c" * 64,
        data_identity_hash="d" * 64,
        preprocess_hash="e" * 64,
        environment_hash="f" * 64,
        seeds={"extraction": seed},
    )


def _run(lineage, *, stage="model_extraction", attempt=1, parent=None, owner="person_a_model"):
    run_id = make_run_id(
        stage_id=stage,
        config_hash="a" * 64,
        code_sha="b" * 40,
        seed=20260725,
        attempt=attempt,
    )
    lineage.register_run(
        RunRecord(
            run_id=run_id,
            stage_id=stage,
            owner=owner,
            status="in_progress",
            command=("python", "scripts/run_mvp.py", "run"),
            identity=_identity(),
            started_at="2026-08-06T00:00:00Z",
            parent_run_id=parent,
            attempt=attempt,
        )
    )
    return run_id


def _artifact(lineage, run_id, *, sha="1" * 64, artifact_type="activation"):
    record = ArtifactRecord(
        artifact_id=make_artifact_id(
            artifact_type=artifact_type, run_id=run_id, sha256=sha
        ),
        artifact_type=artifact_type,
        creator_run_id=run_id,
        sha256=sha,
        uri=f"s3://mineocclude/{sha[:8]}.json",
        size_bytes=1024,
    )
    return lineage.register_artifact(record)


class IdentityTests(unittest.TestCase):
    def test_run_ids_are_derived_from_what_determines_a_run(self):
        base = dict(
            stage_id="model_extraction",
            config_hash="a" * 64,
            code_sha="b" * 40,
            seed=1,
        )
        self.assertEqual(make_run_id(**base), make_run_id(**base))
        self.assertNotEqual(make_run_id(**base), make_run_id(**{**base, "seed": 2}))
        self.assertNotEqual(
            make_run_id(**base), make_run_id(**base, attempt=2)
        )

    def test_artifact_ids_are_content_addressed(self):
        first = make_artifact_id(artifact_type="activation", run_id="r", sha256="a" * 64)
        second = make_artifact_id(
            artifact_type="activation", run_id="r", sha256="b" * 64
        )
        self.assertNotEqual(first, second)

    def test_a_bare_filename_is_refused_as_artifact_identity(self):
        lineage = MvpLineage(registry_id="r")
        run_id = _run(lineage)
        with self.assertRaises(LineageError) as caught:
            lineage.register_artifact(
                ArtifactRecord(
                    artifact_id="x",
                    artifact_type="activation",
                    creator_run_id=run_id,
                    sha256="1" * 64,
                    uri="index.json",
                    size_bytes=1,
                )
            )
        self.assertIs(caught.exception.code, LineageErrorCode.FILENAME_AS_IDENTITY)

    def test_artifact_type_outside_the_catalog_is_refused(self):
        lineage = MvpLineage(registry_id="r")
        run_id = _run(lineage)
        with self.assertRaises(LineageError) as caught:
            lineage.register_artifact(
                ArtifactRecord(
                    artifact_id="x",
                    artifact_type="invented_type",
                    creator_run_id=run_id,
                    sha256="1" * 64,
                    uri="s3://bucket/x",
                    size_bytes=1,
                )
            )
        self.assertIs(caught.exception.code, LineageErrorCode.UNKNOWN_ARTIFACT_TYPE)


class RetryAndSupersessionTests(unittest.TestCase):
    def test_a_retry_must_name_the_run_it_retries(self):
        lineage = MvpLineage(registry_id="r")
        with self.assertRaises(LineageError) as caught:
            _run(lineage, attempt=2)
        self.assertIs(caught.exception.code, LineageErrorCode.RETRY_WITHOUT_PARENT)

    def test_a_retry_with_a_parent_is_distinguishable_from_a_new_result(self):
        lineage = MvpLineage(registry_id="r")
        first = _run(lineage)
        lineage.fail_run(first, failure_reason="host OOM")
        second = _run(lineage, attempt=2, parent=first)
        document = lineage.runs[second].to_document()
        self.assertTrue(document["is_retry_of_parent"])
        self.assertEqual(document["parent_run_id"], first)

    def test_supersession_preserves_the_superseded_history(self):
        lineage = MvpLineage(registry_id="r")
        first = _run(lineage)
        lineage.complete_run(first, ended_at="2026-08-06T00:01:00Z")
        old_artifact = _artifact(lineage, first, sha="1" * 64)
        second = _run(lineage, attempt=2, parent=first)
        lineage.complete_run(second, ended_at="2026-08-06T00:02:00Z")
        _artifact(lineage, second, sha="2" * 64)

        lineage.supersede_run(first, by_run_id=second, reason="defect correction")

        self.assertEqual(lineage.runs[second].supersedes_run_id, first)
        self.assertEqual(
            lineage.artifacts[old_artifact.artifact_id].status, "superseded"
        )
        self.assertIn(first, lineage.runs)
        self.assertTrue(lineage.to_document()["failed_and_superseded_records_retained"])

    def test_supersession_across_owners_is_refused(self):
        lineage = MvpLineage(registry_id="r")
        first = _run(lineage)
        lineage.complete_run(first, ended_at="2026-08-06T00:01:00Z")
        second = _run(lineage, stage="probes", owner="person_b_analysis")
        lineage.complete_run(second, ended_at="2026-08-06T00:02:00Z")
        with self.assertRaises(LineageError) as caught:
            lineage.supersede_run(first, by_run_id=second, reason="x")
        self.assertIs(caught.exception.code, LineageErrorCode.ILLEGAL_SUPERSESSION)


class TraceTests(unittest.TestCase):
    def test_a_displayed_output_traces_to_inputs_and_execution_identity(self):
        lineage = MvpLineage(registry_id="r")
        upstream = _run(lineage, stage="manifest_validation")
        lineage.complete_run(upstream, ended_at="2026-08-06T00:01:00Z")
        source = _artifact(lineage, upstream, sha="1" * 64, artifact_type="metric_table")

        run_id = make_run_id(
            stage_id="model_extraction",
            config_hash="a" * 64,
            code_sha="b" * 40,
            seed=20260725,
        )
        lineage.register_run(
            RunRecord(
                run_id=run_id,
                stage_id="model_extraction",
                owner="person_a_model",
                status="in_progress",
                command=("python", "scripts/run_mvp.py"),
                identity=_identity(),
                started_at="2026-08-06T00:02:00Z",
                input_artifact_ids=(source.artifact_id,),
                parent_run_id=upstream,
            )
        )
        lineage.complete_run(run_id, ended_at="2026-08-06T00:03:00Z")
        output = _artifact(lineage, run_id, sha="2" * 64)

        trace = lineage.trace(output.artifact_id)
        self.assertEqual(trace["producing_run"]["run_id"], run_id)
        self.assertEqual(
            [item["artifact_id"] for item in trace["direct_input_artifacts"]],
            [source.artifact_id],
        )
        self.assertEqual(len(trace["run_chain"]), 2)
        self.assertTrue(trace["traceable_without_filename"])
        self.assertEqual(trace["producing_run"]["checkpoint_hash"], "c" * 64)

    def test_unknown_artifact_is_refused(self):
        lineage = MvpLineage(registry_id="r")
        with self.assertRaises(LineageError) as caught:
            lineage.trace("nope")
        self.assertIs(caught.exception.code, LineageErrorCode.UNKNOWN_ARTIFACT)


class PersonERegistryTests(unittest.TestCase):
    def test_the_ledger_projects_onto_person_e_schema_and_is_accepted(self):
        lineage = MvpLineage(registry_id="mineocclude-mvp-registry", synthetic=True)
        run_id = _run(lineage)
        lineage.complete_run(run_id, ended_at="2026-08-06T00:01:00Z")
        _artifact(lineage, run_id)

        report = lineage.require_person_e_acceptance()
        self.assertTrue(report["accepted"])
        self.assertEqual(report["run_count"], 1)
        self.assertEqual(report["artifact_count"], 1)

    def test_synthetic_ledgers_forbid_scientific_use(self):
        lineage = MvpLineage(registry_id="r", synthetic=True)
        self.assertEqual(lineage.scientific_use, "forbidden")
        self.assertEqual(
            lineage.to_immutable_registry()["scientific_use"], "forbidden"
        )

    def test_a_rejected_projection_raises_with_the_exact_reasons(self):
        lineage = MvpLineage(registry_id="r")
        with self.assertRaises(LineageError) as caught:
            lineage.require_person_e_acceptance()
        self.assertIs(caught.exception.code, LineageErrorCode.REGISTRY_REJECTED)


class InvocationRecordTests(unittest.TestCase):
    def _entry_points(self):
        return (
            AnalysisEntryPoint(
                owner="person_b_analysis",
                entry_point="scripts/run_person_b_pilot.py",
                command=("python", "scripts/run_person_b_pilot.py"),
                frozen_config_path="configs/analysis/core.yaml",
                frozen_config_sha256="b" * 64,
            ),
        )

    def test_a_blocked_invocation_must_name_its_blocker(self):
        with self.assertRaises(LineageError):
            build_u1_u3_invocation_record(
                run_id="r",
                identity={},
                entry_points=self._entry_points(),
                accepted_manifest_sha256="a" * 64,
                activation_index_sha256=None,
                fold_manifest_sha256="c" * 64,
                fold_count=5,
                accepted_row_count=None,
                exclusion_count=61,
                log_uris=(),
                output_paths=(),
                executed=False,
            )

    def test_a_blocked_invocation_is_recorded_without_implying_a_result(self):
        record = build_u1_u3_invocation_record(
            run_id="r",
            identity={"config_hash": "a" * 64},
            entry_points=self._entry_points(),
            accepted_manifest_sha256="a" * 64,
            activation_index_sha256=None,
            fold_manifest_sha256="c" * 64,
            fold_count=5,
            accepted_row_count=None,
            exclusion_count=61,
            log_uris=(),
            output_paths=(),
            executed=False,
            blocked_reason="the accepted dataset is incomplete",
        )
        self.assertEqual(record["status"], "BLOCKED")
        self.assertFalse(record["metrics_interpreted_by_person_a"])
        self.assertIsNone(record["inputs"]["accepted_row_count"])

    def test_an_executed_invocation_must_name_the_activation_index(self):
        with self.assertRaises(LineageError):
            build_u1_u3_invocation_record(
                run_id="r",
                identity={},
                entry_points=self._entry_points(),
                accepted_manifest_sha256="a" * 64,
                activation_index_sha256=None,
                fold_manifest_sha256="c" * 64,
                fold_count=5,
                accepted_row_count=100,
                exclusion_count=0,
                log_uris=(),
                output_paths=(),
                executed=True,
            )

    def test_an_invocation_requires_at_least_one_entry_point(self):
        with self.assertRaises(LineageError):
            build_u1_u3_invocation_record(
                run_id="r",
                identity={},
                entry_points=(),
                accepted_manifest_sha256="a" * 64,
                activation_index_sha256="d" * 64,
                fold_manifest_sha256="c" * 64,
                fold_count=5,
                accepted_row_count=1,
                exclusion_count=0,
                log_uris=(),
                output_paths=(),
                executed=True,
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
