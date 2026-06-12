import { ReactNode } from "react";

import { SocialPlatform } from "@/types";

export interface SocialPlatformMeta {
  displayName: string;
  chipClassName: string;
  icon: ReactNode;
}

const iconClassName = "h-3.5 w-3.5";

const platformMetaMap: Record<SocialPlatform, SocialPlatformMeta> = {
  x: {
    displayName: "X",
    chipClassName: "bg-[#111111] text-white",
    icon: (
      <svg className={iconClassName} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M18.244 2H21.5l-7.12 8.13L22 22h-5.95l-4.66-6.31L5.91 22H2.65l7.62-8.7L2 2h6.1l4.21 5.7L18.244 2Zm-1.04 18h1.81L7.12 3.9H5.19L17.204 20Z" />
      </svg>
    ),
  },
  linkedin: {
    displayName: "LinkedIn",
    chipClassName: "bg-[#0A66C2] text-white",
    icon: (
      <svg className={iconClassName} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M4.98 3.5C4.98 4.88 3.87 6 2.49 6S0 4.88 0 3.5 1.11 1 2.49 1s2.49 1.12 2.49 2.5ZM.5 8.5h4V23h-4V8.5Zm7 0h3.84v1.98h.06c.54-1.01 1.86-2.07 3.83-2.07C19.32 8.41 21 10.8 21 14.25V23h-4v-7.56c0-1.8-.03-4.11-2.5-4.11-2.5 0-2.88 1.95-2.88 3.98V23h-4V8.5H7.5Z" />
      </svg>
    ),
  },
  facebook: {
    displayName: "Facebook",
    chipClassName: "bg-[#1877F2] text-white",
    icon: (
      <svg className={iconClassName} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M24 12.07C24 5.4 18.63 0 12 0S0 5.4 0 12.07C0 18.1 4.39 23.1 10.13 24v-8.44H7.08v-3.49h3.05V9.41c0-3.02 1.79-4.69 4.53-4.69 1.31 0 2.69.24 2.69.24v2.97h-1.52c-1.5 0-1.96.94-1.96 1.9v2.28h3.34l-.53 3.49h-2.81V24C19.61 23.1 24 18.1 24 12.07Z" />
      </svg>
    ),
  },
  tiktok: {
    displayName: "TikTok",
    chipClassName: "bg-[#101010] text-white",
    icon: (
      <svg className={iconClassName} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M19.58 8.94a7.36 7.36 0 0 1-4.3-1.37v6.24a5.81 5.81 0 1 1-5.82-5.81c.37 0 .73.04 1.08.11v2.9a2.9 2.9 0 1 0 1.83 2.7V2h2.9a4.45 4.45 0 0 0 4.31 4.02v2.92Z" />
      </svg>
    ),
  },
  instagram: {
    displayName: "Instagram",
    chipClassName: "bg-[#C13584] text-white",
    icon: (
      <svg className={iconClassName} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <rect x="3" y="3" width="18" height="18" rx="5" stroke="currentColor" strokeWidth="2" />
        <circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="2" />
        <circle cx="17.5" cy="6.5" r="1.5" fill="currentColor" />
      </svg>
    ),
  },
  threads: {
    displayName: "Threads",
    chipClassName: "bg-[#0D0D0D] text-white",
    icon: (
      <svg className={iconClassName} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M15.34 11.72c-.16-.07-.33-.14-.51-.2a6.8 6.8 0 0 0-.3-1.42A3.7 3.7 0 0 0 10.9 7.3c-1.9 0-3.2 1.03-3.66 2.9l2.1.54c.2-.78.68-1.17 1.47-1.17.8 0 1.28.4 1.47 1.2.06.22.1.46.14.7a8.5 8.5 0 0 0-1.74-.18c-2.5 0-4.14 1.45-4.14 3.66 0 2.16 1.63 3.64 4.05 3.64 1.48 0 2.67-.53 3.45-1.54.6-.76.9-1.76.9-2.95v-.11c.38.17.68.37.88.59.24.25.35.55.35.92 0 .77-.5 1.33-1.51 1.66-.9.3-2.13.4-3.69.33l-.08 2.12c.33.01.65.02.95.02 1.64 0 3.03-.2 4.17-.6 1.95-.7 2.93-1.93 2.93-3.65 0-.96-.32-1.8-.95-2.5-.5-.56-1.18-1.01-2.04-1.35Zm-3.22 3.17c-.35.46-.85.69-1.51.69-.97 0-1.62-.57-1.62-1.42 0-.9.68-1.48 1.73-1.48.55 0 1.09.08 1.63.24-.03.77-.12 1.4-.23 1.97Z" />
      </svg>
    ),
  },
  youtube: {
    displayName: "YouTube",
    chipClassName: "bg-[#FF0000] text-white",
    icon: (
      <svg className={iconClassName} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M23.5 6.2a3.01 3.01 0 0 0-2.12-2.13C19.52 3.5 12 3.5 12 3.5s-7.52 0-9.38.57A3.01 3.01 0 0 0 .5 6.2 31.7 31.7 0 0 0 0 12a31.7 31.7 0 0 0 .5 5.8 3.01 3.01 0 0 0 2.12 2.13c1.86.57 9.38.57 9.38.57s7.52 0 9.38-.57a3.01 3.01 0 0 0 2.12-2.13A31.7 31.7 0 0 0 24 12a31.7 31.7 0 0 0-.5-5.8ZM9.6 15.64V8.36L15.84 12 9.6 15.64Z" />
      </svg>
    ),
  },
};

export function getSocialPlatformMeta(platform: string): SocialPlatformMeta {
  const key = platform as SocialPlatform;
  if (platformMetaMap[key]) {
    return platformMetaMap[key];
  }

  const displayName = platform
    ? platform.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase())
    : "Platform";

  return {
    displayName,
    chipClassName: "bg-[var(--app-primary)] text-white",
    icon: (
      <svg className={iconClassName} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" />
        <path d="M8 12H16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    ),
  };
}
