from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

from mineocclude.experiments.registry import (
    ImmutableRegistryIndex,
    ProvenanceError,
)

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "person_e"
    / "immutable_registry_v2_transitive_query.json"
)


def _load_registry() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _canonical_bytes(document: dict[str, object]) -> bytes:
    return (
        json.dumps(document, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _trust_inputs(
    registry: dict[str, object],
) -> dict[str, object]:
    authorities = {
        authority["authority_id"]: authority
        for authority in registry["owner_authorities"]
    }
    trusted_owner_authorities: dict[str, object] = {}
    trusted_status_record_bytes: dict[str, bytes] = {}
    for authority in authorities.values():
        status_record = {
            "authority_revision": authority["authority_revision"],
            "decision": authority["decision"],
            "owner_id": authority["owner_id"],
            "owner_status": authority["owner_status"],
            "schema_version": authority["status_record_schema_version"],
            "status_record_id": authority["status_record_id"],
        }
        payload = _canonical_bytes(status_record)
        if (
            hashlib.sha256(payload).hexdigest()
            != authority["status_record_sha256"]
        ):
            raise AssertionError("Synthetic status-record hash drifted.")
        trusted_owner_authorities[authority["authority_id"]] = {
            "authority": copy.deepcopy(authority),
            "status_record_verification": {
                "external_receipt": None,
                "mode": "local_bytes",
            },
        }
        trusted_status_record_bytes[authority["status_record_id"]] = payload

    trusted_artifact_authorizations: dict[str, object] = {}
    trusted_authorization_record_bytes: dict[str, bytes] = {}
    trusted_manifest_records: dict[str, object] = {}
    trusted_artifact_receipts: dict[str, object] = {}
    manifests = {
        manifest["manifest_id"]: manifest
        for manifest in registry["manifests"]
    }
    verifications = {
        verification["artifact_id"]: verification
        for verification in registry["byte_verifications"]
    }
    for artifact in registry["artifacts"]:
        authority = authorities[artifact["owner_authority_id"]]
        authorization_record = {
            "artifact_id": artifact["artifact_id"],
            "artifact_schema_version": artifact[
                "artifact_schema_version"
            ],
            "artifact_sha256": artifact["sha256"],
            "artifact_size_bytes": artifact["size_bytes"],
            "artifact_type": artifact["artifact_type"],
            "authority_id": authority["authority_id"],
            "authorization_id": (
                f"authorization_{artifact['artifact_id']}"
            ),
            "authorization_record_id": (
                f"authorization_record_{artifact['artifact_id']}"
            ),
            "decision": "accepted",
            "manifest_artifact_identity": artifact[
                "manifest_artifact_identity"
            ],
            "manifest_id": artifact["manifest_id"],
            "manifest_schema_version": artifact[
                "manifest_schema_version"
            ],
            "manifest_sha256": artifact["manifest_sha256"],
            "owner_authority_revision": authority["authority_revision"],
            "owner_id": authority["owner_id"],
            "owner_status": "accepted",
        }
        authorization_bytes = _canonical_bytes(authorization_record)
        authorization = {
            **authorization_record,
            "authorization_record_receipt_authority_revision": None,
            "authorization_record_receipt_id": None,
            "authorization_record_receipt_sha256": None,
            "authorization_record_sha256": hashlib.sha256(
                authorization_bytes
            ).hexdigest(),
            "authorization_record_verification_mode": "local_bytes",
        }
        trusted_artifact_authorizations[artifact["artifact_id"]] = {
            "authorization": authorization,
            "authorization_record_verification": {
                "external_receipt": None,
                "mode": "local_bytes",
            },
        }
        trusted_authorization_record_bytes[
            authorization["authorization_record_id"]
        ] = authorization_bytes

        manifest = manifests[artifact["manifest_id"]]
        trusted_manifest_records[manifest["manifest_id"]] = {
            "artifact_identities": [
                {
                    "artifact_id": artifact["artifact_id"],
                    "artifact_schema_version": artifact[
                        "artifact_schema_version"
                    ],
                    "artifact_sha256": artifact["sha256"],
                    "artifact_size_bytes": artifact["size_bytes"],
                    "artifact_type": artifact["artifact_type"],
                    "manifest_artifact_identity": artifact[
                        "manifest_artifact_identity"
                    ],
                }
            ],
            "decision": "accepted",
            "manifest_id": manifest["manifest_id"],
            "manifest_schema_version": manifest[
                "manifest_schema_version"
            ],
            "manifest_sha256": manifest["manifest_sha256"],
            "owner_authority_id": authority["authority_id"],
            "owner_authority_revision": authority[
                "authority_revision"
            ],
            "owner_id": authority["owner_id"],
            "owner_status": "accepted",
        }

        verification = verifications[artifact["artifact_id"]]
        trusted_artifact_receipts[
            verification["external_receipt_id"]
        ] = {
            "receipt_authority_revision": verification[
                "external_receipt_authority_revision"
            ],
            "receipt_id": verification["external_receipt_id"],
            "receipt_sha256": verification["external_receipt_sha256"],
            "verified_artifact_id": artifact["artifact_id"],
            "verified_artifact_schema_version": artifact[
                "artifact_schema_version"
            ],
            "verified_artifact_sha256": artifact["sha256"],
            "verified_artifact_size": artifact["size_bytes"],
            "verified_artifact_type": artifact["artifact_type"],
            "verified_manifest_artifact_identity": artifact[
                "manifest_artifact_identity"
            ],
            "verified_manifest_id": artifact["manifest_id"],
            "verified_manifest_sha256": artifact["manifest_sha256"],
            "verified_owner_authority_revision": authority[
                "authority_revision"
            ],
            "verified_owner_id": authority["owner_id"],
        }
    return {
        "trusted_artifact_authorizations": (
            trusted_artifact_authorizations
        ),
        "trusted_artifact_receipts": trusted_artifact_receipts,
        "trusted_authorization_record_bytes": (
            trusted_authorization_record_bytes
        ),
        "trusted_manifest_records": trusted_manifest_records,
        "trusted_owner_authorities": trusted_owner_authorities,
        "trusted_status_record_bytes": trusted_status_record_bytes,
    }


def _index(
    registry: dict[str, object] | None = None,
) -> ImmutableRegistryIndex:
    document = registry or _load_registry()
    return ImmutableRegistryIndex(document, **_trust_inputs(document))


def _artifact(
    registry: dict[str, object],
    artifact_id: str,
) -> dict[str, object]:
    return next(
        artifact
        for artifact in registry["artifacts"]
        if artifact["artifact_id"] == artifact_id
    )


def _run(
    registry: dict[str, object],
    run_id: str,
) -> dict[str, object]:
    return next(
        run for run in registry["runs"] if run["run_id"] == run_id
    )


def _manifest(
    registry: dict[str, object],
    manifest_id: str,
) -> dict[str, object]:
    return next(
        manifest
        for manifest in registry["manifests"]
        if manifest["manifest_id"] == manifest_id
    )


def _verification(
    registry: dict[str, object],
    artifact_id: str,
) -> dict[str, object]:
    return next(
        verification
        for verification in registry["byte_verifications"]
        if verification["artifact_id"] == artifact_id
    )


def _multi_output_registry() -> dict[str, object]:
    registry = _load_registry()
    detection = _artifact(registry, "artifact_detection")
    prediction = _artifact(registry, "artifact_prediction")
    for key in (
        "owner_authority_id",
        "owner_authority_revision",
        "owner_status_record_id",
        "owner_status_record_sha256",
        "owner_decision",
    ):
        detection[key] = prediction[key]
    detection["artifact_type"] = "prediction"
    _manifest(
        registry,
        detection["manifest_id"],
    )["owner_authority_id"] = detection["owner_authority_id"]

    producer = _run(registry, "run_detection")
    producer["owner"] = "person_b"
    producer["input_artifact_ids"] = [
        "artifact_fitted",
        "artifact_raw",
    ]
    producer["output_artifact_ids"] = [
        "artifact_detection",
        "artifact_prediction",
    ]
    prediction["creator_run_id"] = "run_detection"
    registry["runs"] = [
        run
        for run in registry["runs"]
        if run["run_id"] != "run_prediction"
    ]
    return registry


def _three_output_registry() -> dict[str, object]:
    registry = _multi_output_registry()
    prediction = _artifact(registry, "artifact_prediction")
    extra = copy.deepcopy(prediction)
    extra.update(
        {
            "artifact_id": "artifact_prediction_extra",
            "byte_verification_id": "verification_prediction_extra",
            "manifest_artifact_identity": (
                "synthetic-query-prediction-extra-entry"
            ),
            "manifest_id": "manifest_prediction_extra",
            "manifest_sha256": "d" * 64,
            "sha256": "e" * 64,
            "size_bytes": 108,
            "uri": "memory://person-e-v2-query/prediction-extra",
        }
    )
    registry["artifacts"].append(extra)

    manifest = copy.deepcopy(
        _manifest(registry, "manifest_prediction")
    )
    manifest.update(
        {
            "artifact_identities": [
                extra["manifest_artifact_identity"]
            ],
            "manifest_id": extra["manifest_id"],
            "manifest_sha256": extra["manifest_sha256"],
        }
    )
    registry["manifests"].append(manifest)

    verification = copy.deepcopy(
        _verification(registry, "artifact_prediction")
    )
    verification.update(
        {
            "artifact_id": extra["artifact_id"],
            "external_receipt_id": "receipt_prediction_extra",
            "external_receipt_sha256": "c" * 64,
            "verification_id": extra["byte_verification_id"],
            "verified_sha256": extra["sha256"],
            "verified_size_bytes": extra["size_bytes"],
        }
    )
    registry["byte_verifications"].append(verification)

    _run(registry, "run_detection")["output_artifact_ids"].append(
        extra["artifact_id"]
    )
    _artifact(registry, "artifact_metric")[
        "direct_input_artifact_ids"
    ].append(extra["artifact_id"])
    _run(registry, "run_metric")["input_artifact_ids"].append(
        extra["artifact_id"]
    )
    return registry


def _root_dependency_registry() -> dict[str, object]:
    registry = _multi_output_registry()
    _artifact(registry, "artifact_prediction")[
        "direct_input_artifact_ids"
    ] = ["artifact_detection"]
    _run(registry, "run_detection")["input_artifact_ids"] = [
        "artifact_detection",
        "artifact_raw",
    ]
    _artifact(registry, "artifact_metric")[
        "direct_input_artifact_ids"
    ] = ["artifact_prediction"]
    _run(registry, "run_metric")["input_artifact_ids"] = [
        "artifact_prediction"
    ]
    return registry


def _three_root_chain_registry() -> dict[str, object]:
    registry = _three_output_registry()
    _artifact(registry, "artifact_prediction")[
        "direct_input_artifact_ids"
    ] = ["artifact_detection"]
    _artifact(registry, "artifact_prediction_extra")[
        "direct_input_artifact_ids"
    ] = ["artifact_prediction"]
    _run(registry, "run_detection")["input_artifact_ids"] = [
        "artifact_detection",
        "artifact_prediction",
        "artifact_raw",
    ]
    _artifact(registry, "artifact_metric")[
        "direct_input_artifact_ids"
    ] = ["artifact_prediction_extra"]
    _run(registry, "run_metric")["input_artifact_ids"] = [
        "artifact_prediction_extra"
    ]
    return registry


def _affected_row(
    result: dict[str, object],
    artifact_id: str,
) -> dict[str, object]:
    return next(
        row
        for row in result["affected_artifacts"]
        if row["affected_artifact_id"] == artifact_id
    )


class TestImmutableRegistryV2Queries(unittest.TestCase):
    def test_fixture_is_synthetic_and_validated_with_external_trust(
        self,
    ) -> None:
        registry = _load_registry()
        self.assertIs(registry["synthetic"], True)
        self.assertEqual(registry["scientific_use"], "forbidden")
        self.assertEqual(len(registry["artifacts"]), 10)
        self.assertIsInstance(_index(registry), ImmutableRegistryIndex)

    def test_fixture_uses_repository_canonical_serialization(self) -> None:
        payload = FIXTURE.read_bytes()
        self.assertFalse(payload.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(
            payload,
            (
                json.dumps(
                    json.loads(payload.decode("utf-8")),
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            ).encode("utf-8"),
        )

    def test_forward_artifact_query_returns_every_descendant_once(
        self,
    ) -> None:
        result = _index().forward_artifact_impact("artifact_raw")
        ids = [
            row["affected_artifact_id"]
            for row in result["affected_artifacts"]
        ]
        self.assertEqual(
            ids,
            [
                "artifact_detection",
                "artifact_model",
                "artifact_extraction",
                "artifact_metric",
                "artifact_activation",
                "artifact_figure",
                "artifact_fitted",
                "artifact_prediction",
            ],
        )
        self.assertEqual(len(ids), len(set(ids)))
        self.assertNotIn("artifact_unaffected", ids)

    def test_forward_run_query_unions_all_output_descendants(self) -> None:
        registry = _load_registry()
        raw_run = next(
            run for run in registry["runs"] if run["run_id"] == "run_raw"
        )
        unaffected = next(
            artifact
            for artifact in registry["artifacts"]
            if artifact["artifact_id"] == "artifact_unaffected"
        )
        registry["runs"] = [
            run
            for run in registry["runs"]
            if run["run_id"] != "run_unaffected"
        ]
        raw_run["output_artifact_ids"].append("artifact_unaffected")
        unaffected["creator_run_id"] = "run_raw"
        result = _index(registry).forward_run_impact("run_raw")
        self.assertEqual(
            result["subject_output_artifact_ids"],
            ["artifact_raw", "artifact_unaffected"],
        )
        self.assertEqual(
            {
                row["affected_artifact_id"]
                for row in result["affected_artifacts"]
            },
            {
                "artifact_activation",
                "artifact_detection",
                "artifact_extraction",
                "artifact_figure",
                "artifact_fitted",
                "artifact_metric",
                "artifact_model",
                "artifact_prediction",
            },
        )

    def test_run_roots_are_separate_while_traversal_continues(self) -> None:
        result = _index(_root_dependency_registry()).forward_run_impact(
            "run_detection"
        )
        self.assertEqual(
            result["subject_output_artifact_ids"],
            ["artifact_detection", "artifact_prediction"],
        )
        self.assertEqual(
            result["subject_output_dependency_edges"],
            [
                {
                    "downstream_subject_output_artifact_id": (
                        "artifact_prediction"
                    ),
                    "relationship": "direct_input_artifact_ids",
                    "upstream_subject_output_artifact_id": (
                        "artifact_detection"
                    ),
                }
            ],
        )
        affected = {
            row["affected_artifact_id"]: row
            for row in result["affected_artifacts"]
        }
        self.assertEqual(set(affected), {"artifact_metric", "artifact_figure"})
        self.assertEqual(affected["artifact_metric"]["graph_distance"], 1)
        self.assertEqual(affected["artifact_figure"]["graph_distance"], 2)
        self.assertEqual(
            affected["artifact_metric"]["causal_paths"],
            [
                [
                    "artifact_detection",
                    "artifact_prediction",
                    "artifact_metric",
                ],
                ["artifact_prediction", "artifact_metric"],
            ],
        )
        self.assertEqual(
            affected["artifact_figure"]["causal_paths"],
            [
                [
                    "artifact_detection",
                    "artifact_prediction",
                    "artifact_metric",
                    "artifact_figure",
                ],
                [
                    "artifact_prediction",
                    "artifact_metric",
                    "artifact_figure",
                ],
            ],
        )

    def test_dependent_subject_root_has_distance_zero_and_details(self) -> None:
        result = _index(_root_dependency_registry()).forward_run_impact(
            "run_detection"
        )
        roots = {
            row["artifact_id"]: row
            for row in result["subject_output_artifacts"]
        }
        prediction = roots["artifact_prediction"]
        self.assertEqual(prediction["subject_distance"], 0)
        self.assertEqual(prediction["artifact_type"], "prediction")
        self.assertEqual(prediction["creator_run_id"], "run_detection")
        self.assertEqual(prediction["base_lifecycle_status"], "accepted")
        self.assertIsNone(
            prediction["assigned_hypothetical_root_state"]
        )
        self.assertEqual(prediction["effective_state"], "current")
        self.assertEqual(
            prediction[
                "direct_subject_output_dependency_artifact_ids"
            ],
            ["artifact_detection"],
        )
        self.assertEqual(
            prediction["causal_paths_from_subject_outputs"],
            [["artifact_detection", "artifact_prediction"]],
        )

    def test_artifact_query_still_returns_reachable_run_root(self) -> None:
        result = _index(_root_dependency_registry()).forward_artifact_impact(
            "artifact_detection"
        )
        affected = [
            row["affected_artifact_id"]
            for row in result["affected_artifacts"]
        ]
        self.assertEqual(
            affected,
            ["artifact_prediction", "artifact_metric", "artifact_figure"],
        )

    def test_three_root_chain_keeps_all_roots_separate(self) -> None:
        result = _index(_three_root_chain_registry()).forward_run_impact(
            "run_detection"
        )
        roots = {
            row["artifact_id"]: row
            for row in result["subject_output_artifacts"]
        }
        self.assertEqual(
            set(roots),
            {
                "artifact_detection",
                "artifact_prediction",
                "artifact_prediction_extra",
            },
        )
        self.assertTrue(
            all(row["subject_distance"] == 0 for row in roots.values())
        )
        self.assertEqual(
            {
                row["affected_artifact_id"]
                for row in result["affected_artifacts"]
            },
            {"artifact_metric", "artifact_figure"},
        )
        extra = roots["artifact_prediction_extra"]
        self.assertEqual(
            extra["causal_paths_from_subject_outputs"],
            [
                [
                    "artifact_detection",
                    "artifact_prediction",
                    "artifact_prediction_extra",
                ],
                ["artifact_prediction", "artifact_prediction_extra"],
            ],
        )
        self.assertEqual(
            result["subject_output_dependency_edges"],
            [
                {
                    "downstream_subject_output_artifact_id": (
                        "artifact_prediction"
                    ),
                    "relationship": "direct_input_artifact_ids",
                    "upstream_subject_output_artifact_id": (
                        "artifact_detection"
                    ),
                },
                {
                    "downstream_subject_output_artifact_id": (
                        "artifact_prediction_extra"
                    ),
                    "relationship": "direct_input_artifact_ids",
                    "upstream_subject_output_artifact_id": (
                        "artifact_prediction"
                    ),
                },
            ],
        )

    def test_root_dependency_preserves_mixed_causes(self) -> None:
        mapping = {
            "artifact_detection": "stale",
            "artifact_prediction": "invalid",
        }
        original = copy.deepcopy(mapping)
        registry = _root_dependency_registry()
        original_registry = copy.deepcopy(registry)
        result = _index(registry).forward_run_impact(
            "run_detection",
            root_effective_states_by_artifact_id=mapping,
        )
        roots = {
            row["artifact_id"]: row
            for row in result["subject_output_artifacts"]
        }
        prediction = roots["artifact_prediction"]
        self.assertEqual(prediction["effective_state"], "invalid")
        self.assertEqual(
            prediction["stale_root_cause_artifact_ids"],
            ["artifact_detection"],
        )
        self.assertEqual(
            prediction["invalid_root_cause_artifact_ids"],
            ["artifact_prediction"],
        )
        self.assertEqual(
            prediction["root_cause_artifact_ids"],
            ["artifact_detection", "artifact_prediction"],
        )
        metric = _affected_row(result, "artifact_metric")
        self.assertEqual(metric["effective_state"], "invalid")
        self.assertEqual(
            metric["stale_root_cause_artifact_ids"],
            ["artifact_detection"],
        )
        self.assertEqual(
            metric["invalid_root_cause_artifact_ids"],
            ["artifact_prediction"],
        )
        self.assertEqual(len(metric["causal_path_causes"]), 2)
        self.assertEqual(mapping, original)
        self.assertEqual(registry, original_registry)

    def test_root_separation_is_invariant_to_output_order(self) -> None:
        first_registry = _three_root_chain_registry()
        second_registry = copy.deepcopy(first_registry)
        _run(second_registry, "run_detection")[
            "output_artifact_ids"
        ].reverse()
        first = _index(first_registry).forward_run_impact("run_detection")
        second = _index(second_registry).forward_run_impact("run_detection")
        self.assertEqual(first, second)
        for result in (first, second):
            roots = set(result["subject_output_artifact_ids"])
            affected = {
                row["affected_artifact_id"]
                for row in result["affected_artifacts"]
            }
            self.assertFalse(roots & affected)

    def test_every_run_query_keeps_roots_out_of_affected(self) -> None:
        cases = (
            (_load_registry(), "run_raw", {}),
            (_multi_output_registry(), "run_detection", {}),
            (
                _multi_output_registry(),
                "run_detection",
                {"root_effective_state": "stale"},
            ),
            (
                _multi_output_registry(),
                "run_detection",
                {
                    "root_effective_states_by_artifact_id": {
                        "artifact_detection": "stale",
                        "artifact_prediction": "invalid",
                    }
                },
            ),
            (_three_output_registry(), "run_detection", {}),
            (_root_dependency_registry(), "run_detection", {}),
            (_three_root_chain_registry(), "run_detection", {}),
        )
        for registry, run_id, kwargs in cases:
            with self.subTest(
                registry=registry["registry_id"],
                outputs=_run(registry, run_id)["output_artifact_ids"],
                kwargs=kwargs,
            ):
                result = _index(registry).forward_run_impact(
                    run_id,
                    **kwargs,
                )
                roots = set(result["subject_output_artifact_ids"])
                affected = {
                    row["affected_artifact_id"]
                    for row in result["affected_artifacts"]
                }
                self.assertFalse(roots & affected)

    def test_backward_figure_provenance_reconstructs_all_layers(
        self,
    ) -> None:
        result = _index().backward_provenance("artifact_figure")
        ids = {row["artifact_id"] for row in result["upstream_artifacts"]}
        self.assertEqual(
            ids,
            {
                "artifact_activation",
                "artifact_detection",
                "artifact_extraction",
                "artifact_fitted",
                "artifact_metric",
                "artifact_model",
                "artifact_prediction",
                "artifact_raw",
            },
        )
        raw = next(
            row
            for row in result["upstream_artifacts"]
            if row["artifact_id"] == "artifact_raw"
        )
        self.assertEqual(len(raw["causal_paths"]), 2)
        self.assertTrue(raw["multiple_causal_paths"])

    def test_every_returned_edge_is_an_explicit_direct_input(self) -> None:
        registry = _load_registry()
        explicit_edges = {
            (input_id, artifact["artifact_id"])
            for artifact in registry["artifacts"]
            for input_id in artifact["direct_input_artifact_ids"]
        }
        result = _index(registry).backward_provenance(
            "artifact_figure"
        )
        returned_edges = {
            (edge["input_artifact_id"], edge["output_artifact_id"])
            for edge in result["direct_input_edges"]
        }
        self.assertEqual(returned_edges, explicit_edges)

    def test_graph_distances_and_discovery_predecessors_are_exact(
        self,
    ) -> None:
        rows = {
            row["affected_artifact_id"]: row
            for row in _index().forward_artifact_impact("artifact_raw")[
                "affected_artifacts"
            ]
        }
        self.assertEqual(rows["artifact_model"]["graph_distance"], 1)
        self.assertEqual(rows["artifact_detection"]["graph_distance"], 1)
        self.assertEqual(rows["artifact_metric"]["graph_distance"], 2)
        self.assertEqual(rows["artifact_figure"]["graph_distance"], 3)
        self.assertEqual(
            rows["artifact_metric"]["discovery_predecessor_artifact_id"],
            "artifact_detection",
        )

    def test_multiple_causal_paths_are_complete_and_deterministic(
        self,
    ) -> None:
        index = _index()
        first = index.forward_artifact_impact("artifact_raw")
        second = index.forward_artifact_impact("artifact_raw")
        self.assertEqual(first, second)
        metric = next(
            row
            for row in first["affected_artifacts"]
            if row["affected_artifact_id"] == "artifact_metric"
        )
        self.assertTrue(metric["multiple_causal_paths"])
        self.assertEqual(len(metric["causal_paths"]), 2)
        self.assertEqual(metric["causal_paths"], sorted(metric["causal_paths"]))

    def test_no_lineage_is_inferred_from_metadata(self) -> None:
        registry = _load_registry()
        for artifact in registry["artifacts"]:
            artifact["uri"] = (
                "memory://misleading/shared-name-and-owner-like-path"
            )
        registry["artifacts"].reverse()
        registry["runs"].reverse()
        result = _index(registry).forward_artifact_impact("artifact_raw")
        ids = {
            row["affected_artifact_id"]
            for row in result["affected_artifacts"]
        }
        self.assertNotIn("artifact_unaffected", ids)
        self.assertIn("artifact_figure", ids)

    def test_supersession_reports_direct_transitive_and_unaffected(
        self,
    ) -> None:
        result = _index().supersession_impact("artifact_raw")
        self.assertEqual(
            result["directly_affected_artifact_ids"],
            ["artifact_detection", "artifact_model"],
        )
        self.assertEqual(
            set(result["transitively_affected_artifact_ids"]),
            {
                "artifact_activation",
                "artifact_extraction",
                "artifact_figure",
                "artifact_fitted",
                "artifact_metric",
                "artifact_prediction",
            },
        )
        self.assertEqual(
            result["unaffected_artifact_ids"],
            ["artifact_unaffected"],
        )
        self.assertEqual(result["invalid_artifact_ids"], [])
        self.assertEqual(len(result["stale_artifact_ids"]), 8)
        self.assertIs(
            result["superseded_source"]["current_usable_input"],
            False,
        )
        self.assertEqual(
            result["unaffected_artifacts"],
            [
                {
                    "artifact_id": "artifact_unaffected",
                    "effective_state": "current",
                }
            ],
        )

    def test_stale_and_invalid_states_propagate_transitively(self) -> None:
        stale = _index().forward_artifact_impact(
            "artifact_raw",
            root_effective_state="stale",
        )
        invalid = _index().forward_artifact_impact(
            "artifact_raw",
            root_effective_state="invalid",
        )
        self.assertTrue(
            all(
                row["effective_state"] == "stale"
                for row in stale["affected_artifacts"]
            )
        )
        self.assertTrue(
            all(
                row["effective_state"] == "invalid"
                for row in invalid["affected_artifacts"]
            )
        )
        self.assertTrue(
            all(
                row["root_cause_artifact_ids"] == ["artifact_raw"]
                for row in stale["affected_artifacts"]
            )
        )

    def test_mixed_diamond_state_and_cause_inventories(self) -> None:
        index = _index(_multi_output_registry())
        cases = (
            (
                {"artifact_detection": "stale"},
                "stale",
                ["artifact_detection"],
                [],
            ),
            (
                {"artifact_detection": "invalid"},
                "invalid",
                [],
                ["artifact_detection"],
            ),
            (
                {
                    "artifact_detection": "stale",
                    "artifact_prediction": "invalid",
                },
                "invalid",
                ["artifact_detection"],
                ["artifact_prediction"],
            ),
            (
                {
                    "artifact_detection": "stale",
                    "artifact_prediction": "stale",
                },
                "stale",
                ["artifact_detection", "artifact_prediction"],
                [],
            ),
            (
                {
                    "artifact_detection": "invalid",
                    "artifact_prediction": "invalid",
                },
                "invalid",
                [],
                ["artifact_detection", "artifact_prediction"],
            ),
        )
        for mapping, state, stale_roots, invalid_roots in cases:
            with self.subTest(mapping=mapping):
                result = index.forward_run_impact(
                    "run_detection",
                    root_effective_states_by_artifact_id=mapping,
                )
                metric = _affected_row(result, "artifact_metric")
                self.assertEqual(metric["effective_state"], state)
                self.assertEqual(
                    metric["stale_root_cause_artifact_ids"],
                    stale_roots,
                )
                self.assertEqual(
                    metric["invalid_root_cause_artifact_ids"],
                    invalid_roots,
                )
                self.assertEqual(
                    metric["root_cause_artifact_ids"],
                    sorted({*stale_roots, *invalid_roots}),
                )
        mixed = _affected_row(
            index.forward_run_impact(
                "run_detection",
                root_effective_states_by_artifact_id={
                    "artifact_detection": "stale",
                    "artifact_prediction": "invalid",
                },
            ),
            "artifact_metric",
        )
        self.assertEqual(
            mixed["effective_state_reason"],
            "invalid_precedence_with_stale_causes",
        )
        self.assertEqual(
            mixed["stale_root_causal_paths"],
            [["artifact_detection", "artifact_metric"]],
        )
        self.assertEqual(
            mixed["invalid_root_causal_paths"],
            [["artifact_prediction", "artifact_metric"]],
        )

    def test_three_mixed_roots_are_all_retained(self) -> None:
        index = _index(_three_output_registry())
        cases = (
            (
                {
                    "artifact_detection": "stale",
                    "artifact_prediction": "invalid",
                    "artifact_prediction_extra": "stale",
                },
                ["artifact_detection", "artifact_prediction_extra"],
                ["artifact_prediction"],
            ),
            (
                {
                    "artifact_detection": "stale",
                    "artifact_prediction": "invalid",
                    "artifact_prediction_extra": "invalid",
                },
                ["artifact_detection"],
                ["artifact_prediction", "artifact_prediction_extra"],
            ),
        )
        for mapping, stale_roots, invalid_roots in cases:
            with self.subTest(mapping=mapping):
                result = index.forward_run_impact(
                    "run_detection",
                    root_effective_states_by_artifact_id=mapping,
                )
                figure = _affected_row(result, "artifact_figure")
                self.assertEqual(figure["effective_state"], "invalid")
                self.assertEqual(
                    figure["stale_root_cause_artifact_ids"],
                    stale_roots,
                )
                self.assertEqual(
                    figure["invalid_root_cause_artifact_ids"],
                    invalid_roots,
                )
                self.assertEqual(
                    figure["root_cause_artifact_ids"],
                    sorted({*stale_roots, *invalid_roots}),
                )
                self.assertEqual(
                    len(figure["causal_path_causes"]),
                    3,
                )

    def test_same_root_retains_every_distinct_causal_path(self) -> None:
        result = _index().forward_artifact_impact(
            "artifact_raw",
            root_effective_state="stale",
        )
        metric = _affected_row(result, "artifact_metric")
        self.assertEqual(
            metric["stale_root_cause_artifact_ids"],
            ["artifact_raw"],
        )
        self.assertEqual(len(metric["stale_root_causal_paths"]), 2)
        self.assertEqual(len(metric["causal_path_causes"]), 2)
        self.assertEqual(
            metric["stale_root_causal_paths"],
            sorted(metric["stale_root_causal_paths"]),
        )

    def test_shared_intermediate_retains_each_originating_root(self) -> None:
        mapping = {
            "artifact_detection": "stale",
            "artifact_prediction": "invalid",
            "artifact_prediction_extra": "stale",
        }
        result = _index(_three_output_registry()).forward_run_impact(
            "run_detection",
            root_effective_states_by_artifact_id=mapping,
        )
        figure = _affected_row(result, "artifact_figure")
        self.assertEqual(
            figure["root_cause_artifact_ids"],
            [
                "artifact_detection",
                "artifact_prediction",
                "artifact_prediction_extra",
            ],
        )
        self.assertEqual(
            {path[-2] for path in figure["causal_paths"]},
            {"artifact_metric"},
        )
        self.assertEqual(len(figure["causal_path_causes"]), 3)

    def test_scalar_run_state_remains_backwards_compatible(self) -> None:
        index = _index(_multi_output_registry())
        scalar = index.forward_run_impact(
            "run_detection",
            root_effective_state="stale",
        )
        mapped = index.forward_run_impact(
            "run_detection",
            root_effective_states_by_artifact_id={
                "artifact_detection": "stale",
                "artifact_prediction": "stale",
            },
        )
        self.assertEqual(
            scalar["affected_artifacts"],
            mapped["affected_artifacts"],
        )
        self.assertEqual(scalar["root_effective_state"], "stale")
        self.assertEqual(
            scalar["root_effective_states_by_artifact_id"],
            {
                "artifact_detection": "stale",
                "artifact_prediction": "stale",
            },
        )

    def test_per_root_run_state_validation_fails_closed(self) -> None:
        index = _index(_multi_output_registry())
        invalid_mappings = (
            {"missing_artifact": "stale"},
            {"artifact_raw": "stale"},
            {"artifact_detection": "current"},
            {"artifact_detection": "arbitrary"},
        )
        for mapping in invalid_mappings:
            with (
                self.subTest(mapping=mapping),
                self.assertRaises(ProvenanceError),
            ):
                index.forward_run_impact(
                    "run_detection",
                    root_effective_states_by_artifact_id=mapping,
                )
        with self.assertRaises(ProvenanceError):
            index.forward_run_impact(
                "run_detection",
                root_effective_state="stale",
                root_effective_states_by_artifact_id={},
            )
        with self.assertRaises(ProvenanceError):
            index.forward_run_impact(
                "run_detection",
                root_effective_states_by_artifact_id=[],
            )

    def test_empty_and_reordered_root_state_mappings_are_deterministic(
        self,
    ) -> None:
        index = _index(_multi_output_registry())
        self.assertEqual(
            index.forward_run_impact("run_detection"),
            index.forward_run_impact(
                "run_detection",
                root_effective_states_by_artifact_id={},
            ),
        )
        first_mapping = {
            "artifact_detection": "stale",
            "artifact_prediction": "invalid",
        }
        second_mapping = {
            "artifact_prediction": "invalid",
            "artifact_detection": "stale",
        }
        original = copy.deepcopy(first_mapping)
        first = index.forward_run_impact(
            "run_detection",
            root_effective_states_by_artifact_id=first_mapping,
        )
        second = index.forward_run_impact(
            "run_detection",
            root_effective_states_by_artifact_id=second_mapping,
        )
        self.assertEqual(first, second)
        self.assertEqual(first_mapping, original)
        self.assertEqual(
            first["subject_output_artifact_ids"],
            ["artifact_detection", "artifact_prediction"],
        )
        self.assertFalse(
            set(first["subject_output_artifact_ids"])
            & {
                row["affected_artifact_id"]
                for row in first["affected_artifacts"]
            }
        )
        self.assertEqual(
            len(
                [
                    row
                    for row in first["affected_artifacts"]
                    if row["affected_artifact_id"] == "artifact_metric"
                ]
            ),
            1,
        )

    def test_cause_sets_are_deterministic_and_not_cached_mutably(
        self,
    ) -> None:
        registry = _three_output_registry()
        original_registry = copy.deepcopy(registry)
        mapping = {
            "artifact_detection": "stale",
            "artifact_prediction": "invalid",
            "artifact_prediction_extra": "stale",
        }
        original_mapping = copy.deepcopy(mapping)
        index = _index(registry)
        first = index.forward_run_impact(
            "run_detection",
            root_effective_states_by_artifact_id=mapping,
        )
        index.forward_run_impact(
            "run_detection",
            root_effective_states_by_artifact_id={
                "artifact_prediction": "stale",
            },
        )
        second = index.forward_run_impact(
            "run_detection",
            root_effective_states_by_artifact_id=mapping,
        )
        self.assertEqual(first, second)
        self.assertEqual(mapping, original_mapping)
        self.assertEqual(registry, original_registry)

    def test_shared_downstream_is_affected_by_one_superseded_branch(
        self,
    ) -> None:
        impact = _index().supersession_impact("artifact_detection")
        self.assertEqual(
            impact["stale_artifact_ids"],
            ["artifact_metric", "artifact_figure"],
        )
        self.assertIn("artifact_prediction", impact["unaffected_artifact_ids"])
        metric = impact["affected_artifacts"][0]
        self.assertEqual(metric["root_cause_artifact_ids"], ["artifact_detection"])

    def test_unaffected_branch_remains_current_and_queryable(self) -> None:
        index = _index()
        impact = index.supersession_impact("artifact_raw")
        self.assertIn("artifact_unaffected", impact["unaffected_artifact_ids"])
        result = index.forward_artifact_impact("artifact_unaffected")
        self.assertEqual(result["affected_artifacts"], [])

    def test_metric_provenance_preserves_both_direct_inputs(self) -> None:
        result = _index().backward_provenance("artifact_metric")
        direct = {
            edge["input_artifact_id"]
            for edge in result["direct_input_edges"]
            if edge["output_artifact_id"] == "artifact_metric"
        }
        self.assertEqual(
            direct,
            {"artifact_detection", "artifact_prediction"},
        )

    def test_missing_subjects_fail_closed(self) -> None:
        index = _index()
        with self.assertRaises(ProvenanceError):
            index.forward_artifact_impact("missing_artifact")
        with self.assertRaises(ProvenanceError):
            index.forward_run_impact("missing_run")
        with self.assertRaises(ProvenanceError):
            index.backward_provenance("missing_artifact")

    def test_unvalidated_and_malformed_graphs_fail_closed(self) -> None:
        registry = _load_registry()
        with self.assertRaises(ProvenanceError):
            ImmutableRegistryIndex(registry)
        broken = copy.deepcopy(registry)
        next(
            artifact
            for artifact in broken["artifacts"]
            if artifact["artifact_id"] == "artifact_model"
        )["direct_input_artifact_ids"] = ["missing_artifact"]
        with self.assertRaises(ProvenanceError):
            _index(broken)
        cyclic = copy.deepcopy(registry)
        raw = next(
            artifact
            for artifact in cyclic["artifacts"]
            if artifact["artifact_id"] == "artifact_raw"
        )
        raw["direct_input_artifact_ids"] = ["artifact_figure"]
        next(
            run
            for run in cyclic["runs"]
            if run["run_id"] == "run_raw"
        )["input_artifact_ids"] = ["artifact_figure"]
        with self.assertRaises(ProvenanceError):
            _index(cyclic)

    def test_queries_are_pure(self) -> None:
        registry = _load_registry()
        original = copy.deepcopy(registry)
        index = _index(registry)
        index.forward_artifact_impact("artifact_raw")
        index.forward_run_impact("run_raw")
        index.backward_provenance("artifact_figure")
        index.supersession_impact("artifact_raw")
        self.assertEqual(registry, original)


if __name__ == "__main__":
    unittest.main()
