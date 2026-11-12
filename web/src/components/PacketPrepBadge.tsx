import type { PacketPrepStatus } from "../lib/packetPrep";
import { isPacketPrepared, packetPrepLabel } from "../lib/packetPrep";

type PacketPrepBadgeProps = {
  status: PacketPrepStatus;
  className?: string;
};

export function PacketPrepBadge({ status, className = "" }: PacketPrepBadgeProps) {
  const prepared = isPacketPrepared(status);
  const failed = status === "failed";
  const pending = status === "generating";

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${
        prepared
          ? "bg-success-muted text-success"
          : pending
            ? "bg-accent-muted text-accent-strong"
            : failed
              ? "bg-danger-muted text-danger"
              : "border border-border bg-surface-raised text-subtle"
      } ${className}`}
    >
      {pending ? (
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" aria-hidden />
      ) : prepared ? (
        <span aria-hidden>✓</span>
      ) : null}
      {packetPrepLabel(status)}
    </span>
  );
}
