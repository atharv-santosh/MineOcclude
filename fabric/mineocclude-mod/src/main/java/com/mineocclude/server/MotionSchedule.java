package com.mineocclude.server;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * Immutable, spec-bound commanded-speed schedule for the large-scale no-wall
 * campaign. The Python campaign controller serializes the already-frozen P1
 * segments; the server validates complete, gap-free tick coverage and never
 * synthesizes or repairs a scientific schedule.
 */
public final class MotionSchedule {
    public static final String FORMAT_VERSION = "mineocclude-motion-schedule-v0.1";

    public static final class Segment {
        public final int startTick;
        public final int stopTickExclusive;
        public final double signedSpeed;

        Segment(int startTick, int stopTickExclusive, double signedSpeed) {
            this.startTick = startTick;
            this.stopTickExclusive = stopTickExclusive;
            this.signedSpeed = signedSpeed;
        }
    }

    public final String trajectorySpecId;
    public final String specHash;
    public final int expectedTicks;
    private final Segment[] segments;

    private MotionSchedule(String trajectorySpecId, String specHash,
                           int expectedTicks, Segment[] segments) {
        this.trajectorySpecId = trajectorySpecId;
        this.specHash = specHash;
        this.expectedTicks = expectedTicks;
        this.segments = segments;
    }

    public int segmentCount() { return segments.length; }

    public int segmentIndexAt(int tick) {
        for (int index = 0; index < segments.length; index++) {
            Segment segment = segments[index];
            if (tick >= segment.startTick && tick < segment.stopTickExclusive) {
                return index;
            }
        }
        throw new IllegalStateException("motion schedule has no command for tick " + tick);
    }

    public double velocityAt(int tick) {
        return segments[segmentIndexAt(tick)].signedSpeed;
    }

    public static MotionSchedule load(Path file, String expectedSpecId,
                                      String expectedSpecHash, int expectedTicks)
            throws IOException {
        JsonObject root = new JsonParser().parse(new String(
                Files.readAllBytes(file), StandardCharsets.UTF_8)).getAsJsonObject();
        if (!FORMAT_VERSION.equals(root.get("schedule_format_version").getAsString())) {
            throw new IOException("unsupported motion schedule format");
        }
        String specId = root.get("trajectory_spec_id").getAsString();
        String specHash = root.get("spec_hash").getAsString();
        int ticks = root.get("expected_ticks").getAsInt();
        if (!expectedSpecId.equals(specId) || !expectedSpecHash.equals(specHash)) {
            throw new IOException("motion schedule spec identity mismatch");
        }
        if (ticks != expectedTicks || ticks <= 0) {
            throw new IOException("motion schedule expected_ticks mismatch");
        }
        JsonArray rows = root.getAsJsonArray("segments");
        if (rows == null || rows.size() == 0) {
            throw new IOException("motion schedule has no segments");
        }
        Segment[] segments = new Segment[rows.size()];
        int expectedStart = 0;
        for (int index = 0; index < rows.size(); index++) {
            JsonObject row = rows.get(index).getAsJsonObject();
            int start = row.get("start_model_frame_idx").getAsInt();
            int stop = row.get("stop_model_frame_idx_exclusive").getAsInt();
            double speed = row.get("signed_speed_blocks_per_second").getAsDouble();
            if (start != expectedStart || stop <= start || stop > ticks
                    || Double.isNaN(speed) || Double.isInfinite(speed)) {
                throw new IOException("invalid motion segment " + index);
            }
            segments[index] = new Segment(start, stop, speed);
            expectedStart = stop;
        }
        if (expectedStart != ticks) {
            throw new IOException("motion schedule does not cover every expected tick");
        }
        return new MotionSchedule(specId, specHash, ticks, segments);
    }
}
