import type { Metadata } from "next";
import { redirect } from "next/navigation";
import AppShell from "@/components/shell/AppShell";
import TopPageContent from "@/components/library/TopPageContent";
import {
  resolveBrowsePageSize,
  safeBrowsePage,
} from "@/lib/browse";
import {
  defaultTopCategory,
  formatTopLabel,
  parseTopBrowseParams,
  topBrowseUrl,
} from "@/lib/top";

type TopPageProps = {
  searchParams: Promise<{
    category?: string;
    page?: string;
    size?: string;
  }>;
};

export async function generateMetadata({ searchParams }: TopPageProps): Promise<Metadata> {
  const params = await searchParams;
  const parsed = parseTopBrowseParams(params.category);
  const title = parsed ? `Top · ${formatTopLabel(parsed)}` : "Top by popularity";
  return { title: `${title} — AnimeManager` };
}

export default async function TopPage({ searchParams }: TopPageProps) {
  const params = await searchParams;
  const parsed = parseTopBrowseParams(params.category);
  const page = safeBrowsePage(params.page);
  const pageSize = resolveBrowsePageSize(params.size);

  if (!parsed) {
    redirect(topBrowseUrl(defaultTopCategory(), { size: pageSize }));
  }

  const label = formatTopLabel(parsed);

  return (
    <AppShell activeNav="library" pageTitle={`Top · ${label}`}>
      <TopPageContent
        category={parsed}
        label={label}
        page={page}
        pageSize={pageSize}
      />
    </AppShell>
  );
}
