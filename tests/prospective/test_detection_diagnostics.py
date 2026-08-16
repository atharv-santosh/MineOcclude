"""Base-rate, type-safety, and D-10 join diagnostics."""

import math
import pytest

from mineocclude.prospective.detection_diagnostics import (
    ConfusionCounts,
    DetectionJoinContract,
    JoinStatus,
    agreement_report,
    join_detection_rows,
)


def test_confusion_count_objects_reject_invalid_counts():
    with pytest.raises(ValueError):
        ConfusionCounts(true_positive=-1)
    with pytest.raises(ValueError):
        ConfusionCounts(false_positive=True)


def _cohort(n_visible, n_occluded, false_positive_rate, recall=1.0):
    """Reference/predicted sequences with a fixed per-class error rate."""
    reference, predicted = [], []
    n_fn = round(n_visible * (1 - recall))
    for i in range(n_visible):
        reference.append(True)
        predicted.append(i >= n_fn)
    n_fp = round(n_occluded * false_positive_rate)
    for i in range(n_occluded):
        reference.append(False)
        predicted.append(i < n_fp)
    return reference, predicted


def test_precision_moves_with_prevalence_while_error_rate_is_fixed():
    """The P3 confound, reproduced exactly: identical detector, three
    prevalences, precision rises from ~0.85 to ~0.94 with no improvement."""
    precisions, fp_rates = [], []
    # occluded counts are multiples of 100 so the modelled FP rate is exact
    for n_visible, n_occluded in ((288, 400), (383, 300), (438, 200)):
        reference, predicted = _cohort(n_visible, n_occluded, 0.11)
        metrics = agreement_report(reference, predicted).metrics()
        precisions.append(metrics["precision"])
        fp_rates.append(metrics["false_positive_rate"])
    assert precisions[0] < precisions[1] < precisions[2]
    assert precisions[0] < 0.90 and precisions[2] > 0.92
    assert max(fp_rates) - min(fp_rates) < 1e-9   # detector is unchanged


def test_prevalence_independent_metrics_are_stable_across_prevalence():
    a = agreement_report(*_cohort(288, 400, 0.11)).metrics()
    b = agreement_report(*_cohort(438, 200, 0.11)).metrics()
    assert a["specificity"] == pytest.approx(b["specificity"], abs=1e-3)
    assert a["recall"] == pytest.approx(b["recall"], abs=1e-3)
    assert a["positive_class_prevalence"] != pytest.approx(b["positive_class_prevalence"])


def test_report_labels_which_metrics_are_prevalence_dependent():
    report = agreement_report(*_cohort(100, 100, 0.1)).to_dict()
    assert "precision" in report["prevalence_dependent_metrics"]
    assert "accuracy" in report["prevalence_dependent_metrics"]
    assert "specificity" in report["prevalence_independent_metrics"]
    assert "recall" in report["prevalence_independent_metrics"]
    assert "prevalence" in report["prevalence_warning"]


def test_report_contains_no_pass_fail_judgement():
    report = agreement_report(*_cohort(100, 100, 0.1)).to_dict()
    assert report["contains_no_pass_fail_judgement"] is True
    assert not any(k in report for k in ("status", "passed", "verdict", "threshold"))


def test_undetermined_samples_are_counted_not_coerced():
    metrics = agreement_report([True, False, None, True], [True, None, False, False]).metrics()
    assert metrics["undetermined"] == 2
    assert metrics["scored_rows"] == 2
    assert metrics["true_positive"] == 1
    assert metrics["false_negative"] == 1


def test_stratification_by_regime_separates_the_transition_band():
    reference = [True] * 4 + [False] * 4 + [False] * 4
    predicted = [True] * 4 + [False] * 4 + [True] * 4
    regimes = ["stable_visible"] * 4 + ["stable_occluded"] * 4 + ["partial_transition"] * 4
    report = agreement_report(reference, predicted, regimes=regimes).to_dict()
    assert report["by_regime"]["stable_visible"]["recall"] == 1.0
    assert report["by_regime"]["stable_occluded"]["specificity"] == 1.0
    assert report["by_regime"]["partial_transition"]["specificity"] == 0.0
    # pooled precision is dragged down purely by the transition band
    assert report["overall"]["precision"] == pytest.approx(0.5)


def test_world_support_is_reported_with_the_confusion_structure():
    report = agreement_report([True, False], [True, False], world_x=[-4.8, 5.9]).to_dict()
    support = report["world_support"]
    assert support["world_x_min"] == pytest.approx(-4.8)
    assert support["world_x_max"] == pytest.approx(5.9)
    assert support["world_x_span"] == pytest.approx(10.7)


def test_length_mismatches_rejected():
    with pytest.raises(ValueError):
        agreement_report([True], [True, False])
    with pytest.raises(ValueError):
        agreement_report([True], [True], regimes=["a", "b"])


def test_empty_class_yields_none_rather_than_a_fabricated_rate():
    metrics = agreement_report([True, True], [True, True]).metrics()
    assert metrics["specificity"] is None
    assert metrics["recall"] == 1.0


@pytest.mark.parametrize(
    "bad",
    ["false", "", 0, 1, 0.0, 1.0, math.nan, [], {}, object()],
)
def test_detection_state_rejects_every_non_bool_non_none_type(bad):
    with pytest.raises(TypeError):
        agreement_report([bad], [True])
    with pytest.raises(TypeError):
        agreement_report([True], [bad])


def _contract(*, same_clock=True, mapping=None):
    return DetectionJoinContract(
        identity_fields=("scientific_run_id", "episode_id", "scene", "target_id"),
        detector_index_field="model_frame_idx",
        reference_index_field="server_tick",
        detector_clock_domain="model_frame" if not same_clock else "shared",
        reference_clock_domain="server_tick" if not same_clock else "shared",
        index_mapping=mapping,
    )


def _row(index=3, run="run-a"):
    return {
        "scientific_run_id": run,
        "episode_id": 7,
        "scene": "NORMAL",
        "target_id": "sheep-1",
        "model_frame_idx": index,
        "server_tick": index,
    }


def test_d10_unique_explicit_join_is_valid():
    report = join_detection_rows([_row()], [_row()], _contract())
    assert report.status is JoinStatus.VALID
    assert report.pairs == [(0, 0)]


@pytest.mark.parametrize("side", ["detector", "reference"])
def test_d10_duplicate_identity_timestamp_is_ambiguous(side):
    detector, reference = [_row()], [_row()]
    if side == "detector":
        detector *= 2
    else:
        reference *= 2
    report = join_detection_rows(detector, reference, _contract())
    assert report.status is JoinStatus.AMBIGUOUS
    assert report.pairs == []


def test_d10_mismatched_run_identity_fails_closed():
    report = join_detection_rows([_row(run="a")], [_row(run="b")], _contract())
    assert report.status is JoinStatus.INVALID
    assert report.pairs == []


@pytest.mark.parametrize("field", ["scientific_run_id", "episode_id", "scene", "target_id"])
def test_d10_missing_identity_fails_closed(field):
    detector = _row()
    detector.pop(field)
    assert join_detection_rows([detector], [_row()], _contract()).status is JoinStatus.INVALID


@pytest.mark.parametrize("field", ["model_frame_idx", "server_tick"])
def test_d10_missing_timestamp_or_index_fails_closed(field):
    detector, reference = _row(), _row()
    (detector if field == "model_frame_idx" else reference).pop(field)
    assert join_detection_rows([detector], [reference], _contract()).status is JoinStatus.INVALID


def test_d10_incompatible_clock_domain_needs_exact_mapping():
    invalid = join_detection_rows([_row()], [_row()], _contract(same_clock=False))
    valid = join_detection_rows(
        [_row(index=3)], [_row(index=9)], _contract(same_clock=False, mapping={3: 9})
    )
    assert invalid.status is JoinStatus.INVALID
    assert valid.status is JoinStatus.VALID


def test_d10_more_than_one_reference_candidate_is_never_silently_chosen():
    report = join_detection_rows([_row()], [_row(), _row()], _contract())
    assert report.status is JoinStatus.AMBIGUOUS
    assert report.pairs == []
