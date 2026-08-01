"""Person D support for Person B's ratified signed-explicit-mapping fold contract.

Person B's own real validator module
(``mineocclude.probes.production_fold_contract_v0_1``) lives only on
``role/person-b-analysis`` at commit
``06bd2a17b90d95de37c0739d17d3a624964cc4fa`` and has not been merged
onto this branch. This module is Person D's own, independent
reimplementation of the same frozen validation logic, built by reading
that commit's Git objects directly (never executed, never imported,
never merged). Every frozen constant and check below is copied verbatim
from that exact commit; if Person B's fold contract is ever revised,
these must be re-read from the new authoritative commit, never edited
from local judgment.

## Why the historical reproduction was wrong for this manifest

Person D's pre-existing ``mineocclude.probes.splits.validate_fold_manifest``
recomputes a fold-to-layout assignment from the *admitted* per-layout row
counts and rejects a manifest whose declared assignment disagrees. That
recomputation is only valid when the manifest's assignment was itself
computed from those same (reduced, post-join) counts. Person B's real
production manifest inherits its fold assignment from an *original,
six-layout, pre-join* greedy computation (row counts 507/502/335/524/
418/170, ``assignment_source: "frozen_layout_plan_subset_without_reassignment"``)
and never recomputes it after only five of those six layouts were
admitted with reduced per-frame counts (409/387/335/292/272) -- so
recomputing from the reduced counts alone can never reproduce it. This
module validates the exact *signed* mapping instead of attempting to
regenerate it.

This module never fits a baseline, never computes a metric, and never
reads a U4 artifact. It only validates a fold manifest already claiming
to be this exact production format/contract version.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

from mineocclude.analysis.manifests import (
    AnalysisArtifactError,
    validate_sealed_artifact,
)
from mineocclude.experiments.registry import canonical_json_bytes, formatted_json_bytes


class ProductionFoldContractError(ValueError):
    """Raised when production-fold authority does not match exact frozen bytes."""


#: Person B's fold-contract implementation and ratification commits --
#: the sole authorities for every frozen constant in this module.
PERSON_B_FOLD_CONTRACT_COMMIT = "06bd2a17b90d95de37c0739d17d3a624964cc4fa"
PERSON_B_FOLD_RATIFICATION_COMMIT = "a612ec29108c8f69f19cdc283e40873e75796ea7"

PRODUCTION_FOLD_CONTRACT_VERSION = "person-b-step4-1-production-fold-contract-v0.1"
PRODUCTION_FOLD_MANIFEST_FORMAT_VERSION = "person-b-ten-pilot-frame-fold-v0.1"
PRODUCTION_FOLD_SCHEMA_VERSION = "person-b-fold-v0.1"
PRODUCTION_FOLD_VALIDATION_MODE = "signed_explicit_mapping"

PRODUCING_PERSON_B_COMMIT = "ca3bf19120d5553a34a5edc1bda6bfed54859127"
RATIFYING_PERSON_B_COMMIT = "c9a519b42cf651e05f5b4f640fda6e1a0aed3e7c"
ORIGINAL_LAYOUT_PLAN_COMMIT = "08b9677124f3ed04db49d5e5e720f04771c96b83"

FROZEN_FOLD_MANIFEST_PATH = (
    "docs/status/person_b_phase4_step4_1_production_handoff_v0_1/"
    "ten_pilot_frame_fold_manifest.json"
)
FROZEN_FOLD_MANIFEST_SHA256 = (
    "53ca938c6ae936c3ecb6e6e8d95a3fda152f5fa130b52e7a000d297810738d71"
)
FROZEN_FOLD_MANIFEST_BYTE_SIZE = 742_601
FROZEN_FOLD_ARTIFACT_HASH = (
    "be30c65ed5bb8b4b05d87be21d846b60b918d450976e3901e40a71db481dcf96"
)

FROZEN_TARGET_MANIFEST_PATH = (
    "docs/status/person_b_phase4_step4_1_production_handoff_v0_1/"
    "production_oracle_target_manifest.json"
)
FROZEN_TARGET_MANIFEST_SHA256 = (
    "afcf3afae00db6330665afc5964608c6db89eeac3767c9486d8ba0a218858282"
)
FROZEN_TARGET_MANIFEST_BYTE_SIZE = 4_934_874
FROZEN_TARGET_ARTIFACT_HASH = (
    "c9d2406d3d1b9df336a8a0a6998e45bdc54dd9a68e0d0dde5872a3344fc7338b"
)

FROZEN_CONFIG_HASH = "b2e12e7049e0494c756be442a4f300cbc7dc0a6e262deecf682f1354e887f0ab"
FROZEN_ANALYSIS_CONFIG_VERSION = "person-b-phase1-v0.2"
FROZEN_SEED = 20_260_719
FROZEN_N_SPLITS = 5

FROZEN_LAYOUT_IDS = (
    "layout_00",
    "layout_01",
    "layout_02",
    "layout_03",
    "layout_04",
)
FROZEN_LAYOUT_ROW_COUNTS = {
    "layout_00": 409,
    "layout_01": 387,
    "layout_02": 335,
    "layout_03": 292,
    "layout_04": 272,
}
FROZEN_LAYOUT_FOLDS = {
    "layout_00": 1,
    "layout_01": 2,
    "layout_02": 4,
    "layout_03": 0,
    "layout_04": 3,
}
FROZEN_ACCEPTED_PILOT_IDS = (
    "layout_00_ep9403",
    "layout_00_ep9441",
    "layout_01_ep9405",
    "layout_01_ep9442",
    "layout_02_ep9407",
    "layout_02_ep9432",
    "layout_03_ep9404",
    "layout_03_ep9443",
    "layout_04_ep9406",
    "layout_04_ep9444",
)
FROZEN_SOURCE_FRAME_COUNTS = {
    "layout_00_ep9403": 248,
    "layout_00_ep9441": 200,
    "layout_01_ep9405": 230,
    "layout_01_ep9442": 200,
    "layout_02_ep9407": 158,
    "layout_02_ep9432": 200,
    "layout_03_ep9404": 125,
    "layout_03_ep9443": 200,
    "layout_04_ep9406": 113,
    "layout_04_ep9444": 200,
}

ROW_MAPPING_DIGEST_DOMAIN = "person-b-step4-1-production-fold-row-mapping-v0.1"
FROZEN_ROW_MAPPING_SHA256 = (
    "6bc8ced64ebce10b27a2c9e1dceede31d92bf2013015fb81975e64bdf01ad52c"
)


def _fail(message: str) -> None:
    raise ProductionFoldContractError(message)


def _require_contract_version(contract_version: str) -> None:
    if contract_version != PRODUCTION_FOLD_CONTRACT_VERSION:
        _fail(f"Unknown production fold contract version: {contract_version!r}.")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def row_mapping_sha256(document: Mapping[str, Any]) -> str:
    """Hash the ordered admitted/excluded mapping in an explicit digest domain."""

    projection = {
        "excluded_memberships": document.get("excluded_memberships"),
        "memberships": document.get("memberships"),
    }
    domain = ROW_MAPPING_DIGEST_DOMAIN.encode("utf-8") + b"\0"
    return _sha256(domain + canonical_json_bytes(projection))


def _expected_layout_assignments() -> list[dict[str, Any]]:
    return [
        {"fold_idx": FROZEN_LAYOUT_FOLDS[layout], "layout_id": layout}
        for layout in FROZEN_LAYOUT_IDS
    ]


def _validate_source_manifests(document: Mapping[str, Any]) -> None:
    source_manifests = document.get("source_manifests")
    if not isinstance(source_manifests, list) or [
        row.get("trajectory_id") for row in source_manifests
    ] != list(FROZEN_ACCEPTED_PILOT_IDS):
        _fail("Production source manifests are not the frozen pilot sequence.")
    for row in source_manifests:
        trajectory_id = row.get("trajectory_id")
        expected_layout = str(trajectory_id).split("_ep", 1)[0]
        activation_index = row.get("activation_index")
        if (
            expected_layout not in FROZEN_LAYOUT_FOLDS
            or row.get("layout_id") != expected_layout
            or row.get("fold_idx") != FROZEN_LAYOUT_FOLDS[expected_layout]
            or row.get("chunk_count") != 20
            or row.get("activation_row_count")
            != FROZEN_SOURCE_FRAME_COUNTS[trajectory_id] * 20
            or not isinstance(activation_index, Mapping)
            or not _is_sha256(activation_index.get("sha256"))
            or not isinstance(activation_index.get("byte_size"), int)
            or isinstance(activation_index.get("byte_size"), bool)
            or activation_index["byte_size"] < 1
            or not _is_sha256(row.get("capture_package_sha256"))
            or not isinstance(row.get("capture_package_byte_size"), int)
            or isinstance(row.get("capture_package_byte_size"), bool)
            or row["capture_package_byte_size"] < 1
        ):
            _fail(f"Source-manifest identity is invalid for {trajectory_id!r}.")


def _validate_memberships(document: Mapping[str, Any]) -> None:
    memberships = document.get("memberships")
    exclusions = document.get("excluded_memberships")
    if not isinstance(memberships, list) or not isinstance(exclusions, list):
        _fail("Production membership collections must be arrays.")
    if len(memberships) != 1_695 or len(exclusions) != 179:
        _fail("Production admitted/excluded row counts changed.")

    source_counts = document.get("source_frame_counts")
    expected_source_counts = [
        {
            "source_frame_count": FROZEN_SOURCE_FRAME_COUNTS[trajectory_id],
            "trajectory_id": trajectory_id,
        }
        for trajectory_id in FROZEN_ACCEPTED_PILOT_IDS
    ]
    if source_counts != expected_source_counts:
        _fail("Production source-frame counts changed.")

    admitted_keys: set[tuple[str, int]] = set()
    excluded_keys: set[tuple[str, int]] = set()
    for row in memberships:
        if not isinstance(row, Mapping):
            _fail("Production membership row is not an object.")
        trajectory_id = row.get("trajectory_id")
        frame_idx = row.get("model_frame_idx")
        layout_id = row.get("layout_id")
        key = (trajectory_id, frame_idx)
        if (
            trajectory_id not in FROZEN_SOURCE_FRAME_COUNTS
            or not isinstance(frame_idx, int)
            or isinstance(frame_idx, bool)
            or not 0 <= frame_idx < FROZEN_SOURCE_FRAME_COUNTS[trajectory_id]
            or key in admitted_keys
            or layout_id != trajectory_id.split("_ep", 1)[0]
            or row.get("fold_idx") != FROZEN_LAYOUT_FOLDS[layout_id]
            or row.get("source_frame_id") != f"{trajectory_id}:render_frame:{frame_idx}"
            or row.get("status") != "accepted"
            or row.get("target_availability_status") != "available"
            or row.get("analysis_scopes")
            not in (["hidden_mean", "hidden_spread"], ["visible_no_wall_control"])
        ):
            _fail("Production admitted membership changed or leaks across folds.")
        admitted_keys.add(key)

    for row in exclusions:
        if not isinstance(row, Mapping):
            _fail("Production exclusion row is not an object.")
        trajectory_id = row.get("trajectory_id")
        frame_idx = row.get("model_frame_idx")
        key = (trajectory_id, frame_idx)
        if (
            trajectory_id not in FROZEN_SOURCE_FRAME_COUNTS
            or not isinstance(frame_idx, int)
            or isinstance(frame_idx, bool)
            or not 0 <= frame_idx < FROZEN_SOURCE_FRAME_COUNTS[trajectory_id]
            or key in admitted_keys
            or key in excluded_keys
            or row.get("layout_id") != trajectory_id.split("_ep", 1)[0]
            or row.get("source_frame_id") != f"{trajectory_id}:render_frame:{frame_idx}"
            or row.get("exclusion_reason") != "outside_frozen_condition_selection"
            or row.get("target_availability_status") != "not_admitted"
        ):
            _fail("Production excluded membership changed.")
        excluded_keys.add(key)

    complete_keys = {
        (trajectory_id, frame_idx)
        for trajectory_id, count in FROZEN_SOURCE_FRAME_COUNTS.items()
        for frame_idx in range(count)
    }
    if admitted_keys | excluded_keys != complete_keys:
        _fail("Production admitted/excluded partition is incomplete.")

    def _sort_key(row: Mapping[str, Any]) -> tuple[Any, Any]:
        return (row["trajectory_id"], row["model_frame_idx"])

    if memberships != sorted(memberships, key=_sort_key) or exclusions != sorted(
        exclusions, key=_sort_key
    ):
        _fail("Production row ordering changed.")
    if row_mapping_sha256(document) != FROZEN_ROW_MAPPING_SHA256:
        _fail("Production row-level mapping identity changed.")

    observed_layout_counts = Counter(row["layout_id"] for row in memberships)
    if observed_layout_counts != Counter(FROZEN_LAYOUT_ROW_COUNTS):
        _fail("Production layout row counts changed.")
    observed_layout_folds: dict[str, set[int]] = {}
    for row in memberships:
        observed_layout_folds.setdefault(row["layout_id"], set()).add(row["fold_idx"])
    if observed_layout_folds != {
        layout: {fold_idx} for layout, fold_idx in FROZEN_LAYOUT_FOLDS.items()
    }:
        _fail("Production layout grouping leaks across folds.")
    admitted_by_fold = Counter(row["fold_idx"] for row in memberships)
    admitted_by_pilot = Counter(row["trajectory_id"] for row in memberships)
    excluded_by_pilot = Counter(row["trajectory_id"] for row in exclusions)
    expected_counts = {
        "admitted_by_fold": [
            {"fold_idx": fold_idx, "row_count": admitted_by_fold[fold_idx]}
            for fold_idx in sorted(admitted_by_fold)
        ],
        "admitted_by_layout": [
            {"layout_id": layout_id, "row_count": observed_layout_counts[layout_id]}
            for layout_id in FROZEN_LAYOUT_IDS
        ],
        "admitted_by_pilot": [
            {"row_count": admitted_by_pilot[trajectory_id], "trajectory_id": trajectory_id}
            for trajectory_id in FROZEN_ACCEPTED_PILOT_IDS
        ],
        "excluded_by_pilot": [
            {"row_count": excluded_by_pilot[trajectory_id], "trajectory_id": trajectory_id}
            for trajectory_id in FROZEN_ACCEPTED_PILOT_IDS
        ],
    }
    if document.get("row_counts") != expected_counts:
        _fail("Production fold row-count audit changed or is incomplete.")


def validate_production_fold_document(
    document: Mapping[str, Any],
    *,
    contract_version: str,
) -> None:
    """Validate the exact signed mapping without subset rebalancing.

    Mirrors ``mineocclude.probes.production_fold_contract_v0_1
    .validate_production_fold_document`` at commit 06bd2a1 verbatim.
    ``contract_version`` is the caller's declared intent -- checked
    against the one known contract version, not read from the document
    -- so a caller mistakenly invoking this against an unrelated or
    future contract version fails closed instead of silently validating
    against stale rules.
    """

    _require_contract_version(contract_version)
    if not isinstance(document, Mapping):
        _fail("Production fold document must be an object.")
    try:
        validate_sealed_artifact(document, expected_type="fold_manifest")
    except AnalysisArtifactError as error:
        raise ProductionFoldContractError(
            f"Production fold artifact seal is invalid: {error}"
        ) from error
    expected_fields = {
        "fold_manifest_format_version": PRODUCTION_FOLD_MANIFEST_FORMAT_VERSION,
        "fold_schema_version": PRODUCTION_FOLD_SCHEMA_VERSION,
        "analysis_config_version": FROZEN_ANALYSIS_CONFIG_VERSION,
        "config_hash": FROZEN_CONFIG_HASH,
        "artifact_hash": FROZEN_FOLD_ARTIFACT_HASH,
        "assignment_source": "frozen_layout_plan_subset_without_reassignment",
        "strategy": "layout_grouped",
        "n_splits": FROZEN_N_SPLITS,
        "seed": FROZEN_SEED,
        "random_split_used": False,
        "row_order_has_scientific_meaning": False,
        "synthetic": False,
        "scientific_use": "permitted",
        "u4_output_inspected": False,
        "source_frame_count": 1_874,
        "admitted_frame_count": 1_695,
        "excluded_frame_count": 179,
        "activation_row_count": 37_480,
        "activation_chunk_count": 200,
    }
    for field, expected in expected_fields.items():
        if document.get(field) != expected:
            _fail(f"Production fold field {field!r} changed.")
    if document.get("accepted_pilot_ids") != list(FROZEN_ACCEPTED_PILOT_IDS):
        _fail("Production accepted-pilot binding changed.")
    if document.get("layout_assignments") != _expected_layout_assignments():
        _fail("Production signed explicit layout mapping changed.")
    expected_source_identities = {
        "c_accepted_manifest_sha256": (
            "7a12b8a5c5ce8b81b32bcdb044f72d5c4d9ada41af9a9402d3ac52904e494be2"
        ),
        "combined_activation_index_sha256": (
            "1a25d2186912ba72fdbf123ea9f07b2255bd0e55c6a48a1a50e3b7c0f23eb1e9"
        ),
        "condition_selection_sha256": (
            "b5f0f22978bc62911f284da8b700bd8f166144586d0925bb03f8a730963a50aa"
        ),
        "frozen_layout_plan_sha256": (
            "a762cfe66984675e6af9177ff954540fe17cafc7747422fcad26ed1a2f7bbf8b"
        ),
        "person_a_commit": "55776dc88302b89b52eef483a710fbf6811cf536",
        "person_c_commit": "c6bff25b5ef4f5fdb0e1ef0ce0d22e3f8b5e4960",
    }
    if document.get("source_identities") != expected_source_identities:
        _fail("Production fold no longer binds the frozen prejoin plan.")
    expected_input_inventory = [
        {
            "byte_size": 245_491_346,
            "path": (
                "/home/sagemaker-user/person-a-phase6-approved-outputs/"
                "person-a-phase6-ten-pilot-expansion-seed-20260725/"
                "combined_activation_index.json"
            ),
            "sha256": (
                "1a25d2186912ba72fdbf123ea9f07b2255bd0e55c6a48a1a50e3b7c0f23eb1e9"
            ),
        },
        {
            "byte_size": 656_885,
            "path": "data/person_b/phase6_c_intake/condition_selection_source.json",
            "sha256": (
                "b5f0f22978bc62911f284da8b700bd8f166144586d0925bb03f8a730963a50aa"
            ),
        },
        {
            "byte_size": 6_540,
            "path": "data/person_b/phase6_c_intake/layout_fold_plan.json",
            "sha256": (
                "a762cfe66984675e6af9177ff954540fe17cafc7747422fcad26ed1a2f7bbf8b"
            ),
        },
        {
            "byte_size": 64_556,
            "path": (
                "docs/status/person_c_phase6_ten_pilot_expansion_acceptance_v0_1/"
                "accepted_pilot_manifest.json"
            ),
            "sha256": (
                "7a12b8a5c5ce8b81b32bcdb044f72d5c4d9ada41af9a9402d3ac52904e494be2"
            ),
        },
    ]
    if document.get("input_byte_inventory") != expected_input_inventory:
        _fail("Production fold input-byte inventory changed.")
    _validate_memberships(document)
    _validate_source_manifests(document)


def validate_production_fold_manifest_bytes(
    payload: bytes,
    *,
    contract_version: str,
) -> Mapping[str, Any]:
    """Validate literal manifest bytes, canonical serialization, and semantics."""

    _require_contract_version(contract_version)
    if not isinstance(payload, bytes):
        _fail("Production fold payload must be bytes.")
    if len(payload) != FROZEN_FOLD_MANIFEST_BYTE_SIZE:
        _fail("Production fold literal byte size changed.")
    if _sha256(payload) != FROZEN_FOLD_MANIFEST_SHA256:
        _fail("Production fold literal SHA-256 changed.")
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProductionFoldContractError(
            "Production fold payload is not strict UTF-8 JSON."
        ) from error
    if payload != formatted_json_bytes(document):
        _fail("Production fold bytes are not the frozen formatted JSON encoding.")
    validate_production_fold_document(document, contract_version=contract_version)
    return document


def validate_fold_target_binding_bytes(
    fold_payload: bytes,
    target_payload: bytes,
    *,
    contract_version: str,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Validate exact fold/target bytes and their one-to-one row binding."""

    fold_document = validate_production_fold_manifest_bytes(
        fold_payload, contract_version=contract_version
    )
    if not isinstance(target_payload, bytes):
        _fail("Production target payload must be bytes.")
    if len(target_payload) != FROZEN_TARGET_MANIFEST_BYTE_SIZE:
        _fail("Production target literal byte size changed.")
    if _sha256(target_payload) != FROZEN_TARGET_MANIFEST_SHA256:
        _fail("Production target literal SHA-256 changed.")
    try:
        target_document = json.loads(target_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProductionFoldContractError(
            "Production target payload is not strict UTF-8 JSON."
        ) from error
    if target_payload != formatted_json_bytes(target_document):
        _fail("Production target bytes are not the frozen formatted JSON encoding.")
    if (
        target_document.get("artifact_hash") != FROZEN_TARGET_ARTIFACT_HASH
        or target_document.get("input_manifest_hash") != FROZEN_FOLD_ARTIFACT_HASH
        or target_document.get("row_count") != 1_695
    ):
        _fail("Production target does not bind the frozen fold artifact.")
    target_rows = target_document.get("rows")
    if not isinstance(target_rows, list):
        _fail("Production target rows are absent.")
    fold_keys = [
        (row["trajectory_id"], row["model_frame_idx"])
        for row in fold_document["memberships"]
    ]
    target_keys = [
        (row.get("trajectory_id"), row.get("model_frame_idx"))
        for row in target_rows
        if isinstance(row, Mapping)
    ]
    if len(target_keys) != 1_695 or target_keys != fold_keys:
        _fail("Production target-to-fold row identity binding changed.")
    return fold_document, target_document


__all__ = [
    "FROZEN_FOLD_MANIFEST_PATH",
    "FROZEN_FOLD_MANIFEST_SHA256",
    "FROZEN_TARGET_MANIFEST_PATH",
    "FROZEN_TARGET_MANIFEST_SHA256",
    "PERSON_B_FOLD_CONTRACT_COMMIT",
    "PERSON_B_FOLD_RATIFICATION_COMMIT",
    "PRODUCTION_FOLD_CONTRACT_VERSION",
    "PRODUCTION_FOLD_MANIFEST_FORMAT_VERSION",
    "PRODUCTION_FOLD_VALIDATION_MODE",
    "ProductionFoldContractError",
    "row_mapping_sha256",
    "validate_fold_target_binding_bytes",
    "validate_production_fold_document",
    "validate_production_fold_manifest_bytes",
]
