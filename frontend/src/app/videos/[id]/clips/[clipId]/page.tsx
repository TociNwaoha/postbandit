import Link from "next/link";
import { getServerSession } from "next-auth";
import { notFound, redirect } from "next/navigation";

import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { ClipEditorPanel } from "@/components/videos/ClipEditorPanel";
import { authOptions } from "@/lib/auth";
import { SERVER_API_URL } from "@/lib/serverApi";
import { Clip, Export, Video } from "@/types";

async function fetchWithAuth(path: string, token: string) {
  return fetch(`${SERVER_API_URL}${path}`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
  });
}

async function readErrorDetail(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json();
    if (body?.detail && typeof body.detail === "string" && body.detail.trim()) {
      return body.detail.trim();
    }
  } catch {
    // Keep fallback when response is not JSON.
  }
  return fallback;
}

interface PageProps {
  params: {
    id: string;
    clipId: string;
  };
}

export default async function ClipEditorPage({ params }: PageProps) {
  const session = await getServerSession(authOptions);
  if (!session) redirect("/login");

  const token = (session as any)?.accessToken;
  if (!token) redirect("/login");

  const [videoRes, clipRes, exportsRes] = await Promise.all([
    fetchWithAuth(`/api/videos/${params.id}`, token),
    fetchWithAuth(`/api/clips/${params.clipId}`, token),
    fetchWithAuth(`/api/exports?clip_id=${encodeURIComponent(params.clipId)}`, token),
  ]);

  if (videoRes.status === 401 || videoRes.status === 403 || clipRes.status === 401 || clipRes.status === 403) {
    redirect("/login");
  }
  if (videoRes.status === 404 || clipRes.status === 404) {
    notFound();
  }
  if (!videoRes.ok || !clipRes.ok) {
    const errorMessage = !videoRes.ok
      ? await readErrorDetail(videoRes, "Unable to load this video right now.")
      : await readErrorDetail(clipRes, "Unable to load this clip right now.");

    return (
      <DashboardLayout title="Clip Review & Export">
        <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-700">
          <p>{errorMessage}</p>
          <Link
            href={`/videos/${params.id}`}
            className="mt-4 inline-flex items-center rounded-md bg-[#1D3FD0] px-3 py-2 text-sm font-medium text-white hover:bg-[#1633B8]"
          >
            Back to Video
          </Link>
        </div>
      </DashboardLayout>
    );
  }

  const video = (await videoRes.json()) as Video;
  const clip = (await clipRes.json()) as Clip;
  if (clip.video_id !== video.id) {
    notFound();
  }

  let exports: Export[] = [];
  if (exportsRes.ok) {
    exports = (await exportsRes.json()) as Export[];
  }

  return (
    <DashboardLayout title="Clip Review & Export">
      <ClipEditorPanel video={video} initialClip={clip} initialExports={exports} />
    </DashboardLayout>
  );
}
