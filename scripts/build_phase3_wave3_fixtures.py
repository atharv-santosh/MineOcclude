"""Build or verify the small Person A Phase 3 Wave 3 token-map fixture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.models import _mineworld_adapter_wave3 as wave3
from mineocclude.models.mineworld_adapter import (
    FrameIdentity,
    FrameTokenMap,
    FrameTokenSpan,
)

FIXTURE_VERSION = "person-a-phase3-wave3-v1.0"


def build_fixture() -> dict[str, object]:
    identities = tuple(
        FrameIdentity(SCHEMA_VERSION, "wave3-trajectory", index)
        for index in range(40, 43)
    )
    tokens: list[int] = []
    spans = []
    for pair_index, identity in enumerate(identities):
        start = len(tokens)
        tokens.extend(
            (pair_index + token_index) % wave3.VISUAL_VOCABULARY_SIZE
            for token_index in range(336)
        )
        action_start = len(tokens)
        tokens.extend(range(8192, 8203))
        end = len(tokens)
        spans.append(
            FrameTokenSpan(
                identity=identity,
                pair_index=pair_index,
                visual_positions=tuple(range(start, action_start)),
                action_positions=tuple(range(action_start, end)),
                accepted_pair_index=pair_index,
                pair_start=start,
                pair_end_exclusive=end,
                causal_predecessor=(
                    identities[pair_index - 1] if pair_index else None
                ),
                causal_successor=(
                    identities[pair_index + 1]
                    if pair_index + 1 < len(identities)
                    else None
                ),
            )
        )
    frame_token_map = FrameTokenMap(
        schema_version=SCHEMA_VERSION,
        trajectory_id="wave3-trajectory",
        sequence_length=len(tokens),
        spans=tuple(spans),
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "fixture_version": FIXTURE_VERSION,
        "classification": "cpu_fake_official_boundary",
        "source_revision_inspected": wave3.PINNED_SOURCE_REVISION,
        "limitations": (
            "Visual IDs are deterministic fake-boundary values; this fixture "
            "does not claim real VAE certification."
        ),
        "expected": {
            "frame_token_map": wave3._compact_map_payload(frame_token_map),
            "token_sha256": wave3._token_sha256(tuple(tokens)),
            "frame_token_map_sha256": wave3._frame_token_map_sha256(
                frame_token_map
            ),
            "included_model_frame_indices": [40, 41, 42],
            "excluded_model_frame_indices": [],
            "sequence_length": 1041,
        },
    }


def serialized_fixture() -> str:
    return json.dumps(
        build_fixture(),
        indent=2,
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
    ) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = serialized_fixture()
    if args.check:
        if not args.output.is_file():
            raise SystemExit(f"fixture does not exist: {args.output}")
        if args.output.read_text(encoding="utf-8") != expected:
            raise SystemExit("fixture differs from deterministic regeneration")
        print(f"PASS: {args.output}")
        return 0
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite existing fixture: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(expected, encoding="utf-8", newline="\n")
    print(f"WROTE: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
