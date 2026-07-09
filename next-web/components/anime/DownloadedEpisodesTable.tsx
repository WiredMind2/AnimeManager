"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useToast } from "@/components/Toast";
import { api, type AnimeLibraryTorrent } from "@/lib/api";

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
  // Polling refresh runs every few seconds while a download is active; only
  // surface one toast per outage instead of re-notifying on every tick.
  const refreshFailedRef = useRef(false);

  const refresh = useCallback(async () => {
    try {
      const { items } = await api.getAnimeLibraryTorrents(animeId);
      setTorrents(items);
      refreshFailedRef.current = false;
    } catch {
      if (!refreshFailedRef.current) {
        refreshFailedRef.current = true;
        showToast("Failed to refresh downloads.", "error");
      }
    }
  }, [animeId, showToast]);

  async function cancelDownload() {
    try {
      await api.cancelDownload(animeId);
      await refresh();
    } catch {
      showToast("Failed to cancel download. Please try again.", "error");
    }
  }

  useEffect(() => {
    const onDownload = () => refresh();
    window.addEventListener("am:download-started", onDownload);
    return () => window.removeEventListener("am:download-started", onDownload);
  }, [refresh]);

  useEffect(() => {
    const hasActive = torrents.some(
      (t) => (t.state || "").toUpperCase() === "DOWNLOADING",
    );
    if (!hasActive) return;
    const id = window.setInterval(refresh, 3000);
    return () => window.clearInterval(id);
  }, [torrents, refresh]);

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
                const pct =
                  row.progress != null ? Math.round(row.progress * 1000) / 10 : null;
                const state = (row.state || "SAVED").toUpperCase();
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
                      ) : state === "DOWNLOADING" ? (
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
                      {state === "DOWNLOADING" ? (
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
