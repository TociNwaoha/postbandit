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
  const { videos, loading, error, refresh } = useVideos();
  const { imports, refresh: refreshImports } = useYoutubeImports();

  const refreshAll = async () => {
    await Promise.all([refresh(), refreshImports()]);
  };

  return (
    <>
      <ConnectionsSummary />
      <DashboardScheduleCalendar />

      <div className="mb-6 flex items-center justify-between gap-4">
        <h2 className="text-2xl font-semibold text-[var(--app-text)]">Videos</h2>
        <Button onClick={() => setIsUploadOpen(true)}>Upload Video</Button>
      </div>

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

      <UploadModal
        isOpen={isUploadOpen}
        onClose={() => setIsUploadOpen(false)}
        onUploaded={refreshAll}
      />
    </>
  );
}
