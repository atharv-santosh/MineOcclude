"""The pre-registered result adjudication matrix (authority 14, stage ``A17``).

Seventeen outcome rows, written **before any result exists**. Every reported
claim must map to a permitted interpretation in exactly one row; a claim outside
every permitted interpretation is ``ANALYSIS_CLAIM_OUT_OF_SCOPE``.

The rows are **parsed from the frozen authority markdown** rather than copied
into Python. A hand-copied table is a second source of truth that can drift from
the authority silently; parsing binds the module to the hashed bytes.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from mineocclude.experiment_iii.authority import (
    AUTHORITY_MARKDOWN_PATH,
    verify_authority_binding,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError

__all__ = [
    "ADJUDICATION_ROW_COUNT",
    "NEVER_ESTABLISHED",
    "adjudication_matrix",
    "assert_claim_in_scope",
    "permitted_interpretations",
    "prohibited_interpretations",
]

ADJUDICATION_ROW_COUNT = 17

#: Authority 14: no outcome in the table may establish any of these.
NEVER_ESTABLISHED = (
    "calibrated posterior uncertainty",
    "u2",
    "u3",
    "u4",
    "causal object permanence",
    "universal absence of hidden state",
)

_SECTION = "## 14. Result adjudication matrix (pre-registered)"


def _strip_markup(cell: str) -> str:
    return re.sub(r"[*`]", "", cell).strip()


@lru_cache(maxsize=1)
def adjudication_matrix() -> list[dict[str, Any]]:
    """The 17 frozen rows, parsed from the hashed authority markdown."""
    verify_authority_binding()
    text = AUTHORITY_MARKDOWN_PATH.read_text(encoding="utf-8")
    start = text.index(_SECTION)
    body = text[start:]
    rows: list[dict[str, Any]] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            if rows and not stripped:
                continue
            if rows and not stripped.startswith("|"):
                break
            continue
        cells = [_strip_markup(cell) for cell in stripped.strip("|").split("|")]
        if len(cells) != 7 or not cells[0].isdigit():
            continue
        rows.append(
            {
                "row": int(cells[0]),
                "outcome": cells[1],
                "permitted_interpretation": cells[2],
                "prohibited_interpretation": cells[3],
                "paper_value": cells[4],
                "usable": cells[5],
                "can_close": cells[6],
            }
        )
    if len(rows) != ADJUDICATION_ROW_COUNT:
        raise ExperimentIIIError(
            "ANALYSIS_CLAIM_OUT_OF_SCOPE",
            f"the adjudication matrix has {len(rows)} rows, not "
            f"{ADJUDICATION_ROW_COUNT}; the matrix is pre-registered and frozen",
        )
    if [row["row"] for row in rows] != list(range(1, ADJUDICATION_ROW_COUNT + 1)):
        raise ExperimentIIIError(
            "ANALYSIS_CLAIM_OUT_OF_SCOPE", "adjudication rows are not 1..17 in order"
        )
    return rows


def permitted_interpretations() -> list[str]:
    return [row["permitted_interpretation"] for row in adjudication_matrix()]


def prohibited_interpretations() -> list[str]:
    return [row["prohibited_interpretation"] for row in adjudication_matrix()]


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 3}


def assert_claim_in_scope(claim: str) -> dict[str, Any]:
    """Map a claim to its permitted interpretation, or refuse it.

    A claim matches a row when it is a restatement of that row's permitted
    interpretation: every substantive token of the permitted text is present in
    the claim. That is deliberately strict -- a claim that merely shares a word
    with the table is not in scope.
    """
    lowered = claim.lower()
    for phrase in NEVER_ESTABLISHED:
        if re.search(rf"\b{re.escape(phrase)}\b", lowered):
            raise ExperimentIIIError(
                "ANALYSIS_CLAIM_OUT_OF_SCOPE",
                f"no outcome in the adjudication matrix may establish {phrase!r}",
            )
    claim_tokens = _tokens(claim)
    for row in adjudication_matrix():
        if row["prohibited_interpretation"] not in ("", "-", "—"):
            for part in re.split(r";", row["prohibited_interpretation"]):
                part = part.strip()
                if part and part.lower() in lowered:
                    raise ExperimentIIIError(
                        "ANALYSIS_CLAIM_OUT_OF_SCOPE",
                        f"row {row['row']} prohibits {part!r}",
                    )
        permitted = _tokens(row["permitted_interpretation"])
        if permitted and permitted <= claim_tokens:
            return {
                "row": row["row"],
                "outcome": row["outcome"],
                "permitted_interpretation": row["permitted_interpretation"],
                "in_scope": True,
            }
    raise ExperimentIIIError(
        "ANALYSIS_CLAIM_OUT_OF_SCOPE",
        f"{claim!r} maps to no permitted interpretation in the pre-registered "
        f"{ADJUDICATION_ROW_COUNT}-row adjudication matrix",
    )
