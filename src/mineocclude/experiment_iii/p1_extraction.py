"""A5 pilot activation extraction (authority 6A, 8.4, 8.5).

Frozen lifecycle A5 -- ``P1_ENGINEERING_PILOT`` -- has two halves. The capture
host runs ``CAPTURE_10_PILOT_UNITS``; the extraction host runs
``EXTRACT_190_FORWARDS``. This module owns the second half.

    2 pilot identities x 5 conditions =    10 captures
    10 captures x 19 target rows      =   190 target rows
                                      =   190 MineWorld forwards
    190 x 3 layers x 2 slices         = 1,140 logical row tensors
    10 x 3 layers x 2 slices          =    60 persisted .npy arrays

**A5 extraction is not A9.** A9 is production extraction -- 125 captures, 2,375
forwards, 750 arrays -- and its lifecycle entry additionally requires ``A8 ==
PASS``, the A6 freeze binding and ``MODEL_INFERENCE_AUTHORIZED == true``. A5's
entry requires ``A4 == P0_PASS``, ``A3 == PASS on capture and extraction hosts``
and ``P1_AUTHORIZED == true`` -- and *not* ``MODEL_INFERENCE_AUTHORIZED``, which
is precisely how the authority authorizes 190 pilot forwards before P2 while
still refusing 2,375 production ones. :func:`authorize_a5_extraction` and
:func:`refuse_production_extraction` are the two sides of that distinction, and
neither can be satisfied by the other's evidence.

**Nothing here is a second MineWorld implementation.** Model loading,
preprocessing, action conversion, tokenization and the teacher-forced forward
all go through the frozen :class:`~mineocclude.models.mineworld_adapter.
MineWorldAdapter` boundary; hooks go through
:class:`~mineocclude.activations.hooks.ScopedHookManager`; slicing, the semantic
assertions and the forward budget go through
:mod:`mineocclude.experiment_iii.extraction`. This module is the translation
layer between an Experiment III capture unit and those existing components, plus
the campaign that resumes across them.

**One forward per target row.** :class:`MineWorldPilotDecoder` issues exactly one
``adapter.teacher_forced`` call per target row and harvests all three layers and
both temporal slices from that single call's hooks. It counts its own calls, so
an accidental second forward is ``EXTRACTION_FORWARD_COUNT_EXCESS`` rather than a
silently doubled bill.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.contracts.trajectory import (
    EXPECTED_ARTIFACT_FORMATS,
    ROW_STREAMS,
    validate_trajectory_package,
)
from mineocclude.experiment_iii.activation_store import (
    EXPECTED_NPY_BYTES,
    EXPECTED_SHAPE,
    UNITS_PER_CAPTURE,
    build_extraction_inventory,
    validate_extraction_inventory,
    write_activation_array,
)
from mineocclude.experiment_iii.authority import (
    AUTHORITY_VERSION,
    CONTEXT_PAIRS,
    PILOT_IDENTITY_IDS,
    PRODUCTION_IDENTITY_IDS,
    TARGET_ROWS_PER_CAPTURE,
    canonical_sha256,
    machine_authority,
    sha256_file,
    verify_authority_binding,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.execution import (
    ExtractionUnit,
    HashChainLedger,
    plan_extraction_units,
    resume_decision,
)
from mineocclude.experiment_iii.extraction import (
    SELECTED_LAYERS,
    TRANSIENT_HOOK_LAYER_COUNT,
    ForwardResult,
    extract_capture,
)
from mineocclude.experiment_iii.host_preflight import A5_EXTRACTION_STAGE
from mineocclude.experiment_iii.schema import TemporalSlice, read_jsonl
from mineocclude.experiment_iii.slices import (
    SEQUENCE_LENGTH,
    action_positions,
    visual_positions,
)

__all__ = [
    "A5_EXTRACTION_STAGE",
    "CANONICAL_INVENTORY_NAME",
    "HOOK_SITE",
    "PERSON_A_RUNTIME_SCRIPTED_IMPULSE",
    "PILOT_ARRAYS",
    "PILOT_CAPTURES",
    "PILOT_FORWARDS",
    "PILOT_TARGET_ROWS",
    "PilotExtractionResult",
    "MineWorldPilotDecoder",
    "P1ExtractionCampaign",
    "assert_pilot_identity",
    "authorize_a5_extraction",
    "build_context_package",
    "capture_stream_rows",
    "context_window",
    "extract_pilot_capture",
    "refuse_production_extraction",
    "token_position_hash",
]

#: Authority 6A, restated here only as a derived assertion below.
PILOT_CAPTURES = 10
PILOT_TARGET_ROWS = PILOT_CAPTURES * TARGET_ROWS_PER_CAPTURE  # 190
PILOT_FORWARDS = PILOT_TARGET_ROWS  # one per target row, and no more
PILOT_ARRAYS = PILOT_CAPTURES * UNITS_PER_CAPTURE  # 60

#: Authority 8.5 names ``extraction_inventory.json`` -- both in the A9
#: ``expected_outputs`` and in ``EXPECTED_ARTIFACT_INVENTORY.json``. The
#: ``activation_inventory.json`` name that appeared in the non-frozen handoff
#: manifest and runbook is the *historical Regime-A* name (see
#: ``scripts/run_regime_a.py``) and is not the Experiment III artifact. One name,
#: taken from the authority.
CANONICAL_INVENTORY_NAME = "extraction_inventory.json"

#: The conceptual hook site the qualified hook machinery already names.
HOOK_SITE = "decoder_layer_output_residual_stream"

#: The frozen Person A runtime scripted-impulse fixture. The C-to-A trajectory
#: contract will not accept a package whose camera-axis impulse orientation is
#: unverified, and that evidence is a property of the **MineWorld runtime's**
#: action-conversion semantics, not of any one capture -- which is why it is a
#: pre-existing frozen fixture rather than something Experiment III measures.
#: Experiment III's camera is locked and every captured action carries
#: ``camera_dx == camera_dy == 0``, so no Experiment III frame exercises it; the
#: binding is recorded in the pilot receipt so a reader can see exactly which
#: fixture was named. Verbatim from ``run_person_a_phase6_single_pilot_sagemaker
#: .CANONICAL_IMPULSE_ORIENTATION``.
PERSON_A_RUNTIME_SCRIPTED_IMPULSE: Mapping[str, Any] = {
    "camera_component_0_observed_effect": "runtime_no_component_0_effect",
    "camera_component_1_observed_effect": (
        "runtime_positive_component_1_step_in_visual_i_to_i_plus_1"
    ),
    "evidence_hash": (
        "9b8d58c383cee1e37de0119acd23794719d1892d14e2186c3e0585e6769a3914"
    ),
    "evidence_scope": "frozen_person_a_runtime_scripted_impulse",
    "fixture_id": "runtime_scripted_impulse",
    "status": "verified",
}

_STREAM_FILES = {
    "frame_map": "raw/frame_map.jsonl",
    "actions": "raw/actions.jsonl",
    "server_state": "raw/server_state.jsonl",
    "client_tick": "raw/client_tick.jsonl",
    "visibility": "raw/visibility.jsonl",
    "coordinates": "coordinates.jsonl",
}


# --------------------------------------------------------------------------
# Stage authorization
# --------------------------------------------------------------------------


def assert_pilot_identity(identity: str) -> None:
    """Refuse anything but ``e3_p90`` / ``e3_p91``.

    Authority 2.1 forbids identity replacement, so a production identity spent
    on the engineering pilot permanently shrinks the 25-identity cohort. This is
    checked before any forward, not after.
    """
    name = str(identity)
    if name in set(PRODUCTION_IDENTITY_IDS):
        raise ExperimentIIIError(
            "P1_INCOMPLETE",
            f"{name} is a production identity; A5 spends only "
            f"{list(PILOT_IDENTITY_IDS)} and authority 2.1 forbids replacing a "
            "production identity consumed by a debug run",
        )
    if name not in set(PILOT_IDENTITY_IDS):
        raise ExperimentIIIError(
            "P1_INCOMPLETE", f"{name} is not one of the frozen pilot identities"
        )


def authorize_a5_extraction(a3_receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Whether this extraction host's A3 receipt authorizes the A5 pilot half.

    The lifecycle's A5 entry is ``A4 == P0_PASS``, ``A3 == PASS on capture and
    extraction hosts`` and ``P1_AUTHORIZED == true``. It does **not** name
    ``MODEL_INFERENCE_AUTHORIZED``, ``A6_FREEZE_BOUND`` or ``A8``; those belong to
    A9. So the only gate this function applies is the extraction host's own A3
    receipt, and the only thing it will accept as that receipt is one that
    actually verified the weights.
    """
    if not isinstance(a3_receipt, Mapping):
        raise ExperimentIIIError(
            "P2_PREREQUISITE_NOT_PASSED", "the A5 extraction gate needs an A3 receipt"
        )
    stages = list(a3_receipt.get("authorized_stages") or [])
    if A5_EXTRACTION_STAGE not in stages:
        raise ExperimentIIIError(
            "P2_PREREQUISITE_NOT_PASSED",
            f"this A3 receipt authorizes {stages}; A5 extraction requires "
            f"{A5_EXTRACTION_STAGE}. A capture-host receipt never authorizes it",
        )
    if not a3_receipt.get("passed"):
        raise ExperimentIIIError(
            "P2_PREREQUISITE_NOT_PASSED", "the extraction host A3 receipt is not PASS"
        )
    checks = a3_receipt.get("model_identity_checks") or {}
    if not checks.get("verified"):
        raise ExperimentIIIError(
            "ENV_CHECKPOINT_HASH_MISMATCH",
            "the A3 receipt does not record verified MineWorld checkpoint and VAE "
            "identities; A5 extraction will not load weights A3 never hashed",
        )
    expected = machine_authority()["extraction"]
    observed_model = (checks.get("main_checkpoint") or {}).get("observed_sha256")
    observed_vae = (checks.get("vae_checkpoint") or {}).get("observed_sha256")
    if observed_model != expected["main_checkpoint_sha256"]:
        raise ExperimentIIIError(
            "ENV_CHECKPOINT_HASH_MISMATCH",
            f"the A3 receipt records checkpoint {observed_model}, the authority "
            f"freezes {expected['main_checkpoint_sha256']}",
        )
    if observed_vae != expected["vae_sha256"]:
        raise ExperimentIIIError(
            "ENV_VAE_HASH_MISMATCH",
            f"the A3 receipt records VAE {observed_vae}, the authority freezes "
            f"{expected['vae_sha256']}",
        )
    return {
        "stage": A5_EXTRACTION_STAGE,
        "authorized": True,
        "authorized_stages": stages,
        "requires_model_inference_authorized": False,
        "requires_p2": False,
        "rationale": (
            "lifecycle A5 entry is A4 == P0_PASS, A3 == PASS on capture and "
            "extraction hosts, P1_AUTHORIZED == true; MODEL_INFERENCE_AUTHORIZED "
            "and the A6 freeze binding are A9 entry conditions, not A5's"
        ),
        "checkpoint_sha256": observed_model,
        "vae_sha256": observed_vae,
    }


def refuse_production_extraction(
    a3_receipt: Mapping[str, Any] | None = None,
    *,
    model_inference_authorized: bool = False,
    a6_freeze_bound: bool = False,
    a8_passed: bool = False,
) -> None:
    """A9 remains production-only and gated behind P2. Always, from here.

    An A3 receipt authorizing ``A9`` proves only that the *host* could run it.
    A9's remaining entry conditions -- A8 PASS, the A6 freeze binding, and
    ``MODEL_INFERENCE_AUTHORIZED`` -- are program state, and A6 has not run. No
    banked field, ``P0_LADDER_ACCEPTED`` included, can substitute for them: the
    caller must pass them explicitly, and this function refuses whenever any is
    absent rather than reading a stale document that might claim otherwise.
    """
    missing = [
        name
        for name, value in (
            ("A8", a8_passed),
            ("A6_FREEZE_BOUND", a6_freeze_bound),
            ("MODEL_INFERENCE_AUTHORIZED", model_inference_authorized),
        )
        if not value
    ]
    if missing:
        raise ExperimentIIIError(
            "P2_PREREQUISITE_NOT_PASSED",
            "A9 production extraction requires " + ", ".join(missing) + "; the P2 "
            "freeze (A6) is the only place MODEL_INFERENCE_AUTHORIZED may be "
            "emitted and it has not run. The A5 pilot's 190 forwards are a "
            "different stage and are not a route into this one",
        )


# --------------------------------------------------------------------------
# Capture unit -> adapter package
# --------------------------------------------------------------------------


def capture_stream_rows(unit_dir: Path) -> list[dict[str, Any]]:
    """One flat row per model frame, joined from the banked capture streams.

    The mod writes five JSONL streams plus ``coordinates.jsonl``, each 180 rows
    long and keyed differently: ``frame_map`` and ``actions`` by
    ``render_frame_idx``, ``server_state`` and ``coordinates`` by ``server_tick``,
    ``visibility`` by ``model_frame_idx``. This join is by those keys, and a row
    that cannot be joined on every stream is a refusal, not a gap to fill in.
    """
    unit_dir = Path(unit_dir)
    tables: dict[str, list[Mapping[str, Any]]] = {}
    for name, relative in _STREAM_FILES.items():
        path = unit_dir / relative
        if not path.is_file():
            raise ExperimentIIIError(
                "CAPTURE_MISSING_FRAME", f"{unit_dir.name} has no {relative}"
            )
        tables[name] = read_jsonl(path)

    frame_map = tables["frame_map"]
    counts = {name: len(rows) for name, rows in tables.items()}
    if len(set(counts.values())) != 1:
        raise ExperimentIIIError(
            "TIMING_CARDINALITY_MISMATCH",
            f"{unit_dir.name} streams disagree on length: {counts}",
        )

    actions = {int(row["render_frame_idx"]): row for row in tables["actions"]}
    server = {int(row["server_tick"]): row for row in tables["server_state"]}
    ticks = {int(row["render_frame_idx"]): row for row in tables["client_tick"]}
    coordinates = {int(row["server_tick"]): row for row in tables["coordinates"]}
    visibility = {int(row["model_frame_idx"]): row for row in tables["visibility"]}

    rows: list[dict[str, Any]] = []
    for entry in frame_map:
        render_idx = int(entry["render_frame_idx"])
        tick = int(entry["server_tick"])
        for name, table, key in (
            ("actions", actions, render_idx),
            ("server_state", server, tick),
            ("client_tick", ticks, render_idx),
            ("coordinates", coordinates, tick),
            ("visibility", visibility, render_idx),
        ):
            if key not in table:
                raise ExperimentIIIError(
                    "CAPTURE_MISSING_ACTION",
                    f"{unit_dir.name} frame {render_idx} has no {name} row",
                )
        action = actions[render_idx]
        state = server[tick]
        coordinate = coordinates[tick]
        seen = visibility[render_idx]
        rows.append(
            {
                "episode_id": int(entry["episode_id"]),
                # The mod indexes render frames and model frames identically:
                # one captured frame per server tick, 180 of each, in lockstep.
                "model_frame_idx": render_idx,
                "render_frame_idx": render_idx,
                "server_tick": tick,
                "action_idx": int(action["action_idx"]),
                "frame_path": str(entry["frame_path"]),
                "frame_sha256": str(entry["frame_sha256"]),
                "action": dict(action),
                "axis_pos": float(coordinate["axis_pos"]),
                "axis_velocity": float(coordinate["axis_velocity"]),
                "noise_draw": float(coordinate["noise_draw"]),
                "seed": int(state["seed"]),
                "geometric_visible": bool(state["geometric_visible"]),
                "counterfactual_extent_class": str(
                    seen["counterfactual_extent_class"]
                ),
            }
        )
    return rows


def context_window(
    rows: Sequence[Mapping[str, Any]], target_row: int
) -> list[Mapping[str, Any]]:
    """The 16 complete pairs for model frames ``[t-15, ..., t]`` (authority 8.4).

    A target row whose context would run off the start of the capture is a
    refusal: a short window would tokenize to fewer than 5,552 positions and the
    slice arithmetic would address the wrong pairs.
    """
    index = {int(row["model_frame_idx"]): row for row in rows}
    start = int(target_row) - (CONTEXT_PAIRS - 1)
    if start < 0:
        raise ExperimentIIIError(
            "EXTRACTION_TEMPORAL_INDEX_MISMATCH",
            f"target row {target_row} has no {CONTEXT_PAIRS}-pair context",
        )
    window = []
    for frame in range(start, int(target_row) + 1):
        if frame not in index:
            raise ExperimentIIIError(
                "EXTRACTION_TEMPORAL_INDEX_MISMATCH",
                f"model frame {frame} is missing from the capture streams",
            )
        window.append(index[frame])
    if len(window) != CONTEXT_PAIRS:
        raise ExperimentIIIError(
            "TOKEN_SEQUENCE_LENGTH_MISMATCH",
            f"context window is {len(window)} pairs, expected {CONTEXT_PAIRS}",
        )
    return window


def token_position_hash() -> str:
    """A digest over the exact positions every persisted array was cut from.

    Bound into each artifact so a later reader can tell whether the arrays it is
    holding came from this token layout or some other one.
    """
    return canonical_sha256(
        {
            "sequence_length": SEQUENCE_LENGTH,
            "context_pairs": CONTEXT_PAIRS,
            "slices": {
                name.value: {
                    "visual_positions": list(
                        visual_positions(
                            CONTEXT_PAIRS - (1 if name is TemporalSlice.CURRENT else 2)
                        )
                    ),
                    "excluded_action_positions": list(
                        action_positions(
                            CONTEXT_PAIRS - (1 if name is TemporalSlice.CURRENT else 2)
                        )
                    ),
                }
                for name in TemporalSlice
            },
        }
    )


def build_context_package(
    unit_dir: Path,
    rows: Sequence[Mapping[str, Any]],
    target_row: int,
    *,
    trajectory_id: str,
    seed: int,
    impulse_orientation: Mapping[str, Any],
) -> dict[str, Any]:
    """The C-to-A trajectory package for one target row's 16-pair context.

    The adapter's ``validate_trajectory`` accepts only a package that passes
    :func:`~mineocclude.contracts.trajectory.validate_trajectory_package`, so the
    package is built to that contract and then submitted to it here -- a
    rejection stops the row rather than reaching the model. The stream
    construction (official raw action, camera binning, tri-state normalization)
    reuses the qualified converters in
    :mod:`mineocclude.data.convert_mineworld` rather than restating them.
    """
    from mineocclude.data.convert_mineworld import (
        bin_camera,
        flat_to_official_raw_action,
    )

    window = context_window(rows, target_row)
    episode_id = str(window[0]["episode_id"])

    def _tri(positive: Any, negative: Any) -> int:
        if bool(positive):
            return 1
        if bool(negative):
            return 2
        return 0

    streams: dict[str, list[dict[str, Any]]] = {name: [] for name in ROW_STREAMS}
    previous_hotbar: int | None = None
    for row in window:
        action = row["action"]
        key = {
            "episode_id": episode_id,
            "trajectory_id": trajectory_id,
            "server_tick": int(row["server_tick"]),
            "render_frame_idx": int(row["render_frame_idx"]),
            "action_idx": int(row["action_idx"]),
            "model_frame_idx": int(row["model_frame_idx"]),
        }
        official = flat_to_official_raw_action(action, prev_hotbar=previous_hotbar)
        previous_hotbar = int(action["hotbar"])
        streams["frame_map"].append(dict(key))
        streams["raw_actions"].append({**key, "raw_action": official})
        streams["normalized_actions"].append(
            {
                **key,
                "normalized_action": {
                    "camera_component_0": bin_camera(float(action["camera_dy"])),
                    "camera_component_1": bin_camera(float(action["camera_dx"])),
                    "hotbar": int(action["hotbar"]),
                    "forward_back": _tri(action["forward"], action["back"]),
                    "left_right": _tri(action["left"], action["right"]),
                    "sprint_sneak": _tri(action["sprint"], action["sneak"]),
                    "use_attack": _tri(action["use"], action["attack"]),
                    "jump": 1 if bool(action["jump"]) else 0,
                    "drop_pick_item": _tri(action["drop"], action["pick_item"]),
                },
            }
        )
        streams["server_state"].append(
            {
                **key,
                "state": {
                    "axis_pos": float(row["axis_pos"]),
                    "axis_velocity": float(row["axis_velocity"]),
                },
            }
        )
        streams["client_tick_log"].append(
            {**key, "client_tick": int(row["render_frame_idx"])}
        )
        streams["visibility"].append(
            {
                **key,
                "visibility": (
                    "visible" if row["geometric_visible"] else "occluded"
                ),
            }
        )
        streams["seed_noise"].append(
            {**key, "seed": int(seed), "noise_draw": float(row["noise_draw"])}
        )

    unit_dir = Path(unit_dir)
    artifacts: dict[str, dict[str, str]] = {}
    artifact_sources = {
        "frame_map": "raw/frame_map.jsonl",
        "raw_actions": "raw/actions.jsonl",
        "normalized_actions": "raw/actions.jsonl",
        "server_state": "raw/server_state.jsonl",
        "client_tick_log": "raw/client_tick.jsonl",
        "visibility": "raw/visibility.jsonl",
        "seed_noise": "coordinates.jsonl",
        "config": "capture_completion.json",
        "diagnostics": "timing_receipt.json",
    }
    for name, relative in artifact_sources.items():
        path = unit_dir / relative
        if not path.is_file():
            raise ExperimentIIIError(
                "PROVENANCE_BINDING_MISSING",
                f"{unit_dir.name} has no {relative} to bind as artifact {name}",
            )
        artifacts[name] = {
            "path": relative,
            "format": EXPECTED_ARTIFACT_FORMATS[name],
            "sha256": sha256_file(path),
        }

    frames_digest = hashlib.sha256()
    for row in window:
        frames_digest.update(bytes.fromhex(str(row["frame_sha256"])))

    package = {
        "schema_version": SCHEMA_VERSION,
        "episode_id": episode_id,
        "trajectory_id": trajectory_id,
        "seed": int(seed),
        "media": {
            "mode": "numbered_frames",
            "path": (unit_dir / "raw" / "frames").as_posix(),
            "width": 640,
            "height": 360,
            "fps": 20.0,
            "frame_count": len(window),
            "sha256": frames_digest.hexdigest(),
        },
        "artifacts": artifacts,
        "streams": streams,
        "impulse_orientation": dict(impulse_orientation),
    }
    validation = validate_trajectory_package(package)
    if not validation.accepted:
        detail = "; ".join(
            f"{item.code.value}:{item.message}" for item in validation.rejections[:3]
        )
        raise ExperimentIIIError(
            "EXTRACTION_SPEC_DRIFT",
            f"{trajectory_id} target row {target_row}: the adapter package was "
            f"rejected by the frozen trajectory contract: {detail}",
        )
    return package


# --------------------------------------------------------------------------
# The adapter-backed decoder
# --------------------------------------------------------------------------


class MineWorldPilotDecoder:
    """A :class:`~mineocclude.experiment_iii.extraction.TeacherForcedDecoder`
    backed by the real MineWorld adapter.

    ``extract_target_row`` calls :meth:`teacher_forced` once per target row and
    takes every layer and both slices out of what comes back, so the one-forward
    contract is a property of this seam rather than a convention callers must
    remember. The hook manager registers all 20 decoder layers transiently
    (authority 8.4) and is discarded when the call returns; only layers
    ``{4, 10, 19}`` are ever serialized.
    """

    def __init__(
        self,
        adapter: Any,
        runtime_identity: Any,
        *,
        unit_dir: Path,
        trajectory_id: str,
        seed: int,
        rows: Sequence[Mapping[str, Any]],
        impulse_orientation: Mapping[str, Any],
        hook_manager_factory: Callable[[tuple[tuple[str, object], ...]], Any],
        frame_loader: Callable[[Path], Any],
        expected_adapter_code_sha256: str | None = None,
        precision: str = "float16",
        forward_seed: int = 0,
    ) -> None:
        self.adapter = adapter
        self.runtime_identity = runtime_identity
        self.unit_dir = Path(unit_dir)
        self.trajectory_id = str(trajectory_id)
        self.seed = int(seed)
        self.rows = list(rows)
        self.impulse_orientation = dict(impulse_orientation)
        self.hook_manager_factory = hook_manager_factory
        self.frame_loader = frame_loader
        self.expected_adapter_code_sha256 = expected_adapter_code_sha256
        self.precision = precision
        self.forward_seed = int(forward_seed)
        #: Every ``adapter.teacher_forced`` call this decoder has made. The
        #: campaign asserts this against the authority's 190, so an extra
        #: forward is visible rather than merely expensive.
        self.adapter_forward_calls = 0
        self.forward_log: list[dict[str, Any]] = []

    def teacher_forced(
        self, *, trajectory_id: str, model_frame_idx: int
    ) -> ForwardResult:
        """ONE adapter forward for one target row; all layers, both slices."""
        from mineocclude.models import mineworld_adapter as adapter_module

        if trajectory_id != self.trajectory_id:
            raise ExperimentIIIError(
                "TOKEN_FRAME_IDENTITY_MISMATCH",
                f"this decoder is bound to {self.trajectory_id}, not {trajectory_id}",
            )
        package = build_context_package(
            self.unit_dir,
            self.rows,
            model_frame_idx,
            trajectory_id=self.trajectory_id,
            seed=self.seed,
            impulse_orientation=self.impulse_orientation,
        )
        package_sha256 = canonical_sha256(package)

        validated = self.adapter.validate_trajectory(
            adapter_module.AcceptedTrajectoryInput(
                schema_version=SCHEMA_VERSION,
                trajectory_id=self.trajectory_id,
                accepted_manifest_sha256=package_sha256,
                document=package,
            )
        )
        window = context_window(self.rows, model_frame_idx)
        frames = tuple(
            self.adapter.preprocess_frame(
                adapter_module.FramePreprocessRequest(
                    identity=identity,
                    source_frame_idx=int(row["render_frame_idx"]),
                    frame=self.frame_loader(self.unit_dir / row["frame_path"]),
                )
            )
            for identity, row in zip(validated.frame_identities, window)
        )
        actions = tuple(
            self.adapter.convert_action(
                adapter_module.ActionConversionRequest(
                    identity=identity,
                    action_idx=int(row["action_idx"]),
                    raw_action=raw["raw_action"],
                )
            )
            for identity, row, raw in zip(
                validated.frame_identities, window, package["streams"]["raw_actions"]
            )
        )
        tokenized = self.adapter.tokenize_trajectory(
            adapter_module.TrajectoryTokenizationRequest(
                runtime_identity=self.runtime_identity,
                trajectory=validated,
                frames=frames,
                actions=actions,
            )
        )
        if len(tokenized.token_ids) != SEQUENCE_LENGTH:
            raise ExperimentIIIError(
                "TOKEN_SEQUENCE_LENGTH_MISMATCH",
                f"the 16-pair context tokenized to {len(tokenized.token_ids)} "
                f"positions, expected {SEQUENCE_LENGTH}",
            )

        holder: dict[str, Any] = {}

        def factory(modules: tuple[tuple[str, object], ...]) -> Any:
            if len(modules) != TRANSIENT_HOOK_LAYER_COUNT:
                raise ExperimentIIIError(
                    "HOOK_REGISTRATION_INCOMPLETE",
                    f"the teacher boundary exposed {len(modules)} decoder modules, "
                    f"expected {TRANSIENT_HOOK_LAYER_COUNT}",
                )
            manager = self.hook_manager_factory(modules)
            holder["manager"] = manager
            return manager

        result = self.adapter.teacher_forced(
            adapter_module.TeacherForcedRequest(
                runtime_identity=self.runtime_identity,
                trajectory=tokenized,
                seed=self.forward_seed,
                precision=self.precision,
                batch_size=1,
                hook_context_factory=factory,
                expected_adapter_code_sha256=self.expected_adapter_code_sha256,
                accepted_manifest_sha256=package_sha256,
            )
        )
        self.adapter_forward_calls += 1

        manager = holder.get("manager")
        if manager is None:
            raise ExperimentIIIError(
                "HOOK_REGISTRATION_INCOMPLETE",
                "the adapter did not enter the hook context; no residuals were "
                "captured and no array may be written from this forward",
            )
        if not getattr(manager, "closed", False):
            raise ExperimentIIIError(
                "HOOK_REGISTRATION_INCOMPLETE",
                "the hook context did not close; a leaked hook would contaminate "
                "the next forward",
            )
        captures = dict(manager.captures)
        missing = [layer for layer in SELECTED_LAYERS if layer not in captures]
        if missing:
            raise ExperimentIIIError(
                "HOOK_LAYER_MISSING",
                f"this forward captured no residual for layers {missing}",
            )
        if len(captures) != TRANSIENT_HOOK_LAYER_COUNT:
            raise ExperimentIIIError(
                "HOOK_REGISTRATION_INCOMPLETE",
                f"{len(captures)} of {TRANSIENT_HOOK_LAYER_COUNT} decoder layers "
                "reported a capture in this forward",
            )
        activations = {
            layer: _as_numpy(captures[layer]) for layer in SELECTED_LAYERS
        }
        self.forward_log.append(
            {
                "trajectory_id": self.trajectory_id,
                "target_model_frame_idx": int(model_frame_idx),
                "accepted_manifest_sha256": package_sha256,
                "token_sha256": tokenized.token_sha256,
                "frame_token_map_sha256": tokenized.frame_token_map_sha256,
                "result_sha256": getattr(result, "result_sha256", None),
                "sequence_length": len(tokenized.token_ids),
                "hooked_layers": sorted(captures),
                "serialized_layers": list(SELECTED_LAYERS),
                "forward_index": self.adapter_forward_calls,
            }
        )
        return ForwardResult(
            layer_activations=activations,
            frame_token_map=result.frame_token_map,
            trajectory_id=self.trajectory_id,
            model_frame_idx=int(model_frame_idx),
        )


def _as_numpy(capture: Any) -> np.ndarray:
    """The ``[1, 5552, 2048]`` residual of one hooked layer, as float32 NumPy.

    The hook machinery hands back its own capture object wrapping a torch
    tensor; converting here keeps every downstream module -- slicing, stacking,
    serialization -- torch-free and CPU-testable, exactly as
    :mod:`~mineocclude.experiment_iii.extraction` already assumes.
    """
    tensor = getattr(getattr(capture, "output", None), "tensor", None)
    if tensor is None:
        tensor = getattr(capture, "tensor", capture)
    if isinstance(tensor, np.ndarray):
        return tensor
    detached = getattr(tensor, "detach", None)
    if callable(detached):
        tensor = detached()
    for method in ("float", "cpu"):
        converter = getattr(tensor, method, None)
        if callable(converter):
            tensor = converter()
    to_numpy = getattr(tensor, "numpy", None)
    if callable(to_numpy):
        return np.asarray(to_numpy())
    return np.asarray(tensor)


# --------------------------------------------------------------------------
# One capture: six arrays and an inventory
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PilotExtractionResult:
    """What one extracted capture unit produced."""

    capture_unit_id: str
    identity: str
    condition_id: str
    forwards: int
    arrays: list[dict[str, Any]]
    inventory: dict[str, Any]
    inventory_sha256: str
    forward_log: list[dict[str, Any]]


def extract_pilot_capture(
    decoder: MineWorldPilotDecoder,
    *,
    unit_dir: Path,
    output_root: Path,
    identity: str,
    condition_id: str,
    capture_unit_id: str,
    target_rows: Sequence[int],
    checkpoint_identity: str,
    preprocessing_identity: str,
    source_capture_hash: str,
    namespace_root: Path | None = None,
    roster_check: Callable[[str], None] = assert_pilot_identity,
    stage: str = A5_EXTRACTION_STAGE,
) -> PilotExtractionResult:
    """19 forwards, six ``[19,336,2048]`` arrays, one inventory, all bound.

    The forward budget, the semantic assertions and the slicing all come from
    :func:`~mineocclude.experiment_iii.extraction.extract_capture`; the byte
    contract and the independent revalidation come from
    :mod:`~mineocclude.experiment_iii.activation_store`. What is added here is
    the binding: which identity, which condition, which capture, which source
    frames, and which forward each array came out of.

    ``roster_check`` and ``stage`` are the *caller's* authority-bound semantics.
    A5 passes :func:`assert_pilot_identity` / ``A5_EXTRACTION``; A9 passes
    ``assert_production_identity`` / ``A9``. They are parameters rather than
    literals because this engine is shared: a hardcoded pilot roster refuses
    every production identity, and a hardcoded pilot stage seals production
    evidence under the pilot's stage identity. The defaults keep A5 behaviour
    for every existing caller.
    """
    roster_check(identity)
    rows = [int(value) for value in target_rows]
    if len(rows) != TARGET_ROWS_PER_CAPTURE:
        raise ExperimentIIIError(
            "TARGET_ROW_MISMATCH",
            f"{capture_unit_id} names {len(rows)} target rows, the authority "
            f"freezes {TARGET_ROWS_PER_CAPTURE}",
        )
    before = decoder.adapter_forward_calls
    stacked, counter = extract_capture(
        decoder, trajectory_id=capture_unit_id, target_rows=rows
    )
    forwards = decoder.adapter_forward_calls - before
    if forwards != len(rows) or counter.forwards != len(rows):
        raise ExperimentIIIError(
            "EXTRACTION_FORWARD_COUNT_EXCESS",
            f"{capture_unit_id} issued {forwards} adapter forwards for {len(rows)} "
            "target rows; authority 8.4 authorizes exactly one per row",
        )

    capture_root = Path(output_root) / capture_unit_id
    written: dict[tuple[int, str], Mapping[str, Any]] = {}
    arrays: list[dict[str, Any]] = []
    for layer in SELECTED_LAYERS:
        for name in TemporalSlice:
            array = stacked[(layer, name)]
            if array.shape != EXPECTED_SHAPE:
                raise ExperimentIIIError(
                    "TENSOR_SHAPE_MISMATCH",
                    f"{capture_unit_id} layer {layer} {name.value} stacked to "
                    f"{array.shape}, expected {EXPECTED_SHAPE}",
                )
            record = write_activation_array(
                capture_root,
                layer,
                name,
                array,
                namespace_root=namespace_root,
            )
            written[(layer, name.value)] = record
            arrays.append({**record, "layer": layer, "temporal_slice": name.value})

    inventory = build_extraction_inventory(
        identity=identity,
        condition_id=condition_id,
        target_model_frame_indices=rows,
        written=written,
        hook_site=HOOK_SITE,
        preprocessing_identity=preprocessing_identity,
        checkpoint_identity=checkpoint_identity,
        source_capture_hash=source_capture_hash,
        token_position_hash=token_position_hash(),
    )
    # Bind the provenance authority 8.5 asks for beyond the per-artifact fields:
    # which capture, which forwards, and that all six arrays share them.
    inventory["capture_unit_id"] = capture_unit_id
    inventory["source_capture_hash"] = source_capture_hash
    inventory["stage"] = str(stage)
    inventory["forwards"] = forwards
    inventory["one_forward_per_target_row"] = True
    inventory["shared_forward_set_per_capture"] = forwards
    inventory["transient_hook_layer_count"] = TRANSIENT_HOOK_LAYER_COUNT
    inventory["forward_ledger"] = list(decoder.forward_log[-forwards:])
    inventory["inventory_sha256"] = canonical_sha256(
        {key: value for key, value in inventory.items() if key != "inventory_sha256"}
    )

    digest = _write_json(capture_root / CANONICAL_INVENTORY_NAME, inventory)
    validate_extraction_inventory(
        capture_root,
        inventory,
        expected_target_rows=rows,
        source_capture_hash=source_capture_hash,
        checkpoint_identity=checkpoint_identity,
        preprocessing_identity=preprocessing_identity,
    )
    return PilotExtractionResult(
        capture_unit_id=capture_unit_id,
        identity=identity,
        condition_id=condition_id,
        forwards=forwards,
        arrays=arrays,
        inventory=inventory,
        inventory_sha256=digest,
        forward_log=list(decoder.forward_log[-forwards:]),
    )


def _write_json(target: Path, body: Mapping[str, Any]) -> str:
    payload = json.dumps(body, indent=2, sort_keys=True, allow_nan=False) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# The campaign
# --------------------------------------------------------------------------


class P1ExtractionCampaign:
    """Ten capture units, one ledger, 190 forwards, 60 arrays, resumable.

    The unit of work is one ``(capture unit x layer x temporal slice)`` array,
    per authority 8.6, but the *forwards* are shared by a capture's six arrays --
    so the ledger records the shared forward set and a restart never re-runs a
    completed capture's 19 forwards. A capture whose six units are all COMPLETE
    is skipped without loading a frame.
    """

    def __init__(
        self,
        units: Sequence[Mapping[str, Any]],
        *,
        output_root: Path,
        ledger_path: Path,
        extraction_spec_hash: str,
        namespace_root: Path | None = None,
        roster_check: Callable[[str], None] = assert_pilot_identity,
        stage: str = A5_EXTRACTION_STAGE,
    ) -> None:
        # A9 runs this same loop over 125 production captures. The engine --
        # shared-forward accounting, per-array ledger states, skip-a-complete-
        # capture-without-reading-a-frame resume -- is what P1 qualified against
        # a real MineWorld adapter, and authority 8.6 gives A5 extraction and A9
        # the same unit of work. A9 therefore swaps the roster gate and the
        # stage label rather than growing a second extraction engine.
        self.stage = stage
        #: Retained, not just applied once at construction: the extraction loop
        #: itself must apply the caller's roster gate, or the outer gate accepts
        #: an identity the inner engine then refuses.
        self.roster_check = roster_check
        self.units = [dict(unit) for unit in units]
        for unit in self.units:
            roster_check(unit["identity"])
        self.output_root = Path(output_root)
        self.namespace_root = Path(namespace_root) if namespace_root else None
        self.ledger = HashChainLedger(Path(ledger_path), root=self.namespace_root)
        self.extraction_spec_hash = str(extraction_spec_hash)
        self.binding = verify_authority_binding()
        self.forwards = 0
        self.results: list[PilotExtractionResult] = []

    def planned_units(self, unit: Mapping[str, Any]) -> list[ExtractionUnit]:
        return plan_extraction_units(
            str(unit["capture_unit_id"]),
            source_capture_hash=str(unit["source_capture_hash"]),
            extraction_spec_hash=self.extraction_spec_hash,
        )

    def capture_is_complete(self, unit: Mapping[str, Any]) -> bool:
        """Whether every one of a capture's six arrays is already COMPLETE."""
        return all(
            resume_decision(planned, self.ledger)["action"] == "SKIP"
            for planned in self.planned_units(unit)
        )

    def run(
        self,
        decoder_factory: Callable[[Mapping[str, Any]], MineWorldPilotDecoder],
        *,
        checkpoint_identity: str,
        preprocessing_identity: str,
        on_unit: Callable[[str, str], None] | None = None,
    ) -> dict[str, Any]:
        skipped: list[str] = []
        extracted: list[str] = []
        for unit in self.units:
            unit_id = str(unit["capture_unit_id"])
            if self.capture_is_complete(unit):
                skipped.append(unit_id)
                if on_unit:
                    on_unit(unit_id, "SKIPPED_COMPLETE")
                continue
            planned = self.planned_units(unit)
            for entry in planned:
                self.ledger.append(
                    entry.unit_id,
                    "PLANNED",
                    source_capture_hash=entry.source_capture_hash,
                    extraction_spec_hash=entry.extraction_spec_hash,
                    authority_sha256=self.binding["AUTHORITY_SHA256"],
                )
                self.ledger.append(
                    entry.unit_id,
                    "RUNNING",
                    source_capture_hash=entry.source_capture_hash,
                    extraction_spec_hash=entry.extraction_spec_hash,
                )
            decoder = decoder_factory(unit)
            result = extract_pilot_capture(
                decoder,
                unit_dir=Path(unit["unit_dir"]),
                output_root=self.output_root,
                identity=str(unit["identity"]),
                condition_id=str(unit["condition_id"]),
                capture_unit_id=unit_id,
                target_rows=unit["target_model_frame_indices"],
                checkpoint_identity=checkpoint_identity,
                preprocessing_identity=preprocessing_identity,
                source_capture_hash=str(unit["source_capture_hash"]),
                namespace_root=self.namespace_root,
                roster_check=self.roster_check,
                stage=self.stage,
            )
            self.forwards += result.forwards
            self.results.append(result)
            by_key = {
                (int(row["layer"]), str(row["temporal_slice"])): row
                for row in result.arrays
            }
            for entry in planned:
                record = by_key[(entry.layer, entry.temporal_slice)]
                for state in ("EXTRACTED", "VALIDATED", "DURABLE", "COMPLETE"):
                    self.ledger.append(
                        entry.unit_id,
                        state,
                        source_capture_hash=entry.source_capture_hash,
                        extraction_spec_hash=entry.extraction_spec_hash,
                        array_sha256=record["sha256"],
                        byte_size=record["byte_size"],
                        shared_forward_set=result.forwards,
                    )
            extracted.append(unit_id)
            if on_unit:
                on_unit(unit_id, "COMPLETE")
        return {"skipped": skipped, "extracted": extracted, "inventory": self.inventory()}

    def inventory(self) -> dict[str, Any]:
        """What is actually banked, reconstructed from disk and the ledger."""
        complete = self.ledger.complete_units()
        units = []
        arrays = 0
        for unit in self.units:
            unit_id = str(unit["capture_unit_id"])
            planned = self.planned_units(unit)
            done = [entry for entry in planned if entry.unit_id in complete]
            present = [
                entry
                for entry in done
                if (
                    self.output_root
                    / unit_id
                    / f"activations/layer_{entry.layer:02d}/{entry.temporal_slice}.npy"
                ).is_file()
            ]
            arrays += len(present)
            units.append(
                {
                    "capture_unit_id": unit_id,
                    "identity": unit["identity"],
                    "condition_id": unit["condition_id"],
                    "target_rows": len(unit["target_model_frame_indices"]),
                    "arrays_complete": len(present),
                    "complete": len(present) == UNITS_PER_CAPTURE,
                }
            )
        completed = [entry for entry in units if entry["complete"]]
        return {
            "stage": self.stage,
            "authority_version": AUTHORITY_VERSION,
            "total_captures": len(self.units),
            "captures_complete": len(completed),
            "arrays_expected": len(self.units) * UNITS_PER_CAPTURE,
            "arrays_complete": arrays,
            "forwards_this_run": self.forwards,
            "expected_bytes_per_array": EXPECTED_NPY_BYTES,
            "identities": sorted({str(unit["identity"]) for unit in self.units}),
            "production_identities_used": bool(
                {str(unit["identity"]) for unit in self.units}
                & set(PRODUCTION_IDENTITY_IDS)
            ),
            "units": units,
            "complete": len(completed) == len(self.units)
            and arrays == len(self.units) * UNITS_PER_CAPTURE,
        }
