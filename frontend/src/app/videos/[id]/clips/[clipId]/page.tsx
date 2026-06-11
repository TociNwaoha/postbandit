import Link from "next/link";
import { getServerSession } from "next-auth";
import { notFound, redirect } from "next/navigation";

import { ClipEditorShell } from "@/components/editor/ClipEditorShell";
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
  searchParams?: {
    advancedEditor?: string;
    scheduleAt?: string;
  };
}

export default async function ClipEditorPage({ params, searchParams }: PageProps) {
  const session = await getServerSession(authOptions);
  if (!session) redirect("/login");

  const token = (session as any)?.accessToken;
  if (!token) redirect("/login");

  const [videoRes, clipRes, exportsRes] = await Promise.all([
    fetchWithAuth(`/api/videos/${params.id}`, token),
    fetchWithAuth(`/api/clips/${params.clipId}`, token),
    fetchWithAuth(`/api/exports?clip_id=${encodeURIComponent(params.clipId)}`, token),
  ]);

  if (
    videoRes.status === 401 ||
    videoRes.status === 403 ||
    clipRes.status === 401 ||
    clipRes.status === 403 ||
    exportsRes.status === 401 ||
    exportsRes.status === 403
  ) {
    redirect("/login");
  }
  if (videoRes.status === 404 || clipRes.status === 404) {
    notFound();
  }
  if (!videoRes.ok || !clipRes.ok || !exportsRes.ok) {
    const errorMessage = !videoRes.ok
      ? await readErrorDetail(videoRes, "Unable to load this video right now.")
      : !clipRes.ok
      ? await readErrorDetail(clipRes, "Unable to load this clip right now.")
      : await readErrorDetail(exportsRes, "Unable to load this clip's exports right now.");

    return (
      <div className="editor-workspace min-h-screen p-6">
        <div className="mx-auto max-w-3xl rounded-lg border border-red-500/40 bg-red-500/10 p-6 text-red-100">
          <p>{errorMessage}</p>
          <Link
            href={`/videos/${params.id}`}
            className="mt-4 inline-flex items-center rounded-md bg-[#3C6DFF] px-3 py-2 text-sm font-medium text-white hover:bg-[#2A57DD]"
          >
            Back to Video
          </Link>
        </div>
      </div>
    );
  }

  const video = (await videoRes.json()) as Video;
  const clip = (await clipRes.json()) as Clip;
  const exports = (await exportsRes.json()) as Export[];
  if (clip.video_id !== video.id) {
    notFound();
  }

  if (searchParams?.advancedEditor === "1") {
    return <ClipEditorShell video={video} clip={clip} />;
  }

  return (
    <ClipEditorPanel
      video={video}
      initialClip={clip}
      initialExports={exports}
      initialScheduleAt={typeof searchParams?.scheduleAt === "string" ? searchParams.scheduleAt : undefined}
    />
  );
}
