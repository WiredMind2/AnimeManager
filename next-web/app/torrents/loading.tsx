import AppShell from "@/components/shell/AppShell";
import { PageHeadSkeleton, PanelSkeleton } from "@/components/shell/RouteSkeletons";

export default function TorrentsLoading() {
  return (
    <AppShell activeNav="torrents" pageTitle="Torrent search">
      <PageHeadSkeleton />
      <PanelSkeleton rows={10} />
    </AppShell>
  );
}
