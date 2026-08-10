package com.mineocclude.client;

import com.mineocclude.MineOcclude;
import com.mojang.blaze3d.systems.RenderSystem;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gl.Framebuffer;
import net.minecraft.client.texture.NativeImage;

import java.io.File;
import java.io.IOException;
import java.nio.file.Path;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Captures the current main framebuffer to a PNG. Mirrors the logic Minecraft's
 * own screenshot helper uses (read the color attachment into a NativeImage,
 * flip vertically because GL's origin is bottom-left).
 *
 * IMPORTANT: launch the client at exactly 640x360 so the framebuffer is already
 * the raw capture resolution required by the model-input contract. We assert the
 * size and warn loudly on mismatch rather than silently rescaling here — the
 * deterministic 384x224 resize belongs in Python preprocessing, not the client.
 *
 * Must be called on the render thread (a valid GL context is required).
 */
public final class FrameCapture {
    public static final int EXPECTED_W = 640;
    public static final int EXPECTED_H = 360;

    private boolean warnedSize = false;

    private static final long NO_SAMPLE = Long.MIN_VALUE;
    private static final int STALE_WARN_THRESHOLD = 5;
    private long lastSample = NO_SAMPLE;
    private int staleStreak = 0;

    /** Cheap 8x8-grid pixel sample so a frozen framebuffer is detectable
     *  without scanning every pixel of every frame. */
    private static long sampleChecksum(NativeImage image) {
        int w = image.getWidth(), h = image.getHeight();
        long hash = 0;
        for (int gy = 0; gy < 8; gy++) {
            int y = Math.min(h - 1, gy * h / 8);
            for (int gx = 0; gx < 8; gx++) {
                int x = Math.min(w - 1, gx * w / 8);
                hash = hash * 31 + image.getPixelColor(x, y);
            }
        }
        return hash;
    }

    // PNG encoding + disk I/O run OFF the render thread so capture never blocks
    // rendering (a synchronous 720p PNG write per frame freezes the client).
    private static final ExecutorService IO = Executors.newFixedThreadPool(
            3, r -> {
                Thread t = new Thread(r, "mineocclude-frame-io");
                t.setDaemon(true);
                return t;
            });
    private final AtomicInteger pending = new AtomicInteger(0);
    private final AtomicInteger writeErrors = new AtomicInteger(0);

    /** Call when a new episode starts recording: a stale-frame streak carried
     *  over from the previous episode must not be silently attributed to (or
     *  hidden from) the new one. */
    public void resetStaleDetector() {
        lastSample = NO_SAMPLE;
        staleStreak = 0;
        writeErrors.set(0);
    }

    /** @return true on success. */
    public boolean capture(MinecraftClient client, Path outFile) {
        return capture(client, outFile, -1, -1);
    }

    /** @return true on success. episodeId/tick are for diagnostics only (-1 if unknown). */
    public boolean capture(MinecraftClient client, Path outFile, long episodeId, long tick) {
        Framebuffer fb = client.getFramebuffer();
        if (fb == null) return false;

        int w = fb.textureWidth;
        int h = fb.textureHeight;
        if (!warnedSize) {
            // Any 16:9 framebuffer is fine: Python preprocessing resizes every
            // frame to 384x224 downstream, so a Retina 1280x720 capture is a
            // higher-quality superset of 640x360. Only warn if the aspect ratio
            // is wrong (letterboxing/stretch would corrupt the geometry).
            double aspect = (double) w / h;
            double target = (double) EXPECTED_W / EXPECTED_H; // 16:9
            if (Math.abs(aspect - target) > 0.02) {
                MineOcclude.LOG.warn("[MineOcclude] framebuffer {}x{} is not 16:9 "
                        + "(aspect {}). Homography/geometry assume 16:9 — set the "
                        + "window to a 16:9 size (e.g. 640x360 or 1280x720).",
                        w, h, aspect);
            } else if (w != EXPECTED_W || h != EXPECTED_H) {
                MineOcclude.LOG.info("[MineOcclude] capturing at {}x{} (16:9). "
                        + "Fine — downstream resize is to 384x224. For exact "
                        + "640x360 on a Retina display use a 320x180 window.",
                        w, h);
            }
            warnedSize = true;
        }

        // Copy the framebuffer into a NativeImage on the render thread (this is
        // the only part that needs the GL context — it's a fast memory copy).
        NativeImage image = new NativeImage(w, h, false);
        try {
            RenderSystem.bindTexture(fb.getColorAttachment());
            image.loadFromTextureImage(0, false);
            image.mirrorVertically();
        } catch (Throwable t) {
            MineOcclude.LOG.error("[MineOcclude] framebuffer read failed", t);
            image.close();
            return false;
        }

        // GL context can silently stop presenting (observed on macOS as
        // "Cocoa: Failed to find service port for display" when the window is
        // minimized/occluded) — the texture read above still "succeeds" but
        // returns whatever was last actually rendered, so every subsequent
        // capture is a byte-identical stale copy. That corruption previously
        // surfaced only days later as a Python QA rejection ("sheep was never
        // seen"). Catch it here instead: a real GL error, or an unchanged
        // sparse pixel sample vs. the previous capture, means this frame (and
        // likely the rest of the episode) is stale.
        int glErr = org.lwjgl.opengl.GL11.glGetError();
        if (glErr != org.lwjgl.opengl.GL11.GL_NO_ERROR) {
            MineOcclude.LOG.error("[MineOcclude] GL error {} while reading framebuffer for {} — "
                    + "capture is likely stale (window minimized/occluded?)", glErr, outFile);
        }
        long sample = sampleChecksum(image);
        if (sample == lastSample && lastSample != NO_SAMPLE) {
            staleStreak++;
            // Fire at the threshold and then periodically for as long as the
            // freeze persists — a one-shot warning goes silent for the rest of
            // a fully-frozen episode (previously observed: the warning fired
            // once at the tail of episode N, then episode N+1 ran fully
            // frozen with no further log line at all).
            if (staleStreak == STALE_WARN_THRESHOLD || staleStreak % 20 == 0) {
                MineOcclude.LOG.error("[MineOcclude] {} consecutive byte-identical captures at "
                        + "episode={} tick={} — the renderer appears frozen (keep the Minecraft "
                        + "window visible and un-occluded during collection; this episode's frames "
                        + "are likely all duplicates)",
                        staleStreak, episodeId, tick);
            }
        } else {
            staleStreak = 0;
        }
        lastSample = sample;

        // Encode + write to disk on a background thread. The render thread is free.
        final NativeImage img = image;
        final File file = new File(outFile.toString());
        pending.incrementAndGet();
        IO.execute(() -> {
            try {
                img.writeFile(file);
            } catch (IOException e) {
                writeErrors.incrementAndGet();
                MineOcclude.LOG.error("[MineOcclude] frame write failed: {}", file, e);
            } finally {
                img.close();
                pending.decrementAndGet();
            }
        });
        return true;
    }

    /** Frames captured but not yet written to disk (backlog). */
    public int pendingWrites() {
        return pending.get();
    }

    public int writeErrors() { return writeErrors.get(); }

    /** Bounded authoritative wait for all queued PNG writes to finish. */
    public boolean awaitDrained(long timeoutMillis) {
        long deadline = System.nanoTime() + timeoutMillis * 1_000_000L;
        while (pending.get() > 0 && System.nanoTime() < deadline) {
            try {
                Thread.sleep(10L);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                return false;
            }
        }
        return pending.get() == 0 && writeErrors.get() == 0;
    }
}
