import { EditorRenderPreset } from "@/types";

interface SafeAreaGuidesProps {
  preset: EditorRenderPreset;
}

const PRESET_MARGINS: Record<EditorRenderPreset, { top: number; bottom: number; label: string }> = {
  tiktok: { top: 0.12, bottom: 0.16, label: "TikTok safe area" },
  reels: { top: 0.11, bottom: 0.15, label: "Reels safe area" },
  shorts: { top: 0.1, bottom: 0.14, label: "Shorts safe area" },
  linkedin: { top: 0.08, bottom: 0.1, label: "LinkedIn safe area" },
  square: { top: 0.08, bottom: 0.08, label: "Square safe area" },
  landscape: { top: 0.08, bottom: 0.08, label: "Landscape safe area" },
};

export function SafeAreaGuides({ preset }: SafeAreaGuidesProps) {
  const margin = PRESET_MARGINS[preset] || PRESET_MARGINS.tiktok;

  return (
    <>
      <div
        className="pointer-events-none absolute inset-x-0 border-t border-dashed border-white/70"
        style={{ top: `${margin.top * 100}%` }}
        aria-hidden="true"
      />
      <div
        className="pointer-events-none absolute inset-x-0 border-t border-dashed border-white/70"
        style={{ bottom: `${margin.bottom * 100}%` }}
        aria-hidden="true"
      />
      <div className="pointer-events-none absolute right-2 top-2 rounded bg-black/55 px-2 py-1 text-[10px] text-white">
        {margin.label}
      </div>
    </>
  );
}
