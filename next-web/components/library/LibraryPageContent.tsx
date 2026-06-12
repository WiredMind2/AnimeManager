"use client";

import { useCallback, useState } from "react";
import type { AnimeItem } from "@/lib/api";
import EmptyState from "@/components/EmptyState";
import AnimeCard from "./AnimeCard";
import FilterChips from "./FilterChips";
import LibraryView from "./LibraryView";

type StreamState = "connecting" | "streaming" | "done" | "error" | "closed";

type LibraryPageContentProps = {
  pageTitle: string;
  q: string;
  activeFilter: string;
  streamingSearch: boolean;
  items: AnimeItem[];
  hasNext: boolean;
  listStart: number;
  prevUrl: string | null;
  nextUrl: string | null;
};

function filterLabel(filter: string): string {
  const value = filter || "DEFAULT";
  return value.charAt(0) + value.slice(1).toLowerCase();
}

function streamBadgeClass(state: StreamState): string {
  return state === "error" ? "badge badge--bad" : "badge badge--accent";
}

export default function LibraryPageContent({
  pageTitle,
  q,
  activeFilter,
  streamingSearch,
  items,
  hasNext,
  listStart,
  prevUrl,
  nextUrl,
}: LibraryPageContentProps) {
  const [streamCount, setStreamCount] = useState(0);
  const [streamState, setStreamState] = useState<StreamState>("connecting");
  const [streamLabel, setStreamLabel] = useState("Connecting…");

  const onStreamUpdate = useCallback(
    (update: { count: number; streamState: StreamState; streamLabel: string }) => {
      setStreamCount(update.count);
      setStreamState(update.streamState);
      setStreamLabel(update.streamLabel);
    },
    [],
  );

  return (
    <>
      <header className="page-head">
        <div>
          <h1 className="page-head__title">{pageTitle}</h1>
          <p className="page-head__subtitle">
            {q ? (
              <>
                Showing results for <em>&ldquo;{q}&rdquo;</em>. Local catalog first, then remote
                providers stream in as they reply.
              </>
            ) : activeFilter && activeFilter !== "DEFAULT" ? (
              <>
                Library filtered by <strong>{filterLabel(activeFilter)}</strong>. Switch filters to
                refine.
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
          {streamingSearch ? (
            <>
              <span data-library-stream-count>
                <span className="page-head__count" data-library-count>
                  {streamCount}
                </span>{" "}
                streamed
              </span>
              <span
                className={streamBadgeClass(streamState)}
                data-library-stream-state={streamState}
              >
                {streamLabel}
              </span>
            </>
          ) : (
            <>
              <span>
                <span className="page-head__count">{items.length}</span> on page
              </span>
              {hasNext ? <span className="badge badge--accent">more available</span> : null}
            </>
          )}
        </div>
      </header>

      <FilterChips activeFilter={activeFilter} q={q || null} />

      {streamingSearch ? (
        <LibraryView query={q} onStreamUpdate={onStreamUpdate} />
      ) : items.length > 0 ? (
        <>
          <section className="grid">
            {items.map((item) => (
              <AnimeCard key={item.id} item={item} />
            ))}
          </section>

          <nav className="pager" aria-label="Pagination">
            <span>
              Showing <strong>{listStart + 1}</strong>–<strong>{listStart + items.length}</strong>
            </span>
            <div className="pager__actions">
              {prevUrl ? (
                <a className="btn" href={prevUrl}>
                  ← Previous
                </a>
              ) : (
                <span className="btn" aria-disabled="true">
                  ← Previous
                </span>
              )}
              {nextUrl ? (
                <a className="btn" href={nextUrl}>
                  Next →
                </a>
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
    </>
  );
}
