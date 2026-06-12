"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { TorrentTableRow } from "@/lib/api";
import { DEFAULT_USER_ID } from "@/lib/config";

type TorrentRowProps = {
  row: TorrentTableRow;
  animeId?: number;
  onFilterClick?: (facet: string, value: string) => void;
};

export default function TorrentRow({ row, animeId, onFilterClick }: TorrentRowProps) {
  const [queued, setQueued] = useState(false);
  const [busy, setBusy] = useState(false);
  const p = row.parsed;

  async function handleDownload() {
    if (!animeId || !row.link) return;
    setBusy(true);
    try {
      await api.startDownload(animeId, {
        url: row.link,
        hash_value: row.hash,
        user_id: DEFAULT_USER_ID,
      });
      setQueued(true);
      window.dispatchEvent(new CustomEvent("am:download-started"));
    } catch {
      /* ignore */
    } finally {
      setBusy(false);
    }
  }

  function pill(
    facet: string,
    value: string,
    label: string,
    className = "torrent-meta__pill",
  ) {
    return (
      <button
        type="button"
        className={className}
        data-filter-trigger={facet}
        data-filter-value={value}
        title={`Filter by ${label}`}
        onClick={(e) => {
          e.preventDefault();
          onFilterClick?.(facet, value);
        }}
      >
        {label}
      </button>
    );
  }

  return (
    <tr
      data-pub={p.publisher || ""}
      data-pub-display={p.publisher_display || ""}
      data-res={p.resolution || ""}
      data-codec={p.codec || ""}
      data-source={p.source || ""}
      data-provider={p.provider || ""}
      data-season={row.seasonLabel}
      data-episode={p.episode ?? ""}
      data-ep-start={row.epStart}
      data-ep-end={row.epEnd}
      data-episode-kind={p.episode_kind || "none"}
      data-batch={p.is_batch ? "true" : "false"}
      data-confidence={String(p.parse_confidence ?? 0)}
      data-sort-name={row.sort.name}
      data-sort-res={String(row.sort.res)}
      data-sort-season={String(row.sort.season)}
      data-sort-episode={String(row.sort.episode)}
      data-sort-size={String(row.sort.size)}
      data-sort-seeds={String(row.sort.seeds)}
      data-sort-leech={String(row.sort.leech)}
    >
      <td className="col--release">
        <div className="torrent-name" title={row.name} data-full-name={row.name}>
          {row.name}
        </div>
      </td>
      <td className="col--publisher">
        {p.publisher_display ? (
          pill("pub", p.publisher || "", p.publisher_display, "torrent-meta__pub")
        ) : (
          <span className="torrent-meta__empty">—</span>
        )}
      </td>
      <td className="col--quality num">
        {p.resolution ? pill("res", p.resolution, p.resolution) : "—"}
      </td>
      <td className="col--codec">
        {p.codec ? pill("codec", p.codec, p.codec, "torrent-meta__pill torrent-meta__pill--muted") : "—"}
      </td>
      <td className="col--source">
        {p.source && p.source !== "OTHER"
          ? pill("source", p.source, p.source, "torrent-meta__pill torrent-meta__pill--muted")
          : null}
        {p.provider
          ? pill("provider", p.provider, p.provider, "torrent-meta__pill torrent-meta__pill--muted")
          : null}
        {!(p.source && p.source !== "OTHER") && !p.provider ? "—" : null}
      </td>
      <td className="col--season num">
        {row.seasonLabel
          ? pill("season", row.seasonLabel, `S${row.seasonLabel}`, "torrent-meta__pill torrent-meta__pill--ep")
          : "—"}
      </td>
      <td className="col--episode num">
        {row.episodeLabel ? (
          pill(
            "episode-kind",
            p.episode_kind === "range" ? "range" : "single",
            row.episodeLabel,
            "torrent-meta__pill torrent-meta__pill--ep",
          )
        ) : (
          "—"
        )}
      </td>
      <td className="col--size num">{row.size_human || row.size || "—"}</td>
      <td className="col--seeds num">
        {row.seeds && row.seeds > 5 ? (
          <span className="badge badge--good">{row.seeds}</span>
        ) : row.seeds ? (
          <span className="badge">{row.seeds}</span>
        ) : (
          "—"
        )}
      </td>
      <td className="col--leech num">{row.leech ?? "—"}</td>
      <td className="col--actions num" style={{ whiteSpace: "nowrap" }}>
        {row.link ? (
          animeId ? (
            queued ? (
              <span className="badge badge--accent" title="Download queued">
                Queued
              </span>
            ) : (
              <button
                className="btn btn--primary btn--small"
                type="button"
                disabled={busy}
                onClick={handleDownload}
              >
                Download
              </button>
            )
          ) : (
            <a className="btn btn--small" href={row.link} target="_blank" rel="noreferrer">
              Open
            </a>
          )
        ) : null}
      </td>
    </tr>
  );
}
