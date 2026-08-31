"""MineOcclude Experiment III — Graded Partial Observability.

Experiment III-native implementation, bound to the frozen authority package at
``docs/experiment_iii/final_authorities/``. Historical Regime A, Regime A-prime
and Experiment II artifacts are immutable and are never written from here; see
:mod:`mineocclude.experiment_iii.namespace`.

Import order matters only in that :mod:`errors` and :mod:`authority` must be
importable without touching any experiment data.
"""

from __future__ import annotations

from mineocclude.experiment_iii.authority import (
    AUTHORITY_FREEZE_COMMIT,
    FROZEN_AUTHORITY_SHA256,
    RUN_NAMESPACE,
    master_salt,
    verify_authority_binding,
)
from mineocclude.experiment_iii.errors import (
    AuthorityAmendmentRequired,
    ExperimentIIIError,
)
from mineocclude.experiment_iii.namespace import guard_write_path
from mineocclude.experiment_iii.schema import (
    ConditionId,
    ExtentClassName,
    TemporalSlice,
    VisibilityRow,
)

__all__ = [
    "AUTHORITY_FREEZE_COMMIT",
    "AuthorityAmendmentRequired",
    "ConditionId",
    "ExperimentIIIError",
    "ExtentClassName",
    "FROZEN_AUTHORITY_SHA256",
    "RUN_NAMESPACE",
    "TemporalSlice",
    "VisibilityRow",
    "guard_write_path",
    "master_salt",
    "verify_authority_binding",
]

VERSION = "experiment-iii-v1"
