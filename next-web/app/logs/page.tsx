import AppShell from "@/components/shell/AppShell";
import LogConsole from "@/components/logs/LogConsole";
import { api } from "@/lib/api";
import {
  KNOWN_CATEGORIES,
  LOG_TAIL_INITIAL,
  filtersToQuery,
  mergeKnownCategories,
  normalizeCategories,
  type LogFilters,
} from "@/lib/logs";

type PageProps = {
  searchParams: Promise<{
    level?: string;
    logger?: string;
    q?: string;
    category?: string | string[];
  }>;
};

export const metadata = {
  title: "Logs — AnimeManager",
};

function parseAppliedFilters(params: {
  level?: string;
  logger?: string;
  q?: string;
  category?: string | string[];
}): LogFilters {
  return {
    level: (params.level ?? "").toUpperCase(),
    logger: (params.logger ?? "").trim(),
    q: (params.q ?? "").trim(),
    categories: normalizeCategories(params.category),
  };
}

function resolveDisabledCategories(
  settings: Record<string, unknown>,
  knownCategories: string[],
): string[] {
  const logs = settings.logs;
  if (!logs || typeof logs !== "object" || Array.isArray(logs)) {
    return [];
  }
  const enabled = (logs as Record<string, unknown>).enabled_categories;
  if (!Array.isArray(enabled)) {
    return [];
  }
  const enabledSet = new Set(enabled.map((c) => String(c).toUpperCase()));
  return knownCategories.filter((cat) => !enabledSet.has(cat.toUpperCase()));
}

export default async function LogsPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const appliedFilters = parseAppliedFilters(params);

  let settings: Record<string, unknown> = {};
  try {
    settings = (await api.getSettings()) ?? {};
  } catch {
    settings = {};
  }

  let initialRecords: Awaited<ReturnType<typeof api.getLogsData>>["records"] = [];
  let initialLastId = 0;
  let initialBuffered = 0;

  try {
    const data = await api.getLogsData({
      ...filtersToQuery(appliedFilters),
      limit: LOG_TAIL_INITIAL,
    });
    initialRecords = data.records ?? [];
    initialLastId = data.last_id ?? 0;
    initialBuffered = data.buffered ?? 0;
  } catch {
    initialRecords = [];
    initialLastId = 0;
    initialBuffered = 0;
  }

  let knownCategories: string[] = [...KNOWN_CATEGORIES];
  const logsSection = settings.logs;
  if (logsSection && typeof logsSection === "object" && !Array.isArray(logsSection)) {
    const enabled = (logsSection as Record<string, unknown>).enabled_categories;
    if (Array.isArray(enabled)) {
      for (const cat of enabled.map(String)) {
        if (!knownCategories.includes(cat)) knownCategories.push(cat);
      }
    }
  }
  knownCategories = mergeKnownCategories(initialRecords);

  const disabledInSettings = resolveDisabledCategories(settings, knownCategories);

  return (
    <AppShell activeNav="logs" pageTitle="Logs" showSearch={false}>
      <LogConsole
        initialRecords={initialRecords}
        initialLastId={initialLastId}
        initialBuffered={initialBuffered}
        appliedFilters={appliedFilters}
        knownCategories={knownCategories}
        disabledInSettings={disabledInSettings}
      />
    </AppShell>
  );
}
