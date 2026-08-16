#!/usr/bin/env python3
"""Deterministic construction-time consistency audit; performs no capture."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
PACKAGE = ROOT / "docs/status/integration/regime_a_prime_qualification_v0_1/prospective_development_authority_v0_2"


def load(name: str) -> dict:
    return json.loads((PACKAGE / name).read_text())


def main() -> None:
    from mineocclude.prospective.development_workflow import bind_manifest, validate_stage2_manifest_design

    authority_path = PACKAGE / "authority_parameters.json"
    authority = load("authority_parameters.json")
    stage1, stage2 = load("stage1_manifest.json"), load("stage2_locked_manifest.json")
    bind_manifest(authority_path, stage1); bind_manifest(authority_path, stage2)
    validate_stage2_manifest_design(authority, stage2, require_materialized=False)
    assert authority["status"] == "DRAFT_REPAIRED_UNFROZEN_NOT_AUTHORIZED"
    assert authority["STAGE_1_COLLECTION_AUTHORIZED"] is False
    assert authority["STAGE_2_COLLECTION_AUTHORIZED"] is False
    assert authority["confirmatory_collection_authorized"] is False
    assert authority["REGIME_A_PRIME_COLLECTION_AUTHORIZED"] == "NO"
    runtime_binding = "BOUND_AT_LAUNCH_BY_PREOUTCOME_PROVENANCE_RECEIPT"
    assert authority["prospective_source_commit_binding"] == runtime_binding
    assert "head" not in authority["runtime_identity_policy"]["required_fields"]
    assert stage1["source_commit_binding"] == runtime_binding and stage2["source_commit_binding"] == runtime_binding
    # Every apparatus-critical pin must be a materialized lowercase SHA-256.
    # The Minecraft server and Fabric launcher JARs were previously deferred
    # placeholders; an unmaterialized pin cannot constrain the runtime, so
    # requiring real digests is strictly stronger than the placeholder check it
    # replaces. Comparing them to the running apparatus is the launch-time
    # probe's job (verify_runtime_identity), not this environment-independent
    # package audit's.
    pins = authority["runtime_identity_policy"]["critical_file_sha256"]
    assert set(pins) == set(authority["runtime_identity_policy"]["critical_file_paths"])
    for name, pin in pins.items():
        assert (isinstance(pin, str) and len(pin) == 64
                and all(character in "0123456789abcdef" for character in pin)), name
    assert len(stage1["units"]) == 8 and stage1["speed_blocks_per_second"] == 2.0
    assert len(stage2["trajectory_identities"]) == 25 and len(stage2["capture_units"]) == 50
    assert all(sorted(item["phase_frames"] for item in stage2["trajectory_identities"]
                      if item["outer_fold"] == fold) == [0, 3, 6, 9, 12]
               for fold in range(5))
    assert sum(item["direction"] == "LEFT_TO_RIGHT"
               for item in stage2["trajectory_identities"]) == 13
    assert len(stage2["extraction_units"]) == 50 and stage2["STAGE_2_COLLECTION_AUTHORIZED"] is False
    assert stage2["pipeline_order"].index("physical_gates") < stage2["pipeline_order"].index("layer4_extraction")
    p2 = json.loads((PACKAGE.parent / "p2_temporal_alignment_forensic_v0_1/05_p2_corrected_metrics.json").read_text())["models"]["B_kernel_convolved"]
    readout = authority["stage2_policy"]["readout"]
    assert readout["corrected_p2_best_k_visible_rmse_reference_blocks"] == p2["BEST_K"]["rmse_blocks"]
    assert readout["best_k_each_scene_rmse_maximum_blocks"] == 2 * p2["BEST_K"]["rmse_blocks"]
    serialized = json.dumps({"authority": authority, "stage1": stage1, "stage2": stage2})
    assert "HIDDEN_BOUNDS" not in serialized and "0.1660274234445584" not in serialized
    assert "0.52" not in serialized and "0.4374893206596274" not in serialized
    assert "independent_method_count" not in serialized
    assert all(item["target_window_status"] == "TO_BE_MATERIALIZED_FROM_FROZEN_STAGE1_DECISION"
               for item in stage2["trajectory_identities"])
    assert all(value != "UNJUSTIFIED" for value in _walk(authority))
    base = authority["immutable_software_forensic_base_sha"]
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", base, "HEAD"], cwd=ROOT,
                              capture_output=True, check=False)
    assert ancestor.returncode == 0, "immutable forensic base is not an ancestor of HEAD"
    # Prospectively corrected apparatus sources. Each is enumerated one file at
    # a time and carries a recorded FORENSIC_CONTINUITY_MATRIX disposition; no
    # frozen historical *artifact* is rewritten by any of them.
    corrected_sources = ("src/mineocclude/prospective/temporal_alignment.py",
                         "src/mineocclude/regime_a.py",
                         # Asserted the superseded uncropped projection value.
                         "tests/test_regime_a_production.py")
    allowed = ("docs/status/integration/regime_a_prime_qualification_v0_1/"
               "prospective_development_authority_v0_2/", "schemas/prospective/",
               "scripts/regime_a_prime_qualification_v0_2/",
               "src/mineocclude/prospective/development_workflow.py",
               "tests/prospective/test_development_authority_v0_2_repair.py",
               "tests/prospective/test_provenance_authorization_and_stage_binding.py",
               "tests/prospective/test_stage1_evidence_builder_end_to_end.py",
               *corrected_sources)
    changed = subprocess.run(["git", "diff", "--name-only", base, "--"], cwd=ROOT, text=True,
                             capture_output=True, check=True).stdout.splitlines()
    status = subprocess.run(["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=ROOT,
                            text=True, capture_output=True, check=True).stdout.splitlines()
    status_paths = [line[3:].split(" -> ")[-1] for line in status if len(line) > 3]
    unexpected = sorted({path for path in changed + status_paths
                         if not any(path == prefix or path.startswith(prefix) for prefix in allowed)})
    assert not unexpected, f"historical/base files changed: {unexpected}"
    touched = sorted({path for path in changed + status_paths if path in corrected_sources})
    print("PACKAGE_CONSISTENCY_STATUS=PASS")
    print("HISTORICAL_FROZEN_ARTIFACTS_MODIFIED=false")
    print(f"PROSPECTIVELY_CORRECTED_APPARATUS_SOURCES={','.join(touched) or 'none'}")
    print("COLLECTION_AUTHORIZED=false")


def _walk(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)
    else:
        yield value


if __name__ == "__main__": main()
