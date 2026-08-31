"""Fail-closed Experiment III error type.

Every Experiment III failure carries a blocker code from
``docs/experiment_iii/final_authorities/BLOCKER_TAXONOMY.json``. The code is
validated lazily against the taxonomy by
:mod:`mineocclude.experiment_iii.blockers` so this module stays importable with
no filesystem access, which the namespace guard needs.
"""

from __future__ import annotations

__all__ = ["ExperimentIIIError", "AuthorityAmendmentRequired"]


class ExperimentIIIError(RuntimeError):
    """A fail-closed Experiment III contract violation.

    ``blocker`` is the authority blocker code. It is carried on the exception
    rather than embedded in the message so callers can branch on the code and
    receipts can record it verbatim.
    """

    def __init__(self, blocker: str, message: str) -> None:
        if not isinstance(blocker, str) or not blocker:
            raise ValueError("an Experiment III failure requires a blocker code")
        super().__init__(f"{blocker}: {message}")
        self.blocker = blocker
        self.message = message


class AuthorityAmendmentRequired(ExperimentIIIError):
    """A frozen scientific value would have to change to proceed."""

    def __init__(self, message: str) -> None:
        super().__init__("AUTHORITY_AMENDMENT_REQUIRED", message)
