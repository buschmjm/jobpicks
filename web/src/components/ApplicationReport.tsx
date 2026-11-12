import type { ApplicationPacket } from "../types";
import { Button } from "./ui/Button";
import { Alert, SurfaceCard } from "./ui/Alert";
import { FieldGroup, FieldTextarea } from "./ui/Field";

const FIT_LABELS: Record<NonNullable<ApplicationPacket["fit_verdict"]>, string> = {
  apply: "Apply",
  lean_apply: "Lean apply",
  lean_skip: "Lean skip",
  skip: "Skip",
};

function identityField(identity: Record<string, unknown>, ...keys: string[]): string {
  for (const key of keys) {
    const value = identity[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "—";
}

function fitTone(
  verdict: ApplicationPacket["fit_verdict"],
): "success" | "warning" | "info" | "error" {
  if (verdict === "apply") return "success";
  if (verdict === "lean_apply") return "info";
  if (verdict === "lean_skip") return "warning";
  if (verdict === "skip") return "error";
  return "info";
}

type ApplicationReportProps = {
  packet: ApplicationPacket;
  coverLetter: string;
  coverDisabled?: boolean;
  kitCopied?: boolean;
  onCopyKit: () => void;
  onCoverLetterChange: (value: string) => void;
  onCoverLetterBlur: () => void;
};

export function ApplicationReport({
  packet,
  coverLetter,
  coverDisabled,
  kitCopied,
  onCopyKit,
  onCoverLetterChange,
  onCoverLetterBlur,
}: ApplicationReportProps) {
  return (
    <div className="space-y-4">
      {packet.fit_verdict ? (
        <SurfaceCard>
          <p className="text-sm font-semibold text-ink-text">Fit summary</p>
          <Alert tone={fitTone(packet.fit_verdict)} className="mt-3">
            <span className="font-semibold">{FIT_LABELS[packet.fit_verdict]}</span>
            {packet.fit_rationale?.length ? (
              <ul className="mt-2 list-disc space-y-1 pl-5">
                {packet.fit_rationale.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : null}
          </Alert>
        </SurfaceCard>
      ) : null}

      <SurfaceCard>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm font-semibold text-ink-text">Contact</p>
          <Button size="sm" variant="secondary" onClick={onCopyKit}>
            {kitCopied ? "Copied kit" : "Copy cover letter"}
          </Button>
        </div>
        <dl className="mt-3 grid gap-3 sm:grid-cols-3">
          <div>
            <dt className="text-xs text-subtle">Name</dt>
            <dd className="mt-0.5 text-sm font-medium text-ink-text">
              {identityField(packet.identity, "preferred_name", "full_name", "name")}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-subtle">Email</dt>
            <dd className="mt-0.5 text-sm font-medium text-ink-text">
              {identityField(packet.identity, "email")}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-subtle">Phone</dt>
            <dd className="mt-0.5 text-sm font-medium text-ink-text">
              {identityField(packet.identity, "phone")}
            </dd>
          </div>
        </dl>
      </SurfaceCard>

      <SurfaceCard>
        <FieldGroup label="Cover letter">
          <FieldTextarea
            rows={14}
            value={coverLetter}
            disabled={coverDisabled}
            onChange={(event) => onCoverLetterChange(event.target.value)}
            onBlur={onCoverLetterBlur}
            placeholder="Your tailored cover letter will appear here once generation completes."
          />
        </FieldGroup>
      </SurfaceCard>
    </div>
  );
}
