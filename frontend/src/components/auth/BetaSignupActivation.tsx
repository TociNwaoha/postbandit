"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";

import { api } from "@/lib/api";

export function BetaSignupActivation({ betaAccessCode }: { betaAccessCode: string }) {
  const router = useRouter();
  const { status } = useSession();

  useEffect(() => {
    if (status !== "authenticated") return;

    async function activate() {
      try {
        await api.post("/api/auth/beta/activate", { beta_access_code: betaAccessCode });
        router.replace("/dashboard");
      } catch {
        // Invalid codes intentionally use the normal post-signup checkout path.
        router.replace("/start-trial");
      }
    }

    void activate();
  }, [betaAccessCode, router, status]);

  return null;
}
