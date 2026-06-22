"use client";

import { useEffect, useMemo, useState } from "react";

import { getPlatformBrandMeta } from "@/components/connections/platformBrand";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { api, ApiError } from "@/lib/api";
import { ConnectedAccount, SocialPlatform, SocialWorkflow } from "@/types";

const DESTINATION_PLATFORMS: SocialPlatform[] = ["instagram", "threads", "facebook", "youtube", "x", "tiktok"];

function statusLabel(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function destinationName(account: ConnectedAccount): string {
  return account.display_name || account.username_or_channel_name || account.external_account_id;
}

export function SocialWorkflowsPanel() {
  const [accounts, setAccounts] = useState<ConnectedAccount[]>([]);
  const [workflows, setWorkflows] = useState<SocialWorkflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("Instagram repurpose workflow");
  const [sourceAccountId, setSourceAccountId] = useState("");
  const [copyMode, setCopyMode] = useState<"reuse_source" | "platform_ai" | "both">("both");
  const [selectedDestinationIds, setSelectedDestinationIds] = useState<Set<string>>(new Set());

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [accountRows, workflowRows] = await Promise.all([
        api.get<ConnectedAccount[]>("/api/social/accounts"),
        api.get<SocialWorkflow[]>("/api/social/workflows"),
      ]);
      setAccounts(accountRows);
      setWorkflows(workflowRows);
      const firstInstagram = accountRows.find(
        (account) => account.platform === "instagram" && account.destination_type === "instagram_professional"
      );
      if (firstInstagram && !sourceAccountId) setSourceAccountId(firstInstagram.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load workflows");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const sourceAccounts = useMemo(
    () => accounts.filter((account) => account.platform === "instagram" && account.destination_type === "instagram_professional"),
    [accounts]
  );

  const destinationAccounts = useMemo(
    () =>
      accounts.filter((account) => {
        if (!DESTINATION_PLATFORMS.includes(account.platform)) return false;
        if (account.platform === "facebook") return account.destination_type === "facebook_page";
        if (account.platform === "instagram") return account.destination_type === "instagram_professional";
        return account.platform !== "linkedin";
      }),
    [accounts]
  );

  const createWorkflow = async () => {
    if (!sourceAccountId) {
      setError("Connect an Instagram professional account first.");
      return;
    }
    const destinations = destinationAccounts
      .filter((account) => selectedDestinationIds.has(account.id))
      .map((account) => ({ platform: account.platform, connected_account_id: account.id }));
    if (!destinations.length) {
      setError("Select at least one destination account.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.post<SocialWorkflow>("/api/social/workflows", {
        name,
        source_platform: "instagram",
        source_account_id: sourceAccountId,
        copy_mode: copyMode,
        auto_publish: true,
        destinations,
      });
      setSelectedDestinationIds(new Set());
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create workflow");
    } finally {
      setSaving(false);
    }
  };

  const pollNow = async (workflowId: string) => {
    setError(null);
    try {
      await api.post(`/api/social/workflows/${workflowId}/poll-now`, {});
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to enqueue workflow poll");
    }
  };

  const pauseOrResume = async (workflow: SocialWorkflow) => {
    setError(null);
    try {
      await api.patch<SocialWorkflow>(`/api/social/workflows/${workflow.id}`, {
        status: workflow.status === "active" ? "paused" : "active",
      });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to update workflow");
    }
  };

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <LoadingSpinner />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {error ? <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div> : null}

      <Card className="space-y-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--app-subtle)]">Official API workflow</p>
          <h2 className="mt-1 text-2xl font-bold text-[var(--app-text)]">Repurpose Instagram posts automatically</h2>
          <p className="mt-1 max-w-3xl text-sm text-[var(--app-muted)]">
            PostBandit polls your connected Instagram professional account. When the official API exposes a usable video file,
            it imports, processes, exports, and publishes it to your selected destinations. No scraping or browser automation.
          </p>
        </div>

        <div className="grid gap-4 lg:grid-cols-[1fr_1fr_220px]">
          <label className="space-y-1 text-sm font-medium text-[var(--app-muted)]">
            Workflow name
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="w-full rounded-xl border border-[var(--app-border)] bg-white px-3 py-2 text-[var(--app-text)] outline-none focus:border-[var(--app-primary)]"
            />
          </label>
          <label className="space-y-1 text-sm font-medium text-[var(--app-muted)]">
            Instagram source
            <select
              value={sourceAccountId}
              onChange={(event) => setSourceAccountId(event.target.value)}
              className="w-full rounded-xl border border-[var(--app-border)] bg-white px-3 py-2 text-[var(--app-text)] outline-none focus:border-[var(--app-primary)]"
            >
              <option value="">Select account</option>
              {sourceAccounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {destinationName(account)}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1 text-sm font-medium text-[var(--app-muted)]">
            Copy mode
            <select
              value={copyMode}
              onChange={(event) => setCopyMode(event.target.value as typeof copyMode)}
              className="w-full rounded-xl border border-[var(--app-border)] bg-white px-3 py-2 text-[var(--app-text)] outline-none focus:border-[var(--app-primary)]"
            >
              <option value="both">AI copy, fallback to source</option>
              <option value="platform_ai">Platform AI copy</option>
              <option value="reuse_source">Reuse source copy</option>
            </select>
          </label>
        </div>

        <div>
          <p className="mb-2 text-sm font-semibold text-[var(--app-text)]">Destinations</p>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {destinationAccounts.map((account) => {
              const brand = getPlatformBrandMeta(account.platform);
              const selected = selectedDestinationIds.has(account.id);
              return (
                <button
                  key={account.id}
                  type="button"
                  onClick={() => {
                    const next = new Set(selectedDestinationIds);
                    if (selected) next.delete(account.id);
                    else next.add(account.id);
                    setSelectedDestinationIds(next);
                  }}
                  className={`flex items-center gap-3 rounded-xl border px-3 py-2 text-left transition ${
                    selected ? "border-[var(--app-primary)] bg-[#EEF3FF]" : "border-[var(--app-border)] bg-white hover:bg-[#F8FAFF]"
                  }`}
                >
                  <span className={`flex h-8 w-8 items-center justify-center rounded-lg ${brand.badgeClassName}`}>
                    {brand.icon}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-semibold text-[var(--app-text)]">{brand.displayName}</span>
                    <span className="block truncate text-xs text-[var(--app-muted)]">{destinationName(account)}</span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-[var(--app-muted)]">
            Auto-publish is enabled. If Instagram does not provide a reusable video URL, the run will be marked Original file required.
          </p>
          <Button onClick={() => void createWorkflow()} disabled={saving}>
            {saving ? "Saving..." : "Create Workflow"}
          </Button>
        </div>
      </Card>

      <div className="space-y-3">
        {workflows.length === 0 ? (
          <Card>
            <p className="text-sm text-[var(--app-muted)]">No workflows yet. Create one above after connecting Instagram and at least one destination.</p>
          </Card>
        ) : (
          workflows.map((workflow) => (
            <Card key={workflow.id} className="space-y-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-lg font-bold text-[var(--app-text)]">{workflow.name}</h3>
                    <span className="rounded-full bg-[#EEF3FF] px-2 py-0.5 text-xs font-semibold text-[var(--app-primary)]">
                      {statusLabel(workflow.status)}
                    </span>
                  </div>
                  <p className="text-sm text-[var(--app-muted)]">
                    Instagram source · {workflow.destination_targets_json.length} destination(s) · {statusLabel(workflow.copy_mode)}
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button variant="secondary" onClick={() => void pollNow(workflow.id)}>Poll now</Button>
                  <Button variant="secondary" onClick={() => void pauseOrResume(workflow)}>
                    {workflow.status === "active" ? "Pause" : "Resume"}
                  </Button>
                </div>
              </div>

              <div className="overflow-hidden rounded-xl border border-[var(--app-border)]">
                <div className="grid grid-cols-[1.2fr_150px_1fr] bg-[var(--app-surface-soft)] px-3 py-2 text-xs font-semibold uppercase tracking-wide text-[var(--app-subtle)]">
                  <span>Source post</span>
                  <span>Status</span>
                  <span>Result</span>
                </div>
                {workflow.source_posts.length === 0 ? (
                  <p className="px-3 py-3 text-sm text-[var(--app-muted)]">No detected source posts yet.</p>
                ) : (
                  workflow.source_posts.slice(0, 8).map((post) => (
                    <div key={post.id} className="grid grid-cols-[1.2fr_150px_1fr] gap-3 border-t border-[var(--app-border)] px-3 py-2 text-sm">
                      <div className="min-w-0">
                        <p className="truncate font-semibold text-[var(--app-text)]">{post.caption_snapshot || post.permalink || post.external_post_id}</p>
                        {post.permalink ? (
                          <a className="text-xs text-[var(--app-primary)] hover:underline" href={post.permalink} target="_blank" rel="noreferrer">
                            Open source
                          </a>
                        ) : null}
                      </div>
                      <span className="text-[var(--app-muted)]">{statusLabel(post.status)}</span>
                      <span className="text-[var(--app-muted)]">
                        {post.error_message || (post.export_id ? "Export prepared" : post.video_id ? "Video imported" : "Waiting")}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
