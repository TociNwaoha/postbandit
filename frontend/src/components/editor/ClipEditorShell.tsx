"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { getSession } from "next-auth/react";

import { inferEditorAspectFromVideo, safeAreaPresetForAspect } from "@/components/editor/aspectInference";
import { EditorTimeline, TimelineTrack } from "@/components/editor/EditorTimeline";
import {
  PreviewHealthDiagnostics,
  VideoPreviewCanvas,
  VideoPreviewCanvasHandle,
} from "@/components/editor/VideoPreviewCanvas";
import { api, ApiError } from "@/lib/api";
import {
  Clip,
  EditorAsset,
  EditorCaptionConfig,
  EditorOverlay,
  EditorProject,
  EditorProjectFromClipResponse,
  EditorRender,
  EditorRenderPreset,
  Video,
} from "@/types";

interface ClipEditorShellProps {
  video: Video;
  clip: Clip;
}

type EditorTab = "media" | "captions" | "text" | "images" | "templates" | "brand";

type EditorSelection =
  | { kind: "video" }
  | { kind: "caption_style" }
  | { kind: "caption_segment"; index: number }
  | { kind: "overlay"; overlayId: string };

const HISTORY_LIMIT = 50;
const HISTORY_COALESCE_MS = 450;
const LAYOUT_STORAGE_KEY = "clip_editor_layout_v1";
const LEFT_PANE_MIN = 240;
const LEFT_PANE_MAX = 520;
const RIGHT_PANE_MIN = 260;
const RIGHT_PANE_MAX = 560;
const TIMELINE_HEIGHT_MIN = 240;
const TIMELINE_HEIGHT_MAX = 460;

const TAB_ITEMS: Array<{ id: EditorTab; label: string }> = [
  { id: "media", label: "Media" },
  { id: "captions", label: "Captions" },
  { id: "text", label: "Text" },
  { id: "images", label: "Images / Logo" },
  { id: "templates", label: "Templates" },
  { id: "brand", label: "Brand" },
];

const PRESET_OPTIONS: Array<{ value: EditorRenderPreset; label: string }> = [
  { value: "tiktok", label: "TikTok (9:16)" },
  { value: "reels", label: "Reels (9:16)" },
  { value: "shorts", label: "Shorts (9:16)" },
  { value: "linkedin", label: "LinkedIn (9:16)" },
  { value: "square", label: "Square (1:1)" },
  { value: "landscape", label: "Landscape (16:9)" },
];

const TEXT_PRESETS: Array<{ label: string; content: string; y: number; bg: string }> = [
  { label: "Hook", content: "Stop scrolling. Watch this.", y: 0.16, bg: "#1D3FD0CC" },
  { label: "CTA", content: "Follow for more clips like this", y: 0.86, bg: "#0B1223CC" },
  { label: "Lower Third", content: "Speaker Name · Key Topic", y: 0.78, bg: "#111827CC" },
];

type SplitterKind = "left" | "right" | "timeline" | null;

function mapCanvasAspectToApi(value: "9:16" | "1:1" | "16:9"): "9:16" | "1:1" | "16:9" {
  return value;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function formatTime(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds || 0));
  const mins = Math.floor(safe / 60);
  const secs = safe % 60;
  return `${mins}:${String(secs).padStart(2, "0")}`;
}

function deepCloneProjectState(projectState: EditorProject["project_json"]): EditorProject["project_json"] {
  return JSON.parse(JSON.stringify(projectState)) as EditorProject["project_json"];
}

function createTextOverlay(content: string, y: number, bgColor: string, clipStart: number, clipEnd: number): EditorOverlay {
  return {
    id: `text_${crypto.randomUUID().slice(0, 8)}`,
    type: "text",
    start_sec: clipStart,
    end_sec: clipEnd,
    x: 0.5,
    y,
    width: 0.6,
    height: 0.14,
    rotation_deg: 0,
    opacity: 1,
    z_index: 10,
    content,
    style: {
      font_family: "Plus Jakarta Sans",
      font_size: 40,
      font_weight: 700,
      alignment: "center",
      color: "#FFFFFF",
      bg_color: bgColor,
    },
  };
}

function createImageOverlay(assetId: string, clipStart: number, clipEnd: number): EditorOverlay {
  return {
    id: `img_${crypto.randomUUID().slice(0, 8)}`,
    type: "image",
    start_sec: clipStart,
    end_sec: clipEnd,
    x: 0.86,
    y: 0.14,
    width: 0.2,
    height: 0.2,
    rotation_deg: 0,
    opacity: 1,
    z_index: 20,
    asset_id: assetId,
  };
}

const DEFAULT_CAPTION_GROUP = {
  anchor_x: 0.5,
  anchor_y: 0.85,
  scale: 1,
};

function normalizeProjectJsonForEditor(projectJson: EditorProject["project_json"]): EditorProject["project_json"] {
  const next = deepCloneProjectState(projectJson);
  if (!next.meta) {
    next.meta = { aspect_auto_inferred_v1: true };
  }

  const group = next.captions.group || {};
  next.captions.group = {
    anchor_x: typeof group.anchor_x === "number" ? clamp(group.anchor_x, 0, 1) : DEFAULT_CAPTION_GROUP.anchor_x,
    anchor_y: typeof group.anchor_y === "number" ? clamp(group.anchor_y, 0, 1) : DEFAULT_CAPTION_GROUP.anchor_y,
    scale: typeof group.scale === "number" ? clamp(group.scale, 0.35, 3) : DEFAULT_CAPTION_GROUP.scale,
  };

  return next;
}

async function uploadAsset(projectId: string, file: File): Promise<EditorAsset> {
  const session = await getSession();
  const token = (session as any)?.accessToken;
  const form = new FormData();
  form.append("file", file);
  form.append("asset_type", "image");

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const headers = token ? { Authorization: `Bearer ${token}` } : undefined;
  let res: Response;
  try {
    res = await fetch(`${apiUrl}/api/editor/projects/${projectId}/assets`, {
      method: "POST",
      body: form,
      headers,
    });
  } catch {
    res = await fetch(`/api/backend/editor/projects/${projectId}/assets`, {
      method: "POST",
      body: form,
      headers,
    });
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: "Failed to upload asset" }));
    throw new Error(body.detail || "Failed to upload asset");
  }

  return (await res.json()) as EditorAsset;
}

function renderAutosaveLabel({
  loading,
  saving,
  dirty,
}: {
  loading: boolean;
  saving: boolean;
  dirty: boolean;
}): string {
  if (loading) return "Loading project...";
  if (saving) return "Saving...";
  if (dirty) return "Unsaved changes";
  return "Saved";
}

export function ClipEditorShell({ video, clip }: ClipEditorShellProps) {
  const [project, setProject] = useState<EditorProject | null>(null);
  const [projectState, setProjectState] = useState<EditorProject["project_json"] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [currentTimeSec, setCurrentTimeSec] = useState<number>(clip.start_time || 0);
  const [mediaDurationSec, setMediaDurationSec] = useState<number>(video.duration_sec || 0);
  const [latestRender, setLatestRender] = useState<EditorRender | null>(null);
  const [rendering, setRendering] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [activeTab, setActiveTab] = useState<EditorTab>("media");
  const [selection, setSelection] = useState<EditorSelection>({ kind: "video" });
  const [showSafeAreas, setShowSafeAreas] = useState(true);
  const [timelineZoom, setTimelineZoom] = useState(14);
  const [previewDiagnostics, setPreviewDiagnostics] = useState<PreviewHealthDiagnostics | null>(null);
  const [undoStack, setUndoStack] = useState<string[]>([]);
  const [redoStack, setRedoStack] = useState<string[]>([]);
  const [leftPaneWidth, setLeftPaneWidth] = useState(300);
  const [rightPaneWidth, setRightPaneWidth] = useState(320);
  const [timelineHeight, setTimelineHeight] = useState(300);

  const undoStackRef = useRef<string[]>([]);
  const redoStackRef = useRef<string[]>([]);
  const lastHistoryPushAtRef = useRef(0);
  const lastSavedSnapshotRef = useRef<string>("");
  const pollTimerRef = useRef<number | null>(null);
  const previewStatusPollTimerRef = useRef<number | null>(null);
  const videoPreviewRef = useRef<VideoPreviewCanvasHandle | null>(null);
  const splitterDragRef = useRef<{
    kind: SplitterKind;
    startX: number;
    startY: number;
    startLeft: number;
    startRight: number;
    startTimeline: number;
  }>({
    kind: null,
    startX: 0,
    startY: 0,
    startLeft: 300,
    startRight: 320,
    startTimeline: 300,
  });

  const editorPreviewStatus = project?.preview_status ?? projectState?.meta?.editor_preview_status ?? null;
  const sourcePlayerUrl = video.source_download_url || null;
  const previewUrl = project?.preview_download_url || null;
  const previewOffsetSec = project?.preview_offset_sec ?? projectState?.meta?.editor_preview_offset_sec ?? 0;
  const previewDurationSec = project?.preview_duration_sec ?? projectState?.meta?.editor_preview_duration_sec ?? null;
  const previewError = project?.preview_error ?? projectState?.meta?.editor_preview_error ?? null;
  const hasReadyPreviewProxy = editorPreviewStatus === "ready" && Boolean(previewUrl);
  const preparingPreview = Boolean(project) && !hasReadyPreviewProxy && editorPreviewStatus !== "failed";
  const sourceUrl = hasReadyPreviewProxy ? previewUrl : null;
  const sourceKind: "source" | "proxy" | "none" = hasReadyPreviewProxy ? "proxy" : "none";
  const usingEditorPreviewProxy = sourceKind === "proxy";

  useEffect(() => {
    setPreviewDiagnostics(null);
  }, [video]);

  useEffect(() => {
    undoStackRef.current = undoStack;
  }, [undoStack]);

  useEffect(() => {
    redoStackRef.current = redoStack;
  }, [redoStack]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem(LAYOUT_STORAGE_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw) as {
        leftPaneWidth?: number;
        rightPaneWidth?: number;
        timelineHeight?: number;
      };
      if (typeof parsed.leftPaneWidth === "number") {
        setLeftPaneWidth(clamp(parsed.leftPaneWidth, LEFT_PANE_MIN, LEFT_PANE_MAX));
      }
      if (typeof parsed.rightPaneWidth === "number") {
        setRightPaneWidth(clamp(parsed.rightPaneWidth, RIGHT_PANE_MIN, RIGHT_PANE_MAX));
      }
      if (typeof parsed.timelineHeight === "number") {
        setTimelineHeight(clamp(parsed.timelineHeight, TIMELINE_HEIGHT_MIN, TIMELINE_HEIGHT_MAX));
      }
    } catch {
      // ignore local storage parse errors
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(
      LAYOUT_STORAGE_KEY,
      JSON.stringify({
        leftPaneWidth,
        rightPaneWidth,
        timelineHeight,
      })
    );
  }, [leftPaneWidth, rightPaneWidth, timelineHeight]);

  useEffect(() => {
    const handlePointerMove = (event: PointerEvent) => {
      const state = splitterDragRef.current;
      if (!state.kind) return;
      if (state.kind === "left") {
        const next = clamp(state.startLeft + (event.clientX - state.startX), LEFT_PANE_MIN, LEFT_PANE_MAX);
        setLeftPaneWidth(next);
        return;
      }
      if (state.kind === "right") {
        const next = clamp(state.startRight - (event.clientX - state.startX), RIGHT_PANE_MIN, RIGHT_PANE_MAX);
        setRightPaneWidth(next);
        return;
      }
      if (state.kind === "timeline") {
        const next = clamp(
          state.startTimeline + (event.clientY - state.startY),
          TIMELINE_HEIGHT_MIN,
          TIMELINE_HEIGHT_MAX
        );
        setTimelineHeight(next);
      }
    };

    const clearDrag = () => {
      splitterDragRef.current.kind = null;
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", clearDrag);
    window.addEventListener("pointercancel", clearDrag);
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", clearDrag);
      window.removeEventListener("pointercancel", clearDrag);
    };
  }, []);

  const loadProject = async (projectId: string) => {
    const fetched = await api.get<EditorProject>(`/api/editor/projects/${projectId}`);
    const normalizedProjectState = normalizeProjectJsonForEditor(fetched.project_json);
    setProject({ ...fetched, project_json: normalizedProjectState });
    setProjectState(normalizedProjectState);
    setLatestRender(fetched.latest_render || null);
    const snapshot = JSON.stringify(normalizedProjectState);
    lastSavedSnapshotRef.current = snapshot;
    setCurrentTimeSec(fetched.trim_start_sec);
    setIsPlaying(false);
    setUndoStack([]);
    setRedoStack([]);
    lastHistoryPushAtRef.current = 0;
    setSelection({ kind: "video" });
  };

  useEffect(() => {
    let mounted = true;

    const boot = async () => {
      setLoading(true);
      setError(null);
      try {
        const inferredAspect = inferEditorAspectFromVideo(video);
        const created = await api.post<EditorProjectFromClipResponse>("/api/editor/projects/from-clip", {
          clip_id: clip.id,
          aspect_ratio: inferredAspect,
        });
        if (!mounted) return;
        await loadProject(created.project_id);
      } catch (err) {
        if (!mounted) return;
        const message = err instanceof ApiError ? err.message : "Failed to initialize editor project";
        setError(message);
      } finally {
        if (mounted) setLoading(false);
      }
    };

    void boot();

    return () => {
      mounted = false;
      if (pollTimerRef.current !== null) {
        window.clearInterval(pollTimerRef.current);
      }
    };
  }, [clip.id]);

  const snapshot = useMemo(() => (projectState ? JSON.stringify(projectState) : ""), [projectState]);
  const dirty = Boolean(snapshot && snapshot !== lastSavedSnapshotRef.current);

  const pushHistorySnapshot = (previousSnapshot: string, coalesce = true) => {
    const now = Date.now();
    const canCoalesce = coalesce && now - lastHistoryPushAtRef.current < HISTORY_COALESCE_MS;
    if (canCoalesce) {
      return;
    }
    lastHistoryPushAtRef.current = now;

    setUndoStack((prev) => {
      const next = [...prev, previousSnapshot];
      return next.slice(-HISTORY_LIMIT);
    });
    setRedoStack([]);
  };

  const applyProjectMutation = (
    updater: (prev: EditorProject["project_json"]) => EditorProject["project_json"],
    options?: { recordHistory?: boolean; coalesce?: boolean }
  ) => {
    const recordHistory = options?.recordHistory ?? true;
    const coalesce = options?.coalesce ?? true;

    setProjectState((prev) => {
      if (!prev) return prev;
      const next = updater(prev);
      if (next === prev) return prev;
      if (recordHistory) {
        pushHistorySnapshot(JSON.stringify(prev), coalesce);
      }
      return next;
    });
  };

  const handleUndo = () => {
    if (!projectState || !undoStackRef.current.length) return;
    const currentSnapshot = JSON.stringify(projectState);
    const previousSnapshot = undoStackRef.current[undoStackRef.current.length - 1];

    setUndoStack((prev) => prev.slice(0, -1));
    setRedoStack((prev) => [...prev, currentSnapshot].slice(-HISTORY_LIMIT));
    setProjectState(JSON.parse(previousSnapshot) as EditorProject["project_json"]);
    setSelection({ kind: "video" });
  };

  const handleRedo = () => {
    if (!projectState || !redoStackRef.current.length) return;
    const currentSnapshot = JSON.stringify(projectState);
    const nextSnapshot = redoStackRef.current[redoStackRef.current.length - 1];

    setRedoStack((prev) => prev.slice(0, -1));
    setUndoStack((prev) => [...prev, currentSnapshot].slice(-HISTORY_LIMIT));
    setProjectState(JSON.parse(nextSnapshot) as EditorProject["project_json"]);
    setSelection({ kind: "video" });
  };

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const isMeta = event.metaKey || event.ctrlKey;
      if (!isMeta) return;

      if (event.key.toLowerCase() === "z" && !event.shiftKey) {
        event.preventDefault();
        handleUndo();
      } else if ((event.key.toLowerCase() === "z" && event.shiftKey) || event.key.toLowerCase() === "y") {
        event.preventDefault();
        handleRedo();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [projectState]);

  useEffect(() => {
    if (!project || !projectState || !dirty || saving) return;

    const timer = window.setTimeout(async () => {
      setSaving(true);
      try {
        const updated = await api.patch<EditorProject>(`/api/editor/projects/${project.id}`, {
          revision: project.revision,
          name: project.name,
          aspect_ratio: mapCanvasAspectToApi(projectState.canvas.aspect_ratio),
          trim_start_sec: projectState.trim.start_sec,
          trim_end_sec: projectState.trim.end_sec,
          project_json: projectState,
        });

        setProject(updated);
        setProjectState(updated.project_json);
        setLatestRender(updated.latest_render || null);
        lastSavedSnapshotRef.current = JSON.stringify(updated.project_json);
        setInfo("Saved");
        window.setTimeout(() => setInfo(null), 900);
      } catch (err) {
        const message = err instanceof ApiError ? err.message : "Autosave failed";
        setError(message);
      } finally {
        setSaving(false);
      }
    }, 1100);

    return () => window.clearTimeout(timer);
  }, [dirty, project, projectState, saving]);

  useEffect(() => {
    if (!latestRender) return;
    if (!(latestRender.status === "queued" || latestRender.status === "processing")) return;

    if (pollTimerRef.current !== null) {
      window.clearInterval(pollTimerRef.current);
    }

    pollTimerRef.current = window.setInterval(async () => {
      try {
        const refreshed = await api.get<EditorRender>(`/api/editor/renders/${latestRender.id}`);
        setLatestRender(refreshed);
        if (refreshed.status === "completed" || refreshed.status === "failed") {
          if (pollTimerRef.current !== null) {
            window.clearInterval(pollTimerRef.current);
            pollTimerRef.current = null;
          }
          if (project) {
            await loadProject(project.id);
          }
        }
      } catch {
        // transient failures ignored
      }
    }, 4000);

    return () => {
      if (pollTimerRef.current !== null) {
        window.clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [latestRender?.id, latestRender?.status, project?.id]);

  useEffect(() => {
    const previewReady = editorPreviewStatus === "ready" && Boolean(previewUrl);
    const previewTerminal = previewReady || editorPreviewStatus === "failed";
    if (previewTerminal || !project) {
      if (previewStatusPollTimerRef.current !== null) {
        window.clearInterval(previewStatusPollTimerRef.current);
        previewStatusPollTimerRef.current = null;
      }
      return;
    }

    let cancelled = false;
    const refreshProjectPreviewStatus = async () => {
      try {
        const refreshed = await api.get<EditorProject>(`/api/editor/projects/${project.id}`);
        if (!cancelled) {
          setProject((prev) =>
            prev
              ? {
                  ...refreshed,
                  project_json: prev.project_json,
                  revision: prev.revision,
                }
              : refreshed
          );
          setLatestRender(refreshed.latest_render || null);
        }
      } catch {
        // ignore transient network errors while polling preview readiness
      }
    };

    void refreshProjectPreviewStatus();
    previewStatusPollTimerRef.current = window.setInterval(refreshProjectPreviewStatus, 2500);
    return () => {
      cancelled = true;
      if (previewStatusPollTimerRef.current !== null) {
        window.clearInterval(previewStatusPollTimerRef.current);
        previewStatusPollTimerRef.current = null;
      }
    };
  }, [editorPreviewStatus, previewUrl, project?.id]);

  useEffect(() => {
    if (!previewDiagnostics) return;

    if (previewDiagnostics.state === "frame_visible") {
      return;
    }

    if (previewDiagnostics.state === "frame_failed") {
      setError("Editor preview failed to paint. Regenerate the editor preview and try again.");
    }
  }, [previewDiagnostics]);

  useEffect(() => {
    return () => {
      if (previewStatusPollTimerRef.current !== null) {
        window.clearInterval(previewStatusPollTimerRef.current);
      }
    };
  }, []);

  // Keep all hooks above this line to prevent hook-order mismatches.

  if (loading) {
    return (
      <div className="editor-workspace min-h-screen px-6 py-6">
        <div className="rounded-xl border border-[var(--editor-border)] bg-[var(--editor-panel)] p-6 text-sm text-[var(--editor-muted)]">
          Loading editor project...
        </div>
      </div>
    );
  }

  if (error && !projectState) {
    return (
      <div className="editor-workspace min-h-screen px-6 py-6">
        <div className="rounded-xl border border-red-500/40 bg-red-500/10 p-6 text-sm text-red-200">{error}</div>
      </div>
    );
  }

  if (!project || !projectState) {
    return (
      <div className="editor-workspace min-h-screen px-6 py-6">
        <div className="rounded-xl border border-red-500/40 bg-red-500/10 p-6 text-sm text-red-200">
          Editor project could not be loaded.
        </div>
      </div>
    );
  }

  const trimStart = projectState.trim.start_sec;
  const trimEnd = projectState.trim.end_sec;
  const effectiveDurationSec = mediaDurationSec || video.duration_sec || trimEnd;

  const selectedOverlay =
    selection.kind === "overlay"
      ? projectState.overlays.find((overlay) => overlay.id === selection.overlayId) || null
      : null;
  const selectedTextOverlay = selectedOverlay?.type === "text" ? selectedOverlay : null;
  const selectedImageOverlay = selectedOverlay?.type === "image" ? selectedOverlay : null;

  const captionSegment =
    selection.kind === "caption_segment"
      ? projectState.captions.overrides[selection.index] || null
      : null;

  const captionGroup = projectState.captions.group || DEFAULT_CAPTION_GROUP;
  const captionGroupAnchorX =
    typeof captionGroup.anchor_x === "number" ? clamp(captionGroup.anchor_x, 0, 1) : DEFAULT_CAPTION_GROUP.anchor_x;
  const captionGroupAnchorY =
    typeof captionGroup.anchor_y === "number" ? clamp(captionGroup.anchor_y, 0, 1) : DEFAULT_CAPTION_GROUP.anchor_y;
  const captionGroupScale =
    typeof captionGroup.scale === "number" ? clamp(captionGroup.scale, 0.35, 3) : DEFAULT_CAPTION_GROUP.scale;

  const seekPreview = (seconds: number) => {
    const safe = clamp(seconds, 0, effectiveDurationSec || seconds || 0);
    setCurrentTimeSec(safe);
    videoPreviewRef.current?.seekTo(safe);
    return safe;
  };

  const handleStartPlayback = async () => {
    if (!sourceUrl) {
      if (preparingPreview) {
        setInfo("Preparing editor-safe preview. Playback will start once proxy is ready.");
        window.setTimeout(() => setInfo(null), 1400);
      } else {
        setError("Preview source unavailable.");
      }
      return;
    }

    try {
      setError(null);
      await videoPreviewRef.current?.play();
      setIsPlaying(true);
    } catch {
      setError("Playback was blocked by browser autoplay policy. Click Play again to allow audio.");
    }
  };

  const handleStopPlayback = () => {
    videoPreviewRef.current?.pause();
    setIsPlaying(false);
  };

  const handleJumpToStart = () => {
    handleStopPlayback();
    seekPreview(trimStart);
  };

  const handleReplay = async () => {
    handleStopPlayback();
    seekPreview(trimStart);
    await handleStartPlayback();
  };

  const handleRegeneratePreview = async () => {
    if (!project) return;
    try {
      setInfo("Regenerating editor preview...");
      const refreshed = await api.post<EditorProject>(`/api/editor/projects/${project.id}/preview/regenerate`, {});
      setProject((prev) =>
        prev
          ? {
              ...refreshed,
              project_json: prev.project_json,
              revision: prev.revision,
            }
          : refreshed
      );
      setPreviewDiagnostics(null);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to regenerate editor preview";
      setError(message);
    } finally {
      window.setTimeout(() => setInfo(null), 1200);
    }
  };

  const beginSplitterDrag = (kind: Exclude<SplitterKind, null>, event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    splitterDragRef.current = {
      kind,
      startX: event.clientX,
      startY: event.clientY,
      startLeft: leftPaneWidth,
      startRight: rightPaneWidth,
      startTimeline: timelineHeight,
    };
  };

  const replaceOverlay = (overlayId: string, patch: Partial<EditorOverlay>, coalesce = true) => {
    applyProjectMutation(
      (prev) => ({
        ...prev,
        overlays: prev.overlays.map((overlay) =>
          overlay.id === overlayId
            ? {
                ...overlay,
                ...patch,
                style: {
                  ...(overlay.style || {}),
                  ...(patch.style || {}),
                },
              }
            : overlay
        ),
      }),
      { recordHistory: true, coalesce }
    );
  };

  const updateOverlayTimingFromTimeline = (trackId: string, itemId: string, startSec: number, endSec: number) => {
    if (trackId !== "text" && trackId !== "images") return;
    const safeStart = clamp(startSec, 0, effectiveDurationSec);
    const safeEnd = clamp(Math.max(safeStart + 0.1, endSec), safeStart + 0.1, effectiveDurationSec);
    replaceOverlay(
      itemId,
      {
        start_sec: safeStart,
        end_sec: safeEnd,
      },
      true
    );
  };

  const updateCaptionConfig = (next: EditorCaptionConfig, coalesce = true) => {
    applyProjectMutation(
      (prev) => ({
        ...prev,
        captions: next,
      }),
      { recordHistory: true, coalesce }
    );
  };

  const updateCaptionGroup = (
    patch: Partial<{ anchor_x: number; anchor_y: number; scale: number }>,
    coalesce = true
  ) => {
    applyProjectMutation(
      (prev) => {
        const current = prev.captions.group || DEFAULT_CAPTION_GROUP;
        const nextAnchorX = patch.anchor_x !== undefined ? clamp(patch.anchor_x, 0, 1) : current.anchor_x ?? DEFAULT_CAPTION_GROUP.anchor_x;
        const nextAnchorY = patch.anchor_y !== undefined ? clamp(patch.anchor_y, 0, 1) : current.anchor_y ?? DEFAULT_CAPTION_GROUP.anchor_y;
        const nextScale = patch.scale !== undefined ? clamp(patch.scale, 0.35, 3) : current.scale ?? DEFAULT_CAPTION_GROUP.scale;

        return {
          ...prev,
          captions: {
            ...prev.captions,
            group: {
              ...current,
              anchor_x: nextAnchorX,
              anchor_y: nextAnchorY,
              scale: nextScale,
            },
          },
        };
      },
      { recordHistory: true, coalesce }
    );
  };

  const updateCaptionSegment = (index: number, patch: Partial<(typeof projectState.captions.overrides)[number]>) => {
    applyProjectMutation(
      (prev) => {
        const nextOverrides = [...prev.captions.overrides];
        const segment = nextOverrides[index];
        if (!segment) return prev;
        nextOverrides[index] = {
          ...segment,
          ...patch,
          start_sec: patch.start_sec !== undefined ? Math.max(0, patch.start_sec) : segment.start_sec,
          end_sec:
            patch.end_sec !== undefined
              ? Math.max((patch.start_sec ?? segment.start_sec) + 0.05, patch.end_sec)
              : segment.end_sec,
        };
        return {
          ...prev,
          captions: {
            ...prev.captions,
            overrides: nextOverrides,
          },
        };
      },
      { recordHistory: true, coalesce: true }
    );
  };

  const addTextPreset = (preset: (typeof TEXT_PRESETS)[number]) => {
    const layer = createTextOverlay(preset.content, preset.y, preset.bg, trimStart, trimEnd);
    applyProjectMutation(
      (prev) => ({
        ...prev,
        overlays: [...prev.overlays, layer],
      }),
      { recordHistory: true, coalesce: false }
    );
    setSelection({ kind: "overlay", overlayId: layer.id });
  };

  const insertImageLayer = (assetId: string) => {
    const layer = createImageOverlay(assetId, trimStart, trimEnd);
    applyProjectMutation(
      (prev) => ({
        ...prev,
        overlays: [...prev.overlays, layer],
      }),
      { recordHistory: true, coalesce: false }
    );
    setSelection({ kind: "overlay", overlayId: layer.id });
  };

  const removeOverlay = (overlayId: string) => {
    applyProjectMutation(
      (prev) => ({
        ...prev,
        overlays: prev.overlays.filter((overlay) => overlay.id !== overlayId),
      }),
      { recordHistory: true, coalesce: false }
    );
    if (selection.kind === "overlay" && selection.overlayId === overlayId) {
      setSelection({ kind: "video" });
    }
  };

  const moveOverlayLayer = (overlayId: string, direction: "up" | "down") => {
    applyProjectMutation(
      (prev) => {
        const sorted = [...prev.overlays].sort((a, b) => a.z_index - b.z_index);
        const index = sorted.findIndex((item) => item.id === overlayId);
        if (index < 0) return prev;
        const target = direction === "up" ? index + 1 : index - 1;
        if (target < 0 || target >= sorted.length) return prev;

        const first = sorted[index];
        const second = sorted[target];
        const swap = first.z_index;
        first.z_index = second.z_index;
        second.z_index = swap;

        return {
          ...prev,
          overlays: sorted,
        };
      },
      { recordHistory: true, coalesce: false }
    );
  };

  const handleUploadAsset = async (file: File) => {
    setError(null);
    try {
      const uploaded = await uploadAsset(project.id, file);
      setProject((prev) => (prev ? { ...prev, assets: [...prev.assets, uploaded] } : prev));
      setInfo(`Uploaded ${uploaded.original_filename || "asset"}`);
      window.setTimeout(() => setInfo(null), 1200);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload asset");
    }
  };

  const handleRender = async () => {
    setRendering(true);
    setError(null);
    try {
      const render = await api.post<EditorRender>(`/api/editor/projects/${project.id}/render`, {
        preset: projectState.export.preset,
      });
      setLatestRender(render);
      setInfo("Render queued");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to queue render");
    } finally {
      setRendering(false);
    }
  };

  // Intentionally not memoized: this computation sits after early return branches.
  // Keeping it as a plain const avoids hook-order mismatches across loading/error/ready renders.
  const timelineTracks: TimelineTrack[] = (() => {
    const captionItems = projectState.captions.overrides.slice(0, 120).map((segment, index) => ({
      id: `segment-${index}`,
      label: segment.text?.slice(0, 24) || `Caption ${index + 1}`,
      type: "caption" as const,
      startSec: trimStart + segment.start_sec,
      endSec: trimStart + segment.end_sec,
      selected: selection.kind === "caption_segment" && selection.index === index,
    }));

    const textItems = projectState.overlays
      .filter((overlay) => overlay.type === "text")
      .map((overlay) => ({
        id: overlay.id,
        label: (overlay.content || "Text").slice(0, 24),
        type: "text" as const,
        startSec: overlay.start_sec,
        endSec: overlay.end_sec,
        selected: selection.kind === "overlay" && selection.overlayId === overlay.id,
      }));

    const imageItems = projectState.overlays
      .filter((overlay) => overlay.type === "image")
      .map((overlay) => ({
        id: overlay.id,
        label: overlay.asset_id ? `Image ${overlay.asset_id.slice(0, 6)}` : "Image",
        type: "image" as const,
        startSec: overlay.start_sec,
        endSec: overlay.end_sec,
        selected: selection.kind === "overlay" && selection.overlayId === overlay.id,
      }));

    return [
      {
        id: "video",
        label: "Track 1 · Main Video",
        items: [
          {
            id: "video-main",
            label: clip.title || "Main clip",
            type: "video",
            startSec: trimStart,
            endSec: trimEnd,
            selected: selection.kind === "video",
          },
        ],
      },
      {
        id: "captions",
        label: "Track 2 · Captions",
        items: captionItems,
      },
      {
        id: "text",
        label: "Track 3 · Text Overlays",
        items: textItems,
      },
      {
        id: "images",
        label: "Track 4 · Images / Logos",
        items: imageItems,
      },
    ];
  })();

  const autosaveLabel = renderAutosaveLabel({ loading, saving, dirty });

  const selectTimelineItem = (trackId: string, itemId: string) => {
    if (trackId === "video") {
      setSelection({ kind: "video" });
      seekPreview(trimStart);
      return;
    }

    if (trackId === "captions") {
      const index = Number(itemId.replace("segment-", ""));
      if (Number.isFinite(index)) {
        setSelection({ kind: "caption_segment", index });
        const segment = projectState.captions.overrides[index];
        if (segment) seekPreview(trimStart + segment.start_sec);
      }
      return;
    }

    if (trackId === "text" || trackId === "images") {
      setSelection({ kind: "overlay", overlayId: itemId });
      const overlay = projectState.overlays.find((item) => item.id === itemId);
      if (overlay) seekPreview(overlay.start_sec);
    }
  };

  return (
    <div className="editor-workspace min-h-screen px-4 py-3 md:px-6">
      <div className="mx-auto flex h-[calc(100vh-1.5rem)] max-w-[1800px] flex-col gap-3">
        <header className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--editor-border)] bg-[var(--editor-panel)] px-4 py-3">
          <div className="flex min-w-0 flex-1 items-center gap-3">
            <Link
              href={`/videos/${video.id}`}
              className="rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2.5 py-1.5 text-xs text-[var(--editor-muted)] hover:text-[var(--editor-text)]"
            >
              Back to Clips
            </Link>

            <input
              value={project.name || "Clip Project"}
              onChange={(event) => setProject((prev) => (prev ? { ...prev, name: event.target.value } : prev))}
              className="min-w-0 flex-1 rounded-md border border-transparent bg-transparent px-2 py-1 text-sm font-semibold text-[var(--editor-text)] focus:border-[var(--editor-border)] focus:bg-[var(--editor-panel-2)] focus:outline-none"
            />

            <span className="rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2 py-1 text-[11px] text-[var(--editor-muted)]">
              {autosaveLabel}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={handleUndo}
              disabled={undoStack.length === 0}
              className="rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2.5 py-1.5 text-xs text-[var(--editor-muted)] disabled:opacity-40"
            >
              Undo
            </button>
            <button
              type="button"
              onClick={handleRedo}
              disabled={redoStack.length === 0}
              className="rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2.5 py-1.5 text-xs text-[var(--editor-muted)] disabled:opacity-40"
            >
              Redo
            </button>

            <div className="inline-flex rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] p-1">
              {(["9:16", "1:1", "16:9"] as const).map((aspect) => (
                <button
                  key={aspect}
                  type="button"
                  onClick={() =>
                    applyProjectMutation(
                      (prev) => ({
                        ...prev,
                        canvas: {
                          ...prev.canvas,
                          aspect_ratio: aspect,
                          safe_area_preset: safeAreaPresetForAspect(aspect),
                        },
                      }),
                      { recordHistory: true, coalesce: false }
                    )
                  }
                  className={`rounded px-2.5 py-1 text-xs ${
                    projectState.canvas.aspect_ratio === aspect
                      ? "bg-[#3C6DFF] text-white"
                      : "text-[var(--editor-muted)] hover:text-[var(--editor-text)]"
                  }`}
                >
                  {aspect}
                </button>
              ))}
            </div>

            <select
              value={projectState.export.preset}
              onChange={(event) =>
                applyProjectMutation(
                  (prev) => ({
                    ...prev,
                    export: {
                      ...prev.export,
                      preset: event.target.value as EditorRenderPreset,
                    },
                    canvas: {
                      ...prev.canvas,
                      safe_area_preset: event.target.value as EditorProject["project_json"]["canvas"]["safe_area_preset"],
                    },
                  }),
                  { recordHistory: true, coalesce: false }
                )
              }
              className="rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2.5 py-1.5 text-xs text-[var(--editor-text)]"
            >
              {PRESET_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>

            <button
              type="button"
              onClick={() => void handleRender()}
              disabled={rendering || project.storage_usage?.blocked}
              className="rounded-md bg-[#3C6DFF] px-3.5 py-1.5 text-sm font-semibold text-white hover:bg-[#2A57DD] disabled:opacity-60"
            >
              {rendering ? "Queueing..." : "Export"}
            </button>
          </div>
        </header>

        {error ? <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">{error}</p> : null}
        {info ? <p className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">{info}</p> : null}

        <div className="min-h-0 flex flex-1 flex-col gap-2">
          <div className="min-h-0 flex flex-1 items-stretch">
            <aside
              className="flex min-h-0 shrink-0 flex-col overflow-hidden rounded-xl border border-[var(--editor-border)] bg-[var(--editor-panel)]"
              style={{ width: `${leftPaneWidth}px` }}
            >
            <div className="grid grid-cols-2 gap-1 border-b border-[var(--editor-border)] p-2">
              {TAB_ITEMS.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveTab(tab.id)}
                  className={`rounded-md px-2 py-1.5 text-xs font-medium ${
                    activeTab === tab.id
                      ? "bg-[#25324A] text-[var(--editor-text)]"
                      : "text-[var(--editor-muted)] hover:text-[var(--editor-text)]"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto p-3">
              {activeTab === "media" ? (
                <div className="space-y-4 text-xs text-[var(--editor-muted)]">
                  <div className="rounded-lg border border-[var(--editor-border)] bg-[var(--editor-panel-2)] p-3">
                    <p className="text-[11px] uppercase tracking-wide text-[var(--editor-subtle)]">Source Clip</p>
                    <p className="mt-2 text-sm text-[var(--editor-text)]">{video.title || "Untitled video"}</p>
                    <p className="mt-1">{formatTime(trimStart)} - {formatTime(trimEnd)}</p>
                    <p>Duration: {formatTime(effectiveDurationSec)}</p>
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <p className="text-[11px] uppercase tracking-wide text-[var(--editor-subtle)]">Assets</p>
                      <label className="cursor-pointer rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2 py-1 text-[11px] text-[var(--editor-text)]">
                        Upload
                        <input
                          type="file"
                          accept="image/*"
                          className="hidden"
                          onChange={(event) => {
                            const file = event.target.files?.[0];
                            if (!file) return;
                            void handleUploadAsset(file);
                            event.target.value = "";
                          }}
                        />
                      </label>
                    </div>

                    {project.assets.length === 0 ? (
                      <p className="rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] p-2 text-[11px]">
                        No uploaded images/logos yet.
                      </p>
                    ) : (
                      <div className="space-y-2">
                        {project.assets.map((asset) => (
                          <div key={asset.id} className="rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] p-2">
                            <p className="truncate text-[12px] text-[var(--editor-text)]">{asset.original_filename || asset.id}</p>
                            <div className="mt-2 flex items-center justify-between">
                              <span className="text-[10px] text-[var(--editor-subtle)]">{asset.asset_type}</span>
                              <button
                                type="button"
                                onClick={() => insertImageLayer(asset.id)}
                                className="rounded border border-[var(--editor-border)] px-2 py-1 text-[10px] text-[var(--editor-text)]"
                              >
                                Insert
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ) : null}

              {activeTab === "captions" ? (
                <div className="space-y-3 text-xs text-[var(--editor-muted)]">
                  <div className="flex items-center justify-between rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] p-2">
                    <span>Captions Enabled</span>
                    <input
                      type="checkbox"
                      checked={projectState.captions.enabled}
                      onChange={(event) =>
                        updateCaptionConfig(
                          {
                            ...projectState.captions,
                            enabled: event.target.checked,
                          },
                          false
                        )
                      }
                    />
                  </div>

                  <button
                    type="button"
                    onClick={() => setSelection({ kind: "caption_style" })}
                    className="w-full rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-3 py-2 text-left text-[11px] text-[var(--editor-text)]"
                  >
                    Edit caption style in inspector
                  </button>

                  <div className="space-y-1">
                    <p className="text-[11px] uppercase tracking-wide text-[var(--editor-subtle)]">Segments</p>
                    <div className="max-h-[320px] space-y-1 overflow-y-auto">
                      {projectState.captions.overrides.slice(0, 120).map((segment, index) => {
                        const selected = selection.kind === "caption_segment" && selection.index === index;
                        return (
                          <button
                            type="button"
                            key={`${segment.segment_id || "seg"}-${index}`}
                            onClick={() => {
                              setSelection({ kind: "caption_segment", index });
                              seekPreview(segment.start_sec);
                            }}
                            className={`w-full rounded-md border px-2 py-1 text-left ${
                              selected
                                ? "border-[#4A7BFF] bg-[#25324A] text-[var(--editor-text)]"
                                : "border-[var(--editor-border)] bg-[var(--editor-panel-2)] text-[var(--editor-muted)]"
                            }`}
                          >
                            <p className="truncate text-[11px]">{segment.text || "(empty)"}</p>
                            <p className="text-[10px] text-[var(--editor-subtle)]">
                              {segment.start_sec.toFixed(1)}s - {segment.end_sec.toFixed(1)}s
                            </p>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              ) : null}

              {activeTab === "text" ? (
                <div className="space-y-3 text-xs text-[var(--editor-muted)]">
                  <p className="text-[11px] uppercase tracking-wide text-[var(--editor-subtle)]">Quick Text</p>
                  <div className="grid gap-2">
                    {TEXT_PRESETS.map((preset) => (
                      <button
                        key={preset.label}
                        type="button"
                        onClick={() => addTextPreset(preset)}
                        className="rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-3 py-2 text-left text-[11px] text-[var(--editor-text)]"
                      >
                        <p className="font-semibold">{preset.label}</p>
                        <p className="mt-1 truncate text-[10px] text-[var(--editor-subtle)]">{preset.content}</p>
                      </button>
                    ))}
                  </div>

                  <div className="space-y-2">
                    <p className="text-[11px] uppercase tracking-wide text-[var(--editor-subtle)]">Text Layers</p>
                    {projectState.overlays.filter((overlay) => overlay.type === "text").length === 0 ? (
                      <p className="rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] p-2 text-[11px]">
                        No text layers yet.
                      </p>
                    ) : (
                      projectState.overlays
                        .filter((overlay) => overlay.type === "text")
                        .map((overlay) => {
                          const selected = selection.kind === "overlay" && selection.overlayId === overlay.id;
                          return (
                            <div
                              key={overlay.id}
                              className={`rounded-md border p-2 ${
                                selected
                                  ? "border-[#4A7BFF] bg-[#25324A]"
                                  : "border-[var(--editor-border)] bg-[var(--editor-panel-2)]"
                              }`}
                            >
                              <button
                                type="button"
                                onClick={() => {
                                  setSelection({ kind: "overlay", overlayId: overlay.id });
                                  seekPreview(overlay.start_sec);
                                }}
                                className="w-full text-left"
                              >
                                <p className="truncate text-[11px] text-[var(--editor-text)]">{overlay.content || "Text overlay"}</p>
                                <p className="text-[10px] text-[var(--editor-subtle)]">
                                  {overlay.start_sec.toFixed(1)}s - {overlay.end_sec.toFixed(1)}s
                                </p>
                              </button>
                              <div className="mt-2 flex gap-2">
                                <button
                                  type="button"
                                  onClick={() => moveOverlayLayer(overlay.id, "up")}
                                  className="rounded border border-[var(--editor-border)] px-2 py-1 text-[10px] text-[var(--editor-muted)]"
                                >
                                  Up
                                </button>
                                <button
                                  type="button"
                                  onClick={() => moveOverlayLayer(overlay.id, "down")}
                                  className="rounded border border-[var(--editor-border)] px-2 py-1 text-[10px] text-[var(--editor-muted)]"
                                >
                                  Down
                                </button>
                                <button
                                  type="button"
                                  onClick={() => removeOverlay(overlay.id)}
                                  className="rounded border border-red-500/40 px-2 py-1 text-[10px] text-red-300"
                                >
                                  Delete
                                </button>
                              </div>
                            </div>
                          );
                        })
                    )}
                  </div>
                </div>
              ) : null}

              {activeTab === "images" ? (
                <div className="space-y-3 text-xs text-[var(--editor-muted)]">
                  <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-3 py-2 text-[11px] text-[var(--editor-text)]">
                    Upload image/logo
                    <input
                      type="file"
                      accept="image/*"
                      className="hidden"
                      onChange={(event) => {
                        const file = event.target.files?.[0];
                        if (!file) return;
                        void handleUploadAsset(file);
                        event.target.value = "";
                      }}
                    />
                  </label>

                  <div className="space-y-2">
                    {project.assets.length === 0 ? (
                      <p className="rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] p-2 text-[11px]">
                        Upload an image or logo to use on timeline.
                      </p>
                    ) : (
                      project.assets.map((asset) => (
                        <div key={asset.id} className="rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] p-2">
                          <p className="truncate text-[11px] text-[var(--editor-text)]">{asset.original_filename || asset.id}</p>
                          <div className="mt-2 flex justify-end">
                            <button
                              type="button"
                              onClick={() => insertImageLayer(asset.id)}
                              className="rounded border border-[var(--editor-border)] px-2 py-1 text-[10px] text-[var(--editor-text)]"
                            >
                              Insert layer
                            </button>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              ) : null}

              {activeTab === "templates" ? (
                <div className="rounded-md border border-dashed border-[var(--editor-border)] bg-[var(--editor-panel-2)] p-4 text-xs text-[var(--editor-muted)]">
                  Templates panel is reserved for reusable clip layouts in a later pass.
                </div>
              ) : null}

              {activeTab === "brand" ? (
                <div className="rounded-md border border-dashed border-[var(--editor-border)] bg-[var(--editor-panel-2)] p-4 text-xs text-[var(--editor-muted)]">
                  Brand styles panel is reserved for saved fonts/colors/logo kits in a later pass.
                </div>
              ) : null}
            </div>
            </aside>

            <div
              role="separator"
              aria-orientation="vertical"
              onPointerDown={(event) => beginSplitterDrag("left", event)}
              className="mx-1 w-2 shrink-0 cursor-col-resize rounded bg-[var(--editor-border)]/70 hover:bg-[#3C6DFF]/80"
            />

            <section className="min-h-0 min-w-0 flex-1 overflow-hidden rounded-xl border border-[var(--editor-border)] bg-[var(--editor-panel)] p-3">
            <div className="flex h-full flex-col gap-3">
              <div className="flex min-h-0 flex-1 items-center justify-center rounded-xl border border-[var(--editor-border)] bg-[var(--editor-canvas)] p-3">
                <VideoPreviewCanvas
                  ref={videoPreviewRef}
                  sourceUrl={sourceUrl}
                  sourcePlayerUrl={sourcePlayerUrl}
                  previewStatus={editorPreviewStatus}
                  usingPreviewProxy={usingEditorPreviewProxy}
                  sourceKind={sourceKind}
                  preparingPreview={preparingPreview}
                  forceSafeMode={false}
                  mediaOffsetSec={previewOffsetSec || 0}
                  project={projectState}
                  assets={project.assets}
                  currentTimeSec={currentTimeSec}
                  isPlaying={isPlaying}
                  showSafeAreas={showSafeAreas}
                  selectedOverlayId={selection.kind === "overlay" ? selection.overlayId : null}
                  selectedCaptionGroup={selection.kind === "caption_style"}
                  onCurrentTimeChange={(seconds) => setCurrentTimeSec(seconds)}
                  onDurationResolved={(seconds) => {
                    setMediaDurationSec((prev) => Math.max(prev, (previewOffsetSec || 0) + seconds, trimEnd));
                  }}
                  onSelectVideo={() => setSelection({ kind: "video" })}
                  onSelectCaptionGroup={() => setSelection({ kind: "caption_style" })}
                  onSelectOverlay={(id) => {
                    if (!id) {
                      setSelection({ kind: "video" });
                      return;
                    }
                    setSelection({ kind: "overlay", overlayId: id });
                  }}
                  onOverlayPatch={(overlayId, patch) => {
                    replaceOverlay(overlayId, patch, true);
                  }}
                  onCaptionGroupPatch={(patch) => {
                    updateCaptionGroup(patch, true);
                  }}
                  onPlayingChange={setIsPlaying}
                  onPreviewHealthChange={setPreviewDiagnostics}
                />
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-3 py-2 text-xs text-[var(--editor-muted)]">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      if (isPlaying) {
                        handleStopPlayback();
                      } else {
                        void handleStartPlayback();
                      }
                    }}
                    className="rounded-md border border-[var(--editor-border)] px-2.5 py-1 text-xs text-[var(--editor-text)]"
                  >
                    {isPlaying ? "Pause" : "Play"}
                  </button>
                  <button
                    type="button"
                    onClick={handleJumpToStart}
                    className="rounded-md border border-[var(--editor-border)] px-2.5 py-1 text-xs text-[var(--editor-muted)]"
                  >
                    Start Clip
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleReplay()}
                    className="rounded-md border border-[var(--editor-border)] px-2.5 py-1 text-xs text-[var(--editor-muted)]"
                  >
                    Replay Clip
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleRegeneratePreview()}
                    disabled={!project || editorPreviewStatus === "pending"}
                    className="rounded-md border border-[var(--editor-border)] px-2.5 py-1 text-xs text-[var(--editor-muted)] disabled:opacity-50"
                  >
                    Regenerate Preview
                  </button>
                </div>
                <div className="flex items-center gap-3">
                  <label className="inline-flex items-center gap-1">
                    <input
                      type="checkbox"
                      checked={showSafeAreas}
                      onChange={(event) => setShowSafeAreas(event.target.checked)}
                    />
                    Safe area guides
                  </label>
                  <span>
                    {formatTime(currentTimeSec)} / {formatTime(effectiveDurationSec)}
                  </span>
                </div>
              </div>

              <div className="rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-3 py-1.5 text-[11px] text-[var(--editor-subtle)]">
                Preview: source={sourceKind}
                {" · "}proxy={editorPreviewStatus || "unknown"}
                {" · "}offset={(previewOffsetSec || 0).toFixed(2)}s
                {" · "}status={previewDiagnostics?.state || "loading"}
                {" · "}readyState={previewDiagnostics?.ready_state ?? 0}
                {" · "}video={previewDiagnostics?.video_width ?? 0}x{previewDiagnostics?.video_height ?? 0}
                {" · "}time={(previewDiagnostics?.current_time_sec ?? currentTimeSec).toFixed(2)}s
                {previewError ? ` · error=${previewError}` : ""}
              </div>
            </div>
            </section>

            <div
              role="separator"
              aria-orientation="vertical"
              onPointerDown={(event) => beginSplitterDrag("right", event)}
              className="mx-1 w-2 shrink-0 cursor-col-resize rounded bg-[var(--editor-border)]/70 hover:bg-[#3C6DFF]/80"
            />

            <aside
              className="min-h-0 shrink-0 overflow-y-auto rounded-xl border border-[var(--editor-border)] bg-[var(--editor-panel)] p-3"
              style={{ width: `${rightPaneWidth}px` }}
            >
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--editor-muted)]">Inspector</p>

            {selection.kind === "video" ? (
              <div className="space-y-3 text-xs text-[var(--editor-muted)]">
                <p className="text-[11px] uppercase tracking-wide text-[var(--editor-subtle)]">Video Transform</p>

                <label className="block">
                  Fit Mode
                  <select
                    value={projectState.reframe.fit_mode || "fill"}
                    onChange={(event) =>
                      applyProjectMutation(
                        (prev) => ({
                          ...prev,
                          reframe: {
                            ...prev.reframe,
                            fit_mode: event.target.value as "fit" | "fill",
                          },
                        }),
                        { recordHistory: true, coalesce: false }
                      )
                    }
                    className="mt-1 w-full rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2 py-1 text-sm text-[var(--editor-text)]"
                  >
                    <option value="fill">Fill canvas</option>
                    <option value="fit">Fit canvas</option>
                  </select>
                </label>

                <label className="block">
                  Zoom ({projectState.reframe.zoom.toFixed(2)}x)
                  <input
                    type="range"
                    min={1}
                    max={3}
                    step={0.01}
                    value={projectState.reframe.zoom}
                    onChange={(event) =>
                      applyProjectMutation(
                        (prev) => ({
                          ...prev,
                          reframe: {
                            ...prev.reframe,
                            zoom: Number(event.target.value),
                          },
                        }),
                        { recordHistory: true, coalesce: true }
                      )
                    }
                    className="mt-1 w-full"
                  />
                </label>

                <label className="block">
                  Horizontal Position ({projectState.reframe.anchor_x.toFixed(2)})
                  <input
                    type="range"
                    min={0}
                    max={1}
                    step={0.01}
                    value={projectState.reframe.anchor_x}
                    onChange={(event) =>
                      applyProjectMutation(
                        (prev) => ({
                          ...prev,
                          reframe: {
                            ...prev.reframe,
                            anchor_x: Number(event.target.value),
                          },
                        }),
                        { recordHistory: true, coalesce: true }
                      )
                    }
                    className="mt-1 w-full"
                  />
                </label>

                <label className="block">
                  Vertical Position ({projectState.reframe.anchor_y.toFixed(2)})
                  <input
                    type="range"
                    min={0}
                    max={1}
                    step={0.01}
                    value={projectState.reframe.anchor_y}
                    onChange={(event) =>
                      applyProjectMutation(
                        (prev) => ({
                          ...prev,
                          reframe: {
                            ...prev.reframe,
                            anchor_y: Number(event.target.value),
                          },
                        }),
                        { recordHistory: true, coalesce: true }
                      )
                    }
                    className="mt-1 w-full"
                  />
                </label>
              </div>
            ) : null}

            {selection.kind === "caption_style" ? (
              <div className="space-y-3 text-xs text-[var(--editor-muted)]">
                <p className="text-[11px] uppercase tracking-wide text-[var(--editor-subtle)]">Caption Style</p>

                <label className="block">
                  Font size
                  <input
                    type="number"
                    min={12}
                    max={120}
                    value={projectState.captions.style.font_size}
                    onChange={(event) =>
                      updateCaptionConfig(
                        {
                          ...projectState.captions,
                          style: {
                            ...projectState.captions.style,
                            font_size: Number(event.target.value) || 54,
                          },
                        },
                        true
                      )
                    }
                    className="mt-1 w-full rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2 py-1 text-sm text-[var(--editor-text)]"
                  />
                </label>

                <label className="block">
                  Position
                  <select
                    value={projectState.captions.style.position}
                    onChange={(event) =>
                      updateCaptionConfig(
                        {
                          ...projectState.captions,
                          style: {
                            ...projectState.captions.style,
                            position: event.target.value as "top" | "middle" | "bottom",
                          },
                        },
                        false
                      )
                    }
                    className="mt-1 w-full rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2 py-1 text-sm text-[var(--editor-text)]"
                  >
                    <option value="top">Top</option>
                    <option value="middle">Middle</option>
                    <option value="bottom">Bottom</option>
                  </select>
                </label>

                <div className="grid grid-cols-2 gap-2">
                  <label className="block">
                    X position ({captionGroupAnchorX.toFixed(2)})
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.01}
                      value={captionGroupAnchorX}
                      onChange={(event) => updateCaptionGroup({ anchor_x: Number(event.target.value) }, true)}
                      className="mt-1 w-full"
                    />
                  </label>
                  <label className="block">
                    Y position ({captionGroupAnchorY.toFixed(2)})
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.01}
                      value={captionGroupAnchorY}
                      onChange={(event) => updateCaptionGroup({ anchor_y: Number(event.target.value) }, true)}
                      className="mt-1 w-full"
                    />
                  </label>
                </div>

                <label className="block">
                  Group scale ({captionGroupScale.toFixed(2)}x)
                  <input
                    type="range"
                    min={0.35}
                    max={3}
                    step={0.01}
                    value={captionGroupScale}
                    onChange={(event) => updateCaptionGroup({ scale: Number(event.target.value) }, true)}
                    className="mt-1 w-full"
                  />
                </label>

                <label className="block">
                  Text color
                  <input
                    type="color"
                    value={(projectState.captions.style.text_color || "#FFFFFF").slice(0, 7)}
                    onChange={(event) =>
                      updateCaptionConfig(
                        {
                          ...projectState.captions,
                          style: {
                            ...projectState.captions.style,
                            text_color: event.target.value,
                          },
                        },
                        true
                      )
                    }
                    className="mt-1 h-9 w-full rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-1"
                  />
                </label>

                <label className="block">
                  Background color
                  <input
                    type="color"
                    value={(projectState.captions.style.bg_color || "#000000").slice(0, 7)}
                    onChange={(event) =>
                      updateCaptionConfig(
                        {
                          ...projectState.captions,
                          style: {
                            ...projectState.captions.style,
                            bg_color: `${event.target.value}CC`,
                          },
                        },
                        true
                      )
                    }
                    className="mt-1 h-9 w-full rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-1"
                  />
                </label>

                <label className="inline-flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={projectState.captions.style.uppercase}
                    onChange={(event) =>
                      updateCaptionConfig(
                        {
                          ...projectState.captions,
                          style: {
                            ...projectState.captions.style,
                            uppercase: event.target.checked,
                          },
                        },
                        false
                      )
                    }
                  />
                  Uppercase
                </label>

                <label className="inline-flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={projectState.captions.active_word_highlight}
                    onChange={(event) =>
                      updateCaptionConfig(
                        {
                          ...projectState.captions,
                          active_word_highlight: event.target.checked,
                        },
                        false
                      )
                    }
                  />
                  Active word highlight
                </label>
              </div>
            ) : null}

            {selection.kind === "caption_segment" && captionSegment ? (
              <div className="space-y-3 text-xs text-[var(--editor-muted)]">
                <p className="text-[11px] uppercase tracking-wide text-[var(--editor-subtle)]">Caption Segment</p>

                <label className="block">
                  Text
                  <textarea
                    rows={3}
                    value={captionSegment.text}
                    onChange={(event) => updateCaptionSegment(selection.index, { text: event.target.value })}
                    className="mt-1 w-full rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2 py-1 text-sm text-[var(--editor-text)]"
                  />
                </label>

                <label className="block">
                  Start (s)
                  <input
                    type="number"
                    step={0.05}
                    value={captionSegment.start_sec}
                    onChange={(event) => updateCaptionSegment(selection.index, { start_sec: Number(event.target.value) || 0 })}
                    className="mt-1 w-full rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2 py-1 text-sm text-[var(--editor-text)]"
                  />
                </label>

                <label className="block">
                  End (s)
                  <input
                    type="number"
                    step={0.05}
                    value={captionSegment.end_sec}
                    onChange={(event) => updateCaptionSegment(selection.index, { end_sec: Number(event.target.value) || 0 })}
                    className="mt-1 w-full rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2 py-1 text-sm text-[var(--editor-text)]"
                  />
                </label>
              </div>
            ) : null}

            {selectedTextOverlay ? (
              <div className="space-y-3 text-xs text-[var(--editor-muted)]">
                <p className="text-[11px] uppercase tracking-wide text-[var(--editor-subtle)]">Text Layer</p>

                <label className="block">
                  Text
                  <textarea
                    rows={3}
                    value={selectedTextOverlay.content || ""}
                    onChange={(event) => replaceOverlay(selectedTextOverlay.id, { content: event.target.value }, true)}
                    className="mt-1 w-full rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2 py-1 text-sm text-[var(--editor-text)]"
                  />
                </label>

                <div className="grid grid-cols-2 gap-2">
                  <label className="block">
                    Start
                    <input
                      type="number"
                      step={0.1}
                      value={selectedTextOverlay.start_sec}
                      onChange={(event) => replaceOverlay(selectedTextOverlay.id, { start_sec: Number(event.target.value) || trimStart }, false)}
                      className="mt-1 w-full rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2 py-1 text-sm text-[var(--editor-text)]"
                    />
                  </label>
                  <label className="block">
                    End
                    <input
                      type="number"
                      step={0.1}
                      value={selectedTextOverlay.end_sec}
                      onChange={(event) => replaceOverlay(selectedTextOverlay.id, { end_sec: Number(event.target.value) || trimEnd }, false)}
                      className="mt-1 w-full rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2 py-1 text-sm text-[var(--editor-text)]"
                    />
                  </label>
                  <label className="block">
                    Width (%)
                    <input
                      type="number"
                      min={2}
                      max={100}
                      value={Math.round(selectedTextOverlay.width * 100)}
                      onChange={(event) =>
                        replaceOverlay(selectedTextOverlay.id, { width: clamp((Number(event.target.value) || 50) / 100, 0.02, 1) }, true)
                      }
                      className="mt-1 w-full rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2 py-1 text-sm text-[var(--editor-text)]"
                    />
                  </label>
                  <label className="block">
                    Height (%)
                    <input
                      type="number"
                      min={2}
                      max={100}
                      value={Math.round(selectedTextOverlay.height * 100)}
                      onChange={(event) =>
                        replaceOverlay(selectedTextOverlay.id, { height: clamp((Number(event.target.value) || 14) / 100, 0.02, 1) }, true)
                      }
                      className="mt-1 w-full rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2 py-1 text-sm text-[var(--editor-text)]"
                    />
                  </label>
                  <label className="block">
                    Font size
                    <input
                      type="number"
                      value={selectedTextOverlay.style?.font_size || 42}
                      onChange={(event) =>
                        replaceOverlay(
                          selectedTextOverlay.id,
                          { style: { ...(selectedTextOverlay.style || {}), font_size: Number(event.target.value) || 42 } },
                          true
                        )
                      }
                      className="mt-1 w-full rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2 py-1 text-sm text-[var(--editor-text)]"
                    />
                  </label>
                  <label className="block">
                    Weight
                    <input
                      type="number"
                      min={300}
                      max={900}
                      step={100}
                      value={selectedTextOverlay.style?.font_weight || 700}
                      onChange={(event) =>
                        replaceOverlay(
                          selectedTextOverlay.id,
                          { style: { ...(selectedTextOverlay.style || {}), font_weight: Number(event.target.value) || 700 } },
                          true
                        )
                      }
                      className="mt-1 w-full rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2 py-1 text-sm text-[var(--editor-text)]"
                    />
                  </label>
                </div>

                <label className="block">
                  Alignment
                  <select
                    value={selectedTextOverlay.style?.alignment || "center"}
                    onChange={(event) =>
                      replaceOverlay(
                        selectedTextOverlay.id,
                        {
                          style: {
                            ...(selectedTextOverlay.style || {}),
                            alignment: event.target.value as "left" | "center" | "right",
                          },
                        },
                        false
                      )
                    }
                    className="mt-1 w-full rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2 py-1 text-sm text-[var(--editor-text)]"
                  >
                    <option value="left">Left</option>
                    <option value="center">Center</option>
                    <option value="right">Right</option>
                  </select>
                </label>

                <div className="grid grid-cols-2 gap-2">
                  <label className="block">
                    Text color
                    <input
                      type="color"
                      value={(selectedTextOverlay.style?.color || "#FFFFFF").slice(0, 7)}
                      onChange={(event) =>
                        replaceOverlay(
                          selectedTextOverlay.id,
                          { style: { ...(selectedTextOverlay.style || {}), color: event.target.value } },
                          true
                        )
                      }
                      className="mt-1 h-9 w-full rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-1"
                    />
                  </label>
                  <label className="block">
                    BG color
                    <input
                      type="color"
                      value={(selectedTextOverlay.style?.bg_color || "#1D3FD0").slice(0, 7)}
                      onChange={(event) =>
                        replaceOverlay(
                          selectedTextOverlay.id,
                          { style: { ...(selectedTextOverlay.style || {}), bg_color: `${event.target.value}CC` } },
                          true
                        )
                      }
                      className="mt-1 h-9 w-full rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-1"
                    />
                  </label>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <label className="block">
                    X position
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.01}
                      value={selectedTextOverlay.x}
                      onChange={(event) => replaceOverlay(selectedTextOverlay.id, { x: Number(event.target.value) }, true)}
                      className="mt-1 w-full"
                    />
                  </label>
                  <label className="block">
                    Y position
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.01}
                      value={selectedTextOverlay.y}
                      onChange={(event) => replaceOverlay(selectedTextOverlay.id, { y: Number(event.target.value) }, true)}
                      className="mt-1 w-full"
                    />
                  </label>
                </div>
              </div>
            ) : null}

            {selectedImageOverlay ? (
              <div className="space-y-3 text-xs text-[var(--editor-muted)]">
                <p className="text-[11px] uppercase tracking-wide text-[var(--editor-subtle)]">Image / Logo Layer</p>

                <div className="grid grid-cols-2 gap-2">
                  <label className="block">
                    Start
                    <input
                      type="number"
                      step={0.1}
                      value={selectedImageOverlay.start_sec}
                      onChange={(event) => replaceOverlay(selectedImageOverlay.id, { start_sec: Number(event.target.value) || trimStart }, false)}
                      className="mt-1 w-full rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2 py-1 text-sm text-[var(--editor-text)]"
                    />
                  </label>
                  <label className="block">
                    End
                    <input
                      type="number"
                      step={0.1}
                      value={selectedImageOverlay.end_sec}
                      onChange={(event) => replaceOverlay(selectedImageOverlay.id, { end_sec: Number(event.target.value) || trimEnd }, false)}
                      className="mt-1 w-full rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2 py-1 text-sm text-[var(--editor-text)]"
                    />
                  </label>

                  <label className="block">
                    Width (%)
                    <input
                      type="number"
                      min={2}
                      max={100}
                      value={Math.round(selectedImageOverlay.width * 100)}
                      onChange={(event) =>
                        replaceOverlay(selectedImageOverlay.id, { width: clamp((Number(event.target.value) || 20) / 100, 0.02, 1) }, true)
                      }
                      className="mt-1 w-full rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2 py-1 text-sm text-[var(--editor-text)]"
                    />
                  </label>
                  <label className="block">
                    Height (%)
                    <input
                      type="number"
                      min={2}
                      max={100}
                      value={Math.round(selectedImageOverlay.height * 100)}
                      onChange={(event) =>
                        replaceOverlay(selectedImageOverlay.id, { height: clamp((Number(event.target.value) || 20) / 100, 0.02, 1) }, true)
                      }
                      className="mt-1 w-full rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2 py-1 text-sm text-[var(--editor-text)]"
                    />
                  </label>

                  <label className="block">
                    Opacity (%)
                    <input
                      type="number"
                      min={0}
                      max={100}
                      value={Math.round((selectedImageOverlay.opacity ?? 1) * 100)}
                      onChange={(event) =>
                        replaceOverlay(selectedImageOverlay.id, { opacity: clamp((Number(event.target.value) || 100) / 100, 0, 1) }, true)
                      }
                      className="mt-1 w-full rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2 py-1 text-sm text-[var(--editor-text)]"
                    />
                  </label>
                  <label className="block">
                    Rotation
                    <input
                      type="number"
                      value={selectedImageOverlay.rotation_deg}
                      onChange={(event) => replaceOverlay(selectedImageOverlay.id, { rotation_deg: Number(event.target.value) || 0 }, true)}
                      className="mt-1 w-full rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2 py-1 text-sm text-[var(--editor-text)]"
                    />
                  </label>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <label className="block">
                    X position
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.01}
                      value={selectedImageOverlay.x}
                      onChange={(event) => replaceOverlay(selectedImageOverlay.id, { x: Number(event.target.value) }, true)}
                      className="mt-1 w-full"
                    />
                  </label>
                  <label className="block">
                    Y position
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.01}
                      value={selectedImageOverlay.y}
                      onChange={(event) => replaceOverlay(selectedImageOverlay.id, { y: Number(event.target.value) }, true)}
                      className="mt-1 w-full"
                    />
                  </label>
                </div>
              </div>
            ) : null}

            {selection.kind !== "video" && selection.kind !== "caption_style" && !captionSegment && !selectedOverlay ? (
              <p className="text-xs text-[var(--editor-muted)]">Select a timeline block or layer to edit settings.</p>
            ) : null}

            {latestRender ? (
              <div className="mt-4 rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] p-2 text-xs text-[var(--editor-muted)]">
                <p>
                  Latest render: <span className="text-[var(--editor-text)]">{latestRender.status}</span>
                </p>
                {latestRender.error_message ? <p className="mt-1 text-red-300">{latestRender.error_message}</p> : null}
                {latestRender.download_url ? (
                  <a href={latestRender.download_url} target="_blank" rel="noreferrer" className="mt-1 inline-block text-[#8FB2FF]">
                    Download MP4
                  </a>
                ) : null}
              </div>
            ) : null}
            </aside>
          </div>

          <div
            role="separator"
            aria-orientation="horizontal"
            onPointerDown={(event) => beginSplitterDrag("timeline", event)}
            className="h-2 shrink-0 cursor-row-resize rounded bg-[var(--editor-border)]/70 hover:bg-[#3C6DFF]/80"
          />

          <div className="shrink-0">
            <EditorTimeline
            durationSec={effectiveDurationSec}
            currentTimeSec={currentTimeSec}
            trimStartSec={trimStart}
            trimEndSec={trimEnd}
            isPlaying={isPlaying}
            timelineZoom={timelineZoom}
            heightPx={timelineHeight}
            tracks={timelineTracks}
            onTimelineZoomChange={setTimelineZoom}
            onCurrentTimeChange={(seconds) => {
              seekPreview(seconds);
            }}
            onTrimChange={(start, end) => {
              const safeStart = clamp(start, 0, effectiveDurationSec || end);
              const safeEnd = clamp(end, safeStart + 0.1, effectiveDurationSec || end + 0.1);
              applyProjectMutation(
                (prev) => ({
                  ...prev,
                  trim: {
                    start_sec: safeStart,
                    end_sec: safeEnd,
                  },
                }),
                { recordHistory: true, coalesce: false }
              );
            }}
            onJumpToStart={handleJumpToStart}
            onReplay={() => void handleReplay()}
            onStart={() => void handleStartPlayback()}
            onStop={handleStopPlayback}
            onSelectTrackItem={selectTimelineItem}
            onUpdateTrackItemTiming={updateOverlayTimingFromTimeline}
          />
          </div>
        </div>
      </div>
    </div>
  );
}
