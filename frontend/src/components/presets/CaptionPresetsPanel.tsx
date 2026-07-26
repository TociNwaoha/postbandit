"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { api } from "@/lib/api";
import {
  CAPTION_STYLES,
  CaptionStylePreview,
  type UserCaptionStyle,
  useCaptionStylePicker,
} from "@/components/presets/CaptionStylePicker";

type CaptionPreset = "music_video" | null;
type CaptionPresetResponse = { caption_preset: CaptionPreset };
export function CaptionPresetsPanel() {
  const [activePreset, setActivePreset] = useState<CaptionPreset>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");
  const {
    activeStyle,
    error: styleError,
    isLoading: isStyleLoading,
    isSaving: isStyleSaving,
    selectStyle,
  } = useCaptionStylePicker();

  useEffect(() => {
    let mounted = true;
    void api
      .get<CaptionPresetResponse>("/api/users/me/caption-preset")
      .then((response) => {
        if (mounted) setActivePreset(response.caption_preset || null);
      })
      .catch(() => {
        if (mounted) setError("Could not load your caption preset.");
      })
      .finally(() => {
        if (mounted) setIsLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  const selectPreset = async (preset: CaptionPreset) => {
    if (isSaving || preset === activePreset) return;
    setError("");
    setIsSaving(true);
    try {
      const response = await api.post<CaptionPresetResponse>("/api/users/me/caption-preset", preset);
      setActivePreset(response.caption_preset || null);
    } catch {
      setError("Could not save your caption preset. Please try again.");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="mx-auto w-full max-w-3xl px-6 py-8">
      <div className="mb-8">
        <h1 className="app-display text-2xl font-bold text-[var(--app-text)]">Caption presets</h1>
        <p className="mt-2 text-sm text-[var(--app-muted)]">Choose the visual treatment used for burned-in captions on future exports.</p>
      </div>

      <div className="space-y-3" aria-busy={isLoading}>
        <PresetOption
          active={activePreset === null}
          disabled={isLoading || isSaving}
          title="Default captions"
          description="Your current caption style, placement, and color settings."
          onClick={() => void selectPreset(null)}
        />
        <PresetOption
          active={activePreset === "music_video"}
          disabled={isLoading || isSaving}
          title="Music video"
          description="Words appear across the frame as they are spoken, remain briefly, and play over a subtly darkened video."
          onClick={() => void selectPreset("music_video")}
          preview
        />
      </div>

      <section className="mt-8 border-t border-[var(--app-border)] pt-8" aria-busy={isStyleLoading}>
        <div className="mb-4">
          <h2 className="text-lg font-semibold text-[var(--app-text)]">Caption style</h2>
          <p className="mt-1 text-sm text-[var(--app-muted)]">Choose the look used for standard burned-in captions.</p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {CAPTION_STYLES.map((style) => (
            <CaptionStyleOption
              key={style.id}
              style={style}
              active={activeStyle === style.id}
              disabled={isStyleLoading || isStyleSaving}
              onClick={() => void selectStyle(style.id)}
            />
          ))}
        </div>
      </section>

      {activePreset ? (
        <section className="mt-8 border border-blue-200 bg-blue-50/60 p-5" aria-label="Try your active preset">
          <p className="text-sm font-semibold text-blue-900">Preset active - now try it</p>
          <p className="mt-1 text-xs text-blue-700">
            Upload a video or pick an existing clip. The preset applies automatically when you export.
          </p>
          <div className="mt-4 flex flex-col gap-3 sm:flex-row">
            <Link
              href="/dashboard?upload=1"
              className="flex flex-1 items-center justify-center bg-blue-600 px-4 py-2.5 text-center text-sm font-semibold text-white transition-colors hover:bg-blue-700"
            >
              Upload a video
            </Link>
            <Link
              href="/dashboard?videos=1"
              className="flex flex-1 items-center justify-center border border-blue-300 px-4 py-2.5 text-center text-sm font-medium text-blue-700 transition-colors hover:bg-blue-100"
            >
              Pick existing clip
            </Link>
          </div>
          <p className="mt-3 text-xs text-blue-500">After exporting a clip, download it to see the preset applied.</p>
        </section>
      ) : null}

      {error || styleError ? <p className="mt-4 text-sm text-red-600" role="alert">{error || styleError}</p> : null}
    </div>
  );
}

function CaptionStyleOption({
  style,
  active,
  disabled,
  onClick,
}: {
  style: { id: UserCaptionStyle; name: string; description: string };
  active: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`border p-3 text-left transition-colors disabled:cursor-wait disabled:opacity-60 ${
        active
          ? "border-[var(--app-primary)] bg-[rgba(29,63,208,0.06)]"
          : "border-[var(--app-border)] bg-white hover:border-[var(--app-subtle)]"
      }`}
    >
      <span className="relative block h-24 overflow-hidden bg-[#202634]">
        <CaptionStylePreview style={style.id} />
      </span>
      <span className="mt-3 flex items-start justify-between gap-3">
        <span>
          <span className="block text-sm font-semibold text-[var(--app-text)]">{style.name}</span>
          <span className="mt-1 block text-xs leading-4 text-[var(--app-muted)]">{style.description}</span>
        </span>
        {active ? <span className="shrink-0 text-xs font-semibold text-[var(--app-primary)]">Active</span> : null}
      </span>
    </button>
  );
}

function PresetOption({
  active,
  disabled,
  title,
  description,
  onClick,
  preview = false,
}: {
  active: boolean;
  disabled: boolean;
  title: string;
  description: string;
  onClick: () => void;
  preview?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`w-full border p-4 text-left transition-colors disabled:cursor-wait disabled:opacity-60 ${
        active
          ? "border-[var(--app-primary)] bg-[rgba(29,63,208,0.06)]"
          : "border-[var(--app-border)] bg-white hover:border-[var(--app-subtle)]"
      }`}
    >
      <span className="flex items-start justify-between gap-4">
        <span>
          <span className="block text-sm font-semibold text-[var(--app-text)]">{title}</span>
          <span className="mt-1 block text-sm leading-5 text-[var(--app-muted)]">{description}</span>
        </span>
        {active ? <span className="shrink-0 text-xs font-semibold text-[var(--app-primary)]">Active</span> : null}
      </span>
      {preview ? <MusicVideoPreview /> : null}
    </button>
  );
}

function MusicVideoPreview() {
  return (
    <span className="relative mt-4 block h-32 overflow-hidden bg-[#182032]" aria-hidden="true">
      <span className="absolute inset-0 bg-black/30" />
      <span className="absolute left-[13%] top-[17%] text-sm font-normal tracking-[0.12em] text-white">WALK</span>
      <span className="absolute left-[47%] top-[41%] text-sm font-normal tracking-[0.12em] text-white">WITH</span>
      <span className="absolute left-[70%] top-[68%] text-sm font-normal tracking-[0.12em] text-white">GOD</span>
    </span>
  );
}
