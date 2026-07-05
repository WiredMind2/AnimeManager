/**
 * Guards POST /stop so overlapping stopSession calls (Fast Refresh remount,
 * stale unmount) do not tear down the session an in-flight load still needs.
 *
 * Manual repro without guard: start resume playback, trigger Fast Refresh while
 * session_create_ok is in flight — unmount stop races create and segment GET 404s.
 */
export type ShouldStopSessionInput = {
  /** Current global load epoch (playbackLoadEpoch) at stop time. */
  activeLoadGeneration: number;
  /** Load generation that created the session being stopped. */
  sessionLoadGeneration: number | null;
  stopUrl: string;
  /** True when invoked from the hook unmount cleanup effect. */
  isUnmountDuringLoad: boolean;
  /** True while loadPlayback holds activeLoadGenerationRef (load in progress). */
  isLoadInProgress: boolean;
};

export function shouldStopSession(input: ShouldStopSessionInput): boolean {
  const {
    activeLoadGeneration,
    sessionLoadGeneration,
    stopUrl,
    isUnmountDuringLoad,
    isLoadInProgress,
  } = input;

  if (!stopUrl) return false;
  if (sessionLoadGeneration == null) return false;

  if (isUnmountDuringLoad) {
    if (isLoadInProgress) return false;
    if (sessionLoadGeneration !== activeLoadGeneration) return false;
    return true;
  }

  // Explicit stop (load-start cleanup, user stop): allow tearing down a prior generation.
  if (sessionLoadGeneration < activeLoadGeneration) return true;
  if (sessionLoadGeneration === activeLoadGeneration) return !isLoadInProgress;
  return false;
}
