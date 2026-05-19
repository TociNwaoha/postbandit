"use client";

import { useSession } from "next-auth/react";

interface HeaderProps {
  title: string;
}

export function Header({ title }: HeaderProps) {
  const { data: session } = useSession();
  const userEmail = session?.user?.email || "";
  const initials = userEmail.slice(0, 2).toUpperCase();

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

        {/* Avatar */}
        <div className="w-8 h-8 rounded-full bg-[rgba(29,63,208,0.1)] flex items-center justify-center">
          <span className="text-xs font-semibold text-[var(--app-primary)]">{initials}</span>
        </div>
      </div>
    </header>
  );
}
