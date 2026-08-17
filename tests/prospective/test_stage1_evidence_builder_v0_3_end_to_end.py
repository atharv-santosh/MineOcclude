"""End-to-end regression for the Stage-1 evidence builder under v0.3 authority.

This is the coverage gap that produced the ``134a242`` scientific FAIL. The
sibling module ``test_stage1_evidence_builder_end_to_end`` drives the real
builder end to end, but it binds the **v0.2** package -- so it proved only that
the builder speaks v0.2 point/band semantics correctly. Nothing anywhere
exercised the builder against an authority declaring

    primary_predicate = extent_occlusion_geometry_over_rendered_target_extent

and the builder was never ported. It kept emitting the v0.2 transition schema,
kept classifying rows by the superseded point/band rule, and kept selecting
FIRST_N designated rows over the stale pool. Five of nine Stage-1 gates failed
on live data before anyone learned that the *physics* was fine.

So this module drives the same real path against the v0.3 package:

    synthetic raw capture -> scripts/.../build_stage1_evidence.py main()
    -> real evidence document -> v0.3 Stage1Evaluator -> PASS

and then asserts, specifically, the four properties whose absence was the
defect: zero builder/evaluator regime mismatches, a complete v0.3 extent
transition schema, a designated-row schedule drawn from the extent-stable pool,
and no unresolved warm-up row reachable by the aligned transition derivation.

The synthetic renderer is driven **by the frozen extent geometry itself** rather
than by a hand-chosen band, so the fixture cannot silently encode the very
semantics under test. See :func:`_occluded_interval`.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from PIL import Image

from mineocclude.prospective.development_workflow import (
    Stage1Evaluator, load_json, sha256_file,
)
from mineocclude.prospective.extent_geometry import ExtentClass
from mineocclude.prospective.package_binding import stage1_decision_artifact_id
from scripts.regime_a_prime_qualification_v0_2 import build_stage1_evidence
from tests.prospective.test_stage1_evidence_builder_end_to_end import (
    BLOB_HEIGHT_PIXELS, BLOB_WIDTH_PIXELS, FRAME_PIXELS, RENDER_SMOOTHING,
    SCREEN_MARGIN_PIXELS, _render_frame, _screen_x, _synthetic_path, _write_receipt,
    run_builder,
)


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / ("docs/status/integration/regime_a_prime_qualification_v0_1"
                  "/prospective_development_authority_v0_3")

#: How far the synthetic renderer's blank-out band is widened past the frozen
#: fully-occluded interval, in blocks. It must be strictly positive so every
#: scored stable-occluded row renders absent despite the sub-hundredth-block
#: residual between the reconstructed aligned coordinate and the coordinate the
#: frame was actually drawn at, and strictly smaller than the partial band
#: (~2.62 blocks per edge) so no scored stable-visible row is blanked. Any value
#: in that wide interior works; nothing scientific reads it.
RENDER_BLANKOUT_MARGIN_BLOCKS = 0.5


def _evaluator(authority: dict, manifest: dict, authority_path: Path,
               manifest_path: Path) -> Stage1Evaluator:
    return Stage1Evaluator(authority, manifest,
                           authority_sha256=sha256_file(authority_path),
                           manifest_sha256=sha256_file(manifest_path))


def _occluded_interval(evaluator: Stage1Evaluator, lane: list[float]) -> tuple[float, float]:
    """Locate the frozen fully-occluded world-x interval by scanning the lane.

    Read out of the geometry engine rather than declared, so the fixture cannot
    drift from the predicate the evaluator scores with.
    """
    step = 0.001
    occluded = [lane[0] + index * step
                for index in range(int((lane[1] - lane[0]) / step) + 1)
                if evaluator.classify_extent_row(lane[0] + index * step, "WALL")
                is ExtentClass.EXTENT_FULLY_OCCLUDED]
    assert occluded, "frozen apparatus has no fully-occluded extent rows"
    return min(occluded), max(occluded)


def synthesize_capture(tmp_path: Path) -> tuple[Path, Path]:
    """Write a complete synthetic v0.3 Stage-1 raw capture and return its bindings."""
    authority = load_json(PACKAGE / "authority_parameters.json")
    assert (authority["stage1_policy"]["visibility"]["primary_predicate"]
            == "extent_occlusion_geometry_over_rendered_target_extent"), (
        "this module must bind an authority that selects the extent predicate")
    authority["apparatus"]["canonical_frame_pixels"] = FRAME_PIXELS
    authority["apparatus_observation_policy"]["canonical_frame_pixels"] = FRAME_PIXELS
    authority_path = tmp_path / "authority_parameters.json"
    authority_path.write_text(json.dumps(authority, indent=2, sort_keys=True) + "\n")

    manifest = load_json(PACKAGE / "stage1_manifest.json")
    manifest["authority_binding"]["sha256"] = sha256_file(authority_path)
    for unit in manifest["units"]:
        unit["receipt_path"] = str(tmp_path / "receipts" / f"{unit['unit_id']}.json")
        unit["command"] = ["python3", "--stage", "stage1-capture",
                           "--unit-id", unit["unit_id"]]
    manifest_path = tmp_path / "stage1_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    evaluator = _evaluator(authority, manifest, authority_path, manifest_path)
    width, height = FRAME_PIXELS
    lane = authority["apparatus"]["lane_world_x_blocks"]
    seconds_per_tick = authority["apparatus"]["seconds_per_server_tick"]
    token_grid = authority["apparatus"]["visual_token_grid"]
    centre_y = authority["apparatus"]["target_centre_world_y"]
    lane_z = authority["apparatus"]["lane_world_z"]
    camera = tuple(authority["apparatus"]["camera_eye_world_xyz"])
    wall = evaluator.extent_truth["wall"]
    occluded_low, occluded_high = _occluded_interval(evaluator, lane)
    blank_low = occluded_low - RENDER_BLANKOUT_MARGIN_BLOCKS
    blank_high = occluded_high + RENDER_BLANKOUT_MARGIN_BLOCKS

    for unit in manifest["units"]:
        path = _synthetic_path(unit, seconds_per_tick, lane)
        capture = tmp_path / "captures" / unit["unit_id"]
        (capture / "raw/frames").mkdir(parents=True, exist_ok=True)
        state, coordinates = [], []
        for index, world_x in enumerate(path):
            rendered_x = sum(weight * path[max(0, index - lag)]
                             for lag, weight in RENDER_SMOOTHING.items())
            render_hidden = (unit["scene"] == "WALL"
                             and blank_low <= rendered_x <= blank_high)
            # The blank-out band must sit strictly between the fully-occluded
            # extent and the fully-visible extent, or the fixture -- not the
            # builder -- would be deciding the detector's error rates.
            if unit["scene"] == "WALL":
                extent = evaluator.classify_extent_row(rendered_x, "WALL")
                if extent is ExtentClass.EXTENT_FULLY_OCCLUDED:
                    assert render_hidden, "a fully-occluded row must render absent"
                if extent is ExtentClass.EXTENT_FULLY_VISIBLE:
                    assert not render_hidden, "a fully-visible row must render present"
            # point_visible keeps its v0.2 centre-ray meaning and is derived from
            # the same reference primitive the mod uses. Under v0.3 it is
            # diagnostic only; nothing here lets it reach the truth predicate.
            point_hidden = (unit["scene"] == "WALL"
                            and wall.occludes(camera, (world_x, centre_y, lane_z)))
            state.append({"server_tick": index, "sheep_x": world_x, "sheep_z": lane_z,
                          "geometric_visible": not point_hidden})
            screen_x, screen_y = _screen_x(world_x, width), height / 2.0
            coordinates.append({"model_frame_idx": index,
                "screen_x": screen_x, "screen_y": screen_y,
                "token_cell_row": math.floor(screen_y * token_grid[0] / height),
                "token_cell_col": math.floor(screen_x * token_grid[1] / width)})
            Image.fromarray(_render_frame(width, height, _screen_x(rendered_x, width),
                                          not render_hidden)).save(
                capture / "raw/frames" / f"{index:06d}.png")
        (capture / "raw/server_state.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in state))
        (capture / "coordinates.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in coordinates))
        _write_receipt(authority, manifest, unit)
    return authority_path, manifest_path


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """Build the v0.3 evidence document once; every assertion below reads it."""
    tmp_path = tmp_path_factory.mktemp("v0_3_builder")
    authority_path, manifest_path = synthesize_capture(tmp_path)
    evidence_path = tmp_path / "stage1_evidence.json"

    class _Monkey:
        def setattr(self, target, value):
            import sys
            assert target == "sys.argv"
            sys.argv = value

    run_builder(_Monkey(), authority_path, manifest_path, evidence_path)
    authority, manifest = load_json(authority_path), load_json(manifest_path)
    return {"authority": authority, "manifest": manifest,
            "authority_path": authority_path, "manifest_path": manifest_path,
            "evidence": load_json(evidence_path), "evidence_path": evidence_path,
            "evaluator": _evaluator(authority, manifest, authority_path, manifest_path)}


def test_v0_3_builder_output_reaches_a_legitimate_stage1_pass(built):
    decision = built["evaluator"].evaluate(built["evidence"])
    assert decision.status == "PASS", decision.reasons
    assert decision.reasons == ()
    # The decision now carries the identity of the experiment that produced it.
    payload = decision.to_dict(authority_sha256="a" * 64, manifest_sha256="b" * 64,
                               evidence_sha256="e" * 64,
                               artifact_id=stage1_decision_artifact_id(built["manifest"]))
    assert payload["artifact_id"] == "regime-a-prime-stage1-decision-v0.3"


def test_builder_and_evaluator_agree_on_every_row(built):
    """Zero regime mismatches -- the 134a242 count was 166, all one-directional."""
    evaluator, evidence = built["evaluator"], built["evidence"]
    units = {unit["unit_id"]: unit for unit in built["manifest"]["units"]}
    transitions = evidence["transition_measurement_by_direction"]
    mismatches = []
    for run in evidence["runs"]:
        unit = units[run["unit_id"]]
        for index, sample in enumerate(run["visibility_samples"]):
            expected = evaluator.expected_regime(sample, unit, transitions[unit["direction"]])
            if sample["regime"] != expected:
                mismatches.append((run["unit_id"], index, sample["regime"], expected))
    assert mismatches == []


def test_builder_uses_extent_semantics_not_the_superseded_point_band_rule(built):
    """A row the v0.2 rule calls stable-occluded, v0.3 calls partial.

    This is the exact defect shape: every one of the 166 mismatches was a
    builder ``stable_*`` against an evaluator ``partial_transition``, because the
    rendered extent straddles the shadow edge over a band where the centre point
    is already hidden. The row must be emitted PARTIAL, and therefore unscored --
    which is also why the old boundary false positives disappeared.
    """
    evaluator, evidence = built["evaluator"], built["evidence"]
    run = next(row for row in evidence["runs"]
               if row["scene"] == "WALL" and row["unit_id"].endswith("_r02"))
    straddling = [sample for sample in run["visibility_samples"]
                  if sample["point_visible"] is False
                  and evaluator.classify_extent_row(sample["world_x"], "WALL")
                  is ExtentClass.EXTENT_PARTIAL]
    assert straddling, (
        "the frozen apparatus must produce rows whose centre is hidden while the "
        "rendered extent is not; otherwise this regression proves nothing")
    assert all(sample["regime"] == "partial_transition" for sample in straddling)
    # ...and a partial row never enters the scored pools or the hidden pool.
    assert all(index not in run["designated_hidden_row_indices"]
               for index, sample in enumerate(run["visibility_samples"])
               if sample["regime"] == "partial_transition")


def test_transition_block_carries_the_complete_v0_3_extent_schema(built):
    evidence = built["evidence"]
    for direction, item in evidence["transition_measurement_by_direction"].items():
        assert item["status"] == "MEASURED", direction
        assert item["derivation"] == "EXTENT_GEOMETRY_ON_ALIGNED_ROWS_ONLY"
        assert item["detector_defines_held_out_truth"] is False
        assert len(item["extent_fully_occluded_world_x_interval"]) == 2
        assert len(item["rendered_detector_absent_world_x_interval"]) == 2
        assert len(item["geometric_extent_transition_world_x_intervals"]) == 2
        # The superseded v0.2 keys must be gone, not merely accompanied.
        assert "stable_occluded_world_x_interval" not in item
        assert "partial_transition_world_x_intervals" not in item


def test_unresolved_warmup_rows_cannot_enter_the_aligned_transition_derivation(built):
    """Rows 0..maximum_lag-1 have no aligned coordinate and must be excluded."""
    evidence, authority = built["evidence"], built["authority"]
    maximum_lag = authority["stage1_policy"]["temporal_alignment"][
        "maximum_lag_ticks_for_estimation"]
    frames = authority["fixed_development_configuration"]["expected_frames_per_run"]
    for direction, item in evidence["transition_measurement_by_direction"].items():
        assert item["rows_excluded_unaligned"] == maximum_lag, direction
        assert item["aligned_rows_admitted"] == frames - maximum_lag, direction
    for run in evidence["runs"]:
        unresolved = [index for index, sample in enumerate(run["visibility_samples"])
                      if sample["temporal_alignment_resolved"] is not True]
        assert unresolved == list(range(maximum_lag)), run["unit_id"]


def test_designated_hidden_rows_come_from_the_extent_stable_occluded_pool(built):
    """FIRST_N over the *extent* pool, reproduced identically by both sides.

    At 134a242 the builder's LTR held-out schedule began at frame 38 -- the first
    row its stale point/band rule called stable-occluded -- while the evaluator
    recomputed the schedule over the extent pool beginning at 47. The rule is
    unchanged; only the pool it reads is repaired.
    """
    evaluator, evidence = built["evaluator"], built["evidence"]
    required = built["authority"]["stage1_policy"]["contamination"][
        "required_hidden_rows_per_wall_validation_run"]
    units = {unit["unit_id"]: unit for unit in built["manifest"]["units"]}
    held_out = [run for run in evidence["runs"]
                if units[run["unit_id"]]["scene"] == "WALL"
                and units[run["unit_id"]]["design_role"] == "HELD_OUT_VALIDATION"]
    assert len(held_out) == 2
    for run in held_out:
        indices = run["designated_hidden_row_indices"]
        regimes = [sample["regime"] for sample in run["visibility_samples"]]
        assert len(indices) == required == 19, run["unit_id"]
        # Independently reproduced by the evaluator's own schedule method.
        assert indices == evaluator.designated_hidden_row_indices(
            regimes, scene="WALL", design_role="HELD_OUT_VALIDATION")
        # Every designated row is fully occluded over its whole rendered extent.
        assert all(evaluator.classify_extent_row(
            run["visibility_samples"][index]["world_x"], "WALL")
            is ExtentClass.EXTENT_FULLY_OCCLUDED for index in indices)
        # FIRST_N, not "some N": the schedule starts at the first qualified row.
        assert indices[0] == regimes.index("stable_occluded")
        assert indices == list(range(indices[0], indices[0] + required))
        # Zero contamination on every prohibited class.
        assert all(value == 0 for value in
                   run["hidden_row_contamination"]["prohibited_counts"].values())


def test_detector_never_participates_in_v0_3_truth(built):
    """Flipping every detector value cannot move a single regime."""
    evaluator, evidence = built["evaluator"], built["evidence"]
    units = {unit["unit_id"]: unit for unit in built["manifest"]["units"]}
    transitions = evidence["transition_measurement_by_direction"]
    for run in evidence["runs"]:
        unit = units[run["unit_id"]]
        for sample in run["visibility_samples"]:
            before = evaluator.expected_regime(sample, unit, transitions[unit["direction"]])
            flipped = dict(sample, detector_visible=not sample["detector_visible"])
            assert evaluator.expected_regime(
                flipped, unit, transitions[unit["direction"]]) == before
