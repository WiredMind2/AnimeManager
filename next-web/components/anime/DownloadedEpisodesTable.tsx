"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useToast } from "@/components/Toast";
import { api, type AnimeLibraryTorrent } from "@/lib/api";
import {
  dispatchDownloadActivityChanged,
  DOWNLOAD_STARTED_EVENT,
  hasActiveTorrents,
  isActiveTorrentState,
  torrentProgressPercent,
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

  async function cancelDownload() {
    // Optimistic: demote active rows right away so the Cancel button and
    // progress shimmer disappear without waiting for the round trip.
    const snapshot = torrents;
    setTorrents((prev) =>
      prev.map((t) =>
        isActiveTorrentState(t.state) ? { ...t, state: "STOPPED" } : t,
      ),
    );
    try {
      await api.cancelDownload(animeId);
      await refresh();
    } catch {
      setTorrents(snapshot);
      showToast("Failed to cancel download. Please try again.", "error");
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
                    </td>
                    <td className="num">
                      {active ? (
                        <button className="btn btn--ghost" type="button" onClick={() => void cancelDownload()}>
                          Cancel
                        </button>
                      ) : null}
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
