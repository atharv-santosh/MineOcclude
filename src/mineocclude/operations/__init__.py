"""Person E frozen operating layer: reproduction, checkpoint evidence, handoff.

These modules own Phase 7 of the Person E execution manual. They deliberately
carry no scientific logic: they verify that measurement outputs can be
regenerated from declared inputs, that displayed evidence resolves to a real
source artifact, and that a second operator can run the frozen pipelines.
"""

from __future__ import annotations

__all__ = [
    "checkpoint_evidence",
    "clean_reproduction",
    "handoff",
]
