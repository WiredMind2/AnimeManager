import type { Metadata } from "next";
import Link from "next/link";
import AppShell from "@/components/shell/AppShell";
import LibraryPageContent from "@/components/library/LibraryPageContent";
import { api, ApiError } from "@/lib/api";
import { DEFAULT_USER_ID, type FilterValue } from "@/lib/config";
import {
  apiFilterForBackend,
  filterFooterLabel,
  libraryPageUrl,
  readAnimePerPage,
  readHideRatedDefault,
  resolveHideRated,
  resolvePageSize,
} from "@/lib/library";

type LibraryPageProps = {
  searchParams: Promise<{
    filter?: string;
    q?: string;
    page?: string;
    size?: string;
    hide_rated?: string;
  }>;
};

function safePage(value: string | undefined): number {
  const parsed = Number.parseInt(value ?? "1", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

export async function generateMetadata({ searchParams }: LibraryPageProps): Promise<Metadata> {
  const params = await searchParams;
  const q = (params.q ?? "").trim();
  const pageTitle = q ? "Search results" : "Library";
  return { title: `${pageTitle} — AnimeManager` };
}

export default async function LibraryPage({ searchParams }: LibraryPageProps) {
  const params = await searchParams;
  const page = safePage(params.page);
  const activeFilter = ((params.filter || "DEFAULT") as FilterValue).toUpperCase();
  const qClean = (params.q ?? "").trim();

  let settingsHideRated = false;
  let settingsPageSize = resolvePageSize(undefined, undefined);
  try {
    const settings = await api.getSettings();
    settingsHideRated = readHideRatedDefault(settings);
    settingsPageSize = readAnimePerPage(settings);
  } catch {
    /* use defaults when settings are unavailable */
  }

  const pageSize = resolvePageSize(params.size, settingsPageSize);
  const hideRated = resolveHideRated(params.hide_rated, settingsHideRated);
  const listStart = (page - 1) * pageSize;
  const backendFilter = apiFilterForBackend(activeFilter);

  let items: Awaited<ReturnType<typeof api.getAnimeList>>["items"] = [];
  let hasNext = false;
  let streamingSearch = false;
  let flash: { kind: string; message: string } | null = null;

  if (qClean) {
    if (qClean.length < 3) {
      flash = { kind: "error", message: "Search query must contain at least 3 characters." };
    } else {
      streamingSearch = true;
    }
  } else {
    try {
      const response = await api.getAnimeList({
        filter: backendFilter,
        user_id: DEFAULT_USER_ID,
        list_start: listStart,
        list_stop: listStart + pageSize + 1,
        hide_rated: hideRated,
      });
      const allItems = response.items ?? [];
      hasNext = allItems.length > pageSize || Boolean(response.has_next);
      items = allItems.slice(0, pageSize);
    } catch (err) {
      const message =
        err instanceof ApiError
          ? String((err.detail as { detail?: string })?.detail ?? err.message)
          : err instanceof Error
            ? err.message
            : "Library load failed";
      flash = { kind: "error", message: `Library load failed: ${message}` };
    }
  }

  const urlBase = {
    filter: activeFilter,
    q: qClean,
    size: pageSize,
    hideRated,
    settingsHideRated,
    settingsPageSize,
  };
  const prevUrl = page > 1 ? libraryPageUrl({ ...urlBase, page: page - 1 }) : null;
  const nextUrl = hasNext ? libraryPageUrl({ ...urlBase, page: page + 1 }) : null;
  const pageTitle = qClean ? "Search results" : "Library";

  const topbarActions = (
    <>
      <Link className="btn btn--ghost" href="/torrents">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <path d="M12 3v12" />
          <path d="M6 9l6 6 6-6" />
        </svg>
        Find torrents
      </Link>
      <Link className="btn btn--primary" href="/downloads">
        Downloads
      </Link>
    </>
  );

  return (
    <AppShell
      activeNav="library"
      activeFilter={activeFilter as FilterValue}
      pageTitle={pageTitle}
      topbarActions={topbarActions}
      flash={flash}
    >
      <LibraryPageContent
        pageTitle={pageTitle}
        q={qClean}
        activeFilter={activeFilter}
        streamingSearch={streamingSearch}
        items={items}
        hasNext={hasNext}
        listStart={listStart}
        prevUrl={prevUrl}
        nextUrl={nextUrl}
        pageSize={pageSize}
        hideRated={hideRated}
        settingsHideRated={settingsHideRated}
        settingsPageSize={settingsPageSize}
        filterFooterLabel={filterFooterLabel(activeFilter)}
      />
    </AppShell>
  );
}
