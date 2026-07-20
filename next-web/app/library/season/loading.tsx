import AppShell from "@/components/shell/AppShell";
import { CardGridSkeleton, PageHeadSkeleton } from "@/components/shell/RouteSkeletons";

export default function SeasonBrowseLoading() {
  return (
    <AppShell activeNav="library" pageTitle="Browse by season">
      <PageHeadSkeleton />
      <CardGridSkeleton />
    </AppShell>
  );
}
