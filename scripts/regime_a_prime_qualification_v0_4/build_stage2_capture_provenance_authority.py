#!/usr/bin/env python3
"""Freeze the authorized Stage-2 capture / processing provenance split.

Why this artifact exists
=======================

Stage-2 collection began, one real scientific capture completed and became durable,
and a defect was then found *downstream* of capture: the extraction path fed the
raw capture package's legacy trajectory identity into a resolver that validates
Stage-2 visibility rows, so every real unit was refused for a cross-namespace
mismatch. Repairing it requires a successor freeze.

At that point five independent checks required a capture receipt's
``source_commit_sha`` to equal the campaign's commit. Each was written as a
source-homogeneity proxy -- "one campaign, one freeze, one commit" -- which is
correct until a successor freeze is needed and silently becomes a correctness bug
at that moment: it declares a valid, durable, physically irreproducible capture
invalid, and the controller's response to an invalid capture is to take it again.

The operator's governance decision resolves this by separating two facts the proxy
had conflated. This document freezes that decision prospectively, before any
Stage-2 scientific outcome exists.

Why it is a separate document
=============================

Two files could have carried this rule and must not.

``authority_parameters.json`` is welded to the completed v0.4 Stage-1 PASS:
``stage1_decision.json`` records ``authority_sha256 = 52b9590b...``, the historical
re-derivation compares against those bytes, and ``require_stage2_authorization``
refuses a Stage-1 decision whose authority digest is not the live one. Editing it
would make the frozen Stage-1 PASS irreproducible and simultaneously unusable as
the predicate for Stage-2 authorization.

``stage2_decision_authority.json`` is the *scientific* decision contract -- K grid,
alphas, fold construction, the six BEST-K gates, terminal semantics. An operational
rule about which raw captures may be processed is not within its scope, and putting
it there would mean an operational governance change altered the bytes of the
scientific decision contract.

So this lands beside both, exactly as the Stage-2 decision authority landed beside
the authority: bound to the authority's bytes in both directions, and bound
forward into the successor Stage-2 provenance and authorization path rather than
into the frozen scientific manifest -- which is what keeps
``stage2_locked_manifest.json`` byte-identical and its scientific inventory
untouched.

Why nothing here is a scientific choice
=======================================

Every clause is about provenance, identity and closure equality. None may depend on
RMSE, R-squared, a decoder result, BEST-K, FULL, a bootstrap interval or a terminal
status, and ``depends_on_scientific_outcome`` is recorded as ``false`` and checked
by the consumer. The capture-critical closure this document governs is derived from
the source graph by :mod:`mineocclude.prospective.capture_closure`, not enumerated
here, so the document cannot quietly widen or narrow it.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

DEFAULT_VERSION = "v0.4"

#: The freeze whose downstream defect made a successor processing freeze necessary,
#: and under which the one existing real capture was taken.
PREDECESSOR_CAPTURE_FREEZE = "49f0cca9d0ec6d204444bf3c0d1fa5fc7e263936"


def build(*, version_tag: str) -> tuple[dict, Path, Path]:
    from mineocclude.prospective.capture_admission import (
        CAPTURE_PROVENANCE_AUTHORITY_FILENAME,
        capture_provenance_authority_artifact_id_for,
    )
    from mineocclude.prospective.capture_closure import (
        CAPTURE_CRITICAL_APPARATUS_FILES,
        CAPTURE_CRITICAL_APPARATUS_OBSERVATIONS,
        CAPTURE_CRITICAL_NON_SOURCE_RUNTIME_IDENTITIES,
        CAPTURE_ENTRYPOINTS,
        GOVERNANCE_SCOPE_COMPONENTS,
        MODULE_PROLOGUE,
        capture_critical_closure_at,
        capture_critical_paths,
        derive_capture_critical_symbols,
        worktree_reader,
    )
    from mineocclude.prospective.package_binding import package_directory

    package = package_directory(version_tag, ROOT)
    authority_path = package / "authority_parameters.json"
    if not authority_path.is_file():
        raise SystemExit(f"authority is absent: {authority_path}")
    authority_sha256 = hashlib.sha256(authority_path.read_bytes()).hexdigest()

    symbols = derive_capture_critical_symbols(repository=ROOT)
    closure_sha, digests = capture_critical_closure_at(worktree_reader(ROOT), repository=ROOT)
    paths = capture_critical_paths(symbols)

    document = {
        "artifact_id": capture_provenance_authority_artifact_id_for(version_tag),
        "schema_version": "1.0",
        "classification": "DEVELOPMENT_ONLY",
        "status": "FROZEN_PROSPECTIVE_GOVERNANCE",
        "generated_by": "scripts/regime_a_prime_qualification_v0_4/"
                        "build_stage2_capture_provenance_authority.py",
        "scope": "STAGE_2_ONLY",
        "authorized_option": "OPTION_3_SPLIT_CAPTURE_PROVENANCE_FROM_PROCESSING_PROVENANCE",
        "extends_authority": {
            "path": authority_path.relative_to(ROOT).as_posix(),
            "sha256": authority_sha256,
        },
        # The unauthorized / non-adaptive baseline the consumer checks.
        "STAGE_2_COLLECTION_AUTHORIZED": False,
        "confirmatory_collection_authorized": False,
        "depends_on_scientific_outcome": False,

        "decision_is_prospective_with_respect_to_stage2_outcomes": True,
        "reason_for_decision": (
            "A frozen DOWNSTREAM identity defect requires a successor processing "
            "freeze after a valid raw source capture already exists. No Stage-2 "
            "decoder outcome has been computed, exposed or consulted."),

        # ------------------------------------------------------------------
        "immutable_capture_evidence": {
            "principle": (
                "A completed raw capture remains permanently bound to the exact "
                "source, runtime, manifest, authorization and provenance under "
                "which it was actually captured. A later downstream software repair "
                "MUST NOT rewrite it."),
            "fields_never_rewritten_to_successor_values": [
                "capture_source_commit",
                "capture_critical_closure_sha256",
                "capture_preoutcome_provenance_sha256",
                "capture_authorization_sha256",
                "capture_manifest_sha256",
                "capture_authority_sha256",
                "capture_receipt_sha256",
                "durable_object_inventory",
                "remote_checksum_manifest_sha256",
                "runtime_provenance_receipt",
                "captured_apparatus_receipt",
                "unit_id",
                "episode_id",
                "trajectory_id",
                "scene",
                "seed",
                "noise_seed",
                "expected_path_sha256",
                "path_state_receipt",
            ],
            "receipt_is_read_only_to_every_consumer": True,
        },

        # ------------------------------------------------------------------
        "capture_compatibility": {
            "principle": (
                "A raw capture produced under predecessor full commit P may "
                "participate in a successor processing campaign S only if its "
                "capture-critical closure is EQUAL to the cohort's authorized "
                "closure. Full repository source-commit equality is NOT required, "
                "and is NOT sufficient on its own either."),
            "lineage_is_not_evidence": (
                "Capture compatibility is NOT established by two commits belonging "
                "to a declared lineage, by a permitted-commit list, or by any "
                "ancestry relation. No commit is enumerated by this document."),
            "required_conditions": [
                "same scientific manifest identity and inventory",
                "same authority identity required for capture",
                "same scientific capture unit identity",
                "same scientific trajectory identity",
                "same scene",
                "same seed and noise seed",
                "same episode",
                "same target rows and path identity",
                "same capture-critical closure",
                "same capture runtime and apparatus identities",
                "original capture receipt verifies independently",
                "capture-time recorded source digests agree with the capture commit",
                "raw durable bytes verify exactly",
            ],
            "full_repository_commit_may_differ": True,
            "capture_critical_closure_must_be_equal": True,
        },

        # ------------------------------------------------------------------
        "capture_critical_closure": {
            "derivation": (
                "Call-graph reachability over first-party definitions, seeded at the "
                "Stage-2 capture DRIVER entrypoints, digesting the exact source text "
                "of each reachable definition plus each capture-critical file's "
                "executable module prologue."),
            "why_not_module_import_closure": (
                "The transitive module-import closure of the capture entrypoint is 60 "
                "files and contains p2d_extract, p2e_analyze, the model adapter, the "
                "activation hooks and the ridge implementation, because "
                "p3_run_sequential binds those names at module scope while the capture "
                "path uses only derive_artifacts from it. Adopting it would make the "
                "capture and processing closures nearly identical and every downstream "
                "repair would fail capture compatibility -- not because a frame could "
                "change, but because Python binds names at module scope."),
            "why_definitions_not_files": (
                "development_workflow holds both derive_effective_capture_spec, which "
                "decides the seed, frame count, speed and start position a capture runs "
                "under, and DurableController, which cannot touch a captured byte. "
                "Digesting whole files would make an edit to the second "
                "indistinguishable from an edit to the first and report a changed "
                "capture apparatus when no capture-determining component had changed -- "
                "a false BLOCKED that would force recollection of valid measurements."),
            "why_the_driver_and_not_the_launcher": (
                "The capture is produced by stage_unit_driver in its own process. The "
                "launching controller decides only WHETHER a unit runs; the driver "
                "re-derives and re-verifies its authority, manifest, stage binding, "
                "authorization, provenance and unit identity through "
                "require_capture_authorization before capturing anything, and refuses "
                "on any disagreement. A launcher therefore cannot change what a capture "
                "records or the identity it records itself under."),
            "unbounded_module_handle_rule": (
                "A module the capture path holds as a module OBJECT rather than by an "
                "imported name contributes ALL of its definitions, because name "
                "resolution cannot bound which of them execute. This is why the live "
                "campaign runtime -- reached as a returned module from "
                "p2_common.load_live and stored on CaptureSession.live -- is governed "
                "in full. The escalation is conservative: it can only add components."),
            "import_time_side_effect_soundness": (
                "Every file that is import-reachable but not call-reachable is asserted "
                "by test to have a definition-only module body, so a module doing real "
                "work at import time is forced into governance rather than pruned."),
            "governance_scope_projection": (
                "A reachable component whose only capture-time effect is to say WHICH "
                "source paths pre-outcome provenance must already have verified is "
                "digested by its capture-relevant PROJECTION -- the subset naming "
                "capture-critical paths -- not by its literal bytes. Lengthening the "
                "governed list strengthens verification of files that cannot change a "
                "frame; dropping a capture-critical path from it changes the projection "
                "and blocks."),
            "entrypoints": [f"{path}::{symbol}" for path, symbol in CAPTURE_ENTRYPOINTS],
            "governance_scope_components": [
                f"{path}::{symbol}" for path, symbol in GOVERNANCE_SCOPE_COMPONENTS],
            "module_prologue_pseudo_symbol": MODULE_PROLOGUE,
            "component_count": len(digests),
            "source_path_count": len(paths),
            "source_paths": paths,
            "closure_sha256_at_generation": closure_sha,
            "closure_is_derived_not_enumerated_here": True,
            "non_source_runtime_identities":
                list(CAPTURE_CRITICAL_NON_SOURCE_RUNTIME_IDENTITIES),
            "apparatus_files": list(CAPTURE_CRITICAL_APPARATUS_FILES),
            "apparatus_observations": list(CAPTURE_CRITICAL_APPARATUS_OBSERVATIONS),
            "apparatus_reference_is_frozen_authority_not_a_peer_capture": True,
        },

        # ------------------------------------------------------------------
        "processing_provenance": {
            "principle": (
                "Processing provenance is bound separately, to the exact successor "
                "source and runtime that produce activations, readouts and derived "
                "evidence."),
            "every_derived_artifact_records": [
                "processing_source_commit",
                "processing_runtime_critical_source_closure_sha256",
                "processing_provenance_sha256",
                "processing_authorization_sha256",
                "source_capture_unit_id",
                "source_capture_receipt_sha256",
                "source_capture_provenance_sha256",
                "source_capture_source_commit",
                "source_capture_capture_critical_closure_sha256",
            ],
            "derived_units_still_require_processing_commit_equality": [
                "physical_gates", "layer4_extraction", "best_k", "full", "terminal",
            ],
        },

        # ------------------------------------------------------------------
        "no_provenance_laundering": {
            "principle": (
                "A downstream processor MUST NOT claim capture_source_commit == "
                "processing_source_commit unless they actually are equal."),
            "enforcement": (
                "Both commits are recorded as separate fields and the equality claim "
                "is recomputed from them, so a hand-set boolean cannot carry it."),
        },

        # ------------------------------------------------------------------
        "recollection": {
            "a_valid_capture_must_not_be_recollected_because_processing_changed": True,
            "if_capture_critical_closure_differs": (
                "Reuse is FORBIDDEN and the pipeline STOPS for authority review. "
                "Automatic recollection is forbidden, because recapturing would "
                "destroy the evidence that the apparatus had changed."),
            "automatic_recollection_authorized": False,
        },

        # ------------------------------------------------------------------
        "cohort_reporting": {
            "per_unit_capture_source_commit_retained_in_evidence": True,
            "mixed_full_commit_cohort_must_be_visible_not_hidden": True,
            "scientific_compatibility_fact": (
                "all admitted capture-critical closures are equal to one value"),
        },

        "predecessor_capture_freeze_at_decision_time": PREDECESSOR_CAPTURE_FREEZE,
        "historical_stage1_authority_modified": False,
        "stage2_scientific_decision_authority_modified": False,
        "stage2_locked_manifest_modified": False,
        "scientific_design_modified": False,
    }
    document["payload_sha256"] = hashlib.sha256(json.dumps(
        {key: value for key, value in document.items() if key != "payload_sha256"},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()
    return document, package / CAPTURE_PROVENANCE_AUTHORITY_FILENAME, authority_path


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default=DEFAULT_VERSION)
    arguments = parser.parse_args()
    document, output, _ = build(version_tag=arguments.version)
    output.write_bytes(json.dumps(document, indent=1, sort_keys=True).encode("utf-8") + b"\n")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(f"CAPTURE_PROVENANCE_AUTHORITY_ARTIFACT_ID={document['artifact_id']}")
    print(f"CAPTURE_PROVENANCE_AUTHORITY_PATH={output.relative_to(ROOT)}")
    print(f"CAPTURE_PROVENANCE_AUTHORITY_SHA256={digest}")
    print(f"CAPTURE_CRITICAL_COMPONENT_COUNT="
          f"{document['capture_critical_closure']['component_count']}")
    print(f"CAPTURE_CRITICAL_SOURCE_PATH_COUNT="
          f"{document['capture_critical_closure']['source_path_count']}")
    print(f"CAPTURE_CRITICAL_CLOSURE_SHA256="
          f"{document['capture_critical_closure']['closure_sha256_at_generation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
