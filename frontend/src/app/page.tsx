import { LandingPage } from "@/components/marketing/LandingPage";
import { SERVER_API_URL } from "@/lib/serverApi";
import { PublicBillingPlan } from "@/types";

export const revalidate = 300;

async function getPlans(): Promise<PublicBillingPlan[]> {
  try {
    const response = await fetch(`${SERVER_API_URL}/api/billing/plans`, {
      next: { revalidate },
    });

    return response.ok ? (await response.json()) as PublicBillingPlan[] : [];
  } catch {
    // The landing page remains available if billing is temporarily unavailable.
    return [];
  }
}

export default async function HomePage() {
  return <LandingPage initialPlans={await getPlans()} />;
}
