import { ReactNode } from "react";

import { SocialPlatform } from "@/types";

export interface PlatformBrandMeta {
  platform: SocialPlatform | "unknown";
  displayName: string;
  buttonLabel: string;
  analyticsColor: string;
  baseClassName: string;
  disabledClassName: string;
  badgeClassName: string;
  icon: ReactNode;
}

const iconClassName = "h-5 w-5 flex-shrink-0";

const platformBrandMap: Record<SocialPlatform, PlatformBrandMeta> = {
  x: {
    platform: "x",
    displayName: "X",
    buttonLabel: "Login with X",
    analyticsColor: "#111111",
    baseClassName: "bg-[#111111] text-white hover:bg-[#222222]",
    disabledClassName: "bg-[#2B2B2B] text-white/70",
    badgeClassName: "bg-[#111111] text-white",
    icon: (
      <svg className={iconClassName} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M18.244 2H21.5l-7.12 8.13L22 22h-5.95l-4.66-6.31L5.91 22H2.65l7.62-8.7L2 2h6.1l4.21 5.7L18.244 2Zm-1.04 18h1.81L7.12 3.9H5.19L17.204 20Z" />
      </svg>
    ),
  },
  linkedin: {
    platform: "linkedin",
    displayName: "LinkedIn",
    buttonLabel: "Login with LinkedIn",
    analyticsColor: "#0A66C2",
    baseClassName: "bg-[#0A66C2] text-white hover:bg-[#084d93]",
    disabledClassName: "bg-[#5E9ED4] text-white/80",
    badgeClassName: "bg-[#0A66C2] text-white",
    icon: (
      <svg className={iconClassName} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M4.98 3.5C4.98 4.88 3.87 6 2.49 6S0 4.88 0 3.5 1.11 1 2.49 1s2.49 1.12 2.49 2.5ZM.5 8.5h4V23h-4V8.5Zm7 0h3.84v1.98h.06c.54-1.01 1.86-2.07 3.83-2.07C19.32 8.41 21 10.8 21 14.25V23h-4v-7.56c0-1.8-.03-4.11-2.5-4.11-2.5 0-2.88 1.95-2.88 3.98V23h-4V8.5H7.5Z" />
      </svg>
    ),
  },
  facebook: {
    platform: "facebook",
    displayName: "Facebook",
    buttonLabel: "Login with Facebook",
    analyticsColor: "#1877F2",
    baseClassName: "bg-[#1877F2] text-white hover:bg-[#1664cc]",
    disabledClassName: "bg-[#6FA8FF] text-white/80",
    badgeClassName: "bg-[#1877F2] text-white",
    icon: (
      <svg className={iconClassName} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M24 12.07C24 5.4 18.63 0 12 0S0 5.4 0 12.07C0 18.1 4.39 23.1 10.13 24v-8.44H7.08v-3.49h3.05V9.41c0-3.02 1.79-4.69 4.53-4.69 1.31 0 2.69.24 2.69.24v2.97h-1.52c-1.5 0-1.96.94-1.96 1.9v2.28h3.34l-.53 3.49h-2.81V24C19.61 23.1 24 18.1 24 12.07Z" />
      </svg>
    ),
  },
  tiktok: {
    platform: "tiktok",
    displayName: "TikTok",
    buttonLabel: "Login with TikTok",
    analyticsColor: "#00F2EA",
    baseClassName: "bg-[#101010] text-white hover:bg-[#242424]",
    disabledClassName: "bg-[#3B3B3B] text-white/80",
    badgeClassName: "bg-[#101010] text-white",
    icon: (
      <svg className={iconClassName} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M19.58 8.94a7.36 7.36 0 0 1-4.3-1.37v6.24a5.81 5.81 0 1 1-5.82-5.81c.37 0 .73.04 1.08.11v2.9a2.9 2.9 0 1 0 1.83 2.7V2h2.9a4.45 4.45 0 0 0 4.31 4.02v2.92Z" />
      </svg>
    ),
  },
  instagram: {
    platform: "instagram",
    displayName: "Instagram",
    buttonLabel: "Login with Instagram",
    analyticsColor: "#C13584",
    baseClassName:
      "bg-[linear-gradient(90deg,#405DE6_0%,#5851DB_25%,#C13584_55%,#E1306C_75%,#FD1D1D_100%)] text-white hover:brightness-110",
    disabledClassName: "bg-[#B5549A] text-white/80",
    badgeClassName:
      "bg-[radial-gradient(circle_at_30%_110%,#FEDA75_0%,#FA7E1E_25%,#D62976_50%,#962FBF_75%,#4F5BD5_100%)] text-white",
    icon: (
      <svg className={iconClassName} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <rect x="3" y="3" width="18" height="18" rx="5" stroke="currentColor" strokeWidth="2" />
        <circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="2" />
        <circle cx="17.5" cy="6.5" r="1.5" fill="currentColor" />
      </svg>
    ),
  },
  threads: {
    platform: "threads",
    displayName: "Threads",
    buttonLabel: "Login with Threads",
    analyticsColor: "#111111",
    baseClassName: "bg-[#0D0D0D] text-white hover:bg-[#1e1e1e]",
    disabledClassName: "bg-[#3A3A3A] text-white/80",
    badgeClassName: "bg-[#0D0D0D] text-white",
    icon: (
      <svg className={iconClassName} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M12.186 24h-.007c-3.581-.024-6.334-1.205-8.184-3.509C2.35 18.44 1.5 15.586 1.472 12.01v-.017c.03-3.579.879-6.43 2.525-8.482C5.845 1.205 8.6.024 12.18 0h.014c2.746.02 5.043.725 6.826 2.098 1.677 1.29 2.858 3.13 3.509 5.467l-2.04.569c-1.104-3.96-3.898-5.984-8.304-6.015-2.91.022-5.11.936-6.54 2.717C4.307 6.504 3.616 8.914 3.589 12c.027 3.086.718 5.496 2.057 7.164 1.43 1.783 3.631 2.698 6.54 2.717 2.623-.02 4.358-.631 5.8-2.045 1.647-1.613 1.618-3.593 1.09-4.798-.31-.71-.873-1.3-1.634-1.75-.192 1.352-.622 2.446-1.284 3.272-.886 1.102-2.14 1.704-3.73 1.79-1.202.065-2.361-.218-3.259-.801-1.063-.689-1.685-1.74-1.752-2.964-.065-1.19.408-2.285 1.33-3.082.88-.76 2.119-1.207 3.583-1.291a13.853 13.853 0 0 1 3.02.142c-.126-.742-.375-1.332-.75-1.757-.513-.586-1.308-.883-2.359-.89h-.029c-.844 0-1.992.232-2.721 1.32L7.734 7.847c.98-1.454 2.568-2.256 4.478-2.256h.044c3.194.02 5.097 1.975 5.287 5.388.108.046.216.094.321.142 1.49.7 2.58 1.761 3.154 3.07.797 1.82.871 4.79-1.548 7.158-1.85 1.81-4.094 2.628-7.277 2.65Zm1.003-11.69c-.242 0-.487.007-.739.021-1.836.103-2.98.946-2.916 2.143.067 1.256 1.452 1.839 2.784 1.767 1.224-.065 2.818-.543 3.086-3.71a10.5 10.5 0 0 0-2.215-.221z" />
      </svg>
    ),
  },
  youtube: {
    platform: "youtube",
    displayName: "YouTube",
    buttonLabel: "Login with YouTube",
    analyticsColor: "#FF0000",
    baseClassName: "bg-[#FF0000] text-white hover:bg-[#d50000]",
    disabledClassName: "bg-[#FF7A7A] text-white/80",
    badgeClassName: "bg-[#FF0000] text-white",
    icon: (
      <svg className={iconClassName} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M23.5 6.2a3.01 3.01 0 0 0-2.12-2.13C19.52 3.5 12 3.5 12 3.5s-7.52 0-9.38.57A3.01 3.01 0 0 0 .5 6.2 31.7 31.7 0 0 0 0 12a31.7 31.7 0 0 0 .5 5.8 3.01 3.01 0 0 0 2.12 2.13c1.86.57 9.38.57 9.38.57s7.52 0 9.38-.57a3.01 3.01 0 0 0 2.12-2.13A31.7 31.7 0 0 0 24 12a31.7 31.7 0 0 0-.5-5.8ZM9.6 15.64V8.36L15.84 12 9.6 15.64Z" />
      </svg>
    ),
  },
};

const fallbackMeta = (platform: string): PlatformBrandMeta => {
  const normalized = platform.trim().replace(/_/g, " ");
  const displayName = normalized
    ? normalized.replace(/\b\w/g, (char) => char.toUpperCase())
    : "Provider";
  return {
    platform: "unknown",
    displayName,
    buttonLabel: `Login with ${displayName}`,
    analyticsColor: "#1D3FD0",
    baseClassName: "bg-[var(--app-primary)] text-white hover:bg-[var(--app-primary-hover)]",
    disabledClassName: "bg-[#6B83DC] text-white/80",
    badgeClassName: "bg-[var(--app-primary)] text-white",
    icon: (
      <svg className={iconClassName} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" />
        <path d="M8 12H16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    ),
  };
};

export function getPlatformBrandMeta(platform: string): PlatformBrandMeta {
  const known = platformBrandMap[platform as SocialPlatform];
  return known || fallbackMeta(platform);
}
