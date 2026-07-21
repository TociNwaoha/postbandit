"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { getPlatformBrandMeta } from "@/components/connections/platformBrand";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { api, ApiError } from "@/lib/api";
import { Clip, ConnectedAccount, SocialProvider } from "@/types";

interface CarouselSchedulePanelProps {
  clip: Clip;
  initialScheduledFor?: string;
}

function toLocalDatetimeInput(value?: string): string {
  const date = value ? new Date(value) : new Date(Date.now() + 30 * 60 * 1000);
  if (Number.isNaN(date.getTime())) return "";

  const offsetMs = date.getTimezoneOffset() * 60 * 1000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

function localInputToIso(value: string): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toISOString();
}

function buildCarouselTopic(clip: Clip): string {
  const title = (clip.title || "").trim();
  const transcript = (clip.transcript_text || "").replace(/\s+/g, " ").trim();
  const parts = [title, transcript].filter(Boolean);
  return parts.join("\n\n").slice(0, 1800);
}

export function CarouselSchedulePanel({ clip, initialScheduledFor }: CarouselSchedulePanelProps) {
  const [providers, setProviders] = useState<SocialProvider[]>([]);
  const [accounts, setAccounts] = useState<ConnectedAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [scheduledFor, setScheduledFor] = useState(() => toLocalDatetimeInput(initialScheduledFor));

  useEffect(() => {
    let mounted = true;

    const loadDestinations = async () => {
      setLoading(true);
      setError(null);
      try {
        const [providerRows, accountRows] = await Promise.all([
          api.get<SocialProvider[]>("/api/social/providers"),
          api.get<ConnectedAccount[]>("/api/social/accounts"),
        ]);
        if (!mounted) return;
        setProviders(providerRows);
        setAccounts(accountRows);
      } catch (err) {
        if (!mounted) return;
        setError(err instanceof ApiError ? err.message : "Could not load connected platforms.");
      } finally {
        if (mounted) setLoading(false);
      }
    };

    void loadDestinations();
    return () => {
      mounted = false;
    };
  }, []);

  const connectedDestinations = useMemo(() => {
    const providerMap = new Map(providers.map((provider) => [provider.platform, provider]));
    return accounts
      .filter((account) => providerMap.get(account.platform)?.setup_status === "ready")
      .map((account) => ({ account, provider: providerMap.get(account.platform) }))
      .slice(0, 6);
  }, [accounts, providers]);

  const topic = buildCarouselTopic(clip);
  const scheduledIso = localInputToIso(scheduledFor);
  const buildCarouselHref = (scheduleValue?: string | null) => {
    const params = new URLSearchParams();
    params.set("sourceClip", clip.id);
    if (topic) params.set("topic", topic);
    if (scheduleValue) params.set("scheduledFor", scheduleValue);
    return `/carousels/new?${params.toString()}`;
  };
  const createNowHref = buildCarouselHref();
  const scheduleHref = buildCarouselHref(scheduledIso);

  return (
    <div className="space-y-3">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-wide text-[#1D3FD0]">Carousel workflow</p>
        <h3 className="mt-1 text-base font-semibold text-[var(--app-text)]">Schedule Carousel</h3>
        <p className="mt-1 text-[11px] leading-5 text-[var(--app-muted)]">
          Turn this clip into a carousel draft, then post now or schedule it for your connected platforms.
        </p>
      </div>

      <div className="rounded-md border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-2.5">
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs font-semibold text-[var(--app-text)]">Destinations</p>
          <Link href="/connections" className="text-xs font-medium text-[#1D3FD0] hover:text-[#1633B8]">
            Manage
          </Link>
        </div>
        {loading ? (
          <p className="mt-2 inline-flex items-center gap-2 text-xs text-[var(--app-muted)]">
            <LoadingSpinner size="sm" /> Loading platforms...
          </p>
        ) : error ? (
          <p className="mt-2 text-xs text-red-700">{error}</p>
        ) : connectedDestinations.length ? (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {connectedDestinations.map(({ account }) => {
              const brand = getPlatformBrandMeta(account.platform);
              return (
                <span
                  key={account.id}
                  className="inline-flex items-center gap-1.5 rounded-full border border-[var(--app-border)] bg-white px-2 py-1 text-[11px] font-medium text-[var(--app-text)]"
                >
                  <span className={`inline-flex h-5 w-5 items-center justify-center rounded-md ${brand.badgeClassName}`}>
                    {brand.icon}
                  </span>
                  {brand.displayName}
                </span>
              );
            })}
          </div>
        ) : (
          <p className="mt-2 text-xs text-[var(--app-muted)]">Connect a platform before posting carousel content.</p>
        )}
      </div>

      <label className="block text-xs text-[var(--app-muted)]">
        Schedule time
        <input
          type="datetime-local"
          value={scheduledFor}
          onChange={(event) => setScheduledFor(event.target.value)}
          className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-white px-2.5 py-1.5 text-sm text-[var(--app-text)] focus:border-[#1D3FD0] focus:outline-none"
        />
      </label>

      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
        <Link
          href={createNowHref}
          className="inline-flex items-center justify-center rounded-md border border-[var(--app-border)] bg-white px-3 py-2 text-xs font-semibold text-[var(--app-text)] hover:bg-[var(--app-surface-soft)]"
        >
          Post now draft
        </Link>
        <Link
          href={scheduleHref}
          className="inline-flex items-center justify-center rounded-md bg-[#1D3FD0] px-3 py-2 text-xs font-semibold text-white hover:bg-[#1633B8]"
        >
          Schedule draft
        </Link>
      </div>

      <p className="text-[11px] leading-5 text-[var(--app-subtle)]">
        The carousel builder will open with this clip as source text. Render and save the carousel before final publishing.
      </p>
    </div>
  );
}
