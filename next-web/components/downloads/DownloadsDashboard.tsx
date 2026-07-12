"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import AppShell from "@/components/shell/AppShell";
import DownloadsPanel from "@/components/downloads/DownloadsPanel";
import { api } from "@/lib/api";
import type { DownloadsSnapshot } from "@/lib/api";
import { wsBackendUrl } from "@/lib/config";

const WS_PATH = "/ui/downloads/ws";
const POLL_INTERVAL_MS = 4000;
const RECONNECT_MIN_MS = 1500;
const RECONNECT_MAX_MS = 30000;
const MAX_FAILURES_BEFORE_POLLING = 4;

type ConnectionStatus = "connecting" | "live" | "error";

type DownloadsDashboardProps = {
  initial: DownloadsSnapshot;
};

function statusLabel(status: ConnectionStatus, usingPolling: boolean): string {
  if (usingPolling) return "polling fallback";
  if (status === "connecting") return "connecting…";
  if (status === "live") return "live";
  return "connection error";
}

export default function DownloadsDashboard({ initial }: DownloadsDashboardProps) {
  const [snapshot, setSnapshot] = useState<DownloadsSnapshot>(initial);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [usingPolling, setUsingPolling] = useState(false);

  const socketRef = useRef<WebSocket | null>(null);
  const pollTimerRef = useRef<number | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const failureCountRef = useRef(0);
  const reconnectDelayRef = useRef(RECONNECT_MIN_MS);
  const closedRef = useRef(false);
  const usingPollingRef = useRef(false);

  const applySnapshot = useCallback((payload: DownloadsSnapshot) => {
    setSnapshot({
      overview: payload.overview ?? {},
      counts: payload.counts ?? {},
      ts: payload.ts,
    });
  }, []);

  const clearReconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      window.clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const pollOnce = useCallback(async () => {
    try {
      const data = await api.getDownloadsOverview();
      applySnapshot(data);
      setStatus("live");
    } catch {
      setStatus("error");
    }
  }, [applySnapshot]);

  const startPolling = useCallback(() => {
    if (usingPollingRef.current) return;
    usingPollingRef.current = true;
    setUsingPolling(true);
    setStatus("error");
    void pollOnce();
    pollTimerRef.current = window.setInterval(() => {
      void pollOnce();
    }, POLL_INTERVAL_MS);
  }, [pollOnce]);

  const connect = useCallback(() => {
    if (closedRef.current || usingPollingRef.current) return;
    if (typeof WebSocket === "undefined") {
      startPolling();
      return;
    }

    clearReconnect();
    setStatus("connecting");

    let socket: WebSocket;
    try {
      socket = new WebSocket(wsBackendUrl(WS_PATH));
    } catch {
      failureCountRef.current += 1;
      if (failureCountRef.current >= MAX_FAILURES_BEFORE_POLLING) {
        startPolling();
      } else {
        reconnectTimerRef.current = window.setTimeout(() => {
          connect();
        }, reconnectDelayRef.current);
        reconnectDelayRef.current = Math.min(
          RECONNECT_MAX_MS,
          Math.round(reconnectDelayRef.current * 1.6),
        );
      }
      return;
    }

    socketRef.current = socket;

    socket.addEventListener("open", () => {
      failureCountRef.current = 0;
      reconnectDelayRef.current = RECONNECT_MIN_MS;
      setStatus("live");
    });

    socket.addEventListener("message", (ev) => {
      try {
        const payload = JSON.parse(String(ev.data)) as DownloadsSnapshot;
        if (payload && typeof payload === "object") {
          applySnapshot(payload);
        }
      } catch {
        /* ignore malformed frames */
      }
    });

    socket.addEventListener("close", () => {
      socketRef.current = null;
      if (closedRef.current || usingPollingRef.current) return;
      failureCountRef.current += 1;
      if (failureCountRef.current >= MAX_FAILURES_BEFORE_POLLING) {
        setStatus("error");
        startPolling();
        return;
      }
      setStatus("connecting");
      reconnectTimerRef.current = window.setTimeout(() => {
        connect();
      }, reconnectDelayRef.current);
      reconnectDelayRef.current = Math.min(
        RECONNECT_MAX_MS,
        Math.round(reconnectDelayRef.current * 1.6),
      );
    });

    socket.addEventListener("error", () => {
      setStatus("error");
    });
  }, [applySnapshot, clearReconnect, startPolling]);

  const requestRefresh = useCallback(() => {
    const socket = socketRef.current;
    if (socket && socket.readyState === WebSocket.OPEN) {
      try {
        socket.send(JSON.stringify({ type: "refresh" }));
        return;
      } catch {
        /* fall through */
      }
    }
    void pollOnce();
  }, [pollOnce]);

  useEffect(() => {
    closedRef.current = false;
    connect();

    const onVisibility = () => {
      if (document.visibilityState === "hidden") {
        try {
          socketRef.current?.close();
        } catch {
          /* ignore */
        }
      } else if (usingPollingRef.current) {
        void pollOnce();
      } else if (socketRef.current?.readyState === WebSocket.OPEN) {
        requestRefresh();
      } else {
        reconnectDelayRef.current = RECONNECT_MIN_MS;
        connect();
      }
    };

    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      closedRef.current = true;
      clearReconnect();
      stopPolling();
      document.removeEventListener("visibilitychange", onVisibility);
      try {
        socketRef.current?.close();
      } catch {
        /* ignore */
      }
      socketRef.current = null;
    };
  }, [clearReconnect, connect, pollOnce, requestRefresh, stopPolling]);

  const counts = snapshot.counts ?? {};
  const badgeClass =
    status === "error" && !usingPolling
      ? "badge badge--bad"
      : status === "live" && !usingPolling
        ? "badge badge--accent"
        : "badge badge--muted";

  return (
    <AppShell
      activeNav="downloads"
      pageTitle="Downloads"
      showSearch={false}
      topbarActions={
        <button
          type="button"
          className="btn btn--primary"
          data-downloads-refresh
          onClick={requestRefresh}
        >
          Refresh
        </button>
      }
    >
      <header className="page-head">
        <div>
          <h1 className="page-head__title">Downloads &amp; seeding</h1>
          <p className="page-head__subtitle">
            Live view of every torrent the app is downloading, seeding or keeping on disk.
            Streaming over WebSocket{" "}
            <span
              className={badgeClass}
              data-downloads-status={status}
              data-downloads-status-target
            >
              {statusLabel(status, usingPolling)}
            </span>
          </p>
        </div>
        <div className="page-head__meta">
          <span>
            <span className="page-head__count" data-downloads-count="active">
              {counts.active ?? 0}
            </span>{" "}
            active
          </span>
          <span>
            <span className="page-head__count" data-downloads-count="seeding">
              {counts.seeding ?? 0}
            </span>{" "}
            seeding
          </span>
          <span>
            <span className="page-head__count" data-downloads-count="completed">
              {counts.completed ?? 0}
            </span>{" "}
            completed
          </span>
        </div>
      </header>

      <DownloadsPanel overview={snapshot.overview ?? {}} onRefresh={requestRefresh} />
    </AppShell>
  );
}
