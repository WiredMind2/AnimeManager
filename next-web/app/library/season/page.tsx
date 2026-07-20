import type { Metadata } from "next";
import { redirect } from "next/navigation";
import AppShell from "@/components/shell/AppShell";
import SeasonPageContent from "@/components/library/SeasonPageContent";
import {
  resolveBrowsePageSize,
  safeBrowsePage,
} from "@/lib/browse";
import {
  currentAiringSeason,
  formatSeasonLabel,
  parseSeasonBrowseParams,
  seasonBrowseUrl,
} from "@/lib/season";

type SeasonPageProps = {
  searchParams: Promise<{
    year?: string;
    season?: string;
    page?: string;
    size?: string;
  }>;
};

export async function generateMetadata({ searchParams }: SeasonPageProps): Promise<Metadata> {
  const params = await searchParams;
  const parsed = parseSeasonBrowseParams(params.season, params.year);
  const title = parsed ? formatSeasonLabel(parsed.season, parsed.year) : "Browse by season";
  return { title: `${title} — AnimeManager` };
}

export default async function SeasonPage({ searchParams }: SeasonPageProps) {
  const params = await searchParams;
  const parsed = parseSeasonBrowseParams(params.season, params.year);
  const page = safeBrowsePage(params.page);
  const pageSize = resolveBrowsePageSize(params.size);

  if (!parsed) {
    const defaults = currentAiringSeason();
    redirect(seasonBrowseUrl(defaults.year, defaults.season, { size: pageSize }));
  }

  const label = formatSeasonLabel(parsed.season, parsed.year);

  return (
    <AppShell activeNav="library" pageTitle={label}>
      <SeasonPageContent
        year={parsed.year}
        season={parsed.season}
        label={label}
        page={page}
        pageSize={pageSize}
      />
    </AppShell>
  );
}
