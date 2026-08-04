package com.mineocclude.server;

import net.minecraft.entity.Entity;
import net.minecraft.entity.passive.SheepEntity;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

/**
 * Narrow policy boundary for the one explicitly created experiment target.
 *
 * <p>Minecraft 1.16.5 removes every {@code AnimalEntity} during the server
 * tick when {@code spawn-animals=false}; the check does not distinguish
 * natural spawning from an explicitly created persistent entity. MineOcclude
 * keeps that server setting false and suppresses only that removal call for a
 * sheep carrying the private experiment tag below. Every other passive mob is
 * still governed by the vanilla removal path.</p>
 */
public final class TargetRetentionPolicy {
    public static final String EXPERIMENT_TARGET_TAG = "mineocclude_experimental_target";
    public static final double LOCATION_TOLERANCE_BLOCKS = 1.0e-6;

    private TargetRetentionPolicy() {}

    public enum AnimalRemovalDecision {
        VANILLA_SETTING_ALLOWS_ANIMALS,
        NOT_AN_ANIMAL,
        PRESERVE_TAGGED_EXPERIMENT_TARGET,
        REMOVE_UNCONTROLLED_ANIMAL
    }

    /** Pure decision used by the mixin and unit tests. */
    public static AnimalRemovalDecision animalRemovalDecision(
            boolean spawnAnimals, boolean animalEntity, boolean taggedExperimentSheep) {
        if (spawnAnimals) return AnimalRemovalDecision.VANILLA_SETTING_ALLOWS_ANIMALS;
        if (!animalEntity) return AnimalRemovalDecision.NOT_AN_ANIMAL;
        if (taggedExperimentSheep) {
            return AnimalRemovalDecision.PRESERVE_TAGGED_EXPERIMENT_TARGET;
        }
        return AnimalRemovalDecision.REMOVE_UNCONTROLLED_ANIMAL;
    }

    /** True only for MineOcclude's tagged sheep, never for natural animals. */
    public static boolean isTaggedExperimentTarget(Entity entity) {
        return entity instanceof SheepEntity
                && entity.getScoreboardTags().contains(EXPERIMENT_TARGET_TAG);
    }

    /** Called only at vanilla's spawn-animals=false AnimalEntity removal site. */
    public static boolean suppressVanillaAnimalRemoval(Entity entity) {
        return isTaggedExperimentTarget(entity);
    }

    /** IDs which must be removed before installing one intended target. */
    public static Set<String> staleTargetIds(Iterable<String> loadedIds, String intendedId) {
        Set<String> stale = new LinkedHashSet<>();
        for (String id : loadedIds) {
            if (intendedId == null || !intendedId.equals(id)) stale.add(id);
        }
        return stale;
    }

    /** Immutable observation passed through the hard validation gate. */
    public static final class Snapshot {
        public final boolean targetRequired;
        public final int taggedTargetCount;
        public final boolean alive;
        public final boolean removed;
        public final boolean tagged;
        public final String entityType;
        public final String color;
        public final boolean aiDisabled;
        public final boolean silent;
        public final boolean persistent;
        public final boolean invulnerable;
        public final boolean adult;
        public final boolean uuidMatches;
        public final boolean worldMatches;
        public final double expectedX, expectedY, expectedZ;
        public final double actualX, actualY, actualZ;

        public Snapshot(boolean targetRequired, int taggedTargetCount,
                        boolean alive, boolean removed, boolean tagged,
                        String entityType, String color, boolean aiDisabled,
                        boolean silent, boolean persistent, boolean invulnerable,
                        boolean adult, boolean uuidMatches, boolean worldMatches,
                        double expectedX, double expectedY, double expectedZ,
                        double actualX, double actualY, double actualZ) {
            this.targetRequired = targetRequired;
            this.taggedTargetCount = taggedTargetCount;
            this.alive = alive;
            this.removed = removed;
            this.tagged = tagged;
            this.entityType = entityType;
            this.color = color;
            this.aiDisabled = aiDisabled;
            this.silent = silent;
            this.persistent = persistent;
            this.invulnerable = invulnerable;
            this.adult = adult;
            this.uuidMatches = uuidMatches;
            this.worldMatches = worldMatches;
            this.expectedX = expectedX;
            this.expectedY = expectedY;
            this.expectedZ = expectedZ;
            this.actualX = actualX;
            this.actualY = actualY;
            this.actualZ = actualZ;
        }
    }

    /** Returns every reason a capture must be refused; empty means valid. */
    public static List<String> validate(Snapshot snapshot) {
        List<String> problems = new ArrayList<>();
        if (!snapshot.targetRequired) {
            if (snapshot.taggedTargetCount != 0) {
                problems.add("no-target scene contains tagged experiment targets");
            }
            return problems;
        }
        if (snapshot.taggedTargetCount != 1) problems.add("tagged target count is not exactly one");
        if (!snapshot.alive) problems.add("target is not alive");
        if (snapshot.removed) problems.add("target is marked removed");
        if (!snapshot.tagged) problems.add("target tag is missing");
        if (!"minecraft:sheep".equals(snapshot.entityType)) problems.add("target entity type is not minecraft:sheep");
        if (!"magenta".equals(snapshot.color)) problems.add("target color is not magenta");
        if (!snapshot.aiDisabled) problems.add("target NoAI state is missing");
        if (!snapshot.silent) problems.add("target Silent state is missing");
        if (!snapshot.persistent) problems.add("target PersistenceRequired state is missing");
        if (!snapshot.invulnerable) problems.add("target invulnerable state is missing");
        if (!snapshot.adult) problems.add("target is not an adult");
        if (!snapshot.uuidMatches) problems.add("target UUID changed");
        if (!snapshot.worldMatches) problems.add("target world changed");
        if (!close(snapshot.expectedX, snapshot.actualX)
                || !close(snapshot.expectedY, snapshot.actualY)
                || !close(snapshot.expectedZ, snapshot.actualZ)) {
            problems.add("target location differs from the authoritative pose");
        }
        return problems;
    }

    public static boolean isValid(Snapshot snapshot) {
        return validate(snapshot).isEmpty();
    }

    private static boolean close(double expected, double actual) {
        return Double.isFinite(expected) && Double.isFinite(actual)
                && Math.abs(expected - actual) <= LOCATION_TOLERANCE_BLOCKS;
    }
}
