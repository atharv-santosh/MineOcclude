"""Load, hash, and freeze the MVP configuration identity (Step 7.1).

The configuration file is the authority for model, preprocessing, extraction,
seed, matrix, storage, queue, and U4 settings. This module gives it a stable
content hash, separates result-changing values from operational ones, and
refuses to accept a document that silently moved a scientific choice.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from mineocclude.contracts.activation import (
    MAX_MODEL_FRAMES,
    TOKENS_PER_FRAME_ACTION_PAIR,
    VISUAL_TOKENS_PER_FRAME,
)
from mineocclude.contracts.identity import SCHEMA_VERSION

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

MVP_CONFIG_ID = "person-a-mvp-v1.0"
MVP_CONFIG_VERSION = "1.0"

# Dotted paths whose value changes the scientific meaning of a result. Editing
# any of these requires a dated decision record and a new run identity.
RESULT_CHANGING_PATHS: tuple[str, ...] = (
    "model.checkpoint_sha256",
    "model.vae_checkpoint_sha256",
    "model.config_sha256",
    "model.vae_config_sha256",
    "model.source_revision",
    "model.asset_revision",
    "model.decoder_layer_count",
    "model.precision",
    "preprocess.identity",
    "preprocess.model_resolution",
    "preprocess.interpolation",
    "preprocess.color_conversion",
    "tokens.visual_tokens_per_frame",
    "tokens.action_tokens_per_frame",
    "tokens.max_model_frames_per_context",
    "extraction.mode",
    "extraction.hook_site",
    "extraction.layers",
    "extraction.pooling",
    "extraction.pooling_identity",
    "extraction.stored_dtype",
    "extraction.vector_width",
    "seeds.extraction_seed",
    "seeds.rollout_seeds",
    "seeds.control_seed",
    "matrix.expected_cell_count",
    "matrix.expected_matrix_source.sha256",
    "accepted_manifest.canonical_collection_id",
    "accepted_manifest.capture_output_bundle_sha256",
    "u4_pilot.intended_block_shifts",
    "u4_pilot.max_relative_activation_norm",
    "u4_pilot.injection_scope",
    "u4_pilot.injected_position_count",
    "repeatability.rtol",
    "repeatability.atol",
    "frozen_decisions.step_4_1_decision",
)

# Operational values that may change without a new scientific run identity.
OPERATIONAL_PATHS: tuple[str, ...] = (
    "queue.max_transient_retries",
    "queue.transient_retry_backoff_seconds",
    "queue.quarantine_on",
    "queue.skip_rule",
    "storage.bytes_per_activation_row",
    "storage.bytes_per_model_frame",
    "storage.chunk_layout",
)

REQUIRED_SECTIONS: tuple[str, ...] = (
    "model",
    "preprocess",
    "tokens",
    "extraction",
    "seeds",
    "matrix",
    "accepted_manifest",
    "storage",
    "queue",
    "u4_pilot",
    "repeatability",
    "frozen_decisions",
)


class MvpConfigErrorCode(str, Enum):
    """Stable reasons an MVP configuration is not usable."""

    MISSING_FILE = "missing_file"
    MALFORMED_DOCUMENT = "malformed_document"
    MISSING_SECTION = "missing_section"
    MISSING_FIELD = "missing_field"
    SCHEMA_MISMATCH = "schema_mismatch"
    IDENTITY_MISMATCH = "identity_mismatch"
    NOT_FROZEN = "not_frozen"
    FROZEN_DECISION_MOVED = "frozen_decision_moved"
    CONTRACT_DISAGREEMENT = "contract_disagreement"


class MvpConfigError(ValueError):
    """Raised when the frozen MVP configuration cannot be trusted."""

    def __init__(self, code: MvpConfigErrorCode, message: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}")


def _fail(code: MvpConfigErrorCode, message: str) -> None:
    raise MvpConfigError(code, message)


def canonical_config_bytes(document: Mapping[str, Any]) -> bytes:
    """Serialize a configuration deterministically for hashing."""

    return json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def config_hash(document: Mapping[str, Any]) -> str:
    """Return the content hash of a configuration's canonical form."""

    return hashlib.sha256(canonical_config_bytes(document)).hexdigest()


def read_path(document: Mapping[str, Any], dotted: str) -> Any:
    """Return a dotted-path value, or raise when a segment is missing."""

    current: Any = document
    for segment in dotted.split("."):
        if not isinstance(current, Mapping) or segment not in current:
            _fail(
                MvpConfigErrorCode.MISSING_FIELD,
                f"configuration path {dotted!r} is absent",
            )
        current = current[segment]
    return current


@dataclass(frozen=True)
class MvpConfig:
    """One validated, content-addressed MVP configuration."""

    path: Path
    document: Mapping[str, Any]
    config_hash: str
    file_sha256: str

    @property
    def relative_path(self) -> str:
        """Return a repository-relative path so identity stays portable."""

        try:
            return self.path.resolve().relative_to(_REPOSITORY_ROOT).as_posix()
        except ValueError:
            return self.path.as_posix()

    @property
    def config_id(self) -> str:
        return str(self.document["config_id"])

    @property
    def config_version(self) -> str:
        return str(self.document["config_version"])

    @property
    def extraction_seed(self) -> int:
        return int(read_path(self.document, "seeds.extraction_seed"))

    @property
    def model_hash(self) -> str:
        return str(read_path(self.document, "model.checkpoint_sha256"))

    @property
    def preprocess_hash(self) -> str:
        """Hash the frozen preprocessing block, not just its human label."""

        return hashlib.sha256(
            canonical_config_bytes(self.document["preprocess"])
        ).hexdigest()

    @property
    def expected_cell_count(self) -> int:
        return int(read_path(self.document, "matrix.expected_cell_count"))

    def get(self, dotted: str) -> Any:
        return read_path(self.document, dotted)

    def identity(self) -> dict[str, Any]:
        """Return the immutable identity block stamped onto every MVP run."""

        return {
            "schema_version": SCHEMA_VERSION,
            "config_id": self.config_id,
            "config_version": self.config_version,
            "config_hash": self.config_hash,
            "config_file_sha256": self.file_sha256,
            "config_path": self.relative_path,
            "model_hash": self.model_hash,
            "preprocess_hash": self.preprocess_hash,
            "seed": self.extraction_seed,
        }

    def result_changing_values(self) -> dict[str, Any]:
        return {path: read_path(self.document, path) for path in RESULT_CHANGING_PATHS}

    def operational_values(self) -> dict[str, Any]:
        return {path: read_path(self.document, path) for path in OPERATIONAL_PATHS}


def load_mvp_config(path: Path | str) -> MvpConfig:
    """Read, validate, and hash the frozen MVP configuration."""

    source = Path(path)
    if not source.is_file():
        _fail(
            MvpConfigErrorCode.MISSING_FILE,
            f"MVP configuration is absent: {source.as_posix()}",
        )
    raw = source.read_bytes()
    try:
        document = yaml.safe_load(raw.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as error:
        _fail(
            MvpConfigErrorCode.MALFORMED_DOCUMENT,
            f"{source.as_posix()} is not readable YAML: {error}",
        )
        raise  # pragma: no cover - _fail always raises
    if not isinstance(document, Mapping):
        _fail(
            MvpConfigErrorCode.MALFORMED_DOCUMENT,
            "MVP configuration must be a mapping",
        )
    validate_mvp_config(document)
    return MvpConfig(
        path=source,
        document=document,
        config_hash=config_hash(document),
        file_sha256=hashlib.sha256(raw).hexdigest(),
    )


def validate_mvp_config(document: Mapping[str, Any]) -> None:
    """Reject a configuration that drifted from the frozen contracts."""

    if document.get("schema_version") != SCHEMA_VERSION:
        _fail(
            MvpConfigErrorCode.SCHEMA_MISMATCH,
            f"schema_version must equal {SCHEMA_VERSION!r}",
        )
    if document.get("config_id") != MVP_CONFIG_ID:
        _fail(
            MvpConfigErrorCode.IDENTITY_MISMATCH,
            f"config_id must equal {MVP_CONFIG_ID!r}",
        )
    if document.get("config_version") != MVP_CONFIG_VERSION:
        _fail(
            MvpConfigErrorCode.IDENTITY_MISMATCH,
            f"config_version must equal {MVP_CONFIG_VERSION!r}",
        )
    if document.get("frozen") is not True:
        _fail(
            MvpConfigErrorCode.NOT_FROZEN,
            "the MVP configuration must declare frozen: true",
        )
    missing = [name for name in REQUIRED_SECTIONS if name not in document]
    if missing:
        _fail(
            MvpConfigErrorCode.MISSING_SECTION,
            "configuration is missing sections: " + ", ".join(missing),
        )
    for dotted in (*RESULT_CHANGING_PATHS, *OPERATIONAL_PATHS):
        read_path(document, dotted)

    if read_path(document, "frozen_decisions.step_4_1_decision") != "FAIL":
        _fail(
            MvpConfigErrorCode.FROZEN_DECISION_MOVED,
            "the frozen Step 4.1 scientific decision must remain FAIL",
        )
    if read_path(document, "frozen_decisions.step_4_1_rerun_authorized") is not False:
        _fail(
            MvpConfigErrorCode.FROZEN_DECISION_MOVED,
            "Step 4.1 must not be authorized for rerun by this configuration",
        )

    _require_contract_agreement(document)
    _require_matrix_arithmetic(document)
    _require_u4_arithmetic(document)


def _require_contract_agreement(document: Mapping[str, Any]) -> None:
    checks = (
        (
            "tokens.visual_tokens_per_frame",
            VISUAL_TOKENS_PER_FRAME,
        ),
        (
            "tokens.tokens_per_frame_action_pair",
            TOKENS_PER_FRAME_ACTION_PAIR,
        ),
        (
            "tokens.max_model_frames_per_context",
            MAX_MODEL_FRAMES,
        ),
    )
    for dotted, expected in checks:
        actual = read_path(document, dotted)
        if actual != expected:
            _fail(
                MvpConfigErrorCode.CONTRACT_DISAGREEMENT,
                f"{dotted} is {actual!r} but the frozen contract requires "
                f"{expected!r}",
            )
    visual = read_path(document, "tokens.visual_tokens_per_frame")
    action = read_path(document, "tokens.action_tokens_per_frame")
    pair = read_path(document, "tokens.tokens_per_frame_action_pair")
    if visual + action != pair:
        _fail(
            MvpConfigErrorCode.CONTRACT_DISAGREEMENT,
            "visual + action tokens must equal the frame/action pair width",
        )
    if read_path(document, "extraction.rows_per_frame") != read_path(
        document, "model.decoder_layer_count"
    ):
        _fail(
            MvpConfigErrorCode.CONTRACT_DISAGREEMENT,
            "rows per frame must equal the decoder layer count",
        )
    if read_path(document, "extraction.vector_width") != read_path(
        document, "model.hidden_size"
    ):
        _fail(
            MvpConfigErrorCode.CONTRACT_DISAGREEMENT,
            "stored vector width must equal the model hidden size",
        )


def _require_matrix_arithmetic(document: Mapping[str, Any]) -> None:
    parts: Sequence[int] = (
        int(read_path(document, "matrix.core_regime_a_cells")),
        int(read_path(document, "matrix.no_wall_visible_control_cells")),
        int(read_path(document, "matrix.occluder_only_no_sheep_control_cells")),
        int(read_path(document, "matrix.context_sentinel_cells")),
    )
    expected = int(read_path(document, "matrix.expected_cell_count"))
    if sum(parts) != expected:
        _fail(
            MvpConfigErrorCode.CONTRACT_DISAGREEMENT,
            f"matrix cell groups sum to {sum(parts)} but expected_cell_count "
            f"is {expected}",
        )


def _require_u4_arithmetic(document: Mapping[str, Any]) -> None:
    events = int(read_path(document, "u4_pilot.heldout_event_count"))
    shifts = read_path(document, "u4_pilot.intended_block_shifts")
    seeds = int(read_path(document, "u4_pilot.seeds_per_cell"))
    primary = int(read_path(document, "u4_pilot.primary_clip_count"))
    if not isinstance(shifts, list) or not shifts:
        _fail(
            MvpConfigErrorCode.MALFORMED_DOCUMENT,
            "u4_pilot.intended_block_shifts must be a non-empty list",
        )
    if events * len(shifts) * seeds != primary:
        _fail(
            MvpConfigErrorCode.CONTRACT_DISAGREEMENT,
            f"{events} events x {len(shifts)} shifts x {seeds} seeds != "
            f"{primary} declared primary clips",
        )
    if read_path(document, "u4_pilot.injected_position_count") != (
        VISUAL_TOKENS_PER_FRAME
    ):
        _fail(
            MvpConfigErrorCode.CONTRACT_DISAGREEMENT,
            "U4 injection must cover exactly the frozen visual-position count",
        )


def compare_configs(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    """Classify the differences between two MVP configurations.

    A result-changing difference demands a new run identity; an operational
    difference does not. Anything else is reported as unclassified so it cannot
    be waved through.
    """

    result_changing: list[dict[str, Any]] = []
    operational: list[dict[str, Any]] = []
    for dotted in RESULT_CHANGING_PATHS:
        before, after = _safe_read(baseline, dotted), _safe_read(candidate, dotted)
        if before != after:
            result_changing.append(
                {"path": dotted, "baseline": before, "candidate": after}
            )
    for dotted in OPERATIONAL_PATHS:
        before, after = _safe_read(baseline, dotted), _safe_read(candidate, dotted)
        if before != after:
            operational.append(
                {"path": dotted, "baseline": before, "candidate": after}
            )
    unclassified = _unclassified_differences(baseline, candidate)
    return {
        "baseline_config_hash": config_hash(baseline),
        "candidate_config_hash": config_hash(candidate),
        "identical": config_hash(baseline) == config_hash(candidate),
        "result_changing_differences": result_changing,
        "operational_differences": operational,
        "unclassified_differences": unclassified,
        "requires_new_run_identity": bool(result_changing or unclassified),
        "requires_dated_decision_record": bool(result_changing),
    }


def _safe_read(document: Mapping[str, Any], dotted: str) -> Any:
    try:
        return read_path(document, dotted)
    except MvpConfigError:
        return None


def _unclassified_differences(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> list[dict[str, Any]]:
    known = set(RESULT_CHANGING_PATHS) | set(OPERATIONAL_PATHS)
    flat_baseline = _flatten(baseline)
    flat_candidate = _flatten(candidate)
    differences: list[dict[str, Any]] = []
    for dotted in sorted(set(flat_baseline) | set(flat_candidate)):
        if dotted in known or any(dotted.startswith(f"{p}.") for p in known):
            continue
        before = flat_baseline.get(dotted)
        after = flat_candidate.get(dotted)
        if before != after:
            differences.append(
                {"path": dotted, "baseline": before, "candidate": after}
            )
    return differences


def _flatten(document: Any, prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    if isinstance(document, Mapping):
        for key, value in document.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, Mapping):
                flat.update(_flatten(value, child))
            else:
                flat[child] = value
    elif prefix:
        flat[prefix] = document
    return flat


def build_freeze_record(
    config: MvpConfig,
    *,
    code_sha: str,
    signed_by: Sequence[str],
) -> dict[str, Any]:
    """Produce the Step 7.1 signed identity record for this configuration."""

    if not signed_by:
        _fail(
            MvpConfigErrorCode.MISSING_FIELD,
            "a freeze record requires at least one validating role",
        )
    return {
        "schema_version": "person-a-mvp-identity-freeze-v0.1",
        "step": "7.1",
        "status": "FROZEN",
        "identity": config.identity(),
        "code_sha": code_sha,
        "validated_by_roles": sorted(set(signed_by)),
        "result_changing_paths": list(RESULT_CHANGING_PATHS),
        "operational_paths": list(OPERATIONAL_PATHS),
        "result_changing_values": config.result_changing_values(),
        "operational_values": config.operational_values(),
        "migration_rule": (
            "A change to any result_changing path requires a dated decision "
            "record and a new run identity; it never edits an accepted run."
        ),
        "frozen_step_4_1_decision": config.get(
            "frozen_decisions.step_4_1_decision"
        ),
    }


__all__ = [
    "MVP_CONFIG_ID",
    "MVP_CONFIG_VERSION",
    "OPERATIONAL_PATHS",
    "RESULT_CHANGING_PATHS",
    "MvpConfig",
    "MvpConfigError",
    "MvpConfigErrorCode",
    "build_freeze_record",
    "canonical_config_bytes",
    "compare_configs",
    "config_hash",
    "load_mvp_config",
    "read_path",
    "validate_mvp_config",
]
