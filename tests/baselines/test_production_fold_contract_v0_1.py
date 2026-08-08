"""Tests for Person D's signed-explicit-mapping production fold validator.

The "exact real-manifest regression" this task requires can only be
proved against the actual real, committed fold/target manifests -- a
hand-built synthetic fixture cannot satisfy ``row_mapping_sha256``
(a hash over the real 1,695+179 real membership rows) or
``artifact_hash`` (a hash over the entire real document), by
construction. These tests read the real bytes directly from Person B's
branch via ``git show <commit>:<path>`` -- the same commit
(``RATIFYING_PERSON_B_COMMIT``) every frozen hash constant in this
package was already independently derived from -- never a checkout,
merge, or copy of that branch. No baseline is fit and no metric is
computed anywhere in this file.
"""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

import pytest

from mineocclude.baselines import production_fold_contract_v0_1 as contract

ROOT = Path(__file__).resolve().parents[2]


def _read_git_blob(commit: str, path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=ROOT, capture_output=True, check=True,
    )
    return result.stdout


def _real_fold_manifest_bytes() -> bytes:
    return _read_git_blob(contract.RATIFYING_PERSON_B_COMMIT, contract.FROZEN_FOLD_MANIFEST_PATH)


def _real_target_manifest_bytes() -> bytes:
    return _read_git_blob(contract.RATIFYING_PERSON_B_COMMIT, contract.FROZEN_TARGET_MANIFEST_PATH)


@pytest.fixture(scope="module")
def real_fold_bytes() -> bytes:
    return _real_fold_manifest_bytes()


@pytest.fixture(scope="module")
def real_fold_document(real_fold_bytes) -> dict:
    return json.loads(real_fold_bytes.decode("utf-8"))


@pytest.fixture(scope="module")
def real_target_bytes() -> bytes:
    return _real_target_manifest_bytes()


# --------------------------------------------------------------------------
# Exact real-manifest regression
# --------------------------------------------------------------------------


def test_real_production_fold_manifest_passes_signed_explicit_mapping_validation(
    real_fold_document,
):
    contract.validate_production_fold_document(
        real_fold_document, contract_version=contract.PRODUCTION_FOLD_CONTRACT_VERSION
    )  # must not raise


def test_real_production_fold_manifest_bytes_pass_the_literal_byte_check(real_fold_bytes):
    document = contract.validate_production_fold_manifest_bytes(
        real_fold_bytes, contract_version=contract.PRODUCTION_FOLD_CONTRACT_VERSION
    )
    assert document["layout_assignments"] == [
        {"fold_idx": 1, "layout_id": "layout_00"},
        {"fold_idx": 2, "layout_id": "layout_01"},
        {"fold_idx": 4, "layout_id": "layout_02"},
        {"fold_idx": 0, "layout_id": "layout_03"},
        {"fold_idx": 3, "layout_id": "layout_04"},
    ]


def test_real_fold_and_target_manifests_bind_together(real_fold_bytes, real_target_bytes):
    fold_document, target_document = contract.validate_fold_target_binding_bytes(
        real_fold_bytes, real_target_bytes, contract_version=contract.PRODUCTION_FOLD_CONTRACT_VERSION
    )
    assert len(fold_document["memberships"]) == 1_695
    assert target_document["row_count"] == 1_695


def test_historical_seed_invariant_reproduction_is_not_the_production_authority(
    real_fold_document,
):
    """Proves why bypassing (not patching) the historical helper was correct.

    The historical greedy reproduction, run directly here on the real
    admitted memberships with the real seed, produces a different
    assignment than the real signed mapping -- confirming the
    historical helper is genuinely inapplicable to this document, not
    merely inconvenient.
    """

    from mineocclude.probes.splits import _assign_validated_rows

    naive = _assign_validated_rows(
        real_fold_document["memberships"],
        n_splits=real_fold_document["n_splits"],
        seed=real_fold_document["seed"],
    )
    signed = {
        row["layout_id"]: row["fold_idx"] for row in real_fold_document["layout_assignments"]
    }
    assert naive == {
        "layout_00": 0, "layout_01": 1, "layout_02": 2, "layout_03": 3, "layout_04": 4,
    }
    assert signed == {
        "layout_00": 1, "layout_01": 2, "layout_02": 4, "layout_03": 0, "layout_04": 3,
    }
    assert naive != signed


# --------------------------------------------------------------------------
# Rejection cases
# --------------------------------------------------------------------------


def test_unknown_contract_version_fails_closed(real_fold_document):
    with pytest.raises(
        contract.ProductionFoldContractError, match="Unknown production fold contract version"
    ):
        contract.validate_production_fold_document(
            real_fold_document, contract_version="person-b-step4-1-production-fold-contract-v9.9"
        )


def test_changed_explicit_mapping_fails(real_fold_document):
    # Any mutation to the sealed document changes its self-consistent
    # artifact_hash away from the one frozen value -- the seal check
    # (which runs first) catches this before the friendlier
    # mapping-specific message would. This still proves rejection.
    mutated = copy.deepcopy(real_fold_document)
    mutated["layout_assignments"] = [
        {"fold_idx": 0, "layout_id": "layout_00"},
        {"fold_idx": 1, "layout_id": "layout_01"},
        {"fold_idx": 2, "layout_id": "layout_02"},
        {"fold_idx": 3, "layout_id": "layout_03"},
        {"fold_idx": 4, "layout_id": "layout_04"},
    ]
    with pytest.raises(contract.ProductionFoldContractError):
        contract.validate_production_fold_document(
            mutated, contract_version=contract.PRODUCTION_FOLD_CONTRACT_VERSION
        )


def test_changed_row_assignment_fails(real_fold_document):
    """Direct unit test of the membership-level check, bypassing the
    whole-document artifact seal so the specific leakage message fires."""

    mutated = copy.deepcopy(real_fold_document)
    first = mutated["memberships"][0]
    first["fold_idx"] = (first["fold_idx"] + 1) % 5
    with pytest.raises(contract.ProductionFoldContractError, match="leaks across folds"):
        contract._validate_memberships(mutated)


def test_duplicate_row_identity_fails(real_fold_document):
    mutated = copy.deepcopy(real_fold_document)
    mutated["memberships"].append(copy.deepcopy(mutated["memberships"][0]))
    with pytest.raises(contract.ProductionFoldContractError):
        contract._validate_memberships(mutated)


def test_cross_fold_leakage_fails(real_fold_document):
    mutated = copy.deepcopy(real_fold_document)
    for row in mutated["memberships"]:
        if row["layout_id"] == "layout_00":
            row["fold_idx"] = 2
            break
    with pytest.raises(contract.ProductionFoldContractError, match="leaks across folds"):
        contract._validate_memberships(mutated)


def test_changed_layout_order_or_count_fails_via_row_counts_audit(real_fold_document):
    mutated = copy.deepcopy(real_fold_document)
    mutated["row_counts"]["admitted_by_layout"] = list(
        reversed(mutated["row_counts"]["admitted_by_layout"])
    )
    with pytest.raises(contract.ProductionFoldContractError, match="row-count audit"):
        contract._validate_memberships(mutated)


def test_changed_fold_manifest_hash_fails(real_fold_bytes):
    tampered = real_fold_bytes + b" "
    with pytest.raises(contract.ProductionFoldContractError, match="literal byte size"):
        contract.validate_production_fold_manifest_bytes(
            tampered, contract_version=contract.PRODUCTION_FOLD_CONTRACT_VERSION
        )


def test_changed_target_hash_fails(real_fold_bytes, real_target_bytes):
    tampered_target = real_target_bytes + b" "
    with pytest.raises(contract.ProductionFoldContractError, match="literal byte size"):
        contract.validate_fold_target_binding_bytes(
            real_fold_bytes, tampered_target, contract_version=contract.PRODUCTION_FOLD_CONTRACT_VERSION
        )


def test_changed_producing_authority_fails(real_fold_document):
    # Same story as test_changed_explicit_mapping_fails: the whole-document
    # seal catches this before the source_identities-specific message
    # would. Rejection is what's required; either failure mode proves it.
    mutated = copy.deepcopy(real_fold_document)
    mutated["source_identities"]["person_c_commit"] = "0" * 40
    with pytest.raises(contract.ProductionFoldContractError):
        contract.validate_production_fold_document(
            mutated, contract_version=contract.PRODUCTION_FOLD_CONTRACT_VERSION
        )


def test_target_row_identity_mismatch_is_contradictory_ratification(real_fold_bytes, real_target_bytes):
    target_document = json.loads(real_target_bytes.decode("utf-8"))
    target_document["rows"] = list(reversed(target_document["rows"]))
    tampered_target_bytes = json.dumps(target_document).encode("utf-8")
    # Deliberately does not match the frozen formatted-JSON encoding either,
    # but the row-identity check is what this test targets specifically --
    # reaching either failure proves the binding cannot be silently accepted.
    with pytest.raises(contract.ProductionFoldContractError):
        contract.validate_fold_target_binding_bytes(
            real_fold_bytes, tampered_target_bytes, contract_version=contract.PRODUCTION_FOLD_CONTRACT_VERSION
        )


def test_no_u4_import_in_this_module():
    source = Path(
        ROOT / "src" / "mineocclude" / "baselines" / "production_fold_contract_v0_1.py"
    ).read_text(encoding="utf-8")
    import_lines = [
        line for line in source.splitlines() if line.strip().startswith(("import ", "from "))
    ]
    assert not any("u4" in line.lower() for line in import_lines)
