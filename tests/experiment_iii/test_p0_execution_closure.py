"""A4 end-to-end closure, physical evidence binding, and sentinel runtime wiring.

Every test here would have FAILED on the source state the v1.6 pre-execution
readiness audit examined. They are deliberately written against the *authority*
rather than against the implementation, and several assert **runtime
reachability** rather than behaviour, because the defect they guard against was
not a wrong answer -- it was a correct library function with no production call
site.

Named checks: A.14 (RVE and P0 machinery), A.15 (sentinels and capture order),
A.29 (execution, resume and evidence binding).
"""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

import numpy as np
import pytest

from mineocclude.experiment_iii import p0_analysis, sentinels
from mineocclude.experiment_iii.artifact_inventory import (
    resolve_artifact_path,
    stage_exit_check_fs,
)
from mineocclude.experiment_iii.authority import (
    AUTHORITY_FREEZE_COMMIT,
    PREDECESSOR_AUTHORITY_FREEZE_COMMIT,
    verify_authority_binding,
)
from mineocclude.experiment_iii.capture_driver import FrameSink, prepare_condition
from mineocclude.experiment_iii.capture_evidence import (
    evidence_binding_matrix,
    join_frames_to_ticks,
    png_dimensions,
    read_capture_complete,
    read_client_tick_ledger,
)
from mineocclude.experiment_iii.capture_liveness import (
    LivenessProbe,
    verify_unit_liveness,
)
from mineocclude.experiment_iii.conditions import ELIGIBLE_STAINED_GLASS
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.p0_analysis import (
    A4_ARTIFACTS,
    P0_VALIDITY_RULE_IDS,
    CellFrames,
    analyse_p0,
    load_selected_ladder,
    write_a4_artifacts,
)
from mineocclude.experiment_iii.p0_campaign import campaign_manifest
from mineocclude.experiment_iii.placements import sentinel_placement_indices

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SRC = REPOSITORY_ROOT / "src" / "mineocclude" / "experiment_iii"
SCRIPTS = REPOSITORY_ROOT / "scripts" / "experiment_iii"

# --------------------------------------------------------------------------
# Synthetic P0: noise-free, so every RVE is exactly the amplitude squared
# --------------------------------------------------------------------------

HEIGHT, WIDTH = 24, 32
FRAMES_PER_STATE = 4
BLOCKS = 2
PLACEMENTS = list(range(9))

#: Twelve candidate RVEs, chosen so exactly one triple sits on the frozen target
#: (0.725, 0.425, 0.165) and every zone, separation and ordering rule passes.
CANDIDATE_RVE = {
    "minecraft:white_stained_glass": 0.95,
    "minecraft:orange_stained_glass": 0.80,
    "minecraft:light_blue_stained_glass": 0.725,
    "minecraft:yellow_stained_glass": 0.66,
    "minecraft:lime_stained_glass": 0.52,
    "minecraft:gray_stained_glass": 0.425,
    "minecraft:light_gray_stained_glass": 0.33,
    "minecraft:cyan_stained_glass": 0.24,
    "minecraft:blue_stained_glass": 0.165,
    "minecraft:brown_stained_glass": 0.11,
    "minecraft:green_stained_glass": 0.30,
    "minecraft:black_stained_glass": 0.06,
}
EXPECTED_LADDER = {
    "L1": "minecraft:light_blue_stained_glass",
    "L2": "minecraft:gray_stained_glass",
    "L3": "minecraft:blue_stained_glass",
}


def _blob(placement: int) -> np.ndarray:
    """A compact 'target' region, at a placement-dependent column."""
    field = np.zeros((HEIGHT, WIDTH, 3), dtype=np.float64)
    left = 3 + placement * 2
    field[9:15, left : left + 6, :] = 0.5
    return field


def _cell(condition: str, placement: int, block: int, amplitude: float) -> CellFrames:
    """One (condition, placement, block) cell with zero renderer noise.

    ``P - A`` is exactly ``amplitude * blob``, so ``D`` scales as ``amplitude**2``
    and ``RVE = E / E(L0) == amplitude**2`` exactly. That makes every assertion
    below about the frozen arithmetic rather than about a tolerance.
    """
    background = np.full((HEIGHT, WIDTH, 3), 0.2, dtype=np.float64)
    absent = background
    present = background + amplitude * _blob(placement)
    return CellFrames(
        condition_key=condition,
        placement_index=placement,
        block_index=block,
        present=tuple(present.copy() for _ in range(FRAMES_PER_STATE)),
        absent=tuple(absent.copy() for _ in range(FRAMES_PER_STATE)),
        frame_paths=tuple(
            f"{condition}/p{placement}/b{block}/{i:06d}.png"
            for i in range(FRAMES_PER_STATE * 2)
        ),
        frame_hashes=tuple(
            f"{condition}{placement}{block}{i}".ljust(64, "0")
            for i in range(FRAMES_PER_STATE * 2)
        ),
    )


def _synthetic_cells(rve_by_condition: dict[str, float] | None = None):
    values = dict(CANDIDATE_RVE if rve_by_condition is None else rve_by_condition)
    cells = []
    for placement in PLACEMENTS:
        for block in range(BLOCKS):
            cells.append(_cell("L0", placement, block, 1.0))
            cells.append(_cell("L4", placement, block, np.sqrt(0.02)))
            for condition in ELIGIBLE_STAINED_GLASS:
                cells.append(
                    _cell(condition, placement, block, float(np.sqrt(values[condition])))
                )
    return cells


@pytest.fixture(scope="module")
def passing_analysis():
    return analyse_p0(_synthetic_cells())


# ==========================================================================
# F-01 -- the P0 analysis half exists, is correct, and is REACHABLE
# ==========================================================================


def test_a14_the_p0_runner_reaches_the_rve_analysis() -> None:
    """--execute must not stop after capturing 252 units.

    The audited runner captured every unit and returned, so seven of A4's eight
    outputs had no producer and A4's exit condition was unreachable. This asserts
    the production call sites exist in the runner itself, not in a test.
    """
    source = (SCRIPTS / "run_p0_rve_calibration.py").read_text(encoding="utf-8")
    for symbol in ("analyse_p0", "write_a4_artifacts", "load_unit_frames"):
        assert symbol in source, f"{symbol} is not called from the P0 runner"
    assert "close_p0_stage(" in source
    # The capture loop must be followed by stage closure, not by a bare return.
    assert source.index("capture_campaign(") < source.index("close_p0_stage(")


def test_a14_every_frozen_rve_primitive_has_a_production_call_site() -> None:
    """Each of these had a call-site census of exactly zero outside rve.py."""
    analysis = (SRC / "p0_analysis.py").read_text(encoding="utf-8")
    for symbol in (
        "srgb_to_linear",
        "robust_median_image",
        "placement_mask",
        "split_half_noise",
        "excess_energy",
        "aggregate_placement",
        "aggregate_condition",
        "select_ladder",
        "l0_noise_threshold",
        "background_gate",
    ):
        assert symbol in analysis, f"{symbol} has no production call site"


def test_a14_analysis_selects_the_frozen_ladder(passing_analysis) -> None:
    assert passing_analysis["P0_RESULT"] == "P0_PASS"
    assert passing_analysis["PRODUCTION_AUTHORIZED"] is True
    selected = passing_analysis["selection"]["selected"]
    assert {k: selected[k] for k in ("L1", "L2", "L3")} == EXPECTED_LADDER


def test_a14_rve_is_exactly_the_frozen_normalisation(passing_analysis) -> None:
    """RVE(L0) == 1 exactly, and each candidate reproduces its amplitude squared."""
    medians = passing_analysis["condition_medians"]
    assert medians["L0"] == pytest.approx(1.0, abs=1e-12)
    for condition, expected in CANDIDATE_RVE.items():
        assert medians[condition] == pytest.approx(expected, abs=1e-9)
    # L4 is measured, not forced to zero (authority 7.4).
    assert medians["L4"] == pytest.approx(0.02, abs=1e-9)
    assert medians["L4"] > 0.0


def test_a14_the_search_is_exhaustive_over_1320_permutations(passing_analysis) -> None:
    assert passing_analysis["selection"]["evaluated_triples"] == 12 * 11 * 10


def test_a14_all_nine_validity_rules_are_evaluated_from_production(
    passing_analysis,
) -> None:
    """No rule may exist only in tests, and none may be silently skipped."""
    record = passing_analysis["validity_records"][0]
    reported = [rule["rule_id"] for rule in record["rules"]]
    for rule_id in P0_VALIDITY_RULE_IDS:
        assert rule_id in reported
    assert "bootstrap_lower_bounds_positive" in reported
    for rule in record["rules"]:
        assert rule["outcome"] in ("PASS", "FAIL")
        assert "reference" in rule


def test_a14_no_valid_ladder_is_reachable_from_the_analysis() -> None:
    """Twelve indistinguishable candidates cannot separate, so no ladder exists."""
    flat = {name: 0.5 for name in ELIGIBLE_STAINED_GLASS}
    analysis = analyse_p0(_synthetic_cells(flat))
    # Authority 7.6 names the outcome P0_NO_VALID_LADDER; that exact string,
    # not a second spelling of it, is what reaches the artifacts and the operator.
    assert analysis["P0_RESULT"] == "P0_NO_VALID_LADDER"
    assert analysis["PRODUCTION_AUTHORIZED"] is False
    assert analysis["selection"]["selected"] is None
    # An approximate ladder is never returned in place of a refusal.
    assert "L1" not in analysis["selection"]


def test_a14_no_valid_ladder_names_the_frozen_blocker_codes() -> None:
    """These A4 blocker codes previously had no producer anywhere."""
    flat = {name: 0.5 for name in ELIGIBLE_STAINED_GLASS}
    analysis = analyse_p0(_synthetic_cells(flat))
    codes = {row["blocker"] for row in analysis["blockers"]}
    assert "RVE_BOOTSTRAP_LOWER_BOUND_NOT_POSITIVE" in codes
    assert "RVE_ORDER_UNSTABLE" in codes


def test_a14_an_incomplete_campaign_cannot_be_analysed() -> None:
    cells = _synthetic_cells()
    with pytest.raises(ExperimentIIIError) as error:
        analyse_p0(cells[:-1])
    assert error.value.blocker == "P0_TECHNICAL_FAIL"


def test_a14_a_candidate_outside_the_roster_is_refused() -> None:
    with pytest.raises(ExperimentIIIError) as error:
        analyse_p0(_synthetic_cells(), candidates=["minecraft:red_stained_glass"])
    assert error.value.blocker == "P0_CANDIDATE_ID_UNSUPPORTED"


def test_a14_the_mask_is_derived_from_l0_only_and_shared(passing_analysis) -> None:
    masks = passing_analysis["mask_records"]
    assert len(masks) == 9
    for record in masks:
        assert record["source"] == "L0_PRESENT_MINUS_ABSENT_ABOVE_FROZEN_NOISE_THRESHOLD"
        assert record["shared_across_all_candidates"] is True
        assert record["per_candidate_mask_forbidden"] is True
        assert record["dilation_pixels"] == 2
        assert record["l0_noise_threshold"]["candidate_frames_consumed"] is False
        assert record["l0_noise_threshold"]["tunable_constants"] == 0
        assert 0.0 < record["mask_fraction_of_frame"] <= 0.5


# ==========================================================================
# The eight A4 artifacts, and P0_SELECTION_RECEIPT in particular
# ==========================================================================


def _p0_tree(base: Path) -> tuple[Path, Path]:
    """A temporary Experiment III tree.

    The namespace guard refuses any write outside ``docs/experiment_iii/``, and
    that guard stays fully active here: these tests exercise the real producer
    against a temporary root rather than disabling the check.
    """
    root = Path(base)
    return root, root / "docs" / "experiment_iii" / "p0"


@pytest.fixture(scope="module")
def written_artifacts(passing_analysis, tmp_path_factory):
    root, out = _p0_tree(tmp_path_factory.mktemp("p0"))
    digests = write_a4_artifacts(
        passing_analysis,
        out_dir=out,
        capture_manifest=campaign_manifest(),
        campaign_state_sha256="c" * 64,
        namespace_root=root,
        host_receipt={"qualified": True, "system": "Linux"},
        image_inventory=[
            {"unit_id": "L0__p0__b0", "frame_sha256": "a" * 64, "server_tick": 1}
        ],
    )
    return out, digests


def test_a29_every_expected_a4_artifact_has_a_producer(written_artifacts) -> None:
    """Seven of the eight had no producer anywhere in the repository."""
    out, digests = written_artifacts
    for name in A4_ARTIFACTS:
        assert (out / name).is_file(), f"{name} was not produced"
        assert digests[name]
    assert len(A4_ARTIFACTS) == 8


def test_a29_p0_selection_receipt_proves_the_whole_decision(written_artifacts) -> None:
    """P2 must be able to consume this without reconstructing a decision."""
    out, digests = written_artifacts
    receipt = json.loads((out / "P0_SELECTION_RECEIPT.json").read_text(encoding="utf-8"))
    provenance = receipt["provenance"]
    assert provenance["authority_binding"]["AUTHORITY_SHA256"]
    assert provenance["authority_freeze_commit"] == AUTHORITY_FREEZE_COMMIT
    assert provenance["source_closure"]
    assert provenance["p0_campaign_state_sha256"]
    assert provenance["capture_manifest_sha256"]
    assert provenance["rve_implementation"] == "mineocclude.experiment_iii.rve"
    assert receipt["P0_RESULT"] == "P0_PASS"
    assert receipt["selected_ladder"]["L1"] == EXPECTED_LADDER["L1"]
    assert receipt["capture_host_receipt"]["qualified"] is True
    assert receipt["validity_records"]
    assert receipt["tie_break_evidence"]["rule"]
    assert receipt["is_provisional"] is False
    assert receipt["model_inference_used"] is False
    assert receipt["outcome_blind"] is True
    # It binds the digest of every artifact it depends on.
    for name in A4_ARTIFACTS:
        if name != "P0_SELECTION_RECEIPT.json":
            assert receipt["artifact_sha256"][name] == digests[name]


def test_a29_the_selection_receipt_is_written_last(written_artifacts) -> None:
    """It is A4's exit condition and must not describe an unwritten state."""
    out, _ = written_artifacts
    receipt = json.loads((out / "P0_SELECTION_RECEIPT.json").read_text(encoding="utf-8"))
    assert set(receipt["artifact_sha256"]) >= set(A4_ARTIFACTS) - {
        "P0_SELECTION_RECEIPT.json"
    }


def test_a29_selected_ladder_is_consumable_and_no_ladder_is_not(
    written_artifacts, tmp_path
) -> None:
    out, _ = written_artifacts
    assert load_selected_ladder(out / "P0_SELECTED_LADDER.json") == EXPECTED_LADDER

    flat = {name: 0.5 for name in ELIGIBLE_STAINED_GLASS}
    root, failed = _p0_tree(tmp_path)
    write_a4_artifacts(
        analyse_p0(_synthetic_cells(flat)),
        out_dir=failed,
        capture_manifest=campaign_manifest(),
        campaign_state_sha256="d" * 64,
        namespace_root=root,
    )
    with pytest.raises(ExperimentIIIError) as error:
        load_selected_ladder(failed / "P0_SELECTED_LADDER.json")
    assert error.value.blocker == "P0_NO_VALID_LADDER"


def test_a29_no_valid_ladder_derives_no_sentinel_envelope(tmp_path) -> None:
    flat = {name: 0.5 for name in ELIGIBLE_STAINED_GLASS}
    root, out = _p0_tree(tmp_path)
    write_a4_artifacts(
        analyse_p0(_synthetic_cells(flat)),
        out_dir=out,
        capture_manifest=campaign_manifest(),
        campaign_state_sha256="e" * 64,
        namespace_root=root,
    )
    body = json.loads((out / "P0_SENTINEL_ENVELOPE.json").read_text(encoding="utf-8"))
    assert body["envelope"] is None
    assert body["numeric_envelope_bound"] is False


# ==========================================================================
# F-04 -- a provisional or superseded ladder cannot enter P1/P2/production
# ==========================================================================


def _contaminated_schedule_ladder(tmp_path: Path) -> Path:
    """The shape of the artifact found untracked during the audit."""
    path = tmp_path / "capture_schedule.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "mineocclude-experiment-iii-capture-schedule-v1",
                "authority_binding": {
                    "AUTHORITY_SHA256": (
                        "3d116d9713b2c7fa705a194023e271061f712d0693618abbd991efa45437d7fb"
                    )
                },
                "L1": "minecraft:white_stained_glass",
                "L2": "minecraft:lime_stained_glass",
                "L3": "minecraft:blue_stained_glass",
            }
        ),
        encoding="utf-8",
    )
    return path


def test_a15_a_v1_5_bound_provisional_schedule_is_rejected(tmp_path) -> None:
    with pytest.raises(ExperimentIIIError) as error:
        load_selected_ladder(_contaminated_schedule_ladder(tmp_path))
    assert error.value.blocker == "P0_CANDIDATE_ID_UNSUPPORTED"


def test_a15_a_bare_three_key_ladder_is_rejected(tmp_path) -> None:
    """Any JSON object with L1/L2/L3 used to be accepted by the runner."""
    path = tmp_path / "ladder.json"
    path.write_text(json.dumps(dict(EXPECTED_LADDER)), encoding="utf-8")
    with pytest.raises(ExperimentIIIError) as error:
        load_selected_ladder(path)
    assert error.value.blocker == "P0_CANDIDATE_ID_UNSUPPORTED"


def test_a15_a_ladder_bound_to_another_authority_is_rejected(
    written_artifacts, tmp_path
) -> None:
    out, _ = written_artifacts
    body = json.loads((out / "P0_SELECTED_LADDER.json").read_text(encoding="utf-8"))
    body["provenance"]["authority_binding"]["AUTHORITY_SHA256"] = "0" * 64
    path = tmp_path / "drifted.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(ExperimentIIIError) as error:
        load_selected_ladder(path)
    assert error.value.blocker == "PROVENANCE_AUTHORITY_DRIFT"


def test_a15_a_provisional_ladder_is_rejected(written_artifacts, tmp_path) -> None:
    out, _ = written_artifacts
    body = json.loads((out / "P0_SELECTED_LADDER.json").read_text(encoding="utf-8"))
    body["is_provisional"] = True
    path = tmp_path / "provisional.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(ExperimentIIIError) as error:
        load_selected_ladder(path)
    assert error.value.blocker == "P0_CANDIDATE_ID_UNSUPPORTED"


def test_a15_production_capture_resolves_the_ladder_through_the_gate() -> None:
    """The gate must be on the production path, not only available to it."""
    source = (SCRIPTS / "run_production_capture.py").read_text(encoding="utf-8")
    assert "load_selected_ladder(args.ladder)" in source
    assert "json.loads(args.ladder.read_text" not in source


def test_a15_the_contaminated_schedule_is_gone_and_dispositioned() -> None:
    stale = REPOSITORY_ROOT / "docs" / "experiment_iii" / "capture" / "capture_schedule.json"
    assert not stale.exists(), "the pre-P0 dry-run schedule is still on the capture path"
    record = json.loads(
        (
            REPOSITORY_ROOT
            / "docs"
            / "experiment_iii"
            / "superseded_evidence"
            / "SUPERSEDED_ARTIFACT_DISPOSITION.json"
        ).read_text(encoding="utf-8")
    )
    assert record["sha256"] == (
        "beceb38f0058dd3ed7a76e1cf0b10dd45ab1ad5ce0f3bb4d51c75f70ec145339"
    )
    assert record["may_enter_p2"] is False
    assert record["captured_any_frame"] is False


# ==========================================================================
# F-03 -- physical evidence, read from the apparatus
# ==========================================================================


def _png(path: Path, width: int = 640, height: int = 360) -> None:
    """A real, minimal PNG so the IHDR chunk is genuinely parsed."""

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    raw = b"".join(b"\x00" + bytes(width * 3) for _ in range(height))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def _episode(
    root: Path,
    episode_id: int,
    *,
    frames: int = 4,
    first_tick: int = 100,
    drained: bool = True,
    writer_errors: int = 0,
    queue_depth: int = 0,
    width: int = 640,
    height: int = 360,
    tick_of: object = None,
) -> Path:
    directory = root / f"episode_{episode_id}"
    (directory / "frames").mkdir(parents=True, exist_ok=True)
    rows = []
    for index in range(frames):
        name = f"{index:06d}.png"
        _png(directory / "frames" / name, width=width, height=height)
        tick = tick_of(index) if tick_of else first_tick + index
        rows.append(
            {
                "episode_id": episode_id,
                "server_tick": tick,
                "render_frame_idx": index,
                "server_epoch_nanos": 0,
                "client_recv_nanos": 0,
                "client_capture_nanos": 0,
                "tick_queue_depth_at_capture": queue_depth,
                "frame_path": f"frames/{name}",
            }
        )
    (directory / "client_tick.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    (directory / "capture_complete.json").write_text(
        json.dumps(
            {
                "schema_version": "mineocclude-capture-drain-v0.1",
                "episode_id": episode_id,
                "frame_count": frames,
                "final_render_frame_idx": frames - 1,
                "pending_writes": 0,
                "writer_errors": writer_errors,
                "drained": drained,
            }
        ),
        encoding="utf-8",
    )
    (directory / "client_authority.json").write_text(
        json.dumps(
            {
                "schema_version": "mineocclude-client-authority-v0.1",
                "episode_id": episode_id,
                "framebuffer_width": 640,
                "framebuffer_height": 360,
                "hud_hidden": True,
            }
        ),
        encoding="utf-8",
    )
    return directory


def test_a29_python_consumes_the_real_client_tick_ledger(tmp_path) -> None:
    """The tick is the mod's server_tick, not the frame's index."""
    _episode(tmp_path, 87001, frames=4, first_tick=5000)
    records = FrameSink(tmp_path).frame_records(87001)
    assert [row["tick"] for row in records] == [5000, 5001, 5002, 5003]
    assert all(row["evidence_source"] == "OBSERVED_PHYSICAL_EVIDENCE" for row in records)


def test_a29_a_corrupt_tick_ledger_fails_even_when_the_frame_count_is_right(
    tmp_path,
) -> None:
    """The historical defect: enumerate() guaranteed the property being checked.

    Four frames are on disk and four rows are in the ledger, so any count-based
    check passes. The ticks themselves are duplicated, which only a real ledger
    can reveal.
    """
    _episode(tmp_path, 87002, frames=4, tick_of=lambda i: 7000 + (i % 2))
    records = FrameSink(tmp_path).frame_records(87002)
    assert len(records) == 4
    with pytest.raises(ExperimentIIIError) as error:
        verify_unit_liveness(
            frames=records,
            probes=[
                LivenessProbe(
                    "MANDATORY_PRE_CAPTURE_LIVENESS_WITNESS",
                    before_hash="a",
                    after_hash="b",
                    before_tick=0,
                    after_tick=1,
                )
            ],
            process_alive=True,
        )
    assert error.value.blocker == "TIMING_CARDINALITY_MISMATCH"


def test_a29_a_gap_in_the_real_ticks_fails(tmp_path) -> None:
    _episode(tmp_path, 87003, frames=4, tick_of=lambda i: 900 + i * 2)
    records = FrameSink(tmp_path).frame_records(87003)
    with pytest.raises(ExperimentIIIError) as error:
        verify_unit_liveness(
            frames=records,
            probes=[
                LivenessProbe(
                    "MANDATORY_PRE_CAPTURE_LIVENESS_WITNESS",
                    before_hash="a",
                    after_hash="b",
                    before_tick=0,
                    after_tick=1,
                )
            ],
            process_alive=True,
        )
    assert error.value.blocker == "TIMING_CARDINALITY_MISMATCH"


def test_a29_a_missing_tick_ledger_fails_closed(tmp_path) -> None:
    directory = _episode(tmp_path, 87004)
    (directory / "client_tick.jsonl").unlink()
    with pytest.raises(ExperimentIIIError) as error:
        FrameSink(tmp_path).frame_records(87004)
    assert error.value.blocker == "TIMING_CARDINALITY_MISMATCH"


def test_a29_a_ledger_bound_to_another_episode_fails_closed(tmp_path) -> None:
    directory = _episode(tmp_path, 87005)
    rows = [
        json.loads(line)
        for line in (directory / "client_tick.jsonl").read_text().splitlines()
    ]
    for row in rows:
        row["episode_id"] = 99999
    (directory / "client_tick.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    with pytest.raises(ExperimentIIIError) as error:
        read_client_tick_ledger(directory, episode_id=87005)
    assert error.value.blocker == "TIMING_CARDINALITY_MISMATCH"


def test_a29_a_frame_with_no_ledger_row_fails_closed(tmp_path) -> None:
    directory = _episode(tmp_path, 87006, frames=3)
    _png(directory / "frames" / "000009.png")
    with pytest.raises(ExperimentIIIError) as error:
        FrameSink(tmp_path).frame_records(87006)
    assert error.value.blocker == "TIMING_CARDINALITY_MISMATCH"


def test_a29_a_nonzero_tick_queue_depth_fails_closed(tmp_path) -> None:
    """Direct evidence that the world advanced past the photographed state."""
    _episode(tmp_path, 87007, queue_depth=3)
    with pytest.raises(ExperimentIIIError) as error:
        FrameSink(tmp_path).frame_records(87007)
    assert error.value.blocker == "TIMING_CARDINALITY_MISMATCH"


def test_a29_drained_false_fails_closed(tmp_path) -> None:
    _episode(tmp_path, 87010, drained=False)
    with pytest.raises(ExperimentIIIError) as error:
        read_capture_complete(tmp_path / "episode_87010", episode_id=87010)
    assert error.value.blocker == "CAPTURE_STALE_FRAME"


def test_a29_writer_errors_fail_closed(tmp_path) -> None:
    _episode(tmp_path, 87011, writer_errors=1)
    with pytest.raises(ExperimentIIIError) as error:
        FrameSink(tmp_path).frame_records(87011)
    assert error.value.blocker == "CAPTURE_STALE_FRAME"


def test_a29_a_missing_completion_receipt_fails_closed(tmp_path) -> None:
    directory = _episode(tmp_path, 87012)
    (directory / "capture_complete.json").unlink()
    with pytest.raises(ExperimentIIIError) as error:
        FrameSink(tmp_path).frame_records(87012)
    assert error.value.blocker == "CAPTURE_STALE_FRAME"


def test_a29_a_malformed_completion_receipt_fails_closed(tmp_path) -> None:
    directory = _episode(tmp_path, 87013)
    (directory / "capture_complete.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ExperimentIIIError) as error:
        read_capture_complete(directory)
    assert error.value.blocker == "CAPTURE_STALE_FRAME"


def test_a29_a_completion_receipt_for_the_wrong_unit_fails_closed(tmp_path) -> None:
    directory = _episode(tmp_path, 87014)
    with pytest.raises(ExperimentIIIError) as error:
        read_capture_complete(directory, episode_id=87099)
    assert error.value.blocker == "CAPTURE_STALE_FRAME"


def test_a29_wait_for_frames_waits_on_the_drain_receipt_not_a_file_count(
    tmp_path,
) -> None:
    """A file exists at open, not at completion; the count can be right and the
    bytes truncated."""
    directory = _episode(tmp_path, 87015, frames=4)
    (directory / "capture_complete.json").unlink()
    with pytest.raises(ExperimentIIIError) as error:
        FrameSink(tmp_path).wait_for_frames(87015, 4, timeout=0.5)
    assert error.value.blocker == "TIMING_CARDINALITY_MISMATCH"


def test_a29_actual_written_frame_dimensions_are_validated(tmp_path) -> None:
    """Configured dimensions are correct; the written images are not."""
    _episode(tmp_path, 87020, width=1280, height=720)
    records = FrameSink(tmp_path).frame_records(87020)
    assert records[0]["width"] == 1280
    with pytest.raises(ExperimentIIIError) as error:
        verify_unit_liveness(
            frames=records,
            probes=[
                LivenessProbe(
                    "MANDATORY_PRE_CAPTURE_LIVENESS_WITNESS",
                    before_hash="a",
                    after_hash="b",
                    before_tick=0,
                    after_tick=1,
                )
            ],
            process_alive=True,
        )
    assert error.value.blocker == "ENV_FRAMEBUFFER_SIZE_MISMATCH"


def test_a29_dimensions_come_from_the_png_header(tmp_path) -> None:
    _png(tmp_path / "f.png", width=321, height=123)
    assert png_dimensions(tmp_path / "f.png") == (321, 123)


def test_a29_a_non_png_frame_fails_closed(tmp_path) -> None:
    (tmp_path / "bad.png").write_bytes(b"not an image at all, but named .png")
    with pytest.raises(ExperimentIIIError) as error:
        png_dimensions(tmp_path / "bad.png")
    assert error.value.blocker == "CAPTURE_STALE_FRAME"


def test_a29_requested_configuration_cannot_substitute_for_observed_evidence() -> None:
    """A frame record built from constants is refused outright."""
    fabricated = [
        {
            "tick": index,
            "frame_sha256": "a" * 64,
            "width": 640,
            "height": 360,
            "read_succeeded": True,
        }
        for index in range(4)
    ]
    with pytest.raises(ExperimentIIIError) as error:
        verify_unit_liveness(
            frames=fabricated,
            probes=[
                LivenessProbe(
                    "MANDATORY_PRE_CAPTURE_LIVENESS_WITNESS",
                    before_hash="a",
                    after_hash="b",
                    before_tick=0,
                    after_tick=1,
                )
            ],
            process_alive=True,
        )
    assert error.value.blocker == "CAPTURE_STALE_FRAME"


def test_a29_no_required_physical_evidence_item_is_self_certifying() -> None:
    matrix = evidence_binding_matrix()
    contract_items = {row["evidence_id"] for row in matrix}
    from mineocclude.experiment_iii.capture_liveness import liveness_contract

    assert contract_items == set(liveness_contract()["required_evidence"])
    for row in matrix:
        if row["class"] != "OBSERVED_PHYSICAL_EVIDENCE":
            continue
        assert row["physical_producer"]
        assert row["python_parser"]
        assert row["validator"]
        assert row["runtime_call_site"]


def test_a29_the_frame_sink_no_longer_synthesises_ticks_or_dimensions() -> None:
    source = (SRC / "capture_driver.py").read_text(encoding="utf-8")
    assert "first_tick + index" not in source
    assert '"width": FRAMEBUFFER_WIDTH' not in source
    assert '"read_succeeded": True,' not in source
    assert "read_client_tick_ledger" in source
    assert "png_dimensions" in source


# ==========================================================================
# F-02 -- the frozen WALL_MATERIAL_CHANGE probe
# ==========================================================================


def test_a15_a_material_transition_requires_the_wall_material_probe(tmp_path) -> None:
    _episode(tmp_path, 87030)
    records = FrameSink(tmp_path).frame_records(87030)
    probes = [
        LivenessProbe(
            "MANDATORY_PRE_CAPTURE_LIVENESS_WITNESS",
            before_hash="a",
            after_hash="b",
            before_tick=0,
            after_tick=1,
        )
    ]
    with pytest.raises(ExperimentIIIError) as error:
        verify_unit_liveness(
            frames=records,
            probes=probes,
            process_alive=True,
            material_transition=True,
        )
    assert error.value.blocker == "CAPTURE_STALE_FRAME"
    assert "WALL_MATERIAL_CHANGE" in error.value.message


def test_a15_the_wall_material_probe_satisfies_the_requirement(tmp_path) -> None:
    _episode(tmp_path, 87031)
    records = FrameSink(tmp_path).frame_records(87031)
    report = verify_unit_liveness(
        frames=records,
        probes=[
            LivenessProbe(
                "MANDATORY_PRE_CAPTURE_LIVENESS_WITNESS",
                before_hash="a",
                after_hash="b",
                before_tick=0,
                after_tick=1,
            ),
            LivenessProbe(
                "WALL_MATERIAL_CHANGE",
                before_hash="old_material",
                after_hash="new_material",
                before_tick=1,
                after_tick=2,
            ),
        ],
        process_alive=True,
        material_transition=True,
    )
    assert report["material_transition_probed"] is True
    assert "WALL_MATERIAL_CHANGE" in report["required_probe_kinds"]


def test_a15_a_stale_wall_across_a_material_change_is_caught(tmp_path) -> None:
    """The wall did not repaint: same pixels across the material transition."""
    _episode(tmp_path, 87032)
    records = FrameSink(tmp_path).frame_records(87032)
    with pytest.raises(ExperimentIIIError) as error:
        verify_unit_liveness(
            frames=records,
            probes=[
                LivenessProbe(
                    "MANDATORY_PRE_CAPTURE_LIVENESS_WITNESS",
                    before_hash="a",
                    after_hash="b",
                    before_tick=0,
                    after_tick=1,
                ),
                LivenessProbe(
                    "WALL_MATERIAL_CHANGE",
                    before_hash="identical",
                    after_hash="identical",
                    before_tick=1,
                    after_tick=2,
                ),
            ],
            process_alive=True,
            material_transition=True,
        )
    assert error.value.blocker == "CAPTURE_STALE_FRAME"


def test_a15_the_driver_emits_the_probe_on_a_material_change() -> None:
    source = (SRC / "capture_driver.py").read_text(encoding="utf-8")
    assert 'LivenessProbe(\n                    "WALL_MATERIAL_CHANGE"' in source
    assert 'material_transition=bool(transition["probe_required"])' in source
    liveness = (SRC / "capture_liveness.py").read_text(encoding="utf-8")
    assert 'required = {"MANDATORY_PRE_CAPTURE_LIVENESS_WITNESS"}' in liveness
    assert 'required.add("WALL_MATERIAL_CHANGE")' in liveness


def test_a15_prepare_condition_reports_the_transition() -> None:
    """Amendment 4: the unit rebuilds from the witness's NO_WALL, not from the
    preceding unit, so a unit changes the material exactly when it is not air."""
    changed = prepare_condition(
        None, wall_block_id="minecraft:blue_stained_glass", previous_wall_block_id="minecraft:stone"
    )
    assert changed["probe_required"] is True
    assert changed["previous_wall_block_id"] == "minecraft:air"
    # Even when the PRECEDING UNIT declared the same material, the witness has
    # since torn the wall down, so the rebuild is real and must be probed.
    same_as_preceding = prepare_condition(
        None, wall_block_id="minecraft:stone", previous_wall_block_id="minecraft:stone"
    )
    assert same_as_preceding["probe_required"] is True
    # L0 declares air, which is what the witness already left standing.
    l0 = prepare_condition(
        None, wall_block_id="minecraft:air", previous_wall_block_id="minecraft:stone"
    )
    assert l0["probe_required"] is False


# ==========================================================================
# F-07 / F-12 / F-17 -- the pre-capture probe, warmup, and dry-run evidence
# ==========================================================================


def test_a29_the_pre_capture_probe_is_issued_before_the_measured_slots() -> None:
    source = (SRC / "capture_driver.py").read_text(encoding="utf-8")
    probe_at = source.index('"MANDATORY_PRE_CAPTURE_LIVENESS_WITNESS"')
    slots_at = source.index("for slot in unit.slots(frames_per_slot):")
    assert probe_at < slots_at, "the mandatory probe still runs after the ABBA slots"
    assert "results[0].settled_hash,\n                after_hash=results[1]" not in source


def test_a29_the_warmup_is_actually_issued() -> None:
    source = (SRC / "capture_driver.py").read_text(encoding="utf-8")
    assert "runtime.send(warmup_command(ticks=warmup_ticks))" in source
    assert '"warmup_issued": warmup_issued' in source


def test_a29_dry_run_evidence_cannot_look_like_a_measurement() -> None:
    source = (SRC / "capture_driver.py").read_text(encoding="utf-8")
    assert '"may_be_persisted_as_complete": False' in source
    assert '"verdict": "NOT_MEASURED_DRY_RUN"' in source
    runner = (SCRIPTS / "run_p0_rve_calibration.py").read_text(encoding="utf-8")
    assert 'evidence.get("dry_run")' in runner


# ==========================================================================
# F-06 / F-08 -- pipes drained, refusals surfaced
# ==========================================================================


def test_a29_both_process_pipes_are_drained() -> None:
    source = (SRC / "capture_runtime.py").read_text(encoding="utf-8")
    assert "import threading" in source
    assert "class _OutputPump" in source
    assert "self._server_pump = _OutputPump(" in source
    assert "self._client_pump = _OutputPump(" in source
    assert "daemon=True" in source


def test_a29_a_mod_refusal_raises_the_mods_own_blocker() -> None:
    from mineocclude.experiment_iii.capture_runtime import CaptureRuntime, RuntimeConfig

    config = RuntimeConfig.from_mapping(
        {
            "runtime_root": "/tmp/rt",
            "java_executable": "/usr/bin/java",
            "output_root": "/tmp/out",
        }
    )
    runtime = CaptureRuntime(config)
    with pytest.raises(ExperimentIIIError) as error:
        runtime._assert_not_refused(
            "mineocclude p0 1 0.0 4 L1 \"minecraft:bedrock\" true",
            ["[Server] p0 REFUSED: unsupported wall material minecraft:bedrock"],
        )
    assert error.value.blocker == "P0_CANDIDATE_ID_UNSUPPORTED"

    with pytest.raises(ExperimentIIIError) as error:
        runtime._assert_not_refused(
            "mineocclude p0 1 99.0 4 L1 \"minecraft:stone\" true",
            ["p0 REFUSED: placement 99.0 is outside the lane"],
        )
    assert error.value.blocker == "P0_PLACEMENT_GROSS_ERROR"


def test_a29_the_mods_stale_renderer_warning_is_retained() -> None:
    from mineocclude.experiment_iii.capture_runtime import CaptureRuntime, RuntimeConfig

    config = RuntimeConfig.from_mapping(
        {
            "runtime_root": "/tmp/rt",
            "java_executable": "/usr/bin/java",
            "output_root": "/tmp/out",
        }
    )
    runtime = CaptureRuntime(config)
    runtime._assert_not_refused(
        "noop", ["[MineOcclude] 40 consecutive byte-identical captures at tick 900"]
    )
    assert runtime.stale_renderer_warnings


def test_a29_output_root_is_honoured() -> None:
    from mineocclude.experiment_iii.capture_runtime import CaptureRuntime, RuntimeConfig

    config = RuntimeConfig.from_mapping(
        {
            "runtime_root": "/tmp/rt",
            "java_executable": "/usr/bin/java",
            "output_root": "/tmp/declared-output",
        }
    )
    path = CaptureRuntime(config)._log_path("server")
    assert "declared-output" in path.as_posix()


# ==========================================================================
# F-10 -- every attempt is retained
# ==========================================================================


def test_a29_a_failed_unit_is_marked_before_the_error_propagates() -> None:
    source = (SCRIPTS / "run_p0_rve_calibration.py").read_text(encoding="utf-8")
    assert "state.mark_attempt(unit, error.blocker, error.message)" in source
    assert "raise" in source.split("mark_attempt", 1)[1][:400]


# ==========================================================================
# I08 -- sentinel machinery on the live path
# ==========================================================================


def test_a15_the_sentinel_envelope_uses_the_single_frozen_formula() -> None:
    """An earlier derive_envelope used 3*stdev, which is not authority 7.10e."""
    source = (SRC / "sentinels.py").read_text(encoding="utf-8")
    assert "sentinel_envelope(p0_replicates[placement])" in source
    assert "tolerance * spread" not in source
    assert "std(ddof=0)" not in source


def test_a15_the_envelope_matches_p0_bindings_exactly() -> None:
    from mineocclude.experiment_iii.p0_bindings import sentinel_envelope

    replicates = {0: [0.70, 0.76], 4: [0.72, 0.73], 8: [0.71, 0.75]}
    envelope = sentinels.derive_envelope([0, 4, 8], replicates)
    for placement, values in replicates.items():
        expected = sentinel_envelope(values)
        low, high = envelope.bounds[placement]
        assert low == pytest.approx(expected["lower"])
        assert high == pytest.approx(expected["upper"])


def test_a15_the_envelope_is_produced_by_a4(written_artifacts) -> None:
    out, _ = written_artifacts
    body = json.loads((out / "P0_SENTINEL_ENVELOPE.json").read_text(encoding="utf-8"))
    assert body["sentinel_placement_indices"] == list(sentinel_placement_indices())
    assert body["inputs"] == "P0_REPLICATE_VARIATION_ONLY"
    assert body["derived_from_production_measurement"] is False
    assert body["formula_frozen_before_p0"] is True
    # Amendment 3 3e: the formula is frozen now, the numbers are bound in P2.
    assert body["numeric_envelope_bound"] is False
    assert body["numeric_envelope_bound_in"] == "P2"
    assert body["envelope"]["placements"] == [0, 4, 8]


def test_a15_a_batch_boundary_without_an_envelope_fails_closed() -> None:
    with pytest.raises(ExperimentIIIError) as error:
        sentinels.measure_batch_boundary(
            batch_index=0,
            boundary="before",
            scores={0: 0.7, 4: 0.7, 8: 0.7},
            envelope_artifact=None,
            batch_capture_unit_ids=["e3_t01__L1"],
            authority_sha256=verify_authority_binding()["AUTHORITY_SHA256"],
        )
    assert error.value.blocker == "SENTINEL_ENVELOPE_VIOLATION"


def test_a15_a_batch_boundary_with_a_stale_authority_envelope_fails_closed(
    written_artifacts,
) -> None:
    out, _ = written_artifacts
    body = json.loads((out / "P0_SENTINEL_ENVELOPE.json").read_text(encoding="utf-8"))
    body["authority_binding"]["AUTHORITY_SHA256"] = "0" * 64
    with pytest.raises(ExperimentIIIError) as error:
        sentinels.measure_batch_boundary(
            batch_index=0,
            boundary="before",
            scores={0: 0.7, 4: 0.7, 8: 0.7},
            envelope_artifact=body,
            batch_capture_unit_ids=["e3_t01__L1"],
            authority_sha256=verify_authority_binding()["AUTHORITY_SHA256"],
        )
    assert error.value.blocker == "PROVENANCE_AUTHORITY_DRIFT"


def test_a15_an_envelope_at_the_wrong_placements_fails_closed(
    written_artifacts,
) -> None:
    out, _ = written_artifacts
    body = json.loads((out / "P0_SENTINEL_ENVELOPE.json").read_text(encoding="utf-8"))
    body["envelope"]["placements"] = [1, 2, 3]
    with pytest.raises(ExperimentIIIError) as error:
        sentinels.envelope_from_artifact(body)
    assert error.value.blocker == "SENTINEL_ENVELOPE_VIOLATION"


def test_a15_deriving_the_envelope_at_unfrozen_placements_is_refused() -> None:
    with pytest.raises(ExperimentIIIError) as error:
        sentinels.sentinel_envelope_artifact(
            {1: [0.7, 0.72], 4: [0.7, 0.72], 8: [0.7, 0.72]},
            authority_binding=verify_authority_binding(),
            p0_selection_receipt_sha256="x" * 64,
        )
    assert error.value.blocker == "SENTINEL_ENVELOPE_VIOLATION"


def test_a15_a_batch_boundary_passes_and_fails_within_the_frozen_scope(
    written_artifacts,
) -> None:
    out, _ = written_artifacts
    body = json.loads((out / "P0_SENTINEL_ENVELOPE.json").read_text(encoding="utf-8"))
    centre = {
        int(k): (v[0] + v[1]) / 2 for k, v in body["envelope"]["bounds"].items()
    }
    authority = verify_authority_binding()["AUTHORITY_SHA256"]
    passing = sentinels.measure_batch_boundary(
        batch_index=3,
        boundary="before",
        scores=centre,
        envelope_artifact=body,
        batch_capture_unit_ids=["e3_t01__L1", "e3_t02__L1"],
        authority_sha256=authority,
    )
    assert passing["passed"] is True
    assert passing["invalidation"]["invalidated_capture_unit_ids"] == []

    drifted = dict(centre)
    drifted[0] = centre[0] + 10.0
    failing = sentinels.measure_batch_boundary(
        batch_index=3,
        boundary="after",
        scores=drifted,
        envelope_artifact=body,
        batch_capture_unit_ids=["e3_t01__L1", "e3_t02__L1"],
        authority_sha256=authority,
    )
    assert failing["passed"] is False
    assert failing["blocker"] in (
        "SENTINEL_ORDER_VIOLATION",
        "SENTINEL_ENVELOPE_VIOLATION",
    )
    # A sentinel failure is technical, and scoped to its own batch only.
    assert failing["failure_is_technical_not_scientific"] is True
    assert failing["may_change_materials"] is False
    assert failing["is_a_condition_selection_mechanism"] is False
    assert failing["invalidation"]["scope"] == "AFFECTED_UNMODELED_BATCH_ONLY"
    assert failing["invalidation"]["invalidated_capture_unit_ids"] == [
        "e3_t01__L1",
        "e3_t02__L1",
    ]
    assert failing["invalidation"]["other_batches_unaffected"] is True


def test_a15_a_modeled_batch_escalates_rather_than_being_rewritten(
    written_artifacts,
) -> None:
    out, _ = written_artifacts
    body = json.loads((out / "P0_SENTINEL_ENVELOPE.json").read_text(encoding="utf-8"))
    centre = {
        int(k): (v[0] + v[1]) / 2 for k, v in body["envelope"]["bounds"].items()
    }
    centre[0] = centre[0] + 10.0
    receipt = sentinels.measure_batch_boundary(
        batch_index=1,
        boundary="after",
        scores=centre,
        envelope_artifact=body,
        batch_capture_unit_ids=["e3_t01__L1"],
        authority_sha256=verify_authority_binding()["AUTHORITY_SHA256"],
        batch_already_modeled=True,
    )
    assert receipt["invalidation"]["scope"] == "ESCALATE_BATCH_ALREADY_MODELED"


# ==========================================================================
# F-05 -- the authority freeze commit
# ==========================================================================


def test_a30_the_authority_freeze_commit_is_the_v1_7_freeze() -> None:
    assert AUTHORITY_FREEZE_COMMIT == "3fe0bc13d18f0002eebb99a2b10ef83e651d6f9a"


def test_a30_current_and_predecessor_freeze_commits_are_distinct() -> None:
    """They were once degenerate: both held v1.5's freeze."""
    assert AUTHORITY_FREEZE_COMMIT != PREDECESSOR_AUTHORITY_FREEZE_COMMIT
    # v1.6, the predecessor of the current v1.7 package.
    assert PREDECESSOR_AUTHORITY_FREEZE_COMMIT == (
        "a1f5dd1a959ff477edbf469cd12bb4db606371ea"
    )


def test_a30_the_predecessor_freeze_matches_the_frozen_amendment() -> None:
    """The authority names its own predecessor; source must agree with it."""
    from mineocclude.experiment_iii.authority import machine_authority

    amendment = machine_authority()["authority_amendment_4"]
    assert (
        amendment["predecessor_authority_freeze_commit"]
        == PREDECESSOR_AUTHORITY_FREEZE_COMMIT
    )
    # The provenance chain must not collapse: v1.6's own record still names v1.5.
    previous = machine_authority()["authority_amendment_3"]
    assert previous["predecessor_authority_freeze_commit"] == (
        "3fd66eddfce017078b6af2774a381077759b98a0"
    )


def test_a30_the_cohort_salt_constant_is_defined_once() -> None:
    source = (SRC / "authority.py").read_text(encoding="utf-8")
    assert source.count("COHORT_SALT_AUTHORITY_SHA256 = (") == 1


def test_a30_the_host_receipt_would_carry_the_correct_freeze() -> None:
    from mineocclude.experiment_iii import host_preflight

    source = Path(host_preflight.__file__).read_text(encoding="utf-8")
    assert '"authority_freeze_commit": AUTHORITY_FREEZE_COMMIT' in source


# ==========================================================================
# F-09 -- the artifact inventory is filesystem-backed
# ==========================================================================


def test_a29_stage_exit_check_reads_the_real_filesystem() -> None:
    report = stage_exit_check_fs("A1", REPOSITORY_ROOT)
    assert report["filesystem_backed"] is True
    assert report["exit_permitted"] is True
    assert report["present_count"] == report["required_count"]
    assert stage_exit_check_fs("A2", REPOSITORY_ROOT)["exit_permitted"] is True


def test_a29_stage_exit_check_fails_on_a_missing_artifact(tmp_path) -> None:
    """Against an empty tree every A1 artifact is absent, with its own blocker."""
    with pytest.raises(ExperimentIIIError) as error:
        stage_exit_check_fs("A1", tmp_path)
    assert error.value.blocker != "PROVENANCE_BINDING_MISSING"


def test_a29_a4_cannot_exit_before_p0_has_run() -> None:
    with pytest.raises(ExperimentIIIError) as error:
        stage_exit_check_fs("A4", REPOSITORY_ROOT)
    assert error.value.blocker in ("P0_TECHNICAL_FAIL", "P0_NO_VALID_LADDER")


def test_a29_the_stage_exit_check_has_a_production_caller() -> None:
    """F-09's repair is that the check runs at stage exit, not that it exists.

    ``stage_exit_check`` had exactly one caller -- a test that fed it the
    inventory's own patterns -- so it could not fail. The filesystem-backed check
    now runs where the stage actually exits: when each receipt is written.
    """
    for script in ("build_completion_receipt.py", "build_static_validation_receipt.py"):
        source = (SCRIPTS / script).read_text(encoding="utf-8")
        assert "stage_exit_check_fs(" in source, f"{script} does not check stage exit"


def test_a29_the_receipts_record_the_stage_exit_check() -> None:
    receipt = json.loads(
        (
            REPOSITORY_ROOT
            / "docs"
            / "experiment_iii"
            / "a1_receipts"
            / "implementation_completion_receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert receipt["a1_stage_exit_check"]["filesystem_backed"] is True
    assert receipt["a1_stage_exit_check"]["exit_permitted"] is True
    assert receipt["a1_tasks_complete"] == receipt["a1_tasks_total"] == 20
    assert receipt["a1_tasks_wiring_verified"] == 20


def test_a29_every_a1_artifact_resolves_to_a_real_file() -> None:
    from mineocclude.experiment_iii.artifact_inventory import required_before_next_stage

    for artifact in required_before_next_stage("A1"):
        target = resolve_artifact_path(str(artifact["path_or_pattern"]))
        assert (REPOSITORY_ROOT / target).is_file(), target


# ==========================================================================
# Resource policy -- nothing here touches the apparatus
# ==========================================================================


def test_a29_this_closure_generated_no_live_evidence() -> None:
    p0 = REPOSITORY_ROOT / "docs" / "experiment_iii" / "p0"
    assert not (p0 / "P0_SELECTION_RECEIPT.json").exists()
    assert not (p0 / "P0_SELECTED_LADDER.json").exists()
