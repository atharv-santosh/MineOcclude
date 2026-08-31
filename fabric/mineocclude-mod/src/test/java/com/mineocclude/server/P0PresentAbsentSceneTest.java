package com.mineocclude.server;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Experiment III authority 7.11 — the P0 present/absent contrast must change
 * ONLY target presence.
 *
 * <p>The defect these tests exist to prevent is specific and silent: if the
 * absent state removed or substituted the wall, then
 * {@code D(c,p,b) = ||P - A||^2} would measure the WALL rather than the target.
 * Every candidate's RVE would then be dominated by its own opacity against
 * open air, the ladder would still look well-formed, and nothing downstream
 * would notice. Wall presence must follow the condition; target presence must
 * be an independent axis.
 */
final class P0PresentAbsentSceneTest {

    private static final double LANE_MIN = -8.0;
    private static final double LANE_MAX = 8.0;

    private static EpisodeConfig p0Unit(WallCondition condition, boolean targetPresent) {
        return new EpisodeConfig(
                "layout_01", 90001L, 90001L,
                0.0, 0.0, 32,
                LANE_MIN, LANE_MAX, 0.0,
                -2.5, 2.5,
                6.0, -4.0, 5.5,
                4.0, EpisodeConfig.Axis.X, condition.scene, 0,
                0, -1, 0.0, true, "P0_STATIC", "P0", condition, targetPresent);
    }

    @Test
    void candidateAbsentStateKeepsTheSameWallAndMaterial() {
        WallCondition lime = WallCondition.of("L2", "minecraft:lime_stained_glass");
        EpisodeConfig present = p0Unit(lime, true);
        EpisodeConfig absent = p0Unit(lime, false);

        // Only target presence differs.
        assertTrue(present.spawnSheep());
        assertFalse(absent.spawnSheep());

        // The wall stands in both halves, of the same material.
        assertTrue(present.buildWall(), "present half must build the wall");
        assertTrue(absent.buildWall(), "ABSENT half must still build the wall");
        assertEquals(present.condition.wallBlockId, absent.condition.wallBlockId);
        assertEquals("minecraft:lime_stained_glass", absent.condition.wallBlockId);
        assertEquals(present.condition.wallState(), absent.condition.wallState());
    }

    @Test
    void everyEligibleCandidateKeepsItsMaterialWhenTheTargetIsAbsent() {
        for (String block : WallCondition.ELIGIBLE_STAINED_GLASS) {
            WallCondition condition = WallCondition.of("L1", block);
            EpisodeConfig absent = p0Unit(condition, false);
            assertTrue(absent.buildWall(), block + " must still stand when the target is absent");
            assertFalse(absent.spawnSheep());
            assertEquals(block, absent.condition.wallBlockId);
        }
    }

    @Test
    void stoneAbsentStateKeepsTheStoneWall() {
        WallCondition stone = WallCondition.of("L4", "minecraft:stone");
        EpisodeConfig absent = p0Unit(stone, false);
        assertTrue(absent.buildWall());
        assertFalse(absent.spawnSheep());
        assertEquals("minecraft:stone", absent.condition.wallBlockId);
    }

    @Test
    void l0AbsentStateHasNoWallAndNoTarget() {
        WallCondition l0 = WallCondition.of("L0", "minecraft:air");
        EpisodeConfig present = p0Unit(l0, true);
        EpisodeConfig absent = p0Unit(l0, false);

        assertFalse(present.buildWall(), "L0 is the no-wall anchor");
        assertFalse(absent.buildWall(), "L0 must not grow a wall when the target is absent");
        assertTrue(present.spawnSheep());
        assertFalse(absent.spawnSheep());
    }

    @Test
    void cameraLightingAndGeometryAreIdenticalAcrossTheContrast() {
        WallCondition cyan = WallCondition.of("L3", "minecraft:cyan_stained_glass");
        EpisodeConfig present = p0Unit(cyan, true);
        EpisodeConfig absent = p0Unit(cyan, false);

        assertEquals(present.cameraDist, absent.cameraDist);
        assertEquals(present.lockCamera, absent.lockCamera);
        assertEquals(present.laneY, absent.laneY);
        assertEquals(present.wallSegMin, absent.wallSegMin);
        assertEquals(present.wallSegMax, absent.wallSegMax);
        assertEquals(present.wallOrthoConst, absent.wallOrthoConst);
        assertEquals(present.wallOrthoOffset, absent.wallOrthoOffset);
        assertEquals(present.wallAxis, absent.wallAxis);
        assertEquals(present.layoutId, absent.layoutId);
        assertEquals(present.startPos, absent.startPos, 0.0);
    }

    @Test
    void p0UnitsAreStaticSoTheSceneIsSettled() {
        WallCondition white = WallCondition.of("L1", "minecraft:white_stained_glass");
        EpisodeConfig unit = p0Unit(white, true);
        assertEquals(0.0, unit.driftV, 0.0);
        assertEquals(0.0, unit.processQ, 0.0);
    }

    @Test
    void materialChangeChangesTheArenaCacheKey() {
        // C07: without the material in the cache key a stone->glass switch hits
        // the cache and captures a whole batch under the previous wall.
        WallCondition lime = WallCondition.of("L2", "minecraft:lime_stained_glass");
        WallCondition cyan = WallCondition.of("L2", "minecraft:cyan_stained_glass");
        assertNotEquals(lime.cacheKeyFragment(), cyan.cacheKeyFragment());
    }

    @Test
    void legacyConstructorsStillDeriveTargetPresenceFromTheScene() {
        // The independent axis must not change any pre-Experiment-III behaviour.
        EpisodeConfig legacyNormal = new EpisodeConfig(
                "layout_01", 1L, 1L, 2.0, 0.05, 32,
                LANE_MIN, LANE_MAX, 0.0, -2.5, 2.5, 6.0, -4.0, 5.5,
                4.0, EpisodeConfig.Axis.X, EpisodeConfig.Scene.NORMAL, 0,
                0, -1, 0.0, true);
        EpisodeConfig legacyNoSheep = new EpisodeConfig(
                "layout_01", 2L, 2L, 2.0, 0.05, 32,
                LANE_MIN, LANE_MAX, 0.0, -2.5, 2.5, 6.0, -4.0, 5.5,
                4.0, EpisodeConfig.Axis.X, EpisodeConfig.Scene.NO_SHEEP, 0,
                0, -1, 0.0, true);
        assertTrue(legacyNormal.spawnSheep());
        assertFalse(legacyNoSheep.spawnSheep());
        assertTrue(legacyNoSheep.buildWall());
    }
}
