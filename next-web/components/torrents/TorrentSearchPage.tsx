"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";
import EmptyState from "@/components/EmptyState";
import type { TorrentRow } from "@/lib/api";
import { torrentRowFromApi } from "@/lib/torrentRow";
import TorrentResultsTable from "./TorrentResultsTable";

type TorrentSearchPageProps = {
  term: string;
  animeId?: number;
  results: TorrentRow[] | null;
  searched: boolean;
  allowNsfw?: boolean;
};

export default function TorrentSearchPage({
  term,
  animeId,
  results,
  searched,
  allowNsfw = false,
}: TorrentSearchPageProps) {
  const router = useRouter();
  const [query, setQuery] = useState(term);
  const [showNsfw, setShowNsfw] = useState(allowNsfw);

  useEffect(() => {
    setQuery(term);
  }, [term]);

  useEffect(() => {
    setShowNsfw(allowNsfw);
  }, [allowNsfw]);

  const onSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const params = new URLSearchParams();
    const trimmed = query.trim();
    if (trimmed) params.set("term", trimmed);
    if (animeId != null) params.set("anime_id", String(animeId));
    if (showNsfw) params.set("allow_nsfw", "true");
    const qs = params.toString();
    router.push(qs ? `/torrents?${qs}` : "/torrents");
  };

  const tableRows = useMemo(
    () => (results ?? []).map((row, index) => torrentRowFromApi(row, index)),
    [results],
  );

  const hasResults = tableRows.length > 0;

  return (
    <>
      <header className="page-head">
        <div>
          <h1 className="page-head__title">Torrent search</h1>
          <p className="page-head__subtitle">
            Query the bundled search engines through the SDK. Comma-separate to merge multiple terms.
          </p>
        </div>
      </header>

      <form
        action="/torrents"
        method="get"
        className="form-row"
        style={{ marginBottom: "var(--sp-6)" }}
        onSubmit={onSubmit}
      >
        <input
          className="input"
          name="term"
          placeholder="e.g. SubsPlease Bleach 1080p"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {animeId != null ? <input type="hidden" name="anime_id" value={animeId} /> : null}
        <label className="torrent-search__nsfw-toggle">
          <input
            type="checkbox"
            name="allow_nsfw"
            value="true"
            checked={showNsfw}
            onChange={(e) => setShowNsfw(e.target.checked)}
          />
          <span>Include NSFW / hentai</span>
        </label>
        <button className="btn btn--primary" type="submit">
          Search
        </button>
      </form>

      {hasResults ? (
        <section>
          <TorrentResultsTable rows={tableRows} animeId={animeId} hideNsfw={!showNsfw} />
        </section>
      ) : searched ? (
        <EmptyState
          icon="⌕"
          title="No matches for that term"
          hint="Try a broader query or remove publisher prefixes."
        />
      ) : (
        <EmptyState
          icon="⌕"
          title="Search torrents"
          hint='Enter a query above. Tip: from an anime page click "Find torrents" to pre-fill it.'
        />
      )}
    </>
  );
}

export function TorrentsTopbarAction() {
  return (
    <Link className="btn btn--ghost" href="/downloads">
      Active downloads
    </Link>
  );
}
