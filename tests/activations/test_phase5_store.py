"""Focused CPU tests for the immutable Phase 5 pooled activation store."""

from __future__ import annotations

import copy
import errno
import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

import numpy

import mineocclude.activations.store as store_module
from mineocclude.activations.store import (
    ACTIVATION_ELIGIBILITY_METADATA_FIELDS,
    ActivationEligibilityProof,
    ActivationPublicationFaultPoint,
    ActivationRowKey,
    ActivationStoreError,
    ActivationStoreErrorCode,
    ActivationStoreIdentity,
    audit_activation_store,
    build_activation_eligibility_proof,
    load_activation_index_snapshot,
    plan_activation_resume,
    publish_activation_chunk,
    read_activation_vectors,
    validate_activation_index_snapshot,
)

FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures"
    / "activation"
    / "accepted_activation_handoff.json"
)
BENCHMARK_SCRIPT = (
    Path(__file__).parents[2]
    / "scripts"
    / "benchmark_phase5_activation_store.py"
)
CHECKED_EXAMPLE = (
    Path(__file__).parents[2]
    / "docs"
    / "status"
    / "fixtures"
    / "phase5_activation_store_example"
)
CREATED = "2026-07-27T00:00:00Z"
WIDTH = 2048


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _identity(*, dtype: str = "float32", code_sha: str | None = None):
    document = _fixture()
    row = document["index_rows"][0]
    return ActivationStoreIdentity(
        schema_version="1.0",
        run_id=document["run_id"],
        checkpoint_hash=document["checkpoint_hash"],
        model_hash=document["checkpoint_hash"],
        config_hash=row["config_hash"],
        preprocess_hash=document["preprocess_hash"],
        accepted_manifest_hash=document["accepted_manifest_hash"],
        code_sha=code_sha or row["code_sha"],
        hook_site=row["hook_site"],
        requested_layers=(5, 12),
        dtype=dtype,
        hidden_width=WIDTH,
    )


def _rows(layer: int) -> list[dict]:
    document = _fixture()
    return [
        copy.deepcopy(row)
        for row in document["index_rows"]
        if row["layer_idx"] == layer
    ]


def _vectors(layer: int, *, dtype: str = "float32") -> numpy.ndarray:
    values = numpy.arange(3 * WIDTH, dtype=numpy.float32).reshape(3, WIDTH)
    return (values + layer).astype(dtype)


def _rows_for_identity(
    layer: int,
    identity: ActivationStoreIdentity,
) -> list[dict]:
    rows = _rows(layer)
    for row in rows:
        row.update(
            {
                "accepted_manifest_hash": identity.accepted_manifest_hash,
                "checkpoint_hash": identity.checkpoint_hash,
                "code_sha": identity.code_sha,
                "config_hash": identity.config_hash,
                "hook_site": identity.hook_site,
                "model_hash": identity.model_hash,
                "preprocess_hash": identity.preprocess_hash,
                "run_id": identity.run_id,
                "schema_version": identity.schema_version,
            }
        )
    return rows


def _benchmark_module():
    spec = importlib.util.spec_from_file_location(
        "phase5_benchmark_for_tests",
        BENCHMARK_SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("could not load benchmark module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _publish(
    root: str | Path,
    *,
    layer: int = 5,
    identity: ActivationStoreIdentity | None = None,
    prior=None,
    rows: list[dict] | None = None,
    vectors: numpy.ndarray | None = None,
    eligibility_rows: list[dict] | None = None,
    claimed_proof=...,
    fault_point: ActivationPublicationFaultPoint | None = None,
):
    identity = identity or _identity()
    authority_rows = (
        eligibility_rows
        if eligibility_rows is not None
        else _manifest_rows(identity)
    )
    honest_proof = build_activation_eligibility_proof(
        store_identity=identity,
        accepted_manifest_rows=authority_rows,
    )
    proof = honest_proof if claimed_proof is ... else claimed_proof
    return publish_activation_chunk(
        store_root=root,
        store_identity=identity,
        accepted_manifest_rows=authority_rows,
        eligibility_proof=proof,
        rows=rows or _rows(layer),
        vectors=vectors if vectors is not None else _vectors(layer),
        creation_timestamp=CREATED,
        prior_snapshot=prior,
        fault_point=fault_point,
    )


def _full_snapshot(root: str | Path):
    first = _publish(root, layer=5)
    return _publish(root, layer=12, prior=first)


def _manifest_rows(
    identity: ActivationStoreIdentity | None = None,
) -> list[dict]:
    identity = identity or _identity()
    rows = _rows(5)
    for row in rows:
        row.pop("layer_idx")
        row.pop("hook_site")
        row.update(
            {
                "accepted_manifest_hash": identity.accepted_manifest_hash,
                "checkpoint_hash": identity.checkpoint_hash,
                "code_sha": identity.code_sha,
                "config_hash": identity.config_hash,
                "model_hash": identity.model_hash,
                "preprocess_hash": identity.preprocess_hash,
                "run_id": identity.run_id,
                "schema_version": identity.schema_version,
            }
        )
    return rows


def _resign(snapshot, *, rows=None, chunks=None):
    prototype = replace(
        snapshot,
        snapshot_id="0" * 64,
        index_rows=tuple(rows if rows is not None else snapshot.index_rows),
        chunks=tuple(chunks if chunks is not None else snapshot.chunks),
    )
    return replace(
        prototype,
        snapshot_id=store_module._canonical_digest(
            store_module._snapshot_identity_document(prototype)
        ),
    )


def _unsafe_frozen_replace(value, **changes):
    copied = copy.copy(value)
    for field, replacement in changes.items():
        object.__setattr__(copied, field, replacement)
    return copied


def _symlink_or_skip(test: unittest.TestCase, target: Path, link: Path):
    try:
        os.symlink(target, link, target_is_directory=target.is_dir())
    except NotImplementedError as error:
        test.skipTest(f"symbolic links are unavailable: {error}")
    except OSError as error:
        if error.errno in {errno.EACCES, errno.EPERM, errno.ENOSYS} or getattr(
            error, "winerror", None
        ) == 1314:
            test.skipTest(
                "symbolic-link creation lacks platform privilege: "
                f"{type(error).__name__}: {error}"
            )
        raise


def _resume_expected(snapshot) -> dict[ActivationRowKey, dict]:
    return {
        ActivationRowKey.from_row(row): {
            **store_module._thaw_json(row),
            "operational_status": "completed",
        }
        for row in snapshot.index_rows
    }


class TestPhase5IdentitiesAndPublication(unittest.TestCase):
    def test_identity_levels_are_deterministic_and_changes_are_distinct(self):
        identity = _identity()
        self.assertEqual(identity.digest, _identity().digest)
        changed = _identity(code_sha="f" * 40)
        self.assertNotEqual(identity.digest, changed.digest)
        row = ActivationRowKey.from_row(_rows(5)[0])
        self.assertEqual(row.digest, ActivationRowKey.from_row(_rows(5)[0]).digest)

    def test_bfloat16_is_rejected_without_reinterpretation(self):
        with self.assertRaises(ActivationStoreError) as captured:
            _identity(dtype="bfloat16")
        self.assertEqual(
            captured.exception.code,
            ActivationStoreErrorCode.UNSUPPORTED_DTYPE,
        )

    def test_publish_load_read_and_canonical_order(self):
        with tempfile.TemporaryDirectory() as directory:
            rows = list(reversed(_rows(5)))
            vectors = numpy.flip(_vectors(5), axis=0).copy()
            snapshot = _publish(directory, rows=rows, vectors=vectors)
            self.assertEqual(
                list(snapshot.index_rows),
                sorted(snapshot.index_rows, key=ActivationRowKey.from_row),
            )
            path = Path(directory) / snapshot.relative_path
            loaded = load_activation_index_snapshot(path, store_root=directory)
            self.assertEqual(snapshot, loaded)
            keys = tuple(
                ActivationRowKey.from_row(row) for row in loaded.index_rows
            )
            observed = read_activation_vectors(
                store_root=directory,
                snapshot=loaded,
                row_keys=keys,
            )
            numpy.testing.assert_array_equal(observed, _vectors(5))
            self.assertEqual(observed.dtype.name, "float32")
            self.assertEqual(
                path.read_bytes(),
                store_module._canonical_json_bytes(snapshot.to_document()),
            )

    def test_float16_selective_read_promotes_and_avoids_unrelated_chunk(self):
        identity = _identity(dtype="float16")
        with tempfile.TemporaryDirectory() as directory:
            first = _publish(
                directory,
                identity=identity,
                vectors=_vectors(5, dtype="float16"),
            )
            snapshot = _publish(
                directory,
                layer=12,
                identity=identity,
                vectors=_vectors(12, dtype="float16"),
                prior=first,
            )
            key = ActivationRowKey.from_row(snapshot.index_rows[0])
            real_load = numpy.load
            opened: list[str] = []

            def tracking_load(path, *args, **kwargs):
                opened.append(str(path))
                return real_load(path, *args, **kwargs)

            with mock.patch.object(numpy, "load", side_effect=tracking_load):
                values = read_activation_vectors(
                    store_root=directory,
                    snapshot=snapshot,
                    row_keys=(key,),
                )
            self.assertEqual(values.dtype.name, "float32")
            self.assertTrue(opened)
            self.assertTrue(
                all(snapshot.index_rows[0]["activation_chunk_id"] in path for path in opened)
            )

    def test_invalid_rows_arrays_and_paths_fail_closed(self):
        cases = []
        duplicate_rows = _rows(5)
        duplicate_rows[1] = copy.deepcopy(duplicate_rows[0])
        cases.append(("duplicate", duplicate_rows, _vectors(5), None))
        cases.append(
            (
                "rank",
                _rows(5),
                numpy.zeros(3 * WIDTH, dtype=numpy.float32),
                None,
            )
        )
        cases.append(
            (
                "object",
                _rows(5),
                numpy.full((3, WIDTH), object(), dtype=object),
                None,
            )
        )
        cases.append(
            (
                "dtype",
                _rows(5),
                numpy.zeros((3, WIDTH), dtype=numpy.float16),
                None,
            )
        )
        for label, rows, vectors, _unused in cases:
            with (
                self.subTest(label=label),
                tempfile.TemporaryDirectory() as root,
                self.assertRaises(ActivationStoreError),
            ):
                _publish(root, rows=rows, vectors=vectors)
        with self.assertRaises(ActivationStoreError):
            store_module._safe_store_relative_path("../escape.npy", "path")
        with self.assertRaises(ActivationStoreError):
            store_module._safe_store_relative_path("C:/escape.npy", "path")

    def test_forced_interruptions_cleanup_and_visibility(self):
        for fault in ActivationPublicationFaultPoint:
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as root:
                with self.assertRaises(ActivationStoreError):
                    _publish(root, fault_point=fault)
                temporary = list(Path(root).rglob("*.tmp"))
                self.assertEqual(temporary, [])
                indexes = list((Path(root) / "indexes").glob("*.json"))
                chunks = list((Path(root) / "chunks").glob("*.npy"))
                if fault == ActivationPublicationFaultPoint.AFTER_INDEX_PUBLICATION:
                    self.assertEqual(len(indexes), 1)
                    load_activation_index_snapshot(indexes[0], store_root=root)
                else:
                    self.assertEqual(indexes, [])
                if fault in {
                    ActivationPublicationFaultPoint.AFTER_FINAL_CHUNK_PUBLICATION,
                    ActivationPublicationFaultPoint.AFTER_INDEX_CONSTRUCTION,
                    ActivationPublicationFaultPoint.DURING_INDEX_PUBLICATION,
                }:
                    self.assertEqual(len(chunks), 1)

    def test_orphan_reuse_and_conflicting_orphan_rejection(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ActivationStoreError):
                _publish(
                    root,
                    fault_point=(
                        ActivationPublicationFaultPoint.AFTER_FINAL_CHUNK_PUBLICATION
                    ),
                )
            orphan = next((Path(root) / "chunks").glob("*.npy"))
            original = orphan.read_bytes()
            snapshot = _publish(root)
            self.assertEqual(orphan.read_bytes(), original)
            self.assertEqual(len(snapshot.index_rows), 3)
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ActivationStoreError):
                _publish(
                    root,
                    fault_point=(
                        ActivationPublicationFaultPoint.AFTER_FINAL_CHUNK_PUBLICATION
                    ),
                )
            orphan = next((Path(root) / "chunks").glob("*.npy"))
            payload = bytearray(orphan.read_bytes())
            payload[-1] ^= 1
            orphan.write_bytes(payload)
            with self.assertRaises(ActivationStoreError) as captured:
                _publish(root)
            self.assertEqual(
                captured.exception.code,
                ActivationStoreErrorCode.IDENTITY_CONFLICT,
            )

    def test_completed_overwrite_and_prior_files_are_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            snapshot = _publish(root)
            chunk = Path(root) / snapshot.chunks[0].relative_path
            index = Path(root) / snapshot.relative_path
            before = (chunk.read_bytes(), index.read_bytes())
            with self.assertRaises(ActivationStoreError):
                _publish(root, prior=snapshot)
            self.assertEqual(before, (chunk.read_bytes(), index.read_bytes()))


class TestPhase5ResumeAuditAndIntegrity(unittest.TestCase):
    def test_resume_is_idempotent_and_classifies_retry_conflict_exclusion(self):
        with tempfile.TemporaryDirectory() as root:
            snapshot = _publish(root)
            stored_keys = [
                ActivationRowKey.from_row(row) for row in snapshot.index_rows
            ]
            missing = ActivationRowKey(
                "missing-trajectory",
                0,
                5,
                snapshot.store_identity.hook_site,
                snapshot.store_identity.run_id,
            )
            excluded = ActivationRowKey(
                "excluded-trajectory",
                0,
                5,
                snapshot.store_identity.hook_site,
                snapshot.store_identity.run_id,
            )
            expected = {}
            for row, key in zip(snapshot.index_rows, stored_keys, strict=True):
                expected[key] = {
                    **dict(row),
                    "operational_status": "completed",
                }
            missing_metadata = {
                **dict(snapshot.index_rows[0]),
                **missing.to_document(),
                "run_id": missing.producing_run_id,
                "status": "accepted",
                "operational_status": "failed",
            }
            missing_metadata.pop("producing_run_id")
            expected[missing] = missing_metadata
            excluded_metadata = {
                **dict(snapshot.index_rows[0]),
                **excluded.to_document(),
                "run_id": excluded.producing_run_id,
                "status": "excluded",
                "exclusion_reason": "controlled exclusion",
                "operational_status": "completed",
            }
            excluded_metadata.pop("producing_run_id")
            expected[excluded] = excluded_metadata
            plan = plan_activation_resume(
                store_root=root,
                requested_identity=snapshot.store_identity,
                snapshot=snapshot,
                expected_rows=expected,
            )
            self.assertEqual(plan.skip, tuple(stored_keys))
            self.assertEqual(plan.retry, (missing,))
            self.assertEqual(plan.excluded, (excluded,))
            self.assertEqual(
                plan,
                plan_activation_resume(
                    store_root=root,
                    requested_identity=snapshot.store_identity,
                    snapshot=snapshot,
                    expected_rows=expected,
                ),
            )
            with self.assertRaises(ActivationStoreError):
                plan_activation_resume(
                    store_root=root,
                    requested_identity=_identity(code_sha="f" * 40),
                    snapshot=snapshot,
                    expected_rows=expected,
                )

    def test_interrupted_resume_matches_uninterrupted_reference(self):
        with tempfile.TemporaryDirectory() as interrupted, tempfile.TemporaryDirectory() as reference:
            first = _publish(interrupted)
            resumed = _publish(interrupted, layer=12, prior=first)
            reference_snapshot = _full_snapshot(reference)
            self.assertEqual(
                [ActivationRowKey.from_row(row) for row in resumed.index_rows],
                [
                    ActivationRowKey.from_row(row)
                    for row in reference_snapshot.index_rows
                ],
            )
            numpy.testing.assert_array_equal(
                read_activation_vectors(
                    store_root=interrupted,
                    snapshot=resumed,
                    row_keys=tuple(
                        ActivationRowKey.from_row(row)
                        for row in resumed.index_rows
                    ),
                ),
                read_activation_vectors(
                    store_root=reference,
                    snapshot=reference_snapshot,
                    row_keys=tuple(
                        ActivationRowKey.from_row(row)
                        for row in reference_snapshot.index_rows
                    ),
                ),
            )
            self.assertEqual(resumed.snapshot_id, reference_snapshot.snapshot_id)
            self.assertEqual(
                [chunk.sha256 for chunk in resumed.chunks],
                [chunk.sha256 for chunk in reference_snapshot.chunks],
            )

    def test_audit_uses_post_first_visible_authority_and_reports_states(self):
        with tempfile.TemporaryDirectory() as root:
            snapshot = _full_snapshot(root)
            manifest = _manifest_rows()
            manifest[0]["visibility"] = "occluded"
            manifest[1]["visibility"] = "visible"
            pending = dict(snapshot.index_rows[0])
            pending["trajectory_id"] = "pending-trajectory"
            pending["operational_status"] = "pending"
            pending["state_reason"] = "not yet extracted"
            audit = audit_activation_store(
                store_root=root,
                snapshot=snapshot,
                accepted_manifest_rows=manifest,
                work_records=(pending,),
            )
            self.assertEqual(len(audit.expected_keys), 4)
            self.assertEqual(len(audit.pre_first_seen_keys), 2)
            self.assertEqual(len(audit.unexpected_keys), 2)
            self.assertEqual(len(audit.pending_keys), 1)
            self.assertFalse(audit.corrupt_chunks)
            self.assertEqual(
                audit.to_document()["schema_version"],
                "1.0",
            )

    def test_corrupt_chunk_fails_validation_and_is_audited(self):
        with tempfile.TemporaryDirectory() as root:
            snapshot = _publish(root)
            path = Path(root) / snapshot.chunks[0].relative_path
            payload = bytearray(path.read_bytes())
            payload[-1] ^= 1
            path.write_bytes(payload)
            with self.assertRaises(ActivationStoreError) as captured:
                validate_activation_index_snapshot(snapshot, store_root=root)
            self.assertEqual(
                captured.exception.code,
                ActivationStoreErrorCode.CHECKSUM_MISMATCH,
            )
            audit = audit_activation_store(
                store_root=root,
                snapshot=snapshot,
                accepted_manifest_rows=_manifest_rows(),
            )
            self.assertEqual(
                audit.checksum_mismatches,
                (snapshot.chunks[0].chunk_id,),
            )

    def test_chunk_metadata_mismatch_matrix_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            snapshot = _publish(root)
            chunk = snapshot.chunks[0]
            mutations = (
                ("byte_size", replace(chunk, byte_size=chunk.byte_size + 1)),
                ("sha256", replace(chunk, sha256="f" * 64)),
                ("row_count", replace(chunk, row_count=chunk.row_count + 1)),
                (
                    "hidden_width",
                    replace(chunk, hidden_width=chunk.hidden_width + 1),
                ),
                ("dtype", replace(chunk, dtype="float16")),
                ("shape", replace(chunk, vector_shape=(WIDTH + 1,))),
                (
                    "status",
                    replace(chunk, operational_status="writing"),
                ),
                ("path", replace(chunk, relative_path="../escape.npy")),
            )
            for label, mutated in mutations:
                with self.subTest(label=label), self.assertRaises(
                    ActivationStoreError
                ):
                    store_module._validate_persisted_chunk(
                        root,
                        mutated,
                        snapshot.store_identity,
                    )

    def test_audit_missing_duplicates_orphans_and_nonaccepted_states(self):
        with tempfile.TemporaryDirectory() as root:
            snapshot = _publish(root)
            excluded = dict(snapshot.index_rows[0])
            excluded.update(
                {
                    "trajectory_id": "excluded",
                    "status": "excluded",
                    "exclusion_reason": "quality gate",
                    "operational_status": "completed",
                }
            )
            superseded = dict(snapshot.index_rows[0])
            superseded.update(
                {
                    "trajectory_id": "superseded",
                    "status": "superseded",
                    "superseded_by": "replacement-run",
                    "operational_status": "completed",
                }
            )
            work = [excluded, superseded]
            for state in ("pending", "writing", "failed"):
                record = dict(snapshot.index_rows[0])
                record.update(
                    {
                        "trajectory_id": f"{state}-trajectory",
                        "operational_status": state,
                        "state_reason": f"controlled {state}",
                    }
                )
                work.append(record)
            orphan = Path(root) / "chunks" / "controlled-orphan.npy"
            orphan.write_bytes(
                (Path(root) / snapshot.chunks[0].relative_path).read_bytes()
            )
            duplicate_rows = (*snapshot.index_rows, dict(snapshot.index_rows[0]))
            malformed = replace(snapshot, index_rows=duplicate_rows)
            audit = audit_activation_store(
                store_root=root,
                snapshot=malformed,
                accepted_manifest_rows=_manifest_rows(),
                work_records=work,
            )
            self.assertEqual(len(audit.missing_keys), 6)
            self.assertEqual(len(audit.duplicate_scientific_keys), 1)
            self.assertEqual(len(audit.duplicate_chunk_row_references), 1)
            self.assertEqual(audit.immutable_orphan_chunks, ("chunks/controlled-orphan.npy",))
            self.assertEqual(len(audit.pending_keys), 1)
            self.assertEqual(len(audit.writing_keys), 1)
            self.assertEqual(len(audit.failed_keys), 1)
            self.assertEqual(len(audit.excluded_keys), 1)
            self.assertEqual(len(audit.superseded_keys), 1)

    def test_index_rejects_duplicate_reference_and_bad_state(self):
        with tempfile.TemporaryDirectory() as root:
            snapshot = _publish(root)
            rows = [dict(row) for row in snapshot.index_rows]
            rows[1]["chunk_row_idx"] = rows[0]["chunk_row_idx"]
            prototype = copy.copy(snapshot)
            object.__setattr__(prototype, "index_rows", tuple(rows))
            object.__setattr__(
                prototype,
                "snapshot_id",
                store_module._canonical_digest(
                    store_module._snapshot_identity_document(prototype)
                ),
            )
            with self.assertRaises(ActivationStoreError):
                store_module._validate_snapshot_structure(prototype)


class TestPhase5ReviewedCorrections(unittest.TestCase):
    def test_snapshot_rejects_row_to_chunk_identity_mutations(self):
        with tempfile.TemporaryDirectory() as root:
            snapshot = _publish(root)
            cases = {}
            rows = [store_module._thaw_json(row) for row in snapshot.index_rows]
            changed = copy.deepcopy(rows)
            changed[0]["layer_idx"] = 12
            cases["row_layer"] = _resign(snapshot, rows=changed)
            changed = copy.deepcopy(rows)
            changed[0]["hook_site"] = "different_hook"
            cases["row_hook"] = _resign(snapshot, rows=changed)
            changed = copy.deepcopy(rows)
            changed[0]["run_id"] = "different-run"
            cases["row_run"] = _resign(snapshot, rows=changed)
            changed = copy.deepcopy(rows)
            changed[1]["chunk_row_idx"] = 0
            cases["incomplete_offsets"] = _resign(snapshot, rows=changed)

            chunk = snapshot.chunks[0]
            for label, field, value in (
                ("chunk_layer", "layer_idx", 12),
                (
                    "first_key",
                    "first_row_key",
                    ActivationRowKey(
                        "different-first",
                        0,
                        5,
                        snapshot.store_identity.hook_site,
                        snapshot.store_identity.run_id,
                    ),
                ),
                (
                    "last_key",
                    "last_row_key",
                    ActivationRowKey(
                        "different-last",
                        2,
                        5,
                        snapshot.store_identity.hook_site,
                        snapshot.store_identity.run_id,
                    ),
                ),
            ):
                forged_identity = _unsafe_frozen_replace(
                    chunk.chunk_identity,
                    **{field: value},
                )
                forged_record = _unsafe_frozen_replace(
                    chunk,
                    chunk_identity=forged_identity,
                    chunk_identity_digest=forged_identity.digest,
                    chunk_id=f"activation-chunk-{forged_identity.digest[:24]}",
                )
                changed_rows = copy.deepcopy(rows)
                for row in changed_rows:
                    row["activation_chunk_id"] = forged_record.chunk_id
                cases[label] = _resign(
                    snapshot,
                    rows=changed_rows,
                    chunks=(forged_record,),
                )

            for label, malformed in cases.items():
                with self.subTest(label=label), self.assertRaises(
                    ActivationStoreError
                ):
                    validate_activation_index_snapshot(
                        malformed,
                        store_root=root,
                    )

    def test_symlinked_chunk_snapshot_and_parent_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            snapshot = _publish(root)
            chunk_path = Path(root) / snapshot.chunks[0].relative_path
            real_chunk = chunk_path.with_name("real-chunk.npy")
            chunk_path.replace(real_chunk)
            _symlink_or_skip(self, real_chunk, chunk_path)
            with self.assertRaises(ActivationStoreError) as captured:
                validate_activation_index_snapshot(snapshot, store_root=root)
            self.assertEqual(
                captured.exception.code,
                ActivationStoreErrorCode.UNSAFE_PATH,
            )

        with tempfile.TemporaryDirectory() as root:
            snapshot = _publish(root)
            index_path = Path(root) / snapshot.relative_path
            link = index_path.with_name("linked-index.json")
            _symlink_or_skip(self, index_path, link)
            with self.assertRaises(ActivationStoreError):
                load_activation_index_snapshot(link, store_root=root)

        with tempfile.TemporaryDirectory() as root:
            snapshot = _publish(root)
            chunks = Path(root) / "chunks"
            real_chunks = Path(root) / "real-chunks"
            chunks.replace(real_chunks)
            _symlink_or_skip(self, real_chunks, chunks)
            with self.assertRaises(ActivationStoreError):
                validate_activation_index_snapshot(snapshot, store_root=root)

    def test_resume_rejects_malformed_key_identity(self):
        with tempfile.TemporaryDirectory() as root:
            snapshot = _publish(root)
            source = store_module._thaw_json(snapshot.index_rows[0])
            valid_key = ActivationRowKey.from_row(source)
            cases = {
                "wrong_hook": ActivationRowKey(
                    valid_key.trajectory_id,
                    valid_key.model_frame_idx,
                    valid_key.layer_idx,
                    "wrong_hook",
                    valid_key.producing_run_id,
                ),
                "outside_layer": ActivationRowKey(
                    valid_key.trajectory_id,
                    valid_key.model_frame_idx,
                    99,
                    valid_key.hook_site,
                    valid_key.producing_run_id,
                ),
                "metadata_layer": valid_key,
                "metadata_trajectory": valid_key,
                "metadata_frame": valid_key,
            }
            for label, key in cases.items():
                metadata = copy.deepcopy(source)
                metadata["operational_status"] = "pending"
                if label == "wrong_hook":
                    metadata["hook_site"] = key.hook_site
                elif label == "outside_layer":
                    metadata["layer_idx"] = key.layer_idx
                elif label == "metadata_layer":
                    metadata["layer_idx"] = 12
                elif label == "metadata_trajectory":
                    metadata["trajectory_id"] = "different-trajectory"
                elif label == "metadata_frame":
                    metadata["model_frame_idx"] = 1
                expected = _resume_expected(snapshot)
                expected[key] = metadata
                plan = plan_activation_resume(
                    store_root=root,
                    requested_identity=snapshot.store_identity,
                    snapshot=snapshot,
                    expected_rows=expected,
                )
                with self.subTest(label=label):
                    self.assertEqual(plan.retry, ())
                    self.assertEqual(plan.conflicts, (key,))

    def test_resume_operational_state_table(self):
        for has_stored in (False, True):
            for state in ("pending", "writing", "failed", "completed"):
                with (
                    self.subTest(has_stored=has_stored, state=state),
                    tempfile.TemporaryDirectory() as root,
                ):
                    snapshot = _publish(root)
                    stored_row = store_module._thaw_json(snapshot.index_rows[0])
                    if has_stored:
                        key = ActivationRowKey.from_row(stored_row)
                        metadata = copy.deepcopy(stored_row)
                    else:
                        key = ActivationRowKey(
                            "missing-state-row",
                            0,
                            5,
                            snapshot.store_identity.hook_site,
                            snapshot.store_identity.run_id,
                        )
                        metadata = copy.deepcopy(stored_row)
                        metadata["trajectory_id"] = key.trajectory_id
                    metadata["operational_status"] = state
                    expected = _resume_expected(snapshot)
                    expected[key] = metadata
                    plan = plan_activation_resume(
                        store_root=root,
                        requested_identity=snapshot.store_identity,
                        snapshot=snapshot,
                        expected_rows=expected,
                    )
                    if has_stored and state == "completed":
                        self.assertIn(key, plan.skip)
                        self.assertEqual(len(plan.skip), len(snapshot.index_rows))
                    elif not has_stored and state in {
                        "pending",
                        "writing",
                        "failed",
                    }:
                        self.assertEqual(plan.retry, (key,))
                    else:
                        self.assertEqual(plan.conflicts, (key,))

    def test_resume_nonaccepted_state_table(self):
        for has_stored in (False, True):
            for lifecycle in ("excluded", "superseded"):
                with (
                    self.subTest(has_stored=has_stored, lifecycle=lifecycle),
                    tempfile.TemporaryDirectory() as root,
                ):
                    snapshot = _publish(root)
                    metadata = store_module._thaw_json(snapshot.index_rows[0])
                    if has_stored:
                        key = ActivationRowKey.from_row(metadata)
                    else:
                        key = ActivationRowKey(
                            f"missing-{lifecycle}",
                            0,
                            5,
                            snapshot.store_identity.hook_site,
                            snapshot.store_identity.run_id,
                        )
                        metadata["trajectory_id"] = key.trajectory_id
                    metadata["status"] = lifecycle
                    metadata["operational_status"] = "completed"
                    metadata["exclusion_reason"] = (
                        "controlled exclusion"
                        if lifecycle == "excluded"
                        else None
                    )
                    metadata["superseded_by"] = (
                        "replacement" if lifecycle == "superseded" else None
                    )
                    expected = _resume_expected(snapshot)
                    expected[key] = metadata
                    plan = plan_activation_resume(
                        store_root=root,
                        requested_identity=snapshot.store_identity,
                        snapshot=snapshot,
                        expected_rows=expected,
                    )
                    if has_stored:
                        self.assertEqual(plan.conflicts, (key,))
                        self.assertEqual(plan.excluded, ())
                    else:
                        self.assertEqual(plan.excluded, (key,))

    def test_audit_corrupt_chunks_remove_completed_cardinality(self):
        writers = {
            "missing": lambda path: path.unlink(),
            "corrupt": lambda path: path.write_bytes(b"not-a-npy"),
            "truncated": lambda path: path.write_bytes(path.read_bytes()[:64]),
            "wrong_dtype": lambda path: numpy.save(
                path,
                numpy.zeros((3, WIDTH), dtype=numpy.float16),
                allow_pickle=False,
            ),
            "wrong_shape": lambda path: numpy.save(
                path,
                numpy.zeros((3, WIDTH - 1), dtype=numpy.float32),
                allow_pickle=False,
            ),
            "row_count": lambda path: numpy.save(
                path,
                numpy.zeros((2, WIDTH), dtype=numpy.float32),
                allow_pickle=False,
            ),
        }
        for label, writer in writers.items():
            with (
                self.subTest(label=label),
                tempfile.TemporaryDirectory() as root,
            ):
                snapshot = _publish(root)
                path = Path(root) / snapshot.chunks[0].relative_path
                writer(path)
                audit_snapshot = snapshot
                if path.exists() and label in {
                    "wrong_dtype",
                    "wrong_shape",
                    "row_count",
                }:
                    chunk = replace(
                        snapshot.chunks[0],
                        byte_size=path.stat().st_size,
                        sha256=store_module._sha256_file(path),
                    )
                    audit_snapshot = _resign(snapshot, chunks=(chunk,))
                audit = audit_activation_store(
                    store_root=root,
                    snapshot=audit_snapshot,
                    accepted_manifest_rows=_manifest_rows(),
                )
                self.assertEqual(audit.completed_accepted_keys, ())
                self.assertEqual(len(audit.missing_keys), 6)
                self.assertTrue(audit.corrupt_chunks)
                self.assertTrue(
                    all(
                        reason.reason
                        for reason in audit.shortfall_reasons
                    )
                )

    def test_audit_reports_reference_binding_categories(self):
        with tempfile.TemporaryDirectory() as root:
            snapshot = _publish(root)
            rows = [
                store_module._thaw_json(row) for row in snapshot.index_rows
            ]
            rows[0]["activation_chunk_id"] = "unknown"
            rows[1]["chunk_row_idx"] = 99
            rows[2]["chunk_row_idx"] = 1
            rows[2]["layer_idx"] = 12
            rows[2]["dtype"] = "float16"
            rows[2]["vector_shape"] = [WIDTH - 1]
            rows[2]["hook_site"] = "wrong-hook"
            rows[2]["run_id"] = "wrong-run"
            malformed = _resign(snapshot, rows=rows)
            audit = audit_activation_store(
                store_root=root,
                snapshot=malformed,
                accepted_manifest_rows=_manifest_rows(),
            )
            self.assertEqual(audit.unknown_referenced_chunks, ("unknown",))
            self.assertEqual(len(audit.out_of_bounds_references), 1)
            self.assertTrue(audit.incomplete_chunk_offsets)
            self.assertTrue(audit.row_chunk_layer_mismatches)
            self.assertTrue(audit.row_chunk_dtype_mismatches)
            self.assertTrue(audit.row_chunk_shape_mismatches)
            self.assertTrue(audit.row_store_hook_mismatches)
            self.assertTrue(audit.row_store_run_mismatches)
            self.assertTrue(audit.chunk_row_range_mismatches)
            self.assertTrue(audit.referenced_row_count_mismatches)

    def test_pre_first_seen_reports_only_observed_or_work_keys(self):
        with tempfile.TemporaryDirectory() as root:
            snapshot = _publish(root)
            extra_pre = copy.deepcopy(_manifest_rows()[0])
            extra_pre.update(
                {
                    "trajectory_id": "manifest-only",
                    "model_frame_idx": 0,
                    "visibility": "occluded",
                }
            )
            extra_visible = copy.deepcopy(extra_pre)
            extra_visible.update(
                {"model_frame_idx": 1, "visibility": "visible"}
            )
            clean_audit = audit_activation_store(
                store_root=root,
                snapshot=snapshot,
                accepted_manifest_rows=[
                    *_manifest_rows(),
                    extra_pre,
                    extra_visible,
                ],
            )
            self.assertEqual(clean_audit.pre_first_seen_keys, ())

            manifest = _manifest_rows()
            manifest[0]["visibility"] = "occluded"
            manifest[1]["visibility"] = "visible"
            observed_audit = audit_activation_store(
                store_root=root,
                snapshot=snapshot,
                accepted_manifest_rows=manifest,
            )
            self.assertEqual(len(observed_audit.pre_first_seen_keys), 1)

            work = store_module._thaw_json(snapshot.index_rows[0])
            work.update(
                {
                    "trajectory_id": "manifest-only",
                    "operational_status": "pending",
                    "state_reason": "awaiting extraction",
                }
            )
            work_audit = audit_activation_store(
                store_root=root,
                snapshot=snapshot,
                accepted_manifest_rows=[
                    *_manifest_rows(),
                    extra_pre,
                    extra_visible,
                ],
                work_records=(work,),
            )
            self.assertEqual(len(work_audit.pre_first_seen_keys), 1)
            self.assertEqual(
                work_audit.pre_first_seen_keys[0].trajectory_id,
                "manifest-only",
            )

    def test_shortfall_reasons_preserve_work_and_integrity_details(self):
        with tempfile.TemporaryDirectory() as root:
            snapshot = _publish(root)
            work = store_module._thaw_json(snapshot.index_rows[0])
            work.update(
                {
                    "layer_idx": 12,
                    "operational_status": "failed",
                    "state_reason": "controlled extraction failure",
                }
            )
            audit = audit_activation_store(
                store_root=root,
                snapshot=snapshot,
                accepted_manifest_rows=_manifest_rows(),
                work_records=(work,),
            )
            document = audit.to_document()
            matching = [
                reason
                for reason in document["shortfall_reasons"]
                if reason["row_key"]["layer_idx"] == 12
                and reason["row_key"]["model_frame_idx"] == 0
            ]
            self.assertEqual(
                matching,
                [
                    {
                        "lifecycle_status": "accepted",
                        "operational_status": "failed",
                        "reason": "controlled extraction failure",
                        "row_key": ActivationRowKey.from_row(work).to_document(),
                        "source_classification": "work_record",
                    }
                ],
            )
            unexplained = [
                reason
                for reason in document["shortfall_reasons"]
                if reason["source_classification"] == "unexplained_missing"
            ]
            self.assertTrue(unexplained)

    def test_real_fault_resume_matches_uninterrupted_store(self):
        with tempfile.TemporaryDirectory() as reference_root, tempfile.TemporaryDirectory() as resumed_root:
            reference = _full_snapshot(reference_root)
            with self.assertRaises(ActivationStoreError):
                _publish(
                    resumed_root,
                    fault_point=(
                        ActivationPublicationFaultPoint.AFTER_FINAL_CHUNK_PUBLICATION
                    ),
                )
            self.assertEqual(
                list((Path(resumed_root) / "indexes").glob("*.json")),
                [],
            )
            self.assertEqual(
                len(list((Path(resumed_root) / "chunks").glob("*.npy"))),
                1,
            )
            resumed_first = _publish(resumed_root)
            resumed = _publish(
                resumed_root,
                layer=12,
                prior=resumed_first,
            )
            reference_keys = tuple(
                ActivationRowKey.from_row(row) for row in reference.index_rows
            )
            resumed_keys = tuple(
                ActivationRowKey.from_row(row) for row in resumed.index_rows
            )
            self.assertEqual(resumed_keys, reference_keys)
            self.assertEqual(resumed.snapshot_id, reference.snapshot_id)
            self.assertEqual(
                [chunk.chunk_id for chunk in resumed.chunks],
                [chunk.chunk_id for chunk in reference.chunks],
            )
            self.assertEqual(
                [chunk.sha256 for chunk in resumed.chunks],
                [chunk.sha256 for chunk in reference.chunks],
            )
            self.assertEqual(
                [
                    (row["activation_chunk_id"], row["chunk_row_idx"])
                    for row in resumed.index_rows
                ],
                [
                    (row["activation_chunk_id"], row["chunk_row_idx"])
                    for row in reference.index_rows
                ],
            )
            numpy.testing.assert_array_equal(
                read_activation_vectors(
                    store_root=resumed_root,
                    snapshot=resumed,
                    row_keys=resumed_keys,
                ),
                read_activation_vectors(
                    store_root=reference_root,
                    snapshot=reference,
                    row_keys=reference_keys,
                ),
            )
            audit = audit_activation_store(
                store_root=resumed_root,
                snapshot=resumed,
                accepted_manifest_rows=_manifest_rows(),
            )
            self.assertEqual(len(audit.completed_accepted_keys), 6)
            self.assertEqual(audit.missing_keys, ())
            self.assertEqual(audit.duplicate_scientific_keys, ())
            self.assertEqual(audit.shortfall_reasons, ())

    def test_strict_deserialization_and_loaded_snapshot_immutability(self):
        with tempfile.TemporaryDirectory() as root:
            snapshot = _publish(root)
            document = snapshot.to_document()
            row_key = copy.deepcopy(
                document["chunks"][0]["chunk_identity"]["first_row_key"]
            )
            for label, mutation in (
                ("missing_row_key", lambda value: value.pop("trajectory_id")),
                ("extra_row_key", lambda value: value.update({"extra": 1})),
            ):
                changed = copy.deepcopy(row_key)
                mutation(changed)
                with self.subTest(label=label), self.assertRaises(
                    ActivationStoreError
                ):
                    store_module._row_key_from_document(changed)
            chunk_document = document["chunks"][0]
            for label, field, add_extra in (
                ("chunk_missing", "byte_size", False),
                ("chunk_extra", "", True),
                ("chunk_identity_missing", "dtype", False),
                ("chunk_identity_extra", "", True),
                ("nested_first_missing", "trajectory_id", False),
                ("nested_last_extra", "", True),
            ):
                changed = copy.deepcopy(chunk_document)
                if label.startswith("chunk_identity"):
                    target = changed["chunk_identity"]
                elif label.startswith("nested_first"):
                    target = changed["chunk_identity"]["first_row_key"]
                elif label.startswith("nested_last"):
                    target = changed["chunk_identity"]["last_row_key"]
                else:
                    target = changed
                if add_extra:
                    target["extra"] = 1
                else:
                    target.pop(field)
                with self.subTest(label=label), self.assertRaises(
                    ActivationStoreError
                ):
                    store_module._chunk_record_from_document(changed)
            loaded = load_activation_index_snapshot(
                Path(root) / snapshot.relative_path,
                store_root=root,
            )
            with self.assertRaises(TypeError):
                loaded.index_rows[0]["trajectory_id"] = "mutated"
            self.assertIsInstance(
                loaded.index_rows[0]["frame_token_positions"],
                tuple,
            )

    def test_orphan_timestamp_is_index_record_time(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ActivationStoreError):
                _publish(
                    root,
                    fault_point=(
                        ActivationPublicationFaultPoint.AFTER_FINAL_CHUNK_PUBLICATION
                    ),
                )
            snapshot = publish_activation_chunk(
                store_root=root,
                store_identity=_identity(),
                accepted_manifest_rows=_manifest_rows(),
                eligibility_proof=build_activation_eligibility_proof(
                    store_identity=_identity(),
                    accepted_manifest_rows=_manifest_rows(),
                ),
                rows=_rows(5),
                vectors=_vectors(5),
                creation_timestamp="2026-07-27T01:00:00Z",
            )
            document = snapshot.to_document()
            self.assertEqual(
                document["chunks"][0]["creation_timestamp"],
                "2026-07-27T01:00:00Z",
            )
            self.assertEqual(
                document["chunks"][0]["creation_timestamp_semantics"],
                store_module.ACTIVATION_CHUNK_TIMESTAMP_SEMANTICS,
            )
            rows = [dict(row) for row in snapshot.index_rows]
            rows[0]["run_status"] = "writing"
            prototype = copy.copy(snapshot)
            object.__setattr__(prototype, "index_rows", tuple(rows))
            object.__setattr__(
                prototype,
                "snapshot_id",
                store_module._canonical_digest(
                    store_module._snapshot_identity_document(prototype)
                ),
            )
            with self.assertRaises(ActivationStoreError):
                store_module._validate_snapshot_structure(prototype)


class TestPhase5AuditOneCorrections(unittest.TestCase):
    def test_publication_reconstructs_authority_and_rejects_forged_proof(self):
        identity = _identity()
        authority = _manifest_rows(identity)
        authority[0]["visibility"] = "occluded"
        authority[1]["visibility"] = "visible"
        honest = build_activation_eligibility_proof(
            store_identity=identity,
            accepted_manifest_rows=authority,
        )
        pre_first = _rows_for_identity(5, identity)[0]
        pre_first["visibility"] = "occluded"
        forged_entry = {
            "metadata": {
                field: copy.deepcopy(pre_first[field])
                for field in ACTIVATION_ELIGIBILITY_METADATA_FIELDS
            },
            "row_key": ActivationRowKey.from_row(pre_first).to_document(),
        }
        forged_rows = [
            *(store_module._thaw_json(row) for row in honest.eligible_rows),
            forged_entry,
        ]
        forged_rows.sort(
            key=lambda value: store_module._row_key_from_document(
                value["row_key"]
            )
        )
        forged = ActivationEligibilityProof(
            store_identity_digest=honest.store_identity_digest,
            accepted_manifest_hash=honest.accepted_manifest_hash,
            source_manifest_row_count=honest.source_manifest_row_count,
            source_rows_digest=honest.source_rows_digest,
            eligible_rows=tuple(forged_rows),
        )

        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ActivationStoreError) as captured:
                publish_activation_chunk(
                    store_root=root,
                    store_identity=identity,
                    eligibility_proof=forged,
                    rows=[pre_first],
                    vectors=_vectors(5)[0:1],
                    creation_timestamp=CREATED,
                )
            self.assertEqual(
                captured.exception.code,
                ActivationStoreErrorCode.ELIGIBILITY_CONFLICT,
            )
            self.assertEqual(captured.exception.field, "accepted_manifest_rows")
            self.assertEqual(list(Path(root).rglob("*")), [])

        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ActivationStoreError) as captured:
                publish_activation_chunk(
                    store_root=root,
                    store_identity=identity,
                    accepted_manifest_rows=authority,
                    eligibility_proof=forged,
                    rows=[pre_first],
                    vectors=_vectors(5)[0:1],
                    creation_timestamp=CREATED,
                )
            self.assertEqual(
                captured.exception.code,
                ActivationStoreErrorCode.ELIGIBILITY_CONFLICT,
            )
            self.assertEqual(
                captured.exception.field,
                "eligibility_proof.eligible_rows",
            )
            self.assertIn(honest.digest, str(captured.exception))
            self.assertIn(forged.digest, str(captured.exception))
            self.assertEqual(list(Path(root).rglob("*")), [])

        accepted = _rows_for_identity(5, identity)[1]
        accepted["visibility"] = "visible"
        with tempfile.TemporaryDirectory() as root:
            claimed = publish_activation_chunk(
                store_root=root,
                store_identity=identity,
                accepted_manifest_rows=authority,
                eligibility_proof=honest,
                rows=[accepted],
                vectors=_vectors(5)[1:2],
                creation_timestamp=CREATED,
            )
            self.assertEqual(len(claimed.index_rows), 1)
        with tempfile.TemporaryDirectory() as root:
            reconstructed = publish_activation_chunk(
                store_root=root,
                store_identity=identity,
                accepted_manifest_rows=authority,
                rows=[accepted],
                vectors=_vectors(5)[1:2],
                creation_timestamp=CREATED,
            )
            self.assertEqual(len(reconstructed.index_rows), 1)

    def test_authoritative_metadata_change_rejects_before_output(self):
        identity = _identity()
        authority = _manifest_rows(identity)
        authority[0]["tau"] = float(authority[0]["tau"]) + 0.25
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ActivationStoreError) as captured:
                publish_activation_chunk(
                    store_root=root,
                    store_identity=identity,
                    accepted_manifest_rows=authority,
                    rows=[_rows_for_identity(5, identity)[0]],
                    vectors=_vectors(5)[0:1],
                    creation_timestamp=CREATED,
                )
            self.assertEqual(
                captured.exception.code,
                ActivationStoreErrorCode.ELIGIBILITY_CONFLICT,
            )
            self.assertEqual(captured.exception.field, "rows[0].tau")
            self.assertIn(
                identity.accepted_manifest_hash,
                str(captured.exception),
            )
            self.assertEqual(list(Path(root).rglob("*")), [])

    def test_run_binding_is_idempotent_conflicting_and_run_scoped(self):
        with tempfile.TemporaryDirectory() as root:
            identity_a = _identity()
            first = _publish(root, identity=identity_a)
            chunk_count = len(list((Path(root) / "chunks").glob("*.npy")))
            index_count = len(list((Path(root) / "indexes").glob("*.json")))
            replay = _publish(root, identity=identity_a)
            self.assertEqual(first, replay)
            self.assertEqual(
                len(list((Path(root) / "chunks").glob("*.npy"))),
                chunk_count,
            )
            self.assertEqual(
                len(list((Path(root) / "indexes").glob("*.json"))),
                index_count,
            )
            changed_manifest = _manifest_rows(identity_a)
            changed_rows = _rows_for_identity(5, identity_a)
            for row in (*changed_manifest, *changed_rows):
                row["duration"] = float(row["duration"]) + 1.0
            with self.assertRaises(ActivationStoreError) as captured:
                _publish(
                    root,
                    identity=identity_a,
                    rows=changed_rows,
                    eligibility_rows=changed_manifest,
                )
            self.assertEqual(
                captured.exception.code,
                ActivationStoreErrorCode.ELIGIBILITY_CONFLICT,
            )

            identity_b = replace(identity_a, code_sha="f" * 40)
            with self.assertRaises(ActivationStoreError) as captured:
                _publish(
                    root,
                    identity=identity_b,
                    rows=_rows_for_identity(5, identity_b),
                )
            self.assertEqual(
                captured.exception.code,
                ActivationStoreErrorCode.RUN_BINDING_CONFLICT,
            )
            self.assertIn(identity_a.digest, str(captured.exception))
            self.assertIn(identity_b.digest, str(captured.exception))
            self.assertEqual(
                len(list((Path(root) / "chunks").glob("*.npy"))),
                chunk_count,
            )
            self.assertEqual(
                list(Path(root).rglob("*.tmp")),
                [],
            )

            identity_c = replace(
                identity_b,
                run_id="phase5-distinct-producing-run",
            )
            created = _publish(
                root,
                identity=identity_c,
                rows=_rows_for_identity(5, identity_c),
            )
            self.assertEqual(created.store_identity, identity_c)
            self.assertEqual(
                len(list((Path(root) / "run_bindings").glob("*.json"))),
                2,
            )

    def test_run_binding_tamper_and_interruption_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            snapshot = _publish(root)
            binding = next((Path(root) / "run_bindings").glob("*.json"))
            document = json.loads(binding.read_text(encoding="utf-8"))
            document["store_identity"]["config_hash"] = "f" * 64
            binding.write_text(
                json.dumps(document, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(ActivationStoreError):
                load_activation_index_snapshot(
                    Path(root) / snapshot.relative_path,
                    store_root=root,
                )
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ActivationStoreError) as captured:
                _publish(
                    root,
                    fault_point=(
                        ActivationPublicationFaultPoint
                        .DURING_RUN_BINDING_PUBLICATION
                    ),
                )
            self.assertEqual(
                captured.exception.code,
                ActivationStoreErrorCode.FORCED_INTERRUPTION,
            )
            self.assertEqual(
                list((Path(root) / "run_bindings").glob("*.json")),
                [],
            )
            self.assertEqual(list(Path(root).rglob("*.tmp")), [])
            replacement = replace(_identity(), code_sha="f" * 40)
            recovered = _publish(
                root,
                identity=replacement,
                rows=_rows_for_identity(5, replacement),
            )
            self.assertEqual(recovered.store_identity, replacement)

    def test_authoritative_eligibility_rejects_before_publication(self):
        manifest = _manifest_rows()
        manifest[0]["visibility"] = "occluded"
        manifest[1]["visibility"] = "visible"
        pre_first = _rows(5)[0]
        pre_first["visibility"] = "occluded"
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ActivationStoreError) as captured:
                _publish(
                    root,
                    rows=[pre_first],
                    vectors=_vectors(5)[0:1],
                    eligibility_rows=manifest,
                )
            self.assertEqual(
                captured.exception.code,
                ActivationStoreErrorCode.ELIGIBILITY_CONFLICT,
            )
            self.assertEqual(list(Path(root).rglob("*.tmp")), [])
            self.assertEqual(list((Path(root) / "chunks").glob("*")), [])
            self.assertEqual(list((Path(root) / "indexes").glob("*")), [])

            accepted = _rows(5)[1]
            accepted["visibility"] = "visible"
            snapshot = _publish(
                root,
                rows=[accepted],
                vectors=_vectors(5)[1:2],
                eligibility_rows=manifest,
            )
            self.assertEqual(len(snapshot.index_rows), 1)

        changed = _rows(5)[1]
        changed["visibility"] = "visible"
        changed["tau"] = float(changed["tau"]) + 0.25
        with (
            tempfile.TemporaryDirectory() as root,
            self.assertRaises(ActivationStoreError),
        ):
            _publish(
                root,
                rows=[changed],
                vectors=_vectors(5)[1:2],
                eligibility_rows=manifest,
            )
        unexpected = _rows(5)[1]
        unexpected["visibility"] = "visible"
        unexpected["trajectory_id"] = "unexpected-trajectory"
        with (
            tempfile.TemporaryDirectory() as root,
            self.assertRaises(ActivationStoreError),
        ):
            _publish(
                root,
                rows=[unexpected],
                vectors=_vectors(5)[1:2],
                eligibility_rows=manifest,
            )
        duplicate_manifest = [*manifest, copy.deepcopy(manifest[1])]
        with self.assertRaises(ActivationStoreError):
            build_activation_eligibility_proof(
                store_identity=_identity(),
                accepted_manifest_rows=duplicate_manifest,
            )

    def test_hard_link_failure_cleans_only_current_temporary(self):
        with tempfile.TemporaryDirectory() as root:
            identity = _identity()
            store_module._ensure_run_identity_binding(
                store_root=root,
                identity=identity,
                eligibility_proof=build_activation_eligibility_proof(
                    store_identity=identity,
                    accepted_manifest_rows=_manifest_rows(identity),
                ),
                fault_point=None,
            )
            unrelated = Path(root) / "chunks" / ".unrelated.tmp"
            unrelated.parent.mkdir(exist_ok=True)
            unrelated.write_text("preserve", encoding="utf-8")
            with (
                mock.patch.object(
                    os,
                    "link",
                    side_effect=OSError("controlled hard-link failure"),
                ),
                self.assertRaises(ActivationStoreError) as captured,
            ):
                _publish(root, identity=identity)
            self.assertEqual(
                captured.exception.code,
                ActivationStoreErrorCode.PUBLICATION_FAILED,
            )
            self.assertEqual(
                [
                    path
                    for path in (Path(root) / "chunks").glob("*.npy")
                    if path.is_file()
                ],
                [],
            )
            self.assertEqual(list((Path(root) / "indexes").glob("*.json")), [])
            self.assertEqual(
                [path.name for path in Path(root).rglob("*.tmp")],
                [unrelated.name],
            )

    def test_cleanup_failure_preserves_primary_publication_error(self):
        with tempfile.TemporaryDirectory() as root:
            identity = _identity()
            store_module._ensure_run_identity_binding(
                store_root=root,
                identity=identity,
                eligibility_proof=build_activation_eligibility_proof(
                    store_identity=identity,
                    accepted_manifest_rows=_manifest_rows(identity),
                ),
                fault_point=None,
            )
            real_unlink = Path.unlink

            def fail_current_temporary(path, *args, **kwargs):
                if path.suffix == ".tmp":
                    raise OSError("controlled cleanup failure")
                return real_unlink(path, *args, **kwargs)

            with (
                mock.patch.object(
                    os,
                    "link",
                    side_effect=OSError("controlled hard-link failure"),
                ),
                mock.patch.object(Path, "unlink", fail_current_temporary),
                self.assertRaises(ActivationStoreError) as captured,
            ):
                _publish(root, identity=identity)
            self.assertEqual(
                captured.exception.code,
                ActivationStoreErrorCode.PUBLICATION_FAILED,
            )
            self.assertIn("hard-link publication failed", str(captured.exception))
            self.assertIn(
                "temporary chunk cleanup failed",
                str(getattr(captured.exception, "cleanup_error", "")),
            )
            for temporary in Path(root).rglob("*.tmp"):
                real_unlink(temporary)

    def test_midwrite_cleanup_failure_is_attached_and_retry_is_deterministic(self):
        with tempfile.TemporaryDirectory() as root:
            identity = _identity()
            proof = build_activation_eligibility_proof(
                store_identity=identity,
                accepted_manifest_rows=_manifest_rows(identity),
            )
            store_module._ensure_run_identity_binding(
                store_root=root,
                identity=identity,
                eligibility_proof=proof,
                fault_point=None,
            )
            real_unlink = Path.unlink

            def fail_current_temporary(path, *args, **kwargs):
                if (
                    path.suffix == ".tmp"
                    and path.parent.name == "chunks"
                ):
                    raise OSError("controlled midwrite cleanup failure")
                return real_unlink(path, *args, **kwargs)

            with (
                mock.patch.object(Path, "unlink", fail_current_temporary),
                self.assertRaises(ActivationStoreError) as captured,
            ):
                _publish(
                    root,
                    identity=identity,
                    fault_point=(
                        ActivationPublicationFaultPoint.DURING_TEMPORARY_CHUNK
                    ),
                )
            self.assertEqual(
                captured.exception.code,
                ActivationStoreErrorCode.FORCED_INTERRUPTION,
            )
            cleanup = getattr(captured.exception, "cleanup_error", None)
            self.assertIsInstance(cleanup, ActivationStoreError)
            self.assertIn(
                "controlled midwrite cleanup failure",
                str(cleanup),
            )
            temporaries = list((Path(root) / "chunks").glob("*.tmp"))
            self.assertEqual(len(temporaries), 1)
            self.assertEqual(str(temporaries[0]), cleanup.path)
            self.assertEqual(list((Path(root) / "chunks").glob("*.npy")), [])
            self.assertEqual(list((Path(root) / "indexes").glob("*.json")), [])
            real_unlink(temporaries[0])
            recovered = _publish(root, identity=identity)
            self.assertEqual(len(recovered.index_rows), 3)
            self.assertEqual(list(Path(root).rglob("*.tmp")), [])

    def test_reviewed_limits_fail_before_unsafe_load_and_accept_boundaries(self):
        payload_size = len(store_module._npy_bytes(_vectors(5)))
        with (
            tempfile.TemporaryDirectory() as root,
            mock.patch.object(
                store_module,
                "MAX_ACTIVATION_ROWS_PER_CHUNK",
                3,
            ),
            mock.patch.object(
                store_module,
                "MAX_ACTIVATION_CHUNK_BYTES",
                payload_size,
            ),
            mock.patch.object(
                store_module,
                "MAX_ACTIVATION_INDEX_ROWS",
                3,
            ),
            mock.patch.object(
                store_module,
                "MAX_ACTIVATION_HIDDEN_WIDTH",
                WIDTH,
            ),
        ):
            snapshot = _publish(root)
            validate_activation_index_snapshot(snapshot, store_root=root)

        for field, limit in (
            ("MAX_ACTIVATION_ROWS_PER_CHUNK", 2),
            ("MAX_ACTIVATION_INDEX_ROWS", 2),
            ("MAX_ACTIVATION_CHUNK_BYTES", payload_size - 1),
            ("MAX_ACTIVATION_HIDDEN_WIDTH", WIDTH - 1),
        ):
            with (
                self.subTest(field=field),
                tempfile.TemporaryDirectory() as root,
                mock.patch.object(store_module, field, limit),
                self.assertRaises(ActivationStoreError) as captured,
            ):
                if field == "MAX_ACTIVATION_HIDDEN_WIDTH":
                    _identity()
                else:
                    _publish(root)
            self.assertEqual(
                captured.exception.code,
                ActivationStoreErrorCode.LIMIT_EXCEEDED,
            )
        with tempfile.TemporaryDirectory() as root:
            first = _publish(root)
            prior_chunks = list((Path(root) / "chunks").glob("*.npy"))
            with (
                mock.patch.object(
                    store_module,
                    "MAX_ACTIVATION_CHUNKS_PER_SNAPSHOT",
                    1,
                ),
                self.assertRaises(ActivationStoreError) as captured,
            ):
                _publish(root, layer=12, prior=first)
            self.assertEqual(
                captured.exception.code,
                ActivationStoreErrorCode.LIMIT_EXCEEDED,
            )
            self.assertEqual(
                list((Path(root) / "chunks").glob("*.npy")),
                prior_chunks,
            )
            self.assertEqual(list(Path(root).rglob("*.tmp")), [])

        with tempfile.TemporaryDirectory() as root:
            snapshot = _full_snapshot(root)
            with (
                mock.patch.object(
                    store_module,
                    "MAX_ACTIVATION_CHUNKS_PER_SNAPSHOT",
                    2,
                ),
            ):
                validate_activation_index_snapshot(snapshot, store_root=root)
            with (
                mock.patch.object(
                    store_module,
                    "MAX_ACTIVATION_CHUNKS_PER_SNAPSHOT",
                    1,
                ),
                self.assertRaises(ActivationStoreError),
            ):
                validate_activation_index_snapshot(snapshot, store_root=root)

            index = Path(root) / snapshot.relative_path
            index_size = index.stat().st_size
            with mock.patch.object(
                store_module,
                "MAX_ACTIVATION_INDEX_JSON_BYTES",
                index_size,
            ):
                load_activation_index_snapshot(index, store_root=root)
            with (
                mock.patch.object(
                    store_module,
                    "MAX_ACTIVATION_INDEX_JSON_BYTES",
                    index_size - 1,
                ),
                mock.patch.object(
                    Path,
                    "read_text",
                    side_effect=AssertionError("unsafe full read reached"),
                ),
                self.assertRaises(ActivationStoreError) as captured,
            ):
                load_activation_index_snapshot(index, store_root=root)
            self.assertEqual(
                captured.exception.code,
                ActivationStoreErrorCode.LIMIT_EXCEEDED,
            )

    def test_reader_aggregate_limits_are_costed_before_chunk_loading(self):
        with tempfile.TemporaryDirectory() as root:
            snapshot = _full_snapshot(root)
            keys = tuple(
                ActivationRowKey.from_row(row) for row in snapshot.index_rows
            )
            exact_bytes = len(keys) * WIDTH * numpy.dtype("float32").itemsize
            with (
                mock.patch.object(
                    store_module,
                    "MAX_ACTIVATION_READ_ROWS",
                    len(keys),
                ),
                mock.patch.object(
                    store_module,
                    "MAX_ACTIVATION_READ_CHUNKS",
                    len(snapshot.chunks),
                ),
                mock.patch.object(
                    store_module,
                    "MAX_ACTIVATION_READ_RESULT_BYTES",
                    exact_bytes,
                ),
            ):
                values = read_activation_vectors(
                    store_root=root,
                    snapshot=snapshot,
                    row_keys=keys,
                )
            self.assertEqual(values.shape, (len(keys), WIDTH))
            expected = numpy.stack(
                [
                    _vectors(key.layer_idx)[key.model_frame_idx]
                    for key in keys
                ]
            )
            numpy.testing.assert_array_equal(values, expected)

            empty = read_activation_vectors(
                store_root=root,
                snapshot=snapshot,
                row_keys=(),
            )
            self.assertEqual(empty.shape, (0, WIDTH))

            for field, limit in (
                ("MAX_ACTIVATION_READ_ROWS", len(keys) - 1),
                (
                    "MAX_ACTIVATION_READ_CHUNKS",
                    len(snapshot.chunks) - 1,
                ),
                (
                    "MAX_ACTIVATION_READ_RESULT_BYTES",
                    exact_bytes - 1,
                ),
            ):
                with (
                    self.subTest(field=field),
                    mock.patch.object(store_module, field, limit),
                    mock.patch.object(
                        store_module,
                        "_validate_persisted_chunk",
                    ) as validate_chunk,
                    mock.patch.object(numpy, "load") as load,
                    mock.patch.object(numpy, "stack") as stack,
                    self.assertRaises(ActivationStoreError) as captured,
                ):
                    read_activation_vectors(
                        store_root=root,
                        snapshot=snapshot,
                        row_keys=keys,
                    )
                self.assertEqual(
                    captured.exception.code,
                    ActivationStoreErrorCode.LIMIT_EXCEEDED,
                )
                self.assertIn("calculated_result_bytes", str(captured.exception))
                validate_chunk.assert_not_called()
                load.assert_not_called()
                stack.assert_not_called()

            with mock.patch.object(
                store_module,
                "MAX_ACTIVATION_READ_ROWS",
                2,
            ):
                one_below = read_activation_vectors(
                    store_root=root,
                    snapshot=snapshot,
                    row_keys=keys[:1],
                )
                exact = read_activation_vectors(
                    store_root=root,
                    snapshot=snapshot,
                    row_keys=keys[:2],
                )
            self.assertEqual(one_below.shape[0], 1)
            self.assertEqual(exact.shape[0], 2)

    def test_float16_promotion_is_costed_at_float32_result_bytes(self):
        identity = _identity(dtype="float16")
        with tempfile.TemporaryDirectory() as root:
            snapshot = _publish(
                root,
                identity=identity,
                vectors=_vectors(5, dtype="float16"),
            )
            key = ActivationRowKey.from_row(snapshot.index_rows[0])
            promoted_bytes = WIDTH * numpy.dtype("float32").itemsize
            with mock.patch.object(
                store_module,
                "MAX_ACTIVATION_READ_RESULT_BYTES",
                promoted_bytes,
            ):
                values = read_activation_vectors(
                    store_root=root,
                    snapshot=snapshot,
                    row_keys=(key,),
                )
            self.assertEqual(values.dtype.name, "float32")
            with (
                mock.patch.object(
                    store_module,
                    "MAX_ACTIVATION_READ_RESULT_BYTES",
                    promoted_bytes - 1,
                ),
                mock.patch.object(
                    store_module,
                    "_validate_persisted_chunk",
                ) as validate_chunk,
                mock.patch.object(numpy, "load") as load,
                mock.patch.object(numpy, "stack") as stack,
                self.assertRaises(ActivationStoreError) as captured,
            ):
                read_activation_vectors(
                    store_root=root,
                    snapshot=snapshot,
                    row_keys=(key,),
                )
            self.assertEqual(
                captured.exception.code,
                ActivationStoreErrorCode.LIMIT_EXCEEDED,
            )
            self.assertIn(
                "requested_output_dtype=float32",
                str(captured.exception),
            )
            validate_chunk.assert_not_called()
            load.assert_not_called()
            stack.assert_not_called()


class TestPhase5ExampleAndForecast(unittest.TestCase):
    def test_checked_example_validates_reads_and_detects_tampering(self):
        benchmark = _benchmark_module()
        benchmark._validate_example(
            type("Arguments", (), {"output_dir": CHECKED_EXAMPLE})()
        )
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "example"
            shutil.copytree(CHECKED_EXAMPLE, copied)
            chunk = next((copied / "chunks").glob("*.npy"))
            payload = bytearray(chunk.read_bytes())
            payload[-1] ^= 1
            chunk.write_bytes(payload)
            with self.assertRaises((ValueError, ActivationStoreError)):
                benchmark._validate_example(
                    type("Arguments", (), {"output_dir": copied})()
                )

    def test_example_generation_is_byte_deterministic(self):
        benchmark = _benchmark_module()
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first"
            second = Path(directory) / "second"
            for output in (first, second):
                benchmark._write_example(
                    type("Arguments", (), {"output_dir": output})()
                )
            first_files = {
                path.relative_to(first).as_posix(): path.read_bytes()
                for path in first.rglob("*")
                if path.is_file()
            }
            second_files = {
                path.relative_to(second).as_posix(): path.read_bytes()
                for path in second.rglob("*")
                if path.is_file()
            }
            self.assertEqual(first_files, second_files)

    def test_example_inventory_rejects_every_unapproved_entry(self):
        benchmark = _benchmark_module()
        mutations = {
            "unlisted": lambda root: (root / "UNLISTED.txt").write_text(
                "unlisted",
                encoding="utf-8",
            ),
            "second_chunk": lambda root: shutil.copy2(
                next((root / "chunks").glob("*.npy")),
                root / "chunks" / "alternate.npy",
            ),
            "temporary": lambda root: (
                root / "chunks" / ".controlled.tmp"
            ).write_bytes(b"temporary"),
            "nested_directory": lambda root: (
                root / "unapproved"
            ).mkdir(),
            "missing": lambda root: (root / "README.md").unlink(),
        }
        for label, mutate in mutations.items():
            with (
                self.subTest(label=label),
                tempfile.TemporaryDirectory() as directory,
            ):
                copied = Path(directory) / "example"
                shutil.copytree(CHECKED_EXAMPLE, copied)
                mutate(copied)
                with self.assertRaises(ValueError):
                    benchmark._validate_example(
                        type("Arguments", (), {"output_dir": copied})()
                    )

    def test_forecast_requires_all_authoritative_scenarios(self):
        benchmark = _benchmark_module()
        scenarios = [
            {
                "assumption_classification": "caller_supplied_input",
                "chunk_row_count": 100,
                "dtype": "float16",
                "hidden_width": 2048,
                "label": label,
                "layer_count": 20,
                "model_frames_per_trajectory": 129,
                "trajectory_count": count if count is not None else 12,
            }
            for label, count in (
                benchmark.REQUIRED_SCENARIO_TRAJECTORY_COUNTS.items()
            )
        ]
        benchmark._validate_required_scenarios(scenarios)
        with self.assertRaises(ValueError):
            benchmark._validate_required_scenarios(scenarios[:-1])
        wrong = copy.deepcopy(scenarios)
        wrong[0]["trajectory_count"] += 1
        with self.assertRaises(ValueError):
            benchmark._validate_required_scenarios(wrong)

    def test_benchmark_run_rejects_missing_regime_a_before_output(self):
        benchmark = _benchmark_module()
        scenarios = [
            {
                "assumption_classification": "caller_supplied_input",
                "chunk_row_count": 100,
                "dtype": "float16",
                "hidden_width": 2048,
                "label": label,
                "layer_count": 20,
                "model_frames_per_trajectory": 129,
                "trajectory_count": count,
            }
            for label, count in (
                benchmark.REQUIRED_SCENARIO_TRAJECTORY_COUNTS.items()
            )
            if count is not None
        ]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "must-not-exist"
            with self.assertRaises(ValueError):
                benchmark._run(
                    type(
                        "Arguments",
                        (),
                        {
                            "approved_capacity_bytes": None,
                            "output_dir": output,
                            "scenario": scenarios,
                            "smoke_dtype": "float16",
                            "smoke_rows": 2,
                        },
                    )()
                )
            self.assertFalse(output.exists())

    def test_forecast_arithmetic_overheads_capacity_and_serialization(self):
        benchmark = _benchmark_module()
        scenario = {
            "assumption_classification": "caller_supplied_input",
            "chunk_row_count": 3,
            "dtype": "float16",
            "hidden_width": 4,
            "label": "regime-a",
            "layer_count": 2,
            "model_frames_per_trajectory": 2,
            "trajectory_count": 2,
        }
        measured = {
            "checksum_bytes_per_second": 100.0,
            "chunk_read_bytes_per_second": 100.0,
            "chunk_write_bytes_per_second": 100.0,
            "float_to_float32_promotion_bytes_per_second": 100.0,
            "index_bytes": 4096,
            "selective_read_bytes_per_second": 100.0,
        }
        unresolved = benchmark.forecast_scenario(
            scenario,
            measured=measured,
            smoke_rows=2,
            approved_capacity_bytes=None,
        )
        self.assertEqual(unresolved["vector_count"], 8)
        self.assertGreater(unresolved["numpy_header_overhead_bytes"], 0)
        self.assertGreater(unresolved["estimated_index_bytes"], 0)
        self.assertEqual(
            unresolved["staging_peak_bytes"],
            unresolved["total_persisted_bytes"]
            + unresolved["simultaneous_staging_bytes"],
        )
        self.assertEqual(unresolved["capacity"]["status"], "UNRESOLVED")
        passing = benchmark.forecast_scenario(
            scenario,
            measured=measured,
            smoke_rows=2,
            approved_capacity_bytes=unresolved["staging_peak_bytes"],
        )
        failing = benchmark.forecast_scenario(
            scenario,
            measured=measured,
            smoke_rows=2,
            approved_capacity_bytes=unresolved["staging_peak_bytes"] - 1,
        )
        self.assertEqual(passing["capacity"]["status"], "PASS")
        self.assertEqual(failing["capacity"]["status"], "FAIL")
        self.assertEqual(
            benchmark._deterministic_json_bytes(unresolved),
            benchmark._deterministic_json_bytes(copy.deepcopy(unresolved)),
        )


if __name__ == "__main__":
    unittest.main()
