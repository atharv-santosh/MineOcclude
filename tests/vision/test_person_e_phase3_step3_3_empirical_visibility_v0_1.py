"""Focused proofs for the frozen Person E Step 3.3 empirical handoff."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT
    / "scripts/generate_person_e_phase3_step3_3_empirical_visibility_v0_1.py"
)
SPEC = importlib.util.spec_from_file_location("person_e_step3_3_generator", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
GEN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GEN)
OUTPUT = ROOT / GEN.OUTPUT_RELATIVE_PATH


def _person_c_root() -> Path:
    value = os.environ.get("MINEOCCLUDE_PERSON_C_STEP3_3_ROOT")
    if not value:
        pytest.skip("MINEOCCLUDE_PERSON_C_STEP3_3_ROOT is not configured.")
    root = Path(value)
    if not root.is_dir():
        pytest.skip("Detached Person C Step 3.3 worktree is unavailable.")
    return root


def _person_c_package() -> Path:
    return _person_c_root() / GEN.C_PACKAGE_RELATIVE_PATH


def _committed_output() -> Path:
    if not OUTPUT.is_dir():
        pytest.skip("Production empirical package has not been generated yet.")
    return OUTPUT


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _c_rows() -> list[dict]:
    return _jsonl(_person_c_package() / GEN.C_GENERATION_MANIFEST)


def _empirical_rows() -> list[dict]:
    return _jsonl(_committed_output() / "empirical_visibility_records.jsonl")


def _diagnostic_rows() -> list[dict]:
    return _jsonl(_committed_output() / "detector_diagnostics.jsonl")


def _generation_row(**changes) -> dict:
    row = {
        "archive_member_path": "frames_640x360/000000.png",
        "archive_path": "canonical_frames/t_frames_640x360.tar.gz",
        "archive_sha256": "a" * 64,
        "canonical_camera_pose_id": "layout_01_canonical_pose_v1",
        "coordinate_convention": GEN.EXPECTED_COORDINATE_CONVENTION,
        "frame_640_sha256": "b" * 64,
        "frame_size_bytes": 10,
        "layout_id": "layout_01",
        "model_frame_idx": 0,
        "render_frame_idx": 0,
        "resolution": GEN.EXPECTED_RESOLUTION,
        "source_frame_map": "data/autonomous/t/frame_map.parquet",
        "source_frame_map_sha256": "c" * 64,
        "trajectory_id": "layout_01_ep1",
    }
    row.update(changes)
    return row


def _identity_row(row: dict) -> dict:
    return {
        "model_frame_idx": row["model_frame_idx"],
        "source_frame_map": row["source_frame_map"],
        "source_frame_map_sha256": row["source_frame_map_sha256"],
        "trajectory_id": row["trajectory_id"],
    }


def _handoff_rows(*, accepted: bool = True) -> tuple[dict, dict, dict]:
    generation = _generation_row()
    empirical = {
        "canonical_camera_pose_id": generation["canonical_camera_pose_id"],
        "coordinate_convention": generation["coordinate_convention"],
        "detector_version": GEN.DETECTOR_VERSION,
        "empirical_magenta_visible": accepted,
        "layout_id": generation["layout_id"],
        "model_frame_idx": generation["model_frame_idx"],
        "resolution": generation["resolution"],
        "trajectory_id": generation["trajectory_id"],
    }
    diagnostic = {
        "accepted": accepted,
        "bounding_box_xyxy": [1, 2, 3, 4] if accepted else None,
        "candidate_blob_count": 1 if accepted else 0,
        "centroid_xy": [1.5, 2.5] if accepted else None,
        "decision_ordinal": 1,
        "detector_identity_sha256": GEN.DETECTOR_IDENTITY_SHA256,
        "detector_status": "detected" if accepted else "not_detected",
        "detector_version": GEN.DETECTOR_VERSION,
        "empirical_magenta_visible": accepted,
        "frame_640_sha256": generation["frame_640_sha256"],
        "model_frame_idx": generation["model_frame_idx"],
        "rejection_reason": None if accepted else "no_threshold_match",
        "selected_blob_area_pixels": 20 if accepted else None,
        "threshold_match_pixels": 20 if accepted else 0,
        "trajectory_id": generation["trajectory_id"],
    }
    return generation, empirical, diagnostic


def _png(size: tuple[int, int] = (640, 360)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color=(10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def _archive_fixture(tmp_path: Path, payload: bytes) -> tuple[Path, list[dict]]:
    package = tmp_path / "package"
    archive_relative = "canonical_frames/t_frames_640x360.tar.gz"
    member_name = "frames_640x360/000000.png"
    archive_path = package / archive_relative
    archive_path.parent.mkdir(parents=True)
    with tarfile.open(archive_path, "w:gz") as archive:
        info = tarfile.TarInfo(member_name)
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    archive_hash = GEN.sha256_file(archive_path)
    row = _generation_row(
        archive_member_path=member_name,
        archive_path=archive_relative,
        archive_sha256=archive_hash,
        frame_640_sha256=GEN.sha256_bytes(payload),
        frame_size_bytes=len(payload),
    )
    inventory = {
        "archive_count": 1,
        "archives": [
            {
                "archive_path": archive_relative,
                "archive_sha256": archive_hash,
            }
        ],
        "member_count": 1,
        "schema_id": "synthetic",
        "schema_version": "1.0",
    }
    (package / "archive_inventory.json").write_bytes(GEN.json_bytes(inventory))
    return package, [row]


def _valid_result(*, accepted: bool = True):
    return SimpleNamespace(
        area_pixels=20 if accepted else None,
        bounding_box_xyxy=(1, 2, 3, 4) if accepted else None,
        candidate_blob_count=1 if accepted else 0,
        centroid_xy=(1.5, 2.5) if accepted else None,
        detected=accepted,
        rejection_reason=None if accepted else "no_threshold_match",
        status="detected" if accepted else "not_detected",
        threshold_match_pixels=20 if accepted else 0,
    )


def test_committed_import_row_schema_is_exact():
    assert all(set(row) == GEN.EMPIRICAL_FIELDS for row in _empirical_rows())


def test_committed_import_rows_have_exactly_eight_fields():
    assert all(len(row) == 8 for row in _empirical_rows())


def test_committed_empirical_row_count_is_1850():
    assert len(_empirical_rows()) == GEN.EXPECTED_INPUT_COUNT


def test_committed_diagnostic_row_count_is_1850():
    assert len(_diagnostic_rows()) == GEN.EXPECTED_INPUT_COUNT


def test_committed_primary_keys_are_unique():
    rows = _empirical_rows()
    keys = {(row["trajectory_id"], row["model_frame_idx"]) for row in rows}
    assert len(keys) == len(rows) == GEN.EXPECTED_INPUT_COUNT


def test_committed_c_empirical_key_sets_are_equal():
    c_keys = {(row["trajectory_id"], row["model_frame_idx"]) for row in _c_rows()}
    e_keys = {
        (row["trajectory_id"], row["model_frame_idx"]) for row in _empirical_rows()
    }
    assert c_keys == e_keys


def test_committed_diagnostic_empirical_key_sets_are_equal():
    e_keys = {
        (row["trajectory_id"], row["model_frame_idx"]) for row in _empirical_rows()
    }
    d_keys = {
        (row["trajectory_id"], row["model_frame_idx"]) for row in _diagnostic_rows()
    }
    assert e_keys == d_keys


def test_committed_context_values_and_json_types_are_exact():
    for row in _empirical_rows():
        assert type(row["resolution"]) is str
        assert row["resolution"] == GEN.EXPECTED_RESOLUTION
        assert type(row["coordinate_convention"]) is str
        assert (
            row["coordinate_convention"] == GEN.EXPECTED_COORDINATE_CONVENTION
        )


def test_committed_detector_version_is_exact():
    assert {
        row["detector_version"] for row in _empirical_rows()
    } == {GEN.DETECTOR_VERSION}


def test_committed_detector_identity_is_exact():
    assert {
        row["detector_identity_sha256"] for row in _diagnostic_rows()
    } == {GEN.DETECTOR_IDENTITY_SHA256}


def test_committed_accepted_rejected_accounting():
    diagnostics = _diagnostic_rows()
    accepted = sum(row["accepted"] for row in diagnostics)
    rejected = sum(not row["accepted"] for row in diagnostics)
    assert accepted + rejected == GEN.EXPECTED_INPUT_COUNT


def test_committed_empirical_values_are_booleans():
    assert all(
        type(row["empirical_magenta_visible"]) is bool
        for row in _empirical_rows()
    )


def test_committed_accepted_implies_empirical_true():
    assert all(
        not row["accepted"] or row["empirical_magenta_visible"]
        for row in _diagnostic_rows()
    )


def test_committed_rejection_implies_empirical_false():
    assert all(
        row["accepted"] or not row["empirical_magenta_visible"]
        for row in _diagnostic_rows()
    )


def test_committed_accepted_rejection_reason_is_null():
    assert all(
        not row["accepted"] or row["rejection_reason"] is None
        for row in _diagnostic_rows()
    )


def test_committed_rejected_rejection_reason_is_non_null():
    assert all(
        row["accepted"]
        or row["rejection_reason"] in {"no_threshold_match", "no_valid_blob"}
        for row in _diagnostic_rows()
    )


def test_committed_forbidden_final_geometry_quarantine_fields_are_absent():
    forbidden = {
        "geometric_visible",
        "visible_flag",
        "quarantined",
        "quarantine_category",
        "invalidity_reason",
    }
    assert all(not (set(row) & forbidden) for row in _empirical_rows())
    assert all(not (set(row) & forbidden) for row in _diagnostic_rows())


def test_committed_json_and_jsonl_are_deterministic():
    output = _committed_output()
    for path in output.iterdir():
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        assert raw.endswith(b"\n")
        if path.suffix == ".json":
            value = json.loads(raw.decode("utf-8"))
            assert raw == GEN.json_bytes(value)
        elif path.suffix == ".jsonl":
            rows = _jsonl(path)
            assert raw == b"".join(GEN.jsonl_line(row) for row in rows)


def test_committed_validation_only_passes_without_detector(monkeypatch):
    def forbidden_detector(*_args, **_kwargs):
        raise AssertionError("validation-only mode executed the detector")

    monkeypatch.setattr(GEN, "execute_frozen_detector", forbidden_detector)
    result = GEN.validate_output_package(
        _committed_output(),
        _c_rows(),
    )
    assert result["empirical_rows"] == GEN.EXPECTED_INPUT_COUNT
    assert result["diagnostic_rows"] == GEN.EXPECTED_INPUT_COUNT


def test_wrong_inventory_hash_fails_closed():
    with pytest.raises(GEN.FailClosed):
        GEN.validate_package_inventory(
            _person_c_package(),
            expected_inventory_sha256="0" * 64,
        )


def test_wrong_aggregate_hash_fails_closed():
    with pytest.raises(GEN.FailClosed):
        GEN.validate_package_inventory(
            _person_c_package(),
            expected_aggregate_sha256="0" * 64,
        )


def test_missing_archive_fails_closed(tmp_path):
    package, rows = _archive_fixture(tmp_path, _png())
    (package / rows[0]["archive_path"]).unlink()
    with pytest.raises(GEN.FailClosed):
        GEN.verify_archive_members(
            package,
            rows,
            decode=False,
            expected_archive_count=1,
            expected_member_count=1,
        )


def test_wrong_archive_hash_fails_closed(tmp_path):
    package, rows = _archive_fixture(tmp_path, _png())
    rows[0]["archive_sha256"] = "0" * 64
    with pytest.raises(GEN.FailClosed):
        GEN.verify_archive_members(
            package,
            rows,
            decode=False,
            expected_archive_count=1,
            expected_member_count=1,
        )


def test_missing_archive_member_fails_closed(tmp_path):
    package, rows = _archive_fixture(tmp_path, _png())
    rows[0]["archive_member_path"] = "frames_640x360/missing.png"
    with pytest.raises(GEN.FailClosed):
        GEN.verify_archive_members(
            package,
            rows,
            decode=False,
            expected_archive_count=1,
            expected_member_count=1,
        )


def test_wrong_member_hash_fails_closed(tmp_path):
    package, rows = _archive_fixture(tmp_path, _png())
    rows[0]["frame_640_sha256"] = "0" * 64
    with pytest.raises(GEN.FailClosed):
        GEN.verify_archive_members(
            package,
            rows,
            decode=False,
            expected_archive_count=1,
            expected_member_count=1,
        )


def test_wrong_member_size_fails_closed(tmp_path):
    package, rows = _archive_fixture(tmp_path, _png())
    rows[0]["frame_size_bytes"] += 1
    with pytest.raises(GEN.FailClosed):
        GEN.verify_archive_members(
            package,
            rows,
            decode=False,
            expected_archive_count=1,
            expected_member_count=1,
        )


def test_decode_failure_fails_closed(tmp_path):
    sys.path.insert(0, str(ROOT / "src"))
    from mineocclude.vision.calibration import decode_png_rgb_bytes

    package, rows = _archive_fixture(tmp_path, b"not a PNG")
    with pytest.raises(GEN.FailClosed):
        GEN.verify_archive_members(
            package,
            rows,
            decode=True,
            decoder=decode_png_rgb_bytes,
            expected_archive_count=1,
            expected_member_count=1,
        )


def test_wrong_dimensions_fail_closed(tmp_path):
    sys.path.insert(0, str(ROOT / "src"))
    from mineocclude.vision.calibration import decode_png_rgb_bytes

    package, rows = _archive_fixture(tmp_path, _png((100, 100)))
    with pytest.raises(GEN.FailClosed):
        GEN.verify_archive_members(
            package,
            rows,
            decode=True,
            decoder=decode_png_rgb_bytes,
            expected_archive_count=1,
            expected_member_count=1,
        )


def test_duplicate_identity_fails_closed():
    row = _generation_row()
    identity = _identity_row(row)
    with pytest.raises(GEN.FailClosed):
        GEN.validate_generation_rows(
            [row, dict(row)],
            [identity, dict(identity)],
            expected_count=2,
        )


def test_missing_identity_fails_closed():
    row = _generation_row()
    with pytest.raises(GEN.FailClosed):
        GEN.validate_generation_rows([row], [], expected_count=1)


def test_extra_identity_fails_closed():
    row = _generation_row()
    identity = _identity_row(row)
    extra = dict(identity, model_frame_idx=1)
    with pytest.raises(GEN.FailClosed):
        GEN.validate_generation_rows(
            [row],
            [identity, extra],
            expected_count=1,
        )


def test_wrong_layout_context_fails_closed():
    row = _generation_row(layout_id="layout_99")
    with pytest.raises(GEN.FailClosed):
        GEN.validate_generation_rows([row], [_identity_row(row)], expected_count=1)


def test_wrong_camera_context_fails_closed():
    row = _generation_row(
        canonical_camera_pose_id="layout_02_canonical_pose_v1"
    )
    with pytest.raises(GEN.FailClosed):
        GEN.validate_generation_rows([row], [_identity_row(row)], expected_count=1)


def test_wrong_resolution_fails_closed():
    row = _generation_row(resolution="384x224")
    with pytest.raises(GEN.FailClosed):
        GEN.validate_generation_rows([row], [_identity_row(row)], expected_count=1)


def test_wrong_coordinate_convention_fails_closed():
    row = _generation_row(coordinate_convention="top_left_origin")
    with pytest.raises(GEN.FailClosed):
        GEN.validate_generation_rows([row], [_identity_row(row)], expected_count=1)


def test_wrong_detector_version_fails_closed():
    generation, empirical, diagnostic = _handoff_rows()
    empirical["detector_version"] = "wrong"
    with pytest.raises(GEN.FailClosed):
        GEN.validate_empirical_records(
            [empirical],
            [diagnostic],
            [generation],
            expected_count=1,
        )


def test_wrong_detector_identity_fails_closed():
    generation, empirical, diagnostic = _handoff_rows()
    diagnostic["detector_identity_sha256"] = "0" * 64
    with pytest.raises(GEN.FailClosed):
        GEN.validate_empirical_records(
            [empirical],
            [diagnostic],
            [generation],
            expected_count=1,
        )


def test_malformed_detector_result_fails_closed():
    with pytest.raises(GEN.FailClosed):
        GEN.validate_detector_result(SimpleNamespace(detected=True))


def test_detector_exception_fails_closed():
    def failing_detector(_rgb, _arguments):
        raise RuntimeError("synthetic detector failure")

    with pytest.raises(GEN.FailClosed):
        GEN.call_detector_fail_closed(failing_detector, [], {})


def test_attempt_to_write_visible_flag_fails_closed():
    generation, empirical, diagnostic = _handoff_rows()
    empirical["visible_flag"] = True
    with pytest.raises(GEN.FailClosed):
        GEN.validate_empirical_records(
            [empirical],
            [diagnostic],
            [generation],
            expected_count=1,
        )


def test_u4_path_is_rejected(tmp_path):
    with pytest.raises(GEN.FailClosed):
        GEN.reject_u4_path(tmp_path / "u4-pushed-results")


def test_valid_accepted_detector_result_passes():
    assert GEN.validate_detector_result(_valid_result(accepted=True)) is True


def test_valid_rejected_detector_result_passes():
    assert GEN.validate_detector_result(_valid_result(accepted=False)) is False


def test_committed_production_run_ordinal_and_count_remain_one():
    receipt = json.loads(
        (_committed_output() / "production_run_receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert receipt["formal_production_ordinal"] == 1
    assert receipt["formal_production_run_count"] == 1
    assert receipt["second_production_pass_occurred"] is False


def test_committed_package_has_no_accuracy_metrics():
    output = _committed_output()
    for path in output.iterdir():
        if path.suffix == ".json":
            GEN.assert_no_accuracy_fields(
                json.loads(path.read_text(encoding="utf-8")),
                location=path.name,
            )
        elif path.suffix == ".jsonl":
            for index, row in enumerate(_jsonl(path)):
                GEN.assert_no_accuracy_fields(
                    row,
                    location=f"{path.name}[{index}]",
                )
