"use client";

import { useMemo, useRef, useState } from "react";
import { getSession } from "next-auth/react";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { ClipProfile, YouTubeImportResponse } from "@/types";

type UploadTab = "upload" | "youtube";

interface UploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  onUploaded: () => Promise<void> | void;
}

interface UploadUrlResponse {
  video_id: string;
  upload_url: string;
  upload_fields: Record<string, string>;
  storage_key: string;
  use_local: boolean;
}

interface VideoStatusResponse {
  video_id: string;
  status: "queued" | "downloading" | "transcribing" | "scoring" | "ready" | "error";
  error_message?: string | null;
}

const MAX_UPLOAD_BYTES = 5_368_709_120;
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const CONFIRM_RETRY_DELAYS_MS = [1000, 2000, 3000, 5000, 8000, 10000, 10000];
const PROCESSING_STARTED_STATUSES = new Set(["downloading", "transcribing", "scoring", "ready"]);
const ACCEPTED_TYPES = new Set([
  "video/mp4",
  "video/quicktime",
  "video/x-msvideo",
  "video/x-matroska",
]);
const ACCEPTED_EXTENSIONS = new Set([".mp4", ".mov", ".avi", ".mkv"]);

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes;
  let unitIndex = -1;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[unitIndex]}`;
}

function isSupportedImportUrl(value: string): boolean {
  try {
    const parsed = new URL(value);
    if (!["http:", "https:"].includes(parsed.protocol)) return false;
    const host = parsed.hostname.toLowerCase().replace(/^www\./, "");
    const parts = parsed.pathname.split("/").filter(Boolean);
    if (host === "youtube.com" || host === "youtu.be" || host.endsWith(".youtube.com")) return true;
    if (host === "instagram.com" || host.endsWith(".instagram.com")) {
      return parts.length >= 2 && ["reel", "p", "tv"].includes(parts[0]);
    }
    if (host === "tiktok.com" || host === "vm.tiktok.com" || host.endsWith(".tiktok.com")) {
      return (parts.length >= 3 && parts[0].startsWith("@") && parts[1] === "video") || (parts.length >= 2 && parts[0] === "t") || (host === "vm.tiktok.com" && parts.length >= 1);
    }
    if (host === "facebook.com" || host.endsWith(".facebook.com") || host === "fb.watch") {
      return Boolean(parsed.searchParams.get("v")) || parts.includes("videos") || (parts[0] === "share" && parts[1] === "v") || (host === "fb.watch" && parts.length >= 1);
    }
    if (host === "x.com" || host === "twitter.com" || host.endsWith(".twitter.com")) {
      return parts.length >= 3 && parts[1] === "status";
    }
    if (host === "twitch.tv" || host.endsWith(".twitch.tv") || host === "clips.twitch.tv") {
      return (parts.length >= 2 && parts[0] === "videos") || (parts.length >= 3 && parts[1] === "clip") || (host === "clips.twitch.tv" && parts.length >= 1);
    }
    return false;
  } catch {
    return false;
  }
}

function uploadWithXhr(upload: UploadUrlResponse, file: File, onProgress: (percent: number) => void) {
  return new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", upload.upload_url);

    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return;
      const percent = Math.min(100, Math.round((event.loaded / event.total) * 100));
      onProgress(percent);
    };

    xhr.onerror = () => reject(new Error("Upload failed. Please try again."));
    xhr.onabort = () => reject(new Error("Upload canceled"));
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress(100);
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

async function authHeaders(): Promise<Record<string, string>> {
  const session = await getSession();
  const token = (session as any)?.accessToken;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function proxyUploadWithXhr(
  upload: UploadUrlResponse,
  file: File,
  onProgress: (percent: number) => void,
  endpoint = `${API_URL}/api/videos/proxy-upload`
) {
  return authHeaders().then((headers) => new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", endpoint);

    Object.entries(headers).forEach(([key, value]) => xhr.setRequestHeader(key, value));

    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return;
      const percent = Math.min(100, Math.round((event.loaded / event.total) * 100));
      onProgress(percent);
    };

    xhr.onerror = () => reject(new Error("Upload failed. Please try again."));
    xhr.onabort = () => reject(new Error("Upload canceled"));
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress(100);
        resolve();
        return;
      }

      let message = `Upload failed with status ${xhr.status}`;
      try {
        const payload = JSON.parse(xhr.responseText || "{}");
        if (payload?.detail) {
          message = typeof payload.detail === "string" ? payload.detail : payload.detail.message || message;
        }
      } catch {
        // keep status-based message
      }
      reject(new Error(message));
    };

    const formData = new FormData();
    formData.append("video_id", upload.video_id);
    formData.append("file", file);
    xhr.send(formData);
  }));
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function fetchVideoStatus(videoId: string): Promise<VideoStatusResponse | null> {
  try {
    return await api.get<VideoStatusResponse>(`/api/videos/${videoId}/status`);
  } catch {
    return null;
  }
}

async function confirmUploadWithRetry(
  videoId: string,
  maxAttempts = CONFIRM_RETRY_DELAYS_MS.length + 1
): Promise<void> {
  let attempt = 0;
  let lastError: unknown = null;

  while (attempt < maxAttempts) {
    try {
      await api.post("/api/videos/confirm-upload", { video_id: videoId });
      return;
    } catch (err) {
      lastError = err;
      const status = await fetchVideoStatus(videoId);
      if (status?.status && PROCESSING_STARTED_STATUSES.has(status.status)) {
        return;
      }
      if (status?.status === "error") {
        throw new Error(status.error_message || "Video processing failed");
      }
      attempt += 1;
      if (attempt >= maxAttempts) break;
      const delay = CONFIRM_RETRY_DELAYS_MS[Math.min(attempt - 1, CONFIRM_RETRY_DELAYS_MS.length - 1)];
      await sleep(delay);
    }
  }

  throw lastError ?? new Error("Upload confirmation failed");
}

export function UploadModal({ isOpen, onClose, onUploaded }: UploadModalProps) {
  const [activeTab, setActiveTab] = useState<UploadTab>("upload");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadPhase, setUploadPhase] = useState<"idle" | "preparing" | "uploading" | "fallback" | "finalizing">("idle");
  const [pendingConfirmVideoId, setPendingConfirmVideoId] = useState<string | null>(null);
  const [confirmingUpload, setConfirmingUpload] = useState(false);
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [recoveryMessage, setRecoveryMessage] = useState<string | null>(null);
  const [clipProfile, setClipProfile] = useState<ClipProfile>("viral");

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const busy = uploading || importing || confirmingUpload;

  const youtubeValid = useMemo(() => youtubeUrl.trim() === "" || isSupportedImportUrl(youtubeUrl.trim()), [youtubeUrl]);

  if (!isOpen) return null;

  const resetState = () => {
    setSelectedFile(null);
    setUploadProgress(0);
    setUploadPhase("idle");
    setUploading(false);
    setConfirmingUpload(false);
    setImporting(false);
    setPendingConfirmVideoId(null);
    setYoutubeUrl("");
    setError(null);
    setSuccessMessage(null);
    setRecoveryMessage(null);
    setClipProfile("viral");
    setIsDragging(false);
    setActiveTab("upload");
  };

  const closeModal = () => {
    if (busy) return;
    resetState();
    onClose();
  };

  const validateFile = (file: File): string | null => {
    if (file.size > MAX_UPLOAD_BYTES) return "File exceeds 5GB limit";
    if (file.type && !ACCEPTED_TYPES.has(file.type)) return "Unsupported file type";
    if (!file.type) {
      const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
      if (!ACCEPTED_EXTENSIONS.has(ext)) return "Unsupported file type";
    }
    return null;
  };

  const handleFileSelection = (file: File | null) => {
    if (!file) return;
    const validationError = validateFile(file);
    if (validationError) {
      setError(validationError);
      setSelectedFile(null);
      return;
    }
    setError(null);
    setSuccessMessage(null);
    setSelectedFile(file);
  };

  const startUpload = async () => {
    if (!selectedFile || uploading) return;
    setError(null);
    setSuccessMessage(null);
    setUploading(true);
    setUploadPhase("preparing");
    setUploadProgress(0);
    let uploadedVideoId: string | null = null;
    let uploadTransferred = false;

    try {
      const upload = await api.post<UploadUrlResponse>("/api/videos/upload-url", {
        filename: selectedFile.name,
        file_size: selectedFile.size,
        content_type: selectedFile.type || "video/mp4",
        clip_profile: clipProfile,
      });
      uploadedVideoId = upload.video_id;

      setUploadPhase("uploading");
      if (upload.use_local) {
        try {
          await proxyUploadWithXhr(upload, selectedFile, setUploadProgress);
        } catch (proxyError) {
          if (API_URL) {
            await proxyUploadWithXhr(upload, selectedFile, setUploadProgress, "/api/backend/videos/proxy-upload");
          } else {
            throw proxyError;
          }
        }
      } else {
        try {
          await uploadWithXhr(upload, selectedFile, setUploadProgress);
        } catch (directUploadError) {
          console.warn("[direct_upload_failed_using_proxy]", {
            videoId: upload.video_id,
            error: directUploadError,
          });
          setUploadProgress(0);
          setUploadPhase("fallback");
          setSuccessMessage("Direct upload was interrupted. Finishing through PostBandit...");
          try {
            await proxyUploadWithXhr(upload, selectedFile, setUploadProgress);
          } catch (proxyError) {
            if (API_URL) {
              await proxyUploadWithXhr(upload, selectedFile, setUploadProgress, "/api/backend/videos/proxy-upload");
            } else {
              throw proxyError;
            }
          }
        }
      }
      uploadTransferred = true;
      setUploadPhase("finalizing");
      setPendingConfirmVideoId(upload.video_id);
      await confirmUploadWithRetry(upload.video_id);
      setPendingConfirmVideoId(null);

      setSuccessMessage("Video uploaded! Processing...");
      await onUploaded();
      window.setTimeout(() => {
        closeModal();
      }, 2000);
    } catch (err) {
      if (uploadTransferred && uploadedVideoId) {
        console.warn("[upload_confirm_failed]", { videoId: uploadedVideoId, error: err });
        setPendingConfirmVideoId(uploadedVideoId);
        setSuccessMessage("File upload completed.");
        setError("Upload finished, but processing has not started yet. Keep this popup open and retry confirmation.");
      } else {
        const message = err instanceof ApiError ? err.message : err instanceof Error ? err.message : "Upload failed";
        setError(message);
      }
    } finally {
      setUploading(false);
      setUploadPhase("idle");
    }
  };

  const retryConfirmUpload = async () => {
    if (!pendingConfirmVideoId || confirmingUpload) return;
    setConfirmingUpload(true);
    setError(null);
    try {
      await confirmUploadWithRetry(pendingConfirmVideoId, 3);
      setPendingConfirmVideoId(null);
      setSuccessMessage("Upload confirmed! Processing...");
      await onUploaded();
      window.setTimeout(() => {
        closeModal();
      }, 1500);
    } catch (err) {
      console.warn("[upload_confirm_failed]", { videoId: pendingConfirmVideoId, error: err });
      const message = err instanceof ApiError ? err.message : err instanceof Error ? err.message : "Upload confirmation failed";
      setError(`Upload finished, but processing has not started yet. Retry confirmation. (${message})`);
    } finally {
      setConfirmingUpload(false);
    }
  };

  const importYoutube = async () => {
    if (importing) return;
    const normalized = youtubeUrl.trim();
    if (!isSupportedImportUrl(normalized)) {
      setError("Please enter a public video URL from YouTube, Instagram, TikTok, Facebook, X, or Twitch");
      return;
    }

    setImporting(true);
    setError(null);
    setSuccessMessage(null);
    setRecoveryMessage(null);
    try {
      const payload = await api.post<YouTubeImportResponse>("/api/videos/import-youtube", {
        url: normalized,
        clip_profile: clipProfile,
      });
      if (payload.import_kind === "playlist") {
        setSuccessMessage("Importing playlist. Items will appear progressively.");
        await onUploaded();
        window.setTimeout(() => {
          closeModal();
        }, 2000);
      } else if (payload.recovery_required) {
        setSuccessMessage("Import added in recovery mode.");
        setRecoveryMessage(
          "Server download is currently blocked for this link. Close this dialog, open the new row, and click Upload replacement file."
        );
        await onUploaded();
      } else {
        setSuccessMessage("Import started! We'll process your video shortly.");
        await onUploaded();
        window.setTimeout(() => {
          closeModal();
        }, 2000);
      }
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to start import";
      setError(message);
    } finally {
      setImporting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm px-4"
      onClick={closeModal}
    >
      <div
        className="w-full max-w-xl rounded-2xl border border-[var(--app-border)] bg-[var(--app-bg)] shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-[var(--app-border)] px-5 py-3.5">
          <h2 className="text-lg font-semibold text-[var(--app-text)]">Add Video</h2>
          <button
            className="rounded-md p-2 text-[var(--app-muted)] hover:bg-[var(--app-surface-soft)] hover:text-[var(--app-text)] transition-colors"
            onClick={closeModal}
            disabled={busy}
            aria-label="Close"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
              <path d="M18 6L6 18M6 6L18 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        <div className="px-5 pt-3.5">
          <div className="inline-flex rounded-lg bg-[var(--app-surface-soft)] p-1">
            <button
              className={`rounded-md px-4 py-2 text-sm transition-colors ${
                activeTab === "upload" ? "bg-[#1D3FD0] text-white" : "text-[var(--app-muted)] hover:text-[var(--app-text)]"
              }`}
              onClick={() => {
                setActiveTab("upload");
                setError(null);
                setSuccessMessage(null);
                setRecoveryMessage(null);
              }}
            >
              Upload File
            </button>
            <button
              className={`rounded-md px-4 py-2 text-sm transition-colors ${
                activeTab === "youtube" ? "bg-[#1D3FD0] text-white" : "text-[var(--app-muted)] hover:text-[var(--app-text)]"
              }`}
              onClick={() => {
                setActiveTab("youtube");
                setError(null);
                setSuccessMessage(null);
                setRecoveryMessage(null);
              }}
            >
              URL Import
            </button>
          </div>
        </div>

        <div className="p-5">
          <div className="mb-4 rounded-lg border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-3">
            <label className="mb-2 block text-xs font-semibold uppercase tracking-wide text-[var(--app-muted)]">
              Clip Profile
            </label>
            <select
              value={clipProfile}
              onChange={(event) => setClipProfile(event.target.value as ClipProfile)}
              disabled={busy}
              className="w-full rounded-md border border-[var(--app-border)] bg-white/80 px-3 py-2 text-sm text-[var(--app-text)] focus:border-[#1D3FD0] focus:outline-none"
            >
              <option value="viral">Viral (short-form, higher clip count)</option>
              <option value="sermon">Long-form Speaking (fewer, longer clips)</option>
            </select>
            <p className="mt-2 text-xs text-[var(--app-muted)]">
              Long-form Speaking targets approximately 60-180 second clips that preserve full message context.
            </p>
          </div>
          {activeTab === "upload" ? (
            <div>
              <input
                ref={fileInputRef}
                type="file"
                accept="video/mp4,video/quicktime,video/x-msvideo,video/x-matroska"
                className="hidden"
                onChange={(event) => handleFileSelection(event.target.files?.[0] || null)}
              />
              <button
                type="button"
                className={`w-full rounded-xl border-2 border-dashed px-5 py-10 text-center transition-colors ${
                  isDragging
                    ? "border-[#1D3FD0] bg-[#1D3FD0]/10"
                    : "border-[var(--app-border)] bg-white/40 hover:border-[#1D3FD0]/80 hover:bg-[#1D3FD0]/5"
                }`}
                onClick={() => fileInputRef.current?.click()}
                onDragOver={(event) => {
                  event.preventDefault();
                  setIsDragging(true);
                }}
                onDragLeave={(event) => {
                  event.preventDefault();
                  setIsDragging(false);
                }}
                onDrop={(event) => {
                  event.preventDefault();
                  setIsDragging(false);
                  handleFileSelection(event.dataTransfer.files?.[0] || null);
                }}
              >
                <div className="mx-auto mb-3 w-fit rounded-full bg-[#1D3FD0]/15 p-3 text-[#1D3FD0]">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path
                      d="M12 16V4M12 4L7 9M12 4L17 9M4 16V18C4 19.1 4.9 20 6 20H18C19.1 20 20 19.1 20 18V16"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </div>
                <p className="text-base font-medium text-[var(--app-text)]">Drag your video here or click to browse</p>
                <p className="mt-2 text-sm text-[var(--app-muted)]">Supports MP4, MOV, MKV, AVI · Max 5GB</p>
              </button>

              {selectedFile && (
                <div className="mt-4 rounded-xl border border-[var(--app-border)] bg-white/70 px-4 py-3">
                  <p className="truncate text-sm font-medium text-[var(--app-text)]">{selectedFile.name}</p>
                  <p className="mt-1 text-xs text-[var(--app-muted)]">{formatBytes(selectedFile.size)}</p>
                </div>
              )}

              {uploading && (
                <div className="mt-4">
                  <div className="mb-1 flex items-center justify-between text-xs text-[var(--app-muted)]">
                    <span>
                      {uploadPhase === "preparing"
                        ? "Preparing secure upload..."
                        : uploadPhase === "fallback"
                          ? "Finishing through PostBandit..."
                        : uploadPhase === "finalizing"
                          ? "Finalizing and starting processing..."
                          : "Uploading..."}
                    </span>
                    <span>{uploadProgress}%</span>
                  </div>
                  <div className="h-2 rounded-full bg-[var(--app-surface-soft)]">
                    <div
                      className="h-full rounded-full bg-[#1D3FD0] transition-all"
                      style={{ width: `${uploadProgress}%` }}
                    />
                  </div>
                  {uploadPhase === "fallback" ? (
                    <p className="mt-2 text-xs text-[var(--app-muted)]">
                      The direct upload was interrupted, so PostBandit is completing the upload through the app.
                    </p>
                  ) : null}
                  {uploadPhase === "finalizing" ? (
                    <p className="mt-2 text-xs text-[var(--app-muted)]">
                      The file is in storage. Keep this popup open while PostBandit confirms it and starts transcription.
                    </p>
                  ) : null}
                </div>
              )}

              <div className="mt-5 flex justify-end">
                <Button onClick={startUpload} loading={uploading} disabled={!selectedFile} className="min-w-40">
                  Start Processing
                </Button>
              </div>
              {pendingConfirmVideoId && !uploading ? (
                <div className="mt-3 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
                  <p>Upload finished but processing is not confirmed yet.</p>
                  <div className="mt-2 flex justify-end">
                    <Button onClick={retryConfirmUpload} loading={confirmingUpload} variant="secondary">
                      Retry Confirm
                    </Button>
                  </div>
                </div>
              ) : null}
            </div>
          ) : (
            <div>
              <label className="mb-2 block text-sm text-[var(--app-muted)]">Video URL</label>
              <input
                type="text"
                value={youtubeUrl}
                onChange={(event) => setYoutubeUrl(event.target.value)}
                placeholder="Paste a video URL from YouTube, TikTok, Instagram, and more..."
                disabled={importing}
                className="w-full rounded-lg border border-[var(--app-border)] bg-white/70 px-4 py-3 text-sm text-[var(--app-text)]
                           placeholder:text-[var(--app-subtle)] focus:border-[#1D3FD0] focus:outline-none"
              />
              {!youtubeValid && <p className="mt-2 text-xs text-red-700">Paste a public video URL from YouTube, Instagram, TikTok, Facebook, X, or Twitch.</p>}
              <p className="mt-2 text-xs text-[var(--app-muted)]">
                Supports YouTube, Instagram, TikTok, Facebook, X, and Twitch. Public content only; private, login-gated, and live content cannot be imported.
              </p>
              <div className="mt-5 flex justify-end">
                <Button onClick={importYoutube} disabled={!youtubeUrl.trim()} loading={importing} className="min-w-28">
                  Import
                </Button>
              </div>
            </div>
          )}

          {error && <p className="mt-4 text-sm text-red-700">{error}</p>}
          {successMessage && <p className="mt-4 text-sm text-emerald-400">{successMessage}</p>}
          {recoveryMessage && <p className="mt-2 text-sm text-amber-700">{recoveryMessage}</p>}
        </div>
      </div>
    </div>
  );
}
