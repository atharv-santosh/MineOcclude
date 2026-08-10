from __future__ import annotations

import importlib.util
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_large_scale_no_wall_campaign.py"
SPEC = importlib.util.spec_from_file_location("p3_campaign", SCRIPT)
assert SPEC and SPEC.loader
p3 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p3)


@pytest.fixture(scope="module")
def authority():
    return p3.CampaignAuthority(p3.DEFAULT_CAMPAIGN)


def test_locked_stage_sizes_and_cumulative_targets(authority):
    assert {stage: len(authority.stage_specs(stage)) for stage in "ABCD"} == {
        "A": 12,
        "B": 36,
        "C": 36,
        "D": 36,
    }
    assert {stage: len(p3.cumulative_specs(authority, stage)) for stage in "ABCD"} == {
        "A": 12,
        "B": 48,
        "C": 84,
        "D": 120,
    }


def test_final_campaign_has_exact_balanced_cells(authority):
    specs = p3.cumulative_specs(authority, "D")
    assert Counter(row["layout_id"] for row in specs) == {
        f"L{index:02d}": 20 for index in range(1, 7)
    }
    assert Counter((row["layout_id"], row["direction"]) for row in specs) == {
        (f"L{index:02d}", direction): 10
        for index in range(1, 7)
        for direction in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT")
    }
    assert set(
        Counter(
            (row["layout_id"], row["direction"], row["profile_family"]) for row in specs
        ).values()
    ) == {2}


def test_every_spec_maps_to_one_locked_stage(authority):
    assert Counter(authority.stage_by_spec.values()) == {
        "A": 12,
        "B": 36,
        "C": 36,
        "D": 36,
    }
    with pytest.raises(p3.CampaignError, match="unplanned spec"):
        authority.stage_for("replacement_spec_is_forbidden")


def test_dry_run_through_d_is_capture_free_and_balanced(authority):
    result = p3.dry_run(authority, "D")
    assert result["status"] == "PASS"
    assert result["cumulative_count"] == 120
    assert result["per_layout"] == {f"L{index:02d}": 20 for index in range(1, 7)}
    assert result["unique_spec_ids"] == result["unique_spec_hashes"] == 120


def test_p2_stage_a_upload_prefix_is_stable(authority):
    spec = authority.stage_specs("A")[0]
    assert authority.stage_for(spec["trajectory_spec_id"]) == "A"
    expected = (
        p3.DEFAULT_S3_PREFIX
        + "stage_a/attempts/"
        + spec["trajectory_spec_id"]
        + "/attempt_01/"
    )
    assert expected.endswith("/attempt_01/")
