import AppShell from "@/components/shell/AppShell";
import { CardGridSkeleton, PageHeadSkeleton } from "@/components/shell/RouteSkeletons";

export default function LibraryLoading() {
  return (
    <AppShell activeNav="library" pageTitle="Library">
      <PageHeadSkeleton />
      <CardGridSkeleton />
    </AppShell>
  );
}
