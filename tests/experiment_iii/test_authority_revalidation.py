"""A0 revalidation of evidence bound to a predecessor authority.

Amendment 5 moved ``AUTHORITY_SHA256``, so every P0 and P1 artifact -- all
produced under v1.7 -- fell under A0's invalidation scope: "invalidated and must
be **revalidated**". The word matters. Regenerating would have meant re-running a
valid 252-unit P0 campaign because a bootstrap seed was named; relaxing the drift
check would have let genuinely stale evidence through. Revalidation is the
authority's own third option, and these tests pin down that it proves something
rather than merely asserting it.
"""

from __future__ import annotations

import json

import pytest

from mineocclude.experiment_iii.authority import (
    FROZEN_AUTHORITY_SHA256,
    PREDECESSOR_AUTHORITY_FREEZE_COMMIT,
    PREDECESSOR_AUTHORITY_SHA256,
    REPOSITORY_ROOT,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.p0_analysis import load_selected_ladder
from mineocclude.experiment_iii.revalidation import (
    AUTHORITY_LINEAGE,
    REVALIDATION_INDEX_PATH,
    authority_delta,
    build_revalidation_receipt,
    load_revalidation_index,
    resolve_authority_binding,
)

LADDER = REPOSITORY_ROOT / "docs" / "experiment_iii" / "p0" / "P0_SELECTED_LADDER.json"


def test_the_amendment_touched_only_the_statistics_root() -> None:
    """The claim every P0/P1 revalidation rests on, computed from git."""
    delta = authority_delta(PREDECESSOR_AUTHORITY_FREEZE_COMMIT)
    assert delta["changed_scientific_roots"] == ["statistics"]
    for root in ("p0_rve", "conditions", "apparatus", "cohort", "extraction",
                 "readout", "representations", "fir", "visibility_semantics"):
        assert root not in delta["changed_scientific_roots"]


def test_the_lineage_is_the_recognised_predecessors_only() -> None:
    shas = [sha for sha, _commit in AUTHORITY_LINEAGE]
    assert PREDECESSOR_AUTHORITY_SHA256 in shas
    assert FROZEN_AUTHORITY_SHA256 not in shas


def test_foreign_provenance_is_never_revalidatable() -> None:
    """A hash outside the frozen lineage is not a predecessor, it is a stranger."""
    scratch = REPOSITORY_ROOT / "docs" / "experiment_iii" / "p0" / "_foreign_probe.json"
    scratch.write_text(
        json.dumps(
            {"provenance": {"authority_binding": {"AUTHORITY_SHA256": "0" * 64}}}
        ),
        encoding="utf-8",
    )
    try:
        with pytest.raises(ExperimentIIIError) as error:
            build_revalidation_receipt(
                {scratch.relative_to(REPOSITORY_ROOT).as_posix(): ("apparatus",)}
            )
        assert error.value.blocker == "PROVENANCE_AUTHORITY_DRIFT"
        assert "not a recognised predecessor" in error.value.message
    finally:
        scratch.unlink(missing_ok=True)


def test_a_missing_artifact_cannot_be_revalidated() -> None:
    with pytest.raises(ExperimentIIIError) as error:
        build_revalidation_receipt({"docs/experiment_iii/p0/nope.json": ("apparatus",)})
    assert error.value.blocker == "PROVENANCE_BINDING_MISSING"


def test_an_artifact_depending_on_the_changed_root_is_refused() -> None:
    """Revalidation must refuse exactly what it cannot honestly cover.

    If a P0 artifact really did consume ``statistics``, the amendment would have
    invalidated it for real and it would need regenerating, not a receipt.
    """
    with pytest.raises(ExperimentIIIError) as error:
        build_revalidation_receipt(
            {"docs/experiment_iii/p0/P0_SELECTED_LADDER.json": ("statistics",)}
        )
    assert error.value.blocker == "PROVENANCE_AUTHORITY_DRIFT"
    assert "must be regenerated, not revalidated" in error.value.message


def test_an_already_current_artifact_is_refused_a_record() -> None:
    """A record implying revalidation happened where none was needed is a lie."""
    index = REVALIDATION_INDEX_PATH
    if not index.is_file():
        pytest.skip("no revalidation index banked")
    with pytest.raises(ExperimentIIIError) as error:
        build_revalidation_receipt({
            index.relative_to(REPOSITORY_ROOT).as_posix(): ("apparatus",)
        })
    assert error.value.blocker == "PROVENANCE_BINDING_MISSING"


def test_the_banked_index_covers_the_p0_ladder() -> None:
    records = load_revalidation_index()
    assert records, "the revalidation index is empty or bound to another authority"
    artifacts = {record["artifact"] for record in records.values()}
    assert "docs/experiment_iii/p0/P0_SELECTED_LADDER.json" in artifacts
    for record in records.values():
        assert record["revalidated_against_authority_sha256"] == FROZEN_AUTHORITY_SHA256
        assert record["historical_authority_sha256"] != FROZEN_AUTHORITY_SHA256
        assert record["dependency_intersection_empty"] is True
        assert record["bytes_modified_by_revalidation"] is False


def test_the_ladder_loads_again_under_the_successor_authority() -> None:
    """The concrete thing that was broken: A7 could not read its own ladder."""
    ladder = load_selected_ladder(LADDER)
    assert set(ladder) == {"L1", "L2", "L3"}
    assert len(set(ladder.values())) == 3


def test_drift_without_a_record_still_fails_closed(tmp_path) -> None:
    body = json.loads(LADDER.read_text(encoding="utf-8"))
    body["provenance"]["authority_binding"]["AUTHORITY_SHA256"] = "0" * 64
    forged = tmp_path / "forged.json"
    forged.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(ExperimentIIIError) as error:
        resolve_authority_binding(forged, "0" * 64)
    assert error.value.blocker == "PROVENANCE_AUTHORITY_DRIFT"


def test_an_edited_artifact_loses_its_revalidation(tmp_path) -> None:
    """Keyed on canonical content: change a value and the record stops matching."""
    body = json.loads(LADDER.read_text(encoding="utf-8"))
    body["L2"] = "minecraft:stone"
    edited = tmp_path / "edited.json"
    edited.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(ExperimentIIIError) as error:
        resolve_authority_binding(
            edited, body["provenance"]["authority_binding"]["AUTHORITY_SHA256"]
        )
    assert error.value.blocker == "PROVENANCE_AUTHORITY_DRIFT"


def test_a_faithful_copy_keeps_its_revalidation(tmp_path) -> None:
    """Re-serialising is not editing; formatting is not scientific content."""
    body = json.loads(LADDER.read_text(encoding="utf-8"))
    copy = tmp_path / "copy.json"
    copy.write_text(json.dumps(body, indent=4), encoding="utf-8")
    resolved = resolve_authority_binding(
        copy, body["provenance"]["authority_binding"]["AUTHORITY_SHA256"]
    )
    assert resolved["binding"] == "REVALIDATED_PREDECESSOR"
    assert resolved["revalidated"] is True
