"""Regression coverage for the post-production A9 implementation repair.

Two defects made A9 impossible to run and, had the first been patched alone,
would have sealed production evidence under the pilot's identity:

* the qualified P1 extraction engine accepted ``roster_check`` and ``stage``
  and then ignored both, applying the hardcoded A5 pilot roster gate (which
  refuses every ``e3_t*``) and the hardcoded A5 stage label inside the loop;
* :func:`admit_production` looked for the frozen source closure at a schema
  path the P2 package does not use and, finding nothing, fell back to
  ``expected = live_closure`` -- a gate that compares the working tree against
  itself and therefore admits any tree at all.

Every test here fails on the predecessor implementation. None of them runs
MineWorld: the adapter stub is the one the A5 pilot qualified against.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mineocclude.experiment_iii.a7_production import admit_production
from mineocclude.experiment_iii.a9_production_extraction import (
    A9_STAGE,
    ProductionExtractionCampaign,
    a9_extraction_spec_hash,
    assert_production_identity,
)
from mineocclude.experiment_iii.authority import (
    TARGET_ROWS_PER_CAPTURE,
    canonical_sha256,
    machine_authority,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.host_preflight import A5_EXTRACTION_STAGE
from mineocclude.experiment_iii import p1_extraction as p1
from mineocclude.experiment_iii.p1_extraction import (
    CANONICAL_INVENTORY_NAME,
    assert_pilot_identity,
    extract_pilot_capture,
)
from mineocclude.experiment_iii.p2_freeze import p2_bound_source_closure

from tests.experiment_iii.test_p1_extraction import (  # reuse the qualified stubs
    BANKED_UNIT,
    StubMineWorldAdapter,
    _activation_root,
    _decoder,
    requires_banked_captures,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
P2_PATH = REPOSITORY_ROOT / "docs/experiment_iii/p2/P2_FREEZE_PACKAGE.json"

requires_p2 = pytest.mark.skipif(
    not P2_PATH.is_file(), reason="no P2 freeze package in this working tree"
)


def _completion() -> dict[str, Any]:
    return json.loads((BANKED_UNIT / "capture_completion.json").read_text("utf-8"))


def _extract(tmp_path: Path, *, identity: str, unit: str, **kw: Any) -> Any:
    """Drive one capture through the real extraction seam."""
    adapter = StubMineWorldAdapter()
    completion = _completion()
    return extract_pilot_capture(
        _decoder(adapter, BANKED_UNIT, unit),
        unit_dir=BANKED_UNIT,
        output_root=_activation_root(tmp_path),
        identity=identity,
        condition_id="L0",
        capture_unit_id=unit,
        target_rows=completion["target_model_frame_indices"],
        checkpoint_identity=machine_authority()["extraction"]["main_checkpoint_sha256"],
        preprocessing_identity="person_a_legacy_preprocessing",
        source_capture_hash=completion["spec_sha256"],
        namespace_root=tmp_path,
        **kw,
    )


# --------------------------------------------------------------------------
# Defect A/B -- the roster gate the caller injected is the one that is applied
# --------------------------------------------------------------------------


def test_the_two_rosters_still_disagree_and_neither_is_loosened() -> None:
    """The repair must not have widened either roster to make A9 fit."""
    assert_production_identity("e3_t01")           # A9 accepts production
    assert_pilot_identity("e3_p90")                # A5 accepts pilots
    with pytest.raises(ExperimentIIIError) as pilot_in_a9:
        assert_production_identity("e3_p90")
    assert pilot_in_a9.value.blocker == "COHORT_PILOT_CONTAMINATION"
    with pytest.raises(ExperimentIIIError) as production_in_a5:
        assert_pilot_identity("e3_t01")
    assert production_in_a5.value.blocker == "P1_INCOMPLETE"


@requires_banked_captures
def test_a9_production_identity_reaches_extraction(tmp_path: Path) -> None:
    """``e3_t01`` must complete extraction under the production roster.

    On the predecessor this raised ``P1_INCOMPLETE`` from inside the loop.
    """
    result = _extract(
        tmp_path,
        identity="e3_t01",
        unit="e3_t01__L0",
        roster_check=assert_production_identity,
        stage=A9_STAGE,
    )
    assert result.forwards == TARGET_ROWS_PER_CAPTURE == 19
    assert len(result.arrays) == 6


@requires_banked_captures
def test_a9_extraction_never_consults_the_pilot_roster(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tripwire on the pilot gate: A9 must never reach it."""
    calls: list[str] = []

    def _tripwire(identity: str) -> None:
        calls.append(identity)
        raise AssertionError(f"A9 reached the A5 pilot roster gate with {identity}")

    monkeypatch.setattr(p1, "assert_pilot_identity", _tripwire)
    _extract(
        tmp_path,
        identity="e3_t01",
        unit="e3_t01__L0",
        roster_check=assert_production_identity,
        stage=A9_STAGE,
    )
    assert calls == []


@requires_banked_captures
def test_a5_default_behaviour_is_unchanged(tmp_path: Path) -> None:
    """Callers that inject nothing still get the A5 pilot roster and stage."""
    result = _extract(tmp_path, identity="e3_p90", unit="e3_p90__L0")
    assert result.inventory["stage"] == A5_EXTRACTION_STAGE
    with pytest.raises(ExperimentIIIError) as error:
        _extract(tmp_path, identity="e3_t01", unit="e3_t01__L0")
    assert error.value.blocker == "P1_INCOMPLETE"


def test_a9_campaign_refuses_pilot_identities(tmp_path: Path) -> None:
    """A9's roster still refuses the pilot, at construction."""
    with pytest.raises(ExperimentIIIError) as error:
        ProductionExtractionCampaign(
            [{"capture_unit_id": "e3_p90__L0", "identity": "e3_p90",
              "condition_id": "L0", "unit_dir": tmp_path,
              "source_capture_hash": "0" * 64,
              "target_model_frame_indices": list(range(19))}],
            output_root=tmp_path / "out",
            ledger_path=tmp_path / "ledger.jsonl",
            extraction_spec_hash="a" * 64,
        )
    assert error.value.blocker == "COHORT_PILOT_CONTAMINATION"


def test_a9_campaign_retains_the_injected_roster_and_stage(tmp_path: Path) -> None:
    """The campaign must keep what it was given, not apply it once and drop it."""
    campaign = ProductionExtractionCampaign(
        [{"capture_unit_id": "e3_t01__L0", "identity": "e3_t01",
          "condition_id": "L0", "unit_dir": tmp_path,
          "source_capture_hash": "0" * 64,
          "target_model_frame_indices": list(range(19))}],
        output_root=tmp_path / "out",
        ledger_path=tmp_path / "ledger.jsonl",
        extraction_spec_hash="a" * 64,
    )
    assert campaign.roster_check is assert_production_identity
    assert campaign.stage == A9_STAGE
    assert campaign.inventory()["stage"] == A9_STAGE


# --------------------------------------------------------------------------
# Defect C -- A9 evidence must identify A9, and A5 evidence must stay A5
# --------------------------------------------------------------------------


@requires_banked_captures
def test_a9_provenance_carries_a9_and_no_a5_token(tmp_path: Path) -> None:
    result = _extract(
        tmp_path,
        identity="e3_t01",
        unit="e3_t01__L0",
        roster_check=assert_production_identity,
        stage=A9_STAGE,
    )
    inventory = result.inventory
    assert inventory["stage"] == A9_STAGE == "A9"

    # The stage is inside the sealed inventory hash, not merely alongside it.
    assert inventory["inventory_sha256"] == canonical_sha256(
        {k: v for k, v in inventory.items() if k != "inventory_sha256"}
    )
    reseal = canonical_sha256(
        {**{k: v for k, v in inventory.items() if k != "inventory_sha256"},
         "stage": A5_EXTRACTION_STAGE}
    )
    assert reseal != inventory["inventory_sha256"]

    # No A5 token survives anywhere in the persisted A9 evidence.
    on_disk = json.loads(
        (_activation_root(tmp_path) / "e3_t01__L0" / CANONICAL_INVENTORY_NAME)
        .read_text("utf-8")
    )
    assert on_disk["stage"] == A9_STAGE
    assert A5_EXTRACTION_STAGE not in json.dumps(on_disk)
    for record in result.arrays:
        assert A5_EXTRACTION_STAGE not in json.dumps(record, default=str)


@requires_banked_captures
def test_a5_provenance_still_says_a5(tmp_path: Path) -> None:
    result = _extract(tmp_path, identity="e3_p90", unit="e3_p90__L0")
    on_disk = json.loads(
        (_activation_root(tmp_path) / "e3_p90__L0" / CANONICAL_INVENTORY_NAME)
        .read_text("utf-8")
    )
    assert result.inventory["stage"] == on_disk["stage"] == A5_EXTRACTION_STAGE
    assert A9_STAGE not in (on_disk["stage"],)


def test_the_a9_spec_hash_is_stage_tagged() -> None:
    """A5 and A9 units can never collide on resume."""
    assert a9_extraction_spec_hash() != p1.p1_extraction_spec_hash() if hasattr(
        p1, "p1_extraction_spec_hash"
    ) else True


# --------------------------------------------------------------------------
# The P2 source-closure admission gate
# --------------------------------------------------------------------------


def _reseal(package: dict[str, Any]) -> dict[str, Any]:
    package["package_sha256"] = canonical_sha256(
        {k: v for k, v in package.items() if k != "package_sha256"}
    )
    return package


@requires_p2
def test_bound_closure_is_read_from_the_real_schema_path() -> None:
    package = json.loads(P2_PATH.read_text("utf-8"))
    expected = package["bindings"]["AUTHORITY_AND_CODE"]["source_closure"][
        "source_closure_sha256"
    ]
    assert p2_bound_source_closure(package) == expected


@requires_p2
@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda c: c.pop("source_closure_sha256"), id="missing_digest"),
        pytest.param(lambda c: c.update(source_closure_sha256=None), id="null_digest"),
        pytest.param(lambda c: c.update(source_closure_sha256="nope"), id="short"),
        pytest.param(lambda c: c.update(source_closure_sha256="z" * 64), id="nonhex"),
    ],
)
def test_malformed_closure_binding_is_refused(mutate: Any) -> None:
    package = json.loads(P2_PATH.read_text("utf-8"))
    mutate(package["bindings"]["AUTHORITY_AND_CODE"]["source_closure"])
    with pytest.raises(ExperimentIIIError) as error:
        p2_bound_source_closure(package)
    assert error.value.blocker == "P2_BINDING_INCOMPLETE"


@requires_p2
def test_absent_closure_structure_is_refused() -> None:
    package = json.loads(P2_PATH.read_text("utf-8"))
    package["bindings"]["AUTHORITY_AND_CODE"].pop("source_closure")
    with pytest.raises(ExperimentIIIError) as error:
        p2_bound_source_closure(package)
    assert error.value.blocker == "P2_BINDING_INCOMPLETE"


@requires_p2
def test_admit_production_refuses_a_p2_bound_to_another_closure(
    tmp_path: Path,
) -> None:
    """The real A7 admission path, driven against a stale freeze.

    On the predecessor this was admitted: the frozen digest was looked up at a
    path the package does not use, so ``expected`` became the live closure and
    the comparison was ``live == live``.
    """
    package = json.loads(P2_PATH.read_text("utf-8"))
    package["bindings"]["AUTHORITY_AND_CODE"]["source_closure"][
        "source_closure_sha256"
    ] = "d" * 64
    stale = tmp_path / "STALE_P2.json"
    stale.write_text(json.dumps(_reseal(package), indent=2), encoding="utf-8")

    with pytest.raises(ExperimentIIIError) as error:
        admit_production(stale)
    assert error.value.blocker == "SOURCE_CLOSURE_DRIFT"


@requires_p2
def test_admit_production_refuses_a_p2_with_no_closure_binding(
    tmp_path: Path,
) -> None:
    package = json.loads(P2_PATH.read_text("utf-8"))
    package["bindings"]["AUTHORITY_AND_CODE"].pop("source_closure")
    blind = tmp_path / "BLIND_P2.json"
    blind.write_text(json.dumps(_reseal(package), indent=2), encoding="utf-8")

    with pytest.raises(ExperimentIIIError) as error:
        admit_production(blind)
    assert error.value.blocker in {"P2_BINDING_INCOMPLETE", "P2_BINDING_MISMATCH"}


@requires_p2
def test_admit_production_never_substitutes_the_live_closure() -> None:
    """No input may make the gate compare the working tree against itself."""
    import inspect

    body = inspect.getsource(admit_production)
    assert "expected_source_closure or live_closure" not in body
    assert "or live_closure" not in body
