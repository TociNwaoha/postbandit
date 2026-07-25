import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";

import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { CaptionPresetsPanel } from "@/components/presets/CaptionPresetsPanel";
import { authOptions } from "@/lib/auth";

export default async function PresetsPage() {
  const session = await getServerSession(authOptions);
  if (!session) redirect("/login");

  return (
    <DashboardLayout title="Caption presets">
      <CaptionPresetsPanel />
    </DashboardLayout>
  );
}
