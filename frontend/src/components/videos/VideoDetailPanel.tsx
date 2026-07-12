"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Card } from "@/components/ui/Card";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { api, ApiError } from "@/lib/api";
import { Clip, ClipProfile, Video, VideoGenerateClipsResponse, VideoTranscript } from "@/types";

type TabKey = "transcript" | "clips";

interface VideoDetailPanelProps {
  video: Video;
  transcript: VideoTranscript | null;
  transcriptError: string | null;
  clips: Clip[];
  clipsError: string | null;
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

const URL_IMPORT_SOURCE_TYPES = new Set(["youtube", "youtube_single", "youtube_playlist", "instagram", "facebook", "tiktok", "x", "twitch"]);
const BLOCKED_IMPORT_STATES = new Set([
  "blocked",
  "replacement_upload_required",
  "helper_required",
  "embed_only",
]);

function formatDuration(seconds: number | null): string {
  if (!seconds || seconds <= 0) return "Unknown";
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const remainderMinutes = minutes % 60;
  if (hours > 0) return `${hours}h ${remainderMinutes}m`;
  return `${minutes}m`;
}

function formatTimeBoundary(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds));
  const mins = Math.floor(safe / 60);
  const secs = safe % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

function formatClipDuration(seconds: number | null): string {
  if (!seconds || seconds <= 0) return "0s";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}m ${secs}s`;
}

function importStateLabel(state: string): string {
  return state
    .split(":")[0]
    .split("_")
    .filter(Boolean)
    .map((chunk) => chunk.charAt(0).toUpperCase() + chunk.slice(1))
    .join(" ");
}

export function VideoDetailPanel({ video, transcript, transcriptError, clips, clipsError }: VideoDetailPanelProps) {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<TabKey>("transcript");
  const [batchProfile, setBatchProfile] = useState<ClipProfile>(video.clip_profile || "viral");
  const [batchLoading, setBatchLoading] = useState(false);
  const [batchError, setBatchError] = useState<string | null>(null);
  const [batchMessage, setBatchMessage] = useState<string | null>(null);
  const [videoDisplayWidth, setVideoDisplayWidth] = useState(25);

  const transcriptText = useMemo(() => {
    if (!transcript) return "";
    return transcript.full_text || "";
  }, [transcript]);
  const isUrlImportSource = URL_IMPORT_SOURCE_TYPES.has(video.source_type);
  const effectiveImportState = isUrlImportSource ? video.import_state : null;
  const displayStateKey =
    isUrlImportSource && effectiveImportState && effectiveImportState !== "processing"
      ? effectiveImportState
      : video.status;
  const displayStateLabel =
    isUrlImportSource && effectiveImportState && effectiveImportState !== "processing"
      ? importStateLabel(effectiveImportState)
      : video.status.charAt(0).toUpperCase() + video.status.slice(1);
  const isBlockedImport =
    Boolean(video.is_download_blocked) ||
    Boolean(effectiveImportState && BLOCKED_IMPORT_STATES.has(effectiveImportState));
  const canGenerateByStatus = !["queued", "downloading", "transcribing"].includes(video.status);
  const canGenerateByMedia = Boolean(video.storage_key);
  const generationDisabled = batchLoading || !canGenerateByStatus || !canGenerateByMedia;
  const selectedBatchLabel = batchProfile === "sermon" ? "Long-form Speaking" : "Viral";

  useEffect(() => {
    setBatchProfile(video.clip_profile || "viral");
    setVideoDisplayWidth(25);
    setBatchError(null);
    setBatchMessage(null);
  }, [video.id, video.clip_profile]);

  const handleGenerateBatch = async () => {
    if (generationDisabled) return;
    setBatchLoading(true);
    setBatchError(null);
    setBatchMessage(null);
    try {
      const payload = await api.post<VideoGenerateClipsResponse>(`/api/videos/${video.id}/generate-clips`, {
        clip_profile: batchProfile,
      });
      setBatchMessage(payload.message);
      router.refresh();
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to start clip generation";
      setBatchError(message);
    } finally {
      setBatchLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="text-xl font-semibold text-[var(--app-text)]">{video.title || "Untitled Video"}</h2>
            <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${statusStyles[displayStateKey] || statusStyles.queued}`}>
              {displayStateLabel}
            </span>
          </div>
          {video.source_download_url || video.embed_url ? (
            <label className="flex min-w-[210px] items-center gap-3 text-xs text-[var(--app-muted)]">
              <span className="whitespace-nowrap">Video size</span>
              <input
                type="range"
                min="25"
                max="100"
                step="5"
                value={videoDisplayWidth}
                onChange={(event) => setVideoDisplayWidth(Number(event.target.value))}
                className="h-2 min-w-0 flex-1 cursor-pointer accent-[#1D3FD0]"
                aria-label="Video player size"
              />
              <span className="w-9 text-right font-medium text-[var(--app-text)]">{videoDisplayWidth}%</span>
            </label>
          ) : null}
        </div>
        <div className="mt-4 flex flex-wrap gap-6 text-sm text-[var(--app-muted)]">
          <p>
            <span className="text-[var(--app-subtle)]">Duration:</span> {formatDuration(video.duration_sec)}
          </p>
          <p>
            <span className="text-[var(--app-subtle)]">Clip profile:</span> {video.clip_profile === "sermon" ? "Long-form Speaking" : "Viral"}
          </p>
          <p>
            <span className="text-[var(--app-subtle)]">Resolution:</span> {video.resolution || "Unknown"}
          </p>
          {isUrlImportSource ? (
            <p>
              <span className="text-[var(--app-subtle)]">Import mode:</span>{" "}
              {video.import_mode === "embed_only"
                ? "Embed only"
                : video.import_mode === "manual_upload"
                ? "Manual upload"
                : "Server download"}
            </p>
          ) : null}
        </div>
        {isBlockedImport ? (
          <p className="mt-3 text-xs text-amber-700">
            Server download was blocked for this source. You can keep it as embed reference or upload file manually.
          </p>
        ) : null}
      </Card>

      {video.source_download_url ? (
        <Card>
          <div className="flex justify-center">
            <div
              className="max-w-full transition-[width] duration-200"
              style={{ width: `clamp(280px, ${videoDisplayWidth}%, 100%)` }}
            >
              <video
                className="block h-auto w-full rounded-lg border border-[var(--app-border)] bg-black"
                controls
                playsInline
                preload="metadata"
                src={video.source_download_url}
              >
                Your browser does not support the video tag.
              </video>
            </div>
          </div>
        </Card>
      ) : video.embed_url ? (
        <Card>
          <div className="flex justify-center">
            <div
              className="aspect-video max-w-full overflow-hidden rounded-lg border border-[var(--app-border)] bg-black transition-[width] duration-200"
              style={{ width: `clamp(280px, ${videoDisplayWidth}%, 100%)` }}
            >
              <iframe
                src={video.embed_url}
                title={video.title || "YouTube embed"}
                className="h-full w-full"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
              />
            </div>
          </div>
        </Card>
      ) : null}

      <Card>
        <div className="mb-4 inline-flex rounded-lg bg-[var(--app-surface-soft)] p-1">
          <button
            className={`rounded-md px-4 py-2 text-sm transition-colors ${
              activeTab === "transcript" ? "bg-[#1D3FD0] text-white" : "text-[var(--app-muted)] hover:text-[var(--app-text)]"
            }`}
            onClick={() => setActiveTab("transcript")}
          >
            Transcript
          </button>
          <button
            className={`rounded-md px-4 py-2 text-sm transition-colors ${
              activeTab === "clips" ? "bg-[#1D3FD0] text-white" : "text-[var(--app-muted)] hover:text-[var(--app-text)]"
            }`}
            onClick={() => setActiveTab("clips")}
          >
            Clips
          </button>
        </div>

        {activeTab === "clips" ? (
          <div className="mb-4 rounded-lg border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h4 className="text-sm font-semibold text-[var(--app-text)]">Generate New Clip Batch</h4>
                <p className="mt-1 text-xs text-[var(--app-muted)]">
                  Regenerate clips using a different profile. Existing clips for this video will be replaced when scoring completes.
                </p>
              </div>
              <span className="rounded-full border border-[var(--app-border)] px-2 py-1 text-[11px] text-[var(--app-muted)]">
                Selected: {selectedBatchLabel}
              </span>
            </div>

            <div className="mt-3 flex flex-wrap items-end gap-3">
              <label className="text-xs text-[var(--app-muted)]">
                Clip profile
                <select
                  value={batchProfile}
                  onChange={(event) => setBatchProfile(event.target.value as ClipProfile)}
                  className="mt-1 block min-w-[220px] rounded-md border border-[var(--app-border)] bg-[var(--app-surface-soft)] px-3 py-2 text-sm text-[var(--app-text)] focus:border-[#1D3FD0] focus:outline-none"
                >
                  <option value="viral">Viral</option>
                  <option value="sermon">Long-form Speaking</option>
                </select>
              </label>
              <button
                type="button"
                onClick={() => void handleGenerateBatch()}
                disabled={generationDisabled}
                className="rounded-md bg-[#1D3FD0] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#1633B8] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {batchLoading ? "Starting..." : "Generate New Clip Batch"}
              </button>
            </div>

            {!canGenerateByMedia ? (
              <p className="mt-2 text-xs text-amber-700">
                Source media is unavailable for this video, so clip regeneration is currently disabled.
              </p>
            ) : null}
            {!canGenerateByStatus ? (
              <p className="mt-2 text-xs text-[var(--app-muted)]">
                Clip regeneration is available after ingest/transcription completes.
              </p>
            ) : null}
            {batchError ? <p className="mt-2 text-xs text-red-700">{batchError}</p> : null}
            {batchMessage ? <p className="mt-2 text-xs text-emerald-700">{batchMessage}</p> : null}
          </div>
        ) : null}

        {activeTab === "clips" && video.status === "scoring" && clips.length === 0 ? (
          <div className="flex items-center gap-3 rounded-lg border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-6 text-[var(--app-text)]">
            <LoadingSpinner />
            <p>Scoring clips... This usually completes shortly after transcription.</p>
          </div>
        ) : null}

        {activeTab === "clips" && clipsError ? (
          <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-700">
            {clipsError}
          </div>
        ) : null}

        {activeTab === "clips" && !clipsError && video.status === "ready" && clips.length === 0 ? (
          <div className="rounded-lg border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-6 text-[var(--app-muted)]">
            No strong clips found for this video yet.
          </div>
        ) : null}

        {activeTab === "clips" &&
        !clipsError &&
        clips.length === 0 &&
        ["queued", "downloading", "transcribing"].includes(video.status) ? (
          <div className="rounded-lg border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-6 text-[var(--app-muted)]">
            Clips will appear after processing reaches scoring.
          </div>
        ) : null}

        {activeTab === "clips" && !clipsError && clips.length > 0 ? (
          <div className="space-y-4">
            {clips.map((clip, index) => (
              <div key={clip.id} className="rounded-lg border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-4">
                <div className="flex gap-4">
                  {clip.thumbnail_url ? (
                    <img
                      src={clip.thumbnail_url}
                      alt={`Clip ${index + 1} thumbnail`}
                      className="h-24 w-40 rounded-md border border-[var(--app-border)] object-cover"
                    />
                  ) : (
                    <div className="h-24 w-40 rounded-md border border-[var(--app-border)] bg-[var(--app-surface-soft)]/80" />
                  )}

                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-3">
                      <h4 className="text-sm font-semibold text-[var(--app-text)]">{clip.title || `Clip ${index + 1}`}</h4>
                      <span className="rounded-full bg-purple-500/20 px-2.5 py-1 text-xs text-purple-700">
                        Score {(clip.score ?? 0).toFixed(2)}
                      </span>
                    </div>

                    <div className="mt-2 flex flex-wrap gap-3 text-xs text-[var(--app-muted)]">
                      <span>{formatClipDuration(clip.duration_sec)}</span>
                      <span>
                        {formatTimeBoundary(clip.start_time)} - {formatTimeBoundary(clip.end_time)}
                      </span>
                      <span>Hook {(clip.hook_score ?? 0).toFixed(2)}</span>
                      <span>Energy {(clip.energy_score ?? 0).toFixed(2)}</span>
                    </div>

                    <p className="mt-3 line-clamp-3 text-sm text-[var(--app-muted)]">
                      {clip.transcript_text || "Transcript excerpt unavailable."}
                    </p>

                    <div className="mt-4">
                      <Link
                        href={`/videos/${video.id}/clips/${clip.id}`}
                        className="inline-flex items-center rounded-md bg-[#1D3FD0] px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-[#1633B8]"
                      >
                        Review & Export
                      </Link>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : null}

        {activeTab === "transcript" && video.status === "transcribing" ? (
          <div className="flex items-center gap-3 rounded-lg border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-6 text-[var(--app-text)]">
            <LoadingSpinner />
            <p>Transcribing your video... This takes about 6 minutes per hour of content</p>
          </div>
        ) : null}

        {activeTab === "transcript" && video.status === "error" ? (
          <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-700">
            {video.error_message || "This video failed during processing."}
          </div>
        ) : null}

        {activeTab === "transcript" && (video.status === "scoring" || video.status === "ready") ? (
          transcript ? (
            <div className="space-y-4">
              <div className="flex flex-wrap gap-4 text-xs text-[var(--app-muted)]">
                <p>Words: {transcript.word_count}</p>
                <p>Language: {transcript.language || "Unknown"}</p>
              </div>
              <div className="max-h-[28rem] overflow-auto whitespace-pre-wrap rounded-lg border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-4 text-sm leading-7 text-[var(--app-text)]">
                {transcriptText || "Transcript text is empty."}
              </div>
            </div>
          ) : (
            <div className="rounded-lg border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-6 text-[var(--app-muted)]">
              {transcriptError || "Transcript not ready yet"}
            </div>
          )
        ) : null}
      </Card>
    </div>
  );
}
