"use client";

import Link from "next/link";

type AnimeItem = {
  id: number;
  title?: string;
  picture?: string;
  status?: string;
  liked?: boolean;
  tag?: string;
  episodes?: number;
  duration?: number;
};

const STATUS_CLASS: Record<string, string> = {
  AIRING: "dot--airing",
  FINISHED: "dot--finished",
  UPCOMING: "dot--upcoming",
  UNKNOWN: "dot--unknown",
};

function posterFallback(title: string) {
  const trimmed = title.length > 28 ? `${title.slice(0, 27)}…` : title;
  return trimmed || "?";
}

export function AnimeCard({ item }: { item: AnimeItem }) {
  const statusLabel = (item.status || "UNKNOWN").toUpperCase();
  const statusClass = STATUS_CLASS[statusLabel] || STATUS_CLASS.UNKNOWN;
  const tag = (item.tag || "NONE").toUpperCase();
  const title = item.title || "?";

  return (
    <Link href={`/anime/${item.id}`} className="card">
      <div className="card__poster">
        {item.picture ? (
          <img
            src={item.picture}
            alt={title}
            loading="lazy"
            referrerPolicy="no-referrer"
            onError={(event) => {
              const target = event.currentTarget;
              const empty = document.createElement("div");
              empty.className = "card__poster-empty";
              empty.textContent = posterFallback(title);
              target.replaceWith(empty);
            }}
          />
        ) : (
          <div className="card__poster-empty">{posterFallback(title)}</div>
        )}

        <span className="card__status" title={statusLabel}>
          <span className={`dot ${statusClass}`} />
          {statusLabel.charAt(0) + statusLabel.slice(1).toLowerCase()}
        </span>

        {item.liked ? <span className="card__like" aria-label="Liked">♥</span> : null}
        <span className="card__overlay" aria-hidden="true" />
      </div>

      <span className="card__title" data-tag={tag}>
        {title}
      </span>
      <span className="card__meta">
        {item.episodes ? <span>{item.episodes} ep</span> : null}
        {item.duration ? <span>{item.duration} min</span> : null}
        {tag !== "NONE" ? <span>{tag.charAt(0) + tag.slice(1).toLowerCase()}</span> : null}
      </span>
    </Link>
  );
}
