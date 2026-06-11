import Link from "next/link";

import { EditorRender, EditorRenderPreset, UserStorageUsage } from "@/types";

interface ExportPanelProps {
  preset: EditorRenderPreset;
  onPresetChange: (preset: EditorRenderPreset) => void;
  onRender: () => void;
  rendering: boolean;
  latestRender: EditorRender | null;
  storageUsage: UserStorageUsage | null;
}

const PRESET_OPTIONS: Array<{ value: EditorRenderPreset; label: string }> = [
  { value: "tiktok", label: "TikTok (9:16)" },
  { value: "reels", label: "Instagram Reels (9:16)" },
  { value: "shorts", label: "YouTube Shorts (9:16)" },
  { value: "linkedin", label: "LinkedIn (9:16)" },
  { value: "square", label: "Square (1:1)" },
  { value: "landscape", label: "Landscape (16:9)" },
];

function formatBytes(bytes: number): string {
  if (bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const power = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** power;
  return `${value.toFixed(value >= 10 || power === 0 ? 0 : 1)} ${units[power]}`;
}

export function ExportPanel({
  preset,
  onPresetChange,
  onRender,
  rendering,
  latestRender,
  storageUsage,
}: ExportPanelProps) {
  return (
    <div className="space-y-3 rounded-lg border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-[var(--app-muted)]">Render Export</p>

      <label className="text-xs text-[var(--app-muted)]">
        Preset
        <select
          value={preset}
          onChange={(event) => onPresetChange(event.target.value as EditorRenderPreset)}
          className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-white px-2 py-1 text-sm text-[var(--app-text)]"
        >
          {PRESET_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <button
        type="button"
        onClick={onRender}
        disabled={rendering || storageUsage?.blocked}
        className="rounded-md bg-[#1D3FD0] px-3 py-2 text-sm font-medium text-white hover:bg-[#1633B8] disabled:cursor-not-allowed disabled:opacity-60"
      >
        {rendering ? "Queueing render..." : "Render Final MP4"}
      </button>

      {storageUsage ? (
        <div className="rounded-md border border-[var(--app-border)] bg-white px-2.5 py-2 text-xs text-[var(--app-muted)]">
          Storage: {formatBytes(storageUsage.used_bytes)} / {formatBytes(storageUsage.quota_bytes)}
          {storageUsage.warning ? <span className="ml-1 text-amber-700">(quota warning)</span> : null}
          {storageUsage.blocked ? <span className="ml-1 text-red-700">(hard stop active)</span> : null}
        </div>
      ) : null}

      {latestRender ? (
        <div className="space-y-2 rounded-md border border-[var(--app-border)] bg-white px-2.5 py-2 text-xs">
          <p className="text-[var(--app-muted)]">Latest render status: <span className="font-medium text-[var(--app-text)]">{latestRender.status}</span></p>
          {latestRender.error_message ? <p className="text-red-700">{latestRender.error_message}</p> : null}
          {latestRender.download_url ? (
            <a href={latestRender.download_url} target="_blank" rel="noreferrer" className="text-[#1D3FD0] hover:text-[#1633B8]">
              Download MP4
            </a>
          ) : null}
          {latestRender.export_id ? (
            <Link href="/exports" className="block text-[var(--app-muted)] hover:text-[var(--app-text)]">
              Open in Export Library
            </Link>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
