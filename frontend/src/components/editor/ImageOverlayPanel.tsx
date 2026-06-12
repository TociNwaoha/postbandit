"use client";

import { getSession } from "next-auth/react";

import { EditorAsset, EditorOverlay } from "@/types";

interface ImageOverlayPanelProps {
  projectId: string;
  assets: EditorAsset[];
  overlays: EditorOverlay[];
  selectedId: string | null;
  clipStart: number;
  clipEnd: number;
  onAssetsChange: (assets: EditorAsset[]) => void;
  onOverlaysChange: (overlays: EditorOverlay[]) => void;
  onSelect: (id: string) => void;
  onError: (message: string | null) => void;
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

export function ImageOverlayPanel({
  projectId,
  assets,
  overlays,
  selectedId,
  clipStart,
  clipEnd,
  onAssetsChange,
  onOverlaysChange,
  onSelect,
  onError,
}: ImageOverlayPanelProps) {
  const selected = overlays.find((overlay) => overlay.id === selectedId && overlay.type === "image") || null;

  const updateSelected = (patch: Partial<EditorOverlay>) => {
    if (!selected) return;
    onOverlaysChange(
      overlays.map((overlay) =>
        overlay.id === selected.id
          ? toOverlaySafeValues(
              {
                ...overlay,
                ...patch,
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
        <p className="text-xs font-semibold uppercase tracking-wide text-[var(--app-muted)]">Image Overlays</p>
        <label className="cursor-pointer rounded-md bg-[#1D3FD0] px-2.5 py-1 text-xs font-medium text-white">
          Upload
          <input
            type="file"
            accept="image/*"
            className="hidden"
            onChange={async (event) => {
              const file = event.target.files?.[0];
              if (!file) return;
              onError(null);
              try {
                const uploaded = await uploadAsset(projectId, file);
                onAssetsChange([...assets, uploaded]);
              } catch (err) {
                onError(err instanceof Error ? err.message : "Failed to upload image");
              } finally {
                event.target.value = "";
              }
            }}
          />
        </label>
      </div>

      <div className="space-y-2">
        <label className="text-xs text-[var(--app-muted)]">
          Asset
          <select
            value={selected?.asset_id || ""}
            onChange={(event) => {
              const assetId = event.target.value;
              if (!assetId) return;
              if (!selected) {
                const id = `img_${crypto.randomUUID().slice(0, 8)}`;
                const newLayer = toOverlaySafeValues(
                  {
                    id,
                    type: "image",
                    start_sec: clipStart,
                    end_sec: clipEnd,
                    x: 0.85,
                    y: 0.12,
                    width: 0.2,
                    height: 0.2,
                    rotation_deg: 0,
                    opacity: 1,
                    z_index: 20,
                    asset_id: assetId,
                  },
                  clipStart,
                  clipEnd
                );
                onOverlaysChange([...overlays, newLayer]);
                onSelect(id);
                return;
              }
              updateSelected({ asset_id: assetId });
            }}
            className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-white px-2 py-1 text-sm text-[var(--app-text)]"
          >
            <option value="">Select asset</option>
            {assets.map((asset) => (
              <option key={asset.id} value={asset.id}>
                {asset.original_filename || asset.id}
              </option>
            ))}
          </select>
        </label>
      </div>

      {selected ? (
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
                  updateSelected({ width: clamp((Number(event.target.value) || 20) / 100, 0.02, 1) })
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
                  updateSelected({ height: clamp((Number(event.target.value) || 20) / 100, 0.02, 1) })
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
              Rotation (deg)
              <input
              type="number"
              value={selected.rotation_deg}
              onChange={(event) => updateSelected({ rotation_deg: Number(event.target.value) || 0 })}
              className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-white px-2 py-1 text-sm"
            />
          </label>
        </div>
      ) : (
        <p className="text-xs text-[var(--app-muted)]">Select or create an image layer to edit timing and transforms.</p>
      )}
    </div>
  );
}
