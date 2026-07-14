"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ConnectionsSummary } from "@/components/connections/ConnectionsSummary";
import { UploadModal } from "@/components/upload/UploadModal";
import { DashboardScheduleCalendar } from "@/components/videos/DashboardScheduleCalendar";
import { PlaylistImportCard } from "@/components/videos/PlaylistImportCard";
import { VideoList } from "@/components/videos/VideoList";
import { useVideos } from "@/hooks/useVideos";
import { useYoutubeImports } from "@/hooks/useYoutubeImports";

export function VideosDashboard() {
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [isVideosOpen, setIsVideosOpen] = useState(false);
  const { videos, loading, error, refresh } = useVideos();
  const { imports, refresh: refreshImports } = useYoutubeImports();

  const refreshAll = async () => {
    await Promise.all([refresh(), refreshImports()]);
  };

  return (
    <>
      <ConnectionsSummary />
      <DashboardScheduleCalendar />

      <section className="rounded-2xl border border-[var(--app-border)] bg-[var(--app-surface)] shadow-sm">
        <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
          <button
            type="button"
            onClick={() => setIsVideosOpen((current) => !current)}
            aria-expanded={isVideosOpen}
            className="group flex min-w-0 flex-1 items-center gap-3 text-left"
          >
            <span
              className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-[var(--app-border)] bg-[var(--app-surface-soft)] text-lg text-[var(--app-muted)] transition-transform ${
                isVideosOpen ? "rotate-90" : ""
              }`}
              aria-hidden="true"
            >
              ›
            </span>
            <span className="min-w-0">
              <span className="block text-xl font-semibold text-[var(--app-text)] group-hover:text-[var(--app-primary)]">
                Videos
              </span>
              <span className="mt-1 block text-sm text-[var(--app-muted)]">
                {loading ? "Loading library..." : `${videos.length} video${videos.length === 1 ? "" : "s"} in your library`}
                {imports.length > 0 ? ` · ${imports.length} playlist import${imports.length === 1 ? "" : "s"}` : ""}
              </span>
            </span>
          </button>
          <div className="flex items-center gap-2 sm:justify-end">
            <Button variant="secondary" onClick={() => setIsVideosOpen((current) => !current)}>
              {isVideosOpen ? "Hide Videos" : "View Videos"}
            </Button>
            <Button onClick={() => setIsUploadOpen(true)}>Upload Video</Button>
          </div>
        </div>

        {isVideosOpen ? (
          <div className="border-t border-[var(--app-border)] p-4">
            <VideoList
              videos={videos}
              loading={loading}
              error={error}
              onRefresh={refreshAll}
              onOpenUpload={() => setIsUploadOpen(true)}
            />

            {imports.length > 0 ? (
              <div className="mt-6 space-y-3">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-[var(--app-muted)]">Playlist Imports</h3>
                {imports.map((playlist) => (
                  <PlaylistImportCard key={playlist.id} playlist={playlist} />
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </section>

      <UploadModal
        isOpen={isUploadOpen}
        onClose={() => setIsUploadOpen(false)}
        onUploaded={refreshAll}
      />
    </>
  );
}
