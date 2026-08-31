"""Authority Amendment 3 (v1.6) — the P0 operational bindings.

Six rules that v1.5 named and never froze, plus the capture layer that executes
them. The negative tests matter more than the positive ones here: each of these
bindings decides which materials can qualify, so the failure mode to guard is a
rule that quietly becomes candidate-dependent or outcome-dependent.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from mineocclude.experiment_iii.authority import machine_authority
from mineocclude.experiment_iii.capture_driver import p0_slot_command, startspec_command
from mineocclude.experiment_iii.capture_liveness import (
    verify_capture_tick_integrity,
    LivenessProbe,
    assert_transition_observed,
    liveness_contract,
    verify_tick_integrity,
    verify_unit_liveness,
)
from mineocclude.experiment_iii.capture_runtime import (
    QUALIFIED_DISPLAY_STRATEGIES,
    CaptureRuntime,
    RuntimeConfig,
    qualify_capture_host,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.p0_bindings import (
    background_gate,
    deterministic_split_half,
    l0_noise_threshold,
    p0_bootstrap_seed,
    sentinel_envelope,
    sentinel_within_envelope,
)
from mineocclude.experiment_iii.p0_campaign import (
    MEASURED_CONDITION_COUNT,
    UNIT_COUNT,
    P0CampaignState,
    campaign_manifest,
    campaign_units,
)
from mineocclude.experiment_iii.placements import (
    PLACEMENT_COUNT,
    SUPERSEDED_PLACEMENTS_SHA256,
    assert_not_the_superseded_derivation,
    corridor_interval,
    placement_coordinates,
    placement_manifest,
    sentinel_placement_indices,
)

RNG = np.random.default_rng(20260831)


def _state_path(tmp_path: Path) -> Path:
    """Campaign state lives inside the Experiment III namespace, as in production."""
    directory = tmp_path / "docs" / "experiment_iii" / "p0"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "p0_campaign_state.json"


def _noise_frames(count: int, *, scale: float, shape=(12, 16, 3)) -> list[np.ndarray]:
    base = np.full(shape, 0.5, dtype=np.float64)
    return [base + RNG.normal(0.0, scale, size=shape) for _ in range(count)]


# ==========================================================================
# 3a  placements
# ==========================================================================


def test_the_nine_frozen_phase0_positions() -> None:
    xs = [p["lane_x"] for p in placement_coordinates()]
    assert xs == [-2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0]
    assert len(xs) == PLACEMENT_COUNT


def test_placements_are_read_from_the_authority_not_restated() -> None:
    frozen = machine_authority()["p0_rve"]["placement_coordinates_lane_x"]
    assert [p["lane_x"] for p in placement_coordinates()] == [float(x) for x in frozen]


def test_placement_digest_matches_the_frozen_hash() -> None:
    manifest = placement_manifest()
    assert manifest["placements_sha256"] == machine_authority()["p0_rve"]["placements_sha256"]
    assert (
        manifest["placements_sha256"]
        == "5676aa3371fcc481f89c709d8be81e2b14932f550b94ce44a42b2617420a84b6"
    )


def test_every_placement_is_inside_the_occluded_corridor() -> None:
    low, high = corridor_interval()
    for placement in placement_coordinates():
        assert low <= placement["lane_x"] <= high


def test_placements_stay_on_the_frozen_sheep_lane() -> None:
    lane = machine_authority()["apparatus"]["sheep_lane"]
    for placement in placement_coordinates():
        assert placement["lane_y"] == float(lane["y"])
        assert placement["lane_z"] == float(lane["z"])


def test_the_superseded_derivation_is_refused() -> None:
    """The pre-amendment corridor partition must never enter P2."""
    with pytest.raises(ExperimentIIIError) as error:
        assert_not_the_superseded_derivation(SUPERSEDED_PLACEMENTS_SHA256)
    assert error.value.blocker == "PROVENANCE_AUTHORITY_DRIFT"
    assert placement_manifest()["placements_sha256"] != SUPERSEDED_PLACEMENTS_SHA256
    assert placement_manifest()["superseded_may_enter_p2"] is False


# ==========================================================================
# 3b  bootstrap seed
# ==========================================================================


def test_bootstrap_seed_is_the_frozen_value() -> None:
    assert p0_bootstrap_seed() == 1530570907966297797
    assert p0_bootstrap_seed() == int(machine_authority()["p0_rve"]["bootstrap_seed"])


def test_bootstrap_seed_derivation_is_reproducible_from_phase0() -> None:
    phase0 = machine_authority()["phase0_inputs"]
    del phase0  # provenance only; the derivation uses the design digest below
    expected = (
        int.from_bytes(
            hashlib.sha256(
                (
                    "MINEOCCLUDE_EXPERIMENT_III_P0_BOOTSTRAP_V1|"
                    "be3ccd97525434659dc39b3be36e6046ceebaeab2a33db81ce18c139e19c8e4c"
                ).encode("utf-8")
            ).digest()[:8],
            "big",
        )
        & ((1 << 63) - 1)
    )
    assert p0_bootstrap_seed() == expected


def test_bootstrap_seed_is_in_range_and_not_hand_picked() -> None:
    seed = p0_bootstrap_seed()
    assert 0 <= seed < (1 << 63)
    # A different Phase 0 binding must give a different seed, proving derivation.
    other = p0_bootstrap_seed(phase0_sha256="00" * 32)
    assert other != seed


# ==========================================================================
# 3c  L0 noise threshold
# ==========================================================================


def test_split_half_is_balanced_and_drops_the_middle_frame_when_odd() -> None:
    first, second = deterministic_split_half([0, 1, 2, 3, 4])
    assert first == [0, 1]
    assert second == [3, 4]
    assert len(first) == len(second)
    first, second = deterministic_split_half([0, 1, 2, 3])
    assert (first, second) == ([0, 1], [2, 3])


def test_split_half_refuses_fewer_than_two_frames() -> None:
    with pytest.raises(ExperimentIIIError) as error:
        deterministic_split_half([0])
    assert error.value.blocker == "P0_TECHNICAL_FAIL"


def test_l0_noise_threshold_is_deterministic_and_has_no_tunable() -> None:
    blocks = [_noise_frames(8, scale=0.001), _noise_frames(8, scale=0.001)]
    first = l0_noise_threshold(blocks)
    second = l0_noise_threshold(blocks)
    assert first["threshold"] == second["threshold"]
    assert first["tunable_constants"] == 0
    assert first["threshold"] > 0.0


def test_l0_noise_threshold_is_an_envelope_over_the_noisiest_block() -> None:
    quiet = _noise_frames(8, scale=0.0005)
    loud = _noise_frames(8, scale=0.02)
    pooled = l0_noise_threshold([quiet, loud])["threshold"]
    quiet_only = l0_noise_threshold([quiet])["threshold"]
    assert pooled >= quiet_only


def test_candidate_frames_cannot_influence_the_threshold() -> None:
    """The negative test the amendment exists for.

    The threshold decides the support mask, and the mask decides every
    candidate's D. If a candidate's frames could move it, a material would be
    scoring against a mask it had itself widened.
    """
    l0_blocks = [_noise_frames(8, scale=0.001), _noise_frames(8, scale=0.001)]
    baseline = l0_noise_threshold(l0_blocks)["threshold"]

    # A candidate material's frames are a different, much larger signal. They are
    # simply never an admissible argument: the function's whole input is L0.
    candidate_blocks = [
        [frame + 0.4 for frame in _noise_frames(8, scale=0.05)] for _ in range(2)
    ]
    with_candidate = l0_noise_threshold(candidate_blocks)["threshold"]
    assert with_candidate != baseline

    # Recomputing from the same L0 input is unchanged regardless of what any
    # candidate did, because the candidate never enters the computation.
    assert l0_noise_threshold(l0_blocks)["threshold"] == baseline
    assert l0_noise_threshold(l0_blocks)["candidate_frames_consumed"] is False


def test_threshold_rule_is_declared_in_the_authority() -> None:
    rule = machine_authority()["p0_rve"]["l0_noise_threshold_rule"]
    assert rule["candidate_frames_consumed"] is False
    assert rule["mineworld_output_consumed"] is False
    assert rule["tunable_constants"] == 0
    assert rule["dtype"] == "float64"
    assert rule["comparison_operator"] == "STRICTLY_GREATER_THAN"


# ==========================================================================
# 3d  background tolerance
# ==========================================================================


def _mask(shape=(12, 16)) -> np.ndarray:
    mask = np.zeros(shape, dtype=bool)
    mask[4:8, 5:10] = True
    return mask


def test_clean_background_passes() -> None:
    mask = _mask()
    absent_frames = _noise_frames(8, scale=0.001)
    absent = np.median(np.stack(absent_frames), axis=0)
    present = absent.copy()
    present[mask] += 0.5  # the target, entirely inside the mask
    report = background_gate(present, absent, absent_frames, mask)
    assert report["passed"] is True
    assert report["blocker"] is None


def test_planted_background_change_fails() -> None:
    mask = _mask()
    absent_frames = _noise_frames(8, scale=0.001)
    absent = np.median(np.stack(absent_frames), axis=0)
    present = absent.copy()
    present[mask] += 0.5
    # A wall material, light level or camera slip changed OUTSIDE the mask.
    present[0:2, 0:4] += 0.3
    report = background_gate(present, absent, absent_frames, mask)
    assert report["passed"] is False
    assert report["blocker"] == "RVE_BACKGROUND_TOLERANCE_EXCEEDED"


def test_background_threshold_is_candidate_independent() -> None:
    """The ratio is frozen; only the cell's own technical noise scales it."""
    mask = _mask()
    absent_frames = _noise_frames(8, scale=0.001)
    absent = np.median(np.stack(absent_frames), axis=0)
    bright = absent.copy()
    bright[mask] += 0.9
    dim = absent.copy()
    dim[mask] += 0.05
    a = background_gate(bright, absent, absent_frames, mask)
    b = background_gate(dim, absent, absent_frames, mask)
    assert a["ratio"] == b["ratio"] == 4.0
    assert a["allowed"] == pytest.approx(b["allowed"])
    assert a["candidate_independent"] is True


def test_zero_noise_denominator_requires_exact_background_identity() -> None:
    """No epsilon: with demonstrably zero noise, any outside change is real."""
    mask = _mask()
    flat = np.full((12, 16, 3), 0.5, dtype=np.float64)
    absent_frames = [flat.copy() for _ in range(8)]
    identical = flat.copy()
    identical[mask] += 0.5
    clean = background_gate(identical, flat, absent_frames, mask)
    assert clean["zero_reference"] is True
    assert clean["passed"] is True

    dirty = identical.copy()
    dirty[0, 0] += 1e-9
    report = background_gate(dirty, flat, absent_frames, mask)
    assert report["zero_reference"] is True
    assert report["passed"] is False
    assert report["blocker"] == "RVE_BACKGROUND_TOLERANCE_EXCEEDED"


def test_background_rule_may_not_be_lowered_after_failure() -> None:
    rule = machine_authority()["p0_rve"]["background_tolerance_rule"]
    assert rule["may_be_lowered_after_failure"] is False
    assert rule["tuned_from_candidate_ranking"] is False
    assert rule["tuned_from_mineworld_output"] is False


# ==========================================================================
# 3e  sentinels
# ==========================================================================


def test_sentinel_selection_is_prospective_left_centre_right() -> None:
    assert sentinel_placement_indices() == (0, 4, 8)
    xs = [placement_coordinates()[i]["lane_x"] for i in sentinel_placement_indices()]
    assert xs == [-2.0, 0.0, 2.0]


def test_sentinel_selection_reads_no_measurement() -> None:
    """Selection must not depend on which placements later looked stable."""
    before = sentinel_placement_indices()
    # Any imaginable measurement outcome leaves the selection untouched, because
    # the function takes no measurement argument at all.
    after = sentinel_placement_indices()
    assert before == after
    assert machine_authority()["p0_rve"]["sentinel_selection_is_outcome_independent"]


def test_sentinel_envelope_is_reproducible() -> None:
    scores = [0.42, 0.44]
    first = sentinel_envelope(scores)
    second = sentinel_envelope(scores)
    assert first == second
    assert first["lower"] < first["centre"] < first["upper"]


def test_sentinel_envelope_never_has_zero_width() -> None:
    """Two identical P0 replicates must not doom every later batch."""
    envelope = sentinel_envelope([0.5, 0.5])
    assert envelope["replicate_range"] == 0.0
    assert envelope["half_width"] > 0.0
    assert sentinel_within_envelope(0.5, envelope)


def test_sentinel_envelope_lower_bound_is_clamped_at_zero() -> None:
    envelope = sentinel_envelope([0.01, 0.9])
    assert envelope["lower"] == 0.0


def test_sentinel_envelope_uses_only_replicate_variation() -> None:
    envelope = sentinel_envelope([0.3, 0.34])
    assert envelope["inputs"] == "P0_REPLICATE_VARIATION_ONLY"
    assert envelope["formula_frozen_before_p0"] is True


# ==========================================================================
# 3f  capture liveness
# ==========================================================================


def _frames(
    count: int,
    *,
    hashes: list[str] | None = None,
    start: int = 0,
    episode_id: int = 90_000,
):
    return [
        {
            # The apparatus keys a frame on (episode_id, server_tick); a record
            # carrying only the tick is half an identity.
            "episode_id": episode_id,
            "tick": start + index,
            "frame_sha256": (hashes[index] if hashes else "a" * 64),
            "width": 640,
            "height": 360,
            "read_succeeded": True,
            "evidence_source": "OBSERVED_PHYSICAL_EVIDENCE",
        }
        for index in range(count)
    ]


def _probe(before: str = "aa", after: str = "bb") -> LivenessProbe:
    return LivenessProbe(
        "MANDATORY_PRE_CAPTURE_LIVENESS_PROBE",
        before_hash=before,
        after_hash=after,
        before_tick=0,
        after_tick=4,
    )


def test_static_scene_with_repeated_bytes_passes() -> None:
    """The whole point of the amendment: a settled static scene is valid."""
    report = verify_unit_liveness(
        frames=_frames(16),  # every frame byte-identical
        probes=[_probe()],
        process_alive=True,
        expected_frames=16,
    )
    assert report["passed"] is True
    assert report["distinct_frame_hashes"] == 1
    assert report["repeated_frame_hashes"] == 15
    assert report["repeated_bytes_within_static_state_is_stale"] is False


def test_frozen_renderer_across_a_transition_fails() -> None:
    """Ticks advanced, the scene changed, the pixels did not."""
    with pytest.raises(ExperimentIIIError) as error:
        assert_transition_observed(
            LivenessProbe(
                "TARGET_PRESENT_TO_ABSENT",
                before_hash="same",
                after_hash="same",
                before_tick=0,
                after_tick=4,
            )
        )
    assert error.value.blocker == "CAPTURE_STALE_FRAME"


def test_transition_without_tick_advance_is_a_timing_failure() -> None:
    with pytest.raises(ExperimentIIIError) as error:
        assert_transition_observed(
            LivenessProbe(
                "WALL_MATERIAL_CHANGE",
                before_hash="a",
                after_hash="b",
                before_tick=7,
                after_tick=7,
            )
        )
    assert error.value.blocker == "TIMING_CARDINALITY_MISMATCH"


def test_duplicated_tick_identity_fails() -> None:
    frames = _frames(4)
    frames[2]["tick"] = frames[1]["tick"]
    with pytest.raises(ExperimentIIIError) as error:
        verify_unit_liveness(frames=frames, probes=[_probe()], process_alive=True)
    assert error.value.blocker == "TIMING_CARDINALITY_MISMATCH"


def test_missing_tick_fails() -> None:
    with pytest.raises(ExperimentIIIError) as error:
        verify_tick_integrity([0, 1, 3, 4])
    assert error.value.blocker == "TIMING_CARDINALITY_MISMATCH"


def test_a_unit_without_the_mandatory_probe_fails() -> None:
    with pytest.raises(ExperimentIIIError) as error:
        verify_unit_liveness(frames=_frames(8), probes=[], process_alive=True)
    assert error.value.blocker == "CAPTURE_STALE_FRAME"


def test_a_dead_capture_process_fails() -> None:
    with pytest.raises(ExperimentIIIError) as error:
        verify_unit_liveness(
            frames=_frames(8), probes=[_probe()], process_alive=False
        )
    assert error.value.blocker == "CAPTURE_STALE_FRAME"


def test_wrong_framebuffer_size_fails() -> None:
    frames = _frames(4)
    frames[1]["height"] = 720
    with pytest.raises(ExperimentIIIError) as error:
        verify_unit_liveness(frames=frames, probes=[_probe()], process_alive=True)
    assert error.value.blocker == "ENV_FRAMEBUFFER_SIZE_MISMATCH"


def test_the_withdrawn_rule_is_recorded_as_withdrawn() -> None:
    contract = liveness_contract()
    assert contract["repeated_bytes_within_one_static_state_is_stale"] is False
    assert contract["frame_hash_alone_is_a_verdict"] is False
    assert "UNIVERSAL_BYTE_DUPLICATE" in contract["supersedes"]


# ==========================================================================
# capture runtime — portability and qualification
# ==========================================================================


def _config(tmp_path: Path, **overrides) -> RuntimeConfig:
    raw = {
        "runtime_root": str(tmp_path),
        "java_executable": str(tmp_path / "java"),
        "output_root": str(tmp_path / "out"),
    }
    raw.update(overrides)
    return RuntimeConfig.from_mapping(raw)


def test_runtime_config_refuses_to_assume_a_host_path(tmp_path: Path) -> None:
    with pytest.raises(ExperimentIIIError) as error:
        RuntimeConfig.from_mapping({"runtime_root": str(tmp_path)})
    assert error.value.blocker == "ENV_RUNTIME_VERSION_MISMATCH"


def test_no_sagemaker_home_is_hard_coded() -> None:
    source = (
        Path(__file__).resolve().parents[2]
        / "src/mineocclude/experiment_iii/capture_runtime.py"
    ).read_text(encoding="utf-8")
    assert "/home/sagemaker-user" not in source
    assert "/usr/lib/jvm" not in source
    assert "sagemaker" not in source.lower()


def test_runtime_config_round_trips_through_json(tmp_path: Path) -> None:
    config = _config(tmp_path, display=":77")
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps(config.as_dict()), encoding="utf-8")
    assert RuntimeConfig.from_json(path).display == ":77"


def test_software_rendering_environment_is_llvmpipe(tmp_path: Path) -> None:
    env = _config(tmp_path).environment()
    assert env["LIBGL_ALWAYS_SOFTWARE"] == "1"
    assert env["GALLIUM_DRIVER"] == "llvmpipe"
    assert env["DISPLAY"] == ":99"


def test_only_headless_software_rendering_qualifies(tmp_path: Path) -> None:
    assert QUALIFIED_DISPLAY_STRATEGIES == ("XVFB",)
    native = qualify_capture_host(
        _config(tmp_path, display_strategy="NATIVE"), system="Linux"
    )
    assert native["qualified"] is False
    assert any("not headless software rendering" in r for r in native["reasons"])


def test_windows_interactive_host_is_not_qualified(tmp_path: Path) -> None:
    report = qualify_capture_host(_config(tmp_path), system="Windows")
    assert report["qualified"] is False
    assert any("Xvfb/llvmpipe stack on Linux" in r for r in report["reasons"])
    assert report["gpu_required"] is False
    assert report["mineworld_loaded"] is False


def test_dry_run_runtime_records_commands_without_processes(tmp_path: Path) -> None:
    runtime = CaptureRuntime(_config(tmp_path), dry_run=True)
    runtime.send("mineocclude status")
    assert runtime.issued_commands == ["mineocclude status"]
    assert runtime.alive() is True


def test_p0_slot_command_carries_material_and_target_presence() -> None:
    command = p0_slot_command(
        episode_id=87001,
        lane_x=-2.0,
        ticks=4,
        condition_id="L1",
        wall_block_id="minecraft:lime_stained_glass",
        target_present=False,
    )
    assert "mineocclude p0 87001 -2.0 4 L1" in command
    assert '"minecraft:lime_stained_glass"' in command
    assert command.endswith("false")


def test_startspec_command_carries_the_condition() -> None:
    command = startspec_command(
        layout_id="layout_01",
        episode_id=86001,
        seed=1,
        q=0.05,
        ticks=180,
        start_pos=-6.0,
        spec_id="s",
        spec_hash="h",
        condition_id="L4",
        wall_block_id="minecraft:stone",
    )
    assert command.startswith("mineocclude startspec layout_01 86001")
    assert '"minecraft:stone"' in command


# ==========================================================================
# P0 campaign structure and resume
# ==========================================================================


def test_campaign_enumerates_every_unit() -> None:
    units = campaign_units()
    assert len(units) == UNIT_COUNT == 14 * 9 * 2 == 252
    assert len({unit.unit_id for unit in units}) == len(units)


def test_campaign_is_condition_major_and_measures_l0_first() -> None:
    units = campaign_units()
    assert units[0].condition_key == "L0"
    order = []
    for unit in units:
        if not order or order[-1] != unit.condition_key:
            order.append(unit.condition_key)
    assert len(order) == MEASURED_CONDITION_COUNT  # one contiguous run each
    assert order[0] == "L0"
    assert order[-1] == "L4"


def test_campaign_meets_the_frozen_frame_minimum() -> None:
    manifest = campaign_manifest()
    minimum = int(machine_authority()["p0_rve"]["min_total_settled_frames"])
    assert manifest["total_settled_frames"] >= minimum == 4032
    assert manifest["settled_frames_per_state_per_block"] >= 8


def test_campaign_refuses_a_plan_below_the_frame_minimum() -> None:
    with pytest.raises(ExperimentIIIError) as error:
        campaign_manifest(frames_per_slot=1)
    assert error.value.blocker == "P0_TECHNICAL_FAIL"


def test_abba_order_is_balanced_across_replicate_blocks() -> None:
    units = campaign_units()
    first = [u for u in units if u.block_index == 0][0]
    second = [u for u in units if u.block_index == 1][0]
    assert first.abba_order == ("P", "A", "A", "P")
    assert second.abba_order == ("A", "P", "P", "A")


def test_campaign_state_resumes_without_remeasuring(tmp_path: Path) -> None:
    units = campaign_units()[:5]
    path = _state_path(tmp_path)
    state = P0CampaignState(path, authority_sha256="A", source_closure="S", namespace_root=tmp_path)
    state.mark_complete(units[0], {"frames": 16})
    state.mark_complete(units[1], {"frames": 16})
    state.save()

    resumed = P0CampaignState(path, authority_sha256="A", source_closure="S", namespace_root=tmp_path)
    assert resumed.is_complete(units[0].unit_id)
    assert [u.unit_id for u in resumed.pending(units)] == [
        u.unit_id for u in units[2:]
    ]


def test_campaign_state_refuses_an_authority_change(tmp_path: Path) -> None:
    path = _state_path(tmp_path)
    P0CampaignState(path, authority_sha256="A", source_closure="S", namespace_root=tmp_path).save()
    with pytest.raises(ExperimentIIIError) as error:
        P0CampaignState(path, authority_sha256="DIFFERENT", source_closure="S", namespace_root=tmp_path)
    assert error.value.blocker == "PROVENANCE_AUTHORITY_DRIFT"


def test_campaign_state_refuses_a_source_change(tmp_path: Path) -> None:
    path = _state_path(tmp_path)
    P0CampaignState(path, authority_sha256="A", source_closure="S", namespace_root=tmp_path).save()
    with pytest.raises(ExperimentIIIError) as error:
        P0CampaignState(path, authority_sha256="A", source_closure="DIFFERENT", namespace_root=tmp_path)
    assert error.value.blocker == "SOURCE_CLOSURE_DRIFT"


def test_a_failed_attempt_never_overwrites_a_completed_unit(tmp_path: Path) -> None:
    unit = campaign_units()[0]
    state = P0CampaignState(
        _state_path(tmp_path),
        authority_sha256="A",
        source_closure="S",
        namespace_root=tmp_path,
    )
    state.mark_complete(unit, {"frames": 16})
    state.mark_attempt(unit, "CAPTURE_STALE_FRAME", "late failure")
    assert state.is_complete(unit.unit_id)


# ==========================================================================
# amendment provenance
# ==========================================================================


def test_amendment_3_is_recorded_as_prospective() -> None:
    record = machine_authority()["authority_amendment_3"]
    assert record["scientific_outcomes_existed_before_amendment"] is False
    assert record["p0_frames_observed"] == 0
    assert record["mineworld_outcomes_observed"] == 0
    assert record["production_outcomes_observed"] == 0
    assert record["iii_a_scientific_design_changed"] is False
    assert record["iii_b_scientific_design_changed"] is False
    assert record["predecessor_authority_version"] == "v1.5"


def test_the_scientific_core_is_unchanged_by_the_amendment() -> None:
    p0 = machine_authority()["p0_rve"]
    assert p0["selection_zones"] == {
        "L1": [0.6, 0.85],
        "L2": [0.3, 0.55],
        "L3": [0.08, 0.25],
    }
    assert p0["selection_targets"] == [0.725, 0.425, 0.165]
    assert p0["minimum_adjacent_median_separation"] == 0.12
    assert p0["placement_bootstrap_replicates"] == 10000
    assert p0["minimum_l3_excess_energy_to_noise_ratio"] == 5.0
    assert p0["maximum_within_placement_replicate_cv"] == 0.15
    assert len(machine_authority()["p0_candidate_roster"]) == 12


def test_present_absent_semantics_are_frozen() -> None:
    semantics = machine_authority()["p0_rve"]["present_absent_scene_semantics"]
    assert semantics["only_target_presence_differs"] is True
    assert semantics["wall_material_identical_between_present_and_absent"] is True
    assert semantics["target_presence_is_an_independent_axis"] is True
    assert semantics["candidate_absent"] == "SAME_STAINED_GLASS_MATERIAL_AND_TARGET_ABSENT"


def test_a_units_four_captures_each_restart_their_tick_counter() -> None:
    """The real evidence shape: four captures, each starting again at tick 0.

    ``capture_p0_unit`` concatenates a unit's four ABBA captures before handing
    them to the liveness contract. The mod restarts ``server_tick`` at 0 for
    every capture and keys its lockstep gate on ``(episodeId, serverTick)``, so
    the concatenation repeats 0..n four times. Verifying the bare tick rejected
    every real unit with "duplicated tick identities"; no synthetic fixture in
    this file had that shape, so nothing caught it before the apparatus ran.
    """
    frames = [
        frame
        for slot in range(4)
        for frame in _frames(8, episode_id=8_000_000 + slot)
    ]
    report = verify_capture_tick_integrity(frames, expected_total=32)
    assert report["captures"] == 4
    assert report["accepted_frames"] == 32
    assert report["tick_identity"] == "(episode_id, server_tick)"

    liveness = verify_unit_liveness(
        frames=frames,
        probes=[_probe()],
        process_alive=True,
        expected_frames=32,
    )
    assert liveness["passed"] is True
    assert liveness["ticks"]["scope"] == "PER_CAPTURE_EPISODE"


def test_a_gap_inside_one_capture_still_fails() -> None:
    """Per-capture scope must not weaken the frozen tick evidence."""
    frames = [{"episode_id": 1, "tick": tick} for tick in (0, 1, 3, 4)]
    with pytest.raises(ExperimentIIIError) as error:
        verify_capture_tick_integrity(frames)
    assert error.value.blocker == "TIMING_CARDINALITY_MISMATCH"


def test_a_duplicate_inside_one_capture_still_fails() -> None:
    frames = [{"episode_id": 1, "tick": tick} for tick in (0, 1, 1, 2)]
    with pytest.raises(ExperimentIIIError) as error:
        verify_capture_tick_integrity(frames)
    assert error.value.blocker == "TIMING_CARDINALITY_MISMATCH"


def test_a_frame_without_its_episode_is_only_half_an_identity() -> None:
    with pytest.raises(ExperimentIIIError) as error:
        verify_capture_tick_integrity([{"tick": 0}])
    assert error.value.blocker == "TIMING_CARDINALITY_MISMATCH"


def test_a_transition_bracketed_by_two_captures_counts_as_advanced() -> None:
    """The real bracket: two captures, each ending at its own tick 7.

    ``capture_p0_unit`` brackets every transition with two SEPARATE captures.
    The mod restarts ``server_tick`` at 0 per capture, so the mandatory probe
    read ``7 -> 7`` and every ABBA target transition read ``7 -> 0``. Comparing
    the bare tick therefore reported a correctly captured transition as a world
    that never advanced, and no fixture here had that shape.
    """
    mandatory = LivenessProbe(
        "MANDATORY_PRE_CAPTURE_LIVENESS_PROBE",
        before_hash="a", after_hash="b",
        before_tick=7, after_tick=7,
        before_episode=8_001_050, after_episode=8_001_051,
    )
    assert mandatory.tick_advanced is True
    assert assert_transition_observed(mandatory)["framebuffer_changed"] is True

    abba = LivenessProbe(
        "TARGET_PRESENT_TO_ABSENT",
        before_hash="a", after_hash="b",
        before_tick=7, after_tick=0,
        before_episode=8_001_000, after_episode=8_001_001,
    )
    assert abba.tick_advanced is True
    assert assert_transition_observed(abba)["before_episode"] == 8_001_000


def test_a_frozen_world_inside_one_capture_still_fails() -> None:
    """Per-pair ordering must not weaken the frozen tick guard."""
    frozen = LivenessProbe(
        "TARGET_PRESENT_TO_ABSENT",
        before_hash="a", after_hash="b",
        before_tick=5, after_tick=5,
        before_episode=7, after_episode=7,
    )
    assert frozen.tick_advanced is False
    with pytest.raises(ExperimentIIIError) as error:
        assert_transition_observed(frozen)
    assert error.value.blocker == "TIMING_CARDINALITY_MISMATCH"


def test_an_unchanged_framebuffer_across_captures_is_still_stale() -> None:
    stale = LivenessProbe(
        "TARGET_PRESENT_TO_ABSENT",
        before_hash="same", after_hash="same",
        before_tick=7, after_tick=0,
        before_episode=1, after_episode=2,
    )
    with pytest.raises(ExperimentIIIError) as error:
        assert_transition_observed(stale)
    assert error.value.blocker == "CAPTURE_STALE_FRAME"
