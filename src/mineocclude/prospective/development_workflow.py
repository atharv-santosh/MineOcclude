"""Fail-closed prospective development workflow for Regime A-prime.

Scientific choices are supplied by the draft authority. This module verifies
evidence and cryptographic bindings; it never authorizes collection itself.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import statistics
import subprocess
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from mineocclude.prospective.extent_geometry import (
    TARGET_EXTENT_HALF_BLOCKS,
    ExtentClass,
    WallGeometry,
    classify_extent,
)
from mineocclude.prospective.package_binding import (
    PackageBindingError,
    artifact_version_tag,
    provenance_artifact_id_for,
    stage1_decision_artifact_id,
)
from mineocclude.prospective.source_provenance import CriticalSource, verify_sources
from mineocclude.prospective.temporal_alignment import (
    PURE_DELAY_OFF_PEAK_MASS_TOLERANCE,
    kernel_group_delay_ticks,
    kernel_is_effectively_pure_delay,
    kernel_mode_lag,
    kernel_off_peak_mass,
    kernel_positive_mass_support,
    normalized_kernel,
)


#: The v0.3 truth predicate, selected by the authority rather than by evidence.
EXTENT_TRUTH_PREDICATE = "extent_occlusion_geometry_over_rendered_target_extent"

RUNTIME_CRITICAL_SOURCE_PATHS = (
    "scripts/regime_a_prime_qualification_v0_3/build_authority.py",
    "scripts/regime_a_prime_qualification_v0_3/build_manifests.py",
    "src/mineocclude/prospective/extent_geometry.py",
    # The v0.3 execution surface. These carry no scientific logic -- they bind a
    # version tag and delegate -- but the tag is precisely what selects WHICH
    # experiment runs, so their bytes are as runtime-critical as the code they
    # delegate to. Omitting them would let the closure certify an apparatus
    # whose entrypoint had been repointed at the predecessor inventory.
    "src/mineocclude/prospective/package_binding.py",
    "scripts/regime_a_prime_qualification_v0_3/generate_receipts.py",
    "scripts/regime_a_prime_qualification_v0_3/development_controller.py",
    "scripts/regime_a_prime_qualification_v0_3/verify_package.py",
    "scripts/regime_a_prime_qualification_v0_3/acceptance_harness.py",
    "scripts/regime_a_prime_qualification_v0_2/build_manifests.py",
    "scripts/regime_a_prime_qualification_v0_2/build_stage1_evidence.py",
    "scripts/regime_a_prime_qualification_v0_2/development_controller.py",
    "scripts/regime_a_prime_qualification_v0_2/generate_receipts.py",
    "scripts/regime_a_prime_qualification_v0_2/stage2_backend.py",
    "scripts/regime_a_prime_qualification_v0_2/stage_unit_driver.py",
    "scripts/regime_a_prime_qualification_v0_2/verify_package.py",
    "src/mineocclude/prospective/development_workflow.py",
    "src/mineocclude/prospective/clock_domains.py",
    "src/mineocclude/prospective/temporal_alignment.py",
    "src/mineocclude/prospective/source_provenance.py",
    "src/mineocclude/vision/magenta.py",
    "src/mineocclude/contracts/identity.py",
    "src/mineocclude/contracts/trajectory.py",
    "src/mineocclude/data/align.py",
    "src/mineocclude/data/build_dataset.py",
    "src/mineocclude/data/capture_contract.py",
    "src/mineocclude/data/convert_mineworld.py",
    "src/mineocclude/data/fsretry.py",
    "src/mineocclude/data/impulse.py",
    "src/mineocclude/data/noise_schedule.py",
    "src/mineocclude/data/package_episode.py",
    "src/mineocclude/data/preprocess.py",
    "src/mineocclude/data/qa_report.py",
    "src/mineocclude/data/visibility.py",
    "src/mineocclude/models/__init__.py",
    "src/mineocclude/probes/p7_ridge.py",
    "src/mineocclude/probes/p7a_execution.py",
    "src/mineocclude/regime_a.py",
    "src/mineocclude/regime_a_execution.py",
    "src/mineocclude/regime_a_first25_analysis.py",
    "scripts/run_regime_a.py",
    # Capture/startup apparatus. Both were outside the closure while controlling
    # real Stage-1 behaviour, so their bytes could change what a capture did
    # without changing the runtime-critical digest that authorizes it.
    #
    # p2_common.load_live() imports the campaign module directly
    # ("from scripts import run_large_scale_no_wall_campaign as live"), and it
    # owns LiveRuntime.send, the startspec FIFO command, launch_runtime,
    # stop_runtime, SERVER_ROOT/CLIENT_ROOT and the scientific episode startup.
    #
    # launch_runtime execs the provisioning script for start-display,
    # start-server and start-client, so that script owns the Xvfb geometry
    # (640x360x24), LIBGL_ALWAYS_SOFTWARE, the JVM heap/runtime arguments and
    # the natives path -- every one of which is physically material to a frame.
    "scripts/run_large_scale_no_wall_campaign.py",
    "scripts/provision_capture_runtime_sagemaker.sh",
    "scripts/regime_a_prime_qualification_v0_1/p2_common.py",
    "scripts/regime_a_prime_qualification_v0_1/p2c_capture.py",
    "scripts/regime_a_prime_qualification_v0_1/p2d_extract.py",
    "scripts/regime_a_prime_qualification_v0_1/p2e_analyze.py",
    "scripts/regime_a_prime_qualification_v0_1/p3_run_sequential.py",
    "schemas/prospective/regime_a_prime_stage1_decision_v0_2.schema.json",
    # One decision schema per package version, pinning that version's decision
    # identity as a const. A single schema with a loosened artifact_id pattern
    # would have accepted the very cross-version substitution the Stage-2 gate
    # now refuses.
    "schemas/prospective/regime_a_prime_stage1_decision_v0_3.schema.json",
    "schemas/prospective/regime_a_prime_stage1_decision_v0_4.schema.json",
    # The v0.4 execution surface. As with v0.3, these carry no scientific logic
    # -- they bind a version tag and delegate to the shared v0.2 implementations
    # -- but the tag is precisely what selects WHICH inventory runs, so their
    # bytes are as runtime-critical as the code they delegate to.
    "scripts/regime_a_prime_qualification_v0_4/build_authority.py",
    "scripts/regime_a_prime_qualification_v0_4/build_manifests.py",
    "scripts/regime_a_prime_qualification_v0_4/development_controller.py",
    "scripts/regime_a_prime_qualification_v0_4/generate_receipts.py",
    "scripts/regime_a_prime_qualification_v0_4/verify_package.py",
    "scripts/regime_a_prime_qualification_v0_4/acceptance_harness.py",
)
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class EvidenceError(ValueError):
    """Malformed, missing, contradictory, or insufficient evidence."""


# The two required methods do not share an estimand, so requiring each one's
# point estimate to land inside the other's interval compares quantities that
# are not expected to coincide. ``causal_fir_group_delay`` reports the FIRST
# MOMENT sum(k*h[k]) of the fitted causal kernel; ``derivative_cross_correlation
# _lag`` picks the single lag that best explains the rendered increments, which
# is that same kernel's MODE, sub-tick refined. A right-tailed causal smoothing
# response puts the mode strictly before the first moment, so the superseded
# mutual-containment rule was satisfiable only by a kernel whose mode equals its
# mean -- the symmetric or bare-delay response this authority already forbids.
# The frozen P2/P3 forensic reference demonstrates this concretely: FIR 3.3636
# ticks (t95 [3.1850, 3.5423]) against cross-correlation 2.4597 ticks (t95
# [2.2588, 2.6607]), two intervals separated by 0.5243 ticks with the reference
# violating mutual containment by 0.7253 ticks.
#
# Agreement is therefore defined between matched estimands: each method's own
# interval must reproduce from its own per-trajectory values and contain its own
# estimate; every estimate and endpoint must lie in the admissible causal lag
# range [0, maximum_lag_ticks_for_estimation] (the frozen clock-domain authority
# orders render at-or-after server state, so a negative lag is acausal, and no
# estimator resolves a lag outside its declared search range); and the
# cross-correlation lag must pair with the MODE of the bound FIR kernel, per
# trajectory and in aggregate, within the estimator's own parabolic-refinement
# clamp. Because the kernels are already bound to the per-trajectory group
# delays, this trusts no new mutable field, and unlike interval overlap it
# cannot be satisfied by widening an interval.
AGREEMENT_RULE = ("causal_kernel_mode_and_first_moment_estimand_pairing"
                  "_within_admissible_causal_lag_range")

# Designated hidden rows must be reproducible from the frozen schedule rather
# than chosen after the run is observed.
DESIGNATED_HIDDEN_ROW_SELECTION_RULE = (
    "FIRST_N_QUALIFIED_STABLE_OCCLUDED_ROWS_IN_ASCENDING_MODEL_FRAME_ORDER")


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def canonical_payload_sha256(value: Mapping[str, Any], *, omit: str | None = None) -> str:
    payload = {key: item for key, item in value.items() if key != omit}
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"invalid JSON at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"top-level JSON at {path} must be an object")
    return value


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(dict(value))
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceError(f"{name} must be a plain number")
    result = float(value)
    if not math.isfinite(result):
        raise EvidenceError(f"{name} must be finite")
    return result


def _integer(value: Any, name: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvidenceError(f"{name} must be a plain integer")
    if minimum is not None and value < minimum:
        raise EvidenceError(f"{name} must be >= {minimum}")
    return value


def _sha(value: Any, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise EvidenceError(f"{name} must be a lowercase SHA-256")
    return value


def derive_projection_validity(raw: Mapping[str, Any], *,
                               frame_pixels: Sequence[int],
                               token_grid: Sequence[int]) -> bool:
    """Derive in-frame status from bound raw screen and token-cell coordinates."""
    if (not isinstance(frame_pixels, (list, tuple)) or len(frame_pixels) != 2
            or not isinstance(token_grid, (list, tuple)) or len(token_grid) != 2):
        raise EvidenceError("projection dimensions are missing or malformed")
    width = _integer(frame_pixels[0], "frame width", minimum=1)
    height = _integer(frame_pixels[1], "frame height", minimum=1)
    token_rows = _integer(token_grid[0], "token rows", minimum=1)
    token_cols = _integer(token_grid[1], "token columns", minimum=1)
    screen_x = _number(raw.get("screen_x"), "screen_x")
    screen_y = _number(raw.get("screen_y"), "screen_y")
    token_row = _integer(raw.get("token_row"), "token_row", minimum=0)
    token_col = _integer(raw.get("token_col"), "token_col", minimum=0)
    in_screen = 0 <= screen_x < width and 0 <= screen_y < height
    in_tokens = token_row < token_rows and token_col < token_cols
    if not in_screen or not in_tokens:
        return False
    expected_row = math.floor(screen_y * token_rows / height)
    expected_col = math.floor(screen_x * token_cols / width)
    return token_row == expected_row and token_col == expected_col


def bind_manifest(authority_path: Path, manifest: Mapping[str, Any]) -> None:
    expected = manifest.get("authority_binding", {}).get("sha256")
    _sha(expected, "manifest authority binding")
    actual = sha256_file(authority_path)
    if actual != expected:
        raise EvidenceError(f"authority binding mismatch: expected {expected}, got {actual}")


def validate_stage2_manifest_design(authority: Mapping[str, Any], manifest: Mapping[str, Any], *,
                                    require_materialized: bool) -> None:
    """Bind the complete Stage-2 fold/phase/pair/pipeline design to authority."""
    policy = authority["stage2_policy"]
    fixed = authority["fixed_development_configuration"]
    # Read out of the authority's own stage binding table rather than spelled as
    # a literal here. A literal made this shared validator silently v0.2-only:
    # the v0.3 locked manifest, which correctly identifies itself as v0.3, was
    # rejected as an invalid authority boundary. Deriving it is also strictly
    # stronger, because a manifest must now match the identity the authority
    # that binds it declares, not one this module remembers.
    expected_artifact_id = (authority["stage_binding_policy"]["stages"]["stage2-capture"]
                            ["manifest_artifact_id"])
    if (manifest.get("artifact_id") != expected_artifact_id
            or manifest.get("classification") != "DEVELOPMENT_ONLY"
            or manifest.get("STAGE_2_COLLECTION_AUTHORIZED") is not False
            or manifest.get("confirmatory_collection_authorized") is not False
            or manifest.get("source_commit_binding")
               != "BOUND_AT_LAUNCH_BY_PREOUTCOME_PROVENANCE_RECEIPT"):
        raise EvidenceError("Stage-2 manifest authority boundary is invalid")
    expected_status = ("POST_STAGE1_MATERIALIZED_AWAITING_SEPARATE_FREEZE_AND_AUTHORIZATION"
                       if require_materialized
                       else "DRAFT_TEMPLATE_AWAITING_STAGE1_TARGET_MATERIALIZATION")
    if manifest.get("status") != expected_status:
        raise EvidenceError("Stage-2 manifest materialization state is invalid")
    if (manifest.get("trajectory_identity_count") != policy["paired_trajectory_identities"]
            or manifest.get("scientific_capture_count") != policy["scientific_capture_count"]
            or manifest.get("required_target_rows_per_capture")
               != policy["required_target_rows_per_capture"]):
        raise EvidenceError("Stage-2 declared counts override authority")
    identities = manifest.get("trajectory_identities")
    if not isinstance(identities, list) or len(identities) != policy["paired_trajectory_identities"]:
        raise EvidenceError("Stage-2 trajectory identity count mismatch")
    phases = policy["phase_offsets_frames"]
    folds = policy["outer_folds"]
    ltr = {int(fold): set(indices)
           for fold, indices in policy["left_to_right_phase_indices_by_fold"].items()}
    by_id: dict[str, Mapping[str, Any]] = {}
    cells: set[tuple[int, int]] = set()
    for item in identities:
        if not isinstance(item, dict):
            raise EvidenceError("Stage-2 trajectory identity is malformed")
        identity = item.get("trajectory_id")
        if not isinstance(identity, str) or not identity or identity in by_id:
            raise EvidenceError("Stage-2 trajectory identity is duplicate or malformed")
        fold = _integer(item.get("outer_fold"), "outer_fold", minimum=0)
        phase = _integer(item.get("phase_frames"), "phase_frames", minimum=0)
        if fold >= folds or phase not in phases:
            raise EvidenceError("Stage-2 fold/phase is outside authority")
        phase_index = phases.index(phase)
        expected_direction = "LEFT_TO_RIGHT" if phase_index in ltr[fold] else "RIGHT_TO_LEFT"
        if (item.get("direction") != expected_direction
                or item.get("speed_blocks_per_second") != fixed["speed_blocks_per_second"]
                or item.get("motion_noise_q") != fixed["motion_noise_q"]
                or item.get("start_world_x") != fixed["start_world_x_by_direction"][expected_direction]
                or item.get("expected_frames") != fixed["expected_frames_per_run"]
                or item.get("scientific_run_id") != manifest.get("run_namespace")
                or item.get("confirmatory_membership") is not False):
            raise EvidenceError(f"Stage-2 identity {identity} overrides authority")
        target_status = ("MATERIALIZED_FROM_STAGE1" if require_materialized
                         else "TO_BE_MATERIALIZED_FROM_FROZEN_STAGE1_DECISION")
        if item.get("target_window_status") != target_status:
            raise EvidenceError("Stage-2 target materialization status mismatch")
        if require_materialized:
            ticks = item.get("target_model_frame_indices")
            labels = item.get("expected_causal_fir_target_world_x_blocks")
            if (not isinstance(ticks, list) or len(ticks) != policy["required_target_rows_per_capture"]
                    or not isinstance(labels, list) or len(labels) != len(ticks)):
                raise EvidenceError("Stage-2 materialized target evidence is incomplete")
        cells.add((fold, phase)); by_id[identity] = item
    expected_cells = {(fold, phase) for fold in range(folds) for phase in phases}
    if cells != expected_cells:
        raise EvidenceError("Stage-2 fold and phase are confounded or incomplete")
    captures = manifest.get("capture_units")
    if not isinstance(captures, list) or len(captures) != policy["scientific_capture_count"]:
        raise EvidenceError("Stage-2 capture count mismatch")
    capture_ids: set[str] = set(); pair_cells: set[tuple[str, str]] = set()
    identity_fields = ("seed", "noise_seed", "direction", "outer_fold", "phase_frames",
        "speed_blocks_per_second", "motion_noise_q", "start_world_x", "expected_frames",
        "scientific_run_id", "expected_path_sha256", "target_window_status")
    if require_materialized:
        identity_fields += ("target_model_frame_indices", "expected_causal_fir_target_world_x_blocks")
    for unit in captures:
        if not isinstance(unit, dict) or unit.get("trajectory_id") not in by_id:
            raise EvidenceError("Stage-2 capture identity is malformed")
        identity = by_id[unit["trajectory_id"]]; scene = unit.get("scene")
        unit_id = unit.get("unit_id")
        if (scene not in policy["scenes_per_identity"] or not isinstance(unit_id, str)
                or not unit_id or unit_id in capture_ids
                or unit.get("confirmatory_membership") is not False
                or any(unit.get(field) != identity.get(field) for field in identity_fields)):
            raise EvidenceError("Stage-2 capture overrides its paired identity")
        capture_ids.add(unit_id); pair_cells.add((unit["trajectory_id"], scene))
    expected_pairs = {(identity, scene) for identity in by_id for scene in policy["scenes_per_identity"]}
    if pair_cells != expected_pairs:
        raise EvidenceError("Stage-2 WALL/NO_WALL pair allocation is incomplete")
    extractions = manifest.get("extraction_units")
    if (not isinstance(extractions, list) or len(extractions) != len(captures)
            or {item.get("source_capture_unit_id") for item in extractions} != capture_ids
            or any(item.get("layer") != 4 for item in extractions)):
        raise EvidenceError("Stage-2 layer-4 extraction allocation is invalid")
    if (manifest.get("pipeline_order") != ["capture_and_durability", "physical_gates",
            "layer4_extraction", "best_k", "full", "terminal"]
            or manifest.get("fail_closed_before_extraction") is not True):
        raise EvidenceError("Stage-2 pipeline order is not fail-closed")
    expected_units = (captures + [manifest.get("physical_gate_unit")] + extractions
                      + manifest.get("readout_and_terminal_units", []))
    if manifest.get("units") != expected_units:
        raise EvidenceError("Stage-2 execution unit sequence diverges from locked pipeline")


def one_sided_zero_error_upper_95(sample_count: int) -> float:
    if sample_count < 1:
        raise EvidenceError("zero-error bound requires at least one sample")
    return 1.0 - 0.05 ** (1.0 / sample_count)


def mean_student_t_interval(values: Sequence[float], confidence: float) -> tuple[float, list[float]]:
    """Reconstruct a predeclared trajectory-level Student-t interval."""
    clean = [_number(value, "per-trajectory estimate") for value in values]
    level = _number(confidence, "confidence level")
    if len(clean) < 2 or not 0 < level < 1:
        raise EvidenceError("Student-t interval requires >=2 values and 0<confidence<1")
    import statistics
    from scipy.stats import t as student_t

    mean = statistics.fmean(clean)
    sem = statistics.stdev(clean) / math.sqrt(len(clean))
    half = float(student_t.ppf((1 + level) / 2, len(clean) - 1) * sem)
    return mean, [mean - half, mean + half]


def causal_fir_targets(server_positions: Sequence[float], model_frame_indices: Sequence[int],
                       kernel: Sequence[float],
                       *, pure_delay_tolerance: float = PURE_DELAY_OFF_PEAK_MASS_TOLERANCE
                       ) -> list[float]:
    """Construct labels from the qualified causal state-to-render FIR mapping.

    Uses the single authority-bound pure-delay definition shared with
    :class:`Stage1Evaluator`; counting positive taps admits kernels such as
    ``[1e-300, 0, 0, 1, 0, ...]`` that are a bare 3-tick delay in binary64.
    """
    positions = [_number(value, "server position") for value in server_positions]
    for value in kernel if isinstance(kernel, (list, tuple)) else ():
        _number(value, "FIR coefficient")
    try:
        taps = normalized_kernel(kernel)
    except (TypeError, ValueError) as exc:
        raise EvidenceError(
            f"qualified FIR kernel must contain nonnegative causal smoothing taps: {exc}"
        ) from exc
    if kernel_is_effectively_pure_delay(taps, tolerance=pure_delay_tolerance):
        raise EvidenceError(
            "pure-delay kernel is forbidden: off-peak mass "
            f"{kernel_off_peak_mass(taps):.3e} is within the numerical tolerance "
            f"{pure_delay_tolerance:.3e} of a bare integer-tick delay")
    targets: list[float] = []
    for raw_index in model_frame_indices:
        index = _integer(raw_index, "model frame index", minimum=0)
        if index >= len(positions) or index - len(taps) + 1 < 0:
            raise EvidenceError("model frame lacks complete causal FIR state history")
        targets.append(sum(tap * positions[index - lag] for lag, tap in enumerate(taps)))
    return targets


def verify_runtime_identity(expected: Mapping[str, Any], observed: Mapping[str, Any]) -> dict[str, Any]:
    """Compare independently probed runtime evidence with every authority pin."""
    if observed.get("independently_derived") is not True or observed.get("asserted_by_evidence_builder") is not False:
        raise EvidenceError("runtime evidence must be independently derived")
    fields = expected.get("required_fields")
    if not isinstance(fields, dict) or not fields:
        raise EvidenceError("authority has no runtime identity pins")
    mismatches = {key: {"expected": value, "observed": observed.get(key)}
                  for key, value in fields.items() if observed.get(key) != value}
    source_pins = expected.get("critical_file_sha256")
    observed_pins = observed.get("critical_file_sha256")
    if not isinstance(source_pins, dict) or not isinstance(observed_pins, dict):
        raise EvidenceError("runtime critical-file hashes are missing")
    for key, value in source_pins.items():
        if observed_pins.get(key) != value:
            mismatches[f"critical_file_sha256.{key}"] = {"expected": value, "observed": observed_pins.get(key)}
    if mismatches:
        raise EvidenceError(f"runtime identity mismatch: {mismatches}")
    return {"status": "PASS", "independently_derived": True, "mismatches": {}}


def verify_runtime_source_hashes(source_hashes: Mapping[str, Any], *,
                                 repository: Path = REPOSITORY_ROOT) -> None:
    """Rehash every apparatus-critical runtime source instead of trusting its summary."""
    if not isinstance(source_hashes, dict) or set(source_hashes) != set(RUNTIME_CRITICAL_SOURCE_PATHS):
        raise EvidenceError("runtime source hash coverage is incomplete")
    for relative in RUNTIME_CRITICAL_SOURCE_PATHS:
        expected = _sha(source_hashes.get(relative), f"runtime source SHA {relative}")
        path = repository / relative
        if not path.is_file() or sha256_file(path) != expected:
            raise EvidenceError(f"runtime source bytes mismatch: {relative}")


# --------------------------------------------------------------------------
# Effective capture specification (v0.2 -> v0.1 capture contract)
#
# The v0.1 capture interface (`p2_common.capture_context` via
# `run_regime_a.ProductionCaptureWorker._raw_capture_spec_hash`) requires every
# capture spec to carry a physical-capture identity. v0.1 trajectory specs get
# it from the freeze pipeline, which sets
# ``body["spec_hash"] = canonical_sha256(body)`` over the spec body with the
# field itself absent. The v0.2 Stage-1 manifest describes *units*, not v0.1
# trajectory specs, so the identity has to be derived here or the reused v0.1
# interface raises KeyError before any frame is rendered.
#
# Two fields with distinct meanings, per the v0.1 docstring:
#   spec_hash             analysis/authority identity of the specification
#   raw_capture_spec_hash physical-capture identity; present only when a
#                         versioned amendment keeps the physical capture
#                         contract but reassigns the analysis identity.
# When absent, the physical identity IS the spec identity, so the v0.1 accessor
# falls back to ``spec_hash``. We reproduce that: derive ``spec_hash``, and bind
# ``raw_capture_spec_hash`` to the same value rather than inventing a second one.
#
# Field selection is deliberate and mirrors the split the frozen code already
# makes. ``command`` and ``receipt_path`` are operational dispatch, bound
# separately by ``stage_run_inventory_sha256``; letting them into a scientific
# capture identity would make that identity change when a receipt moves on disk.
# Everything else in the unit describes the physical capture and is included.
# --------------------------------------------------------------------------

# Operational dispatch; already bound by stage_run_inventory_sha256.
CAPTURE_SPEC_DISPATCH_FIELDS = ("command", "receipt_path")
# Self-referential identity fields, excluded so the digest is well-founded.
CAPTURE_SPEC_IDENTITY_FIELDS = ("spec_hash", "raw_capture_spec_hash")
# Every key the v0.1 functions the v0.2 driver actually calls will dereference:
#   p2_common.capture_context     trajectory_spec_id, expected_max_frames,
#                                 noise_seed, motion_noise_q,
#                                 noise_schedule_sha256, speed_blocks_per_second,
#                                 direction, start_world_x, spec_hash
#   p3_run_sequential.derive_artifacts   + seed
#   p2c_capture.package                  (scientific_run_id is defaulted there)
# ``outer_fold`` and the other v0.1 keys in those modules belong to functions the
# v0.2 driver never calls, so requiring them here would overconstrain the gate.
CAPTURE_SPEC_REQUIRED_FIELDS = (
    "trajectory_spec_id", "expected_max_frames", "noise_seed", "motion_noise_q",
    "noise_schedule_sha256", "speed_blocks_per_second", "direction",
    "start_world_x", "spec_hash", "seed",
)


def capture_spec_body(spec: Mapping[str, Any]) -> dict[str, Any]:
    """The scientific body a capture identity is taken over."""
    excluded = set(CAPTURE_SPEC_IDENTITY_FIELDS) | set(CAPTURE_SPEC_DISPATCH_FIELDS)
    return {key: value for key, value in spec.items() if key not in excluded}


def capture_spec_hash(spec: Mapping[str, Any]) -> str:
    """Derive the v0.1 capture identity for an effective capture spec.

    Reuses ``mineocclude.regime_a.canonical_sha256`` -- the exact helper the v0.1
    freeze pipeline used -- rather than a local re-implementation. This is not
    interchangeable with ``canonical_payload_sha256`` above: that one appends a
    trailing newline before hashing, so it does not reproduce v0.1 identities.
    Verified against the frozen v0.1 trajectory manifest: 25/25 reproduce.
    """
    from mineocclude.regime_a import canonical_sha256

    return canonical_sha256(capture_spec_body(spec))


def derive_effective_capture_spec(unit: Mapping[str, Any],
                                  authority: Mapping[str, Any]) -> dict[str, Any]:
    """Build the capture spec Stage-1 actually hands to the v0.1 interface.

    Single source of truth: production capture and pre-authorization preflight
    both call this, so a preflight cannot pass against a spec that differs from
    the one the run will use.
    """
    import numpy

    from mineocclude.data.noise_schedule import generate_noise_schedule

    spec = dict(unit)
    spec.update({
        "trajectory_spec_id": unit.get("trajectory_id", unit["unit_id"]),
        "expected_max_frames": unit["expected_frames"],
        "classification": "DEVELOPMENT_ONLY",
        "confirmatory_membership": False,
    })
    seconds_per_tick = authority["apparatus"]["seconds_per_server_tick"]
    schedule = generate_noise_schedule(int(spec["noise_seed"]), int(spec["expected_frames"]),
                                       float(spec["motion_noise_q"]), seconds_per_tick)
    noise = numpy.asarray([row.noise_draw for row in schedule.rows], dtype="<f8")
    spec["noise_schedule_sha256"] = hashlib.sha256(noise.tobytes()).hexdigest()
    # Derived last, so it covers every scientific field set above.
    spec["spec_hash"] = capture_spec_hash(spec)
    spec["raw_capture_spec_hash"] = spec["spec_hash"]
    return spec


def require_server_seed_contract(spec: Mapping[str, Any]) -> None:
    """Refuse a spec the Java server would refuse to arm.

    ``NoiseSchedule.load(schedulePath, cfg.seed)`` requires the schedule header
    seed to equal the episode seed, and the episode seed is whatever the
    ``startspec`` line carried -- ``spec["seed"]``. Python generates the schedule
    from ``spec["noise_seed"]``. So a spec whose two seed fields disagree cannot
    arm: the server logs ``REFUSED: noise schedule ... is invalid: schedule seed
    X does not match the episode seed Y`` and the episode dies before any frame.

    Sending ``noise_seed`` on the startspec line instead is not the alternative
    reading of this contract: the server logs ``cfg.seed`` into every
    ``server_state`` row and ``p3_run_sequential.derive_artifacts`` re-checks
    each row against ``spec["seed"]``, so that only moves the refusal from
    arming to ``CAPTURE_IDENTITY_MISMATCH`` at frame 0. One value, two names --
    exactly as all 25 Regime A v2.1 amendment-1 specs and every P3 development
    spec carry it.

    Checked here rather than only at the apparatus so the mismatch is a static
    pre-authorization refusal instead of a burnt launch attempt.
    """
    for field in ("seed", "noise_seed"):
        value = spec.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise EvidenceError(f"{field} is not a non-negative integer seed")
    if int(spec["seed"]) != int(spec["noise_seed"]):
        raise EvidenceError(
            f"capture spec violates the server seed contract: seed {spec['seed']} "
            f"!= noise_seed {spec['noise_seed']}; the server refuses any schedule "
            "whose header seed differs from the episode seed it was armed with")


def require_capture_spec_contract(spec: Mapping[str, Any]) -> None:
    """Refuse a capture spec the reused v0.1 interface would reject.

    Re-derives the identity rather than trusting the field, so a hash copied
    from an unrelated spec or left stale after a scientific edit is caught here
    instead of silently mislabelling a capture.
    """
    missing = [field for field in CAPTURE_SPEC_REQUIRED_FIELDS if field not in spec]
    if missing:
        raise EvidenceError(f"effective capture spec is missing required fields: {missing}")
    require_server_seed_contract(spec)
    for field in CAPTURE_SPEC_IDENTITY_FIELDS:
        if field not in spec:
            continue
        value = spec[field]
        if (not isinstance(value, str) or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)):
            raise EvidenceError(f"{field} is not a lowercase SHA-256")
    derived = capture_spec_hash(spec)
    if spec["spec_hash"] != derived:
        raise EvidenceError("spec_hash is not derived from this capture spec")
    # raw_capture_spec_hash may legitimately differ under a versioned amendment,
    # but Stage-1 v0.2 declares no amendment, so it must be the same identity.
    if spec.get("raw_capture_spec_hash", derived) != derived:
        raise EvidenceError("raw_capture_spec_hash does not match the derived capture identity")


# --------------------------------------------------------------------------
# Capture toolchain
#
# Exactly the executables the frozen capture path invokes, traced to their call
# sites rather than taken from the apt closure that happened to be installed:
#
#   start-display : Xvfb, openbox, xdpyinfo   (provision_capture_runtime_sagemaker.sh)
#   start-client  : xdotool, xdpyinfo
#   launch_runtime: xdpyinfo                  (run_large_scale_no_wall_campaign.py)
#
# provision() additionally requires curl, tar, python3 and ffmpeg, but those run
# only during one-time runtime provisioning and are never invoked by capture, so
# requiring them before a capture authorization would overconstrain the gate.
#
# Materiality: Xvfb is already bound as a scientific identity pin (it is the X
# server the frame is rendered through), together with the Mesa/LLVM renderer and
# the JDK. openbox, xdotool and xdpyinfo cannot reach the rendered pixels --
# frames are written by the mod to the client output directory, never screen
# scraped -- so they gate startup only. They are required to be PRESENT and are
# recorded with their package versions, but are deliberately not promoted into
# the scientific identity pins, which stay exactly as they are.
# --------------------------------------------------------------------------

CAPTURE_PATH_EXECUTABLES: tuple[tuple[str, str], ...] = (
    ("Xvfb", "scientific_identity_pinned"),
    ("openbox", "operational_startup_only"),
    ("xdpyinfo", "operational_startup_only"),
    ("xdotool", "operational_startup_only"),
)


def _executable_package(path: str) -> dict[str, Any]:
    """Owning package and version for a resolved executable, best effort."""
    record: dict[str, Any] = {"package": None, "package_version": None}
    try:
        owner = subprocess.run(["dpkg-query", "-S", path], text=True,
                               capture_output=True, check=False)
        if owner.returncode == 0 and ":" in owner.stdout:
            package = owner.stdout.split(":", 1)[0].strip()
            record["package"] = package
            version = subprocess.run(["dpkg-query", "-W", "-f=${Version}", package],
                                     text=True, capture_output=True, check=False)
            if version.returncode == 0:
                record["package_version"] = version.stdout.strip()
    except OSError:
        pass
    return record


def capture_toolchain_evidence() -> dict[str, Any]:
    """Resolve every capture-path executable and record what was found.

    Reports rather than asserts: ``require_capture_toolchain`` adjudicates. Each
    entry also carries unresolved shared libraries, because a present-but-unusable
    binary fails at launch in exactly the same way a missing one does.
    """
    import shutil

    tools: dict[str, Any] = {}
    for name, materiality in CAPTURE_PATH_EXECUTABLES:
        resolved = shutil.which(name)
        entry: dict[str, Any] = {"required_by": "frozen_capture_path",
                                 "materiality": materiality,
                                 "present": resolved is not None,
                                 "path": resolved, "missing_shared_libraries": []}
        if resolved is not None:
            entry.update(_executable_package(resolved))
            try:
                ldd = subprocess.run(["ldd", resolved], text=True,
                                     capture_output=True, check=False)
                entry["missing_shared_libraries"] = [
                    line.split("=>")[0].strip()
                    for line in ldd.stdout.splitlines() if "not found" in line]
            except OSError:
                pass
        tools[name] = entry
    return {"schema": "mineocclude-capture-toolchain-v0.1", "tools": tools,
            "all_present": all(item["present"] for item in tools.values()),
            "all_linkable": all(not item["missing_shared_libraries"]
                                for item in tools.values())}


def require_capture_toolchain(evidence: Mapping[str, Any]) -> None:
    """Refuse authorization when the capture path could not run."""
    tools = evidence.get("tools")
    if not isinstance(tools, dict) or set(tools) != {name for name, _ in CAPTURE_PATH_EXECUTABLES}:
        raise EvidenceError("capture toolchain evidence does not cover the required executables")
    absent = sorted(name for name, item in tools.items() if not item.get("present"))
    if absent:
        raise EvidenceError(f"capture-path executables are absent: {absent}")
    unlinkable = sorted(name for name, item in tools.items()
                        if item.get("missing_shared_libraries"))
    if unlinkable:
        raise EvidenceError(f"capture-path executables cannot resolve libraries: {unlinkable}")


def capture_contract_preflight(manifest: Mapping[str, Any],
                               authority: Mapping[str, Any]) -> dict[str, Any]:
    """Statically prove every unit builds a spec the v0.1 interface accepts.

    Uses ``derive_effective_capture_spec`` -- the same call production capture
    makes -- so this cannot pass against a spec the run would not use. Catches a
    broken v0.2 -> v0.1 contract before a JVM is ever started.
    """
    units = manifest.get("units")
    if not isinstance(units, list) or not units:
        raise EvidenceError("manifest declares no units to preflight")
    checked = {}
    for unit in units:
        spec = derive_effective_capture_spec(unit, authority)
        require_capture_spec_contract(spec)
        checked[str(unit.get("unit_id"))] = spec["spec_hash"]
    if len(set(checked.values())) != len(checked):
        raise EvidenceError("distinct units produced a colliding capture identity")
    return {"schema": "mineocclude-capture-contract-preflight-v0.1",
            "units_checked": len(checked), "capture_spec_sha256_by_unit": checked,
            "required_fields": list(CAPTURE_SPEC_REQUIRED_FIELDS), "verified": True}


# --------------------------------------------------------------------------
# Non-scientific operational startup smoke
#
# The previous provenance chain reached FROZEN_VERIFIED while
# minecraft_started_by_receipt_generation=false: it proved Java, display,
# package and renderer identity, but never started the apparatus, so it could
# not see a missing xdotool, a broken v0.2->v0.1 spec contract, or a startup
# that leaks a server. This control exercises the real startup path and then
# tears it down.
#
# It is emphatically not collection. The classification below is the tripwire:
# the Stage-1 evidence builder refuses any receipt carrying it, and the smoke
# runs under its own namespace so its artifacts cannot be confused for units.
# --------------------------------------------------------------------------

# The provenance identity assumed when a caller names none. Deliberately the
# predecessor's: a v0.3 receipt carries a v0.3 identifier, so a v0.3 runner that
# forgot to pass its own identity is refused by this gate rather than quietly
# accepting whatever receipt it was handed. Callers get their identity from
# ``package_binding.PackageBinding.provenance_artifact_id``.
DEFAULT_PREOUTCOME_PROVENANCE_ARTIFACT_ID = (
    "regime-a-prime-prospective-pre-outcome-provenance-v0.2")

OPERATIONAL_SMOKE_CLASSIFICATION = "NON_SCIENTIFIC_OPERATIONAL_SMOKE"
OPERATIONAL_SMOKE_NAMESPACE_SUFFIX = "-nonscientific-operational-smoke"
OPERATIONAL_SMOKE_ARTIFACT_ID = "regime-a-prime-nonscientific-operational-smoke-v0.1"
# v0.1 was a set of self-asserted booleans; refusing it by schema is what stops
# an older hand-written PASS document from authorizing a successor campaign.
OPERATIONAL_SMOKE_SCHEMA = "mineocclude-operational-smoke-v0.2"

# The geometry the production capture display is started with, in
# provision_capture_runtime_sagemaker.sh start_display:
#   Xvfb "$display" -screen 0 640x360x24 ...
# A smoke that ran against any other geometry did not exercise the real capture
# display, so it cannot stand in for one.
OPERATIONAL_SMOKE_DISPLAY_GEOMETRY = "640x360x24"
OPERATIONAL_SMOKE_DISPLAY_WIDTH = 640
OPERATIONAL_SMOKE_DISPLAY_HEIGHT = 360
OPERATIONAL_SMOKE_DISPLAY_DEPTH = 24

# Each stage of the startup, with the log marker that proves it happened. The
# markers are the same strings launch_runtime waits on, so the smoke cannot
# claim a stage the real startup path would not have accepted.
OPERATIONAL_SMOKE_STAGES: tuple[tuple[str, str], ...] = (
    ("display_ready", "640x360"),
    ("server_ready", "server ready"),
    ("client_joined", "joined the game"),
    # The startspec handshake. This marker is the server's own arming line, and
    # it is unreachable unless NoiseSchedule.load accepted the materialized
    # schedule against the episode seed the startspec line carried. An episode
    # that armed on the java.util.Random fallback prints a different rng source
    # and fails here, so the marker proves a real schedule was verified rather
    # than merely that an episode started.
    ("episode_armed", "rng=immutable_numpy_schedule"),
    ("teardown", "teardown_complete"),
)

OPERATIONAL_SMOKE_HANDSHAKE_SCHEMA = "mineocclude-startspec-handshake-v0.1"

# An ENCODING tolerance, not a scientific threshold. The frozen authority
# serializes camera coordinates to 10 decimal places while the runtime produces
# the exact binary64 `feet + (double) 1.62f`, so the declared and observed eye
# differ by ~3.2e-11. Mirrors CAMERA_ROUNDING_TOLERANCE in path_state_gate.
CAMERA_ENCODING_TOLERANCE = 1e-9

# A smoke that captured a frame, wrote a receipt, or put an object in the
# Stage-1 durable namespace is no longer a smoke. These stay zero by
# verification, not by assertion.
OPERATIONAL_SMOKE_ZERO_COUNTS = (
    "frames_captured", "scientific_receipts_written", "stage1_durable_objects_written",
)


def require_camera_apparatus_observation(smoke: Mapping[str, Any],
                                         apparatus_policy: Mapping[str, Any]) -> None:
    """Refuse a smoke that did not cross the camera apparatus identity contract.

    The v0.2 smoke exercised startspec, schedule acceptance and arming, then
    stopped. Everything after arming -- including the post-capture camera check
    -- was first executed by a governed launch, and a representation defect
    there blocked all 8 Stage-1 units after a full 180-tick capture: the
    verifier read ``server_state``'s ``player_y`` column as the camera FEET when
    ``EpisodeManager`` logs it as ``getEyeY()``, so the comparison was off by a
    constant 1.62f eye height while the apparatus sat exactly where this policy
    requires it. This verifier closes that gap before collection.

    Feet and eye are checked SEPARATELY and against their own declared values,
    which is the whole point: a check that derived one from the other would
    still have accepted the confusion that caused the block.

    The tolerance is an ENCODING tolerance, not a scientific threshold. The
    frozen authority serializes eye coordinates to 10 decimal places while the
    runtime produces the exact binary64 ``feet + (double) 1.62f``, so the two
    differ by ~3.2e-11. This matches ``CAMERA_ROUNDING_TOLERANCE`` in
    ``prospective/path_state_gate.py``.

    This reads a NON-SCIENTIFIC observation: ``observegeometry`` is a pure read
    that writes to ``mineocclude_observations/`` -- outside every scientific
    namespace -- and self-declares ``observation_only`` and
    ``scientific_use: forbidden``. Those self-declarations are verified here, so
    a document sourced from a capturing episode or from a mutating instrument is
    refused rather than accepted as a preflight.
    """
    observation = smoke.get("startspec_handshake", {})
    observation = observation.get("camera_apparatus_observation") if isinstance(
        observation, Mapping) else None
    if not isinstance(observation, Mapping):
        raise EvidenceError(
            "operational startup smoke carries no camera apparatus observation; a "
            "smoke that never observed the armed camera cannot show that the "
            "apparatus identity contract is satisfiable")

    # The instrument must be the non-scientific one, and it must not have been
    # read out of an episode that was already capturing.
    if observation.get("observation_only") is not True:
        raise EvidenceError("camera apparatus observation is not observation-only")
    if observation.get("scientific_use") != "forbidden":
        raise EvidenceError("camera apparatus observation is not marked scientific_use=forbidden")
    if observation.get("mutates_runtime_state") is not False:
        raise EvidenceError("camera apparatus observation claims to mutate runtime state")
    if observation.get("capturing") is not False:
        raise EvidenceError("camera apparatus observation was taken from a capturing episode")
    if observation.get("observed_player_count") != 1:
        raise EvidenceError("camera apparatus observation does not carry exactly one observed player")

    declared_feet = apparatus_policy["camera_feet_world_xyz"]
    declared_eye = apparatus_policy["camera_eye_world_xyz"]
    observed_feet = observation.get("observed_feet_xyz")
    observed_eye_y = observation.get("observed_eye_y")
    if (not isinstance(observed_feet, (list, tuple)) or len(observed_feet) != 3
            or not all(isinstance(value, (int, float)) and not isinstance(value, bool)
                       for value in observed_feet)):
        raise EvidenceError("camera apparatus observation carries no observed feet")
    if not isinstance(observed_eye_y, (int, float)) or isinstance(observed_eye_y, bool):
        raise EvidenceError("camera apparatus observation carries no observed eye height")
    if any(abs(float(observed) - float(declared)) > CAMERA_ENCODING_TOLERANCE
           for observed, declared in zip(observed_feet, declared_feet)):
        raise EvidenceError(
            f"observed camera feet {list(observed_feet)} do not satisfy the frozen "
            f"apparatus policy {list(declared_feet)}")
    if abs(float(observed_eye_y) - float(declared_eye[1])) > CAMERA_ENCODING_TOLERANCE:
        raise EvidenceError(
            f"observed camera eye height {observed_eye_y} does not satisfy the frozen "
            f"apparatus policy {declared_eye[1]}")
    # Feet and eye must be the SAME pose, not two independently satisfied
    # numbers: this is the eye/feet confusion, stated as an invariant.
    declared_offset = float(declared_eye[1]) - float(declared_feet[1])
    if abs((float(observed_eye_y) - float(observed_feet[1])) - declared_offset) > CAMERA_ENCODING_TOLERANCE:
        raise EvidenceError(
            "observed camera eye/feet offset does not match the frozen apparatus policy")

    yaw_pitch = apparatus_policy["yaw_pitch_degrees"]
    if [observation.get("observed_yaw_degrees"), observation.get("observed_pitch_degrees")] != list(yaw_pitch):
        raise EvidenceError("observed camera orientation does not satisfy the frozen apparatus policy")


def require_startspec_handshake(smoke: Mapping[str, Any]) -> None:
    """Refuse a smoke that did not actually cross the server seed contract.

    The v0.2 smoke built a capture context and stopped there, so it proved the
    Python side of the interface and nothing about what the server would accept.
    A startspec was never issued, and the seed-contract break that blocked
    Stage-1 attempt 02 therefore survived every prelaunch gate and was first seen
    by a real launch. This verifier closes that gap: the smoke must carry
    evidence that a startspec was issued and armed, and that evidence is
    re-derived rather than trusted.

    All three seeds are required to agree -- the value on the startspec line, the
    value the schedule was generated from, and the header of the materialized
    schedule bytes -- and the seed must appear in the server's own arming line,
    so a handshake record that names one seed while the apparatus armed another
    is refused.
    """
    handshake = smoke.get("startspec_handshake")
    if not isinstance(handshake, Mapping):
        raise EvidenceError(
            "operational startup smoke carries no startspec handshake; a smoke that "
            "never issued a startspec cannot detect a server-side contract break")
    if handshake.get("schema") != OPERATIONAL_SMOKE_HANDSHAKE_SCHEMA:
        raise EvidenceError(
            f"startspec handshake is not {OPERATIONAL_SMOKE_HANDSHAKE_SCHEMA}")

    seeds = {}
    for field in ("seed", "noise_seed", "schedule_seed_header"):
        value = handshake.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise EvidenceError(f"startspec handshake {field} is not a non-negative integer")
        seeds[field] = value
    if len(set(seeds.values())) != 1:
        raise EvidenceError(
            f"startspec handshake seeds disagree: {seeds}; the episode seed, the "
            "noise seed and the materialized schedule header must be one value")
    seed_value = seeds["seed"]

    episode_id = handshake.get("episode_id")
    if not isinstance(episode_id, int) or isinstance(episode_id, bool):
        raise EvidenceError("startspec handshake does not identify its episode")

    command = handshake.get("startspec_command")
    if not isinstance(command, str) or not command.startswith("mineocclude startspec "):
        raise EvidenceError("startspec handshake does not carry the startspec command")
    # Positional, because the server reads this line positionally: the seed is
    # the third argument after the literal, layout and episode id.
    fields = command.split()
    if len(fields) < 5 or fields[3] != str(episode_id) or fields[4] != str(seed_value):
        raise EvidenceError(
            "startspec handshake command does not carry the declared episode and seed")

    if handshake.get("armed") is not True:
        raise EvidenceError(
            f"startspec handshake did not arm: {handshake.get('refusal')!r}")
    if handshake.get("rng_source") != "immutable_numpy_schedule":
        raise EvidenceError(
            "startspec handshake did not arm on the immutable schedule "
            f"(rng_source={handshake.get('rng_source')!r})")
    armed_line = handshake.get("armed_log_line")
    if not isinstance(armed_line, str) or f"seed={seed_value}" not in armed_line:
        raise EvidenceError(
            "startspec handshake arming line does not carry the declared seed")
    if "rng=immutable_numpy_schedule" not in armed_line:
        raise EvidenceError(
            "startspec handshake arming line does not show the immutable schedule")

    # A handshake is not a capture. Both are verified as observations of the
    # apparatus, so a preflight that ran on into recording is refused outright
    # rather than relabelled as a smoke.
    if handshake.get("recording_started") is not False:
        raise EvidenceError("startspec handshake ran on into recording; that is a capture")
    if handshake.get("frames_written") != 0 or isinstance(handshake.get("frames_written"), bool):
        raise EvidenceError(
            f"startspec handshake wrote {handshake.get('frames_written')!r} frames")


def operational_smoke_namespace(run_namespace: str) -> str:
    return f"{run_namespace}{OPERATIONAL_SMOKE_NAMESPACE_SUFFIX}"


def _require_sha256_field(value: Any, label: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)):
        raise EvidenceError(f"{label} is not a lowercase SHA-256")
    return value


def require_operational_smoke(smoke: Mapping[str, Any], *, run_namespace: str,
                              source_commit: str | None = None,
                              closure_sha256: str | None = None) -> None:
    """Refuse authorization unless bound execution evidence replays.

    This deliberately verifies rather than trusts. The superseded version read a
    set of booleans -- ``server_started``, ``client_joined``, ``runtime_torn_down``
    -- straight out of the document, so a hand-written JSON file asserting PASS
    authorized a real campaign. Nothing here reads a boolean that describes what
    happened. Every claim is re-derived from evidence carried in the document:

      payload identity  ``payload_sha256`` is recomputed over the canonical body
                        with the field itself omitted, so any edit anywhere in
                        the document invalidates it.
      stage evidence    each stage carries the log excerpt it was concluded from
                        and that excerpt's digest. The digest is recomputed from
                        the excerpt bytes, and the stage's marker must actually
                        appear in the excerpt -- so a forged digest fails the
                        recomputation and a real digest over text that never
                        contained the marker fails the marker check.
      ordering          stages must be monotonic in the recorded clock, so
                        evidence cannot be reassembled out of the order the
                        startup can physically produce.
      display           geometry must be the production 640x360x24, and the
                        smoke must have owned the display it ran on.
      counts            frames, receipts and Stage-1 durable writes must be zero.

    This raises forgery from "write a JSON file" to "fabricate an internally
    consistent execution record whose every digest, marker and ordering agrees".
    It is emphatically NOT a cryptographic signature: the digests are computed
    over evidence the same document carries, so an author with the code in front
    of them can still construct a consistent fake. Defeating that needs a signing
    key or an external witness, neither of which exists here, and this docstring
    is the honest statement of that limit rather than a claim it does not apply.
    """
    if not isinstance(smoke, Mapping):
        raise EvidenceError("operational startup smoke evidence is absent")

    # Schema first: a v0.1 boolean document must be refused as a format, not
    # silently re-interpreted against the fields v0.2 happens to share with it.
    if smoke.get("schema") != OPERATIONAL_SMOKE_SCHEMA:
        raise EvidenceError(
            f"operational startup smoke is not {OPERATIONAL_SMOKE_SCHEMA} "
            "(a self-asserted v0.1 smoke cannot authorize a campaign)")

    identity = {
        "artifact_id": OPERATIONAL_SMOKE_ARTIFACT_ID,
        "classification": OPERATIONAL_SMOKE_CLASSIFICATION,
        "run_namespace": operational_smoke_namespace(run_namespace),
        "scientific_evidence": False,
        "counts_toward_stage1_units": False,
        "status": "PASS",
    }
    for key, value in identity.items():
        if smoke.get(key) != value:
            raise EvidenceError(f"operational startup smoke rejects {key}")

    # Payload identity. Recomputed over everything else in the document, so a
    # mutated field without a recomputed digest is caught here.
    declared = _require_sha256_field(smoke.get("payload_sha256"), "payload_sha256")
    if canonical_payload_sha256(smoke, omit="payload_sha256") != declared:
        raise EvidenceError("operational startup smoke payload_sha256 does not reproduce")

    if source_commit is not None and smoke.get("source_commit") != source_commit:
        raise EvidenceError("operational startup smoke was not produced at this commit")
    if closure_sha256 is not None and smoke.get(
            "runtime_critical_source_closure_sha256") != closure_sha256:
        raise EvidenceError(
            "operational startup smoke is not bound to this runtime-critical closure")

    # Java identity: the apparatus is a JVM, so which java ran is material.
    java = smoke.get("java_executable")
    if not isinstance(java, Mapping) or not java.get("path"):
        raise EvidenceError("operational startup smoke does not identify the Java executable")
    _require_sha256_field(java.get("sha256"), "java_executable.sha256")

    # Display: the production capture geometry, owned by this smoke.
    display = smoke.get("display")
    if not isinstance(display, Mapping):
        raise EvidenceError("operational startup smoke does not identify the display")
    if display.get("geometry") != OPERATIONAL_SMOKE_DISPLAY_GEOMETRY:
        raise EvidenceError(
            f"operational startup smoke display geometry is not "
            f"{OPERATIONAL_SMOKE_DISPLAY_GEOMETRY}: {display.get('geometry')!r}")
    # Independently confirmed by xdpyinfo against the live server, so a document
    # that merely names the right geometry string still has to agree with what
    # the X server reported.
    if (display.get("xdpyinfo_width") != OPERATIONAL_SMOKE_DISPLAY_WIDTH
            or display.get("xdpyinfo_height") != OPERATIONAL_SMOKE_DISPLAY_HEIGHT
            or display.get("xdpyinfo_depth") != OPERATIONAL_SMOKE_DISPLAY_DEPTH):
        raise EvidenceError(
            "operational startup smoke display was not confirmed as "
            f"{OPERATIONAL_SMOKE_DISPLAY_GEOMETRY} by xdpyinfo")
    if display.get("started_by_smoke") is not True:
        raise EvidenceError(
            "operational startup smoke did not start its own display; a pre-existing "
            "generic display does not exercise the production Xvfb startup path")
    if not display.get("name"):
        raise EvidenceError("operational startup smoke does not name the display")

    # openbox is part of the production start_display path; a smoke that skipped
    # it did not exercise that path.
    openbox = smoke.get("openbox")
    if not isinstance(openbox, Mapping) or openbox.get("started_by_smoke") is not True:
        raise EvidenceError("operational startup smoke did not start openbox")

    # Stage evidence: digests recomputed, markers required, ordering enforced.
    evidence = smoke.get("stage_evidence")
    if not isinstance(evidence, Mapping):
        raise EvidenceError("operational startup smoke carries no stage evidence")
    expected_stages = [name for name, _ in OPERATIONAL_SMOKE_STAGES]
    if set(evidence) != set(expected_stages):
        raise EvidenceError(
            f"operational startup smoke stage evidence must cover exactly {expected_stages}")
    previous = None
    for stage, marker in OPERATIONAL_SMOKE_STAGES:
        entry = evidence[stage]
        if not isinstance(entry, Mapping):
            raise EvidenceError(f"stage evidence for {stage} is malformed")
        excerpt = entry.get("excerpt")
        if not isinstance(excerpt, str) or not excerpt:
            raise EvidenceError(f"stage evidence for {stage} carries no excerpt")
        declared_digest = _require_sha256_field(entry.get("excerpt_sha256"),
                                                f"{stage}.excerpt_sha256")
        if hashlib.sha256(excerpt.encode("utf-8")).hexdigest() != declared_digest:
            raise EvidenceError(f"stage evidence for {stage} does not match its digest")
        if marker not in excerpt:
            raise EvidenceError(
                f"stage evidence for {stage} does not contain the marker {marker!r}")
        if not entry.get("source_path"):
            raise EvidenceError(f"stage evidence for {stage} does not name its source")
        observed = entry.get("observed_monotonic")
        if not isinstance(observed, (int, float)) or isinstance(observed, bool):
            raise EvidenceError(f"stage evidence for {stage} has no usable timestamp")
        if previous is not None and observed < previous:
            raise EvidenceError(
                f"operational startup smoke stages are out of order at {stage}")
        previous = observed

    # Teardown outcome: every process the smoke started must be gone.
    processes = smoke.get("launched_processes")
    if not isinstance(processes, list) or not processes:
        raise EvidenceError("operational startup smoke records no launched processes")
    for entry in processes:
        if not isinstance(entry, Mapping) or entry.get("pid") is None:
            raise EvidenceError("operational startup smoke process record is malformed")
        if entry.get("exited") is not True:
            raise EvidenceError(
                f"operational startup smoke left pid {entry.get('pid')} running")
    if smoke.get("stranded_processes") != []:
        raise EvidenceError("operational startup smoke stranded processes")
    if smoke.get("session_lock_present_after_teardown") is not False:
        raise EvidenceError("operational startup smoke left the world session.lock held")

    # The startspec handshake: the stage above proves the arming marker appeared,
    # this proves the identity it appeared under is the one the smoke declares.
    require_startspec_handshake(smoke)

    # Non-collection: verified as counts, so a smoke that actually captured
    # something is refused rather than relabelled.
    for field in OPERATIONAL_SMOKE_ZERO_COUNTS:
        value = smoke.get(field)
        if value != 0 or isinstance(value, bool):
            raise EvidenceError(
                f"operational startup smoke is not non-scientific: {field}={value!r}")


def refuse_operational_smoke_as_evidence(document: Mapping[str, Any], label: str) -> None:
    """Structural barrier: smoke output can never enter Stage-1 evidence.

    Checked by identity and namespace rather than by file location, so renaming
    or relocating a smoke artifact does not launder it into a scientific unit.
    """
    if not isinstance(document, Mapping):
        return
    namespace = str(document.get("run_namespace", ""))
    if (document.get("classification") == OPERATIONAL_SMOKE_CLASSIFICATION
            or document.get("artifact_id") == OPERATIONAL_SMOKE_ARTIFACT_ID
            or document.get("scientific_evidence") is False
            or namespace.endswith(OPERATIONAL_SMOKE_NAMESPACE_SUFFIX)):
        raise EvidenceError(
            f"{label} is non-scientific operational smoke and cannot be Stage-1 evidence")


def stage_run_inventory_sha256(manifest: Mapping[str, Any]) -> str:
    """Digest of exactly which units a stage is allowed to run.

    An authorization that binds only the manifest SHA still authorizes whatever
    that manifest happens to say. Binding the inventory separately means a
    receipt cannot be carried to a differently-populated run, and it is what the
    launch gate compares against the manifest actually loaded.
    """
    units = manifest.get("units")
    if not isinstance(units, list) or not units:
        raise EvidenceError("manifest declares no units to inventory")
    inventory = [{"unit_id": unit.get("unit_id"),
                  "scientific_run_id": unit.get("scientific_run_id"),
                  "receipt_path": unit.get("receipt_path"),
                  "command": unit.get("command")}
                 for unit in sorted(units, key=lambda item: str(item.get("unit_id")))]
    return hashlib.sha256(canonical_json_bytes(inventory)).hexdigest()


def runtime_critical_source_closure_sha256(repository: Path = REPOSITORY_ROOT) -> str:
    """Single digest over every runtime-critical source file's current bytes.

    Lets one field in a receipt stand for the whole apparatus source closure
    while remaining recomputable from disk, so a receipt cannot be carried
    across a source edit.
    """
    closure = {relative: sha256_file(repository / relative)
               for relative in RUNTIME_CRITICAL_SOURCE_PATHS}
    return hashlib.sha256(canonical_json_bytes(closure)).hexdigest()


def require_stage_manifest_binding(stage: str, manifest: Mapping[str, Any], *,
                                   manifest_path: Path, authority: Mapping[str, Any],
                                   unit: Mapping[str, Any] | None = None,
                                   repository: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    """Bind a requested stage to its manifest, namespace, unit role, and receipt type.

    ``--stage stage1-capture --manifest stage2_locked_manifest.json`` previously
    reached capture: the stage string selected which authorization receipt to
    look for, but nothing tied it to the manifest that was actually loaded, so a
    Stage-1 authorization could drive Stage-2 units. Every entrypoint -- direct,
    delegated, backend, and restart/resume -- routes through this function
    before any capture or extraction, and it refuses on the first disagreement
    between the requested stage and:

    * the manifest's own ``artifact_id`` and declared location;
    * the manifest's ``run_namespace``;
    * the unit's ``scientific_run_id`` namespace;
    * the stage the unit's own locked command declares;
    * the collection the unit is allowed to be drawn from.

    Returns the resolved binding, including the authorization and pre-outcome
    provenance ``artifact_id``s the caller must then require, so no call site
    re-spells either as a literal.
    """
    policy = authority.get("stage_binding_policy")
    if not isinstance(policy, Mapping) or not isinstance(policy.get("stages"), Mapping):
        raise PermissionError("authority declares no stage binding policy")
    binding = policy["stages"].get(stage)
    if not isinstance(binding, Mapping):
        raise PermissionError(f"stage is not declared by the frozen authority: {stage!r}")
    if manifest.get("artifact_id") != binding["manifest_artifact_id"]:
        raise PermissionError(
            f"stage {stage} requires manifest {binding['manifest_artifact_id']!r}, "
            f"got {manifest.get('artifact_id')!r}")
    try:
        relative = manifest_path.resolve().relative_to(repository.resolve()).as_posix()
    except ValueError as exc:
        raise PermissionError(f"manifest lies outside the repository: {manifest_path}") from exc
    if relative != binding["manifest_relative_path"]:
        raise PermissionError(
            f"stage {stage} manifest must be {binding['manifest_relative_path']}, got {relative}")
    if manifest.get("run_namespace") != binding["run_namespace"]:
        raise PermissionError(f"stage {stage} run namespace mismatch")
    # The authority declares no provenance identity of its own, so it is derived
    # from the version this stage's declared identities carry -- and those two
    # must agree, or the stage table is itself mixing packages.
    manifest_version = artifact_version_tag(binding["manifest_artifact_id"])
    authorization_version = artifact_version_tag(binding["authorization_artifact_id"])
    if manifest_version != authorization_version:
        raise PermissionError(
            f"stage {stage} binds a {manifest_version} manifest to an "
            f"{authorization_version} authorization")
    resolved = {"stage": stage, "stage_role": binding["stage_role"],
                "run_namespace": binding["run_namespace"],
                "authorization_artifact_id": binding["authorization_artifact_id"],
                # Carried here for the same reason the authorization identity is:
                # the unit driver omitted it, and so checked a v0.3 provenance
                # receipt against the deliberately fail-closed v0.2 default.
                "provenance_artifact_id": provenance_artifact_id_for(manifest_version),
                "manifest_sha256": sha256_file(manifest_path)}
    if unit is None:
        return resolved
    if unit.get("scientific_run_id") != binding["run_namespace"]:
        raise PermissionError(
            f"unit {unit.get('unit_id')!r} belongs to namespace "
            f"{unit.get('scientific_run_id')!r}, not to stage {stage}")
    command = unit.get("command")
    if not isinstance(command, list) or "--stage" not in command:
        raise PermissionError(f"unit {unit.get('unit_id')!r} declares no locked stage")
    declared = command[command.index("--stage") + 1] if command.index("--stage") + 1 < len(command) else None
    if declared != stage:
        raise PermissionError(
            f"unit {unit.get('unit_id')!r} is a {declared!r} unit, not a {stage!r} unit")
    collections = binding.get("unit_collections")
    if not isinstance(collections, list) or not collections:
        raise PermissionError(f"stage {stage} declares no unit collections")
    members = {item.get("unit_id") for name in collections
               for item in manifest.get(name, []) if isinstance(item, Mapping)}
    if unit.get("unit_id") not in members:
        raise PermissionError(
            f"unit {unit.get('unit_id')!r} is not a member of the {stage} unit collections")
    resolved["unit_id"] = unit.get("unit_id")
    resolved["unit_role"] = binding["unit_role"]
    return resolved


def resolve_qualified_runtime(authority: Mapping[str, Any], *,
                              environment: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Reconstruct the pinned JDK/display runtime without trusting shell state.

    ``java`` is not on this environment's default PATH, and overlay-installed
    components may not survive a Space rebuild, so the qualified interpreter is
    located from the authority's own ``runtime_reconstruction.java_home`` pin and
    invoked by absolute path. A ``java`` inherited from PATH is an unpinned
    runtime whose bytes are not the bytes the probe evidence records, so it is
    never used. Fails closed when the pinned JDK is absent.
    """
    policy = authority.get("runtime_identity_policy")
    if not isinstance(policy, Mapping):
        raise EvidenceError("authority has no runtime identity policy")
    reconstruction = policy.get("runtime_reconstruction")
    if not isinstance(reconstruction, Mapping):
        raise EvidenceError("authority declares no runtime reconstruction procedure")
    java_home = reconstruction.get("java_home")
    relative = reconstruction.get("java_executable_relative_path")
    if not isinstance(java_home, str) or not java_home.startswith("/") or not isinstance(relative, str):
        raise EvidenceError("authority runtime reconstruction pins are unusable")
    executable = Path(java_home) / relative
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise EvidenceError(
            f"qualified JDK is absent from its pinned location: {executable}. "
            "See runtime_identity_policy.runtime_reconstruction.reinstall_procedure.")
    inherited = dict(os.environ if environment is None else environment)
    display = reconstruction.get("display")
    resolved = {**inherited, "JAVA_HOME": java_home,
                "PATH": f"{Path(java_home) / 'bin'}:{inherited.get('PATH', '')}".rstrip(":")}
    if isinstance(display, str) and display:
        resolved["DISPLAY"] = display
    return {"java_executable": str(executable), "java_home": java_home,
            "display": resolved.get("DISPLAY"), "environment": resolved}


def verify_receipt_payload_digest(receipt: Mapping[str, Any], name: str) -> None:
    """Check a receipt's internal integrity digest.

    This is a deterministic SHA-256 over the receipt's own canonical JSON. It is
    NOT a signature: there is no asymmetric key and no authenticated signer, so
    it proves only that the receipt has not been edited since it was assembled.
    It says nothing about whether a probe ran. Callers that need probe evidence
    must additionally call :func:`verify_probe_execution`.
    """
    if not isinstance(receipt, Mapping):
        raise EvidenceError(f"{name} is not a receipt object")
    if receipt.get("status") != "PASS":
        raise EvidenceError(f"{name} is not PASS evidence")
    claimed = receipt.get("payload_sha256")
    if not isinstance(claimed, str) or claimed != canonical_payload_sha256(
            receipt, omit="payload_sha256"):
        raise EvidenceError(f"{name} payload digest mismatch")


def runtime_probe_identity_tokens(fields: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    """Derive, from the authority alone, the tokens each probe output must contain.

    Shared by the probe and by the verifier so neither can declare its own
    acceptance criteria. The renderer pin is a compound
    ``"<renderer> LLVM <version>"`` string that no single line of ``glxinfo``
    reproduces verbatim, so it is split into the tokens that do appear.
    """
    try:
        renderer_name, llvm_version = str(fields["renderer"]).rsplit(" LLVM ", 1)
        return {
            "java_version": (str(fields["java"]),),
            "renderer": (renderer_name, f"LLVM {llvm_version}", str(fields["mesa"])),
            "xvfb": (str(fields["xvfb"]),),
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise EvidenceError(f"authority runtime identity pins are unusable: {exc}") from exc


def probe_evidence_digest(execution: Mapping[str, Any]) -> str:
    """Deterministic SHA-256 over a probe-execution record's canonical JSON."""
    return hashlib.sha256(canonical_json_bytes(dict(execution))).hexdigest()


def verify_probe_execution(receipt: Mapping[str, Any], name: str, *,
                           authority: Mapping[str, Any],
                           repository: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    """Require concrete evidence that an independent probe process actually ran.

    The superseded ``verify_signed_probe`` accepted any document carrying
    ``status=PASS``, ``independently_derived=true``,
    ``asserted_by_evidence_builder=false`` and a hash of itself. Every one of
    those is a self-assertion: the evidence builder could -- and structurally
    did -- emit them without any probe existing. Nothing distinguished a real
    measurement from a dictionary literal.

    A receipt now passes only if it carries a ``probe_execution`` record that is
    reproducible from concrete verifier inputs:

    A. probe source identity        -- a runtime-critical source path whose
                                       bytes on disk are rehashed here;
    B. exact invocation identity    -- argv, resolved executable, working
                                       directory, for every required probe;
    C. process exit status          -- must be zero for every invocation;
    D. observed normalized output   -- rehashed here, and required to carry the
                                       authority's own identity tokens;
    E. runtime executable identity  -- the executable's absolute path is
                                       rehashed from disk;
    F. apparatus measurements       -- compared to the authority pins;
    G. runtime-critical source hashes -- byte-level, via the independent
                                       :func:`verify_runtime_source_hashes`;
    H. receipt binding              -- the record's digest is bound into the
                                       receipt, and the receipt's own payload
                                       digest covers that binding.

    The digest is named for what it is. It is a deterministic cryptographic
    digest over independently generated probe evidence, not a signature.
    """
    verify_receipt_payload_digest(receipt, name)
    policy = authority.get("runtime_identity_policy")
    if not isinstance(policy, Mapping):
        raise EvidenceError("authority has no runtime identity policy")
    probe_policy = policy.get("probe_evidence_policy")
    if not isinstance(probe_policy, Mapping):
        raise EvidenceError("authority declares no probe evidence policy")
    fields = policy.get("required_fields")
    if not isinstance(fields, Mapping) or not fields:
        raise EvidenceError("authority has no runtime identity pins")

    execution = receipt.get("probe_execution")
    if not isinstance(execution, Mapping):
        raise EvidenceError(
            f"{name} carries no probe execution record, so its PASS is self-asserted")
    claimed = receipt.get("probe_evidence_sha256")
    if not isinstance(claimed, str) or claimed != probe_evidence_digest(execution):
        raise EvidenceError(f"{name} probe evidence digest mismatch")

    # A. Probe source identity. The producer must be an authority-declared
    # independent probe, never the evidence builder, and its source bytes are
    # rehashed from disk rather than taken from the record.
    producers = probe_policy.get("independent_probe_producers")
    forbidden = probe_policy.get("forbidden_probe_producers")
    if not isinstance(producers, list) or not producers or not isinstance(forbidden, list):
        raise EvidenceError("authority probe producer allow-list is unusable")
    producer = execution.get("producer")
    if producer not in producers or producer in forbidden:
        raise EvidenceError(f"{name} was not produced by an independent probe: {producer!r}")
    source_relative = execution.get("probe_source_path")
    if source_relative not in RUNTIME_CRITICAL_SOURCE_PATHS:
        raise EvidenceError(f"{name} probe source is not a runtime-critical source")
    source_path = repository / str(source_relative)
    declared_source = _sha(execution.get("probe_source_sha256"), "probe source SHA")
    if not source_path.is_file() or sha256_file(source_path) != declared_source:
        raise EvidenceError(f"{name} probe source bytes differ from the verified tree")

    # B-E. Every required invocation, its exit status, its executable, and its
    # normalized output.
    tokens = runtime_probe_identity_tokens(fields)
    required_ids = probe_policy.get("required_invocation_ids")
    if not isinstance(required_ids, list) or set(required_ids) != set(tokens):
        raise EvidenceError("authority required probe invocations do not match its pins")
    invocations = execution.get("invocations")
    if not isinstance(invocations, list):
        raise EvidenceError(f"{name} probe execution record has no invocations")
    by_id = {item.get("command_id"): item for item in invocations if isinstance(item, Mapping)}
    if len(by_id) != len(invocations) or set(by_id) != set(required_ids):
        raise EvidenceError(f"{name} probe invocation coverage is incomplete")
    for command_id in sorted(required_ids):
        invocation = by_id[command_id]
        argv = invocation.get("argv")
        if (not isinstance(argv, list) or not argv
                or not all(isinstance(value, str) and value for value in argv)):
            raise EvidenceError(f"{name} invocation {command_id} has no command identity")
        executable = invocation.get("executable_path")
        if not isinstance(executable, str) or not executable.startswith("/") or executable != argv[0]:
            raise EvidenceError(
                f"{name} invocation {command_id} does not resolve argv[0] to an absolute executable")
        declared_executable = _sha(invocation.get("executable_sha256"),
                                   f"{command_id} executable SHA")
        executable_path = Path(executable)
        if not executable_path.is_file() or sha256_file(executable_path) != declared_executable:
            raise EvidenceError(
                f"{name} invocation {command_id} executable bytes differ from the probed runtime")
        if command_id == "java_version":
            # The JDK must be the pinned one, invoked by absolute path. A `java`
            # resolved from an inherited PATH is an unpinned runtime, and this
            # environment has no `java` on PATH at all.
            reconstruction = policy.get("runtime_reconstruction")
            if not isinstance(reconstruction, Mapping):
                raise EvidenceError("authority declares no runtime reconstruction procedure")
            pinned = str(Path(str(reconstruction.get("java_home", "")))
                         / str(reconstruction.get("java_executable_relative_path", "")))
            if executable != pinned:
                raise EvidenceError(
                    f"{name} probed {executable} rather than the pinned JDK {pinned}")
        if invocation.get("exit_status") != 0:
            raise EvidenceError(
                f"{name} invocation {command_id} exited {invocation.get('exit_status')!r}")
        output = invocation.get("normalized_output")
        if not isinstance(output, str) or not output:
            raise EvidenceError(f"{name} invocation {command_id} recorded no output")
        if hashlib.sha256(output.encode()).hexdigest() != _sha(
                invocation.get("normalized_output_sha256"), f"{command_id} output SHA"):
            raise EvidenceError(f"{name} invocation {command_id} output digest mismatch")
        missing = [token for token in tokens[command_id] if token not in output]
        if missing:
            raise EvidenceError(
                f"{name} invocation {command_id} output lacks authority identity tokens {missing}")

    # F. Apparatus/runtime measurements, against the authority's own pins and
    # against the files on disk.
    pins = policy.get("critical_file_sha256")
    paths = policy.get("critical_file_paths")
    if not isinstance(pins, Mapping) or not isinstance(paths, Mapping) or set(pins) != set(paths):
        raise EvidenceError("authority apparatus pins are incomplete")
    measured = execution.get("apparatus_file_sha256")
    if not isinstance(measured, Mapping) or set(measured) != set(pins):
        raise EvidenceError(f"{name} apparatus hash coverage is incomplete")
    for key, pinned in pins.items():
        if measured.get(key) != pinned:
            raise EvidenceError(f"{name} apparatus pin mismatch: {key}")
        location = Path(str(paths[key]))
        located = location if location.is_absolute() else repository / location
        if not located.is_file() or sha256_file(located) != pinned:
            raise EvidenceError(f"{name} apparatus bytes differ from the pinned artefact: {key}")

    # G. Independent byte-level runtime source control, retained unchanged.
    verify_runtime_source_hashes(execution.get("runtime_source_sha256"), repository=repository)

    # H. The record must describe the same runtime the receipt reports.
    for key in sorted(fields):
        if execution.get("measurements", {}).get(key) != receipt.get(key):
            raise EvidenceError(f"{name} probe record and receipt disagree on {key}")
    return {"status": "PASS", "producer": producer,
            "probe_evidence_sha256": claimed,
            "invocations_verified": sorted(required_ids)}


@dataclass(frozen=True)
class Decision:
    status: str
    gates: dict[str, Any]
    reasons: tuple[str, ...]

    def to_dict(self, *, authority_sha256: str, manifest_sha256: str,
                evidence_sha256: str, artifact_id: str) -> dict[str, Any]:
        """Serialize the decision under the identity of the experiment it judged.

        ``artifact_id`` is required and unvalidated-by-default nowhere: every
        caller derives it with
        :func:`package_binding.stage1_decision_artifact_id` from the Stage-1
        manifest that was actually evaluated. It used to be the literal
        ``regime-a-prime-stage1-decision-v0.2``, which made every v0.3 decision
        claim the predecessor's identity.
        """
        if not isinstance(artifact_id, str) or not artifact_id:
            raise EvidenceError("Stage-1 decision artifact identity is missing")
        return {
            "schema_version": "1.1", "artifact_id": artifact_id,
            "classification": "DEVELOPMENT_ONLY", "status": self.status,
            "authority_sha256": _sha(authority_sha256, "authority_sha256"),
            "stage1_manifest_sha256": _sha(manifest_sha256, "stage1_manifest_sha256"),
            "stage1_evidence_sha256": _sha(evidence_sha256, "stage1_evidence_sha256"),
            "gates": self.gates, "reasons": list(self.reasons),
            "stage2_collection_authorized": False,
            "confirmatory_interpretation_authorized": False,
        }


class Stage1Evaluator:
    """Evaluate measured Stage-1 evidence without inventing thresholds."""

    PROHIBITED = (
        "point_visible", "partial_transition", "detector_visible", "clock_unresolved",
        "out_of_support", "ambiguous_or_invalid_identity", "runtime_or_provenance_unresolved",
        "path_state_invalid", "malformed_or_missing",
    )

    def __init__(self, authority: Mapping[str, Any], manifest: Mapping[str, Any], *,
                 authority_sha256: str, manifest_sha256: str):
        self.authority = authority
        self.manifest = manifest
        self.policy = authority["stage1_policy"]
        self.authority_sha256 = _sha(authority_sha256, "authority SHA")
        self.manifest_sha256 = _sha(manifest_sha256, "Stage-1 manifest SHA")
        self.extent_truth = self._extent_truth_binding()

    def _extent_truth_binding(self) -> dict[str, Any] | None:
        """Bind the v0.3 extent truth predicate, or ``None`` under v0.2.

        The predicate is selected by what the *authority* declares, never by a
        flag on the evidence, so a v0.2 package keeps its v0.2 semantics and a
        v0.3 package cannot silently fall back to the superseded band logic.
        """
        visibility = self.policy.get("visibility", {})
        if visibility.get("primary_predicate") != EXTENT_TRUTH_PREDICATE:
            return None
        extent = visibility.get("target_extent")
        classification = visibility.get("extent_classification")
        wall_spec = self.authority.get("apparatus", {}).get("wall_geometry_as_built")
        if not isinstance(extent, dict) or not isinstance(classification, dict) \
                or not isinstance(wall_spec, dict):
            raise EvidenceError(
                "authority declares the extent truth predicate but omits its target "
                "extent, classification policy or as-built wall geometry")
        half = _number(extent.get("half_width_blocks"), "target_extent.half_width_blocks")
        # The declared extent must be exactly what the pinned client jar's model
        # geometry yields. A package that ships a hand-edited scalar -- in either
        # direction -- fails closed here rather than quietly scoring against it.
        if half != TARGET_EXTENT_HALF_BLOCKS:
            raise EvidenceError(
                "declared target extent does not reproduce the renderer-model "
                f"derivation: {half!r} != {TARGET_EXTENT_HALF_BLOCKS!r}")
        if extent.get("detector_derived") is not False or extent.get("outcome_derived") is not False:
            raise EvidenceError("target extent must be declared detector- and outcome-independent")
        samples = _integer(classification.get("samples_per_axis"),
                           "extent_classification.samples_per_axis", minimum=2)
        apparatus = self.authority["apparatus"]
        return {
            "half_extent": half,
            "samples_per_axis": samples,
            "camera": tuple(apparatus["camera_eye_world_xyz"]),
            "target_centre_y": _number(apparatus.get("target_centre_world_y"),
                                       "apparatus.target_centre_world_y"),
            "lane_world_z": _number(apparatus.get("lane_world_z"), "apparatus.lane_world_z"),
            "wall": WallGeometry(
                wall_axis=wall_spec["wall_axis"],
                wall_ortho=_number(wall_spec.get("wall_ortho"), "wall_ortho"),
                wall_axis_min=_number(wall_spec.get("wall_axis_min"), "wall_axis_min"),
                wall_axis_max=_number(wall_spec.get("wall_axis_max"), "wall_axis_max"),
                wall_y_min=_number(wall_spec.get("wall_y_min"), "wall_y_min"),
                wall_y_max=_number(wall_spec.get("wall_y_max"), "wall_y_max"),
                half=_number(wall_spec.get("ortho_half_thickness"), "ortho_half_thickness"),
                present=True),
        }

    def classify_extent_row(self, world_x: float, scene: str) -> ExtentClass:
        """Detector-independent extent class for one row.

        Reads only the frozen apparatus geometry and the row's aligned position.
        It is deliberately given no access to the sample dict, so no future edit
        can let ``detector_visible`` reach the truth predicate.
        """
        binding = self.extent_truth
        if binding is None:
            raise EvidenceError("authority does not declare the extent truth predicate")
        wall = binding["wall"] if scene == "WALL" else replace(binding["wall"], present=False)
        return classify_extent(
            binding["camera"],
            (world_x, binding["target_centre_y"], binding["lane_world_z"]),
            wall,
            half_extent=binding["half_extent"],
            samples_per_axis=binding["samples_per_axis"])

    def derive_transition_measurement(self, samples: Sequence[Mapping[str, Any]],
                                      scene: str) -> dict[str, Any]:
        """Derive one direction's transition block from a run's own rows.

        Public for the same reason as :meth:`expected_regime`: the Stage-1
        evidence builder emits this block and the evaluator re-derives it and
        demands equality, so there must be exactly one derivation. Under
        ``134a242`` there were two, and the builder's still spoke the v0.2
        point/band schema while the evaluator expected the v0.3 extent schema.

        ONLY rows whose aligned physical position is resolved may enter an
        interval derivation. A finite raw ``world_x`` is not a substitute: over
        the causal-FIR warm-up prefix the raw coordinate exists while the aligned
        one does not, and admitting it drags the derived interval toward the lane
        extremes.
        """
        admissible = [(_number(sample.get("world_x"), "world_x"), sample)
                      for sample in samples
                      if sample.get("temporal_alignment_resolved") is True]
        if not admissible:
            raise EvidenceError("transition measurement has no temporally aligned rows")
        rendered_absent = [x for x, sample in admissible
                           if sample.get("detector_visible") is False]
        if self.extent_truth is not None:
            # v0.3: the interval is GEOMETRIC. The detector-absent interval is
            # still reported -- it is how the rendered detector's response across
            # the geometric transition is calibrated -- but it no longer defines
            # any boundary that held-out truth depends on.
            extent_hidden = [x for x, _ in admissible
                             if self.classify_extent_row(x, scene)
                             is ExtentClass.EXTENT_FULLY_OCCLUDED]
            extent_visible = [x for x, _ in admissible
                              if self.classify_extent_row(x, scene)
                              is ExtentClass.EXTENT_FULLY_VISIBLE]
            if not extent_hidden or not extent_visible:
                raise EvidenceError(
                    "transition measurement lacks fully-occluded or fully-visible extent rows")
            if not rendered_absent:
                raise EvidenceError("transition measurement lacks detector-absent rows")
            occluded = [min(extent_hidden), max(extent_hidden)]
            return {
                "extent_fully_occluded_world_x_interval": occluded,
                "rendered_detector_absent_world_x_interval":
                    [min(rendered_absent), max(rendered_absent)],
                "geometric_extent_transition_world_x_intervals":
                    [[min(x for x, _ in admissible), occluded[0]],
                     [occluded[1], max(x for x, _ in admissible)]],
                "aligned_rows_admitted": len(admissible),
                "rows_excluded_unaligned": len(samples) - len(admissible),
                "derivation": "EXTENT_GEOMETRY_ON_ALIGNED_ROWS_ONLY",
                "detector_defines_held_out_truth": False,
            }
        lane_min, lane_max = self.authority["apparatus"]["lane_world_x_blocks"]
        geometric_hidden = [x for x, sample in admissible
                            if sample.get("point_visible") is False]
        if not geometric_hidden or not rendered_absent:
            raise EvidenceError("transition measurement lacks point-hidden or detector-absent rows")
        geometric = [min(geometric_hidden), max(geometric_hidden)]
        rendered = [min(rendered_absent), max(rendered_absent)]
        stable_hidden = [max(geometric[0], rendered[0]), min(geometric[1], rendered[1])]
        if stable_hidden[0] >= stable_hidden[1]:
            raise EvidenceError("transition measurement has no stable-hidden intersection")
        partial_intervals = [[min(geometric[0], rendered[0]), stable_hidden[0]],
                             [stable_hidden[1], max(geometric[1], rendered[1])]]
        return {
            "geometric_point_hidden_world_x_interval": geometric,
            "rendered_detector_absent_world_x_interval": rendered,
            "stable_occluded_world_x_interval": stable_hidden,
            "partial_transition_world_x_intervals": partial_intervals,
            "stable_visible_world_x_intervals": [[lane_min, partial_intervals[0][0]],
                                                 [partial_intervals[1][1], lane_max]],
        }

    def designated_hidden_row_indices(self, regimes: Sequence[str], *,
                                      scene: str, design_role: str) -> list[int]:
        """Reproduce the frozen FIRST_N designated hidden-row schedule.

        The rule itself is unchanged and deliberately conservative:
        ``FIRST_N_QUALIFIED_STABLE_OCCLUDED_ROWS_IN_ASCENDING_MODEL_FRAME_ORDER``.
        What was wrong at ``134a242`` was the *pool* it was applied to -- the
        builder selected over its stale v0.2 point-stable rows, so its LTR
        schedule began at frame 38 where the extent-stable pool begins at 47.
        Builder and evaluator now select from the same authority-selected pool by
        calling this one method.
        """
        if self.policy["contamination"].get(
                "designated_hidden_row_selection_rule") != DESIGNATED_HIDDEN_ROW_SELECTION_RULE:
            raise EvidenceError("authority does not bind a designated hidden-row schedule")
        required = (self.policy["contamination"]["required_hidden_rows_per_wall_validation_run"]
                    if scene == "WALL" and design_role == "HELD_OUT_VALIDATION" else 0)
        return [index for index, name in enumerate(regimes)
                if name == "stable_occluded"][:required]

    def _validate_manifest_design(self) -> None:
        fixed = self.authority["fixed_development_configuration"]
        # The expected manifest identity is whatever the authority's own stage
        # binding names, so a v0.3 package is not scored against a v0.2 artifact
        # id -- and, more importantly, a manifest from the wrong authority
        # version is still refused rather than accepted by a loosened check.
        expected_manifest_id = (self.authority.get("stage_binding_policy", {})
                                .get("stages", {}).get("stage1-capture", {})
                                .get("manifest_artifact_id"))
        if not isinstance(expected_manifest_id, str) or not expected_manifest_id:
            raise EvidenceError("authority does not bind a Stage-1 manifest artifact id")
        if (self.manifest.get("artifact_id") != expected_manifest_id
                or self.manifest.get("classification") != "DEVELOPMENT_ONLY"
                or self.manifest.get("STAGE_1_COLLECTION_AUTHORIZED") is not False
                or self.manifest.get("STAGE_2_COLLECTION_AUTHORIZED") is not False
                or self.manifest.get("confirmatory_collection_authorized") is not False
                or self.manifest.get("source_commit_binding")
                   != "BOUND_AT_LAUNCH_BY_PREOUTCOME_PROVENANCE_RECEIPT"):
            raise EvidenceError("Stage-1 manifest authority boundary is invalid")
        if self.manifest.get("authority_binding", {}).get("sha256") != self.authority_sha256:
            raise EvidenceError("Stage-1 manifest authority SHA mismatch")
        units = self.manifest.get("units")
        if not isinstance(units, list) or len(units) != self.policy["run_count"]:
            raise EvidenceError("Stage-1 manifest run count mismatch")
        roles = self.policy["replicate_roles"]
        expected_cells = {(direction, scene, int(replicate), role)
                          for direction in self.policy["directions"]
                          for scene in self.policy["scenes"]
                          for replicate, role in roles.items()}
        observed_cells: set[tuple[Any, ...]] = set()
        unit_ids: list[str] = []
        episode_ids: list[int] = []
        for unit in units:
            if not isinstance(unit, dict):
                raise EvidenceError("Stage-1 manifest unit is malformed")
            unit_id = unit.get("unit_id")
            if not isinstance(unit_id, str) or not unit_id:
                raise EvidenceError("Stage-1 unit identity is malformed")
            unit_ids.append(unit_id)
            episode_ids.append(_integer(unit.get("episode_id"), "episode_id", minimum=0))
            _integer(unit.get("seed"), "seed", minimum=0)
            _integer(unit.get("noise_seed"), "noise_seed", minimum=0)
            # One seed identity per unit. Checked at manifest validation too, so a
            # manifest the apparatus could never arm is refused at its structure
            # rather than only when a spec is derived from it.
            require_server_seed_contract(unit)
            replicate = _integer(unit.get("replicate"), "replicate", minimum=1)
            observed_cells.add((unit.get("direction"), unit.get("scene"), replicate,
                                unit.get("design_role")))
            if (unit.get("speed_blocks_per_second") != fixed["speed_blocks_per_second"]
                    or unit.get("motion_noise_q") != fixed["motion_noise_q"]
                    or unit.get("start_world_x") != fixed["start_world_x_by_direction"].get(
                        unit.get("direction"))
                    or unit.get("expected_frames") != fixed["expected_frames_per_run"]
                    or unit.get("confirmatory_membership") is not False
                    or unit.get("scientific_run_id") != self.manifest.get("run_namespace")):
                raise EvidenceError(f"Stage-1 unit {unit_id} overrides authority")
            command = unit.get("command")
            if (not isinstance(command, list) or "--stage" not in command
                    or command[command.index("--stage") + 1:command.index("--stage") + 2]
                       != ["stage1-capture"]
                    or "--unit-id" not in command
                    or command[command.index("--unit-id") + 1:command.index("--unit-id") + 2]
                       != [unit_id]):
                raise EvidenceError(f"Stage-1 unit {unit_id} command is not locked")
        if (observed_cells != expected_cells or len(set(unit_ids)) != len(unit_ids)
                or len(set(episode_ids)) != len(episode_ids)):
            raise EvidenceError("Stage-1 manifest allocation is incomplete or ambiguous")

    def _clock_coordinates_ok(self, item: Mapping[str, Any], expected_ids: set[str],
                              observed: Mapping[str, Any]) -> bool:
        """Derive unit-spaced clock coordinates from raw tick/frame identities.

        ``unit_spaced_clock_coordinates`` cannot be a bare Boolean: the evidence
        must carry the server-tick and model-frame identities the property is
        derived from, so the flag can be independently reproduced and cannot be
        mutated without also forging the coordinates underneath it.
        """
        cadence = _integer(self.authority["apparatus"]["server_ticks_per_model_frame"],
                           "server_ticks_per_model_frame", minimum=1)
        coordinates = item.get("clock_coordinate_evidence")
        if not isinstance(coordinates, dict) or set(coordinates) != set(expected_ids):
            return False
        derived = True
        for unit_id in sorted(expected_ids):
            entry = coordinates.get(unit_id)
            run = observed.get(unit_id)
            if not isinstance(entry, dict) or not isinstance(run, dict):
                return False
            ticks = entry.get("server_state_ticks")
            frames = entry.get("render_model_frame_indices")
            samples = run.get("visibility_samples")
            if (not isinstance(ticks, list) or not isinstance(frames, list)
                    or not isinstance(samples, list) or len(ticks) != len(samples)
                    or len(frames) != len(samples) or len(samples) < 2):
                return False
            tick_values, frame_values = (
                [_integer(value, "clock coordinate", minimum=0) for value in series]
                for series in (ticks, frames))
            derived &= all(later - earlier == 1
                           for earlier, later in zip(frame_values, frame_values[1:]))
            derived &= all(later - earlier == cadence
                           for earlier, later in zip(tick_values, tick_values[1:]))
            # The frozen clock-domain authority fixes the server-tick to
            # model-frame cadence; the two coordinate series must advance in
            # lockstep at exactly that ratio, whatever their common origin.
            derived &= all(tick - tick_values[0] == cadence * (frame - frame_values[0])
                           for tick, frame in zip(tick_values, frame_values, strict=True))
        return item.get("unit_spaced_clock_coordinates") is derived and derived

    def _gate(self, gates: dict[str, Any], name: str, passed: bool, detail: Any,
              reasons: list[str]) -> None:
        gates[name] = {"status": "PASS" if passed else "FAIL", "detail": detail}
        if not passed:
            reasons.append(name)

    def evaluate(self, evidence: Mapping[str, Any]) -> Decision:
        gates: dict[str, Any] = {}
        reasons: list[str] = []
        try:
            self._evaluate(evidence, gates, reasons)
        except (KeyError, TypeError, EvidenceError, ValueError) as exc:
            reasons.append(f"MALFORMED_EVIDENCE: {exc}")
            gates.setdefault("evidence_integrity", {"status": "FAIL", "detail": str(exc)})
        failed = any(value.get("status") != "PASS" for value in gates.values())
        return Decision("FAIL" if failed else "PASS", gates, tuple(reasons))

    def expected_regime(self, sample: Mapping[str, Any], unit: Mapping[str, Any],
                        bounds: Mapping[str, Any]) -> str:
        """Classify one row under whichever truth predicate the authority selects.

        Public because it is the *only* row classifier in the repository. The
        Stage-1 evidence builder calls this exact method rather than keeping a
        hand-copied twin, which is what produced the ``134a242`` failure: the
        builder stayed on v0.2 point/band semantics while the authority moved to
        v0.3 rendered-extent semantics, and 166 rows the evaluator called
        ``partial_transition`` were labelled stable by the builder. Divergence is
        now unrepresentable -- there is nothing left to diverge from.
        """
        required_booleans = ("point_visible", "detector_visible", "render_frame_present",
            "projected_in_frame", "temporal_alignment_resolved", "identity_valid", "in_support",
            "runtime_provenance_resolved", "path_state_valid", "malformed_or_missing")
        if any(type(sample.get(name)) is not bool for name in required_booleans):
            raise EvidenceError("visibility row has missing or non-Boolean physical evidence")
        frame_pixels = sample.get("projection_frame_pixels")
        token_grid = sample.get("projection_token_grid")
        if (frame_pixels != self.authority["apparatus"].get("canonical_frame_pixels")
                or token_grid != self.authority["apparatus"].get("visual_token_grid")):
            raise EvidenceError("projection dimensions are absent or not bound to authority")
        derived_projection = derive_projection_validity(
            sample, frame_pixels=frame_pixels, token_grid=token_grid)
        if sample["projected_in_frame"] is not derived_projection:
            raise EvidenceError("projected_in_frame contradicts bound raw coordinates")
        required_true = ("temporal_alignment_resolved", "identity_valid", "in_support",
            "render_frame_present", "runtime_provenance_resolved", "path_state_valid")
        if sample["malformed_or_missing"] or any(sample[name] is not True for name in required_true):
            return "unresolved"
        if sample.get("point_visible") is not True and unit["scene"] == "NO_WALL":
            return "unresolved"
        if sample.get("projected_in_frame") is not True:
            return "unresolved"
        if self.extent_truth is not None:
            # v0.3: classify this row directly from geometry. No detector output,
            # no detector edge and no band transferred from another replicate
            # participates. NO_WALL still resolves through the same call -- with
            # no occluder present -- rather than short-circuiting, so both scenes
            # share one predicate.
            x = _number(sample.get("world_x"), "world_x")
            return self.classify_extent_row(x, unit["scene"]).regime
        if unit["scene"] == "NO_WALL":
            return "stable_visible"
        x = _number(sample.get("world_x"), "world_x")
        hidden = bounds.get("stable_occluded_world_x_interval")
        partial = bounds.get("partial_transition_world_x_intervals")
        visible = bounds.get("stable_visible_world_x_intervals")
        if not (isinstance(hidden, list) and len(hidden) == 2
                and isinstance(partial, list) and len(partial) == 2
                and isinstance(visible, list) and len(visible) == 2):
            raise EvidenceError("measured transition intervals are malformed")
        # The truth predicate must not read the detector it is used to score.
        # Requiring detector_visible=False here made a row "hidden" only once the
        # detector already agreed it was hidden, so the false-positive count was
        # identically zero by construction. Membership of the physically
        # qualified stable-occluded interval is decided by server-side geometry
        # and the transition band measured on the independent, predeclared
        # TRANSITION_MEASUREMENT replicates -- never by the scored detector. A
        # detector firing through this interval is now a false positive.
        in_hidden = _number(hidden[0], "hidden low") <= x <= _number(hidden[1], "hidden high")
        # The measured bands are closed on their own endpoints. Those endpoints
        # ARE observed rows -- the outer one is the extreme point-hidden sample
        # and the inner one is the extreme detector-absent sample -- so a strict
        # test left both band edges in no class at all.
        in_partial = any(
            _number(interval[0], "partial low") <= x <= _number(interval[1], "partial high")
            for interval in partial)
        in_visible = any(
            _number(interval[0], "visible low") <= x <= _number(interval[1], "visible high")
            for interval in visible)
        if in_hidden and sample["point_visible"] is False:
            return "stable_occluded"
        if in_partial:
            return "partial_transition"
        if in_visible and sample["point_visible"] is True:
            return "stable_visible"
        # Server-side point visibility and the band measured on the predeclared
        # TRANSITION_MEASUREMENT replicate disagree on this row. That is the
        # definition of a transition row, not an unclassifiable one: the band is
        # measured on a different replicate, so its edges never fall on exactly
        # the same aligned coordinate twice, and treating the disagreement as
        # "unresolved" made required_evidence_completeness unsatisfiable by any
        # physically correct held-out run. Nothing is scored more leniently --
        # partial rows are reported and never scored, exactly as before -- and
        # the >=60 stable samples per direction per class minimum, plus the
        # positive stable-occluded qualification required of every designated
        # hidden row, still refuse a run that empties a scored class this way.
        if in_hidden or in_visible:
            return "partial_transition"
        return "unresolved"

    def _evaluate(self, evidence: Mapping[str, Any], gates: dict[str, Any], reasons: list[str]) -> None:
        self._validate_manifest_design()
        if evidence.get("schema_version") != "1.1":
            raise EvidenceError("unsupported evidence schema_version")
        if evidence.get("authority_sha256") != self.authority_sha256:
            raise EvidenceError("evidence authority binding mismatch")
        if evidence.get("stage1_manifest_sha256") != self.manifest_sha256:
            raise EvidenceError("evidence Stage-1 manifest binding mismatch")
        expected = {unit["unit_id"]: unit for unit in self.manifest["units"]}
        runs = evidence.get("runs")
        if not isinstance(runs, list):
            raise EvidenceError("runs must be a list")
        observed = {row.get("unit_id"): row for row in runs if isinstance(row, dict)}
        complete = len(observed) == len(runs) and set(observed) == set(expected)
        self._gate(gates, "unit_completeness", complete,
                   {"expected": len(expected), "observed": len(observed)}, reasons)

        transitions = evidence.get("transition_measurement_by_direction")
        if not isinstance(transitions, dict):
            raise EvidenceError("transition measurement is missing")
        transition_ok = set(transitions) == set(self.policy["directions"])
        for direction, item in transitions.items():
            required_units = {u["unit_id"] for u in expected.values() if u["direction"] == direction
                              and u["scene"] == "WALL" and u["design_role"] == "TRANSITION_MEASUREMENT"}
            transition_ok &= item.get("status") == "MEASURED" and set(item.get("measurement_unit_ids", [])) == required_units
            if self.extent_truth is not None:
                # v0.3 reports a geometric occlusion interval plus the detector's
                # response across it. The detector interval is calibration
                # evidence; it defines no boundary held-out truth depends on, and
                # the evidence must say so rather than leave it implied.
                occluded = item.get("extent_fully_occluded_world_x_interval")
                rendered = item.get("rendered_detector_absent_world_x_interval")
                transition_ok &= isinstance(occluded, list) and len(occluded) == 2
                transition_ok &= isinstance(rendered, list) and len(rendered) == 2
                transition_ok &= item.get("detector_defines_held_out_truth") is False
                transition_ok &= item.get("derivation") == "EXTENT_GEOMETRY_ON_ALIGNED_ROWS_ONLY"
            else:
                hidden = item.get("stable_occluded_world_x_interval")
                partial = item.get("partial_transition_world_x_intervals")
                visible = item.get("stable_visible_world_x_intervals")
                transition_ok &= isinstance(hidden, list) and len(hidden) == 2
                transition_ok &= isinstance(partial, list) and len(partial) == 2
                transition_ok &= isinstance(visible, list) and len(visible) == 2
        unit_ok = complete
        support_ok = complete
        support: dict[str, Any] = {}
        # Structured subconditions for the two gates whose ``134a242`` failures
        # were diagnostically misleading. Neither gate's acceptance criterion
        # changes: these record WHICH conjunct failed, so a scientific
        # cleanliness failure can no longer read as a runtime/storage failure,
        # and a pure regime disagreement can no longer read as broken
        # world-coordinate arithmetic.
        support_subconditions: dict[str, Any] = {}
        unit_subconditions: dict[str, Any] = {}
        derived_transitions: dict[str, dict[str, Any]] = {}
        detector = {d: {"visible": [], "hidden": [], "partial": 0} for d in self.policy["directions"]}
        calibration = {d: {"visible": [], "units": []} for d in self.policy["directions"]}
        contamination_total = 0
        contamination_detail: dict[str, Any] = {}
        support_ledger: dict[str, Any] = {}
        completeness_ok = complete
        maximum_lag = _integer(
            self.policy["temporal_alignment"]["maximum_lag_ticks_for_estimation"],
            "maximum_lag_ticks_for_estimation", minimum=1)
        lane_min, lane_max = self.authority["apparatus"]["lane_world_x_blocks"]
        wall_origin = self.authority["apparatus"]["wall_relative_origin_world_x"]
        for unit_id, spec in expected.items():
            if unit_id not in observed:
                continue
            row = observed[unit_id]
            identity_ok = all(row.get(key) == spec.get(key)
                              for key in ("direction", "scene", "speed_blocks_per_second"))
            frame_count_ok = (_integer(row.get("frame_count"), f"{unit_id}.frame_count")
                              == spec["expected_frames"])
            unit_ok &= identity_ok
            unit_ok &= frame_count_ok
            receipt_pass: dict[str, bool] = {}
            for receipt_name in ("runtime_provenance_receipt", "path_state_receipt", "durability_receipt"):
                receipt = row.get(receipt_name)
                if not isinstance(receipt, dict):
                    unit_ok = False
                    receipt_pass[receipt_name] = False
                    continue
                try:
                    verify_receipt_payload_digest(receipt, receipt_name)
                    if (receipt.get("independently_derived") is not True
                            or receipt.get("asserted_by_evidence_builder") is not False):
                        # Declared metadata only. These two booleans are not
                        # evidence of anything -- the runtime receipt's actual
                        # independence is established by verify_probe_execution
                        # below, and the other two receipts by their own
                        # byte-level reproductions.
                        raise EvidenceError(f"{receipt_name} does not declare independent derivation")
                    if receipt_name == "runtime_provenance_receipt":
                        verify_runtime_identity(self.authority["runtime_identity_policy"], receipt)
                        # Concrete proof that an independent probe process ran:
                        # source identity, argv, exit status, normalized output,
                        # executable bytes, apparatus pins, source closure.
                        verify_probe_execution(receipt, receipt_name, authority=self.authority)
                        for probe_hash in ("java_version_probe_sha256", "renderer_probe_sha256",
                                           "xvfb_probe_sha256"):
                            _sha(receipt.get(probe_hash), probe_hash)
                        source_hashes = receipt.get("runtime_source_sha256")
                        verify_runtime_source_hashes(source_hashes)
                        apparatus = receipt.get("captured_apparatus_receipt")
                        if not isinstance(apparatus, dict):
                            raise EvidenceError("captured apparatus receipt is missing")
                        verify_receipt_payload_digest(apparatus, "captured apparatus receipt")
                        apparatus_policy = self.authority["apparatus_observation_policy"]
                        apparatus_expected = {
                            "camera_feet_world_xyz": apparatus_policy["camera_feet_world_xyz"],
                            "camera_eye_world_xyz": apparatus_policy["camera_eye_world_xyz"],
                            "yaw_pitch_degrees": apparatus_policy["yaw_pitch_degrees"],
                            "fov_degrees": apparatus_policy["fov_degrees"],
                            "canonical_frame_pixels": apparatus_policy["canonical_frame_pixels"],
                            "target_respawn_count": apparatus_policy["target_respawn_count"],
                            "layout_id": self.authority["apparatus"]["layout_id"],
                            "camera_authority": self.authority["apparatus"]["camera_authority"],
                            "wall_authority": self.authority["apparatus"]["wall_authority"],
                            "scene": spec["scene"], "wall_layout_physical_evidence": "PASS",
                        }
                        if any(apparatus.get(key) != value for key, value in apparatus_expected.items()):
                            raise EvidenceError("captured apparatus identity mismatch")
                        if not isinstance(apparatus.get("target_entity_uuid"), str) or not apparatus["target_entity_uuid"]:
                            raise EvidenceError("captured target identity is missing")
                    elif receipt_name == "path_state_receipt":
                        if (receipt.get("unit_id") != unit_id
                                or _integer(receipt.get("frame_count"), "path frame_count", minimum=1)
                                   != spec["expected_frames"]
                                or receipt.get("exact_binary64_path_match") is not True
                                or _sha(receipt.get("captured_path_sha256"), "captured path SHA")
                                   != _sha(receipt.get("expected_path_sha256"), "expected path SHA")):
                            raise EvidenceError("path/state evidence mismatch")
                    else:
                        expected_uri = self.manifest["durable_prefix"].rstrip("/") + "/" + unit_id
                        if (receipt.get("unit_id") != unit_id or receipt.get("durable_uri") != expected_uri
                                or _integer(receipt.get("remote_object_count"),
                                            "remote object count", minimum=1) < 1):
                            raise EvidenceError("durability evidence mismatch")
                        _sha(receipt.get("remote_checksum_manifest_sha256"), "remote manifest SHA")
                    receipt_pass[receipt_name] = True
                except (EvidenceError, KeyError, TypeError, ValueError):
                    receipt_pass[receipt_name] = False
                    unit_ok = False

            samples = row.get("visibility_samples")
            if not isinstance(samples, list) or len(samples) != spec["expected_frames"]:
                raise EvidenceError(f"{unit_id} visibility sample coverage mismatch")
            xs: list[float] = []
            rels: list[float] = []
            regimes: list[str] = []
            unresolved_indices: list[int] = []
            required_evidence_failures = {name: 0 for name in (
                "malformed_or_missing", "identity_valid", "in_support", "path_state_valid",
                "runtime_provenance_resolved", "render_frame_present")}
            alignment_unresolved: list[int] = []
            wall_relative_violations: list[int] = []
            world_support_violations: list[int] = []
            regime_mismatches: list[dict[str, Any]] = []
            for index, sample in enumerate(samples):
                if not isinstance(sample, dict):
                    raise EvidenceError("visibility sample must be an object")
                x = _number(sample.get("world_x"), "world_x")
                relative = _number(sample.get("wall_relative_x"), "wall_relative_x")
                if relative != x - wall_origin:
                    wall_relative_violations.append(index)
                    support_ok = False
                xs.append(x); rels.append(relative)
                in_support = lane_min <= x <= lane_max and sample.get("in_support") is True
                if not in_support:
                    world_support_violations.append(index)
                support_ok &= in_support
                expected_regime = self.expected_regime(sample, spec, transitions[spec["direction"]])
                if sample.get("regime") != expected_regime:
                    # The single most valuable diagnostic this evaluator can
                    # emit: at 134a242 every one of the 166 mismatches was a
                    # builder "stable_*" against an evaluator "partial_transition",
                    # which named the stale-builder root cause outright -- but the
                    # gate reported only a wall of world_x/wall_relative_x extrema.
                    if len(regime_mismatches) < 20:
                        regime_mismatches.append({"index": index,
                            "reported": sample.get("regime"), "expected": expected_regime})
                    support_ok = False
                regimes.append(expected_regime)
                # Required apparatus evidence must be resolved on every frame of
                # every unit; there is no legitimate reason for a captured frame
                # to carry invalid identity, absent render, broken path/state or
                # unresolved runtime provenance, so these fail closed.
                required_evidence_failures["malformed_or_missing"] += int(
                    sample["malformed_or_missing"])
                for name in ("identity_valid", "in_support", "path_state_valid",
                             "runtime_provenance_resolved", "render_frame_present"):
                    required_evidence_failures[name] += int(sample[name] is not True)
                if sample["temporal_alignment_resolved"] is not True:
                    alignment_unresolved.append(index)
                if expected_regime == "unresolved":
                    unresolved_indices.append(index)
                detected = sample.get("detector_visible")
                if type(detected) is not bool:
                    raise EvidenceError("detector_visible must be Boolean")
                if spec["design_role"] == "HELD_OUT_VALIDATION":
                    if expected_regime == "stable_visible": detector[spec["direction"]]["visible"].append(detected)
                    elif expected_regime == "stable_occluded": detector[spec["direction"]]["hidden"].append(detected)
                    elif expected_regime == "partial_transition": detector[spec["direction"]]["partial"] += 1
                elif expected_regime == "stable_visible":
                    # Calibration/transition-measurement evidence is required
                    # evidence too: a run whose rendered detector never fires
                    # across its qualified visible rows cannot be allowed to pass
                    # merely because it is not the held-out replicate.
                    calibration[spec["direction"]]["visible"].append(detected)
            if spec["design_role"] != "HELD_OUT_VALIDATION":
                calibration[spec["direction"]]["units"].append(unit_id)
            # A frame may only remain unresolved for a prospectively expected
            # reason: it precedes a complete causal FIR history, or the target
            # projects outside the canonical frame. Every other frame must land
            # in a physical regime, so "unresolved" cannot absorb contradictory
            # or unusable evidence as an unbounded budget.
            excusable_unresolved = {index for index in range(len(samples))
                                    if index < maximum_lag
                                    or samples[index].get("projected_in_frame") is not True}
            unexcused = [index for index in unresolved_indices if index not in excusable_unresolved]
            expected_alignment_unresolved = list(range(maximum_lag))
            unit_complete = (not unexcused
                             and all(value == 0 for value in required_evidence_failures.values())
                             and alignment_unresolved == expected_alignment_unresolved)
            completeness_ok &= unit_complete
            support_ledger[unit_id] = {
                "required_evidence_failures": required_evidence_failures,
                "alignment_unresolved_indices": alignment_unresolved,
                "expected_alignment_unresolved_indices": expected_alignment_unresolved,
                "unresolved_frame_count": len(unresolved_indices),
                "unexcused_unresolved_indices": unexcused,
                "projection_out_of_frame_count": sum(
                    1 for sample in samples if sample.get("projected_in_frame") is not True),
                "regime_counts": {name: regimes.count(name) for name in (
                    "stable_visible", "stable_occluded", "partial_transition", "unresolved")},
                "complete": unit_complete,
            }
            if spec["scene"] == "WALL" and spec["design_role"] == "TRANSITION_MEASUREMENT":
                derived_transitions[spec["direction"]] = self.derive_transition_measurement(
                    samples, spec["scene"])
            support[f"{spec['direction']}/{spec['scene']}/{spec['replicate']}"] = {
                "world_x": {"minimum": min(xs), "maximum": max(xs),
                            "maximum_gap": max((b-a for a,b in zip(sorted(xs), sorted(xs)[1:])), default=0.0)},
                "wall_relative_x": {"minimum": min(rels), "maximum": max(rels),
                                    "maximum_gap": max((b-a for a,b in zip(sorted(rels), sorted(rels)[1:])), default=0.0)},
                "measurement_only_no_numeric_acceptance_cutoff": True,
            }
            support_subconditions[unit_id] = {
                "WORLD_COORDINATE_SUPPORT_OK": not world_support_violations,
                "WALL_RELATIVE_ARITHMETIC_OK": not wall_relative_violations,
                "REGIME_CONSISTENCY_OK": not regime_mismatches,
                "world_coordinate_support_violation_count": len(world_support_violations),
                "wall_relative_arithmetic_violation_count": len(wall_relative_violations),
                "regime_mismatch_count": sum(1 for index, sample in enumerate(samples)
                                             if sample.get("regime") != regimes[index]),
                "regime_mismatch_examples": regime_mismatches,
            }
            summary = row.get("hidden_row_contamination")
            if not isinstance(summary, dict):
                raise EvidenceError("hidden-row contamination enumeration is missing")
            required_hidden = (self.policy["contamination"]["required_hidden_rows_per_wall_validation_run"]
                               if spec["scene"] == "WALL" and spec["design_role"] == "HELD_OUT_VALIDATION" else 0)
            raw_indices = row.get("designated_hidden_row_indices")
            if not isinstance(raw_indices, list):
                raise EvidenceError("designated hidden-row identities are missing")
            indices = [_integer(value, "designated_hidden_row_index", minimum=0) for value in raw_indices]
            if len(set(indices)) != len(indices) or any(index >= len(samples) for index in indices):
                raise EvidenceError("designated hidden-row identities are duplicate or out of range")
            # Designated rows are not selectable after observing the run: they
            # are reproduced here from the frozen selection rule applied to the
            # measured regimes, so substituting the last N qualified rows for the
            # first N fails even though both are individually qualified.
            scheduled_indices = self.designated_hidden_row_indices(
                regimes, scene=spec["scene"], design_role=spec["design_role"])
            reproduces_schedule = indices == scheduled_indices
            derived = {name: 0 for name in self.PROHIBITED}
            # A designated hidden row must POSITIVELY qualify as stable-occluded.
            # Counting only prohibited classes is fail-open: a row outside the
            # measured stable-occluded interval with point_visible=False and
            # detector_visible=False classifies as "unresolved", scores zero on
            # every prohibited class, and would otherwise be accepted as hidden.
            qualified_hidden = 0
            for index in indices:
                sample = samples[index]
                expected_regime = regimes[index]
                qualified_hidden += int(expected_regime == "stable_occluded"
                                        and sample["regime"] == "stable_occluded")
                derived["point_visible"] += int(sample["point_visible"])
                derived["partial_transition"] += int(expected_regime == "partial_transition"
                    or sample["regime"] == "partial_transition")
                derived["detector_visible"] += int(sample["detector_visible"])
                derived["clock_unresolved"] += int(not sample["temporal_alignment_resolved"])
                derived["out_of_support"] += int(not sample["in_support"])
                derived["ambiguous_or_invalid_identity"] += int(not sample["identity_valid"])
                derived["runtime_or_provenance_unresolved"] += int(
                    not sample["runtime_provenance_resolved"]
                    or not receipt_pass.get("runtime_provenance_receipt", False)
                    or not receipt_pass.get("durability_receipt", False))
                derived["path_state_invalid"] += int(
                    not sample["path_state_valid"] or not receipt_pass.get("path_state_receipt", False))
                derived["malformed_or_missing"] += int(sample["malformed_or_missing"])
            reported = summary.get("prohibited_counts")
            reported_count = _integer(summary.get("designated_hidden_row_count"),
                                      "designated_hidden_row_count", minimum=0)
            summaries_match = (isinstance(reported, dict) and set(reported) == set(self.PROHIBITED)
                and all(_integer(reported.get(name), f"contamination.{name}", minimum=0) == derived[name]
                        for name in self.PROHIBITED))
            observed_hidden = len(indices)
            clean = (observed_hidden == required_hidden == reported_count
                     and qualified_hidden == required_hidden and reproduces_schedule
                     and summaries_match and all(value == 0 for value in derived.values()))
            contamination_total += (sum(derived.values()) + (required_hidden - qualified_hidden)
                                    + int(not reproduces_schedule))
            contamination_detail[unit_id] = {"required": required_hidden, "observed": observed_hidden,
                "derived_prohibited_counts": derived, "reported_summary_matches": summaries_match,
                "stable_occluded_qualified_rows": qualified_hidden,
                "reproduces_frozen_row_schedule": reproduces_schedule,
                "scheduled_hidden_row_indices": scheduled_indices, "clean": clean}
            unit_ok &= clean
            # The 134a242 report showed unit_identity_runtime_path_durability
            # FAIL on all eight units when identity, frame count, runtime
            # provenance, path state and durability had each individually
            # passed -- the gate failed only through ``clean``, a scientific
            # cleanliness property. These subconditions separate the two so a
            # contamination failure never again reads as a storage failure.
            unit_subconditions[unit_id] = {
                "IDENTITY_OK": identity_ok,
                "FRAME_COUNT_OK": frame_count_ok,
                "RUNTIME_PROVENANCE_OK": receipt_pass.get("runtime_provenance_receipt", False),
                "PATH_STATE_OK": receipt_pass.get("path_state_receipt", False),
                "DURABILITY_OK": receipt_pass.get("durability_receipt", False),
                "CONTAMINATION_CLEAN": clean,
            }
        for direction in self.policy["directions"]:
            reported = transitions.get(direction, {})
            derived = derived_transitions.get(direction)
            transition_ok &= derived is not None and all(
                reported.get(key) == value for key, value in (derived or {}).items())
        self._gate(gates, "prospective_transition_measurement", transition_ok,
                   {"reported": transitions, "derived_from_rows": derived_transitions}, reasons)
        self._gate(gates, "unit_identity_runtime_path_durability", unit_ok,
                   {"units": len(observed), "subconditions_by_unit": unit_subconditions,
                    "failing_subconditions": sorted({
                        name for item in unit_subconditions.values()
                        for name, passed in item.items() if not passed})}, reasons)
        self._gate(gates, "calibration_world_and_wall_relative_support", support_ok,
                   {"support": support, "subconditions_by_unit": support_subconditions,
                    "failing_subconditions": sorted({
                        name for item in support_subconditions.values()
                        for name, passed in item.items()
                        if isinstance(passed, bool) and not passed})}, reasons)
        self._gate(gates, "hidden_row_contamination", contamination_total == 0 and unit_ok,
                   contamination_detail, reasons)

        detector_ok = True
        detector_detail: dict[str, Any] = {}
        minimum = self.policy["visibility"]["minimum_stable_samples_per_direction_per_class"]
        for direction, values in detector.items():
            visible, hidden = values["visible"], values["hidden"]
            fp, fn = sum(hidden), sum(not value for value in visible)
            passed = len(visible) >= minimum and len(hidden) >= minimum and fp == 0 and fn == 0
            if self.policy["visibility"].get("partial_transition_observation_required_on_held_out_wall") is True:
                passed &= values["partial"] > 0
            detector_ok &= passed
            detector_detail[direction] = {"stable_visible_n": len(visible), "stable_occluded_n": len(hidden),
                "partial_n_reported_not_scored": values["partial"], "false_positive": fp, "false_negative": fn}
        self._gate(gates, "stable_visibility_base_rate_robust", detector_ok, detector_detail, reasons)

        calibration_ok = True
        calibration_detail: dict[str, Any] = {}
        for direction, values in calibration.items():
            responses = values["visible"]
            missed = sum(not value for value in responses)
            passed = len(responses) >= minimum and missed == 0
            calibration_ok &= passed
            calibration_detail[direction] = {"units": values["units"],
                "qualified_visible_n": len(responses), "detector_absent_n": missed,
                "minimum_required": minimum}
        self._gate(gates, "calibration_detector_response", calibration_ok, calibration_detail, reasons)
        self._gate(gates, "required_evidence_completeness", completeness_ok, support_ledger, reasons)

        alignments = evidence.get("alignment_by_direction")
        if not isinstance(alignments, dict):
            raise EvidenceError("alignment_by_direction must be an object")
        temporal = self.policy["temporal_alignment"]
        if temporal.get("agreement_rule") != AGREEMENT_RULE:
            raise EvidenceError("unsupported or missing authority-supplied temporal agreement rule")
        required_methods = set(temporal["required_method_ids"])
        maximum_lag = _integer(temporal["maximum_lag_ticks_for_estimation"],
                               "maximum_lag_ticks_for_estimation", minimum=1)
        pure_delay_tolerance = _number(temporal["pure_delay_off_peak_mass_tolerance"],
                                       "pure_delay_off_peak_mass_tolerance")
        # The estimator's own parabolic-refinement clamp, supplied by the
        # authority rather than hard-coded here so a package that omits it fails
        # closed instead of silently adopting a bound nothing declared.
        refinement_bound = _number(
            temporal.get("cross_correlation_subtick_refinement_bound_ticks"),
            "cross_correlation_subtick_refinement_bound_ticks")
        if not 0.0 < refinement_bound <= 1.0:
            raise EvidenceError(
                "cross-correlation sub-tick refinement bound must be a positive "
                "fraction of a tick no larger than the estimator's own clamp")
        if temporal.get("pure_delay_interpretation_allowed") is not False:
            raise EvidenceError("authority must forbid a pure-delay interpretation")
        if temporal.get("causal_fir_must_beat_best_pure_delay_scope") != "EVERY_TRAJECTORY":
            raise EvidenceError("authority must bind the FIR improvement scope to every trajectory")
        alignment_ok = set(alignments) == set(self.policy["directions"])
        alignment_detail: dict[str, Any] = {}
        for direction in self.policy["directions"]:
            item = alignments.get(direction)
            if not isinstance(item, dict):
                alignment_ok = False; continue
            methods = item.get("methods")
            if not isinstance(methods, list):
                raise EvidenceError("temporal methods must be a list")
            by_id = {method.get("method_id"): method for method in methods if isinstance(method, dict)}
            passed = len(by_id) == len(methods) and set(by_id) == required_methods
            passed &= item.get("agreement_rule") == temporal["agreement_rule"]
            intervals: list[tuple[float, float]] = []
            point_estimates: dict[str, float] = {}
            per_trajectory_by_method: dict[str, list[Any]] = {}
            expected_ids = {unit["unit_id"] for unit in self.manifest["units"]
                            if unit["direction"] == direction}
            for method_id in sorted(required_methods):
                if method_id not in by_id:
                    passed = False
                    continue
                method = by_id[method_id]
                estimate = _number(method.get("estimate_ticks"), f"{method_id}.estimate")
                interval = method.get("confidence_interval_ticks")
                if not isinstance(interval, list) or len(interval) != 2:
                    raise EvidenceError(f"{method_id} confidence interval is missing")
                low, high = _number(interval[0], "interval low"), _number(interval[1], "interval high")
                trajectories = _integer(method.get("trajectory_count"), "trajectory_count", minimum=1)
                evidence_ids = method.get("trajectory_evidence_ids")
                per_trajectory = method.get("per_trajectory_estimates_ticks")
                receipt_bindings = method.get("trajectory_receipt_sha256")
                passed &= method.get("status") == "MEASURED" and low <= estimate <= high
                # Admissible causal lag range: acausal or unresolvable estimates
                # and intervals cannot support agreement, and this bounds the
                # usable interval width without a fabricated precision cutoff.
                passed &= 0.0 <= low and high <= float(maximum_lag)
                point_estimates[method_id] = estimate
                if isinstance(per_trajectory, list):
                    per_trajectory_by_method[method_id] = per_trajectory
                passed &= trajectories >= temporal["minimum_trajectories_per_direction"]
                passed &= isinstance(evidence_ids, list) and len(evidence_ids) == trajectories and len(set(evidence_ids)) == trajectories
                passed &= set(evidence_ids) == expected_ids
                passed &= isinstance(per_trajectory, list) and len(per_trajectory) == trajectories
                passed &= isinstance(receipt_bindings, dict) and set(receipt_bindings) == expected_ids
                if isinstance(receipt_bindings, dict):
                    for unit_id in expected_ids:
                        source_run = observed.get(unit_id, {})
                        passed &= (receipt_bindings.get(unit_id) == source_run.get("unit_receipt_sha256")
                                   and isinstance(receipt_bindings.get(unit_id), str)
                                   and len(receipt_bindings[unit_id]) == 64)
                if isinstance(per_trajectory, list) and len(per_trajectory) == trajectories:
                    reconstructed_mean, reconstructed_interval = mean_student_t_interval(
                        per_trajectory, temporal["confidence_level"])
                    passed &= math.isclose(estimate, reconstructed_mean, rel_tol=0, abs_tol=1e-12)
                    passed &= all(math.isclose(observed_value, reconstructed_value,
                                               rel_tol=0, abs_tol=1e-12)
                                  for observed_value, reconstructed_value in zip(
                                      (low, high), reconstructed_interval, strict=True))
                intervals.append((low, high))
            passed &= len(intervals) == len(required_methods)
            passed &= len(point_estimates) == len(required_methods)
            fir = by_id.get("causal_fir_group_delay", {})
            per_kernels = fir.get("per_trajectory_kernels")
            per_improvements = fir.get("per_trajectory_fir_vs_pure_delay_relative_improvement")
            aggregate_kernel = fir.get("kernel")
            expected_kernel_length = temporal["maximum_lag_ticks_for_estimation"] + 1
            kernel_evidence_ok = (isinstance(per_kernels, list)
                and len(per_kernels) == len(expected_ids)
                and isinstance(per_improvements, list) and len(per_improvements) == len(expected_ids)
                and isinstance(aggregate_kernel, list)
                and len(aggregate_kernel) == expected_kernel_length)
            fir_estimates = fir.get("per_trajectory_estimates_ticks")
            if kernel_evidence_ok:
                normalized_kernels: list[list[float]] = []
                for kernel in per_kernels:
                    if not isinstance(kernel, list) or len(kernel) != expected_kernel_length:
                        kernel_evidence_ok = False
                        break
                    for value in kernel:
                        _number(value, "per-trajectory FIR coefficient")
                    try:
                        normalized_kernels.append(normalized_kernel(kernel))
                    except (TypeError, ValueError):
                        kernel_evidence_ok = False
                        break
                improvements = [_number(value, "FIR improvement") for value in per_improvements]
                if normalized_kernels and kernel_evidence_ok:
                    reconstructed_kernel = [statistics.fmean(values) for values in zip(
                        *normalized_kernels, strict=True)]
                    reconstructed_kernel = [value / sum(reconstructed_kernel)
                                            for value in reconstructed_kernel]
                    kernel_evidence_ok &= all(math.isclose(_number(observed_tap, "aggregate FIR tap"),
                                                           expected_tap, rel_tol=0, abs_tol=1e-12)
                                              for observed_tap, expected_tap in zip(
                                                  aggregate_kernel, reconstructed_kernel, strict=True))
                    # Reported group delay is not independently mutable metadata:
                    # every per-trajectory estimate must be the first moment of
                    # its own bound kernel, index for index.
                    kernel_evidence_ok &= (isinstance(fir_estimates, list)
                                           and len(fir_estimates) == len(normalized_kernels))
                    if isinstance(fir_estimates, list) and len(fir_estimates) == len(normalized_kernels):
                        kernel_evidence_ok &= all(
                            math.isclose(_number(reported, "per-trajectory group delay"),
                                         kernel_group_delay_ticks(bound_kernel),
                                         rel_tol=0, abs_tol=1e-9)
                            for reported, bound_kernel in zip(fir_estimates, normalized_kernels,
                                                              strict=True))
                    # Group delay is linear in the normalized kernel, so the
                    # aggregate estimate must equal the installed aggregate
                    # kernel's own group delay exactly. This forbids reporting
                    # 6.5 ticks while installing a ~3.3-tick kernel.
                    kernel_evidence_ok &= math.isclose(
                        _number(fir.get("estimate_ticks"), "aggregate FIR estimate"),
                        kernel_group_delay_ticks(reconstructed_kernel),
                        rel_tol=0, abs_tol=1e-9)
                    # One authority-bound pure-delay definition, shared with
                    # causal_fir_targets: kernel mass, never positive-tap count.
                    kernel_evidence_ok &= fir.get("kernel_is_pure_delay") is (
                        kernel_is_effectively_pure_delay(reconstructed_kernel,
                                                         tolerance=pure_delay_tolerance))
                    kernel_evidence_ok &= not any(
                        kernel_is_effectively_pure_delay(bound_kernel,
                                                         tolerance=pure_delay_tolerance)
                        for bound_kernel in normalized_kernels)
                    # Coverage, not central tendency: a single large improvement
                    # may not rescue trajectories that are worse than a delay.
                    kernel_evidence_ok &= fir.get("causal_fir_beats_best_pure_delay") is (
                        all(value > 0 for value in improvements))
                    kernel_evidence_ok &= fir.get("per_trajectory_beats_best_pure_delay") is (
                        all(value > 0 for value in improvements))
                    # Estimand-matched agreement. The cross-correlation method
                    # searches single lags, so its estimand is the MODE of this
                    # same kernel, not its first moment. Pair it against the
                    # mode of each bound per-trajectory kernel and of the bound
                    # aggregate kernel, inside the estimator's own parabolic
                    # refinement clamp. The kernels are already tied to the
                    # per-trajectory group delays above, so nothing here can be
                    # satisfied by editing a standalone field, and -- unlike the
                    # superseded interval-overlap rule -- nothing here can be
                    # satisfied by widening an interval.
                    cross = per_trajectory_by_method.get(
                        "derivative_cross_correlation_lag")
                    kernel_evidence_ok &= (isinstance(cross, list)
                                           and len(cross) == len(normalized_kernels))
                    if isinstance(cross, list) and len(cross) == len(normalized_kernels):
                        kernel_evidence_ok &= all(
                            abs(_number(lag, "per-trajectory cross-correlation lag")
                                - kernel_mode_lag(bound_kernel)) <= refinement_bound
                            for lag, bound_kernel in zip(cross, normalized_kernels,
                                                         strict=True))
                    aggregate_cross = point_estimates.get(
                        "derivative_cross_correlation_lag")
                    kernel_evidence_ok &= (aggregate_cross is not None and abs(
                        aggregate_cross - kernel_mode_lag(reconstructed_kernel))
                        <= refinement_bound)
                    # Both aggregate estimands must live where the shared kernel
                    # actually carries mass.
                    low_support, high_support = kernel_positive_mass_support(
                        reconstructed_kernel)
                    kernel_evidence_ok &= all(
                        float(low_support) <= value <= float(high_support)
                        for value in point_estimates.values())
            passed &= kernel_evidence_ok
            passed &= fir.get("causal_fir_beats_best_pure_delay") is True and fir.get("kernel_is_pure_delay") is False
            try:
                causal_fir_targets([float(i) for i in range(32)], [16], fir.get("kernel"),
                                   pure_delay_tolerance=pure_delay_tolerance)
            except (EvidenceError, TypeError):
                passed = False
            passed &= self._clock_coordinates_ok(item, expected_ids, observed)
            alignment_ok &= passed
            alignment_detail[direction] = {"methods": methods,
                "agreement_rule": AGREEMENT_RULE, "agrees": passed}
        self._gate(gates, "render_server_temporal_alignment", alignment_ok, alignment_detail, reasons)


DurableVerifier = Callable[[Mapping[str, Any], Mapping[str, Any]], bool]


def verify_remote_durable_objects(unit: Mapping[str, Any], receipt: Mapping[str, Any]) -> bool:
    """Read back the remote checksum manifest and verify every declared object exists."""
    uri = receipt.get("durable_uri")
    objects = receipt.get("durable_objects")
    manifest_sha = receipt.get("remote_checksum_manifest_sha256")
    if not isinstance(uri, str) or not uri.startswith("s3://") or not isinstance(objects, dict) or not objects:
        return False
    readback = subprocess.run(["aws", "s3", "cp", f"{uri}/sha256_manifest.json", "-", "--only-show-errors"],
                              capture_output=True, check=False)
    if readback.returncode or hashlib.sha256(readback.stdout).hexdigest() != manifest_sha:
        return False
    try:
        remote_manifest = json.loads(readback.stdout)
    except json.JSONDecodeError:
        return False
    expected_binding = {"unit_id": unit.get("unit_id"),
        "authority_sha256": receipt.get("authority_sha256"),
        "manifest_sha256": receipt.get("manifest_sha256"),
        "source_commit_sha": receipt.get("source_commit_sha"),
        "scientific_run_id": receipt.get("scientific_run_id")}
    if (remote_manifest.get("files") != objects
            or any(remote_manifest.get(key) != value for key, value in expected_binding.items())
            or uri.rstrip("/").rsplit("/", 1)[-1] != unit.get("unit_id")):
        return False
    bucket, key_prefix = uri.split("/", 3)[2:4]
    listing = subprocess.run(["aws", "s3api", "list-objects-v2", "--bucket", bucket,
                              "--prefix", key_prefix.rstrip("/") + "/", "--output", "json"],
                             capture_output=True, check=False)
    if listing.returncode:
        return False
    try:
        keys = {item["Key"] for item in json.loads(listing.stdout).get("Contents", [])}
    except (json.JSONDecodeError, KeyError, TypeError):
        return False
    expected_keys = {key_prefix.rstrip("/") + "/" + relative for relative in objects}
    expected_keys.add(key_prefix.rstrip("/") + "/sha256_manifest.json")
    if keys != expected_keys:
        return False
    for relative, expected_sha in objects.items():
        read_object = subprocess.run(["aws", "s3", "cp", f"{uri}/{relative}", "-", "--only-show-errors"],
                                     capture_output=True, check=False)
        if read_object.returncode or hashlib.sha256(read_object.stdout).hexdigest() != expected_sha:
            return False
    return receipt.get("unit_id") == unit.get("unit_id")


class DurableController:
    TERMINAL = "COMPLETE_VALIDATED_DURABLE"

    def __init__(self, manifest: Mapping[str, Any], state_dir: Path, event_log: Path, *,
                 manifest_sha256: str | None = None, authority_sha256: str | None = None,
                 source_commit_sha: str | None = None, run_namespace: str | None = None,
                 maximum_attempts: int = 3, stage_role: str | None = None,
                 durable_verifier: DurableVerifier = verify_remote_durable_objects):
        self.manifest = manifest; self.state_dir = state_dir; self.event_log = event_log
        self.manifest_sha256 = manifest_sha256; self.authority_sha256 = authority_sha256
        self.source_commit_sha = source_commit_sha; self.run_namespace = run_namespace
        # A6 on the restart/resume path. Durable state is keyed by unit_id, so a
        # state directory carried over from the other stage could otherwise mark
        # a unit "already complete" and skip it, or drive units the caller never
        # authorized. Every unit is checked against the stage the caller is
        # authorized for before it is run OR reused.
        self.stage_role = stage_role
        self.maximum_attempts = _integer(maximum_attempts, "maximum_attempts", minimum=1)
        self.durable_verifier = durable_verifier
        units = manifest.get("units")
        if not isinstance(units, list) or not units:
            raise EvidenceError("durable manifest units are missing")
        unit_ids = [unit.get("unit_id") for unit in units if isinstance(unit, dict)]
        if (len(unit_ids) != len(units) or any(not isinstance(value, str) or not value for value in unit_ids)
                or len(set(unit_ids)) != len(unit_ids)):
            raise EvidenceError("durable manifest unit identities are malformed or duplicate")
        prefix = manifest.get("durable_prefix")
        if not isinstance(prefix, str) or not prefix.startswith("s3://") or prefix.rstrip("/") != prefix.rstrip("/").strip():
            raise EvidenceError("durable manifest prefix is missing or malformed")
        self.durable_prefix = prefix.rstrip("/")

    def expected_durable_uri(self, unit_id: str) -> str:
        return f"{self.durable_prefix}/{unit_id}"

    def _events(self, event: Mapping[str, Any]) -> None:
        self.event_log.parent.mkdir(parents=True, exist_ok=True)
        with self.event_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(event), sort_keys=True, allow_nan=False) + "\n")
            handle.flush(); os.fsync(handle.fileno())

    def _state_path(self, unit_id: str) -> Path:
        return self.state_dir / f"{unit_id}.json"

    def _valid_receipt(self, unit: Mapping[str, Any], receipt_path: Path) -> bool:
        if not receipt_path.is_file():
            return False
        try:
            receipt = load_json(receipt_path)
        except EvidenceError:
            return False
        # The restart/reuse path must bind the receipt's durable location to the
        # authority/manifest prefix, not merely to the trailing unit identity: a
        # foreign bucket or prefix ending in the same unit_id would otherwise
        # satisfy resume verification and let a completed unit be "reused" from
        # storage the manifest never authorized.
        expected = {"unit_id": unit["unit_id"], "status": self.TERMINAL,
                    "manifest_sha256": self.manifest_sha256, "authority_sha256": self.authority_sha256,
                    "source_commit_sha": self.source_commit_sha, "scientific_run_id": self.run_namespace,
                    "durable_uri": self.expected_durable_uri(unit["unit_id"])}
        return (all(receipt.get(k) == v and v is not None for k, v in expected.items())
                and self.durable_verifier(unit, receipt))

    def completed(self, unit_id: str) -> bool:
        unit = next((item for item in self.manifest.get("units", []) if item.get("unit_id") == unit_id), None)
        path = self._state_path(unit_id)
        if unit is None or not path.is_file():
            return False
        try:
            state = load_json(path)
        except EvidenceError:
            return False
        receipt_path = Path(state.get("receipt_path", ""))
        return (state.get("status") == self.TERMINAL
                and state.get("receipt_sha256") == (sha256_file(receipt_path) if receipt_path.is_file() else None)
                and state.get("manifest_sha256") == self.manifest_sha256
                and state.get("authority_sha256") == self.authority_sha256
                and state.get("source_commit_sha") == self.source_commit_sha
                and state.get("scientific_run_id") == self.run_namespace
                and self._valid_receipt(unit, receipt_path))

    def run(self, *, authorized: bool, stop_after_stage1: bool = True,
            environment: Mapping[str, str] | None = None) -> None:
        if not authorized:
            raise PermissionError("collection authorization is false")
        if None in (self.manifest_sha256, self.authority_sha256, self.source_commit_sha, self.run_namespace):
            raise EvidenceError("controller execution bindings are incomplete")
        if self.stage_role is None:
            raise EvidenceError("controller stage role binding is required")
        self.state_dir.mkdir(parents=True, exist_ok=True)
        for unit in self.manifest["units"]:
            unit_id = unit["unit_id"]
            # Cross-stage restart/resume refusal, applied before reuse as well
            # as before launch.
            if unit.get("scientific_run_id") != self.run_namespace:
                raise PermissionError(
                    f"unit {unit_id!r} belongs to namespace {unit.get('scientific_run_id')!r}, "
                    f"not to the authorized {self.run_namespace!r}")
            command = unit.get("command")
            declared = (command[command.index("--stage") + 1]
                        if isinstance(command, list) and "--stage" in command
                        and command.index("--stage") + 1 < len(command) else None)
            if not isinstance(declared, str) or not declared.startswith(self.stage_role):
                raise PermissionError(
                    f"unit {unit_id!r} declares stage {declared!r}, which is not a "
                    f"{self.stage_role!r} stage")
            if self.completed(unit_id):
                self._events({"event": "unit_reused", "unit_id": unit_id}); continue
            if not isinstance(command, list) or not command or not all(isinstance(part, str) and part for part in command):
                raise EvidenceError(f"unit {unit_id} has invalid command")
            receipt_path = Path(unit["receipt_path"])
            for attempt in range(1, self.maximum_attempts + 1):
                self._events({"event": "unit_started", "unit_id": unit_id, "attempt": attempt})
                result = subprocess.run(command, check=False,
                                        env=None if environment is None else {**os.environ, **environment})
                if result.returncode == 0 and self._valid_receipt(unit, receipt_path):
                    break
                self._events({"event": "unit_attempt_failed", "unit_id": unit_id,
                              "attempt": attempt, "returncode": result.returncode})
            else:
                raise RuntimeError(f"unit {unit_id} failed after {self.maximum_attempts} identical attempts")
            atomic_write_json(self._state_path(unit_id), {"unit_id": unit_id, "status": self.TERMINAL,
                "receipt_path": str(receipt_path), "receipt_sha256": sha256_file(receipt_path),
                "manifest_sha256": self.manifest_sha256, "authority_sha256": self.authority_sha256,
                "source_commit_sha": self.source_commit_sha, "scientific_run_id": self.run_namespace})
            self._events({"event": "unit_completed", "unit_id": unit_id})
        if stop_after_stage1:
            self._events({"event": "stage1_units_complete", "automatic_stage2_start": False})


def require_stage2_authorization(manifest: Mapping[str, Any],
                                 authorization_receipt: Mapping[str, Any] | None, *,
                                 authorization_receipt_path: Path,
                                 stage1_decision: Mapping[str, Any] | None, authority_path: Path,
                                 manifest_path: Path, stage1_manifest_path: Path,
                                 stage1_evidence_path: Path, stage1_decision_path: Path,
                                 current_source_commit: str,
                                 preoutcome_provenance_path: Path) -> None:
    """Require a separate, exact, hash-bound post-Stage-1 authorization."""
    if manifest.get("STAGE_2_COLLECTION_AUTHORIZED") is not False:
        raise PermissionError("locked Stage-2 manifest is malformed")
    if manifest.get("status") != "POST_STAGE1_MATERIALIZED_AWAITING_SEPARATE_FREEZE_AND_AUTHORIZATION":
        raise PermissionError("Stage-2 draft template has no materialized target windows")
    try:
        validate_stage2_manifest_design(load_json(authority_path), manifest,
                                        require_materialized=True)
    except (EvidenceError, KeyError, TypeError, ValueError) as exc:
        raise PermissionError("Stage-2 manifest violates frozen authority") from exc
    identities = manifest.get("trajectory_identities")
    if not isinstance(identities, list) or not identities or any(
            item.get("target_window_status") != "MATERIALIZED_FROM_STAGE1"
            or len(item.get("target_model_frame_indices", [])) != 19 for item in identities):
        raise PermissionError("Stage-2 target-window materialization is incomplete")
    if not stage1_decision_path.is_file() or not stage1_decision or load_json(stage1_decision_path) != dict(stage1_decision):
        raise PermissionError("exact Stage-1 decision artifact is required")
    if not stage1_evidence_path.is_file():
        raise PermissionError("exact Stage-1 evidence artifact is required")
    if (not authorization_receipt_path.is_file() or not authorization_receipt
            or load_json(authorization_receipt_path) != dict(authorization_receipt)):
        raise PermissionError("exact on-disk Stage-2 authorization artifact is required")
    # Both identities below used to be v0.2 literals. The authority's own stage
    # binding table already names the Stage-2 authorization artifact per version,
    # and the Stage-1 manifest already names its version, so neither is spelled
    # here: a v0.3 gate demands v0.3 artifacts and refuses v0.2 ones, and the
    # v0.2 package keeps its own identities on replay.
    stage2_authorization_id = ((load_json(authority_path).get("stage_binding_policy") or {})
                               .get("stages", {}).get("stage2-capture", {})
                               .get("authorization_artifact_id"))
    if not isinstance(stage2_authorization_id, str) or not stage2_authorization_id:
        raise PermissionError("authority does not bind a Stage-2 authorization identity")
    required = {"artifact_id": stage2_authorization_id,
                "schema_version": "1.1",
                "status": "FROZEN_AUTHORIZED", "STAGE_2_COLLECTION_AUTHORIZED": True,
                "confirmatory_collection_authorized": False}
    if any(authorization_receipt.get(k) != v for k, v in required.items()):
        raise PermissionError("separate post-Stage-1 authorization is invalid")
    if not preoutcome_provenance_path.is_file():
        raise PermissionError("Stage-2 pre-outcome provenance artifact is required")
    bindings = {"authority_sha256": sha256_file(authority_path),
                "stage1_manifest_sha256": sha256_file(stage1_manifest_path),
                "stage1_decision_sha256": sha256_file(stage1_decision_path), "stage1_status": "PASS",
                "stage2_manifest_sha256": sha256_file(manifest_path), "source_commit_sha": current_source_commit,
                "expected_run_namespace": manifest.get("run_namespace"),
                "preoutcome_provenance_receipt_sha256": sha256_file(preoutcome_provenance_path)}
    required_gates = {"unit_completeness", "prospective_transition_measurement",
        "unit_identity_runtime_path_durability", "calibration_world_and_wall_relative_support",
        "hidden_row_contamination", "stable_visibility_base_rate_robust",
        "calibration_detector_response", "required_evidence_completeness",
        "render_server_temporal_alignment"}
    decision_gates = stage1_decision.get("gates")
    try:
        expected_decision_id = stage1_decision_artifact_id(load_json(stage1_manifest_path))
    except (PackageBindingError, OSError, ValueError) as exc:
        raise PermissionError("Stage-1 decision identity is unresolvable") from exc
    genuine = (stage1_decision.get("schema_version") == "1.1"
        and stage1_decision.get("artifact_id") == expected_decision_id
        and stage1_decision.get("classification") == "DEVELOPMENT_ONLY"
        and stage1_decision.get("status") == "PASS"
        and stage1_decision.get("reasons") == []
        and stage1_decision.get("stage2_collection_authorized") is False
        and stage1_decision.get("confirmatory_interpretation_authorized") is False
        and isinstance(decision_gates, dict) and set(decision_gates) == required_gates
        and all(isinstance(gate, dict) and gate.get("status") == "PASS"
                for gate in decision_gates.values()))
    if not genuine:
        raise PermissionError("genuine Stage-1 PASS decision is required")
    if (stage1_decision.get("authority_sha256") != bindings["authority_sha256"]
            or stage1_decision.get("stage1_manifest_sha256") != bindings["stage1_manifest_sha256"]):
        raise PermissionError("Stage-1 decision binding mismatch")
    evidence_sha = stage1_decision.get("stage1_evidence_sha256")
    try:
        _sha(evidence_sha, "Stage-1 evidence SHA")
    except EvidenceError as exc:
        raise PermissionError("Stage-1 decision evidence binding is missing") from exc
    if sha256_file(stage1_evidence_path) != evidence_sha:
        raise PermissionError("on-disk Stage-1 evidence binding mismatch")
    try:
        stage1_authority = load_json(authority_path)
        stage1_manifest = load_json(stage1_manifest_path)
        reproduced = Stage1Evaluator(stage1_authority, stage1_manifest,
            authority_sha256=bindings["authority_sha256"],
            manifest_sha256=bindings["stage1_manifest_sha256"]).evaluate(
                load_json(stage1_evidence_path)).to_dict(
                    authority_sha256=bindings["authority_sha256"],
                    manifest_sha256=bindings["stage1_manifest_sha256"],
                    evidence_sha256=evidence_sha,
                    artifact_id=expected_decision_id)
    except (EvidenceError, KeyError, TypeError, ValueError) as exc:
        raise PermissionError("Stage-1 evidence cannot reproduce its decision") from exc
    if reproduced != dict(stage1_decision):
        raise PermissionError("Stage-1 decision is not reproduced from bound evidence")
    if authorization_receipt.get("stage1_evidence_sha256") != evidence_sha:
        raise PermissionError("Stage-2 authorization Stage-1 evidence binding mismatch")
    if manifest.get("stage1_evidence_sha256") != evidence_sha:
        raise PermissionError("Stage-2 manifest Stage-1 evidence binding mismatch")
    for key, value in bindings.items():
        if authorization_receipt.get(key) != value:
            raise PermissionError(f"Stage-2 authorization binding mismatch: {key}")
    if manifest.get("authority_binding", {}).get("sha256") != bindings["authority_sha256"]:
        raise PermissionError("Stage-2 manifest authority mismatch")
    if manifest.get("stage1_manifest_binding") != bindings["stage1_manifest_sha256"]:
        raise PermissionError("Stage-2 manifest Stage-1 manifest mismatch")
    if manifest.get("stage1_decision_sha256") != bindings["stage1_decision_sha256"]:
        raise PermissionError("Stage-2 manifest Stage-1 decision mismatch")
    if manifest.get("source_commit_binding") != "BOUND_AT_LAUNCH_BY_PREOUTCOME_PROVENANCE_RECEIPT":
        raise PermissionError("Stage-2 manifest source-commit policy mismatch")
    if authorization_receipt.get("authorization_payload_sha256") != canonical_payload_sha256(
            authorization_receipt, omit="authorization_payload_sha256"):
        raise PermissionError("Stage-2 authorization payload hash mismatch")


def require_preoutcome_provenance(
        receipt: Mapping[str, Any], *, authority_path: Path, manifest_path: Path,
        required_source_paths: Sequence[Path],
        provenance_artifact_id: str = DEFAULT_PREOUTCOME_PROVENANCE_ARTIFACT_ID) -> None:
    repository = authority_path.resolve()
    while repository != repository.parent and not (repository / ".git").exists():
        repository = repository.parent
    if not (repository / ".git").exists():
        raise PermissionError("pre-outcome provenance repository is unresolved")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repository, text=True,
                          capture_output=True, check=True).stdout.strip()
    authority = load_json(authority_path)
    manifest = load_json(manifest_path)
    runtime_policy = "BOUND_AT_LAUNCH_BY_PREOUTCOME_PROVENANCE_RECEIPT"
    if (authority.get("prospective_source_commit_binding") != runtime_policy
            or manifest.get("source_commit_binding") != runtime_policy):
        raise PermissionError("authority/manifest runtime source-commit policy mismatch")
    expected = {"artifact_id": provenance_artifact_id,
                "status": "FROZEN_VERIFIED", "authority_sha256": sha256_file(authority_path),
                "manifest_sha256": sha256_file(manifest_path),
                "source_paths_verified_bytes_and_modes": True, "runtime_identity_verified": True,
                "apparatus_identity_verified": True, "renderer_identity_verified": True,
                "remote_durable_prefix_read_write_probe_verified": True,
                "scientific_outcomes_observed": False, "confirmatory_collection_authorized": False,
                "independently_derived": True, "source_commit": head,
                # Step 3 of the two-step commit binding. A PRE_FREEZE_VERIFIED
                # receipt names no commit and is refused here by construction.
                "source_commit_binding_state": "BOUND_TO_FROZEN_COMMIT",
                "committed_bytes_equal_reviewed_bytes": True,
                "repository_clean_at_post_freeze_verification": True,
                # The whole apparatus source closure in one recomputable field,
                # so the receipt cannot outlive a source edit.
                "runtime_critical_source_closure_sha256":
                    runtime_critical_source_closure_sha256(repository),
                # Exactly which units this receipt was verified against.
                "run_inventory_sha256": stage_run_inventory_sha256(manifest),
                "run_namespace": manifest.get("run_namespace")}
    for key, value in expected.items():
        if receipt.get(key) != value:
            raise PermissionError(f"pre-outcome provenance rejects {key}")
    dirty = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=repository, text=True, capture_output=True, check=True).stdout.strip()
    if dirty:
        raise PermissionError("pre-outcome provenance rejects dirty frozen repository")
    if receipt.get("payload_sha256") != canonical_payload_sha256(receipt, omit="payload_sha256"):
        raise PermissionError("pre-outcome provenance payload digest mismatch")
    # Reproduce the runtime result from the concrete probe record embedded in
    # the provenance receipt.  The former gate checked only summary booleans and
    # a syntactically valid digest, so a freshly rehashed document containing
    # ``runtime_identity_verified=true`` but no probe at all could authorize a
    # launch.  Embedding the independently produced receipt lets every launch
    # rehash the current executable, apparatus, and runtime-critical source
    # bytes and replay the exact argv/exit/output checks.
    probe_evidence = receipt.get("probe_evidence")
    if not isinstance(probe_evidence, Mapping):
        raise PermissionError("pre-outcome provenance has no concrete probe evidence")
    try:
        runtime_result = verify_runtime_identity(
            authority["runtime_identity_policy"], probe_evidence)
        probe_result = verify_probe_execution(
            probe_evidence, "embedded pre-outcome probe evidence",
            authority=authority, repository=repository)
    except (EvidenceError, KeyError, TypeError, ValueError) as exc:
        raise PermissionError("pre-outcome runtime probe evidence does not reproduce") from exc
    if (runtime_result.get("status") != "PASS"
            or probe_result.get("probe_evidence_sha256")
               != receipt.get("probe_evidence_sha256")
            or hashlib.sha256(canonical_json_bytes(dict(probe_evidence))).hexdigest()
               != receipt.get("probe_evidence_path_sha256")):
        raise PermissionError("pre-outcome runtime probe binding mismatch")
    # The runtime probe above proves identity, not runnability. These two prove
    # the capture path itself: that its executables resolve, and that the frozen
    # units build a spec the reused v0.1 interface accepts. A receipt produced
    # before these controls existed has neither field and is refused here, so an
    # older provenance cannot authorize a successor campaign.
    try:
        require_capture_toolchain(receipt.get("capture_toolchain") or {})
        preflight = receipt.get("capture_contract_preflight") or {}
        if preflight.get("verified") is not True:
            raise EvidenceError("capture contract preflight did not verify")
        expected_preflight = capture_contract_preflight(manifest, authority)
        if preflight.get("capture_spec_sha256_by_unit") != expected_preflight[
                "capture_spec_sha256_by_unit"]:
            raise EvidenceError("capture contract preflight does not reproduce")
        # Bound to the closure as well as the commit: the expanded closure now
        # covers the campaign module and the provisioning script, so a smoke
        # taken before an apparatus edit cannot authorize the edited apparatus.
        require_operational_smoke(receipt.get("operational_startup_smoke") or {},
                                  run_namespace=str(manifest.get("run_namespace")),
                                  source_commit=head,
                                  closure_sha256=runtime_critical_source_closure_sha256(
                                      repository))
        # The camera apparatus identity contract, crossed before collection
        # rather than after a full capture. Checked here because this is where
        # the frozen apparatus policy is in scope.
        require_camera_apparatus_observation(
            receipt.get("operational_startup_smoke") or {},
            authority["apparatus_observation_policy"])
    except EvidenceError as exc:
        raise PermissionError(f"pre-outcome capture-path preflight rejects receipt: {exc}") from exc
    bindings = receipt.get("source_bindings")
    if not isinstance(bindings, dict):
        raise PermissionError("pre-outcome provenance has no source bindings")
    critical: list[CriticalSource] = []
    for path in required_source_paths:
        try:
            relative = path.resolve().relative_to(repository).as_posix()
        except ValueError as exc:
            raise PermissionError(f"pre-outcome source lies outside repository: {path}") from exc
        binding = bindings.get(relative)
        if not isinstance(binding, dict) or not path.is_file():
            raise PermissionError(f"pre-outcome source binding mismatch: {path}")
        try:
            critical.append(CriticalSource(relative, binding.get("sha256")))
        except (TypeError, ValueError) as exc:
            raise PermissionError(f"invalid pre-outcome source pin: {relative}") from exc
    result = verify_sources(repository, critical, expected_head=head)
    if not result.verified:
        raise PermissionError("pre-outcome source provenance failed: " + "; ".join(result.violations))
    records = {record["relative_path"]: record for record in result.sources}
    for relative, binding in bindings.items():
        if relative in records and binding.get("git_mode") != records[relative].get("tree_mode"):
            raise PermissionError(f"pre-outcome source mode pin mismatch: {relative}")
