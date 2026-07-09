import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";

import { BillingPage } from "@/components/billing/BillingPage";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { authOptions } from "@/lib/auth";

export default async function BillingRoute() {
  const session = await getServerSession(authOptions);
  if (!session) redirect("/login");

  return (
    <DashboardLayout title="Billing">
      <BillingPage />
    </DashboardLayout>
  );
}
