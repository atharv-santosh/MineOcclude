from __future__ import annotations

import copy
from pathlib import Path

import pytest

from mineocclude.probes import p11_sharding as authority
from scripts import run_large_scale_no_wall_p11_shard as runner


def synthetic_parent() -> tuple[dict, str]:
    jobs = []
    for seed_index in range(49):
        seed = 10_000 + seed_index
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
                "seed": seed,
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


def frozen_shards() -> tuple[dict, str, list[dict]]:
    parent, parent_sha = synthetic_parent()
    shards = authority.build_shards(
        parent,
        parent_sha,
        [0, 1, 2],
        repository_branch="test-branch",
        implementation_commit_sha="a" * 40,
    )
    return parent, parent_sha, shards


def relock(document: dict) -> None:
    document["shard_manifest_sha"] = authority.shard_sha(document)


def test_exact_round_robin_partition_and_original_identities() -> None:
    parent, parent_sha, shards = frozen_shards()
    authority.validate_partition(parent, parent_sha, [0, 1, 2], shards)
    assert [len(shard["seed_indices"]) for shard in shards] == [10, 9, 9, 9, 9]
    assert shards[0]["seed_indices"] == list(range(3, 49, 5))
    assigned = [index for shard in shards for index in shard["seed_indices"]]
    assert len(assigned) == len(set(assigned)) == 46
    assert set(assigned) == set(range(3, 49))
    assert all(shard["expected_job_count"] == 4 * shard["expected_seed_count"] for shard in shards)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda shard: shard["seed_indices"].append(99), "unknown seed identity"),
        (lambda shard: shard["seed_indices"].append(shard["seed_indices"][0]), "duplicate seed assignment"),
        (lambda shard: shard["exact_original_job_ids"].append(shard["exact_original_job_ids"][0]), "duplicate job identity"),
        (lambda shard: shard["exact_original_job_ids"].pop(), "missing, foreign, or reordered representation job"),
        (lambda shard: shard.__setitem__("parent_p11_manifest_sha", "foreign"), "foreign parent manifest SHA"),
    ],
)
def test_malformed_shards_hard_fail(mutation, message: str) -> None:
    parent, parent_sha, shards = frozen_shards()
    shard = copy.deepcopy(shards[0])
    mutation(shard)
    relock(shard)
    with pytest.raises(authority.ShardAuthorityError, match=message):
        authority.validate_shard(shard, parent, parent_sha, completed_seed_indices=[0, 1, 2])


def test_completed_seed_cannot_be_recomputed() -> None:
    parent, parent_sha, shards = frozen_shards()
    shard = copy.deepcopy(shards[0])
    shard["seed_indices"][0] = 2
    relock(shard)
    with pytest.raises(authority.ShardAuthorityError, match="validated completed seed"):
        authority.validate_shard(shard, parent, parent_sha, completed_seed_indices=[0, 1, 2])


def test_unassigned_job_cannot_execute() -> None:
    _parent, _parent_sha, shards = frozen_shards()
    with pytest.raises(authority.ShardAuthorityError, match="unassigned job"):
        authority.require_assigned_job(shards[0], shards[1]["exact_original_job_ids"][0])


def test_shard_worker_delegates_to_unchanged_frozen_worker(monkeypatch) -> None:
    _parent, _parent_sha, shards = frozen_shards()
    observed: list[str] = []
    monkeypatch.setattr(runner.p11, "run_worker", observed.append)
    job_id = shards[0]["exact_original_job_ids"][0]
    runner.execute_assigned_worker(shards[0], job_id)
    assert observed == [job_id]


def test_resume_skips_already_validated_shard_jobs() -> None:
    parent, _parent_sha, shards = frozen_shards()
    first, second = shards[0]["exact_original_job_ids"][:2]
    latest = {first: {"state": "VALIDATED"}, second: {"state": "FAILED_RETRYABLE"}}
    pending = runner.resume_job_ids(shards[0], parent, latest)
    assert first not in pending
    assert second in pending
    assert set(pending) <= set(shards[0]["exact_original_job_ids"])


def test_each_shard_has_an_independent_mutable_namespace() -> None:
    parent, parent_sha, shards = frozen_shards()
    authority.validate_partition(parent, parent_sha, [0, 1, 2], shards)
    fields = ("local_result_root", "ledger_path", "progress_path", "log_path", "durable_output_prefix")
    for field in fields:
        values = [shard[field] for shard in shards]
        assert len(values) == len(set(values)) == 5
    assert all(Path(shard["ledger_path"]).parent == Path(shard["local_result_root"]) for shard in shards)


def test_overlap_and_non_round_robin_assignment_hard_fail() -> None:
    parent, parent_sha, shards = frozen_shards()
    changed = copy.deepcopy(shards)
    changed[1]["seed_indices"][0] = changed[0]["seed_indices"][0]
    relock(changed[1])
    with pytest.raises(authority.ShardAuthorityError):
        authority.validate_partition(parent, parent_sha, [0, 1, 2], changed)

