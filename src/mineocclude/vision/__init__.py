"""Artifact-independent visual measurement foundations owned by Person E."""

from .calibration import (
    CalibrationDatasetError,
    decode_png_rgb_bytes,
    load_committed_frame_rgb,
    load_detector_calibration_dataset,
    validate_detector_calibration_dataset,
    validate_detector_calibration_plan,
)
from .config import (
    PersonEConfigError,
    hash_person_e_config,
    load_person_e_config,
    require_live_ready_person_e_config,
)
from .homography import (
    Homography,
    HomographyError,
    fit_marker_homography,
    homography_from_record,
    localize_ground_contact_from_background_pair,
    localize_marker_top_face,
    summarize_localization,
    validate_homography_fixture,
)
from .magenta import (
    DetectionResult,
    HsvRange,
    VisionInputError,
    detect_magenta,
    validate_detection_document,
)
from .markers import (
    MARKER_DETECTOR_VERSION,
    MarkerDetectionError,
    detect_layout_markers,
    detect_marker_point,
)
from .measurement import (
    MeasurementError,
    ReappearanceResult,
    build_measurement_document,
    build_measurement_evidence,
    build_measurement_row,
    find_alpha_zero_matches,
    find_reappearance,
    validate_phase1_rollout_measurement_fixture,
)
from .png_decode import (
    PNG_DECODER_VERSION,
    PngDecodeError,
    decode_png_rgb,
    load_png_rgb,
)
from .ssim import (
    SsimError,
    SsimResult,
    compare_frames,
    compute_ssim,
    require_natural_variation_pair,
)

__all__ = [
    "CalibrationDatasetError",
    "DetectionResult",
    "Homography",
    "HomographyError",
    "HsvRange",
    "MARKER_DETECTOR_VERSION",
    "MarkerDetectionError",
    "MeasurementError",
    "PNG_DECODER_VERSION",
    "PersonEConfigError",
    "PngDecodeError",
    "ReappearanceResult",
    "SsimError",
    "SsimResult",
    "VisionInputError",
    "build_measurement_document",
    "build_measurement_evidence",
    "build_measurement_row",
    "compare_frames",
    "compute_ssim",
    "decode_png_rgb",
    "decode_png_rgb_bytes",
    "detect_layout_markers",
    "detect_magenta",
    "detect_marker_point",
    "find_alpha_zero_matches",
    "find_reappearance",
    "fit_marker_homography",
    "hash_person_e_config",
    "homography_from_record",
    "load_committed_frame_rgb",
    "load_detector_calibration_dataset",
    "load_person_e_config",
    "load_png_rgb",
    "localize_ground_contact_from_background_pair",
    "localize_marker_top_face",
    "require_live_ready_person_e_config",
    "require_natural_variation_pair",
    "summarize_localization",
    "validate_detection_document",
    "validate_detector_calibration_dataset",
    "validate_detector_calibration_plan",
    "validate_homography_fixture",
    "validate_phase1_rollout_measurement_fixture",
]
