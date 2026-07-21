import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";

import { SlideEditor } from "@/components/carousels/SlideEditor";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { authOptions } from "@/lib/auth";

export default async function NewCarouselPage({
  searchParams,
}: {
  searchParams?: { template?: string; queueItem?: string; scheduledFor?: string; topic?: string };
}) {
  const session = await getServerSession(authOptions);
  if (!session) redirect("/login");

  const initialTemplateId = typeof searchParams?.template === "string" ? searchParams.template : undefined;
  const initialQueueItemId = typeof searchParams?.queueItem === "string" ? searchParams.queueItem : undefined;
  const initialScheduledFor =
    typeof searchParams?.scheduledFor === "string" ? searchParams.scheduledFor : undefined;
  const initialTopic = typeof searchParams?.topic === "string" ? searchParams.topic : undefined;

  return (
    <DashboardLayout title="New Carousel">
      <SlideEditor
        initialTemplateId={initialTemplateId}
        initialQueueItemId={initialQueueItemId}
        initialScheduledFor={initialScheduledFor}
        initialTopic={initialTopic}
      />
    </DashboardLayout>
  );
}
