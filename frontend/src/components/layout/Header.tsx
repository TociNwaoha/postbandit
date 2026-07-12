"use client";

import Link from "next/link";
import { signOut, useSession } from "next-auth/react";
import { useEffect, useRef, useState } from "react";

interface HeaderProps {
  title: string;
}

export function Header({ title }: HeaderProps) {
  const { data: session } = useSession();
  const userEmail = session?.user?.email || "";
  const displayName = session?.user?.name || userEmail.split("@")[0] || "Account";
  const initials = userEmail.slice(0, 2).toUpperCase();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!menuOpen) return;

    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };

    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [menuOpen]);

  return (
    <header className="flex items-center justify-between px-8 py-4 border-b border-[var(--app-border)] bg-white">
      <h1 className="app-display text-xl font-semibold text-[var(--app-text)]">{title}</h1>

      <div className="flex items-center gap-3">
        {/* Notification bell (inactive) */}
        <button className="w-9 h-9 rounded-lg flex items-center justify-center text-[var(--app-subtle)]
                           hover:text-[var(--app-text)] hover:bg-[#F4F8FF] transition-colors relative">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M18 8C18 6.4087 17.3679 4.88258 16.2426 3.75736C15.1174 2.63214 13.5913 2 12 2C10.4087 2 8.88258 2.63214 7.75736 3.75736C6.63214 4.88258 6 6.4087 6 8C6 15 3 17 3 17H21C21 17 18 15 18 8Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M13.73 21C13.5542 21.3031 13.3019 21.5547 12.9982 21.7295C12.6946 21.9044 12.3504 21.9965 12 21.9965C11.6496 21.9965 11.3054 21.9044 11.0018 21.7295C10.6982 21.5547 10.4458 21.3031 10.27 21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>

        <div ref={menuRef} className="relative">
          <button
            type="button"
            onClick={() => setMenuOpen((open) => !open)}
            className="flex items-center gap-2 rounded-xl border border-transparent px-2 py-1.5 text-left transition-colors hover:border-[var(--app-border)] hover:bg-[#F4F8FF]"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
          >
            <div className="w-8 h-8 rounded-full bg-[rgba(29,63,208,0.1)] flex items-center justify-center">
              <span className="text-xs font-semibold text-[var(--app-primary)]">{initials || "PB"}</span>
            </div>
            <div className="hidden max-w-40 sm:block">
              <p className="truncate text-sm font-semibold text-[var(--app-text)]">{displayName}</p>
              <p className="truncate text-xs text-[var(--app-muted)]">{userEmail}</p>
            </div>
            <svg
              className={`h-4 w-4 text-[var(--app-subtle)] transition-transform ${menuOpen ? "rotate-180" : ""}`}
              viewBox="0 0 20 20"
              fill="currentColor"
              aria-hidden="true"
            >
              <path
                fillRule="evenodd"
                d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.17l3.71-3.94a.75.75 0 1 1 1.08 1.04l-4.25 4.5a.75.75 0 0 1-1.08 0l-4.25-4.5a.75.75 0 0 1 .02-1.06Z"
                clipRule="evenodd"
              />
            </svg>
          </button>

          {menuOpen ? (
            <div
              role="menu"
              className="absolute right-0 z-50 mt-2 w-64 overflow-hidden rounded-2xl border border-[var(--app-border)] bg-white shadow-xl"
            >
              <div className="border-b border-[var(--app-border)] px-4 py-3">
                <p className="truncate text-sm font-semibold text-[var(--app-text)]">{displayName}</p>
                <p className="truncate text-xs text-[var(--app-muted)]">{userEmail}</p>
              </div>
              <div className="p-2">
                <Link
                  href="/settings"
                  role="menuitem"
                  onClick={() => setMenuOpen(false)}
                  className="flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium text-[var(--app-muted)] hover:bg-[#F4F8FF] hover:text-[var(--app-text)]"
                >
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#F4F8FF] text-[var(--app-primary)]">
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                      <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="2" />
                      <path d="M12 2V5M12 19V22M4.93 4.93L7.05 7.05M16.95 16.95L19.07 19.07M2 12H5M19 12H22M4.93 19.07L7.05 16.95M16.95 7.05L19.07 4.93" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                    </svg>
                  </span>
                  Account settings
                </Link>
                <Link
                  href="/billing"
                  role="menuitem"
                  onClick={() => setMenuOpen(false)}
                  className="flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium text-[var(--app-muted)] hover:bg-[#F4F8FF] hover:text-[var(--app-text)]"
                >
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#F4F8FF] text-[var(--app-primary)]">
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                      <rect x="3" y="5" width="18" height="14" rx="2" stroke="currentColor" strokeWidth="2" />
                      <path d="M3 9H21M7 15H11" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                    </svg>
                  </span>
                  Billing
                </Link>
              </div>
              <div className="border-t border-[var(--app-border)] p-2">
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => signOut({ callbackUrl: "/login" })}
                  className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm font-medium text-red-600 hover:bg-red-50"
                >
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-red-50">
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                      <path d="M10 17L15 12L10 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                      <path d="M15 12H3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                      <path d="M12 3H19C20.1 3 21 3.9 21 5V19C21 20.1 20.1 21 19 21H12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                    </svg>
                  </span>
                  Sign out
                </button>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </header>
  );
}
