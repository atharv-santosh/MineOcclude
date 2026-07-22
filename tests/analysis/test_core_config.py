from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from mineocclude.analysis.config import (
    AnalysisConfigError,
    load_core_analysis_config,
    validate_core_analysis_config,
)


class TestCoreAnalysisConfig(unittest.TestCase):
    def test_frozen_config_passes(self) -> None:
        config = load_core_analysis_config()
        self.assertEqual(config["schema_version"], "1.0")
        self.assertEqual(config["targets"]["x_true_blocks"]["use"], "scoring_only")

    def test_every_result_affecting_setting_is_frozen(self) -> None:
        mutations = (
            (("analysis_config_version",), "unreviewed-v2"),
            (("status",), "mutable"),
            (("targets", "mu_oracle_blocks", "unit"), "meters"),
            (("targets", "mu_oracle_blocks", "source"), "unknown"),
            (("targets", "x_true_blocks", "use"), "oracle_input"),
            (("filters", "allowed_status"), ["excluded"]),
            (("filters", "required_activation_run_status"), "partial"),
            (("cross_validation", "fit_scaler_on_training_fold_only"), False),
            (("cross_validation", "test_layout_may_select_layer"), True),
            (("ridge", "selection_scope"), "all_rows"),
            (("mlp", "activation"), "sigmoid"),
            (("resampling", "permutation_count_mvp"), 1),
            (("resampling", "bootstrap_count_mvp"), 1),
            (("resampling", "bootstrap_count_final_minimum"), 1),
            (("outputs", "U4"), []),
            (("coverage_levels",), [0.95]),
        )

        for path, value in mutations:
            with self.subTest(path=path):
                unsafe = copy.deepcopy(load_core_analysis_config())
                location = unsafe
                for key in path[:-1]:
                    location = location[key]
                location[path[-1]] = value
                with self.assertRaises(AnalysisConfigError):
                    validate_core_analysis_config(unsafe)

    def test_malformed_target_metadata_uses_public_error(self) -> None:
        unsafe = copy.deepcopy(load_core_analysis_config())
        unsafe["targets"]["x_true_blocks"] = None
        with self.assertRaises(AnalysisConfigError):
            validate_core_analysis_config(unsafe)

    def test_invalid_json_uses_public_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.yaml"
            path.write_text("{not valid json", encoding="utf-8")
            with self.assertRaises(AnalysisConfigError):
                load_core_analysis_config(path)


if __name__ == "__main__":
    unittest.main()
