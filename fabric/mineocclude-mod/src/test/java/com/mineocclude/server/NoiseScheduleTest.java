package com.mineocclude.server;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** C2.4: the server verifies and consumes the immutable schedule in order. */
class NoiseScheduleTest {

    @TempDir
    Path tmp;

    private static String header(long seed, int nDraws, double q, double dt) {
        return String.format(Locale.ROOT,
                "{\"schedule_format_version\":\"person-c-noise-schedule-v0.1\","
                + "\"producer\":\"numpy.random.Generator\",\"bit_generator\":\"PCG64\","
                + "\"numpy_version\":\"1.26.0\",\"seed\":%d,\"n_draws\":%d,"
                + "\"q\":%s,\"dt_seconds\":%s}", seed, nDraws, q, dt);
    }

    private static String row(long seed, int idx, double z, double q, double dt) {
        double std = Math.sqrt(q * dt);
        return String.format(Locale.ROOT,
                "{\"seed\":%d,\"draw_idx\":%d,\"standard_normal_draw\":%s,"
                + "\"q\":%s,\"dt_seconds\":%s,\"noise_std_blocks\":%s,"
                + "\"noise_draw\":%s}", seed, idx, z, q, dt, std, z * std);
    }

    private Path write(String... lines) throws IOException {
        Path file = tmp.resolve("schedule.jsonl");
        Files.write(file, String.join("\n", lines).concat("\n")
                .getBytes(StandardCharsets.UTF_8));
        return file;
    }

    @Test
    void validScheduleLoadsAndConsumesInOrder() throws IOException {
        Path file = write(
                header(42, 3, 0.2, 0.05),
                row(42, 0, 0.5, 0.2, 0.05),
                row(42, 1, -1.25, 0.2, 0.05),
                row(42, 2, 2.0, 0.2, 0.05));
        NoiseSchedule schedule = NoiseSchedule.load(file, 42);
        assertEquals(3, schedule.size());
        double std = Math.sqrt(0.2 * 0.05);
        assertEquals(0.5 * std, schedule.nextNoiseDraw(), 1e-12);
        assertEquals(-1.25 * std, schedule.nextNoiseDraw(), 1e-12);
        assertEquals(2, schedule.consumed());
        assertEquals(1, schedule.remaining());
        assertEquals(2.0 * std, schedule.nextNoiseDraw(), 1e-12);
        IllegalStateException e = assertThrows(IllegalStateException.class,
                schedule::nextNoiseDraw);
        assertTrue(e.getMessage().contains("exhausted"));
    }

    @Test
    void seedMismatchIsRejected() throws IOException {
        Path file = write(header(42, 1, 0.2, 0.05), row(42, 0, 0.5, 0.2, 0.05));
        assertThrows(IOException.class, () -> NoiseSchedule.load(file, 99));
    }

    @Test
    void skippedDrawIsRejected() throws IOException {
        Path file = write(
                header(42, 2, 0.2, 0.05),
                row(42, 0, 0.5, 0.2, 0.05),
                row(42, 2, 0.5, 0.2, 0.05));  // draw_idx 1 skipped
        assertThrows(IOException.class, () -> NoiseSchedule.load(file, 42));
    }

    @Test
    void wrongDrawCountIsRejected() throws IOException {
        Path file = write(header(42, 3, 0.2, 0.05), row(42, 0, 0.5, 0.2, 0.05));
        assertThrows(IOException.class, () -> NoiseSchedule.load(file, 42));
    }

    @Test
    void scalingViolationIsRejected() throws IOException {
        String bad = row(42, 0, 0.5, 0.2, 0.05)
                .replace("\"noise_draw\":", "\"noise_draw\":1e9, \"x\":");
        Path file = write(header(42, 1, 0.2, 0.05), bad);
        assertThrows(IOException.class, () -> NoiseSchedule.load(file, 42));
    }

    @Test
    void wrongProducerIsRejected() throws IOException {
        Path file = write(
                header(42, 1, 0.2, 0.05).replace("PCG64", "MT19937"),
                row(42, 0, 0.5, 0.2, 0.05));
        assertThrows(IOException.class, () -> NoiseSchedule.load(file, 42));
    }
}
