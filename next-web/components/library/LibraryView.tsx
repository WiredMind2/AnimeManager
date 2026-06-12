"use client";

import { useEffect, useRef, useState } from "react";
import { wsBackendUrl } from "@/lib/config";

type StreamState = "connecting" | "streaming" | "done" | "error" | "closed";

type StreamUpdate = {
  count: number;
  streamState: StreamState;
  streamLabel: string;
};

type LibraryViewProps = {
  query: string;
  wsPath?: string;
  limit?: number;
  onStreamUpdate?: (update: StreamUpdate) => void;
};

export default function LibraryView({
  query,
  wsPath = "/ui/library/ws",
  limit = 50,
  onStreamUpdate,
}: LibraryViewProps) {
  const gridRef = useRef<HTMLElement>(null);
  const onStreamUpdateRef = useRef(onStreamUpdate);
  onStreamUpdateRef.current = onStreamUpdate;
  const [emptyVisible, setEmptyVisible] = useState(false);

  useEffect(() => {
    const grid = gridRef.current;
    if (!grid || !query) return;

    grid.innerHTML = "";
    setEmptyVisible(false);

    const seen = new Set<string>();
    let count = 0;
    let closed = false;

    const emit = (streamState: StreamState, streamLabel: string, nextCount = count) => {
      onStreamUpdateRef.current?.({ count: nextCount, streamState, streamLabel });
    };

    const setState = (streamState: StreamState, label: string) => {
      emit(streamState, label);
    };

    const url = `${wsBackendUrl(wsPath)}?q=${encodeURIComponent(query)}&limit=${limit}`;
    let socket: WebSocket;

    try {
      socket = new WebSocket(url);
    } catch {
      setState("error", "Connection failed");
      setEmptyVisible(true);
      return;
    }

    setState("connecting", "Connecting…");

    socket.addEventListener("open", () => {
      setState("streaming", "Streaming…");
    });

    socket.addEventListener("message", (ev) => {
      let payload: { type?: string; html?: string; id?: number | string; count?: number; message?: string };
      try {
        payload = JSON.parse(String(ev.data));
      } catch {
        return;
      }
      if (!payload || typeof payload !== "object") return;

      if (payload.type === "card" && typeof payload.html === "string") {
        if (payload.id != null) {
          const key = String(payload.id);
          if (seen.has(key)) return;
          seen.add(key);
        }
        const wrapper = document.createElement("div");
        wrapper.innerHTML = payload.html;
        const card = wrapper.firstElementChild;
        if (card) {
          if (card instanceof HTMLAnchorElement) {
            const href = card.getAttribute("href");
            if (href?.startsWith("/ui/anime/")) {
              card.setAttribute("href", href.replace("/ui/anime/", "/anime/"));
            }
          }
          grid.appendChild(card);
          count += 1;
          emit("streaming", "Streaming…", count);
          setEmptyVisible(false);
        }
      } else if (payload.type === "done") {
        closed = true;
        const finalCount = typeof payload.count === "number" ? payload.count : count;
        setState("done", finalCount > 0 ? `Done · ${finalCount}` : "No results");
        setEmptyVisible(finalCount === 0);
        try {
          socket.close();
        } catch {
          /* ignore */
        }
      } else if (payload.type === "error") {
        closed = true;
        setState("error", payload.message || "Search failed");
        setEmptyVisible(count === 0);
      }
    });

    socket.addEventListener("close", () => {
      if (!closed) {
        setState("closed", count > 0 ? `Closed · ${count}` : "Closed");
      }
      if (count === 0) setEmptyVisible(true);
    });

    socket.addEventListener("error", () => {
      setState("error", "Connection error");
    });

    return () => {
      closed = true;
      try {
        socket.close();
      } catch {
        /* ignore */
      }
    };
  }, [query, wsPath, limit]);

  return (
    <>
      <section
        ref={gridRef}
        className="grid"
        data-library-stream
        data-library-stream-path={wsPath}
        data-library-stream-query={query}
      />

      <p className="page-head__subtitle" data-library-stream-empty hidden={!emptyVisible}>
        No results yet. Local catalog returned nothing and remote providers either failed or are still
        in flight.
      </p>

      <noscript>
        <p className="page-head__subtitle">
          Live streaming requires JavaScript.{" "}
          <a href={`/library?q=${encodeURIComponent(query)}&page=1`}>Reload the static results.</a>
        </p>
      </noscript>
    </>
  );
}
