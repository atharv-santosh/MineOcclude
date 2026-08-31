package com.mineocclude.server;

import net.minecraft.block.Block;
import net.minecraft.block.BlockState;
import net.minecraft.block.Blocks;
import net.minecraft.util.Identifier;
import net.minecraft.util.registry.Registry;

import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * The five frozen Experiment III conditions and the wall-material allowlist.
 *
 * <p>The material seam spans builder, config, command, arena cache key, receipt
 * and validator. The authority (§4.1) warns that they must change together or the
 * apparatus fails silently, so all of them resolve their material through this
 * one class rather than each hard-coding {@code Blocks.STONE}.
 *
 * <p>Two fail-closed properties are load-bearing:
 * <ul>
 *   <li>an unsupported registry ID <b>refuses the episode</b> instead of
 *       defaulting to stone;</li>
 *   <li>{@link #cacheKeyFragment()} is folded into the arena-rebuild cache key so
 *       a material transition always forces a rebuild. Without it a stone→glass
 *       switch hits the cache and leaves the previous wall standing, silently
 *       capturing a whole batch under the wrong condition.</li>
 * </ul>
 */
public final class WallCondition {

    /** L0 is the no-wall anchor; L4 the opaque anchor; L1–L3 are P0-selected. */
    public enum Id { L0, L1, L2, L3, L4 }

    public static final String AIR = "minecraft:air";
    public static final String STONE = "minecraft:stone";

    /** Authority §4.2 — exactly twelve eligible P0 stained-glass candidates. */
    public static final List<String> ELIGIBLE_STAINED_GLASS = Collections.unmodifiableList(
            Arrays.asList(
                    "minecraft:white_stained_glass",
                    "minecraft:orange_stained_glass",
                    "minecraft:light_blue_stained_glass",
                    "minecraft:yellow_stained_glass",
                    "minecraft:lime_stained_glass",
                    "minecraft:gray_stained_glass",
                    "minecraft:light_gray_stained_glass",
                    "minecraft:cyan_stained_glass",
                    "minecraft:blue_stained_glass",
                    "minecraft:brown_stained_glass",
                    "minecraft:green_stained_glass",
                    "minecraft:black_stained_glass"));

    /** Authority §4.3 — frozen exclusions, never eligible as a scientific level. */
    public static final Set<String> PROSPECTIVELY_EXCLUDED =
            Collections.unmodifiableSet(new HashSet<>(Arrays.asList(
                    "minecraft:magenta_stained_glass",
                    "minecraft:pink_stained_glass",
                    "minecraft:purple_stained_glass",
                    "minecraft:red_stained_glass",
                    "minecraft:glass",
                    "minecraft:glass_pane")));

    private static final Set<String> SUPPORTED;

    static {
        Set<String> supported = new HashSet<>(ELIGIBLE_STAINED_GLASS);
        supported.add(AIR);
        supported.add(STONE);
        SUPPORTED = Collections.unmodifiableSet(supported);
    }

    public final Id id;
    public final String wallBlockId;
    public final EpisodeConfig.Scene scene;

    private WallCondition(Id id, String wallBlockId, EpisodeConfig.Scene scene) {
        this.id = id;
        this.wallBlockId = wallBlockId;
        this.scene = scene;
    }

    /** Whether physical blocks stand in the original wall cells. */
    public boolean wallPresent() {
        return id != Id.L0;
    }

    /**
     * Resolve a condition, refusing an unsupported or excluded material.
     *
     * @throws IllegalArgumentException so the calling command refuses the episode
     *         rather than silently substituting stone.
     */
    public static WallCondition of(String conditionId, String wallBlockId) {
        Id id;
        try {
            id = Id.valueOf(conditionId.toUpperCase());
        } catch (IllegalArgumentException error) {
            throw new IllegalArgumentException(
                    "unknown condition '" + conditionId + "'; expected L0..L4");
        }
        if (wallBlockId == null || wallBlockId.indexOf(':') < 0) {
            throw new IllegalArgumentException(
                    "wall block must be a registry ID, got '" + wallBlockId + "'");
        }
        if (PROSPECTIVELY_EXCLUDED.contains(wallBlockId)) {
            throw new IllegalArgumentException(
                    wallBlockId + " is prospectively excluded by authority 4.3");
        }
        if (!SUPPORTED.contains(wallBlockId)) {
            throw new IllegalArgumentException(
                    wallBlockId + " is not a supported Experiment III wall material; "
                    + "refusing the episode rather than defaulting to stone");
        }
        if (id == Id.L0 && !AIR.equals(wallBlockId)) {
            throw new IllegalArgumentException("L0 is the no-wall anchor and must be " + AIR);
        }
        if (id == Id.L4 && !STONE.equals(wallBlockId)) {
            throw new IllegalArgumentException("L4 is the opaque anchor and must be " + STONE);
        }
        if ((id == Id.L1 || id == Id.L2 || id == Id.L3)
                && !ELIGIBLE_STAINED_GLASS.contains(wallBlockId)) {
            throw new IllegalArgumentException(
                    id + " must be a P0-selected stained glass from the twelve-candidate roster");
        }
        // The block must also exist in the live registry, so a typo that passes the
        // allowlist cannot reach the builder.
        if (!AIR.equals(wallBlockId) && resolveBlock(wallBlockId) == Blocks.AIR) {
            throw new IllegalArgumentException(
                    wallBlockId + " does not resolve to a block in this client's registry");
        }
        EpisodeConfig.Scene scene =
                id == Id.L0 ? EpisodeConfig.Scene.NO_WALL : EpisodeConfig.Scene.NORMAL;
        return new WallCondition(id, wallBlockId, scene);
    }

    /** The default condition for a legacy (non-Experiment-III) capture. */
    public static WallCondition legacyStone() {
        return new WallCondition(Id.L4, STONE, EpisodeConfig.Scene.NORMAL);
    }

    private static Block resolveBlock(String registryId) {
        return Registry.BLOCK.get(new Identifier(registryId));
    }

    /** The BlockState this condition places in the wall cells. */
    public BlockState wallState() {
        if (!wallPresent()) {
            return Blocks.AIR.getDefaultState();
        }
        return resolveBlock(wallBlockId).getDefaultState();
    }

    /** Folded into the arena-rebuild cache key so a material switch rebuilds. */
    public String cacheKeyFragment() {
        return id.name() + "|" + wallBlockId;
    }

    @Override
    public String toString() {
        return "WallCondition{" + id + "," + wallBlockId + "," + scene + "}";
    }
}
