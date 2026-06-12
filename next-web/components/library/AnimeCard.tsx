"use client";

import Link from "next/link";
import type { AnimeItem } from "@/lib/api";

const STATUS_DOT: Record<string, string> = {
  AIRING: "dot--airing",
  FINISHED: "dot--finished",
  UPCOMING: "dot--upcoming",
  UNKNOWN: "dot--unknown",
};

function truncateTitle(title: string, max = 28): string {
  if (title.length <= max) return title;
  return `${title.slice(0, max - 1)}…`;
}

function capitalize(value: string): string {
  if (!value) return value;
  return value.charAt(0).toUpperCase() + value.slice(1).toLowerCase();
}

type AnimeCardProps = {
  item: AnimeItem;
};

export default function AnimeCard({ item }: AnimeCardProps) {
  const statusLabel = (item.status || "UNKNOWN").toUpperCase();
  const statusClass = STATUS_DOT[statusLabel] ?? "dot--unknown";
  const tag = (item.tag || "NONE").toUpperCase();
  const posterFallback = truncateTitle(item.title || "?");

  return (
    <Link href={`/anime/${item.id}`} className="card">
      <div className="card__poster">
        {item.picture ? (
          <img
            src={item.picture}
            alt={item.title ?? ""}
            loading="lazy"
            referrerPolicy="no-referrer"
            onError={(e) => {
              const img = e.currentTarget;
              const div = document.createElement("div");
              div.className = "card__poster-empty";
              div.textContent = posterFallback;
              img.replaceWith(div);
            }}
          />
        ) : (
          <div className="card__poster-empty">{posterFallback}</div>
        )}

        <span className="card__status" title={statusLabel}>
          <span className={`dot ${statusClass}`} />
          {capitalize(statusLabel)}
        </span>

        {item.liked ? (
          <span className="card__like" aria-label="Liked">
            ♥
          </span>
        ) : null}

        <span className="card__overlay" aria-hidden="true" />
      </div>
      <span className="card__title" data-tag={tag}>
        {item.title}
      </span>
      <span className="card__meta">
        {item.episodes ? <span>{item.episodes} ep</span> : null}
        {item.duration ? <span>{item.duration} min</span> : null}
        {tag && tag !== "NONE" ? <span>{capitalize(tag)}</span> : null}
      </span>
    </Link>
  );
}
