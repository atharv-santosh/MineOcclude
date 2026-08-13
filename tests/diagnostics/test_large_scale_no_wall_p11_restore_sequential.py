from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from mineocclude.probes import p11_sharding as authority
from scripts import restore_large_scale_no_wall_p11_sequential_results as restorer


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def synthetic_parent() -> dict:
    jobs = []
    for seed_index in range(49):
        for representation in authority.REPRESENTATIONS:
            payload = {
                "alpha_grid": [0.1, 1.0, 10.0, 100.0],
                "assignment_sha256": f"assignment-{seed_index}",
                "best_k_grid": [1, 4, 8, 16, 32, 64, 128]
                if representation == "BEST_K_TOKENS"
                else None,
                "canonical_subset_hash": "canonical-subset",
                "canonical_subset_id": "n100_r00",
                "fixed_test_hash": "fixed-test",
                "job_id": f"seed_{seed_index:02d}__{representation.lower()}",
                "null_authority_sha256": "prospective-null",
                "representation": representation,
                "seed": 10_000 + seed_index,
                "seed_index": seed_index,
                "training_trajectory_ids": ["training-a", "training-b"],
            }
            payload["identity_sha256"] = authority.canonical_sha256(payload)
            jobs.append(payload)
    return {
        "artifact_id": "synthetic-parent",
        "canonical_null_authority_sha256": "canonical-null",
        "canonical_subset_id": "n100_r00",
        "expected_jobs": 196,
        "expected_seeds": 49,
        "jobs": jobs,
        "p10_manifest_sha256": authority.P10_COARSE_AUTHORITY_SHA,
        "prospective_null_authority_sha256": "prospective-null",
        "representations": list(authority.REPRESENTATIONS),
    }


class DirectoryTransport:
    def __init__(self, root: Path, source_uri: str, keys: list[str] | None = None) -> None:
        self.root = root
        self.source_uri = source_uri
        self.keys = keys

    def list_keys(self, relative_prefix: str) -> list[str]:
        assert relative_prefix == "jobs/"
        if self.keys is not None:
            return list(self.keys)
        return sorted(
            path.relative_to(self.root).as_posix()
            for path in (self.root / "jobs").rglob("*")
            if path.is_file()
        )

    def download_file(self, relative: str, destination: Path) -> None:
        assert not destination.exists()
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.root / relative, destination)


def authority_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path, dict, DirectoryTransport, list[str]]:
    parent = synthetic_parent()
    parent_path = tmp_path / "scientific" / "p11_run_manifest.json"
    write_json(parent_path, parent)
    parent_sha = authority.sha256_file(parent_path)
    implementation_sha = "a" * 40
    shards = authority.build_shards(
        parent,
        parent_sha,
        [0, 1, 2],
        repository_branch="test-branch",
        implementation_commit_sha=implementation_sha,
    )
    authority_root = tmp_path / "authority"
    shard_files = []
    for shard in shards:
        name = f"p11_shard_{shard['worker_slug']}.json"
        write_json(authority_root / name, shard)
        shard_files.append(name)
    common = {
        "completed_seed_indices": [0, 1, 2],
        "completed_seed_values": [10_000, 10_001, 10_002],
        "implementation_commit_sha": implementation_sha,
        "parent_p11_manifest_sha": parent_sha,
        "shard_manifest_files": shard_files,
        "shard_manifest_shas": {
            shard["worker_slug"]: shard["shard_manifest_sha"] for shard in shards
        },
    }
    common["common_authority_sha"] = authority.common_sha(common)
    common_path = authority_root / "common_authority.json"
    write_json(common_path, common)

    source_uri = "s3://fixture-bucket/frozen-p11/"
    durable = tmp_path / "durable"
    historical_jobs = [job for job in parent["jobs"] if job["seed_index"] < 3]
    result_hashes = {}
    for job in historical_jobs:
        job_root = durable / "jobs" / job["job_id"]
        result = {
            "artifact_id": "large-scale-no-wall-p11-null-job-v0.1",
            "fixed_test_hash": job["fixed_test_hash"],
            "identity_sha256": job["identity_sha256"],
            "job_id": job["job_id"],
            "representation": job["representation"],
            "seed": job["seed"],
            "seed_index": job["seed_index"],
            "status": "VALIDATED",
        }
        write_json(job_root / "job_result.json", result)
        (job_root / "predictions.npz").write_bytes(b"frozen-predictions")
        write_json(job_root / "selection_evidence.json", {"frozen": True})
        result_hashes[job["job_id"]] = authority.sha256_file(job_root / "job_result.json")
    pause = {
        "artifact_id": "large-scale-no-wall-p11-clean-pause-v0.1",
        "completed_seed_indices": [0, 1, 2],
        "completed_seed_values": [10_000, 10_001, 10_002],
        "durable_checkpoint_verified": True,
        "implementation_commit_sha": implementation_sha,
        "job_result_sha256": result_hashes,
        "parent_p11_manifest_sha": parent_sha,
        "partial_seed_present": False,
        "s3_downloaded_hash_verification": {
            "object_count": 40,
            "seed_indices": [0, 1, 2],
            "status": "PASS",
        },
        "s3_prefix": source_uri,
        "status": restorer.PAUSE_STATUS,
        "validated_job_count": 12,
        "validated_seed_count": 3,
    }
    pause_path = authority_root / "p11_pause_receipt.json"
    write_json(pause_path, pause)
    monkeypatch.setattr(restorer.p11, "MANIFEST", parent_path)
    monkeypatch.setattr(restorer.p11, "validate_manifest", lambda **_kwargs: parent)
    transport = DirectoryTransport(durable, source_uri)
    return pause_path, common_path, durable, parent, transport, [job["job_id"] for job in historical_jobs]


def refresh_pause_hash(pause_path: Path, result_path: Path) -> None:
    pause = json.loads(pause_path.read_text(encoding="utf-8"))
    job_id = json.loads(result_path.read_text(encoding="utf-8"))["job_id"]
    pause["job_result_sha256"][job_id] = authority.sha256_file(result_path)
    write_json(pause_path, pause)


def accepting_validator(calls: list[str]):
    def validate(job: dict, job_root: Path) -> tuple[dict, Path]:
        calls.append(job["job_id"])
        assert {path.name for path in job_root.iterdir()} == restorer.JOB_FILES
        return {"job_id": job["job_id"]}, job_root / "predictions.npz"

    return validate


def test_exact_12_job_restore_writes_deterministic_receipt_without_compute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pause, common, _durable, _parent, transport, expected_ids = authority_fixture(
        tmp_path, monkeypatch
    )

    def compute_forbidden(*_args, **_kwargs):
        raise AssertionError("compute path invoked")

    for name in ("run_worker", "run_jobs", "run_all"):
        monkeypatch.setattr(restorer.p11, name, compute_forbidden)
    for name in ("run_global", "run_full", "run_best_k"):
        monkeypatch.setattr(restorer.p11.p8, name, compute_forbidden)
    monkeypatch.setattr(restorer.p11.p10, "run_coarse", compute_forbidden)

    calls: list[str] = []
    output = tmp_path / "owner-runtime" / "historical"
    receipt = restorer.restore_sequential_results(
        pause,
        common,
        output,
        transport=transport,
        result_validator=accepting_validator(calls),
        timestamp="2026-08-13T00:00:00+00:00",
    )
    assert receipt["status"] == restorer.RESTORE_STATUS
    assert receipt["restored_job_count"] == 12
    assert receipt["source_job_object_count"] == 36
    assert receipt["expected_job_ids"] == expected_ids
    assert receipt["observed_job_result_sha256"] == receipt["expected_job_result_sha256"]
    assert calls == expected_ids
    assert json.loads((output / restorer.RECEIPT_NAME).read_text()) == receipt
    assert set(receipt) == {
        "artifact_id",
        "canonical_subset_id",
        "common_authority_path",
        "common_authority_sha",
        "duplicate_job_count",
        "expected_job_count",
        "expected_job_ids",
        "expected_job_result_sha256",
        "foreign_job_count",
        "missing_job_count",
        "observed_job_result_sha256",
        "output_root",
        "parent_p11_manifest_sha",
        "representations",
        "restored_at",
        "restored_job_count",
        "seeds",
        "source_durable_prefix",
        "source_job_object_count",
        "source_pause_receipt_path",
        "source_pause_receipt_sha256",
        "status",
        "validation_status",
    }


def test_missing_job_is_rejected_before_destination_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pause, common, _durable, _parent, transport, _ids = authority_fixture(tmp_path, monkeypatch)
    keys = transport.list_keys("jobs/")
    transport.keys = keys[:-1]
    output = tmp_path / "missing"
    with pytest.raises(restorer.SequentialRestoreError, match="artifact set|job directory"):
        restorer.restore_sequential_results(pause, common, output, transport=transport)
    assert not output.exists()


@pytest.mark.parametrize(
    "extra_key, message",
    [
        ("DUPLICATE", "duplicate durable historical object key"),
        ("jobs/seed_03__global_mean/job_result.json", "foreign historical job"),
        ("jobs/../escape/job_result.json", "unsafe durable historical object path"),
    ],
)
def test_duplicate_foreign_or_unsafe_object_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    extra_key: str,
    message: str,
) -> None:
    pause, common, _durable, _parent, transport, _ids = authority_fixture(tmp_path, monkeypatch)
    keys = transport.list_keys("jobs/")
    transport.keys = keys + [keys[0] if extra_key == "DUPLICATE" else extra_key]
    with pytest.raises(restorer.SequentialRestoreError, match=message):
        restorer.restore_sequential_results(
            pause, common, tmp_path / "rejected", transport=transport
        )


@pytest.mark.parametrize(
    "field, value, message",
    [
        ("seed_index", 3, "seed index mismatch"),
        ("representation", "FOREIGN_REPRESENTATION", "representation mismatch"),
    ],
)
def test_wrong_seed_or_representation_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
    message: str,
) -> None:
    pause, common, durable, _parent, transport, expected_ids = authority_fixture(tmp_path, monkeypatch)
    result_path = durable / "jobs" / expected_ids[0] / "job_result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result[field] = value
    write_json(result_path, result)
    refresh_pause_hash(pause, result_path)
    with pytest.raises(restorer.SequentialRestoreError, match=message):
        restorer.restore_sequential_results(
            pause,
            common,
            tmp_path / f"wrong-{field}",
            transport=transport,
            result_validator=lambda *_args: None,
        )


def test_job_result_sha_mismatch_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pause, common, durable, _parent, transport, expected_ids = authority_fixture(tmp_path, monkeypatch)
    result_path = durable / "jobs" / expected_ids[0] / "job_result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["unexpected"] = True
    write_json(result_path, result)
    with pytest.raises(restorer.SequentialRestoreError, match="job-result SHA mismatch"):
        restorer.restore_sequential_results(
            pause, common, tmp_path / "sha-mismatch", transport=transport
        )


def test_parent_authority_mismatch_is_rejected_before_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pause, common, _durable, _parent, transport, _ids = authority_fixture(tmp_path, monkeypatch)
    document = json.loads(pause.read_text(encoding="utf-8"))
    document["parent_p11_manifest_sha"] = "0" * 64
    write_json(pause, document)
    output = tmp_path / "parent-mismatch"
    with pytest.raises(restorer.SequentialRestoreError, match="parent authority mismatch"):
        restorer.restore_sequential_results(pause, common, output, transport=transport)
    assert not output.exists()


def test_nonempty_or_artifact_directory_destination_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pause, common, _durable, _parent, transport, _ids = authority_fixture(tmp_path, monkeypatch)
    existing = tmp_path / "existing"
    existing.mkdir()
    (existing / "unrelated").write_text("preserve", encoding="utf-8")
    with pytest.raises(restorer.SequentialRestoreError, match="already exists"):
        restorer.restore_sequential_results(pause, common, existing, transport=transport)
    assert (existing / "unrelated").read_text(encoding="utf-8") == "preserve"

    fake_repo = tmp_path / "repo"
    monkeypatch.setattr(restorer, "OPERATIONAL_ROOT", fake_repo)
    unsafe = fake_repo / restorer.STUDY_RELATIVE / "runtime"
    with pytest.raises(restorer.SequentialRestoreError, match="Git experimental artifact"):
        restorer.restore_sequential_results(pause, common, unsafe, transport=transport)
    assert not unsafe.exists()
