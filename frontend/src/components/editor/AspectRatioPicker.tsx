type EditorCanvasAspectRatio = "9:16" | "1:1" | "16:9";

interface AspectRatioPickerProps {
  value: EditorCanvasAspectRatio;
  onChange: (value: EditorCanvasAspectRatio) => void;
}

const OPTIONS: Array<{ value: EditorCanvasAspectRatio; label: string }> = [
  { value: "9:16", label: "9:16 Vertical" },
  { value: "1:1", label: "1:1 Square" },
  { value: "16:9", label: "16:9 Landscape" },
];

export function AspectRatioPicker({ value, onChange }: AspectRatioPickerProps) {
  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold uppercase tracking-wide text-[var(--app-muted)]">Aspect Ratio</p>
      <div className="inline-flex rounded-lg border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-1">
        {OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={`rounded-md px-3 py-1.5 text-xs transition-colors ${
              value === option.value
                ? "bg-[#1D3FD0] text-white"
                : "text-[var(--app-muted)] hover:text-[var(--app-text)]"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}
