"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import EmptyState from "@/components/EmptyState";
import SeasonBrowseView from "@/components/library/SeasonBrowseView";
import SeasonPicker from "@/components/library/SeasonPicker";
import {
  browseOffset,
  PAGE_SIZE_OPTIONS,
  type PageSizeOption,
} from "@/lib/browse";
import { formatSeasonLabel, seasonBrowseUrl, type AiringSeason } from "@/lib/season";

type StreamState = "connecting" | "streaming" | "done" | "error" | "closed";

type SeasonPageContentProps = {
  year: number;
  season: AiringSeason;
  label: string;
  page: number;
  pageSize: PageSizeOption;
};

function streamBadgeClass(state: StreamState): string {
  return state === "error" ? "badge badge--bad" : "badge badge--accent";
}

export default function SeasonPageContent({
  year,
  season,
  label,
  page,
  pageSize,
}: SeasonPageContentProps) {
  const router = useRouter();
  const [streamCount, setStreamCount] = useState(0);
  const [streamState, setStreamState] = useState<StreamState>("connecting");
  const [streamLabel, setStreamLabel] = useState("Connecting…");

  const offset = browseOffset(page, pageSize);
  const prevUrl =
    page > 1
      ? seasonBrowseUrl(year, season, { page: page - 1, size: pageSize })
      : null;
  const nextUrl = seasonBrowseUrl(year, season, { page: page + 1, size: pageSize });

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
        onChange={(next) =>
          router.push(seasonBrowseUrl(next.year, next.season, { size: pageSize }))
        }
      />

      <div className="library-controls">
        <label className="library-controls__size">
          <span>Per page</span>
          <select
            value={pageSize}
            onChange={(event) =>
              router.push(
                seasonBrowseUrl(year, season, {
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

      <div className="chip-row" role="toolbar" aria-label="Season browse actions">
        <Link className="chip" href="/library">
          Back to library
        </Link>
      </div>

      <SeasonBrowseView
        year={year}
        season={season}
        limit={pageSize}
        offset={offset}
        prevUrl={prevUrl}
        nextUrl={nextUrl}
        onStreamUpdate={onStreamUpdate}
      />

      {streamState === "done" && streamCount === 0 && page === 1 ? (
        <EmptyState
          icon="⌀"
          title="No anime for this season"
          hint="Try another quarter/year or search the library to seed local metadata."
        />
      ) : null}
    </>
  );
}
