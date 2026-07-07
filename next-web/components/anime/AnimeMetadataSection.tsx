"use client";

import type { AnimeItem } from "@/lib/api";

type AnimeMetadataSectionProps = {
  anime: AnimeItem;
};

function formatDateRange(dateFrom?: number, dateTo?: number): string | null {
  if (!dateFrom) return null;
  const fmt = (ts: number) =>
    new Date(ts * 1000).toLocaleDateString(undefined, {
      day: "2-digit",
      month: "short",
      year: "numeric",
      timeZone: "UTC",
    });
  if (dateTo) return `${fmt(dateFrom)} → ${fmt(dateTo)}`;
  return `${fmt(dateFrom)} → ?`;
}

function formatBroadcast(broadcast?: string): string | null {
  if (!broadcast) return null;
  const parts = broadcast.split("-");
  if (parts.length !== 3) return broadcast;
  const weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const [w, h, m] = parts.map((p) => Number.parseInt(p, 10));
  if (!Number.isFinite(w) || w < 0 || w > 6) return broadcast;
  return `${weekdays[w]} ${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

export default function AnimeMetadataSection({ anime }: AnimeMetadataSectionProps) {
  const aired = formatDateRange(anime.date_from, anime.date_to);
  const broadcast = formatBroadcast(anime.broadcast);
  const studios = (anime.studios || []).filter(Boolean);
  const producers = (anime.producers || []).filter(Boolean);
  const externalUrls = anime.external_urls || [];

  const rows: Array<{ label: string; value: string | null }> = [
    { label: "Aired", value: aired },
    { label: "Broadcast", value: broadcast },
    { label: "Popularity", value: anime.popularity != null ? String(anime.popularity) : null },
    { label: "Studios", value: studios.length ? studios.join(", ") : null },
    { label: "Producers", value: producers.length ? producers.join(", ") : null },
    { label: "Last seen", value: anime.last_seen || null },
  ].filter((row) => row.value);

  if (rows.length === 0 && !(anime.airing_lines || []).length && externalUrls.length === 0) {
    return null;
  }

  return (
    <section className="detail__section detail__metadata">
      <div className="detail__section-title">
        <h3>Metadata</h3>
      </div>

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
    </section>
  );
}
