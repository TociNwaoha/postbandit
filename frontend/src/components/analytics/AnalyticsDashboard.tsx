"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card } from "@/components/ui/Card";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { getPlatformBrandMeta } from "@/components/connections/platformBrand";
import { api, ApiError } from "@/lib/api";
import {
  ConnectedAccount,
  PostAnalyticsSummary,
  PostAnalyticsTimeseriesPoint,
  PostAnalyticsTopPerformer,
  SocialPlatform,
} from "@/types";

const platforms: Array<SocialPlatform | "all"> = ["all", "instagram", "threads", "tiktok", "facebook", "youtube", "x", "linkedin"];
const rangeButtons = [
  { label: "7 days", days: 7 },
  { label: "30 days", days: 30 },
  { label: "90 days", days: 90 },
];

function dateDaysAgo(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString().slice(0, 10);
}

function toIsoEndOfDay(value: string): string {
  const date = new Date(`${value}T23:59:59.999`);
  return date.toISOString();
}

function toIsoStartOfDay(value: string): string {
  const date = new Date(`${value}T00:00:00.000`);
  return date.toISOString();
}

function compactNumber(value: number): string {
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(value || 0);
}

function formatDate(value: string | null): string {
  if (!value) return "Unknown";
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric" }).format(new Date(value));
}

function buildQuery(fromDate: string, toDate: string, platform?: string): string {
  const params = new URLSearchParams({ from_date: toIsoStartOfDay(fromDate), to_date: toIsoEndOfDay(toDate) });
  if (platform && platform !== "all") params.set("platform", platform);
  return params.toString();
}

export function AnalyticsDashboard() {
  const [fromDate, setFromDate] = useState(dateDaysAgo(30));
  const [toDate, setToDate] = useState(new Date().toISOString().slice(0, 10));
  const [platform, setPlatform] = useState<SocialPlatform | "all">("all");
  const [summary, setSummary] = useState<PostAnalyticsSummary | null>(null);
  const [timeseries, setTimeseries] = useState<PostAnalyticsTimeseriesPoint[]>([]);
  const [topPerformers, setTopPerformers] = useState<PostAnalyticsTopPerformer[]>([]);
  const [accounts, setAccounts] = useState<ConnectedAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const chartData = useMemo(() => {
    const rows = new Map<string, Record<string, string | number>>();
    for (const point of timeseries) {
      const row = rows.get(point.date) || { date: point.date };
      row[point.platform] = point.views;
      rows.set(point.date, row);
    }
    return Array.from(rows.values()).sort((a, b) => String(a.date).localeCompare(String(b.date)));
  }, [timeseries]);

  const chartPlatforms = useMemo(() => {
    const present = new Set(timeseries.map((point) => point.platform));
    return Array.from(present.values());
  }, [timeseries]);

  const expiredAccounts = useMemo(() => accounts.filter((account) => account.token_expired), [accounts]);

  const applyRange = (days: number) => {
    setFromDate(dateDaysAgo(days));
    setToDate(new Date().toISOString().slice(0, 10));
  };

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const query = buildQuery(fromDate, toDate, platform);
      const [summaryData, timeseriesData, topData, accountData] = await Promise.all([
        api.get<PostAnalyticsSummary>(`/api/analytics/summary?${query}`),
        api.get<PostAnalyticsTimeseriesPoint[]>(`/api/analytics/timeseries?${query}`),
        api.get<PostAnalyticsTopPerformer[]>(`/api/analytics/top-performers?${query}&metric=views&limit=10`),
        api.get<ConnectedAccount[]>("/api/social/accounts"),
      ]);
      setSummary(summaryData);
      setTimeseries(timeseriesData);
      setTopPerformers(topData);
      setAccounts(accountData);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load analytics");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [fromDate, toDate, platform]);

  const cards = [
    ["Views", summary?.total_views || 0],
    ["Likes", summary?.total_likes || 0],
    ["Comments", summary?.total_comments || 0],
    ["Shares", summary?.total_shares || 0],
  ];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="app-display text-2xl font-bold text-[var(--app-text)]">Post performance</h2>
          <p className="mt-1 text-sm text-[var(--app-muted)]">
            Latest metrics for published posts that PostBandit can match to provider post IDs.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <div className="flex rounded-lg border border-[var(--app-border)] bg-white p-1">
            {rangeButtons.map((item) => (
              <button
                key={item.days}
                type="button"
                onClick={() => applyRange(item.days)}
                className="rounded-md px-3 py-1.5 text-xs font-semibold text-[var(--app-muted)] transition hover:bg-[#F4F8FF] hover:text-[var(--app-text)]"
              >
                {item.label}
              </button>
            ))}
          </div>
          <label className="text-xs font-medium text-[var(--app-muted)]">
            From
            <input
              type="date"
              value={fromDate}
              onChange={(event) => setFromDate(event.target.value)}
              className="mt-1 block rounded-lg border border-[var(--app-border)] bg-white px-3 py-2 text-sm text-[var(--app-text)]"
            />
          </label>
          <label className="text-xs font-medium text-[var(--app-muted)]">
            To
            <input
              type="date"
              value={toDate}
              onChange={(event) => setToDate(event.target.value)}
              className="mt-1 block rounded-lg border border-[var(--app-border)] bg-white px-3 py-2 text-sm text-[var(--app-text)]"
            />
          </label>
          <label className="text-xs font-medium text-[var(--app-muted)]">
            Platform
            <select
              value={platform}
              onChange={(event) => setPlatform(event.target.value as SocialPlatform | "all")}
              className="mt-1 block rounded-lg border border-[var(--app-border)] bg-white px-3 py-2 text-sm text-[var(--app-text)]"
            >
              {platforms.map((item) => (
                <option key={item} value={item}>
                  {item === "all" ? "All platforms" : getPlatformBrandMeta(item).displayName}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {error ? <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div> : null}
      {expiredAccounts.length ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {expiredAccounts.length} account{expiredAccounts.length === 1 ? "" : "s"} need reconnection. Analytics refresh will resume after reconnecting on the Connections page.
        </div>
      ) : null}
      {loading ? (
        <div className="inline-flex items-center gap-2 text-sm text-[var(--app-muted)]">
          <LoadingSpinner size="sm" /> Loading analytics...
        </div>
      ) : null}

      <div className="grid gap-3 md:grid-cols-4">
        {cards.map(([label, value]) => (
          <Card key={String(label)} padding="sm">
            <p className="text-xs font-semibold uppercase tracking-wide text-[var(--app-muted)]">{label}</p>
            <p className="mt-2 text-3xl font-bold text-[var(--app-text)]">{compactNumber(Number(value))}</p>
          </Card>
        ))}
      </div>

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-lg font-semibold text-[var(--app-text)]">Views by publish date</h3>
            <p className="text-sm text-[var(--app-muted)]">Latest provider snapshots grouped by the date PostBandit marked the post published.</p>
          </div>
          {summary?.top_platform ? (
            <span className="rounded-full bg-[#EEF3FF] px-3 py-1 text-xs font-semibold text-[var(--app-primary)]">
              Top: {getPlatformBrandMeta(summary.top_platform).displayName}
            </span>
          ) : null}
        </div>
        <div className="mt-4 h-72">
          {chartData.length ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 8, right: 24, bottom: 8, left: 0 }}>
                <CartesianGrid stroke="#E1E8F5" strokeDasharray="3 3" />
                <XAxis dataKey="date" tickFormatter={formatDate} stroke="#7B8BA5" fontSize={12} />
                <YAxis stroke="#7B8BA5" fontSize={12} tickFormatter={compactNumber} />
                <Tooltip labelFormatter={(value) => formatDate(String(value))} formatter={(value, name) => [compactNumber(Number(value)), getPlatformBrandMeta(String(name)).displayName]} />
                {chartPlatforms.map((item) => (
                  <Line
                    key={item}
                    type="monotone"
                    dataKey={item}
                    stroke={getPlatformBrandMeta(item).analyticsColor}
                    strokeWidth={2}
                    dot={false}
                    connectNulls
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full items-center justify-center rounded-xl bg-[#F7FAFF] text-sm text-[var(--app-muted)]">
              No analytics snapshots for this range yet.
            </div>
          )}
        </div>
      </Card>

      <Card>
        <h3 className="text-lg font-semibold text-[var(--app-text)]">Top performers</h3>
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-[var(--app-muted)]">
              <tr>
                <th className="py-2 pr-4">Post</th>
                <th className="py-2 pr-4">Platform</th>
                <th className="py-2 pr-4">Views</th>
                <th className="py-2 pr-4">Engagement</th>
                <th className="py-2 pr-4">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--app-border)]">
              {topPerformers.map((item) => (
                <tr key={item.publish_job_id}>
                  <td className="py-3 pr-4">
                    <div className="flex min-w-[260px] items-center gap-3">
                      {item.thumbnail_url ? <img src={item.thumbnail_url} alt="" className="h-10 w-16 rounded-md object-cover" /> : null}
                      <div>
                        <p className="line-clamp-1 font-medium text-[var(--app-text)]">{item.title}</p>
                        <p className="text-xs text-[var(--app-muted)]">{formatDate(item.published_at)}</p>
                      </div>
                    </div>
                  </td>
                  <td className="py-3 pr-4">{getPlatformBrandMeta(item.platform).displayName}</td>
                  <td className="py-3 pr-4 font-semibold">{compactNumber(item.views)}</td>
                  <td className="py-3 pr-4 text-[var(--app-muted)]">
                    {compactNumber(item.likes + item.comments + item.shares)} total
                  </td>
                  <td className="py-3 pr-4">
                    {item.fetch_error ? (
                      <span className="rounded-full bg-amber-50 px-2 py-1 text-xs font-semibold text-amber-800">{item.fetch_error}</span>
                    ) : item.external_post_url ? (
                      <a href={item.external_post_url} target="_blank" rel="noreferrer" className="text-xs font-semibold text-[var(--app-primary)] hover:underline">
                        Open post
                      </a>
                    ) : (
                      <span className="text-xs text-[var(--app-muted)]">Ready</span>
                    )}
                  </td>
                </tr>
              ))}
              {!topPerformers.length ? (
                <tr>
                  <td colSpan={5} className="py-8 text-center text-sm text-[var(--app-muted)]">
                    No top performers yet. Published posts will appear after the analytics worker fetches provider metrics.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
