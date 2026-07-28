"use client";

import type { EpisodeFile } from "@/lib/api";
import {
  episodePlaybackStatus,
  episodeUnplayableLabel,
  episodeUnplayableTitle,
  isEpisodePlayable,
} from "@/lib/playback/episode-playable";

export type EpisodePickerProps = {
  episodeFiles: EpisodeFile[];
  onPlay: (fileId: string, title: string) => void;
};

function formatSizeMb(sizeBytes?: number | null): string {
  if (!sizeBytes) return "—";
  return `${(sizeBytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function EpisodePicker({ episodeFiles, onPlay }: EpisodePickerProps) {
  if (!episodeFiles.length) return null;

  return (
    <div className="table-wrap watch-view__table">
      <table className="table">
        <thead>
          <tr>
            <th className="truncate">Episode file</th>
            <th className="num">Season</th>
            <th className="num">Episode</th>
            <th className="num">Size</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {episodeFiles.map((item) => {
            const fileId = String(item.file_id ?? "");
            const title = String(item.title || item.file_name || "Episode");
            const playable = isEpisodePlayable(item);
            const status = episodePlaybackStatus(item);
            return (
              <tr key={fileId}>
                <td className="truncate" title={title}>
                  {title}
                </td>
                <td className="num">{item.season ?? "—"}</td>
                <td className="num">{item.episode ?? "—"}</td>
                <td className="num">{formatSizeMb(item.size_bytes)}</td>
                <td className="num">
                  {playable ? (
                    <button
                      className="btn btn--ghost btn--small"
                      type="button"
                      data-play-file-id={fileId}
                      data-play-title={title}
                      onClick={() => onPlay(fileId, title)}
                    >
                      Play
                    </button>
                  ) : (
                    <button
                      className="btn btn--ghost btn--small"
                      type="button"
                      disabled
                      title={episodeUnplayableTitle(status)}
                    >
                      {episodeUnplayableLabel(status)}
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
