import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { EngagementSummary } from "../types";

export function useEngagement(enabled = true) {
  const [engagement, setEngagement] = useState<EngagementSummary | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [newMilestones, setNewMilestones] = useState<string[]>([]);

  const refresh = useCallback(async () => {
    if (!enabled) return null;
    setLoading(true);
    try {
      const summary = await api.engagement.summary();
      setEngagement(summary);
      return summary;
    } catch {
      setEngagement(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, [enabled]);

  const heartbeat = useCallback(
    async (activityType = "session") => {
      if (!enabled) return null;
      try {
        const summary = await api.engagement.heartbeat(activityType);
        setEngagement(summary);
        if (summary.new_milestones?.length) {
          setNewMilestones(summary.new_milestones);
        }
        return summary;
      } catch {
        return null;
      }
    },
    [enabled],
  );

  useEffect(() => {
    void heartbeat("session");
  }, [heartbeat]);

  const clearMilestones = useCallback(() => setNewMilestones([]), []);

  return { engagement, loading, refresh, heartbeat, newMilestones, clearMilestones };
}
