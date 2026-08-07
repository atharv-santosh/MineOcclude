#!/usr/bin/env python3
"""Deliverable 4: final visibility interface + strict join contract (C -> E Phase 3).

Publishes the owner-authored interface combining C geometry with E's later
empirical detector records. C owns final visible_flag. Enforcement lives in
mineocclude.data.visibility_join.strict_join. Deterministic JSON.
"""
from __future__ import annotations
import hashlib
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys
sys.path.insert(0, os.path.join(ROOT, "src"))
import mineocclude.contracts  # noqa: F401,E402
from mineocclude.data.visibility_join import (  # noqa: E402
    CONTEXT_KEYS, FINAL_VISIBILITY_INTERFACE_VERSION, PRIMARY_KEY)
from mineocclude.data.visibility import (  # noqa: E402
    GEOMETRY_RULE_VERSION, QUARANTINE_GEO_HIDDEN_DET_VISIBLE,
    QUARANTINE_GEO_VISIBLE_DET_HIDDEN, QUARANTINE_INVALID_GEOMETRY,
    QUARANTINE_MISSING_DETECTOR, QUARANTINE_NONE)

OUT = os.path.join(ROOT, "data/handoff_e/phase3_visibility_interface_v0_1")
SCHEMA_VERSION = "1.0"
PKG = "person-c-phase3-visibility-interface-v0_1"
DETECTOR_VERSION = ("hsv-largest-valid-blob-v1.0-candidate:sha256:"
                    "0cadf618fca1578196bde4982021c38627ccb9c39e46353812e7da3fce6aa125")
SOURCE_REVISION = "fa70424530f422a2e6140e0e90d0ff18f583141e"


def canon(o): return (json.dumps(o, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def build_all():
    interface = {
        "schema_version": SCHEMA_VERSION, "package_id": PKG, "owner": "Person C",
        "final_visibility_interface_version": FINAL_VISIBILITY_INTERFACE_VERSION,
        "rule": "visible_flag = geometric_visible AND empirical_magenta_visible",
        "final_label_owner": "Person C",
        "person_e_may_write_visible_flag": False,
        "authoritative_primary_key": list(PRIMARY_KEY),
        "primary_key_is_complete": True,
        "primary_key_confirmation": (
            "(trajectory_id, model_frame_idx) remains the complete authoritative primary "
            "key for the join; it uniquely identifies a model frame within the dataset."),
        "context_identities_must_match": list(CONTEXT_KEYS),
        "separately_preserved_fields": [
            "geometric_visible", "empirical_magenta_visible", "visible_flag",
            "quarantine_category", "quarantined", "invalidity_reason",
            "detector_version", "geometry_rule_version"],
        "geometry_rule_version": GEOMETRY_RULE_VERSION,
        "enforcement_module": "mineocclude.data.visibility_join.strict_join",
    }

    import_contract = {
        "schema_version": SCHEMA_VERSION, "package_id": PKG, "owner": "Person C",
        "empirical_source": "Person E frozen detector",
        "required_detector_version": DETECTOR_VERSION,
        "join_primary_key": list(PRIMARY_KEY),
        "required_e_record_fields": list(PRIMARY_KEY) + [
            "empirical_magenta_visible", "detector_version"] + list(CONTEXT_KEYS),
        "e_forbidden_fields": ["visible_flag"],
        "e_may_supply_only": "empirical_magenta_visible + identity + context",
        "fail_closed_categories": [
            "incomplete_c_input", "incomplete_e_input", "e_cannot_write_visible_flag",
            "wrong_detector_version", "duplicate_c_record", "duplicate_e_record",
            "extra_unmatched_e_record", "missing_e_record", "context_identity_mismatch"],
        "context_mismatch_covers": [
            "wrong_layout", "wrong_camera_pose", "wrong_resolution",
            "wrong_coordinate_convention"],
        "e_fail_closed_condition_coverage": {
            "missing_e_records": "missing_e_record",
            "duplicate_e_records": "duplicate_e_record",
            "duplicate_c_records": "duplicate_c_record",
            "conflicting_identities": "context_identity_mismatch (+ duplicate_c/e_record)",
            "unmatched_c_records": "missing_e_record",
            "extra_e_records_no_c_frame": "extra_unmatched_e_record",
            "wrong_detector_version": "wrong_detector_version",
            "wrong_layout": "context_identity_mismatch",
            "wrong_camera_pose": "context_identity_mismatch",
            "wrong_resolution": "context_identity_mismatch",
            "wrong_coordinate_convention": "context_identity_mismatch",
            "incomplete_package_input": "incomplete_c_input / incomplete_e_input"},
        "no_mismatch_may_silently_become_visible": True,
    }

    disagreement_schema = {
        "schema_version": SCHEMA_VERSION, "package_id": PKG, "owner": "Person C",
        "quarantine_categories": {
            QUARANTINE_NONE: "channels agree (or both hidden); not quarantined",
            QUARANTINE_GEO_VISIBLE_DET_HIDDEN:
                "geometry says visible, detector says hidden -> quarantined, visible_flag=False",
            QUARANTINE_GEO_HIDDEN_DET_VISIBLE:
                "geometry says hidden, detector says visible -> quarantined, visible_flag=False",
            QUARANTINE_INVALID_GEOMETRY:
                "geometric_visible is null/invalid -> quarantined, visible_flag=False",
            QUARANTINE_MISSING_DETECTOR:
                "empirical value present-but-null -> quarantined, visible_flag=False"},
        "quarantine_never_flips_a_raw_channel": True,
        "disagreements_are_retained_not_dropped": True,
    }

    files = {}
    files["final_visibility_interface.json"] = canon(interface)
    files["empirical_visibility_import_contract.json"] = canon(import_contract)
    files["visibility_disagreement_schema.json"] = canon(disagreement_schema)
    files["visibility_join_validation_receipt.json"] = canon({
        "schema_version": SCHEMA_VERSION, "package_id": PKG, "owner": "Person C",
        "source_revision": SOURCE_REVISION,
        "final_visibility_interface_version": FINAL_VISIBILITY_INTERFACE_VERSION,
        "enforcement_module": "mineocclude.data.visibility_join",
        "authoritative_primary_key": list(PRIMARY_KEY),
        "primary_key_is_complete": True,
        "tests": "tests/handoff/test_phase3_visibility_interface.py",
        "file_sha256": {n: hashlib.sha256(b).hexdigest() for n, b in sorted(files.items())}})
    return files


def write_all(dest: str = OUT):
    os.makedirs(dest, exist_ok=True)
    for n, b in sorted(build_all().items()):
        with open(os.path.join(dest, n), "wb") as f:
            f.write(b)
    return sorted(build_all().keys())


if __name__ == "__main__":
    for n in write_all():
        print("wrote", n)
