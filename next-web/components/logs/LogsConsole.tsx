"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import AppShell from "@/components/shell/AppShell";
import EmptyState from "@/components/EmptyState";
import { api, type LogRecord } from "@/lib/api";
import { backendPath } from "@/lib/config";
import {
  LOG_LEVEL_CHOICES,
  LOG_MAX_ROWS,
  buildCategoryChips,
  formatAbsoluteTs,
  matchesLogFilters,
  recordToDownloadLine,
  type LogFilters,
} from "@/lib/logs";

type ConnectionState = "connecting" | "live" | "paused" | "error";

export type LogsConsoleProps = {
  initialRecords: LogRecord[];
  initialLastId: number;
  initialBuffered: number;
  /** Filters applied server-side (from the page URL) when the tail was fetched. */
  appliedLevel: string;
  appliedLogger: string;
  appliedQ: string;
  appliedCategories: string[];
  knownCategories: string[];
  disabledCategories: string[];
  flash?: { kind: string; message: string } | null;
};

function statusLabel(state: ConnectionState, queued: number): string {
  switch (state) {
    case "connecting":
      return "connecting…";
    case "live":
      return "live";
    case "paused":
      return queued > 0 ? `paused — ${queued} queued` : "paused";
    default:
      return "reconnecting…";
  }
}

export default function LogsConsole({
  initialRecords,
  initialLastId,
  initialBuffered,
  appliedLevel,
  appliedLogger,
  appliedQ,
  appliedCategories,
  knownCategories,
  disabledCategories,
  flash: initialFlash = null,
}: LogsConsoleProps) {
  const router = useRouter();

  const [records, setRecords] = useState<LogRecord[]>(initialRecords);
  const [buffered, setBuffered] = useState(initialBuffered);
  const [connState, setConnState] = useState<ConnectionState>("connecting");
  const [queuedCount, setQueuedCount] = useState(0);
  const [paused, setPaused] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const [wrap, setWrap] = useState(false);
  const [flash, setFlash] = useState(initialFlash);

  // Live (not yet applied) filter inputs — re-filter the visible rows
  // client-side without reopening the EventSource, mirroring the
  // legacy web UI behaviour.
  const [level, setLevel] = useState(appliedLevel);
  const [logger, setLogger] = useState(appliedLogger);
  const [q, setQ] = useState(appliedQ);
  const [activeCategories, setActiveCategories] = useState<string[]>(appliedCategories);

  const listRef = useRef<HTMLOListElement | null>(null);
  const stickToBottomRef = useRef(true);
  const lastIdRef = useRef(initialLastId);
  const sessionStartIdRef = useRef(initialLastId);
  const pausedRef = useRef(false);
  const pendingRef = useRef<LogRecord[]>([]);
  const pauseHadIdRef = useRef(0);

  const liveFilters: LogFilters = useMemo(
    () => ({ level, logger, q, categories: activeCategories }),
    [level, logger, q, activeCategories],
  );

  const visibleRecords = useMemo(
    () => records.filter((record) => matchesLogFilters(record, liveFilters)),
    [records, liveFilters],
  );

  const chips = useMemo(
    () => buildCategoryChips(knownCategories, activeCategories, disabledCategories),
    [knownCategories, activeCategories, disabledCategories],
  );

  const appendRecords = useCallback((incoming: LogRecord[]) => {
    const fresh = incoming.filter((r) => (Number(r.id) || 0) > lastIdRef.current);
    if (!fresh.length) return;
    lastIdRef.current = Math.max(
      lastIdRef.current,
      ...fresh.map((r) => Number(r.id) || 0),
    );
    setRecords((prev) => {
      const next = [...prev, ...fresh];
      return next.length > LOG_MAX_ROWS ? next.slice(next.length - LOG_MAX_ROWS) : next;
    });
  }, []);

  // --- SSE live tail -------------------------------------------------
  // The server-side filter uses the *applied* (URL) level/logger/q so
  // typing in the inputs never reopens the connection; toggling a
  // category chip does reconnect because dropping records server-side
  // is much cheaper than streaming them just to hide them.
  useEffect(() => {
    if (typeof window === "undefined" || !("EventSource" in window)) return;

    const params = new URLSearchParams();
    if (appliedLevel) params.set("level", appliedLevel);
    if (appliedLogger) params.set("logger", appliedLogger);
    if (appliedQ) params.set("q", appliedQ);
    for (const cat of activeCategories) params.append("category", cat);
    const qs = params.toString();
    const url = backendPath(`/ui/logs/stream${qs ? `?${qs}` : ""}`);

    setConnState((prev) => (pausedRef.current ? prev : "connecting"));
    const source = new EventSource(url);

    const onRecord = (ev: MessageEvent) => {
      let record: LogRecord;
      try {
        record = JSON.parse(String(ev.data)) as LogRecord;
      } catch {
        return;
      }
      if (pausedRef.current) {
        pendingRef.current.push(record);
        if (pendingRef.current.length > LOG_MAX_ROWS) {
          pendingRef.current.splice(0, pendingRef.current.length - LOG_MAX_ROWS);
        }
        setQueuedCount(pendingRef.current.length);
        return;
      }
      appendRecords([record]);
    };

    source.addEventListener("record", onRecord);
    source.onopen = () => {
      if (!pausedRef.current) setConnState("live");
    };
    source.onerror = () => {
      if (!pausedRef.current) setConnState("error");
    };

    return () => {
      source.removeEventListener("record", onRecord);
      source.close();
    };
  }, [appliedLevel, appliedLogger, appliedQ, activeCategories, appendRecords]);

  // --- Auto-scroll ----------------------------------------------------
  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    if (autoScroll && !paused && stickToBottomRef.current) {
      list.scrollTop = list.scrollHeight;
    }
  }, [visibleRecords.length, autoScroll, paused]);

  useEffect(() => {
    const list = listRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, []);

  const onListScroll = useCallback(() => {
    const list = listRef.current;
    if (!list) return;
    stickToBottomRef.current =
      list.scrollHeight - list.scrollTop - list.clientHeight <= 40;
  }, []);

  // --- Toolbar actions -------------------------------------------------
  const togglePause = useCallback(() => {
    const next = !pausedRef.current;
    pausedRef.current = next;
    setPaused(next);
    if (next) {
      pauseHadIdRef.current = lastIdRef.current;
      setConnState("paused");
      return;
    }
    const pending = pendingRef.current;
    pendingRef.current = [];
    setQueuedCount(0);
    appendRecords(pending);
    setConnState("live");
    if (autoScroll && listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
    // Belt + braces: pull anything the server may have dropped from
    // this subscriber's queue while paused, scoped to the applied filter.
    const since = pauseHadIdRef.current;
    if (since && lastIdRef.current >= since) {
      api
        .getLogsData({
          level: appliedLevel,
          logger: appliedLogger,
          q: appliedQ,
          category: activeCategories,
          since,
        })
        .then((data) => {
          appendRecords(data.records ?? []);
          if (typeof data.buffered === "number") setBuffered(data.buffered);
        })
        .catch(() => {});
    }
  }, [appendRecords, autoScroll, appliedLevel, appliedLogger, appliedQ, activeCategories]);

  const downloadVisible = useCallback(() => {
    const lines = visibleRecords.map((record) =>
      recordToDownloadLine(record, formatAbsoluteTs(record.ts)),
    );
    const blob = new Blob([lines.join("\n")], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    a.download = `animemanager-logs-${stamp}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [visibleRecords]);

  const clearBuffer = useCallback(async () => {
    if (!window.confirm("Clear the in-memory log buffer? (Live tail keeps going)")) {
      return;
    }
    try {
      await api.clearLogs();
      setRecords([]);
      setBuffered(0);
      setFlash({ kind: "info", message: "Log buffer cleared." });
    } catch {
      setFlash({ kind: "error", message: "Could not clear the log buffer." });
    }
  }, []);

  // --- Filters ----------------------------------------------------------
  const applyFilters = useCallback(
    (ev: React.FormEvent) => {
      ev.preventDefault();
      const params = new URLSearchParams();
      if (level) params.set("level", level);
      if (logger.trim()) params.set("logger", logger.trim());
      if (q.trim()) params.set("q", q.trim());
      for (const cat of activeCategories) params.append("category", cat);
      const qs = params.toString();
      router.push(`/logs${qs ? `?${qs}` : ""}`);
    },
    [router, level, logger, q, activeCategories],
  );

  const syncCategoryUrl = useCallback((categories: string[]) => {
    const params = new URLSearchParams(window.location.search);
    params.delete("category");
    for (const cat of categories) params.append("category", cat);
    const qs = params.toString();
    const newUrl = window.location.pathname + (qs ? `?${qs}` : "") + window.location.hash;
    try {
      window.history.replaceState(null, "", newUrl);
    } catch {
      /* ignore */
    }
  }, []);

  const toggleCategory = useCallback(
    (name: string, disabled: boolean) => {
      if (disabled) return;
      setActiveCategories((prev) => {
        const upper = name.toUpperCase();
        const next = prev.includes(upper)
          ? prev.filter((c) => c !== upper)
          : [...prev, upper];
        syncCategoryUrl(next);
        return next;
      });
    },
    [syncCategoryUrl],
  );

  const showAllCategories = useCallback(() => {
    setActiveCategories([]);
    syncCategoryUrl([]);
  }, [syncCategoryUrl]);

  const statusBadgeClass =
    connState === "live"
      ? "badge badge--accent"
      : connState === "error"
        ? "badge badge--bad"
        : "badge badge--muted";

  return (
    <AppShell activeNav="logs" pageTitle="Logs" showSearch={false} flash={flash}>
      <header className="page-head">
        <div>
          <h1 className="page-head__title">Live logs</h1>
          <p className="page-head__subtitle">
            Streaming tail of every Python logger captured by the embedded runtime.
            Filters and live updates run entirely in-process — no external log file is
            required.
          </p>
        </div>
        <div className="page-head__meta">
          <span>
            <span className="page-head__count" data-log-count>
              {visibleRecords.length}
            </span>{" "}
            shown
          </span>
          <span className={statusBadgeClass} data-log-status={connState}>
            {statusLabel(connState, queuedCount)}
          </span>
          <span className="badge" data-log-buffered>
            {buffered} buffered
          </span>
        </div>
      </header>

      <div className="log-toolbar">
        <button
          className="btn btn--ghost"
          type="button"
          onClick={togglePause}
          aria-pressed={paused}
        >
          {paused ? "Resume" : "Pause"}
        </button>
        <button className="btn btn--ghost" type="button" onClick={downloadVisible}>
          Download visible
        </button>
        <button className="btn btn--danger" type="button" onClick={clearBuffer}>
          Clear buffer
        </button>
      </div>

      <form className="log-filters" role="search" onSubmit={applyFilters}>
        <label className="log-filters__field">
          <span className="log-filters__label">Min level</span>
          <select
            name="level"
            className="input log-filters__select"
            value={level}
            onChange={(e) => setLevel(e.target.value)}
          >
            <option value="">All</option>
            {LOG_LEVEL_CHOICES.map((choice) => (
              <option key={choice.value} value={choice.value}>
                {choice.label}
              </option>
            ))}
          </select>
        </label>

        <label className="log-filters__field">
          <span className="log-filters__label">Logger</span>
          <input
            type="text"
            name="logger"
            className="input log-filters__input"
            value={logger}
            placeholder="e.g. clients.http"
            autoComplete="off"
            onChange={(e) => setLogger(e.target.value)}
          />
        </label>

        <label className="log-filters__field log-filters__field--grow">
          <span className="log-filters__label">Search message</span>
          <input
            type="search"
            name="q"
            className="input log-filters__input"
            value={q}
            placeholder="contains…"
            autoComplete="off"
            onChange={(e) => setQ(e.target.value)}
          />
        </label>

        <div className="log-filters__actions">
          <button type="submit" className="btn btn--primary">
            Apply
          </button>
          <Link className="btn btn--ghost" href="/logs">
            Reset
          </Link>
        </div>

        <label className="log-filters__toggle">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={(e) => setAutoScroll(e.target.checked)}
          />
          <span>Auto-scroll</span>
        </label>
        <label className="log-filters__toggle">
          <input type="checkbox" checked={wrap} onChange={(e) => setWrap(e.target.checked)} />
          <span>Wrap lines</span>
        </label>
      </form>

      <div className="log-categories" aria-label="Category filter">
        <span className="log-categories__label">Categories</span>
        <div className="log-categories__chips">
          {chips.map((chip) => (
            <button
              key={chip.name}
              type="button"
              className={`chip log-cat-chip log-cat-chip--${chip.name.toLowerCase()}${
                chip.active ? " is-active" : ""
              }${chip.disabledInSettings ? " is-muted" : ""}`}
              aria-pressed={chip.active}
              title={
                chip.disabledInSettings
                  ? "Disabled in settings — won't appear even if you tick it here. Edit settings.logs.enabled_categories to re-enable."
                  : undefined
              }
              onClick={() => toggleCategory(chip.name, chip.disabledInSettings)}
            >
              <span className="log-cat-chip__dot" aria-hidden="true" />
              {chip.name}
            </button>
          ))}
        </div>
        <div className="log-categories__actions">
          <button
            type="button"
            className="btn btn--ghost btn--small"
            onClick={showAllCategories}
          >
            Show all
          </button>
          <Link className="btn btn--ghost btn--small" href="/settings#section-logs">
            Configure…
          </Link>
        </div>
      </div>

      <section
        className={`log-console${wrap ? " is-wrap" : ""}`}
        data-log-console
        aria-live="polite"
      >
        <ol className="log-list" ref={listRef} onScroll={onListScroll}>
          {visibleRecords.map((record) => {
            const recordLevel = (record.level || "INFO").toUpperCase();
            const category = String(record.category || "OTHER").toUpperCase();
            const isStreamed = (Number(record.id) || 0) > sessionStartIdRef.current;
            return (
              <li
                key={record.id}
                className={`log-row log-row--${recordLevel.toLowerCase()}`}
                data-log-row
                data-log-level={recordLevel}
                data-log-category={category}
                {...(isStreamed ? { "data-log-flash": "1" } : {})}
              >
                <time className="log-row__ts" dateTime={String(record.ts ?? "")}>
                  {formatAbsoluteTs(record.ts)}
                </time>
                <span className="log-row__level">{recordLevel}</span>
                <span className="log-row__category" title={category}>
                  {category}
                </span>
                <span className="log-row__logger" title={record.logger ?? ""}>
                  {record.logger ?? ""}
                </span>
                <span className="log-row__msg">{record.message ?? ""}</span>
                {record.exc_info ? (
                  <pre className="log-row__exc">{record.exc_info}</pre>
                ) : null}
              </li>
            );
          })}
        </ol>
        <div className="log-list__empty" hidden={visibleRecords.length > 0}>
          <EmptyState
            icon="〿"
            title="No log entries to show"
            hint="Adjust the filters above or trigger an action — new records appear here instantly."
          />
        </div>
      </section>
    </AppShell>
  );
}
