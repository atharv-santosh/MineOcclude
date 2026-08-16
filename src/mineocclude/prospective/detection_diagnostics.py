"""Type-safe detector diagnostics and ambiguity-explicit row joins."""

from __future__ import annotations

import enum
import math
from collections import Counter
from dataclasses import dataclass, field
from numbers import Real
from typing import Iterable, Mapping, Sequence

__all__ = [
    "ConfusionCounts",
    "AgreementReport",
    "agreement_report",
    "DetectionJoinContract",
    "JoinStatus",
    "DetectionJoinReport",
    "join_detection_rows",
]


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _validate_detection_state(value: object, label: str) -> None:
    if value is not None and type(value) is not bool:
        raise TypeError(f"{label} values must be bool or None, not {type(value).__name__}")


@dataclass(frozen=True)
class ConfusionCounts:
    true_positive: int = 0
    false_positive: int = 0
    true_negative: int = 0
    false_negative: int = 0
    undetermined: int = 0

    def __post_init__(self) -> None:
        for name in (
            "true_positive", "false_positive", "true_negative",
            "false_negative", "undetermined",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative plain int")

    @property
    def total(self) -> int:
        return sum(
            (
                self.true_positive,
                self.false_positive,
                self.true_negative,
                self.false_negative,
                self.undetermined,
            )
        )

    @property
    def scored(self) -> int:
        return self.total - self.undetermined


@dataclass
class AgreementReport:
    counts: ConfusionCounts
    by_regime: dict = field(default_factory=dict)
    world_support: dict | None = None

    PREVALENCE_INDEPENDENT = (
        "recall",
        "specificity",
        "false_positive_rate",
        "false_negative_rate",
    )
    PREVALENCE_DEPENDENT = ("precision", "negative_predictive_value", "accuracy")

    def metrics(self) -> dict:
        c = self.counts
        positives = c.true_positive + c.false_negative
        negatives = c.true_negative + c.false_positive
        recall = _ratio(c.true_positive, positives)
        specificity = _ratio(c.true_negative, negatives)
        return {
            "true_positive": c.true_positive,
            "false_positive": c.false_positive,
            "true_negative": c.true_negative,
            "false_negative": c.false_negative,
            "undetermined": c.undetermined,
            "scored_rows": c.scored,
            "recall": recall,
            "specificity": specificity,
            "false_positive_rate": None if specificity is None else 1.0 - specificity,
            "false_negative_rate": None if recall is None else 1.0 - recall,
            "precision": _ratio(c.true_positive, c.true_positive + c.false_positive),
            "negative_predictive_value": _ratio(
                c.true_negative, c.true_negative + c.false_negative
            ),
            "accuracy": _ratio(c.true_positive + c.true_negative, c.scored),
            "balanced_accuracy": (
                None
                if recall is None or specificity is None
                else (recall + specificity) / 2.0
            ),
            "positive_class_prevalence": _ratio(positives, c.scored),
            "negative_class_prevalence": _ratio(negatives, c.scored),
        }

    def to_dict(self) -> dict:
        return {
            "artifact_id": "prospective-detector-agreement-report-v0.2",
            "overall": self.metrics(),
            "by_regime": {
                regime: AgreementReport(counts).metrics()
                for regime, counts in self.by_regime.items()
            },
            "world_support": self.world_support,
            "prevalence_independent_metrics": list(self.PREVALENCE_INDEPENDENT),
            "prevalence_dependent_metrics": list(self.PREVALENCE_DEPENDENT),
            "prevalence_warning": (
                "precision, negative_predictive_value and accuracy move with class "
                "prevalence"
            ),
            "contains_no_pass_fail_judgement": True,
        }


def agreement_report(
    reference: Sequence[bool | None],
    predicted: Sequence[bool | None],
    *,
    regimes: Sequence[str | None] | None = None,
    world_x: Sequence[float] | None = None,
) -> AgreementReport:
    if len(reference) != len(predicted):
        raise ValueError("reference and predicted must have equal length")
    if regimes is not None and len(regimes) != len(reference):
        raise ValueError("regimes must match sample count")
    if world_x is not None and len(world_x) != len(reference):
        raise ValueError("world_x must match sample count")
    for index, value in enumerate(reference):
        _validate_detection_state(value, f"reference[{index}]")
    for index, value in enumerate(predicted):
        _validate_detection_state(value, f"predicted[{index}]")

    def tally(pairs: Iterable[tuple[bool | None, bool | None]]) -> ConfusionCounts:
        tp = fp = tn = fn = un = 0
        for ref, pred in pairs:
            if ref is None or pred is None:
                un += 1
            elif ref is True and pred is True:
                tp += 1
            elif ref is False and pred is True:
                fp += 1
            elif ref is False and pred is False:
                tn += 1
            else:
                fn += 1
        return ConfusionCounts(tp, fp, tn, fn, un)

    overall = tally(zip(reference, predicted))
    by_regime: dict[str, ConfusionCounts] = {}
    if regimes is not None:
        for index, regime in enumerate(regimes):
            if regime is not None and (not isinstance(regime, str) or not regime):
                raise TypeError(f"regimes[{index}] must be a non-empty string or None")
        for name in sorted({regime for regime in regimes if regime is not None}):
            by_regime[name] = tally(
                (ref, pred)
                for ref, pred, regime in zip(reference, predicted, regimes)
                if regime == name
            )

    support = None
    if world_x is not None and len(world_x):
        values: list[float] = []
        for index, value in enumerate(world_x):
            if isinstance(value, bool) or not isinstance(value, Real):
                raise TypeError(f"world_x[{index}] must be a real number")
            converted = float(value)
            if not math.isfinite(converted):
                raise ValueError(f"world_x[{index}] must be finite")
            values.append(converted)
        support = {
            "world_x_min": min(values),
            "world_x_max": max(values),
            "world_x_span": max(values) - min(values),
            "sample_count": len(values),
        }
    return AgreementReport(overall, by_regime, support)


class JoinStatus(enum.Enum):
    VALID = "VALID"
    AMBIGUOUS = "AMBIGUOUS"
    INVALID = "INVALID"


@dataclass(frozen=True)
class DetectionJoinContract:
    """Explicit identity, key, and clock mapping for a D-10 join."""

    identity_fields: tuple[str, ...]
    detector_index_field: str
    reference_index_field: str
    detector_clock_domain: str
    reference_clock_domain: str
    index_mapping: Mapping[int, int] | None

    def __post_init__(self) -> None:
        strings = (
            *self.identity_fields,
            self.detector_index_field,
            self.reference_index_field,
            self.detector_clock_domain,
            self.reference_clock_domain,
        )
        if not self.identity_fields or any(not isinstance(value, str) or not value for value in strings):
            raise ValueError("join fields and clock domains must be explicitly named")


@dataclass
class DetectionJoinReport:
    status: JoinStatus
    pairs: list[tuple[int, int]]
    issues: list[str]
    detector_row_count: int
    reference_row_count: int

    @property
    def valid(self) -> bool:
        return self.status is JoinStatus.VALID

    def to_dict(self) -> dict:
        return {
            "artifact_id": "prospective-detection-d10-join-v0.1",
            "status": self.status.value,
            "valid": self.valid,
            "pairs": [list(pair) for pair in self.pairs],
            "issues": self.issues,
            "detector_row_count": self.detector_row_count,
            "reference_row_count": self.reference_row_count,
        }


def _plain_index(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def join_detection_rows(
    detector_rows: Sequence[Mapping[str, object]],
    reference_rows: Sequence[Mapping[str, object]],
    contract: DetectionJoinContract,
) -> DetectionJoinReport:
    """Join rows without choosing among ambiguous or incompatible candidates."""
    issues: list[str] = []
    ambiguous = False
    if not detector_rows or not reference_rows:
        issues.append("detector and reference rows must both be non-empty")

    if contract.detector_clock_domain != contract.reference_clock_domain and contract.index_mapping is None:
        issues.append("incompatible clock/index domains have no explicit mapping")

    detector_keys: list[tuple[tuple[object, ...], int] | None] = []
    reference_keys: list[tuple[tuple[object, ...], int] | None] = []
    for label, rows, index_field, sink in (
        ("detector", detector_rows, contract.detector_index_field, detector_keys),
        ("reference", reference_rows, contract.reference_index_field, reference_keys),
    ):
        for row_number, row in enumerate(rows):
            missing = [field for field in contract.identity_fields if row.get(field) in (None, "")]
            if missing:
                issues.append(f"{label} row {row_number} missing identity fields {missing}")
                sink.append(None)
                continue
            index = row.get(index_field)
            if not _plain_index(index):
                issues.append(f"{label} row {row_number} missing or invalid {index_field}")
                sink.append(None)
                continue
            sink.append((tuple(row[field] for field in contract.identity_fields), index))

    for label, keys in (("detector", detector_keys), ("reference", reference_keys)):
        duplicates = [key for key, count in Counter(key for key in keys if key is not None).items() if count > 1]
        if duplicates:
            ambiguous = True
            issues.append(f"duplicate {label} identity/timestamp keys: {duplicates}")

    reference_lookup: dict[tuple[tuple[object, ...], int], list[int]] = {}
    for row_number, key in enumerate(reference_keys):
        if key is not None:
            reference_lookup.setdefault(key, []).append(row_number)

    pairs: list[tuple[int, int]] = []
    for detector_number, key in enumerate(detector_keys):
        if key is None:
            continue
        identity, detector_index = key
        if contract.detector_clock_domain == contract.reference_clock_domain:
            reference_index = detector_index
        elif contract.index_mapping is not None and detector_index in contract.index_mapping:
            reference_index = contract.index_mapping[detector_index]
            if not _plain_index(reference_index):
                issues.append(f"mapping for detector index {detector_index} is invalid")
                continue
        else:
            issues.append(f"detector index {detector_index} has no clock mapping")
            continue
        candidates = reference_lookup.get((identity, reference_index), [])
        if len(candidates) == 1:
            pairs.append((detector_number, candidates[0]))
        elif len(candidates) > 1:
            ambiguous = True
            issues.append(
                f"detector row {detector_number} has more than one candidate reference row"
            )
        else:
            issues.append(
                f"detector row {detector_number} has no reference with matching run identity and key"
            )

    if ambiguous:
        status = JoinStatus.AMBIGUOUS
        pairs = []
    elif issues or len(pairs) != len(detector_rows) or len(pairs) != len(reference_rows):
        status = JoinStatus.INVALID
        pairs = []
    else:
        status = JoinStatus.VALID
    return DetectionJoinReport(
        status, pairs, issues, len(detector_rows), len(reference_rows)
    )
