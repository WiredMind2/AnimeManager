import type { Metadata } from "next";
import Link from "next/link";
import AppShell from "@/components/shell/AppShell";
import LibraryPageContent from "@/components/library/LibraryPageContent";
import { api, ApiError } from "@/lib/api";
import { DEFAULT_USER_ID, PAGE_SIZE, type FilterValue } from "@/lib/config";

type LibraryPageProps = {
  searchParams: Promise<{
    filter?: string;
    q?: string;
    page?: string;
  }>;
};

function safePage(value: string | undefined): number {
  const parsed = Number.parseInt(value ?? "1", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

function pageUrl(pageNum: number, activeFilter: string, q: string): string {
  const parts = [`page=${pageNum}`];
  if (activeFilter && activeFilter !== "DEFAULT") {
    parts.push(`filter=${activeFilter}`);
  }
  if (q) {
    parts.push(`q=${encodeURIComponent(q)}`);
  }
  return `/library?${parts.join("&")}`;
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
  const listStart = (page - 1) * PAGE_SIZE;

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
        filter: activeFilter,
        user_id: DEFAULT_USER_ID,
        list_start: listStart,
        list_stop: listStart + PAGE_SIZE + 1,
      });
      const allItems = response.items ?? [];
      hasNext = allItems.length > PAGE_SIZE || Boolean(response.has_next);
      items = allItems.slice(0, PAGE_SIZE);
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

  const prevUrl = page > 1 ? pageUrl(page - 1, activeFilter, qClean) : null;
  const nextUrl = hasNext ? pageUrl(page + 1, activeFilter, qClean) : null;
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
      />
    </AppShell>
  );
}
