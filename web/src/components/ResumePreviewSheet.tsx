import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { useResumePreviewHtml } from "../hooks/useResumePreviewHtml";
import { Alert } from "./ui/Alert";
import { Button } from "./ui/Button";
import { InlineSpinner } from "./ui/NavIcon";

type Props = {
  draftId: string;
  refreshKey?: number;
  onClose: () => void;
};

export function ResumePreviewSheet({ draftId, refreshKey = 0, onClose }: Props) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const { html, loading, error } = useResumePreviewHtml(draftId, refreshKey);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose]);

  function handlePrint() {
    const frame = iframeRef.current;
    if (!frame?.contentWindow) return;
    frame.contentWindow.focus();
    frame.contentWindow.print();
  }

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-end justify-center sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="resume-preview-title"
    >
      <button
        type="button"
        className="absolute inset-0 bg-ink-text/40 backdrop-blur-[2px]"
        aria-label="Close resume preview"
        onClick={onClose}
      />

      <div className="relative mx-auto flex h-[94dvh] w-full max-w-3xl min-h-0 flex-col overflow-hidden rounded-t-[var(--radius-card)] border border-border bg-surface shadow-[0_-12px_40px_rgba(15,23,42,0.18)] sm:h-auto sm:max-h-[min(92vh,900px)] sm:rounded-[var(--radius-card)] sm:shadow-[0_20px_50px_-12px_rgba(15,23,42,0.25)]">
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-border-subtle px-4 py-3 sm:px-5">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.06em] text-subtle">
              Resume preview
            </p>
            <h2 id="resume-preview-title" className="mt-0.5 text-base font-semibold text-ink-text">
              Letter-size preview
            </h2>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button
              type="button"
              size="sm"
              variant="secondary"
              disabled={loading || !html}
              onClick={handlePrint}
            >
              Print / Save PDF
            </Button>
            <button
              type="button"
              onClick={onClose}
              className="flex h-9 w-9 items-center justify-center rounded-full border border-border bg-surface-raised text-lg leading-none text-muted transition hover:border-muted hover:text-ink-text"
              aria-label="Close"
            >
              ×
            </button>
          </div>
        </div>

        <div
          className="min-h-0 flex-1 overflow-y-auto overscroll-contain bg-surface-raised/60 px-3 py-4 sm:px-6 sm:py-6"
          style={{ WebkitOverflowScrolling: "touch" }}
        >
          {loading ? (
            <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted">
              <InlineSpinner label="Loading preview" />
              Loading preview…
            </div>
          ) : null}

          {error ? (
            <div className="mx-auto max-w-md">
              <Alert tone="error">{error}</Alert>
            </div>
          ) : null}

          {html && !error ? (
            <div className="mx-auto w-full max-w-[8.5in]">
              <div
                className="mx-auto w-full max-w-[8.5in] overflow-hidden rounded-sm border border-border bg-white shadow-[0_8px_30px_rgba(15,23,42,0.12)]"
                style={{
                  aspectRatio: "8.5 / 11",
                  maxHeight: "min(75vh, 11in)",
                }}
              >
                <iframe
                  ref={iframeRef}
                  title="Resume preview"
                  srcDoc={html}
                  className="h-full w-full border-0 bg-white"
                  sandbox="allow-same-origin"
                />
              </div>
              <p className="mt-3 text-center text-xs text-muted">
                Scroll inside the page to review longer resumes. Use Print / Save PDF for export.
              </p>
            </div>
          ) : null}
        </div>
      </div>
    </div>,
    document.body,
  );
}
