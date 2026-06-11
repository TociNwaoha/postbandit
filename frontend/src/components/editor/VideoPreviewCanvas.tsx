"use client";

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";

import { SafeAreaGuides } from "@/components/editor/SafeAreaGuides";
import { EditorAsset, EditorOverlay, EditorProjectSchemaV1 } from "@/types";

interface VideoPreviewCanvasProps {
  sourceUrl: string | null;
  sourcePlayerUrl?: string | null;
  previewStatus?: "pending" | "ready" | "failed" | null;
  usingPreviewProxy?: boolean;
  sourceKind?: "source" | "proxy" | "none";
  preparingPreview?: boolean;
  forceSafeMode?: boolean;
  mediaOffsetSec?: number;
  project: EditorProjectSchemaV1;
  assets: EditorAsset[];
  currentTimeSec: number;
  isPlaying: boolean;
  showSafeAreas: boolean;
  selectedOverlayId: string | null;
  selectedCaptionGroup: boolean;
  onCurrentTimeChange: (seconds: number) => void;
  onDurationResolved: (seconds: number) => void;
  onSelectVideo: () => void;
  onSelectCaptionGroup: () => void;
  onSelectOverlay: (id: string | null) => void;
  onCaptionGroupPatch: (patch: Partial<{ anchor_x: number; anchor_y: number; scale: number }>) => void;
  onOverlayPatch: (id: string, patch: Partial<EditorOverlay>) => void;
  onPlayingChange: (playing: boolean) => void;
  onPreviewHealthChange?: (diagnostics: PreviewHealthDiagnostics) => void;
}

interface OverlayDragState {
  id: string;
  offsetX: number;
  offsetY: number;
}

interface OverlayResizeState {
  id: string;
  centerX: number;
  centerY: number;
}

interface CaptionDragState {
  offsetX: number;
  offsetY: number;
}

interface CaptionResizeState {
  centerX: number;
  centerY: number;
  startDistance: number;
  startScale: number;
}

interface StageResizeState {
  startX: number;
  startWidth: number;
}

export interface VideoPreviewCanvasHandle {
  play: () => Promise<void>;
  pause: () => void;
  seekTo: (seconds: number) => void;
}

export type PreviewHealthState = "loading" | "playing" | "frame_visible" | "frame_failed";

export interface PreviewHealthDiagnostics {
  state: PreviewHealthState;
  source_kind: "source" | "proxy" | "none";
  using_preview_proxy: boolean;
  ready_state: number;
  video_width: number;
  video_height: number;
  current_time_sec: number;
  failure_reason: string | null;
}

const FRAME_FAILURE_TIMEOUT_MS = 1800;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function clamp01(value: number): number {
  return clamp(value, 0, 1);
}

function aspectRatioValue(aspect: EditorProjectSchemaV1["canvas"]["aspect_ratio"]): string {
  if (aspect === "1:1") return "1 / 1";
  if (aspect === "16:9") return "16 / 9";
  return "9 / 16";
}

function aspectRatioNumbers(aspect: EditorProjectSchemaV1["canvas"]["aspect_ratio"]): { width: number; height: number } {
  if (aspect === "1:1") return { width: 1, height: 1 };
  if (aspect === "16:9") return { width: 16, height: 9 };
  return { width: 9, height: 16 };
}

function defaultStageWidth(aspect: EditorProjectSchemaV1["canvas"]["aspect_ratio"]): number {
  if (aspect === "9:16") return 340;
  if (aspect === "16:9") return 620;
  return 420;
}

function hexToCssColor(value: string, fallback: string): string {
  const raw = (value || "").trim();
  if (!raw.startsWith("#")) return fallback;
  if (raw.length !== 7 && raw.length !== 9) return fallback;

  if (raw.length === 7) return raw;

  const rr = raw.slice(1, 3);
  const gg = raw.slice(3, 5);
  const bb = raw.slice(5, 7);
  const aa = raw.slice(7, 9);
  const alpha = Number.parseInt(aa, 16) / 255;
  if (Number.isNaN(alpha)) return fallback;
  return `rgba(${Number.parseInt(rr, 16)}, ${Number.parseInt(gg, 16)}, ${Number.parseInt(bb, 16)}, ${alpha.toFixed(3)})`;
}

function overlaySafePatch(overlay: EditorOverlay, patch: Partial<EditorOverlay>): Partial<EditorOverlay> {
  const width = clamp(patch.width ?? overlay.width, 0.02, 1);
  const height = clamp(patch.height ?? overlay.height, 0.02, 1);
  const startSec = patch.start_sec ?? overlay.start_sec;
  const endSec = patch.end_sec ?? overlay.end_sec;

  return {
    ...patch,
    width,
    height,
    x: patch.x !== undefined ? clamp01(patch.x) : undefined,
    y: patch.y !== undefined ? clamp01(patch.y) : undefined,
    opacity: patch.opacity !== undefined ? clamp(patch.opacity, 0, 1) : undefined,
    start_sec: startSec,
    end_sec: Math.max(startSec + 0.1, endSec),
  };
}

export const VideoPreviewCanvas = forwardRef<VideoPreviewCanvasHandle, VideoPreviewCanvasProps>(function VideoPreviewCanvas(
  {
    sourceUrl,
    sourcePlayerUrl = null,
    previewStatus,
    usingPreviewProxy = false,
    sourceKind = "none",
    preparingPreview = false,
    forceSafeMode = false,
    mediaOffsetSec = 0,
    project,
    assets,
    currentTimeSec,
    isPlaying,
    showSafeAreas,
    selectedOverlayId,
    selectedCaptionGroup,
    onCurrentTimeChange,
    onDurationResolved,
    onSelectVideo,
    onSelectCaptionGroup,
    onSelectOverlay,
    onCaptionGroupPatch,
    onOverlayPatch,
    onPlayingChange,
    onPreviewHealthChange,
  },
  ref
) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const stageRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<OverlayDragState | null>(null);
  const resizeRef = useRef<OverlayResizeState | null>(null);
  const captionDragRef = useRef<CaptionDragState | null>(null);
  const captionResizeRef = useRef<CaptionResizeState | null>(null);
  const stageResizeRef = useRef<StageResizeState | null>(null);
  const lastPublishedTimeRef = useRef<number>(currentTimeSec);
  const pendingSeekRef = useRef<number | null>(null);
  const hasMetadataRef = useRef(false);
  const frameCallbackIdRef = useRef<number | null>(null);
  const supportsRvfcRef = useRef(false);
  const hasSeenFrameRef = useRef(false);
  const playingSinceMsRef = useRef<number | null>(null);
  const previewHealthRef = useRef<PreviewHealthState>("loading");

  const [playheadSec, setPlayheadSec] = useState<number>(currentTimeSec);
  const [decodeNotice, setDecodeNotice] = useState<string | null>(null);
  const [previewHealth, setPreviewHealth] = useState<PreviewHealthState>("loading");
  const [stageWidthPx, setStageWidthPx] = useState<number>(() => defaultStageWidth(project.canvas.aspect_ratio));
  const [stageSize, setStageSize] = useState<{ width: number; height: number }>({ width: 0, height: 0 });
  const [videoIntrinsic, setVideoIntrinsic] = useState<{ width: number; height: number }>({ width: 0, height: 0 });
  const mediaOffset = Number.isFinite(mediaOffsetSec) ? Math.max(0, mediaOffsetSec) : 0;
  const projectToMediaTime = useCallback((seconds: number) => Math.max(0, seconds - mediaOffset), [mediaOffset]);
  const mediaToProjectTime = useCallback((seconds: number) => Math.max(0, mediaOffset + seconds), [mediaOffset]);

  const overlayById = useMemo(() => {
    const map = new Map<string, EditorOverlay>();
    for (const overlay of project.overlays) {
      map.set(overlay.id, overlay);
    }
    return map;
  }, [project.overlays]);

  const assetUrlById = useMemo(() => {
    const map = new Map<string, string>();
    for (const asset of assets) {
      if (asset.download_url) map.set(asset.id, asset.download_url);
    }
    return map;
  }, [assets]);

  const visibleOverlays = useMemo(
    () =>
      project.overlays
        .filter((overlay) => playheadSec >= overlay.start_sec && playheadSec <= overlay.end_sec)
        .sort((a, b) => a.z_index - b.z_index),
    [playheadSec, project.overlays]
  );

  const activeCaption = useMemo(() => {
    if (!project.captions.enabled) return null;
    const captionTimeSec = Math.max(0, playheadSec - project.trim.start_sec);
    const activeWords = project.captions.overrides
      .filter((segment) => captionTimeSec >= segment.start_sec && captionTimeSec <= segment.end_sec)
      .map((segment) => segment.text?.trim())
      .filter((segment): segment is string => Boolean(segment));
    if (!activeWords.length) return null;

    const style = project.captions.style;
    const group = project.captions.group || {};
    const fallbackAnchorY =
      style.position === "top"
        ? 0.12
        : style.position === "middle"
        ? 0.5
        : 0.85;
    const text = style.uppercase ? activeWords.join(" ").toUpperCase() : activeWords.join(" ");
    return {
      text,
      style,
      group: {
        anchor_x: typeof group.anchor_x === "number" ? clamp01(group.anchor_x) : 0.5,
        anchor_y: typeof group.anchor_y === "number" ? clamp01(group.anchor_y) : fallbackAnchorY,
        scale: typeof group.scale === "number" ? clamp(group.scale, 0.35, 3) : 1,
      },
    };
  }, [playheadSec, project.captions, project.trim.start_sec]);

  const emitPreviewHealth = useCallback(
    (state: PreviewHealthState, failureReason: string | null = null) => {
      previewHealthRef.current = state;
      setPreviewHealth((prev) => (prev === state ? prev : state));

      if (!onPreviewHealthChange) return;
      const video = videoRef.current;
      onPreviewHealthChange({
        state,
        source_kind: sourceKind,
        using_preview_proxy: usingPreviewProxy,
        ready_state: video?.readyState ?? 0,
        video_width: video?.videoWidth ?? 0,
        video_height: video?.videoHeight ?? 0,
        current_time_sec: video ? mediaToProjectTime(video.currentTime || 0) : playheadSec,
        failure_reason: failureReason,
      });
    },
    [mediaToProjectTime, onPreviewHealthChange, playheadSec, sourceKind, usingPreviewProxy]
  );

  useEffect(() => {
    const video = videoRef.current;
    if (!video) {
      setPlayheadSec(currentTimeSec);
      return;
    }

    const targetMediaTime = projectToMediaTime(currentTimeSec);
    const externalJump = Math.abs(currentTimeSec - lastPublishedTimeRef.current) > 0.16;
    if ((!isPlaying || externalJump) && Math.abs(video.currentTime - targetMediaTime) > 0.04) {
      if (!hasMetadataRef.current || video.readyState < 1) {
        pendingSeekRef.current = targetMediaTime;
      } else {
        try {
          video.currentTime = targetMediaTime;
        } catch {
          pendingSeekRef.current = targetMediaTime;
        }
      }
    }
    if (!isPlaying || externalJump) {
      setPlayheadSec(currentTimeSec);
    }
  }, [currentTimeSec, isPlaying, projectToMediaTime]);

  useEffect(() => {
    setDecodeNotice(null);
    hasMetadataRef.current = false;
    pendingSeekRef.current = null;
    hasSeenFrameRef.current = false;
    playingSinceMsRef.current = null;
    setVideoIntrinsic({ width: 0, height: 0 });
    emitPreviewHealth("loading");
  }, [emitPreviewHealth, sourceUrl]);

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;

    const publishStageSize = () => {
      const nextWidth = stage.clientWidth;
      const nextHeight = stage.clientHeight;
      if (!nextWidth || !nextHeight) return;
      setStageSize((prev) =>
        prev.width === nextWidth && prev.height === nextHeight
          ? prev
          : { width: nextWidth, height: nextHeight }
      );
    };

    publishStageSize();

    if (typeof ResizeObserver !== "undefined") {
      const observer = new ResizeObserver(() => publishStageSize());
      observer.observe(stage);
      return () => observer.disconnect();
    }

    window.addEventListener("resize", publishStageSize);
    return () => window.removeEventListener("resize", publishStageSize);
  }, [project.canvas.aspect_ratio, stageWidthPx]);

  useEffect(() => {
    setStageWidthPx(defaultStageWidth(project.canvas.aspect_ratio));
  }, [project.canvas.aspect_ratio]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    supportsRvfcRef.current = "requestVideoFrameCallback" in video;
    if (!supportsRvfcRef.current) return;

    if (frameCallbackIdRef.current !== null && "cancelVideoFrameCallback" in video) {
      try {
        video.cancelVideoFrameCallback(frameCallbackIdRef.current);
      } catch {
        // ignore
      }
      frameCallbackIdRef.current = null;
    }

    const watchFrames = () => {
      if (!hasSeenFrameRef.current) {
        hasSeenFrameRef.current = true;
        setDecodeNotice(null);
        emitPreviewHealth("frame_visible");
      }
      frameCallbackIdRef.current = video.requestVideoFrameCallback(watchFrames);
    };

    frameCallbackIdRef.current = video.requestVideoFrameCallback(watchFrames);

    return () => {
      if (frameCallbackIdRef.current !== null && "cancelVideoFrameCallback" in video) {
        try {
          video.cancelVideoFrameCallback(frameCallbackIdRef.current);
        } catch {
          // ignore
        }
        frameCallbackIdRef.current = null;
      }
    };
  }, [emitPreviewHealth, sourceUrl]);

  useEffect(() => {
    if (!isPlaying || previewHealthRef.current === "frame_failed" || previewHealthRef.current === "frame_visible") {
      return;
    }

    if (playingSinceMsRef.current === null) {
      playingSinceMsRef.current = performance.now();
    }

    const timer = window.setInterval(() => {
      const video = videoRef.current;
      if (!video || video.paused) return;

      if (!hasSeenFrameRef.current && !supportsRvfcRef.current && video.currentTime > 0.12 && video.readyState >= 2) {
        hasSeenFrameRef.current = true;
        setDecodeNotice(null);
        emitPreviewHealth("frame_visible");
        return;
      }

      if (hasSeenFrameRef.current) {
        if (previewHealthRef.current !== "frame_visible") {
          emitPreviewHealth("frame_visible");
        }
        return;
      }

      const elapsedMs = performance.now() - (playingSinceMsRef.current || performance.now());
      const progressed = video.currentTime > 0.12;
      if (elapsedMs >= FRAME_FAILURE_TIMEOUT_MS && progressed) {
        setDecodeNotice(
          "Editor preview frames failed to paint in this browser session. Regenerate the editor preview and try again."
        );
        emitPreviewHealth("frame_failed", "time_advanced_without_visible_frame");
      }
    }, 350);

    return () => window.clearInterval(timer);
  }, [emitPreviewHealth, isPlaying]);

  useImperativeHandle(
    ref,
    () => ({
      async play() {
        const video = videoRef.current;
        if (!video) return;
        if (!hasMetadataRef.current || video.readyState < 1) {
          await new Promise<void>((resolve) => {
            const onLoaded = () => {
              video.removeEventListener("loadedmetadata", onLoaded);
              resolve();
            };
            video.addEventListener("loadedmetadata", onLoaded, { once: true });
          });
        }
        playingSinceMsRef.current = performance.now();
        emitPreviewHealth("playing");
        await video.play();
        onPlayingChange(true);
      },
      pause() {
        const video = videoRef.current;
        if (!video) return;
        video.pause();
        onPlayingChange(false);
      },
      seekTo(seconds: number) {
        const video = videoRef.current;
        if (!video) return;
        const safe = Math.max(0, seconds);
        const mediaSafe = projectToMediaTime(safe);
        if (!hasMetadataRef.current || video.readyState < 1) {
          pendingSeekRef.current = mediaSafe;
        } else {
          try {
            video.currentTime = mediaSafe;
          } catch {
            pendingSeekRef.current = mediaSafe;
          }
        }
        setPlayheadSec(safe);
        lastPublishedTimeRef.current = safe;
      },
    }),
    [emitPreviewHealth, onPlayingChange, projectToMediaTime]
  );

  const fitMode = project.reframe.fit_mode === "fit" ? "fit" : "fill";
  const effectiveFitMode = forceSafeMode ? "fit" : fitMode;
  const anchorX = forceSafeMode ? 0.5 : clamp01(project.reframe.anchor_x ?? 0.5);
  const anchorY = forceSafeMode ? 0.5 : clamp01(project.reframe.anchor_y ?? 0.5);
  const reframeZoom = forceSafeMode ? 1 : clamp(project.reframe.zoom ?? 1, 1, 3);

  const mediaLayout = useMemo(() => {
    const aspect = aspectRatioNumbers(project.canvas.aspect_ratio);
    const fallbackStageWidth = Math.max(1, stageWidthPx);
    const fallbackStageHeight = Math.max(1, fallbackStageWidth * (aspect.height / aspect.width));
    const stageWidth = stageSize.width > 0 ? stageSize.width : fallbackStageWidth;
    const stageHeight = stageSize.height > 0 ? stageSize.height : fallbackStageHeight;

    const intrinsicWidth = videoIntrinsic.width > 0 ? videoIntrinsic.width : stageWidth;
    const intrinsicHeight = videoIntrinsic.height > 0 ? videoIntrinsic.height : stageHeight;
    const fitScale = Math.min(stageWidth / intrinsicWidth, stageHeight / intrinsicHeight);
    const fillScale = Math.max(stageWidth / intrinsicWidth, stageHeight / intrinsicHeight);
    const baseScale = effectiveFitMode === "fit" ? fitScale : fillScale;
    const scale = Math.max(0.0001, baseScale * reframeZoom);

    const width = intrinsicWidth * scale;
    const height = intrinsicHeight * scale;
    const extraX = Math.max(0, width - stageWidth);
    const extraY = Math.max(0, height - stageHeight);
    const left = -extraX * anchorX;
    const top = -extraY * anchorY;

    return {
      stageWidth,
      stageHeight,
      width,
      height,
      left,
      top,
    };
  }, [
    anchorX,
    anchorY,
    effectiveFitMode,
    project.canvas.aspect_ratio,
    reframeZoom,
    stageSize.height,
    stageSize.width,
    stageWidthPx,
    videoIntrinsic.height,
    videoIntrinsic.width,
  ]);

  const videoElementKey = `${sourceUrl || "none"}:${mediaOffset.toFixed(3)}:${effectiveFitMode}:${forceSafeMode ? "safe" : "framed"}`;

  useEffect(() => {
    hasMetadataRef.current = false;
    pendingSeekRef.current = projectToMediaTime(lastPublishedTimeRef.current || 0);
    hasSeenFrameRef.current = false;
    playingSinceMsRef.current = null;
    onPlayingChange(false);
  }, [onPlayingChange, projectToMediaTime, videoElementKey]);

  const beginDrag = (overlay: EditorOverlay, event: ReactPointerEvent<HTMLDivElement>) => {
    const stage = stageRef.current;
    if (!stage) return;

    const rect = stage.getBoundingClientRect();
    const centerX = overlay.x * rect.width;
    const centerY = overlay.y * rect.height;
    dragRef.current = {
      id: overlay.id,
      offsetX: event.clientX - rect.left - centerX,
      offsetY: event.clientY - rect.top - centerY,
    };

    event.currentTarget.setPointerCapture(event.pointerId);
    onSelectOverlay(overlay.id);
  };

  const beginResize = (overlay: EditorOverlay, event: ReactPointerEvent<HTMLButtonElement>) => {
    const stage = stageRef.current;
    if (!stage) return;

    const rect = stage.getBoundingClientRect();
    resizeRef.current = {
      id: overlay.id,
      centerX: overlay.x * rect.width,
      centerY: overlay.y * rect.height,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    onSelectOverlay(overlay.id);
    event.stopPropagation();
    event.preventDefault();
  };

  const beginCaptionDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    const stage = stageRef.current;
    if (!stage || !activeCaption) return;
    const rect = stage.getBoundingClientRect();
    captionDragRef.current = {
      offsetX: event.clientX - rect.left - activeCaption.group.anchor_x * rect.width,
      offsetY: event.clientY - rect.top - activeCaption.group.anchor_y * rect.height,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    onSelectCaptionGroup();
    event.stopPropagation();
  };

  const beginCaptionResize = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const stage = stageRef.current;
    if (!stage || !activeCaption) return;
    const rect = stage.getBoundingClientRect();
    const centerX = activeCaption.group.anchor_x * rect.width;
    const centerY = activeCaption.group.anchor_y * rect.height;
    const startDistance = Math.max(
      8,
      Math.hypot(event.clientX - rect.left - centerX, event.clientY - rect.top - centerY)
    );
    captionResizeRef.current = {
      centerX,
      centerY,
      startDistance,
      startScale: activeCaption.group.scale,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    onSelectCaptionGroup();
    event.stopPropagation();
    event.preventDefault();
  };

  const beginStageResize = (event: ReactPointerEvent<HTMLButtonElement>) => {
    stageResizeRef.current = {
      startX: event.clientX,
      startWidth: stageWidthPx,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    event.stopPropagation();
    event.preventDefault();
  };

  const handlePointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const stage = stageRef.current;
    if (!stage) return;

    const rect = stage.getBoundingClientRect();

    if (stageResizeRef.current) {
      const deltaX = event.clientX - stageResizeRef.current.startX;
      setStageWidthPx(clamp(stageResizeRef.current.startWidth + deltaX, 220, 900));
      return;
    }

    if (dragRef.current) {
      const centerX = event.clientX - rect.left - dragRef.current.offsetX;
      const centerY = event.clientY - rect.top - dragRef.current.offsetY;
      const active = overlayById.get(dragRef.current.id);
      if (!active) return;
      onOverlayPatch(
        dragRef.current.id,
        overlaySafePatch(active, {
          x: centerX / rect.width,
          y: centerY / rect.height,
        })
      );
      return;
    }

    if (resizeRef.current) {
      const active = overlayById.get(resizeRef.current.id);
      if (!active) return;
      const pointerX = event.clientX - rect.left;
      const pointerY = event.clientY - rect.top;
      const width = (Math.abs(pointerX - resizeRef.current.centerX) * 2) / rect.width;
      const height = (Math.abs(pointerY - resizeRef.current.centerY) * 2) / rect.height;

      onOverlayPatch(
        resizeRef.current.id,
        overlaySafePatch(active, {
          width,
          height,
        })
      );
      return;
    }

    if (captionDragRef.current && activeCaption) {
      const centerX = event.clientX - rect.left - captionDragRef.current.offsetX;
      const centerY = event.clientY - rect.top - captionDragRef.current.offsetY;
      onCaptionGroupPatch({
        anchor_x: centerX / rect.width,
        anchor_y: centerY / rect.height,
      });
      return;
    }

    if (captionResizeRef.current) {
      const pointerX = event.clientX - rect.left;
      const pointerY = event.clientY - rect.top;
      const distance = Math.max(
        8,
        Math.hypot(pointerX - captionResizeRef.current.centerX, pointerY - captionResizeRef.current.centerY)
      );
      onCaptionGroupPatch({
        scale: captionResizeRef.current.startScale * (distance / captionResizeRef.current.startDistance),
      });
    }
  };

  const endPointerInteraction = () => {
    dragRef.current = null;
    resizeRef.current = null;
    captionDragRef.current = null;
    captionResizeRef.current = null;
    stageResizeRef.current = null;
  };

  const compatibilityLabel =
    sourceKind === "proxy"
      ? "Editor clip preview (720p SDR)"
      : preparingPreview
      ? "Preparing editor-safe preview..."
      : forceSafeMode
      ? "Safe mode fallback"
      : sourcePlayerUrl
      ? "Waiting for preview source"
      : "Source media unavailable";

  return (
    <div className="space-y-2">
      <div className="flex justify-center">
        <div
          ref={stageRef}
          className="relative overflow-hidden rounded-xl border border-[var(--editor-border)] bg-black"
          style={{
            aspectRatio: aspectRatioValue(project.canvas.aspect_ratio),
            width: `min(100%, ${Math.round(stageWidthPx)}px)`,
          }}
          onPointerMove={handlePointerMove}
          onPointerUp={endPointerInteraction}
          onPointerCancel={endPointerInteraction}
          onPointerDown={(event) => {
            if (event.target === event.currentTarget) {
              onSelectVideo();
            }
          }}
        >
          {sourceUrl ? (
            <video
              key={videoElementKey}
              ref={videoRef}
              src={sourceUrl}
              className="absolute block bg-black"
              style={{
                width: `${mediaLayout.width}px`,
                height: `${mediaLayout.height}px`,
                left: `${mediaLayout.left}px`,
                top: `${mediaLayout.top}px`,
              }}
              preload="metadata"
              playsInline
              controls={false}
              onPointerDown={onSelectVideo}
              onLoadedMetadata={(event) => {
                hasMetadataRef.current = true;
                const duration = event.currentTarget.duration;
                if (Number.isFinite(duration) && duration > 0) {
                  onDurationResolved(duration);
                }
                const pendingSeek = pendingSeekRef.current;
                if (pendingSeek !== null) {
                  try {
                    event.currentTarget.currentTime = Math.max(0, pendingSeek);
                    const projectSeek = mediaToProjectTime(Math.max(0, pendingSeek));
                    setPlayheadSec(projectSeek);
                    lastPublishedTimeRef.current = projectSeek;
                    pendingSeekRef.current = null;
                  } catch {
                    // keep pending seek for next ready state tick
                  }
                }
                const width = event.currentTarget.videoWidth;
                const height = event.currentTarget.videoHeight;
                setVideoIntrinsic({ width, height });
                if (width <= 0 || height <= 0) {
                  setDecodeNotice("Video has audio but no decodable visual track in this browser.");
                  emitPreviewHealth("frame_failed", "metadata_has_no_video_dimensions");
                } else {
                  setDecodeNotice(null);
                  emitPreviewHealth("loading");
                }
              }}
              onError={(event) => {
                const mediaError = event.currentTarget.error;
                if (!mediaError) {
                  setDecodeNotice("Video failed to load in preview. Try refreshing this page.");
                  emitPreviewHealth("frame_failed", "video_error_unknown");
                  return;
                }
                const detailByCode: Record<number, string> = {
                  1: "Video loading was aborted.",
                  2: "Network error while loading preview video.",
                  3: "Video decode error in browser preview.",
                  4: "Video format is not supported by this browser.",
                };
                const detail = detailByCode[mediaError.code] || "Unknown video playback error.";
                setDecodeNotice(detail);
                emitPreviewHealth("frame_failed", `video_error_code_${mediaError.code}`);
              }}
              onTimeUpdate={(event) => {
                const nextMedia = event.currentTarget.currentTime || 0;
                const nextProject = mediaToProjectTime(nextMedia);
                setPlayheadSec(nextProject);
                if (!isPlaying || Math.abs(nextProject - lastPublishedTimeRef.current) >= 0.1) {
                  lastPublishedTimeRef.current = nextProject;
                  onCurrentTimeChange(nextProject);
                }

                if (!supportsRvfcRef.current && previewHealthRef.current === "playing" && nextMedia > 0.12) {
                  hasSeenFrameRef.current = true;
                  setDecodeNotice(null);
                  emitPreviewHealth("frame_visible");
                }
              }}
              onPlay={() => {
                playingSinceMsRef.current = performance.now();
                emitPreviewHealth("playing");
                onPlayingChange(true);
              }}
              onPause={(event) => {
                const nextProject = mediaToProjectTime(event.currentTarget.currentTime || 0);
                setPlayheadSec(nextProject);
                lastPublishedTimeRef.current = nextProject;
                onCurrentTimeChange(nextProject);
                onPlayingChange(false);
              }}
            />
          ) : preparingPreview ? (
            <div className="flex h-full items-center justify-center text-xs text-white/80">
              Preparing editor-safe preview...
            </div>
          ) : previewStatus === "failed" ? (
            <div className="flex h-full items-center justify-center px-4 text-center text-xs text-white/80">
              Editor preview failed. Regenerate the preview to rebuild a browser-safe clip.
            </div>
          ) : (
            <div className="flex h-full items-center justify-center text-xs text-white/80">
              Source media unavailable
            </div>
          )}

          {showSafeAreas ? <SafeAreaGuides preset={project.canvas.safe_area_preset} /> : null}

          {activeCaption ? (
            <div
              className={`absolute z-20 cursor-move ${selectedCaptionGroup ? "ring-2 ring-[#4A7BFF]/80" : "ring-1 ring-white/50"}`}
              style={{
                left: `${(activeCaption.group.anchor_x * 100).toFixed(3)}%`,
                top: `${(activeCaption.group.anchor_y * 100).toFixed(3)}%`,
                width: `${clamp(0.88 * activeCaption.group.scale, 0.3, 0.98) * 100}%`,
                transform: "translate(-50%, -50%)",
              }}
              onPointerDown={beginCaptionDrag}
            >
              <div
                className="block w-full rounded px-3 py-2 text-center font-semibold leading-tight"
                style={{
                  color: hexToCssColor(activeCaption.style.text_color, "#FFFFFF"),
                  backgroundColor: hexToCssColor(activeCaption.style.bg_color, "rgba(0,0,0,0.75)"),
                  fontSize: clamp(activeCaption.style.font_size * activeCaption.group.scale, 12, 160),
                }}
              >
                {activeCaption.text}
              </div>
              {selectedCaptionGroup ? (
                <button
                  type="button"
                  onPointerDown={beginCaptionResize}
                  className="absolute -bottom-2 -right-2 h-4 w-4 rounded-sm border border-white bg-[#4A7BFF]"
                  aria-label="Resize caption group"
                />
              ) : null}
            </div>
          ) : null}

          {visibleOverlays.map((overlay) => {
            const selected = selectedOverlayId === overlay.id;
            const left = `${overlay.x * 100}%`;
            const top = `${overlay.y * 100}%`;
            const width = `${Math.max(0.02, overlay.width) * 100}%`;
            const height = `${Math.max(0.02, overlay.height) * 100}%`;

            if (overlay.type === "image") {
              const src = overlay.asset_id ? assetUrlById.get(overlay.asset_id) : undefined;
              return (
                <div
                  key={overlay.id}
                  className={`absolute cursor-move border ${
                    selected ? "border-[#4A7BFF] ring-2 ring-[#4A7BFF]/70" : "border-white/50"
                  }`}
                  style={{
                    left,
                    top,
                    width,
                    height,
                    transform: `translate(-50%, -50%) rotate(${overlay.rotation_deg || 0}deg)`,
                    opacity: overlay.opacity ?? 1,
                  }}
                  onPointerDown={(event) => beginDrag(overlay, event)}
                >
                  {src ? <img src={src} alt="Overlay" className="h-full w-full object-contain" draggable={false} /> : null}
                  {selected ? (
                    <button
                      type="button"
                      onPointerDown={(event) => beginResize(overlay, event)}
                      className="absolute -bottom-2 -right-2 h-4 w-4 rounded-sm border border-white bg-[#4A7BFF]"
                      aria-label="Resize overlay"
                    />
                  ) : null}
                </div>
              );
            }

            return (
              <div
                key={overlay.id}
                className={`absolute cursor-move rounded px-2 py-1 ${selected ? "ring-2 ring-[#4A7BFF]" : "ring-1 ring-white/40"}`}
                style={{
                  left,
                  top,
                  width,
                  minHeight: height,
                  transform: `translate(-50%, -50%) rotate(${overlay.rotation_deg || 0}deg)`,
                  backgroundColor: overlay.style?.bg_color || "rgba(29,63,208,0.75)",
                  color: overlay.style?.color || "#FFFFFF",
                  fontSize: overlay.style?.font_size || 28,
                  fontWeight: overlay.style?.font_weight || 600,
                  textAlign: overlay.style?.alignment || "center",
                  opacity: overlay.opacity ?? 1,
                }}
                onPointerDown={(event) => beginDrag(overlay, event)}
              >
                {overlay.content || "Text overlay"}
                {selected ? (
                  <button
                    type="button"
                    onPointerDown={(event) => beginResize(overlay, event)}
                    className="absolute -bottom-2 -right-2 h-4 w-4 rounded-sm border border-white bg-[#4A7BFF]"
                    aria-label="Resize overlay"
                  />
                ) : null}
              </div>
            );
          })}

          {decodeNotice ? (
            <div className="absolute bottom-2 left-2 right-2 z-30 rounded-md border border-amber-300/40 bg-amber-100/90 px-2 py-1.5 text-[11px] text-amber-900">
              <span>{decodeNotice}</span>
            </div>
          ) : null}

          <div className="absolute left-2 top-2 z-30 rounded bg-black/60 px-2 py-1 text-[10px] text-white/85">
            {compatibilityLabel}
          </div>

          <div className="absolute bottom-2 right-2 z-30 rounded bg-black/65 px-2 py-1 text-[10px] text-white/85">
            {previewHealth}
          </div>

          <button
            type="button"
            onPointerDown={beginStageResize}
            className="absolute bottom-2 left-2 z-30 h-4 w-4 cursor-se-resize rounded-sm border border-white/70 bg-[#4A7BFF]/80"
            aria-label="Resize preview stage"
            title="Drag to resize preview stage"
          />
        </div>
      </div>
    </div>
  );
});
