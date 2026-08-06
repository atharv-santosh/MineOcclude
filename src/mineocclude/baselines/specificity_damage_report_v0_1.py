"""Specificity and damage report (Person D Step 7.4).

Execution manual Step 7.4 requires a report pipeline covering the signed
displacement pattern, alpha=0 persistence, positive and negative dose
behavior, random-direction effects, orthogonal-direction effects,
wrong-layer effects, wrong-timestep effects, pushed-versus-unpushed SSIM,
natural unpushed variation, background-masked SSIM, missingness and
non-persistence, and Person B's inferential results -- and forbids
Person D from creating a causal claim threshold.

That prohibition is enforced structurally. Every section carries a
``verdict_owner``, and the only permitted value for a section that could
support or undermine a causal claim is ``person_b``. A section can report
*what was observed* (D's job: counts, coverage, which controls exist and
which are missing) but a section that states whether the observation
supports a causal claim must cite a Person B inferential record; a
Person-D-authored verdict is rejected by the validator.

When Person E's measurements or Person B's inferential outputs are
absent, sections stay structurally empty and explicitly blocked. An empty
section is never rendered as "no effect".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from mineocclude.baselines.u4_measurement_join_v0_1 import (
    CLIP_OUTCOMES,
    validate_u4_control_matrix,
)

SCHEMA_ID = "person-d-specificity-damage-report-v0-1"
SCHEMA_VERSION = "1.0"

#: Every section the report must contain, in rendering order. A section
#: with no data is present and blocked, never omitted.
REQUIRED_SECTION_IDS: tuple[str, ...] = (
    "signed_displacement_pattern",
    "alpha_zero_persistence",
    "positive_dose_behavior",
    "negative_dose_behavior",
    "random_direction_effects",
    "orthogonal_direction_effects",
    "wrong_layer_effects",
    "wrong_timestep_effects",
    "pushed_versus_unpushed_ssim",
    "natural_unpushed_variation",
    "background_masked_ssim",
    "missingness_and_non_persistence",
    "person_b_inferential_results",
)

SECTION_STATUSES: tuple[str, ...] = ("rendered", "blocked")

#: Sections whose content could support or undermine a causal claim.
#: Their verdicts belong to Person B, without exception.
PERSON_B_VERDICT_SECTIONS: frozenset[str] = frozenset(
    {
        "signed_displacement_pattern",
        "positive_dose_behavior",
        "negative_dose_behavior",
        "random_direction_effects",
        "orthogonal_direction_effects",
        "wrong_layer_effects",
        "wrong_timestep_effects",
        "person_b_inferential_results",
    }
)


class SpecificityReportError(ValueError):
    """Raised when a section cannot be rendered honestly."""


@dataclass(frozen=True)
class SectionBlocker:
    """One missing input, named precisely enough to act on."""

    missing_artifact: str
    expected_owner: str
    expected_schema_or_version: str
    exact_command_after_receipt: str


@dataclass(frozen=True)
class DamageSection:
    """One report section.

    ``observed`` holds Person D's descriptive counts. ``verdict`` and
    ``verdict_source_record_id`` hold a Person B inferential conclusion,
    if one exists -- Person D never writes one.
    """

    section_id: str
    title: str
    status: str
    observed: Mapping[str, Any] = field(default_factory=dict)
    verdict: Optional[str] = None
    verdict_owner: Optional[str] = None
    verdict_source_record_id: Optional[str] = None
    blockers: tuple[SectionBlocker, ...] = ()
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in SECTION_STATUSES:
            raise SpecificityReportError(
                f"section {self.section_id!r} has unknown status {self.status!r}"
            )
        if self.status == "blocked":
            if not self.blockers:
                raise SpecificityReportError(
                    f"blocked section {self.section_id!r} names no missing artifact"
                )
            if self.observed:
                raise SpecificityReportError(
                    f"blocked section {self.section_id!r} carries observations; a "
                    "blocked section must be structurally empty"
                )
            if self.verdict:
                raise SpecificityReportError(
                    f"blocked section {self.section_id!r} states a verdict"
                )
        if self.verdict is not None:
            if self.verdict_owner != "person_b":
                raise SpecificityReportError(
                    f"section {self.section_id!r} states a verdict owned by "
                    f"{self.verdict_owner!r}; only Person B may draw a causal "
                    "conclusion, and Person D never creates a claim threshold"
                )
            if not self.verdict_source_record_id:
                raise SpecificityReportError(
                    f"section {self.section_id!r} states a verdict with no Person "
                    "B record to cite"
                )


def blocked_damage_section(
    section_id: str, title: str, blockers: Sequence[SectionBlocker]
) -> DamageSection:
    """Build an explicitly blocked, structurally empty section."""

    return DamageSection(
        section_id=section_id,
        title=title,
        status="blocked",
        blockers=tuple(blockers),
    )


def summarize_control_matrix(matrix: Mapping[str, Any]) -> dict[str, Any]:
    """Produce Person D's descriptive coverage summary of a joined matrix.

    Counts only. There is deliberately no statistic here that could be
    read as an effect size, and no comparison against any threshold.
    """

    validate_u4_control_matrix(matrix)

    by_control_type: dict[str, dict[str, int]] = {}
    for row in matrix["rows"]:
        bucket = by_control_type.setdefault(
            row["control_type"], {outcome: 0 for outcome in CLIP_OUTCOMES}
        )
        bucket[row["outcome"]] += 1

    return {
        "manifest_id": matrix["manifest_id"],
        "manifest_version": matrix["manifest_version"],
        "planned_clip_count": matrix["planned_clip_count"],
        "outcome_counts": dict(matrix["outcome_counts"]),
        "outcome_counts_by_control_type": {
            control_type: dict(sorted(counts.items()))
            for control_type, counts in sorted(by_control_type.items())
        },
        "join_complete": matrix["join_complete"],
        "measured_clip_count": matrix["outcome_counts"]["measured"],
        "non_persistent_clip_count": matrix["outcome_counts"]["non_persistent"],
        "missing_clip_count": matrix["outcome_counts"]["missing"],
    }


def build_specificity_damage_report(
    *,
    sections: Sequence[DamageSection],
    run_id: str,
    control_matrix_run_id: Optional[str],
    person_b_inferential_run_id: Optional[str],
    evidence_kind: str = "synthetic",
) -> dict[str, Any]:
    """Assemble the machine-readable specificity and damage report."""

    if evidence_kind not in ("real", "synthetic"):
        raise SpecificityReportError("evidence_kind must be 'real' or 'synthetic'")

    by_id: dict[str, DamageSection] = {}
    for section in sections:
        if section.section_id in by_id:
            raise SpecificityReportError(f"duplicate section {section.section_id!r}")
        by_id[section.section_id] = section

    missing = [sid for sid in REQUIRED_SECTION_IDS if sid not in by_id]
    if missing:
        raise SpecificityReportError(
            f"report is missing required sections {missing}; a section with no "
            "data must be present and blocked, never omitted"
        )
    unknown = sorted(set(by_id) - set(REQUIRED_SECTION_IDS))
    if unknown:
        raise SpecificityReportError(f"report contains unknown sections {unknown}")

    blocked = [s for s in by_id.values() if s.status == "blocked"]

    return {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "producer_role": "person_d",
        "run_id": run_id,
        "evidence_kind": evidence_kind,
        "control_matrix_run_id": control_matrix_run_id,
        "person_b_inferential_run_id": person_b_inferential_run_id,
        "causal_threshold_owner": "person_b",
        "person_d_created_any_causal_threshold": False,
        "section_count": len(by_id),
        "blocked_section_count": len(blocked),
        "report_complete": not blocked,
        "sections": tuple(
            _section_to_dict(by_id[section_id]) for section_id in REQUIRED_SECTION_IDS
        ),
        "blockers": tuple(
            {
                "section_id": section.section_id,
                "missing_artifact": blocker.missing_artifact,
                "expected_owner": blocker.expected_owner,
                "expected_schema_or_version": blocker.expected_schema_or_version,
                "exact_command_after_receipt": blocker.exact_command_after_receipt,
            }
            for section in sorted(blocked, key=lambda s: s.section_id)
            for blocker in section.blockers
        ),
    }


def _section_to_dict(section: DamageSection) -> dict[str, Any]:
    return {
        "section_id": section.section_id,
        "title": section.title,
        "status": section.status,
        "observed": dict(sorted(section.observed.items())),
        "verdict": section.verdict,
        "verdict_owner": section.verdict_owner,
        "verdict_source_record_id": section.verdict_source_record_id,
        "blockers": [
            {
                "missing_artifact": blocker.missing_artifact,
                "expected_owner": blocker.expected_owner,
                "expected_schema_or_version": blocker.expected_schema_or_version,
                "exact_command_after_receipt": blocker.exact_command_after_receipt,
            }
            for blocker in section.blockers
        ],
        "notes": list(section.notes),
    }


def validate_specificity_damage_report(document: Mapping[str, Any]) -> None:
    """Validate the report, raising on the first violation."""

    if document.get("schema_id") != SCHEMA_ID:
        raise SpecificityReportError(
            f"expected schema_id {SCHEMA_ID!r}, got {document.get('schema_id')!r}"
        )
    if document.get("evidence_kind") not in ("real", "synthetic"):
        raise SpecificityReportError("evidence_kind must be 'real' or 'synthetic'")
    if document.get("causal_threshold_owner") != "person_b":
        raise SpecificityReportError("the causal threshold owner must be person_b")
    if document.get("person_d_created_any_causal_threshold"):
        raise SpecificityReportError(
            "Person D must not create a causal claim threshold"
        )

    section_ids = tuple(s["section_id"] for s in document.get("sections", ()))
    if section_ids != REQUIRED_SECTION_IDS:
        raise SpecificityReportError(
            f"sections must be present exactly once in the frozen order "
            f"{REQUIRED_SECTION_IDS}, got {section_ids}"
        )

    for section in document["sections"]:
        if section["status"] not in SECTION_STATUSES:
            raise SpecificityReportError(
                f"section {section['section_id']!r} has unknown status "
                f"{section['status']!r}"
            )
        if section["status"] == "blocked":
            if not section["blockers"]:
                raise SpecificityReportError(
                    f"blocked section {section['section_id']!r} names no missing "
                    "artifact"
                )
            if section["observed"]:
                raise SpecificityReportError(
                    f"blocked section {section['section_id']!r} carries "
                    "observations"
                )
            for blocker in section["blockers"]:
                for required in (
                    "missing_artifact",
                    "expected_owner",
                    "expected_schema_or_version",
                    "exact_command_after_receipt",
                ):
                    if not blocker.get(required):
                        raise SpecificityReportError(
                            f"blocker in {section['section_id']!r} is missing "
                            f"{required!r}"
                        )
        if section["verdict"] is not None:
            if section["verdict_owner"] != "person_b":
                raise SpecificityReportError(
                    f"section {section['section_id']!r} carries a verdict not "
                    "owned by Person B"
                )
            if not section["verdict_source_record_id"]:
                raise SpecificityReportError(
                    f"section {section['section_id']!r} carries a verdict with "
                    "no Person B record"
                )

    blocked = [s for s in document["sections"] if s["status"] == "blocked"]
    if document.get("report_complete") != (not blocked):
        raise SpecificityReportError(
            "report_complete must be false whenever any section is blocked"
        )


def dump_specificity_damage_report(document: Mapping[str, Any]) -> str:
    """Serialize a validated report deterministically."""

    validate_specificity_damage_report(document)
    return json.dumps(document, indent=2, sort_keys=True, default=_json_default) + "\n"


def _json_default(value: Any) -> Any:
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


__all__ = [
    "PERSON_B_VERDICT_SECTIONS",
    "REQUIRED_SECTION_IDS",
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "SECTION_STATUSES",
    "DamageSection",
    "SectionBlocker",
    "SpecificityReportError",
    "blocked_damage_section",
    "build_specificity_damage_report",
    "dump_specificity_damage_report",
    "summarize_control_matrix",
    "validate_specificity_damage_report",
]
