import type { Metadata } from "next";
import { redirect } from "next/navigation";
import AppShell from "@/components/shell/AppShell";
import GenrePageContent from "@/components/library/GenrePageContent";
import {
  resolveBrowsePageSize,
  safeBrowsePage,
} from "@/lib/browse";
import {
  defaultGenreSelection,
  formatGenreLabel,
  genreBrowseUrl,
  parseGenreBrowseParams,
} from "@/lib/genres";

type GenrePageProps = {
  searchParams: Promise<{
    name?: string;
    page?: string;
    size?: string;
  }>;
};

export async function generateMetadata({ searchParams }: GenrePageProps): Promise<Metadata> {
  const params = await searchParams;
  const parsed = parseGenreBrowseParams(params.name);
  const title = parsed ? formatGenreLabel(parsed) : "Browse by genre";
  return { title: `${title} — AnimeManager` };
}

export default async function GenrePage({ searchParams }: GenrePageProps) {
  const params = await searchParams;
  const parsed = parseGenreBrowseParams(params.name);
  const page = safeBrowsePage(params.page);
  const pageSize = resolveBrowsePageSize(params.size);

  if (!parsed) {
    redirect(genreBrowseUrl(defaultGenreSelection(), { size: pageSize }));
  }

  const label = formatGenreLabel(parsed);

  return (
    <AppShell activeNav="library" pageTitle={label}>
      <GenrePageContent
        genres={parsed}
        label={label}
        page={page}
        pageSize={pageSize}
      />
    </AppShell>
  );
}
