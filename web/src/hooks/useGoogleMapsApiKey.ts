import { useEffect, useState } from "react";
import { api } from "../api/client";

let cachedKey: string | null | undefined;

export function useGoogleMapsApiKey(): string | null {
  const [apiKey, setApiKey] = useState<string | null>(() =>
    cachedKey === undefined ? null : cachedKey,
  );

  useEffect(() => {
    if (cachedKey !== undefined) {
      setApiKey(cachedKey);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const config = await api.config.client();
        cachedKey = config.google_maps_api_key ?? null;
      } catch {
        cachedKey = null;
      }
      if (!cancelled) {
        setApiKey(cachedKey ?? null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return apiKey;
}
