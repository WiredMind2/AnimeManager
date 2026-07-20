"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type AnimeItem, type AnimeRelation } from "@/lib/api";
import {
  buildRelationTimeline,
  formatRelationLabel,
  formatRelationYear,
  relationBadgeClass,
  type RelationTimelineEntry,
} from "@/lib/relations";
import { useCoverSrc } from "@/lib/covers/use-cover-src";

const POLL_INTERVAL_MS = 2500;
const MAX_POLL_ATTEMPTS = 15;

type AnimeRelationsSectionProps = {
  animeId: number;
  currentAnime: AnimeItem;
  initialRelations: AnimeRelation[];
  onRelationsUpdated?: (relations: AnimeRelation[]) => void;
};

function RelationPoster({ entry }: { entry: RelationTimelineEntry }) {
  const posterRef = useRef<HTMLDivElement>(null);
  const coverSrc = useCoverSrc(
    posterRef,
    entry.picture_variants,
    entry.picture,
  );

  return (
    <div className="detail__relation-poster" ref={posterRef}>
      {coverSrc ? (
        <img
          src={coverSrc}
          alt=""
          loading="lazy"
          referrerPolicy="no-referrer"
        />
      ) : (
        <div className="detail__relation-poster-empty" aria-hidden="true">
          {entry.title.slice(0, 2)}
        </div>
      )}
    </div>
  );
}

function TimelineCard({ entry }: { entry: RelationTimelineEntry }) {
  const year = formatRelationYear(entry.date_from);
  const badgeClass = relationBadgeClass(entry.relation);
  const cardClass = [
    "detail__relation-card",
    entry.isCurrent ? "detail__relation-card--current" : "",
    `detail__relation-card--${entry.timelinePosition}`,
  ]
    .filter(Boolean)
    .join(" ");

  const content = (
    <>
      <div className="detail__relation-marker" aria-hidden="true" />
      <RelationPoster entry={entry} />
      <div className="detail__relation-body">
        <span className={`detail__relation-badge ${badgeClass}`}>
          {formatRelationLabel(entry.relation)}
        </span>
        <strong className="detail__relation-title">{entry.title}</strong>
        <span className="detail__relation-meta">
          {year ? <span>{year}</span> : null}
          {entry.episodes ? <span>{entry.episodes} ep</span> : null}
          {entry.status ? <span>{entry.status}</span> : null}
        </span>
      </div>
    </>
  );

  if (entry.isCurrent) {
    return (
      <article className={cardClass} aria-current="true">
        {content}
      </article>
    );
  }

  return (
    <Link href={`/anime/${entry.rel_id}`} className={cardClass}>
      {content}
    </Link>
  );
}

export default function AnimeRelationsSection({
  animeId,
  currentAnime,
  initialRelations,
  onRelationsUpdated,
}: AnimeRelationsSectionProps) {
  const [relations, setRelations] = useState(initialRelations);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);

  useEffect(() => {
    setRelations(initialRelations);
  }, [initialRelations]);

  const timeline = useMemo(
    () => buildRelationTimeline(currentAnime, relations),
    [currentAnime, relations],
  );

  const refresh = useCallback(async () => {
    setRefreshing(true);
    setRefreshError(null);
    try {
      await api.refreshAnimeDetails(animeId);
      let latest: AnimeRelation[] = [];
      for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, POLL_INTERVAL_MS));
        const { items } = await api.getRelations(animeId);
        latest = items;
        if (items.length > 0) break;
      }
      setRelations(latest);
      onRelationsUpdated?.(latest);
    } catch {
      setRefreshError("Failed to refresh related anime. Please try again.");
    } finally {
      setRefreshing(false);
    }
  }, [animeId, onRelationsUpdated]);

  const hasRelatedEntries = relations.length > 0;

  return (
    <section className="detail__section" id="anime-relations">
      <div className="detail__section-title">
        <h3>Related anime</h3>
        {hasRelatedEntries ? (
          <span className="meta">{relations.length} related</span>
        ) : null}
        <button
          className="btn btn--ghost"
          type="button"
          onClick={refresh}
          disabled={refreshing}
        >
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {refreshError ? <p className="flash flash--error">{refreshError}</p> : null}

      {!hasRelatedEntries ? (
        <p className="detail__relation-empty">
          No related anime cached — refresh metadata to fetch sequels, prequels, and side
          stories.
        </p>
      ) : null}

      <div className="detail__relation-timeline" role="list">
        {timeline.map((entry) => (
          <div key={entry.rel_id} className="detail__relation-timeline-item" role="listitem">
            <TimelineCard entry={entry} />
          </div>
        ))}
      </div>
    </section>
  );
}
