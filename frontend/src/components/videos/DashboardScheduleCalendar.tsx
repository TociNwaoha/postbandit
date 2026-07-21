"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Card } from "@/components/ui/Card";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { api, ApiError } from "@/lib/api";
import { getSocialPlatformMeta } from "@/lib/socialPlatformMeta";
import {
  Export,
  PublishCalendarItem,
  PublishCalendarResponse,
  PublishJobStatus,
  SocialPlatform,
} from "@/types";

type CalendarView = "month" | "week";
type SchedulePostKind = "video" | null;

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const PLATFORMS: Array<SocialPlatform | "all"> = [
  "all",
  "instagram",
  "threads",
  "facebook",
  "youtube",
  "x",
  "tiktok",
  "linkedin",
];
const STATUSES: Array<PublishJobStatus | "all"> = [
  "all",
  "scheduled",
  "queued",
  "publishing",
  "published",
  "failed",
  "waiting_user_action",
  "provider_not_configured",
  "cancelled",
];
const STATUS_STYLES: Record<PublishJobStatus, string> = {
  scheduled: "bg-indigo-100 text-indigo-700",
  queued: "bg-slate-100 text-slate-700",
  publishing: "bg-blue-100 text-blue-700",
  published: "bg-emerald-100 text-emerald-700",
  failed: "bg-red-100 text-red-700",
  waiting_user_action: "bg-amber-100 text-amber-800",
  provider_not_configured: "bg-yellow-100 text-yellow-800",
  cancelled: "bg-slate-200 text-slate-600",
};

function safeCalendarErrorMessage(item: PublishCalendarItem): string | null {
  if (!item.error_message) return null;
  const normalized = item.error_message.toLowerCase();
  if (
    normalized.includes("client error") ||
    normalized.includes("bad request") ||
    normalized.includes("unauthorized") ||
    normalized.includes("invalid token") ||
    normalized.includes("access token") ||
    normalized.includes("oauth") ||
    normalized.includes("googleapis.com") ||
    normalized.includes("graph.facebook.com") ||
    normalized.includes("graph.instagram.com") ||
    normalized.includes("api.twitter.com") ||
    normalized.includes("api.x.com") ||
    normalized.includes("open.tiktokapis.com") ||
    normalized.includes("api.linkedin.com") ||
    normalized.includes("developer.mozilla.org")
  ) {
    return `Reconnect ${getSocialPlatformMeta(item.platform).displayName} in Connections, then retry this post.`;
  }
  return item.error_message;
}

function pad2(value: number): string {
  return String(value).padStart(2, "0");
}

function dayKey(date: Date): string {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

function monthStart(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function monthEnd(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth() + 1, 1);
}

function weekStart(date: Date): Date {
  const result = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  result.setDate(result.getDate() - ((result.getDay() + 6) % 7));
  result.setHours(0, 0, 0, 0);
  return result;
}

function addDays(date: Date, days: number): Date {
  const result = new Date(date);
  result.setDate(result.getDate() + days);
  return result;
}

function getTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

function eventTitle(item: PublishCalendarItem): string {
  return (
    item.content_title_snapshot ||
    item.title ||
    item.caption?.replace(/\s+/g, " ").trim().slice(0, 72) ||
    "Scheduled post"
  );
}

function prettyStatus(value: PublishJobStatus): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function localInputValue(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return `${dayKey(date)}T${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
}

function defaultTime(date: Date): string {
  const now = new Date();
  if (dayKey(date) !== dayKey(now)) return "09:00";
  const next = new Date(now.getTime() + 15 * 60 * 1000);
  next.setSeconds(0, 0);
  const remainder = next.getMinutes() % 5;
  if (remainder) next.setMinutes(next.getMinutes() + 5 - remainder);
  return `${pad2(next.getHours())}:${pad2(next.getMinutes())}`;
}

export function DashboardScheduleCalendar() {
  const [view, setView] = useState<CalendarView>("month");
  const [anchorDate, setAnchorDate] = useState(() => new Date());
  const [platformFilter, setPlatformFilter] = useState<SocialPlatform | "all">("all");
  const [statusFilter, setStatusFilter] = useState<PublishJobStatus | "all">("all");
  const [items, setItems] = useState<PublishCalendarItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<PublishCalendarItem | null>(null);
  const [selectedDay, setSelectedDay] = useState<Date | null>(null);
  const [selectedPostKind, setSelectedPostKind] = useState<SchedulePostKind>(null);
  const [scheduleTime, setScheduleTime] = useState("09:00");
  const [readyExports, setReadyExports] = useState<Export[]>([]);
  const [saving, setSaving] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);
  const timezone = getTimeZone();

  const range = useMemo(() => {
    if (view === "week") {
      const start = weekStart(anchorDate);
      return { start, end: addDays(start, 7) };
    }
    return { start: monthStart(anchorDate), end: monthEnd(anchorDate) };
  }, [anchorDate, view]);

  const loadCalendar = useCallback(async () => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({
      scheduled_from: range.start.toISOString(),
      scheduled_to: range.end.toISOString(),
      page_size: "250",
    });
    if (platformFilter !== "all") params.set("platform", platformFilter);
    if (statusFilter !== "all") params.set("status", statusFilter);
    try {
      const response = await api.get<PublishCalendarResponse>(
        `/api/social/publish/calendar?${params.toString()}`
      );
      setItems(response.items);
      setSelectedEvent((current) =>
        current ? response.items.find((item) => item.id === current.id) || current : null
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load publishing calendar");
    } finally {
      setLoading(false);
    }
  }, [platformFilter, range.end, range.start, statusFilter]);

  useEffect(() => {
    void loadCalendar();
  }, [loadCalendar, refreshToken]);

  useEffect(() => {
    const loadExports = async () => {
      try {
        const exports = await api.get<Export[]>("/api/exports");
        setReadyExports(
          exports.filter(
            (item) => item.status === "ready" && item.storage_key && item.video_id && item.clip_id
          )
        );
      } catch {
        setReadyExports([]);
      }
    };
    void loadExports();
  }, []);

  const cells = useMemo(() => {
    if (view === "week") {
      return Array.from({ length: 7 }, (_, index) => addDays(range.start, index));
    }
    const start = weekStart(range.start);
    return Array.from({ length: 42 }, (_, index) => addDays(start, index));
  }, [range.start, view]);

  const itemsByDay = useMemo(() => {
    const map = new Map<string, PublishCalendarItem[]>();
    for (const item of items) {
      if (!item.scheduled_for) continue;
      const date = new Date(item.scheduled_for);
      if (Number.isNaN(date.getTime())) continue;
      const key = dayKey(date);
      map.set(key, [...(map.get(key) || []), item]);
    }
    return map;
  }, [items]);

  const uniqueReadyExports = useMemo(() => {
    const clipIds = new Set<string>();
    return readyExports
      .filter((item) => {
        if (clipIds.has(item.clip_id)) return false;
        clipIds.add(item.clip_id);
        return true;
      })
      .slice(0, 6);
  }, [readyExports]);

  const navigate = (direction: -1 | 1) => {
    setAnchorDate((current) => {
      if (view === "week") return addDays(current, direction * 7);
      return new Date(current.getFullYear(), current.getMonth() + direction, 1);
    });
  };

  const openDay = (date: Date) => {
    setSelectedDay(new Date(date.getFullYear(), date.getMonth(), date.getDate()));
    setSelectedPostKind(null);
    setScheduleTime(defaultTime(date));
  };

  const updateSelectedEvent = async (
    body: Record<string, unknown>,
    successMessage?: string
  ) => {
    if (!selectedEvent) return;
    setSaving(true);
    setError(null);
    try {
      await api.patch(`/api/social/publish/${selectedEvent.id}`, body);
      setSelectedEvent(null);
      setRefreshToken((value) => value + 1);
      if (successMessage) setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to update publish job");
    } finally {
      setSaving(false);
    }
  };

  const retrySelectedEvent = async () => {
    if (!selectedEvent) return;
    setSaving(true);
    setError(null);
    try {
      await api.post(`/api/social/publish/${selectedEvent.id}/retry`, {});
      setSelectedEvent(null);
      setRefreshToken((value) => value + 1);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to retry publish job");
    } finally {
      setSaving(false);
    }
  };

  const titleLabel =
    view === "month"
      ? anchorDate.toLocaleDateString(undefined, { month: "long", year: "numeric" })
      : `${range.start.toLocaleDateString(undefined, { month: "short", day: "numeric" })} - ${addDays(
          range.end,
          -1
        ).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}`;
  const todayKey = dayKey(new Date());
  const selectedScheduleValue = selectedDay
    ? `${dayKey(selectedDay)}T${scheduleTime}`
    : "";
  const selectedDayLabel = selectedDay
    ? selectedDay.toLocaleDateString(undefined, {
        weekday: "long",
        month: "long",
        day: "numeric",
        year: "numeric",
      })
    : "";
  const selectedDayIsPast = selectedDay
    ? selectedDay < new Date(new Date().setHours(0, 0, 0, 0))
    : false;
  const encodedSchedule = encodeURIComponent(selectedScheduleValue);

  return (
    <Card className="mb-6" padding="sm">
      <div className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-[var(--app-text)]">Publishing Calendar</h3>
            <p className="mt-1 text-xs text-[var(--app-muted)]">
              Scheduled posts and publishing history. Click a day to create; click an event to manage it.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <select
              value={platformFilter}
              onChange={(event) => setPlatformFilter(event.target.value as SocialPlatform | "all")}
              className="rounded-md border border-[var(--app-border)] bg-white px-2 py-1 text-xs"
            >
              {PLATFORMS.map((platform) => (
                <option key={platform} value={platform}>
                  {platform === "all" ? "All platforms" : getSocialPlatformMeta(platform).displayName}
                </option>
              ))}
            </select>
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as PublishJobStatus | "all")}
              className="rounded-md border border-[var(--app-border)] bg-white px-2 py-1 text-xs"
            >
              {STATUSES.map((status) => (
                <option key={status} value={status}>
                  {status === "all" ? "All statuses" : prettyStatus(status)}
                </option>
              ))}
            </select>
            <div className="inline-flex rounded-md border border-[var(--app-border)] p-0.5">
              {(["month", "week"] as CalendarView[]).map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => setView(option)}
                  className={`rounded px-2 py-1 text-xs capitalize ${
                    view === option ? "bg-[var(--app-primary)] text-white" : "text-[var(--app-muted)]"
                  }`}
                >
                  {option}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-1.5">
            <button type="button" onClick={() => navigate(-1)} className="rounded border px-2 py-1 text-xs">
              Prev
            </button>
            <button
              type="button"
              onClick={() => setAnchorDate(new Date())}
              className="rounded border px-2 py-1 text-xs"
            >
              Today
            </button>
            <button type="button" onClick={() => navigate(1)} className="rounded border px-2 py-1 text-xs">
              Next
            </button>
          </div>
          <p className="app-display text-lg font-semibold text-[var(--app-text)]">{titleLabel}</p>
          <p className="text-[11px] text-[var(--app-subtle)]">{timezone}</p>
        </div>

        {error ? <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">{error}</p> : null}

        <div className="overflow-hidden rounded-lg border border-[var(--app-border)] bg-white">
          <div className="grid grid-cols-7 border-b bg-[var(--app-surface-soft)]">
            {WEEKDAYS.map((label) => (
              <div key={label} className="px-2 py-1.5 text-center text-[11px] font-semibold text-[var(--app-muted)]">
                {label}
              </div>
            ))}
          </div>
          <div className="grid grid-cols-7">
            {cells.map((date) => {
              const key = dayKey(date);
              const dayItems = itemsByDay.get(key) || [];
              const outside = view === "month" && date.getMonth() !== anchorDate.getMonth();
              return (
                <div
                  key={key}
                  role="button"
                  tabIndex={0}
                  onClick={() => openDay(date)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") openDay(date);
                  }}
                  className={`min-h-[96px] cursor-pointer border-b border-r p-1.5 hover:bg-[#F4F8FF] ${
                    outside ? "bg-[#FAFBFF]" : "bg-white"
                  }`}
                >
                  <span
                    className={`inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1 text-[11px] ${
                      key === todayKey
                        ? "bg-[var(--app-primary)] text-white"
                        : outside
                          ? "text-[var(--app-subtle)]"
                          : "text-[var(--app-text)]"
                    }`}
                  >
                    {date.getDate()}
                  </span>
                  <div className="mt-1 space-y-1">
                    {dayItems.slice(0, view === "week" ? 8 : 4).map((item) => {
                      const meta = getSocialPlatformMeta(item.platform);
                      const time = new Date(item.scheduled_for as string).toLocaleTimeString([], {
                        hour: "numeric",
                        minute: "2-digit",
                      });
                      return (
                        <button
                          key={item.id}
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            setSelectedEvent(item);
                          }}
                          className="flex w-full items-center gap-1 overflow-hidden rounded border border-[var(--app-border)] bg-white px-1 py-0.5 text-left shadow-sm"
                          title={`${eventTitle(item)} - ${prettyStatus(item.status)}`}
                        >
                          <span className={`inline-flex h-5 w-5 shrink-0 items-center justify-center rounded ${meta.chipClassName}`}>
                            {meta.icon}
                          </span>
                          <span className="min-w-0 flex-1 truncate text-[10px] text-[var(--app-text)]">
                            {time} {view === "week" ? eventTitle(item) : ""}
                          </span>
                          <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${STATUS_STYLES[item.status].split(" ")[0]}`} />
                        </button>
                      );
                    })}
                    {dayItems.length > (view === "week" ? 8 : 4) ? (
                      <span className="text-[10px] text-[var(--app-muted)]">
                        +{dayItems.length - (view === "week" ? 8 : 4)} more
                      </span>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {loading ? (
          <p className="inline-flex items-center gap-2 text-xs text-[var(--app-muted)]">
            <LoadingSpinner size="sm" /> Loading publishing history...
          </p>
        ) : !items.length ? (
          <p className="text-xs text-[var(--app-muted)]">No publish jobs match this range and filter.</p>
        ) : null}

        {selectedDay ? (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-[#091528]/35 p-4"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) setSelectedDay(null);
            }}
          >
            <div className="w-full max-w-[430px] rounded-2xl bg-white p-5 shadow-2xl sm:p-6">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h4 className="app-display text-3xl font-extrabold tracking-[-0.04em] text-[#091528]">
                    Schedule Post
                  </h4>
                  <p className="mt-2 text-base text-[#4A5568]">{selectedDayLabel}</p>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedDay(null)}
                  className="rounded-full p-1.5 text-[#7A8495] transition hover:bg-[#F4F8FF] hover:text-[#091528]"
                  aria-label="Close schedule modal"
                >
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path d="M6 6L18 18M18 6L6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  </svg>
                </button>
              </div>

              <label className="mt-4 block text-xs font-semibold text-[#4A5568]">
                Planned time
                <input
                  type="time"
                  step={300}
                  value={scheduleTime}
                  onChange={(event) => setScheduleTime(event.target.value)}
                  className="mt-1.5 w-full rounded-lg border border-[#E1E5EC] px-3 py-2 text-sm text-[#091528] outline-none focus:border-[var(--app-primary)] focus:ring-2 focus:ring-[rgba(29,63,208,0.12)]"
                />
              </label>

              {selectedDayIsPast ? (
                <p className="mt-4 rounded-lg bg-amber-50 p-2.5 text-xs text-amber-800">
                  Historical days are view-only. Choose today or a future day to schedule content.
                </p>
              ) : (
                <>
                  <div className="mt-5 space-y-2.5">
                    <ScheduleOptionLink
                      href={`/content-queue?scheduledFor=${encodedSchedule}&type=text`}
                      label="Text Post"
                      icon="text"
                    />
                    <ScheduleOptionLink
                      href={`/carousels/new?scheduledFor=${encodedSchedule}`}
                      label="Image Post"
                      icon="image"
                    />
                    <ScheduleOptionButton
                      label="Video Post"
                      icon="video"
                      active={selectedPostKind === "video"}
                      onClick={() => setSelectedPostKind((current) => (current === "video" ? null : "video"))}
                    />
                    <ScheduleOptionLink
                      href={`/carousels/new?scheduledFor=${encodedSchedule}&format=story`}
                      label="Story"
                      icon="story"
                    />
                  </div>

                  {selectedPostKind === "video" ? (
                    <div className="mt-3 rounded-xl border border-[#E1E5EC] bg-[#F8FAFF] p-2.5">
                      <p className="px-1 text-xs font-semibold text-[#091528]">Schedule a ready video clip</p>
                      <div className="mt-2 max-h-48 space-y-1.5 overflow-y-auto pr-1">
                        {uniqueReadyExports.length ? (
                          uniqueReadyExports.map((item) => (
                            <Link
                              key={item.id}
                              href={`/videos/${item.video_id}/clips/${item.clip_id}?scheduleAt=${encodedSchedule}#publish-social`}
                              className="flex items-center gap-2 rounded-lg border border-[#E1E5EC] bg-white p-1.5 transition hover:border-[var(--app-primary)]"
                            >
                              {item.clip_thumbnail_url ? (
                                <img src={item.clip_thumbnail_url} alt="" className="h-10 w-16 rounded-md object-cover" />
                              ) : (
                                <span className="h-10 w-16 rounded-md bg-[var(--app-surface-soft)]" />
                              )}
                              <span className="min-w-0">
                                <span className="block truncate text-xs font-semibold text-[#091528]">
                                  {item.clip_title || item.video_title || `Clip ${item.clip_id.slice(0, 8)}`}
                                </span>
                                <span className="block text-[11px] text-[#6A7280]">Opens with this time prefilled</span>
                              </span>
                            </Link>
                          ))
                        ) : (
                          <p className="rounded-lg border border-dashed border-[#CBD5E1] bg-white px-3 py-3 text-xs text-[#6A7280]">
                            No ready clip exports are available yet. Export a clip first, then schedule it here.
                          </p>
                        )}
                      </div>
                    </div>
                  ) : null}

                  <div className="my-5 h-px bg-[#E1E5EC]" />

                  <ScheduleOptionLink
                    href={`/content-queue?scheduledFor=${encodedSchedule}`}
                    label="Pick from Drafts"
                    icon="drafts"
                  />

                  <button
                    type="button"
                    onClick={() => setSelectedDay(null)}
                    className="mt-5 w-full rounded-lg px-3 py-2 text-center text-base font-medium text-[#4A5568] transition hover:bg-[#F4F8FF]"
                  >
                    Cancel
                  </button>
                </>
              )}
            </div>
          </div>
        ) : null}

        {selectedEvent ? (
          <EventDrawer
            item={selectedEvent}
            timezone={timezone}
            saving={saving}
            onClose={() => setSelectedEvent(null)}
            onSave={(body) => void updateSelectedEvent(body)}
            onAction={(action) => void updateSelectedEvent({ action })}
            onRetry={() => void retrySelectedEvent()}
          />
        ) : null}
      </div>
    </Card>
  );
}

type ScheduleOptionIcon = "text" | "image" | "video" | "story" | "drafts";

function ScheduleIcon({ type }: { type: ScheduleOptionIcon }) {
  if (type === "text") {
    return (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M7 3H14L19 8V21H7V3Z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
        <path d="M14 3V8H19" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
        <path d="M10 12H16M10 16H15" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    );
  }
  if (type === "image") {
    return (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <rect x="4" y="5" width="16" height="14" rx="2" stroke="currentColor" strokeWidth="2" />
        <path d="M7 16L10.5 12.5L13 15L15 13L19 17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="9" cy="9" r="1.2" fill="currentColor" />
      </svg>
    );
  }
  if (type === "video") {
    return (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <rect x="3" y="7" width="13" height="10" rx="2" stroke="currentColor" strokeWidth="2" />
        <path d="M16 10L21 7.5V16.5L16 14V10Z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      </svg>
    );
  }
  if (type === "story") {
    return (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M7 8H5V20H19V8H17" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
        <path d="M9 8L10.5 5H13.5L15 8" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
        <circle cx="12" cy="14" r="3" stroke="currentColor" strokeWidth="2" />
      </svg>
    );
  }
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M3 7H9L11 9H21V19H3V7Z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path d="M3 11H21" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

function scheduleOptionClass(active = false): string {
  return `flex w-full items-center gap-4 rounded-xl border px-4 py-3 text-left transition ${
    active
      ? "border-[var(--app-primary)] bg-[#F4F8FF] text-[var(--app-primary)] shadow-[0_8px_24px_rgba(29,63,208,0.12)]"
      : "border-[#E1E5EC] bg-white text-[#091528] hover:border-[var(--app-primary)] hover:bg-[#F8FAFF]"
  }`;
}

function ScheduleOptionLink({
  href,
  label,
  icon,
}: {
  href: string;
  label: string;
  icon: ScheduleOptionIcon;
}) {
  return (
    <Link href={href} className={scheduleOptionClass()}>
      <span className="text-[#6B7280]">
        <ScheduleIcon type={icon} />
      </span>
      <span className="app-display text-lg font-bold tracking-[-0.03em]">{label}</span>
    </Link>
  );
}

function ScheduleOptionButton({
  label,
  icon,
  active,
  onClick,
}: {
  label: string;
  icon: ScheduleOptionIcon;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button type="button" onClick={onClick} className={scheduleOptionClass(active)}>
      <span className={active ? "text-[var(--app-primary)]" : "text-[#6B7280]"}>
        <ScheduleIcon type={icon} />
      </span>
      <span className="app-display text-lg font-bold tracking-[-0.03em]">{label}</span>
    </button>
  );
}

interface EventDrawerProps {
  item: PublishCalendarItem;
  timezone: string;
  saving: boolean;
  onClose: () => void;
  onSave: (body: Record<string, unknown>) => void;
  onAction: (action: "cancel" | "post_now") => void;
  onRetry: () => void;
}

function EventDrawer({ item, timezone, saving, onClose, onSave, onAction, onRetry }: EventDrawerProps) {
  const [scheduledFor, setScheduledFor] = useState(() => localInputValue(item.scheduled_for));
  const [title, setTitle] = useState(item.title || "");
  const [caption, setCaption] = useState(item.caption || "");
  const [description, setDescription] = useState(item.description || "");
  const [hashtags, setHashtags] = useState((item.hashtags || []).join(" "));
  const editable = item.status === "scheduled";
  const meta = getSocialPlatformMeta(item.platform);

  return (
    <div className="fixed inset-0 z-[60] bg-[#091528]/35" onMouseDown={onClose}>
      <aside
        className="ml-auto h-full w-full max-w-md overflow-y-auto bg-white p-5 shadow-2xl"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className={`inline-flex h-9 w-9 items-center justify-center rounded-lg ${meta.chipClassName}`}>
              {meta.icon}
            </span>
            <div>
              <p className="font-semibold text-[var(--app-text)]">{eventTitle(item)}</p>
              <p className="text-xs text-[var(--app-muted)]">
                {meta.displayName} · {item.destination_display_name || "Disconnected account"}
              </p>
            </div>
          </div>
          <button type="button" onClick={onClose} className="text-xs text-[var(--app-muted)]">Close</button>
        </div>
        <span className={`mt-3 inline-flex rounded-full px-2 py-1 text-xs ${STATUS_STYLES[item.status]}`}>
          {prettyStatus(item.status)}
        </span>

        <div className="mt-4 space-y-3">
          <label className="block text-xs text-[var(--app-muted)]">
            Schedule ({timezone})
            <input
              type="datetime-local"
              value={scheduledFor}
              onChange={(event) => setScheduledFor(event.target.value)}
              disabled={!editable}
              className="mt-1 w-full rounded-md border px-3 py-2 text-sm disabled:bg-slate-50"
            />
          </label>
          <label className="block text-xs text-[var(--app-muted)]">
            Title
            <input value={title} onChange={(event) => setTitle(event.target.value)} disabled={!editable} className="mt-1 w-full rounded-md border px-3 py-2 text-sm disabled:bg-slate-50" />
          </label>
          <label className="block text-xs text-[var(--app-muted)]">
            Caption
            <textarea value={caption} onChange={(event) => setCaption(event.target.value)} disabled={!editable} rows={4} className="mt-1 w-full rounded-md border px-3 py-2 text-sm disabled:bg-slate-50" />
          </label>
          <label className="block text-xs text-[var(--app-muted)]">
            Description
            <textarea value={description} onChange={(event) => setDescription(event.target.value)} disabled={!editable} rows={3} className="mt-1 w-full rounded-md border px-3 py-2 text-sm disabled:bg-slate-50" />
          </label>
          <label className="block text-xs text-[var(--app-muted)]">
            Hashtags
            <input value={hashtags} onChange={(event) => setHashtags(event.target.value)} disabled={!editable} className="mt-1 w-full rounded-md border px-3 py-2 text-sm disabled:bg-slate-50" />
          </label>
        </div>

        {safeCalendarErrorMessage(item) ? (
          <p className="mt-4 rounded-md bg-red-50 p-3 text-xs text-red-700">{safeCalendarErrorMessage(item)}</p>
        ) : null}
        {item.external_post_url ? (
          <a href={item.external_post_url} target="_blank" rel="noreferrer" className="mt-4 inline-flex text-sm text-[var(--app-primary)] underline">
            Open published post
          </a>
        ) : null}

        <div className="mt-5 flex flex-wrap gap-2">
          {editable ? (
            <>
              <button
                type="button"
                disabled={saving}
                onClick={() =>
                  onSave({
                    scheduled_for: scheduledFor ? new Date(scheduledFor).toISOString() : null,
                    timezone,
                    title: title || null,
                    caption: caption || null,
                    description: description || null,
                    hashtags: hashtags.split(/[\s,]+/).filter(Boolean),
                  })
                }
                className="rounded-md bg-[var(--app-primary)] px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
              >
                Save changes
              </button>
              <button type="button" disabled={saving} onClick={() => onAction("post_now")} className="rounded-md border px-3 py-2 text-xs">
                Post now
              </button>
              <button type="button" disabled={saving} onClick={() => onAction("cancel")} className="rounded-md border border-red-200 px-3 py-2 text-xs text-red-700">
                Cancel job
              </button>
            </>
          ) : ["failed", "provider_not_configured", "waiting_user_action"].includes(item.status) ? (
            <button type="button" disabled={saving} onClick={onRetry} className="rounded-md bg-[var(--app-primary)] px-3 py-2 text-xs font-semibold text-white">
              Retry
            </button>
          ) : null}
        </div>
      </aside>
    </div>
  );
}
