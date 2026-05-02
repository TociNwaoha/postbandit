"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { api, ApiError } from "@/lib/api";
import {
  Clip,
  ConnectedAccount,
  Export,
  PublishJobStatus,
  SocialPlatform,
  SocialProvider,
  SocialPublishJob,
} from "@/types";

interface SocialPublishPanelProps {
  exports: Export[];
  clip: Clip;
  onClipUpdate?: (clip: Clip) => void;
}

interface PublishFormFields {
  caption: string;
  title: string;
  description: string;
  hashtags: string;
  privacy: string;
  scheduled_for: string;
}

interface TargetDraft {
  enabled: boolean;
  connected_account_id: string;
  use_override: boolean;
  override: PublishFormFields;
}

const PLATFORM_ORDER: SocialPlatform[] = ["instagram", "threads", "facebook", "youtube", "x", "tiktok", "linkedin"];
const ACTIVE_PUBLISH_STATUSES = new Set<PublishJobStatus>(["queued", "publishing"]);
const PRIVACY_OPTIONS_BY_PLATFORM: Partial<Record<SocialPlatform, Array<{ value: string; label: string }>>> = {
  youtube: [
    { value: "private", label: "Private" },
    { value: "unlisted", label: "Unlisted" },
    { value: "public", label: "Public" },
  ],
};
const TIKTOK_DEFAULT_PRIVACY_OPTIONS = [
  "PUBLIC_TO_EVERYONE",
  "MUTUAL_FOLLOW_FRIENDS",
  "FOLLOWER_OF_CREATOR",
  "SELF_ONLY",
];
const TIKTOK_PRIVACY_LABELS: Record<string, string> = {
  PUBLIC_TO_EVERYONE: "Public to everyone",
  MUTUAL_FOLLOW_FRIENDS: "Mutual follow friends",
  FOLLOWER_OF_CREATOR: "Followers of creator",
  SELF_ONLY: "Only me",
};

const statusStyles: Record<PublishJobStatus, string> = {
  queued: "bg-slate-700/80 text-slate-200",
  publishing: "bg-blue-500/20 text-blue-300 animate-pulse",
  published: "bg-emerald-500/20 text-emerald-300",
  failed: "bg-red-500/20 text-red-300",
  waiting_user_action: "bg-amber-500/20 text-amber-300",
  provider_not_configured: "bg-yellow-500/20 text-yellow-300",
};

function emptyFields(): PublishFormFields {
  return {
    caption: "",
    title: "",
    description: "",
    hashtags: "",
    privacy: "",
    scheduled_for: "",
  };
}

function normalizeText(value: string): string | null {
  const trimmed = value.trim();
  return trimmed.length ? trimmed : null;
}

function cleanText(value: string | null | undefined): string {
  return (value || "").trim();
}

function descriptionFromTranscript(transcript: string | null | undefined): string {
  const normalized = (transcript || "").replace(/\s+/g, " ").trim();
  if (!normalized) return "";

  const maxLen = 260;
  if (normalized.length <= maxLen) return normalized;

  const cut = normalized.slice(0, maxLen);
  const lastSpace = cut.lastIndexOf(" ");
  const safeCut = lastSpace > 120 ? cut.slice(0, lastSpace) : cut;
  return `${safeCut.trim()}...`;
}

function parseHashtags(value: string): string[] | null {
  const parts = value
    .split(/[,\s]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => (item.startsWith("#") ? item : `#${item}`));

  const deduped: string[] = [];
  const seen = new Set<string>();
  for (const item of parts) {
    const key = item.toLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      deduped.push(item);
    }
  }
  return deduped.length ? deduped : null;
}

function privacyLabelForValue(platform: SocialPlatform, value: string): string {
  if (platform === "tiktok") {
    return TIKTOK_PRIVACY_LABELS[value] || value;
  }
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function tiktokPrivacyOptionsForAccount(account: ConnectedAccount | undefined): Array<{ value: string; label: string }> {
  const creatorInfo = account?.metadata_json?.tiktok_creator_info;
  const rawOptions = Array.isArray((creatorInfo as Record<string, unknown> | undefined)?.privacy_level_options)
    ? (((creatorInfo as Record<string, unknown>).privacy_level_options as unknown[]) || [])
    : [];

  const options: Array<{ value: string; label: string }> = [];
  const seen = new Set<string>();
  for (const item of rawOptions) {
    if (typeof item !== "string") continue;
    const value = item.trim().toUpperCase();
    if (!value || seen.has(value)) continue;
    seen.add(value);
    options.push({ value, label: privacyLabelForValue("tiktok", value) });
  }

  if (options.length) return options;
  return TIKTOK_DEFAULT_PRIVACY_OPTIONS.map((value) => ({
    value,
    label: privacyLabelForValue("tiktok", value),
  }));
}

function privacyOptionsForTarget(
  platform: SocialPlatform,
  selectedAccount: ConnectedAccount | undefined
): Array<{ value: string; label: string }> {
  if (platform === "tiktok") {
    return tiktokPrivacyOptionsForAccount(selectedAccount);
  }
  return PRIVACY_OPTIONS_BY_PLATFORM[platform] || [];
}

function toIsoDatetime(value: string): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toISOString();
}

function toPayloadFields(fields: PublishFormFields) {
  return {
    caption: normalizeText(fields.caption),
    title: normalizeText(fields.title),
    description: normalizeText(fields.description),
    hashtags: parseHashtags(fields.hashtags),
    privacy: normalizeText(fields.privacy),
    scheduled_for: toIsoDatetime(fields.scheduled_for),
  };
}
type PublishPayloadFields = ReturnType<typeof toPayloadFields>;

function prettyStatus(status: PublishJobStatus): string {
  return status
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string");
}

function isReconnectRequiredXJob(job: SocialPublishJob | undefined): boolean {
  if (!job || job.platform !== "x") return false;

  const metadata = job.provider_metadata_json || {};
  const action = typeof metadata.action === "string" ? metadata.action : "";
  const reason = typeof metadata.reason === "string" ? metadata.reason : "";
  const missingScopes = asStringArray(metadata.missing_scopes).map((scope) => scope.toLowerCase());
  const errorMessage = (job.error_message || "").toLowerCase();

  if (action === "reconnect_x") return true;
  if (job.status === "waiting_user_action" && (reason === "missing_scope" || reason === "reconnect_required")) {
    return true;
  }
  if (missingScopes.includes("media.write")) return true;
  return errorMessage.includes("reconnect");
}

function hasAnyOverrideValue(fields: PublishFormFields): boolean {
  return Boolean(
    fields.caption.trim() ||
      fields.title.trim() ||
      fields.description.trim() ||
      fields.hashtags.trim() ||
      fields.privacy.trim() ||
      fields.scheduled_for.trim()
  );
}

function isFacebookPageDestination(account: ConnectedAccount): boolean {
  return account.platform === "facebook" && account.destination_type === "facebook_page";
}

function isFacebookAccountIdentity(account: ConnectedAccount): boolean {
  return account.platform === "facebook" && account.destination_type === "facebook_account";
}

function pad2(value: number): string {
  return value.toString().padStart(2, "0");
}

function toLocalDateInput(value: Date): string {
  return `${value.getFullYear()}-${pad2(value.getMonth() + 1)}-${pad2(value.getDate())}`;
}

function parseLocalDatetimeInput(value: string): Date | null {
  if (!value) return null;
  const [datePart, timePart] = value.split("T");
  if (!datePart || !timePart) return null;
  const [yearText, monthText, dayText] = datePart.split("-");
  const [hourText, minuteText] = timePart.split(":");
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const hour = Number(hourText);
  const minute = Number(minuteText);
  if (
    !Number.isFinite(year) ||
    !Number.isFinite(month) ||
    !Number.isFinite(day) ||
    !Number.isFinite(hour) ||
    !Number.isFinite(minute)
  ) {
    return null;
  }

  const parsed = new Date(year, month - 1, day, hour, minute, 0, 0);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed;
}

function startOfDay(value: Date): Date {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate(), 0, 0, 0, 0);
}

function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function ceilToNextFiveMinutes(value: Date): Date {
  const next = new Date(value.getTime() + 60_000);
  next.setSeconds(0, 0);
  const remainder = next.getMinutes() % 5;
  if (remainder !== 0) {
    next.setMinutes(next.getMinutes() + (5 - remainder));
  }
  return next;
}

function formatScheduleLabel(value: string): string {
  const parsed = parseLocalDatetimeInput(value);
  if (!parsed) return "Select date and time";
  return parsed.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function getBrowserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "Local time";
  } catch {
    return "Local time";
  }
}

interface SchedulePickerProps {
  value: string;
  onChange: (next: string) => void;
  disabled?: boolean;
  disabledReason?: string;
}

function SchedulePicker({ value, onChange, disabled = false, disabledReason }: SchedulePickerProps) {
  const [open, setOpen] = useState(false);
  const [nowTick, setNowTick] = useState(Date.now());
  const [timezone, setTimezone] = useState("Local time");
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const parsedValue = parseLocalDatetimeInput(value);
  const [visibleMonth, setVisibleMonth] = useState<Date>(() => {
    const base = parsedValue || new Date();
    return new Date(base.getFullYear(), base.getMonth(), 1);
  });
  const now = new Date(nowTick);

  useEffect(() => {
    setTimezone(getBrowserTimeZone());
  }, []);

  useEffect(() => {
    if (!open) return;
    const timer = window.setInterval(() => setNowTick(Date.now()), 15_000);
    return () => window.clearInterval(timer);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onMouseDown = (event: MouseEvent) => {
      if (!wrapperRef.current) return;
      if (!wrapperRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onMouseDown);
    return () => document.removeEventListener("mousedown", onMouseDown);
  }, [open]);

  useEffect(() => {
    const base = parsedValue || new Date();
    setVisibleMonth(new Date(base.getFullYear(), base.getMonth(), 1));
  }, [value]);

  const monthStart = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth(), 1);
  const monthEnd = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth() + 1, 0);
  const leadingDays = monthStart.getDay();
  const totalDays = monthEnd.getDate();
  const todayStart = startOfDay(now);

  const calendarCells: Array<{ key: string; date: Date | null; disabled: boolean }> = [];
  for (let i = 0; i < leadingDays; i += 1) {
    calendarCells.push({ key: `blank-${i}`, date: null, disabled: true });
  }
  for (let day = 1; day <= totalDays; day += 1) {
    const date = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth(), day, 0, 0, 0, 0);
    calendarCells.push({
      key: toLocalDateInput(date),
      date,
      disabled: date.getTime() < todayStart.getTime(),
    });
  }

  const selectedDate = parsedValue ? startOfDay(parsedValue) : null;
  const selectedDateKey = selectedDate ? toLocalDateInput(selectedDate) : "";
  const selectedTime = parsedValue ? `${pad2(parsedValue.getHours())}:${pad2(parsedValue.getMinutes())}` : "";

  const timeOptions = useMemo(() => {
    if (!selectedDate) return [] as string[];

    const options: string[] = [];
    const minAllowed = isSameDay(selectedDate, now) ? ceilToNextFiveMinutes(now) : null;
    for (let hour = 0; hour < 24; hour += 1) {
      for (let minute = 0; minute < 60; minute += 5) {
        const slot = new Date(
          selectedDate.getFullYear(),
          selectedDate.getMonth(),
          selectedDate.getDate(),
          hour,
          minute,
          0,
          0
        );
        if (minAllowed && slot.getTime() < minAllowed.getTime()) continue;
        options.push(`${pad2(hour)}:${pad2(minute)}`);
      }
    }
    return options;
  }, [selectedDate, now]);

  const handleDaySelect = (day: Date) => {
    if (day.getTime() < todayStart.getTime()) return;
    const dayKey = toLocalDateInput(day);
    const existing = parsedValue && toLocalDateInput(parsedValue) === dayKey ? parsedValue : null;
    const existingTime = existing ? `${pad2(existing.getHours())}:${pad2(existing.getMinutes())}` : "";

    const minAllowed = isSameDay(day, now) ? ceilToNextFiveMinutes(now) : null;
    const options: string[] = [];
    for (let hour = 0; hour < 24; hour += 1) {
      for (let minute = 0; minute < 60; minute += 5) {
        const slot = new Date(day.getFullYear(), day.getMonth(), day.getDate(), hour, minute, 0, 0);
        if (minAllowed && slot.getTime() < minAllowed.getTime()) continue;
        options.push(`${pad2(hour)}:${pad2(minute)}`);
      }
    }

    const chosenTime = existingTime && options.includes(existingTime) ? existingTime : options[0];
    if (!chosenTime) {
      onChange("");
      return;
    }
    onChange(`${dayKey}T${chosenTime}`);
  };

  const handleTimeSelect = (nextTime: string) => {
    if (!selectedDate) return;
    onChange(`${toLocalDateInput(selectedDate)}T${nextTime}`);
  };

  return (
    <div className="relative mt-1" ref={wrapperRef}>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        disabled={disabled}
        className="flex w-full items-center justify-between rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-left text-sm text-white hover:bg-slate-900 disabled:cursor-not-allowed disabled:opacity-50"
      >
        <span>{value ? formatScheduleLabel(value) : "Post now (no schedule)"}</span>
        <span className="text-xs text-slate-400">{open ? "Close" : "Pick"}</span>
      </button>
      <p className="mt-1 text-[11px] text-slate-500">Timezone: {timezone}</p>
      {disabledReason ? <p className="mt-1 text-[11px] text-slate-500">{disabledReason}</p> : null}

      {open && !disabled ? (
        <div className="absolute z-30 mt-2 w-[320px] rounded-md border border-slate-700 bg-slate-950 p-3 shadow-2xl">
          <div className="mb-2 flex items-center justify-between">
            <button
              type="button"
              onClick={() =>
                setVisibleMonth((prev) => new Date(prev.getFullYear(), prev.getMonth() - 1, 1))
              }
              className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
            >
              Prev
            </button>
            <p className="text-sm font-medium text-slate-100">
              {visibleMonth.toLocaleString(undefined, { month: "long", year: "numeric" })}
            </p>
            <button
              type="button"
              onClick={() =>
                setVisibleMonth((prev) => new Date(prev.getFullYear(), prev.getMonth() + 1, 1))
              }
              className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
            >
              Next
            </button>
          </div>

          <div className="mb-2 grid grid-cols-7 gap-1 text-center text-[10px] uppercase tracking-wide text-slate-500">
            {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((label) => (
              <span key={label}>{label}</span>
            ))}
          </div>

          <div className="grid grid-cols-7 gap-1">
            {calendarCells.map((cell) =>
              cell.date ? (
                <button
                  key={cell.key}
                  type="button"
                  disabled={cell.disabled}
                  onClick={() => handleDaySelect(cell.date as Date)}
                  className={`rounded px-2 py-1 text-xs ${
                    selectedDateKey === cell.key
                      ? "bg-[#7C3AED] text-white"
                      : cell.disabled
                        ? "cursor-not-allowed text-slate-600"
                        : "text-slate-200 hover:bg-slate-800"
                  }`}
                >
                  {cell.date.getDate()}
                </button>
              ) : (
                <span key={cell.key} className="px-2 py-1 text-xs text-transparent">
                  .
                </span>
              )
            )}
          </div>

          <div className="mt-3">
            <label className="text-xs text-slate-400">
              Time
              <select
                value={timeOptions.includes(selectedTime) ? selectedTime : ""}
                onChange={(event) => handleTimeSelect(event.target.value)}
                disabled={!selectedDate || !timeOptions.length}
                className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white focus:border-[#7C3AED] focus:outline-none disabled:opacity-50"
              >
                {!selectedDate ? <option value="">Select a day first</option> : null}
                {selectedDate && !timeOptions.length ? <option value="">No future times left today</option> : null}
                {timeOptions.map((time) => (
                  <option key={time} value={time}>
                    {time}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="mt-3 flex items-center justify-between">
            <button
              type="button"
              onClick={() => {
                onChange("");
                setOpen(false);
              }}
              className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
            >
              Post now
            </button>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded bg-[#7C3AED] px-2 py-1 text-xs font-medium text-white hover:bg-[#6D28D9]"
            >
              Done
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function SocialPublishPanel({ exports, clip: initialClip, onClipUpdate }: SocialPublishPanelProps) {
  const readyExports = useMemo(
    () => exports.filter((item) => item.status === "ready" && item.storage_key),
    [exports]
  );
  const [clip, setClip] = useState<Clip>(initialClip);
  const [selectedExportId, setSelectedExportId] = useState<string>("");
  const [providers, setProviders] = useState<SocialProvider[]>([]);
  const [accounts, setAccounts] = useState<ConnectedAccount[]>([]);
  const [publishJobs, setPublishJobs] = useState<SocialPublishJob[]>([]);
  const [universalFields, setUniversalFields] = useState<PublishFormFields>(emptyFields());
  const [targetDrafts, setTargetDrafts] = useState<Record<SocialPlatform, TargetDraft>>(
    Object.fromEntries(
      PLATFORM_ORDER.map((platform) => [platform, { enabled: false, connected_account_id: "", use_override: false, override: emptyFields() }])
    ) as Record<SocialPlatform, TargetDraft>
  );
  const [loadingMeta, setLoadingMeta] = useState(true);
  const [loadingJobs, setLoadingJobs] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [generatingCopy, setGeneratingCopy] = useState(false);
  const [retryingJobId, setRetryingJobId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setClip(initialClip);
  }, [initialClip]);

  useEffect(() => {
    if (!readyExports.length) {
      setSelectedExportId("");
      return;
    }
    if (!selectedExportId || !readyExports.some((item) => item.id === selectedExportId)) {
      setSelectedExportId(readyExports[0].id);
    }
  }, [readyExports, selectedExportId]);

  const providersByPlatform = useMemo(
    () => Object.fromEntries(providers.map((provider) => [provider.platform, provider])) as Record<string, SocialProvider>,
    [providers]
  );

  const accountsByPlatform = useMemo(() => {
    const grouped: Record<string, ConnectedAccount[]> = {};
    for (const account of accounts) {
      if (!grouped[account.platform]) {
        grouped[account.platform] = [];
      }
      grouped[account.platform].push(account);
    }
    return grouped;
  }, [accounts]);

  const latestJobsByPlatform = useMemo(() => {
    const map = new Map<SocialPlatform, SocialPublishJob>();
    for (const job of publishJobs) {
      if (!map.has(job.platform)) {
        map.set(job.platform, job);
      }
    }
    return map;
  }, [publishJobs]);

  const loadMeta = async () => {
    setLoadingMeta(true);
    setError(null);
    try {
      const [providersData, accountsData] = await Promise.all([
        api.get<SocialProvider[]>("/api/social/providers"),
        api.get<ConnectedAccount[]>("/api/social/accounts"),
      ]);
      setProviders(providersData);
      setAccounts(accountsData);

      setTargetDrafts((previous) => {
        const next = { ...previous };
        for (const platform of PLATFORM_ORDER) {
          const platformAccounts = accountsData.filter((account) => account.platform === platform);
          const selectableAccounts =
            platform === "facebook"
              ? platformAccounts.filter((account) => isFacebookPageDestination(account))
              : platformAccounts;
          const defaultAccountId = selectableAccounts[0]?.id ?? "";
          const prior = previous[platform] ?? {
            enabled: false,
            connected_account_id: "",
            use_override: false,
            override: emptyFields(),
          };

          next[platform] = {
            ...prior,
            connected_account_id:
              prior.connected_account_id &&
              selectableAccounts.some((account) => account.id === prior.connected_account_id)
                ? prior.connected_account_id
                : defaultAccountId,
          };
        }
        return next;
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load social providers");
    } finally {
      setLoadingMeta(false);
    }
  };

  const loadPublishJobs = async (exportId: string) => {
    if (!exportId) {
      setPublishJobs([]);
      return;
    }
    setLoadingJobs(true);
    try {
      const jobs = await api.get<SocialPublishJob[]>(
        `/api/social/publish?export_id=${encodeURIComponent(exportId)}`
      );
      setPublishJobs(jobs);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load publish status");
    } finally {
      setLoadingJobs(false);
    }
  };

  useEffect(() => {
    void loadMeta();
  }, []);

  useEffect(() => {
    void loadPublishJobs(selectedExportId);
  }, [selectedExportId]);

  useEffect(() => {
    if (!publishJobs.some((job) => ACTIVE_PUBLISH_STATUSES.has(job.status))) return;
    const timer = window.setInterval(() => {
      if (!selectedExportId) return;
      void loadPublishJobs(selectedExportId);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [publishJobs, selectedExportId]);

  const handlePlatformToggle = (platform: SocialPlatform, enabled: boolean) => {
    setTargetDrafts((previous) => ({
      ...previous,
      [platform]: {
        ...previous[platform],
        enabled,
      },
    }));
  };

  const handlePlatformAccountChange = (platform: SocialPlatform, accountId: string) => {
    setTargetDrafts((previous) => ({
      ...previous,
      [platform]: {
        ...previous[platform],
        connected_account_id: accountId,
      },
    }));
  };

  const handleOverrideToggle = (platform: SocialPlatform, useOverride: boolean) => {
    setTargetDrafts((previous) => ({
      ...previous,
      [platform]: {
        ...previous[platform],
        use_override: useOverride,
      },
    }));
  };

  const handleOverrideFieldChange = (
    platform: SocialPlatform,
    key: keyof PublishFormFields,
    value: string
  ) => {
    setTargetDrafts((previous) => ({
      ...previous,
      [platform]: {
        ...previous[platform],
        override: {
          ...previous[platform].override,
          [key]: value,
        },
      },
    }));
  };

  const applyClipCopyToUniversalFields = (source: Clip) => {
    const title = cleanText(source.title_options?.[0] || source.title || "");
    const hashtagsArray = source.hashtag_options?.[0] || source.hashtags || [];
    const hashtags = hashtagsArray.join(" ").trim();
    const caption = [title, hashtags].filter(Boolean).join("\n\n");
    const description = descriptionFromTranscript(source.transcript_text);

    setUniversalFields((previous) => ({
      ...previous,
      title,
      caption,
      description,
      hashtags,
    }));
  };

  const handleGenerateCopy = async () => {
    setError(null);
    setMessage(null);

    const hasStoredCopy =
      clip.copy_generation_status === "ready" &&
      Array.isArray(clip.title_options) &&
      clip.title_options.length > 0 &&
      Array.isArray(clip.hashtag_options) &&
      clip.hashtag_options.length > 0;

    if (hasStoredCopy) {
      applyClipCopyToUniversalFields(clip);
      setMessage("Filled fields from existing AI clip copy.");
      return;
    }

    setGeneratingCopy(true);
    try {
      const updatedClip = await api.post<Clip>(`/api/clips/${clip.id}/generate-copy`, {});
      setClip(updatedClip);
      onClipUpdate?.(updatedClip);
      applyClipCopyToUniversalFields(updatedClip);
      setMessage("Generated clip copy and filled title, caption, and description.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "AI copy generation is unavailable right now.");
    } finally {
      setGeneratingCopy(false);
    }
  };

  const handleCreatePublishJobs = async () => {
    if (!selectedExportId) {
      setError("Select a ready export before publishing.");
      return;
    }

    const universalPayload = toPayloadFields({
      ...universalFields,
      privacy: "",
    });
    const universalPrivacy = normalizeText(universalFields.privacy) || null;

    const targets: Array<Record<string, unknown>> = [];
    for (const platform of PLATFORM_ORDER) {
      const draft = targetDrafts[platform];
      if (!draft?.enabled || !draft.connected_account_id) continue;

      const target: Record<string, unknown> = {
        platform,
        connected_account_id: draft.connected_account_id,
      };

      const platformAccounts = accountsByPlatform[platform] || [];
      const selectedAccount = platformAccounts.find((account) => account.id === draft.connected_account_id);
      const privacyOptions = privacyOptionsForTarget(platform, selectedAccount);

      const useOverridePayload = platform === "tiktok" ? true : draft.use_override;
      let overridePayload: PublishPayloadFields | null = useOverridePayload && hasAnyOverrideValue(draft.override)
        ? toPayloadFields(draft.override)
        : null;

      const overridePrivacy = useOverridePayload ? normalizeText(draft.override.privacy) || null : null;
      if (privacyOptions.length) {
        const resolvedPrivacy = platform === "tiktok" ? overridePrivacy : (overridePrivacy ?? universalPrivacy);
        if (platform === "tiktok" && !resolvedPrivacy) {
          setError(
            "TikTok requires an explicit privacy selection. Choose a privacy option in the TikTok platform section."
          );
          return;
        }
        if (resolvedPrivacy) {
          const matchingOption = privacyOptions.find(
            (option) => option.value.toLowerCase() === resolvedPrivacy.toLowerCase()
          );
          if (!matchingOption) {
            const allowed = privacyOptions.map((option) => option.label).join(", ");
            setError(`Invalid TikTok privacy selection. Allowed options: ${allowed}`);
            return;
          }
          overridePayload = {
            caption: overridePayload?.caption ?? null,
            title: overridePayload?.title ?? null,
            description: overridePayload?.description ?? null,
            hashtags: overridePayload?.hashtags ?? null,
            privacy: matchingOption.value,
            scheduled_for: overridePayload?.scheduled_for ?? null,
          };
        }
      } else if (overridePayload?.privacy) {
        overridePayload = {
          caption: overridePayload?.caption ?? null,
          title: overridePayload?.title ?? null,
          description: overridePayload?.description ?? null,
          hashtags: overridePayload?.hashtags ?? null,
          privacy: null,
          scheduled_for: overridePayload?.scheduled_for ?? null,
        };
      }

      if (overridePayload) {
        target.override = overridePayload;
      }
      targets.push(target);
    }

    if (!targets.length) {
      setError("Select at least one platform and connected account.");
      return;
    }

    setPublishing(true);
    setError(null);
    setMessage(null);
    try {
      const created = await api.post<SocialPublishJob[]>("/api/social/publish", {
        export_id: selectedExportId,
        universal: universalPayload,
        targets,
      });
      setMessage(`Created ${created.length} publish job(s).`);
      await loadPublishJobs(selectedExportId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create publish jobs");
    } finally {
      setPublishing(false);
    }
  };

  const handleRetry = async (publishJobId: string) => {
    setRetryingJobId(publishJobId);
    setError(null);
    setMessage(null);
    try {
      await api.post<SocialPublishJob>(`/api/social/publish/${publishJobId}/retry`, {});
      setMessage("Retry queued.");
      await loadPublishJobs(selectedExportId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to retry publish job");
    } finally {
      setRetryingJobId(null);
    }
  };

  const anyScheduleCapableProvider = useMemo(
    () => providers.some((provider) => provider.capabilities?.supports_schedule),
    [providers]
  );

  const openFacebookManualShare = () => {
    if (!selectedExportId) {
      setError("Select a ready export first.");
      return;
    }
    if (typeof window === "undefined") return;

    const shareUrl = `${window.location.origin}/share/exports/${selectedExportId}`;
    const quote = [universalFields.title.trim(), universalFields.caption.trim()]
      .filter(Boolean)
      .join(" ")
      .trim()
      .slice(0, 250);
    const dialogUrl = `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(shareUrl)}${
      quote ? `&quote=${encodeURIComponent(quote)}` : ""
    }`;

    window.open(dialogUrl, "_blank", "noopener,noreferrer");
    setMessage("Opened Facebook manual share dialog for your personal profile.");
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-white">Publish to Social</h3>
          <p className="mt-1 text-xs text-slate-400">
            Publish from a ready export. One publish job is created per selected platform/account.
          </p>
        </div>
        <Link href="/connections" className="text-xs text-[#A78BFA] hover:text-[#C4B5FD]">
          Manage Connections
        </Link>
      </div>

      {message ? <p className="text-sm text-emerald-300">{message}</p> : null}
      {error ? <p className="text-sm text-red-400">{error}</p> : null}

      {loadingMeta ? (
        <p className="inline-flex items-center gap-2 text-sm text-slate-300">
          <LoadingSpinner size="sm" />
          Loading social providers...
        </p>
      ) : null}

      <div className="rounded-md border border-slate-700 bg-slate-900/40 p-3">
        <label className="text-xs text-slate-400">
          Ready Export Asset
          <select
            value={selectedExportId}
            onChange={(event) => setSelectedExportId(event.target.value)}
            className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white focus:border-[#7C3AED] focus:outline-none"
          >
            {readyExports.length ? null : <option value="">No ready exports available</option>}
            {readyExports.map((item) => (
              <option key={item.id} value={item.id}>
                {item.id.slice(0, 8)} • {item.aspect_ratio} • {item.caption_format}
              </option>
            ))}
          </select>
        </label>
        {!readyExports.length ? (
          <p className="mt-2 text-xs text-slate-500">
            Create and wait for a ready export before publishing.
          </p>
        ) : null}
      </div>

      <div className="rounded-md border border-slate-700 bg-slate-900/40 p-3">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-300">Universal Content</h4>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => void handleGenerateCopy()}
            disabled={generatingCopy}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-800 disabled:opacity-60"
          >
            {generatingCopy ? "Generating..." : "Generate Copy"}
          </button>
          <p className="text-xs text-slate-500">
            Fills title, caption, and description from this clip&apos;s AI copy.
          </p>
        </div>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <label className="text-xs text-slate-400">
            Title
            <input
              value={universalFields.title}
              onChange={(event) => setUniversalFields((prev) => ({ ...prev, title: event.target.value }))}
              className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white focus:border-[#7C3AED] focus:outline-none"
            />
          </label>
          <div className="text-xs text-slate-400">
            YouTube Privacy (default)
            <div className="mt-1 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setUniversalFields((prev) => ({ ...prev, privacy: "" }))}
                className={`rounded-full border px-3 py-1 text-xs ${
                  !universalFields.privacy
                    ? "border-[#7C3AED] bg-[#7C3AED]/20 text-[#C4B5FD]"
                    : "border-slate-700 text-slate-300 hover:bg-slate-800"
                }`}
              >
                Not set
              </button>
              {(PRIVACY_OPTIONS_BY_PLATFORM.youtube || []).map((option) => (
                <button
                  key={`universal-privacy-${option.value}`}
                  type="button"
                  onClick={() => setUniversalFields((prev) => ({ ...prev, privacy: option.value }))}
                  className={`rounded-full border px-3 py-1 text-xs ${
                    universalFields.privacy === option.value
                      ? "border-[#7C3AED] bg-[#7C3AED]/20 text-[#C4B5FD]"
                      : "border-slate-700 text-slate-300 hover:bg-slate-800"
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <p className="mt-1 text-[11px] text-slate-500">
              Applied only to providers that support privacy controls.
            </p>
          </div>
          <label className="text-xs text-slate-400 md:col-span-2">
            Caption
            <textarea
              value={universalFields.caption}
              onChange={(event) => setUniversalFields((prev) => ({ ...prev, caption: event.target.value }))}
              rows={2}
              className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white focus:border-[#7C3AED] focus:outline-none"
            />
          </label>
          <label className="text-xs text-slate-400 md:col-span-2">
            Description
            <textarea
              value={universalFields.description}
              onChange={(event) => setUniversalFields((prev) => ({ ...prev, description: event.target.value }))}
              rows={3}
              className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white focus:border-[#7C3AED] focus:outline-none"
            />
          </label>
          <label className="text-xs text-slate-400">
            Hashtags
            <input
              value={universalFields.hashtags}
              onChange={(event) => setUniversalFields((prev) => ({ ...prev, hashtags: event.target.value }))}
              placeholder="#postbandit #podcast"
              className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white focus:border-[#7C3AED] focus:outline-none"
            />
          </label>
          <div className="text-xs text-slate-400">
            Schedule Time (optional)
            <SchedulePicker
              value={universalFields.scheduled_for}
              onChange={(next) => setUniversalFields((prev) => ({ ...prev, scheduled_for: next }))}
              disabled={!anyScheduleCapableProvider}
              disabledReason={
                anyScheduleCapableProvider
                  ? "Applies only to providers that support scheduling."
                  : "Scheduling is unavailable because no loaded provider supports it."
              }
            />
          </div>
        </div>
      </div>

      <div className="space-y-3">
        {PLATFORM_ORDER.map((platform) => {
          const provider = providersByPlatform[platform];
          const platformAccounts = accountsByPlatform[platform] || [];
          const facebookIdentityAccounts = platform === "facebook"
            ? platformAccounts.filter((account) => isFacebookAccountIdentity(account))
            : [];
          const selectableAccounts = platform === "facebook"
            ? platformAccounts.filter((account) => isFacebookPageDestination(account))
            : platformAccounts;
          const draft = targetDrafts[platform];
          const selectedAccount = selectableAccounts.find(
            (account) => account.id === draft?.connected_account_id
          );
          const latestJob = latestJobsByPlatform.get(platform);
          const providerName = provider?.display_name || platform;
          const providerReady = provider?.setup_status === "ready";
          const providerSupportsSchedule = Boolean(provider?.capabilities?.supports_schedule);
          const hasConnectedAccounts = selectableAccounts.length > 0;
          const privacyOptions = privacyOptionsForTarget(platform, selectedAccount);
          const reconnectRequired = isReconnectRequiredXJob(latestJob);
          const providerSetupDetails = (provider?.setup_details || {}) as Record<string, unknown>;
          const threadsSupportsMedia = Boolean(provider?.capabilities?.supports_video_upload);
          const threadsPublishTextReady = Boolean(providerSetupDetails.publish_text_ready);
          const threadsPublishMediaReady = Boolean(providerSetupDetails.publish_media_ready);
          const tiktokDirectReady = Boolean(providerSetupDetails.publish_direct_ready);
          const tiktokUploadReady = Boolean(providerSetupDetails.publish_upload_ready);
          const showOverrideEditor = Boolean(draft?.use_override || platform === "tiktok");

          return (
            <div key={platform} className="rounded-md border border-slate-700 bg-slate-900/30 p-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <label className="inline-flex items-center gap-2 text-sm text-slate-200">
                  <input
                    type="checkbox"
                    checked={draft?.enabled || false}
                    disabled={!providerReady || !hasConnectedAccounts}
                    onChange={(event) => handlePlatformToggle(platform, event.target.checked)}
                    className="h-4 w-4 rounded border-slate-600 bg-slate-950 text-[#7C3AED] focus:ring-[#7C3AED]"
                  />
                  <span className="font-medium">{providerName}</span>
                </label>
                {latestJob ? (
                  <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${statusStyles[latestJob.status]}`}>
                    {prettyStatus(latestJob.status)}
                  </span>
                ) : (
                  <span className="rounded-full bg-slate-800 px-2.5 py-1 text-xs text-slate-300">No jobs yet</span>
                )}
              </div>

              <p className="mt-2 text-xs text-slate-400">
                {!providerReady
                  ? provider?.setup_message || "Provider is not configured"
                  : platform === "facebook"
                    ? hasConnectedAccounts
                      ? `${selectableAccounts.length} page destination(s) connected for automated publishing`
                      : facebookIdentityAccounts.length > 0
                        ? "Facebook account connected, but no Pages found. Automated publishing requires a Page."
                        : "No connected Facebook account yet."
                    : hasConnectedAccounts
                      ? `${selectableAccounts.length} account(s) connected`
                      : "No connected accounts. Connect one first."}
              </p>
              {platform === "threads" ? (
                <p className="mt-1 text-[11px] text-slate-500">
                  {threadsSupportsMedia
                    ? threadsPublishMediaReady
                      ? "Threads text and video publishing are enabled."
                      : threadsPublishTextReady
                        ? "Threads text publishing is enabled. Video publishing may be blocked until app permissions/tester setup are complete."
                        : "Connect a Threads profile to publish text/video."
                    : "Threads text publishing is enabled. Video publishing is not enabled for this provider."}
                </p>
              ) : null}
              {platform === "facebook" ? (
                <p className="mt-1 text-[11px] text-slate-500">
                  Facebook Pages support automated publishing. Personal profile sharing is manual.
                </p>
              ) : null}
              {platform === "tiktok" ? (
                <p className="mt-1 text-[11px] text-slate-500">
                  {tiktokDirectReady
                    ? "TikTok direct post is enabled. If direct post is blocked at runtime, PostBandit falls back to TikTok inbox upload."
                    : tiktokUploadReady
                      ? "TikTok direct post is unavailable right now; inbox upload fallback will be used."
                      : "Connect TikTok and complete app setup to enable publish."}
                </p>
              ) : null}

              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <label className="text-xs text-slate-400">
                  {platform === "facebook" ? "Page Destination" : "Account"}
                  <select
                    value={draft?.connected_account_id || ""}
                    onChange={(event) => handlePlatformAccountChange(platform, event.target.value)}
                    disabled={!hasConnectedAccounts}
                    className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white focus:border-[#7C3AED] focus:outline-none disabled:opacity-50"
                  >
                    {selectableAccounts.length ? null : (
                      <option value="">
                        {platform === "facebook" ? "No Facebook Pages connected" : "No connected accounts"}
                      </option>
                    )}
                    {selectableAccounts.map((account) => (
                      <option key={account.id} value={account.id}>
                        {account.display_name || account.username_or_channel_name || account.external_account_id}
                      </option>
                    ))}
                  </select>
                </label>

                {platform === "tiktok" ? (
                  <p className="inline-flex items-center text-xs text-slate-400">
                    TikTok privacy selection is required.
                  </p>
                ) : (
                  <label className="inline-flex items-center gap-2 text-xs text-slate-300">
                    <input
                      type="checkbox"
                      checked={draft?.use_override || false}
                      onChange={(event) => handleOverrideToggle(platform, event.target.checked)}
                      className="h-4 w-4 rounded border-slate-600 bg-slate-950 text-[#7C3AED] focus:ring-[#7C3AED]"
                    />
                    Use per-platform overrides
                  </label>
                )}
              </div>

              {showOverrideEditor ? (
                <div className="mt-3 grid gap-3 rounded-md border border-slate-700 bg-slate-950/50 p-3 md:grid-cols-2">
                  <label className="text-xs text-slate-400">
                    Title
                    <input
                      value={draft.override.title}
                      onChange={(event) => handleOverrideFieldChange(platform, "title", event.target.value)}
                      className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white focus:border-[#7C3AED] focus:outline-none"
                    />
                  </label>
                  <label className="text-xs text-slate-400">
                    Privacy
                    {privacyOptions.length ? (
                      <div className="mt-1 flex flex-wrap gap-2">
                        {platform !== "tiktok" ? (
                          <button
                            type="button"
                            onClick={() => handleOverrideFieldChange(platform, "privacy", "")}
                            className={`rounded-full border px-3 py-1 text-xs ${
                              !draft.override.privacy
                                ? "border-[#7C3AED] bg-[#7C3AED]/20 text-[#C4B5FD]"
                                : "border-slate-700 text-slate-300 hover:bg-slate-800"
                            }`}
                          >
                            Use default
                          </button>
                        ) : null}
                        {privacyOptions.map((option) => (
                          <button
                            key={`${platform}-privacy-${option.value}`}
                            type="button"
                            onClick={() => handleOverrideFieldChange(platform, "privacy", option.value)}
                            className={`rounded-full border px-3 py-1 text-xs ${
                              draft.override.privacy === option.value
                                ? "border-[#7C3AED] bg-[#7C3AED]/20 text-[#C4B5FD]"
                                : "border-slate-700 text-slate-300 hover:bg-slate-800"
                            }`}
                          >
                            {privacyLabelForValue(platform, option.value)}
                          </button>
                        ))}
                      </div>
                    ) : (
                      <p className="mt-1 text-[11px] text-slate-500">Privacy is not configurable for this provider.</p>
                    )}
                    {platform === "tiktok" ? (
                      <p className="mt-1 text-[11px] text-slate-500">
                        Required by TikTok. Select one option returned for the connected TikTok account.
                      </p>
                    ) : null}
                  </label>
                  <label className="text-xs text-slate-400 md:col-span-2">
                    Caption
                    <textarea
                      value={draft.override.caption}
                      onChange={(event) => handleOverrideFieldChange(platform, "caption", event.target.value)}
                      rows={2}
                      className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white focus:border-[#7C3AED] focus:outline-none"
                    />
                  </label>
                  <label className="text-xs text-slate-400 md:col-span-2">
                    Description
                    <textarea
                      value={draft.override.description}
                      onChange={(event) => handleOverrideFieldChange(platform, "description", event.target.value)}
                      rows={2}
                      className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white focus:border-[#7C3AED] focus:outline-none"
                    />
                  </label>
                  <label className="text-xs text-slate-400">
                    Hashtags
                    <input
                      value={draft.override.hashtags}
                      onChange={(event) => handleOverrideFieldChange(platform, "hashtags", event.target.value)}
                      className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white focus:border-[#7C3AED] focus:outline-none"
                    />
                  </label>
                  <div className="text-xs text-slate-400">
                    Schedule Time
                    <SchedulePicker
                      value={draft.override.scheduled_for}
                      onChange={(next) => handleOverrideFieldChange(platform, "scheduled_for", next)}
                      disabled={!providerSupportsSchedule}
                      disabledReason={
                        providerSupportsSchedule ? undefined : "Scheduling is not supported for this provider."
                      }
                    />
                  </div>
                </div>
              ) : null}

              {latestJob?.error_message ? <p className="mt-3 text-xs text-red-400">{latestJob.error_message}</p> : null}
              {platform === "facebook" ? (
                <div className="mt-3 rounded-md border border-slate-700 bg-slate-950/50 p-3">
                  <p className="text-xs font-medium text-slate-200">Share to personal profile (manual)</p>
                  <p className="mt-1 text-[11px] text-slate-500">
                    Opens Facebook&apos;s manual share flow. This does not create a publish job.
                  </p>
                  <button
                    type="button"
                    onClick={openFacebookManualShare}
                    disabled={!selectedExportId}
                    className="mt-2 inline-flex rounded-md border border-slate-700 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-800 disabled:opacity-60"
                  >
                    Share to Personal Profile
                  </button>
                </div>
              ) : null}
              {platform === "x" && reconnectRequired ? (
                <p className="mt-1 text-[11px] text-amber-300">
                  Reconnect X in{" "}
                  <Link href="/connections" className="underline hover:text-amber-200">
                    Connections
                  </Link>{" "}
                  to grant media permissions, then publish again.
                </p>
              ) : null}
              {platform === "x" && latestJob?.error_message && !reconnectRequired ? (
                <p className="mt-1 text-[11px] text-amber-300">
                  X media posting can fail due to account-tier limits, provider credits, or media policy restrictions.
                </p>
              ) : null}
              {platform === "tiktok" && latestJob?.status === "waiting_user_action" ? (
                <p className="mt-1 text-[11px] text-amber-300">
                  TikTok may require you to finish posting in the TikTok app inbox, or to complete app review/setup for direct post.
                </p>
              ) : null}
              {latestJob?.external_post_url ? (
                <a
                  href={latestJob.external_post_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-3 inline-flex text-xs text-[#A78BFA] hover:text-[#C4B5FD]"
                >
                  Open published post
                </a>
              ) : null}
              {latestJob &&
              (latestJob.status === "failed" || latestJob.status === "provider_not_configured") &&
              !reconnectRequired ? (
                <button
                  type="button"
                  onClick={() => void handleRetry(latestJob.id)}
                  disabled={retryingJobId === latestJob.id}
                  className="mt-3 inline-flex rounded-md border border-slate-700 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-800 disabled:opacity-60"
                >
                  {retryingJobId === latestJob.id ? "Retrying..." : "Retry"}
                </button>
              ) : null}
            </div>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => void handleCreatePublishJobs()}
          disabled={publishing || !selectedExportId || !readyExports.length}
          className="rounded-md bg-[#7C3AED] px-4 py-2 text-sm font-medium text-white hover:bg-[#6D28D9] disabled:opacity-60"
        >
          {publishing ? "Publishing..." : "Publish Selected Platforms"}
        </button>
        <button
          type="button"
          onClick={() => void loadPublishJobs(selectedExportId)}
          disabled={loadingJobs || !selectedExportId}
          className="rounded-md border border-slate-700 px-3 py-2 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-60"
        >
          {loadingJobs ? "Refreshing..." : "Refresh Status"}
        </button>
      </div>

      {publishJobs.length ? (
        <div className="space-y-2 rounded-md border border-slate-700 bg-slate-900/40 p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-300">Per-platform Publish Jobs</p>
          {publishJobs.map((job) => (
            <div key={job.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-slate-700 bg-slate-950/60 px-3 py-2">
              <div className="text-xs text-slate-300">
                <span className="font-medium">{providersByPlatform[job.platform]?.display_name || job.platform}</span>{" "}
                • {job.id.slice(0, 8)}
                {job.external_post_id ? ` • ${job.external_post_id}` : ""}
              </div>
              <span className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${statusStyles[job.status]}`}>
                {prettyStatus(job.status)}
              </span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
