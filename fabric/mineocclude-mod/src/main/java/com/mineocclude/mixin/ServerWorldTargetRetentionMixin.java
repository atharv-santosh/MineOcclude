package com.mineocclude.mixin;

import com.mineocclude.server.TargetRetentionPolicy;
import net.minecraft.entity.Entity;
import net.minecraft.server.world.ServerWorld;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;

/**
 * Exempts only the tagged MineOcclude sheep from Minecraft 1.16.5's broad
 * spawn-animals=false removal call. Natural animals still execute remove().
 */
@Mixin(ServerWorld.class)
public abstract class ServerWorldTargetRetentionMixin {
    @Redirect(
            method = "tick(Ljava/util/function/BooleanSupplier;)V",
            at = @At(
                    value = "INVOKE",
                    target = "Lnet/minecraft/entity/Entity;remove()V",
                    ordinal = 0))
    private void mineocclude$preserveTaggedExperimentTarget(Entity entity) {
        if (!TargetRetentionPolicy.suppressVanillaAnimalRemoval(entity)) {
            entity.remove();
        }
    }
}
