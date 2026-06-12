import type { LogRecord } from "./api";

export const LOG_MAX_ROWS = 4000;
export const LOG_TAIL_INITIAL = 250;

export const LOG_LEVEL_CHOICES = [
  { value: "DEBUG", label: "Debug" },
  { value: "INFO", label: "Info" },
  { value: "WARNING", label: "Warning" },
  { value: "ERROR", label: "Error" },
  { value: "CRITICAL", label: "Critical" },
] as const;

export const LOG_LEVEL_ORDER: Record<string, number> = {
  DEBUG: 10,
  INFO: 20,
  WARNING: 30,
  ERROR: 40,
  CRITICAL: 50,
};

export const KNOWN_CATEGORIES = [
  "DB_ERROR",
  "DB_UPDATE",
  "DISK_ERROR",
  "MAIN_STATE",
  "NETWORK",
  "NETWORK_DATA",
  "SERVER",
  "SETTINGS",
  "THREAD",
  "TIME",
  "HTTP",
  "DOWNLOAD",
  "SEARCH",
  "STARTUP",
  "PLAYER",
  "OTHER",
] as const;

export type LogFilters = {
  level: string;
  logger: string;
  q: string;
  categories: string[];
};

export type CategoryChip = {
  name: string;
  active: boolean;
  disabledInSettings: boolean;
};

export function normalizeCategories(raw: string | string[] | undefined): string[] {
  if (!raw) return [];
  const items = Array.isArray(raw) ? raw : [raw];
  return items.map((c) => c.trim().toUpperCase()).filter(Boolean);
}

export function formatAbsoluteTs(ts?: number | string): string {
  if (!ts) return "";
  const d = new Date(Number(ts) * 1000);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.` +
    `${String(d.getMilliseconds()).padStart(3, "0")}`
  );
}

const relativeFormatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

export function formatRelativeTs(ts?: number | string, nowMs = Date.now()): string {
  if (!ts) return "";
  const seconds = Number(ts);
  if (!Number.isFinite(seconds)) return "";
  const diff = (seconds * 1000 - nowMs) / 1000;
  const abs = Math.abs(diff);
  let value: number;
  let unit: Intl.RelativeTimeFormatUnit;
  if (abs < 60) {
    value = diff;
    unit = "second";
  } else if (abs < 3600) {
    value = diff / 60;
    unit = "minute";
  } else if (abs < 86400) {
    value = diff / 3600;
    unit = "hour";
  } else if (abs < 86400 * 30) {
    value = diff / 86400;
    unit = "day";
  } else if (abs < 86400 * 365) {
    value = diff / (86400 * 30);
    unit = "month";
  } else {
    value = diff / (86400 * 365);
    unit = "year";
  }
  return relativeFormatter.format(Math.round(value), unit);
}

export function matchesLogFilters(record: LogRecord, filters: LogFilters): boolean {
  if (filters.level) {
    const min = LOG_LEVEL_ORDER[filters.level.toUpperCase()] ?? 0;
    const levelno = record.levelno ?? LOG_LEVEL_ORDER[(record.level ?? "INFO").toUpperCase()] ?? 0;
    if (levelno < min) return false;
  }
  if (filters.logger) {
    const needle = filters.logger.toLowerCase();
    const hay = String(record.logger ?? "").toLowerCase();
    if (!hay.includes(needle)) return false;
  }
  if (filters.q) {
    const needle = filters.q.toLowerCase();
    const hay = `${record.message ?? ""}\n${record.exc_info ?? ""}`.toLowerCase();
    if (!hay.includes(needle)) return false;
  }
  if (filters.categories.length) {
    const cat = String(record.category ?? "OTHER").toUpperCase();
    const selected = new Set(filters.categories.map((c) => c.toUpperCase()));
    if (!selected.has(cat)) return false;
  }
  return true;
}

export function buildCategoryChips(
  knownNames: readonly string[],
  selected: string[],
  disabledInSettings: string[],
): CategoryChip[] {
  const selectedSet = new Set(selected.map((c) => c.toUpperCase()));
  const disabledSet = new Set(disabledInSettings.map((c) => c.toUpperCase()));
  return knownNames.map((name) => ({
    name,
    active: selectedSet.has(name.toUpperCase()),
    disabledInSettings: disabledSet.has(name.toUpperCase()),
  }));
}

export function mergeKnownCategories(records: LogRecord[]): string[] {
  const seen = new Set<string>(KNOWN_CATEGORIES);
  const extras: string[] = [];
  for (const record of records) {
    const cat = String(record.category ?? "OTHER").toUpperCase();
    if (!seen.has(cat)) {
      seen.add(cat);
      extras.push(cat);
    }
  }
  return [...KNOWN_CATEGORIES, ...extras.sort()];
}

export function filtersToQuery(filters: LogFilters): Record<string, string | string[] | undefined> {
  return {
    level: filters.level || undefined,
    logger: filters.logger || undefined,
    q: filters.q || undefined,
    category: filters.categories.length ? filters.categories : undefined,
  };
}

export function recordToDownloadLine(record: LogRecord, tsLabel: string): string {
  let line = [tsLabel, record.level ?? "INFO", record.logger ?? "", record.message ?? ""].join(" \t ");
  if (record.exc_info) line += `\n${record.exc_info}`;
  return line;
}
