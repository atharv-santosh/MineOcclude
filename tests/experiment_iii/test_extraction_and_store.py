"""I09 / I10 — token slices, one-forward extraction, and tensor storage.

Covers A.13, A.16, A.17, A.18, A.28 and the action-contamination checks, against a
deterministic stub decoder. No MineWorld, no GPU.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pytest

from mineocclude.experiment_iii.activation_store import (
    BYTES_PER_ROW_TENSOR,
    EXPECTED_DTYPE,
    EXPECTED_NPY_BYTES,
    EXPECTED_SHAPE,
    NPY_HEADER_BYTES,
    UNITS_PER_CAPTURE,
    build_extraction_inventory,
    validate_activation_array,
    validate_extraction_inventory,
    write_activation_array,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.extraction import (
    SELECTED_LAYERS,
    TRANSIENT_HOOK_LAYER_COUNT,
    ExtractionCounter,
    ForwardResult,
    assert_full_sequence_coverage,
    assert_semantic_slice_identity,
    extract_capture,
    extract_target_row,
)
from mineocclude.experiment_iii.schema import TemporalSlice
from mineocclude.experiment_iii.slices import (
    HIDDEN_WIDTH,
    SEQUENCE_LENGTH,
    TOKENS_PER_PAIR,
    VISUAL_TOKENS_PER_PAIR,
    action_positions,
    slice_spec,
    verify_slice_arithmetic,
    visual_positions,
)

CONTEXT_PAIRS = 16
TRAJECTORY = "e3_t01__L2"


# --------------------------------------------------------------------------
# Deterministic stub decoder
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class StubIdentity:
    trajectory_id: str
    model_frame_idx: int


@dataclass(frozen=True)
class StubSpan:
    identity: StubIdentity
    pair_index: int
    visual_positions: tuple[int, ...]
    action_positions: tuple[int, ...]


@dataclass(frozen=True)
class StubMap:
    trajectory_id: str
    sequence_length: int
    spans: tuple[StubSpan, ...]


def _token_map(target_row: int, *, trajectory_id: str = TRAJECTORY) -> StubMap:
    spans = []
    for pair in range(CONTEXT_PAIRS):
        frame = target_row - (CONTEXT_PAIRS - 1 - pair)
        spans.append(
            StubSpan(
                identity=StubIdentity(trajectory_id, frame),
                pair_index=pair,
                visual_positions=visual_positions(pair),
                action_positions=action_positions(pair),
            )
        )
    return StubMap(trajectory_id, SEQUENCE_LENGTH, tuple(spans))


class StubDecoder:
    """Every token position carries its own index, so slices are identifiable."""

    def __init__(self, *, layers=SELECTED_LAYERS, map_builder=_token_map):
        self.layers = tuple(layers)
        self.forwards = 0
        self._map_builder = map_builder

    def teacher_forced(self, *, trajectory_id: str, model_frame_idx: int):
        self.forwards += 1
        base = np.arange(SEQUENCE_LENGTH, dtype=np.float32).reshape(
            SEQUENCE_LENGTH, 1
        )
        activations = {}
        for layer in self.layers:
            block = np.repeat(base, HIDDEN_WIDTH, axis=1) + layer * 100_000.0
            activations[layer] = block[None, :, :]
        return ForwardResult(
            layer_activations=activations,
            frame_token_map=self._map_builder(
                model_frame_idx, trajectory_id=trajectory_id
            ),
            trajectory_id=trajectory_id,
            model_frame_idx=model_frame_idx,
        )


# --------------------------------------------------------------------------
# Token-slice numeric fixture (authority 8.4)
# --------------------------------------------------------------------------

def test_token_slice_arithmetic_matches_the_authority():
    report = verify_slice_arithmetic()
    assert 14 * 347 == 4858
    assert 15 * 347 == 5205
    assert 16 * 347 == 5552 == SEQUENCE_LENGTH
    previous = slice_spec(TemporalSlice.PREVIOUS)
    current = slice_spec(TemporalSlice.CURRENT)
    assert (previous.start, previous.stop_exclusive) == (4858, 5194)
    assert (current.start, current.stop_exclusive) == (5205, 5541)
    assert previous.python_slice == slice(4858, 5194)
    assert current.python_slice == slice(5205, 5541)
    assert report["selected_visual_disjoint_from_actions"] is True


def test_excluded_action_ranges():
    previous = slice_spec(TemporalSlice.PREVIOUS)
    current = slice_spec(TemporalSlice.CURRENT)
    assert (previous.excluded_action_start, previous.excluded_action_stop_exclusive - 1) == (
        5194,
        5204,
    )
    assert (current.excluded_action_start, current.excluded_action_stop_exclusive - 1) == (
        5541,
        5551,
    )


def test_pair_ordinals_and_token_counts():
    assert slice_spec(TemporalSlice.PREVIOUS).pair_index == 14
    assert slice_spec(TemporalSlice.CURRENT).pair_index == 15
    assert slice_spec(TemporalSlice.PREVIOUS).token_count == VISUAL_TOKENS_PER_PAIR == 336
    assert TOKENS_PER_PAIR == 347


# --------------------------------------------------------------------------
# A.16 — one forward, three layers, two slices
# --------------------------------------------------------------------------

def test_single_forward_yields_three_layers_and_both_slices():
    decoder = StubDecoder()
    harvested = extract_target_row(decoder, trajectory_id=TRAJECTORY, target_row=48)
    assert decoder.forwards == 1
    assert set(harvested) == {
        (layer, name) for layer in SELECTED_LAYERS for name in TemporalSlice
    }
    for array in harvested.values():
        assert array.shape == (VISUAL_TOKENS_PER_PAIR, HIDDEN_WIDTH)


def test_selected_layers_are_exactly_4_10_19():
    assert SELECTED_LAYERS == (4, 10, 19)
    assert TRANSIENT_HOOK_LAYER_COUNT == 20
    assert len(SELECTED_LAYERS) == 3


def test_slices_come_from_the_right_token_positions():
    decoder = StubDecoder()
    harvested = extract_target_row(decoder, trajectory_id=TRAJECTORY, target_row=48)
    previous = harvested[(19, TemporalSlice.PREVIOUS)]
    current = harvested[(19, TemporalSlice.CURRENT)]
    # Each token's value encodes its sequence position (plus the layer offset).
    assert previous[0, 0] == 4858 + 19 * 100_000
    assert previous[-1, 0] == 5193 + 19 * 100_000
    assert current[0, 0] == 5205 + 19 * 100_000
    assert current[-1, 0] == 5540 + 19 * 100_000


def test_no_action_token_is_harvested():
    decoder = StubDecoder()
    harvested = extract_target_row(decoder, trajectory_id=TRAJECTORY, target_row=48)
    excluded = set(range(5194, 5205)) | set(range(5541, 5552))
    for (layer, _name), array in harvested.items():
        values = {int(v) - layer * 100_000 for v in array[:, 0]}
        assert not values & excluded


def test_nineteen_forwards_for_a_full_capture():
    decoder = StubDecoder()
    rows = list(range(30, 49))
    stacked, counter = extract_capture(
        decoder, trajectory_id=TRAJECTORY, target_rows=rows
    )
    assert decoder.forwards == 19
    assert counter.forwards == 19
    assert len(stacked) == UNITS_PER_CAPTURE == 6
    for array in stacked.values():
        assert array.shape == EXPECTED_SHAPE


def test_forward_count_excess_is_detected():
    counter = ExtractionCounter(expected_per_capture=19)
    for _ in range(20):
        counter.record()
    with pytest.raises(ExperimentIIIError) as caught:
        counter.assert_within_budget()
    assert caught.value.blocker == "EXTRACTION_FORWARD_COUNT_EXCESS"


def test_missing_layer_is_detected():
    decoder = StubDecoder(layers=(4, 10))
    with pytest.raises(ExperimentIIIError) as caught:
        extract_target_row(decoder, trajectory_id=TRAJECTORY, target_row=48)
    assert caught.value.blocker == "HOOK_LAYER_MISSING"


# --------------------------------------------------------------------------
# Semantic frame identity — shape agreement is NOT sufficient
# --------------------------------------------------------------------------

def test_semantic_assertions_pass_on_a_correct_map():
    assert_semantic_slice_identity(_token_map(48), 48, trajectory_id=TRAJECTORY)


def test_correctly_shaped_tensor_from_the_wrong_pair_is_rejected():
    """The negative control the authority specifically demands."""

    def wrong_frame_map(target_row, *, trajectory_id=TRAJECTORY):
        spans = list(_token_map(target_row, trajectory_id=trajectory_id).spans)
        # Same shape, same positions, WRONG frame identity on the CURRENT pair.
        spans[-1] = StubSpan(
            identity=StubIdentity(trajectory_id, target_row + 7),
            pair_index=spans[-1].pair_index,
            visual_positions=spans[-1].visual_positions,
            action_positions=spans[-1].action_positions,
        )
        return StubMap(trajectory_id, SEQUENCE_LENGTH, tuple(spans))

    decoder = StubDecoder(map_builder=wrong_frame_map)
    with pytest.raises(ExperimentIIIError) as caught:
        extract_target_row(decoder, trajectory_id=TRAJECTORY, target_row=48)
    assert caught.value.blocker == "TOKEN_FRAME_IDENTITY_MISMATCH"


def test_previous_must_be_the_frame_before_current():
    def shifted(target_row, *, trajectory_id=TRAJECTORY):
        spans = list(_token_map(target_row, trajectory_id=trajectory_id).spans)
        spans[-2] = StubSpan(
            identity=StubIdentity(trajectory_id, target_row),
            pair_index=spans[-2].pair_index,
            visual_positions=spans[-2].visual_positions,
            action_positions=spans[-2].action_positions,
        )
        return StubMap(trajectory_id, SEQUENCE_LENGTH, tuple(spans))

    with pytest.raises(ExperimentIIIError) as caught:
        assert_semantic_slice_identity(shifted(48), 48, trajectory_id=TRAJECTORY)
    assert caught.value.blocker == "TOKEN_FRAME_IDENTITY_MISMATCH"


def test_wrong_pair_index_is_rejected():
    spans = list(_token_map(48).spans)
    spans[-1] = StubSpan(
        identity=spans[-1].identity,
        pair_index=13,
        visual_positions=spans[-1].visual_positions,
        action_positions=spans[-1].action_positions,
    )
    with pytest.raises(ExperimentIIIError) as caught:
        assert_semantic_slice_identity(
            StubMap(TRAJECTORY, SEQUENCE_LENGTH, tuple(spans)), 48,
            trajectory_id=TRAJECTORY,
        )
    assert caught.value.blocker == "TOKEN_SPAN_MISMATCH"


def test_incomplete_sequence_coverage_is_rejected():
    spans = list(_token_map(48).spans)[:-1]
    with pytest.raises(ExperimentIIIError) as caught:
        assert_full_sequence_coverage(
            StubMap(TRAJECTORY, SEQUENCE_LENGTH, tuple(spans))
        )
    assert caught.value.blocker == "TOKEN_SEQUENCE_LENGTH_MISMATCH"


def test_wrong_trajectory_is_rejected():
    with pytest.raises(ExperimentIIIError) as caught:
        assert_semantic_slice_identity(
            _token_map(48, trajectory_id="e3_t02__L2"), 48, trajectory_id=TRAJECTORY
        )
    assert caught.value.blocker == "TOKEN_FRAME_IDENTITY_MISMATCH"


# --------------------------------------------------------------------------
# A.13 — context age from explicit frame identities
# --------------------------------------------------------------------------

def test_context_age_is_verified_from_explicit_frame_identities():
    target_row = 48
    token_map = _token_map(target_row)
    frames = [span.identity.model_frame_idx for span in token_map.spans]
    assert frames == list(range(target_row - 15, target_row + 1))
    for age in (1, 15):
        assert (target_row - age) in frames, age
    for age in (16, 19):
        assert (target_row - age) not in frames, age


def test_wrong_identity_frame_in_context_is_detected():
    spans = list(_token_map(48).spans)
    spans[0] = StubSpan(
        identity=StubIdentity(TRAJECTORY, 999),
        pair_index=spans[0].pair_index,
        visual_positions=spans[0].visual_positions,
        action_positions=spans[0].action_positions,
    )
    frames = [span.identity.model_frame_idx for span in spans]
    assert frames != list(range(33, 49))


# --------------------------------------------------------------------------
# A.17 / A.18 — shape, dtype and byte count
# --------------------------------------------------------------------------

def test_byte_arithmetic():
    assert 336 * 2048 * 2 == BYTES_PER_ROW_TENSOR == 1_376_256
    assert 19 * BYTES_PER_ROW_TENSOR + NPY_HEADER_BYTES == EXPECTED_NPY_BYTES
    assert EXPECTED_NPY_BYTES == 26_148_992
    assert EXPECTED_SHAPE == (19, 336, 2048)


def _sample_array(seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.standard_normal(EXPECTED_SHAPE).astype(np.float16)


@pytest.fixture(scope="module")
def written_capture(tmp_path_factory):
    # The namespace guard admits only Experiment III roots, so the synthetic
    # capture lives under data/experiment_iii/ inside a temporary repo root.
    namespace_root = tmp_path_factory.mktemp("repo")
    root = namespace_root / "data" / "experiment_iii" / "captures" / "e3_t01__L2"
    written = {}
    for layer in SELECTED_LAYERS:
        for name in TemporalSlice:
            written[(layer, name.value)] = write_activation_array(
                root,
                layer,
                name,
                _sample_array(layer * 10 + len(name.value)),
                namespace_root=namespace_root,
            )
    inventory = build_extraction_inventory(
        identity="e3_t01",
        condition_id="L2",
        target_model_frame_indices=list(range(30, 49)),
        written=written,
        hook_site="decoder.layers[*].residual",
        preprocessing_identity="frozen-preprocessing-v1",
        checkpoint_identity="a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5",
        source_capture_hash="c0ffee" * 10 + "abcd",
        token_position_hash=hashlib.sha256(b"4858:5194|5205:5541").hexdigest(),
    )
    return root, inventory


def test_written_arrays_are_exactly_the_frozen_size(written_capture):
    root, inventory = written_capture
    for row in inventory["artifacts"]:
        path = root / row["path"]
        assert path.stat().st_size == EXPECTED_NPY_BYTES
        array = np.load(path)
        assert array.shape == EXPECTED_SHAPE
        assert array.dtype.str == EXPECTED_DTYPE == "<f2"


def test_six_arrays_per_capture(written_capture):
    _root, inventory = written_capture
    assert len(inventory["artifacts"]) == UNITS_PER_CAPTURE == 6
    assert inventory["layer_indices"] == [4, 10, 19]
    assert sorted(inventory["temporal_slices"]) == ["CURRENT", "PREVIOUS"]


def test_inventory_is_not_the_legacy_twenty_layer_contract(written_capture):
    _root, inventory = written_capture
    assert inventory["layer_indices"] != list(range(20))
    assert len(inventory["artifacts"]) != 20


def test_independent_validator_accepts_a_clean_capture(written_capture):
    root, inventory = written_capture
    validated = validate_extraction_inventory(
        root, inventory, expected_target_rows=list(range(30, 49))
    )
    assert len(validated) == 6


def test_transposed_array_is_rejected(tmp_path):
    with pytest.raises(ExperimentIIIError) as caught:
        write_activation_array(
            tmp_path / "data" / "experiment_iii" / "c",
            19,
            TemporalSlice.CURRENT,
            np.zeros((19, 2048, 336), np.float16),
            namespace_root=tmp_path,
        )
    assert caught.value.blocker == "TENSOR_SHAPE_MISMATCH"


def test_big_endian_write_is_rejected(tmp_path, written_capture):
    root, inventory = written_capture
    row = dict(inventory["artifacts"][0])
    path = tmp_path / "big_endian.npy"
    np.save(path, _sample_array().astype(">f2"), allow_pickle=False)
    row["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    row["byte_size"] = path.stat().st_size
    with pytest.raises(ExperimentIIIError) as caught:
        validate_activation_array(path, row)
    assert caught.value.blocker in {"TENSOR_DTYPE_MISMATCH", "TENSOR_BYTE_SIZE_MISMATCH"}


def test_nonfinite_values_are_refused(tmp_path):
    array = _sample_array()
    array[0, 0, 0] = np.inf
    with pytest.raises(ExperimentIIIError) as caught:
        write_activation_array(
            tmp_path / "data" / "experiment_iii" / "c",
            19,
            TemporalSlice.CURRENT,
            array,
            namespace_root=tmp_path,
        )
    assert caught.value.blocker == "TENSOR_NONFINITE"


# --------------------------------------------------------------------------
# A.28 — corrupted artifact rejection
# --------------------------------------------------------------------------

@pytest.mark.parametrize("corruption", ["truncate", "bitflip", "zeropad"])
def test_corrupted_arrays_are_rejected(written_capture, tmp_path, corruption):
    root, inventory = written_capture
    row = dict(inventory["artifacts"][0])
    payload = bytearray((root / row["path"]).read_bytes())
    if corruption == "truncate":
        payload = payload[:-4096]
    elif corruption == "bitflip":
        payload[NPY_HEADER_BYTES + 11] ^= 0xFF
    else:
        payload.extend(b"\x00" * 128)
    target = tmp_path / f"{corruption}.npy"
    target.write_bytes(bytes(payload))
    with pytest.raises(ExperimentIIIError) as caught:
        validate_activation_array(target, row)
    assert caught.value.blocker in {
        "TENSOR_BYTE_SIZE_MISMATCH",
        "TENSOR_HASH_MISMATCH",
    }


def test_injected_nan_is_rejected_by_the_validator(written_capture, tmp_path):
    root, inventory = written_capture
    row = dict(inventory["artifacts"][0])
    array = np.load(root / row["path"])
    array[3, 5, 7] = np.nan
    target = tmp_path / "nan.npy"
    np.save(target, array, allow_pickle=False)
    row["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    with pytest.raises(ExperimentIIIError) as caught:
        validate_activation_array(target, row)
    assert caught.value.blocker == "TENSOR_NONFINITE"


def test_missing_provenance_field_is_rejected(written_capture):
    root, inventory = written_capture
    row = dict(inventory["artifacts"][0])
    row["checkpoint_identity"] = ""
    with pytest.raises(ExperimentIIIError) as caught:
        validate_activation_array(root / row["path"], row)
    assert caught.value.blocker == "PROVENANCE_BINDING_MISSING"


def test_incomplete_inventory_is_rejected(written_capture):
    root, inventory = written_capture
    broken = dict(inventory)
    broken["artifacts"] = inventory["artifacts"][:5]
    with pytest.raises(ExperimentIIIError) as caught:
        validate_extraction_inventory(root, broken)
    assert caught.value.blocker == "EXTRACTION_INVENTORY_INCOMPLETE"


def test_source_capture_drift_is_detected(written_capture):
    root, inventory = written_capture
    with pytest.raises(ExperimentIIIError) as caught:
        validate_extraction_inventory(
            root, inventory, source_capture_hash="deadbeef" * 8
        )
    assert caught.value.blocker == "EXTRACTION_SOURCE_CAPTURE_DRIFT"


def test_target_row_order_mismatch_is_detected(written_capture):
    root, inventory = written_capture
    with pytest.raises(ExperimentIIIError) as caught:
        validate_extraction_inventory(
            root, inventory, expected_target_rows=list(range(31, 50))
        )
    assert caught.value.blocker == "TARGET_ROW_MISMATCH"


def test_unsafe_artifact_path_is_refused(written_capture):
    root, inventory = written_capture
    broken = dict(inventory)
    artifacts = [dict(row) for row in inventory["artifacts"]]
    artifacts[0]["path"] = "../escape.npy"
    broken["artifacts"] = artifacts
    with pytest.raises(ExperimentIIIError) as caught:
        validate_extraction_inventory(root, broken)
    assert caught.value.blocker == "PROVENANCE_NAMESPACE_VIOLATION"
