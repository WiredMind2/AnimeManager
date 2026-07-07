import { backendPath } from "@/lib/config";

export type PlayerLogLevel = "debug" | "info" | "warn" | "error";

/** Classifies player faults for console and server logs. */
export type PlayerFaultClass =
  | "startup_config_warning"
  | "startup_stall"
  | "playback_runtime_error"
  | "rebuffering";

export function playerFaultFields(
  faultClass: PlayerFaultClass,
  faultStage: string,
  recoverable: boolean,
): Record<string, unknown> {
  return {
    fault_class: faultClass,
    fault_stage: faultStage,
    recoverable,
  };
}

export type PlayerLogEvent = {
  ts: string;
  event: string;
  level: PlayerLogLevel;
  data?: Record<string, unknown>;
};

export type ShakaErrorPlain = {
  code: number | null;
  codeName: string | null;
  category: number | null;
  categoryName: string | null;
  severity: number | null;
  severityName: string | null;
  message: string;
  data: unknown;
};

type PlayerLoggerOptions = {
  animeId: number;
  fileId?: string;
  sessionId?: string;
  getVideo?: () => HTMLVideoElement | null;
};

const FLUSH_INTERVAL_MS = 2000;
const MAX_QUEUE = 200;

function utcIso(): string {
  return new Date().toISOString();
}

export function mediaErrorCodeName(code: number | null | undefined): string {
  switch (Number(code || 0)) {
    case 1:
      return "MEDIA_ERR_ABORTED";
    case 2:
      return "MEDIA_ERR_NETWORK";
    case 3:
      return "MEDIA_ERR_DECODE";
    case 4:
      return "MEDIA_ERR_SRC_NOT_SUPPORTED";
    default:
      return "UNKNOWN";
  }
}

export function shakaErrorToPlain(
  shakaNs: typeof window.shaka | null | undefined,
  detail: {
    code?: number;
    category?: number;
    severity?: number;
    data?: unknown;
    message?: string;
    getMessage?: () => string;
  } | null
  | undefined,
): ShakaErrorPlain {
  const out: ShakaErrorPlain = {
    code: detail?.code != null ? detail.code : null,
    codeName: null,
    category: detail?.category != null ? detail.category : null,
    categoryName: null,
    severity: detail?.severity != null ? detail.severity : null,
    severityName: null,
    message: "",
    data: null,
  };
  try {
    if (shakaNs?.util?.Error) {
      const E = shakaNs.util.Error;
      if (typeof out.code === "number" && E.Code) {
        for (const key of Object.keys(E.Code)) {
          if (E.Code[key as keyof typeof E.Code] === out.code) {
            out.codeName = key;
            break;
          }
        }
      }
      if (typeof out.category === "number" && E.Category) {
        for (const key of Object.keys(E.Category)) {
          if (E.Category[key as keyof typeof E.Category] === out.category) {
            out.categoryName = key;
            break;
          }
        }
      }
      if (typeof out.severity === "number" && E.Severity) {
        for (const key of Object.keys(E.Severity)) {
          if (E.Severity[key as keyof typeof E.Severity] === out.severity) {
            out.severityName = key;
            break;
          }
        }
      }
    }
  } catch {
    /* ignore */
  }
  try {
    if (detail && typeof detail.getMessage === "function") {
      out.message = String(detail.getMessage() || "").trim();
    }
  } catch {
    /* ignore */
  }
  try {
    const raw = detail?.data ?? null;
    if (raw !== undefined && raw !== null) {
      out.data = JSON.parse(
        JSON.stringify(raw, (_key, value) => {
          if (value instanceof Error) {
            return { name: value.name, message: value.message };
          }
          if (typeof value === "bigint") {
            return String(value);
          }
          return value;
        }),
      );
    }
  } catch {
    try {
      out.data = String(detail?.data);
    } catch {
      out.data = "[unserializable]";
    }
  }
  return out;
}

export type PlayerLogger = {
  setSessionId: (sessionId: string) => void;
  setFileId: (fileId: string) => void;
  log: (level: PlayerLogLevel, event: string, data?: Record<string, unknown>) => void;
  flush: () => void;
  dispose: () => void;
};

export function createPlayerLogger(opts: PlayerLoggerOptions): PlayerLogger {
  let sessionId = opts.sessionId || "";
  let fileId = opts.fileId || "";
  const animeId = opts.animeId;
  const getVideo = opts.getVideo;
  const queue: PlayerLogEvent[] = [];
  let flushTimer: ReturnType<typeof setInterval> | null = null;
  let disposed = false;

  const baseContext = (): Record<string, unknown> => {
    const video = getVideo?.() ?? null;
    return {
      anime_id: animeId || "",
      file_id: fileId || "",
      session_id: sessionId || "",
      current_time: video ? Number(video.currentTime || 0) : 0,
      video_ready_state: video ? video.readyState : null,
      video_network_state: video ? video.networkState : null,
      client_ts_ms: Date.now(),
    };
  };

  const flushNow = () => {
    if (!sessionId || queue.length === 0) {
      return;
    }
    const batch = queue.splice(0, MAX_QUEUE);
    const url = backendPath(`/ui/stream/${encodeURIComponent(sessionId)}/log`);
    const body = JSON.stringify({ events: batch });
    try {
      if (typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
        const blob = new Blob([body], { type: "application/json" });
        if (navigator.sendBeacon(url, blob)) {
          return;
        }
      }
    } catch {
      /* fall through to fetch */
    }
    fetch(url, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body,
      keepalive: true,
    }).catch(() => {});
  };

  const scheduleFlush = () => {
    if (flushTimer != null || disposed) return;
    flushTimer = setInterval(() => {
      flushNow();
    }, FLUSH_INTERVAL_MS);
  };

  const onVisibility = () => {
    if (document.visibilityState === "hidden") {
      flushNow();
    }
  };

  const onBeforeUnload = () => {
    flushNow();
  };

  if (typeof document !== "undefined") {
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("beforeunload", onBeforeUnload);
    scheduleFlush();
  }

  const log = (level: PlayerLogLevel, event: string, data?: Record<string, unknown>) => {
    const payload = {
      ...baseContext(),
      ...(data || {}),
    };
    const line = `[AnimeManager player][${level.toUpperCase()}] ${event}`;
    try {
      if (level === "error") {
        console.error(line, payload);
      } else if (level === "warn") {
        console.warn(line, payload);
      } else {
        console.info(line, payload);
      }
    } catch {
      /* ignore */
    }

    if (!sessionId || disposed) {
      return;
    }
    queue.push({
      ts: utcIso(),
      event,
      level,
      data: payload,
    });
    if (queue.length >= MAX_QUEUE) {
      flushNow();
    }
  };

  return {
    setSessionId(next) {
      if (sessionId && sessionId !== next) {
        flushNow();
      }
      sessionId = next;
    },
    setFileId(next) {
      fileId = next;
    },
    log,
    flush: flushNow,
    dispose() {
      if (disposed) return;
      disposed = true;
      flushNow();
      if (flushTimer != null) {
        clearInterval(flushTimer);
        flushTimer = null;
      }
      if (typeof document !== "undefined") {
        document.removeEventListener("visibilitychange", onVisibility);
        window.removeEventListener("beforeunload", onBeforeUnload);
      }
    },
  };
}
