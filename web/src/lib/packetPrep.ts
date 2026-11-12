import type { ApplicationPacket, TodoItem } from "../types";

export type PacketPrepStatus = TodoItem["packet_status"];

export function isPacketPrepared(status: PacketPrepStatus | ApplicationPacket["status"]): boolean {
  return status === "ready" || status === "opened" || status === "applied";
}

export function packetPrepLabel(status: PacketPrepStatus): string {
  switch (status) {
    case "generating":
      return "Preparing…";
    case "ready":
    case "opened":
    case "applied":
      return "Prepared";
    case "failed":
      return "Prep failed";
    default:
      return "Not prepared";
  }
}

export function packetActionLabel(
  packet: ApplicationPacket | null,
  busy: boolean,
): string {
  if (busy) {
    return packet && isPacketPrepared(packet.status) ? "Regenerating…" : "Generating…";
  }
  if (!packet) return "Generate application packet";
  if (packet.status === "failed") return "Retry generation";
  if (packet.status === "generating") return "Generating…";
  if (isPacketPrepared(packet.status)) return "Regenerate packet";
  return "Generate application packet";
}

export function canOpenApplication(packet: ApplicationPacket | null): boolean {
  return Boolean(packet && isPacketPrepared(packet.status));
}
