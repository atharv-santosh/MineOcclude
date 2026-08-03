"""Tests for D's own Registry v2-style handoff artifact schemas.

These are D's independent artifact types for D-owned baseline outputs
(owner-status, exact-artifact authorization, manifest,
verification-receipt) -- built on Person B's real sealing primitive
(`mineocclude.analysis.manifests.seal_artifact`/
`validate_sealed_artifact`), not a vendored copy of Person E's actual
Immutable Registry v2 system. See the module docstring in
`registry_v2_artifacts.py` for why this is a separate, D-owned
schema rather than an import of E's code.
"""

from __future__ import annotations

import pytest

from mineocclude.baselines.registry_v2_artifacts import (
    RegistryV2ArtifactError,
    RegistryV2HandoffPackage,
    build_exact_artifact_authorization,
    build_handoff_manifest,
    build_owner_status_record,
    build_verification_receipt,
    validate_exact_artifact_authorization,
    validate_owner_status_record,
    validate_registry_v2_handoff_package,
    validate_verification_receipt,
)
from mineocclude.baselines.scientific_readiness import BASELINE_PREDICTION_DIRECT_INPUTS

_CODE_SHA = "d" * 40
_CONFIG_HASH = "b" * 64
_INPUT_MANIFEST_HASH = "e" * 64
_TARGET_ARTIFACT_ID = "person_d_baseline_prediction::abc123"
_TARGET_ARTIFACT_TYPE = "baseline_prediction_document"
_TARGET_ARTIFACT_SHA256 = "1" * 64


def _owner_status(**overrides):
    kwargs = dict(
        owner_status="accepted",
        authority_revision="f" * 40,
        authorized_artifact_types=["baseline_prediction_document"],
        artifact_id="person_d_owner_status_v1",
        code_sha=_CODE_SHA,
        config_hash=_CONFIG_HASH,
        input_manifest_hash=_INPUT_MANIFEST_HASH,
    )
    kwargs.update(overrides)
    return build_owner_status_record(**kwargs)


def _authorization(owner_status_record, **overrides):
    kwargs = dict(
        target_artifact_id=_TARGET_ARTIFACT_ID,
        target_artifact_type=_TARGET_ARTIFACT_TYPE,
        target_artifact_sha256=_TARGET_ARTIFACT_SHA256,
        owner_status_record_hash=owner_status_record["artifact_hash"],
        direct_input_hashes={
            "fold_manifest_hash": "2" * 64,
            "oracle_target_hash": "3" * 64,
            "config_hash": "4" * 64,
        },
        artifact_id="person_d_authorization_v1",
        code_sha=_CODE_SHA,
        config_hash=_CONFIG_HASH,
        input_manifest_hash=_INPUT_MANIFEST_HASH,
    )
    kwargs.update(overrides)
    return build_exact_artifact_authorization(**kwargs)


def _manifest(owner_status_record, **overrides):
    kwargs = dict(
        artifact_identities=[
            {
                "artifact_id": _TARGET_ARTIFACT_ID,
                "artifact_type": _TARGET_ARTIFACT_TYPE,
                "artifact_sha256": _TARGET_ARTIFACT_SHA256,
            }
        ],
        owner_status_record_hash=owner_status_record["artifact_hash"],
        artifact_id="person_d_manifest_v1",
        code_sha=_CODE_SHA,
        config_hash=_CONFIG_HASH,
        input_manifest_hash=_INPUT_MANIFEST_HASH,
    )
    kwargs.update(overrides)
    return build_handoff_manifest(**kwargs)


def _receipt(**overrides):
    kwargs = dict(
        verified_artifact_id=_TARGET_ARTIFACT_ID,
        verified_sha256=_TARGET_ARTIFACT_SHA256,
        verification_mode="local_bytes",
        verification_result="pass",
        artifact_id="person_d_receipt_v1",
        code_sha=_CODE_SHA,
        config_hash=_CONFIG_HASH,
        input_manifest_hash=_INPUT_MANIFEST_HASH,
    )
    kwargs.update(overrides)
    return build_verification_receipt(**kwargs)


def test_direct_input_hashes_must_match_the_frozen_direct_inputs_constant():
    # Cross-checks registry_v2_artifacts against scientific_readiness's
    # own constant so the two modules cannot silently drift apart.
    owner = _owner_status()
    good = _authorization(owner)
    assert set(good["direct_input_hashes"]) == set(BASELINE_PREDICTION_DIRECT_INPUTS)

    with pytest.raises(RegistryV2ArtifactError, match="direct_input_hashes"):
        _authorization(
            owner,
            direct_input_hashes={"fold_manifest_hash": "2" * 64},  # missing keys
        )


def test_owner_status_round_trips_and_validates():
    owner = _owner_status()
    validate_owner_status_record(owner)
    assert owner["owner_id"] == "person_d"
    assert owner["decision"] == "accepted"


def test_owner_status_rejects_a_bad_decision_mapping():
    owner = _owner_status()
    tampered = dict(owner)
    tampered["decision"] = "excluded"  # accepted must map to accepted, not excluded
    with pytest.raises(RegistryV2ArtifactError):
        validate_owner_status_record(tampered)


def test_owner_status_rejects_tampered_bytes():
    owner = _owner_status()
    tampered = dict(owner)
    tampered["owner_status"] = "rejected"
    with pytest.raises(RegistryV2ArtifactError, match="does not match"):
        validate_owner_status_record(tampered)


def test_exact_artifact_authorization_is_scoped_to_one_artifact_id():
    owner = _owner_status()
    authorization = _authorization(owner)
    assert authorization["target_artifact_id"] == _TARGET_ARTIFACT_ID
    validate_exact_artifact_authorization(authorization, owner_status_record=owner)


def test_exact_artifact_authorization_rejects_owner_status_hash_mismatch():
    owner = _owner_status()
    authorization = _authorization(owner)
    other_owner = _owner_status(artifact_id="person_d_owner_status_v2")
    with pytest.raises(RegistryV2ArtifactError, match="owner_status_record_hash"):
        validate_exact_artifact_authorization(authorization, owner_status_record=other_owner)


def test_handoff_manifest_rejects_duplicate_artifact_ids():
    owner = _owner_status()
    with pytest.raises(RegistryV2ArtifactError, match="duplicate"):
        _manifest(
            owner,
            artifact_identities=[
                {
                    "artifact_id": _TARGET_ARTIFACT_ID,
                    "artifact_type": _TARGET_ARTIFACT_TYPE,
                    "artifact_sha256": _TARGET_ARTIFACT_SHA256,
                },
                {
                    "artifact_id": _TARGET_ARTIFACT_ID,
                    "artifact_type": _TARGET_ARTIFACT_TYPE,
                    "artifact_sha256": _TARGET_ARTIFACT_SHA256,
                },
            ],
        )


def test_verification_receipt_rejects_a_hash_mismatch_against_the_manifest():
    owner = _owner_status()
    manifest = _manifest(owner)
    bad_receipt = _receipt(verified_sha256="9" * 64)
    with pytest.raises(RegistryV2ArtifactError, match="does not match"):
        validate_verification_receipt(bad_receipt, handoff_manifest=manifest)


def test_verification_receipt_rejects_an_artifact_id_absent_from_the_manifest():
    owner = _owner_status()
    manifest = _manifest(owner)
    bad_receipt = _receipt(verified_artifact_id="person_d_baseline_prediction::not_in_manifest")
    with pytest.raises(RegistryV2ArtifactError, match="no entry in the handoff manifest"):
        validate_verification_receipt(bad_receipt, handoff_manifest=manifest)


def test_composite_package_validates_when_every_cross_reference_agrees():
    owner = _owner_status()
    authorization = _authorization(owner)
    manifest = _manifest(owner)
    receipt = _receipt()
    package = RegistryV2HandoffPackage(
        owner_status_record=owner,
        exact_artifact_authorization=authorization,
        handoff_manifest=manifest,
        verification_receipt=receipt,
    )
    validate_registry_v2_handoff_package(package)


def test_composite_package_rejects_an_authorized_artifact_missing_from_the_manifest():
    owner = _owner_status()
    authorization = _authorization(owner, target_artifact_id="person_d_baseline_prediction::other")
    manifest = _manifest(owner)  # still only lists _TARGET_ARTIFACT_ID
    receipt = _receipt()
    package = RegistryV2HandoffPackage(
        owner_status_record=owner,
        exact_artifact_authorization=authorization,
        handoff_manifest=manifest,
        verification_receipt=receipt,
    )
    with pytest.raises(RegistryV2ArtifactError, match="does not appear in the handoff manifest"):
        validate_registry_v2_handoff_package(package)
