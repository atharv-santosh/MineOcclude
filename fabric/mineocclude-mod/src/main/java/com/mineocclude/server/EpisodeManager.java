package com.mineocclude.server;

import com.mineocclude.MineOcclude;
import com.mineocclude.net.EpisodeEventPacket;
import com.mineocclude.net.NetworkingIds;
import com.mineocclude.net.TickSyncPacket;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonNull;
import com.google.gson.JsonObject;
import net.fabricmc.fabric.api.networking.v1.ServerPlayNetworking;
import net.minecraft.block.Block;
import net.minecraft.block.BlockState;
import net.minecraft.block.Blocks;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.network.ServerPlayerEntity;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.text.LiteralText;
import net.minecraft.util.math.BlockPos;
import net.minecraft.util.registry.Registry;
import net.minecraft.world.GameRules;
import net.minecraft.world.World;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.List;

/**
 * Drives one episode: build arena, spawn sheep, then on every server tick step
 * the dynamics, log authoritative state, and broadcast the tick-sync packet.
 *
 * One instance is live at a time. {@code tick()} must be called from
 * ServerTickEvents.END_SERVER_TICK so the broadcast reflects post-step state.
 */
public final class EpisodeManager {
    private final MinecraftServer server;
    private final Path outputRoot;

    private EpisodeConfig cfg;
    private SheepController sheep;
    private ArenaBuilder arena;
    private ServerStateLogger logger;
    private double wallOrtho;
    private double camOrtho;

    private boolean running = false;    // episode active (warmup or capturing)
    private boolean capturing = false;  // past the warmup delay, recording ticks
    private int warmupRemaining = 0;    // ticks left in the pre-capture delay
    private long tickInEpisode = 0;
    private int visibleFrames = 0;
    private int totalTicks = 0;
    private boolean sawVisible = false;  // sheep has been visible at least once
    private int hiddenCount = 0;         // hidden frames accumulated after first visibility
    private int dbgWarm = 0;
    private String lastBuiltArenaKey = null;  // geometry key of the arena currently standing

    // C2.2/C2.4 additions: explicit lifecycle + immutable noise schedule.
    private EpisodeLifecycle lifecycle;
    private NoiseSchedule noiseSchedule;
    private String failureReason;

    // C3.6 deterministic camera program: canonical pose held by the server.
    private double camPoseX, camPoseZ, camPoseFeetY;
    private float basePoseYaw;
    // Reveal window bookkeeping (U3: record past the reveal, not only the
    // hidden phase).
    private boolean hiddenPhaseDone = false;
    private int revealCount = 0;
    /** Session-calibrated client action-pairing shift, sent in START. */
    private int pairingShift = 0;

    public void setPairingShift(int shift) { this.pairingShift = shift; }
    public int pairingShift() { return pairingShift; }

    public EpisodeManager(MinecraftServer server, Path outputRoot) {
        this.server = server;
        this.outputRoot = outputRoot;
    }

    public boolean isRunning() { return running; }

    public String lifecycleState() {
        return lifecycle == null ? "IDLE" : lifecycle.state().name();
    }

    /**
     * Arm an episode. The scene is built and the sheep spawned immediately, then
     * a warmup delay of {@code warmupTicks} runs (a countdown, no capture) before
     * recording begins. Recording lasts {@code lengthTicks} server ticks.
     */
    public boolean start(EpisodeConfig config, int lengthTicks, int warmupTicks) {
        if (running) {
            MineOcclude.LOG.warn("[MineOcclude] a previous episode was still active; ending it before starting {}",
                    config.episodeId);
            end();
        }
        ServerWorld world = server.getWorld(World.OVERWORLD);
        if (world == null) {
            MineOcclude.LOG.error("[MineOcclude] no overworld; cannot start episode");
            return false;
        }

        // C2.2: reject a repeated episode ID rather than overwriting an
        // existing completed episode.
        Path episodeDir = outputRoot.resolve("episode_" + config.episodeId);
        if (java.nio.file.Files.exists(episodeDir)) {
            MineOcclude.LOG.error("[MineOcclude] REFUSED: episode {} output already exists at {} — "
                    + "recollect under a NEW episode id; completed episodes are never overwritten",
                    config.episodeId, episodeDir);
            return false;
        }

        // C2.4: locate the immutable Python-produced noise schedule for this
        // episode, if provided. Scientific runs REQUIRE it; without it the
        // episode is marked non-scientific in the manifest.
        this.noiseSchedule = null;
        Path schedulePath = server.getRunDirectory().toPath()
                .resolve("mineocclude_schedules")
                .resolve("episode_" + config.episodeId + ".jsonl");
        if (java.nio.file.Files.isRegularFile(schedulePath)) {
            try {
                this.noiseSchedule = NoiseSchedule.load(schedulePath, config.seed);
                MineOcclude.LOG.info("[MineOcclude] loaded immutable noise schedule ({} draws) from {}",
                        noiseSchedule.size(), schedulePath);
            } catch (Exception e) {
                MineOcclude.LOG.error("[MineOcclude] REFUSED: noise schedule at {} is invalid: {}",
                        schedulePath, e.toString());
                return false; // an invalid schedule must never fall back silently
            }
        } else {
            MineOcclude.LOG.warn("[MineOcclude] no noise schedule at {} — episode {} will use the "
                    + "NON-SCIENTIFIC java.util.Random fallback (smoke tests only)",
                    schedulePath, config.episodeId);
        }

        this.lifecycle = new EpisodeLifecycle();
        this.failureReason = null;
        lifecycle.to(EpisodeLifecycle.State.RESETTING, "start command accepted");

        // Fixed, controlled lighting/weather (plan requirement + so the magenta
        // sheep is clearly lit): permanent noon, no weather.
        world.getGameRules().get(GameRules.DO_DAYLIGHT_CYCLE).set(false, server);
        world.getGameRules().get(GameRules.DO_WEATHER_CYCLE).set(false, server);
        world.getGameRules().get(GameRules.DO_MOB_SPAWNING).set(false, server);
        world.setTimeOfDay(6000L);                    // noon
        world.setWeather(1_000_000, 0, false, false); // clear, no rain/thunder

        this.cfg = config;
        this.wallOrtho = cfg.wallOrthoConst + cfg.wallOrthoOffset;
        // Camera sits on the opposite side of the wall from the sheep.
        this.camOrtho = wallOrtho - cfg.cameraDist;
        double orthoMin = camOrtho - 3;            // arena covers the camera...
        double orthoMax = cfg.wallOrthoConst + 3;  // ...through past the sheep lane
        this.arena = new ArenaBuilder(cfg, wallOrtho, orthoMin, orthoMax);
        this.tickInEpisode = 0;
        this.visibleFrames = 0;
        this.totalTicks = lengthTicks;
        this.warmupRemaining = Math.max(0, warmupTicks);
        this.dbgWarm = 0;
        this.capturing = false;
        this.hiddenPhaseDone = false;
        this.revealCount = 0;

        buildArenaIfChanged(world, orthoMin, orthoMax);
        forceLoadArena(world);
        placeCameraAtCanonicalPose(world, camOrtho);   // position the player FIRST
        // Fresh sheep AFTER the player is in place, so the entity tracker reliably
        // delivers the spawn packet to the present player (spawning before the
        // teleport left some clients never seeing the sheep).
        if (sheep != null) { sheep.despawn(); sheep = null; }
        if (cfg.spawnSheep()) { sheep = new SheepController(cfg, noiseSchedule); sheep.spawn(world); }

        // C2.3: reset must verify the target count before READY.
        if (cfg.spawnSheep() && (sheep == null || !sheep.entityAlive())) {
            lifecycle.fail("target count wrong after reset: expected 1 live sheep");
            MineOcclude.LOG.error("[MineOcclude] reset failed: sheep did not spawn alive");
            running = false;
            return false;
        }
        lifecycle.to(EpisodeLifecycle.State.READY,
                "scene built, target verified, warmup " + warmupRemaining + " ticks");

        running = true;
        MineOcclude.LOG.info("[MineOcclude] episode {} armed (layout={}, {} warmup + {} record ticks, v={}, q={}, seed={}, rng={})",
                cfg.episodeId, cfg.layoutId, warmupRemaining, lengthTicks, cfg.driftV, cfg.processQ, cfg.seed,
                sheep != null ? sheep.rngSource() : "no_target");

        if (warmupRemaining <= 0) beginCapture();
        return true;
    }

    /**
     * Build the default (layout_01) scene and position players — no recording.
     * Called on server start and on player join so a connecting client always
     * sees the arena from the canonical pose instead of empty sky.
     */
    public void preview() {
        if (running) return; // don't disturb an active episode
        ServerWorld world = server.getWorld(World.OVERWORLD);
        if (world == null) return;

        Layouts.Layout L = Layouts.get("layout_01");
        EpisodeConfig c = new EpisodeConfig("layout_01", -1L, 0L,
                1.0, 0.05, 0,
                L.laneMin, L.laneMax, 0.75 * L.laneMin,
                L.wallSegMin, L.wallSegMax,
                L.wallOrthoConst, L.wallOrthoOffset, L.cameraDist,
                L.laneY, L.wallAxis, EpisodeConfig.Scene.NORMAL, 0,
                0, -1, 0.0, false);
        this.cfg = c;
        this.wallOrtho = c.wallOrthoConst + c.wallOrthoOffset;
        this.camOrtho = wallOrtho - c.cameraDist;
        this.arena = new ArenaBuilder(c, wallOrtho, camOrtho - 3, c.wallOrthoConst + 3);

        world.getGameRules().get(GameRules.DO_DAYLIGHT_CYCLE).set(false, server);
        world.getGameRules().get(GameRules.DO_WEATHER_CYCLE).set(false, server);
        world.getGameRules().get(GameRules.DO_MOB_SPAWNING).set(false, server);
        world.setTimeOfDay(6000L);
        world.setWeather(1_000_000, 0, false, false);

        buildArenaIfChanged(world, camOrtho - 3, c.wallOrthoConst + 3);
        forceLoadArena(world);
        placeCameraAtCanonicalPose(world, camOrtho);   // position players first
        if (sheep != null) { sheep.despawn(); sheep = null; }
        sheep = new SheepController(c);
        sheep.spawn(world);
        MineOcclude.LOG.info("[MineOcclude] preview scene ready (layout_01); players positioned at canonical pose");
    }

    /** Open the logs, snap the camera to canonical pose, and start recording. */
    private void beginCapture() {
        ServerWorld world = server.getWorld(World.OVERWORLD);
        placeCameraAtCanonicalPose(world, camOrtho); // re-snap in case the operator moved during warmup
        try {
            Path episodeDir = outputRoot.resolve("episode_" + cfg.episodeId);
            this.logger = new ServerStateLogger(episodeDir);
            writeLayoutMarkers(episodeDir);
            writeResetResult(episodeDir);
        } catch (IOException e) {
            MineOcclude.LOG.error("[MineOcclude] failed to open state logger", e);
            if (lifecycle != null) lifecycle.fail("state logger open failed: " + e);
            running = false;
            return;
        }
        if (lifecycle != null) {
            lifecycle.to(EpisodeLifecycle.State.RECORDING, "capture opened");
        }
        this.tickInEpisode = 0;
        this.visibleFrames = 0;
        this.sawVisible = false;
        this.hiddenCount = 0;
        this.capturing = true;

        // Diagnostic: how many connected clients have the mod's channel? If 0,
        // the client mod is NOT loaded on the connected client (check that the
        // launcher installation's Game Directory is ~/mineocclude-client).
        int total = server.getPlayerManager().getPlayerList().size();
        int canRecv = 0;
        for (ServerPlayerEntity p : server.getPlayerManager().getPlayerList()) {
            if (ServerPlayNetworking.canSend(p, NetworkingIds.TICK_SYNC)) canRecv++;
        }
        MineOcclude.LOG.info("[MineOcclude] {}/{} connected client(s) have the MineOcclude client mod",
                canRecv, total);
        if (total > 0 && canRecv == 0) {
            MineOcclude.LOG.warn("[MineOcclude] NO connected client has the client mod — "
                    + "frames will NOT be captured. Launch the fabric-1.16.5 installation whose "
                    + "Game Directory is ~/mineocclude-client (its mods/ has mineocclude + fabric-api).");
        }

        // DIAGNOSTIC: sheep vs player distance + whether the entity is alive.
        ServerPlayerEntity p0 = firstPlayer();
        if (sheep != null && p0 != null) {
            double d = Math.sqrt(Math.pow(p0.getX() - sheep.sheepX(), 2)
                    + Math.pow(p0.getZ() - sheep.sheepZ(), 2));
            MineOcclude.LOG.info("[MineOcclude/dbg] REC start ep={} layout={} sheep=({},{}) player=({},{}) dist={} alive={}",
                    cfg.episodeId, cfg.layoutId, sheep.sheepX(), sheep.sheepZ(),
                    p0.getX(), p0.getZ(), String.format("%.1f", d), sheep.entityAlive());
        }

        broadcastEpisode(EpisodeEventPacket.Type.START);
        actionbar("§aRecording…");
        MineOcclude.LOG.info("[MineOcclude] episode {} recording started", cfg.episodeId);
    }

    /** Called once per server tick. */
    public void tick() {
        if (!running) return;

        // Warmup delay: countdown, no motion, no capture.
        if (!capturing) {
            int secs = (warmupRemaining + 19) / 20;
            actionbar("§eRecording in " + secs + "s…");
            if (sheep != null && dbgWarm < 6) {
                MineOcclude.LOG.info("[MineOcclude/dbg] warmup tick {} alive={} removed={}",
                        dbgWarm, sheep.entityAlive(),
                        sheep.entity() != null && sheep.entity().removed);
                dbgWarm++;
            }
            warmupRemaining--;
            if (warmupRemaining <= 0) beginCapture();
            return;
        }

        // C3.6 deterministic camera program: the server re-asserts the
        // canonical pose every recorded tick, so operator mouse/keyboard
        // motion cannot change the scientific framing. The scripted one-tick
        // impulse (C4.7) is a step-and-hold yaw change applied from
        // cfg.impulseTick onward — one unmistakable transition whose visual
        // effect the pixel-level validator locates.
        if (cfg.lockCamera) {
            float yaw = basePoseYaw;
            if (cfg.impulseTick >= 0 && tickInEpisode >= cfg.impulseTick) {
                yaw += (float) cfg.impulseYawDeg;
            }
            ServerWorld lockWorld = server.getWorld(World.OVERWORLD);
            for (ServerPlayerEntity p : server.getPlayerManager().getPlayerList()) {
                try {
                    p.teleport(lockWorld, camPoseX + 0.5, camPoseFeetY, camPoseZ + 0.5,
                            yaw, 0.0f);
                } catch (Exception e) {
                    MineOcclude.LOG.warn("[MineOcclude] camera lock teleport failed: {}",
                            e.toString());
                }
            }
        }

        if (sheep != null) {
            try {
                sheep.step();  // null for the NO_SHEEP control
            } catch (IllegalStateException e) {
                // Noise schedule exhausted: an episode-fatal condition. Never
                // generate a replacement draw (frozen RNG decision).
                MineOcclude.LOG.error("[MineOcclude] {} — failing episode {}", e.getMessage(),
                        cfg.episodeId);
                failureReason = e.getMessage();
                end();
                return;
            }
        }

        ServerPlayerEntity player = firstPlayer();
        double px = Double.NaN, py = Double.NaN, pz = Double.NaN, yaw = Double.NaN, pitch = Double.NaN;
        if (player != null) {
            px = player.getX();
            py = player.getEyeY();
            pz = player.getZ();
            yaw = player.yaw;   // 1.16.5: yaw/pitch are fields
            pitch = player.pitch;
        }
        boolean geometricVisible;
        if (sheep == null) {
            geometricVisible = false;               // NO_SHEEP: nothing to see
        } else if (!cfg.buildWall()) {
            // NO_WALL positive control: the occluder was never built, so there
            // is nothing to occlude the sightline — the sheep is geometrically
            // visible throughout. Testing against the phantom wall volume here
            // wrongly labeled the control mostly occluded (geometric 5/200
            // while the detector saw the sheep 200/200), which would have made
            // "visible position should be decodable" false for the control.
            geometricVisible = true;
        } else if (player != null) {
            // Test against the wall AS BUILT: ArenaBuilder floors/ceils the
            // spec to whole blocks (a block at coordinate n occupies
            // [n, n+1)), so the real occluder is wider and thicker than the
            // raw spec. Using the spec here declared "visible" while the
            // rendered wall still occluded the sheep — observed at runtime
            // as a 20-frame geometry_visible_detector_hidden quarantine run
            // and a reveal window with no visual reveal.
            boolean hit = GeometryUtil.segmentHitsWall(
                    cfg.wallAxis, px, py, pz,
                    sheep.sheepX(), sheep.sheepY() + 0.5, sheep.sheepZ(),
                    Math.floor(wallOrtho) + 0.5,
                    Math.floor(cfg.wallSegMin), Math.ceil(cfg.wallSegMax) + 1.0,
                    cfg.laneY, cfg.laneY + ArenaBuilder.WALL_HEIGHT, 0.5);
            geometricVisible = !hit;
        } else {
            geometricVisible = true;                // headless (no player): assume visible
        }
        if (geometricVisible) {
            visibleFrames++;
            sawVisible = true;
        } else if (sawVisible) {
            hiddenCount++;  // count hidden frames after the first occlusion onset
        }

        long epochNanos = System.nanoTime();
        try {
            logger.write(cfg, tickInEpisode, epochNanos, sheep, geometricVisible,
                    px, py, pz, yaw, pitch);
        } catch (IOException e) {
            MineOcclude.LOG.error("[MineOcclude] state write failed; ending episode to avoid a gap", e);
            failureReason = "state write failed: " + e;
            end();
            return;
        }

        // Broadcast the authoritative tick to every client that can receive it.
        TickSyncPacket pkt = new TickSyncPacket(cfg.episodeId, tickInEpisode, epochNanos);
        for (ServerPlayerEntity p : server.getPlayerManager().getPlayerList()) {
            if (ServerPlayNetworking.canSend(p, NetworkingIds.TICK_SYNC)) {
                ServerPlayNetworking.send(p, NetworkingIds.TICK_SYNC, pkt.write());
            }
        }

        tickInEpisode++;
        // Duration control. With revealTicks == 0 the episode stops at the
        // hidden target (legacy). With revealTicks > 0 it keeps recording
        // until the sheep is geometrically visible again and revealTicks
        // post-reveal frames are captured (U3 needs the reveal, not only the
        // hidden phase). totalTicks stays the hard safety cap.
        if (cfg.hiddenTarget > 0 && hiddenCount >= cfg.hiddenTarget) {
            if (cfg.revealTicks <= 0) {
                end();
                return;
            }
            hiddenPhaseDone = true;
        }
        if (hiddenPhaseDone && geometricVisible) {
            revealCount++;
        }
        if (hiddenPhaseDone && revealCount >= cfg.revealTicks) {
            end();
            return;
        }
        if (tickInEpisode >= totalTicks) {
            end();
        }
    }

    public void end() {
        if (!running) return;
        boolean wasCapturing = capturing;
        running = false;
        capturing = false;
        if (lifecycle != null && !lifecycle.isTerminal()) {
            if (wasCapturing) {
                lifecycle.to(EpisodeLifecycle.State.FINALIZING, "end requested");
            } else {
                lifecycle.fail("aborted during warmup");
            }
        }
        boolean closeFailed = false;
        try {
            if (logger != null) logger.close();
        } catch (IOException e) {
            MineOcclude.LOG.error("[MineOcclude] logger close failed", e);
            closeFailed = true;
        }
        int respawns = sheep != null ? sheep.respawnCount() : -1;
        String rngSource = sheep != null ? sheep.rngSource() : "no_target";
        int drawsConsumed = sheep != null ? sheep.scheduleDrawsConsumed() : -1;
        if (sheep != null) { sheep.despawn(); sheep = null; }  // fresh sheep next episode
        if (wasCapturing) {
            broadcastEpisode(EpisodeEventPacket.Type.END);
            actionbar("§7Recording finished.");
            MineOcclude.LOG.info("[MineOcclude] episode {} ended after {} ticks ({} visible, {} hidden from camera; sheep respawns={})",
                    cfg.episodeId, tickInEpisode, visibleFrames, tickInEpisode - visibleFrames, respawns);
        } else {
            MineOcclude.LOG.info("[MineOcclude] episode {} aborted during warmup", cfg.episodeId);
        }

        // C2.2/C2.5 finalization: resolve the lifecycle and persist the
        // transition log + machine-readable finalization record so a crash
        // fragment can never be mistaken for a complete episode.
        if (lifecycle != null && !lifecycle.isTerminal()) {
            if (failureReason != null) {
                lifecycle.fail(failureReason);
            } else if (closeFailed) {
                lifecycle.fail("logger close failed");
            } else {
                lifecycle.to(EpisodeLifecycle.State.COMPLETED, "finalized cleanly");
            }
        }
        if (wasCapturing && lifecycle != null) {
            try {
                Path episodeDir = outputRoot.resolve("episode_" + cfg.episodeId);
                java.nio.file.Files.write(episodeDir.resolve("lifecycle.jsonl"),
                        lifecycle.toJsonLines().getBytes(java.nio.charset.StandardCharsets.UTF_8));
                String finalization = "{\"episode_id\":" + cfg.episodeId
                        + ",\"state\":\"" + lifecycle.state() + "\""
                        + ",\"ticks\":" + tickInEpisode
                        + ",\"rng_source\":\"" + rngSource + "\""
                        + ",\"schedule_draws_consumed\":" + drawsConsumed
                        + ",\"failure_reason\":"
                        + (failureReason == null ? "null"
                           : "\"" + failureReason.replace("\"", "'") + "\"")
                        + "}";
                java.nio.file.Files.write(episodeDir.resolve("finalization.json"),
                        finalization.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            } catch (IOException e) {
                MineOcclude.LOG.error("[MineOcclude] failed to write finalization record", e);
            }
        }
    }

    /** Send an actionbar overlay message to every connected player. */
    private void actionbar(String msg) {
        for (ServerPlayerEntity p : server.getPlayerManager().getPlayerList()) {
            try {
                p.sendMessage(new LiteralText(msg), true); // true = actionbar overlay
            } catch (Exception ignored) {
                // never let a UI message abort a tick
            }
        }
    }

    private void broadcastEpisode(EpisodeEventPacket.Type type) {
        EpisodeEventPacket pkt = new EpisodeEventPacket(type, cfg.episodeId, cfg.layoutId, pairingShift);
        for (ServerPlayerEntity p : server.getPlayerManager().getPlayerList()) {
            if (ServerPlayNetworking.canSend(p, NetworkingIds.EPISODE_EVENT)) {
                ServerPlayNetworking.send(p, NetworkingIds.EPISODE_EVENT, pkt.write());
            }
        }
    }

    /**
     * Put every connected player at the canonical camera pose and set world
     * spawn there, so no manual /tp is needed and framing is identical each run.
     * Camera stands on the arena floor, opposite the sheep across the wall, and
     * looks toward the wall/sheep.
     */
    private void placeCameraAtCanonicalPose(ServerWorld world, double camOrtho) {
        if (world == null) return;
        // Center the camera on the wall segment (the scene), not the sheep start.
        double camAxis = 0.5 * (cfg.wallSegMin + cfg.wallSegMax);
        double feetY = cfg.laneY; // arena floor top surface is at laneY
        double camX, camZ;
        float yaw;
        if (cfg.wallAxis == EpisodeConfig.Axis.X) {
            camX = camAxis; camZ = camOrtho; yaw = 0.0f;   // face +Z
        } else {
            camX = camOrtho; camZ = camAxis; yaw = -90.0f; // face +X
        }
        this.camPoseX = camX;
        this.camPoseZ = camZ;
        this.camPoseFeetY = feetY;
        this.basePoseYaw = yaw;
        try {
            BlockPos spawn = new BlockPos((int) Math.floor(camX), (int) Math.floor(feetY), (int) Math.floor(camZ));
            world.setSpawnPos(spawn, yaw);
        } catch (Exception e) {
            MineOcclude.LOG.warn("[MineOcclude] setSpawnPos failed (non-fatal): {}", e.toString());
        }
        int placed = 0;
        for (ServerPlayerEntity p : server.getPlayerManager().getPlayerList()) {
            try {
                p.teleport(world, camX + 0.5, feetY, camZ + 0.5, yaw, 0.0f);
                placed++;
            } catch (Exception e) {
                MineOcclude.LOG.warn("[MineOcclude] teleport of {} failed (non-fatal): {}",
                        p.getGameProfile().getName(), e.toString());
            }
        }
        MineOcclude.LOG.info("[MineOcclude] camera pose ({}, {}, {}) yaw={} — {} player(s) placed",
                camX + 0.5, feetY, camZ + 0.5, yaw, placed);
    }

    private ServerPlayerEntity firstPlayer() {
        List<ServerPlayerEntity> players = server.getPlayerManager().getPlayerList();
        return players.isEmpty() ? null : players.get(0);
    }

    /**
     * C1.1 non-scientific observation tooling. This reads the currently standing
     * arena and connected-player camera state without moving blocks, entities,
     * markers, camera, or target and without changing reset/capture timing.
     * Receipts are create-only so an earlier observation is never overwritten.
     */
    public Path writeGeometryObservation(String receiptId) throws IOException {
        if (!receiptId.matches("[A-Za-z0-9][A-Za-z0-9_-]{0,63}")) {
            throw new IllegalArgumentException(
                    "receiptId must match [A-Za-z0-9][A-Za-z0-9_-]{0,63}");
        }
        if (cfg == null || arena == null) {
            throw new IllegalStateException("no runtime layout is currently available");
        }
        ServerWorld world = server.getWorld(World.OVERWORLD);
        if (world == null) throw new IllegalStateException("overworld is unavailable");

        JsonObject root = new JsonObject();
        root.addProperty("schema_version", "person-c-c1-runtime-geometry-observation-v0.1");
        root.addProperty("receipt_id", receiptId);
        root.addProperty("observation_only", true);
        root.addProperty("scientific_use", "forbidden");
        root.addProperty("mutates_runtime_state", false);
        root.addProperty("layout_id", cfg.layoutId);
        root.addProperty("episode_id", cfg.episodeId);
        root.addProperty("scene", cfg.scene.name());
        root.addProperty("running", running);
        root.addProperty("capturing", capturing);
        root.addProperty("lifecycle_state", lifecycleState());
        root.addProperty("warmup_ticks_remaining", warmupRemaining);

        JsonObject worldState = new JsonObject();
        worldState.addProperty("world_seed", world.getSeed());
        worldState.addProperty("difficulty", world.getDifficulty().name().toLowerCase());
        worldState.addProperty("time_of_day_ticks", world.getTimeOfDay() % 24000L);
        worldState.addProperty("raining", world.isRaining());
        worldState.addProperty("thundering", world.isThundering());
        worldState.addProperty("connected_player_count",
                server.getPlayerManager().getPlayerList().size());
        JsonObject gamerules = new JsonObject();
        gamerules.addProperty("doMobSpawning",
                world.getGameRules().get(GameRules.DO_MOB_SPAWNING).get());
        gamerules.addProperty("doWeatherCycle",
                world.getGameRules().get(GameRules.DO_WEATHER_CYCLE).get());
        gamerules.addProperty("doDaylightCycle",
                world.getGameRules().get(GameRules.DO_DAYLIGHT_CYCLE).get());
        gamerules.addProperty("mobGriefing",
                world.getGameRules().get(GameRules.DO_MOB_GRIEFING).get());
        gamerules.addProperty("randomTickSpeed",
                world.getGameRules().get(GameRules.RANDOM_TICK_SPEED).get());
        gamerules.addProperty("doFireTick",
                world.getGameRules().get(GameRules.DO_FIRE_TICK).get());
        gamerules.addProperty("keepInventory",
                world.getGameRules().get(GameRules.KEEP_INVENTORY).get());
        worldState.add("gamerules", gamerules);
        root.add("world_state", worldState);

        JsonObject override = new JsonObject();
        override.addProperty("enabled", ArenaBuilder.markerGeomOverrideEnabled());
        override.addProperty("signature", ArenaBuilder.markerGeomSignature());
        addNullableInt(override, "near_ortho", ArenaBuilder.ovrNearOrtho);
        addNullableInt(override, "far_ortho", ArenaBuilder.ovrFarOrtho);
        addNullableInt(override, "near_inset", ArenaBuilder.ovrNearInset);
        addNullableInt(override, "far_inset", ArenaBuilder.ovrFarInset);
        root.add("marker_override", override);

        JsonObject floor = new JsonObject();
        floor.addProperty("axis", cfg.wallAxis.name());
        floor.addProperty("axis_min_block_inclusive", arena.floorAxisMinBlock());
        floor.addProperty("axis_max_block_inclusive", arena.floorAxisMaxBlock());
        floor.addProperty("ortho_min_block_inclusive", arena.floorOrthoMinBlock());
        floor.addProperty("ortho_max_block_inclusive", arena.floorOrthoMaxBlock());
        floor.addProperty("y_block", arena.floorYBlock());
        floor.addProperty("default_block_id", "minecraft:grass_block");
        JsonArray floorMismatches = new JsonArray();
        int floorExpected = 0;
        int floorMatches = 0;
        Block[] markerBlocks = markerStateBlocks();
        JsonArray observedMarkerBlocks = new JsonArray();
        for (int a = arena.floorAxisMinBlock(); a <= arena.floorAxisMaxBlock(); a++) {
            for (int o = arena.floorOrthoMinBlock(); o <= arena.floorOrthoMaxBlock(); o++) {
                BlockPos pos = arena.observedBlockPos(a, arena.floorYBlock(), o);
                Block expected = Blocks.GRASS_BLOCK;
                for (int m = 0; m < arena.markerBlocks.size(); m++) {
                    int[] b = arena.markerBlocks.get(m);
                    if (b[0] == pos.getX() && b[1] == pos.getY() && b[2] == pos.getZ()) {
                        expected = markerBlocks[m];
                        break;
                    }
                }
                BlockState actual = world.getBlockState(pos);
                int observedMarkerIndex = markerStateIndex(actual.getBlock());
                if (observedMarkerIndex >= 0) {
                    JsonObject observedMarker = new JsonObject();
                    observedMarker.addProperty("role", ArenaBuilder.MARKER_ROLES[observedMarkerIndex]);
                    observedMarker.addProperty("color", ArenaBuilder.MARKER_COLORS[observedMarkerIndex]);
                    observedMarker.addProperty("actual_block_id", blockId(actual.getBlock()));
                    observedMarker.add("block_pos_xyz", blockPosition(pos));
                    observedMarker.add("top_face_centre_world_xyz",
                            xyz(pos.getX() + 0.5, pos.getY() + 1.0, pos.getZ() + 0.5));
                    observedMarkerBlocks.add(observedMarker);
                }
                floorExpected++;
                if (actual.getBlock() == expected) {
                    floorMatches++;
                } else {
                    floorMismatches.add(blockComparison(pos, expected, actual));
                }
            }
        }
        floor.addProperty("expected_position_count", floorExpected);
        floor.addProperty("matching_position_count", floorMatches);
        floor.add("mismatches", floorMismatches);
        root.add("floor", floor);
        root.addProperty("observed_marker_block_count", observedMarkerBlocks.size());
        root.add("observed_marker_blocks", observedMarkerBlocks);

        JsonObject wall = new JsonObject();
        wall.addProperty("axis", cfg.wallAxis.name());
        int wallAxisMin = (int) Math.floor(cfg.wallSegMin);
        int wallAxisMax = (int) Math.ceil(cfg.wallSegMax);
        wall.addProperty("declared_axis_min_block_inclusive", wallAxisMin);
        wall.addProperty("declared_axis_max_block_inclusive", wallAxisMax);
        wall.addProperty("scan_axis_min_block_inclusive", arena.floorAxisMinBlock());
        wall.addProperty("scan_axis_max_block_inclusive", arena.floorAxisMaxBlock());
        wall.addProperty("ortho_block", arena.wallOrthoBlock());
        wall.addProperty("y_min_block_inclusive", (int) Math.floor(cfg.laneY));
        wall.addProperty("y_max_block_inclusive",
                (int) Math.floor(cfg.laneY) + ArenaBuilder.WALL_HEIGHT - 1);
        wall.addProperty("declared_block_id",
                cfg.buildWall() ? "minecraft:stone" : "minecraft:air");
        JsonArray observedNonAir = new JsonArray();
        JsonArray wallMismatches = new JsonArray();
        int wallMatches = 0;
        int wallExpected = 0;
        for (int a = arena.floorAxisMinBlock(); a <= arena.floorAxisMaxBlock(); a++) {
            for (int h = 0; h < ArenaBuilder.WALL_HEIGHT; h++) {
                BlockPos pos = arena.observedBlockPos(
                        a, Math.floor(cfg.laneY) + h, arena.wallOrthoBlock());
                BlockState actual = world.getBlockState(pos);
                Block expectedWall = cfg.buildWall() && a >= wallAxisMin && a <= wallAxisMax
                        ? Blocks.STONE : Blocks.AIR;
                wallExpected++;
                if (!actual.isAir()) {
                    observedNonAir.add(blockComparison(pos, expectedWall, actual));
                }
                if (actual.getBlock() == expectedWall) {
                    wallMatches++;
                } else {
                    wallMismatches.add(blockComparison(pos, expectedWall, actual));
                }
            }
        }
        wall.addProperty("expected_position_count", wallExpected);
        wall.addProperty("matching_position_count", wallMatches);
        wall.add("observed_non_air_positions", observedNonAir);
        wall.add("mismatches", wallMismatches);
        root.add("wall", wall);

        JsonObject lane = new JsonObject();
        lane.addProperty("axis", cfg.wallAxis.name());
        lane.addProperty("axis_min", cfg.laneMin);
        lane.addProperty("axis_max", cfg.laneMax);
        lane.addProperty("ortho", cfg.wallOrthoConst);
        lane.addProperty("feet_y", cfg.laneY);
        lane.addProperty("start_axis", cfg.startPos);
        lane.add("world_start_xyz", worldPoint(cfg.laneMin, cfg.laneY, cfg.wallOrthoConst));
        lane.add("world_end_xyz", worldPoint(cfg.laneMax, cfg.laneY, cfg.wallOrthoConst));
        root.add("lane", lane);

        JsonArray markers = new JsonArray();
        for (int m = 0; m < arena.markerBlocks.size(); m++) {
            int[] b = arena.markerBlocks.get(m);
            BlockPos pos = new BlockPos(b[0], b[1], b[2]);
            BlockState actual = world.getBlockState(pos);
            JsonObject marker = new JsonObject();
            marker.addProperty("role", ArenaBuilder.MARKER_ROLES[m]);
            marker.addProperty("color", ArenaBuilder.MARKER_COLORS[m]);
            marker.add("block_pos_xyz", blockPosition(pos));
            marker.add("top_face_centre_world_xyz",
                    xyz(pos.getX() + 0.5, pos.getY() + 1.0, pos.getZ() + 0.5));
            marker.addProperty("expected_block_id", blockId(markerBlocks[m]));
            marker.addProperty("actual_block_id", blockId(actual.getBlock()));
            marker.addProperty("matches", actual.getBlock() == markerBlocks[m]);
            markers.add(marker);
        }
        root.add("markers", markers);

        JsonObject camera = new JsonObject();
        camera.add("canonical_feet_xyz", xyz(
                camPoseX + 0.5, camPoseFeetY, camPoseZ + 0.5));
        camera.addProperty("canonical_yaw_degrees", basePoseYaw);
        camera.addProperty("canonical_pitch_degrees", 0.0);
        camera.addProperty("fov_status", "not_server_observable");
        JsonArray players = new JsonArray();
        for (ServerPlayerEntity player : server.getPlayerManager().getPlayerList()) {
            JsonObject p = new JsonObject();
            p.addProperty("name", player.getGameProfile().getName());
            p.add("feet_xyz", xyz(player.getX(), player.getY(), player.getZ()));
            p.addProperty("eye_y", player.getEyeY());
            p.addProperty("yaw_degrees", player.yaw);
            p.addProperty("pitch_degrees", player.pitch);
            players.add(p);
        }
        camera.add("observed_players", players);
        root.add("camera", camera);

        ServerPlayerEntity player = firstPlayer();
        double cameraX = player != null ? player.getX() : camPoseX + 0.5;
        double cameraY = player != null ? player.getEyeY() : camPoseFeetY + 1.62;
        double cameraZ = player != null ? player.getZ() : camPoseZ + 0.5;
        JsonObject shadow = new JsonObject();
        shadow.addProperty("definition", "GeometryUtil.segmentHitsWall");
        shadow.addProperty("camera_source",
                player != null ? "observed_first_player" : "canonical_fallback");
        shadow.addProperty("target_centre_y", cfg.laneY + 0.5);
        JsonArray samples = new JsonArray();
        for (int a = (int) Math.floor(cfg.laneMin); a <= (int) Math.ceil(cfg.laneMax); a++) {
            double targetX = cfg.wallAxis == EpisodeConfig.Axis.X ? a : cfg.wallOrthoConst;
            double targetZ = cfg.wallAxis == EpisodeConfig.Axis.X ? cfg.wallOrthoConst : a;
            boolean occluded = cfg.buildWall() && GeometryUtil.segmentHitsWall(
                    cfg.wallAxis, cameraX, cameraY, cameraZ,
                    targetX, cfg.laneY + 0.5, targetZ,
                    Math.floor(wallOrtho) + 0.5,
                    Math.floor(cfg.wallSegMin), Math.ceil(cfg.wallSegMax) + 1.0,
                    cfg.laneY, cfg.laneY + ArenaBuilder.WALL_HEIGHT, 0.5);
            JsonObject sample = new JsonObject();
            sample.addProperty("axis_position", a);
            sample.add("target_world_xyz", xyz(targetX, cfg.laneY, targetZ));
            sample.addProperty("occluded", occluded);
            samples.add(sample);
        }
        shadow.add("integer_lane_samples", samples);
        root.add("shadow", shadow);

        Path observationRoot = outputRoot.resolveSibling("mineocclude_observations");
        Files.createDirectories(observationRoot);
        Path receipt = observationRoot.resolve(receiptId + ".json");
        byte[] bytes = new GsonBuilder().setPrettyPrinting().disableHtmlEscaping()
                .create().toJson(root).getBytes(StandardCharsets.UTF_8);
        Files.write(receipt, bytes, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
        MineOcclude.LOG.info("[MineOcclude/observation] wrote read-only geometry receipt {}", receipt);
        return receipt;
    }

    private static void addNullableInt(JsonObject object, String name, Integer value) {
        if (value == null) object.add(name, JsonNull.INSTANCE);
        else object.addProperty(name, value);
    }

    private static Block[] markerStateBlocks() {
        return new Block[]{Blocks.BLUE_CONCRETE, Blocks.YELLOW_CONCRETE,
                Blocks.LIME_CONCRETE, Blocks.WHITE_CONCRETE};
    }

    private static int markerStateIndex(Block block) {
        Block[] markers = markerStateBlocks();
        for (int i = 0; i < markers.length; i++) {
            if (block == markers[i]) return i;
        }
        return -1;
    }

    private static String blockId(Block block) {
        return Registry.BLOCK.getId(block).toString();
    }

    private static JsonObject blockComparison(BlockPos pos, Block expected, BlockState actual) {
        JsonObject object = new JsonObject();
        object.add("block_pos_xyz", blockPosition(pos));
        object.addProperty("expected_block_id", blockId(expected));
        object.addProperty("actual_block_id", blockId(actual.getBlock()));
        return object;
    }

    private JsonArray worldPoint(double axis, double y, double ortho) {
        return cfg.wallAxis == EpisodeConfig.Axis.X
                ? xyz(axis, y, ortho) : xyz(ortho, y, axis);
    }

    private static JsonArray blockPosition(BlockPos pos) {
        JsonArray array = new JsonArray();
        array.add(pos.getX());
        array.add(pos.getY());
        array.add(pos.getZ());
        return array;
    }

    private static JsonArray xyz(double x, double y, double z) {
        JsonArray array = new JsonArray();
        array.add(x);
        array.add(y);
        array.add(z);
        return array;
    }

    /**
     * C2.3: machine-readable reset result — target count, start state, RNG
     * source, and configuration identity, written before the first recorded
     * tick so downstream QA can verify the reset independently.
     */
    private void writeResetResult(Path episodeDir) throws IOException {
        int targetCount = (sheep != null && sheep.entityAlive()) ? 1 : 0;
        int expected = cfg.spawnSheep() ? 1 : 0;
        String json = "{\"episode_id\":" + cfg.episodeId
                + ",\"layout_id\":\"" + cfg.layoutId + "\""
                + ",\"scene\":\"" + cfg.scene + "\""
                + ",\"seed\":" + cfg.seed
                + ",\"v\":" + cfg.driftV
                + ",\"q\":" + cfg.processQ
                + ",\"expected_target_count\":" + expected
                + ",\"observed_target_count\":" + targetCount
                + ",\"start_axis_pos\":" + (sheep != null ? sheep.axisPos() : "null")
                + ",\"rng_source\":\""
                + (sheep != null ? sheep.rngSource() : "no_target") + "\""
                + ",\"schedule_draws\":"
                + (noiseSchedule != null ? noiseSchedule.size() : "null")
                + ",\"target_count_ok\":" + (targetCount == expected)
                + ",\"lock_camera\":" + cfg.lockCamera
                + ",\"impulse_tick\":" + cfg.impulseTick
                + ",\"impulse_yaw_deg\":" + cfg.impulseYawDeg
                + ",\"reveal_ticks\":" + cfg.revealTicks
                + "}";
        java.nio.file.Files.write(episodeDir.resolve("reset_result.json"),
                json.getBytes(java.nio.charset.StandardCharsets.UTF_8));
    }

    private void writeLayoutMarkers(Path episodeDir) throws IOException {
        StringBuilder markers = new StringBuilder("[");
        if (arena != null) {
            for (int m = 0; m < arena.markerBlocks.size(); m++) {
                int[] b = arena.markerBlocks.get(m);
                if (m > 0) markers.append(',');
                // world_* is the AUTHORITATIVE homography world point: the CENTRE
                // of the marker block's TOP FACE (x+0.5, y+1, z+0.5), which is the
                // point the marker_image_point_convention detects and which lies on
                // the y=4 sheep foot-plane. The raw BlockPos (x/y/z, the block's
                // minimum corner) is retained for provenance only. Recording the
                // corner AS the homography world point injected a uniform
                // (-0.5,-0.5) frame shift -> the constant-sign ~0.5-block
                // wall-parallel localization bias Person E measured.
                markers.append("{\"role\":\"").append(ArenaBuilder.MARKER_ROLES[m])
                        .append("\",\"color\":\"").append(ArenaBuilder.MARKER_COLORS[m])
                        .append("\",\"x\":").append(b[0])
                        .append(",\"y\":").append(b[1])
                        .append(",\"z\":").append(b[2])
                        .append(",\"world_x\":").append(b[0] + 0.5)
                        .append(",\"world_y\":").append(b[1] + 1)
                        .append(",\"world_z\":").append(b[2] + 0.5)
                        .append('}');
            }
        }
        markers.append(']');
        String json = "{\"layout_id\":\"" + cfg.layoutId + "\",\"wall_axis\":\""
                + cfg.wallAxis + "\",\"wall_ortho\":" + wallOrtho
                + ",\"scene\":\"" + cfg.scene + "\""
                + ",\"markers\":" + markers + "}";
        java.nio.file.Files.write(episodeDir.resolve("layout_meta.json"),
                json.getBytes(java.nio.charset.StandardCharsets.UTF_8));
    }

    /** Skip the rebuild when the standing arena already matches this episode's
     *  geometry (consecutive episodes on the same layout are the common case).
     *  arena.build() is ~thousands of setBlockState calls; repeating it every
     *  episode forces the CLIENT to relight/remesh those chunks every 1-2s,
     *  which was stalling the render thread for several frames at a time —
     *  observed as runs of byte-identical captured frames (see FrameCapture's
     *  stale-capture detector) that silently corrupted whole episodes. */
    private void buildArenaIfChanged(ServerWorld world, double orthoMin, double orthoMax) {
        String key = cfg.layoutId + "|" + cfg.scene + "|" + wallOrtho + "|" + orthoMin + "|" + orthoMax
                + "|" + ArenaBuilder.markerGeomSignature();
        if (key.equals(lastBuiltArenaKey)) {
            return;
        }
        arena.build(world);
        lastBuiltArenaKey = key;
    }

    /** Keep the arena chunks ENTITY-ticking. setChunkForced only *loads* the
     *  chunk (level 33). Entity-ticking is provided by the connected player, who
     *  keeps nearby chunks at ENTITY_TICKING level — no server-side ticket needed
     *  (and a headless server, having no player, cannot tick entities at all). */
    private void forceLoadArena(ServerWorld world) {
        // Keep every chunk the arena actually occupies LOADED so the entity
        // tracker reliably delivers the sheep's spawn packet to the joined
        // client. The sheep lane (laneMin..laneMax) and the wall/camera ortho
        // span can straddle more than one 16x16 chunk (e.g. a lane of -9..9
        // crosses the x=0 chunk boundary) — force-loading only chunk (0,0), as
        // this used to do, left the far chunk unloaded, so the sheep got
        // unloaded/removed ("chunk churn") whenever it drifted across the
        // boundary, regardless of how close the player stood. Ticking itself
        // still comes from the player; we only need the chunks resident.
        double orthoMin = camOrtho - 3;
        double orthoMax = cfg.wallOrthoConst + 3;
        double axisMin = cfg.laneMin;
        double axisMax = cfg.laneMax;
        double xMin, xMax, zMin, zMax;
        if (cfg.wallAxis == EpisodeConfig.Axis.X) {
            xMin = axisMin; xMax = axisMax; zMin = orthoMin; zMax = orthoMax;
        } else {
            zMin = axisMin; zMax = axisMax; xMin = orthoMin; xMax = orthoMax;
        }
        int cxMin = ((int) Math.floor(xMin)) >> 4;
        int cxMax = ((int) Math.floor(xMax)) >> 4;
        int czMin = ((int) Math.floor(zMin)) >> 4;
        int czMax = ((int) Math.floor(zMax)) >> 4;
        for (int cx = cxMin; cx <= cxMax; cx++) {
            for (int cz = czMin; cz <= czMax; cz++) {
                world.setChunkForced(cx, cz, true);
            }
        }
    }

}
