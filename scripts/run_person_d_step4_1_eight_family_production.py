"""Frozen, fail-closed Person D Step 4.1 eight-family production runner.

Not executed as part of preparing or repairing it -- it targets a
SageMaker environment with Person A's real preprocessed frames and
Person B's real production fold/oracle manifests mounted locally, none
of which exist on this machine.

## What this binds

- Person D's own exporter implementation commit
  (``PERSON_D_EXPORTER_IMPLEMENTATION_COMMIT``) -- the commit whose
  ``baseline_family_input_v0_2``/``eight_family_execution_manifest``/
  ``frame_handoff_v0_2``/``eight_family_runner`` modules this script
  actually calls, never the historical branch-starting authority;
- the authorized exact runner commit this script itself must equal at
  execution time (``AUTHORIZATION_RECORD_PATH``, populated by the
  companion "runner-preparation" evidence commit once this script's
  own commit hash is known -- see "Branch and commit authorization"
  below for why this cannot be self-referential inside one commit);
- Person B's v0.2 contract and schema-correction commits;
- Person A's frame-handoff commit and frame-manifest identity;
- the exact ordered eight-family set;
- approved input/output roots, environment, and seed requirements;
- per-family runner and environment receipts;
- canonical manifests and SHA-256 inventories.

## Branch and commit authorization

A script cannot embed its own future commit hash. Instead,
``AUTHORIZATION_RECORD_PATH`` names a small JSON file
(``{"authorized_runner_commit": "<hash>"}``) that is committed
*separately*, after this script's own commit hash is known, and cites
it. At real execution time this script requires: the current branch is
exactly ``role/person-d-baselines`` (never a detached HEAD or any
other branch); the worktree is clean; the exporter implementation
commit is an ancestor of HEAD; and HEAD equals exactly the hash
recorded in that authorization file. Before the authorization file is
committed, ``load_authorized_runner_commit`` returns ``None`` and the
check fails closed (``no_authorized_runner_commit_recorded``) rather
than silently permitting any HEAD. Whoever actually deploys a real run
must refresh the authorization record to the exact commit being
deployed immediately beforehand -- this is deliberate operational
discipline against silent drift, not an oversight.

## Restart / resume

Every family's completed, verified output is recorded in
``run_state.json`` under the approved output root. A family is only
skipped when its recorded output file both still exists on disk and
still independently re-validates against
:func:`mineocclude.baselines.baseline_family_input_v0_2
.validate_baseline_document_v0_2` -- :func:`determine_family_execution_plan`
implements this and is exercised directly in
``tests/baselines/test_baseline_family_production_cli.py`` without
ever invoking ``run`` mode for real.

## Fail-closed per family

If any family's fit/export/validation step fails, this script stops
immediately (nonzero exit) without deleting or altering any earlier
family's already-verified, on-disk output.

## No U4 access

This script never imports, reads, or references any U4-owned module,
path, or artifact.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.analysis.config import hash_core_analysis_config
from mineocclude.baselines.baseline_family_input_v0_2 import (
    FROZEN_BASELINE_FAMILY_IDS,
    FROZEN_DIRECT_INPUTS,
    PERSON_B_V0_2_CONTRACT_COMMIT,
    PERSON_B_V0_2_PRODUCTION_RATIFICATION_COMMIT,
    PERSON_E_V0_2_STEP4_1_HANDOFF_COMMIT,
    validate_baseline_document_v0_2,
)
from mineocclude.baselines.eight_family_execution_manifest import (
    FROZEN_SOURCE_CONTEXTS,
    build_eight_family_execution_manifest,
    validate_eight_family_execution_manifest,
)
from mineocclude.baselines.eight_family_runner import (
    EightFamilyRunnerError,
    fit_and_export_family,
)
from mineocclude.baselines.export import BaselineExportError, validate_b_fold_manifest
from mineocclude.baselines.frame_handoff_v0_2 import (
    PERSON_A_EXTERNAL_FRAME_ROOT,
    PERSON_A_FRAME_HANDOFF_COMMIT,
    PERSON_A_FRAME_MANIFEST_PATH,
    PERSON_A_FRAME_MANIFEST_SHA256,
    build_frame_manifest_direct_input_reference,
    verify_frame_manifest_raw_bytes,
    verify_frame_manifest_records,
    verify_frame_manifest_summary_counts,
    verify_frame_payloads_on_disk,
)
from mineocclude.baselines.production_fold_contract_v0_1 import (
    PERSON_B_FOLD_CONTRACT_COMMIT,
    PERSON_B_FOLD_RATIFICATION_COMMIT,
    PRODUCTION_FOLD_CONTRACT_VERSION,
    PRODUCTION_FOLD_MANIFEST_FORMAT_VERSION,
)
from mineocclude.baselines.production_input_ingest import (
    PERSON_C_EXPANSION_ACCEPTANCE_COMMIT,
    ProductionInputIngestError,
    build_all_trajectory_contexts,
    build_fit_manifest_hash,
    build_input_manifest_hash,
    build_oracle_target_lookups,
    build_pixel_features_by_key,
    load_and_verify_json_artifact,
    materialize_git_committed_artifact,
    verify_oracle_target_manifest_structure,
)

#: Person D's actual exporter implementation commit this runner calls
#: into. Never the historical branch-starting authority
#: (853e0acadf050a0b1f318b399b524e57379d03bf) -- that commit predates
#: baseline_family_input_v0_2.py/eight_family_execution_manifest.py/
#: frame_handoff_v0_2.py entirely and cannot be what this script runs.
PERSON_D_EXPORTER_IMPLEMENTATION_COMMIT = "fd9302e5d218193211f2f96986ca32dc1a365e66"

#: Person B's schema-correction commit (fixed the 62-character
#: truncated fold_manifest_hash const this preparation already flagged
#: and worked around independently).
PERSON_B_V0_2_SCHEMA_CORRECTION_COMMIT = "4e0e0f49d4642cf069de8c66c3a8fee47806c4b0"

AUTHORIZED_BRANCH = "role/person-d-baselines"

#: Populated by the companion runner-preparation evidence commit with
#: this script's own commit hash, once known. See module docstring.
AUTHORIZATION_RECORD_PATH = (
    ROOT
    / "docs"
    / "status"
    / "person_d_phase4_step4_1_eight_family_production_v0_2"
    / "authorized_runner_commit.json"
)

#: Approved SageMaker input root for Person A's preprocessed frames.
APPROVED_PERSON_A_FRAME_ROOT = PERSON_A_EXTERNAL_FRAME_ROOT

#: Approved output root for this runner's own produced artifacts.
DEFAULT_APPROVED_OUTPUT_ROOT = (
    "/home/sagemaker-user/person-d-step4-1-approved-outputs/"
    "person-d-step4-1-production-v0-1"
)

#: Approved root this runner's own ``materialize`` mode writes committed
#: cross-role Git artifacts into (fold manifest, oracle target manifest,
#: source-context manifest, Person A's frame manifest, and the ten real
#: capture packages) -- never a substitute for the source branches
#: themselves, only a local, byte-verified copy for ``run`` mode to read.
DEFAULT_MATERIALIZED_INPUT_ROOT = (
    "/home/sagemaker-user/person-d-step4-1-approved-outputs/"
    "person-d-step4-1-materialized-inputs-v0-1"
)

#: Filenames this script's own ``materialize`` mode writes the fold/
#: oracle-target/source-context manifests under, inside whatever
#: ``--materialize-root`` is given. The ten real capture packages are
#: written at their own frozen ``FROZEN_SOURCE_CONTEXTS`` relative paths
#: instead, so ``--source-context-root`` can point at the same root.
MATERIALIZED_FOLD_MANIFEST_FILENAME = "ten_pilot_frame_fold_manifest.json"
MATERIALIZED_ORACLE_TARGET_FILENAME = "production_oracle_target_manifest.json"
MATERIALIZED_SOURCE_CONTEXT_MANIFEST_FILENAME = "source_context_manifest.json"
MATERIALIZED_FRAME_MANIFEST_FILENAME = "preprocessed_frame_manifest.json"

#: The real, independently-verified byte size of Person A's committed
#: frame manifest at ``PERSON_A_FRAME_HANDOFF_COMMIT``/
#: ``PERSON_A_FRAME_MANIFEST_PATH`` (``git show <commit>:<path> | wc -c``).
#: Not frozen alongside ``PERSON_A_FRAME_MANIFEST_SHA256`` in
#: frame_handoff_v0_2.py, so it is bound here for materialization only.
PERSON_A_FRAME_MANIFEST_BYTE_SIZE = 6460547

REQUIRED_ENVIRONMENT = {
    "device": "cpu",
    "python_requires": ">=3.10",
    "seed_source": "configs/analysis/core.yaml",
}

RUN_STATE_FILENAME = "run_state.json"


class ProductionRunnerError(ValueError):
    """Raised when a preflight, authorization, or per-family check fails."""


# --------------------------------------------------------------------------
# Branch / commit authorization (defects 2 and 3)
# --------------------------------------------------------------------------


def resolve_git_facts(repo_root: Path) -> dict:
    """Gather the real git facts this script's authorization check needs.

    The only impure half of the authorization check -- kept separate
    from :func:`verify_branch_and_authorization` so that function stays
    a pure, directly testable check over plain values.
    """

    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo_root, capture_output=True, text=True, check=True,
    ).stdout.strip()
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root, capture_output=True, text=True, check=True,
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root, capture_output=True, text=True, check=True,
        ).stdout.strip()
    )
    ancestor_check = subprocess.run(
        [
            "git", "merge-base", "--is-ancestor",
            PERSON_D_EXPORTER_IMPLEMENTATION_COMMIT, "HEAD",
        ],
        cwd=repo_root, capture_output=True, text=True, check=False,
    )
    return {
        "branch": branch,
        "head": head,
        "worktree_dirty": dirty,
        "exporter_commit_is_ancestor": ancestor_check.returncode == 0,
    }


def load_authorized_runner_commit(path: Path) -> str | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    value = data.get("authorized_runner_commit")
    return value if isinstance(value, str) and value else None


def verify_branch_and_authorization(
    *,
    branch: str,
    head: str,
    worktree_dirty: bool,
    exporter_commit_is_ancestor: bool,
    authorized_runner_commit: str | None,
) -> tuple[str, ...]:
    """Pure fail-closed check: is this exact execution context authorized.

    Never trusts a branch name alone, a clean-looking worktree alone,
    or an ancestor relationship alone -- every one of the four facts
    must hold simultaneously.
    """

    errors: list[str] = []
    if branch != AUTHORIZED_BRANCH:
        errors.append(f"wrong_branch:{branch!r}")
    if worktree_dirty:
        errors.append("dirty_worktree")
    if not exporter_commit_is_ancestor:
        errors.append("exporter_commit_not_ancestor")
    if authorized_runner_commit is None:
        errors.append("no_authorized_runner_commit_recorded")
    elif head != authorized_runner_commit:
        errors.append(
            f"head_not_authorized:head={head!r}:authorized={authorized_runner_commit!r}"
        )
    return tuple(errors)


# --------------------------------------------------------------------------
# Resume planning (unchanged in spirit, still pure and testable)
# --------------------------------------------------------------------------


def load_run_state(output_root: Path) -> dict:
    path = output_root / RUN_STATE_FILENAME
    if not path.exists():
        return {"schema_version": "1.0", "families": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_run_state(output_root: Path, state: Mapping[str, Any]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    path = output_root / RUN_STATE_FILENAME
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def determine_family_execution_plan(
    existing_state: Mapping[str, Any],
    *,
    output_root: Path,
    load_document: Callable[[Path], Any] | None = None,
) -> dict:
    """Pure resume-planning function: which families to skip vs. (re)run.

    A family is skipped only when all of the following hold:
    (1) ``existing_state`` records it as ``"status": "completed"``;
    (2) its recorded output file still exists on disk;
    (3) re-loading and re-validating that file against
    :func:`validate_baseline_document_v0_2` still returns no errors.
    """

    if load_document is None:
        def load_document(path: Path):
            return json.loads(path.read_text(encoding="utf-8"))

    families_state = existing_state.get("families", {})
    plan: dict[str, str] = {}
    for family_id in FROZEN_BASELINE_FAMILY_IDS:
        record = families_state.get(family_id)
        if not isinstance(record, Mapping) or record.get("status") != "completed":
            plan[family_id] = "must_run"
            continue
        output_path = record.get("output_path")
        if not isinstance(output_path, str):
            plan[family_id] = "must_run"
            continue
        full_path = output_root / output_path
        if not full_path.exists():
            plan[family_id] = "must_run"
            continue
        try:
            document = load_document(full_path)
        except (OSError, ValueError):
            plan[family_id] = "must_run"
            continue
        if validate_baseline_document_v0_2(document) != ():
            plan[family_id] = "must_run"
            continue
        plan[family_id] = "skip_already_verified"
    return plan


# --------------------------------------------------------------------------
# Preflight (defects 4 and 5 repaired here)
# --------------------------------------------------------------------------


def run_preflight(
    *,
    frame_manifest_path: Path,
    frame_root: Path | None = None,
    verify_payloads: bool = False,
    fold_manifest_path: Path | None = None,
) -> dict:
    """Verify every frozen input identity before any family is fit.

    Verifies the frame manifest's raw bytes (defect 4) before trusting
    anything parsed from it, then its declared summary counts and
    per-record structural fields, and -- when ``verify_payloads`` is
    true and ``frame_root`` is supplied -- every one of the 1,695
    external frame payloads on disk (defect 5). Never fits a baseline,
    computes a metric, or reads a U4 artifact.

    When ``fold_manifest_path`` is supplied, its raw bytes are verified
    against the frozen fold-manifest identity and its contents are
    dispatch-validated through :func:`mineocclude.baselines.export
    .validate_b_fold_manifest` -- the exact same version-aware check
    ``attach_b_fold_assignments`` performs during a real run, called
    here too so the producing path can never bypass it: this function
    is the one preflight shared by both the ``preflight`` and ``run``
    CLI modes.
    """

    raw_errors = verify_frame_manifest_raw_bytes(frame_manifest_path)
    if raw_errors:
        raise ProductionRunnerError(f"frame manifest raw-byte checks failed: {raw_errors}")

    frame_manifest_byte_size = frame_manifest_path.stat().st_size
    manifest = json.loads(frame_manifest_path.read_text(encoding="utf-8"))

    summary_errors = verify_frame_manifest_summary_counts(manifest)
    if summary_errors:
        raise ProductionRunnerError(
            f"frame manifest summary checks failed: {summary_errors}"
        )
    record_errors = verify_frame_manifest_records(manifest)
    if record_errors:
        raise ProductionRunnerError(
            f"frame manifest record checks failed: {record_errors[:10]}"
            + (" ... (truncated)" if len(record_errors) > 10 else "")
        )

    payload_result = None
    if verify_payloads:
        if frame_root is None:
            raise ProductionRunnerError(
                "verify_payloads=True requires frame_root"
            )
        payload_result = verify_frame_payloads_on_disk(manifest, frame_root=frame_root)
        if not payload_result.all_clear:
            raise ProductionRunnerError(
                "frame payload verification failed: "
                f"missing={payload_result.missing_frame_count} "
                f"duplicate={payload_result.duplicate_frame_count} "
                f"size_mismatch={payload_result.size_mismatch_count} "
                f"hash_mismatch={payload_result.hash_mismatch_count} "
                f"identity_mismatch={payload_result.identity_mismatch_count} "
                f"preprocessing_mismatch={payload_result.preprocessing_mismatch_count} "
                f"errors={payload_result.errors[:10]}"
            )

    frame_reference = build_frame_manifest_direct_input_reference(
        byte_size=frame_manifest_byte_size
    )
    execution_manifest = build_eight_family_execution_manifest(
        preprocessed_frame_manifest_reference=frame_reference
    )
    manifest_errors = validate_eight_family_execution_manifest(execution_manifest)
    if manifest_errors:
        raise ProductionRunnerError(
            f"eight-family execution manifest failed validation: {manifest_errors}"
        )

    fold_manifest_verified = False
    if fold_manifest_path is not None:
        try:
            fold_manifest_document = load_and_verify_json_artifact(
                fold_manifest_path,
                expected_sha256=FROZEN_DIRECT_INPUTS["fold_manifest"]["sha256"],
                expected_byte_size=FROZEN_DIRECT_INPUTS["fold_manifest"]["byte_size"],
            )
        except ProductionInputIngestError as error:
            raise ProductionRunnerError(
                f"fold manifest raw-byte checks failed: {error}"
            ) from error
        try:
            validate_b_fold_manifest(fold_manifest_document)
        except BaselineExportError as error:
            raise ProductionRunnerError(f"fold manifest failed validation: {error}") from error
        fold_manifest_verified = True

    return {
        "status": "PREFLIGHT_PASSED",
        "person_a_frame_handoff_commit": PERSON_A_FRAME_HANDOFF_COMMIT,
        "person_b_v0_2_contract_commit": PERSON_B_V0_2_CONTRACT_COMMIT,
        "person_b_v0_2_production_ratification_commit": (
            PERSON_B_V0_2_PRODUCTION_RATIFICATION_COMMIT
        ),
        "person_b_v0_2_schema_correction_commit": PERSON_B_V0_2_SCHEMA_CORRECTION_COMMIT,
        "person_b_fold_contract_commit": PERSON_B_FOLD_CONTRACT_COMMIT,
        "person_b_fold_ratification_commit": PERSON_B_FOLD_RATIFICATION_COMMIT,
        "fold_contract_version": PRODUCTION_FOLD_CONTRACT_VERSION,
        "fold_manifest_verified": fold_manifest_verified,
        "person_e_v0_2_step4_1_handoff_commit": PERSON_E_V0_2_STEP4_1_HANDOFF_COMMIT,
        "person_d_exporter_implementation_commit": PERSON_D_EXPORTER_IMPLEMENTATION_COMMIT,
        "eight_family_execution_manifest": execution_manifest,
        "frame_manifest": manifest,
        "frame_payload_verification_performed": verify_payloads,
        "baseline_execution_performed": False,
        "u4_output_inspected": False,
    }


# --------------------------------------------------------------------------
# Materialize mode: byte-verified local copies of committed cross-role inputs
# --------------------------------------------------------------------------


def run_materialize(*, repo_root: Path, materialize_root: Path) -> dict:
    """Materialize every committed cross-role artifact this runner needs.

    Each artifact is read via a plain ``git show <commit>:<path>`` object
    read -- never a checkout or merge of another role's branch -- and
    verified byte-for-byte against its frozen identity before being
    written into ``materialize_root``. Fails closed (raises
    :class:`ProductionInputIngestError`) on any read failure or hash/size
    mismatch; never fits a baseline or computes a metric.

    The ten real capture packages are read from Person C's branch at
    ``PERSON_C_EXPANSION_ACCEPTANCE_COMMIT`` -- the exact commit Person
    B's own ``source_context_manifest.json`` already cites as
    ``person_c_expansion_acceptance`` -- not from Person B's own branch,
    whose copy at the same nominal path does not match the frozen
    ``FROZEN_SOURCE_CONTEXTS`` identity (verified directly; see this
    script's module docstring and ``production_input_ingest.py``).
    """

    materialized: dict[str, str] = {}

    fold_reference = FROZEN_DIRECT_INPUTS["fold_manifest"]
    materialize_git_committed_artifact(
        repo_root=repo_root,
        commit=PERSON_B_V0_2_PRODUCTION_RATIFICATION_COMMIT,
        repo_relative_path=fold_reference["path"],
        output_path=materialize_root / MATERIALIZED_FOLD_MANIFEST_FILENAME,
        expected_sha256=fold_reference["sha256"],
        expected_byte_size=fold_reference["byte_size"],
    )
    materialized["fold_manifest"] = str(materialize_root / MATERIALIZED_FOLD_MANIFEST_FILENAME)

    oracle_reference = FROZEN_DIRECT_INPUTS["oracle_target"]
    materialize_git_committed_artifact(
        repo_root=repo_root,
        commit=PERSON_B_V0_2_PRODUCTION_RATIFICATION_COMMIT,
        repo_relative_path=oracle_reference["path"],
        output_path=materialize_root / MATERIALIZED_ORACLE_TARGET_FILENAME,
        expected_sha256=oracle_reference["sha256"],
        expected_byte_size=oracle_reference["byte_size"],
    )
    materialized["oracle_target"] = str(materialize_root / MATERIALIZED_ORACLE_TARGET_FILENAME)

    source_context_reference = FROZEN_DIRECT_INPUTS["source_context_manifest"]
    materialize_git_committed_artifact(
        repo_root=repo_root,
        commit=PERSON_B_V0_2_CONTRACT_COMMIT,
        repo_relative_path=source_context_reference["path"],
        output_path=materialize_root / MATERIALIZED_SOURCE_CONTEXT_MANIFEST_FILENAME,
        expected_sha256=source_context_reference["sha256"],
        expected_byte_size=source_context_reference["byte_size"],
    )
    materialized["source_context_manifest"] = str(
        materialize_root / MATERIALIZED_SOURCE_CONTEXT_MANIFEST_FILENAME
    )

    materialize_git_committed_artifact(
        repo_root=repo_root,
        commit=PERSON_A_FRAME_HANDOFF_COMMIT,
        repo_relative_path=PERSON_A_FRAME_MANIFEST_PATH,
        output_path=materialize_root / MATERIALIZED_FRAME_MANIFEST_FILENAME,
        expected_sha256=PERSON_A_FRAME_MANIFEST_SHA256,
        expected_byte_size=PERSON_A_FRAME_MANIFEST_BYTE_SIZE,
    )
    materialized["frame_manifest"] = str(materialize_root / MATERIALIZED_FRAME_MANIFEST_FILENAME)

    for source_context in FROZEN_SOURCE_CONTEXTS:
        capture_reference = source_context["capture_package"]
        output_path = materialize_root / capture_reference["path"]
        materialize_git_committed_artifact(
            repo_root=repo_root,
            commit=PERSON_C_EXPANSION_ACCEPTANCE_COMMIT,
            repo_relative_path=capture_reference["path"],
            output_path=output_path,
            expected_sha256=capture_reference["sha256"],
            expected_byte_size=capture_reference["byte_size"],
        )
        materialized[f"capture_package:{source_context['trajectory_id']}"] = str(output_path)

    return {
        "status": "MATERIALIZE_PASSED",
        "materialize_root": str(materialize_root),
        "materialized_artifacts": materialized,
        "person_b_v0_2_production_ratification_commit": (
            PERSON_B_V0_2_PRODUCTION_RATIFICATION_COMMIT
        ),
        "person_b_v0_2_contract_commit": PERSON_B_V0_2_CONTRACT_COMMIT,
        "person_a_frame_handoff_commit": PERSON_A_FRAME_HANDOFF_COMMIT,
        "person_c_expansion_acceptance_commit": PERSON_C_EXPANSION_ACCEPTANCE_COMMIT,
        "baseline_execution_performed": False,
        "u4_output_inspected": False,
    }


# --------------------------------------------------------------------------
# Real input assembly for run mode
# --------------------------------------------------------------------------


def build_real_run_inputs(
    *,
    fold_manifest_path: Path,
    target_manifest_path: Path,
    source_context_manifest_path: Path,
    source_context_root: Path,
    analysis_config_path: Path,
    frame_manifest: Mapping[str, Any],
    frame_root: Path,
    execution_manifest: Mapping[str, Any],
) -> dict:
    """Load, verify, and join every real input ``run_production`` needs.

    Every artifact is byte-verified against its frozen identity before
    being trusted, exactly matching the discipline the frame manifest
    already applies. Never fits a baseline or computes a metric -- this
    only assembles ``run_production``'s input arguments.
    """

    config_hash = hash_core_analysis_config(analysis_config_path)
    if config_hash != FROZEN_DIRECT_INPUTS["analysis_config"]["sha256"]:
        raise ProductionRunnerError(
            f"analysis config hash mismatch: expected="
            f"{FROZEN_DIRECT_INPUTS['analysis_config']['sha256']} actual={config_hash}"
        )

    fold_manifest = load_and_verify_json_artifact(
        fold_manifest_path,
        expected_sha256=FROZEN_DIRECT_INPUTS["fold_manifest"]["sha256"],
        expected_byte_size=FROZEN_DIRECT_INPUTS["fold_manifest"]["byte_size"],
    )
    # Explicit binding, ahead of build_all_trajectory_contexts's own
    # (also-enforced) dispatch: the real production fold manifest must
    # declare exactly this contract's format version, not merely
    # whatever export.validate_b_fold_manifest happens to accept. Fails
    # closed before any family executes if it is absent or wrong.
    if fold_manifest.get("fold_manifest_format_version") != PRODUCTION_FOLD_MANIFEST_FORMAT_VERSION:
        raise ProductionRunnerError(
            "fold manifest does not declare the required production fold "
            f"contract format version {PRODUCTION_FOLD_MANIFEST_FORMAT_VERSION!r}: "
            f"got {fold_manifest.get('fold_manifest_format_version')!r}"
        )
    try:
        validate_b_fold_manifest(fold_manifest)
    except BaselineExportError as error:
        raise ProductionRunnerError(f"fold manifest failed validation: {error}") from error

    oracle_target_document = load_and_verify_json_artifact(
        target_manifest_path,
        expected_sha256=FROZEN_DIRECT_INPUTS["oracle_target"]["sha256"],
        expected_byte_size=FROZEN_DIRECT_INPUTS["oracle_target"]["byte_size"],
    )
    oracle_errors = verify_oracle_target_manifest_structure(oracle_target_document)
    if oracle_errors:
        raise ProductionRunnerError(f"oracle target manifest failed validation: {oracle_errors}")

    # Bound the manifest to D's own frozen contract, not merely loaded --
    # confirms this real file agrees with source_context_manifest.json's
    # own committed identity before it is used to join capture packages.
    load_and_verify_json_artifact(
        source_context_manifest_path,
        expected_sha256=FROZEN_DIRECT_INPUTS["source_context_manifest"]["sha256"],
        expected_byte_size=FROZEN_DIRECT_INPUTS["source_context_manifest"]["byte_size"],
    )

    try:
        contexts, visible_positions_by_trajectory = build_all_trajectory_contexts(
            source_context_root=source_context_root,
            oracle_target_document=oracle_target_document,
            fold_manifest=fold_manifest,
            config_hash=config_hash,
        )
    except ProductionInputIngestError as error:
        raise ProductionRunnerError(f"trajectory context assembly failed: {error}") from error

    mu_oracle_by_key, log_sigma_oracle_by_key = build_oracle_target_lookups(oracle_target_document)
    pixel_features_by_key = build_pixel_features_by_key(
        frame_manifest=frame_manifest, frame_root=frame_root
    )
    frame_reference = execution_manifest["direct_inputs"]["preprocessed_frame_manifest"]

    return {
        "contexts": contexts,
        "mu_oracle_by_key": mu_oracle_by_key,
        "log_sigma_oracle_by_key": log_sigma_oracle_by_key,
        "visible_positions_by_trajectory": visible_positions_by_trajectory,
        "pixel_features_by_key": pixel_features_by_key,
        "config_hash": config_hash,
        "input_manifest_hash": build_input_manifest_hash(execution_manifest),
        "fit_manifest_hash": build_fit_manifest_hash(execution_manifest),
        "preprocessed_frame_manifest_reference": frame_reference,
    }


# --------------------------------------------------------------------------
# Production run mode (defect 1 repaired here)
# --------------------------------------------------------------------------


def run_production(
    *,
    contexts,
    mu_oracle_by_key,
    log_sigma_oracle_by_key,
    visible_positions_by_trajectory,
    pixel_features_by_key,
    config_hash: str,
    input_manifest_hash: str,
    fit_manifest_hash: str,
    preprocessed_frame_manifest_reference: Mapping[str, object],
    output_root: Path,
    force_rerun: bool = False,
) -> dict:
    """Fit, validate, and persist every family not already verified.

    Fails closed per family: on any family's failure, this stops
    immediately and raises, leaving every earlier family's persisted,
    already-verified output untouched. ``force_rerun`` is the explicit,
    caller-authorized override for "resume behavior" (``--resume force``
    on the CLI): when true, every family is (re)fit regardless of any
    already-recorded ``run_state.json`` entry, but an already-completed
    *other* family's on-disk output is still never touched unless that
    family itself is refit.
    """

    existing_state = load_run_state(output_root)
    plan_source: Mapping[str, Any] = {} if force_rerun else existing_state
    plan = determine_family_execution_plan(plan_source, output_root=output_root)
    state = {"schema_version": "1.0", "families": dict(existing_state.get("families", {}))}

    for family_id in FROZEN_BASELINE_FAMILY_IDS:
        if plan[family_id] == "skip_already_verified":
            continue
        try:
            documents = fit_and_export_family(
                family_id,
                contexts,
                mu_oracle_by_key=mu_oracle_by_key,
                log_sigma_oracle_by_key=log_sigma_oracle_by_key,
                visible_positions_by_trajectory=visible_positions_by_trajectory,
                pixel_features_by_key=pixel_features_by_key,
                config_hash=config_hash,
                input_manifest_hash=input_manifest_hash,
                fit_manifest_hash=fit_manifest_hash,
                preprocessed_frame_manifest_reference=(
                    preprocessed_frame_manifest_reference if family_id == "raw_pixel" else None
                ),
            )
        except EightFamilyRunnerError as error:
            state["families"][family_id] = {"status": "failed", "error": str(error)}
            save_run_state(output_root, state)
            raise ProductionRunnerError(f"{family_id}: fit/export failed: {error}") from error

        for target_name, document in documents.items():
            errors = validate_baseline_document_v0_2(document)
            if errors:
                state["families"][family_id] = {
                    "status": "failed",
                    "error": f"{target_name}: {errors}",
                }
                save_run_state(output_root, state)
                raise ProductionRunnerError(
                    f"{family_id}/{target_name}: exported document failed validation: {errors}"
                )
            output_path = output_root / f"{family_id}__{target_name}.json"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )

        state["families"][family_id] = {
            "status": "completed",
            "output_path": f"{family_id}__{min(documents)}.json",
            "targets": sorted(documents),
        }
        save_run_state(output_root, state)

    return state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=("preflight", "materialize", "run"),
        help=(
            "preflight: verify all frozen inputs and the eight-family "
            "execution manifest without fitting anything. materialize: "
            "byte-verify and locally copy every committed cross-role "
            "input (fold/oracle-target/source-context manifests, Person "
            "A's frame manifest, and the ten real capture packages) from "
            "their authoritative branches. run: fit and export each "
            "family in order, resuming any already-verified family "
            "output."
        ),
    )
    parser.add_argument(
        "--authorization-record-path",
        type=Path,
        default=AUTHORIZATION_RECORD_PATH,
        help="Path to the {authorized_runner_commit} JSON this exact HEAD must equal.",
    )
    parser.add_argument(
        "--frame-manifest-path",
        type=Path,
        default=Path(PERSON_A_FRAME_MANIFEST_PATH),
        help="Local path to Person A's committed preprocessed_frame_manifest.json.",
    )
    parser.add_argument(
        "--frame-root",
        type=Path,
        default=None,
        help="Local root containing the 1,695 real frame payload files.",
    )
    parser.add_argument(
        "--verify-payloads",
        action="store_true",
        help=(
            "Verify all 1,695 frame payloads on disk during preflight "
            "(requires --frame-root). Always forced on for 'run' mode "
            "regardless of this flag, since raw_pixel requires every "
            "payload to be read either way."
        ),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(DEFAULT_APPROVED_OUTPUT_ROOT),
        help="Approved output root for this runner's produced artifacts.",
    )
    parser.add_argument(
        "--materialize-root",
        type=Path,
        default=Path(DEFAULT_MATERIALIZED_INPUT_ROOT),
        help="Root 'materialize' mode writes byte-verified committed inputs into.",
    )
    parser.add_argument(
        "--fold-manifest-path",
        type=Path,
        default=None,
        help=(
            "Local path to Person B's real ten_pilot_frame_fold_manifest.json "
            "(defaults to <materialize-root>/" + MATERIALIZED_FOLD_MANIFEST_FILENAME + ")."
        ),
    )
    parser.add_argument(
        "--target-manifest-path",
        type=Path,
        default=None,
        help=(
            "Local path to Person B's real production_oracle_target_manifest.json "
            "(defaults to <materialize-root>/" + MATERIALIZED_ORACLE_TARGET_FILENAME + ")."
        ),
    )
    parser.add_argument(
        "--source-context-manifest-path",
        type=Path,
        default=None,
        help=(
            "Local path to Person B's real source_context_manifest.json "
            "(defaults to <materialize-root>/"
            + MATERIALIZED_SOURCE_CONTEXT_MANIFEST_FILENAME
            + ")."
        ),
    )
    parser.add_argument(
        "--source-context-root",
        type=Path,
        default=None,
        help=(
            "Local root containing the ten real capture_package_v0_1.json "
            "files at their frozen relative paths (defaults to --materialize-root)."
        ),
    )
    parser.add_argument(
        "--analysis-config-path",
        type=Path,
        default=Path(FROZEN_DIRECT_INPUTS["analysis_config"]["path"]),
        help="Local path to the frozen configs/analysis/core.yaml.",
    )
    parser.add_argument(
        "--resume",
        choices=("resume", "force"),
        default="resume",
        help=(
            "resume: skip any family whose recorded output still exists "
            "and still re-validates. force: explicitly authorize "
            "refitting every family regardless of run_state.json."
        ),
    )
    args = parser.parse_args()

    git_facts = resolve_git_facts(ROOT)
    authorized_runner_commit = load_authorized_runner_commit(args.authorization_record_path)
    authorization_errors = verify_branch_and_authorization(
        authorized_runner_commit=authorized_runner_commit, **git_facts
    )
    if authorization_errors:
        print(f"FAIL-CLOSED: authorization checks failed: {authorization_errors}", file=sys.stderr)
        return 1

    if args.mode == "materialize":
        try:
            materialize_report = run_materialize(
                repo_root=ROOT, materialize_root=args.materialize_root
            )
        except ProductionInputIngestError as error:
            print(f"FAIL-CLOSED: materialize failed: {error}", file=sys.stderr)
            return 1
        print(json.dumps({"materialize": materialize_report["status"]}, indent=2))
        return 0

    if not args.frame_manifest_path.exists():
        print(
            f"FAIL-CLOSED: frame manifest not found at {args.frame_manifest_path}. "
            "This script must not be run outside its approved SageMaker "
            "environment.",
            file=sys.stderr,
        )
        return 1

    if args.mode == "run" and args.frame_root is None:
        print("FAIL-CLOSED: 'run' mode requires --frame-root.", file=sys.stderr)
        return 1

    materialize_root = args.materialize_root
    fold_manifest_path = args.fold_manifest_path or (
        materialize_root / MATERIALIZED_FOLD_MANIFEST_FILENAME
    )
    target_manifest_path = args.target_manifest_path or (
        materialize_root / MATERIALIZED_ORACLE_TARGET_FILENAME
    )
    source_context_manifest_path = args.source_context_manifest_path or (
        materialize_root / MATERIALIZED_SOURCE_CONTEXT_MANIFEST_FILENAME
    )
    source_context_root = args.source_context_root or materialize_root

    # The producing ('run') path must always validate the fold manifest
    # as part of the one shared preflight below -- it can never bypass
    # it. A bare 'preflight' invocation only validates it when the
    # caller explicitly supplied --fold-manifest-path, preserving
    # backward-compatible frame-manifest-only preflight checks.
    preflight_fold_manifest_path = (
        fold_manifest_path if args.mode == "run" or args.fold_manifest_path else None
    )

    verify_payloads = args.verify_payloads or args.mode == "run"
    try:
        preflight_report = run_preflight(
            frame_manifest_path=args.frame_manifest_path,
            frame_root=args.frame_root,
            verify_payloads=verify_payloads,
            fold_manifest_path=preflight_fold_manifest_path,
        )
    except ProductionRunnerError as error:
        print(f"FAIL-CLOSED: preflight failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"preflight": preflight_report["status"]}, indent=2))

    if args.mode == "preflight":
        return 0

    try:
        real_inputs = build_real_run_inputs(
            fold_manifest_path=fold_manifest_path,
            target_manifest_path=target_manifest_path,
            source_context_manifest_path=source_context_manifest_path,
            source_context_root=source_context_root,
            analysis_config_path=args.analysis_config_path,
            frame_manifest=preflight_report["frame_manifest"],
            frame_root=args.frame_root,
            execution_manifest=preflight_report["eight_family_execution_manifest"],
        )
    except ProductionRunnerError as error:
        print(f"FAIL-CLOSED: real input assembly failed: {error}", file=sys.stderr)
        return 1

    state = run_production(
        output_root=args.output_root,
        force_rerun=args.resume == "force",
        **real_inputs,
    )
    print(
        json.dumps(
            {
                "run": "COMPLETED",
                "families": {
                    family_id: record.get("status")
                    for family_id, record in state["families"].items()
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
