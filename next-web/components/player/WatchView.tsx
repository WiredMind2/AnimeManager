"use client";

import { useRef } from "react";
import EpisodePicker from "./EpisodePicker";
import VideoPlayer from "./VideoPlayer";
import { usePlayback } from "@/lib/playback/use-playback";
import type { EpisodeFile, WatchTrackMap } from "@/lib/api";

export type WatchViewProps = {
  animeId: number;
  episodeFiles: EpisodeFile[];
  trackMap: WatchTrackMap;
  episodeResumeMap: Record<string, number>;
  selectedFileId: string;
  selectedFileTitle: string;
  selectedAudioTracks: { id: string; label: string }[];
  selectedSubtitleTracks: { id: string; label: string }[];
};

/** Hosts player + episode table with one shared playback session. */
export default function WatchView({
  animeId,
  episodeFiles,
  trackMap,
  episodeResumeMap,
  selectedFileId,
  selectedFileTitle,
  selectedAudioTracks,
  selectedSubtitleTracks,
}: WatchViewProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const session = usePlayback(videoRef, panelRef, {
    animeId,
    trackMap,
    initialFileId: selectedFileId,
    initialFileTitle: selectedFileTitle,
    initialAudioTracks: selectedAudioTracks,
    initialSubtitleTracks: selectedSubtitleTracks,
  });

  return (
    <section className="watch-view" data-player-host tabIndex={0}>
      <VideoPlayer
        animeId={animeId}
        videoRef={videoRef}
        panelRef={panelRef}
        session={session}
      />
      <EpisodePicker episodeFiles={episodeFiles} onPlay={session.playFile} />
    </section>
  );
}
