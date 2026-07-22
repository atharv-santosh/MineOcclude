"""Vendored subset of Person B's analysis package.

Only ``config``, ``coordinates``, and ``manifests`` are vendored here
from ``origin/role/person-b-methods`` -- see
``docs/decisions/person_d_phase1_decision_log.md``. This package
intentionally does not re-export ``filters``/``outputs`` (not
vendored, not needed by Person D's baseline code) the way B's real
``analysis/__init__.py`` does; reconcile against B's actual package at
integration time rather than treating this as authoritative.

Import order matters here: ``coordinates`` imports ``manifests``
internally, and ``config``/``manifests`` both import
``mineocclude.contracts.identity``, which in turn pulls in
``mineocclude.contracts.analysis_inputs`` (via ``contracts/__init__.py``),
which imports back into this package. Importing ``config`` then
``coordinates`` here first -- before anything else can reach
``manifests`` through a more roundabout path -- avoids a circular
partial-import failure. Do not reorder these without re-checking that.
"""

from .config import (
    AnalysisConfigError,
    hash_core_analysis_config,
    load_core_analysis_config,
    validate_core_analysis_config,
)
from .coordinates import (
    CoordinateContractError,
    WallParallelCoordinateFrame,
    validate_coordinate_frame,
)
from .manifests import (
    AnalysisArtifactError,
    is_hex_digest,
    seal_artifact,
    sha256_value,
    validate_sealed_artifact,
)

__all__ = [
    "AnalysisConfigError",
    "hash_core_analysis_config",
    "load_core_analysis_config",
    "validate_core_analysis_config",
    "CoordinateContractError",
    "WallParallelCoordinateFrame",
    "validate_coordinate_frame",
    "AnalysisArtifactError",
    "is_hex_digest",
    "seal_artifact",
    "sha256_value",
    "validate_sealed_artifact",
]
