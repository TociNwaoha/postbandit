"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { Card } from "@/components/ui/Card";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { api, ApiError } from "@/lib/api";
import { ConnectedAccount, SocialProvider } from "@/types";

type ReviewConnectionState = "not_connected" | "connecting" | "connected" | "failed";

interface ProfileSummary {
  id: string;
  username: string | null;
  displayName: string | null;
  accountType: string | null;
  profilePictureUrl: string | null;
  source: string | null;
  metadataSummary: Record<string, unknown>;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function extractProfileSummary(account: ConnectedAccount): ProfileSummary {
  const metadata = isRecord(account.metadata_json) ? account.metadata_json : {};
  const profile = isRecord(metadata.profile) ? metadata.profile : {};

  const username = account.username_or_channel_name || (typeof profile.username === "string" ? profile.username : null);
  const displayName = account.display_name || (typeof profile.name === "string" ? profile.name : null);
  const accountType =
    (typeof metadata.account_type === "string" ? metadata.account_type : null) ||
    (typeof profile.account_type === "string" ? profile.account_type : null);
  const profilePictureUrl =
    typeof profile.profile_picture_url === "string" && profile.profile_picture_url.startsWith("http")
      ? profile.profile_picture_url
      : null;

  const metadataSummary: Record<string, unknown> = {
    login_model: typeof metadata.login_model === "string" ? metadata.login_model : "instagram_login",
    source: typeof metadata.source === "string" ? metadata.source : null,
    account_type: accountType,
    profile: {
      id: profile.id ?? account.external_account_id,
      username,
      name: displayName,
      account_type: accountType,
    },
  };

  return {
    id: account.external_account_id,
    username,
    displayName,
    accountType,
    profilePictureUrl,
    source: typeof metadata.source === "string" ? metadata.source : null,
    metadataSummary,
  };
}

function callbackReasonText(reason: string | null): string {
  if (!reason) return "Connection failed.";
  if (reason === "oauth_session_expired") return "OAuth session expired. Start Connect Instagram again.";
  if (reason === "oauth_exchange_failed") {
    return "OAuth was completed but PostBandit could not resolve a professional Instagram account. Use a Business or Creator account and retry.";
  }
  if (reason === "missing_code") return "OAuth callback did not include an authorization code.";
  if (reason === "invalid_state" || reason === "missing_state") return "OAuth callback state validation failed.";
  if (reason === "internal_callback_error") return "Callback processing failed unexpectedly.";
  return `Connection failed: ${reason}`;
}

function SectionCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <h3 className="text-base font-semibold text-white">{title}</h3>
      {subtitle ? <p className="mt-1 text-xs text-slate-400">{subtitle}</p> : null}
      <div className="mt-4">{children}</div>
    </Card>
  );
}

export function MetaInstagramReviewPanel() {
  const searchParams = useSearchParams();
  const [providers, setProviders] = useState<SocialProvider[]>([]);
  const [accounts, setAccounts] = useState<ConnectedAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);

  const callbackStatus = searchParams.get("status");
  const callbackPlatform = searchParams.get("platform");
  const callbackReason = searchParams.get("message");

  const instagramProvider = providers.find((provider) => provider.platform === "instagram");
  const instagramAccounts = accounts.filter((account) => account.platform === "instagram");

  const callbackMessage = useMemo(() => {
    if (!callbackStatus || callbackPlatform !== "instagram") return null;
    if (callbackStatus === "connected") return "Instagram account connected successfully.";
    return callbackReasonText(callbackReason);
  }, [callbackReason, callbackPlatform, callbackStatus]);

  const reviewState: ReviewConnectionState = useMemo(() => {
    if (connecting) return "connecting";
    if (instagramAccounts.length > 0) return "connected";
    if (callbackStatus && callbackPlatform === "instagram" && callbackStatus !== "connected") return "failed";
    return "not_connected";
  }, [callbackPlatform, callbackStatus, connecting, instagramAccounts.length]);

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
      setError(err instanceof ApiError ? err.message : "Failed to load Instagram review data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const startConnect = async () => {
    setConnecting(true);
    setActionError(null);
    try {
      const data = await api.post<{ authorization_url: string }>("/api/social/instagram/connect", {
        return_to: "/review/meta-instagram",
      });
      window.location.href = data.authorization_url;
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Failed to start Instagram OAuth.");
      setConnecting(false);
    }
  };

  const profileCards = instagramAccounts.map((account) => {
    const summary = extractProfileSummary(account);
    return (
      <div key={account.id} className="rounded-lg border border-slate-700 bg-slate-900/50 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-white">{summary.displayName || summary.username || summary.id}</p>
            <p className="mt-1 text-xs text-slate-300">@{summary.username || "unknown"}</p>
            <p className="mt-1 text-xs text-slate-400">External Account ID: {summary.id}</p>
            <p className="mt-1 text-xs text-slate-400">Account Type: {summary.accountType || "not returned"}</p>
            <p className="mt-1 text-xs text-slate-500">Source: {summary.source || "not returned"}</p>
          </div>
          {summary.profilePictureUrl ? (
            <img
              src={summary.profilePictureUrl}
              alt={`${summary.username || "instagram"} profile`}
              className="h-16 w-16 rounded-full border border-slate-700 object-cover"
            />
          ) : null}
        </div>
        <pre className="mt-3 overflow-x-auto rounded-md bg-slate-950/70 p-3 text-[11px] text-slate-300">
          {JSON.stringify(summary.metadataSummary, null, 2)}
        </pre>
      </div>
    );
  });

  const providerReady = instagramProvider?.setup_status === "ready";

  return (
    <div className="space-y-5">
      <SectionCard title="Meta Reviewer Recording Steps" subtitle="Use this exact flow during your app-review recording.">
        <ol className="list-decimal space-y-2 pl-5 text-sm text-slate-200">
          <li>Sign in to PostBandit.</li>
          <li>Click <span className="font-semibold text-white">Connect Instagram</span>.</li>
          <li>Complete the Meta OAuth prompts for your Instagram professional account.</li>
          <li>Return to this page and show the connected Instagram profile details.</li>
        </ol>
      </SectionCard>

      <SectionCard title="Instagram Connection State" subtitle="Real state from the live social provider and account records.">
        {loading ? (
          <div className="inline-flex items-center gap-2 text-sm text-slate-300">
            <LoadingSpinner size="sm" />
            Loading state...
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-slate-200">
              Current state:{" "}
              <span className="font-semibold text-white">
                {reviewState === "not_connected" && "not_connected"}
                {reviewState === "connecting" && "connecting"}
                {reviewState === "connected" && "connected"}
                {reviewState === "failed" && "failed"}
              </span>
            </p>
            {callbackMessage ? (
              <p className={`text-sm ${reviewState === "failed" ? "text-red-300" : "text-emerald-300"}`}>
                {callbackMessage}
              </p>
            ) : null}
            {error ? <p className="text-sm text-red-300">{error}</p> : null}
            {actionError ? <p className="text-sm text-red-300">{actionError}</p> : null}
            {!providerReady ? (
              <p className="text-sm text-amber-300">
                {instagramProvider?.setup_message || "Instagram provider is not configured."}
              </p>
            ) : null}
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => void startConnect()}
                disabled={!providerReady || connecting}
                className="rounded-md bg-[#7C3AED] px-4 py-2 text-sm font-medium text-white hover:bg-[#6D28D9] disabled:opacity-60"
              >
                {connecting ? "Connecting..." : "Connect Instagram"}
              </button>
              <button
                type="button"
                onClick={() => void load()}
                disabled={loading}
                className="rounded-md border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-60"
              >
                Refresh
              </button>
              <Link href="/connections" className="text-sm text-[#A78BFA] hover:text-[#C4B5FD]">
                Open full Connections page
              </Link>
            </div>
          </div>
        )}
      </SectionCard>

      <SectionCard
        title="Connected Instagram Profile"
        subtitle="This section displays the real account data persisted after OAuth."
      >
        {loading ? null : profileCards.length ? (
          <div className="space-y-3">{profileCards}</div>
        ) : (
          <p className="text-sm text-slate-400">No Instagram account connected yet.</p>
        )}
      </SectionCard>

      <SectionCard
        title="Future Meta Permission Demos"
        subtitle="This review layout is reusable for additional Meta permissions in later passes."
      >
        <ul className="list-disc space-y-1 pl-5 text-sm text-slate-300">
          <li>`instagram_business_manage_messages`</li>
          <li>`instagram_business_manage_comments`</li>
          <li>`instagram_manage_insights` and related insights flows</li>
        </ul>
      </SectionCard>
    </div>
  );
}
