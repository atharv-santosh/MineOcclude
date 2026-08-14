from __future__ import annotations

import io
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mineocclude.regime_a import (
    AtomicTrajectoryStore,
    HashChainLedger,
    RegimeAError,
    sha256_file,
    validate_a4_authorization,
)
from mineocclude.regime_a_execution import A4ExecutionRunner, S3DurableStore


def spec(identity: str = "synthetic_t01", seed: int = 7) -> dict[str, object]:
    return {"trajectory_spec_id": identity, "spec_hash": ("a" if seed == 7 else "b") * 64, "seed": seed}


class FakeS3:
    def __init__(self, *, fail_put: bool = False, bad_size: bool = False, bad_bytes: bool = False):
        self.objects: dict[tuple[str, str], tuple[bytes, dict[str, str]]] = {}
        self.fail_put, self.bad_size, self.bad_bytes = fail_put, bad_size, bad_bytes

    def put_object(self, *, Bucket, Key, Body, Metadata, ChecksumAlgorithm):
        if self.fail_put:
            raise OSError("synthetic upload failure")
        self.objects[(Bucket, Key)] = (Body.read(), dict(Metadata))

    def head_object(self, *, Bucket, Key):
        data, metadata = self.objects[(Bucket, Key)]
        return {"ContentLength": len(data) + int(self.bad_size), "Metadata": metadata}

    def get_object(self, *, Bucket, Key):
        data = self.objects[(Bucket, Key)][0]
        return {"Body": io.BytesIO(data + (b"corrupt" if self.bad_bytes else b""))}


class Capture:
    def __init__(self, fail_once: bool = False):
        self.calls: list[tuple[str, int]] = []
        self.fail_once = fail_once
        self.closed = 0

    def capture(self, value, partial):
        self.calls.append((value["trajectory_spec_id"], value["seed"]))
        if self.fail_once:
            self.fail_once = False
            raise OSError("synthetic capture interruption")
        for relative in (
            "raw/server_state.jsonl", "raw/client_tick.jsonl", "raw/actions.jsonl",
            "raw/frame_map.jsonl", "raw/visibility.jsonl", "coordinates.jsonl",
        ):
            path = partial / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n", encoding="utf-8")

    def close(self):
        self.closed += 1


class ResumableCapture(Capture):
    def __init__(self, *, accept: bool = True, fail: bool = False):
        super().__init__()
        self.accept = accept
        self.fail = fail
        self.resume_calls: list[str] = []

    def resume_capture(self, value, partial):
        self.resume_calls.append(value["trajectory_spec_id"])
        if self.fail:
            raise RegimeAError("synthetic post-capture validation failure")
        if not self.accept:
            return False
        super().capture(value, partial)
        self.calls.clear()
        return True


class Model:
    def __init__(self):
        self.load_count = 0
        self.calls: list[str] = []
        self.closed = 0

    def extract(self, value, partial):
        if self.load_count == 0:
            self.load_count = 1
        self.calls.append(value["trajectory_spec_id"])
        artifact_root = partial / "activations"
        artifact_root.mkdir()
        artifacts = []
        for layer in range(20):
            artifact = artifact_root / f"synthetic_{layer:02d}.bin"
            artifact.write_bytes(b"non-scientific")
            artifacts.append({"path": artifact.relative_to(partial).as_posix(), "layer_idx": layer, "byte_size": artifact.stat().st_size, "sha256": sha256_file(artifact)})
        (partial / "activation_inventory.json").write_text(json.dumps({
            "layer_indices": list(range(20)), "target_tau": list(range(1, 20)),
            "artifacts": artifacts,
        }), encoding="utf-8")

    def close(self):
        self.closed += 1


def make_runner(root: Path, capture=None, model=None, s3=None):
    return A4ExecutionRunner(
        store=AtomicTrajectoryStore(root / "trajectories"),
        ledger=HashChainLedger(root / "progress_ledger.jsonl"),
        capture_worker=capture or Capture(), model_worker=model or Model(),
        durable_store=S3DurableStore("s3://synthetic-bucket/non-scientific/", s3 or FakeS3()),
    )


class RegimeAA4RunnerTests(unittest.TestCase):
    def test_capture_worker_uses_qualified_java_home(self):
        runner_path = Path(__file__).parents[1] / "scripts/run_regime_a.py"
        module_spec = importlib.util.spec_from_file_location("regime_a_runner_test", runner_path)
        module = importlib.util.module_from_spec(module_spec)
        assert module_spec.loader is not None
        module_spec.loader.exec_module(module)
        java_home = Path(os.environ["JAVA_HOME"])
        with tempfile.TemporaryDirectory() as tmp:
            server, client = Path(tmp) / "server", Path(tmp) / "client"
            server.mkdir()
            client.mkdir()
            with patch.dict(os.environ, {"MINEOCCLUDE_SERVER_ROOT": str(server), "MINEOCCLUDE_CLIENT_ROOT": str(client)}):
                worker = module.ProductionCaptureWorker(Path("/mnt/sagemaker-nvme/non-scientific-test"))
            self.assertEqual(worker.java_home, java_home)
            self.assertEqual(worker.live.JAVA_PATH, java_home / "bin/java")
            self.assertEqual(worker.live.SERVER_ROOT, server)
            self.assertEqual(worker.live.CLIENT_ROOT, client)
            self.assertEqual(worker.live.FIFO, server / "cmd.fifo")
            self.assertTrue(worker.live.XVFB_PATH.is_file())
            self.assertTrue(worker.live.XDOTOOL_PATH.is_file())

    def test_authorization_required_and_full_binding_obsolete_commit_refused(self):
        with self.assertRaises(RegimeAError):
            validate_a4_authorization({}, "1" * 64, "2" * 64)
        document = {"status": "AUTHORIZED_A4_SCIENTIFIC_EXECUTION", "operator": "Kazim Abbas", "trajectory_manifest_sha256": "1" * 64, "study_manifest_sha256": "2" * 64, "final_reviewed_regime_a_commit_sha": "old"}
        with self.assertRaises(RegimeAError):
            validate_a4_authorization(document, "1" * 64, "2" * 64, expected_bindings={"final_reviewed_regime_a_commit_sha": "new"})
        with self.assertRaises(RegimeAError):
            validate_a4_authorization(document, "9" * 64, "2" * 64)

    def test_loop_dispatch_skip_durable_and_model_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = HashChainLedger(root / "progress_ledger.jsonl")
            ledger.append("synthetic_done", "COMPLETE_VALIDATED_DURABLE", spec_hash="a" * 64)
            capture, model, remote = Capture(), Model(), FakeS3()
            runner = A4ExecutionRunner(store=AtomicTrajectoryStore(root / "trajectories"), ledger=ledger, capture_worker=capture, model_worker=model, durable_store=S3DurableStore("s3://synthetic-bucket/non-scientific/", remote))
            dispatched = runner.run([spec("synthetic_done"), spec("synthetic_t01"), spec("synthetic_t02")])
            self.assertEqual(dispatched, ["synthetic_t01", "synthetic_t02"])
            self.assertEqual(model.load_count, 1)
            self.assertEqual([seed for _identity, seed in capture.calls], [7, 7])
            self.assertEqual(runner.ledger.complete_ids(), {"synthetic_done", "synthetic_t01", "synthetic_t02"})
            self.assertTrue(all(key.startswith("non-scientific/synthetic_") for _bucket, key in remote.objects))

    def test_local_validated_is_not_skipped_and_durability_only_resumes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            value = spec()
            store = AtomicTrajectoryStore(root / "trajectories")
            partial = store.begin(value["trajectory_spec_id"], value["spec_hash"])
            capture, model = Capture(), Model()
            capture.capture(value, partial)
            model.extract(value, partial)
            store.finalize(partial, value["trajectory_spec_id"], value["spec_hash"])
            ledger = HashChainLedger(root / "progress_ledger.jsonl")
            ledger.append(value["trajectory_spec_id"], "VALIDATED", spec_hash=value["spec_hash"])
            runner = A4ExecutionRunner(store=store, ledger=ledger, capture_worker=Capture(), model_worker=Model(), durable_store=S3DurableStore("s3://synthetic-bucket/non-scientific/", FakeS3()))
            self.assertEqual(runner.run([value]), [])
            self.assertIn(value["trajectory_spec_id"], runner.ledger.complete_ids())

    def test_same_spec_retry_discards_only_identified_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = Capture(fail_once=True)
            with self.assertRaises(OSError):
                make_runner(root, capture=capture).run([spec()])
            capture2 = Capture()
            runner = make_runner(root, capture=capture2)
            self.assertEqual(runner.run([spec()]), ["synthetic_t01"])
            self.assertEqual(capture2.calls, [("synthetic_t01", 7)])
            records = [row for row in runner.ledger.records if row["trajectory_spec_id"] == "synthetic_t01"]
            self.assertTrue(any(row.get("retry_same_spec") for row in records))

    def test_identity_proven_raw_partial_resumes_without_recapture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            value = spec()
            partial = AtomicTrajectoryStore(root / "trajectories").begin(
                value["trajectory_spec_id"], value["spec_hash"]
            )
            (partial / "raw").mkdir()
            capture, model = ResumableCapture(), Model()
            runner = make_runner(root, capture=capture, model=model)
            self.assertEqual(runner.run([value]), ["synthetic_t01"])
            self.assertEqual(capture.resume_calls, ["synthetic_t01"])
            self.assertEqual(capture.calls, [])
            self.assertEqual(model.calls, ["synthetic_t01"])
            captured = [row for row in runner.ledger.records if row["state"] == "CAPTURED"]
            self.assertTrue(captured[-1]["resumed_existing_raw_capture"])

    def test_failed_post_capture_resume_preserves_partial_and_blocks_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            value = spec()
            partial = AtomicTrajectoryStore(root / "trajectories").begin(
                value["trajectory_spec_id"], value["spec_hash"]
            )
            (partial / "raw").mkdir()
            capture, model = ResumableCapture(fail=True), Model()
            with self.assertRaises(RegimeAError):
                make_runner(root, capture=capture, model=model).run([value])
            self.assertTrue(partial.is_dir())
            self.assertEqual(model.calls, [])
            self.assertFalse(any(row["state"] == "CAPTURED" for row in HashChainLedger(root / "progress_ledger.jsonl").records))

    def test_ledger_captured_partial_resumes_directly_at_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            value = spec()
            store = AtomicTrajectoryStore(root / "trajectories")
            partial = store.begin(value["trajectory_spec_id"], value["spec_hash"])
            Capture().capture(value, partial)
            ledger = HashChainLedger(root / "progress_ledger.jsonl")
            ledger.append(value["trajectory_spec_id"], "CAPTURED", spec_hash=value["spec_hash"])
            capture, model = ResumableCapture(fail=True), Model()
            runner = A4ExecutionRunner(
                store=store,
                ledger=ledger,
                capture_worker=capture,
                model_worker=model,
                durable_store=S3DurableStore(
                    "s3://synthetic-bucket/non-scientific/", FakeS3()
                ),
            )

            self.assertEqual(runner.run([value]), ["synthetic_t01"])
            self.assertEqual(capture.resume_calls, [])
            self.assertEqual(capture.calls, [])
            self.assertEqual(model.calls, ["synthetic_t01"])

    def test_partial_identity_and_atomic_final(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AtomicTrajectoryStore(Path(tmp))
            partial = store.begin("synthetic_t01", "a" * 64)
            self.assertTrue((partial / "partial_identity.json").is_file())
            self.assertTrue(store.discard_same_spec_partial("synthetic_t01", "a" * 64))
            partial = store.begin("synthetic_t01", "a" * 64)
            (partial / "payload").write_bytes(b"x")
            final = store.finalize(partial, "synthetic_t01", "a" * 64)
            self.assertTrue(final.is_dir())
            self.assertFalse(partial.exists())

    def test_s3_key_inventory_and_download_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, remote = Path(tmp), FakeS3()
            runner = make_runner(root, s3=remote)
            runner.run([spec()])
            final = root / "trajectories/synthetic_t01"
            self.assertTrue((final / "durable_receipt.json").is_file())
            keys = {key for _bucket, key in remote.objects}
            self.assertIn("non-scientific/synthetic_t01/raw/server_state.jsonl", keys)
            self.assertIn("non-scientific/synthetic_t01/durable_receipt.json", keys)
            self.assertTrue(json.loads((final / "durable_receipt.json").read_text())["objects"])

    def test_s3_upload_size_and_download_failures_block_complete(self):
        for remote in (FakeS3(fail_put=True), FakeS3(bad_size=True), FakeS3(bad_bytes=True)):
            with self.subTest(remote=vars(remote)), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                with self.assertRaises((OSError, RegimeAError)):
                    make_runner(root, s3=remote).run([spec()])
                self.assertNotIn("synthetic_t01", HashChainLedger(root / "progress_ledger.jsonl").complete_ids())

    def test_ledger_hash_chain_resume_and_tamper_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.jsonl"
            ledger = HashChainLedger(path)
            ledger.append("synthetic_t01", "PLANNED", spec_hash="a" * 64, seed=7)
            self.assertEqual(len(HashChainLedger(path).records), 1)
            path.write_text(path.read_text().replace('"seed":7', '"seed":8'), encoding="utf-8")
            with self.assertRaises(RegimeAError):
                HashChainLedger(path)

    def test_no_analysis_and_runtime_outside_repository_are_structural(self):
        source = (Path(__file__).parents[1] / "scripts/run_regime_a.py").read_text()
        self.assertNotIn("macro_r2(", source)
        self.assertNotIn("best_k", source.lower())
        self.assertIn("runtime root must be outside the Git repository", source)

    def test_first25_v2_entrypoint_uses_exact_production_workers_and_stays_sealed(self):
        from scripts import run_regime_a as production
        from scripts import run_regime_a_first25_v2 as v2

        rows, digest = v2.validate_manifest(
            v2.V2 / "trajectory_manifest.jsonl",
            v2.V2 / "trajectory_manifest.sha256",
        )
        self.assertEqual(len(rows), 25)
        self.assertEqual(digest, sha256_file(v2.V2 / "trajectory_manifest.jsonl"))
        self.assertIs(v2.ProductionCaptureWorker, production.ProductionCaptureWorker)
        self.assertIs(v2.PersistentMineWorldWorker, production.PersistentMineWorldWorker)
        source = Path(v2.__file__).read_text()
        self.assertIn("A4-v2 scientific execution is sealed: authorization absent", source)
        self.assertNotIn("macro_r2(", source)
        self.assertNotIn("best_k", source.lower())


if __name__ == "__main__":
    unittest.main()
