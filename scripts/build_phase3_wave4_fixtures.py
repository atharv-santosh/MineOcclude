"""Rebuild the small deterministic Person A Phase 3 Wave 4 fixture."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "tests"
    / "fixtures"
    / "models"
    / "phase3_wave4_failure_matrix.json"
)
CASES = (
    "source_revision_mismatch",
    "asset_revision_mismatch",
    "main_checkpoint_sha256_mismatch",
    "vae_checkpoint_sha256_mismatch",
    "model_config_sha256_mismatch",
    "adapter_code_sha256_mismatch",
    "preprocessing_profile_mismatch",
    "action_converter_identity_mismatch",
    "tokenization_profile_mismatch",
    "schema_version_mismatch",
    "adapter_api_version_mismatch",
    "accepted_manifest_sha256_mismatch",
    "runtime_identity_mismatch",
    "token_sha256_mismatch",
    "frame_token_map_sha256_mismatch",
    "precision_mismatch",
    "device_mismatch",
    "unsafe_output_path",
)


def build() -> bytes:
    document = {
        "fixture_version": "person-a-phase3-wave4-v1.0",
        "schema_version": "1.0",
        "operation": "fail_before_expensive_work",
        "cases": list(CASES),
        "expensive_dependencies": [
            "runtime_loader",
            "vae_tokenizer",
            "teacher_executor",
            "rollout_executor",
        ],
        "expected": {
            "all_cases_rejected": True,
            "expensive_dependency_calls": 0,
        },
    }
    return (
        json.dumps(document, indent=2, sort_keys=False, ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def main() -> int:
    OUTPUT.write_bytes(build())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
