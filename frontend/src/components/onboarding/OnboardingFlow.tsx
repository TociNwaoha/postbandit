"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { getPlatformBrandMeta } from "@/components/connections/platformBrand";
import { Button } from "@/components/ui/Button";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { api, ApiError } from "@/lib/api";
import {
  BrandProfile,
  ConnectedAccount,
  OnboardingRole,
  OnboardingStatus,
  SocialProvider,
  UserTier,
} from "@/types";

type OnboardingStep = "start" | "connect" | "brand" | "plans" | "thank-you";

type RoleOption = {
  id: OnboardingRole;
  title: string;
  description: string;
};

type PlanOption = {
  id: UserTier;
  title: string;
  price: string;
  description: string;
  badge?: string;
  features: string[];
};

interface OnboardingFlowProps {
  step: OnboardingStep;
}

const stepOrder: OnboardingStep[] = ["start", "connect", "brand", "plans"];

const stepMeta: Record<OnboardingStep, { index: number; eyebrow: string; title: string; subtitle: string }> = {
  start: {
    index: 1,
    eyebrow: "Step 1",
    title: "What best describes you?",
    subtitle: "PostBandit will tailor the first-run experience around how you publish.",
  },
  connect: {
    index: 2,
    eyebrow: "Step 2",
    title: "Connect your accounts",
    subtitle: "Connect now or skip. You can always add accounts later from Connections.",
  },
  brand: {
    index: 3,
    eyebrow: "Step 3",
    title: "Set your brand basics",
    subtitle: "This helps AI copy, carousels, and content queue drafts match your voice.",
  },
  plans: {
    index: 4,
    eyebrow: "Step 4",
    title: "Choose your starting plan",
    subtitle: "No payment is collected here. Billing will be added later.",
  },
  "thank-you": {
    index: 4,
    eyebrow: "All set",
    title: "Your workspace is ready",
    subtitle: "Start importing videos, creating clips, and publishing from one place.",
  },
};

const roleOptions: RoleOption[] = [
  { id: "creator", title: "Creator", description: "Growing an audience across social platforms" },
  { id: "founder", title: "Founder / Business", description: "Building a brand, business, or offer" },
  { id: "agency", title: "Agency", description: "Managing content for clients or multiple brands" },
  { id: "team", title: "Team / Enterprise", description: "Coordinating a larger publishing workflow" },
];

const planOptions: PlanOption[] = [
  {
    id: "starter",
    title: "Starter",
    price: "$9/mo",
    description: "For testing a simple repurposing workflow.",
    features: ["5 video imports / month", "20 AI clips / month", "Connect up to 3 platforms"],
  },
  {
    id: "creator",
    title: "Creator",
    price: "$29/mo",
    description: "For active creators publishing every week.",
    badge: "Recommended",
    features: ["25 video imports / month", "100 AI clips / month", "Scheduling and auto-posting"],
  },
  {
    id: "agency",
    title: "Agency",
    price: "$59/mo",
    description: "For teams and agencies managing multiple brands.",
    features: ["Unlimited video imports", "Multiple brand workflows", "Priority support"],
  },
];

const platformOptions = ["instagram", "threads", "linkedin", "tiktok", "youtube", "x"];

function PostBanditLogo() {
  return (
    <Link href="/dashboard" className="flex items-center gap-3 text-[#091528]">
      <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#1D3FD0] shadow-sm">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M5 3L19 12L5 21V3Z" fill="white" />
        </svg>
      </span>
      <span className="app-display text-xl font-extrabold tracking-tight">PostBandit</span>
    </Link>
  );
}

function Progress({ activeStep }: { activeStep: number }) {
  return (
    <div className="flex items-center justify-center gap-3 sm:gap-5">
      {[1, 2, 3, 4].map((step, index) => {
        const active = step <= activeStep;
        return (
          <div key={step} className="flex items-center gap-3 sm:gap-5">
            <span
              className={`flex h-10 w-10 items-center justify-center rounded-full text-sm font-bold transition ${
                active ? "bg-[#1D3FD0] text-white shadow-[0_8px_24px_rgba(29,63,208,0.25)]" : "bg-[#E1E8F5] text-[#7A94B0]"
              }`}
            >
              {step}
            </span>
            {index < 3 ? <span className={`h-0.5 w-12 sm:w-20 ${active ? "bg-[#1D3FD0]" : "bg-[#D6E2F5]"}`} /> : null}
          </div>
        );
      })}
    </div>
  );
}

function Shell({
  step,
  children,
  onBack,
  onNext,
  nextLabel = "Next",
  nextDisabled = false,
  nextLoading = false,
  hideActions = false,
}: {
  step: OnboardingStep;
  children: React.ReactNode;
  onBack?: () => void;
  onNext?: () => void;
  nextLabel?: string;
  nextDisabled?: boolean;
  nextLoading?: boolean;
  hideActions?: boolean;
}) {
  const router = useRouter();
  const meta = stepMeta[step];

  async function skip() {
    await api.post<OnboardingStatus>("/api/onboarding/skip", {});
    router.push("/dashboard");
    router.refresh();
  }

  return (
    <main className="min-h-[100dvh] bg-[linear-gradient(180deg,#F4F8FF_0%,#EAF1FF_52%,#FFFFFF_100%)] text-[#091528]">
      <header className="border-b border-[#D6E2F5] bg-white/88 backdrop-blur">
        <div className="mx-auto grid max-w-[1240px] grid-cols-1 items-center gap-5 px-6 py-5 md:grid-cols-[1fr_1.4fr_1fr]">
          <PostBanditLogo />
          <Progress activeStep={meta.index} />
          <div className="flex justify-start md:justify-end">
            <button
              type="button"
              onClick={() => void skip()}
              className="rounded-full border border-[#D6E2F5] bg-white px-4 py-2 text-sm font-semibold text-[#4A6080] transition hover:border-[#1D3FD0]/40 hover:text-[#1D3FD0]"
            >
              Skip for now
            </button>
          </div>
        </div>
      </header>

      <section className="mx-auto max-w-[980px] px-5 pb-28 pt-14 sm:pt-16">
        {step !== "thank-you" ? (
          <div className="mb-9 text-center">
            <p className="text-sm font-bold uppercase tracking-[0.16em] text-[#1D3FD0]">{meta.eyebrow}</p>
            <h1 className="app-display mt-3 text-4xl font-extrabold tracking-[-0.035em] text-[#091528] sm:text-5xl">
              {meta.title}
            </h1>
            <p className="mx-auto mt-3 max-w-2xl text-base leading-7 text-[#4A6080]">{meta.subtitle}</p>
          </div>
        ) : null}

        {children}
      </section>

      {!hideActions ? (
        <footer className="fixed inset-x-0 bottom-0 z-20 border-t border-[#D6E2F5] bg-white/94 px-5 py-4 shadow-[0_-10px_35px_rgba(9,21,40,0.08)] backdrop-blur">
          <div className="mx-auto flex max-w-[1240px] items-center justify-between gap-4">
            <Button type="button" variant="ghost" size="lg" onClick={onBack} disabled={!onBack || nextLoading}>
              Back
            </Button>
            <Button type="button" size="lg" onClick={onNext} disabled={nextDisabled} loading={nextLoading} className="min-w-32">
              {nextLabel}
            </Button>
          </div>
        </footer>
      ) : null}
    </main>
  );
}

function RoleStep({ selected, onSelect }: { selected: OnboardingRole | null; onSelect: (value: OnboardingRole) => void }) {
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      {roleOptions.map((role) => {
        const active = selected === role.id;
        return (
          <button
            key={role.id}
            type="button"
            onClick={() => onSelect(role.id)}
            className={`group flex w-full items-center gap-5 rounded-2xl border px-6 py-5 text-left shadow-sm transition ${
              active
                ? "border-[#1D3FD0] bg-[#1D3FD0] text-white shadow-[0_18px_50px_rgba(29,63,208,0.22)]"
                : "border-[#D6E2F5] bg-white text-[#091528] hover:border-[#9DB5FF] hover:bg-[#F8FAFF]"
            }`}
          >
            <span
              className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full border-2 ${
                active ? "border-white bg-white/18 text-white" : "border-[#D6E2F5] bg-white text-transparent group-hover:border-[#9DB5FF]"
              }`}
            >
              <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                <path d="M4.5 10.4 8.2 14l7.3-8" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
            <span>
              <span className="block text-xl font-bold">{role.title}</span>
              <span className={`mt-1 block text-sm ${active ? "text-white/80" : "text-[#6A7C99]"}`}>{role.description}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

function ConnectStep() {
  const [providers, setProviders] = useState<SocialProvider[]>([]);
  const [accounts, setAccounts] = useState<ConnectedAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [providerRows, accountRows] = await Promise.all([
          api.get<SocialProvider[]>("/api/social/providers"),
          api.get<ConnectedAccount[]>("/api/social/accounts"),
        ]);
        if (!active) return;
        setProviders(providerRows);
        setAccounts(accountRows);
      } catch (err) {
        if (!active) return;
        setError(err instanceof ApiError ? err.message : "Failed to load providers");
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, []);

  const connectedCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const account of accounts) counts[account.platform] = (counts[account.platform] || 0) + 1;
    return counts;
  }, [accounts]);

  async function connect(platform: string) {
    setConnecting(platform);
    setError(null);
    try {
      const data = await api.post<{ authorization_url: string }>(`/api/social/${platform}/connect`, {
        return_to: "/onboarding/connect",
      });
      window.location.href = data.authorization_url;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to start connection");
      setConnecting(null);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-3 rounded-3xl border border-[#D6E2F5] bg-white p-10 text-[#4A6080]">
        <LoadingSpinner size="sm" /> Loading connection options...
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl rounded-3xl border border-[#D6E2F5] bg-white p-5 shadow-[0_22px_70px_rgba(9,21,40,0.08)] sm:p-7">
      {error ? <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div> : null}
      <div className="grid gap-3 sm:grid-cols-2">
        {providers.map((provider) => {
          const brand = getPlatformBrandMeta(provider.platform);
          const ready = provider.setup_status === "ready";
          const count = connectedCounts[provider.platform] || provider.connected_account_count || 0;
          return (
            <button
              key={provider.platform}
              type="button"
              onClick={() => void connect(provider.platform)}
              disabled={!ready || connecting === provider.platform}
              className={`flex items-center justify-between gap-4 rounded-2xl px-4 py-3 text-left text-sm font-semibold transition ${
                ready ? brand.baseClassName : brand.disabledClassName
              } ${!ready ? "cursor-not-allowed opacity-75" : ""}`}
            >
              <span className="flex min-w-0 items-center gap-3">
                {brand.icon}
                <span className="truncate">{connecting === provider.platform ? `Connecting ${brand.displayName}...` : brand.buttonLabel}</span>
              </span>
              <span className="rounded-full bg-white/20 px-2 py-1 text-xs">{count}</span>
            </button>
          );
        })}
      </div>
      <p className="mt-5 text-center text-sm text-[#6A7C99]">
        Connected accounts can publish from clips, workflows, and scheduled calendar posts.
      </p>
    </div>
  );
}

function BrandStep({ status }: { status: OnboardingStatus | null }) {
  const [displayName, setDisplayName] = useState("");
  const [handle, setHandle] = useState("");
  const [niche, setNiche] = useState("");
  const [targetAudience, setTargetAudience] = useState("");
  const [tone, setTone] = useState("casual");
  const [preferredPlatforms, setPreferredPlatforms] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const profile = await api.get<BrandProfile>("/api/brand-profile");
        if (!active) return;
        setDisplayName(profile.display_name || "");
        setHandle(profile.handle || "");
        setNiche(profile.niche || "");
        setTargetAudience(profile.target_audience || "");
        setTone(profile.tone || "casual");
        setPreferredPlatforms(profile.preferred_platforms || []);
      } catch {
        const metadata = status?.metadata || {};
        setDisplayName(typeof metadata.display_name === "string" ? metadata.display_name : "");
        setHandle(typeof metadata.handle === "string" ? metadata.handle : "");
        setNiche(typeof metadata.niche === "string" ? metadata.niche : "");
        setTargetAudience(typeof metadata.target_audience === "string" ? metadata.target_audience : "");
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [status]);

  function togglePlatform(platform: string) {
    setPreferredPlatforms((current) =>
      current.includes(platform) ? current.filter((item) => item !== platform) : [...current, platform]
    );
    setSaved(false);
  }

  async function save() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const payload = {
        display_name: displayName.trim(),
        handle: handle.trim(),
        niche: niche.trim(),
        target_audience: targetAudience.trim(),
        tone,
        use_phrases: [],
        avoid_phrases: [],
        post_frequency: 1,
        preferred_platforms: preferredPlatforms,
      };
      await api.post<BrandProfile>("/api/brand-profile", payload);
      await api.patch<OnboardingStatus>("/api/onboarding/profile", {
        metadata: {
          ...(status?.metadata || {}),
          display_name: payload.display_name,
          handle: payload.handle,
          niche: payload.niche,
          target_audience: payload.target_audience,
          preferred_platforms: preferredPlatforms,
        },
      });
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save brand basics");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-3 rounded-3xl border border-[#D6E2F5] bg-white p-10 text-[#4A6080]">
        <LoadingSpinner size="sm" /> Loading brand basics...
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl rounded-3xl border border-[#D6E2F5] bg-white p-5 shadow-[0_22px_70px_rgba(9,21,40,0.08)] sm:p-7">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1.5 block text-sm font-semibold text-[#233252]">Brand or creator name</span>
          <input value={displayName} onChange={(event) => { setDisplayName(event.target.value); setSaved(false); }} className="w-full rounded-xl border border-[#D6E2F5] px-4 py-3 text-sm outline-none focus:border-[#1D3FD0] focus:ring-2 focus:ring-[#1D3FD0]/15" placeholder="PostBandit" />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-sm font-semibold text-[#233252]">Handle</span>
          <input value={handle} onChange={(event) => { setHandle(event.target.value); setSaved(false); }} className="w-full rounded-xl border border-[#D6E2F5] px-4 py-3 text-sm outline-none focus:border-[#1D3FD0] focus:ring-2 focus:ring-[#1D3FD0]/15" placeholder="@postbandit" />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-sm font-semibold text-[#233252]">Niche</span>
          <input value={niche} onChange={(event) => { setNiche(event.target.value); setSaved(false); }} className="w-full rounded-xl border border-[#D6E2F5] px-4 py-3 text-sm outline-none focus:border-[#1D3FD0] focus:ring-2 focus:ring-[#1D3FD0]/15" placeholder="Business coaching, sermons, sports clips..." />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-sm font-semibold text-[#233252]">Tone</span>
          <select value={tone} onChange={(event) => { setTone(event.target.value); setSaved(false); }} className="w-full rounded-xl border border-[#D6E2F5] px-4 py-3 text-sm outline-none focus:border-[#1D3FD0] focus:ring-2 focus:ring-[#1D3FD0]/15">
            <option value="casual">Casual</option>
            <option value="professional">Professional</option>
            <option value="edgy">Edgy</option>
            <option value="educational">Educational</option>
          </select>
        </label>
      </div>

      <label className="mt-4 block">
        <span className="mb-1.5 block text-sm font-semibold text-[#233252]">Target audience</span>
        <textarea value={targetAudience} onChange={(event) => { setTargetAudience(event.target.value); setSaved(false); }} rows={3} className="w-full rounded-xl border border-[#D6E2F5] px-4 py-3 text-sm outline-none focus:border-[#1D3FD0] focus:ring-2 focus:ring-[#1D3FD0]/15" placeholder="Creators, founders, local businesses, church members..." />
      </label>

      <div className="mt-5">
        <p className="text-sm font-semibold text-[#233252]">Preferred platforms</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {platformOptions.map((platform) => {
            const brand = getPlatformBrandMeta(platform);
            const active = preferredPlatforms.includes(platform);
            return (
              <button key={platform} type="button" onClick={() => togglePlatform(platform)} className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${active ? "border-[#1D3FD0] bg-[#1D3FD0] text-white" : "border-[#D6E2F5] bg-white text-[#4A6080] hover:border-[#9DB5FF]"}`}>
                {brand.displayName}
              </button>
            );
          })}
        </div>
      </div>

      {error ? <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div> : null}
      {saved ? <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">Brand basics saved.</div> : null}

      <div className="mt-6 flex justify-end">
        <Button type="button" onClick={() => void save()} loading={saving} disabled={!displayName.trim() || !handle.trim() || !niche.trim() || !targetAudience.trim()}>
          Save brand basics
        </Button>
      </div>
    </div>
  );
}

function PlanStep({ selected, onSelect }: { selected: UserTier; onSelect: (value: UserTier) => void }) {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      {planOptions.map((plan) => {
        const active = selected === plan.id;
        return (
          <button
            key={plan.id}
            type="button"
            onClick={() => onSelect(plan.id)}
            className={`relative flex min-h-[410px] flex-col rounded-3xl border p-6 text-left shadow-sm transition ${
              active
                ? "border-[#1D3FD0] bg-white shadow-[0_22px_70px_rgba(29,63,208,0.16)] ring-2 ring-[#1D3FD0]/15"
                : "border-[#D6E2F5] bg-white hover:border-[#9DB5FF]"
            }`}
          >
            {plan.badge ? <span className="absolute right-5 top-5 rounded-full bg-[#E9EFFF] px-3 py-1 text-xs font-bold text-[#1D3FD0]">{plan.badge}</span> : null}
            <span className="text-xl font-extrabold text-[#091528]">{plan.title}</span>
            <span className="mt-5 text-4xl font-extrabold tracking-tight text-[#091528]">{plan.price}</span>
            <span className="mt-3 min-h-12 text-sm leading-6 text-[#5F708F]">{plan.description}</span>
            <span className="mt-5 h-px w-full bg-[#E3EAF8]" />
            <span className="mt-5 space-y-3">
              {plan.features.map((feature) => (
                <span key={feature} className="flex items-start gap-2 text-sm font-medium text-[#233252]">
                  <svg className="mt-0.5 h-4 w-4 shrink-0 text-[#1D3FD0]" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                    <path d="M4.5 10.6 8 14l7.5-8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  <span>{feature}</span>
                </span>
              ))}
            </span>
            <span className={`mt-auto rounded-xl px-4 py-3 text-center text-sm font-bold ${active ? "bg-[#1D3FD0] text-white" : "bg-[#F4F8FF] text-[#1D3FD0]"}`}>
              {active ? "Selected" : "Choose plan"}
            </span>
          </button>
        );
      })}
      <p className="lg:col-span-3 text-center text-sm text-[#6A7C99]">
        This is onboarding only. No payment is collected and no subscription is activated here.
      </p>
    </div>
  );
}

function ThankYouStep() {
  return (
    <main className="min-h-[100dvh] bg-[radial-gradient(circle_at_top,#E8EEFF_0%,#F8FAFF_45%,#FFFFFF_100%)] px-5 py-10 text-[#091528]">
      <div className="mx-auto flex min-h-[calc(100dvh-5rem)] max-w-4xl flex-col items-center justify-center">
        <PostBanditLogo />
        <div className="mt-12 w-full max-w-2xl rounded-[2rem] border border-[#CFE0FF] bg-white p-8 text-center shadow-[0_24px_90px_rgba(9,21,40,0.10)] sm:p-12">
          <div className="mx-auto flex h-24 w-24 items-center justify-center rounded-full bg-[#E9EFFF] text-[#1D3FD0]">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M5 12.5 9.2 16.5 19 7" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <h1 className="app-display mt-8 text-5xl font-extrabold tracking-[-0.04em]">You are ready.</h1>
          <p className="mx-auto mt-4 max-w-md text-base leading-7 text-[#4A6080]">
            Your PostBandit workspace is set up. Import a video, build clips, or connect more destinations from the dashboard.
          </p>
          <Link href="/dashboard" className="mt-8 inline-flex w-full max-w-md items-center justify-center rounded-xl bg-[#1D3FD0] px-6 py-4 text-base font-bold text-white shadow-[0_14px_34px_rgba(29,63,208,0.25)] transition hover:bg-[#1633B8]">
            Go to dashboard {"->"}
          </Link>
        </div>
      </div>
    </main>
  );
}

export function OnboardingFlow({ step }: OnboardingFlowProps) {
  const router = useRouter();
  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [role, setRole] = useState<OnboardingRole | null>(null);
  const [tier, setTier] = useState<UserTier>("creator");
  const [loading, setLoading] = useState(step !== "thank-you");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (step === "thank-you") return;
    let active = true;
    async function load() {
      setLoading(true);
      try {
        const data = await api.get<OnboardingStatus>("/api/onboarding/status");
        if (!active) return;
        setStatus(data);
        setRole(data.role);
        setTier(data.tier || "creator");
      } catch (err) {
        if (active) setError(err instanceof ApiError ? err.message : "Failed to load onboarding status");
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [step]);

  function go(path: string) {
    router.push(path);
  }

  async function saveProfile(patch: Record<string, unknown>) {
    const nextMetadata = {
      ...(status?.metadata || {}),
      ...(typeof patch.metadata === "object" && patch.metadata !== null ? (patch.metadata as Record<string, unknown>) : {}),
    };
    const payload = { ...patch, metadata: nextMetadata };
    const data = await api.patch<OnboardingStatus>("/api/onboarding/profile", payload);
    setStatus(data);
    setRole(data.role);
    setTier(data.tier);
  }

  async function next() {
    setSaving(true);
    setError(null);
    try {
      if (step === "start") {
        if (!role) return;
        await saveProfile({ role, metadata: { role } });
        go("/onboarding/connect");
      } else if (step === "connect") {
        go("/onboarding/brand");
      } else if (step === "brand") {
        go("/onboarding/plans");
      } else if (step === "plans") {
        await saveProfile({ tier, metadata: { selected_plan: tier } });
        await api.post<OnboardingStatus>("/api/onboarding/complete", {});
        go("/onboarding/thank-you");
        router.refresh();
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save onboarding progress");
    } finally {
      setSaving(false);
    }
  }

  if (step === "thank-you") return <ThankYouStep />;

  const index = stepOrder.indexOf(step);
  const previousStep = index > 0 ? stepOrder[index - 1] : null;

  if (loading) {
    return (
      <Shell step={step} hideActions>
        <div className="flex items-center justify-center gap-3 rounded-3xl border border-[#D6E2F5] bg-white p-10 text-[#4A6080]">
          <LoadingSpinner size="sm" /> Loading onboarding...
        </div>
      </Shell>
    );
  }

  return (
    <Shell
      step={step}
      onBack={previousStep ? () => go(`/onboarding/${previousStep}`) : undefined}
      onNext={() => void next()}
      nextDisabled={(step === "start" && !role) || saving}
      nextLoading={saving}
      nextLabel={step === "plans" ? "Finish setup" : "Next"}
    >
      {error ? <div className="mx-auto mb-4 max-w-3xl rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div> : null}
      {step === "start" ? <RoleStep selected={role} onSelect={setRole} /> : null}
      {step === "connect" ? <ConnectStep /> : null}
      {step === "brand" ? <BrandStep status={status} /> : null}
      {step === "plans" ? <PlanStep selected={tier} onSelect={setTier} /> : null}
    </Shell>
  );
}
