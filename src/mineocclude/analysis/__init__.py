"""Person B analysis configuration and statistical utilities."""

from .config import (
    AnalysisConfigError,
    hash_core_analysis_config,
    load_core_analysis_config,
    validate_core_analysis_config,
)
from .filters import (
    FilterRejectionCode,
    FilterResult,
    apply_ordered_filters,
    build_filter_audit_artifact,
)
from .coordinates import (
    CoordinateContractError,
    WallParallelCoordinateFrame,
    validate_coordinate_frame,
)
from .outputs import (
    append_correction,
    build_prediction_artifact,
    build_result_artifact,
    create_correction_log,
)
from .manifests import (
    build_event_manifest,
    require_disjoint_event_sets,
    validate_event_manifest,
)

__all__ = [
    "AnalysisConfigError",
    "hash_core_analysis_config",
    "FilterRejectionCode",
    "FilterResult",
    "apply_ordered_filters",
    "build_filter_audit_artifact",
    "CoordinateContractError",
    "WallParallelCoordinateFrame",
    "validate_coordinate_frame",
    "append_correction",
    "build_prediction_artifact",
    "build_result_artifact",
    "create_correction_log",
    "build_event_manifest",
    "require_disjoint_event_sets",
    "validate_event_manifest",
    "load_core_analysis_config",
    "validate_core_analysis_config",
]
