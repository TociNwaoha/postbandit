"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { ApiError, api } from "@/lib/api";
import { BillingStatus, PublicBillingPlan } from "@/types";

function formatStorage(bytes: number) {
  return `${Math.round(bytes / 1024 / 1024 / 1024)}GB storage`;
}

function formatMonthlyPrice(cents: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(cents / 100) + "/mo";
}

export function StartTrialPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [loading, setLoading] = useState(true);
  const [plans, setPlans] = useState<PublicBillingPlan[]>([]);
  const [startingPlan, setStartingPlan] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const checkoutCompleted = searchParams.get("status") === "checkout_success";
  const checkoutCancelled = searchParams.get("status") === "checkout_cancelled";

  useEffect(() => {
    let active = true;
    let attempts = 0;
    let timeout: ReturnType<typeof setTimeout> | undefined;

    async function loadStatus() {
      try {
        const [status, planRows] = await Promise.all([
          api.get<BillingStatus>("/api/billing/status"),
          api.get<PublicBillingPlan[]>("/api/billing/plans"),
        ]);
        if (!active) return;
        setPlans(planRows);
        if (status.subscription_status !== "pending_checkout") {
          router.replace("/dashboard");
          return;
        }
        if (checkoutCompleted && attempts < 5) {
          attempts += 1;
          timeout = setTimeout(() => void loadStatus(), 1500);
        }
      } catch (err) {
        if (active) setError(err instanceof ApiError ? err.message : "Unable to load your trial options.");
      } finally {
        if (active) setLoading(false);
      }
    }

    void loadStatus();
    return () => {
      active = false;
      if (timeout) clearTimeout(timeout);
    };
  }, [checkoutCompleted, router]);

  async function startCheckout(plan: string) {
    setStartingPlan(plan);
    setError(null);
    try {
      const response = await api.post<{ checkout_url: string }>(`/api/billing/signup-checkout?plan=${plan}`, {});
      window.location.href = response.checkout_url;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start checkout. Please try again.");
      setStartingPlan(null);
    }
  }

  return (
    <main className="min-h-[100dvh] bg-[radial-gradient(circle_at_top,#DCE8FF_0%,#F4F8FF_42%,#FFFFFF_100%)] px-5 py-10 text-[#091528] sm:py-16">
      <div className="mx-auto max-w-6xl">
        <div className="mx-auto max-w-2xl text-center">
          <p className="inline-flex rounded-full border border-[#BDD0FF] bg-white/85 px-4 py-1.5 text-xs font-bold uppercase tracking-[0.12em] text-[#1D3FD0]">
            Choose your plan
          </p>
          <h1 className="app-display mt-5 text-4xl font-extrabold tracking-[-0.035em] sm:text-5xl">Start your {plans[0]?.trial_period_days ?? 7}-day free trial</h1>
          <p className="mt-4 text-base leading-7 text-[#4A6080]">Choose the plan that fits your workflow. A card is required to start, and you will not be charged if you cancel before the trial ends.</p>
        </div>

        {checkoutCompleted ? <div className="mx-auto mt-7 max-w-2xl rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">Checkout completed. Unlocking your workspace as Stripe confirms your trial.</div> : null}
        {checkoutCancelled ? <div className="mx-auto mt-7 max-w-2xl rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">Checkout was cancelled. Choose any plan whenever you are ready.</div> : null}
        {error ? <div className="mx-auto mt-7 max-w-2xl rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div> : null}

        <div className="mt-10 grid gap-5 md:grid-cols-2 xl:grid-cols-4">
          {plans.map((plan) => (
            <section key={plan.tier} className="relative flex min-h-[360px] flex-col rounded-3xl border border-[#D6E2F5] bg-white p-7 shadow-[0_20px_55px_rgba(9,21,40,0.09)]">
              {plan.tier === "pro" ? <span className="absolute right-5 top-5 rounded-full bg-[#E9EFFF] px-3 py-1 text-xs font-bold text-[#1D3FD0]">Most popular</span> : null}
              <h2 className="text-2xl font-extrabold">{plan.name}</h2>
              <p className="mt-4 text-4xl font-extrabold tracking-tight">{formatMonthlyPrice(plan.monthly_price_cents)}</p>
              <p className="mt-4 min-h-12 text-sm leading-6 text-[#5F708F]">{plan.description}</p>
              <ul className="mt-6 space-y-3 border-t border-[#E3EAF8] pt-6 text-sm font-medium text-[#233252]">
                {[plan.platform_label, formatStorage(plan.storage_quota_bytes), `${plan.trial_period_days}-day free trial`].map((detail) => <li key={detail} className="flex items-center gap-2"><span className="text-[#1D3FD0]">+</span>{detail}</li>)}
              </ul>
              <button type="button" disabled={loading || startingPlan !== null} onClick={() => void startCheckout(plan.tier)} className="mt-auto rounded-xl bg-[#1D3FD0] px-4 py-3 text-sm font-bold text-white transition hover:bg-[#1633B8] disabled:cursor-not-allowed disabled:opacity-60">
                {startingPlan === plan.tier ? "Opening checkout..." : `Start ${plan.name} trial`}
              </button>
            </section>
          ))}
        </div>

        <div className="mt-8 text-center">
          <button type="button" onClick={() => router.push("/dashboard")} className="text-sm font-semibold text-[#4A6080] underline underline-offset-4 hover:text-[#1D3FD0]">Skip for now</button>
          <p className="mt-2 text-xs text-[#6A7C99]">Your account will stay available, and you can start a trial whenever you are ready.</p>
        </div>
      </div>
    </main>
  );
}
