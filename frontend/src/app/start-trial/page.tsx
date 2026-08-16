import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";

import { StartTrialPage } from "@/components/billing/StartTrialPage";
import { authOptions } from "@/lib/auth";

export default async function StartTrialRoute() {
  const session = await getServerSession(authOptions);
  if (!session) redirect("/login");
  return <StartTrialPage />;
}
