package com.mineocclude.server;

import com.mineocclude.MineOcclude;
import net.minecraft.entity.EntityType;
import net.minecraft.entity.passive.SheepEntity;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.util.DyeColor;
import net.minecraft.util.math.Box;
import net.minecraft.util.registry.Registry;

import java.util.List;
import java.util.Locale;
import java.util.Random;
import java.util.UUID;

/**
 * Owns the one authoritative experiment sheep and advances its seeded Regime A
 * random walk. A missing or altered target is episode-fatal; this controller
 * never masks a retention failure by silently respawning during an episode.
 */
public final class SheepController {
    public static final String RNG_IMMUTABLE_SCHEDULE = "immutable_numpy_schedule";
    public static final String RNG_FALLBACK_NONSCIENTIFIC = "java_util_random_nonscientific";

    private EpisodeConfig cfg;
    private Random rng;
    private NoiseSchedule schedule;
    private SheepEntity sheep;
    private ServerWorld world;
    private UUID expectedUuid;
    private double axisPos;
    private double lastNoiseDraw;
    private double lastVelocity;

    public SheepController(EpisodeConfig cfg) {
        this(cfg, null);
    }

    public SheepController(EpisodeConfig cfg, NoiseSchedule schedule) {
        this.cfg = cfg;
        this.schedule = schedule;
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

    /** Remove stale tagged targets, then spawn exactly one controlled target. */
    public void spawn(ServerWorld world) {
        this.world = world;
        int staleRemoved = removeAllTaggedTargets(world);
        if (staleRemoved > 0) {
            MineOcclude.LOG.warn("[MineOcclude] removed {} stale tagged target(s) before spawn",
                    staleRemoved);
        }
        spawnAt(axisPos);
        requireValid("spawn-to-reset");
        double[] xyz = toWorld(axisPos);
        MineOcclude.LOG.info("[MineOcclude] spawned magenta sheep at axis={} ({}, {}, {})",
                axisPos, xyz[0], xyz[1], xyz[2]);
    }

    /**
     * Reset the current target without changing its identity. A target already
     * removed by another subsystem is a refusal, never a respawn opportunity.
     */
    public void reset(EpisodeConfig newCfg, ServerWorld world) {
        requireValid("pre-reset");
        this.cfg = newCfg;
        this.schedule = null;
        this.rng = new Random(newCfg.seed);
        this.axisPos = newCfg.startAxis();
        this.lastNoiseDraw = 0.0;
        this.lastVelocity = 0.0;
        this.world = world;
        removeTaggedTargetsExcept(world, sheep);
        double[] xyz = toWorld(axisPos);
        sheep.refreshPositionAndAngles(xyz[0], xyz[1], xyz[2], 0.0f, 0.0f);
        sheep.setVelocity(0, 0, 0);
        sheep.velocityDirty = true;
        requireValid("reset-to-armed");
    }

    private void spawnAt(double axis) {
        SheepEntity created = EntityType.SHEEP.create(world);
        if (created == null) throw new IllegalStateException("Failed to create SheepEntity");

        UUID uuid = UUID.randomUUID();
        created.setUuid(uuid);
        if (!created.addScoreboardTag(TargetRetentionPolicy.EXPERIMENT_TARGET_TAG)) {
            throw new IllegalStateException("Failed to apply experiment target tag");
        }
        created.setColor(DyeColor.MAGENTA);
        created.setAiDisabled(true);
        created.setSilent(true);
        created.setPersistent();
        created.setInvulnerable(true);
        created.setBreedingAge(0);

        double[] xyz = toWorld(axis);
        created.refreshPositionAndAngles(xyz[0], xyz[1], xyz[2], 0.0f, 0.0f);
        boolean added = world.spawnEntity(created);
        if (!added) {
            throw new IllegalStateException("ServerWorld refused the experiment target entity");
        }
        this.sheep = created;
        this.expectedUuid = uuid;

        int cx = ((int) Math.floor(xyz[0])) >> 4;
        int cz = ((int) Math.floor(xyz[2])) >> 4;
        boolean loaded = world.getChunkManager().isChunkLoaded(cx, cz);
        MineOcclude.LOG.info("[MineOcclude/target] spawn added={} removed={} uuid={} tag={} chunk({},{}) loaded={}",
                added, created.removed, uuid, TargetRetentionPolicy.EXPERIMENT_TARGET_TAG,
                cx, cz, loaded);
    }

    /** Advance one authoritative motion tick after passing the retention gate. */
    public void step() {
        requireValid("armed-to-recording-pre-step");
        double dt = MineOcclude.DT_SECONDS;
        double eta;
        if (schedule != null) {
            eta = schedule.nextNoiseDraw();
        } else {
            eta = rng.nextGaussian() * Math.sqrt(cfg.processQ * dt);
        }
        double proposed = axisPos + cfg.driftV * dt + eta;
        double clamped = cfg.clampAxis(proposed);
        this.lastNoiseDraw = eta;
        this.lastVelocity = (clamped - axisPos) / dt;
        this.axisPos = clamped;

        if (world == null) throw new IllegalStateException("target world is absent");
        double[] xyz = toWorld(axisPos);
        sheep.refreshPositionAndAngles(xyz[0], xyz[1], xyz[2], sheep.yaw, sheep.pitch);
        sheep.setVelocity(0, 0, 0);
        sheep.velocityDirty = true;
        requireValid("recording-post-step");
    }

    private double[] toWorld(double axis) {
        if (cfg.wallAxis == EpisodeConfig.Axis.X) {
            return new double[]{axis, cfg.laneY, cfg.wallOrthoConst};
        }
        return new double[]{cfg.wallOrthoConst, cfg.laneY, axis};
    }

    /** Stop/finalization owns deterministic target cleanup. */
    public void despawn() {
        if (sheep != null) {
            sheep.remove();
            sheep = null;
        }
        expectedUuid = null;
        if (world != null) removeAllTaggedTargets(world);
    }

    /** Read-only hard-gate snapshot of identity, state, count, and pose. */
    public TargetRetentionPolicy.Snapshot snapshot() {
        double[] expected = toWorld(axisPos);
        int count = world == null ? 0 : taggedTargets(world).size();
        if (sheep == null) {
            return new TargetRetentionPolicy.Snapshot(true, count, false, true,
                    false, "none", "none", false, false, false, false,
                    false, false, false,
                    expected[0], expected[1], expected[2],
                    Double.NaN, Double.NaN, Double.NaN);
        }
        return new TargetRetentionPolicy.Snapshot(true, count,
                sheep.isAlive(), sheep.removed,
                TargetRetentionPolicy.isTaggedExperimentTarget(sheep),
                Registry.ENTITY_TYPE.getId(sheep.getType()).toString(),
                sheep.getColor().getName(), sheep.isAiDisabled(), sheep.isSilent(),
                sheep.isPersistent(), sheep.isInvulnerable(), !sheep.isBaby(),
                expectedUuid != null && expectedUuid.equals(sheep.getUuid()),
                sheep.getEntityWorld() == world,
                expected[0], expected[1], expected[2],
                sheep.getX(), sheep.getY(), sheep.getZ());
    }

    public List<String> validationProblems() {
        return TargetRetentionPolicy.validate(snapshot());
    }

    public void requireValid(String phase) {
        List<String> problems = validationProblems();
        if (!problems.isEmpty()) {
            throw new IllegalStateException("target retention failure at " + phase
                    + ": " + String.join("; ", problems));
        }
    }

    public String statusLine(String layoutId, long episodeId, String lifecycle) {
        TargetRetentionPolicy.Snapshot status = snapshot();
        List<String> problems = TargetRetentionPolicy.validate(status);
        return String.format(Locale.ROOT,
                "target status: valid=%s required=true count=%d uuid=%s tag=%s "
                        + "type=%s color=%s no_ai=%s silent=%s persistent=%s invulnerable=%s "
                        + "adult=%s alive=%s removed=%s xyz=%.6f/%.6f/%.6f "
                        + "expected_xyz=%.6f/%.6f/%.6f layout=%s episode=%d lifecycle=%s problems=%s",
                problems.isEmpty(), status.taggedTargetCount,
                sheep != null ? sheep.getUuidAsString() : "NONE",
                TargetRetentionPolicy.EXPERIMENT_TARGET_TAG,
                status.entityType, status.color, status.aiDisabled, status.silent,
                status.persistent, status.invulnerable, status.adult,
                status.alive, status.removed,
                status.actualX, status.actualY, status.actualZ,
                status.expectedX, status.expectedY, status.expectedZ,
                layoutId, episodeId, lifecycle,
                problems.isEmpty() ? "NONE" : String.join("|", problems));
    }

    public static TargetRetentionPolicy.Snapshot noTargetSnapshot(ServerWorld world) {
        int count = world == null ? 0 : taggedTargets(world).size();
        return new TargetRetentionPolicy.Snapshot(false, count, false, true,
                false, "none", "none", false, false, false, false,
                false, false, world != null,
                Double.NaN, Double.NaN, Double.NaN,
                Double.NaN, Double.NaN, Double.NaN);
    }

    public static int removeAllTaggedTargets(ServerWorld world) {
        return removeTaggedTargetsExcept(world, null);
    }

    private static int removeTaggedTargetsExcept(ServerWorld world, SheepEntity keep) {
        int removed = 0;
        for (SheepEntity candidate : taggedTargets(world)) {
            if (candidate != keep) {
                candidate.remove();
                removed++;
            }
        }
        return removed;
    }

    private static List<SheepEntity> taggedTargets(ServerWorld world) {
        Box arenaEnvelope = new Box(-64.0, 0.0, -64.0, 64.0, 256.0, 64.0);
        return world.getEntitiesByClass(SheepEntity.class, arenaEnvelope,
                entity -> !entity.removed
                        && TargetRetentionPolicy.isTaggedExperimentTarget(entity));
    }

    public int respawnCount()        { return 0; }
    public boolean entityAlive()     { return sheep != null && sheep.isAlive() && !sheep.removed; }
    public SheepEntity entity()      { return sheep; }
    public String targetUuid()       { return sheep != null ? sheep.getUuidAsString() : "NONE"; }
    public double axisPos()          { return axisPos; }
    public double lastNoiseDraw()    { return lastNoiseDraw; }
    public double lastVelocity()     { return lastVelocity; }
    public double sheepX()           { return sheep != null ? sheep.getX() : Double.NaN; }
    public double sheepY()           { return sheep != null ? sheep.getY() : Double.NaN; }
    public double sheepZ()           { return sheep != null ? sheep.getZ() : Double.NaN; }
}
