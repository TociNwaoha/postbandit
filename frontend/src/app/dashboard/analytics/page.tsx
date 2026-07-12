import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";

import { AnalyticsDashboard } from "@/components/analytics/AnalyticsDashboard";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { authOptions } from "@/lib/auth";

export default async function AnalyticsPage() {
  const session = await getServerSession(authOptions);
  if (!session) redirect("/login");

  return (
    <DashboardLayout title="Analytics">
      <AnalyticsDashboard />
    </DashboardLayout>
  );
}
