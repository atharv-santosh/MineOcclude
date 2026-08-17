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
    Decision, DurableController, Stage1Evaluator, atomic_write_json, bind_manifest,
    RUNTIME_CRITICAL_SOURCE_PATHS, canonical_payload_sha256, load_json, require_preoutcome_provenance,
    require_stage2_authorization, require_stage_manifest_binding,
    runtime_critical_source_closure_sha256, sha256_file, stage_run_inventory_sha256,
)
from mineocclude.prospective.package_binding import (  # noqa: E402
    PackageBinding, resolve_package_binding,
)


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
    run2.add_argument("--authorization", type=Path, required=True)
    run2.add_argument("--provenance", type=Path, required=True)
    run2.add_argument("--state-dir", type=Path, required=True)
    run2.add_argument("--events", type=Path, required=True)
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
        decision = Stage1Evaluator(authority, manifest, authority_sha256=sha256_file(authority_path),
                                   manifest_sha256=sha256_file(stage1_path)).evaluate(load_json(args.evidence))
        atomic_write_json(args.output, decision.to_dict(authority_sha256=sha256_file(authority_path),
            manifest_sha256=sha256_file(stage1_path), evidence_sha256=sha256_file(args.evidence)))
        return 0 if decision.status == "PASS" else 2
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
            manifest_sha256=sha256_file(stage1_path), evidence_sha256=evidence_sha))
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
        current_source_commit=head, preoutcome_provenance_path=args.provenance)
    environment = {"MINEOCCLUDE_STAGE1_EVIDENCE_PATH": str(args.stage1_evidence),
                   "MINEOCCLUDE_STAGE1_DECISION_PATH": str(args.stage1_decision),
                   "MINEOCCLUDE_STAGE2_AUTHORIZATION_PATH": str(args.authorization),
                   "MINEOCCLUDE_STAGE1_MANIFEST_PATH": str(stage1_path),
                   "MINEOCCLUDE_PREOUTCOME_PROVENANCE_PATH": str(args.provenance)}
    DurableController(manifest, args.state_dir, args.events,
        manifest_sha256=sha256_file(stage2_path), authority_sha256=sha256_file(authority_path),
        source_commit_sha=head, run_namespace=stage2_binding["run_namespace"],
        stage_role=stage2_binding["stage_role"],
        maximum_attempts=authority["stage1_policy"]["stop_rules"]["retry_same_unit_maximum_attempts"]
    ).run(authorized=True, stop_after_stage1=False, environment=environment)
    return 0


if __name__ == "__main__":
    sys.exit(main())
