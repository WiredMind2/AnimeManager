"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { type EpisodeFile } from "@/lib/api";
import { uiPost } from "@/lib/api";
import { formatMb, watchPercent, watchProgressLabel, watchProgressTitle } from "@/lib/format";

type EpisodePlayerTableProps = {
  animeId: number;
  initialFiles: EpisodeFile[];
  loading?: boolean;
};

const STATUSES = [
  { value: "UNSEEN", label: "Not started" },
  { value: "IN_PROGRESS", label: "In progress" },
  { value: "SEEN", label: "Seen" },
] as const;

export default function EpisodePlayerTable({
  animeId,
  initialFiles,
  loading = false,
}: EpisodePlayerTableProps) {
  const [files, setFiles] = useState(initialFiles);

  // Own local state after first paint; re-sync when navigating to another
  // anime or when the parent's deferred episode-files fetch resolves.
  useEffect(() => {
    setFiles(initialFiles);
  }, [animeId, initialFiles]);

  async function updateProgress(fileId: string, status: string) {
    setFiles((prev) =>
      prev.map((f) =>
        f.file_id === fileId ? { ...f, watch_status: status } : f,
      ),
    );
    await uiPost(`/ui/anime/${animeId}/episode-progress`, {
      file_id: fileId,
      status,
    });
  }

  async function deleteFile(fileId: string) {
    if (!confirm("Delete this file from disk? This cannot be undone.")) return;
    setFiles((prev) => prev.filter((f) => f.file_id !== fileId));
    await uiPost(`/ui/anime/${animeId}/episode-delete`, { file_id: fileId });
  }

  return (
    <section id="anime-player" className="detail__section">
      <div className="detail__section-title">
        <h3>Episode player</h3>
        <span className="meta">
          {files.length > 0
            ? `${files.length} file${files.length === 1 ? "" : "s"} ready`
            : loading
              ? "Checking local files…"
              : "No local episode files found"}
        </span>
      </div>

      {files.length > 0 ? (
        <div className="table-wrap">
          <table className="table table--anime-episodes">
            <colgroup>
              <col className="col--episode-file" />
              <col className="col--season" />
              <col className="col--episode" />
              <col className="col--size" />
              <col className="col--progress" />
              <col className="col--actions" />
            </colgroup>
            <thead>
              <tr>
                <th className="truncate">Episode file</th>
                <th className="num">Season</th>
                <th className="num">Episode</th>
                <th className="num">Size</th>
                <th>Progress</th>
                <th className="num">Actions</th>
              </tr>
            </thead>
            <tbody>
              {files.map((item) => {
                const st = (item.watch_status || "UNSEEN").toUpperCase();
                const pct = watchPercent(item);
                const pctLabel = Math.round(pct);
                const meta = watchProgressLabel(item, pct);
                return (
                  <tr key={item.file_id}>
                    <td className="truncate" title={item.title}>
                      {item.title}
                    </td>
                    <td className="num">{item.season ?? "—"}</td>
                    <td className="num">{item.episode ?? "—"}</td>
                    <td className="num">{formatMb(item.size_bytes)}</td>
                    <td className="episode-table__progress">
                      <div
                        className={`progress progress--watch${pct > 80 ? " progress--watch-high" : ""}`}
                        role="progressbar"
                        aria-valuenow={pctLabel}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-label={`Watched ${pctLabel} percent of this episode`}
                        title={watchProgressTitle(item, pct)}
                      >
                        <div className="progress__bar" style={{ width: `${pct}%` }} />
                      </div>
                      <div className="episode-watch-meta">
                        <span className={meta === "—" ? "episode-watch-meta--muted" : undefined}>
                          {meta}
                        </span>
                      </div>
                      <form
                        className="episode-table__progress-form"
                        onSubmit={(e) => e.preventDefault()}
                      >
                        <select
                          className="input"
                          name="status"
                          style={{ height: 32 }}
                          value={st}
                          onChange={(e) =>
                            item.file_id && updateProgress(item.file_id, e.target.value)
                          }
                        >
                          {STATUSES.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                              {opt.label}
                            </option>
                          ))}
                        </select>
                      </form>
                    </td>
                    <td className="num episode-table__actions">
                      <Link
                        className="btn btn--ghost btn--small"
                        href={`/anime/${animeId}/watch?file_id=${encodeURIComponent(item.file_id || "")}`}
                      >
                        Play
                      </Link>
                      <form style={{ display: "inline" }} onSubmit={(e) => e.preventDefault()}>
                        <button
                          className="btn btn--small btn--danger"
                          type="button"
                          onClick={() => item.file_id && deleteFile(item.file_id)}
                        >
                          Delete
                        </button>
                      </form>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : loading ? (
        <div
          style={{ display: "flex", flexDirection: "column", gap: "var(--sp-3)" }}
          aria-hidden="true"
        >
          <span className="skeleton-line" style={{ width: "72%" }} />
          <span className="skeleton-line" style={{ width: "58%" }} />
          <span className="skeleton-line" style={{ width: "65%" }} />
        </div>
      ) : (
        <p style={{ color: "var(--text-faint)", fontSize: 13 }}>
          Download an episode first. The web player automatically transcodes files for browser
          playback.
        </p>
      )}
    </section>
  );
}
