import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";

export interface TimelineTrackItem {
  id: string;
  label: string;
  type: "video" | "caption" | "text" | "image";
  startSec: number;
  endSec: number;
  selected: boolean;
}

export interface TimelineTrack {
  id: string;
  label: string;
  items: TimelineTrackItem[];
}

interface EditorTimelineProps {
  durationSec: number;
  currentTimeSec: number;
  trimStartSec: number;
  trimEndSec: number;
  isPlaying: boolean;
  timelineZoom: number;
  tracks: TimelineTrack[];
  onTimelineZoomChange: (zoom: number) => void;
  onCurrentTimeChange: (seconds: number) => void;
  onTrimChange: (startSec: number, endSec: number) => void;
  onJumpToStart: () => void;
  onReplay: () => void;
  onStart: () => void;
  onStop: () => void;
  onSelectTrackItem: (trackId: string, itemId: string) => void;
  onUpdateTrackItemTiming?: (trackId: string, itemId: string, startSec: number, endSec: number) => void;
  heightPx?: number;
  snapStepSec?: number;
}

interface DragState {
  trackId: string;
  itemId: string;
  mode: "move" | "trim_start" | "trim_end";
  pointerStartTimeSec: number;
  itemStartSec: number;
  itemEndSec: number;
}

const MIN_TRACK_ITEM_DURATION_SEC = 0.12;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function snap(value: number, step: number): number {
  if (!Number.isFinite(step) || step <= 0) return value;
  return Math.round(value / step) * step;
}

function formatTime(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds));
  const m = Math.floor(safe / 60);
  const s = safe % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function markerStepForZoom(pxPerSecond: number): number {
  if (pxPerSecond >= 26) return 1;
  if (pxPerSecond >= 16) return 2;
  if (pxPerSecond >= 10) return 5;
  return 10;
}

function blockColor(type: TimelineTrackItem["type"], selected: boolean): string {
  if (selected) {
    return "border-[#6EA8FF] bg-[#2D5FF4] text-white";
  }
  if (type === "video") return "border-[#3E4655] bg-[#2A313D] text-[#D9E2FF]";
  if (type === "caption") return "border-[#3A4F5D] bg-[#203848] text-[#B7D7FF]";
  if (type === "text") return "border-[#5B4B34] bg-[#3A2E1C] text-[#FFD7A0]";
  return "border-[#4D3F61] bg-[#2E2541] text-[#D7C9FF]";
}

function isTimingEditable(trackId: string, item: TimelineTrackItem, hasUpdater: boolean): boolean {
  if (!hasUpdater) return false;
  if (trackId !== "text" && trackId !== "images") return false;
  return item.type === "text" || item.type === "image";
}

export function EditorTimeline({
  durationSec,
  currentTimeSec,
  trimStartSec,
  trimEndSec,
  isPlaying,
  timelineZoom,
  tracks,
  onTimelineZoomChange,
  onCurrentTimeChange,
  onTrimChange,
  onJumpToStart,
  onReplay,
  onStart,
  onStop,
  onSelectTrackItem,
  onUpdateTrackItemTiming,
  heightPx = 270,
  snapStepSec = 0.1,
}: EditorTimelineProps) {
  const safeDuration = Math.max(0.1, durationSec || 0);
  const safeZoom = clamp(timelineZoom, 8, 60);
  const safeHeight = clamp(heightPx, 220, 520);
  const trackWidthPx = Math.max(900, Math.ceil(safeDuration * safeZoom));
  const playheadX = clamp(currentTimeSec, 0, safeDuration) * safeZoom;

  const [activeDrag, setActiveDrag] = useState<DragState | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const step = markerStepForZoom(safeZoom);
  const markers: number[] = [];
  for (let sec = 0; sec <= safeDuration; sec += step) {
    markers.push(sec);
  }

  const trimStartPx = clamp(trimStartSec, 0, safeDuration) * safeZoom;
  const trimEndPx = clamp(trimEndSec, 0, safeDuration) * safeZoom;

  const pointerClientXToTime = (clientX: number): number | null => {
    const scrollEl = scrollRef.current;
    if (!scrollEl) return null;
    const rect = scrollEl.getBoundingClientRect();
    if (rect.width <= 0) return null;
    const xPx = clientX - rect.left + scrollEl.scrollLeft;
    return clamp(xPx / safeZoom, 0, safeDuration);
  };

  useEffect(() => {
    if (!activeDrag || !onUpdateTrackItemTiming) return;

    const onPointerMove = (event: PointerEvent) => {
      const nextPointerTime = pointerClientXToTime(event.clientX);
      if (nextPointerTime === null) return;

      const delta = nextPointerTime - activeDrag.pointerStartTimeSec;
      const snappedDelta = snap(delta, snapStepSec);

      if (activeDrag.mode === "move") {
        const duration = activeDrag.itemEndSec - activeDrag.itemStartSec;
        const unsnappedStart = activeDrag.itemStartSec + snappedDelta;
        const start = clamp(unsnappedStart, 0, safeDuration - duration);
        const end = start + duration;
        onUpdateTrackItemTiming(activeDrag.trackId, activeDrag.itemId, start, end);
        return;
      }

      if (activeDrag.mode === "trim_start") {
        const unsnappedStart = activeDrag.itemStartSec + snappedDelta;
        const maxStart = activeDrag.itemEndSec - MIN_TRACK_ITEM_DURATION_SEC;
        const start = clamp(unsnappedStart, 0, maxStart);
        onUpdateTrackItemTiming(activeDrag.trackId, activeDrag.itemId, start, activeDrag.itemEndSec);
        return;
      }

      const unsnappedEnd = activeDrag.itemEndSec + snappedDelta;
      const minEnd = activeDrag.itemStartSec + MIN_TRACK_ITEM_DURATION_SEC;
      const end = clamp(unsnappedEnd, minEnd, safeDuration);
      onUpdateTrackItemTiming(activeDrag.trackId, activeDrag.itemId, activeDrag.itemStartSec, end);
    };

    const onPointerUp = () => {
      setActiveDrag(null);
    };

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    window.addEventListener("pointercancel", onPointerUp);
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      window.removeEventListener("pointercancel", onPointerUp);
    };
  }, [activeDrag, onUpdateTrackItemTiming, safeDuration, safeZoom, snapStepSec]);

  const beginDrag = (
    event: ReactPointerEvent<HTMLElement>,
    trackId: string,
    item: TimelineTrackItem,
    mode: DragState["mode"]
  ) => {
    if (!onUpdateTrackItemTiming) return;
    const pointerStartTime = pointerClientXToTime(event.clientX);
    if (pointerStartTime === null) return;
    event.preventDefault();
    event.stopPropagation();
    onSelectTrackItem(trackId, item.id);
    setActiveDrag({
      trackId,
      itemId: item.id,
      mode,
      pointerStartTimeSec: pointerStartTime,
      itemStartSec: item.startSec,
      itemEndSec: item.endSec,
    });
  };

  return (
    <div
      className="rounded-xl border border-[var(--editor-border)] bg-[var(--editor-panel)] p-3"
      style={{ height: `${safeHeight}px` }}
    >
      <div className="flex h-full flex-col">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-[var(--editor-muted)]">Timeline</p>
            <span className="rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2 py-1 text-[11px] text-[var(--editor-muted)]">
              {formatTime(currentTimeSec)} / {formatTime(safeDuration)}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={onJumpToStart}
              className="rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2.5 py-1.5 text-xs text-[var(--editor-muted)] hover:text-[var(--editor-text)]"
            >
              Start Clip
            </button>
            <button
              type="button"
              onClick={onReplay}
              className="rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2.5 py-1.5 text-xs text-[var(--editor-muted)] hover:text-[var(--editor-text)]"
            >
              Replay Clip
            </button>
            <button
              type="button"
              onClick={onStart}
              className="rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2.5 py-1.5 text-xs text-[var(--editor-muted)] hover:text-[var(--editor-text)]"
            >
              Play
            </button>
            <button
              type="button"
              onClick={onStop}
              className={`rounded-md px-2.5 py-1.5 text-xs ${
                isPlaying
                  ? "border border-red-500/50 bg-red-500/20 text-red-200"
                  : "border border-[var(--editor-border)] bg-[var(--editor-panel-2)] text-[var(--editor-muted)]"
              }`}
            >
              Stop
            </button>
          </div>
        </div>

        <div className="mb-3 grid gap-2 md:grid-cols-[1fr_1fr_auto]">
          <label className="text-xs text-[var(--editor-muted)]">
            Trim start (s)
            <input
              type="number"
              value={trimStartSec}
              step={0.1}
              min={0}
              max={safeDuration}
              onChange={(event) => onTrimChange(Number(event.target.value) || 0, trimEndSec)}
              className="mt-1 w-full rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2 py-1 text-sm text-[var(--editor-text)]"
            />
          </label>
          <label className="text-xs text-[var(--editor-muted)]">
            Trim end (s)
            <input
              type="number"
              value={trimEndSec}
              step={0.1}
              min={0}
              max={safeDuration}
              onChange={(event) => onTrimChange(trimStartSec, Number(event.target.value) || 0)}
              className="mt-1 w-full rounded-md border border-[var(--editor-border)] bg-[var(--editor-panel-2)] px-2 py-1 text-sm text-[var(--editor-text)]"
            />
          </label>
          <label className="text-xs text-[var(--editor-muted)]">
            Timeline Zoom
            <input
              type="range"
              min={8}
              max={60}
              step={1}
              value={safeZoom}
              onChange={(event) => onTimelineZoomChange(Number(event.target.value) || 8)}
              className="mt-2 w-40"
            />
          </label>
        </div>

        <div
          ref={scrollRef}
          className="relative min-h-0 flex-1 overflow-auto rounded-lg border border-[var(--editor-border)] bg-[var(--editor-canvas)]"
        >
          <div className="relative" style={{ width: `${trackWidthPx}px` }}>
            <div className="sticky left-0 top-0 z-20 h-7 border-b border-[var(--editor-border)] bg-[var(--editor-panel)]/95 backdrop-blur">
              {markers.map((sec) => {
                const x = sec * safeZoom;
                return (
                  <div key={`marker-${sec}`} className="absolute top-0 h-full" style={{ left: `${x}px` }}>
                    <div className="h-2 w-px bg-[var(--editor-border)]" />
                    <p className="mt-0.5 -translate-x-1/2 text-[10px] text-[var(--editor-muted)]">{formatTime(sec)}</p>
                  </div>
                );
              })}
            </div>

            <div className="relative z-10">
              {tracks.map((track) => (
                <div key={track.id} className="flex h-8 items-center border-b border-[var(--editor-border)] px-2">
                  <div className="w-28 pr-2 text-[11px] font-medium text-[var(--editor-subtle)]">{track.label}</div>
                  <div className="relative h-6 flex-1 rounded-sm bg-transparent">
                    {track.items.map((item) => {
                      const startPx = clamp(item.startSec, 0, safeDuration) * safeZoom;
                      const widthPx = Math.max(6, (item.endSec - item.startSec) * safeZoom);
                      const editable = isTimingEditable(track.id, item, Boolean(onUpdateTrackItemTiming));
                      return (
                        <button
                          type="button"
                          key={`${track.id}-${item.id}`}
                          onClick={() => onSelectTrackItem(track.id, item.id)}
                          onPointerDown={
                            editable
                              ? (event) => {
                                  beginDrag(event, track.id, item, "move");
                                }
                              : undefined
                          }
                          className={`absolute top-0 h-6 overflow-hidden rounded border px-1 text-left text-[10px] leading-5 ${blockColor(item.type, item.selected)} ${
                            editable ? "cursor-grab active:cursor-grabbing" : "cursor-pointer"
                          }`}
                          style={{ left: `${startPx}px`, width: `${widthPx}px` }}
                          title={`${item.label} (${formatTime(item.startSec)} - ${formatTime(item.endSec)})`}
                        >
                          {editable ? (
                            <span
                              className="absolute left-0 top-0 h-full w-1.5 cursor-ew-resize bg-white/40"
                              onPointerDown={(event) => beginDrag(event, track.id, item, "trim_start")}
                            />
                          ) : null}
                          <span className="truncate">{item.label}</span>
                          {editable ? (
                            <span
                              className="absolute right-0 top-0 h-full w-1.5 cursor-ew-resize bg-white/40"
                              onPointerDown={(event) => beginDrag(event, track.id, item, "trim_end")}
                            />
                          ) : null}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>

            <div className="pointer-events-none absolute inset-y-0 z-30" style={{ left: `${playheadX}px` }}>
              <div className="h-full w-px bg-[#6EA8FF]" />
            </div>

            <input
              type="range"
              min={0}
              max={safeDuration}
              step={0.05}
              value={clamp(currentTimeSec, 0, safeDuration)}
              onChange={(event) => onCurrentTimeChange(Number(event.target.value) || 0)}
              className="absolute inset-x-0 top-0 z-40 h-full cursor-ew-resize opacity-0"
            />

            <div className="pointer-events-none absolute top-7 z-10" style={{ left: 0, width: `${trimStartPx}px`, bottom: 0 }}>
              <div className="h-full bg-black/25" />
            </div>
            <div
              className="pointer-events-none absolute top-7 z-10"
              style={{ left: `${trimEndPx}px`, right: 0, bottom: 0 }}
            >
              <div className="h-full bg-black/25" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
