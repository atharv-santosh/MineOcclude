"""Focused structural tests for repaired-V2 P6 activation authority."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from scripts import run_large_scale_no_wall_p6_extraction as p6


class LargeScaleNoWallP6Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.input_manifest = json.loads(p6.REPO_INPUT_MANIFEST.read_text())
        cls.activation_manifest = json.loads(p6.REPO_ACTIVATION_MANIFEST.read_text())
        cls.durability = json.loads(p6.REPO_DURABILITY_RECEIPT.read_text())
        cls.receipt = json.loads(p6.REPO_RECEIPT.read_text())

    def test_protected_authorities_and_corrected_checkpoint_are_frozen(self) -> None:
        self.assertEqual(p6.sha256_file(p6.COHORT_LOCK), p6.COHORT_LOCK_SHA256)
        self.assertEqual(p6.sha256_file(p6.SPLIT_AUTHORITY), p6.SPLIT_SHA256)
        self.assertEqual(p6.sha256_file(p6.TEST_GUARD), p6.TEST_GUARD_SHA256)
        self.assertEqual(
            p6.sha256_file(p6.PRODUCTION_FRAME_MANIFEST),
            p6.PRODUCTION_FRAME_MANIFEST_SHA256,
        )
        self.assertEqual(p6.CHECKPOINT_SHA256, p6.wave2.PINNED_MAIN_CHECKPOINT_SHA256)
        self.assertEqual(p6.VAE_SHA256, p6.wave2.PINNED_VAE_CHECKPOINT_SHA256)

    def test_model_input_manifest_is_exact_repaired_v2_universe(self) -> None:
        manifest = self.input_manifest
        self.assertEqual(manifest["status"], "COMPLETE")
        self.assertEqual(manifest["trajectory_count"], 120)
        self.assertEqual(manifest["frames_per_trajectory"], 60)
        self.assertEqual(manifest["frame_count"], 7200)
        self.assertEqual(manifest["v1_trajectory_count"], 0)
        chunks = manifest["chunks"]
        self.assertEqual(len(chunks), 120)
        self.assertEqual(len({chunk["trajectory_spec_id"] for chunk in chunks}), 120)
        self.assertTrue(all(chunk["frame_count"] == 60 for chunk in chunks))
        self.assertTrue(
            all(chunk["payload_shape"] == [60, 3, 224, 384] for chunk in chunks)
        )
        self.assertTrue(
            all(
                chunk["trajectory_spec_id"].startswith("fresh_vp_v2_")
                for chunk in chunks
            )
        )

    def test_activation_manifest_is_only_layer4_and_exact_7200_rows(self) -> None:
        manifest = self.activation_manifest
        representation = manifest["representation"]
        self.assertEqual(manifest["status"], "COMPLETE")
        self.assertEqual(manifest["trajectory_count"], 120)
        self.assertEqual(manifest["frame_count"], 7200)
        self.assertEqual(representation["layer"], 4)
        self.assertFalse(representation["other_layers_retained"])
        self.assertEqual(representation["token_grid"], [14, 24])
        self.assertEqual(representation["token_count"], 336)
        self.assertEqual(representation["hidden_width"], 2048)
        self.assertEqual(representation["unpooled_dtype"], "float16")
        self.assertEqual(representation["pooled_dtype"], "float32")
        self.assertTrue(representation["teacher_forcing"])
        self.assertEqual(
            representation["window_schedule"],
            [[0, 16], [16, 32], [32, 48], [48, 60]],
        )
        chunks = manifest["chunks"]
        self.assertEqual(len(chunks), 120)
        self.assertEqual(sum(chunk["rows"]["row_count"] for chunk in chunks), 7200)
        self.assertTrue(
            all(chunk["unpooled"]["shape"] == [60, 336, 2048] for chunk in chunks)
        )
        self.assertTrue(all(chunk["pooled"]["shape"] == [60, 2048] for chunk in chunks))
        self.assertTrue(all(len(chunk["windows"]) == 4 for chunk in chunks))
        self.assertTrue(manifest["test_rows_extracted"])
        self.assertFalse(manifest["test_rows_used_for_selection"])
        self.assertTrue(manifest["checkpoint_hash_prompt_typo_resolved"])

    def test_integrity_and_s3_durability_receipts_pass(self) -> None:
        validation = self.receipt["validation"]
        self.assertEqual(validation["activation_rows"], 7200)
        self.assertEqual(validation["missing_activation_rows"], 0)
        self.assertEqual(validation["duplicate_activation_rows"], 0)
        self.assertEqual(validation["nonfinite_value_count"], 0)
        self.assertEqual(validation["pooled_equivalence_max_abs_diff"], 0.0)
        self.assertTrue(validation["pooled_equivalence_pass"])
        self.assertEqual(validation["runtime"]["forward_window_count"], 480)
        self.assertEqual(validation["runtime"]["trajectory_retry_count"], 0)
        self.assertEqual(self.durability["status"], "PASS")
        self.assertEqual(self.durability["expected_object_count"], 483)
        self.assertEqual(self.durability["observed_object_count"], 483)
        self.assertTrue(self.durability["object_sizes_valid"])
        self.assertTrue(self.durability["manifest_checksum_sha256_valid"])
        observed = hashlib.sha256(p6.REPO_ACTIVATION_MANIFEST.read_bytes()).hexdigest()
        self.assertEqual(observed, self.durability["activation_manifest_sha256"])

    def test_p6_boundary_remains_closed(self) -> None:
        receipt = self.receipt
        self.assertTrue(receipt["fresh_activations_extracted"])
        self.assertFalse(receipt["fresh_r2_computed"])
        self.assertFalse(receipt["token_ranking_performed"])
        self.assertFalse(receipt["alpha_selection_performed"])
        self.assertFalse(receipt["k_selection_performed"])
        self.assertFalse(receipt["target_null_executed"])
        self.assertFalse(receipt["p7_started"])
        self.assertTrue(receipt["safe_for_p7"])
        new_files = {path.name for path in Path(p6.STUDY_ROOT).glob("p6_*")}
        self.assertEqual(
            new_files,
            {
                "p6_activation_manifest.json",
                "p6_model_input_manifest.json",
                "p6_receipt.json",
                "p6_s3_durability_receipt.json",
            },
        )


if __name__ == "__main__":
    unittest.main()
