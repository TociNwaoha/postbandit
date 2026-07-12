"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { signOut, useSession } from "next-auth/react";
import { useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { BrandProfile } from "@/types";

const workspaceNavItems = [
  {
    label: "Dashboard",
    href: "/dashboard",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="3" y="3" width="7" height="7" rx="1" stroke="currentColor" strokeWidth="2"/>
        <rect x="14" y="3" width="7" height="7" rx="1" stroke="currentColor" strokeWidth="2"/>
        <rect x="3" y="14" width="7" height="7" rx="1" stroke="currentColor" strokeWidth="2"/>
        <rect x="14" y="14" width="7" height="7" rx="1" stroke="currentColor" strokeWidth="2"/>
      </svg>
    ),
  },
  {
    label: "Videos",
    href: "/videos",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="2" y="2" width="20" height="20" rx="3" stroke="currentColor" strokeWidth="2"/>
        <path d="M10 8L16 12L10 16V8Z" fill="currentColor"/>
      </svg>
    ),
  },
  {
    label: "Analytics",
    href: "/dashboard/analytics",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M4 19V5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <path d="M4 19H20" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <path d="M8 16L11 11L14 13L18 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    label: "Carousels",
    href: "/carousels",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="3" y="4" width="12" height="14" rx="2" stroke="currentColor" strokeWidth="2" />
        <rect x="9" y="7" width="12" height="14" rx="2" stroke="currentColor" strokeWidth="2" />
      </svg>
    ),
  },
  {
    label: "Clips",
    href: "/clips",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M14.5 4H9.5L7 8H3V20H21V8H17L14.5 4Z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round"/>
        <circle cx="12" cy="14" r="3" stroke="currentColor" strokeWidth="2"/>
      </svg>
    ),
  },
  {
    label: "Exports",
    href: "/exports",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M21 15V19C21 20.1046 20.1046 21 19 21H5C3.89543 21 3 20.1046 3 19V15" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
        <path d="M7 10L12 15L17 10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        <path d="M12 15V3" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
      </svg>
    ),
  },
  {
    label: "Connections",
    href: "/connections",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M9 12H15" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <path d="M12 9V15" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <rect x="3" y="4" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="2" />
        <rect x="14" y="4" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="2" />
        <rect x="3" y="13" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="2" />
        <rect x="14" y="13" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="2" />
      </svg>
    ),
  },
  {
    label: "Workflows",
    href: "/workflows",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M5 7H15C17.2091 7 19 8.79086 19 11V11" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <path d="M9 3L5 7L9 11" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M19 17H9C6.79086 17 5 15.2091 5 13V13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <path d="M15 13L19 17L15 21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    label: "Developers",
    href: "/developers",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M8 8L4 12L8 16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M16 8L20 12L16 16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M14 5L10 19" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    label: "Billing",
    href: "/billing",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="3" y="5" width="18" height="14" rx="2" stroke="currentColor" strokeWidth="2" />
        <path d="M3 9H21" stroke="currentColor" strokeWidth="2" />
        <path d="M7 15H11" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    label: "Settings",
    href: "/settings",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="2"/>
        <path d="M19.4 15C19.1 15.5 19.3 16.1 19.7 16.5L19.8 16.6C20.1 16.9 20.3 17.3 20.3 17.7C20.3 18.1 20.1 18.5 19.8 18.8C19.5 19.1 19.1 19.3 18.7 19.3C18.3 19.3 17.9 19.1 17.6 18.8L17.5 18.7C17.1 18.3 16.5 18.1 16 18.4C15.5 18.6 15.2 19.1 15.2 19.6V19.8C15.2 20.6 14.6 21.2 13.8 21.3C13.6 21.3 13.4 21.3 13.2 21.3C12.4 21.3 11.8 20.7 11.8 19.9V19.7C11.8 19.2 11.5 18.7 11 18.5C10.5 18.2 9.9 18.4 9.5 18.8L9.4 18.9C9.1 19.2 8.7 19.4 8.3 19.4C7.9 19.4 7.5 19.2 7.2 18.9C6.6 18.3 6.6 17.3 7.2 16.7L7.3 16.6C7.7 16.2 7.9 15.6 7.6 15.1C7.4 14.6 6.9 14.3 6.4 14.3H6.2C5.4 14.3 4.8 13.7 4.7 12.9C4.7 12.7 4.7 12.5 4.7 12.3C4.7 11.5 5.3 10.9 6.1 10.9H6.3C6.8 10.9 7.3 10.6 7.5 10.1C7.8 9.6 7.6 9 7.2 8.6L7.1 8.5C6.8 8.2 6.6 7.8 6.6 7.4C6.6 7 6.8 6.6 7.1 6.3C7.7 5.7 8.7 5.7 9.3 6.3L9.4 6.4C9.8 6.8 10.4 7 10.9 6.7C11.4 6.5 11.7 6 11.7 5.5V5.3C11.7 4.5 12.3 3.9 13.1 3.8C13.3 3.8 13.5 3.8 13.7 3.8C14.5 3.8 15.1 4.4 15.1 5.2V5.4C15.1 5.9 15.4 6.4 15.9 6.6C16.4 6.9 17 6.7 17.4 6.3L17.5 6.2C17.8 5.9 18.2 5.7 18.6 5.7C19 5.7 19.4 5.9 19.7 6.2C20.3 6.8 20.3 7.8 19.7 8.4L19.6 8.5C19.2 8.9 19 9.5 19.3 10C19.5 10.5 20 10.8 20.5 10.8H20.7C21.5 10.8 22.1 11.4 22.2 12.2C22.2 12.4 22.2 12.6 22.2 12.8C22.2 13.6 21.6 14.2 20.8 14.2H20.6C20.1 14.2 19.6 14.5 19.4 15Z" stroke="currentColor" strokeWidth="2"/>
      </svg>
    ),
  },
];

const aiCmoNavItems = [
  {
    label: "Content Queue",
    href: "/content-queue",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M8 6H21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <path d="M8 12H21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <path d="M8 18H21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <circle cx="4" cy="6" r="1" fill="currentColor" />
        <circle cx="4" cy="12" r="1" fill="currentColor" />
        <circle cx="4" cy="18" r="1" fill="currentColor" />
      </svg>
    ),
  },
  {
    label: "Brand Setup",
    href: "/brand-setup",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 15L8.5 17L9.5 13L6.5 10.5L10.5 10L12 6.5L13.5 10L17.5 10.5L14.5 13L15.5 17L12 15Z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" />
      </svg>
    ),
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const { data: session } = useSession();
  const userEmail = session?.user?.email || "";
  const initials = userEmail.slice(0, 2).toUpperCase();
  const [aiCmoEnabled, setAiCmoEnabled] = useState(false);

  useEffect(() => {
    if (!session?.user) return;
    let active = true;

    const loadAiCmoStatus = async () => {
      try {
        const profile = await api.get<BrandProfile>("/api/brand-profile");
        if (active) setAiCmoEnabled(profile.ai_cmo_enabled ?? true);
      } catch (err) {
        if (active) {
          setAiCmoEnabled(false);
          if (!(err instanceof ApiError && err.status === 404)) {
            // Non-blocking: sidebar still renders with the safe "off" indicator.
            console.warn("[sidebar] failed to load AI CMO status", err);
          }
        }
      }
    };

    const onStatusChanged = (event: Event) => {
      const detail = (event as CustomEvent<{ enabled?: boolean }>).detail;
      if (typeof detail?.enabled === "boolean") setAiCmoEnabled(detail.enabled);
    };

    void loadAiCmoStatus();
    window.addEventListener("ai-cmo-status-changed", onStatusChanged);
    return () => {
      active = false;
      window.removeEventListener("ai-cmo-status-changed", onStatusChanged);
    };
  }, [session?.user]);

  return (
    <aside className="flex min-h-screen w-60 flex-col border-r border-[var(--app-border)] bg-white">
      <div className="flex items-center gap-2.5 border-b border-[var(--app-border)] px-5 py-5">
        <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md bg-[var(--app-primary)]">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M5 3L19 12L5 21V3Z" fill="white" />
          </svg>
        </div>
        <span className="app-display text-base font-bold tracking-tight text-[var(--app-text)]">PostBandit</span>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-3">
        <div className="space-y-0.5">
          {workspaceNavItems.map((item) => {
            const isActive = pathname === item.href || (item.href !== "/dashboard" && pathname.startsWith(item.href + "/"));
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`
                  flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors
                  ${isActive
                    ? "bg-[rgba(29,63,208,0.1)] text-[var(--app-primary)]"
                    : "text-[var(--app-muted)] hover:text-[var(--app-text)] hover:bg-[#F4F8FF]"
                  }
                `}
              >
                <span className={isActive ? "text-[var(--app-primary)]" : "text-[var(--app-subtle)]"}>{item.icon}</span>
                {item.label}
              </Link>
            );
          })}
        </div>
        <div className="pt-2">
          <div className="flex items-center gap-2 px-3 pb-1.5">
            <span
              className={`relative flex h-3 w-3 items-center justify-center rounded-full ${
                aiCmoEnabled ? "bg-emerald-500" : "bg-red-500"
              }`}
              aria-label={aiCmoEnabled ? "AI CMO is on" : "AI CMO is off"}
              title={aiCmoEnabled ? "AI CMO is on" : "AI CMO is off"}
            >
              <span
                className={`absolute h-6 w-6 rounded-full blur-sm ${
                  aiCmoEnabled ? "bg-emerald-400/35" : "bg-red-500/35"
                }`}
              />
              <span
                className={`absolute h-10 w-10 rounded-full blur-md ${
                  aiCmoEnabled ? "bg-emerald-400/10" : "bg-red-500/10"
                }`}
              />
            </span>
            <p className="text-xs font-bold uppercase tracking-wide text-[var(--app-muted)]">AI CMO</p>
          </div>
          <div className="space-y-0.5">
            {aiCmoNavItems.map((item) => {
              const isActive = pathname === item.href || pathname.startsWith(item.href + "/");
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`
                    flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors
                    ${isActive
                      ? "bg-[rgba(29,63,208,0.1)] text-[var(--app-primary)]"
                      : "text-[var(--app-muted)] hover:text-[var(--app-text)] hover:bg-[#F4F8FF]"
                    }
                  `}
                >
                  <span className={isActive ? "text-[var(--app-primary)]" : "text-[var(--app-subtle)]"}>{item.icon}</span>
                  {item.label}
                </Link>
              );
            })}
          </div>
        </div>
      </nav>

      <div className="border-t border-[var(--app-border)] px-3 py-4">
        <div className="mb-2 flex items-center gap-3 px-2">
          <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-[rgba(29,63,208,0.1)]">
            <span className="text-xs font-semibold text-[var(--app-primary)]">{initials}</span>
          </div>
          <p className="flex-1 truncate text-xs text-[var(--app-muted)]">{userEmail}</p>
        </div>
        <button
          onClick={() => signOut({ callbackUrl: "/login" })}
          className="w-full rounded-lg px-3 py-2 text-left text-sm text-[var(--app-subtle)] transition-colors hover:bg-[#F4F8FF] hover:text-[var(--app-text)]"
        >
          Sign out
        </button>
      </div>
    </aside>
  );
}
