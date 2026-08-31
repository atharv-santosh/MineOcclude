"""Blocker-code validation against the frozen taxonomy (BLOCKER_TAXONOMY.json).

Every raised failure must carry a code from the taxonomy. Inventing an ad hoc
name when the authority already defines one is itself a defect, so
:func:`validate_blocker_code` is the single admission point and
:func:`assert_error_codes_are_known` sweeps a whole receipt.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Iterable, Mapping

from mineocclude.experiment_iii.authority import AUTHORITY_ROOT
from mineocclude.experiment_iii.errors import ExperimentIIIError

__all__ = [
    "TAXONOMY_PATH",
    "blocker_taxonomy",
    "blocker_codes",
    "blocker",
    "validate_blocker_code",
    "assert_error_codes_are_known",
    "severity_of",
    "is_terminal",
]

TAXONOMY_PATH = AUTHORITY_ROOT / "BLOCKER_TAXONOMY.json"


@lru_cache(maxsize=1)
def blocker_taxonomy() -> dict[str, Any]:
    if not TAXONOMY_PATH.is_file():
        raise ExperimentIIIError(
            "AUTHORITY_INCOMPLETE", f"blocker taxonomy is absent: {TAXONOMY_PATH}"
        )
    return json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _by_code() -> dict[str, dict[str, Any]]:
    return {row["code"]: row for row in blocker_taxonomy()["blockers"]}


def blocker_codes() -> frozenset[str]:
    return frozenset(_by_code())


def blocker(code: str) -> dict[str, Any]:
    """The taxonomy entry for one code."""
    entry = _by_code().get(code)
    if entry is None:
        raise ExperimentIIIError(
            "STATUS_BLOCKER_CODE_UNKNOWN",
            f"{code!r} is not a code in BLOCKER_TAXONOMY.json",
        )
    return entry


def validate_blocker_code(code: str | None) -> str | None:
    """``None`` or a valid taxonomy code; anything else is refused."""
    if code is None:
        return None
    if not isinstance(code, str) or code not in _by_code():
        raise ExperimentIIIError(
            "STATUS_BLOCKER_CODE_UNKNOWN",
            f"{code!r} is not a code in BLOCKER_TAXONOMY.json; never invent a "
            "blocker name when the authority already defines one",
        )
    return code


def severity_of(code: str) -> str:
    return blocker(code)["severity"]


def is_terminal(code: str) -> bool:
    return bool(blocker(code)["terminal_if_unresolved"])


def assert_error_codes_are_known(codes: Iterable[str]) -> None:
    unknown = sorted({code for code in codes if code not in _by_code()})
    if unknown:
        raise ExperimentIIIError(
            "STATUS_BLOCKER_CODE_UNKNOWN",
            f"unknown blocker codes: {unknown}",
        )
