package com.mineocclude.net;

import net.fabricmc.fabric.api.networking.v1.PacketByteBufs;
import net.minecraft.network.PacketByteBuf;

/**
 * Wire format for the client -> server capture acknowledgement.
 *
 * Layout: [int protocolVersion][long episodeId][long serverTick]
 *
 * This packet is the back-pressure signal that makes a captured frame
 * correspond to the tick it is joined to. The server broadcasts TICK_SYNC for
 * tick N and then STALLS the recorded episode until this acknowledgement for
 * tick N arrives, so the world cannot advance past the state the client just
 * photographed.
 *
 * Without it the server free-ran at 20 Hz while the client consumed exactly one
 * queued tick per client tick, so any backlog was permanent: the screenshot was
 * current but the state row it was joined to was arbitrarily old (observed at
 * roughly 1,067 ms, about twenty-one ticks).
 */
public final class CaptureAckPacket {
    /** Bump on ANY wire-format or semantic change. */
    public static final int PROTOCOL_VERSION = 1;

    public final long episodeId;
    public final long serverTick;

    public CaptureAckPacket(long episodeId, long serverTick) {
        this.episodeId = episodeId;
        this.serverTick = serverTick;
    }

    public PacketByteBuf write() {
        PacketByteBuf buf = PacketByteBufs.create();
        buf.writeInt(PROTOCOL_VERSION);
        buf.writeLong(episodeId);
        buf.writeLong(serverTick);
        return buf;
    }

    /** @throws IllegalStateException on a protocol-version mismatch. */
    public static CaptureAckPacket read(PacketByteBuf buf) {
        int version = buf.readInt();
        if (version != PROTOCOL_VERSION) {
            throw new IllegalStateException("capture_ack protocol mismatch: peer sent "
                    + version + ", this build requires " + PROTOCOL_VERSION);
        }
        long episodeId = buf.readLong();
        long serverTick = buf.readLong();
        return new CaptureAckPacket(episodeId, serverTick);
    }
}
