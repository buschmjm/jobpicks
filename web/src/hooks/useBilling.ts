import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { BillingStatus } from "../types";

export function useBilling(enabled = true) {
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState(false);

  const refresh = useCallback(async () => {
    if (!enabled) return null;
    setLoading(true);
    setError(false);
    try {
      const status = await api.billing.status();
      setBilling(status);
      return status;
    } catch {
      setError(true);
      setBilling(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, [enabled]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { billing, loading, error, refresh };
}
