"use client";

import EmptyState from "@/components/EmptyState";
import DownloadCard from "@/components/downloads/DownloadCard";
import type { DownloadsOverview } from "@/lib/api";

const SECTIONS = [
  {
    key: "active",
    heading: "Active downloads",
    blurb: "Currently downloading data from peers.",
    emptyText: "No downloads in progress.",
  },
  {
    key: "seeding",
    heading: "Seeding",
    blurb: "Completed torrents that are still uploading to peers.",
    emptyText: "Nothing is being seeded right now.",
  },
  {
    key: "completed",
    heading: "Completed",
    blurb: "Finished torrents that have stopped seeding.",
    emptyText: "No completed torrents in the client.",
  },
  {
    key: "error",
    heading: "Errored",
    blurb: "Torrents the client could not finish (missing files, tracker errors, …).",
    emptyText: "No errored torrents.",
  },
] as const;

type DownloadsPanelProps = {
  overview: DownloadsOverview;
  onRefresh?: () => void;
};

function totalVisible(overview: DownloadsOverview): number {
  return (
    (overview.active?.length ?? 0) +
    (overview.seeding?.length ?? 0) +
    (overview.completed?.length ?? 0) +
    (overview.error?.length ?? 0) +
    (overview.other?.length ?? 0)
  );
}

export default function DownloadsPanel({ overview, onRefresh }: DownloadsPanelProps) {
  const showGlobalEmpty = totalVisible(overview) === 0;

  return (
    <div id="downloads-panel" data-downloads-panel>
      {showGlobalEmpty ? (
        <EmptyState
          icon="↓"
          title="No downloads yet"
          hint="Start one from an anime detail page — it will appear here in real time."
        />
      ) : null}

      {SECTIONS.map(({ key, heading, blurb, emptyText }) => {
        const rows = overview[key] ?? [];
        const isEmpty = rows.length === 0;

        return (
          <section
            key={key}
            className="downloads-section"
            data-downloads-section={key}
            {...(isEmpty ? { "data-downloads-empty": "1" } : {})}
          >
            <header className="downloads-section__head">
              <div>
                <h2 className="downloads-section__title">
                  {heading}
                  <span className="badge" data-downloads-section-count>
                    {rows.length}
                  </span>
                </h2>
                <p className="downloads-section__hint">{blurb}</p>
              </div>
            </header>

            <div className="downloads-section__list" data-downloads-list={key}>
              {isEmpty ? (
                <p className="downloads-section__empty" data-downloads-section-empty>
                  {emptyText}
                </p>
              ) : null}
              {rows.map((dl) => (
                <DownloadCard
                  key={dl.hash ?? `${dl.anime_id}-${dl.name}`}
                  item={dl}
                  bucket={key}
                  onCancel={onRefresh}
                />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
