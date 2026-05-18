import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import { HtmlEmbed } from "@/components/ui/html-embed";
import { backendFetch, backendFetchHtml } from "@/lib/backend";

type TorrentSearch = {
  query: string;
  items: Array<Record<string, unknown>>;
};

export default async function TorrentsPage({
  searchParams,
}: {
  searchParams: Promise<{ term?: string; anime_id?: string }>;
}) {
  const params = await searchParams;
  const term = (params.term || "").trim();
  const animeId = params.anime_id ? Number(params.anime_id) : undefined;

  let resultsHtml = "";
  if (term && animeId) {
    resultsHtml = await backendFetchHtml(
      `/ui/anime/${animeId}/torrents?term=${encodeURIComponent(term)}`,
    ).catch(() => "");
  } else if (term) {
    const data = await backendFetch<TorrentSearch>(
      `/ui/api/torrents/search?term=${encodeURIComponent(term)}`,
    ).catch(() => ({ query: term, items: [] }));
    if (data.items.length) {
      resultsHtml = `<p class="meta">${data.items.length} results for &ldquo;${data.query}&rdquo;</p>`;
    }
  }

  return (
    <AppShell
      activeNav="torrents"
      pageTitle="Torrent search"
      topbarActions={
        <Link className="btn btn--ghost" href="/downloads">
          Active downloads
        </Link>
      }
    >
      <header className="page-head">
        <div>
          <h1 className="page-head__title">Torrent search</h1>
          <p className="page-head__subtitle">
            Query the bundled search engines through the SDK. Comma-separate to merge multiple
            terms.
          </p>
        </div>
      </header>

      <form action="/torrents" method="get" className="form-row" style={{ marginBottom: "var(--sp-6)" }}>
        <input
          className="input"
          name="term"
          placeholder="e.g. SubsPlease Bleach 1080p"
          defaultValue={term}
        />
        {animeId ? <input type="hidden" name="anime_id" value={animeId} /> : null}
        <button className="btn btn--primary" type="submit">
          Search
        </button>
      </form>

      {resultsHtml ? <HtmlEmbed html={resultsHtml} /> : term ? (
        <p style={{ color: "var(--text-faint)", fontSize: 14 }}>No results.</p>
      ) : null}
    </AppShell>
  );
}
