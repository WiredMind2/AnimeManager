"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type AnimeItem } from "@/lib/api";
import { backendPath } from "@/lib/config";
import type { GenreName } from "@/lib/genres";
import AnimeCard from "./AnimeCard";

type StreamState = "connecting" | "streaming" | "done" | "error" | "closed";

type StreamUpdate = {
  count: number;
  streamState: StreamState;
  streamLabel: string;
};

type GenreBrowseViewProps = {
  genre: GenreName;
  limit?: number;
  onStreamUpdate?: (update: StreamUpdate) => void;
};

export default function GenreBrowseView({
  genre,
  limit = 50,
  onStreamUpdate,
}: GenreBrowseViewProps) {
  const [items, setItems] = useState<AnimeItem[]>([]);
  const [emptyVisible, setEmptyVisible] = useState(false);
  const onStreamUpdateRef = useRef(onStreamUpdate);
  onStreamUpdateRef.current = onStreamUpdate;

  const runHttpFallback = useCallback(
    async (
      seen: Set<number>,
      emit: (streamState: StreamState, streamLabel: string, nextCount?: number) => void,
      setCount: (n: number) => void,
    ) => {
      try {
        const results = await api.browseGenre(genre, limit);
        let count = 0;
        const next: AnimeItem[] = [];
        for (const item of results) {
          if (item.id != null) {
            if (seen.has(item.id)) continue;
            seen.add(item.id);
          }
          next.push(item);
          count += 1;
        }
        setItems(next);
        setCount(count);
        emit("done", count > 0 ? `Done · ${count}` : "No results", count);
        setEmptyVisible(count === 0);
      } catch {
        emit("error", "Genre browse failed");
        setEmptyVisible(true);
      }
    },
    [genre, limit],
  );

  useEffect(() => {
    setItems([]);
    setEmptyVisible(false);

    const seen = new Set<number>();
    let count = 0;
    let closed = false;

    const emit = (streamState: StreamState, streamLabel: string, nextCount = count) => {
      onStreamUpdateRef.current?.({ count: nextCount, streamState, streamLabel });
    };

    const setState = (streamState: StreamState, label: string) => {
      emit(streamState, label);
    };

    const appendItem = (item: AnimeItem) => {
      if (item.id != null) {
        if (seen.has(item.id)) return;
        seen.add(item.id);
      }
      count += 1;
      setItems((prev) => [...prev, item]);
      emit("streaming", "Streaming…", count);
      setEmptyVisible(false);
    };

    const finish = (finalCount: number, label: string) => {
      closed = true;
      setState("done", label);
      setEmptyVisible(finalCount === 0);
    };

    const streamUrl =
      `${backendPath("/ui/library/genre/stream")}` +
      `?genre=${encodeURIComponent(genre)}` +
      `&limit=${limit}`;

    if (typeof EventSource === "undefined") {
      void runHttpFallback(seen, emit, (n) => {
        count = n;
      });
      return;
    }

    let source: EventSource;
    try {
      source = new EventSource(streamUrl);
    } catch {
      void runHttpFallback(seen, emit, (n) => {
        count = n;
      });
      return;
    }

    setState("connecting", "Connecting…");

    source.addEventListener("open", () => {
      setState("streaming", "Streaming…");
    });

    source.addEventListener("card", (ev) => {
      try {
        appendItem(JSON.parse(ev.data) as AnimeItem);
      } catch {
        /* ignore malformed card */
      }
    });

    source.addEventListener("done", (ev) => {
      const parsed = Number.parseInt(ev.data, 10);
      const finalCount = Number.isFinite(parsed) ? parsed : count;
      finish(finalCount, finalCount > 0 ? `Done · ${finalCount}` : "No results");
      source.close();
    });

    source.addEventListener("error", (ev) => {
      const msg = (ev as MessageEvent).data;
      if (typeof msg === "string" && msg) {
        closed = true;
        setState("error", msg);
        setEmptyVisible(count === 0);
        source.close();
      }
    });

    source.onerror = () => {
      if (closed || count > 0) {
        if (!closed) {
          setState("closed", count > 0 ? `Closed · ${count}` : "Closed");
          if (count === 0) setEmptyVisible(true);
        }
        source.close();
        return;
      }
      closed = true;
      source.close();
      void runHttpFallback(seen, emit, (n) => {
        count = n;
      });
    };

    return () => {
      closed = true;
      try {
        source.close();
      } catch {
        /* ignore */
      }
    };
  }, [genre, limit, runHttpFallback]);

  return (
    <>
      <section className="grid" data-genre-stream data-genre-name={genre}>
        {items.map((item) => (
          <AnimeCard key={item.id} item={item} />
        ))}
      </section>

      <p className="page-head__subtitle" data-genre-stream-empty hidden={!emptyVisible}>
        No results yet. Your local catalog returned nothing and remote providers either failed or
        are still in flight.
      </p>
    </>
  );
}
