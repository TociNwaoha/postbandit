"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { BlockedImportActions } from "@/components/videos/BlockedImportActions";
import { getPlatformBrandMeta } from "@/components/connections/platformBrand";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { FullVideoExportResponse, VideoListItem } from "@/types";

interface VideoListProps {
  videos: VideoListItem[];
  loading: boolean;
  error: string | null;
  onRefresh: () => Promise<void> | void;
  onOpenUpload: () => void;
}

const statusStyles: Record<string, string> = {
  queued: "border border-[var(--app-border)] bg-[var(--app-surface-soft)] text-[var(--app-subtle)]",
  downloading: "bg-blue-500/20 text-blue-700 animate-pulse",
  transcribing: "bg-blue-500/20 text-blue-700 animate-pulse",
  scoring: "bg-purple-500/20 text-purple-700 animate-pulse",
  ready: "bg-emerald-500/20 text-emerald-700",
  error: "bg-red-500/20 text-red-700",
  metadata_extracting: "bg-blue-500/20 text-blue-700 animate-pulse",
  downloadable: "bg-blue-500/20 text-blue-700 animate-pulse",
  blocked: "bg-amber-500/20 text-amber-700",
  replacement_upload_required: "bg-amber-500/20 text-amber-700",
  helper_required: "bg-amber-500/20 text-amber-700",
  embed_only: "border border-[var(--app-border)] bg-[var(--app-surface-soft)] text-[var(--app-subtle)]",
  failed_retryable: "bg-red-500/20 text-red-700",
  failed_terminal: "bg-red-500/20 text-red-700",
};

const YOUTUBE_SOURCE_TYPES = new Set(["youtube", "youtube_single", "youtube_playlist"]);
const URL_IMPORT_SOURCE_TYPES = new Set(["youtube", "youtube_single", "youtube_playlist", "instagram", "facebook", "tiktok", "x", "twitch"]);
const BLOCKED_IMPORT_STATES = new Set([
  "blocked",
  "replacement_upload_required",
  "helper_required",
  "embed_only",
]);

function formatDuration(seconds: number | null): string | null {
  if (!seconds || seconds <= 0) return null;
  const totalMinutes = Math.max(1, Math.round(seconds / 60));
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function formatRelativeTime(isoDate: string): string {
  const now = Date.now();
  const then = new Date(isoDate).getTime();
  const deltaSec = Math.round((then - now) / 1000);

  const units: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ["year", 60 * 60 * 24 * 365],
    ["month", 60 * 60 * 24 * 30],
    ["day", 60 * 60 * 24],
    ["hour", 60 * 60],
    ["minute", 60],
  ];

  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  for (const [unit, unitSeconds] of units) {
    if (Math.abs(deltaSec) >= unitSeconds) {
      return rtf.format(Math.round(deltaSec / unitSeconds), unit);
    }
  }
  return "just now";
}

function statusLabel(status: string): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function importStateLabel(state: string): string {
  return state
    .split(":")[0]
    .split("_")
    .filter(Boolean)
    .map((chunk) => chunk.charAt(0).toUpperCase() + chunk.slice(1))
    .join(" ");
}

function displayStateKey(video: VideoListItem): string {
  if (!URL_IMPORT_SOURCE_TYPES.has(video.source_type) || !video.import_state) {
    return video.status;
  }
  if (video.import_state === "processing") {
    return video.status;
  }
  return video.import_state;
}

function displayStateLabel(video: VideoListItem): string {
  if (!URL_IMPORT_SOURCE_TYPES.has(video.source_type) || !video.import_state) {
    return statusLabel(video.status);
  }
  if (video.import_state === "processing") {
    return statusLabel(video.status);
  }
  return importStateLabel(video.import_state);
}

function sourcePlatformKey(video: VideoListItem): string | null {
  if (YOUTUBE_SOURCE_TYPES.has(video.source_type)) return "youtube";
  if (["instagram", "facebook", "tiktok", "x", "twitch"].includes(video.source_type)) return video.source_type;
  return null;
}

export function VideoList({ videos, loading, error, onRefresh, onOpenUpload }: VideoListProps) {
  const router = useRouter();
  const [menuVideoId, setMenuVideoId] = useState<string | null>(null);
  const [deletingVideoId, setDeletingVideoId] = useState<string | null>(null);
  const [preparingVideoId, setPreparingVideoId] = useState<string | null>(null);
  const [failedThumbnailUrls, setFailedThumbnailUrls] = useState<Record<string, boolean>>({});
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const sortedVideos = useMemo(
    () => [...videos].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()),
    [videos]
  );

  const handleDeleteVideo = async (videoId: string) => {
    if (deletingVideoId) return;
    setDeletingVideoId(videoId);
    setDeleteError(null);
    setActionMessage(null);
    try {
      await api.delete(`/api/videos/${videoId}`);
      await onRefresh();
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to delete video";
      setDeleteError(message);
    } finally {
      setDeletingVideoId(null);
      setMenuVideoId(null);
    }
  };

  const handlePrepareFullExport = async (videoId: string) => {
    if (preparingVideoId) return;
    setPreparingVideoId(videoId);
    setDeleteError(null);
    setActionMessage(null);
    try {
      const payload = await api.post<FullVideoExportResponse>(`/api/social/videos/${videoId}/full-export`, {});
      setActionMessage(
        payload.reused_existing_export
          ? "Reused existing full export and opened clip editor."
          : "Prepared full export and opened clip editor."
      );
      router.push(`/videos/${videoId}/clips/${payload.clip_id}`);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to prepare full export";
      setDeleteError(message);
    } finally {
      setPreparingVideoId(null);
    }
  };

  if (loading) {
    return (
      <Card className="min-h-72 flex items-center justify-center">
        <div className="flex items-center gap-3 text-[var(--app-muted)]">
          <LoadingSpinner />
          Loading videos...
        </div>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="min-h-72 flex flex-col items-center justify-center text-center">
        <p className="text-red-700">{error}</p>
        <Button onClick={() => void onRefresh()} className="mt-4">
          Retry
        </Button>
      </Card>
    );
  }

  if (!sortedVideos.length) {
    return (
      <Card className="min-h-80 flex flex-col items-center justify-center text-center">
        <p className="text-2xl font-semibold text-[var(--app-text)]">No videos yet</p>
        <p className="mt-2 text-[var(--app-muted)]">Upload a video or import from YouTube to get started</p>
        <Button className="mt-6" onClick={onOpenUpload}>
          Get Started
        </Button>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {actionMessage && <p className="text-sm text-emerald-700">{actionMessage}</p>}
      {deleteError && <p className="text-sm text-red-700">{deleteError}</p>}
      {sortedVideos.map((video) => {
        const thumbnailUrl = video.thumbnail_url;
        const showThumbnail = Boolean(thumbnailUrl && !failedThumbnailUrls[thumbnailUrl]);
        const stateKey = displayStateKey(video);
        const stateLabel = displayStateLabel(video);
        const platformKey = sourcePlatformKey(video);
        const platformMeta = platformKey ? getPlatformBrandMeta(platformKey) : null;
        const showBlockedActions =
          Boolean(video.is_download_blocked) || Boolean(video.import_state && BLOCKED_IMPORT_STATES.has(video.import_state));
        const showErrorText =
          (video.status === "error" ||
            video.import_state === "failed_retryable" ||
            video.import_state === "failed_terminal") &&
          Boolean(video.error_message);

        return (
        <Card key={video.id} className="relative">
          <div className="flex items-start gap-4">
            <Link href={`/videos/${video.id}`} className="flex min-w-0 flex-1 items-start gap-4 group">
              {showThumbnail ? (
                <img
                  src={thumbnailUrl!}
                  alt={video.title ? `${video.title} thumbnail` : "Video thumbnail"}
                  className="h-20 w-36 rounded-lg border border-[var(--app-border)] object-cover flex-shrink-0 bg-[var(--app-surface-soft)] group-hover:border-[#1D3FD0]/70 transition-colors"
                  onError={() => {
                    if (!thumbnailUrl) return;
                    setFailedThumbnailUrls((previous) =>
                      previous[thumbnailUrl] ? previous : { ...previous, [thumbnailUrl]: true }
                    );
                  }}
                />
              ) : (
                <div className="h-20 w-36 rounded-lg bg-[var(--app-surface-soft)] border border-[var(--app-border)] flex-shrink-0 group-hover:border-[#1D3FD0]/70 transition-colors" />
              )}
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <h3 className="truncate text-base font-semibold text-[var(--app-text)] group-hover:text-[#1D3FD0] transition-colors">
                    {video.title || "Untitled video"}
                  </h3>
                  <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${statusStyles[stateKey] || statusStyles.queued}`}>
                    {stateLabel}
                  </span>
                  {platformMeta ? (
                    <span
                      className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-[11px] font-semibold ${platformMeta.badgeClassName}`}
                      title={`Imported from ${platformMeta.displayName}`}
                    >
                      <span className="[&>svg]:h-3.5 [&>svg]:w-3.5">{platformMeta.icon}</span>
                      {platformMeta.displayName}
                    </span>
                  ) : null}
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-[var(--app-muted)]">
                  {formatDuration(video.duration_sec) && <span>{formatDuration(video.duration_sec)}</span>}
                  {video.clip_count > 0 && <span>{video.clip_count} clips</span>}
                  <span>Profile: {video.clip_profile === "sermon" ? "Long-form Speaking" : "Viral"}</span>
                  <span>{formatRelativeTime(video.created_at)}</span>
                  {video.source_type === "youtube_playlist" && video.playlist_index !== null ? (
                    <span>Playlist item #{(video.playlist_index || 0) + 1}</span>
                  ) : null}
                </div>
                {showBlockedActions ? (
                  <div className="mt-2 flex flex-wrap gap-2">
                    <span className="rounded bg-amber-500/20 px-2 py-0.5 text-[11px] text-amber-700">
                      Blocked on server
                    </span>
                    <span className="rounded bg-blue-500/20 px-2 py-0.5 text-[11px] text-blue-700">
                      Can still embed
                    </span>
                    <span className="rounded bg-[var(--app-surface-soft)] px-2 py-0.5 text-[11px] text-[var(--app-text)]">
                      Upload file manually
                    </span>
                  </div>
                ) : null}
                {showErrorText ? (
                  <p className="mt-2 text-xs text-red-700">{video.error_message}</p>
                ) : null}
              </div>
            </Link>

            <div className="flex flex-col items-end gap-2">
              {video.status === "ready" ? (
                <button
                  type="button"
                  onClick={() => void handlePrepareFullExport(video.id)}
                  disabled={preparingVideoId === video.id}
                  className="rounded-md border border-[#1D3FD0]/40 bg-[#1D3FD0]/10 px-3 py-1.5 text-xs font-medium text-[#1633B8] hover:bg-[#1D3FD0]/20 disabled:opacity-50"
                >
                  {preparingVideoId === video.id ? "Preparing..." : "Prepare Full Export"}
                </button>
              ) : null}
              <div className="relative">
                <button
                  className="rounded-lg p-2 text-[var(--app-muted)] hover:bg-[var(--app-surface-soft)] hover:text-[var(--app-text)] transition-colors"
                  onClick={() => setMenuVideoId(menuVideoId === video.id ? null : video.id)}
                  aria-label="More options"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                    <circle cx="5" cy="12" r="1.8" fill="currentColor" />
                    <circle cx="12" cy="12" r="1.8" fill="currentColor" />
                    <circle cx="19" cy="12" r="1.8" fill="currentColor" />
                  </svg>
                </button>
                {menuVideoId === video.id && (
                  <div className="absolute right-0 mt-1 w-28 rounded-lg border border-[var(--app-border)] bg-[var(--app-bg)] p-1 shadow-xl">
                    <button
                      className="w-full rounded-md px-3 py-2 text-left text-sm text-red-700 hover:bg-red-500/10 disabled:opacity-50"
                      onClick={() => void handleDeleteVideo(video.id)}
                      disabled={deletingVideoId === video.id}
                    >
                      {deletingVideoId === video.id ? "Deleting..." : "Delete"}
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
          {showBlockedActions ? (
            <BlockedImportActions video={video} onActionDone={onRefresh} />
          ) : null}
        </Card>
      );
      })}
    </div>
  );
}
