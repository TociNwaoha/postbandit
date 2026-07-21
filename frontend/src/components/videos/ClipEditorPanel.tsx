"use client";

import Link from "next/link";
import { getSession } from "next-auth/react";
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent } from "react";

import { Card } from "@/components/ui/Card";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { CarouselSchedulePanel } from "@/components/videos/CarouselSchedulePanel";
import { SocialPublishPanel } from "@/components/videos/SocialPublishPanel";
import { api, ApiError } from "@/lib/api";
import {
  buildCaptionPreviewText,
  formatCaptionColorVariantLabel,
  formatCaptionStyleLabel,
  getCaptionColorVariantMeta,
  getCaptionColorVariantOptions,
  getCaptionPreviewLayout,
  getCaptionStyleMeta,
  getCaptionStyleOptions,
  getCaptionStyleTheme,
  wrapCaptionPreviewText,
} from "@/lib/captionPreview";
import {
  AspectRatio,
  CaptionCadence,
  CaptionColorVariant,
  CaptionFormat,
  CaptionStyle,
  Clip,
  ClipOverlayAsset,
  Export,
  ExportOverlayImageConfig,
  ExportOverlayTextConfig,
  Video,
} from "@/types";

interface ClipEditorPanelProps {
  video: Video;
  initialClip: Clip;
  initialExports: Export[];
  initialScheduleAt?: string;
}

const ACTIVE_EXPORT_STATUSES = new Set(["queued", "rendering"]);
const CAPTION_VERTICAL_MIN = 0;
const CAPTION_VERTICAL_MAX = 98;
const CAPTION_SCALE_MIN = 0.25;
const CAPTION_SCALE_MAX = 2;
const OVERLAY_IMAGE_WIDTH_MIN = 0.05;
const OVERLAY_IMAGE_WIDTH_MAX = 0.8;
const HIGHLIGHT_COLORS = ["#FACC15", "#22D3EE", "#FB7185", "#4ADE80", "#C084FC"];
const DEFAULT_IMAGE_OVERLAY: ExportOverlayImageConfig = {
  x: 0.82,
  y: 0.15,
  width: 0.22,
  opacity: 1,
};
const DEFAULT_TEXT_OVERLAY: ExportOverlayTextConfig = {
  text: "",
  x: 0.5,
  y: 0.2,
  font_size: 52,
  text_color: "#FFFFFF",
  highlights: [],
};

const exportStatusStyles: Record<string, string> = {
  queued: "border border-[var(--app-border)] bg-[var(--app-surface-soft)] text-[var(--app-subtle)]",
  rendering: "bg-blue-500/20 text-blue-700 animate-pulse",
  ready: "bg-emerald-500/20 text-emerald-700",
  error: "bg-red-500/20 text-red-700",
};

function formatTimeBoundary(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds));
  const mins = Math.floor(safe / 60);
  const secs = safe % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

function formatClockTime(seconds: number | null | undefined): string {
  const safeValue = Number(seconds || 0);
  if (!Number.isFinite(safeValue) || safeValue <= 0) return "0:00";
  const whole = Math.floor(safeValue);
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const secs = whole % 60;
  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  }
  return `${minutes}:${secs.toString().padStart(2, "0")}`;
}

function formatSeconds(seconds: number | null | undefined): string {
  const value = Number(seconds || 0);
  if (value <= 0) return "0.0s";
  return `${value.toFixed(1)}s`;
}

function statusLabel(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function parseNumberInput(value: string): number | null {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return null;
  return parsed;
}

function parseResolutionAspectRatio(resolution: string | null | undefined): number | null {
  if (!resolution) return null;
  const match = resolution.trim().match(/^(\d+)\s*x\s*(\d+)$/i);
  if (!match) return null;
  const width = Number(match[1]);
  const height = Number(match[2]);
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return null;
  return width / height;
}

function aspectRatioToValue(aspectRatio: AspectRatio, sourceAspectRatio: number): number {
  if (aspectRatio === "9:16") return 9 / 16;
  if (aspectRatio === "16:9") return 16 / 9;
  if (aspectRatio === "1:1") return 1;
  return sourceAspectRatio;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function hexToRgba(hex: string, alpha: number): string {
  const normalized = hex.replace("#", "");
  if (!/^[\da-fA-F]{6}$/.test(normalized)) {
    return `rgba(0,0,0,${alpha})`;
  }
  const r = Number.parseInt(normalized.slice(0, 2), 16);
  const g = Number.parseInt(normalized.slice(2, 4), 16);
  const b = Number.parseInt(normalized.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

async function uploadClipOverlayAsset(clipId: string, file: File): Promise<ClipOverlayAsset> {
  const session = await getSession();
  const token = (session as any)?.accessToken;
  const form = new FormData();
  form.append("file", file);
  const headers = token ? { Authorization: `Bearer ${token}` } : undefined;
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  let response: Response;
  try {
    response = await fetch(`${apiUrl}/api/clips/${clipId}/overlay-assets`, {
      method: "POST",
      body: form,
      headers,
    });
  } catch {
    response = await fetch(`/api/backend/clips/${clipId}/overlay-assets`, {
      method: "POST",
      body: form,
      headers,
    });
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Failed to upload image" }));
    throw new Error(body.detail || "Failed to upload image");
  }
  return (await response.json()) as ClipOverlayAsset;
}

export function ClipEditorPanel({ video, initialClip, initialExports, initialScheduleAt }: ClipEditorPanelProps) {
  const sourceAspectFromResolution = parseResolutionAspectRatio(video.resolution);
  const [clip, setClip] = useState<Clip>(initialClip);
  const [clipStart, setClipStart] = useState<string>(initialClip.start_time.toFixed(2));
  const [clipEnd, setClipEnd] = useState<string>(initialClip.end_time.toFixed(2));
  const [saveLoading, setSaveLoading] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const [aspectRatio, setAspectRatio] = useState<AspectRatio>("original");
  const [captionStyle, setCaptionStyle] = useState<CaptionStyle>("bold_boxed");
  const [captionColorVariant, setCaptionColorVariant] = useState<CaptionColorVariant>("classic");
  const [captionFormat, setCaptionFormat] = useState<CaptionFormat>("burned_in");
  const [captionCadence, setCaptionCadence] = useState<CaptionCadence>("split_line");
  const [captionVerticalPosition, setCaptionVerticalPosition] = useState<number>(15);
  const [captionScale, setCaptionScale] = useState<number>(1);
  const [frameAnchorX, setFrameAnchorX] = useState<number>(0.5);
  const [frameAnchorY, setFrameAnchorY] = useState<number>(0.5);
  const [frameZoom, setFrameZoom] = useState<number>(1);
  const [imageOverlayOpen, setImageOverlayOpen] = useState(false);
  const [textOverlayOpen, setTextOverlayOpen] = useState(false);
  const [overlayAsset, setOverlayAsset] = useState<ClipOverlayAsset | null>(null);
  const [overlayImageConfig, setOverlayImageConfig] =
    useState<ExportOverlayImageConfig>(DEFAULT_IMAGE_OVERLAY);
  const [overlayTextConfig, setOverlayTextConfig] =
    useState<ExportOverlayTextConfig>(DEFAULT_TEXT_OVERLAY);
  const [selectedHighlightColor, setSelectedHighlightColor] = useState(HIGHLIGHT_COLORS[0]);
  const [overlayUploadLoading, setOverlayUploadLoading] = useState(false);
  const [overlayError, setOverlayError] = useState<string | null>(null);
  const [exports, setExports] = useState<Export[]>(initialExports);
  const [exportsLoading, setExportsLoading] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [createExportLoading, setCreateExportLoading] = useState(false);
  const [createExportMessage, setCreateExportMessage] = useState<string | null>(null);

  const [mediaDuration, setMediaDuration] = useState<number | null>(video.duration_sec ?? null);
  const [sourceAspectRatio, setSourceAspectRatio] = useState<number | null>(sourceAspectFromResolution);
  const [playerCurrentTime, setPlayerCurrentTime] = useState<number>(0);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [isTimelineScrubbing, setIsTimelineScrubbing] = useState(false);
  const [isFrameDragging, setIsFrameDragging] = useState(false);
  const [isCaptionDragging, setIsCaptionDragging] = useState(false);
  const [isCaptionResizing, setIsCaptionResizing] = useState(false);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const framedVideoRef = useRef<HTMLVideoElement | null>(null);
  const framedPreviewRef = useRef<HTMLDivElement | null>(null);
  const timelineRef = useRef<HTMLDivElement | null>(null);
  const framingOverlayRef = useRef<HTMLDivElement | null>(null);
  const captionInteractionRef = useRef<{
    mode: "drag" | "resize" | null;
    startClientY: number;
    startVertical: number;
    startScale: number;
  }>({
    mode: null,
    startClientY: 0,
    startVertical: 15,
    startScale: 1,
  });
  const overlayInteractionRef = useRef<{
    mode: "image-drag" | "image-resize" | "text-drag" | null;
    startClientX: number;
    startWidth: number;
  }>({
    mode: null,
    startClientX: 0,
    startWidth: DEFAULT_IMAGE_OVERLAY.width,
  });
  const replayStopAtRef = useRef<number | null>(null);
  const replayActiveRef = useRef<boolean>(false);
  const replayTokenRef = useRef<number>(0);

  const sourceUrl = video.source_download_url || null;
  const activeExportExists = exports.some((item) => ACTIVE_EXPORT_STATUSES.has(item.status));

  const computedDuration = useMemo(() => {
    const start = parseNumberInput(clipStart);
    const end = parseNumberInput(clipEnd);
    if (start === null || end === null) return null;
    const duration = end - start;
    if (duration <= 0) return null;
    return duration;
  }, [clipStart, clipEnd]);

  const normalizedMediaDuration = useMemo(() => {
    const duration = Number(mediaDuration ?? video.duration_sec ?? 0);
    if (!Number.isFinite(duration) || duration <= 0) return null;
    return duration;
  }, [mediaDuration, video.duration_sec]);

  const normalizedClipRange = useMemo(() => {
    const start = parseNumberInput(clipStart);
    const end = parseNumberInput(clipEnd);
    if (start === null || end === null) return null;

    let safeStart = Math.max(0, start);
    let safeEnd = Math.max(0, end);
    if (normalizedMediaDuration) {
      safeStart = Math.min(safeStart, normalizedMediaDuration);
      safeEnd = Math.min(safeEnd, normalizedMediaDuration);
    }
    if (safeEnd <= safeStart) return null;

    return {
      start: safeStart,
      end: safeEnd,
      duration: safeEnd - safeStart,
    };
  }, [clipStart, clipEnd, normalizedMediaDuration]);

  const timelineMetrics = useMemo(() => {
    if (!normalizedMediaDuration || !normalizedClipRange) return null;
    const toPercent = (value: number) =>
      Math.min(100, Math.max(0, (value / normalizedMediaDuration) * 100));

    const clipStartPercent = toPercent(normalizedClipRange.start);
    const clipEndPercent = toPercent(normalizedClipRange.end);
    const clipWidthPercent = Math.max(0, clipEndPercent - clipStartPercent);
    const playheadPercent = toPercent(playerCurrentTime);

    return {
      clipStartPercent,
      clipEndPercent,
      clipWidthPercent,
      playheadPercent,
    };
  }, [normalizedMediaDuration, normalizedClipRange, playerCurrentTime]);

  const effectiveSourceAspectRatio = sourceAspectRatio ?? sourceAspectFromResolution ?? 16 / 9;

  const outputPreviewAspect = useMemo(
    () => aspectRatioToValue(aspectRatio, effectiveSourceAspectRatio),
    [aspectRatio, effectiveSourceAspectRatio]
  );
  const outputPreviewAspectRatioValue = useMemo(() => {
    if (aspectRatio === "9:16") return "9 / 16";
    if (aspectRatio === "16:9") return "16 / 9";
    if (aspectRatio === "1:1") return "1 / 1";
    return `${effectiveSourceAspectRatio}`;
  }, [aspectRatio, effectiveSourceAspectRatio]);

  const frameGeometry = useMemo(() => {
    const sourceAspect = Math.max(0.0001, effectiveSourceAspectRatio);
    const targetAspect = Math.max(0.0001, outputPreviewAspect);
    const safeZoom = clamp(frameZoom, 1, 3);

    let baseWidth = 1;
    let baseHeight = 1;
    if (sourceAspect > targetAspect) {
      baseWidth = targetAspect / sourceAspect;
      baseHeight = 1;
    } else {
      baseWidth = 1;
      baseHeight = sourceAspect / targetAspect;
    }

    const frameWidth = clamp(baseWidth / safeZoom, 0.01, 1);
    const frameHeight = clamp(baseHeight / safeZoom, 0.01, 1);
    const minCenterX = frameWidth / 2;
    const maxCenterX = 1 - frameWidth / 2;
    const minCenterY = frameHeight / 2;
    const maxCenterY = 1 - frameHeight / 2;

    return {
      targetAspect,
      frameWidth,
      frameHeight,
      minCenterX,
      maxCenterX,
      minCenterY,
      maxCenterY,
      safeZoom,
    };
  }, [effectiveSourceAspectRatio, outputPreviewAspect, frameZoom]);

  const clampedFrameAnchorX = useMemo(
    () => clamp(frameAnchorX, frameGeometry.minCenterX, frameGeometry.maxCenterX),
    [frameAnchorX, frameGeometry.maxCenterX, frameGeometry.minCenterX]
  );
  const clampedFrameAnchorY = useMemo(
    () => clamp(frameAnchorY, frameGeometry.minCenterY, frameGeometry.maxCenterY),
    [frameAnchorY, frameGeometry.maxCenterY, frameGeometry.minCenterY]
  );

  const frameOverlayStyle = useMemo(
    () => ({
      left: `${(clampedFrameAnchorX - frameGeometry.frameWidth / 2) * 100}%`,
      top: `${(clampedFrameAnchorY - frameGeometry.frameHeight / 2) * 100}%`,
      width: `${frameGeometry.frameWidth * 100}%`,
      height: `${frameGeometry.frameHeight * 100}%`,
    }),
    [clampedFrameAnchorX, clampedFrameAnchorY, frameGeometry.frameHeight, frameGeometry.frameWidth]
  );

  const captionPreviewLayout = useMemo(
    () => getCaptionPreviewLayout(captionStyle, aspectRatio, effectiveSourceAspectRatio),
    [captionStyle, aspectRatio, effectiveSourceAspectRatio]
  );
  const captionPreviewTheme = useMemo(
    () => getCaptionStyleTheme(captionStyle, captionColorVariant),
    [captionStyle, captionColorVariant]
  );
  const captionStyleMeta = useMemo(() => getCaptionStyleMeta(captionStyle), [captionStyle]);
  const captionStyleOptions = useMemo(() => getCaptionStyleOptions(), []);
  const captionColorVariantOptions = useMemo(() => getCaptionColorVariantOptions(), []);
  const captionColorVariantMeta = useMemo(
    () => getCaptionColorVariantMeta(captionColorVariant),
    [captionColorVariant]
  );
  const captionPreviewText = useMemo(
    () => buildCaptionPreviewText(clip.transcript_text),
    [clip.transcript_text]
  );
  const captionPreviewLines = useMemo(
    () =>
      wrapCaptionPreviewText(
        captionPreviewText,
        captionPreviewLayout.maxCharsPerLine,
        captionPreviewLayout.maxLines
      ),
    [captionPreviewLayout.maxCharsPerLine, captionPreviewLayout.maxLines, captionPreviewText]
  );
  const captionFontSizePx = useMemo(
    () => Math.max(14, Math.round(captionPreviewLayout.fontSizePx * captionScale)),
    [captionPreviewLayout.fontSizePx, captionScale]
  );
  const overlayTextWords = useMemo(
    () => overlayTextConfig.text.trim().split(/\s+/).filter(Boolean),
    [overlayTextConfig.text]
  );
  const overlayHighlightMap = useMemo(
    () =>
      new Map(
        overlayTextConfig.highlights.map((highlight) => [
          highlight.word_index,
          highlight.color,
        ])
      ),
    [overlayTextConfig.highlights]
  );

  const refreshExports = async () => {
    setExportsLoading(true);
    setExportError(null);
    try {
      const items = await api.get<Export[]>(`/api/exports?clip_id=${encodeURIComponent(clip.id)}`);
      setExports(items);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to load exports";
      setExportError(message);
    } finally {
      setExportsLoading(false);
    }
  };

  useEffect(() => {
    if (!activeExportExists) return;
    const timer = setInterval(() => {
      void refreshExports();
    }, 5000);
    return () => clearInterval(timer);
  }, [activeExportExists, clip.id]);

  const syncFramedPreviewTime = useCallback((time: number) => {
    const framed = framedVideoRef.current;
    if (!framed || !Number.isFinite(time)) return;
    if (Math.abs(framed.currentTime - time) > 0.08) {
      framed.currentTime = time;
    }
  }, []);

  const syncFramedPreviewPlayState = useCallback((isPlaying: boolean) => {
    const framed = framedVideoRef.current;
    if (!framed) return;
    if (isPlaying) {
      void framed.play().catch(() => undefined);
    } else {
      framed.pause();
    }
  }, []);

  const clearClipPlaybackMode = useCallback(() => {
    replayActiveRef.current = false;
    replayStopAtRef.current = null;
  }, []);

  const seekPlayerToTime = useCallback(
    async (nextTime: number) => {
      const player = videoRef.current;
      if (!player || !normalizedMediaDuration) return;
      const clamped = Math.min(Math.max(nextTime, 0), normalizedMediaDuration);
      if (Math.abs(player.currentTime - clamped) < 0.03) {
        setPlayerCurrentTime(clamped);
        return;
      }

      await new Promise<void>((resolve) => {
        let settled = false;
        let frameHandle: number | null = null;
        const settleTolerance = 0.08;
        const settleTimeoutMs = 2500;

        const cleanup = () => {
          if (frameHandle !== null) {
            window.cancelAnimationFrame(frameHandle);
          }
          player.removeEventListener("seeked", onSeeked);
          window.clearTimeout(timeoutHandle);
        };

        const finish = () => {
          if (settled) return;
          settled = true;
          cleanup();
          resolve();
        };

        const waitForConvergence = () => {
          if (Math.abs(player.currentTime - clamped) <= settleTolerance) {
            finish();
            return;
          }
          frameHandle = window.requestAnimationFrame(waitForConvergence);
        };

        const onSeeked = () => {
          waitForConvergence();
        };

        const timeoutHandle = window.setTimeout(() => {
          // Safety timeout: avoid hanging replay on edge-case browser seek stalls.
          finish();
        }, settleTimeoutMs);

        player.addEventListener("seeked", onSeeked);
        player.currentTime = clamped;
        waitForConvergence();
      });
      const settledTime = player.currentTime;
      setPlayerCurrentTime(settledTime);
      syncFramedPreviewTime(settledTime);
    },
    [normalizedMediaDuration, syncFramedPreviewTime]
  );

  const handleAspectRatioChange = (nextRatio: AspectRatio) => {
    setAspectRatio(nextRatio);
    setFrameAnchorX(0.5);
    setFrameAnchorY(0.5);
    setFrameZoom(1);
  };

  const updateFrameAnchorFromClientPoint = useCallback(
    (clientX: number, clientY: number) => {
      const overlay = framingOverlayRef.current;
      if (!overlay) return;
      const rect = overlay.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return;
      const normalizedX = (clientX - rect.left) / rect.width;
      const normalizedY = (clientY - rect.top) / rect.height;
      setFrameAnchorX(clamp(normalizedX, frameGeometry.minCenterX, frameGeometry.maxCenterX));
      setFrameAnchorY(clamp(normalizedY, frameGeometry.minCenterY, frameGeometry.maxCenterY));
    },
    [frameGeometry.maxCenterX, frameGeometry.maxCenterY, frameGeometry.minCenterX, frameGeometry.minCenterY]
  );

  const handleFramePointerDown = (event: PointerEvent<HTMLDivElement>) => {
    setIsFrameDragging(true);
    event.currentTarget.setPointerCapture(event.pointerId);
    updateFrameAnchorFromClientPoint(event.clientX, event.clientY);
  };

  const handleFramePointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!isFrameDragging) return;
    updateFrameAnchorFromClientPoint(event.clientX, event.clientY);
  };

  const handleFramePointerUp = (event: PointerEvent<HTMLDivElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    setIsFrameDragging(false);
  };

  const startCaptionInteraction = (
    mode: "drag" | "resize",
    event: PointerEvent<HTMLDivElement>
  ) => {
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    captionInteractionRef.current = {
      mode,
      startClientY: event.clientY,
      startVertical: captionVerticalPosition,
      startScale: captionScale,
    };
    if (mode === "drag") {
      setIsCaptionDragging(true);
    } else {
      setIsCaptionResizing(true);
    }
  };

  const handleCaptionPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const interaction = captionInteractionRef.current;
    if (!interaction.mode) return;
    const preview = framedPreviewRef.current;
    if (!preview) return;
    const rect = preview.getBoundingClientRect();
    if (rect.height <= 0) return;

    const deltaY = event.clientY - interaction.startClientY;
    if (interaction.mode === "drag") {
      const deltaPercent = (deltaY / rect.height) * 100;
      const nextVertical = clamp(
        interaction.startVertical - deltaPercent,
        CAPTION_VERTICAL_MIN,
        CAPTION_VERTICAL_MAX
      );
      setCaptionVerticalPosition(nextVertical);
      return;
    }

    const scaleDelta = (-deltaY / rect.height) * 1.5;
    const nextScale = clamp(
      interaction.startScale + scaleDelta,
      CAPTION_SCALE_MIN,
      CAPTION_SCALE_MAX
    );
    setCaptionScale(nextScale);
  };

  const stopCaptionInteraction = (event: PointerEvent<HTMLDivElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    captionInteractionRef.current.mode = null;
    setIsCaptionDragging(false);
    setIsCaptionResizing(false);
  };

  const startOverlayInteraction = (
    mode: "image-drag" | "image-resize" | "text-drag",
    event: PointerEvent<HTMLElement>
  ) => {
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    overlayInteractionRef.current = {
      mode,
      startClientX: event.clientX,
      startWidth: overlayImageConfig.width,
    };
  };

  const handleOverlayPointerMove = (event: PointerEvent<HTMLElement>) => {
    const interaction = overlayInteractionRef.current;
    if (!interaction.mode) return;
    const preview = framedPreviewRef.current;
    if (!preview) return;
    const rect = preview.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return;

    if (interaction.mode === "image-resize") {
      const delta = ((event.clientX - interaction.startClientX) / rect.width) * 2;
      setOverlayImageConfig((current) => ({
        ...current,
        width: clamp(
          interaction.startWidth + delta,
          OVERLAY_IMAGE_WIDTH_MIN,
          OVERLAY_IMAGE_WIDTH_MAX
        ),
      }));
      return;
    }

    const x = clamp((event.clientX - rect.left) / rect.width, 0, 1);
    const y = clamp((event.clientY - rect.top) / rect.height, 0, 1);
    if (interaction.mode === "image-drag") {
      setOverlayImageConfig((current) => ({ ...current, x, y }));
    } else {
      setOverlayTextConfig((current) => ({ ...current, x, y }));
    }
  };

  const stopOverlayInteraction = (event: PointerEvent<HTMLElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    overlayInteractionRef.current.mode = null;
  };

  const handleOverlayUpload = async (file: File) => {
    setOverlayUploadLoading(true);
    setOverlayError(null);
    const previous = overlayAsset;
    try {
      const uploaded = await uploadClipOverlayAsset(clip.id, file);
      setOverlayAsset(uploaded);
      setImageOverlayOpen(true);
      if (previous) {
        try {
          await api.delete(`/api/clips/${clip.id}/overlay-assets/${previous.id}`);
        } catch {
          // Existing exports may retain the previous asset snapshot.
        }
      }
    } catch (err) {
      setOverlayError(err instanceof Error ? err.message : "Failed to upload image");
    } finally {
      setOverlayUploadLoading(false);
    }
  };

  const handleRemoveOverlayAsset = async () => {
    const current = overlayAsset;
    setOverlayAsset(null);
    setOverlayImageConfig(DEFAULT_IMAGE_OVERLAY);
    if (!current) return;
    try {
      await api.delete(`/api/clips/${clip.id}/overlay-assets/${current.id}`);
    } catch (err) {
      if (!(err instanceof ApiError && err.status === 409)) {
        setOverlayError(err instanceof Error ? err.message : "Failed to delete image");
      }
    }
  };

  const toggleWordHighlight = (wordIndex: number) => {
    setOverlayTextConfig((current) => {
      const existing = current.highlights.find((item) => item.word_index === wordIndex);
      const remaining = current.highlights.filter((item) => item.word_index !== wordIndex);
      if (existing?.color === selectedHighlightColor) {
        return { ...current, highlights: remaining };
      }
      return {
        ...current,
        highlights: [
          ...remaining,
          { word_index: wordIndex, color: selectedHighlightColor },
        ].sort((left, right) => left.word_index - right.word_index),
      };
    });
  };

  const seekByTimelinePosition = useCallback(
    (clientX: number) => {
      const player = videoRef.current;
      const timeline = timelineRef.current;
      if (!player || !timeline || !normalizedMediaDuration) return;

      const rect = timeline.getBoundingClientRect();
      if (rect.width <= 0) return;
      const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
      const nextTime = ratio * normalizedMediaDuration;
      clearClipPlaybackMode();
      player.currentTime = nextTime;
      setPlayerCurrentTime(nextTime);
      syncFramedPreviewTime(nextTime);
    },
    [clearClipPlaybackMode, normalizedMediaDuration, syncFramedPreviewTime]
  );

  const handleTimelinePointerDown = (event: PointerEvent<HTMLDivElement>) => {
    setIsTimelineScrubbing(true);
    event.currentTarget.setPointerCapture(event.pointerId);
    seekByTimelinePosition(event.clientX);
  };

  const handleTimelinePointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!isTimelineScrubbing) return;
    seekByTimelinePosition(event.clientX);
  };

  const handleTimelinePointerUp = (event: PointerEvent<HTMLDivElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    setIsTimelineScrubbing(false);
  };

  const handleReplay = async () => {
    const player = videoRef.current;
    if (!player) return;
    if (!normalizedClipRange) return;

    const replayToken = replayTokenRef.current + 1;
    replayTokenRef.current = replayToken;

    clearClipPlaybackMode();
    player.pause();
    await seekPlayerToTime(normalizedClipRange.start);
    if (replayTokenRef.current !== replayToken) return;

    replayStopAtRef.current = normalizedClipRange.end;
    replayActiveRef.current = true;

    await player.play().catch(() => {
      clearClipPlaybackMode();
    });
  };

  const handleSeekStart = () => {
    const player = videoRef.current;
    if (!player) return;
    if (!normalizedClipRange) return;
    clearClipPlaybackMode();
    void seekPlayerToTime(normalizedClipRange.start);
  };

  const handleTimeUpdate = () => {
    const player = videoRef.current;
    if (!player) return;
    setPlayerCurrentTime(player.currentTime);
    syncFramedPreviewTime(player.currentTime);

    if (!replayActiveRef.current) return;
    const stopAt = replayStopAtRef.current;
    if (stopAt === null) return;
    if (player.currentTime >= stopAt - 0.03) {
      player.pause();
      player.currentTime = stopAt;
      setPlayerCurrentTime(stopAt);
      clearClipPlaybackMode();
    }
  };

  const handleSeeked = () => {
    const player = videoRef.current;
    if (!player) return;
    setPlayerCurrentTime(player.currentTime);
    syncFramedPreviewTime(player.currentTime);
    const stopAt = replayStopAtRef.current;
    if (replayActiveRef.current && stopAt !== null && player.currentTime > stopAt) {
      player.pause();
      player.currentTime = stopAt;
      setPlayerCurrentTime(stopAt);
      clearClipPlaybackMode();
    }
  };

  const handleSourcePlay = () => {
    syncFramedPreviewPlayState(true);
  };

  const handleSourcePause = () => {
    syncFramedPreviewPlayState(false);
  };

  const handleSaveTrim = async () => {
    setSaveError(null);
    setSaveMessage(null);

    const start = parseNumberInput(clipStart);
    const end = parseNumberInput(clipEnd);
    if (start === null || end === null) {
      setSaveError("Start and end must be valid numbers.");
      return;
    }

    let nextStart = Math.max(start, 0);
    let nextEnd = Math.max(end, 0);
    const maxDuration = mediaDuration ?? video.duration_sec ?? null;
    if (maxDuration && maxDuration > 0) {
      nextStart = Math.min(nextStart, maxDuration);
      nextEnd = Math.min(nextEnd, maxDuration);
    }

    if (nextEnd <= nextStart) {
      setSaveError("End time must be greater than start time.");
      return;
    }

    setSaveLoading(true);
    try {
      const updated = await api.patch<Clip>(`/api/clips/${clip.id}`, {
        video_id: video.id,
        start_time: nextStart,
        end_time: nextEnd,
      });
      setClip(updated);
      setClipStart(updated.start_time.toFixed(2));
      setClipEnd(updated.end_time.toFixed(2));
      setSaveMessage("Trim updated.");
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to save trim changes";
      setSaveError(message);
    } finally {
      setSaveLoading(false);
    }
  };

  const handleCreateExport = async () => {
    setCreateExportLoading(true);
    setCreateExportMessage(null);
    setExportError(null);
    try {
      const created = await api.post<Export>("/api/exports", {
        clip_id: clip.id,
        aspect_ratio: aspectRatio,
        caption_style: captionStyle,
        caption_color_variant: captionColorVariant,
        caption_format: captionFormat,
        caption_cadence: captionCadence,
        caption_vertical_position: captionVerticalPosition,
        caption_scale: captionScale,
        frame_anchor_x: clampedFrameAnchorX,
        frame_anchor_y: clampedFrameAnchorY,
        frame_zoom: frameGeometry.safeZoom,
        overlay_image_asset_id: overlayAsset?.id || null,
        overlay_image_config: overlayAsset ? overlayImageConfig : null,
        overlay_text_config: overlayTextConfig.text.trim()
          ? {
              ...overlayTextConfig,
              text: overlayTextConfig.text.trim(),
            }
          : null,
      });
      setExports((prev) => {
        const existingIndex = prev.findIndex((item) => item.id === created.id);
        if (existingIndex >= 0) {
          const next = [...prev];
          next[existingIndex] = created;
          return next;
        }
        return [created, ...prev];
      });
      if (created.reused) {
        setCreateExportMessage("Identical export is already in progress. Reusing existing export.");
      } else {
        setCreateExportMessage("Export created and queued.");
      }
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to create export";
      setExportError(message);
    } finally {
      setCreateExportLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-wide text-[var(--app-muted)]">Clip Editor</p>
            <h2 className="mt-1 text-xl font-semibold text-[var(--app-text)]">{clip.title || "Untitled clip"}</h2>
            <p className="mt-1 text-sm text-[var(--app-muted)]">
              Video: {video.title || "Untitled video"} • Clip {formatTimeBoundary(clip.start_time)} -{" "}
              {formatTimeBoundary(clip.end_time)}
            </p>
          </div>
          <Link
            href={`/videos/${video.id}`}
            className="rounded-md border border-[var(--app-border)] px-3 py-2 text-sm text-[var(--app-text)] hover:bg-[var(--app-surface-soft)]"
          >
            Back to Video
          </Link>
        </div>
      </Card>

      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <Card>
          <h3 className="text-sm font-semibold text-[var(--app-text)]">Preview</h3>
          <p className="mt-1 text-xs text-[var(--app-muted)]">
            Source preview with current clip boundaries and caption style preview for selected export settings.
          </p>
          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <div>
              <div className="mb-2 flex items-center justify-between text-xs text-[var(--app-muted)]">
                <span>Source Preview</span>
                <span>{formatClockTime(playerCurrentTime)}</span>
              </div>
              <div
                ref={framingOverlayRef}
                className="relative overflow-hidden rounded-lg border border-[var(--app-border)] bg-black"
                style={{ aspectRatio: `${effectiveSourceAspectRatio}` }}
              >
                {sourceUrl ? (
                  <video
                    ref={videoRef}
                    controls
                    src={sourceUrl}
                    className="h-full w-full bg-black object-contain"
                    onLoadedMetadata={(event) => {
                      const duration = event.currentTarget.duration;
                      if (Number.isFinite(duration) && duration > 0) {
                        setMediaDuration(duration);
                      }
                      const width = event.currentTarget.videoWidth;
                      const height = event.currentTarget.videoHeight;
                      if (width > 0 && height > 0) {
                        setSourceAspectRatio(width / height);
                      }
                      setPlayerCurrentTime(event.currentTarget.currentTime || 0);
                      syncFramedPreviewTime(event.currentTarget.currentTime || 0);
                    }}
                    onError={() => setPreviewError("Preview failed to load source video.")}
                    onTimeUpdate={handleTimeUpdate}
                    onSeeked={handleSeeked}
                    onPlay={handleSourcePlay}
                    onPause={handleSourcePause}
                  />
                ) : (
                  <div className="flex h-full items-center justify-center text-sm text-[var(--app-muted)]">
                    Source preview URL is unavailable for this video.
                  </div>
                )}

                <div
                  className="absolute inset-x-0 bottom-14 top-0 z-10 cursor-crosshair touch-none"
                  onPointerDown={handleFramePointerDown}
                  onPointerMove={handleFramePointerMove}
                  onPointerUp={handleFramePointerUp}
                  onPointerCancel={handleFramePointerUp}
                />

                <div className="pointer-events-none absolute inset-0 z-20">
                  <div
                    className="absolute border-2 border-[#1D3FD0] bg-[#1D3FD0]/10 shadow-[0_0_0_9999px_rgba(2,6,23,0.45)]"
                    style={frameOverlayStyle}
                  >
                    <div className="absolute left-1/2 top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#1633B8]" />
                  </div>
                </div>
              </div>
              <p className="mt-2 text-xs text-[var(--app-muted)]">
                Drag directly on the source preview to position the reframing window.
              </p>
            </div>

            <div>
              <div className="mb-2 flex items-center justify-between text-xs text-[var(--app-muted)]">
                <span>Framed Output Preview</span>
                <span>
                  {aspectRatio} • {frameGeometry.safeZoom.toFixed(2)}x
                </span>
              </div>
              <div
                ref={framedPreviewRef}
                className="relative overflow-hidden rounded-lg border border-[var(--app-border)] bg-black"
                style={{ aspectRatio: outputPreviewAspectRatioValue }}
              >
                {sourceUrl ? (
                  <video
                    ref={framedVideoRef}
                    muted
                    playsInline
                    src={sourceUrl}
                    className="h-full w-full bg-black object-cover"
                    style={{
                      transform: `scale(${frameGeometry.safeZoom})`,
                      transformOrigin: `${clampedFrameAnchorX * 100}% ${clampedFrameAnchorY * 100}%`,
                    }}
                    onLoadedMetadata={() => {
                      const sourcePlayer = videoRef.current;
                      const framedPlayer = framedVideoRef.current;
                      if (!sourcePlayer || !framedPlayer) return;
                      framedPlayer.currentTime = sourcePlayer.currentTime;
                      if (sourcePlayer.paused) {
                        framedPlayer.pause();
                      } else {
                        void framedPlayer.play().catch(() => undefined);
                      }
                    }}
                    onError={() => setPreviewError("Preview failed to load source video.")}
                  />
                ) : (
                  <div className="flex h-full items-center justify-center text-sm text-[var(--app-muted)]">
                    Source video is temporarily unavailable from storage. Try again after the storage download limit resets.
                  </div>
                )}

                {overlayAsset ? (
                  <div
                    className="absolute z-[15] cursor-move touch-none rounded-sm ring-1 ring-white/70"
                    style={{
                      left: `${overlayImageConfig.x * 100}%`,
                      top: `${overlayImageConfig.y * 100}%`,
                      width: `${overlayImageConfig.width * 100}%`,
                      opacity: overlayImageConfig.opacity,
                      transform: "translate(-50%, -50%)",
                    }}
                    onPointerDown={(event) => startOverlayInteraction("image-drag", event)}
                    onPointerMove={handleOverlayPointerMove}
                    onPointerUp={stopOverlayInteraction}
                    onPointerCancel={stopOverlayInteraction}
                  >
                    <img
                      src={overlayAsset.download_url}
                      alt="Video overlay"
                      draggable={false}
                      className="block h-auto w-full select-none"
                    />
                    <div
                      className="absolute -bottom-2 -right-2 h-4 w-4 cursor-nwse-resize rounded-full border-2 border-white bg-[#1D3FD0]"
                      onPointerDown={(event) => startOverlayInteraction("image-resize", event)}
                      onPointerMove={handleOverlayPointerMove}
                      onPointerUp={stopOverlayInteraction}
                      onPointerCancel={stopOverlayInteraction}
                    />
                  </div>
                ) : null}

                {captionFormat === "burned_in" ? (
                  <div className="pointer-events-none absolute inset-0 z-20">
                    <div
                      className="absolute left-0 right-0 w-full"
                      style={{
                        paddingLeft: `${captionPreviewLayout.marginXPercent}%`,
                        paddingRight: `${captionPreviewLayout.marginXPercent}%`,
                        bottom: `${captionVerticalPosition}%`,
                      }}
                    >
                      <div
                        className={`pointer-events-auto relative mx-auto w-full cursor-move text-center text-white ${
                          isCaptionDragging ? "ring-2 ring-[#1D3FD0]/70" : "ring-1 ring-[#1D3FD0]/45"
                        }`}
                        style={{
                          fontSize: `${captionFontSizePx}px`,
                          lineHeight: captionPreviewLayout.lineHeight,
                          fontWeight: captionPreviewTheme.bold ? 700 : 500,
                          fontStyle: captionPreviewTheme.italic ? "italic" : "normal",
                          fontFamily: captionPreviewTheme.fontFamily,
                          color: captionPreviewTheme.textColor,
                          textShadow:
                            captionPreviewTheme.outlinePx > 0
                              ? `0 0 ${captionPreviewTheme.outlinePx}px ${captionPreviewTheme.outlineColor}, 0 2px ${
                                  captionPreviewTheme.outlinePx + 1
                                }px ${captionPreviewTheme.outlineColor}`
                              : `0 1px 2px ${captionPreviewTheme.outlineColor}`,
                          padding: captionPreviewTheme.boxed ? "6px 10px" : "0",
                          borderRadius: captionPreviewTheme.boxed ? "8px" : "0",
                          backgroundColor: hexToRgba(
                            captionPreviewTheme.backgroundColor,
                            captionPreviewTheme.backgroundOpacity
                          ),
                        }}
                        onPointerDown={(event) => startCaptionInteraction("drag", event)}
                        onPointerMove={handleCaptionPointerMove}
                        onPointerUp={stopCaptionInteraction}
                        onPointerCancel={stopCaptionInteraction}
                      >
                        {captionPreviewLines.map((line, index) => (
                          <div key={`caption-preview-line-${index}`}>{line}</div>
                        ))}
                        <div
                          className={`absolute -bottom-3 -right-3 h-5 w-5 cursor-nwse-resize rounded-full border-2 border-white bg-[#1D3FD0] ${
                            isCaptionResizing ? "scale-110" : ""
                          }`}
                          onPointerDown={(event) => startCaptionInteraction("resize", event)}
                          onPointerMove={handleCaptionPointerMove}
                          onPointerUp={stopCaptionInteraction}
                          onPointerCancel={stopCaptionInteraction}
                        />
                      </div>
                    </div>
                  </div>
                ) : captionFormat === "srt" ? (
                  <div className="pointer-events-none absolute inset-0 z-20 flex items-end justify-center p-4">
                    <p className="rounded-md bg-black/70 px-3 py-2 text-center text-xs text-white">
                      SRT mode: captions are exported as a sidecar file and are not burned into this preview.
                    </p>
                  </div>
                ) : null}

                {overlayTextConfig.text.trim() ? (
                  <div
                    className="absolute z-30 max-w-[82%] cursor-move touch-none select-none text-center font-bold leading-tight drop-shadow-[0_2px_2px_rgba(0,0,0,0.9)] ring-1 ring-white/60"
                    style={{
                      left: `${overlayTextConfig.x * 100}%`,
                      top: `${overlayTextConfig.y * 100}%`,
                      color: overlayTextConfig.text_color,
                      fontSize: `${clamp(overlayTextConfig.font_size * 0.46, 12, 74)}px`,
                      transform: "translate(-50%, -50%)",
                    }}
                    onPointerDown={(event) => startOverlayInteraction("text-drag", event)}
                    onPointerMove={handleOverlayPointerMove}
                    onPointerUp={stopOverlayInteraction}
                    onPointerCancel={stopOverlayInteraction}
                  >
                    {overlayTextWords.map((word, index) => {
                      const highlight = overlayHighlightMap.get(index);
                      return (
                        <span
                          key={`overlay-word-${index}`}
                          className="mx-[0.12em] inline-block rounded px-[0.08em]"
                          style={highlight ? { backgroundColor: highlight } : undefined}
                        >
                          {word}
                        </span>
                      );
                    })}
                  </div>
                ) : null}

                <div className="pointer-events-none absolute right-2 top-2 z-20 rounded-md bg-black/65 px-2 py-1 text-[11px] text-white">
                  {captionFormat === "burned_in"
                    ? "Burned-in caption preview"
                    : captionFormat === "srt"
                      ? "SRT sidecar"
                      : "Captions disabled"}
                </div>
              </div>
              <div className="mt-2 space-y-1 text-xs text-[var(--app-muted)]">
                <p>
                  Current caption in preview:{" "}
                  <span className="text-[var(--app-text)]">{captionPreviewText}</span>
                </p>
                <p>
                  Caption position: <span className="text-white">{captionVerticalPosition.toFixed(1)}%</span> •
                  Size: <span className="text-white"> {captionScale.toFixed(2)}x</span>
                </p>
                <p>
                  Style:{" "}
                  <span className="text-white">
                    {captionStyleMeta.label} • {captionColorVariantMeta.label}
                  </span>
                </p>
              </div>
            </div>
          </div>
          {previewError ? <p className="mt-2 text-sm text-red-700">{previewError}</p> : null}

          <div className="mt-4 rounded-lg border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-4">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-[var(--app-muted)]">
              <span>Source Timeline</span>
              <span>
                Playhead {formatClockTime(playerCurrentTime)} / {formatClockTime(normalizedMediaDuration)}
              </span>
            </div>

            {timelineMetrics ? (
              <>
                <div
                  ref={timelineRef}
                  className={`relative mt-3 h-5 touch-none cursor-pointer ${isTimelineScrubbing ? "opacity-95" : ""}`}
                  onPointerDown={handleTimelinePointerDown}
                  onPointerMove={handleTimelinePointerMove}
                  onPointerUp={handleTimelinePointerUp}
                  onPointerCancel={handleTimelinePointerUp}
                >
                  <div className="absolute inset-x-0 top-1/2 h-2 -translate-y-1/2 rounded-full bg-[var(--app-surface-soft)]" />
                  <div
                    className="absolute top-1/2 h-2 -translate-y-1/2 rounded-full border border-[#1D3FD0] bg-[#1D3FD0]/45"
                    style={{
                      left: `${timelineMetrics.clipStartPercent}%`,
                      width: `${timelineMetrics.clipWidthPercent}%`,
                    }}
                  />

                  <div
                    className="absolute top-0 h-5 w-0.5 bg-[#1633B8]"
                    style={{ left: `${timelineMetrics.clipStartPercent}%` }}
                  />
                  <div
                    className="absolute top-0 h-5 w-0.5 bg-[#1633B8]"
                    style={{ left: `${timelineMetrics.clipEndPercent}%` }}
                  />

                  <div
                    className="absolute top-0 h-5 w-0.5 bg-sky-300"
                    style={{ left: `${timelineMetrics.playheadPercent}%` }}
                  >
                    <div className="absolute -left-1 -top-1 h-2 w-2 rounded-full bg-sky-300" />
                  </div>
                </div>
                <div className="mt-1 flex items-center justify-between text-[11px] text-[var(--app-subtle)]">
                  <span>0:00</span>
                  <span>{formatClockTime(normalizedMediaDuration)}</span>
                </div>
              </>
            ) : (
              <p className="mt-2 text-xs text-[var(--app-subtle)]">
                Timeline becomes active after valid clip timings and video metadata are available.
              </p>
            )}

            <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
              <div className="rounded-md border border-[var(--app-border)] bg-[var(--app-surface-soft)] px-3 py-2">
                <p className="text-[11px] uppercase tracking-wide text-[var(--app-muted)]">Clip Start</p>
                <p className="text-sm font-semibold text-[var(--app-text)]">
                  {formatClockTime(normalizedClipRange?.start ?? parseNumberInput(clipStart) ?? 0)}
                </p>
              </div>
              <div className="rounded-md border border-[var(--app-border)] bg-[var(--app-surface-soft)] px-3 py-2">
                <p className="text-[11px] uppercase tracking-wide text-[var(--app-muted)]">Clip End</p>
                <p className="text-sm font-semibold text-[var(--app-text)]">
                  {formatClockTime(normalizedClipRange?.end ?? parseNumberInput(clipEnd) ?? 0)}
                </p>
              </div>
              <div className="rounded-md border border-[#1D3FD0]/50 bg-[#1D3FD0]/10 px-3 py-2">
                <p className="text-[11px] uppercase tracking-wide text-[#1633B8]">Clip Duration</p>
                <p className="text-base font-semibold text-[var(--app-text)]">{formatSeconds(normalizedClipRange?.duration ?? computedDuration)}</p>
              </div>
            </div>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => void handleReplay()}
              className="rounded-md bg-[#1D3FD0] px-3 py-2 text-sm font-medium text-white hover:bg-[#1633B8]"
            >
              Replay Clip
            </button>
            <button
              type="button"
              onClick={handleSeekStart}
              className="rounded-md border border-[var(--app-border)] px-3 py-2 text-sm text-[var(--app-text)] hover:bg-[var(--app-surface-soft)]"
            >
              Jump to Clip Start
            </button>
            <span className="text-xs text-[var(--app-muted)]">
              Clip range: {formatClockTime(normalizedClipRange?.start ?? parseNumberInput(clipStart) ?? 0)} -{" "}
              {formatClockTime(normalizedClipRange?.end ?? parseNumberInput(clipEnd) ?? 0)} (
              {formatSeconds(normalizedClipRange?.duration ?? computedDuration)})
            </span>
          </div>
        </Card>

        <Card>
          <h3 className="text-sm font-semibold text-[var(--app-text)]">Trim</h3>
          {clip.thumbnail_url ? (
            <img
              src={clip.thumbnail_url}
              alt="Clip thumbnail"
              className="mt-4 h-32 w-full rounded-md border border-[var(--app-border)] object-cover"
            />
          ) : null}
          <div className="mt-4 space-y-3">
            <label className="block text-xs text-[var(--app-muted)]">
              Start (seconds)
              <input
                type="number"
                step="0.1"
                min={0}
                value={clipStart}
                onChange={(event) => setClipStart(event.target.value)}
                className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-[var(--app-surface-soft)] px-3 py-2 text-sm text-[var(--app-text)] focus:border-[#1D3FD0] focus:outline-none"
              />
            </label>
            <label className="block text-xs text-[var(--app-muted)]">
              End (seconds)
              <input
                type="number"
                step="0.1"
                min={0}
                value={clipEnd}
                onChange={(event) => setClipEnd(event.target.value)}
                className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-[var(--app-surface-soft)] px-3 py-2 text-sm text-[var(--app-text)] focus:border-[#1D3FD0] focus:outline-none"
              />
            </label>
            <p className="text-xs text-[var(--app-muted)]">
              Duration: <span className="text-[var(--app-text)]">{formatSeconds(computedDuration)}</span>
              {mediaDuration ? (
                <>
                  {" "}
                  • Video length: <span className="text-[var(--app-text)]">{formatSeconds(mediaDuration)}</span>
                </>
              ) : null}
            </p>
            <button
              type="button"
              onClick={() => void handleSaveTrim()}
              disabled={saveLoading}
              className="w-full rounded-md bg-[#1D3FD0] px-3 py-2 text-sm font-medium text-white hover:bg-[#1633B8] disabled:opacity-60"
            >
              {saveLoading ? "Saving..." : "Save Trim"}
            </button>
            {saveMessage ? <p className="text-xs text-emerald-700">{saveMessage}</p> : null}
            {saveError ? <p className="text-xs text-red-700">{saveError}</p> : null}
          </div>

          <div className="mt-5 border-t border-[var(--app-border)] pt-4">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-[var(--app-muted)]">Framing</h4>
            <p className="mt-1 text-xs text-[var(--app-muted)]">
              Choose export aspect and drag the source frame in preview. Aspect changes reset frame to centered.
            </p>
            <div className="mt-3 grid grid-cols-2 gap-2">
              {(["original", "9:16", "1:1", "16:9"] as AspectRatio[]).map((ratio) => (
                <button
                  key={ratio}
                  type="button"
                  onClick={() => handleAspectRatioChange(ratio)}
                  className={`rounded-md border px-3 py-2 text-xs font-medium ${
                    aspectRatio === ratio
                      ? "border-[#1D3FD0] bg-[#1D3FD0]/20 text-white"
                      : "border-[var(--app-border)] text-[var(--app-muted)] hover:bg-[var(--app-surface-soft)]"
                  }`}
                >
                  {ratio}
                </button>
              ))}
            </div>
            <label className="mt-3 block text-xs text-[var(--app-muted)]">
              Zoom
              <div className="mt-1 flex items-center gap-3">
                <input
                  type="range"
                  min={1}
                  max={3}
                  step={0.05}
                  value={frameZoom}
                  onChange={(event) => setFrameZoom(Number(event.target.value))}
                  className="w-full accent-[#1D3FD0]"
                />
                <span className="min-w-12 text-right text-sm text-[var(--app-text)]">{frameGeometry.safeZoom.toFixed(2)}x</span>
              </div>
            </label>
            <p className="mt-2 text-[11px] text-[var(--app-subtle)]">
              Anchor: x {clampedFrameAnchorX.toFixed(3)} • y {clampedFrameAnchorY.toFixed(3)}
            </p>

            <div className="mt-4 border-t border-[var(--app-border)] pt-3">
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setImageOverlayOpen((current) => !current)}
                  className={`rounded-md border px-3 py-2 text-xs font-medium ${
                    imageOverlayOpen
                      ? "border-[#1D3FD0] bg-[#1D3FD0]/10 text-[#1D3FD0]"
                      : "border-[var(--app-border)] text-[var(--app-text)] hover:bg-[var(--app-surface-soft)]"
                  }`}
                >
                  {overlayAsset ? "Edit Image / Logo" : "Add Image / Logo"}
                </button>
                <button
                  type="button"
                  onClick={() => setTextOverlayOpen((current) => !current)}
                  className={`rounded-md border px-3 py-2 text-xs font-medium ${
                    textOverlayOpen
                      ? "border-[#1D3FD0] bg-[#1D3FD0]/10 text-[#1D3FD0]"
                      : "border-[var(--app-border)] text-[var(--app-text)] hover:bg-[var(--app-surface-soft)]"
                  }`}
                >
                  {overlayTextConfig.text.trim() ? "Edit Overlay Text" : "Add Overlay Text"}
                </button>
              </div>

              {imageOverlayOpen ? (
                <div className="mt-3 space-y-3 rounded-lg border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs font-semibold text-[var(--app-text)]">Image or logo</p>
                    {overlayAsset ? (
                      <button
                        type="button"
                        onClick={() => void handleRemoveOverlayAsset()}
                        className="text-xs font-medium text-red-600 hover:text-red-700"
                      >
                        Remove
                      </button>
                    ) : null}
                  </div>
                  <label className="block cursor-pointer rounded-md border border-dashed border-[var(--app-border)] bg-white px-3 py-2 text-center text-xs font-medium text-[#1D3FD0] hover:bg-[#F4F8FF]">
                    {overlayUploadLoading
                      ? "Uploading..."
                      : overlayAsset
                        ? "Replace image"
                        : "Upload PNG, JPG, or WebP"}
                    <input
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      disabled={overlayUploadLoading}
                      className="hidden"
                      onChange={(event) => {
                        const file = event.target.files?.[0];
                        if (file) void handleOverlayUpload(file);
                        event.target.value = "";
                      }}
                    />
                  </label>
                  {overlayAsset ? (
                    <>
                      <p className="truncate text-[11px] text-[var(--app-muted)]">
                        {overlayAsset.original_filename || "Uploaded image"} • {overlayAsset.width}×
                        {overlayAsset.height}
                      </p>
                      <label className="block text-xs text-[var(--app-muted)]">
                        Size
                        <div className="mt-1 flex items-center gap-2">
                          <input
                            type="range"
                            min={OVERLAY_IMAGE_WIDTH_MIN}
                            max={OVERLAY_IMAGE_WIDTH_MAX}
                            step={0.01}
                            value={overlayImageConfig.width}
                            onChange={(event) =>
                              setOverlayImageConfig((current) => ({
                                ...current,
                                width: Number(event.target.value),
                              }))
                            }
                            className="w-full accent-[#1D3FD0]"
                          />
                          <span className="w-10 text-right text-[11px] text-[var(--app-text)]">
                            {Math.round(overlayImageConfig.width * 100)}%
                          </span>
                        </div>
                      </label>
                      <label className="block text-xs text-[var(--app-muted)]">
                        Opacity
                        <div className="mt-1 flex items-center gap-2">
                          <input
                            type="range"
                            min={0.1}
                            max={1}
                            step={0.05}
                            value={overlayImageConfig.opacity}
                            onChange={(event) =>
                              setOverlayImageConfig((current) => ({
                                ...current,
                                opacity: Number(event.target.value),
                              }))
                            }
                            className="w-full accent-[#1D3FD0]"
                          />
                          <span className="w-10 text-right text-[11px] text-[var(--app-text)]">
                            {Math.round(overlayImageConfig.opacity * 100)}%
                          </span>
                        </div>
                      </label>
                      <p className="text-[11px] text-[var(--app-subtle)]">
                        Drag the image in the framed preview. Use its corner handle or Size slider to resize it.
                      </p>
                    </>
                  ) : null}
                </div>
              ) : null}

              {textOverlayOpen ? (
                <div className="mt-3 space-y-3 rounded-lg border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs font-semibold text-[var(--app-text)]">Overlay text</p>
                    {overlayTextConfig.text ? (
                      <button
                        type="button"
                        onClick={() => setOverlayTextConfig(DEFAULT_TEXT_OVERLAY)}
                        className="text-xs font-medium text-red-600 hover:text-red-700"
                      >
                        Remove
                      </button>
                    ) : null}
                  </div>
                  <textarea
                    rows={2}
                    maxLength={280}
                    value={overlayTextConfig.text}
                    onChange={(event) =>
                      setOverlayTextConfig((current) => ({
                        ...current,
                        text: event.target.value,
                        highlights: [],
                      }))
                    }
                    placeholder="Add a hook, CTA, or label"
                    className="w-full rounded-md border border-[var(--app-border)] bg-white px-2.5 py-2 text-sm text-[var(--app-text)] focus:border-[#1D3FD0] focus:outline-none"
                  />
                  <div className="grid grid-cols-2 gap-2">
                    <label className="text-xs text-[var(--app-muted)]">
                      Text color
                      <input
                        type="color"
                        value={overlayTextConfig.text_color}
                        onChange={(event) =>
                          setOverlayTextConfig((current) => ({
                            ...current,
                            text_color: event.target.value.toUpperCase(),
                          }))
                        }
                        className="mt-1 h-9 w-full cursor-pointer rounded-md border border-[var(--app-border)] bg-white p-1"
                      />
                    </label>
                    <label className="text-xs text-[var(--app-muted)]">
                      Font size
                      <input
                        type="number"
                        min={16}
                        max={160}
                        value={overlayTextConfig.font_size}
                        onChange={(event) =>
                          setOverlayTextConfig((current) => ({
                            ...current,
                            font_size: clamp(Number(event.target.value) || 16, 16, 160),
                          }))
                        }
                        className="mt-1 h-9 w-full rounded-md border border-[var(--app-border)] bg-white px-2 text-sm text-[var(--app-text)]"
                      />
                    </label>
                  </div>
                  {overlayTextWords.length ? (
                    <>
                      <div>
                        <p className="text-[11px] font-medium text-[var(--app-muted)]">Highlight color</p>
                        <div className="mt-1 flex flex-wrap gap-2">
                          {HIGHLIGHT_COLORS.map((color) => (
                            <button
                              key={color}
                              type="button"
                              onClick={() => setSelectedHighlightColor(color)}
                              aria-label={`Use highlight color ${color}`}
                              className={`h-7 w-7 rounded-full border-2 ${
                                selectedHighlightColor === color
                                  ? "border-[#091528] ring-2 ring-[#1D3FD0]/25"
                                  : "border-white"
                              }`}
                              style={{ backgroundColor: color }}
                            />
                          ))}
                        </div>
                      </div>
                      <div>
                        <p className="text-[11px] text-[var(--app-muted)]">
                          Click words to apply or remove the selected highlight.
                        </p>
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {overlayTextWords.map((word, index) => {
                            const highlight = overlayHighlightMap.get(index);
                            return (
                              <button
                                key={`highlight-word-${index}`}
                                type="button"
                                onClick={() => toggleWordHighlight(index)}
                                className="rounded-md border border-[var(--app-border)] px-2 py-1 text-xs font-semibold text-[#091528]"
                                style={{ backgroundColor: highlight || "#FFFFFF" }}
                              >
                                {word}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    </>
                  ) : null}
                  <p className="text-[11px] text-[var(--app-subtle)]">
                    Drag the text directly in the framed preview. It remains visible for the full clip.
                  </p>
                </div>
              ) : null}

              {overlayError ? <p className="mt-2 text-xs text-red-700">{overlayError}</p> : null}
            </div>
          </div>
        </Card>
      </div>

      <Card>
        <h3 className="text-sm font-semibold text-[var(--app-text)]">Transcript Context</h3>
        <p className="mt-3 max-h-40 overflow-y-auto whitespace-pre-wrap rounded-md border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-3 text-sm text-[var(--app-muted)]">
          {clip.transcript_text || "Transcript excerpt unavailable for this clip."}
        </p>
      </Card>

      <Card>
        <h3 className="text-sm font-semibold text-[var(--app-text)]">Export Settings</h3>
        <div className="mt-3 rounded-md border border-[var(--app-border)] bg-[var(--app-surface-soft)] px-3 py-2 text-xs text-[var(--app-muted)]">
          Selected aspect from Framing: <span className="font-semibold text-[var(--app-text)]">{aspectRatio}</span>
        </div>
        <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <label className="text-xs text-[var(--app-muted)]">
            Caption Style
            <select
              value={captionStyle}
              onChange={(event) => setCaptionStyle(event.target.value as CaptionStyle)}
              className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-[var(--app-surface-soft)] px-3 py-2 text-sm text-[var(--app-text)] focus:border-[#1D3FD0] focus:outline-none"
            >
              {captionStyleOptions.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
            <div className="mt-2 rounded-md border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-3">
              <p className="text-[11px] uppercase tracking-wide text-[var(--app-muted)]">Style preview</p>
              <p className="mt-1 text-xs text-[var(--app-muted)]">{captionStyleMeta.description}</p>
              <p className="mt-1 text-xs text-[var(--app-subtle)]">{captionColorVariantMeta.description}</p>
              <div className="mt-2 rounded-md bg-black/55 px-2 py-2 text-center">
                <span
                  className="inline-block"
                  style={{
                    fontFamily: captionPreviewTheme.fontFamily,
                    fontWeight: captionPreviewTheme.bold ? 700 : 500,
                    fontStyle: captionPreviewTheme.italic ? "italic" : "normal",
                    color: captionPreviewTheme.textColor,
                    textShadow:
                      captionPreviewTheme.outlinePx > 0
                        ? `0 0 ${captionPreviewTheme.outlinePx}px ${captionPreviewTheme.outlineColor}, 0 2px ${
                            captionPreviewTheme.outlinePx + 1
                          }px ${captionPreviewTheme.outlineColor}`
                        : `0 1px 2px ${captionPreviewTheme.outlineColor}`,
                    padding: captionPreviewTheme.boxed ? "4px 8px" : "0",
                    borderRadius: captionPreviewTheme.boxed ? "6px" : "0",
                    backgroundColor: hexToRgba(
                      captionPreviewTheme.backgroundColor,
                      captionPreviewTheme.backgroundOpacity
                    ),
                  }}
                >
                  Preview: {captionPreviewLines[0] || "Your caption style sample"}
                </span>
              </div>
            </div>
          </label>
          <label className="text-xs text-[var(--app-muted)]">
            Caption Color
            <select
              value={captionColorVariant}
              onChange={(event) => setCaptionColorVariant(event.target.value as CaptionColorVariant)}
              className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-[var(--app-surface-soft)] px-3 py-2 text-sm text-[var(--app-text)] focus:border-[#1D3FD0] focus:outline-none"
            >
              {captionColorVariantOptions.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
            <div className="mt-2 flex items-center gap-2">
              {captionColorVariantOptions.map((item) => {
                const selected = captionColorVariant === item.value;
                return (
                  <button
                    key={`caption-variant-chip-${item.value}`}
                    type="button"
                    onClick={() => setCaptionColorVariant(item.value)}
                    className={`rounded-md border px-2 py-1 text-[11px] ${
                      selected
                        ? "border-[#1D3FD0] bg-[#1D3FD0]/20 text-[#1633B8]"
                        : "border-[var(--app-border)] text-[var(--app-muted)] hover:bg-[var(--app-surface-soft)]"
                    }`}
                    title={item.description}
                  >
                    <span className="mr-1 inline-block h-2.5 w-2.5 rounded-full border border-white/30 align-middle"
                      style={{ backgroundColor: item.swatch.textColor }} />
                    {item.label}
                  </button>
                );
              })}
            </div>
          </label>
          <label className="text-xs text-[var(--app-muted)]">
            Caption Output
            <select
              value={captionFormat}
              onChange={(event) => setCaptionFormat(event.target.value as CaptionFormat)}
              className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-[var(--app-surface-soft)] px-3 py-2 text-sm text-[var(--app-text)] focus:border-[#1D3FD0] focus:outline-none"
            >
              <option value="none">None</option>
              <option value="burned_in">Burned In</option>
              <option value="srt">SRT Sidecar</option>
            </select>
          </label>
          <label className="text-xs text-[var(--app-muted)]">
            Caption Pacing
            <select
              value={captionCadence}
              onChange={(event) => setCaptionCadence(event.target.value as CaptionCadence)}
              disabled={captionFormat === "none"}
              className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-[var(--app-surface-soft)] px-3 py-2 text-sm text-[var(--app-text)] focus:border-[#1D3FD0] focus:outline-none disabled:opacity-50"
            >
              <option value="split_line">Split Line</option>
              <option value="word_by_word">Word by Word</option>
              <option value="subtitle_block">Subtitle Block</option>
              <option value="phrase">Existing Phrase</option>
            </select>
            <p className="mt-1 text-[11px] text-[var(--app-subtle)]">
              Controls timing groups independently from visual style.
            </p>
          </label>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => void handleCreateExport()}
            disabled={createExportLoading}
            className="rounded-md bg-[#1D3FD0] px-4 py-2 text-sm font-medium text-white hover:bg-[#1633B8] disabled:opacity-60"
          >
            {createExportLoading ? "Creating Export..." : "Create Export"}
          </button>
          {createExportMessage ? <p className="text-sm text-emerald-700">{createExportMessage}</p> : null}
        </div>
      </Card>

      <Card>
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-[var(--app-text)]">Export History</h3>
          {exportsLoading ? (
            <span className="inline-flex items-center gap-2 text-xs text-[var(--app-muted)]">
              <LoadingSpinner />
              Refreshing...
            </span>
          ) : null}
        </div>
        {exportError ? <p className="mt-3 text-sm text-red-700">{exportError}</p> : null}

        {!exports.length && !exportsLoading ? (
          <p className="mt-4 rounded-md border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-4 text-sm text-[var(--app-muted)]">
            No exports yet for this clip.
          </p>
        ) : null}

        {exports.length ? (
          <div className="mt-4 space-y-3">
            {exports.map((item) => (
              <div key={item.id} className="rounded-md border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="text-sm text-[var(--app-text)]">
                    <p className="font-medium">Export {item.id.slice(0, 8)}</p>
                    <p className="mt-1 text-xs text-[var(--app-muted)]">
                      {item.aspect_ratio} • {formatCaptionStyleLabel(item.caption_style)} •{" "}
                      {formatCaptionColorVariantLabel(item.caption_color_variant)} • {item.caption_format} •{" "}
                      {item.caption_cadence}
                    </p>
                  </div>
                  <span
                    className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                      exportStatusStyles[item.status] || exportStatusStyles.queued
                    }`}
                  >
                    {statusLabel(item.status)}
                  </span>
                </div>
                {item.error_message ? <p className="mt-3 text-xs text-red-700">{item.error_message}</p> : null}
                {item.status === "ready" && item.download_url ? (
                  <div className="mt-3 flex flex-wrap items-center gap-4">
                    <a
                      href={item.download_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex text-xs text-[#1D3FD0] hover:text-[#1633B8]"
                    >
                      Download export
                    </a>
                    {item.srt_download_url ? (
                      <a
                        href={item.srt_download_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex text-xs text-[#1D3FD0] hover:text-[#1633B8]"
                      >
                        Download captions (.srt)
                      </a>
                    ) : null}
                  </div>
                ) : null}
                {item.status === "ready" && !item.download_url ? (
                  <p className="mt-3 text-xs text-[var(--app-muted)]">Export is ready but no download URL is available yet.</p>
                ) : null}
              </div>
            ))}
          </div>
        ) : null}
      </Card>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(320px,0.6fr)]">
        <Card>
          <SocialPublishPanel
            clip={clip}
            exports={exports}
            onClipUpdate={setClip}
            initialScheduledFor={initialScheduleAt}
          />
        </Card>
        <Card>
          <CarouselSchedulePanel clip={clip} initialScheduledFor={initialScheduleAt} />
        </Card>
      </div>
    </div>
  );
}
