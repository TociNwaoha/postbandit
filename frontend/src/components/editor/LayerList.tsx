import { EditorOverlay } from "@/types";

interface LayerListProps {
  overlays: EditorOverlay[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onMove: (id: string, direction: "up" | "down") => void;
}

export function LayerList({ overlays, selectedId, onSelect, onDelete, onMove }: LayerListProps) {
  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold uppercase tracking-wide text-[var(--app-muted)]">Layers</p>
      {overlays.length === 0 ? (
        <p className="rounded-md border border-[var(--app-border)] bg-[var(--app-surface-soft)] px-3 py-2 text-xs text-[var(--app-muted)]">
          No overlays yet.
        </p>
      ) : (
        <div className="space-y-2">
          {overlays
            .slice()
            .sort((a, b) => a.z_index - b.z_index)
            .map((overlay, index, arr) => {
              const isSelected = overlay.id === selectedId;
              return (
                <div
                  key={overlay.id}
                  className={`rounded-md border px-3 py-2 ${
                    isSelected
                      ? "border-[#1D3FD0] bg-[#1D3FD0]/10"
                      : "border-[var(--app-border)] bg-[var(--app-surface-soft)]"
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => onSelect(overlay.id)}
                    className="w-full text-left text-xs font-medium text-[var(--app-text)]"
                  >
                    {overlay.type === "text" ? "Text" : "Image"} • {overlay.id}
                  </button>
                  <div className="mt-2 flex items-center gap-2 text-[11px]">
                    <button
                      type="button"
                      onClick={() => onMove(overlay.id, "up")}
                      disabled={index === arr.length - 1}
                      className="rounded border border-[var(--app-border)] px-2 py-1 text-[var(--app-muted)] disabled:opacity-40"
                    >
                      Up
                    </button>
                    <button
                      type="button"
                      onClick={() => onMove(overlay.id, "down")}
                      disabled={index === 0}
                      className="rounded border border-[var(--app-border)] px-2 py-1 text-[var(--app-muted)] disabled:opacity-40"
                    >
                      Down
                    </button>
                    <button
                      type="button"
                      onClick={() => onDelete(overlay.id)}
                      className="rounded border border-red-200 px-2 py-1 text-red-700"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              );
            })}
        </div>
      )}
    </div>
  );
}
