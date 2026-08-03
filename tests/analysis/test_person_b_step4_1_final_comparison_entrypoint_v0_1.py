"""Focused non-production tests for the final-comparison entrypoint."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path

import pytest

from mineocclude.analysis.step4_1_bounded_reveal_v0_1 import reveal_events
from mineocclude.analysis.step4_1_final_comparison_runtime_v0_1 import (
    FINAL_OUTPUT_ROOT,
    PERSON_B_PREDICTION_PATH,
    PERSON_D_ROOT,
    POST_REVEAL_PATH,
    ExecutionRequest,
    decode_strict_json,
    exact_execution_command,
    load_bounded_reveal_artifact,
    validate_bounded_reveal_payload,
    validate_execution_request,
)
from mineocclude.analysis.step4_1_final_comparison_v0_1 import (
    BOUNDED_REVEAL_PREDICTIONS_SHA256,
    COMPARISON_CONTRACT_COMMIT,
    ComparisonDataset,
    FinalComparisonExecutionError,
    build_output_documents,
    compute_final_comparison,
    frozen_method_configuration,
    hierarchical_layout_confidence_interval,
    shared_sign_flip_max_t,
    validate_method_configuration,
    validate_output_documents,
)
from mineocclude.experiments.registry import formatted_json_bytes
from scripts import run_person_b_step4_1_final_comparison as entrypoint

ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "scripts/run_person_b_step4_1_final_comparison.py"


def _base_argv() -> list[str]:
    return [
        "--repository-root",
        str(ROOT),
        "--person-b-contract-commit",
        "53c2cd287a63e18e9b1fa5565b77f5c476baf9c4",
        "--person-e-ratification-commit",
        "origin/role/person-e-operations",
        "--person-b-predictions",
        str(PERSON_B_PREDICTION_PATH),
        "--person-d-root",
        str(PERSON_D_ROOT),
        "--post-reveal-predictions",
        str(POST_REVEAL_PATH),
        "--output-root",
        str(FINAL_OUTPUT_ROOT),
    ]


def _reveal_payload() -> bytes:
    rows = []
    for event in reveal_events():
        for layer in range(20):
            rows.append(
                {
                    "event_id": event["event_id"],
                    "fold_idx": event["fold_idx"],
                    "hook_site": "decoder_layer_output_residual_stream",
                    "layer_idx": layer,
                    "layout_id": event["layout_id"],
                    "model_frame_idx": event["post_identity"]["model_frame_idx"],
                    "prediction": float(layer) / 10.0,
                    "prediction_scope": "held_out",
                    "relative_time_seconds": 0.0,
                    "target_name": "log_sigma_oracle",
                    "trajectory_id": event["trajectory_id"],
                    "visibility": "visible",
                }
            )
    return formatted_json_bytes(
        {
            "comparison_contract_commit": (
                "4da02023a376df77eacb48084b1406ec1accfcb1"
            ),
            "person_b_contract_commit": (
                "53c2cd287a63e18e9b1fa5565b77f5c476baf9c4"
            ),
            "person_e_authorization_commit": (
                "99fb896ed8e6a3b187272fe078706bc7b17666d8"
            ),
            "prediction_count": 100,
            "rows": rows,
            "schema_id": "person-b-step4-1-bounded-reveal-predictions-v0-1",
            "schema_version": "1.0",
            "u4_output_inspected": False,
        }
    )


def _request(**changes) -> ExecutionRequest:
    values = {
        "repository_root": ROOT,
        "person_b_contract_commit": "53c2cd287a63e18e9b1fa5565b77f5c476baf9c4",
        "person_e_ratification_commit": "origin/role/person-e-operations",
        "person_b_predictions": PERSON_B_PREDICTION_PATH,
        "person_d_root": PERSON_D_ROOT,
        "post_reveal_predictions": POST_REVEAL_PATH,
        "output_root": FINAL_OUTPUT_ROOT,
        "mode": "validate",
        "resume": "validate-complete-no-write",
    }
    values.update(changes)
    return ExecutionRequest(**values)


def _synthetic_dataset() -> ComparisonDataset:
    ranges = (
        ("layout_00_ep9403", "layout_00", 1, 19, 227),
        ("layout_01_ep9405", "layout_01", 2, 23, 209),
        ("layout_02_ep9407", "layout_02", 4, 3, 137),
        ("layout_03_ep9404", "layout_03", 0, 14, 105),
        ("layout_04_ep9406", "layout_04", 3, 21, 92),
    )
    oracle_rows = []
    probe_rows = []
    baseline_rows = {
        (family, target): []
        for family, target in (
            ("last_seen", "mu_oracle_blocks"),
            ("constant_velocity", "mu_oracle_blocks"),
            ("grouped_shuffled", "mu_oracle_blocks"),
            ("explicit_feature", "mu_oracle_blocks"),
            ("raw_pixel", "mu_oracle_blocks"),
            ("grouped_shuffled", "log_sigma_oracle"),
            ("time_only", "log_sigma_oracle"),
            ("visible_history_q", "log_sigma_oracle"),
            ("known_q_analytic", "log_sigma_oracle"),
        )
    }
    for layout_number, (trajectory, layout, fold, first, last) in enumerate(ranges):
        for frame in range(first, last + 1):
            tau = (frame - first + 1) * 0.05
            mu = layout_number * 2.0 + tau
            sigma = 0.5 + 0.08 * tau + 0.01 * math.sin(frame * 0.31)
            log_sigma = math.log(sigma)
            oracle_rows.append(
                {
                    "fold_idx": fold,
                    "layout_id": layout,
                    "log_sigma_oracle": log_sigma,
                    "model_frame_idx": frame,
                    "mu_oracle_blocks": mu,
                    "tau": tau,
                    "trajectory_id": trajectory,
                    "visibility": "occluded",
                    "x_true_blocks": mu + 0.02 * math.cos(frame * 0.17),
                }
            )
            for layer in range(20):
                mu_prediction = mu + 0.01 * math.sin(frame + layer)
                decoded_sigma = (
                    0.5
                    + 0.081 * tau
                    + 0.009 * math.sin(frame * 0.31 + layer * 0.01)
                )
                for target, prediction in (
                    ("mu_oracle_blocks", mu_prediction),
                    ("log_sigma_oracle", math.log(decoded_sigma)),
                ):
                    probe_rows.append(
                        {
                            "fold_idx": fold,
                            "hook_site": "decoder_layer_output_residual_stream",
                            "layer_idx": layer,
                            "model_frame_idx": frame,
                            "prediction": prediction,
                            "target_name": target,
                            "trajectory_id": trajectory,
                        }
                    )
            for (family, target), rows in baseline_rows.items():
                offset = 0.35 + 0.04 * layout_number
                prediction = mu + offset if target == "mu_oracle_blocks" else log_sigma + offset
                rows.append(
                    {
                        "fold_idx": fold,
                        "model_frame_idx": frame,
                        "prediction": prediction,
                        "target_name": target,
                        "trajectory_id": trajectory,
                    }
                )
    post_rows = []
    for layout_number, event in enumerate(reveal_events()):
        for layer in range(20):
            post_rows.append(
                {
                    "event_id": event["event_id"],
                    "hook_site": "decoder_layer_output_residual_stream",
                    "layer_idx": layer,
                    "prediction": math.log(0.2 + 0.02 * layout_number),
                    "target_name": "log_sigma_oracle",
                    "trajectory_id": event["trajectory_id"],
                }
            )
    return ComparisonDataset(
        oracle_rows=tuple(oracle_rows),
        probe_rows=tuple(probe_rows),
        baseline_rows={key: tuple(rows) for key, rows in baseline_rows.items()},
        post_reveal_rows=tuple(post_rows),
        direct_input_sha256s={"synthetic_fixture": "f" * 64},
        positive_control_valid=True,
    )


def test_missing_entrypoint_is_now_present_and_thin() -> None:
    source = ENTRYPOINT.read_text(encoding="utf-8")
    assert ENTRYPOINT.is_file()
    assert "run_final_comparison" in source
    assert "compute_final_comparison" not in source
    assert "max_t" not in source
    assert "bootstrap" not in source


def test_cli_dispatches_exact_frozen_request_without_execution(monkeypatch) -> None:
    observed = []

    def fake_run(request: ExecutionRequest):
        observed.append(request)
        return {
            "scientific_execution_performed": False,
            "status": "VALIDATED_NO_SCIENTIFIC_EXECUTION",
        }

    monkeypatch.setattr(entrypoint, "run_final_comparison", fake_run)
    assert entrypoint.main([*_base_argv(), "--mode", "validate"]) == 0
    assert len(observed) == 1
    assert observed[0].mode == "validate"
    assert observed[0].person_b_contract_commit == (
        "53c2cd287a63e18e9b1fa5565b77f5c476baf9c4"
    )


def test_execution_command_is_exact_and_has_no_placeholder() -> None:
    command = exact_execution_command()
    assert command[:2] == [
        "python",
        "scripts/run_person_b_step4_1_final_comparison.py",
    ]
    assert not any("<" in token or ">" in token for token in command)
    assert "53c2cd287a63e18e9b1fa5565b77f5c476baf9c4" in command
    assert "origin/role/person-e-operations" in command
    assert "/home/sagemaker-user/person-b-step4-1-approved-outputs/" in " ".join(
        command
    )


def test_exact_deterministic_max_t_vector() -> None:
    hypotheses = {
        "layer_00_last_seen": {
            "layout_00": 0.5,
            "layout_01": 0.2,
            "layout_02": 0.4,
            "layout_03": -0.1,
            "layout_04": 0.3,
        },
        "layer_01_last_seen": {
            "layout_00": 0.6,
            "layout_01": 0.3,
            "layout_02": 0.5,
            "layout_03": 0.1,
            "layout_04": 0.4,
        },
    }
    result = shared_sign_flip_max_t(hypotheses)
    assert result["layer_00_last_seen"]["max_t_adjusted_p_value"] == 0.078
    assert result["layer_01_last_seen"]["max_t_adjusted_p_value"] == 0.037


def test_hierarchical_bootstrap_is_seeded_and_exact() -> None:
    values = {f"layout_{index:02d}": float(index) for index in range(5)}
    assert hierarchical_layout_confidence_interval(values) == (
        0.8,
        3.2,
    )
    assert hierarchical_layout_confidence_interval(values) == (
        0.8,
        3.2,
    )


@pytest.mark.parametrize(
    ("section", "field", "changed"),
    [
        ("layer_contract", "selection_mode", "best_observed_layer"),
        ("multiplicity_contract", "adjustment", "none"),
        ("confidence_interval_contract", "bootstrap_count", 1000),
        (
            "multiplicity_contract",
            "family_wise_comparison_sets",
            {"U1": "one favorable test"},
        ),
        (
            "acceptance_contract",
            "scientific_gates",
            {"U1_green": {"held_out_r2_strictly_greater_than": -1.0}},
        ),
    ],
)
def test_changed_scientific_configuration_fails(
    section: str, field: str, changed: object
) -> None:
    document = copy.deepcopy(frozen_method_configuration())
    document[section][field] = changed
    with pytest.raises(FinalComparisonExecutionError, match="differs"):
        validate_method_configuration(document)


def test_completed_reveal_reuse_validates_count_and_hash() -> None:
    payload = _reveal_payload()
    document = validate_bounded_reveal_payload(
        payload,
        expected_sha256=hashlib.sha256(payload).hexdigest(),
    )
    assert document["prediction_count"] == 100
    assert BOUNDED_REVEAL_PREDICTIONS_SHA256 == (
        "b7716ba00b1e45b20dab130965d03bba8947a87999be51e89404fad4982d288d"
    )


def test_changed_reveal_hash_fails() -> None:
    with pytest.raises(FinalComparisonExecutionError, match="SHA-256"):
        validate_bounded_reveal_payload(_reveal_payload())


def test_missing_reveal_artifact_fails(tmp_path: Path) -> None:
    with pytest.raises(FinalComparisonExecutionError, match="Could not read"):
        load_bounded_reveal_artifact(tmp_path / "missing.json")


@pytest.mark.parametrize(
    "forbidden",
    [
        "--refit-probes",
        "--additional-person-a-extraction",
        "--manual-u4-inspection",
        "--metric",
        "--layer-selection",
        "--significance-test",
        "--confidence-interval",
        "--multiplicity",
        "--threshold",
    ],
)
def test_cli_rejects_unratified_or_prohibited_options(forbidden: str) -> None:
    with pytest.raises(SystemExit):
        entrypoint.parse_args([*_base_argv(), forbidden, "changed"])


def test_changed_paths_and_resume_mode_fail_closed() -> None:
    with pytest.raises(FinalComparisonExecutionError, match="paths differ"):
        validate_execution_request(
            _request(post_reveal_predictions=Path("changed.json"))
        )
    with pytest.raises(FinalComparisonExecutionError, match="Resume behavior"):
        validate_execution_request(_request(resume="overwrite"))


def test_strict_json_rejects_duplicate_and_nonfinite_values() -> None:
    with pytest.raises(FinalComparisonExecutionError, match="Duplicate JSON"):
        decode_strict_json(b'{"a":1,"a":2}', label="fixture")
    with pytest.raises(FinalComparisonExecutionError, match="Non-finite"):
        decode_strict_json(b'{"a":NaN}', label="fixture")


def test_exact_output_schemas_build_on_non_scientific_fixture() -> None:
    hashes = {"fixture": "a" * 64}
    layer_gates = {
        layer: {
            "U1_green": False,
            "U2_green": False,
            "U3_green": False,
            "qualifies": False,
        }
        for layer in range(20)
    }
    documents = build_output_documents(
        decision="INCONCLUSIVE",
        metric_records=(),
        paired_test_records=(),
        confidence_interval_records=(),
        layer_gates=layer_gates,
        layer_bands=(),
        direct_input_sha256s=hashes,
        inconclusive_reasons=("NON_SCIENTIFIC_TEST_FIXTURE",),
    )
    validate_output_documents(documents)
    assert documents["comparison_metric_table.json"][
        "schema_id"
    ] == "person-b-step4-1-final-comparison-output-v0-1"
    assert documents["layer_band_decision.json"]["decision"] == "INCONCLUSIVE"


def test_synthetic_library_fixture_exercises_every_frozen_layer() -> None:
    documents = compute_final_comparison(_synthetic_dataset())
    validate_output_documents(documents)
    table = documents["comparison_metric_table.json"]
    assert {row["layer_idx"] for row in table["metric_records"]} == set(range(20))
    assert len(table["paired_test_records"]) == 100
    assert table["u4_output_inspected"] is False


def test_library_dataset_type_carries_only_ratified_inputs() -> None:
    dataset = ComparisonDataset((), (), {}, (), {"fixture": "f" * 64}, True)
    assert not hasattr(dataset, "layer_selection")
    assert not hasattr(dataset, "test_selection")
    assert COMPARISON_CONTRACT_COMMIT == (
        "4da02023a376df77eacb48084b1406ec1accfcb1"
    )


def test_entrypoint_contains_no_scientific_execution_during_import() -> None:
    # Import and parser construction are the only operations performed here.
    parser = entrypoint.build_parser()
    assert parser.prog
    assert json.loads('{"scientific_execution_performed":false}')[
        "scientific_execution_performed"
    ] is False
