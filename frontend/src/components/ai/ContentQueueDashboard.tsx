"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { ApiError, api } from "@/lib/api";
import { BrandProfile, ContentQueueItem, ContentQueueStatus } from "@/types";

const FILTERS: Array<{ label: string; value: "all" | ContentQueueStatus }> = [
  { label: "All", value: "all" },
  { label: "Ready", value: "ready" },
  { label: "Approved", value: "approved" },
  { label: "Posted", value: "posted" },
  { label: "Rejected", value: "rejected" },
];
const TEMPLATE_OPTIONS = [
  { id: "viral-dark", label: "Viral Dark" },
  { id: "navy-clean", label: "Navy Clean" },
];
const PLATFORM_OPTIONS = ["instagram", "threads", "linkedin", "tiktok", "youtube", "x"];

const STATUS_STYLES: Record<string, string> = {
  ready: "bg-teal-500/20 text-teal-700",
  approved: "bg-emerald-500/20 text-emerald-700",
  rejected: "bg-red-500/20 text-red-700",
  posted: "bg-blue-500/20 text-blue-700",
  draft: "bg-slate-500/20 text-slate-700",
  rendering: "bg-amber-500/20 text-amber-700",
};

function formatStatus(value: string): string {
  return value.split("_").map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
}

function formatAssetRetention(item: ContentQueueItem): string | null {
  if (item.assets_deleted_at) return "Media cleaned up";
  if (item.status === "approved" || item.status === "posted" || item.scheduled_at) return "Approved content retained";
  if (!item.asset_cleanup_at) return null;

  const cleanupAt = new Date(item.asset_cleanup_at).getTime();
  if (!Number.isFinite(cleanupAt)) return null;
  const daysLeft = Math.max(0, Math.ceil((cleanupAt - Date.now()) / (1000 * 60 * 60 * 24)));
  if (daysLeft <= 0) return "Draft media cleanup pending";
  return `Draft media expires in ${daysLeft} day${daysLeft === 1 ? "" : "s"}`;
}

export function ContentQueueDashboard() {
  const searchParams = useSearchParams();
  const saved = searchParams.get("saved") === "1";

  const [hasBrandProfile, setHasBrandProfile] = useState(true);
  const [loading, setLoading] = useState(true);
  const [queue, setQueue] = useState<ContentQueueItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [topic, setTopic] = useState("");
  const [templateId, setTemplateId] = useState("viral-dark");
  const [platforms, setPlatforms] = useState<string[]>([]);
  const [generating, setGenerating] = useState(false);
  const [activeFilter, setActiveFilter] = useState<"all" | ContentQueueStatus>("all");

  const load = async (status: "all" | ContentQueueStatus = activeFilter) => {
    setLoading(true);
    setError(null);
    try {
      const [brand, items] = await Promise.all([
        api.get<BrandProfile>("/api/brand-profile").catch((err) => {
          if (err instanceof ApiError && err.status === 404) return null;
          throw err;
        }),
        api.get<ContentQueueItem[]>(status === "all" ? "/api/content-queue" : `/api/content-queue?status=${status}`),
      ]);
      setHasBrandProfile(Boolean(brand));
      if (brand) {
        setPlatforms((current) => (current.length ? current : brand.preferred_platforms || []));
      }
      setQueue(items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load content queue.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load("all");
  }, []);

  useEffect(() => {
    void load(activeFilter);
  }, [activeFilter]);

  const togglePlatform = (platform: string) => {
    setPlatforms((current) => current.includes(platform) ? current.filter((item) => item !== platform) : [...current, platform]);
  };

  const onGenerate = async () => {
    if (!topic.trim()) return;
    setGenerating(true);
    setError(null);
    try {
      const created = await api.post<ContentQueueItem>("/api/content-queue/generate", { topic, template_id: templateId, platforms });
      setQueue((current) => [created, ...current]);
      setTopic("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to generate content.");
    } finally {
      setGenerating(false);
    }
  };

  const updateStatus = async (id: string, action: "approve" | "reject") => {
    try {
      const updated = await api.patch<ContentQueueItem>(`/api/content-queue/${id}/${action}`, {});
      setQueue((current) => current.map((item) => (item.id === id ? updated : item)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : `Failed to ${action} item.`);
    }
  };

  const deleteItem = async (id: string) => {
    try {
      await api.delete<void>(`/api/content-queue/${id}`);
      setQueue((current) => current.filter((item) => item.id !== id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to delete item.");
    }
  };

  const emptyQueueMessage = useMemo(() => {
    if (!hasBrandProfile) return null;
    if (queue.length === 0) return "No content yet. Generate your first carousel above.";
    return null;
  }, [hasBrandProfile, queue.length]);

  return (
    <div className="space-y-5">
      {saved ? <p className="text-sm text-emerald-700">Brand profile saved.</p> : null}
      {error ? <p className="text-sm text-red-700">{error}</p> : null}

      {!hasBrandProfile ? (
        <Card>
          <p className="text-sm text-[var(--app-text)]">Set up your brand profile to start generating content. <Link href="/brand-setup" className="text-[var(--app-primary)] hover:underline">Go to Brand Setup</Link></p>
        </Card>
      ) : null}

      <Card>
        <div className="space-y-4">
          <div>
            <h2 className="text-lg font-semibold text-[var(--app-text)]">Generate Now</h2>
            <p className="mt-1 text-sm text-[var(--app-subtle)]">Create a new draft carousel with Bandit LM.</p>
          </div>
          <Input label="Topic" placeholder="What do you want to post about?" value={topic} onChange={(event) => setTopic(event.target.value)} />
          <div>
            <label className="text-sm font-medium text-[var(--app-muted)]">Template</label>
            <select className="mt-1 w-full rounded-lg border border-[var(--app-border)] bg-white px-3 py-2.5 text-sm" value={templateId} onChange={(event) => setTemplateId(event.target.value)}>
              {TEMPLATE_OPTIONS.map((template) => <option key={template.id} value={template.id}>{template.label}</option>)}
            </select>
          </div>
          <div className="space-y-2">
            <p className="text-sm font-medium text-[var(--app-muted)]">Platforms</p>
            <div className="grid gap-2 md:grid-cols-3">
              {PLATFORM_OPTIONS.map((platform) => (
                <label key={platform} className="flex items-center gap-2 text-sm text-[var(--app-text)]">
                  <input type="checkbox" checked={platforms.includes(platform)} onChange={() => togglePlatform(platform)} />
                  {platform.charAt(0).toUpperCase() + platform.slice(1)}
                </label>
              ))}
            </div>
          </div>
          <Button onClick={onGenerate} loading={generating} disabled={!hasBrandProfile || !topic.trim()}>{generating ? "Bandit LM is writing your slides..." : "Generate with Bandit LM"}</Button>
        </div>
      </Card>

      <Card>
        <div className="flex flex-wrap items-center gap-2">
          {FILTERS.map((filter) => {
            const active = activeFilter === filter.value;
            return (
              <button key={filter.value} onClick={() => setActiveFilter(filter.value)} className={`rounded-full border px-3 py-1 text-xs ${active ? "border-[var(--app-primary)] bg-[rgba(29,63,208,0.1)] text-[var(--app-primary)]" : "border-[var(--app-border)] text-[var(--app-subtle)]"}`}>
                {filter.label}
              </button>
            );
          })}
        </div>
      </Card>

      {loading ? <p className="text-sm text-[var(--app-subtle)]">Loading queue...</p> : null}
      {emptyQueueMessage ? <p className="text-sm text-[var(--app-subtle)]">{emptyQueueMessage}</p> : null}

      <div className="space-y-4">
        {queue.map((item) => (
          <Card key={item.id}>
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${STATUS_STYLES[item.status] || STATUS_STYLES.draft}`}>{formatStatus(item.status)}</span>
                <span className="text-xs text-[var(--app-subtle)]">{new Date(item.created_at).toLocaleString()}</span>
              </div>
              {formatAssetRetention(item) ? <p className="text-xs text-[var(--app-subtle)]">{formatAssetRetention(item)}</p> : null}
              {item.generation_topic ? <p className="text-xs text-[var(--app-subtle)]">Topic: {item.generation_topic}</p> : null}
              <div className="flex gap-2 overflow-x-auto pb-1">
                {(item.slide_urls || []).map((url, index) => <img key={`${item.id}-${index}`} src={url} alt={`Slide ${index + 1}`} className="h-28 w-20 rounded-md border border-[var(--app-border)] object-cover" />)}
              </div>
              <div className="flex flex-wrap gap-2">
                <Link href={`/carousels/new?queueItem=${encodeURIComponent(item.id)}`} className="inline-flex items-center rounded-lg border border-[var(--app-border)] px-3 py-1.5 text-xs text-[var(--app-text)]">Edit</Link>
                <Button size="sm" onClick={() => updateStatus(item.id, "approve")}>Approve</Button>
                <Button size="sm" variant="secondary" onClick={() => updateStatus(item.id, "reject")}>Reject</Button>
                <Button size="sm" variant="danger" onClick={() => deleteItem(item.id)}>Delete</Button>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
