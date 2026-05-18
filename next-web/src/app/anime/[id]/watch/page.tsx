import { AppShell } from "@/components/app-shell";
import { WatchView } from "@/components/watch/watch-view";
import { backendFetch } from "@/lib/backend";

type WatchContext = Parameters<typeof WatchView>[0]["ctx"];

export default async function WatchPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ file_id?: string }>;
}) {
  const { id } = await params;
  const { file_id } = await searchParams;
  const animeId = Number(id);
  const ctx = await backendFetch<WatchContext>(
    `/ui/api/anime/${animeId}/watch?file_id=${encodeURIComponent(file_id || "")}`,
  );
  const title = String(ctx.anime?.title || animeId);

  return (
    <AppShell
      activeNav="library"
      topbarTitle={`Watch · ${title.length > 48 ? `${title.slice(0, 47)}…` : title}`}
    >
      <WatchView ctx={ctx} />
    </AppShell>
  );
}
