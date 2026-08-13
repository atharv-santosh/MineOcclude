from __future__ import annotations

import copy
import json
import shutil
import subprocess
import tarfile
from pathlib import Path

import numpy as np
import pytest

from mineocclude.probes import p11_sharding as authority
from scripts import bootstrap_large_scale_no_wall_p11_worker as bootstrap
from scripts import collect_large_scale_no_wall_p11_returns as collector
from scripts import run_large_scale_no_wall_p11_shard as runner
from scripts import validate_large_scale_no_wall_p11_merge as merger

REPO = Path(__file__).resolve().parents[2]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def synthetic_parent() -> tuple[dict, str]:
    jobs = []
    for seed_index in range(49):
        for representation in authority.REPRESENTATIONS:
            payload = {
                "alpha_grid": [0.1, 1.0, 10.0, 100.0],
                "assignment_sha256": f"assignment-{seed_index}",
                "best_k_grid": [1, 4, 8, 16, 32, 64, 128] if representation == "BEST_K_TOKENS" else None,
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
    parent = {
        "artifact_id": "synthetic-parent",
        "canonical_null_authority_sha256": "canonical-null",
        "expected_jobs": 196,
        "expected_seeds": 49,
        "jobs": jobs,
        "p10_manifest_sha256": authority.P10_COARSE_AUTHORITY_SHA,
        "prospective_null_authority_sha256": "prospective-null",
        "representations": list(authority.REPRESENTATIONS),
    }
    return parent, authority.frozen_json_file_sha256(parent)


def synthetic_authority(tmp_path: Path) -> tuple[Path, dict, list[dict]]:
    parent, parent_sha = synthetic_parent()
    shards = authority.build_shards(
        parent, parent_sha, [0, 1, 2],
        repository_branch="test-branch", implementation_commit_sha="a" * 40,
    )
    root = tmp_path / "authority"
    files = []
    for shard in shards:
        name = f"p11_shard_{shard['worker_slug']}.json"
        write_json(root / name, shard)
        files.append(name)
    common = {
        "parent_p11_manifest_sha": parent_sha,
        "completed_seed_indices": [0, 1, 2],
        "shard_manifest_files": files,
        "shard_manifest_shas": {item["worker_slug"]: item["shard_manifest_sha"] for item in shards},
    }
    common["common_authority_sha"] = authority.common_sha(common)
    common_path = root / "common_authority.json"
    write_json(common_path, common)
    return common_path, parent, shards


def complete_ledger(path: Path, shard: dict, parent: dict, validated: set[str] | None = None) -> None:
    validated = set(shard["exact_original_job_ids"]) if validated is None else validated
    jobs = {job["job_id"]: job for job in parent["jobs"]}
    for job_id in shard["exact_original_job_ids"]:
        job = jobs[job_id]
        runner.append_jsonl(path, {
            "attempt": 0, "event_at": "t0", "identity_sha256": job["identity_sha256"],
            "job_id": job_id, "seed": job["seed"], "seed_index": job["seed_index"], "state": "PENDING",
        })
        if job_id in validated:
            runner.append_jsonl(path, {
                "attempt": 1, "event_at": "t1", "identity_sha256": job["identity_sha256"],
                "job_id": job_id, "seed": job["seed"], "seed_index": job["seed_index"], "state": "RUNNING",
            })
            runner.append_jsonl(path, {
                "attempt": 1, "event_at": "t2", "identity_sha256": job["identity_sha256"],
                "job_id": job_id, "seed": job["seed"], "seed_index": job["seed_index"], "state": "VALIDATED",
            })


class DirectoryControlTransport:
    def __init__(self, root: Path) -> None:
        self.root = root

    def download_file(self, relative: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.root / relative, destination)

    def download_tree(self, relative: str, destination: Path) -> None:
        shutil.copytree(self.root / relative, destination)

    def list_keys(self, relative_prefix: str) -> list[str]:
        base = self.root / relative_prefix
        return [path.relative_to(self.root).as_posix() for path in base.rglob("*") if path.is_file()]


def durable_restore_fixture(tmp_path: Path) -> tuple[dict, dict, DirectoryControlTransport, str]:
    parent, parent_sha = synthetic_parent()
    shard = authority.build_shards(
        parent, parent_sha, [0, 1, 2],
        repository_branch="test-branch", implementation_commit_sha="a" * 40,
    )[0]
    target = tmp_path / "lost-nvme" / "me"
    shard = copy.deepcopy(shard)
    shard["local_result_root"] = str(target)
    shard["ledger_path"] = str(target / "p11_shard_me_ledger.jsonl")
    shard["progress_path"] = str(target / "p11_shard_me_progress.json")
    source = tmp_path / "durable"
    first = shard["exact_original_job_ids"][0]
    write_json(source / "shard_manifest.json", shard)
    complete_ledger(source / "p11_shard_me_ledger.jsonl", shard, parent, {first})
    write_json(source / "p11_shard_me_progress.json", {
        "worker_name": shard["worker_name"], "shard_manifest_sha": shard["shard_manifest_sha"],
        "validated_jobs": 1,
    })
    write_json(source / "jobs" / first / "job_result.json", {"job_id": first, "fixture": True})
    write_json(source / runner.CONTROL_RECEIPT_NAME, runner.durable_control_receipt(shard, parent, source))
    return shard, parent, DirectoryControlTransport(source), first


def test_fresh_bootstrap_separates_exact_authorities(tmp_path: Path) -> None:
    current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    receipt = bootstrap.bootstrap_worker(str(REPO), tmp_path / "worker", current, "alan")
    assert receipt["moving_branch_head_used"] is False
    assert receipt["scientific_implementation_commit"] == runner.SCIENTIFIC_IMPLEMENTATION_COMMIT
    assert receipt["immutable_handoff_commit"] == runner.IMMUTABLE_HANDOFF_COMMIT
    assert receipt["operational_handoff_commit"] == current
    assert receipt["scientific_branch"] == "exploration/large-scale-no-wall-scaling-best-k-v0-1"
    assert Path(receipt["operational_root"]) != Path(receipt["scientific_root"])


def test_original_manifests_and_seed_assignments_remain_byte_frozen() -> None:
    expected = {
        "common_authority.json": "50b51d54fa1b74efc50e47f4b47754e26ed6b08200058dbd312953b008630bac",
        "alan/shard_manifest.json": "4b5bc990b4b95a50ffaf13ba1baf1a9b832d880fcfc20e48bcb6c0f5473b74df",
        "atharv/shard_manifest.json": "d501ec9cd219375f8f16f84dfee44329667bff9119102b51dc08bfb424e5601e",
        "ayman/shard_manifest.json": "05428029293b9d9f8cd5ac4205de0adfbe0927c27595fd631ccd74b52ee9a420",
        "me/shard_manifest.json": "b6fc8d69803a712d20f93b0b75563712a0e5bec0ff4aa6179c0f94de6a1d7ab1",
        "sahil/shard_manifest.json": "8c2aff40358ff4104977d24bf6132cdb8ce824f57264febc38b54b2b8288afb4",
    }
    root = REPO / "p11_distributed_handoff"
    for relative, digest in expected.items():
        assert authority.sha256_file(root / relative) == digest


@pytest.mark.parametrize("takeover", [False, True])
def test_full_nvme_restore_and_whole_shard_takeover_skip_validated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, takeover: bool
) -> None:
    shard, parent, transport, first = durable_restore_fixture(tmp_path)
    monkeypatch.setattr(runner, "validate_result", lambda job: {"job_id": job["job_id"]})
    attestation = None
    if takeover:
        attestation = tmp_path / "stopped.json"
        write_json(attestation, {
            "process_proven_stopped": True,
            "original_worker_name": shard["worker_name"],
            "shard_manifest_sha": shard["shard_manifest_sha"],
            "durable_output_prefix": shard["durable_output_prefix"],
            "replacement_operator": "replacement-human",
            "observed_stopped_at": "2026-08-11T00:00:00Z",
        })
    receipt = runner.restore_durable_state(
        shard, parent, operator_name="replacement-human" if takeover else "original-human",
        takeover_attestation=attestation, transport=transport,
    )
    assert receipt["takeover"] is takeover
    assert receipt["restored_validated_job_count"] == 1
    latest, _counts, _attempts = runner.latest_ledger(Path(shard["ledger_path"]))
    pending = runner.resume_job_ids(shard, parent, latest)
    assert first not in pending
    assert set(pending) == set(shard["exact_original_job_ids"]) - {first}


def test_restore_rejects_foreign_or_ambiguous_durable_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shard, parent, transport, _first = durable_restore_fixture(tmp_path)
    monkeypatch.setattr(runner, "validate_result", lambda job: {"job_id": job["job_id"]})
    write_json(transport.root / "jobs" / "foreign-job" / "job_result.json", {})
    with pytest.raises(authority.ShardAuthorityError, match="foreign durable jobs"):
        runner.restore_durable_state(
            shard, parent, operator_name="operator", transport=transport,
        )


def make_return_packages(
    durable: Path, parent: dict, shards: list[dict]
) -> None:
    jobs = {job["job_id"]: job for job in parent["jobs"]}
    for shard in shards:
        slug = shard["worker_slug"]
        build = durable / f"build-{slug}"
        write_json(build / "shard_manifest.json", shard)
        ledger_name = Path(shard["ledger_path"]).name
        complete_ledger(build / ledger_name, shard, parent)
        write_json(build / Path(shard["progress_path"]).name, {
            "worker_name": shard["worker_name"], "shard_manifest_sha": shard["shard_manifest_sha"],
            "validated_jobs": shard["expected_job_count"],
        })
        hashes = {}
        for job_id in shard["exact_original_job_ids"]:
            result = build / "jobs" / job_id / "job_result.json"
            write_json(result, {"job_id": job_id, "identity_sha256": jobs[job_id]["identity_sha256"]})
            hashes[job_id] = authority.sha256_file(result)
        write_json(build / "completion_receipt.json", {
            "worker_name": shard["worker_name"], "shard_manifest_sha": shard["shard_manifest_sha"],
            "parent_p11_manifest_sha": shard["parent_p11_manifest_sha"], "job_result_sha256": hashes,
        })
        return_root = durable / slug / "return"
        return_root.mkdir(parents=True)
        package_name = f"p11_shard_{slug}_return.tar.gz"
        package = return_root / package_name
        with tarfile.open(package, "w:gz") as archive:
            for name in ("jobs", "shard_manifest.json", ledger_name, Path(shard["progress_path"]).name, "completion_receipt.json"):
                archive.add(build / name, arcname=name)
        write_json(return_root / "package_upload_receipt.json", {
            "status": "PASS_P11_SHARD_COMPLETE_VALIDATED",
            "worker_name": shard["worker_name"], "shard_manifest_sha": shard["shard_manifest_sha"],
            "parent_p11_manifest_sha": shard["parent_p11_manifest_sha"],
            "durable_output_prefix": shard["durable_output_prefix"],
            "package_path": str(build / package_name), "package_byte_count": package.stat().st_size,
            "package_sha256": authority.sha256_file(package),
            "package_s3_uri": (
                f"s3://{collector.p11.p8.S3_BUCKET}/{shard['durable_output_prefix']}/return/{package_name}"
            ),
        })


def test_owner_collection_validates_checksums_and_populates_exact_five_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common_path, parent, shards = synthetic_authority(tmp_path)
    parent_path = tmp_path / "p11_run_manifest.json"
    write_json(parent_path, parent)
    durable = tmp_path / "durable"
    make_return_packages(durable, parent, shards)
    monkeypatch.setattr(collector.p11, "MANIFEST", parent_path)
    monkeypatch.setattr(collector.p11, "validate_manifest", lambda **_kwargs: parent)
    monkeypatch.setattr(collector.merge, "validate_result_at", lambda job, path: ({"job_id": job["job_id"]}, path / "predictions.npz"))
    output = tmp_path / "collected"
    receipt = collector.collect_return_packages(common_path, output, local_durable_root=durable)
    assert receipt["collected_worker_count"] == 5
    assert receipt["collected_job_count"] == 184
    assert {path.name for path in output.iterdir() if path.is_dir()} == {"me", "alan", "atharv", "ayman", "sahil"}


def test_owner_collection_rejects_package_checksum_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common_path, parent, shards = synthetic_authority(tmp_path)
    parent_path = tmp_path / "p11_run_manifest.json"
    write_json(parent_path, parent)
    durable = tmp_path / "durable"
    make_return_packages(durable, parent, shards)
    receipt_path = durable / "alan/return/package_upload_receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["package_sha256"] = "0" * 64
    write_json(receipt_path, receipt)
    monkeypatch.setattr(collector.p11, "MANIFEST", parent_path)
    monkeypatch.setattr(collector.p11, "validate_manifest", lambda **_kwargs: parent)
    monkeypatch.setattr(collector.merge, "validate_result_at", lambda job, path: ({}, path))
    with pytest.raises(collector.CollectionError, match="checksum mismatch"):
        collector.collect_return_packages(common_path, tmp_path / "collected", local_durable_root=durable)


def test_safe_extract_rejects_path_traversal(tmp_path: Path) -> None:
    _common, _parent, shards = synthetic_authority(tmp_path)
    archive = tmp_path / "unsafe.tar.gz"
    payload = tmp_path / "payload"
    payload.write_text("unsafe", encoding="utf-8")
    with tarfile.open(archive, "w:gz") as stream:
        stream.add(payload, arcname="../escape")
    with pytest.raises(collector.CollectionError, match="unsafe return archive path"):
        collector.safe_extract_return(archive, tmp_path / "extract", shards[0])


def test_exact_five_root_gate_on_controlled_196_job_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common_path, parent, shards = synthetic_authority(tmp_path)
    parent_path = tmp_path / "p11_run_manifest.json"
    write_json(parent_path, parent)
    sequential = tmp_path / "sequential"
    roots = {shard["worker_slug"]: tmp_path / shard["worker_slug"] for shard in shards}
    assignment = {}
    for job in parent["jobs"]:
        if job["seed_index"] < 3:
            assignment[job["job_id"]] = sequential
    for shard in shards:
        for job_id in shard["exact_original_job_ids"]:
            assignment[job_id] = roots[shard["worker_slug"]]
    for job_id, root in assignment.items():
        (root / "jobs" / job_id).mkdir(parents=True)
    monkeypatch.setattr(merger.p11, "MANIFEST", parent_path)
    monkeypatch.setattr(merger.p11, "validate_manifest", lambda **_kwargs: parent)
    monkeypatch.setattr(merger.p11.p8, "JobContext", lambda: type("Context", (), {
        "test_ids": ["row"], "targets": lambda self, ids: np.array([0.0]),
        "layouts": lambda self, ids: ["layout"],
        "access": type("Access", (), {"row_ordinals": lambda self, ids: [0]})(),
    })())
    monkeypatch.setattr(merger, "validate_result_at", lambda job, path: ({
        "job_id": job["job_id"], "representation": job["representation"], "metrics": {"fixture": True},
    }, path / "predictions.npz"))
    monkeypatch.setattr(merger.np, "load", lambda *args, **kwargs: {"row_ordinals": np.array([0]), "predictions": np.array([0.0])})
    monkeypatch.setattr(merger, "metric_document", lambda *args, **kwargs: {"fixture": True})
    receipt = merger.validate_merge(common_path, sequential, roots)
    assert receipt["validated_seed_count"] == 49
    assert receipt["validated_job_count"] == 196
    assert all(receipt[key] == 0 for key in (
        "missing_seed_count", "extra_seed_count", "duplicate_seed_count", "foreign_seed_count",
        "partial_seed_count", "missing_job_count", "extra_job_count",
        "duplicate_job_count", "foreign_job_count",
    ))


def test_canonical_distributed_aggregation_matches_frozen_builder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    results = [
        {
            "representation": representation, "seed_index": seed_index, "seed": 10_000 + seed_index,
            "metrics": {"equal_layout_macro": {"r2": float(seed_index) / 100.0}},
        }
        for seed_index in range(49) for representation in authority.REPRESENTATIONS
    ]
    gate = {
        "status": "PASS_49_SEEDS_196_JOBS_SAFE_FOR_CANONICAL_AGGREGATION",
        "parent_p11_manifest_sha": "parent",
        "validated_seed_count": 49, "validated_job_count": 196, "representations_per_seed": 4,
        "missing_seed_count": 0, "extra_seed_count": 0, "duplicate_seed_count": 0, "foreign_seed_count": 0,
        "partial_seed_count": 0, "missing_job_count": 0, "extra_job_count": 0,
        "duplicate_job_count": 0, "foreign_job_count": 0,
        "aggregation_performed": False,
        "future_canonical_p_formula": "(1 + count(null >= observed)) / (49 + 1)",
    }
    monkeypatch.setattr(merger, "validate_merge_with_results", lambda *args, **kwargs: (gate, results))
    monkeypatch.setattr(merger.p11, "observed_statistics", lambda: {name: 0.245 for name in authority.REPRESENTATIONS})
    expected = merger.p11.build_result(results)
    output = tmp_path / "aggregate"
    durable = tmp_path / "durable"
    receipt = merger.aggregate_distributed(
        tmp_path / "common", tmp_path / "sequential", {}, output, f"file://{durable}",
    )
    observed = json.loads((output / "prospective_target_null_results.json").read_text())
    assert observed == expected
    assert observed["null_replicates"] == 49
    assert observed["empirical_upper_tail_formula"] == "(1 + count(null >= observed)) / (49 + 1)"
    assert receipt["package_sha256"] == authority.sha256_file(durable / "p11_canonical_distributed_aggregation.tar.gz")
