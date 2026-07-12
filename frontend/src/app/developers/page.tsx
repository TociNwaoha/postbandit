import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { DeveloperDashboard } from "@/components/developers/DeveloperDashboard";

export default function DevelopersPage() {
  return (
    <DashboardLayout title="Developers">
      <DeveloperDashboard />
    </DashboardLayout>
  );
}
