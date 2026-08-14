#!/usr/bin/env python3
"""Validate and durably mirror the compact Regime-A first25 result package."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import boto3
import numpy as np
import pandas as pd


REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs/status/integration/regime_a_occlusion_extraction_v0_1/first25_analysis"
BUCKET = "sagemaker-us-east-1-323206973672"
PREFIX = "mineocclude/regime_a_occlusion_extraction_v0_1/regime_a_first25_analysis_v1/8c1b8ec921ac7cd2b742b926db162d99ff877395"
FILES = (
    "analysis_input_binding.json",
    "a5_quality_visibility_confound_receipt.json",
    "collection_completion_recovery_receipt.json",
    "slice_predictions.parquet",
    "slice_primary_results.json",
    "slice_duration_results.json",
    "slice_baselines.json",
    "slice_best_k_results.json",
    "slice_secondary_target_results.json",
    "slice_all_layer_profile.json",
    "slice_null_results.json",
    "slice_bootstrap_results.json",
    "slice_validation_receipt.json",
    "continuation_adjudication.json",
    "scientific_report.md",
)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    adjudication = json.loads((OUT / "continuation_adjudication.json").read_text())
    validation = json.loads((OUT / "slice_validation_receipt.json").read_text())
    frame = pd.read_parquet(OUT / "slice_predictions.parquet")
    if adjudication["scientific_adjudication"] != "FAIL_NO_DEFENSIBLE_DECODING":
        raise RuntimeError("unexpected adjudication")
    if validation["status"] != "PASS" or len(frame) != 475 or not frame.select_dtypes(include=[np.number]).apply(np.isfinite).all().all():
        raise RuntimeError("result validation failed before durability")
    client = boto3.client("s3")
    objects = []
    for name in FILES:
        path = OUT / name
        digest = sha(path)
        key = f"{PREFIX}/{name}"
        client.put_object(Bucket=BUCKET, Key=key, Body=path.read_bytes(), ChecksumAlgorithm="SHA256")
        head = client.head_object(Bucket=BUCKET, Key=key, ChecksumMode="ENABLED")
        encoded = base64.b64encode(bytes.fromhex(digest)).decode()
        if head["ContentLength"] != path.stat().st_size or head.get("ChecksumSHA256") != encoded:
            raise RuntimeError(f"durable verification failed: {name}")
        objects.append({
            "path": str(path.relative_to(REPO)), "sha256": digest, "byte_size": path.stat().st_size,
            "s3_uri": f"s3://{BUCKET}/{key}", "s3_checksum_sha256_base64": head["ChecksumSHA256"],
            "uploaded_object_verified": True,
        })
    receipt = {
        "artifact_id": "regime-a-first25-scientific-result-durability-receipt-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "analysis_code_commit": "8c1b8ec921ac7cd2b742b926db162d99ff877395",
        "scientific_adjudication": adjudication["scientific_adjudication"],
        "durable_prefix": f"s3://{BUCKET}/{PREFIX}/",
        "object_count_excluding_receipt": len(objects),
        "objects": objects,
        "status": "PASS_ALL_COMPACT_RESULTS_DURABLE",
    }
    receipt_path = OUT / "result_durability_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    digest = sha(receipt_path)
    key = f"{PREFIX}/result_durability_receipt.json"
    client.put_object(Bucket=BUCKET, Key=key, Body=receipt_path.read_bytes(), ChecksumAlgorithm="SHA256")
    head = client.head_object(Bucket=BUCKET, Key=key, ChecksumMode="ENABLED")
    if head["ChecksumSHA256"] != base64.b64encode(bytes.fromhex(digest)).decode():
        raise RuntimeError("durability receipt verification failed")
    print(json.dumps({"status": receipt["status"], "prefix": receipt["durable_prefix"], "receipt_sha256": digest, "objects": len(objects)}, indent=2))


if __name__ == "__main__":
    main()
