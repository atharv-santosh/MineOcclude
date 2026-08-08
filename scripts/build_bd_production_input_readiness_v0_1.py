#!/usr/bin/env python3
"""Validate and materialize the final B/D production inputs without fitting.

This consumer is intentionally post-extraction and CPU-only.  It authenticates
the published 66-cell combined Activation Store v2 index with the existing
``activation_v2`` and ``production_v2`` consumers, loads every referenced
chunk, joins Person B's successor scientific universe/targets/folds, validates
Person D's already-complete production baseline package, and publishes only:

* two external NumPy arrays plus an external manifest, and
* one compact Git readiness receipt.

No probe, metric, permutation, split, baseline, or scientific result is fit or
computed here.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

from mineocclude.analysis.production_v2 import (  # noqa: E402
    validate_combined_activation_index_bytes,
)
from mineocclude.contracts.activation_v2 import (  # noqa: E402
    ExternalChunkBinding,
    PERSON_A_ACTIVATION_INDEX_V2_CANONICALIZATION_CONTRACT,
    load_activation_index_v2,
)
from mineocclude.analysis.no_wall_positive_control_66_cell_v0_1 import (  # noqa: E402
    CONTROL_PACKAGE_RELATIVE,
    load_current_positive_control_readiness,
)

SCHEMA_ID = "integration-bd-production-input-readiness-v0.1"
RUN_ID = "mineocclude-run-ea6169430d693f8adcd16a23a62c4422"
EXPECTED_STARTING_HEAD = "13167eb89fe868ac18a251992a72b53b8dcc2d7d"
PERSON_D_AUTHORITY_COMMIT = "fba8ddf96c29e29d88c6a2b190a038507943b8a5"
ACCEPTED_MANIFEST_SHA256 = (
    "96ba43e15bc024aeaef7c519fa4ece0a4afe0bb0e877501dffaca44fee927ff7"
)

ACTIVATION_INDEX_PATH = Path(
    "/mnt/sagemaker-nvme/mineocclude/phase6/"
    f"{RUN_ID}/output/combined_activation_index.json"
)
ACTIVATION_INDEX_SHA256 = (
    "b5f97728bf4bcf957805f2664afbb53481d61db16318159cb0df6d8654c2f571"
)
ACTIVATION_INDEX_BYTE_SIZE = 321_940_278
ACTIVATION_HANDOFF_PATH = (
    ROOT / "docs/status/person_a_66_cell_production_activation_index_v0_1/"
    "production_activation_handoff.json"
)
ACTIVATION_HANDOFF_SHA256 = (
    "ed314fa73d743a124337962491dd42436e5befec8bbfecddb34ad2606ef926c9"
)

B_ORACLE_ROOT = ROOT / "docs/status/person_b_66_cell_oracle_target_v0_1"
B_PREACTIVATION_ROOT = ROOT / "docs/status/person_b_66_cell_preactivation_v0_1"
D_BASELINE_ROOT = ROOT / "docs/status/person_d_66_cell_production_baselines_v0_1"

B_AUTHORITY_IDENTITIES = {
    "row_universe_receipt": (
        B_ORACLE_ROOT / "row_universe_receipt_v0_2.json",
        "e897c31cda46e2dbe7fab605320cd98eba68a1396a80ccd78b178c8dc5547351",
    ),
    "row_universe_records": (
        B_ORACLE_ROOT / "row_universe_records.jsonl",
        "29b4cf003f3d9479b3606f17947879078801b400b09d942bd6827544b95227b2",
    ),
    "oracle_target_manifest": (
        B_ORACLE_ROOT / "oracle_target_manifest.json",
        "c064e1856be67ebab95cbcb07b80009729c396f2398b15b4dec57458b73b8ac9",
    ),
    "oracle_target_records": (
        B_ORACLE_ROOT / "oracle_target_records.jsonl",
        "d95c83518d2ad322e6862f5460727382511fe831c0c6658a6cf72c9f7a8858b1",
    ),
    "fold_manifest": (
        B_PREACTIVATION_ROOT / "fold_manifest.json",
        "86739975882f4926c3398d5bfa21611daf06c579b3893809eb385e8dcd03001d",
    ),
    "fold_leakage_audit": (
        B_PREACTIVATION_ROOT / "fold_leakage_audit.json",
        "5e76eee7dfbe4f9f66405d9d779a6fa4bb252b2adffdd0664869fb7b3bab98f8",
    ),
    "post_activation_preflight": (
        B_PREACTIVATION_ROOT / "post_activation_analysis_preflight.json",
        "7fc217501cb61c34b2e6b700dccfb703dbdaf6c661ae7f3734529c9efc05cd25",
    ),
    "storage_dtype_review": (
        B_PREACTIVATION_ROOT / "storage_dtype_review.json",
        "d63e6e3d936c7b2444bccfdf74000ffe8c0e4eb23d8c5c2349be606a5c50a503",
    ),
    "successor_authority_decision": (
        B_PREACTIVATION_ROOT / "successor_authority_decision.json",
        "d3af0a73b88700521841bb30452b696ccc83e7b4f13927cf4c8da341e1e9405a",
    ),
    "u4_status": (
        B_ORACLE_ROOT / "u4_status.json",
        "a5c0f225cc8ef228e9a0d3053a1fc7c57a25e127b83d004256c115694fed92c9",
    ),
}

D_AUTHORITY_IDENTITIES = {
    "authority_verification_receipt": (
        D_BASELINE_ROOT / "authority_verification_receipt.json",
        "19d48d4530e17ae070d308e9b8734e6a1fec2c5cdb995fc52524ab4ada5a3967",
    ),
    "baseline_metrics": (
        D_BASELINE_ROOT / "baseline_metrics.json",
        "cecaf081e3b320043419106686222c1f9508d13d125ce4055043d1e57e3254f5",
    ),
    "baseline_handoff": (
        D_BASELINE_ROOT / "d_to_b_production_baseline_handoff.json",
        "932a2d35a9739035bcb812eefcc6e2af728252baa0a8f08e9843293e6d1a8684",
    ),
    "execution_universe": (
        D_BASELINE_ROOT / "execution_universe.json",
        "57b8877c9e9288c8dac2202d65cf9fa671de7a14ef54541990c2c79188bfd75e",
    ),
    "prediction_manifest": (
        D_BASELINE_ROOT / "prediction_manifest.json",
        "ffd8f8316f8d3fd74e8ca441dda6f9f45d4d05c7834496abc461a76b97337ea7",
    ),
}

EXPECTED_TRAJECTORY_COUNT = 66
EXPECTED_FRAME_COUNT = 2_468
EXPECTED_TARGET_FRAME_COUNT = 2_108
EXPECTED_ELIGIBLE_FRAME_COUNT = 662
EXPECTED_LAYER_COUNT = 20
EXPECTED_ACTIVATION_ROW_COUNT = 49_360
EXPECTED_ACTIVATION_CHUNK_COUNT = 1_320
EXPECTED_ELIGIBLE_ACTIVATION_ROW_COUNT = 13_240
EXPECTED_FOLD_IDS = frozenset(range(5))
EXPECTED_D_FAMILIES = frozenset(
    {
        "constant_velocity",
        "explicit_feature",
        "grouped_shuffled",
        "known_q_analytic",
        "last_seen",
        "raw_pixel",
        "time_only",
        "visible_history_q",
    }
)

EXTERNAL_ROOT = (
    ACTIVATION_INDEX_PATH.parent / "status/bd_production_input_readiness_v0_1"
)
VECTOR_PATH = EXTERNAL_ROOT / "activation_vectors.npy"
METADATA_PATH = EXTERNAL_ROOT / "sample_metadata.npy"
EXTERNAL_MANIFEST_PATH = EXTERNAL_ROOT / "analysis_ready_manifest.json"
RECEIPT_PATH = (
    ROOT / "docs/status/integration/bd_production_input_readiness_v0_1/"
    "readiness_receipt.json"
)
BUILDER_RELATIVE_PATH = "scripts/build_bd_production_input_readiness_v0_1.py"

SCOPE_BITS = {
    "hidden_mean": 1,
    "hidden_spread": 2,
    "visible_no_wall_control": 4,
}

METADATA_DTYPE = np.dtype(
    [
        ("trajectory_id", "U32"),
        ("global_model_frame_idx", "<i4"),
        ("layer_idx", "<i2"),
        ("mu_oracle_blocks", "<f8"),
        ("log_sigma_oracle", "<f8"),
        ("log_sigma_available", "?"),
        ("sigma_oracle_blocks", "<f8"),
        ("var_oracle_blocks2", "<f8"),
        ("x_true_blocks", "<f8"),
        ("tau_seconds", "<f8"),
        ("last_visible_position_blocks", "<f8"),
        ("elapsed_hidden_frames", "<i4"),
        ("context_fraction", "<f8"),
        ("speed_blocks_per_second", "<f8"),
        ("q_blocks_squared_per_second", "<f8"),
        ("seed", "<i8"),
        ("layout_id", "U16"),
        ("control_type", "U40"),
        ("admission_stratum", "U40"),
        ("fold_idx", "<i2"),
        ("scope_mask", "u1"),
    ]
)


class ReadinessError(RuntimeError):
    """An input or artifact conflicts with a frozen production authority."""


def _fail(message: str) -> None:
    raise ReadinessError(message)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_bytes(document: Any) -> bytes:
    return (
        json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _strict_json_bytes(payload: bytes, *, label: str) -> Mapping[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail(f"{label} repeats JSON key {key!r}")
            result[key] = value
        return result

    try:
        document = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda value: _fail(
                f"{label} contains non-finite constant {value!r}"
            ),
        )
    except ReadinessError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail(f"{label} is not strict UTF-8 JSON: {error}")
    if not isinstance(document, Mapping):
        _fail(f"{label} root must be an object")
    return document


def _jsonl_rows(payload: bytes, *, label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(payload.splitlines(), start=1):
        if not line.strip():
            continue
        document = _strict_json_bytes(line, label=f"{label} line {line_number}")
        rows.append(dict(document))
    return rows


def _read_exact(path: Path, expected_sha256: str) -> bytes:
    if not path.is_file() or path.is_symlink():
        _fail(f"authority is absent or not a regular file: {path}")
    payload = path.read_bytes()
    actual = _sha256_bytes(payload)
    if actual != expected_sha256:
        _fail(f"authority SHA-256 differs at {path}: {actual}")
    return payload


def _identity(path: Path, expected_sha256: str | None = None) -> dict[str, Any]:
    sha256 = _sha256_file(path)
    if expected_sha256 is not None and sha256 != expected_sha256:
        _fail(f"published file SHA-256 differs at {path}")
    try:
        rendered_path = str(path.relative_to(ROOT))
    except ValueError:
        rendered_path = str(path)
    return {
        "byte_size": path.stat().st_size,
        "path": rendered_path,
        "sha256": sha256,
    }


def _run_git(*arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _builder_code_identity() -> dict[str, Any]:
    commit = _run_git("log", "-1", "--format=%H", "--", BUILDER_RELATIVE_PATH)
    if len(commit) != 40:
        _fail("readiness builder must be committed before publication")
    source = (ROOT / BUILDER_RELATIVE_PATH).read_bytes()
    committed = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{commit}:{BUILDER_RELATIVE_PATH}"],
        check=True,
        capture_output=True,
    ).stdout
    if source != committed:
        _fail("working readiness builder differs from its producing commit")
    return {
        "git_commit": commit,
        "path": BUILDER_RELATIVE_PATH,
        "sha256": _sha256_bytes(source),
    }


def _publish_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not path.is_file() or path.is_symlink() or path.read_bytes() != payload:
            _fail(f"immutable publication conflicts at {path}")
        return
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o644)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _publish_temp_file(temp_path: Path, final_path: Path) -> dict[str, Any]:
    final_path.parent.mkdir(parents=True, exist_ok=True)
    temp_identity = _identity(temp_path)
    if final_path.exists():
        final_identity = _identity(final_path)
        if (
            temp_identity["sha256"] != final_identity["sha256"]
            or temp_identity["byte_size"] != final_identity["byte_size"]
        ):
            temp_path.unlink(missing_ok=True)
            _fail(f"immutable external publication conflicts at {final_path}")
        temp_path.unlink()
        return final_identity
    os.replace(temp_path, final_path)
    return _identity(final_path)


def _load_json_authorities(
    identities: Mapping[str, tuple[Path, str]],
) -> tuple[dict[str, Mapping[str, Any]], dict[str, dict[str, Any]]]:
    documents: dict[str, Mapping[str, Any]] = {}
    inventory: dict[str, dict[str, Any]] = {}
    for name, (path, sha256) in identities.items():
        payload = _read_exact(path, sha256)
        if path.suffix == ".json":
            documents[name] = _strict_json_bytes(payload, label=name)
        inventory[name] = {
            "byte_size": len(payload),
            "path": str(path.relative_to(ROOT)),
            "sha256": sha256,
        }
    return documents, inventory


def load_b_authorities() -> dict[str, Any]:
    documents, inventory = _load_json_authorities(B_AUTHORITY_IDENTITIES)
    row_payload = _read_exact(*B_AUTHORITY_IDENTITIES["row_universe_records"])
    target_payload = _read_exact(*B_AUTHORITY_IDENTITIES["oracle_target_records"])
    rows = _jsonl_rows(row_payload, label="B row universe")
    targets = _jsonl_rows(target_payload, label="B oracle targets")
    row_receipt = documents["row_universe_receipt"]
    oracle_manifest = documents["oracle_target_manifest"]
    fold_manifest = documents["fold_manifest"]
    if (
        len(rows) != EXPECTED_FRAME_COUNT
        or row_receipt.get("total_model_frame_key_count") != EXPECTED_FRAME_COUNT
        or row_receipt.get("admitted_analysis_row_count")
        != EXPECTED_ELIGIBLE_FRAME_COUNT
        or row_receipt.get("target_bearing_key_count") != EXPECTED_TARGET_FRAME_COUNT
        or len(targets) != EXPECTED_TARGET_FRAME_COUNT
        or oracle_manifest.get("oracle_target_row_count") != EXPECTED_TARGET_FRAME_COUNT
        or fold_manifest.get("model_frame_key_count") != EXPECTED_FRAME_COUNT
    ):
        _fail("Person B authority cardinality differs from the successor package")
    if (
        documents["successor_authority_decision"].get("decision")
        != "PRODUCTION_MVP_UNIVERSE_BOUND_TO_66_CELL_AUTHORITIES"
        or documents["storage_dtype_review"].get("review_complete") is not True
        or documents["storage_dtype_review"].get("chosen_stored_activation_dtype")
        != "float32"
    ):
        _fail("Person B successor or dtype decision is not current")
    return {
        "documents": documents,
        "fold_manifest": fold_manifest,
        "inventory": inventory,
        "rows": rows,
        "targets": targets,
    }


def validate_fold_integrity(
    row_by_key: Mapping[tuple[str, int], Mapping[str, Any]],
    fold_manifest: Mapping[str, Any],
    leakage_audit: Mapping[str, Any],
) -> dict[str, Any]:
    memberships = fold_manifest.get("memberships")
    if not isinstance(memberships, list):
        _fail("B fold manifest memberships are absent")
    fold_by_key: dict[tuple[str, int], int] = {}
    trajectory_folds: dict[str, set[int]] = defaultdict(set)
    layout_folds: dict[str, set[int]] = defaultdict(set)
    for membership in memberships:
        if not isinstance(membership, Mapping):
            _fail("B fold membership is malformed")
        key = (
            str(membership.get("trajectory_id")),
            int(membership.get("model_frame_idx", -1)),
        )
        fold_idx = membership.get("fold_idx")
        if (
            key in fold_by_key
            or not isinstance(fold_idx, int)
            or isinstance(fold_idx, bool)
            or fold_idx not in EXPECTED_FOLD_IDS
        ):
            _fail("B fold membership is duplicate or has an unexpected fold")
        fold_by_key[key] = fold_idx
        trajectory_folds[key[0]].add(fold_idx)
        layout_folds[str(membership.get("layout_id"))].add(fold_idx)
    if set(fold_by_key) != set(row_by_key):
        _fail("B fold manifest does not cover the exact row universe")
    if any(len(values) != 1 for values in trajectory_folds.values()) or any(
        len(values) != 1 for values in layout_folds.values()
    ):
        _fail("a grouped trajectory/layout crosses frozen folds")
    missing_eligible = 0
    row_fold_mismatches = 0
    for key, row in row_by_key.items():
        if row.get("fold_idx") != fold_by_key[key]:
            row_fold_mismatches += 1
        if row.get("status") == "accepted" and key not in fold_by_key:
            missing_eligible += 1
    if (
        row_fold_mismatches
        or missing_eligible
        or set(fold_by_key.values()) != EXPECTED_FOLD_IDS
        or leakage_audit.get("leakage_audit_pass") is not True
        or leakage_audit.get("leaking_trajectory_ids") != []
        or leakage_audit.get("leaking_layout_ids") != []
        or set(leakage_audit.get("populated_fold_indices", ())) != EXPECTED_FOLD_IDS
    ):
        _fail("frozen fold integrity audit failed")
    return {
        "fold_count": len(EXPECTED_FOLD_IDS),
        "fold_ids": sorted(EXPECTED_FOLD_IDS),
        "grouping_unit": ["layout_id", "trajectory_id"],
        "leakage_audit_pass": True,
        "missing_eligible_assignment_count": missing_eligible,
        "new_random_split_generated": False,
        "row_fold_mismatch_count": row_fold_mismatches,
        "trajectory_cross_fold_count": 0,
    }


def build_b_join_audit(
    combined_document: Mapping[str, Any], b: Mapping[str, Any]
) -> dict[str, Any]:
    activation_rows = combined_document.get("index_rows")
    if not isinstance(activation_rows, list):
        _fail("combined activation index lacks rows")
    activation_counter: Counter[tuple[str, int, int]] = Counter()
    activation_frame_keys: set[tuple[str, int]] = set()
    for row in activation_rows:
        key = (
            str(row.get("trajectory_id")),
            int(row.get("global_model_frame_idx", -1)),
            int(row.get("layer_idx", -1)),
        )
        activation_counter[key] += 1
        activation_frame_keys.add(key[:2])
    row_by_key: dict[tuple[str, int], Mapping[str, Any]] = {}
    for row in b["rows"]:
        key = (str(row["trajectory_id"]), int(row["model_frame_idx"]))
        if key in row_by_key:
            _fail("B row universe repeats a frame key")
        row_by_key[key] = row
    target_by_key: dict[tuple[str, int], Mapping[str, Any]] = {}
    for target in b["targets"]:
        key = (str(target["trajectory_id"]), int(target["model_frame_idx"]))
        if key in target_by_key:
            _fail("B oracle target repeats a frame key")
        target_by_key[key] = target
    if (
        len(activation_frame_keys) != EXPECTED_FRAME_COUNT
        or set(row_by_key) != activation_frame_keys
        or len(target_by_key) != EXPECTED_TARGET_FRAME_COUNT
    ):
        _fail("activation/B row/target frame authorities do not reconcile")
    declared_target_keys = {
        key
        for key, row in row_by_key.items()
        if row.get("oracle_target_present") is True
    }
    if declared_target_keys != set(target_by_key):
        _fail("B target-bearing declaration differs from oracle records")
    eligible_by_key = {
        key: row for key, row in row_by_key.items() if row.get("status") == "accepted"
    }
    if len(eligible_by_key) != EXPECTED_ELIGIBLE_FRAME_COUNT:
        _fail("B successor eligible row count differs")
    expected_eligible_keys = {
        (trajectory_id, frame_idx, layer_idx)
        for trajectory_id, frame_idx in eligible_by_key
        for layer_idx in range(EXPECTED_LAYER_COUNT)
    }
    duplicate_count = sum(
        count - 1 for key, count in activation_counter.items() if count > 1
    )
    missing = expected_eligible_keys - set(activation_counter)
    unauthorized = {
        key for key in expected_eligible_keys if key[:2] not in eligible_by_key
    }
    if duplicate_count or missing or unauthorized:
        _fail("eligible B activation join is duplicate, missing, or unauthorized")
    if any(key not in target_by_key for key in eligible_by_key):
        _fail("an eligible B row lacks an oracle target")

    by_scope = Counter()
    by_control_type = Counter()
    by_stratum = Counter()
    by_fold = Counter()
    by_layout = Counter()
    for row in eligible_by_key.values():
        for scope in row.get("analysis_scopes", ()):
            by_scope[str(scope)] += 1
        by_control_type[str(row["control_type"])] += 1
        by_stratum[str(row["admission_stratum"])] += 1
        by_fold[int(row["fold_idx"])] += 1
        by_layout[str(row["layout_id"])] += 1
        target = target_by_key[(row["trajectory_id"], row["model_frame_idx"])]
        if not isinstance(target.get("mu_oracle_blocks"), (int, float)):
            _fail("eligible B row lacks its U1 location target")
        if "hidden_spread" in row.get("analysis_scopes", ()) and not isinstance(
            target.get("log_sigma_oracle"), (int, float)
        ):
            _fail("eligible hidden-spread row lacks its U2 target")
    exclusions = Counter(
        str(row.get("exclusion_reason"))
        for row in row_by_key.values()
        if row.get("status") == "excluded"
    )
    quarantines = Counter(
        str(row.get("quarantine_category"))
        for row in row_by_key.values()
        if row.get("quarantined") is True
    )
    eligible_quarantined_count = sum(
        row.get("status") == "accepted" and row.get("quarantined") is True
        for row in row_by_key.values()
    )
    if sum(exclusions.values()) != EXPECTED_FRAME_COUNT - EXPECTED_ELIGIBLE_FRAME_COUNT:
        _fail("B exclusion accounting does not close")
    if sum(quarantines.values()) != 744 or eligible_quarantined_count != 0:
        _fail("B quarantine accounting does not match the frozen authority")
    return {
        "activation_frame_count": len(activation_frame_keys),
        "activation_row_count": len(activation_rows),
        "analysis_eligible_activation_row_count": len(expected_eligible_keys),
        "analysis_eligible_frame_count": len(eligible_by_key),
        "eligible_by_control_type": dict(sorted(by_control_type.items())),
        "eligible_by_fold": {str(k): by_fold[k] for k in sorted(by_fold)},
        "eligible_by_layout": dict(sorted(by_layout.items())),
        "eligible_by_scope": dict(sorted(by_scope.items())),
        "eligible_by_stratum": dict(sorted(by_stratum.items())),
        "eligible_quarantined_frame_count": eligible_quarantined_count,
        "excluded_by_reason": dict(sorted(exclusions.items())),
        "join_duplicate_count": duplicate_count,
        "join_missing_activation_count": len(missing),
        "join_unauthorized_source_count": len(unauthorized),
        "row_by_key": row_by_key,
        "target_bearing_frame_count": len(target_by_key),
        "target_by_key": target_by_key,
        "row_universe_frame_count": len(row_by_key),
        "quarantined_by_category": dict(sorted(quarantines.items())),
        "quarantined_frame_count": sum(quarantines.values()),
    }


def validate_d_baselines(
    b_join: Mapping[str, Any], fold_integrity: Mapping[str, Any]
) -> dict[str, Any]:
    documents, inventory = _load_json_authorities(D_AUTHORITY_IDENTITIES)
    verification = documents["authority_verification_receipt"]
    universe = documents["execution_universe"]
    handoff = documents["baseline_handoff"]
    predictions = documents["prediction_manifest"]
    metrics = documents["baseline_metrics"]
    if (
        _run_git(
            "log", "-1", "--format=%H", "--", str(D_BASELINE_ROOT.relative_to(ROOT))
        )
        != PERSON_D_AUTHORITY_COMMIT
    ):
        _fail("current Person D package is not the declared authority commit")
    try:
        _run_git("merge-base", "--is-ancestor", PERSON_D_AUTHORITY_COMMIT, "HEAD")
    except subprocess.CalledProcessError:
        _fail("Person D authority commit is not in integration ancestry")
    if (
        verification.get("all_verified") is not True
        or verification.get("fold_manifest_agreement") is not True
        or verification.get("person_b_accounting_reconciled") is not True
        or universe.get("reconciles_to_person_b") is not True
        or universe.get("reconciliation_mismatch_count") != 0
        or universe.get("total_model_frame_key_count") != EXPECTED_FRAME_COUNT
        or universe.get("admitted_row_count") != EXPECTED_ELIGIBLE_FRAME_COUNT
        or universe.get("excluded_row_count")
        != EXPECTED_FRAME_COUNT - EXPECTED_ELIGIBLE_FRAME_COUNT
        or universe.get("counts_by_fold") != b_join["eligible_by_fold"]
        or handoff.get("consumable_without_further_person_d_implementation") is not True
        or set(handoff.get("families_executed", ())) != EXPECTED_D_FAMILIES
        or handoff.get("families_not_executed") != {}
    ):
        _fail("Person D production universe or handoff differs from Person B")
    input_authorities = handoff.get("input_authorities", {})
    if (
        input_authorities.get("person_b_fold_manifest_sha256")
        != B_AUTHORITY_IDENTITIES["fold_manifest"][1]
        or input_authorities.get("person_b_oracle_target_manifest_sha256")
        != B_AUTHORITY_IDENTITIES["oracle_target_manifest"][1]
        or input_authorities.get("person_b_oracle_target_records_sha256")
        != B_AUTHORITY_IDENTITIES["oracle_target_records"][1]
        or input_authorities.get("person_b_row_universe_receipt_sha256")
        != B_AUTHORITY_IDENTITIES["row_universe_receipt"][1]
        or input_authorities.get("person_b_row_universe_records_sha256")
        != B_AUTHORITY_IDENTITIES["row_universe_records"][1]
    ):
        _fail("Person D baseline package binds stale B authorities")
    source_identities = metrics.get("source_identities", {})
    if (
        source_identities.get("person_b_fold_manifest_sha256")
        != B_AUTHORITY_IDENTITIES["fold_manifest"][1]
        or source_identities.get("person_b_oracle_target_manifest_sha256")
        != B_AUTHORITY_IDENTITIES["oracle_target_manifest"][1]
        or source_identities.get("person_b_row_universe_receipt_sha256")
        != B_AUTHORITY_IDENTITIES["row_universe_receipt"][1]
    ):
        _fail("Person D metric package binds stale B authorities")
    records = predictions.get("records")
    family_status = predictions.get("family_status")
    if not isinstance(records, list) or not isinstance(family_status, Mapping):
        _fail("Person D prediction package is malformed")
    eligible_keys = set(b_join["row_by_key"])
    eligible_keys = {
        key
        for key in eligible_keys
        if b_join["row_by_key"][key].get("status") == "accepted"
    }
    expected_prediction_keys = {
        (family, target, trajectory_id, frame_idx)
        for family in EXPECTED_D_FAMILIES
        for target in ("mu_oracle_blocks", "log_sigma_oracle")
        for trajectory_id, frame_idx in eligible_keys
    }
    observed_prediction_keys: set[tuple[str, str, str, int]] = set()
    fold_mismatch = 0
    for record in records:
        key = (
            str(record.get("baseline_family")),
            str(record.get("target_name")),
            str(record.get("trajectory_id")),
            int(record.get("model_frame_idx", -1)),
        )
        if key in observed_prediction_keys:
            _fail("Person D prediction package repeats a family/target/frame key")
        observed_prediction_keys.add(key)
        row = b_join["row_by_key"].get(key[2:])
        if row is None or row.get("status") != "accepted":
            _fail("Person D prediction enters from outside B's eligible universe")
        if record.get("fold_idx") != row.get("fold_idx"):
            fold_mismatch += 1
    if (
        observed_prediction_keys != expected_prediction_keys
        or predictions.get("prediction_row_count") != len(expected_prediction_keys)
        or fold_mismatch
        or set(family_status) != EXPECTED_D_FAMILIES
        or any(value.get("status") != "completed" for value in family_status.values())
        or fold_integrity.get("leakage_audit_pass") is not True
    ):
        _fail("Person D prediction/fold coverage differs from B's universe")

    no_wall_keys = {
        key
        for key in eligible_keys
        if b_join["row_by_key"][key].get("control_type") == "no_wall_visible_control"
    }
    if len(no_wall_keys) != b_join["eligible_by_scope"]["visible_no_wall_control"]:
        _fail("Person D no-wall control coverage differs from B")
    positive_control = load_current_positive_control_readiness(
        ROOT / CONTROL_PACKAGE_RELATIVE / "positive_control_receipt.json"
    )
    statuses = {
        "constant_velocity": "READY_EXISTING",
        "explicit_features": "READY_EXISTING",
        "grouped_shuffled": "READY_EXISTING",
        "known_q": "READY_EXISTING",
        "last_seen": "READY_EXISTING",
        "no_wall_positive_control": (
            "STATISTICAL_GATE_PASS"
            if positive_control.statistical_gate_pass
            else (
                "STATISTICAL_GATE_FAIL"
                if positive_control.artifact_present
                else "MISSING_CURRENT_RECEIPT"
            )
        ),
        "occluder_only_negative_control": "NOT_APPLICABLE",
        "raw_pixel": "READY_EXISTING",
        "time_only": "READY_EXISTING",
        "visible_history_uncertainty": "READY_EXISTING",
    }
    return {
        "authority_commit": PERSON_D_AUTHORITY_COMMIT,
        "comparator_status": statuses,
        "fold_mismatch_count": fold_mismatch,
        "inventory": inventory,
        "no_wall_control_frame_count": len(no_wall_keys),
        "no_wall_positive_control_artifact_present": (
            positive_control.artifact_present
        ),
        "no_wall_positive_control_statistical_gate_pass": (
            positive_control.statistical_gate_pass
        ),
        "no_wall_control_status_basis": positive_control.reason,
        "occluder_only_status_basis": (
            "B's frozen authority excludes 360 no-object frames as not oracle "
            "eligible; D must not reinstate them"
        ),
        "prediction_row_count": len(records),
        "required_comparators_ready": (
            positive_control.statistical_gate_pass
            and all(
                value in {"READY_EXISTING", "NOT_APPLICABLE"}
                for name, value in statuses.items()
                if name != "no_wall_positive_control"
            )
        ),
    }


def _metadata_value(
    row: Mapping[str, Any], target: Mapping[str, Any], layer_idx: int
) -> tuple[Any, ...]:
    scopes = tuple(str(value) for value in row.get("analysis_scopes", ()))
    unknown_scopes = set(scopes) - set(SCOPE_BITS)
    if unknown_scopes:
        _fail(f"B row uses unknown analysis scopes: {sorted(unknown_scopes)}")
    scope_mask = sum(SCOPE_BITS[scope] for scope in scopes)
    log_sigma = target.get("log_sigma_oracle")
    log_sigma_available = isinstance(log_sigma, (int, float)) and not isinstance(
        log_sigma, bool
    )
    return (
        str(row["trajectory_id"]),
        int(row["model_frame_idx"]),
        layer_idx,
        float(target["mu_oracle_blocks"]),
        float(log_sigma) if log_sigma_available else float("nan"),
        log_sigma_available,
        float(target["sigma_oracle_blocks"]),
        float(target["var_oracle_blocks2"]),
        float(target["x_true_blocks"]),
        float(target["tau"]),
        float(target["last_visible_position_blocks"]),
        int(row["hidden_frames"]),
        float(row["context_fraction"]),
        float(row["speed_blocks_per_second"]),
        float(row["q_blocks_squared_per_second"]),
        int(row["seed"]),
        str(row["layout_id"]),
        str(row["control_type"]),
        str(row["admission_stratum"]),
        int(row["fold_idx"]),
        scope_mask,
    )


def materialize_analysis_ready_inputs(
    combined_document: Mapping[str, Any],
    inventories: Mapping[str, Mapping[str, Any]],
    b_join: Mapping[str, Any],
    code_identity: Mapping[str, Any],
) -> dict[str, Any]:
    ordered_ids = tuple(combined_document["ordered_pilot_ids"])
    combined_rows = combined_document["index_rows"]
    eligible_by_trajectory: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for key, row in b_join["row_by_key"].items():
        if row.get("status") == "accepted":
            eligible_by_trajectory[key[0]].append(row)
    for rows in eligible_by_trajectory.values():
        rows.sort(key=lambda row: int(row["model_frame_idx"]))

    EXTERNAL_ROOT.mkdir(parents=True, exist_ok=True)
    vector_fd, vector_name = tempfile.mkstemp(
        prefix="activation-vectors-", suffix=".npy", dir=EXTERNAL_ROOT
    )
    metadata_fd, metadata_name = tempfile.mkstemp(
        prefix="sample-metadata-", suffix=".npy", dir=EXTERNAL_ROOT
    )
    os.close(vector_fd)
    os.close(metadata_fd)
    vector_temp = Path(vector_name)
    metadata_temp = Path(metadata_name)
    try:
        vectors = np.lib.format.open_memmap(
            vector_temp,
            mode="w+",
            dtype=np.float32,
            shape=(EXPECTED_ELIGIBLE_ACTIVATION_ROW_COUNT, 2048),
        )
        metadata = np.lib.format.open_memmap(
            metadata_temp,
            mode="w+",
            dtype=METADATA_DTYPE,
            shape=(EXPECTED_ELIGIBLE_ACTIVATION_ROW_COUNT,),
        )
        output_offset = 0
        combined_offset = 0
        loaded_chunk_count = 0
        for position, trajectory_id in enumerate(ordered_ids, start=1):
            inventory = inventories[trajectory_id]
            index_identity = inventory["activation_index"]
            chunk_bindings = {
                str(chunk["chunk_id"]): ExternalChunkBinding(
                    chunk_id=str(chunk["chunk_id"]),
                    path=Path(str(chunk["path"])),
                    sha256=str(chunk["sha256"]),
                    byte_size=int(chunk["byte_size"]),
                    row_count=int(chunk["row_count"]),
                )
                for chunk in inventory["chunks"]
            }
            loaded = load_activation_index_v2(
                Path(str(index_identity["path"])),
                canonicalization_contract=(
                    PERSON_A_ACTIVATION_INDEX_V2_CANONICALIZATION_CONTRACT
                ),
                expected_index_sha256=str(index_identity["sha256"]),
                expected_index_byte_size=int(index_identity["byte_size"]),
                expected_trajectory_id=trajectory_id,
                expected_manifest_sha256=ACCEPTED_MANIFEST_SHA256,
                chunk_bindings=chunk_bindings,
                retain_vectors=True,
            )
            row_count = int(inventory["activation_row_count"])
            combined_slice = combined_rows[
                combined_offset : combined_offset + row_count
            ]
            if combined_slice != [dict(row) for row in loaded.rows]:
                _fail(f"{trajectory_id}: combined rows differ from authenticated index")
            combined_offset += row_count
            loaded_chunk_count += len(loaded.chunks)
            loaded_by_key: dict[tuple[int, int], Mapping[str, Any]] = {}
            for activation_row in loaded.rows:
                key = (
                    int(activation_row["global_model_frame_idx"]),
                    int(activation_row["layer_idx"]),
                )
                if key in loaded_by_key:
                    _fail(f"{trajectory_id}: loaded activation key repeats")
                loaded_by_key[key] = activation_row
            for b_row in eligible_by_trajectory.get(trajectory_id, ()):
                frame_idx = int(b_row["model_frame_idx"])
                target = b_join["target_by_key"][(trajectory_id, frame_idx)]
                for layer_idx in range(EXPECTED_LAYER_COUNT):
                    activation_row = loaded_by_key.get((frame_idx, layer_idx))
                    if activation_row is None:
                        _fail(f"{trajectory_id}:{frame_idx}:{layer_idx} is absent")
                    array = loaded.arrays_by_chunk_id[
                        str(activation_row["activation_chunk_id"])
                    ]
                    vector = array[int(activation_row["chunk_row_idx"])]
                    if vector.shape != (2048,) or not bool(np.isfinite(vector).all()):
                        _fail("eligible activation vector is malformed or non-finite")
                    vectors[output_offset] = vector
                    metadata[output_offset] = _metadata_value(b_row, target, layer_idx)
                    output_offset += 1
            del loaded
            print(
                f"loaded {position:02d}/{len(ordered_ids):02d} {trajectory_id}",
                file=sys.stderr,
                flush=True,
            )
        if (
            combined_offset != EXPECTED_ACTIVATION_ROW_COUNT
            or loaded_chunk_count != EXPECTED_ACTIVATION_CHUNK_COUNT
            or output_offset != EXPECTED_ELIGIBLE_ACTIVATION_ROW_COUNT
        ):
            _fail("authenticated load/materialization cardinality does not close")
        vectors.flush()
        metadata.flush()
        del vectors
        del metadata
        vector_identity = _publish_temp_file(vector_temp, VECTOR_PATH)
        metadata_identity = _publish_temp_file(metadata_temp, METADATA_PATH)
    except BaseException:
        vector_temp.unlink(missing_ok=True)
        metadata_temp.unlink(missing_ok=True)
        raise

    manifest = {
        "activation_vectors": {
            **vector_identity,
            "dtype": "float32",
            "shape": [EXPECTED_ELIGIBLE_ACTIVATION_ROW_COUNT, 2048],
        },
        "authorities": {
            "activation_index_sha256": ACTIVATION_INDEX_SHA256,
            "person_b_fold_manifest_sha256": B_AUTHORITY_IDENTITIES["fold_manifest"][1],
            "person_b_oracle_target_records_sha256": B_AUTHORITY_IDENTITIES[
                "oracle_target_records"
            ][1],
            "person_b_row_universe_records_sha256": B_AUTHORITY_IDENTITIES[
                "row_universe_records"
            ][1],
        },
        "builder_code_identity": dict(code_identity),
        "eligible_frame_count": EXPECTED_ELIGIBLE_FRAME_COUNT,
        "eligible_frame_layer_row_count": EXPECTED_ELIGIBLE_ACTIVATION_ROW_COUNT,
        "join_key": [
            "trajectory_id",
            "global_model_frame_idx",
            "layer_idx",
        ],
        "metadata": {
            **metadata_identity,
            "dtype_descr": METADATA_DTYPE.descr,
            "log_sigma_null_representation": (
                "NaN only when log_sigma_available is false; eligible hidden_spread "
                "rows always carry finite log_sigma_oracle"
            ),
            "scope_bits": SCOPE_BITS,
            "shape": [EXPECTED_ELIGIBLE_ACTIVATION_ROW_COUNT],
        },
        "row_order": "trajectory_id,global_model_frame_idx,layer_idx",
        "run_id": RUN_ID,
        "schema_id": f"{SCHEMA_ID}-external-analysis-ready-inputs",
        "schema_version": "1.0",
        "scientific_fitting_executed": False,
    }
    _publish_bytes(EXTERNAL_MANIFEST_PATH, _json_bytes(manifest))
    return {
        "manifest": _identity(EXTERNAL_MANIFEST_PATH),
        "metadata": metadata_identity,
        "vectors": vector_identity,
    }


def load_and_validate_activations() -> (
    tuple[Mapping[str, Any], dict[str, Mapping[str, Any]], dict[str, Any]]
):
    handoff_bytes = _read_exact(ACTIVATION_HANDOFF_PATH, ACTIVATION_HANDOFF_SHA256)
    handoff = _strict_json_bytes(handoff_bytes, label="Person A activation handoff")
    activation = handoff.get("activation_index")
    if (
        not isinstance(activation, Mapping)
        or activation.get("path") != str(ACTIVATION_INDEX_PATH)
        or activation.get("sha256") != ACTIVATION_INDEX_SHA256
        or activation.get("byte_size") != ACTIVATION_INDEX_BYTE_SIZE
        or handoff.get("run_id") != RUN_ID
        or handoff.get("status") != "READY_FOR_B_D_INPUT_LOADING_NOT_SCIENTIFIC_FITTING"
    ):
        _fail("Person A handoff does not authorize this exact production index")
    index_bytes = _read_exact(ACTIVATION_INDEX_PATH, ACTIVATION_INDEX_SHA256)
    if len(index_bytes) != ACTIVATION_INDEX_BYTE_SIZE:
        _fail("combined activation index byte size differs")
    preliminary = _strict_json_bytes(index_bytes, label="combined activation index")
    ordered_ids = tuple(preliminary.get("ordered_pilot_ids", ()))
    no_wall_ids = tuple(preliminary.get("no_wall_control_pilot_ids", ()))
    if len(ordered_ids) != EXPECTED_TRAJECTORY_COUNT:
        _fail("combined activation index does not contain 66 trajectories")
    inventory_refs = handoff.get("per_trajectory_inventories")
    if not isinstance(inventory_refs, list) or len(inventory_refs) != len(ordered_ids):
        _fail("Person A handoff lacks per-trajectory inventories")
    inventories: dict[str, Mapping[str, Any]] = {}
    inventory_identities: dict[str, dict[str, Any]] = {}
    for reference in inventory_refs:
        trajectory_id = str(reference["trajectory_id"])
        path = Path(str(reference["path"]))
        payload = _read_exact(path, str(reference["sha256"]))
        if len(payload) != reference["byte_size"]:
            _fail(f"{trajectory_id}: inventory byte size differs")
        inventory = _strict_json_bytes(payload, label=f"{trajectory_id} inventory")
        if inventory.get("trajectory_id") != trajectory_id:
            _fail(f"{trajectory_id}: inventory crosses trajectory identity")
        inventories[trajectory_id] = inventory
        inventory_identities[trajectory_id] = {
            "byte_size": len(payload),
            "path": str(path),
            "sha256": str(reference["sha256"]),
        }
    accepted = {
        trajectory_id: ACCEPTED_MANIFEST_SHA256 for trajectory_id in ordered_ids
    }
    combined = validate_combined_activation_index_bytes(
        index_bytes,
        expected_sha256=ACTIVATION_INDEX_SHA256,
        expected_byte_size=ACTIVATION_INDEX_BYTE_SIZE,
        per_pilot_inventories=inventories,
        accepted_manifest_by_trajectory=accepted,
        expected_pilot_ids=ordered_ids,
        expected_no_wall_ids=no_wall_ids,
        expected_row_count=EXPECTED_ACTIVATION_ROW_COUNT,
    )
    provenance = combined.get("production_provenance", {})
    if (
        provenance.get("run_id") != RUN_ID
        or provenance.get("trajectory_count") != EXPECTED_TRAJECTORY_COUNT
        or provenance.get("global_model_frame_key_count") != EXPECTED_FRAME_COUNT
        or provenance.get("activation_chunk_count") != EXPECTED_ACTIVATION_CHUNK_COUNT
        or provenance.get("stored_dtype") != "float32"
        or provenance.get("layer_indices") != list(range(EXPECTED_LAYER_COUNT))
    ):
        _fail("combined activation production provenance differs")
    return (
        combined,
        inventories,
        {
            "handoff": _identity(ACTIVATION_HANDOFF_PATH, ACTIVATION_HANDOFF_SHA256),
            "index": _identity(ACTIVATION_INDEX_PATH, ACTIVATION_INDEX_SHA256),
            "per_trajectory_inventories": inventory_identities,
        },
    )


def build_receipt() -> dict[str, Any]:
    if _run_git("rev-parse", "--abbrev-ref", "HEAD") != "integration/mvp-final":
        _fail("execution branch differs from integration/mvp-final")
    if (
        not _run_git("merge-base", "--is-ancestor", EXPECTED_STARTING_HEAD, "HEAD")
        == ""
    ):
        _fail("required starting HEAD is not in branch ancestry")
    code_identity = _builder_code_identity()
    combined, inventories, activation_identities = load_and_validate_activations()
    b = load_b_authorities()
    b_join = build_b_join_audit(combined, b)
    fold_integrity = validate_fold_integrity(
        b_join["row_by_key"],
        b["fold_manifest"],
        b["documents"]["fold_leakage_audit"],
    )
    d = validate_d_baselines(b_join, fold_integrity)
    analysis_ready = materialize_analysis_ready_inputs(
        combined, inventories, b_join, code_identity
    )
    scope_counts = b_join["eligible_by_scope"]
    u1_ready = (
        scope_counts.get("hidden_mean") == 311 and fold_integrity["leakage_audit_pass"]
    )
    u2_ready = (
        scope_counts.get("hidden_spread") == 311
        and fold_integrity["leakage_audit_pass"]
    )
    u4_status = b["documents"]["u4_status"]
    u3_ready = bool(
        u4_status.get("VALID_TERMINAL_REVEAL_COUNT", 0) > 0
        and u4_status.get("CURRENT_66_CELL_U4_REVEAL_ELIGIBLE") is True
    )
    receipt = {
        "activation_validation": {
            "activation_chunk_count": EXPECTED_ACTIVATION_CHUNK_COUNT,
            "activation_frame_count": b_join["activation_frame_count"],
            "activation_index_load_pass": True,
            "activation_layer_count": EXPECTED_LAYER_COUNT,
            "activation_row_count": b_join["activation_row_count"],
            "activation_trajectory_count": EXPECTED_TRAJECTORY_COUNT,
            "all_chunk_files_exist": True,
            "all_chunk_hashes_verified": True,
            "stored_dtype": "float32",
        },
        "analysis_ready_inputs": analysis_ready,
        "authorities": {
            "person_a": activation_identities,
            "person_b": b["inventory"],
            "person_d": d["inventory"],
        },
        "builder_code_identity": code_identity,
        "fold_integrity": fold_integrity,
        "join_audit": {
            key: value
            for key, value in b_join.items()
            if key not in {"row_by_key", "target_by_key"}
        },
        "person_d_compatibility": {
            key: value for key, value in d.items() if key != "inventory"
        },
        "readiness_decision": {
            "are_required_d_comparators_ready": d["required_comparators_ready"],
            "can_real_u1_fitting_begin": u1_ready,
            "can_real_u2_fitting_begin": u2_ready,
            "can_real_u3_analysis_begin": u3_ready,
            "blockers": (
                []
                if u3_ready
                else [
                    {
                        "blocked_scope": "U3_REVEAL_SNAPBACK",
                        "code": "NO_VALID_TERMINAL_REVEAL_EVENTS",
                        "detail": (
                            "The frozen 66-cell authority declares "
                            "VALID_TERMINAL_REVEAL_COUNT=0; supplemental capture "
                            "requires a later run identity."
                        ),
                    }
                ]
            ),
        },
        "run_id": RUN_ID,
        "schema_id": SCHEMA_ID,
        "schema_version": "1.0",
        "scientific_execution": {
            "baseline_recomputed": False,
            "final_u1_u2_u3_results_computed": False,
            "layer_selected": False,
            "permutation_executed": False,
            "probe_fitted": False,
            "scientific_claim_made": False,
        },
    }
    _publish_bytes(RECEIPT_PATH, _json_bytes(receipt))
    return receipt


def main() -> int:
    receipt = build_receipt()
    print(
        json.dumps(
            {
                "analysis_ready_manifest": receipt["analysis_ready_inputs"]["manifest"],
                "readiness": receipt["readiness_decision"],
                "receipt": _identity(RECEIPT_PATH),
            },
            sort_keys=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
