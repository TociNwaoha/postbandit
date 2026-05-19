import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";

import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { MetaInstagramReviewPanel } from "@/components/review/MetaInstagramReviewPanel";
import { authOptions } from "@/lib/auth";

export default async function MetaInstagramReviewPage() {
  const session = await getServerSession(authOptions);
  if (!session) redirect("/login");

  return (
    <DashboardLayout title="Meta Instagram Review">
      <MetaInstagramReviewPanel />
    </DashboardLayout>
  );
}
