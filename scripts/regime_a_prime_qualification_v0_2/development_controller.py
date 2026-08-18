#!/usr/bin/env python3
"""CLI for evaluation, monitoring, and locked durable execution."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# The controller is invoked as a script, so the repository ``src`` tree is not on
# ``sys.path``. Without this the CLI dies with ModuleNotFoundError before any
# authorization or provenance check executes, making Stage 1 unlaunchable.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mineocclude.prospective.development_workflow import (  # noqa: E402
    Decision, DurableController, EvidenceError, Stage1Evaluator, atomic_write_json,
    bind_manifest, bind_historical_source_closure, campaign_source_commit,
    RUNTIME_CRITICAL_SOURCE_PATHS, canonical_payload_sha256, evidence_source_drift,
    load_json, require_preoutcome_provenance,
    require_stage2_authorization, require_stage_manifest_binding,
    restore_durable_capture_tree, restore_durable_unit_state,
    runtime_critical_source_closure_sha256, sha256_file, stage_run_inventory_sha256,
)
from mineocclude.prospective.package_binding import (  # noqa: E402
    PackageBinding, artifact_version_tag, provenance_artifact_id_for,
    resolve_package_binding, stage1_decision_artifact_id,
)
from mineocclude.prospective.capture_admission import (  # noqa: E402
    build_capture_admission_context, load_capture_provenance_authority,
    verify_processing_provenance_binding,
)
from mineocclude.prospective.stage2_processability import (  # noqa: E402
    capture_root_for, capture_unit_structural_probe, make_unit1_checkpoint,
)

#: Exit status for an OPERATIONAL refusal. Deliberately distinct from 2, which
#: this CLI has always used for a completed scientific FAIL: a provenance or
#: binding problem must not be reportable with the same code as a real negative
#: result, and a caller scripting on the exit status must be able to tell them
#: apart without parsing text.
BLOCKED_EXIT = 3


#: Package version this controller drives. Rebound -- once, before ``main`` --
#: by the sibling v0.3 entrypoint. Nothing else in this file names a version:
#: the namespace, the stage role and the authorization identity all come out of
#: the bound authority's own stage binding table.
VERSION_TAG = "v0.2"


def package_binding(root: Path) -> PackageBinding:
    """Resolve the declared package, refusing if its bytes are another version.

    Deliberately not named ``binding``: ``main`` binds that name locally to the
    resolved *stage* binding, which would make this function unreachable from
    inside it and crash ``run-stage1`` with ``UnboundLocalError`` before any
    authorization was checked.
    """
    return resolve_package_binding(VERSION_TAG, root)


def paths(root: Path) -> tuple[Path, Path, Path]:
    bound = package_binding(root)
    return bound.authority_path, bound.stage1_manifest_path, bound.stage2_manifest_path


def required_sources(root: Path) -> list[Path]:
    return [root / relative for relative in RUNTIME_CRITICAL_SOURCE_PATHS]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    sub = parser.add_subparsers(dest="action", required=True)
    evaluate = sub.add_parser("evaluate-stage1")
    evaluate.add_argument("evidence", type=Path)
    evaluate.add_argument("output", type=Path)
    # B006. This used to evaluate any Stage-1 evidence in current-source mode
    # silently, so pointing it at a COMPLETED campaign's frozen evidence at a
    # later HEAD printed SCIENTIFIC FAIL for a legitimate PASS -- source drift
    # presented as a negative scientific result. The mode is now explicit and
    # required; neither branch can produce a scientific FAIL from drift.
    mode = evaluate.add_mutually_exclusive_group(required=True)
    mode.add_argument("--historical", type=Path, metavar="STAGE1_PROVENANCE",
                      help="evaluate a COMPLETED campaign against the source closure "
                           "recorded in its own frozen pre-outcome provenance receipt")
    mode.add_argument("--current-source", action="store_true",
                      help="evaluate a campaign running against the working tree now; "
                           "refuses with BLOCKED if the tree is not the source the "
                           "evidence records")
    monitor = sub.add_parser("monitor")
    monitor.add_argument("state_dir", type=Path)
    run1 = sub.add_parser("run-stage1")
    run1.add_argument("--authorization", type=Path, required=True)
    run1.add_argument("--provenance", type=Path, required=True)
    run1.add_argument("--state-dir", type=Path, required=True)
    run1.add_argument("--events", type=Path, required=True)
    run1.add_argument("--evidence", type=Path, required=True)
    run1.add_argument("--decision", type=Path, required=True)
    run2 = sub.add_parser("run-stage2")
    run2.add_argument("--stage1-evidence", type=Path, required=True)
    run2.add_argument("--stage1-decision", type=Path, required=True)
    # The Stage-1 campaign's own frozen pre-outcome provenance. Distinct from
    # --provenance, which is Stage-2's: that one binds the source about to run,
    # this one binds the source the reused Stage-1 PASS was collected under.
    run2.add_argument("--stage1-provenance", type=Path, required=True)
    run2.add_argument("--authorization", type=Path, required=True)
    run2.add_argument("--provenance", type=Path, required=True)
    run2.add_argument("--state-dir", type=Path, required=True)
    run2.add_argument("--events", type=Path, required=True)
    # B003. Recovering a unit whose local receipt was lost with the NVMe. The
    # raw bytes were always durable; the receipt now is too, so a lost local
    # tree is restored rather than recollected.
    restore = sub.add_parser("restore-unit")
    restore.add_argument("--stage", choices=["stage1-capture", "stage2-capture"],
                         required=True)
    restore.add_argument("--unit-id", required=True)
    restore.add_argument("--provenance", type=Path, required=True,
                         help="the campaign's own frozen pre-outcome provenance "
                              "receipt, which names the source freeze the receipt "
                              "must be bound to")
    restore.add_argument("--restore-capture-tree", action="store_true")
    restore.add_argument("--overwrite", action="store_true",
                         help="replace a differing local receipt; refused by default")
    args = parser.parse_args()
    bound = package_binding(args.repo.resolve())
    authority_path = bound.authority_path
    stage1_path = bound.stage1_manifest_path
    stage2_path = bound.stage2_manifest_path
    authority = load_json(authority_path)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=args.repo, text=True,
                          capture_output=True, check=True).stdout.strip()
    if args.action == "monitor":
        states = [load_json(path) for path in sorted(args.state_dir.glob("*.json"))]
        print(json.dumps({"durable_units": len(states), "states": states}, indent=2, sort_keys=True))
        return 0
    if args.action == "evaluate-stage1":
        manifest = load_json(stage1_path)
        bind_manifest(authority_path, manifest)
        evidence = load_json(args.evidence)
        closure = None
        if args.historical:
            # The completed campaign's own record of what ran. Failing to bind it
            # is a provenance problem, not a result: nothing is written and the
            # BLOCKED status is returned rather than a decision artifact.
            try:
                closure = bind_historical_source_closure(
                    load_json(args.historical),
                    provenance_sha256=sha256_file(args.historical),
                    expected_artifact_id=provenance_artifact_id_for(
                        artifact_version_tag(manifest["artifact_id"])),
                    authority_sha256=sha256_file(authority_path),
                    manifest_sha256=sha256_file(stage1_path))
            except (EvidenceError, KeyError, TypeError, ValueError) as exc:
                print(f"STAGE1_EVALUATION_STATUS=BLOCKED\nREASON=historical provenance "
                      f"does not establish the source that ran: {exc}", file=sys.stderr)
                return BLOCKED_EXIT
        else:
            drift = evidence_source_drift(evidence, args.repo.resolve())
            if drift["drifted"]:
                print("STAGE1_EVALUATION_STATUS=BLOCKED\nREASON=the working tree is not "
                      "the source this evidence records; re-run with --historical "
                      "<that campaign's pre-outcome provenance receipt>.\n"
                      f"RECORDED_SOURCE_COMMITS={','.join(drift['recorded_source_commits'])}\n"
                      f"DRIFTED_UNITS={','.join(drift['units'])}", file=sys.stderr)
                return BLOCKED_EXIT
        decision = Stage1Evaluator(authority, manifest, authority_sha256=sha256_file(authority_path),
                                   manifest_sha256=sha256_file(stage1_path),
                                   historical_source_closure=closure).evaluate(evidence)
        atomic_write_json(args.output, decision.to_dict(authority_sha256=sha256_file(authority_path),
            manifest_sha256=sha256_file(stage1_path), evidence_sha256=sha256_file(args.evidence),
            artifact_id=stage1_decision_artifact_id(manifest)))
        print(f"STAGE1_EVALUATION_STATUS={decision.status}")
        print(f"STAGE1_EVALUATION_MODE={'HISTORICAL' if closure else 'CURRENT_SOURCE'}")
        return 0 if decision.status == "PASS" else 2
    if args.action == "restore-unit":
        stage2 = args.stage == "stage2-capture"
        manifest_path = stage2_path if stage2 else stage1_path
        manifest = load_json(manifest_path)
        bind_manifest(authority_path, manifest)
        binding = require_stage_manifest_binding(args.stage, manifest,
            manifest_path=manifest_path, authority=authority, repository=args.repo.resolve())
        require_preoutcome_provenance(load_json(args.provenance), authority_path=authority_path,
            manifest_path=manifest_path, required_source_paths=required_sources(args.repo),
            provenance_artifact_id=bound.provenance_artifact_id)
        unit = next((item for item in manifest["units"]
                     if item.get("unit_id") == args.unit_id), None)
        if unit is None:
            print(f"RESTORE_STATUS=BLOCKED\nREASON=unknown unit {args.unit_id!r}",
                  file=sys.stderr)
            return BLOCKED_EXIT
        try:
            receipt = restore_durable_unit_state(manifest, unit,
                receipt_path=Path(unit["receipt_path"]),
                manifest_sha256=sha256_file(manifest_path),
                authority_sha256=sha256_file(authority_path),
                source_commit_sha=campaign_source_commit(load_json(args.provenance)),
                run_namespace=binding["run_namespace"], overwrite=args.overwrite)
            restored = (restore_durable_capture_tree(manifest, unit, receipt=receipt,
                            destination=capture_root_for(unit))
                        if args.restore_capture_tree else {})
        except (EvidenceError, KeyError, TypeError, ValueError) as exc:
            print(f"RESTORE_STATUS=BLOCKED\nREASON={exc}", file=sys.stderr)
            return BLOCKED_EXIT
        print(f"RESTORE_STATUS=RESTORED\nUNIT_ID={args.unit_id}")
        print(f"CAPTURE_RECEIPT_SHA256={sha256_file(Path(unit['receipt_path']))}")
        print(f"RESTORED_CAPTURE_OBJECTS={len(restored)}")
        print("RECAPTURE_REQUIRED=false")
        return 0
    if args.action == "run-stage1":
        manifest = load_json(stage1_path)
        bind_manifest(authority_path, manifest)
        # A6: the controller resolves its own stage through the frozen binding
        # table, so the authorization artifact_id it demands and the namespace it
        # runs under are the authority's, not literals repeated here.
        binding = require_stage_manifest_binding("stage1-capture", manifest,
            manifest_path=stage1_path, authority=authority, repository=args.repo.resolve())
        authorization = load_json(args.authorization)
        require_preoutcome_provenance(load_json(args.provenance), authority_path=authority_path,
            manifest_path=stage1_path, required_source_paths=required_sources(args.repo),
            provenance_artifact_id=bound.provenance_artifact_id)
        authorized = (
            authorization.get("artifact_id") == binding["authorization_artifact_id"]
            and authorization.get("status") == "FROZEN_AUTHORIZED"
            and authorization.get("STAGE_1_COLLECTION_AUTHORIZED") is True
            and authorization.get("STAGE_2_COLLECTION_AUTHORIZED") is False
            and authorization.get("authority_sha256") == sha256_file(authority_path)
            and authorization.get("stage1_manifest_sha256") == sha256_file(stage1_path)
            and authorization.get("source_commit_sha") == head
            and authorization.get("expected_run_namespace") == binding["run_namespace"]
            # Same stage/inventory/source-closure bindings the unit driver
            # enforces, so the delegated route is not weaker than the direct one.
            and authorization.get("authorized_stage") == binding["stage"]
            and authorization.get("stage_role") == binding["stage_role"]
            and authorization.get("stage1_run_inventory_sha256")
                == stage_run_inventory_sha256(manifest)
            and authorization.get("runtime_critical_source_closure_sha256")
                == runtime_critical_source_closure_sha256(args.repo.resolve())
            and authorization.get("preoutcome_provenance_receipt_sha256") == sha256_file(args.provenance)
            and authorization.get("confirmatory_collection_authorized") is False
            and authorization.get("authorization_payload_sha256")
                == canonical_payload_sha256(authorization, omit="authorization_payload_sha256")
            and manifest.get("source_commit_binding")
                == "BOUND_AT_LAUNCH_BY_PREOUTCOME_PROVENANCE_RECEIPT"
        )
        try:
            DurableController(manifest, args.state_dir, args.events,
                manifest_sha256=sha256_file(stage1_path), authority_sha256=sha256_file(authority_path),
                source_commit_sha=head, run_namespace=binding["run_namespace"],
                stage_role=binding["stage_role"],
                maximum_attempts=authority["stage1_policy"]["stop_rules"]["retry_same_unit_maximum_attempts"]
            ).run(authorized=authorized, environment={
                "MINEOCCLUDE_STAGE1_AUTHORIZATION_PATH": str(args.authorization),
                "MINEOCCLUDE_PREOUTCOME_PROVENANCE_PATH": str(args.provenance)})
            builder = args.repo / "scripts/regime_a_prime_qualification_v0_2/build_stage1_evidence.py"
            subprocess.run([sys.executable, str(builder), str(stage1_path), str(authority_path), str(args.evidence)], check=True)
            decision = Stage1Evaluator(authority, manifest, authority_sha256=sha256_file(authority_path),
                                       manifest_sha256=sha256_file(stage1_path)).evaluate(load_json(args.evidence))
        except Exception as exc:
            decision = Decision("FAIL", {"operational_completion": {"status": "FAIL", "detail": str(exc)}},
                                ("operational_completion",))
        evidence_sha = sha256_file(args.evidence) if args.evidence.is_file() else "0" * 64
        atomic_write_json(args.decision, decision.to_dict(authority_sha256=sha256_file(authority_path),
            manifest_sha256=sha256_file(stage1_path), evidence_sha256=evidence_sha,
            artifact_id=stage1_decision_artifact_id(manifest)))
        return 0 if decision.status == "PASS" else 2
    manifest = load_json(stage2_path)
    bind_manifest(authority_path, manifest)
    stage2_binding = require_stage_manifest_binding("stage2-capture", manifest,
        manifest_path=stage2_path, authority=authority, repository=args.repo.resolve())
    decision = load_json(args.stage1_decision)
    authorization = load_json(args.authorization)
    require_preoutcome_provenance(load_json(args.provenance), authority_path=authority_path,
        manifest_path=stage2_path, required_source_paths=required_sources(args.repo),
        provenance_artifact_id=bound.provenance_artifact_id)
    require_stage2_authorization(manifest, authorization,
        authorization_receipt_path=args.authorization, stage1_decision=decision,
        authority_path=authority_path, manifest_path=stage2_path,
        stage1_manifest_path=stage1_path, stage1_decision_path=args.stage1_decision,
        stage1_evidence_path=args.stage1_evidence,
        current_source_commit=head, preoutcome_provenance_path=args.provenance,
        stage1_preoutcome_provenance_path=args.stage1_provenance)
    # B002. The unit-1 operational processability checkpoint and the per-unit
    # structural probe were implemented and never constructed here, so the
    # module was dead code and a real campaign would have captured all fifty
    # expensive scientific trajectories before anything tried to process one.
    # Both are wired in below. Neither reads a scientific outcome; a failure of
    # either is BLOCKED and stops the remaining collection without altering any
    # scientific parameter.
    decision_authority = load_json(bound.stage2_decision_authority_path)
    activation_contract = decision_authority["activation_contract"]
    stage1_decision_document = load_json(args.stage1_decision)
    # The authorized capture/processing provenance split. Loaded and verified in
    # both directions against the authority bytes on disk before it can govern
    # anything, then bound into every consumer through one shared admission
    # context -- so the per-unit probe, the unit-1 checkpoint, the controller's
    # reuse test and the cohort evidence builder cannot drift into four slightly
    # different admission rules, which is how the superseded commit-equality proxy
    # came to be duplicated in five places.
    capture_provenance_authority, capture_provenance_authority_sha256 = (
        load_capture_provenance_authority(
            bound.package, version_tag=bound.version_tag,
            authority_path=authority_path, repository=args.repo.resolve()))
    # Independent consumer verification of the binding minted into the receipt.
    provenance_binding = verify_processing_provenance_binding(
        load_json(args.provenance), package=bound.package, version_tag=bound.version_tag,
        authority_path=authority_path, repository=args.repo.resolve())
    capture_admission = build_capture_admission_context(
        authority=authority, manifest=manifest,
        manifest_sha256=sha256_file(stage2_path),
        authority_sha256=sha256_file(authority_path),
        scientific_run_id=stage2_binding["run_namespace"],
        processing_source_commit_sha=head,
        capture_provenance_authority_sha256=capture_provenance_authority_sha256,
        repository=args.repo.resolve())
    processability = {
        "manifest": manifest, "manifest_sha256": sha256_file(stage2_path),
        "authority_sha256": sha256_file(authority_path), "source_commit_sha": head,
        "scientific_run_id": stage2_binding["run_namespace"],
        "required_target_rows": manifest["required_target_rows_per_capture"],
        "stage1_decision": stage1_decision_document,
        "capture_admission": capture_admission,
    }
    print("CAPTURE_PROCESSING_PROVENANCE_AUTHORITY_SHA256="
          f"{capture_provenance_authority_sha256}")
    print("AUTHORIZED_CAPTURE_CRITICAL_CLOSURE_SHA256="
          f"{capture_admission.expected_capture_critical_closure_sha256}")
    print(f"PROCESSING_SOURCE_COMMIT={head}")
    print("PROCESSING_RUNTIME_CLOSURE_SHA256="
          f"{provenance_binding['processing_runtime_critical_closure_sha256']}")
    print(f"CAPTURE_AND_PROCESSING_CLOSURES_DISTINCT="
          f"{provenance_binding['closures_are_distinct']}")
    environment = {"MINEOCCLUDE_STAGE1_EVIDENCE_PATH": str(args.stage1_evidence),
                   "MINEOCCLUDE_STAGE1_DECISION_PATH": str(args.stage1_decision),
                   "MINEOCCLUDE_STAGE2_AUTHORIZATION_PATH": str(args.authorization),
                   "MINEOCCLUDE_STAGE1_MANIFEST_PATH": str(stage1_path),
                   "MINEOCCLUDE_PREOUTCOME_PROVENANCE_PATH": str(args.provenance),
                   "MINEOCCLUDE_STAGE1_PREOUTCOME_PROVENANCE_PATH":
                       str(args.stage1_provenance)}
    DurableController(manifest, args.state_dir, args.events,
        manifest_sha256=sha256_file(stage2_path), authority_sha256=sha256_file(authority_path),
        source_commit_sha=head, run_namespace=stage2_binding["run_namespace"],
        stage_role=stage2_binding["stage_role"],
        # Stage 2 reads the authority's stage-neutral OPERATIONAL restart policy,
        # not Stage 1's scientific stop_rules. It used to read
        # ``stage1_policy.stop_rules.retry_same_unit_maximum_attempts``, which
        # made Stage-2 execution depend on another stage's policy block: editing
        # a Stage-1 rule would have silently changed Stage-2 retry behaviour, and
        # Stage 2 had no field of its own to state its intent in.
        #
        # ``restart_resume`` is the right home and already existed. It is
        # explicitly stage-neutral -- its own durable_atomic_unit names "one run
        # for Stage 1; one scene/trajectory capture or one extraction unit for
        # Stage 2" -- and its ``maximum_identical_attempts`` is 3, the identical
        # value Stage 2 was already inheriting. Behaviour is therefore unchanged
        # to the number; no new retry policy is chosen here, and no scientific
        # subtree is touched.
        maximum_attempts=authority["restart_resume"]["maximum_identical_attempts"],
        capture_admission=capture_admission,
        capture_unit_probe=capture_unit_structural_probe(**processability),
        unit1_checkpoint=make_unit1_checkpoint(
            **processability,
            expected_activation_shape=list(activation_contract["expected_shape"]),
            expected_activation_dtype=activation_contract["dtype"],
            receipts_root=Path(manifest["capture_units"][0]["receipt_path"]).parent.parent),
    ).run(authorized=True, stop_after_stage1=False, environment=environment)
    return 0


if __name__ == "__main__":
    sys.exit(main())
