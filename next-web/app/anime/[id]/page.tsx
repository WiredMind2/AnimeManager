import Link from "next/link";
import { notFound } from "next/navigation";
import AppShell from "@/components/shell/AppShell";
import AnimeDetailView from "@/components/anime/AnimeDetailView";
import { api, ApiError } from "@/lib/api";
import { DEFAULT_USER_ID } from "@/lib/config";
import { truncateTitle } from "@/lib/format";

type PageProps = {
  params: Promise<{ id: string }>;
};

export default async function AnimeDetailPage({ params }: PageProps) {
  const { id } = await params;
  const animeId = Number.parseInt(id, 10);
  if (!Number.isFinite(animeId) || animeId <= 0) {
    notFound();
  }

  let anime;
  try {
    anime = await api.getAnime(animeId);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }

  const [userState, torrentSearchOptions, relationsRes, episodeRes, torrentsRes, charactersRes, picturesRes] =
    await Promise.all([
      api.getUserState(animeId, DEFAULT_USER_ID).catch(() => ({})),
      api.getTorrentSearchOptions(animeId).catch(() => ({
        catalog_title_states: [],
        manual_terms: [],
        active_terms: [],
      })),
      api.getRelations(animeId).catch(() => ({ items: [] })),
      api.getEpisodeFiles(animeId, DEFAULT_USER_ID).catch(() => ({ items: [] })),
      api.getAnimeLibraryTorrents(animeId).catch(() => ({ items: [] })),
      api.getCharacters(animeId).catch(() => ({ items: [] })),
      api.getAnimePictures(animeId).catch(() => ({ items: [] })),
    ]);

  const title = anime.title || `Anime #${animeId}`;

  return (
    <AppShell
      activeNav="library"
      pageTitle={truncateTitle(title)}
      showSearch={false}
      topbarActions={
        <>
          <Link className="btn btn--ghost" href="/library">
            ← Library
          </Link>
          <a className="btn btn--ghost" href="#anime-torrents">
            Find torrents
          </a>
        </>
      }
    >
      <AnimeDetailView
        anime={anime}
        userState={userState}
        torrentSearchOptions={torrentSearchOptions}
        relations={relationsRes.items}
        episodeFiles={episodeRes.items}
        animeTorrents={torrentsRes.items}
        characters={charactersRes.items}
        pictures={picturesRes.items}
      />
    </AppShell>
  );
}
