"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { Card } from "@/components/ui/Card";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { api, ApiError } from "@/lib/api";
import { ConnectedAccount, SocialProvider } from "@/types";

import { getPlatformBrandMeta } from "./platformBrand";

const statusTextStyles: Record<string, string> = {
  ready: "text-emerald-700",
  provider_not_configured: "text-amber-700",
};

const accountRowClasses = "rounded-md border border-[var(--app-border)] bg-[var(--app-surface-soft)] px-3 py-2";

function destinationTypeLabel(value: string | null | undefined): string | null {
  if (!value) return null;
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function providerCapabilityCopy(provider: SocialProvider, setupDetails: Record<string, unknown>): string | null {
  if (provider.platform === "threads") {
    const threadsPublishTextReady = Boolean(setupDetails.publish_text_ready);
    const threadsPublishMediaReady = Boolean(setupDetails.publish_media_ready);
    if (threadsPublishMediaReady) return "Text and video publishing are enabled.";
    if (threadsPublishTextReady) return "Text publishing is enabled. Video may require extra app setup.";
    return "Connect Threads to enable publishing.";
  }

  if (provider.platform === "tiktok") {
    const tiktokDirectReady = Boolean(setupDetails.publish_direct_ready);
    const tiktokUploadReady = Boolean(setupDetails.publish_upload_ready);
    if (tiktokDirectReady) return "Direct post is enabled. Inbox upload fallback is available.";
    if (tiktokUploadReady) return "Inbox upload fallback is ready. Direct post may need review/setup.";
    return "Connect TikTok to enable video publishing.";
  }

  return null;
}

function tiktokProfileSummary(account: ConnectedAccount): string | null {
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
}

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

  const accountsByPlatform = useMemo(() => {
    const grouped: Partial<Record<string, ConnectedAccount[]>> = {};
    for (const account of accounts) {
      if (!grouped[account.platform]) grouped[account.platform] = [];
      grouped[account.platform]?.push(account);
    }
    return grouped;
  }, [accounts]);

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

  const renderAccountRows = (providerPlatform: string, rows: ConnectedAccount[], emptyMessage: string) => {
    if (!rows.length) {
      return <p className="text-xs text-[var(--app-muted)]">{emptyMessage}</p>;
    }

    return (
      <div className="space-y-1.5">
        {rows.map((account) => {
          const accountTypeLabel = destinationTypeLabel(account.destination_type);
          const tiktokSummary = providerPlatform === "tiktok" ? tiktokProfileSummary(account) : null;

          return (
            <div key={account.id} className={accountRowClasses}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-[var(--app-text)]">
                    {account.display_name || account.external_account_id}
                  </p>
                  <p className="truncate text-xs text-[var(--app-muted)]">
                    {account.username_or_channel_name || account.external_account_id}
                  </p>
                  {tiktokSummary ? <p className="truncate text-[11px] text-[var(--app-subtle)]">{tiktokSummary}</p> : null}
                  {accountTypeLabel ? (
                    <p className="truncate text-[11px] text-[var(--app-subtle)]">{accountTypeLabel}</p>
                  ) : null}
                </div>

                <button
                  type="button"
                  onClick={() => void disconnectAccount(account.id)}
                  disabled={disconnectingAccountId === account.id}
                  className="rounded-md border border-[var(--app-border)] px-2.5 py-1 text-[11px] text-[var(--app-text)] hover:bg-white disabled:opacity-50"
                >
                  {disconnectingAccountId === account.id ? "Disconnecting..." : "Disconnect"}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-[var(--app-subtle)]">{accounts.length} connected destination(s)</p>
        <Link href="/review/meta-instagram" className="text-xs text-[#1D3FD0] hover:text-[#1633B8]">
          Open Meta review demo
        </Link>
      </div>

      {callbackMessage ? (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700">
          {callbackMessage}
        </div>
      ) : null}
      {actionError ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{actionError}</div>
      ) : null}
      {error ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div>
      ) : null}

      {loading ? (
        <div className="inline-flex items-center gap-2 text-sm text-[var(--app-muted)]">
          <LoadingSpinner size="sm" />
          Loading connections...
        </div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(280px,340px)_minmax(0,1fr)]">
        <Card padding="sm" className="h-fit">
          <h3 className="text-sm font-semibold text-[var(--app-text)]">Add new account</h3>
          <p className="mt-1 text-xs text-[var(--app-muted)]">
            Connect platforms with branded OAuth buttons and manage them on the right.
          </p>

          <div className="mt-3 space-y-2">
            {providers.map((provider) => {
              const brand = getPlatformBrandMeta(provider.platform);
              const isReady = provider.setup_status === "ready";
              const isConnecting = connectingPlatform === provider.platform;
              const setupClass = statusTextStyles[provider.setup_status] || "text-[var(--app-muted)]";
              const setupDetails = (provider.setup_details || {}) as Record<string, unknown>;
              const capabilityCopy = providerCapabilityCopy(provider, setupDetails);

              return (
                <div key={provider.platform} className="space-y-1">
                  <button
                    type="button"
                    onClick={() => void connectPlatform(provider.platform)}
                    disabled={isConnecting || !isReady}
                    className={`w-full rounded-md px-3 py-2 text-sm font-semibold transition ${
                      isReady ? brand.baseClassName : brand.disabledClassName
                    } ${!isReady ? "cursor-not-allowed" : ""}`}
                  >
                    <span className="flex items-center justify-between gap-2">
                      <span className="flex min-w-0 items-center gap-2.5">
                        {brand.icon}
                        <span className="truncate">
                          {isConnecting ? `Connecting ${brand.displayName}...` : brand.buttonLabel}
                        </span>
                      </span>
                      <span className="rounded-full bg-white/20 px-1.5 py-0.5 text-[10px] leading-none">
                        {provider.connected_account_count}
                      </span>
                    </span>
                  </button>

                  <p className={`px-1 text-[11px] ${setupClass}`}>
                    {isReady ? "Ready" : provider.setup_message || "Not configured"}
                    {capabilityCopy ? ` · ${capabilityCopy}` : ""}
                  </p>
                </div>
              );
            })}
          </div>
        </Card>

        <Card padding="sm">
          <h3 className="text-sm font-semibold text-[var(--app-text)]">Connected accounts</h3>
          <p className="mt-1 text-xs text-[var(--app-muted)]">
            Compact account list with disconnect controls and destination details.
          </p>

          <div className="mt-3 space-y-2.5">
            {providers.map((provider) => {
              const providerAccounts = accountsByPlatform[provider.platform] || [];
              const facebookAccountRows = providerAccounts.filter(
                (account) => account.destination_type === "facebook_account"
              );
              const facebookPageRows = providerAccounts.filter(
                (account) => account.destination_type === "facebook_page"
              );

              const brand = getPlatformBrandMeta(provider.platform);
              const setupClass = statusTextStyles[provider.setup_status] || "text-[var(--app-muted)]";
              const setupDetails = (provider.setup_details || {}) as Record<string, unknown>;
              const capabilityCopy = providerCapabilityCopy(provider, setupDetails);

              return (
                <div key={provider.platform} className="rounded-lg border border-[var(--app-border)] bg-[#F9FBFF] p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                      <span
                        className={`inline-flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md shadow-sm ${brand.badgeClassName}`}
                        aria-label={`${brand.displayName} logo`}
                      >
                        {brand.icon}
                      </span>
                      <div>
                        <p className="text-sm font-semibold text-[var(--app-text)]">{provider.display_name}</p>
                        <p className={`text-[11px] ${setupClass}`}>
                          {provider.setup_status === "ready" ? "Ready" : provider.setup_message || "Not configured"}
                        </p>
                      </div>
                    </div>
                    <span className="rounded-full bg-white px-2 py-0.5 text-[11px] font-medium text-[var(--app-muted)] shadow-sm">
                      {provider.connected_account_count} connected
                    </span>
                  </div>

                  {capabilityCopy ? <p className="mt-1 text-[11px] text-[var(--app-subtle)]">{capabilityCopy}</p> : null}

                  <div className="mt-2 space-y-2">
                    {provider.platform === "facebook" ? (
                      <>
                        <div className="space-y-1.5">
                          <p className="text-[11px] font-semibold uppercase tracking-wide text-[var(--app-muted)]">Profiles</p>
                          {renderAccountRows("facebook", facebookAccountRows, "No Facebook account connected yet.")}
                        </div>

                        <div className="space-y-1.5">
                          <p className="text-[11px] font-semibold uppercase tracking-wide text-[var(--app-muted)]">Pages</p>
                          {renderAccountRows(
                            "facebook",
                            facebookPageRows,
                            "No Pages discovered yet for automated publishing."
                          )}
                          <p className="text-[11px] text-[var(--app-subtle)]">
                            Personal profile sharing remains available from the clip publish panel.
                          </p>
                        </div>
                      </>
                    ) : (
                      renderAccountRows(provider.platform, providerAccounts, "No accounts connected yet.")
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      </div>
    </div>
  );
}
