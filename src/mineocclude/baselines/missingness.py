"""Missingness and exclusion audit (Person D).

Execution manual Step 4.5: "Model or tabulate acceptance/missingness by
layout, condition, duration, target bins, and method. Preserve NA
separately from zero." Pass check: "No silent method-specific
population; every missing prediction has a reason code."

``BaselineRow`` already enforces "NA is never zero" structurally -- a
non-applicable row can never carry a numeric prediction (see
``interface.BaselineRow.__post_init__``). What was still missing was
one consolidated tabulation across every baseline/condition, plus an
explicit check that every non-applicable row actually carries a
human-readable reason rather than silently going unexplained.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from mineocclude.baselines.interface import BaselineRow

FrameKey = Tuple[str, str, str, int]


@dataclass(frozen=True)
class MissingnessCell:
    baseline_name: str
    target_name: str
    layout_id: str
    regime: str
    duration_bin: str
    accepted_count: int
    missing_count: int


@dataclass(frozen=True)
class MissingnessExclusionReport:
    cells: Tuple[MissingnessCell, ...]
    rows_missing_reason_code: Tuple[FrameKey, ...]
    """Each entry is (baseline_name, target_name, trajectory_id,
    model_frame_idx) for a non-applicable row whose fit_metadata has no
    non-empty 'reason' key -- a silent, unexplained exclusion."""

    @property
    def has_silent_missingness(self) -> bool:
        return bool(self.rows_missing_reason_code)


def _duration_bin(duration_seconds: Optional[float]) -> str:
    if duration_seconds is None:
        return "unknown"
    return f"{duration_seconds:g}s"


def build_missingness_exclusion_report(
    rows: Sequence[BaselineRow],
) -> MissingnessExclusionReport:
    """Tabulate applicable/non-applicable counts by method and condition.

    Grouping cells are (baseline_name, target_name, layout_id, regime,
    duration_bin); frame-level rows are additionally flagged if a
    non-applicable row's ``fit_metadata`` has no (or an empty) 'reason'
    key, which is the "silent method-specific population" the pass
    check forbids.
    """

    counts: dict[tuple[str, str, str, str, str], list[int]] = defaultdict(
        lambda: [0, 0]
    )
    missing_reason: list[FrameKey] = []

    for row in rows:
        key = (
            row.baseline_name,
            row.target_name,
            row.layout_id,
            row.regime,
            _duration_bin(row.duration_seconds),
        )
        bucket = counts[key]
        if row.applicable:
            bucket[0] += 1
        else:
            bucket[1] += 1
            reason = row.fit_metadata.get("reason")
            if not reason:
                missing_reason.append(
                    (
                        row.baseline_name,
                        row.target_name,
                        row.trajectory_id,
                        row.model_frame_idx,
                    )
                )

    cells = tuple(
        MissingnessCell(
            baseline_name=key[0],
            target_name=key[1],
            layout_id=key[2],
            regime=key[3],
            duration_bin=key[4],
            accepted_count=bucket[0],
            missing_count=bucket[1],
        )
        for key, bucket in sorted(counts.items())
    )
    return MissingnessExclusionReport(
        cells=cells, rows_missing_reason_code=tuple(missing_reason)
    )


def summarize_non_applicable_reasons(rows: Sequence[BaselineRow]) -> dict:
    """Count non-applicable rows by their ``fit_metadata`` reason text.

    Companion to :func:`build_missingness_exclusion_report`: that function
    only flags rows missing a reason entirely (the "silent" case). This
    collects the actual reason strings so a summary report can explain
    *why* a baseline has few or zero applicable rows on some slice of
    data, instead of surfacing a bare zero with no explanation.
    """

    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        if not row.applicable:
            reason = row.fit_metadata.get("reason") or "<no reason recorded>"
            counts[str(reason)] += 1
    return dict(counts)
