/** Broadcast schedule helpers — stored slots are Japan Standard Time (JST). */

export type BroadcastSlot = {
  weekday: number; // 0=Monday .. 6=Sunday
  hour: number;
  minute: number;
};

const WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;

type ZonedParts = {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
  weekday: number;
};

export function parseBroadcast(value?: string | null): BroadcastSlot | null {
  if (!value) return null;
  const parts = value.trim().split("-");
  if (parts.length !== 3) return null;
  const weekday = Number.parseInt(parts[0] ?? "", 10);
  const hour = Number.parseInt(parts[1] ?? "", 10);
  const minute = Number.parseInt(parts[2] ?? "", 10);
  if (!Number.isFinite(weekday) || weekday < 0 || weekday > 6) return null;
  if (!Number.isFinite(hour) || hour < 0 || hour > 23) return null;
  if (!Number.isFinite(minute) || minute < 0 || minute > 59) return null;
  return { weekday, hour, minute };
}

function zonedParts(date: Date, timeZone: string): ZonedParts {
  const formatter = new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    weekday: "short",
    hourCycle: "h23",
  });
  const parts = formatter.formatToParts(date);
  const read = (type: Intl.DateTimeFormatPartTypes) =>
    Number.parseInt(parts.find((part) => part.type === type)?.value ?? "0", 10);
  const weekdayLabel = parts.find((part) => part.type === "weekday")?.value ?? "Mon";
  const weekday = WEEKDAY_SHORT.indexOf(weekdayLabel as (typeof WEEKDAY_SHORT)[number]);
  return {
    year: read("year"),
    month: read("month"),
    day: read("day"),
    hour: read("hour"),
    minute: read("minute"),
    second: read("second"),
    weekday: weekday >= 0 ? weekday : 0,
  };
}

function localTimeInZoneToUtc(
  year: number,
  month: number,
  day: number,
  hour: number,
  minute: number,
  second: number,
  timeZone: string,
): number {
  let guess = Date.UTC(year, month - 1, day, hour, minute, second);
  for (let adjust = -14; adjust <= 14; adjust++) {
    const ms = guess + adjust * 3_600_000;
    const parts = zonedParts(new Date(ms), timeZone);
    if (
      parts.year === year &&
      parts.month === month &&
      parts.day === day &&
      parts.hour === hour &&
      parts.minute === minute &&
      parts.second === second
    ) {
      return ms;
    }
  }
  return guess;
}

export function convertJstSlotToLocal(
  slot: BroadcastSlot,
  timeZone: string,
  now: Date = new Date(),
): BroadcastSlot {
  const next = nextEpisodeDate(slot, now, timeZone);
  const parts = zonedParts(next, timeZone);
  return {
    weekday: parts.weekday,
    hour: parts.hour,
    minute: parts.minute,
  };
}

export function formatSlotShort(slot: BroadcastSlot): string {
  const weekday = WEEKDAY_SHORT[slot.weekday] ?? "???";
  return `${weekday} ${String(slot.hour).padStart(2, "0")}:${String(slot.minute).padStart(2, "0")}`;
}

export function formatBroadcastJst(slot: BroadcastSlot): string {
  return `${formatSlotShort(slot)} JST`;
}

export function formatBroadcastDisplay(
  slot: BroadcastSlot,
  timeZone: string,
  options: { includeJst?: boolean; now?: Date } = {},
): string {
  const includeJst = options.includeJst ?? true;
  const now = options.now ?? new Date();
  const local = convertJstSlotToLocal(slot, timeZone, now);
  const localText = formatSlotShort(local);
  if (!includeJst) return localText;
  const jstText = formatSlotShort(slot);
  if (localText === jstText) return localText;
  return `${localText} (${jstText} JST)`;
}

export function nextEpisodeDate(
  slot: BroadcastSlot,
  now: Date = new Date(),
  timeZone: string,
): Date {
  const nowMs = now.getTime();
  for (let offset = 0; offset <= 14; offset++) {
    const probe = new Date(nowMs + offset * 86_400_000);
    const jst = zonedParts(probe, "Asia/Tokyo");
    if (jst.weekday !== slot.weekday) continue;

    const candidateMs = localTimeInZoneToUtc(
      jst.year,
      jst.month,
      jst.day,
      slot.hour,
      slot.minute,
      0,
      "Asia/Tokyo",
    );
    if (candidateMs > nowMs) {
      return new Date(candidateMs);
    }
  }

  const fallbackMs = localTimeInZoneToUtc(
    zonedParts(now, "Asia/Tokyo").year,
    zonedParts(now, "Asia/Tokyo").month,
    zonedParts(now, "Asia/Tokyo").day,
    slot.hour,
    slot.minute,
    0,
    "Asia/Tokyo",
  );
  return new Date(fallbackMs + 7 * 86_400_000);
}

export function formatNextEpisodeLine(
  slot: BroadcastSlot,
  now: Date = new Date(),
  timeZone: string,
): string {
  const next = nextEpisodeDate(slot, now, timeZone);
  const formatter = new Intl.DateTimeFormat("en-US", {
    timeZone,
    weekday: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
  return `Next episode on ${formatter.format(next)}`;
}

function calendarDayKey(date: Date, timeZone: string): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

export function latestEpisodeLabel(
  slot: BroadcastSlot,
  now: Date = new Date(),
  timeZone: string,
): string {
  const next = nextEpisodeDate(slot, now, timeZone);
  const last = new Date(next.getTime() - 7 * 86_400_000);
  const nowDay = calendarDayKey(now, timeZone);
  const lastDay = calendarDayKey(last, timeZone);

  if (nowDay === lastDay) return "Today";

  const nowUtc = Date.parse(`${nowDay}T12:00:00Z`);
  const lastUtc = Date.parse(`${lastDay}T12:00:00Z`);
  const daysSince = Math.round((nowUtc - lastUtc) / 86_400_000);

  if (daysSince === 1) return "Yesterday";
  if (daysSince > 1) return `${daysSince} days ago`;
  return "uhh?";
}

export function buildBroadcastAiringLines(
  broadcast: string | null | undefined,
  timeZone: string,
  now: Date = new Date(),
): string[] {
  const slot = parseBroadcast(broadcast);
  if (!slot) return [];
  return [
    formatNextEpisodeLine(slot, now, timeZone),
    `Latest episode: ${latestEpisodeLabel(slot, now, timeZone)}`,
  ];
}

export function mergeAiringLines(
  serverLines: string[],
  broadcast: string | null | undefined,
  timeZone: string,
  now: Date = new Date(),
): string[] {
  const base = serverLines.filter(
    (line) =>
      !line.startsWith("Next episode on") && !line.startsWith("Latest episode:"),
  );
  if (!broadcast) return base;
  return [...base, ...buildBroadcastAiringLines(broadcast, timeZone, now)];
}
