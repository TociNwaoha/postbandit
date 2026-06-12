"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Card } from "@/components/ui/Card";
import { api, ApiError } from "@/lib/api";
import { SocialProvider } from "@/types";

import { getPlatformBrandMeta } from "./platformBrand";

export function ConnectionsSummary() {
  const [providers, setProviders] = useState<SocialProvider[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const data = await api.get<SocialProvider[]>("/api/social/providers");
        setProviders(data);
        setError(null);
      } catch (err) {
        const message =
          err instanceof ApiError
            ? err.status === 401 || err.status === 403
              ? "Session expired, please log in again."
              : err.message
            : "Failed to load connections";
        setError(message);
      }
    };
    void load();
  }, []);

  return (
    <Card className="mb-6" padding="sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-baseline gap-2">
          <h3 className="text-sm font-semibold text-[var(--app-text)]">Connections</h3>
          <p className="text-[11px] text-[var(--app-muted)]">Publishing destinations</p>
        </div>
        <Link href="/connections" className="text-xs font-medium text-[#1D3FD0] hover:text-[#1633B8]">
          Manage
        </Link>
      </div>

      {error ? <p className="mt-2 text-xs text-red-700">{error}</p> : null}

      <div className="mt-2.5 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {providers.map((provider) => {
          const brand = getPlatformBrandMeta(provider.platform);
          const setupDetails = (provider.setup_details || {}) as Record<string, unknown>;
          const facebookPageCount =
            provider.platform === "facebook" && typeof setupDetails.facebook_page_count === "number"
              ? setupDetails.facebook_page_count
              : 0;
          const facebookAccountCount =
            provider.platform === "facebook" && typeof setupDetails.facebook_account_count === "number"
              ? setupDetails.facebook_account_count
              : 0;
          const connected = provider.connected_account_count > 0;
          const statusText =
            provider.platform === "facebook"
              ? `${facebookAccountCount} account${facebookAccountCount === 1 ? "" : "s"} · ${facebookPageCount} page${
                  facebookPageCount === 1 ? "" : "s"
                }`
              : connected
                ? `${provider.connected_account_count} connected`
                : "Not connected";

          return (
            <div
              key={provider.platform}
              title={!connected && provider.setup_message ? provider.setup_message : undefined}
              className="flex min-w-0 items-center gap-2 rounded-lg border border-[var(--app-border)] bg-[var(--app-surface-soft)] px-2.5 py-2"
            >
              <span
                className={`inline-flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md shadow-sm ${brand.badgeClassName}`}
                aria-label={`${brand.displayName} logo`}
              >
                {brand.icon}
              </span>
              <div className="min-w-0">
                <p className="truncate text-xs font-semibold text-[var(--app-text)]">{brand.displayName}</p>
                <p className={`truncate text-[10px] ${connected ? "text-emerald-700" : "text-[var(--app-muted)]"}`}>
                  {statusText}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
