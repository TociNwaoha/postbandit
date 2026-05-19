"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { VideoListItem } from "@/types";

interface BlockedImportActionsProps {
  video: VideoListItem;
  onActionDone: () => Promise<void> | void;
}

interface ManualUploadUrlResponse {
  video_id: string;
  upload_url: string;
  upload_fields: Record<string, string>;
  storage_key: string;
  use_local: boolean;
}

interface LocalHelperSessionResponse {
  video_id: string;
  helper_session_token: string;
  upload_url: string;
  upload_fields: Record<string, string>;
  upload_key: string;
  use_local: boolean;
  source_url: string;
  complete_url: string;
  expires_at: string;
}

const ACCEPTED_TYPES = new Set([
  "video/mp4",
  "video/quicktime",
  "video/x-msvideo",
  "video/x-matroska",
]);
const NON_RETRYABLE_RETRY_CODES = new Set([
  "YT_SIGNIN_REQUIRED",
  "YT_BOT_VERIFICATION",
  "YT_PO_TOKEN_REQUIRED",
  "YT_NO_FORMATS",
]);

function shellQuote(value: string): string {
  return `'${value.replace(/'/g, `'\"'\"'`)}'`;
}

function buildLocalHelperCommand(payload: LocalHelperSessionResponse): string {
  return [
    "python3 tools/youtube_local_helper.py",
    `--source-url ${shellQuote(payload.source_url)}`,
    `--upload-url ${shellQuote(payload.upload_url)}`,
    `--complete-url ${shellQuote(payload.complete_url)}`,
    `--session-token ${shellQuote(payload.helper_session_token)}`,
    `--upload-key ${shellQuote(payload.upload_key)}`,
    `--upload-fields-json ${shellQuote(JSON.stringify(payload.upload_fields || {}))}`,
    `--use-local ${payload.use_local ? "true" : "false"}`,
  ].join(" ");
}

function buildLocalHelperLauncher(payload: LocalHelperSessionResponse): string {
  const command = buildLocalHelperCommand(payload);
  return [
    "#!/usr/bin/env bash",
    "set -euo pipefail",
    "",
    "if ! command -v python3 >/dev/null 2>&1; then",
    "  echo 'python3 is required.' >&2",
    "  exit 1",
    "fi",
    "if ! command -v yt-dlp >/dev/null 2>&1; then",
    "  echo 'yt-dlp is required. Install it first: https://github.com/yt-dlp/yt-dlp#installation' >&2",
    "  exit 1",
    "fi",
    "if ! command -v curl >/dev/null 2>&1; then",
    "  echo 'curl is required.' >&2",
    "  exit 1",
    "fi",
    "",
    "if [ ! -f tools/youtube_local_helper.py ]; then",
    "  echo 'Run this launcher from your PostBandit repo root where tools/youtube_local_helper.py exists.' >&2",
    "  echo 'CLI fallback command:' >&2",
    `  echo ${shellQuote(command)} >&2`,
    "  exit 1",
    "fi",
    "",
    command,
    "",
  ].join("\n");
}

function formatTimeRemaining(expiresAtIso: string, nowMs: number): string {
  const expiresAtMs = new Date(expiresAtIso).getTime();
  const remainingMs = expiresAtMs - nowMs;
  if (!Number.isFinite(expiresAtMs)) {
    return "unknown";
  }
  if (remainingMs <= 0) {
    return "expired";
  }
  const totalSeconds = Math.ceil(remainingMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}m ${seconds}s`;
}

async function uploadWithXhr(upload: ManualUploadUrlResponse, file: File): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", upload.upload_url);

    xhr.onerror = () => reject(new Error("Upload failed"));
    xhr.onabort = () => reject(new Error("Upload canceled"));
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve();
      } else {
        reject(new Error(`Upload failed with status ${xhr.status}`));
      }
    };

    const formData = new FormData();
    if (upload.use_local) {
      formData.append("key", upload.storage_key);
      formData.append("file", file);
    } else {
      Object.entries(upload.upload_fields || {}).forEach(([field, value]) => {
        formData.append(field, value);
      });
      if (!upload.upload_fields?.key) {
        formData.append("key", upload.storage_key);
      }
      formData.append("file", file);
    }
    xhr.send(formData);
  });
}

export function BlockedImportActions({ video, onActionDone }: BlockedImportActionsProps) {
  const [busyAction, setBusyAction] = useState<"retry" | "keep" | "upload" | "helper" | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [helperSession, setHelperSession] = useState<LocalHelperSessionResponse | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [nowMs, setNowMs] = useState<number>(Date.now());

  useEffect(() => {
    if (!helperSession) {
      return;
    }
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [helperSession]);

  const helperCommand = useMemo(
    () => (helperSession ? buildLocalHelperCommand(helperSession) : null),
    [helperSession]
  );
  const helperLauncher = useMemo(
    () => (helperSession ? buildLocalHelperLauncher(helperSession) : null),
    [helperSession]
  );
  const helperTimeRemaining = useMemo(
    () => (helperSession ? formatTimeRemaining(helperSession.expires_at, nowMs) : null),
    [helperSession, nowMs]
  );
  const canRetry = !video.error_code || !NON_RETRYABLE_RETRY_CODES.has(video.error_code);

  const setError = (err: unknown, fallback: string) => {
    const text = err instanceof ApiError ? err.message : err instanceof Error ? err.message : fallback;
    setMessage(text);
  };

  const handleRetry = async () => {
    if (busyAction) return;
    setBusyAction("retry");
    setMessage(null);
    setHelperSession(null);
    try {
      await api.post(`/api/videos/${video.id}/retry-import`, {});
      setMessage("Retry started.");
      await onActionDone();
    } catch (err) {
      setError(err, "Failed to retry import.");
    } finally {
      setBusyAction(null);
    }
  };

  const handleKeepEmbed = async () => {
    if (busyAction) return;
    setBusyAction("keep");
    setMessage(null);
    setHelperSession(null);
    try {
      await api.post(`/api/videos/${video.id}/keep-embed`, {});
      setMessage("Saved as embed-only item.");
      await onActionDone();
    } catch (err) {
      setError(err, "Failed to keep as embed.");
    } finally {
      setBusyAction(null);
    }
  };

  const onPickFile = () => {
    fileInputRef.current?.click();
  };

  const handleUploadFile = async (file: File | null) => {
    if (!file || busyAction) return;
    if (file.type && !ACCEPTED_TYPES.has(file.type)) {
      setMessage("Unsupported file type.");
      return;
    }

    setBusyAction("upload");
    setMessage(null);
    setHelperSession(null);
    try {
      const upload = await api.post<ManualUploadUrlResponse>(`/api/videos/${video.id}/manual-upload-url`, {
        filename: file.name,
        file_size: file.size,
        content_type: file.type || "video/mp4",
      });
      await uploadWithXhr(upload, file);
      await api.post(`/api/videos/${video.id}/manual-upload-confirm`, {});
      setMessage("Manual upload confirmed. Processing started.");
      await onActionDone();
    } catch (err) {
      setError(err, "Manual upload failed.");
    } finally {
      setBusyAction(null);
    }
  };

  const handleUseLocalHelper = async () => {
    if (busyAction) return;
    setBusyAction("helper");
    setMessage(null);
    try {
      const payload = await api.post<LocalHelperSessionResponse>("/api/videos/local-helper/session", {
        video_id: video.id,
      });
      setHelperSession(payload);
      setMessage("Local helper session created.");
    } catch (err) {
      setError(err, "Failed to create local helper session.");
    } finally {
      setBusyAction(null);
    }
  };

  const copyHelperCommand = async () => {
    if (!helperCommand) return;
    try {
      await navigator.clipboard.writeText(helperCommand);
      setMessage("Local helper command copied.");
    } catch {
      setMessage("Could not copy automatically. Select and copy the command manually.");
    }
  };

  const downloadHelperLauncher = () => {
    if (!helperLauncher) {
      return;
    }
    const blob = new Blob([helperLauncher], { type: "text/x-shellscript" });
    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = `postbandit-local-helper-${video.id.slice(0, 8)}.sh`;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(objectUrl);
    setMessage("Helper launcher downloaded. Run it on your machine before it expires.");
  };

  return (
    <div className="mt-3 space-y-2">
      <p className="text-xs text-[var(--app-muted)]">
        Why this happens: some YouTube videos block server downloads from datacenter IPs. You can still recover this row
        by uploading a replacement file or running the helper on your machine.
      </p>
      <div className="flex flex-wrap gap-2">
        <Button type="button" onClick={onPickFile} disabled={busyAction !== null} className="text-xs px-3 py-1.5">
          {busyAction === "upload" ? "Uploading..." : "Upload replacement file"}
        </Button>
        {canRetry ? (
          <Button
            type="button"
            variant="secondary"
            onClick={handleRetry}
            disabled={busyAction !== null}
            className="text-xs px-3 py-1.5"
          >
            {busyAction === "retry" ? "Retrying..." : "Retry"}
          </Button>
        ) : null}
        <Button
          type="button"
          variant="secondary"
          onClick={handleKeepEmbed}
          disabled={busyAction !== null}
          className="text-xs px-3 py-1.5"
        >
          {busyAction === "keep" ? "Saving..." : "Keep as embed"}
        </Button>
        <Button
          type="button"
          variant="secondary"
          onClick={handleUseLocalHelper}
          disabled={busyAction !== null}
          className="text-xs px-3 py-1.5"
        >
          {busyAction === "helper" ? "Creating..." : "Use Local Helper"}
        </Button>
      </div>
      {!canRetry ? (
        <p className="text-[11px] text-[var(--app-muted)]">
          Retry is disabled for this blocked error. Use upload replacement, embed-only, or local helper.
        </p>
      ) : null}
      {helperSession ? (
        <div className="rounded-md border border-[var(--app-border)]/80 bg-[var(--app-surface-soft)] p-3 space-y-2">
          <p className="text-xs text-[var(--app-text)]">Runs on your machine; server block remains unchanged.</p>
          <p className="text-[11px] text-[var(--app-muted)]">
            Session expires: {new Date(helperSession.expires_at).toLocaleString()} ({helperTimeRemaining || "unknown"}).
          </p>
          <div className="space-y-1 text-[11px] text-[var(--app-muted)]">
            <p>1. Download helper launcher.</p>
            <p>2. Run the launcher on your machine.</p>
            <p>3. Return here and refresh; this row should resume processing.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" onClick={downloadHelperLauncher} variant="primary" className="text-xs px-3 py-1.5">
              Download helper launcher
            </Button>
            <Button type="button" onClick={copyHelperCommand} variant="ghost" className="text-xs px-3 py-1.5">
              Copy CLI fallback
            </Button>
          </div>
          <details className="rounded-md border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-2">
            <summary className="cursor-pointer text-[11px] text-[var(--app-muted)]">Advanced: show raw command</summary>
            <textarea
              readOnly
              value={helperCommand || ""}
              className="mt-2 h-20 w-full rounded-md border border-[var(--app-border)] bg-white px-2 py-1 text-[11px] text-[var(--app-text)]"
            />
          </details>
          <Button
            type="button"
            onClick={handleUseLocalHelper}
            variant="ghost"
            disabled={busyAction !== null}
            className="text-xs px-3 py-1.5"
          >
            Create new helper session
          </Button>
        </div>
      ) : null}
      <input
        ref={fileInputRef}
        type="file"
        accept="video/mp4,video/quicktime,video/x-msvideo,video/x-matroska"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0] || null;
          void handleUploadFile(file);
          event.currentTarget.value = "";
        }}
      />
      {message ? <p className="text-xs text-[var(--app-muted)]">{message}</p> : null}
    </div>
  );
}
