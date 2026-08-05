package com.mineocclude.server;

import org.junit.jupiter.api.Test;

import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashSet;

import static com.mineocclude.server.TargetRetentionPolicy.AnimalRemovalDecision.PRESERVE_TAGGED_EXPERIMENT_TARGET;
import static com.mineocclude.server.TargetRetentionPolicy.AnimalRemovalDecision.REMOVE_UNCONTROLLED_ANIMAL;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Eleven focused regression cases corresponding to the C1.5 repair gate. */
public final class TargetRetentionPolicyTest {
    @Test
    void spawnAnimalsFalseStillRemovesNaturalPassiveMobs() {
        assertEquals(REMOVE_UNCONTROLLED_ANIMAL,
                TargetRetentionPolicy.animalRemovalDecision(false, true, false));
    }

    @Test
    void explicitlyTaggedExperimentalTargetIsPermitted() {
        assertEquals(PRESERVE_TAGGED_EXPERIMENT_TARGET,
                TargetRetentionPolicy.animalRemovalDecision(false, true, true));
    }

    @Test
    void genericRemovalExemptionIsNarrowlyTagBound() {
        assertFalse(TargetRetentionPolicy.animalRemovalDecision(false, true, false)
                == PRESERVE_TAGGED_EXPERIMENT_TARGET);
    }

    @Test
    void validTargetSurvivesResetToArmedValidation() {
        assertTrue(TargetRetentionPolicy.isValid(validSnapshot()));
    }

    @Test
    void validTargetSurvivesArmedToCaptureValidation() {
        assertTrue(TargetRetentionPolicy.validate(validSnapshot()).isEmpty());
    }

    @Test
    void identifiersTagsPoseStateAndLocationAreRequired() {
        TargetRetentionPolicy.Snapshot invalid = snapshot(1, true, false, false,
                "minecraft:sheep", "magenta", true, true, true, true,
                true, false, true, -6.0, 4.0, 6.0);
        assertTrue(TargetRetentionPolicy.validate(invalid).contains("target tag is missing"));
        assertTrue(TargetRetentionPolicy.validate(invalid).contains("target UUID changed"));
    }

    @Test
    void staleTargetsFromPreviousEpisodesAreSelectedForRemoval() {
        assertEquals(new LinkedHashSet<>(Arrays.asList("old-a", "old-b")),
                TargetRetentionPolicy.staleTargetIds(
                        Arrays.asList("old-a", "current", "old-b"), "current"));
    }

    @Test
    void exactlyOneIntendedTargetIsRequiredAfterReset() {
        assertTrue(TargetRetentionPolicy.isValid(validSnapshot()));
        assertFalse(TargetRetentionPolicy.isValid(snapshot(2, true, false, true,
                "minecraft:sheep", "magenta", true, true, true, true,
                true, true, true, -6.0, 4.0, 6.0)));
    }

    @Test
    void LayoutChangeCannotLeaveDuplicateTaggedTargets() {
        assertEquals(Collections.singleton("layout_01_target"),
                TargetRetentionPolicy.staleTargetIds(
                        Arrays.asList("layout_01_target", "layout_02_target"),
                        "layout_02_target"));
    }

    @Test
    void stopCleanupRequiresZeroTaggedTargets() {
        TargetRetentionPolicy.Snapshot stopped = new TargetRetentionPolicy.Snapshot(
                false, 1, false, true, false, "none", "none",
                false, false, false, false, false, false, true,
                Double.NaN, Double.NaN, Double.NaN,
                Double.NaN, Double.NaN, Double.NaN);
        assertTrue(TargetRetentionPolicy.validate(stopped).contains(
                "no-target scene contains tagged experiment targets"));
    }

    @Test
    void retentionFailureProducesAValidationRefusal() {
        TargetRetentionPolicy.Snapshot removed = snapshot(0, false, true, true,
                "minecraft:sheep", "magenta", true, true, true, true,
                true, true, true, -6.0, 4.0, 6.0);
        assertFalse(TargetRetentionPolicy.isValid(removed));
        assertTrue(TargetRetentionPolicy.validate(removed).contains("target is not alive"));
        assertTrue(TargetRetentionPolicy.validate(removed).contains("target is marked removed"));
    }

    private static TargetRetentionPolicy.Snapshot validSnapshot() {
        return snapshot(1, true, false, true, "minecraft:sheep", "magenta",
                true, true, true, true, true, true, true, -6.0, 4.0, 6.0);
    }

    private static TargetRetentionPolicy.Snapshot snapshot(
            int count, boolean alive, boolean removed, boolean tagged,
            String type, String color, boolean noAi, boolean silent,
            boolean persistent, boolean invulnerable, boolean adult,
            boolean uuidMatches, boolean worldMatches,
            double actualX, double actualY, double actualZ) {
        return new TargetRetentionPolicy.Snapshot(true, count, alive, removed,
                tagged, type, color, noAi, silent, persistent, invulnerable,
                adult, uuidMatches, worldMatches,
                -6.0, 4.0, 6.0, actualX, actualY, actualZ);
    }
}
