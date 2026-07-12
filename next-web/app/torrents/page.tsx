import { redirect } from "next/navigation";

type PageProps = {
  searchParams: Promise<{ anime_id?: string }>;
};

/** Legacy route — torrent search lives on anime detail pages only. */
export default async function TorrentsRedirectPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const animeIdRaw = params.anime_id?.trim();
  const animeId = animeIdRaw ? Number(animeIdRaw) : NaN;

  if (Number.isFinite(animeId) && animeId > 0) {
    redirect(`/anime/${animeId}?tab=torrents`);
  }

  redirect("/library");
}
