"""Load and validate Person E's artifact-independent Phase 1 configuration."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from mineocclude.analysis.manifests import is_hex_digest
from mineocclude.contracts.analysis_inputs import MEASUREMENT_INPUT_SCHEMA_VERSION
from mineocclude.contracts.identity import SCHEMA_VERSION

DEFAULT_PERSON_E_CONFIG_PATH = (
    Path(__file__).resolve().parents[3]
    / "configs"
    / "vision"
    / "person_e_phase1.yaml"
)

LEGACY_PERSON_E_CONFIG_SCHEMA_VERSION = "person-e-phase1-config-schema-v0.1"
PERSON_E_CONFIG_SCHEMA_VERSION = "person-e-phase2-config-schema-v0.1"
FOUNDATION_PERSON_E_CONFIG_VERSION = "person-e-phase1-foundation-v0.1"
LIVE_READY_STATUS = "calibrated_live_ready"
PENDING_STATUS = "foundation_pending_upstream_calibration"
PHASE2_CALIBRATED_STATUS = "phase2_calibrated"


class PersonEConfigError(ValueError):
    """Raised when Person E settings are incomplete, unsafe, or modified."""


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PersonEConfigError(f"{name} must be a mapping.")
    return value


def _require_exact_keys(
    value: Mapping[str, Any], expected: set[str], name: str
) -> None:
    if set(value) != expected:
        missing = sorted(expected - set(value))
        extra = sorted(set(value) - expected)
        raise PersonEConfigError(
            f"{name} fields changed; missing={missing}, extra={extra}."
        )


def validate_person_e_config(config: Mapping[str, Any]) -> None:
    """Validate the pre-calibration configuration and its explicit gaps."""

    if not isinstance(config, Mapping):
        raise PersonEConfigError("Person E config must be a mapping.")
    top_level = {
        "schema_version",
        "config_schema_version",
        "config_instance_version",
        "status",
        "coordinate_contract",
        "registry",
        "detector",
        "homography",
        "measurement",
        "ssim",
        "measurement_output",
    }
    _require_exact_keys(config, top_level, "Person E config")
    if config["schema_version"] != SCHEMA_VERSION:
        raise PersonEConfigError("Frozen schema_version must remain '1.0'.")
    config_schema_version = config["config_schema_version"]
    if config_schema_version not in {
        LEGACY_PERSON_E_CONFIG_SCHEMA_VERSION,
        PERSON_E_CONFIG_SCHEMA_VERSION,
    }:
        raise PersonEConfigError("Person E config-schema version has changed.")
    instance_version = config["config_instance_version"]
    if not isinstance(instance_version, str) or not instance_version.strip():
        raise PersonEConfigError("config_instance_version must be non-empty.")
    status = config["status"]
    if status not in {
        PENDING_STATUS,
        PHASE2_CALIBRATED_STATUS,
        LIVE_READY_STATUS,
    }:
        raise PersonEConfigError("Unknown Person E configuration lifecycle status.")
    if status == PENDING_STATUS and instance_version != FOUNDATION_PERSON_E_CONFIG_VERSION:
        raise PersonEConfigError("The pending foundation config has a fixed identity.")
    if (
        status == PENDING_STATUS
        and config_schema_version != LEGACY_PERSON_E_CONFIG_SCHEMA_VERSION
    ):
        raise PersonEConfigError("The Phase 1 foundation uses its legacy config schema.")
    if (
        status == PHASE2_CALIBRATED_STATUS
        and config_schema_version != PERSON_E_CONFIG_SCHEMA_VERSION
    ):
        raise PersonEConfigError("Phase 2 calibration requires its versioned config schema.")

    coordinate = _require_mapping(config["coordinate_contract"], "coordinate_contract")
    _require_exact_keys(
        coordinate,
        {
            "quantity",
            "unit",
            "image_point_convention",
            "world_ground_plane_axes",
            "positive_direction_source",
            "silent_axis_inference_forbidden",
        },
        "coordinate_contract",
    )
    if (
        coordinate.get("quantity") != "signed_wall_parallel_position"
        or coordinate.get("unit") != "blocks"
        or coordinate.get("image_point_convention")
        != "pixel_center_xy_zero_based"
        or coordinate.get("world_ground_plane_axes") != ["world_x", "world_z"]
        or coordinate.get("silent_axis_inference_forbidden") is not True
        or coordinate.get("positive_direction_source")
        != "signed_person_b_person_c_coordinate_frame"
    ):
        raise PersonEConfigError("Coordinate sign and block units are frozen.")

    registry = _require_mapping(config["registry"], "registry")
    _require_exact_keys(
        registry,
        {
            "schema_version",
            "hash_algorithm",
            "hash_source",
            "completed_runs_are_immutable",
            "corrections_supersede_instead_of_overwrite",
            "filenames_are_identity",
        },
        "registry",
    )
    if (
        registry.get("schema_version") != SCHEMA_VERSION
        or registry.get("hash_algorithm") != "sha256"
        or registry.get("hash_source") != "literal_file_bytes"
        or registry.get("completed_runs_are_immutable") is not True
        or registry.get("corrections_supersede_instead_of_overwrite") is not True
        or registry.get("filenames_are_identity") is not False
    ):
        raise PersonEConfigError("Registry provenance policy has changed.")

    detector = _require_mapping(config["detector"], "detector")
    detector_fields = {
        "color_space",
        "threshold_status",
        "threshold_version",
        "calibration_dataset_hash",
        "heldout_report_hash",
        "hsv_ranges",
        "morphology",
        "blob",
        "heldout_gates",
    }
    if config_schema_version == PERSON_E_CONFIG_SCHEMA_VERSION:
        detector_fields |= {
            "detector_algorithm_version",
            "split_version",
            "settings_hash",
            "software_runtime_hash",
        }
    _require_exact_keys(detector, detector_fields, "detector")
    if detector.get("color_space") != "hsv_h_degrees_sv_unit_interval":
        raise PersonEConfigError("Detector color-space convention has changed.")
    morphology = _require_mapping(detector.get("morphology"), "detector.morphology")
    blob = _require_mapping(detector.get("blob"), "detector.blob")
    heldout_gates = _require_mapping(
        detector.get("heldout_gates"), "detector.heldout_gates"
    )
    _require_exact_keys(
        morphology,
        {"open_iterations", "close_iterations", "radius_pixels"},
        "detector.morphology",
    )
    _require_exact_keys(
        blob,
        {
            "connectivity",
            "min_area_pixels",
            "max_area_pixels",
            "selection",
        },
        "detector.blob",
    )
    _require_exact_keys(
        heldout_gates,
        {"minimum_precision", "minimum_recall"},
        "detector.heldout_gates",
    )
    if (
        not isinstance(morphology.get("open_iterations"), int)
        or isinstance(morphology.get("open_iterations"), bool)
        or morphology["open_iterations"] < 0
        or not isinstance(morphology.get("close_iterations"), int)
        or isinstance(morphology.get("close_iterations"), bool)
        or morphology["close_iterations"] < 0
        or not isinstance(morphology.get("radius_pixels"), int)
        or isinstance(morphology.get("radius_pixels"), bool)
        or morphology["radius_pixels"] < 0
        or blob.get("connectivity") != 8
        or blob.get("selection") != "largest_valid_area_then_top_left"
        or heldout_gates.get("minimum_precision") != 0.95
        or heldout_gates.get("minimum_recall") != 0.95
    ):
        raise PersonEConfigError("Detector algorithm or planning gates changed.")
    hsv_ranges = detector.get("hsv_ranges")
    if not isinstance(hsv_ranges, list):
        raise PersonEConfigError("detector.hsv_ranges must be a list.")
    if status == PENDING_STATUS:
        if (
            detector.get("threshold_status") != "pending_person_c_calibration"
            or detector.get("threshold_version") is not None
            or detector.get("calibration_dataset_hash") is not None
            or detector.get("heldout_report_hash") is not None
            or hsv_ranges
            or blob.get("min_area_pixels") is not None
            or blob.get("max_area_pixels") is not None
        ):
            raise PersonEConfigError(
                "Pending detector settings must remain null until calibration."
            )
    else:
        if detector.get("threshold_status") != "frozen_calibration_only":
            raise PersonEConfigError("Live detector thresholds must be frozen.")
        for field in ("threshold_version",):
            if not isinstance(detector.get(field), str) or not detector[field].strip():
                raise PersonEConfigError(f"detector.{field} must be non-empty.")
        for field in ("calibration_dataset_hash",):
            if not is_hex_digest(detector.get(field), 64):
                raise PersonEConfigError(f"detector.{field} must be SHA-256.")
        if status == LIVE_READY_STATUS:
            if not is_hex_digest(detector.get("heldout_report_hash"), 64):
                raise PersonEConfigError(
                    "Live detector heldout_report_hash must be SHA-256."
                )
        elif detector.get("heldout_report_hash") is not None:
            raise PersonEConfigError(
                "Phase 2 calibration cannot claim a held-out detector report."
            )
        if config_schema_version == PERSON_E_CONFIG_SCHEMA_VERSION:
            if detector.get("detector_algorithm_version") != (
                "hsv-largest-valid-blob-v0.1"
            ):
                raise PersonEConfigError("Detector algorithm version changed.")
            split_version = detector.get("split_version")
            if (
                not isinstance(split_version, str)
                or not split_version.startswith("sha256:")
                or not is_hex_digest(split_version.removeprefix("sha256:"), 64)
            ):
                raise PersonEConfigError("detector.split_version is invalid.")
            for field in ("settings_hash", "software_runtime_hash"):
                if not is_hex_digest(detector.get(field), 64):
                    raise PersonEConfigError(f"detector.{field} must be SHA-256.")
        if not hsv_ranges:
            raise PersonEConfigError("Live detector requires at least one HSV range.")
        expected_range_fields = {"h_min", "h_max", "s_min", "s_max", "v_min", "v_max"}
        for index, hsv_range in enumerate(hsv_ranges):
            mapping = _require_mapping(hsv_range, f"detector.hsv_ranges[{index}]")
            _require_exact_keys(mapping, expected_range_fields, f"detector.hsv_ranges[{index}]")
            values = [mapping[field] for field in expected_range_fields]
            if any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                for value in values
            ):
                raise PersonEConfigError("HSV bounds must be numeric.")
            if not (
                0.0 <= float(mapping["h_min"]) <= float(mapping["h_max"]) <= 360.0
                and 0.0 <= float(mapping["s_min"]) <= float(mapping["s_max"]) <= 1.0
                and 0.0 <= float(mapping["v_min"]) <= float(mapping["v_max"]) <= 1.0
            ):
                raise PersonEConfigError("HSV bounds are outside the declared space.")
        min_area = blob.get("min_area_pixels")
        max_area = blob.get("max_area_pixels")
        if (
            not isinstance(min_area, int)
            or isinstance(min_area, bool)
            or min_area < 1
            or not isinstance(max_area, int)
            or isinstance(max_area, bool)
            or max_area < min_area
        ):
            raise PersonEConfigError("Live blob-area bounds must be positive and ordered.")

    homography = _require_mapping(config["homography"], "homography")
    _require_exact_keys(
        homography,
        {
            "marker_count",
            "matrix_shape",
            "fit_scope",
            "singular_pivot_tolerance",
            "maximum_median_wall_parallel_error_blocks",
            "maximum_p95_wall_parallel_error_blocks",
            "minimum_shift_error_multiplier_on_gate_failure",
        },
        "homography",
    )
    if (
        homography.get("marker_count") != 4
        or homography.get("matrix_shape") != [3, 3]
        or homography.get("fit_scope") != "layout_and_canonical_camera_pose"
        or homography.get("singular_pivot_tolerance") != 1e-12
        or homography.get("maximum_median_wall_parallel_error_blocks") != 0.2
        or homography.get("maximum_p95_wall_parallel_error_blocks") != 0.5
        or homography.get("minimum_shift_error_multiplier_on_gate_failure") != 2.0
    ):
        raise PersonEConfigError("Homography contract or planning gates changed.")

    measurement = _require_mapping(config["measurement"], "measurement")
    _require_exact_keys(
        measurement,
        {
            "post_reveal_comparison",
            "primary_valid_consecutive_frames",
            "sensitivity_first_valid_frames",
            "baseline_control_type",
            "baseline_match_keys",
            "displacement_unit",
            "displacement_rule",
            "persistence_score_rule",
            "non_persistence_is_zero",
            "generation_failure_is_zero",
            "silent_interpolation_forbidden",
        },
        "measurement",
    )
    if (
        measurement.get("post_reveal_comparison")
        != "frame_idx_strictly_greater_than_reveal_frame_idx"
        or measurement.get("primary_valid_consecutive_frames") != 2
        or measurement.get("sensitivity_first_valid_frames") != 3
        or measurement.get("baseline_control_type") != "alpha_zero"
        or measurement.get("baseline_match_keys") != ["event_id", "seed"]
        or measurement.get("displacement_unit") != "blocks"
        or measurement.get("displacement_rule")
        != "pushed_wall_coordinate_minus_alpha_zero_wall_coordinate"
        or measurement.get("persistence_score_rule")
        != "one_for_valid_primary_reappearance_null_otherwise"
        or measurement.get("non_persistence_is_zero") is not False
        or measurement.get("generation_failure_is_zero") is not False
        or measurement.get("silent_interpolation_forbidden") is not True
    ):
        raise PersonEConfigError("Reappearance or outcome semantics changed.")

    ssim = _require_mapping(config["ssim"], "ssim")
    _require_exact_keys(
        ssim,
        {
            "algorithm",
            "ssim_version",
            "data_range",
            "channel_handling",
            "sample_covariance",
            "k1",
            "k2",
            "alignment",
            "background_mask",
            "background_mask_margin_pixels",
            "mask_status",
        },
        "ssim",
    )
    if (
        ssim.get("algorithm") != "global_ssim_per_channel_mean_v0.1"
        or ssim.get("data_range") != 255.0
        or ssim.get("channel_handling") != "rgb_per_channel_mean"
        or ssim.get("sample_covariance") is not True
        or ssim.get("k1") != 0.01
        or ssim.get("k2") != 0.03
        or ssim.get("alignment") != "exact_frame_identity_and_equal_dimensions"
        or ssim.get("background_mask")
        != "exclude_union_of_pushed_and_baseline_boxes_plus_margin"
    ):
        raise PersonEConfigError("SSIM algorithm settings changed.")
    if status in {PENDING_STATUS, PHASE2_CALIBRATED_STATUS}:
        if (
            ssim.get("ssim_version") is not None
            or ssim.get("background_mask_margin_pixels") is not None
            or ssim.get("mask_status") != "pending_person_b_person_e_signoff"
        ):
            raise PersonEConfigError("Pending SSIM mask values must remain null.")
    elif (
        not isinstance(ssim.get("ssim_version"), str)
        or not ssim["ssim_version"].strip()
        or not isinstance(ssim.get("background_mask_margin_pixels"), int)
        or isinstance(ssim.get("background_mask_margin_pixels"), bool)
        or ssim["background_mask_margin_pixels"] < 0
        or ssim.get("mask_status") != "frozen_person_b_person_e_signed"
    ):
        raise PersonEConfigError("Live SSIM settings require a signed fixed mask margin.")

    output = _require_mapping(config["measurement_output"], "measurement_output")
    _require_exact_keys(
        output,
        {
            "consumer_schema_version",
            "producer_role",
            "one_row_per_rollout",
            "allowed_statuses",
        },
        "measurement_output",
    )
    if (
        output.get("consumer_schema_version") != MEASUREMENT_INPUT_SCHEMA_VERSION
        or output.get("producer_role") != "person_e"
        or output.get("one_row_per_rollout") is not True
        or output.get("allowed_statuses")
        != ["measured", "non_persistence", "generation_failure", "excluded"]
    ):
        raise PersonEConfigError("E-to-B measurement contract changed.")


def _load_validated_config_bytes(
    path: Path | str,
) -> tuple[dict[str, Any], bytes]:
    config_path = Path(path)
    try:
        payload = config_path.read_bytes()
        parsed = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PersonEConfigError(
            f"Could not load Person E config {config_path}: {error}"
        ) from error
    if not isinstance(parsed, dict):
        raise PersonEConfigError("Person E config must contain one mapping.")
    validate_person_e_config(parsed)
    return parsed, payload


def load_person_e_config(
    path: Path | str = DEFAULT_PERSON_E_CONFIG_PATH,
) -> dict[str, Any]:
    """Load JSON-compatible YAML without introducing an unpinned dependency."""

    config, _ = _load_validated_config_bytes(path)
    return config


def hash_person_e_config(
    path: Path | str = DEFAULT_PERSON_E_CONFIG_PATH,
) -> str:
    """Hash the exact bytes of the same configuration that is validated."""

    _, payload = _load_validated_config_bytes(path)
    return hashlib.sha256(payload).hexdigest()


def require_live_ready_person_e_config(
    path: Path | str = DEFAULT_PERSON_E_CONFIG_PATH,
) -> dict[str, Any]:
    """Load a config and reject foundation settings in scientific workflows."""

    config = load_person_e_config(path)
    if config["status"] != LIVE_READY_STATUS:
        raise PersonEConfigError(
            "Scientific E workflows require a calibrated_live_ready config; "
            "the foundation config is only valid for known-answer tests."
        )
    return config
