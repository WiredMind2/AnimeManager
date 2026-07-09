import { notFound } from "next/navigation";

import AnimeDetailPageClient from "@/components/anime/AnimeDetailPageClient";

import {
  api,
  ApiError,
  getAnimeForSSR,
  requestWithSsrRetry,
  type EpisodeFile,
  type TorrentSearchOptions,
  type UserState,
} from "@/lib/api";

import { DEFAULT_USER_ID } from "@/lib/config";

type PageProps = {
  params: Promise<{ id: string }>;
};

export default async function AnimeDetailPage({ params }: PageProps) {
  const { id } = await params;
  const animeId = Number.parseInt(id, 10);
  if (!Number.isFinite(animeId) || animeId <= 0) {
    notFound();
  }

  const emptyTorrentSearchOptions: TorrentSearchOptions = {
    catalog_title_states: [],
    manual_terms: [],
    active_terms: [],
  };

  let anime;
  let userState;
  let initialTorrentSearchOptions: TorrentSearchOptions;
  let initialEpisodeFiles;
  let initialAnimeTorrents;

  try {
    [anime, userState, initialTorrentSearchOptions, initialEpisodeFiles, initialAnimeTorrents] =
      await Promise.all([
        getAnimeForSSR(animeId),
        requestWithSsrRetry<UserState>(`/state/${animeId}?user_id=${DEFAULT_USER_ID}`).catch(
          () => ({}),
        ),
        api.getTorrentSearchOptions(animeId).catch(() => emptyTorrentSearchOptions),
        requestWithSsrRetry<{ items: EpisodeFile[] }>(
          `/anime/${animeId}/episode-files?user_id=${DEFAULT_USER_ID}`,
        ).catch(() => ({ items: [] })),
        api.getAnimeLibraryTorrents(animeId).catch(() => ({ items: [] })),
      ]);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }

  return (
    <AnimeDetailPageClient
      key={animeId}
      animeId={animeId}
      initialAnime={anime}
      userState={userState}
      initialTorrentSearchOptions={initialTorrentSearchOptions}
      initialEpisodeFiles={initialEpisodeFiles.items ?? []}
      initialAnimeTorrents={initialAnimeTorrents.items ?? []}
    />
  );
}
