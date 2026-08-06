"""Schema versions for the Person E report envelopes exchanged between stages.

These live outside the algorithm modules on purpose. ``vision/homography.py``
and the other measurement implementations are byte-pinned by frozen evidence
packages (see ``docs/status/person_e_phase2_step2_4_v0_4/``), so a report
envelope version — which is a handoff contract, not an algorithm — must not be
added there or the frozen runtime identity would change.

Producers and consumers of a report both import the version from here so the
two cannot drift apart, which is exactly the failure that broke the U4
composition when ``fit_homographies.py`` emitted v0.3 while
``localize_u4_frames.py`` still accepted v0.2.
"""

from __future__ import annotations

#: Emitted by ``scripts/fit_homographies.py``, required by
#: ``scripts/localize_u4_frames.py``.
HOMOGRAPHY_REPORT_SCHEMA_VERSION = "person-e-homography-report-v0.3"

__all__ = ["HOMOGRAPHY_REPORT_SCHEMA_VERSION"]
