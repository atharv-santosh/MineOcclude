package com.mineocclude.client;

import net.minecraft.client.MinecraftClient;
import net.minecraft.client.option.GameOptions;

/**
 * Samples one complete raw keyboard/mouse action for the current tick, including
 * no-op. These raw fields are what Python later feeds through the pinned
 * MCDataset.json_action_to_env_action / get_action_index_from_actiondict path
 * to produce MineWorld's 11-token action. We deliberately record RAW state here
 * and normalize in Python, so the conversion is auditable.
 *
 * Camera dx/dy are the per-tick yaw/pitch deltas (degrees), mapping to
 * MineWorld's camera yaw (dx) and pitch (dy) tokens.
 */
public final class ActionSampler {

    public static final class Action {
        public boolean forward, back, left, right;
        public boolean jump, sneak, sprint;
        public boolean use, attack, drop, pickItem;
        public int hotbar;       // 0..8 selected slot
        public double cameraDx;  // yaw delta, degrees
        public double cameraDy;  // pitch delta, degrees
    }

    private float prevYaw = Float.NaN;
    private float prevPitch = Float.NaN;

    /** Reset deltas at episode start so the first frame has dx=dy=0. */
    public void resetCamera() {
        prevYaw = Float.NaN;
        prevPitch = Float.NaN;
    }

    public Action sample(MinecraftClient client) {
        Action a = new Action();
        GameOptions o = client.options;
        if (o != null) {
            a.forward  = o.keyForward.isPressed();
            a.back     = o.keyBack.isPressed();
            a.left     = o.keyLeft.isPressed();
            a.right    = o.keyRight.isPressed();
            a.jump     = o.keyJump.isPressed();
            a.sneak    = o.keySneak.isPressed();
            a.sprint   = o.keySprint.isPressed();
            a.use      = o.keyUse.isPressed();
            a.attack   = o.keyAttack.isPressed();
            a.drop     = o.keyDrop.isPressed();
            a.pickItem = o.keyPickItem.isPressed();
        }

        if (client.player != null) {
            a.hotbar = client.player.inventory.selectedSlot;
            // 1.16.5: yaw/pitch are public fields (getYaw/getPitch arrive in 1.17).
            float yaw = client.player.yaw;
            float pitch = client.player.pitch;
            if (!Float.isNaN(prevYaw)) {
                a.cameraDx = wrapDegrees(yaw - prevYaw);
                a.cameraDy = pitch - prevPitch;
            } else {
                a.cameraDx = 0.0;
                a.cameraDy = 0.0;
            }
            prevYaw = yaw;
            prevPitch = pitch;
        }
        return a;
    }

    private static double wrapDegrees(double d) {
        d %= 360.0;
        if (d >= 180.0) d -= 360.0;
        if (d < -180.0) d += 360.0;
        return d;
    }
}
