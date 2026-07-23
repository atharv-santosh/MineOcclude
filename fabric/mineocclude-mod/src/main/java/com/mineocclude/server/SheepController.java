package com.mineocclude.server;

import com.mineocclude.MineOcclude;
import net.minecraft.entity.EntityType;
import net.minecraft.entity.passive.SheepEntity;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.util.DyeColor;

import java.util.Random;

/**
 * Owns the authoritative sheep and advances it by the seeded Regime A random
 * walk on every server tick.
 *
 * The exact eta draw is exposed via {@link #lastNoiseDraw} so the logger can
 * record the process-noise realization BEFORE it is broadcast — reproducibility
 * requires the draw, not just the resulting position.
 *
 * Noise source (frozen RNG decision, C2.4): when an immutable Python-produced
 * {@link NoiseSchedule} is supplied, the server consumes its stored draws in
 * strict draw_idx order and NEVER generates its own. The seeded
 * java.util.Random path remains only as an explicitly non-scientific fallback
 * for smoke tests without a schedule; {@link #rngSource()} records which path
 * ran so the episode manifest can gate acceptance.
 */
public final class SheepController {
    public static final String RNG_IMMUTABLE_SCHEDULE = "immutable_numpy_schedule";
    public static final String RNG_FALLBACK_NONSCIENTIFIC = "java_util_random_nonscientific";

    private EpisodeConfig cfg;
    private Random rng;
    private NoiseSchedule schedule;  // null => non-scientific fallback

    private SheepEntity sheep;
    private ServerWorld world;      // kept so the sheep can be respawned if removed
    private double axisPos;         // current wall-parallel position (blocks)
    private double lastNoiseDraw;   // eta_k used to reach axisPos
    private double lastVelocity;    // realized per-tick velocity (blocks/s)

    public SheepController(EpisodeConfig cfg) {
        this(cfg, null);
    }

    public SheepController(EpisodeConfig cfg, NoiseSchedule schedule) {
        this.cfg = cfg;
        this.schedule = schedule;
        // Fallback generator, used ONLY when no immutable schedule exists.
        this.rng = new Random(cfg.seed);
        this.axisPos = cfg.startAxis();
        this.lastNoiseDraw = 0.0;
        this.lastVelocity = 0.0;
    }

    public String rngSource() {
        return schedule != null ? RNG_IMMUTABLE_SCHEDULE : RNG_FALLBACK_NONSCIENTIFIC;
    }

    public int scheduleDrawsConsumed() {
        return schedule != null ? schedule.consumed() : -1;
    }

    /** Spawn exactly one magenta NoAI/Silent/Persistent sheep at the current pose. */
    public void spawn(ServerWorld world) {
        this.world = world;
        spawnAt(axisPos);
        double[] xyz = toWorld(axisPos);
        MineOcclude.LOG.info("[MineOcclude] spawned magenta sheep at axis={} ({}, {}, {})",
                axisPos, xyz[0], xyz[1], xyz[2]);
    }

    /**
     * Reuse the existing sheep for a new episode: re-seed the motion, reset to
     * the new start, and reposition the SAME entity (no despawn/respawn) so the
     * client's entity tracker never loses it. Respawns only if it is truly gone.
     */
    public void reset(EpisodeConfig newCfg, ServerWorld world) {
        this.cfg = newCfg;
        this.schedule = null;  // a new episode must supply its own schedule
        this.rng = new Random(newCfg.seed);
        this.axisPos = newCfg.startAxis();
        this.lastNoiseDraw = 0.0;
        this.lastVelocity = 0.0;
        this.world = world;
        double[] xyz = toWorld(axisPos);
        if (sheep == null || sheep.removed || !sheep.isAlive()) {
            spawnAt(axisPos);
        } else {
            sheep.refreshPositionAndAngles(xyz[0], xyz[1], xyz[2], 0.0f, 0.0f);
            sheep.setVelocity(0, 0, 0);
            sheep.velocityDirty = true;
        }
    }

    /** Create + place a fresh sheep entity at the given axis position. */
    private void spawnAt(double axis) {
        SheepEntity s = EntityType.SHEEP.create(world);
        if (s == null) {
            throw new IllegalStateException("Failed to create SheepEntity");
        }
        s.setUuid(java.util.UUID.randomUUID());
        s.setColor(DyeColor.MAGENTA);
        s.setAiDisabled(true);   // NoAI
        s.setSilent(true);       // Silent
        s.setPersistent();       // PersistenceRequired
        s.setInvulnerable(true);
        s.setBreedingAge(0);     // adult, stable size

        double[] xyz = toWorld(axis);
        s.refreshPositionAndAngles(xyz[0], xyz[1], xyz[2], 0.0f, 0.0f);
        boolean added = world.spawnEntity(s);
        this.sheep = s;
        if (respawnCount <= 1) {
            int cx = ((int) Math.floor(xyz[0])) >> 4;
            int cz = ((int) Math.floor(xyz[2])) >> 4;
            boolean loaded = world.getChunkManager().isChunkLoaded(cx, cz);
            MineOcclude.LOG.info("[MineOcclude/dbg] spawn added={} removed={} chunk({},{}) loaded={}",
                    added, s.removed, cx, cz, loaded);
        }
    }

    /**
     * Advance one tick: x_{k+1} = x_k + v*dt + eta, eta ~ N(0, q*dt).
     * Returns nothing; read state via getters after calling.
     */
    public void step() {
        double dt = MineOcclude.DT_SECONDS;
        double eta;
        if (schedule != null) {
            // Consume exactly one stored draw per tick, in draw_idx order.
            // Exhaustion throws IllegalStateException; EpisodeManager fails
            // the episode rather than generating a replacement draw.
            eta = schedule.nextNoiseDraw();
        } else {
            double sigmaStep = Math.sqrt(cfg.processQ * dt); // std of eta
            eta = rng.nextGaussian() * sigmaStep;
        }
        double proposed = axisPos + cfg.driftV * dt + eta;
        double clamped = cfg.clampAxis(proposed);

        this.lastNoiseDraw = eta;
        this.lastVelocity = (clamped - axisPos) / dt;
        this.axisPos = clamped;

        if (world == null) return;
        double[] xyz = toWorld(axisPos);
        if (sheep == null || sheep.removed || !sheep.isAlive()) {
            // Sheep was removed (e.g. chunk churn) — respawn it at the current
            // position so it is always present and correctly placed.
            respawnCount++;
            spawnAt(axisPos);
        } else {
            sheep.refreshPositionAndAngles(xyz[0], xyz[1], xyz[2],
                    sheep.yaw, sheep.pitch); // 1.16.5: yaw/pitch are fields
            sheep.setVelocity(0, 0, 0);
            sheep.velocityDirty = true;
        }
    }

    private double[] toWorld(double axis) {
        if (cfg.wallAxis == EpisodeConfig.Axis.X) {
            return new double[]{axis, cfg.laneY, cfg.wallOrthoConst};
        } else {
            return new double[]{cfg.wallOrthoConst, cfg.laneY, axis};
        }
    }

    public void despawn() {
        if (sheep != null) {
            sheep.remove(); // 1.16.5: remove() (discard() arrives in 1.17)
            sheep = null;
        }
    }

    private int respawnCount = 0;
    public int respawnCount()        { return respawnCount; }
    public boolean entityAlive()     { return sheep != null && sheep.isAlive() && !sheep.removed; }
    public SheepEntity entity()      { return sheep; }
    public double axisPos()          { return axisPos; }
    public double lastNoiseDraw()    { return lastNoiseDraw; }
    public double lastVelocity()     { return lastVelocity; }
    public double sheepX()           { return sheep != null ? sheep.getX() : Double.NaN; }
    public double sheepY()           { return sheep != null ? sheep.getY() : Double.NaN; }
    public double sheepZ()           { return sheep != null ? sheep.getZ() : Double.NaN; }
}
