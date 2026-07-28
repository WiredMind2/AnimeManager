export type StartDownloadResult = {
  started: boolean;
  skipped?: boolean;
  reason?: string;
};

/** True when the API declined to queue a new download. */
export function isStartDownloadSkipped(result: StartDownloadResult): boolean {
  return result.skipped === true || result.started === false;
}

export function startDownloadFailureMessage(result: StartDownloadResult): string {
  if (result.reason?.trim()) return result.reason.trim();
  if (result.skipped) return "Download was skipped.";
  return "Download was not started.";
}
