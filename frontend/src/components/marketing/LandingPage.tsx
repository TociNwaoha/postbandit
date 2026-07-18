"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { MascotSection } from "@/components/landing/MascotSection";

type LandingPageProps = {
  displayClassName?: string;
  bodyClassName?: string;
};

type PlatformKey = "youtube" | "tiktok" | "instagram" | "x" | "threads";

type PlatformRow = {
  name: string;
  handle: string;
  key: PlatformKey;
};

const platformRows: PlatformRow[] = [
  { name: "YouTube Shorts", handle: "@postbandit", key: "youtube" },
  { name: "TikTok", handle: "@postbandit", key: "tiktok" },
  { name: "Instagram", handle: "@postbandit", key: "instagram" },
  { name: "X (Twitter)", handle: "@postbandit", key: "x" },
  { name: "Threads", handle: "@postbandit", key: "threads" },
];

const platformColors: Record<PlatformKey, string> = {
  youtube: "#FF0000",
  tiktok: "#161722",
  instagram: "#E1306C",
  x: "#0F1419",
  threads: "#161722",
};

const featureCards = [
  {
    tag: "Import",
    title: "Bring content in fast",
    body: "Upload your file or paste a YouTube link. PostBandit handles ingest, transcription, and prep automatically.",
    bullets: ["Direct upload + YouTube intake", "Transcript and metadata extraction", "Reliable processing status visibility"],
  },
  {
    tag: "Clip",
    title: "Find stronger moments",
    body: "AI scoring surfaces high-signal segments, then you can refine timing, captions, and framing in the editor.",
    bullets: ["Viral and Long-form Speaking profiles", "Clip score + timing confidence", "Manual trim and caption controls"],
  },
  {
    tag: "Publish",
    title: "Ship everywhere from one queue",
    body: "Connect your accounts once, then publish with platform-specific controls and transparent delivery outcomes.",
    bullets: ["Per-platform destination selection", "Scheduling + retries", "Published URL tracking and history"],
  },
];

const pricing = [
  {
    plan: "Creator",
    price: "$18",
    note: "/mo",
    desc: "For creators starting a repeatable video-to-social workflow.",
    items: [
      "7-day trial with card required",
      "Connect up to 5 platforms",
      "5GB included storage",
      "AI clips, captions, and platform copy",
      "Scheduling calendar and publish history",
    ],
    cta: "Get started",
    featured: false,
  },
  {
    plan: "Pro",
    price: "$49",
    note: "/mo",
    desc: "For active creators and teams publishing across more channels.",
    items: [
      "Connect up to 10 platforms",
      "25GB included storage",
      "Social repurpose workflows",
      "AI CMO carousel drafts",
      "Priority publishing queue",
    ],
    cta: "Try now for free",
    featured: true,
  },
  {
    plan: "Elite",
    price: "$250",
    note: "/mo",
    desc: "For serious operators managing high-volume content systems.",
    items: [
      "Every supported social platform",
      "100GB included storage",
      "Highest workflow limits",
      "Advanced automation and API access",
      "Priority human support",
    ],
    cta: "Get started",
    featured: false,
  },
];

const workflowDestinations = [
  { label: "TikTok", key: "tiktok" },
  { label: "X", key: "x" },
  { label: "Facebook", key: "facebook" },
  { label: "YouTube", key: "youtube" },
] as const;

function CheckIcon({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" aria-hidden className={className}>
      <path
        d="M4.5 10.6 8 14l7.5-8"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ArrowRightIcon({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" aria-hidden className={className}>
      <path
        d="M3 10h13m0 0-4-4m4 4-4 4"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function SpinnerIcon({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className={className}>
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2.5" />
      <path d="M12 3a9 9 0 0 1 9 9" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}

function StarIcon({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" aria-hidden className={className}>
      <path d="m10 1.8 2.57 5.2 5.75.83-4.16 4.05.98 5.72L10 14.88l-5.14 2.72.98-5.72L1.67 7.83l5.75-.83Z" />
    </svg>
  );
}

function PlatformIcon({ platform, className = "" }: { platform: string; className?: string }) {
  if (platform === "youtube") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden className={className}>
        <rect x="2.5" y="6" width="19" height="12" rx="3.5" fill="currentColor" />
        <path d="M10 9.2v5.6l5-2.8-5-2.8Z" fill="#fff" />
      </svg>
    );
  }

  if (platform === "instagram") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden className={className}>
        <rect x="4" y="4" width="16" height="16" rx="4.5" fill="none" stroke="currentColor" strokeWidth="2" />
        <circle cx="12" cy="12" r="3.6" fill="none" stroke="currentColor" strokeWidth="2" />
        <circle cx="17.2" cy="6.8" r="1.1" fill="currentColor" />
      </svg>
    );
  }

  if (platform === "x") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden className={className}>
        <path d="M4 4h4.8l4.2 5.7L18.4 4H20l-6.2 7.1L20.5 20h-4.8l-4.6-6.2L5.6 20H4l6.8-7.8L4 4Z" fill="currentColor" />
      </svg>
    );
  }

  if (platform === "threads") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden className={className}>
        <path
          d="M15.6 10.7c-.2-2.5-1.9-3.8-4.8-3.8-2.7 0-4.6 1.5-4.6 3.8 0 2 1.2 3.3 3.6 3.8l1.8.4c1 .2 1.4.6 1.4 1.2 0 .8-.8 1.4-2 1.4-1.3 0-2.2-.7-2.3-1.8H6.2c.2 2.5 2 4 5 4 3.1 0 5.2-1.6 5.2-4 0-1.9-1.1-3.2-3.5-3.7l-1.9-.4c-1-.2-1.4-.6-1.4-1.2 0-.7.7-1.2 1.8-1.2 1.3 0 2.1.6 2.2 1.6h2Z"
          fill="currentColor"
        />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 24 24" aria-hidden className={className}>
      <path
        d="M12.6 3.3c.6 0 1.2.2 1.6.8l.7 1.1a3 3 0 0 0 1.7 1.2l1.3.3c1.2.3 1.8 1.6 1.2 2.7l-.6 1.1a3 3 0 0 0-.3 2.1l.3 1.3c.3 1.2-.8 2.3-2 2.1l-1.3-.3a3 3 0 0 0-2.1.3l-1.1.6c-1.1.6-2.4 0-2.7-1.2l-.3-1.3a3 3 0 0 0-1.2-1.7l-1.1-.7c-1-.7-1-2.1 0-2.8l1.1-.7A3 3 0 0 0 9 6.3l.3-1.3c.2-1 1-1.7 2-1.7Z"
        fill="currentColor"
      />
    </svg>
  );
}

function WorkflowDiagram({ displayClassName }: { displayClassName: string }) {
  return (
    <div className="sr mt-10 overflow-hidden rounded-[28px] border border-[#D6E2F5] bg-[#F6FAFF] p-5 shadow-[0_18px_48px_rgba(9,21,40,0.08)]">
      <div className="grid items-stretch gap-4 lg:grid-cols-[1fr_auto_1.08fr_auto_1.28fr]">
        <div className="rounded-2xl border border-[#D6E2F5] bg-white p-5">
          <p className="text-[11px] font-bold uppercase tracking-[0.08em] text-[#7A94B0]">Source post</p>
          <div className="mt-4 flex items-center gap-3">
            <span className="inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-[#FACC15] via-[#E1306C] to-[#5851DB] text-white shadow-[0_12px_28px_rgba(225,48,108,0.22)]">
              <PlatformIcon platform="instagram" className="h-6 w-6" />
            </span>
            <div>
              <p className={`${displayClassName} text-xl font-bold tracking-[-0.5px] text-[#091528]`}>Instagram Reel</p>
              <p className="text-sm text-[#5A7192]">Detected from a connected source account</p>
            </div>
          </div>
        </div>

        <div className="hidden items-center justify-center text-[#9AB0CF] lg:flex">
          <ArrowRightIcon className="h-8 w-8" />
        </div>

        <div className="rounded-2xl border border-[#BFD1F3] bg-white p-5 shadow-[inset_0_0_0_1px_rgba(29,63,208,0.08)]">
          <p className="text-[11px] font-bold uppercase tracking-[0.08em] text-[#1D3FD0]">PostBandit workflow</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-3 lg:grid-cols-1 xl:grid-cols-3">
            {["Import media", "Generate export", "Write platform copy"].map((step, index) => (
              <div key={step} className="rounded-xl border border-[#E0EAF9] bg-[#FAFCFF] p-3">
                <p className="text-[11px] font-bold text-[#1D3FD0]">0{index + 1}</p>
                <p className="mt-1 text-sm font-semibold text-[#18325D]">{step}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="hidden items-center justify-center text-[#9AB0CF] lg:flex">
          <ArrowRightIcon className="h-8 w-8" />
        </div>

        <div className="rounded-2xl border border-[#D6E2F5] bg-white p-5">
          <p className="text-[11px] font-bold uppercase tracking-[0.08em] text-[#7A94B0]">Republished to</p>
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            {workflowDestinations.map((destination) => (
              <div key={destination.key} className="flex items-center gap-2 rounded-xl border border-[#E0EAF9] bg-[#FBFDFF] px-3 py-2.5">
                <span
                  className={`inline-flex h-8 w-8 items-center justify-center rounded-lg ${
                    destination.key === "youtube"
                      ? "bg-[#FF0000] text-white"
                      : destination.key === "tiktok" || destination.key === "x"
                        ? "bg-[#111827] text-white"
                        : "bg-[#1877F2] text-white"
                  }`}
                >
                  {destination.key === "facebook" ? (
                    <span className="text-lg font-bold leading-none">f</span>
                  ) : (
                    <PlatformIcon platform={destination.key} className="h-4.5 w-4.5" />
                  )}
                </span>
                <span className="text-sm font-semibold text-[#18325D]">{destination.label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <p className="mt-4 text-center text-sm leading-6 text-[#5A7192]">
        Example: PostBandit detects an Instagram post, imports the reusable video when the official API allows it, prepares the export, and creates destination jobs for TikTok, X, Facebook, and YouTube.
      </p>
    </div>
  );
}

function SectionHeading({
  tag,
  title,
  body,
  displayClassName,
}: {
  tag: string;
  title: string;
  body: string;
  displayClassName: string;
}) {
  return (
    <div className="sr text-center">
      <p className="text-xs font-bold uppercase tracking-[0.08em] text-[#1D3FD0]">{tag}</p>
      <h2 className={`${displayClassName} mt-3 text-[clamp(28px,3.8vw,48px)] font-extrabold tracking-[-1.6px]`}>{title}</h2>
      <p className="mx-auto mt-4 max-w-2xl text-base leading-7 text-[#4A6080]">{body}</p>
    </div>
  );
}

export function LandingPage({ displayClassName = "marketing-display", bodyClassName = "marketing-body" }: LandingPageProps) {
  const [publishingIndex, setPublishingIndex] = useState(0);

  useEffect(() => {
    const revealObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) entry.target.classList.add("on");
        });
      },
      { threshold: 0.12 }
    );

    const nodes = document.querySelectorAll(".sr, .sl, .srr");
    nodes.forEach((node) => revealObserver.observe(node));

    return () => revealObserver.disconnect();
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setPublishingIndex((current) => (current + 1) % (platformRows.length + 1));
    }, 2200);

    return () => window.clearInterval(timer);
  }, []);

  const doneCount = useMemo(() => {
    if (publishingIndex >= platformRows.length) return 0;
    return publishingIndex;
  }, [publishingIndex]);

  return (
    <div className={`${bodyClassName} bg-[#F6FAFF] text-[#091528]`}>
      <header className="fixed inset-x-0 top-0 z-[100] border-b border-[#D6E2F5] bg-[rgba(246,250,255,0.92)] backdrop-blur-xl">
        <div className="mx-auto flex h-16 w-full max-w-[1160px] items-center justify-between px-7">
          <Link href="/" className={`${displayClassName} text-2xl font-extrabold tracking-tight`}>
            <span className="text-[#1D3FD0]">Post</span>
            <span className="text-[#091528]">Bandit</span>
          </Link>

          <nav className="hidden items-center gap-8 text-sm font-medium text-[#4A6080] md:flex">
            <a href="#workflow" className="transition hover:text-[#1D3FD0]">
              Workflow
            </a>
            <a href="#pricing" className="transition hover:text-[#1D3FD0]">
              Pricing
            </a>
            <a href="#reviews" className="transition hover:text-[#1D3FD0]">
              Reviews
            </a>
          </nav>

          <div className="flex items-center gap-3">
            <Link href="/login" className="hidden text-sm font-semibold text-[#4A6080] transition hover:text-[#091528] md:inline-flex">
              Log in
            </Link>
            <Link
              href="/signup"
              className="inline-flex items-center gap-1 rounded-lg bg-[#1D3FD0] px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-[#1633B8]"
            >
              Start free
              <ArrowRightIcon className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </header>

      <section className="relative overflow-hidden border-b border-[#D6E2F5] bg-[linear-gradient(180deg,#F6FAFF_0%,#EDF4FF_100%)] pt-28">
        <div className="hero-grid pointer-events-none absolute inset-0 opacity-[0.35]" />
        <div className="hero-glow pointer-events-none absolute inset-0" />

        <div className="relative mx-auto grid w-full max-w-[1160px] gap-14 px-7 pb-16 md:grid-cols-[56fr_44fr] md:pb-20">
          <div className="sl">
            <p className="inline-flex items-center gap-2 rounded-full border border-[#C7D8F5] bg-white px-3.5 py-1.5 text-[12px] font-semibold text-[#31589F]">
              Now live - 10 platforms connected
            </p>

            <h1 className={`${displayClassName} mt-6 max-w-2xl text-[clamp(40px,5.2vw,66px)] font-extrabold leading-[1.03] tracking-[-2.4px]`}>
              Post to all your social accounts from
              <span className="block text-[#1D3FD0]">one dashboard</span>
            </h1>

            <p className="mt-6 max-w-xl text-lg leading-8 text-[#4A6080]">
              Easy to use, fairly priced. Import your content, let AI find the best moments, then publish everywhere -
              in minutes.
            </p>

            <div className="mt-9 flex flex-wrap items-center gap-3">
              <Link
                href="/signup"
                className="inline-flex items-center gap-2 rounded-xl bg-[#1D3FD0] px-7 py-3.5 text-[15px] font-bold text-white shadow-[0_12px_34px_rgba(29,63,208,0.28)] transition hover:-translate-y-0.5 hover:bg-[#1633B8]"
              >
                Try now for free
                <ArrowRightIcon className="h-4 w-4" />
              </Link>
              <a
                href="#workflow"
                className="inline-flex items-center rounded-xl border border-[#C5D8FA] bg-white px-6 py-3.5 text-[15px] font-semibold text-[#31589F] transition hover:border-[#AFC6EE] hover:text-[#1D3FD0]"
              >
                See how it works
              </a>
            </div>

            <div className="mt-8 flex flex-wrap items-center gap-5 text-sm text-[#5D769B]">
              <span>Loved by 1,200+ creators &amp; teams</span>
            </div>
          </div>

          <div className="srr">
            <div className="overflow-hidden rounded-[22px] border border-[#C6D8F4] bg-white shadow-[0_16px_44px_rgba(9,21,40,0.12)]">
              <div className="flex items-center justify-between border-b border-[#D6E2F5] bg-[#FAFCFF] px-4 py-3">
                <p className="text-sm font-semibold text-[#16356B]">Publishing Queue</p>
                <span className="rounded-full bg-[#E6EEFF] px-2.5 py-1 text-[11px] font-semibold text-[#1D3FD0]">Live</span>
              </div>

              <div className="space-y-2.5 p-4">
                {platformRows.map((platform, index) => {
                  const done = index < doneCount;
                  const active = index === doneCount;
                  return (
                    <div
                      key={platform.name}
                      className={`flex items-center justify-between rounded-xl border px-3.5 py-2.5 transition ${
                        active ? "border-[#BAD0F3] bg-[#F2F7FF]" : "border-[#DDE9FA] bg-white"
                      } ${done ? "opacity-65" : "opacity-100"}`}
                    >
                      <div className="flex items-center gap-2.5">
                        <span
                          className="inline-flex h-8 w-8 items-center justify-center rounded-lg"
                          style={{ color: platformColors[platform.key], backgroundColor: "#F4F8FF" }}
                        >
                          <PlatformIcon platform={platform.key} className="h-4 w-4" />
                        </span>
                        <div>
                          <p className="text-[13px] font-medium text-[#102341]">{platform.name}</p>
                          <p className="text-[11px] text-[#7A94B0]">{platform.handle}</p>
                        </div>
                      </div>
                      <div className="text-xs font-semibold">
                        {done ? (
                          <span className="inline-flex items-center gap-1 text-[#15803D]">
                            <CheckIcon className="h-3.5 w-3.5" />
                            Posted
                          </span>
                        ) : active ? (
                          <span className="inline-flex items-center gap-1 text-[#1D3FD0]">
                            <SpinnerIcon className="h-3.5 w-3.5 animate-spin" />
                            Publishing
                          </span>
                        ) : (
                          <span className="text-[#7A94B0]">Queued</span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="border-t border-[#D6E2F5] bg-[#FAFCFF] px-4 py-3">
                <div className="h-2 w-full overflow-hidden rounded-full bg-[#DDE8F9]">
                  <div className="progress-fill h-full" />
                </div>
                <div className="mt-2 flex items-center justify-between text-[11px] text-[#7A94B0]">
                  <span>Active publish cycle</span>
                  <span>{doneCount} / 5 completed</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="border-b border-[#D6E2F5] bg-white py-10">
        <div className="mx-auto w-full max-w-[1160px] px-7">
          <p className="mb-6 text-center text-xs font-semibold uppercase tracking-[0.08em] text-[#7A94B0]">
            Publish to every major platform
          </p>
          <div className="flex flex-wrap items-center justify-center gap-x-10 gap-y-4">
            {platformRows.map((platform) => (
              <span
                key={platform.key}
                className="inline-flex items-center gap-2 text-sm font-semibold"
                style={{ color: platformColors[platform.key], opacity: 0.58 }}
              >
                <PlatformIcon platform={platform.key} className="h-[18px] w-[18px]" />
                {platform.name.replace(" Shorts", "")}
              </span>
            ))}
          </div>
        </div>
      </section>

      <section id="workflow" className="bg-white py-[96px]">
        <div className="mx-auto w-full max-w-[1160px] px-7">
          <SectionHeading
            tag="Workflow"
            title="One clean workflow from raw video to published post"
            body="PostBandit keeps the process operationally simple: import, score clips, review, and publish with platform-specific controls."
            displayClassName={displayClassName}
          />

          <div className="mt-14 grid gap-5 md:grid-cols-3">
            {featureCards.map((feature, idx) => (
              <article
                key={feature.title}
                className={`sr rounded-2xl border border-[#D6E2F5] p-6 ${idx === 1 ? "bg-[#F4F8FF]" : "bg-white"}`}
              >
                <p className="text-xs font-bold uppercase tracking-[0.08em] text-[#1D3FD0]">{feature.tag}</p>
                <h3 className={`${displayClassName} mt-3 text-[26px] font-bold leading-[1.15] tracking-[-0.8px]`}>{feature.title}</h3>
                <p className="mt-3 text-[15px] leading-7 text-[#4A6080]">{feature.body}</p>
                <ul className="mt-5 space-y-2.5 text-sm text-[#415A7A]">
                  {feature.bullets.map((item) => (
                    <li key={item} className="flex items-start gap-2.5">
                      <span className="mt-1 inline-flex h-4.5 w-4.5 shrink-0 items-center justify-center rounded border border-[#C4D8FA] bg-[#E7F0FF] text-[#1D3FD0]">
                        <CheckIcon className="h-3 w-3" />
                      </span>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </article>
            ))}
          </div>

          <WorkflowDiagram displayClassName={displayClassName} />
        </div>
      </section>

      <section className="bg-[#F6FAFF] py-[96px]">
        <div className="mx-auto grid w-full max-w-[1160px] items-center gap-10 px-7 md:grid-cols-[48fr_52fr]">
          <div className="sl">
            <p className="text-xs font-bold uppercase tracking-[0.08em] text-[#1D3FD0]">Scheduling</p>
            <h2 className={`${displayClassName} mt-3 text-[clamp(28px,3.7vw,44px)] font-extrabold leading-[1.1] tracking-[-1.4px]`}>
              Schedule posts effortlessly across every platform
            </h2>
            <p className="mt-5 max-w-xl text-base leading-8 text-[#4A6080]">
              Queue your content in advance and let PostBandit handle publishing - consistently, per platform, on your
              schedule.
            </p>
            <ul className="mt-6 space-y-3 text-sm text-[#415A7A]">
              <li className="flex items-center gap-2.5">
                <CheckIcon className="h-4 w-4 text-[#1D3FD0]" />
                Set publishing times per platform independently
              </li>
              <li className="flex items-center gap-2.5">
                <CheckIcon className="h-4 w-4 text-[#1D3FD0]" />
                Visual queue with live status tracking
              </li>
              <li className="flex items-center gap-2.5">
                <CheckIcon className="h-4 w-4 text-[#1D3FD0]" />
                Automatic retry on failed posts
              </li>
            </ul>
          </div>

          <div className="srr">
            <div className="overflow-hidden rounded-2xl border border-[#D6E2F5] bg-white shadow-[0_10px_30px_rgba(9,21,40,0.08)]">
              <div className="border-b border-[#D6E2F5] bg-[#FAFCFF] px-4 py-3">
                <p className="text-sm font-semibold text-[#16356B]">Publishing Queue - Today</p>
              </div>

              <div className="space-y-2 p-4">
                {[
                  ["9:00 AM", "YouTube", "Published"],
                  ["12:30 PM", "TikTok", "Publishing now"],
                  ["5:00 PM", "Instagram", "Scheduled"],
                  ["8:00 PM", "X", "Scheduled"],
                ].map(([time, destination, status]) => (
                  <div key={`${time}-${destination}`} className="flex items-center justify-between rounded-lg border border-[#E0EAF9] bg-[#FBFDFF] px-3 py-2.5">
                    <div>
                      <p className="text-xs font-semibold text-[#18325D]">{time}</p>
                      <p className="text-[11px] text-[#7390B2]">{destination}</p>
                    </div>
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                        status === "Published"
                          ? "bg-emerald-100 text-emerald-700"
                          : status === "Publishing now"
                            ? "bg-blue-100 text-blue-700"
                            : "bg-slate-100 text-slate-700"
                      }`}
                    >
                      {status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      <MascotSection />

      <section id="pricing" className="bg-white py-[96px]">
        <div className="mx-auto w-full max-w-[1160px] px-7">
          <SectionHeading
            tag="Pricing"
            title="Simple, fair pricing"
            body="Start with a 7-day trial. No hidden fees, no per-post charges, and plan limits are visible before you publish."
            displayClassName={displayClassName}
          />

          <div className="mt-12 grid gap-6 md:grid-cols-[1fr_1.06fr_1fr]">
            {pricing.map((plan) => (
              <article
                key={plan.plan}
                className={`sr rounded-2xl border p-7 ${
                  plan.featured
                    ? "-mt-1 border-[#1D3FD0] bg-[#1D3FD0] text-white shadow-[0_14px_36px_rgba(29,63,208,0.32)]"
                    : "border-[#D6E2F5] bg-white"
                }`}
              >
                {plan.featured ? (
                  <span className="inline-flex rounded-full border border-white/35 bg-white/15 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.06em] text-white">
                    Most popular
                  </span>
                ) : null}
                <p className={`mt-2 text-xs font-bold uppercase tracking-[0.08em] ${plan.featured ? "text-white/75" : "text-[#7A94B0]"}`}>
                  {plan.plan}
                </p>
                <p className={`${displayClassName} mt-3`}>
                  <span className="align-top text-[22px]">{plan.price.charAt(0)}</span>
                  <span className="text-[50px] font-extrabold leading-none">{plan.price.slice(1)}</span>
                  <span className={`ml-1 text-sm ${plan.featured ? "text-white/70" : "text-[#7A94B0]"}`}>{plan.note}</span>
                </p>
                <p className={`mt-3 text-sm leading-6 ${plan.featured ? "text-white/82" : "text-[#4A6080]"}`}>{plan.desc}</p>
                <ul className={`mt-5 space-y-2.5 text-sm ${plan.featured ? "text-white/92" : "text-[#415A7A]"}`}>
                  {plan.items.map((item) => (
                    <li key={item} className="flex items-start gap-2.5">
                      <span
                        className={`mt-1 inline-flex h-5 w-5 items-center justify-center rounded-md border ${
                          plan.featured
                            ? "border-white/35 bg-white/18"
                            : "border-[#C4D8FA] bg-[#E7F0FF] text-[#1D3FD0]"
                        }`}
                      >
                        <CheckIcon className={`h-3.5 w-3.5 ${plan.featured ? "text-white" : "text-[#1D3FD0]"}`} />
                      </span>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
                <Link
                  href="/signup"
                  className={`mt-6 inline-flex w-full items-center justify-center rounded-lg px-4 py-2.5 text-sm font-semibold transition ${
                    plan.featured
                      ? "bg-white text-[#1D3FD0] hover:bg-[#EAF1FF]"
                      : "border border-[#D6E2F5] text-[#16356B] hover:bg-[#F4F8FF]"
                  }`}
                >
                  {plan.cta}
                </Link>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section id="reviews" className="bg-[#F6FAFF] py-[96px]">
        <div className="mx-auto w-full max-w-[1160px] px-7">
          <SectionHeading
            tag="Reviews"
            title="Loved by creators everywhere"
            body="Creators use PostBandit to cut clip workflow time and publish faster across platforms."
            displayClassName={displayClassName}
          />

          <div className="mt-12 grid gap-5 md:grid-cols-[1.45fr_1fr]">
            <article className="sr rounded-2xl border border-[#D6E2F5] bg-white p-8 shadow-[0_4px_16px_rgba(9,21,40,0.06)]">
              <div className="mb-4 flex gap-1 text-[#F59E0B]">
                {Array.from({ length: 5 }).map((_, idx) => (
                  <StarIcon key={idx} className="h-[13px] w-[13px]" />
                ))}
              </div>
              <p className="text-[16px] leading-8 text-[#465F80]">
                "I used to spend 2 hours every Monday clipping our Sunday sermon. PostBandit cut that to 20 minutes.
                The AI consistently finds moments I'd genuinely miss on my own - and the quality is better than what I
                was manually selecting."
              </p>
              <div className="mt-6 flex items-center gap-3">
                <span className="inline-flex h-[38px] w-[38px] items-center justify-center rounded-full bg-[#2D4AAE] text-xs font-bold text-white">
                  JM
                </span>
                <div>
                  <p className={`${displayClassName} text-[13px] font-semibold`}>James Mitchell</p>
                  <p className="text-xs text-[#7A94B0]">Worship Pastor, New Life Church</p>
                </div>
              </div>
            </article>

            <div className="flex flex-col gap-5">
              {[
                [
                  "OpusClip was more than I needed and too expensive. PostBandit has everything I actually use - and scheduling killed my daily posting grind entirely.",
                  "SK",
                  "Content creator - 45k followers",
                ],
                [
                  "We manage social for 8 clients. One dashboard, all accounts, everything tracked. The Agency plan pays for itself within the first week of saved time.",
                  "TW",
                  "Founder, Sparrow Media Agency",
                ],
              ].map(([quote, initials, role]) => (
                <article key={initials} className="sr rounded-2xl border border-[#D6E2F5] bg-white p-6 shadow-[0_4px_16px_rgba(9,21,40,0.06)]">
                  <div className="mb-3 flex gap-1 text-[#F59E0B]">
                    {Array.from({ length: 5 }).map((_, idx) => (
                      <StarIcon key={idx} className="h-[13px] w-[13px]" />
                    ))}
                  </div>
                  <p className="text-[15px] leading-7 text-[#4A6080]">"{quote}"</p>
                  <div className="mt-5 flex items-center gap-3">
                    <span className="inline-flex h-[36px] w-[36px] items-center justify-center rounded-full bg-[#3659CA] text-xs font-bold text-white">
                      {initials}
                    </span>
                    <p className="text-xs text-[#7A94B0]">{role}</p>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="relative overflow-hidden bg-[#1D3FD0] py-24 text-white">
        <div className="hero-grid pointer-events-none absolute inset-0 opacity-[0.12]" />
        <div className="relative mx-auto w-full max-w-[920px] px-7 text-center">
          <h2 className={`${displayClassName} sr text-[clamp(30px,4.6vw,56px)] font-extrabold tracking-[-2px]`}>
            Ready to post smarter?
          </h2>
          <p className="sr mx-auto mt-5 max-w-2xl text-[17px] leading-8 text-[rgba(255,255,255,0.78)]">
            Join 1,200+ creators publishing to every platform from one place. Free to start, no card required.
          </p>
          <div className="sr mt-8">
            <Link
              href="/signup"
              className="inline-flex items-center gap-2 rounded-[10px] bg-white px-8 py-3.5 text-[15px] font-bold text-[#1D3FD0] shadow-[0_10px_26px_rgba(0,0,0,0.18)] transition hover:-translate-y-0.5"
            >
              Try now for free
              <ArrowRightIcon className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </section>

      <footer className="bg-[#0D1A33] py-11 text-white">
        <div className="mx-auto flex w-full max-w-[1160px] flex-col items-center justify-between gap-5 px-7 text-center md:flex-row md:text-left">
          <p className={`${displayClassName} text-lg font-extrabold`}>
            <span className="text-[#7EA7FF]">Post</span>
            <span className="text-white">Bandit</span>
          </p>

          <div className="flex items-center gap-6 text-sm text-[rgba(255,255,255,0.46)]">
            <Link href="/privacy" className="transition hover:text-[rgba(255,255,255,0.84)]">
              Privacy Policy
            </Link>
            <Link href="/terms" className="transition hover:text-[rgba(255,255,255,0.84)]">
              Terms of Service
            </Link>
            <Link href="/refunds" className="transition hover:text-[rgba(255,255,255,0.84)]">
              Refund Policy
            </Link>
            <a href="#" className="transition hover:text-[rgba(255,255,255,0.84)]">
              Support
            </a>
          </div>

          <p className="text-[13px] text-[rgba(255,255,255,0.3)]">© 2026 PostBandit. All rights reserved.</p>
        </div>
      </footer>

      <style jsx global>{`
        .marketing-display {
          font-family: "Bricolage Grotesque", Inter, sans-serif;
        }

        .marketing-body {
          font-family: "Plus Jakarta Sans", Inter, sans-serif;
        }

        .hero-grid {
          background-image: linear-gradient(rgba(29, 63, 208, 0.07) 1px, transparent 1px),
            linear-gradient(90deg, rgba(29, 63, 208, 0.07) 1px, transparent 1px);
          background-size: 34px 34px;
        }

        .hero-glow {
          background: radial-gradient(circle at 82% 16%, rgba(103, 144, 255, 0.24), transparent 46%),
            radial-gradient(circle at 8% 84%, rgba(29, 63, 208, 0.2), transparent 50%);
        }

        .progress-fill {
          width: 8%;
          background: linear-gradient(90deg, #1d3fd0, #8bb3ff);
          animation: progress-wave 3.5s linear infinite;
        }

        .sr,
        .sl,
        .srr {
          opacity: 0;
          transform: translateY(20px) scale(0.985);
          transition: transform 540ms cubic-bezier(0.22, 1, 0.36, 1), opacity 540ms cubic-bezier(0.22, 1, 0.36, 1);
          will-change: transform, opacity;
        }

        .sl {
          transform: translateX(-18px) scale(0.985);
        }

        .srr {
          transform: translateX(18px) scale(0.985);
        }

        .sr.on,
        .sl.on,
        .srr.on {
          opacity: 1;
          transform: translateX(0) translateY(0) scale(1);
        }

        @keyframes progress-wave {
          0% {
            width: 8%;
          }
          50% {
            width: 78%;
          }
          100% {
            width: 8%;
          }
        }

        @media (hover: hover) and (pointer: fine) {
          a,
          button {
            transition-duration: 160ms;
          }
        }

        @media (prefers-reduced-motion: reduce) {
          .sr,
          .sl,
          .srr {
            transform: none !important;
            transition: opacity 180ms ease !important;
          }

          .progress-fill,
          .animate-spin {
            animation: none !important;
          }
        }
      `}</style>
    </div>
  );
}
