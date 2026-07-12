import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";

import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { SocialWorkflowsPanel } from "@/components/workflows/SocialWorkflowsPanel";
import { authOptions } from "@/lib/auth";

export default async function WorkflowsPage() {
  const session = await getServerSession(authOptions);
  if (!session) redirect("/login");

  return (
    <DashboardLayout title="Workflows">
      <SocialWorkflowsPanel />
    </DashboardLayout>
  );
}
