import Link from "next/link";
import { getServerSession } from "next-auth";
import { notFound, redirect } from "next/navigation";

import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { VideoDetailPanel } from "@/components/videos/VideoDetailPanel";
import { authOptions } from "@/lib/auth";
import { SERVER_API_URL } from "@/lib/serverApi";
import { Clip, Video, VideoTranscript } from "@/types";

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

export default async function VideoDetailPage({ params }: { params: { id: string } }) {
  const session = await getServerSession(authOptions);
  if (!session) redirect("/login");

  const token = (session as any)?.accessToken;
  if (!token) redirect("/login");

  let video: Video | null = null;
  let videoLoadError: string | null = null;

  try {
    const videoRes = await fetchWithAuth(`/api/videos/${params.id}`, token);
    if (videoRes.status === 404) notFound();
    if (videoRes.status === 401 || videoRes.status === 403) redirect("/login");
    if (!videoRes.ok) {
      videoLoadError = await readErrorDetail(videoRes, "Unable to load this video right now.");
    } else {
      video = (await videoRes.json()) as Video;
    }
  } catch {
    videoLoadError = "Unable to load this video right now.";
  }

  if (!video) {
    return (
      <DashboardLayout title="Video Details">
        <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-700">
          <p>{videoLoadError || "Unable to load this video right now."}</p>
          <Link
            href="/videos"
            className="mt-4 inline-flex items-center rounded-md bg-[#1D3FD0] px-3 py-2 text-sm font-medium text-white hover:bg-[#1633B8]"
          >
            Back to Videos
          </Link>
        </div>
      </DashboardLayout>
    );
  }

  let transcript: VideoTranscript | null = null;
  let transcriptError: string | null = null;
  let clips: Clip[] = [];
  let clipsError: string | null = null;

  if (video.status === "scoring" || video.status === "ready") {
    const transcriptRes = await fetchWithAuth(`/api/videos/${params.id}/transcript`, token);
    if (transcriptRes.ok) {
      transcript = (await transcriptRes.json()) as VideoTranscript;
    } else {
      const body = await transcriptRes.json().catch(() => ({ detail: "Transcript not ready yet" }));
      transcriptError = body.detail || "Transcript not ready yet";
    }
  }

  const clipsRes = await fetchWithAuth(`/api/clips?video_id=${encodeURIComponent(params.id)}`, token);
  if (clipsRes.ok) {
    clips = (await clipsRes.json()) as Clip[];
  } else {
    const body = await clipsRes.json().catch(() => ({ detail: "Failed to load clips" }));
    clipsError = body.detail || "Failed to load clips";
  }

  return (
    <DashboardLayout title="Video Details">
      <VideoDetailPanel
        video={video}
        transcript={transcript}
        transcriptError={transcriptError}
        clips={clips}
        clipsError={clipsError}
      />
    </DashboardLayout>
  );
}
