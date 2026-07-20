import AppShell from "@/components/shell/AppShell";
import { CardGridSkeleton, PageHeadSkeleton } from "@/components/shell/RouteSkeletons";

export default function TopBrowseLoading() {
  return (
    <AppShell activeNav="library" pageTitle="Top anime">
      <PageHeadSkeleton />
      <CardGridSkeleton />
    </AppShell>
  );
}
