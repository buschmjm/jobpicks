import { useRef } from "react";
import { useResumePreviewHtml } from "../hooks/useResumePreviewHtml";
import { Alert } from "./ui/Alert";
import { Button } from "./ui/Button";
import { InlineSpinner } from "./ui/NavIcon";

type Props = {
  draftId: string | null;
  refreshKey?: number;
};

export function ResumeLivePreview({ draftId, refreshKey = 0 }: Props) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const { html, loading, error } = useResumePreviewHtml(draftId, refreshKey);

  function handlePrint() {
    const frame = iframeRef.current;
    if (!frame?.contentWindow) return;
    frame.contentWindow.focus();
    frame.contentWindow.print();
  }

  if (!draftId) {
    return (
      <div className="flex h-full min-h-[16rem] items-center justify-center rounded-[var(--radius-card)] border border-dashed border-border bg-surface-raised/40 p-6 text-center text-sm text-muted">
        Select a resume variant to preview your draft.
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-[var(--radius-card)] border border-border bg-surface">
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-border-subtle px-3 py-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-subtle">Live preview</p>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          disabled={loading || !html}
          onClick={handlePrint}
        >
          Print / Save PDF
        </Button>
      </div>
      <div className="relative min-h-0 flex-1 overflow-hidden bg-white">
        {loading ? (
          <div className="absolute inset-0 flex items-center justify-center gap-2 bg-surface text-sm text-muted">
            <InlineSpinner label="Loading preview" />
            Updating preview…
          </div>
        ) : null}
        {error ? (
          <div className="p-3">
            <Alert tone="error">{error}</Alert>
          </div>
        ) : null}
        {html && !error ? (
          <iframe
            ref={iframeRef}
            title="Resume preview"
            srcDoc={html}
            className="h-full w-full border-0 bg-white"
            sandbox="allow-same-origin"
          />
        ) : null}
      </div>
    </div>
  );
}
