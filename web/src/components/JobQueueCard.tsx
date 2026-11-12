import { isPacketPrepared } from "../lib/packetPrep";
import type { TodoItem } from "../types";
import { ApplicationProgressStepper } from "./ApplicationProgressStepper";
import { PacketPrepBadge } from "./PacketPrepBadge";
import { Button } from "./ui/Button";
import { SurfaceCard } from "./ui/Alert";

type JobQueueCardProps = {
  item: TodoItem;
  isExpanded: boolean;
  isSaving: boolean;
  showPrompt: boolean;
  onPrepare: () => void;
  onMarkApplied: () => void;
  onMoveBack: () => void;
  onArchive: () => void;
  onToggleExpand: () => void;
  onSelfReport: (didApply: boolean) => void;
  onStepsChange: (steps: import("../types").ApplicationStep[]) => void;
  stepsPanel: React.ReactNode;
};

export function JobQueueCard({
  item,
  isExpanded,
  isSaving,
  showPrompt,
  onPrepare,
  onMarkApplied,
  onMoveBack,
  onArchive,
  onToggleExpand,
  onSelfReport,
  stepsPanel,
}: JobQueueCardProps) {
  const stepsDone = item.steps_done ?? 0;
  const stepsTotal = item.steps_total ?? 0;

  return (
    <SurfaceCard className="transition hover:border-border">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            {item.match_score != null ? (
              <span className="rounded-full bg-accent-muted px-2 py-0.5 text-xs font-bold text-accent-strong">
                {item.match_score}% match
              </span>
            ) : null}
            <PacketPrepBadge status={item.packet_status ?? "none"} />
            <span className="rounded-full border border-border bg-surface-raised px-2 py-0.5 text-xs capitalize text-subtle">
              {item.status.replace(/_/g, " ")}
            </span>
          </div>
          <h2 className="font-semibold text-ink-text">{item.title}</h2>
          <p className="text-sm text-muted">
            {item.company} · {item.salary_display} · {item.location_display}
          </p>
          <div className="mt-3">
            <ApplicationProgressStepper
              stepsDone={stepsDone}
              stepsTotal={stepsTotal}
              compact
            />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {item.status === "to_apply" ? (
            <>
              <Button size="sm" onClick={onPrepare}>
                {isPacketPrepared(item.packet_status ?? "none")
                  ? "View application"
                  : "Prepare application"}
              </Button>
              <Button size="sm" variant="success" disabled={isSaving} onClick={onMarkApplied}>
                Mark applied
              </Button>
            </>
          ) : null}
          {item.status === "applied" ? (
            <Button size="sm" variant="secondary" disabled={isSaving} onClick={onMoveBack}>
              Move back to apply
            </Button>
          ) : null}
          {item.status !== "archived" ? (
            <Button size="sm" variant="ghost" onClick={onArchive}>
              Archive
            </Button>
          ) : null}
          <Button size="sm" variant="ghost" onClick={onToggleExpand}>
            {isExpanded ? "Hide steps" : "Track steps"}
          </Button>
        </div>
      </div>

      {showPrompt ? (
        <div className="mt-3 rounded-xl border border-accent/20 bg-accent-muted/30 p-3">
          <p className="text-sm font-semibold text-ink-text">Did you apply?</p>
          <div className="mt-2 flex gap-2">
            <Button size="sm" variant="success" onClick={() => onSelfReport(true)}>
              Yes, applied
            </Button>
            <Button size="sm" variant="secondary" onClick={() => onSelfReport(false)}>
              Not yet
            </Button>
          </div>
        </div>
      ) : null}

      {isExpanded ? (
        <div className="mt-4 border-t border-border pt-4">{stepsPanel}</div>
      ) : null}
    </SurfaceCard>
  );
}
