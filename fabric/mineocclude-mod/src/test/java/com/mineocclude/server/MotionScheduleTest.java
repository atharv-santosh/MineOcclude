package com.mineocclude.server;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class MotionScheduleTest {
    @TempDir
    Path tmp;

    private Path write(String segments) throws IOException {
        String json = "{\"schedule_format_version\":\"mineocclude-motion-schedule-v0.1\","
                + "\"trajectory_spec_id\":\"spec_a\",\"spec_hash\":\"abc123\","
                + "\"expected_ticks\":60,\"segments\":" + segments + "}";
        Path file = tmp.resolve("motion.json");
        Files.write(file, json.getBytes(StandardCharsets.UTF_8));
        return file;
    }

    @Test
    void loadsGapFreePiecewiseSchedule() throws IOException {
        MotionSchedule schedule = MotionSchedule.load(write("["
                        + "{\"start_model_frame_idx\":0,\"stop_model_frame_idx_exclusive\":12,"
                        + "\"signed_speed_blocks_per_second\":1.5},"
                        + "{\"start_model_frame_idx\":12,\"stop_model_frame_idx_exclusive\":28,"
                        + "\"signed_speed_blocks_per_second\":0.0},"
                        + "{\"start_model_frame_idx\":28,\"stop_model_frame_idx_exclusive\":60,"
                        + "\"signed_speed_blocks_per_second\":1.5}]"),
                "spec_a", "abc123", 60);
        assertEquals(3, schedule.segmentCount());
        assertEquals(1.5, schedule.velocityAt(11));
        assertEquals(0.0, schedule.velocityAt(12));
        assertEquals(1.5, schedule.velocityAt(59));
        assertEquals(2, schedule.segmentIndexAt(59));
    }

    @Test
    void rejectsIdentityMismatch() throws IOException {
        Path file = write("[{\"start_model_frame_idx\":0,"
                + "\"stop_model_frame_idx_exclusive\":60,"
                + "\"signed_speed_blocks_per_second\":1.0}]");
        assertThrows(IOException.class,
                () -> MotionSchedule.load(file, "other", "abc123", 60));
    }

    @Test
    void rejectsGapOrIncompleteCoverage() throws IOException {
        Path file = write("[{\"start_model_frame_idx\":1,"
                + "\"stop_model_frame_idx_exclusive\":60,"
                + "\"signed_speed_blocks_per_second\":1.0}]");
        assertThrows(IOException.class,
                () -> MotionSchedule.load(file, "spec_a", "abc123", 60));
    }
}
