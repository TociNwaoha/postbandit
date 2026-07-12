import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";

import { OnboardingFlow } from "@/components/onboarding/OnboardingFlow";
import { authOptions } from "@/lib/auth";

type OnboardingStep = "start" | "connect" | "brand" | "plans" | "thank-you";

export async function OnboardingRoute({ step }: { step: OnboardingStep }) {
  const session = await getServerSession(authOptions);
  if (!session) redirect("/login");
  return <OnboardingFlow step={step} />;
}
