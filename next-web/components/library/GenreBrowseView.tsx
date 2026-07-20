"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type AnimeItem } from "@/lib/api";
import { backendPath } from "@/lib/config";
import type { GenreName } from "@/lib/genres";
import AnimeCard from "./AnimeCard";
import BrowsePager from "./BrowsePager";

type StreamState = "connecting" | "streaming" | "done" | "error" | "closed";

type StreamUpdate = {
  count: number;
  streamState: StreamState;
  streamLabel: string;
  hasNext?: boolean;
};

type GenreBrowseViewProps = {
  genres: GenreName[];
  limit?: number;
  offset?: number;
  prevUrl?: string | null;
  nextUrl?: string | null;
  onStreamUpdate?: (update: StreamUpdate) => void;
};

export default function GenreBrowseView({
  genres,
  limit = 24,
  offset = 0,
  prevUrl = null,
  nextUrl: nextUrlProp = null,
  onStreamUpdate,
}: GenreBrowseViewProps) {
  const [items, setItems] = useState<AnimeItem[]>([]);
  const [emptyVisible, setEmptyVisible] = useState(false);
  const [hasNext, setHasNext] = useState(false);
  const onStreamUpdateRef = useRef(onStreamUpdate);
  onStreamUpdateRef.current = onStreamUpdate;
  const nameParam = genres.join(",");
  // Over-fetch one row so we can detect another page without a second round-trip.
  const fetchLimit = limit + 1;

  const runHttpFallback = useCallback(
    async (
      seen: Set<number>,
      emit: (
        streamState: StreamState,
        streamLabel: string,
        nextCount?: number,
        nextHasNext?: boolean,
      ) => void,
      setCount: (n: number) => void,
    ) => {
      try {
        const response = await api.browseGenre(genres, limit, offset);
        const results = response.items ?? [];
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
        setHasNext(Boolean(response.has_next));
        emit(
          "done",
          count > 0 ? `Done · ${count}` : "No results",
          count,
          Boolean(response.has_next),
        );
        setEmptyVisible(count === 0);
      } catch {
        emit("error", "Genre browse failed");
        setEmptyVisible(true);
      }
    },
    [genres, limit, offset],
  );

  useEffect(() => {
    setItems([]);
    setEmptyVisible(false);
    setHasNext(false);

    const seen = new Set<number>();
    let count = 0;
    let closed = false;
    let more = false;

    const emit = (
      streamState: StreamState,
      streamLabel: string,
      nextCount = count,
      nextHasNext = more,
    ) => {
      onStreamUpdateRef.current?.({
        count: nextCount,
        streamState,
        streamLabel,
        hasNext: nextHasNext,
      });
    };

    const appendItem = (item: AnimeItem) => {
      if (item.id != null) {
        if (seen.has(item.id)) return;
        seen.add(item.id);
      }
      if (count >= limit) {
        more = true;
        setHasNext(true);
        return;
      }
      count += 1;
      setItems((prev) => [...prev, item]);
      emit("streaming", "Streaming…", count, more);
      setEmptyVisible(false);
    };

    const finish = (finalCount: number, label: string) => {
      closed = true;
      setHasNext(more);
      emit("done", label, finalCount, more);
      setEmptyVisible(finalCount === 0);
    };

    const streamUrl =
      `${backendPath("/ui/library/genre/stream")}` +
      `?genre=${encodeURIComponent(nameParam)}` +
      `&limit=${fetchLimit}` +
      `&offset=${offset}`;

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

    emit("connecting", "Connecting…");

    source.addEventListener("open", () => {
      emit("streaming", "Streaming…");
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
      const finalCount = Number.isFinite(parsed)
        ? Math.min(parsed, limit)
        : count;
      if (Number.isFinite(parsed) && parsed > limit) more = true;
      finish(finalCount, finalCount > 0 ? `Done · ${finalCount}` : "No results");
      source.close();
    });

    source.addEventListener("error", (ev) => {
      const msg = (ev as MessageEvent).data;
      if (typeof msg === "string" && msg) {
        closed = true;
        emit("error", msg);
        setEmptyVisible(count === 0);
        source.close();
      }
    });

    source.onerror = () => {
      if (closed || count > 0) {
        if (!closed) {
          finish(count, count > 0 ? `Closed · ${count}` : "Closed");
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
  }, [nameParam, limit, offset, fetchLimit, runHttpFallback]);

  const nextUrl = hasNext ? nextUrlProp : null;

  return (
    <>
      <section className="grid" data-genre-stream data-genre-name={nameParam}>
        {items.map((item) => (
          <AnimeCard key={item.id} item={item} />
        ))}
      </section>

      {(items.length > 0 || prevUrl || nextUrl) && (
        <BrowsePager
          listStart={offset}
          itemCount={items.length}
          prevUrl={prevUrl}
          nextUrl={nextUrl}
        />
      )}

      <p className="page-head__subtitle" data-genre-stream-empty hidden={!emptyVisible}>
        No results yet. Your local catalog returned nothing and remote providers either failed or
        are still in flight.
      </p>
    </>
  );
}
