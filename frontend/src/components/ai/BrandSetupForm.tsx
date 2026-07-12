"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { ApiError, api } from "@/lib/api";
import { BrandProfile } from "@/types";

const TONES = ["professional", "casual", "edgy", "educational"] as const;
const PLATFORM_OPTIONS = ["instagram", "threads", "linkedin", "tiktok", "youtube", "x"] as const;

function TagInput({ label, values, onChange, placeholder }: { label: string; values: string[]; onChange: (next: string[]) => void; placeholder: string }) {
  const [draft, setDraft] = useState("");
  const addTag = () => {
    const clean = draft.trim();
    if (!clean) return;
    if (values.some((value) => value.toLowerCase() === clean.toLowerCase())) {
      setDraft("");
      return;
    }
    onChange([...values, clean]);
    setDraft("");
  };

  return (
    <div className="space-y-2">
      <label className="text-sm font-medium text-[var(--app-muted)]">{label}</label>
      <Input
        value={draft}
        placeholder={placeholder}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            addTag();
          }
        }}
      />
      <div className="flex flex-wrap gap-2">
        {values.map((value) => (
          <span key={value} className="inline-flex items-center gap-2 rounded-full border border-[var(--app-border)] bg-[var(--app-surface-soft)] px-3 py-1 text-xs text-[var(--app-text)]">
            {value}
            <button type="button" className="text-[var(--app-subtle)] hover:text-[var(--app-text)]" onClick={() => onChange(values.filter((item) => item !== value))}>×</button>
          </span>
        ))}
      </div>
    </div>
  );
}

export function BrandSetupForm() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [displayName, setDisplayName] = useState("");
  const [handle, setHandle] = useState("");
  const [niche, setNiche] = useState("");
  const [targetAudience, setTargetAudience] = useState("");
  const [tone, setTone] = useState<(typeof TONES)[number]>("professional");
  const [usePhrases, setUsePhrases] = useState<string[]>([]);
  const [avoidPhrases, setAvoidPhrases] = useState<string[]>([]);
  const [aiCmoEnabled, setAiCmoEnabled] = useState(true);
  const [postFrequency, setPostFrequency] = useState(1);
  const [preferredPlatforms, setPreferredPlatforms] = useState<string[]>([]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const profile = await api.get<BrandProfile>("/api/brand-profile");
        if (!active) return;
        setDisplayName(profile.display_name || "");
        setHandle(profile.handle || "");
        setNiche(profile.niche || "");
        setTargetAudience(profile.target_audience || "");
        setTone((TONES.includes(profile.tone as (typeof TONES)[number]) ? profile.tone : "professional") as (typeof TONES)[number]);
        setUsePhrases(profile.use_phrases || []);
        setAvoidPhrases(profile.avoid_phrases || []);
        setAiCmoEnabled(profile.ai_cmo_enabled ?? true);
        setPostFrequency(Math.max(0, Math.min(5, profile.post_frequency || 1)));
        setPreferredPlatforms(profile.preferred_platforms || []);
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return;
        if (!active) return;
        setError(err instanceof ApiError ? err.message : "Failed to load brand profile.");
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, []);

  const togglePlatform = (platform: string) => {
    setPreferredPlatforms((current) =>
      current.includes(platform) ? current.filter((item) => item !== platform) : [...current, platform]
    );
  };

  const saveProfile = async (nextAiCmoEnabled = aiCmoEnabled) => {
    const profile = await api.post<BrandProfile>("/api/brand-profile", {
      display_name: displayName,
      handle,
      niche,
      target_audience: targetAudience,
      tone,
      use_phrases: usePhrases,
      avoid_phrases: avoidPhrases,
      ai_cmo_enabled: nextAiCmoEnabled,
      post_frequency: postFrequency,
      preferred_platforms: preferredPlatforms,
    });
    setAiCmoEnabled(profile.ai_cmo_enabled);
    window.dispatchEvent(
      new CustomEvent("ai-cmo-status-changed", {
        detail: { enabled: profile.ai_cmo_enabled },
      })
    );
    return profile;
  };

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await saveProfile();
      router.push("/content-queue?saved=1");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save brand profile.");
    } finally {
      setSaving(false);
    }
  };

  const onToggleAiCmo = async () => {
    const nextEnabled = !aiCmoEnabled;
    setSaving(true);
    setError(null);
    try {
      await saveProfile(nextEnabled);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to update AI CMO status.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <form className="space-y-5" onSubmit={onSubmit}>
        <div>
          <h2 className="text-lg font-semibold text-[var(--app-text)]">Brand Setup</h2>
          <p className="mt-1 text-sm text-[var(--app-subtle)]">
            Configure how PostBandit AI CMO writes carousel drafts for your account. When AI CMO is on, PostBandit creates posts every day on your behalf; you only need to review and approve them.
          </p>
        </div>
        {error ? <p className="text-sm text-red-700">{error}</p> : null}
        {loading ? <p className="text-sm text-[var(--app-subtle)]">Loading brand profile...</p> : null}
        <div className="grid gap-4 md:grid-cols-2">
          <Input label="Display Name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
          <Input label="Handle" value={handle} onChange={(e) => setHandle(e.target.value)} placeholder="@yourhandle" required />
          <Input label="Your Niche" value={niche} onChange={(e) => setNiche(e.target.value)} placeholder="e.g. AI tools for entrepreneurs" required />
          <Input label="Target Audience" value={targetAudience} onChange={(e) => setTargetAudience(e.target.value)} placeholder="e.g. freelancers and small business owners" required />
        </div>
        <div>
          <label className="text-sm font-medium text-[var(--app-muted)]">Tone</label>
          <select className="mt-1 w-full rounded-lg border border-[var(--app-border)] bg-white px-3 py-2.5 text-sm text-[var(--app-text)]" value={tone} onChange={(e) => setTone(e.target.value as (typeof TONES)[number])}>
            {TONES.map((item) => <option key={item} value={item}>{item.charAt(0).toUpperCase() + item.slice(1)}</option>)}
          </select>
        </div>
        <TagInput label="Phrases to always use" values={usePhrases} onChange={setUsePhrases} placeholder="Type phrase and press Enter" />
        <TagInput label="Phrases to never use" values={avoidPhrases} onChange={setAvoidPhrases} placeholder="Type phrase and press Enter" />
        <Input type="number" min={0} max={5} label="Posts per day" value={postFrequency} onChange={(e) => setPostFrequency(Math.max(0, Math.min(5, Number(e.target.value || 0))))} />
        <div className="space-y-2">
          <p className="text-sm font-medium text-[var(--app-muted)]">Preferred platforms</p>
          <div className="grid gap-2 md:grid-cols-3">
            {PLATFORM_OPTIONS.map((platform) => (
              <label key={platform} className="flex items-center gap-2 text-sm text-[var(--app-text)]">
                <input type="checkbox" checked={preferredPlatforms.includes(platform)} onChange={() => togglePlatform(platform)} />
                {platform.charAt(0).toUpperCase() + platform.slice(1)}
              </label>
            ))}
          </div>
        </div>
        <div className="flex flex-col gap-3 border-t border-[var(--app-border)] pt-4 sm:flex-row sm:items-center">
          <Button type="submit" loading={saving}>Save Brand Profile</Button>
          <Button
            type="button"
            variant={aiCmoEnabled ? "danger" : "secondary"}
            loading={saving}
            onClick={onToggleAiCmo}
          >
            {aiCmoEnabled ? "Turn Off AI CMO" : "Turn On AI CMO"}
          </Button>
          <span className="text-xs text-[var(--app-subtle)]">
            {aiCmoEnabled
              ? "AI CMO is on and can create daily carousel drafts."
              : "AI CMO is off and daily carousel creation is paused."}
          </span>
        </div>
      </form>
    </Card>
  );
}
