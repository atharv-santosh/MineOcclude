"""Tests for real production input materialization/ingestion (CLI finalization).

Every real cross-role commit hash this module cites (Person B's fold/
oracle-target/source-context manifests, Person A's frame manifest,
Person C's capture packages) was independently verified via direct
``git show <commit>:<path> | sha256sum`` before any code here was
written -- these tests exercise the generic mechanics with synthetic
fixtures and a throwaway local Git repository, never by fetching or
depending on another role's real branch being present in this checkout.

No baseline is fit, no metric is computed, and no U4 path is touched
anywhere in this file.
"""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path

import pytest

from mineocclude.baselines import production_input_ingest as ingest


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )


@pytest.fixture
def throwaway_git_repo(tmp_path: Path) -> tuple[Path, str]:
    """A tiny, isolated Git repo with one committed file, for materialize tests."""

    repo = tmp_path / "throwaway_repo"
    repo.mkdir()
    _git("init", "-q", cwd=repo)
    _git("config", "user.email", "test@example.com", cwd=repo)
    _git("config", "user.name", "Test", cwd=repo)
    committed = repo / "data" / "committed_artifact.json"
    committed.parent.mkdir(parents=True)
    committed.write_text('{"hello": "world"}', encoding="utf-8")
    _git("add", "-A", cwd=repo)
    _git("commit", "-q", "-m", "add artifact", cwd=repo)
    commit = _git("rev-parse", "HEAD", cwd=repo).stdout.strip()
    return repo, commit


def test_verify_raw_bytes_all_clear(tmp_path):
    path = tmp_path / "file.bin"
    payload = b"abcdef"
    path.write_bytes(payload)
    expected_sha256 = hashlib.sha256(payload).hexdigest()
    assert ingest.verify_raw_bytes(
        path, expected_sha256=expected_sha256, expected_byte_size=len(payload)
    ) == ()


def test_verify_raw_bytes_missing_file(tmp_path):
    errors = ingest.verify_raw_bytes(
        tmp_path / "missing.bin", expected_sha256="a" * 64, expected_byte_size=1
    )
    assert errors == ("file_not_found",)


def test_verify_raw_bytes_size_and_hash_mismatch(tmp_path):
    path = tmp_path / "file.bin"
    path.write_bytes(b"abcdef")
    errors = ingest.verify_raw_bytes(
        path, expected_sha256="f" * 64, expected_byte_size=999
    )
    assert any(error.startswith("byte_size_mismatch") for error in errors)
    assert any(error.startswith("sha256_mismatch") for error in errors)


def test_load_and_verify_json_artifact_round_trips(tmp_path):
    payload = {"a": 1, "b": [1, 2, 3]}
    raw = json.dumps(payload).encode("utf-8")
    path = tmp_path / "artifact.json"
    path.write_bytes(raw)
    loaded = ingest.load_and_verify_json_artifact(
        path, expected_sha256=hashlib.sha256(raw).hexdigest(), expected_byte_size=len(raw)
    )
    assert loaded == payload


def test_load_and_verify_json_artifact_fails_closed_on_tamper(tmp_path):
    raw = b'{"a": 1}'
    path = tmp_path / "artifact.json"
    path.write_bytes(raw)
    with pytest.raises(ingest.ProductionInputIngestError):
        ingest.load_and_verify_json_artifact(
            path, expected_sha256="0" * 64, expected_byte_size=len(raw)
        )


def test_materialize_git_committed_artifact_reads_and_verifies(throwaway_git_repo, tmp_path):
    repo, commit = throwaway_git_repo
    raw = (repo / "data" / "committed_artifact.json").read_bytes()
    output_path = tmp_path / "materialized" / "artifact.json"

    result_path = ingest.materialize_git_committed_artifact(
        repo_root=repo,
        commit=commit,
        repo_relative_path="data/committed_artifact.json",
        output_path=output_path,
        expected_sha256=hashlib.sha256(raw).hexdigest(),
        expected_byte_size=len(raw),
    )

    assert result_path == output_path
    assert output_path.read_bytes() == raw
    # The source file itself must be untouched.
    assert (repo / "data" / "committed_artifact.json").read_bytes() == raw


def test_materialize_git_committed_artifact_fails_closed_on_hash_mismatch(
    throwaway_git_repo, tmp_path
):
    repo, commit = throwaway_git_repo
    with pytest.raises(ingest.ProductionInputIngestError, match="raw-byte"):
        ingest.materialize_git_committed_artifact(
            repo_root=repo,
            commit=commit,
            repo_relative_path="data/committed_artifact.json",
            output_path=tmp_path / "out.json",
            expected_sha256="f" * 64,
            expected_byte_size=999,
        )
    assert not (tmp_path / "out.json").exists()


def test_materialize_git_committed_artifact_fails_closed_on_missing_path(
    throwaway_git_repo, tmp_path
):
    repo, commit = throwaway_git_repo
    with pytest.raises(ingest.ProductionInputIngestError, match="failed to read"):
        ingest.materialize_git_committed_artifact(
            repo_root=repo,
            commit=commit,
            repo_relative_path="data/does_not_exist.json",
            output_path=tmp_path / "out.json",
            expected_sha256="f" * 64,
            expected_byte_size=1,
        )


def test_verify_oracle_target_manifest_structure_reports_every_mismatch():
    errors = ingest.verify_oracle_target_manifest_structure(
        {
            "target_schema_version": "wrong",
            "config_hash": "wrong",
            "join_key": ["something_else"],
            "row_count": 3,
            "accepted_pilot_ids": ["not_frozen"],
            "u4_output_inspected": True,
            "rows": [],
        }
    )
    assert "target_schema_version_mismatch" in errors
    assert "config_hash_mismatch" in errors
    assert "join_key_mismatch" in errors
    assert "row_count_mismatch" in errors
    assert "accepted_pilot_ids_mismatch" in errors
    assert "u4_access_not_forbidden" in errors
    assert "rows_count_mismatch" in errors


def test_verify_oracle_target_manifest_structure_not_a_mapping():
    assert ingest.verify_oracle_target_manifest_structure([1, 2, 3]) == ("document_not_mapping",)


def test_build_oracle_target_lookups_filters_non_accepted_and_null_log_sigma():
    document = {
        "rows": [
            {
                "trajectory_id": "layout_00_ep9403",
                "model_frame_idx": 0,
                "status": "accepted",
                "mu_oracle_blocks": 1.5,
                "log_sigma_oracle": -2.0,
            },
            {
                "trajectory_id": "layout_00_ep9403",
                "model_frame_idx": 1,
                "status": "accepted",
                "mu_oracle_blocks": 2.5,
                "log_sigma_oracle": None,
            },
            {
                "trajectory_id": "layout_00_ep9403",
                "model_frame_idx": 2,
                "status": "not_admitted",
                "mu_oracle_blocks": 99.0,
                "log_sigma_oracle": 99.0,
            },
        ]
    }
    mu_by_key, log_sigma_by_key = ingest.build_oracle_target_lookups(document)
    assert mu_by_key == {
        ("layout_00_ep9403", 0): 1.5,
        ("layout_00_ep9403", 1): 2.5,
    }
    assert log_sigma_by_key == {("layout_00_ep9403", 0): -2.0}


def test_build_scripted_context_by_trajectory_consistent():
    document = {
        "rows": [
            {
                "trajectory_id": "layout_00_ep9403",
                "layout_id": "layout_00",
                "v": 1.0,
                "q": 0.02,
                "duration": 12.4,
                "seed": 42,
            },
            {
                "trajectory_id": "layout_00_ep9403",
                "layout_id": "layout_00",
                "v": 1.0,
                "q": 0.02,
                "duration": 12.4,
                "seed": 42,
            },
        ]
    }
    result = ingest.build_scripted_context_by_trajectory(document)
    assert result == {
        "layout_00_ep9403": {
            "layout_id": "layout_00",
            "v_scripted_blocks_per_s": 1.0,
            "q_scripted_blocks2_per_s": 0.02,
            "duration_seconds": 12.4,
            "seed": 42,
        }
    }


def test_build_scripted_context_by_trajectory_rejects_inconsistency():
    document = {
        "rows": [
            {"trajectory_id": "t", "layout_id": "layout_00", "v": 1.0, "q": 0.02, "duration": 1.0, "seed": 1},
            {"trajectory_id": "t", "layout_id": "layout_00", "v": 2.0, "q": 0.02, "duration": 1.0, "seed": 1},
        ]
    }
    with pytest.raises(ingest.ProductionInputIngestError, match="inconsistent"):
        ingest.build_scripted_context_by_trajectory(document)


def _write_capture_package(path: Path, *, trajectory_id: str) -> bytes:
    document = {
        "trajectory_id": trajectory_id,
        "streams": {
            "frame_map": [
                {"trajectory_id": trajectory_id, "model_frame_idx": 0},
                {"trajectory_id": trajectory_id, "model_frame_idx": 1},
            ],
            "server_state": [
                {
                    "trajectory_id": trajectory_id,
                    "model_frame_idx": 0,
                    "state": {"wall_parallel_position_blocks": 0.0},
                },
                {
                    "trajectory_id": trajectory_id,
                    "model_frame_idx": 1,
                    "state": {"wall_parallel_position_blocks": 1.0},
                },
            ],
            "visibility": [
                {"trajectory_id": trajectory_id, "model_frame_idx": 0, "visibility": "visible"},
                {"trajectory_id": trajectory_id, "model_frame_idx": 1, "visibility": "occluded"},
            ],
        },
    }
    raw = json.dumps(document).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def test_load_capture_package_round_trips(tmp_path):
    path = tmp_path / "root" / "capture_package_v0_1.json"
    raw = _write_capture_package(path, trajectory_id="layout_00_ep9403")
    document = ingest.load_capture_package(
        source_context_root=tmp_path / "root",
        trajectory_id="layout_00_ep9403",
        expected_reference={
            "path": "capture_package_v0_1.json",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "byte_size": len(raw),
        },
    )
    assert document["trajectory_id"] == "layout_00_ep9403"


def test_load_capture_package_rejects_trajectory_id_mismatch(tmp_path):
    path = tmp_path / "root" / "capture_package_v0_1.json"
    raw = _write_capture_package(path, trajectory_id="wrong_trajectory")
    with pytest.raises(ingest.ProductionInputIngestError, match="trajectory_id mismatch"):
        ingest.load_capture_package(
            source_context_root=tmp_path / "root",
            trajectory_id="layout_00_ep9403",
            expected_reference={
                "path": "capture_package_v0_1.json",
                "sha256": hashlib.sha256(raw).hexdigest(),
                "byte_size": len(raw),
            },
        )


def test_extract_visible_positions_orders_by_frame_and_filters_hidden():
    capture_package = {
        "streams": {
            "server_state": [
                {"model_frame_idx": 2, "state": {"wall_parallel_position_blocks": 2.0}},
                {"model_frame_idx": 0, "state": {"wall_parallel_position_blocks": 0.0}},
                {"model_frame_idx": 1, "state": {"wall_parallel_position_blocks": 1.0}},
            ],
            "visibility": [
                {"model_frame_idx": 0, "visibility": "visible"},
                {"model_frame_idx": 1, "visibility": "occluded"},
                {"model_frame_idx": 2, "visibility": "visible"},
            ],
        }
    }
    assert ingest.extract_visible_positions(capture_package) == [0.0, 2.0]


def test_build_all_trajectory_contexts_end_to_end_synthetic(tmp_path, monkeypatch):
    source_contexts = (
        {
            "trajectory_id": "traj_a",
            "capture_package": {"path": "traj_a/capture_package_v0_1.json"},
        },
        {
            "trajectory_id": "traj_b",
            "capture_package": {"path": "traj_b/capture_package_v0_1.json"},
        },
    )
    root = tmp_path / "source_contexts"
    references = []
    for entry in source_contexts:
        path = root / entry["capture_package"]["path"]
        raw = _write_capture_package(path, trajectory_id=entry["trajectory_id"])
        references.append(
            {
                **entry,
                "capture_package": {
                    "path": entry["capture_package"]["path"],
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "byte_size": len(raw),
                },
            }
        )
    monkeypatch.setattr(ingest, "FROZEN_SOURCE_CONTEXTS", tuple(references))

    oracle_target_document = {
        "rows": [
            {
                "trajectory_id": trajectory_id,
                "layout_id": "layout_00" if trajectory_id == "traj_a" else "layout_01",
                "v": 1.0,
                "q": 0.02,
                "duration": 1.0,
                "seed": 7,
            }
            for trajectory_id in ("traj_a", "traj_b")
        ]
    }
    fold_manifest = {
        "memberships": [
            {"trajectory_id": "traj_a", "model_frame_idx": 0, "fold_idx": 1, "layout_id": "layout_00"},
            {"trajectory_id": "traj_a", "model_frame_idx": 1, "fold_idx": 1, "layout_id": "layout_00"},
            {"trajectory_id": "traj_b", "model_frame_idx": 0, "fold_idx": 2, "layout_id": "layout_01"},
            {"trajectory_id": "traj_b", "model_frame_idx": 1, "fold_idx": 2, "layout_id": "layout_01"},
        ]
    }

    def fake_attach(contexts, *, fold_manifest):
        from dataclasses import replace

        fold_by_key = {
            (m["trajectory_id"], m["model_frame_idx"]): m["fold_idx"]
            for m in fold_manifest["memberships"]
        }
        return [
            replace(ctx, fold=fold_by_key[(ctx.trajectory_id, ctx.model_frame_idx)])
            for ctx in contexts
        ]

    monkeypatch.setattr(ingest, "attach_b_fold_assignments", fake_attach)

    contexts, visible_positions = ingest.build_all_trajectory_contexts(
        source_context_root=root,
        oracle_target_document=oracle_target_document,
        fold_manifest=fold_manifest,
        config_hash="c" * 64,
    )

    assert len(contexts) == 4
    assert {ctx.trajectory_id for ctx in contexts} == {"traj_a", "traj_b"}
    assert all(ctx.fold in (1, 2) for ctx in contexts)
    assert visible_positions == {"traj_a": [0.0], "traj_b": [0.0]}


def test_build_all_trajectory_contexts_requires_scripted_context(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ingest,
        "FROZEN_SOURCE_CONTEXTS",
        ({"trajectory_id": "traj_missing", "capture_package": {"path": "x.json"}},),
    )
    with pytest.raises(ingest.ProductionInputIngestError, match="no scripted context"):
        ingest.build_all_trajectory_contexts(
            source_context_root=tmp_path,
            oracle_target_document={"rows": []},
            fold_manifest={"memberships": []},
            config_hash="c" * 64,
        )


def test_build_pixel_features_by_key_decodes_real_float32_payloads(tmp_path):
    frame_root = tmp_path / "frames"
    relative_path = "traj_a/000000.f32le"
    full_path = frame_root / relative_path
    full_path.parent.mkdir(parents=True)
    values = [0.5, -1.0, 2.25]
    full_path.write_bytes(struct.pack(f"<{len(values)}f", *values))

    frame_manifest = {
        "records": [
            {
                "trajectory_id": "traj_a",
                "model_frame_idx": 0,
                "output_relative_path": relative_path,
            }
        ]
    }
    features = ingest.build_pixel_features_by_key(
        frame_manifest=frame_manifest, frame_root=frame_root
    )
    assert features[("traj_a", 0)] == pytest.approx(values)


def test_build_input_manifest_hash_and_fit_manifest_hash_are_deterministic_and_distinct():
    execution_manifest = {
        "direct_inputs": {"a": 1},
        "source_contexts": [{"trajectory_id": "x"}],
        "baseline_families": [{"family_id": "last_seen"}],
    }
    input_hash_1 = ingest.build_input_manifest_hash(execution_manifest)
    input_hash_2 = ingest.build_input_manifest_hash(execution_manifest)
    fit_hash = ingest.build_fit_manifest_hash(execution_manifest)
    assert input_hash_1 == input_hash_2
    assert len(input_hash_1) == 64
    assert len(fit_hash) == 64
    assert input_hash_1 != fit_hash

    changed_manifest = {**execution_manifest, "direct_inputs": {"a": 2}}
    assert ingest.build_input_manifest_hash(changed_manifest) != input_hash_1
