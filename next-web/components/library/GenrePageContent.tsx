"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import EmptyState from "@/components/EmptyState";
import GenreBrowseView from "@/components/library/GenreBrowseView";
import { formatGenreLabel, type GenreName } from "@/lib/genres";

type StreamState = "connecting" | "streaming" | "done" | "error" | "closed";

type GenrePageContentProps = {
  genre: GenreName;
  label: string;
};

function streamBadgeClass(state: StreamState): string {
  return state === "error" ? "badge badge--bad" : "badge badge--accent";
}

export default function GenrePageContent({ genre, label }: GenrePageContentProps) {
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
      <header className="page-head" data-genre={genre}>
        <div>
          <h1 className="page-head__title">{label}</h1>
          <p className="page-head__subtitle">
            Anime tagged with <strong>{formatGenreLabel(genre)}</strong>. Local catalog first,
            then remote providers stream in as they reply.
          </p>
        </div>
        <div className="page-head__meta">
          <span>
            <span className="page-head__count">{streamCount}</span> streamed
          </span>
          <span className={streamBadgeClass(streamState)}>{streamLabel}</span>
        </div>
      </header>

      <div className="chip-row" role="toolbar" aria-label="Genre browse actions">
        <Link className="chip" href="/library">
          Back to library
        </Link>
      </div>

      <GenreBrowseView genre={genre} onStreamUpdate={onStreamUpdate} />

      {streamState === "done" && streamCount === 0 ? (
        <EmptyState
          icon="⌀"
          title="No anime for this genre"
          hint="Try another genre or search the library to seed local metadata."
        />
      ) : null}
    </>
  );
}
