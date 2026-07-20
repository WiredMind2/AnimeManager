import AppShell from "@/components/shell/AppShell";
import { CardGridSkeleton, PageHeadSkeleton } from "@/components/shell/RouteSkeletons";

export default function GenreBrowseLoading() {
  return (
    <AppShell activeNav="library" pageTitle="Browse by genre">
      <PageHeadSkeleton />
      <CardGridSkeleton />
    </AppShell>
  );
}
