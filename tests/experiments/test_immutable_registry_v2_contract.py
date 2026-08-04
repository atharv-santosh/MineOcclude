from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

from mineocclude.contracts.rollout_registry import (
    IMMUTABLE_REGISTRY_V2_SCHEMA_VERSION,
    IMMUTABLE_V2_ARTIFACT_OWNER_IDS,
    IMMUTABLE_V2_ARTIFACT_TYPES,
    IMMUTABLE_V2_OWNER_STATUSES,
    IMMUTABLE_V2_RUN_STATUSES,
    IMMUTABLE_V2_STATUS_RECORD_SCHEMA_VERSION,
    IMMUTABLE_V2_STEP4_ARTIFACT_TYPE_MAP,
    ImmutableRegistryRejectionCode,
    validate_immutable_run_artifact_registry,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "person_e"
V1_FIXTURE = FIXTURE_ROOT / "immutable_registry_v1.json"
V1_REJECTED_FIXTURE = (
    FIXTURE_ROOT / "rejected_registry_missing_direct_input_v1.json"
)
V2_PENDING_FIXTURE = FIXTURE_ROOT / "immutable_registry_v2_pending.json"
V2_COMPLETED_FIXTURE = FIXTURE_ROOT / "immutable_registry_v2_completed.json"
STATUS_RECORD_DOCUMENT = {
    "authority_revision": "1" * 40,
    "decision": "accepted",
    "owner_id": "person_a",
    "owner_status": "accepted",
    "schema_version": IMMUTABLE_V2_STATUS_RECORD_SCHEMA_VERSION,
    "status_record_id": "person_a_extraction_status_v0_1",
}
STATUS_RECORD_BYTES = (
    json.dumps(STATUS_RECORD_DOCUMENT, indent=2, sort_keys=True) + "\n"
).encode("utf-8")
STATUS_RECORD_SHA256 = hashlib.sha256(STATUS_RECORD_BYTES).hexdigest()
TRUSTED_AUTHORITY_RECORD = {
    "authority_id": "authority_person_a_extraction",
    "authority_revision": "1" * 40,
    "authorized_artifact_types": ["extraction"],
    "decision": "accepted",
    "owner_id": "person_a",
    "owner_status": "accepted",
    "schema_version": "1.0",
    "status_record_id": "person_a_extraction_status_v0_1",
    "status_record_receipt_authority_revision": None,
    "status_record_receipt_id": None,
    "status_record_receipt_sha256": None,
    "status_record_schema_version": IMMUTABLE_V2_STATUS_RECORD_SCHEMA_VERSION,
    "status_record_sha256": STATUS_RECORD_SHA256,
    "status_record_verification_mode": "local_bytes",
}
AUTHORIZATION_RECORD_DOCUMENT = {
    "artifact_id": "artifact_extraction",
    "artifact_schema_version": "synthetic-extraction-v0.1",
    "artifact_sha256": "a" * 64,
    "artifact_size_bytes": 12,
    "artifact_type": "extraction",
    "authority_id": "authority_person_a_extraction",
    "authorization_id": "authorization_person_a_extraction",
    "authorization_record_id": "person_a_extraction_authorization_v0_1",
    "decision": "accepted",
    "manifest_artifact_identity": "person-a-extraction-output-1",
    "manifest_id": "manifest_person_a_extraction",
    "manifest_schema_version": "person-a-extraction-manifest-v1.0",
    "manifest_sha256": "3" * 64,
    "owner_authority_revision": "1" * 40,
    "owner_id": "person_a",
    "owner_status": "accepted",
}
AUTHORIZATION_RECORD_BYTES = (
    json.dumps(AUTHORIZATION_RECORD_DOCUMENT, indent=2, sort_keys=True) + "\n"
).encode("utf-8")
AUTHORIZATION_RECORD_SHA256 = hashlib.sha256(
    AUTHORIZATION_RECORD_BYTES
).hexdigest()
TRUSTED_ARTIFACT_AUTHORIZATION = {
    **AUTHORIZATION_RECORD_DOCUMENT,
    "authorization_record_receipt_authority_revision": None,
    "authorization_record_receipt_id": None,
    "authorization_record_receipt_sha256": None,
    "authorization_record_sha256": AUTHORIZATION_RECORD_SHA256,
    "authorization_record_verification_mode": "local_bytes",
}
TRUSTED_MANIFEST_RECORD = {
    "artifact_identities": [
        {
            "artifact_id": "artifact_extraction",
            "artifact_schema_version": "synthetic-extraction-v0.1",
            "artifact_sha256": "a" * 64,
            "artifact_size_bytes": 12,
            "artifact_type": "extraction",
            "manifest_artifact_identity": "person-a-extraction-output-1",
        }
    ],
    "decision": "accepted",
    "manifest_id": "manifest_person_a_extraction",
    "manifest_schema_version": "person-a-extraction-manifest-v1.0",
    "manifest_sha256": "3" * 64,
    "owner_authority_id": "authority_person_a_extraction",
    "owner_authority_revision": "1" * 40,
    "owner_id": "person_a",
    "owner_status": "accepted",
}
TRUSTED_ARTIFACT_RECEIPT = {
    "receipt_authority_revision": "5" * 40,
    "receipt_id": "receipt_person_a_extraction",
    "receipt_sha256": "4" * 64,
    "verified_artifact_id": "artifact_extraction",
    "verified_artifact_schema_version": "synthetic-extraction-v0.1",
    "verified_artifact_sha256": "a" * 64,
    "verified_artifact_size": 12,
    "verified_artifact_type": "extraction",
    "verified_manifest_artifact_identity": "person-a-extraction-output-1",
    "verified_manifest_id": "manifest_person_a_extraction",
    "verified_manifest_sha256": "3" * 64,
    "verified_owner_authority_revision": "1" * 40,
    "verified_owner_id": "person_a",
}


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _pending_registry() -> dict[str, object]:
    return _load(V2_PENDING_FIXTURE)


def _completed_registry() -> dict[str, object]:
    return _load(V2_COMPLETED_FIXTURE)


def _status_record_bytes_for(
    authority: dict[str, object],
    **overrides: object,
) -> bytes:
    document = {
        "authority_revision": authority["authority_revision"],
        "decision": authority["decision"],
        "owner_id": authority["owner_id"],
        "owner_status": authority["owner_status"],
        "schema_version": authority["status_record_schema_version"],
        "status_record_id": authority["status_record_id"],
    }
    document.update(overrides)
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _external_receipt_for(authority: dict[str, object]) -> dict[str, object]:
    return {
        "receipt_authority_revision": authority["authority_revision"],
        "receipt_id": "trusted_status_receipt_person_a_extraction",
        "receipt_sha256": "9" * 64,
        "verified_decision": authority["decision"],
        "verified_owner_authority_revision": authority["authority_revision"],
        "verified_owner_id": authority["owner_id"],
        "verified_owner_status": authority["owner_status"],
        "verified_status_record_id": authority["status_record_id"],
        "verified_status_record_schema_version": authority[
            "status_record_schema_version"
        ],
        "verified_status_record_sha256": authority["status_record_sha256"],
    }


def _authority_with_status_record(
    **updates: object,
) -> tuple[dict[str, object], bytes]:
    authority = copy.deepcopy(TRUSTED_AUTHORITY_RECORD)
    authority.update(updates)
    payload = _status_record_bytes_for(authority)
    authority["status_record_sha256"] = hashlib.sha256(payload).hexdigest()
    return authority, payload


def _authorization_record_bytes_for(
    authorization: dict[str, object],
    **overrides: object,
) -> bytes:
    document = {
        field: authorization[field] for field in AUTHORIZATION_RECORD_DOCUMENT
    }
    document.update(overrides)
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _authorization_with_record(
    **updates: object,
) -> tuple[dict[str, object], bytes]:
    authorization = copy.deepcopy(TRUSTED_ARTIFACT_AUTHORIZATION)
    authorization.update(updates)
    payload = _authorization_record_bytes_for(authorization)
    authorization["authorization_record_sha256"] = hashlib.sha256(
        payload
    ).hexdigest()
    return authorization, payload


def _manifest_with_artifact(
    **updates: object,
) -> dict[str, object]:
    manifest = copy.deepcopy(TRUSTED_MANIFEST_RECORD)
    manifest["artifact_identities"][0].update(updates)
    return manifest


def _external_status_case() -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    document = _completed_registry()
    embedded_authority = document["owner_authorities"][0]
    trusted_authority = copy.deepcopy(TRUSTED_AUTHORITY_RECORD)
    receipt_binding = {
        "status_record_receipt_authority_revision": trusted_authority[
            "authority_revision"
        ],
        "status_record_receipt_id": (
            "trusted_status_receipt_person_a_extraction"
        ),
        "status_record_receipt_sha256": "9" * 64,
        "status_record_verification_mode": "external_receipt",
    }
    embedded_authority.update(receipt_binding)
    trusted_authority.update(receipt_binding)
    receipt = _external_receipt_for(trusted_authority)
    return document, trusted_authority, receipt


def _external_authorization_case() -> tuple[
    dict[str, object],
    dict[str, object],
]:
    authorization = copy.deepcopy(TRUSTED_ARTIFACT_AUTHORIZATION)
    authorization.update(
        {
            "authorization_record_receipt_authority_revision": "1" * 40,
            "authorization_record_receipt_id": (
                "receipt_person_a_extraction_authorization"
            ),
            "authorization_record_receipt_sha256": "8" * 64,
            "authorization_record_verification_mode": "external_receipt",
        }
    )
    receipt = {
        "receipt_authority_revision": "1" * 40,
        "receipt_id": "receipt_person_a_extraction_authorization",
        "receipt_sha256": "8" * 64,
        "verified_artifact_id": authorization["artifact_id"],
        "verified_artifact_sha256": authorization["artifact_sha256"],
        "verified_artifact_size": authorization["artifact_size_bytes"],
        "verified_artifact_type": authorization["artifact_type"],
        "verified_authority_id": authorization["authority_id"],
        "verified_authorization_record_id": authorization[
            "authorization_record_id"
        ],
        "verified_authorization_record_sha256": authorization[
            "authorization_record_sha256"
        ],
        "verified_decision": authorization["decision"],
        "verified_manifest_artifact_identity": authorization[
            "manifest_artifact_identity"
        ],
        "verified_manifest_id": authorization["manifest_id"],
        "verified_manifest_sha256": authorization["manifest_sha256"],
        "verified_owner_id": authorization["owner_id"],
        "verified_owner_revision": authorization["owner_authority_revision"],
        "verified_owner_status": authorization["owner_status"],
    }
    return authorization, receipt


def _trusted_authorities(
    authority: dict[str, object] | None = None,
    *,
    mode: str = "local_bytes",
    receipt: dict[str, object] | None = None,
) -> dict[str, object]:
    trusted_authority = copy.deepcopy(
        authority or TRUSTED_AUTHORITY_RECORD
    )
    return {
        trusted_authority["authority_id"]: {
            "authority": trusted_authority,
            "status_record_verification": {
                "external_receipt": (
                    copy.deepcopy(receipt)
                    if mode == "external_receipt"
                    else None
                ),
                "mode": mode,
            },
        }
    }


def _validate_authenticated(
    document: dict[str, object],
    *,
    authority: dict[str, object] | None = None,
    mode: str = "local_bytes",
    receipt: dict[str, object] | None = None,
    status_record_bytes: bytes | None = STATUS_RECORD_BYTES,
    previous_registry: dict[str, object] | None = None,
    artifact_bytes_by_id: dict[str, bytes] | None = None,
    artifact_authorization: dict[str, object] | None = None,
    authorization_mode: str = "local_bytes",
    authorization_receipt: dict[str, object] | None = None,
    authorization_record_bytes: bytes | None = AUTHORIZATION_RECORD_BYTES,
    trusted_manifest: dict[str, object] | None = None,
    artifact_receipt: dict[str, object] | None = None,
    include_artifact_authorization: bool = True,
    include_trusted_manifest: bool = True,
    include_artifact_receipt: bool = True,
) -> object:
    trusted_authority = authority or TRUSTED_AUTHORITY_RECORD
    trusted_authorization = (
        artifact_authorization or TRUSTED_ARTIFACT_AUTHORIZATION
    )
    trusted_manifest_record = trusted_manifest or TRUSTED_MANIFEST_RECORD
    trusted_receipt = artifact_receipt or TRUSTED_ARTIFACT_RECEIPT
    return validate_immutable_run_artifact_registry(
        document,
        previous_registry=previous_registry,
        artifact_bytes_by_id=artifact_bytes_by_id,
        trusted_owner_authorities=_trusted_authorities(
            trusted_authority,
            mode=mode,
            receipt=receipt,
        ),
        trusted_status_record_bytes=(
            {trusted_authority["status_record_id"]: status_record_bytes}
            if mode == "local_bytes" and status_record_bytes is not None
            else None
        ),
        trusted_artifact_authorizations=(
            {
                trusted_authorization["artifact_id"]: {
                    "authorization": copy.deepcopy(trusted_authorization),
                    "authorization_record_verification": {
                        "external_receipt": (
                            copy.deepcopy(authorization_receipt)
                            if authorization_mode == "external_receipt"
                            else None
                        ),
                        "mode": authorization_mode,
                    },
                }
            }
            if include_artifact_authorization
            else None
        ),
        trusted_authorization_record_bytes=(
            {
                trusted_authorization[
                    "authorization_record_id"
                ]: authorization_record_bytes
            }
            if include_artifact_authorization
            and authorization_mode == "local_bytes"
            and authorization_record_bytes is not None
            else None
        ),
        trusted_manifest_records=(
            {
                trusted_manifest_record["manifest_id"]: copy.deepcopy(
                    trusted_manifest_record
                )
            }
            if include_trusted_manifest
            else None
        ),
        trusted_artifact_receipts=(
            {
                trusted_receipt["receipt_id"]: copy.deepcopy(
                    trusted_receipt
                )
            }
            if include_artifact_receipt
            else None
        ),
    )


def _codes(result: object) -> set[ImmutableRegistryRejectionCode]:
    return {rejection.code for rejection in result.rejections}


def _set_run_lifecycle(
    document: dict[str, object],
    status: str,
    *,
    preserve_outputs: bool = False,
) -> None:
    run = document["runs"][0]
    run["status"] = status
    run["pending_reason"] = None
    run["failure_reason"] = None
    if not preserve_outputs:
        run["output_artifact_ids"] = []
    if status == "pending":
        run["started_at"] = None
        run["ended_at"] = None
        run["pending_reason"] = "Synthetic pending dependency."
    elif status == "running":
        run["started_at"] = "2026-01-01T00:00:01Z"
        run["ended_at"] = None
    elif status == "failed":
        run["started_at"] = "2026-01-01T00:00:01Z"
        run["ended_at"] = "2026-01-01T00:00:02Z"
        run["failure_reason"] = "Synthetic expected failure."


def _two_artifact_registry(source_status: str = "completed") -> dict[str, object]:
    document = _completed_registry()
    source_run = document["runs"][0]
    source_artifact = document["artifacts"][0]

    child_run = copy.deepcopy(source_run)
    child_run.update(
        {
            "command": ["synthetic-child"],
            "created_at": "2026-01-01T00:00:03Z",
            "ended_at": "2026-01-01T00:00:05Z",
            "input_artifact_ids": ["artifact_extraction"],
            "output_artifact_ids": ["artifact_child"],
            "run_id": "run_child",
            "started_at": "2026-01-01T00:00:04Z",
        }
    )
    child_artifact = copy.deepcopy(source_artifact)
    child_artifact.update(
        {
            "artifact_id": "artifact_child",
            "artifact_schema_version": "synthetic-activation-v0.1",
            "artifact_type": "activation",
            "byte_verification_id": "verification_artifact_child",
            "creator_run_id": "run_child",
            "direct_input_artifact_ids": ["artifact_extraction"],
            "manifest_artifact_identity": "person-a-activation-output-1",
            "sha256": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
            "size_bytes": 13,
            "uri": "memory://person-e-v2/child",
        }
    )
    child_verification = copy.deepcopy(document["byte_verifications"][0])
    child_verification.update(
        {
            "artifact_id": "artifact_child",
            "external_receipt_id": "receipt_person_a_child",
            "external_receipt_sha256": (
                "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
            ),
            "verification_id": "verification_artifact_child",
            "verified_at": "2026-01-01T00:00:06Z",
            "verified_sha256": child_artifact["sha256"],
            "verified_size_bytes": child_artifact["size_bytes"],
        }
    )
    document["manifests"][0]["artifact_identities"].append(
        child_artifact["manifest_artifact_identity"]
    )
    document["owner_authorities"][0]["authorized_artifact_types"].append(
        "activation"
    )
    document["runs"].append(child_run)
    document["artifacts"].append(child_artifact)
    document["byte_verifications"].append(child_verification)
    if source_status != "completed":
        _set_run_lifecycle(
            document,
            source_status,
            preserve_outputs=True,
        )
    return document


class TestImmutableRegistryV2Contract(unittest.TestCase):
    def assert_rejected_with(
        self,
        document: dict[str, object],
        code: ImmutableRegistryRejectionCode,
    ) -> None:
        result = _validate_authenticated(document)
        self.assertFalse(result.accepted)
        self.assertIn(code, _codes(result), result.rejections)

    def test_v1_valid_fixture_and_rejection_behavior_are_unchanged(self) -> None:
        valid = validate_immutable_run_artifact_registry(_load(V1_FIXTURE))
        rejected = validate_immutable_run_artifact_registry(
            _load(V1_REJECTED_FIXTURE)
        )
        self.assertTrue(valid.accepted, valid.rejections)
        self.assertFalse(rejected.accepted)
        self.assertIn(
            ImmutableRegistryRejectionCode.BROKEN_DIRECT_INPUT,
            _codes(rejected),
        )

    def test_minimal_pending_job_passes_without_placeholder(self) -> None:
        document = _pending_registry()
        result = validate_immutable_run_artifact_registry(document)
        self.assertTrue(result.accepted, result.rejections)
        self.assertEqual(document["runs"][0]["pending_reason"], (
            "Synthetic dependency is not yet available."
        ))
        self.assertEqual(document["artifacts"], [])

    def test_minimal_running_job_passes_without_placeholder(self) -> None:
        document = _pending_registry()
        _set_run_lifecycle(document, "running")
        result = validate_immutable_run_artifact_registry(document)
        self.assertTrue(result.accepted, result.rejections)
        self.assertEqual(document["artifacts"], [])

    def test_minimal_failed_job_passes_and_preserves_reason(self) -> None:
        document = _pending_registry()
        _set_run_lifecycle(document, "failed")
        result = validate_immutable_run_artifact_registry(document)
        self.assertTrue(result.accepted, result.rejections)
        self.assertEqual(
            document["runs"][0]["failure_reason"],
            "Synthetic expected failure.",
        )
        self.assertEqual(document["artifacts"], [])

    def test_completed_authenticated_extraction_passes(self) -> None:
        document = _completed_registry()
        result = _validate_authenticated(document)
        self.assertTrue(result.accepted, result.rejections)
        self.assertEqual(
            document["immutable_registry_schema_version"],
            IMMUTABLE_REGISTRY_V2_SCHEMA_VERSION,
        )
        self.assertEqual(document["artifacts"][0]["artifact_type"], "extraction")
        self.assertEqual(
            document["owner_authorities"][0],
            TRUSTED_AUTHORITY_RECORD,
        )

    def test_completed_artifact_requires_external_trust_anchor(self) -> None:
        document = _completed_registry()
        result = validate_immutable_run_artifact_registry(document)
        self.assertFalse(result.accepted)
        self.assertIn(
            ImmutableRegistryRejectionCode.MISSING_TRUSTED_AUTHORITY,
            _codes(result),
        )

    def test_missing_trusted_authority_id_fails(self) -> None:
        document = _completed_registry()
        fabricated_id = "fabricated_person_a_authority"
        document["owner_authorities"][0]["authority_id"] = fabricated_id
        document["artifacts"][0]["owner_authority_id"] = fabricated_id
        document["manifests"][0]["owner_authority_id"] = fabricated_id
        result = _validate_authenticated(document)
        self.assertFalse(result.accepted)
        self.assertIn(
            ImmutableRegistryRejectionCode.MISSING_TRUSTED_AUTHORITY,
            _codes(result),
        )

    def test_normalized_owner_status_catalog_and_accepted_pair(self) -> None:
        self.assertEqual(
            IMMUTABLE_V2_OWNER_STATUSES,
            {"pending", "accepted", "rejected", "failed", "superseded"},
        )
        result = _validate_authenticated(_completed_registry())
        self.assertTrue(result.accepted, result.rejections)

    def test_nonaccepted_or_arbitrary_owner_status_cannot_accept(self) -> None:
        for owner_status in (
            "PASS",
            "READY",
            "FAIL",
            "arbitrary-owner-status",
            "failed",
            "pending",
            "rejected",
            "superseded",
        ):
            with self.subTest(owner_status=owner_status):
                document = _completed_registry()
                document["owner_authorities"][0]["owner_status"] = owner_status
                result = _validate_authenticated(document)
                self.assertFalse(result.accepted)
                self.assertIn(
                    ImmutableRegistryRejectionCode.INVALID_AUTHORITY,
                    _codes(result),
                )

    def test_v2_fixtures_are_canonical_utf8_json_with_final_newline(self) -> None:
        for path in (V2_PENDING_FIXTURE, V2_COMPLETED_FIXTURE):
            with self.subTest(path=path.name):
                payload = path.read_bytes()
                self.assertFalse(payload.startswith(b"\xef\xbb\xbf"))
                self.assertTrue(payload.endswith(b"\n"))
                decoded = payload.decode("utf-8")
                canonical = json.dumps(
                    json.loads(decoded),
                    indent=2,
                    sort_keys=True,
                ) + "\n"
                self.assertEqual(decoded, canonical)

    def test_v2_catalog_and_step4_data_mapping_are_closed(self) -> None:
        expected_step4 = {
            "activation",
            "baseline",
            "data",
            "detection",
            "extraction",
            "figure",
            "fitted_probe",
            "metric_table",
            "model_input",
            "oracle_target",
            "prediction",
            "rollout",
        }
        self.assertEqual(set(IMMUTABLE_V2_STEP4_ARTIFACT_TYPE_MAP), expected_step4)
        self.assertEqual(
            IMMUTABLE_V2_STEP4_ARTIFACT_TYPE_MAP["data"],
            "raw_trajectory",
        )
        self.assertEqual(
            set(IMMUTABLE_V2_STEP4_ARTIFACT_TYPE_MAP.values())
            - IMMUTABLE_V2_ARTIFACT_TYPES,
            set(),
        )
        self.assertEqual(
            set(IMMUTABLE_V2_ARTIFACT_TYPES),
            set(IMMUTABLE_V2_STEP4_ARTIFACT_TYPE_MAP.values())
            | {
                "detector_calibration",
                "diagnostic_log",
                "figure_input",
                "homography",
                "input_context",
                "intervention_request",
                "localization",
                "measurement",
                "partial_rollout",
                "rollout_clip",
                "ssim",
            },
        )
        self.assertEqual(
            set(IMMUTABLE_V2_ARTIFACT_OWNER_IDS),
            set(IMMUTABLE_V2_ARTIFACT_TYPES),
        )
        self.assertEqual(
            IMMUTABLE_V2_RUN_STATUSES,
            {"pending", "running", "completed", "failed"},
        )

    def test_owner_authority_binding_is_mandatory_and_authenticated(self) -> None:
        mutations = {
            "missing binding": lambda document: document["artifacts"][0].pop(
                "owner_authority_id"
            ),
            "arbitrary authority": lambda document: document["artifacts"][0].update(
                {"owner_authority_id": "arbitrary_owner_claim"}
            ),
            "incorrect revision": lambda document: document["artifacts"][0].update(
                {"owner_authority_revision": "9" * 40}
            ),
            "missing status identity": lambda document: document["artifacts"][
                0
            ].pop("owner_status_record_id"),
            "incorrect status hash": lambda document: document["artifacts"][0].update(
                {"owner_status_record_sha256": "9" * 64}
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                document = _completed_registry()
                mutate(document)
                self.assertFalse(_validate_authenticated(document).accepted)

    def test_arbitrary_run_owner_is_not_acceptance_authority(self) -> None:
        document = _completed_registry()
        document["runs"][0]["owner"] = "arbitrary_owner"
        self.assert_rejected_with(
            document,
            ImmutableRegistryRejectionCode.INVALID_RUN,
        )

    def test_authenticated_wrong_owner_cannot_authorize_artifact_type(self) -> None:
        document = _completed_registry()
        document["owner_authorities"][0]["owner_id"] = "person_b"
        document["runs"][0]["owner"] = "person_b"
        self.assert_rejected_with(
            document,
            ImmutableRegistryRejectionCode.OWNER_AUTHORITY_MISMATCH,
        )

    def test_embedded_and_trusted_authority_identity_mismatches_fail(self) -> None:
        embedded_mutations = {
            "owner": lambda document: (
                document["owner_authorities"][0].update({"owner_id": "person_b"}),
                document["runs"][0].update({"owner": "person_b"}),
            ),
            "authority revision": lambda document: document["owner_authorities"][
                0
            ].update({"authority_revision": "8" * 40}),
            "status id": lambda document: document["owner_authorities"][0].update(
                {"status_record_id": "different_status_record"}
            ),
            "status hash": lambda document: document["owner_authorities"][0].update(
                {"status_record_sha256": "8" * 64}
            ),
        }
        for name, mutate in embedded_mutations.items():
            with self.subTest(kind="embedded", name=name):
                document = _completed_registry()
                mutate(document)
                self.assertFalse(_validate_authenticated(document).accepted)

        trusted_owner, trusted_owner_bytes = _authority_with_status_record(
            owner_id="person_b",
            authorized_artifact_types=["oracle_target"],
        )
        trusted_revision, trusted_revision_bytes = _authority_with_status_record(
            authority_revision="8" * 40
        )
        trusted_status_id, trusted_status_id_bytes = _authority_with_status_record(
            status_record_id="different_status_record"
        )
        trusted_cases = (
            ("owner", trusted_owner, trusted_owner_bytes),
            ("authority revision", trusted_revision, trusted_revision_bytes),
            ("status id", trusted_status_id, trusted_status_id_bytes),
        )
        for name, authority, payload in trusted_cases:
            with self.subTest(kind="trusted", name=name):
                result = _validate_authenticated(
                    _completed_registry(),
                    authority=authority,
                    status_record_bytes=payload,
                )
                self.assertFalse(result.accepted)
                self.assertIn(
                    ImmutableRegistryRejectionCode.OWNER_AUTHORITY_MISMATCH,
                    _codes(result),
                )

    def test_local_status_record_bytes_are_required_and_rehashed(self) -> None:
        missing = _validate_authenticated(
            _completed_registry(),
            status_record_bytes=None,
        )
        self.assertFalse(missing.accepted)
        self.assertIn(
            ImmutableRegistryRejectionCode.STATUS_RECORD_VERIFICATION_FAILED,
            _codes(missing),
        )

        wrong = _validate_authenticated(
            _completed_registry(),
            status_record_bytes=b"incorrect status record bytes\n",
        )
        self.assertFalse(wrong.accepted)
        self.assertIn(
            ImmutableRegistryRejectionCode.STATUS_RECORD_VERIFICATION_FAILED,
            _codes(wrong),
        )

    def test_local_status_record_content_must_match_trusted_authority(self) -> None:
        mismatches = {
            "owner": {"owner_id": "person_b"},
            "revision": {"authority_revision": "8" * 40},
            "status": {"owner_status": "failed"},
            "decision": {"decision": "failed"},
        }
        for name, overrides in mismatches.items():
            with self.subTest(name=name):
                document = _completed_registry()
                payload = _status_record_bytes_for(
                    document["owner_authorities"][0],
                    **overrides,
                )
                digest = hashlib.sha256(payload).hexdigest()
                document["owner_authorities"][0]["status_record_sha256"] = digest
                document["artifacts"][0]["owner_status_record_sha256"] = digest
                authority = copy.deepcopy(TRUSTED_AUTHORITY_RECORD)
                authority["status_record_sha256"] = digest
                result = _validate_authenticated(
                    document,
                    authority=authority,
                    status_record_bytes=payload,
                )
                self.assertFalse(result.accepted)
                self.assertIn(
                    ImmutableRegistryRejectionCode.STATUS_RECORD_VERIFICATION_FAILED,
                    _codes(result),
                )

    def test_external_status_record_receipt_can_authenticate(self) -> None:
        document, authority, receipt = _external_status_case()
        result = _validate_authenticated(
            document,
            authority=authority,
            mode="external_receipt",
            receipt=receipt,
            status_record_bytes=None,
        )
        self.assertTrue(result.accepted, result.rejections)

    def test_external_status_record_receipt_is_required_and_exact(self) -> None:
        document, authority, receipt = _external_status_case()
        missing = _validate_authenticated(
            document,
            authority=authority,
            mode="external_receipt",
            receipt=None,
            status_record_bytes=None,
        )
        self.assertFalse(missing.accepted)

        mutations = {
            "receipt id": {"receipt_id": "wrong_receipt"},
            "receipt hash": {"receipt_sha256": "8" * 64},
            "owner": {"verified_owner_id": "person_e"},
            "authority revision": {
                "receipt_authority_revision": "8" * 40
            },
            "verified authority revision": {
                "verified_owner_authority_revision": "8" * 40
            },
            "status id": {
                "verified_status_record_id": "wrong_status_record"
            },
            "status hash": {"verified_status_record_sha256": "8" * 64},
        }
        for name, updates in mutations.items():
            with self.subTest(name=name):
                mutated = copy.deepcopy(receipt)
                mutated.update(updates)
                result = _validate_authenticated(
                    document,
                    authority=authority,
                    mode="external_receipt",
                    receipt=mutated,
                    status_record_bytes=None,
                )
                self.assertFalse(result.accepted)
                self.assertIn(
                    ImmutableRegistryRejectionCode.STATUS_RECORD_VERIFICATION_FAILED,
                    _codes(result),
                )

    def test_fabricated_person_a_authority_without_anchor_fails(self) -> None:
        document = _completed_registry()
        result = validate_immutable_run_artifact_registry(document)
        self.assertFalse(result.accepted)
        self.assertIn(
            ImmutableRegistryRejectionCode.MISSING_TRUSTED_AUTHORITY,
            _codes(result),
        )

    def test_person_e_trust_anchor_cannot_authorize_person_a_extraction(
        self,
    ) -> None:
        person_e, person_e_bytes = _authority_with_status_record(
            owner_id="person_e",
            authorized_artifact_types=["detection"],
        )
        result = _validate_authenticated(
            _completed_registry(),
            authority=person_e,
            status_record_bytes=person_e_bytes,
        )
        self.assertFalse(result.accepted)
        self.assertIn(
            ImmutableRegistryRejectionCode.OWNER_AUTHORITY_MISMATCH,
            _codes(result),
        )

    def test_manifest_binding_is_mandatory_and_exact(self) -> None:
        mutations = {
            "missing id": lambda document: document["artifacts"][0].pop(
                "manifest_id"
            ),
            "missing hash": lambda document: document["artifacts"][0].pop(
                "manifest_sha256"
            ),
            "hash mismatch": lambda document: document["artifacts"][0].update(
                {"manifest_sha256": "8" * 64}
            ),
            "identity mismatch": lambda document: document["artifacts"][0].update(
                {"manifest_artifact_identity": "unlisted-output"}
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                document = _completed_registry()
                mutate(document)
                self.assertFalse(_validate_authenticated(document).accepted)

    def test_byte_verification_is_mandatory_and_placeholder_fails(self) -> None:
        without_binding = _completed_registry()
        without_binding["artifacts"][0]["byte_verification_id"] = None
        self.assert_rejected_with(
            without_binding,
            ImmutableRegistryRejectionCode.UNVERIFIED_ARTIFACT,
        )

        bare_placeholder = _completed_registry()
        bare_placeholder["byte_verifications"] = []
        bare_placeholder["artifacts"][0]["byte_verification_id"] = None
        self.assert_rejected_with(
            bare_placeholder,
            ImmutableRegistryRejectionCode.UNVERIFIED_ARTIFACT,
        )

    def test_local_byte_mode_recomputes_hash_and_size(self) -> None:
        document = _completed_registry()
        payload = b"local bytes\n"
        digest = hashlib.sha256(payload).hexdigest()
        artifact = document["artifacts"][0]
        verification = document["byte_verifications"][0]
        artifact.update({"sha256": digest, "size_bytes": len(payload)})
        verification.update(
            {
                "external_receipt_authority_revision": None,
                "external_receipt_id": None,
                "external_receipt_sha256": None,
                "mode": "local_bytes",
                "verified_sha256": digest,
                "verified_size_bytes": len(payload),
            }
        )
        authorization, authorization_bytes = _authorization_with_record(
            artifact_sha256=digest,
            artifact_size_bytes=len(payload),
        )
        trusted_manifest = _manifest_with_artifact(
            artifact_sha256=digest,
            artifact_size_bytes=len(payload),
        )
        accepted = _validate_authenticated(
            document,
            artifact_bytes_by_id={"artifact_extraction": payload},
            artifact_authorization=authorization,
            authorization_record_bytes=authorization_bytes,
            trusted_manifest=trusted_manifest,
        )
        self.assertTrue(accepted.accepted, accepted.rejections)
        self.assert_rejected_with(
            document,
            ImmutableRegistryRejectionCode.UNVERIFIED_ARTIFACT,
        )

    def test_pending_running_and_failed_runs_cannot_publish_accepted_artifacts(
        self,
    ) -> None:
        for status in ("pending", "running", "failed"):
            with self.subTest(status=status):
                document = _completed_registry()
                _set_run_lifecycle(document, status, preserve_outputs=True)
                result = _validate_authenticated(document)
                self.assertFalse(result.accepted)

    def test_accepted_artifact_cannot_depend_on_pending_or_failed_output(
        self,
    ) -> None:
        for status in ("pending", "failed"):
            with self.subTest(status=status):
                document = _two_artifact_registry(status)
                authority = copy.deepcopy(TRUSTED_AUTHORITY_RECORD)
                authority["authorized_artifact_types"].append("activation")
                result = _validate_authenticated(
                    document,
                    authority=authority,
                )
                self.assertFalse(result.accepted)
                self.assertIn(
                    ImmutableRegistryRejectionCode.AMBIGUOUS_LINEAGE,
                    _codes(result),
                )

    def test_missing_direct_input_still_fails(self) -> None:
        document = _completed_registry()
        document["artifacts"][0]["direct_input_artifact_ids"] = ["missing"]
        document["runs"][0]["input_artifact_ids"] = ["missing"]
        self.assert_rejected_with(
            document,
            ImmutableRegistryRejectionCode.BROKEN_DIRECT_INPUT,
        )

    def test_duplicate_run_artifact_authority_manifest_and_verification_fail(
        self,
    ) -> None:
        cases = (
            (
                "run",
                "runs",
                ImmutableRegistryRejectionCode.DUPLICATE_RUN_ID,
            ),
            (
                "artifact",
                "artifacts",
                ImmutableRegistryRejectionCode.DUPLICATE_ARTIFACT_ID,
            ),
            (
                "authority",
                "owner_authorities",
                ImmutableRegistryRejectionCode.DUPLICATE_AUTHORITY_ID,
            ),
            (
                "manifest",
                "manifests",
                ImmutableRegistryRejectionCode.DUPLICATE_MANIFEST_ID,
            ),
            (
                "verification",
                "byte_verifications",
                ImmutableRegistryRejectionCode.DUPLICATE_BYTE_VERIFICATION_ID,
            ),
        )
        for name, field, code in cases:
            with self.subTest(name=name):
                document = _completed_registry()
                document[field].append(copy.deepcopy(document[field][0]))
                self.assert_rejected_with(document, code)

    def test_direct_input_cycle_still_fails(self) -> None:
        document = _two_artifact_registry()
        document["artifacts"][0]["direct_input_artifact_ids"] = ["artifact_child"]
        document["runs"][0]["input_artifact_ids"] = ["artifact_child"]
        self.assert_rejected_with(
            document,
            ImmutableRegistryRejectionCode.AMBIGUOUS_LINEAGE,
        )

    def test_supersession_cycle_still_fails(self) -> None:
        document = _two_artifact_registry()
        first, second = document["artifacts"]
        first.update(
            {
                "status": "superseded",
                "status_reason": "Synthetic replacement.",
                "superseded_by": second["artifact_id"],
            }
        )
        second.update(
            {
                "status": "superseded",
                "status_reason": "Synthetic replacement.",
                "superseded_by": first["artifact_id"],
            }
        )
        self.assert_rejected_with(
            document,
            ImmutableRegistryRejectionCode.MALFORMED_SUPERSESSION,
        )

    def test_unknown_v2_field_and_stored_effective_state_fail(self) -> None:
        mutations = {
            "top-level": lambda document: document.update({"unknown": True}),
            "artifact": lambda document: document["artifacts"][0].update(
                {"unknown": True}
            ),
            "stored stale": lambda document: document["artifacts"][0].update(
                {"effective_status": "stale"}
            ),
            "stored invalid": lambda document: document["artifacts"][0].update(
                {"effective_status": "invalid"}
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                document = _completed_registry()
                mutate(document)
                self.assert_rejected_with(
                    document,
                    ImmutableRegistryRejectionCode.UNVERSIONED_SCHEMA_CHANGE,
                )

    def test_v2_field_on_v1_document_still_fails(self) -> None:
        document = _load(V1_FIXTURE)
        document["owner_authorities"] = []
        self.assert_rejected_with(
            document,
            ImmutableRegistryRejectionCode.UNVERSIONED_SCHEMA_CHANGE,
        )

    def test_unknown_registry_schema_version_fails_closed(self) -> None:
        document = _completed_registry()
        document["immutable_registry_schema_version"] = (
            "mineocclude-immutable-registry-v999.0"
        )
        self.assert_rejected_with(
            document,
            ImmutableRegistryRejectionCode.UNSUPPORTED_SCHEMA_VERSION,
        )

    def test_v2_pending_transition_to_completed_is_append_only(self) -> None:
        previous = _pending_registry()
        completed = _completed_registry()
        completed["registry_id"] = previous["registry_id"]
        completed_run = completed["runs"][0]
        completed_run.update(
            {
                "code_sha": previous["runs"][0]["code_sha"],
                "command": previous["runs"][0]["command"],
                "config_snapshot_hash": previous["runs"][0][
                    "config_snapshot_hash"
                ],
                "created_at": previous["runs"][0]["created_at"],
                "data_identity_hash": previous["runs"][0]["data_identity_hash"],
                "environment_hash": previous["runs"][0]["environment_hash"],
                "preprocess_hash": previous["runs"][0]["preprocess_hash"],
                "run_id": previous["runs"][0]["run_id"],
                "seeds": previous["runs"][0]["seeds"],
            }
        )
        completed["artifacts"][0]["creator_run_id"] = completed_run["run_id"]
        result = _validate_authenticated(
            completed,
            previous_registry=previous,
        )
        self.assertTrue(result.accepted, result.rejections)

    def test_v2_terminal_run_and_artifact_records_are_immutable(self) -> None:
        previous = _completed_registry()
        changed_run = copy.deepcopy(previous)
        changed_run["runs"][0]["command"] = ["silently-mutated"]
        self.assert_rejected_with_previous(
            changed_run,
            previous,
            ImmutableRegistryRejectionCode.COMPLETED_RUN_MUTATION,
        )
        changed_artifact = copy.deepcopy(previous)
        changed_artifact["artifacts"][0]["uri"] = (
            "memory://person-e-v2/silently-mutated"
        )
        self.assert_rejected_with_previous(
            changed_artifact,
            previous,
            ImmutableRegistryRejectionCode.IMMUTABLE_ARTIFACT_MUTATION,
        )

    def assert_rejected_with_previous(
        self,
        document: dict[str, object],
        previous: dict[str, object],
        code: ImmutableRegistryRejectionCode,
    ) -> None:
        result = _validate_authenticated(
            document,
            previous_registry=previous,
        )
        self.assertFalse(result.accepted)
        self.assertIn(code, _codes(result), result.rejections)

    def test_exact_artifact_authorization_is_external_and_field_exact(
        self,
    ) -> None:
        missing = _validate_authenticated(
            _completed_registry(),
            include_artifact_authorization=False,
        )
        self.assertFalse(missing.accepted)
        self.assertIn(
            ImmutableRegistryRejectionCode.MISSING_ARTIFACT_AUTHORIZATION,
            _codes(missing),
        )

        mutations = {
            "artifact id": {"artifact_id": "different_artifact"},
            "artifact type": {"artifact_type": "activation"},
            "artifact schema": {
                "artifact_schema_version": "different-artifact-schema"
            },
            "artifact hash": {"artifact_sha256": "7" * 64},
            "artifact size": {"artifact_size_bytes": 999},
            "manifest id": {"manifest_id": "different_manifest"},
            "manifest hash": {"manifest_sha256": "7" * 64},
            "manifest schema": {
                "manifest_schema_version": "different-manifest-schema"
            },
            "manifest identity": {
                "manifest_artifact_identity": "different-identity"
            },
            "owner revision": {"owner_authority_revision": "7" * 40},
        }
        for name, updates in mutations.items():
            with self.subTest(name=name):
                authorization, payload = _authorization_with_record(
                    **updates
                )
                result = _validate_authenticated(
                    _completed_registry(),
                    artifact_authorization=authorization,
                    authorization_record_bytes=payload,
                )
                self.assertFalse(result.accepted, result.rejections)

    def test_local_authorization_record_is_required_canonical_and_exact(
        self,
    ) -> None:
        missing = _validate_authenticated(
            _completed_registry(),
            authorization_record_bytes=None,
        )
        self.assertFalse(missing.accepted)
        wrong = _validate_authenticated(
            _completed_registry(),
            authorization_record_bytes=b"incorrect authorization bytes\n",
        )
        self.assertFalse(wrong.accepted)

        duplicate_payload = AUTHORIZATION_RECORD_BYTES.replace(
            b'  "owner_id": "person_a",\n',
            b'  "owner_id": "person_a",\n  "owner_id": "person_b",\n',
        )
        duplicate_authorization = copy.deepcopy(
            TRUSTED_ARTIFACT_AUTHORIZATION
        )
        duplicate_authorization["authorization_record_sha256"] = (
            hashlib.sha256(duplicate_payload).hexdigest()
        )
        duplicate = _validate_authenticated(
            _completed_registry(),
            artifact_authorization=duplicate_authorization,
            authorization_record_bytes=duplicate_payload,
        )
        self.assertFalse(duplicate.accepted)

        mismatches = {
            "owner": {"owner_id": "person_b"},
            "artifact": {"artifact_id": "different_artifact"},
            "manifest": {"manifest_id": "different_manifest"},
        }
        for name, updates in mismatches.items():
            with self.subTest(name=name):
                payload = _authorization_record_bytes_for(
                    TRUSTED_ARTIFACT_AUTHORIZATION,
                    **updates,
                )
                authorization = copy.deepcopy(
                    TRUSTED_ARTIFACT_AUTHORIZATION
                )
                authorization["authorization_record_sha256"] = (
                    hashlib.sha256(payload).hexdigest()
                )
                result = _validate_authenticated(
                    _completed_registry(),
                    artifact_authorization=authorization,
                    authorization_record_bytes=payload,
                )
                self.assertFalse(result.accepted)

    def test_external_authorization_receipt_is_required_and_exact(
        self,
    ) -> None:
        authorization, receipt = _external_authorization_case()
        valid = _validate_authenticated(
            _completed_registry(),
            artifact_authorization=authorization,
            authorization_mode="external_receipt",
            authorization_receipt=receipt,
            authorization_record_bytes=None,
        )
        self.assertTrue(valid.accepted, valid.rejections)

        missing = _validate_authenticated(
            _completed_registry(),
            artifact_authorization=authorization,
            authorization_mode="external_receipt",
            authorization_receipt=None,
            authorization_record_bytes=None,
        )
        self.assertFalse(missing.accepted)

        mutations = {
            "receipt id": {"receipt_id": "different_receipt"},
            "receipt hash": {"receipt_sha256": "7" * 64},
            "owner revision": {"verified_owner_revision": "7" * 40},
            "receipt revision": {"receipt_authority_revision": "7" * 40},
            "artifact hash": {"verified_artifact_sha256": "7" * 64},
        }
        for name, updates in mutations.items():
            with self.subTest(name=name):
                mutated = copy.deepcopy(receipt)
                mutated.update(updates)
                result = _validate_authenticated(
                    _completed_registry(),
                    artifact_authorization=authorization,
                    authorization_mode="external_receipt",
                    authorization_receipt=mutated,
                    authorization_record_bytes=None,
                )
                self.assertFalse(result.accepted)

    def test_trusted_manifest_is_required_and_exact(self) -> None:
        missing = _validate_authenticated(
            _completed_registry(),
            include_trusted_manifest=False,
        )
        self.assertFalse(missing.accepted)
        self.assertIn(
            ImmutableRegistryRejectionCode.MISSING_TRUSTED_MANIFEST,
            _codes(missing),
        )

        mutations = {
            "manifest hash": lambda manifest: manifest.update(
                {"manifest_sha256": "7" * 64}
            ),
            "owner": lambda manifest: manifest.update(
                {"owner_id": "person_e"}
            ),
            "owner revision": lambda manifest: manifest.update(
                {"owner_authority_revision": "7" * 40}
            ),
            "artifact absent": lambda manifest: manifest[
                "artifact_identities"
            ][0].update({"artifact_id": "different_artifact"}),
            "artifact hash": lambda manifest: manifest[
                "artifact_identities"
            ][0].update({"artifact_sha256": "7" * 64}),
            "artifact size": lambda manifest: manifest[
                "artifact_identities"
            ][0].update({"artifact_size_bytes": 999}),
            "artifact type": lambda manifest: manifest[
                "artifact_identities"
            ][0].update({"artifact_type": "activation"}),
            "manifest identity": lambda manifest: manifest[
                "artifact_identities"
            ][0].update(
                {"manifest_artifact_identity": "different-identity"}
            ),
            "nonaccepted": lambda manifest: manifest.update(
                {"decision": "excluded", "owner_status": "rejected"}
            ),
            "duplicate artifact": lambda manifest: manifest[
                "artifact_identities"
            ].append(copy.deepcopy(manifest["artifact_identities"][0])),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                manifest = copy.deepcopy(TRUSTED_MANIFEST_RECORD)
                mutate(manifest)
                result = _validate_authenticated(
                    _completed_registry(),
                    trusted_manifest=manifest,
                )
                self.assertFalse(result.accepted)

    def test_external_artifact_receipt_is_external_and_field_exact(
        self,
    ) -> None:
        missing = _validate_authenticated(
            _completed_registry(),
            include_artifact_receipt=False,
        )
        self.assertFalse(missing.accepted)
        self.assertIn(
            ImmutableRegistryRejectionCode.MISSING_TRUSTED_ARTIFACT_RECEIPT,
            _codes(missing),
        )
        mutations = {
            "receipt id": {"receipt_id": "different_receipt"},
            "receipt hash": {"receipt_sha256": "7" * 64},
            "owner": {"verified_owner_id": "person_e"},
            "receipt revision": {"receipt_authority_revision": "7" * 40},
            "owner revision": {
                "verified_owner_authority_revision": "7" * 40
            },
            "artifact id": {"verified_artifact_id": "different_artifact"},
            "artifact hash": {"verified_artifact_sha256": "7" * 64},
            "artifact size": {"verified_artifact_size": 999},
            "manifest": {"verified_manifest_id": "different_manifest"},
        }
        for name, updates in mutations.items():
            with self.subTest(name=name):
                receipt = copy.deepcopy(TRUSTED_ARTIFACT_RECEIPT)
                receipt.update(updates)
                result = _validate_authenticated(
                    _completed_registry(),
                    artifact_receipt=receipt,
                )
                self.assertFalse(result.accepted)

    def test_same_type_substitution_and_changed_embedded_manifest_fail(
        self,
    ) -> None:
        document = _completed_registry()
        replacement = b"person e replacement extraction bytes\n"
        replacement_sha = hashlib.sha256(replacement).hexdigest()
        artifact = document["artifacts"][0]
        artifact.update(
            {
                "manifest_artifact_identity": "replacement-identity",
                "sha256": replacement_sha,
                "size_bytes": len(replacement),
                "uri": "memory://person-e-v2/replacement",
            }
        )
        document["manifests"][0]["artifact_identities"] = [
            "replacement-identity"
        ]
        verification = document["byte_verifications"][0]
        verification.update(
            {
                "external_receipt_authority_revision": None,
                "external_receipt_id": None,
                "external_receipt_sha256": None,
                "mode": "local_bytes",
                "verified_sha256": replacement_sha,
                "verified_size_bytes": len(replacement),
            }
        )
        result = _validate_authenticated(
            document,
            artifact_bytes_by_id={"artifact_extraction": replacement},
        )
        self.assertFalse(result.accepted)
        self.assertIn(
            ImmutableRegistryRejectionCode.INVALID_ARTIFACT_AUTHORIZATION,
            _codes(result),
        )
        self.assertIn(
            ImmutableRegistryRejectionCode.TRUSTED_MANIFEST_MISMATCH,
            _codes(result),
        )

    def test_artifact_x_authorization_cannot_authorize_same_type_y(
        self,
    ) -> None:
        document = _completed_registry()
        artifact = document["artifacts"][0]
        artifact["artifact_id"] = "artifact_extraction_y"
        document["runs"][0]["output_artifact_ids"] = [
            "artifact_extraction_y"
        ]
        document["byte_verifications"][0]["artifact_id"] = (
            "artifact_extraction_y"
        )
        result = _validate_authenticated(document)
        self.assertFalse(result.accepted)
        self.assertIn(
            ImmutableRegistryRejectionCode.MISSING_ARTIFACT_AUTHORIZATION,
            _codes(result),
        )

    def test_malformed_unhashable_values_reject_without_crashing(self) -> None:
        mutations = (
            lambda document: document.update({"scientific_use": []}),
            lambda document: document["owner_authorities"][0].update(
                {"owner_id": []}
            ),
            lambda document: document["owner_authorities"][0].update(
                {"decision": {}}
            ),
            lambda document: document["manifests"][0].update({"decision": []}),
            lambda document: document["byte_verifications"][0].update(
                {"mode": {}}
            ),
            lambda document: document["runs"][0].update({"owner": []}),
            lambda document: document["runs"][0].update({"status": {}}),
            lambda document: document["artifacts"][0].update(
                {"artifact_type": []}
            ),
            lambda document: document["artifacts"][0].update({"status": {}}),
            lambda document: document["artifacts"][0].update(
                {"owner_decision": []}
            ),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                document = _completed_registry()
                mutate(document)
                result = _validate_authenticated(document)
                self.assertFalse(result.accepted)


if __name__ == "__main__":
    unittest.main()
