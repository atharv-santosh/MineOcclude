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


PACKAGE = (ROOT / "docs/status/integration/regime_a_prime_qualification_v0_1"
           / "prospective_development_authority_v0_2")
ALLOWED_NUMERIC_CLASSES = {
    "FROZEN_EVIDENCE_DERIVED", "PROSPECTIVE_STAGE1_MEASURED", "PURE_IMPLEMENTATION_CONSTANT"
}
ALLOWED_CONTINUITY = {
    "INCORPORATED", "SUPERSEDED_WITH_JUSTIFICATION", "DEFERRED_EXPLICITLY",
    "NOT_AUTHORITY_RELEVANT",
}


def run(*command: str) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def load(name: str) -> dict:
    value = json.loads((PACKAGE / name).read_text())
    assert isinstance(value, dict)
    return value


def audit_documents() -> None:
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
    serialized = json.dumps({"authority": authority, "stage1": stage1, "stage2": stage2})
    assert "0.52" not in serialized and "0.4374893206596274" not in serialized
    assert authority["STAGE_1_COLLECTION_AUTHORIZED"] is False
    assert authority["STAGE_2_COLLECTION_AUTHORIZED"] is False
    assert stage1["STAGE_2_COLLECTION_AUTHORIZED"] is False
    assert stage2["STAGE_2_COLLECTION_AUTHORIZED"] is False
    assert authority["REGIME_A_PRIME_COLLECTION_AUTHORIZED"] == "NO"
    assert authority["confirmatory_collection_authorized"] is False

    trace_rows = [line for line in (PACKAGE / "NUMERIC_TRACEABILITY.md").read_text().splitlines()
                  if line.startswith("|") and "`" in line and "Choice" not in line]
    assert trace_rows
    for row in trace_rows:
        classifications = {value for value in ALLOWED_NUMERIC_CLASSES if f"`{value}`" in row}
        assert len(classifications) == 1, f"unclassified numeric traceability row: {row}"

    continuity_rows = [line for line in (PACKAGE / "FORENSIC_CONTINUITY_MATRIX.md").read_text().splitlines()
                       if line.startswith("|") and "`" in line]
    assert len(continuity_rows) >= 15
    for row in continuity_rows:
        dispositions = {value for value in ALLOWED_CONTINUITY if f"`{value}`" in row}
        assert len(dispositions) == 1, f"invalid forensic disposition: {row}"


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
        evaluator._expected_regime(sample, no_wall, {})
    except EvidenceError:
        pass
    else:
        raise AssertionError("finite out-of-frame coordinates overrode projected_in_frame")


def main() -> int:
    audit_documents()
    audit_projection_exploit()
    run(sys.executable, "-m", "pytest",
        "tests/prospective/test_development_authority_v0_2_repair.py",
        # D-A4 closure evidence: the artefact the real builder writes, not just
        # a hand-built document, must reach a PASS through the frozen evaluator.
        "tests/prospective/test_stage1_evidence_builder_end_to_end.py",
        # A4/A6 closure evidence: probe-execution provenance, cross-stage
        # binding, and the two receipt generators, each attacked directly.
        "tests/prospective/test_provenance_authorization_and_stage_binding.py", "-q")
    run(sys.executable, "scripts/regime_a_prime_qualification_v0_2/verify_package.py")
    run(sys.executable, "-m", "compileall", "-q",
        "src/mineocclude/prospective", "scripts/regime_a_prime_qualification_v0_2",
        "tests/prospective")
    print("PROSPECTIVE_ACCEPTANCE_HARNESS_STATUS=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
