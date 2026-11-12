import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import { prepareResumePreviewHtml } from "../lib/resumePreviewHtml";

export function useResumePreviewHtml(draftId: string | null, refreshKey = 0) {
  const [html, setHtml] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!draftId) {
      setHtml(null);
      setError(null);
      return;
    }
    let cancelled = false;
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        const next = await api.resume.fetchHtml(draftId);
        if (!cancelled) setHtml(prepareResumePreviewHtml(next));
      } catch (err) {
        if (!cancelled) {
          setHtml(null);
          setError(err instanceof ApiError ? err.message : "Failed to load resume preview");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [draftId, refreshKey]);

  return { html, loading, error };
}
