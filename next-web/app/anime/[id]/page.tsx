import { notFound } from "next/navigation";

import AnimeDetailPageClient, {
  parseAnimeDetailTab,
} from "@/components/anime/AnimeDetailPageClient";
import {
  ApiError,
  getAnimeForSSR,
  requestWithSsrRetry,
  type UserState,
} from "@/lib/api";
import { DEFAULT_USER_ID } from "@/lib/config";

type PageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ tab?: string }>;
};

export default async function AnimeDetailPage({ params, searchParams }: PageProps) {
  const { id } = await params;
  const query = await searchParams;
  const animeId = Number.parseInt(id, 10);
  if (!Number.isFinite(animeId) || animeId <= 0) {
    notFound();
  }

  let anime;
  let userState;

  try {
    [anime, userState] = await Promise.all([
      getAnimeForSSR(animeId),
      requestWithSsrRetry<UserState>(`/state/${animeId}?user_id=${DEFAULT_USER_ID}`).catch(
        () => ({}),
      ),
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
      initialTab={parseAnimeDetailTab(query.tab)}
    />
  );
}
