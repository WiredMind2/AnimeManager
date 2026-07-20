"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import EmptyState from "@/components/EmptyState";
import TopBrowseView from "@/components/library/TopBrowseView";
import TopCategoryPicker from "@/components/library/TopCategoryPicker";
import {
  browseOffset,
  PAGE_SIZE_OPTIONS,
  type PageSizeOption,
} from "@/lib/browse";
import { formatTopLabel, topBrowseUrl, type TopCategory } from "@/lib/top";

type StreamState = "connecting" | "streaming" | "done" | "error" | "closed";

type TopPageContentProps = {
  category: TopCategory;
  label: string;
  page: number;
  pageSize: PageSizeOption;
};

function streamBadgeClass(state: StreamState): string {
  return state === "error" ? "badge badge--bad" : "badge badge--accent";
}

export default function TopPageContent({
  category,
  label,
  page,
  pageSize,
}: TopPageContentProps) {
  const router = useRouter();
  const [streamCount, setStreamCount] = useState(0);
  const [streamState, setStreamState] = useState<StreamState>("connecting");
  const [streamLabel, setStreamLabel] = useState("Connecting…");

  const offset = browseOffset(page, pageSize);
  const prevUrl =
    page > 1 ? topBrowseUrl(category, { page: page - 1, size: pageSize }) : null;
  const nextUrl = topBrowseUrl(category, { page: page + 1, size: pageSize });

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
      <header className="page-head" data-top-category={category}>
        <div>
          <h1 className="page-head__title">Top · {label}</h1>
          <p className="page-head__subtitle">
            Most popular anime in the <strong>{formatTopLabel(category)}</strong> category.
            Local catalog first when available, then remote providers stream in as they reply.
          </p>
        </div>
        <div className="page-head__meta">
          <span>
            <span className="page-head__count">{streamCount}</span> streamed
          </span>
          <span className={streamBadgeClass(streamState)}>{streamLabel}</span>
        </div>
      </header>

      <TopCategoryPicker
        value={category}
        onChange={(next) => router.push(topBrowseUrl(next, { size: pageSize }))}
      />

      <div className="library-controls">
        <label className="library-controls__size">
          <span>Per page</span>
          <select
            value={pageSize}
            onChange={(event) =>
              router.push(
                topBrowseUrl(category, {
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

      <div className="chip-row" role="toolbar" aria-label="Top browse actions">
        <Link className="chip" href="/library">
          Back to library
        </Link>
      </div>

      <TopBrowseView
        category={category}
        limit={pageSize}
        offset={offset}
        prevUrl={prevUrl}
        nextUrl={nextUrl}
        onStreamUpdate={onStreamUpdate}
      />

      {streamState === "done" && streamCount === 0 && page === 1 ? (
        <EmptyState
          icon="⌀"
          title="No anime for this category"
          hint="Try another category or search the library to seed local metadata."
        />
      ) : null}
    </>
  );
}
