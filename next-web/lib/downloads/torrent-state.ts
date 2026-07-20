/**
 * Active torrent states mirrored from DownloadManager._ACTIVE_STATES in
 * application/services/download_manager.py. Used by the anime detail
 * downloads table to decide when to poll and show progress.
 */
const ACTIVE_TORRENT_STATES = new Set([
  "downloading",
  "downloading_metadata",
  "metadl",
  "queueddl",
  "stalleddl",
  "forceddl",
  "checkingdl",
  "checking",
  "checking_files",
  "checking_resume",
  "checking_resume_data",
  "allocating",
  "queued",
  "queued_for_checking",
]);

export function isActiveTorrentState(state?: string | null): boolean {
  const token = (state || "").trim().toLowerCase().replace(/ /g, "_");
  return ACTIVE_TORRENT_STATES.has(token);
}

/** Return progress as 0–100 percent, or null when not applicable. */
export function torrentProgressPercent(
  progress?: number | null,
  state?: string | null,
): number | null {
  if (progress != null && Number.isFinite(progress)) {
    return Math.round(progress * 1000) / 10;
  }
  if (isActiveTorrentState(state)) {
    return 0;
  }
  return null;
}

export function hasActiveTorrents(
  torrents: ReadonlyArray<{ state?: string | null }>,
): boolean {
  return torrents.some((t) => isActiveTorrentState(t.state));
}

export type DownloadActivityDetail = {
  animeId: number;
  active: boolean;
};

export const DOWNLOAD_STARTED_EVENT = "am:download-started";
export const DOWNLOAD_ACTIVITY_CHANGED_EVENT = "am:download-activity-changed";

export function dispatchDownloadActivityChanged(detail: DownloadActivityDetail): void {
  window.dispatchEvent(
    new CustomEvent<DownloadActivityDetail>(DOWNLOAD_ACTIVITY_CHANGED_EVENT, { detail }),
  );
}
