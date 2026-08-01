from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from mineocclude.experiments.registry import formatted_json_bytes

ROOT = Path(__file__).resolve().parents[2]
STATUS_ROOT = (
    ROOT
    / "docs"
    / "status"
    / "person_b_phase4_step4_1_fold_validation_interface_v0_1"
)
D_RUNNER_COMMIT = "b260561143d72d69428f45c1f210bdf117f9803d"
D_CLI_COMMIT = "bb2ebf7947c92c814dae85fc9cef29fef04e4c6f"
IMPLEMENTATION_COMMIT = "06bd2a17b90d95de37c0739d17d3a624964cc4fa"


def _git_bytes(commit: str, path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=ROOT)


def test_interface_binds_exact_b_and_d_authorities() -> None:
    authority = json.loads(
        (STATUS_ROOT / "authority_binding.json").read_text(encoding="utf-8")
    )
    assert authority["fold_contract"]["implementation_commit"] == (
        IMPLEMENTATION_COMMIT
    )
    assert authority["person_d"]["cli_implementation_commit"] == D_CLI_COMMIT
    assert authority["person_d"]["runner_preparation_commit"] == D_RUNNER_COMMIT
    assert (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", D_CLI_COMMIT, D_RUNNER_COMMIT],
            cwd=ROOT,
            check=False,
        ).returncode
        == 0
    )


def test_exact_d_blocker_and_patch_points_are_bound() -> None:
    contract = json.loads(
        (STATUS_ROOT / "person_d_compatibility_contract.json").read_text(
            encoding="utf-8"
        )
    )
    for patch_point in contract["required_person_d_patch_points"]:
        payload = _git_bytes(
            patch_point["current_commit"],
            patch_point["path"],
        )
        assert len(payload) == patch_point["current_byte_size"]
        assert hashlib.sha256(payload).hexdigest() == patch_point["current_sha256"]

    blocker = json.loads(
        _git_bytes(
            D_RUNNER_COMMIT,
            (
                "docs/status/"
                "person_d_phase4_step4_1_eight_family_cli_finalization_v0_1/"
                "fold_manifest_reproduction_blocker.json"
            ),
        )
    )
    assert blocker["unresolved"] is True
    assert blocker["u4_output_inspected"] is False
    assert blocker["exact_reproduction"]["declared_layout_assignments"] == {
        "layout_00": 1,
        "layout_01": 2,
        "layout_02": 4,
        "layout_03": 0,
        "layout_04": 3,
    }
    assert blocker["exact_reproduction"]["ds_recomputed_layout_assignments"] == {
        "layout_00": 0,
        "layout_01": 1,
        "layout_02": 2,
        "layout_03": 3,
        "layout_04": 4,
    }


def test_interface_keeps_person_d_execution_blocked() -> None:
    contract = json.loads(
        (STATUS_ROOT / "person_d_compatibility_contract.json").read_text(
            encoding="utf-8"
        )
    )
    assert contract["baseline_execution_authorized"] is False
    assert contract["final_person_d_execution_authorization_issued"] is False
    assert contract["person_d_execution_ready"] is False
    assert contract["person_d_patch_required"] is True
    assert contract["u4_output_inspected"] is False
    assert contract["exact_test_vectors"][1]["expected_signed_assignment"] == [
        1,
        2,
        4,
        0,
        3,
    ]
    assert contract["exact_test_vectors"][1][
        "expected_historical_subset_reproduction"
    ] == [0, 1, 2, 3, 4]


def test_interface_package_is_canonical_and_inventory_matches() -> None:
    for path in STATUS_ROOT.glob("*.json"):
        raw = path.read_bytes()
        assert raw == formatted_json_bytes(json.loads(raw.decode("utf-8")))
    inventory = json.loads(
        (STATUS_ROOT / "sha256_inventory.json").read_text(encoding="utf-8")
    )
    assert inventory["inventory_excludes_self"] is True
    for relative_path, expected in inventory["files"].items():
        payload = (ROOT / relative_path).read_bytes()
        assert len(payload) == expected["byte_size"]
        assert hashlib.sha256(payload).hexdigest() == expected["sha256"]
