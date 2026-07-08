import type { Metadata } from "next";
import { redirect } from "next/navigation";
import AppShell from "@/components/shell/AppShell";
import GenrePageContent from "@/components/library/GenrePageContent";
import { formatGenreLabel, GENRES, parseGenreBrowseParams } from "@/lib/genres";

type GenrePageProps = {
  searchParams: Promise<{
    name?: string;
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

  if (!parsed) {
    redirect(`/library/genre?name=${encodeURIComponent(GENRES[0])}`);
  }

  const label = formatGenreLabel(parsed);

  return (
    <AppShell activeNav="library" pageTitle={label}>
      <GenrePageContent genre={parsed} label={label} />
    </AppShell>
  );
}
