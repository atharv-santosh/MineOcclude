package com.mineocclude.server;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.EnumMap;
import java.util.EnumSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Explicit episode lifecycle state machine (C2.2).
 *
 * States distinguish idle, resetting, ready, recording, finalizing,
 * completed, and failed so a reset can never overlap recording and a
 * partially finalized episode can never be mistaken for complete data.
 * Illegal transitions throw; every transition is recorded with a reason and
 * a diagnostic timestamp so the per-episode lifecycle log is reproducible.
 *
 * Pure Java: no Minecraft types, unit-testable off the server.
 */
public final class EpisodeLifecycle {

    public enum State { IDLE, RESETTING, READY, RECORDING, FINALIZING, COMPLETED, FAILED }

    private static final Map<State, EnumSet<State>> LEGAL = new EnumMap<>(State.class);
    static {
        LEGAL.put(State.IDLE, EnumSet.of(State.RESETTING));
        LEGAL.put(State.RESETTING, EnumSet.of(State.READY, State.FAILED));
        LEGAL.put(State.READY, EnumSet.of(State.RECORDING, State.FAILED));
        LEGAL.put(State.RECORDING, EnumSet.of(State.FINALIZING, State.FAILED));
        LEGAL.put(State.FINALIZING, EnumSet.of(State.COMPLETED, State.FAILED));
        LEGAL.put(State.COMPLETED, EnumSet.noneOf(State.class));
        LEGAL.put(State.FAILED, EnumSet.noneOf(State.class));
    }

    /** One recorded transition. */
    public static final class Transition {
        public final State from;
        public final State to;
        public final String reason;
        public final long diagnosticNanos;

        Transition(State from, State to, String reason, long diagnosticNanos) {
            this.from = from;
            this.to = to;
            this.reason = reason;
            this.diagnosticNanos = diagnosticNanos;
        }

        public String toJson() {
            return String.format(Locale.ROOT,
                    "{\"from\":\"%s\",\"to\":\"%s\",\"reason\":\"%s\",\"diagnostic_nanos\":%d}",
                    from, to, reason.replace("\"", "'"), diagnosticNanos);
        }
    }

    private State state = State.IDLE;
    private final List<Transition> log = new ArrayList<>();

    public State state() { return state; }

    public boolean isTerminal() {
        return state == State.COMPLETED || state == State.FAILED;
    }

    public List<Transition> transitions() {
        return Collections.unmodifiableList(log);
    }

    /** Move to {@code next}; throws on an illegal transition. */
    public void to(State next, String reason) {
        if (!LEGAL.get(state).contains(next)) {
            throw new IllegalStateException(
                    "illegal lifecycle transition " + state + " -> " + next
                    + " (" + reason + "); legal: " + LEGAL.get(state));
        }
        log.add(new Transition(state, next, reason, System.nanoTime()));
        state = next;
    }

    /** FAILED is reachable from every non-terminal state. */
    public void fail(String reason) {
        if (isTerminal()) {
            throw new IllegalStateException(
                    "cannot fail a terminal episode (" + state + "): " + reason);
        }
        log.add(new Transition(state, State.FAILED, reason, System.nanoTime()));
        state = State.FAILED;
    }

    /** JSONL block for the per-episode lifecycle log. */
    public String toJsonLines() {
        StringBuilder sb = new StringBuilder();
        for (Transition transition : log) {
            sb.append(transition.toJson()).append('\n');
        }
        return sb.toString();
    }

    static { // sanity: every state has an entry
        assert LEGAL.keySet().containsAll(Arrays.asList(State.values()));
    }
}
