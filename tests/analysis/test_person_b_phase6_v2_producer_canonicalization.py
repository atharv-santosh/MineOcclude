"""Regression coverage for Person A-owned Activation Store v2 JSON bytes."""

from __future__ import annotations

import gc
import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from mineocclude.contracts.activation_v2 import (
    PERSON_A_ACTIVATION_INDEX_V2_CANONICALIZATION_CONTRACT,
    PERSON_A_ACTIVATION_STORE_V2_PRODUCER_COMMIT,
    PERSON_A_ACTIVATION_STORE_V2_PRODUCER_SHA256,
    person_a_activation_index_v2_canonical_json_bytes,
    person_a_activation_index_v2_snapshot_digest,
    validate_activation_index_v2_bytes,
)
from mineocclude.experiments.registry import canonical_json_bytes

REPOSITORY = Path(__file__).resolve().parents[2]
PERSON_C_ACCEPTANCE_COMMIT = "c6bff25b5ef4f5fdb0e1ef0ce0d22e3f8b5e4960"
TRANSFER_ARCHIVE_BYTE_SIZE = 3_707_822
TRANSFER_ARCHIVE_SHA256 = (
    "9bdcd1526533fac4d53e8e617851c85fd060f0ab8b477ba8b99856b632368584"
)
TRANSFER_MANIFEST_SHA256 = (
    "73d77935fefc423ac4a295c380cf327624caf862052b2f38f58840e307d4011d"
)
TRANSFER_SHA256SUMS_SHA256 = (
    "0cdf8a4abd4c69ddbfe105488f438d18536b9a30e9c6b7906cc6d18b629ff0d2"
)
INVENTORY_ROOT = (
    "docs/status/phase6_runtime/"
    "person-a-phase6-ten-pilot-expansion-seed-20260725/"
    "per_pilot_inventories"
)
C_ACCEPTED_MANIFEST_PATH = (
    "docs/status/person_c_phase6_ten_pilot_expansion_acceptance_v0_1/"
    "accepted_pilot_manifest.json"
)
COMMITTED_FULL_INDEX_PATH = (
    "docs/status/phase6_runtime/"
    "person-a-phase6-step6-3-continuation-a102aa4d1ca5d4760e9c9997/"
    "activation_store/indexes/"
    "index-82dc0e18607a1a89135a1a88cbec5d53531682db970e9a1323672e7f4d28677b.json"
)
INDEX_BINDINGS = (
    (
        "layout_00_ep9403",
        "473efef1eb52514c097051ec8f4501cb621f92c9ceaeb847249c7e3ae042ad55",
        32502224,
        "82dc0e18607a1a89135a1a88cbec5d53531682db970e9a1323672e7f4d28677b",
    ),
    (
        "layout_00_ep9441",
        "a553a431e3cb8bef174552f0ac77d1afa881db255b1ca8d76f8461ad02b3c6ce",
        26233589,
        "bf518a89b761223fac62c1bb3c5b6457d9796a2abd62f0030ab2cc4da10a50bf",
    ),
    (
        "layout_01_ep9405",
        "023786fd7fb3002e5acebcddd82e8f1e7ddb597138820c9401bd5dd7af5f10e6",
        30164409,
        "0ceffdaab158e7edec75816bc1958922531fe2baa7c2189b558153de4f3ad7b9",
    ),
    (
        "layout_01_ep9442",
        "f8708f04e72a3e73ce9ac7136f6f7c191fdee9dbfba026d6867445cd2ffaa2eb",
        26233589,
        "6f0488a2e8d5fc16db98e5218b56038738cbc937b872fad1e85f14a627fd74ee",
    ),
    (
        "layout_02_ep9407",
        "c76bf46818c70a798276d52d1d46a4f27aee255e44e0bd20fa1a583f23c3c467",
        20734849,
        "e6ede10a3d0f2115275a5e287acea472785fde798da0820935117bc0ba5fba81",
    ),
    (
        "layout_02_ep9432",
        "33ef1f8d3f6bf3487e33fdfe14a38446a37d421f90cb24e885c4594f53783fab",
        26233589,
        "058396bacb360c159a670d6b48c40024d1314ce1fa66be21ecb8fb53ca9faac1",
    ),
    (
        "layout_03_ep9404",
        "66b162bb09a170d82563838cf5ebc1eea4e7e9c6fe0f10927e155d1e765633fe",
        16406599,
        "b4b5232cb549a41882998312071b88200ff7c047ab9c045b89d4e9a6ad0b6cbf",
    ),
    (
        "layout_03_ep9443",
        "2d48a43da1c720a81f5bb8ce6a4a2e1d1ea3344b5884fb62df2846409d8dca6f",
        26233589,
        "f15423703da1ce45f65fe13ed350c79ce73ccfdff9f415e6b252b4b29f2dca01",
    ),
    (
        "layout_04_ep9406",
        "df8f0541c872e3d6daf7a6a1165e6deafe6256ec745ffb5329befe0e3c697a78",
        14829719,
        "3e8d24985d51b9ffbaf81f8b0e8be6bedc8b082c6e2dda721b6e14961ff20e47",
    ),
    (
        "layout_04_ep9444",
        "2ab37112dfabe22c773e02512f894d7aa0c2f63d32493a743a6dbee6fb30c933",
        26233589,
        "451de28efa43dcc476a258b7637df4fb7eb6c30784025f786afd1bcbbcdaa876",
    ),
)


def _git_blob(commit: str, path: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(REPOSITORY), "cat-file", "blob", f"{commit}:{path}"],
        check=True,
        capture_output=True,
    )
    return completed.stdout


def _json_blob(commit: str, path: str) -> dict:
    return json.loads(_git_blob(commit, path))


def _external_transfer_paths() -> tuple[Path, Path]:
    fixture_value = os.environ.get("PERSON_A_PHASE6_NINE_INDEX_FIXTURE_ROOT")
    archive_value = os.environ.get("PERSON_A_PHASE6_INDEX_ARCHIVE")
    if not fixture_value or not archive_value:
        pytest.skip("Exact external Person A transfer evidence is not mounted.")
    return Path(fixture_value).resolve(), Path(archive_value).resolve()


def test_exact_person_a_producer_contract_is_bound() -> None:
    source = _git_blob(
        PERSON_A_ACTIVATION_STORE_V2_PRODUCER_COMMIT,
        "src/mineocclude/activations/store_v2.py",
    )
    assert hashlib.sha256(source).hexdigest() == (
        PERSON_A_ACTIVATION_STORE_V2_PRODUCER_SHA256
    )
    assert b"indent=2" in source
    assert b"sort_keys=True" in source
    assert b"ensure_ascii=False" in source
    assert b' + "\\n"' in source
    assert b"hashlib.sha256(canonical_json_bytes(value)).hexdigest()" in source


@pytest.mark.parametrize(
    "trajectory_id,expected_sha256,expected_byte_size,expected_snapshot_id",
    INDEX_BINDINGS,
)
def test_all_ten_committed_inventory_bindings_are_exact(
    trajectory_id: str,
    expected_sha256: str,
    expected_byte_size: int,
    expected_snapshot_id: str,
) -> None:
    inventory = _json_blob(
        PERSON_A_ACTIVATION_STORE_V2_PRODUCER_COMMIT,
        f"{INVENTORY_ROOT}/{trajectory_id}.json",
    )
    index = inventory["activation_index"]
    assert inventory["trajectory_id"] == trajectory_id
    assert index["sha256"] == expected_sha256
    assert index["byte_size"] == expected_byte_size
    assert Path(index["path"]).name == f"index-{expected_snapshot_id}.json"


def test_exact_committed_index_bytes_use_producer_not_registry_digest() -> None:
    raw = _git_blob(
        PERSON_A_ACTIVATION_STORE_V2_PRODUCER_COMMIT,
        COMMITTED_FULL_INDEX_PATH,
    )
    before = bytes(raw)
    document = json.loads(raw)
    inventory = _json_blob(
        PERSON_A_ACTIVATION_STORE_V2_PRODUCER_COMMIT,
        f"{INVENTORY_ROOT}/layout_00_ep9403.json",
    )
    accepted = _json_blob(PERSON_C_ACCEPTANCE_COMMIT, C_ACCEPTED_MANIFEST_PATH)
    accepted_by_trajectory = {
        row["trajectory_id"]: row["capture_package_sha256"]
        for row in accepted["intake_rows"]
    }

    assert hashlib.sha256(raw).hexdigest() == inventory["activation_index"]["sha256"]
    assert len(raw) == inventory["activation_index"]["byte_size"]
    assert raw == person_a_activation_index_v2_canonical_json_bytes(document)
    assert (
        person_a_activation_index_v2_snapshot_digest(
            document,
            canonicalization_contract=(
                PERSON_A_ACTIVATION_INDEX_V2_CANONICALIZATION_CONTRACT
            ),
        )
        == document["snapshot_id"]
    )
    identity = dict(document)
    identity.pop("snapshot_id")
    assert (
        hashlib.sha256(canonical_json_bytes(identity)).hexdigest()
        != document["snapshot_id"]
    )

    validated = validate_activation_index_v2_bytes(
        raw,
        canonicalization_contract=(
            PERSON_A_ACTIVATION_INDEX_V2_CANONICALIZATION_CONTRACT
        ),
        expected_index_sha256=inventory["activation_index"]["sha256"],
        expected_index_byte_size=inventory["activation_index"]["byte_size"],
        expected_trajectory_id="layout_00_ep9403",
        expected_manifest_sha256=accepted_by_trajectory["layout_00_ep9403"],
    )
    assert validated.raw_sha256 == inventory["activation_index"]["sha256"]
    assert len(validated.rows) == inventory["activation_row_count"] == 4960
    assert len(validated.chunks) == 20
    assert raw == before


def test_person_a_receipt_binds_ten_successful_index_hashes() -> None:
    receipt = _json_blob(
        PERSON_A_ACTIVATION_STORE_V2_PRODUCER_COMMIT,
        "docs/status/phase6_runtime/"
        "person-a-phase6-ten-pilot-expansion-seed-20260725/"
        "validation_receipt.json",
    )
    assert receipt["activation_index_hash_count"] == len(INDEX_BINDINGS) == 10
    assert receipt["activation_index_hash_failure_count"] == 0
    assert receipt["canonical_json_pass"] is True
    assert receipt["step6_6_complete"] is False
    assert receipt["u4_output_inspected"] is False


def test_full_ten_index_real_artifact_regression() -> None:
    fixture_root, archive_path = _external_transfer_paths()
    assert not fixture_root.is_relative_to(REPOSITORY)
    assert not archive_path.is_relative_to(REPOSITORY)
    archive_bytes = archive_path.read_bytes()
    assert len(archive_bytes) == TRANSFER_ARCHIVE_BYTE_SIZE
    assert hashlib.sha256(archive_bytes).hexdigest() == TRANSFER_ARCHIVE_SHA256

    manifest_path = fixture_root / "transfer_manifest.json"
    sums_path = fixture_root / "SHA256SUMS"
    assert hashlib.sha256(manifest_path.read_bytes()).hexdigest() == (
        TRANSFER_MANIFEST_SHA256
    )
    assert hashlib.sha256(sums_path.read_bytes()).hexdigest() == (
        TRANSFER_SHA256SUMS_SHA256
    )
    manifest = json.loads(manifest_path.read_bytes())
    expected_manifest = {
        "activation_chunks_included": False,
        "hash_mismatch_count": 0,
        "index_file_count": 9,
        "person_a_commit": PERSON_A_ACTIVATION_STORE_V2_PRODUCER_COMMIT,
        "schema_id": "person-a-phase6-nine-index-transfer-v1.0",
        "schema_version": "1.0",
        "scientific_execution_performed": False,
        "size_mismatch_count": 0,
        "snapshot_identity_mismatch_count": 0,
        "source_artifacts_modified": False,
        "u4_output_inspected": False,
        "unique_pilot_count": 9,
    }
    assert all(manifest.get(key) == value for key, value in expected_manifest.items())
    entries = manifest["transferred_files"]
    assert isinstance(entries, list) and len(entries) == 9
    evidence = manifest["person_a_evidence"]
    committed_evidence = {
        "committed_artifact_manifest_sha256": "artifact_manifest.json",
        "committed_completion_report_sha256": "completion_report.json",
        "committed_sha256_inventory_sha256": "sha256_inventory.json",
        "committed_validation_receipt_sha256": "validation_receipt.json",
    }
    evidence_root = (
        "docs/status/phase6_runtime/person-a-phase6-ten-pilot-expansion-seed-20260725"
    )
    assert (
        evidence["evidence_root"] == f"/home/sagemaker-user/MineOcclude/{evidence_root}"
    )
    for manifest_field, filename in committed_evidence.items():
        assert (
            hashlib.sha256(
                _git_blob(
                    PERSON_A_ACTIVATION_STORE_V2_PRODUCER_COMMIT,
                    f"{evidence_root}/{filename}",
                )
            ).hexdigest()
            == evidence[manifest_field]
        )

    files = sorted(path for path in fixture_root.rglob("*") if path.is_file())
    assert len(files) == 11
    if os.name == "nt":
        assert all(
            path.stat().st_file_attributes & stat.FILE_ATTRIBUTE_READONLY
            for path in files
        )
    assert not any(
        path.suffix.lower() in {".npy", ".npz", ".pt", ".pth"}
        or "chunk" in path.name.lower()
        for path in files
    )
    index_paths = sorted((fixture_root / "indices").glob("*.json"))
    assert len(index_paths) == 9
    sums = {
        fields[1]: fields[0]
        for line in sums_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
        for fields in [line.split()]
    }
    assert len(sums) == 9
    assert (
        set(sums)
        == {entry["transferred_relative_path"] for entry in entries}
        == {path.relative_to(fixture_root).as_posix() for path in index_paths}
    )

    accepted = _json_blob(PERSON_C_ACCEPTANCE_COMMIT, C_ACCEPTED_MANIFEST_PATH)
    accepted_by_trajectory = {
        row["trajectory_id"]: row["capture_package_sha256"]
        for row in accepted["intake_rows"]
    }
    expected_by_trajectory = {
        trajectory_id: (raw_sha256, byte_size, snapshot_id)
        for trajectory_id, raw_sha256, byte_size, snapshot_id in INDEX_BINDINGS
    }
    transferred_ids: list[str] = []
    actual_row_count = 0
    for entry in entries:
        trajectory_id = entry["pilot_id"]
        raw_sha256, byte_size, snapshot_id = expected_by_trajectory[trajectory_id]
        path = fixture_root / entry["transferred_relative_path"]
        before = path.read_bytes()
        assert path.name == f"{trajectory_id}-index.json"
        assert hashlib.sha256(before).hexdigest() == raw_sha256
        assert len(before) == byte_size
        assert entry["raw_sha256"] == raw_sha256
        assert entry["byte_size"] == byte_size
        assert entry["person_a_snapshot_identity"] == snapshot_id
        assert sums[entry["transferred_relative_path"]] == raw_sha256
        assert entry["original_bytes_preserved"] is True
        assert entry["person_a_commit"] == PERSON_A_ACTIVATION_STORE_V2_PRODUCER_COMMIT

        inventory = _json_blob(
            PERSON_A_ACTIVATION_STORE_V2_PRODUCER_COMMIT,
            f"{INVENTORY_ROOT}/{trajectory_id}.json",
        )
        assert inventory["activation_index"]["sha256"] == raw_sha256
        assert inventory["activation_index"]["byte_size"] == byte_size
        assert (
            inventory["activation_index"]["path"]
            == entry["original_absolute_source_path"]
        )
        validated = validate_activation_index_v2_bytes(
            before,
            canonicalization_contract=(
                PERSON_A_ACTIVATION_INDEX_V2_CANONICALIZATION_CONTRACT
            ),
            expected_index_sha256=raw_sha256,
            expected_index_byte_size=byte_size,
            expected_trajectory_id=trajectory_id,
            expected_manifest_sha256=accepted_by_trajectory[trajectory_id],
        )
        assert validated.document["snapshot_id"] == snapshot_id
        identity = dict(validated.document)
        identity.pop("snapshot_id")
        assert hashlib.sha256(canonical_json_bytes(identity)).hexdigest() != snapshot_id
        assert all(row["trajectory_id"] == trajectory_id for row in validated.rows)
        assert path.read_bytes() == before
        actual_row_count += len(validated.rows)
        transferred_ids.append(trajectory_id)
        del before, inventory, validated, identity
        gc.collect()

    git_trajectory = "layout_00_ep9403"
    git_inventory = _json_blob(
        PERSON_A_ACTIVATION_STORE_V2_PRODUCER_COMMIT,
        f"{INVENTORY_ROOT}/{git_trajectory}.json",
    )
    git_bytes = _git_blob(
        PERSON_A_ACTIVATION_STORE_V2_PRODUCER_COMMIT,
        COMMITTED_FULL_INDEX_PATH,
    )
    git_validated = validate_activation_index_v2_bytes(
        git_bytes,
        canonicalization_contract=(
            PERSON_A_ACTIVATION_INDEX_V2_CANONICALIZATION_CONTRACT
        ),
        expected_index_sha256=git_inventory["activation_index"]["sha256"],
        expected_index_byte_size=git_inventory["activation_index"]["byte_size"],
        expected_trajectory_id=git_trajectory,
        expected_manifest_sha256=accepted_by_trajectory[git_trajectory],
    )
    all_trajectories = [*transferred_ids, git_trajectory]
    actual_row_count += len(git_validated.rows)
    assert len(all_trajectories) == len(set(all_trajectories)) == 10
    assert actual_row_count == 37_480
    assert git_validated.document["snapshot_id"] == INDEX_BINDINGS[0][3]
