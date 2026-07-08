"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { OnboardingStatus } from "@/types";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";

interface DashboardLayoutProps {
  title: string;
  children: React.ReactNode;
}

export function DashboardLayout({ title, children }: DashboardLayoutProps) {
  const router = useRouter();
  const [checkingOnboarding, setCheckingOnboarding] = useState(true);

  useEffect(() => {
    let active = true;

    async function checkOnboarding() {
      try {
        const status = await api.get<OnboardingStatus>("/api/onboarding/status");
        if (!active) return;
        if (status.should_onboard) {
          router.replace("/onboarding/start");
          return;
        }
      } catch {
        // Do not block existing app usage if onboarding status cannot be read.
      } finally {
        if (active) setCheckingOnboarding(false);
      }
    }

    void checkOnboarding();
    return () => {
      active = false;
    };
  }, [router]);

  if (checkingOnboarding) {
    return (
      <div className="app-shell app-body flex min-h-screen items-center justify-center bg-[#F4F8FF] text-sm text-[var(--app-muted)]">
        Loading workspace...
      </div>
    );
  }

  return (
    <div className="app-shell app-body flex min-h-screen">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0">
        <Header title={title} />
        <main className="flex-1 px-8 py-6 overflow-auto">{children}</main>
      </div>
    </div>
  );
}
