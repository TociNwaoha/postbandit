"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { PlaylistImport } from "@/types";

const ACTIVE_PARENT_STATUSES = new Set(["queued", "expanding", "importing"]);
const ACTIVE_IMPORT_STATES = new Set([
  "queued",
  "metadata_extracting",
  "downloadable",
  "downloading",
  "processing",
]);

export function useYoutubeImports() {
  const [imports, setImports] = useState<PlaylistImport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchImports = useCallback(async () => {
    try {
      const data = await api.get<PlaylistImport[]>("/api/videos/playlist-imports?limit=20&offset=0");
      setImports(data);
      setError(null);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to load playlist imports";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchImports();
  }, [fetchImports]);

  const hasActive = useMemo(
    () =>
      imports.some((item) => {
        if (ACTIVE_PARENT_STATUSES.has(item.status)) return true;
        return item.items.some((child) => {
          if (child.import_state) {
            return ACTIVE_IMPORT_STATES.has(child.import_state);
          }
          return ["queued", "downloading", "transcribing", "scoring"].includes(child.status);
        });
      }),
    [imports]
  );

  useEffect(() => {
    if (!hasActive) return;
    const timer = window.setInterval(() => {
      void fetchImports();
    }, 10_000);
    return () => window.clearInterval(timer);
  }, [fetchImports, hasActive]);

  const refresh = useCallback(async () => {
    setLoading(true);
    await fetchImports();
  }, [fetchImports]);

  return { imports, loading, error, refresh };
}
