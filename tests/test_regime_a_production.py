from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from mineocclude.regime_a import (
    CANONICAL_FRAME_WIDTH,
    RAW_FRAMEBUFFER_HEIGHT,
    RAW_FRAMEBUFFER_WIDTH,
    AtomicTrajectoryStore,
    HashChainLedger,
    RegimeAError,
    ZeroTSS,
    assign_stable_hidden_tau,
    best_k_features,
    canonical_crop_window,
    bootstrap_macro_r2,
    build_null_mappings,
    canonical_sha256,
    classify_visibility,
    constant_velocity_baseline,
    duration_bin,
    fold_assignment,
    generate_scientific_specs,
    macro_r2,
    project_world_to_coordinates,
    rank_best_k_tokens,
    ridge_fit_predict,
    sha256_file,
    trailing_window_indices,
    training_mean_baseline,
    trajectory_r2,
    validate_best_k_selection,
    validate_frame_alignment,
    validate_null_mappings,
    validate_scientific_specs,
    verified_local_durable_copy,
)


STUDY_HASH = "6" * 64


class RegimeAProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.specs = generate_scientific_specs(STUDY_HASH)

    def test_manifest_seed_fold_determinism_and_geometry(self) -> None:
        again = generate_scientific_specs(STUDY_HASH)
        self.assertEqual(canonical_sha256(self.specs), canonical_sha256(again))
        receipt = validate_scientific_specs(self.specs)
        self.assertEqual(receipt["fold_counts"], {0: 5, 1: 5, 2: 5, 3: 5, 4: 5})
        self.assertEqual(fold_assignment(self.specs), {row["trajectory_spec_id"]: row["outer_fold"] for row in self.specs})

    def test_alignment_entity_and_windows(self) -> None:
        rows = [
            {"model_frame_idx": i, "server_tick": i, "render_frame_idx": i, "action_idx": i,
             "target_entity_id": "uuid", "target_present": True}
            for i in range(18)
        ]
        validate_frame_alignment(rows, "uuid")
        self.assertEqual(trailing_window_indices(15, 18), tuple(range(16)))
        self.assertEqual(trailing_window_indices(16, 18), tuple(range(1, 17)))
        rows[5]["target_entity_id"] = "replacement"
        with self.assertRaises(RegimeAError):
            validate_frame_alignment(rows, "uuid")

    def test_tau_visibility_guard_and_bins(self) -> None:
        self.assertEqual(classify_visibility("visible", "detected"), "VISIBLE_AGREEMENT")
        self.assertEqual(classify_visibility("occluded", "not_detected"), "OCCLUDED_AGREEMENT")
        rows = ([{"geometric_status": "visible", "magenta_status": "detected"}] * 15
                + [{"geometric_status": "occluded", "magenta_status": "detected"}] * 3
                + [{"geometric_status": "occluded", "magenta_status": "not_detected"}] * 19)
        labeled = assign_stable_hidden_tau(rows, "LEFT_TO_RIGHT")
        self.assertIsNone(labeled[17]["tau"])
        self.assertEqual(labeled[18]["tau"], 1)
        self.assertEqual([duration_bin(x) for x in (1, 5, 9, 13, 16, 20)],
                         ["SHORT", "INTERMEDIATE", "LONG", "NEAR_CONTEXT", "BEYOND_CONTEXT", None])

    def test_projection_and_baselines(self) -> None:
        projection = project_world_to_coordinates(0.5, 6.0, [[300, 0, 960], [0, 0, 523], [0, 0, 1]])
        # The homography lands this point at raw framebuffer x=1110. The
        # canonical frame is the 16:9 centre crop of the raw framebuffer, then
        # resized, so the expected value is derived from that crop rather than
        # from the superseded bare 640/1920 scale, which returned 370.0 and was
        # exact only at the frame centre.
        crop_x0, _, crop_width, _ = canonical_crop_window()
        self.assertAlmostEqual(projection["screen_x"],
                               (1110.0 - crop_x0) * CANONICAL_FRAME_WIDTH / crop_width)
        self.assertEqual(training_mean_baseline([1, 3], 2).tolist(), [2, 2])
        predicted = constant_velocity_baseline([0, 1, 2], [1, 3, 5], [3, 4])
        np.testing.assert_allclose(predicted, [7, 9])

    def test_canonical_crop_window_reproduces_to_canonical(self) -> None:
        """Prove the restated crop rule, rather than trusting the restatement.

        ``project_world_to_coordinates`` reimplements the centre crop that
        ``preprocess.to_canonical`` performs before resizing. If the two ever
        disagree, every prospective screen and token coordinate is silently
        wrong, so the agreement is checked against the real function.
        """
        from mineocclude.data.preprocess import to_canonical

        crop_x0, crop_y0, crop_width, crop_height = canonical_crop_window()
        raw = np.zeros((RAW_FRAMEBUFFER_HEIGHT, RAW_FRAMEBUFFER_WIDTH, 3), dtype=np.uint8)
        raw[..., 0] = 255  # red everywhere the crop is expected to discard
        raw[crop_y0:crop_y0 + crop_height, crop_x0:crop_x0 + crop_width] = (0, 255, 0)
        canonical = to_canonical(raw)
        # Nothing outside the predicted window survives the real crop.
        self.assertEqual(int(canonical[..., 0].max()), 0)
        self.assertEqual(int(canonical[..., 1].min()), 255)
        # ...and the window is not larger than the real crop either: shrinking
        # it by one column on each side leaves discarded pixels visible.
        narrow = raw.copy()
        narrow[:, crop_x0] = (255, 0, 0)
        narrow[:, crop_x0 + crop_width - 1] = (255, 0, 0)
        self.assertGreater(int(to_canonical(narrow)[..., 0].max()), 0)

    def test_primary_metric_and_zero_tss(self) -> None:
        result = macro_r2({"a": [0, 1], "b": [0, 2]}, {"a": [0, 1], "b": [1, 1]})
        self.assertAlmostEqual(result["macro_r2"], 0.5)
        with self.assertRaises(ZeroTSS):
            trajectory_r2([1, 1], [1, 1])

    def test_best_k_training_scope_and_ridge(self) -> None:
        selection = {"trajectory_ids_used": ["a", "b"], "layer": 4, "selected_k": 4,
                     "shared_across_bins": True, "shared_across_directions": True}
        validate_best_k_selection(selection, {"a", "b"}, {"c"})
        selection["trajectory_ids_used"].append("c")
        with self.assertRaises(RegimeAError):
            validate_best_k_selection(selection, {"a", "b"}, {"c"})
        rng = np.random.default_rng(4)
        tensor = rng.normal(size=(8, 128, 3))
        target = tensor[:, 7, 1]
        ranking = rank_best_k_tokens(tensor, target)
        self.assertEqual(int(ranking[0]), 7)
        reduced = best_k_features(tensor, ranking, 4)
        prediction = ridge_fit_predict(reduced[:6], target[:6], reduced[6:], 1.0)
        self.assertEqual(prediction.shape, (2,))

    def test_bootstrap_is_whole_trajectory_and_deterministic(self) -> None:
        first = bootstrap_macro_r2({"a": 0.1, "b": 0.5, "c": 0.9}, 2000, 8)
        second = bootstrap_macro_r2({"a": 0.1, "b": 0.5, "c": 0.9}, 2000, 8)
        np.testing.assert_array_equal(first, second)

    def test_null_donors_are_training_only_stratified_unique_and_no_self(self) -> None:
        ids = [f"l{i}" for i in range(10)] + [f"r{i}" for i in range(10)]
        strata = {identity: identity[0] for identity in ids}
        mappings = build_null_mappings(ids, strata, b=49, seed=9)
        validate_null_mappings(mappings, set(ids), strata)
        broken = [dict(row) for row in mappings]
        broken[0]["l0"] = "l0"
        with self.assertRaises(RegimeAError):
            validate_null_mappings(broken, set(ids), strata)

    def test_atomic_hash_durable_and_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = AtomicTrajectoryStore(root / "stage")
            partial = store.begin("t1", "a" * 64)
            (partial / "payload.bin").write_bytes(b"scientifically-empty-test")
            final = store.finalize(partial, "t1", "a" * 64)
            store.validate("t1", "a" * 64)
            receipt = verified_local_durable_copy(final / "completion.json", root / "durable" / "completion.json")
            self.assertEqual(receipt["sha256"], sha256_file(root / "durable" / "completion.json"))
            with self.assertRaises(FileExistsError):
                store.begin("t1", "a" * 64)
            ledger = HashChainLedger(root / "ledger.jsonl")
            ledger.append("t1", "PLANNED")
            ledger.append("t1", "COMPLETE_VALIDATED_DURABLE")
            self.assertEqual(HashChainLedger(root / "ledger.jsonl").complete_ids(), {"t1"})


if __name__ == "__main__":
    unittest.main()
