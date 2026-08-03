package com.mineocclude.server;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

/**
 * Immutable per-episode noise schedule, produced by
 * {@code mineocclude.data.noise_schedule} (NumPy PCG64) and consumed by the
 * server in strict {@code draw_idx} order.
 *
 * Per the frozen RNG decision the server never recreates draws from a seed:
 * it verifies the stored schedule (seed match, consecutive draw_idx,
 * sqrt(q*dt) scaling) and hands out draws one tick at a time. Exhausting or
 * skipping the schedule is an episode-fatal error, never repaired.
 *
 * File format (one JSON object per line): a header line with
 * schedule_format_version/producer/bit_generator/seed/n_draws/q/dt_seconds,
 * then one row per draw with draw_idx/standard_normal_draw/q/dt_seconds/
 * noise_std_blocks/noise_draw.
 */
public final class NoiseSchedule {
    public static final String FORMAT_VERSION = "person-c-noise-schedule-v0.1";
    private static final double ABS_TOL = 1e-9;

    public final long seed;
    public final double q;
    public final double dtSeconds;
    private final double[] noiseDraws;
    private int nextDraw = 0;

    private NoiseSchedule(long seed, double q, double dtSeconds, double[] noiseDraws) {
        this.seed = seed;
        this.q = q;
        this.dtSeconds = dtSeconds;
        this.noiseDraws = noiseDraws;
    }

    public int size() { return noiseDraws.length; }
    public int consumed() { return nextDraw; }
    public int remaining() { return noiseDraws.length - nextDraw; }

    /** Consume the next draw in order. Throws when the schedule is exhausted. */
    public double nextNoiseDraw() {
        if (nextDraw >= noiseDraws.length) {
            throw new IllegalStateException(
                    "noise schedule exhausted after " + noiseDraws.length + " draws");
        }
        return noiseDraws[nextDraw++];
    }

    /** Parse and verify a serialized schedule. Throws on any defect. */
    public static NoiseSchedule load(Path file, long expectedSeed) throws IOException {
        List<String> lines = Files.readAllLines(file, StandardCharsets.UTF_8);
        if (lines.isEmpty()) {
            throw new IOException("noise schedule file is empty: " + file);
        }
        // Gson 2.8.0 (bundled by MC 1.16.5) has no static parseString.
        JsonObject header = new JsonParser().parse(lines.get(0)).getAsJsonObject();
        String format = asString(header, "schedule_format_version");
        if (!FORMAT_VERSION.equals(format)) {
            throw new IOException("unsupported schedule_format_version " + format);
        }
        if (!"numpy.random.Generator".equals(asString(header, "producer"))
                || !"PCG64".equals(asString(header, "bit_generator"))) {
            throw new IOException("schedule producer violates the frozen RNG decision");
        }
        long seed = header.get("seed").getAsLong();
        if (seed != expectedSeed) {
            throw new IOException("schedule seed " + seed
                    + " does not match the episode seed " + expectedSeed);
        }
        int nDraws = header.get("n_draws").getAsInt();
        double q = header.get("q").getAsDouble();
        double dt = header.get("dt_seconds").getAsDouble();
        double expectedStd = Math.sqrt(q * dt);

        List<String> rows = lines.subList(1, lines.size());
        // Tolerate a single trailing blank line from text editors; nothing else.
        while (!rows.isEmpty() && rows.get(rows.size() - 1).trim().isEmpty()) {
            rows = rows.subList(0, rows.size() - 1);
        }
        if (rows.size() != nDraws) {
            throw new IOException("header declares " + nDraws
                    + " draws but the file has " + rows.size());
        }
        double[] draws = new double[nDraws];
        for (int index = 0; index < nDraws; index++) {
            JsonObject row = new JsonParser().parse(rows.get(index)).getAsJsonObject();
            if (row.get("draw_idx").getAsInt() != index) {
                throw new IOException("draw_idx must be consecutive from 0; row "
                        + index + " has " + row.get("draw_idx"));
            }
            if (row.get("seed").getAsLong() != seed) {
                throw new IOException("row " + index + " seed does not match the header");
            }
            double z = row.get("standard_normal_draw").getAsDouble();
            double std = row.get("noise_std_blocks").getAsDouble();
            double draw = row.get("noise_draw").getAsDouble();
            if (Math.abs(std - expectedStd) > ABS_TOL) {
                throw new IOException("row " + index + " violates sqrt(q*dt) scaling");
            }
            if (Math.abs(draw - z * std) > ABS_TOL) {
                throw new IOException("row " + index
                        + ": noise_draw != standard_normal_draw * std");
            }
            draws[index] = draw;
        }
        return new NoiseSchedule(seed, q, dt, draws);
    }

    private static String asString(JsonObject object, String key) {
        return object.has(key) && !object.get(key).isJsonNull()
                ? object.get(key).getAsString() : null;
    }
}
