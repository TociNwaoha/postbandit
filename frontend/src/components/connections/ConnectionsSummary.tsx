"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Card } from "@/components/ui/Card";
import { api, ApiError } from "@/lib/api";
import { SocialProvider } from "@/types";

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
        setError(err instanceof ApiError ? err.message : "Failed to load connections");
      }
    };
    void load();
  }, []);

  return (
    <Card className="mb-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold text-[var(--app-text)]">Connections</h3>
          <p className="mt-1 text-xs text-[var(--app-muted)]">Connect social accounts for in-app publishing.</p>
        </div>
        <Link href="/connections" className="text-sm text-[#1D3FD0] hover:text-[#1633B8]">
          Manage
        </Link>
      </div>

      {error ? <p className="mt-3 text-xs text-red-700">{error}</p> : null}

      <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {providers.map((provider) => {
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
          return (
            <div key={provider.platform} className="rounded-md border border-[var(--app-border)] bg-[var(--app-surface-soft)] px-3 py-2">
              <p className="text-sm font-medium text-[var(--app-text)]">{provider.display_name}</p>
              {provider.platform === "facebook" ? (
                <div className="mt-1 space-y-1 text-xs text-[var(--app-muted)]">
                  <p>{facebookAccountCount > 0 ? `${facebookAccountCount} account connected` : "Account not connected"}</p>
                  <p>{facebookPageCount > 0 ? `${facebookPageCount} page destination(s)` : "No page destinations"}</p>
                  {facebookAccountCount > 0 && facebookPageCount === 0 ? (
                    <p className="text-[11px] text-[var(--app-subtle)]">Manual profile sharing is available; Page publishing is not.</p>
                  ) : null}
                </div>
              ) : (
                <p className="mt-1 text-xs text-[var(--app-muted)]">
                  {connected ? `${provider.connected_account_count} connected` : "Not connected"}
                </p>
              )}
              {!connected && provider.setup_message ? (
                <p className="mt-1 line-clamp-2 text-[11px] text-[var(--app-subtle)]">{provider.setup_message}</p>
              ) : null}
            </div>
          );
        })}
      </div>
    </Card>
  );
}
