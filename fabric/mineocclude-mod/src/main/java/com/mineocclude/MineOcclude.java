package com.mineocclude;

import net.fabricmc.api.ModInitializer;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

/**
 * Common entrypoint. Runs on both the dedicated server and the client JVMs.
 *
 * Deliberately minimal: it only holds shared constants and logging. All
 * server-side dynamics live in {@code com.mineocclude.server}; all capture
 * lives in {@code com.mineocclude.client}. Channel identifiers are shared via
 * {@code com.mineocclude.net.NetworkingIds}.
 */
public class MineOcclude implements ModInitializer {
    public static final String MOD_ID = "mineocclude";
    public static final Logger LOG = LogManager.getLogger(MOD_ID);

    /** Fixed model-facing tick rate. 20 Hz => dt = 0.05 s. Never change per run. */
    public static final int TICK_HZ = 20;
    public static final double DT_SECONDS = 1.0 / TICK_HZ;

    @Override
    public void onInitialize() {
        LOG.info("[MineOcclude] common init: tick={}Hz dt={}s", TICK_HZ, DT_SECONDS);
    }
}
