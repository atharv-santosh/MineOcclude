package com.mineocclude.net;

import net.minecraft.util.Identifier;

/**
 * Shared channel identifiers for MineOcclude server<->client sync.
 *
 * The server is authoritative. It broadcasts one TICK_SYNC packet on every
 * accepted server tick carrying (episodeId, serverTick). The client uses that
 * packet as the ONLY clock for binding a captured frame + action record to a
 * tick. Wall-clock timestamps are diagnostics, never the alignment key.
 */
public final class NetworkingIds {
    private NetworkingIds() {}

    public static final String NAMESPACE = "mineocclude";

    /** Server -> client: authoritative tick boundary (episodeId, serverTick, epochNanos). */
    public static final Identifier TICK_SYNC = new Identifier(NAMESPACE, "tick_sync");

    /** Server -> client: episode lifecycle (start/reset/end) so the client rotates output files. */
    public static final Identifier EPISODE_EVENT = new Identifier(NAMESPACE, "episode_event");
}
