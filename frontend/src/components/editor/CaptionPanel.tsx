import { EditorCaptionConfig } from "@/types";

interface CaptionPanelProps {
  value: EditorCaptionConfig;
  onChange: (next: EditorCaptionConfig) => void;
}

export function CaptionPanel({ value, onChange }: CaptionPanelProps) {
  const updateStyle = <K extends keyof EditorCaptionConfig["style"]>(key: K, nextValue: EditorCaptionConfig["style"][K]) => {
    onChange({
      ...value,
      style: {
        ...value.style,
        [key]: nextValue,
      },
    });
  };

  return (
    <div className="space-y-3 rounded-lg border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wide text-[var(--app-muted)]">Captions</p>
        <label className="inline-flex items-center gap-2 text-xs text-[var(--app-muted)]">
          <input
            type="checkbox"
            checked={value.enabled}
            onChange={(event) => onChange({ ...value, enabled: event.target.checked })}
          />
          Enabled
        </label>
      </div>

      <div className="grid gap-2 md:grid-cols-2">
        <label className="text-xs text-[var(--app-muted)]">
          Font size
          <input
            type="number"
            value={value.style.font_size}
            min={16}
            max={120}
            onChange={(event) => updateStyle("font_size", Number(event.target.value) || 54)}
            className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-white px-2 py-1 text-sm text-[var(--app-text)]"
          />
        </label>
        <label className="text-xs text-[var(--app-muted)]">
          Position
          <select
            value={value.style.position}
            onChange={(event) => updateStyle("position", event.target.value as "top" | "middle" | "bottom")}
            className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-white px-2 py-1 text-sm text-[var(--app-text)]"
          >
            <option value="top">Top</option>
            <option value="middle">Middle</option>
            <option value="bottom">Bottom</option>
          </select>
        </label>
        <label className="text-xs text-[var(--app-muted)]">
          Text color
          <input
            type="color"
            value={(value.style.text_color || "#FFFFFF").slice(0, 7)}
            onChange={(event) => updateStyle("text_color", event.target.value)}
            className="mt-1 h-9 w-full rounded-md border border-[var(--app-border)] bg-white px-1"
          />
        </label>
        <label className="text-xs text-[var(--app-muted)]">
          Background color
          <input
            type="color"
            value={(value.style.bg_color || "#000000").slice(0, 7)}
            onChange={(event) => updateStyle("bg_color", `${event.target.value}CC`)}
            className="mt-1 h-9 w-full rounded-md border border-[var(--app-border)] bg-white px-1"
          />
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-4 text-xs text-[var(--app-muted)]">
        <label className="inline-flex items-center gap-2">
          <input
            type="checkbox"
            checked={value.style.uppercase}
            onChange={(event) => updateStyle("uppercase", event.target.checked)}
          />
          Uppercase
        </label>
        <label className="inline-flex items-center gap-2">
          <input
            type="checkbox"
            checked={value.active_word_highlight}
            onChange={(event) => onChange({ ...value, active_word_highlight: event.target.checked })}
          />
          Active-word highlight
        </label>
      </div>

      <div className="space-y-2">
        <p className="text-xs text-[var(--app-subtle)]">Caption Segments</p>
        <div className="max-h-48 space-y-2 overflow-y-auto pr-1">
          {value.overrides.slice(0, 80).map((segment, index) => (
            <label key={`${segment.segment_id || "seg"}-${index}`} className="block text-xs text-[var(--app-muted)]">
              {segment.start_sec.toFixed(1)}s - {segment.end_sec.toFixed(1)}s
              <input
                type="text"
                value={segment.text}
                onChange={(event) => {
                  const next = [...value.overrides];
                  next[index] = { ...segment, text: event.target.value };
                  onChange({ ...value, overrides: next });
                }}
                className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-white px-2 py-1 text-sm text-[var(--app-text)]"
              />
            </label>
          ))}
        </div>
      </div>
    </div>
  );
}
