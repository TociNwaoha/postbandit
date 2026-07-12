"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { VideoListItem } from "@/types";

const ACTIVE_STATUSES = new Set(["queued", "downloading", "transcribing", "scoring"]);
const ACTIVE_IMPORT_STATES = new Set([
  "queued",
  "metadata_extracting",
  "downloadable",
  "downloading",
  "processing",
]);

const URL_IMPORT_SOURCE_TYPES = new Set(["youtube", "youtube_single", "youtube_playlist", "instagram", "facebook", "tiktok", "x", "twitch"]);

export function useVideos() {
  const [videos, setVideos] = useState<VideoListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchVideos = useCallback(async () => {
    try {
      const data = await api.get<VideoListItem[]>("/api/videos?limit=20&offset=0");
      setVideos(data);
      setError(null);
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.status === 401 || err.status === 403
            ? "Session expired, please log in again."
            : err.message
          : "Failed to load videos";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchVideos();
  }, [fetchVideos]);

  const hasActiveVideos = useMemo(
    () =>
      videos.some((video) => {
        if (URL_IMPORT_SOURCE_TYPES.has(video.source_type) && video.import_state) {
          return ACTIVE_IMPORT_STATES.has(video.import_state);
        }
        return ACTIVE_STATUSES.has(video.status);
      }),
    [videos]
  );

  useEffect(() => {
    if (!hasActiveVideos) return;
    const timer = window.setInterval(() => {
      void fetchVideos();
    }, 10_000);
    return () => window.clearInterval(timer);
  }, [fetchVideos, hasActiveVideos]);

  const refresh = useCallback(async () => {
    setLoading(true);
    await fetchVideos();
  }, [fetchVideos]);

  return { videos, loading, error, refresh };
}
