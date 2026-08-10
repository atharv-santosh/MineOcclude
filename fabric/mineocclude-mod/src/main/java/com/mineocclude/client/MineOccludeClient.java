package com.mineocclude.client;

import com.mineocclude.MineOcclude;
import com.mineocclude.net.EpisodeEventPacket;
import com.mineocclude.net.NetworkingIds;
import com.mineocclude.net.TickSyncPacket;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.networking.v1.ClientPlayNetworking;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gui.screen.ConnectScreen;
import net.minecraft.client.gui.screen.TitleScreen;

import java.io.IOException;
import java.nio.file.Path;
import java.util.concurrent.ConcurrentLinkedQueue;

/**
 * Client entrypoint. Receives the authoritative tick packet and, at CLIENT
 * TICK time, captures one frame (the last fully completed render — F2
 * screenshot semantics) plus one complete action record, bound to
 * (episode_id, server_tick, render_frame_idx, action_idx).
 *
 * Capture policy: exactly one pending server tick is consumed per client
 * tick. If rendering stalls (occluded window) the stale-frame detector
 * fires and Python QA rejects the episode; if ticks back up, cardinality QA
 * rejects it — either way the trajectory is recollected, never repaired.
 * Action pairing uses the session-calibrated pairingShift from the START
 * packet (see EpisodeEventPacket). Any 16:9 window works; Python
 * normalizes the preserved source frames to canonical 640x360.
 */
public final class MineOccludeClient implements ClientModInitializer {

    private static final class PendingTick {
        final long episodeId, serverTick, serverEpochNanos, recvNanos;
        PendingTick(long e, long t, long s, long r) {
            episodeId = e; serverTick = t; serverEpochNanos = s; recvNanos = r;
        }
    }

    private final ConcurrentLinkedQueue<PendingTick> pending = new ConcurrentLinkedQueue<>();
    private final FrameCapture frameCapture = new FrameCapture();
    private final ActionSampler actionSampler = new ActionSampler();

    private ClientLogger logger;
    private Path episodeDir;
    private long currentEpisodeId = -1;
    private long renderFrameIdx = 0;
    /** Session-calibrated pairing shift from the START packet: the sample
     *  taken at capture k is written as action index k - 1 + pairingShift. */
    private int pairingShift = 0;
    /** Next action index to write (guards gaps/duplicates in pairing). */
    private long nextActionIdx = 0;

    @Override
    public void onInitializeClient() {
        ClientPlayNetworking.registerGlobalReceiver(NetworkingIds.TICK_SYNC,
            (client, handler, buf, responseSender) -> {
                try {
                    TickSyncPacket pkt = TickSyncPacket.read(buf);
                    long recv = System.nanoTime();
                    pending.add(new PendingTick(pkt.episodeId, pkt.serverTick, pkt.serverEpochNanos, recv));
                } catch (Throwable t) {
                    MineOcclude.LOG.error("[MineOcclude/client] tick_sync read failed (non-fatal)", t);
                }
            });

        ClientPlayNetworking.registerGlobalReceiver(NetworkingIds.EPISODE_EVENT,
            (client, handler, buf, responseSender) -> {
                try {
                    EpisodeEventPacket pkt = EpisodeEventPacket.read(buf);
                    client.execute(() -> {
                        try {
                            onEpisodeEvent(client, pkt);
                        } catch (Throwable t) {
                            MineOcclude.LOG.error("[MineOcclude/client] episode event failed (non-fatal)", t);
                        }
                    });
                } catch (Throwable t) {
                    MineOcclude.LOG.error("[MineOcclude/client] episode_event read failed (non-fatal)", t);
                }
            });

        // Capture at CLIENT TICK time, not during HUD rendering. A mid-frame
        // glGetTexImage on Apple-silicon tiled GPUs returns only the portions
        // of the render pass that happen to be resolved — terrain appeared
        // but entities (the magenta sheep!) were consistently missing from
        // every live capture, while vanilla F2 screenshots (same read, taken
        // BETWEEN frames) contained them. Client tick runs on the render
        // thread between frames, so the framebuffer holds the last fully
        // completed frame — exactly the F2 semantics. One pending server
        // tick is consumed per client tick, preserving 1:1 cardinality.
        ClientTickEvents.END_CLIENT_TICK.register(client -> {
            pinFov(client);
            tryAutoConnect(client);
            onFrame(client);
        });
    }

    private boolean fovPinned = false;

    /** Force FOV to Normal (70) so a stray/0 FOV can't blank the view.
     *  In 1.16.5 the fov field is in DEGREES: 70.0 == Normal, 0.0 == void. */
    private void pinFov(MinecraftClient client) {
        if (fovPinned || client.options == null) return;
        fovPinned = true;
        try {
            client.options.fov = 70.0;            // Normal
            client.options.fovEffectScale = 0.0f; // no FOV change from speed/sprint
            MineOcclude.LOG.info("[MineOcclude/client] FOV pinned to 70 (Normal)");
        } catch (Throwable t) {
            MineOcclude.LOG.error("[MineOcclude/client] pinFov failed (non-fatal)", t);
        }
    }

    private boolean autoConnectDone = false;
    private long autoConnectAfterNanos = -1L;

    private void tryAutoConnect(MinecraftClient client) {
        if (autoConnectDone) return;
        String target = System.getenv("MINEOCCLUDE_AUTOCONNECT");
        if (target == null || target.isEmpty()) return;
        if (client.world != null) { autoConnectDone = true; return; }
        if (!(client.currentScreen instanceof TitleScreen)) return;
        // Linux software rendering can expose TitleScreen several seconds
        // before vanilla finishes baking block models. Opening ConnectScreen
        // in that interval races the resource reload and Indigo receives null
        // baked models when the first world chunks arrive. The accepted
        // Windows launch is fast enough not to hit the race. Permit the Linux
        // launcher to request a bounded pre-connect delay; this changes only
        // session orchestration before any episode starts.
        if (autoConnectAfterNanos < 0L) {
            long delayMs = 0L;
            String configuredDelay = System.getenv("MINEOCCLUDE_AUTOCONNECT_DELAY_MS");
            if (configuredDelay != null && !configuredDelay.isEmpty()) {
                try {
                    delayMs = Math.max(0L, Long.parseLong(configuredDelay));
                } catch (NumberFormatException e) {
                    MineOcclude.LOG.error("[MineOcclude/client] invalid auto-connect delay: {}",
                            configuredDelay);
                    autoConnectDone = true;
                    return;
                }
            }
            autoConnectAfterNanos = System.nanoTime() + delayMs * 1_000_000L;
            if (delayMs > 0L) {
                MineOcclude.LOG.info("[MineOcclude/client] deferring auto-connect by {} ms",
                        delayMs);
            }
        }
        if (System.nanoTime() < autoConnectAfterNanos) return;
        autoConnectDone = true;
        try {
            String host = target;
            int port = 25565;
            int c = target.lastIndexOf(':');
            if (c > 0) {
                host = target.substring(0, c);
                port = Integer.parseInt(target.substring(c + 1));
            }
            MineOcclude.LOG.info("[MineOcclude/client] auto-connecting to {}:{}", host, port);
            client.openScreen(new ConnectScreen(client.currentScreen, client, host, port));
        } catch (Throwable t) {
            MineOcclude.LOG.error("[MineOcclude/client] auto-connect failed; connect manually", t);
        }
    }

    private void onEpisodeEvent(MinecraftClient client, EpisodeEventPacket pkt) {
        if (pkt.type == EpisodeEventPacket.Type.START) {
            closeLogger();
            // Keep already-queued ticks OF THIS EPISODE: tick packets arrive
            // on the network thread while this START handler is deferred to
            // the game thread, so tick 0 can already be queued — clearing it
            // dropped the first tick of an episode (observed once at runtime
            // as a state=210/frame=209 cardinality rejection).
            pending.removeIf(t -> t.episodeId != pkt.episodeId);
            frameCapture.resetStaleDetector();
            currentEpisodeId = pkt.episodeId;
            renderFrameIdx = 0;
            nextActionIdx = 0;
            prevServerTick = -1;
            pairingShift = pkt.pairingShift;
            MineOcclude.LOG.info("[MineOcclude/client] action pairing shift = {}", pairingShift);
            actionSampler.resetCamera();
            // Hide the HUD so crosshair/hotbar/hand are not baked into frames.
            if (client.options != null) client.options.hudHidden = true;
            Path root = client.runDirectory.toPath().resolve("mineocclude_client_out");
            episodeDir = root.resolve("episode_" + pkt.episodeId);
            try {
                // Wipe any stale frames from a previous run of this episode id,
                // otherwise leftover PNGs cause a frame/log cardinality mismatch.
                deleteRecursively(episodeDir);
                java.nio.file.Files.createDirectories(episodeDir.resolve("frames"));
                logger = new ClientLogger(episodeDir);
                MineOcclude.LOG.info("[MineOcclude/client] episode {} recording -> {}",
                        pkt.episodeId, episodeDir);
            } catch (IOException e) {
                MineOcclude.LOG.error("[MineOcclude/client] could not open logs", e);
                logger = null;
            }
        } else {
            // Flush any straggler ticks before closing, then finalize.
            drainAll(client);
            // Deferred pairing: frames past nextActionIdx have no action
            // row yet (one with shift 0, none with shift 1). Top up with
            // terminal samples so cardinality stays one action per frame.
            if (logger != null) {
                while (nextActionIdx < renderFrameIdx) {
                    try {
                        logger.writeAction(currentEpisodeId, prevServerTick,
                                nextActionIdx, nextActionIdx,
                                actionSampler.sample(client));
                    } catch (IOException e) {
                        MineOcclude.LOG.error("[MineOcclude/client] final action write failed", e);
                        break;
                    }
                    nextActionIdx++;
                }
            }
            closeLogger();
            if (client.options != null) client.options.hudHidden = false; // restore HUD
            MineOcclude.LOG.info("[MineOcclude/client] episode {} finished, {} frames",
                    currentEpisodeId, renderFrameIdx);
            currentEpisodeId = -1;
        }
    }

    /** One rendered frame: consume at most one pending tick. */
    private void onFrame(MinecraftClient client) {
        if (logger == null) return;
        PendingTick pt = pending.poll();
        if (pt == null) return;
        try {
            captureOne(client, pt);
        } catch (Throwable t) {
            // Never let a capture error crash the render thread / drop the client.
            MineOcclude.LOG.error("[MineOcclude/client] capture threw (non-fatal)", t);
        }
        if (pending.size() > 4) {
            MineOcclude.LOG.warn("[MineOcclude/client] {} ticks queued — render is behind 20 Hz; "
                    + "trajectory may fail cardinality QA", pending.size());
        }
        int writeBacklog = frameCapture.pendingWrites();
        if (writeBacklog > 20) {
            MineOcclude.LOG.warn("[MineOcclude/client] {} PNG writes backlogged — disk I/O is falling "
                    + "behind capture; the growing in-memory image queue can itself trigger GC pauses "
                    + "that freeze rendering", writeBacklog);
        }
    }

    private void drainAll(MinecraftClient client) {
        PendingTick pt;
        while ((pt = pending.poll()) != null) {
            captureOne(client, pt);
        }
    }

    /** server_tick of the previously captured frame (for deferred pairing). */
    private long prevServerTick = -1;

    private void captureOne(MinecraftClient client, PendingTick pt) {
        long idx = renderFrameIdx;
        Path framePath = episodeDir.resolve("frames")
                .resolve(String.format("%06d.png", idx));
        long captureNanos = System.nanoTime();
        boolean ok = frameCapture.capture(client, framePath, pt.episodeId, pt.serverTick);
        // Frozen orientation: visual_i -> action_i -> visual_(i+1). The
        // sample taken at capture k is written as action index
        // k - 1 + pairingShift, where pairingShift is calibrated per
        // connection by the scripted-impulse fixture: the client/server tick
        // phase (fixed at connect time) moves the sub-tick attribution by
        // +/-1 between sessions, so no constant pairing is universally
        // correct. Calibration measures the offset and zeroes it; the
        // pixel-level impulse check then gates every impulse episode on
        // offset == 0.
        ActionSampler.Action action = actionSampler.sample(client);
        long targetIdx = idx - 1 + pairingShift;
        try {
            if (targetIdx >= 0 && targetIdx == nextActionIdx) {
                long targetTick = targetIdx == idx ? pt.serverTick : prevServerTick;
                logger.writeAction(pt.episodeId, targetTick, targetIdx, targetIdx, action);
                nextActionIdx++;
            }
            logger.writeTick(pt.episodeId, pt.serverTick, idx,
                    pt.serverEpochNanos, pt.recvNanos, captureNanos,
                    episodeDir.relativize(framePath).toString());
        } catch (IOException e) {
            MineOcclude.LOG.error("[MineOcclude/client] log write failed", e);
        }
        prevServerTick = pt.serverTick;
        if (!ok) {
            MineOcclude.LOG.error("[MineOcclude/client] frame capture failed at idx {}", idx);
        }
        renderFrameIdx++;
    }

    private void closeLogger() {
        if (logger != null) {
            try { logger.close(); } catch (IOException ignored) {}
            logger = null;
        }
    }

    private static void deleteRecursively(Path dir) {
        if (!java.nio.file.Files.exists(dir)) return;
        try (java.util.stream.Stream<Path> walk = java.nio.file.Files.walk(dir)) {
            walk.sorted(java.util.Comparator.reverseOrder()).forEach(p -> {
                try { java.nio.file.Files.delete(p); } catch (IOException ignored) {}
            });
        } catch (IOException ignored) {}
    }
}
