"use client";

import Link from "next/link";

type EpisodeFile = {
  file_id?: string;
  title?: string;
  season?: number | null;
  episode?: number | null;
  size_bytes?: number;
  duration_seconds?: number | null;
  position_seconds?: number | null;
  watch_status?: string;
  audio_tracks?: Array<{ id: string; label: string }>;
  subtitle_tracks?: Array<{ id: string; label: string }>;
};

type WatchContext = {
  anime: { id?: number; title?: string };
  episode_files: EpisodeFile[];
  selected_file_id: string;
  selected_file_title: string;
  selected_audio_tracks: Array<{ id: string; label: string }>;
  selected_subtitle_tracks: Array<{ id: string; label: string }>;
  track_map: Record<string, { audio: EpisodeFile["audio_tracks"]; subtitles: EpisodeFile["subtitle_tracks"] }>;
  episode_resume_map: Record<string, number>;
  play_endpoint: string;
  progress_endpoint: string;
};

function watchPercent(item: EpisodeFile): number {
  const st = (item.watch_status || "UNSEEN").toUpperCase();
  if (st === "SEEN") return 100;
  const dur = item.duration_seconds;
  const pos = item.position_seconds ?? 0;
  if (dur && dur > 0) return Math.min(100, (pos / dur) * 100);
  return 0;
}

export function WatchView({ ctx }: { ctx: WatchContext }) {
  const animeId = ctx.anime.id || 0;
  const title = ctx.anime.title || `Anime #${animeId}`;

  return (
    <section className="watch-view" data-player-host>
      <nav className="watch-view__page-nav" aria-label="Watch page">
        <Link className="btn btn--ghost" href={`/anime/${animeId}`}>
          ← Back to details
        </Link>
      </nav>

      <div
        className="player-panel watch-view__panel"
        data-player-panel
        data-play-anime-id={String(animeId)}
        data-play-endpoint={ctx.play_endpoint}
        data-episode-progress-url={ctx.progress_endpoint}
        data-episode-resume-map={JSON.stringify(ctx.episode_resume_map)}
        data-player-auto-file-id={ctx.selected_file_id}
        data-player-auto-file-title={ctx.selected_file_title}
        data-player-track-map={JSON.stringify(ctx.track_map)}
        data-player-auto-fullscreen="0"
      >
        <div
          className="player-panel__video-wrap watch-view__video-wrap"
          id={`watch-wrap-${animeId}`}
        >
          <media-controller
            className="watch-view__controller"
            id={`watch-controller-${animeId}`}
            fullscreenelement={`watch-wrap-${animeId}`}
          >
            <video
              className="player-panel__video watch-view__video"
              id={`watch-video-${animeId}`}
              data-player-video
              slot="media"
              playsInline
              preload="metadata"
              crossOrigin="anonymous"
            />
            <media-loading-indicator slot="centered-chrome" />
            <media-control-bar>
              <media-play-button />
              <media-seek-backward-button seek-offset="10" />
              <media-seek-forward-button seek-offset="10" />
              <media-time-range />
              <media-time-display show-duration="" />
              <media-mute-button />
              <media-volume-range />
              <media-pip-button />
              <media-fullscreen-button />
            </media-control-bar>
          </media-controller>
          <div className="watch-view__ass-overlay" data-player-ass-overlay aria-hidden="true" />
          <div className="player-panel__status" data-player-status>
            Click play to start.
          </div>
        </div>

        <div className="player-panel__meta">
          <span data-player-title>{ctx.selected_file_title || "Nothing playing"}</span>
          <span data-player-error className="badge badge--bad" hidden />
        </div>

        <div className="player-panel__controls">
          <label className="label">
            Audio
            <select className="input player-panel__select" data-player-audio defaultValue="">
              {ctx.selected_audio_tracks.length ? (
                ctx.selected_audio_tracks.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.label}
                  </option>
                ))
              ) : (
                <option value="">Default</option>
              )}
            </select>
          </label>
          <label className="label">
            Subtitle
            <select className="input player-panel__select" data-player-subtitle defaultValue="">
              <option value="">Off</option>
              {ctx.selected_subtitle_tracks.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {ctx.episode_files.length ? (
        <div className="table-wrap watch-view__table">
          <table className="table table--anime-episodes">
            <thead>
              <tr>
                <th className="truncate">Episode file</th>
                <th className="num">Season</th>
                <th className="num">Episode</th>
                <th className="num">Size</th>
                <th>Watched</th>
                <th className="num">Play</th>
              </tr>
            </thead>
            <tbody>
              {ctx.episode_files.map((item) => {
                const pct = watchPercent(item);
                const pctLabel = Math.round(pct);
                const sizeMb = item.size_bytes
                  ? `${(item.size_bytes / 1024 / 1024).toFixed(1)} MB`
                  : "—";
                return (
                  <tr key={item.file_id}>
                    <td className="truncate" title={item.title}>
                      {item.title}
                    </td>
                    <td className="num">{item.season ?? "—"}</td>
                    <td className="num">{item.episode ?? "—"}</td>
                    <td className="num">{sizeMb}</td>
                    <td style={{ minWidth: 148 }}>
                      <div
                        className={`progress progress--watch${pct > 80 ? " progress--watch-high" : ""}`}
                        role="progressbar"
                        aria-valuenow={pctLabel}
                        aria-valuemin={0}
                        aria-valuemax={100}
                      >
                        <div className="progress__bar" style={{ width: `${pct}%` }} />
                      </div>
                      <div className="episode-watch-meta">
                        <span>{pctLabel > 0 ? `${pctLabel}%` : "—"}</span>
                      </div>
                    </td>
                    <td className="num" style={{ whiteSpace: "nowrap" }}>
                      <Link
                        className="btn btn--ghost btn--small"
                        href={`/anime/${animeId}/watch?file_id=${encodeURIComponent(item.file_id || "")}`}
                        data-play-file-id={item.file_id}
                        data-play-title={item.title}
                      >
                        Play
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
