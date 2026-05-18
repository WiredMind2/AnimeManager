"use client";

import { useEffect, useMemo, useState } from "react";

import { browserWsBase } from "@/lib/backend";

export function LibraryStream({
  path,
  query,
}: {
  path: string;
  query: string;
}) {
  const [status, setStatus] = useState("connecting");
  const [count, setCount] = useState(0);
  const [html, setHtml] = useState("");
  const url = useMemo(() => {
    const base = browserWsBase();
    return `${base}${path}?q=${encodeURIComponent(query)}`;
  }, [path, query]);

  useEffect(() => {
    let socket: WebSocket | null = null;
    try {
      socket = new WebSocket(url);
    } catch {
      setStatus("error");
      return;
    }

    socket.addEventListener("open", () => setStatus("streaming"));
    socket.addEventListener("message", (event) => {
      let payload: Record<string, unknown>;
      try {
        payload = JSON.parse(event.data);
      } catch {
        return;
      }
      if (payload.type === "card" && typeof payload.html === "string") {
        setHtml((prev) => prev + payload.html);
        setCount((prev) => prev + 1);
      } else if (payload.type === "done") {
        setStatus("done");
        if (typeof payload.count === "number") {
          setCount(payload.count);
        }
      } else if (payload.type === "error") {
        setStatus("error");
      }
    });
    socket.addEventListener("close", () => {
      setStatus((prev) => (prev === "done" ? prev : "closed"));
    });
    socket.addEventListener("error", () => setStatus("error"));

    return () => {
      try {
        socket?.close();
      } catch {
        // ignore
      }
    };
  }, [url]);

  useEffect(() => {
    if (!html) return;
    document.body.dispatchEvent(
      new CustomEvent("htmx:afterSwap", {
        detail: { target: document },
        bubbles: true,
      }),
    );
  }, [html]);

  return (
    <>
      <section
        className="grid"
        data-library-stream
        data-library-stream-path={path}
        data-library-stream-query={query}
        dangerouslySetInnerHTML={{ __html: html }}
      />
      <p
        className="page-head__subtitle"
        data-library-stream-empty
        hidden={count > 0}
      >
        No results yet. Local catalog returned nothing and remote providers either failed or are still in flight.
      </p>
      <span hidden data-library-stream-count>
        <span className="page-head__count" data-library-count>
          {count}
        </span>{" "}
        streamed
      </span>
      <span
        className="badge badge--accent"
        data-library-stream-state={status}
        hidden
      >
        {status}
      </span>
    </>
  );
}
