#!/usr/bin/env python3
"""Deterministic no-collection acceptance harness for the v0.2 package."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.prospective.development_workflow import (  # noqa: E402
    EvidenceError, Stage1Evaluator, derive_projection_validity,
)


#: Package version this harness accepts. Rebound -- once, before ``main`` -- by
#: the sibling v0.3 entrypoint.
VERSION_TAG = "v0.2"

ALLOWED_NUMERIC_CLASSES = {
    "FROZEN_EVIDENCE_DERIVED", "PROSPECTIVE_STAGE1_MEASURED", "PURE_IMPLEMENTATION_CONSTANT"
}
ALLOWED_CONTINUITY = {
    "INCORPORATED", "SUPERSEDED_WITH_JUSTIFICATION", "DEFERRED_EXPLICITLY",
    "NOT_AUTHORITY_RELEVANT",
}

#: Per-version classified-table audits: every row of the named document must
#: carry exactly one disposition from the allowed set. The two packages document
#: different things -- v0.2 traces numerics forward from the superseded run,
#: v0.3 derives a new target extent -- so each version enumerates its own
#: documents rather than one version's tables being asserted against the other's.
DOCUMENT_TABLE_AUDITS = {
    "v0.2": (("NUMERIC_TRACEABILITY.md", ALLOWED_NUMERIC_CLASSES, 1),
             ("FORENSIC_CONTINUITY_MATRIX.md", ALLOWED_CONTINUITY, 15)),
    "v0.3": (),
    "v0.4": (),
}

#: Documents each package must carry, and the execution surface each accepts.
REQUIRED_DOCUMENTS = {
    "v0.2": ("PROSPECTIVE_DEVELOPMENT_AUTHORITY.md", "NUMERIC_TRACEABILITY.md",
             "FORENSIC_CONTINUITY_MATRIX.md"),
    "v0.3": ("PROSPECTIVE_DEVELOPMENT_AUTHORITY.md", "SAMPLE_FLOOR_ANALYSIS.md",
             "TARGET_EXTENT_DERIVATION.md"),
    # v0.4 inherits v0.3's science verbatim, so it carries the same two derivation
    # documents unchanged alongside its own authority narrative.
    "v0.4": ("PROSPECTIVE_DEVELOPMENT_AUTHORITY.md", "SAMPLE_FLOOR_ANALYSIS.md",
             "TARGET_EXTENT_DERIVATION.md"),
}
SUITES = {
    "v0.2": ("tests/prospective/test_development_authority_v0_2_repair.py",
             # D-A4 closure evidence: the artefact the real builder writes, not
             # just a hand-built document, must reach a PASS through the frozen
             # evaluator.
             "tests/prospective/test_stage1_evidence_builder_end_to_end.py",
             # A4/A6 closure evidence: probe-execution provenance, cross-stage
             # binding, and the two receipt generators, each attacked directly.
             "tests/prospective/test_provenance_authorization_and_stage_binding.py"),
    "v0.3": ("tests/prospective/test_extent_geometry_v0_3.py",
             # The execution-closure evidence: that the v0.3 entrypoints exist,
             # resolve the v0.3 inventory, and refuse every v0.2 substitution.
             "tests/prospective/test_v0_3_execution_entrypoints.py"),
    "v0.4": (# The builder synchronization this package exists to carry: the real
             # builder driven end to end under an extent authority, the
             # version-aware decision identity, and the audit proving the
             # scientific rules did not move.
             "tests/prospective/test_stage1_evidence_builder_v0_3_end_to_end.py",
             "tests/prospective/test_stage1_decision_artifact_id_version_binding.py",
             "tests/prospective/test_v0_3_scientific_non_change_audit.py",
             # That the v0.4 entrypoints exist, resolve the a1y_*/85xxx
             # inventory, and refuse every closed predecessor substitution.
             "tests/prospective/test_v0_4_package_binding.py",
             # The Stage-2 terminal chain this package now carries: the promoted
             # decision rules proved equal to the implementation, the evidence
             # builder and independent evaluator driven to PASS/FAIL/BLOCKED over
             # fixtures, byte-identical decision reproduction under mutation, and
             # the two rehearsal defects -- an activation receipt that bound no
             # checkpoint, and target rows that were inferred rather than proved.
             "tests/prospective/test_stage2_terminal_authority.py",
             # The final operational and terminal verification closure: the
             # terminal's independent re-derivation of fold discipline, bootstrap
             # configuration, self-grade agreement and activation metadata, and
             # the production wiring of the unit-1 checkpoint, the per-unit
             # structural probe, durable capture receipts and the explicit
             # historical/current-source evaluation modes.
             "tests/prospective/test_stage2_fold_and_terminal_verification.py",
             "tests/prospective/test_stage2_operational_closure.py"),
}
ENTRYPOINT_DIRECTORY = {"v0.2": "scripts/regime_a_prime_qualification_v0_2",
                        "v0.3": "scripts/regime_a_prime_qualification_v0_3",
                        "v0.4": "scripts/regime_a_prime_qualification_v0_4"}


def package() -> Path:
    from mineocclude.prospective.package_binding import package_directory

    return package_directory(VERSION_TAG, ROOT)


def run(*command: str) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def load(name: str) -> dict:
    value = json.loads((package() / name).read_text())
    assert isinstance(value, dict)
    return value


def audit_documents() -> None:
    from mineocclude.prospective.development_workflow import superseded_half_extent_present
    from mineocclude.prospective.package_binding import resolve_package_binding

    PACKAGE = package()
    # Refuses here if the directory's bytes are another version's, so every
    # assertion below is known to be about the package this harness declared.
    resolve_package_binding(VERSION_TAG, ROOT)
    authority = load("authority_parameters.json")
    stage1 = load("stage1_manifest.json")
    stage2 = load("stage2_locked_manifest.json")
    authority_sha = hashlib.sha256((PACKAGE / "authority_parameters.json").read_bytes()).hexdigest()
    assert stage1["authority_binding"]["sha256"] == authority_sha
    assert stage2["authority_binding"]["sha256"] == authority_sha
    assert stage2["stage1_manifest_binding"] == hashlib.sha256(
        (PACKAGE / "stage1_manifest.json").read_bytes()).hexdigest()
    assert len(stage1["units"]) == authority["stage1_policy"]["run_count"] == 8
    assert {(unit["direction"], unit["scene"], unit["design_role"])
            for unit in stage1["units"]} == {
        (direction, scene, role)
        for direction in authority["stage1_policy"]["directions"]
        for scene in authority["stage1_policy"]["scenes"]
        for role in authority["stage1_policy"]["replicate_roles"].values()
    }
    assert authority["stage1_policy"]["temporal_alignment"]["prospective_ci_width"][
        "acceptance_threshold"] is None
    identities = stage2["trajectory_identities"]
    assert len(identities) == authority["stage2_policy"]["paired_trajectory_identities"] == 25
    phases = authority["stage2_policy"]["phase_offsets_frames"]
    folds = authority["stage2_policy"]["outer_folds"]
    assert all(sorted(item["phase_frames"] for item in identities if item["outer_fold"] == fold)
               == sorted(phases) for fold in range(folds))
    assert sum(item["direction"] == "LEFT_TO_RIGHT" for item in identities) == 13
    documents = {"authority": authority, "stage1": stage1, "stage2": stage2}
    assert "0.4374893206596274" not in json.dumps(documents)
    assert not superseded_half_extent_present(documents)
    assert authority["STAGE_1_COLLECTION_AUTHORIZED"] is False
    assert authority["STAGE_2_COLLECTION_AUTHORIZED"] is False
    assert stage1["STAGE_2_COLLECTION_AUTHORIZED"] is False
    assert stage2["STAGE_2_COLLECTION_AUTHORIZED"] is False
    assert authority["REGIME_A_PRIME_COLLECTION_AUTHORIZED"] == "NO"
    assert authority["confirmatory_collection_authorized"] is False

    for document in REQUIRED_DOCUMENTS[VERSION_TAG]:
        assert (PACKAGE / document).is_file(), f"package document is absent: {document}"

    for document, allowed, minimum_rows in DOCUMENT_TABLE_AUDITS[VERSION_TAG]:
        rows = [line for line in (PACKAGE / document).read_text().splitlines()
                if line.startswith("|") and "`" in line and "Choice" not in line]
        assert len(rows) >= minimum_rows, f"{document} carries no classified rows"
        for row in rows:
            dispositions = {value for value in allowed if f"`{value}`" in row}
            assert len(dispositions) == 1, f"unclassified {document} row: {row}"


def audit_projection_exploit() -> None:
    """Permanently reject finite out-of-frame coordinates and stale PASS summaries."""
    authority = load("authority_parameters.json")
    stage1 = load("stage1_manifest.json")
    frame = authority["apparatus"]["canonical_frame_pixels"]
    grid = authority["apparatus"]["visual_token_grid"]
    invalid = [
        {"screen_x": -1.0, "screen_y": 180.0, "token_row": 7, "token_col": 0},
        {"screen_x": 320.0, "screen_y": -1.0, "token_row": 0, "token_col": 12},
        {"screen_x": frame[0], "screen_y": 180.0, "token_row": 7, "token_col": 23},
        {"screen_x": 320.0, "screen_y": frame[1], "token_row": 13, "token_col": 12},
    ]
    assert all(not derive_projection_validity(row, frame_pixels=frame, token_grid=grid)
               for row in invalid)
    evaluator = Stage1Evaluator(authority, stage1,
        authority_sha256=stage1["authority_binding"]["sha256"], manifest_sha256="0" * 64)
    sample = {**invalid[0], "projection_frame_pixels": frame, "projection_token_grid": grid,
        "point_visible": True, "detector_visible": True, "render_frame_present": True,
        "projected_in_frame": True, "temporal_alignment_resolved": True,
        "identity_valid": True, "in_support": True, "runtime_provenance_resolved": True,
        "path_state_valid": True, "malformed_or_missing": False, "world_x": 0.0}
    no_wall = next(unit for unit in stage1["units"] if unit["scene"] == "NO_WALL")
    try:
        evaluator.expected_regime(sample, no_wall, {})
    except EvidenceError:
        pass
    else:
        raise AssertionError("finite out-of-frame coordinates overrode projected_in_frame")


def main() -> int:
    audit_documents()
    audit_projection_exploit()
    entrypoints = ENTRYPOINT_DIRECTORY[VERSION_TAG]
    run(sys.executable, "-m", "pytest", *SUITES[VERSION_TAG], "-q")
    run(sys.executable, f"{entrypoints}/verify_package.py")
    # Both entrypoint trees: the v0.3 surface delegates into the v0.2 modules,
    # so compiling only the declared version would leave half of what a v0.3
    # command actually executes unchecked.
    run(sys.executable, "-m", "compileall", "-q", "src/mineocclude/prospective",
        *sorted(set(ENTRYPOINT_DIRECTORY.values())), "tests/prospective")
    print("PROSPECTIVE_ACCEPTANCE_HARNESS_STATUS=PASS")
    print(f"ACCEPTED_PACKAGE_VERSION={VERSION_TAG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
