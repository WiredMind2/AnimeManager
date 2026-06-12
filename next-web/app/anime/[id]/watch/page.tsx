import Link from "next/link";
import { notFound } from "next/navigation";
import AppShell from "@/components/shell/AppShell";
import WatchView from "@/components/player/WatchView";
import { api, ApiError, type MediaTrackOption } from "@/lib/api";
import { truncateTitle } from "@/lib/format";

type PageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ file_id?: string }>;
};

function toTrackOptions(tracks: MediaTrackOption[] | undefined): { id: string; label: string }[] {
  return (tracks ?? []).map((t) => ({
    id: String(t.id ?? ""),
    label: String(t.label || `Track ${t.id}`),
  }));
}

export default async function AnimeWatchPage({ params, searchParams }: PageProps) {
  const { id } = await params;
  const { file_id: fileIdParam } = await searchParams;
  const animeId = Number.parseInt(id, 10);
  if (!Number.isFinite(animeId) || animeId <= 0) {
    notFound();
  }

  let watchData;
  try {
    watchData = await api.getWatchPageData(animeId, fileIdParam ?? "");
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }

  const title = watchData.anime.title || `Anime #${animeId}`;
  const pageTitle = `Watch · ${truncateTitle(title)}`;

  return (
    <AppShell
      activeNav="library"
      pageTitle={pageTitle}
      showSearch={false}
      topbarActions={
        <Link className="btn btn--ghost" href={`/anime/${animeId}`}>
          ← Back to details
        </Link>
      }
    >
      <WatchView
        animeId={animeId}
        episodeFiles={watchData.episode_files}
        trackMap={watchData.track_map}
        episodeResumeMap={watchData.episode_resume_map}
        selectedFileId={watchData.selected_file_id}
        selectedFileTitle={watchData.selected_file_title}
        selectedAudioTracks={toTrackOptions(watchData.selected_audio_tracks)}
        selectedSubtitleTracks={toTrackOptions(watchData.selected_subtitle_tracks)}
      />
    </AppShell>
  );
}
