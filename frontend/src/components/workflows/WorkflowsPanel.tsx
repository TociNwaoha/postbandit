"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { getSocialPlatformMeta } from "@/lib/socialPlatformMeta";
import {
  ConnectedAccount,
  Export,
  SocialPlatform,
  SocialWorkflow,
  WorkflowCopyMode,
  WorkflowRunList,
  WorkflowSourceCapability,
} from "@/types";

const runTone: Record<string, string> = {
  waiting_asset: "bg-amber-100 text-amber-800",
  processing: "bg-blue-100 text-blue-700",
  queued: "bg-blue-100 text-blue-700",
  completed: "bg-emerald-100 text-emerald-700",
  partial_failed: "bg-amber-100 text-amber-800",
  failed: "bg-red-100 text-red-700",
  skipped: "bg-slate-100 text-slate-600",
};

function accountName(account: ConnectedAccount) {
  return account.display_name || account.username_or_channel_name || account.external_account_id;
}

function defaultPrivacy(platform: SocialPlatform) {
  if (platform === "youtube") return "private";
  if (platform === "tiktok") return "SELF_ONLY";
  return null;
}

export function WorkflowsPanel() {
  const [accounts, setAccounts] = useState<ConnectedAccount[]>([]);
  const [capabilities, setCapabilities] = useState<WorkflowSourceCapability[]>([]);
  const [workflows, setWorkflows] = useState<SocialWorkflow[]>([]);
  const [exports, setExports] = useState<Export[]>([]);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string | null>(null);
  const [runs, setRuns] = useState<WorkflowRunList>({ items: [], total: 0 });
  const [name, setName] = useState("Cross-post new videos");
  const [sourceAccountId, setSourceAccountId] = useState("");
  const [destinationIds, setDestinationIds] = useState<string[]>([]);
  const [copyMode, setCopyMode] = useState<WorkflowCopyMode>("ai_platform");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attachExport, setAttachExport] = useState<Record<string, string>>({});

  const capabilityByAccount = useMemo(
    () => new Map(capabilities.map((item) => [item.connected_account_id, item])),
    [capabilities]
  );

  const loadBase = async () => {
    setLoading(true);
    setError(null);
    try {
      const [accountRows, capabilityRows, workflowRows, exportRows] = await Promise.all([
        api.get<ConnectedAccount[]>("/api/social/accounts"),
        api.get<WorkflowSourceCapability[]>("/api/social/workflows/capabilities"),
        api.get<SocialWorkflow[]>("/api/social/workflows"),
        api.get<Export[]>("/api/exports"),
      ]);
      setAccounts(accountRows);
      setCapabilities(capabilityRows);
      setWorkflows(workflowRows);
      setExports(exportRows.filter((item) => item.status === "ready" && item.storage_key));
      if (!sourceAccountId && accountRows.length) setSourceAccountId(accountRows[0].id);
      if (!selectedWorkflowId && workflowRows.length) setSelectedWorkflowId(workflowRows[0].id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load workflows");
    } finally {
      setLoading(false);
    }
  };

  const loadRuns = async (workflowId: string) => {
    try {
      setRuns(await api.get<WorkflowRunList>(`/api/social/workflows/${workflowId}/runs`));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load workflow history");
    }
  };

  useEffect(() => {
    void loadBase();
  }, []);

  useEffect(() => {
    if (selectedWorkflowId) void loadRuns(selectedWorkflowId);
    else setRuns({ items: [], total: 0 });
  }, [selectedWorkflowId]);

  const createWorkflow = async () => {
    if (!sourceAccountId || !destinationIds.length) {
      setError("Choose one source and at least one destination.");
      return;
    }
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const destinations = destinationIds.map((id) => {
        const account = accounts.find((item) => item.id === id)!;
        return {
          connected_account_id: account.id,
          platform: account.platform,
          privacy: defaultPrivacy(account.platform),
        };
      });
      const created = await api.post<SocialWorkflow>("/api/social/workflows", {
        name,
        source_account_id: sourceAccountId,
        copy_mode: copyMode,
        destinations,
        enabled: true,
      });
      setWorkflows((current) => [created, ...current]);
      setSelectedWorkflowId(created.id);
      setDestinationIds([]);
      setMessage("Workflow created. Existing posts are baselined; only new posts trigger it.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create workflow");
    } finally {
      setSaving(false);
    }
  };

  const toggleWorkflow = async (workflow: SocialWorkflow) => {
    const updated = await api.patch<SocialWorkflow>(`/api/social/workflows/${workflow.id}`, {
      enabled: !workflow.enabled,
    });
    setWorkflows((current) => current.map((item) => (item.id === updated.id ? updated : item)));
  };

  const deleteWorkflow = async (workflow: SocialWorkflow) => {
    if (!window.confirm(`Delete "${workflow.name}" and its run history?`)) return;
    await api.delete(`/api/social/workflows/${workflow.id}`);
    setWorkflows((current) => current.filter((item) => item.id !== workflow.id));
    if (selectedWorkflowId === workflow.id) setSelectedWorkflowId(null);
  };

  const pollNow = async (workflow: SocialWorkflow) => {
    await api.post(`/api/social/workflows/${workflow.id}/poll-now`, {});
    setMessage("Source check queued. Refresh history in a few seconds.");
  };

  const attachReadyExport = async (runId: string) => {
    const exportId = attachExport[runId];
    if (!exportId) return;
    await api.post(`/api/social/workflows/runs/${runId}/attach-export`, { export_id: exportId });
    setMessage("Original export attached. Automatic destination publishing is queued.");
    if (selectedWorkflowId) window.setTimeout(() => void loadRuns(selectedWorkflowId), 1500);
  };

  if (loading) return <p className="text-sm text-[var(--app-muted)]">Loading workflows...</p>;

  return (
    <div className="space-y-5">
      {error && <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
      {message && (
        <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700">{message}</div>
      )}

      <section className="rounded-2xl border border-[var(--app-border)] bg-white p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="app-display text-xl font-bold text-[var(--app-text)]">Automatic cross-post workflow</h2>
            <p className="mt-1 max-w-3xl text-sm text-[var(--app-muted)]">
              When a new video appears on the source account, PostBandit reuses the exact stored export and publishes it
              to your selected destinations. Direct external posts require the original file.
            </p>
          </div>
          <Link href="/connections" className="text-sm font-semibold text-[var(--app-primary)]">
            Manage connections
          </Link>
        </div>

        {!accounts.length ? (
          <p className="mt-5 rounded-xl bg-[#F4F8FF] p-4 text-sm text-[var(--app-muted)]">
            Connect at least two social accounts before creating a workflow.
          </p>
        ) : (
          <div className="mt-5 grid gap-4 lg:grid-cols-[1fr_1fr]">
            <div className="space-y-3">
              <label className="block text-xs font-semibold uppercase tracking-wide text-[var(--app-subtle)]">
                Workflow name
              </label>
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                className="w-full rounded-xl border border-[var(--app-border)] px-3 py-2.5 text-sm"
              />
              <label className="block text-xs font-semibold uppercase tracking-wide text-[var(--app-subtle)]">
                Source account
              </label>
              <select
                value={sourceAccountId}
                onChange={(event) => {
                  setSourceAccountId(event.target.value);
                  setDestinationIds((current) => current.filter((id) => id !== event.target.value));
                }}
                className="w-full rounded-xl border border-[var(--app-border)] px-3 py-2.5 text-sm"
              >
                {accounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {getSocialPlatformMeta(account.platform).displayName} - {accountName(account)}
                  </option>
                ))}
              </select>
              {sourceAccountId && capabilityByAccount.get(sourceAccountId)?.status !== "ready" && (
                <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
                  {capabilityByAccount.get(sourceAccountId)?.message} Posts published through PostBandit still trigger
                  automatically.
                </p>
              )}
              <label className="block text-xs font-semibold uppercase tracking-wide text-[var(--app-subtle)]">
                Copy mode
              </label>
              <div className="grid grid-cols-2 gap-2">
                {[
                  ["ai_platform", "AI platform copy"],
                  ["reuse_source", "Reuse source copy"],
                ].map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setCopyMode(value as WorkflowCopyMode)}
                    className={`rounded-xl border px-3 py-2.5 text-sm font-semibold ${
                      copyMode === value
                        ? "border-[var(--app-primary)] bg-blue-50 text-[var(--app-primary)]"
                        : "border-[var(--app-border)] text-[var(--app-muted)]"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-[var(--app-subtle)]">Destinations</p>
              <div className="mt-3 space-y-2">
                {accounts
                  .filter((account) => account.id !== sourceAccountId)
                  .map((account) => {
                    const checked = destinationIds.includes(account.id);
                    const meta = getSocialPlatformMeta(account.platform);
                    return (
                      <label
                        key={account.id}
                        className={`flex cursor-pointer items-center gap-3 rounded-xl border px-3 py-2.5 ${
                          checked ? "border-[var(--app-primary)] bg-blue-50" : "border-[var(--app-border)]"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() =>
                            setDestinationIds((current) =>
                              checked ? current.filter((id) => id !== account.id) : [...current, account.id]
                            )
                          }
                        />
                        <span
                          className={`flex h-8 w-8 items-center justify-center rounded-lg ${meta.chipClassName}`}
                        >
                          {meta.icon}
                        </span>
                        <span className="min-w-0">
                          <span className="block text-sm font-semibold text-[var(--app-text)]">{accountName(account)}</span>
                          <span className="block text-xs text-[var(--app-muted)]">{meta.displayName}</span>
                        </span>
                      </label>
                    );
                  })}
              </div>
              <button
                type="button"
                disabled={saving || !destinationIds.length}
                onClick={() => void createWorkflow()}
                className="mt-4 w-full rounded-xl bg-[var(--app-primary)] px-4 py-3 text-sm font-bold text-white disabled:opacity-50"
              >
                {saving ? "Creating..." : "Create automatic workflow"}
              </button>
            </div>
          </div>
        )}
      </section>

      <div className="grid gap-5 xl:grid-cols-[360px_1fr]">
        <section className="rounded-2xl border border-[var(--app-border)] bg-white p-4">
          <h3 className="app-display text-lg font-bold text-[var(--app-text)]">Your workflows</h3>
          <div className="mt-3 space-y-2">
            {workflows.map((workflow) => (
              <button
                type="button"
                key={workflow.id}
                onClick={() => setSelectedWorkflowId(workflow.id)}
                className={`w-full rounded-xl border p-3 text-left ${
                  selectedWorkflowId === workflow.id
                    ? "border-[var(--app-primary)] bg-blue-50"
                    : "border-[var(--app-border)]"
                }`}
              >
                <span className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-[var(--app-text)]">{workflow.name}</span>
                  <span className={`text-xs font-semibold ${workflow.enabled ? "text-emerald-700" : "text-slate-500"}`}>
                    {workflow.enabled ? "Active" : "Paused"}
                  </span>
                </span>
                <span className="mt-1 block text-xs text-[var(--app-muted)]">
                  {getSocialPlatformMeta(workflow.source_platform).displayName} to{" "}
                  {workflow.destination_configs.length} destination(s)
                </span>
              </button>
            ))}
            {!workflows.length && <p className="py-5 text-sm text-[var(--app-muted)]">No workflows yet.</p>}
          </div>
        </section>

        <section className="rounded-2xl border border-[var(--app-border)] bg-white p-4">
          {selectedWorkflowId ? (
            <>
              {workflows
                .filter((workflow) => workflow.id === selectedWorkflowId)
                .map((workflow) => (
                  <div key={workflow.id}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <h3 className="app-display text-lg font-bold text-[var(--app-text)]">{workflow.name}</h3>
                        <p className="text-xs text-[var(--app-muted)]">
                          {workflow.copy_mode === "ai_platform" ? "AI platform copy" : "Reuse source copy"}
                          {workflow.last_checked_at
                            ? ` · Checked ${new Date(workflow.last_checked_at).toLocaleString()}`
                            : " · Not checked yet"}
                        </p>
                      </div>
                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={() => void pollNow(workflow)}
                          className="rounded-lg border border-[var(--app-border)] px-3 py-2 text-xs font-semibold"
                        >
                          Check now
                        </button>
                        <button
                          type="button"
                          onClick={() => void toggleWorkflow(workflow)}
                          className="rounded-lg border border-[var(--app-border)] px-3 py-2 text-xs font-semibold"
                        >
                          {workflow.enabled ? "Pause" : "Resume"}
                        </button>
                        <button
                          type="button"
                          onClick={() => void deleteWorkflow(workflow)}
                          className="rounded-lg border border-red-200 px-3 py-2 text-xs font-semibold text-red-700"
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                    {workflow.last_error && (
                      <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">{workflow.last_error}</p>
                    )}
                  </div>
                ))}

              <div className="mt-4 space-y-3">
                {runs.items.map((run) => (
                  <article key={run.id} className="rounded-xl border border-[var(--app-border)] p-3">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <p className="font-semibold text-[var(--app-text)]">{run.source_title || "New source post"}</p>
                        <p className="mt-0.5 text-xs text-[var(--app-muted)]">
                          {getSocialPlatformMeta(run.source_platform).displayName}
                          {run.source_published_at ? ` · ${new Date(run.source_published_at).toLocaleString()}` : ""}
                        </p>
                      </div>
                      <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${runTone[run.status]}`}>
                        {run.status.replaceAll("_", " ")}
                      </span>
                    </div>
                    {run.error_message && <p className="mt-2 text-xs text-amber-800">{run.error_message}</p>}
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      {run.source_external_url && (
                        <a
                          href={run.source_external_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-xs font-semibold text-[var(--app-primary)]"
                        >
                          Open source post
                        </a>
                      )}
                      {run.status === "waiting_asset" && (
                        <>
                          <select
                            value={attachExport[run.id] || ""}
                            onChange={(event) =>
                              setAttachExport((current) => ({ ...current, [run.id]: event.target.value }))
                            }
                            className="min-w-[220px] rounded-lg border border-[var(--app-border)] px-2 py-1.5 text-xs"
                          >
                            <option value="">Choose original ready export</option>
                            {exports.map((item) => (
                              <option key={item.id} value={item.id}>
                                {item.clip_title || item.video_title || item.id.slice(0, 8)} · {item.aspect_ratio}
                              </option>
                            ))}
                          </select>
                          <button
                            type="button"
                            disabled={!attachExport[run.id]}
                            onClick={() => void attachReadyExport(run.id)}
                            className="rounded-lg bg-[var(--app-primary)] px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                          >
                            Attach and publish
                          </button>
                        </>
                      )}
                    </div>
                  </article>
                ))}
                {!runs.items.length && <p className="py-8 text-center text-sm text-[var(--app-muted)]">No new posts detected.</p>}
              </div>
            </>
          ) : (
            <p className="py-10 text-center text-sm text-[var(--app-muted)]">Select a workflow to view activity.</p>
          )}
        </section>
      </div>
    </div>
  );
}
