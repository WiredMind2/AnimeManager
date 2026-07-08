"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import EmptyState from "@/components/EmptyState";
import SeasonBrowseView from "@/components/library/SeasonBrowseView";
import SeasonPicker from "@/components/library/SeasonPicker";
import { formatSeasonLabel, seasonBrowseUrl, type AiringSeason } from "@/lib/season";

type StreamState = "connecting" | "streaming" | "done" | "error" | "closed";

type SeasonPageContentProps = {
  year: number;
  season: AiringSeason;
  label: string;
};

function streamBadgeClass(state: StreamState): string {
  return state === "error" ? "badge badge--bad" : "badge badge--accent";
}

export default function SeasonPageContent({ year, season, label }: SeasonPageContentProps) {
  const router = useRouter();
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
      <header className="page-head" data-season={season}>
        <div>
          <h1 className="page-head__title">{label}</h1>
          <p className="page-head__subtitle">
            Anime that aired in <strong>{formatSeasonLabel(season, year)}</strong>. Local catalog
            first, then remote providers stream in as they reply.
          </p>
        </div>
        <div className="page-head__meta">
          <span>
            <span className="page-head__count">{streamCount}</span> streamed
          </span>
          <span className={streamBadgeClass(streamState)}>{streamLabel}</span>
        </div>
      </header>

      <SeasonPicker
        value={{ year, season }}
        onChange={(next) => router.push(seasonBrowseUrl(next.year, next.season))}
      />

      <div className="chip-row" role="toolbar" aria-label="Season browse actions">
        <Link className="chip" href="/library">
          Back to library
        </Link>
      </div>

      <SeasonBrowseView year={year} season={season} onStreamUpdate={onStreamUpdate} />

      {streamState === "done" && streamCount === 0 ? (
        <EmptyState
          icon="⌀"
          title="No anime for this season"
          hint="Try another quarter/year or search the library to seed local metadata."
        />
      ) : null}
    </>
  );
}
