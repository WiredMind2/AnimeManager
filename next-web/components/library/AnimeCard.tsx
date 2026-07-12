"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { MouseEvent } from "react";
import type { AnimeItem } from "@/lib/api";

const STATUS_DOT: Record<string, string> = {
  AIRING: "dot--airing",
  FINISHED: "dot--finished",
  UPCOMING: "dot--upcoming",
  UNKNOWN: "dot--unknown",
};

const LIKE_SUFFIX = " ♥";

function truncateTitle(title: string, max = 28): string {
  if (title.length <= max) return title;
  return `${title.slice(0, max - 1)}…`;
}

function capitalize(value: string): string {
  if (!value) return value;
  return value.charAt(0).toUpperCase() + value.slice(1).toLowerCase();
}

function displayTitle(item: AnimeItem): string {
  const base = item.title ?? "";
  return item.liked ? `${base}${LIKE_SUFFIX}` : base;
}

type AnimeCardProps = {
  item: AnimeItem;
};

export default function AnimeCard({ item }: AnimeCardProps) {
  const router = useRouter();
  const statusLabel = (item.status || "UNKNOWN").toUpperCase();
  const statusClass = STATUS_DOT[statusLabel] ?? "dot--unknown";
  const tag = (item.tag || "NONE").toUpperCase();
  const title = displayTitle(item);
  const posterFallback = truncateTitle(title || "?");

  function openTorrentSearch(event: MouseEvent) {
    event.preventDefault();
    event.stopPropagation();
    router.push(`/anime/${item.id}?tab=torrents`);
  }

  return (
    <Link
      href={`/anime/${item.id}`}
      className="card"
      onContextMenu={openTorrentSearch}
      title="Right-click to search torrents"
    >
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

        <span className="card__overlay" aria-hidden="true" />
      </div>
      <span className="card__title" data-tag={tag}>
        {title.trim() ? (
          title
        ) : (
          <span className="card__title-skeleton" aria-hidden="true" />
        )}
      </span>
      <span className="card__meta">
        {item.episodes ? <span>{item.episodes} ep</span> : null}
        {item.duration ? <span>{item.duration} min</span> : null}
        {tag && tag !== "NONE" ? <span>{capitalize(tag)}</span> : null}
      </span>
    </Link>
  );
}
