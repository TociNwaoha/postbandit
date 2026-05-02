"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { Card } from "@/components/ui/Card";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { api, ApiError } from "@/lib/api";
import { ConnectedAccount, SocialProvider } from "@/types";

const statusTextStyles: Record<string, string> = {
  ready: "text-emerald-300",
  provider_not_configured: "text-amber-300",
};

export function ConnectionsPanel() {
  const searchParams = useSearchParams();
  const [providers, setProviders] = useState<SocialProvider[]>([]);
  const [accounts, setAccounts] = useState<ConnectedAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [connectingPlatform, setConnectingPlatform] = useState<string | null>(null);
  const [disconnectingAccountId, setDisconnectingAccountId] = useState<string | null>(null);

  const callbackMessage = useMemo(() => {
    const callbackStatus = searchParams.get("status");
    const platform = searchParams.get("platform");
    const reason = searchParams.get("message");
    if (!callbackStatus) return null;
    const target = platform || "account";
    if (callbackStatus === "connected") {
      const destinations = searchParams.get("destinations");
      if (destinations && Number(destinations) > 1) {
        return `Connected ${target} successfully (${destinations} destinations discovered).`;
      }
      return `Connected ${target} successfully.`;
    }

    if (reason === "oauth_session_expired") {
      return `Connection failed for ${target}: session expired. Start connect again.`;
    }
    if (reason === "oauth_exchange_failed") {
      return `Connection failed for ${target}: OAuth exchange was rejected by provider.`;
    }
    if (reason === "internal_callback_error") {
      return `Connection failed for ${target}: callback processing error.`;
    }
    return `Connection failed${platform ? ` for ${platform}` : ""}.`;
  }, [searchParams]);

  const destinationTypeLabel = (value: string | null | undefined): string | null => {
    if (!value) return null;
    return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
  };

  const tiktokProfileSummary = (account: ConnectedAccount): string | null => {
    if (account.platform !== "tiktok") return null;
    const metadata = account.metadata_json || {};
    const creatorInfo = metadata.tiktok_creator_info as Record<string, unknown> | undefined;
    const profile = metadata.profile as Record<string, unknown> | undefined;
    const creatorUsername =
      typeof creatorInfo?.creator_username === "string" ? creatorInfo.creator_username : null;
    const creatorNickname =
      typeof creatorInfo?.creator_nickname === "string" ? creatorInfo.creator_nickname : null;
    const username = typeof profile?.username === "string" ? profile.username : null;
    const displayName = typeof profile?.display_name === "string" ? profile.display_name : null;
    const handle = creatorUsername || username;
    const name = creatorNickname || displayName;
    if (handle && name) return `${name} (@${handle.replace(/^@/, "")})`;
    if (handle) return `@${handle.replace(/^@/, "")}`;
    if (name) return name;
    return null;
  };

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [providersData, accountsData] = await Promise.all([
        api.get<SocialProvider[]>("/api/social/providers"),
        api.get<ConnectedAccount[]>("/api/social/accounts"),
      ]);
      setProviders(providersData);
      setAccounts(accountsData);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load connections");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const connectPlatform = async (platform: string) => {
    setConnectingPlatform(platform);
    setActionError(null);
    try {
      const data = await api.post<{ authorization_url: string }>(`/api/social/${platform}/connect`, {
        return_to: "/connections",
      });
      window.location.href = data.authorization_url;
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Failed to start connection");
    } finally {
      setConnectingPlatform(null);
    }
  };

  const disconnectAccount = async (accountId: string) => {
    setDisconnectingAccountId(accountId);
    setActionError(null);
    try {
      await api.delete(`/api/social/accounts/${accountId}`);
      await load();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Failed to disconnect account");
    } finally {
      setDisconnectingAccountId(null);
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-end">
        <Link href="/review/meta-instagram" className="text-sm text-[#A78BFA] hover:text-[#C4B5FD]">
          Open Meta review demo
        </Link>
      </div>
      {callbackMessage ? <p className="text-sm text-emerald-300">{callbackMessage}</p> : null}
      {actionError ? <p className="text-sm text-red-400">{actionError}</p> : null}
      {error ? <p className="text-sm text-red-400">{error}</p> : null}

      {loading ? (
        <div className="inline-flex items-center gap-2 text-sm text-slate-300">
          <LoadingSpinner size="sm" />
          Loading connections...
        </div>
      ) : null}

      {providers.map((provider) => {
        const providerAccounts = accounts.filter((account) => account.platform === provider.platform);
        const facebookAccountRows = providerAccounts.filter(
          (account) => account.destination_type === "facebook_account"
        );
        const facebookPageRows = providerAccounts.filter((account) => account.destination_type === "facebook_page");
        const setupClass = statusTextStyles[provider.setup_status] || "text-slate-300";
        const setupDetails = (provider.setup_details || {}) as Record<string, unknown>;
        const threadsPublishTextReady =
          provider.platform === "threads" && Boolean(setupDetails.publish_text_ready);
        const threadsPublishMediaReady =
          provider.platform === "threads" && Boolean(setupDetails.publish_media_ready);
        const tiktokDirectReady =
          provider.platform === "tiktok" && Boolean(setupDetails.publish_direct_ready);
        const tiktokUploadReady =
          provider.platform === "tiktok" && Boolean(setupDetails.publish_upload_ready);

        return (
          <Card key={provider.platform}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-base font-semibold text-white">{provider.display_name}</h3>
                <p className={`mt-1 text-xs ${setupClass}`}>
                  {provider.setup_status === "ready" ? "Ready" : provider.setup_message || "Not configured"}
                </p>
                <p className="mt-1 text-xs text-slate-500">{provider.connected_account_count} connected account(s)</p>
                {provider.platform === "threads" ? (
                  <p className="mt-1 text-[11px] text-slate-500">
                    {threadsPublishMediaReady
                      ? "Threads text and video publishing are enabled."
                      : threadsPublishTextReady
                        ? "Threads text publishing is enabled. Video may require additional app permissions/tester setup."
                        : "Connect Threads to enable publishing."}
                  </p>
                ) : null}
                {provider.platform === "tiktok" ? (
                  <p className="mt-1 text-[11px] text-slate-500">
                    {tiktokDirectReady
                      ? "TikTok direct post is enabled. If direct post is blocked, inbox upload fallback is available."
                      : tiktokUploadReady
                        ? "TikTok is connected for inbox upload fallback; direct post may require additional review/setup."
                        : "Connect TikTok to enable video publishing."}
                  </p>
                ) : null}
              </div>
              <button
                type="button"
                onClick={() => void connectPlatform(provider.platform)}
                disabled={connectingPlatform === provider.platform || provider.setup_status !== "ready"}
                className="rounded-md bg-[#7C3AED] px-3 py-2 text-sm font-medium text-white hover:bg-[#6D28D9] disabled:opacity-50"
              >
                {connectingPlatform === provider.platform ? "Connecting..." : "Connect"}
              </button>
            </div>

            {provider.platform === "facebook" ? (
              <div className="mt-4 space-y-2">
                <div className="rounded-md border border-slate-700 bg-slate-900/40 p-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-300">
                    Connected Facebook Account(s)
                  </p>
                  {facebookAccountRows.length ? (
                    <div className="mt-2 space-y-2">
                      {facebookAccountRows.map((account) => (
                        <div key={account.id} className="rounded-md border border-slate-700 bg-slate-950/60 p-3">
                          <div className="flex flex-wrap items-center justify-between gap-3">
                            <div>
                              <p className="text-sm text-white">{account.display_name || account.external_account_id}</p>
                              <p className="mt-1 text-xs text-slate-400">
                                {account.username_or_channel_name || account.external_account_id}
                              </p>
                              <p className="mt-1 text-[11px] text-slate-500">
                                {destinationTypeLabel(account.destination_type)}
                              </p>
                            </div>
                            <button
                              type="button"
                              onClick={() => void disconnectAccount(account.id)}
                              disabled={disconnectingAccountId === account.id}
                              className="rounded-md border border-slate-700 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-800 disabled:opacity-50"
                            >
                              {disconnectingAccountId === account.id ? "Disconnecting..." : "Disconnect"}
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-2 text-sm text-slate-400">No Facebook account connected yet.</p>
                  )}
                </div>

                <div className="rounded-md border border-slate-700 bg-slate-900/40 p-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-300">
                    Facebook Page Destinations (Automated Publish)
                  </p>
                  {facebookPageRows.length ? (
                    <div className="mt-2 space-y-2">
                      {facebookPageRows.map((account) => (
                        <div key={account.id} className="rounded-md border border-slate-700 bg-slate-950/60 p-3">
                          <div className="flex flex-wrap items-center justify-between gap-3">
                            <div>
                              <p className="text-sm text-white">{account.display_name || account.external_account_id}</p>
                              <p className="mt-1 text-xs text-slate-400">
                                {account.username_or_channel_name || account.external_account_id}
                              </p>
                              <p className="mt-1 text-[11px] text-slate-500">
                                {destinationTypeLabel(account.destination_type)}
                              </p>
                            </div>
                            <button
                              type="button"
                              onClick={() => void disconnectAccount(account.id)}
                              disabled={disconnectingAccountId === account.id}
                              className="rounded-md border border-slate-700 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-800 disabled:opacity-50"
                            >
                              {disconnectingAccountId === account.id ? "Disconnecting..." : "Disconnect"}
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-2 text-sm text-slate-400">
                      No Pages discovered yet. Automated Facebook publishing requires at least one managed Page.
                    </p>
                  )}
                  <p className="mt-2 text-[11px] text-slate-500">
                    Personal profile sharing is available as a manual action from the clip publish panel.
                  </p>
                </div>
              </div>
            ) : (
              providerAccounts.length > 0 ? (
                <div className="mt-4 space-y-2">
                  {providerAccounts.map((account) => (
                    <div key={account.id} className="rounded-md border border-slate-700 bg-slate-900/40 p-3">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <p className="text-sm text-white">{account.display_name || account.external_account_id}</p>
                          <p className="mt-1 text-xs text-slate-400">
                            {account.username_or_channel_name || account.external_account_id}
                          </p>
                          {provider.platform === "tiktok" && tiktokProfileSummary(account) ? (
                            <p className="mt-1 text-[11px] text-slate-500">{tiktokProfileSummary(account)}</p>
                          ) : null}
                          {destinationTypeLabel(account.destination_type) ? (
                            <p className="mt-1 text-[11px] text-slate-500">
                              {destinationTypeLabel(account.destination_type)}
                            </p>
                          ) : null}
                        </div>
                        <button
                          type="button"
                          onClick={() => void disconnectAccount(account.id)}
                          disabled={disconnectingAccountId === account.id}
                          className="rounded-md border border-slate-700 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-800 disabled:opacity-50"
                        >
                          {disconnectingAccountId === account.id ? "Disconnecting..." : "Disconnect"}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="mt-4 text-sm text-slate-400">No accounts connected yet.</p>
              )
            )}
          </Card>
        );
      })}
    </div>
  );
}
