"""Build a stable direct-provenance index from a validated A/E registry."""

from __future__ import annotations

import argparse
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
        description="Create a machine-readable artifact index without path identity."
    )
    parser.add_argument("rollout_manifest", type=Path)
    parser.add_argument("registry", type=Path)
    parser.add_argument("output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rollout_manifest, rollout_manifest_hash = load_json_with_sha256(
        args.rollout_manifest
    )
    registry, registry_hash = load_json_with_sha256(args.registry)
    index = RegistryIndex(rollout_manifest, registry)
    document = {
        "artifact_index_schema_version": "person-e-artifact-index-v0.1",
        "rollout_manifest_hash": rollout_manifest_hash,
        "registry_hash": registry_hash,
        "rows": index.artifact_index(),
        "provenance_qa": index.provenance_qa_report(),
    }
    write_json_exclusive(args.output, document)


if __name__ == "__main__":
    main()
