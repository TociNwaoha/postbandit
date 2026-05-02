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
    <Card className="mb-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold text-white">Connections</h3>
          <p className="mt-1 text-xs text-slate-400">Connect social accounts for in-app publishing.</p>
        </div>
        <Link href="/connections" className="text-sm text-[#A78BFA] hover:text-[#C4B5FD]">
          Manage
        </Link>
      </div>

      {error ? <p className="mt-3 text-xs text-red-400">{error}</p> : null}

      <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {providers.map((provider) => {
          const connected = provider.connected_account_count > 0;
          return (
            <div key={provider.platform} className="rounded-md border border-slate-700 bg-slate-900/30 px-3 py-2">
              <p className="text-sm font-medium text-white">{provider.display_name}</p>
              <p className="mt-1 text-xs text-slate-400">
                {connected ? `${provider.connected_account_count} connected` : "Not connected"}
              </p>
              {!connected && provider.setup_message ? (
                <p className="mt-1 line-clamp-2 text-[11px] text-slate-500">{provider.setup_message}</p>
              ) : null}
            </div>
          );
        })}
      </div>
    </Card>
  );
}
