import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import { LibraryStream } from "@/components/library/library-stream";
import { AnimeCard } from "@/components/ui/anime-card";
import { EmptyState } from "@/components/ui/empty-state";
import { FilterChips } from "@/components/ui/filter-chips";
import { backendFetch } from "@/lib/backend";

type LibraryResponse = {
  mode: "list" | "search";
  query: string;
  items: Array<Record<string, unknown>>;
  has_next: boolean;
  list_start: number;
  page: number;
  page_size: number;
  filter: string;
  streaming_search?: boolean;
  search_ws_path?: string;
};

type ConfigResponse = {
  filter_options: Array<{ value: string; label: string; dot?: string | null }>;
  page_size: number;
};

export default async function LibraryPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; filter?: string; page?: string }>;
}) {
  const params = await searchParams;
  const query = (params.q || "").trim();
  const filter = (params.filter || "DEFAULT").toUpperCase();
  const page = Math.max(1, Number(params.page || "1") || 1);

  const [library, config] = await Promise.all([
    backendFetch<LibraryResponse>(
      `/ui/api/library?filter=${encodeURIComponent(filter)}&q=${encodeURIComponent(query)}&page=${page}`,
    ),
    backendFetch<ConfigResponse>("/ui/api/config"),
  ]);

  const streaming = Boolean(library.streaming_search && query);
  const pageTitle = query ? "Search results" : "Library";
  const listStart = library.list_start || 0;
  const itemCount = library.items.length;

  const pageUrl = (pageNum: number) => {
    const parts = [`page=${pageNum}`];
    if (filter && filter !== "DEFAULT") parts.push(`filter=${filter}`);
    if (query) parts.push(`q=${encodeURIComponent(query)}`);
    return `/library?${parts.join("&")}`;
  };

  return (
    <AppShell
      activeNav="library"
      activeFilter={filter}
      pageTitle={pageTitle}
      topbarQuery={query}
      topbarActions={
        <>
          <Link className="btn btn--ghost" href="/torrents">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path d="M12 3v12" />
              <path d="M6 9l6 6 6-6" />
            </svg>
            Find torrents
          </Link>
          <Link className="btn btn--primary" href="/downloads">
            Downloads
          </Link>
        </>
      }
    >
      <header className="page-head">
        <div>
          <h1 className="page-head__title">{pageTitle}</h1>
          <p className="page-head__subtitle">
            {query ? (
              <>
                Showing results for <em>&ldquo;{query}&rdquo;</em>. Local catalog first, then remote
                providers stream in as they reply.
              </>
            ) : filter !== "DEFAULT" ? (
              <>
                Library filtered by <strong>{filter.charAt(0) + filter.slice(1).toLowerCase()}</strong>.
                Switch filters to refine.
              </>
            ) : (
              <>
                Your full anime catalog. Filter, search, and queue downloads — every action goes
                through the embedded SDK.
              </>
            )}
          </p>
        </div>
        <div className="page-head__meta">
          {streaming ? (
            <span data-library-stream-count>
              <span className="page-head__count" data-library-count>
                0
              </span>{" "}
              streamed
            </span>
          ) : (
            <>
              <span>
                <span className="page-head__count">{itemCount}</span> on page
              </span>
              {library.has_next ? <span className="badge badge--accent">more available</span> : null}
            </>
          )}
          {streaming ? (
            <span className="badge badge--accent" data-library-stream-state="connecting">
              Connecting…
            </span>
          ) : null}
        </div>
      </header>

      <FilterChips options={config.filter_options} activeFilter={filter} query={query} />

      {streaming ? (
        <LibraryStream path={library.search_ws_path || "/ui/library/ws"} query={query} />
      ) : itemCount ? (
        <>
          <section className="grid">
            {library.items.map((item) => (
              <AnimeCard key={String(item.id)} item={item as never} />
            ))}
          </section>
          <nav className="pager" aria-label="Pagination">
            <span>
              Showing <strong>{listStart + 1}</strong>–<strong>{listStart + itemCount}</strong>
            </span>
            <div className="pager__actions">
              {page > 1 ? (
                <Link className="btn" href={pageUrl(page - 1)}>
                  ← Previous
                </Link>
              ) : (
                <span className="btn" aria-disabled="true">
                  ← Previous
                </span>
              )}
              {library.has_next ? (
                <Link className="btn" href={pageUrl(page + 1)}>
                  Next →
                </Link>
              ) : (
                <span className="btn" aria-disabled="true">
                  Next →
                </span>
              )}
            </div>
          </nav>
        </>
      ) : (
        <EmptyState
          icon="⌀"
          title="No anime to show"
          hint="Try a different filter, broaden your search, or hit the torrent search to seed the library."
        />
      )}
    </AppShell>
  );
}
