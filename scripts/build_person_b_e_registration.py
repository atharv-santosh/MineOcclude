"""Build E-validatable immutable-registry records for B artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.analysis.handoffs import build_e_registration_request  # noqa: E402
from mineocclude.experiments.registry import (  # noqa: E402
    load_json_with_sha256,
    write_json_exclusive,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("artifacts", nargs="+", type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--checkpoint-hash", required=True)
    parser.add_argument("--data-identity-hash", required=True)
    parser.add_argument("--preprocess-hash", required=True)
    parser.add_argument("--environment-hash", required=True)
    parser.add_argument("--started-at", required=True)
    parser.add_argument("--ended-at", required=True)
    parser.add_argument("--uri-prefix", required=True)
    parser.add_argument("--git-dirty", action="store_true")
    parser.add_argument(
        "--external-artifact-map",
        type=Path,
        help="JSON mapping from upstream content hashes to E artifact IDs.",
    )
    parser.add_argument(
        "--command",
        nargs="+",
        required=True,
        help="Exact command tokens used for the B run.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artifacts = []
    artifact_bytes_by_id = {}
    for path in args.artifacts:
        payload = path.read_bytes()
        artifact = json.loads(payload.decode("utf-8"))
        artifacts.append(artifact)
        artifact_bytes_by_id[artifact["artifact_id"]] = payload
    external_artifact_map = (
        load_json_with_sha256(args.external_artifact_map)[0]
        if args.external_artifact_map is not None
        else None
    )
    request = build_e_registration_request(
        artifacts,
        run_id=args.run_id,
        checkpoint_hash=args.checkpoint_hash,
        data_identity_hash=args.data_identity_hash,
        preprocess_hash=args.preprocess_hash,
        environment_hash=args.environment_hash,
        command=args.command,
        started_at=args.started_at,
        ended_at=args.ended_at,
        uri_prefix=args.uri_prefix,
        git_dirty=args.git_dirty,
        external_artifact_ids_by_hash=external_artifact_map,
        artifact_bytes_by_id=artifact_bytes_by_id,
    )
    write_json_exclusive(args.output, request)


if __name__ == "__main__":
    main()
