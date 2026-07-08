"use client";

import { useState } from "react";
import type { AnimeItem } from "@/lib/api";
import { formatBroadcast, formatDateRange } from "./anime-metadata-utils";

export { hasMetadataContent } from "./anime-metadata-utils";

type AnimeMetadataSectionProps = {
  anime: AnimeItem;
};

export default function AnimeMetadataSection({ anime }: AnimeMetadataSectionProps) {
  const [collapsed, setCollapsed] = useState(false);
  const aired = formatDateRange(anime.date_from, anime.date_to);
  const broadcast = formatBroadcast(anime.broadcast);
  const studios = (anime.studios || []).filter(Boolean);
  const producers = (anime.producers || []).filter(Boolean);
  const externalUrls = anime.external_urls || [];

  const rows: Array<{ label: string; value: string | null }> = [
    { label: "Aired", value: aired },
    { label: "Broadcast", value: broadcast },
    {
      label: "Popularity",
      value:
        anime.popularity != null
          ? anime.popularity.toLocaleString("en-US")
          : null,
    },
    { label: "Studios", value: studios.length ? studios.join(", ") : null },
    { label: "Producers", value: producers.length ? producers.join(", ") : null },
    { label: "Last seen", value: anime.last_seen || null },
  ].filter((row) => row.value);

  if (rows.length === 0 && !(anime.airing_lines || []).length && externalUrls.length === 0) {
    return null;
  }

  return (
    <section className="detail__section" id="anime-metadata" data-collapsed={collapsed}>
      <div className="detail__section-title">
        <h3>Metadata</h3>
        <button
          className="btn btn--ghost detail__metadata-toggle"
          type="button"
          aria-expanded={!collapsed}
          onClick={() => setCollapsed((c) => !c)}
        >
          {collapsed ? "Show details" : "Hide details"}
        </button>
      </div>

      <div className="detail__metadata-body" hidden={collapsed}>
        {(anime.airing_lines || []).length > 0 ? (
          <div className="detail__airing-callout" role="note">
            {(anime.airing_lines || []).map((line) => (
              <p key={line}>{line}</p>
            ))}
          </div>
        ) : null}

        {rows.length > 0 ? (
          <dl className="detail__metadata-grid">
            {rows.map((row) => (
              <div key={row.label} className="detail__metadata-item">
                <dt>{row.label}</dt>
                <dd>{row.value}</dd>
              </div>
            ))}
          </dl>
        ) : null}

        {externalUrls.length > 0 ? (
          <div className="detail__external-links">
            {externalUrls.map((link) => (
              <a
                key={link.url}
                className="btn btn--ghost"
                href={link.url}
                target="_blank"
                rel="noreferrer"
              >
                {link.label}
              </a>
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}
