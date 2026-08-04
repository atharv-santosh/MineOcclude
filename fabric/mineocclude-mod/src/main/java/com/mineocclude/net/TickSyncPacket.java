package com.mineocclude.net;

import net.fabricmc.fabric.api.networking.v1.PacketByteBufs;
import net.minecraft.network.PacketByteBuf;

/**
 * Wire format for the authoritative tick-sync packet.
 *
 * Layout: [int protocolVersion][long episodeId][long serverTick][long serverEpochNanos]
 *
 * The protocol version is validated on read (C2.6): a mismatched client is
 * an explicit failure, never a silently misinterpreted stream.
 * serverEpochNanos is a DIAGNOSTIC only. Alignment is defined by
 * (episodeId, serverTick, renderFrameIdx, actionIdx) in downstream joins.
 */
public final class TickSyncPacket {
    /** Bump on ANY wire-format or semantic change. */
    public static final int PROTOCOL_VERSION = 1;

    public final long episodeId;
    public final long serverTick;
    public final long serverEpochNanos;

    public TickSyncPacket(long episodeId, long serverTick, long serverEpochNanos) {
        this.episodeId = episodeId;
        this.serverTick = serverTick;
        this.serverEpochNanos = serverEpochNanos;
    }

    public PacketByteBuf write() {
        PacketByteBuf buf = PacketByteBufs.create();
        buf.writeInt(PROTOCOL_VERSION);
        buf.writeLong(episodeId);
        buf.writeLong(serverTick);
        buf.writeLong(serverEpochNanos);
        return buf;
    }

    /** @throws IllegalStateException on a protocol-version mismatch. */
    public static TickSyncPacket read(PacketByteBuf buf) {
        int version = buf.readInt();
        if (version != PROTOCOL_VERSION) {
            throw new IllegalStateException("tick_sync protocol mismatch: peer sent "
                    + version + ", this build requires " + PROTOCOL_VERSION);
        }
        long ep = buf.readLong();
        long tick = buf.readLong();
        long nanos = buf.readLong();
        return new TickSyncPacket(ep, tick, nanos);
    }
}
