"use client";

import { useEffect, useState } from "react";
import type { LogRecord } from "@/lib/api";
import { formatAbsoluteTs } from "@/lib/logs";

type LogRowProps = {
  record: LogRecord;
  flash?: boolean;
  hidden?: boolean;
};

export default function LogRow({ record, flash = false, hidden = false }: LogRowProps) {
  const level = (record.level ?? "INFO").toUpperCase();
  const category = String(record.category ?? "OTHER").toUpperCase();
  const [flashing, setFlashing] = useState(flash);

  useEffect(() => {
    if (!flash) return;
    setFlashing(true);
    const timer = window.setTimeout(() => setFlashing(false), 1100);
    return () => window.clearTimeout(timer);
  }, [flash, record.id]);

  return (
    <li
      className={`log-row log-row--${level.toLowerCase()}`}
      data-log-row
      data-log-id={String(record.id ?? "")}
      data-log-level={level}
      data-log-logger={record.logger ?? ""}
      data-log-category={category}
      hidden={hidden}
      {...(flashing ? { "data-log-flash": "1" } : {})}
    >
      <time className="log-row__ts" dateTime={String(record.ts ?? "")}>
        {formatAbsoluteTs(record.ts)}
      </time>
      <span className="log-row__level">{level}</span>
      <span className="log-row__category" title={category}>
        {category}
      </span>
      <span className="log-row__logger" title={record.logger ?? ""}>
        {record.logger ?? ""}
      </span>
      <span className="log-row__msg">{record.message ?? ""}</span>
      {record.exc_info ? <pre className="log-row__exc">{record.exc_info}</pre> : null}
    </li>
  );
}
