"""Artifact-independent visual measurement foundations owned by Person E."""

from .calibration import (
    CalibrationDatasetError,
    load_detector_calibration_dataset,
    validate_detector_calibration_dataset,
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
    summarize_localization,
)
from .magenta import DetectionResult, HsvRange, VisionInputError, detect_magenta
from .measurement import (
    MeasurementError,
    ReappearanceResult,
    build_measurement_document,
    build_measurement_evidence,
    build_measurement_row,
    find_alpha_zero_matches,
    find_reappearance,
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
    "MeasurementError",
    "PersonEConfigError",
    "ReappearanceResult",
    "SsimError",
    "SsimResult",
    "VisionInputError",
    "build_measurement_document",
    "build_measurement_evidence",
    "build_measurement_row",
    "compare_frames",
    "compute_ssim",
    "detect_magenta",
    "find_alpha_zero_matches",
    "find_reappearance",
    "fit_marker_homography",
    "hash_person_e_config",
    "homography_from_record",
    "load_detector_calibration_dataset",
    "load_person_e_config",
    "require_live_ready_person_e_config",
    "require_natural_variation_pair",
    "summarize_localization",
    "validate_detector_calibration_dataset",
]
