"use client";

import { useEffect, useMemo, useState } from "react";

import { getPlatformBrandMeta } from "@/components/connections/platformBrand";
import { UploadModal } from "@/components/upload/UploadModal";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { api, ApiError } from "@/lib/api";
import {
  ConnectedAccount,
  Export,
  FullVideoExportResponse,
  SocialPlatform,
  SocialPublishJob,
  SocialWorkflow,
  SocialWorkflowImportMode,
  SocialWorkflowSourcePost,
  VideoListItem,
} from "@/types";

const DESTINATION_PLATFORMS: SocialPlatform[] = ["instagram", "threads", "facebook", "youtube", "x", "tiktok"];
const SOURCE_PLATFORMS: SocialPlatform[] = ["instagram", "youtube", "facebook"];

function statusLabel(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function destinationName(account: ConnectedAccount): string {
  return account.display_name || account.username_or_channel_name || account.external_account_id;
}

function shortId(value: string): string {
  return value.slice(0, 8);
}

function formatDateTime(value: string | null): string {
  if (!value) return "Not scheduled";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function sourcePostTitle(post: SocialWorkflowSourcePost): string {
  return post.caption_snapshot || post.permalink || `${getPlatformBrandMeta(post.source_platform).displayName} post ${shortId(post.external_post_id)}`;
}

function exportLabel(item: Export): string {
  const title = item.clip_title || item.video_title || `Export ${shortId(item.id)}`;
  return `${title} · ${item.aspect_ratio} · ${shortId(item.id)}`;
}

function videoLabel(item: VideoListItem): string {
  const title = item.title || `Video ${shortId(item.id)}`;
  const duration = item.duration_sec ? `${Math.round(item.duration_sec / 60)}m` : "ready";
  return `${title} · ${duration} · ${shortId(item.id)}`;
}

function sourceStatusDescription(post: SocialWorkflowSourcePost): string {
  if (post.error_message) return post.error_message;
  if (post.status === "original_required") return "Official API found the post, but did not provide a reusable source video file.";
  if (post.status === "detected") return "Detected and waiting to import.";
  if (post.status === "importing") return "Downloading the source through the official API.";
  if (post.status === "imported_processing") return "Imported into PostBandit and processing.";
  if (post.status === "ready_to_publish") return "Ready for workflow publishing.";
  if (post.status === "publishing") return "Publishing to selected destinations.";
  if (post.status === "completed") return "Workflow completed.";
  if (post.status === "partial_failed") return "Some destinations failed; successful destinations remain published.";
  return "Workflow step failed.";
}

function publishJobLabel(job: SocialPublishJob): string {
  if (job.status === "scheduled") return `Scheduled ${formatDateTime(job.scheduled_for)}`;
  if (job.status === "published") return "Published";
  if (job.status === "queued") return "Queued";
  if (job.status === "publishing") return "Publishing";
  if (job.status === "cancelled") return "Cancelled";
  if (job.status === "waiting_user_action") return "Needs action";
  if (job.status === "provider_not_configured") return "Provider setup needed";
  return "Failed";
}

function statusBadgeClass(status: string): string {
  if (["completed", "published"].includes(status)) return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (["scheduled", "ready_to_publish"].includes(status)) return "bg-blue-50 text-blue-700 border-blue-200";
  if (["queued", "publishing", "importing", "imported_processing", "detected"].includes(status)) return "bg-amber-50 text-amber-700 border-amber-200";
  if (["original_required", "waiting_user_action", "provider_not_configured"].includes(status)) return "bg-orange-50 text-orange-700 border-orange-200";
  if (["cancelled"].includes(status)) return "bg-slate-50 text-slate-600 border-slate-200";
  return "bg-red-50 text-red-700 border-red-200";
}

function isValidWorkflowSource(account: ConnectedAccount, platform: SocialPlatform): boolean {
  if (platform === "instagram") {
    return account.platform === "instagram" && account.destination_type === "instagram_professional";
  }
  if (platform === "facebook") {
    return account.platform === "facebook" && account.destination_type === "facebook_page";
  }
  if (platform === "youtube") {
    return account.platform === "youtube";
  }
  return false;
}

function sourceHelpText(platform: SocialPlatform): string {
  if (platform === "youtube") {
    return "PostBandit detects new YouTube uploads with the official API. YouTube does not provide a reusable source file, so runs usually require attaching the original export/file.";
  }
  if (platform === "facebook") {
    return "PostBandit polls your connected Facebook Page videos. If Graph exposes a reusable source URL, it imports automatically; otherwise it marks Original file required.";
  }
  return "PostBandit polls your connected Instagram professional account. If the official API exposes a reusable video file, it imports automatically.";
}

function workflowNeedsReconnect(workflow: SocialWorkflow): boolean {
  return workflow.source_account_status === "needs_reconnection";
}

function workflowSourceMessage(workflow: SocialWorkflow): string | null {
  if (workflow.source_account_status === "needs_reconnection") {
    return workflow.source_account_message || `Reconnect the ${getPlatformBrandMeta(workflow.source_platform).displayName} source account.`;
  }
  if (workflow.source_account_status === "poll_error") {
    return workflow.source_account_message || workflow.last_error || "The source poll failed. Try polling again or reconnect the source account.";
  }
  return null;
}

function workflowImportMode(workflow: SocialWorkflow): SocialWorkflowImportMode {
  const value = workflow.poll_cursor_json?.source_import_mode;
  if (value === "start_now" || value === "last_n" || value === "manual_select") return value;
  return "manual_select";
}

function workflowDestinationIds(workflow: SocialWorkflow): string[] {
  return workflow.destination_targets_json
    .map((target) => target.connected_account_id)
    .filter((value): value is string => typeof value === "string" && value.length > 0);
}

function canStartSourcePost(post: SocialWorkflowSourcePost): boolean {
  return ["detected", "import_failed", "ready_to_publish"].includes(post.status);
}

function startButtonLabel(post: SocialWorkflowSourcePost): string {
  if (post.status === "ready_to_publish") return "Publish now";
  if (post.status === "import_failed") return "Retry import";
  return "Import / publish";
}

export function SocialWorkflowsPanel() {
  const [accounts, setAccounts] = useState<ConnectedAccount[]>([]);
  const [workflows, setWorkflows] = useState<SocialWorkflow[]>([]);
  const [readyExports, setReadyExports] = useState<Export[]>([]);
  const [readyVideos, setReadyVideos] = useState<VideoListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [attachingPostId, setAttachingPostId] = useState<string | null>(null);
  const [preparingVideoPostId, setPreparingVideoPostId] = useState<string | null>(null);
  const [startingPostId, setStartingPostId] = useState<string | null>(null);
  const [selectedExportByPost, setSelectedExportByPost] = useState<Record<string, string>>({});
  const [selectedVideoByPost, setSelectedVideoByPost] = useState<Record<string, string>>({});
  const [selectedDestinationIdsByPost, setSelectedDestinationIdsByPost] = useState<Record<string, string[]>>({});
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("Social repurpose workflow");
  const [sourcePlatform, setSourcePlatform] = useState<SocialPlatform>("instagram");
  const [sourceAccountId, setSourceAccountId] = useState("");
  const [copyMode, setCopyMode] = useState<"reuse_source" | "platform_ai" | "both">("both");
  const [sourceImportMode, setSourceImportMode] = useState<SocialWorkflowImportMode>("manual_select");
  const [sourceBackfillLimit, setSourceBackfillLimit] = useState(3);
  const [selectedDestinationIds, setSelectedDestinationIds] = useState<Set<string>>(new Set());

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [accountRows, workflowRows, exportRows, videoRows] = await Promise.all([
        api.get<ConnectedAccount[]>("/api/social/accounts"),
        api.get<SocialWorkflow[]>("/api/social/workflows"),
        api.get<Export[]>("/api/exports"),
        api.get<VideoListItem[]>("/api/videos?limit=100&offset=0"),
      ]);
      setAccounts(accountRows);
      setWorkflows(workflowRows);
      setReadyExports(exportRows.filter((item) => item.status === "ready"));
      setReadyVideos(videoRows.filter((item) => item.status === "ready"));
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
    () => accounts.filter((account) => isValidWorkflowSource(account, sourcePlatform)),
    [accounts, sourcePlatform]
  );

  useEffect(() => {
    if (sourceAccountId && sourceAccounts.some((account) => account.id === sourceAccountId)) return;
    setSourceAccountId(sourceAccounts[0]?.id || "");
  }, [sourceAccountId, sourceAccounts]);

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
      setError(`Connect a ${getPlatformBrandMeta(sourcePlatform).displayName} source account first.`);
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
        source_platform: sourcePlatform,
        source_account_id: sourceAccountId,
        copy_mode: copyMode,
        auto_publish: true,
        source_import_mode: sourceImportMode,
        source_backfill_limit: sourceImportMode === "last_n" ? sourceBackfillLimit : null,
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
    setNotice(null);
    setError(null);
    try {
      await api.post(`/api/social/workflows/${workflowId}/poll-now`, {});
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to enqueue workflow poll");
    }
  };

  const pauseOrResume = async (workflow: SocialWorkflow) => {
    setNotice(null);
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

  const attachExport = async (workflow: SocialWorkflow, post: SocialWorkflowSourcePost, exportIdOverride?: string) => {
    const postId = post.id;
    const exportId = selectedExportByPost[postId] || readyExports[0]?.id;
    const selectedExportId = exportIdOverride || exportId;
    if (!selectedExportId) {
      setError("No ready exports are available to attach yet.");
      return;
    }
    setAttachingPostId(postId);
    setNotice(null);
    setError(null);
    try {
      await api.post(`/api/social/workflows/source-posts/${postId}/attach-export`, { export_id: selectedExportId });
      await api.post(`/api/social/workflows/source-posts/${postId}/start`, {
        destinations: selectedDestinationsForPost(workflow, postId)
          .map((accountId) => destinationAccounts.find((account) => account.id === accountId))
          .filter(Boolean)
          .map((account) => ({ platform: account!.platform, connected_account_id: account!.id })),
      });
      setNotice("Export attached. Publishing will start now, or automatically after the export finishes rendering.");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to attach export and continue workflow");
    } finally {
      setAttachingPostId(null);
    }
  };

  const useReadyVideoOriginal = async (workflow: SocialWorkflow, post: SocialWorkflowSourcePost) => {
    const videoId = selectedVideoByPost[post.id] || readyVideos[0]?.id;
    if (!videoId) {
      setError("No ready videos are available yet. Upload the original first, then wait for processing to finish.");
      return;
    }
    setPreparingVideoPostId(post.id);
    setNotice(null);
    setError(null);
    try {
      const payload = await api.post<FullVideoExportResponse>(`/api/social/videos/${videoId}/full-export`, {});
      await api.post(`/api/social/workflows/source-posts/${post.id}/attach-export`, { export_id: payload.export_id });
      if (payload.export_status === "ready") {
        await api.post(`/api/social/workflows/source-posts/${post.id}/start`, {
          destinations: selectedDestinationsForPost(workflow, post.id)
            .map((accountId) => destinationAccounts.find((account) => account.id === accountId))
            .filter(Boolean)
            .map((account) => ({ platform: account!.platform, connected_account_id: account!.id })),
        });
        setNotice("Ready video attached and publishing started.");
      } else {
        setNotice("Ready video attached. PostBandit is rendering the full export and will publish when it is ready.");
      }
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to use this video as the workflow original");
    } finally {
      setPreparingVideoPostId(null);
    }
  };

  const selectedDestinationsForPost = (workflow: SocialWorkflow, postId: string): string[] => {
    return selectedDestinationIdsByPost[postId] || workflowDestinationIds(workflow);
  };

  const togglePostDestination = (workflow: SocialWorkflow, postId: string, accountId: string) => {
    const current = selectedDestinationsForPost(workflow, postId);
    const next = current.includes(accountId) ? current.filter((id) => id !== accountId) : [...current, accountId];
    setSelectedDestinationIdsByPost((state) => ({ ...state, [postId]: next }));
  };

  const startSourcePost = async (workflow: SocialWorkflow, post: SocialWorkflowSourcePost) => {
    const selectedIds = selectedDestinationsForPost(workflow, post.id);
    const destinations = destinationAccounts
      .filter((account) => selectedIds.includes(account.id))
      .map((account) => ({ platform: account.platform, connected_account_id: account.id }));
    if (!destinations.length) {
      setError("Select at least one destination for this source post.");
      return;
    }
    setStartingPostId(post.id);
    setNotice(null);
    setError(null);
    try {
      await api.post(`/api/social/workflows/source-posts/${post.id}/start`, { destinations });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to start source post workflow");
    } finally {
      setStartingPostId(null);
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
      {notice ? <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700">{notice}</div> : null}

      <Card className="space-y-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--app-subtle)]">Official API workflow</p>
          <h2 className="mt-1 text-2xl font-bold text-[var(--app-text)]">Repurpose social posts automatically</h2>
          <p className="mt-1 max-w-3xl text-sm text-[var(--app-muted)]">
            Choose Instagram, YouTube, or Facebook as a source. PostBandit uses official APIs only, then imports when a reusable
            file is available or marks the run Original file required. No scraping or browser automation.
          </p>
        </div>

        <div className="grid gap-4 lg:grid-cols-[1fr_180px_1fr_220px]">
          <label className="space-y-1 text-sm font-medium text-[var(--app-muted)]">
            Workflow name
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="w-full rounded-xl border border-[var(--app-border)] bg-white px-3 py-2 text-[var(--app-text)] outline-none focus:border-[var(--app-primary)]"
            />
          </label>
          <label className="space-y-1 text-sm font-medium text-[var(--app-muted)]">
            Source app
            <select
              value={sourcePlatform}
              onChange={(event) => setSourcePlatform(event.target.value as SocialPlatform)}
              className="w-full rounded-xl border border-[var(--app-border)] bg-white px-3 py-2 text-[var(--app-text)] outline-none focus:border-[var(--app-primary)]"
            >
              {SOURCE_PLATFORMS.map((platform) => (
                <option key={platform} value={platform}>
                  {getPlatformBrandMeta(platform).displayName}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1 text-sm font-medium text-[var(--app-muted)]">
            {getPlatformBrandMeta(sourcePlatform).displayName} source
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

        <div className="rounded-xl border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-[var(--app-text)]">When source posts are found</p>
              <p className="mt-1 text-xs text-[var(--app-muted)]">
                Default is safest: detect posts first, then let the user choose which ones to import and publish.
              </p>
            </div>
            {sourceImportMode === "last_n" ? (
              <label className="flex items-center gap-2 text-xs font-medium text-[var(--app-muted)]">
                Import last
                <select
                  value={sourceBackfillLimit}
                  onChange={(event) => setSourceBackfillLimit(Number(event.target.value))}
                  className="rounded-lg border border-[var(--app-border)] bg-white px-2 py-1 text-[var(--app-text)] outline-none"
                >
                  {[1, 3, 5, 10].map((count) => (
                    <option key={count} value={count}>
                      {count}
                    </option>
                  ))}
                </select>
                post(s)
              </label>
            ) : null}
          </div>
          <div className="mt-3 grid gap-2 md:grid-cols-3">
            {[
              {
                value: "manual_select",
                title: "Show source posts first",
                description: "Detect posts only. User clicks Import / publish per post.",
              },
              {
                value: "start_now",
                title: "Start from now",
                description: "Ignore old posts. Auto-process future posts only.",
              },
              {
                value: "last_n",
                title: "Import last N posts",
                description: "Process a small backfill now, then future posts.",
              },
            ].map((option) => {
              const selected = sourceImportMode === option.value;
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setSourceImportMode(option.value as SocialWorkflowImportMode)}
                  className={`rounded-xl border px-3 py-2 text-left transition ${
                    selected ? "border-[var(--app-primary)] bg-white shadow-sm" : "border-[var(--app-border)] bg-white/60 hover:bg-white"
                  }`}
                >
                  <span className="block text-sm font-semibold text-[var(--app-text)]">{option.title}</span>
                  <span className="mt-1 block text-xs text-[var(--app-muted)]">{option.description}</span>
                </button>
              );
            })}
          </div>
        </div>

        <p className="rounded-xl border border-[var(--app-border)] bg-[var(--app-surface-soft)] px-3 py-2 text-xs text-[var(--app-muted)]">
          {sourceHelpText(sourcePlatform)}
        </p>

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
            Auto-publish runs only after a source post is selected/imported. If the source API does not provide a reusable video URL,
            the run will be marked Original file required.
          </p>
          <Button onClick={() => void createWorkflow()} disabled={saving}>
            {saving ? "Saving..." : "Create Workflow"}
          </Button>
        </div>
      </Card>

      <div className="space-y-3">
        {workflows.length === 0 ? (
          <Card>
            <p className="text-sm text-[var(--app-muted)]">
              No workflows yet. Create one above after connecting a source account and at least one destination.
            </p>
          </Card>
        ) : (
          workflows.map((workflow) => {
            const needsReconnect = workflowNeedsReconnect(workflow);
            const sourceMessage = workflowSourceMessage(workflow);
            const sourceBrand = getPlatformBrandMeta(workflow.source_platform);
            return (
            <Card key={workflow.id} className="space-y-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-lg font-bold text-[var(--app-text)]">{workflow.name}</h3>
                    <span className="rounded-full bg-[#EEF3FF] px-2 py-0.5 text-xs font-semibold text-[var(--app-primary)]">
                      {statusLabel(workflow.status)}
                    </span>
                    {needsReconnect ? (
                      <span className="rounded-full border border-orange-200 bg-orange-50 px-2 py-0.5 text-xs font-semibold text-orange-700">
                        Needs reconnection
                      </span>
                    ) : null}
                  </div>
                  <p className="text-sm text-[var(--app-muted)]">
                    {sourceBrand.displayName} source · {workflow.destination_targets_json.length} destination(s) · {statusLabel(workflow.copy_mode)}
                  </p>
                  <p className="mt-1 text-xs text-[var(--app-subtle)]">
                    Intake: {statusLabel(workflowImportMode(workflow))}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs text-[var(--app-muted)]">
                    <span className="rounded-full bg-[var(--app-surface-soft)] px-2 py-1">
                      {workflow.source_posts.length} source post(s)
                    </span>
                    <span className="rounded-full bg-[var(--app-surface-soft)] px-2 py-1">
                      {workflow.source_posts.flatMap((post) => post.publish_jobs || []).filter((job) => job.status === "scheduled").length} scheduled
                    </span>
                    <span className="rounded-full bg-[var(--app-surface-soft)] px-2 py-1">
                      {workflow.source_posts.flatMap((post) => post.publish_jobs || []).filter((job) => job.status === "published").length} published
                    </span>
                    <span className="rounded-full bg-[var(--app-surface-soft)] px-2 py-1">
                      {workflow.source_posts.filter((post) => post.status === "original_required").length} need original
                    </span>
                  </div>
                </div>
                <div className="flex gap-2">
                  {needsReconnect ? (
                    <a
                      href="/connections"
                      className="inline-flex items-center justify-center rounded-lg border border-orange-200 bg-orange-50 px-4 py-2 text-sm font-medium text-orange-700 transition hover:bg-orange-100"
                    >
                      Reconnect source
                    </a>
                  ) : null}
                  <Button variant="secondary" onClick={() => void pollNow(workflow.id)} disabled={needsReconnect}>
                    Poll now
                  </Button>
                  <Button variant="secondary" onClick={() => void pauseOrResume(workflow)}>
                    {workflow.status === "active" ? "Pause" : "Resume"}
                  </Button>
                </div>
              </div>

              {sourceMessage ? (
                <div
                  className={`rounded-xl border px-3 py-2 text-sm ${
                    needsReconnect
                      ? "border-orange-200 bg-orange-50 text-orange-800"
                      : "border-red-200 bg-red-50 text-red-700"
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p>
                      <span className="font-semibold">
                        {needsReconnect ? `${sourceBrand.displayName} source needs reconnection.` : "Source poll failed."}
                      </span>{" "}
                      {sourceMessage}
                    </p>
                    {needsReconnect ? (
                      <a className="font-semibold text-orange-800 underline underline-offset-2" href="/connections">
                        Open Connections
                      </a>
                    ) : null}
                  </div>
                </div>
              ) : null}

              <div className="rounded-xl border border-[var(--app-border)] bg-[var(--app-surface-soft)] px-3 py-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-[var(--app-subtle)]">Workflow activity</p>
                <p className="text-xs text-[var(--app-muted)]">
                  Detected source posts, available recovery actions, and destination publish jobs created by this workflow.
                </p>
              </div>

              <div className="space-y-3">
                {workflow.source_posts.length === 0 ? (
                  <div
                    className={`rounded-xl border border-dashed px-4 py-5 text-sm ${
                      needsReconnect
                        ? "border-orange-200 bg-orange-50 text-orange-800"
                        : "border-[var(--app-border)] text-[var(--app-muted)]"
                    }`}
                  >
                    {needsReconnect
                      ? `No source posts can be detected until the ${sourceBrand.displayName} source account is reconnected.`
                      : "No detected source posts yet. Use Poll now, or wait for the scheduled poll to find new posts from the selected source account."}
                  </div>
                ) : (
                  workflow.source_posts.slice(0, 12).map((post) => {
                    const sourceBrand = getPlatformBrandMeta(post.source_platform);
                    const jobs = post.publish_jobs || [];
                    return (
                      <div key={post.id} className="rounded-xl border border-[var(--app-border)] bg-white p-3">
                        <div className="grid gap-3 lg:grid-cols-[88px_1fr]">
                          <div className="relative h-24 overflow-hidden rounded-lg bg-[var(--app-surface-soft)]">
                            {post.thumbnail_url ? (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img src={post.thumbnail_url} alt="" className="h-full w-full object-cover" />
                            ) : (
                              <div className="flex h-full w-full items-center justify-center text-xs text-[var(--app-subtle)]">No preview</div>
                            )}
                            <span className={`absolute left-2 top-2 flex h-7 w-7 items-center justify-center rounded-md ${sourceBrand.badgeClassName}`}>
                              {sourceBrand.icon}
                            </span>
                          </div>

                          <div className="min-w-0 space-y-3">
                            <div className="flex flex-wrap items-start justify-between gap-3">
                              <div className="min-w-0">
                                <p className="truncate text-sm font-bold text-[var(--app-text)]">{sourcePostTitle(post)}</p>
                                <p className="text-xs text-[var(--app-muted)]">
                                  Source posted {formatDateTime(post.published_at)} · ID {shortId(post.external_post_id)}
                                </p>
                              </div>
                              <span className={`rounded-full border px-2 py-1 text-xs font-semibold ${statusBadgeClass(post.status)}`}>
                                {statusLabel(post.status)}
                              </span>
                            </div>

                            <p className="text-xs text-[var(--app-muted)]">{sourceStatusDescription(post)}</p>

                            <div className="flex flex-wrap gap-2 text-xs">
                              {post.permalink ? (
                                <a className="rounded-lg border border-[var(--app-border)] px-2 py-1 text-[var(--app-primary)] hover:bg-[#F8FAFF]" href={post.permalink} target="_blank" rel="noreferrer">
                                  Open source
                                </a>
                              ) : null}
                              {post.video_id ? (
                                <a className="rounded-lg border border-[var(--app-border)] px-2 py-1 text-[var(--app-primary)] hover:bg-[#F8FAFF]" href={`/videos/${post.video_id}`}>
                                  View imported video
                                </a>
                              ) : null}
                              {post.export_id ? (
                                <span className="rounded-lg border border-emerald-200 bg-emerald-50 px-2 py-1 text-emerald-700">
                                  Export attached
                                </span>
                              ) : null}
                            </div>

                            {canStartSourcePost(post) ? (
                              <div className="rounded-xl border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-3">
                                <div className="flex flex-wrap items-center justify-between gap-2">
                                  <div>
                                    <p className="text-xs font-semibold text-[var(--app-text)]">Publish this source post</p>
                                    <p className="mt-0.5 text-xs text-[var(--app-muted)]">
                                      Choose destinations, then start import/processing or publish if the export is ready.
                                    </p>
                                  </div>
                                  <Button
                                    size="sm"
                                    onClick={() => void startSourcePost(workflow, post)}
                                    disabled={startingPostId === post.id}
                                  >
                                    {startingPostId === post.id ? "Starting..." : startButtonLabel(post)}
                                  </Button>
                                </div>
                                <div className="mt-3 flex flex-wrap gap-2">
                                  {destinationAccounts.map((account) => {
                                    const brand = getPlatformBrandMeta(account.platform);
                                    const selected = selectedDestinationsForPost(workflow, post.id).includes(account.id);
                                    return (
                                      <button
                                        key={account.id}
                                        type="button"
                                        onClick={() => togglePostDestination(workflow, post.id, account.id)}
                                        className={`flex items-center gap-2 rounded-lg border px-2 py-1.5 text-xs transition ${
                                          selected
                                            ? "border-[var(--app-primary)] bg-white text-[var(--app-text)]"
                                            : "border-[var(--app-border)] bg-white/60 text-[var(--app-muted)] hover:bg-white"
                                        }`}
                                      >
                                        <span className={`flex h-5 w-5 items-center justify-center rounded ${brand.badgeClassName}`}>
                                          {brand.icon}
                                        </span>
                                        <span className="max-w-[130px] truncate">{brand.displayName}</span>
                                      </button>
                                    );
                                  })}
                                </div>
                              </div>
                            ) : null}

                            {post.status === "original_required" ? (
                              <div className="rounded-xl border border-orange-200 bg-orange-50 p-3">
                                <p className="text-xs font-semibold text-orange-800">Original file required</p>
                                <p className="mt-1 text-xs text-orange-700">
                                  Official APIs can see this post but cannot provide a reusable video file. Attach a ready export,
                                  select a ready uploaded video, or upload the original file to continue.
                                </p>
                                <div className="mt-3 grid gap-3 xl:grid-cols-2">
                                  <div className="rounded-lg border border-orange-200 bg-white/70 p-2">
                                    <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-orange-800">
                                      Use existing ready export
                                    </p>
                                    <div className="flex flex-col gap-2 sm:flex-row">
                                      <select
                                        value={selectedExportByPost[post.id] || readyExports[0]?.id || ""}
                                        onChange={(event) =>
                                          setSelectedExportByPost((current) => ({ ...current, [post.id]: event.target.value }))
                                        }
                                        className="min-w-0 flex-1 rounded-lg border border-orange-200 bg-white px-2 py-1.5 text-xs text-[var(--app-text)] outline-none"
                                      >
                                        {readyExports.length === 0 ? <option value="">No ready exports available</option> : null}
                                        {readyExports.map((item) => (
                                          <option key={item.id} value={item.id}>
                                            {exportLabel(item)}
                                          </option>
                                        ))}
                                      </select>
                                      <Button
                                        size="sm"
                                        variant="secondary"
                                        disabled={readyExports.length === 0 || attachingPostId === post.id}
                                        onClick={() => void attachExport(workflow, post)}
                                      >
                                        {attachingPostId === post.id ? "Continuing..." : "Attach & publish"}
                                      </Button>
                                    </div>
                                  </div>

                                  <div className="rounded-lg border border-orange-200 bg-white/70 p-2">
                                    <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-orange-800">
                                      Use uploaded original video
                                    </p>
                                    <div className="flex flex-col gap-2 sm:flex-row">
                                      <select
                                        value={selectedVideoByPost[post.id] || readyVideos[0]?.id || ""}
                                        onChange={(event) =>
                                          setSelectedVideoByPost((current) => ({ ...current, [post.id]: event.target.value }))
                                        }
                                        className="min-w-0 flex-1 rounded-lg border border-orange-200 bg-white px-2 py-1.5 text-xs text-[var(--app-text)] outline-none"
                                      >
                                        {readyVideos.length === 0 ? <option value="">No ready videos available</option> : null}
                                        {readyVideos.map((item) => (
                                          <option key={item.id} value={item.id}>
                                            {videoLabel(item)}
                                          </option>
                                        ))}
                                      </select>
                                      <Button
                                        size="sm"
                                        variant="secondary"
                                        disabled={readyVideos.length === 0 || preparingVideoPostId === post.id}
                                        onClick={() => void useReadyVideoOriginal(workflow, post)}
                                      >
                                        {preparingVideoPostId === post.id ? "Preparing..." : "Use video"}
                                      </Button>
                                    </div>
                                    <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                                      <p className="text-[11px] text-orange-700">
                                        Upload first, then select it here after processing finishes.
                                      </p>
                                      <Button size="sm" variant="ghost" onClick={() => setIsUploadOpen(true)}>
                                        Upload original
                                      </Button>
                                    </div>
                                  </div>
                                </div>
                              </div>
                            ) : null}

                            <div>
                              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--app-subtle)]">
                                Destination jobs
                              </p>
                              {jobs.length === 0 ? (
                                <p className="rounded-lg border border-dashed border-[var(--app-border)] px-3 py-2 text-xs text-[var(--app-muted)]">
                                  No destination jobs yet. Jobs appear here after the workflow has an export ready to publish.
                                </p>
                              ) : (
                                <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
                                  {jobs.map((job) => {
                                    const brand = getPlatformBrandMeta(job.platform);
                                    return (
                                      <div key={job.id} className="rounded-lg border border-[var(--app-border)] p-2">
                                        <div className="flex items-center gap-2">
                                          <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${brand.badgeClassName}`}>
                                            {brand.icon}
                                          </span>
                                          <span className="min-w-0">
                                            <span className="block truncate text-xs font-semibold text-[var(--app-text)]">{brand.displayName}</span>
                                            <span className="block truncate text-[11px] text-[var(--app-muted)]">
                                              {job.destination_display_name || "Destination"}
                                            </span>
                                          </span>
                                        </div>
                                        <div className="mt-2 flex items-center justify-between gap-2">
                                          <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${statusBadgeClass(job.status)}`}>
                                            {publishJobLabel(job)}
                                          </span>
                                          {job.external_post_url ? (
                                            <a className="text-[11px] text-[var(--app-primary)] hover:underline" href={job.external_post_url} target="_blank" rel="noreferrer">
                                              Open
                                            </a>
                                          ) : null}
                                        </div>
                                        {job.error_message ? <p className="mt-1 line-clamp-2 text-[11px] text-red-600">{job.error_message}</p> : null}
                                      </div>
                                    );
                                  })}
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </Card>
            );
          })
        )}
      </div>
      <UploadModal
        isOpen={isUploadOpen}
        onClose={() => setIsUploadOpen(false)}
        onUploaded={async () => {
          setNotice("Original uploaded. Wait for processing to finish, then select it under Use uploaded original video.");
          await load();
        }}
      />
    </div>
  );
}
