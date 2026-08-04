package com.mineocclude.server;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Server-side geometric occlusion sampling (mirrors the Python C5.2 rule). */
class GeometryUtilTest {

    // Wall along X: axis extent [-2.5, 2.5], plane at ortho (z) 2.0,
    // height [4, 7], half-thickness 0.6.
    private boolean hits(double camX, double camY, double camZ,
                         double tgtX, double tgtY, double tgtZ) {
        return GeometryUtil.segmentHitsWall(EpisodeConfig.Axis.X,
                camX, camY, camZ, tgtX, tgtY, tgtZ,
                2.0, -2.5, 2.5, 4.0, 7.0, 0.6);
    }

    @Test
    void directLineThroughWallIsBlocked() {
        assertTrue(hits(0, 5.5, -4, 0, 5.5, 8));
    }

    @Test
    void targetInFrontOfWallIsVisible() {
        assertFalse(hits(0, 5.5, -4, 0, 5.5, 0));
    }

    @Test
    void lineOverWallTopIsVisible() {
        assertFalse(hits(0, 8.5, -4, 0, 8.0, 8));
    }

    @Test
    void lineBeyondWallEndIsVisible() {
        assertFalse(hits(6.0, 5.5, -4, 6.0, 5.5, 8));
    }

    @Test
    void zAxisWallMirrorsXAxisBehavior() {
        // Wall along Z: same geometry rotated; ortho is X.
        assertTrue(GeometryUtil.segmentHitsWall(EpisodeConfig.Axis.Z,
                -4, 5.5, 0, 8, 5.5, 0, 2.0, -2.5, 2.5, 4.0, 7.0, 0.6));
        assertFalse(GeometryUtil.segmentHitsWall(EpisodeConfig.Axis.Z,
                -4, 5.5, 6.0, 8, 5.5, 6.0, 2.0, -2.5, 2.5, 4.0, 7.0, 0.6));
    }
}
