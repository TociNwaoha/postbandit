"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { api, ApiError } from "@/lib/api";
import { BillingStatus } from "@/types";

const plans = [
  {
    id: "creator",
    name: "Creator",
    price: "$18/mo",
    platforms: "5 platforms",
    storage: "5GB storage",
    points: ["7-day trial", "Connect 5 social platforms", "5GB storage with 6GB hard stop"],
  },
  {
    id: "pro",
    name: "Pro",
    price: "$49/mo",
    platforms: "10 platforms",
    storage: "25GB storage",
    points: ["7-day trial", "Connect up to 10 platforms", "25GB storage with 30GB hard stop"],
  },
  {
    id: "elite",
    name: "Elite",
    price: "$250/mo",
    platforms: "Every supported platform",
    storage: "100GB storage",
    points: ["7-day trial", "Full platform access", "100GB storage for high-volume workflows"],
  },
];

function formatDate(value: string | null) {
  if (!value) return "Not set";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

function formatBytes(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0GB";
  const gb = bytes / 1024 / 1024 / 1024;
  if (gb >= 10) return `${Math.round(gb)}GB`;
  return `${Math.round(gb * 10) / 10}GB`;
}

export function BillingPage() {
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const notice = useMemo(() => {
    const statusParam = searchParams.get("status");
    if (statusParam === "checkout_success") {
      return "Checkout completed. Billing will update after Stripe confirms your subscription.";
    }
    if (statusParam === "checkout_cancelled") {
      return "Checkout was cancelled. You can start again whenever you are ready.";
    }
    return null;
  }, [searchParams]);

  async function loadStatus() {
    setLoading(true);
    setError(null);
    try {
      setStatus(await api.get<BillingStatus>("/api/billing/status"));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load billing status");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadStatus();
  }, []);

  async function startCheckout(plan: string) {
    setBusyAction(`checkout-${plan}`);
    setError(null);
    try {
      const response = await api.post<{ checkout_url: string }>(`/api/billing/checkout?plan=${plan}`, {});
      window.location.href = response.checkout_url;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start checkout");
    } finally {
      setBusyAction(null);
    }
  }

  async function openPortal() {
    setBusyAction("portal");
    setError(null);
    try {
      const response = await api.post<{ portal_url: string }>("/api/billing/portal", {});
      window.location.href = response.portal_url;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not open billing portal");
    } finally {
      setBusyAction(null);
    }
  }

  return (
    <div className="space-y-6">
      {notice ? (
        <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">{notice}</div>
      ) : null}
      {error ? (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      ) : null}

      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-[var(--app-subtle)]">Current plan</p>
            {loading ? (
              <div className="mt-3 inline-flex items-center gap-2 text-sm text-[var(--app-muted)]">
                <LoadingSpinner size="sm" />
                Loading billing...
              </div>
            ) : status ? (
              <>
                <h2 className="mt-2 text-2xl font-bold capitalize text-[var(--app-text)]">{status.plan_tier}</h2>
                <p className="mt-1 text-sm text-[var(--app-muted)]">
                  Status: <span className="font-medium capitalize">{status.subscription_status.replace(/_/g, " ")}</span>
                </p>
                <p className="mt-1 text-sm text-[var(--app-muted)]">
                  Platforms: {status.platforms_connected} connected / {status.platforms_allowed} allowed
                </p>
                <div className="mt-4 max-w-md">
                  <div className="flex items-center justify-between gap-3 text-sm">
                    <span className="font-medium text-[var(--app-text)]">Storage</span>
                    <span className={status.storage_blocked ? "font-semibold text-red-700" : "text-[var(--app-muted)]"}>
                      {formatBytes(status.storage_used_bytes)} / {formatBytes(status.storage_quota_bytes)}
                    </span>
                  </div>
                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-[var(--app-surface-soft)]">
                    <div
                      className={`h-full rounded-full ${
                        status.storage_blocked ? "bg-red-600" : status.storage_warning ? "bg-amber-500" : "bg-[#1D3FD0]"
                      }`}
                      style={{
                        width: `${Math.min(
                          100,
                          Math.round((status.storage_used_bytes / Math.max(1, status.storage_quota_bytes)) * 100)
                        )}%`,
                      }}
                    />
                  </div>
                  <p className="mt-2 text-xs text-[var(--app-muted)]">
                    Hard stop: {formatBytes(status.storage_hard_stop_bytes)}. Raw sources, editor assets, and render outputs count toward storage.
                  </p>
                </div>
                <p className="mt-1 text-sm text-[var(--app-muted)]">Trial ends: {formatDate(status.trial_ends_at)}</p>
              </>
            ) : null}
          </div>

          <Button type="button" variant="secondary" onClick={() => void openPortal()} loading={busyAction === "portal"}>
            Manage billing
          </Button>
        </div>
      </Card>

      {status && !status.billing_enabled ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          Stripe billing is not enabled in this environment yet. Add the Stripe env vars and enable billing before production checkout.
        </div>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        {plans.map((plan) => {
          const current = status?.plan_tier === plan.id;
          return (
            <Card key={plan.id} className={current ? "border-[#1D3FD0]" : ""}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-xl font-bold text-[var(--app-text)]">{plan.name}</h3>
                  <p className="mt-1 text-sm text-[var(--app-muted)]">{plan.platforms}</p>
                  <p className="mt-1 text-sm text-[var(--app-muted)]">{plan.storage}</p>
                </div>
                <p className="text-xl font-bold text-[var(--app-text)]">{plan.price}</p>
              </div>
              <ul className="mt-5 space-y-2 text-sm text-[var(--app-muted)]">
                {plan.points.map((point) => (
                  <li key={point}>- {point}</li>
                ))}
              </ul>
              <Button
                type="button"
                className="mt-6 w-full"
                variant={current ? "secondary" : "primary"}
                loading={busyAction === `checkout-${plan.id}`}
                onClick={() => void startCheckout(plan.id)}
              >
                {current ? "Restart checkout" : `Start ${plan.name}`}
              </Button>
              <p className="mt-3 text-center text-xs leading-5 text-[var(--app-muted)]">
                By subscribing you agree to our{" "}
                <Link href="/terms" className="underline underline-offset-2">
                  Terms of Service
                </Link>{" "}
                and{" "}
                <Link href="/privacy" className="underline underline-offset-2">
                  Privacy Policy
                </Link>
                . See our{" "}
                <Link href="/refunds" className="underline underline-offset-2">
                  Refund Policy
                </Link>
                .
              </p>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
