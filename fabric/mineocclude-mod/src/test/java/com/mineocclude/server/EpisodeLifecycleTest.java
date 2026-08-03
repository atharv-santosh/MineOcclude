package com.mineocclude.server;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** C2.2: legal transitions succeed, illegal transitions fail loudly. */
class EpisodeLifecycleTest {

    @Test
    void happyPathReachesCompleted() {
        EpisodeLifecycle lc = new EpisodeLifecycle();
        lc.to(EpisodeLifecycle.State.RESETTING, "start");
        lc.to(EpisodeLifecycle.State.READY, "scene built");
        lc.to(EpisodeLifecycle.State.RECORDING, "capture opened");
        lc.to(EpisodeLifecycle.State.FINALIZING, "end");
        lc.to(EpisodeLifecycle.State.COMPLETED, "clean");
        assertTrue(lc.isTerminal());
        assertEquals(EpisodeLifecycle.State.COMPLETED, lc.state());
        assertEquals(5, lc.transitions().size());
    }

    @Test
    void recordingCannotStartFromIdle() {
        EpisodeLifecycle lc = new EpisodeLifecycle();
        assertThrows(IllegalStateException.class,
                () -> lc.to(EpisodeLifecycle.State.RECORDING, "skip reset"));
    }

    @Test
    void resetCannotOverlapRecording() {
        EpisodeLifecycle lc = new EpisodeLifecycle();
        lc.to(EpisodeLifecycle.State.RESETTING, "start");
        lc.to(EpisodeLifecycle.State.READY, "ready");
        lc.to(EpisodeLifecycle.State.RECORDING, "go");
        assertThrows(IllegalStateException.class,
                () -> lc.to(EpisodeLifecycle.State.RESETTING, "overlapping reset"));
    }

    @Test
    void failIsReachableFromAnyNonTerminalState() {
        EpisodeLifecycle lc = new EpisodeLifecycle();
        lc.to(EpisodeLifecycle.State.RESETTING, "start");
        lc.fail("target count wrong");
        assertEquals(EpisodeLifecycle.State.FAILED, lc.state());
        assertTrue(lc.isTerminal());
        assertThrows(IllegalStateException.class, () -> lc.fail("double fail"));
    }

    @Test
    void completedIsImmutable() {
        EpisodeLifecycle lc = new EpisodeLifecycle();
        lc.to(EpisodeLifecycle.State.RESETTING, "start");
        lc.to(EpisodeLifecycle.State.READY, "ready");
        lc.to(EpisodeLifecycle.State.RECORDING, "go");
        lc.to(EpisodeLifecycle.State.FINALIZING, "end");
        lc.to(EpisodeLifecycle.State.COMPLETED, "clean");
        assertThrows(IllegalStateException.class,
                () -> lc.to(EpisodeLifecycle.State.RESETTING, "reuse"));
    }

    @Test
    void jsonLogContainsEveryTransition() {
        EpisodeLifecycle lc = new EpisodeLifecycle();
        lc.to(EpisodeLifecycle.State.RESETTING, "start \"quoted\"");
        String json = lc.toJsonLines();
        assertTrue(json.contains("\"from\":\"IDLE\""));
        assertTrue(json.contains("\"to\":\"RESETTING\""));
        assertFalse(json.contains("\"quoted\""));  // quotes are sanitized
    }
}
