"""The A5 exit gate: ``p1_pilot_receipt.json`` (authority 6A, A5).

A5's exit is ``p1_pilot_receipt.json == PASS`` and its pass condition is
``EVERY_VERIFICATION_ITEM_PROVEN_WITH_ITS_OBSERVED_VALUE``. So the tests here
run the **whole pilot extraction campaign** over the ten banked capture units --
190 forwards, 60 arrays -- through the stub adapter, and then build the receipt
from what actually landed on disk. Nothing is asserted that was not observed.

The one thing these tests deliberately do not do is run MineWorld. The adapter
seam is the real frozen protocol (see ``test_p1_extraction.StubMineWorldAdapter``)
but no weights are loaded, no CUDA is touched and no scientific activation is
produced: the arrays here are synthetic residuals in a temporary tree.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mineocclude.experiment_iii.authority import machine_authority
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.host_preflight import EXTRACTION_HOST_STAGES
from mineocclude.experiment_iii.p1_extraction import (
    CANONICAL_INVENTORY_NAME,
    PERSON_A_RUNTIME_SCRIPTED_IMPULSE,
    PILOT_ARRAYS,
    PILOT_CAPTURES,
    PILOT_FORWARDS,
    PILOT_TARGET_ROWS,
    MineWorldPilotDecoder,
    P1ExtractionCampaign,
    capture_stream_rows,
)
from mineocclude.experiment_iii.p1_receipt import (
    REQUIRED_BINDINGS,
    build_p1_pilot_receipt,
    p1_full_pass,
)

from tests.experiment_iii.test_p1_extraction import (
    StubMineWorldAdapter,
    _RecordingHookManager,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DOCS = REPOSITORY_ROOT / "docs" / "experiment_iii"
CAPTURES = REPOSITORY_ROOT / "data" / "experiment_iii" / "p1" / "captures"
CAPTURE_LEDGER = REPOSITORY_ROOT / "data" / "experiment_iii" / "p1" / (
    "p1_capture_ledger.jsonl"
)
PLAN = DOCS / "p1" / "p1_pilot_plan.json"

pytestmark = pytest.mark.skipif(
    not (CAPTURES / "e3_p90__L0" / "capture_completion.json").is_file()
    or not CAPTURE_LEDGER.is_file(),
    reason="the banked P1 capture units are not present in this working tree",
)

CHECKPOINT_IDENTITY = machine_authority()["extraction"]["main_checkpoint_sha256"]
PREPROCESSING_IDENTITY = "person_a_legacy_preprocessing"


def _extraction_a3_receipt(tmp_path: Path) -> Path:
    """An extraction-host A3 receipt shaped exactly as ``preflight.py`` writes."""
    extraction = machine_authority()["extraction"]
    body = {
        "schema_version": "mineocclude-experiment-iii-environment-receipt-v1",
        "stage": "A3",
        "host_role": "GPU_EXTRACTION_HOST",
        "passed": True,
        "implementation_checkpoint_commit": "f" * 40,
        "authorized_stages": list(EXTRACTION_HOST_STAGES),
        "not_authorized_stages": [],
        "display": {"status": "NOT_APPLICABLE"},
        "renderer_qualification": {"status": "NOT_APPLICABLE"},
        "gpu": {"status": "EVALUATED", "available": True},
        "model_identity_checks": {
            "status": "VERIFIED",
            "verified": True,
            "main_checkpoint": {
                "path": "/weights/model.pt",
                "observed_sha256": extraction["main_checkpoint_sha256"],
                "expected_sha256": extraction["main_checkpoint_sha256"],
                "matches": True,
            },
            "vae_checkpoint": {
                "path": "/weights/vae.pt",
                "observed_sha256": extraction["vae_sha256"],
                "expected_sha256": extraction["vae_sha256"],
                "matches": True,
            },
        },
    }
    path = tmp_path / "environment_receipt_gpu_extraction_host.json"
    path.write_text(json.dumps(body, indent=2, sort_keys=True), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def extracted_pilot(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Run the complete A5 extraction half once: 10 captures, 190 forwards, 60 arrays.

    Module-scoped because it materializes 60 x 26,148,992 bytes; every test in
    this file reads the same run rather than repeating it.
    """
    namespace_root = tmp_path_factory.mktemp("repo")
    activations = namespace_root / "data" / "experiment_iii" / "p1" / "activations"
    plan = json.loads(PLAN.read_text(encoding="utf-8"))

    units = []
    for planned in plan["units"]:
        unit_id = str(planned["capture_unit_id"])
        unit_dir = CAPTURES / unit_id
        completion = json.loads(
            (unit_dir / "capture_completion.json").read_text(encoding="utf-8")
        )
        units.append(
            {
                "capture_unit_id": unit_id,
                "identity": completion["identity"],
                "condition_id": completion["condition_id"],
                "unit_dir": unit_dir,
                "seed": int(completion["spec"]["seed"]),
                "source_capture_hash": str(completion["spec_sha256"]),
                "target_model_frame_indices": [
                    int(value) for value in completion["target_model_frame_indices"]
                ],
            }
        )

    adapter = StubMineWorldAdapter()
    campaign = P1ExtractionCampaign(
        units,
        output_root=activations,
        ledger_path=activations / "p1_extraction_ledger.jsonl",
        extraction_spec_hash="e" * 64,
        namespace_root=namespace_root,
    )

    def decoder_factory(unit: dict[str, Any]) -> MineWorldPilotDecoder:
        return MineWorldPilotDecoder(
            adapter,
            adapter.runtime_identity,
            unit_dir=unit["unit_dir"],
            trajectory_id=unit["capture_unit_id"],
            seed=unit["seed"],
            rows=capture_stream_rows(unit["unit_dir"]),
            impulse_orientation=PERSON_A_RUNTIME_SCRIPTED_IMPULSE,
            hook_manager_factory=lambda modules: _RecordingHookManager(
                modules, seed=11
            ),
            frame_loader=lambda path: _blank_frame(),
        )

    result = campaign.run(
        decoder_factory,
        checkpoint_identity=CHECKPOINT_IDENTITY,
        preprocessing_identity=PREPROCESSING_IDENTITY,
    )
    return {
        "namespace_root": namespace_root,
        "activations": activations,
        "adapter": adapter,
        "campaign": campaign,
        "result": result,
        "units": units,
    }


def _blank_frame():
    import numpy as np

    return np.zeros((360, 640, 3), dtype=np.uint8)


# --------------------------------------------------------------------------
# The campaign's own counts
# --------------------------------------------------------------------------


def test_the_pilot_campaign_issues_exactly_one_hundred_ninety_forwards(
    extracted_pilot: dict[str, Any],
) -> None:
    """190, not 1,140 -- an extra forward per layer or slice is not authorized."""
    adapter = extracted_pilot["adapter"]
    inventory = extracted_pilot["result"]["inventory"]
    assert adapter.teacher_forced_calls == PILOT_FORWARDS == 190
    assert inventory["forwards_this_run"] == 190
    assert inventory["total_captures"] == PILOT_CAPTURES == 10


def test_the_pilot_campaign_persists_exactly_sixty_arrays(
    extracted_pilot: dict[str, Any],
) -> None:
    inventory = extracted_pilot["result"]["inventory"]
    assert inventory["arrays_expected"] == PILOT_ARRAYS == 60
    assert inventory["arrays_complete"] == 60
    assert inventory["complete"] is True
    assert inventory["production_identities_used"] is False
    assert inventory["identities"] == ["e3_p90", "e3_p91"]


def test_a_completed_capture_is_skipped_on_restart(
    extracted_pilot: dict[str, Any],
) -> None:
    """Resume is per unit and never re-runs a completed capture's forwards."""
    campaign = extracted_pilot["campaign"]
    for unit in extracted_pilot["units"]:
        assert campaign.capture_is_complete(unit) is True

    adapter = StubMineWorldAdapter()
    restarted = P1ExtractionCampaign(
        extracted_pilot["units"],
        output_root=extracted_pilot["activations"],
        ledger_path=extracted_pilot["activations"] / "p1_extraction_ledger.jsonl",
        extraction_spec_hash="e" * 64,
        namespace_root=extracted_pilot["namespace_root"],
    )
    result = restarted.run(
        lambda unit: pytest.fail("a COMPLETE capture must not be re-extracted"),
        checkpoint_identity=CHECKPOINT_IDENTITY,
        preprocessing_identity=PREPROCESSING_IDENTITY,
    )
    assert len(result["skipped"]) == PILOT_CAPTURES
    assert result["extracted"] == []
    assert adapter.teacher_forced_calls == 0


def test_a_changed_extraction_spec_is_not_adopted_as_a_resume(
    extracted_pilot: dict[str, Any],
) -> None:
    """Same-spec resume only: a spec change discards rather than reuses."""
    drifted = P1ExtractionCampaign(
        extracted_pilot["units"],
        output_root=extracted_pilot["activations"],
        ledger_path=extracted_pilot["activations"] / "p1_extraction_ledger.jsonl",
        extraction_spec_hash="d" * 64,
        namespace_root=extracted_pilot["namespace_root"],
    )
    assert drifted.capture_is_complete(extracted_pilot["units"][0]) is False


# --------------------------------------------------------------------------
# The receipt
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pilot_receipt(
    extracted_pilot: dict[str, Any], tmp_path_factory: pytest.TempPathFactory
) -> dict[str, Any]:
    a3 = _extraction_a3_receipt(tmp_path_factory.mktemp("a3"))
    return build_p1_pilot_receipt(
        plan_path=PLAN,
        captures_root=CAPTURES,
        capture_ledger_path=CAPTURE_LEDGER,
        activations_root=extracted_pilot["activations"],
        p0_selection_receipt_path=DOCS / "p0" / "P0_SELECTION_RECEIPT.json",
        resume_receipt_path=DOCS / "p1" / "P1_RESUME_RECEIPT.json",
        capture_host_a3_path=(
            DOCS / "receipts" / "environment_receipt_wsl2_capture_host.json"
        ),
        extraction_host_a3_path=a3,
        extraction_implementation={
            "checkpoint_commit": "a" * 40,
            "source_closure": "b" * 64,
            "record_count": 1234,
            "includes_uncommitted_working_tree": False,
        },
    )


def test_the_full_a5_exit_gate_passes_on_complete_evidence(
    pilot_receipt: dict[str, Any],
) -> None:
    assert pilot_receipt["failed_items"] == []
    assert pilot_receipt["missing_bindings"] == []
    assert pilot_receipt["P1_RESULT"] == "PASS"
    assert pilot_receipt["P1_FULL_PASS"] is True
    assert p1_full_pass(pilot_receipt) is True


def test_the_receipt_binds_everything_a5_requires(
    pilot_receipt: dict[str, Any],
) -> None:
    for name in REQUIRED_BINDINGS:
        assert pilot_receipt["bindings"].get(name), name


def test_every_verification_item_carries_its_observed_value(
    pilot_receipt: dict[str, Any],
) -> None:
    """A5 requires the *observed* value, not merely a claim that it matched."""
    for name, item in pilot_receipt["verification_items"].items():
        assert "observed" in item and "expected" in item, name
        assert item["requirement"], name
        assert item["passed"] is True, name


def test_the_receipt_counts_are_the_frozen_counts(
    pilot_receipt: dict[str, Any],
) -> None:
    bindings = pilot_receipt["bindings"]
    assert bindings["p1_local_capture"]["captures_complete"] == PILOT_CAPTURES == 10
    assert bindings["target_rows"]["observed_total"] == PILOT_TARGET_ROWS == 190
    assert bindings["forward_ledger"]["observed"] == PILOT_FORWARDS == 190
    assert bindings["forward_ledger"]["rows"] == 190
    assert bindings["array_inventory"]["observed"] == PILOT_ARRAYS == 60
    assert bindings["physical_array_validation"]["arrays_validated"] == 60
    assert bindings["one_forward_validation"]["logical_row_tensors"] == 1140
    assert bindings["array_inventory"]["inventory_name"] == CANONICAL_INVENTORY_NAME


def test_the_receipt_records_both_implementation_identities(
    pilot_receipt: dict[str, Any],
) -> None:
    """P1 spans two checkpoints and the receipt must not collapse them.

    The ten capture units were banked under the capture host's closure; the 60
    arrays are produced under the extraction host's. Recording one as "the" P1
    checkpoint would be a false claim about bytes already on disk.
    """
    capture = pilot_receipt["bindings"]["capture_implementation"]
    extraction = pilot_receipt["bindings"]["extraction_implementation"]
    assert capture["role"] == "LOCAL_CAPTURE_HOST"
    assert extraction["role"] == "GPU_EXTRACTION_HOST"
    assert capture["single_closure"] is True
    assert capture["source_closure"]
    assert extraction["source_closure"]
    assert capture["source_closure"] != extraction["source_closure"]
    assert (
        pilot_receipt["verification_items"]["dual_checkpoint_provenance_recorded"][
            "passed"
        ]
        is True
    )


def test_the_receipt_never_emits_a_production_gate(
    pilot_receipt: dict[str, Any],
) -> None:
    """A5 exiting is not P2 passing; only A6 may emit either flag."""
    assert pilot_receipt["PRODUCTION_AUTHORIZED"] is False
    assert pilot_receipt["MODEL_INFERENCE_AUTHORIZED"] is False
    assert pilot_receipt["P2_EXECUTED"] is False
    assert pilot_receipt["next_authorized_state"] == "A6"


def test_no_verification_item_is_a_pilot_outcome(
    pilot_receipt: dict[str, Any],
) -> None:
    """Authority 6A: pilot accuracy may never inform a scientific choice.

    Every gate item is an engineering count, a hash or a boolean. A scan of the
    receipt's prose would be the wrong instrument -- the note explaining the rule
    naturally contains the word -- so what is checked is the shape of the items
    the verdict is computed from.
    """
    assert pilot_receipt["pilot_outcomes_consulted"] is False
    for name, item in pilot_receipt["verification_items"].items():
        assert isinstance(item["expected"], (int, str, bool)), name
        assert isinstance(item["observed"], (int, str, bool)), name
        assert not isinstance(item["expected"], float), name


def test_the_verdict_does_not_move_with_the_analysis_smoke_result(
    extracted_pilot: dict[str, Any], tmp_path: Path
) -> None:
    """The strongest form of "no pilot outcome is an input": vary it, and see.

    The smoke run is recorded, because 6A asks whether the analysis code produces
    finite numbers. It is not a term in the gate, so a receipt built with a
    dismal smoke result and one built with a glowing one reach the same verdict
    and differ only in the recorded field.
    """
    a3 = _extraction_a3_receipt(tmp_path)

    def _build(smoke: dict[str, Any]) -> dict[str, Any]:
        return build_p1_pilot_receipt(
            plan_path=PLAN,
            captures_root=CAPTURES,
            capture_ledger_path=CAPTURE_LEDGER,
            activations_root=extracted_pilot["activations"],
            p0_selection_receipt_path=DOCS / "p0" / "P0_SELECTION_RECEIPT.json",
            resume_receipt_path=DOCS / "p1" / "P1_RESUME_RECEIPT.json",
            capture_host_a3_path=(
                DOCS / "receipts" / "environment_receipt_wsl2_capture_host.json"
            ),
            extraction_host_a3_path=a3,
            extraction_implementation={
                "checkpoint_commit": "a" * 40,
                "source_closure": "b" * 64,
            },
            analysis_smoke=smoke,
        )

    poor = _build({"finite": True, "pilot_decoding_score": 0.01})
    strong = _build({"finite": True, "pilot_decoding_score": 0.99})
    assert poor["P1_RESULT"] == strong["P1_RESULT"] == "PASS"
    assert poor["verification_items"] == strong["verification_items"]
    assert poor["analysis_smoke"] != strong["analysis_smoke"]


# --------------------------------------------------------------------------
# Fail-closed
# --------------------------------------------------------------------------


def test_a_capture_host_a3_receipt_cannot_stand_in_for_the_extraction_host(
    extracted_pilot: dict[str, Any], tmp_path: Path
) -> None:
    body = json.loads(
        (DOCS / "receipts" / "environment_receipt_wsl2_capture_host.json").read_text(
            encoding="utf-8"
        )
    )
    path = tmp_path / "capture_as_extraction.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(ExperimentIIIError) as error:
        build_p1_pilot_receipt(
            plan_path=PLAN,
            captures_root=CAPTURES,
            capture_ledger_path=CAPTURE_LEDGER,
            activations_root=extracted_pilot["activations"],
            p0_selection_receipt_path=DOCS / "p0" / "P0_SELECTION_RECEIPT.json",
            resume_receipt_path=DOCS / "p1" / "P1_RESUME_RECEIPT.json",
            capture_host_a3_path=(
                DOCS / "receipts" / "environment_receipt_wsl2_capture_host.json"
            ),
            extraction_host_a3_path=path,
            extraction_implementation={"source_closure": "b" * 64},
        )
    assert error.value.blocker == "ENV_CHECKPOINT_HASH_MISMATCH"


def test_missing_arrays_refuse_the_receipt(tmp_path: Path) -> None:
    a3 = _extraction_a3_receipt(tmp_path)
    with pytest.raises(ExperimentIIIError) as error:
        build_p1_pilot_receipt(
            plan_path=PLAN,
            captures_root=CAPTURES,
            capture_ledger_path=CAPTURE_LEDGER,
            activations_root=tmp_path / "no_activations_here",
            p0_selection_receipt_path=DOCS / "p0" / "P0_SELECTION_RECEIPT.json",
            resume_receipt_path=DOCS / "p1" / "P1_RESUME_RECEIPT.json",
            capture_host_a3_path=(
                DOCS / "receipts" / "environment_receipt_wsl2_capture_host.json"
            ),
            extraction_host_a3_path=a3,
            extraction_implementation={"source_closure": "b" * 64},
        )
    assert error.value.blocker == "EXTRACTION_INVENTORY_INCOMPLETE"


def test_p1_full_pass_refuses_a_receipt_with_a_failed_item() -> None:
    assert p1_full_pass({"P1_FULL_PASS": True, "P1_RESULT": "PASS"}) is True
    assert (
        p1_full_pass(
            {"P1_FULL_PASS": True, "P1_RESULT": "PASS", "failed_items": ["counts"]}
        )
        is False
    )
    assert (
        p1_full_pass(
            {
                "P1_FULL_PASS": True,
                "P1_RESULT": "PASS",
                "missing_bindings": ["forward_ledger"],
            }
        )
        is False
    )
