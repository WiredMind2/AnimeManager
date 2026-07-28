"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useToast } from "@/components/Toast";
import { api, type AnimeLibraryTorrent } from "@/lib/api";
import {
  dispatchDownloadActivityChanged,
  dispatchLibraryTorrentDeleted,
  DOWNLOAD_ACTIVITY_CHANGED_EVENT,
  DOWNLOAD_STARTED_EVENT,
  hasActiveTorrents,
  isActiveTorrentState,
  isPausedTorrentState,
  isQueuedTorrentState,
  torrentProgressPercent,
  type DownloadActivityDetail,
} from "@/lib/downloads/torrent-state";

const POLL_INTERVAL_MS = 3000;
const BOOTSTRAP_POLL_INTERVAL_MS = 1000;
const BOOTSTRAP_POLL_MAX_MS = 15000;

type DownloadedEpisodesTableProps = {
  animeId: number;
  initialTorrents: AnimeLibraryTorrent[];
};

export default function DownloadedEpisodesTable({
  animeId,
  initialTorrents,
}: DownloadedEpisodesTableProps) {
  const [torrents, setTorrents] = useState(initialTorrents);
  const { showToast } = useToast();

  useEffect(() => {
    setTorrents(initialTorrents);
  }, [initialTorrents]);

  const refreshFailedRef = useRef(false);
  const bootstrapTimerRef = useRef<number | null>(null);
  const bootstrapStartedAtRef = useRef<number | null>(null);
  const hadActiveRef = useRef(hasActiveTorrents(initialTorrents));

  const emitActivityIfChanged = useCallback(
    (items: AnimeLibraryTorrent[]) => {
      const active = hasActiveTorrents(items);
      if (active === hadActiveRef.current) return;
      hadActiveRef.current = active;
      dispatchDownloadActivityChanged({ animeId, active });
    },
    [animeId],
  );

  const refresh = useCallback(async () => {
    try {
      const { items } = await api.getAnimeLibraryTorrents(animeId);
      setTorrents(items);
      emitActivityIfChanged(items);
      refreshFailedRef.current = false;
      return items;
    } catch {
      if (!refreshFailedRef.current) {
        refreshFailedRef.current = true;
        showToast("Failed to refresh downloads.", "error");
      }
      return null;
    }
  }, [animeId, emitActivityIfChanged, showToast]);

  const stopBootstrapPoll = useCallback(() => {
    if (bootstrapTimerRef.current) {
      window.clearInterval(bootstrapTimerRef.current);
      bootstrapTimerRef.current = null;
    }
    bootstrapStartedAtRef.current = null;
  }, []);

  const startBootstrapPoll = useCallback(() => {
    if (bootstrapTimerRef.current) return;
    bootstrapStartedAtRef.current = Date.now();
    void refresh();
    bootstrapTimerRef.current = window.setInterval(() => {
      const startedAt = bootstrapStartedAtRef.current;
      if (startedAt && Date.now() - startedAt >= BOOTSTRAP_POLL_MAX_MS) {
        stopBootstrapPoll();
        void refresh();
        return;
      }
      void refresh().then((items) => {
        if (items && hasActiveTorrents(items)) {
          stopBootstrapPoll();
        }
      });
    }, BOOTSTRAP_POLL_INTERVAL_MS);
  }, [refresh, stopBootstrapPoll]);

  async function cancelTorrent(hash: string | undefined) {
    if (!hash) return;
    const snapshot = torrents;
    setTorrents((prev) =>
      prev.map((t) =>
        t.hash === hash && isActiveTorrentState(t.state)
          ? { ...t, state: "STOPPED" }
          : t,
      ),
    );
    try {
      const result = await api.cancelDownloadByHash(hash);
      if (!result.cancelled) {
        setTorrents(snapshot);
        showToast("Could not cancel download.", "error");
        return;
      }
      dispatchDownloadActivityChanged({ animeId, active: false });
      await refresh();
    } catch {
      setTorrents(snapshot);
      showToast("Failed to cancel download. Please try again.", "error");
    }
  }

  async function togglePause(hash: string | undefined, state: string) {
    if (!hash) return;
    const snapshot = torrents;
    const pausing = !isPausedTorrentState(state);
    setTorrents((prev) =>
      prev.map((t) =>
        t.hash === hash
          ? { ...t, state: pausing ? "pausedDL" : "DOWNLOADING" }
          : t,
      ),
    );
    try {
      const result = pausing
        ? await api.pauseDownload(hash)
        : await api.resumeDownload(hash);
      const ok = pausing ? result.paused : result.resumed;
      if (!ok) {
        setTorrents(snapshot);
        showToast(
          pausing ? "Could not pause torrent." : "Could not resume torrent.",
          "error",
        );
        return;
      }
      await refresh();
    } catch {
      setTorrents(snapshot);
      showToast(
        pausing
          ? "Failed to pause torrent. Please try again."
          : "Failed to resume torrent. Please try again.",
        "error",
      );
    }
  }

  async function prioritizeTorrent(hash: string | undefined) {
    if (!hash) return;
    try {
      const result = await api.prioritizeDownload(hash);
      if (!result.prioritized) {
        showToast("Could not prioritize torrent.", "error");
        return;
      }
      await refresh();
    } catch {
      showToast("Failed to prioritize torrent. Please try again.", "error");
    }
  }

  async function deleteTorrent(hash: string | undefined) {
    if (!hash) return;
    if (
      !confirm(
        "Delete this torrent and its downloaded files from disk? This cannot be undone.",
      )
    ) {
      return;
    }
    const snapshot = torrents;
    setTorrents((prev) =>
      prev.map((t) => (t.hash === hash ? { ...t, state: "DELETED", progress: t.progress } : t)),
    );
    try {
      const result = await api.deleteAnimeTorrent(animeId, hash);
      if (!result.deleted) {
        setTorrents(snapshot);
        showToast("Could not delete torrent.", "error");
        return;
      }
      dispatchLibraryTorrentDeleted({ animeId, hash });
      dispatchDownloadActivityChanged({ animeId, active: false });
      await refresh();
    } catch (err) {
      setTorrents(snapshot);
      const detail =
        err && typeof err === "object" && "status" in err
          ? ` (${String((err as { status?: unknown }).status)})`
          : "";
      console.error("deleteAnimeTorrent failed", err);
      showToast(`Failed to delete torrent${detail}. Please try again.`, "error");
    }
  }

  useEffect(() => {
    const onDownload = () => {
      dispatchDownloadActivityChanged({ animeId, active: true });
      hadActiveRef.current = true;
      startBootstrapPoll();
    };
    window.addEventListener(DOWNLOAD_STARTED_EVENT, onDownload);
    return () => window.removeEventListener(DOWNLOAD_STARTED_EVENT, onDownload);
  }, [animeId, startBootstrapPoll]);

  useEffect(() => {
    const onActivityChanged = (event: Event) => {
      const detail = (event as CustomEvent<DownloadActivityDetail>).detail;
      if (!detail || detail.animeId !== animeId) return;
      void refresh();
    };
    window.addEventListener(DOWNLOAD_ACTIVITY_CHANGED_EVENT, onActivityChanged);
    return () =>
      window.removeEventListener(DOWNLOAD_ACTIVITY_CHANGED_EVENT, onActivityChanged);
  }, [animeId, refresh]);

  useEffect(() => {
    const hasActive = hasActiveTorrents(torrents);
    if (!hasActive) return;
    const id = window.setInterval(() => {
      void refresh();
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [torrents, refresh]);

  useEffect(() => () => stopBootstrapPoll(), [stopBootstrapPoll]);

  useEffect(() => {
    emitActivityIfChanged(torrents);
  }, [torrents, emitActivityIfChanged]);

  return (
    <section id="anime-downloaded-episodes" className="detail__section">
      <div className="detail__section-title">
        <h3>Downloaded episodes</h3>
        <span className="meta">
          {torrents.length > 0
            ? `${torrents.length} torrent${torrents.length === 1 ? "" : "s"}`
            : "Nothing downloaded yet"}
        </span>
      </div>

      {torrents.length > 0 ? (
        <div className="table-wrap">
          <table className="table table--anime-downloads">
            <colgroup>
              <col className="col--release" />
              <col className="col--size" />
              <col className="col--progress" />
              <col className="col--state" />
              <col className="col--actions" />
            </colgroup>
            <thead>
              <tr>
                <th className="truncate">Release</th>
                <th className="num">Size</th>
                <th className="num">Progress</th>
                <th>State</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {torrents.map((row) => {
                const state = (row.state || "SAVED").toUpperCase();
                const pct = torrentProgressPercent(row.progress, state);
                const active = isActiveTorrentState(state);
                const paused = isPausedTorrentState(state);
                const queued = isQueuedTorrentState(state);
                const seeding = state === "SEEDING" || state === "UPLOADING";
                const canPauseOrResume =
                  Boolean(row.hash) && (active || seeding || paused) && !queued;
                const canPrioritize = Boolean(row.hash) && queued;
                const canDelete = Boolean(row.hash) && state !== "DELETED";
                return (
                  <tr key={row.hash || row.name || String(pct)}>
                    <td className="truncate" title={row.name}>
                      {row.name || row.hash || "—"}
                      {row.path ? (
                        <div style={{ fontSize: 11, color: "var(--text-faint)" }}>{row.path}</div>
                      ) : null}
                    </td>
                    <td className="num">{row.size_human || "—"}</td>
                    <td className="num" style={{ minWidth: 120 }}>
                      {pct != null ? (
                        <>
                          <div className="progress" aria-label="Download progress">
                            <div className="progress__bar" style={{ width: `${pct}%` }} />
                          </div>
                          <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                            {pct}%
                          </span>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                        {state === "COMPLETE" ? (
                          <span className="badge badge--good">{state}</span>
                        ) : active || state === "DOWNLOADING" ? (
                          <span className="badge badge--accent">{state}</span>
                        ) : state === "DELETED" ? (
                          <span className="badge" style={{ opacity: 0.75 }}>
                            {state}
                          </span>
                        ) : (
                          <span className="badge">{state}</span>
                        )}
                        {String(row.source || "").toLowerCase() === "auto" ? (
                          <span className="badge" title="Downloaded automatically">
                            AUTO
                          </span>
                        ) : null}
                      </div>
                    </td>
                    <td className="num">
                      <div style={{ display: "flex", gap: 6, justifyContent: "flex-end", flexWrap: "wrap" }}>
                        {canPrioritize ? (
                          <button
                            className="btn btn--ghost"
                            type="button"
                            onClick={() => void prioritizeTorrent(row.hash)}
                          >
                            Prioritize
                          </button>
                        ) : null}
                        {canPauseOrResume ? (
                          <button
                            className="btn btn--ghost"
                            type="button"
                            onClick={() => void togglePause(row.hash, state)}
                          >
                            {paused ? "Resume" : "Pause"}
                          </button>
                        ) : null}
                        {active ? (
                          <button
                            className="btn btn--ghost"
                            type="button"
                            onClick={() => void cancelTorrent(row.hash)}
                          >
                            Cancel
                          </button>
                        ) : null}
                        {canDelete ? (
                          <button
                            className="btn btn--small btn--danger"
                            type="button"
                            onClick={() => void deleteTorrent(row.hash)}
                          >
                            Delete
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p style={{ color: "var(--text-faint)", fontSize: 13 }}>
          Nothing downloaded yet — pick a release from the torrent search above to start.
        </p>
      )}
    </section>
  );
}
