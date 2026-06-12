import AppShell from "@/components/shell/AppShell";
import TorrentSearchPage, { TorrentsTopbarAction } from "@/components/torrents/TorrentSearchPage";
import { api, ApiError } from "@/lib/api";
import type { TorrentRow } from "@/lib/api";

type PageProps = {
  searchParams: Promise<{ term?: string; anime_id?: string }>;
};

export const metadata = {
  title: "Torrent search — AnimeManager",
};

export default async function TorrentsPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const term = (params.term ?? "").trim();
  const animeIdRaw = params.anime_id?.trim();
  const animeId = animeIdRaw ? Number(animeIdRaw) : undefined;
  const animeIdValid = animeId != null && Number.isFinite(animeId) ? animeId : undefined;

  let results: TorrentRow[] | null = null;
  if (term) {
    try {
      results = await api.searchTorrents(term);
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        results = [];
      } else {
        throw err;
      }
    }
  }

  return (
    <AppShell
      activeNav="torrents"
      pageTitle="Torrent search"
      topbarActions={<TorrentsTopbarAction />}
    >
      <TorrentSearchPage
        term={term}
        animeId={animeIdValid}
        results={results}
        searched={Boolean(term)}
      />
    </AppShell>
  );
}
