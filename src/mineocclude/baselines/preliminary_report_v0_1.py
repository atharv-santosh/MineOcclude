"""Preliminary comparison report pipeline (Person D Step 6.4).

Execution manual Step 6.4 requires a *machine-generated* report covering
U1 versus last-seen and the shuffled floor, U2 versus time-only and the
visible-history spread, the raw-pixel comparison, the visible positive
control, the no-object negative control, the known-q oracle ceiling,
failed controls, NA and missing cells, the sample unit, the uncertainty
type, the frozen metric identity, and planning-versus-scientific
thresholds. The report must regenerate solely from registered
machine-readable predictions and Person B-owned metric outputs.

The hard rule this module enforces is: **no manually copied scientific
number.** Every numeric value in a rendered section must arrive through
``MetricValue`` carrying the ID of the registered B-owned metric record
it came from. A section built without a source reference is rejected,
not rendered with a footnote.

Person D also never invents a threshold. Two threshold kinds exist and
are kept apart by construction:

* ``scientific`` -- owned by Person B, copied verbatim from the frozen
  ``person-b-step4-1-final-comparison-contract-v0-1`` acceptance gates,
  and never edited here.
* ``planning`` -- Person D's own operational readiness targets (is the
  pipeline complete enough to run?). These can never appear in a
  scientific verdict field; the validator rejects a report that mixes
  them.

Sections whose real inputs do not exist yet are rendered *structurally
empty and explicitly blocked*, naming the missing artifact and its
owner, rather than being omitted or filled with a placeholder number.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from mineocclude.baselines.grouped_nulls_v0_1 import (
    FROZEN_LOSS_BY_TARGET,
    FROZEN_OBJECTIVE_BASELINES,
    FROZEN_RESAMPLING_UNIT,
    FROZEN_SAMPLE_UNIT,
    PERSON_B_FINAL_COMPARISON_CONTRACT_ID,
)
from mineocclude.baselines.missingness_audit_v0_1 import comparison_class_for

SCHEMA_ID = "person-d-preliminary-comparison-report-v0-1"
SCHEMA_VERSION = "1.0"

#: Person B owns every scientific threshold. Copied verbatim from
#: ``acceptance_contract.scientific_gates`` in Person B's frozen final
#: comparison contract; Person D restates them for provenance and never
#: alters, relaxes, or supplements them.
PERSON_B_SCIENTIFIC_THRESHOLDS: Mapping[str, Mapping[str, Any]] = {
    "U1_green": {
        "held_out_r2_strictly_greater_than": 0.0,
        "max_t_adjusted_p_strictly_less_than": 0.01,
        "paired_loss_improvement_strictly_greater_than": 0.0,
        "required_primary_baselines": ("last_seen", "grouped_shuffled"),
    },
    "U2_green": {
        "average_absolute_coverage_error_at_most": 0.1,
        "coverage_error_strictly_better_than": ("time_only", "visible_history_q"),
        "coverage_levels": (0.5, 0.8, 0.95),
        "partial_correlation_bootstrap_ci_lower_strictly_greater_than": 0.0,
    },
}

#: Person D's own *operational* readiness targets. They answer "is the
#: pipeline ready to run?", never "did the science work?". Keeping them
#: in a separate namespace is what makes the mixing check enforceable.
PERSON_D_PLANNING_THRESHOLDS: Mapping[str, Any] = {
    "minimum_accepted_trajectories_to_execute": 2,
    "minimum_layouts_for_layout_macro_aggregation": 2,
    "maximum_tolerated_missing_prediction_fraction": 0.0,
}

#: The frozen uncertainty machinery, from B's ``confidence_interval_contract``.
FROZEN_UNCERTAINTY_TYPE = "equal_tailed_percentile_bootstrap"
FROZEN_BOOTSTRAP_COUNT = 2000
FROZEN_BOOTSTRAP_COVERAGE = 0.95
FROZEN_BOOTSTRAP_UNIT = "whole_layout_then_whole_trajectory"

#: Every section the report must contain, in rendering order. A report
#: missing any of these is incomplete, not merely shorter.
REQUIRED_SECTION_IDS: tuple[str, ...] = (
    "u1_vs_last_seen",
    "u1_vs_grouped_shuffled_floor",
    "u2_vs_time_only",
    "u2_vs_visible_history_spread",
    "raw_pixel_comparison",
    "visible_positive_control",
    "no_object_negative_control",
    "known_q_oracle_ceiling",
    "failed_controls",
    "na_and_missing_cells",
)

SECTION_STATUSES: tuple[str, ...] = ("rendered", "blocked", "not_applicable")


class PreliminaryReportError(ValueError):
    """Raised when a report section cannot be generated honestly."""


@dataclass(frozen=True)
class MetricValue:
    """One numeric value, bound to the registered record it came from.

    ``source_record_id`` and ``source_sha256`` are mandatory. A value
    with no registered source cannot be constructed at all, which is how
    "no manually copied scientific number" is enforced structurally
    rather than by review.
    """

    metric_id: str
    value: float
    unit: str
    sample_count: int
    sample_unit: str
    source_record_id: str
    source_sha256: str
    owner_role: str = "person_b"

    def __post_init__(self) -> None:
        if not self.source_record_id or not self.source_sha256:
            raise PreliminaryReportError(
                f"metric {self.metric_id!r} has no registered source record; "
                "every scientific number must trace to a machine-readable "
                "registered artifact, never to a hand-copied figure"
            )
        if len(self.source_sha256) != 64:
            raise PreliminaryReportError(
                f"metric {self.metric_id!r} source_sha256 is not a SHA-256"
            )
        if self.owner_role not in ("person_b", "person_d", "person_e"):
            raise PreliminaryReportError(
                f"metric {self.metric_id!r} has unknown owner_role {self.owner_role!r}"
            )


@dataclass(frozen=True)
class Blocker:
    """One missing real input, named precisely enough to act on."""

    missing_artifact: str
    expected_owner: str
    expected_schema_or_version: str
    required_identity_fields: tuple[str, ...]
    exact_command_after_receipt: str


@dataclass(frozen=True)
class ReportSection:
    """One report section: rendered from registered values, or blocked."""

    section_id: str
    title: str
    comparison_kind: str
    status: str
    methods: tuple[str, ...] = ()
    target_name: Optional[str] = None
    values: tuple[MetricValue, ...] = ()
    na_count: int = 0
    missing_count: int = 0
    blockers: tuple[Blocker, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.status not in SECTION_STATUSES:
            raise PreliminaryReportError(
                f"section {self.section_id!r} has unknown status {self.status!r}"
            )
        if self.status == "rendered" and not self.values:
            raise PreliminaryReportError(
                f"section {self.section_id!r} claims to be rendered but carries "
                "no registered metric value; an empty section must be marked "
                "'blocked' with a named missing artifact instead"
            )
        if self.status == "blocked" and not self.blockers:
            raise PreliminaryReportError(
                f"section {self.section_id!r} is blocked but names no missing "
                "artifact; a blocker must be actionable"
            )
        if self.status == "blocked" and self.values:
            raise PreliminaryReportError(
                f"section {self.section_id!r} is blocked but carries metric "
                "values; a blocked section must be structurally empty"
            )
        for method in self.methods:
            comparison_class_for(method)


def blocked_section(
    section_id: str,
    title: str,
    comparison_kind: str,
    *,
    methods: Sequence[str] = (),
    target_name: Optional[str] = None,
    blockers: Sequence[Blocker],
    notes: Sequence[str] = (),
) -> ReportSection:
    """Build an explicitly blocked, structurally empty section."""

    return ReportSection(
        section_id=section_id,
        title=title,
        comparison_kind=comparison_kind,
        status="blocked",
        methods=tuple(methods),
        target_name=target_name,
        blockers=tuple(blockers),
        notes=tuple(notes),
    )


def build_preliminary_report(
    *,
    sections: Sequence[ReportSection],
    run_id: str,
    prediction_run_ids: Sequence[str],
    metric_run_ids: Sequence[str],
    accepted_manifest_sha256: Optional[str],
    fold_manifest_sha256: Optional[str],
    evidence_kind: str = "synthetic",
) -> dict[str, Any]:
    """Assemble the machine-generated preliminary comparison report.

    Requires every section in :data:`REQUIRED_SECTION_IDS` to be present
    exactly once. A section may be ``blocked``; it may not be absent,
    because an absent section is indistinguishable from a section someone
    chose not to show.
    """

    if evidence_kind not in ("real", "synthetic"):
        raise PreliminaryReportError("evidence_kind must be 'real' or 'synthetic'")

    by_id: dict[str, ReportSection] = {}
    for section in sections:
        if section.section_id in by_id:
            raise PreliminaryReportError(
                f"duplicate section {section.section_id!r}"
            )
        by_id[section.section_id] = section

    missing_sections = [sid for sid in REQUIRED_SECTION_IDS if sid not in by_id]
    if missing_sections:
        raise PreliminaryReportError(
            f"report is missing required sections {missing_sections}; a section "
            "with no real inputs must be present and blocked, never omitted"
        )
    unknown_sections = sorted(set(by_id) - set(REQUIRED_SECTION_IDS))
    if unknown_sections:
        raise PreliminaryReportError(
            f"report contains unknown sections {unknown_sections}"
        )

    rendered = [s for s in by_id.values() if s.status == "rendered"]
    blocked = [s for s in by_id.values() if s.status == "blocked"]

    all_blockers: list[Blocker] = []
    for section in sorted(blocked, key=lambda s: s.section_id):
        all_blockers.extend(section.blockers)

    document: dict[str, Any] = {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "producer_role": "person_d",
        "run_id": run_id,
        "evidence_kind": evidence_kind,
        "generated_from_registered_sources_only": True,
        "manual_scientific_values_present": False,
        "person_b_contract_id": PERSON_B_FINAL_COMPARISON_CONTRACT_ID,
        "metric_identity": {
            "primary_statistic": "layout_macro_paired_loss_improvement",
            "loss_by_target": dict(sorted(FROZEN_LOSS_BY_TARGET.items())),
            "positive_direction": "probe_better",
            "owner_role": "person_b",
        },
        "sample_unit": FROZEN_SAMPLE_UNIT,
        "resampling_unit": FROZEN_RESAMPLING_UNIT,
        "uncertainty": {
            "type": FROZEN_UNCERTAINTY_TYPE,
            "bootstrap_count": FROZEN_BOOTSTRAP_COUNT,
            "coverage": FROZEN_BOOTSTRAP_COVERAGE,
            "unit": FROZEN_BOOTSTRAP_UNIT,
            "owner_role": "person_b",
        },
        "scientific_thresholds": {
            "owner_role": "person_b",
            "source_contract_id": PERSON_B_FINAL_COMPARISON_CONTRACT_ID,
            "gates": _plain(PERSON_B_SCIENTIFIC_THRESHOLDS),
        },
        "planning_thresholds": {
            "owner_role": "person_d",
            "scope": "operational_readiness_only_never_a_scientific_verdict",
            "targets": dict(sorted(PERSON_D_PLANNING_THRESHOLDS.items())),
        },
        "objective_baselines": {
            key: list(value) for key, value in sorted(FROZEN_OBJECTIVE_BASELINES.items())
        },
        "prediction_run_ids": tuple(sorted(set(prediction_run_ids))),
        "metric_run_ids": tuple(sorted(set(metric_run_ids))),
        "accepted_manifest_sha256": accepted_manifest_sha256,
        "fold_manifest_sha256": fold_manifest_sha256,
        "section_count": len(by_id),
        "rendered_section_count": len(rendered),
        "blocked_section_count": len(blocked),
        "sections": tuple(
            _section_to_dict(by_id[section_id]) for section_id in REQUIRED_SECTION_IDS
        ),
        "blockers": tuple(
            {
                "missing_artifact": blocker.missing_artifact,
                "expected_owner": blocker.expected_owner,
                "expected_schema_or_version": blocker.expected_schema_or_version,
                "required_identity_fields": list(blocker.required_identity_fields),
                "exact_command_after_receipt": blocker.exact_command_after_receipt,
            }
            for blocker in all_blockers
        ),
        "totals": {
            "na_cells": sum(section.na_count for section in by_id.values()),
            "missing_cells": sum(section.missing_count for section in by_id.values()),
        },
    }
    document["report_complete"] = not blocked
    return document


def _section_to_dict(section: ReportSection) -> dict[str, Any]:
    return {
        "section_id": section.section_id,
        "title": section.title,
        "comparison_kind": section.comparison_kind,
        "status": section.status,
        "methods": list(section.methods),
        "comparison_classes": [comparison_class_for(m) for m in section.methods],
        "target_name": section.target_name,
        "values": [
            {
                "metric_id": value.metric_id,
                "value": value.value,
                "unit": value.unit,
                "sample_count": value.sample_count,
                "sample_unit": value.sample_unit,
                "source_record_id": value.source_record_id,
                "source_sha256": value.source_sha256,
                "owner_role": value.owner_role,
            }
            for value in section.values
        ],
        "na_count": section.na_count,
        "missing_count": section.missing_count,
        "blockers": [
            {
                "missing_artifact": blocker.missing_artifact,
                "expected_owner": blocker.expected_owner,
                "expected_schema_or_version": blocker.expected_schema_or_version,
                "required_identity_fields": list(blocker.required_identity_fields),
                "exact_command_after_receipt": blocker.exact_command_after_receipt,
            }
            for blocker in section.blockers
        ],
        "notes": list(section.notes),
    }


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in sorted(value.items())}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def validate_preliminary_report(document: Mapping[str, Any]) -> None:
    """Validate a preliminary report, raising on the first violation."""

    if document.get("schema_id") != SCHEMA_ID:
        raise PreliminaryReportError(
            f"expected schema_id {SCHEMA_ID!r}, got {document.get('schema_id')!r}"
        )
    if document.get("evidence_kind") not in ("real", "synthetic"):
        raise PreliminaryReportError("evidence_kind must be 'real' or 'synthetic'")
    if document.get("manual_scientific_values_present"):
        raise PreliminaryReportError(
            "a report containing manually copied scientific values is not "
            "publishable; regenerate it from the registered sources"
        )

    section_ids = [section["section_id"] for section in document.get("sections", ())]
    if tuple(section_ids) != REQUIRED_SECTION_IDS:
        raise PreliminaryReportError(
            "sections must be present exactly once in the frozen order "
            f"{REQUIRED_SECTION_IDS}, got {tuple(section_ids)}"
        )

    for section in document["sections"]:
        if section["status"] not in SECTION_STATUSES:
            raise PreliminaryReportError(
                f"section {section['section_id']!r} has unknown status "
                f"{section['status']!r}"
            )
        if section["status"] == "rendered":
            if not section["values"]:
                raise PreliminaryReportError(
                    f"rendered section {section['section_id']!r} has no values"
                )
            for value in section["values"]:
                if not value.get("source_record_id") or not value.get("source_sha256"):
                    raise PreliminaryReportError(
                        f"section {section['section_id']!r} contains a value with "
                        "no registered source; that is a hand-copied number"
                    )
                if not value.get("sample_unit"):
                    raise PreliminaryReportError(
                        f"section {section['section_id']!r} value "
                        f"{value['metric_id']!r} declares no sample unit"
                    )
        elif section["status"] == "blocked":
            if section["values"]:
                raise PreliminaryReportError(
                    f"blocked section {section['section_id']!r} carries values"
                )
            if not section["blockers"]:
                raise PreliminaryReportError(
                    f"blocked section {section['section_id']!r} names no missing "
                    "artifact"
                )
            for blocker in section["blockers"]:
                for required in (
                    "missing_artifact",
                    "expected_owner",
                    "expected_schema_or_version",
                    "exact_command_after_receipt",
                ):
                    if not blocker.get(required):
                        raise PreliminaryReportError(
                            f"blocker in section {section['section_id']!r} is "
                            f"missing {required!r}"
                        )

    scientific = document.get("scientific_thresholds", {})
    planning = document.get("planning_thresholds", {})
    if scientific.get("owner_role") != "person_b":
        raise PreliminaryReportError("scientific thresholds must be owned by person_b")
    if planning.get("owner_role") != "person_d":
        raise PreliminaryReportError("planning thresholds must be owned by person_d")
    overlap = set(scientific.get("gates", {})) & set(planning.get("targets", {}))
    if overlap:
        raise PreliminaryReportError(
            f"planning and scientific thresholds share keys {sorted(overlap)}; a "
            "planning target must never be readable as a scientific gate"
        )

    if document.get("resampling_unit") != FROZEN_RESAMPLING_UNIT:
        raise PreliminaryReportError("resampling_unit must be Person B's frozen unit")
    if document.get("uncertainty", {}).get("owner_role") != "person_b":
        raise PreliminaryReportError("uncertainty specification must be owned by person_b")

    blocked = [s for s in document["sections"] if s["status"] == "blocked"]
    if document.get("report_complete") != (not blocked):
        raise PreliminaryReportError(
            "report_complete must be false whenever any section is blocked"
        )


def dump_preliminary_report(document: Mapping[str, Any]) -> str:
    """Serialize a validated report deterministically."""

    validate_preliminary_report(document)
    return json.dumps(document, indent=2, sort_keys=True, default=_json_default) + "\n"


def _json_default(value: Any) -> Any:
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


__all__ = [
    "FROZEN_BOOTSTRAP_COUNT",
    "FROZEN_BOOTSTRAP_COVERAGE",
    "FROZEN_UNCERTAINTY_TYPE",
    "PERSON_B_SCIENTIFIC_THRESHOLDS",
    "PERSON_D_PLANNING_THRESHOLDS",
    "REQUIRED_SECTION_IDS",
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "SECTION_STATUSES",
    "Blocker",
    "MetricValue",
    "PreliminaryReportError",
    "ReportSection",
    "blocked_section",
    "build_preliminary_report",
    "dump_preliminary_report",
    "validate_preliminary_report",
]
