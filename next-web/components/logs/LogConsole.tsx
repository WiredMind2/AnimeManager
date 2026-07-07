"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import EmptyState from "@/components/EmptyState";
import LogRow from "@/components/logs/LogRow";
import { api, type LogRecord } from "@/lib/api";
import { backendPath } from "@/lib/config";
import {
  LOG_LEVEL_CHOICES,
  LOG_MAX_ROWS,
  buildCategoryChips,
  filtersToQuery,
  formatAbsoluteTs,
  matchesLogFilters,
  recordToDownloadLine,
  type CategoryChip,
  type LogFilters,
} from "@/lib/logs";

type StreamStatus = "connecting" | "live" | "paused" | "error";

type LogConsoleProps = {
  initialRecords: LogRecord[];
  initialLastId: number;
  initialBuffered: number;
  appliedFilters: LogFilters;
  knownCategories: string[];
  disabledInSettings: string[];
};

function statusBadgeClass(status: StreamStatus): string {
  if (status === "live") return "badge badge--accent";
  if (status === "error") return "badge badge--bad";
  if (status === "paused") return "badge badge--muted";
  return "badge";
}

function buildStreamUrl(filters: LogFilters): string {
  const params = new URLSearchParams();
  if (filters.level) params.set("level", filters.level);
  if (filters.logger) params.set("logger", filters.logger);
  if (filters.q) params.set("q", filters.q);
  for (const cat of filters.categories) {
    if (cat) params.append("category", cat);
  }
  const base = backendPath("/ui/logs/stream");
  const qs = params.toString();
  return qs ? `${base}?${qs}` : base;
}

export default function LogConsole({
  initialRecords,
  initialLastId,
  initialBuffered,
  appliedFilters,
  knownCategories,
  disabledInSettings,
}: LogConsoleProps) {
  const router = useRouter();

  const [records, setRecords] = useState<LogRecord[]>(initialRecords);
  const [liveFilters, setLiveFilters] = useState<LogFilters>(appliedFilters);
  const [paused, setPaused] = useState(false);
  const [pendingCount, setPendingCount] = useState(0);
  const [autoScroll, setAutoScroll] = useState(true);
  const [wrapLines, setWrapLines] = useState(false);
  const [streamStatus, setStreamStatus] = useState<StreamStatus>("connecting");
  const [buffered, setBuffered] = useState(initialBuffered);
  const [flash, setFlash] = useState<string | null>(null);
  const [newRowIds, setNewRowIds] = useState<Set<number>>(new Set());

  const lastIdRef = useRef(initialLastId);
  const pauseHadIdRef = useRef(0);
  const pendingWhilePausedRef = useRef<LogRecord[]>([]);
  const listRef = useRef<HTMLOListElement>(null);
  const sourceRef = useRef<EventSource | null>(null);
  const pausedRef = useRef(paused);
  const liveFiltersRef = useRef(liveFilters);
  pausedRef.current = paused;
  liveFiltersRef.current = liveFilters;

  const categoryChips = useMemo(
    () =>
      buildCategoryChips(
        knownCategories,
        liveFilters.categories,
        disabledInSettings,
      ),
    [knownCategories, liveFilters.categories, disabledInSettings],
  );

  const visibleCount = useMemo(
    () => records.filter((record) => matchesLogFilters(record, liveFilters)).length,
    [records, liveFilters],
  );

  const stuckToBottom = useCallback(() => {
    const list = listRef.current;
    if (!list) return true;
    const slack = 40;
    return list.scrollHeight - list.scrollTop - list.clientHeight <= slack;
  }, []);

  const scrollToBottom = useCallback(() => {
    const list = listRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, []);

  const trimRecords = useCallback((next: LogRecord[]) => {
    if (next.length <= LOG_MAX_ROWS) return next;
    return next.slice(next.length - LOG_MAX_ROWS);
  }, []);

  const markNewRow = useCallback((id: number) => {
    setNewRowIds((prev) => {
      const next = new Set(prev);
      next.add(id);
      return next;
    });
    window.setTimeout(() => {
      setNewRowIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }, 1100);
  }, []);

  const appendRecord = useCallback(
    (record: LogRecord) => {
      if (!record) return;
      lastIdRef.current = Math.max(lastIdRef.current, Number(record.id) || 0);

      const wasAtBottom = stuckToBottom();
      setRecords((prev) => trimRecords([...prev, record]));

      if (record.id != null) {
        markNewRow(record.id);
      }

      if (wasAtBottom && autoScroll && !pausedRef.current) {
        window.requestAnimationFrame(scrollToBottom);
      }
    },
    [autoScroll, markNewRow, scrollToBottom, stuckToBottom, trimRecords],
  );

  const flushPending = useCallback(() => {
    const pending = pendingWhilePausedRef.current;
    if (!pending.length) return;
    pending.forEach((record) => {
      if (matchesLogFilters(record, liveFiltersRef.current)) {
        appendRecord(record);
      } else {
        lastIdRef.current = Math.max(lastIdRef.current, Number(record.id) || 0);
      }
    });
    pendingWhilePausedRef.current = [];
    setPendingCount(0);
  }, [appendRecord]);

  const connect = useCallback(() => {
    if (typeof EventSource === "undefined") {
      setStreamStatus("error");
      return;
    }

    if (sourceRef.current) {
      try {
        sourceRef.current.close();
      } catch {
        /* ignore */
      }
      sourceRef.current = null;
    }

    if (!pausedRef.current) {
      setStreamStatus("connecting");
    }

    const source = new EventSource(buildStreamUrl(appliedFilters));
    sourceRef.current = source;

    const onMessage = (ev: MessageEvent) => {
      let record: LogRecord;
      try {
        record = JSON.parse(ev.data) as LogRecord;
      } catch {
        return;
      }

      if (pausedRef.current) {
        pendingWhilePausedRef.current.push(record);
        if (pendingWhilePausedRef.current.length > LOG_MAX_ROWS) {
          pendingWhilePausedRef.current = pendingWhilePausedRef.current.slice(
            -LOG_MAX_ROWS,
          );
        }
        setPendingCount(pendingWhilePausedRef.current.length);
        setStreamStatus("paused");
        return;
      }

      if (matchesLogFilters(record, liveFiltersRef.current)) {
        appendRecord(record);
      } else {
        lastIdRef.current = Math.max(lastIdRef.current, Number(record.id) || 0);
      }
    };

    source.addEventListener("record", onMessage);
    source.onopen = () => {
      if (!pausedRef.current) setStreamStatus("live");
    };
    source.onerror = () => {
      if (!pausedRef.current) setStreamStatus("error");
    };
  }, [appendRecord, appliedFilters]);

  useEffect(() => {
    connect();
    return () => {
      if (sourceRef.current) {
        try {
          sourceRef.current.close();
        } catch {
          /* ignore */
        }
        sourceRef.current = null;
      }
    };
  }, [connect]);

  useEffect(() => {
    setRecords(initialRecords);
    lastIdRef.current = initialLastId;
    setBuffered(initialBuffered);
    setLiveFilters(appliedFilters);
  }, [initialRecords, initialLastId, initialBuffered, appliedFilters]);

  useEffect(() => {
    if (autoScroll) {
      window.setTimeout(scrollToBottom, 0);
    }
  }, [autoScroll, scrollToBottom]);

  const togglePause = useCallback(async () => {
    if (!paused) {
      pauseHadIdRef.current = lastIdRef.current;
      setPaused(true);
      setStreamStatus("paused");
      return;
    }

    setPaused(false);
    flushPending();
    setStreamStatus("live");
    if (autoScroll) scrollToBottom();

    const pauseHadId = pauseHadIdRef.current;
    if (pauseHadId && lastIdRef.current > pauseHadId) {
      try {
        const data = await api.getLogsData({
          ...filtersToQuery(appliedFilters),
          since: pauseHadId,
        });
        for (const record of data.records ?? []) {
          if (matchesLogFilters(record, liveFiltersRef.current)) {
            appendRecord(record);
          } else {
            lastIdRef.current = Math.max(lastIdRef.current, Number(record.id) || 0);
          }
        }
        if (typeof data.buffered === "number") setBuffered(data.buffered);
      } catch {
        /* ignore catch-up failure */
      }
    }
  }, [appendRecord, appliedFilters, autoScroll, flushPending, paused, scrollToBottom]);

  const handleApply = (ev: FormEvent<HTMLFormElement>) => {
    ev.preventDefault();
    const params = new URLSearchParams();
    if (liveFilters.level) params.set("level", liveFilters.level);
    if (liveFilters.logger) params.set("logger", liveFilters.logger);
    if (liveFilters.q) params.set("q", liveFilters.q);
    for (const cat of liveFilters.categories) {
      params.append("category", cat);
    }
    const qs = params.toString();
    router.push(qs ? `/logs?${qs}` : "/logs");
  };

  const syncCategoryUrl = useCallback(
    (categories: string[]) => {
      const params = new URLSearchParams();
      if (appliedFilters.level) params.set("level", appliedFilters.level);
      if (appliedFilters.logger) params.set("logger", appliedFilters.logger);
      if (appliedFilters.q) params.set("q", appliedFilters.q);
      for (const cat of categories) {
        params.append("category", cat);
      }
      const qs = params.toString();
      router.replace(qs ? `/logs?${qs}` : "/logs");
    },
    [appliedFilters.level, appliedFilters.logger, appliedFilters.q, router],
  );

  const toggleCategory = (chip: CategoryChip) => {
    if (chip.disabledInSettings) return;
    const nextSelected = chip.active
      ? liveFilters.categories.filter((c) => c.toUpperCase() !== chip.name.toUpperCase())
      : [...liveFilters.categories, chip.name];
    setLiveFilters((prev) => ({ ...prev, categories: nextSelected }));
    syncCategoryUrl(nextSelected);
  };

  const showAllCategories = () => {
    setLiveFilters((prev) => ({ ...prev, categories: [] }));
    syncCategoryUrl([]);
  };

  const handleClear = async () => {
    if (!window.confirm("Clear the in-memory log buffer? (Live tail keeps going)")) {
      return;
    }
    try {
      await api.clearLogs();
      setRecords([]);
      lastIdRef.current = 0;
      pendingWhilePausedRef.current = [];
      setPendingCount(0);
      setBuffered(0);
      setFlash("Log buffer cleared.");
      window.setTimeout(() => setFlash(null), 4000);
    } catch {
      setFlash("Failed to clear log buffer.");
      window.setTimeout(() => setFlash(null), 4000);
    }
  };

  const handleDownload = () => {
    const visibleRecords = records.filter((record) =>
      matchesLogFilters(record, liveFilters),
    );
    const lines = visibleRecords.map((record) =>
      recordToDownloadLine(record, formatAbsoluteTs(record.ts)),
    );
    const blob = new Blob([lines.join("\n")], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    anchor.download = `animemanager-logs-${stamp}.txt`;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
  };

  const statusLabel =
    paused && pendingCount > 0
      ? `paused — ${pendingCount} queued`
      : streamStatus === "connecting"
        ? "connecting…"
        : streamStatus === "live"
          ? "live"
          : streamStatus === "paused"
            ? "paused"
            : "reconnecting…";

  return (
    <>
      {flash ? <div className="flash flash--info">{flash}</div> : null}

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
            <span className="page-head__count">{visibleCount}</span> shown
          </span>
          <span className={statusBadgeClass(streamStatus)} data-log-status={streamStatus}>
            {statusLabel}
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
          aria-pressed={paused}
          onClick={() => void togglePause()}
        >
          <span data-log-pause-label>{paused ? "Resume" : "Pause"}</span>
        </button>
        <button className="btn btn--ghost" type="button" onClick={handleDownload}>
          Download visible
        </button>
        <button className="btn btn--danger" type="button" onClick={() => void handleClear()}>
          Clear buffer
        </button>
      </div>

      <form className="log-filters" role="search" onSubmit={handleApply}>
        <label className="log-filters__field">
          <span className="log-filters__label">Min level</span>
          <select
            name="level"
            className="input log-filters__select"
            value={liveFilters.level}
            onChange={(ev) =>
              setLiveFilters((prev) => ({ ...prev, level: ev.target.value.toUpperCase() }))
            }
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
            value={liveFilters.logger}
            placeholder="e.g. clients.http"
            autoComplete="off"
            onChange={(ev) =>
              setLiveFilters((prev) => ({ ...prev, logger: ev.target.value }))
            }
          />
        </label>

        <label className="log-filters__field log-filters__field--grow">
          <span className="log-filters__label">Search message</span>
          <input
            type="search"
            name="q"
            className="input log-filters__input"
            value={liveFilters.q}
            placeholder="contains…"
            autoComplete="off"
            onChange={(ev) => setLiveFilters((prev) => ({ ...prev, q: ev.target.value }))}
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
            onChange={(ev) => setAutoScroll(ev.target.checked)}
          />
          <span>Auto-scroll</span>
        </label>
        <label className="log-filters__toggle">
          <input
            type="checkbox"
            checked={wrapLines}
            onChange={(ev) => setWrapLines(ev.target.checked)}
          />
          <span>Wrap lines</span>
        </label>
      </form>

      <div className="log-categories" aria-label="Category filter">
        <span className="log-categories__label">Categories</span>
        <div className="log-categories__chips">
          {categoryChips.map((chip) => (
            <button
              key={chip.name}
              type="button"
              className={`chip log-cat-chip log-cat-chip--${chip.name.toLowerCase()}${chip.active ? " is-active" : ""}${chip.disabledInSettings ? " is-muted" : ""}`}
              aria-pressed={chip.active}
              title={
                chip.disabledInSettings
                  ? "Disabled in settings — won't appear even if you tick it here. Edit settings.logs.enabled_categories to re-enable."
                  : undefined
              }
              onClick={() => toggleCategory(chip)}
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
        className={`log-console${wrapLines ? " is-wrap" : ""}`}
        aria-live="polite"
      >
        <ol className="log-list" ref={listRef}>
          {records.map((record) => (
            <LogRow
              key={record.id}
              record={record}
              flash={record.id != null && newRowIds.has(record.id)}
              hidden={!matchesLogFilters(record, liveFilters)}
            />
          ))}
        </ol>
        <div className="log-list__empty" hidden={visibleCount > 0}>
          <EmptyState
            icon="〿"
            title="No log entries to show"
            hint="Adjust the filters above or trigger an action — new records appear here instantly."
          />
        </div>
      </section>
    </>
  );
}
