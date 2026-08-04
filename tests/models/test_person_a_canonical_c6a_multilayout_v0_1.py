from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import numpy
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/prepare_person_a_phase6_canonical_multilayout.py"
STATUS_ROOT = ROOT / "docs/status/person_a_canonical_c6a_multilayout_preparation_v0_1"
SELECTION = STATUS_ROOT / "selection_record.json"
INPUT_ROOT = (
    ROOT / "data/handoff_a/person_a_canonical_c6a_multilayout_sagemaker_input_v0_1"
)
INPUT_MANIFEST = INPUT_ROOT / "bundle_manifest.json"
INPUT_SHA256 = "ff7801c1a331f173bc5fc197454889b72d8554a8e31b5a88731de8eb7d9ed987"
PROMPT = STATUS_ROOT / "sagemaker_continuation_prompt.txt"
PROMPT_SHA256 = "4d5217733137657b58093a0309a3136dcf1824c1473fa01e72d84e6544f19299"
EXISTING_OUTPUT = ROOT / (
    "docs/status/phase6_runtime/"
    "person-a-canonical-c6a-layout-01-ep12602-seed-20260725-retry-"
    "20260804T193204Z-package-retry-20260804T193627Z"
)


def _load_module():
    specification = importlib.util.spec_from_file_location(
        "person_a_canonical_c6a_multilayout_test", SCRIPT
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


multi = _load_module()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _synthetic_output(root: Path, layout: str, episode: int) -> Path:
    trajectory = f"{layout}_ep{episode}"
    chunks = []
    rows = []
    for layer in range(20):
        chunk_id = f"chunk-{layer}"
        chunk_path = root / "activation_store/chunks" / f"{chunk_id}.npy"
        chunk_path.parent.mkdir(parents=True, exist_ok=True)
        chunk_path.write_bytes(f"{trajectory}:{layer}".encode())
        chunks.append(
            {
                "byte_size": chunk_path.stat().st_size,
                "chunk_id": chunk_id,
                "layer_idx": layer,
                "path": f"chunks/{chunk_id}.npy",
                "row_count": 60,
                "sha256": _sha256(chunk_path),
            }
        )
        for frame in range(60):
            rows.append(
                {
                    "activation_chunk_id": chunk_id,
                    "chunk_row_idx": frame,
                    "global_model_frame_idx": frame,
                    "hook_site": "decoder_layer_output_residual_stream",
                    "layer_idx": layer,
                    "run_id": f"run-{trajectory}",
                    "source_frame_id": f"{trajectory}:render_frame:{frame}",
                    "trajectory_id": trajectory,
                }
            )
    index_path = root / "activation_store/indexes/index.json"
    _write(
        index_path,
        {
            "chunks": chunks,
            "format_version": "person-a-activation-index-v2",
            "index_rows": rows,
            "run_status": "completed",
        },
    )
    _write(root / "accepted_pilot_manifest.json", {"trajectory_id": trajectory})
    _write(
        root / "step6_5.json",
        {
            "result": {
                "direct_pooling_audit": "PASS",
                "repeatability_maximum_absolute_difference": 0.0,
                "source_identity_join_failure_count": 0,
                "status": "PASS",
            }
        },
    )
    common = {
        "exact_source_identity_joins": {"status": "PASS"},
        "expected_activation_row_count": 1200,
        "grouping": {"key": "layout_id", "value": layout},
        "trajectory_id": trajectory,
    }
    _write(
        root / "person_a_to_person_b_canonical_pilot_handoff.json",
        {
            **common,
            "direct_pooling_validation": "PASS",
            "status": "READY_FOR_PERSON_B_CONSUMPTION",
        },
    )
    _write(
        root / "person_a_to_person_e_canonical_provenance_handoff.json",
        {**common, "status": "READY_FOR_PERSON_E_PROVENANCE_CONSUMPTION"},
    )
    _write(
        root / "terminal_execution_receipt.json",
        {"process_exit_status": 0, "status": "PASS"},
    )
    _write(
        root / "output_bundle_manifest.json",
        {
            "activation_index": "activation_store/indexes/index.json",
            "episode_id": episode,
            "schema_version": "person-a-canonical-sagemaker-output-bundle-v0.1",
            "status": "READY_FOR_LOCAL_RETRIEVAL",
            "trajectory_id": trajectory,
        },
    )
    inventory_rows = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        inventory_rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "role": "test",
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
            }
        )
    _write(root / "sha256_inventory.json", {"files": inventory_rows})
    return root


def test_frozen_blocker_and_selection_are_exact() -> None:
    document = json.loads(SELECTION.read_bytes())
    assert document["frozen_person_b_requirements"] == {
        "five_layouts_and_five_trajectories_sufficient": True,
        "grouping_key": "layout_id",
        "inner_fold_count": 4,
        "label_requirements": (
            "x_true_blocks from finite canonical_server_state.axis_pos on 60 fully "
            "geometric-visible NO_WALL frames with nonzero position range"
        ),
        "outer_fold_count": 5,
        "required_distinct_layout_count": 5,
        "required_distinct_trajectory_count": 5,
        "shuffled_control": {
            "minimum_trajectory_count": 2,
            "permutation_count": 999,
            "permutation_p_value": "add_one_greater_or_equal",
            "permutation_seed": 20260720,
            "permutation_unit": "whole_trajectory_block",
        },
    }
    assert document["selected_trajectory_order"] == [
        "layout_01_ep12602",
        "layout_02_ep12610",
        "layout_03_ep12645",
        "layout_04_ep12626",
        "layout_05_ep12634",
    ]
    assert len(document["candidates_inspected"]) == 24
    assert [
        row["trajectory_id"]
        for row in document["candidates_inspected"]
        if row["selected"]
    ] == document["selected_trajectory_order"][1:]


def test_selected_sources_are_unique_complete_and_canonical() -> None:
    document = json.loads(SELECTION.read_bytes())
    input_manifest = json.loads(INPUT_MANIFEST.read_bytes())
    staged_paths = {}
    for child in input_manifest["new_trajectory_bundles"]:
        child_manifest_path = INPUT_ROOT / child["bundle_manifest"]
        child_manifest = json.loads(child_manifest_path.read_bytes())
        for staged in child_manifest["direct_artifacts"]:
            source = staged["source"]
            staged_paths[
                (
                    child["trajectory_id"],
                    source["side"],
                    source["relative_path"],
                )
            ] = child_manifest_path.parent / staged["bundle_path"]
    source_identities = []
    source_paths = []
    for trajectory in document["selected_new_trajectories"]:
        assert trajectory["frame_count"] == 60
        assert trajectory["expected_activation_row_count"] == 1200
        assert trajectory["expected_activation_chunk_count"] == 20
        assert trajectory["label_position_audit"]["finite_count"] == 60
        assert trajectory["label_position_audit"]["nonzero_range"] is True
        assert len(trajectory["direct_source_artifacts"]) == 67
        for artifact in trajectory["direct_source_artifacts"]:
            source_identities.append(
                (
                    trajectory["episode_id"],
                    artifact["side"],
                    artifact["relative_path"],
                )
            )
            source_paths.append(artifact["path"])
            path = Path(artifact["path"])
            if not path.is_file():
                path = staged_paths[
                    (
                        trajectory["trajectory_id"],
                        artifact["side"],
                        artifact["relative_path"],
                    )
                ]
            assert path.stat().st_size == artifact["size_bytes"]
            assert _sha256(path) == artifact["sha256"]
    assert len(source_identities) == len(set(source_identities)) == 268
    assert len(source_paths) == len(set(source_paths)) == 268


def test_multilayout_input_manifest_and_every_staged_hash_pass() -> None:
    assert _sha256(INPUT_MANIFEST) == INPUT_SHA256
    result = multi.verify_multilayout_input(INPUT_MANIFEST, INPUT_SHA256)
    assert result["status"] == "PASS"
    assert result["file_count"] == 301
    assert [row["expected_activation_rows"] for row in result["trajectories"]] == [
        1200,
        1200,
        1200,
        1200,
    ]


def test_additive_session_identity_preserves_existing_attempt() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        inputs = root / "inputs"
        outputs = root / "outputs"
        inputs.mkdir()
        outputs.mkdir()
        first = multi._additive_session_id(inputs, outputs, "layout_02_ep12610")
        assert first.endswith("multilayout-v0-1")
        (outputs / first).mkdir()
        retry = multi._additive_session_id(inputs, outputs, "layout_02_ep12610")
        assert retry.startswith(first + "-retry-")
        assert (outputs / first).is_dir()


def test_completed_external_session_is_reused_before_additive_retry(
    tmp_path: Path,
) -> None:
    inputs = tmp_path / "inputs"
    outputs = tmp_path / "outputs"
    inputs.mkdir()
    outputs.mkdir()
    session = multi._additive_session_id(inputs, outputs, "layout_02_ep12610")
    input_root = inputs / session
    output_root = outputs / session
    store_root = outputs / f"{session}-activation-store-v2"
    input_root.mkdir()
    output_root.mkdir()
    (store_root / "indexes").mkdir(parents=True)
    (input_root / "accepted_pilot_manifest.json").write_text("{}", encoding="utf-8")
    index_path = store_root / "indexes/index.json"
    index_path.write_text("{}", encoding="utf-8")
    _write(
        output_root / "final_report.json",
        {"selected_pilot": "layout_02_ep12610", "status": "PASS"},
    )
    _write(
        output_root / "step6_4.json",
        {"result": {"activation_index_path": str(index_path), "status": "PASS"}},
    )
    _write(
        output_root / "step6_5.json",
        {
            "result": {
                "direct_pooling_audit": "PASS",
                "source_identity_join_failure_count": 0,
                "status": "PASS",
            }
        },
    )
    assert (
        multi._find_successful_external_session(inputs, outputs, "layout_02_ep12610")
        == session
    )


def test_existing_direct_pooling_audit_matches_indexed_frame_zero_vectors() -> None:
    audit_path = EXISTING_OUTPUT / "bounded_audit/limited_unpooled_frame_0.npz"
    with numpy.load(audit_path, allow_pickle=False) as audit:
        token_values = audit["token_values"].astype(numpy.float32)
        pooled_means = audit["pooled_means"]
        layers = audit["layer_indices"].tolist()
    recomputed = token_values.mean(axis=1, dtype=numpy.float32)
    numpy.testing.assert_allclose(recomputed, pooled_means, rtol=1e-3, atol=1e-3)

    output_manifest = json.loads(
        (EXISTING_OUTPUT / "output_bundle_manifest.json").read_bytes()
    )
    index = json.loads(
        (EXISTING_OUTPUT / output_manifest["activation_index"]).read_bytes()
    )
    chunks = {row["chunk_id"]: row for row in index["chunks"]}
    frame_zero = {
        row["layer_idx"]: row
        for row in index["index_rows"]
        if row["global_model_frame_idx"] == 0
    }
    assert sorted(frame_zero) == layers == list(range(20))
    for layer in layers:
        row = frame_zero[layer]
        chunk = chunks[row["activation_chunk_id"]]
        values = numpy.load(
            EXISTING_OUTPUT / "activation_store/chunks" / Path(chunk["path"]).name,
            allow_pickle=False,
        )
        numpy.testing.assert_allclose(
            values[row["chunk_row_idx"]],
            pooled_means[layer],
            rtol=1e-3,
            atol=1e-3,
        )


def test_multirun_collection_keeps_five_physical_indexes_and_new_e_gate() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        outputs = [
            _synthetic_output(root / f"output-{episode}", layout, episode)
            for layout, episode in multi.NEW_TRAJECTORIES
        ]
        destination = root / "successor"
        result = multi.collect_successor(
            existing_output=EXISTING_OUTPUT,
            new_outputs=outputs,
            selection_record_path=SELECTION,
            input_bundle_manifest=INPUT_MANIFEST,
            destination=destination,
        )
        assert result["status"] == "PASS"
        assert result["activation_index_count"] == 5
        assert result["activation_row_count"] == 6000
        assert result["activation_chunk_count"] == 100
        collection = json.loads((destination / "collection_manifest.json").read_bytes())
        assert (
            collection["collection_contract"]["physical_combined_index_created"]
            is False
        )
        assert collection["no_missing_extra_duplicate_stale_or_reordered_rows"] is True
        handoff = json.loads(
            (
                destination / "person_a_to_person_e_canonical_multilayout_handoff.json"
            ).read_bytes()
        )
        assert handoff["person_e_successor_acceptance_claimed"] is False
        assert handoff["requires_new_person_e_receipt"] is True


def test_create_only_collection_rejects_existing_destination(tmp_path: Path) -> None:
    destination = tmp_path / "exists"
    destination.mkdir()
    with pytest.raises(FileExistsError, match="create-only successor"):
        multi.collect_successor(
            existing_output=EXISTING_OUTPUT,
            new_outputs=[],
            selection_record_path=SELECTION,
            input_bundle_manifest=INPUT_MANIFEST,
            destination=destination,
        )


def test_sagemaker_prompt_is_complete_and_binds_the_automatic_launcher() -> None:
    assert _sha256(PROMPT) == PROMPT_SHA256
    prompt = PROMPT.read_text(encoding="utf-8")
    required = (
        "origin/role/person-a-model",
        "nvidia-smi",
        "NVIDIA L4",
        "ffmpeg=/home/sagemaker-user/tools/ffmpeg/bin/ffmpeg",
        "ffprobe=/home/sagemaker-user/tools/ffmpeg/bin/ffprobe",
        multi.C6A_PACKAGE_SHA256,
        INPUT_SHA256,
        "layout_02_ep12610",
        "layout_03_ep12645",
        "layout_04_ep12626",
        "layout_05_ep12634",
        "run_person_a_phase6_canonical_multilayout_sagemaker.sh",
        "5 activation indexes",
        "6,000 activation rows",
        "100 activation chunks",
        "requires_new_person_e_receipt true",
        "git push",
        "PERSON_A_MULTILAYOUT_SAGEMAKER_RESULT_BEGIN",
        "PERSON_A_MULTILAYOUT_SAGEMAKER_RESULT_END",
    )
    for value in required:
        assert value in prompt


def test_preparation_manifest_and_status_inventory_are_exact() -> None:
    manifest = json.loads((STATUS_ROOT / "preparation_manifest.json").read_bytes())
    assert manifest["status"] == "READY_FOR_SAGEMAKER_GPU_CONTINUATION"
    assert manifest["multirun_collection_ready"] is True
    assert manifest["successor_a_to_b_handoff_generation_ready"] is True
    assert manifest["successor_a_to_e_handoff_generation_ready"] is True
    for descriptor in manifest["implementation"].values():
        assert _sha256(ROOT / descriptor["path"]) == descriptor["sha256"]
    inventory = json.loads((STATUS_ROOT / "sha256_inventory.json").read_bytes())
    observed = set()
    for row in inventory["files"]:
        path = STATUS_ROOT / row["path"]
        assert path.stat().st_size == row["size_bytes"]
        assert _sha256(path) == row["sha256"]
        observed.add(row["path"])
    assert observed == {
        "preparation_manifest.json",
        "sagemaker_continuation_prompt.txt",
        "selection_record.json",
        "validation_receipt.json",
    }
