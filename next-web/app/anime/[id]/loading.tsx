import AppShell from "@/components/shell/AppShell";
import { DetailSkeleton, PanelSkeleton } from "@/components/shell/RouteSkeletons";

export default function AnimeDetailLoading() {
  return (
    <AppShell activeNav="library">
      <DetailSkeleton />
      <PanelSkeleton rows={5} />
    </AppShell>
  );
}
