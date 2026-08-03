from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from mineocclude.activations import store as store_v1
from mineocclude.activations.store_v2 import (
    ACTIVATION_INDEX_V1_FORMAT_VERSION,
    ACTIVATION_INDEX_V2_FORMAT_VERSION,
    ACTIVATION_STORE_V2_FORMAT_VERSION,
    FROZEN_PHASE6_LAYERS,
    ActivationIndexSnapshotV2,
    ActivationSourceFrameIdentityV2,
    ActivationStoreIdentityV2,
    ActivationStoreV2Error,
    build_source_frame_bindings_v2,
    candidate_row_from_frame_token_span_v2,
    derive_visual_token_positions,
    expected_activation_row_count,
    load_activation_index_dispatched,
    load_activation_index_snapshot_v2,
    publish_activation_chunk_v2,
    validate_activation_rows_v2,
)
from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.models.mineworld_adapter import (
    FrameIdentity,
    FrameTokenMap,
    FrameTokenSpan,
)

ROOT = Path(__file__).resolve().parents[2]
V1_FIXTURE_ROOT = (
    ROOT / "docs" / "status" / "fixtures" / "phase5_activation_store_example"
)
V1_INDEX = (
    V1_FIXTURE_ROOT
    / "indexes"
    / "index-834f1070e8d77680e06d7713caf618624211c0bcf5ce4cfef8b692011ebd67e4.json"
)
HASHES = {
    "accepted": "1" * 64,
    "checkpoint": "2" * 64,
    "config": "3" * 64,
    "preprocess": "4" * 64,
    "frame_map": "5" * 64,
    "state": "6" * 64,
}


def _store_identity(
    *,
    layers: tuple[int, ...] = FROZEN_PHASE6_LAYERS,
    width: int = 4,
) -> ActivationStoreIdentityV2:
    return ActivationStoreIdentityV2(
        schema_version=SCHEMA_VERSION,
        format_version=ACTIVATION_STORE_V2_FORMAT_VERSION,
        run_id="person-a-phase6-layout-00-ep9403",
        checkpoint_hash=HASHES["checkpoint"],
        model_hash=HASHES["checkpoint"],
        config_hash=HASHES["config"],
        preprocess_hash=HASHES["preprocess"],
        accepted_manifest_hash=HASHES["accepted"],
        code_sha="7" * 40,
        hook_site="decoder_layer_output_residual_stream",
        requested_layers=layers,
        dtype="float32",
        hidden_width=width,
    )


def _source_rows(count: int) -> tuple[list[dict[str, object]], ...]:
    frame_map: list[dict[str, object]] = []
    state: list[dict[str, object]] = []
    for index in range(count):
        common = {
            "trajectory_id": "layout_00_ep9403",
            "model_frame_idx": index,
            "render_frame_idx": index,
            "server_tick": index,
        }
        frame_map.append({**common, "action_idx": index})
        state.append({**common, "state": {"target_present": True}})
    return frame_map, state


def _bindings(count: int) -> tuple[ActivationSourceFrameIdentityV2, ...]:
    frame_map, state = _source_rows(count)
    return build_source_frame_bindings_v2(
        trajectory_id="layout_00_ep9403",
        frame_map_rows=frame_map,
        state_rows=state,
        c_frame_map_sha256=HASHES["frame_map"],
        c_state_sha256=HASHES["state"],
    )


def _candidate(
    identity: ActivationStoreIdentityV2,
    source: ActivationSourceFrameIdentityV2,
    *,
    local_idx: int,
    layer_idx: int,
) -> dict[str, object]:
    start = source.global_model_frame_idx - local_idx
    spans = tuple(
        FrameTokenSpan(
            identity=FrameIdentity(
                schema_version=SCHEMA_VERSION,
                trajectory_id=source.trajectory_id,
                model_frame_idx=start + pair_idx,
            ),
            pair_index=pair_idx,
            visual_positions=tuple(
                range(
                    pair_idx * 347,
                    pair_idx * 347 + 336,
                )
            ),
            action_positions=tuple(
                range(
                    pair_idx * 347 + 336,
                    (pair_idx + 1) * 347,
                )
            ),
        )
        for pair_idx in range(local_idx + 1)
    )
    frame_token_map = FrameTokenMap(
        schema_version=SCHEMA_VERSION,
        trajectory_id=source.trajectory_id,
        sequence_length=len(spans) * 347,
        spans=spans,
    )
    return candidate_row_from_frame_token_span_v2(
        store_identity=identity,
        source_identity=source,
        frame_token_map=frame_token_map,
        frame_token_map_sha256=f"{source.global_model_frame_idx + 8:064x}",
        layer_idx=layer_idx,
    )


class ActivationStoreV2ContractTests(unittest.TestCase):
    def test_v1_limitation_is_reproduced_without_modification(self) -> None:
        fixture = json.loads(V1_INDEX.read_text(encoding="utf-8"))
        source = fixture["index_rows"][0]
        candidate = {
            key: value
            for key, value in source.items()
            if key
            not in {
                "activation_chunk_id",
                "chunk_row_idx",
                "dtype",
                "pooling_method",
                "run_status",
                "token_region",
                "vector_shape",
            }
        }
        candidate["model_frame_idx"] = 16
        candidate["render_frame_idx"] = 16
        candidate["server_tick"] = 16
        candidate["action_idx"] = 16
        candidate["frame_token_positions"] = list(
            range(16 * 347, 16 * 347 + 336)
        )
        v1_identity = store_v1.ActivationStoreIdentity(
            schema_version=source["schema_version"],
            run_id=source["run_id"],
            checkpoint_hash=source["checkpoint_hash"],
            model_hash=source["model_hash"],
            config_hash=source["config_hash"],
            preprocess_hash=source["preprocess_hash"],
            accepted_manifest_hash=source["accepted_manifest_hash"],
            code_sha=source["code_sha"],
            hook_site=source["hook_site"],
            requested_layers=(0,),
            dtype="float32",
            hidden_width=2048,
        )
        with self.assertRaises(store_v1.ActivationStoreError) as caught:
            store_v1._candidate_rows_and_vectors(
                identity=v1_identity,
                rows=[candidate],
                vectors=np.zeros((1, 2048), dtype=np.float32),
            )
        self.assertEqual(caught.exception.field, "frame_token_positions")

    def test_global_and_context_local_identities_roll_over_without_collision(
        self,
    ) -> None:
        identity = _store_identity(layers=(0,))
        sources = _bindings(17)
        frame_15 = _candidate(
            identity,
            sources[15],
            local_idx=15,
            layer_idx=0,
        )
        frame_16 = _candidate(
            identity,
            sources[16],
            local_idx=0,
            layer_idx=0,
        )
        keys = validate_activation_rows_v2(
            [frame_15, frame_16],
            store_identity=identity,
            source_bindings=sources,
        )
        self.assertEqual(len(set(keys)), 2)
        self.assertEqual(
            frame_15["frame_token_positions"],
            list(range(15 * 347, 15 * 347 + 336)),
        )
        self.assertEqual(frame_16["frame_token_positions"], list(range(336)))
        self.assertNotEqual(
            keys[0].global_model_frame_idx,
            keys[1].global_model_frame_idx,
        )

    def test_repeated_local_indices_across_contexts_do_not_collide(self) -> None:
        identity = _store_identity(layers=(0,))
        sources = _bindings(33)
        rows = [
            _candidate(identity, sources[index], local_idx=0, layer_idx=0)
            for index in (0, 16, 32)
        ]
        keys = validate_activation_rows_v2(
            rows,
            store_identity=identity,
            source_bindings=sources,
        )
        self.assertEqual(len(set(keys)), 3)
        self.assertEqual(
            {tuple(row["frame_token_positions"]) for row in rows},
            {tuple(range(336))},
        )

    def test_visual_positions_ignore_global_frame_identity(self) -> None:
        self.assertEqual(
            derive_visual_token_positions(0),
            tuple(range(336)),
        )
        self.assertEqual(
            derive_visual_token_positions(15),
            tuple(range(15 * 347, 15 * 347 + 336)),
        )
        with self.assertRaises(ActivationStoreV2Error):
            derive_visual_token_positions(16)

    def test_exact_source_frame_and_tick_identity_is_fail_closed(self) -> None:
        identity = _store_identity(layers=(0,))
        sources = _bindings(17)
        row = _candidate(identity, sources[16], local_idx=0, layer_idx=0)
        for field in (
            "source_frame_id",
            "source_frame_idx",
            "source_tick",
            "c_frame_map_row_sha256",
            "c_state_row_sha256",
        ):
            changed = copy.deepcopy(row)
            changed[field] = (
                changed[field] + 1
                if isinstance(changed[field], int)
                else "f" * 64
            )
            with self.assertRaises(ActivationStoreV2Error) as caught:
                validate_activation_rows_v2(
                    [changed],
                    store_identity=identity,
                    source_bindings=sources,
                )
            self.assertEqual(caught.exception.code, "source_identity_conflict")

    def test_frame_token_map_conflict_is_fail_closed(self) -> None:
        identity = _store_identity(layers=(0,))
        source = _bindings(17)[16]
        wrong_span = FrameTokenSpan(
            identity=FrameIdentity(
                schema_version=SCHEMA_VERSION,
                trajectory_id=source.trajectory_id,
                model_frame_idx=15,
            ),
            pair_index=0,
            visual_positions=tuple(range(336)),
            action_positions=tuple(range(336, 347)),
        )
        wrong_map = FrameTokenMap(
            schema_version=SCHEMA_VERSION,
            trajectory_id=source.trajectory_id,
            sequence_length=347,
            spans=(wrong_span,),
        )
        with self.assertRaises(ActivationStoreV2Error) as caught:
            candidate_row_from_frame_token_span_v2(
                store_identity=identity,
                source_identity=source,
                frame_token_map=wrong_map,
                frame_token_map_sha256="9" * 64,
                layer_idx=0,
            )
        self.assertEqual(caught.exception.code, "source_identity_conflict")

    def test_all_248_global_frames_and_4960_rows_are_representable(self) -> None:
        identity = _store_identity(layers=(0,))
        sources = _bindings(248)
        rows = [
            _candidate(
                identity,
                source,
                local_idx=source.global_model_frame_idx % 16,
                layer_idx=0,
            )
            for source in sources
        ]
        keys = validate_activation_rows_v2(
            rows,
            store_identity=identity,
            source_bindings=sources,
            expected_global_frame_count=248,
        )
        self.assertEqual(len(keys), 248)
        self.assertEqual(
            expected_activation_row_count(248, FROZEN_PHASE6_LAYERS),
            4960,
        )

    def test_duplicate_global_frame_layer_key_fails(self) -> None:
        identity = _store_identity(layers=(0,))
        sources = _bindings(1)
        row = _candidate(identity, sources[0], local_idx=0, layer_idx=0)
        with self.assertRaises(ActivationStoreV2Error) as caught:
            validate_activation_rows_v2(
                [row, copy.deepcopy(row)],
                store_identity=identity,
                source_bindings=sources,
            )
        self.assertEqual(caught.exception.code, "duplicate_activation_key")

    def test_new_records_require_both_global_and_local_identities(self) -> None:
        identity = _store_identity(layers=(0,))
        sources = _bindings(1)
        row = _candidate(identity, sources[0], local_idx=0, layer_idx=0)
        for field in ("global_model_frame_idx", "context_local_pair_idx"):
            changed = copy.deepcopy(row)
            del changed[field]
            with self.assertRaises(ActivationStoreV2Error) as caught:
                validate_activation_rows_v2(
                    [changed],
                    store_identity=identity,
                    source_bindings=sources,
                )
            self.assertEqual(caught.exception.code, "missing_identity")

    def test_v1_ambiguous_identity_is_forbidden_in_v2(self) -> None:
        identity = _store_identity(layers=(0,))
        sources = _bindings(1)
        row = _candidate(identity, sources[0], local_idx=0, layer_idx=0)
        row["model_frame_idx"] = 0
        with self.assertRaises(ActivationStoreV2Error) as caught:
            validate_activation_rows_v2(
                [row],
                store_identity=identity,
                source_bindings=sources,
            )
        self.assertEqual(
            caught.exception.code,
            "v1_reinterpretation_forbidden",
        )

    def test_explicit_dispatch_preserves_v1_and_rejects_cross_reading(
        self,
    ) -> None:
        v1 = load_activation_index_dispatched(
            V1_INDEX,
            store_root=V1_FIXTURE_ROOT,
        )
        self.assertIsInstance(v1, store_v1.ActivationIndexSnapshot)
        self.assertEqual(
            v1.to_document()["format_version"],
            ACTIVATION_INDEX_V1_FORMAT_VERSION,
        )

        identity = _store_identity(layers=(0,))
        sources = _bindings(2)
        rows = [
            _candidate(identity, source, local_idx=index, layer_idx=0)
            for index, source in enumerate(sources)
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = publish_activation_chunk_v2(
                store_root=root,
                store_identity=identity,
                source_bindings=sources,
                rows=rows,
                vectors=np.zeros((2, 4), dtype=np.float32),
                creation_timestamp="2026-07-31T00:00:00Z",
            )
            self.assertIsInstance(snapshot, ActivationIndexSnapshotV2)
            loaded = load_activation_index_dispatched(
                root / snapshot.relative_path,
                store_root=root,
                source_bindings_v2=sources,
            )
            self.assertIsInstance(loaded, ActivationIndexSnapshotV2)
            self.assertEqual(
                loaded.to_document()["format_version"],
                ACTIVATION_INDEX_V2_FORMAT_VERSION,
            )
            with self.assertRaises(store_v1.ActivationStoreError):
                store_v1.load_activation_index_snapshot(
                    root / snapshot.relative_path,
                    store_root=root,
                )
            with self.assertRaises(ActivationStoreV2Error):
                load_activation_index_snapshot_v2(
                    V1_INDEX,
                    store_root=V1_FIXTURE_ROOT,
                    source_bindings=sources,
                )


if __name__ == "__main__":
    unittest.main()
