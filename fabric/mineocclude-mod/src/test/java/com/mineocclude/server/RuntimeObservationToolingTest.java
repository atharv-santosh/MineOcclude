package com.mineocclude.server;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Focused tests for the C1.1 read-only runtime-observation inputs. */
public final class RuntimeObservationToolingTest {
    @BeforeEach
    @AfterEach
    void clearMarkerOverrides() {
        ArenaBuilder.ovrNearOrtho = null;
        ArenaBuilder.ovrFarOrtho = null;
        ArenaBuilder.ovrNearInset = null;
        ArenaBuilder.ovrFarInset = null;
    }

    @Test
    void markerOverrideStatusReportsDefaultAndPartialOverrideExactly() {
        assertFalse(ArenaBuilder.markerGeomOverrideEnabled());
        assertEquals("null/null/null/null", ArenaBuilder.markerGeomSignature());

        ArenaBuilder.ovrNearInset = 5;
        assertTrue(ArenaBuilder.markerGeomOverrideEnabled());
        assertEquals("null/null/5/null", ArenaBuilder.markerGeomSignature());
    }

    @Test
    void observationBoundsAndMarkersUseTheBuilderGeometry() {
        assertArrayEquals(new int[]{-10, 10, -9, 9, 3},
                ArenaBuilder.floorBoundsForObservation(-8, 8, -9, 9, 4));
        int[][] axes = ArenaBuilder.markerAxesForObservation(-8, 8, 6);
        assertArrayEquals(new int[]{-6, 4}, axes[0]);
        assertArrayEquals(new int[]{6, 4}, axes[1]);
        assertArrayEquals(new int[]{-8, 8}, axes[2]);
        assertArrayEquals(new int[]{8, 8}, axes[3]);
        assertArrayEquals(new int[]{-6, 3, 4},
                ArenaBuilder.blockCoordinatesForObservation(
                        EpisodeConfig.Axis.X, -6, 3, 4));
    }

    @Test
    void observationCoordinateProjectionFollowsZAxisLayouts() {
        assertArrayEquals(new int[]{4, 3, -6},
                ArenaBuilder.blockCoordinatesForObservation(
                        EpisodeConfig.Axis.Z, -6, 3, 4));
    }
}
