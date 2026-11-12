import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { ApplicationReport } from "../components/ApplicationReport";
import { PacketPrepBadge } from "../components/PacketPrepBadge";
import { Alert, SurfaceCard } from "../components/ui/Alert";
import { Button } from "../components/ui/Button";
import { FieldInput } from "../components/ui/Field";
import { LoadingSpinner } from "../components/ui/NavIcon";
import { PageHeader } from "../components/ui/PageHeader";
import { copyText, formatApplicationKit } from "../lib/applicationKit";
import { canOpenApplication } from "../lib/packetPrep";
import type { ApplicationPacket } from "../types";

export function ApplicationReportPage() {
  const { packetId } = useParams<{ packetId: string }>();
  const [packet, setPacket] = useState<ApplicationPacket | null>(null);
  const [coverLetter, setCoverLetter] = useState("");
  const [labelDraft, setLabelDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savingCover, setSavingCover] = useState(false);
  const [savingLabel, setSavingLabel] = useState(false);
  const [kitCopied, setKitCopied] = useState(false);

  const applyPacket = useCallback((next: ApplicationPacket) => {
    setPacket(next);
    setCoverLetter(next.cover_letter ?? "");
    setLabelDraft(next.label || next.title || "");
  }, []);

  useEffect(() => {
    if (!packetId) return;
    setLoading(true);
    setError(null);
    api.todo
      .getPacketById(packetId)
      .then(applyPacket)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Failed to load application"),
      )
      .finally(() => setLoading(false));
  }, [applyPacket, packetId]);

  async function patchPacket(body: Parameters<typeof api.todo.patchPacketById>[1]) {
    if (!packetId) return null;
    const updated = await api.todo.patchPacketById(packetId, body);
    applyPacket(updated);
    return updated;
  }

  async function handleCoverLetterBlur() {
    if (!packet) return;
    if ((packet.cover_letter ?? "") === coverLetter) return;
    setSavingCover(true);
    setError(null);
    try {
      await patchPacket({ cover_letter: coverLetter || null });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save cover letter");
    } finally {
      setSavingCover(false);
    }
  }

  async function handleSaveLabel() {
    const next = labelDraft.trim();
    if (!next || next === (packet?.label || packet?.title || "")) return;
    setSavingLabel(true);
    setError(null);
    try {
      await patchPacket({ label: next });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to rename application");
    } finally {
      setSavingLabel(false);
    }
  }

  async function handleCopyKit() {
    if (!packet) return;
    try {
      await copyText(formatApplicationKit(packet, coverLetter));
      setKitCopied(true);
      window.setTimeout(() => setKitCopied(false), 2000);
    } catch {
      setError("Could not copy cover letter");
    }
  }

  const title = packet?.label || packet?.title || "Application";

  return (
    <div className="pb-8">
      <PageHeader
        title={title}
        subtitle={
          packet
            ? `${packet.title ?? "Role"} at ${packet.company ?? "company"} — reusable cover letter and fit summary.`
            : "Your generated application kit."
        }
        action={
          <Link
            to="/applications"
            className="shrink-0 text-sm font-semibold text-brand-strong hover:text-brand-deep"
          >
            ← All applications
          </Link>
        }
      />

      {error ? (
        <Alert tone="error" className="mt-4">
          {error}
        </Alert>
      ) : null}

      {loading ? (
        <div className="mt-10">
          <LoadingSpinner label="Loading application…" />
        </div>
      ) : null}

      {packet && !loading ? (
        <div className="mt-4 space-y-4">
          <SurfaceCard>
            <div className="flex flex-wrap items-center gap-2">
              <PacketPrepBadge status={packet.status} />
              {packet.todo_item_id ? (
                <Link
                  to={`/todo/${packet.todo_item_id}/prepare`}
                  className="text-sm font-semibold text-brand-strong hover:text-brand-deep"
                >
                  Prep this job →
                </Link>
              ) : null}
            </div>
            <p className="mt-3 text-sm text-muted">
              Rename this kit to keep versions separate (Office Manager, Sales Manager, etc.).
            </p>
            <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
              <FieldInput
                aria-label="Application name"
                value={labelDraft}
                onChange={(event) => setLabelDraft(event.target.value)}
                className="mt-0"
              />
              <Button
                size="sm"
                variant="secondary"
                disabled={savingLabel || !labelDraft.trim()}
                onClick={() => void handleSaveLabel()}
              >
                {savingLabel ? "Saving…" : "Save name"}
              </Button>
            </div>
          </SurfaceCard>

          <ApplicationReport
            packet={packet}
            coverLetter={coverLetter}
            coverDisabled={!canOpenApplication(packet) || savingCover}
            kitCopied={kitCopied}
            onCopyKit={() => void handleCopyKit()}
            onCoverLetterChange={setCoverLetter}
            onCoverLetterBlur={() => void handleCoverLetterBlur()}
          />
        </div>
      ) : null}
    </div>
  );
}
