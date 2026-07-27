package com.mineocclude.server;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * The six versioned MVP arena layouts (Person C, configs/scenes/layouts.yaml).
 *
 * Layout is the grouping unit for train/test separation: probes must generalize
 * to a scene arrangement they did not train on, so the layouts deliberately vary
 * wall axis, occluder width, sheep depth, wall offset, and camera distance.
 *
 * This class is the runtime authority; configs/scenes/layouts.yaml mirrors it
 * for documentation and must be kept in sync (same ids, same numbers).
 */
public final class Layouts {
    private Layouts() {}

    public static final class Layout {
        public final String id;
        public final EpisodeConfig.Axis wallAxis;
        public final double laneMin, laneMax;   // sheep travel bounds along the axis
        public final double wallSegMin, wallSegMax; // finite occluder extent along the axis
        public final double wallOrthoConst;     // sheep depth (ortho coord)
        public final double wallOrthoOffset;    // wall ortho offset from the lane (toward camera, negative)
        public final double cameraDist;         // camera distance in front of the wall
        public final double laneY;

        Layout(String id, EpisodeConfig.Axis wallAxis,
               double laneMin, double laneMax, double wallSegMin, double wallSegMax,
               double wallOrthoConst, double wallOrthoOffset, double cameraDist, double laneY) {
            this.id = id;
            this.wallAxis = wallAxis;
            this.laneMin = laneMin;
            this.laneMax = laneMax;
            this.wallSegMin = wallSegMin;
            this.wallSegMax = wallSegMax;
            this.wallOrthoConst = wallOrthoConst;
            this.wallOrthoOffset = wallOrthoOffset;
            this.cameraDist = cameraDist;
            this.laneY = laneY;
        }
    }

    private static final Map<String, Layout> MAP = new LinkedHashMap<>();

    private static void reg(Layout l) { MAP.put(l.id, l); }

    static {
        // id, axis, laneMin, laneMax, wallSegMin, wallSegMax, sheepDepth, wallOffset, camDist, laneY
        reg(new Layout("layout_01", EpisodeConfig.Axis.X, -8, 8, -2.5, 2.5, 6.0, -4.0, 8.0, 4.0));
        reg(new Layout("layout_02", EpisodeConfig.Axis.Z, -8, 8, -2.5, 2.5, 6.0, -4.0, 8.0, 4.0));
        reg(new Layout("layout_03", EpisodeConfig.Axis.X, -9, 9, -4.0, 4.0, 6.0, -4.0, 8.0, 4.0)); // wider occluder
        reg(new Layout("layout_04", EpisodeConfig.Axis.X, -8, 8, -2.5, 2.5, 8.0, -5.0, 9.0, 4.0)); // farther sheep
        reg(new Layout("layout_05", EpisodeConfig.Axis.X, -7, 7, -2.0, 2.0, 5.0, -3.0, 7.0, 4.0)); // closer, narrow
        reg(new Layout("layout_06", EpisodeConfig.Axis.Z, -9, 9, -3.0, 3.0, 7.0, -4.0, 10.0, 4.0)); // far camera
    }

    /** Look up a layout; falls back to layout_01 for an unknown id. */
    public static Layout get(String id) {
        Layout l = MAP.get(id);
        return l != null ? l : MAP.get("layout_01");
    }

    public static boolean has(String id) { return MAP.containsKey(id); }

    public static Map<String, Layout> all() { return Collections.unmodifiableMap(MAP); }
}
