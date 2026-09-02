"""Regression coverage for the A10 extraction-validation repair.

Two defects would have stopped the chain immediately after A9 had spent every
production forward:

* the supervisor hands A10 the extraction output root, and A10 treated it as a
  single capture root -- it looked for ``activations/extraction_inventory.json``,
  found none, validated 0 of 750 arrays and exited 1;
* A10 persisted no receipt at all, though ``EXPECTED_ARTIFACT_INVENTORY.json``
  marks ``extraction_validation_receipt.json`` required, hashed and durable
  before the next stage.

A third, quieter one: "no failures" was reported as PASS even when almost
nothing was on disk, because nothing compared the corpus against the frozen
125 captures / 750 arrays.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.p1_extraction import CANONICAL_INVENTORY_NAME

import importlib.util

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "_a10_driver", REPOSITORY_ROOT / "scripts/experiment_iii/validate_extraction.py"
)
a10 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(a10)


def _capture_root(parent: Path, name: str) -> Path:
    root = parent / name
    (root / "activations").mkdir(parents=True, exist_ok=True)
    (root / CANONICAL_INVENTORY_NAME).write_text(
        json.dumps({"capture_unit_id": name, "stage": "A9"}), encoding="utf-8"
    )
    return root


def test_the_extraction_output_root_expands_into_capture_roots(tmp_path: Path) -> None:
    """The supervisor's invocation. Previously this found nothing."""
    out = tmp_path / "activations"
    expected = [_capture_root(out, f"e3_t0{i}__L0") for i in (1, 2, 3)]
    assert a10._capture_roots([out], CANONICAL_INVENTORY_NAME) == sorted(expected)


def test_a_capture_root_is_still_accepted_directly(tmp_path: Path) -> None:
    root = _capture_root(tmp_path / "activations", "e3_t01__L0")
    assert a10._capture_roots([root], CANONICAL_INVENTORY_NAME) == [root]


def test_a_root_that_holds_no_capture_refuses_rather_than_passing_empty(
    tmp_path: Path,
) -> None:
    """An empty expansion must never contribute zero captures to a PASS."""
    empty = tmp_path / "activations"
    empty.mkdir()
    with pytest.raises(ExperimentIIIError) as error:
        a10._capture_roots([empty], CANONICAL_INVENTORY_NAME)
    assert error.value.blocker == "EXTRACTION_INVENTORY_INCOMPLETE"


def test_a10_writes_its_required_receipt_and_fails_closed(tmp_path: Path) -> None:
    """The receipt exists, records the counts, and says PASS only when it is."""
    out = tmp_path / "activations"
    for i in (1, 2):
        _capture_root(out, f"e3_t0{i}__L0")
    receipt = (tmp_path / "docs/experiment_iii/receipts"
               / "extraction_validation_receipt.json")
    rc = a10.main([str(out), "--receipt", str(receipt),
                   "--namespace-root", str(tmp_path),
                   "--expect-captures", "125", "--expect-arrays", "750"])
    assert rc == 1                                   # 2 captures is not 125
    assert receipt.is_file()
    doc = json.loads(receipt.read_text(encoding="utf-8"))
    assert doc["stage"] == "A10"
    assert doc["passed"] is False
    assert doc["expected_captures"] == 125
    assert doc["expected_arrays"] == 750
    assert doc["arrays_validated"] < 750
    assert doc["authority_binding"]["AUTHORITY_SHA256"]


def test_a10_count_gate_is_what_turns_no_failures_into_a_real_pass(
    tmp_path: Path,
) -> None:
    """Without an expected count, a near-empty corpus reported PASS."""
    out = tmp_path / "activations"
    _capture_root(out, "e3_t01__L0")
    receipt = tmp_path / "docs/experiment_iii/receipts/r.json"
    rc = a10.main([str(out), "--receipt", str(receipt),
                   "--namespace-root", str(tmp_path), "--expect-captures", "125"])
    doc = json.loads(receipt.read_text(encoding="utf-8"))
    assert rc == 1
    assert any("captures 1 != expected 125" in line for line in doc["shortfall"])
