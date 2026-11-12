import { useEffect, useState } from "react";
import { api } from "../api/client";
import { descriptionLooksTruncated } from "../lib/formatJobDescription";

export function useJobDescription(jobId: string, initialText: string) {
  const [description, setDescription] = useState(initialText);
  const [truncated, setTruncated] = useState(descriptionLooksTruncated(initialText));
  const [loading, setLoading] = useState(descriptionLooksTruncated(initialText));

  useEffect(() => {
    setDescription(initialText);
    const shouldFetch = descriptionLooksTruncated(initialText);
    setTruncated(shouldFetch);
    setLoading(shouldFetch);
    if (!shouldFetch) {
      return;
    }

    let cancelled = false;
    void (async () => {
      try {
        const res = await api.jobs.description(jobId);
        if (cancelled) return;
        setDescription(res.description);
        setTruncated(res.truncated);
      } catch {
        if (!cancelled) {
          setTruncated(descriptionLooksTruncated(initialText));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [initialText, jobId]);

  return { description, truncated, loading };
}
