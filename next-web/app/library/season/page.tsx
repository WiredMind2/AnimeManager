import type { Metadata } from "next";
import { redirect } from "next/navigation";
import AppShell from "@/components/shell/AppShell";
import SeasonPageContent from "@/components/library/SeasonPageContent";
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

  if (!parsed) {
    const defaults = currentAiringSeason();
    redirect(seasonBrowseUrl(defaults.year, defaults.season));
  }

  const label = formatSeasonLabel(parsed.season, parsed.year);

  return (
    <AppShell activeNav="library" pageTitle={label}>
      <SeasonPageContent year={parsed.year} season={parsed.season} label={label} />
    </AppShell>
  );
}
