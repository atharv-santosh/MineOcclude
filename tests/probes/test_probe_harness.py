from __future__ import annotations

import unittest

from mineocclude.analysis.manifests import validate_sealed_artifact
from mineocclude.metrics.u1_mean import regression_metrics
from mineocclude.probes.mlp import (
    MLPTrainingSpec,
    build_mlp_fit_artifact,
    fit_mlp,
    fit_mlp_grouped_validation,
    fit_mlp_oof,
    select_mlp_eligible_layers,
)
from mineocclude.probes.ridge import (
    ProbeFitError,
    build_ridge_fit_artifact,
    build_scaler_artifact,
    fit_ridge,
    fit_ridge_oof,
    fit_standard_scaler,
)


class TestRidgeHarness(unittest.TestCase):
    def test_standardized_and_raw_predictions_are_equivalent(self) -> None:
        features = [[float(index), 1.0] for index in range(10)]
        targets = [2.0 * row[0] + 3.0 for row in features]
        model = fit_ridge(features, targets, alpha=0.1)
        self.assertEqual(model.scaler.constant_feature_indices, (1,))
        for standardized, raw in zip(
            model.predict(features), model.predict_raw_equivalent(features)
        ):
            self.assertAlmostEqual(standardized, raw, places=10)

    def test_oof_models_exclude_every_predicted_fold(self) -> None:
        features: list[list[float]] = []
        targets: list[float] = []
        layouts: list[str] = []
        folds: list[int] = []
        for layout_index, layout in enumerate("abcdef"):
            fold = min(layout_index, 4)
            for offset in range(3):
                value = float(layout_index * 3 + offset)
                features.append([value])
                targets.append(1.5 * value - 2.0)
                layouts.append(layout)
                folds.append(fold)
        result = fit_ridge_oof(
            features,
            targets,
            folds,
            layouts,
            inner_fold_count=4,
        )
        self.assertGreater(regression_metrics(targets, result.predictions).r2, 0.95)
        for fit in result.fits:
            self.assertTrue(
                all(folds[index] != fit.outer_fold_idx for index in fit.training_indices)
            )
            self.assertTrue(
                all(folds[index] == fit.outer_fold_idx for index in fit.test_indices)
            )
        first_fit = result.fits[0]
        scaler = build_scaler_artifact(
            first_fit.model.scaler,
            artifact_id="ridge_scaler_fold_0",
            code_sha="a" * 40,
            config_hash="b" * 64,
            input_manifest_hash="c" * 64,
            outer_fold_idx=first_fit.outer_fold_idx,
        )
        fit_artifact = build_ridge_fit_artifact(
            first_fit,
            artifact_id="ridge_fit_fold_0",
            code_sha="a" * 40,
            config_hash="b" * 64,
            input_manifest_hash="c" * 64,
            fold_manifest_hash="d" * 64,
            scaler_hash=scaler["artifact_hash"],
            layer_idx=2,
            hook_site="residual_stream",
            target_name="mu_oracle_blocks",
        )
        validate_sealed_artifact(scaler, expected_type="scaler_manifest")
        validate_sealed_artifact(
            fit_artifact,
            expected_type="ridge_fit_manifest",
        )


class TestMLPHarness(unittest.TestCase):
    def test_layer_selection_uses_validation_only(self) -> None:
        records = [
            {
                "layer_idx": layer,
                "validation_r2": score,
                "selection_split": "validation",
                "uses_test_data": False,
            }
            for layer, score in ((2, 0.3), (3, 0.8), (4, 0.7), (5, 0.6))
        ]
        self.assertEqual(select_mlp_eligible_layers(records), (3, 4, 5))
        records[0]["uses_test_data"] = True
        with self.assertRaises(ProbeFitError):
            select_mlp_eligible_layers(records)

    def test_small_mlp_fit_is_deterministic_and_finite(self) -> None:
        training_x = [[index / 10.0] for index in range(-20, 21)]
        training_y = [2.0 * row[0] + 1.0 for row in training_x]
        validation_x = [[-2.5], [-1.5], [1.5], [2.5]]
        validation_y = [2.0 * row[0] + 1.0 for row in validation_x]
        spec = MLPTrainingSpec(
            hidden_layers=(8, 4),
            maximum_epochs=250,
            early_stopping_patience=30,
            batch_size=16,
            seed=42,
        )
        first = fit_mlp(
            training_x,
            training_y,
            validation_x,
            validation_y,
            spec=spec,
        )
        second = fit_mlp(
            training_x,
            training_y,
            validation_x,
            validation_y,
            spec=spec,
        )
        self.assertEqual(first.predict(validation_x), second.predict(validation_x))
        self.assertLess(first.best_validation_mse, 0.2)

    def test_grouped_mlp_validation_never_splits_a_layout(self) -> None:
        features = [[float(index)] for index in range(12)]
        targets = [float(index) for index in range(12)]
        groups = [f"layout_{index // 3}" for index in range(12)]
        fit = fit_mlp_grouped_validation(
            features,
            targets,
            groups,
            n_splits=4,
            spec=MLPTrainingSpec(
                hidden_layers=(4, 2),
                maximum_epochs=5,
                early_stopping_patience=2,
                batch_size=4,
                seed=5,
            ),
        )
        self.assertFalse(
            set(fit.training_group_ids) & set(fit.validation_group_ids)
        )
        self.assertEqual(
            fit.model.scaler.training_row_count, len(fit.training_indices)
        )

    def test_mlp_oof_never_uses_the_predicted_outer_fold(self) -> None:
        features: list[list[float]] = []
        targets: list[float] = []
        layouts: list[str] = []
        folds: list[int] = []
        for layout_index in range(5):
            for offset in range(2):
                value = float(layout_index * 2 + offset)
                features.append([value])
                targets.append(value)
                layouts.append(f"layout_{layout_index}")
                folds.append(layout_index)
        result = fit_mlp_oof(
            features,
            targets,
            folds,
            layouts,
            inner_fold_count=4,
            spec=MLPTrainingSpec(
                hidden_layers=(4, 2),
                maximum_epochs=3,
                early_stopping_patience=2,
                batch_size=4,
                seed=11,
            ),
        )
        self.assertEqual(len(result.predictions), len(targets))
        for fit in result.fits:
            self.assertTrue(
                all(
                    folds[index] != fit.outer_fold_idx
                    for index in (*fit.training_indices, *fit.validation_indices)
                )
            )
            self.assertTrue(
                all(
                    folds[index] == fit.outer_fold_idx
                    for index in fit.test_indices
                )
            )
        artifact = build_mlp_fit_artifact(
            result.fits[0],
            artifact_id="mlp_fit_fold_0",
            code_sha="a" * 40,
            config_hash="b" * 64,
            input_manifest_hash="c" * 64,
            fold_manifest_hash="d" * 64,
            layer_idx=2,
            hook_site="residual_stream",
            target_name="mu_oracle_blocks",
        )
        self.assertEqual(artifact["fit_scope"], "outer_fold_oof")
        validate_sealed_artifact(
            artifact,
            expected_type="mlp_fit_manifest",
        )


if __name__ == "__main__":
    unittest.main()
