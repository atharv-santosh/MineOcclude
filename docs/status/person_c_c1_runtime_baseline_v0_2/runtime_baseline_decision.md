# Person C isolated runtime baseline v0.2

This additive decision applies only to evidence newly produced by the completed v0.2 provisioning package. It does not rewrite the v0.1 provisioning block, environment-lock templates, developer observations, geometry records, homographies, or historical captures.

Fabric Loom is pinned to immutable version 1.4.6. The repository exposes named `mineoccludeServer` and `mineoccludeClient` Loom runs whose default directories are the two isolated non-Git runtime roots. Both use explicit 1–2 GiB JVM memory bounds; the client starts at 640 by 360.

The successor server baseline resolves `spawn-animals=false`. Natural mob spawning is also disabled. The only intended magenta sheep is created by the MineOcclude preview/reset system. This decision is prospective; whether the vanilla server retains that explicitly created sheep must be checked by the C1 runtime observation and must not be inferred from this document.

The server is loopback-only, offline, single-player, flat, peaceful, structure-free, fixed to world seed `202608030101`, noon, clear weather, and the committed gamerules. The client baseline is vanilla resources, windowed 640 by 360 launch size, 70-degree FOV, fancy graphics, render distance 10, GUI scale 2, entity shadows on, maximum ambient occlusion, VSync off, and deterministic performance settings.

No geometry owner or geometry version is accepted here. C1.1 observation remains required before scientific screenshots, trajectories, reconstruction, or C6A.
