"""Final visibility interface: strict one-to-one join of C geometry with E's
empirical detector records (Person C owns final ``visible_flag``).

Authoritative rule (unchanged):

    visible_flag = geometric_visible AND empirical_magenta_visible

C is the sole owner of ``visible_flag``. Person E supplies only
``empirical_magenta_visible`` (plus identity + context); E may not write or
overwrite the final label. The join is fail-closed: any structural or context
mismatch raises :class:`VisibilityJoinError` and no row silently becomes
visible. Value disagreements between the two valid channels are QUARANTINED
(retained with a category), never flipped.

Authoritative primary key: ``(trajectory_id, model_frame_idx)``.
"""
from __future__ import annotations

from .visibility import (
    QUARANTINE_GEO_HIDDEN_DET_VISIBLE,
    QUARANTINE_GEO_VISIBLE_DET_HIDDEN,
    QUARANTINE_INVALID_GEOMETRY,
    QUARANTINE_MISSING_DETECTOR,
    QUARANTINE_NONE,
)

FINAL_VISIBILITY_INTERFACE_VERSION = "person-c-final-visibility-interface-v1.0"
PRIMARY_KEY = ("trajectory_id", "model_frame_idx")

# Context identities that must match between the C frame and the E record.
CONTEXT_KEYS = (
    "layout_id",
    "canonical_camera_pose_id",
    "resolution",
    "coordinate_convention",
)

_C_REQUIRED = PRIMARY_KEY + ("geometric_visible",) + CONTEXT_KEYS
_E_REQUIRED = PRIMARY_KEY + ("empirical_magenta_visible", "detector_version") + CONTEXT_KEYS


class VisibilityJoinError(Exception):
    """Raised fail-closed on any structural or context mismatch."""

    def __init__(self, category: str, message: str):
        super().__init__(f"[{category}] {message}")
        self.category = category
        self.message = message


def _key(rec: dict) -> tuple:
    return (rec["trajectory_id"], rec["model_frame_idx"])


def strict_join(
    c_records: list[dict],
    e_records: list[dict],
    *,
    expected_detector_version: str,
) -> list[dict]:
    """Join C geometry with E empirical records into final visibility rows.

    Fails closed (raises :class:`VisibilityJoinError`) on: incomplete input,
    E attempting to write ``visible_flag``, wrong detector version, duplicate C
    rows, duplicate E rows, unmatched C rows (missing E record), extra E rows
    with no C frame, and any context identity mismatch (layout / pose /
    resolution / coordinate convention). Value disagreements are quarantined.
    """
    # ---- completeness of inputs ------------------------------------------
    for rec in c_records:
        missing = [k for k in _C_REQUIRED if k not in rec]
        if missing:
            raise VisibilityJoinError("incomplete_c_input",
                                      f"C record {rec.get('trajectory_id')} missing {missing}")
    for rec in e_records:
        # E must NOT supply the final label — C owns it.
        if "visible_flag" in rec:
            raise VisibilityJoinError("e_cannot_write_visible_flag",
                                      f"E record {_key(rec)} illegally contains visible_flag")
        missing = [k for k in _E_REQUIRED if k not in rec]
        if missing:
            raise VisibilityJoinError("incomplete_e_input",
                                      f"E record {rec.get('trajectory_id')} missing {missing}")
        if rec["detector_version"] != expected_detector_version:
            raise VisibilityJoinError("wrong_detector_version",
                                      f"E record {_key(rec)} detector_version "
                                      f"{rec['detector_version']!r} != {expected_detector_version!r}")

    # ---- duplicate detection (both sides) --------------------------------
    c_index: dict[tuple, dict] = {}
    for rec in c_records:
        k = _key(rec)
        if k in c_index:
            raise VisibilityJoinError("duplicate_c_record", f"duplicate C key {k}")
        c_index[k] = rec
    e_index: dict[tuple, dict] = {}
    for rec in e_records:
        k = _key(rec)
        if k in e_index:
            raise VisibilityJoinError("duplicate_e_record", f"duplicate E key {k}")
        e_index[k] = rec

    # ---- extra E rows that match no C frame ------------------------------
    extra = sorted(set(e_index) - set(c_index))
    if extra:
        raise VisibilityJoinError("extra_unmatched_e_record",
                                  f"E rows with no C frame: {extra}")
    # ---- unmatched C rows (missing E record) -----------------------------
    unmatched = sorted(set(c_index) - set(e_index))
    if unmatched:
        raise VisibilityJoinError("missing_e_record",
                                  f"C frames without an E record: {unmatched}")

    # ---- one-to-one join + context match + AND rule ----------------------
    out: list[dict] = []
    for k in sorted(c_index):
        c, e = c_index[k], e_index[k]
        for ck in CONTEXT_KEYS:
            if c[ck] != e[ck]:
                raise VisibilityJoinError(
                    "context_identity_mismatch",
                    f"{ck} mismatch at {k}: C={c[ck]!r} E={e[ck]!r}")
        geo = c["geometric_visible"]
        emp = e["empirical_magenta_visible"]
        # quarantine categories (value disagreements / invalid inputs) — never flip
        if geo is None:
            category, flag = QUARANTINE_INVALID_GEOMETRY, False
        elif emp is None:
            category, flag = QUARANTINE_MISSING_DETECTOR, False
        else:
            geo_b, emp_b = bool(geo), bool(emp)
            if geo_b and not emp_b:
                category = QUARANTINE_GEO_VISIBLE_DET_HIDDEN
            elif emp_b and not geo_b:
                category = QUARANTINE_GEO_HIDDEN_DET_VISIBLE
            else:
                category = QUARANTINE_NONE
            flag = geo_b and emp_b
        out.append({
            "trajectory_id": k[0],
            "model_frame_idx": k[1],
            "layout_id": c["layout_id"],
            "canonical_camera_pose_id": c["canonical_camera_pose_id"],
            # raw channels retained separately, untouched
            "geometric_visible": geo,
            "empirical_magenta_visible": emp,
            # C-owned final label
            "visible_flag": flag,
            "quarantine_category": category,
            "quarantined": category != QUARANTINE_NONE,
            "invalidity_reason": (category if category in (
                QUARANTINE_INVALID_GEOMETRY, QUARANTINE_MISSING_DETECTOR) else None),
            "detector_version": e["detector_version"],
            "geometry_rule_version": c.get("geometry_rule_version"),
            "final_visibility_interface_version": FINAL_VISIBILITY_INTERFACE_VERSION,
            "label_owner": "Person C",
        })
    return out
