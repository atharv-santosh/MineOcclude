from __future__ import annotations

import json
from pathlib import Path

import pytest

from mineocclude.regime_a import RegimeAError, canonical_sha256
from scripts.freeze_regime_a_guard_amendment_calibration_v2_1 import build_extension
from scripts.run_regime_a import ProductionCaptureWorker
from scripts.run_regime_a_guard_amendment_calibration_v2_1_capture import validate_specs
from scripts.run_regime_a_first25_v2_amendment_1 import validate_manifest


ROOT = Path(__file__).resolve().parents[1]
AMENDMENT = (
    ROOT
    / "docs/status/integration/regime_a_occlusion_extraction_v0_1/v2_amendment_1"
)


def test_calibration_extension_was_frozen_as_six_new_crossings_per_direction() -> None:
    rows = build_extension()
    assert len(rows) == 12
    assert sum(row["direction"] == "LEFT_TO_RIGHT" for row in rows) == 6
    assert sum(row["direction"] == "RIGHT_TO_LEFT" for row in rows) == 6
    assert len({row["trajectory_spec_id"] for row in rows}) == 12
    assert len({row["seed"] for row in rows}) == 12
    assert all(row["NON_SCIENTIFIC_CALIBRATION"] is True for row in rows)
    assert all(row["ELIGIBLE_FOR_REGIME_A_RESULTS"] is False for row in rows)
    assert all(canonical_sha256({k: v for k, v in row.items() if k != "spec_hash"}) == row["spec_hash"] for row in rows)


def test_frozen_calibration_manifest_and_sidecar_validate() -> None:
    rows = validate_specs(
        AMENDMENT / "calibration_extension_manifest.jsonl",
        AMENDMENT / "calibration_extension_manifest.sha256",
    )
    assert [row["calibration_replicate"] for row in rows[:6]] == list(range(3, 9))
    assert [row["calibration_replicate"] for row in rows[6:]] == list(range(3, 9))


def test_amended_capture_identity_is_explicit_and_backward_compatible() -> None:
    old = {"spec_hash": "a" * 64}
    amended = {"spec_hash": "b" * 64, "raw_capture_spec_hash": "a" * 64}
    assert ProductionCaptureWorker._raw_capture_spec_hash(old) == "a" * 64
    assert ProductionCaptureWorker._raw_capture_spec_hash(amended) == "a" * 64
    with pytest.raises(RegimeAError, match="raw capture spec hash"):
        ProductionCaptureWorker._raw_capture_spec_hash(
            {"spec_hash": "b" * 64, "raw_capture_spec_hash": "not-a-hash"}
        )


def test_trigger_receipt_excludes_t04_and_records_zero_outcomes() -> None:
    receipt = json.loads((AMENDMENT / "amendment_trigger_receipt.json").read_text())
    assert receipt["trigger_classification"] == "TRUE_FROZEN_GUARD_EXCEEDANCE"
    assert receipt["t04_excluded_from_numerical_calibration_authority"] is True
    assert receipt["scientific_decoding_outcomes_computed"] == 0
    assert receipt["collection_stopped_before_amendment"] is True


def test_amended_manifest_validates_and_preserves_capture_identity() -> None:
    rows, _digest = validate_manifest(
        AMENDMENT / "trajectory_manifest_v2_1_amendment_1.jsonl",
        AMENDMENT / "trajectory_manifest_v2_1_amendment_1.sha256",
        AMENDMENT / "directional_visibility_authority_v2_1_amendment_1.json",
    )
    original = [
        json.loads(line)
        for line in (
            ROOT
            / "docs/status/integration/regime_a_occlusion_extraction_v0_1/v2/trajectory_manifest.jsonl"
        ).read_text().splitlines()
        if line.strip()
    ]
    assert [row["trajectory_spec_id"] for row in rows] == [
        row["trajectory_spec_id"] for row in original
    ]
    assert [row["seed"] for row in rows] == [row["seed"] for row in original]
    assert [row["raw_capture_spec_hash"] for row in rows] == [
        row["spec_hash"] for row in original
    ]
