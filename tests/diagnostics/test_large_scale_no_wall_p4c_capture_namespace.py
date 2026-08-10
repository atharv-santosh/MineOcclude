from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_large_scale_no_wall_campaign.py"
SPEC = importlib.util.spec_from_file_location("p4c_campaign_runner", SCRIPT)
assert SPEC and SPEC.loader
p4c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p4c)


@pytest.fixture(scope="module")
def authority():
    return p4c.CampaignAuthority(p4c.PACKAGE / "capture_campaign_v2.json")


def test_v2_authority_and_dry_run_are_exact(authority):
    assert authority.is_repaired_v2 is True
    result = p4c.dry_run(authority, "D")
    assert result["status"] == "PASS"
    assert result["cumulative_count"] == 120
    assert result["per_layout"] == {f"L{index:02d}": 20 for index in range(1, 7)}
    assert result["unique_spec_ids"] == 120
    assert result["unique_spec_hashes"] == 120


def test_v2_execution_namespace_is_separate_and_exact(authority):
    p4c.validate_execution_namespace(
        authority,
        p4c.DEFAULT_V2_LEDGER,
        p4c.DEFAULT_V2_RUNTIME_ROOT,
        p4c.DEFAULT_V2_S3_PREFIX,
    )
    assert p4c.DEFAULT_V2_LEDGER != p4c.DEFAULT_LEDGER
    assert p4c.DEFAULT_V2_RUNTIME_ROOT != p4c.DEFAULT_RUNTIME_ROOT
    assert p4c.DEFAULT_V2_S3_PREFIX != p4c.DEFAULT_S3_PREFIX
    assert p4c.DEFAULT_V2_S3_PREFIX.startswith(p4c.DEFAULT_S3_PREFIX)


@pytest.mark.parametrize("field", ["ledger", "runtime_root", "s3_prefix"])
def test_v2_refuses_every_v1_storage_namespace(authority, field):
    values = {
        "ledger": p4c.DEFAULT_V2_LEDGER,
        "runtime_root": p4c.DEFAULT_V2_RUNTIME_ROOT,
        "s3_prefix": p4c.DEFAULT_V2_S3_PREFIX,
    }
    v1 = {
        "ledger": p4c.DEFAULT_LEDGER,
        "runtime_root": p4c.DEFAULT_RUNTIME_ROOT,
        "s3_prefix": p4c.DEFAULT_S3_PREFIX,
    }
    values[field] = v1[field]
    with pytest.raises(p4c.CampaignError, match=f"V2 {field} namespace mismatch"):
        p4c.validate_execution_namespace(
            authority,
            values["ledger"],
            values["runtime_root"],
            values["s3_prefix"],
        )


def test_v1_authority_retains_original_namespaces():
    authority = p4c.CampaignAuthority(p4c.DEFAULT_CAMPAIGN)
    assert authority.is_repaired_v2 is False
    p4c.validate_execution_namespace(
        authority,
        p4c.DEFAULT_LEDGER,
        p4c.DEFAULT_RUNTIME_ROOT,
        p4c.DEFAULT_S3_PREFIX,
    )
