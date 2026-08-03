"""Focused applicability and fail-closed preserved-output tests only."""

from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path

import pytest

from scripts import validate_person_b_step4_1_memory_reauthorization_v0_1 as validator

ROOT = Path(__file__).resolve().parents[2]
AUTHORIZATION_PACKAGE = (
    ROOT
    / "docs/status/person_b_phase4_step4_1_applicability_reauthorization_v0_1"
)


@pytest.fixture(scope="module")
def lineage() -> tuple[dict, dict]:
    return validator._load_resume_lineage(ROOT, None)


def _ordered(keys: set[tuple[str, int]]) -> list[tuple[str, int]]:
    order = {pilot: index for index, pilot in enumerate(validator.EXPECTED_PILOTS)}
    return sorted(keys, key=lambda key: (order[key[0]], key[1]))


def _expected_keys(
    family: str, target: str, lineage: tuple[dict, dict]
) -> set[tuple[str, int]]:
    target_by_key, fold_by_key = lineage
    return validator._expected_resume_keys(
        family,
        target,
        target_by_key,
        fold_by_key,
        repo_root=ROOT,
    )


def _prediction_document(
    family: str,
    target: str,
    keys: set[tuple[str, int]],
    fold_by_key: dict[tuple[str, int], int],
) -> dict:
    direct_inputs = {
        "analysis_config": {
            "byte_size": validator.ANALYSIS_CONFIG_SIZE,
            "path": validator.ANALYSIS_CONFIG_PATH,
            "producer_role": "person_b",
            "sha256": validator.ANALYSIS_CONFIG_SHA256,
        },
        "fold_manifest": {
            "byte_size": validator.FOLD_MANIFEST_SIZE,
            "path": validator.FOLD_MANIFEST_PATH,
            "producer_role": "person_b",
            "sha256": validator.FOLD_MANIFEST_SHA256,
        },
        "oracle_target": {
            "byte_size": validator.TARGET_MANIFEST_SIZE,
            "path": validator.TARGET_MANIFEST_PATH,
            "producer_role": "person_b",
            "sha256": validator.TARGET_MANIFEST_SHA256,
        },
        "source_context_manifest": {
            "byte_size": validator.SOURCE_CONTEXT_SIZE,
            "path": validator.SOURCE_CONTEXT_MANIFEST_PATH,
            "producer_role": "person_b",
            "sha256": validator.SOURCE_CONTEXT_SHA256,
        },
    }
    return {
        "accepted_pilot_ids": list(validator.EXPECTED_PILOTS),
        "baseline_family": family,
        "baseline_id": f"{family}_v1",
        "baseline_input_schema_version": "person-b-baseline-input-v0.2",
        "config_hash": validator.ANALYSIS_CONFIG_SHA256,
        "direct_inputs": direct_inputs,
        "fit_manifest_hash": validator.EXPECTED_FIT_MANIFEST_HASH,
        "fold_manifest_hash": validator.FOLD_MANIFEST_SHA256,
        "input_manifest_hash": validator.EXPECTED_INPUT_MANIFEST_HASH,
        "person_b_prediction_reservation": copy.deepcopy(
            validator.EXPECTED_PERSON_B_PREDICTION_RESERVATION
        ),
        "producer_role": "person_d",
        "random_split_used": False,
        "rows": [
            {
                "fit_id": f"{family}:{target}:v0_2",
                "fold_idx": fold_by_key[key],
                "model_frame_idx": key[1],
                "prediction": float(index + 1),
                "prediction_scope": "out_of_fold",
                "trajectory_id": key[0],
            }
            for index, key in enumerate(_ordered(keys))
        ],
        "schema_version": "1.0",
        "target_name": target,
        "u4_output_inspected": False,
    }


def _write_json(path: Path, document: object) -> None:
    path.write_bytes(validator.canonical_json_bytes(document))


def _write_preserved_bundle(
    output_root: Path, lineage: tuple[dict, dict]
) -> dict[str, Path]:
    output_root.mkdir(parents=True)
    target_by_key, fold_by_key = lineage
    state = {"families": {}, "schema_version": "1.0"}
    paths: dict[str, Path] = {}
    prediction_inventory: dict[str, list[dict]] = {}
    for family in validator.PRESERVED_COMPLETED_FAMILIES:
        targets = validator.EXPECTED_RESUME_TARGET_FAMILIES[family]
        state["families"][family] = {
            "output_path": f"{family}__{min(targets)}.json",
            "status": "completed",
            "targets": sorted(targets),
        }
        inventory: list[dict] = []
        for target in targets:
            keys = _expected_keys(family, target, (target_by_key, fold_by_key))
            document = _prediction_document(family, target, keys, fold_by_key)
            path = output_root / f"{family}__{target}.json"
            _write_json(path, document)
            raw = path.read_bytes()
            inventory.append(
                {
                    "byte_size": len(raw),
                    "path": path.name,
                    "row_count": len(keys),
                    "sha256": validator._sha256(raw),
                    "target": target,
                }
            )
            paths[f"{family}/{target}"] = path
        prediction_inventory[family] = sorted(
            inventory, key=lambda item: item["target"]
        )
    state_path = output_root / "run_state.json"
    _write_json(state_path, state)
    state_raw = state_path.read_bytes()
    state_reference = {
        "byte_size": len(state_raw),
        "path": "run_state.json",
        "sha256": validator._sha256(state_raw),
    }
    families = {}
    for family in validator.PRESERVED_COMPLETED_FAMILIES:
        families[family] = {
            "authorization_receipt": {
                "authorization_authority_commit": validator.PERSON_B_APPLICABILITY_STARTING_AUTHORITY,
                "authorization_record_path": validator.PREDECESSOR_AUTHORIZATION_RECORD_PATH,
                "authorization_record_sha256": validator.PREDECESSOR_AUTHORIZATION_RECORD_SHA256,
                "authorized_runner_commit": validator.PERSON_D_RUNNER_COMMIT,
            },
            "configuration": copy.deepcopy(validator.EXPECTED_CONFIGURATION[family]),
            "environment_receipt": {
                "available_memory_gib": 24.10773468017578,
                "captured_at_utc": "2026-08-02T01:00:00Z",
                "physical_memory_gib": 30.977378845214844,
                "u4_output_inspected": False,
            },
            "output_manifest": {
                "family_status": "completed",
                "run_state": state_reference,
                "targets": sorted(
                    validator.EXPECTED_RESUME_TARGET_FAMILIES[family]
                ),
            },
            "prediction_inventory": prediction_inventory[family],
            "runner_receipt": {
                "branch": validator.PERSON_D_BRANCH,
                "completed_at_utc": "2026-08-02T02:00:00Z",
                "producing_runner_commit": validator.PERSON_D_RUNNER_COMMIT,
                "worktree_clean": True,
            },
        }
    provenance = {
        "chronology": {
            "preserved_run": {
                "authorization_authority_commit": validator.PERSON_B_APPLICABILITY_STARTING_AUTHORITY,
                "completed_families": list(
                    validator.PRESERVED_COMPLETED_FAMILIES
                ),
                "prediction_count": validator.PRESERVED_PREDICTION_COUNT,
                "producing_runner_commit": validator.PERSON_D_RUNNER_COMMIT,
                "recorded_at_utc": "2026-08-02T03:00:00Z",
            },
            "prior_oom_report": {
                "authorization_authority_commit": validator.PERSON_B_STARTING_AUTHORITY,
                "completed_family_count": 0,
                "prediction_count": 0,
                "producing_runner_commit": validator.PERSON_D_PRIOR_RUNNER_COMMIT,
                "recorded_at_utc": "2026-08-01T03:00:00Z",
            },
        },
        "families": families,
        "output_root": validator.OUTPUT_ROOT_ABSOLUTE_PATH,
        "schema_id": "person-b-step4-1-preserved-output-provenance-v0-1",
        "schema_version": "1.0",
        "u4_output_inspected": False,
    }
    provenance_path = output_root / validator.PRESERVED_PROVENANCE_FILENAME
    _write_json(provenance_path, provenance)
    paths["provenance"] = provenance_path
    return paths


def test_global_universe_and_every_family_target_entry_are_frozen(
    lineage: tuple[dict, dict],
) -> None:
    target_by_key, fold_by_key = lineage
    result = validator.load_applicability_contract(
        target_by_key, fold_by_key, repo_root=ROOT
    )
    assert result["global_candidate_count"] == 1695
    assert tuple(result["entries"]) == tuple(
        (family, target)
        for family in validator.EXPECTED_FAMILIES
        for target in validator.EXPECTED_RESUME_TARGET_FAMILIES[family]
    )


def test_constant_velocity_exact_1690_and_five_exclusions(
    lineage: tuple[dict, dict],
) -> None:
    keys = _expected_keys("constant_velocity", "mu_oracle_blocks", lineage)
    excluded = set(lineage[0]) - keys
    assert len(lineage[0]) == 1695
    assert len(keys) == 1690
    assert excluded == {
        ("layout_00_ep9441", 0),
        ("layout_01_ep9442", 0),
        ("layout_02_ep9432", 0),
        ("layout_03_ep9443", 0),
        ("layout_04_ep9444", 0),
    }


def test_constant_velocity_rejects_universal_1695_missing_and_different_sets(
    tmp_path: Path, lineage: tuple[dict, dict]
) -> None:
    target_by_key, fold_by_key = lineage
    expected = _expected_keys("constant_velocity", "mu_oracle_blocks", lineage)
    path = tmp_path / "constant_velocity__mu_oracle_blocks.json"

    universal = _prediction_document(
        "constant_velocity", "mu_oracle_blocks", set(target_by_key), fold_by_key
    )
    _write_json(path, universal)
    with pytest.raises(
        validator.MemoryReauthorizationError,
        match="resume_unauthorized_extra_identity",
    ):
        validator._validate_resume_prediction_document(
            family="constant_velocity",
            target_name="mu_oracle_blocks",
            path=path,
            target_by_key=target_by_key,
            fold_by_key=fold_by_key,
            repo_root=ROOT,
        )

    missing = set(expected)
    missing.remove(next(iter(missing)))
    _write_json(
        path,
        _prediction_document(
            "constant_velocity", "mu_oracle_blocks", missing, fold_by_key
        ),
    )
    with pytest.raises(
        validator.MemoryReauthorizationError,
        match="resume_missing_admitted_identity",
    ):
        validator._validate_resume_prediction_document(
            family="constant_velocity",
            target_name="mu_oracle_blocks",
            path=path,
            target_by_key=target_by_key,
            fold_by_key=fold_by_key,
            repo_root=ROOT,
        )

    different = set(expected)
    admitted_removed = next(iter(different))
    different.remove(admitted_removed)
    different.add(("layout_00_ep9441", 0))
    _write_json(
        path,
        _prediction_document(
            "constant_velocity", "mu_oracle_blocks", different, fold_by_key
        ),
    )
    with pytest.raises(
        validator.MemoryReauthorizationError,
        match="resume_unauthorized_extra_identity",
    ):
        validator._validate_resume_prediction_document(
            family="constant_velocity",
            target_name="mu_oracle_blocks",
            path=path,
            target_by_key=target_by_key,
            fold_by_key=fold_by_key,
            repo_root=ROOT,
        )


def test_duplicate_and_nonfinite_predictions_fail(
    tmp_path: Path, lineage: tuple[dict, dict]
) -> None:
    target_by_key, fold_by_key = lineage
    keys = _expected_keys("constant_velocity", "mu_oracle_blocks", lineage)
    document = _prediction_document(
        "constant_velocity", "mu_oracle_blocks", keys, fold_by_key
    )
    path = tmp_path / "constant_velocity__mu_oracle_blocks.json"
    duplicate = copy.deepcopy(document)
    duplicate["rows"].append(copy.deepcopy(duplicate["rows"][0]))
    _write_json(path, duplicate)
    with pytest.raises(validator.MemoryReauthorizationError, match="resume_duplicate_row"):
        validator._validate_resume_prediction_document(
            family="constant_velocity",
            target_name="mu_oracle_blocks",
            path=path,
            target_by_key=target_by_key,
            fold_by_key=fold_by_key,
            repo_root=ROOT,
        )
    nonfinite = copy.deepcopy(document)
    nonfinite["rows"][0]["prediction"] = float("inf")
    path.write_text(json.dumps(nonfinite), encoding="utf-8")
    with pytest.raises(validator.MemoryReauthorizationError, match="resume_prediction_invalid"):
        validator._validate_resume_prediction_document(
            family="constant_velocity",
            target_name="mu_oracle_blocks",
            path=path,
            target_by_key=target_by_key,
            fold_by_key=fold_by_key,
            repo_root=ROOT,
        )


def test_unknown_contract_version_and_exclusion_reason_fail_closed(
    lineage: tuple[dict, dict],
) -> None:
    path = ROOT / validator.APPLICABILITY_CONTRACT_RELATIVE_PATH
    contract = json.loads(path.read_text(encoding="utf-8"))
    unknown_version = copy.deepcopy(contract)
    unknown_version["contract_version"] = "unknown"
    with pytest.raises(
        validator.MemoryReauthorizationError,
        match="applicability_contract_version_unknown",
    ):
        validator.validate_applicability_contract(
            unknown_version, *lineage, repo_root=ROOT
        )
    unknown_reason = copy.deepcopy(contract)
    unknown_reason["exclusion_reason_vocabulary"]["unknown"] = "not frozen"
    with pytest.raises(
        validator.MemoryReauthorizationError,
        match="applicability_exclusion_reason_unknown",
    ):
        validator.validate_applicability_contract(
            unknown_reason, *lineage, repo_root=ROOT
        )


def test_valid_preserved_outputs_are_reusable_and_absent_outputs_may_run(
    tmp_path: Path, lineage: tuple[dict, dict]
) -> None:
    paths = _write_preserved_bundle(tmp_path / "output", lineage)
    result = validator.validate_output_resume_state(
        tmp_path / "output", repo_root=ROOT
    )
    assert result["completed_family_count"] == 5
    assert result["preserved_output_provenance"]["prediction_count"] == 7691
    assert all(
        result["decisions"][family] == "reusable"
        for family in validator.PRESERVED_COMPLETED_FAMILIES
    )
    assert all(
        result["decisions"][family] == "absent"
        for family in validator.EXPECTED_FAMILIES[5:]
    )
    assert paths["provenance"].is_file()

    empty = tmp_path / "empty"
    empty.mkdir()
    absent = validator.validate_output_resume_state(empty, repo_root=ROOT)
    assert set(absent["decisions"].values()) == {"absent"}


@pytest.mark.parametrize(
    ("receipt", "field", "value", "error"),
    [
        (
            "runner_receipt",
            "producing_runner_commit",
            "0" * 40,
            "resume_runner_lineage_mismatch",
        ),
        (
            "authorization_receipt",
            "authorization_authority_commit",
            "0" * 40,
            "resume_authorization_lineage_mismatch",
        ),
        (
            "runner_receipt",
            "producing_runner_commit",
            validator.PERSON_D_PRIOR_RUNNER_COMMIT,
            "resume_runner_lineage_mismatch",
        ),
    ],
)
def test_wrong_or_unexplained_predecessor_lineage_fails(
    tmp_path: Path,
    lineage: tuple[dict, dict],
    receipt: str,
    field: str,
    value: str,
    error: str,
) -> None:
    paths = _write_preserved_bundle(tmp_path / "output", lineage)
    provenance = json.loads(paths["provenance"].read_text(encoding="utf-8"))
    provenance["families"]["last_seen"][receipt][field] = value
    _write_json(paths["provenance"], provenance)
    with pytest.raises(validator.MemoryReauthorizationError, match=error):
        validator.validate_output_resume_state(tmp_path / "output", repo_root=ROOT)


def test_invalid_conflicting_output_is_not_overwritten(
    tmp_path: Path, lineage: tuple[dict, dict]
) -> None:
    paths = _write_preserved_bundle(tmp_path / "output", lineage)
    prediction_path = paths["constant_velocity/mu_oracle_blocks"]
    document = json.loads(prediction_path.read_text(encoding="utf-8"))
    document["rows"].pop()
    _write_json(prediction_path, document)
    before = {path: path.read_bytes() for path in paths.values()}
    result = validator.audit_preserved_outputs(
        tmp_path / "output", repo_root=ROOT
    )
    assert result["passed"] is False
    assert result["decisions"]["constant_velocity"] == "invalid-conflicting"
    assert {path: path.read_bytes() for path in paths.values()} == before


def test_runtime_orders_memory_before_preserved_audit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    monkeypatch.setattr(validator, "validate_d_checkout", lambda path: events.append("d"))
    monkeypatch.setattr(
        validator,
        "validate_external_authorization_record",
        lambda path: events.append("authorization") or {},
    )
    monkeypatch.setattr(
        validator,
        "validate_memory_gate",
        lambda memory: events.append("memory") or {"passed": True},
    )
    monkeypatch.setattr(
        validator,
        "validate_output_resume_state",
        lambda *args, **kwargs: events.append("audit") or {"passed": True},
    )
    validator.runtime_preflight(
        tmp_path,
        tmp_path / "authorization.json",
        output_root=tmp_path / "output",
        memory={
            "available_bytes": 20 * validator.BYTES_PER_GIB,
            "physical_bytes": 20 * validator.BYTES_PER_GIB,
        },
    )
    assert events == ["d", "authorization", "memory", "audit"]


def test_no_scientific_execution_or_u4_access_is_part_of_contract() -> None:
    contract = json.loads(
        (ROOT / validator.APPLICABILITY_CONTRACT_RELATIVE_PATH).read_text(
            encoding="utf-8"
        )
    )
    assert contract["u4_output_inspected"] is False
    source = inspect.getsource(validator.runtime_preflight)
    assert "run_person_d_step4_1_eight_family_production.py run" not in source


def _authorization_documents() -> dict[str, dict]:
    return {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in AUTHORIZATION_PACKAGE.glob("*.json")
    }


def test_superseding_authorization_record_binds_contract_roots_and_lineage() -> None:
    record = _authorization_documents()["person_d_authorization_record.json"]
    validator._validate_external_auth(ROOT, record)
    assert (
        record["supersedes_authorization_commit"]
        == validator.PERSON_B_APPLICABILITY_STARTING_AUTHORITY
    )
    assert record["applicability_contract_version"] == (
        validator.APPLICABILITY_CONTRACT_VERSION
    )
    assert record["minimum_physical_memory_gib"] == 20.0
    assert record["minimum_available_memory_gib"] == 20.0
    assert record["materialized_root"] == validator.MATERIALIZED_ROOT_ABSOLUTE_PATH
    assert record["frame_root"] == validator.FRAME_ROOT_ABSOLUTE_PATH
    assert record["output_root"] == validator.OUTPUT_ROOT_ABSOLUTE_PATH


def test_superseding_authorization_rejects_contract_or_lineage_drift() -> None:
    record = _authorization_documents()["person_d_authorization_record.json"]
    wrong_contract = copy.deepcopy(record)
    wrong_contract["applicability_contract_sha256"] = "0" * 64
    with pytest.raises(
        validator.MemoryReauthorizationError, match="applicability hash"
    ):
        validator._validate_external_auth(ROOT, wrong_contract)
    wrong_lineage = copy.deepcopy(record)
    wrong_lineage["accepted_producing_authority_by_reusable_family"][
        "constant_velocity"
    ] = validator.PERSON_D_PRIOR_RUNNER_COMMIT
    with pytest.raises(
        validator.MemoryReauthorizationError, match="preserved output decisions"
    ):
        validator._validate_external_auth(ROOT, wrong_lineage)


def test_authorized_chain_has_exact_fail_closed_runtime_sequence() -> None:
    commands = _authorization_documents()["production_commands.json"]
    chain = commands["authorized_production_chain"]
    reuse_index = chain.index(" reuse-validate ")
    preflight_index = chain.index(" runtime-preflight ")
    run_index = chain.index(
        " scripts/run_person_d_step4_1_eight_family_production.py run "
    )
    assert reuse_index < preflight_index < run_index
    assert "--verify-payloads" in chain
    assert "--resume resume" in chain
    assert commands["authorization_record_path"] in chain
    assert validator.MATERIALIZED_ROOT_ABSOLUTE_PATH in chain
    assert validator.FRAME_ROOT_ABSOLUTE_PATH in chain
    assert validator.OUTPUT_ROOT_ABSOLUTE_PATH in chain
    assert "resume-audit" in commands["resume_audit_command"]
    assert commands["runtime_sequence"] == [
        "materialized-input raw identity and reuse validation",
        "all 1695 frame payload plus fold, target, signed mapping, and source-context semantic validation",
        "physical and available memory preflight at 20.0 GiB each",
        "preserved-output provenance, inventory, and applicability audit",
        "Person D producing run with fail-closed resume",
    ]


def test_authorization_package_decisions_are_complete_and_conditional() -> None:
    documents = _authorization_documents()
    decision = documents["applicability_and_resume_decision.json"]
    assert decision["global_frame_universe_count"] == 1695
    assert decision["global_1695_prediction_assumption_removed"] is True
    assert decision["constant_velocity"]["admitted_count"] == 1690
    assert decision["constant_velocity"]["excluded_count"] == 5
    assert decision["preserved_outputs"]["prediction_count"] == 7691
    assert decision["preserved_outputs"]["runtime_revalidation_required"] is True
    assert set(decision["preserved_outputs"]["decisions"]) == set(
        validator.EXPECTED_FAMILIES
    )
    final = documents["final_authorization_decision.json"]
    assert final["previous_authorization_superseded"] is True
    assert final["person_d_code_change_required"] is False
    assert final["production_execution_performed"] is False
    assert final["final_comparison_metrics_computed"] is False


def test_superseding_authorization_package_is_canonical_and_inventoried() -> None:
    documents = _authorization_documents()
    expected_names = {
        "applicability_and_resume_decision.json",
        "authority_binding.json",
        "final_authorization_decision.json",
        "person_d_authorization_record.json",
        "production_commands.json",
        "provenance_audit_contract.json",
        "sha256_inventory.json",
        "validation_receipt.json",
    }
    assert set(documents) == expected_names
    for name, document in documents.items():
        raw = (AUTHORIZATION_PACKAGE / name).read_bytes()
        assert raw == validator.canonical_json_bytes(document)
    inventory = documents["sha256_inventory.json"]
    assert inventory["algorithm"] == "sha256"
    assert inventory["inventory_excludes_self"] is True
    expected_inventory_paths = {
        (
            "docs/status/person_b_phase4_step4_1_applicability_"
            f"reauthorization_v0_1/{name}"
        )
        for name in expected_names - {"sha256_inventory.json"}
    }
    assert set(inventory["files"]) == expected_inventory_paths
    for relative_path, expected in inventory["files"].items():
        raw = (ROOT / relative_path).read_bytes()
        assert expected == {
            "byte_size": len(raw),
            "sha256": validator._sha256(raw),
        }
