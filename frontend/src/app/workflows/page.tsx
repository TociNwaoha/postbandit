import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";

import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { WorkflowsPanel } from "@/components/workflows/WorkflowsPanel";
import { authOptions } from "@/lib/auth";

export default async function WorkflowsPage() {
  const session = await getServerSession(authOptions);
  if (!session) redirect("/login");

  return (
    <DashboardLayout title="Workflows">
      <WorkflowsPanel />
    </DashboardLayout>
  );
}
