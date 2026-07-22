"""Trace a rollout or artifact through the frozen A/E registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.experiments.registry import (  # noqa: E402
    RegistryIndex,
    load_json_with_sha256,
    write_json_exclusive,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trace one explicit rollout_id or artifact_id through run lineage."
    )
    parser.add_argument("rollout_manifest", type=Path)
    parser.add_argument("registry", type=Path)
    parser.add_argument("subject_id")
    parser.add_argument(
        "--subject-type",
        choices=("rollout", "artifact"),
        help="Required only when rollout and artifact namespaces share an ID.",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rollout_manifest, rollout_manifest_hash = load_json_with_sha256(
        args.rollout_manifest
    )
    registry, registry_hash = load_json_with_sha256(args.registry)
    report = RegistryIndex(rollout_manifest, registry).provenance_report(
        args.subject_id,
        subject_type=args.subject_type,
    )
    report["rollout_manifest_hash"] = rollout_manifest_hash
    report["registry_hash"] = registry_hash
    if args.output is None:
        json.dump(report, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        write_json_exclusive(args.output, report)


if __name__ == "__main__":
    main()
