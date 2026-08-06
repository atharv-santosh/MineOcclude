"""Steps 8.5-8.8 — manifest freeze, generation safety, handoffs, and labelling."""

from __future__ import annotations

import unittest

from mineocclude.intervention.rollout_manifest import (
    DEFAULT_INTENDED_SHIFTS,
    ClipOutcome,
    ClipResult,
    ControlType,
    DoseSpec,
    HeldoutEvent,
    RolloutError,
    RolloutErrorCode,
    RolloutRunner,
    U4Classification,
    build_control_handoff,
    build_measurement_handoff,
    build_rollout_manifest,
    classify_u4,
    manifest_hash,
    validate_rollout_manifest,
)


def _events(count=5):
    return tuple(
        HeldoutEvent(
            event_id=f"heldout-{index:02d}",
            trajectory_id=f"layout_0{index}_ep1260{index}",
            layout_id=f"layout_0{index}",
            model_frame_idx=15,
        )
        for index in range(count)
    )


def _doses():
    return tuple(
        DoseSpec(
            dose_id=f"shift{shift:+d}".replace("+0", "0"),
            intended_block_shift=shift,
            alpha_requested=0.1 * shift,
            alpha_applied=0.1 * shift,
        )
        for shift in DEFAULT_INTENDED_SHIFTS
    )


def _manifest(**overrides):
    kwargs = dict(
        manifest_id="person-a-u4-week1-v0.1",
        handoff_id="person-a-u4-week1-handoff-v0.1",
        heldout_events=_events(),
        doses=_doses(),
        seeds=(20260801, 20260802),
        direction_version="b-direction-v1",
        layer_idx=12,
        timestep_idx=0,
        hook_site="decoder_layer_output_residual_stream",
        output_root="u4/week1",
        random_control_seeds=(20260803, 20260804),
        random_control_direction_versions=tuple(
            f"random-{index:02d}" for index in range(10)
        ),
        d_control_ids=("d-wrong-site-01", "d-wrong-layer-01"),
    )
    kwargs.update(overrides)
    return build_rollout_manifest(**kwargs)


class ManifestFreezeTests(unittest.TestCase):
    def test_five_events_five_shifts_two_seeds_yields_fifty_primary_clips(self):
        manifest = _manifest()
        counts = manifest["expected_counts"]
        self.assertEqual(counts["heldout_event_count"], 5)
        self.assertEqual(counts["dose_count"], 5)
        self.assertEqual(counts["seed_count"], 2)
        self.assertEqual(counts["primary_clip_count"], 50)

    def test_twenty_norm_matched_random_controls_are_encoded(self):
        manifest = _manifest()
        self.assertEqual(
            manifest["expected_counts"]["random_direction_control_count"], 20
        )
        randoms = [
            clip
            for clip in manifest["clips"]
            if clip["control_type"] == ControlType.RANDOM_DIRECTION.value
        ]
        self.assertEqual(len(randoms), 20)
        self.assertTrue(all(clip["intended_block_shift"] == 2 for clip in randoms))

    def test_d_specified_control_ids_are_included(self):
        manifest = _manifest()
        d_clips = [
            clip
            for clip in manifest["clips"]
            if clip["control_type"] == ControlType.D_SPECIFIED.value
        ]
        self.assertEqual(len(d_clips), 2)
        self.assertEqual(
            {clip["d_control_id"] for clip in d_clips},
            {"d-wrong-site-01", "d-wrong-layer-01"},
        )

    def test_total_clip_count_is_seventy_two(self):
        manifest = _manifest()
        self.assertEqual(manifest["expected_counts"]["total_clip_count"], 72)
        self.assertEqual(len(manifest["clips"]), 72)

    def test_every_clip_has_a_unique_id_and_path(self):
        manifest = _manifest()
        ids = [clip["clip_id"] for clip in manifest["clips"]]
        paths = [clip["output_path"] for clip in manifest["clips"]]
        self.assertEqual(len(set(ids)), len(ids))
        self.assertEqual(len(set(paths)), len(paths))

    def test_alpha_zero_clips_are_marked_non_overwritable(self):
        manifest = _manifest()
        zeros = [
            clip
            for clip in manifest["clips"]
            if clip["control_type"] == ControlType.ALPHA_ZERO.value
        ]
        self.assertEqual(len(zeros), 10)
        self.assertTrue(all(not clip["overwrite_permitted"] for clip in zeros))

    def test_no_clip_carries_an_outcome_dependent_selection_field(self):
        manifest = _manifest()
        self.assertFalse(manifest["contains_outcome_dependent_selection"])
        validate_rollout_manifest(manifest)

    def test_an_outcome_dependent_field_is_rejected(self):
        manifest = _manifest()
        manifest["clips"][0]["displacement"] = 2.0
        with self.assertRaises(RolloutError) as caught:
            validate_rollout_manifest(manifest)
        self.assertIs(
            caught.exception.code, RolloutErrorCode.OUTCOME_DEPENDENT_FIELD
        )

    def test_a_mismatched_expected_count_is_rejected(self):
        with self.assertRaises(RolloutError) as caught:
            _manifest(expected_primary_clip_count=40)
        self.assertIs(
            caught.exception.code, RolloutErrorCode.EXPECTED_COUNT_MISMATCH
        )

    def test_a_mismatched_random_control_count_is_rejected(self):
        with self.assertRaises(RolloutError) as caught:
            _manifest(random_control_seeds=(1,))
        self.assertIs(
            caught.exception.code, RolloutErrorCode.EXPECTED_COUNT_MISMATCH
        )

    def test_manifest_hash_is_stable(self):
        self.assertEqual(manifest_hash(_manifest()), manifest_hash(_manifest()))


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.manifest = _manifest()
        self.runner = RolloutRunner(manifest=self.manifest)

    def test_an_empty_run_reports_every_clip_pending(self):
        bundle = self.runner.bundle()
        self.assertEqual(bundle["expected_clip_count"], 72)
        self.assertEqual(bundle["pending_clip_count"], 72)
        self.assertFalse(bundle["complete"])
        self.assertFalse(bundle["outcome_selection_applied"])

    def test_a_clip_outside_the_manifest_is_refused(self):
        with self.assertRaises(RolloutError) as caught:
            self.runner.record(
                ClipResult(clip_id="not-in-manifest", outcome=ClipOutcome.COMPLETED)
            )
        self.assertIs(caught.exception.code, RolloutErrorCode.UNKNOWN_CLIP)

    def test_generation_failure_is_recorded_separately_from_non_persistence(self):
        clip_id = self.runner.clip_ids[0]
        self.runner.record(
            ClipResult(
                clip_id=clip_id,
                outcome=ClipOutcome.GENERATION_FAILURE,
                failure_reason="CUDA out of memory",
            )
        )
        bundle = self.runner.bundle()
        self.assertEqual(bundle["generation_failure_count"], 1)
        self.assertEqual(bundle["completed_clip_count"], 0)
        row = next(c for c in bundle["clips"] if c["clip_id"] == clip_id)
        self.assertTrue(row["generation_failure_distinct_from_non_persistence"])

    def test_an_alpha_zero_control_is_never_overwritten(self):
        zero_clip = next(
            clip["clip_id"]
            for clip in self.manifest["clips"]
            if clip["control_type"] == ControlType.ALPHA_ZERO.value
        )
        self.runner.record(
            ClipResult(
                clip_id=zero_clip,
                outcome=ClipOutcome.COMPLETED,
                output_hash="a" * 64,
            )
        )
        with self.assertRaises(RolloutError) as caught:
            self.runner.record(
                ClipResult(
                    clip_id=zero_clip,
                    outcome=ClipOutcome.COMPLETED,
                    output_hash="b" * 64,
                    supersedes_attempt=1,
                )
            )
        self.assertIs(caught.exception.code, RolloutErrorCode.OVERWRITE_FORBIDDEN)

    def test_replacing_a_completed_clip_requires_a_supersession_record(self):
        clip_id = next(
            clip["clip_id"]
            for clip in self.manifest["clips"]
            if clip["control_type"] == ControlType.INTERVENTION.value
        )
        self.runner.record(
            ClipResult(
                clip_id=clip_id, outcome=ClipOutcome.COMPLETED, output_hash="a" * 64
            )
        )
        with self.assertRaises(RolloutError) as caught:
            self.runner.record(
                ClipResult(
                    clip_id=clip_id,
                    outcome=ClipOutcome.COMPLETED,
                    output_hash="b" * 64,
                )
            )
        self.assertIs(
            caught.exception.code, RolloutErrorCode.SUPERSESSION_REQUIRED
        )

    def test_a_recorded_supersession_preserves_the_earlier_attempt(self):
        clip_id = next(
            clip["clip_id"]
            for clip in self.manifest["clips"]
            if clip["control_type"] == ControlType.INTERVENTION.value
        )
        self.runner.record(
            ClipResult(
                clip_id=clip_id, outcome=ClipOutcome.COMPLETED, output_hash="a" * 64
            )
        )
        self.runner.record(
            ClipResult(
                clip_id=clip_id,
                outcome=ClipOutcome.COMPLETED,
                output_hash="b" * 64,
                attempt=2,
                supersedes_attempt=1,
            )
        )
        bundle = self.runner.bundle()
        self.assertEqual(len(bundle["superseded_attempts"]), 1)
        self.assertEqual(
            bundle["superseded_attempts"][0]["outcome"],
            ClipOutcome.SUPERSEDED.value,
        )

    def test_pending_clip_ids_shrink_as_results_arrive(self):
        self.assertEqual(len(self.runner.pending_clip_ids()), 72)
        self.runner.record(
            ClipResult(
                clip_id=self.runner.clip_ids[0],
                outcome=ClipOutcome.COMPLETED,
                output_hash="a" * 64,
            )
        )
        self.assertEqual(len(self.runner.pending_clip_ids()), 71)


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.manifest = _manifest()
        runner = RolloutRunner(manifest=self.manifest)
        for index, clip_id in enumerate(runner.clip_ids):
            runner.record(
                ClipResult(
                    clip_id=clip_id,
                    outcome=ClipOutcome.COMPLETED,
                    output_hash=f"{index:064d}",
                )
            )
        self.bundle = runner.bundle()

    def test_measurement_handoff_transfers_every_clip(self):
        handoff = build_measurement_handoff(
            self.bundle,
            handoff_id="h-e",
            event_dose_table={"rows": []},
            detector_version="magenta-v1",
            homography_version="refit-v0.2",
        )
        self.assertEqual(handoff["expected_clip_count"], 72)
        self.assertEqual(handoff["produced_clip_count"], 72)
        self.assertEqual(handoff["missing_clip_count"], 0)
        self.assertFalse(handoff["selection_applied"])
        self.assertTrue(handoff["summary_withheld_until_full_table"])

    def test_control_handoff_carries_every_control_and_supersession(self):
        handoff = build_control_handoff(self.bundle, handoff_id="h-d")
        self.assertEqual(handoff["control_clip_count"], 32)
        self.assertEqual(
            handoff["control_type_counts"],
            {"alpha_zero": 10, "d_specified_control": 2, "random_direction": 20},
        )
        self.assertTrue(handoff["omission_auditable"])

    def test_a_non_bundle_document_is_refused(self):
        with self.assertRaises(RolloutError) as caught:
            build_control_handoff({"clips": []}, handoff_id="h")
        self.assertIs(caught.exception.code, RolloutErrorCode.INCOMPLETE_HANDOFF)


class ClassificationTests(unittest.TestCase):
    def _kwargs(self, **overrides):
        base = dict(
            injection_exact=True,
            baseline_persistence_confirmed=True,
            signed_displacement_pattern_confirmed=True,
            random_direction_specificity_confirmed=True,
            wrong_site_specificity_confirmed=True,
            ssim_within_natural_variation=True,
            predeclared_heldout_partition_present=True,
            measurement_valid=True,
            controls_valid=True,
            evidence_tables={"rollout_bundle": "bundle.json"},
        )
        base.update(overrides)
        return base

    def test_full_evidence_yields_a_causal_pilot(self):
        report = classify_u4(**self._kwargs())
        self.assertEqual(
            report["classification"], U4Classification.CAUSAL_PILOT.value
        )
        self.assertTrue(report["causal_claim_made"])

    def test_missing_predeclared_partition_caps_at_plumbing_only(self):
        report = classify_u4(
            **self._kwargs(predeclared_heldout_partition_present=False)
        )
        self.assertEqual(
            report["classification"], U4Classification.PLUMBING_ONLY.value
        )
        self.assertFalse(report["causal_claim_made"])

    def test_inexact_injection_is_invalid_measurement(self):
        report = classify_u4(**self._kwargs(injection_exact=False))
        self.assertEqual(
            report["classification"], U4Classification.INVALID_MEASUREMENT.value
        )
        self.assertIn(
            "the injection did not modify exactly the intended positions",
            report["reasons"],
        )

    def test_failed_measurement_withholds_the_claim_and_preserves_outputs(self):
        report = classify_u4(**self._kwargs(measurement_valid=False))
        self.assertEqual(
            report["classification"], U4Classification.INVALID_MEASUREMENT.value
        )
        self.assertTrue(report["outputs_preserved_on_failure"])
        self.assertFalse(report["retuned_on_test_videos"])

    def test_specific_controls_with_no_displacement_are_a_clean_negative(self):
        report = classify_u4(
            **self._kwargs(
                signed_displacement_pattern_confirmed=False,
                ssim_within_natural_variation=False,
            )
        )
        self.assertEqual(
            report["classification"], U4Classification.CLEAN_NEGATIVE.value
        )
        self.assertFalse(report["causal_claim_made"])

    def test_failed_controls_are_invalid_not_negative(self):
        report = classify_u4(**self._kwargs(controls_valid=False))
        self.assertEqual(
            report["classification"], U4Classification.INVALID_MEASUREMENT.value
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
