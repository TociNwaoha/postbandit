import { EditorOverlay } from "@/types";

interface TextOverlayPanelProps {
  overlays: EditorOverlay[];
  selectedId: string | null;
  clipStart: number;
  clipEnd: number;
  onChange: (overlays: EditorOverlay[]) => void;
  onSelect: (id: string) => void;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function toOverlaySafeValues(overlay: EditorOverlay, clipStart: number, clipEnd: number): EditorOverlay {
  const boundedStart = clamp(overlay.start_sec, clipStart, clipEnd);
  const boundedEnd = clamp(overlay.end_sec, boundedStart + 0.1, clipEnd);
  return {
    ...overlay,
    start_sec: boundedStart,
    end_sec: boundedEnd,
    width: clamp(overlay.width, 0.02, 1),
    height: clamp(overlay.height, 0.02, 1),
    opacity: clamp(overlay.opacity ?? 1, 0, 1),
  };
}

function newTextOverlay(startSec: number, endSec: number): EditorOverlay {
  const id = `text_${crypto.randomUUID().slice(0, 8)}`;
  return {
    id,
    type: "text",
    start_sec: startSec,
    end_sec: endSec,
    x: 0.5,
    y: 0.2,
    width: 0.5,
    height: 0.14,
    rotation_deg: 0,
    opacity: 1,
    z_index: 10,
    content: "Your overlay text",
    style: {
      font_family: "Inter",
      font_size: 42,
      color: "#FFFFFF",
      bg_color: "#1D3FD0CC",
    },
  };
}

export function TextOverlayPanel({
  overlays,
  selectedId,
  clipStart,
  clipEnd,
  onChange,
  onSelect,
}: TextOverlayPanelProps) {
  const selected = overlays.find((overlay) => overlay.id === selectedId && overlay.type === "text") || null;

  const updateSelected = (patch: Partial<EditorOverlay>) => {
    if (!selected) return;
    onChange(
      overlays.map((overlay) =>
        overlay.id === selected.id
          ? toOverlaySafeValues(
              {
                ...overlay,
                ...patch,
                style: {
                  ...(overlay.style || {}),
                  ...(patch.style || {}),
                },
              },
              clipStart,
              clipEnd
            )
          : overlay
      )
    );
  };

  return (
    <div className="space-y-3 rounded-lg border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wide text-[var(--app-muted)]">Text Overlays</p>
        <button
          type="button"
          onClick={() => {
            const overlay = newTextOverlay(clipStart, clipEnd);
            onChange([...overlays, overlay]);
            onSelect(overlay.id);
          }}
          className="rounded-md bg-[#1D3FD0] px-2.5 py-1 text-xs font-medium text-white"
        >
          Add Text
        </button>
      </div>

      {!selected ? (
        <p className="text-xs text-[var(--app-muted)]">Select a text layer in Layers to edit timing and style.</p>
      ) : (
        <div className="space-y-2">
          <label className="text-xs text-[var(--app-muted)]">
            Content
            <textarea
              rows={2}
              value={selected.content || ""}
              onChange={(event) => updateSelected({ content: event.target.value })}
              className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-white px-2 py-1 text-sm text-[var(--app-text)]"
            />
          </label>

          <div className="grid gap-2 md:grid-cols-2">
            <label className="text-xs text-[var(--app-muted)]">
              Start (s)
              <input
                type="number"
                step="0.1"
                value={selected.start_sec}
                onChange={(event) => updateSelected({ start_sec: Number(event.target.value) || clipStart })}
                className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-white px-2 py-1 text-sm"
              />
            </label>
            <label className="text-xs text-[var(--app-muted)]">
              End (s)
              <input
                type="number"
                step="0.1"
                value={selected.end_sec}
                onChange={(event) => updateSelected({ end_sec: Number(event.target.value) || clipEnd })}
                className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-white px-2 py-1 text-sm"
              />
            </label>
            <label className="text-xs text-[var(--app-muted)]">
              Width (%)
              <input
                type="number"
                min={2}
                max={100}
                value={Math.round(selected.width * 100)}
                onChange={(event) =>
                  updateSelected({ width: clamp((Number(event.target.value) || 50) / 100, 0.02, 1) })
                }
                className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-white px-2 py-1 text-sm"
              />
            </label>
            <label className="text-xs text-[var(--app-muted)]">
              Height (%)
              <input
                type="number"
                min={2}
                max={100}
                value={Math.round(selected.height * 100)}
                onChange={(event) =>
                  updateSelected({ height: clamp((Number(event.target.value) || 14) / 100, 0.02, 1) })
                }
                className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-white px-2 py-1 text-sm"
              />
            </label>
            <label className="text-xs text-[var(--app-muted)]">
              Opacity (%)
              <input
                type="number"
                min={0}
                max={100}
                value={Math.round((selected.opacity ?? 1) * 100)}
                onChange={(event) =>
                  updateSelected({ opacity: clamp((Number(event.target.value) || 100) / 100, 0, 1) })
                }
                className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-white px-2 py-1 text-sm"
              />
            </label>
            <label className="text-xs text-[var(--app-muted)]">
              Font size
              <input
                type="number"
                value={selected.style?.font_size || 42}
                onChange={(event) =>
                  updateSelected({ style: { ...(selected.style || {}), font_size: Number(event.target.value) || 42 } })
                }
                className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-white px-2 py-1 text-sm"
              />
            </label>
            <label className="text-xs text-[var(--app-muted)]">
              Rotation
              <input
                type="number"
                step="1"
                value={selected.rotation_deg}
                onChange={(event) => updateSelected({ rotation_deg: Number(event.target.value) || 0 })}
                className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-white px-2 py-1 text-sm"
              />
            </label>
            <label className="text-xs text-[var(--app-muted)]">
              Text color
              <input
                type="color"
                value={(selected.style?.color || "#FFFFFF").slice(0, 7)}
                onChange={(event) =>
                  updateSelected({ style: { ...(selected.style || {}), color: event.target.value } })
                }
                className="mt-1 h-9 w-full rounded-md border border-[var(--app-border)] bg-white px-1"
              />
            </label>
            <label className="text-xs text-[var(--app-muted)]">
              Background color
              <input
                type="color"
                value={(selected.style?.bg_color || "#1D3FD0").slice(0, 7)}
                onChange={(event) =>
                  updateSelected({ style: { ...(selected.style || {}), bg_color: `${event.target.value}CC` } })
                }
                className="mt-1 h-9 w-full rounded-md border border-[var(--app-border)] bg-white px-1"
              />
            </label>
          </div>
        </div>
      )}
    </div>
  );
}
