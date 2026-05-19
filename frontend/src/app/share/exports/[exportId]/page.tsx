import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { PublicExportShare } from "@/types";
import { SERVER_API_URL } from "@/lib/serverApi";

interface SharePageProps {
  params: {
    exportId: string;
  };
}

async function fetchShareData(exportId: string): Promise<PublicExportShare | null> {
  const res = await fetch(`${SERVER_API_URL}/api/public/exports/${exportId}/share`, {
    cache: "no-store",
  });
  if (!res.ok) return null;
  return (await res.json()) as PublicExportShare;
}

export async function generateMetadata({ params }: SharePageProps): Promise<Metadata> {
  const data = await fetchShareData(params.exportId);
  if (!data) {
    return {
      title: "Clip Share | PostBandit",
      description: "Shared clip from PostBandit",
      robots: { index: false, follow: true },
    };
  }

  return {
    title: `${data.title} | PostBandit`,
    description: data.description,
    openGraph: {
      title: data.title,
      description: data.description,
      type: "video.other",
      url: data.share_url,
      images: data.thumbnail_url ? [{ url: data.thumbnail_url }] : undefined,
    },
    twitter: {
      card: data.thumbnail_url ? "summary_large_image" : "summary",
      title: data.title,
      description: data.description,
      images: data.thumbnail_url ? [data.thumbnail_url] : undefined,
    },
  };
}

export default async function PublicExportSharePage({ params }: SharePageProps) {
  const data = await fetchShareData(params.exportId);
  if (!data) {
    notFound();
  }

  return (
    <main className="min-h-screen bg-[#0F172A] px-4 py-10 text-white">
      <div className="mx-auto max-w-3xl space-y-6 rounded-xl border border-slate-800 bg-slate-900/50 p-6">
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-wide text-slate-400">PostBandit Share</p>
          <h1 className="text-2xl font-semibold text-white">{data.title}</h1>
          <p className="text-sm text-slate-300">{data.description}</p>
        </div>

        <video
          className="w-full rounded-lg border border-slate-800 bg-black"
          controls
          playsInline
          preload="metadata"
          poster={data.thumbnail_url || undefined}
          src={data.media_url}
        >
          Your browser does not support the video tag.
        </video>

        <div className="text-xs text-slate-400">
          <p>Shared via PostBandit</p>
        </div>
      </div>
    </main>
  );
}
