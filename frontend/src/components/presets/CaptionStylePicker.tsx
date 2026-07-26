"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";

export type UserCaptionStyle = "split_line" | "thick_bold" | "highlight" | "outline" | "box_pill";

export const CAPTION_STYLES: Array<{
  id: UserCaptionStyle;
  name: string;
  description: string;
}> = [
  { id: "split_line", name: "Split line", description: "Short phrases, clear and balanced." },
  { id: "thick_bold", name: "Thick bold", description: "Large outlined text for high impact." },
  { id: "highlight", name: "Highlight", description: "Yellow word-by-word emphasis." },
  { id: "outline", name: "Outline", description: "Clean white text with a strong edge." },
  { id: "box_pill", name: "Box / pill", description: "Bold text on a solid dark backing." },
];

type CaptionStyleResponse = { caption_style: UserCaptionStyle };

export function useCaptionStylePicker(onStyleChange?: (style: UserCaptionStyle) => void) {
  const [activeStyle, setActiveStyle] = useState<UserCaptionStyle>("split_line");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;
    void api
      .get<CaptionStyleResponse>("/api/users/me/caption-style")
      .then((response) => {
        const style = response.caption_style || "split_line";
        if (!mounted) return;
        setActiveStyle(style);
        onStyleChange?.(style);
      })
      .catch(() => {
        if (mounted) setError("Could not load your caption style.");
      })
      .finally(() => {
        if (mounted) setIsLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [onStyleChange]);

  const selectStyle = async (style: UserCaptionStyle) => {
    if (isSaving || style === activeStyle) return;
    setError("");
    setIsSaving(true);
    try {
      const response = await api.post<CaptionStyleResponse>("/api/users/me/caption-style", style);
      setActiveStyle(response.caption_style);
      onStyleChange?.(response.caption_style);
    } catch {
      setError("Could not save your caption style. Please try again.");
    } finally {
      setIsSaving(false);
    }
  };

  return { activeStyle, error, isLoading, isSaving, selectStyle };
}

export function CaptionStylePickerCompact({
  onStyleChange,
}: {
  onStyleChange?: (style: UserCaptionStyle) => void;
}) {
  const { activeStyle, error, isLoading, isSaving, selectStyle } = useCaptionStylePicker(onStyleChange);

  return (
    <div>
      <p className="mb-1.5 text-xs font-medium text-gray-600">Caption style</p>
      <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-thin" aria-busy={isLoading}>
        {CAPTION_STYLES.map((style) => (
          <button
            key={style.id}
            type="button"
            onClick={() => void selectStyle(style.id)}
            disabled={isLoading || isSaving}
            className={`w-20 flex-shrink-0 overflow-hidden rounded-md border transition-all disabled:cursor-wait disabled:opacity-60 ${
              activeStyle === style.id
                ? "border-blue-500 ring-1 ring-blue-500/40"
                : "border-gray-200 hover:border-gray-400"
            }`}
            title={style.description}
          >
            <div className="flex h-[52px] items-end justify-center bg-gray-900 px-1 pb-1.5">
              <CaptionStylePreview style={style.id} compact />
            </div>
            <div className="bg-white px-1 py-1 text-center">
              <p className="truncate text-[10px] font-medium text-gray-700">{style.name}</p>
              <span className={`mt-1 block h-0.5 ${activeStyle === style.id ? "bg-blue-500" : "bg-transparent"}`} />
            </div>
          </button>
        ))}
      </div>
      {error ? <p className="mt-1 text-xs text-red-600" role="alert">{error}</p> : null}
    </div>
  );
}

export function CaptionStylePreview({ style, compact = false }: { style: UserCaptionStyle; compact?: boolean }) {
  const previewText = "YOUR WORDS";
  const textClass = compact
    ? "text-center text-[10px] leading-none"
    : "absolute bottom-4 left-3 right-3 text-center text-lg leading-none";
  const positionClass = compact ? "" : "absolute";

  return (
    <span className={`${positionClass} ${textClass} inline-block`} aria-hidden="true">
      {style === "split_line" ? (
        <span className="bg-black/65 px-1 py-0.5 font-bold text-white">{previewText}</span>
      ) : null}
      {style === "thick_bold" ? (
        <span className="font-black text-white [text-shadow:1px_1px_0_#000,-1px_-1px_0_#000,1px_-1px_0_#000,-1px_1px_0_#000]">{previewText}</span>
      ) : null}
      {style === "highlight" ? (
        <span className="font-black text-yellow-300 [text-shadow:1px_1px_0_#000,-1px_-1px_0_#000,1px_-1px_0_#000,-1px_1px_0_#000]">{previewText}</span>
      ) : null}
      {style === "outline" ? (
        <span className="font-bold text-white [text-shadow:1px_1px_0_#000,-1px_-1px_0_#000,1px_-1px_0_#000,-1px_1px_0_#000]">{previewText}</span>
      ) : null}
      {style === "box_pill" ? (
        <span className="bg-[#101010] px-1.5 py-1 font-bold text-white">{previewText}</span>
      ) : null}
    </span>
  );
}
