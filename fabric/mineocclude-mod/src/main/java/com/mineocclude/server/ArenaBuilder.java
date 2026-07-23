package com.mineocclude.server;

import net.minecraft.block.BlockState;
import net.minecraft.block.Blocks;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.util.math.BlockPos;

import java.util.ArrayList;
import java.util.List;

/**
 * Builds and resets a controlled arena: it first CLEARS its own footprint (so
 * whatever generated there — village, trees, hills — is wiped), lays a flat
 * stone floor, raises a 3-block-high stone occluding wall, and places four
 * non-magenta ground markers used for homography.
 *
 * The ortho span covers everything from the camera side to just past the sheep
 * lane, so the camera always stands on the arena floor and sees a clean scene.
 * Marker coordinates are returned for the layout manifest.
 */
public final class ArenaBuilder {

    public static final int WALL_HEIGHT = 3;
    private static final int CLEAR_HEIGHT = 10; // air blocks cleared above the floor

    private final EpisodeConfig cfg;
    // thing.md: superflat world (grass surface) + a 3-block-high STONE wall.
    // The floor is grass to match the surrounding world; only the wall is stone.
    private final BlockState floor = Blocks.GRASS_BLOCK.getDefaultState();
    private final BlockState wall = Blocks.STONE.getDefaultState();
    private final BlockState air = Blocks.AIR.getDefaultState();

    private final double wallOrtho;   // ortho position of the wall plane
    private final double orthoMin;    // near (camera) edge of the arena
    private final double orthoMax;    // far edge, past the sheep lane

    /** World coordinates of the four placed ground markers, in role order
     *  (near_west, near_east, far_west, far_east); filled by build(). */
    public final List<int[]> markerBlocks = new ArrayList<>();
    public static final String[] MARKER_ROLES =
            {"near_west", "near_east", "far_west", "far_east"};
    public static final String[] MARKER_COLORS =
            {"blue", "yellow", "lime", "white"};

    public ArenaBuilder(EpisodeConfig cfg, double wallOrtho, double orthoMin, double orthoMax) {
        this.cfg = cfg;
        this.wallOrtho = wallOrtho;
        this.orthoMin = orthoMin;
        this.orthoMax = orthoMax;
        computeMarkers();
    }

    /**
     * Marker positions are pure geometry, computed at construction so the
     * per-episode layout_meta.json always carries them — build() may be
     * SKIPPED when the standing arena already matches (buildArenaIfChanged),
     * and populating the list only inside build() left the first episode of
     * a session with an empty marker record while the blocks were standing.
     */
    private void computeMarkers() {
        markerBlocks.clear();
        int y = (int) Math.floor(cfg.laneY);
        int floorY = y - 1;
        int nearOrtho = (int) Math.floor(wallOrtho) - 1;   // just in front of the wall
        int farOrtho = (int) Math.floor(orthoMin) + 2;     // nearer the camera
        int axisWest = (int) Math.floor(cfg.laneMin) + 1;
        int axisEast = (int) Math.ceil(cfg.laneMax) - 1;
        int[][] markerAxes = {
                {axisWest, nearOrtho}, {axisEast, nearOrtho},
                {axisWest, farOrtho}, {axisEast, farOrtho},
        };
        for (int[] axes : markerAxes) {
            BlockPos pos = axisPos(axes[0], floorY, axes[1]);
            markerBlocks.add(new int[]{pos.getX(), pos.getY(), pos.getZ()});
        }
    }

    /** (Re)build the arena. Idempotent — safe to call on every episode reset. */
    public void build(ServerWorld world) {
        int y = (int) Math.floor(cfg.laneY);
        int floorY = y - 1;
        int aMin = (int) Math.floor(cfg.laneMin) - 2;
        int aMax = (int) Math.ceil(cfg.laneMax) + 2;
        int oMin = (int) Math.floor(orthoMin);
        int oMax = (int) Math.ceil(orthoMax);

        for (int a = aMin; a <= aMax; a++) {
            for (int o = oMin; o <= oMax; o++) {
                // Clear the column above the floor (removes any structures).
                for (int h = 1; h <= CLEAR_HEIGHT; h++) {
                    setAtAxis(world, a, floorY + h, o, air);
                }
                // Lay the floor.
                setAtAxis(world, a, floorY, o, floor);
            }
        }

        // Four non-magenta ground markers (C1.2: homography anchors that
        // stay visible near reveal and cannot be confused with the magenta
        // sheep detector). All four sit on the CAMERA side of the wall so
        // they are never occluded. Positions were computed at construction
        // (computeMarkers); build() only places the blocks.
        BlockState[] markerStates = {
                Blocks.BLUE_CONCRETE.getDefaultState(),
                Blocks.YELLOW_CONCRETE.getDefaultState(),
                Blocks.LIME_CONCRETE.getDefaultState(),
                Blocks.WHITE_CONCRETE.getDefaultState(),
        };
        for (int m = 0; m < 4; m++) {
            int[] b = markerBlocks.get(m);
            world.setBlockState(new BlockPos(b[0], b[1], b[2]), markerStates[m]);
        }

        // 3-high stone wall over the FINITE central segment only, so the sheep
        // is visible at the lane ends and hidden only behind this segment.
        // Skipped entirely for the NO_WALL positive control.
        if (cfg.buildWall()) {
            int wMin = (int) Math.floor(cfg.wallSegMin);
            int wMax = (int) Math.ceil(cfg.wallSegMax);
            for (int a = wMin; a <= wMax; a++) {
                for (int h = 0; h < WALL_HEIGHT; h++) {
                    setAtAxis(world, a, y + h, wallOrtho, wall);
                }
            }
        }

    }

    private void setAtAxis(ServerWorld world, double axis, double yy, double ortho, BlockState state) {
        world.setBlockState(axisPos(axis, yy, ortho), state);
    }

    private BlockPos axisPos(double axis, double yy, double ortho) {
        if (cfg.wallAxis == EpisodeConfig.Axis.X) {
            return new BlockPos((int) Math.floor(axis), (int) Math.floor(yy), (int) Math.floor(ortho));
        } else {
            return new BlockPos((int) Math.floor(ortho), (int) Math.floor(yy), (int) Math.floor(axis));
        }
    }
}
