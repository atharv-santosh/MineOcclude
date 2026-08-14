package com.mineocclude.server;

import com.mineocclude.MineOcclude;
import com.mojang.brigadier.arguments.DoubleArgumentType;
import com.mojang.brigadier.arguments.IntegerArgumentType;
import com.mojang.brigadier.arguments.LongArgumentType;
import com.mojang.brigadier.arguments.StringArgumentType;
import net.fabricmc.api.DedicatedServerModInitializer;
import net.fabricmc.fabric.api.command.v1.CommandRegistrationCallback;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.fabricmc.fabric.api.networking.v1.ServerPlayConnectionEvents;
import net.minecraft.server.command.CommandManager;
import net.minecraft.server.command.ServerCommandSource;
import net.minecraft.text.LiteralText;

import java.nio.file.Path;

/**
 * Dedicated-server entrypoint. Owns the tick loop and the operator commands
 * that drive episodes. RCON may still be used as a manual diagnostic/reset
 * fallback, but the 20 Hz motion + tick broadcast run here, on ServerTickEvents.
 *
 * Commands (op level 2):
 *   /mineocclude start <layoutId> <episodeId> <seed> <v> <q> <ticks>
 *   /mineocclude startspec <layoutId> <episodeId> <seed> <q> <ticks> <startPos> <specId> <specHash>
 *   /mineocclude markergeomstatus
 *   /mineocclude observegeometry <receiptId>
 *   /mineocclude targetstatus
 *   /mineocclude stop
 *   /mineocclude status
 */
public final class MineOccludeServer implements DedicatedServerModInitializer {
    /** Pre-capture delay applied on the next start (default 3 s at 20 Hz).
     *  Change it live with {@code /mineocclude warmup <ticks>}. */
    private static int warmupTicks = 60;
    /** Scene mode for the next start: normal | nowall | nosheep. */
    private static EpisodeConfig.Scene sceneMode = EpisodeConfig.Scene.NORMAL;
    /** Hidden-frame target for the next start (0 = record the full tick count). */
    private static int hiddenTarget = 0;
    /** Post-reveal recording window for the next start (0 = stop at hidden target). */
    private static int revealTicks = 0;
    /** Scripted one-tick yaw impulse: recording tick (-1 = none) and degrees. */
    private static int impulseTick = -1;
    private static double impulseYawDeg = 15.0;
    /** Server-side camera lock: re-teleport the player to the canonical pose every tick. */
    private static boolean lockCamera = true;

    private static EpisodeManager manager;

    @Override
    public void onInitializeServer() {
        ServerLifecycleEvents.SERVER_STARTED.register(server -> {
            Path outputRoot = server.getRunDirectory().toPath().resolve("mineocclude_out");
            manager = new EpisodeManager(server, outputRoot);
            manager.preview(); // build the scene + set world spawn before anyone joins
            MineOcclude.LOG.info("[MineOcclude] server ready; output -> {}", outputRoot);
        });

        ServerTickEvents.END_SERVER_TICK.register(server -> {
            if (manager != null) manager.tick();
        });

        // Close any in-progress episode on shutdown so its logs are finalized.
        ServerLifecycleEvents.SERVER_STOPPING.register(server -> {
            if (manager != null && manager.isRunning()) manager.end();
        });

        // Give every joining player operator rights (cheats enabled) so they can
        // run commands and the mod can teleport/manage them freely.
        ServerPlayConnectionEvents.JOIN.register((handler, sender, server) -> {
            server.getPlayerManager().addToOperators(handler.player.getGameProfile());
            MineOcclude.LOG.info("[MineOcclude] {} opped (cheats enabled)",
                    handler.player.getGameProfile().getName());
            // Position the joining player at the scene so they never see empty sky.
            if (manager != null) manager.preview();
        });

        CommandRegistrationCallback.EVENT.register((dispatcher, dedicated) ->
            dispatcher.register(CommandManager.literal("mineocclude")
                .requires(src -> src.hasPermissionLevel(2))
                .then(CommandManager.literal("start")
                    .then(CommandManager.argument("layoutId", StringArgumentType.word())
                    .then(CommandManager.argument("episodeId", LongArgumentType.longArg(0))
                    .then(CommandManager.argument("seed", LongArgumentType.longArg())
                    .then(CommandManager.argument("v", DoubleArgumentType.doubleArg())
                    .then(CommandManager.argument("q", DoubleArgumentType.doubleArg(0))
                    .then(CommandManager.argument("ticks", IntegerArgumentType.integer(1))
                        .executes(ctx -> startCmd(ctx.getSource(),
                                StringArgumentType.getString(ctx, "layoutId"),
                                LongArgumentType.getLong(ctx, "episodeId"),
                                LongArgumentType.getLong(ctx, "seed"),
                                DoubleArgumentType.getDouble(ctx, "v"),
                                DoubleArgumentType.getDouble(ctx, "q"),
                                IntegerArgumentType.getInteger(ctx, "ticks"),
                                warmupTicks)))))))))
                .then(CommandManager.literal("startspec")
                    .then(CommandManager.argument("layoutId", StringArgumentType.word())
                    .then(CommandManager.argument("episodeId", LongArgumentType.longArg(0))
                    .then(CommandManager.argument("seed", LongArgumentType.longArg())
                    .then(CommandManager.argument("q", DoubleArgumentType.doubleArg(0))
                    .then(CommandManager.argument("ticks", IntegerArgumentType.integer(1))
                    .then(CommandManager.argument("startPos", DoubleArgumentType.doubleArg())
                    .then(CommandManager.argument("specId", StringArgumentType.word())
                    .then(CommandManager.argument("specHash", StringArgumentType.word())
                        .executes(ctx -> startSpecCmd(ctx.getSource(),
                                StringArgumentType.getString(ctx, "layoutId"),
                                LongArgumentType.getLong(ctx, "episodeId"),
                                LongArgumentType.getLong(ctx, "seed"),
                                DoubleArgumentType.getDouble(ctx, "q"),
                                IntegerArgumentType.getInteger(ctx, "ticks"),
                                DoubleArgumentType.getDouble(ctx, "startPos"),
                                StringArgumentType.getString(ctx, "specId"),
                                StringArgumentType.getString(ctx, "specHash"),
                                warmupTicks)))))))))))
                .then(CommandManager.literal("markergeom")
                    .then(CommandManager.argument("nearOrtho", IntegerArgumentType.integer())
                    .then(CommandManager.argument("farOrtho", IntegerArgumentType.integer())
                    .then(CommandManager.argument("nearInset", IntegerArgumentType.integer())
                    .then(CommandManager.argument("farInset", IntegerArgumentType.integer())
                        .executes(ctx -> {
                            ArenaBuilder.ovrNearOrtho = IntegerArgumentType.getInteger(ctx, "nearOrtho");
                            ArenaBuilder.ovrFarOrtho = IntegerArgumentType.getInteger(ctx, "farOrtho");
                            ArenaBuilder.ovrNearInset = IntegerArgumentType.getInteger(ctx, "nearInset");
                            ArenaBuilder.ovrFarInset = IntegerArgumentType.getInteger(ctx, "farInset");
                            ctx.getSource().sendFeedback(new LiteralText(
                                    "markergeom override: nearOrtho=" + ArenaBuilder.ovrNearOrtho
                                    + " farOrtho=" + ArenaBuilder.ovrFarOrtho
                                    + " nearInset=" + ArenaBuilder.ovrNearInset
                                    + " farInset=" + ArenaBuilder.ovrFarInset), true);
                            return 1;
                        }))))))
                .then(CommandManager.literal("markergeomreset")
                    .executes(ctx -> {
                        ArenaBuilder.ovrNearOrtho = null; ArenaBuilder.ovrFarOrtho = null;
                        ArenaBuilder.ovrNearInset = null; ArenaBuilder.ovrFarInset = null;
                        ctx.getSource().sendFeedback(new LiteralText("markergeom override cleared"), true);
                        return 1;
                    }))
                .then(CommandManager.literal("markergeomstatus")
                    .executes(ctx -> markerGeomStatusCmd(ctx.getSource())))
                .then(CommandManager.literal("observegeometry")
                    .then(CommandManager.argument("receiptId", StringArgumentType.word())
                        .executes(ctx -> observeGeometryCmd(ctx.getSource(),
                                StringArgumentType.getString(ctx, "receiptId")))))
                .then(CommandManager.literal("targetstatus")
                    .executes(ctx -> targetStatusCmd(ctx.getSource())))
                .then(CommandManager.literal("warmup")
                    .then(CommandManager.argument("ticks", IntegerArgumentType.integer(0))
                        .executes(ctx -> {
                            warmupTicks = IntegerArgumentType.getInteger(ctx, "ticks");
                            ctx.getSource().sendFeedback(new LiteralText(
                                    "Warmup delay set to " + warmupTicks + " ticks ("
                                    + String.format("%.1f", warmupTicks / 20.0) + "s)"), true);
                            return 1;
                        })))
                .then(CommandManager.literal("mode")
                    .then(CommandManager.argument("scene", StringArgumentType.word())
                        .executes(ctx -> {
                            String s = StringArgumentType.getString(ctx, "scene").toLowerCase();
                            switch (s) {
                                case "normal":  sceneMode = EpisodeConfig.Scene.NORMAL; break;
                                case "nowall":  sceneMode = EpisodeConfig.Scene.NO_WALL; break;
                                case "nosheep": sceneMode = EpisodeConfig.Scene.NO_SHEEP; break;
                                default:
                                    ctx.getSource().sendError(new LiteralText(
                                            "scene must be normal | nowall | nosheep"));
                                    return 0;
                            }
                            ctx.getSource().sendFeedback(new LiteralText("Scene mode = " + s), true);
                            return 1;
                        })))
                .then(CommandManager.literal("duration")
                    .then(CommandManager.argument("hiddenFrames", IntegerArgumentType.integer(0))
                        .executes(ctx -> {
                            hiddenTarget = IntegerArgumentType.getInteger(ctx, "hiddenFrames");
                            ctx.getSource().sendFeedback(new LiteralText(hiddenTarget == 0
                                    ? "Duration = full tick count (no hidden-frame auto-stop)"
                                    : "Duration = auto-stop after " + hiddenTarget + " hidden frames"), true);
                            return 1;
                        })))
                .then(CommandManager.literal("reveal")
                    .then(CommandManager.argument("ticks", IntegerArgumentType.integer(0))
                        .executes(ctx -> {
                            revealTicks = IntegerArgumentType.getInteger(ctx, "ticks");
                            ctx.getSource().sendFeedback(new LiteralText(
                                    "Post-reveal window = " + revealTicks + " ticks"), true);
                            return 1;
                        })))
                .then(CommandManager.literal("impulse")
                    .then(CommandManager.argument("tick", IntegerArgumentType.integer(-1))
                    .then(CommandManager.argument("deg", DoubleArgumentType.doubleArg(-90, 90))
                        .executes(ctx -> {
                            impulseTick = IntegerArgumentType.getInteger(ctx, "tick");
                            impulseYawDeg = DoubleArgumentType.getDouble(ctx, "deg");
                            ctx.getSource().sendFeedback(new LiteralText(impulseTick < 0
                                    ? "Scripted impulse disabled"
                                    : "Scripted impulse: +" + impulseYawDeg + " deg yaw at recording tick "
                                      + impulseTick), true);
                            return 1;
                        }))))
                .then(CommandManager.literal("pairshift")
                    .then(CommandManager.argument("shift", IntegerArgumentType.integer(-2, 2))
                        .executes(ctx -> {
                            int shift = IntegerArgumentType.getInteger(ctx, "shift");
                            if (manager != null) manager.setPairingShift(shift);
                            ctx.getSource().sendFeedback(new LiteralText(
                                    "Action pairing shift = " + shift), true);
                            return 1;
                        })))
                .then(CommandManager.literal("lockcam")
                    .then(CommandManager.argument("on", StringArgumentType.word())
                        .executes(ctx -> {
                            lockCamera = "on".equalsIgnoreCase(StringArgumentType.getString(ctx, "on"));
                            ctx.getSource().sendFeedback(new LiteralText(
                                    "Camera lock " + (lockCamera ? "ON" : "OFF")), true);
                            return 1;
                        })))
                .then(CommandManager.literal("stop")
                    .executes(ctx -> stopCmd(ctx.getSource())))
                .then(CommandManager.literal("status")
                    .executes(ctx -> statusCmd(ctx.getSource())))
            )
        );
    }

    private static int startCmd(ServerCommandSource src, String layoutId, long episodeId,
                                long seed, double v, double q, int ticks, int warmup) {
        MineOcclude.LOG.info("[MineOcclude] /start requested: layout={} ep={} seed={} v={} q={} ticks={} warmup={}",
                layoutId, episodeId, seed, v, q, ticks, warmup);
        if (manager == null) {
            src.sendError(new LiteralText("MineOcclude not ready (server not started yet)"));
            return 0;
        }
        if (!Layouts.has(layoutId)) {
            src.sendError(new LiteralText("Unknown layout '" + layoutId + "'. Known: "
                    + String.join(", ", Layouts.all().keySet())));
            return 0;
        }
        try {
            Layouts.Layout L = Layouts.get(layoutId);
            // Start on the upstream (visible) side so a positive drift carries the
            // sheep across: visible -> hidden behind the wall -> visible on reveal.
            double startPos = pickVisibleStart(L, v);
            EpisodeConfig cfg = new EpisodeConfig(
                    layoutId, episodeId, seed,
                    v, q, ticks,
                    L.laneMin, L.laneMax, startPos,
                    L.wallSegMin, L.wallSegMax,
                    L.wallOrthoConst, L.wallOrthoOffset, L.cameraDist,
                    L.laneY, L.wallAxis, sceneMode, hiddenTarget,
                    revealTicks, impulseTick, impulseYawDeg, lockCamera);
            if (!manager.start(cfg, ticks, warmup)) {
                src.sendError(new LiteralText("start REFUSED for episode " + episodeId
                        + " — see the server log for the reason (duplicate id, bad schedule, or reset failure)"));
                return 0;
            }
            src.sendFeedback(new LiteralText("Armed episode " + episodeId + " (" + layoutId
                    + ", scene " + sceneMode + ", warmup " + warmup + "t, record " + ticks
                    + "t, hiddenTarget " + hiddenTarget + ")"), true);
            return 1;
        } catch (Exception e) {
            MineOcclude.LOG.error("[MineOcclude] start failed", e);
            src.sendError(new LiteralText("start failed: " + e));
            return 0;
        }
    }

    /** Start one P1-locked campaign spec using explicit start and speed authority. */
    private static int startSpecCmd(ServerCommandSource src, String layoutId, long episodeId,
                                    long seed, double q, int ticks, double startPos,
                                    String specId, String specHash, int warmup) {
        MineOcclude.LOG.info("[MineOcclude/P2] /startspec requested: spec={} hash={} layout={} "
                        + "ep={} seed={} q={} ticks={} start={} warmup={}",
                specId, specHash, layoutId, episodeId, seed, q, ticks, startPos, warmup);
        if (manager == null) {
            src.sendError(new LiteralText("MineOcclude not ready"));
            return 0;
        }
        if (!Layouts.has(layoutId)) {
            src.sendError(new LiteralText("Unknown layout '" + layoutId + "'"));
            return 0;
        }
        if (sceneMode != EpisodeConfig.Scene.NORMAL) {
            src.sendError(new LiteralText("startspec requires scene mode normal"));
            return 0;
        }
        Layouts.Layout layout = Layouts.get(layoutId);
        if (!Double.isFinite(startPos)
                || startPos < layout.laneMin || startPos > layout.laneMax) {
            src.sendError(new LiteralText("startspec start position outside layout lane"));
            return 0;
        }
        try {
            Path schedulePath = src.getMinecraftServer().getRunDirectory().toPath()
                    .resolve("mineocclude_motion_schedules")
                    .resolve("episode_" + episodeId + ".json");
            MotionSchedule schedule = MotionSchedule.load(
                    schedulePath, specId, specHash, ticks);
            EpisodeConfig cfg = new EpisodeConfig(
                    layoutId, episodeId, seed,
                    schedule.velocityAt(0), q, ticks,
                    layout.laneMin, layout.laneMax, startPos,
                    layout.wallSegMin, layout.wallSegMax,
                    layout.wallOrthoConst, layout.wallOrthoOffset, layout.cameraDist,
                    layout.laneY, layout.wallAxis, EpisodeConfig.Scene.NORMAL, 0,
                    0, -1, 0.0, true, specId, specHash);
            if (!manager.start(cfg, ticks, warmup, schedule)) {
                src.sendError(new LiteralText("startspec REFUSED for episode " + episodeId));
                return 0;
            }
            src.sendFeedback(new LiteralText("Armed locked spec " + specId
                    + " as episode " + episodeId), true);
            return 1;
        } catch (Exception error) {
            MineOcclude.LOG.error("[MineOcclude/P2] startspec failed", error);
            src.sendError(new LiteralText("startspec failed: " + error));
            return 0;
        }
    }

    /**
     * The naive "0.75 * laneMin/laneMax" start position assumed the occluded
     * region is exactly the wall's own axis span, but {@link GeometryUtil#segmentHitsWall}
     * (correctly) accounts for perspective: the camera-to-sheep sightline can
     * cross the wall volume even when the sheep's axis position is well outside
     * [wallSegMin, wallSegMax], widening the true occlusion shadow at the
     * sheep's (farther) depth. For wide-occluder layouts this put the sheep
     * BEHIND the wall at tick 0 — the episode then never has a visible->hidden
     * transition, so hiddenCount never starts counting, the hidden-frame
     * auto-stop never fires, and the episode silently runs the full max-ticks
     * safety cap instead of the intended short window. Verify the candidate
     * start position against the same geometry check tick() uses, at the same
     * canonical camera pose, and fall back to the lane's extreme edge if the
     * default candidate is still occluded.
     */
    private static double pickVisibleStart(Layouts.Layout L, double v) {
        double wallOrtho = L.wallOrthoConst + L.wallOrthoOffset;
        double camOrtho = wallOrtho - L.cameraDist;
        double camAxis = 0.5 * (L.wallSegMin + L.wallSegMax);
        double camEyeY = L.laneY + 1.62; // matches ServerPlayerEntity.getEyeY() at feet=laneY
        double sheepY = L.laneY + 0.5;

        double[] candidates = v >= 0
                ? new double[]{0.75 * L.laneMin, L.laneMin}
                : new double[]{0.75 * L.laneMax, L.laneMax};
        for (double candidate : candidates) {
            // +0.5: placeCameraAtCanonicalPose teleports the player to the
            // block CENTER (camX/camZ + 0.5), not the raw block coordinate —
            // that half-block matters here, since this check is right at the
            // occlusion-shadow boundary (missing it is exactly how the first
            // version of this fix still failed).
            double camX = (L.wallAxis == EpisodeConfig.Axis.X) ? camAxis + 0.5 : camOrtho + 0.5;
            double camZ = (L.wallAxis == EpisodeConfig.Axis.X) ? camOrtho + 0.5 : camAxis + 0.5;
            double sheepX = (L.wallAxis == EpisodeConfig.Axis.X) ? candidate : L.wallOrthoConst;
            double sheepZ = (L.wallAxis == EpisodeConfig.Axis.X) ? L.wallOrthoConst : candidate;
            boolean hidden = GeometryUtil.segmentHitsWall(L.wallAxis, camX, camEyeY, camZ,
                    sheepX, sheepY, sheepZ,
                    Math.floor(wallOrtho) + 0.5,
                    Math.floor(L.wallSegMin), Math.ceil(L.wallSegMax) + 1.0,
                    L.laneY, L.laneY + ArenaBuilder.WALL_HEIGHT, 0.5);
            if (!hidden) return candidate;
        }
        MineOcclude.LOG.error("[MineOcclude] no candidate start position is geometrically visible "
                + "for layout {} (v={}) — using the lane extreme anyway; this episode will start hidden",
                L.id, v);
        return candidates[candidates.length - 1];
    }

    private static int stopCmd(ServerCommandSource src) {
        if (manager != null && manager.isRunning()) {
            manager.end();
            src.sendFeedback(new LiteralText("Episode stopped"), true);
        } else {
            src.sendFeedback(new LiteralText("No episode running"), false);
        }
        return 1;
    }

    private static int markerGeomStatusCmd(ServerCommandSource src) {
        src.sendFeedback(new LiteralText("markergeom status: enabled="
                + ArenaBuilder.markerGeomOverrideEnabled()
                + " nearOrtho=" + ArenaBuilder.ovrNearOrtho
                + " farOrtho=" + ArenaBuilder.ovrFarOrtho
                + " nearInset=" + ArenaBuilder.ovrNearInset
                + " farInset=" + ArenaBuilder.ovrFarInset
                + " signature=" + ArenaBuilder.markerGeomSignature()), false);
        return 1;
    }

    private static int observeGeometryCmd(ServerCommandSource src, String receiptId) {
        if (manager == null) {
            src.sendError(new LiteralText("MineOcclude not ready (server not started yet)"));
            return 0;
        }
        try {
            Path receipt = manager.writeGeometryObservation(receiptId);
            src.sendFeedback(new LiteralText("Wrote observation-only geometry receipt: "
                    + receipt), false);
            return 1;
        } catch (Exception e) {
            MineOcclude.LOG.error("[MineOcclude/observation] geometry receipt failed", e);
            src.sendError(new LiteralText("observegeometry failed: " + e.getMessage()));
            return 0;
        }
    }

    private static int statusCmd(ServerCommandSource src) {
        boolean running = manager != null && manager.isRunning();
        String state = manager != null ? manager.lifecycleState() : "IDLE";
        src.sendFeedback(new LiteralText("MineOcclude running=" + running
                + " lifecycle=" + state), false);
        return 1;
    }

    private static int targetStatusCmd(ServerCommandSource src) {
        if (manager == null) {
            src.sendError(new LiteralText("target status: valid=false problems=server not ready"));
            return 0;
        }
        String line = manager.targetStatusLine();
        MineOcclude.LOG.info("[MineOcclude/target] {}", line);
        if (!manager.targetStatusValid()) {
            src.sendError(new LiteralText(line));
            return 0;
        }
        src.sendFeedback(new LiteralText(line), false);
        return 1;
    }
}
