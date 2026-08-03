package com.mineocclude.net;

import net.fabricmc.fabric.api.networking.v1.PacketByteBufs;
import net.minecraft.network.PacketByteBuf;

/**
 * Episode lifecycle signal so the client knows when to open/close output files.
 *
 * Layout: [int protocolVersion][int typeOrdinal][long episodeId][String layoutId][int pairingShift]
 *
 * pairingShift is the session-calibrated action-pairing offset (see
 * MineOccludeClient): the client pairs the action sampled at capture k to
 * frame index k - 1 + pairingShift. It is calibrated per connection by a
 * scripted-impulse fixture because the client/server tick phase (set at
 * connect time) shifts the sub-tick attribution by +/-1 between sessions.
 *
 * The protocol version is validated on read (C2.6).
 */
public final class EpisodeEventPacket {
    /** Bump on ANY wire-format or semantic change. */
    public static final int PROTOCOL_VERSION = 2;

    public enum Type { START, END }

    public final Type type;
    public final long episodeId;
    public final String layoutId;
    public final int pairingShift;

    public EpisodeEventPacket(Type type, long episodeId, String layoutId, int pairingShift) {
        this.type = type;
        this.episodeId = episodeId;
        this.layoutId = layoutId;
        this.pairingShift = pairingShift;
    }

    public PacketByteBuf write() {
        PacketByteBuf buf = PacketByteBufs.create();
        buf.writeInt(PROTOCOL_VERSION);
        buf.writeInt(type.ordinal());
        buf.writeLong(episodeId);
        buf.writeString(layoutId == null ? "" : layoutId);
        buf.writeInt(pairingShift);
        return buf;
    }

    /** @throws IllegalStateException on a protocol-version mismatch. */
    public static EpisodeEventPacket read(PacketByteBuf buf) {
        int version = buf.readInt();
        if (version != PROTOCOL_VERSION) {
            throw new IllegalStateException("episode_event protocol mismatch: peer sent "
                    + version + ", this build requires " + PROTOCOL_VERSION);
        }
        Type t = Type.values()[buf.readInt()];
        long ep = buf.readLong();
        String layout = buf.readString();
        int shift = buf.readInt();
        return new EpisodeEventPacket(t, ep, layout, shift);
    }
}
