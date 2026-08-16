"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { signOut } from "next-auth/react";

import { ApiError, api } from "@/lib/api";
import { BillingStatus, OnboardingStatus } from "@/types";
import { TrialBanner } from "@/components/billing/TrialBanner";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";

interface DashboardLayoutProps {
  title: string;
  children: React.ReactNode;
}

export function DashboardLayout({ title, children }: DashboardLayoutProps) {
  const router = useRouter();
  const [checkingOnboarding, setCheckingOnboarding] = useState(true);
  const [locked, setLocked] = useState(false);
  const [showBetaWelcome, setShowBetaWelcome] = useState(false);
  const [refreshAccess, setRefreshAccess] = useState(0);

  useEffect(() => {
    let active = true;

    async function checkOnboarding() {
      try {
        const billing = await api.get<BillingStatus>("/api/billing/status");
        if (!active) return;
        if (billing.subscription_status === "pending_checkout") {
          setLocked(true);
          return;
        }
        if (billing.is_beta_tester && !billing.beta_welcome_seen_at) {
          setShowBetaWelcome(true);
          return;
        }
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
  }, [refreshAccess, router]);

  async function acknowledgeBetaWelcome() {
    await api.post("/api/auth/beta/welcome-seen", {});
    setShowBetaWelcome(false);
    setCheckingOnboarding(true);
    setRefreshAccess((value) => value + 1);
  }

  if (checkingOnboarding) {
    return (
      <div className="app-shell app-body flex min-h-screen items-center justify-center bg-[#F4F8FF] text-sm text-[var(--app-muted)]">
        Loading workspace...
      </div>
    );
  }

  return (
    <div className="app-shell app-body flex min-h-screen">
      <Sidebar locked={locked} />
      <div className="flex flex-col flex-1 min-w-0">
        <Header title={title} />
        <TrialBanner />
        <main className="flex-1 px-8 py-6 overflow-auto">{locked ? <LockedWorkspacePrompt onStartTrial={() => router.push("/start-trial")} /> : children}</main>
      </div>
      {showBetaWelcome ? <BetaWelcomeModal onAcknowledge={acknowledgeBetaWelcome} /> : null}
    </div>
  );
}

function BetaWelcomeModal({ onAcknowledge }: { onAcknowledge: () => Promise<void> }) {
  const [acknowledging, setAcknowledging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function acknowledge() {
    setAcknowledging(true);
    setError(null);
    try {
      await onAcknowledge();
    } catch {
      setError("Could not save your acknowledgment. Please try again.");
    } finally {
      setAcknowledging(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/60 px-4" role="dialog" aria-modal="true" aria-labelledby="beta-welcome-title">
      <section className="w-full max-w-md rounded-3xl border border-[#C7D8FF] bg-white p-8 text-center shadow-[0_24px_70px_rgba(9,21,40,0.24)]">
        <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#1D3FD0]">PostBandit beta</p>
        <h2 id="beta-welcome-title" className="app-display mt-3 text-3xl font-extrabold tracking-[-0.03em] text-[#091528]">You are in.</h2>
        <p className="mt-4 text-sm leading-6 text-[#4A6080]">You have full access to PostBandit for 30 days. We are glad to have you helping shape what comes next.</p>
        {error ? <p className="mt-4 text-sm text-red-700">{error}</p> : null}
        <button type="button" onClick={() => void acknowledge()} disabled={acknowledging} className="mt-7 w-full rounded-xl bg-[#1D3FD0] px-5 py-3 text-sm font-bold text-white transition hover:bg-[#1633B8] disabled:cursor-not-allowed disabled:opacity-60">
          {acknowledging ? "Saving..." : "Got it"}
        </button>
      </section>
    </div>
  );
}

function LockedWorkspacePrompt({ onStartTrial }: { onStartTrial: () => void }) {
  const [showDelete, setShowDelete] = useState(false);
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  async function deleteAccount(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setDeleteError(null);
    if (confirmation !== "DELETE") {
      setDeleteError("Type DELETE to confirm account deletion.");
      return;
    }
    setDeleting(true);
    try {
      await api.post<void>("/api/auth/me/delete", { current_password: password, confirm_text: confirmation });
      await signOut({ callbackUrl: "/signup?account=deleted" });
    } catch (error) {
      setDeleteError(error instanceof ApiError ? error.message : "Could not delete your account.");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="flex min-h-[calc(100vh-9rem)] items-center justify-center">
      <section className="w-full max-w-xl rounded-3xl border border-[#C7D8FF] bg-white p-8 text-center shadow-[0_24px_70px_rgba(29,63,208,0.14)] sm:p-10">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-[#E9EFFF] text-[#1D3FD0]">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="m9 5 8 7-8 7V5Z" fill="currentColor" />
          </svg>
        </div>
        <p className="mt-6 text-sm font-bold uppercase tracking-[0.12em] text-[#1D3FD0]">Workspace locked</p>
        <h2 className="app-display mt-3 text-3xl font-extrabold tracking-[-0.03em] text-[#091528]">Start your free trial to unlock PostBandit</h2>
        <p className="mt-4 text-sm leading-6 text-[#4A6080]">Choose a plan and add a card to begin your 7-day trial. You can return to this step whenever you are ready.</p>
        <button type="button" onClick={onStartTrial} className="mt-7 rounded-xl bg-[#1D3FD0] px-5 py-3 text-sm font-bold text-white transition hover:bg-[#1633B8]">Start your free trial</button>
        <div className="mt-7 border-t border-[#E3EAF8] pt-5">
          <button type="button" onClick={() => setShowDelete((visible) => !visible)} className="text-xs font-semibold text-[#6A7C99] underline underline-offset-4 hover:text-red-700">Delete this account</button>
          {showDelete ? (
            <form onSubmit={(event) => void deleteAccount(event)} className="mx-auto mt-4 max-w-sm space-y-3 text-left">
              <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Current password" autoComplete="current-password" required className="w-full rounded-lg border border-[#D6E2F5] px-3 py-2 text-sm outline-none focus:border-[#1D3FD0]" />
              <input type="text" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} placeholder="Type DELETE to confirm" required className="w-full rounded-lg border border-[#D6E2F5] px-3 py-2 text-sm outline-none focus:border-[#1D3FD0]" />
              {deleteError ? <p className="text-xs text-red-700">{deleteError}</p> : null}
              <button type="submit" disabled={deleting} className="w-full rounded-lg border border-red-200 px-3 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-60">{deleting ? "Deleting account..." : "Permanently delete account"}</button>
            </form>
          ) : null}
        </div>
      </section>
    </div>
  );
}
