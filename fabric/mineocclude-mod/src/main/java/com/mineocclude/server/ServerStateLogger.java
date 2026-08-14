package com.mineocclude.server;

import com.mineocclude.MineOcclude;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

/**
 * Writes one authoritative state row per accepted tick to server_state.jsonl.
 *
 * This is the ground-truth channel. The client never infers sheep position from
 * video; Python never reconstructs a missing tick. Exactly one row per tick,
 * consecutive ticks, no repair.
 *
 * JSON is written by hand with Locale.ROOT number formatting so the decimal
 * point is always '.', independent of the host locale.
 */
public final class ServerStateLogger implements AutoCloseable {
    private final BufferedWriter out;
    private long lastTick = -1;

    public ServerStateLogger(Path episodeDir) throws IOException {
        Files.createDirectories(episodeDir);
        Path file = episodeDir.resolve("server_state.jsonl");
        this.out = Files.newBufferedWriter(file, StandardCharsets.UTF_8,
                StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING, StandardOpenOption.WRITE);
    }

    public void write(EpisodeConfig cfg, long serverTick, long epochNanos,
                      SheepController sheep, boolean geometricVisible,
                      double playerX, double playerY, double playerZ,
                      double playerYaw, double playerPitch,
                      double commandedVelocity, int motionSegmentIndex) throws IOException {
        // Consecutive-tick assertion. A gap means a dropped tick -> recollect.
        if (lastTick >= 0 && serverTick != lastTick + 1) {
            MineOcclude.LOG.error("[MineOcclude] NON-CONSECUTIVE TICK: {} after {} (episode {})",
                    serverTick, lastTick, cfg.episodeId);
        }
        lastTick = serverTick;

        double tauSeconds = geometricVisible ? 0.0 : Double.NaN; // filled downstream per-occlusion
        StringBuilder sb = new StringBuilder(384);
        sb.append('{');
        kv(sb, "episode_id", cfg.episodeId); sb.append(',');
        kv(sb, "server_tick", serverTick); sb.append(',');
        kvs(sb, "layout_id", cfg.layoutId); sb.append(',');
        kvs(sb, "regime", "A"); sb.append(',');
        kvs(sb, "scene", cfg.scene.name()); sb.append(',');
        kv(sb, "seed", cfg.seed); sb.append(',');
        kv(sb, "v", commandedVelocity); sb.append(',');
        kv(sb, "commanded_v", commandedVelocity); sb.append(',');
        kv(sb, "motion_segment_index", motionSegmentIndex); sb.append(',');
        nullableString(sb, "trajectory_spec_id", cfg.trajectorySpecId); sb.append(',');
        nullableString(sb, "spec_hash", cfg.specHash); sb.append(',');
        kv(sb, "q", cfg.processQ); sb.append(',');
        kv(sb, "hidden_frames", cfg.hiddenFrames); sb.append(',');
        // sheep is null for the NO_SHEEP control -> log nulls.
        nullableString(sb, "target_entity_uuid", sheep == null ? null : sheep.targetUuid()); sb.append(',');
        nullableString(sb, "target_entity_tag", sheep == null ? null
                : TargetRetentionPolicy.EXPERIMENT_TARGET_TAG); sb.append(',');
        kvb(sb, "target_present", sheep != null && sheep.entityAlive()); sb.append(',');
        kv(sb, "target_respawn_count", sheep == null ? 0 : sheep.respawnCount()); sb.append(',');
        double noise = sheep == null ? Double.NaN : sheep.lastNoiseDraw();
        double apos  = sheep == null ? Double.NaN : sheep.axisPos();
        double avel  = sheep == null ? Double.NaN : sheep.lastVelocity();
        double sx    = sheep == null ? Double.NaN : sheep.sheepX();
        double sy    = sheep == null ? Double.NaN : sheep.sheepY();
        double sz    = sheep == null ? Double.NaN : sheep.sheepZ();
        kv(sb, "noise_draw", noise); sb.append(',');
        kv(sb, "axis_pos", apos); sb.append(',');
        kv(sb, "axis_velocity", avel); sb.append(',');
        kv(sb, "sheep_x", sx); sb.append(',');
        kv(sb, "sheep_y", sy); sb.append(',');
        kv(sb, "sheep_z", sz); sb.append(',');
        kvb(sb, "geometric_visible", geometricVisible); sb.append(',');
        kv(sb, "player_x", playerX); sb.append(',');
        kv(sb, "player_y", playerY); sb.append(',');
        kv(sb, "player_z", playerZ); sb.append(',');
        kv(sb, "player_yaw", playerYaw); sb.append(',');
        kv(sb, "player_pitch", playerPitch); sb.append(',');
        kv(sb, "server_epoch_nanos", epochNanos);
        sb.append('}');
        out.write(sb.toString());
        out.write('\n');
        // Flush every tick: at 20 Hz this is negligible I/O and guarantees the
        // authoritative record survives an unexpected server stop mid-episode.
        out.flush();
    }

    public void flush() throws IOException { out.flush(); }

    @Override
    public void close() throws IOException {
        out.flush();
        out.close();
    }

    private static void kv(StringBuilder sb, String k, long v) {
        sb.append('"').append(k).append("\":").append(v);
    }
    private static void kv(StringBuilder sb, String k, double v) {
        sb.append('"').append(k).append("\":");
        if (Double.isNaN(v) || Double.isInfinite(v)) {
            sb.append("null");
        } else {
            // Full round-trip precision (Double.toString), not %.6f: the
            // deterministic-replay check (C2.7) compares the logged noise
            // draw byte-for-byte against the immutable Python schedule, and
            // 6-decimal truncation loses ~5e-7 of the draw. Double.toString
            // output (including exponent forms like 1.0E-5) is valid JSON
            // and is exact for round-tripping.
            sb.append(Double.toString(v));
        }
    }
    private static void kvs(StringBuilder sb, String k, String v) {
        sb.append('"').append(k).append("\":\"").append(v).append('"');
    }
    private static void kvb(StringBuilder sb, String k, boolean v) {
        sb.append('"').append(k).append("\":").append(v);
    }
    private static void nullableString(StringBuilder sb, String k, String v) {
        sb.append('"').append(k).append("\":");
        if (v == null) sb.append("null");
        else sb.append('"').append(v).append('"');
    }
}
