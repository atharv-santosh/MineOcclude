package com.mineocclude.server;

/**
 * Immutable per-episode experimental configuration for Regime A.
 *
 * Wall-parallel scalar dynamics (the MVP hidden variable is position ALONG the
 * wall). Full x/z is still logged by {@link ServerStateLogger} for later 2D work.
 *
 *   x_{k+1} = x_k + v*dt + eta_k,  eta_k ~ Normal(0, q*dt)
 *
 * Geometry produces a VISIBLE -> HIDDEN -> (VISIBLE) arc:
 *   - the sheep lane runs along {@code wallAxis} at ortho {@code wallOrthoConst}
 *   - a FINITE wall segment [wallSegMin, wallSegMax] sits at a nearer ortho and
 *     occludes only the middle of the lane
 *   - the sheep STARTS at {@code startAxis} (chosen on the visible, upstream
 *     side) and drifts across, so it is seen, then hidden behind the segment,
 *     and — with enough drift/time — revealed on the far side
 *
 * Units (locked by the plan): v [blocks/s], q [blocks^2/s], dt 0.05 s (20 Hz).
 * v and q are KNOWN experimental inputs, never re-estimated from the path.
 */
public final class EpisodeConfig {
    public final String layoutId;
    public final long episodeId;
    public final long seed;
    public final String trajectorySpecId; // null for legacy/non-campaign captures
    public final String specHash;         // null for legacy/non-campaign captures

    // Dynamics
    public final double driftV;       // blocks/s along the wall axis
    public final double processQ;     // blocks^2/s
    public final int hiddenFrames;    // planned occlusion length in ticks {2,4,8,16,24}

    // Sheep lane (clamp bounds) + explicit start
    public final double laneMin;      // min sheep position along the axis
    public final double laneMax;      // max sheep position along the axis
    public final double startPos;     // starting position along the axis (visible side)

    // Occluding wall segment (finite, central)
    public final double wallSegMin;   // wall segment axis extent (min)
    public final double wallSegMax;   // wall segment axis extent (max)

    public final double wallOrthoConst; // sheep-lane orthogonal coordinate
    public final double wallOrthoOffset;// wall ortho offset from the lane (negative = toward camera)
    public final double cameraDist;     // camera distance in front of the wall
    public final double laneY;          // ground height for the sheep
    public final Axis wallAxis;         // which world axis is "along the wall"
    public final Scene scene;           // NORMAL, NO_WALL (positive ctrl), NO_SHEEP (negative ctrl)
    /** Experiment III condition and wall material. Never null; legacy captures
     *  carry {@link WallCondition#legacyStone()} so the seam has one source of
     *  truth and no call site falls back to a hard-coded Blocks.STONE. */
    public final WallCondition condition;
    public final int hiddenTarget;      // auto-stop after this many hidden frames (0 = fixed length)
    public final int revealTicks;       // post-reveal recording window (0 = stop at hidden target)
    public final int impulseTick;       // scripted one-tick yaw impulse at this recording tick (-1 = none)
    public final double impulseYawDeg;  // impulse magnitude in degrees (step-and-hold)
    public final boolean lockCamera;    // server re-teleports the player to the canonical pose every tick

    public enum Axis { X, Z }
    public enum Scene { NORMAL, NO_WALL, NO_SHEEP }

    /**
     * Experiment III authority 7.11: wall presence and target presence are
     * INDEPENDENT axes. The single Scene enum cannot express "wall present and
     * target absent", which is the P0 ABSENT state for 13 of the 14 measured
     * conditions -- every stained-glass candidate and stone. Collapsing the two
     * axes would make the absent state remove the wall, so D(c,p,b) would
     * measure the WALL rather than the target and the whole RVE ladder would be
     * silently meaningless.
     *
     * <p>Wall presence stays with the scene/condition; target presence lives
     * here. Legacy captures derive it from the scene exactly as before, so no
     * existing behaviour changes.
     */
    public final boolean targetPresent;

    public boolean buildWall() { return scene != Scene.NO_WALL; }
    public boolean spawnSheep() { return targetPresent; }

    public EpisodeConfig(String layoutId, long episodeId, long seed,
                         double driftV, double processQ, int hiddenFrames,
                         double laneMin, double laneMax, double startPos,
                         double wallSegMin, double wallSegMax,
                         double wallOrthoConst, double wallOrthoOffset, double cameraDist,
                         double laneY, Axis wallAxis, Scene scene, int hiddenTarget,
                         int revealTicks, int impulseTick, double impulseYawDeg,
                         boolean lockCamera) {
        this(layoutId, episodeId, seed, driftV, processQ, hiddenFrames,
                laneMin, laneMax, startPos, wallSegMin, wallSegMax,
                wallOrthoConst, wallOrthoOffset, cameraDist, laneY, wallAxis,
                scene, hiddenTarget, revealTicks, impulseTick, impulseYawDeg,
                lockCamera, null, null);
    }

    public EpisodeConfig(String layoutId, long episodeId, long seed,
                         double driftV, double processQ, int hiddenFrames,
                         double laneMin, double laneMax, double startPos,
                         double wallSegMin, double wallSegMax,
                         double wallOrthoConst, double wallOrthoOffset, double cameraDist,
                         double laneY, Axis wallAxis, Scene scene, int hiddenTarget,
                         int revealTicks, int impulseTick, double impulseYawDeg,
                         boolean lockCamera, String trajectorySpecId, String specHash) {
        this(layoutId, episodeId, seed, driftV, processQ, hiddenFrames,
                laneMin, laneMax, startPos, wallSegMin, wallSegMax,
                wallOrthoConst, wallOrthoOffset, cameraDist, laneY, wallAxis,
                scene, hiddenTarget, revealTicks, impulseTick, impulseYawDeg,
                lockCamera, trajectorySpecId, specHash, WallCondition.legacyStone());
    }

    public EpisodeConfig(String layoutId, long episodeId, long seed,
                         double driftV, double processQ, int hiddenFrames,
                         double laneMin, double laneMax, double startPos,
                         double wallSegMin, double wallSegMax,
                         double wallOrthoConst, double wallOrthoOffset, double cameraDist,
                         double laneY, Axis wallAxis, Scene scene, int hiddenTarget,
                         int revealTicks, int impulseTick, double impulseYawDeg,
                         boolean lockCamera, String trajectorySpecId, String specHash,
                         WallCondition condition) {
        this(layoutId, episodeId, seed, driftV, processQ, hiddenFrames,
                laneMin, laneMax, startPos, wallSegMin, wallSegMax,
                wallOrthoConst, wallOrthoOffset, cameraDist, laneY, wallAxis,
                scene, hiddenTarget, revealTicks, impulseTick, impulseYawDeg,
                lockCamera, trajectorySpecId, specHash, condition,
                scene != Scene.NO_SHEEP);
    }

    /** The full constructor. {@code targetPresent} is the independent target
     *  axis of authority 7.11; every other overload derives it from the scene,
     *  preserving legacy behaviour exactly. */
    public EpisodeConfig(String layoutId, long episodeId, long seed,
                         double driftV, double processQ, int hiddenFrames,
                         double laneMin, double laneMax, double startPos,
                         double wallSegMin, double wallSegMax,
                         double wallOrthoConst, double wallOrthoOffset, double cameraDist,
                         double laneY, Axis wallAxis, Scene scene, int hiddenTarget,
                         int revealTicks, int impulseTick, double impulseYawDeg,
                         boolean lockCamera, String trajectorySpecId, String specHash,
                         WallCondition condition, boolean targetPresent) {
        this.condition = condition;
        this.targetPresent = targetPresent;
        this.layoutId = layoutId;
        this.episodeId = episodeId;
        this.seed = seed;
        this.trajectorySpecId = trajectorySpecId;
        this.specHash = specHash;
        this.driftV = driftV;
        this.processQ = processQ;
        this.hiddenFrames = hiddenFrames;
        this.laneMin = laneMin;
        this.laneMax = laneMax;
        this.startPos = startPos;
        this.wallSegMin = wallSegMin;
        this.wallSegMax = wallSegMax;
        this.wallOrthoConst = wallOrthoConst;
        this.wallOrthoOffset = wallOrthoOffset;
        this.cameraDist = cameraDist;
        this.laneY = laneY;
        this.wallAxis = wallAxis;
        this.scene = scene;
        this.hiddenTarget = hiddenTarget;
        this.revealTicks = revealTicks;
        this.impulseTick = impulseTick;
        this.impulseYawDeg = impulseYawDeg;
        this.lockCamera = lockCamera;
    }

    /** Clamp a wall-axis position to the lane bounds. */
    public double clampAxis(double a) {
        if (a < laneMin) return laneMin;
        if (a > laneMax) return laneMax;
        return a;
    }

    /** Explicit start position along the wall axis (visible, upstream side). */
    public double startAxis() {
        return startPos;
    }
}
