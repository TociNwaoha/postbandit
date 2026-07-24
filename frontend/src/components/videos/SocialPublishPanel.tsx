"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { getPlatformBrandMeta } from "@/components/connections/platformBrand";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { api, ApiError } from "@/lib/api";
import {
  Clip,
  ClipCopyOptionsResponse,
  ConnectedAccount,
  Export,
  PlatformCopyGenerateResponse,
  PublishJobStatus,
  SocialPlatform,
  SocialProvider,
  SocialPublishJob,
} from "@/types";

interface SocialPublishPanelProps {
  exports: Export[];
  clip: Clip;
  onClipUpdate?: (clip: Clip) => void;
  initialScheduledFor?: string;
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
const COPY_REGEN_PLATFORMS: SocialPlatform[] = ["youtube", "tiktok", "instagram", "x", "facebook", "threads"];
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
  scheduled: "bg-indigo-500/15 text-indigo-700",
  queued: "border border-[var(--app-border)] bg-[var(--app-surface-soft)] text-[var(--app-subtle)]",
  publishing: "bg-blue-500/20 text-blue-700 animate-pulse",
  published: "bg-emerald-500/20 text-emerald-700",
  failed: "bg-red-500/20 text-red-700",
  waiting_user_action: "bg-amber-500/20 text-amber-700",
  provider_not_configured: "bg-yellow-500/20 text-yellow-700",
  cancelled: "bg-slate-500/15 text-slate-600",
};
const PLATFORM_COPY_LIMITS: Partial<Record<SocialPlatform, Partial<Record<"title" | "caption" | "description", number>>>> = {
  instagram: { caption: 2200 },
  threads: { caption: 500 },
  facebook: { caption: 5000 },
  youtube: { title: 100, description: 5000 },
  x: { caption: 280 },
  tiktok: { caption: 2200 },
  linkedin: { caption: 3000 },
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
  const scheduledFor = toIsoDatetime(fields.scheduled_for);
  return {
    caption: normalizeText(fields.caption),
    title: normalizeText(fields.title),
    description: normalizeText(fields.description),
    hashtags: parseHashtags(fields.hashtags),
    privacy: normalizeText(fields.privacy),
    scheduled_for: scheduledFor,
    timezone: scheduledFor ? getBrowserTimeZone() : null,
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

function isReconnectRequiredPublishJob(job: SocialPublishJob | undefined): boolean {
  if (!job) return false;

  const metadata = job.provider_metadata_json || {};
  const action = typeof metadata.action === "string" ? metadata.action.toLowerCase() : "";
  const reason = typeof metadata.reason === "string" ? metadata.reason.toLowerCase() : "";
  const errorMessage = (job.error_message || "").toLowerCase();

  if (action.startsWith("reconnect_") || reason === "reconnect_required") return true;
  if (job.platform === "x" && isReconnectRequiredXJob(job)) return true;
  if (errorMessage.includes("reconnect")) return true;
  if (job.platform === "youtube") {
    return (
      errorMessage.includes("oauth2.googleapis.com/token") ||
      errorMessage.includes("googleapis.com/upload/youtube") ||
      errorMessage.includes("bad request") ||
      errorMessage.includes("unauthorized") ||
      errorMessage.includes("invalid token")
    );
  }
  return false;
}

function safePublishErrorMessage(job: SocialPublishJob): string | null {
  if (!job.error_message) return null;
  if (isReconnectRequiredPublishJob(job)) {
    const platformName = getPlatformBrandMeta(job.platform).displayName;
    return `Reconnect ${platformName} in Connections, then retry this post.`;
  }
  return job.error_message;
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
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

function characterCounterClass(length: number, limit: number): string {
  if (length >= limit) return "text-red-700";
  if (length >= limit * 0.9) return "text-amber-700";
  return "text-[var(--app-subtle)]";
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
        className="flex w-full items-center justify-between rounded-md border border-[var(--app-border)] bg-white px-3 py-2 text-left text-sm text-[var(--app-text)] hover:bg-[var(--app-surface-soft)] disabled:cursor-not-allowed disabled:opacity-50"
      >
        <span>{value ? formatScheduleLabel(value) : "Post now (no schedule)"}</span>
        <span className="text-xs text-[var(--app-muted)]">{open ? "Close" : "Pick"}</span>
      </button>
      <p className="mt-1 text-[11px] text-[var(--app-subtle)]">Timezone: {timezone}</p>
      {disabledReason ? <p className="mt-1 text-[11px] text-[var(--app-subtle)]">{disabledReason}</p> : null}

      {open && !disabled ? (
        <div className="absolute z-30 mt-2 w-[320px] rounded-md border border-[var(--app-border)] bg-white p-3 shadow-2xl">
          <div className="mb-2 flex items-center justify-between">
            <button
              type="button"
              onClick={() =>
                setVisibleMonth((prev) => new Date(prev.getFullYear(), prev.getMonth() - 1, 1))
              }
              className="rounded border border-[var(--app-border)] px-2 py-1 text-xs text-[var(--app-muted)] hover:bg-[var(--app-surface-soft)]"
            >
              Prev
            </button>
            <p className="text-sm font-medium text-[var(--app-text)]">
              {visibleMonth.toLocaleString(undefined, { month: "long", year: "numeric" })}
            </p>
            <button
              type="button"
              onClick={() =>
                setVisibleMonth((prev) => new Date(prev.getFullYear(), prev.getMonth() + 1, 1))
              }
              className="rounded border border-[var(--app-border)] px-2 py-1 text-xs text-[var(--app-muted)] hover:bg-[var(--app-surface-soft)]"
            >
              Next
            </button>
          </div>

          <div className="mb-2 grid grid-cols-7 gap-1 text-center text-[10px] uppercase tracking-wide text-[var(--app-subtle)]">
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
                      ? "bg-[#1D3FD0] text-white"
                      : cell.disabled
                        ? "cursor-not-allowed text-[var(--app-muted)]"
                        : "text-[var(--app-text)] hover:bg-[var(--app-surface-soft)]"
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
            <label className="text-xs text-[var(--app-muted)]">
              Time
              <select
                value={timeOptions.includes(selectedTime) ? selectedTime : ""}
                onChange={(event) => handleTimeSelect(event.target.value)}
                disabled={!selectedDate || !timeOptions.length}
                className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-white px-3 py-2 text-sm text-[var(--app-text)] focus:border-[#1D3FD0] focus:outline-none disabled:opacity-50"
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
              className="rounded border border-[var(--app-border)] px-2 py-1 text-xs text-[var(--app-muted)] hover:bg-[var(--app-surface-soft)]"
            >
              Post now
            </button>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded bg-[#1D3FD0] px-2 py-1 text-xs font-medium text-white hover:bg-[#1633B8]"
            >
              Done
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

interface CopyOptionSelectProps {
  label: string;
  options: string[] | string[][];
  currentValue: string;
  onSelect: (value: string) => void;
  isHashtags?: boolean;
}

function trimOptionLabel(value: string): string {
  return value.length > 100 ? `${value.slice(0, 100)}...` : value;
}

function CopyOptionSelect({
  label,
  options,
  currentValue,
  onSelect,
  isHashtags = false,
}: CopyOptionSelectProps) {
  const optionValues = options.map((option) => (isHashtags ? (option as string[]).join(" ") : String(option)));
  const selectedValue = optionValues.includes(currentValue) ? currentValue : "";
  if (!optionValues.length) return null;

  return (
    <label className="text-xs text-[var(--app-muted)]">
      {label} options
      <select
        value={selectedValue}
        onChange={(event) => onSelect(event.target.value)}
        className="mt-1 w-full cursor-pointer rounded-md border border-[var(--app-border)] bg-white px-2.5 py-1.5 text-sm text-[var(--app-text)] focus:border-[#1D3FD0] focus:outline-none"
      >
        <option value="" disabled>
          Pick {label.toLowerCase()}...
        </option>
        {optionValues.map((value, index) => (
          <option key={`${label}-${index}-${value.slice(0, 24)}`} value={value}>
            {index + 1}. {trimOptionLabel(value)}
          </option>
        ))}
      </select>
    </label>
  );
}

export function SocialPublishPanel({
  exports,
  clip: initialClip,
  onClipUpdate,
  initialScheduledFor,
}: SocialPublishPanelProps) {
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
  const [generatingCopyPlatform, setGeneratingCopyPlatform] = useState<SocialPlatform | null>(null);
  const [copyOptions, setCopyOptions] = useState<ClipCopyOptionsResponse | null>(null);
  const [showCopyInstructions, setShowCopyInstructions] = useState(false);
  const [copyInstructions, setCopyInstructions] = useState("");
  const [generatingPlatformCopy, setGeneratingPlatformCopy] = useState(false);
  const [retryingJobId, setRetryingJobId] = useState<string | null>(null);
  const [showUniversalEditor, setShowUniversalEditor] = useState(false);
  const [showScheduleConfirm, setShowScheduleConfirm] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const schedulePrefillAppliedRef = useRef(false);

  useEffect(() => {
    setClip(initialClip);
  }, [initialClip]);

  useEffect(() => {
    if (schedulePrefillAppliedRef.current || !initialScheduledFor) return;
    const parsed = parseLocalDatetimeInput(initialScheduledFor);
    if (!parsed || parsed.getTime() <= Date.now()) return;

    schedulePrefillAppliedRef.current = true;
    setUniversalFields((previous) => ({
      ...previous,
      scheduled_for: initialScheduledFor,
    }));
    setShowUniversalEditor(true);
    setMessage(`Schedule date prefilled for ${formatScheduleLabel(initialScheduledFor)}.`);
  }, [initialScheduledFor]);

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

  const selectedPlatforms = useMemo(
    () =>
      PLATFORM_ORDER.filter((platform) => {
        const draft = targetDrafts[platform];
        return Boolean(draft?.enabled && draft.connected_account_id);
      }),
    [targetDrafts]
  );

  const scheduleConfirmTime = useMemo(() => {
    if (universalFields.scheduled_for) return universalFields.scheduled_for;
    for (const platform of selectedPlatforms) {
      const value = targetDrafts[platform]?.override.scheduled_for;
      if (value) return value;
    }
    return "";
  }, [selectedPlatforms, targetDrafts, universalFields.scheduled_for]);

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

  const applyCopyOptionsToUniversalFields = (options: ClipCopyOptionsResponse) => {
    setUniversalFields((previous) => ({
      ...previous,
      title: options.titles[0] || previous.title,
      caption: options.captions[0] || previous.caption,
      description: options.descriptions[0] || previous.description,
      hashtags: (options.hashtag_sets[0] || []).join(" ") || previous.hashtags,
    }));
  };

  const handleGenerateCopy = async (platform?: SocialPlatform) => {
    setError(null);
    setMessage(null);
    setCopyOptions(null);
    setGeneratingCopyPlatform(platform || null);

    setGeneratingCopy(true);
    try {
      const generated = await api.post<ClipCopyOptionsResponse>(`/api/clips/${clip.id}/generate-copy`, {
        platform: platform || null,
        instructions: copyInstructions.trim() || null,
      });
      setCopyOptions(generated);
      const updatedClip = {
        ...clip,
        copy_generation_status: "ready",
        copy_generation_error: null,
        title: generated.titles[0] || clip.title,
        hashtags: generated.hashtag_sets[0] || clip.hashtags,
        title_options: generated.titles,
        hashtag_options: generated.hashtag_sets,
      };
      setClip((previous) => ({
        ...previous,
        copy_generation_status: "ready",
        copy_generation_error: null,
        title: generated.titles[0] || previous.title,
        hashtags: generated.hashtag_sets[0] || previous.hashtags,
        title_options: generated.titles,
        hashtag_options: generated.hashtag_sets,
      }));
      onClipUpdate?.(updatedClip);
      applyCopyOptionsToUniversalFields(generated);
      setMessage(
        generated.platform
          ? `Generated 3 ${generated.platform} copy options for title, caption, description, and hashtags.`
          : "Generated 3 copy options for title, caption, description, and hashtags."
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "AI copy generation is unavailable right now.");
    } finally {
      setGeneratingCopy(false);
      setGeneratingCopyPlatform(null);
    }
  };

  const handleGeneratePlatformCopy = async () => {
    const selectedPlatforms = PLATFORM_ORDER.filter((platform) => targetDrafts[platform]?.enabled);
    if (!selectedPlatforms.length) {
      setError("Select at least one connected platform before generating platform copy.");
      return;
    }

    setGeneratingPlatformCopy(true);
    setError(null);
    setMessage(null);
    try {
      const generated = await api.post<PlatformCopyGenerateResponse>(
        `/api/clips/${clip.id}/generate-platform-copy`,
        { platforms: selectedPlatforms }
      );
      setTargetDrafts((previous) => {
        const next = { ...previous };
        for (const platform of selectedPlatforms) {
          const copy = generated.results[platform];
          if (!copy) continue;
          const prior = previous[platform];
          next[platform] = {
            ...prior,
            use_override: true,
            override: {
              ...prior.override,
              title: copy.title ?? prior.override.title,
              caption: copy.caption ?? prior.override.caption,
              description: copy.description ?? prior.override.description,
              hashtags: copy.hashtags.length ? copy.hashtags.join(" ") : prior.override.hashtags,
            },
          };
        }
        return next;
      });
      const generatedCount = Object.keys(generated.results).length;
      const errorCount = Object.keys(generated.errors).length;
      setMessage(
        `Generated DeepSeek copy for ${generatedCount} platform(s)${
          errorCount ? `; ${errorCount} platform(s) need manual copy` : ""
        }.`
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Platform copy generation is unavailable right now.");
    } finally {
      setGeneratingPlatformCopy(false);
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
            timezone: overridePayload?.timezone ?? null,
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
          timezone: overridePayload?.timezone ?? null,
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

  const handleSchedulePosts = async () => {
    await handleCreatePublishJobs();
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
    () => providers.some((provider) => provider.setup_status === "ready" && provider.capabilities?.supports_publish_now),
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
    <>
    <div id="publish-social" className="scroll-mt-6 space-y-2 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-[var(--app-text)]">Publish to Social</h3>
          <p className="mt-0.5 text-[11px] text-[var(--app-muted)]">
            Publish from a ready export. One publish job is created per selected platform/account.
          </p>
        </div>
        <Link
          href="/connections"
          className="rounded-md border border-[var(--app-border)] px-2.5 py-1.5 text-xs text-[#1D3FD0] hover:bg-[var(--app-surface-soft)] hover:text-[#1633B8]"
        >
          Manage Connections
        </Link>
      </div>

      {message ? <p className="text-xs text-emerald-700">{message}</p> : null}
      {error ? <p className="text-xs text-red-700">{error}</p> : null}

      {loadingMeta ? (
        <p className="inline-flex items-center gap-2 text-xs text-[var(--app-muted)]">
          <LoadingSpinner size="sm" />
          Loading social providers...
        </p>
      ) : null}

      <div className="grid gap-2 rounded-md border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-2.5 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
        <label className="text-xs text-[var(--app-muted)]">
          Ready Export Asset
          <select
            value={selectedExportId}
            onChange={(event) => setSelectedExportId(event.target.value)}
            className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-white px-2.5 py-1.5 text-sm text-[var(--app-text)] focus:border-[#1D3FD0] focus:outline-none"
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
          <p className="mt-2 text-xs text-[var(--app-subtle)]">
            Create and wait for a ready export before publishing.
          </p>
        ) : null}
        <button
          type="button"
          onClick={() => setShowUniversalEditor((current) => !current)}
          className="rounded-md border border-[var(--app-border)] bg-white px-3 py-1.5 text-xs font-medium text-[var(--app-text)] hover:bg-[var(--app-surface)]"
        >
          {showUniversalEditor ? "Hide Content Fields" : "Edit Content & Schedule"}
        </button>
      </div>

      {showUniversalEditor ? (
      <div className="rounded-md border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-[var(--app-muted)]">Universal Content</h4>
          <div className="flex flex-wrap gap-1.5">
            <button
              type="button"
              onClick={() => void handleGenerateCopy()}
              disabled={generatingCopy}
              className="rounded-md border border-[var(--app-border)] bg-white px-2.5 py-1 text-xs font-medium text-[var(--app-text)] hover:bg-[var(--app-surface)] disabled:opacity-60"
            >
              {generatingCopy ? "Generating..." : "Generate Universal Copy"}
            </button>
            <button
              type="button"
              onClick={() => void handleGeneratePlatformCopy()}
              disabled={generatingPlatformCopy}
              className="rounded-md bg-[var(--app-primary)] px-2.5 py-1 text-xs font-medium text-white hover:bg-[var(--app-primary-hover)] disabled:opacity-60"
            >
              {generatingPlatformCopy ? "Generating..." : "Generate Platform Copy"}
            </button>
          </div>
        </div>
        <p className="mt-1 text-[11px] text-[var(--app-subtle)]">
          Universal fields apply unless a platform override is enabled.
        </p>
        <div className="mt-2">
          <button
            type="button"
            onClick={() => setShowCopyInstructions((current) => !current)}
            className="inline-flex items-center gap-1 text-xs text-[var(--app-muted)] transition-colors hover:text-[#1D3FD0]"
          >
            <span>{showCopyInstructions ? "▾" : "▸"}</span>
            Add instructions
          </button>
          {showCopyInstructions ? (
            <div className="mt-2">
              <textarea
                value={copyInstructions}
                onChange={(event) => setCopyInstructions(event.target.value.slice(0, 500))}
                placeholder="Tell the AI how to write it. Example: keep it casual, focus on the technique, or make it sound more urgent."
                rows={3}
                className="w-full resize-none rounded-md border border-[var(--app-border)] bg-white px-2.5 py-1.5 text-sm text-[var(--app-text)] placeholder:text-[var(--app-subtle)] focus:border-[#1D3FD0] focus:outline-none"
              />
              <p className="mt-0.5 text-right text-[11px] text-[var(--app-subtle)]">
                {copyInstructions.length}/500
              </p>
            </div>
          ) : null}
        </div>
        {copyOptions ? (
          <div className="mt-2">
            <p className="text-[11px] text-[var(--app-subtle)]">
              Regenerate the universal options for a specific platform:
            </p>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {COPY_REGEN_PLATFORMS.map((platform) => (
                <button
                  key={`copy-regenerate-${platform}`}
                  type="button"
                  onClick={() => void handleGenerateCopy(platform)}
                  disabled={generatingCopy}
                  className="rounded-md border border-[var(--app-border)] bg-white px-2.5 py-1 text-[11px] font-medium capitalize text-[var(--app-text)] hover:border-[#1D3FD0]/50 hover:bg-[#1D3FD0]/5 disabled:opacity-60"
                >
                  {generatingCopyPlatform === platform ? "..." : platform}
                </button>
              ))}
            </div>
          </div>
        ) : null}
        <div className="mt-2 grid gap-2 md:grid-cols-2">
          <label className="text-xs text-[var(--app-muted)]">
            Title
            <input
              value={universalFields.title}
              onChange={(event) => setUniversalFields((prev) => ({ ...prev, title: event.target.value }))}
              className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-white px-2.5 py-1.5 text-sm text-[var(--app-text)] focus:border-[#1D3FD0] focus:outline-none"
            />
          </label>
          <div className="text-xs text-[var(--app-muted)]">
            YouTube Privacy (default)
            <div className="mt-1 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setUniversalFields((prev) => ({ ...prev, privacy: "" }))}
                className={`rounded-full border px-3 py-1 text-xs ${
                  !universalFields.privacy
                    ? "border-[#1D3FD0] bg-[#1D3FD0]/20 text-[#1633B8]"
                    : "border-[var(--app-border)] text-[var(--app-muted)] hover:bg-[var(--app-surface-soft)]"
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
                      ? "border-[#1D3FD0] bg-[#1D3FD0]/20 text-[#1633B8]"
                      : "border-[var(--app-border)] text-[var(--app-muted)] hover:bg-[var(--app-surface-soft)]"
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <p className="mt-1 text-[11px] text-[var(--app-subtle)]">
              Applied only to providers that support privacy controls.
            </p>
          </div>
          <label className="text-xs text-[var(--app-muted)] md:col-span-2">
            Caption
            <textarea
              value={universalFields.caption}
              onChange={(event) => setUniversalFields((prev) => ({ ...prev, caption: event.target.value }))}
              rows={2}
              className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-white px-2.5 py-1.5 text-sm text-[var(--app-text)] focus:border-[#1D3FD0] focus:outline-none"
            />
          </label>
          <label className="text-xs text-[var(--app-muted)] md:col-span-2">
            Description
            <textarea
              value={universalFields.description}
              onChange={(event) => setUniversalFields((prev) => ({ ...prev, description: event.target.value }))}
              rows={2}
              className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-white px-2.5 py-1.5 text-sm text-[var(--app-text)] focus:border-[#1D3FD0] focus:outline-none"
            />
          </label>
          <label className="text-xs text-[var(--app-muted)]">
            Hashtags
            <input
              value={universalFields.hashtags}
              onChange={(event) => setUniversalFields((prev) => ({ ...prev, hashtags: event.target.value }))}
              placeholder="#postbandit #podcast"
              className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-white px-2.5 py-1.5 text-sm text-[var(--app-text)] focus:border-[#1D3FD0] focus:outline-none"
            />
          </label>
          <div className="text-xs text-[var(--app-muted)]">
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
        {copyOptions ? (
          <div className="mt-3 grid gap-2 md:grid-cols-2">
            <CopyOptionSelect
              label="Title"
              options={copyOptions.titles}
              currentValue={universalFields.title}
              onSelect={(value) => setUniversalFields((prev) => ({ ...prev, title: value }))}
            />
            <CopyOptionSelect
              label="Caption"
              options={copyOptions.captions}
              currentValue={universalFields.caption}
              onSelect={(value) => setUniversalFields((prev) => ({ ...prev, caption: value }))}
            />
            <CopyOptionSelect
              label="Description"
              options={copyOptions.descriptions}
              currentValue={universalFields.description}
              onSelect={(value) => setUniversalFields((prev) => ({ ...prev, description: value }))}
            />
            <CopyOptionSelect
              label="Hashtags"
              options={copyOptions.hashtag_sets}
              currentValue={universalFields.hashtags}
              onSelect={(value) => setUniversalFields((prev) => ({ ...prev, hashtags: value }))}
              isHashtags
            />
          </div>
        ) : null}
      </div>
      ) : null}

      <div className="grid gap-1.5 lg:grid-cols-2 2xl:grid-cols-3">
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
          const brand = getPlatformBrandMeta(platform);
          const selectedAccount = selectableAccounts.find(
            (account) => account.id === draft?.connected_account_id
          );
          const latestJob = latestJobsByPlatform.get(platform);
          const providerName = provider?.display_name || brand.displayName;
          const providerReady = provider?.setup_status === "ready";
          const providerSupportsSchedule = Boolean(providerReady && provider?.capabilities?.supports_publish_now);
          const hasConnectedAccounts = selectableAccounts.length > 0;
          const privacyOptions = privacyOptionsForTarget(platform, selectedAccount);
          const reconnectRequired = isReconnectRequiredPublishJob(latestJob);
          const safeErrorMessage = latestJob ? safePublishErrorMessage(latestJob) : null;
          const providerSetupDetails = (provider?.setup_details || {}) as Record<string, unknown>;
          const threadsSupportsMedia = Boolean(provider?.capabilities?.supports_video_upload);
          const threadsPublishTextReady = Boolean(providerSetupDetails.publish_text_ready);
          const threadsPublishMediaReady = Boolean(providerSetupDetails.publish_media_ready);
          const tiktokDirectReady = Boolean(providerSetupDetails.publish_direct_ready);
          const tiktokUploadReady = Boolean(providerSetupDetails.publish_upload_ready);
          const showOverrideEditor = Boolean(draft?.use_override || (platform === "tiktok" && draft?.enabled));

          return (
            <div key={platform} className="rounded-md border border-[var(--app-border)] bg-white p-2 shadow-[0_1px_2px_rgba(9,21,40,0.04)]">
              <div className="flex items-center justify-between gap-2">
                <label className="inline-flex min-w-0 items-center gap-1.5 text-xs text-[var(--app-text)]">
                  <span
                    className={`inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-md [&_svg]:h-3.5 [&_svg]:w-3.5 ${brand.baseClassName}`}
                    aria-hidden="true"
                  >
                    {brand.icon}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate font-semibold">{providerName}</span>
                    <span className="block text-[10px] font-normal text-[var(--app-subtle)]">
                      {hasConnectedAccounts
                        ? `${selectableAccounts.length} connected`
                        : providerReady
                        ? "Not connected"
                        : "Setup required"}
                    </span>
                  </span>
                </label>
                <div className="flex shrink-0 items-center gap-2">
                  <input
                    type="checkbox"
                    checked={draft?.enabled || false}
                    disabled={!providerReady || !hasConnectedAccounts}
                    onChange={(event) => handlePlatformToggle(platform, event.target.checked)}
                    aria-label={`Publish to ${providerName}`}
                    className="h-3.5 w-3.5 rounded border-[var(--app-border)] bg-white text-[#1D3FD0] focus:ring-[#1D3FD0]"
                  />
                {latestJob ? (
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${statusStyles[latestJob.status]}`}>
                    {prettyStatus(latestJob.status)}
                  </span>
                ) : (
                  <span className="rounded-full bg-[var(--app-surface-soft)] px-2 py-0.5 text-[10px] text-[var(--app-muted)]">No jobs</span>
                )}
                </div>
              </div>

              <p className="mt-1 text-[10px] leading-4 text-[var(--app-muted)]">
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
                <p className="mt-0.5 text-[10px] leading-4 text-[var(--app-subtle)]">
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
                <p className="mt-0.5 text-[10px] leading-4 text-[var(--app-subtle)]">
                  Facebook Pages support automated publishing. Personal profile sharing is manual.
                </p>
              ) : null}
              {platform === "tiktok" ? (
                <p className="mt-0.5 text-[10px] leading-4 text-[var(--app-subtle)]">
                  {tiktokDirectReady
                    ? "TikTok direct post is enabled. If direct post is blocked at runtime, PostBandit falls back to TikTok inbox upload."
                    : tiktokUploadReady
                      ? "TikTok direct post is unavailable right now; inbox upload fallback will be used."
                      : "Connect TikTok and complete app setup to enable publish."}
                </p>
              ) : null}

              <div className="mt-1.5 grid gap-1.5 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
                <label className="text-[11px] text-[var(--app-muted)]">
                  {platform === "facebook" ? "Page Destination" : "Account"}
                  <select
                    value={draft?.connected_account_id || ""}
                    onChange={(event) => handlePlatformAccountChange(platform, event.target.value)}
                    disabled={!hasConnectedAccounts}
                    className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-white px-2 py-1 text-[11px] text-[var(--app-text)] focus:border-[#1D3FD0] focus:outline-none disabled:opacity-50"
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
                  <p className="inline-flex items-center text-[10px] text-[var(--app-muted)]">
                    Enable to choose TikTok privacy.
                  </p>
                ) : (
                  <label className="inline-flex items-center gap-1.5 text-[11px] text-[var(--app-muted)]">
                    <input
                      type="checkbox"
                      checked={draft?.use_override || false}
                      onChange={(event) => handleOverrideToggle(platform, event.target.checked)}
                      className="h-3.5 w-3.5 rounded border-[var(--app-border)] bg-white text-[#1D3FD0] focus:ring-[#1D3FD0]"
                    />
                    Use per-platform overrides
                  </label>
                )}
              </div>

              {showOverrideEditor ? (
                <div className="mt-2 grid gap-2 rounded-md border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-2 sm:grid-cols-2">
                  <label className="text-xs text-[var(--app-muted)]">
                    Title
                    <input
                      value={draft.override.title}
                      onChange={(event) => handleOverrideFieldChange(platform, "title", event.target.value)}
                      className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-white px-2 py-1.5 text-xs text-[var(--app-text)] focus:border-[#1D3FD0] focus:outline-none"
                    />
                    {PLATFORM_COPY_LIMITS[platform]?.title ? (
                      <span className={`mt-0.5 block text-right text-[10px] ${characterCounterClass(
                        draft.override.title.length,
                        PLATFORM_COPY_LIMITS[platform]?.title as number
                      )}`}>
                        {draft.override.title.length}/{PLATFORM_COPY_LIMITS[platform]?.title}
                      </span>
                    ) : null}
                  </label>
                  <label className="text-xs text-[var(--app-muted)]">
                    Privacy
                    {privacyOptions.length ? (
                      <div className="mt-1 flex flex-wrap gap-2">
                        {platform !== "tiktok" ? (
                          <button
                            type="button"
                            onClick={() => handleOverrideFieldChange(platform, "privacy", "")}
                            className={`rounded-full border px-3 py-1 text-xs ${
                              !draft.override.privacy
                                ? "border-[#1D3FD0] bg-[#1D3FD0]/20 text-[#1633B8]"
                                : "border-[var(--app-border)] text-[var(--app-muted)] hover:bg-[var(--app-surface-soft)]"
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
                                ? "border-[#1D3FD0] bg-[#1D3FD0]/20 text-[#1633B8]"
                                : "border-[var(--app-border)] text-[var(--app-muted)] hover:bg-[var(--app-surface-soft)]"
                            }`}
                          >
                            {privacyLabelForValue(platform, option.value)}
                          </button>
                        ))}
                      </div>
                    ) : (
                      <p className="mt-1 text-[11px] text-[var(--app-subtle)]">Privacy is not configurable for this provider.</p>
                    )}
                    {platform === "tiktok" ? (
                      <p className="mt-1 text-[11px] text-[var(--app-subtle)]">
                        Required by TikTok. Select one option returned for the connected TikTok account.
                      </p>
                    ) : null}
                  </label>
                  <label className="text-xs text-[var(--app-muted)] md:col-span-2">
                    Caption
                    <textarea
                      value={draft.override.caption}
                      onChange={(event) => handleOverrideFieldChange(platform, "caption", event.target.value)}
                      rows={2}
                      className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-white px-2 py-1.5 text-xs text-[var(--app-text)] focus:border-[#1D3FD0] focus:outline-none"
                    />
                    {PLATFORM_COPY_LIMITS[platform]?.caption ? (
                      <span className={`mt-0.5 block text-right text-[10px] ${characterCounterClass(
                        draft.override.caption.length,
                        PLATFORM_COPY_LIMITS[platform]?.caption as number
                      )}`}>
                        {draft.override.caption.length}/{PLATFORM_COPY_LIMITS[platform]?.caption}
                      </span>
                    ) : null}
                  </label>
                  <label className="text-xs text-[var(--app-muted)] md:col-span-2">
                    Description
                    <textarea
                      value={draft.override.description}
                      onChange={(event) => handleOverrideFieldChange(platform, "description", event.target.value)}
                      rows={2}
                      className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-white px-2 py-1.5 text-xs text-[var(--app-text)] focus:border-[#1D3FD0] focus:outline-none"
                    />
                    {PLATFORM_COPY_LIMITS[platform]?.description ? (
                      <span className={`mt-0.5 block text-right text-[10px] ${characterCounterClass(
                        draft.override.description.length,
                        PLATFORM_COPY_LIMITS[platform]?.description as number
                      )}`}>
                        {draft.override.description.length}/{PLATFORM_COPY_LIMITS[platform]?.description}
                      </span>
                    ) : null}
                  </label>
                  <label className="text-xs text-[var(--app-muted)]">
                    Hashtags
                    <input
                      value={draft.override.hashtags}
                      onChange={(event) => handleOverrideFieldChange(platform, "hashtags", event.target.value)}
                      className="mt-1 w-full rounded-md border border-[var(--app-border)] bg-white px-2 py-1.5 text-xs text-[var(--app-text)] focus:border-[#1D3FD0] focus:outline-none"
                    />
                  </label>
                  <div className="text-xs text-[var(--app-muted)]">
                    Schedule Time
                    <SchedulePicker
                      value={draft.override.scheduled_for}
                      onChange={(next) => handleOverrideFieldChange(platform, "scheduled_for", next)}
                      disabled={!providerSupportsSchedule}
                      disabledReason={providerSupportsSchedule ? undefined : "Publishing is unavailable for this provider."}
                    />
                  </div>
                </div>
              ) : null}

              {safeErrorMessage ? <p className="mt-2 text-[11px] text-red-700">{safeErrorMessage}</p> : null}
              {platform === "facebook" ? (
                <div className="mt-2 flex flex-wrap items-center justify-between gap-2 rounded-md border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-2">
                  <div>
                    <p className="text-[11px] font-medium text-[var(--app-text)]">Personal profile sharing</p>
                    <p className="text-[10px] text-[var(--app-subtle)]">Manual share; no publish job is created.</p>
                  </div>
                  <button
                    type="button"
                    onClick={openFacebookManualShare}
                    disabled={!selectedExportId}
                    className="inline-flex rounded-md border border-[var(--app-border)] bg-white px-2.5 py-1 text-[11px] text-[var(--app-text)] hover:bg-[var(--app-surface)] disabled:opacity-60"
                  >
                    Share manually
                  </button>
                </div>
              ) : null}
              {platform === "x" && reconnectRequired ? (
                <p className="mt-1 text-[11px] text-amber-700">
                  Reconnect X in{" "}
                  <Link href="/connections" className="underline hover:text-amber-800">
                    Connections
                  </Link>{" "}
                  to grant media permissions, then publish again.
                </p>
              ) : null}
              {platform === "x" && latestJob?.error_message && !reconnectRequired ? (
                <p className="mt-1 text-[11px] text-amber-700">
                  X media posting can fail due to account-tier limits, provider credits, or media policy restrictions.
                </p>
              ) : null}
              {platform === "tiktok" && latestJob?.status === "waiting_user_action" ? (
                <p className="mt-1 text-[11px] text-amber-700">
                  TikTok may require you to finish posting in the TikTok app inbox, or to complete app review/setup for direct post.
                </p>
              ) : null}
              {latestJob?.external_post_url ? (
                <a
                  href={latestJob.external_post_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-3 inline-flex text-xs text-[#1D3FD0] hover:text-[#1633B8]"
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
                  className="mt-3 inline-flex rounded-md border border-[var(--app-border)] px-3 py-1.5 text-xs text-[var(--app-text)] hover:bg-[var(--app-surface-soft)] disabled:opacity-60"
                >
                  {retryingJobId === latestJob.id ? "Retrying..." : "Retry"}
                </button>
              ) : null}
            </div>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => void handleCreatePublishJobs()}
          disabled={publishing || !selectedExportId || !readyExports.length}
          className="rounded-md bg-[#1D3FD0] px-3.5 py-1.5 text-sm font-medium text-white hover:bg-[#1633B8] disabled:opacity-60"
        >
          {publishing ? "Publishing..." : "Publish Selected Platforms"}
        </button>
        <button
          type="button"
          onClick={() => setShowScheduleConfirm(true)}
          disabled={publishing || selectedPlatforms.length === 0 || !selectedExportId || !readyExports.length}
          className="rounded-md border border-[#1D3FD0] px-3 py-1.5 text-sm font-medium text-[#1D3FD0] transition-colors hover:bg-[#1D3FD0]/5 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Schedule Posts
        </button>
        <button
          type="button"
          onClick={() => void loadPublishJobs(selectedExportId)}
          disabled={loadingJobs || !selectedExportId}
          className="rounded-md border border-[var(--app-border)] px-3 py-1.5 text-sm text-[var(--app-text)] hover:bg-[var(--app-surface-soft)] disabled:opacity-60"
        >
          {loadingJobs ? "Refreshing..." : "Refresh Status"}
        </button>
      </div>

      {publishJobs.length ? (
        <div className="space-y-1.5 rounded-md border border-[var(--app-border)] bg-[var(--app-surface-soft)] p-2.5">
          <p className="text-xs font-semibold uppercase tracking-wide text-[var(--app-muted)]">Per-platform Publish Jobs</p>
          {publishJobs.map((job) => {
            const brand = getPlatformBrandMeta(job.platform);
            return (
              <div key={job.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-[var(--app-border)] bg-white px-2.5 py-1.5">
                <div className="flex min-w-0 items-center gap-2 text-xs text-[var(--app-muted)]">
                  <span
                    className={`inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md [&_svg]:h-3.5 [&_svg]:w-3.5 ${brand.baseClassName}`}
                    aria-hidden="true"
                  >
                    {brand.icon}
                  </span>
                  <span className="truncate">
                    <span className="font-medium">{providersByPlatform[job.platform]?.display_name || brand.displayName}</span>{" "}
                    • {job.id.slice(0, 8)}
                    {job.external_post_id ? ` • ${job.external_post_id}` : ""}
                  </span>
                </div>
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${statusStyles[job.status]}`}>
                  {prettyStatus(job.status)}
                </span>
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
    {showScheduleConfirm ? (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
        <div className="mx-4 w-full max-w-sm rounded-xl bg-white p-5 shadow-xl">
          <h3 className="text-base font-semibold text-gray-900">Schedule posts</h3>
          <p className="mt-2 text-sm text-gray-600">We&apos;ll schedule this clip for:</p>
          <ul className="mt-3 space-y-1">
            {selectedPlatforms.map((platform) => {
              const brand = getPlatformBrandMeta(platform);
              return (
                <li key={platform} className="flex items-center gap-2 text-sm text-gray-700">
                  <span className="h-2 w-2 rounded-full bg-[#1D3FD0]" />
                  <span>{brand.displayName}</span>
                </li>
              );
            })}
          </ul>
          {scheduleConfirmTime ? (
            <p className="mt-3 text-xs text-gray-500">
              Scheduled for: {formatScheduleLabel(scheduleConfirmTime)}
            </p>
          ) : (
            <p className="mt-3 text-xs text-amber-700">
              No schedule time is set. Confirming will create publish jobs with the current timing fields.
            </p>
          )}
          <div className="mt-5 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setShowScheduleConfirm(false)}
              className="px-3 py-1.5 text-sm text-gray-600 transition-colors hover:text-gray-900"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={async () => {
                setShowScheduleConfirm(false);
                await handleSchedulePosts();
              }}
              disabled={publishing}
              className="rounded-lg bg-[#1D3FD0] px-4 py-1.5 text-sm font-semibold text-white transition-colors hover:bg-[#1633B8] disabled:opacity-60"
            >
              Confirm
            </button>
          </div>
        </div>
      </div>
    ) : null}
    </>
  );
}
