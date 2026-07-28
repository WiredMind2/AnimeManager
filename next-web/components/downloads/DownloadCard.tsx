"use client";

import Link from "next/link";
import { useState } from "react";
import { useToast } from "@/components/Toast";
import { api } from "@/lib/api";
import type { DownloadOverviewRow } from "@/lib/api";
import {
  dispatchDownloadActivityChanged,
  dispatchLibraryTorrentDeleted,
  isPausedTorrentState,
  isQueuedTorrentState,
} from "@/lib/downloads/torrent-state";

type DownloadCardProps = {
  item: DownloadOverviewRow;
  bucket: string;
  onCancel?: () => void;
};

export default function DownloadCard({ item, bucket, onCancel }: DownloadCardProps) {
  const [cancelling, setCancelling] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [pausing, setPausing] = useState(false);
  const [prioritizing, setPrioritizing] = useState(false);
  const [hidden, setHidden] = useState(false);
  const { showToast } = useToast();
  const cardBucket = item.category || bucket;
  const pct =
    item.progress_pct !== null && item.progress_pct !== undefined
      ? Number(item.progress_pct)
      : 0;
  const paused = isPausedTorrentState(item.state);
  const queued = isQueuedTorrentState(item.state);
  const canPauseOrResume =
    Boolean(item.hash) &&
    (cardBucket === "active" || cardBucket === "seeding" || paused) &&
    !queued;
  const canPrioritize = Boolean(item.hash) && queued;
  const canCancel = Boolean(item.hash || item.anime_id) && cardBucket === "active";
  const canDelete = Boolean(item.hash);

  function notifyActivity() {
    if (item.anime_id) {
      dispatchDownloadActivityChanged({ animeId: item.anime_id, active: false });
    }
    onCancel?.();
  }

  async function handleCancel() {
    if (!item.hash && !item.anime_id) return;
    if (!window.confirm("Cancel this download? Files on disk will be kept.")) return;

    setCancelling(true);
    const snapshotHidden = hidden;
    setHidden(true);
    try {
      const result = item.hash
        ? await api.cancelDownloadByHash(item.hash)
        : await api.cancelDownload(item.anime_id!);
      if (!result.cancelled) {
        setHidden(snapshotHidden);
        showToast("Could not cancel download.", "error");
        return;
      }
      notifyActivity();
    } catch {
      setHidden(snapshotHidden);
      showToast("Failed to cancel download. Please try again.", "error");
    } finally {
      setCancelling(false);
    }
  }

  async function handleDelete() {
    if (!item.hash) return;
    if (
      !window.confirm(
        "Delete this torrent and its downloaded files from disk? This cannot be undone.",
      )
    ) {
      return;
    }

    setDeleting(true);
    const snapshotHidden = hidden;
    setHidden(true);
    try {
      const result = await api.deleteDownloadByHash(item.hash);
      if (!result.deleted) {
        setHidden(snapshotHidden);
        showToast("Could not delete torrent.", "error");
        return;
      }
      if (item.anime_id) {
        dispatchLibraryTorrentDeleted({ animeId: item.anime_id, hash: item.hash });
      }
      notifyActivity();
    } catch {
      setHidden(snapshotHidden);
      showToast("Failed to delete torrent. Please try again.", "error");
    } finally {
      setDeleting(false);
    }
  }

  async function handlePauseToggle() {
    if (!item.hash) return;
    setPausing(true);
    const wasPaused = paused;
    try {
      const result = wasPaused
        ? await api.resumeDownload(item.hash)
        : await api.pauseDownload(item.hash);
      const ok = wasPaused ? result.resumed : result.paused;
      if (!ok) {
        showToast(
          wasPaused
            ? "Could not resume torrent."
            : "Could not pause torrent.",
          "error",
        );
        return;
      }
      if (item.anime_id) {
        dispatchDownloadActivityChanged({ animeId: item.anime_id, active: true });
      }
      onCancel?.();
    } catch {
      showToast(
        wasPaused
          ? "Failed to resume torrent. Please try again."
          : "Failed to pause torrent. Please try again.",
        "error",
      );
    } finally {
      setPausing(false);
    }
  }

  async function handlePrioritize() {
    if (!item.hash) return;
    setPrioritizing(true);
    try {
      const result = await api.prioritizeDownload(item.hash);
      if (!result.prioritized) {
        showToast("Could not prioritize torrent.", "error");
        return;
      }
      if (item.anime_id) {
        dispatchDownloadActivityChanged({ animeId: item.anime_id, active: true });
      }
      onCancel?.();
    } catch {
      showToast("Failed to prioritize torrent. Please try again.", "error");
    } finally {
      setPrioritizing(false);
    }
  }

  if (hidden) {
    return null;
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
          <Link className="btn btn--ghost" href={`/anime/${item.anime_id}`}>
            Open anime
          </Link>
        ) : null}
        {canPrioritize ? (
          <button
            type="button"
            className="btn btn--ghost"
            disabled={prioritizing}
            onClick={() => void handlePrioritize()}
          >
            {prioritizing ? "Prioritizing…" : "Prioritize"}
          </button>
        ) : null}
        {canPauseOrResume ? (
          <button
            type="button"
            className="btn btn--ghost"
            disabled={pausing}
            onClick={() => void handlePauseToggle()}
          >
            {pausing ? (paused ? "Resuming…" : "Pausing…") : paused ? "Resume" : "Pause"}
          </button>
        ) : null}
        {canCancel ? (
          <button
            type="button"
            className="btn btn--danger"
            disabled={cancelling}
            onClick={() => void handleCancel()}
          >
            {cancelling ? "Cancelling…" : "Cancel"}
          </button>
        ) : null}
        {canDelete ? (
          <button
            type="button"
            className="btn btn--danger"
            disabled={deleting}
            onClick={() => void handleDelete()}
          >
            {deleting ? "Deleting…" : "Delete"}
          </button>
        ) : null}
      </div>
    </article>
  );
}
