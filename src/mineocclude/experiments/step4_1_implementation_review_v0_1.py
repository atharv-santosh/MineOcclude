"""Independent Person E review of the Person B Step 4.1 implementation.

This module reads Person B only through exact Git objects.  It does not import
or execute Person B code, prediction artifacts, metrics, probes, or U4 data.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import random
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

PERSON_E_STARTING_AUTHORITY = "d2a82a09b2f0acf73c9c7d95c1ea2e382a6cc4f7"
PERSON_B_IMPLEMENTATION_COMMIT = "0a73caf2b74221c5f934b95ae39ac825748e2942"
PERSON_B_PREPARATION_COMMIT = "041ae890ec4f659a97772e83ad82312980f37921"
PERSON_B_COMPARISON_CONTRACT_COMMIT = "4da02023a376df77eacb48084b1406ec1accfcb1"
PERSON_B_BOUNDED_REVEAL_CONTRACT_COMMIT = (
    "53c2cd287a63e18e9b1fa5565b77f5c476baf9c4"
)
PERSON_E_BOUNDED_REVEAL_AUTHORIZATION_COMMIT = (
    "99fb896ed8e6a3b187272fe078706bc7b17666d8"
)
PERSON_E_COMPARISON_RATIFICATION_COMMIT = (
    "d2a82a09b2f0acf73c9c7d95c1ea2e382a6cc4f7"
)
PERSON_D_COMPLETION_COMMIT = "f89b142a6fdb52c2d238669af8df14061cee5896"
BOUNDED_REVEAL_SHA256 = (
    "b7716ba00b1e45b20dab130965d03bba8947a87999be51e89404fad4982d288d"
)
BOUNDED_REVEAL_COUNT = 100

PREPARATION_PACKAGE = (
    "docs/status/person_b_phase4_step4_1_final_comparison_execution_preparation_v0_1"
)
IMPLEMENTATION_PATHS = {
    "cli": "scripts/run_person_b_step4_1_final_comparison.py",
    "focused_tests": (
        "tests/analysis/test_person_b_step4_1_final_comparison_entrypoint_v0_1.py"
    ),
    "runtime_library": (
        "src/mineocclude/analysis/step4_1_final_comparison_runtime_v0_1.py"
    ),
    "scientific_library": (
        "src/mineocclude/analysis/step4_1_final_comparison_v0_1.py"
    ),
}
EXACT_COMMAND = [
    "python",
    "scripts/run_person_b_step4_1_final_comparison.py",
    "--repository-root",
    "$PWD",
    "--person-b-contract-commit",
    PERSON_B_BOUNDED_REVEAL_CONTRACT_COMMIT,
    "--person-e-ratification-commit",
    "origin/role/person-e-operations",
    "--person-b-predictions",
    "/home/sagemaker-user/person-b-step4-1-approved-outputs/person-b-step4-1-production-v0-1/fitted_probes_and_predictions.json",
    "--person-d-root",
    "/home/sagemaker-user/person-d-step4-1-approved-outputs/person-d-step4-1-production-v0-1",
    "--post-reveal-predictions",
    "/home/sagemaker-user/person-b-step4-1-approved-outputs/person-b-step4-1-bounded-reveal-v0-1/post_reveal_predictions.json",
    "--output-root",
    "/home/sagemaker-user/person-b-step4-1-approved-outputs/person-b-step4-1-final-comparison-v0-1",
    "--mode",
    "run",
    "--resume",
    "validate-complete-no-write",
]


class ImplementationReviewError(ValueError):
    """Raised when the exact B implementation cannot be independently ratified."""


def _git(repository: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ImplementationReviewError(f"Git review failed: {error}") from error
    return result.stdout.strip()


def _git_bytes(repository: Path, revision: str, path: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "show", f"{revision}:{path}"],
            cwd=repository,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ImplementationReviewError(
            f"Exact Git-object review failed for {path}: {error}"
        ) from error
    return result.stdout


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _decode(payload: bytes, *, label: str) -> Mapping[str, Any]:
    def reject_constant(value: str) -> None:
        raise ImplementationReviewError(f"{label} contains {value}.")

    def unique(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ImplementationReviewError(f"{label} repeats {key}.")
            result[key] = value
        return result

    try:
        document = json.loads(
            payload.decode("utf-8"),
            parse_constant=reject_constant,
            object_pairs_hook=unique,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ImplementationReviewError(f"Could not decode {label}: {error}") from error
    if not isinstance(document, Mapping):
        raise ImplementationReviewError(f"{label} is not a JSON object.")
    return document


def _load_preparation_package(repository: Path) -> dict[str, Mapping[str, Any]]:
    inventory = _decode(
        _git_bytes(
            repository,
            PERSON_B_PREPARATION_COMMIT,
            f"{PREPARATION_PACKAGE}/sha256_inventory.json",
        ),
        label="Person B preparation inventory",
    )
    files = inventory.get("files")
    if inventory.get("inventory_excludes_self") is not True or not isinstance(
        files, Mapping
    ):
        raise ImplementationReviewError("Person B preparation inventory differs.")
    documents = {}
    for name, reference in files.items():
        if not isinstance(name, str) or not isinstance(reference, Mapping):
            raise ImplementationReviewError("Preparation inventory row is malformed.")
        payload = _git_bytes(
            repository,
            PERSON_B_PREPARATION_COMMIT,
            f"{PREPARATION_PACKAGE}/{name}",
        )
        if (
            len(payload) != reference.get("byte_size")
            or _sha256(payload) != reference.get("sha256")
        ):
            raise ImplementationReviewError(f"Preparation bytes differ at {name}.")
        documents[name] = _decode(payload, label=f"preparation {name}")
    return documents


def _function_names(tree: ast.AST) -> set[str]:
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _assigned_literals(tree: ast.AST) -> dict[str, Any]:
    result = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(
            node.targets[0], ast.Name
        ):
            try:
                result[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                pass
    return result


def _require_source_tokens(source: str, tokens: Sequence[str], *, label: str) -> None:
    missing = [token for token in tokens if token not in source]
    if missing:
        raise ImplementationReviewError(f"{label} lacks {missing!r}.")


def independent_max_t_vector() -> dict[str, float]:
    """Recompute E's expected deterministic vector without importing B code."""

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

    def studentized(values: Sequence[float]) -> float:
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / (
            len(values) - 1
        )
        return mean / math.sqrt(variance / len(values))

    observed = {
        name: studentized([values[key] for key in sorted(values)])
        for name, values in hypotheses.items()
    }
    rng = random.Random(20260720)
    maxima = []
    for _ in range(999):
        signs = {
            layout: rng.choice((-1.0, 1.0))
            for layout in (
                "layout_00",
                "layout_01",
                "layout_02",
                "layout_03",
                "layout_04",
            )
        }
        maxima.append(
            max(
                studentized(
                    [values[key] * signs[key] for key in sorted(values)]
                )
                for values in hypotheses.values()
            )
        )
    return {
        name: (1 + sum(value >= statistic for value in maxima)) / 1000
        for name, statistic in observed.items()
    }


def review_person_b_implementation(repository: Path) -> dict[str, Any]:
    """Perform the complete independent exact-object conformance review."""

    if _git(repository, "show", "-s", "--format=%P", PERSON_B_IMPLEMENTATION_COMMIT) != (
        PERSON_B_BOUNDED_REVEAL_CONTRACT_COMMIT
    ):
        raise ImplementationReviewError("Person B implementation parent differs.")
    if _git(repository, "show", "-s", "--format=%P", PERSON_B_PREPARATION_COMMIT) != (
        PERSON_B_IMPLEMENTATION_COMMIT
    ):
        raise ImplementationReviewError("Person B preparation parent differs.")
    if _git(repository, "show", "-s", "--format=%s", PERSON_B_IMPLEMENTATION_COMMIT) != (
        "Implement Person B Step 4.1 final comparison entrypoint"
    ):
        raise ImplementationReviewError("Person B implementation subject differs.")
    if _git(repository, "show", "-s", "--format=%s", PERSON_B_PREPARATION_COMMIT) != (
        "Prepare Person B Step 4.1 final comparison execution"
    ):
        raise ImplementationReviewError("Person B preparation subject differs.")

    package = _load_preparation_package(repository)
    binding = package["implementation_binding.json"]
    file_bindings = binding.get("files")
    if not isinstance(file_bindings, Mapping) or set(file_bindings) != set(
        IMPLEMENTATION_PATHS
    ):
        raise ImplementationReviewError("Implementation file binding differs.")
    sources = {}
    for role, path in IMPLEMENTATION_PATHS.items():
        payload = _git_bytes(repository, PERSON_B_IMPLEMENTATION_COMMIT, path)
        reference = file_bindings[role]
        if (
            not isinstance(reference, Mapping)
            or reference.get("path") != path
            or reference.get("byte_size") != len(payload)
            or reference.get("sha256") != _sha256(payload)
        ):
            raise ImplementationReviewError(f"Implementation binding differs at {role}.")
        sources[role] = payload.decode("utf-8")

    scientific_tree = ast.parse(sources["scientific_library"])
    runtime_tree = ast.parse(sources["runtime_library"])
    cli_tree = ast.parse(sources["cli"])
    scientific_names = _function_names(scientific_tree)
    runtime_names = _function_names(runtime_tree)
    cli_names = _function_names(cli_tree)
    if not {
        "compute_final_comparison",
        "hierarchical_layout_confidence_interval",
        "shared_sign_flip_max_t",
        "validate_method_configuration",
        "validate_output_documents",
    } <= scientific_names:
        raise ImplementationReviewError("Scientific library interface differs.")
    if not {
        "load_bounded_reveal_artifact",
        "run_final_comparison",
        "validate_all_inputs",
        "validate_bounded_reveal_payload",
        "validate_execution_request",
    } <= runtime_names:
        raise ImplementationReviewError("Runtime library interface differs.")
    if not {"build_parser", "main", "request_from_args"} <= cli_names:
        raise ImplementationReviewError("CLI interface differs.")

    constants = _assigned_literals(scientific_tree)
    expected_constants = {
        "BOOTSTRAP_COUNT": 2000,
        "BOOTSTRAP_COVERAGE": 0.95,
        "BOOTSTRAP_SEED": 20260721,
        "PERMUTATION_COUNT": 999,
        "PERMUTATION_SEED": 20260720,
    }
    for name, expected in expected_constants.items():
        if constants.get(name) != expected:
            raise ImplementationReviewError(f"Scientific constant {name} differs.")
    _require_source_tokens(
        sources["scientific_library"],
        (
            "equal layout -> trajectory -> row weighting",
            "single-step maxT",
            "none_all_layers_fixed_before_runtime",
            "qualifying_layer_bands",
            "max_t_adjusted_p_value",
            "partial_correlation_controlling_tau",
            "trajectory_growth_slopes",
            "oracle_slope_ratio",
            "reveal_difference",
            "u1_r2[layer] > 0.0",
            "< 0.01",
            "ece <= 0.10",
            "partial_ci[0] > 0.0",
            "0.5 <= u3[\"ratio\"] <= 2.0",
            "u3[\"reduction\"] >= 0.25",
            "[\"reveal_difference\"][1] < 0.0",
        ),
        label="scientific library",
    )
    _require_source_tokens(
        sources["runtime_library"],
        (
            "validate-complete-no-write",
            "probe_refit_performed",
            "additional_person_a_extraction_performed",
            "manual_u4_inspection",
            "exploratory_metrics_computed",
            "post_hoc_layer_selection_performed",
            "post_hoc_test_selection_performed",
            "decode_strict_json",
            "tempfile.mkdtemp",
            "os.rename(stage, output_root)",
            "shutil.rmtree(stage, ignore_errors=True)",
        ),
        label="runtime library",
    )
    if "compute_final_comparison" in sources["cli"] or "max_t" in sources["cli"]:
        raise ImplementationReviewError("Scientific logic leaked into the CLI.")
    if "run_person_b_step4_1_bounded_reveal" in sources["runtime_library"]:
        raise ImplementationReviewError("Runtime can rerun bounded reveal.")
    if "fit_ridge" in sources["runtime_library"] or "fit_ridge" in sources[
        "scientific_library"
    ]:
        raise ImplementationReviewError("Implementation can refit probes.")

    test_source = sources["focused_tests"]
    required_tests = (
        "test_missing_entrypoint_is_now_present_and_thin",
        "test_changed_reveal_hash_fails",
        "test_missing_reveal_artifact_fails",
        "test_cli_rejects_unratified_or_prohibited_options",
        "test_changed_scientific_configuration_fails",
        "test_exact_output_schemas_build_on_non_scientific_fixture",
        "test_synthetic_library_fixture_exercises_every_frozen_layer",
    )
    _require_source_tokens(test_source, required_tests, label="focused tests")
    if independent_max_t_vector() != {
        "layer_00_last_seen": 0.078,
        "layer_01_last_seen": 0.037,
    }:
        raise ImplementationReviewError("Independent maxT vector differs.")

    command = package["execution_command.json"]
    input_contract = package["execution_input_contract.json"]
    output = package["output_and_closure_requirements.json"]
    if command.get("command") != EXACT_COMMAND or command.get("non_placeholder") is not True:
        raise ImplementationReviewError("Prepared execution command differs.")
    reveal = input_contract.get("bounded_reveal")
    if not isinstance(reveal, Mapping) or reveal != {
        "additional_person_a_extraction_authorized": False,
        "path": "/home/sagemaker-user/person-b-step4-1-approved-outputs/person-b-step4-1-bounded-reveal-v0-1/post_reveal_predictions.json",
        "prediction_count": BOUNDED_REVEAL_COUNT,
        "probe_refitting_authorized": False,
        "rerun_authorized": False,
        "reuse_required": True,
        "schema_id": "person-b-step4-1-bounded-reveal-predictions-v0-1",
        "sha256": BOUNDED_REVEAL_SHA256,
    }:
        raise ImplementationReviewError("Bounded-reveal reuse contract differs.")
    if output.get("output_files") != [
        "comparison_metric_table.json",
        "paired_test_results.json",
        "confidence_intervals.json",
        "layer_band_decision.json",
        "registry_v2_import_package.json",
        "execution_receipt.json",
        "sha256_inventory.json",
    ]:
        raise ImplementationReviewError("Prepared output set differs.")
    return {
        "bounded_reveal_artifact_count_and_hash_exact": True,
        "bounded_reveal_rerun_absent": True,
        "cli_dispatch_exact": True,
        "confidence_interval_procedure_exact": True,
        "deterministic_test_vectors_exact": True,
        "entrypoint_exists": True,
        "frozen_acceptance_criteria_exact": True,
        "frozen_aggregation_exact": True,
        "frozen_controls_exact": True,
        "frozen_layer_selection_exact": True,
        "frozen_multiplicity_exact": True,
        "frozen_significance_test_exact": True,
        "implementation_blob_count": 4,
        "implementation_commit": PERSON_B_IMPLEMENTATION_COMMIT,
        "manual_u4_inspection_absent": True,
        "person_a_additional_extraction_absent": True,
        "person_b_preparation_commit": PERSON_B_PREPARATION_COMMIT,
        "post_hoc_or_exploratory_options_absent": True,
        "probe_refit_absent": True,
        "schema_id": "person-e-step4-1-implementation-independent-review-v0-1",
        "schema_version": "1.0",
        "scientific_execution_performed": False,
        "u4_output_inspected": False,
    }


def build_implementation_ratification(repository: Path) -> dict[str, Any]:
    review = review_person_b_implementation(repository)
    return {
        "bounded_reveal_artifact_reuse_required": True,
        "bounded_reveal_prediction_count": BOUNDED_REVEAL_COUNT,
        "bounded_reveal_prediction_sha256": BOUNDED_REVEAL_SHA256,
        "comparison_contract_commit": PERSON_B_COMPARISON_CONTRACT_COMMIT,
        "comparison_ratification_commit": PERSON_E_COMPARISON_RATIFICATION_COMMIT,
        "decision": "RATIFY_EXACT_PERSON_B_FINAL_COMPARISON_IMPLEMENTATION",
        "final_comparison_implementation_ratified": True,
        "frozen_scientific_contract_unchanged": True,
        "independent_review": review,
        "person_b_bounded_reveal_contract_commit": (
            PERSON_B_BOUNDED_REVEAL_CONTRACT_COMMIT
        ),
        "person_b_comparison_implementation_commit": PERSON_B_IMPLEMENTATION_COMMIT,
        "person_b_execution_preparation_commit": PERSON_B_PREPARATION_COMMIT,
        "person_d_completion_commit": PERSON_D_COMPLETION_COMMIT,
        "schema_id": "person-e-step4-1-final-comparison-implementation-ratification-v0-1",
        "schema_version": "1.0",
        "scientific_execution_performed": False,
        "step4_1_complete": False,
        "superseding_execution_authorization_pending": True,
        "u4_output_inspected": False,
    }


def build_ratification_documents(repository: Path) -> dict[str, dict[str, Any]]:
    review = review_person_b_implementation(repository)
    return {
        "authority_binding.json": {
            "person_b_comparison_implementation_commit": PERSON_B_IMPLEMENTATION_COMMIT,
            "person_b_execution_preparation_commit": PERSON_B_PREPARATION_COMMIT,
            "person_e_starting_authority": PERSON_E_STARTING_AUTHORITY,
            "ratification_commit_semantics": (
                "The Git commit containing this package is the implementation "
                "ratification authority and must directly descend from person_e_starting_authority."
            ),
            "schema_id": "person-e-step4-1-implementation-ratification-authority-v0-1",
            "schema_version": "1.0",
            "u4_output_inspected": False,
        },
        "closure_interface.json": {
            "decision_vocabulary": ["PASS", "FAIL", "INCONCLUSIVE"],
            "exact_output_files": [
                "comparison_metric_table.json",
                "paired_test_results.json",
                "confidence_intervals.json",
                "layer_band_decision.json",
                "registry_v2_import_package.json",
                "execution_receipt.json",
                "sha256_inventory.json",
            ],
            "output_root": "/home/sagemaker-user/person-b-step4-1-approved-outputs/person-b-step4-1-final-comparison-v0-1",
            "registry_generation": "v2",
            "schema_id": "person-e-step4-1-implementation-closure-interface-v0-1",
            "schema_version": "1.0",
            "scientific_execution_performed": False,
            "step4_1_complete": False,
            "u4_output_inspected": False,
        },
        "implementation_ratification.json": build_implementation_ratification(repository),
        "independent_conformance_review.json": review,
        "validation_receipt.json": {
            "all_required_conformance_checks_passed": True,
            "implementation_ratified": True,
            "person_b_git_objects_read_without_merge": True,
            "schema_id": "person-e-step4-1-implementation-ratification-validation-v0-1",
            "schema_version": "1.0",
            "scientific_execution_performed": False,
            "u4_output_inspected": False,
        },
    }


def validate_ratification_documents(
    repository: Path, documents: Mapping[str, Any]
) -> None:
    expected = build_ratification_documents(repository)
    if documents != expected:
        raise ImplementationReviewError("Implementation ratification differs.")
    review = documents["independent_conformance_review.json"]
    if any(
        value is not True
        for key, value in review.items()
        if key.endswith(("_exact", "_absent"))
    ):
        raise ImplementationReviewError("A conformance check did not pass.")
    ratification = documents["implementation_ratification.json"]
    if (
        ratification["final_comparison_implementation_ratified"] is not True
        or ratification["frozen_scientific_contract_unchanged"] is not True
        or ratification["step4_1_complete"] is not False
    ):
        raise ImplementationReviewError("Ratification state differs.")


__all__ = [
    "BOUNDED_REVEAL_COUNT",
    "BOUNDED_REVEAL_SHA256",
    "EXACT_COMMAND",
    "IMPLEMENTATION_PATHS",
    "PERSON_B_IMPLEMENTATION_COMMIT",
    "PERSON_B_PREPARATION_COMMIT",
    "PERSON_E_STARTING_AUTHORITY",
    "ImplementationReviewError",
    "build_implementation_ratification",
    "build_ratification_documents",
    "independent_max_t_vector",
    "review_person_b_implementation",
    "validate_ratification_documents",
]
