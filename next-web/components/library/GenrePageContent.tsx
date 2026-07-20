"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import EmptyState from "@/components/EmptyState";
import GenreBrowseView from "@/components/library/GenreBrowseView";
import GenrePicker from "@/components/library/GenrePicker";
import {
  browseOffset,
  PAGE_SIZE_OPTIONS,
  type PageSizeOption,
} from "@/lib/browse";
import { formatGenreLabel, genreBrowseUrl, type GenreName } from "@/lib/genres";

type StreamState = "connecting" | "streaming" | "done" | "error" | "closed";

type GenrePageContentProps = {
  genres: GenreName[];
  label: string;
  page: number;
  pageSize: PageSizeOption;
};

function streamBadgeClass(state: StreamState): string {
  return state === "error" ? "badge badge--bad" : "badge badge--accent";
}

export default function GenrePageContent({
  genres,
  label,
  page,
  pageSize,
}: GenrePageContentProps) {
  const router = useRouter();
  const [streamCount, setStreamCount] = useState(0);
  const [streamState, setStreamState] = useState<StreamState>("connecting");
  const [streamLabel, setStreamLabel] = useState("Connecting…");

  const offset = browseOffset(page, pageSize);
  const prevUrl =
    page > 1 ? genreBrowseUrl(genres, { page: page - 1, size: pageSize }) : null;
  const nextUrl = genreBrowseUrl(genres, { page: page + 1, size: pageSize });

  const onStreamUpdate = useCallback(
    (update: {
      count: number;
      streamState: StreamState;
      streamLabel: string;
      hasNext?: boolean;
    }) => {
      setStreamCount(update.count);
      setStreamState(update.streamState);
      setStreamLabel(update.streamLabel);
    },
    [],
  );

  const allLabel = formatGenreLabel(genres);
  const matchCopy =
    genres.length > 1 ? (
      <>
        tagged with <strong>all</strong> of <strong>{allLabel}</strong>
      </>
    ) : (
      <>
        tagged with <strong>{allLabel}</strong>
      </>
    );

  return (
    <>
      <header className="page-head" data-genre={genres.join(",")}>
        <div>
          <h1 className="page-head__title">{label}</h1>
          <p className="page-head__subtitle">
            Anime {matchCopy}. Local catalog first, then remote providers stream in as they
            reply.
          </p>
        </div>
        <div className="page-head__meta">
          <span>
            <span className="page-head__count">{streamCount}</span> streamed
          </span>
          <span className={streamBadgeClass(streamState)}>{streamLabel}</span>
        </div>
      </header>

      <GenrePicker
        value={genres}
        onChange={(next) => router.push(genreBrowseUrl(next, { size: pageSize }))}
      />

      <div className="library-controls">
        <label className="library-controls__size">
          <span>Per page</span>
          <select
            value={pageSize}
            onChange={(event) =>
              router.push(
                genreBrowseUrl(genres, {
                  page: 1,
                  size: Number.parseInt(event.target.value, 10) as PageSizeOption,
                }),
              )
            }
          >
            {PAGE_SIZE_OPTIONS.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="chip-row" role="toolbar" aria-label="Genre browse actions">
        <Link className="chip" href="/library">
          Back to library
        </Link>
      </div>

      <GenreBrowseView
        genres={genres}
        limit={pageSize}
        offset={offset}
        prevUrl={prevUrl}
        nextUrl={nextUrl}
        onStreamUpdate={onStreamUpdate}
      />

      {streamState === "done" && streamCount === 0 && page === 1 ? (
        <EmptyState
          icon="⌀"
          title="No anime for these genres"
          hint="Try fewer genres or search the library to seed local metadata."
        />
      ) : null}
    </>
  );
}
