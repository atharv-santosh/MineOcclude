package com.mineocclude.server;

/**
 * Server-authoritative geometric visibility: does the straight segment from the
 * camera eye to the sheep center pass through the occluding wall volume?
 *
 * This is the geometric channel only. The final visible flag is the logical AND
 * of this and Person E's empirical magenta detector, computed downstream.
 */
public final class GeometryUtil {
    private GeometryUtil() {}

    /**
     * @param wallAxis        which world axis runs along the wall
     * @param wallOrtho       orthogonal coordinate of the wall plane
     * @param wallAxisMin/Max axis extent of the wall
     * @param wallYMin/Max    vertical extent of the wall
     * @param half            half-thickness of the wall in the ortho direction
     */
    public static boolean segmentHitsWall(
            EpisodeConfig.Axis wallAxis,
            double camX, double camY, double camZ,
            double tgtX, double tgtY, double tgtZ,
            double wallOrtho, double wallAxisMin, double wallAxisMax,
            double wallYMin, double wallYMax, double half) {

        int samples = 64;
        for (int i = 1; i < samples; i++) {
            double t = (double) i / samples;
            double px = camX + (tgtX - camX) * t;
            double py = camY + (tgtY - camY) * t;
            double pz = camZ + (tgtZ - camZ) * t;

            double ortho = (wallAxis == EpisodeConfig.Axis.X) ? pz : px;
            double axis  = (wallAxis == EpisodeConfig.Axis.X) ? px : pz;

            boolean inOrtho = Math.abs(ortho - wallOrtho) <= half;
            boolean inAxis  = axis >= wallAxisMin && axis <= wallAxisMax;
            boolean inY     = py >= wallYMin && py <= wallYMax;
            if (inOrtho && inAxis && inY) {
                return true;
            }
        }
        return false;
    }
}
