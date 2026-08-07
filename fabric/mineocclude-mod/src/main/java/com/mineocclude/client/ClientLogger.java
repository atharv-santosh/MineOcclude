package com.mineocclude.client;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Locale;

/**
 * Writes the two client-side logs per episode:
 *   raw_actions.jsonl  — one complete raw action per captured frame
 *   client_tick.jsonl  — capture diagnostics + the join key for each frame
 *
 * The join key (episode_id, server_tick, render_frame_idx, action_idx) is the
 * ONLY thing that binds a frame to a tick downstream. Timestamps are diagnostics.
 */
public final class ClientLogger implements AutoCloseable {
    private final BufferedWriter actions;
    private final BufferedWriter ticks;

    public ClientLogger(Path episodeDir) throws IOException {
        Files.createDirectories(episodeDir);
        this.actions = open(episodeDir.resolve("raw_actions.jsonl"));
        this.ticks = open(episodeDir.resolve("client_tick.jsonl"));
    }

    private static BufferedWriter open(Path p) throws IOException {
        return Files.newBufferedWriter(p, StandardCharsets.UTF_8,
                StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING, StandardOpenOption.WRITE);
    }

    public void writeAction(long episodeId, long serverTick, long renderFrameIdx, long actionIdx,
                            ActionSampler.Action a) throws IOException {
        StringBuilder sb = new StringBuilder(320);
        sb.append('{');
        sb.append("\"episode_id\":").append(episodeId).append(',');
        sb.append("\"server_tick\":").append(serverTick).append(',');
        sb.append("\"render_frame_idx\":").append(renderFrameIdx).append(',');
        sb.append("\"action_idx\":").append(actionIdx).append(',');
        b(sb, "forward", a.forward); b(sb, "back", a.back); b(sb, "left", a.left); b(sb, "right", a.right);
        b(sb, "jump", a.jump); b(sb, "sneak", a.sneak); b(sb, "sprint", a.sprint);
        b(sb, "use", a.use); b(sb, "attack", a.attack); b(sb, "drop", a.drop); b(sb, "pick_item", a.pickItem);
        sb.append("\"hotbar\":").append(a.hotbar).append(',');
        sb.append("\"camera_dx\":").append(fmt(a.cameraDx)).append(',');
        sb.append("\"camera_dy\":").append(fmt(a.cameraDy));
        sb.append('}');
        actions.write(sb.toString());
        actions.write('\n');
    }

    public void writeTick(long episodeId, long serverTick, long renderFrameIdx,
                          long serverEpochNanos, long clientRecvNanos, long clientCaptureNanos,
                          String framePath) throws IOException {
        StringBuilder sb = new StringBuilder(256);
        sb.append('{');
        sb.append("\"episode_id\":").append(episodeId).append(',');
        sb.append("\"server_tick\":").append(serverTick).append(',');
        sb.append("\"render_frame_idx\":").append(renderFrameIdx).append(',');
        sb.append("\"server_epoch_nanos\":").append(serverEpochNanos).append(',');
        sb.append("\"client_recv_nanos\":").append(clientRecvNanos).append(',');
        sb.append("\"client_capture_nanos\":").append(clientCaptureNanos).append(',');
        sb.append("\"frame_path\":\"").append(framePath.replace("\\", "/")).append('"');
        sb.append('}');
        ticks.write(sb.toString());
        ticks.write('\n');
        // Buffered (NOT flushed per frame): this runs on the render thread, and
        // per-frame disk flushes cause capture stutter. The logs are flushed at
        // episode end (close), which is when the QA validator reads them.
    }

    public void flush() throws IOException { actions.flush(); ticks.flush(); }

    @Override
    public void close() throws IOException {
        actions.flush(); actions.close();
        ticks.flush(); ticks.close();
    }

    private static void b(StringBuilder sb, String k, boolean v) {
        sb.append('"').append(k).append("\":").append(v).append(',');
    }
    private static String fmt(double v) {
        return String.format(Locale.ROOT, "%.4f", v);
    }
}
