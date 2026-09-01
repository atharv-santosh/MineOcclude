"""Coverage for the A5 pilot extraction path (authority 6A, 8.4, 8.5).

Three things are load-bearing here and each is tested against the real
component, not a paraphrase of it:

* **A5_EXTRACTION is a stage of its own.** It is authorized before P2; A9 is not,
  and neither is production capture. If those three could be confused, the
  program could either stall the pilot behind a freeze it does not need or spend
  production scope on a debug run.
* **The MineWorld adapter is actually invoked.** The stub below implements the
  frozen :class:`MineWorldAdapter` protocol and returns the real adapter
  dataclasses, so the seam under test is the one production uses. What it does
  *not* do is run MineWorld: no weights, no CUDA, no forward.
* **One forward per target row, and everything comes out of it.** Three layers
  and both temporal slices from a single ``teacher_forced`` call, counted.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.contracts.trajectory import validate_trajectory_package
from mineocclude.experiment_iii.activation_store import (
    EXPECTED_DTYPE,
    EXPECTED_NPY_BYTES,
    EXPECTED_SHAPE,
    UNITS_PER_CAPTURE,
)
from mineocclude.experiment_iii.authority import (
    PILOT_IDENTITY_IDS,
    PRODUCTION_IDENTITY_IDS,
    TARGET_ROWS_PER_CAPTURE,
    machine_authority,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.extraction import (
    SELECTED_LAYERS,
    TRANSIENT_HOOK_LAYER_COUNT,
)
from mineocclude.experiment_iii.host_preflight import (
    A5_EXTRACTION_STAGE,
    CAPTURE_HOST_STAGES,
    EXTRACTION_HOST_STAGES,
)
from mineocclude.experiment_iii.p1_extraction import (
    CANONICAL_INVENTORY_NAME,
    HOOK_SITE,
    PERSON_A_RUNTIME_SCRIPTED_IMPULSE,
    PILOT_ARRAYS,
    PILOT_CAPTURES,
    PILOT_FORWARDS,
    PILOT_TARGET_ROWS,
    MineWorldPilotDecoder,
    P1ExtractionCampaign,
    assert_pilot_identity,
    authorize_a5_extraction,
    build_context_package,
    capture_stream_rows,
    context_window,
    extract_pilot_capture,
    refuse_production_extraction,
    token_position_hash,
)
from mineocclude.experiment_iii.schema import TemporalSlice
from mineocclude.experiment_iii.slices import HIDDEN_WIDTH, SEQUENCE_LENGTH
from mineocclude.models import mineworld_adapter as adapter_module

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CAPTURES = REPOSITORY_ROOT / "data" / "experiment_iii" / "p1" / "captures"
BANKED_UNIT = CAPTURES / "e3_p90__L0"

requires_banked_captures = pytest.mark.skipif(
    not (BANKED_UNIT / "capture_completion.json").is_file(),
    reason="the banked P1 capture units are not present in this working tree",
)


# --------------------------------------------------------------------------
# A stub adapter that is the real protocol
# --------------------------------------------------------------------------


def _runtime_identity() -> adapter_module.MineWorldRuntimeIdentity:
    """A structurally valid runtime identity carrying the frozen digests.

    Every field is validated by the frozen dataclass, so this cannot drift into
    a shape the real ``load_runtime`` would not also produce.
    """
    extraction = machine_authority()["extraction"]
    return adapter_module.MineWorldRuntimeIdentity(
        schema_version=SCHEMA_VERSION,
        adapter_api_version=adapter_module.MINEWORLD_ADAPTER_API_VERSION,
        runtime_id="experiment-iii-a5-pilot-stub",
        mineocclude_revision="0" * 40,
        mineworld_source_revision="1" * 40,
        modelscope_asset_revision="2" * 40,
        model_config_sha256="3" * 64,
        main_checkpoint_sha256=str(extraction["main_checkpoint_sha256"]),
        vae_config_sha256="4" * 64,
        vae_checkpoint_sha256=str(extraction["vae_sha256"]),
        environment_report_sha256="5" * 64,
        preprocessing_identity="person_a_legacy_preprocessing",
        action_conversion_identity="person_a_official_action_conversion",
        model_class="MineWorld",
        transformer_class="MineWorldTransformer",
        vae_class="MineWorldVAE",
        decoder_layer_path="model.transformer.layers",
        layer_count=TRANSIENT_HOOK_LAYER_COUNT,
        hidden_size=HIDDEN_WIDTH,
        max_position_embeddings=8192,
        visual_tokens_per_frame=336,
        action_tokens_per_frame=11,
        tokens_per_pair=347,
        max_context_pairs=16,
        precision="float16",
        device="cuda",
    )


#: One ``[1, 5552, 2048]`` float16 residual, built once and shared by every
#: stub layer and every stub forward. Twenty freshly generated residuals per
#: forward would be ~450 MiB of allocation per target row and would make this
#: file the slowest in the suite for no extra evidence: what the tests below
#: check is that each *position* is sliced from the right pair, and a
#: position-varying array establishes that as well as a random one does.
_RESIDUAL = (
    (
        np.arange(SEQUENCE_LENGTH, dtype=np.float32)[:, None] * 0.001
        + np.arange(HIDDEN_WIDTH, dtype=np.float32)[None, :] * 0.0001
    )
    .astype(np.float16)
    .reshape(1, SEQUENCE_LENGTH, HIDDEN_WIDTH)
)


class _RecordingHookManager:
    """A ScopedHookManager stand-in that records what a forward captured."""

    def __init__(self, modules: tuple[tuple[str, object], ...], seed: int) -> None:
        self.modules = modules
        self.seed = seed
        self.closed = False
        self._captures: dict[int, Any] = {}

    def __enter__(self) -> "_RecordingHookManager":
        for index in range(len(self.modules)):
            self._captures[index] = type("Capture", (), {"tensor": _RESIDUAL})()
        return self

    def __exit__(self, *_exc: object) -> bool:
        self.closed = True
        return False

    @property
    def captures(self) -> dict[int, Any]:
        return dict(self._captures)


class StubMineWorldAdapter:
    """The frozen adapter protocol, implemented without MineWorld.

    Every value it returns is a real adapter dataclass and therefore passes the
    adapter's own validation. It records each operation so a test can prove the
    pilot decoder actually drove the boundary rather than shortcutting it.
    """

    def __init__(self) -> None:
        self.runtime_identity = _runtime_identity()
        self.calls: list[str] = []
        self.teacher_forced_calls = 0
        self.tokenized_target_rows: list[int] = []
        self.hook_context_entered = 0

    def load_runtime(self, request: Any) -> Any:  # pragma: no cover - unused here
        self.calls.append("load_runtime")
        return self.runtime_identity

    def validate_trajectory(self, request: Any) -> Any:
        self.calls.append("validate_trajectory")
        result = validate_trajectory_package(request.document)
        if not result.accepted:
            raise AssertionError(
                "the stub was handed a package the frozen contract rejects: "
                + result.rejections[0].message
            )
        identities = tuple(
            adapter_module.FrameIdentity(
                schema_version=SCHEMA_VERSION,
                trajectory_id=str(row["trajectory_id"]),
                model_frame_idx=int(row["model_frame_idx"]),
            )
            for row in request.document["streams"]["frame_map"]
        )
        return adapter_module.ValidatedTrajectory(
            schema_version=SCHEMA_VERSION,
            trajectory_id=request.trajectory_id,
            accepted_manifest_sha256=request.accepted_manifest_sha256,
            source_document_sha256=hashlib.sha256(
                json.dumps(
                    request.document, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest(),
            frame_identities=identities,
        )

    def preprocess_frame(self, request: Any) -> Any:
        self.calls.append("preprocess_frame")
        return adapter_module.PreprocessedFrame(
            identity=request.identity,
            source_frame_idx=request.source_frame_idx,
            shape=(3, 224, 384),
            dtype="float32",
            color_order="RGB",
            content_sha256=hashlib.sha256(
                f"{request.identity.key}".encode("utf-8")
            ).hexdigest(),
            frame=request.frame,
            preprocessing_profile="person_a_legacy_preprocessing",
        )

    def convert_action(self, request: Any) -> Any:
        self.calls.append("convert_action")
        return adapter_module.ConvertedAction(
            identity=request.identity,
            action_idx=request.action_idx,
            token_ids=tuple(8192 + index for index in range(11)),
            converter_identity="person_a_official_action_conversion",
            content_sha256=hashlib.sha256(
                f"{request.identity.key}:action".encode("utf-8")
            ).hexdigest(),
        )

    def tokenize_trajectory(self, request: Any) -> Any:
        self.calls.append("tokenize_trajectory")
        identities = tuple(
            frame.identity for frame in request.frames
        )
        spans = tuple(
            adapter_module.FrameTokenSpan(
                identity=identity,
                pair_index=index,
                visual_positions=tuple(
                    range(index * 347, index * 347 + 336)
                ),
                action_positions=tuple(
                    range(index * 347 + 336, index * 347 + 347)
                ),
            )
            for index, identity in enumerate(identities)
        )
        token_map = adapter_module.FrameTokenMap(
            schema_version=SCHEMA_VERSION,
            trajectory_id=request.trajectory.trajectory_id,
            sequence_length=len(spans) * 347,
            spans=spans,
        )
        self.tokenized_target_rows.append(spans[-1].identity.model_frame_idx)
        tokens = tuple(range(len(spans) * 347))
        return adapter_module.TokenizedTrajectory(
            runtime_identity=request.runtime_identity,
            trajectory_id=request.trajectory.trajectory_id,
            token_ids=tokens,
            frame_token_map=token_map,
            token_sha256=hashlib.sha256(str(tokens[:8]).encode("utf-8")).hexdigest(),
            frame_token_map_sha256=hashlib.sha256(
                str(token_map.sequence_length).encode("utf-8")
            ).hexdigest(),
        )

    def teacher_forced(self, request: Any) -> Any:
        self.calls.append("teacher_forced")
        self.teacher_forced_calls += 1
        modules = tuple(
            (f"model.transformer.layers.{index}", object())
            for index in range(TRANSIENT_HOOK_LAYER_COUNT)
        )
        manager = request.hook_context_factory(modules)
        with manager:
            self.hook_context_entered += 1
        return adapter_module.TeacherForcedResult(
            runtime_identity=request.runtime_identity,
            trajectory_id=request.trajectory.trajectory_id,
            frame_token_map=request.trajectory.frame_token_map,
            output_shape=(1, len(request.trajectory.token_ids), HIDDEN_WIDTH),
            dtype=request.precision,
            device="cuda",
            output_sha256="a" * 64,
            elapsed_seconds=0.0,
            output={"stub": True},
            result_sha256="b" * 64,
        )

    def free_rollout(self, request: Any) -> Any:  # pragma: no cover - never used
        raise AssertionError("A5 extraction is teacher-forced only")


def _activation_root(tmp_path: Path) -> Path:
    """Where a test may write arrays.

    The namespace guard admits only Experiment III roots, so a test writes into
    ``data/experiment_iii/`` inside a temporary repository root and passes that
    root as ``namespace_root``. The guard therefore still runs -- against the
    temporary tree -- rather than being switched off for the test.
    """
    return tmp_path / "data" / "experiment_iii" / "p1" / "activations"


def _decoder(adapter: StubMineWorldAdapter, unit_dir: Path, trajectory_id: str) -> Any:
    completion = json.loads(
        (unit_dir / "capture_completion.json").read_text(encoding="utf-8")
    )
    return MineWorldPilotDecoder(
        adapter,
        adapter.runtime_identity,
        unit_dir=unit_dir,
        trajectory_id=trajectory_id,
        seed=int(completion["spec"]["seed"]),
        rows=capture_stream_rows(unit_dir),
        impulse_orientation=PERSON_A_RUNTIME_SCRIPTED_IMPULSE,
        hook_manager_factory=lambda modules: _RecordingHookManager(modules, seed=7),
        frame_loader=lambda path: np.zeros((360, 640, 3), dtype=np.uint8),
    )


# --------------------------------------------------------------------------
# Stage binding
# --------------------------------------------------------------------------


def test_a5_extraction_is_a_stage_the_extraction_host_authorizes() -> None:
    """A5's entry names A3 on the extraction host, so that host needs a token."""
    assert A5_EXTRACTION_STAGE == "A5_EXTRACTION"
    assert A5_EXTRACTION_STAGE in EXTRACTION_HOST_STAGES
    assert A5_EXTRACTION_STAGE not in CAPTURE_HOST_STAGES
    assert "A5_CAPTURE" in CAPTURE_HOST_STAGES


def test_a5_extraction_is_not_a9() -> None:
    """Making the pilot equal to A9 would spend production scope on a debug run."""
    assert A5_EXTRACTION_STAGE != "A9"
    assert "A9" in EXTRACTION_HOST_STAGES
    production = machine_authority()["production"]
    assert PILOT_CAPTURES == 10 and int(production["captures"]) == 125
    assert PILOT_FORWARDS == 190 and int(production["target_rows"]) == 2375


def test_a5_pilot_extraction_is_authorized_before_p2() -> None:
    receipt = {
        "passed": True,
        "authorized_stages": list(EXTRACTION_HOST_STAGES),
        "model_identity_checks": _verified_model_checks(),
    }
    authorization = authorize_a5_extraction(receipt)
    assert authorization["authorized"] is True
    assert authorization["requires_model_inference_authorized"] is False
    assert authorization["requires_p2"] is False


def test_a5_extraction_refuses_a_capture_host_receipt() -> None:
    receipt = {
        "passed": True,
        "authorized_stages": list(CAPTURE_HOST_STAGES),
        "model_identity_checks": {"verified": False},
    }
    with pytest.raises(ExperimentIIIError) as error:
        authorize_a5_extraction(receipt)
    assert error.value.blocker == "P2_PREREQUISITE_NOT_PASSED"


def test_a5_extraction_refuses_an_unverified_checkpoint() -> None:
    receipt = {
        "passed": True,
        "authorized_stages": list(EXTRACTION_HOST_STAGES),
        "model_identity_checks": {"verified": False},
    }
    with pytest.raises(ExperimentIIIError) as error:
        authorize_a5_extraction(receipt)
    assert error.value.blocker == "ENV_CHECKPOINT_HASH_MISMATCH"


def _verified_model_checks() -> dict[str, Any]:
    extraction = machine_authority()["extraction"]
    return {
        "verified": True,
        "main_checkpoint": {
            "observed_sha256": extraction["main_checkpoint_sha256"],
            "path": "/weights/model.pt",
        },
        "vae_checkpoint": {
            "observed_sha256": extraction["vae_sha256"],
            "path": "/weights/vae.pt",
        },
    }


def test_a9_production_extraction_is_refused_before_p2() -> None:
    """An A3 receipt naming A9 proves the host, not the program state."""
    with pytest.raises(ExperimentIIIError) as error:
        refuse_production_extraction(
            {"passed": True, "authorized_stages": list(EXTRACTION_HOST_STAGES)}
        )
    assert error.value.blocker == "P2_PREREQUISITE_NOT_PASSED"
    assert "MODEL_INFERENCE_AUTHORIZED" in error.value.message


def test_a9_refusal_is_not_bypassed_by_a_stale_authorization_field() -> None:
    """A banked ``PRODUCTION_AUTHORIZED`` / ``P0_LADDER_ACCEPTED`` is not a gate."""
    with pytest.raises(ExperimentIIIError):
        refuse_production_extraction(
            {
                "passed": True,
                "authorized_stages": ["A9"],
                "PRODUCTION_AUTHORIZED": True,
                "P0_LADDER_ACCEPTED": True,
                "MODEL_INFERENCE_AUTHORIZED": True,
            }
        )


def test_production_capture_is_refused_before_p2() -> None:
    from mineocclude.experiment_iii.p0_analysis import ladder_accepted, production_authorized

    assert ladder_accepted({"P0_LADDER_ACCEPTED": True}) is True
    # An accepted ladder is an A4 verdict and never a production gate.
    assert production_authorized() is False
    assert production_authorized({"P0_LADDER_ACCEPTED": True}) is False
    assert production_authorized({"PRODUCTION_AUTHORIZED": True}) is False


# --------------------------------------------------------------------------
# Identity scope
# --------------------------------------------------------------------------


def test_only_the_two_pilot_identities_reach_extraction() -> None:
    for identity in PILOT_IDENTITY_IDS:
        assert_pilot_identity(identity)
    assert sorted(PILOT_IDENTITY_IDS) == ["e3_p90", "e3_p91"]


def test_a_production_identity_is_refused_before_any_forward() -> None:
    with pytest.raises(ExperimentIIIError) as error:
        assert_pilot_identity(PRODUCTION_IDENTITY_IDS[0])
    assert error.value.blocker == "P1_INCOMPLETE"


def test_an_unknown_identity_is_refused() -> None:
    with pytest.raises(ExperimentIIIError):
        assert_pilot_identity("e3_p99")


def test_the_campaign_refuses_a_production_identity_at_construction(
    tmp_path: Path,
) -> None:
    with pytest.raises(ExperimentIIIError) as error:
        P1ExtractionCampaign(
            [
                {
                    "capture_unit_id": "e3_t01__L0",
                    "identity": PRODUCTION_IDENTITY_IDS[0],
                    "condition_id": "L0",
                    "unit_dir": tmp_path,
                    "seed": 1,
                    "source_capture_hash": "0" * 64,
                    "target_model_frame_indices": list(range(19)),
                }
            ],
            output_root=tmp_path / "out",
            ledger_path=tmp_path / "ledger.jsonl",
            extraction_spec_hash="1" * 64,
            namespace_root=tmp_path,
        )
    assert error.value.blocker == "P1_INCOMPLETE"


# --------------------------------------------------------------------------
# Counts
# --------------------------------------------------------------------------


def test_pilot_counts_equal_the_frozen_authority() -> None:
    pilot = machine_authority()["p1_pilot"]
    assert PILOT_CAPTURES == int(pilot["captures"]) == 10
    assert PILOT_TARGET_ROWS == int(pilot["target_rows"]) == 190
    assert PILOT_FORWARDS == int(pilot["forwards"]) == 190
    assert PILOT_ARRAYS == int(pilot["serialized_npy_arrays"]) == 60
    assert PILOT_ARRAYS == PILOT_CAPTURES * UNITS_PER_CAPTURE


def test_the_canonical_inventory_name_is_the_authority_name() -> None:
    """One name for the inventory, and it is the one the authority uses."""
    assert CANONICAL_INVENTORY_NAME == "extraction_inventory.json"
    inventory = json.loads(
        (
            REPOSITORY_ROOT
            / "docs"
            / "experiment_iii"
            / "final_authorities"
            / "EXPECTED_ARTIFACT_INVENTORY.json"
        ).read_text(encoding="utf-8")
    )
    named = json.dumps(inventory)
    assert CANONICAL_INVENTORY_NAME in named
    assert "activation_inventory.json" not in named


def test_every_consumer_and_producer_uses_the_canonical_inventory_name() -> None:
    validator = (
        REPOSITORY_ROOT / "scripts" / "experiment_iii" / "validate_extraction.py"
    ).read_text(encoding="utf-8")
    handoff = (
        REPOSITORY_ROOT / "scripts" / "experiment_iii" / "build_p1_gpu_handoff.py"
    ).read_text(encoding="utf-8")
    runbook = (
        REPOSITORY_ROOT / "docs" / "experiment_iii" / "p1" / "P1_GPU_SPRINT_RUNBOOK.md"
    ).read_text(encoding="utf-8")
    assert "CANONICAL_INVENTORY_NAME" in validator
    assert '"inventory_name": "extraction_inventory.json"' in handoff
    # The runbook may still explain that the old name was wrong, but it must not
    # instruct anyone to write one.
    assert "at `activations/activation_inventory.json`" not in runbook


# --------------------------------------------------------------------------
# The trajectory package the adapter demands
# --------------------------------------------------------------------------


@requires_banked_captures
def test_capture_streams_join_to_one_row_per_model_frame() -> None:
    rows = capture_stream_rows(BANKED_UNIT)
    assert len(rows) == 180
    assert [row["model_frame_idx"] for row in rows] == list(range(180))


@requires_banked_captures
def test_the_context_window_is_sixteen_complete_pairs() -> None:
    rows = capture_stream_rows(BANKED_UNIT)
    window = context_window(rows, 39)
    assert [row["model_frame_idx"] for row in window] == list(range(24, 40))


@requires_banked_captures
def test_a_target_row_without_a_full_context_is_refused() -> None:
    rows = capture_stream_rows(BANKED_UNIT)
    with pytest.raises(ExperimentIIIError) as error:
        context_window(rows, 3)
    assert error.value.blocker == "EXTRACTION_TEMPORAL_INDEX_MISMATCH"


@requires_banked_captures
def test_the_built_package_satisfies_the_frozen_trajectory_contract() -> None:
    """The adapter accepts only what this contract accepts, so build to it."""
    rows = capture_stream_rows(BANKED_UNIT)
    completion = json.loads(
        (BANKED_UNIT / "capture_completion.json").read_text(encoding="utf-8")
    )
    package = build_context_package(
        BANKED_UNIT,
        rows,
        39,
        trajectory_id="e3_p90__L0",
        seed=int(completion["spec"]["seed"]),
        impulse_orientation=PERSON_A_RUNTIME_SCRIPTED_IMPULSE,
    )
    assert validate_trajectory_package(package).accepted is True
    assert package["media"]["frame_count"] == 16
    assert package["media"]["width"] == 640 and package["media"]["height"] == 360
    for stream in package["streams"].values():
        assert len(stream) == 16


# --------------------------------------------------------------------------
# The one-forward contract, through the real adapter protocol
# --------------------------------------------------------------------------


@requires_banked_captures
def test_the_mineworld_adapter_is_actually_invoked() -> None:
    adapter = StubMineWorldAdapter()
    decoder = _decoder(adapter, BANKED_UNIT, "e3_p90__L0")
    decoder.teacher_forced(trajectory_id="e3_p90__L0", model_frame_idx=39)
    assert adapter.calls[:1] == ["validate_trajectory"]
    assert adapter.calls.count("preprocess_frame") == 16
    assert adapter.calls.count("convert_action") == 16
    assert "tokenize_trajectory" in adapter.calls
    assert adapter.teacher_forced_calls == 1
    assert adapter.hook_context_entered == 1


@requires_banked_captures
def test_exactly_one_forward_per_target_row() -> None:
    adapter = StubMineWorldAdapter()
    decoder = _decoder(adapter, BANKED_UNIT, "e3_p90__L0")
    rows = list(range(39, 39 + TARGET_ROWS_PER_CAPTURE))
    for target_row in rows:
        decoder.teacher_forced(trajectory_id="e3_p90__L0", model_frame_idx=target_row)
    assert adapter.teacher_forced_calls == TARGET_ROWS_PER_CAPTURE == 19
    assert decoder.adapter_forward_calls == 19
    assert adapter.tokenized_target_rows == rows


@requires_banked_captures
def test_all_three_layers_and_both_slices_come_from_the_same_forward() -> None:
    """Not one forward per layer, and not an extra forward for PREVIOUS."""
    from mineocclude.experiment_iii.extraction import extract_target_row

    adapter = StubMineWorldAdapter()
    decoder = _decoder(adapter, BANKED_UNIT, "e3_p90__L0")
    harvested = extract_target_row(
        decoder, trajectory_id="e3_p90__L0", target_row=39
    )
    assert adapter.teacher_forced_calls == 1
    assert set(harvested) == {
        (layer, name) for layer in SELECTED_LAYERS for name in TemporalSlice
    }
    assert len(harvested) == 6
    for array in harvested.values():
        assert array.shape == (336, HIDDEN_WIDTH)
    # The two slices are cut from different pairs of the same residual, so they
    # must not be the same bytes.
    assert not np.array_equal(
        harvested[(4, TemporalSlice.PREVIOUS)], harvested[(4, TemporalSlice.CURRENT)]
    )


@requires_banked_captures
def test_a_forward_that_captures_no_hooks_is_refused() -> None:
    """A hook context that never ran produces no evidence, so no array."""
    adapter = StubMineWorldAdapter()
    decoder = _decoder(adapter, BANKED_UNIT, "e3_p90__L0")

    class _EmptyManager:
        def __init__(self, modules: Any) -> None:
            self.closed = False

        def __enter__(self) -> "_EmptyManager":
            return self

        def __exit__(self, *_exc: object) -> bool:
            self.closed = True
            return False

        @property
        def captures(self) -> dict[int, Any]:
            return {}

    decoder.hook_manager_factory = _EmptyManager
    with pytest.raises(ExperimentIIIError) as error:
        decoder.teacher_forced(trajectory_id="e3_p90__L0", model_frame_idx=39)
    assert error.value.blocker == "HOOK_LAYER_MISSING"


@requires_banked_captures
def test_a_decoder_bound_to_one_trajectory_refuses_another() -> None:
    adapter = StubMineWorldAdapter()
    decoder = _decoder(adapter, BANKED_UNIT, "e3_p90__L0")
    with pytest.raises(ExperimentIIIError) as error:
        decoder.teacher_forced(trajectory_id="e3_p91__L4", model_frame_idx=39)
    assert error.value.blocker == "TOKEN_FRAME_IDENTITY_MISMATCH"
    assert adapter.teacher_forced_calls == 0


# --------------------------------------------------------------------------
# Semantic frame identity and the persisted arrays
# --------------------------------------------------------------------------


@requires_banked_captures
def test_semantic_frame_identity_is_asserted_per_forward() -> None:
    """A correctly shaped residual from the wrong frame is not evidence."""
    from mineocclude.experiment_iii.extraction import extract_target_row

    class _WrongFrameAdapter(StubMineWorldAdapter):
        def tokenize_trajectory(self, request: Any) -> Any:
            tokenized = super().tokenize_trajectory(request)
            # Same shape, same pair indices, one frame identity off by one.
            spans = list(tokenized.frame_token_map.spans)
            last = spans[-1]
            spans[-1] = adapter_module.FrameTokenSpan(
                identity=adapter_module.FrameIdentity(
                    schema_version=SCHEMA_VERSION,
                    trajectory_id=last.identity.trajectory_id,
                    model_frame_idx=last.identity.model_frame_idx + 1,
                ),
                pair_index=last.pair_index,
                visual_positions=last.visual_positions,
                action_positions=last.action_positions,
            )
            import dataclasses

            token_map = dataclasses.replace(
                tokenized.frame_token_map, spans=tuple(spans)
            )
            return dataclasses.replace(tokenized, frame_token_map=token_map)

    adapter = _WrongFrameAdapter()
    decoder = _decoder(adapter, BANKED_UNIT, "e3_p90__L0")
    with pytest.raises(ExperimentIIIError) as error:
        extract_target_row(decoder, trajectory_id="e3_p90__L0", target_row=39)
    assert error.value.blocker == "TOKEN_FRAME_IDENTITY_MISMATCH"


@requires_banked_captures
def test_one_capture_persists_six_arrays_with_the_frozen_byte_contract(
    tmp_path: Path,
) -> None:
    adapter = StubMineWorldAdapter()
    decoder = _decoder(adapter, BANKED_UNIT, "e3_p90__L0")
    completion = json.loads(
        (BANKED_UNIT / "capture_completion.json").read_text(encoding="utf-8")
    )
    result = extract_pilot_capture(
        decoder,
        unit_dir=BANKED_UNIT,
        output_root=_activation_root(tmp_path),
        identity="e3_p90",
        condition_id="L0",
        capture_unit_id="e3_p90__L0",
        target_rows=completion["target_model_frame_indices"],
        checkpoint_identity=machine_authority()["extraction"]["main_checkpoint_sha256"],
        preprocessing_identity="person_a_legacy_preprocessing",
        source_capture_hash=completion["spec_sha256"],
        namespace_root=tmp_path,
    )
    assert result.forwards == TARGET_ROWS_PER_CAPTURE == 19
    assert adapter.teacher_forced_calls == 19
    assert len(result.arrays) == UNITS_PER_CAPTURE == 6

    root = _activation_root(tmp_path) / "e3_p90__L0"
    for layer in SELECTED_LAYERS:
        for name in TemporalSlice:
            path = root / f"activations/layer_{layer:02d}/{name.value}.npy"
            assert path.is_file()
            assert path.stat().st_size == EXPECTED_NPY_BYTES == 26_148_992
            array = np.load(path, allow_pickle=False)
            assert array.shape == EXPECTED_SHAPE == (19, 336, 2048)
            assert array.dtype.str == EXPECTED_DTYPE == "<f2"

    inventory = json.loads(
        (root / CANONICAL_INVENTORY_NAME).read_text(encoding="utf-8")
    )
    assert inventory["forwards"] == 19
    assert inventory["one_forward_per_target_row"] is True
    assert inventory["transient_hook_layer_count"] == TRANSIENT_HOOK_LAYER_COUNT
    assert len(inventory["forward_ledger"]) == 19
    assert inventory["artifacts"][0]["hook_site"] == HOOK_SITE
    assert inventory["artifacts"][0]["token_position_hash"] == token_position_hash()


@requires_banked_captures
def test_every_persisted_array_binds_its_semantic_frame_identity(
    tmp_path: Path,
) -> None:
    adapter = StubMineWorldAdapter()
    decoder = _decoder(adapter, BANKED_UNIT, "e3_p90__L0")
    completion = json.loads(
        (BANKED_UNIT / "capture_completion.json").read_text(encoding="utf-8")
    )
    rows = [int(value) for value in completion["target_model_frame_indices"]]
    result = extract_pilot_capture(
        decoder,
        unit_dir=BANKED_UNIT,
        output_root=_activation_root(tmp_path),
        identity="e3_p90",
        condition_id="L0",
        capture_unit_id="e3_p90__L0",
        target_rows=rows,
        checkpoint_identity=machine_authority()["extraction"]["main_checkpoint_sha256"],
        preprocessing_identity="person_a_legacy_preprocessing",
        source_capture_hash=completion["spec_sha256"],
        namespace_root=tmp_path,
    )
    for artifact in result.inventory["artifacts"]:
        assert artifact["identity"] == "e3_p90"
        assert artifact["condition_id"] == "L0"
        assert artifact["target_model_frame_indices"] == rows
        assert artifact["layer"] in SELECTED_LAYERS
        assert artifact["temporal_slice"] in {name.value for name in TemporalSlice}
        assert artifact["source_capture_hash"] == completion["spec_sha256"]
        assert artifact["checkpoint_identity"]
        assert artifact["preprocessing_identity"]
        assert artifact["token_position_hash"]
    ledger = {int(row["target_model_frame_idx"]) for row in result.forward_log}
    assert ledger == set(rows)
    for row in result.forward_log:
        assert row["serialized_layers"] == list(SELECTED_LAYERS)
        assert row["sequence_length"] == SEQUENCE_LENGTH


@requires_banked_captures
def test_a_wrong_target_row_count_is_refused(tmp_path: Path) -> None:
    adapter = StubMineWorldAdapter()
    decoder = _decoder(adapter, BANKED_UNIT, "e3_p90__L0")
    with pytest.raises(ExperimentIIIError) as error:
        extract_pilot_capture(
            decoder,
            unit_dir=BANKED_UNIT,
            output_root=_activation_root(tmp_path),
            identity="e3_p90",
            condition_id="L0",
            capture_unit_id="e3_p90__L0",
            target_rows=[39, 40],
            checkpoint_identity="0" * 64,
            preprocessing_identity="p",
            source_capture_hash="1" * 64,
            namespace_root=tmp_path,
        )
    assert error.value.blocker == "TARGET_ROW_MISMATCH"
    assert adapter.teacher_forced_calls == 0
