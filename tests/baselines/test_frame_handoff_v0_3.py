"""Unit tests for Person A's 66-cell frame-handoff verifier (Person D).

``frame_handoff_v0_3`` is the fail-closed hash-chain verifier behind the
actual real ``raw_pixel`` evidence published for the 66-cell production
run, but unlike every other Person D module it had no dedicated unit
test file -- only indirect, whole-package coverage from the one real
production run (which never exercises a single mismatch/tamper branch,
since real upstream data always matches by construction). These tests
exercise the fail-closed branches directly with small synthetic
fixtures.
"""

from __future__ import annotations

import hashlib

from mineocclude.baselines import frame_handoff_v0_3 as fh3

VALID_HASH = "a" * 64


def _valid_record(trajectory_id: str = "t1", model_frame_idx: int = 0) -> dict:
    return {
        "artifact_id": f"{trajectory_id}:{model_frame_idx}",
        "payload_sha256": VALID_HASH,
        "payload_byte_size": fh3.REQUIRED_PAYLOAD_BYTE_SIZE,
        "trajectory_id": trajectory_id,
        "model_frame_idx": model_frame_idx,
        "global_frame_identity": f"{trajectory_id}:{model_frame_idx}",
        "dtype": fh3.REQUIRED_PAYLOAD_DTYPE,
        "payload_format": fh3.REQUIRED_PAYLOAD_FORMAT,
        "shape": list(fh3.REQUIRED_PAYLOAD_SHAPE),
        "preprocess_hash": fh3.PERSON_A_PREPROCESS_HASH,
        "preprocessing_identity": fh3.PERSON_A_PREPROCESSING_IDENTITY,
        "canonicalization_implementation_sha256": fh3.PERSON_C_CANONICALIZER_SHA256,
        "source_canonical_width": fh3.PERSON_C_CANONICAL_WIDTH,
        "source_canonical_height": fh3.PERSON_C_CANONICAL_HEIGHT,
        "source_channel_order": fh3.PERSON_C_CANONICAL_CHANNEL_ORDER,
        "source_canonical_png_sha256": "b" * 64,
        "source_canonical_pixel_sha256": "c" * 64,
        "source_raw_sha256": "d" * 64,
        "output_path": fh3.PERSON_A_FILENAME_RULE.format(
            trajectory_id=trajectory_id, model_frame_idx=model_frame_idx
        ),
    }


def _valid_summary_manifest(records: list | None = None) -> dict:
    return {
        "schema_id": fh3.PERSON_A_FRAME_MANIFEST_SCHEMA_ID,
        "artifact_count": fh3.REQUIRED_FRAME_ARTIFACT_COUNT,
        "unique_frame_count": fh3.REQUIRED_FRAME_ARTIFACT_COUNT,
        "trajectory_count": fh3.REQUIRED_TRAJECTORY_COUNT,
        "duplicate_frame_count": 0,
        "missing_frame_count": 0,
        "failure_count": 0,
        "payload_byte_total": fh3.REQUIRED_PAYLOAD_BYTE_TOTAL,
        "mp4_used_as_pixel_source": False,
        "join_key": ["trajectory_id", "model_frame_idx"],
        "output_contract": {
            "dtype": fh3.REQUIRED_PAYLOAD_DTYPE,
            "layout": fh3.REQUIRED_PAYLOAD_LAYOUT,
            "color_order": fh3.REQUIRED_PAYLOAD_COLOR_ORDER,
            "payload_format": fh3.REQUIRED_PAYLOAD_FORMAT,
            "shape": list(fh3.REQUIRED_PAYLOAD_SHAPE),
            "payload_byte_size": fh3.REQUIRED_PAYLOAD_BYTE_SIZE,
            "value_range_inclusive": list(fh3.REQUIRED_PAYLOAD_VALUE_RANGE),
        },
        "person_a_preprocessing": {
            "preprocess_hash": fh3.PERSON_A_PREPROCESS_HASH,
            "implementation_sha256": fh3.PERSON_A_PREPROCESSING_IMPLEMENTATION_SHA256,
            "interpolation": fh3.PERSON_A_INTERPOLATION,
            "normalization": fh3.PERSON_A_NORMALIZATION,
            "colour_conversion": fh3.PERSON_A_COLOUR_CONVERSION,
            "scaling": fh3.PERSON_A_SCALING,
        },
        "person_c_canonical_media": {
            "commit": fh3.PERSON_C_66_CELL_COMMIT,
            "canonicalizer_sha256": fh3.PERSON_C_CANONICALIZER_SHA256,
            "canonical_dimensions": (
                f"{fh3.PERSON_C_CANONICAL_WIDTH}x{fh3.PERSON_C_CANONICAL_HEIGHT}"
            ),
        },
        "records": records if records is not None else [],
    }


# --------------------------------------------------------------------------
# sha256_of_file / verify_artifact_raw_bytes
# --------------------------------------------------------------------------


def test_sha256_of_file_matches_hashlib(tmp_path):
    path = tmp_path / "artifact.bin"
    path.write_bytes(b"real evidence bytes")
    assert fh3.sha256_of_file(path) == hashlib.sha256(b"real evidence bytes").hexdigest()


def test_verify_artifact_raw_bytes_reports_missing_file(tmp_path):
    errors = fh3.verify_artifact_raw_bytes(tmp_path / "missing.json", VALID_HASH)
    assert errors == ("artifact_file_not_found",)


def test_verify_artifact_raw_bytes_reports_hash_mismatch(tmp_path):
    path = tmp_path / "artifact.json"
    path.write_bytes(b"{}")
    errors = fh3.verify_artifact_raw_bytes(path, VALID_HASH)
    assert len(errors) == 1
    assert errors[0].startswith(f"raw_sha256_mismatch:expected={VALID_HASH}:actual=")


def test_verify_artifact_raw_bytes_passes_on_a_real_match(tmp_path):
    path = tmp_path / "artifact.json"
    path.write_bytes(b"{}")
    expected = hashlib.sha256(b"{}").hexdigest()
    assert fh3.verify_artifact_raw_bytes(path, expected) == ()


# --------------------------------------------------------------------------
# verify_frame_manifest_summary_counts
# --------------------------------------------------------------------------


def test_summary_counts_rejects_a_non_mapping():
    assert fh3.verify_frame_manifest_summary_counts([]) == ("manifest_not_mapping",)


def test_summary_counts_passes_on_a_well_formed_manifest():
    records = [_valid_record(f"t{i}", 0) for i in range(fh3.REQUIRED_FRAME_ARTIFACT_COUNT)]
    manifest = _valid_summary_manifest(records)
    assert fh3.verify_frame_manifest_summary_counts(manifest) == ()


def test_summary_counts_flags_schema_id_mismatch():
    manifest = _valid_summary_manifest()
    manifest["schema_id"] = "wrong-schema"
    errors = fh3.verify_frame_manifest_summary_counts(manifest)
    assert "schema_id_mismatch" in errors


def test_summary_counts_flags_mp4_used_as_pixel_source():
    manifest = _valid_summary_manifest()
    manifest["mp4_used_as_pixel_source"] = True
    errors = fh3.verify_frame_manifest_summary_counts(manifest)
    assert "mp4_used_as_pixel_source" in errors


def test_summary_counts_flags_missing_output_contract():
    manifest = _valid_summary_manifest()
    del manifest["output_contract"]
    errors = fh3.verify_frame_manifest_summary_counts(manifest)
    assert "output_contract_missing" in errors


def test_summary_counts_flags_output_contract_shape_mismatch():
    manifest = _valid_summary_manifest()
    manifest["output_contract"]["shape"] = [1, 1, 1]
    errors = fh3.verify_frame_manifest_summary_counts(manifest)
    assert "output_contract_shape_mismatch" in errors


def test_summary_counts_flags_missing_preprocessing_block():
    manifest = _valid_summary_manifest()
    del manifest["person_a_preprocessing"]
    errors = fh3.verify_frame_manifest_summary_counts(manifest)
    assert "person_a_preprocessing_missing" in errors


def test_summary_counts_flags_preprocess_hash_mismatch():
    manifest = _valid_summary_manifest()
    manifest["person_a_preprocessing"]["preprocess_hash"] = "tampered"
    errors = fh3.verify_frame_manifest_summary_counts(manifest)
    assert "preprocess_hash_mismatch" in errors


def test_summary_counts_flags_missing_canonical_media_block():
    manifest = _valid_summary_manifest()
    del manifest["person_c_canonical_media"]
    errors = fh3.verify_frame_manifest_summary_counts(manifest)
    assert "person_c_canonical_media_missing" in errors


def test_summary_counts_flags_canonical_commit_mismatch():
    manifest = _valid_summary_manifest()
    manifest["person_c_canonical_media"]["commit"] = "0" * 40
    errors = fh3.verify_frame_manifest_summary_counts(manifest)
    assert "person_c_commit_mismatch" in errors


def test_summary_counts_flags_records_count_mismatch():
    manifest = _valid_summary_manifest(records=[_valid_record()])
    errors = fh3.verify_frame_manifest_summary_counts(manifest)
    assert "records_count_mismatch" in errors


# --------------------------------------------------------------------------
# verify_frame_manifest_records
# --------------------------------------------------------------------------


def test_records_rejects_a_manifest_without_a_records_list():
    assert fh3.verify_frame_manifest_records({"records": "not-a-list"}) == ("records_not_a_list",)


def test_records_accepts_a_single_well_formed_record():
    manifest = {"records": [_valid_record()]}
    assert fh3.verify_frame_manifest_records(manifest) == ()


def test_records_flags_invalid_payload_sha256():
    record = _valid_record()
    record["payload_sha256"] = "not-a-hash"
    errors = fh3.verify_frame_manifest_records({"records": [record]})
    assert "record[0]:invalid_payload_sha256" in errors


def test_records_flags_duplicate_artifact_id():
    record_a = _valid_record("t1", 0)
    record_b = _valid_record("t1", 1)
    record_b["artifact_id"] = record_a["artifact_id"]
    errors = fh3.verify_frame_manifest_records({"records": [record_a, record_b]})
    assert "record[1]:duplicate_artifact_id" in errors


def test_records_flags_duplicate_frame_identity():
    record_a = _valid_record("t1", 0)
    record_b = _valid_record("t1", 0)
    record_b["artifact_id"] = "distinct-artifact-id"
    errors = fh3.verify_frame_manifest_records({"records": [record_a, record_b]})
    assert "record[1]:duplicate_frame_identity" in errors


def test_records_rejects_a_bool_model_frame_idx():
    record = _valid_record()
    record["model_frame_idx"] = True
    errors = fh3.verify_frame_manifest_records({"records": [record]})
    assert "record[0]:invalid_model_frame_idx" in errors


def test_records_flags_global_frame_identity_mismatch():
    record = _valid_record()
    record["global_frame_identity"] = "wrong:identity"
    errors = fh3.verify_frame_manifest_records({"records": [record]})
    assert "record[0]:global_frame_identity_mismatch" in errors


def test_records_flags_output_path_rule_mismatch():
    record = _valid_record()
    record["output_path"] = "wrong/path.f32le"
    errors = fh3.verify_frame_manifest_records({"records": [record]})
    assert "record[0]:output_path_rule_mismatch" in errors


def test_records_flags_an_invalid_source_hash_chain_field():
    record = _valid_record()
    record["source_raw_sha256"] = "short"
    errors = fh3.verify_frame_manifest_records({"records": [record]})
    assert "record[0]:invalid_source_raw_sha256" in errors


def test_records_reports_missing_and_extra_frame_keys_against_the_row_universe():
    record = _valid_record("t1", 0)
    manifest = {"records": [record]}
    errors = fh3.verify_frame_manifest_records(
        manifest, expected_frame_keys=[("t1", 0), ("t2", 0)]
    )
    joined = " ".join(errors)
    assert "frame_keys_missing_from_manifest:1" in joined
    assert "('t2', 0)" in joined


def test_records_reports_a_manifest_frame_key_absent_from_the_row_universe():
    record = _valid_record("t1", 0)
    manifest = {"records": [record]}
    errors = fh3.verify_frame_manifest_records(manifest, expected_frame_keys=[])
    joined = " ".join(errors)
    assert "frame_keys_not_in_row_universe:1" in joined


# --------------------------------------------------------------------------
# verify_frame_payloads_on_disk
# --------------------------------------------------------------------------


def test_payloads_on_disk_rejects_a_manifest_without_a_records_list():
    result = fh3.verify_frame_payloads_on_disk({"records": None}, frame_root="/tmp")
    assert result.errors == ("records_not_a_list",)
    assert result.missing_frame_count == fh3.REQUIRED_FRAME_ARTIFACT_COUNT
    assert result.all_clear is False


def test_payloads_on_disk_verifies_a_real_matching_file(tmp_path):
    payload = b"\x00" * fh3.REQUIRED_PAYLOAD_BYTE_SIZE
    (tmp_path / "frames" / "t1").mkdir(parents=True)
    (tmp_path / "frames" / "t1" / "000000.f32le").write_bytes(payload)

    record = _valid_record("t1", 0)
    record["payload_sha256"] = hashlib.sha256(payload).hexdigest()
    result = fh3.verify_frame_payloads_on_disk({"records": [record]}, frame_root=tmp_path)

    assert result.verified_frame_count == 1
    assert result.missing_frame_count == 0
    assert result.hash_mismatch_count == 0
    assert result.size_mismatch_count == 0
    assert result.actual_frame_count == 1
    # expected_frame_count is always the full-manifest constant, independent
    # of how many rows this particular call verified.
    assert result.expected_frame_count == fh3.REQUIRED_FRAME_ARTIFACT_COUNT
    assert result.all_clear is False  # actual (1) != expected (2468)


def test_payloads_on_disk_reports_a_missing_file(tmp_path):
    record = _valid_record("t1", 0)
    result = fh3.verify_frame_payloads_on_disk({"records": [record]}, frame_root=tmp_path)
    assert result.missing_frame_count == 1
    assert any("file_missing" in error for error in result.errors)


def test_payloads_on_disk_reports_a_hash_mismatch(tmp_path):
    payload = b"\x00" * fh3.REQUIRED_PAYLOAD_BYTE_SIZE
    (tmp_path / "frames" / "t1").mkdir(parents=True)
    (tmp_path / "frames" / "t1" / "000000.f32le").write_bytes(payload)

    record = _valid_record("t1", 0)
    record["payload_sha256"] = VALID_HASH  # deliberately wrong
    result = fh3.verify_frame_payloads_on_disk({"records": [record]}, frame_root=tmp_path)
    assert result.hash_mismatch_count == 1
    assert any("hash_mismatch" in error for error in result.errors)


def test_payloads_on_disk_skips_keys_outside_only_frame_keys(tmp_path):
    record_wanted = _valid_record("t1", 0)
    record_unwanted = _valid_record("t2", 0)
    result = fh3.verify_frame_payloads_on_disk(
        {"records": [record_wanted, record_unwanted]},
        frame_root=tmp_path,
        only_frame_keys=[("t1", 0)],
    )
    # Neither file exists on disk, but only the wanted key is even attempted.
    assert result.verified_frame_count == 0
    assert result.missing_frame_count == 1
    assert result.actual_frame_count == 2


def test_payloads_on_disk_counts_duplicate_payload_identities(tmp_path):
    record_a = _valid_record("t1", 0)
    record_b = _valid_record("t1", 0)
    result = fh3.verify_frame_payloads_on_disk(
        {"records": [record_a, record_b]}, frame_root=tmp_path
    )
    assert result.duplicate_frame_count == 1
    assert any("duplicate_payload_identity" in error for error in result.errors)


# --------------------------------------------------------------------------
# build_pixel_input_contract
# --------------------------------------------------------------------------


def test_build_pixel_input_contract_names_raw_pixel_as_the_sole_pixel_consumer():
    contract = fh3.build_pixel_input_contract()
    assert contract["families_consuming_pixels"] == ["raw_pixel"]
    assert "raw_pixel" not in contract["families_consuming_no_pixels"]
    assert len(contract["families_consuming_no_pixels"]) == 7
    assert contract["raw_pixel_input_authority"]["commit"] == fh3.PERSON_A_66_CELL_COMMIT
    assert len(contract["source_hash_chain"]) == 3
