#!/usr/bin/env python3
"""Deterministic construction-time consistency audit; performs no capture."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

#: Package version this audit verifies. Rebound -- once, before ``main`` -- by
#: the sibling v0.3 entrypoint, so pointing this audit at a package is a
#: deliberate act rather than a consequence of which directory it lives in.
VERSION_TAG = "v0.2"

#: The one genuinely version-specific expectation. Everything else below holds
#: for every package in this family and is checked identically.
AUTHORITY_STATUS = {"v0.2": "DRAFT_REPAIRED_UNFROZEN_NOT_AUTHORIZED",
                    "v0.3": "DRAFT_PROSPECTIVE_UNFROZEN_NOT_AUTHORIZED",
                    "v0.4": "DRAFT_PROSPECTIVE_UNFROZEN_NOT_AUTHORIZED"}


def load(name: str) -> dict:
    return json.loads((package() / name).read_text())


def package() -> Path:
    from mineocclude.prospective.package_binding import package_directory

    return package_directory(VERSION_TAG, ROOT)


def main() -> None:
    from mineocclude.prospective.development_workflow import (
        bind_manifest, stage2_materialization_phase, superseded_half_extent_present,
        validate_stage2_manifest_design)
    from mineocclude.prospective.package_binding import resolve_package_binding

    PACKAGE = package()
    # Refuses before a single assertion runs if the directory's bytes belong to
    # another version, so this audit cannot certify the predecessor package
    # while reporting the successor's name.
    binding = resolve_package_binding(VERSION_TAG, ROOT)
    authority_path = PACKAGE / "authority_parameters.json"
    authority = load("authority_parameters.json")
    stage1, stage2 = load("stage1_manifest.json"), load("stage2_locked_manifest.json")
    bind_manifest(authority_path, stage1); bind_manifest(authority_path, stage2)
    # This audit certifies committed package bytes, and a package has two
    # legitimate committed states: the draft template it is built in, and the
    # post-Stage-1 materialized form the builder's ``--stage1-decision`` mode
    # rewrites it into. Requiring the draft state unconditionally meant the audit
    # failed on the successful outcome of the repository's own materialization
    # step -- not on any defect. The phase is read from the manifest and the
    # matching rule set is applied in full; an unknown status fails closed, and
    # neither phase is an authorization.
    materialized = stage2_materialization_phase(stage2)
    validate_stage2_manifest_design(authority, stage2, require_materialized=materialized)
    assert authority["status"] == AUTHORITY_STATUS[VERSION_TAG]
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
    package_documents = {"authority": authority, "stage1": stage1, "stage2": stage2}
    serialized = json.dumps(package_documents)
    assert "HIDDEN_BOUNDS" not in serialized and "0.1660274234445584" not in serialized
    assert "0.4374893206596274" not in serialized
    assert "independent_method_count" not in serialized
    assert not superseded_half_extent_present(package_documents)
    # The phase must be declared consistently by every field that depends on it,
    # so a status flipped by hand does not by itself select the weaker rule set.
    # A draft names no Stage-1 outcome because none exists yet; a materialized
    # manifest must name the exact frozen decision and evidence its windows came
    # from. Whether that Stage-1 pair is a genuine PASS is re-derived at the
    # Stage-2 barrier, which is the only place that question can be answered.
    expected_window = ("MATERIALIZED_FROM_STAGE1" if materialized
                       else "TO_BE_MATERIALIZED_FROM_FROZEN_STAGE1_DECISION")
    assert all(item["target_window_status"] == expected_window
               for item in stage2["trajectory_identities"])
    stage1_bindings = (stage2.get("stage1_decision_sha256"), stage2.get("stage1_evidence_sha256"))
    if materialized:
        assert all(isinstance(value, str) and len(value) == 64
                   and all(character in "0123456789abcdef" for character in value)
                   for value in stage1_bindings), "materialized Stage-2 names no Stage-1 outcome"
    else:
        assert stage1_bindings == (None, None), "draft Stage-2 names a Stage-1 outcome"
    # B009: the promoted Stage-2 decision contract. Every package in this family
    # has a Stage-2 locked manifest and therefore carries one. resolve_package_binding
    # already proved the two-way digest binding above; this re-states the
    # scientific content the document must declare, so a contract that bound
    # correctly but promised nothing cannot pass.
    if True:
        contract = json.loads(binding.stage2_decision_authority_path.read_text())
        assert contract["classification"] == "DEVELOPMENT_ONLY"
        assert contract["promotion"]["outcome_adaptive_change"] is False
        assert contract["promotion"]["scientific_outcomes_observed"] is False
        assert contract["promotion"]["new_scientific_values_invented"] is False
        assert contract["terminal"]["states"] == ["PASS", "FAIL", "BLOCKED"]
        assert contract["terminal"]["leading_readout"] == "BEST_K"
        assert contract["terminal"]["terminal_status_is_re_derived_not_copied"] is True
        assert contract["terminal"]["pass_authorizes"] == {
            **contract["terminal"]["pass_authorizes"],
            "confirmatory_collection": False, "causal_intervention": False,
            "next_rung": False}
        assert contract["best_k_gates"]["count"] == 6
        assert sorted(contract["best_k_gates"]["definitions"]) == contract["best_k_gates"]["names"]
        assert contract["readout_procedure"]["k_grid"] == [1, 4, 8, 16, 32, 64, 128]
        assert contract["readout_procedure"]["alpha_grid"] == [0.1, 1.0, 10.0, 100.0]
        assert contract["readout_procedure"]["outer_fold_aggregation"]["rule"] == (
            "POOLED_OUT_OF_FOLD_THEN_TRAJECTORY_EQUAL")
        assert contract["artifacts"]["evidence_builder_may_assert_scientific_status"] is False
        # The promotion may not have moved a Stage-2 design parameter. Those
        # still live in authority_parameters.json and are read from there.
        assert "stage2_policy" not in contract
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
                         "tests/test_regime_a_production.py",
                         # Stage-1 at 95d6fe9f terminated STAGE1_BLOCKED because a
                         # failed startup stranded a server holding the world
                         # session.lock: launch_runtime raised inside
                         # CaptureSession.__enter__, so __exit__ never ran. The
                         # partial-entry teardown lives in the two files that own
                         # the acquisition, so the correction is recorded here
                         # rather than the check being relaxed to hide it.
                         "scripts/regime_a_prime_qualification_v0_1/p2_common.py",
                         "scripts/run_large_scale_no_wall_campaign.py",
                         # NEW-B001 / NEW-B002. The extractor recorded
                         # checkpoint_sha256 from two attributes
                         # MineWorldRuntimeIdentity has never had, so every real
                         # receipt bound "" and failed OPEN on checkpoint
                         # identity; and it inferred its scientific rows from
                         # visibility.tau without ever proving them equal to the
                         # manifest's target_model_frame_indices. Both are
                         # repaired in place. p3_run_sequential is touched only
                         # to pass the new required keyword explicitly -- the
                         # completed P3 campaign has no authority row set and
                         # says so rather than passing its own derivation off as
                         # one.
                         "scripts/regime_a_prime_qualification_v0_1/p2d_extract.py",
                         "scripts/regime_a_prime_qualification_v0_1/p3_run_sequential.py",
                         # B001. The readout recorded which identities each outer
                         # fold trained and tested on, and nothing could check
                         # them: a terminal PASS could have survived train ==
                         # test, a K outside the grid, or one trajectory held out
                         # in every fold. The two readout functions now also
                         # record the inner-fold assignment they used and a
                         # canonical digest of the rows they actually predicted,
                         # which is what makes those properties re-derivable. The
                         # tau ceiling on selection rows is named rather than
                         # left as a bare literal. No number moves.
                         "scripts/regime_a_prime_qualification_v0_1/p2e_analyze.py")
    allowed = ("docs/status/integration/regime_a_prime_qualification_v0_1/"
               "prospective_development_authority_v0_2/", "schemas/prospective/",
               "scripts/regime_a_prime_qualification_v0_2/",
               "src/mineocclude/prospective/development_workflow.py",
               "tests/prospective/test_development_authority_v0_2_repair.py",
               "tests/prospective/test_provenance_authorization_and_stage_binding.py",
               "tests/prospective/test_stage1_evidence_builder_end_to_end.py",
               "tests/prospective/test_capture_contract_and_startup_repair.py",
               "tests/prospective/test_captured_camera_apparatus.py",
               # The v0.3 successor surface: its package, its builders and
               # execution entrypoints, the extent-geometry engine its truth
               # predicate is computed by, the version-binding module every
               # entrypoint resolves through, and their tests. Enumerated one
               # path at a time for the same reason the v0.2 entries are -- an
               # unenumerated path is an unreviewed change to a frozen tree.
               "docs/status/integration/regime_a_prime_qualification_v0_1/"
               "prospective_development_authority_v0_3/",
               "scripts/regime_a_prime_qualification_v0_3/",
               "src/mineocclude/prospective/extent_geometry.py",
               "src/mineocclude/prospective/package_binding.py",
               "tests/prospective/test_extent_geometry_v0_3.py",
               "tests/prospective/test_v0_3_execution_entrypoints.py",
               "tests/prospective/test_v0_3_probe_producer_authority.py",
               "tests/prospective/test_provenance_artifact_id_version_binding.py",
               # The v0.3 builder-synchronization successor: the end-to-end
               # regression that binds the builder to a v0.3 authority (the
               # coverage gap 134a242 fell through), the decision-identity
               # version-binding suite, and the audit pinning every scientific
               # constant the repair was forbidden to move.
               "tests/prospective/test_stage1_evidence_builder_v0_3_end_to_end.py",
               "tests/prospective/test_stage1_decision_artifact_id_version_binding.py",
               "tests/prospective/test_v0_3_scientific_non_change_audit.py",
               # The v0.4 successor surface. v0.4 changes no science -- its
               # scientific delta against v0.3 is empty and proved empty at build
               # time -- but the v0.3 Stage-1 terminated in a scientific FAIL,
               # which permanently closes its a1x_*/83xxx inventory. A new
               # prospective inventory needs a new package version because that
               # is what every artifact identity is templated off.
               "docs/status/integration/regime_a_prime_qualification_v0_1/"
               "prospective_development_authority_v0_4/",
               "scripts/regime_a_prime_qualification_v0_4/",
               "tests/prospective/test_v0_4_package_binding.py",
               # The v0.4 Stage-2-preparation successor: time-invariant historical
               # source verification, and the Stage-2 producer/barrier surface it
               # unblocks. Enumerated one path at a time like every entry above.
               "tests/prospective/test_historical_source_verification.py",
               "tests/prospective/test_v0_4_stage2_preparation.py",
               # The Stage-2 execution-path repair. The Stage-2 pipeline had
               # never met real bytes, so its consumer-side defects -- the stale
               # transition schema, the design-vs-runtime scene vocabulary, the
               # missing scientific_run_id on 54 units, the derived durable URI,
               # and the live-HEAD coupling of completed artifacts -- were all
               # latent. The repairs are edits to already-enumerated sources; the
               # two paths below are new files and are enumerated one at a time
               # like every entry above.
               #
               # unit1_checkpoint.py is the OPERATIONAL processability gate that
               # stops a Stage-2 collection if the FIRST authorized capture is
               # not structurally consumable, so the remaining 49 are never spent
               # on bytes the frozen pipeline cannot read. It observes no
               # scientific outcome and can change no scientific parameter.
               "src/mineocclude/prospective/unit1_checkpoint.py",
               "tests/prospective/test_stage2_execution_path_repair.py",
               # The Stage-2 terminal authority and binding closure (B009 plus
               # NEW-B001/NEW-B002). Terminal used to copy the BEST-K readout's
               # own qualification_status, so no independent component ever
               # re-derived a gate and no completed Stage-2 decision could have
               # been reproduced from frozen rules. These are the evidence
               # builder, the independent evaluator and reproduction verifier,
               # the checkpoint/target-row binding both defects live in, and
               # their suite. Enumerated one path at a time like every entry
               # above.
               "src/mineocclude/prospective/stage2_evidence.py",
               "src/mineocclude/prospective/stage2_decision.py",
               "src/mineocclude/prospective/activation_binding.py",
               "tests/prospective/test_stage2_terminal_authority.py",
               # The final operational and terminal verification closure
               # (B001-B008). Two new modules, enumerated one at a time like
               # every entry above:
               #
               # fold_discipline.py re-derives outer/inner fold membership, held-
               # out row coverage and K/alpha grid membership from frozen
               # authority, so the terminal can establish what the readout
               # previously only reported (B001).
               #
               # stage2_processability.py is the PRODUCTION prober the unit-1
               # checkpoint never had, plus the per-capture-unit structural probe
               # the controller now runs after every unit. Both are operational:
               # they observe no scientific outcome and can change no scientific
               # parameter (B002).
               "src/mineocclude/prospective/fold_discipline.py",
               "src/mineocclude/prospective/stage2_processability.py",
               "tests/prospective/test_stage2_fold_and_terminal_verification.py",
               "tests/prospective/test_stage2_operational_closure.py",
               # The canonical Stage-2 trajectory arithmetic closure. Built-in
               # sum() is naive left-to-right accumulation before CPython 3.12
               # and Neumaier-compensated from 3.12, so causal_fir_targets
               # produced different binary64 labels on the interpreter that
               # materialized the frozen Stage-2 manifest and the pinned
               # mineworld interpreter that re-derives them at capture time; all
               # 50 units failed the exact label check and no scientific capture
               # was reachable. The reduction is now the exactly-rounded rule
               # temporal_alignment.py already applied to every other FIR
               # quantity, which is interpreter-independent and leaves the
               # frozen manifest byte-identical. Only the suite is enumerated
               # here: the two implementation files are already corrected
               # sources.
               "tests/prospective/test_canonical_fir_arithmetic.py",
               # The authorized Stage-2 capture/processing provenance split. Five
               # checks required a capture receipt's source_commit_sha to equal the
               # campaign commit -- a source-homogeneity proxy that turns a valid,
               # durable, physically irreproducible capture into an invalid one the
               # moment a downstream defect forces a successor freeze, whereupon the
               # controller recaptures it. capture_closure derives which components
               # can actually change a raw capture (call-graph reachability at
               # definition granularity, seeded at the capture driver);
               # capture_admission decides admission on closure equality rather than
               # commit equality. The frozen governance document and its builder are
               # registered under the package/scripts prefixes above.
               "src/mineocclude/prospective/capture_closure.py",
               "src/mineocclude/prospective/capture_admission.py",
               "tests/prospective/test_stage2_capture_processing_provenance_split.py",
               # The Part-2 execution repairs: C1, the scientific extraction path
               # that constructed a Layer4Extractor and called extract() without
               # ensure_loaded(); and C2, the same commit-equality proxy surviving on
               # the derived side, where it refused the physical-gate PASS produced by
               # the predecessor freeze.
               "src/mineocclude/prospective/physical_gate_admission.py",
               "tests/prospective/test_stage2_c1_extraction_and_gate_admission.py",
               # C4, the identity namespace collision the T1 canary exposed after
               # C1 and C3 were cleared. extraction() bound the typed capture
               # identity and the model runtime identity to one name; the second
               # shadowed the first, and the receipt asked a mapping of checkpoint
               # digests for a trajectory identity once the activation was already
               # written. Only the suite is enumerated here: the scientific
               # backend and the operational prober it repairs are both already
               # registered above.
               "tests/prospective/test_stage2_c4_identity_namespace_binding.py",
               # The disaster-recovery repairs, R1 and R2. R1: restore-unit derived
               # the CAPTURE commit from the PROCESSING provenance receipt, which is
               # pinned to live HEAD, so a legitimately mixed-freeze cohort could not
               # be restored from durable evidence that was completely intact. R2:
               # the physical-gate receipt WRAPPER was local-only and was destroyed
               # with the host, while its durable payload and checksum manifest
               # survived; the successor admits that surviving evidence on
               # gate-critical closure equality and never reconstructs the wrapper.
               # The governance document is registered under the package prefix.
               "tests/prospective/test_stage2_disaster_recovery_r1_r2.py",
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
    print(f"PACKAGE_VERSION={binding.version_tag}")
    print(f"PACKAGE_AUTHORITY_ARTIFACT_ID={binding.authority_artifact_id}")
    print(f"PACKAGE_STAGE1_MANIFEST_ARTIFACT_ID={binding.stage1_manifest_artifact_id}")
    print(f"PACKAGE_RUN_NAMESPACE={binding.run_namespace}")
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
