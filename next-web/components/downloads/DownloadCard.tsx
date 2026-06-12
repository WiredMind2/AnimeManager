"use client";

import Link from "next/link";
import { useState } from "react";
import { api, uiPost } from "@/lib/api";
import type { DownloadOverviewRow } from "@/lib/api";

type DownloadCardProps = {
  item: DownloadOverviewRow;
  bucket: string;
  onCancel?: () => void;
};

export default function DownloadCard({ item, bucket, onCancel }: DownloadCardProps) {
  const [cancelling, setCancelling] = useState(false);
  const cardBucket = item.category || bucket;
  const pct =
    item.progress_pct !== null && item.progress_pct !== undefined
      ? Number(item.progress_pct)
      : 0;

  async function handleCancel() {
    if (!item.anime_id) return;
    if (!window.confirm("Cancel this download?")) return;

    setCancelling(true);
    try {
      await api.cancelDownload(item.anime_id);
    } catch {
      await uiPost(`/ui/anime/${item.anime_id}/cancel`, {});
    } finally {
      setCancelling(false);
      onCancel?.();
    }
  }

  return (
    <article
      className="download-card"
      data-downloads-card
      data-bucket={cardBucket}
      {...(item.hash ? { "data-hash": item.hash } : {})}
    >
      <div className="download-card__body">
        <div className="download-card__title">
          {item.name}
          {item.anime_title && item.anime_title !== item.name ? (
            <span className="download-card__subtitle">· {item.anime_title}</span>
          ) : null}
        </div>

        <div className="progress" aria-label="Torrent progress">
          <div className="progress__bar" style={{ width: `${pct}%` }} />
        </div>

        <div className="download-card__meta">
          <span>
            <strong style={{ color: "var(--text)" }}>{pct.toFixed(1)}%</strong> complete
          </span>
          {item.size_human ? <span>{item.size_human}</span> : null}
          {item.dl_speed_human ? <span>{item.dl_speed_human} ↓</span> : null}
          {item.up_speed_human ? <span>{item.up_speed_human} ↑</span> : null}
          {item.eta_human ? <span>ETA {item.eta_human}</span> : null}
          {item.state ? <span className="badge">{item.state}</span> : null}
        </div>
      </div>

      <div className="download-card__actions">
        {item.anime_id ? (
          <>
            <Link className="btn btn--ghost" href={`/anime/${item.anime_id}`}>
              Open anime
            </Link>
            {cardBucket === "active" ? (
              <button
                type="button"
                className="btn btn--danger"
                disabled={cancelling}
                onClick={() => void handleCancel()}
              >
                {cancelling ? "Cancelling…" : "Cancel"}
              </button>
            ) : null}
          </>
        ) : null}
      </div>
    </article>
  );
}
