"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { api } from "@/lib/api";
import { BillingStatus } from "@/types";

const DISMISS_KEY = "postbandit-trial-banner-dismissed";

export function TrialBanner() {
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    setDismissed(sessionStorage.getItem(DISMISS_KEY) === "true");
    api.get<BillingStatus>("/api/billing/status").then(setStatus).catch(() => setStatus(null));
  }, []);

  const daysLeft = useMemo(() => {
    if (!status?.trial_ends_at) return null;
    const ms = new Date(status.trial_ends_at).getTime() - Date.now();
    return Math.ceil(ms / (1000 * 60 * 60 * 24));
  }, [status]);

  if (
    dismissed ||
    !status ||
    !status.billing_enabled ||
    status.subscription_status !== "trialing" ||
    daysLeft === null ||
    daysLeft > 3 ||
    daysLeft < 0
  ) {
    return null;
  }

  function dismiss() {
    sessionStorage.setItem(DISMISS_KEY, "true");
    setDismissed(true);
  }

  return (
    <div className="mx-8 mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p>
          Your trial ends in <span className="font-semibold">{daysLeft} day{daysLeft === 1 ? "" : "s"}</span>. Add billing now to keep publishing without interruption.
        </p>
        <div className="flex items-center gap-3">
          <Link href="/billing" className="font-semibold text-[#1D3FD0] hover:text-[#1633B8]">
            Open billing
          </Link>
          <button type="button" onClick={dismiss} className="text-xs font-semibold text-amber-800 hover:text-amber-950">
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}
